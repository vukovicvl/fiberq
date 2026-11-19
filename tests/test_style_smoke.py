"""Every styler the plugin runs gives its layer the renderer, colours, shapes and labels it means to, on every QGIS.

The earlier style tests read files only: test_style_files_exist.py checks that each style file the code names is
shipped, and test_style_fonts.py that those files name fonts that resolve. No test read back what a styler set, and each
styler swallows its own errors, so a broken one gave a layer QGIS's random default symbol without a word. Here each live
styler runs on a memory layer and what it set is read back: the renderer, the field the cables are classified on, each
category's value, colour and label, pen styles, marker shapes, a building's hatch and outline, the label expressions and
what they say for known features, and where a label sits.

Never a symbol size, a line width, a unit or a legend swatch: those are due to change with the way FiberQ sizes its
symbols, and a test of the style must not stand in that change's way. Never the value of a colour QGIS picks at random
(a new layer's default symbol): the route test sets a colour of its own first, one QGIS's palette never gives, and
when the line loses it, compares the line with the colour QGIS gave the style manager's new symbol, whatever it was.

The stylers are reached the way the plugin reaches them: the style manager's methods where the cable, route and
pipe managers hand the work to it, and those managers, wired as the plugin wires them, for the paths that go
through them. The slack style is the layer manager's, which is the one the plugin runs. A manager's own copy of a style,
for when the style manager failed to build, runs in the plugin only if the style manager raises, and is not tested here,
nor is a styler that nothing calls. The branch offset is tested although only a shortcut that fires nothing reaches it
today: a menu entry for it is planned, and that entry needs the offset to work on the categorised cable style.

Expected failures: three on every QGIS (restyling a route gives it a new colour, pipe lines get no round joins and
caps, and the branch offset never reaches the categories of the cable style), and three more from QGIS 3.38, where
manhole and element labels lose "over the point".
"""
import pytest
from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsLinePatternFillSymbolLayer,
    QgsPalLayerSettings,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
    QgsSimpleMarkerSymbolLayerBase,
    QgsSingleSymbolRenderer,
    QgsSymbolLayer,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from support.core_env import Core, CoreIface, clean_project, memory_layer, wired_plugin

from fiberq.core import layer_manager, style_manager
from fiberq.core.style_manager import StyleManager
from fiberq.utils import legacy_bridge


class LabelNotOverPoint(AssertionError):
    """WP5-FU-39: a label FiberQ means to sit over its point is placed around it."""


class RouteRecoloured(AssertionError):
    """WP5-FU-4: restyling the Route layer changed the colour its line had."""


class PipeCornersNotRound(AssertionError):
    """WP5-FU-40: a pipe line has the default bevel joins and square caps, not round ones."""


class OffsetLostOnCategories(AssertionError):
    """WP5-FU-41: a category of the cable style carries no branch offset after the offset was applied."""


#: The fields lay cable gives a cable layer that the cable style and its label read.
CABLE_FIELDS = ("tip", "podtip", "broj_vlakana:integer", "total_len_m:double", "duzina_m:double",
                "branch_index:integer")

#: The categories of the shipped cable styles, styles/Underground cables.qml and Aerial cables.qml, as
#: (subtype, (red, green, blue)). Their labels are not compared with the files: the code shows English ones.
SHIPPED_CABLE_CATEGORIES = [("glavni", (0, 51, 153)), ("distributivni", (204, 0, 0)), ("razvodni", (165, 42, 42))]

#: A colour QGIS's palette for new symbols never gives, so a test that finds it again knows it was kept.
SENTINEL = "#123456"

#: A line 5 long: a 3-4-5 triangle.
LINE_3_4_5 = "LINESTRING(0 0, 3 4)"


@pytest.fixture
def project(qgis_app):
    with clean_project() as prj:
        yield prj


def _rgb(color):
    return (color.red(), color.green(), color.blue())


def _shape(marker):
    """A simple marker's shape by name ("square", "circle", ...), the same on Qt 5 and Qt 6."""
    return QgsSimpleMarkerSymbolLayerBase.encodeShape(marker.shape())


def _label(layer, fid):
    """The text the layer's label expression gives the feature ``fid``."""
    expression = QgsExpression(layer.labeling().settings().fieldName)
    assert not expression.hasParserError(), expression.parserErrorString()
    context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    context.setFeature(layer.getFeature(fid))
    text = expression.evaluate(context)
    assert not expression.hasEvalError(), expression.evalErrorString()
    return text


def _offset_at(layer, symbol_layer, branch_index):
    """The offset a symbol layer's data-defined offset gives a cable of this branch index, or None when the symbol
    layer has no active data-defined offset (or its value cannot be read)."""
    prop = symbol_layer.dataDefinedProperties().property(QgsSymbolLayer.Property.PropertyOffset)
    if not prop.isActive():
        return None
    feature = QgsFeature(layer.fields())
    feature["branch_index"] = branch_index
    context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    context.setFeature(feature)
    value, ok = prop.value(context, -1.0)
    return float(value) if ok else None


def _cable_layer(project, name="Underground cables", rows=()):
    return memory_layer(project, "LineString", name, rows, fields=CABLE_FIELDS)


def _manholes(project):
    """An OKNA layer styled as manholes, holding the numbers "12", "" and none (fids 1, 2, 3)."""
    layer = memory_layer(project, "Point", "OKNA", [("POINT(1 1)", {"broj_okna": "12"}),
                                                    ("POINT(2 2)", {"broj_okna": ""}),
                                                    ("POINT(3 3)", {})], fields=("broj_okna",))
    StyleManager(None).stylize_manhole_layer(layer)
    return layer


# --- the guard ---------------------------------------------------------------------------------------------------

def test_a_styler_leaves_no_layer_and_an_invalid_layer_alone(project):
    """A styler handed no layer, or a layer whose file is missing, returns without raising and gives the invalid
    layer no renderer. (The invalid layer stays out of the project: an OGR layer that opened nothing is safe
    standalone.)"""
    broken = QgsVectorLayer("/nonexistent/fiberq.gpkg|layername=x", "broken", "ogr")
    assert not broken.isValid()
    styler = StyleManager(None)
    for style in (styler.stylize_route_layer, styler.stylize_cable_layer, styler.stylize_manhole_layer,
                  styler.stylize_objects_layer):
        assert style(None) is None
        assert style(broken) is None
        assert broken.renderer() is None, style.__name__


# --- cables ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, pen", [("Kablovi_podzemni", Qt.PenStyle.DashLine),
                                       ("Underground cables", Qt.PenStyle.DashLine),
                                       ("Kablovi_vazdusni", Qt.PenStyle.SolidLine),
                                       ("Aerial cables", Qt.PenStyle.SolidLine)],
                         ids=["podzemni-dash", "underground-dash", "vazdusni-solid", "aerial-solid"])
def test_a_cable_layer_is_categorised_on_its_subtype_like_the_shipped_style(project, name, pen):
    """Cables are drawn by subtype in the shipped styles' colours, dashed when they run underground and solid when
    they hang in the air, whether the layer has its Serbian or its English name."""
    layer = _cable_layer(project, name)
    StyleManager(None).stylize_cable_layer(layer)

    renderer = layer.renderer()
    assert isinstance(renderer, QgsCategorizedSymbolRenderer)
    assert renderer.classAttribute() == "podtip"
    assert [(c.value(), _rgb(c.symbol().color())) for c in renderer.categories()] == SHIPPED_CABLE_CATEGORIES
    assert [c.label() for c in renderer.categories()] == ["Backbone", "Distribution", "Drop"]
    for category in renderer.categories():
        lines = category.symbol().symbolLayers()
        assert [type(line) for line in lines] == [QgsSimpleLineSymbolLayer]
        assert lines[0].penStyle() == pen


def test_a_cable_label_gives_the_stored_length_the_type_and_the_fibres(project):
    """The label along a cable says its length in metres, then its type and fibre count. Lengths stay under 1000,
    so no thousands separator, which depends on the locale, appears."""
    layer = _cable_layer(project, rows=[(LINE_3_4_5, {"total_len_m": 123.4, "tip": "opticki", "broj_vlakana": 24}),
                                        (LINE_3_4_5, {"total_len_m": 77.0, "tip": "bakarni", "broj_vlakana": 10})])
    StyleManager(None).stylize_cable_layer(layer)

    assert layer.labelsEnabled()
    assert isinstance(layer.labeling(), QgsVectorLayerSimpleLabeling)
    settings = layer.labeling().settings()
    assert settings.isExpression
    assert settings.placement == QgsPalLayerSettings.Placement.Line
    assert [_label(layer, fid) for fid in (1, 2)] == ["123 m\nOptical 24f", "77 m\nCopper 10f"]


def test_the_cable_label_length_comes_from_the_total_then_the_length_then_the_line(project):
    """The length shown is the stored total (slack included) where there is one, then the laid length, and only
    then the line's own length."""
    layer = _cable_layer(project, rows=[(LINE_3_4_5, {"total_len_m": 10.0, "duzina_m": 20.0}),
                                        (LINE_3_4_5, {"duzina_m": 20.0}),
                                        (LINE_3_4_5, {})])
    StyleManager(None).stylize_cable_layer(layer)
    assert [_label(layer, fid).split("\n")[0] for fid in (1, 2, 3)] == ["10 m", "20 m", "5 m"]


# --- manholes ----------------------------------------------------------------------------------------------------

def test_a_manhole_is_a_hollow_black_square(project):
    layer = _manholes(project)
    assert isinstance(layer.renderer(), QgsSingleSymbolRenderer)
    markers = layer.renderer().symbol().symbolLayers()
    assert [type(marker) for marker in markers] == [QgsSimpleMarkerSymbolLayer]
    assert _shape(markers[0]) == "square"
    assert markers[0].fillColor().alpha() == 0
    assert _rgb(markers[0].strokeColor()) == (0, 0, 0)


def test_a_manhole_label_names_the_manhole(project):
    layer = _manholes(project)
    assert layer.labelsEnabled()
    assert [_label(layer, fid) for fid in (1, 2, 3)] == ["MH 12", "", ""]


@pytest.mark.xfail(Qgis.QGIS_VERSION_INT >= 33800, strict=True, raises=LabelNotOverPoint,
                   reason="WP5-FU-39: from QGIS 3.38 manhole and element labels lose 'over the point' and stay "
                          "around it; the v1.8.0 fix removes this marker")
def test_a_manhole_label_sits_over_the_point_in_the_quadrant_above(project):
    """The manhole label sits over its point, in the quadrant above it. From QGIS 3.38 the style asks for this
    with an enum that QGIS no longer takes there, and the label stays where QGIS puts it by default."""
    layer = _manholes(project)
    assert layer.labelsEnabled()
    settings = layer.labeling().settings()
    assert settings.isExpression and '"broj_okna"' in settings.fieldName
    placed = (settings.placement, settings.quadOffset)
    if placed != (QgsPalLayerSettings.Placement.OverPoint, QgsPalLayerSettings.QuadrantAbove):
        # WP5-FU-39's effect and nothing else: QGIS's default placement, around the point.
        assert placed == (QgsPalLayerSettings.Placement.AroundPoint, QgsPalLayerSettings.QuadrantAbove), (
            "the manhole label is placed %r in quadrant %r" % placed)
        raise LabelNotOverPoint("the manhole label is placed %r in quadrant %r" % placed)


def _element_layer_from_change_element_type(project):
    """A new TB layer, as Change element type makes one; it labels the layer with layer_manager's helper."""
    return layer_manager._ensure_element_layer_with_style(Core(CoreIface()), "TB")


def _element_layer_from_the_placement_tools(project):
    """An ODF layer labelled with the helper of utils/legacy_bridge.py, which the element placement tools use."""
    layer = memory_layer(project, "Point", "ODF", fields=("naziv",))
    legacy_bridge._apply_fixed_text_label(layer, "naziv", 8.0, 5.0)
    return layer


@pytest.mark.xfail(Qgis.QGIS_VERSION_INT >= 33800, strict=True, raises=LabelNotOverPoint,
                   reason="WP5-FU-39: from QGIS 3.38 manhole and element labels lose 'over the point' and stay "
                          "around it; the v1.8.0 fix removes this marker")
@pytest.mark.parametrize("labelled", [_element_layer_from_change_element_type,
                                      _element_layer_from_the_placement_tools],
                         ids=["layer_manager", "legacy_bridge"])
def test_an_element_label_sits_over_the_point(project, labelled):
    """An element's name sits over its point, through either of the two helpers that label element layers."""
    layer = labelled(project)
    assert layer.labelsEnabled()
    settings = layer.labeling().settings()
    assert settings.fieldName == "naziv"
    if settings.placement != QgsPalLayerSettings.Placement.OverPoint:
        # WP5-FU-39's effect and nothing else: QGIS's default placement, around the point.
        assert settings.placement == QgsPalLayerSettings.Placement.AroundPoint, (
            "the element label is placed %r" % settings.placement)
        raise LabelNotOverPoint("the element label is placed %r" % settings.placement)


# --- routes ------------------------------------------------------------------------------------------------------

def test_a_route_is_dashed(project):
    layer = memory_layer(project, "LineString", "Route", fields=("naziv",))
    StyleManager(None).stylize_route_layer(layer)
    assert isinstance(layer.renderer(), QgsSingleSymbolRenderer)
    lines = layer.renderer().symbol().symbolLayers()
    assert len(lines) == 1
    assert lines[0].penStyle() == Qt.PenStyle.DashLine


def _record_default_symbols(monkeypatch):
    """The colours of the default symbols the style manager asks QGIS for, in order: QgsSymbol.defaultSymbol gives
    each new symbol a colour of its own."""
    handed_out = []
    real = style_manager.QgsSymbol

    class _Recording:
        @staticmethod
        def defaultSymbol(geometry_type):
            symbol = real.defaultSymbol(geometry_type)
            handed_out.append(symbol.color().name())
            return symbol
    monkeypatch.setattr(style_manager, "QgsSymbol", _Recording)
    return handed_out


@pytest.mark.xfail(strict=True, raises=RouteRecoloured,
                   reason="WP5-FU-4: every route operation re-colours the Route layer at random; "
                          "the v1.8.0 fix removes this marker")
def test_restyling_a_route_keeps_its_colour(project, monkeypatch):
    """Restyling the Route layer (each route operation does) keeps the colour its line has."""
    layer = memory_layer(project, "LineString", "Route", fields=("naziv",))
    layer.renderer().symbol().setColor(QColor(SENTINEL))
    assert layer.renderer().symbol().color().name() == SENTINEL
    handed_out = _record_default_symbols(monkeypatch)
    StyleManager(None).stylize_route_layer(layer)
    symbol = layer.renderer().symbol()
    assert symbol.symbolLayers()[0].penStyle() == Qt.PenStyle.DashLine
    if symbol.color().name() != SENTINEL:
        # WP5-FU-4's effect and nothing else: the line took the colour of the one new default symbol.
        assert handed_out == [symbol.color().name()], "the route line is now %s; new default symbols: %s" % (
            symbol.color().name(), handed_out)
        raise RouteRecoloured("the route line was %s and is now %s" % (SENTINEL, symbol.color().name()))


# --- slacks ------------------------------------------------------------------------------------------------------

def test_the_slack_layer_is_a_red_circle(project):
    """The slack layer the plugin makes (the layer manager's, which styles it itself) draws a red circle."""
    layer = wired_plugin(CoreIface()).layer_manager.ensure_slack_layer()
    assert layer is not None
    assert isinstance(layer.renderer(), QgsSingleSymbolRenderer)
    markers = layer.renderer().symbol().symbolLayers()
    assert len(markers) == 1
    assert _shape(markers[0]) == "circle"
    assert _rgb(markers[0].color()) == (255, 0, 0)


# --- pipes -------------------------------------------------------------------------------------------------------

def test_a_pipe_takes_the_colour_the_pipe_tool_gives(project):
    """The pipe tool styles its two layers through the pipe manager, PE pipes orange and transition pipes yellow
    green (tools/pipe_tool.py), each as one solid line."""
    pipes = wired_plugin(CoreIface()).pipe_manager
    pe = memory_layer(project, "LineString", "PE pipes", fields=("materijal",))
    transition = memory_layer(project, "LineString", "Transition pipes", fields=("materijal",))
    pipes.apply_pipe_style(pe, "#FF9900", 1.0)
    pipes.apply_pipe_style(transition, "#D0FF00", 2.2)
    for layer, colour in ((pe, "#ff9900"), (transition, "#d0ff00")):
        assert isinstance(layer.renderer(), QgsSingleSymbolRenderer)
        lines = layer.renderer().symbol().symbolLayers()
        assert [type(line) for line in lines] == [QgsSimpleLineSymbolLayer]
        assert lines[0].color().name() == colour
        assert lines[0].penStyle() == Qt.PenStyle.SolidLine


@pytest.mark.xfail(strict=True, raises=PipeCornersNotRound,
                   reason="WP5-FU-40: the pipe styler calls symbol-layer methods that no QGIS 3 or 4 has, so pipes "
                          "keep bevel joins and square caps; the v1.8.0 fix removes this marker")
def test_a_pipe_has_round_joins_and_caps(project):
    """The pipe style means pipes to have round corners and ends."""
    layer = memory_layer(project, "LineString", "PE pipes", fields=("materijal",))
    wired_plugin(CoreIface()).pipe_manager.apply_pipe_style(layer, "#FF9900", 1.0)
    lines = layer.renderer().symbol().symbolLayers()
    assert [type(line) for line in lines] == [QgsSimpleLineSymbolLayer]
    assert lines[0].color().name() == "#ff9900"
    corners = (lines[0].penJoinStyle(), lines[0].penCapStyle())
    if corners != (Qt.PenJoinStyle.RoundJoin, Qt.PenCapStyle.RoundCap):
        # WP5-FU-40's effect and nothing else: QGIS's default bevel joins and square caps.
        assert corners == (Qt.PenJoinStyle.BevelJoin, Qt.PenCapStyle.SquareCap), (
            "the pipe line has joins %r and caps %r" % corners)
        raise PipeCornersNotRound("the pipe line has joins %r and caps %r" % corners)


# --- buildings ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("styler", [layer_manager._stylize_objects_layer, legacy_bridge._stylize_objects_layer],
                         ids=["objects-menu", "draw-tools"])
def test_every_building_styler_draws_a_hatch_inside_a_black_outline(project, styler):
    """The Objects menu's layer and the building drawing tools' layer get the same building: a black hatch at 60
    degrees inside a black outline, with no fill. The drawing tools run their own copy of the style, so a change
    to the style manager's building that does not reach them fails here."""
    layer = memory_layer(project, "Polygon", "Objects", fields=("tip",))
    styler(layer)
    assert isinstance(layer.renderer(), QgsSingleSymbolRenderer)
    layers = layer.renderer().symbol().symbolLayers()
    assert [type(sl) for sl in layers] == [QgsLinePatternFillSymbolLayer, QgsSimpleFillSymbolLayer]
    hatch, outline = layers
    assert hatch.lineAngle() == 60.0
    assert _rgb(hatch.subSymbol().color()) == (0, 0, 0)
    assert outline.fillColor().alpha() == 0
    assert _rgb(outline.strokeColor()) == (0, 0, 0)


# --- branch offset -----------------------------------------------------------------------------------------------

def test_the_branch_offset_on_a_single_symbol_layer_is_the_index_times_the_step(project):
    """Branch cables (offset) moves each cable sideways by its branch index times the step."""
    layer = _cable_layer(project)
    StyleManager(None).apply_branch_offset_style(layer, 2.0)
    lines = layer.renderer().symbol().symbolLayers()
    assert len(lines) == 1
    assert [_offset_at(layer, lines[0], index) for index in (3, 0)] == [6.0, 0.0]


@pytest.mark.xfail(strict=True, raises=OffsetLostOnCategories,
                   reason="WP5-FU-41: the branch offset does nothing on the categorised cable style; "
                          "the v1.8.0 fix removes this marker")
def test_the_branch_offset_reaches_every_cable_category(project):
    """Lay cable always gives a cable layer the categorised style, so the offset has to reach every category."""
    layer = _cable_layer(project)
    styler = StyleManager(None)
    control = _cable_layer(project, "Control cables")
    styler.apply_branch_offset_style(control, 2.0)
    assert _offset_at(control, control.renderer().symbol().symbolLayers()[0], 3) == 6.0, (
        "premise: the branch offset reaches a single-symbol cable layer")
    styler.stylize_cable_layer(layer)
    styler.apply_branch_offset_style(layer, 2.0)
    renderer = layer.renderer()
    assert isinstance(renderer, QgsCategorizedSymbolRenderer)
    categories = renderer.categories()   # copies, which own the symbols read below: kept until the end
    lines = [category.symbol().symbolLayers() for category in categories]
    assert [[type(line) for line in symbol] for symbol in lines] == [[QgsSimpleLineSymbolLayer]] * 3
    offsets = [_offset_at(layer, symbol[0], 3) for symbol in lines]
    if offsets != [6.0, 6.0, 6.0]:
        # WP5-FU-41's effect and nothing else: no category carries an active data-defined offset.
        active = [symbol[0].dataDefinedProperties().property(QgsSymbolLayer.Property.PropertyOffset).isActive()
                  for symbol in lines]
        assert (offsets, active) == ([None] * 3, [False] * 3), (
            "at branch index 3 the categories are offset by %r (active: %r)" % (offsets, active))
        raise OffsetLostOnCategories("at branch index 3 the categories are offset by %r" % offsets)


# --- the managers hand the style to the style manager ------------------------------------------------------------

def test_the_cable_and_route_managers_apply_the_style_managers_style(project):
    """Lay cable and the route tools style through the cable and route managers, which hand the work to the
    style manager; the cable manager also gives the layer its English name."""
    plugin = wired_plugin(CoreIface())
    cables = _cable_layer(project, "Kablovi_podzemni")
    plugin.cable_manager.stylize_cable_layer(cables)
    assert isinstance(cables.renderer(), QgsCategorizedSymbolRenderer)
    assert cables.name() == "Underground cables"

    routes = memory_layer(project, "LineString", "Route", fields=("naziv",))
    plugin.route_manager.stylize_route_layer(routes)
    assert isinstance(routes.renderer(), QgsSingleSymbolRenderer)
    assert routes.renderer().symbol().symbolLayers()[0].penStyle() == Qt.PenStyle.DashLine
