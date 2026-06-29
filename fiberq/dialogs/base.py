"""
FiberQ v2 - Dialog Base Classes and Common Imports

This module provides common imports and utilities for all dialogs.

Phase 5.2: Added logging infrastructure
"""

# Qt imports
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialogButtonBox, QListWidget, QScrollArea, QWidget,
    QGroupBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox
)
from qgis.PyQt.QtGui import QColor

# QGIS imports
from qgis.core import QgsVectorLayer, QgsSettings

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


def normalize_name(s: str) -> str:
    """
    Normalize a field name for comparison.

    Removes diacritics, converts to lowercase, and replaces
    non-alphanumeric characters with underscores.
    """
    try:
        import unicodedata
        import re
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = s.lower()
        s = re.sub(r"[^a-z0-9_]+", "_", s)
        return s.strip("_")
    except Exception:
        return s


def default_fields_for(layer_name: str):
    """
    Return a list of (key, label, kind, default, options) for the dialog.

    Args:
        layer_name: Name of the layer to get fields for

    Returns:
        List of tuples: (field_key, label, kind, default_value, options)
        kind: 'text' | 'int' | 'double' | 'enum' | 'year'
    """
    # Delegates to the canonical schema (single source of truth, WP1a).
    from ..models.schema import get_default_fields_for_layer as _schema_fields
    return _schema_fields(layer_name)


def get_current_year():
    """Get the current year for default values."""
    try:
        from datetime import datetime
        return datetime.now().year
    except Exception as e:
        logger.debug(f"Could not get current year: {e}")
        return 2025


__all__ = [
    # Qt widgets
    'Qt',
    'QDialog', 'QVBoxLayout', 'QHBoxLayout', 'QFormLayout',
    'QLabel', 'QLineEdit', 'QPushButton',
    'QComboBox', 'QSpinBox', 'QDoubleSpinBox', 'QCheckBox',
    'QDialogButtonBox', 'QListWidget', 'QScrollArea', 'QWidget',
    'QGroupBox', 'QTextEdit', 'QTableWidget', 'QTableWidgetItem',
    'QHeaderView', 'QMessageBox',
    'QColor',

    # QGIS
    'QgsVectorLayer', 'QgsSettings',

    # Utilities
    'normalize_name',
    'default_fields_for',
    'get_current_year',
]
