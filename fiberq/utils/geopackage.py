"""What a GeoPackage says about one of its tables, read from the file itself.

WP4 task 4.1, item PF-4. QGIS reports a GeoPackage layer's declared geometry
type and fields, not what the file holds beyond them: whether a LINESTRING
table holds arcs, or whether the "table" is a view. Both decide whether a box
query answers exactly as the whole-layer scan it replaces (see
``utils.spatial.features_near``), so they are read straight from the file,
read-only.

Anything in doubt answers "cannot tell", and the caller then does what it
did before: a source QGIS reads through an archive or another GDAL virtual
file system, a path the platform cannot stat or turn into a file URI, a file
SQLite cannot open. A finer answer is not worth a guess.
"""
import os
import sqlite3
from collections import namedtuple
from contextlib import closing
from pathlib import Path

from qgis.core import QgsProviderRegistry

#: ``view``: the layer reads a view, whose order is its own. ``curves``: the
#: file registers a ``gpkg_geom_<TYPE>`` extension for the table, which the
#: GeoPackage standard requires of a writer that stores arcs in it.
TableFacts = namedtuple("TableFacts", "view curves")

#: ``path -> (stamp, {table, lower case: kind}, {tables with curves})``.
#: Opening the file costs ~3 ms on the benchmark's 24-table GeoPackage, and one
#: click asks for several layers. Any write changes the file or its WAL, and
#: the stamp with it, so a stale answer is never used.
_SCHEMAS = {}


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


def _schema(path):
    """``(kinds, curved)`` for the file, or None when it cannot be read."""
    stamp = _stamp(path)
    known = _SCHEMAS.get(path)
    if stamp is not None and known is not None and known[0] == stamp:
        return known[1], known[2]
    try:
        with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=0.1)) as db:
            kinds = {name.lower(): kind for kind, name in db.execute(
                "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'view')")}
            curved = set()
            if "gpkg_extensions" in kinds:
                curved = {name.lower() for (name,) in db.execute(
                    "SELECT table_name FROM gpkg_extensions "
                    "WHERE extension_name LIKE 'gpkg_geom_%' AND table_name IS NOT NULL")}
    except (OSError, ValueError, sqlite3.Error):
        return None
    if stamp is not None:
        _SCHEMAS[path] = (stamp, kinds, curved)
    return kinds, curved


def table_facts(layer):
    """The ``TableFacts`` of a GeoPackage layer's table, or None when the file cannot tell."""
    source = _source(layer)
    if source is None:
        return None
    path, table = source
    schema = _schema(path)
    if schema is None:
        return None
    kinds, curved = schema
    kind = kinds.get(table.lower())
    if kind is None:
        return None
    return TableFacts(view=kind == "view", curves=table.lower() in curved)


__all__ = ['TableFacts', 'table_facts']
