"""DELIBERATELY BROKEN seed for `make qt6-check` — see README.md. Do not fix.

Seeds: importing PyQt5 directly instead of going through `qgis.PyQt`, which is what
keeps the plugin loading on both Qt5 and Qt6.
"""

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QWidget


def build_widget(parent: QObject) -> QWidget:
    """Return a widget parented to ``parent``."""
    widget = QWidget()
    widget.setObjectName("seed")
    return widget
