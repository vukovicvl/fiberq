"""The auto-save pre-flight, and the table name that stops features vanishing.

Not claimed under WP4 4.2 -- an ordinary UX fix shipping in the same release
(plan item U6).

The overwrite these pin down was measured, not inferred: auto-save writes a
layer called "Poles" with three features; the user renames it and adds a new
layer, also called "Poles"; the new one is written to the same table with
``CreateOrOverwriteLayer``; the writer answers ``NoError``; the table now holds
one feature. No exception, no warning, three features gone.

No QGIS here. :mod:`fiberq.core.gpkg_target` imports nothing from Qt or QGIS so
it can be tested as plain Python, which is also why it answers with codes rather
than sentences -- a message built in a module that cannot translate would be the
one string in the plugin a volunteer could not reach.
"""
import importlib.util
import os
import pathlib
import sqlite3
from contextlib import closing

import pytest


def _load(name, relpath):
    """Load a module by path, without importing the package around it."""
    path = pathlib.Path(__file__).resolve().parent.parent / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gt = _load("gpkg_target", "fiberq/core/gpkg_target.py")


def _make_gpkg(path, tables=(), application_id=1196444487):
    """A file with a GeoPackage header ('GPKG') and the named tables in it, registered.

    Each table is made as well as registered: only a table ``sqlite_master``
    lists may be offered. SQLite keeps names starting "sqlite_" for itself, so
    those are only registered.
    """
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute(f"PRAGMA application_id = {int(application_id)}")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS gpkg_contents ("
            " table_name TEXT PRIMARY KEY, data_type TEXT, identifier TEXT,"
            " description TEXT, last_change TEXT, srs_id INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (srs_id INTEGER PRIMARY KEY)")
        for table in tables:
            conn.execute(
                "INSERT OR REPLACE INTO gpkg_contents (table_name, data_type) VALUES (?, 'features')",
                (table,))
            if not table.casefold().startswith("sqlite_"):
                quoted = table.replace('"', '""')
                conn.execute(f'CREATE TABLE IF NOT EXISTS "{quoted}" (fid INTEGER PRIMARY KEY)')
        conn.commit()
    return path


# ---------------------------------------------------------------------------
# the pre-flight
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", 0])
def test_no_target_at_all(value):
    assert gt.gpkg_target_problem(value) == "empty"


def test_a_folder_that_is_not_there(tmp_path):
    """The common one: a project carried to another machine, or an unmounted drive."""
    assert gt.gpkg_target_problem(tmp_path / "gone" / "auto.gpkg") == "no_directory"


def test_a_path_that_is_a_directory(tmp_path):
    assert gt.gpkg_target_problem(tmp_path) == "is_directory"


def test_a_file_that_does_not_exist_yet_is_fine(tmp_path):
    """The first save creates it; what matters is that the folder allows it."""
    assert gt.gpkg_target_problem(tmp_path / "new.gpkg") is None


def test_a_real_geopackage_is_fine(tmp_path):
    assert gt.gpkg_target_problem(_make_gpkg(tmp_path / "auto.gpkg")) is None


def test_something_that_is_not_a_geopackage(tmp_path):
    """The file dialog's filter does not stop the user picking last week's notes."""
    other = tmp_path / "notes.gpkg"
    other.write_bytes(b"this is not a database")
    assert gt.gpkg_target_problem(other) == "not_a_geopackage"


def test_a_qgis_project_named_gpkg_is_not_a_geopackage(tmp_path):
    decoy = tmp_path / "project.gpkg"
    decoy.write_bytes(b"<!DOCTYPE qgis><qgis version='3.44'></qgis>")
    assert gt.gpkg_target_problem(decoy) == "not_a_geopackage"


def test_a_geopackage_whose_header_says_0_is_a_geopackage(tmp_path):
    """v1.6.0 QA Q18, third round (review t1): a GeoPackage rebuilt from an SQL
    dump has application_id 0 in its header, and GDAL opens it with only a
    warning. The pre-flight read the header alone and refused it -- and Save
    all now runs the pre-flight on a file that is there, so it would no longer
    save into a file it saved into before this fix."""
    target = _make_gpkg(tmp_path / "dumped.gpkg", ["Poles"], application_id=0)

    assert gt.is_geopackage(target)
    assert gt.gpkg_target_problem(target) is None


def test_a_sqlite_file_without_the_geopackage_tables_is_still_refused(tmp_path):
    other = tmp_path / "cache.gpkg"
    with closing(sqlite3.connect(str(other))) as conn:
        conn.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_data BLOB)")
        conn.commit()

    assert not gt.is_geopackage(other)
    assert gt.gpkg_target_problem(other) == "not_a_geopackage"


def test_a_file_that_cannot_be_written(tmp_path, monkeypatch):
    """Patched rather than chmod-ed, because CI runs as root and root ignores
    the write bit -- a skipif here would mean this branch is never tested."""
    target = _make_gpkg(tmp_path / "auto.gpkg")
    monkeypatch.setattr(gt.os, "access", lambda path, mode: False)

    assert gt.gpkg_target_problem(target) == "not_writable"


def test_a_folder_that_cannot_be_written(tmp_path, monkeypatch):
    folder = tmp_path / "locked"
    folder.mkdir()
    monkeypatch.setattr(gt.os, "access", lambda path, mode: False)

    assert gt.gpkg_target_problem(folder / "auto.gpkg") == "directory_not_writable"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the write bit")
def test_a_read_only_file_for_real(tmp_path):
    """The same thing without the patch, for anyone running as themselves."""
    target = _make_gpkg(tmp_path / "auto.gpkg")
    target.chmod(0o444)
    try:
        assert gt.gpkg_target_problem(target) == "not_writable"
    finally:
        target.chmod(0o644)


@pytest.mark.parametrize("name", [
    "pro#ject.gpkg",      # '#' ends the path in a sqlite URI
    "pro?ject.gpkg",      # '?' starts the query
    "pro%20ject.gpkg",    # a literal %XX the URI parser would decode
    "pro ject.gpkg",      # a space, for contrast: this one always worked
])
def test_a_path_a_uri_would_mangle_still_reads_its_tables(tmp_path, name):
    """The read is done through a sqlite URI, so the path has to be escaped.

    Unescaped, a GeoPackage called "pro#ject.gpkg" read as having no tables,
    so a name already in the file was handed out again -- the exact overwrite
    this module exists to prevent, defeated by a character in a filename.
    """
    target = _make_gpkg(tmp_path / name, ["Poles"])

    assert gt.existing_tables(target) == {"Poles"}
    assert gt.table_name_for("Poles", "Point?crs=EPSG:3857", str(target)) == "Poles_2"


# ---------------------------------------------------------------------------
# f001/f005: a name is claimed case-insensitively, because the store is
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stored, wanted", [
    ("poles", "Poles"),     # what ogr2ogr, "Package layers" and PostGIS produce
    ("POLES", "Poles"),
    ("Poles", "poles"),
    ("PoLeS", "pOlEs"),
])
def test_a_table_differing_only_in_case_is_already_claimed(tmp_path, stored, wanted):
    """The guard compared names case-sensitively; SQLite and OGR do not.

    Measured on GDAL 3.10.3 against a real GeoPackage holding "poles" with three
    features: ``table_name_for("Poles")`` answered "Poles", the writer answered
    NoError, and the three features were gone -- because ``SELECT ... FROM
    "Poles"`` resolves to the same table EVEN QUOTED, while the gpkg_contents
    row compare that found "nothing claimed" does not.
    """
    target = _make_gpkg(tmp_path / f"{stored}.gpkg", [stored])

    chosen = gt.table_name_for(wanted, "Point?crs=EPSG:3857", str(target))

    assert chosen.casefold() != stored.casefold(), (
        f"{wanted!r} must not be written over {stored!r}; got {chosen!r}")
    assert chosen == f"{wanted}_2"


def test_the_chosen_name_keeps_its_own_case(tmp_path):
    """Only the collision test folds -- a new table is still spelled as asked."""
    target = _make_gpkg(tmp_path / "empty.gpkg", [])

    assert gt.table_name_for("Poles", "Point?crs=EPSG:3857", str(target)) == "Poles"
    assert gt.table_name_for("poles", "Point?crs=EPSG:3857", str(target)) == "poles"


def test_a_name_handed_out_this_run_is_claimed_case_insensitively(tmp_path):
    """also_taken has the same problem: Save all writes a project in one pass."""
    target = _make_gpkg(tmp_path / "run.gpkg", [])

    chosen = gt.table_name_for("Poles", "Point?crs=EPSG:3857", str(target),
                               also_taken=("poles",))

    assert chosen == "Poles_2", chosen


def test_the_suffix_search_also_folds(tmp_path):
    """Poles_2 taken in another case must not be handed out as free either."""
    target = _make_gpkg(tmp_path / "suffix.gpkg", ["poles", "POLES_2"])

    assert gt.table_name_for("Poles", "Point?crs=EPSG:3857", str(target)) == "Poles_3"


def test_every_code_it_returns_is_declared():
    """So a caller mapping codes to sentences can be checked for completeness."""
    import ast
    module_path = pathlib.Path(__file__).resolve().parent.parent / "fiberq/core/gpkg_target.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    returned = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "gpkg_target_problem":
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Return) or inner.value is None:
                continue
            # Walked, not matched directly: one code is returned from a
            # conditional expression, which a Constant-only check would miss.
            for leaf in ast.walk(inner.value):
                if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str):
                    returned.add(leaf.value)
    assert returned == set(gt.PROBLEMS), (returned, set(gt.PROBLEMS))


# ---------------------------------------------------------------------------
# the table name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("given, expected", [
    ("Poles", "Poles"),
    ("Optical slacks", "Optical_slacks"),
    ("Poles 2024!", "Poles_2024"),
    ("---", "layer"),
    ("", "layer"),
    ("Stubovi/Trasa", "Stubovi_Trasa"),
])
def test_a_layer_name_becomes_a_table_name(given, expected):
    assert gt.flatten_name(given) == expected


def test_a_fresh_layer_gets_its_own_name(tmp_path):
    target = _make_gpkg(tmp_path / "auto.gpkg", ["Routes"])
    assert gt.table_name_for("Poles", "Point?crs=EPSG:3857", str(target)) == "Poles"


def test_a_name_already_in_the_file_is_not_reused(tmp_path):
    """The measured bug: this is what used to overwrite the old layer."""
    target = _make_gpkg(tmp_path / "auto.gpkg", ["Poles"])
    assert gt.table_name_for("Poles", "Point?crs=EPSG:3857", str(target)) == "Poles_2"


def test_it_keeps_counting_past_a_taken_suffix(tmp_path):
    target = _make_gpkg(tmp_path / "auto.gpkg", ["Poles", "Poles_2", "Poles_3"])
    assert gt.table_name_for("Poles", "Point?crs=EPSG:3857", str(target)) == "Poles_4"


def test_a_layer_already_in_this_file_keeps_its_table(tmp_path):
    """Otherwise every save would invent Poles_2, Poles_3 for the same layer."""
    target = _make_gpkg(tmp_path / "auto.gpkg", ["Poles"])
    source = f"{target}|layername=Poles"
    assert gt.table_name_for("Poles", source, str(target)) == "Poles"


def test_a_layer_from_a_different_geopackage_does_not_keep_its_table(tmp_path):
    target = _make_gpkg(tmp_path / "auto.gpkg", ["Poles"])
    elsewhere = f"{tmp_path / 'other.gpkg'}|layername=Poles"
    assert gt.table_name_for("Poles", elsewhere, str(target)) == "Poles_2"


def test_a_renamed_layer_still_keeps_its_own_table(tmp_path):
    """Renaming in the legend must not orphan the table it already owns."""
    target = _make_gpkg(tmp_path / "auto.gpkg", ["Poles"])
    source = f"{target}|layername=Poles"
    assert gt.table_name_for("Poles 2024", source, str(target)) == "Poles"


def test_a_table_no_registry_lists_is_not_written_over(tmp_path):
    """v1.6.0 QA Q18, third round (review n5d): another program's table, kept
    out of gpkg_contents, named like the layer. The writer replaces it all the
    same, so its name is taken."""
    target = _make_gpkg(tmp_path / "auto.gpkg", ["Poles"])
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('CREATE TABLE "Notes" (nid INTEGER PRIMARY KEY, note TEXT)')
        conn.commit()

    assert gt.table_name_for("Notes", "Point?crs=EPSG:3857", str(target)) == "Notes_2"


def test_a_name_qgis_keeps_for_itself_is_not_handed_out_in_a_new_file(tmp_path):
    """A layer called layer_styles would take the table QGIS keeps styles in."""
    assert gt.table_name_for("layer_styles", "Point?crs=EPSG:3857", str(tmp_path / "new.gpkg")) == "layer_styles_2"


def test_tables_of_a_file_that_is_not_there(tmp_path):
    assert gt.existing_tables(tmp_path / "nothing.gpkg") == set()
    assert gt.existing_tables("") == set()


def test_tables_of_a_file_that_is_not_a_geopackage(tmp_path):
    other = tmp_path / "notes.gpkg"
    other.write_bytes(b"not a database")
    assert gt.existing_tables(other) == set()


def test_reading_the_tables_does_not_create_the_file(tmp_path):
    missing = tmp_path / "absent.gpkg"
    gt.existing_tables(missing)
    assert not missing.exists(), "the check must not create what it is checking"


# ---------------------------------------------------------------------------
# v1.6.0 QA: the read closes the file it opened
# ---------------------------------------------------------------------------

def test_reading_the_table_names_closes_the_file(tmp_path, monkeypatch):
    """A sqlite3 connection's own ``with`` ends a transaction, never the connection.

    Python 3.13 (QGIS 4) reports one left open as "unclosed database" in the
    Python warning log -- found in the v1.6.0 QA's suite logs on 4.2.
    """
    target = _make_gpkg(tmp_path / "t.gpkg", ["Poles"])
    closed = []

    class Tracked:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False    # sqlite3.Connection's own exit commits; it never closes

        def execute(self, *args):
            return self.conn.execute(*args)

        def close(self):
            closed.append(True)
            self.conn.close()

    class Sqlite:
        Error = sqlite3.Error

        @staticmethod
        def connect(*args, **kwargs):
            return Tracked(sqlite3.connect(*args, **kwargs))

    monkeypatch.setattr(gt, "sqlite3", Sqlite)

    assert gt.existing_tables(target) == {"Poles"}
    assert closed == [True]


# ---------------------------------------------------------------------------
# v1.6.0 QA Q18: what a save plans before it writes
# ---------------------------------------------------------------------------
#
# After a restart the maintainer made Poles, Manholes and Scratch A again and
# saved into the file the first session had saved them to. U6's rule kept the
# old tables -- read by no layer any more -- and wrote Poles_2, Manholes_2 and
# Scratch_A_2 beside them without a word. The plan now finds those tables and
# offers them; a table some layer reads is still never offered.

SCRATCH = "Point?crs=EPSG:3857"

#: The maintainer's second session: the same three layers, all in memory.
REDO = [("Poles", SCRATCH, "layer_1"), ("Manholes", SCRATCH, "layer_2"),
        ("Scratch A", SCRATCH, "layer_3")]


def test_the_redo_offers_the_tables_no_layer_uses(tmp_path):
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", [
        "Poles", "Manholes", "Scratch_A", "Unrelated", "layer_styles", "_fiberq_metadata"]))
    used = gt.used_tables([("memory", SCRATCH, True)] * 3, target)

    keep = gt.plan_tables(REDO, target, used)
    replace = gt.plan_tables(REDO, target, used, replace=True)

    assert used == set(), "memory layers read nothing of the file"
    assert keep.offered == ["Poles", "Manholes", "Scratch_A"]
    assert keep.tables == ["Poles_2", "Manholes_2", "Scratch_A_2"], "Keep is the 5721d15 behaviour"
    assert keep.renamed == [0, 1, 2]
    assert replace.offered == keep.offered
    assert replace.tables == ["Poles", "Manholes", "Scratch_A"]
    assert replace.renamed == []


def test_nothing_is_offered_unless_what_the_project_reads_is_known(tmp_path):
    """plan_tables' default: a caller that does not say what the project reads gets no offer."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], target, replace=True)

    assert plan.offers == {}
    assert plan.tables == ["Poles_2"]


def test_a_table_a_layer_reads_is_never_offered(tmp_path):
    """The rename case U6 exists for: "Poles 2024" still reads the table Poles."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    renamed = f"{target}|layername=Poles"
    layers = [("Poles 2024", renamed, "layer_1"), ("Poles", SCRATCH, "layer_2")]
    used = gt.used_tables([("ogr", renamed), ("memory", SCRATCH)], target)

    for replace in (False, True):
        plan = gt.plan_tables(layers, target, used, replace)
        assert plan.offers == {}
        assert plan.kept == {0}
        assert plan.tables == ["Poles", "Poles_2"]
        assert plan.renamed == [1]


def test_a_table_a_layer_of_this_save_lives_in_is_never_offered(tmp_path):
    """Even when the caller counted nothing as used, and the layer comes last."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    layers = [("Poles", SCRATCH, "layer_1"), ("Poles 2024", f"{target}|layername=Poles", "layer_2")]

    plan = gt.plan_tables(layers, target, used=(), replace=True)

    assert plan.offers == {}
    assert plan.tables == ["Poles_2", "Poles"]


def test_a_table_read_under_another_case_counts_as_read(tmp_path):
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    used = gt.used_tables([("ogr", f"{target}|layername=POLES")], target)

    assert used == {"poles"}
    assert gt.plan_tables([("Poles", SCRATCH, "layer_1")], target, used, True).offers == {}


@pytest.mark.parametrize("table, layer", [
    ("layer_styles", "layer_styles"),
    ("qgis_projects", "qgis projects"),
    ("gpkg_spatial_ref_sys", "gpkg spatial ref sys"),
    ("rtree_Poles_geom", "rtree Poles geom"),
    ("sqlite_sequence", "sqlite_sequence"),
])
def test_a_table_kept_for_qgis_or_the_format_is_never_offered(tmp_path, table, layer):
    target = str(_make_gpkg(tmp_path / "t.gpkg", [table]))

    plan = gt.plan_tables([(layer, SCRATCH, "layer_1")], target, set(), replace=True)

    assert plan.offers == {}
    assert plan.tables == [f"{table}_2"]


def test_a_reserved_name_is_not_handed_out_in_a_new_file(tmp_path):
    """A layer called layer_styles would take the table QGIS keeps styles in."""
    plan = gt.plan_tables([("layer_styles", SCRATCH, "layer_1")], str(tmp_path / "new.gpkg"), set())

    assert plan.tables == ["layer_styles_2"]


def test_a_table_is_offered_once_however_many_layers_want_it(tmp_path):
    """"Poles" and "Poles!" flatten alike; only the first may take the old table."""
    target = str(_make_gpkg(tmp_path / "t.gpkg", ["Poles"]))
    layers = [("Poles", SCRATCH, "layer_1"), ("Poles!", SCRATCH, "layer_2")]

    keep = gt.plan_tables(layers, target, set())
    replace = gt.plan_tables(layers, target, set(), replace=True)

    assert keep.offered == replace.offered == ["Poles"]
    assert keep.tables == ["Poles_2", "Poles_3"]
    assert replace.tables == ["Poles", "Poles_2"]


def test_a_layer_keeps_its_own_name_before_others_are_set_aside(tmp_path):
    """Poles kept beside the old table must not take the name of a layer called Poles_2."""
    target = str(_make_gpkg(tmp_path / "t.gpkg", ["Poles"]))

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1"), ("Poles_2", SCRATCH, "layer_2")], target, set())

    assert plan.tables == ["Poles_3", "Poles_2"]
    assert plan.renamed == [0]


def test_an_offer_keeps_the_files_spelling_and_the_layer_its_own(tmp_path):
    target = str(_make_gpkg(tmp_path / "t.gpkg", ["poles"]))

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], target, set(), replace=True)

    assert plan.offered == ["poles"]
    assert plan.tables == ["Poles"]
    assert plan.renamed == []


def test_a_name_sqlite_keeps_apart_is_not_offered(tmp_path):
    """casefold() takes the Kelvin sign for K; SQLite and OGR do not, so the
    writer would not replace that table -- offering it would be a false promise."""
    target = str(_make_gpkg(tmp_path / "t.gpkg", ["Kabel"]))

    plan = gt.plan_tables([("Kabel", SCRATCH, "layer_1")], target, set(), replace=True)

    assert plan.offers == {}
    assert plan.tables == ["Kabel_2"]


def test_a_new_file_offers_nothing(tmp_path):
    plan = gt.plan_tables(REDO, str(tmp_path / "new.gpkg"), set(), replace=True)

    assert plan.offers == {}
    assert plan.tables == ["Poles", "Manholes", "Scratch_A"]
    assert plan.renamed == []


def test_a_relative_source_is_the_same_file(tmp_path, monkeypatch):
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path)

    assert gt.used_tables([("ogr", "./sub/../fu8.gpkg|layername=Poles")], str(target)) == {"poles"}


def test_the_styles_a_file_holds_are_read_as_stored(tmp_path):
    target = _make_gpkg(tmp_path / "t.gpkg", ["Poles"])
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("CREATE TABLE layer_styles (id INTEGER PRIMARY KEY, f_table_name TEXT, styleName TEXT)")
        conn.executemany("INSERT INTO layer_styles (f_table_name, styleName) VALUES (?, ?)",
                         [("Poles", "default"), ("Poles", "other"), ("gone", "default")])
        conn.commit()

    assert gt.styled_tables(target) == {"Poles", "gone"}
    assert gt.styled_tables(_make_gpkg(tmp_path / "plain.gpkg", ["Poles"])) == set()
    missing = tmp_path / "missing.gpkg"
    assert gt.styled_tables(missing) == set()
    assert not missing.exists()


def test_a_free_name_skips_every_taken_spelling():
    assert gt.free_name("Poles", set()) == "Poles"
    assert gt.free_name("Poles", {"poles", "poles_2"}) == "Poles_3"


# ---------------------------------------------------------------------------
# v1.6.0 QA Q18, second round: never wrong in the unsafe direction
# ---------------------------------------------------------------------------
#
# The plan decides which tables Replace destroys, under "No layer of this
# project uses them". The review measured four ways it was wrong in the unsafe
# direction: a layer reading the file through another spelling of its path, a
# layer whose file is not there, a layer reading a view, and a file whose
# tables could not be read -- each planned as "no layer uses it" -- and one
# where the table was not one the writer can replace (tiles).

def _spellings(tmp_path):
    """The target, and the same file through a symlinked folder and a hard link."""
    real = tmp_path / "real"
    real.mkdir()
    target = _make_gpkg(real / "fu8.gpkg", ["Poles", "Routes"])
    link = tmp_path / "link"
    os.symlink(str(real), str(link))
    alias = real / "alias.gpkg"
    os.link(str(target), str(alias))
    return str(target), str(link / "fu8.gpkg"), str(alias)


def test_the_same_file_under_another_spelling_is_the_same_file(tmp_path):
    target, through_link, hard_link = _spellings(tmp_path)

    assert gt.same_file(through_link, target)
    assert gt.same_file(hard_link, target)
    assert not gt.same_file(str(_make_gpkg(tmp_path / "other.gpkg")), target)
    assert not gt.same_file(str(tmp_path / "missing.gpkg"), target)
    assert not gt.same_file("bad\0path", target)


@pytest.mark.parametrize("spelling", ["symlink", "hardlink"])
def test_a_table_read_through_another_spelling_is_used(tmp_path, spelling):
    """Measured on this fix's first version: compared as strings, Poles looked
    unused, was offered, and Replace wrote over the data the layer reads
    (review p12, p2b)."""
    target, through_link, hard_link = _spellings(tmp_path)
    path = through_link if spelling == "symlink" else hard_link
    source = f"{path}|layername=Poles"

    used = gt.used_tables([("ogr", source), ("memory", SCRATCH)], target)
    plan = gt.plan_tables([("Poles 2024", source, "layer_1"), ("Poles", SCRATCH, "layer_2")],
                          target, used, replace=True)

    assert used == {"poles"}
    assert plan.offers == {}
    assert plan.kept == {0}, "the layer reading it already lives in the file"
    assert plan.tables == ["Poles", "Poles_2"]


def test_a_layer_named_like_the_table_it_reads_through_a_link_keeps_it(tmp_path):
    """Review p15/p2: offered as unused, Replace had the writer read the table
    it was dropping -- "poles" came back empty."""
    target, through_link, _hard_link = _spellings(tmp_path)
    source = f"{through_link}|layername=Poles"
    used = gt.used_tables([("ogr", source)], target)

    plan = gt.plan_tables([("Poles", source, "layer_1")], target, used, replace=True)

    assert plan.offers == {}
    assert plan.kept == {0}
    assert gt.table_in_use(source, target) == "Poles"


def test_a_layer_moved_to_a_new_drive_is_folded_into_a_new_name_not_offered(tmp_path):
    """Review p14, p3: an unavailable layer -- its folder moved, its drive not
    mounted -- counted as reading nothing, so its table was offered."""
    (tmp_path / "new-mount").mkdir()
    target = str(_make_gpkg(tmp_path / "new-mount" / "fu8.gpkg", ["Poles"]))
    unavailable = f"{tmp_path / 'old-mount' / 'fu8.gpkg'}|layername=Poles"
    used = gt.used_tables([("ogr", unavailable, False), ("memory", SCRATCH)], target)

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], target, used, replace=True)

    assert used is None
    assert plan.offers == {}
    assert plan.tables == ["Poles_2"]


def _with_view(path, view, over):
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{over}" (fid INTEGER PRIMARY KEY, id INTEGER)')
        conn.execute(f'CREATE VIEW "{view}" AS SELECT fid FROM "{over}"')
        conn.execute("INSERT INTO gpkg_contents (table_name, data_type) VALUES (?, 'features')", (view,))
        conn.commit()


def test_a_layer_reading_a_view_offers_nothing(tmp_path):
    """Review p4b: a view's base tables are not taken apart, so a file with a
    view offers no table at all."""
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles", "Routes"])
    _with_view(target, "poles_view", "Poles")

    used = gt.used_tables([("ogr", f"{target}|layername=poles_view")], str(target))
    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(target), used, replace=True)

    assert used == {"poles_view"}
    assert plan.offers == {}
    assert plan.tables == ["Poles_2"]


def test_a_view_named_like_a_layer_is_not_offered(tmp_path):
    target = _make_gpkg(tmp_path / "fu8.gpkg", [])
    _with_view(target, "Poles", "base")

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(target), set(), replace=True)

    assert plan.offers == {}
    assert plan.tables == ["Poles_2"]


@pytest.mark.parametrize("kind, offered", [
    ("features", True), ("attributes", True), ("tiles", False), ("2d-gridded-coverage", False),
])
def test_only_a_vector_or_attribute_table_is_offered(tmp_path, kind, offered):
    """Review p9: a tiles table named like a layer was offered, and the writer
    could not replace it ("table already exists")."""
    target = _make_gpkg(tmp_path / "fu8.gpkg", [])
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('CREATE TABLE "Poles" (fid INTEGER PRIMARY KEY)')
        conn.execute("INSERT INTO gpkg_contents (table_name, data_type) VALUES ('Poles', ?)", (kind,))
        conn.commit()

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(target), set(), replace=True)

    assert (plan.offers == {0: "Poles"}) is offered
    assert plan.tables == (["Poles"] if offered else ["Poles_2"])


def test_what_a_file_holds_is_read_with_kinds_views_names_and_projects(tmp_path):
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    _with_view(target, "Poles_View", "base")
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('CREATE TABLE "Notes" (nid INTEGER PRIMARY KEY)')
        conn.execute('CREATE INDEX "Notes_by_nid" ON "Notes" (nid)')
        conn.execute("CREATE VIRTUAL TABLE rtree_Poles_geom USING rtree(id, minx, maxx, miny, maxy)")
        conn.commit()

    contents = gt.read_contents(target)

    assert contents.kinds == {"Poles": "features", "Poles_View": "features"}
    assert contents.views == {"poles_view"}
    assert {"Poles", "base", "Notes", "gpkg_contents", "rtree_Poles_geom"} <= contents.tables
    assert {"poles", "poles_view", "base", "notes", "notes_by_nid", "rtree_poles_geom_node"} <= contents.names
    assert contents.projects == 0
    assert contents.modules == {"rtree"}
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("CREATE TABLE qgis_projects (name TEXT PRIMARY KEY, metadata BLOB, content BLOB)")
        conn.execute("INSERT INTO qgis_projects VALUES ('survey', '{}', x'00')")
        conn.commit()
    assert gt.read_contents(target).projects == 1
    assert gt.read_contents(tmp_path / "new.gpkg") == gt.NOTHING
    assert not (tmp_path / "new.gpkg").exists()


def test_a_file_whose_tables_cannot_be_read_is_not_read_as_empty(tmp_path):
    """Review p6b: existing_tables answers an empty set for a file it cannot
    read -- right for a name in a new file, wrong for a plan, which then
    offered nothing and handed out names the file already had."""
    notes = tmp_path / "notes.gpkg"
    notes.write_bytes(b"not a database at all, and long enough to have a header" * 4)

    with pytest.raises(sqlite3.Error):
        gt.read_contents(notes)
    with pytest.raises(sqlite3.Error):
        gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(notes), set(), replace=True)
    with pytest.raises(sqlite3.Error):
        gt.table_name_for("Poles", SCRATCH, str(notes))
    assert gt.existing_tables(notes) == set(), "U6's own reader keeps its contract"


def test_a_file_held_by_another_program_is_not_read_as_empty(tmp_path, monkeypatch):
    """Locked for writing, as another program's transaction holds it (review p6b)."""
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    connect = sqlite3.connect
    # Without the wait sqlite gives a lock by default: five seconds a read.
    monkeypatch.setattr(gt.sqlite3, "connect", lambda *args, **kwargs: connect(*args, **dict(kwargs, timeout=0)))
    holder = connect(str(target), isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(sqlite3.OperationalError):
            gt.read_contents(target)
        with pytest.raises(sqlite3.OperationalError):
            gt.table_name_for("Poles", SCRATCH, str(target))
    finally:
        holder.execute("ROLLBACK")
        holder.close()


def test_a_tables_state_tells_it_from_a_table_made_after_it(tmp_path):
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("UPDATE gpkg_contents SET last_change = '2026-10-01T10:00:00.000Z'")
        conn.commit()

    first = gt.table_state(target, "poles")
    assert first is not None
    assert gt.table_state(target, "Poles") == first, "found as SQLite finds it, in either case"
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('DROP TABLE "Poles"')
        conn.execute('CREATE TABLE "Poles" (fid INTEGER PRIMARY KEY, id INTEGER)')
        conn.execute("UPDATE gpkg_contents SET last_change = '2026-10-28T10:00:00.000Z'")
        conn.commit()
    assert gt.table_state(target, "Poles") not in (None, first)
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('DROP TABLE "Poles"')
        conn.commit()
    assert gt.table_state(target, "Poles") is None


# ---------------------------------------------------------------------------
# v1.6.0 QA Q18, third round: a table is offered only when all is understood
# ---------------------------------------------------------------------------
#
# Two rounds of review kept finding ways a table can be read that the plan
# had not counted: a subquery in a filter, a virtual layer on a hard link,
# "GPKG:" given to OGR, a VRT, a table no registry lists, an invalid layer whose
# old file is there, a QGIS project stored in the file. A search for readers
# does not end, so the plan now offers a table only when it understands the
# whole situation, by an allow-list -- the file, the table and every layer of
# the project -- and otherwise offers nothing: each layer goes beside the
# tables of its name, as U6 did, and no data is ever lost.

def _virtual(path, name, statement):
    """A virtual table's row in ``sqlite_master``, whose module need not be there to be read."""
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute("PRAGMA writable_schema = ON")
        conn.execute("INSERT INTO sqlite_master (type, name, tbl_name, rootpage, sql) VALUES ('table', ?, ?, 0, ?)",
                     (name, name, statement))
        conn.commit()


@pytest.fixture
def identify():
    """GDAL's own answer, asked as the plugin asks it (export_manager._identify).

    The short name of the driver that opens a file -- as a raster dataset for a
    GDAL layer, a vector one for an OGR layer -- or None. No QGIS here: GDAL's
    bindings come with every QGIS, and without them these tests skip.
    """
    gdal = pytest.importorskip("osgeo.gdal")

    def driver(path, raster=False):
        found = gdal.IdentifyDriverEx(str(path), gdal.OF_RASTER if raster else gdal.OF_VECTOR)
        return found.ShortName if found is not None else None

    return driver


@pytest.mark.parametrize("provider, source, valid, expected", [
    # Read nothing of a GeoPackage, however they are set up.
    ("memory", SCRATCH, True, set()),
    ("postgres", "dbname='x' table=\"Poles\" (geom)", True, set()),
    ("WFS", "typename='poles' url='https://example.org/wfs'", True, set()),
    ("delimitedtext", "file:///data/poles.csv?type=csv&xField=x&yField=y", True, set()),
    ("annotation", "", True, set()),
    ("group", "", True, set()),
    # The web -- but a WMS layer reads a GeoPackage as MBTiles, valid.
    ("wms", "type=xyz&url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19", True, set()),
    ("xyzvectortiles", "type=xyz&url=https://example.org/%7Bz%7D/%7Bx%7D/%7By%7D.pbf", True, set()),
    ("wms", "type=mbtiles&url=file://{gpkg}", True, None),
    ("wms", "type=xyz&url=file:///tiles/%7Bz%7D/%7Bx%7D/%7By%7D.png", True, None),
    ("mbtilesvectortiles", "type=mbtiles&url={gpkg}", True, None),
    # This file, one table named.
    ("ogr", "{gpkg}|layername=Poles", True, {"poles"}),
    ("ogr", "{gpkg}|layername=Poles|geometrytype=Point", True, {"poles"}),
    ("gdal", "GPKG:{gpkg}:Routes", True, {"routes"}),
    # This file, and which table it reads is not certain: any filter. SQLite
    # reads another table through one that says neither SELECT nor FROM.
    ("ogr", "{gpkg}|layername=Poles|subset=\"id\" > 1", True, None),
    ("ogr", "{gpkg}|layername=Poles|subset=", True, None),
    ("ogr", "{gpkg}|layername=Manholes|subset=(\"fid\", \"geom\", \"id\") IN \"Poles\"", True, None),
    ("ogr", "{gpkg}|layername=Manholes|subset=(\"fid\", \"geom\", \"id\") IN main.\"Poles\"", True, None),
    ("ogr", "{gpkg}|layername=Manholes|subset=NOT (\"fid\", \"geom\", \"id\") IN \"Poles\"", True, None),
    ("ogr", "{gpkg}|layername=Poles|subset=\"id\" IN \"Picked\"", True, None),
    ("ogr", "{gpkg}|layername=Manholes|subset=\"id\" IN (SELECT \"id\" FROM \"Poles\")", True, None),
    ("ogr", "{gpkg}|layername=Manholes|subset=select * from Poles", True, None),
    ("ogr", "{gpkg}|subset=SELECT * FROM \"Poles\"", True, None),
    ("ogr", "{gpkg}|layerid=1", True, None),
    ("ogr", "{gpkg}", True, None),
    ("ogr", "{gpkg}|layername=Poles|layerid=0", True, None),
    ("ogr", "{gpkg}|layername=Poles|layername=Routes", True, None),
    ("ogr", "{gpkg}|layername=Poles|LAYERNAME=Routes", True, None),
    ("ogr", "{gpkg}|layername=Poles|option:LIST_ALL_TABLES=NO", True, None),
    ("ogr", "{gpkg}|layername=Poles|credential:KEY=value", True, None),
    ("ogr", "{gpkg}|layername=Poles|uniqueGeometryType=yes", True, None),
    ("ogr", "GPKG:{gpkg}:Poles", True, None),
    ("gdal", "GPKG:{gpkg}:Routes|option:USE_TILE_EXTENT=YES", True, None),
    ("gdal", "{gpkg}", True, None),
    ("gdal", "GPKG:{gpkg}", True, None),
    # Another GeoPackage: nothing of this one, filtered or not -- unless the
    # filter is SQL, which GDAL's own SQL runs against any file it names.
    ("ogr", "{other}|layername=Poles", True, set()),
    ("ogr", "{other}|layerid=0", True, set()),
    ("gdal", "GPKG:{other}:Poles", True, set()),
    ("ogr", "{other}|layername=Poles|subset=\"id\" > 1", True, set()),
    ("ogr", "{other}|layername=Poles|subset=\"id\" IN \"Poles\"", True, set()),
    ("ogr", "{other}|layername=Poles|subset=\"id\" IN (SELECT 1 FROM \"x\")", True, None),
    ("ogr", "{other}|layername=Poles|subset=SELECT * FROM '{gpkg}'.Poles", True, None),
    ("ogr", "{other}|layername=Poles|option:PRELUDE_STATEMENTS=ATTACH 'x' AS y", True, None),
    # Not a plain local file, or not a provider this knows.
    ("ogr", "/vsizip/{other}.zip/poles.shp", True, None),
    ("ogr", "https://example.org/poles.geojson", True, None),
    ("ogr", "PG:dbname=x|layername=Poles", True, None),
    ("virtual", "?layer=ogr:{quoted}%7Clayername%3DPoles:Poles:UTF-8&query=SELECT%20*", True, None),
    ("spatialite", "dbname='{gpkg}' table=\"Poles\" (geom)", True, None),
    ("", "", True, None),
    ("someplugin", "{gpkg}", True, None),
    # Invalid, of any provider.
    ("ogr", "{gpkg}|layername=Poles", False, None),
    ("memory", SCRATCH, False, None),
    ("postgres", "dbname='x' table=\"Poles\" (geom)", False, None),
    ("wms", "type=xyz&url=https://example.org/%7Bz%7D/%7Bx%7D/%7By%7D.png", False, None),
])
def test_what_a_layer_reads(tmp_path, identify, provider, source, valid, expected):
    """A set of the tables it reads, or None when it is not understood -- and
    then nothing may be offered."""
    from urllib.parse import quote
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles", "Routes"]))
    other = str(_make_gpkg(tmp_path / "other.gpkg", ["Poles"]))
    source = source.format(gpkg=target, other=other, quoted=quote(target, safe=""))

    assert gt.used_tables([("memory", SCRATCH), (provider, source, valid)], target, identify) == expected


def _write(path, data):
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


VRT = ("<OGRVRTDataSource><OGRVRTLayer name=\"poles_vrt\"><SrcDataSource>{gpkg}</SrcDataSource>"
       "<SrcLayer>Poles</SrcLayer></OGRVRTLayer></OGRVRTDataSource>")

#: A GDAL raster tile index (GTI, GDAL 3.9 and later): the list of its tiles is
#: a table of the GeoPackage it names, here this one (review round three, a2).
GTI = ("<GDALTileIndexDataset><IndexDataset>{gpkg}</IndexDataset><IndexLayer>Poles</IndexLayer>"
       "<LocationField>location</LocationField></GDALTileIndexDataset>")

#: A GDAL pipeline (GDALG, GDAL 3.11 and later): a vector layer reading a table
#: of the GeoPackage it names, here this one (review round three, a3).
GDALG = ('{{"type": "gdal_streamed_alg", "command_line": '
         '"gdal vector pipeline read {gpkg} --layer Poles ! reproject --dst-crs EPSG:4326"}}')

GEOJSON = '{"type": "FeatureCollection", "features": []}'


def _geotiff(path, gpkg):
    """A one-band GeoTIFF as GDAL writes it."""
    gdal = pytest.importorskip("osgeo.gdal")
    raster = gdal.GetDriverByName("GTiff").Create(str(path), 2, 2, 1, gdal.GDT_Byte)
    raster.SetGeoTransform([0, 1, 0, 2, 0, -1])
    raster = None
    return path


@pytest.mark.parametrize("provider, name, make, understood", [
    # GDAL opens these with a driver that reads the file itself and nothing else.
    ("ogr", "other.gpkg", lambda path, gpkg: _make_gpkg(path, ["Poles"]), True),
    ("ogr", "other.gpkg", lambda path, gpkg: _make_gpkg(path, ["Poles"], application_id=0), True),
    ("ogr", "poles.shp.gpkg", lambda path, gpkg: _make_gpkg(path, ["Poles"]), True),
    ("gdal", "other.gpkg", lambda path, gpkg: _make_gpkg(path, ["Poles"]), True),
    ("ogr", "poles.geojson", lambda path, gpkg: _write(path, GEOJSON), True),
    ("ogr", "poles.dat", lambda path, gpkg: _write(path, GEOJSON), True),
    ("ogr", "poles.csv", lambda path, gpkg: _write(path, "id,x,y\n1,2,3\n"), True),
    ("gdal", "photo.tif", _geotiff, True),
    ("gdal", "photo.raster", _geotiff, True),
    # And these with one that reads the table it names in this file, whatever
    # the file is called: a VRT, a tile index, a pipeline. A GDAL older than
    # the tile index (3.9) or the pipeline (3.11) opens such a file with no
    # driver at all, which is not understood either.
    ("ogr", "poles.vrt", lambda path, gpkg: _write(path, VRT.format(gpkg=gpkg)), False),
    ("ogr", "poles.geojson", lambda path, gpkg: _write(path, VRT.format(gpkg=gpkg)), False),
    ("ogr", "poles.csv", lambda path, gpkg: _write(path, VRT.format(gpkg=gpkg)), False),
    ("ogr", "poles.shp", lambda path, gpkg: _write(path, VRT.format(gpkg=gpkg)), False),
    ("gdal", "photo.tif", lambda path, gpkg: _write(path, "<VRTDataset rasterXSize=\"1\"/>"), False),
    ("gdal", "mosaic.tif", lambda path, gpkg: _write(path, GTI.format(gpkg=gpkg)), False),
    ("gdal", "mosaic.json", lambda path, gpkg: _write(path, GTI.format(gpkg=gpkg)), False),
    ("gdal", "mosaic.gti", lambda path, gpkg: _write(path, GTI.format(gpkg=gpkg)), False),
    ("ogr", "poles.gdalg.json", lambda path, gpkg: _write(path, GDALG.format(gpkg=gpkg)), False),
    ("ogr", "poles.json", lambda path, gpkg: _write(path, GDALG.format(gpkg=gpkg)), False),
    # No driver, or one not listed; a raster file read as vectors; a folder;
    # a file that is not there.
    ("ogr", "poles.txt", lambda path, gpkg: _write(path, "id,x,y\n"), False),
    ("ogr", "poles.tab", lambda path, gpkg: _write(path, "!table\n"), False),
    ("ogr", "photo.tif", _geotiff, False),
    ("ogr", "poles.shp", lambda path, gpkg: path.mkdir(), False),
    ("ogr", "poles.shp", lambda path, gpkg: None, False),
])
def test_another_file_reads_nothing_of_this_one_only_when_its_driver_reads_only_it(
        tmp_path, identify, provider, name, make, understood):
    """Review v1, and round three's a2 and a3: GDAL picks a driver by what a
    file holds, so a VRT, a tile index or a pipeline under a plain name --
    .geojson, .csv, .tif, .json -- is opened as one, and reads the table it
    names in this file. A file's name and a search for a VRT's words said
    "plain" for the last two; GDAL's own driver decides now."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    folder = tmp_path / "elsewhere"
    folder.mkdir()
    make(folder / name, target)
    source = f"{folder / name}|layername=Poles" if provider == "ogr" else str(folder / name)

    expected = set() if understood else None
    assert gt.used_tables([(provider, source)], target, identify) == expected


def test_a_link_under_a_plain_name_to_a_vrt_is_not_understood(tmp_path, identify):
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    vrt = _write(tmp_path / "poles.vrt", VRT.format(gpkg=target))
    os.symlink(str(vrt), str(tmp_path / "poles.geojson"))

    assert gt.used_tables([("ogr", f"{tmp_path / 'poles.geojson'}")], target, identify) is None


def test_the_driver_is_asked_under_the_files_own_name_and_its_real_one(tmp_path):
    """GDAL picks some drivers by a file's name -- a shapefile's, a CSV's --
    and a link's name is not its file's: both names must say a listed driver."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    real = _write(tmp_path / "poles.vrt", GEOJSON)
    link = tmp_path / "poles.geojson"
    os.symlink(str(real), str(link))
    asked = []

    def identify(path, raster):
        asked.append((path, raster))
        return "GeoJSON" if path.endswith(".geojson") else "OGR_VRT"

    assert gt.used_tables([("ogr", str(link))], target, identify) is None
    assert sorted(asked) == sorted([(str(link), False), (os.path.realpath(str(real)), False)])


#: The drivers that read one file and never another dataset, as gpkg_target lists them.
SINGLE_FILE_DRIVERS = [
    "AAIGrid", "CSV", "DXF", "ESRI Shapefile", "FlatGeobuf", "GML", "GPX", "GTiff", "GeoJSON", "GeoJSONSeq",
    "JP2OpenJPEG", "JPEG", "KML", "LIBKML", "PNG",
]


def test_the_drivers_trusted_to_read_only_their_file_are_these():
    """A driver added to the list is a decision about every file it opens: it is made here, in a diff."""
    assert gt.SINGLE_FILE_DRIVERS == frozenset(SINGLE_FILE_DRIVERS)
    assert gt.SQLITE_DRIVERS == frozenset({"GPKG", "SQLite"})


@pytest.mark.parametrize("driver", SINGLE_FILE_DRIVERS)
def test_a_file_a_single_file_driver_opens_reads_nothing_of_this_one(tmp_path, driver):
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    other = _write(tmp_path / "other.data", "x")

    def identify(path, raster):
        return driver

    assert gt.used_tables([("ogr", f"{other}|layername=p"), ("gdal", str(other))], target, identify) == set()


@pytest.mark.parametrize("driver", [
    "VRT", "OGR_VRT", "GTI", "GDALG", "STACIT", "STACTA", "MapInfo File", "MBTiles", "WMS", "netCDF", "HDF5",
    "ENVI", "ESRIJSON", "", None,
])
def test_a_file_any_other_driver_opens_is_not_understood(tmp_path, driver):
    """An allow-list: a driver that reads other datasets, one this does not
    know, and no driver at all are the same answer."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    other = _write(tmp_path / "other.data", "x")

    def identify(path, raster):
        return driver

    assert gt.used_tables([("ogr", f"{other}|layername=p")], target, identify) is None
    assert gt.used_tables([("gdal", str(other))], target, identify) is None


def test_without_a_driver_to_ask_no_other_file_is_understood(tmp_path):
    """gpkg_target asks GDAL nothing itself: a caller that names no driver gets no offer over another file."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    other = _make_gpkg(tmp_path / "other.gpkg", ["Poles"])

    assert gt.used_tables([("ogr", f"{other}|layername=Poles")], target) is None
    assert gt.used_tables([("ogr", f"{target}|layername=Poles")], target) == {"poles"}, "this file needs no driver"


@pytest.mark.parametrize("own, expected", [
    ("GeoJSON", set()), (None, set()), ("OGR_VRT", None), ("GDALG", None), ("", None),
])
def test_the_driver_a_layer_opened_its_file_with_must_be_listed_too(tmp_path, own, expected):
    """An OGR layer's storage type is the driver its provider holds the file
    open with: a file GDAL now opens as GeoJSON may have been a VRT when the
    layer opened it, and the layer reads it as one until it opens it again."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    other = _write(tmp_path / "poles.geojson", GEOJSON)

    def identify(path, raster):
        return "GeoJSON"

    assert gt.used_tables([("ogr", f"{other}|layername=poles", True, own)], target, identify) == expected


def test_a_sqlite_driver_is_understood_only_on_a_sqlite_file(tmp_path):
    """GDAL reads a GeoPackage inside a .zip (3.7 and later); its virtual tables are not looked into here."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    zipped = _write(tmp_path / "other.gpkg.zip", b"PK\x03\x04" + b"\x00" * 64)

    def identify(path, raster):
        return "GPKG"

    assert gt.used_tables([("ogr", f"{zipped}|layername=Poles")], target, identify) is None


@pytest.mark.parametrize("module, understood", [
    ("rtree", True),
    ("VirtualSpatialIndex", True),
    ("VirtualElementary", True),
    ("VirtualKNN2", True),
    ("fts5", True),
    # GDAL's VirtualOGR reads another file's table: a QGIS layer reads the
    # target's Poles through one, under QGIS's default settings (measured on
    # 3.22.16 and 4.2.3). An unknown module could do the same.
    ("VirtualOGR", False),
    ("VirtualShape", False),
    ("somemodule", False),
])
def test_another_sqlite_file_is_understood_only_with_virtual_tables_that_read_itself(
        tmp_path, identify, module, understood):
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    other = _make_gpkg(tmp_path / "other.sqlite", ["Roads"], application_id=0)
    _virtual(other, "vt", f"CREATE VIRTUAL TABLE vt USING {module}('{target}', 0, 'Poles')")

    assert identify(other) == "SQLite"
    assert gt.used_tables([("ogr", f"{other}|layername=Roads")], target, identify) == (
        set() if understood else None)


def test_another_sqlite_file_whose_virtual_table_cannot_be_read_is_not_understood(tmp_path, identify):
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles"]))
    other = _make_gpkg(tmp_path / "other.sqlite", ["Roads"])
    _virtual(other, "vt", "CREATE VIRTUAL TABLE")

    assert gt.used_tables([("ogr", f"{other}|layername=Roads")], target, identify) is None


def test_a_project_with_one_layer_not_understood_offers_nothing(tmp_path):
    """Every layer of the project must be understood, not only those saved."""
    target = str(_make_gpkg(tmp_path / "fu8.gpkg", ["Poles", "Manholes"]))
    layers = [("memory", SCRATCH), ("ogr", f"{target}|layername=Manholes|subset=\"id\" IN (SELECT 1 FROM Poles)")]

    used = gt.used_tables(layers, target)
    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], target, used, replace=True)

    assert used is None
    assert plan.offers == {}
    assert plan.tables == ["Poles_2"], "beside it, as U6 did"


def test_a_file_holding_a_view_offers_nothing_even_over_another_table(tmp_path):
    """No view at all: which tables a view reads is in its SQL, not taken apart here."""
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles", "Routes"])
    _with_view(target, "routes_view", "Routes")

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(target), set(), replace=True)

    assert plan.offers == {}
    assert plan.tables == ["Poles_2"]


@pytest.mark.parametrize("rows, offered", [(0, True), (1, False)])
def test_a_file_holding_a_qgis_project_offers_nothing(tmp_path, rows, offered):
    """Review n19: a project stored in the file may read any of its tables."""
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("CREATE TABLE qgis_projects (name TEXT PRIMARY KEY, metadata BLOB, content BLOB)")
        conn.executemany("INSERT INTO qgis_projects VALUES (?, '{}', x'00')", [(f"survey{n}",) for n in range(rows)])
        conn.commit()

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(target), set(), replace=True)

    assert (plan.offers == {0: "Poles"}) is offered


@pytest.mark.parametrize("module, offered", [
    ("rtree", True), ("rtree_i32", True), ("fts5", False), ("VirtualOGR", False), ("somemodule", False),
])
def test_a_file_whose_virtual_tables_are_not_its_rtree_indexes_offers_nothing(tmp_path, module, offered):
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    _virtual(target, "vt", f"CREATE VIRTUAL TABLE vt USING {module}(id, minx, maxx, miny, maxy)")

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(target), set(), replace=True)

    assert (plan.offers == {0: "Poles"}) is offered


def test_a_qgis_projects_table_that_cannot_be_counted_counts_as_a_project(tmp_path):
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    _virtual(target, "qgis_projects", "CREATE VIRTUAL TABLE qgis_projects USING rtree(id, minx, maxx)")

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(target), set(), replace=True)

    assert plan.offers == {}
    assert gt.read_contents(target).projects is None


def test_a_registered_name_without_its_table_is_not_offered(tmp_path):
    target = _make_gpkg(tmp_path / "fu8.gpkg", [])
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("INSERT INTO gpkg_contents (table_name, data_type) VALUES ('Poles', 'features')")
        conn.commit()

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(target), set(), replace=True)

    assert plan.offers == {}
    assert plan.tables == ["Poles_2"]


def test_a_name_registered_twice_is_not_offered(tmp_path):
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("INSERT INTO gpkg_contents (table_name, data_type) VALUES ('POLES', 'features')")
        conn.commit()

    plan = gt.plan_tables([("Poles", SCRATCH, "layer_1")], str(target), set(), replace=True)

    assert plan.offers == {}


def test_a_table_no_registry_lists_is_taken_and_never_offered(tmp_path):
    """Review n5, n5c: another program's table, kept out of gpkg_contents,
    named like a layer. The question said the file's other tables stay; the
    writer replaced it all the same. Now its name is taken, while a registered
    unused table is still offered."""
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('CREATE TABLE "Notes" (nid INTEGER PRIMARY KEY, note TEXT)')
        conn.commit()

    plan = gt.plan_tables([("Notes", SCRATCH, "layer_1"), ("Poles", SCRATCH, "layer_2")], str(target), set(),
                          replace=True)

    assert plan.offers == {1: "Poles"}
    assert plan.tables == ["Notes_2", "Poles"]


def test_every_name_the_file_holds_is_taken(tmp_path):
    """An index, a trigger and a view are named in sqlite_master like a table,
    and a table of their name cannot be made."""
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('CREATE INDEX "Ducts" ON "Poles" (fid)')
        conn.execute('CREATE TRIGGER "Cables" AFTER INSERT ON "Poles" BEGIN SELECT 1; END')
        conn.execute('CREATE VIEW "Routes" AS SELECT fid FROM "Poles"')
        conn.commit()
    layers = [(name, SCRATCH, "layer") for name in ("Ducts", "Cables", "Routes")]

    plan = gt.plan_tables(layers, str(target), set())

    assert plan.tables == ["Ducts_2", "Cables_2", "Routes_2"]
    assert gt.table_name_for("Ducts", SCRATCH, str(target)) == "Ducts_2"


def _linked_dotdot(tmp_path):
    """b/fu8.gpkg, a/link pointing at b/sub, and "a/link/../fu8.gpkg": the
    operating system opens b/fu8.gpkg; os.path.abspath says a/fu8.gpkg."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    (b / "sub").mkdir(parents=True)
    real = _make_gpkg(b / "fu8.gpkg", ["Poles"])
    twin = _make_gpkg(a / "fu8.gpkg", ["Ducts"])
    os.symlink(str(b / "sub"), str(a / "link"))
    return str(real), str(twin), f"{a}/link/../fu8.gpkg"


def test_a_path_through_a_symlink_and_dotdot_is_the_file_the_system_opens(tmp_path):
    """Review n12, t3: compared and opened as os.path.abspath spells it, the
    path named another file -- the plan read the wrong file's tables."""
    real, twin, spelled = _linked_dotdot(tmp_path)

    assert gt.same_file(spelled, real)
    assert not gt.same_file(spelled, twin)
    assert set(gt.read_contents(spelled).kinds) == {"Poles"}
    assert gt.existing_tables(spelled) == {"Poles"}
    assert gt.table_name_for("Poles", SCRATCH, spelled) == "Poles_2"
    assert gt.file_identity(spelled) == gt.file_identity(real)


def test_a_path_whose_dotdot_is_read_two_ways_is_resolved_once(tmp_path):
    """QGIS 3.22.16 takes the ".." away before it follows the link -- its
    writer wrote into a/fu8.gpkg, a layer read a/fu8.gpkg, and so did Python's
    own sqlite3 there -- while the system, and QGIS 3.40 and later, open
    b/fu8.gpkg (measured). Chosen as the target, such a path is resolved;
    read by a layer, it is not understood."""
    real, twin, spelled = _linked_dotdot(tmp_path)
    (tmp_path / "a" / "sub").mkdir()
    plain_dotdot = f"{tmp_path / 'a' / 'sub'}/../fu8.gpkg"

    assert gt.unambiguous(spelled) == os.path.realpath(real)
    assert gt.unambiguous(twin) == twin, "a path read one way keeps its spelling"
    assert gt.unambiguous(plain_dotdot) == plain_dotdot, "with no link before it, '..' is read one way"
    assert gt.unambiguous("") == ""
    assert gt.used_tables([("ogr", f"{spelled}|layername=Poles")], real) is None
    assert gt.used_tables([("ogr", f"{spelled}|layername=Poles")], twin) is None
    assert gt.used_tables([("ogr", f"{plain_dotdot}|layername=Ducts")], twin) == {"ducts"}


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="Linux names open files under /proc/self/fd")
def test_a_path_through_proc_self_fd_is_the_same_file(tmp_path):
    """Review n11: a folder held open, spelled through its descriptor."""
    (tmp_path / "real").mkdir()
    target = str(_make_gpkg(tmp_path / "real" / "fu8.gpkg", ["Poles"]))
    descriptor = os.open(str(tmp_path / "real"), os.O_RDONLY)
    try:
        spelled = f"/proc/self/fd/{descriptor}/fu8.gpkg"
        assert gt.same_file(spelled, target)
        assert gt.used_tables([("ogr", f"{spelled}|layername=Poles")], target) == {"poles"}
    finally:
        os.close(descriptor)


def test_a_files_identity_holds_while_nothing_touches_it(tmp_path):
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])

    first = gt.file_identity(target)
    gt.read_contents(target)
    gt.table_name_for("Poles", SCRATCH, str(target))

    assert gt.file_identity(target) == first
    assert first[0] == os.path.realpath(str(target))


def test_the_empty_log_a_read_makes_does_not_change_a_files_identity(tmp_path):
    """Reading a file in WAL mode makes an empty log when there is none -- the
    plan's own read did, on 3.40.15, and the question's answer then found the
    file "changed" (measured)."""
    target = _make_gpkg(tmp_path / "fu4.gpkg", ["Scratch_A"])
    with closing(sqlite3.connect(str(target))) as conn:
        assert conn.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    assert not os.path.exists(f"{target}-wal")
    first = gt.file_identity(target)

    gt.read_contents(target)

    assert os.path.exists(f"{target}-wal") and os.path.getsize(f"{target}-wal") == 0
    assert gt.file_identity(target) == first


def test_a_files_identity_changes_with_a_write(tmp_path):
    """Review n10: another program wrote a table while the question was open."""
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    first = gt.file_identity(target)
    stat = os.stat(target)

    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('CREATE TABLE "Poles_2" (fid INTEGER PRIMARY KEY)')
        conn.commit()
    os.utime(str(target), ns=(stat.st_atime_ns, stat.st_mtime_ns))

    assert gt.file_identity(target) != first, "a write the file's time does not show"


def test_a_files_identity_changes_with_a_write_its_log_holds(tmp_path):
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    with closing(sqlite3.connect(str(target))) as conn:
        assert conn.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    keeper = sqlite3.connect(str(target))    # held open, so the log is not folded back on close
    try:
        keeper.execute("SELECT count(*) FROM gpkg_contents").fetchone()
        first = gt.file_identity(target)
        with closing(sqlite3.connect(str(target))) as conn:
            conn.execute('CREATE TABLE "Poles_2" (fid INTEGER PRIMARY KEY)')
            conn.commit()
        assert gt.file_identity(target) != first
    finally:
        keeper.close()


def test_a_files_identity_changes_when_another_file_takes_its_place(tmp_path):
    """Review f1: a sync client replaced the file while the question was open."""
    target = _make_gpkg(tmp_path / "fu8.gpkg", ["Poles"])
    incoming = tmp_path / "incoming.gpkg"
    incoming.write_bytes(target.read_bytes())
    stat = os.stat(target)
    os.utime(str(incoming), ns=(stat.st_atime_ns, stat.st_mtime_ns))
    first = gt.file_identity(target)

    os.replace(str(incoming), str(target))

    assert gt.file_identity(target) != first, "same bytes, same time: another file"


def test_a_missing_files_identity_says_so(tmp_path):
    missing = tmp_path / "new.gpkg"

    assert gt.file_identity(missing) == gt.file_identity(missing)
    assert gt.file_identity(missing)[1] == "unreadable"
    assert not missing.exists()
