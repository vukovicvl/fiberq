"""
FiberQ v2 - Route Tool

Tool for manually drawing routes by clicking points on the map.
"""

from .base import (
    Qt, QVariant, QColor, QMessageBox, QInputDialog,
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsWkbTypes, QgsRubberBand,
    QgsMapTool,
    get_element_defs, get_joint_closure_def, get_route_type_options
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class ManualRouteTool(QgsMapTool):
    """
    Tool for manually creating routes by clicking points on the map.

    Features:
    - Snaps to poles, manholes, elements, and existing route vertices
    - Visual feedback with rubber band line
    - Creates route on double-click or right-click
    """

    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()

        # Route line rubber band
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.rb.setColor(QColor(0, 0, 255, 150))
        self.rb.setWidth(2)

        # Collected points
        self.points = []

        # Snap indicator
        self.snap_rubber = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.snap_rubber.setColor(QColor(255, 0, 0, 180))
        self.snap_rubber.setWidth(12)

    def _get_snap_layer_names(self):
        """Get names of layers to snap to."""
        names = ['Poles', 'Stubovi', 'OKNA', 'Manholes']

        # Add joint closure layer
        try:
            jc_def = get_joint_closure_def()
            nm = jc_def.get('name', 'Joint Closures')
            if nm and nm not in names:
                names.append(nm)
        except Exception as e:
            if 'Nastavci' not in names:
                names.append('Nastavci')

        # Add element layers
        try:
            for d in get_element_defs():
                nm = d.get('name')
                if nm and nm not in names:
                    names.append(nm)
        except Exception as e:
            logger.debug(f"Error in ManualRouteTool._get_snap_layer_names: {e}")

        return names

    def _find_snap_point(self, point):
        """
        Find the nearest snap point for a given map point.

        Args:
            point: QgsPointXY to snap

        Returns:
            Tuple of (snap_point, min_distance) or (None, None)
        """
        min_dist = None
        snap_point = None

        # Get node layers to snap to
        node_layer_names = self._get_snap_layer_names()
        node_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and
                    lyr.geometryType() == QgsWkbTypes.PointGeometry and
                    lyr.name() in node_layer_names):
                    node_layers.append(lyr)
            except Exception as e:
                logger.debug(f"Error in ManualRouteTool._find_snap_point: {e}")

        # Snap to node layers
        for nl in node_layers:
            for feature in nl.getFeatures():
                geom = feature.geometry()
                if not geom or geom.isEmpty():
                    continue
                try:
                    pt = geom.asPoint()
                    d = QgsPointXY(point).distance(QgsPointXY(pt))
                    if min_dist is None or d < min_dist:
                        min_dist = d
                        snap_point = QgsPointXY(pt)
                except Exception as e:
                    continue

        # Snap to existing routes (vertices and segment midpoints)
        try:
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if (isinstance(lyr, QgsVectorLayer) and
                        lyr.geometryType() == QgsWkbTypes.LineGeometry and
                        lyr.name() in ('Route', 'Trasa')):

                        for feat in lyr.getFeatures():
                            geom = feat.geometry()
                            if not geom or geom.isEmpty():
                                continue

                            if geom.isMultipart():
                                lines = geom.asMultiPolyline()
                            else:
                                lines = [geom.asPolyline()]

                            for line in lines:
                                if not line:
                                    continue

                                # All vertices
                                for pt in line:
                                    d = QgsPointXY(point).distance(QgsPointXY(pt))
                                    if min_dist is None or d < min_dist:
                                        min_dist = d
                                        snap_point = QgsPointXY(pt)

                                # Segment midpoints
                                for i in range(len(line) - 1):
                                    mid = QgsPointXY(
                                        (line[i].x() + line[i + 1].x()) / 2.0,
                                        (line[i].y() + line[i + 1].y()) / 2.0
                                    )
                                    d = QgsPointXY(point).distance(mid)
                                    if min_dist is None or d < min_dist:
                                        min_dist = d
                                        snap_point = mid
                except Exception as e:
                    logger.debug(f"Error in ManualRouteTool._find_snap_point: {e}")
        except Exception as e:
            logger.debug(f"Error in ManualRouteTool._find_snap_point: {e}")

        return snap_point, min_dist

    def canvasPressEvent(self, event):
        """Handle mouse press - add point or finish route."""
        if event.button() == Qt.MouseButton.RightButton:
            self._finish_route()
            return

        point = self.toMapCoordinates(event.pos())

        # Try to snap
        snap_point, min_dist = self._find_snap_point(point)
        snap_tolerance = self.canvas.mapUnitsPerPixel() * 15

        if min_dist is not None and min_dist < snap_tolerance and snap_point is not None:
            point = snap_point
            self.snap_rubber.reset(QgsWkbTypes.PointGeometry)
            self.snap_rubber.addPoint(snap_point)
        else:
            self.snap_rubber.reset(QgsWkbTypes.PointGeometry)

        self.points.append(point)
        self.rb.addPoint(point)

    def canvasMoveEvent(self, event):
        """Handle mouse move - update rubber band and snap indicator."""
        point = self.toMapCoordinates(event.pos())

        # Try to snap
        snap_point, min_dist = self._find_snap_point(point)
        snap_tolerance = self.canvas.mapUnitsPerPixel() * 15

        if snap_point is not None and min_dist is not None and min_dist < snap_tolerance:
            self.snap_rubber.reset(QgsWkbTypes.PointGeometry)
            self.snap_rubber.addPoint(snap_point)
            disp_point = snap_point
        else:
            self.snap_rubber.reset(QgsWkbTypes.PointGeometry)
            disp_point = point

        # Update rubber band
        pts = (list(self.points) + [disp_point]) if self.points else [disp_point]
        self.rb.setToGeometry(QgsGeometry.fromPolylineXY(pts), None)

    def canvasDoubleClickEvent(self, event):
        """Handle double-click - finish route."""
        self._finish_route()

    def _finish_route(self):
        """Complete the route and add it to the layer."""
        # Clear snap marker
        self.snap_rubber.reset(QgsWkbTypes.PointGeometry)

        # Need at least 2 points
        if len(self.points) < 2:
            self.rb.reset(QgsWkbTypes.LineGeometry)
            self.points = []
            self.canvas.unsetMapTool(self)
            return

        # Find or create Route layer
        route_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and
                lyr.name() in ('Route', 'Trasa') and
                lyr.geometryType() == QgsWkbTypes.LineGeometry):
                route_layer = lyr
                break

        if route_layer is None:
            crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
            route_layer = QgsVectorLayer(f"LineString?crs={crs}", "Route", "memory")
            QgsProject.instance().addMapLayer(route_layer)

        # Ensure required fields exist
        route_layer.startEditing()
        if route_layer.fields().indexFromName("naziv") == -1:
            route_layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
        if route_layer.fields().indexFromName("duzina") == -1:
            route_layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
        if route_layer.fields().indexFromName("duzina_km") == -1:
            route_layer.dataProvider().addAttributes([QgsField("duzina_km", QVariant.Double)])
        if route_layer.fields().indexFromName("tip_trase") == -1:
            route_layer.dataProvider().addAttributes([QgsField("tip_trase", QVariant.String)])
        route_layer.updateFields()
        route_layer.commitChanges()

        # Apply style
        if self.plugin:
            self.plugin.stylize_route_layer(route_layer)

        # Create geometry
        line_geom = QgsGeometry.fromPolylineXY(self.points)
        duzina_m = line_geom.length()
        duzina_km = round(duzina_m / 1000.0, 2)

        # Get route type options
        try:
            TRASA_TYPE_OPTIONS, TRASA_TYPE_LABELS, TRASA_LABEL_TO_CODE = get_route_type_options()
        except Exception as e:
            TRASA_TYPE_OPTIONS = ['vazdusna', 'podzemna', 'kroz objekat']
            TRASA_TYPE_LABELS = {'vazdusna': 'Aerial', 'podzemna': 'Underground', 'kroz objekat': 'Through the object'}
            TRASA_LABEL_TO_CODE = {'Aerial': 'vazdusna', 'Underground': 'podzemna', 'Through the object': 'kroz objekat'}

        # Ask for route type
        items = [TRASA_TYPE_LABELS.get(code, code) for code in TRASA_TYPE_OPTIONS]
        tip_label, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Route type",
            "Select route type:",
            items,
            0,
            False
        )

        if not ok or not tip_label:
            tip_trase = TRASA_TYPE_OPTIONS[0]
        else:
            tip_trase = TRASA_LABEL_TO_CODE.get(tip_label, TRASA_TYPE_OPTIONS[0])

        # Create feature
        route_layer.startEditing()
        feat = QgsFeature(route_layer.fields())
        feat.setGeometry(line_geom)
        feat.setAttribute("naziv", f"Route {route_layer.featureCount() + 1}")
        feat.setAttribute("duzina", duzina_m)
        feat.setAttribute("duzina_km", duzina_km)
        feat.setAttribute("tip_trase", tip_trase)
        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(feat)
        except Exception as e:
            pass
        route_layer.addFeature(feat)
        route_layer.commitChanges()

        # Record for undo (v1.2 — Feature 2)
        try:
            if self.plugin and hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                self.plugin.undo_manager.record_add(route_layer, feat)
        except Exception as e:
            logger.debug(f"Error recording undo for route: {e}")

        # Re-apply style
        if self.plugin:
            self.plugin.stylize_route_layer(route_layer)

        # Show message
        nice_label = TRASA_TYPE_LABELS.get(tip_trase, tip_trase)
        QMessageBox.information(
            self.iface.mainWindow(),
            "FiberQ",
            f"Manual route has been created!\n"
            f"Length: {duzina_m:.2f} m ({duzina_km:.2f} km)\n"
            f"Type: {nice_label}"
        )

        # Reset tool
        self.points = []
        self.rb.reset(QgsWkbTypes.LineGeometry)
        self.canvas.unsetMapTool(self)

    def deactivate(self):
        """Clean up when tool is deactivated."""
        self.rb.reset(QgsWkbTypes.LineGeometry)
        self.snap_rubber.reset(QgsWkbTypes.PointGeometry)
        self.points = []
        super().deactivate()


__all__ = ['ManualRouteTool']
