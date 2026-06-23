"""
FiberQ v1.2 - Command Manager (Feature 3)

Tracks the last FiberQ tool activation so the user can repeat it
with a double-tap of the Space key.

Design:
    - Every FiberQ tool activation calls record_command()
    - Double-tapping Space within 500ms repeats the last command
    - Commands that normally show a dialog (manhole, slack, pipes)
      skip the dialog on repeat and reuse the previous parameters
    - A status bar widget shows: "Space×2 → Place Pole"
"""

import time

from qgis.PyQt.QtCore import Qt, QObject, QEvent
from qgis.PyQt.QtWidgets import QLabel

from ..utils.logger import get_logger
logger = get_logger(__name__)


# =============================================================================
# Command definitions
# =============================================================================

# Human-readable labels for commands
COMMAND_LABELS = {
    'place_pole': 'Place Pole',
    'place_manhole': 'Place Manhole',
    'place_joint_closure': 'Place Joint Closure',
    'place_element': 'Place Element',
    'create_route': 'Create Route',
    'manual_route': 'Manual Route',
    'lay_cable': 'Lay Cable',
    'place_slack': 'Place Slack',
    'place_pe_duct': 'Place PE Duct',
    'place_transition_duct': 'Place Transition Duct',
    'draw_service_area': 'Draw Service Area',
    'place_object': 'Place Object',
    'fiber_break': 'Place Fiber Break',
    'split_route': 'Split Route',
}


# =============================================================================
# Double-tap Space detector
# =============================================================================

class DoubleTapSpaceFilter(QObject):
    """
    Event filter that detects double-tap of the Space key.

    Listens for KeyPress events on the main window. If two Space key
    presses occur within `interval_ms` milliseconds, fires the callback.

    Single Space presses are ignored (passed through to QGIS for panning).
    """

    def __init__(self, parent, callback, interval_ms=500):
        super().__init__(parent)
        self._callback = callback
        self._interval_ms = interval_ms
        self._last_space_time = 0

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space:
            # Ignore auto-repeat (held key)
            if event.isAutoRepeat():
                return False

            now = time.time() * 1000  # ms
            elapsed = now - self._last_space_time

            if elapsed < self._interval_ms:
                # Double tap detected — consume this event
                self._last_space_time = 0
                try:
                    self._callback()
                except Exception as e:
                    logger.debug(f"Error in double-space callback: {e}")
                return True  # consume the event
            else:
                # First tap — record time, let it pass through to QGIS
                self._last_space_time = now
                return False

        return False  # don't filter other events


# =============================================================================
# Command Manager
# =============================================================================

class CommandManager:
    """
    Tracks and repeats the last FiberQ command.

    Usage from main_plugin.py:
        # When activating a tool:
        self.command_manager.record('place_pole')

        # For tools with parameters:
        self.command_manager.record('lay_cable', tip='podzemni', podtip='glavni')

        # For manhole (with dialog params to reuse on repeat):
        self.command_manager.record('place_manhole')
        # The manhole attrs are already stored in self._manhole_pending_attrs,
        # so repeat just re-activates the tool without dialogs.
    """

    def __init__(self, plugin):
        self.plugin = plugin
        self.iface = plugin.iface

        self._last_command = None
        self._last_params = {}
        self._last_time = 0

        # Status bar label
        self._status_label = None

        # Double-tap space detector
        self._space_filter = DoubleTapSpaceFilter(
            self.iface.mainWindow(),
            self._on_double_space,
            interval_ms=500
        )
        self.iface.mainWindow().installEventFilter(self._space_filter)

        # Create status bar widget
        self._init_status_label()

    def _init_status_label(self):
        """Create a status bar label showing the repeatable command."""
        try:
            self._status_label = QLabel("")
            self._status_label.setStyleSheet(
                "color: #475569; padding: 0 8px; font-size: 11px;"
            )
            self.iface.mainWindow().statusBar().addPermanentWidget(
                self._status_label
            )
            self._update_status_label()
        except Exception as e:
            logger.debug(f"Could not create status label: {e}")

    def _update_status_label(self):
        """Update the status bar text."""
        if not self._status_label:
            return

        if self._last_command:
            label = COMMAND_LABELS.get(self._last_command, self._last_command)
            # Include element name if applicable
            element_name = self._last_params.get('layer_name', '')
            if element_name and self._last_command == 'place_element':
                label = f"Place {element_name}"
            self._status_label.setText(f"  Space×2 → {label}  ")
        else:
            self._status_label.setText("")

    # -----------------------------------------------------------------
    # Recording
    # -----------------------------------------------------------------

    def record(self, command_name, **params):
        """
        Record a command activation for potential repeat.

        Args:
            command_name: Key from COMMAND_LABELS (e.g. 'place_pole')
            **params:     Any parameters needed to re-execute
                          (e.g. tip='podzemni', podtip='glavni')
        """
        self._last_command = command_name
        self._last_params = params
        self._last_time = time.time()
        self._update_status_label()
        logger.debug(f"Command recorded: {command_name} {params}")

    def get_last_command(self):
        """Return (command_name, params) or (None, {})."""
        return self._last_command, self._last_params

    # -----------------------------------------------------------------
    # Repeat execution
    # -----------------------------------------------------------------

    def _on_double_space(self):
        """Called when double-space is detected."""
        if not self._last_command:
            self.iface.messageBar().pushInfo(
                "FiberQ", "No command to repeat."
            )
            return

        label = COMMAND_LABELS.get(self._last_command, self._last_command)
        element_name = self._last_params.get('layer_name', '')
        if element_name and self._last_command == 'place_element':
            label = f"Place {element_name}"  # noqa: F841

        logger.debug(f"Repeating command: {self._last_command}")
        self._execute(self._last_command, self._last_params)

    def _execute(self, command, params):
        """Execute a command by name."""
        p = self.plugin

        try:
            if command == 'place_pole':
                p.activate_point_tool()

            elif command == 'place_manhole':
                # Skip dialogs — reuse stored attrs and reactivate tool
                self._repeat_manhole()

            elif command == 'place_joint_closure':
                p.activate_extension_tool()

            elif command == 'place_element':
                layer_name = params.get('layer_name', '')
                symbol_spec = params.get('symbol_spec')
                if layer_name:
                    p.activate_place_element_tool(layer_name, symbol_spec)

            elif command == 'create_route':
                p.create_route()

            elif command == 'manual_route':
                p.activate_manual_route_tool()

            elif command == 'lay_cable':
                tip = params.get('tip', '')
                podtip = params.get('podtip', '')
                if tip and podtip:
                    p.lay_cable_type(tip, podtip)
                else:
                    p.lay_cable()

            elif command == 'place_slack':
                default_tip = params.get('default_tip', 'Terminal')
                p._start_slack_interactive(default_tip)

            elif command == 'place_pe_duct':
                p.open_pe_cev_workflow()

            elif command == 'place_transition_duct':
                p.open_transition_duct_workflow()

            elif command == 'draw_service_area':
                p.activate_draw_service_area_manual()

            elif command == 'fiber_break':
                p.activate_fiber_break_tool()

            elif command == 'split_route':
                p.activate_breakpoint_tool()

            elif command == 'place_object':
                # Object tools are complex (3pt, Npt, ortho) —
                # just re-trigger the same sub-type
                obj_method = params.get('method')
                if obj_method and hasattr(p, obj_method):
                    getattr(p, obj_method)()

            else:
                logger.debug(f"Unknown command for repeat: {command}")
                return

        except Exception as e:
            logger.debug(f"Error repeating command '{command}': {e}")
            self.iface.messageBar().pushWarning(
                "FiberQ", f"Could not repeat command: {e}"
            )

    def _repeat_manhole(self):
        """
        Repeat manhole placement without dialogs.

        Reuses the attributes stored in plugin._manhole_pending_attrs
        and re-creates the ManholePlaceTool with the same auto-increment
        settings (continuing from where the counter left off).
        """
        p = self.plugin

        attrs = getattr(p, '_manhole_pending_attrs', None)
        if not attrs:
            # No previous attrs — fall back to full workflow
            p.open_manhole_workflow()
            return

        from ..tools.manhole_tool import ManholePlaceTool

        p._manhole_place_tool = ManholePlaceTool(p.iface, p)

        # Restore auto-increment if it was enabled
        # The counter continues from where the previous session left off
        auto_inc = self._last_params.get('auto_increment', False)
        if auto_inc:
            last_counter = self._last_params.get('last_counter', 1)
            prefix = self._last_params.get('id_prefix', '')
            pad_width = self._last_params.get('id_pad_width', 0)

            p._manhole_place_tool._auto_increment = True
            p._manhole_place_tool._id_prefix = prefix
            p._manhole_place_tool._id_counter = last_counter
            p._manhole_place_tool._id_pad_width = pad_width

            # Advance past any new IDs that may have been added
            p._manhole_place_tool._advance_past_existing_ids()

            first_id = p._manhole_place_tool._get_current_id()
            p.iface.mapCanvas().setMapTool(p._manhole_place_tool)
            p.iface.messageBar().pushInfo(
                "Placing manholes",
                f"Repeating — auto-incrementing from {first_id} (ESC to exit)."
            )
        else:
            p.iface.mapCanvas().setMapTool(p._manhole_place_tool)
            p.iface.messageBar().pushInfo(
                "Placing manhole",
                "Repeating — click to place (ESC to exit)."
            )

    # -----------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------

    def unload(self):
        """Remove the event filter and status bar widget."""
        try:
            self.iface.mainWindow().removeEventFilter(self._space_filter)
        except Exception as e:
            logger.debug(f"Error removing space filter: {e}")

        try:
            if self._status_label:
                self.iface.mainWindow().statusBar().removeWidget(
                    self._status_label
                )
                self._status_label.deleteLater()
                self._status_label = None
        except Exception as e:
            logger.debug(f"Error removing status label: {e}")


__all__ = ['CommandManager']
