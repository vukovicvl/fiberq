"""
FiberQ v2 - Drawings UI

Toolbar group for drawing/DWG attachment management.
"""

from qgis.PyQt.QtCore import QCoreApplication

from .base import QAction, QMenu, QToolButton, load_icon


class DrawingsUI:
    """
    Toolbar group for drawing operations.

    Creates a drop-down menu with actions for:
    - Add drawing
    - Open drawing (by click)
    - Clear drawing (unlink)
    """

    def __init__(self, core):
        """
        Initialize the drawings UI.

        Args:
            core: Plugin core instance with iface and toolbar
        """
        self.core = core
        #: Menu title, toolbar button label, tooltip and status tip - the SAME string
        #: is reused 4x here, so one translation must serve all four. Plural noun:
        #: external CAD files (DWG/DXF) LINKED to map elements, i.e. documents, not
        #: something you draw in QGIS. Distinct from the "Drawing object" button,
        #: which digitises a building outline. Keep short for a toolbar button.
        self.menu = QMenu(self.tr("Drawings"), core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Add drawing
        #: Menu entry, imperative. Attaches an existing CAD file to the selected
        #: element(s). The trailing character is a real ellipsis (U+2026), Qt's
        #: convention for "opens a dialog" - please keep it.
        act_add = QAction(load_icon('ic_add_drawing.svg'), self.tr("Add drawing…"), core.iface.mainWindow())
        #: Tooltip for the entry above. DWG and DXF are AutoCAD file formats - keep
        #: both as-is. "element(s)" is written with an optional plural in brackets;
        #: use whatever plural form reads naturally in your language.
        act_add.setToolTip(self.tr("Link a DWG/DXF drawing to selected element(s)"))
        act_add.triggered.connect(core.ui_add_drawing)
        self.menu.addAction(act_add)

        # Open drawing (by click)
        #: Menu entry, imperative. Opens the CAD file attached to an element in the
        #: system's default application. "(by click)" tells the user the element is
        #: chosen by clicking it on the map afterwards.
        act_open = QAction(load_icon('ic_drawing.svg'), self.tr("Open drawing (by click)"), core.iface.mainWindow())
        #: Tooltip for the entry above; a full sentence instructing the user.
        act_open.setToolTip(self.tr("Click on an element to open its linked drawing"))
        act_open.triggered.connect(core.ui_open_drawing_click)
        self.menu.addAction(act_open)

        # Issue #7: Add clear drawing action
        #: Menu entry, imperative. Removes the LINK between the element and its CAD
        #: file. The file on disk is not deleted and the element is not deleted -
        #: only the attachment is dropped. "Clear ... from" = unlink, see tooltip.
        act_clear = QAction(load_icon('ic_drawing.svg'), self.tr("Clear drawing from element"), core.iface.mainWindow())
        #: Tooltip for the entry above. "Unlink" confirms nothing is deleted.
        act_clear.setToolTip(self.tr("Unlink drawing from selected element(s)"))
        act_clear.triggered.connect(core.ui_clear_drawing)
        self.menu.addAction(act_clear)

        # Toolbar button
        self.button = QToolButton()
        #: Menu title, toolbar button label, tooltip and status tip - the SAME string
        #: is reused 4x here, so one translation must serve all four. Plural noun:
        #: external CAD files (DWG/DXF) LINKED to map elements, i.e. documents, not
        #: something you draw in QGIS. Distinct from the "Drawing object" button,
        #: which digitises a building outline. Keep short for a toolbar button.
        self.button.setText(self.tr("Drawings"))
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(load_icon('ic_drawing.svg'))
        #: Menu title, toolbar button label, tooltip and status tip - the SAME string
        #: is reused 4x here, so one translation must serve all four. Plural noun:
        #: external CAD files (DWG/DXF) LINKED to map elements, i.e. documents, not
        #: something you draw in QGIS. Distinct from the "Drawing object" button,
        #: which digitises a building outline. Keep short for a toolbar button.
        self.button.setToolTip(self.tr("Drawings"))
        #: Menu title, toolbar button label, tooltip and status tip - the SAME string
        #: is reused 4x here, so one translation must serve all four. Plural noun:
        #: external CAD files (DWG/DXF) LINKED to map elements, i.e. documents, not
        #: something you draw in QGIS. Distinct from the "Drawing object" button,
        #: which digitises a building outline. Keep short for a toolbar button.
        self.button.setStatusTip(self.tr("Drawings"))
        core.toolbar.addWidget(self.button)

    def tr(self, message):
        """Translate a message using the DrawingsUI context."""
        return QCoreApplication.translate('DrawingsUI', message)


__all__ = ['DrawingsUI']
