"""
FiberQ v2 - Base Tool Classes and Common Imports

This module provides common imports and base functionality
for all map tools in the FiberQ plugin.

Phase 5.2: Added logging infrastructure
"""

import math

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
    QgsPointXY, QgsField, QgsWkbTypes, QgsPointLocator,
    QgsMarkerSymbol, QgsSvgMarkerSymbolLayer, QgsUnitTypes,
    QgsSingleSymbolRenderer, QgsSimpleMarkerSymbolLayer
)

# QGIS GUI imports
from qgis.gui import (
    QgsMapTool, QgsMapToolEmitPoint, QgsMapToolIdentify,
    QgsVertexMarker, QgsRubberBand, QgsSnapIndicator
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


def get_canonical_layer_name():
    """Get canonical_layer_name from the schema module."""
    from ..models.schema import canonical_layer_name
    return canonical_layer_name


# =============================================================================
# SNAPPING UTILITIES
# =============================================================================

#: Canonical layer names the placement tools snap to. Every lookup goes through
#: ``canonical_layer_name``, so a project still using the legacy Serbian names
#: (``Trasa``, ``Stubovi``, ``OKNA``, ``Kablovi_*``) snaps exactly the same. The
#: literal-name tests these tools used instead could not see them at all.
SNAP_NODE_LAYERS = ('Poles', 'Manholes')
SNAP_ROUTE_LAYERS = ('Route',)
SNAP_CABLE_LAYERS = ('Underground cables', 'Aerial cables')


def no_match():
    """An invalid ``QgsPointLocator.Match``: the "nothing was snapped" token.

    ``QgsSnapIndicator.setMatch()`` hides the indicator when handed one, so this
    doubles as the way to clear it.
    """
    return QgsPointLocator.Match()


def snap_match(point, layer=None, fid=-1, distance=0.0, on_edge=False, vertex_index=0):
    """Build a ``QgsPointLocator.Match`` for a point FiberQ's own snap found.

    QGIS's snapping hands the caller a real match from
    ``QgsMapMouseEvent.mapPointMatch()``. Giving the fallback the same type means
    one return value serves both paths, and ``QgsSnapIndicator`` can show either
    without the caller knowing which snap produced it.

    Args:
        point: the snapped position, as QgsPointXY.
        layer: the QgsVectorLayer it came from, or None.
        fid: the feature id it came from.
        distance: distance from the cursor in map units -- linear, not squared.
        on_edge: True for a point on a segment, False for a vertex.
        vertex_index: the vertex index, or -- for an edge -- the index of the
            vertex the segment starts at, which is what QGIS's own matches
            carry. The ``edgePoints`` a QGIS edge match also carries are left
            empty; ``QgsSnapIndicator`` does not read them (verified on 3.22
            through 4.2), so nothing here needs them.

    Returns:
        A valid QgsPointLocator.Match.
    """
    kind = QgsPointLocator.Type.Edge if on_edge else QgsPointLocator.Type.Vertex
    return QgsPointLocator.Match(kind, layer, fid, distance, QgsPointXY(point), vertex_index)


class PlacementSnapper:
    """The one snap shared by every FiberQ tool that places a point.

    With the magnet on, the snap is QGIS's own: ``event.snapPoint()`` picks the
    position and ``event.mapPointMatch()`` reports what it locked onto, so the
    user's tolerance, snapping mode and layer selection all apply -- which is
    the whole point, since the tools used to ignore the project's configuration
    entirely and each carried a private tolerance instead.

    With the magnet off -- still the default in a fresh project -- FiberQ falls
    back to its own scan. Dropping that would leave most users with no snap at
    all, so it stays, with its three defects fixed: linear distances, a vertex
    preferred over a point on a segment, and layers resolved by canonical name.

    The fallback deliberately keeps the same full pass over every candidate
    layer the tools have always done. Narrowing it is a separate change,
    measured on its own, and doing it here would hide where the gain came from.

    One instance per tool, built from the canvas alone: the tools that place
    elements, poles and joint closures are constructed without an ``iface``.
    """

    def __init__(self, canvas, point_layers=(), line_layers=(), pixels=20,
                 segments=True, extra_point_layers=()):
        """
        Args:
            canvas: the QgsMapCanvas the tool is working on.
            point_layers: canonical names of point layers to snap to.
            line_layers: canonical names of line layers to snap to.
            pixels: fallback tolerance in screen pixels; a callable is read on
                every event, so a tool can follow a user setting.
            segments: whether the fallback may land on a point along a segment,
                as well as on a vertex.
            extra_point_layers: lowercase substrings that also qualify a point
                layer, for layers outside the FiberQ schema (the joint-closure
                tool's infrastructure-cut markers).
        """
        self.canvas = canvas
        self.point_layers = tuple(point_layers)
        self.line_layers = tuple(line_layers)
        self.pixels = pixels
        self.segments = segments
        self.extra_point_layers = tuple(extra_point_layers)
        self.indicator = QgsSnapIndicator(canvas)

    # -- the tool-facing calls ------------------------------------------------

    def snap(self, event):
        """Snap one mouse event, and show the result on the indicator.

        Call it from both the move and the click handler: snapping the click
        itself is what stops a click with no preceding move from landing on
        wherever the cursor last hovered. Call it **once per event**, though --
        ``snapPoint()`` rewrites the event's own ``mapPoint()``, so a second call
        on the same event would read the first call's result as the cursor.

        Args:
            event: the QgsMapMouseEvent the tool was handed.

        Returns:
            Tuple of (QgsPointXY, QgsPointLocator.Match). The point is where the
            feature belongs: the snapped position when something was found, the
            raw cursor position otherwise. The match is invalid when nothing was
            snapped; callers needing the layer, feature id or vertex index read
            them off it. Do not store the match -- ``Match.layer()`` dangles once
            the layer is gone. Its ``point()`` is a copy and is safe to keep.
        """
        cursor = QgsPointXY(event.mapPoint())
        if self.qgis_snapping_on():
            # snapPoint() has to run first: mapPointMatch() is empty until it
            # has, and snapPoint() also rewrites the event's own mapPoint().
            snapped = QgsPointXY(event.snapPoint())
            match = event.mapPointMatch()
            self.show(match)
            if match.isValid():
                return snapped, match
            return cursor, match
        match = self._fallback(cursor)
        self.show(match)
        if match.isValid():
            return QgsPointXY(match.point()), match
        return cursor, match

    def show(self, match):
        """Put the indicator on ``match``, or clear it if the match is invalid."""
        try:
            self.indicator.setMatch(match)
        except (AttributeError, RuntimeError) as exc:
            # The canvas outlives the tool, so this only fires on teardown.
            logger.debug(f"snap indicator could not be updated: {exc}")

    def clear(self):
        """Hide the indicator: for deactivate(), ESC and right-click.

        Every adopting tool must call this, or the indicator is left on screen
        pointing at a vertex the next tool knows nothing about.
        """
        self.show(no_match())

    def tolerance(self):
        """The fallback's snap tolerance, in map units."""
        pixels = self.pixels() if callable(self.pixels) else self.pixels
        return self.canvas.mapUnitsPerPixel() * pixels

    def qgis_snapping_on(self):
        """True when the user has the magnet on for this canvas.

        Read off the canvas' own snapping utils rather than the project's
        config: that is the configuration ``snapPoint()`` will actually use, and
        the running application keeps the two in step.
        """
        try:
            utils = self.canvas.snappingUtils()
        except (AttributeError, RuntimeError) as exc:
            logger.debug(f"canvas exposes no snapping utils: {exc}")
            return False
        if utils is None:
            return False
        return bool(utils.config().enabled())

    # -- FiberQ's own snap ----------------------------------------------------

    def _candidate_layers(self):
        """Yield (layer, is_line, name) for every layer this tool snaps to.

        The name travels with the layer because the caller's error handler needs
        it *after* the wrapper may already be gone, and asking the dead wrapper
        for it there would raise the very error being handled.
        """
        canonical_layer_name = get_canonical_layer_name()
        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            if not layer.isValid():
                continue
            name = layer.name() or ''
            canonical = canonical_layer_name(name)
            geometry_type = layer.geometryType()
            if geometry_type == QgsWkbTypes.GeometryType.PointGeometry:
                if canonical in self.point_layers:
                    yield layer, False, name
                elif self._is_extra_point_layer(name):
                    yield layer, False, name
            elif geometry_type == QgsWkbTypes.GeometryType.LineGeometry:
                if canonical in self.line_layers:
                    yield layer, True, name

    def _is_extra_point_layer(self, name):
        """Whether ``name`` matches one of the non-schema point layers."""
        lowered = name.lower()
        return any(hint in lowered for hint in self.extra_point_layers)

    def _fallback(self, point):
        """FiberQ's own snap: a vertex if one is in reach, else a segment.

        Both ``closestVertexWithContext`` and ``closestSegmentWithContext``
        return a **squared** distance. The tools these replace compared that
        against a linear tolerance, which went wrong twice over: a segment was
        only reachable within ``sqrt(10 / mapUnitsPerPixel)`` pixels rather than
        the 10 the tolerance reads as, and a squared segment distance was
        written into the same variable as a linear node distance, so a nearby
        line beat a nearer node. Every distance here is linear.

        Returns:
            A QgsPointLocator.Match, invalid when nothing is within tolerance.
        """
        tolerance = self.tolerance()
        best_vertex = None
        best_edge = None

        for layer, is_line, name in self._candidate_layers():
            try:
                features = layer.getFeatures()
            except RuntimeError as exc:
                # A layer pulled out from under a live mouse move. One bad layer
                # must not take the tool down with it -- which is why the name
                # comes from the loop and not from the wrapper that just died.
                logger.debug(f"snap skipped layer {name!r}: {exc}")
                continue
            for feature in features:
                geometry = feature.geometry()
                if geometry is None:
                    continue
                if geometry.isEmpty():
                    continue
                fid = feature.id()

                squared, index = geometry.closestVertexWithContext(point)
                if squared >= 0:
                    distance = math.sqrt(squared)
                    if best_vertex is None or distance < best_vertex[0]:
                        vertex = QgsPointXY(geometry.vertexAt(index))
                        best_vertex = (distance, vertex, layer, fid, index)

                if not is_line:
                    continue
                if not self.segments:
                    continue
                squared, projected, after, _side = geometry.closestSegmentWithContext(point)
                if squared >= 0:
                    distance = math.sqrt(squared)
                    if best_edge is None or distance < best_edge[0]:
                        # ``after`` is the vertex *ending* the segment, while an
                        # edge match records the one starting it -- measured
                        # against QgsPointLocator.nearestEdge() on 3.22, 3.44 and
                        # 4.2, which all report after - 1 for the same hit.
                        best_edge = (distance, QgsPointXY(projected), layer, fid, after - 1)

        for best, on_edge in ((best_vertex, False), (best_edge, True)):
            if best is None:
                continue
            if best[0] > tolerance:
                continue
            try:
                return snap_match(best[1], layer=best[2], fid=best[3],
                                  distance=best[0], on_edge=on_edge, vertex_index=best[4])
            except RuntimeError as exc:
                # ``Match`` keeps the layer pointer, so building one needs the
                # layer still alive -- and the winner was chosen earlier in the
                # scan. Drop that candidate rather than throw out of a mouse
                # move: the next move rescans anyway.
                logger.debug(f"snap dropped a candidate whose layer went away: {exc}")
                continue
        return no_match()


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
    'QgsPointXY', 'QgsField', 'QgsWkbTypes', 'QgsPointLocator',
    'QgsMarkerSymbol', 'QgsSvgMarkerSymbolLayer', 'QgsUnitTypes',
    'QgsSingleSymbolRenderer', 'QgsSimpleMarkerSymbolLayer',

    # QGIS GUI
    'QgsMapTool', 'QgsMapToolEmitPoint', 'QgsMapToolIdentify',
    'QgsVertexMarker', 'QgsRubberBand', 'QgsSnapIndicator',

    # Helper functions
    'get_element_defs', 'get_joint_closure_def', 'get_route_type_options',
    'get_canonical_layer_name',

    # Snapping
    'PlacementSnapper', 'snap_match', 'no_match',
    'SNAP_NODE_LAYERS', 'SNAP_ROUTE_LAYERS', 'SNAP_CABLE_LAYERS',

    # Base classes
    'FiberQMapTool', 'FiberQMapToolEmitPoint',
]
