"""The path lay cable builds across several routes: the order of its points and its length, worked out by hand.

When no single route passes the two selected elements, lay cable (from the toolbar and the cable-type menus) and the
Pipe tool ask ``utils.routing.build_path_across_network`` for a path over the vertices of every route, and
``build_path_across_joined_routes``, which takes each route whole, when the first finds none.
``test_lay_cable_route_search.py`` covers only the single-route search that runs before them, and
``test_route_graph_nearest_key.py`` checks the graph's nearest vertex and that two ways of finding it give the same
paths on the benchmark city; neither knows what a path should be. This file adds the known answers: the order and
the length of the path across junctions, gaps just under and just over the tolerance, multipart routes and loops;
the first run of the joined-routes search, which no earlier test reaches; and, through the plugin's own Lay cable,
the length it stores for a path across several routes and what it tells the user.

The answers follow how the search works. Each vertex is keyed by its cell in a grid as wide as the tolerance
(``utils/geometry.fuzzy_key``), the first vertex read stands for its cell, consecutive vertices in different cells
are joined, and the graph is walked breadth first. The tolerance is 3.0: lay cable passes 6 screen pixels in map units,
at 0.5 map units per pixel here. Cell k holds k - 0.5 < x / 3 < k + 0.5, so cell 34 is 100.5 < x < 103.5. Every
coordinate keeps at least 0.03 of a cell from a cell's edge, so that rounding cannot move it, except in the test of
a small gap across a cell's edge, which straddles one on purpose, 0.05 map units on each side.

The routes are a memory layer in EPSG:3857 near the origin, read in the order its features are given. A path is a
list of points compared exactly (it holds the routes' own vertices); a length with a square root is compared to
1e-6. A tie between two equally short paths is asserted as the set of both.

Lay cable is driven as the Cable laying menu's entries drive it (``lay_cable_type``, here Underground >
Backbone), on a plugin whose managers are wired as the plugin wires them, with the cable picker and the message
boxes replaced. Which pole it takes for the cable's start is the order of ``selectedFeatures()``, which changes
from one QGIS start to the next, so neither the cable's direction nor its ``od`` and ``do`` is pinned. It measures
the cable on the WGS 84 ellipsoid, the one EPSG:3857 names, since the project has none (``utils/measure.py``):
near the origin a map metre east-west is a metre on the ground, and a map metre north-south is (1 - e**2) of one.

Three tests are expected failures, each raising an exception of its own for its defect: the search counts segments,
not metres; routes join by grid cell, not by distance; one non-finite vertex anywhere stops the whole search. Until
v1.7.0, two elements nearest one vertex got a path of that one point, and lay cable a cable of one vertex
(WP5-FU-33); two tests check that there is no path now, and that lay cable lays nothing and warns.
"""
import math

import pytest
from qgis.core import QgsGeometry, QgsLineString, QgsMultiLineString, QgsPoint, QgsPointXY

from support.core_env import (CoreIface, clean_project, memory_layer, patch_cable_picker, record_message_boxes,
                              wired_plugin)

from fiberq.utils import routing
from fiberq.utils.compat import FieldType, new_field
from fiberq.utils.measure import distance_area

#: 6 screen pixels at 0.5 map units per pixel: the tolerance lay cable passes (core/cable_manager.py:948).
TOL = 3.0

#: The T junction: a west arm, an east arm and a stem north from (60, 0), each its own route.
T = ([(0, 0), (60, 0)], [(60, 0), (120, 0)], [(60, 0), (60, 90)])
#: West arm, then the stem: 60 + 90 = 150.
T_PATH = [(0.0, 0.0), (60.0, 0.0), (60.0, 90.0)]

#: Four routes round a block 100 on a side, digitised in no common direction.
BLOCK = ([(0, 0), (100, 0)], [(100, 100), (100, 0)], [(100, 100), (0, 100)], [(0, 0), (0, 100)])

NAN = float("nan")

#: 1 - e**2 of WGS 84 (f = 1 / 298.257223563): a north-south map metre of EPSG:3857 near the equator, on the ground.
NS = 0.99330562000986

#: What the cable picker answers (the dialog is replaced): an underground backbone cable of 12 fibres.
PICKED = {
    "vrsta": "podzemni", "tip": "Distribucioni", "podtip": "Backbone", "color_code": "", "broj_cevcica": 1,
    "broj_vlakana": 12, "tip_kabla": "", "vrsta_vlakana": "", "vrsta_omotaca": "", "vrsta_armature": "",
    "talasno_podrucje": "", "naziv": "C-new", "slabljenje_dbkm": 0.0, "hrom_disp_ps_nmxkm": 0.0, "stanje_kabla": "",
    "cable_laying": "underground", "vrsta_mreze": "", "godina_ugradnje": 2026, "konstr_vlakna_u_cevcicama": 0,
    "konstr_sa_uzlepljenim_elementom": 0, "konstr_punjeni_kabl": 0, "konstr_sa_arm_vlaknima": 0,
    "konstr_bez_metalnih": 0, "fibers_per_tube": 12, "total_fibers": 12, "color_standard": "",
}

#: The cable layer's own columns before lay cable adds the rest; the lengths as full doubles.
CABLE_FIELDS = (("naziv", FieldType.String), ("tip", FieldType.String), ("duzina_m", FieldType.Double),
                ("slack_m", FieldType.Double), ("total_len_m", FieldType.Double))

LAID = "Cable has been laid along the route!"
NOT_CONNECTED = "Joint closures or elements are not at the ends of the same route or connected routes."


class GapAcrossCellEdge(AssertionError):
    """WP5-FU-32: routes join where their vertices share a cell of the tolerance's grid, not within the tolerance."""


class PathCountsSegments(AssertionError):
    """WP5-FU-31: the search across several routes takes the path of fewest segments, not the shortest one."""


class NonFiniteVertexStopsSearch(AssertionError):
    """WP5-FU-34: one non-finite vertex anywhere in the Route layer stops the network search for every pair."""


@pytest.fixture
def project(qgis_app):
    with clean_project() as prj:
        yield prj


def _line(points):
    """A line through ``points``, built from QgsPoint, so that a NaN coordinate stays (WKT "nan" reads as null)."""
    return QgsGeometry(QgsLineString([QgsPoint(x, y) for x, y in points]))


def _parts(parts):
    """A multipart line, one part per list of points."""
    shape = QgsMultiLineString()
    for points in parts:
        shape.addGeometry(QgsLineString([QgsPoint(x, y) for x, y in points]))
    return QgsGeometry(shape)


def _routes(project, *lines, name="Route"):
    """A route layer in EPSG:3857 holding one route per entry of ``lines``, in this order (fids 1, 2, ...)."""
    return memory_layer(project, "LineString", name, [(_line(points), {}) for points in lines])


def _multipart_routes(project, *routes):
    """A multipart route layer: each entry of ``routes`` is one route, a list of parts."""
    return memory_layer(project, "MultiLineString", "Route", [(_parts(parts), {}) for parts in routes])


def _xy(path):
    return None if path is None else [(point.x(), point.y()) for point in path]


def _network(layer, a, b):
    """What the network search answers from ``a`` to ``b``: a list of (x, y), or None."""
    return _xy(routing.build_path_across_network(layer, QgsPointXY(*a), QgsPointXY(*b), TOL))


def _joined(layer, a, b):
    """What the joined-routes search answers from ``a`` to ``b``: a list of (x, y), or None."""
    return _xy(routing.build_path_across_joined_routes(layer, QgsPointXY(*a), QgsPointXY(*b), TOL))


def _length(points):
    """The planar length of the path through ``points``, in map units."""
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


# --- a T junction -----------------------------------------------------------------------------------------------------

def test_a_t_junction_turns_into_the_stem(project):
    """From the west arm's end to the stem's: along the west arm, then up the stem, 60 + 90 = 150."""
    routes = _routes(project, *T)
    for search in (_network, _joined):
        path = search(routes, (0, 0), (60, 90))
        assert path == T_PATH, search.__name__
        assert _length(path) == 150.0


def test_a_t_junction_is_crossed_straight_on(project):
    """From the east arm's end to the west arm's: straight across the junction, not into the stem, 60 + 60 = 120."""
    routes = _routes(project, *T)
    for search in (_network, _joined):
        path = search(routes, (120, 0), (0, 0))
        assert path == [(120.0, 0.0), (60.0, 0.0), (0.0, 0.0)], search.__name__
        assert _length(path) == 120.0


def test_a_t_junction_at_a_vertex_of_an_unsplit_route(project):
    """The bar is one route with a vertex where the stem ends: the network search joins them there, 150. The
    joined-routes search joins routes only at their ends, so it finds nothing."""
    routes = _routes(project, [(0, 0), (60, 0), (120, 0)], [(60, 90), (60, 0)])
    path = _network(routes, (0, 0), (60, 90))
    assert path == T_PATH
    assert _length(path) == 150.0
    assert _joined(routes, (0, 0), (60, 90)) is None


# --- a chain ----------------------------------------------------------------------------------------------------------

def test_a_chain_digitised_both_ways_is_walked_in_order(project):
    """Three routes end to end, the middle one digitised against the walk: 20 + 20 + 30 + 30 + 30 = 130, and the
    same points backwards the other way."""
    routes = _routes(project, [(0, 0), (20, 0), (40, 0)], [(40, 30), (40, 0)], [(40, 30), (70, 30), (100, 30)])
    forward = [(0.0, 0.0), (20.0, 0.0), (40.0, 0.0), (40.0, 30.0), (70.0, 30.0), (100.0, 30.0)]
    for search in (_network, _joined):
        assert search(routes, (0, 0), (100, 30)) == forward, search.__name__
        assert search(routes, (100, 30), (0, 0)) == forward[::-1], search.__name__
    assert _length(forward) == 130.0


# --- gaps between routes ----------------------------------------------------------------------------------------------

def test_a_gap_just_under_the_tolerance_is_bridged(project):
    """A 2.8 gap with both ends in cell 34 (100.6 / 3 = 33.53, 103.4 / 3 = 34.47). The network search keeps the end
    it read first for the cell, so its path runs from there to the next vertex: 100.6 + sqrt(2.8**2 + 60**2) =
    160.665298. The joined-routes search keeps both ends: 100.6 + 2.8 + 60 = 163.4."""
    routes = _routes(project, [(0, 0), (100.6, 0)], [(103.4, 0), (103.4, 60)])
    network = _network(routes, (0, 0), (103.4, 60))
    assert network == [(0.0, 0.0), (100.6, 0.0), (103.4, 60.0)]
    assert _length(network) == pytest.approx(160.665298, abs=1e-6)
    joined = _joined(routes, (0, 0), (103.4, 60))
    assert joined == [(0.0, 0.0), (100.6, 0.0), (103.4, 0.0), (103.4, 60.0)]
    assert _length(joined) == pytest.approx(163.4, abs=1e-6)


def test_a_gap_just_under_the_tolerance_read_the_other_way_round(project):
    """The same routes with the far one read first: its end stands for cell 34, so the path is 103.4 + 60 = 163.4."""
    routes = _routes(project, [(103.4, 0), (103.4, 60)], [(0, 0), (100.6, 0)])
    network = _network(routes, (0, 0), (103.4, 60))
    assert network == [(0.0, 0.0), (103.4, 0.0), (103.4, 60.0)]
    assert _length(network) == pytest.approx(163.4, abs=1e-6)


def test_a_gap_just_over_the_tolerance_is_not_bridged(project):
    """A 3.1 gap: 103.7 / 3 = 34.57 is in cell 35, which no vertex of the first route reaches."""
    routes = _routes(project, [(0, 0), (100.6, 0)], [(103.7, 0), (103.7, 60)])
    assert _network(routes, (0, 0), (103.7, 60)) is None
    assert _joined(routes, (0, 0), (103.7, 60)) is None


@pytest.mark.xfail(strict=True, raises=GapAcrossCellEdge,
                   reason="WP5-FU-32: routes join where their vertices share a grid cell, not within the tolerance; "
                          "the v1.8.0 fix removes this marker")
def test_a_small_gap_across_a_grid_line_is_bridged(project):
    """A 0.1 gap across the edge between cells 33 and 34 (100.45 / 3 = 33.48, 100.55 / 3 = 33.52) is bridged as the
    2.8 gap inside one cell is.

    The control moves the same gap inside cell 34 (100.95 / 3 = 33.65, 101.05 / 3 = 33.68), where it is bridged. A
    right answer runs from (0, 0) to (100.55, 60) over the routes' own vertices, from 100.45 + sqrt(0.1**2 + 60**2)
    = 160.450083 long (the gap's ends merged) to 100.45 + 0.1 + 60 = 160.55 (both kept). Measured: no path at
    tolerance 3.0, and the merged one at 2.9 (6 px at 0.4833 map units per pixel).
    """
    control = _routes(project, [(0, 0), (100.95, 0)], [(101.05, 0), (101.05, 60)], name="Control routes")
    assert _network(control, (0, 0), (101.05, 60)) == [(0.0, 0.0), (100.95, 0.0), (101.05, 60.0)]
    routes = _routes(project, [(0, 0), (100.45, 0)], [(100.55, 0), (100.55, 60)])
    vertices = {(0.0, 0.0), (100.45, 0.0), (100.55, 0.0), (100.55, 60.0)}
    path = _network(routes, (0, 0), (100.55, 60))
    if path is None:
        raise GapAcrossCellEdge("no path across a 0.1 gap that lies across the edge between cells 33 and 34")
    assert (path[0], path[-1]) == ((0.0, 0.0), (100.55, 60.0)), (
        "the path %r does not run from (0, 0) to (100.55, 60)" % path)
    assert set(path) <= vertices, "the path %r leaves the routes' vertices" % path
    assert 160.450083 - 1e-6 <= _length(path) <= 160.55 + 1e-6, (
        "the path %r is %.6f long, outside [160.450083, 160.55]" % (path, _length(path)))


# --- multipart routes -------------------------------------------------------------------------------------------------

def test_the_parts_of_a_multipart_route_are_walked_in_order(project):
    """Two parts of one route meet at (50, 0), the second digitised towards it: 50 + 80 = 130."""
    routes = _multipart_routes(project, [[(0, 0), (50, 0)], [(50, 80), (50, 0)]])
    path = _network(routes, (0, 0), (50, 80))
    assert path == [(0.0, 0.0), (50.0, 0.0), (50.0, 80.0)]
    assert _length(path) == 130.0


def test_two_parts_of_a_route_bridged_by_another_route(project):
    """Parts (0 0, 40 0) and (60 0, 100 0) of one route, joined by a second route (40 0, 60 0): 100."""
    routes = _multipart_routes(project, [[(0, 0), (40, 0)], [(60, 0), (100, 0)]], [[(40, 0), (60, 0)]])
    path = _network(routes, (0, 0), (100, 0))
    assert path == [(0.0, 0.0), (40.0, 0.0), (60.0, 0.0), (100.0, 0.0)]
    assert _length(path) == 100.0


# --- loops ------------------------------------------------------------------------------------------------------------

def test_a_block_is_walked_the_short_way_round(project):
    """Round a block, one corner to the next is 100 along one side, not 300 the other way round."""
    routes = _routes(project, *BLOCK)
    for search in (_network, _joined):
        assert search(routes, (0, 0), (100, 0)) == [(0.0, 0.0), (100.0, 0.0)], search.__name__


def test_a_block_to_the_opposite_corner(project):
    """To the opposite corner both ways round are 200 long, and either is right (both searches take the route read
    first today)."""
    routes = _routes(project, *BLOCK)
    ways = ([(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)], [(0.0, 0.0), (0.0, 100.0), (100.0, 100.0)])
    for search in (_network, _joined):
        assert search(routes, (0, 0), (100, 100)) in ways, search.__name__
    assert _length(ways[0]) == _length(ways[1]) == 200.0


def test_a_closed_ring_route_is_walked_the_short_way_round(project):
    """One route that closes on itself round the block: neighbouring corners are 100 apart one way round and 300 the
    other, either way along the ring; opposite corners are 200 apart both ways round."""
    ring = _routes(project, [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
    assert _network(ring, (0, 0), (100, 0)) == [(0.0, 0.0), (100.0, 0.0)]
    assert _network(ring, (100, 0), (0, 0)) == [(100.0, 0.0), (0.0, 0.0)]
    ways = ([(0.0, 100.0), (0.0, 0.0), (100.0, 0.0)], [(0.0, 100.0), (100.0, 100.0), (100.0, 0.0)])
    assert _network(ring, (0, 100), (100, 0)) in ways
    assert _length(ways[0]) == _length(ways[1]) == 200.0


def test_a_loop_is_walked_along_the_street_with_fewer_and_shorter_segments(project):
    """Two streets from (0, 0) to (100, 0): a short one of two segments, 2 sqrt(50**2 + 10**2) = 101.980390, and a
    long one of four, 2 sqrt(25**2 + 100**2) + 2 sqrt(25**2 + 50**2) = 317.958680."""
    routes = _routes(project, [(0, 0), (50, 10), (100, 0)], [(0, 0), (25, -100), (50, -150), (75, -100), (100, 0)])
    path = _network(routes, (0, 0), (100, 0))
    assert path == [(0.0, 0.0), (50.0, 10.0), (100.0, 0.0)]
    assert _length(path) == pytest.approx(101.980390, abs=1e-6)


@pytest.mark.xfail(strict=True, raises=PathCountsSegments,
                   reason="WP5-FU-31: the search across several routes takes the fewest segments, not the shortest "
                          "path; the v1.8.0 fix removes this marker")
def test_a_loop_is_walked_along_the_shorter_street(project):
    """Two streets from (0, 0) to (100, 0), each of two routes: a short one of four segments, 2 sqrt(650) +
    2 sqrt(629) = 101.149940, and a long one of two, 2 sqrt(42500) = 412.310563. Measured: the long one."""
    routes = _routes(project, [(0, 0), (25, 5), (50, 7)], [(50, 7), (75, 5), (100, 0)], [(0, 0), (50, -200)],
                     [(50, -200), (100, 0)])
    path = _network(routes, (0, 0), (100, 0))
    short = [(0.0, 0.0), (25.0, 5.0), (50.0, 7.0), (75.0, 5.0), (100.0, 0.0)]
    assert path in (short, [(0.0, 0.0), (50.0, -200.0), (100.0, 0.0)]), "premise: one of the two streets: %r" % path
    if path != short or abs(_length(path) - 101.149940) > 1e-6:
        raise PathCountsSegments("took %r, %.6f long, not the short street, 101.149940" % (path, _length(path)))


# --- two elements at one vertex, and a broken route -------------------------------------------------------------------

def test_two_elements_nearest_one_vertex_get_no_one_point_path(project):
    """(98, 0) and (102, 0) are both nearest the vertex (100, 0), 2 away: no path. Until v1.7.0 the answer was
    [(100, 0)], which lay cable wrote as a cable of one vertex (WP5-FU-33). The control, from (98, 0) to (198, 0),
    gets the stretch between the two nearest vertices."""
    routes = _routes(project, [(0, 0), (100, 0), (200, 0)], [(200, 0), (200, 50)])
    assert _network(routes, (98, 0), (198, 0)) == [(100.0, 0.0), (200.0, 0.0)]
    assert _network(routes, (98, 0), (102, 0)) is None


@pytest.mark.xfail(strict=True, raises=NonFiniteVertexStopsSearch,
                   reason="WP5-FU-34: one non-finite vertex anywhere in the Route layer stops the network search; "
                          "the v1.8.0 fix removes this marker")
def test_a_nan_vertex_in_another_route_leaves_the_search_working(project):
    """The T junction with a far route that holds a NaN vertex still gives the T's path. Measured: None, since
    int(round(nan)) raises ValueError in the cell key and the whole search answers None. The control, the T alone,
    gives its path."""
    control = _routes(project, *T, name="Control routes")
    assert _network(control, (0, 0), (60, 90)) == T_PATH
    routes = _routes(project, *T, [(500, 500), (NAN, NAN), (600, 600)])
    path = _network(routes, (0, 0), (60, 90))
    if path is None:
        raise NonFiniteVertexStopsSearch("no path with a NaN vertex in a far route")
    assert path == T_PATH


# --- the ends of the search -------------------------------------------------------------------------------------------

def test_an_element_within_three_tolerances_of_a_route_end_is_taken_to_it(project):
    """(0, 8.9) is 8.9 from (0, 0), within 3 x 3.0, so the path starts there; (0, 9.1) is not, so there is none. The
    joined-routes search takes an element only in the same cell as a route's end, and (0, 8.9) is in cell (0, 3)."""
    routes = _routes(project, *T)
    assert _network(routes, (0, 8.9), (60, 90)) == T_PATH
    assert _network(routes, (0, 9.1), (60, 90)) is None
    assert _joined(routes, (0, 8.9), (60, 90)) is None


def test_an_empty_route_layer_has_no_path(project):
    routes = _routes(project)
    assert _network(routes, (0, 0), (60, 90)) is None
    assert _joined(routes, (0, 0), (60, 90)) is None


# --- through Lay cable ------------------------------------------------------------------------------------------------

def _lay_cable(project, monkeypatch, routes, poles):
    """Lay a cable as Cable laying > Underground > Backbone does, between two poles at ``poles`` across ``routes``.

    The project holds a cable layer Kablovi_podzemni, the routes as a layer Route and a layer Poles with both poles
    selected; the canvas is at 0.5 map units per pixel. Returns the cable layer, the texts of the message boxes shown
    and what reached the message bar.
    """
    said = record_message_boxes(monkeypatch)
    patch_cable_picker(monkeypatch, PICKED)
    cables = memory_layer(project, "LineString", "Kablovi_podzemni")
    assert cables.dataProvider().addAttributes([new_field(name, kind) for name, kind in CABLE_FIELDS])
    cables.updateFields()
    _routes(project, *routes)
    rows = [(QgsGeometry.fromPointXY(QgsPointXY(x, y)), {"tip": "P%d" % i}) for i, (x, y) in enumerate(poles)]
    pole_layer = memory_layer(project, "Point", "Poles", rows, fields=("tip",))
    pole_layer.selectByIds([feature.id() for feature in pole_layer.getFeatures()])
    iface = CoreIface(units_per_pixel=0.5)
    # FiberQ reports to QGIS's global iface when it is given none (utils/errors.py), so this one stands in for it too.
    monkeypatch.setattr("qgis.utils.iface", iface)
    plugin = wired_plugin(iface)
    plugin.lay_cable_type("podzemni", "glavni")
    return cables, said, iface.messageBar().messages


def _vertices(feature):
    return [(point.x(), point.y()) for point in feature.geometry().asPolyline()]


def test_lay_cable_follows_the_t_junction_and_stores_its_ground_length(project, monkeypatch):
    """No route passes both poles, so the path is searched across the routes: along the west arm and up the stem,
    60 m east-west and 90 m north-south, 60 + 90 x 0.99330562 = 149.397506 m on the ground (measured
    149.3975057979801 on QGIS 4.2, 149.39750579797976 on 3.22). The length is stored as the cable's length and its
    total, it says so in a message box, and nothing reaches the message bar."""
    cables, said, bar = _lay_cable(project, monkeypatch, T, [(0, 0), (60, 90)])
    measurer = distance_area(cables.crs())
    assert measurer.willUseEllipsoid() and measurer.ellipsoid() == "EPSG:7030"
    assert said == [LAID]
    assert bar == []
    laid = list(cables.getFeatures())
    assert len(laid) == 1
    assert _vertices(laid[0]) in (T_PATH, T_PATH[::-1])
    assert laid[0]["duzina_m"] == pytest.approx(60 + 90 * NS, abs=1e-6)
    assert laid[0]["total_len_m"] == laid[0]["duzina_m"]


def test_lay_cable_lays_nothing_across_a_gap_just_over_the_tolerance(project, monkeypatch):
    """Across the 3.1 gap neither search finds a path: no cable, the warning, and nothing on the message bar."""
    cables, said, bar = _lay_cable(project, monkeypatch, [[(0, 0), (100.6, 0)], [(103.7, 0), (103.7, 60)]],
                                   [(0, 0), (103.7, 60)])
    assert cables.featureCount() == 0
    assert said == [NOT_CONNECTED]
    assert bar == []


def test_lay_cable_writes_no_cable_of_fewer_than_two_vertices(project, monkeypatch):
    """Poles at (98, 0) and (102, 0), both nearest the route vertex (100, 0): no cable, the warning, and nothing on
    the message bar, as across the 3.1 gap. Until v1.7.0 lay cable wrote a cable LineString (100 0), 0.0 m long,
    and said "Cable has been laid along the route!" (WP5-FU-33)."""
    cables, said, bar = _lay_cable(project, monkeypatch, [[(0, 0), (100, 0), (200, 0)], [(200, 0), (200, 50)]],
                                   [(98, 0), (102, 0)])
    assert [_vertices(feature) for feature in cables.getFeatures()] == []
    assert said == [NOT_CONNECTED]
    assert bar == []
