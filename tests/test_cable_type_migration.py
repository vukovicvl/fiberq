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
them needs changing. The first two tests fail on the parent; the last two pin
what it did and still does.
"""
import pytest
from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

from fiberq.utils.field_aliases import _migrate_cable_type_values


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.clear()
    yield prj
    prj.clear()


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
