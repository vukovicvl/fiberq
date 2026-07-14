"""
FiberQ v2 - Breakpoint Tool

Tool for splitting routes at a click point.
"""

from .base import (
    Qt, QColor, QMessageBox,
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsWkbTypes, QgsRubberBand,
    QgsMapToolEmitPoint
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class BreakpointTool(QgsMapToolEmitPoint):
    """
    Tool for splitting a route at a click point.

    The user clicks on a route, and the tool splits the route into two
    segments at the clicked location. The original route feature is deleted
    and replaced with two new features.
    """

    def __init__(self, canvas, iface, plugin):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.plugin = plugin

        # Visual feedback rubber band
        self.rubber = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.rubber.setColor(QColor(0, 255, 0))
        self.rubber.setWidth(10)

        # Snap info for the current position
        self.snap_info = None

    def _find_route_layer(self):
        """Find the Route layer in the project."""
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                lyr.name() in ('Route', 'Trasa') and  # noqa: W504
                    lyr.geometryType() == QgsWkbTypes.LineGeometry):
                return lyr
        return None

    def canvasMoveEvent(self, event):
        """Update snap indicator as mouse moves."""
        point = self.toMapCoordinates(event.pos())

        route_layer = self._find_route_layer()
        if route_layer is None or route_layer.featureCount() == 0:
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            self.snap_info = None
            return

        min_dist = None
        snapped_point = None
        min_feat = None
        min_geom = None
        min_seg_idx = None

        # Find closest point on any route feature
        for feat in route_layer.getFeatures():
            geom = feat.geometry()
            dist, snap, vertex_after, seg_idx = geom.closestSegmentWithContext(point)
            if min_dist is None or dist < min_dist:
                min_dist = dist
                snapped_point = snap
                min_feat = feat
                min_geom = geom
                min_seg_idx = seg_idx

        tolerance = self.canvas.mapUnitsPerPixel() * 10
        if snapped_point and min_dist < tolerance:
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            self.rubber.addPoint(snapped_point)
            self.snap_info = {
                'feat': min_feat,
                'geom': min_geom,
                'point': snapped_point,
                'seg_idx': min_seg_idx,
                'dist': min_dist
            }
        else:
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            self.snap_info = None

    def canvasReleaseEvent(self, event):
        """Handle mouse release - split route if valid location."""
        # Right click = cancel tool
        if event.button() == Qt.MouseButton.RightButton:
            self.snap_info = None
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            self.iface.mapCanvas().unsetMapTool(self)
            return

        # Only process left click
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.snap_info is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Split route",
                "Click closer to a route!"
            )
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            return

        min_feat = self.snap_info['feat']
        min_geom = self.snap_info['geom']
        snapped_point = self.snap_info['point']
        min_seg_idx = self.snap_info['seg_idx']  # noqa: F841

        # Handle multipart geometry
        if min_geom.isMultipart():
            lines = min_geom.asMultiPolyline()
            if lines and len(lines) == 1:
                min_geom = QgsGeometry.fromPolylineXY(lines[0])
            else:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Split route",
                    "The route is a multi-line (multipart) geometry with multiple lines "
                    "and cannot be split with this tool!\n"
                    "Merge the lines so that there is ONE line (not a MultiLineString)."
                )
                self.rubber.reset(QgsWkbTypes.PointGeometry)
                return

        # Convert all vertices to QgsPointXY
        line_points = [QgsPointXY(pt) for pt in min_geom.vertices()]

        # Special case for 2-vertex line
        if len(line_points) == 2:
            p0, p1 = line_points
            tol = self.canvas.mapUnitsPerPixel() * 2

            # Check if split point is too close to endpoints
            if (QgsGeometry.fromPointXY(snapped_point).distance(QgsGeometry.fromPointXY(p0)) < tol or  # noqa: W504
                    QgsGeometry.fromPointXY(snapped_point).distance(QgsGeometry.fromPointXY(p1)) < tol):
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Split route",
                    "Click closer to the middle of the segment."
                )
                self.rubber.reset(QgsWkbTypes.PointGeometry)
                return

            geom1 = QgsGeometry.fromPolylineXY([p0, snapped_point])
            geom2 = QgsGeometry.fromPolylineXY([snapped_point, p1])
        else:
            # Standard split logic for lines with more vertices
            res, new_geoms, topo_test = min_geom.splitGeometry([snapped_point], False)

            if res != 0 or not new_geoms:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Split route",
                    "Cannot split the route at this location."
                )
                self.rubber.reset(QgsWkbTypes.PointGeometry)
                return

            geom1 = min_geom
            geom2 = new_geoms[0]

        # Get original attributes
        naziv = min_feat['naziv'] if 'naziv' in min_feat.fields().names() else ''
        tip_trase = min_feat['tip_trase'] if 'tip_trase' in min_feat.fields().names() else 'nepoznat'

        # Get route layer
        route_layer = self._find_route_layer()
        if route_layer is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Split route",
                "Route layer 'Route' not found!"
            )
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            return

        # Perform the split
        route_layer.startEditing()
        route_layer.deleteFeature(min_feat.id())

        # Create first segment
        feat1 = QgsFeature(route_layer.fields())
        feat1.setGeometry(geom1)
        feat1.setAttribute('naziv', naziv + "_a")
        feat1.setAttribute('tip_trase', tip_trase)
        duzina_m1 = geom1.length()
        feat1.setAttribute('duzina', duzina_m1)
        feat1.setAttribute('duzina_km', round(duzina_m1 / 1000.0, 2))

        # Create second segment
        feat2 = QgsFeature(route_layer.fields())
        feat2.setGeometry(geom2)
        feat2.setAttribute('naziv', naziv + "_b")
        feat2.setAttribute('tip_trase', tip_trase)
        duzina_m2 = geom2.length()
        feat2.setAttribute('duzina', duzina_m2)
        feat2.setAttribute('duzina_km', round(duzina_m2 / 1000.0, 2))

        # Phase 0.1: Set UUID for FiberQ Designer (new segments get new UUIDs)
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(feat1)
            set_feature_uuid(feat2)
        except Exception as e:
            logger.debug(f"could not set uuid on new route segments: {e}")

        route_layer.addFeatures([feat1, feat2])
        route_layer.commitChanges()

        # Re-apply styling
        if self.plugin:
            self.plugin.stylize_route_layer(route_layer)

        self.rubber.reset(QgsWkbTypes.PointGeometry)
        QMessageBox.information(
            self.iface.mainWindow(),
            "Split route",
            f"The route has been split!\n"
            f"First part: {duzina_m1:.2f} m, second part: {duzina_m2:.2f} m."
        )

    def deactivate(self):
        """Clean up when tool is deactivated."""
        self.rubber.reset(QgsWkbTypes.PointGeometry)
        self.snap_info = None
        super().deactivate()


__all__ = ['BreakpointTool']
