"""The Optical schematic view's PNG, JPG and SVG exports show the whole drawing.

v1.6.0 QA finding Q22, the same on v1.5.0. Each export made an image the
drawing's size plus 40 px, translated the painter by the drawing's corner, and
then called ``scene.render(painter)`` with no target and no source -- which
maps the scene's own ``sceneRect()`` onto the whole image, on top of that
translation. That rect is everything the scene has held since the view opened,
the schematic layout and Center rings included, and it never shrinks. So, on
the QA project's elements and on a copy of the QA project itself:

- the schematic layout, as the view opens, began 999 px down an image 1,045 to
  1,054 px high: 4.4-5.2% of the drawing was in it, 2 of its 18 or 19 elements;
- under Match map styling the drawing came out at 0.36-0.37 of its size in the
  image's lower left, and on the QA project its bottom tenth was cut off;
- a Center at the drawing's edge widened that rect for every later export, and
  an export taken while the ring showed had the ring in it.

Measured on 3.22.16, 3.40.15 and 4.2.3. Each export now draws the drawing's own
rect, without the ring, onto all of an image of the same size: the drawing at
one pixel a scene unit, the margin even, whatever the view shows. A file that
cannot be written is reported; it used to fail without a word.

The tests look at what was written: where the drawing's pixels are in each
image -- against the same scene drawn whole, at one pixel a unit, on a larger
canvas -- the SVG's size and viewBox, and the bytes of the files before and
after the user zooms, pans, centres, fits or resizes. The driver runs in a
child process, which answers the file dialog and records any message box: an
exception escaping a Qt slot kills the interpreter (exit 139, measured), and a
real message box would wait for a click that never comes.
"""
import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for the child. The suite has no timeout plugin.
TIMEOUT_S = 120

KINDS = ("png", "jpg", "svg")

DRIVER = r'''
import hashlib, json, os, re, sys, time
sys.path.insert(0, sys.argv[1])
os.environ["FIBERQ_LOG_FILE"] = "false"
from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)
QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()
from qgis.PyQt.QtCore import QBuffer, QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt
from qgis.PyQt.QtGui import QImage, QMouseEvent, QPainter
from qgis.PyQt.QtSvg import QSvgGenerator, QSvgRenderer
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QMessageBox

#: Anything escaping a slot lands here instead of killing the interpreter.
ERRORS = []
sys.excepthook = lambda kind, value, tb: ERRORS.append("%s: %s" % (kind.__name__, value))

#: Every message box the dialog opens: [kind, title, text].
SAID = []
for _kind in ("critical", "warning", "information", "question"):
    setattr(QMessageBox, _kind, staticmethod(
        lambda *a, _k=_kind, **kw: SAID.append([_k] + [str(v) for v in a[1:3]])
        or QMessageBox.StandardButton.Ok))

from fiberq.core.data_manager import DataManager
from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog


def pump(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        APP.processEvents()
        time.sleep(0.005)


# The QA project's elements, as tests/test_schematic_center.py lays them out:
# their names, layers and cable ends, metres east and north of the middle of
# its map, stretched x3.2.
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

#: A table for bytes.translate: 1 for a channel darker than 200, else 0. On
#: white, JPEG's ringing round a line stays lighter than that.
DARK = bytes(1 if v < 200 else 0 for v in range(256))


def drawn_box(img, on_white):
    """[left, top, right, bottom) of the pixels drawn on, or None.

    On a transparent image, a pixel is drawn on when its alpha is not 0; on
    white, when any of its colours is darker than 200.
    """
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    raw = img.constBits().asstring(img.sizeInBytes())
    box = None
    for y in range(h):
        row = raw[y * bpl:y * bpl + 4 * w]
        marks = row.translate(DARK) if on_white else row[3::4]
        step = 4 if on_white else 1
        rest = marks.lstrip(b"\0")
        if not rest:
            continue
        left = (len(marks) - len(rest)) // step
        right = (len(marks.rstrip(b"\0")) - 1) // step + 1
        box = ([left, y, right, y + 1] if box is None else
               [min(box[0], left), box[1], max(box[2], right), y + 1])
    return box


def drawing(dlg):
    """Everything the scene holds but the Center ring, in scene units."""
    ring = getattr(dlg, "_highlight", None)
    rect = QRectF()
    for item in dlg.scene.items():
        if item is not ring:
            rect = rect.united(item.sceneBoundingRect())
    return rect


def svg_image(data, width, height):
    """An SVG drawn onto a transparent image of the given size."""
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    QSvgRenderer(data).render(painter, QRectF(0, 0, width, height))
    painter.end()
    return img


def drawn_whole(dlg, kind):
    """The box of what the scene draws, in scene units: the scene drawn as
    ``kind`` at one pixel a unit, on a canvas that leaves 50 px round the
    drawing. An SVG states its labels' size in its own way (QSvgGenerator
    writes 9 for a 9 pt label, which the scene draws 12 px high), so the
    SVG's drawing is measured off an SVG."""
    rect = drawing(dlg).adjusted(-50, -50, 50, 50)
    width, height = int(rect.width()), int(rect.height())
    source = QRectF(rect.left(), rect.top(), width, height)
    if kind == "svg":
        svg = QBuffer()
        generator = QSvgGenerator()
        generator.setOutputDevice(svg)
        generator.setSize(QSize(width, height))
        generator.setViewBox(QRect(0, 0, width, height))
        painter = QPainter(generator)
        dlg.scene.render(painter, QRectF(0, 0, width, height), source)
        painter.end()
        canvas = svg_image(bytes(svg.data()), width, height)
    else:
        canvas = QImage(width, height, QImage.Format.Format_ARGB32)
        canvas.fill(0xffffffff if kind == "jpg" else 0)
        painter = QPainter(canvas)
        dlg.scene.render(painter, QRectF(0, 0, width, height), source)
        painter.end()
    box = drawn_box(canvas, kind == "jpg")
    return [rect.left() + box[0], rect.top() + box[1], rect.left() + box[2], rect.top() + box[3]]


def export(kind, path=None):
    """Press PNG, JPG or SVG and answer the file dialog: the file's bytes, or None."""
    path = path or os.path.join(os.getcwd(), "schematic-%d.%s" % (len(WRITTEN), kind))
    WRITTEN.append(path)
    QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: (path, ""))
    getattr(dlg, "_export_" + kind)()
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


WRITTEN = []


def image_of(kind, data):
    """The export as an image; an SVG drawn onto its viewBox, with its header."""
    if kind != "svg":
        img = QImage()
        img.loadFromData(data)
        return img, None
    text = data.decode("utf-8")
    header = re.search(r"<svg[^>]*>", text).group(0)
    found = {name: re.search(r'\b%s="([^"]+)"' % name, header) for name in ("width", "height", "viewBox")}
    head = {name: (m.group(1) if m else None) for name, m in found.items()}
    box = [float(v) for v in head["viewBox"].split()]
    return svg_image(data, int(box[2]), int(box[3])), head


def look(kind):
    """Where the export put the drawing, against where the whole of it goes."""
    data = export(kind)
    if data is None:
        return None
    img, head = image_of(kind, data)
    rect = drawing(dlg)
    whole = drawn_whole(dlg, kind)
    # Centred in an image of the drawing's size plus 40 px, at one pixel a unit.
    left = rect.center().x() - img.width() / 2.0
    top = rect.center().y() - img.height() / 2.0
    corner = img.pixelColor(0, 0)
    return {"size": [img.width(), img.height()], "drawing": [rect.width(), rect.height()],
            "seen": drawn_box(img, kind == "jpg"),
            "whole": [round(whole[0] - left, 2), round(whole[1] - top, 2),
                      round(whole[2] - left, 2), round(whole[3] - top, 2)],
            "corner": [corner.red(), corner.green(), corner.blue(), corner.alpha()],
            "svg": head}


def digests():
    return {kind: hashlib.sha256(export(kind) or b"").hexdigest() for kind in ("png", "jpg", "svg")}


def press_center(name):
    dlg.txt_search.setText(name)
    dlg.btn_center.click()


def click(button, seconds=0.2):
    button.click()
    pump(seconds)


def drag(widget, points):
    """A left-button drag through points, as a pan is. The moves are sent as
    events: on Qt 5 QTest.mouseMove only moves the cursor (5.15.3, 5.15.13)."""
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, points[0])
    for point in points[1:]:
        QApplication.sendEvent(widget, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(point), Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, points[-1])


out = {}
dlg = OpticalSchematicDialog(core)
dlg.show()
dlg.raise_()
dlg.activateWindow()
pump(0.3)
for layout in ("schematic", "map"):
    if layout == "map":
        dlg.chk_map_layout.setChecked(True)
        click(dlg.btn_apply, 0.3)
    pos = dlg._last_positions
    middle = drawing(dlg).center()
    inner = min(pos, key=lambda n: ((pos[n][0] - middle.x()) ** 2 + (pos[n][1] - middle.y()) ** 2, n))
    # The schematic layout's top row, the map's right edge: rings that reach
    # past the drawing.
    if layout == "schematic":
        edge = min(pos, key=lambda n: (pos[n][1], n))
    else:
        edge = max(pos, key=lambda n: (pos[n][0], n))
    state = {"look": {kind: look(kind) for kind in ("png", "jpg", "svg")}, "first": digests(),
             "inner": inner, "edge": edge}
    after = {}
    scale = dlg.view.transform().m11()
    for _ in range(3):
        click(dlg.btn_zoom_in, 0.05)
    after["zoom"] = digests()
    bars = (dlg.view.horizontalScrollBar(), dlg.view.verticalScrollBar())
    scrolled = [bar.value() for bar in bars]
    drag(dlg.view.viewport(), [QPoint(300, 300), QPoint(360, 340), QPoint(420, 380)])
    pump(0.1)
    after["pan"] = digests()
    state["moved"] = {"zoom": round(dlg.view.transform().m11() / scale, 3),
                      "pan": [bar.value() for bar in bars] != scrolled}
    press_center(inner)
    pump(1.8)
    after["center"] = digests()
    # Taken while the ring shows: Center again before each.
    ring, showing = {}, []
    for kind in ("png", "jpg", "svg"):
        press_center(edge)
        pump(0.05)
        showing.append(getattr(dlg, "_highlight", None) is not None)
        ring[kind] = hashlib.sha256(export(kind) or b"").hexdigest()
    state["ring"], state["ring_showing"] = ring, showing
    pump(1.8)
    after["after_edge_center"] = digests()
    click(dlg.btn_fit)
    after["fit"] = digests()
    size = dlg.size()
    dlg.resize(1500, 900)
    pump(0.3)
    after["resize"] = digests()
    dlg.resize(size)
    pump(0.3)
    state["after"] = after
    out[layout] = state

# A file that cannot be written, and an export the user cancels.
missing = os.path.join(os.getcwd(), "no such folder")
failed = {}
for kind in ("png", "jpg", "svg"):
    mark = len(SAID)
    path = os.path.join(missing, "schematic." + kind)
    export(kind, path)
    failed[kind] = {"path": path, "said": SAID[mark:], "written": os.path.exists(path)}
out["failed"] = failed
cancelled = {}
for kind in ("png", "jpg", "svg"):
    mark = len(SAID)
    QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: ("", ""))
    before = sorted(os.listdir(os.getcwd()))
    getattr(dlg, "_export_" + kind)()
    cancelled[kind] = {"said": SAID[mark:], "new_files": sorted(set(os.listdir(os.getcwd())) - set(before))}
out["cancelled"] = cancelled
out["errors"] = ERRORS
print("RESULT " + json.dumps(out), flush=True)
os._exit(0)
'''


@pytest.fixture(scope="module")
def export_child(tmp_path_factory):
    """The dialog opened as the toolbar opens it, and its exports: ``(returncode, result, output)``."""
    folder = tmp_path_factory.mktemp("schematic_export")
    script = folder / "schematic_export.py"
    script.write_text(DRIVER, encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(folder), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script), REPO_ROOT], cwd=str(folder),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT ")]
    result = json.loads(lines[-1][len("RESULT "):]) if lines else None
    return done.returncode, result, output


def _seen(export_child):
    code, result, output = export_child
    assert code == 0, f"returncode {code} (-11/139 is SIGSEGV)\n{output}"
    assert result is not None, output
    assert result["errors"] == [], output
    return result, output


#: How far, in pixels, the drawn pixels may sit from where the whole drawing
#: goes. The two drawings start half a pixel apart at most; JPEG blurs a line's
#: edge by a pixel or two, and the SVG renderer smooths it.
SLACK = {"png": 1.5, "jpg": 3.0, "svg": 2.0}


def test_each_export_shows_the_whole_drawing_at_one_pixel_a_unit(export_child):
    """In both layouts, as the view opens: the image is the drawing's size plus
    20 px each side, as it always was, and the drawing fills it, centred. The
    PNG is transparent round it, the JPG white, and the SVG's size and viewBox
    are the PNG's."""
    result, output = _seen(export_child)
    for layout in ("schematic", "map"):
        looks = result[layout]["look"]
        for kind in KINDS:
            seen = looks[kind]
            assert seen is not None, f"{layout}: no {kind} was written\n{output}"
            width, height = seen["size"]
            assert [width, height] == [int(seen["drawing"][0]) + 40, int(seen["drawing"][1]) + 40], (
                f"{layout} {kind}: {width} x {height} for a drawing of {seen['drawing']}")
            assert seen["seen"] == pytest.approx(seen["whole"], abs=SLACK[kind]), (
                f"{layout} {kind}: the drawing's pixels are at {seen['seen']} in the {width} x {height} "
                f"image, where the whole drawing at one pixel a unit goes at {seen['whole']}")
        assert looks["png"]["corner"][3] == 0, looks["png"]["corner"]
        assert min(looks["jpg"]["corner"][:3]) >= 250, looks["jpg"]["corner"]
        svg = looks["svg"]["svg"]
        width, height = looks["png"]["size"]
        assert [float(v) for v in svg["viewBox"].split()] == [0, 0, width, height], (layout, svg)
        # QSvgGenerator writes the size in millimetres, at 72 dots an inch.
        for key, pixels in (("width", width), ("height", height)):
            assert svg[key].endswith("mm"), (layout, svg)
            assert float(svg[key][:-2]) * 72 / 25.4 == pytest.approx(pixels, abs=0.01), (layout, svg)


def test_an_export_does_not_depend_on_the_view(export_child):
    """Zoom, pan, Center, Fit or a resized window leave every export as it was.
    A Center at the drawing's edge used to widen the rect every later export
    drew."""
    result, output = _seen(export_child)
    for layout in ("schematic", "map"):
        state = result[layout]
        # The view did change: zoomed in three times, then panned.
        assert state["moved"]["zoom"] > 1.9 and state["moved"]["pan"], (layout, state["moved"])
        changed = {step: [kind for kind in KINDS if digests[kind] != state["first"][kind]]
                   for step, digests in state["after"].items()}
        changed = {step: kinds for step, kinds in changed.items() if kinds}
        assert not changed, (
            f"{layout}: these exports changed after the view did (Center on {state['inner']!r} "
            f"inside the drawing, then on {state['edge']!r} at its edge): {changed}")


def test_an_export_taken_while_the_ring_shows_leaves_it_out(export_child):
    """The Center ring points at an element in the view; it is no part of the
    drawing, and an export taken in its 1.5 s had it in it, 4 px taller."""
    result, output = _seen(export_child)
    for layout in ("schematic", "map"):
        state = result[layout]
        assert all(state["ring_showing"]), state["ring_showing"]
        kept = [kind for kind in KINDS if state["ring"][kind] != state["first"][kind]]
        assert not kept, (
            f"{layout}: the {kept} export taken while the ring round {state['edge']!r} showed "
            "is not the one taken without it")


def test_a_file_that_cannot_be_written_is_reported(export_child):
    """A folder that is not there: each export said nothing and wrote nothing.
    One message now names the file; a cancelled export still says nothing."""
    result, output = _seen(export_child)
    for kind in KINDS:
        failed = result["failed"][kind]
        assert not failed["written"], failed
        assert len(failed["said"]) == 1, (
            f"saving the {kind} into a folder that is not there showed {failed['said']}")
        assert failed["said"][0][0] in ("critical", "warning"), failed["said"]
        assert failed["path"] in failed["said"][0][2], failed["said"]
        cancelled = result["cancelled"][kind]
        assert cancelled == {"said": [], "new_files": []}, cancelled
