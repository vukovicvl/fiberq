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
    """Dialog for displaying route errors and applying corrections.

    ``show`` is what "Select on map" calls with the finding. The plugin passes
    one that selects the route and centres the map on the end in question;
    without one, the button only selects the route.
    """

    def __init__(self, greske, parent=None, show=None):
        super().__init__(parent)
        self.setWindowTitle("Route correction - found errors")
        layout = QVBoxLayout(self)
        area = QScrollArea(self)
        widget = QWidget()
        vbox = QVBoxLayout()
        for g in greske:
            lbl = QLabel(g['msg'])
            # Q21: a finding now says what the end is not connected to, or
            # which route it touches and what to do, so it runs to 108-190
            # characters where "End of route (ID 15) is NOT on a pole." took
            # 38. QScrollArea asks for at most 36 font heights of width (about
            # 540 px), so the line was cut off behind both scrollbars, which
            # also half-hid Select on map. Wrapped, it fits.
            lbl.setWordWrap(True)
            vbox.addWidget(lbl)
            # Button for correction (if available)
            if 'popravka' in g:
                btn = QPushButton("Correct")
                # Qt sends bool (checked), we ignore it here and call function
                # without args. Q21: a correction that moved the end answers
                # True and greys its button out, so a second press cannot look
                # like a second correction; one that changed nothing leaves it
                # live, with the reason in the message bar.
                btn.clicked.connect(lambda checked=False, func=g['popravka'], button=btn:
                                    button.setEnabled(not func()))
                vbox.addWidget(btn)

            # Button for selecting on map (if feat and layer exist)
            if 'feat' in g and 'layer' in g:
                btn_sel = QPushButton("Select on map")
                # Q21: the same `checked` placeholder as Correct. The handler
                # this replaces was connected bare, as
                # sel_func(feat_id=g['feat'].id(), layer=g['layer']), so Qt's
                # checked=False arrived as feat_id and it selected feature 0;
                # and it zoomed only when the parent had an `iface`, which
                # QGIS's main window has not. So it selected nothing and never
                # moved the map -- since v1.1, measured on 3.22.16, 3.40.15
                # and 4.2.3.
                btn_sel.clicked.connect(lambda checked=False, finding=g: self._select(finding, show))
                vbox.addWidget(btn_sel)
        widget.setLayout(vbox)
        area.setWidget(widget)
        area.setWidgetResizable(True)
        layout.addWidget(area)
        btn_zatvori = QPushButton("Close")
        btn_zatvori.clicked.connect(self.accept)
        layout.addWidget(btn_zatvori)
        # Q21: and a scrollbar's width to spare. A wrapped label is as tall as
        # its width makes it, and QScrollArea measures it at the width its
        # vertical scrollbar leaves. Opened at exactly the width the labels ask
        # for, the text took another line there, so the scrollbar stayed and
        # hid Select on map (seen in QGIS 3.40.15 and 4.2.3). With room for
        # it, neither scrollbar shows.
        hint = self.sizeHint()
        self.resize(hint.width() + area.verticalScrollBar().sizeHint().width(), hint.height())

    @staticmethod
    def _select(finding, show):
        """Select the finding's route, clearing every other selection; ``show`` does more."""
        if show is not None:
            show(finding)
            return
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer):
                lyr.removeSelection()
        finding['layer'].selectByIds([finding['feat'].id()])


__all__ = ['CorrectionDialog']
