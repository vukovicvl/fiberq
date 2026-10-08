# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ BOM (Bill of Materials) Dialog.

This module contains the BOM report dialog for generating material lists
with export to XLSX/CSV format.
"""

import math
import os
import textwrap

from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP, Qt
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
)

from ..core.interchange_fields import actual_field
from ..i18n import safe_format
from ..utils.compat import has_xlsxwriter
from ..utils.errors import describe
from ..utils.geometry import is_finite
from ..utils.legacy_bridge import _fiberq_translate
from ..utils.measure import ground_length

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)

#: WP4 4.2 item R4. The BOM's user-facing strings, in the FiberQBOM context.
_BOM_TITLE = QT_TRANSLATE_NOOP('FiberQBOM', "BOM export")
_WRITE_FAILED = QT_TRANSLATE_NOOP(
    'FiberQBOM', "Could not write the bill of materials to {path}. Reason: {reason}")
_PARTIAL_REMOVED = QT_TRANSLATE_NOOP(
    'FiberQBOM',
    "Could not write the bill of materials to {path}, and the half-written file has been"
    " removed so it cannot be mistaken for a finished export. Reason: {reason}")
_EXPORTED = QT_TRANSLATE_NOOP('FiberQBOM', "Bill of materials exported:\n{path}")
_NO_XLSX = QT_TRANSLATE_NOOP(
    'FiberQBOM',
    "Excel export needs the xlsxwriter module, which is not installed, so the bill of materials"
    " was saved as CSV instead:\n{path}")
_NOT_MEASURED = QT_TRANSLATE_NOOP(
    'FiberQBOM', "Features whose length could not be measured (counted, not included): {count}")
_SLACK_UNREAD = QT_TRANSLATE_NOOP(
    'FiberQBOM', "Slack values that could not be read (not included in the totals): {count}")
_LAYERS_SKIPPED = QT_TRANSLATE_NOOP(
    'FiberQBOM', "Layers left out of this report entirely: {names}")

#: The length column, newest name first, so the canonical FiberQ field wins
#: whatever order the columns happen to be in. The old code iterated the layer's
#: fields and kept the LAST match, so on a layer carrying both ``duzina_m`` and
#: ``length_m`` the answer depended on column order.
_LENGTH_FIELDS = ("duzina_m", "dužina_m", "length_m", "len_m", "duzina", "dužina")
#: Likewise for slack. The old tuple listed "slack_m" twice and "slacks_m" once.
_SLACK_FIELDS = ("slack_m", "slack", "slacks_m")


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

    def _build(self):
        """Build the BOM data from project layers, and say what it could not use.

        WP4 4.2 item R4. Everything this could not measure used to be folded
        silently into the totals as zero, so the report under-counted with no
        indication at all. Measured, before the fix:

        * a null or empty geometry measured 0.0 with no exception;
        * a stored length of 0.0 -- the schema default -- was trusted over a
          real 100 m geometry, because the guard was ``val_len >= 0`` while the
          comment above it said "and >0";
        * an out-of-domain geometry measured **nan**, which turned the table
          cell, the summary and the exported CSV into "nan m";
        * a layer whose data source was gone dropped out of the report
          entirely;
        * an unparseable slack value was dropped from the slack total.

        Each of those is now counted and the count is shown -- in the summary
        and in both exports. Counted, not guessed: a length this cannot measure
        is not zero.

        It also measured with its own ``QgsDistanceArea`` seeded from the MAP
        CRS and the project's ellipsoid, which is often ``NONE``, while the
        length columns the plugin writes come from ``utils.measure.ground_length``.
        Measured: 100.0 m here against 70.93 m there for the same geometry -- a
        41% disagreement inside one report. It now uses ``ground_length`` with
        each layer's own CRS, which is the same number the attribute table
        shows. **The figures this dialog prints therefore change**; that is the
        fix, and it is in the changelog.
        """
        project = QgsProject.instance()
        layers = [l for l in project.mapLayers().values() if isinstance(l, QgsVectorLayer)]  # noqa: E741

        #: What the report could not use. Surfaced in the summary and in both
        #: exports, so the user can tell an under-count from a small network.
        notes = {"unmeasured": 0, "unreadable_slack": 0, "skipped_layers": []}

        rows = []
        totals = {
            "line_len": 0.0,
            "line_slack": 0.0,
            "line_total": 0.0,
            "points": 0
        }

        for lyr in layers:
            if not lyr.isValid():
                # A layer whose file has moved or been deleted used to vanish
                # from the report with no indication, so the BOM under-counted
                # by a whole layer.
                notes["skipped_layers"].append(lyr.name())
                logger.warning("BOM: leaving out %s -- the layer is not valid", lyr.name())
                continue
            gtype = lyr.geometryType()
            if gtype == QgsWkbTypes.GeometryType.UnknownGeometry:
                notes["skipped_layers"].append(lyr.name())
                logger.warning("BOM: leaving out %s -- unknown geometry type", lyr.name())
                continue

            # Gather stats
            feat_count = 0
            length_m = 0.0
            slack_m = 0.0

            # Attribute names, newest first, through the one resolver that
            # knows every spelling. The old loop kept the LAST match, so on a
            # layer carrying both duzina_m and length_m the answer depended on
            # column order.
            names = lyr.fields().names()
            attr_duz = next((actual_field(names, n) for n in _LENGTH_FIELDS
                             if actual_field(names, n)), None)
            attr_slack = next((actual_field(names, n) for n in _SLACK_FIELDS
                               if actual_field(names, n)), None)

            for f in lyr.getFeatures():
                feat_count += 1
                if gtype == QgsWkbTypes.GeometryType.LineGeometry:
                    val_len = None
                    if attr_duz is not None:
                        try:
                            stored = f[attr_duz]
                            val_len = float(stored) if stored is not None else None
                        except (KeyError, TypeError, ValueError):
                            val_len = None
                    # Trust the stored value only when it is a real number
                    # strictly greater than zero. The old guard was `val_len >= 0`
                    # while the comment above it said "and >0", so a schema
                    # default of 0.0 beat a real 100 m geometry. A genuinely
                    # zero-length cable falls through to the geometry, which
                    # also measures 0, so nothing is invented.
                    if val_len is None or not math.isfinite(val_len) or val_len <= 0:
                        val_len = self._measured_length(f, lyr, notes)
                    length_m += val_len

                    if attr_slack is not None:
                        try:
                            raw = f[attr_slack]
                            slack_m += float(raw) if raw is not None else 0.0
                        except (KeyError, TypeError, ValueError):
                            # Counted, not coerced: a slack value this cannot
                            # read is not zero slack.
                            notes["unreadable_slack"] += 1
                            logger.warning("BOM: %s.%s could not be read on feature %s",
                                           lyr.name(), attr_slack, f.id())
                elif gtype == QgsWkbTypes.GeometryType.PointGeometry:
                    # nothing to compute; just counting
                    pass

            if gtype == QgsWkbTypes.GeometryType.LineGeometry:
                total_m = length_m + slack_m
                rows.append([lyr.name(), "Line", feat_count, length_m, slack_m, total_m])
                totals["line_len"] += length_m
                totals["line_slack"] += slack_m
                totals["line_total"] += total_m
            elif gtype == QgsWkbTypes.GeometryType.PointGeometry:
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
        for line in self._note_lines(notes):
            s += "<br>" + line
        self.lbl_summary.setText(s)
        self._rows = rows
        self._totals = totals
        self._notes = notes

    def _measured_length(self, feature, layer, notes):
        """The feature's ground length, or 0.0 with the miss counted.

        Two guards, and the measurements show both are needed.
        ``utils.geometry.is_finite`` checks the bounding box, so it is False for
        a null geometry, for ``LINESTRING EMPTY`` and for infinite coordinates
        -- but TRUE for a geometry whose bbox is finite and whose length comes
        back **nan**, which is what an out-of-domain coordinate pair does. One
        nan used to turn the table cell, the summary and the exported CSV into
        "nan m", so the result is checked as well as the input.
        """
        geom = feature.geometry()
        if geom is None or not is_finite(geom):
            notes["unmeasured"] += 1
            logger.warning("BOM: %s feature %s has no usable geometry",
                           layer.name(), feature.id())
            return 0.0
        try:
            value = ground_length(geom, layer=layer)
        except (RuntimeError, TypeError, ValueError) as exc:
            notes["unmeasured"] += 1
            logger.warning("BOM: could not measure %s feature %s: %s",
                           layer.name(), feature.id(), describe(exc))
            return 0.0
        if not math.isfinite(value):
            notes["unmeasured"] += 1
            logger.warning("BOM: %s feature %s measured as %s", layer.name(), feature.id(), value)
            return 0.0
        return value

    def _note_lines(self, notes):
        """One line per thing the report could not use, and none when it used
        everything. A note shown on every report is a note nobody reads."""
        lines = []
        if notes.get("unmeasured"):
            lines.append(safe_format(QCoreApplication.translate('FiberQBOM', _NOT_MEASURED),
                                     _NOT_MEASURED, count=notes["unmeasured"]))
        if notes.get("unreadable_slack"):
            lines.append(safe_format(QCoreApplication.translate('FiberQBOM', _SLACK_UNREAD),
                                     _SLACK_UNREAD, count=notes["unreadable_slack"]))
        skipped = notes.get("skipped_layers") or []
        if skipped:
            shown = ", ".join(skipped[:3])
            if len(skipped) > 3:
                shown += f" (+{len(skipped) - 3})"
            lines.append(safe_format(QCoreApplication.translate('FiberQBOM', _LAYERS_SKIPPED),
                                     _LAYERS_SKIPPED, names=shown))
        return lines

    def _export(self):
        """Export BOM to XLSX or CSV.

        R4. One decision about whether XLSX is possible, through
        ``utils.compat.has_xlsxwriter``, instead of two independent probes that
        could disagree -- one to pick the file filter and one to pick the
        writer. When they disagreed the user was offered an Excel filter and
        silently handed a CSV.

        The filter strings stay plain literals and never go through ``tr()``:
        ``tests/test_file_filters.py`` names them as two of the deliberate
        inline patterns.
        """
        has_xlsx = has_xlsxwriter()

        if has_xlsx:
            path, _ = QFileDialog.getSaveFileName(self, "Save as", "", "Excel (*.xlsx);;CSV (*.csv)")
        else:
            # Do not offer a format this install cannot write.
            path, _ = QFileDialog.getSaveFileName(self, "Save as", "", "CSV (*.csv)")
        if not path:
            return

        lowered = path.lower()
        if lowered.endswith(".xlsx") and has_xlsx:
            if self._export_xlsx(path):
                self._said(_EXPORTED, path=path)
            return
        asked_for_xlsx = lowered.endswith(".xlsx")
        if asked_for_xlsx:
            # Replace the extension rather than appending it, so the user does
            # not end up with report.xlsx.csv.
            path = path[:-len(".xlsx")] + ".csv"
        elif not lowered.endswith(".csv"):
            path = path + ".csv"
        if self._export_csv(path):
            self._said(_NO_XLSX if asked_for_xlsx else _EXPORTED, path=path)

    def _said(self, source, **kwargs):
        QMessageBox.information(
            self, QCoreApplication.translate('FiberQBOM', _BOM_TITLE),
            safe_format(QCoreApplication.translate('FiberQBOM', source), source, **kwargs))

    def _failed(self, path, exc, removed=False):
        """Report a write that did not finish. Always False, for the caller.

        A modal rather than the message bar: this runs from the BOM dialog's own
        button while that dialog is the active modal widget, so a message-bar
        entry would be behind it. The WARNING log keeps ``utils.errors``'
        promise that nothing is silent.
        """
        logger.warning("BOM export to %s failed: %s", path, describe(exc))
        source = _PARTIAL_REMOVED if removed else _WRITE_FAILED
        QMessageBox.critical(
            self, QCoreApplication.translate('FiberQBOM', _BOM_TITLE),
            safe_format(QCoreApplication.translate('FiberQBOM', source), source,
                        path=path, reason=describe(exc)))
        return False

    def _export_csv(self, path):
        """Export BOM to CSV file. True when the whole file was written.

        R4. There was no error handling at all here, so a read-only target, a
        file open in another program or a full disk sent ``PermissionError`` or
        ``OSError`` out of a Qt slot -- measured, into QGIS's blocking "Python
        error" traceback dialog, which the caller's own try/except never saw.

        Worse than the traceback: ``open(path, "w")`` TRUNCATES before writing.
        Measured -- a previous 1230-byte export became 512 bytes of half-written
        CSV when the disk filled, and the user saw only a traceback. A partial
        file that looks like an export is worse than no file, so it is removed
        and the message says so.
        """
        import csv
        existed = os.path.exists(path)
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Layer", "Type", "Number", "Length_m", "Slack_m", "Total_m"])
                for row in self._rows:
                    w.writerow(row)
                # add a blank and totals
                w.writerow([])
                t = self._totals
                w.writerow(["TOTAL", "", t["points"], t["line_len"], t["line_slack"],
                            t["line_total"]])
                for line in self._note_lines(getattr(self, "_notes", {}) or {}):
                    w.writerow([line])
        except (OSError, UnicodeEncodeError, csv.Error) as exc:
            return self._failed(path, exc, removed=self._remove_partial(path, existed))
        return True

    @staticmethod
    def _remove_partial(path, existed):
        """Delete a half-written export. True when something was removed.

        ``existed`` is not used to decide -- a truncated copy of the user's
        previous export is exactly the file worth removing -- but a target that
        was never created leaves nothing to clean up.
        """
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
        except OSError as exc:
            logger.warning("could not remove the half-written %s: %s", path, describe(exc))
            return False
        return True

    def _export_xlsx(self, path):
        """Export BOM to XLSX file. True when the whole file was written.

        ``xlsxwriter`` writes most of its output in ``close()``, so that is
        where a locked or full target usually fails -- and without a guard the
        workbook was left open and a partial file on disk.
        """
        import xlsxwriter

        existed = os.path.exists(path)
        try:
            return self._write_xlsx(xlsxwriter, path)
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad. xlsxwriter's FileCreateError is not an OSError
            # subclass and the module is optional, so there is no exception
            # tuple that can be named here without importing it at module scope
            # -- which would make an optional dependency mandatory and break
            # the 3.22 floor. The handler reports, so test A is satisfied.
            return self._failed(path, exc, removed=self._remove_partial(path, existed))

    def _write_xlsx(self, xlsxwriter, path):
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
        for offset, line in enumerate(self._note_lines(getattr(self, "_notes", {}) or {})):
            ws2.write(5 + offset, 0, line)
        wb.close()
        return True


__all__ = ['_BOMDialog']
