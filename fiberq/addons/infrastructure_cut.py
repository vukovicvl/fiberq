
# -*- coding: utf-8 -*-
"""
Infrastructure cut tool for Telecom plugin.
Cuts (splits) a line feature at a clicked point with local snapping preview.
Supports any **line** layer whose name suggests cable/pipe/route, but will
prefer the active line layer if one is selected.
Tested with QGIS 3.x (incl. 3.28, 3.40 LTR APIs).
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import QMessageBox
import unicodedata
import re
from qgis.core import (
    QgsProject, QgsWkbTypes, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsRectangle, QgsFeatureRequest, QgsDistanceArea,
    QgsUnitTypes,
)
from qgis.gui import QgsMapTool, QgsVertexMarker

# Phase 5.3: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


ELIGIBLE_HINTS = (
    'kabl', 'kabel', 'fiber', 'fo', 'trasa', 'route', 'duct', 'cev', 'cevi', 'pipe',
)


class InfrastructureCutTool(QgsMapTool):
    def __init__(self, iface, plugin=None):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        self._tol_px = 12  # pixel tolerance for picking / preview
        # Marker for live snap preview
        self._marker = QgsVertexMarker(self.canvas)
        self._marker.setColor(QColor(255, 0, 0))
        self._marker.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
        self._marker.setPenWidth(2)
        self._marker.setIconSize(12)
        self._marker.hide()

        # cache
        self._last_preview_ok = False
        self._last_preview_layer = None
        self._last_preview_point = None
        self._last_preview_feat = None

    # ------------- Utility helpers -------------
    def _map_tol(self):
        try:
            return self._tol_px * self.canvas.mapSettings().mapUnitsPerPixel()
        except Exception:
            return 1.0

    def _candidate_layers(self):
        """Yield eligible line layers, preferring active layer first if valid."""
        layers = []
        al = self.iface.activeLayer()
        if isinstance(al, QgsVectorLayer) and al.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
            layers.append(al)
        for lyr in QgsProject.instance().mapLayers().values():
            if not isinstance(lyr, QgsVectorLayer):
                continue
            if lyr.geometryType() != QgsWkbTypes.GeometryType.LineGeometry:
                continue
            if lyr is al:
                continue
            name_l = lyr.name().lower()
            if any(h in name_l for h in ELIGIBLE_HINTS):
                layers.append(lyr)
        # Fallback: include all other line layers if nothing matched hints
        if not layers:
            for lyr in QgsProject.instance().mapLayers().values():
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
                    layers.append(lyr)
        return layers

    @staticmethod
    def _closest_point_on_segment(px, py, ax, ay, bx, by):
        # Project P onto segment AB
        abx, aby = bx - ax, by - ay
        apx, apy = px - ax, py - ay
        ab2 = abx * abx + aby * aby
        if ab2 == 0.0:
            return (ax, ay, 0.0, (px - ax)**2 + (py - ay)**2)
        t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
        cx, cy = ax + t * abx, ay + t * aby
        d2 = (px - cx) ** 2 + (py - cy) ** 2
        return (cx, cy, t, d2)

    @staticmethod
    def _as_polyline(geom: QgsGeometry):
        if geom.isMultipart():
            m = geom.asMultiPolyline()
            # choose the longest part by default
            part = max(m, key=lambda pts: len(pts)) if m else None
            return list(part) if part else None, True, m
        else:
            pl = geom.asPolyline()
            return list(pl) if pl else None, False, None

    @staticmethod
    def _geom_from_polyline(pts):
        return QgsGeometry.fromPolylineXY(pts)

    def _find_nearest_on_layers(self, map_pt):
        tol = self._map_tol()
        best = None  # (layer, feature, closest_point, sqdist)
        for lyr in self._candidate_layers():
            if not lyr.isValid():
                continue
            rect = QgsRectangle(map_pt.x() - tol, map_pt.y() - tol, map_pt.x() + tol, map_pt.y() + tol)
            req = QgsFeatureRequest().setFilterRect(rect).setFlags(QgsFeatureRequest.Flag.ExactIntersect)
            for f in lyr.getFeatures(req):
                g = f.geometry()
                if not g or g.isEmpty():
                    continue
                poly, is_multi, multi = self._as_polyline(g)
                if not poly or len(poly) < 2:
                    continue
                # Walk segments
                best_seg = None  # (cx, cy, i, t, d2)
                for i in range(len(poly) - 1):
                    a = poly[i]
                    b = poly[i + 1]
                    cx, cy, t, d2 = self._closest_point_on_segment(map_pt.x(), map_pt.y(), a.x(), a.y(), b.x(), b.y())
                    if best_seg is None or d2 < best_seg[-1]:
                        best_seg = (cx, cy, i, t, d2)
                if best_seg is None:
                    continue
                cx, cy, i, t, d2 = best_seg
                if d2 <= (tol * tol):
                    cp = QgsPointXY(cx, cy)
                    sqd = d2
                    if (best is None) or (sqd < best[3]):
                        best = (lyr, f, cp, sqd)
        return best  # may be None

    # ------------- Map tool events -------------
    def activate(self):
        try:
            self.iface.messageBar().pushInfo("Cutting", "Click on the line (left click) to cut it; right click/ESC aborts.")
        except Exception as e:
            logger.debug(f"Error in InfrastructureCutTool.activate: {e}")

    def deactivate(self):
        try:
            self._marker.hide()
        except Exception as e:
            logger.debug(f"Error in InfrastructureCutTool.deactivate: {e}")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape,):
            self._finish()

    def canvasMoveEvent(self, e):
        try:
            map_pt = self.toMapCoordinates(e.pos())
            found = self._find_nearest_on_layers(map_pt)
            if found is None:
                self._marker.hide()
                self._last_preview_ok = False
                return
            layer, feat, cp, _ = found
            self._marker.setCenter(cp)
            self._marker.show()
            self._last_preview_ok = True
            self._last_preview_layer = layer
            self._last_preview_point = cp
            self._last_preview_feat = feat
        except Exception as ex:
            self._flash(f'Error in move event: {ex}')
            self._marker.hide()
            self._last_preview_ok = False
            self._last_preview_layer = None
            self._last_preview_point = None
            self._last_preview_feat = None

    def canvasReleaseEvent(self, e):
        try:
            pass  # No operation, placeholder for try block

        except Exception as ex:
            self._flash(f'Error in release event: {ex}')
            return
        if e.button() == Qt.MouseButton.RightButton:
            self._finish()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return

        if not self._last_preview_ok:
            # Try one-off detection at the click point
            map_pt = self.toMapCoordinates(e.pos())
            found = self._find_nearest_on_layers(map_pt)
            if found is None:
                self._flash("No line found nearby. Please zoom in or get closer.")
                return
            layer, feat, cp, _ = found
        else:
            layer, feat, cp = self._last_preview_layer, self._last_preview_feat, self._last_preview_point

        if not isinstance(layer, QgsVectorLayer) or layer.geometryType() != QgsWkbTypes.GeometryType.LineGeometry:
            self._flash("Active layer is not a line layer.")
            return

        if not layer.isEditable():
            try:
                layer.startEditing()
            except Exception as e:
                logger.debug(f"Error in InfrastructureCutTool.canvasReleaseEvent: {e}")

        ok = self._split_feature_at_point(layer, feat, cp)
        if ok:
            try:
                self.iface.messageBar().pushSuccess("Cutting", f"Cut in layer: {layer.name()}")
            except Exception as e:
                logger.debug(f"Error in InfrastructureCutTool.canvasReleaseEvent: {e}")
        else:
            self._flash("Cutting failed (maybe the click is too far or the geometry is not supported).")

    # ------------- Core split logic -------------
    def _split_feature_at_point(self, layer: QgsVectorLayer, feat: QgsFeature, cut_pt: QgsPointXY) -> bool:
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            return False

        poly, is_multi, multi = self._as_polyline(geom)
        if not poly or len(poly) < 2:
            return False

        # Find nearest segment and insert the cut point
        best = None  # (i, t, d2, cp)
        for i in range(len(poly) - 1):
            a = poly[i]
            b = poly[i + 1]
            cx, cy, t, d2 = self._closest_point_on_segment(cut_pt.x(), cut_pt.y(), a.x(), a.y(), b.x(), b.y())
            if best is None or d2 < best[2]:
                best = (i, t, d2, QgsPointXY(cx, cy))
        if best is None:
            return False

        i, t, d2, cp = best
        tol2 = self._map_tol() ** 2
        if d2 > tol2:
            return False

        # If the cut point is very close to an endpoint, snap to that endpoint to avoid 0-length segment
        EPS = 1e-9
        if t <= EPS:
            cp = poly[i]
        elif t >= 1.0 - EPS:
            cp = poly[i + 1]
        else:
            # Insert new vertex at position i+1
            poly.insert(i + 1, cp)

        # Recompute index of cp in list (ensure it exists)
        # Find first occurrence by coordinates
        idx = None
        for k, p in enumerate(poly):
            if abs(p.x() - cp.x()) < 1e-9 and abs(p.y() - cp.y()) < 1e-9:
                idx = k
                break
        if idx is None or idx == 0 or idx == len(poly) - 1:
            # splitting at ends creates an empty part -> abort
            return False

        part1 = poly[:idx + 1]
        part2 = [poly[idx]] + poly[idx + 1:]

        g1 = QgsGeometry.fromPolylineXY(part1)
        g2 = QgsGeometry.fromPolylineXY(part2)

        # Prepare new features
        attrs = feat.attributes()
        f1 = QgsFeature(layer.fields())
        f1.setAttributes(attrs)
        f1.setGeometry(g1)
        f2 = QgsFeature(layer.fields())
        f2.setAttributes(attrs)
        f2.setGeometry(g2)

        # Do NOT reuse the parent's GPKG primary key: setAttributes above copied
        # the parent's 'fid' onto both parts, which collides on insert
        # ("UNIQUE constraint failed: <layer>.fid" -> 1 deleted, 2 not added).
        # Clear it so OGR assigns a fresh fid to each part.
        dp = layer.dataProvider()
        pk_idxs = dp.pkAttributeIndexes() if dp else []
        fid_idx = pk_idxs[0] if pk_idxs else layer.fields().indexOf('fid')
        if fid_idx is not None and fid_idx >= 0:
            f1.setAttribute(fid_idx, None)
            f2.setAttribute(fid_idx, None)

        # Each half is a new element -> its own fresh identity. force_new because
        # setAttributes copied the parent's fiberq_uuid onto both, which would
        # otherwise leave the two halves sharing a single uuid.
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(f1, force_new=True)
            set_feature_uuid(f2, force_new=True)
        except Exception as e:
            logger.debug(f"Error setting uuid on cut parts: {e}")

        # Update length fields if present
        self._update_length_fields(layer, f1)
        self._update_length_fields(layer, f2)

        # Apply edit
        if not layer.isEditable():
            layer.startEditing()
        layer.beginEditCommand("Infrastructure cut")
        ok = layer.deleteFeature(feat.id())
        ok = ok and layer.addFeatures([f1, f2])
        if ok:
            layer.endEditCommand()
            layer.triggerRepaint()
            return True
        else:
            layer.destroyEditCommand()
            return False

    def _update_length_fields(self, layer: QgsVectorLayer, feat: QgsFeature):
        """Update all length-like attributes on the feature to meters.
        Matches common Serbian/English field names: duzina, dužina, duzina_m,
        length, length_m, len_m, duzina_cevi, etc. Case/diacritics/spacing-insensitive.
        """
        def _norm(s: str) -> str:
            s = (s or '').lower()
            s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
            s = s.replace('đ', 'dj')
            s = re.sub(r'[^a-z]+', '', s)
            return s
        names = {f.name(): i for i, f in enumerate(layer.fields())}
        norm_names = {_norm(n): (n, idx) for n, idx in names.items()}
        targets = []
        for norm, (orig, idx) in norm_names.items():
            if any(tok in norm for tok in ('duzina', 'duzina', 'duzina', 'length', 'len')):
                targets.append((orig, idx))
        if not targets:
            return
        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        try:
            da.setEllipsoid(QgsProject.instance().ellipsoid())
        except Exception as e:
            logger.debug(f"Error in InfrastructureCutTool._norm: {e}")
        L = da.measureLength(feat.geometry())
        try:
            L = da.convertLengthMeasurement(L, QgsUnitTypes.DistanceUnit.DistanceMeters)
        except Exception as e:
            logger.debug(f"Error in InfrastructureCutTool._norm: {e}")
        val_m = round(float(L or 0.0), 3)
        for orig, idx in targets:
            try:
                fdef = layer.fields()[idx]
                tname = (fdef.typeName() or '').lower()
                if any(k in tname for k in ('int', 'integer', 'whole', 'int4', 'int8')):
                    feat.setAttribute(idx, int(round(val_m)))
                else:
                    feat.setAttribute(idx, val_m)
            except Exception:
                try:
                    feat.setAttribute(idx, val_m)
                except Exception as e:
                    logger.debug(f"Error in InfrastructureCutTool._norm: {e}")

    # ------------- Misc UI helpers -------------
    def _flash(self, msg: str):
        try:
            self.iface.messageBar().pushWarning("Cutting", msg)
        except Exception:
            try:
                QMessageBox.warning(self.iface.mainWindow(), "Cutting", msg)
            except Exception as e:
                logger.debug(f"Error in InfrastructureCutTool._flash: {e}")

    def _finish(self):
        # Hide marker and unset tool (used on ESC / right-click)
        try:
            self._marker.hide()
        except Exception as e:
            logger.debug(f"Error in InfrastructureCutTool._finish: {e}")
        try:
            self.canvas.unsetMapTool(self)
        except Exception as e:
            logger.debug(f"Error in InfrastructureCutTool._finish: {e}")
