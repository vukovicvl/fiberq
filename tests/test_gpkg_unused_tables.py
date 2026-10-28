"""Save all asks before it writes over, or beside, tables no layer uses (v1.6.0 QA Q18).

After a QGIS restart the maintainer made layers called Poles, Manholes and
Scratch A again and ran "Save all layers to GeoPackage" into fu8.gpkg, which
still held the first session's tables of those names, read by no layer of the
project. The native file dialog asked "already exists, replace?" and they
clicked Replace. But FiberQ never replaces the file, and since 5721d15 (WP4
U6) it never writes over a table another layer might own: it kept the old
tables and stored the layers as Poles_2, Manholes_2 and Scratch_A_2, with a
green "All layers saved". Anything reading the file by table name -- QGIS's Add
Layer, FiberQ Designer -- got the old Poles.

Now the file dialog asks nothing (DontConfirmOverwrite: the file is never
replaced), and FiberQ asks its own question about exactly those tables:
Replace them, Keep them (beside them as _2, the 5721d15 behaviour), or Cancel.
A table some layer of the project reads is never offered. Whatever the answer,
a key another tool stored in _fiberq_metadata stays (QA D.6-D.8).

The second round (three reviews of the first): the question says "No layer of
this project uses them" above a default Replace, so the plan must never be
wrong in the unsafe direction -- a layer reading the file through a symlink or a
hard link, a layer whose file is not there, a layer reading a view, a tiles
table, a file that cannot be read: each counts as used, or stops the save. A
replaced table's old styles go only once its write is in, and a write that
fails part-way says what is left of the old table. And the message bar shows
one line per item: the green success is one line, and what else a save has to
say is a line of its own that stays.

The third round: enumerating readers did not end, so a table is offered only
when the file, the table and every layer of the project are understood, by
an allow-list; and nothing is written when the file or the project changed
while the question was open, while auto-save's own hook waits for the save.
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest
from qgis.core import (
    Qgis,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QMessageBox

from fiberq.core import export_manager
from fiberq.core.export_manager import ExportManager

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for the child process. The suite has no timeout plugin.
TIMEOUT_S = 120

#: The first session's layers and how many features each had.
SESSION_ONE = (("Poles", 3), ("Manholes", 2), ("Scratch A", 2), ("Unrelated", 1))

#: What the second session made again: the same names, one feature each.
SESSION_TWO = ("Poles", "Manholes", "Scratch A")

#: Where those land in the file.
REDO_TABLES = {"Poles", "Manholes", "Scratch_A"}


class FakeBar:
    def __init__(self):
        self.warnings = []
        self.successes = []
        self.infos = []
        #: What pushMessage was given: ``(text, level, duration)``.
        self.notes = []
        #: Every push, in the order made: ``(method, title, text)``.
        self.pushed = []

    def pushWarning(self, title, text):
        self.warnings.append(text)
        self.pushed.append(("pushWarning", title, text))

    def pushSuccess(self, title, text):
        self.successes.append(text)
        self.pushed.append(("pushSuccess", title, text))

    def pushCritical(self, title, text):
        self.warnings.append(text)
        self.pushed.append(("pushCritical", title, text))

    def pushInfo(self, title, text):
        self.infos.append(text)
        self.pushed.append(("pushInfo", title, text))

    def pushMessage(self, title, text, level=None, duration=-1):
        self.notes.append((text, level, duration))
        self.pushed.append(("pushMessage", title, text))


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


class FakeAction:
    def __init__(self, checked, text=None):
        self.checked = checked
        if text is not None:
            self.text = lambda: text

    def isChecked(self):
        return self.checked


class FakePlugin:
    def __init__(self, auto_save_on, save_text=None):
        self.action_auto_gpkg = FakeAction(auto_save_on)
        if save_text is not None:
            self.action_save_gpkg = FakeAction(False, save_text)


#: The project entries a save may write: the two GeoPackage keys and the
#: schema stamp the metadata write puts in the project.
ENTRIES = (("FiberQPlugin", "gpkg_path"), ("TelecomPlugin", "gpkg_path"),
           ("FiberQPlugin", "schema/schema_version"))


@pytest.fixture
def iface():
    return FakeIface()


@pytest.fixture
def project():
    """The real QgsProject, emptied of layers and of the entries a save writes."""
    def wipe(instance):
        instance.removeAllMapLayers()
        for scope, key in ENTRIES:
            instance.removeEntry(scope, key)

    instance = QgsProject.instance()
    wipe(instance)
    yield instance
    wipe(instance)


@pytest.fixture
def modals():
    """Every modal dialog that opens, closed and recorded instead of waited on.

    QGIS 3.22's saveStyleToDatabase asks "A style named "default" already
    exists ... overwrite it?" in a modal QMessageBox when it meets an existing
    default style. Headless, nothing would ever answer it; this answers No and
    keeps the title and text, so such a test fails instead of hanging.
    """
    seen = []

    def close():
        widget = QApplication.activeModalWidget()
        if widget is None:
            return
        seen.append((widget.windowTitle(), widget.text() if hasattr(widget, "text") else ""))
        no = widget.button(QMessageBox.StandardButton.No) if isinstance(widget, QMessageBox) else None
        if no is not None:
            no.click()
        else:
            widget.reject()

    timer = QTimer()
    timer.timeout.connect(close)
    timer.start(50)
    yield seen
    timer.stop()


@pytest.fixture
def answer(monkeypatch):
    """FiberQ's own question, answered with ``answer.reply`` and recorded."""
    class Answer:
        reply = None
        asked = []

        def __call__(self, parent, title, gpkg_path, plan):
            self.asked.append({"title": title, "path": gpkg_path,
                               "offered": list(plan.offered),
                               "kept_as": [plan.tables[index] for index in sorted(plan.offers)]})
            return self.reply

    recorder = Answer()
    recorder.asked = []
    # raising=False: the function is this change's; before it, nothing asked.
    monkeypatch.setattr(export_manager, "ask_about_unused_tables", recorder, raising=False)
    return recorder


@pytest.fixture
def logged(monkeypatch):
    """What a save writes to FiberQ's own tab of QGIS's log: ``(text, tag, level)``."""
    lines = []

    class Log:
        @staticmethod
        def logMessage(text, tag="", level=None):
            lines.append((text, tag, level))

    # raising=False: before this change the module wrote nothing there.
    monkeypatch.setattr(export_manager, "QgsMessageLog", Log, raising=False)
    return lines


@pytest.fixture
def save_to(monkeypatch):
    """Answer the file dialog with a path, run Save all, and keep what the dialog was given."""
    calls = []

    def run(manager, target):
        def dialog(*args, **kwargs):
            calls.append((args, kwargs))
            return str(target), ""
        monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(dialog))
        manager.save_all_layers_to_gpkg()

    run.calls = calls
    return run


def _memory_layer(name, count=1):
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer", name, "memory")
    assert layer.isValid()
    layer.startEditing()
    for number in range(count):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(number, number)))
        feature.setAttribute("id", number)
        layer.addFeature(feature)
    assert layer.commitChanges()
    return layer


def _session_one(project, target, save_to, layers=SESSION_ONE):
    """What the first session left: Save all's tables and styles, an extra
    named style on Poles, and a key another tool put in _fiberq_metadata (QA
    D.6). Then the "restart": every layer gone, the file closed."""
    for name, count in layers:
        project.addMapLayer(_memory_layer(name, count))
    first = FakeIface()
    save_to(ExportManager(first), target)
    assert first.bar.warnings == [] and len(first.bar.successes) == 1, first.bar.__dict__
    project.removeAllMapLayers()
    for scope, key in ENTRIES:
        project.removeEntry(scope, key)
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute(
            "INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
            "styleName, styleQML, styleSLD, useAsDefault, description, owner, ui) "
            "VALUES ('', '', 'Poles', 'geom', 'printing', '<qgis/>', '', 0, 'session one', '', '')")
        conn.execute("INSERT OR REPLACE INTO _fiberq_metadata VALUES ('other_tool_state', 'kept')")
        conn.commit()


def _session_two(project, names=SESSION_TWO):
    layers = [_memory_layer(name, 1) for name in names]
    for layer in layers:
        project.addMapLayer(layer)
    return layers


def _feature_tables(path):
    """``{table: feature count}`` of the file's feature tables."""
    with closing(sqlite3.connect(str(path))) as conn:
        names = [row[0] for row in conn.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'")]
        return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}


def _styles(path, table):
    with closing(sqlite3.connect(str(path))) as conn:
        return sorted(row[0] for row in conn.execute(
            "SELECT styleName FROM layer_styles WHERE lower(f_table_name) = lower(?)", (table,)))


def _metadata(path):
    with closing(sqlite3.connect(str(path))) as conn:
        return dict(conn.execute("SELECT key, value FROM _fiberq_metadata"))


def _sha(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _entries(project):
    return {(scope, key): tuple(project.readEntry(scope, key, "")) for scope, key in ENTRIES}


# ---------------------------------------------------------------------------
# the maintainer's redo, one test per answer
# ---------------------------------------------------------------------------

def test_replace_writes_the_layers_over_the_unused_tables(
        iface, project, save_to, answer, modals, logged, tmp_path):
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to)
    layers = _session_two(project)
    answer.reply = getattr(export_manager, "REPLACE", "replace")

    save_to(ExportManager(iface), target)

    assert len(answer.asked) == 1, "FiberQ must ask, once"
    assert answer.asked[0]["title"] == "Save all layers to GeoPackage"
    assert sorted(answer.asked[0]["offered"]) == sorted(REDO_TABLES)
    assert _feature_tables(target) == {"Poles": 1, "Manholes": 1, "Scratch_A": 1, "Unrelated": 1}, (
        "one table per name, holding this project's features, and the unrelated table untouched")
    for table in REDO_TABLES:
        assert _styles(target, table) == ["default"], f"{table}: the old styles must go with the old table"
    assert _styles(target, "Unrelated") == ["default"]
    assert _metadata(target)["other_tool_state"] == "kept"
    for layer in layers:
        table = "Scratch_A" if layer.name() == "Scratch A" else layer.name()
        assert layer.source() == f"{target}|layername={table}"
    assert iface.bar.warnings == []
    assert len(iface.bar.successes) == 1
    success = iface.bar.successes[0]
    assert success.startswith("All layers saved to fu8.gpkg. The old tables "), success
    assert success.endswith(" were replaced.")
    assert all(table in success for table in REDO_TABLES)
    assert "\n" not in success and len(success) <= 100, "one line, the message bar shows no more"
    assert iface.bar.notes == []
    assert logged[-1] == (f"All layers saved to {target}. " + success[len("All layers saved to fu8.gpkg. "):],
                          "FiberQ", Qgis.MessageLevel.Info), "the whole path goes to the FiberQ log"
    assert modals == [], "QGIS asked about a style"


def test_keep_saves_the_layers_beside_them_and_says_where(iface, project, save_to, answer, modals, logged, tmp_path):
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to)
    layers = _session_two(project)
    answer.reply = getattr(export_manager, "KEEP", "keep")

    save_to(ExportManager(iface), target)

    assert len(answer.asked) == 1
    assert sorted(answer.asked[0]["kept_as"]) == ["Manholes_2", "Poles_2", "Scratch_A_2"]
    assert _feature_tables(target) == {
        "Poles": 3, "Manholes": 2, "Scratch_A": 2, "Unrelated": 1,
        "Poles_2": 1, "Manholes_2": 1, "Scratch_A_2": 1}
    assert _styles(target, "Poles") == ["default", "printing"], "kept tables keep their styles"
    assert _styles(target, "Poles_2") == ["default"]
    assert _metadata(target)["other_tool_state"] == "kept"
    assert {layer.source() for layer in layers} == {
        f"{target}|layername={table}" for table in ("Poles_2", "Manholes_2", "Scratch_A_2")}
    assert iface.bar.warnings == []
    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]
    (note, level, duration), = iface.bar.notes
    assert note.startswith("Saved next to tables of the same names: "), note
    for pair in ("Poles → Poles_2", "Manholes → Manholes_2", "Scratch A → Scratch_A_2"):
        assert pair in note, note
    assert (level, duration) == (Qgis.MessageLevel.Info, 0), "a line of its own that stays until closed"
    assert [push[0] for push in iface.bar.pushed] == ["pushMessage", "pushSuccess"], (
        "the bar shows its newest item first: the success is read first, the note stays after it")
    assert logged[-1][0].startswith(f"All layers saved to {target}. Saved next to tables of the same names: ")
    assert all(pair in logged[-1][0] for pair in ("Poles → Poles_2", "Manholes → Manholes_2", "Scratch A → Scratch_A_2"))
    assert modals == []


def test_cancel_changes_nothing(iface, project, save_to, answer, modals, tmp_path):
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to)
    layers = _session_two(project)
    layers[0].startEditing()
    pending = QgsFeature(layers[0].fields())
    pending.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(9, 9)))
    layers[0].addFeature(pending)
    project.setDirty(False)
    before = (_sha(target), os.path.exists(f"{target}-wal"), _entries(project),
              [layer.source() for layer in layers])
    answer.reply = None

    save_to(ExportManager(iface), target)

    assert len(answer.asked) == 1, "the test must reach the question to test its Cancel"
    after = (_sha(target), os.path.exists(f"{target}-wal"), _entries(project),
             [layer.source() for layer in layers])
    assert after == before, "Cancel wrote something"
    assert layers[0].isEditable(), "Cancel committed the pending edit"
    assert not project.isDirty()
    assert iface.bar.successes == [] and iface.bar.warnings == [] and iface.bar.infos == []
    assert _metadata(target)["other_tool_state"] == "kept"
    layers[0].rollBack()


def test_a_replace_that_fails_leaves_the_layers_where_they_were(iface, project, save_to, answer, modals, tmp_path):
    """The old styles go once the table is written; a file that refuses that is
    the layer's failure: it is not repointed, the bar is not green, and the
    message says what is true -- the table holds the layer now, and the layer
    still reads its old source -- unlike "the style was not saved", which
    leaves the layer saved. Nothing asks about a style either: the layer's own
    style is not saved over the old ones (review n18)."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to)
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("CREATE TRIGGER keep_styles BEFORE DELETE ON layer_styles "
                     "BEGIN SELECT RAISE(ABORT, 'styles are kept here'); END;")
        conn.commit()
    layers = _session_two(project)
    answer.reply = getattr(export_manager, "REPLACE", "replace")

    save_to(ExportManager(iface), target)

    assert len(answer.asked) == 1
    assert iface.bar.successes == [], "a failed replace must not end in green"
    assert len(iface.bar.warnings) == 1, iface.bar.warnings
    assert (" now holds this layer, but the layer still reads its old source: the table's old styles could "
            "not be removed (IntegrityError: styles are kept here) (+2 more).") in iface.bar.warnings[0], (
        iface.bar.warnings)
    assert "(+2 more)" in iface.bar.warnings[0], "each of the three layers failed"
    assert [layer.dataProvider().name() for layer in layers] == ["memory"] * 3, "a layer was repointed"
    assert _styles(target, "Poles") == ["default", "printing"]
    assert _metadata(target)["other_tool_state"] == "kept"
    assert modals == []


# ---------------------------------------------------------------------------
# when nothing is asked
# ---------------------------------------------------------------------------

def test_a_table_a_layer_still_reads_is_never_offered(iface, project, save_to, answer, modals, tmp_path):
    """U6's case: "Poles 2024" still reads the table Poles; a new Poles goes beside it."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    renamed = QgsVectorLayer(f"{target}|layername=Poles", "Poles 2024", "ogr")
    assert renamed.isValid()
    project.addMapLayer(renamed)
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = getattr(export_manager, "REPLACE", "replace")

    save_to(ExportManager(iface), target)

    assert answer.asked == [], "a table a layer reads must never be offered"
    assert _feature_tables(target) == {"Poles": 3, "Poles_2": 1}
    assert renamed.source() == f"{target}|layername=Poles"
    assert fresh.source() == f"{target}|layername=Poles_2"
    assert iface.bar.warnings == []
    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]
    assert iface.bar.notes == [("Saved next to a table of the same name: Poles → Poles_2.",
                                Qgis.MessageLevel.Info, 0)]


def test_a_table_a_raster_layer_reads_is_never_offered(iface, project, save_to, answer, tmp_path):
    """Any kind of layer reads a table: here a raster, through GDAL's "GPKG:<path>:<table>"."""
    from osgeo import gdal
    from qgis.core import QgsRasterLayer

    target = tmp_path / "fu8.gpkg"
    raster = gdal.GetDriverByName("GPKG").Create(str(target), 4, 4, 1, gdal.GDT_Byte,
                                                 options=["RASTER_TABLE=Poles"])
    raster.SetGeoTransform([0, 1, 0, 4, 0, -1])
    raster.GetRasterBand(1).Fill(7)
    raster = None
    reader = QgsRasterLayer(f"GPKG:{target}:Poles", "Poles photo", "gdal")
    assert reader.isValid()
    project.addMapLayer(reader)
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = getattr(export_manager, "REPLACE", "replace")

    save_to(ExportManager(iface), target)

    assert answer.asked == [], "a table a raster layer reads must never be offered"
    with closing(sqlite3.connect(str(target))) as conn:
        assert conn.execute("SELECT data_type FROM gpkg_contents WHERE table_name = 'Poles'").fetchall() == [
            ("tiles",)]
    assert fresh.source() == f"{target}|layername=Poles_2"
    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]
    assert [note for note, _level, _duration in iface.bar.notes] == [
        "Saved next to a table of the same name: Poles → Poles_2."]


def test_saving_again_into_the_layers_own_file_asks_nothing(iface, project, save_to, answer, tmp_path):
    for name in SESSION_TWO:
        project.addMapLayer(_memory_layer(name, 1))
    target = tmp_path / "fu8.gpkg"
    save_to(ExportManager(iface), target)
    before = _feature_tables(target)

    save_to(ExportManager(iface), target)

    assert answer.asked == []
    assert _feature_tables(target) == before
    assert iface.bar.successes == ["All layers saved to fu8.gpkg."] * 2
    assert iface.bar.notes == []


def test_a_new_file_asks_nothing(iface, project, save_to, answer, tmp_path):
    for name in SESSION_TWO:
        project.addMapLayer(_memory_layer(name, 1))
    target = tmp_path / "new.gpkg"

    save_to(ExportManager(iface), target)

    assert answer.asked == []
    assert REDO_TABLES <= set(_feature_tables(target))
    assert iface.bar.successes == ["All layers saved to new.gpkg."]


# ---------------------------------------------------------------------------
# the file dialog, and what the message says about auto-save
# ---------------------------------------------------------------------------

def test_the_file_dialog_does_not_ask_to_replace(iface, project, save_to, tmp_path):
    """FiberQ writes into the file and never replaces it, so the native
    "already exists, replace?" misdescribes the save."""
    project.addMapLayer(_memory_layer("Poles"))

    save_to(ExportManager(iface), tmp_path / "out.gpkg")

    no_confirm = getattr(getattr(QFileDialog, "Option", QFileDialog), "DontConfirmOverwrite")
    args, kwargs = save_to.calls[0]
    options = args[5] if len(args) > 5 else kwargs.get("options")
    assert options is not None, f"no options passed to the file dialog: {args}"
    assert options == no_confirm


def test_a_save_that_moves_auto_save_says_so(iface, project, save_to, tmp_path):
    """Save all stores its file as the project's GeoPackage (5721d15), which is
    where auto-save writes new layers; moved silently, they went elsewhere. Said
    on a line of its own, which stays until closed."""
    project.writeEntry("FiberQPlugin", "gpkg_path", str(tmp_path / "fu4.gpkg"))
    project.writeEntry("TelecomPlugin", "gpkg_path", str(tmp_path / "fu4.gpkg"))
    project.addMapLayer(_memory_layer("Poles"))
    target = tmp_path / "fu8.gpkg"

    save_to(ExportManager(iface, FakePlugin(auto_save_on=True)), target)

    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]
    assert iface.bar.notes == [("Auto-save now writes to fu8.gpkg.", Qgis.MessageLevel.Info, 0)]
    assert project.readEntry("FiberQPlugin", "gpkg_path", "")[0] == str(target)


def test_a_save_that_leaves_auto_save_where_it_was_says_nothing_of_it(iface, project, save_to, tmp_path):
    target = tmp_path / "fu8.gpkg"
    project.writeEntry("FiberQPlugin", "gpkg_path", str(target))
    project.addMapLayer(_memory_layer("Poles"))

    save_to(ExportManager(iface, FakePlugin(auto_save_on=True)), target)

    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]
    assert iface.bar.notes == []


def test_auto_save_off_is_not_mentioned(iface, project, save_to, tmp_path):
    project.writeEntry("FiberQPlugin", "gpkg_path", str(tmp_path / "fu4.gpkg"))
    project.addMapLayer(_memory_layer("Poles"))
    target = tmp_path / "fu8.gpkg"

    save_to(ExportManager(iface, FakePlugin(auto_save_on=False)), target)

    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]
    assert iface.bar.notes == []


# ---------------------------------------------------------------------------
# the question itself
# ---------------------------------------------------------------------------

def _keep_plan(tmp_path, tables, layers):
    from fiberq.core.gpkg_target import plan_tables
    path = tmp_path / "fu8.gpkg"
    for table in tables:
        source = _memory_layer(table)
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = table
        options.actionOnExistingFile = (
            QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer if path.exists()
            else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile)
        assert QgsVectorFileWriter.writeAsVectorFormatV3(
            source, str(path), QgsCoordinateTransformContext(), options)[0] == 0
    return path, plan_tables([(name, "Point?crs=EPSG:3857", "layer") for name in layers], str(path), set())


def test_the_question_names_the_tables_and_what_each_answer_does(tmp_path):
    path, plan = _keep_plan(tmp_path, ["Poles", "Manholes", "Scratch_A"], ["Poles", "Manholes", "Scratch A"])

    box, replace, keep = export_manager.unused_tables_question(None, "Save all layers to GeoPackage", str(path), plan)

    assert box.windowTitle() == "Save all layers to GeoPackage"
    assert box.text() == ("fu8.gpkg already has tables named Poles, Manholes, Scratch_A. "
                          "No layer of this project uses them.")
    assert box.informativeText() == (
        "Replace them: the tables are overwritten with this project's layers, and their old "
        "features and styles are gone.\n"
        "Keep them: this project's layers are saved next to them, as Poles_2, Manholes_2, Scratch_A_2.\n"
        "Either way, the file's other tables stay as they are, and so does anything other "
        "programs stored in it.")
    assert [replace.text(), keep.text()] == ["Replace them", "Keep them"]
    assert box.defaultButton() is replace
    assert box.escapeButton() is box.button(QMessageBox.StandardButton.Cancel)
    assert len(box.buttons()) == 3


def test_the_question_about_one_table(tmp_path):
    path, plan = _keep_plan(tmp_path, ["Scratch_A"], ["Scratch A"])

    box, replace, keep = export_manager.unused_tables_question(None, "Auto save to GeoPackage", str(path), plan)

    assert box.text() == "fu8.gpkg already has a table named Scratch_A. No layer of this project uses it."
    assert box.informativeText() == (
        "Replace it: the table is overwritten with this project's layer, and its old features "
        "and styles are gone.\n"
        "Keep it: this project's layer is saved next to it, as Scratch_A_2.\n"
        "Either way, the file's other tables stay as they are, and so does anything other "
        "programs stored in it.")
    assert [replace.text(), keep.text()] == ["Replace it", "Keep it"]


@pytest.mark.parametrize("button, expected", [
    ("Replace it", "replace"), ("Keep it", "keep"), ("Cancel", None), (None, None)])
def test_each_button_gives_its_answer(tmp_path, monkeypatch, button, expected):
    """``None`` closes the box with no button, as Escape or the window's X does."""
    path, plan = _keep_plan(tmp_path, ["Poles"], ["Poles"])

    def click(box):
        for each in box.buttons():
            if button is not None and each.text().replace("&", "") == button:
                each.click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", click)

    assert export_manager.ask_about_unused_tables(None, "t", str(path), plan) == expected


# ---------------------------------------------------------------------------
# QGIS 3.22's style prompt, in a process of its own with a deadline
# ---------------------------------------------------------------------------

DRIVER = '''
import json
import os
import sqlite3
import sys

sys.path.insert(0, {repo!r})

from qgis.core import QgsApplication

QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QMessageBox

from fiberq.core import export_manager

MODALS = []


def close():
    widget = QApplication.activeModalWidget()
    if widget is None:
        return
    MODALS.append([widget.windowTitle(), widget.text() if hasattr(widget, "text") else ""])
    no = widget.button(QMessageBox.StandardButton.No) if isinstance(widget, QMessageBox) else None
    if no is not None:
        no.click()
    else:
        widget.reject()


TIMER = QTimer()
TIMER.timeout.connect(close)
TIMER.start(50)


class Bar:
    def __init__(self):
        self.lines = []

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.lines.append([name] + [str(a) for a in args])


class Iface:
    def __init__(self):
        self.bar = Bar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


def memory(name, count):
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer", name, "memory")
    layer.startEditing()
    for number in range(count):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(number, number)))
        layer.addFeature(feature)
    layer.commitChanges()
    return layer


target = sys.argv[1]
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (target, ""))
export_manager.ask_about_unused_tables = lambda *a, **k: "replace"
project = QgsProject.instance()

# Session one: Save all writes the tables and a default style for each.
for name, count in (("Poles", 3), ("Manholes", 2)):
    project.addMapLayer(memory(name, count))
first = Iface()
export_manager.ExportManager(first).save_all_layers_to_gpkg()
project.removeAllMapLayers()

# Session two, after the "restart": the same names, replaced.
for name in ("Poles", "Manholes"):
    project.addMapLayer(memory(name, 1))
second = Iface()
export_manager.ExportManager(second).save_all_layers_to_gpkg()

conn = sqlite3.connect(target)
styles = conn.execute("SELECT f_table_name, styleName FROM layer_styles ORDER BY f_table_name").fetchall()
tables = conn.execute("SELECT table_name FROM gpkg_contents WHERE data_type = 'features' "
                      "ORDER BY table_name").fetchall()
conn.close()
print("RESULT " + json.dumps({{"first": first.bar.lines, "second": second.bar.lines, "modals": MODALS,
                              "styles": styles, "tables": tables}}), flush=True)
os._exit(0)
'''


def test_replacing_never_meets_the_style_prompt_of_qgis_322(tmp_path):
    """No GDAL removes a table's layer_styles rows when it overwrites the table
    (3.4.1, 3.8.4, 3.10.3, 3.12.2, measured), so a replaced table's old default
    style would still be there -- and QGIS 3.22 answers saveStyleToDatabase over
    an existing default with a modal "overwrite it?" that nothing headless ever
    answers. Run apart, with a deadline: a prompt is closed, recorded and
    failed on, and a hang fails on the timeout rather than stopping the suite.
    """
    script = tmp_path / "replace_styles.py"
    script.write_text(DRIVER.format(repo=REPO_ROOT), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", TMPDIR=str(tmp_path),
                       FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script), str(tmp_path / "fu8.gpkg")], cwd=str(tmp_path),
                          env=environment, timeout=TIMEOUT_S, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [line for line in output.splitlines() if line.startswith("RESULT ")]
    assert done.returncode == 0 and lines, f"returncode {done.returncode}\n{output}"
    result = json.loads(lines[-1][len("RESULT "):])

    assert result["modals"] == [], result["modals"]
    assert result["tables"] == [["Manholes"], ["Poles"]], result
    assert result["styles"] == [["Manholes", "default"], ["Poles", "default"]], result
    assert [line[0] for line in result["second"]] == ["pushSuccess"], result["second"]


# ---------------------------------------------------------------------------
# the second round: what the plan counts as used is never wrong the unsafe way
# ---------------------------------------------------------------------------
#
# Each of these was measured on this fix's first version by the review's
# probes (named pN): the question was asked about a table some layer reads --
# or would, once found -- and Replace wrote over it; or a file the plan could
# not read was planned as empty; or a write that failed took the old table's
# styles, or the old table, without a word.

def _linked(tmp_path):
    """fu8.gpkg in real/, and real/ again as link/: one file, two spellings."""
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    os.symlink(str(real), str(link))
    return real / "fu8.gpkg", link / "fu8.gpkg"


def test_a_layer_reading_the_file_through_a_symlink_keeps_its_table(iface, project, save_to, answer, modals,
                                                                    tmp_path):
    """p12: "Zpoles 2024" reads Poles through a symlinked folder. As strings
    the paths differed, Poles was offered, and Replace wrote the new Poles over
    the three features that layer reads."""
    target, through_link = _linked(tmp_path)
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    reader = QgsVectorLayer(f"{through_link}|layername=Poles", "Zpoles 2024", "ogr")
    assert reader.isValid()
    project.addMapLayer(reader)
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == [], "a table read through another spelling of the file was offered"
    assert _feature_tables(target) == {"Poles": 3, "Poles_2": 1}
    assert reader.source() == f"{through_link}|layername=Poles", "it lives in the file already: kept"
    assert fresh.source() == f"{target}|layername=Poles_2"
    assert modals == []


@pytest.mark.parametrize("spelling, table", [("hardlink", "Poles"), ("symlink", "poles")])
def test_a_layer_reading_its_own_table_under_another_spelling_is_not_written_over_it(
        iface, project, save_to, answer, modals, tmp_path, spelling, table):
    """p2b, p15: the layer called Poles reads the table itself, through a hard
    link (the same file under a second name) or a symlink. Offered as unused,
    Replace had the writer drop the table it was reading: Poles came back empty."""
    if spelling == "hardlink":
        target = tmp_path / "fu8.gpkg"
        _session_one(project, target, save_to, layers=((table, 3),))
        path = tmp_path / "alias.gpkg"
        os.link(str(target), str(path))
    else:
        target, path = _linked(tmp_path)
        _session_one(project, target, save_to, layers=((table, 3),))
    layer = QgsVectorLayer(f"{path}|layername={table}", "Poles", "ogr")
    assert layer.isValid()
    project.addMapLayer(layer)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == []
    assert _feature_tables(target) == {table: 3}
    assert layer.source() == f"{path}|layername={table}"
    assert iface.bar.warnings == []
    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]


def _unavailable(project, save_to, tmp_path, name):
    """A project whose layer ``name`` read old-mount/fu8.gpkg's Poles, opened
    after the drive came back as new-mount: the layer is there and invalid."""
    old = tmp_path / "old-mount"
    old.mkdir()
    _session_one(project, old / "fu8.gpkg", save_to, layers=(("Poles", 3),))
    project.addMapLayer(QgsVectorLayer(f"{old / 'fu8.gpkg'}|layername=Poles", name, "ogr"))
    assert project.write(str(tmp_path / "proj.qgs"))
    project.removeAllMapLayers()
    os.rename(str(old), str(tmp_path / "new-mount"))
    assert project.read(str(tmp_path / "proj.qgs"))
    for scope, key in ENTRIES:
        project.removeEntry(scope, key)
    assert [(layer.name(), layer.isValid()) for layer in project.mapLayers().values()] == [(name, False)]
    return tmp_path / "new-mount" / "fu8.gpkg"


def test_a_table_an_unavailable_layer_reads_is_not_offered(iface, project, save_to, answer, modals, tmp_path):
    """p14: the project's "Poles 2024" read old-mount/fu8.gpkg, and the drive
    came back as new-mount. Unavailable, it read nothing as far as the plan
    could tell, so its Poles was offered -- the table it reads again once the
    user points it at the file."""
    try:
        target = _unavailable(project, save_to, tmp_path, "Poles 2024")
        fresh = _memory_layer("Poles", 1)
        project.addMapLayer(fresh)
        answer.reply = export_manager.REPLACE

        save_to(ExportManager(iface), target)

        assert answer.asked == [], "a table an unavailable layer reads was offered"
        assert _feature_tables(target)["Poles"] == 3
        assert fresh.source() == f"{target}|layername=Poles_2"
    finally:
        project.clear()


def test_an_unavailable_layer_of_the_same_name_keeps_its_table_and_styles(iface, project, save_to, answer, modals,
                                                                          tmp_path):
    """p3: the unavailable layer is itself called Poles. Offered, Replace took
    the old styles and then could not write a layer it cannot read."""
    try:
        target = _unavailable(project, save_to, tmp_path, "Poles")
        answer.reply = export_manager.REPLACE

        save_to(ExportManager(iface), target)

        assert answer.asked == []
        assert _feature_tables(target) == {"Poles": 3}
        assert _styles(target, "Poles") == ["default", "printing"]
        assert iface.bar.successes == [], "an unavailable layer cannot be saved"
    finally:
        project.clear()


def test_a_table_under_a_view_a_layer_reads_is_not_offered(iface, project, save_to, answer, modals, tmp_path):
    """p4b: a layer reads a view over Poles. The view's base tables are not
    taken apart, so the whole file counts as read."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("CREATE VIEW poles_view AS SELECT fid, geom, id FROM Poles")
        conn.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) "
                     "VALUES ('poles_view', 'features', 'poles_view', 3857)")
        conn.execute("INSERT INTO gpkg_geometry_columns (table_name, column_name, geometry_type_name, srs_id, z, m) "
                     "VALUES ('poles_view', 'geom', 'POINT', 3857, 0, 0)")
        conn.commit()
    reader = QgsVectorLayer(f"{target}|layername=poles_view", "Poles (view)", "ogr")
    assert reader.isValid() and reader.featureCount() == 3
    project.addMapLayer(reader)
    project.addMapLayer(_memory_layer("Poles", 1))
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == []
    assert QgsVectorLayer(f"{target}|layername=poles_view", "check", "ogr").featureCount() == 3


def test_a_tiles_table_named_like_a_layer_is_not_offered(iface, project, save_to, answer, modals, tmp_path):
    """p9: offered, Replace could not write over it ("table already exists")."""
    from osgeo import gdal

    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Manholes", 2),))
    raster = gdal.GetDriverByName("GPKG").Create(str(target), 4, 4, 1, gdal.GDT_Byte,
                                                 options=["RASTER_TABLE=Poles", "APPEND_SUBDATASET=YES"])
    raster.SetGeoTransform([0, 1, 0, 4, 0, -1])
    raster.GetRasterBand(1).Fill(7)
    raster = None
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == []
    with closing(sqlite3.connect(str(target))) as conn:
        assert conn.execute("SELECT data_type FROM gpkg_contents WHERE table_name = 'Poles'").fetchall() == [
            ("tiles",)]
    assert fresh.source() == f"{target}|layername=Poles_2"
    assert iface.bar.warnings == []


def test_a_file_whose_tables_cannot_be_read_stops_before_anything_is_asked(iface, project, save_to, answer, modals,
                                                                           tmp_path, monkeypatch):
    """p6b: another program held the file while the plan read its tables. The
    read failed, the plan saw no table -- nothing offered, every name free --
    and the writer, let in a moment later, replaced whatever had the layer's
    name. Here the read fails and the writer would get in: a lock that is gone
    by the time the layers are written, the worst case of it. (A real lock is
    in test_gpkg_target.py: a GeoPackage QGIS has opened is in WAL mode on
    3.40 and 4.2, where a writer's lock does not keep a reader out.)"""
    from fiberq.core import gpkg_target

    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    layers = _session_two(project, ("Poles", "Manholes"))
    answer.reply = export_manager.REPLACE
    entries = _entries(project)

    def locked(path):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(gpkg_target, "_read_only", locked, raising=False)
    monkeypatch.setattr(gpkg_target, "existing_tables", lambda path: set())   # what it answers when locked

    save_to(ExportManager(iface), target)

    assert answer.asked == []
    assert iface.bar.warnings == [
        "The tables of fu8.gpkg could not be read (OperationalError: database is locked). Nothing was saved."]
    assert iface.bar.successes == []
    assert [layer.dataProvider().name() for layer in layers] == ["memory", "memory"]
    assert _feature_tables(target) == {"Poles": 3}, "the old Poles was written over"
    assert _entries(project) == entries, "a save that did not happen moved the project's GeoPackage"


def test_a_file_that_cannot_be_written_to_is_said_before_any_question(iface, project, save_to, answer, modals,
                                                                      tmp_path, monkeypatch):
    """p6a: asked first, then every layer failed. Patched rather than chmod-ed:
    CI runs as root, which the write bit does not stop."""
    from fiberq.core import gpkg_target

    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    _session_two(project, ("Poles",))
    answer.reply = export_manager.REPLACE
    before = (_sha(target), _entries(project))
    monkeypatch.setattr(gpkg_target.os, "access", lambda path, mode: False)

    save_to(ExportManager(iface), target)

    assert answer.asked == []
    assert iface.bar.warnings == ["fu8.gpkg cannot be written to. Nothing was saved."]
    assert (_sha(target), _entries(project)) == before


def test_a_file_that_is_not_a_geopackage_is_said_before_any_question(iface, project, save_to, answer, tmp_path):
    target = tmp_path / "notes.gpkg"
    target.write_bytes(b"last week's notes, saved with the wrong extension")
    project.addMapLayer(_memory_layer("Poles"))

    save_to(ExportManager(iface), target)

    assert iface.bar.warnings == ["notes.gpkg is not a GeoPackage. Nothing was saved."]
    assert target.read_bytes() == b"last week's notes, saved with the wrong extension"


def _big_layer(name, count):
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer&field=blob:string(0)", name, "memory")
    layer.startEditing()
    for number in range(count):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(number, number)))
        feature.setAttributes([number, "x" * 2000])
        layer.addFeature(feature)
    assert layer.commitChanges()
    return layer


def test_a_write_that_fails_part_way_says_the_old_table_is_gone(iface, project, save_to, answer, modals, tmp_path):
    """p6c: a full disk -- RLIMIT_FSIZE stands in for one, and Python ignores
    SIGXFSZ, so a write past it fails with EFBIG -- after the writer dropped
    the old Manholes. The message said only what the writer said."""
    import resource

    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3), ("Manholes", 2)))
    manholes = _big_layer("Manholes", 3000)
    project.addMapLayer(manholes)
    answer.reply = export_manager.REPLACE
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(resource.RLIMIT_FSIZE, (os.path.getsize(target) + 40 * 1024, hard))
    try:
        save_to(ExportManager(iface), target)
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))

    assert iface.bar.successes == []
    assert len(iface.bar.warnings) == 1, iface.bar.warnings
    assert iface.bar.warnings[0].startswith(
        "Manholes: not saved, and the old table Manholes is no longer in the file: "), iface.bar.warnings
    assert "Manholes" not in _feature_tables(target)
    assert manholes.dataProvider().name() == "memory", "the layer keeps its features where they were"
    assert _styles(target, "Manholes") == ["default"], "a write that failed must leave the old styles"


def test_a_write_that_leaves_part_of_the_layer_says_the_old_table_was_overwritten(
        iface, project, save_to, answer, modals, tmp_path):
    """p16: a fid column with one value three times. The writer dropped the old
    Poles, wrote one feature and refused the next two."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=fid:integer&field=id:integer", "Poles", "memory")
    layer.startEditing()
    for number in range(3):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(number, number)))
        feature.setAttributes([7, number])
        layer.addFeature(feature)
    assert layer.commitChanges()
    project.addMapLayer(layer)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert iface.bar.successes == []
    assert len(iface.bar.warnings) == 1, iface.bar.warnings
    assert iface.bar.warnings[0].startswith(
        "Poles: not saved, and the old table Poles was overwritten with only part of this layer: "), iface.bar.warnings
    assert _feature_tables(target) == {"Poles": 1}
    assert layer.dataProvider().name() == "memory"
    assert _styles(target, "Poles") == ["default", "printing"], "a write that failed must leave the old styles"


def test_an_overwrite_the_file_refuses_keeps_the_old_table_and_its_styles(iface, project, save_to, answer, modals,
                                                                          tmp_path):
    """p8: another table's foreign key into Poles makes GDAL refuse to drop it.
    The old styles went before the write; now they go after it, and the old
    table is said to be nothing but where it was."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    with closing(sqlite3.connect(str(target))) as conn:
        fids = [row[0] for row in conn.execute("SELECT fid FROM Poles")]
        conn.execute("CREATE TABLE visits (vid INTEGER PRIMARY KEY, pole_fid INTEGER "
                     "REFERENCES Poles(fid) ON DELETE CASCADE, note TEXT)")
        conn.executemany("INSERT INTO visits (pole_fid, note) VALUES (?, 'v')", [(fid,) for fid in fids])
        conn.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier) "
                     "VALUES ('visits', 'attributes', 'visits')")
        conn.commit()
    project.addMapLayer(_memory_layer("Poles", 1))
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert len(answer.asked) == 1
    assert iface.bar.successes == []
    assert len(iface.bar.warnings) == 1 and "foreign_key_check" in iface.bar.warnings[0], iface.bar.warnings
    assert "the old table" not in iface.bar.warnings[0], "the old table is where it was"
    assert _feature_tables(target) == {"Poles": 3}
    assert _styles(target, "Poles") == ["default", "printing"], "a write that failed must leave the old styles"


# ---------------------------------------------------------------------------
# the second round: one line per message-bar item, and the question's title
# ---------------------------------------------------------------------------
#
# QGIS's message bar shows one line of an item's text: a newline is a space and
# the rest is cut off, and a green item closes after five seconds (measured on
# 3.40.15 and 4.2.3 at 1280 to 1920 pixels). The first round put three
# sentences under the green success, and two of them were never read.

TWENTY = ["Poles", "Manholes", "Route", "Aerial_cables", "Underground_cables", "Joint_Closures", "ODF", "TB",
          "OTB", "TO", "Optical_slacks", "Fiber_break", "Service_Area", "PE_pipes", "Transition_pipes",
          "Patch_panel", "Indoor_OTB", "Outdoor_OTB", "Pole_OTB", "Objects"]


def _plan_of(tables, replace):
    from fiberq.core.gpkg_target import TablePlan

    return TablePlan([table if replace else f"{table}_2" for table in tables], list(tables), frozenset(),
                     dict(enumerate(tables)), replace)


def test_a_long_list_is_shortened_in_the_bar_and_whole_in_the_log():
    success, notes, sentences = export_manager.saved_report("All layers saved to fu8.gpkg.",
                                                            _plan_of(TWENTY, True), TWENTY)

    assert success.startswith("All layers saved to fu8.gpkg. The old tables Poles, Manholes")
    assert success.endswith(" more were replaced."), success
    assert len(success) <= 100
    assert notes == []
    assert sentences == ["The old tables " + ", ".join(TWENTY) + " were replaced."]

    success, notes, sentences = export_manager.saved_report("All layers saved to fu8.gpkg.",
                                                            _plan_of(TWENTY, False), TWENTY)

    assert success == "All layers saved to fu8.gpkg."
    (note,) = notes
    assert note.startswith("Saved next to tables of the same names: Poles → Poles_2, ")
    assert note.endswith(" more."), note
    assert len(note) <= 110
    pairs = ", ".join(f"{table} → {table}_2" for table in TWENTY)
    assert sentences == [f"Saved next to tables of the same names: {pairs}."]


def test_the_replaced_tables_stay_off_a_line_they_do_not_fit():
    outcome = "All layers saved to a-geopackage-whose-name-alone-takes-most-of-the-line-there-is.gpkg."

    success, _notes, sentences = export_manager.saved_report(outcome, _plan_of(TWENTY, True), TWENTY)

    assert success == outcome
    assert len(sentences) == 1, "the log still has it"


def test_what_a_save_says_reaches_a_real_message_bar_in_order(tmp_path):
    """Pushed into QGIS's own QgsMessageBar: the green line is shown first, and
    when it closes the notes stay, each until closed (QGIS shows its newest
    item first and then the others, newest first)."""
    from qgis.gui import QgsMessageBar

    bar = QgsMessageBar()
    plan = _plan_of(["Poles"], False)

    export_manager.push_saved(bar, "GPKG export", "All layers saved to fu8.gpkg.", plan, ["Poles"],
                              moved="Auto-save now writes to fu8.gpkg.")

    items = [(item.text(), item.duration(), item.level()) for item in bar.items()]
    assert items == [
        ("All layers saved to fu8.gpkg.", 5, Qgis.MessageLevel.Success),
        ("Saved next to a table of the same name: Poles → Poles_2.", 0, Qgis.MessageLevel.Info),
        ("Auto-save now writes to fu8.gpkg.", 0, Qgis.MessageLevel.Info),
    ]
    shown = []
    while bar.currentItem() is not None:
        shown.append(bar.currentItem().text())
        bar.popWidget()
    assert shown == [text for text, _duration, _level in items]


def test_the_question_is_titled_with_the_buttons_own_words(iface, project, save_to, answer, tmp_path):
    """The button's text as this QGIS shows it -- translated, its "&" shortcut
    mark dropped -- rather than a second translation of the same words."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    _session_two(project, ("Poles",))
    answer.reply = None

    save_to(ExportManager(iface, FakePlugin(False, "Enregistrer &tout && fermer")), target)

    assert [asked["title"] for asked in answer.asked] == ["Enregistrer tout & fermer"]


# ---------------------------------------------------------------------------
# the third round: a table is offered only when everything is understood
# ---------------------------------------------------------------------------
#
# Two rounds of review kept finding ways a layer reads a table that the plan
# had not counted, and each one let Replace destroy what a layer reads. The
# plan now offers a table only when it understands the file, the table and
# every layer of the project (an allow-list in gpkg_target), and only when
# neither the file nor the project changed while the question was open;
# otherwise nothing is offered and each layer goes beside the tables of its
# name. Each test here is one of the reviews' probes (round one's pN, round
# two's nN, tN, fN, vN) and shows the data a layer reads kept.

def _gdal_gpkg(path, tables):
    """A GeoPackage as another program (ogr2ogr) makes it: feature tables only, fids from 1."""
    from osgeo import ogr, osr

    source = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    for name, numbers in tables.items():
        layer = source.CreateLayer(name, srs, ogr.wkbPoint)
        layer.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
        for number in numbers:
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetField("id", number)
            feature.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({number} {number})"))
            layer.CreateFeature(feature)
    source = None


def _ids(path, table, column="id"):
    """The values of ``column`` in ``table``, sorted. A column that is not there reads as its own name."""
    with closing(sqlite3.connect(str(path))) as conn:
        return sorted(row[0] for row in conn.execute(f'SELECT "{column}" FROM "{table}"'))


def _reads(layer):
    """The ``id`` of every feature ``layer`` reads now."""
    layer.dataProvider().reloadData()
    return sorted(feature["id"] for feature in layer.getFeatures())


@pytest.fixture
def meanwhile(monkeypatch):
    """FiberQ's question: ``meanwhile.action`` runs while it is open, then ``meanwhile.reply`` answers it."""
    class Meanwhile:
        reply = None
        action = None

        def __init__(self):
            self.asked = []
            self.seen = []

        def __call__(self, parent, title, gpkg_path, plan):
            self.asked.append(list(plan.offered))
            if self.action is not None:
                self.seen.append(self.action())
            return self.reply

    recorder = Meanwhile()
    monkeypatch.setattr(export_manager, "ask_about_unused_tables", recorder, raising=False)
    return recorder


#: The one warning of a save whose file or project changed while the question was open.
CHANGED = "fu8.gpkg or this project changed while the question was open. Nothing was saved."

VRT = ("<OGRVRTDataSource><OGRVRTLayer name=\"poles_vrt\"><SrcDataSource>{target}</SrcDataSource>"
       "<SrcLayer>Poles</SrcLayer></OGRVRTLayer></OGRVRTDataSource>")


def _reader(kind, target, folder):
    """A layer reading ``target``'s Poles -- or Manholes, filtered by Poles -- in a way the plan does not understand."""
    from qgis.core import QgsRasterLayer, QgsVirtualLayerDefinition

    if kind == "subquery":       # review n1
        return QgsVectorLayer(f'{target}|layername=Manholes|subset="id" IN (SELECT "id" FROM "Poles")', "near", "ogr")
    if kind == "sql":            # review n1
        return QgsVectorLayer(f'{target}|layername=Manholes|subset=SELECT * FROM "Poles"', "sql", "ogr")
    if kind == "sql_bare":       # review n1
        return QgsVectorLayer(f'{target}|subset=SELECT * FROM "Poles"', "sql", "ogr")
    if kind == "layerid":        # review p4
        return QgsVectorLayer(f"{target}|layerid=0", "first", "ogr")
    if kind == "gpkg_prefix":    # review n4
        return QgsVectorLayer(f"GPKG:{target}:Poles", "Zpoles (GPKG:)", "ogr")
    if kind in ("vrt", "vrt_named_geojson"):     # review v1, and GDAL reading a file by what it holds
        path = folder / ("poles.vrt" if kind == "vrt" else "poles.geojson")
        path.write_text(VRT.format(target=target), encoding="utf-8")
        return QgsVectorLayer(f"{path}|layername=poles_vrt", "Zpoles (VRT)", "ogr")
    if kind.startswith("virtual"):               # review n3: the file under another name
        other = folder / "current.gpkg"
        if kind == "virtual_hardlink":
            os.link(str(target), str(other))
        else:
            os.symlink(str(target), str(other))
        definition = QgsVirtualLayerDefinition()
        definition.addSource("p", f"{other}|layername=Poles", "ogr")
        definition.setQuery("SELECT * FROM p")
        return QgsVectorLayer(definition.toString(), "Poles (virtual)", "virtual")
    if kind == "wms_mbtiles":    # measured: valid, a WMS layer reading the GeoPackage as MBTiles
        return QgsRasterLayer(f"type=mbtiles&url=file://{target}", "Poles tiles", "wms")
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["subquery", "sql", "sql_bare", "layerid", "gpkg_prefix", "vrt",
                                  "vrt_named_geojson", "virtual_hardlink", "virtual_symlink", "wms_mbtiles"])
def test_a_layer_reading_the_file_in_a_way_not_understood_keeps_every_table(
        iface, project, save_to, answer, modals, tmp_path, kind):
    """n1, n3, n4, p4, v1: the second round offered Poles while these layers
    read it -- by a subquery, through a hard link, as "GPKG:" given to OGR, a
    VRT -- and Replace left them reading the new Poles, or nothing."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3), ("Manholes", 2)))
    folder = tmp_path / "elsewhere"
    folder.mkdir()
    reader = _reader(kind, target, folder)
    assert reader.isValid(), kind
    project.addMapLayer(reader)
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == [], "a table was offered while a layer not understood reads the file"
    assert _ids(target, "Poles") == [0, 1, 2]
    assert _ids(target, "Manholes") == [0, 1]
    assert fresh.source() == f"{target}|layername=Poles_2"
    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]
    assert modals == []


@pytest.mark.parametrize("made_by", ["gdal", "fiberq"])
@pytest.mark.parametrize("kind", ["table", "view"])
def test_a_table_no_registry_lists_is_never_written_over(
        iface, project, save_to, answer, modals, tmp_path, made_by, kind):
    """n5: another program's table, or view, kept out of gpkg_contents and
    named like a layer. The plan saw a free name, and the writer replaced the
    table: its three rows were gone."""
    target = tmp_path / "fu8.gpkg"
    if made_by == "gdal":
        _gdal_gpkg(target, {"Poles": [100, 101, 102]})
    else:
        _session_one(project, target, save_to, layers=(("Poles", 3),))
    with closing(sqlite3.connect(str(target))) as conn:
        if kind == "table":
            conn.execute('CREATE TABLE "Notes" (nid INTEGER PRIMARY KEY, note TEXT)')
            conn.executemany('INSERT INTO "Notes" (note) VALUES (?)', [("one",), ("two",), ("three",)])
        else:
            conn.execute('CREATE VIEW "Notes" AS SELECT fid AS nid, id AS note FROM "Poles"')
        conn.commit()
    layer = _memory_layer("Notes", 1)
    project.addMapLayer(layer)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == []
    assert _ids(target, "Notes", "nid") == [1, 2, 3], "the other program's Notes was written over"
    assert layer.source() == f"{target}|layername=Notes_2"
    assert iface.bar.warnings == []


def test_replacing_one_table_leaves_a_table_no_registry_lists(iface, project, save_to, answer, modals, tmp_path):
    """n5c: the question said the file's other tables stay as they are, while
    a layer named like an unregistered table was written over it."""
    target = tmp_path / "fu8.gpkg"
    _gdal_gpkg(target, {"Poles": [100, 101, 102]})
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('CREATE TABLE "Notes" (nid INTEGER PRIMARY KEY, note TEXT)')
        conn.executemany('INSERT INTO "Notes" (note) VALUES (?)', [("one",), ("two",), ("three",)])
        conn.commit()
    project.addMapLayer(_memory_layer("Notes", 1))
    project.addMapLayer(_memory_layer("Poles", 1))
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert [asked["offered"] for asked in answer.asked] == [["Poles"]]
    assert _ids(target, "Notes", "nid") == [1, 2, 3]
    assert _feature_tables(target) == {"Poles": 1, "Notes_2": 1}


@pytest.mark.parametrize("how", ["directly", "by_a_task"])
def test_a_layer_added_while_the_question_is_open_stops_the_save(
        iface, project, save_to, meanwhile, modals, tmp_path, how):
    """n8, n8b: a layer reading Poles came in while the question was open --
    added by a plugin, or by a background task finishing -- and Replace wrote
    over what it reads. Nothing is written now; the user may save again."""
    from qgis.core import QgsApplication, QgsTask

    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3), ("Manholes", 2)))
    layers = _session_two(project, ("Poles", "Manholes"))
    entries = _entries(project)
    added = []

    def add_reader(*_finished):
        reader = QgsVectorLayer(f"{target}|layername=Poles", "Poles 2024", "ogr")
        project.addMapLayer(reader)
        added.append(reader)

    def meanwhile_action():
        if how == "directly":
            add_reader()
            return
        task = QgsTask.fromFunction("loads Poles 2024", lambda _task: "done", on_finished=add_reader)
        QgsApplication.taskManager().addTask(task)
        for _ in range(500):
            if added:
                return
            QApplication.processEvents()
            QTimer.singleShot(10, lambda: None)
        raise AssertionError("the task never finished")

    meanwhile.action = meanwhile_action
    meanwhile.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert len(meanwhile.asked) == 1 and added
    assert iface.bar.warnings == [CHANGED]
    assert iface.bar.successes == []
    assert _reads(added[0]) == [0, 1, 2]
    assert _feature_tables(target) == {"Poles": 3, "Manholes": 2}
    assert [layer.dataProvider().name() for layer in layers] == ["memory", "memory"]
    assert _entries(project) == entries


@pytest.mark.parametrize("reply", ["keep", "replace"])
@pytest.mark.parametrize("change", ["tables_added", "file_replaced"])
def test_a_file_changed_while_the_question_is_open_is_not_written(
        iface, project, save_to, meanwhile, modals, tmp_path, change, reply):
    """n10, f1: another program wrote Poles_2 into the file -- or a sync
    client put another copy of it in its place -- while the question was
    open. Keep then wrote the new Poles over that Poles_2."""
    from osgeo import ogr, osr

    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3), ("Manholes", 2)))
    layers = _session_two(project, ("Poles", "Manholes"))

    def other_program():
        path = target if change == "tables_added" else tmp_path / "incoming.gpkg"
        if change == "file_replaced":
            path.write_bytes(target.read_bytes())
        source = ogr.Open(str(path), 1)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(3857)
        layer = source.CreateLayer("Poles_2", srs, ogr.wkbPoint)
        layer.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
        for number in range(500, 505):
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetField("id", number)
            feature.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({number} {number})"))
            layer.CreateFeature(feature)
        source = layer = None
        if change == "file_replaced":
            os.replace(str(path), str(target))

    meanwhile.action = other_program
    meanwhile.reply = reply

    save_to(ExportManager(iface), target)

    assert iface.bar.warnings == [CHANGED]
    assert _feature_tables(target) == {"Poles": 3, "Manholes": 2, "Poles_2": 5}
    assert _ids(target, "Poles_2") == [500, 501, 502, 503, 504]
    assert [layer.dataProvider().name() for layer in layers] == ["memory", "memory"]


class _HookCore:
    """What RoutingUI's auto-save hook reads of the plugin."""

    def __init__(self):
        self.bar = FakeBar()
        self.iface = self

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


@pytest.fixture
def hook(project):
    """Auto-save's own layer hook, connected as turning auto-save on connects it."""
    from fiberq.ui.routing_ui import RoutingUI

    ui = RoutingUI.__new__(RoutingUI)
    ui.core = _HookCore()
    ui._auto_gpkg_connected = True
    project.layerWasAdded.connect(ui._on_layer_added_auto_gpkg)
    yield ui
    project.layerWasAdded.disconnect(ui._on_layer_added_auto_gpkg)


def test_auto_saves_hook_waits_for_the_question_and_saves_its_layer_after(
        iface, project, save_to, meanwhile, hook, modals, tmp_path):
    """n9: auto-save is on, writing to the file Save all is asking about, and a
    new temporary Poles is added while the question is open. The hook wrote it
    at once as Poles_2 -- the name Keep then wrote Save all's Poles over. Now
    the hook waits; the save stops, the project having changed; and then the
    layer goes the hook's own way."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3), ("Manholes", 2)))
    _session_two(project, ("Poles", "Manholes"))
    for scope in ("FiberQPlugin", "TelecomPlugin"):
        project.writeEntry(scope, "gpkg_path", str(target))
    late = []

    def add_temporary_layer():
        layer = _memory_layer("Poles", 3)
        project.addMapLayer(layer)
        late.append(layer)
        return layer.dataProvider().name(), _feature_tables(target), export_manager.auto_save_held()

    meanwhile.action = add_temporary_layer
    meanwhile.reply = export_manager.KEEP

    save_to(ExportManager(iface, FakePlugin(auto_save_on=True)), target)

    assert meanwhile.seen == [("memory", {"Poles": 3, "Manholes": 2}, True)], "the hook wrote during the question"
    assert iface.bar.warnings == [CHANGED]
    assert not export_manager.auto_save_held()
    assert late[0].source() == f"{target}|layername=Poles_2"
    assert _feature_tables(target) == {"Poles": 3, "Manholes": 2, "Poles_2": 3}
    assert hook.core.bar.notes == [
        ("Poles is stored as table Poles_2, because fu8.gpkg already has a table named Poles.",
         Qgis.MessageLevel.Info, 0)]


@pytest.mark.parametrize("end", ["cancel", "error"])
def test_auto_saves_hook_is_let_go_when_the_save_ends_without_writing(
        iface, project, save_to, meanwhile, hook, modals, tmp_path, end):
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    _session_two(project, ("Poles",))
    for scope in ("FiberQPlugin", "TelecomPlugin"):
        project.writeEntry(scope, "gpkg_path", str(target))
    late = []

    def add_temporary_layer():
        layer = _memory_layer("Scratch D", 1)
        project.addMapLayer(layer)
        late.append(layer)
        if end == "error":
            raise RuntimeError("the question failed")
        return layer.dataProvider().name()

    meanwhile.action = add_temporary_layer
    meanwhile.reply = None

    save_to(ExportManager(iface, FakePlugin(auto_save_on=True)), target)

    assert not export_manager.auto_save_held()
    assert late[0].source() == f"{target}|layername=Scratch_D", "the layer put off was never taken"
    assert _feature_tables(target) == {"Poles": 3, "Scratch_D": 1}
    assert len(iface.bar.warnings) == (1 if end == "error" else 0)


def _linked_dotdot(tmp_path, project, save_to):
    """b/fu8.gpkg holding Poles, and another session's Poles_2 that nothing reads; a/link
    pointing at b/sub; and a/fu8.gpkg, another file holding Ducts."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    (b / "sub").mkdir(parents=True)
    _session_one(project, b / "fu8.gpkg", save_to, layers=(("Poles", 3), ("Poles_2", 4)))
    _gdal_gpkg(a / "fu8.gpkg", {"Ducts": [7, 8]})
    os.symlink(str(b / "sub"), str(a / "link"))
    return b / "fu8.gpkg", a / "fu8.gpkg", f"{a}/link/../fu8.gpkg"


def test_a_file_spelled_through_a_symlink_and_dotdot_is_the_file_saved_into(
        iface, project, save_to, answer, modals, tmp_path):
    """n12, t3: "a/link/../fu8.gpkg" is b/fu8.gpkg to the system and to QGIS
    3.40 and later, a/fu8.gpkg to os.path.abspath and to QGIS 3.22. The plan
    read a's tables and found Poles_2 free; the writer then replaced b's
    Poles_2, another session's four features (3.40, 4.2), or wrote into a
    (3.22). Resolved once, the plan and the writer meet in b."""
    real, twin, spelled = _linked_dotdot(tmp_path, project, save_to)
    reader = QgsVectorLayer(f"{real}|layername=Poles", "Poles 2024", "ogr")
    assert reader.isValid()
    project.addMapLayer(reader)
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), spelled)

    assert answer.asked == []
    assert _ids(real, "Poles_2") == [0, 1, 2, 3], "another session's Poles_2 was written over"
    assert _feature_tables(real) == {"Poles": 3, "Poles_2": 4, "Poles_3": 1}
    assert _feature_tables(twin) == {"Ducts": 2}
    assert _reads(reader) == [0, 1, 2]
    assert fresh.source() == f"{os.path.realpath(real)}|layername=Poles_3"
    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]


def test_a_layer_reading_the_file_through_a_symlink_and_dotdot_keeps_its_table(
        iface, project, save_to, answer, modals, tmp_path):
    """n12: QGIS 3.22 cannot open such a path at all, and the layer is
    invalid; later QGIS can, and the layer reads the target's Poles."""
    real, _twin, _spelled = _linked_dotdot(tmp_path, project, save_to)
    deep = tmp_path / "deep"
    deep.mkdir()
    os.symlink(str(real.parent / "sub"), str(deep / "link2"))
    reader = QgsVectorLayer(f"{deep}/link2/../fu8.gpkg|layername=Poles", "Poles 2024", "ogr")
    project.addMapLayer(reader)
    project.addMapLayer(_memory_layer("Poles", 1))
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), real)

    assert answer.asked == []
    assert _ids(real, "Poles") == [0, 1, 2]
    if reader.isValid():
        assert _reads(reader) == [0, 1, 2]


def test_a_save_through_a_symlink_into_auto_saves_file_does_not_move_it(
        iface, project, save_to, answer, modals, tmp_path):
    """n14: one file, two spellings -- the reader and auto-save on the real path."""
    real = tmp_path / "real"
    real.mkdir()
    target = real / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    link = tmp_path / "link"
    os.symlink(str(real), str(link))
    reader = QgsVectorLayer(f"{target}|layername=Poles", "Poles 2024", "ogr")
    project.addMapLayer(reader)
    project.addMapLayer(_memory_layer("Poles", 1))
    for scope in ("FiberQPlugin", "TelecomPlugin"):
        project.writeEntry(scope, "gpkg_path", str(target))
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface, FakePlugin(auto_save_on=True)), link / "fu8.gpkg")

    assert answer.asked == []
    assert _ids(target, "Poles") == [0, 1, 2]
    assert [note for note, _level, _duration in iface.bar.notes] == [
        "Saved next to a table of the same name: Poles → Poles_2."], "auto-save did not move"


def test_an_invalid_layer_whose_old_file_is_another_copy_keeps_every_table(
        iface, project, save_to, answer, modals, tmp_path):
    """n17: the project's "Poles 2024" read old-share/fu8.gpkg, whose file there
    is now an older copy without Poles: the layer is invalid, and the second
    round counted it as reading nothing -- its Poles, in the new copy, was offered."""
    import shutil

    old = tmp_path / "old-share"
    old.mkdir()
    _session_one(project, old / "fu8.gpkg", save_to, layers=(("Poles", 3),))
    project.addMapLayer(QgsVectorLayer(f"{old / 'fu8.gpkg'}|layername=Poles", "Poles 2024", "ogr"))
    try:
        assert project.write(str(tmp_path / "proj.qgs"))
        project.removeAllMapLayers()
        new = tmp_path / "new-share"
        shutil.copytree(str(old), str(new))
        os.rename(str(old / "fu8.gpkg"), str(old / "moved-away.gpkg"))
        _gdal_gpkg(old / "fu8.gpkg", {"Manholes": [1]})
        assert project.read(str(tmp_path / "proj.qgs"))
        for scope, key in ENTRIES:
            project.removeEntry(scope, key)
        assert [layer.isValid() for layer in project.mapLayers().values()] == [False]
        project.addMapLayer(_memory_layer("Poles", 1))
        answer.reply = export_manager.REPLACE

        save_to(ExportManager(iface), new / "fu8.gpkg")

        assert answer.asked == []
        assert _ids(new / "fu8.gpkg", "Poles") == [0, 1, 2]
    finally:
        project.clear()


def test_a_project_stored_in_the_file_keeps_every_table(iface, project, save_to, answer, modals, tmp_path):
    """n19: a QGIS project saved into the GeoPackage reads Poles; no layer of
    the project open now does, and the second round offered it."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    project.addMapLayer(QgsVectorLayer(f"{target}|layername=Poles", "Poles 2024", "ogr"))
    try:
        assert project.write(f"geopackage:{target}?projectName=survey2024")
        project.clear()
        fresh = _memory_layer("Poles", 1)
        project.addMapLayer(fresh)
        answer.reply = export_manager.REPLACE

        save_to(ExportManager(iface), target)

        assert answer.asked == []
        assert _ids(target, "Poles") == [0, 1, 2]
        assert fresh.source() == f"{target}|layername=Poles_2"
    finally:
        project.clear()


def test_a_geopackage_whose_header_says_0_is_saved_into(iface, project, save_to, answer, modals, tmp_path):
    """t1: a GeoPackage rebuilt from an SQL dump, application_id 0, which GDAL
    opens with a warning. The pre-flight refused it: nothing was saved."""
    target = tmp_path / "fu8.gpkg"
    _gdal_gpkg(target, {"Poles": [100, 101, 102]})
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("PRAGMA application_id = 0")
        conn.commit()
    layer = _memory_layer("Manholes", 1)
    project.addMapLayer(layer)

    save_to(ExportManager(iface), target)

    assert iface.bar.warnings == []
    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]
    assert _feature_tables(target) == {"Poles": 3, "Manholes": 1}
    assert layer.source() == f"{target}|layername=Manholes"


def _same_fid(name, count):
    """A temporary layer whose fid column holds one value ``count`` times: the GeoPackage writer refuses all but one."""
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=fid:integer&field=id:integer", name, "memory")
    layer.startEditing()
    for number in range(count):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(number, number)))
        feature.setAttributes([7, number])
        layer.addFeature(feature)
    assert layer.commitChanges()
    return layer


def test_a_save_that_fails_in_part_still_says_where_the_others_went(
        iface, project, save_to, answer, modals, logged, tmp_path):
    """The bar was told nothing but the failure: the note naming Poles_2, and
    the note that auto-save now writes to the file, went with the green line."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3), ("Manholes", 2)))
    for scope in ("FiberQPlugin", "TelecomPlugin"):
        project.writeEntry(scope, "gpkg_path", str(tmp_path / "fu4.gpkg"))
    poles = _memory_layer("Poles", 1)
    project.addMapLayer(poles)
    project.addMapLayer(_same_fid("Manholes", 3))
    answer.reply = export_manager.KEEP

    save_to(ExportManager(iface, FakePlugin(auto_save_on=True)), target)

    assert iface.bar.successes == []
    assert len(iface.bar.warnings) == 1 and iface.bar.warnings[0].startswith("Manholes: "), iface.bar.warnings
    assert poles.source() == f"{target}|layername=Poles_2"
    assert iface.bar.notes == [
        ("Auto-save now writes to fu8.gpkg.", Qgis.MessageLevel.Info, 0),
        ("Saved next to a table of the same name: Poles → Poles_2.", Qgis.MessageLevel.Info, 0)]
    assert [push[0] for push in iface.bar.pushed] == ["pushMessage", "pushMessage", "pushWarning"], (
        "the failure is pushed last, and so shown first")
    assert logged[-1] == (
        "Saved next to a table of the same name: Poles → Poles_2. Auto-save now writes to fu8.gpkg.",
        "FiberQ", Qgis.MessageLevel.Info)


def test_a_save_that_fails_in_part_logs_the_tables_it_replaced(
        iface, project, save_to, answer, modals, logged, tmp_path):
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3), ("Manholes", 2)))
    poles = _memory_layer("Poles", 1)
    project.addMapLayer(poles)
    project.addMapLayer(_same_fid("Manholes", 3))
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert iface.bar.successes == [] and iface.bar.notes == []
    assert iface.bar.warnings[0].startswith(
        "Manholes: not saved, and the old table Manholes was overwritten with only part of this layer: ")
    assert poles.source() == f"{target}|layername=Poles"
    assert logged[-1] == ("The old table Poles was replaced.", "FiberQ", Qgis.MessageLevel.Info)


# ---------------------------------------------------------------------------
# the fourth round: another file by the driver GDAL opens it with, no filter here
# ---------------------------------------------------------------------------
#
# The third round's review still found tables offered while a layer read them.
# Another file was judged by its name and a search for a VRT's words, and a
# GDAL pipeline (GDALG) or tile index (GTI) saved as .json or .tif passed for
# a plain file; and a filter on a layer of this file read another table
# without saying SELECT or FROM. Another file is now judged by the driver GDAL
# opens it with (export_manager._identify), and a layer of this file with any
# filter is not understood. The first five tests are that review's probes (a1,
# a1b, a2, a3; x6 is in test_gpkg_autosave.py) and show the data kept; the
# rest show what the allow-list still lets through.

#: Filters on Manholes that read Poles, saying neither SELECT nor FROM (review a1).
IN_TABLE = {
    "row_value_in_table": '("fid", "geom", "id") IN "Poles"',
    "row_value_in_main_table": '("fid", "geom", "id") IN main."Poles"',
    "not_in_table": 'NOT ("fid", "geom", "id") IN "Poles"',
}


@pytest.mark.parametrize("case", sorted(IN_TABLE))
def test_a_filter_that_reads_another_table_without_select_keeps_it(
        iface, project, save_to, answer, modals, tmp_path, case):
    """a1: SQLite reads a table through "x IN <table>". The filter on
    Manholes said neither SELECT nor FROM, Poles was offered, and Replace
    changed what the layer reads."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3), ("Manholes", 2)))
    reader = QgsVectorLayer(f"{target}|layername=Manholes|subset={IN_TABLE[case]}", "Manholes on poles", "ogr")
    assert reader.isValid()
    before = _reads(reader)
    assert before == ([] if case == "not_in_table" else [0, 1])
    project.addMapLayer(reader)
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == [], "Poles was offered while a filter reads it"
    assert _ids(target, "Poles") == [0, 1, 2]
    assert _reads(reader) == before
    assert fresh.source() == f"{target}|layername=Poles_2"
    assert iface.bar.successes == ["All layers saved to fu8.gpkg."]
    assert modals == []


def test_a_list_of_ids_a_filter_reads_is_kept(iface, project, save_to, answer, modals, tmp_path):
    """a1b: another program's one-column list of picked ids, registered as an
    attributes table, read by the filter "id" IN "Picked". Picked was offered
    to a new table of its name, and Replace emptied what the layer reads."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute('CREATE TABLE "Picked" (id INTEGER PRIMARY KEY)')
        conn.executemany('INSERT INTO "Picked" VALUES (?)', [(0,), (2,)])
        conn.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier) "
                     "VALUES ('Picked', 'attributes', 'Picked')")
        conn.commit()
    reader = QgsVectorLayer(f'{target}|layername=Poles|subset="id" IN "Picked"', "Picked poles", "ogr")
    assert reader.isValid()
    assert _reads(reader) == [0, 2]
    project.addMapLayer(reader)
    picked = QgsVectorLayer("None?field=id:integer", "Picked", "memory")
    picked.startEditing()
    feature = QgsFeature(picked.fields())
    feature.setAttribute("id", 1)
    picked.addFeature(feature)
    assert picked.commitChanges()
    project.addMapLayer(picked)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == [], "Picked was offered while a filter reads it"
    assert _ids(target, "Picked") == [0, 2]
    assert _reads(reader) == [0, 2]
    assert picked.source() == f"{target}|layername=Picked_2"
    assert modals == []


#: A GDAL raster tile index (GTI): its tiles are listed in a table of the
#: GeoPackage it names.
GTI = ("<GDALTileIndexDataset><IndexDataset>{target}</IndexDataset><IndexLayer>Tiles</IndexLayer>"
       "<LocationField>location</LocationField></GDALTileIndexDataset>")


def _tile_index(folder):
    """fu8.gpkg as gdaltindex leaves it -- a table Tiles listing one tile -- and the tile, a 4x4 raster of 7s."""
    from osgeo import gdal, ogr, osr

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    tile = folder / "tile.tif"
    raster = gdal.GetDriverByName("GTiff").Create(str(tile), 4, 4, 1, gdal.GDT_Byte)
    raster.SetGeoTransform([0, 1, 0, 4, 0, -1])
    raster.SetProjection(srs.ExportToWkt())
    raster.GetRasterBand(1).Fill(7)
    raster = None
    target = folder / "fu8.gpkg"
    source = ogr.GetDriverByName("GPKG").CreateDataSource(str(target))
    layer = source.CreateLayer("Tiles", srs, ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("location", ogr.OFTString))
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetField("location", str(tile))
    feature.SetGeometry(ogr.CreateGeometryFromWkt("POLYGON ((0 0,4 0,4 4,0 4,0 0))"))
    layer.CreateFeature(feature)
    source = layer = feature = None
    return target, tile


@pytest.mark.parametrize("extension", [".tif", ".json"])
def test_a_tile_index_under_a_plain_name_keeps_its_table(iface, project, save_to, answer, modals, tmp_path, extension):
    """a2: a GDAL tile index (GTI, GDAL 3.9 and later) saved as mosaic.tif or
    mosaic.json lists its tiles in Tiles, a table of the file. Taken for a
    plain raster by its name, it was said to read nothing of the file: Tiles
    was offered, and Replace left the mosaic unable to open."""
    from osgeo import gdal
    from qgis.core import QgsPointXY as Point, QgsRasterLayer

    if gdal.GetDriverByName("GTI") is None:
        pytest.skip(f"GDAL {gdal.__version__} has no tile index driver (GTI, GDAL 3.9 and later): "
                    "the mosaic does not open, and reads nothing")
    target, tile = _tile_index(tmp_path)
    mosaic = tmp_path / f"mosaic{extension}"
    mosaic.write_text(GTI.format(target=target), encoding="utf-8")
    reader = QgsRasterLayer(str(mosaic), "Mosaic", "gdal")
    assert reader.isValid()
    assert reader.dataProvider().sample(Point(1.5, 1.5), 1)[0] == 7
    project.addMapLayer(reader)
    fresh = QgsVectorLayer("Polygon?crs=EPSG:3857&field=id:integer", "Tiles", "memory")
    fresh.startEditing()
    feature = QgsFeature(fresh.fields())
    feature.setGeometry(QgsGeometry.fromWkt("POLYGON ((0 0, 1 0, 1 1, 0 0))"))
    feature.setAttribute("id", 0)
    fresh.addFeature(feature)
    assert fresh.commitChanges()
    project.addMapLayer(fresh)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == [], "Tiles was offered while a mosaic reads it"
    assert _ids(target, "Tiles", "location") == [str(tile)]
    again = QgsRasterLayer(str(mosaic), "Mosaic again", "gdal")
    assert again.isValid()
    assert again.dataProvider().sample(Point(1.5, 1.5), 1)[0] == 7
    assert fresh.source() == f"{target}|layername=Tiles_2"
    assert modals == []


@pytest.mark.parametrize("name", ["poles.gdalg.json", "poles.json"])
def test_a_gdal_pipeline_under_a_plain_name_keeps_the_table_it_reads(
        iface, project, save_to, answer, modals, tmp_path, name):
    """a3: a GDAL pipeline (GDALG, GDAL 3.11 and later; QGIS 4.2.3 with GDAL
    3.12.2 has it) is a .json file that QGIS opens as a vector layer reading
    the table it names. Taken for a plain .json by its name, it was said to
    read nothing of the file: Poles was offered, and Replace left the pipeline
    reading the new Poles."""
    from osgeo import gdal

    if gdal.GetDriverByName("GDALG") is None:
        pytest.skip(f"GDAL {gdal.__version__} has no pipeline driver (GDALG, GDAL 3.11 and later): "
                    "the pipeline does not open, and reads nothing")
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    pipeline = tmp_path / name
    pipeline.write_text(json.dumps({"type": "gdal_streamed_alg", "command_line":
                                    f"gdal vector pipeline read {target} --layer Poles ! reproject --dst-crs EPSG:4326"}),
                        encoding="utf-8")
    reader = QgsVectorLayer(str(pipeline), "Poles in 4326", "ogr")
    assert reader.isValid()
    assert _reads(reader) == [0, 1, 2]
    project.addMapLayer(reader)
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == [], "Poles was offered while a pipeline reads it"
    assert _ids(target, "Poles") == [0, 1, 2]
    assert _reads(QgsVectorLayer(str(pipeline), "Poles in 4326 again", "ogr")) == [0, 1, 2]
    assert fresh.source() == f"{target}|layername=Poles_2"
    assert modals == []


def _plain_file_layer(kind, folder):
    """A layer of the project on another file, of a plain single-file format: Roads, or a photo under the maps."""
    from osgeo import gdal, ogr, osr
    from qgis.core import QgsRasterLayer

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    if kind == "geotiff":
        path = folder / "photo.tif"
        raster = gdal.GetDriverByName("GTiff").Create(str(path), 4, 4, 1, gdal.GDT_Byte)
        raster.SetGeoTransform([0, 1, 0, 4, 0, -1])
        raster.SetProjection(srs.ExportToWkt())
        raster = None
        return QgsRasterLayer(str(path), "Photo", "gdal")
    driver, name = {"geojson": ("GeoJSON", "roads.geojson"), "geojson_filtered": ("GeoJSON", "roads.geojson"),
                    "shapefile": ("ESRI Shapefile", "roads.shp"), "other_geopackage": ("GPKG", "other.gpkg")}[kind]
    path = folder / name
    source = ogr.GetDriverByName(driver).CreateDataSource(str(path))
    layer = source.CreateLayer("Roads", srs, ogr.wkbPoint)
    layer.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
    for number in (5, 6):
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("id", number)
        feature.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({number} {number})"))
        layer.CreateFeature(feature)
    source = layer = feature = None
    uri = f"{path}|layername=Roads" if kind == "other_geopackage" else str(path)
    if kind == "geojson_filtered":
        uri += '|subset="id" > 5'
    return QgsVectorLayer(uri, "Roads", "ogr")


@pytest.mark.parametrize("kind", ["geojson", "geojson_filtered", "shapefile", "other_geopackage", "geotiff"])
def test_a_layer_on_another_plain_file_still_lets_the_question_be_asked(
        iface, project, save_to, answer, modals, tmp_path, kind):
    """The allow-list is not "never": a project with a layer on a file of a
    plain format -- a GeoJSON, filtered or not, a shapefile, another
    GeoPackage, a photo under the maps -- still gets the question, as GDAL
    opens that file with a driver that reads it alone, and Replace writes the
    new layer over the unused table."""
    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    folder = tmp_path / "elsewhere"
    folder.mkdir()
    other = _plain_file_layer(kind, folder)
    assert other.isValid(), kind
    project.addMapLayer(other)
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert [asked["offered"] for asked in answer.asked] == [["Poles"]]
    assert _ids(target, "Poles") == [0]
    assert fresh.source() == f"{target}|layername=Poles"
    assert iface.bar.warnings == []
    assert modals == []


def test_a_sql_filter_on_another_file_reading_this_one_keeps_its_table(
        iface, project, save_to, answer, modals, tmp_path):
    """Why a filter on another file still counts when it is SQL: GDAL runs a
    shapefile's filter through its own SQL, which reads a table of any file
    by its path -- this one's Poles, here (measured on 3.22.16 and 4.2.3)."""
    from osgeo import ogr, osr

    target = tmp_path / "fu8.gpkg"
    _session_one(project, target, save_to, layers=(("Poles", 3),))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    shapefile = tmp_path / "manholes.shp"
    source = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(shapefile))
    layer = source.CreateLayer("manholes", srs, ogr.wkbPoint)
    layer.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
    source = layer = None
    reader = QgsVectorLayer(str(shapefile), "Poles through a shapefile", "ogr")
    assert reader.setSubsetString(f"SELECT * FROM '{target}'.Poles")
    assert reader.isValid()
    assert _reads(reader) == [0, 1, 2]
    project.addMapLayer(reader)
    fresh = _memory_layer("Poles", 1)
    project.addMapLayer(fresh)
    answer.reply = export_manager.REPLACE

    save_to(ExportManager(iface), target)

    assert answer.asked == []
    assert _ids(target, "Poles") == [0, 1, 2]
    assert fresh.source() == f"{target}|layername=Poles_2"


def test_gdal_names_the_driver_of_a_file_by_what_it_holds(tmp_path):
    """export_manager._identify, as the plan asks it; and _reader's driver, the one an OGR layer opened its file with."""
    from osgeo import gdal

    geojson = tmp_path / "roads.geojson"
    geojson.write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")
    disguised = tmp_path / "poles.geojson"
    disguised.write_text(VRT.format(target=tmp_path / "fu8.gpkg"), encoding="utf-8")
    photo = tmp_path / "photo.tif"
    photo.write_text(GTI.format(target=tmp_path / "fu8.gpkg"), encoding="utf-8")

    assert export_manager._identify(geojson) == "GeoJSON"
    assert export_manager._identify(geojson, raster=True) is None
    assert export_manager._identify(disguised) == "OGR_VRT"
    assert export_manager._identify(photo, raster=True) == ("GTI" if gdal.GetDriverByName("GTI") else None)
    assert export_manager._identify(tmp_path / "missing.geojson") is None
    assert export_manager._reader(QgsVectorLayer(str(geojson), "Roads", "ogr"))[3] == "GeoJSON"
    assert export_manager._reader(_memory_layer("Poles", 1))[3] is None
