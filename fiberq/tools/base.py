"""
FiberQ v2 - Base Tool Classes and Common Imports

This module provides common imports and base functionality
for all map tools in the FiberQ plugin.

Phase 5.2: Added logging infrastructure
"""

# Qt imports
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QDialogButtonBox, QFormLayout, QInputDialog, QScrollArea, QWidget
)

# QGIS core imports
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsWkbTypes,
    QgsMarkerSymbol, QgsSvgMarkerSymbolLayer, QgsUnitTypes,
    QgsSingleSymbolRenderer, QgsSimpleMarkerSymbolLayer
)

# QGIS GUI imports
from qgis.gui import (
    QgsMapTool, QgsMapToolEmitPoint, QgsMapToolIdentify,
    QgsVertexMarker, QgsRubberBand
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)

# Plugin imports - these need to be imported when the tool is instantiated
# to avoid circular imports
def get_element_defs():
    """Get ELEMENT_DEFS from models module."""
    from ..models.element_defs import ELEMENT_DEFS
    return ELEMENT_DEFS

def get_joint_closure_def():
    """Get NASTAVAK_DEF (joint closure definition) from models module."""
    from ..models.element_defs import NASTAVAK_DEF
    return NASTAVAK_DEF

def get_route_type_options():
    """Get route type options from constants module."""
    from ..utils.constants import TRASA_TYPE_OPTIONS, TRASA_TYPE_LABELS, TRASA_LABEL_TO_CODE
    return TRASA_TYPE_OPTIONS, TRASA_TYPE_LABELS, TRASA_LABEL_TO_CODE


# =============================================================================
# LAYER FINDING UTILITIES
# =============================================================================

def find_route_layer():
    """Find the Route layer in the project."""
    for lyr in QgsProject.instance().mapLayers().values():
        try:
            if (isinstance(lyr, QgsVectorLayer) and
                lyr.geometryType() == QgsWkbTypes.LineGeometry and
                lyr.name() in ('Route', 'Trasa')):
                return lyr
        except Exception as e:
            logger.debug(f"Error in find_route_layer: {e}")
    return None


def find_cable_layers():
    """Find all cable layers in the project."""
    cable_names = {
        'Kablovi_podzemni', 'Kablovi_vazdusni',
        'Underground cables', 'Aerial cables'
    }
    layers = []
    for lyr in QgsProject.instance().mapLayers().values():
        try:
            if (isinstance(lyr, QgsVectorLayer) and
                lyr.geometryType() == QgsWkbTypes.LineGeometry and
                lyr.name() in cable_names):
                layers.append(lyr)
        except Exception as e:
            logger.debug(f"Error in find_cable_layers: {e}")
    return layers


def find_node_layers():
    """Find pole and manhole layers in the project."""
    node_names = {'Poles', 'Stubovi', 'OKNA', 'Manholes'}
    layers = []
    for lyr in QgsProject.instance().mapLayers().values():
        try:
            if (isinstance(lyr, QgsVectorLayer) and
                lyr.geometryType() == QgsWkbTypes.PointGeometry and
                lyr.name() in node_names):
                layers.append(lyr)
        except Exception as e:
            logger.debug(f"Error in find_node_layers: {e}")
    return layers


def find_element_layers():
    """Find all element layers (ODF, OTB, TB, etc.) in the project."""
    try:
        element_defs = get_element_defs()
        element_names = {d.get('name') for d in element_defs if d.get('name')}
    except Exception as e:
        element_names = set()

    # Add joint closure
    try:
        jc_def = get_joint_closure_def()
        element_names.add(jc_def.get('name', 'Joint Closures'))
        element_names.add('Nastavci')  # Legacy name
    except Exception as e:
        logger.debug(f"Error in find_element_layers: {e}")

    layers = []
    for lyr in QgsProject.instance().mapLayers().values():
        try:
            if (isinstance(lyr, QgsVectorLayer) and
                lyr.geometryType() == QgsWkbTypes.PointGeometry and
                lyr.name() in element_names):
                layers.append(lyr)
        except Exception as e:
            logger.debug(f"Error in find_element_layers: {e}")
    return layers


def get_snap_layers():
    """Get all layers that should be used for snapping (nodes, routes, elements)."""
    layers = []
    layers.extend(find_node_layers())
    layers.extend(find_element_layers())

    route_layer = find_route_layer()
    if route_layer:
        layers.append(route_layer)

    return layers


# =============================================================================
# SNAPPING UTILITIES
# =============================================================================

def snap_to_point_layers(point, layers, tolerance):
    """
    Snap a point to the nearest point in a list of point layers.

    Args:
        point: QgsPointXY to snap
        layers: List of QgsVectorLayer (point geometry)
        tolerance: Maximum snap distance

    Returns:
        Tuple of (snapped_point, min_distance) or (None, None) if no snap
    """
    min_dist = None
    snapped_point = None

    for layer in layers:
        if layer.geometryType() != QgsWkbTypes.PointGeometry:
            continue

        for feature in layer.getFeatures():
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                continue
            try:
                pt = geom.asPoint()
                d = QgsPointXY(point).distance(QgsPointXY(pt))
                if min_dist is None or d < min_dist:
                    min_dist = d
                    snapped_point = QgsPointXY(pt)
            except Exception as e:
                continue

    if snapped_point and min_dist is not None and min_dist <= tolerance:
        return snapped_point, min_dist
    return None, None


def snap_to_line_layer(point, layer, tolerance):
    """
    Snap a point to the nearest position on a line layer.

    Args:
        point: QgsPointXY to snap
        layer: QgsVectorLayer (line geometry)
        tolerance: Maximum snap distance

    Returns:
        Tuple of (snapped_point, feature, segment_index, distance) or (None, None, None, None)
    """
    if layer.geometryType() != QgsWkbTypes.LineGeometry:
        return None, None, None, None

    min_dist = None
    snapped_point = None
    min_feat = None
    min_seg_idx = None

    for feat in layer.getFeatures():
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            continue

        dist, snap, vertex_after, seg_idx = geom.closestSegmentWithContext(point)
        if min_dist is None or dist < min_dist:
            min_dist = dist
            snapped_point = snap
            min_feat = feat
            min_seg_idx = seg_idx

    if snapped_point and min_dist is not None and min_dist <= tolerance:
        return snapped_point, min_feat, min_seg_idx, min_dist
    return None, None, None, None


def snap_to_line_vertices(point, layer, tolerance):
    """
    Snap to vertices and segment midpoints of a line layer.

    Args:
        point: QgsPointXY to snap
        layer: QgsVectorLayer (line geometry)
        tolerance: Maximum snap distance

    Returns:
        Tuple of (snapped_point, min_distance) or (None, None)
    """
    if layer.geometryType() != QgsWkbTypes.LineGeometry:
        return None, None

    min_dist = None
    snapped_point = None

    for feat in layer.getFeatures():
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            continue

        # Get line parts
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
        else:
            lines = [geom.asPolyline()]

        for line in lines:
            if not line:
                continue

            # Check all vertices
            for pt in line:
                d = QgsPointXY(point).distance(QgsPointXY(pt))
                if min_dist is None or d < min_dist:
                    min_dist = d
                    snapped_point = QgsPointXY(pt)

            # Check segment midpoints
            for i in range(len(line) - 1):
                mid = QgsPointXY(
                    (line[i].x() + line[i + 1].x()) / 2.0,
                    (line[i].y() + line[i + 1].y()) / 2.0
                )
                d = QgsPointXY(point).distance(mid)
                if min_dist is None or d < min_dist:
                    min_dist = d
                    snapped_point = mid

    if snapped_point and min_dist is not None and min_dist <= tolerance:
        return snapped_point, min_dist
    return None, None


# =============================================================================
# TOOL BASE CLASSES
# =============================================================================

class FiberQMapTool(QgsMapTool):
    """Base class for FiberQ map tools with common functionality."""

    def __init__(self, canvas, iface=None, plugin=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.plugin = plugin

    def get_map_units_per_pixel(self):
        """Get the current map units per pixel for tolerance calculations."""
        return self.canvas.mapUnitsPerPixel()

    def get_tolerance(self, pixels=10):
        """Get snap tolerance in map units."""
        return self.get_map_units_per_pixel() * pixels

    def show_info(self, title, message):
        """Show an information message box."""
        QMessageBox.information(
            self.iface.mainWindow() if self.iface else None,
            title, message
        )

    def show_warning(self, title, message):
        """Show a warning message box."""
        QMessageBox.warning(
            self.iface.mainWindow() if self.iface else None,
            title, message
        )

    def push_message(self, title, message, level='info'):
        """Push a message to the QGIS message bar."""
        if self.iface:
            if level == 'info':
                self.iface.messageBar().pushInfo(title, message)
            elif level == 'warning':
                self.iface.messageBar().pushWarning(title, message)
            elif level == 'success':
                self.iface.messageBar().pushSuccess(title, message)


class FiberQMapToolEmitPoint(QgsMapToolEmitPoint):
    """Base class for FiberQ point-emitting map tools."""

    def __init__(self, canvas, iface=None, plugin=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.plugin = plugin

    def get_map_units_per_pixel(self):
        """Get the current map units per pixel for tolerance calculations."""
        return self.canvas.mapUnitsPerPixel()

    def get_tolerance(self, pixels=10):
        """Get snap tolerance in map units."""
        return self.get_map_units_per_pixel() * pixels

    def show_info(self, title, message):
        """Show an information message box."""
        QMessageBox.information(
            self.iface.mainWindow() if self.iface else None,
            title, message
        )

    def show_warning(self, title, message):
        """Show a warning message box."""
        QMessageBox.warning(
            self.iface.mainWindow() if self.iface else None,
            title, message
        )


# Export commonly used items
__all__ = [
    # Qt
    'Qt', 'QVariant', 'QColor',
    'QMessageBox', 'QDialog', 'QVBoxLayout', 'QHBoxLayout', 'QLabel',
    'QLineEdit', 'QPushButton', 'QComboBox', 'QSpinBox', 'QDoubleSpinBox',
    'QDialogButtonBox', 'QFormLayout', 'QInputDialog', 'QScrollArea', 'QWidget',

    # QGIS Core
    'QgsProject', 'QgsVectorLayer', 'QgsFeature', 'QgsGeometry',
    'QgsPointXY', 'QgsField', 'QgsWkbTypes',
    'QgsMarkerSymbol', 'QgsSvgMarkerSymbolLayer', 'QgsUnitTypes',
    'QgsSingleSymbolRenderer', 'QgsSimpleMarkerSymbolLayer',

    # QGIS GUI
    'QgsMapTool', 'QgsMapToolEmitPoint', 'QgsMapToolIdentify',
    'QgsVertexMarker', 'QgsRubberBand',

    # Helper functions
    'get_element_defs', 'get_joint_closure_def', 'get_route_type_options',
    'find_route_layer', 'find_cable_layers', 'find_node_layers',
    'find_element_layers', 'get_snap_layers',
    'snap_to_point_layers', 'snap_to_line_layer', 'snap_to_line_vertices',

    # Base classes
    'FiberQMapTool', 'FiberQMapToolEmitPoint',
]
