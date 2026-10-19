"""Smaller things an export got wrong, found in the final review of the 1.6.0 branch.

Unclaimed (WP3 code). Each case says what happened before. Results are read back
with sqlite3 as plain data; a bundle is changed as another tool would, through
SQLite.
"""
import json
import sqlite3
import uuid
from contextlib import closing

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsFeature,
                       QgsGeometry, QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer)

from fiberq.core import interchange as ic
from fiberq.core.interchange_bundle import InterchangeBundleWriter, _extra_columns
from fiberq.core.interchange_import import InterchangeBundleReader

LON, LAT = 21.90, 43.32
UUID = "Point?crs=EPSG:4326&field=fiberq_uuid:string(64)"
LINE = "LineString?crs=EPSG:4326&field=fiberq_uuid:string(64)"


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    yield prj
    prj.clear()


def _layer(project, uri, name, uuids, line=False):
    layer = QgsVectorLayer(uri, name, "memory")
    features = []
    for position, identity in enumerate(uuids):
        feature = QgsFeature(layer.fields())
        if line:
            feature.setGeometry(QgsGeometry.fromPolylineXY(
                [QgsPointXY(LON, LAT + position * 0.001), QgsPointXY(LON + 0.01, LAT)]))
        else:
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON + position * 0.001, LAT)))
        feature.setAttribute("fiberq_uuid", identity)
        features.append(feature)
    ok, added = layer.dataProvider().addFeatures(features)
    assert ok
    project.addMapLayer(layer)
    return layer, [f.id() for f in added]


def _export(project, path, **kwargs):
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    result = InterchangeBundleWriter(project).write(str(path), layers=layers, **kwargs)
    assert result.ok, result.errors
    return result


def _rows(path, sql, params=()):
    with closing(sqlite3.connect(str(path))) as conn:
        return conn.execute(sql, params).fetchall()


def _sql(path, *statements):
    with closing(sqlite3.connect(str(path))) as conn:
        for statement in statements:
            if isinstance(statement, tuple):
                conn.execute(*statement)
            else:
                conn.execute(statement)
        conn.commit()


def _relations(project, *relations):
    project.writeEntry("StuboviPlugin", "Relacije/relations_v1",
                       json.dumps({"relations": list(relations)}))


def test_a_relation_is_not_doubled_over_a_bundle_from_before_1_6_0(project, tmp_path):
    """FiberQ before 1.6.0 wrote every relation under an identity derived from the
    project file, even one the Relations dialog gave a uuid of its own. 1.6.0
    writes it under that uuid, and kept the old copy beside it."""
    cables, (fid,) = _layer(project, LINE, "Underground cables", ["c1"], line=True)
    relation = {"id": str(uuid.uuid4()), "name": "Feeder A",
                "cables": [{"layer_id": cables.id(), "fid": fid}]}
    _relations(project, relation)
    bundle = tmp_path / "old.gpkg"
    _export(project, bundle)
    legacy = ic.legacy_relation_uuid(relation, project.fileName() or project.title() or "")
    _sql(bundle,  # as a 1.5.0 export left it: the derived identity, no record
         ("UPDATE fq_relation SET uuid = ?", (legacy,)),
         ("UPDATE fq_relation_member SET relation_uuid = ?", (legacy,)),
         ("DELETE FROM _fiberq_metadata WHERE key = ?", (ic.WRITTEN_KEY,)))

    _export(project, bundle)

    assert _rows(bundle, "SELECT uuid, name FROM fq_relation") == [(relation["id"], "Feeder A")]
    assert _rows(bundle, "SELECT relation_uuid FROM fq_relation_member") == [(relation["id"],)]


def test_another_tools_extension_row_with_no_payload_does_not_fail_the_export(project, tmp_path):
    """The format's fq_extension says payload_json NOT NULL; another tool's may
    not. Its one row with no payload failed the whole side-car and metadata
    write, on every export of the project after."""
    _layer(project, UUID, "Poles", ["p1"])
    bundle = tmp_path / "theirs.gpkg"
    _export(project, bundle)
    _sql(bundle,
         "ALTER TABLE fq_extension RENAME TO fq_extension_was",
         "CREATE TABLE fq_extension (uuid TEXT PRIMARY KEY, owner_uuid TEXT, kind TEXT, "
         "namespace TEXT, payload_json TEXT, produced_by TEXT)",
         "INSERT INTO fq_extension (uuid, kind, namespace, payload_json) "
         "VALUES ('ext-null', 'acme.note', 'com.acme', NULL)")
    target = QgsProject()
    target.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    try:
        assert InterchangeBundleReader(target).read(str(bundle)).ok
        out = tmp_path / "out.gpkg"
        _export(target, out)
        assert _rows(out, "SELECT payload_json FROM fq_extension WHERE uuid = 'ext-null'") == [
            ("null",)]
    finally:
        target.clear()


def test_the_same_table_loaded_twice_is_exported_once(project, tmp_path):
    source = tmp_path / "poles.gpkg"
    memory = QgsVectorLayer(UUID, "poles", "memory")
    feature = QgsFeature(memory.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    feature.setAttribute("fiberq_uuid", "p1")
    assert memory.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "poles"
    QgsVectorFileWriter.writeAsVectorFormatV3(memory, str(source),
                                              QgsCoordinateTransformContext(), options)
    first = QgsVectorLayer(f"{source}|layername=poles", "Poles", "ogr")
    second = QgsVectorLayer(f"{source}|layername=poles", "Poles", "ogr")
    assert first.isValid() and second.isValid() and first.id() != second.id()
    project.addMapLayers([first, second])
    out = tmp_path / "b.gpkg"

    result = InterchangeBundleWriter(project).write(str(out), layers=[first, second])

    assert result.ok, result.errors
    assert _rows(out, 'SELECT fiberq_uuid FROM "Poles"') == [("p1",)]
    assert [name for name, _reason in result.skipped] == ["Poles"]


def test_another_tools_rows_of_fiberqs_kinds_go_back_as_rows(project, tmp_path):
    """Rows of another namespace with kind feature_attributes or bundle_metadata
    were taken for FiberQ's: folded into fq_extra_json and the metadata table, or
    lost when their owner was no feature of the bundle."""
    _layer(project, UUID, "Poles", ["p1"])
    theirs = [
        {"uuid": "acme-1", "owner_uuid": "p1", "kind": ic.EXTENSION_KIND_ATTRIBUTES,
         "namespace": "com.acme", "payload_json": json.dumps({"acme_colour": "teal"})},
        {"uuid": "acme-2", "owner_uuid": None, "kind": ic.EXTENSION_KIND_METADATA,
         "namespace": "com.acme", "payload_json": json.dumps({"acme_state": "x"})},
        {"uuid": "acme-3", "owner_uuid": "u-elsewhere", "kind": ic.EXTENSION_KIND_ATTRIBUTES,
         "namespace": "com.acme", "payload_json": json.dumps({"a": 1})},
    ]
    out = tmp_path / "b.gpkg"

    _export(project, out, passthrough=theirs)

    assert sorted(r[0] for r in _rows(out, "SELECT uuid FROM fq_extension")) == [
        "acme-1", "acme-2", "acme-3"]
    assert _rows(out, 'SELECT fq_extra_json FROM "Poles"') == [(None,)]
    assert _rows(out, "SELECT value FROM _fiberq_metadata WHERE key = 'acme_state'") == []


def test_a_folder_metadata_file_with_a_byte_order_mark_is_read(project, tmp_path):
    _layer(project, UUID, "Poles", ["p1"])
    folder = tmp_path / "geojson"
    assert InterchangeBundleWriter(project).write_geojson(str(folder)).ok
    path = folder / "_fiberq_metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["acme_note"] = "kept"
    path.write_text(json.dumps(metadata), encoding="utf-8-sig")

    result = InterchangeBundleWriter(project).write_geojson(str(folder))

    assert result.ok, result.errors
    assert not any("could not be read" in w for w in result.warnings), result.warnings
    assert json.loads(path.read_text(encoding="utf-8"))["acme_note"] == "kept"


def test_extra_columns_differing_only_in_case_are_one_column(qgis_app):
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.execute("CREATE TABLE fq_relation (uuid TEXT PRIMARY KEY, name TEXT, category TEXT)")
        columns = _extra_columns(conn, "fq_relation", ("uuid", "name", "category"),
                                 [{"Foo": 1}, {"foo": 2}, {"NAME": "x"}])
    assert columns == ["uuid", "name", "category", "Foo"]


@pytest.mark.parametrize("provider, source", [
    ("postgres", "dbname='fttx' host=db.example user='alice' password='correct horse battery' "
                 "table=\"public\".\"poles\" (geom)"),
    ("ogr", "PG:dbname=fttx host=db.example user=alice password=s3cret|layername=poles"),
])
def test_where_a_layers_data_lives_never_shows_its_password(qgis_app, provider, source):
    layer = QgsVectorLayer(source, "Poles", provider)
    shown = InterchangeBundleWriter._source_of(layer)
    for secret in ("correct", "horse", "battery", "s3cret", "password"):
        assert secret not in shown, shown
    assert "poles" in shown


def test_a_blob_payload_goes_back_as_a_blob(project, tmp_path):
    _layer(project, UUID, "Poles", ["p1"])
    bundle = tmp_path / "theirs.gpkg"
    _export(project, bundle)
    blob = b"\x89PNG\r\n\x1a\n"
    _sql(bundle, ("INSERT INTO fq_extension (uuid, kind, namespace, payload_json) "
                  "VALUES ('ext-png', 'acme.image', 'com.acme', ?)", (blob,)))
    target = QgsProject()
    target.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    try:
        assert InterchangeBundleReader(target).read(str(bundle)).ok
        out = tmp_path / "out.gpkg"
        _export(target, out)
        assert _rows(out, "SELECT payload_json FROM fq_extension WHERE uuid = 'ext-png'") == [
            (blob,)]
    finally:
        target.clear()


def test_a_member_added_in_the_dialog_goes_after_the_kept_ones(project, tmp_path):
    cables, (c1, c3) = _layer(project, LINE, "Underground cables", ["c1", "c3"], line=True)
    relation = {"id": str(uuid.uuid4()), "name": "R",
                "cables": [{"layer_id": cables.id(), "fid": c1, "order_index": 0},
                           {"layer_id": cables.id(), "fid": c3}],   # the dialog's: no order
                "kept_members": [{"member_uuid": "u-splitter", "order_index": 3}]}
    _relations(project, relation)
    out = tmp_path / "b.gpkg"

    _export(project, out)

    assert _rows(out, "SELECT member_uuid, order_index FROM fq_relation_member "
                      "ORDER BY order_index") == [("c1", 0), ("u-splitter", 3), ("c3", 4)]


def test_a_reference_that_resolves_leaves_no_stale_copy_in_the_extras(project, tmp_path):
    cables, (cable_fid,) = _layer(project, LINE, "Underground cables", ["cable-now"], line=True)
    slack = QgsVectorLayer(UUID + "&field=cable_layer_id:string&field=cable_fid:integer",
                           "Optical slack", "memory")
    loop = QgsFeature(slack.fields())
    loop.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    loop.setAttribute("fiberq_uuid", "s1")
    loop.setAttribute("cable_layer_id", cables.id())
    loop.setAttribute("cable_fid", cable_fid)
    assert slack.dataProvider().addFeatures([loop])[0]
    project.addMapLayer(slack)
    kept = [{"kind": ic.EXTENSION_KIND_ATTRIBUTES, "namespace": ic.EXTENSION_NAMESPACE,
             "owner_uuid": "s1", "payload_json": json.dumps({"cable_uuid": "cable-gone"})}]
    out = tmp_path / "b.gpkg"

    _export(project, out, passthrough=kept)

    assert _rows(out, 'SELECT cable_uuid, fq_extra_json FROM "Optical slack"') == [
        ("cable-now", None)]


def test_a_kept_stop_yields_to_the_projects_record_of_its_cable(project, tmp_path):
    """An earlier import kept the stop for a cable the project did not have; a
    later one brought the cable with the stop marked 0. Written after the
    record, the kept row put its 1 back -- and brought back a stop removed in
    the dialog."""
    cables, (cable_fid,) = _layer(project, LINE, "Underground cables", ["c1"], line=True)
    poles, (pole_fid,) = _layer(project, UUID, "Poles", ["p1"])
    project.writeEntry("StuboviPlugin", "LatentElements/latent_v1", json.dumps({"cables": {
        f"{cables.id()}:{cable_fid}": {"elements": [
            {"layer_id": poles.id(), "fid": pole_fid, "naziv": "P1", "latent": False}]}}}))
    kept = [{"uuid": ic.stable_uuid("sidecar", "fq_path_stop"), "kind": ic.EXTENSION_KIND_SIDECAR,
             "namespace": ic.EXTENSION_NAMESPACE, "payload_json": json.dumps({
                 "table": "fq_path_stop",
                 "rows": [{"cable_uuid": "c1", "element_uuid": "p1", "order_index": 0,
                           "is_latent": 1},
                          {"cable_uuid": "c-elsewhere", "element_uuid": "p1", "order_index": 0,
                           "is_latent": 1}]})}]
    out = tmp_path / "b.gpkg"

    _export(project, out, passthrough=kept)

    assert _rows(out, "SELECT cable_uuid, element_uuid, is_latent FROM fq_path_stop "
                      "ORDER BY cable_uuid") == [("c-elsewhere", "p1", 1), ("c1", "p1", 0)]
