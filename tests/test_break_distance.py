"""The recorded break distance, and the identity of an imported point.

WP4 FU-2 item U16. Unclaimed: small bug fixes shipping in v1.6.0.

**The break distance.** ``closestSegmentWithContext`` answers four values::

    (sqrDist, closestPoint, indexOfClosestVertexAfter, leftOf)

and ``fiber_break`` unpacked the **fourth** as the segment index::

    _, snapped_pt, _, seg_index = geom.closestSegmentWithContext(map_pt)

``leftOf`` is ``-1`` or ``+1`` -- which side of the line the click is on.
Measured on 3.44.15 and 4.0.3 against a four-vertex line: a click near the
third segment answers ``indexOfClosestVertexAfter = 3`` and ``leftOf = -1`` or
``+1`` depending only on which side the cursor was.

Downstream, ``-1`` was clamped to ``0`` and ``+1`` was used as-is, so the
distance along the cable was measured from the wrong vertex for every click
except one on the first segment -- and it **changed for the same break**
depending on which side of the cable the user clicked. That value is what a
splicing crew drives to.

**The identity.** ``import_points`` stamped no ``fiberq_uuid``, so WP2's B4
validation rule reported every imported point as missing its identity. It
looked as though it fixed itself on reopening, because the uuid migration runs
on project load -- which is exactly the kind of "it goes away if you restart"
that never gets reported.

The third item on U16's list, the mid-span slack storing the raw click point
instead of a point on the cable, was already fixed by U2 on branch 4: see
``SlackPlaceTool._resolve``, which projects onto the segment and says so. One
test here pins that, so the two halves cannot drift apart.
"""
import json
import os

import pytest
from qgis.core import (
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.models.schema import IDENTITY_FIELD


class FakeBar:
    def __init__(self):
        self.warnings = []
        self.infos = []

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushInfo(self, title, text):
        self.infos.append(text)


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None

    def mapCanvas(self):
        return self


@pytest.fixture(autouse=True)
def quiet_dialogs(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


#: A BENT four-vertex cable: (0,0) -> (10,0) -> (10,10) -> (20,10).
#: Each leg is 10 m, so the cable is 30 m long.
#:
#: The bend is the whole point. On a straight cable, measuring from the first
#: vertex straight to the break gives the same answer as walking the segments,
#: so a straight cable cannot tell the defect from the fix -- a first draft of
#: these tests used one and passed against the unfixed code. With the bend, a
#: break 15 m along the cable sits at (10,5): walking the segments gives 15 m,
#: while the straight line from (0,0) gives sqrt(100+25) = 11.18 m.
VERTICES = [QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(20, 10)]


class Planar:
    """Stands in for QgsDistanceArea: plain cartesian metres."""

    @staticmethod
    def measureLine(a, b):
        return float(((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5)


# ---------------------------------------------------------------------------
# The call's contract
# ---------------------------------------------------------------------------

def test_closest_segment_returns_left_of_last_not_the_index(qgis_app):
    """The mistake, pinned: the fourth value is a SIDE, not an index."""
    line = QgsGeometry.fromPolylineXY(VERTICES)
    # (15, 11) is nearest the third leg, from vertex 2 to vertex 3.
    _sqr, _pt, index_after, left_of = line.closestSegmentWithContext(QgsPointXY(15, 11))
    assert index_after == 3, "the closest segment runs from vertex 2 to vertex 3"
    assert left_of in (-1, 1), "leftOf is a side, and was being used as an index"
    assert index_after != left_of


def test_left_of_flips_with_the_side_the_click_is_on(qgis_app):
    """Which is why the same break measured two different distances."""
    line = QgsGeometry.fromPolylineXY(VERTICES)
    above = line.closestSegmentWithContext(QgsPointXY(15, 14))[3]
    below = line.closestSegmentWithContext(QgsPointXY(15, 6))[3]
    assert above != below
    # ...while the real index does not.
    index_above = line.closestSegmentWithContext(QgsPointXY(15, 14))[2]
    index_below = line.closestSegmentWithContext(QgsPointXY(15, 6))[2]
    assert index_above == index_below


# ---------------------------------------------------------------------------
# The distance the tool records
# ---------------------------------------------------------------------------

def _break_tool(monkeypatch, iface):
    from fiberq.addons.fiber_break import FiberBreakTool

    tool = FiberBreakTool.__new__(FiberBreakTool)
    tool.iface = iface
    monkeypatch.setattr(tool, "_flatten_polyline", lambda g: list(VERTICES))
    monkeypatch.setattr(tool, "_measure_line", lambda pts: (30.0, Planar()))
    tool.snap_marker = _FakeMarker()
    return tool


def _cable(project):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Aerial cables", "memory")
    layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    layer.updateFields()
    from qgis.core import QgsFeature
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY(VERTICES))
    layer.startEditing()
    layer.addFeature(feat)
    layer.commitChanges()
    project.addMapLayer(layer)
    return layer


def _break_layer(project):
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "Fiber break", "memory")
    layer.dataProvider().addAttributes([
        QgsField("naziv", QVariant.String),
        QgsField("cable_layer_id", QVariant.String),
        QgsField("cable_fid", QVariant.Int),
        QgsField("distance_m", QVariant.Double),
        QgsField("segments_hit", QVariant.Int),
        QgsField("vreme", QVariant.String),
    ])
    layer.updateFields()
    project.addMapLayer(layer)
    return layer


def _record(project, monkeypatch, click):
    """Record one break at ``click`` and return the distance stored."""
    from fiberq.utils.errors import OperationErrors

    cable = _cable(project)
    breaks = _break_layer(project)
    iface = FakeIface()
    tool = _break_tool(monkeypatch, iface)
    monkeypatch.setattr(tool, "_iter_line_layers", lambda: [cable])
    monkeypatch.setattr(tool, "_ensure_break_layer", lambda: breaks)

    with OperationErrors("Fiber break", iface) as errors:
        tool._record_break(click, errors)

    assert breaks.featureCount() == 1, iface.bar.warnings
    return float(next(breaks.getFeatures())["distance_m"])


@pytest.mark.parametrize("click", [QgsPointXY(11, 5), QgsPointXY(9, 5)])
def test_the_break_distance_does_not_depend_on_which_side_was_clicked(
        project, monkeypatch, click):
    """v1.5.0 recorded a different distance for each side of the same cable.

    Both clicks are 1 m from the same point on the second leg, on opposite
    sides, so both breaks are 15 m along the cable.
    """
    assert _record(project, monkeypatch, click) == pytest.approx(15.0, abs=0.01)


@pytest.mark.parametrize("click,expected", [
    (QgsPointXY(5, 1), 5.0),        # first leg: the one case v1.5.0 got right
    (QgsPointXY(11, 5), 15.0),      # second leg, after one bend
    (QgsPointXY(15, 11), 25.0),     # third leg, after two bends
    (QgsPointXY(19, 9), 29.0),
])
def test_the_break_distance_is_measured_along_the_cable(project, monkeypatch, click, expected):
    """Walking every segment, not a straight line from an earlier vertex."""
    assert _record(project, monkeypatch, click) == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# An imported point has an identity
# ---------------------------------------------------------------------------

def _geojson(tmp_path, features):
    path = os.path.join(str(tmp_path), "pts.geojson")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection",
                   "crs": {"type": "name",
                           "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                   "features": features}, fh)
    return path


def test_an_imported_point_gets_a_uuid(project, tmp_path):
    """v1.5.0: B4 reported every one until the project was reopened."""
    from qgis.core import QgsCoordinateTransform
    from fiberq.main_plugin import FiberQPlugin
    from fiberq.utils.errors import OperationErrors

    path = _geojson(tmp_path, [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Point", "coordinates": [0.0, 0.0]}},
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Point", "coordinates": [0.001, 0.0]}},
    ])
    poles = QgsVectorLayer("Point?crs=EPSG:3857", "Poles", "memory")
    poles.dataProvider().addAttributes([
        QgsField("tip", QVariant.String),
        QgsField(IDENTITY_FIELD, QVariant.String),
    ])
    poles.updateFields()
    project.addMapLayer(poles)

    imported = QgsVectorLayer(path, "tmp", "ogr")
    assert imported.isValid()
    plugin = FiberQPlugin.__new__(FiberQPlugin)
    plugin.iface = FakeIface()
    transform = QgsCoordinateTransform(imported.crs(), poles.crs(), project)
    with OperationErrors("Import points", plugin.iface) as errors:
        added, _skipped = plugin._add_imported_points(
            imported, poles, imported.crs(), poles.crs(), transform, errors)

    assert added == 2
    uuids = [f[IDENTITY_FIELD] for f in poles.getFeatures()]
    assert all(uuids), f"every imported point needs an identity, got {uuids}"
    assert len(set(uuids)) == 2, "and they have to be distinct"


# ---------------------------------------------------------------------------
# The mid-span slack, fixed by U2 on branch 4 -- pinned so it stays fixed
# ---------------------------------------------------------------------------

def test_a_mid_span_slack_lands_on_the_cable(project, monkeypatch):
    """Not where the cursor was, which is up to the whole tolerance away."""
    from fiberq.tools.slack_tool import SlackPlaceTool

    cable = _cable(project)
    tool = SlackPlaceTool.__new__(SlackPlaceTool)
    tool.iface = FakeIface()
    tool.plugin = None
    tool.canvas = _FakeCanvas()
    tool.params = {}
    monkeypatch.setattr(tool, "_nearest_cable_endpoint",
                        lambda p, t: (None, None, None, None, None))
    monkeypatch.setattr(tool, "_nearest_cable_on_line",
                        lambda p, t: (cable, next(cable.getFeatures()), 1.0))

    # 4 m off the second leg, which runs up x=10 from y=0 to y=10.
    _layer, _feat, side, place = tool._resolve(QgsPointXY(14, 5))

    assert side == "sredina"
    assert place.x() == pytest.approx(10.0, abs=1e-6), "projected onto the cable"
    assert place.y() == pytest.approx(5.0, abs=1e-6)


class _FakeCanvas:
    @staticmethod
    def mapUnitsPerPixel():
        return 1.0


class _FakeMarker:
    def setCenter(self, point):
        self.centre = point

    def show(self):
        self.shown = True
