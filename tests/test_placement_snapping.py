"""Placement snapping: the project's configuration, and FiberQ's own fallback.

The first tests in the suite that drive real canvas events. Every placement tool
used to carry a private snap that ignored the project's snapping configuration
entirely, and three of them were wrong in ways that are reproduced below:

* the element and breakpoint tools compared a **squared** distance (what
  ``closestSegmentWithContext`` returns) against a linear tolerance, so their
  real snap radius was ``sqrt(10 / mapUnitsPerPixel)`` pixels rather than the 10
  they read as -- at one map unit per pixel, 3.16 px instead of 10;
* the same mix-up let a squared segment distance beat a linear node distance, so
  the farther of two candidates won;
* the pole and joint-closure tools matched layers by literal name against
  ``('Route', 'Route')`` and ``("Poles", "Poles", ...)`` -- a rename that
  replaced both halves of an (English, Serbian) pair -- so a route still called
  ``Trasa`` was invisible to them.

Harness notes, each of them load-bearing and each measured on 3.22 through 4.2:

* ``project.setSnappingConfig()`` alone does nothing to a bare canvas;
  ``canvas.snappingUtils().setConfig()`` is what ``snapPoint()`` reads.
* ``QgsMapMouseEvent.snapPoint()`` snaps *relaxed*, so a cold index yields no
  match at all and the first event silently fails. ``locatorForLayer().init()``
  warms it.
* ``canvas.show()`` is required, or ``resize()`` is ignored and the extent is
  stretched to the default size hint. With it the map is 798x798, not 800x800,
  so the extent is sized from ``outputSize()``.
* The ``QgsMapMouseEvent(canvas, QEvent.Type, QPoint, ...)`` constructor works on
  Qt5 and Qt6 alike; the ``QMouseEvent`` wrapper needs a ``QPointF`` on Qt6.
* ``setType(QgsSnappingConfig.SnappingType.Vertex)`` is deprecated in favour of
  ``setTypeFlag(...SnappingTypes.Vertex)`` -- and is the only spelling that works
  on all five images. ``SnappingTypes.Vertex`` is an ``AttributeError`` on 3.22,
  where the flag members sit directly on the class. Do not modernise it.
"""
import pytest

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY,
    QgsProject, QgsRectangle, QgsSnappingConfig, QgsTolerance, QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QPoint, Qt

#: The right-angle vertex every test aims at.
CORNER = QgsPointXY(100.0, 100.0)


class StubIface:
    """The three methods the manhole and slack tools touch.

    They bind ``iface.mapCanvas()`` in ``__init__``, and pytest-qgis' own canvas
    is session-scoped -- resizing it or setting its extent would leak into every
    later test.
    """

    def __init__(self, canvas):
        self._canvas = canvas

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return None

    def messageBar(self):
        return self

    def pushInfo(self, *args):
        pass

    def pushWarning(self, *args):
        pass


def add_route(name="Route"):
    """A route bending through a right angle at CORNER."""
    layer = QgsVectorLayer(
        "LineString?crs=EPSG:3857&field=naziv:string&field=tip_trase:string",
        name, "memory")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(0, 100), CORNER, QgsPointXY(100, 0)]))
    layer.dataProvider().addFeatures([feature])
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


def add_poles(name="Poles", at=QgsPointXY(60, 100)):
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=tip:string", name, "memory")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(at))
    layer.dataProvider().addFeatures([feature])
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


def unit_canvas(layers, centre=CORNER, span=None):
    """A private canvas at (about) one map unit per pixel, centred on ``centre``.

    ``span`` overrides the width in map units, for the tests that need a
    tolerance big enough to hold two candidates.
    """
    canvas = QgsMapCanvas()
    canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    canvas.resize(800, 800)
    canvas.show()
    canvas.setLayers(list(layers))
    size = canvas.mapSettings().outputSize()
    width = size.width() if span is None else span
    height = size.height() if span is None else span * size.height() / size.width()
    canvas.setExtent(QgsRectangle(centre.x() - width / 2.0, centre.y() - height / 2.0,
                                  centre.x() + width / 2.0, centre.y() + height / 2.0))
    canvas.refresh()
    if span is None:
        # Every pixel figure in this module is read as a map unit, and that only
        # holds because show() made resize() stick: without it outputSize stays
        # at the 638x478 size hint, the extent is stretched to that aspect and
        # mapUnitsPerPixel comes out 1.669 instead. The tolerance assertions
        # would still pass, while measuring something else entirely.
        assert canvas.mapUnitsPerPixel() == pytest.approx(1.0, abs=0.01)
    return canvas


def set_snapping(canvas, enabled, pixels=12, kind=None):
    """Put the magnet on or off for ``canvas``, the way QGIS itself would.

    The project is told as well as the canvas, because that is the pairing the
    running application maintains, but the canvas' own utils is the one that
    decides what ``snapPoint()`` does.
    """
    config = QgsProject.instance().snappingConfig()
    config.setEnabled(enabled)
    config.setMode(QgsSnappingConfig.SnappingMode.AllLayers)
    config.setType(kind or QgsSnappingConfig.SnappingType.Vertex)
    config.setTolerance(float(pixels))
    config.setUnits(QgsTolerance.UnitType.Pixels)
    QgsProject.instance().setSnappingConfig(config)
    canvas.snappingUtils().setConfig(config)
    canvas.snappingUtils().setMapSettings(canvas.mapSettings())
    if enabled:
        # snapPoint() is non-blocking: against a cold index it reports no match
        # and says nothing. Without this the magnet-on tests are not slow, they
        # are wrong.
        for layer in canvas.layers():
            canvas.snappingUtils().locatorForLayer(layer).init()


def event_at(canvas, point, kind=QEvent.Type.MouseMove, button=None):
    """A QgsMapMouseEvent at the pixel nearest ``point``."""
    device = canvas.getCoordinateTransform().transform(point)
    pixel = QPoint(int(round(device.x())), int(round(device.y())))
    pressed = Qt.MouseButton.NoButton if button is None else button
    return QgsMapMouseEvent(canvas, kind, pixel, pressed, pressed,
                            Qt.KeyboardModifier.NoModifier)


def event_off_corner(canvas, pixels, kind=QEvent.Type.MouseMove, button=None):
    """An event ``pixels`` pixels diagonally outside CORNER."""
    device = canvas.getCoordinateTransform().transform(CORNER)
    step = pixels / (2.0 ** 0.5)
    pixel = QPoint(int(round(device.x() + step)), int(round(device.y() - step)))
    pressed = Qt.MouseButton.NoButton if button is None else button
    return QgsMapMouseEvent(canvas, kind, pixel, pressed, pressed,
                            Qt.KeyboardModifier.NoModifier)


def cursor_offset(event):
    """How far the event's cursor is from CORNER, in map units.

    Read it *before* the tool snaps: ``snapPoint()`` rewrites the event's own
    ``mapPoint()``, and ``originalMapPoint()`` returns the snapped value after
    that too, so there is no reading the raw position back afterwards.
    """
    return QgsPointXY(event.mapPoint()).distance(CORNER)


class EscapeKey:
    """Just the one accessor the tools' keyPressEvent reads."""

    def key(self):
        return Qt.Key.Key_Escape


def indicator_point(snapper):
    """Where the indicator is showing, or None when it is cleared."""
    match = snapper.indicator.match()
    if not match.isValid():
        return None
    return QgsPointXY(match.point())


def assert_on_corner(point, label):
    assert point is not None, f"{label}: nothing snapped"
    assert QgsPointXY(point).distance(CORNER) == pytest.approx(0.0, abs=1e-9), (
        f"{label}: landed {QgsPointXY(point).distance(CORNER)} map units off the vertex")


# ---------------------------------------------------------------------------
# The project's snapping configuration (QA section B, rows 1-5)
# ---------------------------------------------------------------------------

def test_magnet_on_locks_every_placement_tool_onto_the_vertex(qgis_app, qgis_new_project):
    """QA B1-B4: magnet on, Vertex, 12 px; hover 8 px; the click lands exactly."""
    from fiberq.tools.element_tool import PlaceElementTool
    from fiberq.tools.extension_tool import ExtensionTool
    from fiberq.tools.manhole_tool import ManholePlaceTool
    from fiberq.tools.point_tool import PointTool

    route = add_route()
    poles = add_poles()
    canvas = unit_canvas([route, poles])
    set_snapping(canvas, True, pixels=12)
    # Measured, and identical on 3.40, 3.44 and 4.2: the 8 px diagonal rounds to
    # 6 px on each axis, so the cursor sits 8.485 map units from the vertex --
    # inside the 12 px the configuration asks for, and far outside the 3.16 px
    # the element tool could actually reach before the fix.
    assert cursor_offset(event_off_corner(canvas, 8)) == pytest.approx(8.485, abs=0.01)

    element = PlaceElementTool(canvas, "ODF")
    element.canvasMoveEvent(event_off_corner(canvas, 8))
    assert element.snapper.indicator.isVisible()
    assert_on_corner(indicator_point(element.snapper), "element preview")
    # The click is snapped afresh, not read back off the last move.
    point, match = element.snapper.snap(
        event_off_corner(canvas, 8, QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton))
    assert_on_corner(point, "element click")
    assert match.hasVertex()

    pole = PointTool(canvas, poles)
    pole.canvasMoveEvent(event_off_corner(canvas, 8))
    assert pole.snap_marker.isVisible()
    assert_on_corner(indicator_point(pole.snapper), "pole preview")

    closure = ExtensionTool(canvas)
    closure.canvasMoveEvent(event_off_corner(canvas, 8))
    assert_on_corner(indicator_point(closure.snapper), "joint closure preview")

    manhole = ManholePlaceTool(StubIface(canvas), object())
    manhole.canvasMoveEvent(event_off_corner(canvas, 8))
    assert_on_corner(indicator_point(manhole.snapper), "manhole preview")
    placed, _match = manhole.snapper.snap(
        event_off_corner(canvas, 8, QEvent.Type.MouseButtonRelease, Qt.MouseButton.LeftButton))
    assert_on_corner(placed, "manhole click")


def test_the_users_tolerance_is_what_decides(qgis_app, qgis_new_project):
    """QA B5: at 30 px a click 25 px out snaps; at 12 px the same click does not.

    v1.5.0 missed it either way -- the tools never read the configuration, and
    their private tolerances were 10 and 20 px.
    """
    from fiberq.tools.element_tool import PlaceElementTool
    from fiberq.tools.extension_tool import ExtensionTool
    from fiberq.tools.manhole_tool import ManholePlaceTool
    from fiberq.tools.point_tool import PointTool

    route = add_route()
    poles = add_poles()
    canvas = unit_canvas([route, poles])
    builders = (
        ("element", lambda: PlaceElementTool(canvas, "ODF")),
        ("pole", lambda: PointTool(canvas, poles)),
        ("joint closure", lambda: ExtensionTool(canvas)),
        ("manhole", lambda: ManholePlaceTool(StubIface(canvas), object())),
    )

    # Measured, and identical on 3.40, 3.44 and 4.2: the 25 px diagonal rounds
    # to 18 px on each axis, so the click is 25.456 map units out. Both
    # tolerances below are read against that figure, so pin it.
    assert cursor_offset(event_off_corner(canvas, 25)) == pytest.approx(25.456, abs=0.01)

    set_snapping(canvas, True, pixels=30)
    for label, build in builders:
        tool = build()
        point, _match = tool.snapper.snap(
            event_off_corner(canvas, 25, QEvent.Type.MouseButtonRelease, Qt.MouseButton.LeftButton))
        assert_on_corner(point, f"{label} at 30 px tolerance")

    set_snapping(canvas, True, pixels=12)
    for label, build in builders:
        tool = build()
        _point, match = tool.snapper.snap(
            event_off_corner(canvas, 25, QEvent.Type.MouseButtonRelease, Qt.MouseButton.LeftButton))
        assert not match.isValid(), f"{label}: 25 px snapped inside a 12 px tolerance"


# ---------------------------------------------------------------------------
# FiberQ's own snap, for the many projects with the magnet off (decision D3)
# ---------------------------------------------------------------------------

def test_fallback_snaps_when_the_magnet_is_off(qgis_app, qgis_new_project):
    """QA B6. The element tool is the one that could not do this at all.

    Its tolerance reads as 10 px, but it compared a squared distance against it,
    so at one map unit per pixel the real radius was 3.16 px: an 8 px hover was
    out of reach.
    """
    from fiberq.tools.element_tool import PlaceElementTool
    from fiberq.tools.extension_tool import ExtensionTool
    from fiberq.tools.manhole_tool import ManholePlaceTool
    from fiberq.tools.point_tool import PointTool

    route = add_route()
    poles = add_poles()
    canvas = unit_canvas([route, poles])
    set_snapping(canvas, False)
    assert not canvas.snappingUtils().config().enabled()

    element = PlaceElementTool(canvas, "ODF")
    assert not element.snapper.qgis_snapping_on()
    element.canvasMoveEvent(event_off_corner(canvas, 8))
    assert_on_corner(element._last_snap_point, "element fallback preview")
    point, _match = element.snapper.snap(
        event_off_corner(canvas, 8, QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton))
    assert_on_corner(point, "element fallback click")

    for label, tool in (("pole", PointTool(canvas, poles)),
                        ("joint closure", ExtensionTool(canvas)),
                        ("manhole", ManholePlaceTool(StubIface(canvas), object()))):
        tool.canvasMoveEvent(event_off_corner(canvas, 8))
        assert_on_corner(indicator_point(tool.snapper), f"{label} fallback")


def test_fallback_leaves_nothing_behind_when_out_of_reach(qgis_app, qgis_new_project):
    """QA B6, second half: no stale indicator once the cursor moves away."""
    from fiberq.tools.element_tool import PlaceElementTool

    route = add_route()
    canvas = unit_canvas([route])
    set_snapping(canvas, False)

    element = PlaceElementTool(canvas, "ODF")
    element.canvasMoveEvent(event_off_corner(canvas, 8))
    assert element.snapper.indicator.isVisible()
    element.canvasMoveEvent(event_off_corner(canvas, 300))
    assert not element.snapper.indicator.isVisible()
    assert element._last_snap_point is None


def test_fallback_finds_a_route_still_called_trasa(qgis_app, qgis_new_project):
    """QA B8. ``point_tool`` tested ``lyr.name() in ('Route', 'Route')``.

    The rename replaced both halves of the (English, Serbian) pair, so the
    Serbian name was simply lost. Resolved through ``canonical_layer_name`` now.
    """
    from fiberq.models.schema import canonical_layer_name
    from fiberq.tools.element_tool import PlaceElementTool
    from fiberq.tools.extension_tool import ExtensionTool
    from fiberq.tools.manhole_tool import ManholePlaceTool
    from fiberq.tools.point_tool import PointTool

    assert canonical_layer_name("Trasa") == "Route"
    assert canonical_layer_name("Stubovi") == "Poles"

    route = add_route("Trasa")
    poles = add_poles("Stubovi")
    canvas = unit_canvas([route, poles])
    set_snapping(canvas, False)

    pole = PointTool(canvas, poles)
    pole.canvasMoveEvent(event_off_corner(canvas, 8))
    assert_on_corner(indicator_point(pole.snapper), "pole on Trasa")

    closure = ExtensionTool(canvas)
    closure.canvasMoveEvent(event_off_corner(canvas, 8))
    assert_on_corner(indicator_point(closure.snapper), "joint closure on Trasa")

    element = PlaceElementTool(canvas, "ODF")
    element.canvasMoveEvent(event_off_corner(canvas, 8))
    assert_on_corner(element._last_snap_point, "element on Trasa")

    manhole = ManholePlaceTool(StubIface(canvas), object())
    manhole.canvasMoveEvent(event_off_corner(canvas, 8))
    assert_on_corner(indicator_point(manhole.snapper), "manhole on Trasa")


def test_a_vertex_wins_over_a_point_on_a_segment(qgis_app, qgis_new_project):
    """Two defects in one stage: mixed units, and which candidate ought to win.

    The cursor sits 0.1 map units from the route line and 0.2 from a pole, both
    inside the element tool's tolerance -- so the point on the segment is the
    *nearer* of the two. The element still belongs on the pole: a vertex is a
    real feature, while a point on a segment is only wherever the cursor
    happened to be alongside it.

    v1.5.0 chose the line, and not for that reason either -- it wrote the
    line's *squared* distance (0.01) and the pole's *linear* distance (0.2) into
    the same variable, so 0.01 won whichever was really closer.
    """
    from fiberq.tools.element_tool import PlaceElementTool

    route = QgsVectorLayer("LineString?crs=EPSG:3857&field=naziv:string", "Route", "memory")
    feature = QgsFeature(route.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(100.1, 0), QgsPointXY(100.1, 200)]))
    route.dataProvider().addFeatures([feature])
    route.updateExtents()
    QgsProject.instance().addMapLayer(route)
    pole_at = QgsPointXY(100.2, 100.0)
    poles = add_poles("Poles", at=pole_at)

    # 25 map units across the canvas, so the element tool's 10 px is 0.313 map
    # units: measured, and wide enough to hold both candidates.
    canvas = unit_canvas([route, poles], span=25.0)
    set_snapping(canvas, False)
    assert canvas.mapUnitsPerPixel() * 10 == pytest.approx(0.313, abs=0.001)

    element = PlaceElementTool(canvas, "ODF")
    element.canvasMoveEvent(event_at(canvas, CORNER))
    chosen = element._last_snap_point
    assert chosen is not None, "nothing snapped; the tolerance no longer holds both candidates"
    assert QgsPointXY(chosen).distance(pole_at) == pytest.approx(0.0, abs=1e-6), (
        f"chose {QgsPointXY(chosen).asWkt()}, not the pole {pole_at.asWkt()}")
    # And for the right reason: a vertex, not the nearer point on the segment.
    assert element.snapper.indicator.match().hasVertex()


# ---------------------------------------------------------------------------
# The indicator must not outlive the tool (QA section B, row 7)
# ---------------------------------------------------------------------------

def test_escape_and_deactivate_clear_the_indicator(qgis_app, qgis_new_project):
    """QA B7. None of these tools had a deactivate(); the pole tool had no
    keyPressEvent at all, so ESC did nothing and the marker went stale."""
    from fiberq.tools.element_tool import PlaceElementTool
    from fiberq.tools.extension_tool import ExtensionTool
    from fiberq.tools.manhole_tool import ManholePlaceTool
    from fiberq.tools.point_tool import PointTool

    route = add_route()
    poles = add_poles()
    canvas = unit_canvas([route, poles])
    set_snapping(canvas, False)

    builders = (
        ("element", lambda: PlaceElementTool(canvas, "ODF")),
        ("pole", lambda: PointTool(canvas, poles)),
        ("joint closure", lambda: ExtensionTool(canvas)),
        ("manhole", lambda: ManholePlaceTool(StubIface(canvas), object())),
    )
    for label, build in builders:
        tool = build()
        tool.canvasMoveEvent(event_off_corner(canvas, 8))
        assert tool.snapper.indicator.isVisible(), f"{label}: nothing to clear"
        tool.keyPressEvent(EscapeKey())
        assert not tool.snapper.indicator.isVisible(), f"{label}: ESC left the indicator up"

        tool = build()
        tool.canvasMoveEvent(event_off_corner(canvas, 8))
        tool.deactivate()
        assert not tool.snapper.indicator.isVisible(), (
            f"{label}: a tool switch left the indicator up")


def test_right_click_clears_the_indicator(qgis_app, qgis_new_project):
    """QA B7. Right-click cancels, on whichever handler each tool uses."""
    from fiberq.tools.element_tool import PlaceElementTool
    from fiberq.tools.extension_tool import ExtensionTool
    from fiberq.tools.point_tool import PointTool

    route = add_route()
    poles = add_poles()
    canvas = unit_canvas([route, poles])
    set_snapping(canvas, False)

    element = PlaceElementTool(canvas, "ODF")
    element.canvasMoveEvent(event_off_corner(canvas, 8))
    element.canvasPressEvent(event_off_corner(
        canvas, 8, QEvent.Type.MouseButtonPress, Qt.MouseButton.RightButton))
    assert not element.snapper.indicator.isVisible()

    closure = ExtensionTool(canvas)
    closure.canvasMoveEvent(event_off_corner(canvas, 8))
    closure.canvasPressEvent(event_off_corner(
        canvas, 8, QEvent.Type.MouseButtonPress, Qt.MouseButton.RightButton))
    assert not closure.snapper.indicator.isVisible()

    pole = PointTool(canvas, poles)
    pole.canvasMoveEvent(event_off_corner(canvas, 8))
    pole.canvasReleaseEvent(event_off_corner(
        canvas, 8, QEvent.Type.MouseButtonRelease, Qt.MouseButton.RightButton))
    assert not pole.snap_marker.isVisible()


# ---------------------------------------------------------------------------
# The two tools that keep their own scan
# ---------------------------------------------------------------------------

def test_breakpoint_tool_snaps_across_its_whole_declared_tolerance(qgis_app, qgis_new_project):
    """The breakpoint tool carried the same squared-vs-linear comparison.

    Its tolerance reads as 10 px. On v1.5.0 only a hover within sqrt(10/mupp)
    px -- 3.16 px here -- actually snapped, so 4 px upwards silently did not.
    """
    from fiberq.tools.breakpoint_tool import BreakpointTool

    route = add_route()
    canvas = unit_canvas([route])
    set_snapping(canvas, False)
    assert canvas.mapUnitsPerPixel() == pytest.approx(1.0, abs=0.01)

    tool = BreakpointTool(canvas, StubIface(canvas), None)
    for pixels in (2, 4, 6, 8, 9):
        tool.canvasMoveEvent(event_off_corner(canvas, pixels))
        assert tool.snap_info is not None, f"a {pixels} px hover is inside 10 px but did not snap"
    # The keys the split itself reads must survive.
    assert "feat" in tool.snap_info
    assert "seg_idx" in tool.snap_info
    tool.canvasMoveEvent(event_off_corner(canvas, 40))
    assert tool.snap_info is None, "a 40 px hover snapped inside a 10 px tolerance"


def test_a_mid_span_slack_lands_on_its_cable(qgis_app, qgis_new_project):
    """The mid-span branch wrote the raw click, so the slack missed its cable.

    It could sit the full tolerance away from the cable it claimed to belong to.
    """
    from fiberq.tools.slack_tool import SlackPlaceTool

    cable = QgsVectorLayer("LineString?crs=EPSG:3857&field=naziv:string",
                           "Underground cables", "memory")
    feature = QgsFeature(cable.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(0, 100), QgsPointXY(200, 100)]))
    cable.dataProvider().addFeatures([feature])
    cable.updateExtents()
    QgsProject.instance().addMapLayer(cable)

    canvas = unit_canvas([cable])
    set_snapping(canvas, False)
    tool = SlackPlaceTool(StubIface(canvas), None, {})

    # Mid-span, 5 map units off the cable and far from either end.
    cursor = QgsPointXY(100.0, 105.0)
    layer, found, side, place = tool._resolve(cursor)
    assert layer is cable
    assert found is not None
    assert side == "sredina"
    assert place.distance(QgsPointXY(100.0, 100.0)) == pytest.approx(0.0, abs=1e-9), (
        f"the slack went to {place.asWkt()}, not onto the cable")

    # And the preview shows that same point, rather than the raw cursor.
    tool.canvasMoveEvent(event_at(canvas, cursor))
    shown = indicator_point(tool.snapper)
    assert shown is not None
    assert shown.distance(place) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# The dead code stays dead
# ---------------------------------------------------------------------------

def test_the_dead_brute_force_helpers_are_gone(qgis_app):
    """``tools/base.py`` carried eight uncalled snap and layer-finding helpers.

    One of them, ``snap_to_line_layer``, held a third copy of the squared-vs-
    linear comparison. They were re-exported by ``fiberq.tools``, so a partial
    deletion would be an ImportError on plugin load.
    """
    import fiberq.tools as tools
    from fiberq.tools import base

    gone = (
        "find_route_layer", "find_cable_layers", "find_node_layers",
        "find_element_layers", "get_snap_layers", "snap_to_point_layers",
        "snap_to_line_layer", "snap_to_line_vertices",
    )
    for name in gone:
        assert not hasattr(base, name), f"tools.base.{name} is back"
        assert not hasattr(tools, name), f"fiberq.tools re-exports {name} again"
        assert name not in base.__all__
        assert name not in tools.__all__

    # And the replacement is exported in their place.
    for name in ("PlacementSnapper", "snap_match", "no_match"):
        assert hasattr(tools, name)
        assert name in tools.__all__
