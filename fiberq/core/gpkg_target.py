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
already using, and anything else gets a name nothing else has claimed.
"""
import os
import sqlite3

#: The first 16 bytes of any SQLite database.
SQLITE_MAGIC = b"SQLite format 3\x00"

#: Bytes 68-72 of a GeoPackage carry this application id. GDAL writes "GP10"
#: for the 1.0/1.1 spec and "GPKG" for 1.2 and later, and both are in the wild.
GPKG_APPLICATION_IDS = (b"GPKG", b"GP10", b"GP11")

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
    """True when ``path`` looks like a GeoPackage from its first 72 bytes.

    Cheap and deliberately shallow: enough to catch a path that points at a
    .qgs project, a shapefile or last week's spreadsheet, which is what the
    file dialog's filter does not prevent.
    """
    try:
        with open(path, "rb") as handle:
            header = handle.read(72)
    except OSError:
        return False
    if not header.startswith(SQLITE_MAGIC):
        return False
    return header[68:72] in GPKG_APPLICATION_IDS


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
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            rows = conn.execute("SELECT table_name FROM gpkg_contents").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[0]) for row in rows}


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
    if os.path.normcase(os.path.abspath(head)) != os.path.normcase(os.path.abspath(str(gpkg_path))):
        return None
    for part in tail.split("|"):
        if part.startswith("layername="):
            return part[len("layername="):] or None
    return None


def table_name_for(layer_name, source, gpkg_path, fallback="layer", also_taken=()):
    """The GeoPackage table ``layer_name`` should be written to.

    The table it already occupies, if it occupies one in this file; otherwise a
    flattened form of its name, suffixed until nothing else has claimed it.

    Args:
        also_taken: Names already handed out during this run but not yet on
            disk. "Save all layers" writes a whole project in one pass, so two
            layers that flatten to the same name have to be separated before
            either reaches the file.
    """
    already = table_in_use(source, gpkg_path)
    if already:
        return already

    taken = existing_tables(gpkg_path) | set(also_taken)
    base = flatten_name(layer_name, fallback)
    if base not in taken:
        return base
    counter = 2
    while f"{base}_{counter}" in taken:
        counter += 1
    return f"{base}_{counter}"


__all__ = [
    "PROBLEMS",
    "existing_tables",
    "flatten_name",
    "gpkg_target_problem",
    "is_geopackage",
    "table_in_use",
    "table_name_for",
]
