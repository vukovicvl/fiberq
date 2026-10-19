"""Side-car rows FiberQ keeps for other tools survive what used to lose them.

Unclaimed (WP3 code), found in the v1.6.0 docs review. FiberQ does not model
fibre splices, trays or duct occupancy, so an import keeps those tables' rows
and the next export writes them back (spec section 8). Five things broke that:

- every import *replaced* a table's kept rows (one store row per table, its
  uuid derived from the table's name), so importing a second bundle dropped
  the fibre splices the first had brought, and nothing said so;
- a BLOB in a kept table reached ``json.dumps`` as ``bytes`` and raised in the
  middle of the import, after features had been added and before the store
  was saved;
- one kept row that SQLite refused on export aborted the whole side-car phase
  before ``_fiberq_metadata`` was written, and the file was then refused as
  "not a FiberQ interchange bundle";
- an export over a file holding another tool's *feature* table named ``fq_*``
  re-registered it as an attributes table, and QGIS opened it without its
  geometry;
- another tool's ``fq_extension`` row whose kind happened to be FiberQ's own
  ``sidecar_table`` was executed as a write into a side-car table.

Results are read back with sqlite3 as plain data: a failing assertion keeps its
frame alive, and an OGR layer outliving QgsApplication crashes the run.
"""
import json
import sqlite3
from contextlib import closing

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsFeature, QgsGeometry,
    QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer,
)

from fiberq.core.interchange_bundle import InterchangeBundleWriter
from fiberq.core.interchange_import import InterchangeBundleReader


def _closures(*uuids):
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=fiberq_uuid:string(64)&field=naziv:string",
                           "Joint Closures", "memory")
    assert layer.isValid()
    features = []
    for i, uuid in enumerate(uuids):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2437000.0 + 50 * i, 5365000.0)))
        feature.setAttribute("fiberq_uuid", uuid)
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    return layer


def _bundle(path, *uuids):
    """A real bundle FiberQ wrote, with closures and empty side-car tables."""
    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    layer = _closures(*uuids)
    project.addMapLayer(layer)
    result = InterchangeBundleWriter(project).write(str(path), layers=[layer])
    assert result.ok, result.errors
    project.clear()
    return str(path)


def _sql(path, *statements):
    with closing(sqlite3.connect(path)) as conn:
        for statement, params in statements:
            conn.execute(statement, params)
        conn.commit()


def _rows(path, sql):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(sql).fetchall()


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    yield prj
    prj.clear()


def _export(project, path):
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    return InterchangeBundleWriter(project).write(str(path), layers=layers)


SPLICE = ("INSERT INTO fq_splice_point (uuid, element_uuid, port_count, used_ports, "
          "config_json, notes) VALUES (?, ?, 24, 6, ?, 'kept verbatim')")


def test_a_second_import_adds_its_kept_rows_to_the_first(project, tmp_path):
    north = _bundle(tmp_path / "north.gpkg", "u-jc-north")
    _sql(north, (SPLICE, ("sp-north", "u-jc-north", '{"tray": 1}')))
    south = _bundle(tmp_path / "south.gpkg", "u-jc-south")
    _sql(south, (SPLICE, ("sp-south", "u-jc-south", '{"tray": 2}')))

    assert InterchangeBundleReader(project).read(north).ok
    assert InterchangeBundleReader(project).read(south).ok
    out = tmp_path / "out.gpkg"
    assert _export(project, out).ok

    assert _rows(str(out), "SELECT uuid FROM fq_splice_point ORDER BY uuid") == [
        ("sp-north",), ("sp-south",)]


def test_importing_the_same_bundle_again_does_not_duplicate_its_rows(project, tmp_path):
    north = _bundle(tmp_path / "north.gpkg", "u-jc-north")
    _sql(north, (SPLICE, ("sp-north", "u-jc-north", '{"tray": 1}')))
    assert InterchangeBundleReader(project).read(north).ok
    assert InterchangeBundleReader(project).read(north).ok
    out = tmp_path / "out.gpkg"
    assert _export(project, out).ok
    assert _rows(str(out), "SELECT uuid FROM fq_splice_point") == [("sp-north",)]


def test_a_binary_value_is_kept_byte_for_byte(project, tmp_path):
    bundle = _bundle(tmp_path / "blob.gpkg", "u-jc-1")
    _sql(bundle, (SPLICE, ("sp-1", "u-jc-1", sqlite3.Binary(b"\x00\xff\x10"))))

    result = InterchangeBundleReader(project).read(bundle)
    assert result.ok, result.errors
    out = tmp_path / "out.gpkg"
    assert _export(project, out).ok

    assert _rows(str(out), "SELECT config_json FROM fq_splice_point") == [(b"\x00\xff\x10",)]


def test_a_row_the_next_bundle_refuses_costs_only_that_table(project, tmp_path):
    """Another tool's fq_container_slot need not have FiberQ's NOT NULL."""
    foreign = _bundle(tmp_path / "foreign.gpkg", "u-jc-1")
    _sql(foreign,
         ("DROP TABLE fq_container_slot", ()),
         ("CREATE TABLE fq_container_slot (uuid TEXT PRIMARY KEY, container_uuid TEXT, "
          "slot_index INTEGER, label TEXT, kind TEXT, spec_json TEXT, status TEXT)", ()),
         ("INSERT INTO fq_container_slot (uuid, container_uuid, slot_index) VALUES "
          "('slot-1', NULL, 3)", ()),
         (SPLICE, ("sp-1", "u-jc-1", "{}")))
    assert InterchangeBundleReader(project).read(foreign).ok

    out = tmp_path / "out.gpkg"
    result = _export(project, out)
    assert result.ok, result.errors
    assert any("fq_container_slot" in warning for warning in result.warnings), result.warnings
    # The rest landed, and the file is still a bundle.
    assert _rows(str(out), "SELECT uuid FROM fq_splice_point") == [("sp-1",)]
    assert InterchangeBundleReader(QgsProject()).read(str(out)).ok


def test_exporting_over_a_file_leaves_another_tools_feature_table_alone(project, tmp_path):
    path = str(tmp_path / "shared.gpkg")
    trays = QgsVectorLayer("Point?crs=EPSG:4326&field=label:string", "trays", "memory")
    feature = QgsFeature(trays.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(21.9, 43.3)))
    feature.setAttribute("label", "T1")
    assert trays.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "fq_tray_geom"
    code = QgsVectorFileWriter.writeAsVectorFormatV3(
        trays, path, QgsCoordinateTransformContext(), options)
    assert (code[0] if isinstance(code, tuple) else code) == QgsVectorFileWriter.WriterError.NoError

    layer = _closures("u-jc-1")
    project.addMapLayer(layer)
    assert InterchangeBundleWriter(project).write(path, layers=[layer]).ok

    assert _rows(path, "SELECT data_type FROM gpkg_contents WHERE table_name='fq_tray_geom'") == [
        ("features",)]


def test_another_tools_row_with_fiberqs_kind_stays_its_row(project, tmp_path):
    bundle = _bundle(tmp_path / "other.gpkg", "u-jc-1")
    payload = json.dumps({"table": "fq_splice_point",
                          "rows": [{"uuid": "planted", "element_uuid": "u-jc-1"}]})
    _sql(bundle, ("INSERT INTO fq_extension (uuid, owner_uuid, kind, namespace, payload_json, "
                  "produced_by) VALUES ('x-1', NULL, 'sidecar_table', 'example.other', ?, "
                  "'Another Tool')", (payload,)))
    assert InterchangeBundleReader(project).read(bundle).ok
    out = tmp_path / "out.gpkg"
    assert _export(project, out).ok

    assert _rows(str(out), "SELECT uuid, namespace FROM fq_extension") == [("x-1", "example.other")]
    assert _rows(str(out), "SELECT uuid FROM fq_splice_point") == []


# ---------------------------------------------------------------------------
# What a later 1.x version of the format may add: columns and tables
# ---------------------------------------------------------------------------
#
# Rule 4: a 1.0 reader carries what a newer minor version added. The WP3 known
# limit "a column added by a newer minor format version survives in the project
# but not into the next bundle" held for side-car tables until now: the writer
# inserted only the columns its own DDL had, and a table this version does not
# define was never read at all.

def _columns(path, table):
    return [(r[1], r[2], r[3], r[5]) for r in _rows(path, f'PRAGMA table_info("{table}")')]


def test_a_column_a_newer_version_adds_travels_on(project, tmp_path):
    bundle = _bundle(tmp_path / "newer.gpkg", "u-jc-1")
    _sql(bundle,
         ("ALTER TABLE fq_splice_point ADD COLUMN vendor_ref TEXT", ()),
         ("INSERT INTO fq_splice_point (uuid, element_uuid, vendor_ref) "
          "VALUES ('sp-1', 'u-jc-1', 'ACME-7')", ()))
    assert InterchangeBundleReader(project).read(bundle).ok
    out = str(tmp_path / "out.gpkg")
    assert _export(project, out).ok
    assert _rows(out, "SELECT uuid, vendor_ref FROM fq_splice_point") == [("sp-1", "ACME-7")]
    assert ("vendor_ref", "TEXT", 0, 0) in _columns(out, "fq_splice_point")


def test_a_slot_number_written_as_index_travels_on(project, tmp_path):
    """Spec section 13: a writer that followed the earlier text wrote ``index``."""
    bundle = _bundle(tmp_path / "index.gpkg", "u-jc-1")
    _sql(bundle,
         ('ALTER TABLE fq_container_slot ADD COLUMN "index" INTEGER', ()),
         ('INSERT INTO fq_container_slot (uuid, container_uuid, "index") '
          "VALUES ('slot-1', 'c-1', 7)", ()))
    assert InterchangeBundleReader(project).read(bundle).ok
    out = str(tmp_path / "out.gpkg")
    assert _export(project, out).ok
    assert _rows(out, 'SELECT uuid, "index", slot_index FROM fq_container_slot') == [
        ("slot-1", 7, None)]


def _tray_bundle(tmp_path):
    bundle = _bundle(tmp_path / "trays.gpkg", "u-jc-1")
    _sql(bundle,
         ("CREATE TABLE fq_tray (uuid TEXT PRIMARY KEY, closure_uuid TEXT NOT NULL, "
          "positions INTEGER, photo BLOB)", ()),
         ("INSERT INTO gpkg_contents (table_name, data_type, identifier) "
          "VALUES ('fq_tray', 'attributes', 'fq_tray')", ()),
         ("INSERT INTO fq_tray VALUES ('t-1', 'u-jc-1', 12, ?)", (sqlite3.Binary(b"\x89PNG"),)))
    return bundle


def test_a_table_a_newer_version_adds_travels_on(project, tmp_path):
    assert InterchangeBundleReader(project).read(_tray_bundle(tmp_path)).ok
    out = str(tmp_path / "out.gpkg")
    assert _export(project, out).ok

    assert _rows(out, "SELECT * FROM fq_tray") == [("t-1", "u-jc-1", 12, b"\x89PNG")]
    # Its columns, declared types and key; NOT NULL is not a declared type.
    assert _columns(out, "fq_tray") == [("uuid", "TEXT", 0, 1), ("closure_uuid", "TEXT", 0, 0),
                                        ("positions", "INTEGER", 0, 0), ("photo", "BLOB", 0, 0)]
    assert _rows(out, "SELECT data_type FROM gpkg_contents WHERE table_name='fq_tray'") == [
        ("attributes",)]


def test_exporting_twice_over_one_file_does_not_double_a_carried_table(project, tmp_path):
    bundle = _tray_bundle(tmp_path)
    _sql(bundle, ("CREATE TABLE fq_notes (note TEXT, n INTEGER)", ()),
         ("INSERT INTO fq_notes VALUES ('no key', 1)", ()))
    assert InterchangeBundleReader(project).read(bundle).ok
    out = str(tmp_path / "out.gpkg")
    assert _export(project, out).ok
    assert _export(project, out).ok
    assert _rows(out, "SELECT COUNT(*) FROM fq_tray") == [(1,)]
    assert _rows(out, "SELECT * FROM fq_notes") == [("no key", 1)]


def test_a_declared_type_is_never_written_back_as_sql(project, tmp_path):
    """A declared type is SQL text from another tool's file."""
    bundle = _bundle(tmp_path / "odd.gpkg", "u-jc-1")
    _sql(bundle,
         ('CREATE TABLE fq_odd (a VARCHAR(36), b "TEXT NOT NULL", '
          'c "x); DROP TABLE fq_extension; --", d UNSIGNED BIG INT)', ()),
         ("INSERT INTO fq_odd VALUES ('A', NULL, 'C', 4)", ()))
    assert InterchangeBundleReader(project).read(bundle).ok
    out = str(tmp_path / "out.gpkg")
    assert _export(project, out).ok
    assert _columns(out, "fq_odd") == [("a", "VARCHAR(36)", 0, 0), ("b", "TEXT", 0, 0),
                                       ("c", "NUMERIC", 0, 0), ("d", "INTEGER", 0, 0)]
    assert _rows(out, "SELECT * FROM fq_odd") == [("A", None, "C", 4)]
    assert _rows(out, "SELECT COUNT(*) FROM sqlite_master WHERE name='fq_extension'") == [(1,)]


def test_a_column_a_newer_version_adds_to_fq_extension_travels_on(project, tmp_path):
    bundle = _bundle(tmp_path / "ext.gpkg", "u-jc-1")
    _sql(bundle,
         ("ALTER TABLE fq_extension ADD COLUMN signature TEXT", ()),
         ("INSERT INTO fq_extension (uuid, kind, namespace, payload_json, produced_by, signature) "
          "VALUES ('x-1', 'plan', 'example.other', '{}', 'Another Tool', 'sig-1')", ()))
    assert InterchangeBundleReader(project).read(bundle).ok
    out = str(tmp_path / "out.gpkg")
    assert _export(project, out).ok
    assert _rows(out, "SELECT uuid, signature FROM fq_extension") == [("x-1", "sig-1")]


def test_machinery_named_fq_is_not_carried_as_a_table(project, tmp_path):
    """A virtual table (full-text search) and its shadow tables are SQLite's
    machinery, and a table registered as anything but attributes is not a
    side-car table."""
    bundle = _bundle(tmp_path / "machinery.gpkg", "u-jc-1")
    try:
        _sql(bundle, ("CREATE VIRTUAL TABLE fq_search USING fts5(body)", ()),
             ("INSERT INTO fq_search VALUES ('closure')", ()))
    except sqlite3.OperationalError:
        pytest.skip("no FTS5 in this sqlite3")
    _sql(bundle, ("CREATE TABLE fq_tiles (id INTEGER PRIMARY KEY, z INTEGER)", ()),
         ("INSERT INTO gpkg_contents (table_name, data_type, identifier) "
          "VALUES ('fq_tiles', 'tiles', 'fq_tiles')", ()))
    result = InterchangeBundleReader(project).read(bundle)
    assert result.ok, result.errors
    assert not [t for t in result.sidecar_kept if t.startswith(("fq_search", "fq_tiles"))]
