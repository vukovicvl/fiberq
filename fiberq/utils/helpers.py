"""
FiberQ v2 - Helper Utilities Module

This module contains helper functions used throughout the plugin
including icon loading, text normalization, label formatting, and i18n.

Phase 1.1 Refactoring: Added icon loaders and translation helpers
extracted from main_plugin.py for better modularity.
"""

import os
import re
import unicodedata
from typing import Optional, Dict, List

from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtCore import QSettings
from qgis.core import (
    QgsVectorLayer, QgsPalLayerSettings, QgsTextFormat,
    QgsTextBufferSettings, QgsVectorLayerSimpleLabeling, QgsUnitTypes
)

# Phase 5.2: Logging
from .logger import get_logger
logger = get_logger(__name__)


# =============================================================================
# PLUGIN PATHS
# =============================================================================

def get_plugin_dir() -> str:
    """Get the root plugin directory path."""
    return os.path.dirname(os.path.dirname(__file__))


def get_icon_path(filename: str) -> str:
    """
    Get the full path to a toolbar icon file.

    Args:
        filename: Icon filename (e.g., 'ic_routing.svg')

    Returns:
        Full path to the icon file
    """
    return os.path.join(get_plugin_dir(), 'icons', filename)


def get_map_icon_path(filename: str) -> str:
    """
    Get the full path to a map icon file.

    Args:
        filename: Icon filename (e.g., 'map_odf.svg')

    Returns:
        Full path to the map icon file
    """
    return os.path.join(get_plugin_dir(), 'resources', 'map_icons', filename)


def get_style_path(filename: str) -> str:
    """
    Get the full path to a style file.

    Args:
        filename: Style filename (e.g., 'Poles.qml')

    Returns:
        Full path to the style file
    """
    return os.path.join(get_plugin_dir(), 'styles', filename)


# =============================================================================
# ICON LOADING (Phase 1.1 - extracted from main_plugin.py)
# =============================================================================

def _icon_path(filename: str) -> str:
    """
    Get the full path to a toolbar icon file.

    Legacy function name for backward compatibility.
    Prefer get_icon_path() in new code.

    Args:
        filename: Icon filename

    Returns:
        Full path to the icon file
    """
    return os.path.join(get_plugin_dir(), 'icons', filename)


def _load_icon(filename: str) -> QIcon:
    """
    Load an icon from the icons directory.

    Legacy function name for backward compatibility.
    Prefer load_icon() in new code.

    Args:
        filename: Icon filename

    Returns:
        QIcon object (empty icon if file not found)
    """
    try:
        p = _icon_path(filename)
        return QIcon(p) if os.path.exists(p) else QIcon()
    except Exception:
        return QIcon()


def _map_icon_path(filename: str) -> str:
    """
    Get the full path to a map icon file.

    Legacy function name for backward compatibility.
    Prefer get_map_icon_path() in new code.

    Args:
        filename: Icon filename

    Returns:
        Full path to the map icon file
    """
    try:
        return os.path.join(get_plugin_dir(), 'resources', 'map_icons', filename)
    except Exception:
        return filename


def load_icon(filename: str) -> QIcon:
    """
    Load an icon from the icons directory.

    Args:
        filename: Icon filename

    Returns:
        QIcon object (empty icon if file not found)
    """
    try:
        path = get_icon_path(filename)
        if os.path.exists(path):
            return QIcon(path)
    except Exception as e:
        logger.debug(f"Error in load_icon: {e}")
    return QIcon()


def get_element_icon(element_name: str) -> QIcon:
    """
    Get the toolbar icon for an element type.

    Args:
        element_name: Name of the element (e.g., 'ODF', 'Indoor OTB')

    Returns:
        QIcon for the element
    """
    # Map element names to icon slugs
    icon_map = {
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

    slug = icon_map.get(element_name)
    if slug:
        return load_icon(f'ic_place_{slug}.svg')
    return load_icon('ic_place_elements.svg')


def _element_icon_for(name: str) -> QIcon:
    """
    Get the toolbar icon for an element type.

    Legacy function name for backward compatibility.
    Prefer get_element_icon() in new code.

    Args:
        name: Name of the element

    Returns:
        QIcon for the element
    """
    m = {
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
    slug = m.get(name)
    if slug:
        return _load_icon(f'ic_place_{slug}.svg')
    return _load_icon('ic_place_elements.svg')


# =============================================================================
# TEXT UTILITIES
# =============================================================================

def normalize_name(text: str) -> str:
    """
    Normalize a name for comparison by removing diacritics and special characters.

    Args:
        text: Text to normalize

    Returns:
        Normalized lowercase text with only alphanumeric and underscore
    """
    try:
        # Remove diacritics
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")

        # Lowercase and replace non-alphanumeric with underscore
        text = text.lower()
        text = re.sub(r"[^a-z0-9_]+", "_", text)

        return text.strip("_")
    except Exception:
        return text


def clean_layer_name(name: str) -> str:
    """
    Clean a layer name for use in filenames or identifiers.

    Args:
        name: Layer name to clean

    Returns:
        Cleaned name safe for filenames
    """
    try:
        # Remove or replace problematic characters
        cleaned = re.sub(r'[<>:"/\\|?*]', '_', name)
        cleaned = re.sub(r'\s+', '_', cleaned)
        cleaned = cleaned.strip('_')
        return cleaned if cleaned else 'unnamed_layer'
    except Exception:
        return 'unnamed_layer'


# =============================================================================
# LABEL UTILITIES
# =============================================================================

def apply_fixed_text_label(
    layer: QgsVectorLayer,
    field_name: str = 'naziv',
    size_mu: float = 8.0,
    y_offset_mu: float = 5.0,
    buffer_size: float = 0.8,
    buffer_color: QColor = None
) -> bool:
    """
    Apply fixed-size text labels to a layer.

    Makes labels fixed-size in map units with a small offset above the point.

    Args:
        layer: Layer to apply labels to
        field_name: Field to use for label text
        size_mu: Label size in map units
        y_offset_mu: Y offset in map units (positive = above)
        buffer_size: Text buffer size
        buffer_color: Buffer color (default white)

    Returns:
        True if labels applied successfully, False otherwise
    """
    if layer is None:
        return False

    if buffer_color is None:
        buffer_color = QColor(255, 255, 255)

    try:
        settings = QgsPalLayerSettings()
        settings.fieldName = field_name
        settings.enabled = True

        # Set placement to over point
        try:
            settings.placement = getattr(
                QgsPalLayerSettings, 'OverPoint',
                settings.placement
            )
        except Exception as e:
            logger.debug(f"Error in apply_fixed_text_label: {e}")

        # Set offset
        try:
            settings.xOffset = 0.0
            settings.yOffset = float(y_offset_mu)
            settings.offsetUnits = QgsUnitTypes.RenderMapUnits
        except Exception as e:
            logger.debug(f"Error in apply_fixed_text_label: {e}")

        # Configure text format
        text_format = QgsTextFormat()
        try:
            text_format.setSize(float(size_mu))
            text_format.setSizeUnit(QgsUnitTypes.RenderMapUnits)
        except Exception as e:
            logger.debug(f"Error in apply_fixed_text_label: {e}")

        # Configure buffer
        try:
            buffer_settings = QgsTextBufferSettings()
            buffer_settings.setEnabled(True)
            buffer_settings.setSize(buffer_size)
            buffer_settings.setColor(buffer_color)
            text_format.setBuffer(buffer_settings)
        except Exception as e:
            logger.debug(f"Error in apply_fixed_text_label: {e}")

        try:
            settings.setFormat(text_format)
        except Exception as e:
            logger.debug(f"Error in apply_fixed_text_label: {e}")

        # Apply labeling
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()

        return True

    except Exception:
        return False


# =============================================================================
# FIELD ALIAS UTILITIES
# =============================================================================

def apply_field_aliases(
    layer: QgsVectorLayer,
    alias_mapping: Dict[str, str]
) -> int:
    """
    Apply field aliases to a layer.

    Args:
        layer: Layer to apply aliases to
        alias_mapping: Dict mapping field names to display aliases

    Returns:
        Number of aliases successfully applied
    """
    if layer is None:
        return 0

    try:
        fields = layer.fields()
    except Exception:
        return 0

    applied_count = 0

    for field_name, alias in alias_mapping.items():
        try:
            idx = fields.indexFromName(field_name)
            if idx != -1:
                layer.setFieldAlias(idx, alias)
                applied_count += 1
        except Exception:
            continue

    return applied_count


# =============================================================================
# LANGUAGE / I18N (Phase 1.1 - extracted from main_plugin.py)
# =============================================================================

_FIBERQ_LANG_KEY = "FiberQ/lang"


def _get_lang() -> str:
    """
    Get the current UI language setting.

    Legacy function name for backward compatibility.
    Prefer get_language() in new code.

    Returns:
        Language code ('en' or 'sr')
    """
    try:
        return QSettings().value(_FIBERQ_LANG_KEY, "en")
    except Exception:
        return "en"


def _set_lang(lang: str) -> None:
    """
    Set the UI language.

    Legacy function name for backward compatibility.
    Prefer set_language() in new code.

    Args:
        lang: Language code ('en' or 'sr')
    """
    try:
        QSettings().setValue(_FIBERQ_LANG_KEY, lang)
    except Exception as e:
        logger.debug(f"Error in _set_lang: {e}")


def get_language() -> str:
    """
    Get the current UI language setting.

    Returns:
        Language code ('en' or 'sr')
    """
    try:
        return QSettings().value(_FIBERQ_LANG_KEY, "en")
    except Exception:
        return "en"


def set_language(lang: str) -> None:
    """
    Set the UI language.

    Args:
        lang: Language code ('en' or 'sr')
    """
    try:
        QSettings().setValue(_FIBERQ_LANG_KEY, lang)
    except Exception as e:
        logger.debug(f"Error in set_language: {e}")


# Translation phrase map (Serbian ↔ English)
_TRANSLATION_MAP = {
    'Publish to PostGIS': 'Publish to PostGIS',
    'Završna rezerva (prečica)': 'End slack (shortcut)',
    'Razgrani cables (offset)': 'Separate cables (offset)',
    'Show shortcuts': 'Show shortcuts',
    'BOM report (XLSX/CSV)': 'BOM report (XLSX/CSV)',
    'Check (health check)': 'Health check',
    'Cable laying': 'Cable laying',
    'Underground': 'Underground',
    'Aerial': 'Aerial',
    'Main': 'Main',
    'Distribution': 'Distribution',
    'Drop': 'Drop',
    'Place extension': 'Place extension',
    'Drawings': 'Drawings',
    'Attach drawing': 'Attach drawing',
    'Open drawing (by click)': 'Open drawing (by click)',
    'Open FiberQ web': 'Open FiberQ web',
    'Selection': 'Selection',
    'Delete selected': 'Delete selected',
    'Duct infrastructure': 'Duct infrastructure',
    'Place manholes': 'Place manholes',
    'Place PE duct': 'Place PE duct',
    'Place transition duct': 'Place transition duct',
    'Import points': 'Import points',
    'Locator': 'Locator',
    'Hide locator': 'Hide locator',
    'Relations': 'Relations',
    'Latent elements list': 'Latent elements list',
    'Cut infrastructure': 'Cut infrastructure',
    'Fiber break': 'Fiber break',
    'Color catalog': 'Color catalog',
    'Save all layers to GeoPackage': 'Save all layers to GeoPackage',
    'Auto-save to GeoPackage': 'Auto-save to GeoPackage',
    'Optical schematic view': 'Optical schematic view',
    'Optical slack': 'Optical slack',
    'Add end slack (interactive)': 'Add end slack (interactive)',
    'Add thru slack (interactive)': 'Add thru slack (interactive)',
    'End slack at ends of selected cables': 'End slack at ends of selected cables',
    'Preview and export per-layer and summary': 'Preview and export per-layer and summary',
    'Export (.xlsx / .csv)': 'Export (.xlsx / .csv)',
    'By Layers': 'By Layers',
    'Summary': 'Summary',
    'Move element': 'Move elements',
    'Import image to element': 'Attach image to element',
    'Open image (by click)': 'Open image (by click)',
    'Kreiranje Rejona': 'Create region',
    'Kreiraj rejon': 'Create region',
    'Rejon': 'Region',
    'Nacrtaj rejon ručno': 'Draw region (manual)',
    'Nacrtaj rejon rucno': 'Draw region (manual)',
}


def _fiberq_translate(text: str, lang: str) -> str:
    """
    Translate UI text between Serbian and English.

    Args:
        text: Text to translate
        lang: Target language ('en' or 'sr')

    Returns:
        Translated text (or original if no translation found)
    """
    if not isinstance(text, str):
        return text
    text = text.strip()

    sr2en = _TRANSLATION_MAP
    en2sr = {v: k for k, v in sr2en.items()}

    # Simple prefix rules
    if lang == 'en':
        if text.startswith('Place '):
            return 'Place ' + text[len('Place '):]
        return sr2en.get(text, text)
    else:
        if text.startswith('Place '):
            return 'Place ' + text[len('Place '):]
        return en2sr.get(text, text)


def translate_text(text: str, lang: str = None) -> str:
    """
    Translate UI text between Serbian and English.

    Args:
        text: Text to translate
        lang: Target language (uses current setting if None)

    Returns:
        Translated text
    """
    if lang is None:
        lang = get_language()
    return _fiberq_translate(text, lang)


def _apply_text_and_tooltip(obj, lang: str) -> None:
    """
    Apply translation to an object's text and tooltip.

    Args:
        obj: QAction or similar object with text() and toolTip() methods
        lang: Target language
    """
    # Text
    try:
        if hasattr(obj, 'text'):
            t = obj.text()
            nt = _fiberq_translate(t, lang)
            if nt != t:
                obj.setText(nt)
    except Exception as e:
        logger.debug(f"Error in _apply_text_and_tooltip: {e}")

    # ToolTip
    try:
        tip = obj.toolTip()
        if tip:
            ntip = _fiberq_translate(tip, lang)
            if ntip != tip:
                obj.setToolTip(ntip)
    except Exception as e:
        logger.debug(f"Error in _apply_text_and_tooltip: {e}")


def _apply_menu_language(menu, lang: str) -> None:
    """
    Apply translation to a menu and all its actions recursively.

    Args:
        menu: QMenu to translate
        lang: Target language
    """
    try:
        # Title
        try:
            title = menu.title()
            if title:
                menu.setTitle(_fiberq_translate(title, lang))
        except Exception as e:
            logger.debug(f"Error in _apply_menu_language: {e}")

        # Actions (recursively)
        for a in menu.actions():
            try:
                _apply_text_and_tooltip(a, lang)
                sub = a.menu()
                if sub:
                    _apply_menu_language(sub, lang)
            except Exception as e:
                logger.debug(f"Error in _apply_menu_language: {e}")
    except Exception as e:
        logger.debug(f"Error in _apply_menu_language: {e}")


# =============================================================================
# LAYER DETECTION UTILITIES
# =============================================================================

def find_layer_by_name(
    name: str,
    project=None,
    case_sensitive: bool = False
) -> Optional[QgsVectorLayer]:
    """
    Find a layer by name in the project.

    Args:
        name: Layer name to find
        project: QgsProject instance (uses current if None)
        case_sensitive: Whether name matching is case-sensitive

    Returns:
        QgsVectorLayer if found, None otherwise
    """
    if project is None:
        try:
            from qgis.core import QgsProject
            project = QgsProject.instance()
        except ImportError:
            return None

    search_name = name if case_sensitive else name.lower()

    try:
        for layer in project.mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue

            layer_name = layer.name() if case_sensitive else layer.name().lower()
            if layer_name == search_name:
                return layer
    except Exception as e:
        logger.debug(f"Error in find_layer_by_name: {e}")

    return None


def find_layers_by_names(
    names: List[str],
    project=None,
    case_sensitive: bool = False
) -> Optional[QgsVectorLayer]:
    """
    Find a layer matching any of the given names.

    Useful for finding layers that may have Serbian or English names.

    Args:
        names: List of possible layer names
        project: QgsProject instance
        case_sensitive: Whether matching is case-sensitive

    Returns:
        First matching QgsVectorLayer or None
    """
    for name in names:
        layer = find_layer_by_name(name, project, case_sensitive)
        if layer is not None:
            return layer
    return None


def is_route_layer(layer: QgsVectorLayer) -> bool:
    """
    Check if a layer is a route layer.

    Args:
        layer: Layer to check

    Returns:
        True if this is a route layer
    """
    if layer is None:
        return False

    try:
        from qgis.core import QgsWkbTypes

        name = (layer.name() or "").lower()
        is_line = layer.geometryType() == QgsWkbTypes.LineGeometry

        return is_line and name in ('trasa', 'route', 'routes')
    except Exception:
        return False


def is_cable_layer(layer: QgsVectorLayer) -> bool:
    """
    Check if a layer is a cable layer.

    Args:
        layer: Layer to check

    Returns:
        True if this is a cable layer
    """
    if layer is None:
        return False

    try:
        from qgis.core import QgsWkbTypes

        name = (layer.name() or "").lower()
        is_line = layer.geometryType() == QgsWkbTypes.LineGeometry

        cable_keywords = ['kabl', 'cable', 'kablo']
        return is_line and any(kw in name for kw in cable_keywords)
    except Exception:
        return False


def is_pole_layer(layer: QgsVectorLayer) -> bool:
    """
    Check if a layer is a poles layer.

    Args:
        layer: Layer to check

    Returns:
        True if this is a poles layer
    """
    if layer is None:
        return False

    try:
        from qgis.core import QgsWkbTypes

        name = (layer.name() or "").lower()
        is_point = layer.geometryType() == QgsWkbTypes.PointGeometry

        return is_point and name in ('stubovi', 'poles', 'pole')
    except Exception:
        return False


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Path utilities
    'get_plugin_dir',
    'get_icon_path',
    'get_map_icon_path',
    'get_style_path',

    # Icon loading (legacy names)
    '_icon_path',
    '_load_icon',
    '_map_icon_path',
    '_element_icon_for',

    # Icon loading (new names)
    'load_icon',
    'get_element_icon',

    # Text utilities
    'normalize_name',
    'clean_layer_name',

    # Label utilities
    'apply_fixed_text_label',
    'apply_field_aliases',

    # Language/i18n (legacy names)
    '_get_lang',
    '_set_lang',
    '_fiberq_translate',
    '_apply_text_and_tooltip',
    '_apply_menu_language',

    # Language/i18n (new names)
    'get_language',
    'set_language',
    'translate_text',

    # Layer detection
    'find_layer_by_name',
    'find_layers_by_names',
    'is_route_layer',
    'is_cable_layer',
    'is_pole_layer',
]
