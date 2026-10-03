"""
FiberQ v2 - Point Placement Tool

Map tool for placing poles with snap functionality.
Phase 2.1: Extracted from extracted_classes.py
"""

from qgis.PyQt import sip

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsFeature, QgsGeometry, QgsSettings
from qgis.gui import QgsMapToolEmitPoint

from .base import PlacementSnapper, SNAP_ROUTE_LAYERS

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


def snap_pixels():
    """The user's snap distance in pixels, from the FiberQ settings dialog."""
    try:
        return int(QgsSettings().value("FiberQ/default_snap_distance", "20"))
    except (TypeError, ValueError) as exc:
        logger.debug(f"unreadable FiberQ/default_snap_distance, using 20 px: {exc}")
        return 20


class PointTool(QgsMapToolEmitPoint):
    """Map tool for placing poles, snapped to the route."""

    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.snapper = PlacementSnapper(
            canvas,
            line_layers=SNAP_ROUTE_LAYERS,
            pixels=snap_pixels,
        )
        # The benchmark harness reads ``snap_marker.isVisible()`` as the proof a
        # move snapped; the indicator's visibility tracks the match, so the
        # alias keeps that post-condition true and meaningful.
        self.snap_marker = self.snapper.indicator

    def canvasMoveEvent(self, event):
        """Show where the pole will land."""
        self.snapper.snap(event)

    def keyPressEvent(self, event):
        """ESC cancels the tool. The pole tool had no key handler at all."""
        if event.key() == Qt.Key.Key_Escape:
            self.snapper.clear()
            try:
                self.canvas.unsetMapTool(self)
            except (AttributeError, RuntimeError) as exc:
                # Only reachable with the canvas already gone.
                logger.debug(f"could not unset the pole tool: {exc}")

    def deactivate(self):
        """Clear the indicator, so it does not outlive the tool."""
        self.snapper.clear()
        super().deactivate()

    def canvasReleaseEvent(self, event):
        # Right click – cancel command without adding pole
        if event.button() == Qt.MouseButton.RightButton:
            self.snapper.clear()
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in PointTool.canvasReleaseEvent: {e}")
            return

        # Anything that's not left click – ignore
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            QMessageBox.warning(None, "FiberQ", "Layer not found or invalid!")
            return

        final_point, _match = self.snapper.snap(event)

        feature = QgsFeature(self.layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(final_point))
        feature.setAttribute("tip", "POLE")
        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(feature)
        except Exception as e:
            logger.debug(f"Could not set feature uuid on pole: {e}")
        self.layer.startEditing()
        self.layer.addFeature(feature)
        self.layer.commitChanges()
        self.layer.triggerRepaint()
        self.snapper.clear()

        # Record for undo (v1.2 — Feature 2)
        try:
            if hasattr(self, 'plugin') and self.plugin and hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                self.plugin.undo_manager.record_add(self.layer, feature)
        except Exception as e:
            logger.debug(f"Could not record undo for added pole (plugin ref may be missing): {e}")


__all__ = ['PointTool']
