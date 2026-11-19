"""The elements along a cable that the list of latent elements offers, and the relation each cable is in, against
answers worked out by hand.

test_latent_elements.py pins the list against a digest of v1.5.0's output on the XS city, which needs QGIS 3.36 or
later, and checks its smaller cases by name only; test_interchange_path_stops.py checks that the editor keeps the
elements it does not show. This file adds, on every QGIS from 3.22: each candidate's ``m`` (how far along the cable
its foot lies) and distance on a small street worked out by hand, which layers the search takes, elements with no
name, a multipart cable and a MultiPoint element, the name a relation gives each cable, the relation found by its
id, and the plugin's search compared with the second copy that RelationsManager keeps.

The plugin runs DataManager's search, reached through FiberQPlugin and RelationsManager as the plugin wires them
(``wired_plugin``). RelationsManager's own copy runs only when it has no DataManager, or when DataManager's search
raised past its own handling, which no input here makes it do; the tests of the two copies compare its answers
with the plugin's.

The street: the cable runs (0 0) -> (100 0) -> (100 50), 150 m long, so an element's distance is its offset from
the nearer leg, and ``m`` is where its foot lies along the cable. GEOS gives these figures exactly on every QGIS;
they are compared to within 1e-9.
"""
import pytest
from qgis.core import (Qgis, QgsAnnotationLayer, QgsCoordinateTransformContext, QgsVectorFileWriter,
                       QgsVectorLayer)

from support.core_env import CoreIface, canvas_not_rendering, clean_project, is_null, memory_layer, wired_plugin

from fiberq.core.data_manager import PlacingElementIndex
from fiberq.core.relations_manager import RelationsManager


class CopiesDisagree(AssertionError):
    """RelationsManager's own candidate search answers otherwise than DataManager's, which the plugin runs
    (WP5-FU-43)."""


class MultiPointMisplaced(AssertionError):
    """A MultiPoint element is listed at m = -1, first, wherever it lies along the cable (WP5-FU-44)."""


class OwnEndListed(AssertionError):
    """A cable's own unnamed end is listed among its candidates (WP5-FU-45)."""


class NullNamedNull(AssertionError):
    """On QGIS 3 an element with a NULL name in a GeoPackage is named "NULL", and so dropped along a cable whose
    end is named "NULL" (WP5-FU-45)."""


@pytest.fixture
def project(qgis_app):
    with clean_project() as prj:
        yield prj


@pytest.fixture
def plugin(project):
    """FiberQPlugin with its managers wired as the plugin wires them."""
    return wired_plugin(CoreIface())


def _points(project, name, rows, fields=("naziv",), uri="Point"):
    """A point layer ``name`` in the project, holding ``rows`` (``(WKT or None, {field: value})``)."""
    return memory_layer(project, uri, name, rows, fields)


def _cable(project, wkt, od="", do="", uri="LineString"):
    """The layer "Underground cables" holding one cable, ``wkt``, from ``od`` to ``do``; and that cable."""
    layer = memory_layer(project, uri, "Underground cables", [(wkt, {"od": od, "do": do})], ("od", "do"))
    return layer, next(layer.getFeatures())


def _street(project, cable="LineString (0 0, 100 0, 100 50)", tb=True, others=True):
    """The cable from ODF-1 to TO-END, the placing elements along it and off it, and other point layers on it."""
    found = _cable(project, cable, "ODF-1", "TO-END")
    _points(project, "ODF", [("Point (0 0)", {"naziv": "ODF-1"})])       # the cable's od: left out by name
    _points(project, "Joint Closures", [
        ("Point (40 3)", {"naziv": "JC-A"}),          # fid 1: 3 m off the first leg, at m 40
        ("Point (50 6)", {"naziv": "JC-far"}),        # fid 2: 6 m off, beyond the 5 m tolerance
        ("Point (103 -4)", {"naziv": "JC-corner"}),   # fid 3: 5 m from the bend (3-4-5), at m 100
        ("Point (-3 4)", {"naziv": "JC-before"}),     # fid 4: 5 m from the start (3-4-5), at m 0
        (None, {"naziv": "JC-nowhere"}),              # fid 5: no geometry
        ("Point (500 500)", {"naziv": "JC-off"}),     # fid 6: far away
    ])
    _points(project, "Outdoor TO", [
        ("Point (70 -2)", {}),                        # fid 1: no name, 2 m off, at m 70
        ("Point (100 50)", {"naziv": "TO-END"}),      # the cable's do: left out by name
        ("Point (100 56)", {"naziv": "TO-beyond"}),   # 6 m past the cable's end
    ])
    _points(project, "OTB", [("Point (100 30)", {"naziv": "OTB-on"})])   # on the second leg, at m 130
    # Not a vector layer, under the name of a placing layer: passed over.
    options = QgsAnnotationLayer.LayerOptions(project.transformContext())
    assert project.addMapLayer(QgsAnnotationLayer("Joint Closure TO", options)) is not None
    if tb:
        # A placing layer with no naziv field: its element is named by layer and fid.
        _points(project, "TB", [("Point (90 1)", {"oznaka": "TB-x"})], fields=("oznaka",))
    if others:
        # On the cable, but not placing elements.
        _points(project, "Poles", [("Point (20 0)", {"tip": "wood"})], fields=("tip",))
        _points(project, "Manholes", [("Point (30 0)", {"broj_okna": "7"})], fields=("broj_okna",))
        _points(project, "Fiber break", [("Point (80 0)", {"naziv": "FB-1"})])
        _points(project, "Addresses", [("Point (60 1)", {"naziv": "Main St 5"})])
    return found


#: ``(layer, fid, name, m, distance)`` along the street, by hand. ODF-1 and TO-END are the cable's ends and are left
#: out by name; JC-before and JC-corner are exactly the 5 m tolerance away and kept.
EXPECTED = [
    ("Joint Closures", 4, "JC-before", 0.0, 5.0),
    ("Joint Closures", 1, "JC-A", 40.0, 3.0),
    ("Outdoor TO", 1, "Outdoor TO:1", 70.0, 2.0),
    ("TB", 1, "TB:1", 90.0, 1.0),
    ("Joint Closures", 3, "JC-corner", 100.0, 5.0),
    ("OTB", 1, "OTB-on", 130.0, 0.0),
]

#: The same along the cable drawn from (100 50): each ``m`` becomes 150 - m, and the list is in that order.
REVERSED = [
    ("OTB", 1, "OTB-on", 20.0, 0.0),
    ("Joint Closures", 3, "JC-corner", 50.0, 5.0),
    ("TB", 1, "TB:1", 60.0, 1.0),
    ("Outdoor TO", 1, "Outdoor TO:1", 80.0, 2.0),
    ("Joint Closures", 1, "JC-A", 110.0, 3.0),
    ("Joint Closures", 4, "JC-before", 150.0, 5.0),
]


def _short(found):
    """Each candidate the search found, as ``(layer, fid, name, m, distance)``, in the order it gave them."""
    assert isinstance(found, list), "the search answered %r, not a list of candidates" % (found,)
    return [(c["layer_name"], c["fid"], c["naziv"], c["m"], c["distance"]) for c in found]


def _near(rows):
    """``rows`` with each float compared to within 1e-9 (pytest.approx over a list compares a tuple in it exactly)."""
    return [tuple(pytest.approx(v, abs=1e-9) if isinstance(v, float) else v for v in row) for row in rows]


def _ways(plugin, layer, feature, **kwargs):
    """The plugin's answers for the cable: searched afresh, and through an index of the placing elements, as the list
    of latent elements searches when it lists more than three cables."""
    return {
        "fresh": plugin._find_candidate_elements_for_cable(layer, feature, **kwargs),
        "indexed": plugin._find_candidate_elements_for_cable(layer, feature, elements=PlacingElementIndex(), **kwargs),
    }


def _both(plugin, layer, feature, **kwargs):
    """The plugin's answer (DataManager's search) and the answer of RelationsManager's own copy."""
    return (plugin._find_candidate_elements_for_cable(layer, feature, **kwargs),
            RelationsManager(None).find_candidate_elements_for_cable(layer, feature, **kwargs))


# ---------------------------------------------------------------------------
# The search the plugin runs
# ---------------------------------------------------------------------------

def test_the_candidates_along_a_cable_are_the_ones_worked_out_by_hand(project, plugin):
    """Afresh and through the index alike; each candidate carries the id of the layer it was found in."""
    layer, feature = _street(project)
    for way, found in _ways(plugin, layer, feature).items():
        assert _short(found) == _near(EXPECTED), way
        assert [c["layer_id"] for c in found] == [project.mapLayersByName(c["layer_name"])[0].id() for c in found], way


def test_m_is_measured_from_the_cables_first_vertex(project, plugin):
    layer, feature = _street(project, cable="LineString (100 50, 100 0, 0 0)")
    for way, found in _ways(plugin, layer, feature).items():
        assert _short(found) == _near(REVERSED), way


def test_the_tolerance_keeps_an_element_exactly_that_far(project, plugin):
    """An element further than the tolerance is dropped and one exactly that far kept: TB:1 at 1 m, OTB-on at 0 m,
    and at 6 m JC-far and TO-beyond, both exactly 6 m off."""
    layer, feature = _street(project)
    wanted = {
        1.0: ["TB:1", "OTB-on"],
        0.0: ["OTB-on"],
        6.0: ["JC-before", "JC-A", "JC-far", "Outdoor TO:1", "TB:1", "JC-corner", "OTB-on", "TO-beyond"],
    }
    for tol, names in wanted.items():
        for way, found in _ways(plugin, layer, feature, tol=tol).items():
            assert [row[2] for row in _short(found)] == names, (tol, way)


def test_first_stops_at_the_first_candidate_the_scan_meets(project, plugin):
    """What the Edit button asks. The scan takes the layers in mapLayers() order, which is by id and so puts Joint
    Closures before the other placing layers, and each layer's elements in fid order: JC-A."""
    layer, feature = _street(project)
    for way, found in _ways(plugin, layer, feature, first=True).items():
        assert _short(found) == _near([EXPECTED[1]]), way


def test_a_multipart_cable_measures_m_along_its_parts(project, plugin):
    """The gap between the parts is not cable: (250 2) lies at m 150, and (150 1) is 50 m from both parts."""
    layer, feature = _cable(project, "MultiLineString ((0 0, 100 0), (200 0, 300 0))", uri="MultiLineString")
    _points(project, "ODF", [
        ("Point (250 2)", {"naziv": "ODF-250"}),
        ("Point (10 2)", {"naziv": "ODF-10"}),
        ("Point (150 1)", {"naziv": "ODF-gap"}),
    ])
    for way, found in _ways(plugin, layer, feature).items():
        assert [row[2:] for row in _short(found)] == _near([("ODF-10", 10.0, 2.0), ("ODF-250", 150.0, 2.0)]), way


# ---------------------------------------------------------------------------
# The plugin's search and RelationsManager's own copy
# ---------------------------------------------------------------------------

def test_a_cable_with_no_geometry_has_no_candidates(project, plugin):
    layer, feature = _cable(project, None)
    _points(project, "ODF", [("Point (0 0)", {"naziv": "ODF-0"})])
    plugins, own = _both(plugin, layer, feature)
    assert (plugins, own) == ([], [])


def test_the_two_copies_agree_on_the_placing_layers(project, plugin):
    """The street without TB and the layers that are not placing elements; with ``first=True`` both answer that
    there is a candidate (the own copy ignores ``first``)."""
    layer, feature = _street(project, tb=False, others=False)
    plugins, own = _both(plugin, layer, feature)
    assert _short(own) == _short(plugins) == _near([row for row in EXPECTED if row[0] != "TB"])
    plugins, own = _both(plugin, layer, feature, first=True)
    assert _short(plugins) != [] and _short(own) != []


@pytest.mark.xfail(strict=True, raises=CopiesDisagree,
                   reason="WP5-FU-43: the two copies of the candidate search disagree: RelationsManager's own takes "
                          "poles and every point layer with a naziv field, DataManager's only the placing-element "
                          "layers; the v1.8.0 fix removes this marker")
@pytest.mark.parametrize("name, field, value, plugins_answer, own_answer", [
    pytest.param("Poles", "tip", "wood", [], [("Poles", 1, "Poles:1", 50.0, 0.0)], id="a pole"),
    pytest.param("Addresses", "naziv", "Main St 5", [], [("Addresses", 1, "Main St 5", 50.0, 0.0)],
                 id="any point layer with naziv"),
    pytest.param("TB", "oznaka", "TB-x", [("TB", 1, "TB:1", 50.0, 0.0)], [], id="a placing layer with no naziv field"),
])
def test_the_two_copies_agree_on_any_point_layer(project, plugin, name, field, value, plugins_answer, own_answer):
    """One point on the cable, in a layer the two copies treat differently. The plugin's answer is the premise: it
    takes the placing-element layers, and only them, whether they have a naziv field or not (Issue #5)."""
    layer, feature = _cable(project, "LineString (0 0, 100 0)")
    _points(project, name, [("Point (50 0)", {field: value})], fields=(field,))
    plugins, own = _both(plugin, layer, feature)
    assert _short(plugins) == _near(plugins_answer), "premise: the plugin's search takes the placing layers only"
    if _short(own) != _short(plugins):
        # WP5-FU-43's difference and nothing else: the own copy's answer, worked out by hand.
        assert _short(own) == _near(own_answer), "%s: the own copy found %s" % (name, _short(own))
        raise CopiesDisagree("%s: the plugin's search found %s, the own copy %s" % (name, _short(plugins), _short(own)))


# ---------------------------------------------------------------------------
# Elements that are not single named points
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, raises=MultiPointMisplaced,
                   reason="WP5-FU-44: a MultiPoint element is listed first, at m -1, wherever it lies along the "
                          "cable, since lineLocatePoint answers -1 for it; the v1.8.0 fix removes this marker")
def test_a_multipoint_element_takes_its_place_along_the_cable(project, plugin):
    """A closure in a MultiPoint layer, 40 m along the cable, comes after the ODF 10 m along it."""
    layer, feature = _cable(project, "LineString (0 0, 100 0)")
    _points(project, "Joint Closures", [("MultiPoint ((40 3))", {"naziv": "MP-40"})], uri="MultiPoint")
    _points(project, "ODF", [("Point (10 2)", {"naziv": "ODF-10"})])
    found = {way: _short(cands) for way, cands in _ways(plugin, layer, feature).items()}
    for way, listed in found.items():
        assert [row for row in listed if row[2] == "ODF-10"] == _near([("ODF", 1, "ODF-10", 10.0, 2.0)]), (
            "premise: " + way)
        assert [row[2] for row in listed].count("MP-40") == 1, "premise: the closure is listed once (%s): %s" % (
            way, listed)
    wrong = {way: listed for way, listed in found.items()
             if listed != _near([("ODF", 1, "ODF-10", 10.0, 2.0), ("Joint Closures", 1, "MP-40", 40.0, 3.0)])}
    for way, listed in wrong.items():
        # WP5-FU-44's effect and nothing else, in every way that is wrong: the closure first, at m -1, 3 m away.
        assert listed == _near([("Joint Closures", 1, "MP-40", -1.0, 3.0), ("ODF", 1, "ODF-10", 10.0, 2.0)]), (
            "%s: %s" % (way, listed))
    if wrong:
        raise MultiPointMisplaced("; ".join("%s: %s" % item for item in wrong.items()))


@pytest.mark.xfail(strict=True, raises=OwnEndListed,
                   reason="WP5-FU-45: a cable's own unnamed ends are listed among its candidates: Lay cable names an "
                          "unnamed end '<layer>:<fid>', as the search names an unnamed candidate, but the search "
                          "leaves out only an end with a name; the v1.8.0 fix removes this marker")
def test_a_cables_unnamed_ends_are_not_its_candidates(project, plugin):
    """Lay cable writes "ODF:1" and "Outdoor TO:1" as the ends of a cable between these two unnamed elements."""
    layer, feature = _cable(project, "LineString (0 0, 100 0)", "ODF:1", "Outdoor TO:1")
    _points(project, "ODF", [("Point (0 0)", {})])
    _points(project, "Outdoor TO", [("Point (100 0)", {})])
    _points(project, "Joint Closures", [("Point (50 1)", {"naziv": "JC-50"})])
    found = {way: _short(cands) for way, cands in _ways(plugin, layer, feature).items()}
    for way, listed in found.items():
        assert [row for row in listed if row[2] == "JC-50"] == _near([("Joint Closures", 1, "JC-50", 50.0, 1.0)]), (
            "premise: the closure along the cable is listed (%s): %s" % (way, listed))
    wrong = {way: listed for way, listed in found.items()
             if listed != _near([("Joint Closures", 1, "JC-50", 50.0, 1.0)])}
    for way, listed in wrong.items():
        # WP5-FU-45's effect and nothing else, in every way that is wrong: both unnamed ends listed, at their ends.
        assert listed == _near([("ODF", 1, "ODF:1", 0.0, 0.0), ("Joint Closures", 1, "JC-50", 50.0, 1.0),
                                ("Outdoor TO", 1, "Outdoor TO:1", 100.0, 0.0)]), "%s: %s" % (way, listed)
    if wrong:
        raise OwnEndListed("; ".join("%s: %s" % item for item in wrong.items()))


def _geopackage_layer(project, path, uri, name, rows, fields):
    """A table of the GeoPackage at ``path``, written from a memory layer and read back through OGR, so that a NULL
    comes back as OGR hands it out, not as a memory layer's None. It is added to the project: QGIS 3.22 crashes at
    exit when a failed test's traceback keeps a valid OGR layer alive that no project owns."""
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    if path.exists():
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    source = memory_layer(None, uri, name, rows, fields)
    written = QgsVectorFileWriter.writeAsVectorFormatV3(source, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    layer = QgsVectorLayer("%s|layername=%s" % (path, name), name, "ogr")
    assert layer.isValid(), "OGR cannot read the table %r of %s" % (name, path)
    assert project.addMapLayer(layer) is not None
    return layer


@pytest.mark.xfail(Qgis.QGIS_VERSION_INT < 40000, strict=True, raises=NullNamedNull,
                   reason="WP5-FU-45: on QGIS 3 a NULL name read from a GeoPackage is the text 'NULL', so along a "
                          "cable whose end Lay cable named 'NULL' an unnamed element is dropped as that end; the "
                          "v1.8.0 fix removes this marker")
def test_an_unnamed_element_in_a_geopackage_is_listed_by_layer_and_fid(project, plugin, qgis_canvas, tmp_path):
    """A cable whose ends are named "NULL", as Lay cable names an end with a NULL name on QGIS 3, and a closure with
    a NULL name 30 m along it. The layers leave the project before the canvas may render again."""
    path = tmp_path / "street.gpkg"
    with canvas_not_rendering(qgis_canvas):
        try:
            layer = _geopackage_layer(project, path, "LineString", "Underground cables",
                                      [("LineString (0 0, 100 0)", {"od": "NULL", "do": "NULL"})], ("od", "do"))
            closures = _geopackage_layer(project, path, "Point", "Joint Closures",
                                         [("Point (30 1)", {}), ("Point (80 1)", {"naziv": "JC-80"})], ("naziv",))
            names = [feature["naziv"] for feature in closures.getFeatures()]
            points = [feature.geometry().asWkt(0) for feature in closures.getFeatures()]
            found = {way: _short(cands) for way, cands in _ways(plugin, layer, next(layer.getFeatures())).items()}
        finally:
            project.removeAllMapLayers()
    assert [is_null(name) for name in names] == [True, False], "premise: the first closure's name is NULL: %r" % names
    assert points == ["Point (30 1)", "Point (80 1)"], "premise: the closures lie 30 and 80 m along the cable: %r" % (
        points,)
    for way, listed in found.items():
        assert [row for row in listed if row[2] == "JC-80"] == _near([("Joint Closures", 2, "JC-80", 80.0, 1.0)]), (
            "premise: " + way)
    wrong = {way: listed for way, listed in found.items()
             if listed != _near([("Joint Closures", 1, "Joint Closures:1", 30.0, 1.0),
                                 ("Joint Closures", 2, "JC-80", 80.0, 1.0)])}
    for way, listed in wrong.items():
        # WP5-FU-45's effect on QGIS 3 and nothing else, in every way that is wrong: the unnamed closure dropped.
        assert listed == _near([("Joint Closures", 2, "JC-80", 80.0, 1.0)]), "%s: %s" % (way, listed)
    if wrong:
        raise NullNamedNull("; ".join("%s: %s" % item for item in wrong.items()))


# ---------------------------------------------------------------------------
# Relations and the two stores
# ---------------------------------------------------------------------------

#: Two relations that both list the cable L1:3. A fid may be stored as text.
RELATIONS = {"relations": [
    {"id": "r-a", "name": "Feeder A", "cables": [{"layer_id": "L1", "fid": 3}, {"layer_id": "L1", "fid": "4"}]},
    {"id": "r-b", "name": "Feeder B", "cables": [{"layer_id": "L2", "fid": 3}, {"layer_id": "L1", "fid": 3}]},
]}


def test_each_cable_is_named_by_the_last_relation_that_lists_it(project, plugin):
    """L1:3 is in both relations; the later one names it, as the Relations dialog shows."""
    assert plugin._save_relations(RELATIONS)
    assert plugin._relation_name_by_cable() == {("L1", 3): "Feeder B", ("L1", 4): "Feeder A", ("L2", 3): "Feeder B"}


def test_a_relation_is_found_by_id_as_the_dict_the_dialog_edits(project, plugin):
    """The Relations dialog adds cables to the dict it gets back and then saves the whole store, so it must be the
    dict in the store, not a copy."""
    data = {"relations": [dict(relation) for relation in RELATIONS["relations"]]}
    assert plugin._relation_by_id(data, "r-b") is data["relations"][1]
    assert plugin._relation_by_id(data, "r-missing") is None
    assert plugin._cable_key("L1", "4") == "L1:4"


def test_the_two_copies_read_and_name_relations_alike(project, plugin):
    """What either copy writes, the other reads back; both name each cable by the same relation, find the same
    relation by id, and key a cable alike."""
    own = RelationsManager(None)
    assert own.save_relations(RELATIONS)
    assert plugin._load_relations() == RELATIONS
    assert own.get_relation_name_by_cable() == plugin._relation_name_by_cable()
    swapped = {"relations": RELATIONS["relations"][::-1]}
    assert plugin._save_relations(swapped)
    assert own.load_relations() == swapped
    assert own.get_relation_name_by_cable() == plugin._relation_name_by_cable()
    for rid, stored in (("r-a", swapped["relations"][1]), ("r-b", swapped["relations"][0]), ("r-missing", None)):
        assert own.get_relation_by_id(swapped, rid) is plugin._relation_by_id(swapped, rid) is stored, rid
    latent = {"cables": {"L1:3": {"elements": [{"layer_id": "J", "fid": 1, "naziv": "JC-A", "latent": True}]}}}
    assert plugin._save_latent(latent)
    assert own.load_latent() == latent
    latent = {"cables": {"L2:3": {"elements": [{"layer_id": "J", "fid": 2, "naziv": "JC-B", "latent": False}]}}}
    assert own.save_latent(latent)
    assert plugin._load_latent() == latent
    assert own.cable_key("L1", 3) == plugin._cable_key("L1", 3) == "L1:3"
