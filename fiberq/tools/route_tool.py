"""
FiberQ v2 - Route Tool

Tool for manually drawing routes by clicking points on the map.
"""

import math

from .base import (
    Qt, QVariant, QColor, QMessageBox, QInputDialog,
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsWkbTypes, QgsRubberBand,
    QgsMapTool,
    get_element_defs, get_joint_closure_def, get_route_type_options
)

# Phase 5.2: Logging
from ..utils.geometry import held_by_its_box, polylines
from ..utils.logger import get_logger
from ..utils.measure import ground_length
from ..utils.spatial import features_within
logger = get_logger(__name__)

#: How near, in screen pixels, a click or a move must come to a node or a
#: route to snap to it.
SNAP_PIXELS = 15


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
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.rb.setColor(QColor(0, 0, 255, 150))
        self.rb.setWidth(2)

        # Collected points
        self.points = []

        # Snap indicator
        self.snap_rubber = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
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
        except Exception:
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

        A distance that is not a number -- a vertex at NaN -- is passed over.
        Met first, it used to become the best so far, and since ``d < nan`` is
        never true nothing after it could replace it: one such vertex switched
        the snap off for the whole project.

        So is a route that is not a line at all, a point or a polygon stored in
        the Route layer: ``asPolyline()`` raised TypeError for it inside the
        ``try`` around the whole layer, and no route after it was snapped to.

        A node or route a box query can miss -- a line with a coordinate that is
        not a finite number, a one-vertex part, an arc QGIS cannot box -- is
        skipped (``utils.geometry.held_by_its_box``). The check is asked only of
        one that would win within the snap distance, the only answer the callers
        use.

        Each layer is asked only for the features whose box comes within the
        snap distance of ``point`` (``utils.spatial.features_within``, WP4 4.1
        item PF-5), in the order the whole layer hands them out, or read whole
        where a box cannot answer exactly. Every vertex or midpoint within the
        snap distance is among them, so that answer is the scan's.

        Args:
            point: QgsPointXY to snap

        Returns:
            Tuple of (snap_point, min_distance) or (None, None). Beyond the snap
            distance: the nearest of what was read, which no caller uses.
        """
        tolerance = self.canvas.mapUnitsPerPixel() * SNAP_PIXELS
        slack = tolerance / 2
        min_dist = None
        snap_point = None

        # Get node layers to snap to
        node_layer_names = self._get_snap_layer_names()
        node_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and  # noqa: W504
                        lyr.name() in node_layer_names):
                    node_layers.append(lyr)
            except Exception as e:
                logger.debug(f"Error in ManualRouteTool._find_snap_point: {e}")

        # Snap to node layers
        for nl in node_layers:
            near = features_within(nl, point, tolerance)
            for feature in (nl.getFeatures() if near is None else near):
                geom = feature.geometry()
                if not geom or geom.isEmpty():
                    continue
                try:
                    pt = geom.asPoint()
                    d = QgsPointXY(point).distance(QgsPointXY(pt))
                    if math.isnan(d):
                        continue
                    if min_dist is None or d < min_dist:
                        if not d >= tolerance and not held_by_its_box(geom, slack):
                            continue
                        min_dist = d
                        snap_point = QgsPointXY(pt)
                except Exception as e:
                    logger.debug(f"could not compute distance to snap point: {e}")
                    continue

        # Snap to existing routes (vertices and segment midpoints)
        try:
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                        lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry and  # noqa: W504
                            lyr.name() in ('Route', 'Trasa')):

                        near = features_within(lyr, point, tolerance)
                        for feat in (lyr.getFeatures() if near is None else near):
                            geom = feat.geometry()
                            if not geom or geom.isEmpty():
                                continue

                            # A point or polygon in the layer is passed over:
                            # its TypeError used to end the whole layer's search.
                            lines = polylines(geom)

                            # The route's own nearest vertex or midpoint, the
                            # first of a tie; it replaces the best so far only
                            # if it is nearer, as each point did one by one.
                            nearest = None
                            for line in lines:
                                if not line:
                                    continue

                                # All vertices
                                for pt in line:
                                    d = QgsPointXY(point).distance(QgsPointXY(pt))
                                    if math.isnan(d):
                                        continue
                                    if nearest is None or d < nearest[0]:
                                        nearest = (d, QgsPointXY(pt))

                                # Segment midpoints
                                for i in range(len(line) - 1):
                                    mid = QgsPointXY(
                                        (line[i].x() + line[i + 1].x()) / 2.0,
                                        (line[i].y() + line[i + 1].y()) / 2.0
                                    )
                                    d = QgsPointXY(point).distance(mid)
                                    if math.isnan(d):
                                        continue
                                    if nearest is None or d < nearest[0]:
                                        nearest = (d, mid)
                            if nearest is None or not (min_dist is None or nearest[0] < min_dist):
                                continue
                            if not nearest[0] >= tolerance and not held_by_its_box(geom, slack):
                                continue
                            min_dist, snap_point = nearest
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
        snap_tolerance = self.canvas.mapUnitsPerPixel() * SNAP_PIXELS

        if min_dist is not None and min_dist < snap_tolerance and snap_point is not None:
            point = snap_point
            self.snap_rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.snap_rubber.addPoint(snap_point)
        else:
            self.snap_rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)

        self.points.append(point)
        self.rb.addPoint(point)

    def canvasMoveEvent(self, event):
        """Handle mouse move - update rubber band and snap indicator."""
        point = self.toMapCoordinates(event.pos())

        # Try to snap
        snap_point, min_dist = self._find_snap_point(point)
        snap_tolerance = self.canvas.mapUnitsPerPixel() * SNAP_PIXELS

        if snap_point is not None and min_dist is not None and min_dist < snap_tolerance:
            self.snap_rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.snap_rubber.addPoint(snap_point)
            disp_point = snap_point
        else:
            self.snap_rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
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
        self.snap_rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)

        # Need at least 2 points
        if len(self.points) < 2:
            self.rb.reset(QgsWkbTypes.GeometryType.LineGeometry)
            self.points = []
            self.canvas.unsetMapTool(self)
            return

        # Find or create Route layer
        route_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                lyr.name() in ('Route', 'Trasa') and  # noqa: W504
                    lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry):
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

        # WP1b identity invariant: ensure the fiberq_uuid column exists before
        # features are added, so set_feature_uuid() below actually stamps it.
        try:
            from ..utils.uuid_utils import ensure_uuid_field
            ensure_uuid_field(route_layer)
        except Exception as e:
            logger.debug(f"Error ensuring fiberq_uuid on route layer: {e}")

        # Apply style
        if self.plugin:
            self.plugin.stylize_route_layer(route_layer)

        # Create geometry
        line_geom = QgsGeometry.fromPolylineXY(self.points)
        duzina_m = ground_length(line_geom, route_layer)
        duzina_km = round(duzina_m / 1000.0, 2)

        # Get route type options
        try:
            TRASA_TYPE_OPTIONS, TRASA_TYPE_LABELS, TRASA_LABEL_TO_CODE = get_route_type_options()
        except Exception:
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
            logger.debug(f"failed to set uuid on route feature: {e}")
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
        self.rb.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.canvas.unsetMapTool(self)

    def deactivate(self):
        """Clean up when tool is deactivated."""
        self.rb.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.snap_rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.points = []
        super().deactivate()


__all__ = ['ManualRouteTool']
