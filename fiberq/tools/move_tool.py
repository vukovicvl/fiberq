"""
FiberQ v2 - Move Feature Tool

Map tool for moving features with rubber band preview.
Phase 2.1: Extracted from extracted_classes.py
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QCursor

from qgis.core import QgsVectorLayer, QgsGeometry, QgsWkbTypes
from qgis.gui import QgsMapTool, QgsRubberBand, QgsMapToolIdentify

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class MoveFeatureTool(QgsMapTool):
    """Select a feature by click, preview translation with a rubber band,
    left-click to place; right-click to cancel."""

    def __init__(self, iface):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.layer = None
        self.orig_feat = None
        self.orig_geom = None
        self.anchor = None
        self.rb = None
        self.dragging = False
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

    def deactivate(self):
        self._clear()
        super().deactivate()

    def _clear(self):
        try:
            if self.rb:
                self.rb.reset(QgsWkbTypes.PolygonGeometry)
                self.canvas.scene().removeItem(self.rb)
        except Exception as e:
            logger.debug(f"Error in MoveFeatureTool._clear: {e}")
        self.rb = None
        self.orig_feat = None
        self.orig_geom = None
        self.anchor = None
        self.dragging = False

    def canvasPressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            # Cancel
            self._clear()
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in MoveFeatureTool.canvasPressEvent: {e}")
            self.iface.messageBar().pushInfo("Moving", "Command aborted (ESC or right click).")
            return

        if self.dragging:
            # Confirm placement
            self._apply_move(e.mapPoint())
            return

        # Identify topmost feature
        ident = QgsMapToolIdentify(self.canvas)
        res = ident.identify(e.pos().x(), e.pos().y(), ident.TopDownAll, ident.VectorLayer)
        if not res:
            self.iface.messageBar().pushInfo("Moving", "No element at this position.")
            return

        hit = res[0]
        self.layer = hit.mLayer
        f = hit.mFeature
        if not isinstance(self.layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning("Moving", "Layer is not vector.")
            return

        self.orig_feat = f
        self.orig_geom = QgsGeometry(f.geometry())
        self.anchor = e.mapPoint()

        # Rubber band
        try:
            self.rb = QgsRubberBand(self.canvas, self.layer.geometryType())
            self.rb.setWidth(2)
            self.rb.setColor(QColor(59, 130, 246, 100))  # blue-ish, semi
        except Exception as e:
            self.rb = None

        self.dragging = True
        self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

    def keyPressEvent(self, e):
        try:
            if e.key() == Qt.Key.Key_Escape:
                self._clear()
                try:
                    self.canvas.unsetMapTool(self)
                except Exception as e:
                    logger.debug(f"Error in MoveFeatureTool.keyPressEvent: {e}")
                self.iface.messageBar().pushInfo("Moving", "Command cancelled (ESC).")
        except Exception as e:
            logger.debug(f"Error in MoveFeatureTool.keyPressEvent: {e}")

    def canvasMoveEvent(self, e):
        if not self.dragging or not self.orig_geom:
            return
        p = e.mapPoint()
        dx = p.x() - self.anchor.x()
        dy = p.y() - self.anchor.y()
        geom = QgsGeometry(self.orig_geom)
        try:
            geom.translate(dx, dy)
        except Exception as e:
            # Fallback manual translate
            try:
                geom = QgsGeometry.fromWkt(self.orig_geom.asWkt())
                geom.translate(dx, dy)
            except Exception as e:
                return
        if self.rb:
            try:
                self.rb.setToGeometry(geom, self.layer)
            except Exception as e:
                logger.debug(f"Error in MoveFeatureTool.canvasMoveEvent: {e}")

    def _apply_move(self, p):
        dx = p.x() - self.anchor.x()
        dy = p.y() - self.anchor.y()
        new_geom = QgsGeometry(self.orig_geom)
        try:
            new_geom.translate(dx, dy)
        except Exception as e:
            logger.debug(f"Error in MoveFeatureTool._apply_move: {e}")
        lyr = self.layer
        if not lyr.isEditable():
            lyr.startEditing()
        ok = lyr.changeGeometry(self.orig_feat.id(), new_geom)
        if ok:
            lyr.triggerRepaint()
            self.iface.messageBar().pushSuccess("Moving", "Element is moved.")
        else:
            self.iface.messageBar().pushWarning("Moving", "Cannot change geometry.")
        self._clear()
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        try:
            self.canvas.unsetMapTool(self)
        except Exception as e:
            logger.debug(f"Error in MoveFeatureTool._apply_move: {e}")


__all__ = ['MoveFeatureTool']
