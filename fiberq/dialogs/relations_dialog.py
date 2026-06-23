# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Relations Dialog.

This module contains dialogs for managing optical relations
(grouping cables into named relations/routes).
"""

import uuid
from datetime import datetime

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QWidget,
    QMessageBox,
)

pass

from ..utils.legacy_bridge import RELACIJE_KATEGORIJE  # noqa: E402

# Phase 5.2: Logging
from ..utils.logger import get_logger  # noqa: E402
logger = get_logger(__name__)


class NewRelationDialog(QDialog):
    """Dialog for creating a new optical relation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Optical Relation")
        self.setMinimumWidth(380)

        v = QVBoxLayout(self)
        title = QLabel("<b>New main relation</b>")
        v.addWidget(title)

        form = QFormLayout()
        self.edit_name = QLineEdit()
        self.cmb_cat = QComboBox()
        self.cmb_cat.addItems(RELACIJE_KATEGORIJE)
        form.addRow("Name:", self.edit_name)
        form.addRow("Category:", self.cmb_cat)
        v.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def values(self):
        """Return the relation data as a dict."""
        return {
            "id": str(uuid.uuid4()),
            "name": self.edit_name.text().strip(),
            "category": self.cmb_cat.currentText(),
            "created": datetime.utcnow().isoformat() + "Z",
            "cables": []  # list of {"layer_id":, "fid":}
        }


class RelationsDialog(QDialog):
    """Dialog for managing optical relations."""

    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        self.core = core
        self.setWindowTitle("Optical relations management")
        self.setMinimumSize(700, 520)

        # Load data
        self.data = self.core._load_relations()

        # UI
        main = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Vertical)
        main.addWidget(splitter)

        # Top: relations + buttons
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("New relation")
        self.btn_delete = QPushButton("Delete relation")
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch()
        top_layout.addLayout(btn_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Relation", "Category"])
        self.tree.setColumnWidth(0, 320)
        top_layout.addWidget(self.tree)

        splitter.addWidget(top_widget)

        # Bottom: cables list and assign buttons
        bottom = QWidget()
        bl = QVBoxLayout(bottom)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(3)
        self.tbl.setHorizontalHeaderLabels(["Cable", "Layer", "Relation"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        bl.addWidget(self.tbl)

        row_btns = QHBoxLayout()
        self.btn_assign = QPushButton("Add to selected relation")
        self.btn_remove = QPushButton("Remove from relation")
        row_btns.addWidget(self.btn_assign)
        row_btns.addWidget(self.btn_remove)
        row_btns.addStretch()
        bl.addLayout(row_btns)

        splitter.addWidget(bottom)

        # Signals
        self.btn_new.clicked.connect(self._on_add_relation)
        self.btn_delete.clicked.connect(self._on_delete_relation)
        self.btn_assign.clicked.connect(self._on_assign_to_relation)
        self.btn_remove.clicked.connect(self._on_remove_from_relation)
        self.tree.itemSelectionChanged.connect(self._refresh_cables_relation_column)

        # Populate
        self._refresh_relations_tree()
        self._load_cables()

    # --- Data helpers
    def _refresh_relations_tree(self):
        self.tree.clear()
        for r in self.data.get("relations", []):
            it = QTreeWidgetItem([r.get("name", ""), r.get("category", "")])
            it.setData(0, Qt.ItemDataRole.UserRole, r.get("id"))
            self.tree.addTopLevelItem(it)
        if self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _current_relation_id(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def _on_add_relation(self):
        dlg = NewRelationDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.values()
            if not vals["name"]:
                QMessageBox.warning(self, "Relations", "Relation name is required.")
                return
            self.data.setdefault("relations", []).append(vals)
            self.core._save_relations(self.data)
            self._refresh_relations_tree()

    def _on_delete_relation(self):
        rid = self._current_relation_id()
        if not rid:
            return
        reply = QMessageBox.question(self, "Relations", "Delete selected relation?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.data["relations"] = [r for r in self.data.get("relations", []) if r.get("id") != rid]
        self.core._save_relations(self.data)
        self._refresh_relations_tree()
        self._refresh_cables_relation_column()

    def _load_cables(self):
        self.cables = self.core.list_all_cables()
        self.tbl.setRowCount(len(self.cables))
        for row, c in enumerate(self.cables):
            self.tbl.setItem(row, 0, QTableWidgetItem(c["opis"]))
            self.tbl.setItem(row, 1, QTableWidgetItem(c["layer_name"]))
        self._refresh_cables_relation_column()

    def _refresh_cables_relation_column(self):
        # Defensive guard if dialog reopened before cables are loaded
        if not hasattr(self, 'cables') or self.cables is None:
            self.cables = []
        rid = self._current_relation_id()  # noqa: F841
        # Show assigned relation names for all cables (not only the selected relation).
        rel_name_by_cable = {}
        for r in self.data.get("relations", []):
            for c in r.get("cables", []):
                key = (c.get("layer_id"), int(c.get("fid")))
                rel_name_by_cable[key] = r.get("name")
        for row, c in enumerate(self.cables):
            key = (c["layer_id"], c["fid"])
            nm = rel_name_by_cable.get(key, "")
            self.tbl.setItem(row, 2, QTableWidgetItem(nm))

    def _on_assign_to_relation(self):
        rid = self._current_relation_id()
        if not rid:
            QMessageBox.information(self, "Relations", "Select a relation in the upper list.")
            return
        rel = self.core._relation_by_id(self.data, rid)
        if not rel:
            return
        rows = {i.row() for i in self.tbl.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "Relations", "Select cables in the table.")
            return
        assigned = set((c.get("layer_id"), int(c.get("fid"))) for c in rel.get("cables", []))
        for row in rows:
            c = self.cables[row]
            key = (c["layer_id"], c["fid"])
            if key not in assigned:
                rel.setdefault("cables", []).append({"layer_id": c["layer_id"], "fid": int(c["fid"])})
        self.core._save_relations(self.data)
        self._refresh_cables_relation_column()

    def _on_remove_from_relation(self):
        rid = self._current_relation_id()
        if not rid:
            return
        rel = self.core._relation_by_id(self.data, rid)
        if not rel:
            return
        rows = {i.row() for i in self.tbl.selectedIndexes()}
        if not rows:
            return
        # remove only from current relation
        keep = []
        remove_keys = set()
        for row in rows:
            c = self.cables[row]
            remove_keys.add((c["layer_id"], c["fid"]))
        for c in rel.get("cables", []):
            key = (c.get("layer_id"), int(c.get("fid")))
            if key not in remove_keys:
                keep.append(c)
        rel["cables"] = keep
        self.core._save_relations(self.data)
        self._refresh_cables_relation_column()


__all__ = ['NewRelationDialog', 'RelationsDialog']
