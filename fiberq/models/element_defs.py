"""
FiberQ v2 - Element Definitions Module

This module contains definitions for all placeable network elements
including their symbols, default fields, and display properties.
"""

import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


def _get_plugin_dir() -> str:
    """Get the plugin directory path."""
    return os.path.dirname(os.path.dirname(__file__))


def _map_icon_path(filename: str) -> str:
    """Get the full path to a map icon file."""
    try:
        return os.path.join(_get_plugin_dir(), 'resources', 'map_icons', filename)
    except Exception:
        return filename


def _toolbar_icon_path(filename: str) -> str:
    """Get the full path to a toolbar icon file."""
    try:
        return os.path.join(_get_plugin_dir(), 'icons', filename)
    except Exception:
        return filename


# =============================================================================
# SYMBOL SPECIFICATIONS
# =============================================================================

@dataclass
class SymbolSpec:
    """Specification for element map symbol."""
    svg_path: Optional[str] = None
    name: Optional[str] = None  # For simple marker symbols
    color: str = "red"
    size: str = "10"
    size_unit: str = "MapUnit"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for QGIS."""
        if self.svg_path:
            return {
                "svg_path": self.svg_path,
                "size": self.size,
                "size_unit": self.size_unit,
            }
        return {
            "name": self.name,
            "color": self.color,
            "size": self.size,
            "size_unit": self.size_unit,
        }


# =============================================================================
# ELEMENT DEFINITION
# =============================================================================

@dataclass
class ElementDefinition:
    """Definition for a placeable network element."""
    name: str
    symbol: SymbolSpec
    toolbar_icon: Optional[str] = None
    default_capacity: int = 0
    category: str = "general"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for backward compatibility."""
        return {
            "name": self.name,
            "symbol": self.symbol.to_dict(),
        }


# =============================================================================
# ELEMENT DEFINITIONS
# =============================================================================

# Point element definitions with SVG symbols
ELEMENT_DEFS: List[Dict[str, Any]] = [
    {
        "name": "ODF",
        "symbol": {
            "svg_path": _map_icon_path("map_odf.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "TB",
        "symbol": {
            "svg_path": _map_icon_path("map_tb.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "Patch panel",
        "symbol": {
            "svg_path": _map_icon_path("map_patch_panel.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "OTB",
        "symbol": {
            "svg_path": _map_icon_path("map_otb.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "Indoor OTB",
        "symbol": {
            "svg_path": _map_icon_path("map_place_otb_indoor.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "Outdoor OTB",
        "symbol": {
            "svg_path": _map_icon_path("map_place_otb_outdoor.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "Pole OTB",
        "symbol": {
            "svg_path": _map_icon_path("map_place_otb_pole.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "TO",
        "symbol": {
            "svg_path": _map_icon_path("map_place_to.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "Indoor TO",
        "symbol": {
            "svg_path": _map_icon_path("map_place_to_indoor.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "Outdoor TO",
        "symbol": {
            "svg_path": _map_icon_path("map_place_to_outdoor.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "Pole TO",
        "symbol": {
            "svg_path": _map_icon_path("map_place_to_pole.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        "name": "Joint Closure TO",
        "symbol": {
            "svg_path": _map_icon_path("map_place_to_joint_closure.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
]

# Joint closure (nastavak) definition
JOINT_CLOSURE_DEF: Dict[str, Any] = {
    "name": "Joint Closures",
    "symbol": {
        "name": "diamond",
        "color": "red",
        "size": "5",
        "size_unit": "MapUnit"
    }
}

# Legacy alias for backward compatibility
NASTAVAK_DEF = JOINT_CLOSURE_DEF


# =============================================================================
# ELEMENT ICON MAPPING
# =============================================================================

# Map element names to toolbar icon file names
ELEMENT_ICON_MAP: Dict[str, str] = {
    'ODF': 'odf',
    'TB': 'tb',
    'Patch panel': 'patch_panel',
    'OTB': 'otb',
    'Indoor OTB': 'indoor_otb',
    'Outdoor OTB': 'outdoor_otb',
    'Pole OTB': 'pole_otb',
    'TO': 'to',
    'Indoor TO': 'indoor_to',
    'Outdoor TO': 'outdoor_to',
    'Pole TO': 'pole_to',
    'Joint Closure TO': 'joint_closure_to',
}


def get_element_icon_filename(element_name: str) -> str:
    """
    Get the toolbar icon filename for an element.

    Args:
        element_name: Name of the element

    Returns:
        Icon filename (without path)
    """
    slug = ELEMENT_ICON_MAP.get(element_name)
    if slug:
        return f'ic_place_{slug}.svg'
    return 'ic_place_elements.svg'


def get_element_def_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Get element definition by name.

    Args:
        name: Element name to look up

    Returns:
        Element definition dict or None if not found
    """
    for elem_def in ELEMENT_DEFS:
        if elem_def.get("name") == name:
            return elem_def
    return None


# =============================================================================
# DEFAULT ELEMENT FIELDS
# =============================================================================

@dataclass
class FieldDefinition:
    """Definition for an element attribute field."""
    key: str
    label: str
    field_type: str  # 'text', 'int', 'double', 'enum', 'year'
    default: Any = ""
    options: Optional[List[str]] = None


# Default fields for point elements
DEFAULT_ELEMENT_FIELDS: List[FieldDefinition] = [
    FieldDefinition("naziv", "Name", "text", ""),
    FieldDefinition("proizvodjac", "Manufacturer", "text", ""),
    FieldDefinition("oznaka", "Label", "text", ""),
    FieldDefinition("kapacitet", "Capacity", "int", 0),
    FieldDefinition("ukupno_kj", "Total", "int", 0),
    FieldDefinition("zahtev_kapaciteta", "Capacity Requirement", "int", 0),
    FieldDefinition("zahtev_rezerve", "Slack Requirement", "int", 0),
    FieldDefinition("oznaka_izvoda", "Outlet Label", "text", ""),
    FieldDefinition("numeracija", "Numbering", "text", ""),
    FieldDefinition("naziv_objekta", "Object Name", "text", ""),
    FieldDefinition("adresa_ulica", "Address Street", "text", ""),
    FieldDefinition("adresa_broj", "Address Number", "text", ""),
    FieldDefinition("address_id", "Address ID", "text", ""),
    FieldDefinition("stanje", "Status", "enum", "Planned", ["Planned", "Built", "Existing"]),
    FieldDefinition("godina_ugradnje", "Year of Installation", "year", 2025),
]


def get_default_fields_for_layer(layer_name: str) -> List[Tuple[str, str, str, Any, Optional[List[str]]]]:
    """
    Get default field definitions for a layer.

    Args:
        layer_name: Name of the layer

    Returns:
        List of tuples: (key, label, field_type, default, options)
    """
    # Delegates to the canonical schema (single source of truth, WP1a).
    from .schema import get_default_fields_for_layer as _schema_fields
    return _schema_fields(layer_name)


# =============================================================================
# ELEMENT FIELD ALIASES
# =============================================================================

# Standard field aliases for ODF/OTB/TB/Patch panel layers
ELEMENT_FIELD_ALIASES: Dict[str, str] = {
    "naziv": "Name",
    "proizvodjac": "Manufacturer",
    "oznaka": "Label",
    "kapacitet": "Capacity",
    "ukupno_kj": "Total SCs",
    "zahtev_kapaciteta": "Required capacity",
    "zahtev_rezerve": "Reserve capacity",
    "oznaka_izvoda": "Port label",
    "numeracija": "Numbering",
    "naziv_objekta": "Site name",
    "adresa_ulica": "Street",
    "adresa_broj": "Street No.",
    "address_id": "Address ID",
    "stanje": "Status",
    "godina_ugradnje": "Install year",
}


def apply_element_aliases(layer) -> None:
    """
    Apply English field aliases to an element layer.

    Does not change field names, only the display aliases
    visible in the attribute table.

    Args:
        layer: QgsVectorLayer to apply aliases to
    """
    if layer is None:
        return

    try:
        fields = layer.fields()
    except Exception:
        return

    for field_name, alias in ELEMENT_FIELD_ALIASES.items():
        try:
            idx = fields.indexFromName(field_name)
            if idx != -1:
                layer.setFieldAlias(idx, alias)
        except Exception:
            continue


# =============================================================================
# PUBLIC API FUNCTIONS
# =============================================================================

def get_all_element_defs() -> List[Dict[str, Any]]:
    """
    Get all element definitions with their symbols.

    Returns:
        List of element definition dictionaries with name and symbol
    """
    return ELEMENT_DEFS


def get_joint_closure_def() -> Dict[str, Any]:
    """
    Get the joint closure (nastavak) definition.

    Returns:
        Dictionary with name and symbol for joint closures
    """
    return JOINT_CLOSURE_DEF
