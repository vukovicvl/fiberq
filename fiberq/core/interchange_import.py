"""FiberQ interchange bundle reader — WP3 task 3.3.

The other direction of ``interchange_bundle``: reads a conformant bundle into a
QGIS project, as specified in ``docs/interchange-format.md``.

**It does not change the plugin's data model.** Features land in FiberQ's own
layers, with FiberQ's own field names and values, restored through the published
mapping. A bundle from another tool is *adapted into* FiberQ, not bolted beside
it.

The whole difficulty is rule 1 -- preserve, don't discard -- because this is the
side where discarding is tempting. Four cases, and only the first is easy:

* **A type the plugin has.** Mapped into its layer normally.
* **A type the plugin lacks** (a splitter, a patch cable, a micro duct). The
  feature is kept whole in the passthrough store and written out again
  unchanged. It is *never* reclassified to the nearest familiar type: a
  micro duct arriving as a pole cannot be turned back afterwards, and the
  import would look like it worked.
* **An attribute with no column here.** Kept against the feature's identity and
  re-emitted into its ``fq_extra_json`` on the way out.
* **A side-car table the plugin does not model** -- fibre splices, trays, duct
  occupancy. Kept verbatim, written back into the real table on export, so the
  data is still relational when it reaches a tool that does model it.

When the plugin later gains a real layer for something it passes through today,
the mapping is upgraded and those objects start importing properly. **Older
bundles still work**, because nothing was ever thrown away.
"""
import json
import os
import re
import sqlite3

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsField,
    QgsGeometry, QgsProject, QgsVectorLayer,
)

from . import interchange as ic
from . import interchange_fields as fm
from .interchange_bundle import read_bundle_metadata
from ..models import schema as fq_schema
from ..utils.logger import get_logger
from ..utils.uuid_utils import FIBERQ_UUID_FIELD

logger = get_logger(__name__)

#: A GeoPackage table name this reader is willing to interpolate into SQL.
#: Table names cannot be bound as parameters, and a bundle is a file from
#: somewhere else -- so the name is validated against this before it reaches a
#: query, rather than trusted because it came out of ``gpkg_contents``.
_SAFE_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .\-]{0,62}$")


def _safe_table(name):
    """Return ``name`` if it is a table name safe to quote into SQL, else ``None``."""
    return name if name and _SAFE_TABLE_NAME.match(str(name)) else None


#: Columns a bundle adds that are not part of any FiberQ layer.
BUNDLE_COLUMNS = frozenset({"fq_type", "placement", "fq_extra_json", "fid"})

#: Logical schema type -> the QVariant/QMetaType name used to build the field.
_QT_TYPE_NAMES = {
    "text": "QString", "enum": "QString", "int": "Int", "year": "Int",
    "double": "Double", "bool": "Bool",
}


def _field(name, logical_type="text"):
    """Build a :class:`QgsField`, with the constructor this QGIS accepts.

    QGIS 3.38 deprecated the ``QVariant``-typed constructor; QGIS 3.22 LTR, which
    this plugin still targets, only has that one.
    """
    qt_name = _QT_TYPE_NAMES.get(logical_type, "QString")
    try:
        from qgis.PyQt.QtCore import QMetaType
        return QgsField(name, getattr(QMetaType.Type, qt_name))
    except (ImportError, AttributeError, TypeError):
        from qgis.PyQt.QtCore import QVariant
        legacy = {"QString": "String", "Int": "Int", "Double": "Double", "Bool": "Bool"}
        return QgsField(name, getattr(QVariant, legacy[qt_name]))


class ImportResult:
    """What an import actually did, in enough detail to assert on."""

    def __init__(self, path=""):
        self.path = path
        self.layers = {}            # canonical layer name -> features added
        self.created = []           # layers this import had to create
        self.unsupported = {}       # fq_type -> features kept in passthrough
        self.extra_attributes = 0   # features carrying attributes with no column
        self.sidecar_kept = {}      # side-car table -> rows kept in passthrough
        self.already_present = 0    # features whose identity was already in the project
        self.relations = 0
        self.path_stops = 0
        self.passthrough = 0        # total rows in the store after the import
        self.metadata = {}
        self.foreign_metadata = {}  # keys another tool wrote, kept for the next bundle
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
        carried = sum(self.unsupported.values())
        if carried:
            parts.append(f"{carried} unsupported element(s) carried through")
        if self.extra_attributes:
            parts.append(f"{self.extra_attributes} feature(s) with extra attributes kept")
        if self.sidecar_kept:
            rows = sum(self.sidecar_kept.values())
            parts.append(f"{rows} side-car row(s) kept")
        return ", ".join(parts)


class InterchangeBundleReader:
    """Reads a FiberQ interchange bundle into a QGIS project."""

    def __init__(self, project=None):
        self.project = project or QgsProject.instance()

    # -- bundle inspection -------------------------------------------------

    @staticmethod
    def _feature_tables(gpkg_path):
        """The bundle's feature layers, from the GeoPackage's own contents table."""
        with sqlite3.connect(gpkg_path) as conn:
            names = [
                row[0] for row in conn.execute(
                    "SELECT table_name FROM gpkg_contents WHERE data_type = 'features' "
                    "ORDER BY table_name")
            ]
        return [name for name in names if _safe_table(name)]

    @staticmethod
    def _table_rows(gpkg_path, table):
        """Every row of a side-car table as dicts, or ``[]`` if it is not there."""
        if _safe_table(table) is None:
            return []
        with sqlite3.connect(gpkg_path) as conn:
            present = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)).fetchone()
            if present is None:
                return []
            # Table names cannot be bound as parameters; the name is validated
            # by _safe_table above and exists in sqlite_master.
            cursor = conn.execute(f'SELECT * FROM "{table}"')  # nosec B608
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # -- target layers -----------------------------------------------------

    def _find_layer(self, canonical):
        """An existing layer in the project for this canonical name, or ``None``."""
        for layer in self.project.mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            if fq_schema.canonical_layer_name(layer.name()) == canonical:
                return layer
        return None

    def _ensure_layer(self, canonical, result):
        """The project's layer for a canonical name, created from the schema if absent.

        Built from ``models/schema.py`` rather than duplicated here, so an
        imported layer has exactly the fields FiberQ would have made itself.
        """
        existing = self._find_layer(canonical)
        if existing is not None:
            return existing

        layer_schema = fq_schema.get_layer_schema(canonical)
        if layer_schema is None:
            result.errors.append(f"No FiberQ schema for layer '{canonical}'.")
            return None

        crs = self.project.crs()
        authid = crs.authid() if crs.isValid() else "EPSG:3857"
        layer = QgsVectorLayer(
            f"{layer_schema.geometry}?crs={authid}", canonical, "memory")
        if not layer.isValid():
            result.errors.append(f"Could not create layer '{canonical}'.")
            return None

        provider = layer.dataProvider()
        provider.addAttributes([
            _field(f.key, f.field_type) for f in layer_schema.fields
        ])
        layer.updateFields()
        self.project.addMapLayer(layer)
        result.created.append(canonical)
        return layer

    # -- feature import ----------------------------------------------------

    def _restore_attributes(self, roster, bundle_feature, target_fields):
        """Bundle attributes -> FiberQ's stored names and values.

        Returns ``(attributes, extras)``. *extras* holds canonical fields this
        plugin has no column for; they are kept against the feature's identity
        rather than dropped.
        """
        attributes = {}
        extras = {}
        for field in bundle_feature.fields():
            name = field.name()
            if name in BUNDLE_COLUMNS:
                continue
            value = bundle_feature.attribute(name)
            if name == FIBERQ_UUID_FIELD:
                attributes[FIBERQ_UUID_FIELD] = value
                continue
            if name == fm.CABLE_REFERENCE_FIELD:
                # Resolved to the project-local pair in a second pass, once
                # every feature exists and has somewhere to point.
                continue
            stored = fm.stored_field(roster, name) if roster else None
            if stored is None or target_fields.indexFromName(stored) < 0:
                if value is not None and str(value) != "":
                    extras[name] = value
                continue
            attributes[stored] = fm.stored_value(roster, name, value)
        return attributes, extras

    def _import_feature(self, bundle_feature, target, roster, transform):
        """Copy one bundle feature into a FiberQ layer."""
        feature = QgsFeature(target.fields())
        geometry = QgsGeometry(bundle_feature.geometry())
        if transform is not None and not geometry.isNull():
            try:
                geometry.transform(transform)
            except Exception as e:
                logger.debug(f"Could not reproject an imported feature: {e}")
        feature.setGeometry(geometry)

        attributes, extras = self._restore_attributes(
            roster, bundle_feature, target.fields())
        for name, value in attributes.items():
            index = target.fields().indexFromName(name)
            if index >= 0:
                feature.setAttribute(index, value)
        return feature, extras

    # -- the whole thing ---------------------------------------------------

    def read(self, gpkg_path):
        """Import a bundle into the project and report exactly what happened."""
        result = ImportResult(gpkg_path)
        if not gpkg_path or not os.path.isfile(gpkg_path):
            result.errors.append(f"No bundle at {gpkg_path}.")
            return result

        metadata = read_bundle_metadata(gpkg_path)
        result.metadata = metadata
        if metadata.get("format") != ic.FORMAT:
            result.errors.append(
                "This is not a FiberQ interchange bundle: its metadata does not "
                f"declare format '{ic.FORMAT}'. Open it as ordinary layers instead."
            )
            return result
        declared = metadata.get("format_version", "")
        if not ic.can_read_format_version(declared):
            # Spec section 9: refuse rather than import a bundle partially.
            result.errors.append(
                f"This bundle declares interchange format {declared or 'an unknown version'}; "
                f"this plugin implements {ic.FORMAT_VERSION}. Importing it partially "
                "would silently drop whatever the newer version added, so it is "
                "refused. Update FiberQ to read it."
            )
            return result

        self._restore_project_crs(metadata, result)

        storage_crs = QgsCoordinateReferenceSystem.fromEpsgId(ic.STORAGE_EPSG)
        passthrough = self._load_passthrough()
        uuid_index = {}

        for table in self._feature_tables(gpkg_path):
            self._import_table(
                gpkg_path, table, storage_crs, passthrough, uuid_index, result)

        self._restore_cable_references(gpkg_path, uuid_index, result)
        self._restore_relations(gpkg_path, uuid_index, result)
        self._restore_path_stops(gpkg_path, uuid_index, result)
        self._keep_unmodelled_sidecar(gpkg_path, passthrough, result)
        self._keep_foreign_metadata(metadata, passthrough, result)

        result.passthrough = self._save_passthrough(passthrough)
        return result

    def _restore_project_crs(self, metadata, result):
        """Put the design back in the CRS it was authored in (spec section 5).

        A project that already holds vector layers keeps its own CRS: an import
        adds to somebody's work and does not get to reproject it. An empty
        project has no such claim -- its CRS is a QGIS default nobody chose, and
        honouring it lands the whole design in a geographic CRS, which FiberQ's
        own validation rule E1 objects to for good reason.
        """
        if self.project.crs().isValid() and self._holds_vector_layers():
            return
        epsg = (metadata.get("crs_epsg") or "").strip()
        if not epsg:
            return
        crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg}")
        if crs.isValid():
            self.project.setCrs(crs)
        else:
            result.warnings.append(
                f"The bundle names EPSG:{epsg} as its authoring CRS, which this "
                "QGIS does not recognise. Set the project CRS yourself.")

    def _holds_vector_layers(self):
        """Does this project already contain work of its own?"""
        return any(isinstance(layer, QgsVectorLayer)
                   for layer in self.project.mapLayers().values())

    def _import_table(self, gpkg_path, table, storage_crs, passthrough,
                      uuid_index, result):
        """Import one bundle feature table, splitting it by element type.

        Grouped per feature, not per table: a bundle may legitimately carry more
        than one type in a table, and passthrough features certainly do.
        """
        source = QgsVectorLayer(f"{gpkg_path}|layername={table}", table, "ogr")
        if not source.isValid():
            result.errors.append(f"Could not read bundle layer '{table}'.")
            return

        by_target = {}
        for feature in source.getFeatures():
            fq_type = self._text(feature, "fq_type")
            placement = self._text(feature, "placement") or None
            canonical = ic.layer_for_type(fq_type, placement) if fq_type else None
            if canonical is None:
                self._keep_unsupported(feature, fq_type, placement, passthrough, result)
                continue
            by_target.setdefault(canonical, []).append(feature)

        for canonical, features in by_target.items():
            target = self._ensure_layer(canonical, result)
            if target is None:
                continue
            fq_type, _placement = ic.type_for_layer(canonical)
            roster = fm.roster_for_type(fq_type)
            transform = None
            if target.crs().isValid() and target.crs() != storage_crs:
                transform = QgsCoordinateTransform(
                    storage_crs, target.crs(), self.project)

            # Identity is permanent (spec section 4), so a feature whose uuid is
            # already in the layer is the *same* feature, not a second one.
            # Adding it again would put a duplicate identity in the project --
            # which validation rule B4 reports as an error, correctly.
            present = self._existing_identities(target)
            # Index what the project already holds, not only what this import
            # adds. Without it a second import resolves nothing, and the
            # restores below rewrite the project's relations and path stops as
            # empty -- an import that quietly demolishes what the first one
            # put back.
            for identity, fid in present.items():
                uuid_index.setdefault(identity, (target.id(), fid))
            pending = []
            extras_by_uuid = {}
            for feature in features:
                identity = self._text(feature, FIBERQ_UUID_FIELD)
                if identity and identity in present:
                    result.already_present += 1
                    continue
                built, extras = self._import_feature(
                    feature, target, roster, transform)
                pending.append(built)
                if extras and identity:
                    extras_by_uuid[identity] = extras
                self._absorb_extra_json(feature, identity, extras_by_uuid)

            ok, added = self._add_features(target, pending)
            if not ok:
                result.errors.append(f"Could not add features to '{canonical}'.")
                continue
            result.layers[canonical] = result.layers.get(canonical, 0) + len(added)
            for feature in added:
                identity = feature.attribute(FIBERQ_UUID_FIELD)
                if identity:
                    uuid_index[str(identity)] = (target.id(), int(feature.id()))

            for identity, extras in extras_by_uuid.items():
                passthrough.append({
                    "uuid": ic.stable_uuid("extras", identity),
                    "owner_uuid": identity,
                    "kind": ic.EXTENSION_KIND_ATTRIBUTES,
                    "namespace": ic.EXTENSION_NAMESPACE,
                    "payload_json": json.dumps(extras, ensure_ascii=False, sort_keys=True),
                    "produced_by": self._producer(result),
                })
                result.extra_attributes += 1

    @staticmethod
    def _absorb_extra_json(feature, identity, extras_by_uuid):
        """Merge a feature's own ``fq_extra_json`` into what we keep for it.

        A bundle that already carried extras for this feature -- because some
        other tool could not model them either -- must not lose them here.
        """
        if not identity or feature.fields().indexFromName("fq_extra_json") < 0:
            return
        raw = feature.attribute("fq_extra_json")
        if raw is None or not str(raw).strip():
            return
        try:
            carried = json.loads(str(raw))
        except ValueError as e:
            logger.debug(f"fq_extra_json on {identity} is not valid JSON: {e}")
            return
        if isinstance(carried, dict):
            merged = dict(carried)
            merged.update(extras_by_uuid.get(identity, {}))
            extras_by_uuid[identity] = merged

    def _keep_unsupported(self, feature, fq_type, placement, passthrough, result):
        """Keep a whole feature this plugin has no layer for (spec section 8).

        Never reclassified to the nearest familiar type: that is irreversible,
        and the import would look like it worked.
        """
        identity = self._text(feature, FIBERQ_UUID_FIELD)
        attributes = {}
        for field in feature.fields():
            name = field.name()
            if name in ("fid",):
                continue
            value = feature.attribute(name)
            if value is None:
                continue
            attributes[name] = value if isinstance(
                value, (str, int, float, bool)) else str(value)
        geometry = feature.geometry()
        payload = {
            "fq_type": fq_type,
            "placement": placement,
            "geometry_wkt": "" if geometry.isNull() else geometry.asWkt(),
            "attributes": attributes,
        }
        passthrough.append({
            "uuid": ic.stable_uuid("feature", identity or repr(sorted(attributes.items()))),
            "owner_uuid": identity,
            "kind": ic.EXTENSION_KIND_FEATURE,
            "namespace": ic.EXTENSION_NAMESPACE,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "produced_by": self._producer(result),
        })
        key = fq_type or "(no fq_type)"
        result.unsupported[key] = result.unsupported.get(key, 0) + 1

    # -- side-car ----------------------------------------------------------

    def _restore_cable_references(self, gpkg_path, uuid_index, result):
        """Point slack loops and fibre breaks back at their cable.

        The bundle carries ``cable_uuid``; the plugin wants the local
        ``(cable_layer_id, cable_fid)`` pair. Done after every feature exists,
        because before that there is nothing to point at.
        """
        for canonical in ("Optical slack", "Fiber break"):
            layer = self._find_layer(canonical)
            if layer is None:
                continue
            layer_idx = layer.fields().indexFromName("cable_layer_id")
            fid_idx = layer.fields().indexFromName("cable_fid")
            uuid_idx = layer.fields().indexFromName(FIBERQ_UUID_FIELD)
            if min(layer_idx, fid_idx, uuid_idx) < 0:
                continue
            wanted = self._bundle_cable_uuids(gpkg_path, canonical)
            if not wanted:
                continue
            changes = {}
            unresolved = 0
            for feature in layer.getFeatures():
                identity = feature.attribute(uuid_idx)
                cable_uuid = wanted.get(str(identity)) if identity else None
                if not cable_uuid:
                    continue
                target = uuid_index.get(str(cable_uuid))
                if target is None:
                    unresolved += 1
                    continue
                changes[feature.id()] = {layer_idx: target[0], fid_idx: target[1]}
            if changes:
                layer.dataProvider().changeAttributeValues(changes)
            if unresolved:
                result.warnings.append(
                    f"{unresolved} {canonical} reference(s) name a cable that is not "
                    "in this bundle; they were left empty rather than pointed at "
                    "another cable.")

    def _bundle_cable_uuids(self, gpkg_path, table):
        """``feature uuid -> cable_uuid`` as recorded in the bundle."""
        if _safe_table(table) is None:
            return {}
        with sqlite3.connect(gpkg_path) as conn:
            present = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)).fetchone()
            if present is None:
                return {}
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
            if not {FIBERQ_UUID_FIELD, fm.CABLE_REFERENCE_FIELD} <= columns:
                return {}
            # Both column names are module constants; the table name is
            # validated by _safe_table above and exists in sqlite_master.
            sql = f'SELECT {FIBERQ_UUID_FIELD}, {fm.CABLE_REFERENCE_FIELD} FROM "{table}"'  # nosec B608
            return {
                str(identity): cable
                for identity, cable in conn.execute(sql)
                if identity and cable
            }

    def _restore_relations(self, gpkg_path, uuid_index, result):
        """Rebuild the project's relations from the uuid-keyed side-car."""
        relations = self._table_rows(gpkg_path, "fq_relation")
        if not relations:
            return
        members = {}
        for row in self._table_rows(gpkg_path, "fq_relation_member"):
            members.setdefault(row.get("relation_uuid"), []).append(row)

        out = []
        unresolved = 0
        for index, relation in enumerate(relations, start=1):
            cables = []
            for member in sorted(members.get(relation.get("uuid"), []),
                                 key=lambda m: m.get("order_index") or 0):
                target = uuid_index.get(str(member.get("member_uuid")))
                if target is None:
                    unresolved += 1
                    continue
                cables.append({"layer_id": target[0], "fid": target[1]})
            out.append({
                "id": index,
                "name": relation.get("name") or f"Relation {index}",
                "cables": cables,
            })
        self.project.writeEntry(
            "StuboviPlugin", "Relacije/relations_v1",
            json.dumps({"relations": out}, ensure_ascii=False))
        result.relations = len(out)
        if unresolved:
            result.warnings.append(
                f"{unresolved} relation member(s) name a feature that is not in this "
                "bundle and were left out.")

    def _restore_path_stops(self, gpkg_path, uuid_index, result):
        """Rebuild the recorded pass-through elements from ``fq_path_stop``."""
        stops = self._table_rows(gpkg_path, "fq_path_stop")
        if not stops:
            return
        cables = {}
        unresolved = 0
        for row in sorted(stops, key=lambda r: r.get("order_index") or 0):
            cable = uuid_index.get(str(row.get("cable_uuid")))
            element = uuid_index.get(str(row.get("element_uuid")))
            if cable is None or element is None:
                unresolved += 1
                continue
            key = f"{cable[0]}:{cable[1]}"
            entries = cables.setdefault(key, [])
            entries.append({
                "layer_id": element[0],
                "fid": element[1],
                # order_index is the traversal order; 'm' is what the plugin
                # sorts on, and the real distance is recoverable from geometry.
                "m": float(row.get("order_index") or len(entries)),
            })
            result.path_stops += 1
        self.project.writeEntry(
            "StuboviPlugin", "LatentElements/latent_v1",
            json.dumps({"cables": cables}, ensure_ascii=False))
        if unresolved:
            result.warnings.append(
                f"{unresolved} path stop(s) name a feature that is not in this bundle "
                "and were left out.")

    def _keep_unmodelled_sidecar(self, gpkg_path, passthrough, result):
        """Keep the side-car tables this plugin has no model for, verbatim.

        Fibre splices, trays and duct occupancy are exactly the data the format
        exists to carry and the plugin does not yet hold. Kept whole and written
        back into the real table on export, so it is still relational when it
        reaches a tool that does model it.
        """
        for table in ic.SIDECAR_TABLES:
            if table in ic.MODELLED_SIDECAR_TABLES or table == "fq_extension":
                continue
            rows = self._table_rows(gpkg_path, table)
            if not rows:
                continue
            passthrough.append({
                "uuid": ic.stable_uuid("sidecar", table),
                "owner_uuid": None,
                "kind": ic.EXTENSION_KIND_SIDECAR,
                "namespace": ic.EXTENSION_NAMESPACE,
                "payload_json": json.dumps(
                    {"table": table, "rows": rows}, ensure_ascii=False, sort_keys=True),
                "produced_by": self._producer(result),
            })
            result.sidecar_kept[table] = len(rows)

        # Whatever the bundle itself was already carrying for other tools.
        for row in self._table_rows(gpkg_path, "fq_extension"):
            passthrough.append({
                "uuid": row.get("uuid"),
                "owner_uuid": row.get("owner_uuid"),
                "kind": row.get("kind"),
                "namespace": row.get("namespace"),
                "payload_json": row.get("payload_json"),
                "produced_by": row.get("produced_by"),
            })

    def _keep_foreign_metadata(self, metadata, passthrough, result):
        """Keep the metadata keys another tool wrote, so the next bundle has them.

        Merging them back into the same file is spec section 7. Carrying them
        into a *different* file -- which is what a round trip through this plugin
        produces -- needs somewhere to hold them in between, and the project is
        the only place there is.
        """
        foreign = ic.foreign_keys(metadata)
        if not foreign:
            return
        passthrough.append({
            "uuid": ic.stable_uuid("metadata", *sorted(foreign)),
            "owner_uuid": None,
            "kind": ic.EXTENSION_KIND_METADATA,
            "namespace": ic.EXTENSION_NAMESPACE,
            "payload_json": json.dumps(foreign, ensure_ascii=False, sort_keys=True),
            "produced_by": self._producer(result),
        })
        result.foreign_metadata = dict(foreign)

    # -- passthrough store -------------------------------------------------

    def _load_passthrough(self):
        raw = self.project.readEntry(*ic.PASSTHROUGH_ENTRY, "")[0]
        if not raw:
            return []
        try:
            stored = json.loads(raw)
        except ValueError as e:
            logger.debug(f"Passthrough store is not valid JSON, starting fresh: {e}")
            return []
        return stored if isinstance(stored, list) else []

    def _save_passthrough(self, rows):
        """Write the store back, de-duplicated by uuid, and return its size.

        Importing the same bundle twice must not make the store grow. The row
        uuids are derived deterministically from what they describe, so the
        second import overwrites the first rather than stacking beside it.
        """
        seen = {}
        for row in rows:
            seen[row.get("uuid") or repr(sorted(row.items()))] = row
        self.project.writeEntry(
            *ic.PASSTHROUGH_ENTRY,
            json.dumps(list(seen.values()), ensure_ascii=False))
        return len(seen)

    # -- small helpers -----------------------------------------------------

    @staticmethod
    def _producer(result):
        return result.metadata.get("produced_by") or "unknown"

    @staticmethod
    def _existing_identities(layer):
        """``fiberq_uuid -> fid`` for what this layer already holds.

        The fids matter as much as the identities. A feature that is already in
        the project is still a legitimate target for a relation, a path stop or
        a cable reference carried by the bundle being imported, and the restores
        below can only reach it through this index.
        """
        index = layer.fields().indexFromName(FIBERQ_UUID_FIELD)
        if index < 0:
            return {}
        found = {}
        for feature in layer.getFeatures():
            value = feature.attribute(index)
            if value is not None and str(value).strip():
                found[str(value).strip()] = int(feature.id())
        return found

    @staticmethod
    def _text(feature, name):
        if feature.fields().indexFromName(name) < 0:
            return ""
        value = feature.attribute(name)
        if value is None:
            return ""
        if hasattr(value, "isNull") and value.isNull():
            return ""
        return str(value).strip()

    @staticmethod
    def _add_features(layer, features):
        outcome = layer.dataProvider().addFeatures(features)
        if isinstance(outcome, tuple):
            ok, added = outcome
            return ok, added
        return outcome, features


def read_bundle(gpkg_path, project=None):
    """Convenience wrapper: import a bundle and return its :class:`ImportResult`."""
    return InterchangeBundleReader(project=project).read(gpkg_path)


__all__ = ["ImportResult", "InterchangeBundleReader", "read_bundle"]
