"""
FiberQ v2 - Image Map Tool

Map tool for opening attached images for elements.
Phase 2.1: Extracted from extracted_classes.py
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QScrollArea, QWidget, QLabel, QPushButton, QMessageBox
)
from qgis.gui import QgsMapToolIdentify

# Import from legacy bridge for compatibility
from ..utils.legacy_bridge import _img_get

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class _ImagePopup(QDialog):
    """Popup dialog for displaying element images."""

    def __init__(self, path, parent=None, title="FiberQ Image"):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        scr = QScrollArea(self)
        scr.setWidgetResizable(True)
        cont = QWidget()
        scr.setWidget(cont)
        lay2 = QVBoxLayout(cont)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = QPixmap(path)
        if not pm or pm.isNull():
            lbl.setText(f"I can't load the image.:\n{path}")
        else:
            # Scale down if huge
            maxw, maxh = 800, 600
            if pm.width() > maxw or pm.height() > maxh:
                pm = pm.scaled(maxw, maxh, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(pm)
        lay2.addWidget(lbl)
        lay.addWidget(scr)

        # Large close button
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close)


class OpenImageMapTool(QgsMapToolIdentify):
    """Click an element to open its attached image (jpg/png) in a popup."""

    def __init__(self, core):
        super().__init__(core.iface.mapCanvas())
        self.core = core
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def canvasReleaseEvent(self, e):
        res = self.identify(e.pos().x(), e.pos().y(), self.TopDownAll, self.VectorLayer)
        for hit in res or []:
            layer = hit.mLayer
            fid = hit.mFeature.id()
            path = _img_get(layer, fid)
            if path:
                dlg = _ImagePopup(path, self.core.iface.mainWindow(), title="Element picture")
                dlg.exec()
                return
        QMessageBox.information(
            self.core.iface.mainWindow(),
            "FiberQ",
            "No image is attached to the selected element."
        )


__all__ = ['OpenImageMapTool', '_ImagePopup']
