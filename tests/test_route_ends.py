"""The functions in core/route_ends.py, the rules behind Route correction, called directly and checked against
answers worked out by hand (``_name_of`` through the two label functions; the unused ``_PointGrid.__len__`` not
at all).

test_route_correction_ends.py and test_route_correction_scale.py reach these functions only through Route
correction's check and its Correct button. Calling them directly adds: the cell a coordinate is filed in, with
non-finite and huge coordinates; the grid's promise to hand out every point within ON; ``meets_a_node`` answering
True, the guard that keeps Correct from moving an end that already sits on a node, also where a layer has to be
read whole; ``_reach``'s figure and ``nearest_node``'s metres on the ground; which layers count as nodes; and the
labels the check reports.

Coordinates are EPSG:3857 metres near the origin unless a case says otherwise, so ON (0.01 map units) is 1 cm.
Every test of ON runs on layers in EPSG:3857, the GeoJSON file's too, through the CRS it declares. EPSG:4326 is used
only where metres are measured, never for ON: ON in degrees is a known gap, to be changed, not pinned.

Ground distances are on the WGS 84 ellipsoid (EPSG:7030), which FiberQ measures on for these CRSs when the project
has no ellipsoid; the tests that measure assert it. On the equator one Web Mercator unit east is 1 m and one unit
north is (1 - e2) m, since EPSG:3857 is spherical Mercator read as geodetic latitude.
"""
import json
import math
import random

import pytest
from qgis.core import QgsAnnotationLayer, QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY, QgsVectorLayer

from support.core_env import clean_project, memory_layer

from fiberq.core import route_ends
from fiberq.utils.measure import distance_area
from fiberq.utils.spatial import features_near

#: The WGS 84 ellipsoid: its semi-major axis in metres and its first eccentricity squared.
WGS84_A = 6378137.0
E2 = 0.00669437999014


@pytest.fixture
def project(qgis_app):
    with clean_project() as prj:
        yield prj


def _pt(x, y):
    return QgsGeometry.fromPointXY(QgsPointXY(x, y))


def _line(*points):
    return QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in points])


def _wgs84(crs):
    """FiberQ's measurement for ``crs``, after asserting that it measures on WGS 84, as with a project that has no
    ellipsoid of its own."""
    measure = distance_area(QgsCoordinateReferenceSystem(crs))
    assert measure.willUseEllipsoid() and measure.ellipsoid() == "EPSG:7030", (
        "premise: measured on WGS 84 (EPSG:7030), as in a project with no ellipsoid; something set one")
    return measure


# ---------------------------------------------------------------------------
# The node layers
# ---------------------------------------------------------------------------

def test_node_layers_are_every_valid_point_layer_of_the_fifteen_in_project_order(project):
    """Layers under old names count, and a MultiPoint layer is a point layer. Two of the three layers named "Poles", the
    invalid one and the annotation layer, are not memory layers and are added directly. The three share a name, so their
    order among themselves is random, and the answer is compared with mapLayers()."""
    wanted = [
        memory_layer(project, "Point", "Poles"),
        memory_layer(project, "Point", "Stubovi"),         # Poles, under its name from before 1.0
        memory_layer(project, "Point", "OKNA"),            # Manholes, under its old name
        memory_layer(project, "Point", "Patch Panel"),     # Patch panel, in its old spelling
        memory_layer(project, "Point", "Joint Closure TO"),
        memory_layer(project, "MultiPoint", "Nastavci"),   # Joint Closures, under its old name
    ]
    memory_layer(project, "Polygon", "Manholes")           # not a point layer
    memory_layer(project, "LineString", "Route")
    memory_layer(project, "Point", "Addresses")            # not one of the fifteen
    invalid = QgsVectorLayer("Point?crs=EPSG:3857", "Poles", "no_such_provider")
    assert not invalid.isValid() and project.addMapLayer(invalid) is not None
    options = QgsAnnotationLayer.LayerOptions(project.transformContext())
    assert project.addMapLayer(QgsAnnotationLayer("Poles", options)) is not None   # not a vector layer
    found = route_ends.node_layers(project)
    assert found == [layer for layer in project.mapLayers().values() if layer in wanted]
    assert len(found) == 6


# ---------------------------------------------------------------------------
# The grid
# ---------------------------------------------------------------------------

#: ``((x, y), cell)``: a cell is 0.02 (twice ON) on a side; None for a coordinate the grid does not file.
CELLS = [
    ((0.03, -0.01), (1, -1)),                                          # 1.5 and -0.5 cells
    ((0.02, 0.0), (1, 0)),                                             # exactly one cell side
    ((-0.005, 0.004), (-1, 0)),
    ((2.0 ** 40, -(2.0 ** 40)), (54975581388800, -54975581388800)),    # 2 ** 40 / 0.02: the furthest filed
    ((2.0 ** 40 * (1 + 2.0 ** -52), 0.0), None),                       # the next coordinate beyond it
    ((float("nan"), 0.0), None),
    ((0.0, float("-inf")), None),
]


def test_a_point_is_filed_in_the_cell_its_coordinates_fall_in():
    assert [route_ends._cell(QgsPointXY(*xy)) for xy, _cell in CELLS] == [cell for _xy, cell in CELLS]


def test_the_grid_hands_out_every_point_within_on_and_none_far_away():
    """Brute force says which points lie within ON of a point; the grid must hand out at least those, around three
    centres, one at negative coordinates."""
    rng = random.Random(20261118)
    grid = route_ends._PointGrid()
    points = []
    for x, y in ((0.0, 0.0), (-0.03, 0.05), (1234.56, -987.65)):
        for _ in range(300):
            point = QgsPointXY(x + rng.uniform(-0.05, 0.05), y + rng.uniform(-0.05, 0.05))
            grid.add(len(points), point)
            points.append(point)
    grid.add("far", QgsPointXY(10.0, 10.0))
    for k in range(0, len(points), 7):
        handed = set(grid.near(points[k]))
        within = {i for i, point in enumerate(points) if point.distance(points[k]) < route_ends.ON}
        assert within <= handed, k
        assert "far" not in handed, k


def test_a_point_no_cell_holds_is_offered_to_every_question_and_a_question_no_cell_holds_gets_everything():
    grid = route_ends._PointGrid()
    grid.add("here", QgsPointXY(0.0, 0.0))
    grid.add("there", QgsPointXY(500.0, 500.0))
    grid.add("nowhere", QgsPointXY(float("inf"), 0.0))
    assert sorted(grid.near(QgsPointXY(0.0, 0.0))) == ["here", "nowhere"]
    assert sorted(grid.near(QgsPointXY(float("nan"), 0.0))) == ["here", "nowhere", "there"]


def test_the_node_index_files_each_position_and_counts_the_features_without_one(project):
    """A feature with no geometry is counted, not filed; a MultiPoint is filed at its first part."""
    poles = memory_layer(project, "Point", "Poles", [(_pt(0, 0), {}), (None, {}), (_pt(5, 5), {})])
    closures = memory_layer(project, "MultiPoint", "Joint Closures", [("MultiPoint ((7 7), (9 9))", {})])
    index, without = route_ends.node_index([poles, closures])
    assert without == 1
    assert [(layer.name(), fid, p.x(), p.y()) for layer, fid, p in index.near(QgsPointXY(5, 5))] == [
        ("Poles", 3, 5.0, 5.0)]
    assert [(layer.name(), fid, p.x(), p.y()) for layer, fid, p in index.near(QgsPointXY(7, 7))] == [
        ("Joint Closures", 1, 7.0, 7.0)]


@pytest.mark.parametrize("node, point, on", [
    pytest.param((0, 0), (0.0099, 0), True, id="nearer than ON"),
    pytest.param((0, 0), (0.01, 0), False, id="exactly ON east"),
    pytest.param((0, 0), (0.006, 0.008), False, id="exactly ON along a 3-4-5"),
    pytest.param((-0.005, 0), (0.004, 0), True, id="0.009 apart across a cell edge"),
    pytest.param((0, 0), (0, -0.0201), False, id="two cells south"),
])
def test_on_a_node_is_strictly_nearer_than_on(project, node, point, on):
    poles = memory_layer(project, "Point", "Poles", [(_pt(*node), {})])
    index, _without = route_ends.node_index([poles])
    assert route_ends.on_a_node(QgsPointXY(*point), index) is on


# ---------------------------------------------------------------------------
# meets_a_node
# ---------------------------------------------------------------------------

def test_meets_a_node_asks_each_layer_for_the_box_around_the_point(project):
    """Features with no geometry are passed over."""
    manholes = memory_layer(project, "Point", "Manholes", [(None, {})])
    poles = memory_layer(project, "Point", "Poles", [(None, {}), (_pt(10, 10), {})])
    assert features_near(poles, QgsPointXY(10.005, 10), route_ends.ON, geometry_only=True) is not None, (
        "premise: a memory layer answers for a box")
    assert route_ends.meets_a_node(QgsPointXY(10.005, 10), [manholes, poles]) is True
    assert route_ends.meets_a_node(QgsPointXY(10, 10.02), [manholes, poles]) is False
    assert route_ends.meets_a_node(QgsPointXY(0.0, 0.01), [manholes, poles]) is False


def test_meets_a_node_reads_a_layer_whole_where_no_box_can_be_had(project, tmp_path):
    """A GeoJSON file gives no exact box answer (utils.spatial), so the layer is read whole, with the same test.
    The file declares EPSG:3857: without it GDAL reads the file as EPSG:4326, and 0.005 would be degrees."""
    path = tmp_path / "poles.geojson"
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3857"}},
        "features": [
            {"type": "Feature", "properties": {"naziv": "P1"}, "geometry": {"type": "Point", "coordinates": [10, 10]}},
        ],
    }), encoding="utf-8")
    poles = QgsVectorLayer(str(path), "Poles", "ogr")
    assert poles.isValid()
    # Owned by the project, which then deletes it: QGIS 3.22 crashes at exit when a failed test's traceback keeps a
    # valid OGR layer alive that no project owns.
    assert project.addMapLayer(poles) is not None
    assert poles.crs().authid() == "EPSG:3857", "premise: the file's CRS is read"
    assert features_near(poles, QgsPointXY(10.005, 10), route_ends.ON, geometry_only=True) is None, (
        "premise: the layer has no exact box answer, so it is read whole")
    assert route_ends.meets_a_node(QgsPointXY(10.005, 10), [poles]) is True
    assert route_ends.meets_a_node(QgsPointXY(10.02, 10), [poles]) is False
    assert route_ends.meets_a_node(QgsPointXY(float("nan"), 10), [poles]) is False


# ---------------------------------------------------------------------------
# Other routes
# ---------------------------------------------------------------------------

def _routes(project):
    return memory_layer(project, "LineString", "Route", [
        (_line((0, 0), (50, 0), (100, 0)), {"naziv": "Main"}),        # fid 1
        (_line((50, 80), (50, 0)), {"naziv": "Branch"}),              # fid 2: ends on Main's inner vertex
        (_line((25, 30), (25, 0.005)), {"naziv": "Spur"}),            # fid 3: ends 5 mm off Main's segment
        (None, {"naziv": "Ghost"}),                                   # fid 4: no geometry
        (_line((150, 0.005), (250, 0.005)), {"naziv": "Parallel"}),   # fid 5
        (_line((200, 0), (200, 50)), {"naziv": "Riser"}),             # fid 6: starts at (200 0)
    ], fields=("naziv",))


def test_touching_route_tells_a_vertex_from_a_segment_from_nothing(project):
    """A route's own vertices do not count, an inner vertex does, and a vertex anywhere beats an earlier segment."""
    index = route_ends.route_index(_routes(project).getFeatures())
    assert sorted(fid for fid, _geometry, _feature in index.everything()) == [1, 2, 3, 5, 6]

    def touching(point, fid):
        kind, feature = route_ends.touching_route(QgsPointXY(*point), fid, index.everything())
        return kind, None if feature is None else feature["naziv"]

    assert touching((50, 0), 2) == ("vertex", "Main")
    assert touching((25, 0.005), 3) == ("segment", "Main")
    assert touching((25, 0.02), 3) == (None, None)
    assert touching((0, 0), 1) == (None, None)
    assert touching((-0.01, 0), 99) == (None, None)        # exactly ON beyond Main's end
    assert touching((200, 0), 99) == ("vertex", "Riser")   # 5 mm from Parallel's segment, which comes first


def test_routes_near_yields_only_routes_whose_box_comes_within_on(project):
    routes = _routes(project)

    def near(x, y):
        return sorted(fid for fid, _geometry, _feature in route_ends.routes_near(routes, QgsPointXY(x, y)))

    assert near(50, 0) == [1, 2]
    assert near(25, 0.008) == [1, 3]
    assert near(25, 0.012) == [3]   # Main's box is the line y = 0
    assert near(500, 500) == []


# ---------------------------------------------------------------------------
# Ground distance
# ---------------------------------------------------------------------------

#: ``(crs, (x, y), map units, relative tolerance)``: 5 m in map units around the point, with 5% on top.
REACH = [
    # On the equator a unit east is 1 m and a unit north (1 - e2) m; the smaller figure wins (5.285382357896944).
    ("EPSG:3857", (0, 0), 5.0 * 1.05 / (1 - E2), 1e-9),
    # At 60 N (y = a ln tan 75 deg) a unit north is (1 - e2) cos(phi) / (1 - e2 sin(phi)^2)^1.5 m (10.491254420858374).
    ("EPSG:3857", (0, WGS84_A * math.log(math.tan(math.radians(75)))),
     5.0 * 1.05 / ((1 - E2) * 0.5 / (1 - E2 * 0.75) ** 1.5), 1e-6),
    # At 45 N a degree east is (pi / 180) a cos(phi) / sqrt(1 - e2 sin(phi)^2) m along the parallel (6.6584790e-05).
    ("EPSG:4326", (20, 45),
     5.0 * 1.05 / (math.pi / 180 * WGS84_A * math.cos(math.radians(45)) / math.sqrt(1 - E2 * 0.5)), 1e-4),
    # At the pole a degree east is 0 m: no usable figure.
    ("EPSG:4326", (20, 90), None, None),
]


def test_reach_is_five_metres_in_map_units_with_five_percent_on_top(project):
    got = [route_ends._reach(QgsPointXY(*xy), _wgs84(crs), route_ends.MAX_MOVE_M) for crs, xy, _units, _rel in REACH]
    assert got == [None if units is None else pytest.approx(units, rel=rel) for _crs, _xy, units, rel in REACH]


def test_nearest_node_is_the_nearest_on_the_ground_not_in_map_units(project):
    """2.5 units north is 2.483 m on the ground, 3 units east 3 m: the closure is nearer, and not within 2 m."""
    _wgs84("EPSG:3857")
    poles = memory_layer(project, "Point", "Poles", [(None, {}), (_pt(3, 0), {}), (_pt(-3, 0), {}), (_pt(6, 0), {})])
    closures = memory_layer(project, "Point", "Joint Closures", [(_pt(0, 2.5), {})])
    layer, fid, node, metres = route_ends.nearest_node(QgsPointXY(0, 0), poles.crs(), [poles, closures])
    assert (layer, fid, node) == (closures, 1, QgsPointXY(0, 2.5))
    assert metres == pytest.approx(2.5 * (1 - E2), rel=1e-6)
    assert route_ends.nearest_node(QgsPointXY(0, 0), poles.crs(), [poles, closures], metres=2.0) is None


def test_nearest_node_settles_a_tie_by_the_first_met_and_skips_one_with_no_position(project):
    """(3 0) and (-3 0) are both 3 m away; fid 2 is met first."""
    _wgs84("EPSG:3857")
    poles = memory_layer(project, "Point", "Poles", [(None, {}), (_pt(3, 0), {}), (_pt(-3, 0), {}), (_pt(6, 0), {})])
    layer, fid, node, metres = route_ends.nearest_node(QgsPointXY(0, 0), poles.crs(), [poles])
    assert (layer, fid, node, metres) == (poles, 2, QgsPointXY(3, 0), pytest.approx(3.0, abs=1e-9))


@pytest.mark.parametrize("node, point, metres", [
    # 0.00005 deg east at 45 N, along the parallel: 3.94234 m.
    pytest.param((20.00005, 45.0), (20.0, 45.0),
                 0.00005 * math.pi / 180 * WGS84_A * math.cos(math.radians(45)) / math.sqrt(1 - E2 * 0.5),
                 id="45 N"),
    # At the pole _reach has no figure, so the layer is read whole; 0.00001 deg of meridian there is 1.116940 m.
    pytest.param((20.0, 89.99999), (20.0, 90.0), 0.00001 * math.pi / 180 * WGS84_A / math.sqrt(1 - E2),
                 id="at the pole"),
])
def test_nearest_node_measures_metres_in_a_geographic_crs(project, node, point, metres):
    """Feature 1 has no position, and is passed over."""
    _wgs84("EPSG:4326")
    poles = memory_layer(project, "Point", "Poles", [(None, {}), (_pt(*node), {})], crs="EPSG:4326")
    found = route_ends.nearest_node(QgsPointXY(*point), poles.crs(), [poles])
    assert found is not None
    assert (found[1], found[3]) == (2, pytest.approx(metres, rel=1e-4))


# ---------------------------------------------------------------------------
# Cables and ducts at an end, and the labels
# ---------------------------------------------------------------------------

def test_lines_at_names_every_cable_and_duct_with_a_vertex_there(project):
    """Any vertex counts, an inner one too, and a duct layer under its old name; a point inside a segment is not at
    a vertex, and a route is neither a cable nor a duct."""
    memory_layer(project, "LineString", "Underground cables", [
        (_line((0, 0), (50, 0), (100, 0)), {"naziv": "K1"}),
        (_line((0, 5), (100, 5)), {"naziv": "K2"}),
        (None, {"naziv": "K-ghost"}),
    ], fields=("naziv",))
    memory_layer(project, "LineString", "PE cevi", [(_line((50, 0.005), (50, 80)), {"naziv": "D1"})], fields=("naziv",))
    memory_layer(project, "LineString", "Route", [(_line((50, 0), (50, -80)), {"naziv": "R"})], fields=("naziv",))
    assert sorted(route_ends.lines_at(QgsPointXY(50, 0), project)) == [
        "PE cevi 'D1' (ID 1)", "Underground cables 'K1' (ID 1)"]
    assert route_ends.lines_at(QgsPointXY(25, 0), project) == []


@pytest.mark.parametrize("name, fields, values, label", [
    pytest.param("Manholes", ("naziv", "broj_okna"), {"broj_okna": "12312"}, "Manholes '12312' (ID 1)",
                 id="broj_okna"),
    pytest.param("Manholes", ("naziv", "broj_okna"), {"naziv": "  MH-7 ", "broj_okna": "12312"},
                 "Manholes 'MH-7' (ID 1)", id="naziv first, stripped"),
    pytest.param("Manholes", ("naziv", "broj_okna"), {"naziv": "NULL", "broj_okna": "9"}, "Manholes '9' (ID 1)",
                 id="the text NULL is no name"),
    pytest.param("OTB", ("naziv", "oznaka"), {"oznaka": "OTB-3"}, "OTB 'OTB-3' (ID 1)", id="oznaka"),
    pytest.param("Poles", ("tip",), {"tip": "wood"}, "Poles (ID 1)", id="no name"),
    pytest.param("Manholes", ("broj_okna:integer",), {"broj_okna": 12}, "Manholes '12' (ID 1)", id="a number"),
])
def test_feature_label_names_a_point_by_naziv_else_broj_okna_else_oznaka(project, name, fields, values, label):
    layer = memory_layer(project, "Point", name, [(_pt(0, 0), values)], fields=fields)
    assert route_ends.feature_label(layer, next(layer.getFeatures())) == label


def test_route_label_uses_naziv_only(project):
    routes = memory_layer(project, "LineString", "Route", [
        (_line((0, 0), (1, 0)), {"naziv": "Route 7"}),
        (_line((0, 0), (1, 0)), {"broj_okna": "12"}),
    ], fields=("naziv", "broj_okna"))
    assert [route_ends.route_label(feature) for feature in routes.getFeatures()] == ["'Route 7' (ID 1)", "(ID 2)"]
