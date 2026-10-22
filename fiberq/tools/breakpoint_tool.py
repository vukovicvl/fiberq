"""
FiberQ v2 - Breakpoint Tool

Tool for splitting routes at a click point.
"""

import math

from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP

from .base import (
    Qt, QColor, QMessageBox,
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsWkbTypes, QgsRubberBand,
    QgsMapToolEmitPoint
)

from ..utils.errors import OperationErrors, add_and_save, check_commit
from ..utils.geometry import held_by_its_box
from ..utils.spatial import features_within
# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)

#: The split's user-facing strings, in the FiberQTools context.
_SPLIT_TITLE = QT_TRANSLATE_NOOP('FiberQTools', "Split route")
_SPLIT_REFUSED = QT_TRANSLATE_NOOP(
    'FiberQTools', "the layer refused the split, so the route was left as it was")
_SPLIT_NOT_EDITABLE = QT_TRANSLATE_NOOP(
    'FiberQTools', "the layer could not be opened for editing again to remove the original route")
_SPLIT_NOT_REMOVED = QT_TRANSLATE_NOOP(
    'FiberQTools', "the layer would not remove the original route")
_SPLIT_LEFTOVER = QT_TRANSLATE_NOOP(
    'FiberQTools',
    "The two halves were saved, but the original route could not be removed. Delete it by hand so"
    " the network is not counted twice.")
_SPLIT_UNSAVED = QT_TRANSLATE_NOOP(
    'FiberQTools',
    "The Route layer was already in edit mode, so this split is not saved yet. Use Layer > Save"
    " Layer Edits when you are ready.")

#: What _write_split managed to do, as RouteManager._write_merged_route says it.
_SAVED = 'saved'
_IN_BUFFER = 'in-buffer'
_NOT_WRITTEN = 'not-written'
_DUPLICATED = 'duplicated'


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
        self.rubber = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.rubber.setColor(QColor(0, 255, 0))
        self.rubber.setWidth(10)

        # Snap info for the current position
        self.snap_info = None

    @staticmethod
    def _store_lengths(route_layer, feat) -> float:
        """Fill a new segment's length fields from its geometry, before it is added.

        Computed here rather than left to the live length sync on purpose: the
        new half of a split arrives through ``featureAdded``, and a hook that
        writes from there segfaults QGIS on redo (see ``core/length_sync.py``).
        The arithmetic itself belongs to ``core.length_manager.length_values``,
        so a split and a recalculation cannot disagree about ``duzina_km``.

        Returns the metre value it stored, which the confirmation dialog shows.
        """
        from ..core.length_manager import length_field_for, length_values
        values = length_values(feat, route_layer)
        for name, value in values.items():
            feat.setAttribute(name, value)
        field = length_field_for(route_layer)
        return float(values.get(field, 0.0)) if field else 0.0

    @staticmethod
    def _write_split(route_layer, original_fid, halves, errors):
        """Save the two halves, then remove the route they replace.

        Returns ``_SAVED``, ``_IN_BUFFER`` (the user's own edit session took the
        split, unsaved), ``_NOT_WRITTEN`` (nothing changed) or ``_DUPLICATED``
        (the halves are saved and so is the original).

        **The halves are committed before the original is deleted** -- the
        order RouteManager._write_merged_route uses, for the same reason. A
        GeoPackage commit is not atomic across operations: with an insert
        refused by a trigger, the old one-session code had its delete succeed
        and its two inserts refused, so the route vanished from the file while
        the modal said "The route has been split!" (measured on 4.2.3 and
        3.40.15, two rows to one). The worst a refusal can now cost is a
        duplicate the user can see and delete.

        A session the user already had open takes the whole split, unsaved, in
        one edit command, as a merge does: committing it would save their own
        unsaved work too, and an original that only their buffer holds would
        change its id under the delete.
        """
        name = route_layer.name()
        if route_layer.isEditable():
            route_layer.beginEditCommand(QCoreApplication.translate('FiberQTools', _SPLIT_TITLE))
            if all(route_layer.addFeature(half) for half in halves) and route_layer.deleteFeature(original_fid):
                route_layer.endEditCommand()
                return _IN_BUFFER
            # Undoes this split's own edits and nothing else of the user's.
            route_layer.destroyEditCommand()
            errors.add(name, QCoreApplication.translate('FiberQTools', _SPLIT_REFUSED))
            return _NOT_WRITTEN

        if not add_and_save(route_layer, halves, errors):
            # The original is untouched on disk.
            return _NOT_WRITTEN

        # The halves are in the file. Only now the original.
        if not route_layer.startEditing():
            errors.add(name, QCoreApplication.translate('FiberQTools', _SPLIT_NOT_EDITABLE))
            return _DUPLICATED
        if not route_layer.deleteFeature(original_fid):
            errors.add(name, QCoreApplication.translate('FiberQTools', _SPLIT_NOT_REMOVED))
            route_layer.rollBack()
            return _DUPLICATED
        if not check_commit(route_layer, errors):
            return _DUPLICATED
        return _SAVED

    def _find_route_layer(self):
        """Find the Route layer in the project."""
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                lyr.name() in ('Route', 'Trasa') and  # noqa: W504
                    lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry):
                return lyr
        return None

    def canvasMoveEvent(self, event):
        """Update snap indicator as mouse moves."""
        point = self.toMapCoordinates(event.pos())

        route_layer = self._find_route_layer()
        if route_layer is None or route_layer.featureCount() == 0:
            self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.snap_info = None
            return

        tolerance = self.canvas.mapUnitsPerPixel() * 10
        min_dist = None
        snapped_point = None
        min_feat = None
        min_geom = None
        min_seg_idx = None

        # Find closest point on any route feature: those whose box comes within
        # the tolerance of the cursor, in the order the whole layer hands them
        # out (utils.spatial.features_within, WP4 4.1 item PF-5), or the whole
        # layer where a box cannot answer exactly. Only a route within the
        # tolerance is used, and every such route is among them.
        near = features_within(route_layer, point, tolerance)
        for feat in (route_layer.getFeatures() if near is None else near):
            geom = feat.geometry()
            squared, snap, vertex_after, seg_idx = geom.closestSegmentWithContext(point)
            if squared < 0:
                # No segment: an empty or point geometry on the route layer.
                continue
            # closestSegmentWithContext returns a SQUARED distance. Comparing it
            # against a linear tolerance below made the real snap radius
            # sqrt(10 / mapUnitsPerPixel) pixels instead of the 10 it reads as.
            dist = math.sqrt(squared)
            if min_dist is None or dist < min_dist:
                # A route a box query can miss -- a coordinate that is not a
                # finite number, a one-vertex part, an arc QGIS cannot box -- is
                # skipped (utils.geometry.held_by_its_box). Asked only of a route
                # that would win within the tolerance: one beyond it is never used.
                if not dist >= tolerance and not held_by_its_box(geom, tolerance / 2):
                    continue
                min_dist = dist
                snapped_point = snap
                min_feat = feat
                min_geom = geom
                min_seg_idx = seg_idx

        if snapped_point and min_dist < tolerance:
            self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.rubber.addPoint(snapped_point)
            self.snap_info = {
                'feat': min_feat,
                'geom': min_geom,
                'point': snapped_point,
                'seg_idx': min_seg_idx,
                'dist': min_dist
            }
        else:
            self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.snap_info = None

    def canvasReleaseEvent(self, event):
        """Handle mouse release - split route if valid location."""
        # Right click = cancel tool
        if event.button() == Qt.MouseButton.RightButton:
            self.snap_info = None
            self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
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
            self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
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
                self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
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
                self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
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
                self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
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
            self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
            return

        # Create first segment
        feat1 = QgsFeature(route_layer.fields())
        feat1.setGeometry(geom1)
        feat1.setAttribute('naziv', naziv + "_a")
        feat1.setAttribute('tip_trase', tip_trase)
        duzina_m1 = self._store_lengths(route_layer, feat1)

        # Create second segment
        feat2 = QgsFeature(route_layer.fields())
        feat2.setGeometry(geom2)
        feat2.setAttribute('naziv', naziv + "_b")
        feat2.setAttribute('tip_trase', tip_trase)
        duzina_m2 = self._store_lengths(route_layer, feat2)

        # Phase 0.1: Set UUID for FiberQ Designer (new segments get new UUIDs)
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(feat1)
            set_feature_uuid(feat2)
        except Exception as e:
            logger.debug(f"could not set uuid on new route segments: {e}")

        # Perform the split: see _write_split for the order, and why. Every
        # answer used to be thrown away, and the modal below said the route had
        # been split over a file that had just lost it.
        outcome = _NOT_WRITTEN
        with OperationErrors(QCoreApplication.translate('FiberQTools', _SPLIT_TITLE),
                             self.iface, absorb=True) as errors:
            outcome = self._write_split(route_layer, min_feat.id(), [feat1, feat2], errors)

        # Re-apply styling
        if self.plugin and outcome != _NOT_WRITTEN:
            self.plugin.stylize_route_layer(route_layer)

        self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
        if outcome == _DUPLICATED:
            # The one failure that needs more than the message bar: the halves
            # ARE saved, and until the original goes the route is counted twice.
            QMessageBox.warning(self.iface.mainWindow(), "Split route",
                                QCoreApplication.translate('FiberQTools', _SPLIT_LEFTOVER))
            return
        if outcome == _NOT_WRITTEN:
            return
        message = (f"The route has been split!\n"
                   f"First part: {duzina_m1:.2f} m, second part: {duzina_m2:.2f} m.")
        if outcome == _IN_BUFFER:
            message += "\n" + QCoreApplication.translate('FiberQTools', _SPLIT_UNSAVED)
        QMessageBox.information(self.iface.mainWindow(), "Split route", message)

    def deactivate(self):
        """Clean up when tool is deactivated."""
        self.rubber.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.snap_info = None
        super().deactivate()


__all__ = ['BreakpointTool']
