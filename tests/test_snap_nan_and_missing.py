"""The route and pipe tools' snaps survive a NaN vertex and a feature without a geometry.

Branch 13, unclaimed. Both tools find what a click or a move snaps to by
measuring every node and every route vertex and midpoint, keeping the nearest
in a running minimum seeded with the first distance met. Two plain bugs:

* a vertex that is not a number gives a distance that is not a number, and met
  first it became the best so far. ``d < nan`` is never true, so nothing after
  it could replace it, and the callers' ``nan < tolerance`` then refused every
  snap: one such vertex switched the snap off for the whole project;
* the pipe tool read each layer inside one ``try``, so a pole without a
  geometry -- QGIS makes one whenever a row is added in the attribute table --
  raised out of ``asPoint()`` and ended the search of that layer: no pole after
  it was ever snapped to. A route without a geometry did the same to the routes.

A point or polygon stored in the Route layer -- GDAL accepts one into a
LINESTRING GeoPackage table, with a warning, and an edit buffer takes one too --
raised TypeError out of ``asPolyline()`` and ended both tools' route search the
same way.

Each test puts the odd feature first in its layer and a good one in reach after
it. On the parent every one of them snaps to nothing.
"""
import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas

from fiberq.tools.pipe_tool import PipePlaceTool
from fiberq.tools.route_tool import ManualRouteTool

NAN = float("nan")
#: Where every test puts the cursor, at one map unit per pixel: the good
#: feature is 2.5 away, inside both tools' tolerances (15 and 20 px).
CURSOR = QgsPointXY(100.5, 100.0)


class _Iface:
    def __init__(self, canvas):
        self._canvas = canvas

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return None

    def messageBar(self):
        return self

    def pushInfo(self, *args):
        pass

    def pushWarning(self, *args):
        pass


@pytest.fixture(autouse=True)
def canvas_not_rendering(qgis_canvas):
    """pytest-qgis's canvas renders the project's layers in a worker thread,
    which made GeoPackage tests flaky on QGIS 4.2 (branch 12)."""
    qgis_canvas.setRenderFlag(False)
    yield
    qgis_canvas.setRenderFlag(True)


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture
def iface(qgis_app):
    """A private canvas at one map unit per pixel around the cursor."""
    view = QgsMapCanvas()
    view.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    view.resize(800, 800)
    view.show()
    size = view.mapSettings().outputSize()
    view.setExtent(QgsRectangle(CURSOR.x() - size.width() / 2.0, CURSOR.y() - size.height() / 2.0,
                                CURSOR.x() + size.width() / 2.0, CURSOR.y() + size.height() / 2.0))
    assert view.mapUnitsPerPixel() == pytest.approx(1.0, abs=0.01)
    yield _Iface(view)
    view.hide()


def _layer(project, tmp_path, storage, uri, name, geometries):
    """A layer holding ``geometries`` in this order (fids 1, 2, ...), in the project; None = no geometry.

    A GeoPackage's rows are written by its provider: the file writer would
    store a missing geometry as an empty one (code review), the provider
    stores NULL.
    """
    layer = QgsVectorLayer(f"{uri}?crs=EPSG:3857&field=naziv:string", name, "memory")
    if storage == "gpkg":
        path = tmp_path / f"{name}.gpkg"
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = name
        written = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsCoordinateTransformContext(), options)
        assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
        layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
        assert layer.isValid()
    features = []
    for geometry in geometries:
        feature = QgsFeature(layer.fields())
        if geometry is not None:
            feature.setGeometry(geometry)
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    if storage == "gpkg":
        layer = QgsVectorLayer(layer.source(), name, "ogr")
        assert layer.isValid()
        stored = [f.geometry() for f in sorted(layer.getFeatures(), key=lambda f: f.id())]
        assert [g.isNull() for g in stored] == [g is None for g in geometries], [g.asWkt() for g in stored]
    project.addMapLayer(layer)
    return layer


def _line(*points):
    """Built from QgsPoint so a NaN survives: fromWkt turns one into a null geometry."""
    return QgsGeometry(QgsLineString([QgsPoint(x, y) for x, y in points]))


def _xy(point):
    return (round(point.x(), 6), round(point.y(), 6))


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_route_starting_at_nan_no_longer_switches_the_route_snap_off(project, tmp_path, iface, storage):
    _layer(project, tmp_path, storage, "LineString", "Route", [
        _line((NAN, NAN), (5000, 5000)), _line((103, 100), (120, 100))])
    point, distance = ManualRouteTool(iface, None)._find_snap_point(CURSOR)
    assert (_xy(point), distance) == ((103.0, 100.0), 2.5)


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_route_starting_at_nan_no_longer_switches_the_pipe_snap_off(project, tmp_path, iface, storage):
    _layer(project, tmp_path, storage, "LineString", "Route", [
        _line((NAN, NAN), (5000, 5000)), _line((103, 100), (120, 100))])
    assert _xy(PipePlaceTool(iface, None, "PE", {})._snap_point(CURSOR)) == (103.0, 100.0)


def test_a_pole_at_nan_no_longer_switches_the_pipe_snap_off(project, tmp_path, iface):
    """A NaN point reads back as an empty one, whose asPoint() is (nan, nan)."""
    _layer(project, tmp_path, "memory", "Point", "Poles", [
        QgsGeometry(QgsPoint(NAN, NAN)), QgsGeometry.fromPointXY(QgsPointXY(101, 100))])
    assert _xy(PipePlaceTool(iface, None, "PE", {})._snap_point(CURSOR)) == (101.0, 100.0)


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_pole_without_a_geometry_no_longer_hides_the_poles_after_it(project, tmp_path, iface, storage):
    _layer(project, tmp_path, storage, "Point", "Poles", [None, QgsGeometry.fromPointXY(QgsPointXY(101, 100))])
    assert _xy(PipePlaceTool(iface, None, "PE", {})._snap_point(CURSOR)) == (101.0, 100.0)


def test_a_multipart_pole_no_longer_hides_the_poles_after_it(project, tmp_path, iface):
    """``asPoint()`` raises TypeError for a MultiPoint of two points, on every version."""
    _layer(project, tmp_path, "memory", "MultiPoint", "Poles", [
        QgsGeometry.fromWkt("MultiPoint ((500 500),(600 600))"), QgsGeometry.fromWkt("MultiPoint ((101 100))")])
    found = _xy(PipePlaceTool(iface, None, "PE", {})._snap_point(CURSOR))
    # A one-point MultiPoint is read by asPoint() on 3.40+ and raises on 3.22:
    # there the cursor stays where it was. Either way the search went on.
    from qgis.core import Qgis
    assert found == ((101.0, 100.0) if Qgis.QGIS_VERSION_INT >= 32400 else _xy(CURSOR))


def test_a_route_without_a_geometry_no_longer_hides_the_routes_after_it(project, tmp_path, iface):
    _layer(project, tmp_path, "memory", "LineString", "Route", [None, _line((103, 100), (120, 100))])
    assert _xy(PipePlaceTool(iface, None, "PE", {})._snap_point(CURSOR)) == (103.0, 100.0)


@pytest.mark.parametrize("tool", ["route", "pipe"])
def test_a_nan_vertex_after_the_best_still_changes_nothing(project, tmp_path, iface, tool):
    """The pin on the other side: met after a real distance, a NaN never
    replaced anything, and the good route keeps its snap."""
    _layer(project, tmp_path, "memory", "LineString", "Route", [
        _line((103, 100), (120, 100)), _line((NAN, NAN), (5000, 5000))])
    if tool == "route":
        point, distance = ManualRouteTool(iface, None)._find_snap_point(CURSOR)
        assert (_xy(point), distance) == ((103.0, 100.0), 2.5)
    else:
        assert _xy(PipePlaceTool(iface, None, "PE", {})._snap_point(CURSOR)) == (103.0, 100.0)


def _point_first_in_routes(project, tmp_path, storage):
    """A Route layer whose first feature in scan order is a point, then a good route."""
    good = QgsFeature()
    good.setGeometry(_line((103, 100), (120, 100)))
    odd = QgsFeature()
    odd.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(99999, 99999)))
    if storage == "gpkg":
        empty = QgsVectorLayer("LineString?crs=EPSG:3857&field=naziv:string", "Route", "memory")
        path = tmp_path / "point_first.gpkg"
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = "Route"
        written = QgsVectorFileWriter.writeAsVectorFormatV3(empty, str(path), QgsCoordinateTransformContext(), options)
        assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
        layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
        for feature in (odd, good):
            feature.setFields(layer.fields(), True)
            assert layer.dataProvider().addFeatures([feature])[0]
        layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
        assert layer.isValid()
        first = min(layer.getFeatures(), key=lambda f: f.id())
        assert first.geometry().type() == 0, first.geometry().asWkt()   # the point, stored, read first
        project.addMapLayer(layer)
        return layer
    layer = _layer(project, tmp_path, "memory", "LineString", "Route", [_line((103, 100), (120, 100))])
    assert layer.startEditing()
    odd.setFields(layer.fields(), True)
    assert layer.addFeature(odd)      # an added feature comes first in the whole read
    return layer


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_point_in_the_route_layer_no_longer_hides_the_routes_after_it(project, tmp_path, iface, storage):
    layer = _point_first_in_routes(project, tmp_path, storage)
    try:
        point, distance = ManualRouteTool(iface, None)._find_snap_point(CURSOR)
        assert (_xy(point), distance) == ((103.0, 100.0), 2.5)
        assert _xy(PipePlaceTool(iface, None, "PE", {})._snap_point(CURSOR)) == (103.0, 100.0)
    finally:
        if layer.isEditable():
            layer.rollBack()


def test_a_multipart_pole_in_a_point_layer_no_longer_hides_the_poles_after_it(project, tmp_path, iface):
    """A Point layer takes a MultiPoint too -- the memory provider and a
    GeoPackage POINT table check only the dimension -- and asPoint() raises
    TypeError for it on every version, 3.22 included (round-4 review)."""
    _layer(project, tmp_path, "memory", "Point", "Poles", [
        QgsGeometry.fromWkt("MultiPoint ((500 500),(600 600))"), QgsGeometry.fromPointXY(QgsPointXY(101, 100))])
    assert _xy(PipePlaceTool(iface, None, "PE", {})._snap_point(CURSOR)) == (101.0, 100.0)
