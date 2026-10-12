"""
FiberQ v2 - Geometry Utilities Module

This module contains geometry utility functions for point manipulation,
snapping, distance calculations, and coordinate transformations.
"""

import math
import sys
from array import array
from typing import Optional, Tuple, List, Dict
from qgis.core import (QgsCurvePolygon, QgsGeometry, QgsGeometryCollection, QgsGeometryUtils, QgsPointXY,
                       QgsVectorLayer, QgsWkbTypes)

# Phase 5.2: Logging
from .logger import get_logger
logger = get_logger(__name__)


# =============================================================================
# COORDINATE KEY FUNCTIONS
# =============================================================================

def round_key(pt: QgsPointXY, tolerance: float) -> Tuple[int, int]:
    """
    Create a fuzzy coordinate key for a point.

    Points within the same tolerance grid cell will have the same key,
    enabling efficient snapping and vertex matching.

    Args:
        pt: Point to create key for
        tolerance: Grid cell size for rounding

    Returns:
        Tuple of (x_key, y_key) as integers
    """
    return (round(pt.x() / tolerance), round(pt.y() / tolerance))


def fuzzy_key(pt: QgsPointXY, tolerance: float) -> Tuple[int, int]:
    """
    Create a fuzzy coordinate key using integer rounding.

    Similar to round_key but uses int() instead of round() for
    consistent behavior at grid boundaries.

    Args:
        pt: Point to create key for
        tolerance: Grid cell size

    Returns:
        Tuple of (x_key, y_key) as integers
    """
    return (int(round(pt.x() / tolerance)), int(round(pt.y() / tolerance)))


# =============================================================================
# GEOMETRY EXTRACTION FUNCTIONS
# =============================================================================

def get_first_last_points(geom: QgsGeometry) -> Tuple[Optional[QgsPointXY], Optional[QgsPointXY], List[QgsPointXY]]:
    """
    Extract first point, last point, and all points from a line geometry.

    Handles both simple LineString and MultiLineString geometries.
    For MultiLineString, only the first part is used.

    Args:
        geom: Line geometry to extract points from

    Returns:
        Tuple of (first_point, last_point, all_points_list)
        Returns (None, None, []) if geometry is invalid
    """
    line = line_vertices(geom, first_part_only=True)
    if len(line) < 2:
        return None, None, []

    return (
        QgsPointXY(line[0]),
        QgsPointXY(line[-1]),
        [QgsPointXY(p) for p in line]
    )


def line_vertices(geom: QgsGeometry, first_part_only: bool = False) -> List[QgsPointXY]:
    """The vertices of a line geometry, multipart or not. ``[]`` if it has none.

    **The multipart case is tested first, and that is the whole point.**
    ``asPolyline()`` does not answer an empty list for a MultiLineString: it
    raises ``TypeError`` (measured on 3.44.15 and 4.0.3). So the idiom this
    replaces --

        line = geom.asPolyline()
        if not line:
            multi = geom.asMultiPolyline()   # unreachable

    -- could never reach its own fallback, and every caller died on the first
    multipart feature instead of handling it. A Route or cable layer becomes
    multipart through an imported shapefile, a QGIS merge or a provider that
    promotes on write, so this is not a theoretical shape.

    Args:
        geom: The geometry to read.
        first_part_only: Return only the first part of a multipart geometry.
            That is what a caller wants when it needs *one* line's two ends;
            the default concatenates every part, which is what a caller
            counting vertices wants.
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return []
    if geom.type() != QgsWkbTypes.GeometryType.LineGeometry:
        # A point or polygon answers asPolyline() with a TypeError, not an
        # empty list (measured on both stacks), so the type is checked before
        # the shape. A route importer handed a point GeoJSON used to die here.
        return []
    if QgsWkbTypes.isMultiType(geom.wkbType()):
        parts = geom.asMultiPolyline()
        if not parts:
            return []
        if first_part_only:
            return [QgsPointXY(p) for p in parts[0]]
        vertices = []
        for part in parts:
            vertices.extend([QgsPointXY(p) for p in part])
        return vertices
    return [QgsPointXY(p) for p in geom.asPolyline()]


def extract_line_vertices(geom: QgsGeometry) -> List[QgsPointXY]:
    """Every vertex of a line geometry. See :func:`line_vertices`."""
    return line_vertices(geom)


def line_endpoint(geom: QgsGeometry, last: bool = False) -> Tuple[Optional[QgsPointXY], int]:
    """A line's first or last vertex, with the index ``moveVertex`` wants.

    Answers ``(None, -1)`` when ``geom`` holds fewer than two line vertices.

    **The point and the index both come from the stored coordinates**, through
    ``constGet().nCoordinates()`` and ``vertexAt()``, and that is deliberate.
    ``line_vertices`` goes through ``asPolyline()``, which SEGMENTIZES a
    CircularString, a CompoundCurve or a MultiCurve -- it runs ``curveToLine()``
    first -- while ``moveVertex`` indexes the coordinates the geometry really
    holds. Counting one and indexing the other moves the wrong coordinate, and
    ``moveVertex`` still answers True, so nothing notices. Measured on 3.22.16,
    3.44.15, 4.0.3 and 4.2.3::

        CircularString (0 0, 500 1, 1000 0)   stored 3, segmentized 2
        CircularString (0 0, 5 5, 10 0)       stored 3, segmentized 181

    A 1 km road curve with 1 m of sag is the first of those: its segmentized
    count of 2 makes index 1 look like the end, when index 1 is the arc's middle
    control point. Dragging that onto a pole turns a 1000 m route into a 6.28 m
    circle, with the end still unattached. The second segmentizes to MORE points
    than it stores, so the index overshoots and ``vertexAt`` answers
    ``(nan nan)``. For every linear geometry the two counts are equal, which is
    why a MultiLineString test alone cannot see any of this.

    The index runs flat across the parts of a multipart geometry: the last
    vertex of a two-by-two MultiLineString is index 3, not part 1 vertex 1.
    Handing it to :meth:`QgsGeometry.moveVertex` edits the geometry **in place
    and keeps its part structure and its wkbType**, where rebuilding the line
    from ``line_vertices`` and ``QgsGeometry.fromPolylineXY`` silently throws
    every part but the first away -- and a GeoPackage Route layer accepts that
    single-part geometry, commits "SUCCESS" and loses the rest of the route on
    disk (measured on 3.44.15: a 2-part, 20 m route reloaded as 1 part, 31 m).

    "Last" means the last vertex of the last part, not of the first part. For a
    single-part line, which is nearly every route, that is the same vertex it
    always was.

    Args:
        geom: The geometry to read.
        last: Answer the last vertex rather than the first.
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return None, -1
    if geom.type() != QgsWkbTypes.GeometryType.LineGeometry:
        # A point or polygon has ends, but not ones this is about, and
        # vertexAt() would answer a coordinate from a ring.
        return None, -1
    stored = geom.constGet()
    if stored is None:
        return None, -1
    count = stored.nCoordinates()
    if count < 2:
        return None, -1
    index = count - 1 if last else 0
    return QgsPointXY(geom.vertexAt(index)), index


def line_part_count(geom: QgsGeometry) -> int:
    """How many separate pieces a line geometry is in. ``0`` when it is not a line.

    ``partCount()`` answers 1 for a plain LineString, 1 for a CompoundCurve
    (which is ONE line made of several segments, not several lines) and 1 for a
    MultiLineString that happens to hold a single part; it answers the real
    number for a MultiLineString or a MultiCurve with more. Measured on
    3.22.16, 3.44.15 and 4.0.3. ``isMultipart()`` is not the same question --
    it is true for a one-part MultiLineString, and an **ESRI Shapefile** line
    layer hands back exactly that for every feature, single-part or not: the
    format does not distinguish, so OGR declares the layer MultiLineString and
    `asPolyline()` raises on all of it. A GeoPackage only does so when the
    column itself was declared MultiLineString; FiberQ's own GeoPackage export
    writes a LineString column, so its routes read back single-part. Measured
    on all three.
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return 0
    if geom.type() != QgsWkbTypes.GeometryType.LineGeometry:
        return 0
    stored = geom.constGet()
    if stored is None:
        return 0
    return stored.partCount()


def line_parts(geom: QgsGeometry) -> List[List[QgsPointXY]]:
    """Each separate line in a geometry, as its own list of points. ``[]`` if none.

    The multipart case is tested FIRST, as in :func:`line_vertices`, and for the
    same measured reason: ``asPolyline()`` does not answer an empty list for a
    multipart geometry, it raises ``TypeError``. So the idiom this replaces --

        line = geom.asPolyline()
        if not line:
            multi = geom.asMultiPolyline()   # unreachable
            line = multi[0]

    -- can never reach its own fallback. Whatever the fallback was written to
    handle, it handles nothing. ``asMultiPolyline()`` is the mirror image and
    raises on a single-part LineString, so neither call is safe unguarded.
    Measured on 3.22.16, 3.44.15 and 4.0.3.

    This matters far beyond genuinely branching routes, because an **ESRI
    Shapefile** line layer reads back as MultiLineString even when every feature
    is a plain two-point line (the format has no single/multi distinction, so
    OGR declares the layer from the format, not the content). A shapefile is the
    ordinary way to bring an existing network into QGIS, and
    ``RouteManager._find_route_layer`` tests ``geometryType()`` -- the dimension
    -- so such a layer is accepted as the Route layer and reaches every caller
    here.

    Returns one list per part, each with at least two points; parts with fewer
    are dropped, because a one-point "line" is not something a caller counting
    segments, chaining routes or measuring length can use. A caller that wants
    one flat list of vertices wants :func:`line_vertices`; a caller that wants
    one line's two ends wants :func:`line_endpoint`.

    The lists are the ones ``asPolyline()`` / ``asMultiPolyline()`` build, which
    are new on every call, so they are handed over as they are. The routing
    graph calls this once per route on every lay cable; copying each point
    again, and asking ``type()`` and ``wkbType()`` -- each answer a Python enum,
    ~1.5 us apiece on QGIS 3.44 -- made that build a third slower than v1.5.0's
    (route_path, 3.44.15: 0.251 s against 0.192 s at size S, 1.75 s against
    1.32 s at L). A point or a polygon is told apart by the ``TypeError`` both
    calls raise for anything that is not a line, a single line from a multipart
    one by ``isMultipart()``: the tests both checks used to make, made in C++.
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return []
    try:
        if geom.isMultipart():
            parts = geom.asMultiPolyline() or []
        else:
            parts = [geom.asPolyline()]
    except TypeError:
        # Not a line: a point, a polygon, a collection. A null geometry would
        # be a ValueError, which is why it is turned away above.
        return []
    return [part for part in parts if len(part) >= 2]


def polylines(geom: QgsGeometry) -> List[List[QgsPointXY]]:
    """``asMultiPolyline()`` of a multi-part line, ``[asPolyline()]`` of a single one, ``[]`` for anything else.

    The point lists exactly as those two calls give them -- one-vertex and empty
    parts included, unlike :func:`line_parts` -- for a search that measures
    every vertex. Both calls raise TypeError for a point or a polygon: a Route
    table can hold one (GDAL stores a point in a LINESTRING GeoPackage table,
    with a warning, and an edit buffer takes one too), and a search that let the
    TypeError end its whole loop never saw the routes after it.
    """
    try:
        if geom.isMultipart():
            return geom.asMultiPolyline()
        return [geom.asPolyline()]
    except TypeError:
        return []


def _pieces(shape):
    """The non-empty simple curves -- LineStrings, CircularStrings, ... -- a line shape is made of.

    Walks a multi-part shape part by part and a CompoundCurve component by
    component, and never asks a CompoundCurve for its own coordinates: with an
    empty component its ``nCoordinates()`` is a SIGSEGV on QGIS 4.0.3 and
    4.2.3, and its ``vertices()`` walks one vertex fewer per empty component,
    so it stops short, and never ends once that count is below zero -- one
    vertex and two empty arcs -- on 3.22.16, 3.44.15 and 4.2.3 alike, while
    each component answers safely (code reviews of branch 13). QGIS's own
    calls on such a curve -- its box, ``asPolyline()``, the closest vertex and
    segment -- are safe, and the scans the snaps keep made only those.
    """
    kind = QgsWkbTypes.displayString(QgsWkbTypes.flatType(shape.wkbType()))
    if kind.startswith("Multi") or kind == "GeometryCollection":
        for i in range(shape.numGeometries()):
            yield from _pieces(shape.geometryN(i))
    elif kind == "CompoundCurve":
        for i in range(shape.nCurves()):
            curve = shape.curveAt(i)
            if not curve.isEmpty():
                yield curve
    elif not shape.isEmpty():
        yield shape


def has_a_one_vertex_part(geom: QgsGeometry) -> bool:
    """True when a part of the line ``geom`` has exactly one vertex.

    Invalid geometry GEOS cannot test: on QGIS 3.22 a GeoPackage or shapefile
    box query drops a MultiLineString with such a part, because OGR's own
    intersection test fails on it (3.44.15 and 4.2.3 return it). Counted one
    component at a time (``_pieces``); an empty part counts as none. False for
    null geometry and for anything that is not a line.
    """
    if geom is None or geom.isNull() or geom.type() != QgsWkbTypes.GeometryType.LineGeometry:
        return False
    shape = geom.constGet()
    if QgsWkbTypes.isMultiType(geom.wkbType()):
        parts = [shape.geometryN(i) for i in range(shape.numGeometries())]
    else:
        parts = [shape]
    return any(sum(piece.numPoints() for piece in _pieces(part)) == 1 for part in parts)


def _xy_of(line):
    """The x and y coordinates of the LineString ``line`` as two arrays of doubles, read from its WKB.

    A QgsPoint per vertex costs 1.4-2.9 us on QGIS 3.44, which made the check
    below take 37 ms on a 20,000-vertex route that QGIS measures in 0.65 ms
    (code review); the WKB is read at C speed instead. None when it is not laid
    out as expected, and the caller then walks the points.
    """
    data = bytes(line.asWkb())
    stride = 2 + int(QgsWkbTypes.hasZ(line.wkbType())) + int(QgsWkbTypes.hasM(line.wkbType()))
    size = 8 * stride * line.numPoints()
    if len(data) != 9 + size or data[0] not in (0, 1):
        return None
    values = array("d")
    values.frombytes(data[9:])
    if data[0] != (1 if sys.byteorder == "little" else 0):
        values.byteswap()
    return values[0::stride], values[1::stride]


def has_an_arc_without_a_circle(curve) -> bool:
    """True when an arc of the curve geometry ``curve`` has its three points in a row.

    QGIS boxes an arc from the circle through its three points, and three
    points in a row have none: ``circleCenterRadius`` answers radius -1 and
    never sets the centre the box is then built from, so the box is whatever
    that memory held -- (-1e130, -1, 1020, 2000) for one arc on 3.22.16.
    """
    kind = QgsWkbTypes.displayString(QgsWkbTypes.flatType(curve.wkbType()))
    if kind == "CircularString":
        points = curve.points()
        return any(QgsGeometryUtils.circleCenterRadius(*points[i:i + 3])[0] < 0
                   for i in range(0, len(points) - 2, 2))
    if kind == "CompoundCurve":
        return any(has_an_arc_without_a_circle(curve.curveAt(i)) for i in range(curve.nCurves()))
    if kind.startswith("Multi"):
        return any(has_an_arc_without_a_circle(curve.geometryN(i)) for i in range(curve.numGeometries()))
    return False


def held_by_its_box(geom: QgsGeometry, slack: float = 0.0) -> bool:
    """False for a line, or a MultiPoint, a box query can miss where a scan measuring it would not.

    For the searches that read only the features whose box comes near a point
    (``utils.spatial.features_near``) instead of every feature: they skip what
    this turns away, read whole or narrowed alike, so the two answer the same.
    Measured on QGIS 3.22.16, 3.44.15 and 4.2.3 with a box of half-side 1 m
    around a point 0.3 m from a good vertex, a box query misses:

    * a line with a coordinate that is not a finite number, on a GeoPackage
      when it is the first vertex or sits in a part of a multi-part line
      (GDAL boxes a part from its first vertex, so a NaN there leaves that
      bound NaN -- stored as 0 -- and the row's box can miss its good
      vertices), on a memory layer with a spatial index of its own wherever
      it is. A shapefile cannot hold one: GDAL refuses to write it;
    * a MultiLineString with a one-vertex part, on 3.22 (GeoPackage,
      shapefile): OGR's own intersection test fails on it;
    * an arc whose three points are in a row (QGIS's box of it is garbage),
      and on 3.22 an arc starting exactly at (0, 0), whose box leaves that start
      out. Both are caught by holding every vertex, and every point of the
      segmentized line, to the box;
    * a MultiPoint with a part QGIS reads as empty -- one with a coordinate that
      is not a number -- on a GeoPackage, where a part whose other coordinate
      lies far away left the whole feature out of the box query (3.22.16 and
      4.2.3, round-5 review), and in an edit buffer, whose GEOS test dropped one
      with a NaN y first;
    * a GeometryCollection or a polygon with such a part or ring -- an empty
      point, a one-vertex line, a coordinate that is not a number -- which GDAL
      boxes the same way (round-6 review, 3.22.16 to 4.2.3): a collection is
      judged by its parts and a polygon by its rings, with the rules above.

    QGIS's own snapping misses the lines starting or ending at NaN or infinity
    too, and the arcs in a row wherever their box does; it finds a line whose
    NaN sits in the middle and leaves its box finite, and the one-vertex parts.
    So does FiberQ's whole-layer scan, and turning those away is a behaviour
    change (agreed 2026-10-12, the MultiPoints the same day after round 5, the
    collections and polygons on 2026-10-13 after round 6), not a fix: it is
    what lets the box query answer what the scan does.

    Everything else is held: points (a point that is not a number reads back as
    an empty one, which no scan measures), a MultiPoint whose parts are all
    points, a one-vertex line on its own, a line's empty parts and empty
    components. Null and empty geometry is not, as no scan measures it either.
    ``slack`` is how far outside its box an arc's segmentized points may lie: a
    correct box holds its arc to within 2e-6 of the arc's size (20,000 random
    arcs, branch 12), so half the search's tolerance is ample and still inside
    a query of twice it.
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return False
    if geom.type() == QgsWkbTypes.GeometryType.PointGeometry:
        if not QgsWkbTypes.isMultiType(geom.wkbType()):
            return True
        shape = geom.constGet()
        return not any(shape.geometryN(i).isEmpty() for i in range(shape.numGeometries()))
    if geom.type() != QgsWkbTypes.GeometryType.LineGeometry:
        return _parts_held(geom.constGet(), slack)
    if QgsWkbTypes.isMultiType(geom.wkbType()) and has_a_one_vertex_part(geom):
        return False
    box = geom.boundingBox()
    low_x, low_y = box.xMinimum() - slack, box.yMinimum() - slack
    high_x, high_y = box.xMaximum() + slack, box.yMaximum() + slack
    if not all(math.isfinite(value) for value in (low_x, low_y, high_x, high_y)):
        return False
    for piece in _pieces(geom.constGet()):
        coordinates = None
        if QgsWkbTypes.displayString(QgsWkbTypes.flatType(piece.wkbType())) == "LineString":
            coordinates = _xy_of(piece)
        if coordinates is not None:
            xs, ys = coordinates
            if not (all(map(math.isfinite, xs)) and all(map(math.isfinite, ys))):
                return False
            if xs and not (low_x <= min(xs) and max(xs) <= high_x and low_y <= min(ys) and max(ys) <= high_y):
                return False
        # NaN fails both comparisons, so a vertex that is not a number is outside too.
        elif not all(low_x <= point.x() <= high_x and low_y <= point.y() <= high_y for point in piece.points()):
            return False
    if QgsWkbTypes.isCurvedType(geom.wkbType()):
        if has_an_arc_without_a_circle(geom.constGet()):
            return False
        return all(low_x <= point.x() <= high_x and low_y <= point.y() <= high_y
                   for line in line_parts(geom) for point in line)
    return True


def _parts_held(shape, slack: float) -> bool:
    """``held_by_its_box`` for a shape that is neither a point nor a line: a polygon ring by ring, a collection part by part.

    An empty point part (a coordinate that is not a number reads back so) and
    a one-vertex line, ring or part are turned away outright, as in a multi-part
    shape; another empty part is no part at all; every other part or ring is
    held to the point and line rules. A curve is counted through its pieces
    (``_pieces``), never by its own coordinates. Any other shape is held.
    """
    if isinstance(shape, QgsCurvePolygon):
        parts = [shape.exteriorRing()] + [shape.interiorRing(i) for i in range(shape.numInteriorRings())]
    elif isinstance(shape, QgsGeometryCollection):
        parts = [shape.geometryN(i) for i in range(shape.numGeometries())]
    else:
        return True
    for part in parts:
        if part is None:
            continue
        kind = QgsWkbTypes.geometryType(part.wkbType())
        if kind == QgsWkbTypes.GeometryType.PointGeometry:
            if part.isEmpty():
                return False
        elif kind == QgsWkbTypes.GeometryType.LineGeometry:
            vertices = sum(piece.numPoints() for piece in _pieces(part))
            if vertices == 0:
                continue
            if vertices == 1:
                return False
        elif part.isEmpty():
            continue
        if not held_by_its_box(QgsGeometry(part.clone()), slack):
            return False
    return True


def is_finite(geom: QgsGeometry) -> bool:
    """True when every coordinate of ``geom`` is a real number.

    A reprojection that cannot work does **not** raise: measured on 3.44.15 and
    4.0.3, ``QgsGeometry.transform`` answers
    ``GeometryOperationResult.Success`` and leaves ``LineString (inf inf, inf
    inf)`` behind. So catching ``QgsCsException`` is not enough on its own --
    an importer that only did that wrote infinite geometry into the project and
    reported success. Checked on the bounding box, which is one call and covers
    every vertex.
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return False
    box = geom.boundingBox()
    return all(math.isfinite(value) for value in
               (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()))


def transformed(geom: QgsGeometry, transform) -> Optional[QgsGeometry]:
    """A copy of ``geom`` in the transform's target CRS, or ``None``.

    ``None`` means "this feature cannot be reprojected" -- either the transform
    raised, or it succeeded and produced coordinates that are not numbers (see
    :func:`is_finite`). A caller importing many features skips and counts those
    rather than letting one of them end the import.
    """
    if geom is None or geom.isNull():
        return None
    moved = QgsGeometry(geom)
    try:
        moved.transform(transform)
    except Exception as exc:  # QgsCsException, and anything the proj stack adds
        logger.warning(f"Could not reproject a geometry: {exc}")
        return None
    return moved if is_finite(moved) else None


def geometry_point(geom: QgsGeometry) -> Optional[QgsPointXY]:
    """The point of a point geometry, or ``None`` when it has none.

    ``asPoint()`` on a feature with no geometry is
    ``ValueError: Null geometry cannot be converted to a point.`` (measured on
    both stacks), and a layer can hold such a feature perfectly happily -- QGIS
    creates one whenever a row is added without digitising. Callers that sweep
    a whole layer have to expect it.
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return None
    if QgsWkbTypes.isMultiType(geom.wkbType()):
        parts = geom.asMultiPoint()
        return QgsPointXY(parts[0]) if parts else None
    return QgsPointXY(geom.asPoint())


def convert_to_simple_line(geom: QgsGeometry) -> Optional[QgsGeometry]:
    """
    Convert a MultiLineString with one part to a simple LineString.

    Args:
        geom: Geometry to convert

    Returns:
        Simple LineString geometry or None if conversion not possible
    """
    if geom is None or geom.isEmpty():
        return None

    if not geom.isMultipart():
        return geom

    lines = geom.asMultiPolyline()
    if lines and len(lines) == 1:
        return QgsGeometry.fromPolylineXY(lines[0])

    return None


# =============================================================================
# SNAPPING UTILITIES
# =============================================================================

def snap_point_to_layer(
    point: QgsPointXY,
    layer: QgsVectorLayer,
    tolerance: float,
    geometry_type: int = None
) -> Optional[QgsPointXY]:
    """
    Snap a point to the nearest vertex in a layer.

    Args:
        point: Point to snap
        layer: Layer to snap to
        tolerance: Maximum snap distance
        geometry_type: Expected geometry type (QgsWkbTypes constant)

    Returns:
        Snapped point or None if no vertex within tolerance
    """
    if layer is None or not layer.isValid():
        return None

    if geometry_type is not None and layer.geometryType() != geometry_type:
        return None

    min_dist = float('inf')
    snapped_point = None

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            continue

        # Get closest point on geometry
        closest = geom.closestSegmentWithContext(point)
        if closest[0] < min_dist:
            min_dist = closest[0]
            snapped_point = closest[1]

    # Check if within tolerance (closestSegmentWithContext returns squared distance)
    import math
    if snapped_point and math.sqrt(min_dist) <= tolerance:
        return snapped_point

    return None


def find_nearest_vertex(
    point: QgsPointXY,
    vertices: Dict[Tuple[int, int], QgsPointXY],
    tolerance: float
) -> Optional[Tuple[int, int]]:
    """
    Find the nearest vertex key from a dictionary of vertices.

    Args:
        point: Query point
        vertices: Dict mapping keys to points
        tolerance: Maximum distance multiplier for acceptance

    Returns:
        Key of nearest vertex or None if none within tolerance
    """
    import math

    best_key = None
    best_dist_sq = float('inf')

    for key, pt in vertices.items():
        dx = pt.x() - point.x()
        dy = pt.y() - point.y()
        dist_sq = dx * dx + dy * dy

        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_key = key

    # Accept only within reasonable range
    if best_key and math.sqrt(best_dist_sq) <= tolerance * 3.0:
        return best_key

    return None


# =============================================================================
# DISTANCE CALCULATIONS
# =============================================================================

def points_equal(p1: QgsPointXY, p2: QgsPointXY, tolerance: float = 1e-9) -> bool:
    """
    Check if two points are equal within a tolerance.

    Args:
        p1: First point
        p2: Second point
        tolerance: Maximum coordinate difference

    Returns:
        True if points are equal within tolerance
    """
    return (
        abs(p1.x() - p2.x()) < tolerance and  # noqa: W504
        abs(p1.y() - p2.y()) < tolerance
    )


def point_distance(p1: QgsPointXY, p2: QgsPointXY) -> float:
    """
    Calculate Euclidean distance between two points.

    Args:
        p1: First point
        p2: Second point

    Returns:
        Distance between points
    """
    import math
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    return math.sqrt(dx * dx + dy * dy)


def point_distance_squared(p1: QgsPointXY, p2: QgsPointXY) -> float:
    """
    Calculate squared Euclidean distance between two points.

    More efficient than point_distance when only comparing distances.

    Args:
        p1: First point
        p2: Second point

    Returns:
        Squared distance between points
    """
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    return dx * dx + dy * dy


# =============================================================================
# LINE UTILITIES
# =============================================================================

def split_line_at_point(
    line_geom: QgsGeometry,
    split_point: QgsPointXY,
    tolerance: float
) -> Tuple[Optional[QgsGeometry], Optional[QgsGeometry]]:
    """
    Split a line geometry at a given point.

    Args:
        line_geom: Line geometry to split
        split_point: Point where to split
        tolerance: Snap tolerance for determining if point is on line

    Returns:
        Tuple of (first_part, second_part) or (None, None) if split fails
    """
    if line_geom is None or line_geom.isEmpty():
        return None, None

    # Check if multipart
    if line_geom.isMultipart():
        lines = line_geom.asMultiPolyline()
        if lines and len(lines) == 1:
            line_geom = QgsGeometry.fromPolylineXY(lines[0])
        else:
            return None, None

    line_points = line_geom.asPolyline()
    if not line_points or len(line_points) < 2:
        return None, None

    # For simple 2-vertex line
    if len(line_points) == 2:
        p0, p1 = QgsPointXY(line_points[0]), QgsPointXY(line_points[1])

        # Check if split point is too close to endpoints
        if (point_distance(split_point, p0) < tolerance or  # noqa: W504
                point_distance(split_point, p1) < tolerance):
            return None, None

        geom1 = QgsGeometry.fromPolylineXY([p0, split_point])
        geom2 = QgsGeometry.fromPolylineXY([split_point, p1])
        return geom1, geom2

    # For lines with more vertices, use QGIS split
    result, new_geoms, _ = line_geom.splitGeometry([split_point], False)

    if result != 0 or not new_geoms:
        return None, None

    return line_geom, new_geoms[0]


def merge_lines(geometries: List[QgsGeometry]) -> Optional[QgsGeometry]:
    """
    Merge multiple line geometries into one.

    Args:
        geometries: List of line geometries to merge

    Returns:
        Merged line geometry or None if merge fails
    """
    if not geometries:
        return None

    if len(geometries) == 1:
        return geometries[0]

    # Collect all points
    all_points = []
    for geom in geometries:
        pts = extract_line_vertices(geom)
        if all_points and pts:
            # Check if we need to reverse or skip duplicate endpoint
            if points_equal(all_points[-1], pts[0]):
                pts = pts[1:]
            elif points_equal(all_points[-1], pts[-1]):
                pts = list(reversed(pts))[1:]
        all_points.extend(pts)

    if len(all_points) < 2:
        return None

    return QgsGeometry.fromPolylineXY(all_points)


# =============================================================================
# LAYER GEOMETRY UTILITIES
# =============================================================================

def get_layer_extent_center(layer: QgsVectorLayer) -> Optional[QgsPointXY]:
    """
    Get the center point of a layer's extent.

    Args:
        layer: Vector layer

    Returns:
        Center point or None if layer is empty
    """
    if layer is None or not layer.isValid():
        return None

    try:
        extent = layer.extent()
        if extent.isEmpty():
            return None
        return extent.center()
    except Exception:
        return None


def calculate_geometry_length(geom: QgsGeometry) -> float:
    """
    Calculate the length of a geometry in map units.

    Map units are not metres in a projected CRS: Web Mercator inflates distance
    by 1/cos(latitude). For anything stored in a field or shown to the user, use
    :func:`fiberq.utils.measure.ground_length` instead.

    Args:
        geom: Geometry (typically line)

    Returns:
        Length in map units
    """
    if geom is None or geom.isEmpty():
        return 0.0

    try:
        return geom.length()
    except Exception:
        return 0.0
