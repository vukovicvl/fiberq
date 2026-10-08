"""Merge routes: what reaches the file, and what the user is told about it.

WP4 4.2 item R7. Branch ``fix/wp4-write-paths``.

Every assertion here reads the GeoPackage **fresh from disk**, or straight out
of SQLite, and never through ``layer.getFeatures()``. That is not caution, it is
the whole point: ``getFeatures()`` reads through the edit buffer, so the old
code's canvas and attribute table showed a merged route that was not in the file
and never would be. A test that trusted ``getFeatures()`` would have agreed with
the bug.

Four defects, each measured on 3.22.16, 3.44.15 and 4.0.3 through the real
``RouteManager.merge_all_routes()``:

1. **Both routes destroyed, success reported.** A GeoPackage commit is not
   atomic across operations. With a trigger refusing the insert,
   ``commitErrors()`` read::

       ['SUCCESS: 2 feature(s) deleted.', 'ERROR: 1 feature(s) not added.']

   -- the deletes landed, the insert did not, the Route table went from two rows
   to **zero**, and the modal said "Route has been created! Length: 20.00 m".
   The fix is an ordering change, not just a message: the merged route is
   committed *first*, and the originals are removed only once it is on disk. The
   worst a refusal can now cost is a duplicate the user can see.

2. **A crash on a multipart route.** ``asPolyline()`` raises ``TypeError`` on
   any multipart line, so the ``asMultiPolyline()`` fallback was unreachable and
   the error left the Qt slot. An ESRI Shapefile line layer is multipart for
   every feature, single-part or not.

3. **A phantom joining segment.** The "Routes are not connected end-to-end"
   warning could never fire -- ``fromPolylineXY`` always answers a single-part
   LineString, so the ``isMultipart()`` test above it was always False. Two
   routes 490 m apart merged into one 510 m route, silently.

4. **The user's unsaved work committed.** ``startEditing()`` was unguarded, so a
   merge saved whatever else was in the layer's buffer.

Nine of the eleven tests below go red against a tree with only this fix
reverted. The two that do not are marked **characterisation** in their own
docstrings and say why -- one is the happy path, which always worked, and one
guards the new gap report against over-firing, which no past version could fail.
"""
import os
import sqlite3

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.core.route_manager import RouteManager

ROUTE_FIELDS = [
    ("naziv", QVariant.String),
    ("duzina", QVariant.Double),
    ("duzina_km", QVariant.Double),
    ("tip_trase", QVariant.String),
]


class FakeBar:
    def __init__(self):
        self.warnings = []
        self.infos = []

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushInfo(self, title, text):
        self.infos.append(text)

    def pushSuccess(self, title, text):
        self.infos.append(text)


class FakeCanvas:
    def __init__(self, crs):
        self._crs = crs

    def mapSettings(self):
        return self

    def destinationCrs(self):
        return self._crs


class FakeIface:
    def __init__(self, crs=None):
        self.bar = FakeBar()
        self._canvas = FakeCanvas(crs or QgsCoordinateReferenceSystem("EPSG:3857"))

    def messageBar(self):
        return self.bar

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return None


@pytest.fixture(autouse=True)
def quiet_dialogs(monkeypatch):
    """Collect every modal the merge would have shown, so a test can read it."""
    said = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: said.append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: said.append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: said.append(str(a[-1]))))
    return said


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture
def manager(project, monkeypatch):
    """A real RouteManager with the route-type prompt answered, not a __new__."""
    mgr = RouteManager(FakeIface())
    monkeypatch.setattr(mgr, "_ask_route_type", lambda *a, **k: "podzemna")
    monkeypatch.setattr(mgr, "stylize_route_layer", lambda *a, **k: None)
    return mgr


def _gpkg_route_layer(path, wkts, geometry_type="LineString"):
    """A GeoPackage Route layer on disk, holding ``wkts``."""
    mem = QgsVectorLayer(f"{geometry_type}?crs=EPSG:3857", "Route", "memory")
    mem.dataProvider().addAttributes([QgsField(n, t) for n, t in ROUTE_FIELDS])
    mem.updateFields()
    for i, wkt in enumerate(wkts):
        feature = QgsFeature(mem.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        feature.setAttribute("naziv", f"source {i + 1}")
        feature.setAttribute("duzina", 10.0)
        feature.setAttribute("tip_trase", "vazdusna")
        assert mem.dataProvider().addFeatures([feature])[0]

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Route"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem, path, QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
    assert layer.isValid()
    return layer


def _block(path, operation):
    """A real GeoPackage constraint: a trigger that refuses one operation.

    This is what the plan's acceptance criterion names, and it is the right
    fixture because the write call still answers **True** -- the buffer write
    succeeds and only the commit fails. A test that asserted on
    ``addFeature()``'s return value would pass while nothing reached the file.
    """
    con = sqlite3.connect(path)
    con.execute(f'''CREATE TRIGGER fiberq_no_{operation} BEFORE {operation.upper()} ON "Route"
                    BEGIN SELECT RAISE(ABORT, 'FiberQ test: {operation}s are blocked'); END;''')
    con.commit()
    con.close()


def _on_disk(path):
    """``[(fid, naziv)]`` straight out of SQLite, bypassing QGIS entirely."""
    con = sqlite3.connect(path)
    try:
        return con.execute('SELECT fid, naziv FROM "Route" ORDER BY fid').fetchall()
    finally:
        con.close()


def _select_all(layer):
    layer.selectAll()
    assert len(layer.selectedFeatures()) >= 2


# ---------------------------------------------------------------------------
# 1. the data loss
# ---------------------------------------------------------------------------

def test_a_refused_merge_leaves_both_original_routes_in_the_file(manager, project, tmp_path):
    """The one that matters. Before the fix this left the file EMPTY.

    Measured on the old code: deletes committed, insert refused, two rows became
    zero, and the modal said "Route has been created!".
    """
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)
    _block(path, "insert")
    _select_all(layer)

    manager.merge_all_routes()

    rows = _on_disk(path)
    assert len(rows) == 2, (
        f"the two source routes must still be in the file, found {rows}. The merged route "
        "could not be written, so there was never a reason to remove what it replaces.")
    assert sorted(name for _fid, name in rows) == ["source 1", "source 2"]


def test_a_refused_merge_says_so_and_claims_no_success(manager, project, tmp_path, quiet_dialogs):
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)
    _block(path, "insert")
    _select_all(layer)

    manager.merge_all_routes()

    assert not any("has been created" in said for said in quiet_dialogs), (
        f"a success modal was shown for a merge that never happened: {quiet_dialogs}")
    assert manager.iface.bar.warnings, "nothing was said about the refusal at all"
    reported = " ".join(manager.iface.bar.warnings)
    assert "blocked" in reported or "not added" in reported, (
        f"the message does not carry the provider's own reason: {reported!r}")


def test_a_merge_that_works_puts_one_route_in_the_file_and_removes_the_others(
        manager, project, tmp_path, quiet_dialogs):
    """The ordering change must not break the ordinary case.

    **Characterisation, not proof.** This passes against the pre-fix code too --
    measured -- because the ordinary merge always worked. It is here to catch
    the add-then-delete reordering breaking the case that matters most, not to
    demonstrate the bug.
    """
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)
    _select_all(layer)

    manager.merge_all_routes()

    rows = _on_disk(path)
    assert len(rows) == 1, f"expected exactly the merged route on disk, found {rows}"
    assert rows[0][1] == "Merged route"
    assert any("has been created" in said for said in quiet_dialogs), quiet_dialogs

    fresh = QgsVectorLayer(f"{path}|layername=Route", "fresh", "ogr")
    geom = next(fresh.getFeatures()).geometry()
    assert geom.asWkt().startswith("LineString"), geom.asWkt()
    assert round(geom.length(), 3) == 20.0


def test_a_merge_whose_cleanup_is_refused_says_the_routes_are_counted_twice(
        manager, project, tmp_path, quiet_dialogs):
    """The remaining failure mode of the new ordering, named out loud.

    If the delete is refused the merged route is saved and the originals stay.
    That is a duplicate, which is recoverable and visible -- unlike the data
    loss it replaces -- but the user has to be told, or the network is measured
    twice.
    """
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)
    _block(path, "delete")
    _select_all(layer)

    manager.merge_all_routes()

    rows = _on_disk(path)
    assert len(rows) == 3, f"merged route saved, originals refused, so three rows: {rows}"

    # The consequence goes in the MODAL, not into the error collector. The
    # collector renders its first few reasons and counts the rest, so the one
    # sentence the user has to act on is exactly the one that would be counted.
    said = " ".join(quiet_dialogs)
    assert "counted twice" in said, (
        f"the duplicate was not put in front of the user: {quiet_dialogs} / "
        f"{manager.iface.bar.warnings}")
    assert not any("has been created" in text for text in quiet_dialogs), (
        f"this is not a plain success: {quiet_dialogs}")
    # and the provider's own reason is still recorded for the log
    assert any("blocked" in text or "not deleted" in text
               for text in manager.iface.bar.warnings), manager.iface.bar.warnings


# ---------------------------------------------------------------------------
# 2. the multipart crash
# ---------------------------------------------------------------------------

def test_merging_multipart_routes_does_not_raise(manager, project, tmp_path):
    """A shapefile Route layer is multipart for every feature. Before the fix
    this raised TypeError out of the Qt slot."""
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(
        path,
        ["MultiLineString ((0 0, 10 0))", "MultiLineString ((10 0, 20 0))"],
        geometry_type="MultiLineString")
    project.addMapLayer(layer)
    _select_all(layer)

    manager.merge_all_routes()

    rows = _on_disk(path)
    assert len(rows) == 1, f"the multipart routes should have merged, found {rows}"
    assert rows[0][1] == "Merged route"


def test_every_part_of_a_multipart_route_reaches_the_merge(manager, project, tmp_path):
    """The old fallback took ``multi[0]`` and dropped the rest, so a merge over
    a two-part route silently used half of it. Length is the assertion because
    length is what the user reads off the result."""
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(
        path,
        ["MultiLineString ((0 0, 10 0),(10 0, 30 0))", "MultiLineString ((30 0, 40 0))"],
        geometry_type="MultiLineString")
    project.addMapLayer(layer)
    _select_all(layer)

    manager.merge_all_routes()

    fresh = QgsVectorLayer(f"{path}|layername=Route", "fresh", "ogr")
    rows = list(fresh.getFeatures())
    assert len(rows) == 1, _on_disk(path)
    assert round(rows[0].geometry().length(), 3) == 40.0, (
        f"every part must be chained: 10 + 20 + 10 = 40, got {rows[0].geometry().length()}")


# ---------------------------------------------------------------------------
# 3. the phantom joining segment
# ---------------------------------------------------------------------------

def test_a_gap_the_merge_had_to_bridge_is_reported(manager, project, tmp_path, quiet_dialogs):
    """Two routes 490 m apart used to merge into one 510 m route in silence.

    The dead code that was supposed to catch this tested ``isMultipart()`` on a
    geometry built by ``fromPolylineXY``, which is never multipart.
    """
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (500 0, 510 0)"])
    project.addMapLayer(layer)
    _select_all(layer)

    manager.merge_all_routes()

    said = " ".join(quiet_dialogs)
    assert "not touching" in said or "straight segment" in said, (
        f"the invented 490 m segment was not mentioned: {said!r}")
    assert "490" in said, f"the gap's size is the useful part of the message: {said!r}"


def test_routes_that_meet_at_a_vertex_are_not_reported_as_a_gap(
        manager, project, tmp_path, quiet_dialogs):
    """The other half of the pair, and the one that keeps the gap report honest:
    a warning on every ordinary merge is a warning nobody reads. Routes sharing
    a vertex measure exactly 0.0 apart, measured on all three legs.

    **Characterisation, not proof.** It passes against the pre-fix code as well,
    for the uninteresting reason that the old code warned about nothing at all.
    Its job is to stop the new gap report over-firing, which is a thing only a
    future change can break.
    """
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)
    _select_all(layer)

    manager.merge_all_routes()

    said = " ".join(quiet_dialogs)
    assert "not touching" not in said and "straight segment" not in said, (
        f"a connected merge must not warn about a gap: {said!r}")


# ---------------------------------------------------------------------------
# 4. the user's own edit session
# ---------------------------------------------------------------------------

def test_a_merge_does_not_save_the_user_s_other_unsaved_edits(manager, project, tmp_path):
    """Measured on the old code: one unsaved route of the user's own was written
    to disk by Merge routes, and the layer dropped out of edit mode."""
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)

    layer.startEditing()
    theirs = QgsFeature(layer.fields())
    theirs.setGeometry(QgsGeometry.fromWkt("LineString (100 100, 110 100)"))
    theirs.setAttribute("naziv", "the user's unsaved route")
    assert layer.addFeature(theirs)

    layer.selectByIds([1, 2])
    assert len(layer.selectedFeatures()) == 2
    manager.merge_all_routes()

    names = [name for _fid, name in _on_disk(path)]
    assert "the user's unsaved route" not in names, (
        f"the merge committed the user's own unsaved work: {names}")
    assert layer.isEditable(), "the user's edit session was closed for them"


def test_a_merge_inside_the_user_s_session_says_it_is_not_saved_yet(
        manager, project, tmp_path, quiet_dialogs):
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)
    layer.startEditing()
    layer.selectByIds([1, 2])

    manager.merge_all_routes()

    said = " ".join(quiet_dialogs)
    assert "not saved" in said or "Save Layer Edits" in said, (
        f"the user was not told the merge is still only in the layer: {said!r}")


# ---------------------------------------------------------------------------
# a Route layer missing the columns the merge writes
# ---------------------------------------------------------------------------

def test_a_route_layer_without_the_length_columns_is_reported_not_a_traceback(
        manager, project, tmp_path):
    """``QgsFeature.setAttribute`` RAISES KeyError for a column that is not
    there -- it does not answer False (measured on all three legs). A read-only
    Route layer cannot gain the columns ``_ensure_route_fields`` tries to add,
    so this used to end with a bare ``KeyError: 'duzina'`` and no message."""
    path = str(tmp_path / "bare.gpkg")
    mem = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    mem.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    mem.updateFields()
    for wkt in ("LineString (0 0, 10 0)", "LineString (10 0, 20 0)"):
        feature = QgsFeature(mem.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        feature.setAttribute("naziv", "bare")
        assert mem.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Route"
    assert QgsVectorFileWriter.writeAsVectorFormatV3(
        mem, path, QgsCoordinateTransformContext(), options)[0] == 0
    os.chmod(path, 0o444)

    layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
    assert layer.isValid()
    project.addMapLayer(layer)
    _select_all(layer)

    manager.merge_all_routes()  # must not raise

    assert manager.iface.bar.warnings, "a read-only Route layer produced no message at all"


# ---------------------------------------------------------------------------
# Change route type -- the same defect family, a quieter failure
# ---------------------------------------------------------------------------

def _retag(manager, monkeypatch, label="Underground"):
    """Answer the route-type prompt and run Change route type."""
    monkeypatch.setattr("fiberq.core.route_manager.QInputDialog.getItem",
                        staticmethod(lambda *a, **k: (label, True)))
    manager.change_route_type()


def test_retagging_a_route_layer_without_the_column_is_refused_not_announced(
        manager, project, tmp_path, monkeypatch, quiet_dialogs):
    """Measured on all three legs, on a Route layer whose only columns are fid
    and naziv: ``indexFromName`` answered -1, ``changeAttributeValue(fid, -1,
    value)`` answered False for every feature, ``commitChanges()`` then
    SUCCEEDED because there was nothing to commit, and the user was told
    "Route type has been changed to 'Underground' for 2 route(s)."
    """
    path = str(tmp_path / "bare.gpkg")
    mem = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    mem.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    mem.updateFields()
    for wkt in ("LineString (0 0, 10 0)", "LineString (10 0, 20 0)"):
        feature = QgsFeature(mem.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        feature.setAttribute("naziv", "bare")
        assert mem.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Route"
    assert QgsVectorFileWriter.writeAsVectorFormatV3(
        mem, path, QgsCoordinateTransformContext(), options)[0] == 0

    layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
    project.addMapLayer(layer)
    _select_all(layer)

    _retag(manager, monkeypatch)

    said = " ".join(quiet_dialogs)
    assert "has been changed" not in said, f"a change was announced that never happened: {said!r}"
    assert "tip_trase" in said, f"the missing column is the useful part of the message: {said!r}"
    # Refusing rather than adding the column is the deliberate choice: the user
    # asked to re-tag routes, not to alter the layer's schema.
    con = sqlite3.connect(path)
    try:
        columns = [row[1] for row in con.execute('PRAGMA table_info("Route")')]
    finally:
        con.close()
    assert "tip_trase" not in columns, (
        f"the layer's schema was changed behind the user's back: {columns}")


def test_a_refused_retag_does_not_claim_the_type_changed(
        manager, project, tmp_path, monkeypatch, quiet_dialogs):
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)
    _block(path, "update")
    _select_all(layer)

    _retag(manager, monkeypatch)

    assert not any("has been changed" in text for text in quiet_dialogs), (
        f"the retag was refused by the file and still announced: {quiet_dialogs}")
    assert manager.iface.bar.warnings, "nothing was said about the refusal"

    con = sqlite3.connect(path)
    try:
        types = [row[0] for row in con.execute('SELECT tip_trase FROM "Route" ORDER BY fid')]
    finally:
        con.close()
    assert types == ["vazdusna", "vazdusna"], f"the file should be untouched, found {types}"


def test_a_retag_that_works_reaches_the_file(
        manager, project, tmp_path, monkeypatch, quiet_dialogs):
    """Characterisation of the happy path: it worked before and must keep
    working. It passes against the pre-fix code too."""
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)
    _select_all(layer)

    _retag(manager, monkeypatch)

    con = sqlite3.connect(path)
    try:
        types = [row[0] for row in con.execute('SELECT tip_trase FROM "Route" ORDER BY fid')]
    finally:
        con.close()
    assert types == ["podzemna", "podzemna"], types
    assert any("has been changed" in text for text in quiet_dialogs), quiet_dialogs


def test_a_retag_does_not_save_the_user_s_other_unsaved_edits(
        manager, project, tmp_path, monkeypatch):
    path = str(tmp_path / "routes.gpkg")
    layer = _gpkg_route_layer(path, ["LineString (0 0, 10 0)", "LineString (10 0, 20 0)"])
    project.addMapLayer(layer)

    layer.startEditing()
    theirs = QgsFeature(layer.fields())
    theirs.setGeometry(QgsGeometry.fromWkt("LineString (100 100, 110 100)"))
    theirs.setAttribute("naziv", "the user's unsaved route")
    assert layer.addFeature(theirs)

    layer.selectByIds([1, 2])
    _retag(manager, monkeypatch)

    names = [name for _fid, name in _on_disk(path)]
    assert "the user's unsaved route" not in names, (
        f"the retag committed the user's own unsaved work: {names}")
    assert layer.isEditable(), "the user's edit session was closed for them"
