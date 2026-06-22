
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QCheckBox,
                                 QLabel, QDialogButtonBox)

# Phase 5.3: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)

ORG = "FiberQ"
ORG_OLD = "Telecom_plugin"
APP = "FiberQ"
APP_OLD = "FTTx"

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FiberQ Settings")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.ed_slack = QLineEdit()
        self.ed_branch = QLineEdit()
        self.ed_status = QLineEdit()
        self.ed_default_schema = QLineEdit()
        self.ed_updated_by = QLineEdit()
        self.chk_lower = QCheckBox("Lowercase column names (publish)")
        form.addRow("Slack field name:", self.ed_slack)
        form.addRow("Branch index field name:", self.ed_branch)
        form.addRow("Status field name:", self.ed_status)
        form.addRow("Default schema:", self.ed_default_schema)
        form.addRow("Default updated_by:", self.ed_updated_by)
        form.addRow("", self.chk_lower)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self._load()

    def _load(self):
        s = QSettings(ORG, APP)
        s_old = QSettings(ORG_OLD, APP_OLD)
        self.ed_slack.setText(s.value("fields/slack_m", s_old.value("fields/slack_m", "slack_m")))
        self.ed_branch.setText(s.value("fields/branch_index", s_old.value("fields/branch_index", "branch_index")))
        self.ed_status.setText(s.value("fields/status", s_old.value("fields/status", "status")))
        self.ed_default_schema.setText(s.value("publish/default_schema", s_old.value("publish/default_schema", "public")))
        self.ed_updated_by.setText(s.value("publish/updated_by", s_old.value("publish/updated_by", "")))
        self.chk_lower.setChecked(s.value("publish/lowercase", s_old.value("publish/lowercase", True, type=bool), type=bool))

    def save(self):
        s = QSettings(ORG, APP)
        s_old = QSettings(ORG_OLD, APP_OLD)
        s.setValue("fields/slack_m", self.ed_slack.text().strip())
        s.setValue("fields/branch_index", self.ed_branch.text().strip())
        s.setValue("fields/status", self.ed_status.text().strip())
        s.setValue("publish/default_schema", self.ed_default_schema.text().strip())
        s.setValue("publish/updated_by", self.ed_updated_by.text().strip())
        s.setValue("publish/lowercase", self.chk_lower.isChecked())

    def accept(self):
        self.save()
        super().accept()
