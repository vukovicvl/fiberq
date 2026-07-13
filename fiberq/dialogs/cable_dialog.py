"""
FiberQ v2 - Cable Picker Dialog

Dialog for selecting cable parameters before laying cables on routes.

Phase 5.2: Added logging infrastructure
"""

from .base import (
    QDialog, QFormLayout, QDialogButtonBox, QLabel,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QgsSettings
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class CablePickerDialog(QDialog):
    """
    Dialog for entering cable parameters.

    Allows selection of:
    - Cable route type (underground/aerial)
    - Cable class (backbone/distribution/drop)
    - Cable type (optical/copper)
    - Fiber/tube counts
    - Additional specifications
    """

    def __init__(self, parent=None, default_vrsta=None, default_podtip=None,
                 default_tip=None, default_color=None, color_codes=None):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget
            default_vrsta: Default cable route type (podzemni/vazdusni)
            default_podtip: Default cable class (glavni/distributivni/razvodni)
            default_tip: Default cable type (Optical/Copper)
            default_color: Default color code
            color_codes: List of available color codes
        """
        super().__init__(parent)
        self.setWindowTitle("Cable parameters")

        # Internal codes (Serbian) and labels (English)
        self.vrste = ["podzemni", "vazdusni"]
        self.podtipi = ["glavni", "distributivni", "razvodni"]

        self.vrste_labels = {
            "podzemni": "Underground",
            "vazdusni": "Aerial",
        }
        self.podtipi_labels = {
            "glavni": "Backbone",
            "distributivni": "Distribution",
            "razvodni": "Drop",
        }

        self.tipovi_po_vrsti = {
            "podzemni": ["Optical", "Copper"],
            "vazdusni": ["Optical", "Copper"],
        }
        self.tip_labels = {
            "Optical": "Optical",
            "Copper": "Copper",
        }

        self.stanja = ["Projektovano", "Postojeće", "U izgradnji"]
        self.stanja_labels = {
            "Projektovano": "Planned",
            "Postojeće": "Existing",
            "U izgradnji": "Under construction",
        }

        self.polaganja = ["Podzemno", "Vazdusno"]
        self.polaganja_labels = {
            "Podzemno": "Underground",
            "Vazdusno": "Aerial",
        }

        self.color_codes = color_codes or []

        layout = QFormLayout(self)

        # Basic fields
        self.cb_vrsta = QComboBox()
        for code in self.vrste:
            self.cb_vrsta.addItem(self.vrste_labels.get(code, code), code)

        self.cb_podtip = QComboBox()
        for code in self.podtipi:
            self.cb_podtip.addItem(self.podtipi_labels.get(code, code), code)

        self.cb_tip = QComboBox()

        self.cb_color = QComboBox()
        self.cb_color.addItems(self.color_codes)

        # Capacity fields
        self.sb_cevcice = QSpinBox()
        self.sb_cevcice.setRange(0, 96)
        self.sb_cevcice.setValue(0)

        self.sb_vlakna = QSpinBox()
        self.sb_vlakna.setRange(0, 864)
        self.sb_vlakna.setValue(0)
        # Track whether the user has manually edited "Number of fibers". Until they
        # do, it auto-follows the computed total (tubes x fibers-per-tube) instead
        # of freezing at an intermediate keystroke value.
        self._vlakna_manual = False
        self.sb_vlakna.valueChanged.connect(lambda _: setattr(self, '_vlakna_manual', True))

        # Phase 0.3: Fiber schema fields for FiberQ Designer
        self.sb_fibers_per_tube = QSpinBox()
        self.sb_fibers_per_tube.setRange(0, 96)
        self.sb_fibers_per_tube.setValue(0)
        self.sb_fibers_per_tube.setToolTip("Number of fibers in each tube (e.g. 6, 8, 12)")

        self.lbl_total_fibers = QLabel("0")
        self.lbl_total_fibers.setStyleSheet("font-weight: bold; color: #1a56db;")
        self.lbl_total_fibers.setToolTip("Computed: tubes × fibers per tube")

        self.cb_color_standard = QComboBox()
        self.cb_color_standard.addItems([
            "",
            "TIA-598-C",
            "IEC 60304",
            "Custom",
        ])
        self.cb_color_standard.setToolTip("Color code standard for fiber identification")

        # Auto-compute total fibers when tubes or fibers_per_tube changes
        def _recompute_total():
            tubes = self.sb_cevcice.value()
            fpt = self.sb_fibers_per_tube.value()
            total = tubes * fpt
            self.lbl_total_fibers.setText(str(total))
            # Sync the legacy "Number of fibers" field to the computed total until
            # the user manually overrides it. blockSignals so our own setValue does
            # not trip the manual-edit flag.
            if not self._vlakna_manual and total > 0:
                self.sb_vlakna.blockSignals(True)
                self.sb_vlakna.setValue(total)
                self.sb_vlakna.blockSignals(False)

        self.sb_cevcice.valueChanged.connect(lambda _: _recompute_total())
        self.sb_fibers_per_tube.valueChanged.connect(lambda _: _recompute_total())

        # Detail fields
        self.le_tip_kabla = QLineEdit()
        self.cb_vrsta_vlakana = QComboBox()
        self.cb_vrsta_vlakana.addItems(["SM", "MM"])
        self.le_vrsta_omotaca = QLineEdit()
        self.le_vrsta_armature = QLineEdit()
        self.le_talasno = QLineEdit()
        self.le_naziv = QLineEdit()

        self.ds_slabljenje = QDoubleSpinBox()
        self.ds_slabljenje.setDecimals(3)
        self.ds_slabljenje.setRange(0.0, 999.0)

        self.ds_hrom_disp = QDoubleSpinBox()
        self.ds_hrom_disp.setDecimals(3)
        self.ds_hrom_disp.setRange(0.0, 9999.0)

        self.cb_stanje = QComboBox()
        for code in self.stanja:
            self.cb_stanje.addItem(self.stanja_labels.get(code, code), code)

        self.cb_polaganje = QComboBox()
        for code in self.polaganja:
            self.cb_polaganje.addItem(self.polaganja_labels.get(code, code), code)

        self.le_vrsta_mreze = QLineEdit()

        self.sb_godina = QSpinBox()
        self.sb_godina.setRange(1900, 2100)
        self.sb_godina.setValue(2025)

        # Load default cable type from settings
        try:
            s = QgsSettings()
            default_cable = s.value("FiberQ/default_cable_type", "", type=str)
            if default_cable:
                self.le_tip_kabla.setText(default_cable)
        except Exception as e:
            logger.debug(f"Error in CablePickerDialog.__init__: {e}")

        # Constructive characteristics (checkboxes)
        self.ch_vlakna_u_cevcicama = QCheckBox()
        self.ch_sa_uzlepljenim = QCheckBox()
        self.ch_punjeni = QCheckBox()
        self.ch_sa_arm_vlaknima = QCheckBox()
        self.ch_bez_metalnih = QCheckBox()

        # Set default values
        if default_vrsta and default_vrsta in self.vrste:
            idx = self.cb_vrsta.findData(default_vrsta)
            if idx >= 0:
                self.cb_vrsta.setCurrentIndex(idx)
            # Set laying type based on route type
            pol_code = "Vazdusno" if "vazdu" in default_vrsta.lower() else "Podzemno"
            idx_pol = self.cb_polaganje.findData(pol_code)
            if idx_pol >= 0:
                self.cb_polaganje.setCurrentIndex(idx_pol)

        if default_podtip and default_podtip in self.podtipi:
            idx = self.cb_podtip.findData(default_podtip)
            if idx >= 0:
                self.cb_podtip.setCurrentIndex(idx)

        # Connect signals
        def refresh_tipovi():
            vr_code = self.cb_vrsta.currentData()
            self.cb_tip.clear()
            for code in self.tipovi_po_vrsti.get(vr_code, []):
                self.cb_tip.addItem(self.tip_labels.get(code, code), code)

        self.cb_vrsta.currentIndexChanged.connect(lambda _=None: refresh_tipovi())
        refresh_tipovi()

        if default_tip:
            idx_tip = self.cb_tip.findData(default_tip)
            if idx_tip >= 0:
                self.cb_tip.setCurrentIndex(idx_tip)

        if default_color and default_color in self.color_codes:
            self.cb_color.setCurrentText(default_color)

        # Add form rows
        layout.addRow("Cable route type:", self.cb_vrsta)
        layout.addRow("Cable class:", self.cb_podtip)
        layout.addRow("Type:", self.cb_tip)
        layout.addRow("Color code:", self.cb_color)
        layout.addRow("Number of tubes:", self.sb_cevcice)
        layout.addRow("Fibers per tube:", self.sb_fibers_per_tube)
        layout.addRow("Total fibers:", self.lbl_total_fibers)
        layout.addRow("Number of fibers:", self.sb_vlakna)
        layout.addRow("Color standard:", self.cb_color_standard)
        layout.addRow(QLabel("— Additional data —"))
        layout.addRow("Cable type:", self.le_tip_kabla)
        layout.addRow("Fiber type:", self.cb_vrsta_vlakana)
        layout.addRow("Sheath type:", self.le_vrsta_omotaca)
        layout.addRow("Armature type:", self.le_vrsta_armature)
        layout.addRow("Wavelength region:", self.le_talasno)
        layout.addRow("Name:", self.le_naziv)
        layout.addRow("Attenuation (dB/km):", self.ds_slabljenje)
        layout.addRow("Chromatic dispersion (ps/nm×km):", self.ds_hrom_disp)
        layout.addRow("Cable condition:", self.cb_stanje)
        layout.addRow("Cable laying:", self.cb_polaganje)
        layout.addRow("Network type:", self.le_vrsta_mreze)
        layout.addRow("Installation year:", self.sb_godina)
        layout.addRow("With fibers in tubes:", self.ch_vlakna_u_cevcicama)
        layout.addRow("With glued element:", self.ch_sa_uzlepljenim)
        layout.addRow("Filled cable:", self.ch_punjeni)
        layout.addRow("With armature fibers:", self.ch_sa_arm_vlaknima)
        layout.addRow("Without metal elements:", self.ch_bez_metalnih)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def values(self):
        """
        Get the current values from all form fields.

        Automatically parses fiber/tube counts from cable type string
        if not manually specified.

        Returns:
            Dictionary with all cable parameters
        """
        tip_kabla = self.le_tip_kabla.text().strip()
        broj_cevcica = int(self.sb_cevcice.value())
        broj_vlakana = int(self.sb_vlakna.value())

        # Try to parse fiber/tube counts from cable type string
        try:
            import re
            tip_lower = tip_kabla.lower()

            # Parse pattern like "4x6", "2x12"
            if broj_cevcica == 0 and broj_vlakana == 0:
                m = re.search(r'(\d+)\s*[x×]\s*(\d+)', tip_lower)
                if m:
                    broj_cevcica = int(m.group(1))
                    broj_vlakana = int(m.group(2))

            # Parse fiber count from "12F", "24F", etc.
            if broj_vlakana == 0:
                fiber_patterns = [
                    ("12f", 12), ("12 f", 12),
                    ("24f", 24), ("24 f", 24),
                    ("48f", 48), ("48 f", 48),
                    ("96f", 96), ("96 f", 96),
                    ("144f", 144), ("144 f", 144),
                ]
                for pattern, count in fiber_patterns:
                    if pattern in tip_lower:
                        broj_vlakana = count
                        break

            # Estimate tube count if not specified
            if broj_cevcica == 0 and broj_vlakana > 0:
                if broj_vlakana <= 12:
                    broj_cevcica = 1
                elif broj_vlakana <= 24:
                    broj_cevcica = 2
                else:
                    broj_cevcica = broj_vlakana // 12 or 1
        except Exception as e:
            logger.debug(f"Error in CablePickerDialog.values: {e}")

        # Get internal codes from combo boxes
        vrsta = self.cb_vrsta.currentData() or self.cb_vrsta.currentText()
        podtip = self.cb_podtip.currentData() or self.cb_podtip.currentText()
        tip = self.cb_tip.currentData() or self.cb_tip.currentText()
        color_code = self.cb_color.currentData() or self.cb_color.currentText()
        vrsta_vlakana = self.cb_vrsta_vlakana.currentData() or self.cb_vrsta_vlakana.currentText()
        stanje_kabla = self.cb_stanje.currentData() or self.cb_stanje.currentText()
        cable_laying = self.cb_polaganje.currentData() or self.cb_polaganje.currentText()

        return {
            "vrsta": vrsta,
            "podtip": podtip,
            "tip": tip,
            "color_code": color_code,
            "broj_cevcica": broj_cevcica,
            "broj_vlakana": broj_vlakana,
            "tip_kabla": tip_kabla,
            "vrsta_vlakana": vrsta_vlakana,
            "vrsta_omotaca": self.le_vrsta_omotaca.text().strip(),
            "vrsta_armature": self.le_vrsta_armature.text().strip(),
            "talasno_podrucje": self.le_talasno.text().strip(),
            "naziv": self.le_naziv.text().strip(),
            "slabljenje_dbkm": float(self.ds_slabljenje.value()),
            "hrom_disp_ps_nmxkm": float(self.ds_hrom_disp.value()),
            "stanje_kabla": stanje_kabla,
            "cable_laying": cable_laying,
            "vrsta_mreze": self.le_vrsta_mreze.text().strip(),
            "godina_ugradnje": int(self.sb_godina.value()),
            "konstr_vlakna_u_cevcicama": 1 if self.ch_vlakna_u_cevcicama.isChecked() else 0,
            "konstr_sa_uzlepljenim_elementom": 1 if self.ch_sa_uzlepljenim.isChecked() else 0,
            "konstr_punjeni_kabl": 1 if self.ch_punjeni.isChecked() else 0,
            "konstr_sa_arm_vlaknima": 1 if self.ch_sa_arm_vlaknima.isChecked() else 0,
            "konstr_bez_metalnih": 1 if self.ch_bez_metalnih.isChecked() else 0,
            # Phase 0.3: Fiber schema for FiberQ Designer
            "fibers_per_tube": int(self.sb_fibers_per_tube.value()),
            "total_fibers": broj_cevcica * int(self.sb_fibers_per_tube.value()),
            "color_standard": (self.cb_color_standard.currentText() or "").strip(),
        }


__all__ = ['CablePickerDialog']
