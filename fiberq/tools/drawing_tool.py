"""
FiberQ v2 - Drawing Map Tool

Map tool for opening attached drawings (DWG/DXF) for elements.
Phase 2.1: Extracted from extracted_classes.py
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsProject
from qgis.gui import QgsMapToolIdentify

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class OpenDrawingMapTool(QgsMapToolIdentify):
    """
    Map tool: click an element to open its attached drawing (DWG/DXF) in the OS default app.
    Right click or ESC cancels the command.
    """

    def __init__(self, core):
        super().__init__(core.iface.mapCanvas())
        self.core = core
        self._Qt = Qt
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _cancel(self):
        try:
            self.core.iface.mapCanvas().unsetMapTool(self)
        except Exception as e:
            logger.debug(f"Error in OpenDrawingMapTool._cancel: {e}")
        try:
            self.core.iface.messageBar().pushInfo("Drawing", "Command cancelled.")
        except Exception as e:
            logger.debug(f"Error in OpenDrawingMapTool._cancel: {e}")

    def canvasReleaseEvent(self, e):
        # Right click = exit tool
        try:
            if e.button() == Qt.MouseButton.RightButton:
                self._cancel()
                return
        except Exception as e:
            logger.debug(f"Error in OpenDrawingMapTool.canvasReleaseEvent: {e}")

        # Left click = identify + open drawing if exists
        res = self.identify(e.pos().x(), e.pos().y(), self.TopDownAll, self.VectorLayer)
        if not res:
            QMessageBox.information(self.core.iface.mainWindow(), "Drawing", "You did not click on any feature.")
            return

        for hit in res:
            layer = hit.mLayer
            fid = hit.mFeature.id()
            path = self.core._drawing_get(layer, fid)
            if path:
                ids = self.core._drawing_layers_get(layer, fid)

                # Legacy: if no ids (old projects), just open
                if not ids:
                    self.core._open_drawing_path(path)
                    return

                # Open only if at least one of those DWG layers is still in the project
                root = QgsProject.instance().layerTreeRoot()

                def _node_present_and_visible(lid: str) -> bool:
                    node = root.findLayer(lid)  # search in Layers panel
                    if node is None:
                        return False
                    # If group/layer is off (invisible), treat as "not loaded"
                    try:
                        return node.isVisible()
                    except Exception as e:
                        try:
                            return node.itemVisibilityChecked()
                        except Exception as e:
                            return True

                any_loaded = any(_node_present_and_visible(lid) for lid in ids)

                if not any_loaded:
                    QMessageBox.information(self.core.iface.mainWindow(), "Drawing",
                                "This drawing is linked, but its DWG/DXF layer is not loaded in the project anymore (layer was removed).")
                    return

                self.core._open_drawing_path(path)
                return

    def keyPressEvent(self, e):
        # ESC = exit tool
        try:
            if e.key() == Qt.Key.Key_Escape:
                self._cancel()
                return
        except Exception as e:
            logger.debug(f"Error in OpenDrawingMapTool.keyPressEvent: {e}")
        try:
            super().keyPressEvent(e)
        except Exception as e:
            logger.debug(f"Error in OpenDrawingMapTool.keyPressEvent: {e}")


__all__ = ['OpenDrawingMapTool']
