"""
FiberQ v2 - Slack UI

Toolbar group for optical slack operations.
"""

from qgis.PyQt.QtCore import QCoreApplication

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

    def tr(self, message):
        """Translate a user-facing string in the 'SlackUI' context."""
        return QCoreApplication.translate('SlackUI', message)

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
        #: Menu entry, imperative. "Slack" = the spare length of cable coiled and
        #: stored at a point so it can be re-spliced later (fr: the coil is a "love",
        #: "reserve"; "lovage" is the act of coiling). FiberQ has exactly TWO slack
        #: types and they must stay distinct: TERMINAL slack sits at a cable END
        #: (legacy name "end slack", internally "zavrsna", drawn as a C coil).
        #: "(interactive)" = you click the spot, as opposed to the batch entry below.
        act_zav = QAction(load_icon('ic_slack_midspan.svg'), self.tr('Place terminal slack (interactive)'), core.iface.mainWindow())
        act_zav.triggered.connect(lambda: core._start_slack_interactive("Terminal"))
        core.actions.append(act_zav)
        self.menu.addAction(act_zav)

        # Place mid span slack (interactive)
        #: Menu entry, imperative. The OTHER slack type: MID SPAN slack sits at an
        #: intermediate point where the cable runs THROUGH without being cut (legacy
        #: name "thru slack", internally "prolazna", drawn as an S coil). It is NOT
        #: the same as terminal slack above - do not translate both with one word.
        #: Here "span" = the run between two supports/points, not a bridge span.
        act_prol = QAction(load_icon('ic_slack_midspan.svg'), self.tr('Place mid span slack (interactive)'), core.iface.mainWindow())
        act_prol.triggered.connect(lambda: core._start_slack_interactive("Mid span"))
        core.actions.append(act_prol)
        self.menu.addAction(act_prol)

        # Generate terminal slacks (batch)
        #: Menu entry, imperative. Batch counterpart of the first entry: for every
        #: SELECTED cable it creates a terminal slack at BOTH endpoints at once (20 m
        #: by default), instead of you clicking each one. "ends" = the cable's two
        #: extremities. Long string, but it is a menu entry only - no width limit.
        act_batch = QAction(load_icon('ic_slack_batch.svg'), self.tr('Generate terminal slacks at the ends of selected cables'), core.iface.mainWindow())
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
        #: Toolbar button tooltip and status tip (same string twice). Plural noun
        #: naming the group of slack tools, and the map layer they write to. This
        #: button shows an icon only, so the text appears solely on hover.
        btn.setToolTip(self.tr('Optical slacks'))
        #: Toolbar button tooltip and status tip (same string twice). Plural noun
        #: naming the group of slack tools, and the map layer they write to. This
        #: button shows an icon only, so the text appears solely on hover.
        btn.setStatusTip(self.tr('Optical slacks'))
        core.toolbar.addWidget(btn)


__all__ = ['SlackUI']
