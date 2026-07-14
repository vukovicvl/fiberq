"""
FiberQ v2 - Element Placement Tools

Map tools for placing and managing FiberQ elements (ODF, TB, OTB, etc.)
Phase 2.1: Extracted from extracted_classes.py
"""

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog, QDialog

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsWkbTypes, QgsMarkerSymbol,
    QgsSvgMarkerSymbolLayer, QgsUnitTypes, QgsSimpleMarkerSymbolLayer,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling
)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker, QgsMapToolIdentify

# Import from legacy bridge for compatibility
from ..utils.legacy_bridge import (
    ELEMENT_DEFS,
    NASTAVAK_DEF,
    _apply_element_aliases,
    _apply_fixed_text_label,
    _default_fields_for,
    _normalize_name,
)

# Import element dialog
from ..dialogs.element_dialog import PrePlaceAttributesDialog

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class PlaceElementTool(QgsMapToolEmitPoint):
    """Generalized tool for placing point elements on the route.

    target_layer_name: name of the layer to write to (automatically created if doesn't exist)
    symbol_spec: dict for QgsMarkerSymbol.createSimple or {'svg_path': '/path/to/icon.svg'}
    """

    def __init__(self, canvas, target_layer_name, symbol_spec=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.target_layer_name = target_layer_name
        self.symbol_spec = symbol_spec or {'name': 'diamond', 'color': 'red', 'size': '5', 'size_unit': 'MapUnit'}
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setColor(QColor(255, 0, 0))
        self.snap_marker.setIconType(QgsVertexMarker.IconType.ICON_CIRCLE)
        self.snap_marker.setIconSize(14)
        self.snap_marker.setPenWidth(3)
        self.snap_marker.hide()
        self._last_snap_point = None

    def _apply_prekid_style(self, layer):
        """Special style for fiber break points:
        - small black circle
        - fixed size in millimeters (doesn't change with zoom)
        - no labels
        """
        if layer is None:
            return

        try:
            simple = QgsSimpleMarkerSymbolLayer()
            simple.setShape(QgsSimpleMarkerSymbolLayer.Shape.Circle)
            simple.setSize(2.4)  # mm
            simple.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMetersInMapUnits)
            simple.setColor(QColor(0, 0, 0))  # black fill
            simple.setOutlineColor(QColor(0, 0, 0))  # black outline
            simple.setOutlineWidth(0.2)
            simple.setOutlineWidthUnit(QgsUnitTypes.RenderUnit.RenderMetersInMapUnits)

            sym = QgsMarkerSymbol()
            sym.changeSymbolLayer(0, simple)
            layer.renderer().setSymbol(sym)
            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in PlaceElementTool._apply_prekid_style: {e}")

    def canvasMoveEvent(self, event):
        """Snap to lines (Cables/Route) OR to nodes (Poles/Manholes)."""
        point = self.toMapCoordinates(event.pos())

        line_layers = []
        node_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry and lyr.name() in (
                    "Kablovi_podzemni", "Kablovi_vazdusni", "Underground cables",
                    "Aerial cables", "Route", "Route"
                ):
                    line_layers.append(lyr)
                if lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and lyr.name() in (
                    "Poles", "Poles", "OKNA", "Manholes"
                ):
                    node_layers.append(lyr)
            except Exception as e:
                logger.debug(f"Error in PlaceElementTool.canvasMoveEvent: {e}")

        min_dist = None
        snapped_point = None
        tolerance = self.canvas.mapUnitsPerPixel() * 10

        # Lines
        for layer in line_layers:
            for feat in layer.getFeatures():
                geom = feat.geometry()
                if not geom:
                    continue
                dist, snap, vAfter, seg_idx = geom.closestSegmentWithContext(point)
                if min_dist is None or dist < min_dist:
                    min_dist = dist
                    snapped_point = snap

        # Nodes
        for lyr in node_layers:
            for f in lyr.getFeatures():
                geom = f.geometry()
                if not geom or geom.isEmpty():
                    continue
                try:
                    pt = geom.asPoint()
                except Exception as e:
                    logger.debug(f"skipping node without point geometry: {e}")
                    continue
                d = QgsPointXY(point).distance(QgsPointXY(pt))
                if min_dist is None or d < min_dist:
                    min_dist = d
                    snapped_point = QgsPointXY(pt)

        if snapped_point and min_dist is not None and min_dist < tolerance:
            self.snap_marker.setCenter(snapped_point)
            self.snap_marker.show()
            self._last_snap_point = snapped_point
        else:
            self.snap_marker.hide()
            self._last_snap_point = None

    def canvasPressEvent(self, event):
        # Right click – cancel command
        if event.button() == Qt.MouseButton.RightButton:
            try:
                self.snap_marker.hide()
            except Exception as e:
                logger.debug(f"Error in PlaceElementTool.canvasPressEvent: {e}")
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in PlaceElementTool.canvasPressEvent: {e}")
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        final_point = getattr(self, '_last_snap_point', None)
        if final_point is None:
            # Allow without snap (click where user clicked)
            final_point = self.toMapCoordinates(event.pos())

        # Pre-placement dialog (dynamic attributes)
        existing_layer = None
        try:
            for lyr in QgsProject.instance().mapLayers().values():
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and lyr.name() == self.target_layer_name:
                    existing_layer = lyr
                    break
        except Exception:
            existing_layer = None

        # If target is 'Prekid', automatically set name without dialog
        if 'prekid' in self.target_layer_name.lower():
            _attrs = {'naziv': 'Prekid'}
            ok = True
        else:
            try:
                dlg = PrePlaceAttributesDialog(self.target_layer_name, existing_layer)
                ok = (dlg.exec() == QDialog.DialogCode.Accepted)
                _attrs = dlg.values() if ok else {}
            except Exception:
                naziv, ok = QInputDialog.getText(None, "Placing elements", f"Name ({self.target_layer_name}):")
                _attrs = {'naziv': naziv} if ok and naziv else {}

        if not ok or not _attrs.get('naziv'):
            QMessageBox.warning(None, "Element", "Name not entered!")
            self.snap_marker.hide()
            return

        # Find or create layer
        elem_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and lyr.name() == self.target_layer_name:
                elem_layer = lyr
                break

        if elem_layer is None:
            crs = self.canvas.mapSettings().destinationCrs().authid()
            elem_layer = QgsVectorLayer(f"Point?crs={crs}", self.target_layer_name, "memory")
            pr = elem_layer.dataProvider()

            # Add fields based on dialog spec
            try:
                specs = _default_fields_for(self.target_layer_name)
            except Exception:
                specs = [("naziv", "Naziv", "text", "", None)]

            fields = []
            for (key, label, kind, default, opts) in specs:
                qt = QVariant.String
                if kind in ("int", "year"):
                    qt = QVariant.Int
                elif kind == "double":
                    qt = QVariant.Double
                elif kind == "enum":
                    qt = QVariant.String
                fields.append(QgsField(key, qt))

            # Always ensure 'naziv' exists
            if not any(f.name() == "naziv" for f in fields):
                fields.insert(0, QgsField("naziv", QVariant.String))

            pr.addAttributes(fields)
            elem_layer.updateFields()
            _apply_element_aliases(elem_layer)

            # Style
            spec = self.symbol_spec
            if isinstance(spec, dict) and 'svg_path' in spec:
                symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'size': '5', 'size_unit': 'MapUnit'})
                try:
                    svg_layer = QgsSvgMarkerSymbolLayer(spec['svg_path'])
                    try:
                        svg_layer.setSize(float(spec.get('size', 6)))
                    except Exception as e:
                        logger.debug(f"Error in PlaceElementTool.canvasPressEvent: {e}")
                    try:
                        svg_layer.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMetersInMapUnits)
                    except Exception:
                        svg_layer.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMapUnits)
                    symbol.changeSymbolLayer(0, svg_layer)
                except Exception as e:
                    logger.debug(f"Error in PlaceElementTool.canvasPressEvent: {e}")
            else:
                symbol = QgsMarkerSymbol.createSimple(spec)

            elem_layer.renderer().setSymbol(symbol)

            # Label
            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "naziv"
            label_settings.enabled = True
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            elem_layer.setLabeling(labeling)
            elem_layer.setLabelsEnabled(True)
            _apply_fixed_text_label(elem_layer, 'naziv', 8.0, 5.0)
            QgsProject.instance().addMapLayer(elem_layer)
        else:
            # Ensure all fields used by the dialog exist on the layer
            try:
                specs = _default_fields_for(self.target_layer_name)
            except Exception:
                specs = [("naziv", "Naziv", "text", "", None)]

            to_add = []
            for (key, label, kind, default, opts) in specs:
                if elem_layer.fields().indexFromName(key) == -1:
                    qt = QVariant.String
                    if kind in ("int", "year"):
                        qt = QVariant.Int
                    elif kind == "double":
                        qt = QVariant.Double
                    elif kind == "enum":
                        qt = QVariant.String
                    to_add.append(QgsField(key, qt))

            if to_add:
                elem_layer.startEditing()
                elem_layer.dataProvider().addAttributes(to_add)
                elem_layer.updateFields()
                elem_layer.commitChanges()

            _apply_element_aliases(elem_layer)

        # If this is 'Prekid vlakna' layer, apply special style
        if 'prekid' in self.target_layer_name.lower():
            self._apply_prekid_style(elem_layer)

        # WP1b identity invariant: ensure the fiberq_uuid column exists on the
        # element layer (covers both the newly created and found-existing
        # branches above) before building the feature, so set_feature_uuid()
        # below actually stamps it instead of silently no-opping.
        try:
            from ..utils.uuid_utils import ensure_uuid_field
            ensure_uuid_field(elem_layer)
        except Exception as e:
            logger.debug(f"Error ensuring fiberq_uuid on element layer: {e}")

        # Write point
        feat = QgsFeature(elem_layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(final_point))
        name_map = {_normalize_name(f.name()): f.name() for f in elem_layer.fields()}
        for k, v in _attrs.items():
            fname = name_map.get(k, k)
            try:
                feat.setAttribute(fname, v)
            except Exception as e:
                logger.debug(f"Error in PlaceElementTool.canvasPressEvent: {e}")

        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(feat)
        except Exception as e:
            logger.debug(f"Error setting UUID on element: {e}")

        elem_layer.startEditing()
        elem_layer.addFeature(feat)
        elem_layer.commitChanges()

        elem_layer.triggerRepaint()
        self.snap_marker.hide()

        # Record for undo (v1.2 — Feature 2)
        try:
            _plugin = getattr(self, 'plugin', None)
            if _plugin and hasattr(_plugin, 'undo_manager') and _plugin.undo_manager:
                _plugin.undo_manager.record_add(elem_layer, feat)
        except Exception as e:
            logger.debug(f"Error recording undo for element: {e}")

        QMessageBox.information(None, "FiberQ", "Element placed!")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            try:
                self.snap_marker.hide()
            except Exception as e:
                logger.debug(f"Error in PlaceElementTool.keyPressEvent: {e}")
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in PlaceElementTool.keyPressEvent: {e}")


class ChangeElementTypeTool(QgsMapToolIdentify):
    """Click on element (from 'Placing elements'), choose new type and move to appropriate layer with style."""

    def __init__(self, iface, core):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.core = core
        self.canvas = iface.mapCanvas()
        try:
            self.snap_marker = QgsVertexMarker(self.canvas)
            self.snap_marker.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
            self.snap_marker.setPenWidth(3)
            self.snap_marker.setIconSize(14)
            self.snap_marker.setColor(QColor(0, 200, 0))
            self.snap_marker.hide()
        except Exception:
            self.snap_marker = None

    def activate(self):
        try:
            if self.snap_marker:
                self.snap_marker.show()
            self.iface.messageBar().pushInfo("Change element type", "Click on an element and choose a new type.")
        except Exception as e:
            logger.debug(f"Error in ChangeElementTypeTool.activate: {e}")
        super().activate()

    def deactivate(self):
        try:
            if self.snap_marker:
                self.snap_marker.hide()
        except Exception as e:
            logger.debug(f"Error in ChangeElementTypeTool.deactivate: {e}")
        super().deactivate()

    def _element_names(self):
        """Element types offered in combo - English names only (same as Placing elements list)."""
        names = []
        try:
            for edef in ELEMENT_DEFS:
                nm = edef.get("name")
                if nm and nm not in names:
                    names.append(nm)
        except Exception as e:
            logger.debug(f"Error in ChangeElementTypeTool._element_names: {e}")

        # Add Joint Closures if defined
        try:
            if NASTAVAK_DEF:
                jc_name = NASTAVAK_DEF.get("name", "Joint Closures")
                if jc_name and jc_name not in names:
                    names.append(jc_name)
        except Exception as e:
            logger.debug(f"Error in ChangeElementTypeTool._element_names: {e}")

        return names

    def _is_element_layer(self, lyr):
        try:
            if not (isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry):
                return False

            name = (lyr.name() or "").strip()

            # English names (Placing elements)
            if name in self._element_names():
                return True

            # Legacy Serbian names for old projects
            return name in ("Nastavci", "Nastavak")
        except Exception:
            return False

    def canvasReleaseEvent(self, e):
        # Identify hit on point layers that match element names
        res = self.identify(e.pos().x(), e.pos().y(), self.TopDownAll, self.VectorLayer)
        if not res:
            try:
                QMessageBox.information(self.iface.mainWindow(), "Change element type", "You did not click on any element.")
            except Exception as e:
                logger.debug(f"Error in ChangeElementTypeTool.canvasReleaseEvent: {e}")
            return

        hit_layer, hit_fid = None, None
        for hit in res:
            layer = getattr(hit, "mLayer", None) or getattr(hit, "layer", None)
            feature = getattr(hit, "mFeature", None) or getattr(hit, "feature", None)
            if layer is not None and feature is not None and self._is_element_layer(layer):
                hit_layer = layer
                try:
                    hit_fid = int(feature.id())
                except Exception:
                    hit_fid = feature.id()
                break

        if hit_layer is None or hit_fid is None:
            try:
                QMessageBox.information(self.iface.mainWindow(), "Change element type", "Click exactly on a point element from the placement list.")
            except Exception as e:
                logger.debug(f"Error in ChangeElementTypeTool.canvasReleaseEvent: {e}")
            return

        # Ask for new type (combo)
        names = self._element_names()
        try:
            current = hit_layer.name()
        except Exception:
            current = ""
        try:
            new_name, ok = QInputDialog.getItem(
                self.iface.mainWindow(), "Change element type", "New type:",
                names, max(0, names.index(current)) if current in names else 0, False
            )
        except Exception:
            new_name, ok = (names[0] if names else "", True)

        if not ok or not new_name or new_name == current:
            return

        try:
            self.core._change_element_type(hit_layer, hit_fid, new_name)
            try:
                self.iface.messageBar().pushSuccess("Change element type", f"Element changed to: {new_name}")
            except Exception as e:
                logger.debug(f"Error in ChangeElementTypeTool.canvasReleaseEvent: {e}")
        except Exception as e:
            try:
                QMessageBox.critical(self.iface.mainWindow(), "Change element type", f"Error: {e}")
            except Exception as e:
                logger.debug(f"Error in ChangeElementTypeTool.canvasReleaseEvent: {e}")
        finally:
            try:
                self.canvas.unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in ChangeElementTypeTool.canvasReleaseEvent: {e}")


__all__ = ['PlaceElementTool', 'ChangeElementTypeTool']
