"""
FiberQ v2 - Constants Module

This module contains all constant values used throughout the FiberQ plugin.
Constants are organized by category and use English naming conventions.

Note: Database field values (like 'vazdusna', 'podzemna') remain in Serbian
for backward compatibility with existing databases and projects.
"""

from enum import Enum
from typing import Dict, List
from qgis.PyQt.QtGui import QColor


# =============================================================================
# ROUTE TYPE CONSTANTS
# =============================================================================

class RouteType(Enum):
    """Route type enumeration with Serbian database values and English labels."""
    AERIAL = "vazdusna"
    UNDERGROUND = "podzemna"
    THROUGH_OBJECT = "kroz objekat"


# Internal values stored in 'tip_trase' field (Serbian for backward compatibility)
ROUTE_TYPE_OPTIONS: List[str] = [
    RouteType.AERIAL.value,
    RouteType.UNDERGROUND.value,
    RouteType.THROUGH_OBJECT.value,
]

# Display labels for UI (English)
ROUTE_TYPE_LABELS: Dict[str, str] = {
    RouteType.AERIAL.value: "Aerial",
    RouteType.UNDERGROUND.value: "Underground",
    RouteType.THROUGH_OBJECT.value: "Through the object",
}

# Reverse mapping: English label -> Serbian database value
ROUTE_LABEL_TO_CODE: Dict[str, str] = {v: k for k, v in ROUTE_TYPE_LABELS.items()}


# =============================================================================
# CABLE TYPE CONSTANTS
# =============================================================================

class CableSubtype(Enum):
    """Cable subtype enumeration with Serbian database values and English labels."""
    BACKBONE = "glavni"
    DISTRIBUTION = "distributivni"
    DROP = "razvodni"


# Display labels for cable subtypes (English)
CABLE_SUBTYPE_LABELS: Dict[str, str] = {
    CableSubtype.BACKBONE.value: "Backbone",
    CableSubtype.DISTRIBUTION.value: "Distribution",
    CableSubtype.DROP.value: "Drop",
}


# =============================================================================
# LOCATION TYPE CONSTANTS
# =============================================================================

class LocationType(Enum):
    """Location type enumeration for element placement."""
    MANHOLE = "OKNO"
    POLE = "Stub"
    OBJECT = "Objekat"


LOCATION_TYPE_LABELS: Dict[str, str] = {
    LocationType.MANHOLE.value: "Manhole",
    LocationType.POLE.value: "Pole",
    LocationType.OBJECT.value: "Object",
}


# =============================================================================
# SLACK TYPE CONSTANTS
# =============================================================================

class SlackType(Enum):
    """Optical slack type enumeration."""
    TERMINAL = "zavrsna"
    MIDSPAN = "prolazna"


SLACK_TYPE_LABELS: Dict[str, str] = {
    SlackType.TERMINAL.value: "Terminal",
    SlackType.MIDSPAN.value: "Mid-span",
}


# =============================================================================
# CABLE COLOR CONSTANTS
# =============================================================================

# Colors for cable subtypes on map
COLOR_BACKBONE = QColor(0, 51, 153)      # Dark blue for backbone cables
COLOR_DISTRIBUTION = QColor(204, 0, 0)   # Red for distribution cables
COLOR_DROP = QColor(165, 42, 42)         # Brown for drop cables

# Legacy Serbian names (for backward compatibility)
COLOR_GLAVNI = COLOR_BACKBONE
COLOR_DISTR = COLOR_DISTRIBUTION
COLOR_RAZV = COLOR_DROP


# =============================================================================
# FIELD NAME CONSTANTS
# =============================================================================

class FieldNames:
    """
    Database field names (Serbian for backward compatibility)
    with English aliases for display.
    """
    # Common fields
    NAME = "naziv"
    LENGTH_M = "duzina_m"
    LENGTH_KM = "duzina_km"
    LENGTH = "duzina"
    ROUTE_TYPE = "tip_trase"
    SUBTYPE = "podtip"
    MATERIAL = "materijal"
    HEIGHT = "visina"
    CAPACITY = "kapacitet"
    LOCATION = "lokacija"
    TIME = "vreme"

    # Element-specific fields
    OBJECT_NAME = "naziv_objekta"
    CAPACITY_REQUIRED = "zahtev_kapaciteta"
    RESERVE_CAPACITY = "zahtev_rezerve"
    CABLE_LAYER_ID = "cable_layer_id"
    CABLE_FID = "cable_fid"
    MANUFACTURER = "proizvodjac"
    LABEL = "oznaka"
    TOTAL_SC = "ukupno_kj"
    PORT_LABEL = "oznaka_izvoda"
    NUMBERING = "numeracija"
    ADDRESS_STREET = "adresa_ulica"
    ADDRESS_NUMBER = "adresa_broj"
    ADDRESS_ID = "address_id"
    STATUS = "stanje"
    INSTALL_YEAR = "godina_ugradnje"


# Field alias mappings (field_name -> English alias)
FIELD_ALIASES: Dict[str, str] = {
    FieldNames.NAME: "Name",
    FieldNames.LENGTH_M: "Length (m)",
    FieldNames.LENGTH_KM: "Length (km)",
    FieldNames.LENGTH: "Length",
    FieldNames.ROUTE_TYPE: "Route type",
    FieldNames.SUBTYPE: "Subtype",
    FieldNames.MATERIAL: "Material",
    FieldNames.HEIGHT: "Height (m)",
    FieldNames.CAPACITY: "Capacity",
    FieldNames.LOCATION: "Location",
    FieldNames.TIME: "Time",
    FieldNames.OBJECT_NAME: "Object Name",
    FieldNames.CAPACITY_REQUIRED: "Required capacity",
    FieldNames.RESERVE_CAPACITY: "Reserve capacity",
    FieldNames.CABLE_LAYER_ID: "Cable layer ID",
    FieldNames.CABLE_FID: "Cable feature ID",
    FieldNames.MANUFACTURER: "Manufacturer",
    FieldNames.LABEL: "Label",
    FieldNames.TOTAL_SC: "Total SCs",
    FieldNames.PORT_LABEL: "Port label",
    FieldNames.NUMBERING: "Numbering",
    FieldNames.ADDRESS_STREET: "Street",
    FieldNames.ADDRESS_NUMBER: "Street No.",
    FieldNames.ADDRESS_ID: "Address ID",
    FieldNames.STATUS: "Status",
    FieldNames.INSTALL_YEAR: "Install year",
}


# =============================================================================
# LAYER NAME CONSTANTS
# =============================================================================

class LayerNames:
    """Layer names used in the project (both Serbian and English variants)."""
    # Route layer
    ROUTE = "Route"
    ROUTE_SR = "Trasa"

    # Cable layers
    AERIAL_CABLES = "Aerial_cables"
    AERIAL_CABLES_SR = "Kablovi_vazdusni"
    UNDERGROUND_CABLES = "Underground_cables"
    UNDERGROUND_CABLES_SR = "Kablovi_podzemni"

    # Infrastructure layers
    POLES = "Poles"
    POLES_SR = "Stubovi"
    MANHOLES = "Manholes"
    MANHOLES_SR = "OKNA"

    # Duct layers
    PE_DUCTS = "PE_ducts"
    PE_DUCTS_SR = "PE cevi"
    TRANSITION_DUCTS = "Transition_ducts"
    TRANSITION_DUCTS_SR = "Prelazne cevi"

    # Element layers
    JOINT_CLOSURES = "Joint_closures"
    JOINT_CLOSURES_SR = "Nastavci"
    OPTICAL_SLACK = "Optical_slack"
    OPTICAL_SLACK_SR = "Opticke_rezerve"
    FIBER_BREAKS = "Fiber_breaks"
    FIBER_BREAKS_SR = "Prekid vlakna"

    # Service area
    SERVICE_AREA = "Service_area"
    SERVICE_AREA_SR = "Zona opsluživanja"


# Layer name lookup (Serbian -> English)
LAYER_NAME_MAPPING: Dict[str, str] = {
    LayerNames.ROUTE_SR: LayerNames.ROUTE,
    LayerNames.AERIAL_CABLES_SR: LayerNames.AERIAL_CABLES,
    LayerNames.UNDERGROUND_CABLES_SR: LayerNames.UNDERGROUND_CABLES,
    LayerNames.POLES_SR: LayerNames.POLES,
    LayerNames.MANHOLES_SR: LayerNames.MANHOLES,
    LayerNames.PE_DUCTS_SR: LayerNames.PE_DUCTS,
    LayerNames.TRANSITION_DUCTS_SR: LayerNames.TRANSITION_DUCTS,
    LayerNames.JOINT_CLOSURES_SR: LayerNames.JOINT_CLOSURES,
    LayerNames.OPTICAL_SLACK_SR: LayerNames.OPTICAL_SLACK,
    LayerNames.FIBER_BREAKS_SR: LayerNames.FIBER_BREAKS,
    LayerNames.SERVICE_AREA_SR: LayerNames.SERVICE_AREA,
}


# =============================================================================
# STATUS CONSTANTS
# =============================================================================

class ElementStatus(Enum):
    """Element status enumeration."""
    PLANNED = "Planned"
    BUILT = "Built"
    EXISTING = "Existing"


STATUS_OPTIONS: List[str] = [s.value for s in ElementStatus]


# =============================================================================
# PLUGIN SETTINGS KEYS
# =============================================================================

class SettingsKeys:
    """QSettings keys used by the plugin."""
    LANGUAGE = "FiberQ/lang"
    PRO_ENABLED = "pro_enabled"
    COLOR_CATALOGS = "ColorCatalogs/catalogs_v1"


# =============================================================================
# PRO LICENSE CONSTANTS
# =============================================================================

PRO_SETTINGS_ORG = "FiberQ"
PRO_SETTINGS_APP = "FiberQ"
PRO_MASTER_KEY = "FIBERQ-PRO-2025"


# =============================================================================
# UI CONSTANTS
# =============================================================================

# Default symbol sizes
DEFAULT_SYMBOL_SIZE = "10"
DEFAULT_SYMBOL_SIZE_UNIT = "MapUnit"

# Label settings
DEFAULT_LABEL_SIZE = 8.0
DEFAULT_LABEL_OFFSET = 5.0

# Map tolerance (in pixels)
SNAP_TOLERANCE_PIXELS = 10


# =============================================================================
# BACKWARD COMPATIBILITY ALIASES
# =============================================================================

# Legacy constant names (Serbian) mapped to new English names
# These allow existing code to continue working

# Route types
TRASA_TYPE_OPTIONS = ROUTE_TYPE_OPTIONS
TRASA_TYPE_LABELS = ROUTE_TYPE_LABELS
TRASA_LABEL_TO_CODE = ROUTE_LABEL_TO_CODE
