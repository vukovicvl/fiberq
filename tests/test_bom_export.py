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

Eleven of R4's thirteen tests go red against a tree with only this fix
reverted. The two that do not are marked **characterisation**: the control that
keeps the new notes off a clean report, and the ordinary export, which asserts
its file's content rather than the bool the writers only answer after this fix.

The section at the end is v1.6.0 QA finding Q25: R4 removed the target after
any failure, so a read-only file FiberQ could not even open was deleted.
"""
import errno
import io
import os
import stat
import zipfile

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
                                   ("slack_m", QVariant.Double)), crs="EPSG:3857",
            name="Kablovi"):
    """A cable layer whose features are (wkt, {field: value})."""
    layer = QgsVectorLayer(f"LineString?crs={crs}", name, "memory")
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

def test_a_read_only_target_is_reported_instead_of_raising(
        project, tmp_path, modals, monkeypatch):
    """Measured: ``PermissionError`` out of a Qt slot, into QGIS's blocking
    "Python error" dialog, which ``open_bom_dialog``'s own try/except never
    saw because the BOM dialog is the active modal widget.

    The refusal is injected rather than created with ``chmod``, and that is not
    squeamishness: the qgis/qgis containers run as **root** in CI, root ignores
    permission bits, and the first version of this test wrote the file quite
    happily there and failed on all three legs. A test whose premise depends on
    the uid it runs under is a test that only holds where you happened to try
    it. ``tests/test_change_element_type.py`` says the same thing about a
    chmod-444 GeoPackage behaving differently on the 3.22 floor.
    """
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)

    import fiberq.dialogs.bom_dialog as bom
    path = str(tmp_path / "bom.csv")

    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setitem(bom.__dict__, "open", refuse)

    assert dialog._export_csv(path) is False  # must not raise

    assert modals["critical"], "a failed export said nothing"
    assert not modals["info"], f"a failed export claimed success: {modals['info']}"
    assert path in modals["critical"][0], modals["critical"]
    assert "Permission denied" in modals["critical"][0], (
        f"the operating system's half of the story was dropped: {modals['critical']}")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the write bit")
def test_a_read_only_target_for_real(project, tmp_path, modals):
    """The same thing without the patch, for anyone running as themselves.

    The pair is the house pattern -- see ``tests/test_gpkg_target.py``. The
    monkeypatched test above runs everywhere including CI, where the containers
    are root; this one exercises the real operating-system refusal for a
    developer running as a normal user, and skips where it would be a lie.
    """
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


def _disk_fills_half_way(monkeypatch, path):
    """Make writing to ``path`` stop half way with ENOSPC, after a real open.

    The open is real, so the target is truncated or created for real, and half
    of the first write reaches the disk before the error -- which is what a
    disk filling up does. Patched at ``builtins.open`` and ``io.open`` together,
    for ``path`` only, so it reaches whichever code opens the target:
    ``_write_file`` since Q25, the CSV writer's own ``open`` and xlsxwriter's
    ``zipfile`` (which calls ``io.open``) before it. Answers a dict that gets
    the file's size on disk at the moment of the error.
    """
    import builtins

    real_open = builtins.open
    seen = {}

    class HalfWay:
        def __init__(self, handle):
            self._handle = handle

        def __getattr__(self, name):
            return getattr(self._handle, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._handle.close()
            return False

        def write(self, data):
            if "size" not in seen:  # the disk is full from here on
                self._handle.write(data[:max(1, len(data) // 2)])
                self._handle.flush()
                seen["size"] = os.path.getsize(path)
            raise OSError(errno.ENOSPC, "No space left on device")

    def opener(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if isinstance(file, str) and file == path and any(flag in mode for flag in "wax+"):
            return HalfWay(handle)
        return handle

    monkeypatch.setattr(builtins, "open", opener)
    monkeypatch.setattr(io, "open", opener)
    return seen


def test_a_write_that_fails_part_way_does_not_leave_a_half_written_file(
        project, tmp_path, modals, monkeypatch):
    """**The destructive half, and the reason this item matters.**

    ``open(path, "w")`` truncates before writing. Measured: a previous
    1230-byte export became 512 bytes of half-written CSV when the write failed,
    and the user saw only a traceback -- so the ruin of their last good export
    looked like a new one.

    Q25 moved the failure this injects. It made ``csv.writer`` raise on its
    second row, but the CSV is now put together in memory and written in one
    call, so a failure there never reaches the target (the Q25 tests at the end
    of this file). A full disk now surfaces in the file's own write, after the
    open has truncated the target, and that is where it is made to fail.
    """
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)

    path = str(tmp_path / "bom.csv")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("the user's previous export, 1230 bytes of it\n" * 30)
    before = os.path.getsize(path)
    assert before > 500

    # Fail mid-write, after open() has already truncated.
    on_disk = _disk_fills_half_way(monkeypatch, path)

    assert dialog._export_csv(path) is False

    assert 0 < on_disk["size"] < before, f"not truncated and half-written: {on_disk}"
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


# ---------------------------------------------------------------------------
# v1.6.0 QA, Q25: a failed export leaves alone a file FiberQ could not open
# ---------------------------------------------------------------------------
#
# QA step E.5, on 4.2.3: the maintainer made an existing 68-byte BOM export
# read-only (chmod a-w), then BOM report > Export > that file > Replace. FiberQ
# said it could not write the file, "and the half-written file has been removed
# so it cannot be mistaken for a finished export. Reason: PermissionError:
# [Errno 13] Permission denied", and the file was gone. Nothing had been
# half-written: open() was refused before it truncated anything, and R4's
# clean-up removed the target after any failure at all.
#
# Both exports are now put together in memory and written by _write_file, the
# one place that touches the target. A refused open leaves the file as it was
# -- the same bytes, permissions and inode -- with the plain message; only a
# write that fails after FiberQ's own open removes what it half-wrote. The
# chmod tests need a process the write bit stops, which root is not: they skip
# there, and the injected refusal covers the same path. The XLSX cases need
# xlsxwriter, which none of the qgis/qgis images ships: they skip without it.

#: What the export wrote for ``_ordinary_project`` before Q25, byte for byte,
#: measured on 4.2.3: UTF-8 with no byte-order mark, CRLF, ";" between fields.
_CSV_BEFORE_Q25 = (
    b"Layer;Type;Number;Length_m;Slack_m;Total_m\r\n"
    b"A kablovi \xc5\xa0abac;Line;3;350.5;7.25;357.75\r\n"
    b"B stubovi;Point;3;;;\r\n"
    b"\r\n"
    b"TOTAL;;3;350.5;7.25;357.75\r\n"
    b"Features whose length could not be measured (counted, not included): 1\r\n")

#: A previous export to be left alone: an empty project's BOM, 68 bytes, the
#: size of the file in E.5.
_PREVIOUS = b"Layer;Type;Number;Length_m;Slack_m;Total_m\r\n\r\nTOTAL;;0;0.0;0.0;0.0\r\n"


def _need_xlsxwriter():
    from fiberq.utils.compat import has_xlsxwriter
    if not has_xlsxwriter():
        pytest.skip("xlsxwriter is not installed in this QGIS: it is optional, none of the "
                    "qgis/qgis images ships it, and without it FiberQ offers CSV only")


def _ordinary_project(project):
    """A cable layer with a name that is not ASCII and one feature it cannot
    measure, and a point layer: every kind of row and the note, in a known order."""
    _cables(project, [
        ("LineString (0 0, 100 0)", {"duzina_m": 100.0, "slack_m": 5.0}),
        ("LineString (0 0, 0 250)", {"duzina_m": 250.5, "slack_m": 2.25}),
        (None, {}),
    ], name="A kablovi Šabac")
    points = QgsVectorLayer("Point?crs=EPSG:3857", "B stubovi", "memory")
    for x in range(3):
        feature = QgsFeature(points.fields())
        feature.setGeometry(QgsGeometry.fromWkt(f"Point ({x} 0)"))
        assert points.dataProvider().addFeatures([feature])[0]
    project.addMapLayer(points)


def _file_state(path):
    """What "left alone" means: the same bytes, the same permission bits, and
    the same file -- not a new one written in its place."""
    info = os.stat(path)
    with open(path, "rb") as fh:
        data = fh.read()
    return {"bytes": data, "mode": oct(stat.S_IMODE(info.st_mode)), "inode": info.st_ino,
            "mtime_ns": info.st_mtime_ns}


def _make_read_only(path):
    """``chmod a-w``, as in E.5 -- or skip where that does not stop this process."""
    mode = stat.S_IMODE(os.stat(path).st_mode)
    os.chmod(path, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    if os.access(path, os.W_OK):
        pytest.skip("this process can write to a file without write bits (root can), so a "
                    "read-only target cannot be made here; the injected refusal covers it")


def _export_through_the_button(dialog, monkeypatch, path, xlsx):
    """BOM report > Export, the save dialog answering ``path``. By then the
    dialog has asked "Replace?" about an existing file and been told yes."""
    import fiberq.dialogs.bom_dialog as bom
    monkeypatch.setattr(bom, "has_xlsxwriter", lambda: xlsx)
    monkeypatch.setattr(bom.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (path, "")))
    dialog._export()


def _said_could_not_write(modals, path, reason):
    """The plain message: the path, the operating system's reason, and no
    claim that anything was removed."""
    assert not modals["info"], f"a failed export claimed success: {modals['info']}"
    assert len(modals["critical"]) == 1, modals["critical"]
    text = modals["critical"][0]
    assert "removed" not in text, f"the message says a file was removed: {text}"
    assert text.startswith(f"Could not write the bill of materials to {path}. Reason: "), text
    assert reason in text, text


def _xlsx_cells(path):
    """Every cell of every sheet as {sheet: {"A1": value}}, the shared strings
    resolved: enough to read a BOM workbook back without openpyxl."""
    import xml.etree.ElementTree as ET

    main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as book:
        assert book.testzip() is None
        shared = [si.findtext(main + "t")
                  for si in ET.fromstring(book.read("xl/sharedStrings.xml")).iter(main + "si")]
        names = [sheet.get("name")
                 for sheet in ET.fromstring(book.read("xl/workbook.xml")).iter(main + "sheet")]
        cells = {}
        for number, name in enumerate(names, start=1):
            sheet = ET.fromstring(book.read(f"xl/worksheets/sheet{number}.xml"))
            cells[name] = {
                c.get("r"): (shared[int(c.findtext(main + "v"))] if c.get("t") == "s"
                             else float(c.findtext(main + "v")))
                for c in sheet.iter(main + "c")}
    return cells


def test_a_refused_open_leaves_the_file_as_it_was(project, tmp_path, modals, monkeypatch):
    """The operating system refuses the open -- injected, so this holds for
    root and in CI as well. Before Q25 the file, which nothing had touched, was
    removed, and the message said a half-written file had been."""
    import fiberq.dialogs.bom_dialog as bom

    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)
    path = str(tmp_path / "qa16-bom.csv")
    with open(path, "wb") as fh:
        fh.write(_PREVIOUS)
    before = _file_state(path)

    def refuse(file, mode="r", *args, **kwargs):
        if file == path and any(flag in mode for flag in "wax+"):
            raise PermissionError(errno.EACCES, "Permission denied", path)
        return open(file, mode, *args, **kwargs)

    monkeypatch.setitem(bom.__dict__, "open", refuse)
    assert dialog._export_csv(path) is False

    assert os.path.exists(path), "FiberQ removed the file it could not open"
    assert _file_state(path) == before, "FiberQ changed the file it could not open"
    _said_could_not_write(modals, path, "PermissionError: [Errno 13] Permission denied")


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_e5_a_read_only_export_is_still_there_after_the_failed_export(
        project, tmp_path, modals, monkeypatch, suffix):
    """E.5 as the maintainer did it on 4.2.3, with nothing patched between
    FiberQ and the operating system: an export, ``chmod a-w`` on it, then
    Export > that file > Replace. ``ls -l`` showed ``-r--r--r--`` and 68 bytes
    before; afterwards there was no file. XLSX went the same way: xlsxwriter
    could not open the file either, and it was removed."""
    xlsx = suffix == ".xlsx"
    if xlsx:
        _need_xlsxwriter()
    dialog = _dialog(project)
    path = str(tmp_path / f"qa16-bom{suffix}")
    _export_through_the_button(dialog, monkeypatch, path, xlsx)
    assert modals["info"] and not modals["critical"], f"the first export failed: {modals}"
    modals["info"].clear()
    _make_read_only(path)
    before = _file_state(path)

    _export_through_the_button(dialog, monkeypatch, path, xlsx)

    assert os.path.exists(path), "FiberQ deleted the read-only file it could not write"
    assert _file_state(path) == before, "FiberQ changed the read-only file it could not write"
    _said_could_not_write(modals, path, "PermissionError: [Errno 13] Permission denied")


def test_a_folder_in_the_way_is_left_alone(project, tmp_path, modals, monkeypatch):
    """A folder where the export would go. ``open()`` refuses it, and before
    Q25 FiberQ then called ``os.remove`` on it: only the operating system's
    refusal to unlink a folder (IsADirectoryError, measured on 4.2.3) kept it.
    Nothing may even try."""
    dialog = _dialog(project)
    path = tmp_path / "bom.csv"
    path.mkdir()
    (path / "keep.txt").write_text("inside", encoding="utf-8")
    tried = []

    def spy(real):
        def call(target, *args, **kwargs):
            tried.append(os.fspath(target))
            return real(target, *args, **kwargs)
        return call

    for name in ("remove", "unlink", "rmdir"):
        monkeypatch.setattr(os, name, spy(getattr(os, name)))

    assert dialog._export_csv(str(path)) is False

    assert tried == [], f"FiberQ tried to delete what it could not write to: {tried}"
    assert path.is_dir() and (path / "keep.txt").read_text(encoding="utf-8") == "inside"
    _said_could_not_write(modals, str(path), "IsADirectoryError")


def test_a_folder_that_is_not_there_is_reported_not_made(project, tmp_path, modals):
    """**Characterisation**: this one was right before Q25 too, as there was
    nothing to remove. The open is refused, the reason is given, and nothing
    appears -- no file and no folder."""
    dialog = _dialog(project)
    path = tmp_path / "not there" / "bom.csv"

    assert dialog._export_csv(str(path)) is False

    assert os.listdir(str(tmp_path)) == [], "the failed export left something behind"
    _said_could_not_write(modals, str(path), "FileNotFoundError")


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_a_name_that_cannot_be_written_leaves_the_previous_export_alone(
        project, tmp_path, modals, suffix):
    """A layer name UTF-8 cannot hold -- a lone surrogate, which is what Python
    makes of an undecodable byte in a file name; QGIS keeps it in the layer's
    name. Now that fails while the export is put together in memory, before
    the target is opened. Before Q25 the target was opened first, so the
    previous export was truncated and then removed, for a reason that had
    nothing to do with the disk."""
    if suffix == ".xlsx":
        _need_xlsxwriter()
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})], name="Kablovi \udcff")
    dialog = _dialog(project)
    path = str(tmp_path / f"bom{suffix}")
    with open(path, "wb") as fh:
        fh.write(_PREVIOUS)
    before = _file_state(path)

    export = dialog._export_xlsx if suffix == ".xlsx" else dialog._export_csv
    assert export(path) is False

    assert os.path.exists(path), "the previous export was removed"
    assert _file_state(path) == before, "the previous export was changed"
    _said_could_not_write(modals, path, "UnicodeEncodeError")


def test_an_xlsx_write_that_fails_part_way_is_removed_too(project, tmp_path, modals, monkeypatch):
    """**Characterisation** of R4's half for the workbook, which kept working:
    FiberQ's own open, then a full disk part way. The workbook's bytes now go
    through the same ``_write_file`` as the CSV's."""
    _need_xlsxwriter()
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)
    path = str(tmp_path / "bom.xlsx")
    with open(path, "wb") as fh:
        fh.write(_PREVIOUS)
    on_disk = _disk_fills_half_way(monkeypatch, path)

    assert dialog._export_xlsx(path) is False

    assert on_disk.get("size", 0) > 0, f"nothing was half-written: {on_disk}"
    assert not os.path.exists(path), "the half-written workbook is still there"
    assert len(modals["critical"]) == 1 and not modals["info"], modals
    assert "removed" in modals["critical"][0], modals["critical"]
    assert "No space left on device" in modals["critical"][0], modals["critical"]


def test_a_full_disk_for_real(project, tmp_path, modals):
    """**Characterisation**, and the injected test's twin with nothing patched.

    ``/dev/full`` takes the open and refuses every write with ENOSPC, as a full
    disk does. For an export this small the refusal comes when the buffer is
    flushed at close(), not at write(), so this is what shows the close is
    inside the handler too. It is reached through a link in ``tmp_path``: what
    is removed is the link -- ``os.remove`` does not follow links -- and never
    ``/dev/full``."""
    full = "/dev/full"
    try:
        with open(full, "wb") as fh:
            fh.write(b"x")
    except OSError as exc:
        if exc.errno != errno.ENOSPC:
            pytest.skip(f"{full} is not a full disk here: {exc}")
    else:
        pytest.skip(f"{full} took a write here")
    _cables(project, [("LineString (0 0, 100 0)", {"duzina_m": 100.0})])
    dialog = _dialog(project)
    link = tmp_path / "bom.csv"
    link.symlink_to(full)

    assert dialog._export_csv(str(link)) is False

    assert not os.path.lexists(str(link)), "the export that did not fit is still there"
    assert os.path.exists(full)
    assert len(modals["critical"]) == 1 and not modals["info"], modals
    assert "removed" in modals["critical"][0], modals["critical"]
    assert "No space left on device" in modals["critical"][0], modals["critical"]


def test_an_ordinary_csv_export_is_byte_for_byte_what_it_was(project, tmp_path, modals):
    """**Characterisation**: putting the file together in memory first changes
    nothing in it."""
    _ordinary_project(project)
    dialog = _dialog(project)
    path = tmp_path / "bom.csv"

    assert dialog._export_csv(str(path)) is True

    assert path.read_bytes() == _CSV_BEFORE_Q25


def test_an_ordinary_xlsx_export_holds_the_same_cells(project, tmp_path, modals):
    """**Characterisation**: the workbook built in memory holds what the one
    xlsxwriter wrote straight to the file did."""
    _need_xlsxwriter()
    _ordinary_project(project)
    dialog = _dialog(project)
    path = tmp_path / "bom.xlsx"

    assert dialog._export_xlsx(str(path)) is True

    assert _xlsx_cells(str(path)) == {
        "By layers": {
            "A1": "Layer", "B1": "Type", "C1": "Number",
            "D1": "Length_m", "E1": "Slack_m", "F1": "Total_m",
            "A2": "A kablovi Šabac", "B2": "Line", "C2": 3.0,
            "D2": 350.5, "E2": 7.25, "F2": 357.75,
            "A3": "B stubovi", "B3": "Point", "C3": 3.0,
        },
        "Total": {
            "A1": "Total length of lines [m]", "B1": 350.5,
            "A2": "Total slack [m]", "B2": 7.25,
            "A3": "Line + slack [m]", "B3": 357.75,
            "A4": "Total number of point elements", "B4": 3.0,
            "A6": "Features whose length could not be measured (counted, not included): 1",
        },
    }
