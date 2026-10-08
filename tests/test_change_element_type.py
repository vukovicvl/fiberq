"""Changing an element's type copied its attributes, and saved your other work.

WP4 4.2 item R7. Branch ``fix/wp4-write-paths``.

``_copy_attributes_between_layers`` maps one feature's attributes onto another
layer's column names. It is reached from "Change element type", which moves an
element from one layer to another: the copy decides what the moved element knows
about itself, and the original is deleted afterwards. Two measured defects, both
silent.

**It committed the user's unsaved work.** ``dataProvider().addAttributes()``
needs no edit session -- measured on 3.22.16, 3.44.15 and 4.0.3, the column
reaches the file with ``isEditable()`` False throughout. So the
``startEditing()``/``commitChanges()`` pair that used to wrap it never committed
the columns at all. All it ever committed was whatever else was in the
destination layer's buffer, which is the user's own work. Measured: a
destination layer the user had in edit mode with one unsaved point, one Change
element type click, and that point was on disk with the layer dropped out of
edit mode -- saved by a function whose name says it copies attributes.

**It blanked the values it could not make room for.** ``addAttributes()``
answers False on a read-only file and on a duplicate column name. When it did,
the destination map was rebuilt without the new columns and those values simply
vanished. Measured on a read-only destination GeoPackage: the result came back
``{'naziv': 'pole 7'}`` where the source feature had ``operator='Telekom'``.
The element was moved with its columns blanked, the original deleted, and the
message bar said "Element changed to: OTB".

Four of the seven tests below go red against a tree with only this fix reverted.
The three that do not are marked **characterisation** in their own docstrings and
say why.

The tests below drive the real function. The ones about ``addAttributes``
failing monkeypatch its return value rather than using file permissions,
because a chmod-444 GeoPackage behaves differently on the 3.22 floor -- it
reported the failed column as present in ``layer.fields()`` in one probe and
absent in another -- and a test whose premise is unstable across the supported
range proves nothing on the leg that matters.
"""
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

from fiberq.core.layer_manager import _copy_attributes_between_layers
from fiberq.utils.errors import OperationErrors


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


def _source_feature(fields_and_values):
    """A standalone feature carrying the attributes a moved element would have."""
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "src", "memory")
    layer.dataProvider().addAttributes([QgsField(n, t) for n, t, _v in fields_and_values])
    layer.updateFields()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromWkt("Point (1 1)"))
    for name, _type, value in fields_and_values:
        feature.setAttribute(name, value)
    assert layer.dataProvider().addFeatures([feature])[0]
    return next(layer.getFeatures())


def _gpkg_point_layer(path, columns, rows=()):
    mem = QgsVectorLayer("Point?crs=EPSG:3857", "Poles", "memory")
    mem.dataProvider().addAttributes([QgsField(n, t) for n, t in columns])
    mem.updateFields()
    for values in rows:
        feature = QgsFeature(mem.fields())
        feature.setGeometry(QgsGeometry.fromWkt("Point (0 0)"))
        for name, value in values.items():
            feature.setAttribute(name, value)
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


def _names_on_disk(path):
    con = sqlite3.connect(path)
    try:
        return sorted(str(row[0]) for row in con.execute('SELECT naziv FROM "Poles"'))
    finally:
        con.close()


# ---------------------------------------------------------------------------
# the user's own edit session
# ---------------------------------------------------------------------------

def test_copying_attributes_does_not_save_the_user_s_unsaved_work(project, tmp_path):
    """The defect that gave this its own commit.

    The destination needs a column it does not have, which is the only branch
    that used to open an edit session -- and the session it opened committed the
    user's buffer, not the column.
    """
    path = str(tmp_path / "poles.gpkg")
    layer = _gpkg_point_layer(path, [("naziv", QVariant.String)])
    project.addMapLayer(layer)

    layer.startEditing()
    theirs = QgsFeature(layer.fields())
    theirs.setGeometry(QgsGeometry.fromWkt("Point (99 99)"))
    theirs.setAttribute("naziv", "the user's unsaved pole")
    assert layer.addFeature(theirs)

    source = _source_feature([("naziv", QVariant.String, "pole 7"),
                              ("operator", QVariant.String, "Telekom")])

    with OperationErrors("test") as errors:
        _copy_attributes_between_layers(source, layer, errors)

    assert "the user's unsaved pole" not in _names_on_disk(path), (
        "copying attributes committed the user's own unsaved feature")
    assert layer.isEditable(), "the user's edit session was closed for them"


def test_the_missing_column_still_reaches_the_file(project, tmp_path):
    """The other half: removing the edit session must not stop the column being
    added. ``addAttributes()`` goes straight to the provider -- measured on all
    three legs, the column lands with ``isEditable()`` False throughout.

    **Characterisation, not proof.** It passes against the pre-fix code too,
    which also added the column -- just via an edit session that committed the
    user's work instead of the column. Its job is to stop the removal of that
    session taking the column with it.
    """
    path = str(tmp_path / "poles.gpkg")
    layer = _gpkg_point_layer(path, [("naziv", QVariant.String)])
    project.addMapLayer(layer)
    source = _source_feature([("naziv", QVariant.String, "pole 7"),
                              ("operator", QVariant.String, "Telekom")])

    with OperationErrors("test") as errors:
        vals = _copy_attributes_between_layers(source, layer, errors)

    con = sqlite3.connect(path)
    try:
        columns = [row[1] for row in con.execute('PRAGMA table_info("Poles")')]
    finally:
        con.close()
    assert "operator" in columns, f"the column never reached the file: {columns}"
    assert vals.get("operator") == "Telekom", vals


# ---------------------------------------------------------------------------
# a column that could not be added
# ---------------------------------------------------------------------------

def test_a_column_that_could_not_be_added_is_reported(project, tmp_path, monkeypatch):
    """Measured on a read-only destination GeoPackage: the result came back
    ``{'naziv': 'pole 7'}`` and ``operator='Telekom'`` was gone, with nothing
    said. The element is then moved with that column blank and the original
    deleted."""
    path = str(tmp_path / "poles.gpkg")
    layer = _gpkg_point_layer(path, [("naziv", QVariant.String)])
    project.addMapLayer(layer)
    monkeypatch.setattr(layer.dataProvider(), "addAttributes", lambda *a, **k: False)

    source = _source_feature([("naziv", QVariant.String, "pole 7"),
                              ("operator", QVariant.String, "Telekom")])

    with OperationErrors("test") as errors:
        _copy_attributes_between_layers(source, layer, errors)

    assert errors.failed, "a column that could not be added was not reported"
    reported = errors.message()
    assert "operator" in reported, f"the message must name the column: {reported!r}"


def test_the_values_that_can_be_written_still_are(project, tmp_path, monkeypatch):
    """A failure on one column must not cost the others. The element still
    moves; it moves knowing as much as the destination can hold.

    **Characterisation, not proof.** It passes against the pre-fix code, which
    also kept the columns the destination already had; what it lost was the ones
    it could not add. This guards the surviving half against the fix.
    """
    path = str(tmp_path / "poles.gpkg")
    layer = _gpkg_point_layer(path, [("naziv", QVariant.String)])
    project.addMapLayer(layer)
    monkeypatch.setattr(layer.dataProvider(), "addAttributes", lambda *a, **k: False)

    source = _source_feature([("naziv", QVariant.String, "pole 7"),
                              ("operator", QVariant.String, "Telekom")])

    with OperationErrors("test") as errors:
        vals = _copy_attributes_between_layers(source, layer, errors)

    assert vals.get("naziv") == "pole 7", f"the column that exists was dropped too: {vals}"


# ---------------------------------------------------------------------------
# the primary key
# ---------------------------------------------------------------------------

def test_a_destination_whose_primary_key_cannot_be_read_is_reported(project, tmp_path,
                                                                    monkeypatch):
    """The fid/id/gid guess stands, because it is better than nothing -- but a
    destination whose key is called something else will have that key copied
    into it, and the insert then fails on exactly the primary-key conflict the
    skip list exists to prevent. The user has to learn it was a guess."""
    path = str(tmp_path / "poles.gpkg")
    layer = _gpkg_point_layer(path, [("naziv", QVariant.String)])
    project.addMapLayer(layer)
    monkeypatch.setattr(layer, "dataProvider", lambda: None)

    source = _source_feature([("naziv", QVariant.String, "pole 7")])

    with OperationErrors("test") as errors:
        vals = _copy_attributes_between_layers(source, layer, errors)

    assert errors.failed, "an unreadable primary key was not reported"
    assert "primary key" in errors.message(), errors.message()
    assert vals.get("naziv") == "pole 7", f"it must still do its job: {vals}"


def test_the_primary_key_is_never_copied(project, tmp_path):
    """Characterisation: this is what the function exists to guarantee, it
    worked before, and it must keep working. Passes against the pre-fix code."""
    path = str(tmp_path / "poles.gpkg")
    layer = _gpkg_point_layer(path, [("naziv", QVariant.String)])
    project.addMapLayer(layer)
    source = _source_feature([("fid", QVariant.Int, 42),
                              ("naziv", QVariant.String, "pole 7")])

    with OperationErrors("test") as errors:
        vals = _copy_attributes_between_layers(source, layer, errors)

    assert "fid" not in vals, f"the primary key was copied: {vals}"


# ---------------------------------------------------------------------------
# the collector is optional
# ---------------------------------------------------------------------------

def test_a_caller_without_a_collector_still_surfaces_the_problem(project, tmp_path,
                                                                 monkeypatch):
    """``errors`` is optional so this fix could land without its caller being
    changed in the same commit. A caller that passes nothing must still not
    lose the message -- the whole point of the item is that failures stop
    disappearing."""
    path = str(tmp_path / "poles.gpkg")
    layer = _gpkg_point_layer(path, [("naziv", QVariant.String)])
    project.addMapLayer(layer)
    monkeypatch.setattr(layer.dataProvider(), "addAttributes", lambda *a, **k: False)

    pushed = []
    monkeypatch.setattr(OperationErrors, "report",
                        lambda self: pushed.append(self.message()) or True)

    source = _source_feature([("naziv", QVariant.String, "pole 7"),
                              ("operator", QVariant.String, "Telekom")])
    _copy_attributes_between_layers(source, layer)

    assert pushed and "operator" in pushed[0], (
        f"a caller with no collector lost the message: {pushed}")
