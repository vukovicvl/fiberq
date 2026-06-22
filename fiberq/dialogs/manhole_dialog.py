"""
FiberQ v2 - Manhole Dialogs

Dialogs for selecting manhole type and entering manhole details.
"""

from .base import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QDialogButtonBox, QLabel,
    QLineEdit, QComboBox, QSpinBox, QCheckBox, QListWidget
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class ManholeTypeDialog(QDialog):
    """
    Dialog for selecting manhole type.

    Presents a list of standard manhole types for selection.
    """

    # Standard manhole types
    MANHOLE_TYPES = [
        "Standard cable manhole",
        "Existing standard cable manhole",
        "Standard octagonal 200x130x190",
        "Standard octagonal 250x150x190",
        "Standard octagonal cut 200x120x190",
        "Standard octagonal cut 220x128x190",
        "Mounted mini cable manhole",
        "Existing mini cable manhole",
        "Mounted mini manhole type MB 1",
        "Mounted mini manhole type MB 2",
        "Mounted mini manhole type MB 3",
        "Mounted mini manhole type MB 5",
        "Mounted mini manhole type MBi",
        "Mounted mini manhole type MB1i",
        "Mounted mini manhole type MBr",
        "Mounted mini manhole type Mufa (micro ducts)",
        "Mounted mini manhole type Duct End (micro ducts)",
    ]

    def __init__(self, core):
        """
        Initialize the dialog.

        Args:
            core: Plugin core instance (for accessing iface.mainWindow)
        """
        super().__init__(core.iface.mainWindow())
        self.setWindowTitle("Choose manhole type")
        self.resize(420, 520)

        v = QVBoxLayout(self)

        self.list = QListWidget()
        v.addWidget(self.list)

        for t in self.MANHOLE_TYPES:
            self.list.addItem(t)

        if self.list.count() > 0:
            self.list.setCurrentRow(0)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def selected_type(self):
        """
        Get the selected manhole type.

        Returns:
            Selected type string, or empty string if none selected
        """
        it = self.list.currentItem()
        return it.text() if it else ""


class ManholeDetailsDialog(QDialog):
    """
    Dialog for entering detailed manhole information.

    Includes fields for:
    - Basic info (ID, type, category, location, address)
    - Status and installation year
    - Detailed specifications (dimensions, materials, drainage, etc.)
    """

    def __init__(self, core, prefill_type=""):
        """
        Initialize the dialog.

        Args:
            core: Plugin core instance
            prefill_type: Pre-selected manhole type from ManholeTypeDialog
        """
        super().__init__(core.iface.mainWindow())
        self.setWindowTitle("Enter manhole details")
        self.resize(520, 520)

        v = QVBoxLayout(self)
        form = QFormLayout()
        v.addLayout(form)

        # Basic fields - Manhole ID with auto-increment
        self.ed_broj = QLineEdit()
        self.ed_broj.setPlaceholderText("e.g. MH 1, OKNO-001")

        # Auto-increment controls
        self.chk_auto_increment = QCheckBox("Auto-increment")
        self.chk_auto_increment.setChecked(True)
        self.chk_auto_increment.setToolTip(
            "Automatically increment the ID number on each placement.\n"
            "Enter an initial ID like 'MH 1' or 'OKNO-001' and each\n"
            "click will place the next number in sequence."
        )
        self.chk_auto_increment.toggled.connect(self._on_auto_increment_toggled)

        # Layout: [ID field] [Auto-increment checkbox]
        id_row = QHBoxLayout()
        id_row.addWidget(self.ed_broj, 1)
        id_row.addWidget(self.chk_auto_increment)

        self.ed_tip = QLineEdit(prefill_type)

        self.cmb_vrsta = QComboBox()
        self.cmb_vrsta.addItems(["Standard", "Mounted", "Existing"])

        self.ed_polozaj = QLineEdit()
        self.ed_adresa = QLineEdit()

        self.cmb_stanje = QComboBox()
        self.cmb_stanje.addItems(["Planned", "Executed", "Existing"])

        self.spin_god = QSpinBox()
        self.spin_god.setRange(1900, 2100)
        self.spin_god.setValue(2025)

        # Detailed fields
        self.ed_opis = QLineEdit()
        self.ed_dim = QLineEdit()
        self.ed_mat_zid = QLineEdit()
        self.ed_mat_poklop = QLineEdit()
        self.ed_odvod = QLineEdit()
        self.chk_poklop_teski = QCheckBox()
        self.chk_poklop_laki = QCheckBox()

        self.spin_br_nos = QSpinBox()
        self.spin_br_nos.setRange(0, 20)

        self.spin_debl = QLineEdit()  # Wall thickness as text/double
        self.ed_lestve = QLineEdit()

        # Add form rows - Basic
        form.addRow("Manhole ID:", id_row)
        form.addRow("Manhole type:", self.ed_tip)
        form.addRow("Manhole category:", self.cmb_vrsta)
        form.addRow("Manhole location:", self.ed_polozaj)
        form.addRow("Address:", self.ed_adresa)
        form.addRow("Manhole status:", self.cmb_stanje)
        form.addRow("Installation year:", self.spin_god)

        # Separator
        form.addRow(QLabel("Detailed manhole information"), QLabel(""))

        # Add form rows - Detailed
        form.addRow("Manhole description:", self.ed_opis)
        form.addRow("Dimensions (cm):", self.ed_dim)
        form.addRow("Wall material:", self.ed_mat_zid)
        form.addRow("Cover material:", self.ed_mat_poklop)
        form.addRow("Drainage:", self.ed_odvod)
        form.addRow("Heavy covers:", self.chk_poklop_teski)
        form.addRow("Light covers:", self.chk_poklop_laki)
        form.addRow("Number of supports:", self.spin_br_nos)
        form.addRow("Wall thickness (cm):", self.spin_debl)
        form.addRow("Ladders:", self.ed_lestve)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def _on_auto_increment_toggled(self, checked):
        """Update UI when auto-increment checkbox is toggled."""
        if checked:
            self.ed_broj.setPlaceholderText("e.g. MH 1, OKNO-001")
            self.ed_broj.setToolTip(
                "Enter starting ID with prefix and number.\n"
                "Examples: 'MH 1', 'OKNO-001', 'K-10'\n"
                "The number will auto-increment on each click."
            )
        else:
            self.ed_broj.setPlaceholderText("")
            self.ed_broj.setToolTip("")

    def values(self):
        """
        Get the current values from all form fields.

        Returns:
            Dictionary with all manhole attributes.
            Includes '_auto_increment' key (bool) for the placement tool.
        """
        def val(w):
            if isinstance(w, QComboBox):
                return w.currentText()
            if isinstance(w, QCheckBox):
                return bool(w.isChecked())
            if hasattr(w, 'value'):
                try:
                    return w.value()
                except Exception as e:
                    logger.debug(f"Error in ManholeDetailsDialog.val: {e}")
            return w.text() if hasattr(w, 'text') else None

        # Parse wall thickness
        wall_thickness = None
        try:
            thickness_text = self.spin_debl.text().strip()
            if thickness_text:
                wall_thickness = float(thickness_text)
        except Exception as e:
            logger.debug(f"Error in ManholeDetailsDialog.val: {e}")

        return {
            'broj_okna': val(self.ed_broj),
            '_auto_increment': self.chk_auto_increment.isChecked(),
            'tip_okna': val(self.ed_tip),
            'vrsta_okna': val(self.cmb_vrsta),
            'polozaj_okna': val(self.ed_polozaj),
            'adresa': val(self.ed_adresa),
            'stanje': val(self.cmb_stanje),
            'god_ugrad': val(self.spin_god),
            'opis': val(self.ed_opis),
            'dimenzije': val(self.ed_dim),
            'mat_zida': val(self.ed_mat_zid),
            'mat_poklop': val(self.ed_mat_poklop),
            'odvodnj': val(self.ed_odvod),
            'poklop_tes': val(self.chk_poklop_teski),
            'poklop_lak': val(self.chk_poklop_laki),
            'br_nosaca': val(self.spin_br_nos),
            'debl_zida': wall_thickness,
            'lestve': val(self.ed_lestve),
        }


__all__ = ['ManholeTypeDialog', 'ManholeDetailsDialog']
