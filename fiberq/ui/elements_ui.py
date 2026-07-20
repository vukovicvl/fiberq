"""
FiberQ v2 - Element Placement UI

Toolbar group for placing network elements on the map.
"""

from qgis.PyQt.QtCore import QCoreApplication

from ..i18n import safe_format

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
        #: Menu entry: starts the tool that places one joint closure (splice
        #: closure, fr "BPE", sr "nastavak") on the map. "Place" is a VERB in the
        #: imperative; "Joint Closure" is a singular noun phrase.
        action_nast = QAction(load_icon('ic_place_jc.svg'), self.tr('Place Joint Closure'), core.iface.mainWindow())
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

            # 'name' is the runtime IDENTIFIER and must stay untouched: it drives
            # element_icon_for() and the layer/tool identity passed to
            # activate_place_element_tool(). Only the visible label is localised,
            # via the 'ElementNames' catalogue where models/element_defs.py marks
            # each literal with QT_TRANSLATE_NOOP under the same context.
            display = QCoreApplication.translate('ElementNames', name)

            #: Menu entry: places one network element of the given type on the
            #: map. "Place" is a VERB in the imperative. {name} is the element
            #: type (ODF, Indoor OTB, Pole TO, ...), translated separately -- keep
            #: the {name} placeholder exactly as it is and do not translate it here.
            #: Gendered languages: the article cannot be agreed at runtime, since
            #: one label serves every element (fr "une chambre" vs "un poteau"), so
            #: prefer an article-free construction such as "Placer : {name}".
            # safe_format, not str.format: this runs while the toolbar is being
            # built, and the format string comes from a hand-edited catalogue.
            # A renamed placeholder would otherwise abort plugin loading here.
            label = safe_format(self.tr("Place {name}"), "Place {name}", name=display)
            a = QAction(element_icon_for(name), label, core.iface.mainWindow())
            a.triggered.connect(
                lambda _=False, n=name, s=symbol: core.activate_place_element_tool(n, s)
            )
            self.menu.addAction(a)
            self.element_actions.append(a)
            core.actions.append(a)

        # Toolbar button
        self.button = QToolButton()
        #: Toolbar button label, reused as its tooltip and status-bar tip, so the
        #: translation must also work as a compact button caption. GERUND -- the
        #: activity of placing network elements, naming the whole drop-down group;
        #: not an imperative command. "elements" here means the passive optical
        #: devices (ODF, OTB, TO, ...), not map features in general.
        button_label = self.tr('Placing elements')
        # One tr() call, reused: three identical calls would make pylupdate6 emit
        # a duplicate <message> once a translator note is attached to only one.
        self.button.setText(button_label)
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(load_icon('ic_place_elements.svg'))
        self.button.setToolTip(button_label)
        self.button.setStatusTip(button_label)
        core.toolbar.addWidget(self.button)

    def tr(self, message):
        """
        Translate a message using the Qt translation API.

        Args:
            message: String literal to translate

        Returns:
            Translated string for the active locale
        """
        return QCoreApplication.translate('ElementPlacementUI', message)


__all__ = ['ElementPlacementUI']
