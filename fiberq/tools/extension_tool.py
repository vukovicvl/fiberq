"""
FiberQ v2 - Extension Tool (Joint Closure Placement)

Map tool for placing joint closures on the network.
Phase 2.1: Extracted from extracted_classes.py
Phase 5.2: Added logging infrastructure
"""

from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP, Qt
from ..utils.compat import FieldType, new_field
from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsWkbTypes, QgsMarkerSymbol,
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
from ..utils.errors import OperationErrors, add_and_save, add_columns
from ..utils.logger import get_logger
from ..utils.uuid_utils import ensure_uuid_field
logger = get_logger(__name__)


def _place_closure() -> str:
    """Title on the message-bar entries the joint-closure tool pushes."""
    src = QT_TRANSLATE_NOOP('FiberQTools', "Place joint closure")
    return QCoreApplication.translate('FiberQTools', src)


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
            # Along a span as well as on a vertex, like the other placement
            # tools. Until 1.6.0 a closure snapped to vertices and nodes only,
            # so on a straight two-vertex route there was nothing to land on
            # between its ends (v1.6.0 QA, section B; the maintainer's call,
            # 2026-10-21). A vertex or a node within reach still wins: the
            # fallback returns the nearest vertex before any segment point.
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
                # Phase 0.1: Ensure UUID field exists. False where it cannot be
                # added (reason logged); the closure is then placed without an ID.
                ensure_uuid_field(nastavak_layer)
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
                new_field("naziv", FieldType.String),
                new_field("fiberq_uuid", FieldType.String),
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
            # Typed and straight to the provider (utils.errors.add_columns), with
            # a refusal said. No edit session: the startEditing()/commitChanges()
            # pair that was here committed nothing of the column's -- addAttributes
            # bypasses the buffer -- only whatever else the layer had unsaved.
            with OperationErrors(_place_closure(), None) as column_errors:
                add_columns(nastavak_layer, [new_field("naziv", FieldType.String)], column_errors)
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

        # Each answer checked (utils.errors.add_and_save): all three used to be
        # thrown away, and "Joint closure placed!" followed regardless.
        placed = False
        with OperationErrors(_place_closure(), None, absorb=True) as errors:
            placed = add_and_save(nastavak_layer, [nastavak_feat], errors)
        nastavak_layer.triggerRepaint()
        self.snapper.clear()
        if not placed:
            return

        # Record for undo (v1.2 — Feature 2). Only after the save, as above.
        try:
            if hasattr(self, 'plugin') and self.plugin and hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                self.plugin.undo_manager.record_add(nastavak_layer, nastavak_feat)
        except Exception as e:
            logger.debug(f"Error recording undo for joint closure: {e}")

        QMessageBox.information(None, "FiberQ", "Joint closure placed!")


__all__ = ['ExtensionTool']
