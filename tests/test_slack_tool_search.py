"""The slack tool finds the cable it is pointed at, whatever else is in the layer.

``SlackPlaceTool`` answers every click and every mouse move by searching the
cable layers for an end within the snap tolerance, then for a cable passing
within it, and the pole and manhole layers for the nearest node. Four kinds of
feature broke those searches for every OTHER cable in the project:

* **A multipart cable.** ``asPolyline()`` raises ``TypeError`` on a
  MultiLineString instead of answering an empty list, so the
  ``asMultiPolyline()`` fallback after it could never run (FU-10's last
  unfixed site). A shapefile reads back as MultiLineString even when every
  feature is one plain line, so one imported layer was enough: no slack could
  be placed anywhere, and the mouse-move preview -- a Qt slot nothing wraps --
  raised on every move.
* **A cable with no geometry** (QGIS creates one whenever a row is added
  without digitising) raised ``ValueError`` from the same call, and an empty
  one ``TypeError`` from the fallback.
* **A one-vertex cable.** GEOS cannot measure it and answers -1, and -1 is
  "within the tolerance" of every click, so it became the cable of every
  mid-span slack wherever it was. A multipart cable whose only part has one
  vertex measures 0.0 from everywhere, with the same result.
* **A cable with a broken part or vertex** -- a one-vertex part beside a real
  line, a vertex that is not a number. GEOS measured it through its other
  parts, so it could still be picked, although a GeoPackage does not return
  it to a box query at all and its length is NaN when a vertex is.
* **An arc through three points in a row.** QGIS boxes it from a circle it
  does not have, (-1, -1, 100, 0) for ``CircularString (0 0, 200 0, 100 0)``,
  while GEOS measures it out to x = 200.
* **A node with no position.** A pole at NaN met first made ``best`` NaN, and
  ``d < NaN`` is never true, so it decided "Pole" or "Manhole" for every slack.

Now each part of a multipart cable offers its own two ends; a cable that is
not a valid line -- every part two or more vertices, every vertex a real
number, a curve inside its own box -- is skipped by both cable searches; a
node whose point is not finite is skipped. Every test here but the one
marked as pinning fails on the parent commit.
"""
import math

import pytest
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

from fiberq.tools.slack_tool import SlackPlaceTool

#: 20 px at 0.5 m/px, as the tool computes it.
TOLERANCE = 10.0


class _Canvas:
    def mapUnitsPerPixel(self):
        return TOLERANCE / 20


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


def _layer(project, uri, name, geometries):
    layer = QgsVectorLayer(uri, name, "memory")
    features = []
    for geom in geometries:
        feat = QgsFeature(layer.fields())
        if geom is not None:
            feat.setGeometry(geom)
        features.append(feat)
    ok, _added = layer.dataProvider().addFeatures(features)
    assert ok
    project.addMapLayer(layer)
    return layer


def _tool():
    tool = SlackPlaceTool.__new__(SlackPlaceTool)
    tool.iface = None
    tool.plugin = None
    tool.canvas = _Canvas()
    tool.params = {}
    return tool


def _found(result):
    layer, feat, side, place = result
    if layer is None:
        return None
    return layer.name(), int(feat.id()), side, (round(place.x(), 6), round(place.y(), 6))


def test_a_multipart_cable_offers_the_ends_of_each_part(project):
    cables = _layer(project, "MultiLineString?crs=EPSG:3857", "Underground cables",
                    [QgsGeometry.fromWkt("MultiLineString ((0 0, 50 0), (60 0, 100 0))")])
    fid = next(cables.getFeatures()).id()
    tool = _tool()

    assert _found(tool._resolve(QgsPointXY(1, 1))) == ("Underground cables", fid, "od", (0.0, 0.0))
    assert _found(tool._resolve(QgsPointXY(99, -1))) == ("Underground cables", fid, "do", (100.0, 0.0))
    assert _found(tool._resolve(QgsPointXY(59, 2))) == ("Underground cables", fid, "od", (60.0, 0.0))


def test_one_multipart_cable_does_not_stop_the_tool_finding_any_other(project):
    _layer(project, "MultiLineString?crs=EPSG:3857", "Aerial cables",
           [QgsGeometry.fromWkt("MultiLineString ((5000 5000, 5100 5000))")])
    near = _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
                  [QgsGeometry.fromWkt("LineString (0 0, 100 0)")])
    fid = next(near.getFeatures()).id()

    assert _found(_tool()._resolve(QgsPointXY(2, 0))) == ("Underground cables", fid, "od", (0.0, 0.0))


@pytest.mark.parametrize("broken", [None, "LineString EMPTY"], ids=["no geometry", "empty"])
def test_a_cable_with_no_line_does_not_stop_the_tool(project, broken):
    geoms = [QgsGeometry.fromWkt(broken) if broken else None,
             QgsGeometry.fromWkt("LineString (0 0, 100 0)")]
    cables = _layer(project, "LineString?crs=EPSG:3857", "Underground cables", geoms)
    good = max(f.id() for f in cables.getFeatures())
    tool = _tool()

    assert _found(tool._resolve(QgsPointXY(100, 3))) == ("Underground cables", good, "do", (100.0, 0.0))
    # mid-span: the empty line measures 0.0 from everything and used to win here
    assert _found(tool._resolve(QgsPointXY(50, 4))) == ("Underground cables", good, "sredina", (50.0, 0.0))


@pytest.mark.parametrize("kind, lone", [
    ("LineString", "LineString (9000 9000)"),               # GEOS: -1
    ("MultiLineString", "MultiLineString ((9000 9000))"),   # GEOS: 0.0
], ids=["one-vertex line", "one-vertex multipart"])
def test_a_one_vertex_cable_does_not_take_every_mid_span_click(project, kind, lone):
    cables = _layer(project, f"{kind}?crs=EPSG:3857", "Underground cables",
                    [QgsGeometry.fromWkt(lone),
                     QgsGeometry.fromWkt(lone.replace("9000 9000", "0 0, 100 0"))])
    good = max(f.id() for f in cables.getFeatures())

    assert _found(_tool()._resolve(QgsPointXY(50, 4))) == ("Underground cables", good, "sredina", (50.0, 0.0))


@pytest.mark.parametrize("broken", [
    [[(5000, 5000)], [(0, 0), (100, 0)]],
    [[(math.nan, math.nan), (0, 0), (100, 0)]],
    [[(0, 0), (100, 0)], [(math.nan, math.nan), (math.nan, math.nan)]],
], ids=["one-vertex part beside a line", "nan first vertex", "nan part after a line"])
def test_a_cable_with_a_broken_part_or_vertex_is_not_a_cable(project, broken):
    """The broken cable is the nearer one, and the valid cable 6 m away gets the slack."""
    parts = [[QgsPointXY(x, y) for x, y in part] for part in broken]
    cables = _layer(project, "MultiLineString?crs=EPSG:3857", "Underground cables",
                    [QgsGeometry.fromMultiPolylineXY(parts),
                     QgsGeometry.fromWkt("MultiLineString ((0 6, 100 6))")])
    good = max(f.id() for f in cables.getFeatures())
    tool = _tool()

    assert _found(tool._resolve(QgsPointXY(100, 1))) == ("Underground cables", good, "do", (100.0, 6.0))
    assert _found(tool._resolve(QgsPointXY(50, 1))) == ("Underground cables", good, "sredina", (50.0, 6.0))


def test_a_node_with_no_position_does_not_decide_the_location(project):
    # Layer ids start with the name, and QgsProject.mapLayers() is ordered by
    # id, so the manhole layer is searched first and its NaN point met first.
    _layer(project, "Point?crs=EPSG:3857", "Manholes",
           [QgsGeometry.fromPointXY(QgsPointXY(math.nan, math.nan))])
    poles = _layer(project, "Point?crs=EPSG:3857", "Poles",
                   [QgsGeometry.fromPointXY(QgsPointXY(3, 4))])
    layer, feat, distance = _tool()._nearest_node(QgsPointXY(0, 0))

    assert (layer.name(), feat.id(), distance) == ("Poles", next(poles.getFeatures()).id(), 5.0)


def test_only_unusable_nodes_means_no_node(project):
    _layer(project, "Point?crs=EPSG:3857", "Poles",
           [QgsGeometry.fromPointXY(QgsPointXY(math.nan, 0)),
            QgsGeometry.fromPointXY(QgsPointXY(math.inf, 0)),
            None])

    assert _tool()._nearest_node(QgsPointXY(0, 0)) == (None, None, None)


@pytest.mark.parametrize("arc", [
    "CircularString (0 0, 200 0, 100 0)",
    "CompoundCurve ((-50 0, 0 0), CircularString (0 0, 200 0, 100 0))",
    "MultiCurve (CircularString (0 0, 200 0, 100 0))",
], ids=["arc", "inside a compound curve", "inside a multicurve"])
def test_an_arc_through_three_points_in_a_row_is_not_a_cable(project, arc):
    """GEOS measures this arc out to x = 200; QGIS boxes it from a centre it never set."""
    cables = _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
                    [QgsGeometry.fromWkt(arc), QgsGeometry.fromWkt("LineString (0 6, 300 6)")])
    good = max(f.id() for f in cables.getFeatures())

    for _ in range(20):   # the box comes from memory nobody set; one draw is not enough
        assert _found(_tool()._resolve(QgsPointXY(180, 1))) == (
            "Underground cables", good, "sredina", (180.0, 6.0))


@pytest.mark.parametrize("parts", [[[], [(0, 0), (100, 0)]], [[(0, 0), (100, 0)], []]],
                         ids=["empty part first", "empty part last"])
def test_a_cable_with_an_empty_part_is_still_a_cable(project, parts):
    """An empty part is no part: GEOS and every box leave it out (a GeoJSON MultiLineString can carry one)."""
    cables = _layer(project, "MultiLineString?crs=EPSG:3857", "Underground cables",
                    [QgsGeometry.fromMultiPolylineXY([[QgsPointXY(x, y) for x, y in part] for part in parts])])
    fid = next(cables.getFeatures()).id()
    tool = _tool()

    assert _found(tool._resolve(QgsPointXY(99, 1))) == ("Underground cables", fid, "do", (100.0, 0.0))
    assert _found(tool._resolve(QgsPointXY(50, 3))) == ("Underground cables", fid, "sredina", (50.0, 0.0))


def test_a_proper_arc_is_still_a_cable(project):
    """Pins what the parent did: an arc whose box holds its line is found along it."""
    cables = _layer(project, "LineString?crs=EPSG:3857", "Underground cables",
                    [QgsGeometry.fromWkt("CircularString (0 0, 100 100, 200 0)")])
    arc = next(cables.getFeatures()).id()

    layer, fid, side, _place = _found(_tool()._resolve(QgsPointXY(100, 98)))
    assert (layer, fid, side) == ("Underground cables", arc, "sredina")
    assert _found(_tool()._resolve(QgsPointXY(199, 1)))[:3] == ("Underground cables", arc, "do")
