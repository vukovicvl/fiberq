"""Recording an add reads the features near it, and still records the scan's answer.

WP4 task 4.1, item PF-6. Every placement tool calls ``record_add`` after its
commit, and the feature object still carries its temporary negative id then
(verified), so ``_find_committed_fid`` looked the committed feature up by
geometry: every feature of the layer, one GEOS distance each, keeping the
highest fid within 1 mm. 27-71 ms per add at 25k features, on v1.5.0.

Now it reads the features whose box meets the target's, keeps the highest
match among them, W, and asks the layer once whether it holds any feature
above W. If it holds none, no match can be above W either, wherever it lies,
so W is the scan's answer. Otherwise -- and on a layer being edited, or a
provider other than memory or a GeoPackage -- it scans, as before.

That makes the answer the scan's in every state, including the ones the
design review found where the scan's answer is not the new feature: a far
one-vertex line, which GEOS measures as -1 from everything, added after the
target; a multipart whose only part has one vertex, measured as 0.0; an undo
of a delete, which a GeoPackage re-adds at its OLD fid. The scan's answer is
kept there too, whatever it is: changing it is not a performance change.

**Counted, not timed**, as branch 11 did. On a GeoPackage the two reads are
the R-tree and the primary key. A memory layer has neither index in v1.6.0
(PF-5 adds the spatial one), so there the counts are the features handed to
Python only: the C++ passes behind them still read every feature, without
the GEOS distance each.
"""
import random

import pytest
from qgis.core import (
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

from fiberq.core.undo_manager import FiberQUndoManager


class _Bar:
    def __init__(self):
        self.infos, self.warnings = [], []

    def pushInfo(self, title, text):
        self.infos.append(text)

    def pushWarning(self, title, text):
        self.warnings.append(text)

    pushSuccess = pushInfo
    pushCritical = pushWarning


class _Iface:
    def __init__(self):
        self.bar = _Bar()

    def messageBar(self):
        return self.bar


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture(autouse=True)
def canvas_not_rendering(qgis_canvas):
    """pytest-qgis's canvas renders every layer added to the project, in a worker thread.

    On QGIS 4.2 a render opening a GeoPackage a test had just written, while
    the test opened it for editing, left the test's own connection unable
    to read the file (35 of 40 tries in the code review). No test here needs
    the canvas to draw.
    """
    qgis_canvas.setRenderFlag(False)
    yield
    qgis_canvas.setRenderFlag(True)


@pytest.fixture
def manager():
    return FiberQUndoManager(_Iface())


def _scan(layer, geom_wkt):
    """The parent's ``_find_committed_fid``, reading every feature."""
    target = QgsGeometry.fromWkt(geom_wkt)
    if not target or target.isEmpty():
        return None
    best = None
    for f in layer.getFeatures():
        fg = f.geometry()
        if fg and not fg.isEmpty() and target.distance(fg) < 0.001:
            if best is None or f.id() > best:
                best = f.id()
    return best


def _layer(project, tmp_path, storage, kind="MultiLineString"):
    """An empty layer with a name column, in memory or in a GeoPackage."""
    mem = QgsVectorLayer(f"{kind}?crs=EPSG:3857", "Underground cables", "memory")
    mem.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    mem.updateFields()
    layer = mem
    if storage == "gpkg":
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = "cables"
        path = str(tmp_path / f"cables_{random.random():.12f}.gpkg")
        written = QgsVectorFileWriter.writeAsVectorFormatV3(
            mem, path, QgsCoordinateTransformContext(), options)
        assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
        layer = QgsVectorLayer(f"{path}|layername=cables", "Underground cables", "ogr")
        assert layer.isValid()
    project.addMapLayer(layer)
    return layer


def _feature(layer, wkt, name):
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromWkt(wkt))
    feature.setAttribute("name", name)
    return feature


def _commit(layer, *items):
    """Add ``(wkt, name)`` items in one edit session; the feature objects, ids still temporary."""
    assert layer.startEditing()
    features = [_feature(layer, wkt, name) for wkt, name in items]
    for feature in features:
        assert layer.addFeature(feature)
    assert layer.commitChanges(), layer.commitErrors()
    return features


def _named(layer, fid):
    return None if fid is None else layer.getFeature(fid)["name"]


def _recorded(manager, layer, feature):
    """What ``record_add`` puts on the stack for ``feature``, as a fid and the name there."""
    manager.record_add(layer, feature)
    fid = manager._undo_stack[-1].feature_id
    return fid, _named(layer, fid)


# ---------------------------------------------------------------------------
# The work per add
# ---------------------------------------------------------------------------

def _counting(patch):
    """Features handed out by QgsVectorLayer.getFeatures, and GEOS distances measured."""
    counts = {"features": 0, "distance": 0}
    real_get = QgsVectorLayer.getFeatures
    real_distance = QgsGeometry.distance

    def get(self, *args, **kwargs):
        for feat in real_get(self, *args, **kwargs):
            counts["features"] += 1
            yield feat

    def distance(self, *args, **kwargs):
        counts["distance"] += 1
        return real_distance(self, *args, **kwargs)

    patch.setattr(QgsVectorLayer, "getFeatures", get)
    patch.setattr(QgsGeometry, "distance", distance)
    return counts


def _add_counts(project, tmp_path, storage, n):
    project.removeAllMapLayers()
    layer = _layer(project, tmp_path, storage)
    _commit(layer, *[(f"MultiLineString (({i * 10} 0, {i * 10 + 5} 0))", f"c{i}") for i in range(n)])
    new, = _commit(layer, ("MultiLineString ((1000 50, 1005 50))", "new"))
    with pytest.MonkeyPatch.context() as patch:
        counts = _counting(patch)
        recorded = _recorded(FiberQUndoManager(_Iface()), layer, new)
    assert recorded[1] == "new"
    return counts["features"], counts["distance"]


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_recording_an_add_reads_what_is_near_it_not_the_whole_layer(project, tmp_path, storage):
    """The parent read n + 1 features and measured n + 1 distances for one record_add.

    At n = 200 and n = 800 that was 201 against 801 of each: x4 for x4 the
    layer. Now both stay where they are: the one feature near the new one.
    """
    small = _add_counts(project, tmp_path, storage, 200)
    large = _add_counts(project, tmp_path, storage, 800)
    assert large == small, (small, large)
    assert small == (1, 1), small


# ---------------------------------------------------------------------------
# The answer: the scan's, in every state the review found
# ---------------------------------------------------------------------------

STORAGES = ["memory", "gpkg"]


@pytest.mark.parametrize("storage", STORAGES)
def test_a_placement_records_the_new_feature(project, tmp_path, manager, storage):
    layer = _layer(project, tmp_path, storage)
    _commit(layer, ("MultiLineString ((0 0, 10 0))", "old"))
    new, = _commit(layer, ("MultiLineString ((20 0, 30 0))", "new"))
    assert _recorded(manager, layer, new)[1] == "new"
    assert manager._undo_stack[-1].feature_id == _scan(layer, new.geometry().asWkt())


@pytest.mark.parametrize("storage", STORAGES)
@pytest.mark.parametrize("degenerate", [
    "LineString (9000 9000)",               # GEOS: -1 from everything
    "MultiLineString ((9000 9000))",        # GEOS: 0.0 from everything
], ids=["one-vertex line", "one-vertex multipart"])
def test_a_feature_every_target_matches_keeps_the_scans_answer_when_newer(
        project, tmp_path, manager, storage, degenerate):
    """The scan keeps the highest fid within 1 mm, and this one is within 1 mm of everything.

    Added after the target, it is the scan's answer (and Undo would delete
    it); the probe for a feature above the target's fid sends this to the scan.
    """
    layer = _layer(project, tmp_path, storage)
    target, = _commit(layer, ("MultiLineString ((0 0, 10 0))", "target"))
    _commit(layer, (degenerate, "degenerate"))
    fid, name = _recorded(manager, layer, target)
    assert fid == _scan(layer, target.geometry().asWkt())
    assert name == "degenerate", "premise: the scan's answer is the degenerate feature"


@pytest.mark.parametrize("storage", STORAGES)
def test_a_feature_every_target_matches_does_not_win_when_older(project, tmp_path, manager, storage):
    layer = _layer(project, tmp_path, storage)
    _commit(layer, ("LineString (9000 9000)", "degenerate"))
    target, = _commit(layer, ("MultiLineString ((0 0, 10 0))", "target"))
    assert _recorded(manager, layer, target) == (_scan(layer, target.geometry().asWkt()), "target")


@pytest.mark.parametrize("storage", STORAGES)
def test_a_later_feature_of_the_same_commit_does_not_take_the_record(project, tmp_path, manager, storage):
    """The newest row is not always the target: the record is still the target's."""
    layer = _layer(project, tmp_path, storage)
    target, _later = _commit(layer, ("MultiLineString ((0 0, 10 0))", "target"),
                             ("MultiLineString ((5000 0, 5010 0))", "later"))
    assert _recorded(manager, layer, target) == (_scan(layer, target.geometry().asWkt()), "target")


@pytest.mark.parametrize("storage", STORAGES)
def test_coincident_features_record_the_newer(project, tmp_path, manager, storage):
    layer = _layer(project, tmp_path, storage)
    _commit(layer, ("MultiLineString ((0 0, 10 0))", "first"))
    second, = _commit(layer, ("MultiLineString ((0 0, 10 0))", "second"))
    assert _recorded(manager, layer, second) == (_scan(layer, second.geometry().asWkt()), "second")


@pytest.mark.parametrize("storage", STORAGES)
def test_a_target_still_in_the_edit_buffer_is_looked_up_as_before(project, tmp_path, manager, storage):
    """A session the user owns is not committed: the target keeps a temporary id, the lowest."""
    layer = _layer(project, tmp_path, storage)
    _commit(layer, ("MultiLineString ((0 0, 10 0))", "saved"), ("LineString (9000 9000)", "degenerate"))
    assert layer.startEditing()
    target = _feature(layer, "MultiLineString ((20 0, 30 0))", "buffered")
    assert layer.addFeature(target)
    try:
        fid, name = _recorded(manager, layer, target)
        assert fid == _scan(layer, target.geometry().asWkt())
        assert name == "degenerate", "premise: the scan reads through the buffer and finds the newer row"
    finally:
        layer.rollBack()


@pytest.mark.parametrize("storage", STORAGES)
def test_a_layer_whose_rows_are_all_in_the_edit_buffer_is_looked_up_as_before(
        project, tmp_path, manager, storage):
    """No saved row to compare with: only the scan knows which buffered id is the higher.

    A GeoPackage's buffered adds have no ``fid`` value yet, so a query on that
    column cannot see them; this is why a layer being edited is scanned.
    """
    layer = _layer(project, tmp_path, storage)
    assert layer.startEditing()
    degenerate = _feature(layer, "LineString (9000 9000)", "degenerate")
    target = _feature(layer, "MultiLineString ((20 0, 30 0))", "buffered")
    assert layer.addFeature(degenerate) and layer.addFeature(target)
    try:
        fid, name = _recorded(manager, layer, target)
        assert fid == _scan(layer, target.geometry().asWkt())
        assert name == "degenerate", "premise: the scan keeps the higher temporary id"
    finally:
        layer.rollBack()


def test_undoing_a_delete_on_a_geopackage_records_the_scans_answer(project, tmp_path, manager):
    """The re-added row keeps its OLD fid, so it is not the newest; the scan's answer stands."""
    layer = _layer(project, tmp_path, "gpkg")
    _commit(layer, ("MultiLineString ((0 0, 10 0))", "deleted"), ("MultiLineString ((20 0, 30 0))", "kept"),
            ("LineString (9000 9000)", "degenerate"))
    victim = next(f for f in layer.getFeatures() if f["name"] == "deleted")
    manager.record_delete(layer, victim)
    assert layer.startEditing()
    assert layer.deleteFeature(victim.id())
    assert layer.commitChanges()
    assert manager.undo() is True
    redo = manager._redo_stack[-1]
    assert redo.feature_id == _scan(layer, redo.geometry_wkt)
    assert _named(layer, redo.feature_id) == "degenerate", "premise: the scan's answer is the newer row"


@pytest.mark.parametrize("storage", STORAGES)
def test_every_feature_of_a_mixed_layer_looks_up_as_the_scan_does(project, tmp_path, manager, storage):
    """Lines, points' worth of zero-length lines, degenerate rows and coincident ones, in random commits."""
    rng = random.Random(606)
    layer = _layer(project, tmp_path, storage)
    shapes = []
    for i in range(160):
        roll = rng.random()
        x, y = rng.uniform(0, 500), rng.uniform(0, 500)
        if roll < 0.04:
            shapes.append(("LineString (%r %r)" % (x, y), f"lone{i}"))
        elif roll < 0.07:
            shapes.append(("MultiLineString ((%r %r))" % (x, y), f"lonemulti{i}"))
        elif roll < 0.20 and shapes:
            shapes.append((rng.choice(shapes)[0], f"copy{i}"))
        elif roll < 0.30:
            shapes.append(("MultiLineString ((%r %r, %r %r))" % (x, y, x, y), f"zero{i}"))
        else:
            shapes.append(("MultiLineString ((%r %r, %r %r))" % (x, y, x + rng.uniform(-30, 30),
                                                                 y + rng.uniform(-30, 30)), f"line{i}"))
    added = []
    while shapes:
        size = rng.randint(1, 4)
        batch, shapes = shapes[:size], shapes[size:]
        added += _commit(layer, *batch)
        for feature in rng.sample(added, min(3, len(added))) + added[-len(batch):]:
            wkt = feature.geometry().asWkt()
            assert manager._find_committed_fid(layer, wkt) == _scan(layer, wkt), wkt
    for feature in layer.getFeatures():
        wkt = feature.geometry().asWkt()
        assert manager._find_committed_fid(layer, wkt) == _scan(layer, wkt), wkt
    for _ in range(100):
        wkt = QgsGeometry.fromPointXY(QgsPointXY(rng.uniform(0, 500), rng.uniform(0, 500))).asWkt()
        assert manager._find_committed_fid(layer, wkt) == _scan(layer, wkt), wkt


def test_a_filtered_memory_layer_is_scanned_as_before(project, tmp_path, manager):
    """A memory layer's filter is evaluated per feature by every read; one scan is the cheapest exact read."""
    layer = _layer(project, tmp_path, "memory")
    _commit(layer, ("MultiLineString ((0 0, 10 0))", "hidden"), ("MultiLineString ((20 0, 30 0))", "shown"))
    assert layer.setSubsetString('"name" = \'shown\' OR "name" = \'new\'')
    new, = _commit(layer, ("MultiLineString ((40 0, 50 0))", "new"))
    with pytest.MonkeyPatch.context() as patch:
        counts = _counting(patch)
        recorded = _recorded(manager, layer, new)
    assert recorded == (_scan(layer, new.geometry().asWkt()), "new")
    assert counts["features"] == 2, "the scan reads the two features the filter shows, once"
