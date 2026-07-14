"""
FiberQ v2 - Region Drawing Tool

Map tool for manually drawing service area polygons.
Phase 2.1: Extracted from extracted_classes.py
"""

from datetime import datetime

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QInputDialog

from qgis.core import (
    QgsProject, QgsFeature, QgsGeometry,
    QgsPointXY, QgsWkbTypes, QgsDistanceArea
)
from qgis.gui import QgsMapTool, QgsRubberBand

# Import from legacy bridge for compatibility
from ..utils.legacy_bridge import _ensure_region_layer

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class DrawRegionPolygonTool(QgsMapTool):
    """Freehand polygon drawing tool with rubber band (finish with right-click)"""

    def __init__(self, iface, core):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.core = core
        self.canvas = iface.mapCanvas()
        self.points = []
        self.rb = None
        self._setup_rb()

    def _setup_rb(self):
        try:
            self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
            # Style similar to other toolbar icons: soft slate stroke, semi-transparent fill
            self.rb.setWidth(2)
            self.rb.setStrokeColor(QColor('#334155'))  # slate-700
            c = QColor('#60a5fa')  # blue-400
            c.setAlpha(60)
            self.rb.setFillColor(c)
        except Exception:
            self.rb = None

    def activate(self):
        try:
            if self.rb is None:
                self._setup_rb()
            self.points = []
            if self.rb:
                self.rb.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.iface.messageBar().pushInfo(
                'Draw Service Area (manual)',
                'Left click adds vertices, Backspace removes, right click finishes.'
            )
        except Exception as e:
            logger.debug(f"Error in DrawRegionPolygonTool.activate: {e}")
        super().activate()

    def deactivate(self):
        try:
            if self.rb:
                self.rb.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        except Exception as e:
            logger.debug(f"Error in DrawRegionPolygonTool.deactivate: {e}")
        super().deactivate()

    def keyPressEvent(self, e):
        try:
            if e.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                if self.points:
                    self.points.pop()
                    self._update_rb()
            elif e.key() == Qt.Key.Key_Escape:
                self.points = []
                self._update_rb()
        except Exception as e:
            logger.debug(f"Error in DrawRegionPolygonTool.keyPressEvent: {e}")

    def canvasPressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            # Add point to polygon
            self.points.append(self.toMapCoordinates(e.pos()))
            self._update_rb()

        elif e.button() == Qt.MouseButton.RightButton:
            # Right click: if not enough points -> abort and exit
            if len(self.points) < 3:
                self.points = []
                self._update_rb()
                try:
                    self.canvas.unsetMapTool(self)
                except Exception as e:
                    logger.debug(f"Error in DrawRegionPolygonTool.canvasPressEvent: {e}")
            else:
                # We have valid polygon -> finish drawing and exit tool
                self._finish_polygon()

    def canvasMoveEvent(self, e):
        try:
            if self.points:
                p = self.toMapCoordinates(e.pos())
                self._update_rb(temp_point=QgsPointXY(p))
        except Exception as e:
            logger.debug(f"Error in DrawRegionPolygonTool.canvasMoveEvent: {e}")

    def _update_rb(self, temp_point=None):
        try:
            if not self.rb:
                return
            self.rb.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            pts = list(self.points)
            if temp_point is not None:
                pts.append(temp_point)
            if len(pts) >= 2:
                self.rb.setToGeometry(QgsGeometry.fromPolygonXY([pts]), None)
        except Exception as e:
            logger.debug(f"Error in DrawRegionPolygonTool._update_rb: {e}")

    def _finish_polygon(self):
        try:
            if len(self.points) < 3:
                self.iface.messageBar().pushWarning(
                    'Draw Service Area manually',
                    'At least 3 vertices are required.'
                )
                return

            geom = QgsGeometry.fromPolygonXY([self.points])
            region = _ensure_region_layer(self.core)
            if not region:
                return

            # Ask for name
            try:
                name, ok = QInputDialog.getText(self.iface.mainWindow(), 'Service Area', 'Name:')
            except Exception:
                name, ok = ('Rejon', True)
            if not ok:
                return

            d = QgsDistanceArea()
            try:
                prj = QgsProject.instance()
                if prj.ellipsoid():
                    d.setEllipsoid(prj.ellipsoid())
                d.setSourceCrs(prj.crs(), QgsProject.instance().transformContext())
                d.setEllipsoidalMode(True)
            except Exception as e:
                logger.debug(f"Error in DrawRegionPolygonTool._finish_polygon: {e}")

            area = d.measureArea(geom) if d else geom.area()
            peri = d.measurePerimeter(geom) if d else geom.length()

            region.startEditing()
            f = QgsFeature(region.fields())
            f.setGeometry(geom)
            f['name'] = (name or 'Rejon')
            f['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f['area_m2'] = float(area)
            f['perim_m'] = float(peri)
            f['count'] = 0
            # Phase 0.1: Set UUID for FiberQ Designer
            try:
                from ..utils.uuid_utils import set_feature_uuid
                set_feature_uuid(f)
            except Exception as e:
                logger.debug(f"Failed to set uuid on region feature: {e}")
            region.addFeature(f)
            region.commitChanges()
            region.triggerRepaint()

            # Record for undo (v1.2 — Feature 2)
            try:
                _core = getattr(self, 'core', None) or getattr(self, 'plugin', None)
                if _core and hasattr(_core, 'undo_manager') and _core.undo_manager:
                    _core.undo_manager.record_add(region, f)
            except Exception as e:
                logger.debug(f"Error recording undo for region: {e}")

            self.iface.messageBar().pushSuccess(
                'Service Area',
                'Service Area added to "Service Area" layer.'
            )

            # Reset for next polygon
            self.points = []
            self._update_rb()

            # After successful drawing – exit tool
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in DrawRegionPolygonTool._finish_polygon: {e}")

        except Exception as e:
            try:
                self.iface.messageBar().pushCritical('Service Area', f'Error: {e}')
            except Exception as e:
                logger.debug(f"Error in DrawRegionPolygonTool._finish_polygon: {e}")


__all__ = ['DrawRegionPolygonTool']
