"""Undo said "Undone" for work that never left the edit buffer.

WP4 4.2 item R7, the undo/redo half. Branch ``fix/wp4-write-paths``.

``FiberQUndoManager`` is a stack of its own, separate from QGIS's Ctrl+Z, and it
decided every operation had succeeded on the strength of a **buffer** write.
Measured on 3.22.16, 3.44.15 and 4.0.3 with a GeoPackage trigger refusing the
write:

* ``_delete_feature`` answered True -- ``deleteFeature`` succeeded, the commit
  did not -- so ``undo()`` pushed "Undone: Added p1 (poles)" and repainted the
  canvas while the row was still in the file. It came back on the next open.
* ``_add_feature`` answered ``-2``, a buffer-only feature id. ``undo()``'s
  ``if new_fid is not None`` was satisfied, it set ``op.feature_id = -2``, and a
  later redo operated on fid -2.
* ``_restore_feature`` discarded ``changeGeometry``, discarded every
  ``changeAttributeValue``, discarded ``commitChanges`` and then
  ``return True`` unconditionally. The stack then believed a feature was in its
  old state while the file held the new one, so the next undo of that feature
  worked from a baseline that had never existed.

**And one failure poisoned the whole session.** This is the sharpest of them and
it has its own test below. ``_ensure_editable`` read ``isEditable()`` as
"somebody else owns this session, do not commit" -- right for a session the user
opened, wrong for one this manager's own refused commit left open. Measured::

    undo 1, DELETE trigger refusing
        deleteFeature -> True, commitChanges -> False,
        helper answered True, layer left editable, row still on disk
    the trigger is dropped -- the provider would now accept a delete
    undo 2
        answered True, attempted NO commit at all, row still on disk

So after one failure no later undo in the session ever committed again, long
after the cause was gone.

Separately, a failed undo was dropped from **both** stacks with nothing said:
``op`` is popped before the write, ``success`` stayed False, and the only
message-bar push sat inside the success branch. Press undo, nothing happens and
nothing is said; press undo again expecting the same operation and you undo the
one before it instead.

Every assertion here reads the GeoPackage from disk or straight out of SQLite.
``getFeatures()`` reads through the edit buffer and would have agreed with the
bug.

Nine of the twelve tests go red against a tree with only this fix reverted. The
three that do not are marked **characterisation** in their own docstrings: two
are the ordinary undo and redo, which always worked, and one guards the new
push-back rule against keeping operations that can never succeed.
"""
import os
import sqlite3

import pytest
from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from fiberq.core.undo_manager import FiberQUndoManager, OpType


class FakeBar:
    def __init__(self):
        self.infos = []
        self.warnings = []

    def pushInfo(self, title, text):
        self.infos.append(text)

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushSuccess(self, title, text):
        self.infos.append(text)

    def pushCritical(self, title, text):
        self.warnings.append(text)


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture
def manager():
    return FiberQUndoManager(FakeIface())


def _poles(path, names=("p0", "p1", "p2")):
    mem = QgsVectorLayer("Point?crs=EPSG:3857", "Poles", "memory")
    mem.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    mem.updateFields()
    for i, name in enumerate(names):
        feature = QgsFeature(mem.fields())
        feature.setGeometry(QgsGeometry.fromWkt(f"Point ({i} 0)"))
        feature.setAttribute("naziv", name)
        assert mem.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Poles"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem, path, QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    layer = QgsVectorLayer(f"{path}|layername=Poles", "Poles", "ogr")
    assert layer.isValid()
    return layer


def _block(path, operation):
    con = sqlite3.connect(path)
    con.execute(f'''CREATE TRIGGER fiberq_no_{operation} BEFORE {operation.upper()} ON "Poles"
                    BEGIN SELECT RAISE(ABORT, 'FiberQ test: {operation}s blocked'); END;''')
    con.commit()
    con.close()


def _unblock(path, operation):
    con = sqlite3.connect(path)
    con.execute(f"DROP TRIGGER fiberq_no_{operation}")
    con.commit()
    con.close()


def _names(path):
    con = sqlite3.connect(path)
    try:
        return sorted(str(row[0]) for row in con.execute('SELECT naziv FROM "Poles"'))
    finally:
        con.close()


def _record_add(manager, layer, fid):
    """Put an ADD operation on the stack, as a placement tool would."""
    feature = layer.getFeature(fid)
    assert feature.isValid()
    manager.record_add(layer, feature)
    assert manager.can_undo()


# ---------------------------------------------------------------------------
# the session poisoning
# ---------------------------------------------------------------------------

def test_one_refused_undo_does_not_stop_every_later_undo_committing(
        manager, project, tmp_path):
    """**The one that matters most here.**

    Before the fix the second undo never even attempted a commit, because the
    first failure had left the layer editable and ``_ensure_editable`` read
    that as somebody else's session.
    """
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)
    _block(path, "delete")

    _record_add(manager, layer, 1)
    assert manager.undo() is False, "the refused commit must not be reported as success"
    assert _names(path) == ["p0", "p1", "p2"], "nothing should have left the file"

    # The cause is cleared -- exactly what a user does after reading the message.
    _unblock(path, "delete")

    _record_add(manager, layer, 2)
    assert manager.undo() is True, (
        "the second undo must commit now that the cause is gone; before the fix "
        "it answered True while attempting no commit at all")
    assert "p1" not in _names(path), (
        f"the second undo reported success and changed nothing on disk: {_names(path)}")


def test_a_refused_undo_is_not_reported_as_done(manager, project, tmp_path):
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)
    _block(path, "delete")

    _record_add(manager, layer, 1)
    manager.undo()

    assert not any("Undone" in text for text in manager.iface.bar.infos), (
        f"a refused undo claimed to be done: {manager.iface.bar.infos}")
    assert manager.iface.bar.warnings, "nothing at all was said about the refusal"


def test_a_recoverable_undo_stays_on_the_stack(manager, project, tmp_path):
    """Dropped from both stacks before the fix, so pressing undo again undid the
    operation BEFORE it -- two presses, one visible effect, no explanation.

    ``isModified()`` is the discriminator and it is measured: True after a
    refused commit because the edit is still buffered, so a retry has something
    to save.
    """
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)
    _block(path, "delete")

    _record_add(manager, layer, 1)
    assert manager.undo() is False
    assert manager.can_undo(), (
        "the operation was dropped, so the next undo would silently apply to a "
        "different operation")
    assert not manager.can_redo(), "a failed undo must not become redoable"
    assert any("undo again" in text or "left on the undo list" in text
               for text in manager.iface.bar.warnings), manager.iface.bar.warnings


def test_an_undo_that_cannot_ever_work_is_still_dropped(manager, project, tmp_path):
    """The other half of the pair. A feature deleted outside FiberQ is not
    recoverable by retrying, and keeping it would block the stack forever.

    **Characterisation, not proof.** It passes against the pre-fix code, which
    dropped everything indiscriminately. Its job is to stop the new push-back
    rule keeping operations that can never succeed.
    """
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)

    _record_add(manager, layer, 1)
    con = sqlite3.connect(path)
    con.execute('DELETE FROM "Poles" WHERE fid = 1')
    con.commit()
    con.close()
    layer.reload()

    assert manager.undo() is False
    assert not manager.can_undo(), "a hopeless operation must not block the stack"


# ---------------------------------------------------------------------------
# the three helpers
# ---------------------------------------------------------------------------

def test_undoing_an_add_does_not_claim_a_delete_that_was_refused(
        manager, project, tmp_path):
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)
    _block(path, "delete")

    _record_add(manager, layer, 1)
    assert manager.undo() is False
    assert _names(path) == ["p0", "p1", "p2"]


def test_undoing_a_delete_does_not_report_a_buffer_only_feature_id(
        manager, project, tmp_path):
    """Measured: ``_add_feature`` answered -2, a buffer-only id, and ``undo()``
    wrote that into ``op.feature_id`` and pushed the op to the redo stack."""
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)

    feature = layer.getFeature(1)
    manager.record_delete(layer, feature)
    layer.startEditing()
    layer.deleteFeature(1)
    layer.commitChanges()
    assert "p0" not in _names(path)

    _block(path, "insert")
    assert manager.undo() is False, "a refused insert must not be reported as undone"
    assert not manager.can_redo(), "nothing reached the file, so there is nothing to redo"
    for op in list(manager._undo_stack) + list(manager._redo_stack):
        assert op.feature_id is None or op.feature_id >= 0, (
            f"a buffer-only feature id reached the stack: {op.feature_id}")


def test_undoing_a_modify_does_not_claim_a_restore_that_was_refused(
        manager, project, tmp_path):
    """``_restore_feature`` used to ``return True`` unconditionally after three
    discarded writes."""
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)

    before = QgsFeature(layer.getFeature(1))
    layer.startEditing()
    layer.changeAttributeValue(1, layer.fields().indexFromName("naziv"), "CHANGED")
    layer.commitChanges()
    assert "CHANGED" in _names(path)
    manager.record_modify(layer, layer.getFeature(1), before)
    assert manager.can_undo()

    _block(path, "update")
    assert manager.undo() is False, (
        "the restore was refused by the file and still answered True")
    assert "CHANGED" in _names(path), "the file should be unchanged"
    assert not any("Undone" in text for text in manager.iface.bar.infos), (
        manager.iface.bar.infos)


def test_an_attribute_whose_column_is_gone_is_named(manager, project, tmp_path):
    """Message-only, and said so plainly: there is no file-level consequence to
    assert. Undoing a delete after a schema change brought the feature back with
    values missing and named none of them."""
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)

    feature = layer.getFeature(1)
    manager.record_delete(layer, feature)
    layer.startEditing()
    layer.deleteFeature(1)
    layer.commitChanges()

    op = manager._undo_stack[-1]
    op.attributes = dict(op.attributes or {})
    op.attributes["a_column_that_is_gone"] = "value"

    assert manager.undo() is True, "the feature itself must still come back"
    assert any("a_column_that_is_gone" in text for text in manager.iface.bar.warnings), (
        f"the dropped column was not named: {manager.iface.bar.warnings}")


# ---------------------------------------------------------------------------
# the ordinary case
# ---------------------------------------------------------------------------

def test_an_undo_that_works_reaches_the_file_and_says_so(manager, project, tmp_path):
    """Characterisation, not proof: it passes against the pre-fix code too.
    It is here because every change above runs through this path."""
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)

    _record_add(manager, layer, 1)
    assert manager.undo() is True
    assert "p0" not in _names(path), _names(path)
    assert any("Undone" in text for text in manager.iface.bar.infos)
    assert manager.can_redo()


def test_a_redo_that_works_reaches_the_file(manager, project, tmp_path):
    """Characterisation, as above."""
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)

    _record_add(manager, layer, 1)
    assert manager.undo() is True
    assert manager.redo() is True
    assert "p0" in _names(path), f"redo did not put it back: {_names(path)}"


def test_clearing_the_stacks_forgets_the_unsaved_layers(manager, project, tmp_path):
    """``_unsaved`` only means anything while the operations it belongs to are
    still on a stack."""
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)
    _block(path, "delete")

    _record_add(manager, layer, 1)
    manager.undo()
    assert manager._unsaved, "the refused commit should have been remembered"

    manager.clear()
    assert not manager._unsaved
    assert not manager.can_undo() and not manager.can_redo()


def test_an_undo_on_a_layer_that_will_not_open_for_editing_is_reported(
        manager, project, tmp_path, monkeypatch):
    """``startEditing()``'s result was discarded, so a layer that would not open
    looked exactly like one that had."""
    path = str(tmp_path / "poles.gpkg")
    layer = _poles(path)
    project.addMapLayer(layer)

    _record_add(manager, layer, 1)
    monkeypatch.setattr(layer, "startEditing", lambda *a, **k: False)

    assert manager.undo() is False
    assert manager.iface.bar.warnings, "a layer that would not open said nothing"
    assert _names(path) == ["p0", "p1", "p2"]
    assert os.path.exists(path)
