"""
FiberQ v2 - Extension Tool (Joint Closure Placement)

Map tool for placing joint closures on the network.
Phase 2.1: Extracted from extracted_classes.py
Phase 5.2: Added logging infrastructure
"""

from qgis.PyQt import sip

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsWkbTypes, QgsMarkerSymbol,
    QgsSvgMarkerSymbolLayer, QgsUnitTypes, QgsRectangle,
    QgsFeatureRequest, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling
)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker

# Import from legacy bridge for compatibility
from ..utils.legacy_bridge import (
    NASTAVAK_DEF,
    _apply_fixed_text_label,
    _map_icon_path,
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class ExtensionTool(QgsMapToolEmitPoint):
    """Tool for placing joint closures on the network."""

    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setColor(QColor(255, 0, 0))
        self.snap_marker.setIconType(QgsVertexMarker.IconType.ICON_CIRCLE)
        self.snap_marker.setIconSize(14)
        self.snap_marker.setPenWidth(3)
        self.snap_marker.hide()

    def keyPressEvent(self, event):
        # ESC -> cancel tool
        if event.key() == Qt.Key.Key_Escape:
            try:
                self.snap_marker.hide()
            except Exception as e:
                logger.debug(f"Error in ExtensionTool.keyPressEvent: {e}")
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in ExtensionTool.keyPressEvent: {e}")

    def canvasPressEvent(self, event):
        # Right click -> cancel tool (without placing joint closure)
        if event.button() == Qt.MouseButton.RightButton:
            try:
                self.snap_marker.hide()
            except Exception as e:
                logger.debug(f"Error in ExtensionTool.canvasPressEvent: {e}")
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in ExtensionTool.canvasPressEvent: {e}")

    def _snap_candidate(self, point):
        """Snap to:
        - point layers (Poles/Manholes + optionally Infrastructure cuts)
        - vertices of cable line layers (so Joint Closure can be placed exactly at cut location)
        """
        tol = self.canvas.mapUnitsPerPixel() * 20
        rect = QgsRectangle(point.x() - tol, point.y() - tol, point.x() + tol, point.y() + tol)

        snap_point = None
        min_dist = None

        def consider(pt):
            nonlocal snap_point, min_dist
            d = QgsPointXY(point).distance(QgsPointXY(pt))
            if min_dist is None or d < min_dist:
                min_dist = d
                snap_point = QgsPointXY(pt)

        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                    continue

                gtype = lyr.geometryType()
                lname = (lyr.name() or "").lower()

                # --- POINT layers (poles/manholes + optionally cut marker layer) ---
                is_node_layer = (
                    lyr.name() in ("Poles", "Poles", "OKNA", "Okna", "Manholes")
                    or "infrastructure cut" in lname  # noqa: W503
                    or "infrastructure cuts" in lname  # noqa: W503
                    or lname.strip() in ("cuts", "cut")  # noqa: W503
                )

                if gtype == QgsWkbTypes.GeometryType.PointGeometry and is_node_layer:
                    req = QgsFeatureRequest().setFilterRect(rect)
                    for feat in lyr.getFeatures(req):
                        geom = feat.geometry()
                        if not geom or geom.isEmpty():
                            continue
                        # safest: vertices() works for point/multipoint
                        for v in geom.vertices():
                            consider(v)
                    continue

                # --- LINE layers of cables (vertex at cut location) ---
                is_cable_layer = (
                    "cable" in lname
                    or "kabl" in lname  # noqa: W503
                    or lyr.name() in ("Route", "Route")  # noqa: W503
                )

                if gtype == QgsWkbTypes.GeometryType.LineGeometry and is_cable_layer:
                    req = QgsFeatureRequest().setFilterRect(rect)
                    for feat in lyr.getFeatures(req):
                        geom = feat.geometry()
                        if not geom or geom.isEmpty():
                            continue
                        for v in geom.vertices():
                            consider(v)

            except Exception as e:
                # if any layer fails, skip it
                logger.debug(f"Skipping layer during snap candidate search: {e}")

        if snap_point is not None and min_dist is not None and min_dist < tol:
            return snap_point
        return None

    def canvasMoveEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        snap_point = self._snap_candidate(point)
        if snap_point:
            self.snap_marker.setCenter(snap_point)
            self.snap_marker.show()
        else:
            self.snap_marker.hide()

    def _apply_joint_closure_aliases(self, layer):
        """Apply English field aliases and layer name to a joint closure layer.

        Delegates to utils.field_aliases module.
        """
        try:
            from ..utils.field_aliases import apply_joint_closure_aliases, set_joint_closure_layer_alias
            if layer is None:
                return
            apply_joint_closure_aliases(layer)
            set_joint_closure_layer_alias(layer)
        except Exception as e:
            logger.debug(f"Error in ExtensionTool._apply_joint_closure_aliases: {e}")

    def canvasReleaseEvent(self, event):
        # Only left click places joint closure
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            QMessageBox.warning(None, "FiberQ", "Layer not found or invalid!")
            return

        click_point = self.toMapCoordinates(event.pos())
        snap_point = self._snap_candidate(click_point)
        final_point = snap_point if snap_point else click_point

        naziv, ok = QInputDialog.getText(
            None,
            "Joint closure",
            "Enter joint closure name:"
        )
        if not ok or not naziv:
            QMessageBox.warning(None, "FiberQ", "No joint closure name entered!")
            self.snap_marker.hide()
            return

        # Find existing Joint Closures layer (supports old name "Nastavci")
        nastavak_layer = None
        target_names = {
            NASTAVAK_DEF.get("name", "Joint Closures"),
            "Nastavci",
        }
        for lyr in QgsProject.instance().mapLayers().values():
            if (
                isinstance(lyr, QgsVectorLayer)
                and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry  # noqa: W503
                and lyr.name() in target_names  # noqa: W503
            ):
                nastavak_layer = lyr
                self._apply_joint_closure_aliases(nastavak_layer)
                # Phase 0.1: Ensure UUID field exists
                try:
                    from ..utils.uuid_utils import ensure_uuid_field
                    ensure_uuid_field(nastavak_layer)
                except Exception as e:
                    logger.debug(f"Could not ensure UUID field on joint closure layer: {e}")
                break

        # 2) If doesn't exist – create new
        if nastavak_layer is None:
            crs = self.canvas.mapSettings().destinationCrs().authid()
            nastavak_layer = QgsVectorLayer(
                f"Point?crs={crs}",
                NASTAVAK_DEF.get("name", "Joint Closures"),
                "memory",
            )

            pr = nastavak_layer.dataProvider()
            pr.addAttributes([
                QgsField("naziv", QVariant.String),
                QgsField("fiberq_uuid", QVariant.String),
            ])
            nastavak_layer.updateFields()

            symbol = QgsMarkerSymbol.createSimple(
                {"name": "circle", "size": "10", "size_unit": "MapUnit"}
            )
            try:
                svg_layer = QgsSvgMarkerSymbolLayer(
                    _map_icon_path("map_joint_closure.svg")
                )
                svg_layer.setSize(10)
                try:
                    svg_layer.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMetersInMapUnits)
                except Exception:
                    svg_layer.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMapUnits)
                symbol.changeSymbolLayer(0, svg_layer)
            except Exception as e:
                logger.debug(f"Error in ExtensionTool.canvasReleaseEvent: {e}")

            nastavak_layer.renderer().setSymbol(symbol)
            QgsProject.instance().addMapLayer(nastavak_layer)

            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "naziv"
            label_settings.enabled = True
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            nastavak_layer.setLabeling(labeling)
            nastavak_layer.setLabelsEnabled(True)
            _apply_fixed_text_label(nastavak_layer, "naziv", 8.0, 5.0)
            nastavak_layer.triggerRepaint()

            # Apply aliases right after creating layer
            self._apply_joint_closure_aliases(nastavak_layer)

        # 3) If layer exists but doesn't have 'naziv' field – add it + labeling + alias
        elif nastavak_layer.fields().indexFromName("naziv") == -1:
            nastavak_layer.startEditing()
            nastavak_layer.dataProvider().addAttributes(
                [QgsField("naziv", QVariant.String)]
            )
            nastavak_layer.updateFields()
            nastavak_layer.commitChanges()
            nastavak_layer.triggerRepaint()

            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "naziv"
            label_settings.enabled = True
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            nastavak_layer.setLabeling(labeling)
            nastavak_layer.setLabelsEnabled(True)
            _apply_fixed_text_label(nastavak_layer, "naziv", 8.0, 5.0)
            nastavak_layer.triggerRepaint()

            self._apply_joint_closure_aliases(nastavak_layer)

        # 4) Add new joint-closure feature
        nastavak_feat = QgsFeature(nastavak_layer.fields())
        nastavak_feat.setGeometry(QgsGeometry.fromPointXY(final_point))
        nastavak_feat.setAttribute("naziv", naziv)

        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(nastavak_feat)
        except Exception as e:
            logger.debug(f"Could not set UUID on joint closure feature: {e}")

        nastavak_layer.startEditing()
        nastavak_layer.addFeature(nastavak_feat)
        nastavak_layer.commitChanges()
        nastavak_layer.triggerRepaint()
        self.snap_marker.hide()

        # Record for undo (v1.2 — Feature 2)
        try:
            if hasattr(self, 'plugin') and self.plugin and hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                self.plugin.undo_manager.record_add(nastavak_layer, nastavak_feat)
        except Exception as e:
            logger.debug(f"Error recording undo for joint closure: {e}")

        QMessageBox.information(None, "FiberQ", "Joint closure placed!")


__all__ = ['ExtensionTool']
