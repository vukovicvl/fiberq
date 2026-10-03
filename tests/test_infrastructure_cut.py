"""Regression: 'Cut infrastructure' split of a GeoPackage line layer.

The split copied the parent's full attribute vector (including the GPKG primary
key 'fid') onto both halves, so committing failed with
'UNIQUE constraint failed: <layer>.fid' (1 deleted, 2 not added). It also copied
the parent's fiberq_uuid onto both halves, leaving them sharing one identity.

This drives the real split on a GPKG-backed layer and asserts the commit
succeeds, the two parts get distinct fids, and each gets its own fresh uuid.

The tests at the bottom cover the other half of the split: the length fields a
cut part is given. Those were measured planar and then written into every
length-ish field, so a 291 m route part stored 291.34 *kilometres* and a cut
cable's total lost its slack.
"""
import pytest
from qgis.core import (
    QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext,
    QgsCoordinateReferenceSystem, QgsProject,
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


def _fiberq_project():
    """QgsProject.instance() configured the way the cut tool reads it.

    The tool resolves the project itself, so this one test has to use the
    singleton. The ellipsoid matters: the cut used to measure with
    ``QgsProject.ellipsoid()`` raw, which on a fresh project is the string
    'NONE' and silently means map units -- 37% long in Web Mercator here.
    """
    from fiberq.utils.measure import clear_cache
    project = QgsProject.instance()
    project.clear()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    project.setEllipsoid("EPSG:7030")
    clear_cache()
    return project


def _line_layer(project, name, fields, attrs):
    """A one-feature line layer at Niš latitude, 400 map units long."""
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", name, "memory")
    layer.dataProvider().addAttributes([QgsField(f, QVariant.Double) for f in fields])
    layer.updateFields()
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(2437000, 5365000), QgsPointXY(2437400, 5365000)]))
    for key, value in attrs.items():
        feat.setAttribute(key, value)
    layer.dataProvider().addFeatures([feat])
    project.addMapLayer(layer)
    return layer, feat


def test_a_cut_route_part_stores_kilometres_in_the_kilometre_field(qgis_app, qgis_iface):
    """The second half of the old bug: metres were written into ``duzina_km``.

    ``_norm`` strips non-letters, so 'duzina_km' matched the 'duzina' token and
    a 291 m part was stored as 291.34 km. Manual QA step 10 is this assertion.
    """
    from fiberq.addons.infrastructure_cut import InfrastructureCutTool
    from fiberq.utils.measure import clear_cache, ground_length

    project = _fiberq_project()
    layer, feat = _line_layer(project, "Route", ["duzina", "duzina_km"],
                              {"duzina": 999.0, "duzina_km": 999.0})
    try:
        InfrastructureCutTool(qgis_iface)._update_length_fields(layer, feat)

        metres = ground_length(feat.geometry(), layer, project=project)
        assert metres == pytest.approx(291.3, abs=0.5), "ellipsoidal, not planar"
        assert feat["duzina"] == pytest.approx(metres)
        assert feat["duzina_km"] == pytest.approx(round(metres / 1000.0, 2))
    finally:
        project.clear()
        clear_cache()


def test_a_cut_cable_part_keeps_its_slack_in_the_total(qgis_app, qgis_iface):
    """The first half: 'total_len_m' matched the 'len' token and was clobbered.

    The part's total is its own length *plus* the slack it carries, and the
    slack itself is the user's number -- never rewritten.
    """
    from fiberq.addons.infrastructure_cut import InfrastructureCutTool
    from fiberq.utils.measure import clear_cache, ground_length

    project = _fiberq_project()
    layer, feat = _line_layer(project, "Underground cables",
                              ["duzina_m", "slack_m", "total_len_m"],
                              {"duzina_m": 999.0, "slack_m": 20.0, "total_len_m": 999.0})
    try:
        InfrastructureCutTool(qgis_iface)._update_length_fields(layer, feat)

        metres = ground_length(feat.geometry(), layer, project=project)
        assert feat["duzina_m"] == pytest.approx(metres)
        assert feat["slack_m"] == pytest.approx(20.0)
        assert feat["total_len_m"] == pytest.approx(metres + 20.0)
    finally:
        project.clear()
        clear_cache()


def test_a_cut_part_of_a_foreign_layer_still_gets_metres(qgis_app, qgis_iface):
    """The tool cuts any line layer, and those are measured too -- correctly.

    FiberQ has no schema for someone else's table, so the field names are the
    only clue: a name ending in 'km' gets kilometres, everything else metres,
    and the measurement is ellipsoidal either way.
    """
    from fiberq.addons.infrastructure_cut import InfrastructureCutTool
    from fiberq.utils.measure import clear_cache, ground_length

    project = _fiberq_project()
    layer, feat = _line_layer(project, "my_ducts", ["length_m", "duzina_km"],
                              {"length_m": 999.0, "duzina_km": 999.0})
    try:
        InfrastructureCutTool(qgis_iface)._update_length_fields(layer, feat)

        metres = ground_length(feat.geometry(), layer, project=project)
        assert feat["length_m"] == pytest.approx(round(metres, 3))
        assert feat["duzina_km"] == pytest.approx(round(metres / 1000.0, 2))
    finally:
        project.clear()
        clear_cache()
