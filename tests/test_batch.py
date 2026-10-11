"""utils.batch.features_by_id reads through the edit buffer, as the per-fid scans did.

WP4 task 4.1, item PF-1 (and PF-2, which reuses it). The schematic view and the
latent-elements list found each feature by reading its layer from the top until
the fid came up. ``layer.getFeatures()`` reads through the layer's edit buffer,
so those scans saw what the user sees: a feature added and not yet saved, an
attribute or a geometry edited and not yet saved, and not a feature deleted
and not yet saved. The batched read must see exactly the same.

The XS city has no edit buffer, so no equivalence test on it can see this: a
batch that read the provider directly (``dataProvider().getFeatures()``) passed
the whole suite (measured). Asked here for every fid the layer shows, plus the
deleted one and one it never had, and compared with the scan, on a memory and
on a GeoPackage layer -- the two providers whose ``setFilterFids`` answer in
different orders (ascending fid, and Qt hash order).
"""
import pytest
from qgis.core import (QgsCoordinateTransformContext, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorFileWriter, QgsVectorLayer)


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.clear()
    yield prj
    prj.clear()


def _memory():
    layer = QgsVectorLayer("LineString?crs=EPSG:3857&field=naziv:string", "Underground cables", "memory")
    features = []
    for i in range(5):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(i, 0), QgsPointXY(i, 10)]))
        feature["naziv"] = "C%d" % i
        features.append(feature)
    ok, _added = layer.dataProvider().addFeatures(features)
    assert ok
    return layer


def _gpkg(tmp_path):
    path = str(tmp_path / "cables.gpkg")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    write = getattr(QgsVectorFileWriter, "writeAsVectorFormatV3", None) or QgsVectorFileWriter.writeAsVectorFormatV2
    assert write(_memory(), path, QgsCoordinateTransformContext(), options)[0] == 0
    layer = QgsVectorLayer(path, "Underground cables", "ogr")
    assert layer.isValid()
    return layer


def _seen(feature):
    return (feature.id(), feature["naziv"], feature.geometry().asWkt(1))


@pytest.mark.parametrize("kind", ["memory", "gpkg"])
def test_an_open_edit_buffer_reads_as_the_scan_read_it(project, tmp_path, kind):
    from fiberq.utils.batch import features_by_id

    layer = _memory() if kind == "memory" else _gpkg(tmp_path)
    project.addMapLayer(layer)
    saved = sorted(feature.id() for feature in layer.getFeatures())
    assert layer.startEditing()
    try:
        added = QgsFeature(layer.fields())
        added.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(50, 0), QgsPointXY(50, 10)]))
        added["naziv"] = "NEW"
        assert layer.addFeature(added)
        deleted, renamed, moved = saved[:3]
        assert layer.deleteFeature(deleted)
        assert layer.changeAttributeValue(renamed, layer.fields().indexFromName("naziv"), "EDITED")
        assert layer.changeGeometry(moved, QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(99, 99)]))
        asked = sorted({feature.id() for feature in layer.getFeatures()} | {deleted, 987654})
        assert min(asked) < 0, "premise: the unsaved feature is asked for"

        scanned = {}
        for fid in asked:
            for feature in layer.getFeatures():
                if feature.id() == fid:
                    scanned[fid] = _seen(feature)
                    break
        found = features_by_id((layer.id(), fid) for fid in asked).get(layer.id(), {})

        assert {fid: _seen(feature) for fid, feature in found.items()} == scanned
        assert deleted not in found and 987654 not in found
    finally:
        layer.rollBack()
