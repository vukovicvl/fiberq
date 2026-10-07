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

from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP

from ..core import interchange_fields as fm
from ..core.slack_manager import slack_operation
from ..i18n import safe_format
from ..models.schema import canonical_layer_name
# Phase 5.2: Logging
from ..utils.errors import OperationErrors, check_commit, describe
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
        """Place one slack point where the user clicked.

        A Qt slot, so it must not raise: anything that escapes reaches QGIS's
        "unhandled Python error" dialog, which tells the user about a traceback
        instead of about their cable. ``absorb=True`` turns that into the same
        one-line report as every other failure here.
        """
        with OperationErrors(slack_operation(), self.iface, absorb=True) as errors:
            self._place_slack(self.toMapCoordinates(event.pos()), errors)

    def _place_slack(self, p, errors) -> None:
        """The body of :meth:`canvasReleaseEvent`, free to raise."""
        kl, kf, strana_val, place_pt = self._resolve(p)

        if kl is None:
            QMessageBox.information(
                self.iface.mainWindow(),
                slack_operation(),
                QCoreApplication.translate('FiberQSlack', "No cable found nearby.")
            )
            return
        cable_layer_id = kl.id()
        cable_fid = int(kf.id())

        # Determine location type based on nearest node
        (nl, nf, nd) = self._nearest_node(place_pt)
        lok = self.params.get("lokacija", "Auto")

        if lok == "Auto":
            if nl and nf:
                lok = "Stub" if nl.name() in ("Poles", "Stubovi") else "OKNO"
            else:
                lok = "Objekat"

        vl = self._slack_layer()
        if vl is None:
            errors.add(None, QCoreApplication.translate(
                'FiberQSlack', "there is no optical slack layer to write to"))
            return

        # R9: on a pre-1.0 project the pair is kabl_layer_id / kabl_fid.
        # Writing the modern name into such a layer raises KeyError, which is
        # how clicking a cable in an old project used to end the operation.
        layer_id_field, fid_field = fm.cable_link_fields(vl.fields().names())
        if not layer_id_field:
            src = QT_TRANSLATE_NOOP(
                'FiberQSlack',
                "'{layer}' has no cable reference columns, so no slack was created")
            errors.add(vl.name(), safe_format(
                QCoreApplication.translate('FiberQSlack', src), src, layer=vl.name()))
            return

        # Create feature
        f = QgsFeature(vl.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(place_pt)))
        f["tip"] = self.params.get("tip", "Terminal")
        f["duzina_m"] = int(self.params.get("duzina_m", 20))
        f["lokacija"] = lok
        f[layer_id_field] = cable_layer_id
        f[fid_field] = cable_fid
        f["strana"] = strana_val or "sredina"

        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(f)
        except (AttributeError, ImportError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            # Without an identity the slack cannot travel into a bundle or be
            # matched on the way back, so it is reported rather than shrugged off.
            errors.add(None, f"could not give the slack an identity: {describe(exc)}")

        vl.startEditing()
        if not vl.addFeature(f):
            errors.add(vl.name(), QCoreApplication.translate(
                'FiberQSlack', "the slack point was rejected by the layer"))
            return
        if not check_commit(vl, errors):
            return
        vl.triggerRepaint()

        # Record for undo (v1.2 — Feature 2)
        undo_mgr = getattr(self.plugin, 'undo_manager', None) if self.plugin else None
        if undo_mgr:
            try:
                undo_mgr.record_add(vl, f)
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                # The slack is saved; only its undo entry is missing.
                logger.warning(f"Could not record the new slack for undo: {exc}")

        self._recompute(cable_layer_id, cable_fid, errors)

        if not errors.failed:
            self.iface.messageBar().pushInfo(
                slack_operation(),
                QCoreApplication.translate('FiberQSlack', "Slack saved."))

    def _slack_layer(self):
        """The layer to write the slack into, or None.

        Issue #2: the plugin exposes this as ``_ensure_slack_layer`` and the
        SlackManager as ``ensure_slack_layer``.
        """
        if self.plugin:
            for name in ('_ensure_slack_layer', 'ensure_slack_layer'):
                maker = getattr(self.plugin, name, None)
                if maker is not None:
                    vl = maker()
                    if vl is not None:
                        return vl
                    break
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.isValid() and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and canonical_layer_name(lyr.name()) == "Optical slack":
                return lyr
        return None

    def _recompute(self, cable_layer_id, cable_fid, errors) -> None:
        """Re-total the cable's slack, reporting into this operation.

        Issue #2: the name differs between the plugin and the SlackManager, and
        only the manager's own signature takes the collector.
        """
        if not self.plugin:
            return
        for name in ('_recompute_slack_for_cable', 'recompute_slack_for_cable'):
            recompute = getattr(self.plugin, name, None)
            if recompute is None:
                continue
            try:
                recompute(cable_layer_id, cable_fid, errors)
            except TypeError:
                # An older wrapper that does not pass the collector through.
                recompute(cable_layer_id, cable_fid)
            return

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
