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
import sqlite3
from datetime import datetime, timezone

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsCoordinateTransformContext, QgsField, QgsProject, QgsVectorFileWriter,
    QgsVectorLayer,
)
from . import interchange as ic
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

    def _stamp_layer(self, gpkg_path, table, fq_type, placement):
        """Add and fill the bundle's own columns on a written feature table.

        Done through the OGR provider rather than raw SQL: a GeoPackage feature
        table carries spatial-index triggers that call GDAL-registered SQL
        functions, so a plain sqlite3 UPDATE fails on it. The side-car and
        metadata tables have no such triggers and are written directly.

        Existing values are left alone. A feature that arrived from another tool
        carrying an ``fq_type`` this plugin does not model keeps it, rather than
        being relabelled as whatever layer it was parked in -- which is the
        single most destructive thing an importer can do (spec 6.1).
        """
        layer = QgsVectorLayer(f"{gpkg_path}|layername={table}", table, "ogr")
        if not layer.isValid():
            return f"could not reopen '{table}' to stamp its type"
        provider = layer.dataProvider()

        missing = [
            _text_field(name)
            for name in STAMP_COLUMNS
            if layer.fields().indexFromName(name) < 0
        ]
        if missing and not provider.addAttributes(missing):
            return f"could not add the bundle columns to '{table}'"
        layer.updateFields()

        type_idx = layer.fields().indexFromName("fq_type")
        place_idx = layer.fields().indexFromName("placement")
        if type_idx < 0:
            return f"no fq_type column on '{table}'"

        changes = {}
        for feat in layer.getFeatures():
            attrs = {}
            if self._is_blank(feat.attribute(type_idx)):
                attrs[type_idx] = fq_type
            if placement and place_idx >= 0 and self._is_blank(feat.attribute(place_idx)):
                attrs[place_idx] = placement
            if attrs:
                changes[feat.id()] = attrs
        if changes and not provider.changeAttributeValues(changes):
            return f"could not write fq_type onto '{table}'"
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

    def _write_passthrough(self, conn, passthrough=None):
        """Write back everything a previous import could not model (spec section 8)."""
        if passthrough is None:
            raw = self.project.readEntry(*ic.PASSTHROUGH_ENTRY, "")[0]
            if not raw:
                return 0
            try:
                passthrough = json.loads(raw)
            except ValueError as e:
                logger.debug(f"Passthrough store is not valid JSON, not exported: {e}")
                return 0
        written = 0
        for row in passthrough or []:
            conn.execute(
                "INSERT OR REPLACE INTO fq_extension "
                "(uuid, owner_uuid, kind, namespace, payload_json, produced_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row.get("uuid"), row.get("owner_uuid"), row.get("kind"),
                    row.get("namespace"),
                    row.get("payload_json") if isinstance(row.get("payload_json"), str)
                    else json.dumps(row.get("payload_json")),
                    row.get("produced_by"),
                ),
            )
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
            for canonical, (fq_type, placement) in result.types.items():
                error = self._stamp_layer(gpkg_path, canonical, fq_type, placement)
                if error:
                    result.errors.append(error)

            conn = sqlite3.connect(gpkg_path)
            self._create_sidecar(conn, timestamp)

            relations, members, unresolved_members = self._write_relations(conn, index)
            stops, unresolved_stops = self._write_path_stops(conn, index)
            extensions = self._write_passthrough(conn, passthrough)
            result.sidecar_rows = {
                "fq_relation": relations,
                "fq_relation_member": members,
                "fq_path_stop": stops,
                "fq_extension": extensions,
            }
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


def write_bundle(gpkg_path, project=None, layers=None, passthrough=None):
    """Convenience wrapper: write a bundle and return its :class:`BundleResult`."""
    return InterchangeBundleWriter(project=project).write(
        gpkg_path, layers=layers, passthrough=passthrough
    )


__all__ = [
    "BundleResult",
    "InterchangeBundleWriter",
    "read_bundle_metadata",
    "write_bundle",
    "STAMP_COLUMNS",
]
