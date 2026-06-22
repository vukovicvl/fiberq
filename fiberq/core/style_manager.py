"""
FiberQ v2 - Style Manager

This module centralizes all layer styling logic.
It provides methods to apply consistent styles to FiberQ layers.

Phase 7 of the modular refactoring.
"""

from qgis.core import (
    QgsProject, QgsWkbTypes, QgsSymbol,
    QgsMarkerSymbol, QgsFillSymbol, QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer, QgsSimpleFillSymbolLayer,
    QgsLinePatternFillSymbolLayer, QgsSingleSymbolRenderer,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsVectorLayerSimpleLabeling,
    QgsPalLayerSettings, QgsTextFormat,
    QgsTextBufferSettings, QgsUnitTypes,
    QgsProperty, QgsSymbolLayer, QgsMapUnitScale,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


# Import Qgis for version-specific enums
try:
    from qgis.core import Qgis
except ImportError:
    Qgis = None


class StyleManager:
    """
    Centralized style management for FiberQ plugin.

    Handles applying consistent visual styles to all FiberQ layers.
    """

    def __init__(self, iface, plugin=None):
        """
        Initialize the style manager.

        Args:
            iface: QGIS interface instance
            plugin: Optional reference to main plugin for callbacks
        """
        self.iface = iface
        self.plugin = plugin

    # =========================================================================
    # ROUTE LAYER STYLE
    # =========================================================================

    def stylize_route_layer(self, layer):
        """
        Apply route layer style: dashed line in map units.

        Args:
            layer: QgsVectorLayer for routes
        """
        if not layer or not layer.isValid():
            return

        try:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol_layer = symbol.symbolLayer(0)
            symbol_layer.setWidth(0.8)
            symbol_layer.setWidthUnit(QgsUnitTypes.RenderMetersInMapUnits)
            symbol_layer.setPenStyle(Qt.PenStyle.DashLine)
            layer.renderer().setSymbol(symbol)
            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in StyleManager.stylize_route_layer: {e}")

    # =========================================================================
    # CABLE LAYER STYLE
    # =========================================================================

    def stylize_cable_layer(self, layer):
        """
        Apply cable layer style with categorized renderer.

        Underground cables: dashed lines
        Aerial cables: solid lines
        Colors by cable type (backbone/distribution/drop)

        Args:
            layer: QgsVectorLayer for cables
        """
        if not layer or not layer.isValid():
            return

        try:
            # Get base width from route layer if available
            base_width = 0.8
            base_unit = QgsUnitTypes.RenderMetersInMapUnits
            try:
                route_layer = next(
                    (
                        lyr for lyr in QgsProject.instance().mapLayers().values()
                        if lyr.name().lower().strip() in ("trasa", "route")
                        and lyr.geometryType() == QgsWkbTypes.LineGeometry
                    ),
                    None
                )
                if route_layer and route_layer.renderer() and route_layer.renderer().symbol():
                    sl = route_layer.renderer().symbol().symbolLayer(0)
                    if hasattr(sl, "width"):
                        base_width = sl.width()
                    if hasattr(sl, "widthUnit"):
                        base_unit = sl.widthUnit()
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_cable_layer: {e}")

            cable_width = max(base_width * 1.6, base_width + 0.6)

            name_l = layer.name().lower()
            is_underground = "podzem" in name_l or "underground" in name_l
            is_aerial = "vazdus" in name_l or "vazduš" in name_l or "aerial" in name_l

            # Colors for cable types
            COLOR_BACKBONE = QColor(0, 51, 153)
            COLOR_DISTRIB = QColor(204, 0, 0)
            COLOR_DROP = QColor(165, 42, 42)

            # Label mapping (Serbian values -> English labels)
            label_map = {
                "glavni": "Backbone",
                "distributivni": "Distribution",
                "razvodni": "Drop",
            }

            categories = []
            for value, color in [
                ("glavni", COLOR_BACKBONE),
                ("distributivni", COLOR_DISTRIB),
                ("razvodni", COLOR_DROP),
            ]:
                sym = QgsSymbol.defaultSymbol(layer.geometryType())
                try:
                    if sym.symbolLayerCount() > 0:
                        sym.deleteSymbolLayer(0)
                except Exception as e:
                    logger.debug(f"Error in StyleManager.stylize_cable_layer: {e}")

                # Base line
                ln = QgsSimpleLineSymbolLayer()
                ln.setColor(color)
                ln.setWidth(cable_width)
                ln.setWidthUnit(base_unit)
                ln.setPenStyle(Qt.PenStyle.DashLine if is_underground else Qt.PenStyle.SolidLine)
                sym.appendSymbolLayer(ln)

                label = label_map.get(value, value.capitalize())
                categories.append(QgsRendererCategory(value, sym, label))

            layer.setRenderer(QgsCategorizedSymbolRenderer('podtip', categories))

            # Labels
            self._apply_cable_labels(layer)

            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in StyleManager.stylize_cable_layer: {e}")

    def _apply_cable_labels(self, layer):
        """Apply labels to cable layer."""
        try:
            s = QgsPalLayerSettings()
            # Issue #1: Use stored total_len_m or duzina_m, avoid $length which can differ due to CRS
            s.fieldName = (
                "concat("
                "format_number(coalesce(\"total_len_m\", \"duzina_m\", length($geometry)), 0), ' m', '\n', "
                "CASE "
                " WHEN lower(coalesce(attribute($currentfeature,'tip'), attribute($currentfeature,'Tip'), attribute($currentfeature,'TIP'))) LIKE 'optick%' THEN 'Optical' "
                " WHEN lower(coalesce(attribute($currentfeature,'tip'), attribute($currentfeature,'Tip'), attribute($currentfeature,'TIP'))) LIKE 'bakarn%' THEN 'Copper' "
                " ELSE coalesce(attribute($currentfeature,'tip'), attribute($currentfeature,'Tip'), attribute($currentfeature,'TIP')) "
                "END, ' ', "
                "coalesce(attribute($currentfeature,'broj_vlakana'), ''), 'f'"
                ")"
            )
            s.isExpression = True

            try:
                if hasattr(QgsPalLayerSettings, 'LinePlacement') and hasattr(QgsPalLayerSettings.LinePlacement, 'AboveLine'):
                    s.placement = QgsPalLayerSettings.LinePlacement.AboveLine
                elif hasattr(QgsPalLayerSettings, 'Line'):
                    s.placement = QgsPalLayerSettings.Line
            except Exception as e:
                logger.debug(f"Error in StyleManager._apply_cable_labels: {e}")

            tf = QgsTextFormat()
            tf.setSize(9)
            tf.setColor(QColor(200, 0, 0))
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.8)
            buf.setColor(QColor(255, 255, 255))
            tf.setBuffer(buf)
            s.setFormat(tf)

            layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
            layer.setLabelsEnabled(True)
        except Exception as e:
            logger.debug(f"Error in StyleManager._apply_cable_labels: {e}")

    # =========================================================================
    # SLACK LAYER STYLE
    # =========================================================================

    def stylize_slack_layer(self, layer):
        """
        Apply slack layer style: small red circle.

        Args:
            layer: QgsVectorLayer for optical slacks
        """
        if not layer or not layer.isValid():
            return

        try:
            sym = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "size": "3",
            })
            try:
                sym.setColor(QColor(255, 0, 0))
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_slack_layer: {e}")
            try:
                sym.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_slack_layer: {e}")

            renderer = QgsSingleSymbolRenderer(sym)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in StyleManager.stylize_slack_layer: {e}")

    # =========================================================================
    # MANHOLE LAYER STYLE
    # =========================================================================

    def stylize_manhole_layer(self, layer):
        """
        Apply manhole layer style: square marker with label above.

        Marker in map units (meters), outline in mm, label fixed size.

        Args:
            layer: QgsVectorLayer for manholes
        """
        if not layer or not layer.isValid():
            return

        try:
            # Symbol (map units / meters)
            size_m = 10.0
            sym = QgsMarkerSymbol.createSimple({
                'name': 'square',
                'size': str(size_m),
                'color': '255,255,255,0',
                'outline_color': '#000000',
                'outline_width': '0.8'
            })
            sl = sym.symbolLayer(0)

            # Size in meters on map
            try:
                sl.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
            except Exception as e:
                sl.setSizeUnit(QgsUnitTypes.RenderMapUnits)

            # Outline in mm (constant width)
            try:
                sl.setOutlineWidthUnit(QgsUnitTypes.RenderMillimeters)
            except Exception as e:
                try:
                    sl.setStrokeWidthUnit(QgsUnitTypes.RenderMillimeters)
                except Exception as e:
                    logger.debug(f"Error in StyleManager.stylize_manhole_layer: {e}")

            # Reset data-defined properties
            try:
                ddp = sl.dataDefinedProperties()
                if ddp:
                    ddp.setProperty(QgsSymbolLayer.PropertySize, QgsProperty())
                    sl.setDataDefinedProperties(ddp)
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_manhole_layer: {e}")
            try:
                sl.setMapUnitScale(QgsMapUnitScale())
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_manhole_layer: {e}")

            layer.setRenderer(QgsSingleSymbolRenderer(sym))

            # Labels
            self._apply_manhole_labels(layer)

            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in StyleManager.stylize_manhole_layer: {e}")

    def _apply_manhole_labels(self, layer):
        """Apply labels to manhole layer."""
        try:
            s = QgsPalLayerSettings()
            s.enabled = True
            s.isExpression = True
            s.fieldName = (
                "CASE WHEN length(coalesce(\"broj_okna\", ''))>0 "
                "THEN concat('MH ', \"broj_okna\") ELSE '' END"
            )

            # Offset from point placement
            placed = False
            for cand in (
                getattr(Qgis, 'LabelPlacement', None) and getattr(Qgis.LabelPlacement, 'OffsetFromPoint', None) if Qgis else None,
                getattr(QgsPalLayerSettings, 'OffsetFromPoint', None),
            ):
                if cand is not None:
                    try:
                        s.placement = cand
                        placed = True
                        break
                    except Exception as e:
                        logger.debug(f"Error in StyleManager._apply_manhole_labels: {e}")
            if not placed:
                try:
                    s.placement = getattr(QgsPalLayerSettings, 'OverPoint', s.placement)
                except Exception as e:
                    logger.debug(f"Error in StyleManager._apply_manhole_labels: {e}")

            # Quadrant above point
            for attr_name in ('quadrantPosition', 'quadOffset'):
                if hasattr(s, attr_name):
                    enum_val = getattr(QgsPalLayerSettings, 'QuadrantAbove', None)
                    if enum_val is None and Qgis:
                        try:
                            enum_val = getattr(Qgis, 'LabelQuadrantPosition').Above
                        except Exception as e:
                            enum_val = None
                    if enum_val is not None:
                        try:
                            setattr(s, attr_name, enum_val)
                            break
                        except Exception as e:
                            logger.debug(f"Error in StyleManager._apply_manhole_labels: {e}")

            # Fixed offset above marker
            s.xOffset = 0.0
            s.yOffset = 5.0
            s.offsetUnits = QgsUnitTypes.RenderMapUnits

            tf = QgsTextFormat()
            tf.setSize(8.0)
            try:
                tf.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            except Exception as e:
                logger.debug(f"Error in StyleManager._apply_manhole_labels: {e}")
            f = QFont()
            f.setBold(True)
            tf.setFont(f)
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(1.0)
            buf.setColor(QColor(255, 255, 255))
            buf.setOpacity(1.0)
            tf.setBuffer(buf)

            s.setFormat(tf)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
            layer.setLabelsEnabled(True)
        except Exception as e:
            logger.debug(f"Error in StyleManager._apply_manhole_labels: {e}")

    # =========================================================================
    # PIPE LAYER STYLE
    # =========================================================================

    def stylize_pipe_layer(self, layer, color_hex, width_mm):
        """
        Apply pipe layer style: simple line with fixed width.

        Args:
            layer: QgsVectorLayer for pipes
            color_hex: Hex color string (e.g., '#FF0000')
            width_mm: Line width in millimeters
        """
        if not layer or not layer.isValid():
            return

        try:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            sl = QgsSimpleLineSymbolLayer()
            sl.setColor(QColor(color_hex))
            sl.setWidth(float(width_mm))
            sl.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            # Rounded corners for better appearance
            try:
                sl.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                sl.setCapStyle(Qt.PenCapStyle.RoundCap)
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_pipe_layer: {e}")
            symbol.deleteSymbolLayer(0)
            symbol.appendSymbolLayer(sl)
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in StyleManager.stylize_pipe_layer: {e}")

    # =========================================================================
    # FIBER BREAK LAYER STYLE
    # =========================================================================

    def stylize_fiber_break_layer(self, layer):
        """
        Apply fiber break layer style: small black circle.

        Args:
            layer: QgsVectorLayer for fiber breaks
        """
        if not layer or not layer.isValid():
            return

        try:
            simple = QgsSimpleMarkerSymbolLayer()

            try:
                simple.setShape(QgsSimpleMarkerSymbolLayer.Circle)
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_fiber_break_layer: {e}")

            simple.setSize(2.4)
            simple.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
            simple.setColor(QColor(0, 0, 0))
            simple.setOutlineColor(QColor(0, 0, 0))
            simple.setOutlineWidth(0.2)
            simple.setOutlineWidthUnit(QgsUnitTypes.RenderMetersInMapUnits)

            sym = QgsMarkerSymbol()
            sym.changeSymbolLayer(0, simple)
            layer.renderer().setSymbol(sym)
            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in StyleManager.stylize_fiber_break_layer: {e}")

    # =========================================================================
    # OBJECTS (BUILDINGS) LAYER STYLE
    # =========================================================================

    def stylize_objects_layer(self, layer):
        """
        Apply objects layer style: black outline with diagonal hatch.

        DWG-like appearance with transparent fill and hatching.

        Args:
            layer: QgsVectorLayer for building objects
        """
        if not layer or not layer.isValid():
            return

        try:
            # Transparent fill with black outline
            simple = QgsSimpleFillSymbolLayer()
            simple.setFillColor(QColor(0, 0, 0, 0))
            simple.setStrokeColor(QColor(0, 0, 0))
            simple.setStrokeWidth(0.8)
            simple.setStrokeWidthUnit(QgsUnitTypes.RenderMillimeters)

            # Diagonal hatch lines
            hatch = QgsLinePatternFillSymbolLayer()
            try:
                try:
                    hatch.setLineAngle(60.0)
                except Exception as e:
                    try:
                        hatch.setAngle(60.0)
                    except Exception as e:
                        logger.debug(f"Error in StyleManager.stylize_objects_layer: {e}")
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_objects_layer: {e}")
            hatch.setDistance(2.2)
            hatch.setDistanceUnit(QgsUnitTypes.RenderMillimeters)

            # Tune hatch sub symbol
            try:
                sub = hatch.subSymbol()
                if sub and sub.symbolLayerCount() > 0:
                    sl = sub.symbolLayer(0)
                    try:
                        sl.setColor(QColor(0, 0, 0))
                    except Exception as e:
                        logger.debug(f"Error in StyleManager.stylize_objects_layer: {e}")
                    try:
                        sl.setWidth(0.3)
                        sl.setWidthUnit(QgsUnitTypes.RenderMillimeters)
                    except Exception as e:
                        logger.debug(f"Error in StyleManager.stylize_objects_layer: {e}")
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_objects_layer: {e}")

            sym = QgsFillSymbol()
            try:
                sym.deleteSymbolLayer(0)
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_objects_layer: {e}")
            sym.appendSymbolLayer(hatch)
            sym.appendSymbolLayer(simple)

            renderer = QgsSingleSymbolRenderer(sym)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in StyleManager.stylize_objects_layer: {e}")

    # =========================================================================
    # BRANCH OFFSET STYLE
    # =========================================================================

    def apply_branch_offset_style(self, layer, offset_mm=2.0):
        """
        Apply data-defined offset based on branch_index field.

        Works for both SingleSymbol and Categorized renderers.

        Args:
            layer: QgsVectorLayer for cables
            offset_mm: Offset distance in millimeters per branch
        """
        if layer is None or layer.renderer() is None:
            return
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            return

        try:
            renderer = layer.renderer()
            expr = f'coalesce("branch_index",0) * {float(offset_mm)}'

            def apply_on_symbol(sym):
                """Apply offset to all symbol layers."""
                if sym is None:
                    return
                try:
                    for sl in sym.symbolLayers():
                        # Base offset 0, units = mm
                        try:
                            if hasattr(sl, "setOffsetUnit"):
                                sl.setOffsetUnit(QgsUnitTypes.RenderMillimeters)
                            if hasattr(sl, "setOffset"):
                                sl.setOffset(0.0)
                        except Exception as e:
                            logger.debug(f"Error in StyleManager.apply_on_symbol: {e}")
                        # Data-defined offset by branch_index
                        try:
                            prop_enum = getattr(QgsSymbolLayer, "PropertyOffset", None)
                            if prop_enum is not None and hasattr(sl, "setDataDefinedProperty"):
                                sl.setDataDefinedProperty(
                                    prop_enum,
                                    QgsProperty.fromExpression(expr),
                                )
                        except Exception as e:
                            logger.debug(f"Error in StyleManager.apply_on_symbol: {e}")
                        # Sub-symbols (marker line etc.)
                        if hasattr(sl, "subSymbol") and callable(sl.subSymbol):
                            subsym = sl.subSymbol()
                            if subsym is not None:
                                apply_on_symbol(subsym)
                except Exception as e:
                    logger.debug(f"Error in StyleManager.apply_on_symbol: {e}")

            # Handle different renderer types
            if not isinstance(renderer, QgsCategorizedSymbolRenderer):
                sym = None
                if hasattr(renderer, "symbol"):
                    try:
                        sym = renderer.symbol()
                    except Exception as e:
                        sym = None
                if sym is not None:
                    apply_on_symbol(sym)
            else:
                cats = renderer.categories()
                for cat in cats:
                    apply_on_symbol(cat.symbol())
                layer.setRenderer(renderer)

            try:
                layer.triggerRepaint()
            except Exception as e:
                logger.debug(f"Error in StyleManager.apply_on_symbol: {e}")
        except Exception as e:
            logger.debug(f"Error in StyleManager.apply_on_symbol: {e}")

    # =========================================================================
    # ELEMENT LAYER STYLE
    # =========================================================================

    def stylize_element_layer(self, layer, svg_path=None, size=6):
        """
        Apply element layer style with SVG marker or default circle.

        Args:
            layer: QgsVectorLayer for elements
            svg_path: Path to SVG icon (optional)
            size: Marker size in map units
        """
        if not layer or not layer.isValid():
            return

        try:
            from qgis.core import QgsSvgMarkerSymbolLayer

            if svg_path:
                symbol = QgsMarkerSymbol.createSimple({
                    'name': 'circle',
                    'size': '5',
                    'size_unit': 'MapUnit'
                })
                try:
                    svg_layer = QgsSvgMarkerSymbolLayer(svg_path)
                    try:
                        svg_layer.setSize(float(size))
                    except Exception as e:
                        logger.debug(f"Error in StyleManager.stylize_element_layer: {e}")
                    try:
                        svg_layer.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
                    except Exception as e:
                        svg_layer.setSizeUnit(QgsUnitTypes.RenderMapUnits)
                    symbol.changeSymbolLayer(0, svg_layer)
                except Exception as e:
                    logger.debug(f"Error in StyleManager.stylize_element_layer: {e}")
            else:
                symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'size': '5'})

            try:
                layer.renderer().setSymbol(symbol)
            except Exception as e:
                logger.debug(f"Error in StyleManager.stylize_element_layer: {e}")

            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in StyleManager.stylize_element_layer: {e}")

    # =========================================================================
    # FIXED TEXT LABEL UTILITY
    # =========================================================================

    def apply_fixed_text_label(self, layer, field_name, font_size=8.0, offset_y=5.0):
        """
        Apply fixed-size text label to a layer.

        Args:
            layer: QgsVectorLayer
            field_name: Field to use for label text
            font_size: Font size in points
            offset_y: Y offset for label placement
        """
        if not layer or not layer.isValid():
            return

        try:
            s = QgsPalLayerSettings()
            s.fieldName = field_name
            s.enabled = True

            tf = QgsTextFormat()
            tf.setSize(font_size)
            try:
                tf.setSizeUnit(QgsUnitTypes.RenderPoints)
            except Exception as e:
                logger.debug(f"Error in StyleManager.apply_fixed_text_label: {e}")

            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.8)
            buf.setColor(QColor(255, 255, 255))
            tf.setBuffer(buf)

            s.setFormat(tf)

            # Offset
            s.yOffset = offset_y

            layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
            layer.setLabelsEnabled(True)
        except Exception as e:
            logger.debug(f"Error in StyleManager.apply_fixed_text_label: {e}")


# Module-level convenience functions for backward compatibility

def get_style_manager(iface, plugin=None):
    """Get a StyleManager instance."""
    return StyleManager(iface, plugin)


# Standalone style functions for module-level usage

def stylize_objects_layer(layer):
    """Apply objects layer style (standalone function for backward compat)."""
    sm = StyleManager(None)
    sm.stylize_objects_layer(layer)


__all__ = [
    'StyleManager',
    'get_style_manager',
    'stylize_objects_layer',
]
