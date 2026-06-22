"""
FiberQ v2 - Pipe Dialogs

Dialogs for selecting PE duct and transition duct parameters.
"""

from .base import (
    QDialog, QVBoxLayout, QDialogButtonBox, QLabel, QListWidget
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class PEDuctDialog(QDialog):
    """
    Dialog for selecting PE duct capacity.

    Presents a list of standard PE duct configurations.
    """

    # PE duct options: (label, attributes_dict)
    PE_OPTIONS = [
        ("Design PE duct (1x1)", {"materijal": "PE", "kapacitet": "1x1", "fi": 40}),
        ("Install duct bank (1x2)", {"materijal": "PE", "kapacitet": "1x2", "fi": 40}),
        ("Install duct bank (2x1)", {"materijal": "PE", "kapacitet": "2x1", "fi": 40}),
        ("Install duct bank (2x2)", {"materijal": "PE", "kapacitet": "2x2", "fi": 40}),
        ("Install duct bank (1x3)", {"materijal": "PE", "kapacitet": "1x3", "fi": 40}),
        ("Install duct bank (2x3)", {"materijal": "PE", "kapacitet": "2x3", "fi": 40}),
        ("Install duct bank (3x3)", {"materijal": "PE", "kapacitet": "3x3", "fi": 40}),
    ]

    def __init__(self, core):
        """
        Initialize the dialog.

        Args:
            core: Plugin core instance
        """
        super().__init__(core.iface.mainWindow())
        self.setWindowTitle("Place PE duct")

        self._options = self.PE_OPTIONS

        self.list = QListWidget(self)
        for label, _ in self._options:
            self.list.addItem(label)
        self.list.setCurrentRow(0)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Choose PE duct capacity:"))
        lay.addWidget(self.list)
        lay.addWidget(btns)

    def values(self):
        """
        Get the selected PE duct parameters.

        Returns:
            Dictionary with materijal, kapacitet, fi
        """
        idx = self.list.currentRow()
        if idx < 0:
            idx = 0
        return dict(self._options[idx][1])


class TransitionDuctDialog(QDialog):
    """
    Dialog for selecting transition duct parameters.

    Presents a list of transition duct configurations with
    different materials (PVC, PE, Oki, FeZn).
    """

    # Transition duct options: (label, attributes_dict)
    TRANSITION_OPTIONS = [
        ("Transition with PVC ducts 1x1 (Ø110)", {"materijal": "PVC", "kapacitet": "1x1", "fi": 110}),
        ("Transition with PVC ducts 1x2 (Ø110)", {"materijal": "PVC", "kapacitet": "1x2", "fi": 110}),
        ("Transition with PE ducts 1x1 (Ø110)", {"materijal": "PE", "kapacitet": "1x1", "fi": 110}),
        ("Transition with PE ducts 1x2 (Ø110)", {"materijal": "PE", "kapacitet": "1x2", "fi": 110}),
        ("Transition with Oki ducts 1x1 (Ø110)", {"materijal": "Oki", "kapacitet": "1x1", "fi": 110}),
        ("Transition with Oki ducts 1x2 (Ø110)", {"materijal": "Oki", "kapacitet": "1x2", "fi": 110}),
        ("Transition with FeZn ducts 1x1 (Ø110)", {"materijal": "FeZn", "kapacitet": "1x1", "fi": 110}),
        ("Transition with FeZn ducts 1x2 (Ø110)", {"materijal": "FeZn", "kapacitet": "1x2", "fi": 110}),
    ]

    def __init__(self, core):
        """
        Initialize the dialog.

        Args:
            core: Plugin core instance
        """
        super().__init__(core.iface.mainWindow())
        self.setWindowTitle("Place transition duct")

        self._options = self.TRANSITION_OPTIONS

        self.list = QListWidget(self)
        for label, _ in self._options:
            self.list.addItem(label)
        self.list.setCurrentRow(0)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Choose transition duct capacity/material:"))
        lay.addWidget(self.list)
        lay.addWidget(btns)

    def values(self):
        """
        Get the selected transition duct parameters.

        Returns:
            Dictionary with materijal, kapacitet, fi
        """
        idx = self.list.currentRow()
        if idx < 0:
            idx = 0
        return dict(self._options[idx][1])


__all__ = ['PEDuctDialog', 'TransitionDuctDialog']
