"""
FiberQ v2 - Selection UI

Toolbar group for selection operations.
"""

from .base import QAction, QMenu, QToolButton, load_icon


class SelectionUI:
    """
    Toolbar group for selection operations.

    Creates a drop-down menu with actions for:
    - Smart selection (multiple layers)
    - Clear selection
    - Delete selected
    """

    def __init__(self, core):
        """
        Initialize the selection UI.

        Args:
            core: Plugin core instance with iface and toolbar
        """
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Smart selection
        icon_sel = load_icon('ic_selection.svg')
        core.action_smart_select = QAction(icon_sel, 'Smart selection (Multiple Layers)', core.iface.mainWindow())
        core.action_smart_select.triggered.connect(core.activate_smart_select_tool)
        core.actions.append(core.action_smart_select)
        self.menu.addAction(core.action_smart_select)

        # Clear selection
        core.action_clear_selection = QAction(icon_sel, 'Clear selection', core.iface.mainWindow())
        core.action_clear_selection.triggered.connect(core.clear_all_selections)
        core.actions.append(core.action_clear_selection)
        self.menu.addAction(core.action_clear_selection)

        # Delete selected
        icon_del = load_icon('ic_delete_selected.svg')
        core.action_del = QAction(icon_del, 'Delete selected', core.iface.mainWindow())
        core.action_del.triggered.connect(core.delete_selected)
        core.actions.append(core.action_del)
        self.menu.addAction(core.action_del)

        # Toolbar button
        self.button = QToolButton()
        self.button.setText('Selection')
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(load_icon('ic_selection.svg'))
        self.button.setToolTip('Selection')
        self.button.setStatusTip('Selection')
        core.toolbar.addWidget(self.button)


__all__ = ['SelectionUI']
