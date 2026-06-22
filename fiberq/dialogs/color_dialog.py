# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Color Catalog Dialog.

This module contains dialogs for managing color catalogs
(fiber/tube color standards).
"""

import json

from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLineEdit,
    QLabel,
    QDialogButtonBox,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QMessageBox,
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


# Standard 12-color fiber catalog
STANDARD_12_COLORS = [
    {"name": "Blue", "hex": "#0000FF"},
    {"name": "Orange", "hex": "#FF8000"},
    {"name": "Green", "hex": "#00FF00"},
    {"name": "Brown", "hex": "#8B4513"},
    {"name": "Slate", "hex": "#708090"},
    {"name": "White", "hex": "#FFFFFF"},
    {"name": "Red", "hex": "#FF0000"},
    {"name": "Black", "hex": "#000000"},
    {"name": "Yellow", "hex": "#FFFF00"},
    {"name": "Violet", "hex": "#EE82EE"},
    {"name": "Rose", "hex": "#FF007F"},
    {"name": "Aqua", "hex": "#00FFFF"},
]


class ColorCatalogManagerDialog(QDialog):
    """Dialog for viewing and editing color catalogs (fiber/tube color standards).

    Left: catalog list; Right: color arrangement; Bottom: +/-, Save/Close.
    """

    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        self.core = core
        self.setWindowTitle("Choose color catalogs")
        self.resize(720, 520)

        self.data = self.core._load_color_catalogs()
        self.catalogs = list(self.data.get("catalogs", []))

        # UI
        main = QVBoxLayout(self)
        grid = QGridLayout()
        main.addLayout(grid)

        lbl_left = QLabel("Standard")
        lbl_right = QLabel("Color arrangement")
        grid.addWidget(lbl_left, 0, 0)
        grid.addWidget(lbl_right, 0, 1)

        self.list_catalogs = QListWidget()
        self.list_colors = QListWidget()
        self.list_colors.setAlternatingRowColors(True)
        grid.addWidget(self.list_catalogs, 1, 0)
        grid.addWidget(self.list_colors, 1, 1)

        # Row of + / - for catalogs
        row_btns = QHBoxLayout()
        self.btn_add = QPushButton("+")
        self.btn_edit = QPushButton("✎")
        self.btn_del = QPushButton("-")
        self.btn_import = QPushButton("Import")
        self.btn_export = QPushButton("Export")
        self.btn_add.setFixedWidth(28)
        self.btn_edit.setFixedWidth(28)
        self.btn_del.setFixedWidth(28)
        row_btns.addWidget(self.btn_add)
        row_btns.addWidget(self.btn_edit)
        row_btns.addWidget(self.btn_del)
        row_btns.addSpacing(8)
        row_btns.addWidget(self.btn_import)
        row_btns.addWidget(self.btn_export)
        row_btns.addStretch()
        main.addLayout(row_btns)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close)
        main.addWidget(btns)

        # Signals
        self.list_catalogs.currentRowChanged.connect(self._on_select_catalog)
        self.btn_add.clicked.connect(self._on_add_catalog)
        self.btn_edit.clicked.connect(self._on_edit_catalog)
        self.btn_del.clicked.connect(self._on_delete_catalog)
        self.btn_import.clicked.connect(self._on_import_catalog)
        self.btn_export.clicked.connect(self._on_export_catalog)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)

        self._refresh_catalog_list()
        if self.list_catalogs.count() > 0:
            self.list_catalogs.setCurrentRow(0)

    def _refresh_catalog_list(self):
        self.list_catalogs.clear()
        for c in self.catalogs:
            it = QListWidgetItem(c.get("name", ""))
            self.list_catalogs.addItem(it)

    def _on_select_catalog(self, row):
        self.list_colors.clear()
        if 0 <= row < len(self.catalogs):
            cols = self.catalogs[row].get("colors", [])
            for col in cols:
                name = col.get("name", "")
                hx = col.get("hex", "#cccccc")
                it = QListWidgetItem(name)
                it.setBackground(QColor(hx))
                # if dark color, use white text
                try:
                    c = QColor(hx)
                    if c.red()*0.299 + c.green()*0.587 + c.blue()*0.114 < 140:
                        it.setForeground(QColor(255, 255, 255))
                except Exception as e:
                    logger.debug(f"Error in ColorCatalogManagerDialog._on_select_catalog: {e}")
                self.list_colors.addItem(it)

    def _on_add_catalog(self):
        dlg = NewColorCatalogDialog(self.core, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            c = dlg.result_catalog()
            if c and c.get("name"):
                # replace if same name exists
                names = [x.get("name", "") for x in self.catalogs]
                if c["name"] in names:
                    self.catalogs[names.index(c["name"])] = c
                else:
                    self.catalogs.append(c)
                self._refresh_catalog_list()
                self.list_catalogs.setCurrentRow(len(self.catalogs)-1)

    def _on_edit_catalog(self):
        row = self.list_catalogs.currentRow()
        if 0 <= row < len(self.catalogs):
            current = self.catalogs[row]
            dlg = NewColorCatalogDialog(self.core, parent=self, initial=current)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                updated = dlg.result_catalog()
                if updated and updated.get("name"):
                    names = [x.get("name", "") for x in self.catalogs]
                    if updated["name"] in names and names.index(updated["name"]) != row:
                        self.catalogs[names.index(updated["name"])] = updated
                        del self.catalogs[row]
                        self._refresh_catalog_list()
                        self.list_catalogs.setCurrentRow(names.index(updated["name"]))
                    else:
                        self.catalogs[row] = updated
                        self._refresh_catalog_list()
                        self.list_catalogs.setCurrentRow(row)

    def _on_export_catalog(self):
        row = self.list_catalogs.currentRow()
        if not (0 <= row < len(self.catalogs)):
            QMessageBox.warning(self, "Export", "Select a catalog to export.")
            return
        cat = self.catalogs[row]
        path, _ = QFileDialog.getSaveFileName(self, "Save catalog", f"{cat.get('name', 'catalog')}.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cat, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Export", "Catalog exported.")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Error saving: {e}")

    def _on_import_catalog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import catalog", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cat = json.load(f)
            if not isinstance(cat, dict) or 'name' not in cat or 'colors' not in cat:
                raise ValueError('Unknown JSON format')
            names = [x.get('name', '') for x in self.catalogs]
            if cat['name'] in names:
                self.catalogs[names.index(cat['name'])] = cat
            else:
                self.catalogs.append(cat)
            self._refresh_catalog_list()
            self.list_catalogs.setCurrentRow(max(0, len(self.catalogs)-1))
            QMessageBox.information(self, "Import", "Catalog imported.")
        except Exception as e:
            QMessageBox.critical(self, "Import", f"Error: {e}")

    def _on_delete_catalog(self):
        row = self.list_catalogs.currentRow()
        if 0 <= row < len(self.catalogs):
            del self.catalogs[row]
            self._refresh_catalog_list()
            if self.list_catalogs.count() > 0:
                self.list_catalogs.setCurrentRow(0)

    def _on_save(self):
        self.data["catalogs"] = self.catalogs
        self.core._save_color_catalogs(self.data)
        self.accept()


class NewColorCatalogDialog(QDialog):
    """Dialog for creating or editing a color catalog."""

    def __init__(self, core, parent=None, initial=None):
        super().__init__(parent or core.iface.mainWindow())
        self.core = core
        self._initial = initial
        self._std = STANDARD_12_COLORS
        self.setWindowTitle("Color Catalog")
        self.setMinimumWidth(400)

        v = QVBoxLayout(self)

        # Name
        form_name = QHBoxLayout()
        form_name.addWidget(QLabel("Name:"))
        self.edit_name = QLineEdit()
        form_name.addWidget(self.edit_name)
        v.addLayout(form_name)

        # Color list
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        v.addWidget(self.list)

        # Buttons for reorder/remove
        row_btns = QHBoxLayout()
        self.btn_remove = QPushButton("Remove")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        self.btn_up.setFixedWidth(28)
        self.btn_down.setFixedWidth(28)
        row_btns.addWidget(self.btn_remove)
        row_btns.addWidget(self.btn_up)
        row_btns.addWidget(self.btn_down)
        row_btns.addStretch()
        v.addLayout(row_btns)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        v.addWidget(btns)

        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down.clicked.connect(self._move_down)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        # Prepopulate: if editing – use existing values, otherwise standard 12 colors
        if self._initial:
            self.edit_name.setText(self._initial.get('name', ''))
            for c in self._initial.get('colors', []):
                self._add_color(c)
        else:
            for c in self._std:
                self._add_color(c)

    def _add_color(self, col):
        it = QListWidgetItem(col.get("name", ""))
        hx = col.get("hex", "#cccccc")
        it.setBackground(QColor(hx))
        try:
            c = QColor(hx)
            if c.red()*0.299 + c.green()*0.587 + c.blue()*0.114 < 140:
                it.setForeground(QColor(255, 255, 255))
        except Exception as e:
            logger.debug(f"Error in NewColorCatalogDialog._add_color: {e}")
        self.list.addItem(it)

    def _remove_selected(self):
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)

    def _move_up(self):
        row = self.list.currentRow()
        if row > 0:
            it = self.list.takeItem(row)
            self.list.insertItem(row-1, it)
            self.list.setCurrentRow(row-1)

    def _move_down(self):
        row = self.list.currentRow()
        if 0 <= row < self.list.count()-1:
            it = self.list.takeItem(row)
            self.list.insertItem(row+1, it)
            self.list.setCurrentRow(row+1)

    def result_catalog(self):
        """Returns dict {name, colors:[{name,hex},]}"""
        cols = []
        for i in range(self.list.count()):
            txt = self.list.item(i).text()
            # find HEX from standard table
            hex_val = next((c.get("hex") for c in self._std if c.get("name") == txt), "#cccccc")
            cols.append({"name": txt, "hex": hex_val})
        return {"name": self.edit_name.text().strip(), "colors": cols}


__all__ = ['ColorCatalogManagerDialog', 'NewColorCatalogDialog', 'STANDARD_12_COLORS']
