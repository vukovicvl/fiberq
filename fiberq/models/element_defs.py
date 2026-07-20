"""
FiberQ v2 - Element Definitions Module

This module contains definitions for all placeable network elements
including their symbols, default fields, and display properties.
"""

import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

try:
    from qgis.PyQt.QtCore import QT_TRANSLATE_NOOP
except ImportError:  # pragma: no cover - keeps models/ importable without Qt
    # QT_TRANSLATE_NOOP is an identity function on its text argument, so this
    # fallback is behaviourally exact. pylupdate6 reads the source statically
    # and extracts the literals either way.
    def QT_TRANSLATE_NOOP(context, text):
        return text

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
#
# i18n: every "name" below is BOTH a user-visible label and a runtime
# IDENTIFIER -- it keys ELEMENT_ICON_MAP, the icon lookup in ui/base.py and
# utils/helpers.py, the layer-name match in core/data_manager.py
# (PLACING_ELEMENT_LAYERS), utils/layer_names.py, utils/uuid_utils.py, the
# roster in models/schema.py and the .qml style filenames in fiberq/styles/.
# QT_TRANSLATE_NOOP marks the literal for pylupdate6 and returns it UNCHANGED,
# so these values stay byte-identical in every locale. Translation happens at
# DISPLAY time only, in ui/elements_ui.py, via context 'ElementNames'.
# Never translate these values in place, and never wrap a dict KEY.
#
# The "#:" comments are translator notes: pylupdate6 extracts them into
# <extracomment> and Qt Linguist shows them beside the source string.
ELEMENT_DEFS: List[Dict[str, Any]] = [
    {
        #: Element type (acronym), shown in the "Placing elements" menu.
        #: Optical Distribution Frame: the passive frame at the head end where
        #: feeder fibres terminate. Most languages keep the acronym "ODF".
        "name": QT_TRANSLATE_NOOP('ElementNames', "ODF"),
        "symbol": {
            "svg_path": _map_icon_path("map_odf.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type (acronym) = "Terminal Box". The Serbian backend name is
        #: "ZOK" (Zavrsna opticka kutija). Keep the acronym "TB" unless your
        #: language has an established equivalent acronym.
        "name": QT_TRANSLATE_NOOP('ElementNames', "TB"),
        "symbol": {
            "svg_path": _map_icon_path("map_tb.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type (noun phrase, not an acronym): the rack panel holding
        #: patch connections. Its scope overlaps ODF above -- CONTRIBUTING.md
        #: leaves fr "tiroir optique" vs "panneau de brassage" open; keep the
        #: two element types clearly distinct in your language.
        "name": QT_TRANSLATE_NOOP('ElementNames', "Patch panel"),
        "symbol": {
            "svg_path": _map_icon_path("map_patch_panel.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type (acronym) = "Optical Termination Box". (The Serbian
        #: backend name "OD ormar" is legacy wording and does not redefine the
        #: term.) Keep the acronym "OTB" unless your language has an established
        #: equivalent acronym.
        "name": QT_TRANSLATE_NOOP('ElementNames', "OTB"),
        "symbol": {
            "svg_path": _map_icon_path("map_otb.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type. "Indoor" is an ADJECTIVE qualifying OTB: an OTB mounted
        #: inside a building. Serbian catalogue: "Unutrašnji OD ormar".
        "name": QT_TRANSLATE_NOOP('ElementNames', "Indoor OTB"),
        "symbol": {
            "svg_path": _map_icon_path("map_place_otb_indoor.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type. "Outdoor" is an ADJECTIVE qualifying OTB: an OTB
        #: mounted outside, typically on a wall or facade. Serbian catalogue:
        #: "Spoljašnji OD ormar".
        "name": QT_TRANSLATE_NOOP('ElementNames', "Outdoor OTB"),
        "symbol": {
            "svg_path": _map_icon_path("map_place_otb_outdoor.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type. "Pole" is an ADJECTIVE here: an OTB mounted ON a pole.
        #: It is one element, not a pole plus an OTB. Serbian catalogue:
        #: "OD ormar na stubu".
        "name": QT_TRANSLATE_NOOP('ElementNames', "Pole OTB"),
        "symbol": {
            "svg_path": _map_icon_path("map_place_otb_pole.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type (acronym) = "Termination Outlet": the subscriber-side
        #: optical outlet, the last element before the customer's equipment.
        #: WARNING: this is NOT the English preposition "to" -- the from/to
        #: direction words are a separate string. Keep the acronym "TO" unless
        #: your language has an established equivalent acronym.
        "name": QT_TRANSLATE_NOOP('ElementNames', "TO"),
        "symbol": {
            "svg_path": _map_icon_path("map_place_to.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type. "Indoor" is an ADJECTIVE qualifying TO: a TO mounted
        #: inside a building. Serbian catalogue: "Unutrašnji TO Izvod".
        "name": QT_TRANSLATE_NOOP('ElementNames', "Indoor TO"),
        "symbol": {
            "svg_path": _map_icon_path("map_place_to_indoor.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type. "Outdoor" is an ADJECTIVE qualifying TO: a TO mounted
        #: outside. Serbian catalogue: "Spoljašnji TO Izvod".
        "name": QT_TRANSLATE_NOOP('ElementNames', "Outdoor TO"),
        "symbol": {
            "svg_path": _map_icon_path("map_place_to_outdoor.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type. "Pole" is an ADJECTIVE: a TO mounted ON a pole.
        #: Serbian catalogue: "TO Izvod na stubu".
        "name": QT_TRANSLATE_NOOP('ElementNames', "Pole TO"),
        "symbol": {
            "svg_path": _map_icon_path("map_place_to_pole.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
    {
        #: Element type: a TO housed INSIDE a joint (splice) closure. Serbian
        #: catalogue: "TO Izvod u nastavku" = "TO outlet in the joint closure".
        #: "Joint Closure" qualifies "TO" -- one element, not two.
        "name": QT_TRANSLATE_NOOP('ElementNames', "Joint Closure TO"),
        "symbol": {
            "svg_path": _map_icon_path("map_place_to_joint_closure.svg"),
            "size": "10",
            "size_unit": "MapUnit"
        }
    },
]

# Joint closure (nastavak) definition
#
# i18n: "Joint Closures" is deliberately NOT marked for translation. Unlike the
# ELEMENT_DEFS names it is only ever used as a LAYER NAME -- it is written onto
# the layer by utils/field_aliases.set_layer_display_name() and matched back by
# core/data_manager.PLACING_ELEMENT_LAYERS, tools/select_tool and
# tools/extension_tool. docs/i18n.md rule 4 ("do not translate layer names")
# applies. The user-facing menu entry is the separate, translated literal
# 'Place Joint Closure' in ui/elements_ui.py.
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
        except Exception as e:
            logger.debug(f"could not set alias for field {field_name}: {e}")
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
