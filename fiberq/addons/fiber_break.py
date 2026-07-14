from datetime import datetime

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsDistanceArea,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsSimpleMarkerSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsVertexMarker

from ..utils.logger import get_logger

logger = get_logger(__name__)


class FiberBreakTool(QgsMapTool):
    """
    Klik na kabl upisuje tačku u sloj 'Fiber break' sa atributima:
    - cable_layer_id (str)
    - cable_fid (int)
    - distance_m (float)  udaljenost duž polilinije do mesta prekida
    - segments_hit (int)  heuristika (=1)
    - vreme (str, 'YYYY-MM-DD HH:MM')

    Zadržava kompatibilnost sa postojećim stilom (polje 'naziv' za label).
    """

    def __init__(self, iface):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
        self.snap_marker.setPenWidth(2)
        self.snap_marker.setIconSize(12)
        self.snap_marker.hide()

    def _apply_break_field_aliases(self, layer: QgsVectorLayer):
        """Set English field aliases for the Fiber break layer (user view)."""
        if layer is None:
            return

        try:
            alias_map = {
                "naziv": "Name",
                "cable_layer_id": "Cable layer ID",
                "cable_fid": "Cable feature ID",
                "distance_m": "Distance (m)",
                "segments_hit": "Segments hit",
                "vreme": "Time",
            }
            fields = layer.fields()
            for field_name, alias in alias_map.items():
                idx = fields.indexOf(field_name)
                if idx != -1:
                    layer.setFieldAlias(idx, alias)

            try:
                layer.updateFields()
            except Exception as exc:
                logger.debug(f"Error in FiberBreakTool._apply_break_field_aliases: {exc}")

            try:
                layer.triggerRepaint()
            except Exception as exc:
                logger.debug(f"Error in FiberBreakTool._apply_break_field_aliases: {exc}")
        except Exception as exc:
            logger.debug(f"Error in FiberBreakTool._apply_break_field_aliases: {exc}")

    def _apply_break_style(self, layer: QgsVectorLayer):
        """
        Stil za 'Fiber break':

        1) Prvo probamo da učitamo QML stil iz styles/Fiber break.qml
           – isti onaj koji koristi Preview Map.
        2) Ako to omane iz bilo kog razloga, padamo na stari "mali crni krug" u mm.
        """
        if layer is None:
            return

        try:
            import os

            plugin_dir = os.path.dirname(os.path.dirname(__file__))
            qml_path = os.path.join(plugin_dir, "styles", "Fiber break.qml")
            if os.path.exists(qml_path):
                layer.loadNamedStyle(qml_path)
                layer.triggerRepaint()
                return
        except Exception as e:
            logger.debug(f"could not load Fiber break QML style: {e}")

        try:
            from qgis.PyQt.QtGui import QColor
        except Exception:
            return

        try:
            marker = QgsSimpleMarkerSymbolLayer()
            marker.setShape(QgsSimpleMarkerSymbolLayer.Shape.Circle)
            marker.setSize(2.4)
            marker.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMillimeters)
            marker.setColor(QColor(0, 0, 0))
            marker.setOutlineColor(QColor(0, 0, 0))
            marker.setOutlineWidth(0.2)
            marker.setOutlineWidthUnit(QgsUnitTypes.RenderUnit.RenderMillimeters)

            sym = QgsMarkerSymbol()
            sym.changeSymbolLayer(0, marker)

            layer.setRenderer(QgsSingleSymbolRenderer(sym))
            layer.setLabelsEnabled(False)
            layer.triggerRepaint()
        except Exception as exc:
            logger.debug(f"Error in FiberBreakTool._apply_break_style: {exc}")

    def _on_scale_changed(self):
        """
        Više nam ne treba dinamičko skaliranje.
        Stil je već u ekranskim jedinicama (milimetri),
        tako da ovde namerno ne radimo ništa.
        """
        return

    def _ensure_break_layer(self) -> QgsVectorLayer:
        """
        Return existing Fiber break layer or create it.

        Backward compatible with old name 'Prekid vlakna'.
        """
        proj = QgsProject.instance()

        for lyr in proj.mapLayers().values():
            try:
                is_break_layer = (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry  # noqa: W503
                    and lyr.name() in ("Prekid vlakna", "Fiber break")  # noqa: W503
                )
                if not is_break_layer:
                    continue

                if lyr.name() == "Prekid vlakna":
                    try:
                        lyr.setName("Fiber break")
                    except Exception as exc:
                        logger.debug(f"Error in FiberBreakTool._ensure_break_layer: {exc}")

                self._apply_break_style(lyr)
                self._apply_break_field_aliases(lyr)

                try:
                    from ..utils.uuid_utils import ensure_uuid_field

                    ensure_uuid_field(lyr)
                except Exception as e:
                    logger.debug(f"could not ensure uuid field on Fiber break layer: {e}")

                return lyr
            except Exception as e:
                logger.debug(f"skipping layer while locating Fiber break layer: {e}")
                continue

        crs_authid = self.canvas.mapSettings().destinationCrs().authid()
        vl = QgsVectorLayer(f"Point?crs={crs_authid}", "Fiber break", "memory")
        pr = vl.dataProvider()
        pr.addAttributes(
            [
                QgsField("naziv", QVariant.String),
                QgsField("cable_layer_id", QVariant.String),
                QgsField("cable_fid", QVariant.Int),
                QgsField("distance_m", QVariant.Double),
                QgsField("segments_hit", QVariant.Int),
                QgsField("vreme", QVariant.String),
                QgsField("fiberq_uuid", QVariant.String),
            ]
        )
        vl.updateFields()

        proj.addMapLayer(vl)
        self._apply_break_style(vl)
        self._apply_break_field_aliases(vl)
        return vl

    def _iter_line_layers(self):
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry  # noqa: W503
                    and lyr.isValid()  # noqa: W503
                ):
                    yield lyr
            except Exception as e:
                logger.debug(f"skipping layer while iterating line layers: {e}")
                continue

    def _flatten_polyline(self, geom: QgsGeometry):
        """Return list of QgsPointXY vertices for (Multi)LineString geometry; empty list otherwise."""
        try:
            if geom.isMultipart():
                multi = geom.asMultiPolyline()
                if multi and len(multi) > 0:
                    return [QgsPointXY(p) for p in multi[0]]
                return []

            polyline = geom.asPolyline()
            return [QgsPointXY(p) for p in polyline] if polyline else []
        except Exception:
            return []

    def _measure_line(self, pts):
        da = QgsDistanceArea()
        try:
            da.setSourceCrs(
                self.canvas.mapSettings().destinationCrs(),
                QgsProject.instance().transformContext(),
            )
        except Exception as exc:
            logger.debug(f"Error in FiberBreakTool._measure_line: {exc}")

        try:
            da.setEllipsoid(self.canvas.mapSettings().destinationCrs().ellipsoidAcronym())
        except Exception as exc:
            logger.debug(f"Error in FiberBreakTool._measure_line: {exc}")

        total = 0.0
        for i in range(1, len(pts)):
            total += da.measureLine(pts[i - 1], pts[i])
        return total, da

    def canvasMoveEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        self.snap_marker.setCenter(point)
        self.snap_marker.show()

    def canvasReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        map_pt = self.toMapCoordinates(event.pos())
        map_pt_geom = QgsGeometry.fromPointXY(map_pt)

        nearest = None
        nearest_dist = None
        for lyr in self._iter_line_layers():
            for feat in lyr.getFeatures():
                try:
                    geom = feat.geometry()
                    if geom is None:
                        continue
                    dist = geom.distance(map_pt_geom)
                except Exception as e:
                    logger.debug(f"could not compute distance to feature: {e}")
                    continue

                if nearest_dist is None or (dist is not None and dist < nearest_dist):
                    nearest = (lyr, feat)
                    nearest_dist = dist

        if not nearest:
            QMessageBox.warning(self.iface.mainWindow(), "Fiber break", "No cable found nearby.")
            return

        lyr, feat = nearest
        geom = feat.geometry()

        try:
            _, snapped_pt, _, seg_index = geom.closestSegmentWithContext(map_pt)
        except Exception:
            snapped_pt = map_pt
            seg_index = 0

        pts = self._flatten_polyline(geom)
        if not pts:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Fiber break",
                "Cable geometry is not a line.",
            )
            return

        total_len_to_seg = 0.0
        _, da = self._measure_line(pts)

        if seg_index is None or seg_index < 0:
            seg_index = 0
        seg_index = min(seg_index, max(0, len(pts) - 2))

        for i in range(1, seg_index + 1):
            total_len_to_seg += da.measureLine(pts[i - 1], pts[i])

        try:
            seg_start = pts[seg_index]
            partial = da.measureLine(seg_start, snapped_pt)
        except Exception:
            partial = 0.0

        distance_m = float(total_len_to_seg + partial)

        ev_layer = self._ensure_break_layer()
        ev = QgsFeature(ev_layer.fields())
        ev.setGeometry(QgsGeometry.fromPointXY(snapped_pt if snapped_pt else map_pt))
        ev["naziv"] = "Fiber break"
        ev["cable_layer_id"] = lyr.id()

        try:
            ev["cable_fid"] = int(feat.id())
        except Exception:
            ev["cable_fid"] = -1

        ev["distance_m"] = round(distance_m, 3)
        ev["segments_hit"] = 1
        ev["vreme"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            from ..utils.uuid_utils import set_feature_uuid

            set_feature_uuid(ev)
        except Exception as e:
            logger.debug(f"could not set feature uuid: {e}")

        ev_layer.startEditing()
        ev_layer.addFeature(ev)
        ev_layer.commitChanges()
        ev_layer.triggerRepaint()

        seg_count = max(0, len(pts) - 1)
        msg = (
            f"Cable layer: {lyr.name()} • "
            f"Feature #{int(feat.id())} • "
            f"Distance: {round(distance_m, 2)} m • "
            f"Segments: {seg_count}"
        )
        try:
            self.iface.messageBar().pushInfo("Fiber break", msg)
        except Exception:
            QMessageBox.information(self.iface.mainWindow(), "Fiber break", msg)

        self.snap_marker.setCenter(snapped_pt if snapped_pt else map_pt)
        self.snap_marker.show()

    def canvasPressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.canvas.unsetMapTool(self)
            try:
                self.iface.actionPan().trigger()
            except Exception as exc:
                logger.debug(f"Error in FiberBreakTool.canvasPressEvent: {exc}")
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.canvas.unsetMapTool(self)
            try:
                self.iface.actionPan().trigger()
            except Exception as exc:
                logger.debug(f"Error in FiberBreakTool.keyPressEvent: {exc}")

    def deactivate(self):
        """
        Poziva se automatski kada korisnik promeni alat.
        Ovde sakrivamo krstić da ne ostaje na mapi.
        """
        try:
            if self.snap_marker is not None:
                self.snap_marker.hide()
        except Exception as exc:
            logger.debug(f"Error in FiberBreakTool.deactivate: {exc}")

        super().deactivate()
