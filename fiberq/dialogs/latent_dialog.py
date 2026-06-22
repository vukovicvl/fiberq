# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Latent Elements Dialog.

This module contains dialogs for managing latent (hidden/planned) elements
along cable routes.
"""

from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
)

from qgis.core import QgsVectorLayer, QgsProject

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class LatentElementsDialog(QDialog):
    """Dialog for viewing and managing latent elements on cables."""

    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        self.core = core
        self.setWindowTitle("List of latent elements")
        self.resize(820, 520)

        self.data = self.core._load_latent()
        self._rel_map = self.core._relation_name_by_cable()

        layout = QVBoxLayout(self)
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(6)
        self.tbl.setHorizontalHeaderLabels(["", "ID", "Name", "M", "SM", "Edit"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.tbl)

        self._load_cables()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _load_cables(self):
        self.cables = self.core.list_all_cables()
        self.tbl.setRowCount(len(self.cables))
        for row, c in enumerate(self.cables):
            layer = QgsProject.instance().mapLayer(c["layer_id"])
            feat = None
            # Select checkbox
            chk = QCheckBox()

            def on_toggled(checked, lyr=layer, fid=int(c["fid"])):
                try:
                    if lyr is None:
                        return
                    if checked:
                        # deselect others
                        for l in QgsProject.instance().mapLayers().values():
                            if isinstance(l, QgsVectorLayer):
                                l.removeSelection()
                        lyr.selectByIds([fid])
                        self.core.iface.mapCanvas().zoomToSelected(lyr)
                    else:
                        lyr.removeSelection()
                except Exception as e:
                    logger.debug(f"Error in LatentElementsDialog.on_toggled: {e}")
            chk.toggled.connect(on_toggled)
            self.tbl.setCellWidget(row, 0, chk)

            # ID
            self.tbl.setItem(row, 1, QTableWidgetItem(str(c["fid"])))
            # Name from relations
            nm = self._rel_map.get((c["layer_id"], c["fid"]), "")
            self.tbl.setItem(row, 2, QTableWidgetItem(nm))
            # M/SM counts from latent store
            m_cnt, sm_cnt = self._latent_counts_for_cable(c)
            self.tbl.setItem(row, 3, QTableWidgetItem(str(m_cnt)))
            self.tbl.setItem(row, 4, QTableWidgetItem(str(sm_cnt)))
            # Edit button enable if there are >0 candidates
            btn = QPushButton("Edit")
            can_edit = False
            if layer and feat is None:
                # fetch feature by scanning (fallback)
                for f in layer.getFeatures():
                    if int(f.id()) == int(c["fid"]):
                        feat = f
                        break
            if layer and feat:
                cands = self.core._find_candidate_elements_for_cable(layer, feat)
                can_edit = len(cands) > 0
            btn.setEnabled(can_edit)

            def open_edit(lyr=layer, feat=feat, cdict=c, row=row):
                try:
                    d = CablePitstopsDialog(self.core, lyr, feat, cdict, self.data)
                    if d.exec() == QDialog.DialogCode.Accepted:
                        # save updated data already saved in dialog; just refresh counts
                        m_cnt, sm_cnt = self._latent_counts_for_cable(cdict)
                        self.tbl.setItem(row, 3, QTableWidgetItem(str(m_cnt)))
                        self.tbl.setItem(row, 4, QTableWidgetItem(str(sm_cnt)))
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))
            btn.clicked.connect(open_edit)
            self.tbl.setCellWidget(row, 5, btn)

    def _latent_counts_for_cable(self, c):
        key = self.core._cable_key(c["layer_id"], c["fid"])
        rec = self.data.get("cables", {}).get(key, {})
        elems = rec.get("elements", [])
        m_cnt = sum(1 for e in elems if e.get("latent"))
        sm_cnt = sum(1 for e in elems if not e.get("latent"))
        return m_cnt, sm_cnt


class CablePitstopsDialog(QDialog):
    """Dialog for editing latent elements on a specific cable."""

    def __init__(self, core, cable_layer, cable_feat, cable_dict, store):
        super().__init__(core.iface.mainWindow())
        self.core = core
        self.cable_layer = cable_layer
        self.cable_feat = cable_feat
        self.cable_dict = cable_dict
        self.store = store
        self.setWindowTitle("Latent elements - editing")
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(3)
        self.tbl.setHorizontalHeaderLabels(["#", "Element", "Latent"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tbl)

        # Buttons
        rowbtn = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")
        rowbtn.addWidget(self.btn_save)
        rowbtn.addWidget(self.btn_cancel)
        rowbtn.addStretch()
        layout.addLayout(rowbtn)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self._on_save)

        self._load_elements()

        # double-click toggles
        self.tbl.itemDoubleClicked.connect(self._toggle_row)

    def _load_elements(self):
        # candidates ordered
        cands = self.core._find_candidate_elements_for_cable(self.cable_layer, self.cable_feat)
        key = self.core._cable_key(self.cable_dict["layer_id"], self.cable_dict["fid"])
        saved = {
            (e.get("layer_id"), int(e.get("fid"))): bool(e.get("latent"))
            for e in self.store.get("cables", {}).get(key, {}).get("elements", [])
        }
        self.elements = []
        self.tbl.setRowCount(len(cands))
        for i, it in enumerate(cands, start=1):
            latent = saved.get((it["layer_id"], it["fid"]), False)
            self.elements.append({**it, "latent": latent})
            self.tbl.setItem(i-1, 0, QTableWidgetItem(str(i)))
            self.tbl.setItem(i-1, 1, QTableWidgetItem(it.get("naziv", f"{it['layer_name']}:{it['fid']}")))
            self.tbl.setItem(i-1, 2, QTableWidgetItem("YES" if latent else "NO"))

    def _toggle_row(self, item):
        row = item.row()
        if 0 <= row < len(self.elements):
            self.elements[row]["latent"] = not self.elements[row]["latent"]
            self.tbl.setItem(row, 2, QTableWidgetItem("YES" if self.elements[row]["latent"] else "NO"))

    def _on_save(self):
        # save to store and project
        key = self.core._cable_key(self.cable_dict["layer_id"], self.cable_dict["fid"])
        rec = {"elements": [
            {"layer_id": e["layer_id"], "fid": int(e["fid"]), "naziv": e.get("naziv", ""), "latent": bool(e.get("latent"))}
            for e in self.elements
        ]}
        data = dict(self.store)
        data.setdefault("cables", {})[key] = rec
        self.core._save_latent(data)
        self.store.clear()
        self.store.update(data)
        self.accept()


__all__ = ['LatentElementsDialog', 'CablePitstopsDialog']
