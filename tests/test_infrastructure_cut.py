"""Regression: 'Cut infrastructure' split of a GeoPackage line layer.

The split copied the parent's full attribute vector (including the GPKG primary
key 'fid') onto both halves, so committing failed with
'UNIQUE constraint failed: <layer>.fid' (1 deleted, 2 not added). It also copied
the parent's fiberq_uuid onto both halves, leaving them sharing one identity.

This drives the real split on a GPKG-backed layer and asserts the commit
succeeds, the two parts get distinct fids, and each gets its own fresh uuid.
"""
from qgis.core import (
    QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext,
)
from qgis.PyQt.QtCore import QVariant


def _gpkg_line_layer(tmp_path):
    """A single-feature GeoPackage LineString layer with a fiberq_uuid value."""
    mem = QgsVectorLayer("LineString?crs=EPSG:3857", "cables", "memory")
    pr = mem.dataProvider()
    pr.addAttributes([QgsField("naziv", QVariant.String),
                      QgsField("fiberq_uuid", QVariant.String)])
    mem.updateFields()
    f = QgsFeature(mem.fields())
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(10, 0)]))
    f["naziv"] = "c1"
    f["fiberq_uuid"] = "PARENT-UUID"
    pr.addFeature(f)

    path = str(tmp_path / "cables.gpkg")
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = "cables"
    QgsVectorFileWriter.writeAsVectorFormatV3(mem, path, QgsCoordinateTransformContext(), opts)
    uri = f"{path}|layername=cables"
    return QgsVectorLayer(uri, "cables", "ogr"), uri


def test_cut_split_avoids_fid_collision_and_gives_fresh_uuids(qgis_app, qgis_iface, tmp_path):
    from fiberq.addons.infrastructure_cut import InfrastructureCutTool
    layer, uri = _gpkg_line_layer(tmp_path)
    assert layer.isValid() and layer.featureCount() == 1
    feat = next(layer.getFeatures())
    parent_uuid = feat["fiberq_uuid"]

    tool = InfrastructureCutTool(qgis_iface)
    layer.startEditing()
    assert tool._split_feature_at_point(layer, feat, QgsPointXY(5, 0))
    # The bug surfaced here: the two new features reused the parent's fid.
    assert layer.commitChanges(), f"commit failed (fid collision?): {layer.commitErrors()}"

    # Re-read from disk: two parts, distinct fids, distinct fresh uuids.
    reread = QgsVectorLayer(uri, "cables", "ogr")
    feats = list(reread.getFeatures())
    assert len(feats) == 2, f"expected 2 parts, got {len(feats)}"
    fids = [f["fid"] for f in feats]
    uuids = [f["fiberq_uuid"] for f in feats]
    assert len(set(fids)) == 2, f"fid collision: {fids}"
    assert all(u and str(u).strip() for u in uuids), f"missing uuid on a part: {uuids}"
    assert len(set(uuids)) == 2, f"the two parts share one uuid: {uuids}"
    assert parent_uuid not in uuids, "a part reused the parent's uuid"
