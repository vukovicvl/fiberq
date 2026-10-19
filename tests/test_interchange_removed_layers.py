"""An export over a bundle removes what FiberQ wrote there for a layer it no longer has.

Unclaimed (WP3 code), found in the v1.6.0 review. Before FiberQ 1.6.0 an export
over a bundle left the feature table it had written there last time for a layer
the project no longer had -- deleted, renamed, or left out of the export -- and
the GeoJSON profile left the file. A reader went on finding manholes that had
been deleted, presented as part of this export.

Only what FiberQ's own record (``interchange.WRITTEN_KEY``) says it wrote is
removed: another tool's table or file stays, and so does everything in a bundle
written before the record existed. Results are read back with sqlite3 and the
file system, as plain data.
"""
import json
import sqlite3
from contextlib import closing

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsFeature,
                       QgsGeometry, QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer)

from fiberq.core import interchange as ic
from fiberq.core.interchange_bundle import InterchangeBundleWriter

LON, LAT = 21.90, 43.32
UUID = "Point?crs=EPSG:4326&field=fiberq_uuid:string(64)"


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    yield prj
    prj.clear()


def _layer(project, name, uuid):
    layer = QgsVectorLayer(UUID, name, "memory")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    feature.setAttribute("fiberq_uuid", uuid)
    assert layer.dataProvider().addFeatures([feature])[0]
    project.addMapLayer(layer)
    return layer


def _export(project, path):
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    result = InterchangeBundleWriter(project).write(str(path), layers=layers)
    assert result.ok, result.errors
    return result


def _geojson(project, folder):
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    result = InterchangeBundleWriter(project).write_geojson(str(folder), layers=layers)
    assert result.ok, result.errors
    return result


def _rows(path, sql):
    with closing(sqlite3.connect(str(path))) as conn:
        return conn.execute(sql).fetchall()


def _feature_tables(path):
    return sorted(name for (name,) in _rows(
        path, "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"))


def _sqlite_tables(path):
    return {name for (name,) in _rows(path, "SELECT name FROM sqlite_master WHERE type = 'table'")}


def _foreign_table(path, name):
    """A feature table another tool adds to the bundle after FiberQ wrote it."""
    layer = QgsVectorLayer(UUID + "&field=fq_type:string", name, "memory")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    feature.setAttribute("fiberq_uuid", "u-acme-1")
    feature.setAttribute("fq_type", "acme.splitter")
    assert layer.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    code = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(path), QgsCoordinateTransformContext(), options)
    assert (code[0] if isinstance(code, tuple) else code) == QgsVectorFileWriter.WriterError.NoError


def test_the_table_of_a_layer_the_project_no_longer_has_is_removed(project, tmp_path):
    _layer(project, "Poles", "p1")
    manholes = _layer(project, "Manholes", "m1")
    bundle = tmp_path / "b.gpkg"
    _export(project, bundle)
    assert _feature_tables(bundle) == ["Manholes", "Poles"], "premise"

    project.removeMapLayer(manholes.id())
    result = _export(project, bundle)

    assert _feature_tables(bundle) == ["Poles"]
    assert "Manholes" not in _sqlite_tables(bundle)
    assert any("Manholes" in warning for warning in result.warnings), result.warnings
    assert _rows(bundle, 'SELECT fiberq_uuid FROM "Poles"') == [("p1",)]


def test_another_tools_table_stays(project, tmp_path):
    _layer(project, "Poles", "p1")
    bundle = tmp_path / "b.gpkg"
    _export(project, bundle)
    _foreign_table(bundle, "acme_splitters")

    _export(project, bundle)

    assert _feature_tables(bundle) == ["Poles", "acme_splitters"]


def test_a_bundle_with_no_record_loses_nothing(project, tmp_path):
    """What FiberQ before 1.6.0 left: no record of which tables it wrote."""
    _layer(project, "Poles", "p1")
    manholes = _layer(project, "Manholes", "m1")
    bundle = tmp_path / "b.gpkg"
    _export(project, bundle)
    with closing(sqlite3.connect(str(bundle))) as conn:
        conn.execute("DELETE FROM _fiberq_metadata WHERE key = ?", (ic.WRITTEN_KEY,))
        conn.commit()

    project.removeMapLayer(manholes.id())
    _export(project, bundle)

    assert _feature_tables(bundle) == ["Manholes", "Poles"]


def test_a_record_another_tool_copied_removes_nothing(project, tmp_path):
    _layer(project, "Poles", "p1")
    manholes = _layer(project, "Manholes", "m1")
    bundle = tmp_path / "b.gpkg"
    _export(project, bundle)
    with closing(sqlite3.connect(str(bundle))) as conn:
        conn.execute("UPDATE _fiberq_metadata SET value = '2001-01-01T00:00:00' "
                     "WHERE key = 'produced_at'")
        conn.commit()

    project.removeMapLayer(manholes.id())
    _export(project, bundle)

    assert _feature_tables(bundle) == ["Manholes", "Poles"]


def test_the_geojson_file_of_an_element_type_the_project_no_longer_has_is_removed(project, tmp_path):
    _layer(project, "Poles", "p1")
    manholes = _layer(project, "Manholes", "m1")
    folder = tmp_path / "geojson"
    _geojson(project, folder)
    assert (folder / "manhole.geojson").is_file(), "premise"
    (folder / "acme.geojson").write_text('{"type": "FeatureCollection", "features": []}',
                                         encoding="utf-8")

    project.removeMapLayer(manholes.id())
    result = _geojson(project, folder)

    assert not (folder / "manhole.geojson").exists()
    assert (folder / "pole.geojson").is_file()
    assert (folder / "acme.geojson").is_file(), "another tool's file was removed"
    assert any("manhole.geojson" in warning for warning in result.warnings), result.warnings


def test_a_record_naming_a_path_never_reaches_outside_the_folder(project, tmp_path):
    _layer(project, "Poles", "p1")
    folder = tmp_path / "geojson"
    _geojson(project, folder)
    outside = tmp_path / "outside.geojson"
    outside.write_text("{}", encoding="utf-8")
    metadata_path = folder / "_fiberq_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    record = json.loads(metadata[ic.WRITTEN_KEY])
    record["files"] += ["../outside.geojson", str(outside), "_fiberq_metadata.json"]
    metadata[ic.WRITTEN_KEY] = json.dumps(record)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    result = _geojson(project, folder)

    assert outside.is_file()
    # The export rewrites _fiberq_metadata.json afterwards, so its presence
    # proves nothing; what the removal step reports does.
    assert not any("_fiberq_metadata.json" in w or "outside" in w for w in result.warnings), (
        result.warnings)


# -- a layer the project still has keeps what FiberQ wrote for it ------------------------
#
# Found in the final review of the 1.6.0 branch: the first version of the removal
# above took "not written by this export" for "no longer in the project", so a
# FiberQ layer whose data QGIS could not open that day (a database that was down,
# a share that was not mounted) lost its table, and its cables' stops and its
# features' relation members went with it.


def _gpkg_layer(path, name, uuid, geometry="Point"):
    """A FiberQ layer stored in its own GeoPackage, as a project on disk holds it."""
    memory = QgsVectorLayer(f"{geometry}?crs=EPSG:4326&field=fiberq_uuid:string(64)", name,
                            "memory")
    feature = QgsFeature(memory.fields())
    if geometry == "Point":
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    else:
        feature.setGeometry(QgsGeometry.fromPolylineXY(
            [QgsPointXY(LON, LAT), QgsPointXY(LON + 0.01, LAT)]))
    feature.setAttribute("fiberq_uuid", uuid)
    assert memory.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    QgsVectorFileWriter.writeAsVectorFormatV3(memory, str(path), QgsCoordinateTransformContext(),
                                              options)
    layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
    assert layer.isValid()
    return layer


def _cable_project(tmp_path):
    """Cables and poles on disk, one relation on the cable and one stop at the pole."""
    import uuid as _uuid

    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    prj.writeEntryBool("Paths", "/Absolute", True)
    (tmp_path / "data").mkdir()
    cables = _gpkg_layer(tmp_path / "data" / "cables.gpkg", "Underground cables", "c1",
                         "LineString")
    poles = _gpkg_layer(tmp_path / "poles.gpkg", "Poles", "p1")
    prj.addMapLayers([cables, poles])
    cable_fid = next(cables.getFeatures()).id()
    pole_fid = next(poles.getFeatures()).id()
    relation = str(_uuid.uuid4())
    prj.writeEntry("StuboviPlugin", "Relacije/relations_v1", json.dumps({"relations": [
        {"id": relation, "name": "R", "cables": [{"layer_id": cables.id(), "fid": cable_fid}]}]}))
    prj.writeEntry("StuboviPlugin", "LatentElements/latent_v1", json.dumps({"cables": {
        f"{cables.id()}:{cable_fid}": {"elements": [
            {"layer_id": poles.id(), "fid": pole_fid, "naziv": "P1", "latent": True}]}}}))
    qgs = tmp_path / "design.qgs"
    assert prj.write(str(qgs))
    return prj, qgs, relation


def _reopened_without(tmp_path, qgs, missing):
    """The project, opened where ``missing`` cannot be reached (moved disk, share down)."""
    text = qgs.read_text(encoding="utf-8").replace(str(missing), str(tmp_path / "gone" / "x.gpkg"))
    moved = tmp_path / "moved.qgs"
    moved.write_text(text, encoding="utf-8")
    again = QgsProject()
    assert again.read(str(moved))
    states = {lyr.name(): lyr.isValid() for lyr in again.mapLayers().values()}
    assert states == {"Underground cables": False, "Poles": True}, states
    return again


def test_a_layer_qgis_cannot_open_keeps_its_table_stops_and_members(tmp_path):
    prj, qgs, relation = _cable_project(tmp_path)
    bundle = tmp_path / "b.gpkg"
    assert InterchangeBundleWriter(prj).write(str(bundle)).ok
    prj.clear()
    assert _rows(bundle, "SELECT cable_uuid, element_uuid FROM fq_path_stop") == [("c1", "p1")]

    again = _reopened_without(tmp_path, qgs, tmp_path / "data" / "cables.gpkg")
    result = InterchangeBundleWriter(again).write(str(bundle))
    again.clear()

    assert result.ok, result.errors
    assert "Underground cables" in _feature_tables(bundle)
    assert _rows(bundle, "SELECT cable_uuid, element_uuid FROM fq_path_stop") == [("c1", "p1")]
    assert _rows(bundle, "SELECT relation_uuid, member_uuid FROM fq_relation_member") == [
        (relation, "c1")]
    assert any("cannot open" in w and "Underground cables" in w for w in result.warnings), (
        result.warnings)


def test_a_layer_left_out_for_its_crs_keeps_its_table(project, tmp_path):
    _layer(project, "Poles", "p1")
    manholes = _layer(project, "Manholes", "m1")
    bundle = tmp_path / "b.gpkg"
    _export(project, bundle)

    manholes.setCrs(QgsCoordinateReferenceSystem())
    _export(project, bundle)

    assert _feature_tables(bundle) == ["Manholes", "Poles"]


def test_a_malformed_record_is_ignored_rather_than_crashed_on(project, tmp_path):
    _layer(project, "Poles", "p1")
    manholes = _layer(project, "Manholes", "m1")
    bundle = tmp_path / "b.gpkg"
    _export(project, bundle)
    (produced_at,) = _rows(bundle, "SELECT value FROM _fiberq_metadata "
                                   "WHERE key = 'produced_at'")[0]
    with closing(sqlite3.connect(str(bundle))) as conn:
        conn.execute("UPDATE _fiberq_metadata SET value = ? WHERE key = ?", (
            json.dumps({"produced_at": produced_at, "features": [["Manholes"]]}),
            ic.WRITTEN_KEY))
        conn.commit()

    project.removeMapLayer(manholes.id())
    _export(project, bundle)

    assert _feature_tables(bundle) == ["Manholes", "Poles"], "a malformed record removed a table"


def test_a_relations_entry_that_cannot_be_read_removes_nothing(project, tmp_path):
    import uuid as _uuid

    cables = QgsVectorLayer("LineString?crs=EPSG:4326&field=fiberq_uuid:string(64)",
                            "Underground cables", "memory")
    feature = QgsFeature(cables.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(LON, LAT),
                                                    QgsPointXY(LON + 0.01, LAT)]))
    feature.setAttribute("fiberq_uuid", "c1")
    ok, (feature,) = cables.dataProvider().addFeatures([feature])
    assert ok
    project.addMapLayer(cables)
    relation = str(_uuid.uuid4())
    project.writeEntry("StuboviPlugin", "Relacije/relations_v1", json.dumps({"relations": [
        {"id": relation, "name": "R", "cables": [{"layer_id": cables.id(), "fid": feature.id()}]}]}))
    bundle = tmp_path / "b.gpkg"
    _export(project, bundle)

    project.writeEntry("StuboviPlugin", "Relacije/relations_v1", "{not json")
    result = _export(project, bundle)

    assert _rows(bundle, "SELECT uuid FROM fq_relation") == [(relation,)]
    assert any("relations could not be read" in w for w in result.warnings), result.warnings


def test_a_recorded_table_another_tool_removed_is_forgotten(project, tmp_path):
    """Once gone from the file it is not FiberQ's: a table another tool makes
    under that name later must not be dropped as FiberQ's own."""
    from qgis.core import QgsProviderRegistry

    _layer(project, "Poles", "p1")
    manholes = _layer(project, "Manholes", "m1")
    bundle = tmp_path / "b.gpkg"
    _export(project, bundle)
    QgsProviderRegistry.instance().providerMetadata("ogr").createConnection(
        str(bundle), {}).dropVectorTable("", "Manholes")
    project.removeMapLayer(manholes.id())
    _export(project, bundle)

    _foreign_table(bundle, "Manholes")
    _export(project, bundle)

    assert _feature_tables(bundle) == ["Manholes", "Poles"]


def test_a_layer_qgis_cannot_open_keeps_its_geojson_file(tmp_path):
    prj, qgs, _relation = _cable_project(tmp_path)
    folder = tmp_path / "geojson"
    assert InterchangeBundleWriter(prj).write_geojson(str(folder)).ok
    prj.clear()
    assert (folder / "cable.underground.geojson").is_file(), "premise"

    again = _reopened_without(tmp_path, qgs, tmp_path / "data" / "cables.gpkg")
    result = InterchangeBundleWriter(again).write_geojson(str(folder))
    again.clear()

    assert result.ok, result.errors
    assert (folder / "cable.underground.geojson").is_file()
