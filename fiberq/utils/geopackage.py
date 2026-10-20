"""What a GeoPackage says about one of its tables, read from the file itself.

WP4 task 4.1, item PF-4. QGIS reports a GeoPackage layer's declared geometry
type and fields, not what the file holds beyond them: whether a LINESTRING
table holds arcs, whether the "table" is a view, or what the database does on
its own when a row is written. These decide whether a box query answers
exactly as the whole-layer scan it replaces (``utils.spatial.features_near``),
and whether one commit can stand in for many (the slack batch), so they are
read straight from the file, read-only.

Anything in doubt answers "cannot tell", and the caller then does what it
did before: a source QGIS reads through an archive or another GDAL virtual
file system, a path the platform cannot stat or turn into a file URI, a file
SQLite cannot open. A finer answer is not worth a guess.
"""
import os
import re
import sqlite3
import string
import time
from collections import namedtuple
from contextlib import closing
from pathlib import Path

from qgis.core import QgsProviderRegistry

#: ``view``: the layer reads a view, whose order is its own. ``curves``: the
#: file registers a ``gpkg_geom_<TYPE>`` extension for the table, which the
#: GeoPackage standard requires of a writer that stores arcs in it. ``keyed``:
#: the table's key is SQLite's rowid, so its fid order is the order GDAL reads
#: it in (``_rowid_key``).
TableFacts = namedtuple("TableFacts", "view curves keyed")

#: ``path -> (stamp, {table, lower case: kind}, {tables with curves}, {tables keyed by the rowid})``.
#: Opening the file costs ~3 ms on the benchmark's 24-table GeoPackage, and one
#: click asks for several layers. Any write changes the file or its WAL, and
#: the stamp with it, so a stale answer is never used.
_SCHEMAS = {}

#: ``path -> (stamp, monotonic seconds)`` of a read that failed: tried again a
#: second later, or once the file changes. With a busy timeout, a file another
#: program held locked made every mouse move wait 0.1 s for each GeoPackage
#: layer it searched -- 1.4 s a move for the route tool's 14 (code review,
#: 3.44.15 and 4.2.3). The read now gives up at once: a locked file only means
#: "cannot tell", and the caller reads the layer whole, as before.
_FAILED = {}
_RETRY_AFTER_S = 1.0


def _source(layer):
    """``(path, table)`` of an OGR GeoPackage layer read from a plain file, else None."""
    parts = QgsProviderRegistry.instance().decodeUri("ogr", layer.source())
    path, table = parts.get("path"), parts.get("layerName")
    if not path or not table or parts.get("vsiPrefix") or not os.path.isabs(path):
        return None
    return path, table


def _stamp(path):
    """Size and modification time of the file and its WAL, or None when they cannot be read."""
    stamp = []
    for name in (path, path + "-wal"):
        try:
            status = os.stat(name)
        except FileNotFoundError:
            stamp.append(None)
        except OSError:
            return None
        else:
            stamp.append((status.st_mtime_ns, status.st_size))
    return tuple(stamp)


def _rowid_key(db, table):
    """The name of ``table``'s key column when it is SQLite's rowid itself, else None.

    The GeoPackage standard's key, ``INTEGER PRIMARY KEY``: GDAL reads a table
    in rowid order and takes such a key for the fid, so fid order is the
    order of a whole read. Any other key -- ``INT``, ``INTEGER ... DESC``,
    TEXT, two columns -- has an index of its own (origin 'pk'), and then
    GDAL reads in rowid order while its fid is the key, or takes the rowid
    for the fid while the key is something else (round-4 review: sorted by
    fid, a snap's tie went to another route). GDAL opens such tables without
    a word.
    """
    try:
        keys = [(name, kind) for name, kind, primary in db.execute(
            "SELECT name, type, pk FROM pragma_table_info(?)", (table,)) if primary]
        if len(keys) != 1 or (keys[0][1] or "").strip().upper() != "INTEGER":
            return None
        if db.execute("SELECT 1 FROM pragma_index_list(?) WHERE origin = 'pk'", (table,)).fetchone() is not None:
            return None
    except sqlite3.Error:
        # Whatever SQLite cannot describe here is not a key it can vouch for.
        return None
    return keys[0][0]


#: Folds a name as SQLite folds identifiers: ASCII letters only. ``str.lower()``
#: also folds "Č" into "č", making two of SQLite's tables one key (round-6 review).
_ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def _folded(name):
    """``name`` in the case SQLite compares it in."""
    return name.translate(_ASCII_LOWER)


def _schema(path):
    """``(kinds, curved, keyed)`` for the file, table names folded by ``_folded``; None when it cannot be read."""
    stamp = _stamp(path)
    known = _SCHEMAS.get(path)
    if stamp is not None and known is not None and known[0] == stamp:
        return known[1:]
    failed = _FAILED.get(path)
    if failed is not None and failed[0] == stamp and time.monotonic() - failed[1] < _RETRY_AFTER_S:
        return None
    try:
        with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=0)) as db:
            kinds = {_folded(name): kind for kind, name in db.execute(
                "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'view')")}
            curved = set()
            if "gpkg_extensions" in kinds:
                curved = {_folded(name) for (name,) in db.execute(
                    "SELECT table_name FROM gpkg_extensions "
                    "WHERE extension_name LIKE 'gpkg_geom_%' AND table_name IS NOT NULL")}
            keyed = set()
            if "gpkg_geometry_columns" in kinds:
                # Tables only: SQLite compiles a view to describe it, and a view
                # calling one of GDAL's SQL functions, or reading a table that
                # is gone, fails to compile here and took the whole file down
                # with it (round-5 review). A view is read whole anyway.
                keyed = {_folded(name) for (name,) in db.execute(
                    "SELECT table_name FROM gpkg_geometry_columns WHERE table_name IS NOT NULL").fetchall()
                    if kinds.get(_folded(name)) == "table" and _rowid_key(db, name) is not None}
    except (OSError, ValueError, sqlite3.Error):
        _FAILED[path] = (stamp, time.monotonic())
        return None
    _FAILED.pop(path, None)
    if stamp is not None:
        _SCHEMAS[path] = (stamp, kinds, curved, keyed)
    return kinds, curved, keyed


def layer_file(layer):
    """``(path, table)`` of an OGR GeoPackage layer read from a plain file, else None."""
    return _source(layer)


def file_stamp(path):
    """The stamp ``table_facts`` keys its cache by: size and modification time of the file and its WAL.

    None when they cannot be read. Equal stamps mean the file's tables are the
    ones ``table_facts`` last read; a write to the file changes it.
    """
    return _stamp(path)


def table_facts(layer):
    """The ``TableFacts`` of a GeoPackage layer's table, or None when the file cannot tell."""
    source = _source(layer)
    if source is None:
        return None
    path, table = source
    schema = _schema(path)
    if schema is None:
        return None
    kinds, curved, keyed = schema
    name = _folded(table)
    kind = kinds.get(name)
    if kind is None:
        return None
    return TableFacts(view=kind == "view", curves=name in curved, keyed=name in keyed)


#: GDAL's own triggers on a feature table: its R-tree's and its feature count's.
_GDAL_TRIGGERS = ("rtree_", "trigger_insert_feature_count_", "trigger_delete_feature_count_")


def database_answers_writes(layer):
    """True unless the file shows nothing of its own that refuses or follows a write to the table.

    A trigger other than GDAL's own, a UNIQUE index besides the key, a CHECK,
    a foreign key, or a NOT NULL column besides the key and the geometry; or
    a file that cannot tell. Any of them can refuse one row of a batch, or
    count writes the batch makes fewer of.
    """
    source = _source(layer)
    if source is None:
        return True
    path, table = source
    try:
        with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=0.1)) as db:
            row = db.execute("SELECT type, sql FROM sqlite_master WHERE type IN ('table', 'view') "
                             "AND name = ? COLLATE NOCASE", (table,)).fetchone()
            if row is None or row[0] != "table" or re.search(r"\b(CHECK|REFERENCES)\b", (row[1] or "").upper()):
                return True
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' "
                                      "AND tbl_name = ? COLLATE NOCASE", (table,)):
                if not name.lower().startswith(_GDAL_TRIGGERS):
                    return True
            if any(unique and origin != "pk" for unique, origin in db.execute(
                    'SELECT "unique", origin FROM pragma_index_list(?)', (table,))):
                return True
            geometry = {name.lower() for (name,) in db.execute(
                "SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ? COLLATE NOCASE", (table,))}
            if any(notnull and not key and name.lower() not in geometry for name, notnull, key in db.execute(
                    'SELECT name, "notnull", pk FROM pragma_table_info(?)', (table,))):
                return True
            if db.execute("SELECT 1 FROM pragma_foreign_key_list(?)", (table,)).fetchone() is not None:
                return True
    except (OSError, ValueError, sqlite3.Error):
        return True
    return False


#: The first bytes of the WKB of a row holding one line: a LineString, or a
#: MultiLineString of one part, in either byte order, 2D, Z, M or ZM -- the ISO
#: codes GDAL writes (3.22.16 to 4.2.3). Anything else is read regardless.
_ONE_LINE = tuple(bytes.fromhex(code) for code in (
    "0102000000", "01EA030000", "01D2070000", "01BA0B0000",
    "0000000002", "00000003EA", "00000007D2", "0000000BBA"))
_ONE_PART = tuple(bytes.fromhex(code) for code in (
    "010500000001000000", "01ED03000001000000", "01D507000001000000", "01BD0B000001000000",
    "000000000500000001", "00000003ED00000001", "00000007D500000001", "0000000BBD00000001"))

#: Where a GeoPackage geometry's WKB starts, by its header's flags byte: after
#: the 8-byte header and the envelope the flags name (none, 32, 48, 48 or 64
#: bytes), in either byte order. An empty or extended geometry has none.
_WKB_START = ("CASE WHEN substr(g, 1, 3) = X'475000' THEN CASE substr(g, 4, 1) "
              "WHEN X'00' THEN 9 WHEN X'01' THEN 9 WHEN X'02' THEN 41 WHEN X'03' THEN 41 "
              "WHEN X'04' THEN 57 WHEN X'05' THEN 57 WHEN X'06' THEN 57 WHEN X'07' THEN 57 "
              "WHEN X'08' THEN 73 WHEN X'09' THEN 73 END END")


#: ``rows_near``'s answer: ``ids``, the fids to read, and ``first``, the table's lowest fid.
RowsNear = namedtuple("RowsNear", "ids first")


def rows_near(layer, box):
    """A GeoPackage table's rows that can hold a line within ``box`` (a superset, read from the file), and its lowest fid.

    None where more than a quarter of the table's rows would come back: reading
    a row by its fid costs 3-4 times reading it in a scan (round-4 review), so
    the caller's whole read is then the cheaper one. The rows are counted in
    the file itself -- GDAL's own count where it keeps one, a count of the rows
    otherwise -- not by QGIS, whose count lags what another program does to the
    file (round-5 review), and the pass over the rows stops as soon as the
    quarter is passed. The lowest fid tells the caller where the table starts:
    GDAL's keys count on from the highest ever written, so a table whose rows
    were deleted and written again starts far from 1 (round-6 review).

    For a search that must not miss a row OGR's box request drops (WP4 PF-7,
    branch 13): the rows the table's own R-tree stores within ``box``, and
    every row that is not one line. OGR answers a box request with the R-tree
    and then a geometry test of its own, which GEOS fails on a one-vertex part
    on QGIS 3.22; reading the R-tree directly skips that. The box GDAL stores
    is grown part by part from each part's first vertex, so a NaN there leaves
    that bound NaN -- SQLite stores 0 -- and the box of a multi-part row can
    miss its good parts (code reviews, 3.22.16 to 4.2.3); a row holding one
    line has a box that holds every finite vertex after a finite first one,
    and SQLite's R-tree rounds its boxes outward. So only a row of one line is
    left to the R-tree, told by the WKB its blob starts with; any other row,
    of two parts or more or of anything else, is read regardless, as it was
    before. The rounding is outward only within float32's range: a bound
    beyond +/-3.4e38 is stored as an infinity on the inside of the box (round-4
    review), which a query ``utils.spatial.indexable_box`` accepts never
    reaches.

    None when it cannot tell -- not a plain file, no R-tree, a key that is not
    SQLite's rowid (``_rowid_key``; a TEXT key's strings made lay cable raise,
    round-4 review), a locked or an unreadable file -- and the caller reads
    the layer whole, as before. Only what the file holds: an edit buffer is
    the caller's to rule out.
    """
    source = _source(layer)
    if source is None:
        return None
    path, table = source
    try:
        with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=0)) as db:
            row = db.execute("SELECT table_name, column_name FROM gpkg_geometry_columns "
                             "WHERE table_name = ? COLLATE NOCASE", (table,)).fetchone()
            if row is None:
                return None
            name, column = row
            rtree = "rtree_%s_%s" % (name, column)
            if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                          (rtree,)).fetchone() is None:
                return None
            key = _rowid_key(db, name)
            if key is None:
                return None

            def quoted(identifier):
                return '"%s"' % identifier.replace('"', '""')
            # The names come from the file's own gpkg_geometry_columns and table
            # info, quoted as identifiers; the box and the codes are parameters.
            ids = {fid for (fid,) in db.execute(
                "SELECT id FROM %s WHERE minx <= ? AND maxx >= ? AND miny <= ? AND maxy >= ?"  # nosec B608
                % quoted(rtree), (box.xMaximum(), box.xMinimum(), box.yMaximum(), box.yMinimum()))}
            count = None
            if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'gpkg_ogr_contents'").fetchone():
                kept = db.execute("SELECT feature_count FROM gpkg_ogr_contents WHERE table_name = ? COLLATE NOCASE",
                                  (name,)).fetchone()
                count = kept[0] if kept is not None else None
            if count is None:
                count = db.execute("SELECT count(*) FROM %s" % quoted(name)).fetchone()[0]  # nosec B608
            room = count // 4 - len(ids)
            if room < 0:
                return None
            others = [fid for (fid,) in db.execute(
                "SELECT id FROM (SELECT %s AS id, %s AS g FROM %s WHERE %s IS NOT NULL) "  # nosec B608
                "WHERE coalesce(NOT (substr(g, %s, 5) IN (%s) OR substr(g, %s, 9) IN (%s)), 1) LIMIT ?"
                % (quoted(key), quoted(column), quoted(name), quoted(column),
                   _WKB_START, ",".join("?" * len(_ONE_LINE)), _WKB_START, ",".join("?" * len(_ONE_PART))),
                _ONE_LINE + _ONE_PART + (room + 1,))]
            if len(others) > room:
                return None
            ids.update(others)
            first = db.execute("SELECT min(%s) FROM %s" % (quoted(key), quoted(name))).fetchone()[0]  # nosec B608
    except (OSError, ValueError, sqlite3.Error):
        return None
    return RowsNear(ids, 1 if first is None else first)


__all__ = ['RowsNear', 'TableFacts', 'database_answers_writes', 'rows_near', 'table_facts']
