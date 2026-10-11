"""A closed Optical schematic view stops rebuilding, and is current when shown again.

Once the view had been opened and closed, v1.5.0 rebuilt it after every commit
anywhere in the project, hidden or not: 22.5 s per commit at size S (QGIS
3.44.15, benchmark ``edit_after_schematic``). A hidden view now only notes that
it is out of date, and catches up when it is shown again.

Unclaimed, deliberately: the WP4 plan counts this gate as supporting work, not
as the indexing and batching task 4.1 claims, and it is a separate commit so
the before/after table can show the claimed work without it.

The catch-up runs in showEvent, synchronously. v1.5.0 reappeared showing the
last change it is wired to -- its hidden rebuild had already run -- and a
debounced catch-up painted the old lengths and labels first, with Search and
Center unable to find an element added meanwhile, for 400 ms plus one rebuild
(measured on the XS city, 3.44.15 and 4.0.3). And it runs only when something changed: Qt6 sends
showEvent again when show() is called on a visible dialog, which
``open_optical_schematic()`` does on every click (0 events on Qt 5.15.15, 1 on
Qt 6.8.2, measured).

Two tests fail on v1.5.0, each on the one hidden rebuild it counts:
test_a_closed_view_does_not_rebuild_on_a_commit and
test_a_view_closed_before_its_timer_fires_catches_up_on_show. The others pin
what v1.5.0 did and pass on it. The driver runs in a child process: an
exception escaping a Qt slot kills the interpreter (exit 139, measured), and
the driver installs its own ``sys.excepthook`` to report one instead.
"""
import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for the child. The suite has no timeout plugin.
TIMEOUT_S = 120

DRIVER = '''
import json, os, sys, time
sys.path.insert(0, {repo!r})
os.environ["FIBERQ_LOG_FILE"] = "false"
from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)
QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()
from qgis.PyQt.QtCore import QEvent, QObject
from qgis.PyQt.QtWidgets import QGraphicsTextItem

#: Anything escaping a slot lands here instead of killing the interpreter.
ERRORS = []
sys.excepthook = lambda kind, value, tb: ERRORS.append("%s: %s" % (kind.__name__, value))

from fiberq.core.data_manager import DataManager
from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

#: One entry per rebuild(): was the view visible when it ran?
REBUILDS = []
_rebuild = OpticalSchematicDialog.rebuild


def rebuild(self):
    REBUILDS.append(self.isVisible())
    _rebuild(self)


OpticalSchematicDialog.rebuild = rebuild


def pump(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        APP.processEvents()
        time.sleep(0.01)


def layer(uri, name, rows):
    lyr = QgsVectorLayer(uri, name, "memory")
    feats = []
    for geom, attrs in rows:
        feat = QgsFeature(lyr.fields())
        feat.setGeometry(geom)
        for key, value in attrs.items():
            feat.setAttribute(key, value)
        feats.append(feat)
    assert lyr.dataProvider().addFeatures(feats)[0]
    return lyr


def pt(x, y):
    return QgsGeometry.fromPointXY(QgsPointXY(2437000.0 + x, 5365000.0 + y))


def labels(dlg):
    return sorted(i.toPlainText() for i in dlg.scene.items() if isinstance(i, QGraphicsTextItem))


def found(dlg, name):
    """What Search and Center look the name up in."""
    return name in (getattr(dlg, "_last_positions", {{}}) or {{}})


def set_capacity(value):
    assert cables.startEditing()
    assert cables.changeAttributeValue(next(cables.getFeatures()).id(),
                                       cables.fields().indexFromName("kapacitet"), value)
    assert cables.commitChanges(), cables.commitErrors()


class PaintSpy(QObject):
    """The labels the scene held at each real paint of the view."""

    def __init__(self, dlg):
        super().__init__()
        self.dlg = dlg
        self.seen = []

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Paint:
            self.seen.append(labels(self.dlg))
        return False


project = QgsProject.instance()
nodes = layer("Point?crs=EPSG:3857&field=naziv:string", "ODF",
              [(pt(0, 0), {{"naziv": "ODF-1"}}), (pt(300, 0), {{"naziv": "TB-1"}})])
cables = layer("LineString?crs=EPSG:3857&field=od:string&field=do:string"
               "&field=podtip:string&field=kapacitet:string", "Underground cables",
               [(QgsGeometry.fromPolylineXY([QgsPointXY(2437000.0, 5365000.0),
                                             QgsPointXY(2437300.0, 5365000.0)]),
                 {{"od": "ODF-1", "do": "TB-1", "podtip": "glavni", "kapacitet": "24"}})])
project.addMapLayers([nodes, cables])

data = DataManager()
core = type("Core", (), {{}})()
core.iface = type("Iface", (), {{"mainWindow": lambda self: None}})()
core.list_all_cables = data.list_all_cables
core.list_all_pipes = data.list_all_pipes

dlg = OpticalSchematicDialog(core)
dlg.show()
pump(0.8)
out = {{"first_open_rebuilds": len(REBUILDS), "before": labels(dlg)}}
dlg.close()
pump(0.2)

# While the view is closed: a capacity change and a new element.
mark = len(REBUILDS)
set_capacity("48")
added = QgsFeature(nodes.fields())
added.setGeometry(pt(600, 0))
added.setAttribute("naziv", "TB-2")
assert nodes.startEditing() and nodes.addFeature(added)
assert nodes.commitChanges(), nodes.commitErrors()
pump(0.8)                       # v1.5.0 rebuilt the hidden view in here
out["hidden_rebuilds"] = REBUILDS[mark:].count(False)

spy = PaintSpy(dlg)
dlg.view.viewport().installEventFilter(spy)
dlg.show()                      # what open_optical_schematic() does
out["at_show"] = labels(dlg)    # before the event loop runs: what the first paint draws
out["found_at_show"] = found(dlg, "TB-2")
end = time.perf_counter() + 2.0
while not spy.seen and time.perf_counter() < end:
    APP.processEvents()
out["first_paint"] = spy.seen[0] if spy.seen else None
pump(0.8)
out["settled"] = labels(dlg)
out["found_settled"] = found(dlg, "TB-2")

# show() on the visible view: Qt6 sends showEvent again, Qt5 does not.
mark = len(REBUILDS)
dlg.show()
pump(0.6)
out["reshow_rebuilds"] = len(REBUILDS) - mark

# The open view still follows a commit, through the 400 ms debounce.
mark = len(REBUILDS)
set_capacity("96")
pump(0.8)
out["open_commit_rebuilds"] = REBUILDS[mark:].count(True)
out["after_open_commit"] = labels(dlg)

# Closed and shown again with nothing changed in between: nothing to catch up.
dlg.close()
pump(0.6)
mark = len(REBUILDS)
dlg.show()
pump(0.6)
out["unchanged_reshow_rebuilds"] = len(REBUILDS) - mark

# A commit while open, and the view closed before its 400 ms timer fires.
mark = len(REBUILDS)
set_capacity("144")
dlg.close()
pump(0.8)
out["closed_before_timer_hidden_rebuilds"] = REBUILDS[mark:].count(False)
dlg.show()
out["closed_before_timer_at_show"] = labels(dlg)
pump(0.6)
out["errors"] = ERRORS
print("RESULT " + json.dumps(out), flush=True)
os._exit(0)
'''


@pytest.fixture(scope="module")
def child(tmp_path_factory):
    """Run the driver once for the whole module: ``(returncode, result, output)``."""
    folder = tmp_path_factory.mktemp("schematic_visibility")
    script = folder / "schematic_visibility.py"
    script.write_text(DRIVER.format(repo=REPO_ROOT), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(folder),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [line for line in output.splitlines() if line.startswith("RESULT ")]
    result = json.loads(lines[-1][len("RESULT "):]) if lines else None
    return done.returncode, result, output


def _ok(child):
    code, result, output = child
    assert code == 0, f"returncode {code} (-11/139 is SIGSEGV)\n{output}"
    assert result is not None, output
    assert result["errors"] == [], output
    return result, output


def test_a_closed_view_does_not_rebuild_on_a_commit(child):
    """v1.5.0: one full rebuild of the hidden view per commit."""
    result, output = _ok(child)
    assert result["hidden_rebuilds"] == 0, output


def test_a_reopened_view_paints_what_changed_while_it_was_closed(child):
    result, output = _ok(child)
    # Control: the two edits do reach the view once it has settled.
    assert result["settled"] != result["before"], output
    assert "48" in " ".join(result["settled"]) and "TB-2" in result["settled"], output
    assert result["at_show"] == result["settled"], (
        "the view came back showing the scene from before it was closed "
        f"(v1.5.0 did not)\nat show: {result['at_show']}\nsettled: {result['settled']}")
    if result["first_paint"] is not None:
        assert result["first_paint"] == result["settled"], result["first_paint"]


def test_search_and_center_find_an_element_added_while_closed(child):
    result, output = _ok(child)
    assert result["found_settled"], output
    assert result["found_at_show"], "Search/Center could not find TB-2 when the view came back"


def test_the_first_open_builds_the_scene_once(child):
    """The constructor builds it; the first showEvent has nothing to catch up."""
    result, output = _ok(child)
    assert result["first_open_rebuilds"] == 1, output


def test_show_on_a_visible_view_does_not_rebuild_it(child):
    """Every click on the toolbar button calls show(); on Qt6 that is a showEvent."""
    result, output = _ok(child)
    assert result["reshow_rebuilds"] == 0, (
        "show() on the visible view rebuilt it: the catch-up is not gated on "
        f"a change while hidden\n{output}")


def test_an_open_view_still_follows_commits(child):
    result, output = _ok(child)
    assert result["open_commit_rebuilds"] == 1, output
    assert "96" in " ".join(result["after_open_commit"]), output


def test_reopening_with_nothing_changed_does_not_rebuild(child):
    result, output = _ok(child)
    assert result["unchanged_reshow_rebuilds"] == 0, output


def test_a_view_closed_before_its_timer_fires_catches_up_on_show(child):
    """The commit's debounce timer fires on a hidden view: it waits for the show."""
    result, output = _ok(child)
    assert result["closed_before_timer_hidden_rebuilds"] == 0, output
    assert "144" in " ".join(result["closed_before_timer_at_show"]), output
