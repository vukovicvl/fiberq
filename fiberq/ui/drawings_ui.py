"""
FiberQ v2 - Drawings UI

Toolbar group for drawing/DWG attachment management.
"""

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
        self.menu = QMenu("Drawings", core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Add drawing
        act_add = QAction(load_icon('ic_add_drawing.svg'), "Add drawing…", core.iface.mainWindow())
        act_add.setToolTip("Link a DWG/DXF drawing to selected element(s)")
        act_add.triggered.connect(core.ui_add_drawing)
        self.menu.addAction(act_add)

        # Open drawing (by click)
        act_open = QAction(load_icon('ic_drawing.svg'), "Open drawing (by click)", core.iface.mainWindow())
        act_open.setToolTip("Click on an element to open its linked drawing")
        act_open.triggered.connect(core.ui_open_drawing_click)
        self.menu.addAction(act_open)

        # Issue #7: Add clear drawing action
        act_clear = QAction(load_icon('ic_drawing.svg'), "Clear drawing from element", core.iface.mainWindow())
        act_clear.setToolTip("Unlink drawing from selected element(s)")
        act_clear.triggered.connect(core.ui_clear_drawing)
        self.menu.addAction(act_clear)

        # Toolbar button
        self.button = QToolButton()
        self.button.setText("Drawings")
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(load_icon('ic_drawing.svg'))
        self.button.setToolTip('Drawings')
        self.button.setStatusTip('Drawings')
        core.toolbar.addWidget(self.button)


__all__ = ['DrawingsUI']
