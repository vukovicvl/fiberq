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

from ..core.data_manager import PlacingElementIndex
from ..core.interchange import latent_records
from ..utils.batch import features_by_id

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
        # Normalised once, not per row: every row asking latent_records for the
        # whole store made opening the list quadratic again (WP4 PF-2).
        self._records = latent_records(self.data)
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
        # WP4 PF-2: one read per cable layer and one index of the elements,
        # instead of a scan of the cable's layer and a search of every element
        # for each row -- 61 s to open at size S, ~6 min at M (v1.5.0).
        cables = features_by_id((c["layer_id"], c["fid"]) for c in self.cables)
        # Building the index costs 2.0-2.6 searches (by QGIS version), and a
        # cable whose box spans every element still costs ~0.3 of a search
        # through it, so three such cables were slower than v1.5.0's three
        # searches (measured). From four cables the index never is; a shorter
        # list is searched cable by cable, as before.
        elements = PlacingElementIndex() if len(self.cables) > 3 else None
        for row, c in enumerate(self.cables):
            layer = QgsProject.instance().mapLayer(c["layer_id"])
            feat = cables.get(c["layer_id"], {}).get(int(c["fid"]))
            # Select checkbox
            chk = QCheckBox()

            def on_toggled(checked, lyr=layer, fid=int(c["fid"])):
                try:
                    if lyr is None:
                        return
                    if checked:
                        # deselect others
                        for l in QgsProject.instance().mapLayers().values():  # noqa: E741
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
            if layer and feat:
                cands = self.core._find_candidate_elements_for_cable(
                    layer, feat, elements=elements, first=True)
                can_edit = len(cands) > 0
            btn.setEnabled(can_edit)

            def open_edit(lyr=layer, feat=feat, cdict=c, row=row):
                try:
                    d = CablePitstopsDialog(self.core, lyr, feat, cdict, self.data)
                    if d.exec() == QDialog.DialogCode.Accepted:
                        # save updated data already saved in dialog; just refresh counts
                        self._records = latent_records(self.data)
                        m_cnt, sm_cnt = self._latent_counts_for_cable(cdict)
                        self.tbl.setItem(row, 3, QTableWidgetItem(str(m_cnt)))
                        self.tbl.setItem(row, 4, QTableWidgetItem(str(sm_cnt)))
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))
            btn.clicked.connect(open_edit)
            self.tbl.setCellWidget(row, 5, btn)

    def _latent_counts_for_cable(self, c):
        key = self.core._cable_key(c["layer_id"], c["fid"])
        # Through latent_records: a cable a v1.5.0 bundle import wrote is a list
        # of elements, not this dialog's {"elements": [...]}, and reading it as
        # the latter raised on every such cable.
        elems = self._records.get(key, [])
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
        record = (self.store.get("cables") or {}).get(key)
        saved = latent_records({"cables": {key: record}}).get(key, [])
        by_element = {}
        for element in saved:
            ident = _element_key(element)
            if ident is not None:
                by_element.setdefault(ident, element)
        listed = {(it["layer_id"], int(it["fid"])) for it in cands}
        # What the store holds but this list does not show -- an element more
        # than the search distance from the line, a manhole or pole (never a
        # candidate), one a bundle import kept by identity only. Save used to
        # rewrite the record from the candidates alone and drop all of them.
        self._unlisted = [e for e in saved if _element_key(e) not in listed]
        self.elements = []
        self.tbl.setRowCount(len(cands))
        for i, it in enumerate(cands, start=1):
            before = by_element.get((it["layer_id"], int(it["fid"])), {})
            latent = before.get("latent", False)
            # Keep what the stored element carried beyond the four keys
            # (an import's "extra", say); position now gives the order.
            self.elements.append({**_carried(before), **it, "latent": latent})
            self.tbl.setItem(i - 1, 0, QTableWidgetItem(str(i)))
            self.tbl.setItem(i - 1, 1, QTableWidgetItem(it.get("naziv", f"{it['layer_name']}:{it['fid']}")))
            self.tbl.setItem(i - 1, 2, QTableWidgetItem("YES" if latent else "NO"))

    def _toggle_row(self, item):
        row = item.row()
        if 0 <= row < len(self.elements):
            self.elements[row]["latent"] = not self.elements[row]["latent"]
            self.tbl.setItem(row, 2, QTableWidgetItem("YES" if self.elements[row]["latent"] else "NO"))

    def _on_save(self):
        # save to store and project
        key = self.core._cable_key(self.cable_dict["layer_id"], self.cable_dict["fid"])
        rec = {"elements": [
            {**_carried(e), "layer_id": e["layer_id"], "fid": int(e["fid"]),
             "naziv": e.get("naziv", ""), "latent": bool(e.get("latent"))}
            for e in self.elements
        ] + [_unordered(e) for e in getattr(self, "_unlisted", [])]}
        data = dict(self.store)
        data.setdefault("cables", {})[key] = rec
        self.core._save_latent(data)
        self.store.clear()
        self.store.update(data)
        self.accept()


#: Keys the editor rebuilds for every row it lists, or that only ordered a stored
#: element. The row's position gives the order from here on.
_ROW_KEYS = ("layer_id", "fid", "naziv", "latent", "layer_name", "distance", "order_index", "m")
_ORDER_KEYS = ("order_index", "m")


def _carried(element):
    """What a stored element holds beyond the keys the editor rebuilds for a row."""
    return {k: v for k, v in (element or {}).items() if k not in _ROW_KEYS}


def _unordered(element):
    """An element the editor does not list, kept as it is, minus what ordered it."""
    return {k: v for k, v in element.items() if k not in _ORDER_KEYS}


def _element_key(element):
    """``(layer_id, fid)`` of a stored element, or None when it has none usable."""
    try:
        return element.get("layer_id"), int(element.get("fid"))
    except (TypeError, ValueError):
        return None


__all__ = ['LatentElementsDialog', 'CablePitstopsDialog']
