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

* **Lazy migration, listed first.** The fallback is per feature, where the
  layer and the feature id are already known, and it lists the layer's old
  keys with ``entryList`` before reading one: QGIS 3 logs a Critical "Entry
  token invalid" for every *read* of a numeric key segment, found or not, and
  the picture watcher asks about every feature under every click (v1.6.0 QA
  on 3.40). ``subkeyList`` is not the listing call -- it answers ``[]`` here,
  which an earlier version of this note took to mean the keys could not be
  listed at all.
* **A link already destroyed cannot come back.** After a QGIS 3 round trip the
  old key is not in the file at all, so there is nothing left to read. Links
  made or re-attached from v1.6.0 on are safe; older ones must be attached
  once more.
"""
import json
import os

import pytest
from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject, QgsVectorLayer

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
    """Lazy on purpose: see the module docstring."""
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


# ---------------------------------------------------------------------------
# f012: one project write per selection, not one per feature
# ---------------------------------------------------------------------------

def test_a_batch_stores_every_value(project, layer):
    values = {fid: f"/photos/p{fid}.jpg" for fid in range(50)}

    assert fl.link_set_many(fl.IMAGES, layer.id(), values, project)

    for fid, expected in values.items():
        assert fl.link_get(fl.IMAGES, layer.id(), fid, project) == expected


def test_a_batch_and_a_loop_leave_the_same_entry(project, layer):
    """The point of link_set delegating: the two cannot drift apart."""
    other = QgsProject()
    try:
        values = {1: "/a.jpg", 7: "/b.jpg", 42: ""}
        fl.link_set_many(fl.IMAGES, layer.id(), values, project)
        for fid, value in values.items():
            fl.link_set(fl.IMAGES, layer.id(), fid, value, other)

        key = "FeatureLinks/images_v1"
        assert project.readEntry(fl.SCOPE, key, "")[0] == other.readEntry(fl.SCOPE, key, "")[0]
    finally:
        other.clear()


def test_a_batch_leaves_other_layers_alone(project, layer):
    fl.link_set(fl.IMAGES, "another_layer_id", 3, "/keep.jpg", project)

    fl.link_set_many(fl.IMAGES, layer.id(), {3: "/new.jpg"}, project)

    assert fl.link_get(fl.IMAGES, "another_layer_id", 3, project) == "/keep.jpg"
    assert fl.link_get(fl.IMAGES, layer.id(), 3, project) == "/new.jpg"


def test_a_batch_clears_the_old_per_feature_keys_it_covers(project, layer):
    """And only the ones it covers -- a feature outside the batch keeps its own."""
    project.writeEntry(fl.SCOPE, f"image_map/{layer.id()}/1", "/old1.jpg")
    project.writeEntry(fl.SCOPE, f"image_map/{layer.id()}/2", "/old2.jpg")

    fl.link_set_many(fl.IMAGES, layer.id(), {1: "/new1.jpg"}, project)

    assert not project.readEntry(fl.SCOPE, f"image_map/{layer.id()}/1", "")[0]
    assert project.readEntry(fl.SCOPE, f"image_map/{layer.id()}/2", "")[0] == "/old2.jpg"


def test_an_empty_batch_is_a_no_op(project, layer):
    fl.link_set(fl.IMAGES, layer.id(), 1, "/keep.jpg", project)

    assert fl.link_set_many(fl.IMAGES, layer.id(), {}, project) is True

    assert fl.link_get(fl.IMAGES, layer.id(), 1, project) == "/keep.jpg"


def test_a_whole_selection_is_one_write(project, layer, monkeypatch):
    """What makes it linear: the entry is written once, not once per feature.

    Counting writes rather than timing, because a timing assertion on shared CI
    is a flake. The cost itself was measured separately -- on 3.44.15 the loop
    form runs 0.33 ms per feature at 1,000 and 0.94 ms at 4,000, cleanly
    quadratic, against 0.013 s and 0.060 s TOTAL for the batch.
    """
    writes = []
    real = QgsProject.writeEntry

    def counting(self, scope, key, value):
        if key == "FeatureLinks/images_v1":
            writes.append(key)
        return real(self, scope, key, value)

    monkeypatch.setattr(QgsProject, "writeEntry", counting)
    fl.link_set_many(fl.IMAGES, layer.id(), {fid: "/p.jpg" for fid in range(200)}, project)

    assert len(writes) == 1, f"200 features must be one write, got {len(writes)}"


def test_attaching_a_picture_to_a_selection_goes_through_the_batch(project, layer, monkeypatch):
    """The caller actually uses it -- the fix is worthless if the loop remains."""
    import fiberq.main_plugin as mp

    monkeypatch.setattr(QgsProject, "instance", staticmethod(lambda: project))
    mp._img_set_many(layer, [4, 5, 6], "/shared.jpg")

    for fid in (4, 5, 6):
        assert fl.link_get(fl.IMAGES, layer.id(), fid, project) == "/shared.jpg"


# ---------------------------------------------------------------------------
# Nothing in QGIS's log for a feature that has no old key
# ---------------------------------------------------------------------------

INVALID_TOKEN = "Entry token invalid"
_PROBE = "FiberQ test: can the message log be watched here?"


def _line_signals(log):
    """``(name, signal)`` for each signal a logged line can arrive on, newest first.

    ``messageReceived[str, str, Qgis.MessageLevel]`` is the overload that
    carries the line; ``messageReceived(bool)`` only says one arrived. QGIS 4
    still declares the three-argument one but no longer emits it, and a QGIS
    that drops it answers the look-up with KeyError ("there is no matching
    overloaded signal", what PyQt says for any signature a signal lacks on
    3.40.15 and 4.2.3): it is left out, so the fixture listens on
    ``messageReceivedWithFormat`` instead of erroring.
    """
    signals = []
    if hasattr(log, "messageReceivedWithFormat"):
        signals.append(("messageReceivedWithFormat", log.messageReceivedWithFormat))
    try:
        signals.append(("messageReceived", log.messageReceived[str, str, Qgis.MessageLevel]))
    except (AttributeError, KeyError):
        pass  # no three-argument overload on this QGIS
    return signals


def _listener(lines):
    def take(message, tag, level, *_format):
        lines.append((tag, level, message))
    return take


@pytest.fixture
def qgis_log(qgis_app):
    """Every line QGIS logs while the test runs, as ``(tag, level, message)``.

    QGIS 4 logs a line through ``messageReceivedWithFormat``, which adds the
    line's format, and no longer emits the three-argument ``messageReceived``
    it still declares. Measured with one ``QgsMessageLog.logMessage``: 4.0.3
    and 4.2.3 deliver it on ``messageReceivedWithFormat`` alone, and QGIS's
    own log panel still shows it; 3.22.16, 3.40.15 and 3.44.15 have no
    ``messageReceivedWithFormat`` and deliver it on ``messageReceived``. So
    the fixture logs a line of its own and listens on the first signal that
    delivered it, and on that one only, so that a QGIS emitting both cannot
    count a line twice. It skips where none delivers it, because a "logs
    nothing" check would pass there whatever happened.
    """
    connected = []
    for name, signal in _line_signals(QgsApplication.messageLog()):
        lines = []
        take = _listener(lines)
        signal.connect(take)
        connected.append((name, signal, take, lines))
    try:
        QgsMessageLog.logMessage(_PROBE, "FiberQ tests", Qgis.MessageLevel.Info)
        heard = [entry for entry in connected
                 if any(message == _PROBE for _tag, _level, message in entry[3])]
        if not heard:
            names = " or ".join(entry[0] for entry in connected)
            pytest.skip(f"QGIS {Qgis.QGIS_VERSION} delivered no line logged through "
                        f"QgsMessageLog.logMessage on {names}, so a 'logs nothing' "
                        "check cannot be observed")
        others = [entry for entry in connected if entry is not heard[0]]
        connected = heard[:1]
        for _name, signal, take, _lines in others:
            signal.disconnect(take)
        seen = heard[0][3]
        seen.remove(next(line for line in seen if line[2] == _PROBE))
        yield seen
    finally:
        for _name, signal, take, _lines in connected:
            signal.disconnect(take)


class _OnlyTheBoolOverload:
    """``messageReceived`` on a QGIS that keeps only ``messageReceived(bool)``."""

    def __getitem__(self, signature):
        raise KeyError("there is no matching overloaded signal")


class _LogWithoutTheThreeArgumentSignal:
    messageReceived = _OnlyTheBoolOverload()
    messageReceivedWithFormat = object()


def test_the_log_fixture_listens_where_the_three_argument_signal_is_gone():
    """Such a QGIS leaves the fixture on messageReceivedWithFormat, not in a KeyError."""
    log = _LogWithoutTheThreeArgumentSignal()

    assert _line_signals(log) == [("messageReceivedWithFormat", log.messageReceivedWithFormat)]


def _complaints(seen):
    return [line for line in seen if INVALID_TOKEN in line[2]]


class _CountingReads:
    """A project that remembers which keys were read from it."""

    def __init__(self, inner):
        self.inner = inner
        self.reads = []

    def readEntry(self, scope, key, default=""):
        self.reads.append(key)
        return self.inner.readEntry(scope, key, default)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_the_log_check_sees_a_blind_read_on_qgis_3(project, qgis_log):
    """A check that has never fired is not a check."""
    project.readEntry(fl.SCOPE, "image_map/Poles_x/12", "")
    if Qgis.QGIS_VERSION_INT < 40000:
        assert _complaints(qgis_log), qgis_log
    else:
        # QGIS 4 dropped the complaint -- it is not in 4.2.3's libqgis_core --
        # and 4.0.3 and 4.2.3 log nothing at all for this read (measured).
        assert not qgis_log, "this QGIS 4 logs a line for a numeric key segment: measure again"


@pytest.mark.parametrize("kind,prefix", LEGACY_KINDS)
def test_asking_about_a_feature_without_a_link_logs_nothing(project, layer, qgis_log, kind, prefix):
    """The picture watcher asks this about every feature under every click (QA on 3.40).

    Nothing at all, not only no "Entry token invalid": QGIS 4 has no such
    complaint to log, so there these checks catch a line of FiberQ's own.
    """
    for fid in (1, 2, 12):
        fl.link_get(kind, layer.id(), fid, project)
    assert not qgis_log, qgis_log


def test_setting_and_clearing_links_logs_nothing(project, layer, qgis_log):
    fl.link_set(fl.IMAGES, layer.id(), 12, "/a.jpg", project)
    fl.link_set_many(fl.IMAGES, layer.id(), {1: "/b.jpg", 2: "/c.jpg"}, project)
    fl.link_clear(fl.IMAGES, layer.id(), 12, project)
    assert not qgis_log, qgis_log


def test_only_a_feature_with_an_old_key_gets_its_key_read(project, layer):
    project.writeEntry(fl.SCOPE, f"image_map/{layer.id()}/7", "/old.jpg")
    counting = _CountingReads(project)

    assert fl.link_get(fl.IMAGES, layer.id(), 8, counting) == ""
    assert not [key for key in counting.reads if key.startswith("image_map/")], counting.reads

    assert fl.link_get(fl.IMAGES, layer.id(), 7, counting) == "/old.jpg"
    assert f"image_map/{layer.id()}/7" in counting.reads


def _survey_layer(project):
    """A layer named "2024 survey": its id starts with a digit, which QGIS 3
    would log as an invalid token too."""
    survey = QgsVectorLayer("Point?crs=EPSG:3857", "2024 survey", "memory")
    project.addMapLayer(survey)
    assert survey.id()[0].isdigit(), survey.id()
    return survey


def test_a_layer_id_that_starts_with_a_digit_still_links(project):
    """The links work on every QGIS; the log half is the next test."""
    survey = _survey_layer(project)
    assert fl.link_get(fl.IMAGES, survey.id(), 3, project) == ""
    fl.link_set(fl.IMAGES, survey.id(), 4, "/a.jpg", project)
    assert fl.link_get(fl.IMAGES, survey.id(), 4, project) == "/a.jpg"


def test_a_layer_id_that_starts_with_a_digit_logs_nothing(project, qgis_log):
    survey = _survey_layer(project)
    fl.link_get(fl.IMAGES, survey.id(), 3, project)
    fl.link_set(fl.IMAGES, survey.id(), 4, "/a.jpg", project)
    fl.link_get(fl.IMAGES, survey.id(), 4, project)
    assert not qgis_log, qgis_log


@pytest.mark.skipif(Qgis.QGIS_VERSION_INT < 40000,
                    reason="QGIS 3 cannot have saved a key under such an id")
def test_qgis_4_still_migrates_an_old_key_under_such_an_id(project):
    survey = QgsVectorLayer("Point?crs=EPSG:3857", "2024 survey", "memory")
    project.addMapLayer(survey)
    project.writeEntry(fl.SCOPE, f"image_map/{survey.id()}/3", "/old.jpg")
    assert fl.link_get(fl.IMAGES, survey.id(), 3, project) == "/old.jpg"
