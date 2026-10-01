"""DELIBERATELY BROKEN seed for `make qt6-check` — see README.md. Do not fix.

Seeds: `exec_()`. PyQt6 dropped the trailing underscore, so a modal dialog opened this
way raises `AttributeError` on QGIS 4.
"""

from qgis.PyQt.QtWidgets import QDialog


def run_dialog(dialog: QDialog) -> int:
    """Open ``dialog`` modally, the Qt5 way."""
    return dialog.exec_()
