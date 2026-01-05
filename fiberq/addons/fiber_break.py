
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes, QgsField, QgsFeature,
    QgsGeometry, QgsDistanceArea, QgsUnitTypes, QgsPointXY, QgsCoordinateTransformContext,
    QgsMarkerSymbol, QgsSimpleMarkerSymbolLayer, QgsSingleSymbolRenderer
)
from qgis.gui import QgsMapTool, QgsVertexMarker

class FiberBreakTool(QgsMapTool):
    """
    Click on cable to record a point in 'Fiber break' layer with attributes:
    - kabl_layer_id (str)
    - kabl_fid (int)
    - distance_m (float)  distance along polyline to break location
    - segments_hit (int)  heuristic (=1)
    - vreme (str, 'YYYY-MM-DD HH:MM')
    Maintains compatibility with existing style (field 'naziv' for label).
    """
    def __init__(self, iface,):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setIconType(QgsVertexMarker.ICON_CROSS)
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
                "kabl_layer_id": "Cable layer ID",
                "kabl_fid": "Cable feature ID",
                "distance_m": "Distance (m)",
                "segments_hit": "Segments hit",
                "vreme": "Time",
            }
            fields = layer.fields()
            for field_name, alias in alias_map.items():
                idx = fields.indexOf(field_name)
                if idx != -1:
                    layer.setFieldAlias(idx, alias)

            # nateraj UI da osveži
            try:
                layer.updateFields()
            except Exception:
                pass
            try:
                layer.triggerRepaint()
            except Exception:
                pass

        except Exception:
            pass



    def _apply_break_style(self, layer: QgsVectorLayer):
        """
        Stil za 'Fiber break':

        1) Prvo probamo da učitamo QML stil iz styles/Fiber break.qml
            – isti onaj koji koristi Preview Map (i za koji si potvrdio da radi kako treba).
        2) Ako to omane iz bilo kog razloga, padamo na stari "mali crni krug" u mm.
        """
        if layer is None:
            return

        # --- probaj QML stil kao u Preview Map ---
        try:
            import os
            plugin_dir = os.path.dirname(os.path.dirname(__file__))  # koren plugina (gde je folder 'styles')
            qml_path = os.path.join(plugin_dir, "styles", "Fiber break.qml")
            if os.path.exists(qml_path):
                layer.loadNamedStyle(qml_path)
                layer.triggerRepaint()
            return
        except Exception:
            # ako nešto pukne, nastavljamo na fallback ispod
            pass
        # --- fallback: ručno napravljen mali crni krug u mm ---
        try:
            from qgis.PyQt.QtGui import QColor
        except Exception:
            return

        try:
            marker = QgsSimpleMarkerSymbolLayer()
        except Exception:
            return

        try:
            marker.setShape(QgsSimpleMarkerSymbolLayer.Circle)

            # ostavi mali krug, ali sada je ovo samo rezervna varijanta
            marker.setSize(2.4)
            marker.setSizeUnit(QgsUnitTypes.RenderMillimeters)

            marker.setColor(QColor(0, 0, 0))
            marker.setOutlineColor(QColor(0, 0, 0))
            marker.setOutlineWidth(0.2)
            marker.setOutlineWidthUnit(QgsUnitTypes.RenderMillimeters)

            sym = QgsMarkerSymbol()
            sym.changeSymbolLayer(0, marker)

            layer.setRenderer(QgsSingleSymbolRenderer(sym))
            layer.setLabelsEnabled(False)
            layer.triggerRepaint()
        except Exception:
            pass




    def _on_scale_changed(self):
        """
        Više nam ne treba dinamičko skaliranje.
        Stil je već u ekranskim jedinicama (milimetri),
        tako da ovde namerno ne radimo ništa.
        """
        return



    # ---------- helpers ----------
    def _ensure_break_layer(self) -> QgsVectorLayer:
        """
        Return existing Fiber break layer or create it.

        Backward compatible with old name 'Prekid vlakna'.
        """
        proj = QgsProject.instance()

        # 1) pronađi postojeći sloj
        for lyr in proj.mapLayers().values():
            if (
                isinstance(lyr, QgsVectorLayer)
                and lyr.geometryType() == QgsWkbTypes.PointGeometry
                and lyr.name() in ("Prekid vlakna", "Fiber break")
            ):
                # preimenuj stari sloj ako treba
                if lyr.name() == "Prekid vlakna":
                    try:
                        lyr.setName("Fiber break")
                    except Exception:
                        pass

                # STIL pa ALIAS (stil/QML pregazi alias-e ako ide posle)
                self._apply_break_style(lyr)
                self._apply_break_field_aliases(lyr)
                return lyr

        # 2) napravi novi sloj
        crs_authid = self.canvas.mapSettings().destinationCrs().authid()
        vl = QgsVectorLayer(f"Point?crs={crs_authid}", "Fiber break", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("naziv", QVariant.String),
            QgsField("kabl_layer_id", QVariant.String),
            QgsField("kabl_fid", QVariant.Int),
            QgsField("distance_m", QVariant.Double),
            QgsField("segments_hit", QVariant.Int),
            QgsField("vreme", QVariant.String),
        ])
        vl.updateFields()

        # dodaj u projekat pa onda alias + stil (da UI sigurno "uhvati" promenu)
        proj.addMapLayer(vl)
        self._apply_break_style(vl)          # prvo stil (loadNamedStyle)
        self._apply_break_field_aliases(vl)  # pa tek onda alias
        return vl


    def _iter_line_layers(self):
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.LineGeometry and lyr.isValid():
                    yield lyr
            except Exception:
                continue

    def _flatten_polyline(self, geom: QgsGeometry):
        """Return list of QgsPointXY vertices for (Multi)LineString geometry; empty list otherwise."""
        try:
            if geom.isMultipart():
                m = geom.asMultiPolyline()
                if m and len(m) > 0:
                    return [QgsPointXY(p) for p in m[0]]
                return []
            else:
                pl = geom.asPolyline()
                return [QgsPointXY(p) for p in pl] if pl else []
        except Exception:
            return []

    def _measure_line(self, pts):
        da = QgsDistanceArea()
        try:
            da.setSourceCrs(self.canvas.mapSettings().destinationCrs(), QgsProject.instance().transformContext())
        except Exception:
            pass
        try:
            da.setEllipsoid(self.canvas.mapSettings().destinationCrs().ellipsoidAcronym())
        except Exception:
            pass
        total = 0.0
        for i in range(1, len(pts)):
            total += da.measureLine(pts[i-1], pts[i])
        return total, da

    # ---------- map tool ----------
    def canvasMoveEvent(self, e):
        p = self.toMapCoordinates(e.pos())
        self.snap_marker.setCenter(p)
        self.snap_marker.show()

    def canvasReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        map_pt = self.toMapCoordinates(e.pos())
        map_pt_geom = QgsGeometry.fromPointXY(map_pt)

        # Find nearest line feature among all visible line layers
        nearest = None
        nearest_dist = None
        for lyr in self._iter_line_layers():
            for feat in lyr.getFeatures():
                try:
                    d = feat.geometry().distance(map_pt_geom)
                except Exception:
                    continue
                if nearest_dist is None or (d is not None and d < nearest_dist):
                    nearest = (lyr, feat)
                    nearest_dist = d

        if not nearest:
            QMessageBox.warning(self.iface.mainWindow(), "Fiber break", "No cable found nearby.")
            return

        lyr, feat = nearest
        geom = feat.geometry()

        # Snap to closest segment and compute distance along the polyline
        try:
            dist_to_seg, snapped_pt, v_after, seg_index = geom.closestSegmentWithContext(map_pt)
        except Exception:
            # fallback: no segment context
            snapped_pt = map_pt
            seg_index = 0

        pts = self._flatten_polyline(geom)
        if not pts:
            QMessageBox.warning(self.iface.mainWindow(), "Fiber break", "Cable geometry is not a line.")
            return

        # cumulative distance up to segment start
        # measure using QgsDistanceArea in map/project CRS
        total_len_to_seg = 0.0
        total_len, da = self._measure_line(pts)
        if seg_index is None or seg_index < 0:
            seg_index = 0
        seg_index = min(seg_index, max(0, len(pts) - 2))
        for i in range(1, seg_index + 1):
            total_len_to_seg += da.measureLine(pts[i-1], pts[i])
        # add partial distance from segment start to snapped point
        try:
            seg_start = pts[seg_index]
            partial = da.measureLine(seg_start, snapped_pt)
        except Exception:
            partial = 0.0

        distance_m = float(total_len_to_seg + partial)

        # Write event feature
        ev_layer = self._ensure_break_layer()
        ev = QgsFeature(ev_layer.fields())
        ev.setGeometry(QgsGeometry.fromPointXY(snapped_pt if snapped_pt else map_pt))
        from datetime import datetime
        ev['naziv'] = 'Fiber break'
        ev['kabl_layer_id'] = lyr.id()
        try:
            ev['kabl_fid'] = int(feat.id())
        except Exception:
            ev['kabl_fid'] = -1
        ev['distance_m'] = round(distance_m, 3)
        ev['segments_hit'] = 1
        ev['vreme'] = datetime.now().strftime('%Y-%m-%d %H:%M')

        ev_layer.startEditing()
        ok = ev_layer.addFeature(ev)
        ev_layer.commitChanges()
        ev_layer.triggerRepaint()

        # Mini report
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


        # keep tool active (do not unset)
        self.snap_marker.setCenter(snapped_pt if snapped_pt else map_pt)
        self.snap_marker.show()

            # ---------- važno: očisti marker kad se alat ugasi ----------

    def canvasPressEvent(self, event):
        # desni klik = izlaz iz alata
        if event.button() == Qt.RightButton:
            self.canvas.unsetMapTool(self)
            # po želji prebaci na Pan alat da user može odmah da se šeta
            try:
                self.iface.actionPan().trigger()
            except Exception:
                pass
            return

        # ovde ostavi postojeću logiku za levi klik
        if event.button() != Qt.LeftButton:
            return

    def keyPressEvent(self, event):
        # ESC takođe gasi alat
        if event.key() == Qt.Key_Escape:
            self.canvas.unsetMapTool(self)
            try:
                self.iface.actionPan().trigger()
            except Exception:
                pass

    def deactivate(self):
        """
        Poziva se automatski kada korisnik promeni alat.
        Ovde sakrivamo crveni krstić da ne ostaje na mapi.
        """
        try:
            if self.snap_marker is not None:
                self.snap_marker.hide()
        except Exception:
            pass

        # pozovi i originalni deactivate
        super().deactivate()