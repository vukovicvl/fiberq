"""A cable restyle opens an edit session only when an old type value needs migrating.

Every cable restyle -- after each Lay cable, after each slack recompute, twice
per cable layer at project open -- runs ``_migrate_cable_type_values``, which
rewrites the pre-English ``tip`` values ``opticki`` and ``bakarnI``. It used to
put the layer into edit mode first, look, and roll the session back when there
was nothing to change, which on any project made since the English rename is
every time.

That roll-back is not harmless. In a project whose transaction mode is
"Buffered groups" (QGIS 3.26+), ``rollBack()`` rolls back the WHOLE project.
The first Lay cable creates the cable layer while the user is editing, the
restyle that follows migrates it, and every unsaved edit in the project was
thrown away and the session ended (measured on 3.40.15, 3.44.15 and 4.2.3).

The migration now finds its rows first and opens a session only when one of
them needs changing. The first two tests fail on the parent; the next two pin
what it did and still does.

**WP4 4.1, item PF-s** (supporting): where the provider can be asked, it is
asked for the old values only, and only for the ``tip`` column, instead of
every cable whole. The counted test fails on the parent; the rest pin the
states where asking would answer differently -- an edit buffer, a field added
or deleted in it, a shapefile's stale attribute index, an index that hands
rows back by value -- and each catches the mutant that asks there anyway.
"""
import glob

import pytest
from qgis.core import (
    Qgis,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from fiberq.utils.field_aliases import _migrate_cable_type_values


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.clear()
    yield prj
    prj.clear()


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


def _cables(project, values):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857&field=tip:string&field=podtip:string",
                           "Underground cables", "memory")
    features = []
    for i, value in enumerate(values):
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(i * 10, 0), QgsPointXY(i * 10 + 5, 0)]))
        feat["tip"] = value
        features.append(feat)
    assert layer.dataProvider().addFeatures(features)[0]
    project.addMapLayer(layer)
    return layer


def _signals(layer):
    seen = []
    for name in ("editingStarted", "editingStopped", "beforeRollBack", "afterRollBack"):
        getattr(layer, name).connect(lambda *a, name=name: seen.append(name))
    return seen


def test_a_layer_with_nothing_to_migrate_is_not_put_into_edit_mode(project):
    cables = _cables(project, ["Optical", "Copper", None])
    seen = _signals(cables)
    _migrate_cable_type_values(cables)
    assert seen == []
    assert not cables.isEditable()


@pytest.mark.skipif(not hasattr(QgsProject, "setTransactionMode"),
                    reason="transaction modes arrived in QGIS 3.26")
def test_migrating_a_new_cable_layer_keeps_the_projects_unsaved_edits(project):
    """The first Lay cable, in a Buffered-groups project with work in progress."""
    project.setTransactionMode(Qgis.TransactionMode.BufferedGroups)
    poles = QgsVectorLayer("Point?crs=EPSG:3857&field=naziv:string", "Poles", "memory")
    project.addMapLayer(poles)
    assert project.startEditing(poles)
    pole = QgsFeature(poles.fields())
    pole.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(10, 10)))
    pole["naziv"] = "unsaved pole"
    assert poles.addFeature(pole)
    try:
        cables = _cables(project, [])
        _migrate_cable_type_values(cables)
        assert [f["naziv"] for f in poles.getFeatures()] == ["unsaved pole"]
        assert poles.isEditable()
    finally:
        poles.rollBack()      # in Buffered groups this rolls back the whole project


def test_old_values_are_migrated_and_saved(project):
    cables = _cables(project, ["opticki", "bakarnI", "Optical", "opticki "])
    seen = _signals(cables)
    _migrate_cable_type_values(cables)
    assert [f["tip"] for f in cables.getFeatures()] == ["Optical", "Copper", "Optical", "opticki "]
    assert not cables.isEditable() and not cables.isModified()
    assert seen == ["editingStarted", "editingStopped"]


def test_a_layer_already_being_edited_is_migrated_inside_that_session(project):
    cables = _cables(project, ["Optical", "Copper"])
    assert cables.startEditing()
    first = min(f.id() for f in cables.getFeatures())
    assert cables.changeAttributeValue(first, cables.fields().indexOf("tip"), "opticki")
    _migrate_cable_type_values(cables)
    assert cables.isEditable() and cables.isModified()
    assert cables.getFeature(first)["tip"] == "Optical"
    cables.rollBack()


# ---------------------------------------------------------------------------
# PF-s: only the old values are read, where that answers as the whole read did
# ---------------------------------------------------------------------------

def _saved(project, tmp_path, values, driver, name="cables"):
    """A cable layer written to a file and read back through OGR.

    Kept out of the project: the migration takes the layer itself, and a
    file layer in the project is opened by other readers too -- on QGIS 4.2
    one of them, reading a GeoPackage the test had just written while the
    test opened it for editing, left the test unable to read it.
    """
    source = QgsVectorLayer("LineString?crs=EPSG:3857&field=tip:string&field=naziv:string",
                            "Underground cables", "memory")
    features = []
    for i, value in enumerate(values):
        feat = QgsFeature(source.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(i * 10, 0), QgsPointXY(i * 10 + 5, 0)]))
        feat["tip"] = value
        feat["naziv"] = f"K{i + 1}"
        features.append(feat)
    assert source.dataProvider().addFeatures(features)[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver
    options.layerName = name
    path = str(tmp_path / (f"{name}.gpkg" if driver == "GPKG" else f"{name}.shp"))
    written = QgsVectorFileWriter.writeAsVectorFormatV3(source, path, QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    layer = QgsVectorLayer(f"{path}|layername={name}" if driver == "GPKG" else path, "Underground cables", "ogr")
    assert layer.isValid()
    return layer, path


def _layer(project, tmp_path, storage, values):
    if storage == "memory":
        return _cables(project, values)
    return _saved(project, tmp_path, values, "GPKG")[0]


def _read_counts(project, tmp_path, storage, n):
    project.removeAllMapLayers()
    layer = _layer(project, tmp_path / f"{storage}{n}", storage, ["Optical", "Copper"] * (n // 2))
    handed = []
    real_get = QgsVectorLayer.getFeatures

    def get(self, *args, **kwargs):
        for feat in real_get(self, *args, **kwargs):
            handed.append(feat.id())
            yield feat

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(QgsVectorLayer, "getFeatures", get)
        _migrate_cable_type_values(layer)
    return len(handed)


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_restyle_with_nothing_to_migrate_reads_no_cable(project, tmp_path, storage):
    """The parent read every cable whole on every restyle: 100 then 400 here.

    On a GeoPackage SQLite answers the question; a memory layer answers it in
    C++, so there the count is what reaches Python only.
    """
    (tmp_path / f"{storage}100").mkdir()
    (tmp_path / f"{storage}400").mkdir()
    assert (_read_counts(project, tmp_path, storage, 100), _read_counts(project, tmp_path, storage, 400)) == (0, 0)


def test_an_attribute_index_does_not_change_the_order_of_the_changes(project, tmp_path):
    """SQLite answers through an index on "tip" by value: bakarnI rows first. The changes keep fid order."""
    layer, _path = _saved(project, tmp_path, ["opticki", "bakarnI", "opticki", "bakarnI"], "GPKG")
    assert layer.dataProvider().createAttributeIndex(layer.fields().indexOf("tip"))
    names = {f.id(): f["naziv"] for f in layer.getFeatures()}
    order = []
    layer.attributeValueChanged.connect(lambda fid, idx, value: order.append(names[fid]))
    _migrate_cable_type_values(layer)
    assert order == ["K1", "K2", "K3", "K4"]
    assert [f["tip"] for f in layer.getFeatures()] == ["Optical", "Copper", "Optical", "Copper"]


def test_a_shapefiles_stale_attribute_index_does_not_hide_a_value(project, tmp_path):
    """QGIS edits do not update a shapefile's .idm/.ind, so a query on "tip" misses this row."""
    layer, path = _saved(project, tmp_path, ["Optical", "Copper", "Optical", "Optical"], "ESRI Shapefile")
    assert layer.dataProvider().createAttributeIndex(layer.fields().indexOf("tip"))
    assert glob.glob(path[:-4] + ".i*"), "premise: OGR wrote the attribute index"
    # Opened again, as a project reopened after the index was made would be.
    layer = QgsVectorLayer(path, "Underground cables", "ogr")
    tip = layer.fields().indexOf("tip")
    edited = sorted(layer.allFeatureIds())[2]
    assert layer.startEditing()
    assert layer.changeAttributeValue(edited, tip, "opticki")
    assert layer.commitChanges(), layer.commitErrors()
    assert not list(layer.getFeatures("\"tip\" = 'opticki'")), "premise: the index is stale"
    _migrate_cable_type_values(layer)
    reread = QgsVectorLayer(path, "reread", "ogr")
    assert [f["tip"] for f in reread.getFeatures()] == ["Optical", "Copper", "Optical", "Optical"]


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_type_column_added_in_the_edit_buffer_is_migrated(project, tmp_path, storage):
    layer = _layer(project, tmp_path, storage, ["Optical", "Copper", "Optical"])
    assert layer.startEditing()
    assert layer.deleteAttribute(layer.fields().indexOf("tip"))
    string = QVariant.String if hasattr(QVariant, "String") else QVariant.Type.String
    assert layer.addAttribute(QgsField("tip", string))
    tip = layer.fields().indexOf("tip")
    fids = sorted(layer.allFeatureIds())
    assert layer.changeAttributeValue(fids[0], tip, "opticki")
    assert layer.changeAttributeValue(fids[2], tip, "bakarnI")
    try:
        _migrate_cable_type_values(layer)
        assert [layer.getFeature(fid)["tip"] for fid in fids] == ["Optical", None, "Copper"]
    finally:
        layer.rollBack()


def test_a_field_deleted_before_the_type_column_in_the_edit_buffer_does_not_hide_the_rows(project):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857&field=kind:string&field=tip:string",
                           "Underground cables", "memory")
    features = []
    for value in ("opticki", "Optical", "bakarnI", "x", "opticki"):
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(5, 0)]))
        feat["kind"] = "k"
        feat["tip"] = value
        features.append(feat)
    assert layer.dataProvider().addFeatures(features)[0]
    project.addMapLayer(layer)
    assert layer.startEditing()
    assert layer.deleteAttribute(layer.fields().indexOf("kind"))
    try:
        _migrate_cable_type_values(layer)
        assert [f["tip"] for f in layer.getFeatures()] == ["Optical", "Optical", "Copper", "x", "Optical"]
    finally:
        layer.rollBack()


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_undo_after_a_migration_in_the_users_session_reverts_what_it_always_did(project, tmp_path, storage):
    """Two cables digitised typed "opticki", then K2's type re-picked; the restyle migrates all three.

    The whole read meets the new cables first, in the order they were added,
    then the saved ones, so the undo stack ends NEW1, NEW2, K2 and two Undos
    revert K2's change and NEW2's. A query on the type hands the changed row
    back first, and sorting the ids would put NEW2 before NEW1: the buffer's
    temporary ids count down.
    """
    layer = _layer(project, tmp_path, storage, ["Optical", "Optical", "Optical"])
    tip = layer.fields().indexOf("tip")
    k2 = sorted(layer.allFeatureIds())[1]
    assert layer.startEditing()
    new = []
    for y in (50, 60):
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, y), QgsPointXY(50, y)]))
        feat["tip"] = "opticki"
        assert layer.addFeature(feat)
        new.append(feat.id())
    assert layer.changeAttributeValue(k2, tip, "opticki")
    try:
        _migrate_cable_type_values(layer)
        layer.undoStack().undo()
        layer.undoStack().undo()
        assert [layer.getFeature(fid)["tip"] for fid in (*new, k2)] == ["Optical", "opticki", "opticki"]
    finally:
        layer.rollBack()


def test_the_query_reads_the_type_column_only(project, tmp_path):
    """setFlags() after setSubsetOfAttributes() would clear the subset and read every column."""
    layer = _layer(project, tmp_path, "gpkg", ["opticki", "Copper"])
    requests = []
    real_get = QgsVectorLayer.getFeatures

    def get(self, *args, **kwargs):
        requests.extend(args)
        return real_get(self, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(QgsVectorLayer, "getFeatures", get)
        _migrate_cable_type_values(layer)
    request = requests[0]
    assert request.flags() & QgsFeatureRequest.Flag.SubsetOfAttributes
    assert request.flags() & QgsFeatureRequest.Flag.NoGeometry
    assert request.subsetOfAttributes() == [layer.fields().indexOf("tip")]


def _indexed(project, tmp_path, columns, rows, index_on):
    """A GeoPackage cable layer with an attribute index; ``rows`` are value tuples in ``columns`` order."""
    source = QgsVectorLayer("LineString?crs=EPSG:3857&" + "&".join(f"field={c}:string" for c in columns),
                            "Underground cables", "memory")
    features = []
    for i, row in enumerate(rows):
        feat = QgsFeature(source.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(i * 10, 0), QgsPointXY(i * 10 + 5, 0)]))
        for column, value in zip(columns, row):
            feat[column] = value
        features.append(feat)
    assert source.dataProvider().addFeatures(features)[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "cables"
    path = str(tmp_path / "indexed.gpkg")
    written = QgsVectorFileWriter.writeAsVectorFormatV3(source, path, QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    layer = QgsVectorLayer(f"{path}|layername=cables", "Underground cables", "ogr")
    assert layer.isValid()
    assert layer.dataProvider().createAttributeIndex(layer.fields().indexOf(index_on))
    return layer


def _change_order(layer):
    order = []
    layer.attributeValueChanged.connect(lambda fid, idx, value: order.append(fid))
    return order


def test_a_filter_answered_through_an_index_keeps_the_whole_reads_order(project, tmp_path):
    """The filter is on naziv, indexed, so SQLite returns the rows in naziv order, not fid order."""
    rows = [("opticki", "N9"), ("Optical", "N2"), ("bakarnI", "N1"), ("opticki", "N5"), ("Copper", "N4"),
            ("bakarnI", "N3")]
    layer = _indexed(project, tmp_path, ["tip", "naziv"], rows, "naziv")
    assert layer.setSubsetString('"naziv" >= \'N\'')
    whole_read = [f.id() for f in layer.getFeatures() if f["tip"] in ("opticki", "bakarnI")]
    assert whole_read != sorted(whole_read), "premise: the filtered read is not in fid order"
    order = _change_order(layer)
    _migrate_cable_type_values(layer)
    assert order == whole_read


def test_an_edited_layer_is_read_whole_as_before(project, tmp_path):
    """A tip-only table with an index on tip: a read without geometry is answered by the index, in value order."""
    rows = [("opticki",), ("bakarnI",), ("Optical",), ("opticki",), ("bakarnI",)]
    layer = _indexed(project, tmp_path, ["tip"], rows, "tip")
    assert layer.startEditing()
    try:
        whole_read = [f.id() for f in layer.getFeatures() if f["tip"] in ("opticki", "bakarnI")]
        order = _change_order(layer)
        _migrate_cable_type_values(layer)
        assert order == whole_read
    finally:
        layer.rollBack()
