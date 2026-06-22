# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""
DEPRECATED: This module exists only for backward compatibility.

All classes have been moved to dedicated packages:
- Dialog classes → fiberq.dialogs package
- Map tool classes → fiberq.tools package
- Utility classes → fiberq.utils package

Please update your imports to use the new module locations:

    # Old (deprecated):
    from fiberq.extracted_classes import PointTool, CablePickerDialog

    # New (preferred):
    from fiberq.tools import PointTool
    from fiberq.dialogs import CablePickerDialog

This module will be removed in a future version.
"""

import warnings

# Emit deprecation warning on import
warnings.warn(
    "The 'extracted_classes' module is deprecated. "
    "Import from 'fiberq.tools' or 'fiberq.dialogs' instead.",
    DeprecationWarning,
    stacklevel=2
)

# ===========================================================================
# Map Tools - Re-exported from fiberq.tools package
# ===========================================================================

# Phase 2.1 tools (originally in extracted_classes.py)
from .tools.drawing_tool import OpenDrawingMapTool
from .tools.point_tool import PointTool
from .tools.element_tool import PlaceElementTool, ChangeElementTypeTool
from .tools.extension_tool import ExtensionTool
from .tools.select_tool import SmartMultiSelectTool
from .tools.region_tool import DrawRegionPolygonTool
from .tools.object_tools import (
    ObjectPropertiesDialog,
    _BaseObjMapTool,
    DrawObjectNTool,
    DrawObjectOrthoTool,
    DrawObject3ptTool,
)
from .tools.branch_tool import BranchInfoTool
from .tools.image_tool import OpenImageMapTool, _ImagePopup
from .tools.move_tool import MoveFeatureTool

# Phase 3 tools (added later)
from .tools.breakpoint_tool import BreakpointTool
from .tools.route_tool import ManualRouteTool
from .tools.slack_tool import SlackPlaceTool
from .tools.manhole_tool import ManholePlaceTool
from .tools.pipe_tool import PipePlaceTool

# ===========================================================================
# Dialogs - Re-exported from fiberq.dialogs package
# ===========================================================================

# Phase 2.2 dialogs (originally in extracted_classes.py)
from .dialogs.bom_dialog import _BOMDialog
from .dialogs.correction_dialog import CorrectionDialog
from .dialogs.locator_dialog import LocatorDialog
from .dialogs.schematic_dialog import SchematicView, OpticalSchematicDialog
from .dialogs.relations_dialog import NewRelationDialog, RelationsDialog
from .dialogs.latent_dialog import LatentElementsDialog, CablePitstopsDialog
from .dialogs.color_dialog import ColorCatalogManagerDialog, NewColorCatalogDialog
from .dialogs.region_dialog import CreateRegionDialog
from .dialogs.settings_dialog import FiberQSettingsDialog

# Phase 3 dialogs (added later)
from .dialogs.element_dialog import PrePlaceAttributesDialog
from .dialogs.cable_dialog import CablePickerDialog
from .dialogs.manhole_dialog import ManholeTypeDialog, ManholeDetailsDialog
from .dialogs.pipe_dialog import PEDuctDialog, TransitionDuctDialog
from .dialogs.slack_dialog import SlackDialog

# ===========================================================================
# Utilities - Re-exported from fiberq.utils package
# ===========================================================================
from .utils.image_watcher import CanvasImageClickWatcher


# ===========================================================================
# All exported names for backward compatibility
# ===========================================================================
__all__ = [
    # Map Tools (Phase 2.1)
    'OpenDrawingMapTool',
    'PointTool',
    'PlaceElementTool',
    'ChangeElementTypeTool',
    'ExtensionTool',
    'SmartMultiSelectTool',
    'DrawRegionPolygonTool',
    'ObjectPropertiesDialog',
    '_BaseObjMapTool',
    'DrawObjectNTool',
    'DrawObjectOrthoTool',
    'DrawObject3ptTool',
    'BranchInfoTool',
    'OpenImageMapTool',
    '_ImagePopup',
    'MoveFeatureTool',

    # Map Tools (Phase 3)
    'BreakpointTool',
    'ManualRouteTool',
    'SlackPlaceTool',
    'ManholePlaceTool',
    'PipePlaceTool',

    # Dialogs (Phase 2.2)
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

    # Dialogs (Phase 3)
    'PrePlaceAttributesDialog',
    'CablePickerDialog',
    'ManholeTypeDialog',
    'ManholeDetailsDialog',
    'PEDuctDialog',
    'TransitionDuctDialog',
    'SlackDialog',

    # Utilities
    'CanvasImageClickWatcher',
]
