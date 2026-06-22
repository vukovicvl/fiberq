"""
FiberQ v2 - Routing Utilities Module

This module contains path finding algorithms for routing cables
and other network elements across the route network.

The algorithms support:
- BFS-based shortest path finding on network graphs
- Virtual merging of disconnected route segments
- Handling of both simple and multi-part geometries
"""

from typing import Optional, List, Dict, Tuple, Set
from collections import defaultdict, deque

from qgis.core import QgsPointXY, QgsGeometry, QgsVectorLayer

from .geometry import (
    fuzzy_key, round_key, get_first_last_points,
    find_nearest_vertex
)

# Phase 5.2: Logging
from .logger import get_logger
logger = get_logger(__name__)


# =============================================================================
# NETWORK GRAPH BUILDING
# =============================================================================

def build_network_graph(
    layer: QgsVectorLayer,
    tolerance: float
) -> Tuple[Dict[Tuple[int, int], QgsPointXY], List[Tuple[Tuple[int, int], Tuple[int, int]]]]:
    """
    Build a network graph from a route layer.

    Extracts all vertices and segments from the layer, using fuzzy
    coordinate keys to handle near-coincident vertices.

    Args:
        layer: Route layer to build graph from
        tolerance: Tolerance for vertex matching

    Returns:
        Tuple of:
        - Dict mapping coordinate keys to actual points
        - List of segments as (start_key, end_key) tuples
    """
    key_to_point: Dict[Tuple[int, int], QgsPointXY] = {}
    segments: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            continue

        # Handle simple polyline
        line = geom.asPolyline()
        if line:
            _process_line_part(line, tolerance, key_to_point, segments)
            continue

        # Handle multipart polyline
        multiline = geom.asMultiPolyline()
        if multiline:
            for part in multiline:
                if len(part) >= 2:
                    _process_line_part(part, tolerance, key_to_point, segments)

    return key_to_point, segments


def _process_line_part(
    line_points: List,
    tolerance: float,
    key_to_point: Dict[Tuple[int, int], QgsPointXY],
    segments: List[Tuple[Tuple[int, int], Tuple[int, int]]]
) -> None:
    """
    Process a single line part, extracting vertices and segments.

    Args:
        line_points: List of point coordinates
        tolerance: Tolerance for key generation
        key_to_point: Dict to update with vertices
        segments: List to update with segments
    """
    if len(line_points) < 2:
        return

    # Add all vertices
    for i, pt in enumerate(line_points):
        point = QgsPointXY(pt)
        key = fuzzy_key(point, tolerance)
        if key not in key_to_point:
            key_to_point[key] = point

    # Add segments
    for i in range(len(line_points) - 1):
        u_key = fuzzy_key(QgsPointXY(line_points[i]), tolerance)
        v_key = fuzzy_key(QgsPointXY(line_points[i + 1]), tolerance)
        if u_key != v_key:
            segments.append((u_key, v_key))


def build_adjacency_list(
    segments: List[Tuple[Tuple[int, int], Tuple[int, int]]]
) -> Dict[Tuple[int, int], List[Tuple[int, int]]]:
    """
    Build adjacency list from segment list.

    Creates bidirectional edges for undirected graph traversal.

    Args:
        segments: List of (start_key, end_key) tuples

    Returns:
        Dict mapping each vertex key to list of connected vertex keys
    """
    adj: Dict[Tuple[int, int], List[Tuple[int, int]]] = defaultdict(list)

    for u, v in segments:
        adj[u].append(v)
        adj[v].append(u)

    return adj


# =============================================================================
# PATH FINDING ALGORITHMS
# =============================================================================

def find_path_bfs(
    adj: Dict[Tuple[int, int], List[Tuple[int, int]]],
    start_key: Tuple[int, int],
    end_key: Tuple[int, int]
) -> Optional[List[Tuple[int, int]]]:
    """
    Find shortest path using Breadth-First Search.

    Args:
        adj: Adjacency list mapping vertex keys to neighbors
        start_key: Starting vertex key
        end_key: Target vertex key

    Returns:
        List of vertex keys representing path, or None if no path exists
    """
    if start_key == end_key:
        return [start_key]

    # BFS
    parent: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start_key: None}
    queue = deque([start_key])

    while queue:
        current = queue.popleft()

        if current == end_key:
            break

        for neighbor in adj.get(current, []):
            if neighbor not in parent:
                parent[neighbor] = current
                queue.append(neighbor)

    # Check if we reached the end
    if end_key not in parent:
        return None

    # Reconstruct path
    path_keys = []
    current = end_key
    while current is not None:
        path_keys.append(current)
        current = parent[current]

    path_keys.reverse()
    return path_keys


def build_path_across_network(
    layer: QgsVectorLayer,
    start_pt: QgsPointXY,
    end_pt: QgsPointXY,
    tolerance: float
) -> Optional[List[QgsPointXY]]:
    """
    Find a path across the network including all intermediate vertices.

    Routes through ALL vertices (including breakpoints) without
    physically merging features. Uses BFS for shortest path finding.

    Args:
        layer: Route layer to path through
        start_pt: Starting point
        end_pt: Ending point
        tolerance: Tolerance for vertex matching (map units)

    Returns:
        List of QgsPointXY representing the path, or None if no path exists
    """
    try:
        # Build network graph
        key_to_point, segments = build_network_graph(layer, tolerance)

        if not key_to_point or not segments:
            return None

        # Find nearest vertices to start and end
        start_key = find_nearest_vertex(start_pt, key_to_point, tolerance)
        end_key = find_nearest_vertex(end_pt, key_to_point, tolerance)

        if start_key is None or end_key is None:
            return None

        # Build adjacency list and find path
        adj = build_adjacency_list(segments)
        path_keys = find_path_bfs(adj, start_key, end_key)

        if path_keys is None:
            return None

        # Convert keys back to points
        return [key_to_point[k] for k in path_keys]

    except Exception as e:
        return None


def build_path_across_joined_routes(
    layer: QgsVectorLayer,
    start_pt: QgsPointXY,
    end_pt: QgsPointXY,
    tolerance: float
) -> Optional[List[QgsPointXY]]:
    """
    Find a path across joined routes, treating each feature as an edge.

    This algorithm works at the feature level, treating each route
    feature as a single edge in the graph. It preserves the full
    geometry of each feature in the resulting path.

    Args:
        layer: Route layer to path through
        start_pt: Starting point
        end_pt: Ending point
        tolerance: Tolerance for vertex matching (map units)

    Returns:
        List of QgsPointXY representing the path, or None if no path exists
    """
    try:
        # Build feature-level graph
        node_to_edges: Dict[Tuple[int, int], List[Tuple[int, bool]]] = {}
        edge_to_points: Dict[int, List[QgsPointXY]] = {}
        endpoints: Dict[int, Tuple[QgsPointXY, QgsPointXY]] = {}

        for feature in layer.getFeatures():
            p_first, p_last, pts = get_first_last_points(feature.geometry())
            if not pts:
                continue

            fid = feature.id()
            edge_to_points[fid] = pts
            endpoints[fid] = (p_first, p_last)

            k1 = round_key(p_first, tolerance)
            k2 = round_key(p_last, tolerance)

            node_to_edges.setdefault(k1, []).append((fid, False))
            node_to_edges.setdefault(k2, []).append((fid, True))

        # Find start and end nodes
        start_key = round_key(start_pt, tolerance)
        end_key = round_key(end_pt, tolerance)

        if start_key not in node_to_edges or end_key not in node_to_edges:
            return None

        # BFS at feature level
        queue = deque([start_key])
        parent: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start_key: None}
        via_edge: Dict[Tuple[int, int], Optional[int]] = {start_key: None}

        while queue:
            u = queue.popleft()

            if u == end_key:
                break

            for (fid, _) in node_to_edges.get(u, []):
                p0, p1 = endpoints[fid]
                k0 = round_key(p0, tolerance)
                k1 = round_key(p1, tolerance)
                v = k1 if u == k0 else k0

                if v not in parent:
                    parent[v] = u
                    via_edge[v] = fid
                    queue.append(v)

        if end_key not in parent:
            return None

        # Reconstruct edge sequence
        edge_order = []
        v = end_key
        while via_edge[v] is not None:
            edge_order.append(via_edge[v])
            v = parent[v]
        edge_order.reverse()

        # Build path from edges
        path_pts: List[QgsPointXY] = []
        current_node = start_key

        for fid in edge_order:
            pts = edge_to_points[fid]
            p_first, p_last = endpoints[fid]
            k_first = round_key(p_first, tolerance)
            k_last = round_key(p_last, tolerance)

            # Determine direction
            if k_first == current_node:
                seq = pts
                current_node = k_last
            else:
                seq = list(reversed(pts))
                current_node = k_first

            # Append points, avoiding duplicates at joins
            if not path_pts:
                path_pts.extend(seq)
            else:
                if (path_pts[-1].x() == seq[0].x() and
                    path_pts[-1].y() == seq[0].y()):
                    path_pts.extend(seq[1:])
                else:
                    path_pts.extend(seq)

        # Verify we reached the end
        if round_key(path_pts[-1], tolerance) != end_key:
            return None

        return path_pts

    except Exception as e:
        return None


# =============================================================================
# ROUTING HELPER FUNCTIONS
# =============================================================================

def find_route_between_points(
    layer: QgsVectorLayer,
    start_pt: QgsPointXY,
    end_pt: QgsPointXY,
    tolerance: float
) -> Optional[List[QgsPointXY]]:
    """
    Find a route between two points, trying multiple algorithms.

    First attempts the detailed vertex-level routing, then falls
    back to feature-level routing if that fails.

    Args:
        layer: Route layer to path through
        start_pt: Starting point
        end_pt: Ending point
        tolerance: Tolerance for vertex matching (map units)

    Returns:
        List of QgsPointXY representing the path, or None if no path exists
    """
    # Try vertex-level routing first
    path = build_path_across_network(layer, start_pt, end_pt, tolerance)

    if path is None:
        # Fall back to feature-level routing
        path = build_path_across_joined_routes(layer, start_pt, end_pt, tolerance)

    return path


def get_network_connectivity(
    layer: QgsVectorLayer,
    tolerance: float
) -> Dict[Tuple[int, int], Set[int]]:
    """
    Analyze network connectivity, returning connected components.

    Args:
        layer: Route layer to analyze
        tolerance: Tolerance for vertex matching

    Returns:
        Dict mapping vertex keys to set of feature IDs connected at that vertex
    """
    connectivity: Dict[Tuple[int, int], Set[int]] = defaultdict(set)

    for feature in layer.getFeatures():
        p_first, p_last, _ = get_first_last_points(feature.geometry())
        if p_first is None:
            continue

        fid = feature.id()
        k1 = round_key(p_first, tolerance)
        k2 = round_key(p_last, tolerance)

        connectivity[k1].add(fid)
        connectivity[k2].add(fid)

    return connectivity


def find_endpoints_on_network(
    layer: QgsVectorLayer,
    tolerance: float
) -> List[QgsPointXY]:
    """
    Find dead-end vertices in the network (connected to only one edge).

    Args:
        layer: Route layer to analyze
        tolerance: Tolerance for vertex matching

    Returns:
        List of endpoint QgsPointXY coordinates
    """
    connectivity = get_network_connectivity(layer, tolerance)

    endpoints = []

    # Build key to point mapping
    key_to_point: Dict[Tuple[int, int], QgsPointXY] = {}
    for feature in layer.getFeatures():
        p_first, p_last, _ = get_first_last_points(feature.geometry())
        if p_first:
            k1 = round_key(p_first, tolerance)
            k2 = round_key(p_last, tolerance)
            key_to_point[k1] = p_first
            key_to_point[k2] = p_last

    # Find vertices connected to only one feature
    for key, fids in connectivity.items():
        if len(fids) == 1 and key in key_to_point:
            endpoints.append(key_to_point[key])

    return endpoints
