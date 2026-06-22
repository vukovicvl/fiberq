"""
FiberQ v2 - UI Package

This package contains UI group classes for the FiberQ toolbar.

Modules:
- base.py: Common imports and utilities for all UI classes
- routing_ui.py: RoutingUI - Route creation toolbar (Phase 5)
- drawings_ui.py: DrawingsUI - Drawing attachment toolbar (Phase 5)
- cable_ui.py: CableLayingUI - Cable laying toolbar (Phase 5)
- elements_ui.py: ElementPlacementUI - Element placement toolbar (Phase 5)
- ducting_ui.py: DuctingUI - Ducting/manhole toolbar (Phase 5)
- selection_ui.py: SelectionUI - Selection tools toolbar (Phase 5)
- slack_ui.py: SlackUI - Optical slack toolbar (Phase 5)
- objects_ui.py: ObjectsUI - Building objects toolbar (Phase 5)
"""

# Import UI classes for easy access
from .routing_ui import RoutingUI
from .drawings_ui import DrawingsUI
from .cable_ui import CableLayingUI
from .elements_ui import ElementPlacementUI
from .ducting_ui import DuctingUI
from .selection_ui import SelectionUI
from .slack_ui import SlackUI
from .objects_ui import ObjectsUI

# Base utilities
from .base import (
    load_icon,
    element_icon_for,
    get_element_defs,
)

__all__ = [
    # UI classes
    'RoutingUI',
    'DrawingsUI',
    'CableLayingUI',
    'ElementPlacementUI',
    'DuctingUI',
    'SelectionUI',
    'SlackUI',
    'ObjectsUI',

    # Utilities
    'load_icon',
    'element_icon_for',
    'get_element_defs',
]
