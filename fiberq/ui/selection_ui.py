"""
FiberQ v2 - Selection UI

Toolbar group for selection operations.
"""

from qgis.PyQt.QtCore import QCoreApplication

from .base import QAction, QMenu, QToolButton, load_icon


class SelectionUI:
    """
    Toolbar group for selection operations.

    Creates a drop-down menu with actions for:
    - Smart selection (multiple layers)
    - Clear selection
    - Delete selected
    """

    def tr(self, message):
        """
        Translate a user-facing string.

        Args:
            message: String literal to translate

        Returns:
            Translated string for the active locale
        """
        return QCoreApplication.translate('SelectionUI', message)

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
        core.action_smart_select = QAction(
            #: Menu entry, noun phrase. A click-to-toggle selection tool that can pick
            #: features from SEVERAL layers at once without changing the active layer,
            #: and leaves selections on other layers untouched. "Smart" qualifies
            #: "selection"; the parenthesis explains the scope - keep the brackets.
            icon_sel, self.tr('Smart selection (Multiple Layers)'), core.iface.mainWindow()
        )
        core.action_smart_select.triggered.connect(core.activate_smart_select_tool)
        core.actions.append(core.action_smart_select)
        self.menu.addAction(core.action_smart_select)

        # Clear selection
        #: Menu entry, imperative. NON-DESTRUCTIVE: it only DESELECTS - it removes the
        #: selection highlight from every layer and deletes nothing. It sits directly
        #: above "Delete selected", which does destroy data, so the two must be
        #: unmistakably different in your language. Use your verb for "deselect".
        core.action_clear_selection = QAction(icon_sel, self.tr('Clear selection'), core.iface.mainWindow())
        core.action_clear_selection.triggered.connect(core.clear_all_selections)
        core.actions.append(core.action_clear_selection)
        self.menu.addAction(core.action_clear_selection)

        # Delete selected
        icon_del = load_icon('ic_delete_selected.svg')
        #: Menu entry, imperative. DESTRUCTIVE: permanently deletes the selected
        #: features from every editable layer. "selected" is an elliptical noun
        #: ("the selected features"). Must read as clearly more dangerous than
        #: "Clear selection" above, which merely deselects.
        core.action_del = QAction(icon_del, self.tr('Delete selected'), core.iface.mainWindow())
        core.action_del.triggered.connect(core.delete_selected)
        core.actions.append(core.action_del)
        self.menu.addAction(core.action_del)

        # Toolbar button
        self.button = QToolButton()
        #: Toolbar drop-down button label, tooltip and status tip - the SAME string is
        #: reused 3x here, so one translation must serve all three. Noun naming the
        #: group of selection tools. Keep it short for a toolbar button.
        self.button.setText(self.tr('Selection'))
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(load_icon('ic_selection.svg'))
        #: Toolbar drop-down button label, tooltip and status tip - the SAME string is
        #: reused 3x here, so one translation must serve all three. Noun naming the
        #: group of selection tools. Keep it short for a toolbar button.
        self.button.setToolTip(self.tr('Selection'))
        #: Toolbar drop-down button label, tooltip and status tip - the SAME string is
        #: reused 3x here, so one translation must serve all three. Noun naming the
        #: group of selection tools. Keep it short for a toolbar button.
        self.button.setStatusTip(self.tr('Selection'))
        core.toolbar.addWidget(self.button)


__all__ = ['SelectionUI']
