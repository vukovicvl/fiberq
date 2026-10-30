# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""What a route end may sit on, and how far Route correction's Correct may move one.

Q21 (v1.6.0 QA, unclaimed). Route correction counted only Poles and Manholes as
a place a route may end, so every end FiberQ itself makes elsewhere was an
error: a drop ending at an OTB, a TO, an ODF or a closure, a branch drawn from
another route's vertex, the two halves Add breakpoint, Split route and Cut
infrastructure leave behind. Correct then dragged that end onto the nearest
pole or manhole at any distance -- 20.66 m on the maintainer's project, any
number of kilometres in general -- saved it at once, and so pulled routes off
the very infrastructure they were connected to.

FiberQ connects things by sharing coordinates, and its own tools already agree
on what a route end may sit on:

* Create a route manually snaps to Poles, Manholes, Joint Closures, the twelve
  element layers, route vertices and segment midpoints (tools/route_tool.py);
* Lay cable takes those same fifteen layers as a cable's two ends, and crosses
  from one route to the next only at a vertex the two share -- its network
  search joins routes by vertex (core/cable_manager.py, utils/routing.py);
* Validate's A1 accepts those fifteen layers as a cable's termination
  (core/validation_rules._NODE_LAYERS, which this list mirrors);
* Add breakpoint, Split route and Cut infrastructure leave two halves that meet
  at a shared point.

This module is that agreement, written down once for the check and for Correct,
so the two cannot disagree: an end Correct is offered for is one the check
found loose, and Correct moves nothing the check would call connected.

It lives in ``core`` rather than ``utils`` because it is FiberQ's own rule about
FiberQ's own layers; the primitives it is built from -- the ordered index, the
box query on a provider, the ground measurement -- are the generic ones in
``utils``.
"""
import math

from qgis.core import QgsFeatureRequest, QgsPointXY, QgsVectorLayer, QgsWkbTypes

from ..models.schema import ELEMENT_LAYER_NAMES, canonical_layer_name
from ..utils.geometry import geometry_point
from ..utils.measure import distance_area
from ..utils.spatial import ScanOrderIndex, features_near

#: The layers a route end may sit on, by canonical name: Poles, Manholes, Joint
#: Closures and the twelve element layers. Their old names (Stubovi, OKNA,
#: Nastavci, Patch Panel) resolve through ``canonical_layer_name``.
NODE_LAYERS = ("Poles", "Manholes", "Joint Closures") + tuple(ELEMENT_LAYER_NAMES)

#: Line layers laid along routes. Correct never pulls a route end away from one
#: of these: a laid cable keeps only its from/to names and a copy of the route's
#: points, and a duct the same points, so a route moved alone leaves them behind.
ALONG_LAYERS = ("Aerial cables", "Underground cables", "PE pipes", "Transition pipes")

#: Nearer than this, in the Route layer's units, an end is ON something. The
#: tolerance Route correction has used since v1.1, unchanged.
ON = 1e-2

#: The furthest Correct moves a route end, in metres on the ground. It covers an
#: end left behind when a pole was nudged, or a route imported from GPS or KML a
#: few metres off; it is Validate's default snapping tolerance (A1, A2); and it
#: is far below the 30-150 m between one pole or manhole and the next, so the
#: nearest point within it is the one meant.
MAX_MOVE_M = 5.0


def node_layers(project):
    """Every valid point layer whose canonical name is in :data:`NODE_LAYERS`, in ``mapLayers()`` order.

    Every one, not the first of each name: a project holding both ``Poles`` and
    a pre-1.0 ``Stubovi`` had the second one's poles ignored. A layer of another
    geometry type under one of these names is passed over -- a polygon
    ``Manholes`` layer used to stop the check with ``TypeError: Polygon geometry
    cannot be converted to a point``.
    """
    found = []
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            continue
        if layer.geometryType() != QgsWkbTypes.GeometryType.PointGeometry:
            continue
        if canonical_layer_name(layer.name()) in NODE_LAYERS:
            found.append(layer)
    return found


#: The side of a :class:`_PointGrid` cell, in the Route layer's units: twice
#: :data:`ON`, so the nine cells around an end hold every point nearer than ON.
_CELL = 2 * ON

#: Beyond this a coordinate is not filed in a cell but kept aside and offered to
#: every question. Below it the rounding of ``x / _CELL`` is under 1/128 of a
#: cell, so two points less than ON apart -- half a cell -- can never land two
#: cells apart. No coordinate system comes near it (Web Mercator: 2e7).
_FILED = 2.0 ** 40


def _cell(point):
    """The grid cell of ``point``, or None for a coordinate that is not a number, infinite or beyond :data:`_FILED`."""
    x, y = point.x(), point.y()
    if not (abs(x) <= _FILED and abs(y) <= _FILED):
        return None
    return math.floor(x / _CELL), math.floor(y / _CELL)


class _PointGrid:
    """Points filed in square cells, asked for the ones that may lie within :data:`ON` of a point.

    PF-3 indexed Poles and Manholes in a ``ScanOrderIndex``, whose
    ``QgsSpatialIndex`` costs about 10 us a point to fill. Q21 reads all fifteen
    node layers -- on the benchmark's S city 4,880 points where Poles and
    Manholes were 2,660 -- and filling a ScanOrderIndex with them took 52 ms,
    which with the route index left the check alone 27-44% slower than before
    it on the S and M cities. This grid fills in 2.4 ms and answers the S
    city's 3,632 route ends in 7 ms where the index took 29 (QGIS 3.44.15 and
    4.2.3 alike). A grid is enough because the check asks only whether ANY
    point is near, never which one comes first, so the order a ScanOrderIndex
    keeps is not needed.

    What :meth:`near` hands out is a superset of the points within ON, and the
    check's own test still decides, as with PF-3's index: points in the nine
    cells around the question's, plus the points no cell could hold, and every
    point when the question itself cannot be placed.
    """

    def __init__(self):
        self._cells = {}
        self._items = []
        self._aside = []

    def __len__(self):
        return len(self._items)

    def add(self, item, point):
        """File ``item``, which sits at ``point``."""
        self._items.append(item)
        cell = _cell(point)
        if cell is None:
            self._aside.append(item)
        else:
            self._cells.setdefault(cell, []).append(item)

    def near(self, point):
        """The items that may lie within :data:`ON` of ``point``; a superset."""
        cell = _cell(point)
        if cell is None:
            return list(self._items)
        column, row = cell
        found = []
        cells = self._cells
        for x in (column - 1, column, column + 1):
            for y in (row - 1, row, row + 1):
                found.extend(cells.get((x, y), ()))
        found.extend(self._aside)
        return found


def node_index(layers):
    """``(_PointGrid of (layer, fid, point), how many features have no position)``.

    Read once per check, geometry only. A feature with no geometry is counted,
    not filed (R10): QGIS makes one whenever a row is added without
    digitising, and ``asPoint()`` raises on it.
    """
    index = _PointGrid()
    without = 0
    for layer in layers:
        for feature in layer.getFeatures(QgsFeatureRequest().setNoAttributes()):
            point = geometry_point(feature.geometry())
            if point is None:
                without += 1
                continue
            index.add((layer, feature.id(), point), point)
    return index, without


def on_a_node(point, nodes):
    """True when a node in ``nodes`` (a :func:`node_index`) is within :data:`ON` of ``point``.

    The test, and the same ``QgsPointXY.distance``, the check has always made;
    the grid only hands it the nodes near enough to pass (PF-3, Q21).
    """
    return any(node.distance(point) < ON for _layer, _fid, node in nodes.near(point))


def meets_a_node(point, layers):
    """:func:`on_a_node` for one point, asking each layer's provider instead of an index.

    For Correct, which looks at one end and would read every node in the project
    to build the index. Each layer is asked for the box around ``point``
    (``utils.spatial.features_near``), or read whole where that cannot be had
    exactly, and the same test decides.
    """
    for layer in layers:
        near = features_near(layer, point, ON, geometry_only=True)
        features = layer.getFeatures(QgsFeatureRequest().setNoAttributes()) if near is None else near
        for feature in features:
            node = geometry_point(feature.geometry())
            if node is not None and node.distance(point) < ON:
                return True
    return False


def route_index(features):
    """A ScanOrderIndex of ``(fid, geometry, feature)`` over route features, by bounding box."""
    index = ScanOrderIndex()
    for feature in features:
        geom = feature.geometry()
        if geom is None or geom.isNull() or geom.isEmpty():
            continue
        index.add((feature.id(), geom, feature), geom.boundingBox())
    return index


def touching_route(point, fid, candidates):
    """How the end at ``point`` of route ``fid`` meets another route.

    ``candidates`` are ``(fid, geometry, feature)``, from :func:`route_index` or
    :func:`routes_near`. Answers ``('vertex', feature)`` when another route has a
    vertex -- an end or an inner one -- within :data:`ON`: a junction Lay cable
    can route through. ``('segment', feature)`` when it only touches another
    route between two of its vertices, which Lay cable cannot cross, because
    its network joins routes at shared vertices only. ``(None, None)`` when it
    touches no other route. A vertex anywhere beats a segment.
    """
    segment = None
    for other, geom, feature in candidates:
        if other == fid:
            continue
        squared = geom.closestVertex(point)[4]
        if 0 <= squared < ON * ON:
            return 'vertex', feature
        squared = geom.closestSegmentWithContext(point)[0]
        if segment is None and 0 <= squared < ON * ON:
            segment = feature
    return ('segment', segment) if segment is not None else (None, None)


def routes_near(route_layer, point):
    """``(fid, geometry, feature)`` for the routes whose box comes within :data:`ON` of ``point``.

    The whole layer where the box cannot be had exactly; :func:`touching_route`
    decides either way.
    """
    near = features_near(route_layer, point, ON, geometry_only=True)
    for feature in (route_layer.getFeatures(QgsFeatureRequest().setNoAttributes()) if near is None else near):
        geom = feature.geometry()
        if geom is None or geom.isNull() or geom.isEmpty():
            continue
        yield feature.id(), geom, feature


def _reach(point, measure, metres):
    """Map units around ``point`` that hold every place within ``metres`` on the ground, or None.

    From the local metres per map unit, the smaller of east and north, so the
    square box is a superset: in Web Mercator at 45 N one unit is 0.71 m, so
    5 m is about 7 units; in a geographic CRS a degree east is shorter than a
    degree north. 5% on top for the scale changing across the box. None when
    the measurement gives no usable figure; the caller then reads every node.
    """
    per_unit = min(measure.measureLine(point, QgsPointXY(point.x() + 1.0, point.y())),
                   measure.measureLine(point, QgsPointXY(point.x(), point.y() + 1.0)))
    if not (math.isfinite(per_unit) and per_unit > 0):
        return None
    return metres / per_unit * 1.05


def nearest_node(point, crs, layers, metres=MAX_MOVE_M):
    """``(layer, fid, node point, metres away)`` for the nearest node within ``metres``, else None.

    Measured on the ground with FiberQ's own measurement (``utils.measure``,
    the project's ellipsoid, else the CRS's: what stored lengths use), so the
    limit means the same in Web Mercator, a UTM zone and a geographic CRS. In
    map units it would not: a Web Mercator unit is 0.71 m at 45 N, and a degree
    is 79-111 km. Ties go to the first node met, in layer and scan order.
    """
    measure = distance_area(crs)
    reach = _reach(point, measure, metres)
    best = None
    for layer in layers:
        near = None if reach is None else features_near(layer, point, reach, geometry_only=True)
        features = layer.getFeatures(QgsFeatureRequest().setNoAttributes()) if near is None else near
        for feature in features:
            node = geometry_point(feature.geometry())
            if node is None:
                continue  # R10: a node with no position is not a target
            away = measure.measureLine(point, node)
            if not math.isfinite(away) or away > metres:
                continue
            if best is None or away < best[3]:
                best = (layer, feature.id(), node, away)
    return best


def lines_at(point, project):
    """Labels of the cables and ducts with a vertex within :data:`ON` of ``point``.

    Any vertex, not only an end: a cable laid along this route and on along the
    next one passes through the junction as an inner vertex, and is left behind
    just the same.
    """
    found = []
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            continue
        if layer.geometryType() != QgsWkbTypes.GeometryType.LineGeometry:
            continue
        if canonical_layer_name(layer.name()) not in ALONG_LAYERS:
            continue
        near = features_near(layer, point, ON)
        for feature in (layer.getFeatures() if near is None else near):
            geom = feature.geometry()
            if geom is None or geom.isNull() or geom.isEmpty():
                continue
            if 0 <= geom.closestVertex(point)[4] < ON * ON:
                found.append(feature_label(layer, feature))
    return found


def _name_of(feature, fields=("naziv", "broj_okna", "oznaka")):
    """The first of ``fields`` the feature has a value in, else ``""``."""
    for name in fields:
        index = feature.fields().indexOf(name)
        if index < 0:
            continue
        value = feature.attribute(index)
        text = "" if value is None else str(value).strip()
        if text and text != "NULL":
            return text
    return ""


def feature_label(layer, feature):
    """``Manholes '12312' (ID 4)``, or ``Poles (ID 4)`` for one with no name.

    The name is ``naziv``, else a manhole's ``broj_okna``, else an element's
    ``oznaka``; the layer is named as the project shows it.
    """
    name = _name_of(feature)
    return f"{layer.name()} '{name}' (ID {feature.id()})" if name else f"{layer.name()} (ID {feature.id()})"


def route_label(feature):
    """``'Route 7' (ID 15)``, or ``(ID 15)`` for a route with no name."""
    name = _name_of(feature, ("naziv",))
    return f"'{name}' (ID {feature.id()})" if name else f"(ID {feature.id()})"
