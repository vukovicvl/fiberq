# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Slack Manager.

This module provides slack (optical reserve) management functionality:
- Creating and ensuring slack layers
- Styling slack layers
- Computing slack totals for cables
- Batch slack generation
"""

from typing import Optional

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsFeatureRequest,
    QgsMarkerSymbol,
    QgsSingleSymbolRenderer,
    QgsUnitTypes,
)
from qgis.PyQt.QtGui import QColor

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class SlackManager:
    """Manager for optical slack/reserve operations."""

    def __init__(self, iface, layer_manager=None, style_manager=None):
        """
        Initialize SlackManager.

        Args:
            iface: QGIS interface
            layer_manager: Optional LayerManager instance
            style_manager: Optional StyleManager instance
        """
        self.iface = iface
        self.layer_manager = layer_manager
        self.style_manager = style_manager
        self._reserve_tool = None  # Active reserve placement tool

        # Callbacks for cable styling (set by plugin)
        self._stylize_cable_layer_callback = None

    def set_cable_style_callback(self, callback):
        """Set callback for styling cable layers after slack updates."""
        self._stylize_cable_layer_callback = callback

    def set_slack_layer_alias(self, layer: QgsVectorLayer) -> None:
        """Display layer 'Opticke_rezerve' as 'Optical slack' in Layers panel."""
        try:
            root = QgsProject.instance().layerTreeRoot()
            node = root.findLayer(layer.id())
            if node:
                node.setCustomLayerName("Optical slack")
        except Exception as e:
            logger.debug(f"Error in SlackManager.set_slack_layer_alias: {e}")

    def apply_slack_field_aliases(self, layer: QgsVectorLayer) -> None:
        """Apply English field aliases and value maps to an optical slack layer."""
        try:
            from ..utils.field_aliases import apply_slack_field_aliases
            apply_slack_field_aliases(layer)
        except Exception as e:
            logger.debug(f"Error in SlackManager.apply_slack_field_aliases: {e}")

    def ensure_slack_layer(self) -> Optional[QgsVectorLayer]:
        """Create or return the Optical slacks layer.

        Returns:
            The optical slacks vector layer, or None if creation failed.
        """
        # Try LayerManager first
        if self.layer_manager:
            try:
                lyr = self.layer_manager.ensure_slack_layer()
                if lyr:
                    self.apply_slack_field_aliases(lyr)
                    self.set_slack_layer_alias(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Error in SlackManager.ensure_slack_layer: {e}")

        # Fallback: find existing or create new
        # Issue #2: Check for all possible slack layer names
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.PointGeometry  # noqa: W503
                    and lyr.name() in ("Opticke_rezerve", "Optical slacks", "Optical slack")  # noqa: W503
                ):
                    self.apply_slack_field_aliases(lyr)
                    self.set_slack_layer_alias(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Error in SlackManager.ensure_slack_layer: {e}")

        # Create new memory layer
        crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        vl = QgsVectorLayer(f"Point?crs={crs}", "Optical slacks", "memory")  # Issue #2: Use plural name
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("tip", QVariant.String),
            QgsField("duzina_m", QVariant.Double),
            QgsField("lokacija", QVariant.String),
            QgsField("cable_layer_id", QVariant.String),
            QgsField("cable_fid", QVariant.Int),
            QgsField("strana", QVariant.String),
            QgsField("napomena", QVariant.String),
        ])
        vl.updateFields()
        # WP1b identity invariant: ensure the fiberq_uuid column exists.
        try:
            from ..utils.uuid_utils import ensure_uuid_field
            ensure_uuid_field(vl)
        except Exception as e:
            logger.debug(f"Error ensuring fiberq_uuid on slack layer: {e}")
        self.apply_slack_field_aliases(vl)
        self.set_slack_layer_alias(vl)
        QgsProject.instance().addMapLayer(vl)
        try:
            self.stylize_slack_layer(vl)
        except Exception as e:
            logger.debug(f"Error in SlackManager.ensure_slack_layer: {e}")
        return vl

    def stylize_slack_layer(self, vl: QgsVectorLayer) -> None:
        """Apply simple red circle style to slack layer."""
        # Try StyleManager first
        if self.style_manager:
            try:
                self.style_manager.stylize_slack_layer(vl)
                return
            except Exception as e:
                logger.debug(f"Error in SlackManager.stylize_slack_layer: {e}")

        # Fallback: inline implementation
        try:
            sym = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "size": "3",
            })
            try:
                sym.setColor(QColor(255, 0, 0))
            except Exception as e:
                logger.debug(f"Error in SlackManager.stylize_slack_layer: {e}")
            try:
                sym.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            except Exception as e:
                logger.debug(f"Error in SlackManager.stylize_slack_layer: {e}")

            renderer = QgsSingleSymbolRenderer(sym)
            vl.setRenderer(renderer)
            vl.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in SlackManager.stylize_slack_layer: {e}")

    def recompute_slack_for_cable(self, cable_layer_id: str, cable_fid: int) -> None:
        """
        Compute sum of 'duzina_m' from Optical slack layer for given cable and update:
        - slack_m (if field exists: 'slack_m' / 'slack' / 'slack_m' / 'slacks_m')
        - total_len_m = geom.length() + slack_m (if field 'total_len_m' exists)

        Args:
            cable_layer_id: Layer ID of the cable
            cable_fid: Feature ID of the cable
        """
        try:
            prj = QgsProject.instance()
            rez = self.ensure_slack_layer()
            if rez is None:
                return

            # 1) Calculate slack sum
            slack = 0.0
            expr = f'"cable_layer_id" = \'{cable_layer_id}\' AND "cable_fid" = {int(cable_fid)}'
            try:
                it = rez.getFeatures(QgsFeatureRequest().setFilterExpression(expr))
            except Exception:
                it = rez.getFeatures()
            for f in it:
                try:
                    if f["cable_layer_id"] == cable_layer_id and int(f["cable_fid"]) == int(cable_fid):
                        try:
                            slack += float(f["duzina_m"] or 0.0)
                        except Exception as e:
                            logger.debug(f"Error in SlackManager.recompute_slack_for_cable: {e}")
                except Exception as e:
                    logger.debug(f"Error in SlackManager.recompute_slack_for_cable: {e}")

            # 2) Find cable and update attributes
            cable_lyr = prj.mapLayer(cable_layer_id)
            if cable_lyr is None:
                return
            cable_f = next((f for f in cable_lyr.getFeatures(QgsFeatureRequest(int(cable_fid)))), None)
            if cable_f is None:
                return

            # Find field names
            fld_slack = None
            for name in ("slack_m", "slack", "slack_m", "slacks_m"):
                if cable_lyr.fields().indexOf(name) != -1:
                    fld_slack = name
                    break
            has_total = cable_lyr.fields().indexOf("total_len_m") != -1

            if fld_slack is None and (not has_total):
                return

            cable_lyr.startEditing()
            if fld_slack:
                cable_f[fld_slack] = float(slack)
            if has_total:
                try:
                    geom_len = float(cable_f.geometry().length())
                except Exception:
                    geom_len = 0.0
                cable_f["total_len_m"] = geom_len + float(slack)
            cable_lyr.updateFeature(cable_f)
            cable_lyr.commitChanges()

            # Workaround for QGIS bug: after programmatic editing of memory layers,
            # QGIS sometimes "forgets" labels until style is reapplied
            if self._stylize_cable_layer_callback:
                try:
                    self._stylize_cable_layer_callback(cable_lyr)
                except Exception as e:
                    logger.debug(f"Error in SlackManager.recompute_slack_for_cable: {e}")

            cable_lyr.triggerRepaint()
        except Exception as e:
            try:
                self.iface.messageBar().pushWarning("Optical slacks", f"Failed updating slack: {e}")
            except Exception as e:
                logger.debug(f"Error in SlackManager.recompute_slack_for_cable: {e}")

    def start_slack_interactive(self, default_tip: str = "Terminal") -> None:
        """Start map tool for interactive slack placement.

        Args:
            default_tip: Default slack type ('Terminal' or 'Thru')
        """
        from ..dialogs.slack_dialog import SlackDialog
        from ..tools.slack_tool import SlackPlaceTool

        dlg = SlackDialog(self.iface.mainWindow(), default_tip=default_tip)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        params = dlg.values()
        self._reserve_tool = SlackPlaceTool(self.iface, self, params)
        self.iface.mapCanvas().setMapTool(self._reserve_tool)

    def generate_terminal_slack_for_selected(self) -> None:
        """
        For selected cables (in Underground/Aerial cables layers),
        create terminal slack at both endpoints.
        """
        from ..tools.slack_tool import SlackPlaceTool

        vl = self.ensure_slack_layer()
        kabl_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.geometryType() == QgsWkbTypes.LineGeometry and lyr.name() in (
                    "Kablovi_podzemni", "Kablovi_vazdusni",
                    "Underground cables", "Aerial cables"
                ):
                    kabl_layers.append(lyr)
            except Exception as e:
                logger.debug(f"Error in SlackManager.generate_terminal_slack_for_selected: {e}")

        count = 0
        for kl in kabl_layers:
            sel = kl.selectedFeatures()
            for kf in sel:
                geom = kf.geometry()
                line = geom.asPolyline()
                if not line:
                    parts = geom.asMultiPolyline()
                    if parts:
                        line = parts[0]
                if not line:
                    continue

                for lbl, ep in (("od", line[0]), ("do", line[-1])):
                    f = QgsFeature(vl.fields())
                    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(ep)))
                    f["tip"] = "Terminal"
                    f["duzina_m"] = 20

                    # Auto-location: try to recognize Pole/Manhole
                    lok = "Objekat"
                    try:
                        (nl, nf, nd) = SlackPlaceTool(self.iface, self, {})._nearest_node(QgsPointXY(ep))
                        if nl and nf:
                            if nl.name() in ("Poles", "Stubovi"):
                                lok = "Stub"
                            elif nl.name() in ("OKNA", "Manholes"):
                                lok = "OKNO"
                            else:
                                lok = "Objekat"
                    except Exception as e:
                        logger.debug(f"Error in SlackManager.generate_terminal_slack_for_selected: {e}")

                    f["lokacija"] = lok
                    f["cable_layer_id"] = kl.id()
                    f["cable_fid"] = int(kf.id())
                    f["strana"] = lbl
                    # Phase 0.1: Set UUID for FiberQ Designer
                    try:
                        from ..utils.uuid_utils import set_feature_uuid
                        set_feature_uuid(f)
                    except Exception:
                        pass
                    vl.startEditing()
                    vl.addFeature(f)
                    vl.commitChanges()

                    # Record for undo (v1.2 — Feature 2)
                    try:
                        undo_mgr = getattr(self, 'undo_manager', None)
                        if undo_mgr:
                            undo_mgr.record_add(vl, f)
                    except Exception as e:
                        logger.debug(f"Error recording undo for slack: {e}")

                    # Auto-compute slack for cable
                    try:
                        self.recompute_slack_for_cable(kl.id(), int(kf.id()))
                    except Exception as e:
                        logger.debug(f"Error in SlackManager.generate_terminal_slack_for_selected: {e}")
                    count += 1

        vl.triggerRepaint()
        try:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Optical slacks",
                f"Created {count} slacks."
            )
        except Exception as e:
            logger.debug(f"Error in SlackManager.generate_terminal_slack_for_selected: {e}")


__all__ = ['SlackManager']
