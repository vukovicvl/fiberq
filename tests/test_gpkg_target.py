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

import pytest


def _load(name, relpath):
    """Load a module by path, without importing the package around it."""
    path = pathlib.Path(__file__).resolve().parent.parent / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gt = _load("gpkg_target", "fiberq/core/gpkg_target.py")


def _make_gpkg(path, tables=()):
    """A file with a GeoPackage header and the named tables registered."""
    with sqlite3.connect(str(path)) as conn:
        conn.execute("PRAGMA application_id = 1196444487")   # 'GPKG'
        conn.execute(
            "CREATE TABLE IF NOT EXISTS gpkg_contents ("
            " table_name TEXT PRIMARY KEY, data_type TEXT, identifier TEXT,"
            " description TEXT, last_change TEXT, srs_id INTEGER)")
        for table in tables:
            conn.execute(
                "INSERT OR REPLACE INTO gpkg_contents (table_name, data_type) VALUES (?, 'features')",
                (table,))
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


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the write bit")
def test_a_read_only_file(tmp_path):
    target = _make_gpkg(tmp_path / "auto.gpkg")
    target.chmod(0o444)
    try:
        assert gt.gpkg_target_problem(target) == "not_writable"
    finally:
        target.chmod(0o644)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the write bit")
def test_a_read_only_folder(tmp_path):
    folder = tmp_path / "locked"
    folder.mkdir()
    folder.chmod(0o555)
    try:
        assert gt.gpkg_target_problem(folder / "auto.gpkg") == "directory_not_writable"
    finally:
        folder.chmod(0o755)


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
