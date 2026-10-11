"""
FiberQ v2 - Slack Tool

Tool for placing optical slack (reserve) points on cables.
"""

import math

from .base import (
    Qt, QMessageBox,
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsWkbTypes,
    QgsMapTool,
    PlacementSnapper, snap_match
)

from qgis.core import QgsGeometryUtils
from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP

from ..core import interchange_fields as fm
from ..core.slack_manager import slack_operation
from ..i18n import safe_format
from ..models.schema import canonical_layer_name
# Phase 5.2: Logging
from ..utils.errors import OperationErrors, check_commit, describe
from ..utils.geometry import line_parts
from ..utils.logger import get_logger
from ..utils.spatial import features_near
logger = get_logger(__name__)

#: How many times the nearest-node box may grow, fourfold each time, before
#: the whole layer is read instead: 4**11 times even 10 m is past the
#: circumference of the Earth.
_NODE_SEARCH_STEPS = 12


def _cable_lines(geom, tolerance):
    """The lines of a cable a slack can go on, or ``[]`` when it is not one.

    Every part with a vertex has to be a line -- two or more of them -- and
    every vertex a real number. Anything else is invalid geometry that GEOS
    cannot measure consistently: -1 for a one-vertex line, 0.0 from
    everywhere for a cable whose only part has one vertex, and NaN or
    infinity wherever a vertex is not a number. Each of those made one broken
    cable the cable of every click. A GeoPackage does not even return such a cable to a box query: a
    one-vertex part fails OGR's own intersection test, and a NaN first vertex
    leaves its R-tree entry at 0,0,0,0 (measured on 3.22.16, 3.44.15 and
    4.2.3). So both cable searches skip it, which also lets a search that
    reads only the cables near the click answer what the whole scan does.

    A curve also has to be one QGIS can box. QGIS boxes an arc from the
    circle through its three points, and three points in a row have none:
    ``circleCenterRadius`` answers radius -1 and never sets the centre the
    box is then built from. ``CircularString (0 0, 200 0, 100 0)`` got the
    box (-1, -1, 100, 0) in one run and one holding its whole line in
    another, while GEOS measures it out to x = 200; so such an arc is not a
    cable. Every other arc has to lie in its own box, give or take half the
    snap ``tolerance``: a box holds its arc to within 2e-6 of the arc's size
    (20,000 random arcs, 3.22.16 to 4.2.3), except on 3.22 for an arc that
    starts exactly at (0, 0): 3.22 takes the rectangle (0, 0, 0, 0) its box
    is grown from for an empty one, and drops that point. A memory layer
    keeps a curve digitised on it as a curve, whatever its declared type.

    An empty part is no part at all: GEOS and every box leave it out.
    """
    lines = line_parts(geom)
    if not lines or _has_a_one_vertex_part(geom):
        return []
    if not all(math.isfinite(c) for line in lines for p in line for c in (p.x(), p.y())):
        return []
    if QgsWkbTypes.isCurvedType(geom.wkbType()):
        if _has_an_arc_without_a_circle(geom.constGet()):
            return []
        box = geom.boundingBox()
        slack = tolerance / 2
        low_x, high_x = box.xMinimum() - slack, box.xMaximum() + slack
        low_y, high_y = box.yMinimum() - slack, box.yMaximum() + slack
        if not all(low_x <= p.x() <= high_x and low_y <= p.y() <= high_y for line in lines for p in line):
            return []
    return lines


def _has_a_one_vertex_part(geom):
    """True when a part of ``geom`` has exactly one vertex (see ``_cable_lines``)."""
    shape = geom.constGet()
    if QgsWkbTypes.isMultiType(geom.wkbType()):
        return any(shape.geometryN(i).nCoordinates() == 1 for i in range(shape.numGeometries()))
    return shape.nCoordinates() == 1


def _has_an_arc_without_a_circle(curve):
    """True when an arc of ``curve`` has its three points in a row (see ``_cable_lines``)."""
    kind = QgsWkbTypes.displayString(QgsWkbTypes.flatType(curve.wkbType()))
    if kind == "CircularString":
        points = curve.points()
        return any(QgsGeometryUtils.circleCenterRadius(*points[i:i + 3])[0] < 0
                   for i in range(0, len(points) - 2, 2))
    if kind == "CompoundCurve":
        return any(_has_an_arc_without_a_circle(curve.curveAt(i)) for i in range(curve.nCurves()))
    if kind.startswith("Multi"):
        return any(_has_an_arc_without_a_circle(curve.geometryN(i)) for i in range(curve.numGeometries()))
    return False


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

        A node whose point is not finite is not a node to measure from. A NaN
        one met first used to make ``best`` NaN, and ``d < NaN`` is never true,
        so that one node decided "Pole" or "Manhole" for every slack.

        Returns:
            Tuple of (layer, feature, distance) or (None, None, None)
        """
        best = (None, None, None)
        for nl in self._iter_node_layers():
            for f in self._nodes_to_measure(nl, pt):
                p = self._node_point(f)
                if p is None:
                    continue
                d = p.distance(pt)
                if best[2] is None or d < best[2]:
                    best = (nl, f, d)
        return best

    @staticmethod
    def _node_point(feature):
        """The node's point as the scan has always read it, or None when it has none.

        ``asPoint()`` is still the call, so each QGIS keeps its own answer: a
        single-part MultiPoint reads on 3.44 and 4.2 but raises on 3.22.
        """
        p = None
        try:
            p = feature.geometry().asPoint()
        except Exception as e:
            logger.debug(f"Error in SlackPlaceTool._nearest_node: {e}")
        if p is None or not (math.isfinite(p.x()) and math.isfinite(p.y())):
            return None
        return QgsPointXY(p)

    def _nodes_to_measure(self, layer, pt):
        """The nodes of one layer the nearest-node scan has to measure (WP4 PF-4).

        Every node the whole layer could offer as its nearest, in the whole
        scan's order -- usually a handful near ``pt`` rather than every pole in
        the project. The box reaches twice the reach on each side and grows
        until it holds a node within the reach: every node that near or
        nearer lies inside it then, so the nearest and every tie with it are
        among the nodes returned. Only the nearest node's layer and its
        presence are ever used (Stub, OKNO or Objekat), and a strict ``<``
        across layers in the scan's layer order keeps the layer the whole scan
        picked. When a box cannot answer exactly, or no node turns up, the
        whole layer is read, as before -- and also as soon as a box holds
        nodes but none whose point can be read (on 3.22 ``asPoint()`` reads no
        MultiPoint): the boxes would only grow round them, each a read.

        A count of 0 is not taken at its word, because QGIS keeps it from the
        last time it looked: it stays 0 when another layer on the same table,
        or another program, adds poles, and it drifts in transaction groups
        when a delete is undone (code review, 3.22.16 to 4.2.3). The whole
        layer is read then, which costs nothing if it really is empty.
        """
        count = layer.featureCount()
        if count == 0:
            return layer.getFeatures()
        reach = self._first_reach(layer, count)
        for _ in range(_NODE_SEARCH_STEPS):
            found = features_near(layer, pt, 2.0 * reach)
            if found is None:
                break
            points = [self._node_point(f) for f in found]
            if any(p is not None and p.distance(pt) <= reach for p in points):
                return found
            if found and all(p is None for p in points):
                break
            reach *= 4.0
        return layer.getFeatures()

    def _first_reach(self, layer, count):
        """Where the nearest-node box starts: the layer's own spacing, or the snap reach.

        Only a starting guess -- the box grows until it is right -- so it costs
        nothing in correctness. The square root of the area per node is about
        twice the distance to the nearest of randomly placed nodes, so most
        searches end at the first box, whatever the canvas zoom.
        """
        extent = layer.extent()
        area = extent.width() * extent.height()
        if count > 0 and math.isfinite(area) and area > 0:
            return math.sqrt(area / count)
        return self._tolerance()

    def _tolerance(self):
        """The snap reach, 20 px in map units: what a click is allowed to miss by."""
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return 1.0
        return canvas.mapUnitsPerPixel() * 20

    def _cables_near(self, layer, pt, tolerance):
        """The cables of one layer a search within ``tolerance`` of ``pt`` must test (PF-4).

        Every valid cable (``_cable_lines``) with an end, or a GEOS distance,
        within the tolerance has its box within twice it, the margin covering
        GEOS's rounding (PF-2); a cable that is not a valid line is skipped by
        both searches, so whether a box finds it does not matter. In the whole
        scan's order, or the whole layer when a box cannot answer exactly.
        """
        found = features_near(layer, pt, 2.0 * tolerance)
        return layer.getFeatures() if found is None else found

    def _nearest_cable_endpoint(self, pt, tolerance):
        """
        Find the nearest cable endpoint to a point.

        Each part of a multipart cable offers its own two ends. The vertices
        come from ``line_parts`` because ``asPolyline()`` raises ``TypeError``
        on a MultiLineString rather than answering an empty list (FU-10), and
        ``ValueError`` on a cable with no geometry: one such cable anywhere in
        the project used to stop this search for every other cable. A cable
        that is not a valid line offers no ends (``_cable_lines``).

        Returns:
            Tuple of (layer, feature, side, endpoint, distance)
            side is 'od' (FROM) or 'do' (TO)
        """
        best = (None, None, None, None, None)

        for kl in self._iter_cable_layers():
            for f in self._cables_near(kl, pt, tolerance):
                for line in _cable_lines(f.geometry(), tolerance):
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

        A cable that is not a valid line is skipped (``_cable_lines``). GEOS
        measures an empty line, or one whose only part has one vertex, as 0.0
        from everything and cannot measure a one-vertex line at all (-1), and
        either of those is "within the tolerance" of every click, so such a
        cable used to become the cable of every mid-span slack.

        Returns:
            Tuple of (layer, feature, distance) or (None, None, None)
        """
        best = (None, None, None)
        probe = QgsGeometry.fromPointXY(pt)

        for kl in self._iter_cable_layers():
            for f in self._cables_near(kl, pt, tolerance):
                geom = f.geometry()
                if not _cable_lines(geom, tolerance):
                    continue
                d = geom.distance(probe)
                if d < 0:
                    continue
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
