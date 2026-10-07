"""Save all layers to GeoPackage tells you when a layer did not make it.

WP4 4.2, item R1. Every one of these fails on v1.5.0, and they fail the same
way: the operation finishes, pushes *"All layers saved to: ..."* in green, and
the layer that did not make it is mentioned only in a debug log that a default
install never writes.

The one that matters most is
:func:`test_a_layer_whose_commit_fails_is_not_repointed`. Repointing a layer
whose commit has just been refused swaps the data source out from under edits
that exist only in the buffer -- the user's unsaved work, pointed at a file that
does not contain it. The old behaviour did that silently. The fix is to leave
such a layer completely alone, so its original source keeps the last good copy
and the edits stay in the buffer where the user can try again.
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

from fiberq.core.export_manager import ExportManager


class FakeBar:
    def __init__(self):
        self.warnings = []
        self.successes = []

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushSuccess(self, title, text):
        self.successes.append(text)

    def pushCritical(self, title, text):
        self.warnings.append(text)


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


@pytest.fixture
def iface():
    return FakeIface()


@pytest.fixture
def project():
    """The real QgsProject, emptied before and after.

    Layers must not outlive the test: a project torn down by the interpreter
    while it still owns layers is a reliable segfault on QGIS 4 (the same
    reason conftest.py's city fixture returns paths rather than a project).
    """
    def wipe(instance):
        instance.removeAllMapLayers()
        for scope in ("FiberQPlugin", "TelecomPlugin"):
            instance.removeEntry(scope, "gpkg_path")

    instance = QgsProject.instance()
    wipe(instance)
    yield instance
    wipe(instance)


def _memory_layer(name="Poles", count=1):
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


def _gpkg_layer(path, name, count=1):
    """A layer backed by a real GeoPackage on disk, added to nothing yet."""
    source = _memory_layer(name, count)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    options.actionOnExistingFile = (
        QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
        if os.path.exists(path)
        else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
    )
    code = QgsVectorFileWriter.writeAsVectorFormatV3(
        source, str(path), QgsCoordinateTransformContext(), options)[0]
    assert code == QgsVectorFileWriter.WriterError.NoError
    layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
    assert layer.isValid()
    return layer


def _block_inserts(path, table):
    """A GeoPackage that refuses every insert, the way a real trigger would."""
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            f"CREATE TRIGGER no_insert_{table} BEFORE INSERT ON {table} "
            f"BEGIN SELECT RAISE(ABORT, 'insert blocked'); END;")
        conn.commit()


def _tables(path):
    with sqlite3.connect(str(path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


@pytest.fixture
def save_to(monkeypatch, tmp_path):
    """Answer the file dialog with ``target``, then run Save all layers."""
    def run(manager, target):
        from fiberq.core import export_manager as module
        monkeypatch.setattr(
            module.QFileDialog, "getSaveFileName",
            staticmethod(lambda *args, **kwargs: (str(target), "")))
        manager.save_all_layers_to_gpkg()
    return run


# ---------------------------------------------------------------------------

def test_a_clean_export_says_so_once(iface, project, save_to, tmp_path):
    project.addMapLayer(_memory_layer("Poles"))
    project.addMapLayer(_memory_layer("Routes"))
    target = tmp_path / "out.gpkg"

    save_to(ExportManager(iface), target)

    assert iface.bar.warnings == []
    assert len(iface.bar.successes) == 1
    assert {"Poles", "Routes", "_fiberq_metadata"} <= _tables(target)


def test_a_layer_whose_commit_fails_is_not_repointed(iface, project, save_to, tmp_path):
    """The headline: do not swap the source out from under unsaved edits."""
    original = tmp_path / "original.gpkg"
    blocked = _gpkg_layer(original, "Poles")
    _block_inserts(original, "Poles")
    project.addMapLayer(blocked)
    project.addMapLayer(_memory_layer("Routes"))

    blocked.startEditing()
    pending = QgsFeature(blocked.fields())
    pending.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(9, 9)))
    pending.setAttribute("id", 99)
    blocked.addFeature(pending)

    target = tmp_path / "out.gpkg"
    save_to(ExportManager(iface), target)

    assert iface.bar.successes == [], "a refused commit must not end in green"
    assert len(iface.bar.warnings) == 1, "one line, however many layers failed"
    assert "Poles" in iface.bar.warnings[0]

    assert str(original) in blocked.source(), "the layer was repointed anyway"
    assert blocked.isEditable(), "the pending edit was thrown away"
    assert "Poles" not in _tables(target), "stale data reached the GeoPackage"
    assert "Routes" in _tables(target), "one bad layer stopped the others"

    blocked.rollBack()


def test_the_reason_a_layer_failed_is_in_the_message(iface, project, save_to, tmp_path):
    original = tmp_path / "original.gpkg"
    blocked = _gpkg_layer(original, "Poles")
    _block_inserts(original, "Poles")
    project.addMapLayer(blocked)

    blocked.startEditing()
    pending = QgsFeature(blocked.fields())
    pending.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(9, 9)))
    pending.setAttribute("id", 99)
    blocked.addFeature(pending)

    save_to(ExportManager(iface), tmp_path / "out.gpkg")

    assert "not added" in iface.bar.warnings[0], iface.bar.warnings
    blocked.rollBack()


def test_a_writer_that_cannot_write_names_the_layer(iface, project, save_to, tmp_path):
    """A target whose folder is not there -- a removed drive, a stale path."""
    project.addMapLayer(_memory_layer("Poles"))

    save_to(ExportManager(iface), tmp_path / "gone" / "out.gpkg")

    assert iface.bar.successes == []
    assert "Poles" in iface.bar.warnings[0]


def test_a_layer_that_cannot_be_reopened_is_reported(iface, project, save_to, tmp_path, monkeypatch):
    """setDataSource does not raise: a bad URI just leaves the layer invalid."""
    project.addMapLayer(_memory_layer("Poles"))
    monkeypatch.setattr(ExportManager, "_write_layer",
                        lambda self, layer, path, name, errors: True)

    save_to(ExportManager(iface), tmp_path / "never-written.gpkg")

    assert iface.bar.successes == []
    assert "Poles" in iface.bar.warnings[0]
    assert "reopened" in iface.bar.warnings[0]


def test_an_unregistered_metadata_table_is_a_failure(iface, tmp_path):
    """GDAL lists only what gpkg_contents registers, so an unregistered table
    is one FiberQ Designer cannot see -- which was the point of writing it.

    v1.5.0 swallowed that registration failure at debug level and carried on to
    push the green success message. Tested on the method, because a file with no
    gpkg_contents is not a GeoPackage and the writer refuses it long before the
    metadata step; what reaches the user is covered by the sqlite test below.
    """
    target = tmp_path / "not-really.gpkg"
    with sqlite3.connect(str(target)) as conn:
        conn.execute("CREATE TABLE decoy (id INTEGER)")
        conn.commit()

    written, reason = ExportManager(iface)._write_metadata_table(str(target))

    assert written is False
    assert "gpkg_contents" in reason


def test_a_missing_geopackage_is_reported_not_guessed_at(iface, tmp_path):
    written, reason = ExportManager(iface)._write_metadata_table(str(tmp_path / "nope.gpkg"))
    assert written is False
    assert "not there" in reason


def test_a_sqlite_failure_carries_sqlites_own_words(iface, project, save_to, tmp_path, monkeypatch):
    """_write_metadata_table imports sqlite3 inside itself, so patching the
    module object here reaches it: the local import binds the same object."""
    project.addMapLayer(_memory_layer("Poles"))

    real_connect = sqlite3.connect

    def refuse(path, *args, **kwargs):
        if str(path).endswith("out.gpkg"):
            raise sqlite3.OperationalError("attempt to write a readonly database")
        return real_connect(path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", refuse)
    save_to(ExportManager(iface), tmp_path / "out.gpkg")

    assert iface.bar.successes == []
    assert "readonly" in iface.bar.warnings[0]


def test_one_message_however_many_layers_failed(iface, project, save_to, tmp_path):
    for name in ("Poles", "Routes", "Cables"):
        project.addMapLayer(_memory_layer(name))

    save_to(ExportManager(iface), tmp_path / "gone" / "out.gpkg")

    assert len(iface.bar.warnings) == 1
    assert "more" in iface.bar.warnings[0], "the others must still be counted"


def test_saving_twice_to_the_same_file_is_not_an_error(iface, project, save_to, tmp_path):
    """The second Save all used to warn once per layer while the data was fine.

    Once a layer reads from the GeoPackage, committing its edits IS the save --
    and OGR refuses to overwrite a layer it has open ("Cannot overwrite an OGR
    layer in place"), so rewriting the table could never have worked anyway.
    Measured on v1.5.0 and on 3.44 and 4.0 alike: every layer warned, every
    time, on every project already living in a GeoPackage.
    """
    project.addMapLayer(_memory_layer("Poles"))
    project.addMapLayer(_memory_layer("Routes"))
    target = tmp_path / "out.gpkg"
    manager = ExportManager(iface)

    save_to(manager, target)
    assert len(iface.bar.successes) == 1 and iface.bar.warnings == []

    for layer in list(project.mapLayers().values()):
        layer.startEditing()
        extra = QgsFeature(layer.fields())
        extra.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(7, 7)))
        extra.setAttribute("id", 7)
        layer.addFeature(extra)
        assert layer.commitChanges()

    before = _tables(target)
    sources = {layer.name(): layer.source() for layer in project.mapLayers().values()}

    save_to(manager, target)

    assert iface.bar.warnings == [], iface.bar.warnings
    assert len(iface.bar.successes) == 2
    # No shadow tables: without the reuse rule the second save would add
    # Poles_2 and Routes_2 beside the originals and leave the layers pointing
    # at the new, half-empty ones.
    assert _tables(target) == before
    assert {layer.name(): layer.source() for layer in project.mapLayers().values()} == sources
    with sqlite3.connect(str(target)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM Poles").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM Routes").fetchone()[0] == 2


def test_two_layers_that_flatten_to_one_name_get_two_tables(iface, project, save_to, tmp_path):
    """"Poles" and "Poles!" are one GeoPackage table name; they must not share one."""
    project.addMapLayer(_memory_layer("Poles"))
    project.addMapLayer(_memory_layer("Poles!"))
    target = tmp_path / "out.gpkg"

    save_to(ExportManager(iface), target)

    assert iface.bar.warnings == []
    assert {"Poles", "Poles_2"} <= _tables(target)


def test_a_style_that_cannot_be_saved_is_reported(iface, project, save_to, tmp_path):
    """R2's "style-save error string used": that string was being discarded.

    ``saveStyleToDatabase`` does not raise and does not answer with a bool -- it
    returns the error message, empty on success. Nobody read it, so a
    GeoPackage whose ``layer_styles`` table rejects writes took the user's
    styling nowhere and said the export had gone fine. Measured on both stacks:
    the string is "Error looking for style. The query was logged".

    The data still reaches the file, so this is a warning and not a failure.
    """
    target = tmp_path / "out.gpkg"
    project.addMapLayer(_memory_layer("Poles"))
    save_to(ExportManager(iface), target)
    assert iface.bar.warnings == []

    with sqlite3.connect(str(target)) as conn:
        conn.execute("DROP TABLE IF EXISTS layer_styles")
        conn.execute("""CREATE TABLE layer_styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT,
            f_table_schema TEXT, f_table_name TEXT, f_geometry_column TEXT,
            styleName TEXT, styleQML TEXT, styleSLD TEXT, useAsDefault BOOLEAN,
            description TEXT, owner TEXT, ui TEXT, update_time DATETIME)""")
        conn.execute("CREATE TRIGGER no_style BEFORE INSERT ON layer_styles "
                     "BEGIN SELECT RAISE(ABORT, 'style rejected'); END;")
        conn.commit()

    iface.bar.warnings.clear()
    iface.bar.successes.clear()
    project.removeAllMapLayers()
    project.addMapLayer(_memory_layer("Routes"))

    save_to(ExportManager(iface), target)

    assert len(iface.bar.warnings) == 1, iface.bar.warnings
    assert "style was not saved" in iface.bar.warnings[0]
    assert "Routes" in iface.bar.warnings[0]
    with sqlite3.connect(str(target)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM Routes").fetchone()[0] == 1, (
            "a style failure must not cost the data")
