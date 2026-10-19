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
