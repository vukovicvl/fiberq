"""
FiberQ v2 - Cable Laying UI

Toolbar group for cable laying operations.
"""

from qgis.PyQt.QtCore import QCoreApplication

from .base import QAction, QMenu, QToolButton, load_icon


class CableLayingUI:
    """
    Toolbar group for cable laying operations.

    Creates a drop-down menu with submenus for:
    - Underground cables (Backbone, Distribution, Drop)
    - Aerial cables (Backbone, Distribution, Drop)
    """

    def __init__(self, core):
        """
        Initialize the cable laying UI.

        Args:
            core: Plugin core instance with iface and toolbar
        """
        self.core = core
        #: Title of the top-level cable menu, and the label/tooltip/status tip of the
        #: toolbar button that opens it. Gerund: the ACT of laying (installing) optical
        #: cable on the map. This same string is reused 4x in this file - one translation
        #: must fit both a menu title and a compact toolbar button label.
        self.menu_kabl = QMenu(self.tr("Cable laying"), core.iface.mainWindow())
        self.menu_kabl.setToolTipsVisible(True)

        # Underground cables submenu
        #: Submenu title under "Cable laying". Adjective: cable laid below ground in
        #: ducts or trenches. Pairs with "Aerial". Groups the Backbone/Distribution/Drop
        #: entries into their underground variants.
        self.menu_kabl_podzemni = QMenu(self.tr("Underground"), self.menu_kabl)
        self.menu_kabl_podzemni.setIcon(load_icon('ic_cable_underground.svg'))

        #: Cable class (noun). The transport/feeder cable carrying traffic between the
        #: main network nodes. Menu entry appearing under BOTH the "Underground" and the
        #: "Aerial" submenu, so one translation serves both parents.
        act_pg = QAction(load_icon('ic_underground_backbone.svg'), self.tr("Backbone"), core.iface.mainWindow())
        act_pg.triggered.connect(lambda: core.lay_cable_type("podzemni", "glavni"))
        self.menu_kabl_podzemni.addAction(act_pg)

        #: Cable class (noun, used attributively: "distribution cable"). The mid-level
        #: cable running from a backbone node out to the street distribution points.
        #: Menu entry appearing under BOTH "Underground" and "Aerial" - one translation
        #: serves both parents.
        act_pd = QAction(load_icon('ic_underground_distributive.svg'), self.tr("Distribution"),
                         core.iface.mainWindow())
        act_pd.triggered.connect(lambda: core.lay_cable_type("podzemni", "distributivni"))
        self.menu_kabl_podzemni.addAction(act_pd)

        #: Cable class. "Drop" is a NOUN here (drop cable / subscriber cable) - the final
        #: span from the street distribution point to a single subscriber's premises.
        #: NOT the verb "to drop". Menu entry appearing under BOTH "Underground" and
        #: "Aerial" - one translation serves both parents.
        act_pr = QAction(load_icon('ic_underground_drop.svg'), self.tr("Drop"), core.iface.mainWindow())
        act_pr.triggered.connect(lambda: core.lay_cable_type("podzemni", "razvodni"))
        self.menu_kabl_podzemni.addAction(act_pr)

        # Aerial cables submenu
        #: Submenu title under "Cable laying". Adjective: cable strung overhead on poles.
        #: Pairs with "Underground". Groups the Backbone/Distribution/Drop entries into
        #: their aerial variants.
        self.menu_kabl_vazdusni = QMenu(self.tr("Aerial"), self.menu_kabl)
        self.menu_kabl_vazdusni.setIcon(load_icon('ic_cable_aerial.svg'))

        #: Cable class (noun). The transport/feeder cable carrying traffic between the
        #: main network nodes. Menu entry appearing under BOTH the "Underground" and the
        #: "Aerial" submenu, so one translation serves both parents.
        act_vg = QAction(load_icon('ic_aerial_backbone.svg'), self.tr("Backbone"), core.iface.mainWindow())
        act_vg.triggered.connect(lambda: core.lay_cable_type("vazdusni", "glavni"))
        self.menu_kabl_vazdusni.addAction(act_vg)

        #: Cable class (noun, used attributively: "distribution cable"). The mid-level
        #: cable running from a backbone node out to the street distribution points.
        #: Menu entry appearing under BOTH "Underground" and "Aerial" - one translation
        #: serves both parents.
        act_vd = QAction(load_icon('ic_aerial_distributive.svg'), self.tr("Distribution"), core.iface.mainWindow())
        act_vd.triggered.connect(lambda: core.lay_cable_type("vazdusni", "distributivni"))
        self.menu_kabl_vazdusni.addAction(act_vd)

        #: Cable class. "Drop" is a NOUN here (drop cable / subscriber cable) - the final
        #: span from the street distribution point to a single subscriber's premises.
        #: NOT the verb "to drop". Menu entry appearing under BOTH "Underground" and
        #: "Aerial" - one translation serves both parents.
        act_vr = QAction(load_icon('ic_aerial_drop.svg'), self.tr("Drop"), core.iface.mainWindow())
        act_vr.triggered.connect(lambda: core.lay_cable_type("vazdusni", "razvodni"))
        self.menu_kabl_vazdusni.addAction(act_vr)

        # Add submenus to main menu
        self.menu_kabl.addMenu(self.menu_kabl_podzemni)
        self.menu_kabl.addMenu(self.menu_kabl_vazdusni)

        # Toolbar button
        self.btn_kabl = QToolButton()
        #: Toolbar button label. Same string as the menu title above - gerund, the ACT of
        #: laying (installing) optical cable. Keep short: it sits on a toolbar button.
        self.btn_kabl.setText(self.tr("Cable laying"))
        self.btn_kabl.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_kabl.setMenu(self.menu_kabl)
        self.btn_kabl.setIcon(load_icon('ic_laying_cable.svg'))
        #: Hover tooltip for the "Cable laying" toolbar button. Same string as the button
        #: label and the menu title - gerund, the ACT of laying optical cable.
        self.btn_kabl.setToolTip(self.tr("Cable laying"))
        #: Status-bar hint for the "Cable laying" toolbar button. Same string as the
        #: button label and the menu title - gerund, the ACT of laying optical cable.
        self.btn_kabl.setStatusTip(self.tr("Cable laying"))
        core.toolbar.addWidget(self.btn_kabl)

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """
        Translate a UI string using the Qt translation system.

        The context string must stay exactly equal to this class name, because
        pylupdate6 derives the .ts <context> from the enclosing class.

        Args:
            message: String literal to translate

        Returns:
            Translated string for the active locale
        """
        return QCoreApplication.translate('CableLayingUI', message)


__all__ = ['CableLayingUI']
