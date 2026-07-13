# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Pipe/Duct Manager.

This module provides pipe and duct management functionality:
- PE pipes layer management
- Transition pipes layer management
- Pipe styling and aliases
- Pipe placement workflows

Phase 5.2: Added logging infrastructure
"""

from typing import Optional, List, Dict, Any

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMessageBox, QDialog

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsWkbTypes,
    QgsSymbol,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsUnitTypes,
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class PipeManager:
    """Manager for pipe and duct operations."""

    # Layer name mappings
    LAYER_ALIAS_MAP = {
        "PE cevi": "PE pipes",
        "Prelazne cevi": "Transition pipes",
    }

    # Valid pipe layer names
    PIPE_LAYER_NAMES = ('PE cevi', 'Prelazne cevi', 'PE pipes', 'Transition pipes')

    def __init__(self, iface, layer_manager=None, style_manager=None, data_manager=None):
        """
        Initialize PipeManager.

        Args:
            iface: QGIS interface
            layer_manager: Optional LayerManager instance
            style_manager: Optional StyleManager instance
            data_manager: Optional DataManager instance
        """
        self.iface = iface
        self.layer_manager = layer_manager
        self.style_manager = style_manager
        self.data_manager = data_manager

    # -------------------------------------------------------------------------
    # Group management
    # -------------------------------------------------------------------------

    def move_group_to_top(self, group_name: str = "CEVI") -> None:
        """
        Move a group to the top of the layer tree.

        Args:
            group_name: Name of the group to move
        """
        # Try LayerManager first
        if self.layer_manager:
            try:
                self.layer_manager.move_group_to_top(group_name)
                return
            except Exception as e:
                logger.debug(f"Error in PipeManager.move_group_to_top: {e}")

        # Fallback: inline implementation
        try:
            proj = QgsProject.instance()
            root = proj.layerTreeRoot()

            group = root.findGroup(group_name)
            if group is None and group_name == "CEVI":
                group = root.findGroup("Pipes")

            if not group:
                return

            parent = group.parent() or root
            children = list(parent.children())

            idx = None
            try:
                gname = group.name()
            except Exception:
                gname = group_name
            for i, ch in enumerate(children):
                try:
                    if getattr(ch, "name", lambda: None)() == gname and not hasattr(ch, "layerId"):
                        idx = i
                        break
                except Exception as e:
                    logger.debug(f"Error in PipeManager.move_group_to_top: {e}")
            if idx is not None and idx > 0:
                taken = parent.takeChild(idx)
                parent.insertChildNode(0, taken)

            try:
                if root.hasCustomLayerOrder():
                    order = list(root.customLayerOrder())

                    def _collect_layers(node):
                        out = []
                        for ch in getattr(node, 'children', lambda: [])():
                            try:
                                if hasattr(ch, "layer") and ch.layer():
                                    out.append(ch.layer())
                                else:
                                    out.extend(_collect_layers(ch))
                            except Exception as e:
                                logger.debug(f"Error in PipeManager._collect_layers: {e}")
                        return out

                    group_layers = _collect_layers(group)
                    keep = [l for l in order if l not in group_layers]  # noqa: E741
                    root.setCustomLayerOrder(list(group_layers) + keep)
            except Exception as e:
                logger.debug(f"Error in PipeManager._collect_layers: {e}")
        except Exception as e:
            logger.debug(f"Error in PipeManager._collect_layers: {e}")

    def ensure_pipes_group(self):
        """
        Create or return the Pipes group in the layer tree.

        Returns:
            QgsLayerTreeGroup for Pipes
        """
        # Try LayerManager first
        if self.layer_manager:
            try:
                return self.layer_manager.ensure_pipes_group()
            except Exception as e:
                logger.debug(f"Error in PipeManager.ensure_pipes_group: {e}")

        # Fallback: inline implementation
        proj = QgsProject.instance()
        root = proj.layerTreeRoot()

        group = root.findGroup("CEVI") or root.findGroup("Pipes")
        if group is None:
            try:
                group = root.insertGroup(0, "Pipes")
            except Exception:
                group = root.addGroup("Pipes")
        else:
            try:
                if group.name() == "CEVI":
                    group.setName("Pipes")
            except Exception as e:
                logger.debug(f"Error in PipeManager.ensure_pipes_group: {e}")

        try:
            self.move_group_to_top("CEVI")
        except Exception as e:
            logger.debug(f"Error in PipeManager.ensure_pipes_group: {e}")
        return group

    # -------------------------------------------------------------------------
    # Field aliases
    # -------------------------------------------------------------------------

    def apply_pipe_field_aliases(self, layer: QgsVectorLayer) -> None:
        """Apply English field aliases to a pipe layer."""
        try:
            from ..utils.field_aliases import apply_pipe_field_aliases
            apply_pipe_field_aliases(layer)
        except Exception as e:
            logger.debug(f"Error in PipeManager.apply_pipe_field_aliases: {e}")

    def set_pipe_layer_alias(self, layer: QgsVectorLayer) -> None:
        """Set English layer names for pipe layers."""
        try:
            from ..utils.field_aliases import set_pipe_layer_alias
            set_pipe_layer_alias(layer)
        except Exception as e:
            logger.debug(f"Error in PipeManager.set_pipe_layer_alias: {e}")

    # -------------------------------------------------------------------------
    # Layer management
    # -------------------------------------------------------------------------

    def ensure_pipe_layer(self, name: str) -> Optional[QgsVectorLayer]:
        """
        Create or return a pipe layer by name.

        Args:
            name: Layer name (e.g., "PE cevi", "Prelazne cevi")

        Returns:
            QgsVectorLayer for the pipe layer
        """
        # Try LayerManager first
        if self.layer_manager:
            try:
                lyr = self.layer_manager.ensure_pipe_layer(name)
                if lyr:
                    try:
                        self.apply_pipe_field_aliases(lyr)
                        self.set_pipe_layer_alias(lyr)
                    except Exception as e:
                        logger.debug(f"Error in PipeManager.ensure_pipe_layer: {e}")
                    return lyr
            except Exception as e:
                logger.debug(f"Error in PipeManager.ensure_pipe_layer: {e}")

        # Fallback: inline implementation
        prj = QgsProject.instance()

        target_names = {name}
        if name in self.LAYER_ALIAS_MAP:
            target_names.add(self.LAYER_ALIAS_MAP[name])

        for lyr in prj.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.LineGeometry  # noqa: W503
                    and lyr.name() in target_names  # noqa: W503
                ):
                    try:
                        self.apply_pipe_field_aliases(lyr)
                        self.set_pipe_layer_alias(lyr)
                    except Exception as e:
                        logger.debug(f"Error in PipeManager.ensure_pipe_layer: {e}")
                    return lyr
            except Exception as e:
                logger.debug(f"Error in PipeManager.ensure_pipe_layer: {e}")

        crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        layer = QgsVectorLayer(f"LineString?crs={crs}", name, "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("materijal", QVariant.String),
            QgsField("kapacitet", QVariant.String),
            QgsField("fi", QVariant.Int),
            QgsField("od", QVariant.String),
            QgsField("do", QVariant.String),
            QgsField("duzina_m", QVariant.Double),
        ])
        layer.updateFields()

        # WP1b identity invariant: ensure the fiberq_uuid column exists.
        try:
            from ..utils.uuid_utils import ensure_uuid_field
            ensure_uuid_field(layer)
        except Exception as e:
            logger.debug(f"Error ensuring fiberq_uuid on pipe layer: {e}")

        try:
            layer.setMapTipTemplate(
                "<b>[% \"materijal\" %] [% \"kapacitet\" %]</b><br/>Ø [% \"fi\" %] mm"
            )
        except Exception as e:
            logger.debug(f"Error in PipeManager.ensure_pipe_layer: {e}")

        prj.addMapLayer(layer, False)
        try:
            group = self.ensure_pipes_group()
            group.addLayer(layer)
        except Exception:
            prj.addMapLayer(layer, True)

        try:
            self.move_group_to_top("CEVI")
        except Exception as e:
            logger.debug(f"Error in PipeManager.ensure_pipe_layer: {e}")

        try:
            self.apply_pipe_field_aliases(layer)
            self.set_pipe_layer_alias(layer)
        except Exception as e:
            logger.debug(f"Error in PipeManager.ensure_pipe_layer: {e}")

        return layer

    def ensure_pe_pipe_layer(self) -> Optional[QgsVectorLayer]:
        """Create or return the PE pipes layer."""
        return self.ensure_pipe_layer("PE cevi")

    def ensure_transition_pipe_layer(self) -> Optional[QgsVectorLayer]:
        """Create or return the Transition pipes layer."""
        return self.ensure_pipe_layer("Prelazne cevi")

    # -------------------------------------------------------------------------
    # Styling
    # -------------------------------------------------------------------------

    def apply_pipe_style(self, layer: QgsVectorLayer, color_hex: str, width_mm: float) -> None:
        """
        Apply styling to a pipe layer.

        Args:
            layer: The pipe layer
            color_hex: Color in hex format (e.g., "#FF0000")
            width_mm: Line width in millimeters
        """
        # Try StyleManager first
        if self.style_manager:
            try:
                self.style_manager.stylize_pipe_layer(layer, color_hex, width_mm)
                return
            except Exception as e:
                logger.debug(f"Error in PipeManager.apply_pipe_style: {e}")

        # Fallback: inline implementation
        try:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            sl = QgsSimpleLineSymbolLayer()
            sl.setColor(QColor(color_hex))
            sl.setWidth(float(width_mm))
            sl.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            try:
                sl.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                sl.setCapStyle(Qt.PenCapStyle.RoundCap)
            except Exception as e:
                logger.debug(f"Error in PipeManager.apply_pipe_style: {e}")
            symbol.deleteSymbolLayer(0)
            symbol.appendSymbolLayer(sl)
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in PipeManager.apply_pipe_style: {e}")

    # -------------------------------------------------------------------------
    # Listing pipes
    # -------------------------------------------------------------------------

    def list_all_pipes(self) -> List[Dict[str, Any]]:
        """
        List all pipes from pipe layers.

        Returns:
            List of pipe dicts with layer_id, fid, opis, etc.
        """
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.list_all_pipes()
            except Exception as e:
                logger.debug(f"Error in PipeManager.list_all_pipes: {e}")

        # Fallback: inline implementation
        items = []
        layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.LineGeometry  # noqa: W503
                        and lyr.name() in self.PIPE_LAYER_NAMES):  # noqa: W503
                    layers.append(lyr)
            except Exception as e:
                logger.debug(f"Error in PipeManager.list_all_pipes: {e}")

        for lyr in layers:
            fields = lyr.fields()
            for f in lyr.getFeatures():
                attrs = {fld.name(): f[fld.name()] for fld in fields}
                materijal = attrs.get('materijal', '') or ''
                kap = attrs.get('kapacitet', '') or ''
                fi = attrs.get('fi', '') or ''
                cap_text = ''
                try:
                    if fi not in (None, ''):
                        cap_text = f"Ø {int(fi)} mm"
                except Exception as e:
                    logger.debug(f"Error in PipeManager.list_all_pipes: {e}")
                if (kap or '').strip():
                    cap_text = (cap_text + (' | ' if cap_text else '')) + str(kap)
                items.append({
                    'layer_id': lyr.id(),
                    'layer_name': lyr.name(),
                    'fid': int(f.id()),
                    'opis': (str(materijal).strip() or 'Pipe') + (f" {cap_text}" if cap_text else ''),
                    'tip': 'pipe',
                    'podtip': 'pipe',
                    'kapacitet': cap_text,
                    'color_code': '',
                    'od': attrs.get('od', '') or '',
                    'do': attrs.get('do', '') or ''
                })
        return items

    # -------------------------------------------------------------------------
    # Workflow handlers
    # -------------------------------------------------------------------------

    def open_pe_duct_workflow(self, plugin) -> None:
        """
        Open PE duct placement workflow.

        Args:
            plugin: The main plugin instance (for dialog and tool references)
        """
        try:
            from ..dialogs.pipe_dialog import PEDuctDialog
            from ..tools.pipe_tool import PipePlaceTool

            dlg = PEDuctDialog(plugin)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            vals = dlg.values()
            plugin._pending_pipe = {'kind': 'PE', **vals}
            tool = PipePlaceTool(self.iface, plugin, 'PE', vals)
            self.iface.mapCanvas().setMapTool(tool)
            self.iface.messageBar().pushInfo("PE duct", "Click start and end on the route/manhole to place the PE duct.")
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "PE duct", f"Error: {e}")

    def open_transition_duct_workflow(self, plugin) -> None:
        """
        Open transition duct placement workflow.

        Args:
            plugin: The main plugin instance (for dialog and tool references)
        """
        try:
            from ..dialogs.pipe_dialog import TransitionDuctDialog
            from ..tools.pipe_tool import PipePlaceTool

            dlg = TransitionDuctDialog(plugin)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            vals = dlg.values()
            plugin._pending_pipe = {'kind': 'PRELAZ', **vals}
            tool = PipePlaceTool(self.iface, plugin, 'PRELAZ', vals)
            self.iface.mapCanvas().setMapTool(tool)
            self.iface.messageBar().pushInfo("Transition duct", "Click start and end on the route/manhole to place the transition duct.")
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Transition duct", f"Error: {e}")


__all__ = ['PipeManager']
