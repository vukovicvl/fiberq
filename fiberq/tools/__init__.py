"""
FiberQ v2 - Tools Package

This package contains map tool classes for the FiberQ plugin.

Modules:
- base.py: Base classes and common imports for all tools
- breakpoint_tool.py: Tool for splitting routes (Phase 3)
- route_tool.py: Tool for manual route drawing (Phase 3)
- slack_tool.py: Tool for placing optical slack (Phase 3)
- manhole_tool.py: Tool for placing manholes (Phase 3)
- pipe_tool.py: Tool for drawing pipes (Phase 3)
- drawing_tool.py: Tool for opening attached drawings (Phase 2.1)
- point_tool.py: Tool for placing poles (Phase 2.1)
- element_tool.py: Tools for placing/changing elements (Phase 2.1)
- extension_tool.py: Tool for placing joint closures (Phase 2.1)
- select_tool.py: Smart multi-select tool (Phase 2.1)
- region_tool.py: Tool for drawing service area polygons (Phase 2.1)
- object_tools.py: Tools for drawing building polygons (Phase 2.1)
- branch_tool.py: Tool for displaying cable info (Phase 2.1)
- image_tool.py: Tool for opening attached images (Phase 2.1)
- move_tool.py: Tool for moving features (Phase 2.1)
"""

# Import tool classes for easy access
from .breakpoint_tool import BreakpointTool
from .route_tool import ManualRouteTool
from .slack_tool import SlackPlaceTool
from .manhole_tool import ManholePlaceTool
from .pipe_tool import PipePlaceTool

# Phase 2.1 tools - extracted from extracted_classes.py
from .drawing_tool import OpenDrawingMapTool
from .point_tool import PointTool
from .element_tool import PlaceElementTool, ChangeElementTypeTool
from .extension_tool import ExtensionTool
from .select_tool import SmartMultiSelectTool
from .region_tool import DrawRegionPolygonTool
from .object_tools import (
    ObjectPropertiesDialog,
    _BaseObjMapTool,
    DrawObjectNTool,
    DrawObjectOrthoTool,
    DrawObject3ptTool,
)
from .branch_tool import BranchInfoTool
from .image_tool import OpenImageMapTool, _ImagePopup
from .move_tool import MoveFeatureTool

# Base classes and utilities
from .base import (
    FiberQMapTool,
    FiberQMapToolEmitPoint,
    find_route_layer,
    find_cable_layers,
    find_node_layers,
    find_element_layers,
    get_snap_layers,
    snap_to_point_layers,
    snap_to_line_layer,
    snap_to_line_vertices,
)

__all__ = [
    # Phase 3 Tool classes
    'BreakpointTool',
    'ManualRouteTool',
    'SlackPlaceTool',
    'ManholePlaceTool',
    'PipePlaceTool',

    # Phase 2.1 Tool classes
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

    # Base classes
    'FiberQMapTool',
    'FiberQMapToolEmitPoint',

    # Utility functions
    'find_route_layer',
    'find_cable_layers',
    'find_node_layers',
    'find_element_layers',
    'get_snap_layers',
    'snap_to_point_layers',
    'snap_to_line_layer',
    'snap_to_line_vertices',
]
