"""
FiberQ v2 - Ducting UI

Toolbar group for ducting and manhole operations.
"""

from .base import QAction, QMenu, QToolButton, load_icon


class DuctingUI:
    """
    Toolbar group for ducting operations.

    Creates a drop-down menu with actions for:
    - Placing manholes
    - Place PE pipe
    - Place transition pipe
    """

    def __init__(self, core):
        """
        Initialize the ducting UI.

        Args:
            core: Plugin core instance with iface and toolbar
        """
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Placing manholes
        act = QAction(load_icon('ic_place_manholes.svg'), "Placing manholes", core.iface.mainWindow())
        act.triggered.connect(core.open_manhole_workflow)
        self.menu.addAction(act)
        core.actions.append(act)

        # Place PE pipe
        act_pe = QAction(load_icon('ic_place_pe_pipe.svg'), "Place PE pipe", core.iface.mainWindow())
        act_pe.triggered.connect(core.open_pe_cev_workflow)
        self.menu.addAction(act_pe)
        core.actions.append(act_pe)

        # Place transition pipe
        act_pr = QAction(load_icon('ic_place_transition_pipe.svg'), "Place transition pipe", core.iface.mainWindow())
        act_pr.triggered.connect(core.open_transition_duct_workflow)
        self.menu.addAction(act_pr)
        core.actions.append(act_pr)

        # Toolbar button
        self.button = QToolButton()
        self.button.setText("Ducting")
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(load_icon('ic_ducting.svg'))
        self.button.setToolTip('Ducting')
        self.button.setStatusTip('Ducting')
        core.toolbar.addWidget(self.button)


__all__ = ['DuctingUI']
