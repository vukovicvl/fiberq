"""A Service Area's area and perimeter are measured on the ground.

Unclaimed (WP2-era code), found in the v1.6.0 docs review. Both ways of making
a Service Area built a QgsDistanceArea of their own:
- they ran ``if prj.ellipsoid(): d.setEllipsoid(...)``, where 'NONE' is a
  non-empty string;
- they called ``d.setEllipsoidalMode(True)``, which QGIS 3 no longer has, so
  the call raised into a swallowed ``except``.

With the project ellipsoid left at 'NONE', as in a project nobody configured,
``area_m2`` and ``perim_m`` were stored in map units: in Web Mercator at 45
degrees north the area was twice the ground figure. They now come from
``utils.measure``, like every length the plugin stores: the project's
ellipsoid, else the one its CRS names.
"""
import math

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsDistanceArea, QgsFeature, QgsGeometry,
    QgsPointXY, QgsProject, QgsVectorLayer,
)

#: Web Mercator northing of 45 degrees north on the sphere EPSG:3857 projects onto.
Y45 = 6378137.0 * math.log(math.tan(math.pi / 4 + math.radians(45) / 2))
X0 = 2000000.0
SIDE = 1000.0   # map units


def _square():
    return [QgsPointXY(X0, Y45), QgsPointXY(X0 + SIDE, Y45),
            QgsPointXY(X0 + SIDE, Y45 + SIDE), QgsPointXY(X0, Y45 + SIDE)]


def _expected():
    """The ground figures, measured independently of the plugin."""
    measurer = QgsDistanceArea()
    measurer.setSourceCrs(QgsCoordinateReferenceSystem("EPSG:3857"),
                          QgsProject.instance().transformContext())
    measurer.setEllipsoid("EPSG:7030")
    polygon = QgsGeometry.fromPolygonXY([_square()])
    return measurer.measureArea(polygon), measurer.measurePerimeter(polygon)


class _Core:
    def __init__(self, iface):
        self.iface = iface
        self.undo_manager = None


@pytest.fixture
def service_area(qgis_iface):
    """A Web Mercator project with its ellipsoid left at 'NONE', and the layer."""
    from fiberq.utils import measure

    project = QgsProject.instance()
    old_crs, old_ellipsoid = project.crs(), project.ellipsoid()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    project.setEllipsoid("NONE")
    measure.clear_cache()
    layer = QgsVectorLayer(
        "Polygon?crs=EPSG:3857&field=name:string&field=created_at:string"
        "&field=area_m2:double&field=perim_m:double&field=count:integer"
        "&field=fiberq_uuid:string", "Service Area", "memory")
    assert layer.isValid()
    project.addMapLayer(layer)
    try:
        yield layer
    finally:
        project.removeMapLayer(layer.id())
        project.setCrs(old_crs)
        project.setEllipsoid(old_ellipsoid)
        measure.clear_cache()


def _stored(layer):
    features = list(layer.getFeatures())
    assert len(features) == 1
    return features[0]["area_m2"], features[0]["perim_m"]


def _assert_ground(area, perimeter):
    expected_area, expected_perimeter = _expected()
    # The premise: the ground figure really differs from the map-unit one.
    assert expected_area < 0.6 * SIDE * SIDE
    assert area == pytest.approx(expected_area, rel=1e-6)
    assert perimeter == pytest.approx(expected_perimeter, rel=1e-6)


def test_a_drawn_service_area_stores_ground_figures(service_area, qgis_iface, monkeypatch):
    from fiberq.tools import region_tool

    monkeypatch.setattr(region_tool.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Drawn", True)))
    tool = region_tool.DrawRegionPolygonTool(qgis_iface, _Core(qgis_iface))
    tool.points = _square()
    tool._finish_polygon()
    _assert_ground(*_stored(service_area))


def test_a_service_area_from_a_selection_stores_ground_figures(service_area, qgis_iface,
                                                               monkeypatch):
    from fiberq.core import layer_manager

    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(layer_manager.QMessageBox, name, staticmethod(lambda *a, **k: None))
    objects = QgsVectorLayer("Polygon?crs=EPSG:3857&field=naziv:string", "Objects", "memory")
    feature = QgsFeature(objects.fields())
    feature.setGeometry(QgsGeometry.fromPolygonXY([_square()]))
    assert objects.dataProvider().addFeatures([feature])[0]
    QgsProject.instance().addMapLayer(objects)
    try:
        objects.selectAll()
        assert layer_manager._create_region_from_selection(_Core(qgis_iface), "Selected", 0)
        _assert_ground(*_stored(service_area))
    finally:
        QgsProject.instance().removeMapLayer(objects.id())
