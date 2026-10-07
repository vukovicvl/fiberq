"""A picture or drawing link survives being saved.

WP4 FU-2 item U9. Unclaimed, but it ships with R12: the picture a QGIS 4 user
can finally open is one a QGIS 3 save would have unlinked.

FiberQ remembered a per-feature link at
``FiberQPlugin/image_map/<layer id>/<feature id>``. QGIS 3 writes project
properties as **nested XML elements**, one per path segment, so that becomes
``<image_map><Poles_a8c6…><12>`` -- and ``<12>`` is not a legal element name,
because a name may not begin with a digit. Qt refuses it, prints *"Calling
appendChild() on a null node does nothing."*, writes the parent as an empty
element, and the value is gone. Measured on 3.44.15: **every** picture and
drawing link is lost on save, with nothing in the UI to say so.

Measured on 4.0.3: none of them are lost, because QGIS 4 writes
``<properties name="12" …>`` and puts the key in an *attribute*. So the same
project file loses its links or keeps them depending only on which QGIS saved
it, which is why this is tested by actually writing a ``.qgs`` and reading it
back rather than by asserting on the key shape.

Two limits, both deliberate and both measured:

* **No listing-based migration.** ``QgsProject.subkeyList`` answered ``[]`` for
  three layers whose entries ``readEntry`` then returned correctly, so any
  sweep over the old keys would silently skip links. The fallback is per
  feature instead, where the layer and the feature id are already known.
* **A link already destroyed cannot come back.** After a QGIS 3 round trip the
  old key is not in the file at all, so there is nothing left to read. Links
  made or re-attached from v1.6.0 on are safe; older ones must be attached
  once more.
"""
import json
import os

import pytest
from qgis.core import QgsProject, QgsVectorLayer

from fiberq.core import feature_links as fl

LEGACY_KINDS = [
    (fl.IMAGES, "image_map"),
    (fl.DRAWINGS, "drawing_map"),
    (fl.DRAWING_LAYERS, "drawing_layers"),
]


@pytest.fixture
def project(qgis_app):
    """A standalone project, so the singleton is never touched.

    A project that outlives the test which made it is destroyed during
    interpreter teardown, which segfaults on QGIS 4.0.
    """
    prj = QgsProject()
    yield prj
    prj.clear()


@pytest.fixture
def layer(project):
    lyr = QgsVectorLayer("Point?crs=EPSG:3857&field=a:string", "Poles", "memory")
    project.addMapLayer(lyr)
    return lyr


# ---------------------------------------------------------------------------
# The storage shape
# ---------------------------------------------------------------------------

def test_a_link_reads_back_in_the_same_session(project, layer):
    fl.link_set(fl.IMAGES, layer.id(), 12, "/photos/pole-12.jpg", project)
    assert fl.link_get(fl.IMAGES, layer.id(), 12, project) == "/photos/pole-12.jpg"


def test_an_unset_link_is_the_default(project, layer):
    assert fl.link_get(fl.IMAGES, layer.id(), 99, project) == ""
    assert fl.link_get(fl.DRAWING_LAYERS, layer.id(), 99, project, default=[]) == []


def test_the_entry_key_has_no_numeric_segment(project, layer):
    """The whole fix in one assertion."""
    fl.link_set(fl.IMAGES, layer.id(), 12, "/photos/pole-12.jpg", project)
    raw, found = project.readEntry(fl.SCOPE, "FeatureLinks/images_v1", "")
    assert found and raw
    stored = json.loads(raw)
    assert stored == {layer.id(): {"12": "/photos/pole-12.jpg"}}


def test_links_for_several_features_and_layers_coexist(project, layer):
    other = QgsVectorLayer("Point?crs=EPSG:3857&field=a:string", "Manholes", "memory")
    project.addMapLayer(other)
    fl.link_set(fl.IMAGES, layer.id(), 1, "/a.jpg", project)
    fl.link_set(fl.IMAGES, layer.id(), 2, "/b.jpg", project)
    fl.link_set(fl.IMAGES, other.id(), 1, "/c.jpg", project)

    assert fl.link_get(fl.IMAGES, layer.id(), 1, project) == "/a.jpg"
    assert fl.link_get(fl.IMAGES, layer.id(), 2, project) == "/b.jpg"
    assert fl.link_get(fl.IMAGES, other.id(), 1, project) == "/c.jpg"


def test_the_three_kinds_do_not_collide(project, layer):
    fl.link_set(fl.IMAGES, layer.id(), 1, "/photo.jpg", project)
    fl.link_set(fl.DRAWINGS, layer.id(), 1, "/plan.dxf", project)
    fl.link_set(fl.DRAWING_LAYERS, layer.id(), 1, ["a", "b"], project)

    assert fl.link_get(fl.IMAGES, layer.id(), 1, project) == "/photo.jpg"
    assert fl.link_get(fl.DRAWINGS, layer.id(), 1, project) == "/plan.dxf"
    assert fl.link_get(fl.DRAWING_LAYERS, layer.id(), 1, project) == ["a", "b"]


def test_a_drawing_layer_list_round_trips_as_a_list(project, layer):
    fl.link_set(fl.DRAWING_LAYERS, layer.id(), 1, ["x", "y", "z"], project)
    assert fl.link_get(fl.DRAWING_LAYERS, layer.id(), 1, project) == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# Save and reopen: the thing that failed
# ---------------------------------------------------------------------------

def test_a_link_survives_save_and_reopen(qgis_app, tmp_path):
    """Fails on the 3.44 leg before this change, passes on 4.0 either way."""
    path = os.path.join(str(tmp_path), "p.qgs")
    written = QgsProject()
    lyr = QgsVectorLayer("Point?crs=EPSG:3857&field=a:string", "Poles", "memory")
    written.addMapLayer(lyr)
    layer_id = lyr.id()
    fl.link_set(fl.IMAGES, layer_id, 12, "/photos/pole-12.jpg", written)
    fl.link_set(fl.DRAWINGS, layer_id, 12, "/plans/pole-12.dxf", written)
    fl.link_set(fl.DRAWING_LAYERS, layer_id, 12, ["layer_a", "layer_b"], written)
    assert written.write(path)
    written.clear()

    reopened = QgsProject()
    assert reopened.read(path)
    try:
        assert fl.link_get(fl.IMAGES, layer_id, 12, reopened) == "/photos/pole-12.jpg"
        assert fl.link_get(fl.DRAWINGS, layer_id, 12, reopened) == "/plans/pole-12.dxf"
        assert fl.link_get(fl.DRAWING_LAYERS, layer_id, 12, reopened) == ["layer_a", "layer_b"]
    finally:
        reopened.clear()


def test_the_old_key_shape_really_is_lost_on_save(qgis_app, tmp_path):
    """The defect itself, pinned so nobody "simplifies" the storage back.

    On QGIS 4 the old shape survives, so this asserts the difference rather
    than the loss: whatever this QGIS does with a numeric segment, the new
    shape must survive.
    """
    path = os.path.join(str(tmp_path), "p.qgs")
    written = QgsProject()
    lyr = QgsVectorLayer("Point?crs=EPSG:3857&field=a:string", "Poles", "memory")
    written.addMapLayer(lyr)
    layer_id = lyr.id()
    written.writeEntry(fl.SCOPE, f"image_map/{layer_id}/12", "/old-shape.jpg")
    written.writeEntry(fl.SCOPE, "FeatureLinks/images_v1",
                       json.dumps({layer_id: {"12": "/new-shape.jpg"}}))
    assert written.write(path)
    written.clear()

    reopened = QgsProject()
    assert reopened.read(path)
    try:
        old = reopened.readEntry(fl.SCOPE, f"image_map/{layer_id}/12", "")[0]
        new = reopened.readEntry(fl.SCOPE, "FeatureLinks/images_v1", "")[0]
        assert new, "the new shape must always survive"
        assert json.loads(new) == {layer_id: {"12": "/new-shape.jpg"}}
        if not old:
            # QGIS 3: a key segment starting with a digit is not a legal XML
            # element name, so Qt dropped it.
            assert fl.link_get(fl.IMAGES, layer_id, 12, reopened) == "/new-shape.jpg"
    finally:
        reopened.clear()


# ---------------------------------------------------------------------------
# Reading, and migrating, the pre-1.6.0 keys
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,prefix", LEGACY_KINDS)
def test_the_old_per_feature_key_is_still_read(project, layer, kind, prefix):
    project.writeEntry(fl.SCOPE, f"{prefix}/{layer.id()}/7", "old-value")
    expected = ["old-value"] if kind == fl.DRAWING_LAYERS else "old-value"
    assert fl.link_get(kind, layer.id(), 7, project) == expected


@pytest.mark.parametrize("kind,prefix", LEGACY_KINDS)
def test_the_pre_1_0_scope_is_still_read(project, layer, kind, prefix):
    """``StuboviPlugin`` is what the plugin was called before 1.0."""
    project.writeEntry(fl.LEGACY_SCOPE, f"{prefix}/{layer.id()}/7", "ancient-value")
    expected = ["ancient-value"] if kind == fl.DRAWING_LAYERS else "ancient-value"
    assert fl.link_get(kind, layer.id(), 7, project) == expected


def test_reading_an_old_key_migrates_it(project, layer):
    """Lazy on purpose: the old keys cannot be listed. See the module docstring."""
    project.writeEntry(fl.SCOPE, f"image_map/{layer.id()}/7", "/old.jpg")
    assert fl.link_get(fl.IMAGES, layer.id(), 7, project) == "/old.jpg"

    raw = project.readEntry(fl.SCOPE, "FeatureLinks/images_v1", "")[0]
    assert json.loads(raw) == {layer.id(): {"7": "/old.jpg"}}
    # and the old key is gone, so it cannot later contradict the new one
    assert project.readEntry(fl.SCOPE, f"image_map/{layer.id()}/7", "")[0] == ""


def test_an_old_comma_joined_drawing_layer_list_is_split(project, layer):
    project.writeEntry(fl.SCOPE, f"drawing_layers/{layer.id()}/7", "a,b,,c")
    assert fl.link_get(fl.DRAWING_LAYERS, layer.id(), 7, project) == ["a", "b", "c"]


def test_a_new_value_wins_over_an_old_key(project, layer):
    project.writeEntry(fl.SCOPE, f"image_map/{layer.id()}/7", "/old.jpg")
    fl.link_set(fl.IMAGES, layer.id(), 7, "/new.jpg", project)
    assert fl.link_get(fl.IMAGES, layer.id(), 7, project) == "/new.jpg"


def test_clearing_a_link_does_not_resurrect_the_old_key(project, layer):
    """The reason an empty value is stored rather than removed."""
    project.writeEntry(fl.SCOPE, f"image_map/{layer.id()}/7", "/old.jpg")
    fl.link_set(fl.IMAGES, layer.id(), 7, "/new.jpg", project)
    fl.link_clear(fl.IMAGES, layer.id(), 7, project)
    assert fl.link_get(fl.IMAGES, layer.id(), 7, project) == ""


def test_setting_a_link_clears_the_old_key_in_both_scopes(project, layer):
    project.writeEntry(fl.SCOPE, f"image_map/{layer.id()}/7", "/a.jpg")
    project.writeEntry(fl.LEGACY_SCOPE, f"image_map/{layer.id()}/7", "/b.jpg")
    fl.link_set(fl.IMAGES, layer.id(), 7, "/c.jpg", project)
    assert project.readEntry(fl.SCOPE, f"image_map/{layer.id()}/7", "")[0] == ""
    assert project.readEntry(fl.LEGACY_SCOPE, f"image_map/{layer.id()}/7", "")[0] == ""


# ---------------------------------------------------------------------------
# A damaged entry must not stop the plugin loading
# ---------------------------------------------------------------------------

def test_a_corrupt_entry_reads_as_no_links(project, layer):
    project.writeEntry(fl.SCOPE, "FeatureLinks/images_v1", "{not json at all")
    assert fl.link_get(fl.IMAGES, layer.id(), 7, project) == ""


def test_an_entry_that_is_not_a_mapping_reads_as_no_links(project, layer):
    project.writeEntry(fl.SCOPE, "FeatureLinks/images_v1", '["a", "list"]')
    assert fl.link_get(fl.IMAGES, layer.id(), 7, project) == ""


def test_a_corrupt_entry_can_still_be_written_over(project, layer):
    project.writeEntry(fl.SCOPE, "FeatureLinks/images_v1", "{not json at all")
    fl.link_set(fl.IMAGES, layer.id(), 7, "/fresh.jpg", project)
    assert fl.link_get(fl.IMAGES, layer.id(), 7, project) == "/fresh.jpg"


def test_a_path_with_xml_hostile_characters_round_trips(project, layer, tmp_path):
    """JSON inside an XML element: both layers of escaping have to hold."""
    nasty = '/photos/a & b <c> "d" \'e\' #f.jpg'
    path = os.path.join(str(tmp_path), "p.qgs")
    fl.link_set(fl.IMAGES, layer.id(), 7, nasty, project)
    assert project.write(path)
    layer_id = layer.id()
    project.clear()

    reopened = QgsProject()
    assert reopened.read(path)
    try:
        assert fl.link_get(fl.IMAGES, layer_id, 7, reopened) == nasty
    finally:
        reopened.clear()


# ---------------------------------------------------------------------------
# The two managers that call it
# ---------------------------------------------------------------------------

def test_the_drawing_manager_uses_the_new_storage(project, layer, monkeypatch):
    from fiberq.core.drawing_manager import DrawingManager

    monkeypatch.setattr(QgsProject, "instance", staticmethod(lambda: project))
    manager = DrawingManager.__new__(DrawingManager)
    manager.drawing_set(layer, 3, "/plans/x.dxf")
    manager.drawing_layers_set(layer, 3, ["a", "b"])

    assert manager.drawing_get(layer, 3) == "/plans/x.dxf"
    assert manager.drawing_layers_get(layer, 3) == ["a", "b"]
    raw = project.readEntry(fl.SCOPE, "FeatureLinks/drawings_v1", "")[0]
    assert json.loads(raw) == {layer.id(): {"3": "/plans/x.dxf"}}


def test_the_picture_bridge_uses_the_new_storage(project, layer, monkeypatch):
    from fiberq.utils import legacy_bridge

    monkeypatch.setattr(QgsProject, "instance", staticmethod(lambda: project))
    legacy_bridge._img_set(layer, 4, "/photos/y.jpg")
    assert legacy_bridge._img_get(layer, 4) == "/photos/y.jpg"
    raw = project.readEntry(fl.SCOPE, "FeatureLinks/images_v1", "")[0]
    assert json.loads(raw) == {layer.id(): {"4": "/photos/y.jpg"}}


def test_the_reader_and_the_writer_agree(project, layer, monkeypatch):
    """They did not before: writes and reads had separate implementations.

    ``main_plugin`` wrote the picture link through its own module-level
    ``_img_set``, while ``image_tool`` and ``image_watcher`` read through
    ``legacy_bridge._img_get`` -- and only the reader knew the pre-1.0 scope.
    """
    import fiberq.main_plugin as mp
    from fiberq.utils import legacy_bridge

    monkeypatch.setattr(QgsProject, "instance", staticmethod(lambda: project))
    mp._img_set(layer, 5, "/photos/z.jpg")
    assert legacy_bridge._img_get(layer, 5) == "/photos/z.jpg"
    assert mp._img_get(layer, 5) == "/photos/z.jpg"
