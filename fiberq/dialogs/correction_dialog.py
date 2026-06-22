# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Route Correction Dialog.

This module contains the dialog for displaying and correcting route errors.
"""

from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
)

from qgis.core import QgsVectorLayer, QgsProject

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class CorrectionDialog(QDialog):
    """Dialog for displaying route errors and applying corrections."""

    def __init__(self, greske, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Route correction - found errors")
        layout = QVBoxLayout(self)
        area = QScrollArea(self)
        widget = QWidget()
        vbox = QVBoxLayout()
        for g in greske:
            lbl = QLabel(g['msg'])
            vbox.addWidget(lbl)
            # Button for correction (if available)
            if 'popravka' in g:
                btn = QPushButton("Correct")
                # Qt sends bool (checked), we ignore it here and call function without args
                btn.clicked.connect(lambda checked=False, func=g['popravka']: func())
                vbox.addWidget(btn)

            # Button for selecting on map (if feat and layer exist)
            if 'feat' in g and 'layer' in g:
                btn_sel = QPushButton("Select on map")
                # Create function that selects and zooms to feature

                def sel_func(feat_id=g['feat'].id(), layer=g['layer']):
                    # Clear selection on all layers
                    for lyr in QgsProject.instance().mapLayers().values():
                        if isinstance(lyr, QgsVectorLayer):
                            lyr.removeSelection()
                    layer.selectByIds([feat_id])
                    # Zoom to feature
                    parent_iface = self.parent().iface if hasattr(self.parent(), 'iface') else None
                    if parent_iface:
                        parent_iface.mapCanvas().zoomToSelected(layer)
                btn_sel.clicked.connect(sel_func)
                vbox.addWidget(btn_sel)
        widget.setLayout(vbox)
        area.setWidget(widget)
        area.setWidgetResizable(True)
        layout.addWidget(area)
        btn_zatvori = QPushButton("Close")
        btn_zatvori.clicked.connect(self.accept)
        layout.addWidget(btn_zatvori)


__all__ = ['CorrectionDialog']
