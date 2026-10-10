"""The Optical schematic view does linear work and moves nothing.

WP4 task 4.1, item PF-1. On v1.5.0 the view took 23.8 s to open at size S
(QGIS 3.44.15, benchmark median), 137 s at M and 1,045 s at L. Measured at S:

* ``_collect_edges`` found each cable and pipe by reading its whole layer until
  the fid came up: 2,156,690 features read to find 3,919, ~73% of the open.
  The "Match map styling" layout did the same for every node: 1,471,859
  features read to place 3,304.

The fix must not move a single item, so besides counting the work these tests
compare the result with what v1.5.0's per-item scans produce, in the same
process on the same data.

**Counted, not timed.** Features read are deterministic, and a busy runner
cannot fail a count. The plan's XS-vs-XS4 ratio test is kept, over counts:
XS4 has 4.07x the features of XS, so work that grows with the square of the
project grows ~16x between them and linear work ~4x.

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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for the child. The suite has no timeout plugin.
TIMEOUT_S = 300

CITY_DRIVER = '''
import json, os, sys
sys.path.insert(0, {repo!r})
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FIBERQ_LOG_FILE"] = "false"
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer
app = QgsApplication([], True)
app.initQgis()
from fiberq.core.data_manager import DataManager
from fiberq.dialogs import schematic_dialog
from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

data = DataManager()
core = type("Core", (), {{}})()
core.iface = type("Iface", (), {{"mainWindow": lambda self: None}})()
core.list_all_cables = data.list_all_cables
core.list_all_pipes = data.list_all_pipes

counts = {{"getFeatures": 0, "features": 0}}
# The class-dict descriptor, so it can be put back: QgsVectorLayer.getFeatures
# read through the class no longer binds self once replaced (measured TypeError).
_get_descriptor = vars(QgsVectorLayer)["getFeatures"]
_get = QgsVectorLayer.getFeatures


def counting_get(self, *args):
    counts["getFeatures"] += 1
    for feature in _get(self, *args):
        counts["features"] += 1
        yield feature


def counted(work):
    counts.update(getFeatures=0, features=0)
    QgsVectorLayer.getFeatures = counting_get
    try:
        work()
    finally:
        QgsVectorLayer.getFeatures = _get_descriptor
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


result = {{}}
for size, qgz in (("xs", {xs!r}), ("xs4", {xs4!r})):
    QgsProject.instance().clear()
    assert QgsProject.instance().read(qgz)
    run = result[size] = {{}}
    box = []
    run["build"] = counted(lambda: box.append(OpticalSchematicDialog(core)))
    dlg = box[0]
    dlg.chk_map_layout.setChecked(True)
    run["map_build"] = counted(dlg.rebuild)
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


def test_the_features_read_grow_with_the_project_not_its_square(city):
    """XS to XS4 (x4.07 the features). v1.5.0: x15.7 (43,007 -> 676,311) for a
    build, the map layout too. Linear reads stay well under 8."""
    for build in ("build", "map_build"):
        small, large = city["xs"][build]["features"], city["xs4"][build]["features"]
        assert small > 0
        assert large / small < 8, (build, small, large)
