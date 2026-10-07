"""
FiberQ v2 - Extension Tool (Joint Closure Placement)

Map tool for placing joint closures on the network.
Phase 2.1: Extracted from extracted_classes.py
Phase 5.2: Added logging infrastructure
"""

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsField, QgsWkbTypes, QgsMarkerSymbol,
    QgsSvgMarkerSymbolLayer, QgsUnitTypes,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling
)
from qgis.gui import QgsMapToolEmitPoint

from .base import (
    PlacementSnapper, SNAP_CABLE_LAYERS, SNAP_NODE_LAYERS, SNAP_ROUTE_LAYERS,
)

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

    def __init__(self, canvas, layer=None):
        """``layer`` is accepted and ignored.

        The tool writes only to the Joint Closures layer, which it resolves (or
        creates) from the project on each click. It never read or wrote the layer
        passed here -- that argument is leftover coupling from when joint closures
        were placed onto poles. The parameter is kept so any out-of-tree caller
        keeps working; new code should omit it.
        """
        super().__init__(canvas)
        self.canvas = canvas
        self.snapper = PlacementSnapper(
            canvas,
            point_layers=SNAP_NODE_LAYERS,
            line_layers=SNAP_ROUTE_LAYERS + SNAP_CABLE_LAYERS,
            pixels=20,
            # Vertices only, which is what this tool always did: a closure
            # marks a splice, so it belongs on a node or on the cut vertex of a
            # cable, never at an arbitrary point along one. Letting it land
            # mid-span would be a new behaviour, not one of the three fixes the
            # fallback is here to make.
            segments=False,
            # A joint closure also belongs on a user's infrastructure-cut
            # marker layer, which is not part of the FiberQ schema and so has
            # no canonical name to resolve.
            extra_point_layers=("infrastructure cut", "cuts"),
        )

    def keyPressEvent(self, event):
        # ESC -> cancel tool
        if event.key() == Qt.Key.Key_Escape:
            self.snapper.clear()
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in ExtensionTool.keyPressEvent: {e}")

    def canvasPressEvent(self, event):
        # Right click -> cancel tool (without placing joint closure)
        if event.button() == Qt.MouseButton.RightButton:
            self.snapper.clear()
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in ExtensionTool.canvasPressEvent: {e}")

    def deactivate(self):
        """Clear the indicator, so it does not outlive the tool."""
        self.snapper.clear()
        super().deactivate()

    def canvasMoveEvent(self, event):
        """Show where the joint closure will land."""
        self.snapper.snap(event)

    def _apply_joint_closure_aliases(self, layer):
        """Apply English field aliases and layer name to a joint closure layer.

        Delegates to utils.field_aliases module.
        """
        try:
            from ..utils.field_aliases import apply_joint_closure_aliases
            if layer is None:
                return
            apply_joint_closure_aliases(layer)
        except Exception as e:
            logger.debug(f"Error in ExtensionTool._apply_joint_closure_aliases: {e}")

    def canvasReleaseEvent(self, event):
        # Only left click places joint closure
        if event.button() != Qt.MouseButton.LeftButton:
            return

        final_point, _match = self.snapper.snap(event)

        naziv, ok = QInputDialog.getText(
            None,
            "Joint closure",
            "Enter joint closure name:"
        )
        if not ok or not naziv:
            QMessageBox.warning(None, "FiberQ", "No joint closure name entered!")
            self.snapper.clear()
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
        self.snapper.clear()

        # Record for undo (v1.2 — Feature 2)
        try:
            if hasattr(self, 'plugin') and self.plugin and hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                self.plugin.undo_manager.record_add(nastavak_layer, nastavak_feat)
        except Exception as e:
            logger.debug(f"Error recording undo for joint closure: {e}")

        QMessageBox.information(None, "FiberQ", "Joint closure placed!")


__all__ = ['ExtensionTool']
