"""The placement snaps skip a line a box query can miss. A behaviour change, agreed 2026-10-12.

Branch 13, unclaimed, ahead of WP4 4.1 item PF-5. Four searches find what a
placement snaps to: FiberQ's fallback snap (``PlacementSnapper._fallback``:
the element, pole, manhole and joint-closure tools), the route tool, the pipe
tool and the breakpoint tool. PF-5 makes each read only the features whose box
comes near the cursor, and for most geometry that answers exactly what reading
every feature did. Not for a line whose box does not hold it (measured on QGIS
3.22.16, 3.44.15 and 4.2.3, a box of half-side 1 m around a point 0.3 m from a
good vertex):

* a coordinate that is not a finite number: a GeoPackage's box query misses
  the line when it is the first vertex or in a part of a multi-part line, a
  memory layer's with a spatial index of its own wherever it is (a shapefile
  cannot hold one: GDAL refuses to write it);
* a MultiLineString with a one-vertex part, on 3.22 (GeoPackage, shapefile);
* an arc through three points in a row, whose QGIS box is garbage, and on 3.22
  an arc starting exactly at (0, 0), whose box leaves that start out;
* a MultiPoint with a part QGIS reads as empty (a coordinate that is not a
  number): a GeoPackage's box query left it out when that part's other
  coordinate lay far away (round-5 review, 3.22.16 and 4.2.3);
* a GeometryCollection or a polygon with such a part or ring, which GDAL boxes
  the same way (round-6 review).

The parent snapped to each of these through its good vertices and segments.
Now every search skips them, reading the whole layer or not
(``utils.geometry.held_by_its_box``), so PF-5's box query answers what the scan
does. That is a change in what a user sees, for broken or degenerate geometry
only, and it was agreed as such -- it fixes nothing on its own (the MultiPoints
the same day, after the round-5 review; the collections and polygons on
2026-10-13, after round 6). Points are not affected, nor is a MultiPoint of
points, a well-formed collection or polygon, a lone one-vertex line, or an arc
QGIS boxes correctly.

The check is asked only of a feature that would win *within the tolerance*:
the review of the design measured a check asked of every improvement on a
whole-layer scan at +10-14 % a move on 3-vertex routes and +47-49 % on
83-vertex ones, because fids follow the street and the running best improves
dozens of times a move. And it never asks a CompoundCurve for its own
coordinates: with an empty component its nCoordinates() is a SIGSEGV on QGIS
4.0 and 4.2, and its vertices() never ends on every version once the empty
components outnumber what its vertices allow -- one vertex and two empty arcs
(code reviews); such a curve is held, as QGIS's own calls on it are safe and
the parent snapped to it.
"""
import math

import pytest
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsGeometryCollection,
    QgsLineString,
    QgsMultiLineString,
    QgsMultiPoint,
    QgsPoint,
    QgsPointLocator,
    QgsPointXY,
    QgsPolygon,
    QgsProject,
    QgsRectangle,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QPoint, Qt

import fiberq.tools.base as base
import fiberq.tools.breakpoint_tool as breakpoint_tool
import fiberq.tools.pipe_tool as pipe_tool
import fiberq.tools.route_tool as route_tool
from fiberq.tools.base import PlacementSnapper
import fiberq.utils.spatial as spatial
from fiberq.utils.geometry import held_by_its_box

NAN = float("nan")
#: Where the cursor is, at one map unit per pixel: 0.5 from the broken line's
#: good vertex (100, 100) and on its good segment; 2.5 from the good line's
#: (103, 100). Both well inside every tolerance here.
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


def _canvas(centre=CURSOR):
    view = QgsMapCanvas()
    view.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    view.resize(800, 800)
    view.show()
    size = view.mapSettings().outputSize()
    view.setExtent(QgsRectangle(centre.x() - size.width() / 2.0, centre.y() - size.height() / 2.0,
                                centre.x() + size.width() / 2.0, centre.y() + size.height() / 2.0))
    assert view.mapUnitsPerPixel() == pytest.approx(1.0, abs=0.01)
    return view


@pytest.fixture
def canvas(qgis_app):
    view = _canvas()
    yield view
    view.hide()


def _line(*points):
    """Built from QgsPoint so a NaN survives: fromWkt turns one into a null geometry."""
    return QgsGeometry(QgsLineString([QgsPoint(x, y) for x, y in points]))


def _multi(*parts):
    shape = QgsMultiLineString()
    for part in parts:
        shape.addGeometry(QgsLineString([QgsPoint(x, y) for x, y in part]))
    return QgsGeometry(shape)


def _layer(project, tmp_path, storage, uri, name, geometries):
    """A layer holding ``geometries`` in this order (fids 1, 2, ...), in the project."""
    layer = QgsVectorLayer(f"{uri}?crs=EPSG:3857&field=naziv:string", name, "memory")
    features = []
    for geometry in geometries:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    if storage == "gpkg":
        path = tmp_path / f"{name}.gpkg"
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = name
        written = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsCoordinateTransformContext(), options)
        assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
        layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
        assert layer.isValid()
    project.addMapLayer(layer)
    return layer


def _xy(point):
    return None if point is None else (round(point.x(), 6), round(point.y(), 6))


#: Each holds the good segment (100, 100)-(110, 100) through the cursor, plus
#: what a box query cannot see.
BROKEN = {
    "nan first vertex": ("LineString", lambda: _line((NAN, NAN), (100, 100), (110, 100))),
    "nan last vertex": ("LineString", lambda: _line((100, 100), (110, 100), (NAN, NAN))),
    "nan in the middle": ("LineString", lambda: _line((100, 100), (110, 100), (NAN, NAN), (130, 100))),
    "infinite vertex": ("LineString", lambda: _line((100, 100), (110, 100), (math.inf, 100))),
    "nan part": ("MultiLineString", lambda: _multi([(100, 100), (110, 100)], [(NAN, NAN), (3000, 3000)])),
    "one-vertex part": ("MultiLineString", lambda: _multi([(100, 100), (110, 100)], [(500, 500)])),
}
GOOD = {"LineString": lambda: _line((103, 100), (120, 100)),
        "MultiLineString": lambda: _multi([(103, 100), (120, 100)])}


def _routes(project, tmp_path, storage, case):
    uri, broken = BROKEN[case]
    layer = _layer(project, tmp_path, storage, uri, "Route", [broken(), GOOD[uri]()])
    return layer, max(f.id() for f in layer.getFeatures())


def _hover(tool, canvas, point):
    tool.toMapCoordinates = lambda _pos: QgsPointXY(point)
    tool.canvasMoveEvent(QgsMapMouseEvent(canvas, QEvent.Type.MouseMove, QPoint(1, 1), Qt.MouseButton.NoButton,
                                          Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))


# ---------------------------------------------------------------------------
# Each search skips them
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("storage", ["memory", "gpkg"])
@pytest.mark.parametrize("case", sorted(BROKEN))
def test_the_fallback_snap_skips_a_line_a_box_can_miss(project, tmp_path, canvas, storage, case):
    """The parent snapped to the broken line's good vertex at (100, 100)."""
    _, good = _routes(project, tmp_path, storage, case)
    match = PlacementSnapper(canvas, line_layers=("Route",), pixels=10)._fallback(CURSOR)
    assert match.isValid()
    assert (_xy(match.point()), match.featureId()) == ((103.0, 100.0), good)


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
@pytest.mark.parametrize("case", sorted(BROKEN))
def test_the_route_tool_skips_a_line_a_box_can_miss(project, tmp_path, canvas, storage, case):
    _routes(project, tmp_path, storage, case)
    point, distance = route_tool.ManualRouteTool(_Iface(canvas), None)._find_snap_point(CURSOR)
    assert (_xy(point), distance) == ((103.0, 100.0), 2.5)


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
@pytest.mark.parametrize("case", sorted(BROKEN))
def test_the_pipe_tool_skips_a_line_a_box_can_miss(project, tmp_path, canvas, storage, case):
    _routes(project, tmp_path, storage, case)
    assert _xy(pipe_tool.PipePlaceTool(_Iface(canvas), None, "PE", {})._snap_point(CURSOR)) == (103.0, 100.0)


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
@pytest.mark.parametrize("case", sorted(BROKEN))
def test_the_breakpoint_tool_skips_a_line_a_box_can_miss(project, tmp_path, canvas, storage, case):
    """The broken line ran through the cursor (distance 0) and won."""
    _, good = _routes(project, tmp_path, storage, case)
    tool = breakpoint_tool.BreakpointTool(canvas, _Iface(canvas), None)
    _hover(tool, canvas, CURSOR)
    assert tool.snap_info is not None and tool.snap_info["feat"].id() == good


def test_an_arc_through_three_points_in_a_row_is_skipped(project, tmp_path, canvas):
    """QGIS boxes an arc from the circle through its points; three in a row
    have none, and the box is whatever memory held (a memory layer keeps a
    digitised curve as a curve, whatever its declared type)."""
    _layer(project, tmp_path, "memory", "LineString", "Route", [
        QgsGeometry.fromWkt("CircularString (100 100, 110 100, 120 100)"), GOOD["LineString"]()])
    match = PlacementSnapper(canvas, line_layers=("Route",), pixels=10)._fallback(CURSOR)
    assert _xy(match.point()) == (103.0, 100.0)


@pytest.mark.parametrize("wkt", ["CircularString (0 0, 50 20, 100 0)",
                                 "CompoundCurve (CircularString (0 0, 50 20, 100 0), (100 0, 200 0))"])
def test_an_arc_starting_at_the_origin_is_skipped_only_where_qgis_boxes_it_wrong(project, tmp_path, wkt):
    """3.22 grows an arc's box from the rectangle (0, 0, 0, 0), which it takes
    for an empty one, so the box of this arc leaves (0, 0) out: (50, 0, 100, 20).
    3.44 and 4.2 box it (0, 0, 100, 20) and keep it."""
    view = _canvas(QgsPointXY(0.3, 0))
    _layer(project, tmp_path, "memory", "LineString", "Route", [
        QgsGeometry.fromWkt(wkt), _line((0, 3), (40, 3))])
    match = PlacementSnapper(view, line_layers=("Route",), pixels=10)._fallback(QgsPointXY(0.3, 0))
    held = held_by_its_box(QgsGeometry.fromWkt(wkt), 5.0)
    assert held == (Qgis.QGIS_VERSION_INT >= 32400)
    assert _xy(match.point()) == ((0.0, 0.0) if held else (0.0, 3.0))
    view.hide()


# ---------------------------------------------------------------------------
# What is not skipped
# ---------------------------------------------------------------------------

def test_an_arc_qgis_boxes_correctly_is_still_snapped_to(project, tmp_path, canvas):
    _layer(project, tmp_path, "memory", "LineString", "Route", [
        QgsGeometry.fromWkt("CircularString (100 100, 110 110, 120 100)"), GOOD["LineString"]()])
    match = PlacementSnapper(canvas, line_layers=("Route",), pixels=10)._fallback(CURSOR)
    assert _xy(match.point()) == (100.0, 100.0)


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_lone_one_vertex_line_is_still_snapped_to(project, tmp_path, canvas, storage):
    """Every box query returns it, so nothing needs it skipped."""
    _layer(project, tmp_path, storage, "LineString", "Route", [_line((100, 100)), GOOD["LineString"]()])
    match = PlacementSnapper(canvas, line_layers=("Route",), pixels=10)._fallback(CURSOR)
    assert _xy(match.point()) == (100.0, 100.0)


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
@pytest.mark.parametrize("broken", [(NAN, NAN), (5000, NAN), (NAN, 100)])
def test_a_multipoint_with_an_empty_part_is_skipped(project, tmp_path, canvas, storage, broken):
    """A part with a coordinate that is not a number reads back as an empty
    point, and a GeoPackage's box query left out such a MultiPoint when the
    part's other coordinate lay far away (round-5 review, 3.22.16 and 4.2.3):
    agreed 2026-10-12, the snaps turn it away like the broken lines. The
    parent snapped to its good part at (100, 100)."""
    shape = QgsMultiPoint()
    shape.addGeometry(QgsPoint(100, 100))
    shape.addGeometry(QgsPoint(*broken))
    _layer(project, tmp_path, storage, "MultiPoint", "Poles",
           [QgsGeometry(shape), QgsGeometry.fromWkt("MultiPoint ((103 100))")])
    match = PlacementSnapper(canvas, point_layers=("Poles",), pixels=10)._fallback(CURSOR)
    assert _xy(match.point()) == (103.0, 100.0)


def _rows_written_by_qgis(project, tmp_path, uri, name, geometries):
    """A GeoPackage table declared ``uri`` holding ``geometries`` as written through QGIS's own provider, which
    stores a collection in a POINT table and a polygon in a LINESTRING one as they are."""
    empty = QgsVectorLayer(f"{uri}?crs=EPSG:3857&field=naziv:string", name, "memory")
    path = tmp_path / f"{name}.gpkg"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    written = QgsVectorFileWriter.writeAsVectorFormatV3(empty, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
    for geometry in geometries:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        assert layer.dataProvider().addFeatures([feature])[0]
    layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
    assert layer.isValid()
    project.addMapLayer(layer)
    return layer


@pytest.mark.parametrize("odd", ["collection with a point at nan", "polygon with a hole at nan"])
def test_a_collection_or_a_polygon_with_a_broken_part_is_skipped(project, tmp_path, canvas, odd):
    """GDAL boxes a collection or a polygon with a part or a ring that is not a
    number the way it boxes such a MultiPoint, so a GeoPackage's box query can
    leave it out (round-6 review, 3.22.16 to 4.2.3): agreed 2026-10-13, the
    snaps turn it away, judging a collection by its parts and a polygon by its
    rings. The parent snapped to its good vertex at (100, 100)."""
    if odd.startswith("collection"):
        _rows_written_by_qgis(project, tmp_path, "Point", "Poles", [
            _collection(QgsPoint(100, 100), QgsPoint(5000, NAN)), QgsGeometry.fromWkt("Point (103 100)")])
        snapper = PlacementSnapper(canvas, point_layers=("Poles",), pixels=10)
    else:
        _rows_written_by_qgis(project, tmp_path, "LineString", "Route", [
            _polygon_with_a_nan_hole(100, 100), GOOD["LineString"]()])
        snapper = PlacementSnapper(canvas, line_layers=("Route",), pixels=10)
    assert _xy(snapper._fallback(CURSOR).point()) == (103.0, 100.0)


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_multipoint_of_points_is_still_snapped_to(project, tmp_path, canvas, storage):
    _layer(project, tmp_path, storage, "MultiPoint", "Poles",
           [QgsGeometry.fromWkt("MultiPoint ((100 100),(5000 100))"), QgsGeometry.fromWkt("MultiPoint ((103 100))")])
    match = PlacementSnapper(canvas, point_layers=("Poles",), pixels=10)._fallback(CURSOR)
    assert _xy(match.point()) == (100.0, 100.0)


@pytest.mark.parametrize("wkt", [
    "Point (100 100)",
    "Point (0 0)",
    "MultiPoint ((0 0),(100 100))",
    "LineString (0 0, 10 0)",
    "LineString (0 0, 0 10)",
    "LineString (0 0, 0 0)",
    "LineString (1 1)",
    "LineString M (0 0 1, 10 0 2)",
    "LineString Z (0 0 1, 10 0 2)",
    "MultiLineString ((0 0, 10 0),(20 0, 30 0, 40 5))",
    "MultiLineString ((0 0, 0 0),(100 100, 110 100))",
    "CircularString (0 2, 5 7, 10 2)",
    "CompoundCurve (CircularString (0 2, 5 7, 10 2), (10 2, 20 2))",
    "MultiCurve (CircularString (0 2, 5 7, 10 2), LineString (20 0, 30 0))",
    "Polygon ((0 0, 10 0, 10 10, 0 0))",
    "Polygon ((0 0, 10 0, 10 10, 0 0),(2 1, 3 1, 3 2, 2 1))",
    "MultiPolygon (((0 0, 10 0, 10 10, 0 0)),((20 0, 30 0, 30 10, 20 0)))",
    "GeometryCollection (Point (0 0), LineString (0 0, 10 0), Polygon ((0 0, 10 0, 10 10, 0 0)))",
])
def test_ordinary_geometry_is_held_by_its_box(wkt):
    assert held_by_its_box(QgsGeometry.fromWkt(wkt), 1.0)


def test_an_empty_line_part_is_held():
    """An empty part is no part at all: every box query returned the rest.
    Asked for its vertices it answers a NaN one, which the check must not
    take for a broken coordinate."""
    shape = QgsMultiLineString()
    shape.addGeometry(QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0)]))
    shape.addGeometry(QgsLineString())
    assert held_by_its_box(QgsGeometry(shape), 1.0)


def _collection(*parts):
    shape = QgsGeometryCollection()
    for part in parts:
        shape.addGeometry(part)
    return QgsGeometry(shape)


def _polygon_with_a_nan_hole(x, y):
    """A 10 m square from (x, y), its hole starting at NaN."""
    exterior = QgsLineString([QgsPoint(x, y), QgsPoint(x + 10, y), QgsPoint(x + 10, y + 10), QgsPoint(x, y + 10),
                              QgsPoint(x, y)])
    hole = QgsLineString([QgsPoint(NAN, y + 2), QgsPoint(x + 4, y + 2), QgsPoint(x + 4, y + 4), QgsPoint(NAN, y + 2)])
    # setExteriorRing and addInteriorRing take the rings over on every version;
    # 3.22's QgsPolygon(exterior, rings) binding does not, and they were freed twice.
    polygon = QgsPolygon()
    polygon.setExteriorRing(exterior)
    polygon.addInteriorRing(hole)
    return QgsGeometry(polygon)


def _multipoint(*points):
    shape = QgsMultiPoint()
    for x, y in points:
        shape.addGeometry(QgsPoint(x, y))
    return QgsGeometry(shape)


@pytest.mark.parametrize("make", [
    lambda: QgsGeometry(),
    lambda: QgsGeometry.fromWkt("LineString EMPTY"),
    lambda: _line((NAN, NAN), (1, 1), (2, 2)),
    lambda: _line((1, 1), (NAN, NAN), (2, 2)),
    lambda: _line((1, 1), (2, 2), (NAN, 5)),
    lambda: _line((1, 1), (math.inf, 1)),
    lambda: _multi([(0, 0), (10, 0)], [(NAN, NAN), (5, 5)]),
    lambda: _multi([(0, 0)], [(5, 5), (6, 6)]),
    lambda: QgsGeometry.fromWkt("CircularString (0 0, 10 0, 20 0)"),
    lambda: QgsGeometry.fromWkt("CircularString (0 0, 200 0, 100 0)"),
    lambda: _multipoint((0, 0), (5000, NAN)),
    lambda: _multipoint((NAN, NAN), (0, 0)),
    lambda: _collection(QgsPoint(0, 0), QgsPoint(5000, NAN)),
    lambda: _collection(QgsPoint(0, 0), QgsLineString([QgsPoint(1, 1)])),
    lambda: _collection(QgsPoint(0, 0), QgsLineString([QgsPoint(1, 1), QgsPoint(NAN, 2)])),
    lambda: _polygon_with_a_nan_hole(0, 0),
])
def test_what_a_box_can_miss_is_not_held(make):
    assert not held_by_its_box(make(), 1.0)


def test_qgis_snapping_cannot_find_a_line_starting_at_nan_either(project, tmp_path):
    """The magnet-on path FU-6 adopted (QgsPointLocator) misses this one on
    every version measured -- though not every shape skipped here: it finds
    the one-vertex parts, and a NaN in the middle that leaves the box finite."""
    layer = _layer(project, tmp_path, "memory", "LineString", "Route",
                   [_line((NAN, NAN), (100, 100), (110, 100))])
    locator = QgsPointLocator(layer, QgsCoordinateReferenceSystem("EPSG:3857"), QgsCoordinateTransformContext())
    assert not locator.nearestVertex(CURSOR, 5.0).isValid()
    assert not locator.nearestEdge(CURSOR, 5.0).isValid()
    del locator


# ---------------------------------------------------------------------------
# What the check costs: asked only of a feature that would win within reach
# ---------------------------------------------------------------------------

def test_the_check_is_asked_only_of_features_within_the_tolerance(project, tmp_path, canvas):
    """200 routes along a street, fids in street order, the cursor at the far
    end: reading the whole layer, every route is nearer than the last, so a
    check asked of every improvement ran 200 times a move. Within the tolerance
    there is one route.

    The whole layer is read on purpose, ``utils.spatial.features_near``
    answering None: that is the path every provider a box cannot answer for
    takes, and where the gate matters.
    """
    _layer(project, tmp_path, "memory", "LineString", "Route",
           [_line((x * 100.0 - 20100, 100), (x * 100.0 - 20060, 100)) for x in range(203)])
    calls = {"n": 0}
    real = held_by_its_box

    def counted(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    searches = [
        lambda: PlacementSnapper(canvas, line_layers=("Route",), pixels=10)._fallback(CURSOR),
        lambda: route_tool.ManualRouteTool(_Iface(canvas), None)._find_snap_point(CURSOR),
        lambda: pipe_tool.PipePlaceTool(_Iface(canvas), None, "PE", {})._snap_point(CURSOR),
        lambda: _hover(breakpoint_tool.BreakpointTool(canvas, _Iface(canvas), None), canvas, CURSOR),
    ]
    with pytest.MonkeyPatch.context() as patch:
        for module in (base, route_tool, pipe_tool, breakpoint_tool):
            patch.setattr(module, "held_by_its_box", counted)
        patch.setattr(spatial, "features_near", lambda *args, **kwargs: None)
        for search in searches:
            calls["n"] = 0
            search()
            assert calls["n"] == 1, calls


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_the_fallback_snap_checks_a_line_exactly_one_tolerance_away(project, tmp_path, canvas, storage):
    """The fallback accepts a match at distance <= tol, so its check must be asked
    at exactly tol too ('not distance > tol'; the other three searches accept < tol).
    A broken line whose good vertex is one tolerance away is not snapped to."""
    _layer(project, tmp_path, storage, "LineString", "Route", [_line((NAN, NAN), (110.5, 100), (130, 100))])
    assert not PlacementSnapper(canvas, line_layers=("Route",), pixels=10)._fallback(CURSOR).isValid()


#: A CompoundCurve with an empty component, built through the API: QGIS 3.22
#: parses both WKTs to "CompoundCurve EMPTY".
_COMPOUND_DRIVER = r"""
import sys
sys.path.insert(0, {repo!r})
from qgis.core import (QgsApplication, QgsCircularString, QgsCompoundCurve, QgsCoordinateReferenceSystem, QgsFeature,
                       QgsGeometry, QgsLineString, QgsPoint, QgsPointXY, QgsProject, QgsRectangle, QgsVectorLayer)
app = QgsApplication([], False)
app.initQgis()
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QPoint, Qt
from fiberq.tools.base import PlacementSnapper
from fiberq.tools.breakpoint_tool import BreakpointTool
from fiberq.tools.pipe_tool import PipePlaceTool
from fiberq.tools.route_tool import ManualRouteTool
from fiberq.tools.slack_tool import _cable_lines

class Iface:
    def __init__(self, canvas): self._canvas = canvas
    def mapCanvas(self): return self._canvas
    def mainWindow(self): return None
    def messageBar(self): return self
    def pushInfo(self, *a): pass
    def pushWarning(self, *a): pass

compound = QgsCompoundCurve()
for points in {pieces!r}:
    compound.addCurve(QgsLineString([QgsPoint(x, y) for x, y in points]))
for _ in range({empties}):
    compound.addCurve(QgsCircularString())
geometry = QgsGeometry(compound)
layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
features = []
for g in (geometry, QgsGeometry.fromPolylineXY([QgsPointXY(100, 100), QgsPointXY(110, 100)])):
    f = QgsFeature(layer.fields())
    f.setGeometry(g)
    features.append(f)
assert layer.dataProvider().addFeatures(features)[0]
QgsProject.instance().addMapLayer(layer)
canvas = QgsMapCanvas()
canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
canvas.resize(800, 800)
canvas.show()
size = canvas.mapSettings().outputSize()
cursor = QgsPointXY(5, 0.3)
canvas.setExtent(QgsRectangle(5 - size.width() * 0.1, 0.3 - size.height() * 0.1,
                              5 + size.width() * 0.1, 0.3 + size.height() * 0.1))
iface = Iface(canvas)
match = PlacementSnapper(canvas, line_layers=("Route",), pixels=10)._fallback(cursor)
print("fallback", match.isValid() and (round(match.point().x(), 6), round(match.point().y(), 6)), flush=True)
found, distance = ManualRouteTool(iface, None)._find_snap_point(cursor)
print("route", found and (round(found.x(), 6), round(found.y(), 6)), flush=True)
pipe = PipePlaceTool(iface, None, "PE", {{}})._snap_point(cursor)
print("pipe", (round(pipe.x(), 6), round(pipe.y(), 6)), flush=True)
tool = BreakpointTool(canvas, iface, None)
tool.toMapCoordinates = lambda _pos: QgsPointXY(cursor)
tool.canvasMoveEvent(QgsMapMouseEvent(canvas, QEvent.Type.MouseMove, QPoint(1, 1), Qt.MouseButton.NoButton,
                                      Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
print("breakpoint", tool.snap_info is not None and tool.snap_info["feat"].id(), flush=True)
print("cable_lines", len(_cable_lines(geometry, 2.0)), flush=True)
print("DONE", flush=True)
import os
os._exit(0)
"""


@pytest.mark.parametrize("pieces, empties, expected", [
    # The fallback, route and pipe snaps answer the vertex at (5, 0), the
    # breakpoint tool the segment of feature 1, as the parent did.
    ([[(0, 0), (10, 0)]], 1, {"fallback": "(5.0, 0.0)", "route": "(5.0, 0.0)", "pipe": "(5.0, 0.0)",
                              "breakpoint": "1", "cable_lines": "1"}),
    # A single vertex and two empty arcs: no segment for the breakpoint tool, not
    # a line a slack can go on (branch 12's _cable_lines), and QGIS's own
    # vertexAt() answers (0, 0) for the vertex closestVertexWithContext finds --
    # the parent's fallback snapped there too (3.44.15, 4.2.3). The guard on
    # 3.22 to 3.44: there the first shape's vertices() stops short instead of
    # crashing, while this one's never ends (code review).
    ([[(5, 0)]], 2, {"fallback": "(0.0, 0.0)", "route": "(5.0, 0.0)", "pipe": "(5.0, 0.0)",
                     "breakpoint": "False", "cable_lines": "0"}),
])
def test_a_compound_curve_with_an_empty_component_neither_crashes_nor_hangs(tmp_path, pieces, empties, expected):
    """In a child process, because the failure is a SIGSEGV (QGIS 4.0, 4.2) or an
    endless loop (the second shape, every version), either of which would take
    the suite down. The
    answers are the parent's: main snaps to these normally -- but on 4.2 its
    slack tool's _cable_lines dies (exit 139) on the first, through the same
    QgsCompoundCurve.nCoordinates() the shared one-vertex check no longer asks."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    script = tmp_path / "compound.py"
    script.write_text(_COMPOUND_DRIVER.format(repo=str(Path(__file__).resolve().parent.parent),
                                              pieces=pieces, empties=empties), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", TMPDIR=str(tmp_path), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path), env=environment, timeout=120,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 0 and "DONE" in output, (done.returncode, output[-2000:])
    answers = dict(line.split(" ", 1) for line in output.splitlines()
                   if line.split(" ", 1)[0] in expected)
    assert answers == expected, output[-2000:]
