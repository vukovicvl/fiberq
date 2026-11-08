"""Auto-save to GeoPackage says when a layer did not get there.

WP4 4.2, item R2. Auto-save exists to rescue memory layers -- they hold their
features in RAM and lose them when the project closes -- so a conversion that
fails silently is the one failure mode that costs the user everything the layer
held.

On v1.5.0 both halves were silent. Ticking the box converted every memory layer
in a loop that discarded each result, then announced *"Autosave on GeoPackage."*
in green whether none, some or all of them had made it. The slot that catches
layers added afterwards wrapped its whole body in a debug-level swallow, so a
new layer that could not be written simply stayed in memory, and the user found
out when the project was reopened without it.

``RoutingUI`` builds a whole toolbar in ``__init__``, which these tests do not
need and cannot cheaply provide, so they construct the object with ``__new__``
and give it only what the two slots actually read. The code under test is the
real code.
"""
import os
import sqlite3
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

from fiberq.core.export_manager import export_one_layer_to_gpkg
from fiberq.ui.routing_ui import RoutingUI
from fiberq.utils.errors import OperationErrors


class FakeBar:
    def __init__(self):
        self.warnings = []
        self.successes = []
        self.infos = []
        #: What pushMessage was given: ``(text, level, duration)``.
        self.notes = []
        #: The heading of each push, in order.
        self.titles = []

    def pushWarning(self, title, text):
        self.warnings.append(text)
        self.titles.append(title)

    def pushSuccess(self, title, text):
        self.successes.append(text)
        self.titles.append(title)

    def pushInfo(self, title, text):
        self.infos.append(text)
        self.titles.append(title)

    def pushMessage(self, title, text, level=None, duration=-1):
        self.notes.append((text, level, duration))
        self.titles.append(title)


class FakeAction:
    def __init__(self):
        self.checked = True
        self.blocked = []

    def blockSignals(self, value):
        self.blocked.append(value)

    def setChecked(self, value):
        self.checked = value

    def isChecked(self):
        return self.checked


class FakeCore:
    def __init__(self):
        self.bar = FakeBar()
        self.action_auto_gpkg = FakeAction()
        self.iface = self

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


@pytest.fixture
def core():
    return FakeCore()


@pytest.fixture
def ui(core):
    """A RoutingUI with only what the auto-save slots read."""
    instance = RoutingUI.__new__(RoutingUI)
    instance.core = core
    instance._auto_gpkg_connected = False
    yield instance
    # In teardown, not at the end of each test: a failing assertion above the
    # disconnect would otherwise leak the connection into the next test and
    # turn one real failure into three.
    try:
        QgsProject.instance().layerWasAdded.disconnect(instance._on_layer_added_auto_gpkg)
    except TypeError:
        pass


@pytest.fixture
def project():
    """The real QgsProject, emptied of layers *and* of the auto-save entries.

    Project entries outlive removeAllMapLayers(), so a path written by one test
    would otherwise be read by the next and quietly change what it tested.
    """
    def wipe(instance):
        instance.removeAllMapLayers()
        for scope in ("FiberQPlugin", "TelecomPlugin"):
            instance.removeEntry(scope, "gpkg_path")

    instance = QgsProject.instance()
    wipe(instance)
    yield instance
    wipe(instance)


def _memory_layer(name="Poles"):
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer", name, "memory")
    layer.startEditing()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1, 1)))
    feature.setAttribute("id", 1)
    layer.addFeature(feature)
    assert layer.commitChanges()
    return layer


def _gpkg_layer(path, name):
    source = _memory_layer(name)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    options.actionOnExistingFile = (
        QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
        if os.path.exists(path)
        else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
    )
    assert QgsVectorFileWriter.writeAsVectorFormatV3(
        source, str(path), QgsCoordinateTransformContext(), options
    )[0] == QgsVectorFileWriter.WriterError.NoError
    layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
    assert layer.isValid()
    return layer


def _block_inserts(path, table):
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            f"CREATE TRIGGER no_insert_{table} BEFORE INSERT ON {table} "
            f"BEGIN SELECT RAISE(ABORT, 'insert blocked'); END;")
        conn.commit()


# ---------------------------------------------------------------------------
# export_one_layer_to_gpkg
# ---------------------------------------------------------------------------

def test_one_layer_converts_and_now_reads_from_the_geopackage(core, project, tmp_path):
    layer = _memory_layer()
    project.addMapLayer(layer)
    target = tmp_path / "auto.gpkg"

    assert export_one_layer_to_gpkg(layer, str(target), core.iface) is True
    assert str(target) in layer.source()
    assert core.bar.warnings == []


def test_a_layer_that_cannot_be_written_says_so_and_returns_false(core, project, tmp_path):
    layer = _memory_layer()
    project.addMapLayer(layer)

    assert export_one_layer_to_gpkg(layer, str(tmp_path / "gone" / "auto.gpkg"), core.iface) is False
    assert len(core.bar.warnings) == 1
    assert "Poles" in core.bar.warnings[0]
    assert layer.dataProvider().name() == "memory", (
        "a failed convert must leave the layer where it was")


def test_a_refused_commit_stops_the_convert(core, project, tmp_path):
    original = tmp_path / "original.gpkg"
    layer = _gpkg_layer(original, "Poles")
    _block_inserts(original, "Poles")
    project.addMapLayer(layer)

    layer.startEditing()
    pending = QgsFeature(layer.fields())
    pending.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(5, 5)))
    pending.setAttribute("id", 5)
    layer.addFeature(pending)

    assert export_one_layer_to_gpkg(layer, str(tmp_path / "auto.gpkg"), core.iface) is False
    # These two are what make this a test of R2's guard. Without them the whole
    # GeoPackage suite -- 45 tests -- still passed with that guard deleted
    # (measured): export_one_layer_to_gpkg answers False either way, because the
    # writer fails later on the same blocked insert. The guard's claim is that it
    # stops BEFORE the writer and says why.
    assert not os.path.exists(tmp_path / "auto.gpkg"), "it must stop before the writer, not after it"
    assert "insert blocked" in core.bar.warnings[0], core.bar.warnings
    assert str(original) in layer.source()
    assert layer.isEditable()
    layer.rollBack()


def test_a_shared_collector_gives_one_message_for_many_layers(core, project, tmp_path):
    """Auto-save converts a whole project at once; that is one message, not N."""
    layers = [_memory_layer(name) for name in ("Poles", "Routes", "Cables")]
    for layer in layers:
        project.addMapLayer(layer)
    target = str(tmp_path / "gone" / "auto.gpkg")

    with OperationErrors("Auto GPKG", core.iface) as errors:
        for layer in layers:
            assert export_one_layer_to_gpkg(layer, target, core.iface, errors) is False

    assert len(core.bar.warnings) == 1
    assert "more" in core.bar.warnings[0]


# ---------------------------------------------------------------------------
# the toolbar slots
# ---------------------------------------------------------------------------

def test_ticking_the_box_converts_and_reports_success(ui, core, project, tmp_path, monkeypatch):
    project.addMapLayer(_memory_layer())
    target = tmp_path / "auto.gpkg"
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))

    ui._toggle_auto_gpkg(True)

    assert core.bar.successes == ["Autosave on GeoPackage."]
    assert core.bar.warnings == []
    assert ui._auto_gpkg_connected is True


def test_ticking_the_box_does_not_claim_success_when_a_layer_failed(ui, core, project, tmp_path, monkeypatch):
    """The regression: green regardless of what happened to the layers.

    The target here passes the pre-flight and then fails anyway, because
    another program is holding the file. That is the case the pre-flight
    deliberately cannot see -- it is advisory, so each layer's own result still
    has to be checked. The program takes the file once the plan is made: held
    while the plan reads it, the save stops before anything is asked or
    written (v1.6.0 QA Q18, tests/test_gpkg_unused_tables.py).
    """
    from fiberq.core import export_manager

    project.addMapLayer(_memory_layer())
    target = tmp_path / "held.gpkg"
    _gpkg_layer(target, "Placeholder")
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))

    holder = sqlite3.connect(str(target), isolation_level=None)
    plan_gpkg_tables = export_manager.plan_gpkg_tables

    def plan_then_hold(*args, **kwargs):
        plan = plan_gpkg_tables(*args, **kwargs)
        holder.execute("BEGIN EXCLUSIVE")
        return plan

    monkeypatch.setattr(export_manager, "plan_gpkg_tables", plan_then_hold)
    try:
        ui._toggle_auto_gpkg(True)
    finally:
        if holder.in_transaction:
            holder.execute("ROLLBACK")
        holder.close()

    assert core.bar.successes == [], "a failed conversion must not end in green"
    assert len(core.bar.warnings) == 1
    assert "Poles" in core.bar.warnings[0]


def test_cancelling_the_file_dialog_unticks_the_box(ui, core, project, monkeypatch):
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: "")
    monkeypatch.setattr(RoutingUI, "_ask_for_auto_gpkg", lambda self, prj: "")

    ui._toggle_auto_gpkg(True)

    assert core.action_auto_gpkg.checked is False
    assert core.action_auto_gpkg.blocked == [True, False], "the slot must not re-enter"
    assert ui._auto_gpkg_connected is False


def test_a_new_layer_that_cannot_be_saved_is_reported(ui, core, project, tmp_path, monkeypatch):
    """v1.5.0 swallowed this whole slot, so the layer stayed in memory unsaid."""
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path",
                        lambda self: str(tmp_path / "gone" / "auto.gpkg"))
    layer = _memory_layer()
    project.addMapLayer(layer)

    assert ui._on_layer_added_auto_gpkg(layer) is False
    assert len(core.bar.warnings) == 1
    assert "Poles" in core.bar.warnings[0]


def test_a_new_layer_is_saved_without_a_word_when_it_works(ui, core, project, tmp_path, monkeypatch):
    target = tmp_path / "auto.gpkg"
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    layer = _memory_layer()
    project.addMapLayer(layer)

    assert ui._on_layer_added_auto_gpkg(layer) is True
    assert core.bar.warnings == []
    assert str(target) in layer.source()


def test_a_non_memory_layer_is_left_alone(ui, core, project, tmp_path, monkeypatch):
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(tmp_path / "auto.gpkg"))
    layer = _gpkg_layer(tmp_path / "already.gpkg", "Poles")
    project.addMapLayer(layer)

    assert ui._on_layer_added_auto_gpkg(layer) is None
    assert core.bar.warnings == []


def test_unticking_when_it_was_never_ticked_does_not_raise(ui, core, project):
    """Qt raises from disconnect() when nothing is connected, and never having
    switched auto-save on is the ordinary state, not an error."""
    ui._toggle_auto_gpkg(False)

    assert core.bar.infos == ["Autosave off."]
    assert core.bar.warnings == []


def test_unticking_after_ticking_disconnects(ui, core, project, tmp_path, monkeypatch):
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(tmp_path / "auto.gpkg"))
    ui._toggle_auto_gpkg(True)
    assert ui._auto_gpkg_connected is True

    ui._toggle_auto_gpkg(False)

    assert ui._auto_gpkg_connected is False
    assert core.bar.infos == ["Autosave off."]
    assert core.bar.warnings == []


# ---------------------------------------------------------------------------
# U6: the pre-flight, the two-key read and the overwrite guard
# ---------------------------------------------------------------------------

def test_save_all_seeds_the_path_auto_save_offers(ui, core, project, tmp_path):
    """Save all writes FiberQPlugin/gpkg_path; auto-save used to read only the
    older key, so picking a file in one never reached the other."""
    project.writeEntry("FiberQPlugin", "gpkg_path", str(tmp_path / "chosen.gpkg"))

    assert ui._project_gpkg_path() == str(tmp_path / "chosen.gpkg")


def test_a_project_from_an_older_version_still_works(ui, core, project, tmp_path):
    project.writeEntry("TelecomPlugin", "gpkg_path", str(tmp_path / "legacy.gpkg"))

    assert ui._project_gpkg_path() == str(tmp_path / "legacy.gpkg")


def test_setting_the_path_keeps_an_older_version_able_to_read_it(ui, project, tmp_path):
    ui._set_project_gpkg_path(str(tmp_path / "auto.gpkg"))

    assert project.readEntry("FiberQPlugin", "gpkg_path", "")[0] == str(tmp_path / "auto.gpkg")
    assert project.readEntry("TelecomPlugin", "gpkg_path", "")[0] == str(tmp_path / "auto.gpkg")


def test_a_stale_target_warns_once_and_then_asks(ui, core, project, tmp_path, monkeypatch):
    """A project carried to another machine: one sentence naming the path,
    instead of one raw OGR error per layer."""
    project.addMapLayer(_memory_layer())
    gone = tmp_path / "unplugged" / "auto.gpkg"
    ui._set_project_gpkg_path(str(gone))
    chosen = tmp_path / "chosen.gpkg"
    monkeypatch.setattr(RoutingUI, "_ask_for_auto_gpkg", lambda self, prj: str(chosen))

    ui._toggle_auto_gpkg(True)

    assert len(core.bar.warnings) == 1, core.bar.warnings
    assert str(gone) in core.bar.warnings[0]
    assert core.bar.successes == ["Autosave on GeoPackage."]
    assert ui._project_gpkg_path() == str(chosen)


def test_a_target_that_is_not_a_geopackage_warns(ui, core, project, tmp_path, monkeypatch):
    decoy = tmp_path / "notes.gpkg"
    decoy.write_bytes(b"not a database at all")
    ui._set_project_gpkg_path(str(decoy))
    monkeypatch.setattr(RoutingUI, "_ask_for_auto_gpkg", lambda self, prj: "")

    ui._toggle_auto_gpkg(True)

    assert len(core.bar.warnings) == 1
    assert "not a GeoPackage" in core.bar.warnings[0]
    assert core.action_auto_gpkg.checked is False


def test_no_target_at_all_asks_without_a_warning(ui, core, project, monkeypatch):
    """Having never chosen a file is not a problem worth a warning."""
    monkeypatch.setattr(RoutingUI, "_ask_for_auto_gpkg", lambda self, prj: "")

    ui._toggle_auto_gpkg(True)

    assert core.bar.warnings == []
    assert core.action_auto_gpkg.checked is False


def test_a_project_with_no_target_unticks_and_says_so(ui, core, project):
    core.action_auto_gpkg.checked = True
    core.action_auto_gpkg.blocked = []

    ui.settle_auto_gpkg()

    assert core.action_auto_gpkg.checked is False
    assert core.bar.infos == ["Autosave off: this project has no GeoPackage chosen yet."]


def test_a_project_that_has_a_target_leaves_the_tick_alone(ui, core, project, tmp_path):
    ui._set_project_gpkg_path(str(tmp_path / "auto.gpkg"))
    core.action_auto_gpkg.checked = True

    ui.settle_auto_gpkg()

    assert core.action_auto_gpkg.checked is True
    assert core.bar.infos == []


def test_opening_a_project_that_carries_a_target_keeps_auto_save_on(ui, core, project, tmp_path):
    """The bug this deferral exists for.

    QgsProject.cleared fires first on every open, with the old project's
    entries already gone and the new project's not yet read -- so a slot that
    decided there unticked auto-save on EVERY open, including one whose project
    carries a perfectly good target. New memory layers were then lost silently.
    Driven through the real signals, not by calling the slot.
    """
    from qgis.core import QgsApplication

    target = tmp_path / "auto.gpkg"
    ui._set_project_gpkg_path(str(target))
    saved = tmp_path / "carries-a-target.qgs"
    assert project.write(str(saved))

    core.action_auto_gpkg.checked = True
    ui._auto_gpkg_connected = True
    project.cleared.connect(ui.on_project_target_changed)
    project.readProject.connect(ui.on_project_target_changed)
    try:
        assert project.read(str(saved))
        QgsApplication.processEvents()
    finally:
        project.cleared.disconnect(ui.on_project_target_changed)
        project.readProject.disconnect(ui.on_project_target_changed)

    assert ui._project_gpkg_path() == str(target)
    assert core.action_auto_gpkg.checked is True, "auto-save was turned off on open"
    assert core.bar.infos == []


def test_file_new_still_unticks(ui, core, project):
    """File > New emits cleared and no readProject, so the deferral must still fire."""
    from qgis.core import QgsApplication

    core.action_auto_gpkg.checked = True
    project.cleared.connect(ui.on_project_target_changed)
    try:
        project.clear()
        QgsApplication.processEvents()
    finally:
        project.cleared.disconnect(ui.on_project_target_changed)

    assert core.action_auto_gpkg.checked is False
    assert core.bar.infos == ["Autosave off: this project has no GeoPackage chosen yet."]


def test_a_second_layer_of_the_same_name_does_not_overwrite_the_first(core, project, tmp_path):
    """Measured on v1.5.0: three features in, one feature out, NoError, no warning."""
    target = tmp_path / "auto.gpkg"
    first = _memory_layer("Poles")
    first.startEditing()
    for number in (2, 3):
        extra = QgsFeature(first.fields())
        extra.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(number, number)))
        extra.setAttribute("id", number)
        first.addFeature(extra)
    assert first.commitChanges()
    project.addMapLayer(first)
    assert export_one_layer_to_gpkg(first, str(target), core.iface) is True
    first.setName("Poles 2024")

    second = _memory_layer("Poles")
    project.addMapLayer(second)
    assert export_one_layer_to_gpkg(second, str(target), core.iface) is True

    with sqlite3.connect(str(target)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM Poles").fetchone()[0] == 3, (
            "the first layer's features were overwritten")
        assert conn.execute("SELECT COUNT(*) FROM Poles_2").fetchone()[0] == 1


def test_a_layer_already_in_the_geopackage_is_not_converted_again(ui, core, project, tmp_path, monkeypatch):
    """Auto-save rescues memory layers; one already on disk needs no rescue.

    This is also why the table-reuse rule in gpkg_target is never exercised by
    auto-save itself: a converted layer stops being a memory layer, so the
    layerWasAdded hook ignores it from then on.
    """
    target = tmp_path / "auto.gpkg"
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    layer = _memory_layer("Poles")
    project.addMapLayer(layer)

    assert ui._on_layer_added_auto_gpkg(layer) is True
    assert layer.dataProvider().name() == "ogr"

    assert ui._on_layer_added_auto_gpkg(layer) is None, "a converted layer was converted again"


# ---------------------------------------------------------------------------
# v1.6.0 QA Q18: unused tables of the same names
# ---------------------------------------------------------------------------
#
# Auto-save into an existing file did what Save all did: the first session's
# Scratch_A, read by no layer any more, was kept and the new Scratch A went to
# Scratch_A_2 without a word. Ticking the box now asks FiberQ's question, as
# Save all does. A layer added later is never asked about -- a modal inside
# layerWasAdded would stop whatever is adding the layer -- and one line says
# where it went.

@pytest.fixture
def modals():
    """Modal dialogs that open, closed (No) and recorded instead of waited on.

    QGIS 3.22 answers saveStyleToDatabase over an existing default style with a
    modal "overwrite it?"; headless, nothing would answer it.
    """
    from qgis.PyQt.QtCore import QTimer
    from qgis.PyQt.QtWidgets import QApplication, QMessageBox

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
    from fiberq.core import export_manager

    class Answer:
        reply = None

        def __init__(self):
            self.asked = []

        def __call__(self, parent, title, gpkg_path, plan):
            self.asked.append({"title": title, "offered": list(plan.offered)})
            return self.reply

    recorder = Answer()
    # raising=False: the function is this change's; before it, nothing asked.
    monkeypatch.setattr(export_manager, "ask_about_unused_tables", recorder, raising=False)
    return recorder


def _scratch_saved_earlier(project, core, target):
    """The first session: auto-save put Scratch A, two features, in ``target``. Then a restart."""
    earlier = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer", "Scratch A", "memory")
    earlier.startEditing()
    for number in (1, 2):
        feature = QgsFeature(earlier.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(number, number)))
        earlier.addFeature(feature)
    assert earlier.commitChanges()
    project.addMapLayer(earlier)
    assert export_one_layer_to_gpkg(earlier, str(target), core.iface) is True
    project.removeAllMapLayers()


def _feature_tables(path):
    with closing(sqlite3.connect(str(path))) as conn:
        names = [row[0] for row in conn.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'")]
        return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}


def test_ticking_the_box_asks_about_an_unused_table_first(ui, core, project, answer, modals, tmp_path, monkeypatch):
    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    layer = _memory_layer("Scratch A")
    project.addMapLayer(layer)
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    answer.reply = "replace"

    ui._toggle_auto_gpkg(True)

    assert answer.asked == [{"title": "Auto save to GeoPackage", "offered": ["Scratch_A"]}]
    assert _feature_tables(target) == {"Scratch_A": 1}, "the old table was kept, or kept beside"
    assert layer.source() == f"{target}|layername=Scratch_A"
    with closing(sqlite3.connect(str(target))) as conn:
        styles = conn.execute("SELECT styleName FROM layer_styles WHERE f_table_name = 'Scratch_A'").fetchall()
    assert styles == [("default",)]
    assert core.bar.successes == ["Autosave on GeoPackage. The old table Scratch_A was replaced."]
    assert core.bar.notes == []
    assert core.bar.warnings == []
    assert ui._auto_gpkg_connected is True
    assert modals == []


def test_keeping_the_unused_table_says_where_the_layer_went(ui, core, project, answer, tmp_path, monkeypatch):
    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    project.addMapLayer(_memory_layer("Scratch A"))
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    answer.reply = "keep"

    ui._toggle_auto_gpkg(True)

    assert len(answer.asked) == 1
    assert _feature_tables(target) == {"Scratch_A": 2, "Scratch_A_2": 1}
    assert core.bar.successes == ["Autosave on GeoPackage."]
    assert core.bar.notes == [("Saved next to a table of the same name: Scratch A → Scratch_A_2.",
                               Qgis.MessageLevel.Info, 0)]


def test_cancelling_the_question_leaves_auto_save_off(ui, core, project, answer, tmp_path, monkeypatch):
    """The file was chosen in the dialog just now; Cancel must not store it either."""
    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    layer = _memory_layer("Scratch A")
    project.addMapLayer(layer)
    monkeypatch.setattr(RoutingUI, "_ask_for_auto_gpkg", lambda self, prj: str(target))
    with open(target, "rb") as handle:
        before = handle.read()
    answer.reply = None

    ui._toggle_auto_gpkg(True)

    assert len(answer.asked) == 1, "the test must reach the question to test its Cancel"
    with open(target, "rb") as handle:
        assert handle.read() == before, "Cancel wrote to the file"
    assert layer.dataProvider().name() == "memory"
    assert project.readEntry("FiberQPlugin", "gpkg_path", "") == ("", False)
    assert project.readEntry("TelecomPlugin", "gpkg_path", "") == ("", False)
    assert core.action_auto_gpkg.checked is False
    assert ui._auto_gpkg_connected is False
    assert core.bar.successes == [] and core.bar.warnings == []


def test_a_layer_added_later_with_a_taken_name_is_told_not_asked(ui, core, project, answer, modals, tmp_path,
                                                                 monkeypatch):
    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    layer = _memory_layer("Scratch A")
    project.addMapLayer(layer)
    answer.reply = "replace"

    assert ui._on_layer_added_auto_gpkg(layer) is True

    assert answer.asked == [], "no question inside layerWasAdded"
    assert modals == []
    assert _feature_tables(target) == {"Scratch_A": 2, "Scratch_A_2": 1}
    assert core.bar.notes == [
        ("Scratch A is stored as table Scratch_A_2, because fu4.gpkg already has a table named Scratch_A.",
         Qgis.MessageLevel.Info, 0)], "a line of its own that stays until closed, like Save all's"
    assert core.bar.infos == [] and core.bar.warnings == []


def test_a_layer_added_later_under_its_own_name_says_nothing(ui, core, project, answer, tmp_path, monkeypatch):
    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    layer = _memory_layer("Poles")
    project.addMapLayer(layer)

    assert ui._on_layer_added_auto_gpkg(layer) is True

    assert core.bar.infos == [] and core.bar.warnings == []
    assert layer.source() == f"{target}|layername=Poles"


def test_the_auto_save_file_dialog_does_not_ask_to_replace(ui, project, monkeypatch, tmp_path):
    from qgis.PyQt.QtWidgets import QFileDialog

    calls = []

    def dialog(*args, **kwargs):
        calls.append((args, kwargs))
        return str(tmp_path / "auto.gpkg"), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(dialog))

    assert ui._ask_for_auto_gpkg(project) == str(tmp_path / "auto.gpkg")

    no_confirm = getattr(getattr(QFileDialog, "Option", QFileDialog), "DontConfirmOverwrite")
    args, kwargs = calls[0]
    options = args[5] if len(args) > 5 else kwargs.get("options")
    assert options is not None, f"no options passed to the file dialog: {args}"
    assert options == no_confirm


# ---------------------------------------------------------------------------
# v1.6.0 QA Q18, second round
# ---------------------------------------------------------------------------

def test_ticking_the_box_offers_no_table_a_layer_reads_through_a_symlink(
        ui, core, project, answer, modals, tmp_path, monkeypatch):
    """Review p13: "Scratch kept" reads Scratch_A through a symlinked folder.
    As strings the paths differed, Scratch_A was offered, and Replace wrote the
    new Scratch A over what that layer reads."""
    real = tmp_path / "real"
    real.mkdir()
    target = real / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    link = tmp_path / "link"
    os.symlink(str(real), str(link))
    reader = QgsVectorLayer(f"{link / 'fu4.gpkg'}|layername=Scratch_A", "Scratch kept", "ogr")
    assert reader.isValid()
    project.addMapLayer(reader)
    layer = _memory_layer("Scratch A")
    project.addMapLayer(layer)
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    answer.reply = "replace"

    ui._toggle_auto_gpkg(True)

    assert answer.asked == []
    assert _feature_tables(target) == {"Scratch_A": 2, "Scratch_A_2": 1}
    assert layer.source() == f"{target}|layername=Scratch_A_2"
    assert core.bar.successes == ["Autosave on GeoPackage."]
    assert [note for note, _level, _duration in core.bar.notes] == [
        "Saved next to a table of the same name: Scratch A → Scratch_A_2."]


def test_the_question_is_titled_with_the_auto_save_buttons_own_words(
        ui, core, project, answer, tmp_path, monkeypatch):
    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    project.addMapLayer(_memory_layer("Scratch A"))
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    core.action_auto_gpkg.text = lambda: "Sauvegarde &automatique"
    answer.reply = None

    ui._toggle_auto_gpkg(True)

    assert [asked["title"] for asked in answer.asked] == ["Sauvegarde automatique"]
    assert core.action_auto_gpkg.checked is False, "Cancel leaves it off"


def test_a_chosen_file_that_is_not_a_geopackage_is_said_before_anything_is_written(
        ui, core, project, answer, tmp_path, monkeypatch):
    """The stored path had its pre-flight (U6); a file chosen in the dialog had
    none, and every layer failed on it one by one."""
    decoy = tmp_path / "notes.gpkg"
    decoy.write_bytes(b"not a database at all")
    layer = _memory_layer()
    project.addMapLayer(layer)
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: "")
    monkeypatch.setattr(RoutingUI, "_ask_for_auto_gpkg", lambda self, prj: str(decoy))

    ui._toggle_auto_gpkg(True)

    assert core.bar.warnings == ["notes.gpkg is not a GeoPackage. Nothing was saved."]
    assert core.bar.titles == ["Auto GPKG"]
    assert core.action_auto_gpkg.checked is False
    assert layer.dataProvider().name() == "memory"
    assert project.readEntry("FiberQPlugin", "gpkg_path", "") == ("", False)
    assert decoy.read_bytes() == b"not a database at all"


def test_a_layer_added_later_is_not_written_when_the_files_tables_cannot_be_read(
        ui, core, project, modals, tmp_path, monkeypatch):
    """Read as none, every name in the file looked free, and the writer
    replaces the table whose name it is given: a moment's lock on the file, gone
    by the time the writer opened it, was enough for a new Poles to go over the
    old one -- and on QGIS 3.22 to open its "overwrite the style?" box, which
    the watcher closes and records rather than waits on. The message is a
    sentence of its own: the layer was not saved and is still temporary."""
    from fiberq.core import gpkg_target

    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)    # Scratch_A, two features
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    layer = _memory_layer("Scratch A")
    project.addMapLayer(layer)

    def unreadable(path):
        raise sqlite3.OperationalError("database is locked")

    # Only the read of the table names fails: the writer itself gets in.
    monkeypatch.setattr(gpkg_target, "_read_only", unreadable, raising=False)
    monkeypatch.setattr(gpkg_target, "existing_tables", lambda path: set())

    assert ui._on_layer_added_auto_gpkg(layer) is False

    assert modals == [], "a box opened"
    assert core.bar.warnings == [
        "Scratch A was not saved: the tables of fu4.gpkg could not be read (OperationalError: database is locked). "
        "It is still a temporary layer."]
    assert core.bar.titles == ["Auto GPKG"]
    assert layer.dataProvider().name() == "memory"
    assert _feature_tables(target) == {"Scratch_A": 2}, "the old Scratch_A was written over"


# ---------------------------------------------------------------------------
# v1.6.0 QA Q18, third round
# ---------------------------------------------------------------------------

def test_turning_auto_save_on_holds_the_layer_hook_while_it_asks_and_writes(
        ui, core, project, answer, tmp_path, monkeypatch):
    """A layer added meanwhile reaches the hook, which would write it into the
    file the question is about; the hook waits (export_manager.hold_auto_save),
    and is let go when the toggle is done."""
    from fiberq.core import export_manager

    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    project.addMapLayer(_memory_layer("Scratch A"))
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    held = []

    def ask(parent, title, gpkg_path, plan):
        held.append(export_manager.auto_save_held())
        return "keep"

    monkeypatch.setattr(export_manager, "ask_about_unused_tables", ask)

    ui._toggle_auto_gpkg(True)

    assert held == [True]
    assert not export_manager.auto_save_held()
    assert ui._auto_gpkg_connected is True


def test_turning_auto_save_on_into_a_file_that_changed_meanwhile_writes_nothing(
        ui, core, project, tmp_path, monkeypatch):
    """Review f2: a layer reading Scratch_A was added while the question was
    open, and Replace wrote over what it reads."""
    from fiberq.core import export_manager

    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    layer = _memory_layer("Scratch A")
    project.addMapLayer(layer)
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    added = []

    def ask(parent, title, gpkg_path, plan):
        reader = QgsVectorLayer(f"{target}|layername=Scratch_A", "Scratch kept", "ogr")
        project.addMapLayer(reader)
        added.append(reader)
        return "replace"

    monkeypatch.setattr(export_manager, "ask_about_unused_tables", ask)

    ui._toggle_auto_gpkg(True)

    assert core.bar.warnings == ["fu4.gpkg or this project changed while the question was open. Nothing was saved."]
    assert core.bar.titles == ["Auto GPKG"]
    assert core.action_auto_gpkg.checked is False
    assert layer.dataProvider().name() == "memory"
    assert _feature_tables(target) == {"Scratch_A": 2}
    assert added[0].featureCount() == 2


def test_a_conversion_that_fails_in_part_still_says_where_the_others_went(
        ui, core, project, answer, modals, tmp_path, monkeypatch):
    """The failure has the bar; the note that Scratch A went beside the old
    table was dropped with the green line."""
    target = tmp_path / "fu4.gpkg"
    _scratch_saved_earlier(project, core, target)
    scratch = _memory_layer("Scratch A")
    project.addMapLayer(scratch)
    bad = QgsVectorLayer("Point?crs=EPSG:3857&field=fid:integer", "Manholes", "memory")
    bad.startEditing()
    for number in range(3):
        feature = QgsFeature(bad.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(number, number)))
        feature.setAttributes([7])
        bad.addFeature(feature)
    assert bad.commitChanges()
    project.addMapLayer(bad)
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    answer.reply = "keep"

    ui._toggle_auto_gpkg(True)

    assert core.bar.successes == []
    assert len(core.bar.warnings) == 1 and core.bar.warnings[0].startswith("Manholes: "), core.bar.warnings
    assert scratch.source() == f"{target}|layername=Scratch_A_2"
    assert core.bar.notes == [("Saved next to a table of the same name: Scratch A → Scratch_A_2.",
                               Qgis.MessageLevel.Info, 0)]
    assert modals == []


def test_a_geopackage_whose_header_says_0_is_an_auto_save_target(ui, core, project, tmp_path, monkeypatch):
    """Review t1, in auto-save's own pre-flight: a GeoPackage rebuilt from an
    SQL dump carries application_id 0, and the stored file was refused as "not
    a GeoPackage"."""
    target = tmp_path / "dumped.gpkg"
    _gpkg_layer(target, "Poles")
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("PRAGMA application_id = 0")
        conn.commit()
    ui._set_project_gpkg_path(str(target))
    layer = _memory_layer("Scratch A")
    project.addMapLayer(layer)
    monkeypatch.setattr(RoutingUI, "_ask_for_auto_gpkg", lambda self, prj: pytest.fail("asked for another file"))

    ui._toggle_auto_gpkg(True)

    assert core.bar.warnings == []
    assert core.bar.successes == ["Autosave on GeoPackage."]
    assert layer.source() == f"{target}|layername=Scratch_A"


# ---------------------------------------------------------------------------
# v1.6.0 QA Q18, fourth round
# ---------------------------------------------------------------------------

def test_ticking_the_box_offers_no_table_a_filter_reads(ui, core, project, answer, modals, tmp_path, monkeypatch):
    """Review x6: Save all's a1 through the other door. "B also in A" reads
    Scratch_B filtered by ("fid", "geom", "id") IN "Scratch_A" -- SQLite reads
    Scratch_A without the filter saying SELECT or FROM. Scratch_A was offered,
    and Replace emptied what the layer reads."""
    target = tmp_path / "fu4.gpkg"
    for name in ("Scratch A", "Scratch B"):
        earlier = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer", name, "memory")
        earlier.startEditing()
        for number in (100, 101):
            feature = QgsFeature(earlier.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(number, number)))
            feature.setAttribute("id", number)
            earlier.addFeature(feature)
        assert earlier.commitChanges()
        project.addMapLayer(earlier)
        assert export_one_layer_to_gpkg(earlier, str(target), core.iface) is True
    project.removeAllMapLayers()
    reader = QgsVectorLayer(f'{target}|layername=Scratch_B|subset=("fid", "geom", "id") IN "Scratch_A"',
                            "B also in A", "ogr")
    assert reader.isValid()
    assert sorted(feature["id"] for feature in reader.getFeatures()) == [100, 101]
    project.addMapLayer(reader)
    layer = _memory_layer("Scratch A")
    project.addMapLayer(layer)
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))
    answer.reply = "replace"

    ui._toggle_auto_gpkg(True)

    assert answer.asked == [], "Scratch_A was offered while a filter reads it"
    assert _feature_tables(target) == {"Scratch_A": 2, "Scratch_B": 2, "Scratch_A_2": 1}
    assert layer.source() == f"{target}|layername=Scratch_A_2"
    reader.dataProvider().reloadData()
    assert sorted(feature["id"] for feature in reader.getFeatures()) == [100, 101]
    assert core.bar.successes == ["Autosave on GeoPackage."]
    assert modals == []
