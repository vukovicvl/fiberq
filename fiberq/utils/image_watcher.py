# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Canvas Image Click Watcher.

This module contains the event watcher for auto-displaying element images
when clicking on the map canvas.
"""

from qgis.PyQt.QtCore import QCoreApplication, QObject, QEvent, Qt

from ..utils.legacy_bridge import _img_get, _fiberq_translate, _get_lang
from ..tools.image_tool import _ImagePopup
from .errors import report_error

# Phase 5.2: Logging
from .logger import get_logger
logger = get_logger(__name__)


class CanvasImageClickWatcher(QObject):
    """Global watcher: on left-click over any element that has an attached image, show popup."""

    def __init__(self, core):
        super().__init__(core.iface.mapCanvas())
        self.core = core

    def eventFilter(self, obj, event):
        """Open the attached picture when an element is clicked.

        WP4 4.2 item R12. This used to read the click position with
        ``event.x()`` / ``event.y()``. Those accessors were removed from
        ``QMouseEvent`` in Qt6: on QGIS 4 they raise ``AttributeError``
        (measured on 4.0.3; they are present on 3.44.15). The handler caught it
        and logged at debug level, which at the default log level writes
        nothing -- so on QGIS 4 clicking an element with a picture did nothing
        at all, for every element, with no error and nothing in the log.

        ``event.pos()`` exists on both and answers integers on both, which is
        what ``identify()`` wants. ``event.position()`` is the Qt6 spelling but
        is absent on Qt5 and returns floats, so it is not the portable choice.
        """
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        try:
            self._show_picture_under(event)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            # An event filter must not raise: an exception here reaches Qt,
            # not Python. Reported rather than logged at debug, because a
            # swallow at exactly this spot is what hid R12 for a whole
            # release.
            report_error(
                QCoreApplication.translate('FiberQImages', "Open image"),
                None, exc, getattr(self.core, 'iface', None))
        return False

    def _show_picture_under(self, event):
        """Identify what was clicked and show its picture, if it has one."""
        from qgis.gui import QgsMapToolIdentify

        canvas = self.core.iface.mapCanvas()
        # Don't interfere while our explicit tools are active
        active = canvas.mapTool()
        if active and (active.__class__.__name__ in ("MoveFeatureTool", "OpenImageMapTool")):
            return
        point = event.pos()
        ident = QgsMapToolIdentify(canvas)
        res = ident.identify(int(point.x()), int(point.y()),
                             ident.TopDownAll, ident.VectorLayer)
        for hit in res or []:
            layer = hit.mLayer
            fid = hit.mFeature.id()
            path = _img_get(layer, fid)
            if path:
                dlg = _ImagePopup(path, self.core.iface.mainWindow(), title=_fiberq_translate("Open image (click)", _get_lang()))
                dlg.exec()
                return


__all__ = ['CanvasImageClickWatcher']
