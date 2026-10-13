"""Placing a point reads the features near the cursor, not the whole network.

WP4 task 4.1, item PF-5. Four searches decide where a placement lands, and they
run on every mouse move: FiberQ's fallback snap (``PlacementSnapper._fallback``:
the element, pole, manhole and joint-closure tools), the route tool's, the pipe
tool's and the breakpoint tool's. Each read every feature of every layer it
snaps to and measured it in Python -- 62 ms a move for the element tool at the
benchmark's size S, 3.5 s for nine moves at L (v1.5.0, QGIS 3.44.15).

Now each asks a layer only for the features whose box comes within its
tolerance of the cursor -- twice it on a line layer that can hold an arc --
(``utils.spatial.features_within``), in the order the whole layer would have
handed them out, and runs its own loop -- unchanged -- over those. Every answer is used only when it lies within the tolerance, and
every feature with a point that near is among those asked for, so the answer,
the first of a tie included, is the whole scan's. Geometry a box query cannot
see is skipped by both (the fix(tools) commit before this one).

**Counted, not timed**, as branches 11 and 12 did: features handed out per
search are deterministic, and the parent's grow x4 with x4 the network. The
equivalence tests run each search twice on the same state -- as written, and
with ``features_within`` answering None, which makes the same loop read every
feature -- on the benchmark's XS city and on the states a box can get wrong:
a tie at a shared vertex, between layers, and an edit buffer, where a box query
hands out changed geometry first and the whole read hands out added features
first.
"""
import json
import math
import random
import shutil

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsGeometryCollection,
    QgsLineString,
    QgsMultiLineString,
    QgsMultiPoint,
    QgsPoint,
    QgsPointXY,
    QgsPolygon,
    QgsProject,
    QgsRectangle,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QPoint, Qt

import fiberq.tools.base as base
import fiberq.tools.breakpoint_tool as breakpoint_tool
import fiberq.tools.pipe_tool as pipe_tool
import fiberq.tools.route_tool as route_tool
from fiberq.tools.base import SNAP_CABLE_LAYERS, SNAP_NODE_LAYERS, SNAP_ROUTE_LAYERS, PlacementSnapper
import fiberq.utils.spatial as spatial
from fiberq.utils import geopackage
from fiberq.utils.geometry import line_parts
from fiberq.utils.geopackage import TableFacts, table_facts


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


def _canvas(centre, units_per_pixel):
    view = QgsMapCanvas()
    view.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    view.resize(800, 800)
    view.show()
    size = view.mapSettings().outputSize()
    half_w, half_h = size.width() * units_per_pixel / 2.0, size.height() * units_per_pixel / 2.0
    view.setExtent(QgsRectangle(centre.x() - half_w, centre.y() - half_h, centre.x() + half_w, centre.y() + half_h))
    assert view.mapUnitsPerPixel() == pytest.approx(units_per_pixel, rel=0.01)
    return view


class _Searches:
    """The four searches, on one canvas, each answering in a comparable form."""

    def __init__(self, canvas):
        self.canvas = canvas
        iface = _Iface(canvas)
        self.snapper = PlacementSnapper(canvas, point_layers=SNAP_NODE_LAYERS,
                                        line_layers=SNAP_ROUTE_LAYERS + SNAP_CABLE_LAYERS, pixels=10)
        self.route = route_tool.ManualRouteTool(iface, None)
        self.pipe = pipe_tool.PipePlaceTool(iface, None, "PE", {})
        self.breakpoint = breakpoint_tool.BreakpointTool(canvas, iface, None)
        self._move = QgsMapMouseEvent(canvas, QEvent.Type.MouseMove, QPoint(1, 1), Qt.MouseButton.NoButton,
                                      Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)

    def fallback(self, point):
        match = self.snapper._fallback(point)
        if not match.isValid():
            return None
        return (match.point().x(), match.point().y(), match.layer().id(), match.featureId(),
                match.distance(), match.hasEdge(), match.vertexIndex())

    def route_tool(self, point):
        found, distance = self.route._find_snap_point(point)
        # What the callers use: only an answer nearer than the snap distance.
        if found is None or distance is None or not distance < self.canvas.mapUnitsPerPixel() * route_tool.SNAP_PIXELS:
            return None
        return found.x(), found.y(), distance

    def pipe_tool(self, point):
        found = self.pipe._snap_point(point)
        return found.x(), found.y()

    def breakpoint_tool(self, point):
        self.breakpoint.toMapCoordinates = lambda _pos: QgsPointXY(point)
        self.breakpoint.canvasMoveEvent(self._move)
        info = self.breakpoint.snap_info
        if info is None:
            return None
        return info["feat"].id(), info["point"].x(), info["point"].y(), info["seg_idx"], info["dist"]

    def all(self, point):
        return (self.fallback(point), self.route_tool(point), self.pipe_tool(point), self.breakpoint_tool(point))


def _whole_layers(patch):
    """Every search reads every feature again: features_within answers None."""
    for module in (base, route_tool, pipe_tool, breakpoint_tool):
        patch.setattr(module, "features_within", lambda *args, **kwargs: None)


def _counting(patch):
    """Features handed out by QgsVectorLayer.getFeatures."""
    counts = {"features": 0}
    real_get = QgsVectorLayer.getFeatures

    def get(self, *args, **kwargs):
        for feat in real_get(self, *args, **kwargs):
            counts["features"] += 1
            yield feat

    patch.setattr(QgsVectorLayer, "getFeatures", get)
    return counts


def _memory(project, uri, name, geometries):
    layer = QgsVectorLayer(f"{uri}?crs=EPSG:3857&field=naziv:string", name, "memory")
    features = []
    for geometry in geometries:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    project.addMapLayer(layer)
    return layer


def _to_files(project, folder, storage):
    """Every layer of the project written to a GeoPackage, or to shapefiles, and read back in its place."""
    path = folder / "layers.gpkg"
    for layer in list(project.mapLayers().values()):
        options = QgsVectorFileWriter.SaveVectorOptions()
        stem = layer.name().replace(" ", "_")
        if storage == "gpkg":
            options.driverName = "GPKG"
            options.layerName = stem
            options.actionOnExistingFile = (QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                                            if path.exists() else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile)
            target, source = path, f"{path}|layername={stem}"
        else:
            options.driverName = "ESRI Shapefile"
            target = folder / f"{stem}.shp"
            source = str(target)
        written = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(target), QgsCoordinateTransformContext(), options)
        assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
        saved = QgsVectorLayer(source, layer.name(), "ogr")
        assert saved.isValid()
        project.removeMapLayer(layer.id())
        project.addMapLayer(saved)


def _line(*points):
    return QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in points])


def _pt(x, y):
    return QgsGeometry.fromPointXY(QgsPointXY(x, y))


def _street(project, n):
    """n bent routes along a street, a pole at each route's ends, a manhole at each bend, a cable each."""
    _memory(project, "LineString", "Route", [_line((i * 100.0, 0), (i * 100.0 + 40, 0), (i * 100.0 + 40, 30))
                                             for i in range(n)])
    _memory(project, "Point", "Poles", [_pt(i * 100.0 + dx, dy) for i in range(n) for dx, dy in ((0, 0), (40, 30))])
    _memory(project, "Point", "Manholes", [_pt(i * 100.0 + 40, 0) for i in range(n)])
    _memory(project, "LineString", "Underground cables", [_line((i * 100.0, 0), (i * 100.0 + 40, 0))
                                                          for i in range(n)])


# ---------------------------------------------------------------------------
# What a move reads
# ---------------------------------------------------------------------------

def _move_counts(project, n, storage, tmp_path):
    project.removeAllMapLayers()
    _street(project, n)
    if storage != "memory":
        folder = tmp_path / f"street{n}"
        folder.mkdir()
        _to_files(project, folder, storage)
    searches = _Searches(_canvas(QgsPointXY(1020, 10), 0.5))
    counts = []
    for name in ("fallback", "route_tool", "pipe_tool", "breakpoint_tool"):
        with pytest.MonkeyPatch.context() as patch:
            counted = _counting(patch)
            answer = getattr(searches, name)(QgsPointXY(1041, 1))   # by route 10's bend
            assert answer is not None, name
        counts.append(counted["features"])
    return counts


@pytest.mark.parametrize("storage", ["memory", "gpkg", "shp"])
def test_a_move_reads_what_is_near_the_cursor_not_the_whole_network(project, tmp_path, storage):
    """The parent read every feature of every layer it snaps to, per search.

    In the order fallback, route tool, pipe tool, breakpoint tool, that was
    [200, 160, 160, 40] features at n = 40 and [800, 640, 640, 160] at n = 160:
    x4 for x4 the network (measured on the parent, 3.44.15). Now each stays
    where it is.
    """
    small = _move_counts(project, 40, storage, tmp_path)
    large = _move_counts(project, 160, storage, tmp_path)
    assert large == small, (small, large)
    assert max(small) < 10, small


# ---------------------------------------------------------------------------
# The answers: the whole scan's, to the bit
# ---------------------------------------------------------------------------

def _points_of(project, rng, extent, random_points):
    points = []
    for layer in project.mapLayers().values():
        for feature in layer.getFeatures():
            geom = feature.geometry()
            for line in line_parts(geom):
                for a, b in zip(line, line[1:]):
                    points += [a, QgsPointXY((a.x() + b.x()) / 2, (a.y() + b.y()) / 2),
                               QgsPointXY(a.x() + 0.6, a.y() - 0.4)]
            if not geom.isNull() and geom.type() == QgsWkbTypes.GeometryType.PointGeometry:
                p = geom.asPoint()
                points += [p, QgsPointXY(p.x() - 0.7, p.y() + 0.2)]
    points = rng.sample(points, min(len(points), 150))
    points += [QgsPointXY(rng.uniform(extent.xMinimum(), extent.xMaximum()),
                          rng.uniform(extent.yMinimum(), extent.yMaximum())) for _ in range(random_points)]
    return [QgsPointXY(p) for p in points]


def _same_answers(project, centre, points, zooms=(0.1, 0.5, 2.0)):
    for zoom in zooms:
        searches = _Searches(_canvas(centre, zoom))
        for point in points:
            narrowed = searches.all(point)
            with pytest.MonkeyPatch.context() as patch:
                _whole_layers(patch)
                whole = searches.all(point)
            assert narrowed == whole, (zoom, point.asWkt())


def test_every_move_on_the_xs_city_lands_where_the_whole_scan_put_it(project, city_xs_dataset, tmp_path):
    """Route vertices and midpoints, node positions, each nudged, and random points, at three zooms."""
    for key in ("gpkg", "qgz"):
        shutil.copy(city_xs_dataset[key], tmp_path)
    assert project.read(str(tmp_path / "city_XS.qgz"))
    route = project.mapLayersByName("Route")[0]
    extent = route.extent()
    points = _points_of(project, random.Random(1305), extent, 60)
    _same_answers(project, extent.center(), points)


def test_the_same_on_memory_copies_of_the_xs_city(project, city_xs_dataset, tmp_path):
    """A memory layer answers a box query by testing every feature's box in C++, not through an R-tree."""
    for key in ("gpkg", "qgz"):
        shutil.copy(city_xs_dataset[key], tmp_path)
    assert project.read(str(tmp_path / "city_XS.qgz"))
    for layer in list(project.mapLayers().values()):
        if layer.name() not in SNAP_NODE_LAYERS + SNAP_ROUTE_LAYERS + SNAP_CABLE_LAYERS:
            project.removeMapLayer(layer.id())
            continue
        copy = layer.materialize(QgsFeatureRequest())
        copy.setName(layer.name())
        project.removeMapLayer(layer.id())
        project.addMapLayer(copy)
    names = sorted(layer.name() for layer in project.mapLayers().values())
    assert "Route" in names and "Poles" in names, names
    assert all(layer.dataProvider().name() == "memory" for layer in project.mapLayers().values())
    extent = project.mapLayersByName("Route")[0].extent()
    _same_answers(project, extent.center(), _points_of(project, random.Random(1306), extent, 60))


@pytest.mark.parametrize("storage", ["memory", "gpkg", "shp"])
def test_ties_at_a_shared_vertex_and_between_layers_go_where_the_scan_sent_them(project, tmp_path, storage):
    """Three routes and a cable end at (50, 0), and a pole stands on it."""
    _memory(project, "LineString", "Route", [_line((0, 0), (50, 0)), _line((50, 0), (50, 40)),
                                             _line((90, 0), (50, 0))])
    _memory(project, "LineString", "Underground cables", [_line((50, 0), (90, 0))])
    _memory(project, "Point", "Poles", [_pt(50, 0), _pt(0, 0)])
    if storage != "memory":
        _to_files(project, tmp_path, storage)
    centre = QgsPointXY(50, 0)
    points = [QgsPointXY(50 + dx, dy) for dx in (-1.3, -0.2, 0, 0.4, 2.0) for dy in (-0.9, 0, 0.3, 1.7)]
    _same_answers(project, centre, points)


@pytest.mark.parametrize("storage", ["memory", "gpkg", "shp"])
def test_an_edit_buffer_is_read_in_the_whole_scans_order(project, tmp_path, storage):
    """A box query hands out a changed geometry first, the whole read an added feature first.

    Two routes are added in the buffer (temporary ids -2, -3) and a saved one
    is moved, all ending at (50, 0) with the saved ones: every search's first
    of the tie is decided by the order, and must stay the scan's.
    """
    _memory(project, "LineString", "Route", [_line((0, 0), (50, 0)), _line((50, 0), (50, 40)),
                                             _line((300, 300), (400, 300))])
    if storage != "memory":
        _to_files(project, tmp_path, storage)
    route = project.mapLayersByName("Route")[0]
    assert route.startEditing()
    for geometry in (_line((90, 0), (50, 0)), _line((50, -30), (50, 0))):
        added = QgsFeature(route.fields())
        added.setGeometry(geometry)
        assert route.addFeature(added)
    saved = sorted(f.id() for f in route.getFeatures() if f.id() >= 0)
    assert route.changeGeometry(saved[2], _line((50, 0), (10, 30)))
    centre = QgsPointXY(50, 0)
    points = [QgsPointXY(50 + dx, dy) for dx in (-0.8, 0, 0.5) for dy in (-0.6, 0, 0.9)]
    try:
        _same_answers(project, centre, points)
    finally:
        route.rollBack()


def test_the_same_on_shapefile_copies_of_the_xs_city(project, city_xs_dataset, tmp_path):
    """A shapefile reads by record number and answers a box query in full (branch 13 probe), so it is boxed too."""
    for key in ("gpkg", "qgz"):
        shutil.copy(city_xs_dataset[key], tmp_path)
    assert project.read(str(tmp_path / "city_XS.qgz"))
    for layer in list(project.mapLayers().values()):
        if layer.name() not in SNAP_NODE_LAYERS + SNAP_ROUTE_LAYERS + SNAP_CABLE_LAYERS:
            project.removeMapLayer(layer.id())
    folder = tmp_path / "shp"
    folder.mkdir()
    _to_files(project, folder, "shp")
    assert all(layer.dataProvider().storageType() == "ESRI Shapefile" for layer in project.mapLayers().values())
    extent = project.mapLayersByName("Route")[0].extent()
    _same_answers(project, extent.center(), _points_of(project, random.Random(1307), extent, 60))


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
@pytest.mark.parametrize("arc, zoom, cursors", [
    # A 1 km chord bulging 2 m: QGIS segmentizes it to its chord, 2 m off the arc.
    ("CircularString (1000 2000, 1500 2002, 2000 2000)", 0.05, [(1500, 2002), (1250, 2001.5), (1750, 2001.4)]),
    # 200 m bulging 0.4 m, at 1 cm a pixel.
    ("CircularString (3000 2000, 3100 2000.4, 3200 2000)", 0.01, [(3100, 2000.4), (3050, 2000.3)]),
])
def test_a_curve_changed_in_the_edit_buffer_is_still_found(project, tmp_path, storage, arc, zoom, cursors):
    """A box query tests a changed geometry by the exact intersection of QGIS's
    segmentization with the box, not by its box -- and the segmentization of a
    near-straight arc is its chord, farther from the cursor than the arc the
    snaps measure. Unsaved changed curves are handed out as well (design
    review: without that, the vertex at the bulge and the arc beside it were
    no longer snapped to, on 3.22.16, 3.44.15 and 4.2.3)."""
    _memory(project, "LineString", "Route", [_line((x * 10.0, 0), (x * 10.0 + 5, 0)) for x in range(40)])
    if storage != "memory":
        _to_files(project, tmp_path, storage)
    route = project.mapLayersByName("Route")[0]
    assert route.startEditing()
    target = sorted(f.id() for f in route.getFeatures())[20]
    assert route.changeGeometry(target, QgsGeometry.fromWkt(arc))
    try:
        points = [QgsPointXY(x, y) for x, y in cursors]
        _same_answers(project, points[0], points, zooms=(zoom,))
        # And the arc did win somewhere: the case is not vacuous.
        searches = _Searches(_canvas(points[0], zoom))
        assert searches.fallback(points[0]) is not None and searches.fallback(points[0])[3] == target
    finally:
        route.rollBack()


def test_a_geojson_layer_is_read_whole_and_keeps_its_file_order(project, tmp_path):
    """OGR reads a GeoJSON file with its own ids in file order, not by fid, so
    a box query sorted by fid could settle a tie differently: features_near
    answers None and the searches read it whole. Route 5 ends where route 2
    starts, 5 comes first in the file, and the scan's strict ``<`` keeps 5."""
    path = tmp_path / "routes.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": 5, "properties": {"naziv": "A"},
         "geometry": {"type": "LineString", "coordinates": [[0, 0], [50, 0]]}},
        {"type": "Feature", "id": 2, "properties": {"naziv": "B"},
         "geometry": {"type": "LineString", "coordinates": [[50, 0], [100, 0]]}},
        {"type": "Feature", "id": 9, "properties": {"naziv": "far"},
         "geometry": {"type": "LineString", "coordinates": [[5000, 0], [5100, 0]]}},
    ]}), encoding="utf-8")
    geojson = QgsVectorLayer(str(path), "Route", "ogr")
    assert geojson.isValid()
    project.addMapLayer(geojson)
    assert [f.id() for f in geojson.getFeatures()] == [5, 2, 9], "premise: file order, not fid order"
    assert spatial.features_near(geojson, QgsPointXY(50, 0), 5.0) is None
    searches = _Searches(_canvas(QgsPointXY(50, 0), 0.5))
    with pytest.MonkeyPatch.context() as patch:
        counted = _counting(patch)
        assert searches.fallback(QgsPointXY(50.3, 0.2))[3] == 5
    assert counted["features"] == 3, "read whole, the far route included"
    _same_answers(project, QgsPointXY(50, 0), [QgsPointXY(50.3, 0.2), QgsPointXY(49.8, -0.1), QgsPointXY(50, 0)])


def _one_vertex_or_infinite(project, tmp_path, storage, geometry):
    """40 far routes saved, then route 21 changed in the edit buffer, unsaved, to ``geometry``."""
    _memory(project, "LineString", "Route", [_line((50000 + x * 100.0, 0), (50040 + x * 100.0, 0)) for x in range(40)])
    if storage != "memory":
        _to_files(project, tmp_path, storage)
    route = project.mapLayersByName("Route")[0]
    assert route.startEditing()
    target = sorted(f.id() for f in route.getFeatures())[20]
    assert route.changeGeometry(target, geometry)
    return route, target


@pytest.mark.parametrize("storage", ["memory", "gpkg", "shp"])
def test_an_unsaved_change_to_a_lone_vertex_is_still_found(project, tmp_path, storage):
    """GEOS cannot build a one-vertex LineString, so QGIS's box request -- which
    tests a changed geometry with GEOS -- left it out, while the scans snap to
    its vertex as the parent did (code review, 3.22.16 to 4.2.3)."""
    route, target = _one_vertex_or_infinite(project, tmp_path, storage, QgsGeometry.fromWkt("LineString (1000 2000)"))
    try:
        cursor = QgsPointXY(1000.3, 2000)
        _same_answers(project, cursor, [cursor, QgsPointXY(999.8, 2000.1)], zooms=(0.1, 0.5))
        searches = _Searches(_canvas(cursor, 0.1))
        assert searches.fallback(cursor)[3] == target, "the case is not vacuous"
    finally:
        route.rollBack()


@pytest.mark.parametrize("storage", ["memory", "gpkg", "shp"])
def test_an_unsaved_change_to_an_infinite_coordinate_reads_the_same(project, tmp_path, storage):
    """GEOS throws on it too; the snaps skip it (an agreed U30 shape), read whole or not."""
    shape = QgsGeometry(QgsLineString([QgsPoint(1000, 2000), QgsPoint(1010, math.inf)]))
    route, _target = _one_vertex_or_infinite(project, tmp_path, storage, shape)
    try:
        cursor = QgsPointXY(1000.3, 2000)
        _same_answers(project, cursor, [cursor], zooms=(0.1, 0.5))
    finally:
        route.rollBack()


def _delete_the_vertex(layer, fid):
    """QGIS's Vertex tool on one end of a two-vertex line, which clears a single line."""
    layer.deleteVertex(fid, 0)
    assert layer.getFeature(fid).geometry().isEmpty()


def _delete_the_part(layer, fid):
    """QGIS's Delete Part tool: part -1 of a single line, which leaves it null; part 0 of a shapefile's multi-line."""
    geometry = layer.getFeature(fid).geometry()
    assert geometry.deletePart(0 if geometry.isMultipart() else -1)
    assert layer.changeGeometry(fid, geometry)


def _changed_to(wkt):
    def change(layer, fid):
        assert layer.changeGeometry(fid, QgsGeometry.fromWkt(wkt))
    return change


#: What QGIS's own tools leave in a line layer's buffer, and what only Python
#: can put there -- changeGeometry() does not check the type. Each by the cursor.
_ODD_CHANGES = {
    "deleted vertex": _delete_the_vertex,
    "deleted part": _delete_the_part,
    "point": _changed_to("Point (1000.2 2000)"),
    "multipoint": _changed_to("MultiPoint ((1000.2 2000),(1003 2000))"),
    "polygon": _changed_to("Polygon ((1000.2 2000, 1003 2000, 1003 2003, 1000.2 2000))"),
    # QGIS keeps this one -- its point meets the box -- but the round-2 pass raised on it.
    "collection": _changed_to("GeometryCollection (Point (1000.2 2000), LineString (1001 2000))"),
    # GEOS cannot build these, so QGIS's box request leaves them out; the scan snaps to the lone vertex.
    "lone vertex in a collection": _changed_to("GeometryCollection (LineString (1000.6 2000))"),
    "collection, its point far": _changed_to("GeometryCollection (Point (5000 5000), LineString (1000.6 2000))"),
    # GEOS drops a MultiPoint whose first part has a NaN y; the snaps skip it too since U30 (round-5 review).
    "multipoint with a nan part": lambda layer, fid: layer.changeGeometry(fid, _nan_multipoint()),
    "empty line": _changed_to("LineString EMPTY"),
    "empty arc": _changed_to("CircularString EMPTY"),
    "line with an empty part": lambda layer, fid: layer.changeGeometry(fid, _with_an_empty_part()),
}


def _nan_multipoint():
    return _multipoint((1000.2, math.nan), (1000.2, 2000))


def _multipoint(*points):
    shape = QgsMultiPoint()
    for x, y in points:
        shape.addGeometry(QgsPoint(x, y))
    return QgsGeometry(shape)


def _with_an_empty_part():
    shape = QgsMultiLineString()
    shape.addGeometry(QgsLineString([QgsPoint(1000.2, 2000), QgsPoint(1003, 2000)]))
    shape.addGeometry(QgsLineString())
    return QgsGeometry(shape)


@pytest.mark.parametrize("storage", ["memory", "gpkg", "shp"])
@pytest.mark.parametrize("change", sorted(_ODD_CHANGES))
def test_an_unsaved_change_to_no_line_at_all_reads_the_same(project, tmp_path, storage, change):
    """A null geometry -- what deleting a vertex of a two-vertex line or a single
    part leaves -- or a point, a polygon or a collection in a line layer's edit
    buffer made every search of that layer raise, wherever the cursor was (code
    review). Each answers as the whole read does, a route 3 away or the odd
    feature itself."""
    far = [_line((50000 + x * 100.0, 0), (50040 + x * 100.0, 0)) for x in range(40)]
    _memory(project, "LineString", "Route", far + [_line((1000, 2003), (1040, 2003))])
    if storage != "memory":
        _to_files(project, tmp_path, storage)
    route = project.mapLayersByName("Route")[0]
    assert route.startEditing()
    try:
        target = sorted(f.id() for f in route.getFeatures())[20]
        _ODD_CHANGES[change](route, target)
        cursor = QgsPointXY(1000.3, 2000)
        _same_answers(project, cursor, [cursor, QgsPointXY(1001.1, 2000.2)], zooms=(0.1, 0.5))
        assert _Searches(_canvas(cursor, 0.5)).fallback(cursor) is not None, "the case is not vacuous"
    finally:
        route.rollBack()


@pytest.mark.parametrize("storage", ["memory", "gpkg", "shp"])
def test_a_lone_vertex_changed_into_a_point_layer_is_still_found(project, tmp_path, storage):
    """changeGeometry() takes a line on a point layer too, and the fallback snap
    measures it, while QGIS's GEOS test drops a lone vertex: a point layer's
    buffer was not read at all (round-4 review)."""
    _memory(project, "Point", "Poles", [_pt(50000 + x * 100.0, 0) for x in range(40)])
    if storage != "memory":
        _to_files(project, tmp_path, storage)
    poles = project.mapLayersByName("Poles")[0]
    assert poles.startEditing()
    try:
        target = sorted(f.id() for f in poles.getFeatures())[20]
        assert poles.changeGeometry(target, QgsGeometry.fromWkt("LineString (1000.6 2000)"))
        cursor = QgsPointXY(1000.3, 2000)
        _same_answers(project, cursor, [cursor, QgsPointXY(1000.9, 2000.1)], zooms=(0.1, 0.5))
        assert _Searches(_canvas(cursor, 0.1)).fallback(cursor)[3] == target, "the case is not vacuous"
    finally:
        poles.rollBack()


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_multipoint_with_a_nan_part_reads_the_same_saved_or_changed(project, tmp_path, storage):
    """A GeoPackage's box query left out a saved MultiPoint whose NaN part lies
    far away, and GEOS an unsaved one whose first part has a NaN y, while the
    whole read snapped to its good part (round-5 review, 3.22.16 and 4.2.3).
    The snaps skip such a MultiPoint since U30, read whole or not."""
    poles = [_pt(50000 + x * 100.0, 0) for x in range(40)] + [_multipoint((1000.2, 2000), (5000, math.nan))]
    _memory(project, "MultiPoint", "Poles", poles)
    if storage != "memory":
        _to_files(project, tmp_path, storage)
    layer = project.mapLayersByName("Poles")[0]
    cursor = QgsPointXY(1000.3, 2000)
    _same_answers(project, cursor, [cursor, QgsPointXY(1000.25, 2000.05)], zooms=(0.1, 0.5))
    assert layer.startEditing()
    try:
        target = sorted(f.id() for f in layer.getFeatures())[20]
        assert layer.changeGeometry(target, _multipoint((1000.2, math.nan), (1000.2, 2000)))
        _same_answers(project, cursor, [cursor, QgsPointXY(1000.25, 2000.05)], zooms=(0.1, 0.5))
    finally:
        layer.rollBack()


def test_a_view_sqlite_cannot_compile_leaves_the_tables_narrowed(project, tmp_path):
    """Reading every registered key compiled each view too, and a view calling one
    of GDAL's SQL functions -- or reading a table that is gone -- does not
    compile in a plain SQLite connection: the whole file then read as "cannot
    tell", and every search of it went whole (round-5 review). Only tables are
    asked for their key now."""
    import sqlite3
    from contextlib import closing
    _memory(project, "LineString", "Route", [_line((50000 + x * 100.0, 0), (50040 + x * 100.0, 0)) for x in range(10)])
    _to_files(project, tmp_path, "gpkg")
    route = project.mapLayersByName("Route")[0]
    path = route.source().split("|")[0]
    with closing(sqlite3.connect(path)) as db:
        db.create_function("ST_MinX", 1, lambda _blob: 0.0)
        srs = db.execute("SELECT srs_id FROM gpkg_geometry_columns").fetchone()[0]
        db.execute('CREATE VIEW "routes_west" AS SELECT fid, geom, ST_MinX(geom) AS minx FROM "Route"')
        db.execute("CREATE TABLE gone (fid INTEGER PRIMARY KEY, geom LINESTRING)")
        db.execute('CREATE VIEW "routes_gone" AS SELECT fid, geom FROM gone')
        db.execute("DROP TABLE gone")
        for view in ("routes_west", "routes_gone"):
            db.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) "
                       "VALUES (?, 'features', ?, ?)", (view, view, srs))
            db.execute("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', 'LINESTRING', ?, 0, 0)", (view, srs))
        db.commit()
    route = QgsVectorLayer(route.source(), "Route", "ogr")
    assert route.isValid()
    assert table_facts(route) == TableFacts(view=False, curves=False, keyed=True)
    assert [f.id() for f in spatial.features_near(route, QgsPointXY(50000, 0.3), 1.0)] == [1]
    # Each of the two guards on its own (round-6 review): no view is asked for
    # its key, and asking one answers "no key" rather than raising. Read again
    # from the file itself -- a copy would miss what still sits in its WAL.
    asked = []
    real = geopackage._rowid_key
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(geopackage, "_SCHEMAS", {})
        patch.setattr(geopackage, "_FAILED", {})
        patch.setattr(geopackage, "_rowid_key", lambda db, table: asked.append(table) or real(db, table))
        assert geopackage._schema(path) is not None
    assert asked == ["Route"], asked
    with closing(sqlite3.connect(path)) as db:
        assert real(db, "routes_west") is None and real(db, "routes_gone") is None


def test_the_schema_reads_table_names_as_sqlite_does(tmp_path):
    """A NULL table_name in gpkg_geometry_columns made the schema read raise for
    every layer of the file; and str.lower() folded "TRASA_Č" and "trasa_č",
    two tables to SQLite, into one key, so a table not keyed by the rowid
    passed for one (round-6 review). SQLite folds ASCII letters only."""
    import sqlite3
    from contextlib import closing
    path = tmp_path / "names.gpkg"
    with closing(sqlite3.connect(str(path))) as db:
        db.execute("CREATE TABLE gpkg_geometry_columns (table_name TEXT, column_name TEXT, "
                   "geometry_type_name TEXT, srs_id INTEGER, z TINYINT, m TINYINT)")
        db.execute('CREATE TABLE "TRASA_Č" (pk INT PRIMARY KEY, geom LINESTRING)')
        db.execute('CREATE TABLE "trasa_č" (fid INTEGER PRIMARY KEY, geom LINESTRING)')
        db.executemany("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', 'LINESTRING', 3857, 0, 0)",
                       [("TRASA_Č",), ("trasa_č",), (None,)])
        db.commit()
    kinds, _curved, keyed = geopackage._schema(str(path))
    assert keyed == {"trasa_č"}
    assert kinds["trasa_Č"] == kinds["trasa_č"] == "table"


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


def test_a_collection_or_a_polygon_with_a_part_at_nan_reads_the_same(project, tmp_path):
    """GDAL boxes a collection or a polygon with a part or a ring that is not a
    number so that its GeoPackage box query leaves the row out, while the
    whole read snapped to its good vertex (round-6 review, 3.22.16 to 4.2.3).
    The snaps skip such a shape since U30, read whole or not."""
    collection = QgsGeometryCollection()
    collection.addGeometry(QgsPoint(1000.2, 2000))
    collection.addGeometry(QgsPoint(5000, math.nan))
    exterior = QgsLineString([QgsPoint(1000, 1990), QgsPoint(1010, 1990), QgsPoint(1010, 2000),
                              QgsPoint(1000, 2000), QgsPoint(1000, 1990)])
    hole = QgsLineString([QgsPoint(math.nan, 1992), QgsPoint(1004, 1992), QgsPoint(1004, 1994),
                          QgsPoint(math.nan, 1992)])
    far = [_pt(50000 + x * 100.0, 0) for x in range(30)]
    _rows_written_by_qgis(project, tmp_path, "Point", "Poles", far + [QgsGeometry(collection)])
    lines = [_line((50000 + x * 100.0, 0), (50040 + x * 100.0, 0)) for x in range(30)]
    polygon = QgsPolygon()        # not QgsPolygon(exterior, [hole]): 3.22's binding frees the rings twice
    polygon.setExteriorRing(exterior)
    polygon.addInteriorRing(hole)
    _rows_written_by_qgis(project, tmp_path, "LineString", "Route", lines + [QgsGeometry(polygon)])
    cursor = QgsPointXY(1000.3, 2000)
    _same_answers(project, cursor, [cursor, QgsPointXY(1000.1, 1999.8)], zooms=(0.1, 0.5))


def _keyed(tmp_path, declaration, rows):
    """A GeoPackage "Route" table keyed ``declaration``, holding ``rows`` -- (key, geometry) -- stored in this order
    (rowids 10, 20, ...), with the blobs and R-tree boxes GDAL writes, the R-tree keyed as GDAL keys it."""
    import sqlite3
    from contextlib import closing
    source = QgsVectorLayer("LineString?crs=EPSG:3857", "base", "memory")
    features = []
    for _key, geometry in rows:
        feature = QgsFeature(source.fields())
        feature.setGeometry(geometry)
        features.append(feature)
    assert source.dataProvider().addFeatures(features)[0]
    path = tmp_path / (declaration.replace(" ", "_") + ".gpkg")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "base"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(source, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    alias, text = declaration == "INTEGER PRIMARY KEY", declaration.startswith("TEXT")
    with closing(sqlite3.connect(str(path))) as db:
        stored = db.execute("SELECT b.fid, b.geom, r.minx, r.maxx, r.miny, r.maxy FROM base AS b "
                            "JOIN rtree_base_geom AS r ON r.id = b.fid ORDER BY b.fid").fetchall()
        srs = db.execute("SELECT srs_id FROM gpkg_geometry_columns WHERE table_name = 'base'").fetchone()[0]
        db.execute('CREATE TABLE "Route" (pk %s, geom LINESTRING)' % declaration)
        db.execute('CREATE VIRTUAL TABLE "rtree_Route_geom" USING rtree(id, minx, maxx, miny, maxy)')
        for (key, _geometry), (fid, blob, *box) in zip(rows, stored):
            rowid = key if alias else fid * 10
            if alias:
                db.execute('INSERT INTO "Route" (pk, geom) VALUES (?, ?)', (key, blob))
            else:
                db.execute('INSERT INTO "Route" (rowid, pk, geom) VALUES (?, ?, ?)',
                           (rowid, "k%d" % key if text else key, blob))
            db.execute('INSERT INTO "rtree_Route_geom" VALUES (?, ?, ?, ?, ?)', [rowid if text else key] + box)
        db.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) "
                   "VALUES ('Route', 'features', 'Route', ?)", (srs,))
        db.execute("INSERT INTO gpkg_geometry_columns VALUES ('Route', 'geom', 'LINESTRING', ?, 0, 0)", (srs,))
        db.execute("INSERT INTO gpkg_extensions VALUES ('Route', 'geom', 'gpkg_rtree_index', "
                   "'http://www.geopackage.org/spec120/#extension_rtree', 'write-only')")
        db.commit()
    layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
    assert layer.isValid()
    return layer


def test_a_geopackage_table_keyed_other_than_by_its_rowid_is_read_whole(project, tmp_path):
    """GDAL reads a table in rowid order and, with an INT key, takes the key for
    the fid, so fid order is not the order of a whole read. Two routes meet at
    (1010, 2000), keys 7 and 3 stored in that order: sorted by fid, the
    fallback's tie went to 3 (round-4 review). Such a table is read whole."""
    far = [(101 + x, _line((50000 + x * 100.0, 0), (50040 + x * 100.0, 0))) for x in range(10)]
    route = _keyed(tmp_path, "INT PRIMARY KEY", [(7, _line((1000, 2000), (1010, 2000))),
                                                 (3, _line((1010, 2000), (1020, 2000)))] + far)
    project.addMapLayer(route)
    assert [f.id() for f in route.getFeatures()][:2] == [7, 3], "premise: rowid order, not fid order"
    cursor = QgsPointXY(1010, 2000.3)
    assert spatial.features_near(route, cursor, 1.0) is None
    _same_answers(project, cursor, [cursor, QgsPointXY(1009.8, 1999.9)], zooms=(0.1, 0.5))
    assert _Searches(_canvas(cursor, 0.1)).fallback(cursor)[3] == 7
    control = _keyed(tmp_path, "INTEGER PRIMARY KEY", [(7, _line((1000, 2000), (1010, 2000))),
                                                       (3, _line((1010, 2000), (1020, 2000)))] + far)
    assert [f.id() for f in spatial.features_near(control, cursor, 1.0)] == [3, 7]


def test_a_query_beyond_float32_is_not_asked_of_a_geopackage(project, tmp_path):
    """A GeoPackage's R-tree keeps float32 bounds and stores one beyond
    +/-3.4e38 as an infinity on the inside of the box, so a route out there
    was missed while the whole read snapped to it (round-4 review). No query
    reaching beyond 1e38 is asked of it."""
    far = [_line((50000 + x * 100.0, 0), (50040 + x * 100.0, 0)) for x in range(10)]
    _memory(project, "LineString", "Route", [_line((1e39, 0), (1e39, 10), (1e39, 20))] + far)
    _to_files(project, tmp_path, "gpkg")
    route = project.mapLayersByName("Route")[0]
    assert spatial.features_near(route, QgsPointXY(1e39, 10.3), 1.0) is None
    assert [f.id() for f in spatial.features_near(route, QgsPointXY(50000, 0.3), 1.0)] == [2]


def test_a_reloaded_module_counts_the_edits_itself(project, tmp_path):
    """A plugin reload imports utils.spatial afresh (QGIS's unloadPlugin drops the
    plugin's modules). The fresh import took up the key the old one had put on
    the layer, whose edits only the old import counted, so its first answer
    was kept for good: a lone vertex changed in afterwards was never handed
    out, through undo, redo and new edit sessions (code review)."""
    import importlib.util
    route, target = _one_vertex_or_infinite(project, tmp_path, "memory", _line((50000, 50), (50040, 50)))
    try:
        assert spatial._changes_a_box_may_drop(route) == []
        spec = importlib.util.find_spec("fiberq.utils.spatial")
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        assert fresh._changes_a_box_may_drop(route) == []
        assert route.changeGeometry(target, QgsGeometry.fromWkt("LineString (1000 2000)"))
        assert fresh._changes_a_box_may_drop(route) == [(target, (1000.0, 2000.0))]
        assert spatial._changes_a_box_may_drop(route) == [(target, (1000.0, 2000.0))]
    finally:
        route.rollBack()


def test_a_memory_layer_with_an_index_of_its_own_is_read_whole(project):
    """A memory layer's own spatial index drops a MultiPoint with an infinite
    part, on 3.22 and 4.2, which the scan still snaps to through its finite
    part: U30 holds it, an infinite point not being an empty one (round-6
    review). Only the snaps read such a layer whole: the slack click, which
    shares features_near and never measures a MultiPoint of two parts, narrows
    it as on main (round-5 review)."""
    poles = QgsVectorLayer("MultiPoint?crs=EPSG:3857&field=naziv:string", "Poles", "memory")
    odd = QgsMultiPoint()
    odd.addGeometry(QgsPoint(math.inf, 2000))
    odd.addGeometry(QgsPoint(1000, 2000))
    features = []
    for geometry in [QgsGeometry.fromWkt("MultiPoint ((%d 0))" % (50000 + i * 100)) for i in range(30)] + [QgsGeometry(odd)]:
        feature = QgsFeature(poles.fields())
        feature.setGeometry(geometry)
        features.append(feature)
    assert poles.dataProvider().addFeatures(features)[0]
    assert poles.dataProvider().createSpatialIndex()
    project.addMapLayer(poles)
    assert spatial.features_within(poles, QgsPointXY(1000.3, 2000), 1.0) is None
    assert spatial.features_near(poles, QgsPointXY(50000.3, 0), 1.0) is not None
    _same_answers(project, QgsPointXY(1000.3, 2000), [QgsPointXY(1000.3, 2000)], zooms=(0.1,))
    assert _Searches(_canvas(QgsPointXY(1000.3, 2000), 0.1)).fallback(QgsPointXY(1000.3, 2000))[:2] == (1000.0, 2000.0)


def test_each_search_asks_for_its_own_tolerance_and_twice_it_where_an_arc_can_hide(project, tmp_path):
    """A layer of points or straight lines on file needs only the tolerance -- the
    box v1.5.0's joint-closure tool asked for -- and a memory line layer, or one
    being edited, twice it: held_by_its_box lets an arc's points lie half the
    tolerance outside its box."""
    _street(project, 4)
    folder = tmp_path / "files"
    folder.mkdir()
    _to_files(project, folder, "gpkg")
    _memory(project, "LineString", "Underground cables", [_line((0, 5), (40, 5))])
    asked = []
    real = spatial.features_near

    def spy(layer, point, reach):
        asked.append((layer.name(), round(reach, 9)))
        return real(layer, point, reach)

    searches = _Searches(_canvas(QgsPointXY(41, 1), 0.5))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(spatial, "features_near", spy)
        searches.fallback(QgsPointXY(41, 1))
        tolerance = 0.5 * 10
        assert ("Route", round(tolerance * 1.000001, 9)) in asked
        assert ("Poles", round(tolerance * 1.000001, 9)) in asked
        assert ("Underground cables", 2 * tolerance) in asked
        route = project.mapLayersByName("Route")[0]
        assert route.startEditing()
        try:
            asked.clear()
            searches.breakpoint_tool(QgsPointXY(41, 1))
            assert asked == [("Route", 2 * tolerance)]
        finally:
            route.rollBack()


def test_an_arc_held_through_its_slack_is_found_when_zoomed_out(project):
    """At 12 map units a pixel the fallback's tolerance is 120 and its slack 60.
    On 3.22 the box of an arc starting at (0, 0) leaves that start out, yet the
    arc is held through the slack, so only a reach of twice the tolerance hands
    it over (code review). 3.44 and 4.2 box it correctly."""
    _memory(project, "LineString", "Route", [QgsGeometry.fromWkt("CircularString (0 0, 50 20, 100 0)")])
    cursor = QgsPointXY(-110, 0)
    _same_answers(project, cursor, [cursor, QgsPointXY(-90, 5)], zooms=(12.0,))
    assert _Searches(_canvas(cursor, 12.0)).fallback(cursor)[:2] == (0.0, 0.0)


def test_a_locked_geopackage_gives_up_at_once_and_is_not_asked_again_at_once(qgis_app, tmp_path):
    """A GeoPackage another program holds locked made every mouse move wait the
    0.1 s busy timeout once per layer (code review: 1.4 s a move for the route
    tool's 14 layers, 3.44.15 and 4.2.3, where QGIS leaves a viewed file in
    rollback-journal mode; 3.22 had already put it in WAL). The schema read now
    fails at once -- the layer is then read whole -- and a failure is remembered
    for a second. The file here is one no layer has open, so its journal mode
    can be set."""
    import sqlite3
    import time
    from contextlib import closing
    from fiberq.utils import geopackage
    source = QgsVectorLayer("LineString?crs=EPSG:3857&field=naziv:string", "Route", "memory")
    path = tmp_path / "locked.gpkg"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Route"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(source, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    tries = []
    real_connect = sqlite3.connect
    real_clock = time.monotonic

    def connect(*args, **kwargs):
        tries.append(args[0])
        return real_connect(*args, **kwargs)

    with closing(sqlite3.connect(str(path), isolation_level=None)) as writer:
        assert writer.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
        writer.execute("CREATE TABLE fiberq_lock_probe (x INTEGER)")   # the file changes: a fresh read is due
        writer.execute("BEGIN EXCLUSIVE")
        writer.execute("INSERT INTO fiberq_lock_probe VALUES (1)")
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(geopackage.sqlite3, "connect", connect)
            started = time.perf_counter()
            first = geopackage._schema(str(path))
            second = geopackage._schema(str(path))
            elapsed = time.perf_counter() - started
            assert len(tries) == 1, tries          # the second answer was the remembered failure
            patch.setattr(geopackage.time, "monotonic", lambda: real_clock() + 1.5)
            third = geopackage._schema(str(path))
            assert len(tries) == 2, tries          # a second later the file is asked again
        writer.execute("ROLLBACK")
    assert first is None and second is None and third is None
    assert elapsed < 0.05, elapsed
