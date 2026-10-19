"""Cable references and feature tables: what the import used to leave behind.

Unclaimed (WP3 code), found in the v1.6.0 docs review. Before FiberQ 1.6.0:

- a slack loop's or fibre break's ``cable_uuid`` was read only from a bundle
  table named exactly "Optical slack" or "Fiber break"; a bundle keeping its
  loops in any other table imported them unattached, with no warning, although
  section 6.1 makes ``fq_type``, not the table name, the contract;
- a ``cable_uuid`` on any other element type was dropped, and so was one naming
  a cable not in the project;
- re-importing a bundle re-pointed a loop the user had moved since;
- a feature table whose name was not ASCII letters, digits and ``_ .-`` --
  "Optički kablovi", "Poles (2024)" -- was skipped without a word;
- an empty string in a column FiberQ has no field for was dropped.

Results are read back with sqlite3 as plain data.
"""
import json
import sqlite3
from contextlib import closing

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsFeature,
                       QgsGeometry, QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer)

from fiberq.core.interchange_bundle import InterchangeBundleWriter
from fiberq.core.interchange_import import InterchangeBundleReader

LON, LAT = 21.90, 43.32


def _cable_bundle(path):
    """A FiberQ bundle with one underground cable, u-cable-1."""
    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    cables = QgsVectorLayer("LineString?crs=EPSG:4326&field=fiberq_uuid:string(64)"
                            "&field=od:string&field=do:string", "Underground cables", "memory")
    feature = QgsFeature(cables.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(LON, LAT), QgsPointXY(LON + 0.01, LAT)]))
    feature.setAttribute("fiberq_uuid", "u-cable-1")
    assert cables.dataProvider().addFeatures([feature])[0]
    project.addMapLayer(cables)
    assert InterchangeBundleWriter(project).write(str(path), layers=[cables]).ok
    project.clear()
    return str(path)


def _add_table(path, name, geometry, fields, rows):
    """Add a feature table to an existing bundle, as another tool would."""
    uri = f"{geometry}?crs=EPSG:4326&" + "&".join(f"field={f}" for f in fields)
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid()
    features = []
    for geom, attrs in rows:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geom)
        for key, value in attrs.items():
            feature.setAttribute(key, value)
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    code = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, path, QgsCoordinateTransformContext(), options)
    assert (code[0] if isinstance(code, tuple) else code) == QgsVectorFileWriter.WriterError.NoError


def _point(dx=0.0):
    return QgsGeometry.fromPointXY(QgsPointXY(LON + dx, LAT))


SLACK_FIELDS = ("fiberq_uuid:string(64)", "fq_type:string", "placement:string",
                "cable_uuid:string(64)")


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    yield prj
    prj.clear()


def _import(project, path):
    result = InterchangeBundleReader(project).read(path)
    assert result.ok, result.errors
    return result


def _layer(project, name):
    return next(lyr for lyr in project.mapLayers().values() if lyr.name() == name)


def _link(project):
    """(cable layer id, cable fid) of the one slack loop in the project."""
    slack = _layer(project, "Optical slack")
    (feature,) = list(slack.getFeatures())
    return feature["cable_layer_id"], feature["cable_fid"]


def _export(project, path):
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    assert InterchangeBundleWriter(project).write(str(path), layers=layers).ok


def _rows(path, sql):
    with closing(sqlite3.connect(str(path))) as conn:
        return conn.execute(sql).fetchall()


def test_a_slack_loop_in_a_table_of_any_name_keeps_its_cable(project, tmp_path):
    bundle = _cable_bundle(tmp_path / "b.gpkg")
    _add_table(bundle, "Slack loops", "Point", SLACK_FIELDS, [
        (_point(), {"fiberq_uuid": "u-slack-1", "fq_type": "slack", "cable_uuid": "u-cable-1"})])
    _import(project, bundle)
    cables = _layer(project, "Underground cables")
    assert _link(project) == (cables.id(), next(cables.getFeatures()).id())


def test_a_reference_on_an_element_fiberq_does_not_link_is_kept(project, tmp_path):
    bundle = _cable_bundle(tmp_path / "b.gpkg")
    _add_table(bundle, "Outlets", "Point", SLACK_FIELDS, [
        (_point(), {"fiberq_uuid": "u-to-1", "fq_type": "to", "placement": "outdoor",
                    "cable_uuid": "u-cable-1"})])
    _import(project, bundle)
    out = tmp_path / "out.gpkg"
    _export(project, out)
    (extra,) = _rows(out, 'SELECT fq_extra_json FROM "Outdoor TO"')
    assert json.loads(extra[0])["cable_uuid"] == "u-cable-1"


def test_a_reference_to_a_cable_not_in_the_project_goes_out_again(project, tmp_path):
    bundle = _cable_bundle(tmp_path / "b.gpkg")
    _add_table(bundle, "Slack loops", "Point", SLACK_FIELDS, [
        (_point(), {"fiberq_uuid": "u-slack-1", "fq_type": "slack",
                    "cable_uuid": "u-cable-elsewhere"})])
    result = _import(project, bundle)
    assert any("kept and written out again" in w for w in result.warnings), result.warnings
    out = tmp_path / "out.gpkg"
    _export(project, out)
    assert _rows(out, 'SELECT fiberq_uuid, cable_uuid FROM "Optical slack"') == [
        ("u-slack-1", "u-cable-elsewhere")]


def _slack_bundle(path):
    """A bundle FiberQ wrote from a project whose loop sits on u-cable-1."""
    source = QgsProject()
    source.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    cables = QgsVectorLayer("LineString?crs=EPSG:4326&field=fiberq_uuid:string(64)"
                            "&field=od:string&field=do:string", "Underground cables", "memory")
    cable = QgsFeature(cables.fields())
    cable.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(LON, LAT), QgsPointXY(LON + 0.01, LAT)]))
    cable.setAttribute("fiberq_uuid", "u-cable-1")
    ok, (cable,) = cables.dataProvider().addFeatures([cable])
    assert ok
    slack = QgsVectorLayer("Point?crs=EPSG:4326&field=fiberq_uuid:string(64)"
                           "&field=cable_layer_id:string&field=cable_fid:integer",
                           "Optical slack", "memory")
    loop = QgsFeature(slack.fields())
    loop.setGeometry(_point())
    loop.setAttribute("fiberq_uuid", "u-slack-1")
    loop.setAttribute("cable_layer_id", cables.id())
    loop.setAttribute("cable_fid", cable.id())
    assert slack.dataProvider().addFeatures([loop])[0]
    source.addMapLayers([cables, slack])
    assert InterchangeBundleWriter(source).write(str(path), layers=[cables, slack]).ok
    source.clear()
    return str(path)


def test_a_reimport_does_not_re_point_a_loop_the_user_moved(project, tmp_path):
    bundle = _slack_bundle(tmp_path / "b.gpkg")
    _import(project, bundle)
    cables = _layer(project, "Underground cables")
    assert _link(project)[1] == next(cables.getFeatures()).id(), "premise: linked on import"
    other = QgsFeature(cables.fields())
    other.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(LON, LAT + 0.01),
                                                  QgsPointXY(LON + 0.01, LAT + 0.01)]))
    other.setAttribute("fiberq_uuid", "u-cable-2")
    ok, (moved_to,) = cables.dataProvider().addFeatures([other])
    assert ok
    slack = _layer(project, "Optical slack")
    loop = next(slack.getFeatures())
    assert slack.dataProvider().changeAttributeValues(
        {loop.id(): {slack.fields().indexFromName("cable_fid"): moved_to.id()}})

    _import(project, bundle)
    assert _link(project) == (cables.id(), moved_to.id())


def test_a_feature_table_with_a_name_in_another_language_is_imported(project, tmp_path):
    bundle = _cable_bundle(tmp_path / "b.gpkg")
    _add_table(bundle, "Optički kablovi", "LineString",
               ("fiberq_uuid:string(64)", "fq_type:string", "placement:string"), [
                   (QgsGeometry.fromPolylineXY([QgsPointXY(LON, LAT + 0.02),
                                                QgsPointXY(LON + 0.01, LAT + 0.02)]),
                    {"fiberq_uuid": "u-cable-9", "fq_type": "cable.underground"})])
    _import(project, bundle)
    cables = _layer(project, "Underground cables")
    assert sorted(f["fiberq_uuid"] for f in cables.getFeatures()) == ["u-cable-1", "u-cable-9"]


def test_an_empty_string_in_a_column_fiberq_has_no_field_for_is_kept(project, tmp_path):
    bundle = _cable_bundle(tmp_path / "b.gpkg")
    _add_table(bundle, "Outlets", "Point", SLACK_FIELDS + ("owner_ref:string",), [
        (_point(), {"fiberq_uuid": "u-to-1", "fq_type": "to", "placement": "outdoor",
                    "owner_ref": ""})])
    _import(project, bundle)
    out = tmp_path / "out.gpkg"
    _export(project, out)
    (extra,) = _rows(out, 'SELECT fq_extra_json FROM "Outdoor TO"')
    assert json.loads(extra[0])["owner_ref"] == ""
