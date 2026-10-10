"""Spatial indexing: an index query where a full scan used to be.

WP4 task 4.1 (PF-1, PF-2, PF-3). Three dialogs measured one thing against every
other thing in the project: the schematic view each new label against every
label already placed, the latent-elements list each cable against every placing
element, Route correction each route end against every pole and manhole. That
is n x m work, and at the benchmark's size S it came to 17.2 million rectangle
tests, 4.5 million GEOS distances and 5.1 million point distances (measured on
v1.5.0, QGIS 3.44.15).

Two indexes narrow those loops down to the few things close enough to matter:
``ScanOrderIndex`` for the latent-elements list and Route correction, which
need the things in the order the scan met them, and ``RectGrid`` for the
schematic view's labels, which only ask whether anything overlaps. Neither
decides anything itself: each caller keeps its own exact test -- the same
``QRectF.intersects``, ``QgsGeometry.distance`` or ``QgsPointXY.distance``
comparison the scan made -- and only what that test runs over is shorter. So
the answers are the scan's answers, which is the point: users and tests
already rely on them.

Three facts shape ``ScanOrderIndex``, each measured on QGIS 3.22.16, 3.40.15,
3.44.15, 4.0.3 and 4.2.3, with identical results:

* ``QgsSpatialIndex`` answers in tree order once it holds more than ten
  entries: neither the order things were added nor id order. ``candidates()``
  sorts back into the order things were added, so a caller that kept the
  scan's first match, or relies on a stable sort to break ties, still sees the
  scan's order.
* Its boxes are closed. Boxes that only touch, and zero-width boxes, still
  match, so a query box that holds everything the exact test could accept
  returns a superset, never less.
* A box with a NaN or infinite bound must never go in, and nor must one with a
  bound beyond ~2e154, where the tree's area arithmetic overflows. Among fifty
  neighbours one NaN box killed the process outright (SIGSEGV, exit 139), and
  so did two points at +/-1e200 among two hundred ordinary ones; otherwise a
  NaN box matched unrelated queries, or none. Such things are kept aside and
  handed to every query instead, so the exact test still sees them, as the
  scan did. No coordinate system comes within a hundred orders of magnitude
  of the limit, so this costs real projects nothing.
"""
import math

from qgis.core import QgsRectangle, QgsSpatialIndex


#: The largest bound a box may have and still go into the index. Overflow starts
#: near 2e154 (measured: 2e154 crashed, 1e154 did not, on 3.22.16, 3.44.15 and
#: 4.2.3); this leaves a wide margin below that and a wider one above any map.
_LARGEST_BOUND = 1e150


def indexable_box(box):
    """True when the ``QgsRectangle`` can go into the index: four finite bounds, none huge."""
    return all(math.isfinite(value) and abs(value) <= _LARGEST_BOUND for value in (
        box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()))


def box_around(point, radius):
    """The square of half-side ``radius`` centred on ``point``, edges included.

    Every point whose ``QgsPointXY.distance()`` to ``point`` is less than
    ``radius`` lies inside it. That distance is ``sqrt(dx*dx + dy*dy)``, which is
    never less than ``|dx|``, and rounding is monotone, so rounding the box's
    edges cannot cut off a coordinate the exact edge would keep. Querying this
    box is therefore a superset of a ``distance(...) < radius`` test.
    """
    return QgsRectangle(point.x() - radius, point.y() - radius,
                        point.x() + radius, point.y() + radius)


class ScanOrderIndex:
    """Things with a bounding box each, answered in the order they were added.

    Fill it in the order the scan it replaces met them, query it as often as
    needed, and run the scan's own test over what ``candidates()`` returns. It
    describes the layers as they were when it was filled, so it is built once
    per operation, never kept across one.
    """

    def __init__(self):
        self._index = QgsSpatialIndex()
        self._items = []
        #: Positions of the things whose box cannot be indexed. See the module docstring.
        self._unboxed = []

    def __len__(self):
        return len(self._items)

    def add(self, item, box):
        """Add ``item``, whose bounding box is the ``QgsRectangle`` ``box``."""
        position = len(self._items)
        self._items.append(item)
        if indexable_box(box):
            self._index.addFeature(position, box)
        else:
            self._unboxed.append(position)

    def candidates(self, box):
        """Everything whose box meets ``box``, edges included, in the order added.

        Things whose box cannot be indexed are always included, and so is
        everything when the query box itself cannot be: in both cases only the
        caller's exact test can tell, as it did in the scan.
        """
        if not indexable_box(box):
            return self.everything()
        positions = self._index.intersects(box)
        positions.extend(self._unboxed)
        positions.sort()
        return [self._items[position] for position in positions]

    def everything(self):
        """Every item, in the order added: the scan itself, for when no box applies."""
        return list(self._items)


#: A box spanning more grid cells than this is kept aside, like one that
#: cannot be indexed. No label comes near it: a label is about one cell wide.
_MAX_CELLS = 256


class RectGrid:
    """Boxes in a uniform grid, asked one question: does any of them pass a test?

    For the schematic view's labels (WP4 PF-1). Its "Match map styling" layout
    draws the whole network into a fixed 1600 x 1000 scene, so labels pile up
    as the project grows, and a QgsSpatialIndex query hands back every label
    in the pile -- 215 on average, and up to 467, per query at size L -- when
    one overlap is the whole answer. That was quadratic again, and on QGIS 3
    slower than v1.5.0's plain scan at L (measured). A grid lets the test stop
    at its first hit, and offers it nothing far away.

    The answer is what ``any(test(item) for item in everything)`` answers,
    for a test that can only accept an item whose box overlaps the query's,
    as ``QRectF.intersects`` does. Two boxes that overlap share a point, and
    ``floor`` keeps the order of coordinates, so they share a cell; every item
    in the cells a query covers is offered to the test, and the test decides.
    Items whose box cannot be indexed, or would span more than ``_MAX_CELLS``
    cells, are offered to every query, and a query box that cannot be placed
    is offered everything. An item in several cells may be offered more than
    once, which changes nothing for an any().

    The work per query is bounded by how many boxes sit in the cells the query
    covers, not by the scan's. Cells are walked in turn, so a crowded cell met
    before the one holding the scan's first hit is walked in full, and a scene
    built for it -- two piles of coincident nodes a label apart -- costs more
    than v1.5.0's scan (13.5 million tests against 33 thousand for 3,003
    labels, 3.44.15). The benchmark cities' map layouts stay at 57 tests per
    query or fewer. Walking the cells merged into insertion order would bound
    the work by the scan's, but measured about twice as slow on those layouts.
    """

    def __init__(self, cell):
        self._cell = float(cell)
        self._items = []
        self._cells = {}
        self._unboxed = []

    def __len__(self):
        return len(self._items)

    def add(self, item, box):
        """Add ``item``, whose bounding box is the ``QgsRectangle`` ``box``."""
        self._items.append(item)
        cells = self._cells_of(box)
        if cells is None:
            self._unboxed.append(item)
            return
        for cell in cells:
            self._cells.setdefault(cell, []).append(item)

    def any_passes(self, box, test):
        """True when ``test`` accepts an item near ``box``; stops at the first that it does."""
        cells = self._cells_of(box)
        if cells is None:
            return any(test(item) for item in self._items)
        for cell in cells:
            for item in self._cells.get(cell, ()):
                if test(item):
                    return True
        return any(test(item) for item in self._unboxed)

    def _cells_of(self, box):
        """The cells ``box`` covers, edges included, or None when it cannot be placed."""
        if not indexable_box(box):
            return None
        size = self._cell
        # In order whatever the box says: an inverted box would cover no cell.
        x0, x1 = sorted((box.xMinimum(), box.xMaximum()))
        y0, y1 = sorted((box.yMinimum(), box.yMaximum()))
        left, right = math.floor(x0 / size), math.floor(x1 / size)
        low, high = math.floor(y0 / size), math.floor(y1 / size)
        if (right - left + 1) * (high - low + 1) > _MAX_CELLS:
            return None
        return [(column, row) for column in range(left, right + 1) for row in range(low, high + 1)]


__all__ = ['RectGrid', 'ScanOrderIndex', 'box_around', 'indexable_box']
