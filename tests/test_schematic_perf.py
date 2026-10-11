"""The Optical schematic view's work grows with the project, not its square, and moves nothing.

WP4 task 4.1, item PF-1. On v1.5.0 the view took 23.8 s to open at size S
(QGIS 3.44.15, benchmark median), 137 s at M and 1,045 s at L. Measured at S:

* ``_collect_edges`` found each cable and pipe by reading its whole layer until
  the fid came up: 2,156,690 features read to find 3,919, ~73% of the open.
  The "Match map styling" layout did the same for every node: 1,471,859
  features read to place 3,304.
* every label was compared with every label already placed: 17,229,707
  ``QRectF.intersects`` calls for 5,345 labels, ~16% of the open. Placed
  labels now go into a uniform grid, and a label is compared only with those
  in the cells it covers, stopping at the first overlap.

The fix must not move a single item. Label positions follow the platform's
font metrics, which differ between the QGIS images, so the golden result is
not a file: it is v1.5.0's own drawing code, replayed in the same process on
the same layout and compared item by item.

**Counted, not timed.** Features read and rectangles compared are
deterministic, and a busy runner cannot fail a count. The plan's XS-vs-XS4
ratio test is kept, over counts: XS4 has 4.07x the features of XS, so work that
grows with the square of the project grows ~16x between them and linear work
~4x.

The dataset work runs in one child process. The driver patches QGIS classes
for counting, reads two projects into ``QgsProject.instance()`` and leaves views
wired to its signals, none of which may leak into later tests; and an exception
escaping a Qt slot kills the interpreter (exit 139, measured on 3.22 through
4.2), so a failure there has to cost one test, not the run.
"""
import json
import os
import subprocess
import sys

import pytest
from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for the child. The suite has no timeout plugin.
TIMEOUT_S = 300

CITY_DRIVER = '''
import json, os, sys
sys.path.insert(0, {repo!r})
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FIBERQ_LOG_FILE"] = "false"
from qgis.core import QgsApplication, QgsProject, QgsSpatialIndex, QgsVectorLayer
app = QgsApplication([], True)
app.initQgis()
from qgis.PyQt.QtCore import Qt, QRectF
from qgis.PyQt.QtGui import QColor, QFont, QPainterPath, QPen
from qgis.PyQt.QtWidgets import QGraphicsScene, QGraphicsTextItem
from fiberq.core.data_manager import DataManager
from fiberq.dialogs import schematic_dialog
from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

data = DataManager()
core = type("Core", (), {{}})()
core.iface = type("Iface", (), {{"mainWindow": lambda self: None}})()
core.list_all_cables = data.list_all_cables
core.list_all_pipes = data.list_all_pipes

counts = {{"getFeatures": 0, "features": 0, "intersects": 0, "handed": 0}}
# The class-dict descriptors, so they can be put back: a sip method read through
# the class no longer binds self once replaced (measured TypeError).
_get_descriptor = vars(QgsVectorLayer)["getFeatures"]
_hit_descriptor = vars(QRectF)["intersects"]
_query_descriptor = vars(QgsSpatialIndex)["intersects"]
_get, _hit, _query = QgsVectorLayer.getFeatures, QRectF.intersects, QgsSpatialIndex.intersects


def counting_get(self, *args):
    counts["getFeatures"] += 1
    for feature in _get(self, *args):
        counts["features"] += 1
        yield feature


def counting_hit(self, other):
    counts["intersects"] += 1
    return _hit(self, other)


def counting_query(self, *args):
    # what a spatial index hands back, whether or not anything then tests it
    answer = _query(self, *args)
    counts["handed"] += len(answer)
    return answer


def counted(work):
    counts.update(getFeatures=0, features=0, intersects=0, handed=0)
    QgsVectorLayer.getFeatures, QRectF.intersects = counting_get, counting_hit
    QgsSpatialIndex.intersects = counting_query
    try:
        work()
    finally:
        QgsVectorLayer.getFeatures, QRectF.intersects = _get_descriptor, _hit_descriptor
        QgsSpatialIndex.intersects = _query_descriptor
    return dict(counts)


def retire(dlg):
    # What tools/bench does with a used view: nothing a later project change
    # does may reach it.
    dlg._schedule_rebuild = lambda *a: None
    dlg.deleteLater()


def scan_by_id(pairs):
    """v1.5.0's lookup: read the layer from the top until the fid comes up."""
    found = {{}}
    for layer_id, fid in pairs:
        lyr = QgsProject.instance().mapLayer(layer_id)
        if not isinstance(lyr, QgsVectorLayer):
            continue
        for f in lyr.getFeatures():
            if int(f.id()) == int(fid):
                found.setdefault(layer_id, {{}})[int(fid)] = f
                break
    return found


def v150_drawing(dlg, nodes, pos, lines):
    """v1.5.0's rebuild() from the colours on, verbatim but for its own scene."""
    scene = QGraphicsScene()

    def color_for(e):
        t = (e.get('podtip') or '').lower()
        lname = (e.get('layer_name') or '').lower()
        if 'glavni' in t:
            return QColor(0, 51, 153)
        if 'distribut' in t:
            return QColor(204, 0, 0)
        if 'razvod' in t:
            return QColor(165, 42, 42)
        if e.get('is_pipe') or 'cev' in t or 'cevi' in lname:
            return QColor(255, 140, 0)
        return QColor(60, 60, 60)

    occupied = []

    def place_text(x, y, txt, color):
        if not txt:
            return
        ti = scene.addText(txt, QFont("Arial", 9))
        ti.setDefaultTextColor(color)
        offsets = [(8, -8), (10, 10), (-22, -10), (-22, 12), (8, 12), (12, 0)]
        for dx, dy in offsets:
            ti.setPos(x + dx, y + dy)
            rect = ti.mapRectToScene(ti.boundingRect())
            if not any(rect.intersects(r) for r in occupied):
                bg = rect.adjusted(-2, -1, 2, 2)
                scene.addRect(bg, QPen(Qt.PenStyle.NoPen), QColor(255, 255, 255, 210)).setZValue(ti.zValue() - 1)
                occupied.append(bg)
                return
        occupied.append(ti.mapRectToScene(ti.boundingRect()))

    for e, path in lines:
        pen = QPen(color_for(e))
        pen.setWidthF(2.2)
        if e.get('is_pipe'):
            pen.setStyle(Qt.PenStyle.DashLine)
        gp = QPainterPath()
        x0, y0 = path[0]
        gp.moveTo(x0, y0)
        for x, y in path[1:]:
            gp.lineTo(x, y)
        scene.addPath(gp, pen)
        if dlg.chk_labels.isChecked():
            mx, my = path[len(path) // 2]
            text = f"{{e.get('kapacitet', '')}}".strip()
            if e.get('length', 0.0):
                text = (text + (" / " if text else "")) + f"{{round(e['length'], 1)}} m"
            place_text(mx, my, text, pen.color())
    for name, meta in nodes.items():
        x, y = pos.get(name, (0.0, 0.0))
        r = 6.0
        scene.addEllipse(x - r, y - r, 2 * r, 2 * r, QPen(Qt.GlobalColor.black), QColor(240, 240, 240))
        if dlg.chk_labels.isChecked():
            place_text(x, y, str(name), QColor(10, 10, 10))
    return scene


def items(scene):
    out = []
    for it in scene.items(Qt.SortOrder.AscendingOrder):
        r = it.sceneBoundingRect()
        text = it.toPlainText() if isinstance(it, QGraphicsTextItem) else None
        out.append([type(it).__name__, it.zValue(), it.pos().x(), it.pos().y(),
                    r.x(), r.y(), r.width(), r.height(), text])
    return out


result = {{}}
for size, qgz in (("xs", {xs!r}), ("xs4", {xs4!r})):
    QgsProject.instance().clear()
    assert QgsProject.instance().read(qgz)
    run = result[size] = {{}}
    box = []
    run["build"] = counted(lambda: box.append(OpticalSchematicDialog(core)))
    dlg = box[0]
    run["labels"] = sum(1 for it in dlg.scene.items() if isinstance(it, QGraphicsTextItem))
    dlg.chk_map_layout.setChecked(True)
    run["map_build"] = counted(dlg.rebuild)
    run["map_labels"] = sum(1 for it in dlg.scene.items() if isinstance(it, QGraphicsTextItem))
    dlg.chk_map_layout.setChecked(False)
    if size == "xs":
        edges = []
        run["edges"] = counted(lambda: edges.extend(dlg._collect_edges()))
        run["edge_count"] = len(edges)
        run["edge_layers"] = len({{e["layer_name"] for e in edges}})
        nodes = dlg._collect_nodes()
        run["nodes"] = len(nodes)
        run["node_layers"] = len({{n["layer_id"] for n in nodes.values()}})
        dlg.chk_map_layout.setChecked(True)
        positions = []
        run["map_layout"] = counted(lambda: positions.append(dlg._build_layout(nodes, edges)[0]))
        pos = positions[0]
        run["positions"] = len(pos)

        # The same work through v1.5.0's scans: same edges, same positions, in order.
        batched = getattr(schematic_dialog, "features_by_id", None)
        if batched is not None:
            schematic_dialog.features_by_id = scan_by_id
            try:
                scanned_edges = dlg._collect_edges()
                scanned_pos = dlg._build_layout(nodes, scanned_edges)[0]
            finally:
                schematic_dialog.features_by_id = batched
            run["edges_as_scanned"] = scanned_edges == edges
            run["positions_as_scanned"] = list(scanned_pos.items()) == list(pos.items())
        else:
            # v1.5.0 has no seam to swap: its lookups ARE the scans.
            run["edges_as_scanned"] = run["positions_as_scanned"] = True
        dlg.chk_map_layout.setChecked(False)

        # And in the order the cables and pipes were listed: each one alone,
        # concatenated, is the whole. A batch that walked its layers instead
        # would move every label after the first layer change.
        listed = core.list_all_cables() + core.list_all_pipes()
        one_by_one = []
        for item in listed:
            dlg.core = type("One", (), {{"list_all_cables": lambda self, item=item: [item],
                                         "list_all_pipes": lambda self: []}})()
            one_by_one.extend(dlg._collect_edges())
        dlg.core = core
        run["edges_in_listed_order"] = one_by_one == edges

        # Every scene item where v1.5.0's drawing code puts it, both layouts.
        for layout in ("schematic", "map"):
            dlg.chk_map_layout.setChecked(layout == "map")
            dlg.rebuild()
            nodes = dlg._collect_nodes()
            pos, lines = dlg._build_layout(nodes, dlg._collect_edges())
            expected = items(v150_drawing(dlg, nodes, pos, lines))
            got = items(dlg.scene)
            run[layout] = {{"items": len(got), "same": got == expected,
                           "first_difference": next(([a, b] for a, b in zip(got, expected) if a != b), None)}}
        dlg.chk_map_layout.setChecked(False)
    retire(dlg)
print("RESULT " + json.dumps(result), flush=True)
os._exit(0)
'''


@pytest.fixture(scope="module")
def city(city_xs_dataset, city_xs4_dataset, tmp_path_factory):
    """One child process: the view built on XS and on XS4, with its work counted."""
    folder = tmp_path_factory.mktemp("schematic_perf")
    script = folder / "city.py"
    script.write_text(CITY_DRIVER.format(repo=REPO_ROOT, xs=city_xs_dataset["qgz"],
                                         xs4=city_xs4_dataset["qgz"]), encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], cwd=str(folder), timeout=TIMEOUT_S,
                          env=dict(os.environ, QT_QPA_PLATFORM="offscreen", FIBERQ_LOG_FILE="false"),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [line for line in output.splitlines() if line.startswith("RESULT ")]
    assert done.returncode == 0 and lines, f"returncode {done.returncode}\n{output[-4000:]}"
    return json.loads(lines[-1][len("RESULT "):])


# ---------------------------------------------------------------------------
# Reads: one per layer
# ---------------------------------------------------------------------------

def test_cables_and_pipes_are_read_once_per_layer(city):
    """v1.5.0: one getFeatures() per cable and pipe -- 540 calls and 42,173
    features read at XS. Listing them reads each layer once; the lookup once more."""
    xs = city["xs"]
    assert xs["edges"]["getFeatures"] <= 2 * xs["edge_layers"], xs["edges"]
    assert xs["edges"]["features"] <= 2 * xs["edge_count"], xs["edges"]


def test_map_styling_places_nodes_with_one_read_per_layer(city):
    """v1.5.0: one getFeatures() per node -- 465 calls and 28,802 features at XS."""
    xs = city["xs"]
    assert xs["positions"] > 400
    assert xs["map_layout"]["getFeatures"] <= xs["node_layers"], xs["map_layout"]
    assert xs["map_layout"]["features"] <= xs["nodes"], xs["map_layout"]


def test_the_reads_find_what_the_scans_found(city):
    """The same edges and the same node positions as v1.5.0's per-item scans, in order."""
    xs = city["xs"]
    assert xs["edge_count"] > 400
    assert xs["edges_as_scanned"]
    assert xs["positions_as_scanned"]


def test_the_edges_keep_the_order_the_cables_were_listed_in(city):
    """Label placement follows edge order, so an edge moved is a label moved.

    Walking the batch's layers instead of the listed items moved 117 labels in
    the Match-map-styling layout at XS (measured on 3.44.15), and no count
    above can see it.
    """
    assert city["xs"]["edges_in_listed_order"]


# ---------------------------------------------------------------------------
# Labels: compared with the few placed near them
# ---------------------------------------------------------------------------

def test_labels_are_not_compared_with_every_placed_label(city):
    """v1.5.0 at XS: 324,613 intersects() calls for 740 labels (439 each), and in
    "Match map styling" 705,936 for 1,001 (705 each).

    The grid makes 1.7 per label in the default layout and 13 in the map
    layout, where labels crowd a fixed 1600 x 1000 scene (3.44.15 and 4.2.3,
    measured), so 20 and 40 per label are wide margins that v1.5.0's scan
    still misses by more than ten times.
    """
    xs = city["xs"]
    assert xs["labels"] > 500 and xs["map_labels"] > 500
    assert xs["build"]["intersects"] < 20 * xs["labels"], xs["build"]
    assert xs["map_build"]["intersects"] < 40 * xs["map_labels"], xs["map_build"]


def test_every_item_lands_where_v150_put_it(city):
    """Both layouts on the XS city, item by item: type, z, position, box and text."""
    for layout in ("schematic", "map"):
        run = city["xs"][layout]
        assert run["items"] > 1000, run
        assert run["same"], (layout, run["first_difference"])


def _bare_view():
    """The real rebuild() on a view with no project behind it.

    ``OpticalSchematicDialog.__init__`` wires itself to the project and builds
    from it; these tests hand rebuild() their own nodes instead, so the labels
    land exactly where the test puts them.
    """
    from qgis.PyQt.QtWidgets import QCheckBox, QGraphicsScene, QGraphicsView

    from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

    view = OpticalSchematicDialog.__new__(OpticalSchematicDialog)
    view.scene = QGraphicsScene()
    view.view = QGraphicsView(view.scene)
    view._highlight = None
    view.chk_labels = QCheckBox()
    view.chk_labels.setChecked(True)
    view._collect_edges = lambda: []
    return view


def _draw(view, positions):
    """rebuild() with these named nodes at these positions, and no cables."""
    nodes = {name: {"layer_name": ""} for name in positions}
    view._collect_nodes = lambda: nodes
    view._build_layout = lambda nodes, edges: (dict(positions), [])
    view.rebuild()
    labels = {item.toPlainText(): item for item in view.scene.items()
              if isinstance(item, QGraphicsTextItem)}
    backgrounds = [item.rect() for item in view.scene.items(Qt.SortOrder.AscendingOrder)
                   if isinstance(item, QGraphicsRectItem)]
    return labels, backgrounds


def test_a_label_that_only_touches_a_placed_one_still_fits(qgis_app):
    """``QRectF.intersects`` is strict: boxes that only share an edge do not overlap.

    So v1.5.0 placed a label whose first spot only touched a placed label's
    background, and so must the grid: the touching rect shares a cell, the
    grid offers it, and the unchanged exact test lets the label through.
    Deciding on the grid's offer alone would push the label to another spot.
    The city data has no touching labels (measured at XS and S), so this is
    the one test that sees the case, and it runs the real rebuild().
    """
    view = _bare_view()
    _labels, backgrounds = _draw(view, {"MH 1": (0.0, 0.0)})
    first = backgrounds[0]
    # place_text tries (8, -8) first: put the second label's first rect so its
    # left edge IS the first background's right edge, at the same height.
    x = first.right() - 8
    labels, backgrounds = _draw(view, {"MH 1": (0.0, 0.0), "MH 2": (x, 0.0)})
    second = labels["MH 2"].mapRectToScene(labels["MH 2"].boundingRect())
    assert second.left() == first.right(), "premise: the two rects share an edge"
    assert (labels["MH 2"].pos().x(), labels["MH 2"].pos().y()) == (x + 8, -8.0)
    assert len(backgrounds) == 2, "both labels were placed"


def test_a_scene_box_is_in_order_whatever_the_rect_says(qgis_app):
    """A negative width or height comes back ordered -- on 3.22 too, where
    ``QgsRectangle`` leaves a near-zero box un-normalised (measured)."""
    from fiberq.dialogs.schematic_dialog import _scene_box

    for rect in (QRectF(1e-16, 0, -2e-16, 1e-16), QRectF(0, 1e-16, 1e-16, -2e-16),
                 QRectF(10, 10, -5, -3)):
        box = _scene_box(rect)
        assert box.xMinimum() <= box.xMaximum() and box.yMinimum() <= box.yMaximum(), rect


def test_an_overlap_of_one_ulp_is_still_found(qgis_app):
    """The box a placed label is gridded by is its exact rect, not one ulp less.

    Placed so the overlap is the last ulp before a cell boundary: a box
    shrunk by one ulp would sit in the next cell over, out of the query's.
    """
    from fiberq.dialogs.schematic_dialog import _LABEL_CELL, _scene_box
    from fiberq.utils.spatial import RectGrid

    placed = QRectF(0, 0, _LABEL_CELL, 10)
    occupied = RectGrid(_LABEL_CELL)
    occupied.add(placed, _scene_box(placed))
    overlapping = QRectF(63.99999999999999, 0, 5, 5)        # the double below 64
    assert overlapping.intersects(placed)
    assert occupied.any_passes(_scene_box(overlapping), overlapping.intersects)


# ---------------------------------------------------------------------------
# XS against XS4: linear, not quadratic
# ---------------------------------------------------------------------------

def test_the_work_grows_with_the_project_not_its_square(city):
    """XS to XS4 is x4.07 the features.

    v1.5.0: features read x15.7 per default build (43,007 -> 676,311) and
    x15.9 per map build; intersects x16.4 per default build (324,613 ->
    5,339,531). The grid: x4.0, and x5.1 for the map build (3.44.15).

    The map build's work counts the rects a spatial index hands back as well
    as those tested: the first cut's QgsSpatialIndex handed back each label's
    whole pile in that crowded fixed scene -- 26,214 rects at XS, 427,488 at
    XS4 -- while its tests stayed few. v1.5.0's scan passes this ratio (x7.4,
    705,936 -> 5,250,850: it stopped at the first overlap in the crowd); the
    per-label bound above is what catches the scan.
    """
    for build, work in (("build", "features"), ("map_build", "features"), ("build", "intersects")):
        small, large = city["xs"][build][work], city["xs4"][build][work]
        assert small > 0, (build, work)
        assert large / small < 8, (build, work, small, large)
    small, large = [city[size]["map_build"]["intersects"] + city[size]["map_build"]["handed"]
                    for size in ("xs", "xs4")]
    assert large / small < 8, ("map_build", "intersects + handed", small, large)
