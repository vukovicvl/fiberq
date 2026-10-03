"""Tests for core.length_sync -- stored lengths following the user's edits.

Two kinds of test live here, for two kinds of failure.

The ordinary ones drive a real edit session on a real layer and assert the
stored value, the undo depth and what reaches the provider. The undo depth is
not decoration: the whole reason the live write happens where it does is that it
has to land inside the user's own edit command, so one Ctrl+Z takes the vertex
and the length back together.

The last few run their scenario in a **subprocess** and assert only the exit
code. A hook written the obvious way segfaults QGIS on the redo of an add, a
split or a paste -- measured on 3.22, 3.44 and 4.0 -- and pytest-qgis starts its
QgsApplication in ``pytest_configure``, so a segfault anywhere takes the entire
run with it rather than failing one test. A crash has to cost these tests only.
"""
import math
import os
import pathlib
import subprocess
import sys

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from fiberq.core.length_manager import length_values, plan_recalculation
from fiberq.core.length_sync import LengthSync, _user_edit_command_is_open
from fiberq.utils.measure import clear_cache, ground_length, measures_metres

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Niš, where a planar Web Mercator length is 1.37x the ground length. Measuring
#: the wrong way is therefore visible in every assertion below, not hidden
#: inside a rounding tolerance.
LAT, LON = 43.32, 21.90
SCALE = 1.0 / math.cos(math.radians(LAT))

#: Wall-clock ceiling for one crash-regression subprocess. The suite has no
#: timeout plugin, so without this a wedged child would run until the CI job's
#: own limit. One scenario is about three seconds, nearly all of it QGIS
#: starting up.
TIMEOUT_S = 120


@pytest.fixture
def project():
    """A local project with a real ellipsoid -- ``QgsProject()``, not instance().

    Every length in the plugin is measured on the project ellipsoid, and a
    brand-new QGIS project leaves that on the string ``'NONE'``, so a test
    without this measures map units and proves nothing.
    """
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    prj.setEllipsoid("EPSG:7030")
    clear_cache()
    yield prj
    clear_cache()


@pytest.fixture
def sync(project):
    """An attached LengthSync, detached again however the test ends."""
    following = LengthSync(project)
    following.attach()
    yield following
    following.detach()


def _line(length_map_units=400.0, offset=0.0):
    """A straight line of known *map-unit* length at the reference latitude."""
    xform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsCoordinateTransformContext())
    start = xform.transform(QgsPointXY(LON, LAT))
    y = start.y() + offset
    return QgsGeometry.fromPolylineXY(
        [QgsPointXY(start.x(), y), QgsPointXY(start.x() + length_map_units, y)])


def _layer(project, name, fields, rows, geometry="LineString", crs="EPSG:3857"):
    layer = QgsVectorLayer(f"{geometry}?crs={crs}", name, "memory")
    assert layer.isValid()
    layer.dataProvider().addAttributes([QgsField(f, QVariant.Double) for f in fields])
    layer.updateFields()

    feats = []
    for geom, attrs in rows:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        for key, value in attrs.items():
            feat.setAttribute(key, value)
        feats.append(feat)
    assert layer.dataProvider().addFeatures(feats)[0]
    layer.updateExtents()
    project.addMapLayer(layer)
    return layer


def _route(project, geom=None):
    """A Route layer whose one feature already stores the right length."""
    geom = geom if geom is not None else _line()
    metres = ground_length(geom, project=project)
    return _layer(project, "Route", ["duzina", "duzina_km"],
                  [(geom, {"duzina": metres, "duzina_km": round(metres / 1000.0, 2)})])


def _gpkg_route(project, tmp_path):
    """A Route layer backed by a real GeoPackage, so a commit can be re-read."""
    mem = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    mem.dataProvider().addAttributes([QgsField("duzina", QVariant.Double),
                                      QgsField("duzina_km", QVariant.Double)])
    mem.updateFields()
    geom = _line()
    metres = ground_length(geom, project=project)
    feat = QgsFeature(mem.fields())
    feat.setGeometry(geom)
    feat.setAttribute("duzina", metres)
    feat.setAttribute("duzina_km", round(metres / 1000.0, 2))
    mem.dataProvider().addFeatures([feat])

    path = str(tmp_path / "route.gpkg")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Route"
    QgsVectorFileWriter.writeAsVectorFormatV3(
        mem, path, QgsCoordinateTransformContext(), options)

    uri = f"{path}|layername=Route"
    layer = QgsVectorLayer(uri, "Route", "ogr")
    assert layer.isValid()
    project.addMapLayer(layer)
    return layer, uri


def _stored(layer, field, fid=1):
    return layer.getFeature(fid).attribute(field)


def _on_disk(layer, field, fid=1):
    """The value the *provider* holds, i.e. past the edit buffer."""
    return next(f for f in layer.dataProvider().getFeatures() if f.id() == fid).attribute(field)


def _move_vertex(layer, fid=1, vertex=1, dx=400.0, label="Vertex move"):
    """One QGIS vertex drag: an edit command around a single moveVertex."""
    point = layer.getFeature(fid).geometry().asPolyline()[vertex]
    layer.beginEditCommand(label)
    moved = layer.moveVertex(point.x() + dx, point.y(), fid, vertex)
    layer.endEditCommand()
    assert moved
    return layer.getFeature(fid).geometry()


# ---------------------------------------------------------------------------
# The guard: which moments may be written in
# ---------------------------------------------------------------------------

def test_the_guard_only_opens_while_a_user_edit_command_is_open(project, sync):
    """The measured state table from the design, as an assertion per row.

    Both halves of the guard are load-bearing. Dropping ``isEditCommandActive``
    would write on a bare ``changeGeometry`` and cost the user a second Ctrl+Z;
    dropping ``not canUndo()`` would write during an undo replay, which
    segfaults QGIS on the following redo.
    """
    layer = _route(project)
    assert not _user_edit_command_is_open(layer)

    layer.startEditing()
    assert not _user_edit_command_is_open(layer)

    layer.beginEditCommand("probe")
    assert _user_edit_command_is_open(layer), "a write here joins the user's step"
    layer.endEditCommand()
    assert not _user_edit_command_is_open(layer)

    layer.rollBack()


def test_the_guard_shuts_while_an_abandoned_command_unwinds(project, sync):
    """``destroyEditCommand()`` re-emits geometryChanged with the old geometry.

    ``isEditCommandActive()`` is still True there, so that half alone would
    write during a rollback. ``canUndo()`` is what closes the door.
    """
    layer = _route(project)
    before = _stored(layer, "duzina")
    layer.startEditing()

    states = []
    recorder = (lambda fid, geom: states.append(_user_edit_command_is_open(layer)))
    layer.geometryChanged.connect(recorder)
    try:
        layer.beginEditCommand("abandoned")
        layer.changeGeometry(1, _line(800.0))
        layer.destroyEditCommand()
    finally:
        layer.geometryChanged.disconnect(recorder)

    assert len(states) >= 2, "the rollback must re-emit geometryChanged"
    assert states[0] is True, "inside the command"
    assert all(state is False for state in states[1:]), "while it unwinds"
    # The live write joined the command, so abandoning it took the length too.
    assert _stored(layer, "duzina") == pytest.approx(before)
    layer.rollBack()


def test_a_second_user_edit_command_is_still_written_in(project, sync):
    """``not canUndo()`` reads "a macro is open", not "the session is fresh"."""
    layer = _route(project)
    layer.startEditing()
    _move_vertex(layer)
    first = _stored(layer, "duzina")

    geom = _move_vertex(layer, dx=300.0)

    assert layer.undoStack().count() == 2, "two gestures, two undo steps"
    assert _stored(layer, "duzina") != first
    assert _stored(layer, "duzina") == pytest.approx(ground_length(geom, layer, project=project))
    layer.rollBack()


# ---------------------------------------------------------------------------
# The live path
# ---------------------------------------------------------------------------

def test_a_vertex_move_updates_the_stored_lengths(project, sync):
    layer = _route(project)
    layer.startEditing()

    geom = _move_vertex(layer)

    metres = ground_length(geom, layer, project=project)
    assert _stored(layer, "duzina") == pytest.approx(metres)
    assert _stored(layer, "duzina_km") == pytest.approx(round(metres / 1000.0, 2))
    # The planar length would be 1.37x this; a pass here proves the measurement
    # went through utils.measure and not QgsGeometry.length().
    assert metres == pytest.approx(geom.length() / SCALE, rel=0.01)
    layer.rollBack()


def test_the_length_is_part_of_the_users_own_undo_step(project, sync):
    """One gesture, one undo entry -- and undo/redo carries both halves."""
    layer = _route(project)
    before = _stored(layer, "duzina")
    layer.startEditing()

    geom = _move_vertex(layer)
    after = _stored(layer, "duzina")
    assert layer.undoStack().count() == 1, "the write must not add a second step"
    assert after == pytest.approx(ground_length(geom, layer, project=project))

    stack = layer.undoStack()
    for _ in range(3):
        stack.undo()
        assert layer.undoStack().count() == 1
        assert _stored(layer, "duzina") == pytest.approx(before)
        assert layer.getFeature(1).geometry().length() == pytest.approx(400.0)
        stack.redo()
        assert _stored(layer, "duzina") == pytest.approx(after)
        assert layer.getFeature(1).geometry().length() == pytest.approx(800.0)

    layer.rollBack()


def test_a_rollback_writes_nothing(project, sync):
    layer = _route(project)
    before = _stored(layer, "duzina")
    layer.startEditing()
    _move_vertex(layer)

    layer.rollBack()

    assert not layer.isEditable()
    assert _stored(layer, "duzina") == pytest.approx(before)
    assert _on_disk(layer, "duzina") == pytest.approx(before)


def test_a_bare_change_geometry_is_left_to_the_sweep(project, sync):
    """The move tool and Route correction edit without an edit command.

    Writing here would push a second command onto the undo stack, so the live
    path declines and the commit sweep picks it up instead.
    """
    layer = _route(project)
    before = _stored(layer, "duzina")
    layer.startEditing()

    assert layer.changeGeometry(1, _line(800.0))

    assert _stored(layer, "duzina") == pytest.approx(before), "not written live"
    assert layer.undoStack().count() == 1, "no second undo step was created"
    layer.rollBack()


# ---------------------------------------------------------------------------
# The commit sweep
# ---------------------------------------------------------------------------

def test_the_sweep_fixes_a_bare_edit_at_commit(project, sync):
    layer = _route(project)
    layer.startEditing()
    geom = _line(800.0)
    assert layer.changeGeometry(1, geom)

    assert layer.commitChanges(), layer.commitErrors()

    metres = ground_length(geom, layer, project=project)
    assert not layer.isEditable()
    assert _on_disk(layer, "duzina") == pytest.approx(metres)
    assert _on_disk(layer, "duzina_km") == pytest.approx(round(metres / 1000.0, 2))


def test_the_sweep_gives_an_added_feature_its_length(project, sync):
    """Added features are the sweep's job; writing from featureAdded crashes."""
    layer = _route(project)
    layer.startEditing()
    geom = _line(600.0, offset=50.0)
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    layer.beginEditCommand("Add line feature")
    assert layer.addFeatures([feat])
    layer.endEditCommand()

    assert layer.commitChanges(), layer.commitErrors()

    metres = ground_length(geom, layer, project=project)
    added = [f for f in layer.dataProvider().getFeatures()
             if f.geometry().length() == pytest.approx(600.0)]
    assert len(added) == 1
    assert added[0].attribute("duzina") == pytest.approx(metres)
    assert added[0].attribute("duzina_km") == pytest.approx(round(metres / 1000.0, 2))


def test_a_cable_keeps_its_slack_and_its_total_follows(project, sync):
    """``total_len_m = duzina_m + slack_m``, and the slack is the user's number."""
    geom = _line()
    metres = ground_length(geom, project=project)
    layer = _layer(project, "Underground cables", ["duzina_m", "slack_m", "total_len_m"],
                   [(geom, {"duzina_m": metres, "slack_m": 20.0,
                            "total_len_m": metres + 20.0})])
    layer.startEditing()

    moved = _move_vertex(layer)
    assert layer.commitChanges(), layer.commitErrors()

    expected = ground_length(moved, layer, project=project)
    assert _on_disk(layer, "duzina_m") == pytest.approx(expected)
    assert _on_disk(layer, "slack_m") == pytest.approx(20.0), "slack is never written"
    assert _on_disk(layer, "total_len_m") == pytest.approx(expected + 20.0)


def test_a_live_write_reaches_the_file_on_disk(project, sync, tmp_path):
    """Memory layers can flatter a commit; this one re-reads the GeoPackage."""
    layer, uri = _gpkg_route(project, tmp_path)
    layer.startEditing()

    geom = _move_vertex(layer)
    metres = ground_length(geom, layer, project=project)
    # Right in the buffer *before* the commit: the sweep would land the same
    # value a moment later, so without this line the test would also pass with
    # no live path at all (measured -- it is the one the live-path mutation
    # survives).
    assert _stored(layer, "duzina") == pytest.approx(metres)
    assert layer.undoStack().count() == 1

    assert layer.commitChanges(), layer.commitErrors()

    reread = QgsVectorLayer(uri, "Route", "ogr")
    saved = next(reread.getFeatures())
    assert saved.attribute("duzina") == pytest.approx(metres)
    assert saved.attribute("duzina_km") == pytest.approx(round(metres / 1000.0, 2))


def test_the_sweep_lands_on_a_geopackage_for_an_add_and_a_split(project, sync, tmp_path):
    """The two gestures only the sweep can write, on the provider FiberQ uses.

    The memory provider is not evidence for these: an added feature's attribute
    write goes into the edit buffer against a *negative* fid, and whether it
    survives the commit is the provider's business, not the sweep's. A
    GeoPackage also carries its own ``fid`` column ahead of the schema's, so a
    positional ``setAttributes()`` would put the length in ``fid`` and the add
    would be rejected -- hence by name here. Identical on 3.22, 3.44 and 4.0
    (measured).
    """
    layer, uri = _gpkg_route(project, tmp_path)

    # 1. QGIS "Add line feature": nothing may be written from featureAdded, so
    # the length exists only because the sweep put it there.
    layer.startEditing()
    geom = _line(600.0, offset=50.0)
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    feat.setAttribute("duzina", 0.0)
    feat.setAttribute("duzina_km", 0.0)
    layer.beginEditCommand("Add line feature")
    assert layer.addFeatures([feat])
    layer.endEditCommand()

    assert layer.commitChanges(), layer.commitErrors()

    metres = ground_length(geom, layer, project=project)
    on_disk = {round(f.geometry().length(), 1): f
               for f in QgsVectorLayer(uri, "Route", "ogr").getFeatures()}
    assert 600.0 in on_disk, sorted(on_disk)
    assert on_disk[600.0].attribute("duzina") == pytest.approx(metres)
    assert on_disk[600.0].attribute("duzina_km") == pytest.approx(round(metres / 1000.0, 2))

    # 2. QGIS "Split features": the shortened original arrives through the live
    # path and the new part only through the sweep, so after the save each part
    # has to carry its own length rather than the parent's.
    start = layer.getFeature(1).geometry().asPolyline()[0]
    cut_x = start.x() + 150.0
    layer.startEditing()
    layer.selectByIds([1])
    layer.beginEditCommand("Split features")
    layer.splitFeatures([QgsPointXY(cut_x, start.y() - 10.0),
                         QgsPointXY(cut_x, start.y() + 10.0)], False)
    layer.endEditCommand()
    layer.removeSelection()

    assert layer.commitChanges(), layer.commitErrors()

    parts = [f for f in QgsVectorLayer(uri, "Route", "ogr").getFeatures()
             if round(f.geometry().length(), 1) in (150.0, 250.0)]
    assert len(parts) == 2, "the split did not produce two parts"
    for part in parts:
        want = ground_length(part.geometry(), layer, project=project)
        assert part.attribute("duzina") == pytest.approx(want)
        assert part.attribute("duzina_km") == pytest.approx(round(want / 1000.0, 2))


def test_a_feature_moved_and_then_deleted_is_not_written(project, sync):
    """Nothing is left to carry a length, and the write would only fail."""
    layer = _route(project)
    layer.startEditing()
    _move_vertex(layer)
    assert layer.deleteFeature(1)

    assert layer.commitChanges(), layer.commitErrors()

    assert list(layer.dataProvider().getFeatures()) == []


def test_the_sweep_and_the_recalculation_agree(project, sync):
    """After a save, "Recalculate lengths" must have nothing left to offer."""
    layer = _route(project)
    layer.startEditing()
    assert layer.changeGeometry(1, _line(950.0))
    assert layer.commitChanges(), layer.commitErrors()

    assert plan_recalculation(project).changes == []


def test_a_feature_carrying_no_field_names_is_still_measured(project, sync):
    """``QgsFeature()`` + ``setAttributes([...])``: what the console produces.

    ``addFeature()`` keeps the feature it is handed and checks only the
    attribute *count*, so this one reaches the edit buffer with no field names
    at all and ``feat.attribute("slack_m")`` raises ``KeyError`` on it. The
    values are still positional, so the layer's own field index reads them --
    and the slack it carries has to survive into ``total_len_m``.
    """
    geom = _line()
    metres = ground_length(geom, project=project)
    layer = _layer(project, "Underground cables",
                   ["duzina_m", "slack_m", "total_len_m"],
                   [(geom, {"duzina_m": metres, "slack_m": 1.0,
                            "total_len_m": metres + 1.0})])
    layer.startEditing()

    added_geom = _line(250.0, offset=90.0)
    bare = QgsFeature()
    bare.setGeometry(added_geom)
    bare.setAttributes([None, 7.5, None])
    assert layer.addFeature(bare)
    buffered = list(layer.editBuffer().addedFeatures().values())[0]
    assert buffered.fields().names() == [], "the premise: no field names"

    assert layer.commitChanges(), layer.commitErrors()

    expected = ground_length(added_geom, layer, project=project)
    saved = [f for f in layer.dataProvider().getFeatures()
             if f.geometry().length() == pytest.approx(250.0)]
    assert len(saved) == 1
    assert saved[0].attribute("duzina_m") == pytest.approx(expected)
    assert saved[0].attribute("total_len_m") == pytest.approx(expected + 7.5), \
        "the slack it carried was read, not thrown away"


def test_one_failing_feature_does_not_cost_the_rest_their_refresh(project, sync,
                                                                  monkeypatch):
    """The sweep walks a whole buffer, so one failure must stay one failure.

    Measured before the per-feature guard: a feature the sweep could not write
    raised, abandoned the walk, and a 655.81 m move of a *healthy* feature in
    the same commit stayed stored as ``0.0``. The write is monkeypatched here
    rather than provoked, so the test states the contract (isolation) instead of
    whichever way a feature happens to be unwritable today.
    """
    first, second = _line(400.0), _line(400.0, offset=120.0)
    layer = _layer(project, "Route", ["duzina", "duzina_km"],
                   [(first, {"duzina": 0.0, "duzina_km": 0.0}),
                    (second, {"duzina": 0.0, "duzina_km": 0.0})])
    original = sync._write
    seen = []

    def explode(lyr, fid, **kwargs):
        seen.append(fid)
        if len(seen) == 1:
            raise RuntimeError("the provider said no")
        return original(lyr, fid, **kwargs)

    monkeypatch.setattr(sync, "_write", explode)

    layer.startEditing()
    # Bare changeGeometry, no edit command: the live path skips both by design,
    # so only the sweep can fix them.
    assert layer.changeGeometry(1, _line(900.0))
    assert layer.changeGeometry(2, _line(900.0, offset=120.0))

    assert layer.commitChanges(), layer.commitErrors()

    assert len(seen) == 2, "the sweep carried on past the failure"
    survivor = seen[1]
    # Measured from the geometry that actually reached the file: the two lines
    # sit at different latitudes, so their ground lengths are not the same.
    metres = ground_length(layer.getFeature(survivor).geometry(), layer, project=project)
    assert _on_disk(layer, "duzina", fid=survivor) == pytest.approx(metres)
    assert _on_disk(layer, "duzina_km", fid=survivor) == pytest.approx(
        round(metres / 1000.0, 2))


# ---------------------------------------------------------------------------
# What must never be touched
# ---------------------------------------------------------------------------

def test_the_optical_slack_layer_is_never_followed(project, sync):
    """Same field name, point geometry, user's value: measuring it destroys it.

    ``Optical slack.duzina_m`` is the slack the user typed. A hook that picked
    layers by "has a duzina_m field" instead of by canonical layer name would
    wipe every slack value in the project.
    """
    layer = _layer(project, "Optical slack", ["duzina_m"],
                   [(QgsGeometry.fromPointXY(QgsPointXY(2437000, 5365000)),
                     {"duzina_m": 20.0})], geometry="Point")

    assert layer.id() not in sync._geometry_slots

    layer.startEditing()
    layer.beginEditCommand("Move slack")
    layer.changeGeometry(1, QgsGeometry.fromPointXY(QgsPointXY(2437500, 5365000)))
    layer.endEditCommand()
    assert layer.commitChanges(), layer.commitErrors()

    assert _on_disk(layer, "duzina_m") == pytest.approx(20.0)


def test_a_provider_level_add_is_untouched(project, sync):
    """The WP3 bundle import writes through the provider and emits no signals."""
    layer = _route(project)
    geom = _line(700.0, offset=100.0)
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    feat.setAttribute("duzina", 1.0)

    assert layer.dataProvider().addFeatures([feat])[0]

    imported = [f for f in layer.dataProvider().getFeatures()
                if f.geometry().length() == pytest.approx(700.0)]
    assert len(imported) == 1
    assert imported[0].attribute("duzina") == pytest.approx(1.0), "imported as-is"
    assert not layer.isEditable(), "no edit session was opened behind the import"


def test_a_layer_without_a_usable_ellipsoid_is_left_alone():
    """Map units are not metres; storing one as the other is the original bug.

    A project with no CRS and no ellipsoid is what QGIS hands a user who never
    opened Project Properties. ``measures_metres()`` says so, and the sync then
    refuses rather than storing a number it cannot label.
    """
    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem())
    project.setEllipsoid("NONE")
    clear_cache()
    following = LengthSync(project)
    following.attach()
    layer = QgsVectorLayer("LineString", "Route", "memory")
    # The memory provider defaults to EPSG:4326, which does name an ellipsoid.
    layer.setCrs(QgsCoordinateReferenceSystem())
    layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
    layer.updateFields()
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(100, 0)]))
    feat.setAttribute("duzina", 0.0)
    layer.dataProvider().addFeatures([feat])
    project.addMapLayer(layer)
    assert not measures_metres(layer, project=project), "the premise of this test"

    layer.startEditing()
    _move_vertex(layer, vertex=1, dx=100.0)
    assert layer.commitChanges(), layer.commitErrors()

    assert _on_disk(layer, "duzina") == pytest.approx(0.0)
    following.detach()
    clear_cache()


# ---------------------------------------------------------------------------
# A documented limitation: buffered transaction groups
# ---------------------------------------------------------------------------

def test_a_buffered_transaction_group_keeps_the_live_path_and_loses_the_sweep(
        project, tmp_path):
    """Buffered groups (Project Properties > Data Sources) have no pre-commit signal.

    ``QgsVectorLayerEditBufferGroup`` emits nothing before it writes -- not even
    for an explicit ``layer.commitChanges()`` -- so there is no sweep to hook
    there. The module's docstring says so and warns once per layer; this is that
    paragraph as an assertion, so the day QGIS grows the signal, the test is
    what notices. Identical on 3.44 and 4.0 (measured).
    """
    if not hasattr(project, "setTransactionMode"):
        pytest.skip("transaction modes arrived in QGIS 3.26")
    from qgis.core import Qgis

    project.setTransactionMode(Qgis.TransactionMode.BufferedGroups)
    following = LengthSync(project)
    following.attach()
    layer, uri = _gpkg_route(project, tmp_path)
    try:
        assert following._uses_buffered_groups(), "the premise of this test"
        assert sorted(following._warned_buffered) == [layer.id()], "warned once"

        # Kept: a vertex drag is still one undo step holding both halves, and
        # the value still reaches the file.
        layer.startEditing()
        geom = _move_vertex(layer)
        metres = ground_length(geom, layer, project=project)
        assert _stored(layer, "duzina") == pytest.approx(metres)
        assert layer.undoStack().count() == 1
        assert layer.commitChanges(), layer.commitErrors()
        saved = next(QgsVectorLayer(uri, "Route", "ogr").getFeatures())
        assert saved.attribute("duzina") == pytest.approx(metres)

        # Lost: an edit the live path declines has nothing to fix it at commit.
        layer.startEditing()
        assert layer.changeGeometry(1, _line(1200.0))
        assert layer.commitChanges(), layer.commitErrors()
        stale = next(QgsVectorLayer(uri, "Route", "ogr").getFeatures())
        assert stale.geometry().length() == pytest.approx(1200.0), "the geometry saved"
        assert stale.attribute("duzina") == pytest.approx(metres), \
            "no beforeCommitChanges here: the stale length is the documented cost"
    finally:
        following.detach()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_detach_stops_the_updates(project):
    following = LengthSync(project)
    following.attach()
    layer = _route(project)
    before = _stored(layer, "duzina")

    following.detach()

    layer.startEditing()
    _move_vertex(layer)
    assert _stored(layer, "duzina") == pytest.approx(before)
    assert layer.commitChanges(), layer.commitErrors()
    assert _on_disk(layer, "duzina") == pytest.approx(before)


def test_detach_twice_is_harmless(project, sync):
    _route(project)
    sync.detach()
    sync.detach()
    assert sync._geometry_slots == {}


def test_attaching_twice_follows_each_layer_once(project, sync):
    """A reload that left the old connection in place would write twice.

    Asserted on the writes, not only on the bookkeeping: ``_geometry_slots`` is
    keyed by layer id, so a second ``connect()`` on the same layer would leave
    its length at 1 and the leak invisible (measured -- the mutation that drops
    the guard passes a dict-only test). Qt counts the connections themselves,
    and a doubled one turns one vertex move into two writes.
    """
    layer = _route(project)
    sync.attach()                  # the guard in attach(): already attached
    sync._layers_added([layer])    # and the one in _connect_layer

    assert len(sync._geometry_slots) == 1
    assert len(sync._commit_slots) == 1
    assert layer.receivers(layer.geometryChanged) == 1
    assert layer.receivers(layer.beforeCommitChanges) == 1

    written = []
    unwrapped = sync._write

    def counting(target, fid, **kwargs):
        written.append(fid)
        return unwrapped(target, fid, **kwargs)

    sync._write = counting
    try:
        layer.startEditing()
        _move_vertex(layer)
    finally:
        sync._write = unwrapped
    assert written == [1], "one gesture, one write"
    layer.rollBack()


def test_a_layer_removed_mid_edit_leaves_no_connection(project, sync):
    """Manual QA step 13: remove the Route layer while it is being edited."""
    layer = _route(project)
    layer_id = layer.id()
    layer.startEditing()
    _move_vertex(layer)

    project.removeMapLayer(layer_id)

    assert layer_id not in sync._geometry_slots
    assert layer_id not in sync._commit_slots


# ---------------------------------------------------------------------------
# One source of the arithmetic
# ---------------------------------------------------------------------------

def test_length_values_writes_nothing(project):
    """The helper is shared precisely because it cannot touch anything."""
    layer = _route(project)
    feat = layer.getFeature(1)
    stored = feat.attribute("duzina")

    values = length_values(feat, layer, geom=_line(800.0), project=project)

    assert values["duzina"] == pytest.approx(ground_length(_line(800.0), layer, project=project))
    assert layer.getFeature(1).attribute("duzina") == pytest.approx(stored)
    assert not layer.isEditable()


def test_length_values_refuses_a_point_layer_that_looks_like_a_cable(project):
    layer = _layer(project, "Optical slack", ["duzina_m"],
                   [(QgsGeometry.fromPointXY(QgsPointXY(2437000, 5365000)),
                     {"duzina_m": 20.0})], geometry="Point")

    assert length_values(layer.getFeature(1), layer, project=project) == {}


def test_the_recalculation_and_the_sync_share_one_helper():
    """Two copies of the km rule is how the two repairs would start to disagree."""
    import inspect

    from fiberq.core import length_manager as lm
    from fiberq.core import length_sync as ls

    assert "length_values(" in inspect.getsource(lm._plan_layer)
    assert "1000" not in inspect.getsource(lm._plan_layer), "the km rule moved"
    assert "length_writes" in inspect.getsource(ls.LengthSync._write)
    assert "QgsDistanceArea" not in inspect.getsource(ls), "it must not measure itself"


def test_the_plugin_attaches_it_and_takes_it_down_again(qgis_app):
    """FiberQPlugin needs a live iface, so the wiring is read from the source.

    Both halves matter: a reload that left the previous instance connected
    would write every length twice, and ``unload()`` that forgets it leaves
    slots pointing at a dead Python object.
    """
    import inspect

    import fiberq.main_plugin as mp

    initgui = inspect.getsource(mp.FiberQPlugin.initGui)
    assert "install_length_sync" in initgui
    assert "previous.detach()" in initgui, "idempotent re-init"
    assert "sync.detach()" in inspect.getsource(mp.FiberQPlugin.unload)


# ---------------------------------------------------------------------------
# Crash regressions: each in its own process, asserting only the exit code
# ---------------------------------------------------------------------------

#: The child bootstraps its own QgsApplication, performs one gesture inside an
#: edit command, replays undo/redo three times and saves. It exits through
#: ``os._exit`` so that a segfault during interpreter teardown -- reliable on
#: QGIS 4.0, and unrelated to anything here -- cannot be read as the crash under
#: test. Printing DONE is how the parent knows it got to the end.
DRIVER = '''\
import os
import sys

sys.path.insert(0, {repo!r})

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsFeature,
                       QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer)

QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], False)
APP.initQgis()

from fiberq.core.length_sync import LengthSync

URI = ("LineString?crs=EPSG:3857&field=duzina:double&field=duzina_km:double"
       "&index=yes")


def say(*a):
    print(*a, flush=True)


def line(y, length=400.0):
    x = 2437000.0
    return QgsGeometry.fromPolylineXY(
        [QgsPointXY(x, y), QgsPointXY(x + length / 2.0, y), QgsPointXY(x + length, y)])


project = QgsProject()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
project.setEllipsoid("EPSG:7030")

layer = QgsVectorLayer(URI, "Route", "memory")
feats = []
for i in range(2):
    f = QgsFeature(layer.fields())
    f.setGeometry(line(5365000.0 + i * 50.0))
    f.setAttributes([0.0, 0.0])
    feats.append(f)
layer.dataProvider().addFeatures(feats)
project.addMapLayer(layer)

sync = LengthSync(project)
sync.attach()
assert layer.id() in sync._geometry_slots, "the layer was not followed"

layer.startEditing()
gesture = {gesture!r}

if gesture == "add":
    layer.beginEditCommand("Add line feature")
    f = QgsFeature(layer.fields())
    f.setGeometry(line(5365200.0))
    f.setAttributes([0.0, 0.0])
    say("add", layer.addFeatures([f]))
    layer.endEditCommand()
elif gesture == "split":
    layer.selectByIds([1])
    layer.beginEditCommand("Split features")
    say("split", layer.splitFeatures(
        [QgsPointXY(2437200.0, 5364900.0), QgsPointXY(2437200.0, 5365100.0)], False))
    layer.endEditCommand()
    layer.removeSelection()
elif gesture == "paste":
    # QGIS's paste is addFeatures of several features in one edit command.
    layer.beginEditCommand("Paste features")
    pasted = []
    for i in range(2):
        f = QgsFeature(layer.fields())
        f.setGeometry(line(5365300.0 + i * 50.0))
        f.setAttributes([0.0, 0.0])
        pasted.append(f)
    say("paste", layer.addFeatures(pasted))
    layer.endEditCommand()
elif gesture == "move":
    layer.beginEditCommand("Vertex move")
    say("move", layer.moveVertex(2437500.0, 5365000.0, 1, 1))
    layer.endEditCommand()
else:
    raise SystemExit("unknown gesture " + gesture)

stack = layer.undoStack()
for i in range(3):
    say("undo", i, stack.count(), stack.index())
    stack.undo()
    say("redo", i, stack.count(), stack.index())
    stack.redo()

say("commit", layer.commitChanges(), layer.commitErrors()[:2])
say("lengths", sorted(round(f.attribute("duzina") or 0.0, 2)
                      for f in layer.dataProvider().getFeatures()))
sync.detach()
say("DONE")
sys.stdout.flush()
os._exit(0)
'''


def _crash_probe(tmp_path, gesture):
    """Run one gesture in a child process; returns ``(returncode, output)``."""
    script = tmp_path / f"gesture_{gesture}.py"
    script.write_text(DRIVER.format(repo=str(REPO_ROOT), gesture=gesture),
                      encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(tmp_path), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return done.returncode, done.stdout.decode("utf-8", "replace")


@pytest.mark.parametrize("gesture", ["move", "add", "split", "paste"])
def test_undo_then_redo_does_not_crash_qgis(tmp_path, gesture):
    """The regression that decides this design: no SIGSEGV on redo.

    A hook that writes from ``featureAdded`` -- with or without the guard --
    dies here on all three supported QGIS versions, at the first redo, for all
    three of add, split and paste. The exit code is the only reliable signal:
    the undo-stack depth stays at 1 throughout, so a test that checked the depth
    would pass while the process was already corrupt.
    """
    code, output = _crash_probe(tmp_path, gesture)

    assert code == 0, f"{gesture} exited {code} (-11 is SIGSEGV):\n{output}"
    assert "DONE" in output, output


# ---------------------------------------------------------------------------
# From the adversarial review: two seams with nothing covering them
# ---------------------------------------------------------------------------

def test_a_second_layer_changed_with_no_command_of_its_own_is_fixed_at_commit(
        project, sync):
    """Manual QA step 11: topological editing moves a vertex on two layers.

    The vertex tool opens an edit command on the layer under the cursor only.
    The shared vertex reaches the other layer through ``addTopologicalPoints()``
    with no command of its own, so the live path declines it by design -- the
    sweep at commit is the whole reason step 11 comes out true.
    """
    from qgis.core import QgsPoint

    project.setTopologicalEditing(True)
    route = _route(project)
    pipes = _layer(project, "PE pipes", ["duzina_m", "duzina_km"],
                   [(_line(), {"duzina_m": 0.0, "duzina_km": 0.0})])
    route.startEditing()
    pipes.startEditing()

    point = route.getFeature(1).geometry().asPolyline()[1]
    shared = QgsPointXY(point.x() - 100.0, point.y())
    route.beginEditCommand("Move with topology")
    assert route.moveVertex(shared.x(), shared.y(), 1, 1)
    assert pipes.addTopologicalPoints(QgsPoint(shared)) == 0, \
        "the moved vertex landed off the pipe, so this proves nothing"
    route.endEditCommand()

    assert _stored(pipes, "duzina_m") == 0.0, \
        "no edit command of its own, so the live path must decline it"
    assert pipes.commitChanges(), pipes.commitErrors()
    metres = ground_length(pipes.getFeature(1).geometry(), pipes, project=project)
    assert _on_disk(pipes, "duzina_m") == pytest.approx(metres)
    assert _on_disk(pipes, "duzina_km") == pytest.approx(round(metres / 1000.0, 2))


def test_the_undo_redo_panel_may_jump_several_steps_at_once(project, sync):
    """``QUndoStack.setIndex`` replays several commands with ``index()`` frozen.

    Qt only updates the index once the whole jump is done, so ``canUndo()``
    reads False for the entire replay and ``isEditCommandActive()`` is the only
    half of the guard holding. Measured with the guard removed: clicking around
    the panel swung the stack 5 -> 13 -> 11 under the user.
    """
    layer = _route(project)
    layer.startEditing()
    for i in range(3):
        _move_vertex(layer, dx=40.0 * (i + 1), label=f"Move {i}")
    stack = layer.undoStack()
    assert stack.count() == 3, "one command per gesture"

    stack.setIndex(0)
    assert stack.count() == 3, "a multi-step jump must not push anything"
    stack.setIndex(3)
    assert stack.count() == 3

    metres = ground_length(layer.getFeature(1).geometry(), layer, project=project)
    assert _stored(layer, "duzina") == pytest.approx(metres)
