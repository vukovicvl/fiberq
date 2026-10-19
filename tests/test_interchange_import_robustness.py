"""What an import got wrong, found in the final review of the 1.6.0 branch.

Unclaimed (WP3 code). Each case says what happened before. A bundle is changed
as another tool would, through SQLite; GDAL's R-tree triggers name spatial
functions plain sqlite3 lacks, so they are stood in for (no geometry is
touched).
"""
import json
import sqlite3
from contextlib import closing

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)

from fiberq.core import interchange as ic
from fiberq.core.interchange_bundle import InterchangeBundleWriter
from fiberq.core.interchange_import import InterchangeBundleReader

LON, LAT = 21.90, 43.32


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    yield prj
    prj.clear()


def _fresh():
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    return prj


def _layer(project, name, rows, fields=("fiberq_uuid:string(64)",), line=False):
    geometry = "LineString" if line else "Point"
    layer = QgsVectorLayer(f"{geometry}?crs=EPSG:4326&" + "&".join(f"field={f}" for f in fields),
                           name, "memory")
    features = []
    for position, attrs in enumerate(rows):
        feature = QgsFeature(layer.fields())
        if line:
            feature.setGeometry(QgsGeometry.fromPolylineXY(
                [QgsPointXY(LON, LAT + position * 0.001), QgsPointXY(LON + 0.01, LAT)]))
        else:
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON + position * 0.001, LAT)))
        for key, value in attrs.items():
            feature.setAttribute(key, value)
        features.append(feature)
    ok, added = layer.dataProvider().addFeatures(features)
    assert ok
    project.addMapLayer(layer)
    return layer, [f.id() for f in added]


def _bundle(path, build):
    """A bundle FiberQ writes from a project ``build`` fills."""
    source = _fresh()
    build(source)
    layers = [lyr for lyr in source.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    assert InterchangeBundleWriter(source).write(str(path), layers=layers).ok
    source.clear()
    return str(path)


def _poles(project):
    _layer(project, "Poles", [{"fiberq_uuid": "p1", "owner": "ACME"}],
           ("fiberq_uuid:string(64)", "owner:string"))


def _sql(path, *statements):
    with closing(sqlite3.connect(str(path))) as conn:
        conn.create_function("ST_IsEmpty", 1, lambda geom: 0)
        for name in ("ST_MinX", "ST_MaxX", "ST_MinY", "ST_MaxY"):
            conn.create_function(name, 1, lambda geom: 0.0)
        for statement in statements:
            if isinstance(statement, tuple):
                conn.execute(*statement)
            else:
                conn.execute(statement)
        conn.commit()


def _rows(path, sql):
    with closing(sqlite3.connect(str(path))) as conn:
        return conn.execute(sql).fetchall()


def _import(project, path):
    result = InterchangeBundleReader(project).read(str(path))
    assert result.ok, result.errors
    return result


def _export(project, path):
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    result = InterchangeBundleWriter(project).write(str(path), layers=layers)
    assert result.ok, result.errors
    return result


def _extras(path, table, uuid):
    (extra,) = _rows(path, f"SELECT fq_extra_json FROM \"{table}\" WHERE fiberq_uuid = '{uuid}'")[0]
    return json.loads(extra) if extra else {}


# -- what the store keeps survives a bad table ------------------------------------------

def test_text_that_is_not_utf8_in_a_side_car_table_does_not_cost_the_import(project, tmp_path):
    """"Optički" in CP1250: sqlite3 raised "Could not decode to UTF-8" after the
    features were added and before the store was saved, so the pole's own extra
    column was lost for good -- a re-import skips the pole as already there."""
    bundle = _bundle(tmp_path / "b.gpkg", _poles)
    label = "Optički".encode("cp1250")
    _sql(bundle, "CREATE TABLE fq_tray (uuid TEXT PRIMARY KEY, label TEXT)",
         ("INSERT INTO fq_tray VALUES ('tray-1', CAST(? AS TEXT))", (label,)))

    _import(project, bundle)
    out = tmp_path / "out.gpkg"
    _export(project, out)

    assert _extras(out, "Poles", "p1") == {"owner": "ACME"}
    assert _rows(out, "SELECT uuid, CAST(label AS BLOB) FROM fq_tray") == [("tray-1", label)]


# -- an import adds, never updates ---------------------------------------------------------

def test_a_relation_with_no_uuid_is_added_once(project, tmp_path):
    bundle = _bundle(tmp_path / "b.gpkg", _poles)
    _sql(bundle, "INSERT INTO fq_relation (uuid, name, category) VALUES (NULL, 'Feeder', NULL)")
    for _ in range(3):
        _import(project, bundle)
    stored = json.loads(project.readEntry("StuboviPlugin", "Relacije/relations_v1", "")[0])
    assert [r["name"] for r in stored["relations"]] == ["Feeder"]


def test_a_later_bundles_row_does_not_replace_a_kept_one(project, tmp_path):
    first = _bundle(tmp_path / "first.gpkg", _poles)
    _sql(first, "INSERT INTO fq_splice_point (uuid, element_uuid, used_ports, notes) "
                "VALUES ('sp-1', 'u-jc', 7, 'surveyed 2026')")
    second = _bundle(tmp_path / "second.gpkg", _poles)
    _sql(second, "INSERT INTO fq_splice_point (uuid, element_uuid, used_ports, notes) "
                 "VALUES ('sp-1', 'u-jc', 3, 'plan 2024')")
    _import(project, first)

    again = _import(project, second)

    assert any("fq_splice_point" in w and "earlier row is kept" in w for w in again.warnings), (
        again.warnings)
    out = tmp_path / "out.gpkg"
    _export(project, out)
    assert _rows(out, "SELECT used_ports, notes FROM fq_splice_point") == [(7, "surveyed 2026")]


def test_a_reimport_does_not_reattach_a_loop_the_user_detached(project, tmp_path):
    def build(source):
        cables, (cable_fid,) = _layer(source, "Underground cables", [{"fiberq_uuid": "u-c"}],
                                      line=True)
        _layer(source, "Optical slack", [{"fiberq_uuid": "s1", "cable_layer_id": cables.id(),
                                          "cable_fid": cable_fid}],
               ("fiberq_uuid:string(64)", "cable_layer_id:string", "cable_fid:integer"))
    bundle = _bundle(tmp_path / "b.gpkg", build)
    _import(project, bundle)
    slack = next(lyr for lyr in project.mapLayers().values() if lyr.name() == "Optical slack")
    loop = next(slack.getFeatures())
    assert slack.dataProvider().changeAttributeValues({loop.id(): {
        slack.fields().indexFromName("cable_layer_id"): None,
        slack.fields().indexFromName("cable_fid"): None}})

    _import(project, bundle)

    loop = next(slack.getFeatures())
    assert loop["cable_layer_id"] in (None, "") or (
        hasattr(loop["cable_layer_id"], "isNull") and loop["cable_layer_id"].isNull())


def test_a_relation_from_a_1_5_0_import_is_matched_by_its_name(project, tmp_path):
    """Its integer id gives it no identity, so it was matched by name and
    members together -- and once its members had changed, re-importing its
    bundle added a second one."""
    def build(source):
        cables, (c1, c2) = _layer(source, "Underground cables",
                                  [{"fiberq_uuid": "c1"}, {"fiberq_uuid": "c2"}], line=True)
        source.writeEntry("StuboviPlugin", "Relacije/relations_v1", json.dumps({"relations": [
            {"id": 1, "name": "Feeder A", "cables": [{"layer_id": cables.id(), "fid": c1},
                                                     {"layer_id": cables.id(), "fid": c2}]}]}))
    bundle = _bundle(tmp_path / "b.gpkg", build)
    # Another project file than the one the bundle came from, so the identity
    # derived from it differs, as it does for a real 1.5.0 import.
    project.setTitle("the design, saved elsewhere")
    _import(project, bundle)
    stored = json.loads(project.readEntry("StuboviPlugin", "Relacije/relations_v1", "")[0])
    relation = stored["relations"][0]
    relation.pop("uuid", None)
    relation["id"] = 1                   # as a 1.5.0 import left it
    relation["cables"] = relation["cables"][:1]
    project.writeEntry("StuboviPlugin", "Relacije/relations_v1", json.dumps(stored))

    again = _import(project, bundle)

    stored = json.loads(project.readEntry("StuboviPlugin", "Relacije/relations_v1", "")[0])
    assert [r["name"] for r in stored["relations"]] == ["Feeder A"]
    assert any("other members" in w for w in again.warnings), again.warnings


# -- what an import keeps, it keeps where the store keeps it ------------------------------

def test_a_kept_cable_reference_survives_its_loop_being_added_again(project, tmp_path):
    def build(source):
        _layer(source, "Optical slack", [{"fiberq_uuid": "s1", "cable_uuid": "u-missing",
                                          "vendor": "v1"}],
               ("fiberq_uuid:string(64)", "cable_uuid:string", "vendor:string"))
    bundle = _bundle(tmp_path / "b.gpkg", build)
    _import(project, bundle)
    slack = next(lyr for lyr in project.mapLayers().values() if lyr.name() == "Optical slack")
    assert slack.dataProvider().deleteFeatures([f.id() for f in slack.getFeatures()])

    _import(project, bundle)
    out = tmp_path / "out.gpkg"
    _export(project, out)

    assert _rows(out, 'SELECT cable_uuid FROM "Optical slack"') == [("u-missing",)]


def test_a_json_typed_fq_extra_json_is_kept(project, tmp_path):
    """GDAL's application/json subtype: QGIS hands the value over as a dict, and
    through str() it was a Python repr -- "not a JSON object", and dropped."""
    bundle = _bundle(tmp_path / "b.gpkg", lambda s: _layer(s, "Poles", [{"fiberq_uuid": "p1"}]))
    _sql(bundle,
         ('UPDATE "Poles" SET fq_extra_json = ?', ('{"vendor_ref": "V-17", "height_m": 9}',)),
         "CREATE TABLE IF NOT EXISTS gpkg_data_columns (table_name TEXT NOT NULL, column_name "
         "TEXT NOT NULL, name TEXT, title TEXT, description TEXT, mime_type TEXT, "
         "constraint_name TEXT, CONSTRAINT pk_gdc PRIMARY KEY (table_name, column_name))",
         "INSERT INTO gpkg_data_columns (table_name, column_name, mime_type) VALUES "
         "('Poles', 'fq_extra_json', 'application/json')",
         "INSERT INTO gpkg_extensions (table_name, column_name, extension_name, definition, scope) "
         "VALUES ('gpkg_data_columns', NULL, 'gpkg_schema', "
         "'http://www.geopackage.org/spec121/#extension_schema', 'read-write')")

    result = _import(project, bundle)

    assert not any("not a JSON object" in w for w in result.warnings), result.warnings
    out = tmp_path / "out.gpkg"
    _export(project, out)
    assert _extras(out, "Poles", "p1") == {"vendor_ref": "V-17", "height_m": 9}


def test_a_null_is_left_out_on_every_qgis(project, tmp_path):
    """QGIS 3 hands a NULL back as a NULL QVariant, which was kept as
    {"note": null} -- in every feature's store row and in the next bundle."""
    bundle = _bundle(tmp_path / "b.gpkg", lambda s: _layer(
        s, "Poles", [{"fiberq_uuid": "p1", "note": None, "owner_ref": "x"}],
        ("fiberq_uuid:string(64)", "note:string", "owner_ref:string")))
    result = _import(project, bundle)
    assert not any("no fiberq_uuid" in w for w in result.warnings), result.warnings
    out = tmp_path / "out.gpkg"
    _export(project, out)
    assert _extras(out, "Poles", "p1") == {"owner_ref": "x"}


def test_a_feature_with_no_identity_is_said_to_come_back_on_reimport(project, tmp_path):
    bundle = _bundle(tmp_path / "b.gpkg", _poles)
    _sql(bundle, 'UPDATE "Poles" SET fiberq_uuid = NULL')
    result = _import(project, bundle)
    assert any("importing this bundle again adds them again" in w for w in result.warnings), (
        result.warnings)


# -- an import says what it newly kept, once ---------------------------------------------

def test_reimporting_the_projects_own_bundle_repeats_no_warning(project, tmp_path):
    def build(source):
        cables, (cable_fid,) = _layer(source, "Underground cables", [{"fiberq_uuid": "u-c"}],
                                      line=True)
        _layer(source, "Optical slack", [{"fiberq_uuid": "s1"}])
    bundle = _bundle(tmp_path / "b.gpkg", build)
    # A stop on a cable the project will not have, and a slack table with no
    # cable_uuid column: each warned about on the first import.
    _sql(bundle, "INSERT INTO fq_path_stop (cable_uuid, element_uuid, order_index, is_latent) "
                 "VALUES ('u-elsewhere', 's1', 0, 1)")
    first = _import(project, bundle)
    assert any("path stop(s)" in w for w in first.warnings), "premise"
    assert any("without being attached" in w for w in first.warnings), "premise"

    second = _import(project, bundle)

    assert second.warnings == [], second.warnings


def test_stray_members_are_reported_when_the_bundle_has_no_relation(project, tmp_path):
    bundle = _bundle(tmp_path / "b.gpkg", _poles)
    _sql(bundle, "INSERT INTO fq_relation_member (relation_uuid, member_uuid) "
                 "VALUES ('r-nowhere', 'p1')")
    result = _import(project, bundle)
    assert any("name no relation" in w for w in result.warnings), result.warnings


# -- the reader's own pieces -------------------------------------------------------------

def test_stored_dates_follow_the_feature_id_whatever_the_key(qgis_app, tmp_path):
    """A REAL key is not the feature id OGR reports; keyed by it, two
    features swapped their dates."""
    path = tmp_path / "t.sqlite"
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute("CREATE TABLE t (pk REAL PRIMARY KEY, seen DATETIME)")
        conn.execute("INSERT INTO t (rowid, pk, seen) VALUES (1, 2.0, '2026-01-01T00:00:01Z')")
        conn.execute("INSERT INTO t (rowid, pk, seen) VALUES (2, 1.0, '2026-02-02T00:00:02Z')")
        conn.commit()
    dates = InterchangeBundleReader._stored_dates(str(path), "t")
    assert dates == {1: {"seen": "2026-01-01T00:00:01Z"}, 2: {"seen": "2026-02-02T00:00:02Z"}}


def test_virtual_tables_are_not_carried_on_an_old_sqlite(project, tmp_path, monkeypatch):
    """Before SQLite 3.37 an unknown PRAGMA is an empty answer, not an error, so
    the fallback for table_list never ran and an R*Tree came back as data."""
    bundle = _bundle(tmp_path / "b.gpkg", _poles)
    _sql(bundle, "CREATE VIRTUAL TABLE fq_index USING rtree(id, minx, maxx)")
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 31, 1))
    _import(project, bundle)
    out = tmp_path / "out.gpkg"
    _export(project, out)
    names = {name for (name,) in _rows(out, "SELECT name FROM sqlite_master")}
    assert not any(name.startswith("fq_index") for name in names), names


def test_a_malformed_pass_through_record_is_skipped():
    assert ic.latent_records({"cables": {"a:1": {"elements": 5}}}) == {}
