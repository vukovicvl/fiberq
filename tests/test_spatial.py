"""utils.spatial hands each exact test the same things the scan did, in its order.

WP4 task 4.1 (PF-1, PF-2, PF-3). ``ScanOrderIndex`` is only a speed-up if the
caller's exact test, run over ``candidates()``, gives the answer it gave over
the whole scan. That holds when ``candidates()`` returns

* everything the exact test could accept -- a superset -- which rests on
  ``QgsSpatialIndex`` boxes being closed (touching boxes match), and on a
  ``box_around`` query containing every point a ``distance() < radius`` test
  keeps, rounding included;
* in the order the scan met things, because callers keep the scan's first
  match or rely on a stable sort for ties, and the tree answers in its own
  order once it holds more than ten entries;
* the things no box can describe -- a NaN or infinite bound, or one so large
  the tree's area arithmetic overflows -- every time, because the scan tested
  those too, and an index cannot hold them: one NaN box among fifty, or two
  points at +/-1e200 among two hundred, killed the process (SIGSEGV) on
  3.22.16, 3.44.15 and 4.2.3.

Each test pins one of those. The tree-order and closed-box facts were measured
on 3.22.16, 3.40.15, 3.44.15, 4.0.3 and 4.2.3, identical on all five.
"""
import math
import os
import random
import subprocess
import sys

from qgis.core import QgsPointXY, QgsRectangle, QgsSpatialIndex

from fiberq.utils.spatial import ScanOrderIndex, box_around, indexable_box

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for the crash-regression child. The suite has no timeout plugin.
TIMEOUT_S = 120

NAN, INF = float("nan"), float("inf")


def _points(index, points):
    for key, point in points:
        index.add(key, box_around(point, 0.0))
    return index


def test_candidates_come_back_in_the_order_they_were_added(qgis_app):
    """The tree's own order is not insertion order past ten entries (measured).

    Without the sort, a scan's "first match" and a stable sort's tie order
    would both change with the shape of the tree.
    """
    rng = random.Random(20261010)
    points = [(key, QgsPointXY(rng.uniform(0, 100), rng.uniform(0, 100))) for key in range(500)]
    index = _points(ScanOrderIndex(), points)

    raw = QgsSpatialIndex()
    for key, point in points:
        raw.addFeature(key, box_around(point, 0.0))
    everywhere = QgsRectangle(-1, -1, 101, 101)
    assert raw.intersects(everywhere) != list(range(500)), "premise: the tree reorders"

    assert index.candidates(everywhere) == list(range(500))
    window = QgsRectangle(20, 30, 60, 70)
    inside = [key for key, point in points if window.contains(point)]
    assert index.candidates(window) == inside
    assert index.everything() == list(range(500))
    assert len(index) == 500


def test_boxes_that_only_touch_are_candidates(qgis_app):
    """Closed boxes: an exact test may still accept a touching neighbour.

    A measured premise about QgsSpatialIndex, not a property of this module.
    Every superset argument above rests on it, so if a future QGIS opened its
    boxes this fails first, before a caller quietly loses a neighbour.
    """
    index = ScanOrderIndex()
    index.add("square", QgsRectangle(0, 0, 10, 10))
    assert index.candidates(QgsRectangle(10, 0, 15, 5)) == ["square"]      # shares an edge
    assert index.candidates(QgsRectangle(10, 10, 12, 12)) == ["square"]    # shares a corner
    assert index.candidates(QgsRectangle(10, 2, 10, 4)) == ["square"]      # zero width, on the edge
    beyond = 10.000000000000002                                             # the next double up
    assert index.candidates(QgsRectangle(beyond, 0, 15, 5)) == []


def test_the_box_holds_every_point_a_distance_test_keeps(qgis_app):
    """``distance() < radius`` over candidates() equals it over everything.

    Fuzzed at the magnitudes FiberQ's projects have (EPSG:3857 runs to ~2e7),
    with points placed on and just around the radius, where rounding decides.
    """
    rng = random.Random(1)
    ulp = 2.0 ** -52
    for magnitude in (0.0, 1.0, 1e3, 1.9e6, 5.4e6, 2e7):
        for radius in (1e-2, 5.0):
            centre = QgsPointXY(magnitude + rng.uniform(-1, 1), magnitude + rng.uniform(-1, 1))
            points = []
            for key in range(600):
                # on the axes, where the box edge is the whole story ...
                if key % 3 == 0:
                    reach = radius * rng.choice((1.0, 1 - ulp, 1 + ulp, 1 - 4 * ulp, 1 + 4 * ulp))
                    dx, dy = rng.choice(((reach, 0.0), (-reach, 0.0), (0.0, reach), (0.0, -reach)))
                # ... and in every other direction, inside, on and outside the radius
                else:
                    angle = rng.uniform(0, 2 * math.pi)
                    reach = radius * rng.choice((rng.uniform(0, 2), 1.0, 1 - 1e-12, 1 + 1e-12))
                    dx, dy = reach * math.cos(angle), reach * math.sin(angle)
                points.append((key, QgsPointXY(centre.x() + dx, centre.y() + dy)))
            index = _points(ScanOrderIndex(), points)
            positions = dict(points)
            exact = [key for key, point in points if point.distance(centre) < radius]
            narrowed = [key for key in index.candidates(box_around(centre, radius))
                        if positions[key].distance(centre) < radius]
            assert exact, "premise: some points are inside the radius"
            assert narrowed == exact, (magnitude, radius)


def test_a_point_on_the_box_edge_inside_the_radius_is_found(qgis_app):
    """(1, 2.01) is ON the 1 cm box around (1, 2), and 0.009999999999999787 away.

    The box's top edge is the point's own y, so an index with open boxes would
    lose a pole that Route correction's ``< 1e-2`` test accepts.
    """
    centre, on_edge = QgsPointXY(1.0, 2.0), QgsPointXY(1.0, 2.01)
    assert box_around(centre, 1e-2).yMaximum() == on_edge.y()
    assert on_edge.distance(centre) < 1e-2
    index = _points(ScanOrderIndex(), [("edge", on_edge)])
    assert index.candidates(box_around(centre, 1e-2)) == ["edge"]


def test_a_thing_without_a_finite_box_is_offered_to_every_query(qgis_app):
    """The scan tested them, so the exact test must still see them, in order."""
    index = ScanOrderIndex()
    index.add("a", QgsRectangle(0, 0, 1, 1))
    index.add("nan", QgsRectangle(NAN, 0, 1, 1))
    index.add("far", QgsRectangle(100, 100, 101, 101))
    index.add("inf", QgsRectangle(0, 0, INF, 1))
    assert len(index) == 4
    assert index.candidates(QgsRectangle(0, 0, 2, 2)) == ["a", "nan", "inf"]
    assert index.candidates(QgsRectangle(500, 500, 501, 501)) == ["nan", "inf"]
    # and a query no box can describe gets the scan itself
    assert index.candidates(QgsRectangle(NAN, NAN, NAN, NAN)) == ["a", "nan", "far", "inf"]
    assert not indexable_box(QgsRectangle(-INF, 0, 1, 1))
    assert not indexable_box(QgsRectangle(-1e200, -1e200, -1e200, -1e200))
    assert indexable_box(QgsRectangle(-2e7, -2e7, 2e7, 2e7))


NON_FINITE_DRIVER = '''
import os, random, sys
sys.path.insert(0, {repo!r})
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication, QgsRectangle
app = QgsApplication([], True)
app.initQgis()
from qgis.PyQt.QtCore import QRectF
from fiberq.utils.spatial import ScanOrderIndex
nan, inf = float("nan"), float("inf")
rnd = random.Random(1)
bad = [QRectF(5, nan, 15, 15), QRectF(inf, 5, 30, 15), QRectF(-inf, 5, 30, 15), QRectF(nan, nan, 30, 18)]
for b in bad:
    index, plain = ScanOrderIndex(), []
    for i in range(50):
        r = b if i == 25 else QRectF(rnd.uniform(0, 2000), rnd.uniform(0, 1000), 30, 18)
        # QgsRectangle(QRectF) copies the bounds as they are: the shape that crashed
        index.add(r, QgsRectangle(r))
        plain.append(r)
    for q in [QRectF(rnd.uniform(0, 2000), rnd.uniform(0, 1000), 40, 18) for _ in range(200)] + bad:
        got = any(q.intersects(r) for r in index.candidates(QgsRectangle(q)))
        assert got == any(q.intersects(r) for r in plain), (b, q)
print("SURVIVED", flush=True)
os._exit(0)
'''


def test_a_non_finite_box_never_reaches_the_index(tmp_path):
    """One NaN or infinite box among fifty, as the schematic view can produce.

    Handed to ``QgsSpatialIndex.addFeature`` this exact sequence exits with a
    SIGSEGV (measured on 3.22.16, 3.44.15 and 4.2.3), so it runs in a child
    process: a crash fails this test instead of ending the whole run.
    """
    script = tmp_path / "non_finite.py"
    script.write_text(NON_FINITE_DRIVER.format(repo=REPO_ROOT), encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path), timeout=TIMEOUT_S,
                          env=dict(os.environ, QT_QPA_PLATFORM="offscreen", FIBERQ_LOG_FILE="false"),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 0, f"returncode {done.returncode}\n{output[-3000:]}"
    assert "SURVIVED" in output, output[-3000:]


HUGE_DRIVER = '''
import os, random, sys
sys.path.insert(0, {repo!r})
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication, QgsPointXY
app = QgsApplication([], True)
app.initQgis()
from fiberq.utils.spatial import ScanOrderIndex, box_around
rnd = random.Random(1)
points = [QgsPointXY(1e200, 1e200), QgsPointXY(-1e200, -1e200)] + [
    QgsPointXY(rnd.uniform(0, 1000), rnd.uniform(0, 1000)) for _ in range(200)]
index = ScanOrderIndex()
for key, point in enumerate(points):
    index.add(key, box_around(point, 0.0))
for query in points:
    near = [k for k in index.candidates(box_around(query, 1e-2)) if points[k].distance(query) < 1e-2]
    assert near == [k for k, p in enumerate(points) if p.distance(query) < 1e-2], query
print("SURVIVED", flush=True)
os._exit(0)
'''


def test_a_huge_but_finite_box_never_reaches_the_index(tmp_path):
    """Two points at +/-1e200 added first, then two hundred ordinary ones.

    Finite, so a NaN guard alone lets them in, and the R-tree's area
    arithmetic overflows on them: this exact sequence handed to
    ``addFeature`` exits with a SIGSEGV (measured on 3.22.16, 3.44.15 and
    4.2.3; 2e154 crashed and 1e154 did not). v1.5.0's scans only compared
    distances and answered normally, so the index must too.
    """
    script = tmp_path / "huge.py"
    script.write_text(HUGE_DRIVER.format(repo=REPO_ROOT), encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path), timeout=TIMEOUT_S,
                          env=dict(os.environ, QT_QPA_PLATFORM="offscreen", FIBERQ_LOG_FILE="false"),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 0, f"returncode {done.returncode}\n{output[-3000:]}"
    assert "SURVIVED" in output, output[-3000:]
