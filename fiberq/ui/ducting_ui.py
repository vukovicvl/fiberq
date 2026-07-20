"""
FiberQ v2 - Ducting UI

Toolbar group for ducting and manhole operations.
"""

from qgis.PyQt.QtCore import QCoreApplication

from .base import QAction, QMenu, QToolButton, load_icon


class DuctingUI:
    """
    Toolbar group for ducting operations.

    Creates a drop-down menu with actions for:
    - Placing manholes
    - Place PE pipe
    - Place transition pipe
    """

    def tr(self, message):
        """
        Translate a user-facing string.

        Args:
            message: Source (English) string literal

        Returns:
            The translated string for the active locale
        """
        return QCoreApplication.translate('DuctingUI', message)

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
        #: Menu entry, gerund (the ACT of placing), plural. Opens a multi-step
        #: workflow: pick manhole type, fill in its data, then click on the map to
        #: place them one after another. "manhole" = the underground inspection
        #: chamber on a duct run (fr: chambre de tirage, never trou d'homme).
        act = QAction(load_icon('ic_place_manholes.svg'), self.tr("Placing manholes"), core.iface.mainWindow())
        act.triggered.connect(core.open_manhole_workflow)
        self.menu.addAction(act)
        core.actions.append(act)

        # Place PE pipe
        #: Menu entry, imperative. PE = polyethylene. This is the ordinary buried
        #: distribution duct (Ø 40 mm), placed between two points on the route; the
        #: dialog then offers capacities 1x1 to 3x3, i.e. how many ducts form the
        #: duct bank. NB the rest of the app calls this a "duct", not a "pipe" -
        #: same object; translate both with your single word for duct (fr: fourreau).
        act_pe = QAction(load_icon('ic_place_pe_pipe.svg'), self.tr("Place PE pipe"), core.iface.mainWindow())
        act_pe.triggered.connect(core.open_pe_cev_workflow)
        self.menu.addAction(act_pe)
        core.actions.append(act_pe)

        # Place transition pipe
        act_pr = QAction(load_icon('ic_place_transition_pipe.svg'),
                         #: Menu entry, imperative. "Transition" translates the legacy
                         #: term "prelaz" = a CROSSING. This is the large protective
                         #: casing (O 110 mm, in PVC / PE / Oki / galvanised steel)
                         #: laid where the route crosses under a road, railway or
                         #: watercourse; the smaller PE ducts are pulled through it.
                         #: Not a fitting or an adapter between two pipe sizes.
                         self.tr("Place transition pipe"), core.iface.mainWindow())
        act_pr.triggered.connect(core.open_transition_duct_workflow)
        self.menu.addAction(act_pr)
        core.actions.append(act_pr)

        # Toolbar button
        self.button = QToolButton()
        #: Toolbar drop-down button label, tooltip and status tip - the SAME string is
        #: reused 3x here, so one translation must serve all three. Noun: the whole
        #: duct infrastructure (manholes + ducts). Keep it short for a toolbar button.
        self.button.setText(self.tr("Ducting"))
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(load_icon('ic_ducting.svg'))
        #: Toolbar drop-down button label, tooltip and status tip - the SAME string is
        #: reused 3x here, so one translation must serve all three. Noun: the whole
        #: duct infrastructure (manholes + ducts). Keep it short for a toolbar button.
        self.button.setToolTip(self.tr('Ducting'))
        #: Toolbar drop-down button label, tooltip and status tip - the SAME string is
        #: reused 3x here, so one translation must serve all three. Noun: the whole
        #: duct infrastructure (manholes + ducts). Keep it short for a toolbar button.
        self.button.setStatusTip(self.tr('Ducting'))
        core.toolbar.addWidget(self.button)


__all__ = ['DuctingUI']
