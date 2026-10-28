"""Whether a path can serve as the auto-save GeoPackage, and what to call a table in it.

A pure-data module, like :mod:`fiberq.core.interchange_fields` and
:mod:`fiberq.models.schema`: no QGIS imports, so it is testable without a
runtime.

Two jobs, both of which exist because the auto-save feature used to find out too
late, or not at all:

**The pre-flight.** :func:`gpkg_target_problem` answers *why* a path will not
work before the user is asked anything. A project carried to another machine
keeps the GeoPackage path it was saved with, and that path is now a drive that
is not mounted; today the first layer QGIS tries to write fails, then the next,
and the next, each with its own raw OGR error. One sentence naming the path is
more useful than twelve naming OGR.

It returns a **code**, never a sentence. This module cannot translate -- it
imports nothing from Qt -- and a message built here would be the one string in
the plugin a volunteer could not reach. The caller turns the code into words.

The answer is advisory and the caller must still check each layer's result:
:func:`os.access` does not see Windows ACLs, a file another program holds open,
a full disk, or a filesystem that goes read-only between the question and the
write.

**The table name.** :func:`table_name_for` stops the overwrite that cost
features until now. GeoPackage table names come from the layer's own name with
the punctuation flattened, so renaming "Poles" to "Poles 2024" and then adding a
new layer called "Poles" aims the new one at the table the old one still owns.
The writer is asked to overwrite that table, answers ``NoError``, and the old
features are gone -- measured: three features in, one feature out, no exception
and no warning anywhere.

The rule is: a layer already living in this GeoPackage keeps the table it is
already using, and anything else gets a name nothing else has claimed --
where "claimed" is decided case-insensitively, because SQLite and OGR both
resolve a table name that way and "poles" is the spelling ogr2ogr, "Package
layers" and a PostGIS dump produce. Every name the file holds counts, a table
no GeoPackage registry lists included.

**The plan.** That rule also kept tables nothing reads any more. Restart QGIS,
make the layers again and save into the same file, and the old Poles is still
there, used by no layer, while the new one goes to Poles_2 -- and a reader that
opens the file by table name gets the old one. :func:`plan_tables` therefore
looks at the whole save first and may *offer* such a table: the caller asks the
user whether to replace it, and Replace destroys it.

So a table is offered only when the whole situation is understood, by an
allow-list rather than a search for readers -- two reviews kept finding readers
a search had missed. The file is one FiberQ reads completely, with no view, no
virtual table beyond its R*Tree indexes and no QGIS project stored in it
(:func:`read_contents`); the table is a real vector or attribute table it
registers, of exactly the layer's name; and every layer of the project is one
whose reading :func:`tables_read` understands -- another file it reads by the
GDAL driver that opens that file, which the caller names, this module asking
GDAL nothing. Anything else and nothing is offered: each layer goes beside the
tables of its name, as U6 did. And the file and the project must not change
while the question is open (:func:`file_identity`), nor a free name be taken
before it is written (:func:`free_at_write`). A path whose ".." QGIS 3.22
reads as another file than the system does is resolved where it is chosen
(:func:`unambiguous`), so that what is planned and what is written are one
file.
"""
import os
import re
import sqlite3
from collections import namedtuple
from contextlib import closing
from urllib.parse import parse_qsl, quote

#: The first 16 bytes of any SQLite database.
SQLITE_MAGIC = b"SQLite format 3\x00"

#: Bytes 68-72 of a GeoPackage carry this application id. GDAL writes "GP10"
#: for the 1.0/1.1 spec and "GPKG" for 1.2 and later, and both are in the wild.
GPKG_APPLICATION_IDS = (b"GPKG", b"GP10", b"GP11")

#: The two tables every GeoPackage holds, whatever its header says: a file
#: rebuilt from an SQL dump carries application_id 0, and GDAL opens it with a
#: warning (measured on 3.22.16 and 4.2.3).
GPKG_CORE_TABLES = frozenset({"gpkg_contents", "gpkg_spatial_ref_sys"})

#: Every code :func:`gpkg_target_problem` can return. Kept as a set so a caller
#: that maps codes to sentences can be tested for completeness.
PROBLEMS = frozenset({
    "empty",
    "is_directory",
    "no_directory",
    "directory_not_writable",
    "not_writable",
    "not_a_geopackage",
})

#: Tables a GeoPackage keeps for QGIS and FiberQ themselves. Never offered for
#: replacement, and never handed to a layer: a layer called "layer_styles"
#: written there would leave QGIS no table to keep its styles in.
RESERVED_TABLES = frozenset({"layer_styles", "_fiberq_metadata", "qgis_projects"})

#: The GeoPackage standard's own tables and GDAL's spatial indexes, and
#: SQLite's. Never offered for replacement either.
RESERVED_PREFIXES = ("gpkg_", "rtree_", "sqlite_")

#: The ``gpkg_contents`` kinds a layer may be written over: vector tables and
#: attribute tables. A tiles table, or a kind an extension defines, named like
#: a layer is never offered -- the writer cannot replace it ("table already
#: exists") -- and the layer gets a free name beside it.
OFFERABLE_KINDS = frozenset({"features", "attributes"})

#: Providers whose layers read no table of a GeoPackage file, valid ones: a
#: memory layer; a database server (PostgreSQL, SQL Server, Oracle, SAP HANA,
#: Db2); a web service (WFS, OGC API Features, WCS, ArcGIS REST, SensorThings);
#: QGIS's own readers of a text file (delimited text) and of a GPX file. And two
#: kinds of layer with no provider and no source at all, which the caller passes
#: under these names: an annotation layer, whose items live in the project, and
#: a group layer, whose members are layers of the project in their own right.
READS_NOTHING = frozenset({
    "annotation", "arcgisfeatureserver", "arcgisimageserver", "arcgismapserver", "db2",
    "delimitedtext", "gpx", "group", "hana", "memory", "mssql", "oapif", "oracle", "postgres",
    "postgresraster", "sensorthings", "wcs", "wfs",
})

#: Providers that read a web service -- and also a local SQLite file: given
#: "type=mbtiles", a WMS layer opens a GeoPackage as MBTiles and is valid
#: (measured on 3.22.16 and 4.2.3), and the vector tile providers read MBTiles
#: too. They read nothing of the file only when every url is http(s).
WEB_PROVIDERS = frozenset({"arcgisvectortileservice", "vectortile", "wms", "xyzvectortiles"})

#: GDAL drivers that read one file -- or that file and its sidecars of the same
#: name, a shapefile's .shx and .dbf, a raster's world file -- and never
#: another dataset. A layer reading another file reads nothing of this one
#: only when GDAL opens that file with one of these, or with one of
#: :data:`SQLITE_DRIVERS` (:func:`_reads_only_itself`). Not here, and so never
#: understood: a VRT (VRT, OGR_VRT), a GDAL tile index (GTI, GDAL 3.9 and
#: later), a GDAL pipeline (GDALG, 3.11 and later) and the STAC drivers, which
#: read the datasets they name; a MapInfo .tab, whose seamless table names
#: others; MBTiles; and every driver this list does not name. The driver is
#: what GDAL opens the file with, never the file's name: GDAL picks a driver by
#: what a file holds, and an OGR VRT saved as .geojson, .csv or .shp is
#: OGR_VRT to it (measured on GDAL 3.4.1, 3.8.4, 3.10.3 and 3.12.2), a tile
#: index saved as .tif or .json GTI (3.10.3, 3.12.2), a pipeline saved as
#: .json GDALG (3.12.2) -- each reading a table of this file.
SINGLE_FILE_DRIVERS = frozenset({
    "AAIGrid", "CSV", "DXF", "ESRI Shapefile", "FlatGeobuf", "GML", "GPX", "GTiff", "GeoJSON", "GeoJSONSeq",
    "JP2OpenJPEG", "JPEG", "KML", "LIBKML", "PNG",
})

#: The drivers of another SQLite file -- a GeoPackage, a SpatiaLite database.
#: Understood only when that file's virtual tables read nothing but itself
#: (:data:`SAME_FILE_MODULES`).
SQLITE_DRIVERS = frozenset({"GPKG", "SQLite"})

#: Virtual table modules that read only the database they are in: R*Tree,
#: full-text search, and SpatiaLite's own (its spatial index, elementary
#: geometries, nearest neighbours). Another SQLite file holding any other --
#: GDAL's VirtualOGR, which a QGIS layer reads through under QGIS's default
#: settings (measured on 3.22.16 and 4.2.3), or SpatiaLite's readers of
#: shapefiles and text files -- is not understood.
SAME_FILE_MODULES = frozenset({
    "fts3", "fts4", "fts5", "rtree", "rtree_i32", "virtualelementary", "virtualknn", "virtualknn2",
    "virtualspatialindex",
})

#: The only virtual tables a target may hold for a table of it to be offered:
#: the R*Tree spatial indexes GDAL makes (measured: a GeoPackage QGIS writes on
#: 3.22.16, 3.40.15 and 4.2.3 holds those and no view).
TARGET_MODULES = frozenset({"rtree", "rtree_i32"})

#: The module of a ``CREATE VIRTUAL TABLE`` statement, past a name in any of
#: SQLite's four quotings, or bare, and an optional schema.
_NAME = r"""(?:"(?:[^"]|"")*"|\[[^\]]*\]|`(?:[^`]|``)*`|'(?:[^']|'')*'|[^\s."'`\[(]+)"""
_VIRTUAL_TABLE = re.compile(
    rf"\s*create\s+virtual\s+table\s+(?:if\s+not\s+exists\s+)?(?:{_NAME}\s*\.\s*)?{_NAME}\s+using\s+([a-z_][a-z0-9_]*)",
    re.IGNORECASE | re.DOTALL)

#: What :func:`read_contents` finds in a GeoPackage. ``kinds`` maps each table
#: ``gpkg_contents`` registers to its ``data_type``, as stored; ``views`` holds
#: the casefolded names of its views and ``tables`` its tables' names as stored,
#: from ``sqlite_master``; ``names`` every name ``sqlite_master`` and
#: ``gpkg_contents`` hold, casefolded -- of tables, views, indexes, triggers and
#: the tables those belong to; ``projects`` the rows of ``qgis_projects`` (0
#: without one, None when they cannot be counted); ``modules`` the casefolded
#: modules of its virtual tables (None when one cannot be told).
Contents = namedtuple("Contents", "kinds views tables names projects modules")

#: A file that is not there yet: it holds nothing.
NOTHING = Contents({}, frozenset(), frozenset(), frozenset(), 0, frozenset())


def gpkg_target_problem(path):
    """Why ``path`` cannot be used as the auto-save GeoPackage, or None.

    Args:
        path: The path to check. ``None`` and ``""`` both answer ``"empty"``.

    Returns:
        One of :data:`PROBLEMS`, or None when nothing is visibly wrong. None is
        not a promise that the write will succeed -- see the module docstring.
    """
    if not path:
        return "empty"

    path = str(path)
    if os.path.isdir(path):
        return "is_directory"

    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        # The usual cause: a project carried to another machine, or a drive
        # that is no longer mounted.
        return "no_directory"

    if not os.path.exists(path):
        # It is allowed not to exist yet; the first save creates it. What
        # matters is whether this is somewhere we may create a file.
        return None if os.access(folder, os.W_OK) else "directory_not_writable"

    if not os.access(path, os.W_OK):
        return "not_writable"

    if not is_geopackage(path):
        return "not_a_geopackage"

    return None


def is_geopackage(path):
    """True when ``path`` is a SQLite database a GeoPackage writer can work in.

    Cheap and deliberately shallow: enough to catch a path that points at a
    .qgs project, a shapefile or last week's spreadsheet, which is what the
    file dialog's filter does not prevent. The header's application id says
    GeoPackage for a file GDAL wrote; one rebuilt from an SQL dump has 0 there,
    and GDAL opens it all the same, so then the standard's own two tables
    decide. A SQLite file whose tables cannot be read is let through: reading
    them is the next step, and it stops the save with the reason.
    """
    try:
        with open(path, "rb") as handle:
            header = handle.read(72)
    except OSError:
        return False
    if not header.startswith(SQLITE_MAGIC):
        return False
    if header[68:72] in GPKG_APPLICATION_IDS:
        return True
    try:
        with closing(_read_only(path)) as conn:
            names = {str(row[0]).casefold() for row in
                     conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.Error:
        return True
    return GPKG_CORE_TABLES <= names


def _uri(path):
    """A read-only sqlite URI for the file ``path`` names, symlinks and ".." resolved.

    Percent-encoded, because this is a URI: an unescaped "#" ends the path and
    a "?" starts the query, so a GeoPackage called "pro#ject.gpkg" silently
    read as having no tables at all. quote() leaves "/" alone, so the path still
    resolves. And resolved, not made absolute: "a/link/../fu8.gpkg", with link a
    symlink to b/sub, is b/fu8.gpkg to the operating system, while
    os.path.abspath takes the ".." away first and says a/fu8.gpkg, another file
    (see :func:`unambiguous` for the readers that do the same).
    """
    return "file:" + quote(os.path.realpath(str(path))) + "?mode=ro"


def _read_only(path):
    """A read-only connection to ``path``, through :func:`_uri`."""
    return sqlite3.connect(_uri(path), uri=True)


def existing_tables(path):
    """The table names already in ``path``, or an empty set if it has none.

    Read straight from ``gpkg_contents`` rather than through OGR, so this stays
    free of QGIS. A file that is not a readable GeoPackage answers with an
    empty set: the caller is choosing a name, and "nothing is taken" is the
    right answer for a file that does not exist yet.
    """
    if not path or not os.path.isfile(path):
        return set()
    try:
        # closing(): a connection's own ``with`` ends a transaction, never the
        # connection, which Python 3.13 (QGIS 4) reports as "unclosed database".
        with closing(_read_only(path)) as conn:
            rows = conn.execute("SELECT table_name FROM gpkg_contents").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[0]) for row in rows}


def styled_tables(path):
    """The table names ``layer_styles`` in ``path`` holds styles for, as stored.

    Empty when the file, or its ``layer_styles``, is not there. A table QGIS
    or GDAL dropped keeps its rows here: no GDAL measured removes them, when a
    table is overwritten or deleted (3.4.1, 3.8.4, 3.10.3, 3.12.2).
    """
    if not path or not os.path.isfile(path):
        return set()
    try:
        with closing(_read_only(path)) as conn:
            rows = conn.execute("SELECT DISTINCT f_table_name FROM layer_styles").fetchall()
    except sqlite3.Error:
        # No layer_styles is the usual reason: then there is nothing to clear.
        return set()
    return {str(row[0]) for row in rows if row[0] is not None}


def _modules(rows):
    """The casefolded modules of the virtual tables among ``sqlite_master`` ``rows`` ``(type, sql)``.

    None when a virtual table's statement cannot be taken apart: its module is
    then unknown, and an unknown module is never trusted.
    """
    modules = set()
    for kind, sql in rows:
        text = str(sql or "")
        if kind != "table" or not re.match(r"\s*create\s+virtual\s", text, re.IGNORECASE):
            continue
        found = _VIRTUAL_TABLE.match(text)
        if found is None:
            return None
        modules.add(found.group(1).casefold())
    return frozenset(modules)


def read_contents(path):
    """The :data:`Contents` of the GeoPackage at ``path``, for a save to plan with.

    :data:`NOTHING` for a file that is not there yet: a new file holds
    nothing. A file that is there and cannot be read -- held by another
    program, not a GeoPackage, damaged -- raises :class:`sqlite3.Error` rather
    than answer with nothing, unlike :func:`existing_tables`: a plan made from
    an empty answer would hand out, and offer to replace, names the file
    already has.
    """
    if not path or not os.path.isfile(path):
        return NOTHING
    with closing(_read_only(path)) as conn:
        master = [(str(kind), str(name), str(table), sql) for kind, name, table, sql in
                  conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master")]
        kinds = {str(name): str(kind) for name, kind in
                 conn.execute("SELECT table_name, data_type FROM gpkg_contents")}
        projects = 0
        if any(kind == "table" and name.casefold() == "qgis_projects" for kind, name, _table, _sql in master):
            try:
                projects = conn.execute('SELECT count(*) FROM "qgis_projects"').fetchone()[0]
            except sqlite3.Error:
                # Another QGIS project may be stored there; unread, it counts as one.
                projects = None
    views = frozenset(name.casefold() for kind, name, _table, _sql in master if kind == "view")
    tables = frozenset(name for kind, name, _table, _sql in master if kind == "table")
    names = frozenset(each.casefold() for _kind, name, table, _sql in master for each in (name, table))
    names |= frozenset(name.casefold() for name in kinds)
    return Contents(kinds, views, tables, names, projects, _modules((kind, sql) for kind, _n, _t, sql in master))


def table_state(path, table):
    """What tells ``table`` in ``path`` apart from a table of the same name made after it.

    ``(rowid, rootpage, sql)`` of its ``sqlite_master`` row and its
    ``last_change`` in ``gpkg_contents``, found case-insensitively as SQLite
    and OGR find a table; None when ``path`` has no such table. A write over
    the table that fails part-way may have dropped it, or dropped it and made a
    new one holding part of the layer: either way the answer changes. Raises
    :class:`sqlite3.Error` when the file cannot be read.
    """
    if not path or not os.path.isfile(path):
        return None
    with closing(_read_only(path)) as conn:
        row = conn.execute("SELECT rowid, rootpage, sql FROM sqlite_master "
                           "WHERE type = 'table' AND name = ? COLLATE NOCASE", (str(table),)).fetchone()
        if row is None:
            return None
        change = conn.execute("SELECT last_change FROM gpkg_contents WHERE table_name = ? COLLATE NOCASE",
                              (str(table),)).fetchone()
    return tuple(row) + ((change[0] if change else None),)


def file_identity(path):
    """What a plan rests on of the file at ``path``, to be compared once the user has answered.

    Its real path, device, file number, size and modification time, its
    SQLite header -- whose change counter and schema cookie move with every
    write in rollback mode -- and the size and time of its write-ahead log,
    which takes a write in WAL mode. Equal before and after the question: the
    same file, as it was. A file that is not there, or cannot be looked at,
    answers what stopped it, which compares equal only to the same answer.

    An empty log is no log: reading a file in WAL mode makes one when there is
    none (measured on 3.40.15: the plan's own read did), and it holds nothing.
    """
    real = os.path.realpath(str(path))
    try:
        stat = os.stat(real)
        with open(real, "rb") as handle:
            header = handle.read(100)
    except OSError as exc:
        return real, "unreadable", exc.errno
    try:
        log = os.stat(real + "-wal")
        log = (log.st_size, log.st_mtime_ns) if log.st_size else None
    except FileNotFoundError:
        log = None
    except OSError as exc:
        log = ("unreadable", exc.errno)
    return real, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, header, log


def sqlite_fold(name):
    """``name`` as SQLite and OGR compare a table name: ASCII letters folded, nothing else."""
    return "".join(character.lower() if character.isascii() else character for character in str(name))


def same_file(path, gpkg_path):
    """True when ``path`` and ``gpkg_path`` name the same file.

    Resolved first (:func:`os.path.realpath`, as the operating system resolves
    symlinks and ".."), and then, when the two still differ and both exist,
    compared as files (:func:`os.path.samefile`: the device and the file's
    number, which Windows answers as well). One file has many spellings -- a
    symlinked folder, a hard link, a mapped drive and its UNC path, another
    case on a case-insensitive disk -- and a layer reading it through one of
    them reads it all the same. (A ".." that QGIS 3.22 reads another way is
    :func:`unambiguous`'s matter.)
    """
    if not path or not gpkg_path:
        return False
    first, second = str(path), str(gpkg_path)
    try:
        if os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second)):
            return True
        return os.path.samefile(first, second)
    except (OSError, ValueError):
        # One of them is not there, or is not a path at all (a NUL in it):
        # nothing says it is this file.
        return False


def _ambiguous(path):
    """True when ``path`` names one file to the system and another to a reader that takes ".." away first."""
    text = str(path)
    try:
        return os.path.realpath(os.path.normpath(os.path.abspath(text))) != os.path.realpath(text)
    except (OSError, ValueError):
        return True


def unambiguous(path):
    """``path``, or -- when its ".." would be read two ways -- the file it names to the system.

    "a/link/../fu8.gpkg", with link a symlink to b/sub, is b/fu8.gpkg to the
    system, to Python and to QGIS 3.40 and later, and a/fu8.gpkg to QGIS
    3.22.16, whose SQLite and GDAL take the ".." away before they follow the
    link (measured: its writer wrote into a/fu8.gpkg, a layer opened a/fu8.gpkg,
    and so did Python's own sqlite3). Such a path is resolved once, where it is
    chosen, so that the plan, the writer, the clean-ups and the layers all use
    the same file; any other path keeps the spelling it was chosen with.
    """
    if not path:
        return path
    return os.path.realpath(str(path)) if _ambiguous(path) else path


def is_reserved(table):
    """True for a table no layer is ever written over: see :data:`RESERVED_TABLES`."""
    folded = str(table).casefold()
    return folded in RESERVED_TABLES or folded.startswith(RESERVED_PREFIXES)


def flatten_name(name, fallback="layer"):
    """A layer's name reduced to what a GeoPackage table may be called."""
    flattened = "".join(
        character if character.isascii() and (character.isalnum() or character == "_") else "_"
        for character in str(name or ""))
    while "__" in flattened:
        flattened = flattened.replace("__", "_")
    return flattened.strip("_") or fallback


def table_in_use(source, gpkg_path):
    """The table ``source`` already reads from in ``gpkg_path``, or None.

    ``source`` is a layer's data-source URI. A layer that auto-save converted
    earlier reads ``<path>|layername=<table>``, and keeping that table is what
    stops a second save inventing Poles_2, Poles_3 and so on for the same layer.
    """
    if not source or not gpkg_path:
        return None
    head, separator, tail = str(source).partition("|")
    if not separator:
        return None
    if not same_file(head, gpkg_path):
        return None
    for part in tail.split("|"):
        if part.startswith("layername="):
            return part[len("layername="):] or None
    return None


def free_name(base, taken):
    """``base``, or ``base_2``, ``base_3`` ... -- the first not in ``taken`` (casefolded names)."""
    if base.casefold() not in taken:
        return base
    counter = 2
    while f"{base}_{counter}".casefold() in taken:
        counter += 1
    return f"{base}_{counter}"


def table_name_for(layer_name, source, gpkg_path, fallback="layer", also_taken=()):
    """The GeoPackage table ``layer_name`` should be written to.

    The table it already occupies, if it occupies one in this file; otherwise a
    flattened form of its name, suffixed until nothing else has claimed it.

    Args:
        also_taken: Names already handed out during this run but not yet on
            disk. "Save all layers" writes a whole project in one pass, so two
            layers that flatten to the same name have to be separated before
            either reaches the file.

    Raises:
        sqlite3.Error: When the file is there and its tables cannot be read
            (:func:`read_contents`). Read as empty, every name in it would look
            free, and the writer replaces a table it is given the name of.
    """
    already = table_in_use(source, gpkg_path)
    if already:
        return already

    # Folded, because neither thing this name has to get past is
    # case-sensitive. SQLite resolves a table name case-insensitively EVEN WHEN
    # QUOTED, and OGR resolves a GeoPackage layer name the same way -- while the
    # gpkg_contents row this reads is compared case-sensitively, so the two
    # disagree. Measured on GDAL 3.10.3 against a file holding "poles":
    #
    #     existing_tables          -> {'poles'}
    #     table_name_for('Poles')  -> 'Poles'          (thought it was free)
    #     SELECT count(*) FROM "Poles"             -> 3   (same table)
    #     gpkg_contents WHERE table_name='Poles'   -> 0   (different row)
    #
    # and writing one feature to "Poles" dropped the three in "poles" and
    # answered NoError, with a green "All layers saved to" on screen. Lowercase
    # is not an exotic spelling either: it is what ogr2ogr, QGIS's own "Package
    # layers" and a PostGIS dump all produce, so this is the ordinary shape of
    # a GeoPackage someone else prepared.
    #
    # Every name the file holds, registered or not -- a table another program
    # keeps out of gpkg_contents is overwritten all the same -- and the
    # tables QGIS and FiberQ keep for themselves. The chosen name keeps its own
    # case: only the collision test folds.
    taken = set(read_contents(gpkg_path).names) | set(RESERVED_TABLES)
    taken |= {str(name).casefold() for name in also_taken}
    return free_name(flatten_name(layer_name, fallback), taken)


def _plain_local_file(path):
    """True when ``path`` names a file on this machine, spelled as a plain path, and it is there.

    Not a URL, not a GDAL virtual file system path ("/vsizip/...") or a
    driver's own syntax ("GPKG:...", "PG:..."), not an inline definition
    ("<OGRVRTDataSource>..."), not a folder -- and not a path whose ".." QGIS
    3.22 reads as another file than the system does (:func:`unambiguous`).
    """
    text = str(path or "")
    if not text or "://" in text or "<" in text or text.casefold().startswith("/vsi"):
        return False
    prefix, colon, _rest = text.partition(":")
    if colon and len(prefix) > 1 and not any(separator in prefix for separator in "/\\"):
        return False
    return os.path.isfile(text) and not _ambiguous(text)


def _virtual_modules(path):
    """:func:`_modules` of the SQLite file at ``path``. Raises :class:`sqlite3.Error` when it cannot be read."""
    with closing(_read_only(path)) as conn:
        return _modules(conn.execute("SELECT type, sql FROM sqlite_master").fetchall())


def _sqlite_reads_only_itself(path):
    """True when ``path`` is a SQLite file whose virtual tables read only that file (:data:`SAME_FILE_MODULES`).

    SQLite itself cannot reach into another file, and GDAL does only through a
    VirtualOGR table. A file that does not start as a SQLite file does -- a
    GeoPackage GDAL reads inside a .zip -- is not looked into, and not
    understood.
    """
    real = os.path.realpath(str(path))
    try:
        with open(real, "rb") as handle:
            head = handle.read(len(SQLITE_MAGIC))
    except OSError:
        return False
    if head != SQLITE_MAGIC:
        return False
    try:
        modules = _virtual_modules(real)
    except sqlite3.Error:
        return False
    return modules is not None and modules <= SAME_FILE_MODULES


def _reads_only_itself(path, identify, raster, driver=None):
    """True when another file a layer reads cannot name a table of any other file.

    Decided by the GDAL driver that opens it: ``identify``'s answer for
    ``path`` under its own name and under its real one -- GDAL picks some
    drivers by a file's name, and a link's name is not its file's -- as a
    raster dataset for a GDAL layer (``raster``) and a vector one for an OGR
    layer, which is how each provider opens it; and ``driver``, the one the
    layer's own provider says it opened the file with, when it says. Every one
    must be in :data:`SINGLE_FILE_DRIVERS`, or in :data:`SQLITE_DRIVERS` for a
    SQLite file whose virtual tables read only itself. No ``identify``, no
    driver, or any other driver: not understood.
    """
    if identify is None:
        return False
    drivers = {identify(spelling, raster) for spelling in {str(path), os.path.realpath(str(path))}}
    if driver is not None:
        drivers.add(driver)
    if not drivers <= SINGLE_FILE_DRIVERS | SQLITE_DRIVERS:
        return False
    return not drivers & SQLITE_DRIVERS or _sqlite_reads_only_itself(path)


def _names_sql(subset):
    """True when a filter is SQL rather than an expression: it says SELECT or FROM, in any case.

    Asked of a filter on another file only -- any filter on this one is not
    understood (:func:`_ogr_reads`). GDAL runs a filter on a plain file through
    its own SQL, which reads a table of any file by its path: as the filter of
    a shapefile or a GeoJSON layer, ``SELECT * FROM '<this file>'.Poles`` read
    this file's Poles (measured on 3.22.16 and 4.2.3, with GDAL 3.4.1, 3.10.3
    and 3.12.2). An expression cannot name another table there.
    """
    folded = str(subset).casefold()
    return "select" in folded or "from" in folded


def _web_only(source):
    """True when a web provider's source names only http(s) urls, and no local tile file."""
    pairs = parse_qsl(str(source), keep_blank_values=True)
    urls = [value for key, value in pairs if key.casefold() == "url"]
    types = {value.casefold() for key, value in pairs if key.casefold() == "type"}
    if not urls or types & {"mbtiles", "vtpk"}:
        return False
    return all(url.casefold().startswith(("http://", "https://")) for url in urls)


def _ogr_reads(source, gpkg_path, others, driver=None, identify=None):
    """:func:`tables_read` for an OGR source: ``<path>|layername=<table>`` and the options QGIS adds.

    QGIS keeps a filter last, after "|subset=", and it may hold a "|" itself;
    every other part before it is one option. Understood: one ``layername``, a
    ``layerid`` (of another file only: which table of this one it is, the
    source does not say) and a ``geometrytype``; and a filter on another file
    that is not SQL (:func:`_names_sql`). Not understood: a filter of any kind
    on this file -- SQLite reads another table through one that says neither
    SELECT nor FROM, ``("fid", "geom", "id") IN "Poles"`` (measured) -- an
    open option or a credential, which can make a dataset read another, and
    every option this does not know.
    """
    head, marker, subset = source.partition("|subset=")
    path, *options = head.split("|")
    layer_name = layer_id = None
    for option in options:
        key, equals, value = option.partition("=")
        if not equals:
            return None
        if key == "layername" and value and layer_name is None:
            layer_name = value
        elif key == "layerid" and layer_id is None:
            layer_id = value
        elif not (key == "geometrytype" and value.isalnum()):
            return None
    if not _plain_local_file(path):
        return None
    if same_file(path, gpkg_path):
        if marker or layer_name is None or layer_id is not None:
            return None
        return {layer_name.casefold()}
    if marker and _names_sql(subset):
        return None
    return _other_file(path, others, identify, False, driver)


def _gdal_reads(source, gpkg_path, others, identify=None):
    """:func:`tables_read` for a GDAL source: "GPKG:<path>:<table>", or a file's plain path.

    Understood: a table named in this file, and another file that reads only
    itself as a raster. Not understood: open options (after a "|"), this file
    with no table named, and any other driver's syntax.
    """
    if "|" in source:
        return None
    path, table = source, None
    if source[:5].casefold() == "gpkg:":
        path, colon, table = source[5:].rpartition(":")
        # "GPKG:C:\data\x.gpkg" splits at its drive's colon: a "table" holding
        # a path separator is the rest of that path, and no table is named.
        if not colon or not path or not table or any(separator in table for separator in "/\\"):
            return None
    if not _plain_local_file(path):
        return None
    if same_file(path, gpkg_path):
        return {table.casefold()} if table else None
    return _other_file(path, others, identify, True)


def _other_file(path, others, identify, raster, driver=None):
    """``set()`` when another file reads nothing of the target, else None; answers kept in ``others``."""
    key = (str(path), raster, driver)
    if key not in others:
        others[key] = _reads_only_itself(path, identify, raster, driver)
    return set() if others[key] else None


def tables_read(provider, source, gpkg_path, valid=True, others=None, driver=None, identify=None):
    """The tables of ``gpkg_path`` a layer reads, casefolded -- or None when FiberQ cannot tell.

    An allow-list. A valid layer of :data:`READS_NOTHING` reads nothing of it,
    and so does one of :data:`WEB_PROVIDERS` that reads only the web. A valid
    OGR or GDAL layer reading a plain local path is understood when that path
    is this file and names one table, with no filter -- it reads that table --
    or is another file that GDAL opens with a driver that reads only that file
    (:func:`_reads_only_itself`). Everything else answers None, and then
    nothing may be offered: an invalid layer of any provider, which may read
    this file once pointed back at it; a virtual or SpatiaLite layer; a URL, a
    "/vsi" path, "GPKG:" given to OGR; a filter on this file, or one that is
    SQL on another; a VRT, a tile index, a pipeline, a driver not listed; an
    option this does not know; a provider a plugin brings.

    Args:
        others: A dict this fills with what was found of other files, so that
            a project's many layers on one file look at it once.
        driver: The GDAL driver the layer's provider says it opened its file
            with -- an OGR layer's storage type -- or None when it says none.
        identify: ``identify(path, raster)``, the short name of the GDAL driver
            that opens ``path`` as a raster dataset (``raster``) or a vector
            one, or None when no driver does. The caller supplies it, this
            module importing nothing of GDAL; without it, no other file is
            understood.
    """
    if not valid:
        return None
    provider = str(provider or "").casefold()
    source = str(source or "")
    others = {} if others is None else others
    if provider in READS_NOTHING:
        return set()
    if provider in WEB_PROVIDERS:
        return set() if _web_only(source) else None
    if provider == "ogr":
        return _ogr_reads(source, gpkg_path, others, driver, identify)
    if provider == "gdal":
        return _gdal_reads(source, gpkg_path, others, identify)
    return None


def used_tables(layers, gpkg_path, identify=None):
    """The tables of ``gpkg_path`` the project's layers read, casefolded -- or None.

    None when any layer is not understood (:func:`tables_read`): then nothing
    may be offered.

    Args:
        layers: ``(provider, source)``, ``(provider, source, valid)`` or
            ``(provider, source, valid, driver)`` of every layer of the
            project, of any kind -- a raster or a virtual layer reads a table
            as surely as a vector layer does.
        identify: What names the GDAL driver of a file a layer reads that is
            not this one (:func:`tables_read`).
    """
    used, others = set(), {}
    for layer in layers:
        valid = layer[2] if len(layer) > 2 else True
        driver = layer[3] if len(layer) > 3 else None
        read = tables_read(layer[0], layer[1], gpkg_path, valid, others, driver, identify)
        if read is None:
            return None
        used |= read
    return used


def understood(contents):
    """True when a file with these :data:`Contents` is one a table of may be offered from.

    No view -- its SQL is not taken apart to find what it reads -- no virtual
    table beyond an R*Tree index, and no QGIS project stored in it, which may
    read any of its tables.
    """
    if contents.views or contents.projects != 0 or contents.modules is None:
        return False
    return contents.modules <= TARGET_MODULES


def _offerable(name, contents, used):
    """The file's spelling of the table a layer called ``name`` may be offered, or None.

    A real table, registered as a vector or attribute table, of exactly the
    layer's name as the writer takes it (OGR matches ASCII letters in either
    case, and nothing else), one of each, reserved for nothing, and read by no
    layer.
    """
    folded = sqlite_fold(name)
    registered = [stored for stored in contents.kinds if sqlite_fold(stored) == folded]
    real = [table for table in contents.tables if sqlite_fold(table) == folded]
    if len(registered) != 1 or len(real) != 1:
        return None
    stored = registered[0]
    if is_reserved(stored) or contents.kinds[stored] not in OFFERABLE_KINDS:
        return None
    if {stored.casefold(), real[0].casefold(), name.casefold()} & used:
        return None
    return stored


class TablePlan(namedtuple("TablePlan", "tables wanted kept offers replace")):
    """Where each layer of one save goes, from :func:`plan_tables`.

    ``tables`` and ``wanted`` run parallel to the layers given: the table each
    one is written to (or already lives in), and the name it would have had
    with nothing in the way. ``kept`` holds the indexes of layers that already
    live in the file. ``offers`` maps an index to the table, as the file spells
    it, that nothing reads and that has that layer's name; ``replace`` says
    whether ``tables`` writes over them or puts those layers beside them.
    """

    __slots__ = ()

    @property
    def offered(self):
        """The offered tables, in the order of the layers that want them."""
        return [self.offers[index] for index in sorted(self.offers)]

    @property
    def renamed(self):
        """Indexes of the layers written under a name other than their own."""
        return [index for index, table in enumerate(self.tables)
                if index not in self.kept and table != self.wanted[index]]


def plan_tables(layers, gpkg_path, used=None, replace=False, contents=None):
    """The table each of ``layers`` is written to, for one save into ``gpkg_path``.

    A layer already living in the file keeps its table (:func:`table_in_use`).
    Any other wants its flattened name. When nothing has that name, it gets it.
    When the situation is understood -- ``used`` known and the file
    :func:`understood` -- and an unused vector or attribute table has it
    (:func:`_offerable`), the table is *offered*: written over when
    ``replace``, otherwise kept, with the layer beside it under a free name.
    Otherwise -- a name the file holds in any way, a reserved one, one an
    earlier layer of this save took -- the layer gets a free name and nothing
    is offered.

    Args:
        layers: ``(layer name, source, fallback name)`` of each layer to write.
        used: Casefolded names of the tables the project's layers read, from
            :func:`used_tables`; None, the default, when that is not known, and
            then nothing is offered.
        replace: The user's answer, once they have given one.
        contents: The file's :data:`Contents`, when the caller has read them.

    Raises:
        sqlite3.Error: When the file has to be read here and cannot be.
    """
    contents = read_contents(gpkg_path) if contents is None else contents
    offering = used is not None and understood(contents)
    # A layer of this save that already lives in the file reads its table,
    # whatever the caller counted and wherever that layer comes in the order.
    homes = {index: table_in_use(source, gpkg_path) for index, (_name, source, _fallback) in enumerate(layers)}
    homes = {index: table for index, table in homes.items() if table}
    used = {str(name).casefold() for name in used or ()} | {table.casefold() for table in homes.values()}
    tables, wanted, kept, offers = [], [], set(homes), {}

    claimed = set()
    for index, (layer_name, source, fallback) in enumerate(layers):
        if index in homes:
            tables.append(homes[index])
            wanted.append(homes[index])
            continue
        name = flatten_name(layer_name, fallback)
        key = name.casefold()
        tables.append(None)
        wanted.append(name)
        if key in claimed:
            continue
        if key not in contents.names and key not in used and key not in RESERVED_TABLES:
            tables[index] = name
        else:
            stored = _offerable(name, contents, used) if offering else None
            if stored is None:
                continue
            offers[index] = stored
            if replace:
                tables[index] = name
        claimed.add(key)

    # A free name is found only once every layer that keeps its own name has
    # it, so that "Poles" set aside as Poles_2 cannot take the name of a layer
    # actually called Poles_2.
    taken = set(contents.names) | used | set(RESERVED_TABLES) | claimed
    for index, table in enumerate(tables):
        if table is None:
            tables[index] = free_name(wanted[index], taken)
            taken.add(tables[index].casefold())
    return TablePlan(tables, wanted, frozenset(kept), offers, bool(replace))


def free_at_write(path, plan, index):
    """The table ``plan`` gives layer ``index``, looked at again right before it is written.

    A table the layer already lives in, or the offered one the user chose to
    replace, is what it was planned as. A name the plan found free may have
    been taken since -- another program, or a layer added in the meantime --
    and the writer replaces a table whose name it is given: then the next free
    name is taken instead, beside every name the file holds and every other
    name of the plan, and ``plan.tables`` says so.

    Raises:
        sqlite3.Error: When the file cannot be read.
    """
    name = plan.tables[index]
    if index in plan.kept or (plan.replace and index in plan.offers):
        return name
    names = read_contents(path).names
    if name.casefold() not in names:
        return name
    taken = set(names) | set(RESERVED_TABLES)
    taken |= {table.casefold() for other, table in enumerate(plan.tables) if other != index}
    plan.tables[index] = free_name(plan.wanted[index], taken)
    return plan.tables[index]


__all__ = [
    "GPKG_CORE_TABLES",
    "NOTHING",
    "OFFERABLE_KINDS",
    "PROBLEMS",
    "READS_NOTHING",
    "RESERVED_PREFIXES",
    "RESERVED_TABLES",
    "SAME_FILE_MODULES",
    "SINGLE_FILE_DRIVERS",
    "SQLITE_DRIVERS",
    "TARGET_MODULES",
    "WEB_PROVIDERS",
    "Contents",
    "TablePlan",
    "existing_tables",
    "file_identity",
    "flatten_name",
    "free_at_write",
    "free_name",
    "gpkg_target_problem",
    "is_geopackage",
    "is_reserved",
    "plan_tables",
    "read_contents",
    "same_file",
    "sqlite_fold",
    "styled_tables",
    "table_in_use",
    "table_name_for",
    "table_state",
    "tables_read",
    "unambiguous",
    "understood",
    "used_tables",
]
