"""What a placement snap no longer repeats on every mouse move.

Found in the v1.6.0 QA (finding Q12): on memory layers -- every layer of a new
scratch project -- one joint-closure mouse move cost 0.30 ms on QGIS 3.40.15
where v1.5.0 took 0.09 ms. Two thirds of it was work done again on every move
for nothing:

* ``QgsSnapIndicator.setMatch`` with the match it was already showing: on QGIS 3
  it reads the snap colour from the settings and places the marker and its
  tooltip afresh, ~55 us a call (2 us on 4.2.3);
* Python wrappers QGIS built and threw away on every move -- the project's
  layers, a memory layer's provider, the canvas' snapping utils -- ~9 to 16 us
  each while no wrapper is alive, ~0.15 us while one is;
* the full walk of ``held_by_its_box`` for a plain line, whose answer for one
  part and no arc is the first check alone.

Each test pins one of them, so the cost cannot come back unseen; the snapping
tests elsewhere pin that every answer stayed the same.
"""
import math

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsLineString, QgsPoint,
                       QgsPointLocator, QgsPointXY, QgsProject, QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsMapCanvas

from fiberq.tools.base import PlacementSnapper, SNAP_NODE_LAYERS, SNAP_ROUTE_LAYERS, no_match, snap_match
from fiberq.utils import geometry as geometry_module
from fiberq.utils import spatial
from fiberq.utils.geometry import held_by_its_box


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


def _memory(project, kind, name, geometries):
    layer = QgsVectorLayer(f"{kind}?crs=EPSG:3857&field=naziv:string", name, "memory")
    features = []
    for geometry in geometries:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    project.addMapLayer(layer)
    return layer


def _canvas(layers):
    canvas = QgsMapCanvas()
    canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    canvas.resize(400, 400)
    canvas.show()
    canvas.setLayers(list(layers))
    canvas.setExtent(QgsRectangle(-100, -100, 300, 300))
    return canvas


class _CountingIndicator:
    """The snapper's indicator, counting what reaches ``setMatch``."""

    def __init__(self, real):
        self.real = real
        self.sent = []

    def setMatch(self, match):
        self.sent.append(match)
        self.real.setMatch(match)

    def __getattr__(self, name):
        return getattr(self.real, name)


def test_the_indicator_is_not_sent_the_match_it_shows(project):
    poles = _memory(project, "Point", "Poles", [QgsGeometry.fromPointXY(QgsPointXY(0, 0))])
    canvas = _canvas([poles])
    snapper = PlacementSnapper(canvas, point_layers=SNAP_NODE_LAYERS)
    counting = _CountingIndicator(snapper.indicator)
    snapper.indicator = counting

    at_pole = snap_match(QgsPointXY(0, 0), layer=poles, fid=1, distance=0.4)
    snapper.show(at_pole)
    snapper.show(snap_match(QgsPointXY(0, 0), layer=poles, fid=1, distance=0.9))
    assert len(counting.sent) == 1, "the same vertex, a different cursor: nothing new to show"
    assert counting.real.isVisible()

    snapper.show(snap_match(QgsPointXY(0, 0), layer=poles, fid=1, on_edge=True))
    snapper.show(snap_match(QgsPointXY(5, 0), layer=poles, fid=1))
    snapper.clear()
    snapper.clear()
    assert len(counting.sent) == 4, "a new kind, a new place and a clear are each shown, once"
    assert not counting.real.isVisible()


def test_another_layer_at_the_same_place_is_shown(project):
    """A pole and a manhole numbered alike can sit on one vertex: the marker is the
    same, the tooltip naming the layer is not."""
    poles = _memory(project, "Point", "Poles", [QgsGeometry.fromPointXY(QgsPointXY(0, 0))])
    manholes = _memory(project, "Point", "Manholes", [QgsGeometry.fromPointXY(QgsPointXY(0, 0))])
    canvas = _canvas([poles, manholes])
    snapper = PlacementSnapper(canvas, point_layers=SNAP_NODE_LAYERS)
    counting = _CountingIndicator(snapper.indicator)
    snapper.indicator = counting

    snapper.show(snap_match(QgsPointXY(0, 0), layer=poles, fid=1))
    snapper.show(snap_match(QgsPointXY(0, 0), layer=manholes, fid=1))
    assert len(counting.sent) == 2
    assert counting.real.match().layer().id() == manholes.id()


def test_a_snap_keeps_the_wrappers_it_asks_for_alive(project):
    """Kept, never used: each move still asks the project, the layer and the canvas."""
    route = _memory(project, "LineString", "Route", [QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(100, 0)])])
    poles = _memory(project, "Point", "Poles", [QgsGeometry.fromPointXY(QgsPointXY(100, 0))])
    canvas = _canvas([route, poles])
    snapper = PlacementSnapper(canvas, point_layers=SNAP_NODE_LAYERS, line_layers=SNAP_ROUTE_LAYERS)

    assert snapper._fallback(QgsPointXY(99.5, 0.5)).isValid()
    snapper.qgis_snapping_on()

    assert {layer.id() for layer in snapper._alive_layers} == {route.id(), poles.id()}
    assert snapper._alive_utils is canvas.snappingUtils()
    assert spatial._PROVIDERS[route.id()] is route.dataProvider()
    assert spatial._PROVIDERS[poles.id()] is poles.dataProvider()


def test_a_replaced_provider_is_the_one_asked(project, tmp_path):
    """What is kept alive is never what is used: a layer given a new data source is
    asked through the new provider, which has an index the old one did not."""
    poles = _memory(project, "Point", "Poles", [QgsGeometry.fromPointXY(QgsPointXY(0, 0))])
    assert spatial.features_within(poles, QgsPointXY(0, 0), 5) is not None
    kept = spatial._PROVIDERS[poles.id()]
    other = QgsVectorLayer("Point?crs=EPSG:3857&field=naziv:string", "spare", "memory")
    poles.setDataSource(other.source(), "Poles", "memory")
    assert poles.dataProvider().createSpatialIndex()
    assert spatial.features_within(poles, QgsPointXY(0, 0), 5) is None
    assert spatial._PROVIDERS[poles.id()] is not kept


def _lines():
    """Plain lines, and every coordinate held_by_its_box has a rule for."""
    shapes = []
    for coordinates in ([(0, 0), (10, 0)], [(0, 0), (5, 5), (10, 0)],
                        [(1e10, -1e10), (1e10 + 3, -1e10 + 4)], [(0, 0)]):
        shapes.append(QgsLineString([QgsPoint(x, y) for x, y in coordinates]))
    for bad in (math.nan, math.inf, -math.inf):
        for position in range(3):
            points = [QgsPoint(0, 0), QgsPoint(5, 5), QgsPoint(10, 0)]
            points[position] = QgsPoint(bad, 5) if position % 2 else QgsPoint(5, bad)
            shapes.append(QgsLineString(points))
    z = QgsLineString([QgsPoint(0, 0, 3), QgsPoint(10, 0, 4)])
    zm = QgsLineString([QgsPoint(0, 0, 3, 7), QgsPoint(10, 0, 4, 8)])
    shapes += [z, zm]
    return [QgsGeometry(shape) for shape in shapes]


@pytest.mark.parametrize("slack", [0.0, 0.5])
def test_the_plain_line_shortcut_answers_as_the_walk_does(qgis_app, slack):
    """``held_by_its_box`` answers a one-part line without the walk; with the
    shortcut taken away, every line gets the walk's answer, and it is the same."""
    lines = _lines()
    quick = [held_by_its_box(line, slack) for line in lines]

    class NoLineString:
        pass

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(geometry_module, "QgsLineString", NoLineString)
        walked = [held_by_its_box(line, slack) for line in lines]
    assert quick == walked
    assert quick[0] and not all(quick), "premise: the lines hold some and turn some away"


def test_no_match_is_shown_as_nothing(qgis_app):
    """The key ``show`` compares: a cleared indicator and an invalid match agree."""
    from fiberq.tools.base import _shown_as
    assert _shown_as(no_match()) is None
    assert _shown_as(QgsPointLocator.Match()) is None
