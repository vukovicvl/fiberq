"""
FiberQ v2 - Field Aliases Module

This module contains all field alias mappings and functions for
applying English display aliases to Serbian database field names.

The aliases provide an English user interface while maintaining
backward compatibility with existing Serbian database schemas.
"""

import os
import re
import sqlite3
from contextlib import closing
from typing import Dict
from qgis.PyQt.QtCore import QCoreApplication, QObject, QT_TRANSLATE_NOOP, Qt, pyqtSlot
from qgis.core import QgsEditorWidgetSetup, QgsExpression, QgsFeatureRequest, QgsVectorLayer

# Phase 5.2: Logging
from .errors import OperationErrors, check_commit
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

# Cable type value map: the value FiberQ stores (models/schema.py says why).
CABLE_TYPE_VALUE_MAP: Dict[str, str] = {
    "Optical": "Optical",
    "Copper": "Copper",
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

    except Exception:
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

    The rows are found first, and an edit session is opened only when one of
    them needs changing. This runs on every cable restyle -- after every Lay
    cable, after every slack recompute, twice per cable layer at project open
    -- and used to open a session and roll it back whenever there was nothing
    to change. In a project whose transaction mode is "Buffered groups" (QGIS
    3.26+) ``rollBack()`` rolls back the whole project, so the restyle after
    the first Lay cable, which creates the cable layer while the user is
    editing, threw away every unsaved edit in the project and ended the
    session (measured on 3.40.15, 3.44.15 and 4.2.3). Where the provider can
    be asked for the old values directly, only those rows are read
    (``_old_cable_types_can_be_queried``).

    Args:
        layer: Cable layer to migrate
    """
    try:
        tip_idx = layer.fields().indexOf("tip")
        if tip_idx < 0:
            return

        prefiltered = _old_cable_types_can_be_queried(layer)
        if prefiltered:
            # Flags first: setFlags() replaces them all, SubsetOfAttributes too.
            rows = layer.getFeatures(QgsFeatureRequest().setFlags(
                QgsFeatureRequest.Flag.NoGeometry).setSubsetOfAttributes([tip_idx]).setFilterExpression(
                f"{QgsExpression.quotedColumnRef('tip')} IN ('opticki', 'bakarnI')"))
        else:
            rows = layer.getFeatures()

        todo = []
        for feature in rows:
            val = feature["tip"]
            new_val = None

            if val == "opticki":
                new_val = "Optical"
            elif val == "bakarnI":
                new_val = "Copper"

            if new_val:
                todo.append((feature.id(), new_val))
        if not todo:
            return
        if prefiltered:
            # The provider's own order is fid order, the order the whole read
            # met them; an attribute index on "tip" may hand them back by value.
            todo.sort()

        # Every answer checked: the session, each change and the commit used to
        # be thrown away. A layer that cannot be edited -- read-only, a database
        # login without the right to update -- keeps its old values, which the
        # form still shows correctly (schema.py declares them as legacy
        # values), so that is logged rather than pushed at every restyle.
        started_edit = False
        if not layer.isEditable():
            if not layer.startEditing():
                logger.warning(f"Cable types in '{layer.name()}' stay opticki/bakarnI: the layer "
                               f"could not be opened for editing")
                return
            started_edit = True

        refused = sum(1 for fid, new_val in todo if not layer.changeAttributeValue(fid, tip_idx, new_val))
        if refused:
            logger.warning(f"{refused} cable(s) in '{layer.name()}' would not take their English type")

        if started_edit:
            # A refused commit leaves the layer in edit mode with the rewrite
            # pending (utils.errors.check_commit never rolls back), so the user
            # is told why it is in edit mode.
            src = QT_TRANSLATE_NOOP('FiberQErrors', "Cable types")
            with OperationErrors(QCoreApplication.translate('FiberQErrors', src)) as errors:
                check_commit(layer, errors)

    except Exception as e:
        logger.warning(f"Could not migrate the cable types in '{layer.name()}': {e}")


def _old_cable_types_can_be_queried(layer: QgsVectorLayer) -> bool:
    """True when the provider can be asked for the old values directly (WP4 4.1, PF-s).

    Most restyles find nothing to migrate: every project made since the
    English rename. Reading only the rows whose ``tip`` is an old value, and
    only that column, saves reading every cable whole each time. The
    ``==`` tests stay, so a looser match (a GeoPackage column declared
    NOCASE, say) still changes only what it always changed.

    Only on a layer that is not being edited, from a memory layer or a
    GeoPackage without a filter, because the query answers differently
    anywhere else (measured on 3.22.16, 3.44.15 and 4.2.3 in the design and
    code reviews): with an edit buffer it hands back changed rows first, so
    the user's undo stack gets the changes in another order; with a field
    added or deleted in the buffer it returns rows without "tip", or none; a
    shapefile's own attribute index is not updated by QGIS edits, so a value
    re-picked and saved is not found; and a GeoPackage filter SQLite answers
    through an attribute index reads in that index's order, which the sort
    below would not keep. There the whole layer is read exactly as before.
    """
    if layer.isEditable():
        return False
    provider = layer.dataProvider()
    if provider is None:
        return False
    if provider.name() == "memory":
        return True
    return provider.name() == "ogr" and provider.storageType() == "GPKG" and not layer.subsetString()


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


#: The alias FiberQ up to 1.5.0 gave ``fid`` on every point layer it took for a
#: joint closure layer (``FiberQPlugin._on_layers_added``): one named Joint
#: Closures, or one whose fields are among id, fid and naziv -- which takes in a
#: GeoPackage layer with no field but its key. In a GeoPackage ``fid`` is the
#: table's primary key, never a cable's; a cable's feature id is ``cable_fid``.
WRONG_FID_ALIAS = "Cable feature ID"


def clear_wrong_fid_alias(layer: QgsVectorLayer) -> None:
    """Take :data:`WRONG_FID_ALIAS` off a field named ``fid``.

    Save all and auto-save stored it in the GeoPackage's default style, and a
    saved project stored it too, so it comes back with the layer: FiberQ runs
    this on every layer added to the project, and again each time QGIS loads
    that layer's style (:class:`WrongFidAliasWatch`). Only that exact alias,
    and only on ``fid``: an alias the user gave it is left alone, and so is the
    right "Cable feature ID" on ``cable_fid``. Neither this nor setting an
    alias marks a project modified (measured on 3.22.16, 3.40.15 and 4.2.3), so
    a project opened with the alias in it still opens unmodified.
    """
    idx = layer.fields().indexFromName("fid")
    if idx != -1 and layer.attributeAlias(idx) == WRONG_FID_ALIAS:
        layer.removeFieldAlias(idx)


class WrongFidAliasWatch(QObject):
    """Takes :data:`WRONG_FID_ALIAS` off ``fid`` each time a watched layer's style loads.

    QGIS's own Add Layer adds a layer to the project first and loads its
    default style after. Layer > Add Layer > Add Vector Layer..., the Browser
    panel and a file dropped on QGIS all make the layer without its style, add
    it -- ``layersAdded``, where FiberQ clears an alias that is not there yet
    -- and only then call ``loadDefaultStyle()``, which brings the stored
    alias back (``QgsAppLayerHandling::addSublayers`` on 3.40 and 4.2,
    ``QgisApp::addSublayers`` on 3.22). ``styleLoaded`` follows every style
    load that succeeds, with the style already on the layer (measured on
    3.22.16, 3.40.15, 3.44.15, 4.0.3 and 4.2.3), so the alias goes as it
    arrives, by the same rule -- also when Layer Properties' "Restore Default"
    reloads it.

    One per plugin load. Qt drops a connection when either end is deleted: a
    layer removed from the project takes its own along, and deleting the
    watch, in ``FiberQPlugin.unload``, takes all of them.
    """

    def follow(self, layer: QgsVectorLayer) -> bool:
        """Follow ``layer``'s style loads; False when it already was followed."""
        try:
            layer.styleLoaded.connect(self._style_loaded, Qt.ConnectionType.UniqueConnection)
        except TypeError:
            # Qt refuses a second, identical connection, and PyQt raises it.
            return False
        return True

    @pyqtSlot()
    def _style_loaded(self):
        layer = self.sender()
        if isinstance(layer, QgsVectorLayer):
            clear_wrong_fid_alias(layer)


#: One ``<alias .../>`` element of a QML style. QGIS writes its attributes in
#: no fixed order: a Qt 5 build (3.22.16, 3.40.15) changes the order from one
#: run to the next, and 4.2.3 writes ``field index name`` (measured), so they
#: are read as a set, never matched in a row.
_ALIAS_ELEMENT = re.compile(r"<alias\b[^<>]*>")
_ATTRIBUTE = re.compile(r"""([A-Za-z_][\w.:-]*)\s*=\s*("[^"]*"|'[^']*')""")
_WRONG_NAME = re.compile(r"""(\bname\s*=\s*)(["'])""" + re.escape(WRONG_FID_ALIAS) + r"\2")


def without_wrong_fid_alias(qml: str) -> str:
    """``qml`` with :data:`WRONG_FID_ALIAS` taken off the field named ``fid``.

    Only an ``<alias/>`` whose ``field`` is exactly ``fid`` and whose ``name``
    is exactly that alias loses it (``name=""``); every other byte is kept,
    the right "Cable feature ID" on ``cable_fid`` included.
    """
    def cleaned(match):
        element = match.group(0)
        attributes = {name: value[1:-1] for name, value in _ATTRIBUTE.findall(element)}
        if attributes.get("field") != "fid" or attributes.get("name") != WRONG_FID_ALIAS:
            return element
        return _WRONG_NAME.sub(lambda found: found.group(1) + found.group(2) * 2, element, count=1)

    return _ALIAS_ELEMENT.sub(cleaned, qml)


def clear_wrong_fid_alias_in_styles(gpkg_path):
    """Take :data:`WRONG_FID_ALIAS` off ``fid`` in the styles a GeoPackage stores.

    :func:`clear_wrong_fid_alias` takes it off a layer in the project, and the
    next save writes that layer's style -- but Save all does not write the
    style of a layer already living in its file, so a default style saved
    before 1.6.0 kept the alias, and QGIS without FiberQ still showed it.
    Save all and auto-save therefore run this on the file they write into.

    Straight SQL on ``layer_styles``, in one transaction, never QGIS's style
    API: on QGIS 3.22 saving over an existing default style opens a modal
    "overwrite?" box. Each ``styleQML`` changes only as
    :func:`without_wrong_fid_alias` says; no other column is touched.

    Returns:
        ``(changed, reason)``: how many stored styles changed, and sqlite's own
        words when the file refused, empty otherwise.
    """
    if not gpkg_path or not os.path.isfile(gpkg_path):
        return 0, ""
    changed = 0
    try:
        # closing(): a connection's own ``with`` ends a transaction, never the
        # connection. isolation_level=None puts the transaction in our hands.
        with closing(sqlite3.connect(gpkg_path, isolation_level=None)) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                                "AND name = 'layer_styles' COLLATE NOCASE").fetchone():
                return 0, ""
            # Looked for before the write lock is taken: nearly always there is
            # nothing to do, and a save should not lock the file for nothing.
            if not conn.execute("SELECT 1 FROM layer_styles WHERE instr(styleQML, ?) > 0 LIMIT 1",
                                (WRONG_FID_ALIAS,)).fetchone():
                return 0, ""
            conn.execute("BEGIN IMMEDIATE")
            try:
                rows = conn.execute("SELECT rowid, styleQML FROM layer_styles WHERE instr(styleQML, ?) > 0",
                                    (WRONG_FID_ALIAS,)).fetchall()
                for rowid, qml in rows:
                    if not isinstance(qml, str):
                        continue
                    fixed = without_wrong_fid_alias(qml)
                    if fixed != qml:
                        conn.execute("UPDATE layer_styles SET styleQML = ? WHERE rowid = ?", (fixed, rowid))
                        changed += 1
                conn.execute("COMMIT")
            except sqlite3.Error:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error as rollback_exc:
                    logger.warning(f"Could not roll back the fid alias clean-up: {rollback_exc}")
                raise
    except sqlite3.Error as exc:
        return 0, f"{type(exc).__name__}: {exc}"
    return changed, ""


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

# ``set_layer_display_name`` and the five one-line wrappers that called it
# (route, manhole, slack, joint closure, objects) lived here until v1.6.0. They
# existed to show a Serbian-named layer under an English label in the Layers
# panel, through ``QgsLayerTreeLayer.setCustomLayerName`` -- a QGIS 2.x method.
# It exists on no QGIS this plugin supports: measured AttributeError on 3.22.16,
# 3.40.15, 3.44.15, 4.0.3 and 4.2.3. Every call raised, every caller caught it
# at debug level, and no label was ever set.
#
# They are NOT replaced by ``node.setName()``. That is the modern API, but with
# ``useLayerName`` true it renames the LAYER as well as the node (measured on
# all five), and this plugin identifies its layers by name in well over a
# hundred places. Honouring the old intent would therefore break Delete
# selected, Save all layers, validation and cable laying at once.
#
# The display name a user sees is now simply the layer name. ``set_pipe_layer_alias``
# below stays, because it calls ``layer.setName()`` on purpose: it renames
# 'PE cevi' to 'PE pipes' for real, and always has.

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
