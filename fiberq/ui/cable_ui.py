"""
FiberQ v2 - Cable Laying UI

Toolbar group for cable laying operations.
"""

from .base import QAction, QMenu, QToolButton, load_icon


class CableLayingUI:
    """
    Toolbar group for cable laying operations.

    Creates a drop-down menu with submenus for:
    - Underground cables (Backbone, Distributive, Drop)
    - Aerial cables (Backbone, Distributive, Drop)
    """

    def __init__(self, core):
        """
        Initialize the cable laying UI.

        Args:
            core: Plugin core instance with iface and toolbar
        """
        self.core = core
        self.menu_kabl = QMenu("Cable laying", core.iface.mainWindow())
        self.menu_kabl.setToolTipsVisible(True)

        # Underground cables submenu
        self.menu_kabl_podzemni = QMenu("Underground", self.menu_kabl)
        self.menu_kabl_podzemni.setIcon(load_icon('ic_cable_underground.svg'))

        act_pg = QAction(load_icon('ic_underground_backbone.svg'), "Backbone", core.iface.mainWindow())
        act_pg.triggered.connect(lambda: core.lay_cable_type("podzemni", "glavni"))
        self.menu_kabl_podzemni.addAction(act_pg)

        act_pd = QAction(load_icon('ic_underground_distributive.svg'), "Distributive", core.iface.mainWindow())
        act_pd.triggered.connect(lambda: core.lay_cable_type("podzemni", "distributivni"))
        self.menu_kabl_podzemni.addAction(act_pd)

        act_pr = QAction(load_icon('ic_underground_drop.svg'), "Drop", core.iface.mainWindow())
        act_pr.triggered.connect(lambda: core.lay_cable_type("podzemni", "razvodni"))
        self.menu_kabl_podzemni.addAction(act_pr)

        # Aerial cables submenu
        self.menu_kabl_vazdusni = QMenu("Aerial", self.menu_kabl)
        self.menu_kabl_vazdusni.setIcon(load_icon('ic_cable_aerial.svg'))

        act_vg = QAction(load_icon('ic_aerial_backbone.svg'), "Backbone", core.iface.mainWindow())
        act_vg.triggered.connect(lambda: core.lay_cable_type("vazdusni", "glavni"))
        self.menu_kabl_vazdusni.addAction(act_vg)

        act_vd = QAction(load_icon('ic_aerial_distributive.svg'), "Distributive", core.iface.mainWindow())
        act_vd.triggered.connect(lambda: core.lay_cable_type("vazdusni", "distributivni"))
        self.menu_kabl_vazdusni.addAction(act_vd)

        act_vr = QAction(load_icon('ic_aerial_drop.svg'), "Drop", core.iface.mainWindow())
        act_vr.triggered.connect(lambda: core.lay_cable_type("vazdusni", "razvodni"))
        self.menu_kabl_vazdusni.addAction(act_vr)

        # Add submenus to main menu
        self.menu_kabl.addMenu(self.menu_kabl_podzemni)
        self.menu_kabl.addMenu(self.menu_kabl_vazdusni)

        # Toolbar button
        self.btn_kabl = QToolButton()
        self.btn_kabl.setText("Cable laying")
        self.btn_kabl.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_kabl.setMenu(self.menu_kabl)
        self.btn_kabl.setIcon(load_icon('ic_laying_cable.svg'))
        self.btn_kabl.setToolTip('Cable laying')
        self.btn_kabl.setStatusTip('Cable laying')
        core.toolbar.addWidget(self.btn_kabl)


__all__ = ['CableLayingUI']
