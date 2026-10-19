"""Relations keep their identity, kind, roles and order, and an import adds to yours.

Unclaimed (WP3 code), found in the v1.6.0 docs review. Before FiberQ 1.6.0:

- every relation left a bundle as a uuid derived from the project file's path,
  so its identity changed on Save As, even for a relation the Relations dialog
  had made with a uuid of its own; a foreign relation's uuid was thrown away on
  import; category became ``cable_group`` and every role ``cable``; member order
  was renumbered;
- an import wrote the bundle's relations over the project's, replacing every
  relation the user had;
- a member the project could not draw was dropped, and so was a column a later
  1.x version added to either table;
- an export over a bundle FiberQ had written before left the rows of a relation
  deleted or renamed since, and of a member removed since, in the file.

Results are read with sqlite3 as plain data (see test_interchange_sidecar_kept).
"""
import json
import sqlite3
import uuid
from contextlib import closing

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)

from fiberq.core import interchange as ic
from fiberq.core.interchange_bundle import InterchangeBundleWriter
from fiberq.core.interchange_import import InterchangeBundleReader

RELATIONS = ("StuboviPlugin", "Relacije/relations_v1")
LATENT = ("StuboviPlugin", "LatentElements/latent_v1")


def _cables(*uuids):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857&field=fiberq_uuid:string(64)"
                           "&field=od:string&field=do:string", "Underground cables", "memory")
    assert layer.isValid()
    features = []
    for i, cable_uuid in enumerate(uuids):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 20 * i), QgsPointXY(300, 20 * i)]))
        feature.setAttribute("fiberq_uuid", cable_uuid)
        features.append(feature)
    ok, added = layer.dataProvider().addFeatures(features)
    assert ok
    return layer, [f.id() for f in added]


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    yield prj
    prj.clear()


def _relations_entry(project, *relations):
    project.writeEntry(*RELATIONS, json.dumps({"relations": list(relations)}))


def _stored(project):
    raw = project.readEntry(*RELATIONS, "")[0]
    return json.loads(raw)["relations"] if raw else []


def _export(project, path):
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    result = InterchangeBundleWriter(project).write(str(path), layers=layers)
    assert result.ok, result.errors
    return result


def _import(project, path):
    result = InterchangeBundleReader(project).read(str(path))
    assert result.ok, result.errors
    return result


def _rows(path, sql):
    with closing(sqlite3.connect(str(path))) as conn:
        return conn.execute(sql).fetchall()


def _sql(path, *statements):
    with closing(sqlite3.connect(str(path))) as conn:
        for statement in statements:
            conn.execute(statement)
        conn.commit()


def _two_cables(project):
    layer, (c1, c2) = _cables("u-cable-1", "u-cable-2")
    project.addMapLayer(layer)
    return layer, c1, c2


def test_a_relation_from_the_dialog_leaves_under_its_own_id_and_category(project, tmp_path):
    layer, c1, _c2 = _two_cables(project)
    rid = str(uuid.uuid4())   # what NewRelationDialog.values() gives a relation
    _relations_entry(project, {"id": rid, "name": "Feeder A", "category": "Main",
                               "cables": [{"layer_id": layer.id(), "fid": c1}]})
    path = tmp_path / "out.gpkg"
    _export(project, path)
    assert _rows(path, "SELECT uuid, name, category FROM fq_relation") == [
        (rid, "Feeder A", "Main")]
    project.setFileName(str(tmp_path / "renamed.qgz"))   # Save As
    again = tmp_path / "again.gpkg"
    _export(project, again)
    assert _rows(again, "SELECT uuid FROM fq_relation") == [(rid,)]


def _foreign(tmp_path, *statements):
    """A bundle with two cables, whose relation rows another tool wrote."""
    source = QgsProject()
    layer, _ids = _cables("u-cable-1", "u-cable-2")
    source.addMapLayer(layer)
    path = tmp_path / "foreign.gpkg"
    _export(source, path)
    source.clear()
    _sql(path,
         "INSERT INTO fq_relation VALUES ('rel-foreign-1', 'Optical path 1', 'optical_path')",
         "INSERT INTO fq_relation_member VALUES ('rel-foreign-1', 'u-cable-1', 1, 'feeder_segment')",
         "INSERT INTO fq_relation_member VALUES ('rel-foreign-1', 'u-cable-2', 2, 'drop')",
         *statements)
    return path


def test_a_foreign_relation_round_trips_exactly(project, tmp_path):
    _import(project, _foreign(tmp_path))
    out = tmp_path / "out.gpkg"
    _export(project, out)
    assert _rows(out, "SELECT uuid, name, category FROM fq_relation") == [
        ("rel-foreign-1", "Optical path 1", "optical_path")]
    assert _rows(out, "SELECT relation_uuid, member_uuid, order_index, role "
                      "FROM fq_relation_member ORDER BY order_index") == [
        ("rel-foreign-1", "u-cable-1", 1, "feeder_segment"),
        ("rel-foreign-1", "u-cable-2", 2, "drop")]


def test_an_import_keeps_the_projects_own_relations(project, tmp_path):
    bundle = _foreign(tmp_path)
    _import(project, bundle)
    layer = next(lyr for lyr in project.mapLayers().values() if lyr.name() == "Underground cables")
    fid = next(layer.getFeatures()).id()
    mine = {"id": str(uuid.uuid4()), "name": "Mine", "category": "Local",
            "cables": [{"layer_id": layer.id(), "fid": fid}]}
    _relations_entry(project, mine, *_stored(project))
    _sql(bundle, "INSERT INTO fq_relation VALUES ('rel-foreign-2', 'Another', 'feeder')")

    _import(project, bundle)
    names = sorted(r["name"] for r in _stored(project))
    assert names == ["Another", "Mine", "Optical path 1"]
    assert next(r for r in _stored(project) if r["name"] == "Mine") == mine


def test_importing_the_same_bundle_again_adds_nothing_and_says_nothing(project, tmp_path):
    bundle = _foreign(tmp_path)
    _import(project, bundle)
    before = _stored(project)
    result = _import(project, bundle)
    assert _stored(project) == before
    assert not [w for w in result.warnings if "relation" in w], result.warnings


def test_a_member_fiberq_does_not_draw_is_kept(project, tmp_path):
    bundle = _foreign(tmp_path, "INSERT INTO fq_relation_member VALUES "
                                "('rel-foreign-1', 'u-splitter-1', 3, 'splitter')")
    result = _import(project, bundle)
    assert any("kept and written out again" in w for w in result.warnings), result.warnings
    out = tmp_path / "out.gpkg"
    _export(project, out)
    assert ("rel-foreign-1", "u-splitter-1", 3, "splitter") in _rows(
        out, "SELECT relation_uuid, member_uuid, order_index, role FROM fq_relation_member")


def test_columns_a_newer_version_adds_to_relations_travel_on(project, tmp_path):
    bundle = _foreign(tmp_path,
                      "ALTER TABLE fq_relation ADD COLUMN description TEXT",
                      "UPDATE fq_relation SET description = 'trunk north'",
                      "ALTER TABLE fq_relation_member ADD COLUMN note TEXT",
                      "UPDATE fq_relation_member SET note = 'spliced at JC-4' "
                      "WHERE member_uuid = 'u-cable-2'")
    _import(project, bundle)
    out = tmp_path / "out.gpkg"
    _export(project, out)
    assert _rows(out, "SELECT description FROM fq_relation") == [("trunk north",)]
    assert _rows(out, "SELECT member_uuid, note FROM fq_relation_member ORDER BY order_index") == [
        ("u-cable-1", None), ("u-cable-2", "spliced at JC-4")]


def _pass_through(layer, fid, element_layer, element_fid):
    return {f"{layer.id()}:{fid}": {"elements": [
        {"layer_id": element_layer.id(), "fid": element_fid, "naziv": "", "latent": True}]}}


def test_exporting_again_over_the_same_file_leaves_no_stale_rows(project, tmp_path):
    layer, c1, c2 = _two_cables(project)
    r1, r2 = str(uuid.uuid4()), str(uuid.uuid4())
    _relations_entry(project,
                     {"id": r1, "name": "Keep", "cables": [{"layer_id": layer.id(), "fid": c1},
                                                           {"layer_id": layer.id(), "fid": c2}]},
                     {"id": r2, "name": "Delete me", "cables": [{"layer_id": layer.id(), "fid": c2}]})
    project.writeEntry(*LATENT, json.dumps({"cables": {
        **_pass_through(layer, c1, layer, c2), **_pass_through(layer, c2, layer, c1)}}))
    path = tmp_path / "shared.gpkg"
    _export(project, path)
    _sql(path, "INSERT INTO fq_relation VALUES ('rel-other-tool', 'Theirs', 'x')",
         "INSERT INTO fq_relation_member VALUES ('rel-other-tool', 'u-cable-1', 0, 'x')")

    # Since then: one relation deleted, a member removed, a cable's list cleared.
    _relations_entry(project, {"id": r1, "name": "Keep",
                               "cables": [{"layer_id": layer.id(), "fid": c1}]})
    project.writeEntry(*LATENT, json.dumps({"cables": _pass_through(layer, c1, layer, c2)}))
    _export(project, path)

    assert sorted(_rows(path, "SELECT uuid FROM fq_relation")) == sorted(
        [(r1,), ("rel-other-tool",)])
    assert sorted(_rows(path, "SELECT relation_uuid, member_uuid FROM fq_relation_member")) == sorted(
        [(r1, "u-cable-1"), ("rel-other-tool", "u-cable-1")])
    assert _rows(path, "SELECT cable_uuid FROM fq_path_stop") == [("u-cable-1",)]


def test_a_record_another_tool_copied_deletes_nothing(project, tmp_path):
    layer, c1, _c2 = _two_cables(project)
    r1 = str(uuid.uuid4())
    _relations_entry(project, {"id": r1, "name": "R", "cables": [{"layer_id": layer.id(), "fid": c1}]})
    path = tmp_path / "copied.gpkg"
    _export(project, path)
    # As if another tool rewrote the file: its own produced_at, FiberQ's key copied.
    _sql(path, "UPDATE _fiberq_metadata SET value = '2001-01-01T00:00:00' WHERE key = 'produced_at'")
    _relations_entry(project)
    _export(project, path)
    assert _rows(path, "SELECT uuid FROM fq_relation") == [(r1,)]


def _record(path):
    (value,) = _rows(path, f"SELECT value FROM _fiberq_metadata WHERE key = '{ic.WRITTEN_KEY}'")[0]
    return json.loads(value)


def test_the_record_names_only_what_this_export_wrote(project, tmp_path):
    layer, c1, _c2 = _two_cables(project)
    r1 = str(uuid.uuid4())
    _relations_entry(project, {"id": r1, "name": "R", "cables": [{"layer_id": layer.id(), "fid": c1}]})
    path = tmp_path / "out.gpkg"
    _export(project, path)
    assert _record(path)["fq_relation"] == [r1]
    _relations_entry(project)
    _export(project, path)
    assert _record(path)["fq_relation"] == []


def test_the_geojson_profile_records_its_files_not_the_side_car(project, tmp_path):
    layer, c1, _c2 = _two_cables(project)
    _relations_entry(project, {"id": str(uuid.uuid4()), "name": "R",
                               "cables": [{"layer_id": layer.id(), "fid": c1}]})
    folder = tmp_path / "geojson"
    result = InterchangeBundleWriter(project).write_geojson(str(folder), layers=[layer])
    assert result.ok, result.errors
    with open(folder / "_fiberq_metadata.json", encoding="utf-8") as handle:
        record = json.loads(json.load(handle)[ic.WRITTEN_KEY])
    assert record["files"] == ["cable.underground.geojson"]
    assert "fq_relation" not in record


def test_a_relation_with_an_integer_id_is_matched_on_reimport(project, tmp_path):
    """What a FiberQ 1.5.0 import wrote; matched by its derived identity, and
    after a Save As by its name and members, never added twice."""
    layer, c1, _c2 = _two_cables(project)
    project.setFileName(str(tmp_path / "design.qgz"))
    _relations_entry(project, {"id": 1, "name": "Feeder A",
                               "cables": [{"layer_id": layer.id(), "fid": c1}]})
    path = tmp_path / "out.gpkg"
    _export(project, path)
    _import(project, path)
    assert len(_stored(project)) == 1
    project.setFileName(str(tmp_path / "elsewhere.qgz"))
    _import(project, path)
    assert len(_stored(project)) == 1
    (relation,) = _stored(project)
    assert relation.get("uuid") == _rows(path, "SELECT uuid FROM fq_relation")[0][0]
