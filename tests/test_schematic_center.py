"""The schematic view's Center button, which has never worked.

WP4 4.2 item R11. Two defects in four lines, the second hidden by the first.

**The brush.** The highlight ring was added with::

    self.scene.addEllipse(x, y, w, h, QPen(...), Qt.BrushStyle.NoBrush)

``addEllipse`` wants a ``QBrush`` there. Passing the enum is

    TypeError: argument 6 has unexpected type 'BrushStyle'

measured on **3.44.15 as well as 4.0.3** -- so this is not a Qt6 regression,
it is a button that has never once centred anything on any supported version.
``QBrush(Qt.BrushStyle.NoBrush)`` is the brush that means "no fill".

**The use-after-free underneath.** Removal was a closure over a local ``item``
fired by a 1300 ms timer. ``rebuild()`` calls ``scene.clear()``, which destroys
the item's C++ object, and ``removeItem`` on it afterwards is a **SIGSEGV** --
measured, child process returncode -11 on both stacks, not an exception
anything could catch. The schematic view rebuilds on ``layersAdded`` and
``layerWillBeRemoved``, so adding a layer within 1.3 s of pressing Center
would have taken QGIS down. Fixing only the brush would have turned a dead
button into a hard crash, which is why both are one commit.

The crash regression runs in a **subprocess** and asserts the exit code:
pytest-qgis starts its ``QgsApplication`` in ``pytest_configure``, so a
segfault anywhere takes the whole run with it rather than failing one test.

**And then it moved nothing.** v1.6.0 QA finding Q20, on QGIS 4.2.3: with
both defects fixed, Center on "MH 1" changed nothing anyone could see, and
the view had opened with the drawing a few pixels wide. The constructor fits
the scene before the dialog is shown, to Qt's default 98 x 28 viewport, so it
opened at scale 0.022; and the scene rect was the drawing, so ``centerOn()``
had nothing to scroll, and the ring, 12 units in radius, came out half a
pixel across. One row of 21 controls was also wider than the QA desktop's
1,920 px screen. The tests at the end open the dialog the way the toolbar
button does, on the QA project's elements, and look at what the user sees --
and at the exports, which a Center must leave as they were. Enter in the Find
box runs Center too; it pressed Zoom +, which QDialog had made its default.
"""
import json
import os
import subprocess
import sys

import pytest
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor, QPen
from qgis.PyQt.QtWidgets import QGraphicsScene, QGraphicsView

from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for the crash-regression child. The suite has no timeout
#: plugin, so without this a wedged child would run to the CI job's own limit.
TIMEOUT_S = 120


@pytest.fixture
def dialog(qgis_app):
    """The real ``_center_on`` / ``_drop_highlight`` on a real scene.

    ``OpticalSchematicDialog.__init__`` builds a whole dialog against a live
    ``iface``, which these two methods do not need and a headless run cannot
    cheaply provide. The methods under test are the real ones.
    """
    dlg = OpticalSchematicDialog.__new__(OpticalSchematicDialog)
    dlg.scene = QGraphicsScene()
    dlg.view = QGraphicsView(dlg.scene)
    dlg._highlight = None
    dlg._last_positions = {"ODF-1": (10.0, 20.0), "TB-2": (30.0, 40.0)}
    yield dlg
    dlg.scene.clear()


# ---------------------------------------------------------------------------
# The brush
# ---------------------------------------------------------------------------

def test_the_enum_really_is_rejected_as_a_brush(qgis_app):
    """The defect itself, so nobody writes it back."""
    scene = QGraphicsScene()
    pen = QPen(QColor(255, 165, 0), 2.4)
    with pytest.raises(TypeError):
        scene.addEllipse(0, 0, 10, 10, pen, Qt.BrushStyle.NoBrush)
    # and the form the fix uses
    assert scene.addEllipse(0, 0, 10, 10, pen, QBrush(Qt.BrushStyle.NoBrush)) is not None
    scene.clear()


def test_centering_on_a_known_element_adds_the_ring(dialog):
    dialog._center_on("ODF-1")
    assert dialog._highlight is not None
    assert dialog._highlight in dialog.scene.items()
    assert dialog._highlight.zValue() == 10


def test_centering_on_an_unknown_name_does_nothing(dialog):
    dialog._center_on("not in the layout")
    assert dialog._highlight is None
    assert dialog.scene.items() == []


def test_centering_twice_leaves_one_ring(dialog):
    """The second press drops the first ring rather than stacking them."""
    dialog._center_on("ODF-1")
    first = dialog._highlight
    dialog._center_on("TB-2")
    assert dialog._highlight is not first
    assert first not in dialog.scene.items()
    assert len(dialog.scene.items()) == 1


# ---------------------------------------------------------------------------
# The use-after-free
# ---------------------------------------------------------------------------

def test_dropping_the_highlight_is_idempotent(dialog):
    """The timer, the next press and rebuild() all call it, in any order."""
    dialog._center_on("ODF-1")
    dialog._drop_highlight()
    assert dialog._highlight is None
    dialog._drop_highlight()
    dialog._drop_highlight()
    assert dialog.scene.items() == []


def test_dropping_after_a_scene_clear_does_not_reach_the_dead_item(dialog):
    """``rebuild()`` drops the reference BEFORE clearing, which is the guard.

    Simulated here in the order that used to crash: clear the scene, then ask
    for the removal the timer would have asked for.
    """
    dialog._center_on("ODF-1")
    dialog._highlight = None          # what rebuild() does first
    dialog.scene.clear()              # what destroyed the C++ object
    dialog._drop_highlight()          # what the 1300 ms timer then calls
    assert dialog._highlight is None


CRASH_DRIVER = '''
import os, sys
sys.path.insert(0, {repo!r})
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication
app = QgsApplication([], True)
from qgis.PyQt.QtWidgets import QGraphicsScene, QGraphicsView
from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

dlg = OpticalSchematicDialog.__new__(OpticalSchematicDialog)
dlg.scene = QGraphicsScene()
dlg.view = QGraphicsView(dlg.scene)
dlg._highlight = None
dlg._last_positions = {{"ODF-1": (10.0, 20.0)}}

dlg._center_on("ODF-1")
print("centred", flush=True)
# What rebuild() does. The old code left the pending timer holding this item.
dlg._drop_highlight()
dlg.scene.clear()
print("rebuilt", flush=True)
# What the 1300 ms timer then fires. The old code segfaulted here.
dlg._drop_highlight()
print("SURVIVED", flush=True)
sys.stdout.flush()
os._exit(0)
'''


OLD_PATTERN_DRIVER = '''
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication
app = QgsApplication([], True)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor, QPen
from qgis.PyQt.QtWidgets import QGraphicsScene

# Exactly what _center_on used to do, with the brush already corrected so the
# TypeError does not mask what is underneath.
scene = QGraphicsScene()
item = scene.addEllipse(0, 0, 24, 24, QPen(QColor(255, 165, 0), 2.4),
                        QBrush(Qt.BrushStyle.NoBrush))

def _remove():                 # the closure the 1300 ms timer held
    scene.removeItem(item)

scene.clear()                  # what rebuild() does
print("cleared", flush=True)
_remove()                      # what the timer then fired
print("SURVIVED", flush=True)
sys.stdout.flush()
os._exit(0)
'''


def _child(tmp_path, name, source):
    script = tmp_path / name
    script.write_text(source, encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(tmp_path), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def test_the_old_closure_pattern_really_does_crash(tmp_path):
    """The hazard itself, pinned in a child so it costs this test only.

    Measured returncode -11 (SIGSEGV) on 3.44.15 and 4.0.3. Asserted as
    "did not exit cleanly" rather than exactly -11, because the signal is the
    platform's business; what matters is that it is not an exception the
    plugin could have caught, which is why ``_drop_highlight`` clears the
    reference instead of guarding the call.
    """
    code, output = _child(tmp_path, "old_pattern.py", OLD_PATTERN_DRIVER)
    assert "cleared" in output, output
    assert code != 0, (
        "removeItem() on an item destroyed by scene.clear() exited cleanly "
        f"here, so this QGIS no longer has the hazard: {output}")
    assert "SURVIVED" not in output, output


def test_rebuilding_then_firing_the_timer_does_not_crash_qgis(tmp_path):
    """Exit code is the only reliable signal: a SIGSEGV is not catchable."""
    script = tmp_path / "center_then_rebuild.py"
    script.write_text(CRASH_DRIVER.format(repo=str(REPO_ROOT)), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(tmp_path), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 0, f"returncode {done.returncode}\n{output}"
    assert "SURVIVED" in output, output


# ---------------------------------------------------------------------------
# What the user sees: the first view, Center, and the width (QA finding Q20)
# ---------------------------------------------------------------------------

VIEW_DRIVER = r'''
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
os.environ["FIBERQ_LOG_FILE"] = "false"
from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)
QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()
from qgis.PyQt.QtCore import QPoint, QPointF
from qgis.PyQt.QtWidgets import QFileDialog, QGraphicsEllipseItem, QLabel

#: Anything escaping a slot lands here instead of killing the interpreter.
ERRORS = []
sys.excepthook = lambda kind, value, tb: ERRORS.append("%s: %s" % (kind.__name__, value))

from fiberq.core.data_manager import DataManager
from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

REBUILDS = []
_rebuild = OpticalSchematicDialog.rebuild


def rebuild(self):
    REBUILDS.append(1)
    _rebuild(self)


OpticalSchematicDialog.rebuild = rebuild


def pump(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        APP.processEvents()
        time.sleep(0.005)


# The QA project's elements: their names, layers and cable ends, laid out as
# on its map -- metres east and north of its middle -- and stretched x3.2 to
# ~1.5 km across, around the point the other schematic tests draw at.
def pt(dx, dy):
    return QgsPointXY(2437000.0 + dx * 3.2, 5365000.0 + dy * 3.2)


POINTS = [
    ("Manholes", "broj_okna", [("1", -144.47, -36.43), ("222", 36.72, 66.53),
                               ("223", 137.81, 48.75), ("12312", 228.57, -37.09)]),
    ("Poles", "tip", [("POLE", -228.09, -65.58), ("POLE", -208.63, -9.07),
                      ("POLE", -118.38, 60.10), ("POLE", -19.15, 37.07),
                      ("POLE", 190.64, 12.01), ("POLE", 208.25, 37.07),
                      ("POLE", 178.45, -33.37)]),
    ("Joint Closures", "naziv", [("1", -208.63, -9.07), ("2", -228.09, -65.58)]),
    ("ODF", "naziv", [("1", -134.12, 35.63)]),
    ("TB", "naziv", [("2", -85.02, 14.30)]),
    ("Patch panel", "naziv", [("pp", -27.45, -2.98)]),
    ("OTB", "naziv", [("otb", -27.11, -34.47)]),
    ("Indoor OTB", "naziv", [("iotb", 13.19, -7.38)]),
    ("TO", "naziv", [("to", 13.53, 33.60)]),
    ("Indoor TO", "naziv", [("ito", -35.24, 29.20)]),
    ("Outdoor TO", "naziv", [("o to", -57.93, 55.27)]),
    ("Pole TO", "naziv", [("p to", -67.07, -2.30)]),
    ("Joint Closure TO", "naziv", [("j cl", -65.38, -29.73)]),
    ("Fiber break", "naziv", [("Fiber break", -195.33, -14.74)]),
    ("Outdoor OTB", "naziv", [("O OTB", 120.88, -2.89)]),
    ("Pole OTB", "naziv", [("P OTB", 52.47, -28.29)]),
]
CABLE = "od:string&field=do:string&field=podtip:string"
PIPE = "od:string&field=do:string&field=kapacitet:string&field=fi:integer"
LINES = [
    ("Underground cables", CABLE, [
        ([(-208.63, -9.07), (-212.58, -20.56)], {"od": "1", "do": "2", "podtip": "glavni"}),
        ([(-212.58, -20.56), (-228.09, -65.58)], {"od": "1", "do": "2", "podtip": "glavni"}),
        ([(-35.24, 29.20), (-85.02, 14.30)], {"od": "ito", "do": "2", "podtip": "razvodni"})]),
    ("Aerial cables", CABLE, [
        ([(-208.63, -9.07), (-85.02, 14.30)], {"od": "1", "do": "2", "podtip": "distributivni"}),
        ([(-35.24, 29.20), (-85.02, 14.30)], {"od": "ito", "do": "2", "podtip": "razvodni"})]),
    ("PE pipes", PIPE, [([(-134.12, 35.63), (-118.38, 60.10)],
                         {"od": "Pole POLE", "do": "Pole POLE", "kapacitet": "1x1", "fi": 40})]),
    ("Transition pipes", PIPE, [([(-118.38, 60.10), (-105.83, 33.79)],
                                 {"od": "Pole POLE", "do": "Pole POLE", "kapacitet": "1x1", "fi": 110})]),
]


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


layers = [layer("Point?crs=EPSG:3857&field=%s:string" % field, name,
                [(QgsGeometry.fromPointXY(pt(x, y)), {field: value}) for value, x, y in rows])
          for name, field, rows in POINTS]
layers += [layer("LineString?crs=EPSG:3857&field=" + fields, name,
                 [(QgsGeometry.fromPolylineXY([pt(*p) for p in line]), attrs) for line, attrs in rows])
           for name, fields, rows in LINES]
project = QgsProject.instance()
project.setCrs(layers[0].crs())
project.addMapLayers(layers)

data = DataManager()
core = type("Core", (), {})()
core.iface = type("Iface", (), {"mainWindow": lambda self: None})()
core.list_all_cables = data.list_all_cables
core.list_all_pipes = data.list_all_pipes


def scale(dlg):
    return round(dlg.view.transform().m11(), 4)


def fitted(dlg):
    """The view's scale over the one fitInView() gives the viewport as shown,
    and how much of the viewport the drawing fills, in its fuller direction."""
    view = dlg.view
    drawing = dlg.scene.itemsBoundingRect()
    padded = drawing.adjusted(-40, -40, 40, 40)
    room = view.viewport().rect().adjusted(2, 2, -2, -2)
    best = min(room.width() / padded.width(), room.height() / padded.height())
    seen = view.mapFromScene(drawing).boundingRect()
    return {"scale": scale(dlg), "fit": round(best, 4), "ratio": round(view.transform().m11() / best, 4),
            "fill": round(max(seen.width() / room.width(), seen.height() / room.height()), 3),
            "viewport": [view.viewport().width(), view.viewport().height()]}


def offset(dlg, name):
    """How far the element is from the middle of the viewport, in pixels."""
    view = dlg.view
    at = view.mapFromScene(QPointF(*dlg._last_positions[name]))
    middle = view.viewport().rect().center()
    return [at.x() - middle.x(), at.y() - middle.y()]


def ring(dlg):
    """The Center ring's diameter on screen, in pixels; None if there is none."""
    item = getattr(dlg, "_highlight", None)
    if item is None:
        return None
    return round(item.deviceTransform(dlg.view.viewportTransform()).mapRect(item.rect()).width(), 2)


def ring_inside(dlg):
    """Across the inside edge of the ring's line, on screen, in pixels."""
    item = getattr(dlg, "_highlight", None)
    if item is None:
        return None
    half = item.pen().widthF() / 2.0
    inside = item.rect().adjusted(half, half, -half, -half)
    return round(item.deviceTransform(dlg.view.viewportTransform()).mapRect(inside).width(), 2)


def circle(dlg, name):
    """Across the element's own circle, its outline included, on screen, in pixels."""
    x, y = dlg._last_positions[name]
    for item in dlg.scene.items():
        middle = item.rect().center() if isinstance(item, QGraphicsEllipseItem) else None
        if (middle is not None and abs(item.rect().width() - 12.0) < 1e-6
                and abs(middle.x() - x) < 1e-6 and abs(middle.y() - y) < 1e-6):
            mapped = item.deviceTransform(dlg.view.viewportTransform()).mapRect(item.boundingRect())
            return round(mapped.width(), 2)
    return None


def centre(dlg):
    return dlg.view.mapToScene(dlg.view.viewport().rect().center())


def press_center(dlg, text):
    dlg.txt_search.setText(text)
    dlg.btn_center.click()
    pump(0.15)


def circles(dlg):
    """The nodes drawn: the radius-6 circles."""
    return sum(1 for item in dlg.scene.items()
               if isinstance(item, QGraphicsEllipseItem) and abs(item.rect().width() - 12.0) < 1e-6)


def says(dlg, text):
    """What the dialog shows about text: a label on screen whose words fit
    it, naming text in them or, when they had to be cut short, in its tooltip."""
    return [lb.text() for lb in dlg.findChildren(QLabel)
            if lb.isVisible() and lb.text()
            and lb.width() >= lb.fontMetrics().horizontalAdvance(lb.text())
            and (text in lb.text() or text in lb.toolTip())]


out = {}
# As open_optical_schematic() opens it.
mark = len(REBUILDS)
dlg = OpticalSchematicDialog(core)
dlg.show()
dlg.raise_()
dlg.activateWindow()
pump(0.3)
out["open_rebuilds"] = len(REBUILDS) - mark
out["size"] = [dlg.width(), dlg.height()]
out["min_width"] = dlg.minimumSizeHint().width()
out["boxes"] = {b.placeholderText(): [b.width(), b.fontMetrics().horizontalAdvance(b.placeholderText())]
                for b in (dlg.txt_search, dlg.txt_rel)}
top = dlg.btn_pan.mapTo(dlg, QPoint(0, 0)).y()
out["rows"] = {"pan_bottom": top + dlg.btn_pan.height(),
               "styling_top": dlg.chk_map_layout.mapTo(dlg, QPoint(0, 0)).y()}
out["first"] = fitted(dlg)

# A name that matches nothing, in the window as it opened.
before = (scale(dlg), centre(dlg))
press_center(dlg, "MH 999")
out["nomatch"] = {"says": says(dlg, "MH 999"), "ring": ring(dlg),
                  "view_moved": before[0] != scale(dlg) or (before[1] - centre(dlg)).manhattanLength() > 0.5}

# What a window manager may do once the window is up.
dlg.resize(1500, 900)
pump(0.3)
out["wm_resize"] = fitted(dlg)

press_center(dlg, "MH 1")
out["center"] = {"scale": scale(dlg), "offset": offset(dlg, "MH 1"), "ring": ring(dlg),
                 "inside": ring_inside(dlg), "circle": circle(dlg, "MH 1")}

# The user zooms closer than Center would, then centres on another element.
dlg.btn_zoom_in.click()
dlg.btn_zoom_in.click()
pump(0.1)
closer = scale(dlg)
press_center(dlg, "MH 12312")
out["closer"] = {"before": closer, "scale": scale(dlg), "offset": offset(dlg, "MH 12312"),
                 "ring": ring(dlg), "inside": ring_inside(dlg), "circle": circle(dlg, "MH 12312")}

# Having zoomed, the user resizes the window: the zoom stays theirs.
dlg.resize(1300, 820)
pump(0.3)
out["user_resize"] = {"before": closer, "scale": scale(dlg)}

press_center(dlg, "mh 222")
out["case"] = {"ring": ring(dlg), "offset": offset(dlg, "MH 222")}
pump(2.0)
out["ring_after_2s"] = ring(dlg)

dlg.btn_fit.click()
pump(0.1)
out["fit"] = fitted(dlg)

dlg.chk_map_layout.setChecked(True)
mark = len(REBUILDS)
dlg.btn_apply.click()
pump(0.3)
out["apply_rebuilds"] = len(REBUILDS) - mark
out["map"] = fitted(dlg)
press_center(dlg, "MH 1")
out["map_center"] = {"scale": scale(dlg), "offset": offset(dlg, "MH 1"), "ring": ring(dlg),
                     "inside": ring_inside(dlg), "circle": circle(dlg, "MH 1")}
pump(2.0)

# QA step E.2: Center, Refresh within a second, a layer added meanwhile.
nodes = circles(dlg)
press_center(dlg, "MH 1")
mark = len(REBUILDS)
dlg.btn_refresh.click()
project.addMapLayer(QgsVectorLayer("Point?crs=EPSG:3857&field=naziv:string", "late", "memory"))
pump(2.0)
out["race"] = {"nodes_before": nodes, "nodes_after": circles(dlg), "ring": ring(dlg),
               "rebuilds": len(REBUILDS) - mark}

# The exports. They draw the scene's own sceneRect(), which grows with what is
# added and never shrinks, so what one Center does to it stays for the session:
# a fresh view, before its first Center.
EXPORTS = []


def export(view, kind):
    path = os.path.join(os.getcwd(), "schematic-%d.%s" % (len(EXPORTS), kind))
    EXPORTS.append(path)
    QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: (path, ""))
    getattr(view, "_export_" + kind)()
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


def box(rect):
    return [round(v, 3) for v in (rect.left(), rect.top(), rect.right(), rect.bottom())]


dlg.teardown()
dlg.close()
fresh = OpticalSchematicDialog(core)
fresh.show()
pump(0.3)
scene = fresh.scene
pos = fresh._last_positions
rect = scene.sceneRect()
inner = rect.adjusted(30, 30, -30, -30)
inside = sorted(name for name, (x, y) in pos.items() if inner.contains(QPointF(x, y)))
first = {kind: export(fresh, kind) for kind in ("png", "jpg", "svg")}
press_center(fresh, inside[0])
pump(2.0)
again = {kind: export(fresh, kind) for kind in ("png", "jpg", "svg")}
out["exports"] = {"element": inside[0], "rect_before": box(rect), "rect_after": box(scene.sceneRect()),
                  "same": {kind: first[kind] == again[kind] for kind in first},
                  "written": {kind: first[kind] is not None for kind in first}}

# At the drawing's top edge the ring reaches past it: the rect may grow there.
highest = min(pos, key=lambda name: (pos[name][1], name))
rect = scene.sceneRect()
press_center(fresh, highest)
drawn = fresh._highlight.sceneBoundingRect()
pump(2.0)
out["edge"] = {"element": highest, "expected": box(rect.united(drawn)), "rect": box(scene.sceneRect())}

# Zoomed in well past Center's own zoom, the ring still goes round the element.
for _ in range(5):
    fresh.btn_zoom_in.click()
pump(0.1)
press_center(fresh, inside[0])
out["closest"] = {"scale": scale(fresh), "ring": ring(fresh), "inside": ring_inside(fresh),
                  "circle": circle(fresh, inside[0])}
pump(2.0)
out["errors"] = ERRORS
print("RESULT " + json.dumps(out), flush=True)
os._exit(0)
'''


@pytest.fixture(scope="module")
def view_child(tmp_path_factory):
    """The dialog opened as the toolbar opens it: ``(returncode, result, output)``."""
    folder = tmp_path_factory.mktemp("schematic_view")
    script = folder / "schematic_view.py"
    script.write_text(VIEW_DRIVER, encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(folder), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script), REPO_ROOT], cwd=str(folder),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT ")]
    result = json.loads(lines[-1][len("RESULT "):]) if lines else None
    return done.returncode, result, output


def _seen(view_child):
    code, result, output = view_child
    assert code == 0, f"returncode {code} (-11/139 is SIGSEGV)\n{output}"
    assert result is not None, output
    assert result["errors"] == [], output
    return result, output


def _fitted(state):
    return 0.98 <= state["ratio"] <= 1.02


def _centred(state):
    return max(abs(v) for v in state["offset"]) <= 2


def _rings_the_element(state):
    """A ring at least 24 px across whose line clears the element's circle."""
    if state["ring"] is None:
        return False
    return state["ring"] >= 24.0 - 0.5 and state["inside"] > state["circle"]


def test_the_first_view_shows_the_whole_drawing_fitted_to_its_window(view_child):
    """The scene used to be fitted to the 98 x 28 viewport the view has before
    the dialog is shown: scale 0.022 where 0.6 fits, 17 x 24 px of drawing."""
    result, output = _seen(view_child)
    first = result["first"]
    assert _fitted(first), (
        f"the view opened at scale {first['scale']}, where its {first['viewport']} viewport "
        f"fits the drawing at {first['fit']}\n{output}")
    assert first["fill"] >= 0.85, first
    # Fitted by following the window, not by building the scene again.
    assert result["open_rebuilds"] == 1, result["open_rebuilds"]


def test_the_drawing_follows_the_window_until_the_user_zooms(view_child):
    """A window manager may resize the window after show(). Once the user
    has zoomed, a resize keeps their zoom."""
    result, output = _seen(view_child)
    resized = result["wm_resize"]
    assert _fitted(resized), (
        f"after the window was resized the view stayed at scale {resized['scale']}, where "
        f"{resized['fit']} fits\n{output}")
    user = result["user_resize"]
    assert user["scale"] == pytest.approx(user["before"], rel=1e-3), user


def test_center_brings_the_element_to_the_middle_at_a_readable_zoom(view_child):
    """In both layouts, and without zooming out a view the user brought closer."""
    result, output = _seen(view_child)
    for key in ("center", "map_center"):
        state = result[key]
        assert state["scale"] >= 1.0 - 1e-6, (
            f"{key}: Center left the labels at scale {state['scale']}\n{output}")
        assert _centred(state), (
            f"{key}: MH 1 ended up {state['offset']} px from the middle of the view\n{output}")
    closer = result["closer"]
    assert closer["before"] > 1.0, closer
    assert closer["scale"] == pytest.approx(closer["before"], rel=1e-3), closer
    assert _centred(closer), closer
    # Fit puts back the scene rect Center widened. Not to the pixel: pressed
    # while scroll bars show, fitInView() measures the viewport without the
    # room they give back a moment later (0.98 measured), as it always has.
    fit = result["fit"]
    assert 0.95 <= fit["ratio"] <= 1.02 and fit["fill"] >= 0.85, (
        f"Fit after Center did not show the whole drawing: {fit}")
    assert result["apply_rebuilds"] == 1, result["apply_rebuilds"]


def test_the_center_ring_goes_round_the_element_at_any_zoom(view_child):
    """The ring, 12 scene units in radius, was 0.5 px across at the opening
    zoom. At the zoom Center now leaves it is at least 24 px across, and
    closer it grows with the element's circle: a ring of a fixed 30 px lay
    inside that circle at scale 3.05. It still goes after 1.5 s, also when
    Refresh and a new layer come first (QA step E.2)."""
    result, output = _seen(view_child)
    for key in ("center", "closer", "map_center", "closest"):
        state = result[key]
        assert _rings_the_element(state), (
            f"{key}: at scale {state['scale']} the ring is {state['ring']} px across, "
            f"{state['inside']} px inside its line, round a {state['circle']} px circle\n{output}")
    assert result["closest"]["scale"] > 3.0, result["closest"]
    assert result["ring_after_2s"] is None, result["ring_after_2s"]
    race = result["race"]
    assert race["nodes_after"] == race["nodes_before"] > 0, race
    assert race["ring"] is None, race


def test_a_center_leaves_the_exports_as_they_were(view_child):
    """PNG, JPG and SVG draw the scene's own sceneRect(), which grows and never
    shrinks. A ring that ignored the zoom went into it at the scene's origin,
    not where it was drawn (Qt 5.15.3, 5.15.13, 6.8.2), so from the first
    Center on, every export put the drawing about 9 px further right and 0.3%
    smaller. The ring may widen that rect only where it is drawn: past the
    drawing's edge, as it always could."""
    result, output = _seen(view_child)
    exports = result["exports"]
    assert all(exports["written"].values()), exports
    assert all(exports["same"].values()), (
        f"Center on {exports['element']!r}, inside the drawing, changed the exports "
        f"(same: {exports['same']}): the exported rect went from {exports['rect_before']} "
        f"to {exports['rect_after']}")
    assert exports["rect_after"] == exports["rect_before"], exports
    edge = result["edge"]
    assert edge["rect"] == pytest.approx(edge["expected"], abs=1e-3), (
        f"Center on {edge['element']!r}, at the drawing's top, grew the exported rect to "
        f"{edge['rect']}, not by the ring where it was drawn: {edge['expected']}")


def test_a_name_typed_in_another_case_finds_the_element(view_child):
    """The completer matches any case; Center needed the exact one."""
    result, output = _seen(view_child)
    case = result["case"]
    assert case["ring"] is not None, f"Center found nothing for 'mh 222'\n{output}"
    assert _centred(case), case


def test_a_name_that_matches_nothing_says_so_in_the_dialog(view_child):
    """In the window as it opens. Where the row has too little room for the
    whole message (3.40.15 at 1,200 px), it ends in an ellipsis, and the
    tooltip has it all."""
    result, output = _seen(view_child)
    nomatch = result["nomatch"]
    assert nomatch["says"], f"Center on 'MH 999' showed nothing in the dialog\n{output}"
    assert nomatch["ring"] is None, nomatch
    assert not nomatch["view_moved"], nomatch


def test_the_controls_fit_a_1366_px_screen(view_child):
    """One row of 21 controls was 1,784 px wide at its narrowest on 4.2.3
    and 2,070 px on 3.22.16 and 3.40.15; the dialog opened that wide."""
    result, output = _seen(view_child)
    assert result["min_width"] <= 1366, (
        f"the dialog cannot be narrower than {result['min_width']} px\n{output}")
    assert result["size"][0] <= 1366, result["size"]
    rows = result["rows"]
    assert rows["styling_top"] >= rows["pan_bottom"], rows


def test_the_text_boxes_are_wide_enough_to_read(view_child):
    """At 1,200 px the second row left "Relation contains…" 41 px on
    3.40.15 (offscreen, Qt5 fonts), so it read "R…"."""
    result, output = _seen(view_child)
    for hint, (width, needed) in result["boxes"].items():
        assert width >= needed, f"{hint!r} is {width} px wide, its hint needs {needed} px\n{output}"


# ---------------------------------------------------------------------------
# Enter in the Find box
# ---------------------------------------------------------------------------

ENTER_DRIVER = r'''
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
os.environ["FIBERQ_LOG_FILE"] = "false"
from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)
QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()
from qgis.PyQt.QtCore import QPointF, Qt
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QPushButton

#: Anything escaping a slot lands here instead of killing the interpreter.
ERRORS = []
sys.excepthook = lambda kind, value, tb: ERRORS.append("%s: %s" % (kind.__name__, value))
#: Message boxes and export file dialogs, answered instead of waited on.
SAID = []
for _kind in ("critical", "warning", "information", "question"):
    setattr(QMessageBox, _kind, staticmethod(
        lambda *a, _k=_kind, **kw: SAID.append(_k) or QMessageBox.StandardButton.Ok))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **kw: SAID.append("save") or ("", ""))

from fiberq.core.data_manager import DataManager
from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

#: The name in the box each time Center runs, however it was pressed; and
#: each rebuild. Wrapped before the dialog connects its buttons to them.
CENTERS = []
REBUILDS = []
_center = OpticalSchematicDialog._center_on_query
_rebuild = OpticalSchematicDialog.rebuild


def center_on_query(self, *args):
    CENTERS.append(self.txt_search.text())
    return _center(self)


def rebuild(self):
    REBUILDS.append(1)
    return _rebuild(self)


OpticalSchematicDialog._center_on_query = center_on_query
OpticalSchematicDialog.rebuild = rebuild


def pump(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        APP.processEvents()
        time.sleep(0.005)


# Four of the QA project's manholes: "MH 1" begins "MH 12312" as well, and
# "mh 22" begins MH 222 and MH 223, so typing them opens a list of two.
manholes = QgsVectorLayer("Point?crs=EPSG:3857&field=broj_okna:string", "Manholes", "memory")
rows = []
for number, x, y in (("1", -144.47, -36.43), ("222", 36.72, 66.53),
                     ("223", 137.81, 48.75), ("12312", 228.57, -37.09)):
    feat = QgsFeature(manholes.fields())
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2437000.0 + x * 3.2, 5365000.0 + y * 3.2)))
    feat.setAttribute("broj_okna", number)
    rows.append(feat)
assert manholes.dataProvider().addFeatures(rows)[0]
QgsProject.instance().addMapLayer(manholes)
data = DataManager()
core = type("Core", (), {})()
core.iface = type("Iface", (), {"mainWindow": lambda self: None})()
core.list_all_cables = data.list_all_cables
core.list_all_pipes = data.list_all_pipes

dlg = OpticalSchematicDialog(core)
dlg.show()
dlg.raise_()
dlg.activateWindow()
pump(0.3)
window = dlg.windowHandle()


def key(which):
    """Press a key as the keyboard does: the window hands it to the list of
    names when that is open, else to the widget with the focus."""
    QTest.keyClick(window, which)
    pump(0.2)


def scale():
    return round(dlg.view.transform().m11(), 4)


def defaults():
    return [button.text() for button in dlg.findChildren(QPushButton) if button.isDefault()]


def offset(name):
    view = dlg.view
    at = view.mapFromScene(QPointF(*dlg._last_positions[name]))
    middle = view.viewport().rect().center()
    return [at.x() - middle.x(), at.y() - middle.y()]


def enter(name):
    """Enter in the Find box, then what it did."""
    mark, before = len(CENTERS), scale()
    key(Qt.Key.Key_Return)
    found = dlg._find_node(name)
    state = {"centers": CENTERS[mark:], "text": dlg.txt_search.text(), "scale_before": before,
             "scale": scale(), "ring": getattr(dlg, "_highlight", None) is not None,
             "offset": offset(found) if found else None, "list_open": dlg._completer.popup().isVisible()}
    pump(1.8)
    dlg.btn_fit.click()
    pump(0.2)
    return state


def type_in_box(text):
    dlg.txt_search.clear()
    QTest.keyClicks(dlg.txt_search, text)
    pump(0.2)
    return dlg._completer.popup().isVisible()


out = {"defaults_at_open": defaults()}
dlg.txt_search.setFocus()
pump(0.1)
out["focus_in_box"] = dlg.txt_search.hasFocus()

# The list closed: a name set in the box, Enter.
dlg.txt_search.setText("MH 1")
pump(0.1)
out["closed"] = dict(enter("MH 1"), list_was_open=dlg._completer.popup().isVisible())

# The list open, a name chosen in it with the arrow key, Enter.
was_open = type_in_box("mh 22")
key(Qt.Key.Key_Down)
out["chosen"] = dict(enter("MH 222"), list_was_open=was_open)

# The list open, nothing chosen in it, Enter: the name as typed.
was_open = type_in_box("MH 1")
out["typed"] = dict(enter("MH 1"), list_was_open=was_open)

# A push button with the focus becomes the default if it is autoDefault.
focused = {}
for button in dlg.findChildren(QPushButton):
    button.setFocus()
    pump(0.05)
    focused[button.text()] = defaults()
out["defaults_with_focus"] = focused

# Enter where it has no Center to run: on Zoom + itself, in the Relation box,
# in the capacity boxes. Nothing may zoom, rebuild, centre or export.
elsewhere = {}
for name, widget in (("Zoom +", dlg.btn_zoom_in), ("Relation", dlg.txt_rel),
                     ("Cap min", dlg.cap_min), ("Cap max", dlg.cap_max)):
    widget.setFocus()
    pump(0.05)
    mark, rebuilt, before = len(CENTERS), len(REBUILDS), scale()
    key(Qt.Key.Key_Return)
    elsewhere[name] = {"focus": widget.hasFocus(), "zoom": round(scale() / before, 4),
                       "centers": CENTERS[mark:], "rebuilds": len(REBUILDS) - rebuilt}
out["elsewhere"] = elsewhere
out["said"] = SAID
out["errors"] = ERRORS
print("RESULT " + json.dumps(out), flush=True)
os._exit(0)
'''


@pytest.fixture(scope="module")
def enter_child(tmp_path_factory):
    """Enter pressed in the dialog as the toolbar opens it: ``(returncode, result, output)``."""
    folder = tmp_path_factory.mktemp("schematic_enter")
    script = folder / "schematic_enter.py"
    script.write_text(ENTER_DRIVER, encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(folder), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script), REPO_ROOT], cwd=str(folder),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT ")]
    result = json.loads(lines[-1][len("RESULT "):]) if lines else None
    return done.returncode, result, output


def _entered(state, name, output):
    """Center ran once, on ``name``: at its zoom, the element in the middle, ringed."""
    assert state["centers"] == [name], (
        f"Enter on {name!r} ran Center {len(state['centers'])} times ({state['centers']}); the "
        f"view went from scale {state['scale_before']} to {state['scale']}\n{output}")
    assert state["scale"] >= 1.0 - 1e-6, state
    assert state["ring"], state
    assert max(abs(v) for v in state["offset"]) <= 2, state


def test_enter_in_the_find_box_runs_center(enter_child):
    """It pressed Zoom +, the button QDialog made its default (QA, 3.40.15
    and 4.2.3): the view zoomed by 1.25 and centred nothing."""
    result, output = _seen(enter_child)
    assert result["focus_in_box"], result
    closed = result["closed"]
    assert not closed["list_was_open"], closed
    _entered(closed, "MH 1", output)


def test_enter_on_a_name_in_the_open_list_runs_center(enter_child):
    """Typed, the list of matching names opens. Enter on a name chosen in it
    with the arrow key, or on the name as typed, closed the list and did
    nothing else."""
    result, output = _seen(enter_child)
    chosen = result["chosen"]
    assert chosen["list_was_open"], chosen
    assert chosen["text"] == "MH 222", chosen
    _entered(chosen, "MH 222", output)
    typed = result["typed"]
    assert typed["list_was_open"], typed
    _entered(typed, "MH 1", output)
    for state in (chosen, typed):
        assert not state["list_open"], state


def test_no_button_is_the_default_so_enter_never_zooms(enter_child):
    """A push button in a QDialog is autoDefault, and with none set as the
    default QDialog took the first, Zoom +: Enter pressed it from any box,
    and pressed whichever push button had the focus."""
    result, output = _seen(enter_child)
    assert result["defaults_at_open"] == [], result["defaults_at_open"]
    assert all(found == [] for found in result["defaults_with_focus"].values()), (
        result["defaults_with_focus"])
    for name, state in result["elsewhere"].items():
        assert state["focus"], (name, state)
        assert state == {"focus": True, "zoom": 1.0, "centers": [], "rebuilds": 0}, (
            f"Enter in {name} did something: {state}")
    assert result["said"] == [], result["said"]
