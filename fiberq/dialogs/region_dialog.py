# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Region Dialog.

This module contains the dialog for creating service areas/regions.
"""

from qgis.PyQt.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QLabel,
    QDialogButtonBox,
    QDoubleSpinBox,
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class CreateRegionDialog(QDialog):
    """Dialog for creating a service area from selection."""

    def __init__(self, core, parent=None):
        super().__init__(parent or core.iface.mainWindow())
        self.core = core
        self.setWindowTitle('Service Area')
        lay = QFormLayout(self)

        self.edt_name = QLineEdit()
        self.edt_name.setPlaceholderText('e.g. Service Area 1')
        lay.addRow(QLabel('Service Area Name'), self.edt_name)

        self.spin_buffer = QDoubleSpinBox()
        self.spin_buffer.setDecimals(1)
        self.spin_buffer.setMinimum(0.0)
        self.spin_buffer.setMaximum(9999.0)
        self.spin_buffer.setSingleStep(1.0)
        self.spin_buffer.setValue(5.0)
        self.spin_buffer.setSuffix(' m')
        lay.addRow(QLabel('Margin (buffer)'), self.spin_buffer)

        self.lbl_info = QLabel('Use selection from map (cables/elements).')
        self.lbl_info.setStyleSheet('color: #475569')
        lay.addRow(self.lbl_info)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def buffer_value(self) -> float:
        """Get the buffer/margin value in meters."""
        try:
            return float(self.spin_buffer.value())
        except Exception as e:
            return 0.0

    def region_name(self) -> str:
        """Get the region name entered by user."""
        return (self.edt_name.text() or '').strip() or 'Rejon'


__all__ = ['CreateRegionDialog']
