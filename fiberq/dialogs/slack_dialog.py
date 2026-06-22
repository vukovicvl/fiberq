"""
FiberQ v2 - Slack Dialog

Dialog for entering optical slack (reserve) parameters.
"""

from .base import (
    QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox,
    QLabel, QComboBox, QSpinBox
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class SlackDialog(QDialog):
    """
    Dialog for entering optical slack parameters.

    Allows selection of:
    - Slack type (Terminal/Mid span)
    - Length in meters
    - Location type (Auto/Pole/Manhole/Object)
    """

    def __init__(self, parent=None, default_tip="Terminal"):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget
            default_tip: Default slack type ("Terminal" or "Mid span")
        """
        super().__init__(parent)
        self.setWindowTitle("Optical slack")

        # Slack type combo
        self.cmb_tip = QComboBox()
        self.cmb_tip.addItems(["Terminal", "Mid span"])
        if default_tip in ("Terminal", "Mid span"):
            self.cmb_tip.setCurrentText(default_tip)

        # Length spinner
        self.spn_duz = QSpinBox()
        self.spn_duz.setRange(1, 200)
        self.spn_duz.setValue(20)

        # Location combo (display EN, store SR codes internally)
        self.cmb_lok = QComboBox()
        self.cmb_lok.addItem("Auto", "Auto")
        self.cmb_lok.addItem("Pole", "Stub")
        self.cmb_lok.addItem("Manhole", "OKNO")
        self.cmb_lok.addItem("Object", "Objekat")

        # Layout
        lay = QVBoxLayout(self)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Type:"))
        row1.addWidget(self.cmb_tip)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Length [m]:"))
        row2.addWidget(self.spn_duz)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Location:"))
        row3.addWidget(self.cmb_lok)

        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addLayout(row3)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        lay.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def values(self):
        """
        Get the current values from all form fields.

        Returns:
            Dictionary with tip, duzina_m, lokacija
        """
        return {
            "tip": self.cmb_tip.currentText(),
            "duzina_m": int(self.spn_duz.value()),
            "lokacija": self.cmb_lok.currentData() or self.cmb_lok.currentText(),
        }


__all__ = ['SlackDialog']
