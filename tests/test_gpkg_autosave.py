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

import pytest
from qgis.core import (
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

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushSuccess(self, title, text):
        self.successes.append(text)

    def pushInfo(self, title, text):
        self.infos.append(text)


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
    return instance


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

    project.layerWasAdded.disconnect(ui._on_layer_added_auto_gpkg)


def test_ticking_the_box_does_not_claim_success_when_a_layer_failed(ui, core, project, tmp_path, monkeypatch):
    """The regression: green regardless of what happened to the layers.

    The target here passes the pre-flight and then fails anyway, because
    another program is holding the file. That is the case the pre-flight
    deliberately cannot see -- it is advisory, so each layer's own result still
    has to be checked.
    """
    project.addMapLayer(_memory_layer())
    target = tmp_path / "held.gpkg"
    _gpkg_layer(target, "Placeholder")
    monkeypatch.setattr(RoutingUI, "_project_gpkg_path", lambda self: str(target))

    holder = sqlite3.connect(str(target), isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        ui._toggle_auto_gpkg(True)
    finally:
        holder.execute("ROLLBACK")
        holder.close()

    assert core.bar.successes == [], "a failed conversion must not end in green"
    assert len(core.bar.warnings) == 1
    assert "Poles" in core.bar.warnings[0]

    project.layerWasAdded.disconnect(ui._on_layer_added_auto_gpkg)


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

    project.layerWasAdded.disconnect(ui._on_layer_added_auto_gpkg)


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


def test_a_new_project_with_no_target_unticks(ui, core, project):
    core.action_auto_gpkg.checked = True
    core.action_auto_gpkg.blocked = []

    ui.on_project_target_changed()

    assert core.action_auto_gpkg.checked is False


def test_a_project_that_has_a_target_leaves_the_tick_alone(ui, core, project, tmp_path):
    ui._set_project_gpkg_path(str(tmp_path / "auto.gpkg"))
    core.action_auto_gpkg.checked = True

    ui.on_project_target_changed()

    assert core.action_auto_gpkg.checked is True


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
