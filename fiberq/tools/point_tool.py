"""
FiberQ v2 - Point Placement Tool

Map tool for placing poles with snap functionality.
Phase 2.1: Extracted from extracted_classes.py
"""

from qgis.PyQt import sip

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsWkbTypes, QgsSettings
)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class PointTool(QgsMapToolEmitPoint):
    """Map tool for placing poles with snapping to route vertices and midpoints."""

    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setColor(QColor(0, 255, 0))
        self.snap_marker.setIconType(QgsVertexMarker.ICON_CROSS)
        self.snap_marker.setIconSize(14)
        self.snap_marker.setPenWidth(3)
        self.snap_marker.hide()

    def _snap_candidate(self, point):
        """Find snap candidate on route layer vertices and midpoints."""
        route_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route', 'Route') and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                route_layer = lyr
                break

        snap_point = None
        min_dist = None

        # Snap distance in pixels from FiberQ Settings
        try:
            s = QgsSettings()
            snap_px = int(s.value("FiberQ/default_snap_distance", "20"))
        except Exception as e:
            snap_px = 20

        snap_tolerance = self.canvas.mapUnitsPerPixel() * snap_px

        if route_layer and route_layer.featureCount() > 0:
            for feat in route_layer.getFeatures():
                geom = feat.geometry()
                if geom.isMultipart():
                    lines = geom.asMultiPolyline()
                else:
                    lines = [geom.asPolyline()]

                for line in lines:
                    if not line:
                        continue
                    # Check all vertices (endpoints + break points)
                    for pt in line:
                        dist = QgsPointXY(point).distance(QgsPointXY(pt))
                        if min_dist is None or dist < min_dist:
                            min_dist = dist
                            snap_point = QgsPointXY(pt)

                    # Also keep segment midpoints
                    for i in range(len(line)-1):
                        mid = QgsPointXY(
                            (line[i].x() + line[i+1].x()) / 2,
                            (line[i].y() + line[i+1].y()) / 2
                        )
                        dist = QgsPointXY(point).distance(mid)
                        if min_dist is None or dist < min_dist:
                            min_dist = dist
                            snap_point = mid

        if snap_point and min_dist is not None and min_dist < snap_tolerance:
            return snap_point
        return None

    def canvasMoveEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        snap_point = self._snap_candidate(point)
        if snap_point:
            self.snap_marker.setCenter(snap_point)
            self.snap_marker.show()
        else:
            self.snap_marker.hide()

    def canvasReleaseEvent(self, event):
        # Right click – cancel command without adding pole
        if event.button() == Qt.MouseButton.RightButton:
            try:
                self.snap_marker.hide()
            except Exception as e:
                logger.debug(f"Error in PointTool.canvasReleaseEvent: {e}")
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

        point = self.toMapCoordinates(event.pos())
        snap_point = self._snap_candidate(point)
        final_point = snap_point if snap_point else point

        feature = QgsFeature(self.layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(final_point))
        feature.setAttribute("tip", "POLE")
        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(feature)
        except Exception:
            pass
        self.layer.startEditing()
        self.layer.addFeature(feature)
        self.layer.commitChanges()
        self.layer.triggerRepaint()
        self.snap_marker.hide()

        # Record for undo (v1.2 — Feature 2)
        try:
            if hasattr(self, 'plugin') and self.plugin and hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                self.plugin.undo_manager.record_add(self.layer, feature)
        except Exception as e:
            pass  # PointTool may not always have plugin reference


__all__ = ['PointTool']
