"""FiberQ interchange bundle writer — WP3 task 3.2, the QGIS-facing half.

``interchange.py`` owns the format contract and knows nothing about QGIS. This
module is the other half: it reads a live QGIS project and writes a conformant
bundle, as specified in ``docs/interchange-format.md``.

**This does not change how FiberQ stores anything.** The project's layers, their
names and their fields are read and left exactly as they are; a bundle is an
export artefact, not the project's storage. In particular, and unlike
``ExportManager.save_all_layers_to_gpkg``, nothing here redirects a layer's data
source at the file it just wrote.

Three things the existing GeoPackage export loses, and this writer does not:

1. **Metadata written by another tool.** The old writer drops and recreates
   ``_fiberq_metadata`` on every export, so a key it did not write does not
   survive one. Here the table is read first and merged.
2. **Relations and cable path stops.** Both live in the project file as opaque
   JSON keyed by ``(layer_id, fid)`` -- identifiers that are local to one QGIS
   project and mean nothing after a round trip. They are emitted here as
   ``fiberq_uuid``-keyed side-car rows, which do survive.
3. **Anything the plugin has no model for.** Passthrough rows stashed by an
   import are written back out verbatim (spec section 8).
"""
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsCoordinateTransformContext, QgsField, QgsProject, QgsVectorFileWriter,
    QgsVectorLayer,
)
from . import interchange as ic
from . import interchange_fields as fm
from ..models.schema import SCHEMA_VERSION, canonical_layer_name
from ..utils.logger import get_logger
from ..utils.uuid_utils import FIBERQ_UUID_FIELD

logger = get_logger(__name__)


def _text_field(name):
    """A text :class:`QgsField`, built with the constructor this QGIS accepts.

    QGIS 3.38 deprecated the ``QVariant``-typed constructor in favour of
    ``QMetaType``; QGIS 3.22 LTR, which this plugin still targets, only has the
    old one. Older modules in this package still use ``QVariant`` directly --
    that is deferred debt, not the pattern to copy.
    """
    try:
        from qgis.PyQt.QtCore import QMetaType
        return QgsField(name, QMetaType.Type.QString)
    except (ImportError, AttributeError, TypeError):
        from qgis.PyQt.QtCore import QVariant
        return QgsField(name, QVariant.String)


#: Columns this writer stamps onto every feature layer in a bundle. Values
#: already present on a feature are never overwritten -- that is what lets a
#: bundle imported from a tool with richer types leave through here unchanged.
STAMP_COLUMNS = ("fq_type", "placement", "fq_extra_json")


class BundleResult:
    """What a bundle write actually did, in enough detail to assert on.

    Deliberately verbose: an export that quietly dropped a layer and an export
    that had nothing to drop look identical from a success message alone, and
    the whole point of this format is that loss is never silent.
    """

    def __init__(self, path=""):
        self.path = path
        self.layers = {}          # canonical layer name -> features written
        self.types = {}           # canonical layer name -> (fq_type, placement)
        self.skipped = []         # (layer name, reason)
        self.sidecar_rows = {}    # fq_* table -> rows written
        self.metadata = {}        # the merged table as written
        self.preserved = {}       # metadata keys kept on another tool's behalf
        self.inlined_extras = 0   # features whose kept extras went back into the bundle
        self.warnings = []
        self.errors = []

    @property
    def ok(self):
        return not self.errors

    @property
    def feature_count(self):
        return sum(self.layers.values())

    def summary(self):
        parts = [f"{len(self.layers)} layer(s), {self.feature_count} feature(s)"]
        rows = sum(self.sidecar_rows.values())
        if rows:
            parts.append(f"{rows} side-car row(s)")
        if self.preserved:
            parts.append(f"{len(self.preserved)} foreign metadata key(s) preserved")
        if self.skipped:
            parts.append(f"{len(self.skipped)} layer(s) not part of the bundle")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Metadata: read before writing, merge, never replace
# ---------------------------------------------------------------------------

def read_bundle_metadata(gpkg_path):
    """The ``_fiberq_metadata`` table of an existing bundle, or ``{}``.

    Called *before* anything is written, because the merge needs to know what
    another tool put there and a half-written file no longer does.
    """
    if not gpkg_path or not os.path.isfile(gpkg_path):
        return {}
    conn = None
    try:
        conn = sqlite3.connect(gpkg_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_fiberq_metadata'"
        )
        if cur.fetchone() is None:
            return {}
        return {
            str(k): ("" if v is None else str(v))
            for k, v in conn.execute("SELECT key, value FROM _fiberq_metadata")
        }
    except sqlite3.Error as e:
        logger.debug(f"Could not read existing bundle metadata from {gpkg_path}: {e}")
        return {}
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------

class InterchangeBundleWriter:
    """Writes a FiberQ interchange bundle from a QGIS project."""

    def __init__(self, project=None, plugin_version=None):
        self.project = project or QgsProject.instance()
        self.plugin_version = plugin_version or self._detect_version()
        self._unresolved_cable_refs = 0

    @staticmethod
    def _detect_version():
        try:
            from .. import __version__
            return __version__
        except Exception as e:
            logger.debug(f"Could not read plugin version: {e}")
            return "unknown"

    # -- layer selection ---------------------------------------------------

    def classify_layers(self, layers=None):
        """Split the project's layers into what belongs in a bundle and what does not.

        Returns ``(mapped, skipped)`` where *mapped* is a list of
        ``(layer, canonical_name, fq_type, placement)`` and *skipped* is a list
        of ``(layer_name, reason)``. Nothing is dropped without a reason the
        caller can show the user.
        """
        if layers is None:
            layers = [
                lyr for lyr in self.project.mapLayers().values()
                if isinstance(lyr, QgsVectorLayer)
            ]
        mapped, skipped = [], []
        for lyr in layers:
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                skipped.append((getattr(lyr, "name", lambda: "?")(), "not a valid vector layer"))
                continue
            canonical = canonical_layer_name(lyr.name())
            if canonical is None:
                skipped.append((lyr.name(), "not a FiberQ layer"))
                continue
            entry = ic.type_for_layer(canonical)
            if entry is None:
                # A FiberQ layer the format has no code for. Not silently
                # dropped: the format's first rule says carry it, so say so.
                skipped.append((lyr.name(), f"no fq_type for canonical layer '{canonical}'"))
                continue
            fq_type, placement = entry
            mapped.append((lyr, canonical, fq_type, placement))
        return mapped, skipped

    # -- identity index ----------------------------------------------------

    def build_uuid_index(self, mapped):
        """``(layer_id, fid) -> fiberq_uuid`` for every feature going into the bundle.

        Relations and latent path stops are stored against ``(layer_id, fid)``,
        which is local to one QGIS project. This index is what turns them into
        references the format can actually carry.
        """
        index = {}
        for lyr, _canonical, _t, _p in mapped:
            if lyr.fields().indexFromName(FIBERQ_UUID_FIELD) < 0:
                continue
            for feat in lyr.getFeatures():
                value = feat[FIBERQ_UUID_FIELD]
                if value is None:
                    continue
                text = str(value).strip()
                if text and text.lower() != "null":
                    index[(lyr.id(), int(feat.id()))] = text
        return index

    # -- feature layers ----------------------------------------------------

    def _write_layer(self, layer, canonical, gpkg_path, file_exists):
        """Write one layer into the bundle, reprojected to the storage CRS."""
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        opts.layerName = canonical
        opts.actionOnExistingFile = (
            QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
            if file_exists
            else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        )
        target = QgsCoordinateReferenceSystem.fromEpsgId(ic.STORAGE_EPSG)
        if layer.crs().isValid() and layer.crs() != target:
            opts.ct = QgsCoordinateTransform(layer.crs(), target, self.project)
        else:
            opts.destCRS = target

        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, gpkg_path, QgsCoordinateTransformContext(), opts
        )
        if isinstance(result, tuple):
            code, message = result[0], (result[1] if len(result) > 1 else "")
        else:
            code, message = result, ""
        if code != QgsVectorFileWriter.WriterError.NoError:
            return message or f"writer error {code}"
        return None

    @staticmethod
    def _is_blank(value):
        if value is None:
            return True
        if hasattr(value, "isNull") and value.isNull():
            return True
        return str(value).strip() == ""

    def _canonicalise_layer(self, gpkg_path, table, fq_type, placement, index,
                            extras=None):
        """Turn a written FiberQ table into a conformant bundle layer.

        Four things happen here, all of them on the copy in the bundle and none
        of them on the user's project:

        * the bundle's own columns are added and filled (``fq_type``,
          ``placement``, ``fq_extra_json``);
        * controlled values are translated to the canonical vocabulary, so a
          reader does not have to know that ``vazdusna`` means aerial;
        * ``(cable_layer_id, cable_fid)`` -- a QGIS-local pair -- is replaced by
          a ``cable_uuid`` that means something outside this project;
        * stored field names are renamed to their canonical ones.

        Done through the OGR provider rather than raw SQL: a GeoPackage feature
        table carries spatial-index triggers that call GDAL-registered SQL
        functions, so a plain sqlite3 UPDATE fails on it. The side-car and
        metadata tables have no such triggers and are written directly.
        """
        layer = QgsVectorLayer(f"{gpkg_path}|layername={table}", table, "ogr")
        if not layer.isValid():
            return f"could not reopen '{table}' to write the bundle columns"
        provider = layer.dataProvider()
        roster = fm.roster_for_type(fq_type)

        structural = [
            name for name in fm.STRUCTURAL_FIELDS
            if layer.fields().indexFromName(name) >= 0
        ]
        wanted = list(STAMP_COLUMNS)
        if structural:
            wanted.append(fm.CABLE_REFERENCE_FIELD)
        missing = [
            _text_field(name) for name in wanted
            if layer.fields().indexFromName(name) < 0
        ]
        if missing and not provider.addAttributes(missing):
            return f"could not add the bundle columns to '{table}'"
        layer.updateFields()

        fields = layer.fields()
        type_idx = fields.indexFromName("fq_type")
        place_idx = fields.indexFromName("placement")
        if type_idx < 0:
            return f"no fq_type column on '{table}'"

        # Fields whose values come from a controlled vocabulary, resolved once
        # rather than per feature.
        domains = []
        if roster:
            for stored_name, canonical_name in fm.ROSTERS.get(roster, {}).items():
                idx = fields.indexFromName(stored_name)
                if idx >= 0 and fm.VALUE_DOMAINS.get(f"{roster}/{canonical_name}"):
                    domains.append((idx, canonical_name))

        cable_layer_idx = fields.indexFromName("cable_layer_id")
        cable_fid_idx = fields.indexFromName("cable_fid")
        cable_uuid_idx = fields.indexFromName(fm.CABLE_REFERENCE_FIELD)
        identity_idx = fields.indexFromName(FIBERQ_UUID_FIELD)
        extra_idx = fields.indexFromName("fq_extra_json")

        unresolved = 0
        changes = {}
        for feat in layer.getFeatures():
            attrs = {}
            if self._is_blank(feat.attribute(type_idx)):
                attrs[type_idx] = fq_type
            if placement and place_idx >= 0 and self._is_blank(feat.attribute(place_idx)):
                attrs[place_idx] = placement
            for idx, canonical_name in domains:
                raw = feat.attribute(idx)
                if self._is_blank(raw):
                    continue
                translated = fm.canonical_value(roster, canonical_name, raw)
                if translated != raw:
                    attrs[idx] = translated
            if extras and extra_idx >= 0 and identity_idx >= 0:
                identity = feat.attribute(identity_idx)
                payload = extras.get(str(identity)) if identity else None
                if payload and self._is_blank(feat.attribute(extra_idx)):
                    attrs[extra_idx] = (
                        payload if isinstance(payload, str) else json.dumps(payload))
            if cable_uuid_idx >= 0 and cable_layer_idx >= 0 and cable_fid_idx >= 0:
                resolved = self._resolve(
                    index, feat.attribute(cable_layer_idx), feat.attribute(cable_fid_idx))
                if resolved is not None:
                    attrs[cable_uuid_idx] = resolved
                elif not self._is_blank(feat.attribute(cable_fid_idx)):
                    unresolved += 1
            if attrs:
                changes[feat.id()] = attrs
        if changes and not provider.changeAttributeValues(changes):
            return f"could not write the bundle columns onto '{table}'"

        # Rename before deleting: renaming leaves indices alone, deleting does not.
        if roster:
            renames = {}
            for stored_name, canonical_name in fm.ROSTERS.get(roster, {}).items():
                if stored_name == canonical_name:
                    continue
                idx = layer.fields().indexFromName(stored_name)
                if idx >= 0:
                    renames[idx] = canonical_name
            if renames and not provider.renameAttributes(renames):
                return f"could not rename '{table}' fields to their canonical names"
            layer.updateFields()

        if structural:
            drop = [
                layer.fields().indexFromName(name) for name in structural
                if layer.fields().indexFromName(name) >= 0
            ]
            if drop and not provider.deleteAttributes(drop):
                # Not fatal: cable_uuid is written either way, so the reference
                # travels. The local pair simply rides along as dead weight.
                logger.debug(f"Could not drop the project-local cable reference from {table}")

        self._unresolved_cable_refs += unresolved
        return None

    # -- side-car ----------------------------------------------------------

    @staticmethod
    def _create_sidecar(conn, timestamp):
        """Create the ``fq_*`` tables and register them so GDAL lists them."""
        for statement in ic.SIDECAR_DDL:
            conn.execute(statement)
        names = [
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fq\\_%' ESCAPE '\\'"
            )
        ]
        for name in names:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO gpkg_contents "
                    "(table_name, data_type, identifier, description, last_change, srs_id) "
                    "VALUES (?, 'attributes', ?, ?, ?, 0)",
                    (name, name, f"FiberQ interchange side-car table {name}", timestamp),
                )
            except sqlite3.Error as e:
                # A GeoPackage without gpkg_contents is malformed, but the data
                # is still readable by any SQLite client, so this is not fatal.
                logger.debug(f"Could not register {name} in gpkg_contents: {e}")

    def _write_relations(self, conn, index):
        """Emit the project's cable relations as uuid-keyed side-car rows.

        The plugin stores relations as ``{"relations": [{"id", "name",
        "cables": [{"layer_id", "fid"}]}]}``. Cables whose identity cannot be
        resolved are counted, not guessed at.
        """
        raw = self.project.readEntry("StuboviPlugin", "Relacije/relations_v1", "")[0]
        if not raw:
            return 0, 0, 0
        try:
            data = json.loads(raw)
        except ValueError as e:
            logger.debug(f"Relations entry is not valid JSON, not exported: {e}")
            return 0, 0, 0

        project_key = self.project.fileName() or self.project.title() or ""
        relations = written_members = unresolved = 0
        for relation in data.get("relations", []) or []:
            rid = relation.get("id")
            name = relation.get("name", "") or ""
            relation_uuid = ic.stable_uuid("relation", project_key, rid, name)
            conn.execute(
                "INSERT OR REPLACE INTO fq_relation (uuid, name, category) VALUES (?, ?, ?)",
                (relation_uuid, name, "cable_group"),
            )
            relations += 1
            for order, cable in enumerate(relation.get("cables", []) or []):
                member = self._resolve(index, cable.get("layer_id"), cable.get("fid"))
                if member is None:
                    unresolved += 1
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO fq_relation_member "
                    "(relation_uuid, member_uuid, order_index, role) VALUES (?, ?, ?, ?)",
                    (relation_uuid, member, order, "cable"),
                )
                written_members += 1
        return relations, written_members, unresolved

    def _write_path_stops(self, conn, index):
        """Emit latent elements as ``fq_path_stop`` rows, ordered along the cable.

        The plugin stores these as ``{"cables": {"<layer_id>:<fid>": [{...,
        "m": <distance along cable>}]}}``. ``m`` is what gives the stops their
        order; it is a project-local measurement and does not itself travel.
        """
        raw = self.project.readEntry("StuboviPlugin", "LatentElements/latent_v1", "")[0]
        if not raw:
            return 0, 0
        try:
            data = json.loads(raw)
        except ValueError as e:
            logger.debug(f"Latent elements entry is not valid JSON, not exported: {e}")
            return 0, 0

        written = unresolved = 0
        for key, elements in (data.get("cables", {}) or {}).items():
            layer_id, _, fid = str(key).rpartition(":")
            cable_uuid = self._resolve(index, layer_id, fid)
            if cable_uuid is None:
                unresolved += len(elements or [])
                continue
            ordered = sorted(
                elements or [],
                key=lambda e: float(e.get("m") or 0.0),
            )
            for order, element in enumerate(ordered):
                element_uuid = self._resolve(index, element.get("layer_id"), element.get("fid"))
                if element_uuid is None:
                    unresolved += 1
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO fq_path_stop "
                    "(cable_uuid, element_uuid, order_index, is_latent) VALUES (?, ?, ?, 1)",
                    (cable_uuid, element_uuid, order),
                )
                written += 1
        return written, unresolved

    def _load_passthrough(self, passthrough=None):
        """The passthrough store, split by what each row must become on the way out.

        Returns ``(extensions, attributes, sidecar, metadata)``: rows to emit
        verbatim as ``fq_extension``, per-feature extras to inline into
        ``fq_extra_json`` keyed by the feature they belong to, side-car rows to
        write back into the real table they came from, and the metadata keys
        another tool wrote, to merge into this bundle's own.

        The kind decides the destination. A side-car table kept as a blob and
        re-emitted as a blob would still be lossless, but it would stop being
        *relational* -- and a tool that does model fibre splicing could no longer
        query it. Rule 1 is about the data arriving usable, not merely present.
        """
        if passthrough is None:
            raw = self.project.readEntry(*ic.PASSTHROUGH_ENTRY, "")[0]
            if not raw:
                return [], {}, {}, {}
            try:
                passthrough = json.loads(raw)
            except ValueError as e:
                logger.debug(f"Passthrough store is not valid JSON, not exported: {e}")
                return [], {}, {}, {}

        extensions, attributes, sidecar, metadata = [], {}, {}, {}
        for row in passthrough or []:
            kind = row.get("kind")
            payload = row.get("payload_json")
            if kind == ic.EXTENSION_KIND_METADATA:
                try:
                    parsed = json.loads(payload) if isinstance(payload, str) else payload
                except ValueError as e:
                    logger.debug(f"Kept metadata payload is not valid JSON: {e}")
                    extensions.append(row)
                    continue
                if isinstance(parsed, dict):
                    metadata.update(parsed)
                else:
                    extensions.append(row)
            elif kind == ic.EXTENSION_KIND_ATTRIBUTES and row.get("owner_uuid"):
                attributes[str(row["owner_uuid"])] = payload
            elif kind == ic.EXTENSION_KIND_SIDECAR:
                try:
                    parsed = json.loads(payload) if isinstance(payload, str) else payload
                except ValueError as e:
                    logger.debug(f"Kept side-car payload is not valid JSON: {e}")
                    extensions.append(row)
                    continue
                table = (parsed or {}).get("table")
                if table in ic.SIDECAR_TABLES:
                    sidecar.setdefault(table, []).extend((parsed or {}).get("rows", []))
                else:
                    extensions.append(row)
            else:
                extensions.append(row)
        return extensions, attributes, sidecar, metadata

    def _write_passthrough(self, conn, extensions):
        """Write back everything that stays an extension row (spec section 8)."""
        written = 0
        for row in extensions or []:
            payload = row.get("payload_json")
            conn.execute(
                "INSERT OR REPLACE INTO fq_extension "
                "(uuid, owner_uuid, kind, namespace, payload_json, produced_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row.get("uuid"), row.get("owner_uuid"), row.get("kind"),
                    row.get("namespace"),
                    payload if isinstance(payload, str) else json.dumps(payload),
                    row.get("produced_by"),
                ),
            )
            written += 1
        return written

    @staticmethod
    def _write_kept_sidecar(conn, sidecar):
        """Write kept side-car rows back into the tables they came from.

        Columns are taken from the bundle's own tables rather than from the
        kept rows, so a row that arrived with a column this DDL does not have
        cannot break the insert -- and the rest of it still lands.
        """
        written = 0
        for table, rows in (sidecar or {}).items():
            if not rows:
                continue
            columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            if not columns:
                continue
            placeholders = ", ".join("?" for _ in columns)
            quoted = ", ".join(f'"{c}"' for c in columns)
            # Table and column names come from ic.SIDECAR_TABLES and the
            # bundle's own schema, never from the row data.
            sql = f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({placeholders})'  # nosec B608
            for row in rows:
                conn.execute(sql, [row.get(c) for c in columns])
                written += 1
        return written

    @staticmethod
    def _resolve(index, layer_id, fid):
        """``(layer_id, fid)`` -> ``fiberq_uuid``, or ``None`` if it does not resolve."""
        if layer_id is None or fid is None:
            return None
        try:
            return index.get((str(layer_id), int(fid)))
        except (TypeError, ValueError):
            return None

    # -- metadata ----------------------------------------------------------

    def _write_metadata(self, conn, existing, timestamp):
        """Write the merged metadata table, keeping every foreign key intact."""
        crs = self.project.crs()
        epsg = ""
        if crs.isValid():
            authid = crs.authid()
            epsg = authid.split(":")[-1] if ":" in authid else authid

        produced = ic.build_metadata(
            schema_version=SCHEMA_VERSION,
            crs_epsg=epsg,
            plugin_version=self.plugin_version,
            timestamp=timestamp,
            color_standard=self._color_standard(),
        )
        merged = ic.merge_metadata(existing, produced)

        conn.execute(
            "CREATE TABLE IF NOT EXISTS _fiberq_metadata "
            "(key TEXT PRIMARY KEY, value TEXT)"
        )
        try:
            conn.execute(
                "INSERT OR REPLACE INTO gpkg_contents "
                "(table_name, data_type, identifier, description, last_change, srs_id) "
                "VALUES ('_fiberq_metadata', 'attributes', '_fiberq_metadata', ?, ?, 0)",
                ("FiberQ interchange bundle metadata", timestamp),
            )
        except sqlite3.Error as e:
            logger.debug(f"Could not register _fiberq_metadata in gpkg_contents: {e}")

        for key, value in merged.items():
            conn.execute(
                "INSERT OR REPLACE INTO _fiberq_metadata (key, value) VALUES (?, ?)",
                (key, "" if value is None else str(value)),
            )
        return merged

    def _color_standard(self):
        raw = self.project.readEntry("StuboviPlugin", "ColorCatalogs/catalogs_v1", "")[0]
        if not raw:
            return "TIA-598-C"
        try:
            catalogs = json.loads(raw).get("catalogs", []) or []
        except ValueError as e:
            logger.debug(f"Colour catalogue entry is not valid JSON: {e}")
            return "TIA-598-C"
        for catalog in catalogs:
            name = (catalog.get("name") or "").strip()
            if name:
                return name
        return "TIA-598-C"

    # -- the whole thing ---------------------------------------------------

    def write(self, gpkg_path, layers=None, passthrough=None):
        """Write a bundle to ``gpkg_path`` and report exactly what went into it."""
        if not gpkg_path:
            result = BundleResult()
            result.errors.append("No output path given.")
            return result
        if not gpkg_path.lower().endswith(".gpkg"):
            gpkg_path += ".gpkg"

        result = BundleResult(gpkg_path)
        mapped, skipped = self.classify_layers(layers)
        result.skipped = skipped
        if not mapped:
            result.errors.append(
                "No FiberQ layers in this project, so there is nothing to put in a bundle."
            )
            return result

        # Read first: a half-written file no longer knows what another tool put
        # in it, and this is the merge's only chance to find out.
        existing = read_bundle_metadata(gpkg_path)
        index = self.build_uuid_index(mapped)

        missing_identity = [
            canonical for lyr, canonical, _t, _p in mapped
            if lyr.fields().indexFromName(FIBERQ_UUID_FIELD) < 0
        ]
        if missing_identity:
            names = ", ".join(sorted(set(missing_identity)))
            result.warnings.append(
                f"No fiberq_uuid field on: {names}. Relations and path stops on "
                "those layers cannot be carried; open and re-save the project to "
                "run the identity migration."
            )

        file_exists = os.path.exists(gpkg_path)
        for lyr, canonical, fq_type, placement in mapped:
            error = self._write_layer(lyr, canonical, gpkg_path, file_exists)
            file_exists = True
            if error:
                result.errors.append(f"{lyr.name()}: {error}")
                continue
            result.layers[canonical] = lyr.featureCount()
            result.types[canonical] = (fq_type, placement)

        if not result.layers:
            return result

        timestamp = datetime.now(timezone.utc).isoformat()
        conn = None
        try:
            extensions, extras, kept_sidecar, kept_metadata = self._load_passthrough(
                passthrough)
            # Keys another tool wrote reach a *new* bundle through the project;
            # keys already in *this* file are read straight off it (above).
            existing = ic.merge_metadata(kept_metadata, existing)
            self._unresolved_cable_refs = 0
            for canonical, (fq_type, placement) in result.types.items():
                error = self._canonicalise_layer(
                    gpkg_path, canonical, fq_type, placement, index, extras)
                if error:
                    result.errors.append(error)

            conn = sqlite3.connect(gpkg_path)
            self._create_sidecar(conn, timestamp)

            relations, members, unresolved_members = self._write_relations(conn, index)
            stops, unresolved_stops = self._write_path_stops(conn, index)
            written_extensions = self._write_passthrough(conn, extensions)
            result.sidecar_rows = {
                "fq_relation": relations,
                "fq_relation_member": members,
                "fq_path_stop": stops,
                "fq_extension": written_extensions,
            }
            for table, rows in kept_sidecar.items():
                result.sidecar_rows[table] = len(rows)
            self._write_kept_sidecar(conn, kept_sidecar)
            result.inlined_extras = len(extras)
            unresolved_members += self._unresolved_cable_refs
            if unresolved_members or unresolved_stops:
                result.warnings.append(
                    f"{unresolved_members + unresolved_stops} reference(s) could not be "
                    "resolved to a fiberq_uuid and were left out rather than guessed at."
                )

            result.preserved = ic.foreign_keys(existing)
            result.metadata = self._write_metadata(conn, existing, timestamp)
            conn.commit()
        except sqlite3.Error as e:
            result.errors.append(f"Side-car and metadata write failed: {e}")
            logger.debug(f"Bundle side-car write failed for {gpkg_path}: {e}")
        finally:
            if conn is not None:
                conn.close()

        return result

    # -- the GeoJSON profile -----------------------------------------------

    def write_geojson(self, directory, layers=None, passthrough=None):
        """Write the GeoJSON profile of a bundle (spec section 3).

        One file per element type plus ``_fiberq_metadata.json``. The relational
        side-car is **not representable** in GeoJSON, so a bundle written here
        while the project holds side-car data is lossy by construction and says
        so: ``profile = "geojson-lite"``, and the caller is told how many rows
        were left behind.

        Produced by writing the GeoPackage bundle to a temporary file and
        converting it, rather than by a second export path. One canonicalisation
        means the two profiles cannot disagree about what a field is called --
        and a GeoJSON profile that quietly used the stored Serbian names while
        the GeoPackage used canonical ones would be the worst of both.
        """
        result = BundleResult(directory)
        if not directory:
            result.errors.append("No output directory given.")
            return result

        workdir = tempfile.mkdtemp(prefix="fiberq-bundle-")
        try:
            staged = self.write(
                os.path.join(workdir, "bundle.gpkg"), layers=layers,
                passthrough=passthrough)
            result.layers = staged.layers
            result.types = staged.types
            result.skipped = staged.skipped
            result.warnings = list(staged.warnings)
            result.errors = list(staged.errors)
            result.preserved = staged.preserved
            if not staged.ok:
                return result

            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as e:
                result.errors.append(f"Could not create {directory}: {e}")
                return result

            for canonical in list(result.layers):
                fq_type, placement = result.types[canonical]
                stem = f"{fq_type}.{placement}" if placement else fq_type
                error = self._write_geojson_layer(
                    staged.path, canonical, os.path.join(directory, f"{stem}.geojson"))
                if error:
                    result.errors.append(error)

            dropped = sum(staged.sidecar_rows.values())
            metadata = dict(staged.metadata)
            if dropped:
                # Only when something is actually lost. Marking a complete
                # bundle lossy is as misleading as not marking a lossy one.
                metadata["profile"] = "geojson-lite"
                result.warnings.append(
                    f"GeoJSON cannot carry the relational side-car: {dropped} row(s) "
                    "were left out. The bundle is marked profile=geojson-lite. Export "
                    "to GeoPackage for a complete bundle."
                )
            result.metadata = metadata
            try:
                with open(os.path.join(directory, "_fiberq_metadata.json"), "w",
                          encoding="utf-8") as handle:
                    json.dump(metadata, handle, indent=2, ensure_ascii=False,
                              sort_keys=True)
            except OSError as e:
                result.errors.append(f"Could not write _fiberq_metadata.json: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        return result

    def _write_geojson_layer(self, gpkg_path, table, out_path):
        """Convert one canonicalised bundle table to a GeoJSON file."""
        layer = QgsVectorLayer(f"{gpkg_path}|layername={table}", table, "ogr")
        if not layer.isValid():
            return f"could not read '{table}' back out of the staged bundle"
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GeoJSON"
        opts.fileEncoding = "UTF-8"
        # RFC 7946 is WGS84, which is already the bundle's storage CRS.
        opts.destCRS = QgsCoordinateReferenceSystem.fromEpsgId(ic.STORAGE_EPSG)
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, out_path, QgsCoordinateTransformContext(), opts)
        if isinstance(result, tuple):
            code, message = result[0], (result[1] if len(result) > 1 else "")
        else:
            code, message = result, ""
        if code != QgsVectorFileWriter.WriterError.NoError:
            return f"{table}: {message or code}"
        return None


def write_bundle(gpkg_path, project=None, layers=None, passthrough=None):
    """Convenience wrapper: write a bundle and return its :class:`BundleResult`."""
    return InterchangeBundleWriter(project=project).write(
        gpkg_path, layers=layers, passthrough=passthrough
    )


def write_geojson_bundle(directory, project=None, layers=None, passthrough=None):
    """Convenience wrapper for the GeoJSON profile."""
    return InterchangeBundleWriter(project=project).write_geojson(
        directory, layers=layers, passthrough=passthrough
    )


__all__ = [
    "BundleResult",
    "InterchangeBundleWriter",
    "read_bundle_metadata",
    "write_bundle",
    "write_geojson_bundle",
    "STAMP_COLUMNS",
]
