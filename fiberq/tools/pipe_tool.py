"""
FiberQ v2 - Pipe Tool

Tool for drawing PE ducts and transition pipes on the route network.

Phase 5.2: Added logging infrastructure
"""

from .base import (
    Qt, QVariant, QColor,
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsWkbTypes, QgsRubberBand,
    QgsMapTool, QgsVertexMarker
)

try:
    from qgis.core import QgsDistanceArea
except ImportError:
    QgsDistanceArea = None

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class PipePlaceTool(QgsMapTool):
    """
    Tool for drawing PE ducts and transition pipes.

    Args:
        iface: QGIS interface
        plugin: FiberQ plugin instance
        target_kind: 'PE' for PE ducts or 'PRELAZ' for transition pipes
        attrs: Dict with attributes (materijal, kapacitet, fi)
    """

    def __init__(self, iface, plugin, target_kind, attrs):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()
        self.kind = target_kind
        self.attrs = attrs or {}
        self.points = []

        # Temporary line rubber band
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.rb.setLineStyle(Qt.PenStyle.SolidLine)
        self.rb.show()
        self.rb.setWidth(1.5)
        self.rb.setColor(QColor(0, 255, 0, 180))

        # Snap indicator
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
        self.snap_marker.setPenWidth(3)
        self.snap_marker.setIconSize(14)
        self.snap_marker.setColor(QColor(0, 200, 0))
        self.snap_marker.hide()

    def _event_map_point(self, event):
        """Get QgsPointXY from a map mouse event in a version-safe way."""
        try:
            # QGIS 3.22+
            mp = event.mapPoint()
            return QgsPointXY(mp)
        except Exception:
            try:
                return self.toMapCoordinates(event.pos())
            except Exception:
                return QgsPointXY(0, 0)

    def _snap_via_utils(self, qpt):
        """Try snapping using canvas snapping utils."""
        try:
            su = self.canvas.snappingUtils()
            if su is not None:
                match = su.snapToMap(qpt)
                try:
                    if match.isValid():
                        pt = match.point()
                        return QgsPointXY(pt)
                except Exception as e:
                    logger.debug(f"Error in PipePlaceTool._snap_via_utils: {e}")
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool._snap_via_utils: {e}")
        return None

    def _snap_point(self, qpt):
        """Snap to nodes and route vertices/midpoints."""
        point = QgsPointXY(qpt)
        snap_point = None
        min_dist = None

        # 1) Snap to node layers (poles, manholes)
        node_names = {"Poles", "Stubovi", "OKNA", "Manholes"}
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and  # noqa: W504
                        lyr.name() in node_names):
                    for f in lyr.getFeatures():
                        p = f.geometry().asPoint()
                        d = QgsPointXY(point).distance(QgsPointXY(p))
                        if min_dist is None or d < min_dist:
                            min_dist = d
                            snap_point = QgsPointXY(p)
            except Exception as e:
                logger.debug(f"Error in PipePlaceTool._snap_point: {e}")

        # 2) Snap to route vertices and segment midpoints
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.name() in ('Route', 'Trasa') and  # noqa: W504
                        lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry):

                    for g in lyr.getFeatures():
                        geom = g.geometry()
                        if geom.isMultipart():
                            lines = geom.asMultiPolyline()
                        else:
                            line = geom.asPolyline()
                            lines = [line] if line else []

                        for line in lines:
                            if not line:
                                continue

                            # Vertices
                            for p in line:
                                d = QgsPointXY(point).distance(QgsPointXY(p))
                                if min_dist is None or d < min_dist:
                                    min_dist = d
                                    snap_point = QgsPointXY(p)

                            # Segment midpoints
                            for i in range(len(line) - 1):
                                mid = QgsPointXY(
                                    (line[i].x() + line[i + 1].x()) / 2,
                                    (line[i].y() + line[i + 1].y()) / 2
                                )
                                d = QgsPointXY(point).distance(mid)
                                if min_dist is None or d < min_dist:
                                    min_dist = d
                                    snap_point = mid
            except Exception as e:
                logger.debug(f"Error in PipePlaceTool._snap_point: {e}")

        tolerance = self.canvas.mapUnitsPerPixel() * 20
        if snap_point is not None and min_dist is not None and min_dist < tolerance:
            return snap_point
        return point

    def canvasPressEvent(self, event):
        """Handle mouse press - no action needed."""
        pass

    def canvasReleaseEvent(self, event):
        """Handle mouse release - add point or finish pipe."""
        if event.button() != Qt.MouseButton.LeftButton:
            # Right click finishes if at least 2 points
            if event.button() == Qt.MouseButton.RightButton and len(self.points) >= 2:
                self._finish()
            return

        p0 = self._event_map_point(event)
        sp = self._snap_via_utils(p0)
        p = sp if sp is not None else self._snap_point(p0)
        self.points.append(QgsPointXY(p))

        # Update preview
        try:
            self.snap_marker.setCenter(QgsPointXY(p))
            self.snap_marker.show()
            self.rb.setToGeometry(QgsGeometry.fromPolylineXY(self.points), None)
            self.rb.show()
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool.canvasReleaseEvent: {e}")

        # Finish when we have two points
        if len(self.points) >= 2:
            self._finish()

    def canvasMoveEvent(self, event):
        """Handle mouse move - update snap indicator and preview line."""
        p0 = self._event_map_point(event)
        sp = self._snap_via_utils(p0)
        p = sp if sp is not None else self._snap_point(p0)

        # Show snap marker
        try:
            self.snap_marker.setCenter(QgsPointXY(p))
            self.snap_marker.show()
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool.canvasMoveEvent: {e}")

        # Update rubber band preview
        pts = list(self.points) + [p] if self.points else [p]
        try:
            self.rb.setToGeometry(QgsGeometry.fromPolylineXY(pts), None)
            self.rb.show()
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool.canvasMoveEvent: {e}")

    def keyReleaseEvent(self, event):
        """Handle ESC key to cancel."""
        if event.key() == Qt.Key.Key_Escape:
            self._cleanup(cancel=True)

    def _find_route_layer(self):
        """Find the Route layer in the project."""
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.name() in ('Route', 'Trasa') and  # noqa: W504
                        lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry):
                    return lyr
            except Exception as e:
                logger.debug(f"Error in PipePlaceTool._find_route_layer: {e}")
        return None

    def _get_display_name(self, layer, feat):
        """Get a display name for a node feature."""
        try:
            if layer.name() in ('OKNA', 'Manholes'):
                if 'broj_okna' in layer.fields().names():
                    broj = feat['broj_okna']
                    if broj is not None and str(broj).strip():
                        return f"MH {str(broj).strip()}"  # Issue #9: KO -> MH

            idx = layer.fields().indexFromName('naziv')
            if idx != -1:
                val = feat['naziv']
                if val is not None and str(val).strip():
                    return str(val).strip()

            if layer.name() in ('Poles', 'Stubovi'):
                tip = str(feat['tip']) if 'tip' in layer.fields().names() and feat['tip'] is not None else ''
                return ("Pole " + tip).strip() or f"Pole {int(feat.id())}"  # Stub -> Pole
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool._get_display_name: {e}")
        return f"{layer.name()}:{int(feat.id())}"

    def _find_nearest_name(self, pt, node_layers):
        """Find the display name of the nearest node to a point."""
        best = None  # noqa: F841
        best_dist = None
        best_layer = None
        best_feat = None

        for nl in node_layers:
            for ft in nl.getFeatures():
                try:
                    d = QgsPointXY(pt).distance(QgsPointXY(ft.geometry().asPoint()))
                    if best_dist is None or d < best_dist:
                        best_dist = d
                        best_layer = nl
                        best_feat = ft
                except Exception as e:
                    logger.debug(f"Error in PipePlaceTool._find_nearest_name: {e}")

        if best_layer and best_feat:
            return self._get_display_name(best_layer, best_feat)
        return None

    def _finish(self):
        """Complete the pipe and add it to the layer."""
        route_layer = self._find_route_layer()

        p1, p2 = self.points[0], self.points[1]

        # Try to build geometry along the route
        geom = None
        if route_layer is not None and route_layer.featureCount() > 0:
            try:
                tol_units = self.canvas.mapUnitsPerPixel() * 6
                path_pts = self.plugin._build_path_across_network(route_layer, p1, p2, tol_units)
                if not path_pts:
                    path_pts = self.plugin._build_path_across_joined_trasa(route_layer, p1, p2, tol_units)
                if path_pts:
                    geom = QgsGeometry.fromPolylineXY(path_pts)
            except Exception as e:
                logger.debug(f"Error in PipePlaceTool._finish: {e}")

        if geom is None:
            geom = QgsGeometry.fromPolylineXY([p1, p2])

        # Determine target layer and style
        if self.kind == 'PE':
            layer = self.plugin._ensure_pe_cev_layer()
            color_hex = "#FF9900"  # Orange
            width_mm = 1.0
        else:
            layer = self.plugin._ensure_transition_duct_layer()
            color_hex = "#D0FF00"  # Yellow
            width_mm = 2.2

        # Create feature
        f = QgsFeature(layer.fields())
        f.setGeometry(geom)
        f['materijal'] = self.attrs.get('materijal')
        f['kapacitet'] = self.attrs.get('kapacitet')

        try:
            f['fi'] = int(self.attrs.get('fi')) if self.attrs.get('fi') is not None else None
        except Exception:
            f['fi'] = None

        # Calculate length
        try:
            if QgsDistanceArea is not None:
                d = QgsDistanceArea()
                try:
                    d.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
                except Exception:
                    try:
                        d.setSourceCrs(
                            self.iface.mapCanvas().mapSettings().destinationCrs(),
                            QgsProject.instance().transformContext()
                        )
                    except Exception as e:
                        logger.debug(f"Error in PipePlaceTool._finish: {e}")
                d.setEllipsoid(QgsProject.instance().ellipsoid())
                length_m = d.measureLength(geom) if geom is not None else 0.0
            else:
                length_m = geom.length() if geom is not None else 0.0
            f['duzina_m'] = float(length_m) if length_m else 0.0
        except Exception:
            try:
                f['duzina_m'] = float(geom.length()) if geom is not None else None
            except Exception:
                f['duzina_m'] = None

        # Find FROM/TO names
        node_names = {"Poles", "Stubovi", "OKNA", "Manholes"}
        node_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and  # noqa: W504
                        lyr.name() in node_names):
                    node_layers.append(lyr)
            except Exception as e:
                logger.debug(f"Error in PipePlaceTool._finish: {e}")

        od_naziv = self._find_nearest_name(p1, node_layers)
        do_naziv = self._find_nearest_name(p2, node_layers)

        if 'od' in layer.fields().names():
            f['od'] = od_naziv
        if 'do' in layer.fields().names():
            f['do'] = do_naziv

        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(f)
        except Exception as e:
            logger.debug(f"Error setting UUID on pipe: {e}")

        # Add feature
        layer.startEditing()

        # Ensure duzina_m field exists
        try:
            if 'duzina_m' not in layer.fields().names():
                layer.addAttribute(QgsField('duzina_m', QVariant.Double))
                layer.updateFields()
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool._finish: {e}")

        layer.addFeature(f)
        layer.commitChanges()
        layer.updateExtents()

        # Record for undo (v1.2 — Feature 2)
        try:
            if self.plugin and hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                self.plugin.undo_manager.record_add(layer, f)
        except Exception as e:
            logger.debug(f"Error recording undo for pipe: {e}")

        # Apply style
        try:
            self.plugin._apply_pipe_style(layer, color_hex, width_mm)
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool._finish: {e}")

        self._cleanup(stay_active=True)

    def _cleanup(self, cancel=False, stay_active=False):
        """Clean up markers and rubber band."""
        try:
            if getattr(self, "snap_marker", None) is not None:
                try:
                    self.canvas.scene().removeItem(self.snap_marker)
                except Exception:
                    try:
                        self.snap_marker.hide()
                    except Exception as e:
                        logger.debug(f"Error in PipePlaceTool._cleanup: {e}")
                self.snap_marker = None

            if getattr(self, "rb", None) is not None:
                try:
                    self.rb.reset(QgsWkbTypes.GeometryType.LineGeometry)
                    self.rb.hide()
                except Exception as e:
                    logger.debug(f"Error in PipePlaceTool._cleanup: {e}")
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool._cleanup: {e}")

        self.points = []

        if not stay_active:
            try:
                self.iface.mapCanvas().unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in PipePlaceTool._cleanup: {e}")

        if not cancel:
            self.iface.messageBar().pushInfo("Pipes", "Pipe has been laid.")

    def deactivate(self):
        """Clean up when tool is deactivated."""
        try:
            self._cleanup(cancel=True, stay_active=True)
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool.deactivate: {e}")
        try:
            super().deactivate()
        except Exception as e:
            logger.debug(f"Error in PipePlaceTool.deactivate: {e}")


__all__ = ['PipePlaceTool']
