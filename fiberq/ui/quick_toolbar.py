"""
FiberQ v1.2 - Quick Toolbar (Feature 4)

A compact, second toolbar with the 10 most-used design tools.
Provides optional single-key shortcuts (P, M, R, A, U, O, T, S)
that can be enabled/disabled in FiberQ Settings.

Registered with iface.addToolBar() so it appears in
View → Toolbars → FiberQ Quick.
"""

from qgis.PyQt.QtCore import Qt, QCoreApplication, QT_TRANSLATE_NOOP
from qgis.PyQt.QtGui import QKeySequence
pass
from qgis.PyQt.QtGui import QAction, QShortcut  # noqa: E402

from qgis.core import QgsSettings  # noqa: E402

from .base import load_icon  # noqa: E402
from ..i18n import safe_format  # noqa: E402
from ..utils.logger import get_logger  # noqa: E402
logger = get_logger(__name__)


# ────────────────────────────────────────────────────────────────────
# Quick-toolbar button definitions
# ────────────────────────────────────────────────────────────────────

# Each entry: (key, label, icon, shortcut_key_or_None, method_name, method_args)
# method_name is called on the plugin core; method_args is a dict of kwargs.
#
# i18n: labels are marked here with QT_TRANSLATE_NOOP (context 'FiberQ') so
# pylupdate6 extracts them, but they stay untranslated in the table -- this
# module is imported at initGui time and the dict is built once at import.
# The actual lookup happens in _build_actions() via QCoreApplication.translate,
# so resolution never depends on whether the QTranslator was installed before
# this module was imported.
QUICK_TOOLS = [
    {
        'id': 'pole',
        #: Quick-toolbar button label, imperative. Places one pole (the support that
        #: carries aerial cable). NOTE: this is the SAME command as the main
        #: toolbar's "Add pole" (Routing menu) - only the English wording differs.
        #: Please use one consistent term for the pole in both.
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Place Pole'),
        'icon': 'ic_add_pole.svg',
        'shortcut': 'P',
        'method': 'activate_point_tool',
        'args': {},
    },
    {
        'id': 'manhole',
        #: Quick-toolbar button label, imperative, singular. Same command as the
        #: Ducting menu's "Placing manholes" - only the wording differs. "manhole" =
        #: the underground inspection chamber on a duct run (fr: chambre de tirage).
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Place Manhole'),
        'icon': 'ic_place_manholes.svg',
        'shortcut': 'M',
        'method': 'open_manhole_workflow',
        'args': {},
    },
    {
        'id': 'route',
        #: Quick-toolbar button label, imperative. "Route" = the physical path on the
        #: ground that cables follow (fr: tracé). Same command as the Routing menu's
        #: "Create route" - only the capitalisation differs, so keep one wording.
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Create Route'),
        'icon': 'ic_create_route.svg',
        'shortcut': 'R',
        'method': 'create_route',
        'args': {},
    },
    {
        'id': 'aerial_cable',
        #: Quick-toolbar button label. Noun phrase, "Aerial" = strung overhead on
        #: poles (as opposed to buried). Shortcut for laying specifically a BACKBONE
        #: /feeder aerial cable - the subtype is fixed to "main" in code even though
        #: the label does not say so. The Cable menu offers the full choice.
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Aerial Cable'),
        'icon': 'ic_cable_aerial.svg',
        'shortcut': 'A',
        'method': 'lay_cable_type',
        'args': {'tip': 'vazdusni', 'podtip': 'glavni'},
    },
    {
        'id': 'underground_cable',
        #: Quick-toolbar button label. Noun phrase, "Underground" = laid in ducts or
        #: a trench below ground; pairs with "Aerial Cable" above. Also fixed to the
        #: BACKBONE/feeder subtype in code, though the label does not say so.
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Underground Cable'),
        'icon': 'ic_cable_underground.svg',
        'shortcut': 'U',
        'method': 'lay_cable_type',
        'args': {'tip': 'podzemni', 'podtip': 'glavni'},
    },
    {
        'id': 'odf',
        #: Quick-toolbar button label, imperative. ODF = Optical Distribution Frame,
        #: the passive frame at the head end where feeder fibres terminate. Translate
        #: only "Place"; keep the acronym "ODF" - it doubles as the layer name.
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Place ODF'),
        'icon': 'ic_place_odf.svg',
        'shortcut': 'O',
        'method': 'activate_place_element_tool',
        'args': {'layer_name': 'ODF'},
        'element_def': True,
    },
    {
        'id': 'otb',
        #: Quick-toolbar button label, imperative. OTB = "Optical Termination Box".
        #: Translate only "Place" and keep the acronym "OTB" unless your language
        #: has an established equivalent acronym.
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Place OTB'),
        'icon': 'ic_place_otb.svg',
        'shortcut': 'T',
        'method': 'activate_place_element_tool',
        'args': {'layer_name': 'OTB'},
        'element_def': True,
    },
    {
        'id': 'to',
        #: Quick-toolbar button label, imperative. WARNING: "TO" is an ACRONYM =
        #: "Termination Outlet" (the subscriber-side optical outlet), NOT the English
        #: preposition "to" - do not read this as "place ... to ...". Translate only
        #: "Place" and keep the acronym "TO" unless your language has an equivalent.
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Place TO'),
        'icon': 'ic_place_to.svg',
        'shortcut': None,  # no single-key shortcut
        'method': 'activate_place_element_tool',
        'args': {'layer_name': 'TO'},
        'element_def': True,
    },
    {
        'id': 'slack',
        #: Quick-toolbar button label, noun phrase (singular). "Slack" = the spare
        #: length of cable coiled at a point for later re-splicing. This button
        #: places a TERMINAL slack by default. The Slack menu labels the same group
        #: "Optical slacks" (plural) - keep the two consistent.
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Optical Slack'),
        'icon': 'ic_slack_midspan.svg',
        'shortcut': 'S',
        'method': '_start_slack_interactive',
        'args': {'default_tip': 'Terminal'},
    },
    # Separator before undo
    None,
    {
        'id': 'undo',
        #: Quick-toolbar button label, imperative verb. Undoes the last FiberQ action.
        #: The "(FiberQ)" qualifier distinguishes it from QGIS's own Undo, which is a
        #: separate history - keep the product name as-is and keep the brackets.
        'label': QT_TRANSLATE_NOOP('FiberQ', 'Undo (FiberQ)'),
        'icon': 'ic_undo.svg',
        'shortcut': None,  # already has Ctrl+Shift+Z via main toolbar
        'method': '_on_undo',
        'args': {},
    },
]


# ────────────────────────────────────────────────────────────────────
# Settings keys
# ────────────────────────────────────────────────────────────────────

SETTING_SHOW_TOOLBAR = 'FiberQ/quick_toolbar_visible'
SETTING_ENABLE_SHORTCUTS = 'FiberQ/quick_toolbar_shortcuts'


def _read_bool_setting(key, default=True):
    """Read a boolean from QgsSettings (handles string 'true'/'false')."""
    val = QgsSettings().value(key, 'true' if default else 'false')
    if isinstance(val, bool):
        return val
    return str(val).lower() in ('true', '1', 'yes')


# ────────────────────────────────────────────────────────────────────
# Quick Toolbar class
# ────────────────────────────────────────────────────────────────────

class QuickToolbar:
    """
    Creates and manages the FiberQ Quick toolbar.

    Usage in main_plugin.initGui():
        self.quick_toolbar = QuickToolbar(self)

    Cleanup in main_plugin.unload():
        self.quick_toolbar.unload()
    """

    def __init__(self, core):
        """
        Build the Quick Toolbar.

        Args:
            core: FiberQ plugin instance (self in main_plugin.py)
        """
        self.core = core
        self.iface = core.iface
        self._actions = []
        self._shortcuts = []

        # Create the toolbar
        self.toolbar = self.iface.addToolBar('FiberQ Quick')
        self.toolbar.setObjectName('FiberQQuickToolbar')

        # Build actions
        self._build_actions()

        # Apply visibility from settings
        visible = _read_bool_setting(SETTING_SHOW_TOOLBAR, default=True)
        self.toolbar.setVisible(visible)

        # Apply shortcuts from settings
        shortcuts_on = _read_bool_setting(SETTING_ENABLE_SHORTCUTS, default=False)
        if shortcuts_on:
            self._enable_shortcuts()

    def tr(self, message):
        """Translate a UI string in the 'QuickToolbar' context."""
        return QCoreApplication.translate('QuickToolbar', message)

    # ────────────────────────────────────────────────────
    # Build
    # ────────────────────────────────────────────────────

    def _build_actions(self):
        """Create toolbar actions for each quick-tool definition."""
        # Pre-load element definitions for symbol specs
        element_symbols = {}
        try:
            from .base import get_element_defs
            for edef in get_element_defs():
                element_symbols[edef['name']] = edef.get('symbol')
        except Exception as e:
            logger.debug(f"Could not load element defs for quick toolbar: {e}")

        for tool_def in QUICK_TOOLS:
            if tool_def is None:
                self.toolbar.addSeparator()
                continue

            icon = load_icon(tool_def['icon'])
            # Marked at the definition site with QT_TRANSLATE_NOOP('FiberQ', ...)
            label = QCoreApplication.translate('FiberQ', tool_def['label'])
            shortcut_key = tool_def.get('shortcut')

            # Build tooltip with shortcut hint
            if shortcut_key:
                #: Tooltip pattern for every quick-toolbar button, e.g. "Place Pole
                #: (P)". {label} is the already-translated button label and {shortcut}
                #: is a keyboard key such as P or Ctrl+Shift+Z. Keep both placeholders
                #: spelled exactly as they are; only the punctuation may be adapted.
                tooltip = safe_format(self.tr("{label} ({shortcut})"),
                                      "{label} ({shortcut})",
                                      label=label, shortcut=shortcut_key)
            elif tool_def['id'] == 'undo':
                #: Tooltip pattern for every quick-toolbar button, e.g. "Place Pole
                #: (P)". {label} is the already-translated button label and {shortcut}
                #: is a keyboard key such as P or Ctrl+Shift+Z. Keep both placeholders
                #: spelled exactly as they are; only the punctuation may be adapted.
                tooltip = safe_format(self.tr("{label} ({shortcut})"),
                                      "{label} ({shortcut})",
                                      label=label, shortcut='Ctrl+Shift+Z')
            else:
                tooltip = label

            action = QAction(icon, label, self.iface.mainWindow())
            action.setToolTip(tooltip)
            action.setCheckable(False)

            # Resolve element symbol specs if needed
            args = dict(tool_def['args'])
            if tool_def.get('element_def'):
                layer_name = args.get('layer_name', '')
                sym = element_symbols.get(layer_name)
                if sym:
                    args['symbol_spec'] = sym

            # Connect to the plugin method
            method_name = tool_def['method']
            action.triggered.connect(
                self._make_callback(method_name, args)
            )

            self.toolbar.addAction(action)
            self._actions.append((tool_def['id'], action))

    def _make_callback(self, method_name, args):
        """
        Create a callback lambda for a toolbar action.

        Uses a closure to capture method_name and args by value.
        """
        def callback(checked=False):
            try:
                method = getattr(self.core, method_name, None)
                if method:
                    if args:
                        method(**args)
                    else:
                        method()
                else:
                    logger.debug(f"Quick toolbar: method '{method_name}' not found on plugin")
            except Exception as e:
                logger.debug(f"Quick toolbar error calling {method_name}: {e}")
        return callback

    # ────────────────────────────────────────────────────
    # Keyboard shortcuts
    # ────────────────────────────────────────────────────

    def _enable_shortcuts(self):
        """Create single-key QShortcuts for tools that have them."""
        self._disable_shortcuts()  # clear any existing

        # Disable the existing 'R' shortcut for slack that's already in main_plugin
        self._disable_conflicting_shortcuts()

        for tool_def in QUICK_TOOLS:
            if tool_def is None:
                continue
            shortcut_key = tool_def.get('shortcut')
            if not shortcut_key:
                continue

            try:
                sc = QShortcut(
                    QKeySequence(shortcut_key),
                    self.iface.mainWindow()
                )
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                method_name = tool_def['method']
                args = tool_def['args']
                sc.activated.connect(self._make_callback(method_name, args))
                self._shortcuts.append(sc)
            except Exception as e:
                logger.debug(f"Could not create shortcut '{shortcut_key}': {e}")

    def _disable_shortcuts(self):
        """Remove all quick-toolbar shortcuts."""
        for sc in self._shortcuts:
            try:
                sc.activated.disconnect()
                sc.setParent(None)
                sc.deleteLater()
            except Exception as e:
                logger.debug(f"Error removing shortcut: {e}")
        self._shortcuts.clear()

    def _disable_conflicting_shortcuts(self):
        """
        Disable the existing 'R' shortcut in main_plugin for slack,
        which would conflict with our 'R' for Create Route.
        """
        try:
            slack_action = getattr(self.core, 'action_slack_quick', None)
            if slack_action:
                slack_action.setShortcut(QKeySequence())  # clear its shortcut
        except Exception as e:
            logger.debug(f"Error disabling conflicting shortcut: {e}")

    def set_shortcuts_enabled(self, enabled):
        """Enable or disable single-key shortcuts at runtime."""
        if enabled:
            self._enable_shortcuts()
        else:
            self._disable_shortcuts()
            # Restore the original 'R' shortcut for slack
            try:
                slack_action = getattr(self.core, 'action_slack_quick', None)
                if slack_action:
                    slack_action.setShortcut(QKeySequence('R'))
            except Exception as e:
                logger.debug(f"Could not restore slack 'R' shortcut: {e}")

        QgsSettings().setValue(SETTING_ENABLE_SHORTCUTS,
                               'true' if enabled else 'false')

    def set_visible(self, visible):
        """Show or hide the toolbar and persist the setting."""
        self.toolbar.setVisible(visible)
        QgsSettings().setValue(SETTING_SHOW_TOOLBAR,
                               'true' if visible else 'false')

    # ────────────────────────────────────────────────────
    # Cleanup
    # ────────────────────────────────────────────────────

    def unload(self):
        """Remove toolbar and shortcuts."""
        self._disable_shortcuts()

        try:
            for _, action in self._actions:
                try:
                    self.iface.removeToolBarIcon(action)
                except Exception as e:
                    logger.debug(f"Error removing quick toolbar icon: {e}")
            self._actions.clear()
        except Exception as e:
            logger.debug(f"Error removing quick toolbar actions: {e}")

        try:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
        except Exception as e:
            logger.debug(f"Error removing quick toolbar: {e}")


__all__ = ['QuickToolbar']
