"""
FiberQ v2 - Slack Tool

Tool for placing optical slack (reserve) points on cables.
"""

from .base import (
    Qt, QMessageBox,
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsWkbTypes,
    QgsMapTool,
    PlacementSnapper, snap_match
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class SlackPlaceTool(QgsMapTool):
    """
    Tool for placing optical slack (reserve) points on cable endpoints or along cables.

    The tool snaps to cable endpoints (FROM/TO) or mid-span positions and
    records the cable reference and slack type.
    """

    def __init__(self, iface, plugin, params):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()
        self.params = dict(params or {})

        # The slack tool resolves its own target -- which cable, and which end
        # of it -- so it uses the shared snapper only for the indicator. Showing
        # QGIS's generic nearest vertex here would promise a lock the click
        # would not honour, which is exactly what the old preview did.
        self.snapper = PlacementSnapper(self.canvas)

    def deactivate(self):
        """Clear the indicator, so it does not outlive the tool."""
        self.snapper.clear()
        super().deactivate()

    def _iter_cable_layers(self):
        """Iterate over all cable layers in the project."""
        cable_names = {
            "Kablovi_podzemni", "Kablovi_vazdusni",
            "Underground cables", "Aerial cables"
        }
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry and  # noqa: W504
                        lyr.name() in cable_names):
                    yield lyr
            except Exception as e:
                logger.debug(f"Error in SlackPlaceTool._iter_cable_layers: {e}")

    def _iter_node_layers(self):
        """Iterate over pole and manhole layers."""
        node_names = {"Poles", "Stubovi", "OKNA", "Manholes"}
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and  # noqa: W504
                        lyr.name() in node_names):
                    yield lyr
            except Exception as e:
                logger.debug(f"Error in SlackPlaceTool._iter_node_layers: {e}")

    def _nearest_node(self, pt):
        """
        Find the nearest node (pole/manhole) to a point.

        Returns:
            Tuple of (layer, feature, distance) or (None, None, None)
        """
        best = (None, None, None)
        for nl in self._iter_node_layers():
            for f in nl.getFeatures():
                try:
                    p = f.geometry().asPoint()
                    d = QgsPointXY(p).distance(pt)
                    if best[2] is None or d < best[2]:
                        best = (nl, f, d)
                except Exception as e:
                    logger.debug(f"Error in SlackPlaceTool._nearest_node: {e}")
        return best

    def _nearest_cable_endpoint(self, pt, tolerance):
        """
        Find the nearest cable endpoint to a point.

        Returns:
            Tuple of (layer, feature, side, endpoint, distance)
            side is 'od' (FROM) or 'do' (TO)
        """
        best = (None, None, None, None, None)

        for kl in self._iter_cable_layers():
            for f in kl.getFeatures():
                geom = f.geometry()
                line = geom.asPolyline()
                if not line:
                    parts = geom.asMultiPolyline()
                    if parts:
                        line = parts[0]
                if not line:
                    continue

                ends = [QgsPointXY(line[0]), QgsPointXY(line[-1])]
                labels = ["od", "do"]  # FROM, TO in Serbian

                for lbl, ep in zip(labels, ends):
                    d = QgsPointXY(ep).distance(pt)
                    if (best[4] is None or d < best[4]) and d <= tolerance:
                        best = (kl, f, lbl, ep, d)

        return best

    def _nearest_cable_on_line(self, pt, tolerance):
        """
        Find the nearest cable to a point (anywhere on the line).

        Returns:
            Tuple of (layer, feature, distance) or (None, None, None)
        """
        best = (None, None, None)

        for kl in self._iter_cable_layers():
            for f in kl.getFeatures():
                d = f.geometry().distance(QgsGeometry.fromPointXY(pt))
                if d <= tolerance and (best[2] is None or d < best[2]):
                    best = (kl, f, d)

        return best

    def _resolve(self, point):
        """Where a slack clicked at ``point`` would actually go.

        One resolution for both the preview and the click, so what the
        indicator promises is what gets written.

        Returns:
            Tuple of (layer, feature, side, place_point). ``side`` is 'od' or
            'do' for a cable end, 'sredina' for mid-span. All four are None when
            no cable is in reach.
        """
        tolerance = self.canvas.mapUnitsPerPixel() * 20

        (layer, feat, side, endpoint, _d) = self._nearest_cable_endpoint(point, tolerance)
        if layer and feat:
            return layer, feat, side, QgsPointXY(endpoint)

        (layer, feat, _d) = self._nearest_cable_on_line(point, tolerance)
        if layer and feat:
            # The slack belongs on the cable. The click itself was written
            # before, which put a mid-span slack wherever the cursor happened
            # to be -- up to the whole tolerance away from its own cable.
            squared, projected, _after, _which = feat.geometry().closestSegmentWithContext(point)
            place = QgsPointXY(projected) if squared >= 0 else QgsPointXY(point)
            return layer, feat, "sredina", place

        return None, None, None, None

    def canvasMoveEvent(self, event):
        """Preview the position the click will use."""
        point = self.toMapCoordinates(event.pos())
        layer, feat, side, place = self._resolve(point)
        if place is None:
            self.snapper.clear()
            return
        # A cable end is a vertex; mid-span is a point on a segment. The two get
        # different QGIS indicator icons, and showing the vertex icon mid-span
        # would promise a vertex lock that is not what the click does.
        self.snapper.show(snap_match(place, layer=layer, fid=int(feat.id()),
                                     distance=point.distance(place),
                                     on_edge=(side == "sredina")))

    def canvasReleaseEvent(self, event):
        """Handle mouse release - place slack point."""
        p = self.toMapCoordinates(event.pos())

        kl, kf, strana_val, place_pt = self._resolve(p)

        cable_layer_id = kl.id() if kl else None
        cable_fid = int(kf.id()) if kf else None

        if cable_layer_id is None:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Optical slacks",
                "No cable found nearby."
            )
            return

        # Determine location type based on nearest node
        (nl, nf, nd) = self._nearest_node(place_pt)
        lok = self.params.get("lokacija", "Auto")

        if lok == "Auto":
            if nl and nf:
                lok = "Stub" if nl.name() in ("Poles", "Stubovi") else "OKNO"
            else:
                lok = "Objekat"

        # Get or create slack layer
        # Issue #2: Handle both main plugin (_ensure_slack_layer) and SlackManager (ensure_slack_layer)
        vl = None
        if self.plugin:
            if hasattr(self.plugin, '_ensure_slack_layer'):
                vl = self.plugin._ensure_slack_layer()
            elif hasattr(self.plugin, 'ensure_slack_layer'):
                vl = self.plugin.ensure_slack_layer()

        if vl is None:
            # Fallback: find existing slack layer
            for lyr in QgsProject.instance().mapLayers().values():
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and  # noqa: W504
                        lyr.name() in ("Opticke_rezerve", "Optical slacks", "Optical slack")):
                    vl = lyr
                    break

            if vl is None:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Optical slacks",
                    "Slack layer not found!"
                )
                return

        # Create feature
        f = QgsFeature(vl.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(place_pt)))
        f["tip"] = self.params.get("tip", "Terminal")
        f["duzina_m"] = int(self.params.get("duzina_m", 20))
        f["lokacija"] = lok
        f["cable_layer_id"] = cable_layer_id
        f["cable_fid"] = cable_fid
        f["strana"] = strana_val or "sredina"

        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(f)
        except Exception as e:
            logger.debug(f"Failed to set uuid on slack feature: {e}")

        vl.startEditing()
        vl.addFeature(f)
        vl.commitChanges()
        vl.triggerRepaint()

        # Record for undo (v1.2 — Feature 2)
        try:
            if self.plugin and hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                self.plugin.undo_manager.record_add(vl, f)
        except Exception as e:
            logger.debug(f"Error recording undo for slack: {e}")

        # Recompute slack for the cable
        # Issue #2: Handle both main plugin (_recompute_slack_for_cable) and SlackManager (recompute_slack_for_cable)
        try:
            if self.plugin:
                if hasattr(self.plugin, '_recompute_slack_for_cable'):
                    self.plugin._recompute_slack_for_cable(cable_layer_id, cable_fid)
                elif hasattr(self.plugin, 'recompute_slack_for_cable'):
                    self.plugin.recompute_slack_for_cable(cable_layer_id, cable_fid)
        except Exception as e:
            logger.debug(f"Error in SlackPlaceTool.canvasReleaseEvent: {e}")

        try:
            self.iface.messageBar().pushInfo("Optical slacks", "Slack saved.")
        except Exception as e:
            logger.debug(f"Error in SlackPlaceTool.canvasReleaseEvent: {e}")

    def keyPressEvent(self, event):
        """Handle ESC key to cancel tool."""
        if event.key() == Qt.Key.Key_Escape:
            self.snapper.clear()
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in SlackPlaceTool.keyPressEvent: {e}")

    def canvasPressEvent(self, event):
        """Handle right-click to cancel tool."""
        if event.button() == Qt.MouseButton.RightButton:
            self.snapper.clear()
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in SlackPlaceTool.canvasPressEvent: {e}")


__all__ = ['SlackPlaceTool']
