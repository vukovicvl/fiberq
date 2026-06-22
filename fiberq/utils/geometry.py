"""
FiberQ v2 - Geometry Utilities Module

This module contains geometry utility functions for point manipulation,
snapping, distance calculations, and coordinate transformations.
"""

from typing import Optional, Tuple, List, Dict
from qgis.core import QgsPointXY, QgsGeometry, QgsVectorLayer

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
    if geom is None or geom.isEmpty():
        return None, None, []

    # Try simple polyline first
    line = geom.asPolyline()

    if not line:
        # Try multipart polyline
        multi = geom.asMultiPolyline()
        if multi and len(multi) > 0:
            line = multi[0]

    if not line or len(line) < 2:
        return None, None, []

    return (
        QgsPointXY(line[0]),
        QgsPointXY(line[-1]),
        [QgsPointXY(p) for p in line]
    )


def extract_line_vertices(geom: QgsGeometry) -> List[QgsPointXY]:
    """
    Extract all vertices from a line geometry.

    Args:
        geom: Line geometry

    Returns:
        List of QgsPointXY vertices
    """
    if geom is None or geom.isEmpty():
        return []

    line = geom.asPolyline()
    if line:
        return [QgsPointXY(p) for p in line]

    # Handle multipart
    multi = geom.asMultiPolyline()
    if multi:
        vertices = []
        for part in multi:
            vertices.extend([QgsPointXY(p) for p in part])
        return vertices

    return []


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
        abs(p1.x() - p2.x()) < tolerance and
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
        if (point_distance(split_point, p0) < tolerance or
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
    except Exception as e:
        return None


def calculate_geometry_length(geom: QgsGeometry) -> float:
    """
    Calculate the length of a geometry in map units.

    Args:
        geom: Geometry (typically line)

    Returns:
        Length in map units
    """
    if geom is None or geom.isEmpty():
        return 0.0

    try:
        return geom.length()
    except Exception as e:
        return 0.0
