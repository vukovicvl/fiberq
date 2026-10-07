"""A pre-1.0 project's slack still finds its cable.

WP4 4.2, item R9. The identity migration renamed ``fiberq_uuid`` and nothing
else -- by design, it is an identity migration -- so a project made before the
English field rename still stores the slack-to-cable reference as
``kabl_layer_id`` / ``kabl_fid``. Every FiberQ tool that touches that pair
looked only for the modern name, with three different outcomes:

* **Place slack** and **Generate terminal slacks** wrote to the modern name.
  ``QgsFeature.__setitem__`` raises ``KeyError`` for a name the layer does not
  have -- and so does ``setAttribute``, measured on 3.44 and 4.0, despite the
  C++ signature suggesting it answers False -- so the tool died mid-click. Both
  crashes were reproduced on real legacy data.
* **Delete selected** read the modern name inside
  ``except Exception: logger.debug(...)``. At the default log level that writes
  nothing anywhere, so deleting a 30 m loop left the cable still claiming 30 m
  of slack: the one number the user deleted the loop in order to change.
* **Recompute** was the quiet one. It sums through a filter expression, and an
  expression naming a column the layer does not have raises nothing at all --
  it matches zero rows (measured, 3.44 and 4.0). The total therefore came out
  0.0 and was written over the cable's real figure. A crash would have been
  kinder.

That last one is why the fix is not simply "resolve the name". Resolving makes
the ordinary case work; **refusing to write when neither name is present** is
what stops the crash fix from becoming a quieter version of the same bug, and
``test_recompute_refuses_a_slack_layer_with_no_link_columns`` is the test that
pins it.

The two map tools are exercised through their bodies (``_place_slack``,
``_record_break``) rather than through a synthesised ``QMouseEvent``. The slot
itself is a two-line wrapper whose only job is to not raise; the body is the
code under test, and it is the real code.
"""
import pytest
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.core import interchange_fields as fm
from fiberq.core.slack_manager import SlackManager
from fiberq.tools.slack_tool import SlackPlaceTool
from fiberq.utils.errors import OperationErrors

LEGACY = ("kabl_layer_id", "kabl_fid")
MODERN = ("cable_layer_id", "cable_fid")


class FakeBar:
    def __init__(self):
        self.warnings = []
        self.infos = []

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushInfo(self, title, text):
        self.infos.append(text)


class FakeIface:
    """Only what the slack code actually reads off the interface."""

    def __init__(self, canvas=None):
        self.bar = FakeBar()
        self._canvas = canvas

    def messageBar(self):
        return self.bar

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return None


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """Stop ``QMessageBox.information`` blocking the run.

    ``generate_terminal_slack_for_selected`` reports its count with a modal, and
    under ``QT_QPA_PLATFORM=offscreen`` a modal still waits for a click that
    never comes. A headless suite that reaches one simply hangs.
    """
    seen = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a[-1])))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.append(a[-1])))
    return seen


@pytest.fixture
def project(qgis_app):
    """A clean project, emptied again afterwards.

    Layers left in a project that outlives the test are destroyed during
    interpreter teardown, which segfaults on QGIS 4.0.
    """
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


def _cable_layer(project, name="Aerial cables"):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", name, "memory")
    layer.dataProvider().addAttributes([
        QgsField("naziv", QVariant.String),
        QgsField("duzina_m", QVariant.Double),
        QgsField("slack_m", QVariant.Double),
        QgsField("total_len_m", QVariant.Double),
    ])
    layer.updateFields()
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(0, 0), QgsPointXY(100, 0)]))
    feat.setAttributes(["C1", 100.0, 70.0, 170.0])
    layer.startEditing()
    layer.addFeature(feat)
    layer.commitChanges()
    project.addMapLayer(layer)
    return layer, next(layer.getFeatures()).id()


def _slack_layer(project, pair=LEGACY, name="Opticke_rezerve"):
    """A slack layer whose cable reference uses ``pair``, or has none at all."""
    layer = QgsVectorLayer("Point?crs=EPSG:3857", name, "memory")
    attrs = [
        QgsField("tip", QVariant.String),
        QgsField("duzina_m", QVariant.Double),
        QgsField("lokacija", QVariant.String),
        QgsField("strana", QVariant.String),
    ]
    if pair:
        attrs.append(QgsField(pair[0], QVariant.String))
        attrs.append(QgsField(pair[1], QVariant.Int))
    layer.dataProvider().addAttributes(attrs)
    layer.updateFields()
    project.addMapLayer(layer)
    return layer


def _add_slack(layer, cable_layer_id, cable_fid, metres, pair=LEGACY, at=(0, 0)):
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*at)))
    feat["tip"] = "Terminal"
    feat["duzina_m"] = metres
    if pair:
        feat[pair[0]] = cable_layer_id
        feat[pair[1]] = None if cable_fid is None else int(cable_fid)
    layer.startEditing()
    assert layer.addFeature(feat)
    assert layer.commitChanges()
    return feat


def _manager(project, iface=None):
    return SlackManager(iface or FakeIface())


def _cable_values(layer, fid):
    """``(slack_m, total_len_m)``.

    ``total_len_m`` is ``ground_length() + slack``, and ground_length is a
    measurement: a 100 m line in EPSG:3857 comes back 99.99999999999999. So the
    totals are compared with ``pytest.approx``, while the slack sum -- which is
    plain addition of the stored values -- is compared exactly.
    """
    feat = next(f for f in layer.getFeatures() if f.id() == fid)
    return float(feat["slack_m"]), pytest.approx(float(feat["total_len_m"]))


# ---------------------------------------------------------------------------
# The pure resolver R9 promoted out of the validation engine
# ---------------------------------------------------------------------------

def test_actual_field_prefers_the_modern_name():
    assert fm.actual_field({"cable_fid", "kabl_fid"}, "cable_fid") == "cable_fid"


def test_actual_field_falls_back_to_the_pre_1_0_name():
    assert fm.actual_field({"kabl_fid"}, "cable_fid") == "kabl_fid"


def test_actual_field_is_empty_when_the_column_is_absent():
    assert fm.actual_field({"tip", "duzina_m"}, "cable_fid") == ""


def test_actual_field_accepts_a_plain_field_name_list():
    """``layer.fields().names()`` is a list, not a set."""
    assert fm.actual_field(["kabl_layer_id"], "cable_layer_id") == "kabl_layer_id"


def test_cable_link_fields_resolves_a_legacy_pair():
    assert fm.cable_link_fields(["kabl_layer_id", "kabl_fid"]) == LEGACY


def test_cable_link_fields_refuses_half_a_pair():
    """A layer id with no feature id points at a layer and no feature in it.

    That is not a weaker link but a wrong one, so the pair is all-or-nothing.
    """
    assert fm.cable_link_fields(["kabl_layer_id"]) == ("", "")
    assert fm.cable_link_fields(["cable_fid"]) == ("", "")


def test_cable_link_fields_will_mix_the_two_spellings():
    """A half-migrated layer is still usable, and says which column it used."""
    assert fm.cable_link_fields(["cable_layer_id", "kabl_fid"]) == (
        "cable_layer_id", "kabl_fid")


# ---------------------------------------------------------------------------
# Recompute: the silent one
# ---------------------------------------------------------------------------

def test_recompute_totals_a_legacy_slack_layer(project):
    """v1.5.0 wrote 0.0 here, over the user's real figure."""
    cable, fid = _cable_layer(project)
    slack = _slack_layer(project)
    _add_slack(slack, cable.id(), fid, 30.0)
    _add_slack(slack, cable.id(), fid, 40.0, at=(100, 0))

    assert _manager(project).recompute_slack_for_cable(cable.id(), fid) is True
    assert _cable_values(cable, fid) == (70.0, 170.0)


def test_recompute_still_totals_a_modern_slack_layer(project):
    cable, fid = _cable_layer(project)
    slack = _slack_layer(project, pair=MODERN, name="Optical slacks")
    _add_slack(slack, cable.id(), fid, 25.0, pair=MODERN)

    assert _manager(project).recompute_slack_for_cable(cable.id(), fid) is True
    assert _cable_values(cable, fid) == (25.0, 125.0)


def test_recompute_refuses_a_slack_layer_with_no_link_columns(project):
    """The guard that stops the crash fix becoming a silent one.

    Without it, resolving the names still leaves a slack layer that has neither
    spelling summing to 0.0 and writing that over the cable.
    """
    cable, fid = _cable_layer(project)
    _slack_layer(project, pair=None)
    iface = FakeIface()

    assert _manager(project, iface).recompute_slack_for_cable(cable.id(), fid) is False
    assert _cable_values(cable, fid) == (70.0, 170.0), "the cable must be untouched"
    assert "no cable reference columns" in iface.bar.warnings[0]


def test_recompute_refuses_a_slack_layer_with_no_length_column(project):
    """Summing a column that is not there is the same trap one field over."""
    cable, fid = _cable_layer(project)
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "Opticke_rezerve", "memory")
    layer.dataProvider().addAttributes([
        QgsField("kabl_layer_id", QVariant.String),
        QgsField("kabl_fid", QVariant.Int),
    ])
    layer.updateFields()
    project.addMapLayer(layer)
    iface = FakeIface()

    assert _manager(project, iface).recompute_slack_for_cable(cable.id(), fid) is False
    assert _cable_values(cable, fid) == (70.0, 170.0)
    assert "no slack length column" in iface.bar.warnings[0]


def test_recompute_ignores_slack_belonging_to_another_cable(project):
    cable, fid = _cable_layer(project)
    other, other_fid = _cable_layer(project, name="Underground cables")
    slack = _slack_layer(project)
    _add_slack(slack, cable.id(), fid, 30.0)
    _add_slack(slack, other.id(), other_fid, 500.0, at=(5, 5))

    _manager(project).recompute_slack_for_cable(cable.id(), fid)
    assert _cable_values(cable, fid) == (30.0, 130.0)


def test_recompute_skips_an_unlinked_slack_row(project):
    """A loop not yet attached to anything is incomplete, not broken."""
    cable, fid = _cable_layer(project)
    slack = _slack_layer(project)
    _add_slack(slack, cable.id(), fid, 30.0)
    _add_slack(slack, None, None, 99.0, at=(50, 0))
    iface = FakeIface()

    _manager(project, iface).recompute_slack_for_cable(cable.id(), fid)
    assert _cable_values(cable, fid) == (30.0, 130.0)
    assert iface.bar.warnings == []


def test_recompute_reports_rather_than_shrinking_the_total(project):
    """An unreadable row must not quietly reduce the number written.

    The length column has to be a string one for this to be reachable at all:
    a Double column coerces anything unparseable to NULL, which is the empty
    case above and not this one. Old projects do carry text in numeric-looking
    columns, which is why the guard is worth having.
    """
    cable, fid = _cable_layer(project)
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "Opticke_rezerve", "memory")
    layer.dataProvider().addAttributes([
        QgsField("kabl_layer_id", QVariant.String),
        QgsField("kabl_fid", QVariant.Int),
        QgsField("duzina_m", QVariant.String),
    ])
    layer.updateFields()
    project.addMapLayer(layer)
    for value in ("30", "not a number"):
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        feat["kabl_layer_id"] = cable.id()
        feat["kabl_fid"] = int(fid)
        feat["duzina_m"] = value
        layer.startEditing()
        assert layer.addFeature(feat)
        assert layer.commitChanges()
    iface = FakeIface()

    _manager(project, iface).recompute_slack_for_cable(cable.id(), fid)
    assert iface.bar.warnings, "the unreadable row has to be reported"
    assert "not a number" in iface.bar.warnings[0] or "could not convert" in iface.bar.warnings[0]
    # The readable row still counts: one bad value must not void the total.
    assert _cable_values(cable, fid)[0] == 30.0


def test_recompute_reports_a_cable_layer_that_left_the_project(project):
    """A stale kabl_layer_id from another design announces itself."""
    slack = _slack_layer(project)
    _add_slack(slack, "a_layer_id_that_is_not_here", 1, 30.0)
    iface = FakeIface()

    assert _manager(project, iface).recompute_slack_for_cable(
        "a_layer_id_that_is_not_here", 1) is False
    assert "not in the project" in iface.bar.warnings[0]


def test_recompute_reports_into_a_shared_collector(project):
    """A dozen cables in one gesture must be one message, not a dozen."""
    cable, fid = _cable_layer(project)
    _slack_layer(project, pair=None)
    iface = FakeIface()
    errors = OperationErrors("Delete", iface)

    _manager(project).recompute_slack_for_cable(cable.id(), fid, errors)
    _manager(project).recompute_slack_for_cable(cable.id(), fid, errors)
    assert len(errors) == 2
    assert iface.bar.warnings == [], "the collector reports, not the callee"
    errors.report()
    assert len(iface.bar.warnings) == 1
    assert "(+1 more)" in iface.bar.warnings[0]


# ---------------------------------------------------------------------------
# Generate terminal slacks: KeyError on v1.5.0
# ---------------------------------------------------------------------------

def test_generate_writes_through_the_legacy_pair(project):
    cable, fid = _cable_layer(project)
    slack = _slack_layer(project)
    cable.selectByIds([fid])
    iface = FakeIface()

    _manager(project, iface).generate_terminal_slack_for_selected()

    rows = list(slack.getFeatures())
    assert len(rows) == 2, "one terminal slack at each end"
    assert {r["kabl_layer_id"] for r in rows} == {cable.id()}
    assert {int(r["kabl_fid"]) for r in rows} == {fid}
    assert {r["strana"] for r in rows} == {"od", "do"}
    assert iface.bar.warnings == []
    # 20 m is the terminal default, so both ends together are 40 m.
    assert _cable_values(cable, fid) == (40.0, 140.0)


def test_generate_refuses_a_slack_layer_with_no_link_columns(project):
    """Points that can never attach to a cable are worse than none.

    They look like success and leave every cable total permanently wrong.
    """
    cable, fid = _cable_layer(project)
    slack = _slack_layer(project, pair=None)
    cable.selectByIds([fid])
    iface = FakeIface()

    _manager(project, iface).generate_terminal_slack_for_selected()

    assert slack.featureCount() == 0
    assert "no cable reference columns" in iface.bar.warnings[0]


def test_generate_handles_a_multipart_cable(project):
    """v1.5.0 raised TypeError here, as an unhandled Python error.

    ``asPolyline()`` raises on a MultiLineString rather than answering an empty
    list, so the ``asMultiPolyline()`` fallback written underneath it was never
    reached. See ``SlackManager._endpoints_of``.
    """
    cable, fid = _cable_layer(project)
    cable.startEditing()
    cable.changeGeometry(fid, QgsGeometry.fromMultiPolylineXY(
        [[QgsPointXY(0, 0), QgsPointXY(10, 0)],
         [QgsPointXY(20, 0), QgsPointXY(30, 0)]]))
    cable.commitChanges()
    slack = _slack_layer(project)
    cable.selectByIds([fid])

    _manager(project).generate_terminal_slack_for_selected()
    assert slack.featureCount() == 2


# ---------------------------------------------------------------------------
# Place slack: the other KeyError on v1.5.0
# ---------------------------------------------------------------------------

def _place_tool(project, iface, manager):
    tool = SlackPlaceTool.__new__(SlackPlaceTool)
    tool.iface = iface
    tool.plugin = manager
    tool.canvas = None
    tool.params = {"tip": "Terminal", "duzina_m": 20, "lokacija": "Objekat"}
    return tool


def test_place_slack_writes_through_the_legacy_pair(project, monkeypatch):
    cable, fid = _cable_layer(project)
    slack = _slack_layer(project)
    iface = FakeIface()
    manager = _manager(project, iface)
    tool = _place_tool(project, iface, manager)
    cable_feat = next(cable.getFeatures())
    monkeypatch.setattr(
        tool, "_resolve", lambda p: (cable, cable_feat, "od", QgsPointXY(0, 0)))
    monkeypatch.setattr(tool, "_nearest_node", lambda p: (None, None, None))

    with OperationErrors("Optical slacks", iface) as errors:
        tool._place_slack(QgsPointXY(0, 0), errors)

    row = next(slack.getFeatures())
    assert row["kabl_layer_id"] == cable.id()
    assert int(row["kabl_fid"]) == fid
    assert iface.bar.warnings == []
    assert iface.bar.infos == ["Slack saved."]
    assert _cable_values(cable, fid) == (20.0, 120.0)


def test_place_slack_refuses_a_layer_with_no_link_columns(project, monkeypatch):
    cable, fid = _cable_layer(project)
    slack = _slack_layer(project, pair=None)
    iface = FakeIface()
    tool = _place_tool(project, iface, _manager(project, iface))
    cable_feat = next(cable.getFeatures())
    monkeypatch.setattr(
        tool, "_resolve", lambda p: (cable, cable_feat, "od", QgsPointXY(0, 0)))
    monkeypatch.setattr(tool, "_nearest_node", lambda p: (None, None, None))

    with OperationErrors("Optical slacks", iface) as errors:
        tool._place_slack(QgsPointXY(0, 0), errors)

    assert slack.featureCount() == 0
    assert "no cable reference columns" in iface.bar.warnings[0]
    assert iface.bar.infos == [], "no 'Slack saved.' after a refusal"


def test_place_slack_finds_a_legacy_named_slack_layer(project, monkeypatch):
    """``_slack_layer`` resolves the name through ``canonical_layer_name``."""
    cable, fid = _cable_layer(project)
    slack = _slack_layer(project, name="Opticke_rezerve")
    iface = FakeIface()
    tool = _place_tool(project, iface, None)
    assert tool._slack_layer() is slack
    assert slack.name() == "Opticke_rezerve"


# ---------------------------------------------------------------------------
# Delete selected: the swallowed KeyError on v1.5.0
# ---------------------------------------------------------------------------

def test_cables_behind_reads_through_the_legacy_pair(project):
    """The read that ``delete_selected`` used to do inside a debug swallow."""
    from fiberq.main_plugin import FiberQPlugin

    cable, fid = _cable_layer(project)
    slack = _slack_layer(project)
    _add_slack(slack, cable.id(), fid, 30.0)
    plugin = FiberQPlugin.__new__(FiberQPlugin)
    errors = OperationErrors("Delete", FakeIface())

    found = plugin._cables_behind(slack, list(slack.getFeatures()), errors)
    assert found == {(cable.id(), fid)}
    assert not errors.failed


def test_cables_behind_reports_a_layer_with_no_link_columns(project):
    from fiberq.main_plugin import FiberQPlugin

    slack = _slack_layer(project, pair=None)
    _add_slack(slack, None, None, 30.0, pair=None)
    plugin = FiberQPlugin.__new__(FiberQPlugin)
    errors = OperationErrors("Delete", FakeIface())

    assert plugin._cables_behind(slack, list(slack.getFeatures()), errors) == set()
    assert errors.failed


def test_cables_behind_skips_unlinked_rows_without_complaint(project):
    from fiberq.main_plugin import FiberQPlugin

    cable, fid = _cable_layer(project)
    slack = _slack_layer(project)
    _add_slack(slack, None, None, 30.0)
    plugin = FiberQPlugin.__new__(FiberQPlugin)
    errors = OperationErrors("Delete", FakeIface())

    assert plugin._cables_behind(slack, list(slack.getFeatures()), errors) == set()
    assert not errors.failed


# ---------------------------------------------------------------------------
# Fibre break: the same pair, latent rather than reproduced
# ---------------------------------------------------------------------------

def test_fiber_break_writes_through_the_legacy_pair(project, monkeypatch):
    """No pre-1.0 break layer has been found in the wild.

    Which is exactly why it is worth resolving now rather than waiting for one.
    """
    from fiberq.addons.fiber_break import FiberBreakTool

    cable, fid = _cable_layer(project)
    breaks = QgsVectorLayer("Point?crs=EPSG:3857", "Prekid vlakna", "memory")
    breaks.dataProvider().addAttributes([
        QgsField("naziv", QVariant.String),
        QgsField("kabl_layer_id", QVariant.String),
        QgsField("kabl_fid", QVariant.Int),
        QgsField("distance_m", QVariant.Double),
        QgsField("segments_hit", QVariant.Int),
        QgsField("vreme", QVariant.String),
    ])
    breaks.updateFields()
    project.addMapLayer(breaks)

    iface = FakeIface()
    tool = FiberBreakTool.__new__(FiberBreakTool)
    tool.iface = iface
    monkeypatch.setattr(tool, "_iter_line_layers", lambda: [cable])
    monkeypatch.setattr(tool, "_ensure_break_layer", lambda: breaks)
    monkeypatch.setattr(tool, "_flatten_polyline",
                        lambda g: [QgsPointXY(0, 0), QgsPointXY(100, 0)])
    monkeypatch.setattr(tool, "_measure_line", lambda pts: (100.0, _Planar()))
    tool.snap_marker = _FakeMarker()

    with OperationErrors("Fiber break", iface) as errors:
        tool._record_break(QgsPointXY(40, 0), errors)

    row = next(breaks.getFeatures())
    assert row["kabl_layer_id"] == cable.id()
    assert int(row["kabl_fid"]) == fid
    assert iface.bar.warnings == []


def test_fiber_break_refuses_a_layer_with_no_link_columns(project, monkeypatch):
    from fiberq.addons.fiber_break import FiberBreakTool

    cable, _fid = _cable_layer(project)
    breaks = QgsVectorLayer("Point?crs=EPSG:3857", "Fiber break", "memory")
    breaks.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    breaks.updateFields()
    project.addMapLayer(breaks)

    iface = FakeIface()
    tool = FiberBreakTool.__new__(FiberBreakTool)
    tool.iface = iface
    monkeypatch.setattr(tool, "_iter_line_layers", lambda: [cable])
    monkeypatch.setattr(tool, "_ensure_break_layer", lambda: breaks)
    monkeypatch.setattr(tool, "_flatten_polyline",
                        lambda g: [QgsPointXY(0, 0), QgsPointXY(100, 0)])
    monkeypatch.setattr(tool, "_measure_line", lambda pts: (100.0, _Planar()))
    tool.snap_marker = _FakeMarker()

    with OperationErrors("Fiber break", iface) as errors:
        tool._record_break(QgsPointXY(40, 0), errors)

    assert breaks.featureCount() == 0
    assert "no cable reference columns" in iface.bar.warnings[0]


class _Planar:
    """Stands in for QgsDistanceArea: plain cartesian metres."""

    @staticmethod
    def measureLine(a, b):
        return float(((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5)


class _FakeMarker:
    def setCenter(self, point):
        self.centre = point

    def show(self):
        self.shown = True
