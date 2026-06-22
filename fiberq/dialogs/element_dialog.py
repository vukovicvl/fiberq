"""
FiberQ v2 - Element Placement Dialog

Dialog for entering attributes before placing network elements
(ODF, OTB, TB, etc.) on the map.
"""

from .base import (
    QDialog, QFormLayout, QDialogButtonBox,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QgsVectorLayer,
    normalize_name, default_fields_for, get_current_year
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class PrePlaceAttributesDialog(QDialog):
    """
    Dialog for entering element attributes before placement.

    Dynamically generates form fields based on the target layer
    and element type. Supports text, integer, double, enum, and
    year field types.
    """

    def __init__(self, layer_name: str, layer: QgsVectorLayer = None):
        """
        Initialize the dialog.

        Args:
            layer_name: Name of the target layer (used for title and field defaults)
            layer: Optional existing layer to check for existing fields
        """
        super().__init__()
        self.setWindowTitle(f"Element information — {layer_name}")

        form = QFormLayout(self)
        self._editors = {}

        # Get existing field names from layer
        existing = set()
        try:
            if isinstance(layer, QgsVectorLayer):
                for f in layer.fields():
                    existing.add(normalize_name(f.name()))
        except Exception as e:
            logger.debug(f"Error in PrePlaceAttributesDialog.__init__: {e}")

        # Get default fields for this element type
        fields = default_fields_for(layer_name)

        # Filter to only existing fields if layer has fields
        if existing:
            kept = []
            for (key, label, kind, default, opts) in fields:
                if key == "naziv" or key in existing:
                    kept.append((key, label, kind, default, opts))
            fields = kept

        current_year = get_current_year()

        # Create form widgets
        for (key, label, kind, default, opts) in fields:
            if kind == "enum":
                w = QComboBox()
                try:
                    w.addItems(opts or [])
                except Exception as e:
                    logger.debug(f"Error in PrePlaceAttributesDialog.__init__: {e}")
                try:
                    w.setCurrentText(str(default))
                except Exception as e:
                    logger.debug(f"Error in PrePlaceAttributesDialog.__init__: {e}")

            elif kind == "int" or kind == "year":
                w = QSpinBox()
                try:
                    w.setRange(0, 999999)
                    if kind == "year" and default in (None, 0, ""):
                        w.setValue(int(current_year))
                    else:
                        w.setValue(int(default or 0))
                except Exception as e:
                    logger.debug(f"Error in PrePlaceAttributesDialog.__init__: {e}")

            elif kind == "double":
                w = QDoubleSpinBox()
                try:
                    w.setDecimals(3)
                    w.setRange(-1e9, 1e9)
                    w.setValue(float(default or 0))
                except Exception as e:
                    logger.debug(f"Error in PrePlaceAttributesDialog.__init__: {e}")

            else:  # text
                w = QLineEdit()
                try:
                    w.setText(str(default or ""))
                except Exception as e:
                    logger.debug(f"Error in PrePlaceAttributesDialog.__init__: {e}")

            form.addRow(label, w)
            self._editors[key] = w

        # Dialog buttons
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self
        )
        form.addRow(bb)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

    def values(self) -> dict:
        """
        Get the current values from all form fields.

        Returns:
            Dictionary mapping field keys to their values
        """
        out = {}
        for key, w in self._editors.items():
            try:
                if isinstance(w, QComboBox):
                    out[key] = w.currentText()
                elif isinstance(w, QSpinBox):
                    out[key] = int(w.value())
                elif isinstance(w, QDoubleSpinBox):
                    out[key] = float(w.value())
                else:
                    out[key] = w.text()
            except Exception as e:
                logger.debug(f"Error in PrePlaceAttributesDialog.values: {e}")
        return out


__all__ = ['PrePlaceAttributesDialog']
