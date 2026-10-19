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
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsCoordinateTransformContext, QgsFeature, QgsFeatureRequest, QgsField,
    QgsFields, QgsGeometry, QgsMemoryProviderUtils, QgsProject,
    QgsProviderConnectionException, QgsProviderRegistry, QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from . import interchange as ic
from . import interchange_fields as fm
from ..i18n import safe_format
from ..models.schema import SCHEMA_VERSION, canonical_layer_name
from ..utils.geometry import transformed
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


def _quoted(identifier):
    """An SQL identifier in double quotes, with any quote inside doubled."""
    return '"' + str(identifier).replace('"', '""') + '"'


def _parsed(text):
    """JSON text as the value it encodes, or the text itself when it is not JSON."""
    try:
        return json.loads(text)
    except ValueError:
        return text


#: Declared types FiberQ re-creates a carried column with. Anything else maps to
#: the type with the same SQLite affinity: a type is SQL text from someone else's
#: file, and one such as ``TEXT NOT NULL`` or ``x); DROP ...`` must never be
#: written back verbatim.
_SAFE_TYPE = re.compile(
    r"^(BOOLEAN|TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT|FLOAT|DOUBLE|REAL|NUMERIC|"
    r"DECIMAL|DATE|DATETIME|TEXT|VARCHAR|CHAR|CLOB|BLOB)(\(\d{1,9}(,\d{1,9})?\))?$",
    re.IGNORECASE)
_UNKNOWN_TABLE = re.compile(r"^fq_[A-Za-z0-9_]{1,60}$")


def _column_type(declared):
    """A declared type safe to write into DDL, keeping its SQLite affinity."""
    text = str(declared or "").strip()
    if not text or _SAFE_TYPE.match(text):
        return text.upper()
    upper = text.upper()
    if "INT" in upper:
        return "INTEGER"
    if any(word in upper for word in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in upper:
        return "BLOB"
    if any(word in upper for word in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def _identifier_ok(name):
    text = str(name)
    return bool(text) and len(text) <= 128 and all(ord(ch) >= 32 for ch in text)


def _ensure_columns(conn, table, wanted):
    """Add every wanted ``[name, declared type]`` column ``table`` lacks; answer its columns.

    Compared regardless of case, as SQLite compares column names, and through
    ``table_xinfo`` so a generated column counts as present. A name with a
    control character is not added.
    """
    def present():
        try:
            info = list(conn.execute(f'PRAGMA table_xinfo("{table}")'))  # nosec B608
        except sqlite3.Error:
            info = list(conn.execute(f'PRAGMA table_info("{table}")'))  # nosec B608
        return [r[1] for r in info]

    have = present()
    folded = {c.lower() for c in have}
    for column in wanted:
        name = column[0] if isinstance(column, (list, tuple)) else column
        declared = column[1] if isinstance(column, (list, tuple)) and len(column) > 1 else ""
        if not _identifier_ok(name) or str(name).lower() in folded:
            continue
        # The table is validated, the name quoted, the type from _column_type.
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN {_quoted(name)} {_column_type(declared)}')  # nosec B608
        folded.add(str(name).lower())
    return [c for c in present()]


def _create_carried_table(conn, table, recorded, rows):
    """Re-create a side-car table this format version does not define.

    From the columns the import recorded -- names quoted, types through
    _column_type, and the primary key it had, so a later export over the same
    file replaces its rows instead of doubling them. Registered as an
    attributes table so GDAL lists it, unless the name is already registered.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND lower(name)=lower(?)",
        (table,)).fetchone()
    if exists is None:
        columns = [c for c in recorded if isinstance(c, (list, tuple)) and _identifier_ok(c[0])]
        if not columns:
            names = []
            for row in rows:
                names += [k for k in row if k not in names]
            columns = [[name, "", 0] for name in names if _identifier_ok(name)]
        keys = [c[0] for c in sorted(columns, key=lambda c: c[2] if len(c) > 2 else 0)
                if len(c) > 2 and c[2]]
        parts = [f"{_quoted(c[0])} {_column_type(c[1] if len(c) > 1 else '')}".rstrip()
                 for c in columns]
        if keys:
            parts.append("PRIMARY KEY (" + ", ".join(_quoted(k) for k in keys) + ")")
        # Validated table name (fq_ and word characters), quoted columns.
        conn.execute(f'CREATE TABLE "{table}" ({", ".join(parts)})')  # nosec B608
    conn.execute(
        "INSERT OR IGNORE INTO gpkg_contents "
        "(table_name, data_type, identifier, description, last_change, srs_id) "
        "VALUES (?, 'attributes', ?, ?, ?, 0)",
        (table, table, f"Side-car table {table}, carried by FiberQ",
         datetime.now(timezone.utc).isoformat()))


def _unknown_table(name):
    """``name`` as a carried ``fq_*`` table this format version does not define, or None."""
    text = str(name or "")
    return text if _UNKNOWN_TABLE.match(text) and _sidecar_table(text) is None else None


def _sidecar_table(name):
    """``name`` as one of the format's side-car tables, regardless of case, or None."""
    folded = str(name or "").lower()
    return next((table for table in ic.SIDECAR_TABLES if table == folded), None)


def _united(before, columns):
    """Recorded ``[name, type, pk]`` column lists, one entry per name regardless of case."""
    united, seen = [], set()
    for column in list(before or []) + list(columns or []):
        if isinstance(column, (list, tuple)) and column and str(column[0]).lower() not in seen:
            seen.add(str(column[0]).lower())
            united.append(list(column))
    return united


def _extra_columns(conn, table, defined, extras):
    """``defined`` plus every column the records' ``extra`` names, added to ``table``.

    The extras are what an import kept of a column a later 1.x version added to
    a modelled table (``fq_relation``, ``fq_relation_member``).
    """
    names = []
    for extra in extras:
        for name in (extra or {}):
            if str(name).lower() not in {d.lower() for d in defined} and name not in names:
                names.append(name)
    if names:
        present = {c.lower() for c in _ensure_columns(conn, table, [[n, ""] for n in names])}
        names = [n for n in names if n.lower() in present]
    return list(defined) + names


def _insert_sql(table, columns):
    # The format's own table; every column name is quoted.
    return (f'INSERT OR REPLACE INTO "{table}" ({", ".join(_quoted(c) for c in columns)}) '  # nosec B608
            f'VALUES ({", ".join("?" for _ in columns)})')


def _with_extra(values, record, extra_columns):
    extra = (record or {}).get("extra") or {}
    return list(values) + [ic.from_json_safe(extra.get(c)) for c in extra_columns]


#: The lists FiberQ's record of a write holds; each is a list of names or uuids.
_RECORD_LISTS = ("fq_relation", "fq_path_stop", "features", "files")


def _previously_written(file_metadata):
    """What FiberQ's last export wrote in this file: relation and cable uuids, tables, files.

    Only while the record's ``produced_at`` is the file's own: another tool that
    copied the key into a different file, as section 7 asks, does not make it
    true there. A malformed record -- not JSON, not an object, or a list of
    anything but names -- is ignored rather than trusted; a list of lists used
    to raise mid-export, after the feature tables were written, on every export
    over that file.
    """
    raw = (file_metadata or {}).get(ic.WRITTEN_KEY)
    if not raw:
        return {}
    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        logger.debug("FiberQ's record of written rows is not valid JSON; nothing removed")
        return {}
    if not isinstance(record, dict) or record.get("produced_at") != file_metadata.get("produced_at"):
        return {}
    for key in _RECORD_LISTS:
        value = record.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            logger.debug(f"FiberQ's record of written rows has a malformed {key}; nothing removed")
            return {}
    return record


def _old_tables_removed(gpkg_path, previous, current):
    """Drop the feature tables FiberQ wrote here last time that this export did not.

    Returns ``(removed, failed)``. Only a table the record names, and only one
    that is still a feature table of the file, is dropped; through QGIS's own
    GeoPackage connection, which takes the spatial index and the registration
    with it.
    """
    stale = sorted(set(previous.get("features") or []) - set(current))
    if not stale:
        return [], []
    try:
        with closing(sqlite3.connect(gpkg_path)) as conn:
            present = {str(name).lower(): name for (name,) in conn.execute(
                "SELECT table_name FROM gpkg_contents "
                "WHERE data_type IN ('features', 'attributes')")}
    except (sqlite3.Error, sqlite3.Warning) as e:
        return [], [f"{', '.join(stale)} ({e})"]
    removed, failed = [], []
    for table in stale:
        name = present.get(str(table).lower())
        if name is None:
            continue
        try:
            connection = QgsProviderRegistry.instance().providerMetadata("ogr").createConnection(
                gpkg_path, {})
            connection.dropVectorTable("", name)
        except QgsProviderConnectionException as e:
            failed.append(f"{name} ({e})")
        else:
            removed.append(name)
    return removed, failed


def _geojson_name(name):
    """True for a bare ``*.geojson`` file name: never a path, so never outside the folder."""
    text = str(name or "")
    if not text.endswith(".geojson") or text.startswith("."):
        return False
    if any(ch in text for ch in "/\\\0:"):
        return False
    return os.path.basename(text) == text


def _old_files_removed(directory, previous, current):
    """Delete the GeoJSON files FiberQ wrote in this folder last time that this export did not."""
    removed, failed = [], []
    for name in sorted(set(previous.get("files") or []) - set(current)):
        path = os.path.join(directory, str(name))
        if not _geojson_name(name) or not os.path.isfile(path):
            continue
        try:
            os.remove(path)
        except OSError as e:
            failed.append(f"{name} ({e})")
        else:
            removed.append(name)
    return removed, failed


def _forget(conn, previous, relations_now, cables_now):
    """Remove the rows FiberQ wrote here last time for what the project no longer has."""
    for relation in set(previous.get("fq_relation") or []) - set(relations_now):
        conn.execute("DELETE FROM fq_relation_member WHERE relation_uuid = ?", (relation,))
        conn.execute("DELETE FROM fq_relation WHERE uuid = ?", (relation,))
    for cable in set(previous.get("fq_path_stop") or []) - set(cables_now):
        conn.execute("DELETE FROM fq_path_stop WHERE cable_uuid = ?", (cable,))


def _json_object(value):
    """``value`` -- a dict, JSON text or blank -- as a dict, or ``None`` if it is not one."""
    if isinstance(value, dict):
        return value
    if value is None or (hasattr(value, "isNull") and value.isNull()) or not str(value).strip():
        return {}
    parsed = _parsed(str(value))
    return parsed if isinstance(parsed, dict) else None


def _order(record, position):
    """A row's own ``order_index`` when an import recorded one, else its position."""
    try:
        return int(record["order_index"])
    except (KeyError, TypeError, ValueError):
        return position


def _stored_index(source_fields, stored):
    """Index of a stored field, under its modern name or a pre-1.0 one.

    A project made before the English field rename still calls the cable
    reference ``kabl_layer_id`` / ``kabl_fid``. Looking only for the modern
    name does not merely miss a column -- it misses the *structural* pair, so
    no ``cable_uuid`` is written and the slack loop reaches the next tool
    detached from its cable, carrying a layer id from a project that no longer
    exists.
    """
    index = source_fields.indexFromName(stored)
    if index >= 0:
        return index
    for legacy in fm.legacy_names(stored):
        index = source_fields.indexFromName(legacy)
        if index >= 0:
            return index
    return -1


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
        self._unreprojectable = 0
        self._uncarried = 0
        self._carried_columns = []
        self._unreadable_entries = []
        self._unavailable = []

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
        caller can show the user. A layer passed twice is one layer.
        """
        if layers is None:
            layers = [
                lyr for lyr in self.project.mapLayers().values()
                if isinstance(lyr, QgsVectorLayer)
            ]
        mapped, skipped = [], []
        seen = set()
        self._unavailable = []
        for lyr in layers:
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                name = getattr(lyr, "name", lambda: "?")()
                skipped.append((name, "not a valid vector layer"))
                if isinstance(lyr, QgsVectorLayer) and canonical_layer_name(name):
                    self._unavailable.append(name)
                continue
            if lyr.id() in seen:
                continue
            seen.add(lyr.id())
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

    def _placeable(self, mapped, result):
        """The mapped layers whose coordinates can be put in the storage CRS.

        Unclaimed (WP3 code, found in the v1.6.0 review). A layer with no valid
        CRS, or with one no transformation leads from to EPSG:4326 -- an
        engineering CRS, say -- was written as it stood: its coordinates
        unmoved, in a table that declares EPSG:4326, so a pole 7 500 000 m east
        became a pole at 7 500 000 degrees. Measured on 3.22, 3.44 and 4.2. Such
        a layer is left out now, and the user is told. Its features are in no
        table, so a relation or path stop naming them is reported as
        unresolved, like a reference to any feature the bundle does not hold.
        """
        target = QgsCoordinateReferenceSystem.fromEpsgId(ic.STORAGE_EPSG)
        kept, unplaceable = [], []
        for entry in mapped:
            layer = entry[0]
            if self._reaches(layer, target):
                kept.append(entry)
                continue
            unplaceable.append(layer.name())
            result.skipped.append((layer.name(), "its CRS does not convert to EPSG:4326"))
        if unplaceable:
            src = QT_TRANSLATE_NOOP(
                'FiberQInterchange',
                "Not exported, because their coordinates cannot be converted to EPSG:4326: "
                "{layers}. Each has no valid CRS, or one with no transformation to "
                "EPSG:4326. Set the CRS their coordinates are in (Layer Properties > "
                "Source), then export again.")
            result.warnings.append(safe_format(
                QCoreApplication.translate('FiberQInterchange', src), src,
                layers=", ".join(repr(name) for name in unplaceable)))
        return kept

    def _reaches(self, layer, target):
        """True when ``layer``'s coordinates can be transformed to ``target``."""
        if not layer.isSpatial():
            return True  # a table with no geometry has no coordinates to place
        crs = layer.crs()
        if crs == target:
            return True
        if not crs.isValid():
            return False
        return QgsCoordinateTransform(crs, target, self.project).isValid()

    def _one_layer_per_table(self, mapped, result):
        """The mapped layers, at most one per bundle table -- or ``None``, refused.

        Unclaimed (WP3 code, found in the v1.6.0 review). Two layers that are
        one FiberQ layer by name -- "Poles" beside the pre-1.0 "Stubovi", or a
        name loaded twice -- were both written as the table "Poles", and the
        second write replaced the first: the first layer's features were not in
        the bundle, and nothing said so. An empty duplicate holds nothing to
        lose and is left out. Two that both hold features cannot share one
        table without choosing whose features to drop, so nothing is written
        and the error names them, with where each one's data lives.
        """
        by_table = {}
        for entry in mapped:
            by_table.setdefault(entry[1], []).append(entry)
        chosen, refused = set(), []
        for table, entries in by_table.items():
            if len(entries) == 1:
                chosen.add(entries[0][0].id())
                continue
            filled = [entry for entry in entries if self._has_features(entry[0])]
            if len(filled) > 1:
                refused.append((table, filled))
                continue
            keep = (filled or entries)[0][0]
            chosen.add(keep.id())
            for entry in entries:
                if entry[0].id() != keep.id():
                    result.skipped.append((entry[0].name(), f"empty, and '{keep.name()}' is the "
                                                            f"bundle table '{table}'"))
        for table, filled in refused:
            src = QT_TRANSLATE_NOOP(
                'FiberQInterchange',
                "Nothing was exported: the layers {layers} would all be written as the bundle "
                "table '{table}', which holds one layer. Merge their features into one layer, "
                "or remove or rename all but one of them, then export again.")
            result.errors.append(safe_format(
                QCoreApplication.translate('FiberQInterchange', src), src, table=table,
                layers=", ".join(f"'{entry[0].name()}' ({self._source_of(entry[0])})"
                                 for entry in filled)))
        if refused:
            return None
        return [entry for entry in mapped if entry[0].id() in chosen]

    def _project_canonicals(self, mapped):
        """Every FiberQ layer name the project has, open or not, and those being written.

        A table or file in an existing bundle is FiberQ's to remove only when the
        project no longer has its layer at all. One whose data QGIS cannot open
        today (a database that is down, a file that moved) or that could not be
        placed in EPSG:4326 is still the project's: its old table stays.
        """
        names = {canonical for _lyr, canonical, _t, _p in mapped}
        for layer in self.project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                canonical = canonical_layer_name(layer.name())
                if canonical:
                    names.add(canonical)
        return names

    def _entries_unreadable(self):
        """True when this QGIS cannot read the project entries a newer one saved (U8)."""
        from ..utils import compat
        from .project_compat import opened_a_newer_project

        try:
            saved_major = self.project.lastSaveVersion().majorVersion()
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"Could not read the version this project was saved with: {e}")
            return False
        return opened_a_newer_project(saved_major, compat.QGIS_VERSION_INT // 10000, True)

    @staticmethod
    def _has_features(layer):
        request = QgsFeatureRequest().setFlags(
            QgsFeatureRequest.Flag.NoGeometry).setNoAttributes().setLimit(1)
        return any(True for _feature in layer.getFeatures(request))

    @staticmethod
    def _source_of(layer):
        """Where a layer's data lives, without a password its connection may hold."""
        if layer.providerType() == "memory":
            return QCoreApplication.translate('FiberQInterchange', "temporary scratch layer")
        return layer.publicSource()

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

    def _canonical_layer(self, layer, canonical, fq_type, placement, index, extras):
        """Build the bundle's copy of a layer in memory, already in bundle shape.

        Canonical field names, canonical values, the storage CRS, the bundle's
        own columns, and ``cable_uuid`` in place of the project-local pair -- all
        of it before a single byte is written.

        This used to happen the obvious way: write the layer, reopen it, then
        ALTER TABLE it into shape. It was correct and it was unusably slow. Each
        layer cost three column additions, up to thirty renames and two drops,
        every one of them on a GeoPackage feature table carrying spatial-index
        triggers. A 23-layer, 46-feature project took **13 seconds**, 81% of it
        in that reshaping, and QGIS sat frozen for all of it -- on a real
        25,000-feature design it would have looked hung.

        Building the copy in memory and writing it once does the same work in a
        fraction of the time, and it reads better: the shape of a bundle layer
        is now stated in one place instead of being an edit history applied to
        something else.
        """
        roster = fm.roster_for_type(fq_type)
        source_fields = layer.fields()
        structural = [
            name for name in fm.STRUCTURAL_FIELDS
            if _stored_index(source_fields, name) >= 0
        ]
        wanted = list(STAMP_COLUMNS)
        if structural:
            wanted.append(fm.CABLE_REFERENCE_FIELD)

        # Field plan: rename to canonical, drop the project-local pair, keep
        # anything the format has no name for under the name it arrived with.
        #
        # U4: two source columns can want the same destination. A pre-1.0 cable
        # layer that v1.5.0's lay_cable has touched carries BOTH
        # ``polaganje_kabla`` and ``cable_laying``, and both map to
        # ``installation_type``. ``QgsFields.append`` refuses the duplicate and
        # answers False, leaving ``count()`` unchanged -- so ``count() - 1``
        # pointed at the *previous* field and every later column shifted by
        # one. With fiberq_uuid sitting between the two laying columns, that
        # wrote the cable's installation type over the identity of every
        # exported cable: the one column the whole format is keyed on.
        #
        # So the result of append() is read, and a refused name is merged into
        # the destination already planned for it.
        #
        # That merge is for two of FiberQ's own columns. Unclaimed (WP3 code,
        # found in the v1.6.0 review): a column of the user's own with the name
        # of one this writer fills -- a `Name` or a `name` beside FiberQ's
        # `naziv`, a `cable_uuid` on a slack layer, an `FQ_TYPE` -- failed the
        # whole export when the names differed only in case, because a
        # GeoPackage compares column names as SQLite does, regardless of case;
        # and when they matched exactly it was merged into FiberQ's column, or
        # overwritten by it, and lost a value. Measured on 3.22, 3.44 and 4.2.
        # So FiberQ's names are claimed first, in a pass of their own, and a
        # column of the user's that wants one keeps its values in fq_extra_json
        # under its own name: what a reader does with an attribute it has no
        # column for.
        claimed = {name.lower() for name in wanted} | {"geom"}
        for source in source_fields:
            canonical_name = fm.canonical_field(roster, source.name()) if roster else None
            if canonical_name:
                claimed.add(canonical_name.lower())

        fields = QgsFields()
        plan = []  # (source index, destination index, canonical name)
        merged = set()  # destinations more than one source column feeds
        carried = []  # (source index, name) of columns kept in fq_extra_json
        taken = set()  # planned names, as SQLite compares them
        primary = set(layer.primaryKeyAttributes())
        for src_index, source in enumerate(source_fields):
            name = source.name()
            if fm.modern_field(name) in fm.STRUCTURAL_FIELDS:
                continue
            canonical_name = fm.canonical_field(roster, name) if roster else None
            if canonical_name is None and not self._keeps_column(
                    source, claimed, taken, src_index in primary):
                carried.append((src_index, name))
                continue
            field = QgsField(source)
            if canonical_name and canonical_name != name:
                field.setName(canonical_name)
            taken.add(field.name().lower())
            if fields.append(field):
                plan.append((src_index, fields.count() - 1, canonical_name or name))
                continue
            existing = fields.indexFromName(field.name())
            if existing < 0:
                return None, f"could not plan the bundle copy of '{canonical}'"
            merged.add(existing)
            plan.append((src_index, existing, canonical_name or name))

        for name in wanted:
            if fields.indexFromName(name) < 0:
                fields.append(_text_field(name))

        target = QgsCoordinateReferenceSystem.fromEpsgId(ic.STORAGE_EPSG)
        clone = QgsMemoryProviderUtils.createMemoryLayer(
            canonical, fields, layer.wkbType(), target)
        if clone is None or not clone.isValid():
            return None, f"could not build the bundle copy of '{canonical}'"

        # Carry the display labels across to the renamed columns, so a bundle
        # opened in plain QGIS still reads as something a human wrote.
        for src_index, dest_index, _name in plan:
            alias = layer.attributeAlias(src_index)
            if alias:
                clone.setFieldAlias(dest_index, alias)

        transform = None
        if layer.crs().isValid() and layer.crs() != target:
            transform = QgsCoordinateTransform(layer.crs(), target, self.project)

        type_index = fields.indexFromName("fq_type")
        place_index = fields.indexFromName("placement")
        extra_index = fields.indexFromName("fq_extra_json")
        cable_index = fields.indexFromName(fm.CABLE_REFERENCE_FIELD)
        uuid_index = source_fields.indexFromName(FIBERQ_UUID_FIELD)
        cable_layer_index = _stored_index(source_fields, "cable_layer_id")
        cable_fid_index = _stored_index(source_fields, "cable_fid")

        built = []
        unresolved = 0
        unreprojectable = 0
        uncarried = 0
        for source_feature in layer.getFeatures():
            feature = QgsFeature(fields)
            geometry = QgsGeometry(source_feature.geometry())
            # isEmpty() as well as isNull(): a `Point EMPTY` answers False to
            # isNull() but has no coordinates to move, and `transformed()`
            # rejects it like any other geometry it cannot measure. Guarding on
            # isNull() alone dropped such a feature -- caught by
            # test_sample_bundle.py against this repo's own published example,
            # which carries one. A feature with no geometry is ordinary: QGIS
            # makes one whenever a row is added without digitising.
            if transform is not None and not geometry.isNull() and not geometry.isEmpty():
                # U13. `transform()` does NOT raise for a coordinate outside the
                # projection's domain: measured on 3.22.16, 3.44.15 and 4.2.3 it
                # answers Success and leaves `inf`. For a point it does raise,
                # but only after the geometry is already `Point (inf inf)`, so
                # catching it changed nothing either. The old handler here could
                # not have worked in either direction. `transformed()` checks the
                # result as well as the call -- see utils.geometry.is_finite.
                moved = transformed(geometry, transform)
                if moved is None:
                    unreprojectable += 1
                    continue
                geometry = moved
            feature.setGeometry(geometry)

            for src_index, dest_index, canonical_name in plan:
                value = source_feature.attribute(src_index)
                if roster and value is not None:
                    value = fm.canonical_value(roster, canonical_name, value)
                if dest_index in merged:
                    # First non-blank wins, and nothing blank overwrites it.
                    # Per feature only one of the two columns is ever filled:
                    # cables laid before the rename carry the Serbian one,
                    # cables laid by v1.5.0 carry the English one. Merging is
                    # therefore lossless here, and the project's own columns
                    # are left exactly as they are -- no on-disk migration,
                    # which would rewrite user data and break user expressions.
                    if self._is_blank(value):
                        continue
                    if not self._is_blank(feature.attribute(dest_index)):
                        continue
                feature.setAttribute(dest_index, value)

            # A value already on the feature is never overwritten: that is what
            # lets a bundle carrying a type this plugin does not model leave
            # through here unchanged (spec 6.1).
            if type_index >= 0 and self._is_blank(feature.attribute(type_index)):
                feature.setAttribute(type_index, fq_type)
            if placement and place_index >= 0 and self._is_blank(
                    feature.attribute(place_index)):
                feature.setAttribute(place_index, placement)

            identity = source_feature.attribute(uuid_index) if uuid_index >= 0 else None
            payload = extras.get(str(identity)) if extras and identity else None
            if isinstance(payload, str):
                payload = _parsed(payload)

            if cable_index >= 0 and cable_layer_index >= 0 and cable_fid_index >= 0:
                resolved = self._resolve(
                    index, source_feature.attribute(cable_layer_index),
                    source_feature.attribute(cable_fid_index))
                if resolved is not None:
                    feature.setAttribute(cable_index, resolved)
                elif isinstance(payload, dict) and payload.get(fm.CABLE_REFERENCE_FIELD):
                    # A reference the import could not resolve, kept with the
                    # feature's extras: back into its own column, where a reader
                    # looks for it, not into fq_extra_json.
                    payload = dict(payload)
                    feature.setAttribute(cable_index, payload.pop(fm.CABLE_REFERENCE_FIELD))
                elif not self._is_blank(source_feature.attribute(cable_fid_index)):
                    unresolved += 1

            values = {}
            for src_index, name in carried:
                value = ic.json_safe(source_feature.attribute(src_index))
                if value is not None:
                    values[name] = value
            if values:
                combined = self._combined_extras(payload, values, feature.attribute(extra_index))
                if combined is None:
                    uncarried += 1
                else:
                    feature.setAttribute(extra_index, combined)
                    payload = None

            if payload and extra_index >= 0 and self._is_blank(feature.attribute(extra_index)):
                feature.setAttribute(extra_index, payload if isinstance(
                    payload, str) else json.dumps(payload))

            built.append(feature)

        # addFeatures() answers a tuple, (ok, features), and a non-empty tuple
        # is always true: tested whole, a provider that refused every feature
        # went unnoticed and an empty bundle table was reported as written.
        # Unclaimed (WP3 code; WP5-FU-6, pulled into v1.6.0).
        ok, _added = clone.dataProvider().addFeatures(built) if built else (True, [])
        if not ok:
            return None, f"could not fill the bundle copy of '{canonical}'"
        self._unresolved_cable_refs += unresolved
        self._unreprojectable += unreprojectable
        self._uncarried += uncarried
        self._carried_columns.extend(f"{layer.name()}.{name}" for _index, name in carried)
        return clone, None

    @staticmethod
    def _keeps_column(source, claimed, taken, is_primary_key=False):
        """True when a column the format has no name for can be a column of its own."""
        name = source.name()
        folded = name.lower()
        if folded in taken:
            return False  # differs only in case from a column already planned
        if name in STAMP_COLUMNS:
            # Already a bundle column, filled by whoever wrote it, and kept: the
            # writer never overwrites a value (spec 6.1).
            return True
        if folded == "fid":
            # The layer's own row id (a GeoPackage layer's primary key) stays the
            # bundle's row id, as it always has. Any other column of that name is
            # the user's: OGR would take it for the row id, and failed the write
            # when it was not an integer ("Wrong field type for fid") or, on
            # QGIS 3.40, as soon as two features had one ("UNIQUE constraint
            # failed"). Measured on 3.22, 3.40, 3.44 and 4.2.
            return is_primary_key
        return folded not in claimed

    @staticmethod
    def _combined_extras(kept, values, live):
        """fq_extra_json for a feature that has columns carried in it, or ``None``.

        What an import kept, then the carried columns, then the feature's own
        fq_extra_json, each winning over the one before: what the project holds
        now beats what an import kept. ``None`` when the kept or the feature's
        own value is not a JSON object, so there is nothing to add them to.
        """
        combined = {}
        for part in (kept, values, live):
            part = _json_object(part)
            if part is None:
                return None
            combined.update(part)
        return json.dumps(combined, sort_keys=True)

    # -- side-car ----------------------------------------------------------

    @staticmethod
    def _create_sidecar(conn, timestamp):
        """Create the ``fq_*`` tables and register them so GDAL lists them.

        Only this format's own tables, and only when they are not registered
        yet. This used to re-register every table whose name starts ``fq_``
        with INSERT OR REPLACE: another tool's *feature* table named that way
        became an attributes table with no CRS, and QGIS opened it without its
        geometry; and the REPLACE settled a clash on the unique identifier by
        deleting the other table's registration (measured on 3.22, 3.44, 4.2).
        """
        for statement in ic.SIDECAR_DDL:
            conn.execute(statement)
        for name in ic.SIDECAR_TABLES:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO gpkg_contents "
                    "(table_name, data_type, identifier, description, last_change, srs_id) "
                    "VALUES (?, 'attributes', ?, ?, ?, 0)",
                    (name, name, f"FiberQ interchange side-car table {name}", timestamp),
                )
            except sqlite3.Error as e:
                # A GeoPackage without gpkg_contents is malformed, but the data
                # is still readable by any SQLite client, so this is not fatal.
                logger.debug(f"Could not register {name} in gpkg_contents: {e}")

    def _write_relations(self, conn, index, additive=False):
        """Emit the project's cable relations as uuid-keyed side-car rows.

        Returns ``(relations, members written, unresolved, uuids written)``.

        The plugin stores relations as ``{"relations": [{"id", "name",
        "cables": [{"layer_id", "fid"}]}]}``. Before FiberQ 1.6.0 every
        relation left as a uuid derived from the project file's path -- a new
        identity on Save As, and a foreign relation's own uuid thrown away on
        import -- with category ``cable_group`` and every member's role
        ``cable``. Now each leaves under :func:`interchange.relation_identity`,
        with the category, member roles, member order and any column a later
        1.x version added that it came with, and the members the project
        cannot draw (``kept_members``) go back too. Cables whose identity
        cannot be resolved are counted, not guessed at.
        """
        raw = self.project.readEntry("StuboviPlugin", "Relacije/relations_v1", "")[0]
        if not raw:
            return 0, 0, 0, set()
        data = _parsed(raw)
        if not isinstance(data, dict):
            # Not "no relations": what FiberQ wrote for them before is kept.
            self._unreadable_entries.append("relations")
            return 0, 0, 0, set()
        relations_list = [r for r in data.get("relations", []) or [] if isinstance(r, dict)]

        relation_columns = _extra_columns(conn, "fq_relation", ("uuid", "name", "category"),
                                          [r.get("extra") for r in relations_list])
        member_columns = _extra_columns(
            conn, "fq_relation_member", ("relation_uuid", "member_uuid", "order_index", "role"),
            [m.get("extra") for r in relations_list
             for m in (r.get("cables") or []) + (r.get("kept_members") or []) if isinstance(m, dict)])
        insert_relation = _insert_sql("fq_relation", relation_columns)
        insert_member = _insert_sql("fq_relation_member", member_columns)

        project_key = self.project.fileName() or self.project.title() or ""
        relations = written_members = unresolved = 0
        written = set()
        for relation in relations_list:
            relation_uuid = ic.relation_identity(relation, project_key)
            # A category the relation came with is kept, NULL included; one made
            # before 1.6.0 without any keeps the writer's old default.
            category = relation["category"] if "category" in relation else "cable_group"
            conn.execute(insert_relation, _with_extra(
                [relation_uuid, relation.get("name", ""), category], relation, relation_columns[3:]))
            relations += 1
            written.add(relation_uuid)
            # This relation's rows are rewritten from the project: a member
            # removed since the last export over this file must not stay. Not
            # while a FiberQ layer cannot be read (``additive``): a member on it
            # cannot be written again, and would be lost rather than kept.
            if not additive:
                conn.execute("DELETE FROM fq_relation_member WHERE relation_uuid = ?",
                             (relation_uuid,))
            members = [m for m in relation.get("cables", []) or [] if isinstance(m, dict)]
            orders = [_order(m, None) for m in members]
            following = max((o for o in orders if o is not None), default=-1) + 1
            emitted = set()
            for position, cable in enumerate(members):
                member = self._resolve(index, cable.get("layer_id"), cable.get("fid"))
                if member is None:
                    unresolved += 1
                    continue
                order = _order(cable, None)
                if order is None:
                    # One the dialog added to a relation an import brought in
                    # with its own numbering: after the rest, not in the middle.
                    order = position if following == 0 else following
                    following += 1 if following else 0
                conn.execute(insert_member, _with_extra(
                    [relation_uuid, member, order, cable.get("role", "cable")],
                    cable, member_columns[4:]))
                emitted.add(member)
                written_members += 1
            for kept in relation.get("kept_members") or []:
                member = (kept or {}).get("member_uuid")
                if not member or member in emitted:
                    continue
                conn.execute(insert_member, _with_extra(
                    [relation_uuid, member, kept.get("order_index"), kept.get("role")],
                    kept, member_columns[4:]))
                emitted.add(member)
                written_members += 1
        return relations, written_members, unresolved, written

    def _write_path_stops(self, conn, index, additive=False):
        """Emit the elements each cable passes as ``fq_path_stop`` rows, in order.

        Read through :func:`interchange.latent_records`, which knows both shapes
        the project entry comes in: the pass-through dialog's, where every
        element found along the cable is listed in order and marked latent or
        not, and the list a v1.5.0 bundle import wrote, ordered by ``m``. This
        used to read only the second, and raised on the first -- so a bundle
        export of any project edited in FiberQ's own dialog failed outright.

        ``is_latent`` is the element's mark (spec section 6.4: 1 for an element
        the cable merely passes through). ``order_index`` is the element's own,
        when an import recorded one, else its position.
        """
        raw = self.project.readEntry("StuboviPlugin", "LatentElements/latent_v1", "")[0]
        if not raw:
            return 0, 0, set()
        data = _parsed(raw)
        if not isinstance(data, dict):
            self._unreadable_entries.append("pass-through elements")
            return 0, 0, set()

        records = ic.latent_records(data)
        # A column a later 1.x version added to fq_path_stop rides in each stop's
        # "extra" (the importer put it there); it goes back as that column.
        extra_names = []
        for elements in records.values():
            for element in elements:
                for name in (element.get("extra") or {}):
                    if name not in extra_names:
                        extra_names.append(name)
        columns = ["cable_uuid", "element_uuid", "order_index", "is_latent"]
        if extra_names:
            present = {c.lower() for c in _ensure_columns(
                conn, "fq_path_stop", [[name, ""] for name in extra_names])}
            columns += [n for n in extra_names if n.lower() in present and n.lower() not in
                        {"cable_uuid", "element_uuid", "order_index", "is_latent"}]
        # The format's own table; the extra column names are quoted.
        insert = (f'INSERT OR REPLACE INTO fq_path_stop ({", ".join(_quoted(c) for c in columns)}) '  # nosec B608
                  f'VALUES ({", ".join("?" for _ in columns)})')

        written = unresolved = 0
        cables = set()
        for key, elements in records.items():
            layer_id, _, fid = key.rpartition(":")
            cable_uuid = self._resolve(index, layer_id, fid)
            if cable_uuid is None:
                unresolved += len(elements)
                continue
            # This cable's stops are rewritten from the project, so one removed
            # since the last export over this file goes -- unless a FiberQ layer
            # cannot be read, as for relation members above.
            if not additive:
                conn.execute("DELETE FROM fq_path_stop WHERE cable_uuid = ?", (cable_uuid,))
            cables.add(cable_uuid)
            for position, element in enumerate(elements):
                element_uuid = self._resolve(index, element.get("layer_id"), element.get("fid"))
                if element_uuid is None and "layer_id" not in element:
                    # Kept by identity at import: an element FiberQ does not
                    # draw (a splitter in the passthrough store, say).
                    element_uuid = element.get("element_uuid")
                if element_uuid is None:
                    unresolved += 1
                    continue
                extra = element.get("extra") or {}
                values = [cable_uuid, element_uuid, _order(element, position),
                          1 if element["latent"] else 0]
                values.extend(ic.from_json_safe(extra.get(c)) for c in columns[4:])
                conn.execute(insert, values)
                written += 1
        return written, unresolved, cables

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
            elif kind == ic.EXTENSION_KIND_SIDECAR and row.get("namespace") == ic.EXTENSION_NAMESPACE:
                # Only FiberQ's own store rows are table writes. Another tool's
                # fq_extension row that happens to use the same kind is that
                # tool's data, written back as the row it is.
                try:
                    parsed = json.loads(payload) if isinstance(payload, str) else payload
                except ValueError as e:
                    logger.debug(f"Kept side-car payload is not valid JSON: {e}")
                    extensions.append(row)
                    continue
                table = _sidecar_table((parsed or {}).get("table")) or _unknown_table(
                    (parsed or {}).get("table"))
                if table:
                    entry = sidecar.setdefault(table, {"columns": [], "rows": []})
                    entry["columns"] = _united(entry["columns"], (parsed or {}).get("columns"))
                    entry["rows"] = ic.merge_kept_rows(entry["rows"], (parsed or {}).get("rows"))
                else:
                    extensions.append(row)
            else:
                extensions.append(row)
        return extensions, attributes, sidecar, metadata

    def _write_passthrough(self, conn, extensions):
        """Write back everything that stays an extension row (spec section 8).

        Every column a row arrived with goes back, including one a later 1.x
        version adds to ``fq_extension`` -- the six this version defines were
        all that used to.
        """
        written = 0
        for row in extensions or []:
            values = dict(row)
            payload = values.get("payload_json")
            if payload is not None and not isinstance(payload, str):
                values["payload_json"] = json.dumps(payload)
            columns = _ensure_columns(conn, "fq_extension", [[k, ""] for k in values])
            names = [c for c in columns if c.lower() in {k.lower() for k in values}]
            folded = {k.lower(): v for k, v in values.items()}
            # The table is the format's own; the column names are quoted.
            conn.execute(
                f'INSERT OR REPLACE INTO fq_extension ({", ".join(_quoted(c) for c in names)}) '  # nosec B608
                f'VALUES ({", ".join("?" for _ in names)})',
                [ic.from_json_safe(folded.get(c.lower())) for c in names])
            written += 1
        return written

    @staticmethod
    def _write_kept_sidecar(conn, sidecar):
        """Write kept side-car rows back into the tables they came from.

        Returns ``(rows written, problems)``. Each table goes in under its own
        SAVEPOINT. The rows are another tool's data, so a constraint this
        bundle's table has and theirs had not, or anything else SQLite refuses,
        costs that table's rows and a warning naming it -- it used to abort the
        whole side-car phase before ``_fiberq_metadata`` was written, leaving a
        file the importer refused as "not a FiberQ interchange bundle".

        A row's keys meet the table's columns regardless of case, as SQLite
        compares them; a tagged blob goes back in as bytes.
        """
        written, problems = 0, []
        for table, entry in (sidecar or {}).items():
            rows = entry.get("rows") if isinstance(entry, dict) else entry
            recorded = (entry.get("columns") if isinstance(entry, dict) else None) or []
            if not rows:
                continue
            conn.execute("SAVEPOINT fiberq_kept")
            try:
                if table not in ic.SIDECAR_TABLES:
                    _create_carried_table(conn, table, recorded, rows)
                # A column the rows carry that the table lacks: one a later 1.x
                # version added (the WP3 known limit "a column added by a newer
                # minor format version survives in the project but not into the
                # next bundle"). Used to be dropped here, silently.
                wanted = list(recorded) + [[k, ""] for row in rows for k in row]
                columns = _ensure_columns(conn, table, wanted)
                keyed = any(r[5] for r in conn.execute(f'PRAGMA table_info("{table}")'))  # nosec B608
                quoted = ", ".join(_quoted(c) for c in columns)
                placeholders = ", ".join("?" for _ in columns)
                # The table name is validated (a format table, or fq_ and word
                # characters) and every column name is quoted.
                insert = f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({placeholders})'  # nosec B608
                same = f'DELETE FROM "{table}" WHERE ' + " AND ".join(  # nosec B608
                    f"{_quoted(c)} IS ?" for c in columns)
                for row in rows:
                    folded = {str(k).lower(): v for k, v in row.items()}
                    values = [ic.from_json_safe(folded.get(c.lower())) for c in columns]
                    if not keyed:
                        # No key to REPLACE on: an equal row from an earlier export
                        # over this file would be doubled every time.
                        conn.execute(same, values)
                    conn.execute(insert, values)
                conn.execute("RELEASE fiberq_kept")
                written += len(rows)
            except (sqlite3.Error, sqlite3.Warning) as e:
                conn.execute("ROLLBACK TO fiberq_kept")
                conn.execute("RELEASE fiberq_kept")
                problems.append(f"{len(rows)} kept row(s) of {table} could not be written back: {e}")
        return written, problems

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

    def _write_metadata(self, conn, existing, timestamp, written=None):
        """Write the merged metadata table, keeping every foreign key intact.

        ``written`` is FiberQ's record of the relation and cable rows it wrote
        (``interchange.WRITTEN_KEY``); without one, an older record is removed.

        Unclaimed (WP3 code, found in the v1.6.0 review), two keys FiberQ owns
        but does not always produce:

        - the colour standard. Every export wrote the project's own, or
          TIA-598-C when it has no colour catalogue, so a bundle drawn to
          another standard -- imported into a new project, or exported over --
          left saying TIA-598-C beside the catalogue that defines the other
          one. While the project has no catalogue, the standard and the
          catalogue it arrived with are carried on together. Once it has one,
          its own is written and the arrived catalogue, which describes another
          standard, is removed;
        - keys that only describe an earlier write to the same file. The five
          of RETIRED_METADATA_KEYS are FiberQ's project export's (a bundle
          written over one kept its relations_json, which disagrees with the
          bundle's own fq_relation from then on), and ``profile`` is the
          GeoJSON profile's, which sets it again when it applies.
        """
        crs = self.project.crs()
        epsg = ""
        if crs.isValid():
            authid = crs.authid()
            epsg = authid.split(":")[-1] if ":" in authid else authid

        own = self._project_color_standard()
        produced = ic.build_metadata(
            schema_version=SCHEMA_VERSION,
            crs_epsg=epsg,
            plugin_version=self.plugin_version,
            timestamp=timestamp,
            color_standard=own or (existing or {}).get("color_standard") or ic.DEFAULT_COLOR_STANDARD,
        )
        if written:
            produced[ic.WRITTEN_KEY] = json.dumps(written, sort_keys=True)
        merged = ic.merge_metadata(existing, produced)
        stale = set(ic.RETIRED_METADATA_KEYS) | {"profile"}
        if own:
            stale.add("color_catalog_json")
        if not written:
            stale.add(ic.WRITTEN_KEY)
        for key in stale:
            merged.pop(key, None)

        conn.execute(
            "CREATE TABLE IF NOT EXISTS _fiberq_metadata "
            "(key TEXT PRIMARY KEY, value TEXT)"
        )
        try:
            conn.execute(
                "INSERT OR IGNORE INTO gpkg_contents "
                "(table_name, data_type, identifier, description, last_change, srs_id) "
                "VALUES ('_fiberq_metadata', 'attributes', '_fiberq_metadata', ?, ?, 0)",
                ("FiberQ interchange bundle metadata", timestamp),
            )
        except sqlite3.Error as e:
            logger.debug(f"Could not register _fiberq_metadata in gpkg_contents: {e}")

        for key in sorted(stale):
            conn.execute("DELETE FROM _fiberq_metadata WHERE key = ?", (key,))
        for key, value in merged.items():
            conn.execute(
                "INSERT OR REPLACE INTO _fiberq_metadata (key, value) VALUES (?, ?)",
                (key, "" if value is None else str(value)),
            )
        return merged

    def _project_color_standard(self):
        """The name of the project's own colour catalogue, or ``None`` when it has none."""
        raw = self.project.readEntry("StuboviPlugin", "ColorCatalogs/catalogs_v1", "")[0]
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except ValueError as e:
            logger.debug(f"Colour catalogue entry is not valid JSON: {e}")
            return None
        catalogs = data.get("catalogs") if isinstance(data, dict) else None
        for catalog in catalogs if isinstance(catalogs, list) else []:
            name = str(catalog.get("name") or "").strip() if isinstance(catalog, dict) else ""
            if name:
                return name
        return None

    # -- the whole thing ---------------------------------------------------

    def write(self, gpkg_path, layers=None, passthrough=None, carried_metadata=None):
        """Write a bundle to ``gpkg_path`` and report exactly what went into it.

        ``carried_metadata`` is the metadata of a bundle this one replaces when
        that is not the file itself -- the GeoJSON profile's folder. The file's
        own keys win over it, and it wins over the keys the project kept.
        """
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
        # Both before a byte is written: a refusal must leave an existing
        # bundle exactly as it was.
        mapped = self._one_layer_per_table(self._placeable(mapped, result), result)
        if mapped is None:
            return result
        if not mapped:
            src = QT_TRANSLATE_NOOP(
                'FiberQInterchange',
                "Nothing was exported: no FiberQ layer in this project has coordinates that "
                "convert to EPSG:4326.")
            result.errors.append(QCoreApplication.translate('FiberQInterchange', src))
            return result
        if not self._unreadable_project_may_write(gpkg_path, result):
            return result
        if self._unavailable:
            src = QT_TRANSLATE_NOOP(
                'FiberQInterchange',
                "Not exported, because QGIS cannot open their data: {layers}. Their tables in "
                "an existing bundle are kept as they were.")
            result.warnings.append(safe_format(
                QCoreApplication.translate('FiberQInterchange', src), src,
                layers=", ".join(repr(name) for name in self._unavailable)))

        # Read first: a half-written file no longer knows what another tool put
        # in it, and this is the merge's only chance to find out.
        existing = read_bundle_metadata(gpkg_path)
        file_metadata = dict(existing)
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

        extensions, extras, kept_sidecar, kept_metadata = self._load_passthrough(
            passthrough)
        # Keys another tool wrote reach a *new* bundle through the project;
        # keys already in *this* file are read straight off it (above).
        existing = ic.merge_metadata(ic.merge_metadata(kept_metadata, carried_metadata), existing)
        # Except the colour pair, which is taken whole from one place: what an
        # import brought (what the project's cables were drawn to), else the
        # file, else the folder. Merged key by key, an earlier FiberQ export's
        # TIA-598-C sat beside an imported ACME-24 catalogue.
        colour = ic.colour_pair(kept_metadata, file_metadata, carried_metadata)
        for key in ic.COLOUR_METADATA_KEYS:
            existing.pop(key, None)
        existing.update(colour)
        self._unresolved_cable_refs = 0
        self._unreprojectable = 0
        self._uncarried = 0
        self._carried_columns = []
        self._unreadable_entries = []

        file_exists = os.path.exists(gpkg_path)
        for lyr, canonical, fq_type, placement in mapped:
            clone, error = self._canonical_layer(
                lyr, canonical, fq_type, placement, index, extras)
            if error:
                result.errors.append(f"{lyr.name()}: {error}")
                continue
            error = self._write_layer(clone, canonical, gpkg_path, file_exists)
            file_exists = True
            if error:
                result.errors.append(f"{lyr.name()}: {error}")
                continue
            # What reached the bundle, not what the project holds: a feature
            # left out by the reprojection guard above must not be counted as
            # exported. `clone` is the bundle copy, so its count is the truth.
            result.layers[canonical] = clone.featureCount()
            result.types[canonical] = (fq_type, placement)

        # U13. Said here rather than beside the reference warning below, which
        # sits inside the side-car `try` and after the early return: a geometry
        # left out of the bundle must be reported even when the side-car write
        # fails, and even when no layer produced a side-car row at all.
        if self._unreprojectable:
            result.warnings.append(
                f"{self._unreprojectable} feature(s) could not be reprojected to EPSG:4326 and were "
                "left out of the bundle rather than written with infinite coordinates."
            )
        if self._carried_columns:
            src = QT_TRANSLATE_NOOP(
                'FiberQInterchange',
                "These columns have the name of a column FiberQ writes, so their values are in "
                "fq_extra_json under their own names: {columns}.")
            result.warnings.append(safe_format(
                QCoreApplication.translate('FiberQInterchange', src), src,
                columns=", ".join(self._carried_columns)))
        if self._uncarried:
            src = QT_TRANSLATE_NOOP(
                'FiberQInterchange',
                "{count} feature(s) have a column that belongs in fq_extra_json, but their "
                "fq_extra_json is not a JSON object, so that column's values were not written.")
            result.warnings.append(safe_format(
                QCoreApplication.translate('FiberQInterchange', src), src,
                count=self._uncarried))

        if not result.layers:
            return result

        # Unclaimed (WP3 code, found in the v1.6.0 review). An export over a
        # bundle left the tables it had written there last time for a layer the
        # project no longer has -- removed or renamed -- so a reader went on
        # finding manholes that had been deleted, presented as this export's.
        # The record of what FiberQ wrote says which tables are its own; nobody
        # else's is touched, and a bundle with no record (one written before
        # 1.6.0) loses nothing. A layer the project still has, open or not,
        # keeps its table.
        previous = _previously_written(file_metadata)
        present = self._project_canonicals(mapped)
        removed, failed = _old_tables_removed(gpkg_path, previous, present)
        self._report_removed(result, removed, failed, "bundle")
        # The project's relations and pass-through elements can only be judged
        # complete when every FiberQ layer was read: a member or a stop on a
        # feature of a layer QGIS could not open is not resolvable today, and
        # that is not the same as the project no longer having it.
        incomplete = bool(present - {canonical for _lyr, canonical, _t, _p in mapped})

        timestamp = datetime.now(timezone.utc).isoformat()
        conn = None
        try:
            conn = sqlite3.connect(gpkg_path)
            self._create_sidecar(conn, timestamp)

            relations, members, unresolved_members, relation_uuids = self._write_relations(
                conn, index, additive=incomplete)
            stops, unresolved_stops, cable_uuids = self._write_path_stops(
                conn, index, additive=incomplete)
            # Kept, and still FiberQ's, when what the project holds could not be
            # read in full: a later export that can read it decides about them.
            if incomplete or "relations" in self._unreadable_entries:
                relation_uuids = set(relation_uuids) | set(previous.get("fq_relation") or [])
            if incomplete or "pass-through elements" in self._unreadable_entries:
                cable_uuids = set(cable_uuids) | set(previous.get("fq_path_stop") or [])
            _forget(conn, previous, relation_uuids, cable_uuids)
            for entry in self._unreadable_entries:
                src = QT_TRANSLATE_NOOP(
                    'FiberQInterchange',
                    "The project's {entry} could not be read, so none were exported; what FiberQ "
                    "wrote for them in an existing bundle is kept.")
                result.warnings.append(safe_format(
                    QCoreApplication.translate('FiberQInterchange', src), src, entry=entry))
            written_extensions = self._write_passthrough(conn, extensions)
            result.sidecar_rows = {
                "fq_relation": relations,
                "fq_relation_member": members,
                "fq_path_stop": stops,
                "fq_extension": written_extensions,
            }
            _written, kept_problems = self._write_kept_sidecar(conn, kept_sidecar)
            for table, entry in kept_sidecar.items():
                result.sidecar_rows[table] = len(entry["rows"])
            result.warnings.extend(kept_problems)
            result.inlined_extras = len(extras)
            unresolved_members += self._unresolved_cable_refs
            if unresolved_members or unresolved_stops:
                result.warnings.append(
                    f"{unresolved_members + unresolved_stops} reference(s) could not be "
                    "resolved to a fiberq_uuid and were left out rather than guessed at."
                )

            result.preserved = ic.foreign_keys(existing)
            # A table this export could not write, or could not remove, stays
            # FiberQ's while it is in the file, and the next export decides again.
            # One that is gone is forgotten: another tool may make a table of
            # that name later, and it is not FiberQ's.
            in_file = {str(name).lower() for (name,) in conn.execute(
                "SELECT table_name FROM gpkg_contents")}
            features = set(result.layers) | {
                name for name in previous.get("features") or []
                if name.lower() in in_file and name not in removed}
            written = {"produced_at": timestamp, "fq_relation": sorted(relation_uuids),
                       "fq_path_stop": sorted(cable_uuids), "features": sorted(features)}
            result.metadata = self._write_metadata(conn, existing, timestamp, written)
            conn.commit()
        except (sqlite3.Error, sqlite3.Warning) as e:
            # sqlite3.Warning too: Python 3.10's sqlite3 (QGIS 3.22) raises it,
            # not an Error, for a statement it refuses to run.
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

        # Unclaimed (WP3 code, found in the v1.6.0 review). The folder's own
        # _fiberq_metadata.json was overwritten with this export's keys alone,
        # so writing into a folder another tool also writes lost that tool's
        # keys -- what section 7 forbids, and what the GeoPackage profile has
        # never done. They are merged now, the same way.
        folder_metadata, problem = self._folder_metadata(directory)
        if problem:
            result.warnings.append(problem)
        bundle_there = os.path.isfile(os.path.join(directory, "_fiberq_metadata.json"))
        if not self._unreadable_project_may_write(directory, result, bundle_there):
            return result

        workdir = tempfile.mkdtemp(prefix="fiberq-bundle-")
        try:
            staged = self.write(
                os.path.join(workdir, "bundle.gpkg"), layers=layers,
                passthrough=passthrough, carried_metadata=folder_metadata)
            result.layers = staged.layers
            result.types = staged.types
            result.skipped = staged.skipped
            result.warnings.extend(staged.warnings)
            result.errors = list(staged.errors)
            result.preserved = staged.preserved
            if not staged.ok:
                return result

            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as e:
                result.errors.append(f"Could not create {directory}: {e}")
                return result

            files = set()
            for canonical in list(result.layers):
                fq_type, placement = result.types[canonical]
                stem = f"{fq_type}.{placement}" if placement else fq_type
                files.add(f"{stem}.geojson")
                error = self._write_geojson_layer(
                    staged.path, canonical, os.path.join(directory, f"{stem}.geojson"))
                if error:
                    result.errors.append(error)

            # As for the GeoPackage profile's tables: the files FiberQ wrote here
            # last time for an element type the project no longer has a layer for.
            previous = _previously_written(folder_metadata)
            removed, failed = _old_files_removed(
                directory, previous, files | self._stems(self._project_canonicals([])))
            self._report_removed(result, removed, failed, "folder")

            dropped = sum(staged.sidecar_rows.values())
            metadata = dict(staged.metadata)
            # The staged record is of a GeoPackage's tables and side-car rows;
            # this profile records its files, while they are there.
            kept = files | {name for name in previous.get("files") or []
                            if name not in removed and self._file_there(directory, name)}
            metadata[ic.WRITTEN_KEY] = json.dumps(
                {"produced_at": metadata.get("produced_at"), "files": sorted(kept)},
                sort_keys=True)
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

    @staticmethod
    def _file_there(directory, name):
        """True when a recorded GeoJSON file name is a bare name and the file is there."""
        if not _geojson_name(name):
            return False
        return os.path.isfile(os.path.join(directory, name))

    @staticmethod
    def _stems(canonicals):
        """The GeoJSON file names the profile writes for these canonical layer names."""
        stems = set()
        for canonical in canonicals:
            entry = ic.type_for_layer(canonical)
            if entry is not None:
                fq_type, placement = entry
                stems.add(f"{fq_type}.{placement}.geojson" if placement else f"{fq_type}.geojson")
        return stems

    def _unreadable_project_may_write(self, target, result, exists=None):
        """U8: False, with an error, when a QGIS 4 project read in QGIS 3 would write over a bundle.

        QGIS 3 cannot read a single project entry QGIS 4 saved (see
        core/project_compat.py), so the project reads as one with no relations,
        no pass-through elements and nothing an import kept for other tools.
        Written over an existing bundle, that removed what FiberQ had written
        there for them and the attributes its features carried in
        fq_extra_json. Nothing is written over one now; a new bundle is
        written, and says what it lacks.
        """
        if not self._entries_unreadable():
            return True
        if exists is None:
            exists = os.path.exists(target)
        if exists:
            src = QT_TRANSLATE_NOOP(
                'FiberQInterchange',
                "Nothing was exported: this project was saved in QGIS 4, and QGIS 3 cannot read "
                "its relations, pass-through elements or what an import kept for other tools. "
                "Written over the existing bundle, that would remove them from it. Export from "
                "QGIS 4, or to a new file.")
            result.errors.append(QCoreApplication.translate('FiberQInterchange', src))
            return False
        src = QT_TRANSLATE_NOOP(
            'FiberQInterchange',
            "This project was saved in QGIS 4, and QGIS 3 cannot read its relations, "
            "pass-through elements or what an import kept for other tools, so this bundle has "
            "none of them. Export from QGIS 4 for a complete bundle.")
        result.warnings.append(QCoreApplication.translate('FiberQInterchange', src))
        return True

    @staticmethod
    def _report_removed(result, removed, failed, where):
        """Say what an export removed from the bundle or folder it replaced, and what it could not."""
        if removed:
            if where == "bundle":
                src = QT_TRANSLATE_NOOP(
                    'FiberQInterchange',
                    "Removed from the bundle: {names}. FiberQ wrote them there last time, and "
                    "this export has no layer for them.")
            else:
                src = QT_TRANSLATE_NOOP(
                    'FiberQInterchange',
                    "Removed from the folder: {names}. FiberQ wrote them there last time, and "
                    "this export has no layer for them.")
            result.warnings.append(safe_format(
                QCoreApplication.translate('FiberQInterchange', src), src,
                names=", ".join(removed)))
        if failed:
            src = QT_TRANSLATE_NOOP(
                'FiberQInterchange',
                "Could not remove what FiberQ wrote last time for a layer this export does not "
                "have: {names}.")
            result.warnings.append(safe_format(
                QCoreApplication.translate('FiberQInterchange', src), src,
                names=", ".join(failed)))

    @staticmethod
    def _folder_metadata(directory):
        """``(metadata, problem)``: the folder's ``_fiberq_metadata.json``, if it has one."""
        path = os.path.join(directory, "_fiberq_metadata.json")
        if not os.path.isfile(path):
            return {}, None
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as e:
            data, reason = None, str(e)
        else:
            reason = "not a JSON object"
        if isinstance(data, dict):
            return data, None
        src = QT_TRANSLATE_NOOP(
            'FiberQInterchange',
            "The folder's _fiberq_metadata.json could not be read ({reason}), so it was "
            "replaced, and any keys another tool kept in it are lost.")
        return {}, safe_format(QCoreApplication.translate('FiberQInterchange', src), src,
                               reason=reason)

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
        # Leave the GeoPackage's row id behind. It is the staged file's primary
        # key, invisible in the GeoPackage profile and meaningless outside it --
        # but OGR turns it into an ordinary property here, so a reader of the
        # GeoJSON profile would find two identifier-shaped fields and no way to
        # tell that only fiberq_uuid is stable. Spec section 4 says identity is
        # the uuid; publishing a row number beside it invites exactly the join
        # the format exists to prevent.
        fid_index = layer.fields().indexFromName("fid")
        if fid_index >= 0:
            opts.attributes = [
                index for index in range(layer.fields().count())
                if index != fid_index
            ]
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
