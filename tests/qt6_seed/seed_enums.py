"""DELIBERATELY BROKEN seed for `make qt6-check` — see README.md. Do not fix.

Seeds: unscoped enums. Qt6 requires the enum class in the path
(`Qt.AlignmentFlag.AlignLeft`, `QgsWkbTypes.Type.Point`), and the unscoped spelling
raises at import time on PyQt6.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsMapLayer, QgsWkbTypes


def alignment():
    """A Qt enum, written the Qt5 way."""
    return Qt.AlignLeft | Qt.AlignVCenter


def question_buttons():
    """A widget enum, written the Qt5 way."""
    return QMessageBox.Yes | QMessageBox.No


def layer_facts():
    """Two QGIS enums, written the Qt5 way."""
    return QgsWkbTypes.Point, QgsMapLayer.VectorLayer
