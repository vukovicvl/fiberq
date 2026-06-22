# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Settings Dialog.

This module contains the main plugin settings dialog.
"""

from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QFormLayout,
)

from qgis.core import QgsSettings

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class FiberQSettingsDialog(QDialog):
    """Dialog for configuring FiberQ plugin settings."""

    def __init__(self, parent=None, plugin=None):
        super().__init__(parent)

        self.setWindowTitle("FiberQ Settings")
        self.settings = QgsSettings()
        self.plugin = plugin

        layout = QVBoxLayout()

        # Default cable type
        self.cb_default_cable = QComboBox()
        self.cb_default_cable.addItems([
            "Optical – 12F", "Optical – 24F", "Optical – 48F",
            "Optical – 96F", "Optical – 144F"
        ])

        saved = self.settings.value("FiberQ/default_cable_type", "", type=str)
        if saved:
            idx = self.cb_default_cable.findText(saved)
            if idx >= 0:
                self.cb_default_cable.setCurrentIndex(idx)

        layout.addWidget(QLabel("Default Cable Type:"))
        layout.addWidget(self.cb_default_cable)

        # Default slack length (m)
        self.ed_slack = QLineEdit()
        self.ed_slack.setPlaceholderText("10")
        self.ed_slack.setText(self.settings.value("FiberQ/default_slack_length", "10"))
        layout.addWidget(QLabel("Default Slack Length (m):"))
        layout.addWidget(self.ed_slack)

        # Default snapping distance (px)
        self.ed_snap = QLineEdit()
        self.ed_snap.setPlaceholderText("15")
        self.ed_snap.setText(self.settings.value("FiberQ/default_snap_distance", "15"))
        layout.addWidget(QLabel("Default Snapping Distance (px):"))
        layout.addWidget(self.ed_snap)

        # Auto labels
        self.chk_labels = QCheckBox("Enable automatic labels")
        self.chk_labels.setChecked(
            self.settings.value("FiberQ/auto_labels", "true") == "true"
        )
        layout.addWidget(self.chk_labels)

        # Default semantic diagram style
        self.cb_semantic = QComboBox()
        self.cb_semantic.addItems(["Classic", "Compact", "Detailed"])
        saved_style = self.settings.value("FiberQ/default_semantic_style", "Classic")
        idx = self.cb_semantic.findText(saved_style)
        if idx >= 0:
            self.cb_semantic.setCurrentIndex(idx)

        layout.addWidget(QLabel("Default Semantic Diagram Style:"))
        layout.addWidget(self.cb_semantic)

        # ── Quick Toolbar settings (v1.2 Feature 4) ──
        qt_group = QGroupBox("Quick Toolbar")
        qt_layout = QVBoxLayout()

        self.chk_show_quick_toolbar = QCheckBox("Show Quick Toolbar")
        self.chk_show_quick_toolbar.setToolTip(
            "Show a compact toolbar with the 10 most-used design tools.\n"
            "Also available in View → Toolbars → FiberQ Quick."
        )
        show_qt = self.settings.value("FiberQ/quick_toolbar_visible", "true")
        if isinstance(show_qt, bool):
            self.chk_show_quick_toolbar.setChecked(show_qt)
        else:
            self.chk_show_quick_toolbar.setChecked(str(show_qt).lower() in ('true', '1', 'yes'))

        self.chk_enable_shortcuts = QCheckBox("Enable keyboard shortcuts (P, M, R, A, U, O, T, S)")
        self.chk_enable_shortcuts.setToolTip(
            "Enable single-letter keyboard shortcuts for the Quick Toolbar tools.\n"
            "These may conflict with other plugins or QGIS shortcuts.\n"
            "Default: off."
        )
        sc_on = self.settings.value("FiberQ/quick_toolbar_shortcuts", "false")
        if isinstance(sc_on, bool):
            self.chk_enable_shortcuts.setChecked(sc_on)
        else:
            self.chk_enable_shortcuts.setChecked(str(sc_on).lower() in ('true', '1', 'yes'))

        qt_layout.addWidget(self.chk_show_quick_toolbar)
        qt_layout.addWidget(self.chk_enable_shortcuts)
        qt_group.setLayout(qt_layout)
        layout.addWidget(qt_group)

        # Save button
        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self.save)
        layout.addWidget(btn_save)

        self.setLayout(layout)

    def save(self):
        """Save settings and close dialog."""
        self.settings.setValue("FiberQ/default_cable_type", self.cb_default_cable.currentText())
        self.settings.setValue("FiberQ/default_slack_length", self.ed_slack.text())
        self.settings.setValue("FiberQ/default_snap_distance", self.ed_snap.text())
        self.settings.setValue("FiberQ/auto_labels", "true" if self.chk_labels.isChecked() else "false")
        self.settings.setValue("FiberQ/default_semantic_style", self.cb_semantic.currentText())

        # Quick Toolbar settings (v1.2 Feature 4)
        show_qt = self.chk_show_quick_toolbar.isChecked()
        sc_on = self.chk_enable_shortcuts.isChecked()
        self.settings.setValue("FiberQ/quick_toolbar_visible", "true" if show_qt else "false")
        self.settings.setValue("FiberQ/quick_toolbar_shortcuts", "true" if sc_on else "false")

        # Apply immediately if plugin reference is available
        if self.plugin and hasattr(self.plugin, 'quick_toolbar') and self.plugin.quick_toolbar:
            self.plugin.quick_toolbar.set_visible(show_qt)
            self.plugin.quick_toolbar.set_shortcuts_enabled(sc_on)

        self.accept()


__all__ = ['FiberQSettingsDialog']
