"""The routing graph finds the vertex nearest an element in its own grid, not by reading every key.

WP4 task 4.1, item PF-7 (the indexed nearest vertex). ``build_path_across_network``
builds a graph keyed by ``fuzzy_key`` -- each vertex's cell in a grid
``tolerance`` wide -- and then asked ``find_nearest_vertex`` twice per lay cable
for the key nearest each element, which measured every key in the graph.

``utils.routing._nearest_key`` reads the 11 x 11 cells around the query's own
instead: a vertex the search can accept is within 3 tolerances, hence within 4
cells. Same arithmetic, same strict ``<``, same acceptance expression, and the
linear search answers whenever the grid cannot say what it would -- a tie, an
odd tolerance, a query too many cells from the origin.

**Counted, not timed**: keys measured per search, through points that count
their own reads. Equivalence: against ``find_nearest_vertex`` on graphs built by
``build_network_graph``, the cases the design review constructed, and whole
paths on the XS city.
"""
import math
import random
import shutil

import pytest
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

from fiberq.utils import routing
from fiberq.utils.geometry import find_nearest_vertex, fuzzy_key, line_parts


class _Counted(QgsPointXY):
    """A graph point that counts how often a search reads it."""

    reads = 0

    def x(self):
        _Counted.reads += 1
        return super().x()


def _graph(points, tolerance):
    """``key -> point`` as build_network_graph makes it: the first point of each cell, in order."""
    keys = {}
    for point in points:
        keys.setdefault(fuzzy_key(point, tolerance), point)
    return keys


def _both(point, keys, tolerance):
    return routing._nearest_key(point, keys, tolerance), find_nearest_vertex(point, keys, tolerance)


def _street_graph(n, tolerance=6.0):
    rng = random.Random(n)
    return _graph([_Counted(rng.uniform(0, 100.0 * n), rng.uniform(0, 1000)) for _ in range(40 * n)], tolerance)


def test_a_search_measures_the_keys_near_the_element_not_the_whole_graph(qgis_app):
    """The linear search read every key: 1,600 at n = 40, 6,400 at n = 160 (it
    reads x() once a key). The grid reads only the keys in 121 cells."""
    reads = []
    for n in (40, 160):
        keys = _street_graph(n)
        query = QgsPointXY(50.0 * n, 500)
        _Counted.reads = 0
        found = routing._nearest_key(query, keys, 6.0)
        reads.append(_Counted.reads)
        assert found == find_nearest_vertex(query, keys, 6.0)
    assert reads[0] <= 121 and reads[1] <= 121, reads
    keys = _street_graph(40)
    _Counted.reads = 0
    find_nearest_vertex(QgsPointXY(2000, 500), keys, 6.0)
    assert _Counted.reads == len(keys)


@pytest.mark.parametrize("tolerance", [6.0, 3.0, 0.5, 1.5, 0.1524, 2.22, 5.39e-5, 1e-3, 30.0])
def test_random_graphs_answer_what_the_linear_search_answers(qgis_app, tolerance):
    """Vertices scattered around queries at every distance up to 6 tolerances,
    snapped to cell edges and centres too, on metric and degree-sized coordinates."""
    rng = random.Random(int(tolerance * 1e6))
    for origin in ((0.0, 0.0), (-3.3e6, 5.1e6), (7.4e6, 2.4e6), (19.8, 45.2)):
        points = []
        for _ in range(400):
            angle, reach = rng.uniform(0, 2 * math.pi), rng.uniform(0, 6 * tolerance)
            points.append(QgsPointXY(origin[0] + reach * math.cos(angle), origin[1] + reach * math.sin(angle)))
        for _ in range(60):
            k = rng.randint(-8, 8)
            points.append(QgsPointXY(origin[0] + (round(origin[0] / tolerance) + k + 0.5) * tolerance - origin[0],
                                     origin[1] + rng.uniform(-3, 3) * tolerance))
        keys = _graph(points, tolerance)
        for _ in range(150):
            query = QgsPointXY(origin[0] + rng.uniform(-5, 5) * tolerance, origin[1] + rng.uniform(-5, 5) * tolerance)
            grid, linear = _both(query, keys, tolerance)
            assert grid == linear, (tolerance, origin, query.asWkt())


def test_a_vertex_exactly_at_the_acceptance_edge_is_accepted_as_before(qgis_app):
    """Design review: math.sqrt(best) == 18.0 <= 6.0 * 3.0, where every squared
    form of the test (best <= (3 * tol) ** 2, ...) rejects it."""
    vertex = QgsPointXY(1018.0, 2000.0000002384186)
    keys = _graph([QgsPointXY(990, 2100), vertex], 6.0)
    grid, linear = _both(QgsPointXY(1000.0, 2000.0), keys, 6.0)
    assert grid == linear == (170, 333)


@pytest.mark.parametrize("query, vertex, key", [
    ((0.5, 0.5), (3.5, 0.5), (4, 0)),
    ((-0.5, 0.5), (-3.5, 0.5), (-4, 0)),
    ((0.5, 0.5), (0.5, 3.5), (0, 4)),
])
def test_a_vertex_four_cells_away_is_still_read(qgis_app, query, vertex, key):
    """The farthest an accepted key can be. round() goes half to even, so a
    query at 0.5 sits in cell 0 and a vertex 3 tolerances away, at 3.5, in
    cell 4: accepted (sqrt(9.0) <= 3.0), four cells out. A window of 3 misses it."""
    keys = _graph([QgsPointXY(*vertex)], 1.0)
    grid, linear = _both(QgsPointXY(*query), keys, 1.0)
    assert grid == linear == key


@pytest.mark.parametrize("first, second", [((10.0, 0.0), (-10.0, 0.0)), ((-10.0, 0.0), (10.0, 0.0))])
def test_a_tie_goes_to_the_first_key_in_the_graph_whichever_cell_is_read_first(qgis_app, first, second):
    """Two vertices equally far from the query, inserted in either order. The
    cells are read from (-2, 0) to (2, 0), so with the graph's first key read
    last only the tie fallback gives the linear answer -- and with it read
    first, only a strict < does (code review: a <= mutant passed the test that
    had the first order alone)."""
    keys = {}
    for x, y in (first, second):
        keys[fuzzy_key(QgsPointXY(x, y), 5.0)] = QgsPointXY(x, y)
    grid, linear = _both(QgsPointXY(0.0, 0.0), keys, 5.0)
    assert grid == linear == fuzzy_key(QgsPointXY(*first), 5.0)


def test_a_three_way_tie_goes_to_the_first_key_in_the_graph(qgis_app):
    """Its first key is the one the cells read in the middle."""
    keys = {}
    for x, y in ((0.0, 10.0), (10.0, 0.0), (-10.0, 0.0)):
        keys[fuzzy_key(QgsPointXY(x, y), 5.0)] = QgsPointXY(x, y)
    grid, linear = _both(QgsPointXY(0.0, 0.0), keys, 5.0)
    assert grid == linear == (0, 2)


def test_a_tolerance_small_enough_to_underflow_is_left_to_the_linear_search(qgis_app):
    """Design review: below ~3e-163, dx * dx underflows to 0.0 and the linear
    search accepts a vertex far outside the 11 x 11 window."""
    keys = _graph([QgsPointXY(1e-165, 0), QgsPointXY(2e-165, 0)], 1e-170)
    grid, linear = _both(QgsPointXY(0, 0), keys, 1e-170)
    assert grid == linear and linear is not None


@pytest.mark.parametrize("tolerance", [0.0, -1.0, float("nan"), float("inf")])
def test_a_tolerance_that_is_not_a_positive_number_is_left_to_the_linear_search(qgis_app, tolerance):
    keys = {(0, 0): QgsPointXY(0.1, 0.1)}
    grid, linear = _both(QgsPointXY(0, 0), keys, tolerance)
    assert grid == linear


def test_a_query_too_many_cells_from_the_origin_is_left_to_the_linear_search(qgis_app):
    far = 2.0 ** 41
    keys = _graph([QgsPointXY(far + 0.4, 0), QgsPointXY(far + 7, 0)], 1.0)
    grid, linear = _both(QgsPointXY(far, 0), keys, 1.0)
    assert grid == linear is not None


@pytest.mark.parametrize("query", [QgsPointXY(float("nan"), 0), QgsPointXY(0, float("inf")),
                                   QgsPointXY(float("-inf"), float("nan"))])
def test_a_query_that_is_not_a_finite_point_finds_nothing_either_way(qgis_app, query):
    keys = _graph([QgsPointXY(0, 0), QgsPointXY(1, 1)], 1.0)
    assert _both(query, keys, 1.0) == (None, None)


def test_an_empty_graph_finds_nothing_either_way(qgis_app):
    assert _both(QgsPointXY(0, 0), {}, 1.0) == (None, None)


def test_whole_paths_on_the_xs_city_are_the_ones_the_linear_search_built(qgis_app, city_xs_dataset, tmp_path):
    """build_path_across_network between route ends, as lay cable calls it (6 px at 0.5 and 2 m/px)."""
    for key in ("gpkg", "qgz"):
        shutil.copy(city_xs_dataset[key], tmp_path)
    project = QgsProject()
    assert project.read(str(tmp_path / "city_XS.qgz"))
    route = project.mapLayersByName("Route")[0]
    parts = [line for feature in route.getFeatures() for line in line_parts(feature.geometry())]
    rng = random.Random(1306)
    found = 0
    for tolerance in (3.0, 12.0):
        for _ in range(25):
            a, b = rng.choice(parts)[0], rng.choice(parts)[-1]
            narrowed = routing.build_path_across_network(route, QgsPointXY(a), QgsPointXY(b), tolerance)
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(routing, "_nearest_key", find_nearest_vertex)
                linear = routing.build_path_across_network(route, QgsPointXY(a), QgsPointXY(b), tolerance)
            as_xy = [None if path is None else [(p.x(), p.y()) for p in path] for path in (narrowed, linear)]
            assert as_xy[0] == as_xy[1]
            found += linear is not None
    assert found > 20, found
    project.clear()
    del project


def test_the_counting_point_is_still_a_point(qgis_app):
    """The counted test's points must behave exactly like the graph's own."""
    point = _Counted(3.0, 4.0)
    assert (point.x(), point.y()) == (3.0, 4.0) and point.distance(QgsPointXY(0, 0)) == 5.0
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "p", "memory")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(point))
    assert feature.geometry().asPoint() == QgsPointXY(3.0, 4.0)
