"""
FiberQ v2 - Element Placement UI

Toolbar group for placing network elements on the map.
"""

from .base import QAction, QMenu, QToolButton, load_icon, element_icon_for, get_element_defs


class ElementPlacementUI:
    """
    Toolbar group for element placement operations.

    Creates a drop-down menu with actions for:
    - Place Joint Closure
    - Place various element types (ODF, TB, OTB, TO, etc.)
    """

    def __init__(self, core, element_defs=None):
        """
        Initialize the element placement UI.

        Args:
            core: Plugin core instance with iface and toolbar
            element_defs: Optional list of element definitions. If None, uses get_element_defs()
        """
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Place Joint Closure
        action_nast = QAction(load_icon('ic_place_jc.svg'), 'Place Joint Closure', core.iface.mainWindow())
        action_nast.triggered.connect(core.activate_extension_tool)
        core.actions.append(action_nast)
        self.menu.addAction(action_nast)

        self.menu.addSeparator()

        # Element placement actions
        self.element_actions = []
        defs = element_defs if element_defs is not None else get_element_defs()

        for edef in defs:
            name = edef['name']
            symbol = edef.get('symbol')

            a = QAction(element_icon_for(name), f"Place {name}", core.iface.mainWindow())
            a.triggered.connect(
                lambda _=False, n=name, s=symbol: core.activate_place_element_tool(n, s)
            )
            self.menu.addAction(a)
            self.element_actions.append(a)
            core.actions.append(a)

        # Toolbar button
        self.button = QToolButton()
        self.button.setText('Placing elements')
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(load_icon('ic_place_elements.svg'))
        self.button.setToolTip('Placing elements')
        self.button.setStatusTip('Placing elements')
        core.toolbar.addWidget(self.button)


__all__ = ['ElementPlacementUI']
