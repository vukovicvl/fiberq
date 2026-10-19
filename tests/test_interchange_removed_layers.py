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

    _geojson(project, folder)

    assert outside.is_file()
    assert metadata_path.is_file()
