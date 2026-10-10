"""The list of latent elements opens in linear time and shows what v1.5.0 showed.

WP4 task 4.1, item PF-2. Opening "List of latent elements" cost, for every row,
a scan of the cable's own layer until its fid came up, and then one GEOS
distance call for every placing element in the project: cables x elements,
4,531,020 calls at size S. The list took 61 s to open at S and ~6 min at M,
and did not finish at L in 30 minutes (v1.5.0, QGIS 3.44.15). It now reads each
layer once and measures each cable only against the elements its bounding box
can reach.

**Counted, not timed**: a busy runner cannot fail these, and a regression
cannot hide behind a fast machine. The count test fails on v1.5.0. The output
is pinned twice: against v1.5.0's own result on the XS city, and on small
projects for the cases the city does not contain -- equal ``m`` inside one
layer, an unsaved edit buffer, a one-vertex cable, the tolerance edge.
"""
import hashlib
import json
import shutil

import pytest
from qgis.core import (QgsFeature, QgsGeometry, QgsLineString, QgsPoint, QgsPointXY,
                       QgsProject, QgsVectorLayer, QgsWkbTypes)

#: Every row of the list and every cable's candidate list on the XS city,
#: captured from the v1.5.0 tag: sha256 over the JSON ``_digest`` builds. The
#: floats are compared exactly; v1.5.0 gives the same bits on 3.22.16, 3.40.15,
#: 3.44.15, 4.0.3 and 4.2.3 (measured).
XS_ROWS, XS_EDITABLE, XS_CANDIDATES = 275, 178, 391
XS_DIGEST = "f7bf0b8b60ddc6128d83accdd576bed1ff0088d73a1528396886691adb0feea1"


class _Bar:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _Iface:
    def __init__(self):
        self.bar = _Bar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.clear()
    yield prj
    prj.clear()


@pytest.fixture
def plugin(project):
    """A FiberQPlugin with the managers the list reads, and nothing else."""
    from fiberq.core.cable_manager import CableManager
    from fiberq.core.data_manager import DataManager
    from fiberq.core.relations_manager import RelationsManager
    from fiberq.main_plugin import FiberQPlugin

    obj = FiberQPlugin.__new__(FiberQPlugin)
    obj.iface = _Iface()
    obj.data_manager = DataManager(obj.iface, obj)
    obj.relations_manager = RelationsManager(obj.data_manager)
    obj.cable_manager = CableManager(obj.iface, None, obj.data_manager, None)
    return obj


def _layer(project, uri, name, rows, fields=("naziv",)):
    uri += "".join("&field=%s:string" % f for f in fields)
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid()
    feats = []
    for geom, attrs in rows:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        for key, value in attrs.items():
            feat[key] = value
        feats.append(feat)
    ok, _added = layer.dataProvider().addFeatures(feats)
    assert ok
    project.addMapLayer(layer)
    return layer


def _pt(x, y):
    return QgsGeometry.fromPointXY(QgsPointXY(x, y))


def _line(*points):
    return QgsGeometry(QgsLineString([QgsPoint(x, y) for x, y in points]))


def _rows(dialog):
    tbl = dialog.tbl
    return [[tbl.item(r, 1).text(), tbl.item(r, 2).text(), tbl.item(r, 3).text(),
             tbl.item(r, 4).text(), tbl.cellWidget(r, 5).isEnabled()]
            for r in range(tbl.rowCount())]


def _digest(rows, candidates):
    blob = json.dumps({"rows": rows, "candidates": candidates}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The work
# ---------------------------------------------------------------------------

def _street(project, n):
    """n short cables 100 m apart, each with a closure on it and a terminal 1 km off."""
    _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
           [(_line((i * 100.0, 0), (i * 100.0 + 50, 0)), {"od": "", "do": ""}) for i in range(n)],
           fields=("od", "do"))
    _layer(project, "Point?crs=EPSG:3857", "Joint Closures",
           [(_pt(i * 100.0 + 25, 1), {"naziv": "JC-%d" % i}) for i in range(n)])
    _layer(project, "Point?crs=EPSG:3857", "Outdoor TO",
           [(_pt(i * 100.0 + 25, 1000), {"naziv": "TO-%d" % i}) for i in range(n)])


def _count(patch, cls, name):
    calls = [0]
    real = getattr(cls, name)

    def counting(self, *args, **kwargs):
        calls[0] += 1
        return real(self, *args, **kwargs)
    patch.setattr(cls, name, counting)
    return calls


def _open_counting(project, plugin, n):
    from fiberq.dialogs.latent_dialog import LatentElementsDialog

    project.removeAllMapLayers()
    _street(project, n)
    with pytest.MonkeyPatch.context() as patch:
        distance = _count(patch, QgsGeometry, "distance")
        reads = _count(patch, QgsVectorLayer, "getFeatures")
        rows = _rows(LatentElementsDialog(plugin))
    assert len(rows) == n and all(row[4] for row in rows)
    return distance[0], reads[0]


def test_opening_the_list_does_not_measure_every_cable_against_every_element(project, plugin):
    """v1.5.0: 20 x 40 then 80 x 160 distance calls -- 800 and 12,800, x16 for x4 the data.

    It also read the cable layer again for every row and every element layer
    again for every cable: 61 reads at n=20, 241 at n=80.
    """
    small_distance, small_reads = _open_counting(project, plugin, 20)
    large_distance, large_reads = _open_counting(project, plugin, 80)
    assert large_distance / small_distance < 8, (small_distance, large_distance)
    assert large_reads == small_reads, (small_reads, large_reads)


# ---------------------------------------------------------------------------
# The output: v1.5.0's, to the bit
# ---------------------------------------------------------------------------

def test_the_list_shows_what_v150_showed_on_the_xs_city(project, plugin, city_xs_dataset, tmp_path):
    """Every row, and every cable's candidate list, against the v1.5.0 capture.

    The candidate lists are compared through both ways the code reaches them:
    the index the list builds once per opening, and the fresh search the
    per-cable editor makes when its Edit button is clicked.
    """
    from fiberq.core import data_manager
    from fiberq.dialogs.latent_dialog import LatentElementsDialog

    for key in ("gpkg", "qgz"):
        shutil.copy(city_xs_dataset[key], tmp_path)
    assert project.read(str(tmp_path / "city_XS.qgz"))

    rows = _rows(LatentElementsDialog(plugin))
    # v1.5.0 has no index: there, both ways are the fresh search
    index = getattr(data_manager, "PlacingElementIndex", None)
    shared = {"elements": index()} if index else {}
    fresh, indexed = {}, {}
    for cable in plugin.list_all_cables():
        layer = project.mapLayer(cable["layer_id"])
        feat = layer.getFeature(cable["fid"])
        key = "%s:%d" % (cable["layer_id"], cable["fid"])
        for out, kwargs in ((fresh, {}), (indexed, shared)):
            cands = plugin._find_candidate_elements_for_cable(layer, feat, **kwargs)
            if cands:
                out[key] = [[c["layer_id"], c["fid"], c["naziv"], c["m"], c["distance"]]
                            for c in cands]

    assert (len(rows), sum(1 for row in rows if row[4])) == (XS_ROWS, XS_EDITABLE)
    assert sum(len(cands) for cands in fresh.values()) == XS_CANDIDATES
    assert _digest(rows, fresh) == XS_DIGEST
    assert indexed == fresh


def _names(plugin, layer):
    """The candidate names through every way the code reaches them.

    The fresh search, and the index the list shares between its cables -- which
    v1.5.0 does not have, so there the fresh search is the only way.
    """
    from fiberq.core import data_manager

    feat = next(layer.getFeatures())
    ways = [{}]
    index = getattr(data_manager, "PlacingElementIndex", None)
    if index is not None:
        ways.append({"elements": index()})
    return [[c["naziv"] for c in plugin._find_candidate_elements_for_cable(layer, feat, **kwargs)]
            for kwargs in ways]


def test_equal_m_keeps_the_order_the_old_search_met_the_elements_in(project, plugin):
    """Layer order, then each layer's own order -- never the index's, never fid order.

    The list is a stable sort by ``m``, so elements at the same ``m`` keep the
    order the search met them in. Each station below is such a tie: a north
    point from the first half of the layer and a south point from the second.
    Answered in QgsSpatialIndex order, 29 of the 30 pairs come back
    south-first (measured on 3.44.15; below ~10 entries the index happens to
    answer in insertion order, which is why there are this many). A layer with
    unsaved additions hands them out first, -2 before -3 (measured), so a fid
    tie-break would put the saved terminal first.
    """
    cables = _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
                    [(_line((0, 0), (1000, 0)), {"od": "", "do": ""})], fields=("od", "do"))
    stations = [10 * (i + 1) for i in range(30)]
    north = [(_pt(x, 3), {"naziv": "N%d" % x}) for x in stations]
    south = [(_pt(x, -3), {"naziv": "S%d" % x}) for x in stations]
    _layer(project, "Point?crs=EPSG:3857", "Joint Closures", north + south)
    _layer(project, "Point?crs=EPSG:3857", "ODF", [(_pt(10, 1), {"naziv": "ODF10"})])
    terminals = _layer(project, "Point?crs=EPSG:3857", "Outdoor TO",
                       [(_pt(300, 2), {"naziv": "TO-saved"})])
    assert terminals.startEditing()
    for name in ("TO-new1", "TO-new2"):
        feat = QgsFeature(terminals.fields())
        feat.setGeometry(_pt(300, -2))
        feat["naziv"] = name
        assert terminals.addFeature(feat)
    expected = []
    for x in stations:
        expected += ["N%d" % x, "S%d" % x]
        expected += {10: ["ODF10"], 300: ["TO-new1", "TO-new2", "TO-saved"]}.get(x, [])
    try:
        for names in _names(plugin, cables):
            assert names == expected
    finally:
        terminals.rollBack()


def test_a_one_vertex_cable_still_lists_every_element(project, plugin):
    """GEOS cannot read a one-vertex line, distance() answers -1, and -1 > tol is false.

    So v1.5.0 listed every placing element in the project for such a cable, at
    m = -1, and enabled its Edit button with nothing near it. An index that
    trusted the line's bounding box would list none; this pins the old answer
    until someone decides to change it on purpose.
    """
    from fiberq.dialogs.latent_dialog import LatentElementsDialog

    cables = _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
                    [(_line((50, 50)), {"od": "", "do": ""})], fields=("od", "do"))
    _layer(project, "Point?crs=EPSG:3857", "Joint Closures",
           [(_pt(5000, 5000), {"naziv": "far"}), (_pt(-900, 70), {"naziv": "farther"})])
    for names in _names(plugin, cables):
        assert names == ["far", "farther"]
    assert [row[4] for row in _rows(LatentElementsDialog(plugin))] == [True]


def test_the_edit_button_ignores_the_cables_own_endpoints(project, plugin):
    """Enabled only by a candidate the editor would list -- not by an endpoint.

    The button stops at the first candidate, so that stop must come after the
    endpoint-name exclusion: counting first flipped 97 of the 275 XS rows.
    """
    from fiberq.dialogs.latent_dialog import LatentElementsDialog

    _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
           [(_line((0, 0), (100, 0)), {"od": "ODF-1", "do": "JC-1"}),
            (_line((0, 500), (100, 500)), {"od": "ODF-2", "do": "JC-2"})], fields=("od", "do"))
    _layer(project, "Point?crs=EPSG:3857", "ODF",
           [(_pt(0, 0), {"naziv": "ODF-1"}), (_pt(0, 500), {"naziv": "ODF-2"})])
    _layer(project, "Point?crs=EPSG:3857", "Joint Closures",
           [(_pt(100, 0), {"naziv": "JC-1"}), (_pt(100, 500), {"naziv": "JC-2"}),
            (_pt(50, 501), {"naziv": "JC-mid"})])
    assert [row[4] for row in _rows(LatentElementsDialog(plugin))] == [False, True]


def test_a_curved_cable_finds_the_elements_along_the_line_geos_measures(project, plugin):
    """GEOS measures a curve segmentized; QGIS's box of the curve can miss part of it.

    CircularString (0 0, 200 0, 100 0) is a degenerate arc whose middle point
    lies beyond its end. GEOS segmentizes it to reach x = 200 and measures the
    closure at (200, 3) 3.0 away, so v1.5.0 listed it. QGIS boxes the curve
    from a circle centre a collinear arc does not have: a box ending at x = 100
    on 3.40 through 4.2, which leaves the closure out, and on 3.22 whatever that
    memory held, so the box there changes from run to run (measured). FiberQ's
    own LineString cable layers store a curve unchanged.
    """
    from fiberq.dialogs.latent_dialog import LatentElementsDialog

    cables = _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
                    [(QgsGeometry.fromWkt("CircularString (0 0, 200 0, 100 0)"), {"od": "", "do": ""})],
                    fields=("od", "do"))
    _layer(project, "Point?crs=EPSG:3857", "Joint Closures", [(_pt(200, 3), {"naziv": "JC-1"})])
    assert QgsWkbTypes.isCurvedType(next(cables.getFeatures()).geometry().wkbType()), \
        "premise: the layer kept the curve"
    for names in _names(plugin, cables):
        assert names == ["JC-1"]
    assert [row[4] for row in _rows(LatentElementsDialog(plugin))] == [True]


def test_a_short_list_does_not_build_the_index(project, plugin):
    """Three cables or fewer are searched one by one; four or more share the index.

    Building the index costs 2.0-2.6 fresh searches, so building it for a
    short list made the list slower than v1.5.0's: at size M, 2.6 ms became
    136 ms with no cables and 60 ms became 136 ms with one (3.44.15), and
    three cables whose boxes span every element were 16-29% slower on 3.40
    (measured). A fresh search stopping at its first candidate never costs
    more than v1.5.0's per-cable search did.
    """
    from qgis.core import QgsSpatialIndex
    from fiberq.dialogs.latent_dialog import LatentElementsDialog

    built = []
    for count in range(5):
        project.removeAllMapLayers()
        _layer(project, "Point?crs=EPSG:3857", "Joint Closures",
               [(_pt(i * 10.0, 1), {"naziv": "JC-%d" % i}) for i in range(50)])
        if count:
            _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
                   [(_line((i * 100.0, 0), (i * 100.0 + 50, 0)), {"od": "", "do": ""})
                    for i in range(count)], fields=("od", "do"))
        with pytest.MonkeyPatch.context() as patch:
            indexed = _count(patch, QgsSpatialIndex, "addFeature")
            rows = _rows(LatentElementsDialog(plugin))
        assert len(rows) == count
        built.append(indexed[0])
    assert built[:4] == [0, 0, 0, 0], built
    assert built[4] > 0, "premise: four cables do share the index"


def test_an_element_exactly_tol_from_the_cable_is_kept(project, plugin):
    """The old search kept it; a box grown by exactly tol drops it.

    GEOS measures this pair 5.0 apart, but -3.9970090336748285 + 5.0 rounds to
    1.0029909663251715, just short of the point. Found by a random search: 65
    of 89,623 points at distance <= tol fell outside a box grown by tol near
    the origin, none outside one grown by 2 * tol (measured on 3.44.15).
    """
    cables = _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
                    [(_line((-176.3457609018353, 6.400690145197046), (-3.9970090336748285, 81.2073930300092)),
                      {"od": "", "do": ""})], fields=("od", "do"))
    _layer(project, "Point?crs=EPSG:3857", "Joint Closures",
           [(_pt(1.002990966325172, 81.2073930300092), {"naziv": "edge"})])
    for names in _names(plugin, cables):
        assert names == ["edge"]
