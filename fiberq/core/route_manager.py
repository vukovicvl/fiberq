# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Route Manager.

This module provides route management functionality:
- Creating and styling route layers
- Merging routes
- Importing routes from files
- Changing route types
- Path building across route networks

Phase 5.2: Added logging infrastructure
"""

from typing import Optional, List, Tuple

from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP, QVariant, Qt
from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog, QFileDialog

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsSymbol,
    QgsUnitTypes,
    QgsCoordinateTransform,
)

# Phase 5.2: Logging
from ..i18n import safe_format
from ..utils.errors import OperationErrors, check_commit, describe
from ..utils import file_filters
from ..utils.geometry import line_parts, transformed
from ..utils.logger import get_logger
from ..utils.measure import ground_length
logger = get_logger(__name__)


def _route_import() -> str:
    """Title on the message-bar entries the route importer pushes."""
    src = QT_TRANSLATE_NOOP('FiberQRoutes', "Import route")
    return QCoreApplication.translate('FiberQRoutes', src)


def _merge_routes() -> str:
    """Title on the message-bar entries a merge pushes."""
    src = QT_TRANSLATE_NOOP('FiberQRoutes', "Merge routes")
    return QCoreApplication.translate('FiberQRoutes', src)


#: How far apart two route ends may be and still count as touching, in layer
#: units. This is float noise, NOT a domain tolerance: routes that share a
#: vertex measure exactly 0.0 apart (measured on 3.22.16, 3.44.15 and 4.0.3),
#: so there is no judgement to make about how big a real gap has to be before
#: it is worth mentioning. Every gap is worth mentioning.
_JOIN_EPSILON = 1e-9

#: The merge's user-facing strings. Held as module constants because each one is
#: used twice -- once as the QT_TRANSLATE_NOOP source pylupdate6 extracts, once
#: as safe_format's fallback if a translator renames a placeholder -- and a
#: literal repeated at both sites is a literal that drifts.
_MERGED_OK = QT_TRANSLATE_NOOP(
    'FiberQRoutes', "Route has been created!\nLength: {length} m ({km} km)\nType: {type}")
_MERGED_NAME = QT_TRANSLATE_NOOP('FiberQRoutes', "Merged route")
_MERGED_SKIPPED = QT_TRANSLATE_NOOP(
    'FiberQRoutes', "{count} of the selected routes had no line to merge and were left alone.")
_MERGED_GAP = QT_TRANSLATE_NOOP(
    'FiberQRoutes',
    "The routes were not touching. A straight segment {gap} m long was added to join them, so the"
    " merged route is longer than the routes it replaces. Undo if that is not what you wanted.")
_MERGED_UNSAVED = QT_TRANSLATE_NOOP(
    'FiberQRoutes',
    "The Route layer was already in edit mode, so this merge is not saved yet. Use Layer > Save"
    " Layer Edits when you are ready.")
_UNUSABLE = QT_TRANSLATE_NOOP(
    'FiberQRoutes', "{count} of the selected routes had no line in them and could not be merged")
_NOT_EDITABLE = QT_TRANSLATE_NOOP(
    'FiberQRoutes', "the Route layer could not be opened for editing, so nothing was changed")
_MERGE_REFUSED = QT_TRANSLATE_NOOP(
    'FiberQRoutes',
    "the layer refused the merged route, so the routes it would have replaced were left alone")
_LEFTOVER = QT_TRANSLATE_NOOP(
    'FiberQRoutes',
    "the merged route was saved, but {count} of the routes it replaces could not be removed. Delete"
    " them by hand so the network is not counted twice")
_NO_COLUMNS = QT_TRANSLATE_NOOP(
    'FiberQRoutes',
    "the Route layer has no {columns} column, so the merged route was saved without it. Its"
    " geometry is correct; its length and type are not recorded")
#: What :meth:`RouteManager._write_merged_route` managed to do. Four outcomes
#: and not a bool, because "saved" and "the merged route is on disk but so are
#: the routes it replaces" need different things said to the user, and a bool
#: forced the second one into the error collector -- which renders the first few
#: reasons and COUNTS the rest, so the one sentence the user had to act on was
#: the one that got counted.
_SAVED = 'saved'
_IN_BUFFER = 'in-buffer'
_NOT_WRITTEN = 'not-written'
_DUPLICATED = 'duplicated'

_CMD_ADD = QT_TRANSLATE_NOOP('FiberQRoutes', "Add merged route")
_CMD_REMOVE = QT_TRANSLATE_NOOP('FiberQRoutes', "Remove merged routes")


# Route type options and labels
ROUTE_TYPE_OPTIONS = ["vazdusna", "podzemna", "kroz objekat"]

ROUTE_TYPE_LABELS = {
    "vazdusna": "Aerial",
    "podzemna": "Underground",
    "kroz objekat": "Through the object",
}

ROUTE_LABEL_TO_CODE = {v: k for k, v in ROUTE_TYPE_LABELS.items()}


class RouteManager:
    """Manager for route/trasa operations."""

    def __init__(self, iface, style_manager=None):
        """
        Initialize RouteManager.

        Args:
            iface: QGIS interface
            style_manager: Optional StyleManager instance
        """
        self.iface = iface
        self.style_manager = style_manager

    # -------------------------------------------------------------------------
    # Layer alias methods
    # -------------------------------------------------------------------------

    def apply_route_field_aliases(self, layer: QgsVectorLayer) -> None:
        """Apply English field aliases and value map to a route layer."""
        try:
            from ..utils.field_aliases import apply_route_field_aliases
            apply_route_field_aliases(layer)
        except Exception as e:
            logger.debug(f"Error in RouteManager.apply_route_field_aliases: {e}")

    # -------------------------------------------------------------------------
    # Styling
    # -------------------------------------------------------------------------

    def stylize_route_layer(self, route_layer: QgsVectorLayer) -> None:
        """Apply route layer style."""
        # Apply aliases
        try:
            self.apply_route_field_aliases(route_layer)
        except Exception as e:
            logger.debug(f"Error in RouteManager.stylize_route_layer: {e}")

        # Try StyleManager first
        if self.style_manager:
            try:
                self.style_manager.stylize_route_layer(route_layer)
                return
            except Exception as e:
                logger.debug(f"Error in RouteManager.stylize_route_layer: {e}")

        # Fallback: inline implementation
        try:
            symbol = QgsSymbol.defaultSymbol(route_layer.geometryType())
            symbol_layer = symbol.symbolLayer(0)
            symbol_layer.setWidth(0.8)
            symbol_layer.setWidthUnit(QgsUnitTypes.RenderUnit.RenderMetersInMapUnits)
            symbol_layer.setPenStyle(Qt.PenStyle.DashLine)
            route_layer.renderer().setSymbol(symbol)
            route_layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in RouteManager.stylize_route_layer: {e}")

    # -------------------------------------------------------------------------
    # Path building helpers (delegates to utils modules)
    # -------------------------------------------------------------------------

    def round_key(self, pt: QgsPointXY, tol: float) -> Tuple[int, int]:
        """Round point coordinates for use as dict key."""
        from ..utils.geometry import round_key
        return round_key(pt, tol)

    def first_last_points_of_geom(self, geom: QgsGeometry) -> Tuple[Optional[QgsPointXY], Optional[QgsPointXY]]:
        """Get first and last points of a geometry."""
        from ..utils.geometry import get_first_last_points
        return get_first_last_points(geom)

    def build_path_across_network(self, route_layer: QgsVectorLayer,
                                  start_pt: QgsPointXY, end_pt: QgsPointXY,
                                  tol_units: float) -> Optional[List[QgsPointXY]]:
        """Route through ALL vertices (including breakpoints) without physically merging features.

        Returns list of QgsPointXY or None if no path exists in the network.
        """
        from ..utils.routing import build_path_across_network
        return build_path_across_network(route_layer, start_pt, end_pt, tol_units)

    def build_path_across_joined_routes(self, route_layer: QgsVectorLayer,
                                        start_pt: QgsPointXY, end_pt: QgsPointXY,
                                        tol_units: float) -> Optional[List[QgsPointXY]]:
        """Find path across joined routes at feature level."""
        from ..utils.routing import build_path_across_joined_routes
        return build_path_across_joined_routes(route_layer, start_pt, end_pt, tol_units)

    # -------------------------------------------------------------------------
    # Layer management helpers
    # -------------------------------------------------------------------------

    def _find_route_layer(self) -> Optional[QgsVectorLayer]:
        """Find existing Route layer."""
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route', 'Trasa') and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
                return lyr
        return None

    def _ensure_route_layer(self) -> QgsVectorLayer:
        """Find or create Route layer with required fields."""
        route_layer = self._find_route_layer()

        if route_layer is None:
            crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
            route_layer = QgsVectorLayer(f"LineString?crs={crs}", "Route", "memory")
            QgsProject.instance().addMapLayer(route_layer)

        # Ensure required fields exist
        self._ensure_route_fields(route_layer)
        return route_layer

    def _ensure_route_fields(self, route_layer: QgsVectorLayer) -> None:
        """Ensure route layer has all required fields.

        Does not open or close an edit session the caller did not ask for. This
        runs on the way to every Import route, including the usual case where
        the layer already has all four columns and there is nothing to do -- and
        it used to call startEditing() and commitChanges() unconditionally, so
        an import SAVED whatever the user had digitised and not saved, and
        dropped them out of edit mode. Measured on 3.44.15: one unsaved route in
        the buffer before, committed to the provider and the session closed
        after, with nothing said.

        The session is not touched at all now, because it never needed to be:
        every column here is added through ``dataProvider().addAttributes()``,
        which writes to the provider directly and bypasses the edit buffer. The
        commitChanges() was therefore never committing the fields -- they were
        already there -- it was only ever committing whatever else happened to be
        in the buffer, which is to say the user's work.
        """
        added_fields = []

        if route_layer.fields().indexFromName("naziv") == -1:
            route_layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
            added_fields.append("naziv")
        if route_layer.fields().indexFromName("duzina") == -1:
            route_layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
            added_fields.append("duzina")
        if route_layer.fields().indexFromName("duzina_km") == -1:
            route_layer.dataProvider().addAttributes([QgsField("duzina_km", QVariant.Double)])
            added_fields.append("duzina_km")
        if route_layer.fields().indexFromName("tip_trase") == -1:
            route_layer.dataProvider().addAttributes([QgsField("tip_trase", QVariant.String)])
            added_fields.append("tip_trase")

        if added_fields:
            route_layer.updateFields()

        # WP1b identity invariant: ensure the fiberq_uuid column exists on the
        # Route layer (both freshly created and found-existing layers reach here
        # via _ensure_route_layer), so the set_feature_uuid() calls at feature
        # creation actually stamp a value instead of silently no-opping.
        try:
            from ..utils.uuid_utils import ensure_uuid_field
            ensure_uuid_field(route_layer)
        except Exception as e:
            logger.debug(f"Error ensuring fiberq_uuid on route layer: {e}")

    def _ask_route_type(self, title: str = "Route type",
                        label: str = "Select route type:") -> Optional[str]:
        """Show dialog to select route type. Returns type code or None if cancelled."""
        items = [ROUTE_TYPE_LABELS.get(code, code) for code in ROUTE_TYPE_OPTIONS]
        tip_label, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            title,
            label,
            items,
            0, False
        )
        if not ok or not tip_label:
            return ROUTE_TYPE_OPTIONS[0]  # Default
        return ROUTE_LABEL_TO_CODE.get(tip_label, ROUTE_TYPE_OPTIONS[0])

    # -------------------------------------------------------------------------
    # Main route operations
    # -------------------------------------------------------------------------

    def create_route(self) -> None:
        """Create a route from selected poles/manholes."""
        # Collect selected features from Poles and Manholes layers
        selected_features = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and  # noqa: W504
                        lyr.name() in ('Poles', 'Stubovi', 'OKNA', 'Manholes')):
                    if lyr.selectedFeatureCount() > 0:
                        selected_features.extend(lyr.selectedFeatures())
            except Exception as e:
                logger.debug(f"Error in RouteManager.create_route: {e}")

        if len(selected_features) < 2:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "FiberQ",
                "Select at least two points (Pole/MH) for the route!"
            )
            return

        route_layer = self._ensure_route_layer()
        self.stylize_route_layer(route_layer)

        # Build coordinate list
        pts = [f.geometry().asPoint() for f in selected_features]
        if len(pts) == 2:
            coords = [QgsPointXY(pts[0]), QgsPointXY(pts[1])]
        else:
            # Order points by nearest neighbor
            start_pt = min(pts, key=lambda p: (p.x(), p.y()))
            coords = [QgsPointXY(start_pt)]
            remaining = [QgsPointXY(p) for p in pts if p != start_pt]
            while remaining:
                last = coords[-1]
                nearest = min(
                    remaining,
                    key=lambda p: QgsGeometry.fromPointXY(last).distance(QgsGeometry.fromPointXY(p))
                )
                coords.append(nearest)
                remaining.remove(nearest)

        line_geom = QgsGeometry.fromPolylineXY(coords)

        # Ask for route type
        tip_trase = self._ask_route_type()

        # Calculate length
        duzina_m = ground_length(line_geom, route_layer)
        duzina_km = round(duzina_m / 1000.0, 2)

        # Create feature
        route_feature = QgsFeature(route_layer.fields())
        route_feature.setGeometry(line_geom)
        route_feature.setAttribute("naziv", "Route {}".format(route_layer.featureCount() + 1))
        route_feature.setAttribute("duzina", duzina_m)
        route_feature.setAttribute("duzina_km", duzina_km)
        route_feature.setAttribute("tip_trase", tip_trase)

        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(route_feature)
        except Exception as e:
            logger.debug(f"Could not set feature uuid on route: {e}")

        route_layer.startEditing()
        route_layer.addFeature(route_feature)
        route_layer.commitChanges()

        # Record for undo (v1.2 — Feature 2)
        try:
            undo_mgr = getattr(self, 'undo_manager', None)
            if undo_mgr:
                undo_mgr.record_add(route_layer, route_feature)
        except Exception as e:
            logger.debug(f"Error recording undo for route: {e}")

        self.stylize_route_layer(route_layer)

        tip_label_display = ROUTE_TYPE_LABELS.get(tip_trase, tip_trase)
        QMessageBox.information(
            self.iface.mainWindow(),
            "FiberQ",
            f"Route has been created!\nLength: {duzina_m:.2f} m ({duzina_km:.2f} km)\nType: {tip_label_display}"
        )

    def merge_all_routes(self) -> None:
        """Merge the selected routes into one, and say what happened to them.

        WP4 4.2 item R7. Four separate things were wrong here, all measured on
        3.22.16, 3.44.15 and 4.0.3 through this entry point.

        **It crashed on a multipart route.** ``asPolyline()`` raises
        ``TypeError`` on a multipart line rather than answering an empty list,
        so the ``asMultiPolyline()`` fallback underneath was unreachable and the
        ``TypeError`` left the QAction slot -- ``FiberQPlugin.merge_all_routes``
        has no handler -- as QGIS's own unhandled-error dialog. An ESRI
        Shapefile line layer is multipart for *every* feature, single-part or
        not, so this was every shapefile Route layer, not an exotic shape. See
        :func:`utils.geometry.line_parts`.

        **It destroyed both routes and reported success.** The old code deleted
        the originals and added the merged route in one edit session, then
        discarded ``commitChanges()``. On a GeoPackage whose Route table refuses
        the insert, a commit is *partial*: measured, ``commitErrors()`` reads
        ``['SUCCESS: 2 feature(s) deleted.', 'ERROR: 1 feature(s) not added.']``
        and the table went from two rows to **zero** while the modal said
        "Route has been created! Length: 20.00 m". ``getFeatures()`` still
        answered "Merged route" because it reads through the edit buffer, so
        canvas and attribute table looked right until the project was reopened.

        So the order is now the other way round and that is the fix, not merely
        the report: the merged route is added and committed **first**, and the
        originals are removed only once it is safely on disk. A refusal now
        costs the user a duplicate they can see and delete, instead of two
        routes they cannot get back.

        **It invented a joining segment in silence.** The "Cannot merge into
        single line! Routes are not connected end-to-end." branch could never
        run: ``QgsGeometry.fromPolylineXY`` answers a single-part LineString for
        any list of points, so ``isMultipart()`` was always False there.
        Measured -- two routes 490 m apart merged into one 510 m route with a
        straight segment across the gap and a modal reporting "Length:
        510.00 m". The chaining loop knows the distance of every join it makes,
        so the gap is now reported as the fact it is. No tolerance is invented:
        routes meeting at a shared vertex measure exactly 0.0 apart.

        **It committed the user's own unsaved work.** ``startEditing()`` was
        unguarded, so a merge saved whatever else was in the layer's buffer.
        Same defect as the route importer's, fixed the same way: if this call
        did not open the editing session it does not commit one.
        """
        route_layer = self._find_route_layer()
        if route_layer is None:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Layer 'Route' is not found!")
            return

        self._ensure_route_fields(route_layer)

        selected_feats = route_layer.selectedFeatures()
        if len(selected_feats) < 2:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "FiberQ",
                "Select at least two routes to merge!"
            )
            return

        title = _merge_routes()
        with OperationErrors(title, self.iface) as errors:
            chain, gap_m, unusable = self._chain_selected_routes(selected_feats, errors)
            if chain is None:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "FiberQ",
                    "Not enough valid lines to merge!"
                )
                return

            geom = QgsGeometry.fromPolylineXY(chain)
            tip_trase = self._ask_route_type("Type of connected route")
            duzina_m = ground_length(geom, route_layer)
            duzina_km = round(duzina_m / 1000.0, 2)

            outcome = self._write_merged_route(route_layer, selected_feats, geom,
                                               tip_trase, duzina_m, errors)
            if outcome == _NOT_WRITTEN:
                return
            self.stylize_route_layer(route_layer)

            if outcome == _DUPLICATED:
                # The one outcome that needs a modal even though it failed: the
                # merged route IS saved, the routes it replaces are still there,
                # and until the user deletes them the network is measured twice.
                # errors has the provider's reason; this is the consequence.
                QMessageBox.warning(
                    self.iface.mainWindow(), "FiberQ",
                    safe_format(QCoreApplication.translate('FiberQRoutes', _LEFTOVER), _LEFTOVER,
                                count=len(selected_feats)))
                return

            if errors.failed:
                # The collector pushes the reasons on its way out; a success
                # modal on top of them would be the old lie in a new place.
                return

            tip_label_display = ROUTE_TYPE_LABELS.get(tip_trase, tip_trase)
            lines = [safe_format(QCoreApplication.translate('FiberQRoutes', _MERGED_OK),
                                 _MERGED_OK, length=f"{duzina_m:.2f}", km=f"{duzina_km:.2f}",
                                 type=tip_label_display)]
            if unusable:
                lines.append(safe_format(QCoreApplication.translate('FiberQRoutes', _MERGED_SKIPPED),
                                         _MERGED_SKIPPED, count=unusable))
            if gap_m > _JOIN_EPSILON:
                lines.append(safe_format(QCoreApplication.translate('FiberQRoutes', _MERGED_GAP),
                                         _MERGED_GAP, gap=f"{gap_m:.2f}"))
            if outcome == _IN_BUFFER:
                lines.append(QCoreApplication.translate('FiberQRoutes', _MERGED_UNSAVED))
            QMessageBox.information(self.iface.mainWindow(), "FiberQ", "\n".join(lines))

    def _chain_selected_routes(self, selected_feats, errors):
        """One list of points joining every selected route, nearest end first.

        Returns ``(chain, largest_gap_m, unusable_count)``, or
        ``(None, 0.0, n)`` when fewer than two routes could be read.

        Every part of a multipart route is chained, not just ``parts[0]``: a
        GeoPackage MultiLineString column accepts a single-part LineString and
        drops the other parts on disk, so rebuilding from one part is data loss
        rather than a simplification.

        ``largest_gap_m`` is the longest straight segment the chaining had to
        invent, in layer units. It is measured, not guessed, from the distances
        the loop already computes.
        """
        polylines = []
        unusable = 0
        for feat in selected_feats:
            parts = line_parts(feat.geometry())
            if not parts:
                unusable += 1
                continue
            polylines.extend([list(part) for part in parts])

        if len(polylines) < 2:
            if unusable:
                errors.add(None, safe_format(QCoreApplication.translate('FiberQRoutes', _UNUSABLE),
                                             _UNUSABLE, count=unusable))
            return None, 0.0, unusable

        chain = polylines.pop(0)
        largest_gap = 0.0
        while polylines:
            min_dist = None
            min_poly_idx = None
            reverse_this = False
            reverse_chain = False

            for idx, poly in enumerate(polylines):
                dists = [
                    (chain[-1], poly[0], False, False),
                    (chain[-1], poly[-1], False, True),
                    (chain[0], poly[0], True, False),
                    (chain[0], poly[-1], True, True),
                ]
                for pt1, pt2, rev_chain, rev_poly in dists:
                    dist = pt1.distance(pt2)
                    if min_dist is None or dist < min_dist:
                        min_dist = dist
                        min_poly_idx = idx
                        reverse_this = rev_poly
                        reverse_chain = rev_chain

            next_poly = polylines.pop(min_poly_idx)
            if reverse_this:
                next_poly.reverse()
            if reverse_chain:
                chain.reverse()
            if min_dist is not None and min_dist > largest_gap:
                largest_gap = min_dist
            if chain[-1] == next_poly[0]:
                chain += next_poly[1:]
            else:
                chain += next_poly

        if unusable:
            errors.add(None, safe_format(QCoreApplication.translate('FiberQRoutes', _UNUSABLE),
                                         _UNUSABLE, count=unusable))
        return chain, largest_gap, unusable

    def _write_merged_route(self, route_layer, selected_feats, geom, tip_trase, duzina_m, errors):
        """Add the merged route, then remove the routes it replaces.

        Returns one of ``_SAVED``, ``_IN_BUFFER`` (the user's own edit session
        owns the result), ``_NOT_WRITTEN`` (nothing was written and nothing was
        removed) or ``_DUPLICATED`` (the merged route is on disk and so are the
        routes it replaces).

        **The add is committed before the first delete.** A GeoPackage commit is
        not atomic across operations: with an insert-blocking trigger the old
        single-session code had its deletes succeed and its insert refused, and
        both routes were gone from the file. Committing the addition first means
        the worst a refusal can now cost is a duplicate route the user can see.
        """
        was_editing = route_layer.isEditable()
        if not was_editing and not route_layer.startEditing():
            errors.add(route_layer.name(), QCoreApplication.translate(
                'FiberQRoutes', _NOT_EDITABLE))
            return _NOT_WRITTEN

        feat = QgsFeature(route_layer.fields())
        feat.setGeometry(geom)
        self._set_merged_attributes(feat, route_layer, duzina_m, tip_trase, errors)

        route_layer.beginEditCommand(QCoreApplication.translate('FiberQRoutes', _CMD_ADD))
        if not route_layer.addFeature(feat):
            errors.add(route_layer.name(), QCoreApplication.translate(
                'FiberQRoutes', _MERGE_REFUSED))
            route_layer.destroyEditCommand()
            if not was_editing:
                route_layer.rollBack()
            return _NOT_WRITTEN
        route_layer.endEditCommand()

        if not was_editing and not check_commit(route_layer, errors):
            # The merged route did not reach the file, so the originals stay
            # exactly where they are. Nothing to undo and nothing lost.
            return _NOT_WRITTEN

        # Only now the originals, and in their own edit command so that one
        # undo takes the removal back without taking the merged route with it.
        if not was_editing and not route_layer.startEditing():
            errors.add(route_layer.name(), QCoreApplication.translate(
                'FiberQRoutes', _NOT_EDITABLE))
            return _DUPLICATED
        route_layer.beginEditCommand(QCoreApplication.translate('FiberQRoutes', _CMD_REMOVE))
        refused = sum(1 for old_feat in selected_feats if not route_layer.deleteFeature(old_feat.id()))
        route_layer.endEditCommand()
        if was_editing:
            if refused:
                errors.add(route_layer.name(), safe_format(
                    QCoreApplication.translate('FiberQRoutes', _LEFTOVER), _LEFTOVER, count=refused))
            return _IN_BUFFER
        # check_commit reports the provider's own reason. The CONSEQUENCE goes
        # to the caller, which has a modal for it: deleteFeature() answers True
        # for every feature here and it is the commit that gets refused, so
        # `refused` is usually 0 and the outcome cannot be read off the write
        # results at all.
        if check_commit(route_layer, errors) and not refused:
            return _SAVED
        return _DUPLICATED

    def _set_merged_attributes(self, feat, route_layer, duzina_m, tip_trase, errors):
        """Fill the merged route's columns, naming any the layer does not have.

        ``QgsFeature.setAttribute`` **raises KeyError** for a column that is not
        there -- it does not answer False (measured on all three legs). A
        read-only Route layer cannot gain the columns ``_ensure_route_fields``
        tries to add, so this used to end the merge with a bare
        ``KeyError: 'duzina'`` and no message at all.
        """
        values = [
            ("naziv", QCoreApplication.translate('FiberQRoutes', _MERGED_NAME)),
            ("duzina", duzina_m),
            ("duzina_km", round(duzina_m / 1000.0, 2)),
            ("tip_trase", tip_trase),
        ]
        fields = feat.fields()
        missing = []
        for name, value in values:
            if fields.indexFromName(name) < 0:
                missing.append(name)
                continue
            feat.setAttribute(name, value)
        if missing:
            errors.add(route_layer.name(), safe_format(
                QCoreApplication.translate('FiberQRoutes', _NO_COLUMNS), _NO_COLUMNS,
                columns=", ".join(missing)))
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(feat)
        except (AttributeError, ImportError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            # Without an identity the route does not travel into a bundle and
            # cannot be matched on the way back, so this is a real loss. Same
            # handling as _add_one_route's.
            errors.add(None, f"could not give the merged route an identity: {describe(exc)}")

    def _add_imported_routes(self, imported_layer, route_layer, src_crs, dst_crs,
                             transform, tip_trase, errors):
        """Copy every line in ``imported_layer`` into the Route layer.

        Returns ``(added, skipped, saved)``. ``saved`` is True when this call
        opened the editing session and the commit went through, False when it
        opened one and the commit was refused, and None when the user already
        had the layer in edit mode -- their session, theirs to save.

        A refused commit never zeroes ``added``: "added" and "saved" are
        different facts, and saying one for the other is how a refused write came
        out as "No lines found for import in the file!".

        R6. Three things used to end the whole import on one bad feature, with
        the Route layer left in edit mode holding a partial result:

        * ``geom.asPolyline()`` on a **point** is ``TypeError``, and on a
          **null geometry** ``ValueError`` (measured on 3.44.15 and 4.0.3). The
          ``if polyline and len(polyline) >= 2`` guard underneath could never
          run, so a point GeoJSON -- the obvious thing to try -- killed it.
        * a reprojection that cannot work does NOT raise. It answers
          ``Success`` and leaves ``inf inf`` behind, so the importer wrote
          infinite geometry into the project and reported success. Both the
          exception and the infinite outcome are handled by
          ``utils.geometry.transformed``.
        * ``addFeature`` and ``commitChanges`` both discarded their result.

        The work is scoped in an **edit command**, and the layer is only
        committed if this call opened the editing session. A user who already
        had unsaved edits keeps them: the import joins their undo stack instead
        of committing their buffer for them, and a failure destroys only the
        import's own command.
        """
        was_editing = route_layer.isEditable()
        if not was_editing:
            route_layer.startEditing()
        route_layer.beginEditCommand(_route_import())

        added = 0
        skipped = 0
        try:
            for feat in imported_layer.getFeatures():
                parts = self._route_parts(feat.geometry())
                if not parts:
                    skipped += 1
                    continue
                for polyline in parts:
                    geom_line = QgsGeometry.fromPolylineXY(polyline)
                    if src_crs != dst_crs:
                        moved = transformed(geom_line, transform)
                        if moved is None:
                            errors.add(None, QCoreApplication.translate(
                                'FiberQRoutes',
                                "a route could not be reprojected and was left out"))
                            skipped += 1
                            continue
                        geom_line = moved
                    if self._add_one_route(route_layer, geom_line, tip_trase, errors):
                        added += 1
                    else:
                        # A route the LAYER refuses was counted in neither
                        # total, so it vanished from the report entirely: a
                        # read-only Route layer took three routes, added none,
                        # skipped none, and the user was told the file held no
                        # lines (measured on 3.44.15).
                        skipped += 1
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            # KeyError, because QgsFeature.setAttribute RAISES it for a field
            # the layer does not have -- it does not answer False (measured on
            # 3.44.15 and 4.0.3). _add_one_route sets naziv, duzina, duzina_km
            # and tip_trase outside any try, so a Route layer missing one of
            # them sent KeyError('naziv') straight out of this method and out of
            # the Qt slot: a QGIS crash dialog, with the edit command still open
            # and the layer still editable. Measured on main.
            errors.add(None, exc)
            route_layer.destroyEditCommand()
            if not was_editing:
                route_layer.rollBack()
            # destroyEditCommand() undoes this import's own edits either way, so
            # nothing was added however the session is owned.
            return 0, skipped, None if was_editing else False

        route_layer.endEditCommand()
        if was_editing:
            # The user's session, theirs to save. Not an error, and not "saved".
            return added, skipped, None
        if not check_commit(route_layer, errors):
            # NOT zero. QGIS keeps refused features in the layer's buffer (see
            # utils.errors.check_commit), so they really are in the layer -- and
            # reporting zero here is what made the caller tell the user the file
            # had held no lines, sending them to inspect a file that was fine.
            return added, skipped, False
        return added, skipped, True

    @staticmethod
    def _route_parts(geom):
        """The line parts of a geometry, or ``[]`` when it has none.

        Answers ``[]`` for a point, a polygon and a null geometry rather than
        raising, which is the whole of R6's non-line case.

        This is now one line on top of :func:`utils.geometry.line_parts`, which
        is the same code promoted out of here so that ``cable_manager`` and
        ``utils.routing`` -- which had the broken version of it -- can share
        the fixed one. Kept as a method because R6's tests and
        ``_add_imported_routes`` call it by this name.
        """
        return line_parts(geom)

    def _add_one_route(self, route_layer, geom_line, tip_trase, errors) -> bool:
        """One imported route feature. True when it reached the layer."""
        new_feat = QgsFeature(route_layer.fields())
        duzina_m = ground_length(geom_line, route_layer)
        new_feat.setGeometry(geom_line)
        new_feat.setAttribute("naziv", f"Imported route {route_layer.featureCount() + 1}")
        new_feat.setAttribute("duzina", duzina_m)
        new_feat.setAttribute("duzina_km", round(duzina_m / 1000.0, 2))
        new_feat.setAttribute("tip_trase", tip_trase)
        # Phase 0.1: Set UUID
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(new_feat)
        except (AttributeError, ImportError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            # Without an identity the route does not travel into a bundle and
            # cannot be matched on the way back, so this is a real loss.
            errors.add(None, f"could not give an imported route an identity: {describe(exc)}")
        if not route_layer.addFeature(new_feat):
            errors.add(route_layer.name(), QCoreApplication.translate(
                'FiberQRoutes', "a route was rejected by the layer"))
            return False
        return True

    def import_route_from_file(self) -> None:
        """Import routes from external file (KML/KMZ/DWG/GPX/Shape)."""
        filename, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            QCoreApplication.translate('FiberQRoutes', "Choose a route file"), "",
            file_filters.with_any(
                QCoreApplication.translate('FiberQRoutes', "GIS files"),
                file_filters.GIS,
                QCoreApplication.translate('FiberQRoutes', "All files"))
        )
        if not filename:
            return

        imported_layer = QgsVectorLayer(filename, "Import_route_tmp", "ogr")
        if not imported_layer.isValid():
            QMessageBox.warning(
                self.iface.mainWindow(),
                "FiberQ",
                "File cannot be loaded or is not valid!"
            )
            return

        route_layer = self._ensure_route_layer()

        # Coordinate transformation
        src_crs = imported_layer.crs()
        dst_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

        # Ask for route type
        tip_trase = self._ask_route_type("Imported route type")

        with OperationErrors(_route_import(), self.iface) as errors:
            count_added, skipped, saved = self._add_imported_routes(
                imported_layer, route_layer, src_crs, dst_crs, transform,
                tip_trase, errors)
        if skipped:
            # Reason-free, because the reasons differ and each is already
            # written down where it happened: a reprojection that could not work
            # (errors.add above), a geometry that is not a line (_route_parts),
            # or a route the layer refused (_add_one_route). The old wording
            # said "were not routes", which contradicted the reprojection
            # warning sitting next to it in the same message bar about a feature
            # that WAS a route.
            src = QT_TRANSLATE_NOOP(
                'FiberQRoutes',
                "{count} feature(s) in the file could not be imported and were skipped.")
            self.iface.messageBar().pushInfo(
                _route_import(),
                safe_format(QCoreApplication.translate('FiberQRoutes', src), src,
                            count=skipped))
        self.stylize_route_layer(route_layer)

        tip_label_display = ROUTE_TYPE_LABELS.get(tip_trase, tip_trase)

        # Four outcomes, each saying which one it is. Before this they collapsed
        # into two, and a refused commit came out as "No lines found for import
        # in the file!" -- about a file that was fine, while the routes sat
        # unsaved in the layer's buffer. The user's next move was to go and
        # inspect the file; the retry the modal invites then found the layer
        # already editable and reported a bare success (measured on 3.44.15).
        if count_added and saved is False:
            src = QT_TRANSLATE_NOOP('FiberQRoutes', "{count} route(s) were added to the Route layer but could not be saved. Close any program holding the file open, then use Layer > Save Layer Edits. The reason is in the message bar.")
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ",
                                safe_format(QCoreApplication.translate('FiberQRoutes', src), src, count=count_added))
        elif count_added and saved is None:
            src = QT_TRANSLATE_NOOP('FiberQRoutes', "{count} route(s) of type {kind} were added to the Route layer. They are not saved yet, because you already had the layer open for editing -- use Layer > Save Layer Edits when you are ready.")
            QMessageBox.information(self.iface.mainWindow(), "FiberQ",
                                    safe_format(QCoreApplication.translate('FiberQRoutes', src), src, count=count_added, kind=tip_label_display))
        elif count_added:
            QMessageBox.information(
                self.iface.mainWindow(),
                "FiberQ",
                f"Imported {count_added} routes into the 'Route' layer!\n(All are of type: {tip_label_display})"
            )
        elif skipped:
            # The file DID hold features. Saying "no lines found" here is the
            # same lie in a quieter form.
            src = QT_TRANSLATE_NOOP('FiberQRoutes', "None of the {count} feature(s) in the file could be imported. The reason is in the message bar.")
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ",
                                safe_format(QCoreApplication.translate('FiberQRoutes', src), src, count=skipped))
        else:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "FiberQ",
                "No lines found for import in the file!"
            )

    def change_route_type(self) -> None:
        """Change the type of selected routes."""
        route_layer = self._find_route_layer()
        if route_layer is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "FiberQ",
                "Route layer 'Route' not found!"
            )
            return

        selected_feats = route_layer.selectedFeatures()
        if not selected_feats:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Change route type",
                "No routes selected!"
            )
            return

        # Ask for new type
        items = [ROUTE_TYPE_LABELS.get(code, code) for code in ROUTE_TYPE_OPTIONS]
        tip_label, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Change route type",
            "Select new route type for selected routes:",
            items,
            0, False
        )
        if not ok or not tip_label:
            return
        tip_trase = ROUTE_LABEL_TO_CODE.get(tip_label, ROUTE_TYPE_OPTIONS[0])

        # Update all selected features
        route_layer.startEditing()
        count = 0
        idx_tip = route_layer.fields().indexFromName("tip_trase")
        for feat in selected_feats:
            route_layer.changeAttributeValue(feat.id(), idx_tip, tip_trase)
            count += 1

        route_layer.commitChanges()
        self.stylize_route_layer(route_layer)

        tip_label_display = ROUTE_TYPE_LABELS.get(tip_trase, tip_trase)
        QMessageBox.information(
            self.iface.mainWindow(),
            "Change route type",
            f"Route type has been changed to '{tip_label_display}' for {count} route(s)."
        )


# Export constants for backward compatibility
TRASA_TYPE_OPTIONS = ROUTE_TYPE_OPTIONS
TRASA_TYPE_LABELS = ROUTE_TYPE_LABELS
TRASA_LABEL_TO_CODE = ROUTE_LABEL_TO_CODE

__all__ = [
    'RouteManager',
    'ROUTE_TYPE_OPTIONS',
    'ROUTE_TYPE_LABELS',
    'ROUTE_LABEL_TO_CODE',
    # Legacy names
    'TRASA_TYPE_OPTIONS',
    'TRASA_TYPE_LABELS',
    'TRASA_LABEL_TO_CODE',
]
