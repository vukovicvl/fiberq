"""
FiberQ v2 - Geometry Utilities Module

This module contains geometry utility functions for point manipulation,
snapping, distance calculations, and coordinate transformations.
"""

import math
from typing import Optional, Tuple, List, Dict
from qgis.core import QgsPointXY, QgsGeometry, QgsVectorLayer, QgsWkbTypes

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
    it is true for a one-part MultiLineString, which is what a GeoPackage
    column gives every ordinary route.
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return 0
    if geom.type() != QgsWkbTypes.GeometryType.LineGeometry:
        return 0
    stored = geom.constGet()
    if stored is None:
        return 0
    return stored.partCount()


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
