"""
FiberQ v2 - Slack UI

Toolbar group for optical slack operations.
"""

from .base import Qt, QAction, QMenu, QToolButton, load_icon

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class SlackUI:
    """
    Toolbar group for optical slack operations.

    Creates a drop-down menu with actions for:
    - Place terminal slack (interactive)
    - Place mid span slack (interactive)
    - Generate terminal slacks at cable ends (batch)
    """

    def __init__(self, core):
        """
        Initialize the slack UI.

        Args:
            core: Plugin core instance with iface and toolbar
        """
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Place terminal slack (interactive)
        act_zav = QAction(load_icon('ic_slack_midspan.svg'), 'Place terminal slack (interactive)', core.iface.mainWindow())
        act_zav.triggered.connect(lambda: core._start_slack_interactive("Terminal"))
        core.actions.append(act_zav)
        self.menu.addAction(act_zav)

        # Place mid span slack (interactive)
        act_prol = QAction(load_icon('ic_slack_midspan.svg'), 'Place mid span slack (interactive)', core.iface.mainWindow())
        act_prol.triggered.connect(lambda: core._start_slack_interactive("Mid span"))
        core.actions.append(act_prol)
        self.menu.addAction(act_prol)

        # Generate terminal slacks (batch)
        act_batch = QAction(load_icon('ic_slack_batch.svg'), 'Generate terminal slacks at the ends of selected cables', core.iface.mainWindow())
        act_batch.triggered.connect(core.generate_terminal_slack_for_selected)
        core.actions.append(act_batch)
        self.menu.addAction(act_batch)

        # Toolbar button
        btn = QToolButton()
        btn.setText('')
        try:
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        except Exception as e:
            logger.debug(f"Error in SlackUI.__init__: {e}")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setMenu(self.menu)
        btn.setIcon(load_icon('ic_slack_midspan.svg'))
        btn.setToolTip('Optical slacks')
        btn.setStatusTip('Optical slacks')
        core.toolbar.addWidget(btn)


__all__ = ['SlackUI']
