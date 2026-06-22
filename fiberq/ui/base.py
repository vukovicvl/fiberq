"""
FiberQ v2 - UI Base Classes and Common Imports

This module provides common imports and utilities for all UI group classes.
"""

import os

# Qt imports
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAction, QMenu, QToolButton, QMessageBox, QDialog,
    QFileDialog
)
from qgis.PyQt.QtGui import QIcon

# QGIS imports
from qgis.core import QgsProject, QgsVectorLayer

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


def get_plugin_path():
    """Get the plugin directory path."""
    return os.path.dirname(os.path.dirname(__file__))


def load_icon(filename: str) -> QIcon:
    """
    Load an icon from the plugin's icons directory.

    Args:
        filename: Icon filename (e.g., 'ic_add_pole.svg')

    Returns:
        QIcon instance, or empty QIcon if file not found
    """
    try:
        icon_path = os.path.join(get_plugin_path(), 'icons', filename)
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon()
    except Exception as e:
        return QIcon()


def element_icon_for(name: str) -> QIcon:
    """
    Get the appropriate icon for an element type.

    Args:
        name: Element name (e.g., 'ODF', 'TB', 'OTB')

    Returns:
        QIcon for the element type
    """
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
    slug = icon_map.get(name)
    if slug:
        return load_icon(f'ic_place_{slug}.svg')
    return load_icon('ic_place_elements.svg')


# Element definitions for placement
# Import from models to avoid duplication
def get_element_defs():
    """Get element definitions for UI with full symbol information."""
    try:
        from ..models.element_defs import get_all_element_defs
        defs = get_all_element_defs()
        if defs:
            return defs
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Error in get_element_defs: {e}")

    # Fallback - try direct import of ELEMENT_DEFS
    try:
        from ..models.element_defs import ELEMENT_DEFS
        if ELEMENT_DEFS:
            return ELEMENT_DEFS
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Error in get_element_defs: {e}")

    # Last resort fallback to basic definitions (without symbols)
    return [
        {"name": "ODF"},
        {"name": "TB"},
        {"name": "Patch panel"},
        {"name": "OTB"},
        {"name": "Indoor OTB"},
        {"name": "Outdoor OTB"},
        {"name": "Pole OTB"},
        {"name": "TO"},
        {"name": "Indoor TO"},
        {"name": "Outdoor TO"},
        {"name": "Pole TO"},
        {"name": "Joint Closure TO"},
    ]


__all__ = [
    # Qt
    'Qt',
    'QAction', 'QMenu', 'QToolButton', 'QMessageBox', 'QDialog',
    'QFileDialog',
    'QIcon',

    # QGIS
    'QgsProject', 'QgsVectorLayer',

    # Utilities
    'get_plugin_path',
    'load_icon',
    'element_icon_for',
    'get_element_defs',
]
