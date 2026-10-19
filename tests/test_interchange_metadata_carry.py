"""Bundle metadata FiberQ owns but does not always produce.

Unclaimed (WP3 code), found in the v1.6.0 review. Before FiberQ 1.6.0:

- the colour standard a bundle's fibre colours are derived from (spec 6.2) was
  dropped on import and replaced on export: a bundle drawn to another standard
  came back out saying TIA-598-C, beside -- when exported over -- the catalogue
  that defines the other one;
- keys that describe only an earlier write to the same file were carried
  forever: the five FiberQ's project export writes (its relations_json then
  disagrees with the bundle's own fq_relation) and a stale GeoJSON ``profile``.

Results are read back with sqlite3 as plain data.
"""
import json
import sqlite3
from contextlib import closing

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)

from fiberq.core.interchange_bundle import InterchangeBundleWriter, read_bundle_metadata
from fiberq.core.interchange_import import InterchangeBundleReader

LON, LAT = 21.90, 43.32
ACME = json.dumps({"catalogs": [{"name": "ACME-24", "colors": [{"name": "teal", "hex": "#008080"}]}]})
OWN = json.dumps({"catalogs": [{"name": "ZA-12", "colors": [{"name": "plava", "hex": "#0000ff"}]}]})


def _project():
    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    return project


@pytest.fixture
def project(qgis_app):
    prj = _project()
    yield prj
    prj.clear()


def _poles(project, uuid="p1"):
    poles = QgsVectorLayer("Point?crs=EPSG:4326&field=fiberq_uuid:string(64)", "Poles", "memory")
    feature = QgsFeature(poles.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    feature.setAttribute("fiberq_uuid", uuid)
    assert poles.dataProvider().addFeatures([feature])[0]
    project.addMapLayer(poles)
    return poles


def _export(project, path):
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    result = InterchangeBundleWriter(project).write(str(path), layers=layers)
    assert result.ok, result.errors
    return result


def _set_keys(path, keys):
    """Change metadata keys as another tool, or an earlier export, would."""
    with closing(sqlite3.connect(str(path))) as conn:
        for key, value in keys.items():
            conn.execute("INSERT OR REPLACE INTO _fiberq_metadata (key, value) VALUES (?, ?)",
                         (key, value))
        conn.commit()


def _acme_bundle(path):
    """A bundle drawn to ACME-24, with the catalogue that defines it."""
    source = _project()
    _poles(source)
    _export(source, path)
    source.clear()
    _set_keys(path, {"color_standard": "ACME-24", "color_catalog_json": ACME})
    return path


def test_the_colour_standard_and_catalogue_a_bundle_came_with_reach_the_next_one(project, tmp_path):
    bundle = _acme_bundle(tmp_path / "acme.gpkg")
    assert InterchangeBundleReader(project).read(str(bundle)).ok

    out = tmp_path / "out.gpkg"
    _export(project, out)

    metadata = read_bundle_metadata(str(out))
    assert metadata["color_standard"] == "ACME-24"
    assert json.loads(metadata["color_catalog_json"]) == json.loads(ACME)


def test_an_export_over_a_bundle_keeps_its_standard_while_the_project_has_none(project, tmp_path):
    bundle = _acme_bundle(tmp_path / "acme.gpkg")
    _poles(project, "p2")
    _export(project, bundle)
    metadata = read_bundle_metadata(str(bundle))
    assert metadata["color_standard"] == "ACME-24"
    assert json.loads(metadata["color_catalog_json"]) == json.loads(ACME)


def test_the_projects_own_catalogue_wins_and_the_one_that_came_goes(project, tmp_path):
    bundle = _acme_bundle(tmp_path / "acme.gpkg")
    project.writeEntry("StuboviPlugin", "ColorCatalogs/catalogs_v1", OWN)
    _poles(project, "p2")
    _export(project, bundle)
    metadata = read_bundle_metadata(str(bundle))
    assert metadata["color_standard"] == "ZA-12"
    assert "color_catalog_json" not in metadata


def test_keys_of_an_earlier_write_to_the_file_are_removed(project, tmp_path):
    bundle = tmp_path / "b.gpkg"
    _poles(project)
    _export(project, bundle)
    _set_keys(bundle, {
        "relations_json": json.dumps({"relations": [{"id": "old"}]}),
        "latent_elements_json": "{}", "plugin_settings_json": "{}",
        "export_timestamp": "2020-01-01T00:00:00", "project_version": "0.9",
        "profile": "geojson-lite",
        "acme_note": "another tool's",
    })

    _export(project, bundle)

    metadata = read_bundle_metadata(str(bundle))
    for key in ("relations_json", "latent_elements_json", "plugin_settings_json",
                "export_timestamp", "project_version", "profile"):
        assert key not in metadata, key
    assert metadata["acme_note"] == "another tool's"


# -- the GeoJSON profile's folder -------------------------------------------------
#
# Unclaimed (WP3 code), found in the v1.6.0 review: a GeoJSON export wrote its
# folder's _fiberq_metadata.json from this export's keys alone, so the keys
# another tool had stored there were lost -- what section 7 forbids, and what
# the GeoPackage profile has never done.


def _geojson(project, folder):
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    result = InterchangeBundleWriter(project).write_geojson(str(folder), layers=layers)
    assert result.ok, result.errors
    return result


def _folder_keys(folder):
    with open(folder / "_fiberq_metadata.json", encoding="utf-8") as handle:
        return json.load(handle)


def _set_folder_keys(folder, keys):
    metadata = _folder_keys(folder)
    metadata.update(keys)
    with open(folder / "_fiberq_metadata.json", "w", encoding="utf-8") as handle:
        json.dump(metadata, handle)


def test_a_geojson_export_keeps_the_keys_another_tool_stored_in_its_folder(project, tmp_path):
    folder = tmp_path / "geojson"
    _poles(project)
    _geojson(project, folder)
    _set_folder_keys(folder, {"acme_note": "another tool's", "acme_count": 3})

    result = _geojson(project, folder)

    metadata = _folder_keys(folder)
    assert metadata["acme_note"] == "another tool's"
    assert metadata["acme_count"] == 3
    assert "acme_note" in result.preserved


def test_a_geojson_folder_keeps_its_colour_standard_while_the_project_has_none(project, tmp_path):
    folder = tmp_path / "geojson"
    _poles(project)
    _geojson(project, folder)
    _set_folder_keys(folder, {"color_standard": "ACME-24", "color_catalog_json": ACME})

    _geojson(project, folder)

    metadata = _folder_keys(folder)
    assert metadata["color_standard"] == "ACME-24"
    assert json.loads(metadata["color_catalog_json"]) == json.loads(ACME)


def test_an_unreadable_folder_metadata_file_is_replaced_and_said_so(project, tmp_path):
    folder = tmp_path / "geojson"
    _poles(project)
    _geojson(project, folder)
    (folder / "_fiberq_metadata.json").write_text("{not json", encoding="utf-8")

    result = _geojson(project, folder)

    assert any("_fiberq_metadata.json could not be read" in w for w in result.warnings), (
        result.warnings)
    assert _folder_keys(folder)["format"] == "fiberq-interchange"
