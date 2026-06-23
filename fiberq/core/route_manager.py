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

from qgis.PyQt.QtCore import QVariant, Qt
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
from ..utils.logger import get_logger
logger = get_logger(__name__)


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

    def set_route_layer_alias(self, layer: QgsVectorLayer) -> None:
        """Set the route layer display name to 'Route'."""
        try:
            from ..utils.field_aliases import set_route_layer_alias
            set_route_layer_alias(layer)
        except Exception as e:
            logger.debug(f"Error in RouteManager.set_route_layer_alias: {e}")

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
            self.set_route_layer_alias(route_layer)
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
            symbol_layer.setWidthUnit(QgsUnitTypes.RenderMetersInMapUnits)
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
            if lyr.name() in ('Route', 'Trasa') and lyr.geometryType() == QgsWkbTypes.LineGeometry:
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
        """Ensure route layer has all required fields."""
        added_fields = []
        route_layer.startEditing()

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
        route_layer.commitChanges()

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
                if (lyr.geometryType() == QgsWkbTypes.PointGeometry and  # noqa: W504
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
        duzina_m = line_geom.length()
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
        except Exception:
            pass

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
        """Merge selected routes into one."""
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

        # Extract polylines
        polylines = []
        for feat in selected_feats:
            geom = feat.geometry()
            pts = geom.asPolyline()
            if not pts:
                multi = geom.asMultiPolyline()
                if multi and len(multi) > 0:
                    pts = multi[0]
            if pts and len(pts) >= 2:
                polylines.append(list(pts))

        if len(polylines) < 2:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "FiberQ",
                "Not enough valid lines to merge!"
            )
            return

        # Chain polylines by nearest endpoint
        chain = polylines.pop(0)
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
            if chain[-1] == next_poly[0]:
                chain += next_poly[1:]
            else:
                chain += next_poly

        geom = QgsGeometry.fromPolylineXY(chain)

        # Convert multipart to single if needed
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
            if lines and len(lines) == 1:
                geom = QgsGeometry.fromPolylineXY(lines[0])
            else:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Merge routes",
                    "Cannot merge into single line! Routes are not connected end-to-end."
                )
                return

        # Ask for route type
        tip_trase = self._ask_route_type("Type of connected route")

        duzina_m = geom.length()
        duzina_km = round(duzina_m / 1000.0, 2)

        # Delete old features and add merged
        route_layer.startEditing()
        for f in selected_feats:
            route_layer.deleteFeature(f.id())

        feat = QgsFeature(route_layer.fields())
        feat.setGeometry(geom)
        feat.setAttribute("naziv", "Merged route")
        feat.setAttribute("duzina", duzina_m)
        feat.setAttribute("duzina_km", duzina_km)
        feat.setAttribute("tip_trase", tip_trase)
        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(feat)
        except Exception:
            pass
        route_layer.addFeature(feat)
        route_layer.commitChanges()
        self.stylize_route_layer(route_layer)

        tip_label_display = ROUTE_TYPE_LABELS.get(tip_trase, tip_trase)
        QMessageBox.information(
            self.iface.mainWindow(),
            "FiberQ",
            f"Route has been created!\nLength: {duzina_m:.2f} m ({duzina_km:.2f} km)\nType: {tip_label_display}"
        )

    def import_route_from_file(self) -> None:
        """Import routes from external file (KML/KMZ/DWG/GPX/Shape)."""
        filename, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Choose route file (KML/KMZ/DWG/GPX/Shape)", "",
            "GIS files (*.kml *.kmz *.dwg *.gpx *.shp);;All files (*)"
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

        route_layer.startEditing()
        count_added = 0

        for feat in imported_layer.getFeatures():
            geom = feat.geometry()
            if geom.isMultipart():
                multi = geom.asMultiPolyline()
                if multi:
                    for polyline in multi:
                        if polyline and len(polyline) >= 2:
                            new_feat = QgsFeature(route_layer.fields())
                            geom_line = QgsGeometry.fromPolylineXY(polyline)
                            if src_crs != dst_crs:
                                geom_line.transform(transform)
                            duzina_m = geom_line.length()
                            duzina_km = round(duzina_m / 1000.0, 2)
                            new_feat.setGeometry(geom_line)
                            new_feat.setAttribute("naziv", f"Imported route {route_layer.featureCount() + 1}")
                            new_feat.setAttribute("duzina", duzina_m)
                            new_feat.setAttribute("duzina_km", duzina_km)
                            new_feat.setAttribute("tip_trase", tip_trase)
                            # Phase 0.1: Set UUID
                            try:
                                from ..utils.uuid_utils import set_feature_uuid
                                set_feature_uuid(new_feat)
                            except Exception:
                                pass
                            route_layer.addFeature(new_feat)
                            count_added += 1
            else:
                polyline = geom.asPolyline()
                if polyline and len(polyline) >= 2:
                    new_feat = QgsFeature(route_layer.fields())
                    geom_line = QgsGeometry.fromPolylineXY(polyline)
                    if src_crs != dst_crs:
                        geom_line.transform(transform)
                    duzina_m = geom_line.length()
                    duzina_km = round(duzina_m / 1000.0, 2)
                    new_feat.setGeometry(geom_line)
                    new_feat.setAttribute("naziv", f"Imported route {route_layer.featureCount() + 1}")
                    new_feat.setAttribute("duzina", duzina_m)
                    new_feat.setAttribute("duzina_km", duzina_km)
                    new_feat.setAttribute("tip_trase", tip_trase)
                    # Phase 0.1: Set UUID
                    try:
                        from ..utils.uuid_utils import set_feature_uuid
                        set_feature_uuid(new_feat)
                    except Exception:
                        pass
                    route_layer.addFeature(new_feat)
                    count_added += 1

        route_layer.commitChanges()
        self.stylize_route_layer(route_layer)

        tip_label_display = ROUTE_TYPE_LABELS.get(tip_trase, tip_trase)

        if count_added:
            QMessageBox.information(
                self.iface.mainWindow(),
                "FiberQ",
                f"Imported {count_added} routes into the 'Route' layer!\n(All are of type: {tip_label_display})"
            )
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
