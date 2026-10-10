"""The optical schematic view must not outlive the plugin that opened it.

WP4 item U17, unclaimed. ``OpticalSchematicDialog`` follows the project: it
connects ``QgsProject.instance().layersAdded`` and ``layerWillBeRemoved``, and
five commit signals of every vector layer present when it opens. v1.5.0
connected the two project signals to lambdas capturing ``self`` and kept no
reference to them, so nothing could disconnect them, and
``FiberQPlugin.unload()`` only called ``close()`` on the view and dropped its
reference. The view is parented to the QGIS main window,
so it lived on, hidden and connected, and rebuilt itself after every commit for
the rest of the session: one more hidden copy per plugin reload, each holding
the unloaded plugin through ``dlg.core``.

Measured on v1.5.0 and on the tree before this change, 3.22 through 4.2: after
``unload()`` a layer add and a commit each still ran a full rebuild, and after
an emulated reload both the old and the new view rebuilt. Since the visibility
gate, a hidden view only marks itself stale instead of rebuilding; it is still
connected, still called, and still keeps the old plugin alive. So these tests
look at whether any method of the view runs after unload -- before the view's
deferred deletion, where only a real disconnect keeps the signals out (once a
QObject is deleted, PyQt drops signals to its bound methods anyway), and
after it.

Why a **subprocess**. An exception escaping a Qt slot kills a plain Python
interpreter (exit 139 on every supported version, measured), and pytest-qgis
starts its ``QgsApplication`` in ``pytest_configure``, so one bad slot takes the
whole run with it. The obvious half-fix -- ``deleteLater()`` on the view while
the lambdas stay connected -- does exactly that: the next ``layersAdded`` calls
into a deleted ``QTimer`` and then a deleted ``QGraphicsScene``. The child also
gets its own ``initGui()``/``unload()``, which in-process would leave toolbars,
translators and project hooks behind for every later test.
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
import inspect
import json
import os
import sys
import time
from unittest import mock

sys.path.insert(0, {repo!r})

from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)

QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()

from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QEvent
from qgis.PyQt.QtWidgets import QMainWindow, QMessageBox, QToolBar, QWidget

# open_optical_schematic() reports a failure with QMessageBox.critical, which
# would block a headless child until the timeout instead of failing it.
QMessageBox.critical = staticmethod(lambda *a, **k: print("CRITICAL", a[1:3], flush=True))

#: Anything escaping a slot lands here instead of killing the interpreter.
ERRORS = []
sys.excepthook = lambda kind, value, tb: ERRORS.append("%s: %s" % (kind.__name__, value))


class Iface:
    """What initGui() and unload() really use; the rest answers with a MagicMock."""

    def __init__(self):
        self._window = QMainWindow()
        self._canvas = QgsMapCanvas(self._window)
        self._window.setCentralWidget(self._canvas)
        self._mocks = {{}}

    def mainWindow(self):
        return self._window

    def mapCanvas(self):
        return self._canvas

    def addToolBar(self, name):
        return QToolBar(name, self._window)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self.__dict__["_mocks"].setdefault(name, mock.MagicMock(name=name))


def pump(seconds):
    """Run the event loop long enough for the view's 400 ms debounce to fire."""
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
    return QgsPointXY(2437000.0 + x, 5365000.0 + y)


def commit_edit(lyr, value):
    assert lyr.startEditing()
    assert lyr.changeAttributeValue(1, lyr.fields().indexFromName("kapacitet"), value)
    assert lyr.commitChanges(), lyr.commitErrors()


project = QgsProject.instance()
nodes = layer("Point?crs=EPSG:3857&field=naziv:string", "ODF",
              [(QgsGeometry.fromPointXY(pt(0, 0)), {{"naziv": "ODF-1"}}),
               (QgsGeometry.fromPointXY(pt(300, 0)), {{"naziv": "TB-1"}})])
cables = layer("LineString?crs=EPSG:3857&field=od:string&field=do:string"
               "&field=podtip:string&field=kapacitet:string", "Underground cables",
               [(QgsGeometry.fromPolylineXY([pt(0, 0), pt(300, 0)]),
                 {{"od": "ODF-1", "do": "TB-1", "podtip": "glavni", "kapacitet": "24"}})])
spare = layer("Point?crs=EPSG:3857&field=naziv:string", "Poles", [])
project.addMapLayers([nodes, cables, spare])

from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog
from fiberq.main_plugin import FiberQPlugin

# Every method the view defines counts a call, whatever the design names its
# slots: a lambda calling self._schedule_rebuild() and a bound slot alike.
CALLS = []
for _name, _fn in list(vars(OpticalSchematicDialog).items()):
    if inspect.isfunction(_fn) and not _name.startswith("__"):
        def _spy(self, *a, _fn=_fn, _name=_name, **k):
            CALLS.append((id(self), _name))
            return _fn(self, *a, **k)
        setattr(OpticalSchematicDialog, _name, _spy)


def calls_of(view):
    return [name for who, name in CALLS if who == id(view)]

# initGui() arms a 2 s one-shot schema migration that commits on every layer.
# It is not what this test is about, and it must not land in the middle of it.
FiberQPlugin._run_schema_migrations = lambda self: None

plugin = FiberQPlugin(Iface())
plugin.initGui()
out = {{}}

# A. teardown() on its own, on a view that stays alive -- after one of the
# layers it followed has been removed (and so deleted) from the project.
view = OpticalSchematicDialog(plugin)
project.removeMapLayer(spare.id())
pump(0.8)
try:
    view.teardown()
    view.teardown()             # twice: unload() may follow an earlier call
    out["teardown"] = "ok"
except Exception as exc:
    out["teardown"] = "%s: %s" % (type(exc).__name__, exc)
del CALLS[:]
project.addMapLayer(layer("Point?crs=EPSG:3857&field=naziv:string", "early", []))
commit_edit(cables, "12")
pump(0.8)
out["after_teardown"] = sorted(set(calls_of(view)))

# B. the whole plugin: open, close, unload.
plugin.open_optical_schematic()
dlg = plugin._schematic_dlg
pump(0.2)

# Control: with the view open, a commit does reach it. Without this the
# assertion below could pass because the spies saw nothing at all.
del CALLS[:]
commit_edit(cables, "48")
pump(0.8)
out["open_rebuilds"] = calls_of(dlg).count("rebuild")

dlg.close()
pump(0.2)
plugin.unload()

# Before control returns to the event loop the view still exists, so only a
# disconnect keeps these from reaching it.
del CALLS[:]
late = layer("Point?crs=EPSG:3857&field=naziv:string", "late", [])
project.addMapLayer(late)
commit_edit(cables, "96")
project.removeMapLayer(nodes.id())
pump(0.8)
before_delete = list(CALLS)

# Once it is deleted, nothing may reach into what is gone.
APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
pump(0.2)
del CALLS[:]
project.addMapLayer(layer("Point?crs=EPSG:3857&field=naziv:string", "later", []))
commit_edit(cables, "192")
project.removeMapLayer(late.id())
pump(0.8)
CALLS[:0] = before_delete

left = [w for w in plugin.iface.mainWindow().findChildren(QWidget)
        if type(w).__name__ == "OpticalSchematicDialog" and w is not view]
out.update(after_unload=sorted(set(name for _, name in CALLS)), after_unload_calls=len(CALLS),
           views_left=len(left), errors=ERRORS)
print("RESULT " + json.dumps(out), flush=True)
sys.stdout.flush()
os._exit(0)
'''


@pytest.fixture(scope="module")
def child(tmp_path_factory):
    """Run the driver once for the whole module: ``(returncode, result, output)``."""
    folder = tmp_path_factory.mktemp("schematic_lifecycle")
    script = folder / "schematic_lifecycle.py"
    script.write_text(DRIVER.format(repo=REPO_ROOT), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(folder), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(folder),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT ")]
    result = json.loads(lines[-1][len("RESULT "):]) if lines else None
    return done.returncode, result, output


def _ok(child):
    code, result, output = child
    assert code == 0, f"returncode {code} (-11/139 is SIGSEGV)\n{output}"
    assert result is not None, output
    return result, output


def test_teardown_disconnects_a_view_that_stays_alive(child):
    """``teardown()`` alone silences the view, even with a followed layer deleted."""
    result, output = _ok(child)
    assert result["teardown"] == "ok", output
    assert result["after_teardown"] == [], (
        f"after teardown() the view still ran {result['after_teardown']}\n{output}")


def test_after_unload_no_schematic_slot_fires(child):
    """A layer add, a commit and a layer removal after unload reach no view method,
    before the view's deferred deletion and after it."""
    result, output = _ok(child)
    assert result["open_rebuilds"] >= 1, (
        f"the control failed: an open view did not rebuild on a commit, so the "
        f"spies prove nothing\n{output}")
    assert result["errors"] == [], output
    assert result["after_unload"] == [], (
        f"after unload() the view still ran {result['after_unload_calls']} "
        f"method calls: {result['after_unload']}\n{output}")
    assert result["views_left"] == 0, (
        "unload() left the view under the main window: it is parented there, "
        "so close() and dropping the reference keep it alive for the session")


# ---------------------------------------------------------------------------
# A visible view follows layers added and removed, as v1.5.0's did
# ---------------------------------------------------------------------------

FOLLOW_DRIVER = '''
import json, os, sys, time
sys.path.insert(0, {repo!r})
os.environ["FIBERQ_LOG_FILE"] = "false"
from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)
QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()
from qgis.PyQt.QtWidgets import QGraphicsTextItem

#: Anything escaping a slot lands here instead of killing the interpreter.
ERRORS = []
sys.excepthook = lambda kind, value, tb: ERRORS.append("%s: %s" % (kind.__name__, value))

from fiberq.core.data_manager import DataManager
from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog


def pump(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        APP.processEvents()
        time.sleep(0.01)


def pt(x, y):
    return QgsPointXY(2437000.0 + x, 5365000.0 + y)


def layer(uri, name, rows):
    lyr = QgsVectorLayer(uri, name, "memory")
    feats = []
    for geom, attrs in rows:
        feat = QgsFeature(lyr.fields())
        feat.setGeometry(geom)
        for key, value in attrs.items():
            feat.setAttribute(key, value)
        feats.append(feat)
    if feats:
        assert lyr.dataProvider().addFeatures(feats)[0]
    return lyr


def labels(view):
    return sorted(i.toPlainText() for i in view.scene.items() if isinstance(i, QGraphicsTextItem))


CABLES = ("LineString?crs=EPSG:3857&field=od:string&field=do:string"
          "&field=podtip:string&field=kapacitet:string")
project = QgsProject.instance()
odf = layer("Point?crs=EPSG:3857&field=naziv:string", "ODF",
            [(QgsGeometry.fromPointXY(pt(0, 0)), {{"naziv": "ODF-1"}})])
project.addMapLayer(odf)
data = DataManager()
core = type("Core", (), {{}})()
core.iface = type("Iface", (), {{"mainWindow": lambda self: None}})()
core.list_all_cables = data.list_all_cables
core.list_all_pipes = data.list_all_pipes
view = OpticalSchematicDialog(core)
view.show()
pump(0.8)
out = {{"opened": labels(view)}}

# A populated element layer, then a populated cable layer, added while open.
project.addMapLayer(layer("Point?crs=EPSG:3857&field=naziv:string", "TB",
                          [(QgsGeometry.fromPointXY(pt(300, 0)), {{"naziv": "TB-1"}})]))
pump(0.8)
out["after_add_tb"] = labels(view)
cables = layer(CABLES, "Underground cables",
               [(QgsGeometry.fromPolylineXY([pt(0, 0), pt(300, 0)]),
                 {{"od": "ODF-1", "do": "TB-1", "podtip": "glavni", "kapacitet": "24"}})])
project.addMapLayer(cables)
pump(0.8)
out["after_add_cables"] = labels(view)

# Both removed again.
project.removeMapLayer(cables.id())
pump(0.8)
out["after_remove_cables"] = labels(view)
project.removeMapLayer(odf.id())
pump(0.8)
out["after_remove_odf"] = labels(view)
out["positions"] = sorted((getattr(view, "_last_positions", {{}}) or {{}}).keys())

# An unsaved cable in an open edit buffer is drawn, as the scans drew it.
unsaved = layer(CABLES, "Underground cables", [])
project.addMapLayer(unsaved)
pump(0.8)
assert unsaved.startEditing()
cable = QgsFeature(unsaved.fields())
cable.setGeometry(QgsGeometry.fromPolylineXY([pt(300, 0), pt(600, 0)]))
for key, value in {{"od": "TB-1", "do": "TB-2", "podtip": "glavni", "kapacitet": "12"}}.items():
    cable.setAttribute(key, value)
assert unsaved.addFeature(cable)
view.rebuild()
out["edit_buffer"] = labels(view)
out["errors"] = ERRORS
print("RESULT " + json.dumps(out), flush=True)
os._exit(0)
'''


@pytest.fixture(scope="module")
def follow_child(tmp_path_factory):
    """A visible view while layers come and go: ``(returncode, result, output)``."""
    folder = tmp_path_factory.mktemp("schematic_follow")
    script = folder / "schematic_follow.py"
    script.write_text(FOLLOW_DRIVER.format(repo=REPO_ROOT), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(folder), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(folder),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT ")]
    result = json.loads(lines[-1][len("RESULT "):]) if lines else None
    return done.returncode, result, output


def test_a_layer_added_to_the_project_shows_up_in_an_open_view(follow_child):
    """v1.5.0 rebuilt an open view on every layer added, through the lambdas
    this change replaced with named slots; without those rebuilds the view
    kept showing only what it opened with (measured on 3.22 through 4.2)."""
    result, output = _ok(follow_child)
    assert result["errors"] == [], output
    assert result["opened"] == ["ODF-1"], output
    assert result["after_add_tb"] == ["ODF-1", "TB-1"], output
    assert result["after_add_cables"] == ["24 / 218.5 m", "ODF-1", "TB-1"], output


def test_a_layer_removed_from_the_project_leaves_an_open_view(follow_child):
    """And on every layer removed: its labels go, and Search and Center no longer find them."""
    result, output = _ok(follow_child)
    assert result["after_remove_cables"] == ["ODF-1", "TB-1"], output
    assert result["after_remove_odf"] == ["TB-1"], output
    assert result["positions"] == ["TB-1"], output


def test_an_unsaved_cable_is_drawn(follow_child):
    """The view reads through the edit buffer, as the per-item scans did."""
    result, output = _ok(follow_child)
    assert "12 / 218.5 m" in result["edit_buffer"], result["edit_buffer"]
