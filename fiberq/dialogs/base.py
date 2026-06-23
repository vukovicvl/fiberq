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
    base = [
        ("naziv", "Name", "text", "", None),
        ("proizvodjac", "Manufacturer", "text", "", None),
        ("oznaka", "Label", "text", "", None),
        ("kapacitet", "Capacity", "int", 0, None),
        ("ukupno_kj", "Total", "int", 0, None),
        ("zahtev_kapaciteta", "Capacity Requirement", "int", 0, None),
        ("zahtev_rezerve", "Slack Requirement", "int", 0, None),
        ("oznaka_izvoda", "Outlet Label", "text", "", None),
        ("numeracija", "Numbering", "text", "", None),
        ("naziv_objekta", "Object Name", "text", "", None),
        ("adresa_ulica", "Address Street", "text", "", None),
        ("adresa_broj", "Address Number", "text", "", None),
        ("address_id", "Address ID", "text", "", None),
        ("stanje", "Status", "enum", "Planned", ["Planned", "Built", "Existing"]),
        ("godina_ugradnje", "Year of Installation", "year", 2025, None),
    ]

    ln = (layer_name or "").lower()
    if "od ormar" in ln:
        base = [(k, l, kind, (24 if k == "kapacitet" else d), opt)
                for (k, l, kind, d, opt) in base]
    return base


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
