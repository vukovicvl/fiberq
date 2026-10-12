"""Placing a slack reads the cables and nodes near the click, not the whole project.

WP4 task 4.1, item PF-4 (the click). Every click of the Place slack tool, and
every mouse move while it is active, read every cable in both cable layers --
its ends and a GEOS distance for each -- and then every pole and manhole to
find the nearest one. That is the whole network per click: 195-370 ms at the
benchmark's sizes, on v1.5.0.

Now the cable searches ask each layer for what lies within twice the snap
tolerance of the click (``utils.spatial.features_near``), and the node search
asks a box that grows until it holds a node no farther than half its width.
Each search keeps its own test, word for word, and runs it over those
features in the order the whole-layer scan met them -- which is how a tie at a
shared cable end, the usual place to drop a slack, still goes to the cable it
always went to.

Both cable searches skip a cable that is not a valid line (``_cable_lines``,
the fix(slack) commit before this one), because a GeoPackage does not return
one to a box query at all; so the box search and the scan skip the same ones.

**Counted, not timed**, as branch 11 did: features read and GEOS distances
measured per click are deterministic, and a ratio of them fails on the parent
with its own numbers. On a GeoPackage the box is an R-tree lookup (and since
branch 13 a shapefile is boxed too, through its .qix where it has one); a
memory layer has no index in v1.6.0 -- giving FiberQ's one was dropped in
PF-5, as it crashes QGIS on coordinates beyond +/-2e154 -- so there the counts
are what reaches Python only. The equivalence tests run the parent's own loops, read
from the whole layer, next to the tool -- on the benchmark's XS city, and on
the states the design review found.
"""
import json
import math
import random
import shutil
import sqlite3
import zipfile
from contextlib import closing

import pytest
from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

from fiberq.tools.slack_tool import SlackPlaceTool, _cable_lines
from fiberq.utils.geometry import line_parts
from fiberq.utils.spatial import features_near


class _Canvas:
    def __init__(self, tolerance):
        self._mupp = tolerance / 20.0

    def mapUnitsPerPixel(self):
        return self._mupp


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture(autouse=True)
def canvas_not_rendering(qgis_canvas):
    """pytest-qgis's canvas renders every layer added to the project, in a worker thread.

    On QGIS 4.2 a render opening a GeoPackage a test had just written, while
    the test opened it for editing, left the test's own connection unable
    to read the file (35 of 40 tries in the code review). No test here needs
    the canvas to draw.
    """
    qgis_canvas.setRenderFlag(False)
    yield
    qgis_canvas.setRenderFlag(True)


def _tool(tolerance=10.0, params=None):
    tool = SlackPlaceTool.__new__(SlackPlaceTool)
    tool.iface = None
    tool.plugin = None
    tool.canvas = _Canvas(tolerance)
    tool.params = dict(params or {})
    return tool


def _memory(project, uri, name, geometries):
    layer = QgsVectorLayer(uri, name, "memory")
    features = []
    for geom in geometries:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        features.append(feat)
    ok, _added = layer.dataProvider().addFeatures(features)
    assert ok
    project.addMapLayer(layer)
    return layer


def _line(*points):
    return QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in points])


def _pt(x, y):
    return QgsGeometry.fromPointXY(QgsPointXY(x, y))


# ---------------------------------------------------------------------------
# What the parent read: the whole layer, every time
# ---------------------------------------------------------------------------

def _reference_resolve(tool, point):
    """The parent's ``_resolve``, reading every feature of every cable layer."""
    tolerance = tool.canvas.mapUnitsPerPixel() * 20
    best = (None, None, None, None, None)
    for layer in tool._iter_cable_layers():
        for feat in layer.getFeatures():
            for line in _cable_lines(feat.geometry(), tolerance):
                for label, end in zip(("od", "do"), (QgsPointXY(line[0]), QgsPointXY(line[-1]))):
                    distance = QgsPointXY(end).distance(point)
                    if (best[4] is None or distance < best[4]) and distance <= tolerance:
                        best = (layer, feat, label, end, distance)
    if best[0] is not None:
        return best[0].id(), best[1].id(), best[2], (best[3].x(), best[3].y())
    best = (None, None, None)
    for layer in tool._iter_cable_layers():
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if not _cable_lines(geom, tolerance):
                continue
            distance = geom.distance(QgsGeometry.fromPointXY(point))
            if distance < 0:
                continue
            if distance <= tolerance and (best[2] is None or distance < best[2]):
                best = (layer, feat, distance)
    if best[0] is None:
        return None
    squared, projected, _after, _which = best[1].geometry().closestSegmentWithContext(point)
    place = QgsPointXY(projected) if squared >= 0 else QgsPointXY(point)
    return best[0].id(), best[1].id(), "sredina", (place.x(), place.y())


def _reference_node(tool, point):
    """The parent's ``_nearest_node``, reading every pole and manhole."""
    best = (None, None, None)
    for layer in tool._iter_node_layers():
        for feat in layer.getFeatures():
            try:
                p = feat.geometry().asPoint()
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(p.x()) and math.isfinite(p.y())):
                continue
            distance = QgsPointXY(p).distance(point)
            if best[2] is None or distance < best[2]:
                best = (layer, feat, distance)
    return best if best[0] is None else (best[0].id(), best[1].id(), best[2])


def _resolved(tool, point):
    layer, feat, side, place = tool._resolve(point)
    if layer is None:
        return None
    return layer.id(), feat.id(), side, (place.x(), place.y())


def _node(tool, point):
    layer, feat, distance = tool._nearest_node(point)
    return (None, None, None) if layer is None else (layer.id(), feat.id(), distance)


# ---------------------------------------------------------------------------
# The work per click
# ---------------------------------------------------------------------------

def _street(project, n):
    """n 40 m cables in a row, a pole at each end, a manhole beside each."""
    _memory(project, "LineString?crs=EPSG:3857", "Underground cables",
            [_line((i * 100.0, 0), (i * 100.0 + 40, 0)) for i in range(n)])
    _memory(project, "Point?crs=EPSG:3857", "Poles",
            [_pt(i * 100.0 + dx, 0) for i in range(n) for dx in (0, 40)])
    _memory(project, "Point?crs=EPSG:3857", "Manholes",
            [_pt(i * 100.0 + 20, 15) for i in range(n)])


def _counting(patch):
    """Features handed out by QgsVectorLayer.getFeatures, and GEOS distances measured."""
    counts = {"features": 0, "distance": 0}
    real_get = QgsVectorLayer.getFeatures
    real_distance = QgsGeometry.distance

    def get(self, *args, **kwargs):
        for feat in real_get(self, *args, **kwargs):
            counts["features"] += 1
            yield feat

    def distance(self, *args, **kwargs):
        counts["distance"] += 1
        return real_distance(self, *args, **kwargs)

    patch.setattr(QgsVectorLayer, "getFeatures", get)
    patch.setattr(QgsGeometry, "distance", distance)
    return counts


def _to_gpkg(project, path):
    """Every layer of the project written to one GeoPackage and read back in its place."""
    for layer in list(project.mapLayers().values()):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer.name().replace(" ", "_")
        options.actionOnExistingFile = (QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                                        if path.exists() else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile)
        written = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsCoordinateTransformContext(), options)
        assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
        saved = QgsVectorLayer(f"{path}|layername={options.layerName}", layer.name(), "ogr")
        assert saved.isValid()
        project.removeMapLayer(layer.id())
        project.addMapLayer(saved)


def _click_counts(project, n, storage, tmp_path):
    project.removeAllMapLayers()
    _street(project, n)
    if storage == "gpkg":
        _to_gpkg(project, tmp_path / f"street{n}.gpkg")
    tool = _tool()
    with pytest.MonkeyPatch.context() as patch:
        counts = _counting(patch)
        at_end = _resolved(tool, QgsPointXY(1000 + 40, 1))          # cable 10's far end
        node = _node(tool, QgsPointXY(1000 + 40, 1))
        mid_span = _resolved(tool, QgsPointXY(1000 + 20, 3))       # cable 10, mid-span
    assert at_end[2] == "do" and mid_span[2] == "sredina" and node[2] == 1.0
    return counts["features"], counts["distance"]


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_click_reads_what_is_near_it_not_the_whole_network(project, tmp_path, storage):
    """The parent read 6n features and measured n GEOS distances for these three questions.

    At n = 40 and n = 160 that was 240 against 960 features and 40 against
    160 distances: x4 for x4 the network (measured on the parent). Now both
    stay where they are.
    """
    small = _click_counts(project, 40, storage, tmp_path)
    large = _click_counts(project, 160, storage, tmp_path)
    assert large == small, (small, large)
    assert small[0] < 40, small


# ---------------------------------------------------------------------------
# The answers: the parent's, to the bit
# ---------------------------------------------------------------------------

def test_every_click_on_the_xs_city_lands_where_it_always_did(project, city_xs_dataset, tmp_path):
    """Cable ends, ends nudged inside the tolerance, mid-spans, nodes and random points.

    The XS city has 275 cables meeting at shared poles and manholes, so most
    ends are ties the scan's order decides.
    """
    for key in ("gpkg", "qgz"):
        shutil.copy(city_xs_dataset[key], tmp_path)
    assert project.read(str(tmp_path / "city_XS.qgz"))
    tool = _tool(tolerance=2.0)
    points = []
    for layer in tool._iter_cable_layers():
        for feat in layer.getFeatures():
            for line in line_parts(feat.geometry()):
                a, b = line[0], line[-1]
                points += [a, b, QgsPointXY(a.x() + 0.6, a.y() - 0.4)]
            mid = feat.geometry().interpolate(feat.geometry().length() / 2)
            points.append(mid.asPoint())
    for layer in tool._iter_node_layers():
        points += [feat.geometry().asPoint() for feat in layer.getFeatures()]
    extent = next(iter(tool._iter_cable_layers())).extent()
    rng = random.Random(1212)
    points += [QgsPointXY(rng.uniform(extent.xMinimum(), extent.xMaximum()),
                          rng.uniform(extent.yMinimum(), extent.yMaximum())) for _ in range(300)]
    points = [QgsPointXY(p) for p in points]
    assert len(points) > 1500
    for point in points:
        assert _resolved(tool, point) == _reference_resolve(tool, point), point.asWkt()
        assert _node(tool, point) == _reference_node(tool, point), point.asWkt()


def _shared_end(layer):
    """Three cables ending at (50, 0): two saved, one added in the buffer; one saved moved."""
    assert layer.startEditing()
    added = QgsFeature(layer.fields())
    added.setGeometry(_line((50, 30), (50, 0)))
    assert layer.addFeature(added)
    first = min(f.id() for f in layer.getFeatures() if f.id() >= 0)
    # A changed geometry is handed out FIRST by a rect-filtered request.
    assert layer.changeGeometry(first + 1, _line((90, 0), (50, 0)))
    return added


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
@pytest.mark.parametrize("change", ["deleted vertex", "point", "polygon"])
def test_an_unsaved_change_to_no_line_at_all_reads_the_same(project, tmp_path, storage, change):
    """A cable cleared by deleting one of its two vertices, or a point or a
    polygon put in its place, made every slack click and move raise while the
    edit was unsaved (code review of PF-5's shared search)."""
    _street(project, 40)
    if storage == "gpkg":
        _to_gpkg(project, tmp_path / "odd.gpkg")
    layer = project.mapLayersByName("Underground cables")[0]
    assert layer.startEditing()
    try:
        target = sorted(f.id() for f in layer.getFeatures())[10]          # cable 10, by the clicks
        if change == "deleted vertex":
            layer.deleteVertex(target, 0)
        else:
            wkt = "Point (1020 3)" if change == "point" else "Polygon ((1015 2, 1025 2, 1025 6, 1015 2))"
            assert layer.changeGeometry(target, QgsGeometry.fromWkt(wkt))
        tool = _tool()
        for point in (QgsPointXY(1000 + 40, 1), QgsPointXY(1000 + 20, 3), QgsPointXY(1100, 1), QgsPointXY(990, 0)):
            assert _resolved(tool, point) == _reference_resolve(tool, point), point.asWkt()
        assert _resolved(tool, QgsPointXY(1100, 1)) is not None, "the case is not vacuous"
    finally:
        layer.rollBack()


def test_a_memory_layer_with_an_index_of_its_own_is_still_read_near_the_click(project):
    """The placement snaps read such a layer whole (its index drops a
    MultiPoint with an infinite part, which they measure through its finite
    part); the click's searches never measure one, and reading the layers
    whole made each click ~400 times slower than main (round-5 review). They
    narrow it, as on main."""
    _street(project, 40)
    for layer in project.mapLayers().values():
        assert layer.dataProvider().createSpatialIndex()
    tool = _tool()
    with pytest.MonkeyPatch.context() as patch:
        counts = _counting(patch)
        at_end = _resolved(tool, QgsPointXY(1000 + 40, 1))
        node = _node(tool, QgsPointXY(1000 + 40, 1))
    assert counts["features"] < 20, counts
    assert at_end == _reference_resolve(tool, QgsPointXY(1000 + 40, 1))
    assert node == _reference_node(tool, QgsPointXY(1000 + 40, 1))


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_tie_at_a_shared_end_goes_where_the_whole_scan_sent_it(project, tmp_path, storage):
    """The whole scan meets the buffer's added cable first; a rect request meets the moved one first."""
    source = _memory(project, "LineString?crs=EPSG:3857", "Underground cables",
                     [_line((0, 0), (50, 0)), _line((100, 0), (150, 0)), _line((50, 50), (60, 60))])
    layer = source
    if storage == "gpkg":
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        path = str(tmp_path / "cables.gpkg")
        QgsVectorFileWriter.writeAsVectorFormatV2(source, path, QgsCoordinateTransformContext(), options)
        project.removeMapLayer(source.id())
        layer = QgsVectorLayer(path + "|layername=cables", "Underground cables", "ogr")
        assert layer.isValid()
        project.addMapLayer(layer)
    added = _shared_end(layer)
    tool = _tool()
    try:
        for point in (QgsPointXY(50, 0), QgsPointXY(51, 1), QgsPointXY(50, 0.5)):
            assert _resolved(tool, point) == _reference_resolve(tool, point)
        assert _resolved(tool, QgsPointXY(50, 0))[:3] == (layer.id(), added.id(), "do")
    finally:
        layer.rollBack()


def test_a_cable_exactly_at_the_tolerance_is_still_found(project):
    """GEOS measures this click 5.0 from the cable, and the tolerance is 5.0.

    -3.9970090336748285 + 5.0 rounds to 1.0029909663251715, just short of
    the click, so a box only one tolerance wide misses the cable that the
    scan finds (branch 11 found the same pair for PF-2). Twice the tolerance
    holds it.
    """
    cables = _memory(project, "LineString?crs=EPSG:3857", "Underground cables",
                     [_line((-176.3457609018353, 6.400690145197046),
                            (-3.9970090336748285, 81.2073930300092))])
    tool = _tool(tolerance=5.0)
    click = QgsPointXY(1.002990966325172, 81.2073930300092)
    assert _reference_resolve(tool, click) is not None, "premise: the scan finds it"
    assert _resolved(tool, click) == _reference_resolve(tool, click)
    assert _resolved(tool, click)[1] == next(cables.getFeatures()).id()


def test_layers_a_box_cannot_answer_for_are_read_whole(project, tmp_path):
    """A curved layer, and providers whose order is not known: the whole layer, as before."""
    curve = _memory(project, "CompoundCurve?crs=EPSG:3857", "Underground cables",
                    [QgsGeometry.fromWkt("CompoundCurve (CircularString (0 0, 50 50, 100 0))")])
    csv = tmp_path / "aerial.csv"
    csv.write_text("id;wkt\n1;LINESTRING (1000 0, 1100 0)\n", encoding="utf-8")
    text = QgsVectorLayer(f"file://{csv}?delimiter=;&wktField=wkt&crs=EPSG:3857",
                          "Aerial cables", "delimitedtext")
    assert text.isValid()
    project.addMapLayer(text)
    tool = _tool()
    for point in (QgsPointXY(50, 48), QgsPointXY(1, 0), QgsPointXY(1050, 2), QgsPointXY(1099, 1)):
        assert _resolved(tool, point) == _reference_resolve(tool, point), point.asWkt()
    assert _resolved(tool, QgsPointXY(50, 48))[1] == next(curve.getFeatures()).id()
    assert _resolved(tool, QgsPointXY(1050, 2))[0] == text.id()
    # The fallback itself: a click test passes either way when the box would
    # have found the same cable.
    assert features_near(curve, QgsPointXY(50, 48), 10.0) is None
    assert features_near(text, QgsPointXY(1050, 2), 10.0) is None


def test_the_nearest_node_keeps_the_scans_layer_on_a_tie_and_is_found_far_away(project):
    # Layer ids start with the name and mapLayers() is ordered by id: Manholes first.
    _memory(project, "Point?crs=EPSG:3857", "Manholes", [_pt(0, 5)])
    _memory(project, "Point?crs=EPSG:3857", "Poles", [_pt(5, 0), _pt(30000, 0)])
    tool = _tool()
    for point in (QgsPointXY(0, 0), QgsPointXY(29990, 0), QgsPointXY(-90000, 70000)):
        assert _node(tool, point) == _reference_node(tool, point), point.asWkt()
    assert tool._nearest_node(QgsPointXY(0, 0))[0].name() == "Manholes"


def test_a_geojson_layer_keeps_its_file_order_at_a_shared_end(project, tmp_path):
    """OGR reads a GeoJSON file with its own ids in file order, not by fid.

    Cable A (id 5) ends where cable B (id 2) starts, and A comes first in the
    file, so the scan's strict ``<`` keeps A's end. Sorting by fid would hand
    B over first and put the slack on B's other side.
    """
    path = tmp_path / "aerial.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": 5, "properties": {"naziv": "A"},
         "geometry": {"type": "LineString", "coordinates": [[0, 0], [50, 0]]}},
        {"type": "Feature", "id": 2, "properties": {"naziv": "B"},
         "geometry": {"type": "LineString", "coordinates": [[50, 0], [100, 0]]}},
    ]}), encoding="utf-8")
    layer = QgsVectorLayer(str(path), "Aerial cables", "ogr")
    assert layer.isValid()
    project.addMapLayer(layer)
    assert [f.id() for f in layer.getFeatures()] == [5, 2], "premise: file order, not fid order"
    tool = _tool()
    for point in (QgsPointXY(50, 0), QgsPointXY(50, 1), QgsPointXY(51, 0)):
        assert _resolved(tool, point) == _reference_resolve(tool, point), point.asWkt()
    assert _resolved(tool, QgsPointXY(50, 0))[1:3] == (5, "do")


def test_a_geojson_node_layer_keeps_its_file_order_on_a_tie(project, tmp_path):
    """Two poles 5 m from the click, pole 5 first in the file: the scan's strict ``<`` keeps it."""
    path = tmp_path / "poles.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": 5, "properties": {}, "geometry": {"type": "Point", "coordinates": [0, 5]}},
        {"type": "Feature", "id": 2, "properties": {}, "geometry": {"type": "Point", "coordinates": [5, 0]}},
    ]}), encoding="utf-8")
    layer = QgsVectorLayer(str(path), "Poles", "ogr")
    assert layer.isValid()
    project.addMapLayer(layer)
    tool = _tool()
    assert _node(tool, QgsPointXY(0, 0)) == _reference_node(tool, QgsPointXY(0, 0)) == (layer.id(), 5, 5.0)


BROKEN = {
    "one-vertex part beside a line": [[(5000, 5000)], [(0, 0), (100, 0)]],
    "nan first vertex": [[(math.nan, math.nan), (0, 0), (100, 0)]],
    "nan part after a line": [[(0, 0), (100, 0)], [(math.nan, math.nan), (math.nan, math.nan)]],
    "one-vertex multipart": [[(50, 2)]],
}


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
@pytest.mark.parametrize("broken", sorted(BROKEN))
def test_a_broken_cable_is_skipped_by_the_box_search_as_by_the_scan(project, tmp_path, storage, broken):
    """A GeoPackage's box query does not return these at all; the scan skips them; so must the click."""
    parts = [[QgsPointXY(x, y) for x, y in part] for part in BROKEN[broken]]
    _memory(project, "MultiLineString?crs=EPSG:3857", "Underground cables",
            [QgsGeometry.fromMultiPolylineXY(parts), QgsGeometry.fromWkt("MultiLineString ((0 6, 100 6))")])
    if storage == "gpkg":
        _to_gpkg(project, tmp_path / "broken.gpkg")
    tool = _tool()
    for point in (QgsPointXY(100, 1), QgsPointXY(0, 1), QgsPointXY(50, 1), QgsPointXY(50, 3), QgsPointXY(5000, 5001)):
        assert _resolved(tool, point) == _reference_resolve(tool, point), point.asWkt()
    assert _resolved(tool, QgsPointXY(50, 1))[2:] == ("sredina", (50.0, 6.0))


def _arc_clicks(tool, arcs, per_arc, rng, extra=()):
    """Clicks within the tolerance of each arc, all along it, and the cable each lands on both ways."""
    tolerance = tool.canvas.mapUnitsPerPixel() * 20
    points = list(extra)
    for cx, cy, r, a0, a1 in arcs:
        for _ in range(per_arc):
            a, off = rng.uniform(a0, a1), rng.uniform(-tolerance, tolerance)
            points.append(QgsPointXY(cx + (r + off) * math.cos(a), cy + (r + off) * math.sin(a)))
    for point in points:
        yield point, _resolved(tool, point), _reference_resolve(tool, point)


def _random_arcs(rng, n):
    arcs, wkts = [], []
    for _ in range(n):
        cx, cy, r = rng.uniform(0, 5000), rng.uniform(0, 5000), 10 ** rng.uniform(0.5, 3)
        a0 = rng.uniform(0, 2 * math.pi)
        a1 = a0 + rng.uniform(0.3, 3.0)
        points = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (a0, (a0 + a1) / 2, a1)]
        arcs.append((cx, cy, r, a0, a1))
        wkts.append("CircularString (" + ", ".join(f"{x!r} {y!r}" for x, y in points) + ")")
    return arcs, wkts


@pytest.mark.parametrize("tolerance", [10.0, 1.0, 0.1, 0.01])
def test_arcs_kept_by_a_memory_layer_are_found_as_the_scan_finds_them(project, tolerance):
    """A memory layer keeps an arc as an arc, whatever its type; its box is QGIS's box of the arc.

    That box holds every proper arc's line to within 2e-6 of its size, and
    ``_cable_lines`` turns away the arc through three points in a row, whose
    box does not hold it at all; the box search finds the rest at any reach.
    """
    rng = random.Random(4004)
    arcs, wkts = _random_arcs(rng, 30)
    layer = _memory(project, "LineString?crs=EPSG:3857", "Underground cables",
                    [QgsGeometry.fromWkt(wkt) for wkt in wkts + ["CircularString (0 0, 200 0, 100 0)"]])
    assert all(QgsWkbTypes.isCurvedType(f.geometry().wkbType()) for f in layer.getFeatures()), \
        "premise: the layer kept the arcs"
    tool = _tool(tolerance=tolerance)
    along_the_flat_arc = [QgsPointXY(x, side * tolerance / 2) for x in (20, 60, 110, 150, 190) for side in (-1, 1)]
    for point, got, expected in _arc_clicks(tool, arcs, 20, rng, along_the_flat_arc):
        assert got == expected, point.asWkt()


def test_a_geopackage_line_table_holding_arcs_is_read_whole(project, tmp_path):
    """GDAL writes arcs into a LINESTRING column and registers gpkg_geom_CIRCULARSTRING for the table.

    OGR's box filter tests its own straightening of an arc, which a 0.1 m
    reach can miss: 57 of 600 such clicks found another cable through the box
    (3.44.15, 4.2.3). The registered extension sends the search to the scan.
    """
    from osgeo import ogr, osr
    rng = random.Random(5005)
    arcs, wkts = _random_arcs(rng, 30)
    path = str(tmp_path / "arcs.gpkg")
    source = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    table = source.CreateLayer("cables", srs, ogr.wkbLineString)
    for wkt in wkts:
        feature = ogr.Feature(table.GetLayerDefn())
        feature.SetGeometryDirectly(ogr.CreateGeometryFromWkt(wkt))
        table.CreateFeature(feature)
    source = table = None
    layer = QgsVectorLayer(f"{path}|layername=cables", "Underground cables", "ogr")
    assert layer.isValid() and not QgsWkbTypes.isCurvedType(layer.wkbType()), "premise: a LineString table"
    project.addMapLayer(layer)
    tool = _tool(tolerance=0.1)
    for point, got, expected in _arc_clicks(tool, arcs, 20, rng):
        assert got == expected, point.asWkt()


@pytest.mark.parametrize("arc", [
    "CircularString (0 0, 200 0, 100 0)",
    "CircularString (0 0, 50 0, 100 0)",
    "CompoundCurve ((-50 0, 0 0), CircularString (0 0, 200 0, 100 0))",
    "MultiCurve (CircularString (5 5, 6 6, 7 7))",
])
def test_an_arc_qgis_cannot_box_is_never_a_cable(arc):
    """Its box is built from memory nobody set, so a box search may or may not find it.

    Only refusing it in both searches keeps them in step, and only a direct
    look shows that: a click test passes whenever the box happens to miss.
    """
    assert _cable_lines(QgsGeometry.fromWkt(arc), 10.0) == []


# ---------------------------------------------------------------------------
# States the code review found
# ---------------------------------------------------------------------------

def _gpkg_from(project, tmp_path, name, uri, geometries, file_name="review.gpkg"):
    """A layer written to a GeoPackage table of its own and read back; the memory copy is not kept."""
    source = QgsVectorLayer(uri, name, "memory")
    features = []
    for geom in geometries:
        feat = QgsFeature(source.fields())
        feat.setGeometry(geom)
        features.append(feat)
    assert source.dataProvider().addFeatures(features)[0]
    path = tmp_path / file_name
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name.replace(" ", "_")
    options.actionOnExistingFile = (QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                                    if path.exists() else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile)
    written = QgsVectorFileWriter.writeAsVectorFormatV3(source, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    return path, options.layerName


def test_a_node_layer_counted_empty_is_still_searched(project, tmp_path):
    """QGIS keeps the count from when it last looked: a pole added through another layer object is not in it."""
    path, table = _gpkg_from(project, tmp_path, "Poles", "Point?crs=EPSG:3857&field=naziv:string", [])
    poles = QgsVectorLayer(f"{path}|layername={table}", "Poles", "ogr")
    assert poles.isValid() and poles.featureCount() == 0
    project.addMapLayer(poles)
    other = QgsVectorLayer(f"{path}|layername={table}", "other view of the poles", "ogr")
    feat = QgsFeature(other.fields())
    feat.setGeometry(_pt(100, 0))
    assert other.startEditing() and other.addFeature(feat) and other.commitChanges()
    assert poles.featureCount() == 0 and len(list(poles.getFeatures())) == 1, "premise: a stale count"
    tool = _tool()
    assert _node(tool, QgsPointXY(101, 0)) == _reference_node(tool, QgsPointXY(101, 0)) == (poles.id(), 1, 1.0)


def _shared_end_cables(project, tmp_path):
    """Cable 1 (tip 'b') ends at (50 0) where cable 2 (tip 'a') starts: a tie the scan's order settles."""
    path, table = _gpkg_from(project, tmp_path, "Underground cables", "LineString?crs=EPSG:3857&field=tip:string",
                             [_line((0, 0), (50, 0)), _line((50, 0), (100, 0))])
    layer = QgsVectorLayer(f"{path}|layername={table}", "Underground cables", "ogr")
    assert layer.isValid()
    assert layer.startEditing()
    for fid, tip in ((1, "b"), (2, "a")):
        assert layer.changeAttributeValue(fid, layer.fields().indexOf("tip"), tip)
    assert layer.commitChanges()
    return path, table, layer


def test_a_filter_answered_through_an_index_keeps_the_whole_scans_order(project, tmp_path):
    """SQLite answers the filter from the index on tip, so the whole scan meets cable 2 first."""
    _path, _table, layer = _shared_end_cables(project, tmp_path)
    assert layer.dataProvider().createAttributeIndex(layer.fields().indexOf("tip"))
    assert layer.setSubsetString("\"tip\" IN ('a', 'b')")
    project.addMapLayer(layer)
    assert [f.id() for f in layer.getFeatures()] == [2, 1], "premise: the filtered scan is in index order"
    tool = _tool()
    for point in (QgsPointXY(50, 0), QgsPointXY(50, 1)):
        assert _resolved(tool, point) == _reference_resolve(tool, point), point.asWkt()
    assert _resolved(tool, QgsPointXY(50, 0))[1:3] == (2, "od")


def test_a_geopackage_view_keeps_its_own_order(project, tmp_path):
    path, table, _layer = _shared_end_cables(project, tmp_path)
    with closing(sqlite3.connect(str(path))) as con, con:
        con.execute(f'CREATE VIEW cables_by_tip AS SELECT fid, geom, tip FROM "{table}" ORDER BY tip')
        con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) "
                    "VALUES ('cables_by_tip', 'features', 'cables_by_tip', 3857)")
        con.execute("INSERT INTO gpkg_geometry_columns VALUES ('cables_by_tip', 'geom', 'LINESTRING', 3857, 0, 0)")
    view = QgsVectorLayer(f"{path}|layername=cables_by_tip", "Underground cables", "ogr")
    assert view.isValid()
    project.addMapLayer(view)
    assert [f.id() for f in view.getFeatures()] == [2, 1], "premise: the view reads in tip order"
    tool = _tool()
    for point in (QgsPointXY(50, 0), QgsPointXY(50, 1)):
        assert _resolved(tool, point) == _reference_resolve(tool, point), point.asWkt()


def test_stored_negative_fids_are_not_taken_for_unsaved_cables(project, tmp_path):
    """The whole scan reads -5 before -2; sorting them as unsaved adds would put -2 first."""
    path, table = _gpkg_from(project, tmp_path, "Underground cables", "LineString?crs=EPSG:3857", [])
    layer = QgsVectorLayer(f"{path}|layername={table}", "Underground cables", "ogr")
    features = []
    for fid, points in ((-5, ((0, 0), (50, 0))), (-2, ((50, 0), (100, 0))), (3, ((200, 0), (300, 0)))):
        feat = QgsFeature(layer.fields())
        feat.setAttribute("fid", fid)
        feat.setGeometry(_line(*points))
        features.append(feat)
    assert layer.dataProvider().addFeatures(features)[0]
    layer.reload()
    project.addMapLayer(layer)
    assert [f.id() for f in layer.getFeatures()] == [-5, -2, 3], "premise: rows stored at negative fids"
    tool = _tool()
    assert _resolved(tool, QgsPointXY(50, 0)) == _reference_resolve(tool, QgsPointXY(50, 0))
    assert _resolved(tool, QgsPointXY(50, 0))[1:3] == (-5, "do")


def test_a_geopackage_read_through_an_archive_is_searched_whole(project, tmp_path):
    """QGIS does not split an upper-case .ZIP out of the path, so the file cannot be looked at: no error, the scan."""
    path, table = _gpkg_from(project, tmp_path, "Underground cables", "LineString?crs=EPSG:3857",
                             [_line((0, 0), (50, 0)), _line((50, 0), (100, 0))])
    archive = tmp_path / "B.ZIP"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zipped:
        zipped.write(path, "data/inner.gpkg")
    layer = QgsVectorLayer(f"/vsizip/{archive}/data/inner.gpkg|layername={table}", "Underground cables", "ogr")
    assert layer.isValid()
    project.addMapLayer(layer)
    tool = _tool()
    for point in (QgsPointXY(50, 0), QgsPointXY(25, 3)):
        assert _resolved(tool, point) == _reference_resolve(tool, point), point.asWkt()


def test_nodes_whose_point_cannot_be_read_are_not_boxed_again_and_again(project, monkeypatch):
    """A multi-part MultiPoint gives no point to asPoint(): the first box holding only those ends the box search."""
    import fiberq.tools.slack_tool as slack_tool
    _memory(project, "MultiPoint?crs=EPSG:3857", "Poles",
            [QgsGeometry.fromWkt(f"MultiPoint (({x} 0), ({x} 1))") for x in range(0, 1000, 10)])
    _memory(project, "Point?crs=EPSG:3857", "Manholes", [_pt(500, 40)])
    boxes = []
    real = slack_tool.features_near
    monkeypatch.setattr(slack_tool, "features_near",
                        lambda layer, *a: boxes.append(layer.name()) or real(layer, *a))
    tool = _tool()
    assert _node(tool, QgsPointXY(503, 2)) == _reference_node(tool, QgsPointXY(503, 2))
    assert boxes.count("Poles") == 1


@pytest.mark.parametrize("storage, where", [("memory", "edit buffer"), ("gpkg", "edit buffer"), ("memory", "saved")])
def test_an_infinite_pole_does_not_stop_the_click(project, tmp_path, storage, where):
    """QGIS raises from a node layer's extent() while it holds an infinite
    coordinate -- saved in a memory layer on 3.22 to 4.2, in its edit buffer on
    3.44 and 4.2: the node search's first box asked for it, and the click
    reported an error instead of placing the slack (round-5 and round-6
    reviews). v1.5.0's scan answered."""
    _street(project, 40)
    if storage == "gpkg":
        _to_gpkg(project, tmp_path / "infinite.gpkg")
    poles = project.mapLayersByName("Poles")[0]
    target = sorted(f.id() for f in poles.getFeatures())[5]
    if where == "saved":
        assert poles.dataProvider().changeGeometryValues({target: QgsGeometry(QgsPoint(5, math.inf))})
    else:
        assert poles.startEditing()
        assert poles.changeGeometry(target, QgsGeometry(QgsPoint(5, math.inf)))
    try:
        tool = _tool()
        for point in (QgsPointXY(1000 + 40, 1), QgsPointXY(3, 0)):
            assert _node(tool, point) == _reference_node(tool, point), point.asWkt()
    finally:
        if poles.isEditable():
            poles.rollBack()
