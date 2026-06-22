"""
FiberQ v2 - Field Aliases Module

This module contains all field alias mappings and functions for
applying English display aliases to Serbian database field names.

The aliases provide an English user interface while maintaining
backward compatibility with existing Serbian database schemas.
"""

from typing import Dict, Optional, List, Any
from qgis.core import QgsVectorLayer, QgsEditorWidgetSetup, QgsProject

# Phase 5.2: Logging
from .logger import get_logger
logger = get_logger(__name__)


# =============================================================================
# FIELD ALIAS MAPPINGS
# =============================================================================

# Poles layer field aliases
POLES_FIELD_ALIASES: Dict[str, str] = {
    "tip": "Type",
    "podtip": "Subtype",
    "visina": "Height (m)",
    "materijal": "Material",
    "fiberq_uuid": "FiberQ UUID",
}

# Route layer field aliases
ROUTE_FIELD_ALIASES: Dict[str, str] = {
    "naziv": "Route name",
    "duzina": "Length (m)",
    "duzina_km": "Length (km)",
    "tip_trase": "Route type",
    "fiberq_uuid": "FiberQ UUID",
}

# Cable layer field aliases
CABLE_FIELD_ALIASES: Dict[str, str] = {
    "tip": "Cable type",
    "podtip": "Segment type",
    "color_code": "Color code",
    "broj_cevcica": "Number of ducts",
    "broj_vlakana": "Number of fibers",
    "tip_kabla": "Cable model",
    "vrsta_vlakana": "Fiber type",
    "vrsta_omotaca": "Sheath type",
    "vrsta_armature": "Armour type",
    "talasno_podrucje": "Wavelength band",
    "naziv": "Name",
    "slabljenje_dbkm": "Attenuation [dB/km]",
    "hrom_disp_ps_nmxkm": "Chromatic dispersion [ps/nm/km]",
    "stanje_kabla": "Status",
    "cable_laying": "Installation type",
    "vrsta_mreze": "Network type",
    "godina_ugradnje": "Installation year",
    "konstr_vlakna_u_cevcicama": "Fibers in ducts",
    "konstr_sa_uzlepljenim_elementom": "With bonded element",
    "konstr_punjeni_kabl": "Gel-filled cable",
    "konstr_sa_arm_vlaknima": "Aramid yarn armouring",
    "konstr_bez_metalnih": "Non-metallic",
    "od": "From",
    "do": "To",
    "duzina_m": "Length [m]",
    "slack_m": "Slack [m]",
    "total_len_m": "Total length [m]",
    "fiberq_uuid": "FiberQ UUID",
    # Phase 0.3: Fiber schema for FiberQ Designer
    "fibers_per_tube": "Fibers per tube",
    "total_fibers": "Total fibers",
    "color_standard": "Color standard",
}

# Manhole layer field aliases
MANHOLE_FIELD_ALIASES: Dict[str, str] = {
    "broj_okna": "Manhole ID",
    "tip_okna": "Manhole type",
    "vrsta_okna": "Construction type",
    "polozaj_okna": "Position",
    "adresa": "Address",
    "stanje": "Status",
    "god_ugrad": "Installation year",
    "opis": "Description",
    "dimenzije": "Dimensions (cm)",
    "mat_zida": "Wall material",
    "mat_poklop": "Cover material",
    "odvodnj": "Drainage",
    "poklop_tes": "Heavy cover",
    "poklop_lak": "Light cover",
    "br_nosaca": "Number of steps",
    "debl_zida": "Wall thickness (cm)",
    "lestve": "Ladder",
    "fiberq_uuid": "FiberQ UUID",
}

# Optical slack layer field aliases
SLACK_FIELD_ALIASES: Dict[str, str] = {
    "tip": "Type",
    "duzina_m": "Length (m)",
    "lokacija": "Location",
    "cable_layer_id": "Cable layer ID",
    "cable_fid": "Cable feature ID",
    "strana": "Side",
    "napomena": "Note",
    "fiberq_uuid": "FiberQ UUID",
}

# Pipe layer field aliases (PE ducts, Transition ducts)
PIPE_FIELD_ALIASES: Dict[str, str] = {
    "materijal": "Material",
    "kapacitet": "Capacity",
    "fi": "Diameter (mm)",
    "od": "From",
    "do": "To",
    "duzina_m": "Length (m)",
    "fiberq_uuid": "FiberQ UUID",
}

# Joint closure field aliases
JOINT_CLOSURE_FIELD_ALIASES: Dict[str, str] = {
    "naziv": "Name",
    "fiberq_uuid": "FiberQ UUID",
}

# Fiber break field aliases
FIBER_BREAK_FIELD_ALIASES: Dict[str, str] = {
    "naziv": "Name",
    "cable_layer_id": "Cable layer ID",
    "cable_fid": "Cable feature ID",
    "distance_m": "Distance (m)",
    "segments_hit": "Segments hit",
    "vreme": "Time",
    "fiberq_uuid": "FiberQ UUID",
}

# Objects layer field aliases
OBJECTS_FIELD_ALIASES: Dict[str, str] = {
    "tip": "Type",
    "spratova": "Floors above ground",
    "podzemnih": "Floors below ground",
    "ulica": "Street",
    "broj": "Number",
    "naziv": "Name",
    "napomena": "Note",
    "fiberq_uuid": "FiberQ UUID",
}

# Element layers field aliases (ODF, OTB, TB, etc.)
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
    "fiberq_uuid": "FiberQ UUID",
}


# =============================================================================
# VALUE MAP CONFIGURATIONS
# =============================================================================

# Route type value map (Serbian database values -> English display)
ROUTE_TYPE_VALUE_MAP: Dict[str, str] = {
    "Aerial": "vazdusna",
    "Underground": "podzemna",
    "Through the object": "kroz objekat",
}

# Slack location value map
SLACK_LOCATION_VALUE_MAP: Dict[str, str] = {
    "Manhole": "OKNO",
    "Pole": "Stub",
    "Object": "Objekat",
}

# Slack side value map
SLACK_SIDE_VALUE_MAP: Dict[str, str] = {
    "FROM": "od",
    "TO": "do",
    "MID SPAN": "sredina",
}

# Cable type value map
CABLE_TYPE_VALUE_MAP: Dict[str, str] = {
    "Optical": "opticki",
    "Copper": "bakarnI",
}

# Cable subtype value map
CABLE_SUBTYPE_VALUE_MAP: Dict[str, str] = {
    "Backbone": "glavni",
    "Distribution": "distributivni",
    "Drop": "razvodni",
}

# Cable status value map (Issue #8)
CABLE_STATUS_VALUE_MAP: Dict[str, str] = {
    "Planned": "Projektovano",
    "Existing": "Postojeće",
    "Under construction": "U izgradnji",
}

# Cable laying/installation type value map (Issue #8)
CABLE_LAYING_VALUE_MAP: Dict[str, str] = {
    "Underground": "Podzemno",
    "Aerial": "Vazdusno",
}


# =============================================================================
# ALIAS APPLICATION FUNCTIONS
# =============================================================================

def apply_field_aliases(
    layer: QgsVectorLayer,
    alias_map: Dict[str, str]
) -> int:
    """
    Apply field aliases to a layer.

    Args:
        layer: Layer to apply aliases to
        alias_map: Dict mapping field names to display aliases

    Returns:
        Number of aliases successfully applied
    """
    if layer is None or not layer.isValid():
        return 0

    applied = 0

    try:
        fields = layer.fields()

        for field_name, alias in alias_map.items():
            idx = fields.indexOf(field_name)
            if idx >= 0:
                try:
                    layer.setFieldAlias(idx, alias)
                    applied += 1
                except Exception as e:
                    logger.debug(f"Error in apply_field_aliases: {e}")
    except Exception as e:
        logger.debug(f"Error in apply_field_aliases: {e}")

    return applied


def apply_value_map(
    layer: QgsVectorLayer,
    field_name: str,
    value_map: Dict[str, str],
    editable: bool = True
) -> bool:
    """
    Apply a value map editor widget to a field.

    Value maps allow displaying English labels while storing
    Serbian values in the database.

    Args:
        layer: Layer to configure
        field_name: Name of field to configure
        value_map: Dict mapping display labels to stored values
        editable: Whether the field should be editable

    Returns:
        True if successfully applied
    """
    if layer is None or not layer.isValid():
        return False

    try:
        idx = layer.fields().indexOf(field_name)
        if idx < 0:
            return False

        cfg = {"map": value_map}
        layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup("ValueMap", cfg))
        layer.setFieldEditable(idx, editable)

        try:
            layer.updateFields()
        except Exception as e:
            logger.debug(f"Error in apply_value_map: {e}")

        return True

    except Exception as e:
        return False


# =============================================================================
# LAYER-SPECIFIC ALIAS FUNCTIONS
# =============================================================================

def apply_poles_field_aliases(layer: QgsVectorLayer) -> None:
    """
    Apply English field aliases to a poles layer.

    Args:
        layer: Poles layer
    """
    apply_field_aliases(layer, POLES_FIELD_ALIASES)


def apply_route_field_aliases(layer: QgsVectorLayer) -> None:
    """
    Apply English field aliases and value map to a route layer.

    Configures:
    - Field aliases for all route fields
    - Value map for tip_trase (route type) field

    Args:
        layer: Route layer
    """
    # Apply aliases
    apply_field_aliases(layer, ROUTE_FIELD_ALIASES)

    # Apply value map for route type
    apply_value_map(layer, "tip_trase", ROUTE_TYPE_VALUE_MAP)


def apply_cable_field_aliases(layer: QgsVectorLayer, migrate_values: bool = True) -> None:
    """
    Apply English field aliases to a cable layer.

    Optionally migrates old Serbian cable type values to English.

    Args:
        layer: Cable layer
        migrate_values: Whether to migrate old Serbian values
    """
    # Apply aliases
    apply_field_aliases(layer, CABLE_FIELD_ALIASES)

    # Apply value maps
    apply_value_map(layer, "tip", CABLE_TYPE_VALUE_MAP)
    apply_value_map(layer, "podtip", CABLE_SUBTYPE_VALUE_MAP)
    apply_value_map(layer, "stanje_kabla", CABLE_STATUS_VALUE_MAP)  # Issue #8
    apply_value_map(layer, "cable_laying", CABLE_LAYING_VALUE_MAP)  # Issue #8

    # Migrate old Serbian cable type values
    if migrate_values:
        _migrate_cable_type_values(layer)


def _migrate_cable_type_values(layer: QgsVectorLayer) -> None:
    """
    Migrate old Serbian cable type values to English.

    Converts:
    - 'opticki' -> 'Optical'
    - 'bakarnI' -> 'Copper'

    Args:
        layer: Cable layer to migrate
    """
    try:
        tip_idx = layer.fields().indexOf("tip")
        if tip_idx < 0:
            return

        started_edit = False
        if not layer.isEditable():
            layer.startEditing()
            started_edit = True

        changed = False
        for feature in layer.getFeatures():
            val = feature["tip"]
            new_val = None

            if val == "opticki":
                new_val = "Optical"
            elif val == "bakarnI":
                new_val = "Copper"

            if new_val:
                layer.changeAttributeValue(feature.id(), tip_idx, new_val)
                changed = True

        if started_edit:
            if changed:
                layer.commitChanges()
            else:
                layer.rollBack()

    except Exception as e:
        logger.debug(f"Error in _migrate_cable_type_values: {e}")


def apply_manhole_field_aliases(layer: QgsVectorLayer) -> None:
    """
    Apply English field aliases to a manhole layer.

    Args:
        layer: Manhole layer
    """
    apply_field_aliases(layer, MANHOLE_FIELD_ALIASES)

    try:
        layer.triggerRepaint()
    except Exception as e:
        logger.debug(f"Error in apply_manhole_field_aliases: {e}")


def apply_slack_field_aliases(layer: QgsVectorLayer) -> None:
    """
    Apply English field aliases and value maps to a slack layer.

    Args:
        layer: Optical slack layer
    """
    # Apply aliases
    apply_field_aliases(layer, SLACK_FIELD_ALIASES)

    # Apply value maps
    apply_value_map(layer, "lokacija", SLACK_LOCATION_VALUE_MAP)
    apply_value_map(layer, "strana", SLACK_SIDE_VALUE_MAP)

    try:
        layer.updateFields()
    except Exception as e:
        logger.debug(f"Error in apply_slack_field_aliases: {e}")


def apply_pipe_field_aliases(layer: QgsVectorLayer) -> None:
    """
    Apply English field aliases to a pipe layer (PE ducts, transition ducts).

    Args:
        layer: Pipe layer
    """
    apply_field_aliases(layer, PIPE_FIELD_ALIASES)


def apply_joint_closure_aliases(layer: QgsVectorLayer) -> None:
    """
    Apply English field aliases to a joint closure layer.

    Args:
        layer: Joint closure layer
    """
    apply_field_aliases(layer, JOINT_CLOSURE_FIELD_ALIASES)


def apply_fiber_break_aliases(layer: QgsVectorLayer) -> None:
    """
    Apply English field aliases to a fiber break layer.

    Args:
        layer: Fiber break layer
    """
    apply_field_aliases(layer, FIBER_BREAK_FIELD_ALIASES)

    try:
        layer.updateFields()
        layer.triggerRepaint()
    except Exception as e:
        logger.debug(f"Error in apply_fiber_break_aliases: {e}")


def apply_objects_field_aliases(layer: QgsVectorLayer) -> None:
    """
    Apply English field aliases to an objects layer.

    Args:
        layer: Objects/buildings layer
    """
    apply_field_aliases(layer, OBJECTS_FIELD_ALIASES)


def apply_element_aliases(layer: QgsVectorLayer) -> None:
    """
    Apply English field aliases to an element layer (ODF, OTB, TB, etc.).

    Args:
        layer: Element layer
    """
    apply_field_aliases(layer, ELEMENT_FIELD_ALIASES)


# =============================================================================
# LAYER NAME ALIASES
# =============================================================================

def set_layer_display_name(layer: QgsVectorLayer, display_name: str) -> bool:
    """
    Set the display name for a layer in the Layers panel.

    Args:
        layer: Layer to rename
        display_name: Display name to show

    Returns:
        True if successful
    """
    try:
        root = QgsProject.instance().layerTreeRoot()
        node = root.findLayer(layer.id())
        if node:
            node.setCustomLayerName(display_name)
            return True
    except Exception as e:
        logger.debug(f"Error in set_layer_display_name: {e}")

    return False


def set_route_layer_alias(layer: QgsVectorLayer) -> None:
    """Set the route layer display name to 'Route'."""
    set_layer_display_name(layer, "Route")


def set_manhole_layer_alias(layer: QgsVectorLayer) -> None:
    """Set the manhole layer display name to 'Manholes'."""
    set_layer_display_name(layer, "Manholes")


def set_slack_layer_alias(layer: QgsVectorLayer) -> None:
    """Set the slack layer display name to 'Optical slack'."""
    set_layer_display_name(layer, "Optical slack")


def set_joint_closure_layer_alias(layer: QgsVectorLayer) -> None:
    """Set the joint closure layer display name to 'Joint Closures'."""
    set_layer_display_name(layer, "Joint Closures")


def set_pipe_layer_alias(layer: QgsVectorLayer) -> None:
    """
    Set the pipe layer display name based on layer name.

    Converts:
    - 'PE cevi' -> 'PE pipes'
    - 'Prelazne cevi' -> 'Transition pipes'
    """
    try:
        name = (layer.name() or "").strip()

        if name in ("PE cevi", "PE pipes"):
            layer.setName("PE pipes")
        elif name in ("Prelazne cevi", "Transition pipes"):
            layer.setName("Transition pipes")
    except Exception as e:
        logger.debug(f"Error in set_pipe_layer_alias: {e}")


def set_objects_layer_alias(layer: QgsVectorLayer) -> None:
    """Set the objects layer display name to 'Objects'."""
    set_layer_display_name(layer, "Objects")
