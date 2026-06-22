"""
FiberQ v2 - Dialogs Package

This package contains dialog classes for the FiberQ plugin.

Modules:
- base.py: Common imports and utilities for all dialogs
- element_dialog.py: PrePlaceAttributesDialog
- cable_dialog.py: CablePickerDialog
- manhole_dialog.py: ManholeTypeDialog, ManholeDetailsDialog
- pipe_dialog.py: PEDuctDialog, TransitionDuctDialog
- slack_dialog.py: SlackDialog
- bom_dialog.py: _BOMDialog (Bill of Materials)
- correction_dialog.py: CorrectionDialog (Route correction)
- locator_dialog.py: LocatorDialog (Address geocoding)
- schematic_dialog.py: SchematicView, OpticalSchematicDialog
- relations_dialog.py: NewRelationDialog, RelationsDialog
- latent_dialog.py: LatentElementsDialog, CablePitstopsDialog
- color_dialog.py: ColorCatalogManagerDialog, NewColorCatalogDialog
- region_dialog.py: CreateRegionDialog
- settings_dialog.py: FiberQSettingsDialog
"""

# Import dialog classes for easy access
from .element_dialog import PrePlaceAttributesDialog
from .cable_dialog import CablePickerDialog
from .manhole_dialog import ManholeTypeDialog, ManholeDetailsDialog
from .pipe_dialog import PEDuctDialog, TransitionDuctDialog
from .slack_dialog import SlackDialog

# Phase 2.2: New dialog imports
from .bom_dialog import _BOMDialog
from .correction_dialog import CorrectionDialog
from .locator_dialog import LocatorDialog
from .schematic_dialog import SchematicView, OpticalSchematicDialog
from .relations_dialog import NewRelationDialog, RelationsDialog
from .latent_dialog import LatentElementsDialog, CablePitstopsDialog
from .color_dialog import ColorCatalogManagerDialog, NewColorCatalogDialog
from .region_dialog import CreateRegionDialog
from .settings_dialog import FiberQSettingsDialog

# Base utilities
from .base import (
    normalize_name,
    default_fields_for,
    get_current_year,
)

__all__ = [
    # Phase 1 Dialog classes
    'PrePlaceAttributesDialog',
    'CablePickerDialog',
    'ManholeTypeDialog',
    'ManholeDetailsDialog',
    'PEDuctDialog',
    'TransitionDuctDialog',
    'SlackDialog',

    # Phase 2.2: New dialogs
    '_BOMDialog',
    'CorrectionDialog',
    'LocatorDialog',
    'SchematicView',
    'OpticalSchematicDialog',
    'NewRelationDialog',
    'RelationsDialog',
    'LatentElementsDialog',
    'CablePitstopsDialog',
    'ColorCatalogManagerDialog',
    'NewColorCatalogDialog',
    'CreateRegionDialog',
    'FiberQSettingsDialog',

    # Utilities
    'normalize_name',
    'default_fields_for',
    'get_current_year',
]
