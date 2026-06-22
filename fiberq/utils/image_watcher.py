# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Canvas Image Click Watcher.

This module contains the event watcher for auto-displaying element images
when clicking on the map canvas.
"""

from qgis.PyQt.QtCore import QObject, QEvent, Qt

from ..utils.legacy_bridge import _img_get, _fiberq_translate, _get_lang
from ..tools.image_tool import _ImagePopup

# Phase 5.2: Logging
from .logger import get_logger
logger = get_logger(__name__)


class CanvasImageClickWatcher(QObject):
    """Global watcher: on left-click over any element that has an attached image, show popup."""

    def __init__(self, core):
        super().__init__(core.iface.mapCanvas())
        self.core = core

    def eventFilter(self, obj, event):
        try:
            from qgis.gui import QgsMapToolIdentify
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                canvas = self.core.iface.mapCanvas()
                # Don't interfere while our explicit tools are active
                active = canvas.mapTool()
                if active and (active.__class__.__name__ in ("MoveFeatureTool", "OpenImageMapTool")):
                    return False
                ident = QgsMapToolIdentify(canvas)
                res = ident.identify(event.x(), event.y(), ident.TopDownAll, ident.VectorLayer)
                for hit in res or []:
                    layer = hit.mLayer
                    fid = hit.mFeature.id()
                    path = _img_get(layer, fid)
                    if path:
                        dlg = _ImagePopup(path, self.core.iface.mainWindow(), title=_fiberq_translate("Open image (click)", _get_lang()))
                        dlg.exec()
                        # Do not swallow the event; let normal selection continue
                        return False
        except Exception as e:
            logger.debug(f"Error in CanvasImageClickWatcher.eventFilter: {e}")
        return False


__all__ = ['CanvasImageClickWatcher']
