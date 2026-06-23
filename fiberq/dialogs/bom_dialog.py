# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ BOM (Bill of Materials) Dialog.

This module contains the BOM report dialog for generating material lists
with export to XLSX/CSV format.
"""

import textwrap

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QFileDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
    QMessageBox,
)

from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsWkbTypes,
    QgsDistanceArea,
)

from ..utils.legacy_bridge import _fiberq_translate

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class _BOMDialog(QDialog):
    """BOM (Bill of Materials) report dialog with export to XLSX/CSV."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("BOM report (XLSX/CSV)")
        self.resize(820, 520)

        self.tabs = QTabWidget(self)
        self.tab_layers = QWidget(self)
        self.tab_summary = QWidget(self)

        self.tabs.addTab(self.tab_layers, "By Layers")
        self.tabs.addTab(self.tab_summary, "Summary")

        # By layers table
        self.tbl_layers = QTableWidget(self.tab_layers)
        self.tbl_layers.setColumnCount(6)
        self.tbl_layers.setHorizontalHeaderLabels([
            "Layer", "Type", "Number of elements", "Length [m]", "Slack [m]", "Total [m]"
        ])
        self.tbl_layers.horizontalHeader().setStretchLastSection(True)

        v1 = QVBoxLayout(self.tab_layers)
        v1.addWidget(self.tbl_layers)

        # Summary
        self.lbl_summary = QLabel(self.tab_summary)
        self.lbl_summary.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        v2 = QVBoxLayout(self.tab_summary)
        v2.addWidget(self.lbl_summary)

        # Buttons
        btn_export = QPushButton("Export (.xlsx / .csv)", self)
        btn_export.clicked.connect(self._export)

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)
        root.addWidget(btn_export)

        # build data now
        self._build()

    def apply_language(self, lang: str):
        """Apply language translations to the dialog."""
        try:
            self.setWindowTitle(_fiberq_translate("BOM report (XLSX/CSV)", lang))
            self.tabs.setTabText(0, _fiberq_translate("By Layers", lang))
            self.tabs.setTabText(1, _fiberq_translate("Summary", lang))
            try:
                # Header labels
                hs = [
                    _fiberq_translate("Layer", lang),
                    _fiberq_translate("Type", lang),
                    _fiberq_translate("Number of elements", lang),
                    _fiberq_translate("Length [m]", lang),
                    _fiberq_translate("Slack [m]", lang),
                    _fiberq_translate("Total [m]", lang),
                ]
                self.tbl_layers.setHorizontalHeaderLabels(hs)
            except Exception as e:
                logger.debug(f"Error in _BOMDialog.apply_language: {e}")
            # Export button (last widget in root layout)
            try:
                for i in range(self.layout().count() - 1, -1, -1):
                    w = self.layout().itemAt(i).widget()
                    if isinstance(w, QPushButton):
                        w.setText(_fiberq_translate("Export (.xlsx / .csv)", lang))
                        break
            except Exception as e:
                logger.debug(f"Error in _BOMDialog.apply_language: {e}")
        except Exception as e:
            logger.debug(f"Error in _BOMDialog.apply_language: {e}")

    def _distance_area(self):
        """Create a QgsDistanceArea object for measuring."""
        d = QgsDistanceArea()
        try:
            d.setSourceCrs(self.iface.mapCanvas().mapSettings().destinationCrs(),
                           QgsProject.instance().transformContext())
        except Exception:
            try:
                d.setSourceCrs(QgsProject.instance().crs(),
                               QgsProject.instance().transformContext())
            except Exception as e:
                logger.debug(f"Error in _BOMDialog._distance_area: {e}")
        d.setEllipsoid(QgsProject.instance().ellipsoid())
        return d

    def _build(self):
        """Build the BOM data from project layers."""
        project = QgsProject.instance()
        layers = [l for l in project.mapLayers().values() if isinstance(l, QgsVectorLayer)]  # noqa: E741
        d = self._distance_area()

        rows = []
        totals = {
            "line_len": 0.0,
            "line_slack": 0.0,
            "line_total": 0.0,
            "points": 0
        }

        for lyr in layers:
            try:
                gtype = lyr.geometryType()
            except Exception:
                continue

            # Gather stats
            feat_count = 0
            length_m = 0.0
            slack_m = 0.0

            # attribute names tolerant (latin/serbian variations)
            attr_duz = None
            attr_slack = None
            for f in lyr.fields():
                n = f.name().lower()
                if n in ("duzina_m", "dužina_m", "duzina", "dužina", "length_m", "len_m"):
                    attr_duz = f.name()
                if n in ("slack_m", "slack", "slack_m", "slacks_m"):
                    attr_slack = f.name()

            for f in lyr.getFeatures():
                feat_count += 1
                if gtype == QgsWkbTypes.LineGeometry:
                    # prefer attribute duzina if it exists and >0, else compute geometry
                    val_len = None
                    if attr_duz is not None:
                        try:
                            val_len = float(f[attr_duz]) if f[attr_duz] is not None else None
                        except Exception:
                            val_len = None
                    if val_len is None or not (val_len >= 0):
                        try:
                            geom = f.geometry()
                            if geom is not None:
                                val_len = d.measureLength(geom)
                        except Exception:
                            val_len = 0.0
                    length_m += (val_len or 0.0)

                    if attr_slack is not None:
                        try:
                            slack_m += float(f[attr_slack] or 0.0)
                        except Exception as e:
                            logger.debug(f"Error in _BOMDialog._build: {e}")
                elif gtype == QgsWkbTypes.PointGeometry:
                    # nothing to compute; just counting
                    pass

            if gtype == QgsWkbTypes.LineGeometry:
                total_m = length_m + slack_m
                rows.append([lyr.name(), "Line", feat_count, length_m, slack_m, total_m])
                totals["line_len"] += length_m
                totals["line_slack"] += slack_m
                totals["line_total"] += total_m
            elif gtype == QgsWkbTypes.PointGeometry:
                rows.append([lyr.name(), "Point", feat_count, "", "", ""])
                totals["points"] += feat_count
            else:
                # ignore polygonal for now
                continue

        # fill table
        self.tbl_layers.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem("" if val is None else (f"{val:.3f}" if isinstance(val, float) else str(val)))
                if c in (3, 4, 5):  # numeric align right
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tbl_layers.setItem(r, c, item)

        # summary text
        s = textwrap.dedent(f"""
        <b>Total</b><br>
        Total length of lines: <b>{totals['line_len']:.3f} m</b><br>
        Total slack (reserves): <b>{totals['line_slack']:.3f} m</b><br>
        Line + slack: <b>{totals['line_total']:.3f} m</b><br>
        Total number of point elements: <b>{totals['points']}</b>
        """).strip()
        self.lbl_summary.setText(s)
        self._rows = rows
        self._totals = totals

    def _export(self):
        """Export BOM to XLSX or CSV."""
        # prefer XLSX if xlsxwriter is available
        has_xlsx = False
        try:
            import xlsxwriter  # noqa: F401
            has_xlsx = True
        except Exception:
            has_xlsx = False

        if has_xlsx:
            path, _ = QFileDialog.getSaveFileName(self, "Save as", "", "Excel (*.xlsx);;CSV (*.csv)")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Save as", "", "CSV (*.csv);;Excel (*.xlsx)")
        if not path:
            return

        p = path.lower()
        if p.endswith(".xlsx") and has_xlsx:
            self._export_xlsx(path)
        else:
            if not p.endswith(".csv"):
                path = path + ".csv"
            self._export_csv(path)

    def _export_csv(self, path):
        """Export BOM to CSV file."""
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Layer", "Type", "Number", "Length_m", "Slack_m", "Total_m"])
            for row in self._rows:
                w.writerow(row)
            # add a blank and totals
            w.writerow([])
            t = self._totals
            w.writerow(["TOTAL", "", t["points"], t["line_len"], t["line_slack"], t["line_total"]])
        QMessageBox.information(self, "Export", f"CSV exported:\n{path}")

    def _export_xlsx(self, path):
        """Export BOM to XLSX file."""
        import xlsxwriter

        wb = xlsxwriter.Workbook(path)
        ws = wb.add_worksheet("By layers")
        headers = ["Layer", "Type", "Number", "Length_m", "Slack_m", "Total_m"]
        for c, h in enumerate(headers):
            ws.write(0, c, h)
        for r, row in enumerate(self._rows, start=1):
            for c, val in enumerate(row):
                ws.write(r, c, val)
        # totals sheet
        ws2 = wb.add_worksheet("Total")
        t = self._totals
        ws2.write(0, 0, "Total length of lines [m]")
        ws2.write(0, 1, t["line_len"])
        ws2.write(1, 0, "Total slack [m]")
        ws2.write(1, 1, t["line_slack"])
        ws2.write(2, 0, "Line + slack [m]")
        ws2.write(2, 1, t["line_total"])
        ws2.write(3, 0, "Total number of point elements")
        ws2.write(3, 1, t["points"])
        wb.close()
        QMessageBox.information(self, "Export", f"XLSX exported:\n{path}")


__all__ = ['_BOMDialog']
