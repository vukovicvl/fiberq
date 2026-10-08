"""The bill of materials under-reported, and a failed export left a ruin.

WP4 4.2 item R4. Branch ``fix/wp4-write-paths``.

Everything the BOM could not measure was folded silently into the totals as
zero, so the report under-counted with no indication at all. Measured before the
fix, on 3.22.16, 3.44.15 and 4.0.3:

* a null or empty geometry measured 0.0 with no exception;
* a stored length of 0.0 -- the schema default -- was trusted over a real 100 m
  geometry, because the guard read ``val_len >= 0`` while the comment directly
  above it said "and >0";
* an out-of-domain geometry measured **nan**, which turned the table cell, the
  summary and the exported CSV into "nan m";
* a layer whose data source was gone dropped out of the report entirely;
* an unparseable slack value was dropped from the slack total;
* the length-column lookup kept the LAST matching field, so on a layer carrying
  both ``duzina_m`` and ``length_m`` the answer depended on column order.

And the report disagreed with the plugin. It measured with its own
``QgsDistanceArea`` seeded from the MAP CRS and the project's ellipsoid, often
``NONE``, while every length column FiberQ writes comes from
``utils.measure.ground_length``: measured, **100.0 m here against 70.93 m
there** for the same geometry. A 41% disagreement inside one report.

The writers had no error handling at all, so a read-only target, a file open in
another program or a full disk sent ``PermissionError`` out of a Qt slot and
into QGIS's blocking "Python error" dialog -- which the caller's own
``try/except`` never saw, because the dialog is modal. Worst of all,
``open(path, "w")`` **truncates before writing**: a previous 1230-byte export
became 512 bytes of half-written CSV, and the user saw only a traceback. That
half-written file is the thing this item is really about, and it has its own
test below.

Eleven of the thirteen tests below go red against a tree with only this fix
reverted. The two that do not are marked **characterisation**: the control that
keeps the new notes off a clean report, and the ordinary export, which asserts
its file's content rather than the bool the writers only answer after this fix.
"""
import os
import stat

import pytest
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.dialogs.bom_dialog import _BOMDialog
from fiberq.utils.measure import ground_length


class FakeIface:
    def messageBar(self):
        return self

    def pushWarning(self, *a):
        pass

    def pushInfo(self, *a):
        pass

    def mainWindow(self):
        return None

    def mapCanvas(self):
        return self

    def mapSettings(self):
        return self

    def destinationCrs(self):
        return QgsProject.instance().crs()


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture
def modals(monkeypatch):
    """What the dialog would have shown, by kind."""
    said = {"info": [], "critical": []}
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: said["info"].append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: said["critical"].append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    return said


def _cables(project, rows, fields=(("duzina_m", QVariant.Double),
                                   ("slack_m", QVariant.Double)), crs="EPSG:3857"):
    """A cable layer whose features are (wkt, {field: value})."""
    layer = QgsVectorLayer(f"LineString?crs={crs}", "Kablovi", "memory")
    layer.dataProvider().addAttributes([QgsField(n, t) for n, t in fields])
    layer.updateFields()
    for wkt, values in rows:
        feature = QgsFeature(layer.fields())
        if wkt is not None:
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
        for name, value in values.items():
            feature.setAttribute(name, value)
        assert layer.dataProvider().addFeatures([feature])[0]
    project.addMapLayer(layer)
    return layer


def _dialog(project):
    """A real _BOMDialog, which builds its report in __init__."""
    return _BOMDialog(FakeIface())


# ---------------------------------------------------------------------------
# the under-count
# ---------------------------------------------------------------------------

def test_one_unmeasurable_cable_does_not_turn_the_whole_report_into_nan(project):
    """nan + anything is nan, so one bad feature made every number "nan m".

    The nan case is measured, not guessed: a **geographic** CRS with a latitude
    outside the ellipsoid's domain. On 3.44.15, with ``ground_length``::

        EPSG:4326  LineString (0 0, 1 0)     ->  111319.49
        EPSG:4326  LineString (0 95, 1 96)   ->  nan
        EPSG:3857  LineString (1e9 1e9, ...) ->  0.0     (wrong, but not nan)

    ``is_finite`` is True for every one of those, which is exactly why the
    RESULT has to be checked and not only the input -- the geometry guard is
    necessary and not sufficient.
    """
    _cables(project, [
        ("LineString (0 0, 1 0)", {}),
        ("LineString (0 95, 1 96)", {}),
    ], crs="EPSG:4326")
    dialog = _dialog(project)

    total = dialog._totals["line_len"]
    assert total == total, f"the whole report is nan: {total}"  # nan != nan
    assert total > 0, f"the measurable cable was lost too: {total}"
    assert dialog._notes["unmeasured"] == 1, dialog._notes
    assert "could not be measured" in dialog.lbl_summary.text()


def test_a_cable_with_no_geometry_is_counted_not_silently_zeroed(project):
    _cables(project, [("LineString (0 0, 100 0)", {}), (None, {})])
    dialog = _dialog(project)

    assert dialog._notes["unmeasured"] == 1, dialog._notes
    assert "could not be measured" in dialog.lbl_summary.text(), dialog.lbl_summary.text()


def test_a_stored_zero_length_does_not_beat_a_real_geometry(project):
    """``duzina_m`` defaults to 0.0 in the schema. The old guard was
    ``val_len >= 0``, so the default won and a 100 m cable counted as nothing --
    while the comment directly above the guard said "and >0"."""
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 0.0})])
    dialog = _dialog(project)

    assert dialog._totals["line_len"] > 0, (
        f"a schema default of 0.0 hid a real geometry: {dialog._totals}")


def test_a_slack_value_that_cannot_be_read_is_counted(project):
    layer = _cables(project, [("LineString (0 0, 100 0)", {})],
                    fields=(("duzina_m", QVariant.Double), ("slack_m", QVariant.String)))
    layer.startEditing()
    layer.changeAttributeValue(1, layer.fields().indexFromName("slack_m"), "not a number")
    assert layer.commitChanges()

    dialog = _dialog(project)
    assert dialog._notes["unreadable_slack"] == 1, dialog._notes
    assert "could not be read" in dialog.lbl_summary.text()


def test_the_report_agrees_with_the_length_the_plugin_itself_writes(project):
    """The 41% disagreement. The BOM used its own QgsDistanceArea seeded from
    the map CRS and the project ellipsoid; every length column FiberQ writes
    comes from ``utils.measure.ground_length``. One report cannot hold two
    answers for the same geometry."""
    layer = _cables(project, [("LineString (0 0, 0 100000)", {})])
    expected = ground_length(next(layer.getFeatures()).geometry(), layer=layer)

    dialog = _dialog(project)

    assert round(dialog._totals["line_len"], 3) == round(expected, 3), (
        f"the BOM says {dialog._totals['line_len']} where the plugin says {expected}")


def test_the_canonical_length_column_wins_whatever_the_column_order(project):
    """The old loop kept the LAST matching field, so on a layer carrying both
    names the answer depended on column order."""
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 42.0, "length_m": 999.0})],
            fields=(("duzina_m", QVariant.Double), ("length_m", QVariant.Double)))
    dialog = _dialog(project)

    assert round(dialog._totals["line_len"], 1) == 42.0, (
        f"the canonical duzina_m should win: {dialog._totals}")


def test_a_report_with_nothing_to_complain_about_says_nothing(project):
    """The paired control. A note on every report is a note nobody reads."""
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0, "slack_m": 5.0})])
    dialog = _dialog(project)

    summary = dialog.lbl_summary.text()
    assert "could not" not in summary, summary
    assert "left out" not in summary, summary


# ---------------------------------------------------------------------------
# the writers
# ---------------------------------------------------------------------------

def test_a_read_only_target_is_reported_instead_of_raising(project, tmp_path, modals):
    """Measured: ``PermissionError`` out of a Qt slot, into QGIS's blocking
    "Python error" dialog, which ``open_bom_dialog``'s own try/except never
    saw because the BOM dialog is the active modal widget."""
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)

    target = tmp_path / "locked"
    target.mkdir()
    target.chmod(stat.S_IRUSR | stat.S_IXUSR)
    path = str(target / "bom.csv")
    try:
        assert dialog._export_csv(path) is False  # must not raise
    finally:
        target.chmod(stat.S_IRWXU)

    assert modals["critical"], "a failed export said nothing"
    assert not modals["info"], f"a failed export claimed success: {modals['info']}"
    assert path in modals["critical"][0], modals["critical"]


def test_a_write_that_fails_part_way_does_not_leave_a_half_written_file(
        project, tmp_path, modals, monkeypatch):
    """**The destructive half, and the reason this item matters.**

    ``open(path, "w")`` truncates before writing. Measured: a previous
    1230-byte export became 512 bytes of half-written CSV when the write failed,
    and the user saw only a traceback -- so the ruin of their last good export
    looked like a new one.
    """
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)

    path = str(tmp_path / "bom.csv")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("the user's previous export, 1230 bytes of it\n" * 30)
    before = os.path.getsize(path)
    assert before > 500

    # Fail mid-write, after open() has already truncated.
    real_writerow = None

    class Boom:
        def __init__(self, *a, **k):
            self.calls = 0

        def writerow(self, row):
            self.calls += 1
            if self.calls > 1:
                raise OSError(28, "No space left on device")

    import csv as csv_module
    monkeypatch.setattr(csv_module, "writer", lambda *a, **k: Boom())
    assert real_writerow is None

    assert dialog._export_csv(path) is False

    assert not os.path.exists(path), (
        "the half-written file is still there, looking like an export")
    assert modals["critical"], "nothing was said"
    assert "removed" in modals["critical"][0], (
        f"the user was not told the ruin was cleaned up: {modals['critical']}")
    assert not modals["info"]


def test_a_successful_csv_export_still_writes_the_whole_file(project, tmp_path, modals):
    """Characterisation, not proof: the ordinary export has to keep working.

    It asserts the file's CONTENT and not the return value on purpose. The
    writers answer a bool only after this fix, so asserting that would send this
    red against the old code for a signature change rather than for any
    behaviour -- the kind of false proof this branch has been weeding out.
    Written this way it passes before and after, which is what a
    characterisation test should do.
    """
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)

    path = str(tmp_path / "bom.csv")
    dialog._export_csv(path)
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "TOTAL" in text
    assert "Layer;Type;Number" in text


def test_the_counts_reach_the_exported_file(project, tmp_path, modals):
    """A note the user only sees on screen is a note that does not survive
    being sent to anybody."""
    _cables(project, [("LineString (0 0, 100 0)", {}), (None, {})])
    dialog = _dialog(project)

    path = str(tmp_path / "bom.csv")
    assert dialog._export_csv(path) is True
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "could not be measured" in text, text


def test_xlsx_is_not_offered_when_it_cannot_be_written(project, tmp_path, monkeypatch):
    """Two independent probes used to decide this -- one for the file filter and
    one for the writer -- so they could disagree, and when they did the user was
    offered an Excel filter and silently handed a CSV."""
    import fiberq.dialogs.bom_dialog as bom

    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)

    monkeypatch.setattr(bom, "has_xlsxwriter", lambda: False)
    offered = {}

    def fake_dialog(parent, title, start, filters):
        offered["filters"] = filters
        return "", ""

    monkeypatch.setattr(bom.QFileDialog, "getSaveFileName", staticmethod(fake_dialog))
    dialog._export()

    assert "xlsx" not in offered["filters"].lower(), (
        f"Excel was offered although it cannot be written: {offered['filters']}")


def test_an_xlsx_name_becomes_a_csv_name_not_both(project, tmp_path, monkeypatch, modals):
    """The old code appended, giving report.xlsx.csv."""
    import fiberq.dialogs.bom_dialog as bom

    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)

    monkeypatch.setattr(bom, "has_xlsxwriter", lambda: False)
    asked = str(tmp_path / "report.xlsx")
    monkeypatch.setattr(bom.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (asked, "")))
    dialog._export()

    assert os.path.exists(str(tmp_path / "report.csv")), os.listdir(str(tmp_path))
    assert not os.path.exists(asked + ".csv"), "report.xlsx.csv was written"
    assert modals["info"] and "xlsxwriter" in modals["info"][0], (
        f"the substitution was silent: {modals['info']}")
