"""
FiberQ v2 - Smart Selection Tool

Map tool for smart multi-select without changing active layer.
Phase 2.1: Extracted from extracted_classes.py
Phase 5.2: Added logging infrastructure
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsGeometry,
    QgsPointXY, QgsWkbTypes, QgsRectangle, QgsFeatureRequest
)
from qgis.gui import QgsMapTool, QgsVertexMarker

# Import from legacy bridge for compatibility
from ..utils.legacy_bridge import ELEMENT_DEFS, NASTAVAK_DEF

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class SmartMultiSelectTool(QgsMapTool):
    """Enables selection of objects by clicking without switching active layer.

    - Works on point layers whose name contains element names
    - Click on object: toggle selection (select/deselect) only on that layer
    - Doesn't affect selections on other layers
    - Shows small marker at click location as visual confirmation (temporary only)
    """

    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()
        # Marker for visual feedback
        try:
            self._marker = QgsVertexMarker(self.canvas)
            self._marker.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
            self._marker.setColor(QColor(0, 170, 255))
            self._marker.setIconSize(12)
            self._marker.setPenWidth(3)
            self._marker.hide()
        except Exception:
            self._marker = None

    def _layer_priority(self, lyr):
        """Lower number = higher priority.

        0  - elements (drop-down "Placing elements", Joint Closures)
        10 - poles / manholes (Poles, Manholes)
        50 - lines (Route/Trasa, cables, pipes)
        80 - polygons (Objects, Service Area/Rejon)
        100 - other
        """
        try:
            name = (lyr.name() or "").lower()
            gtype = lyr.geometryType()
        except Exception:
            return 100

        # 1) elements + joint closures (highest priority)
        element_names = set()
        try:
            try:
                element_names.add(NASTAVAK_DEF.get('name', 'Nastavci').lower())
            except Exception:
                element_names.add('nastavci')
            try:
                for d in ELEMENT_DEFS:
                    nm = d.get('name')
                    if nm:
                        element_names.add(nm.lower())
            except Exception as e:
                logger.debug(f"Error in SmartMultiSelectTool._layer_priority: {e}")
        except Exception as e:
            logger.debug(f"Error in SmartMultiSelectTool._layer_priority: {e}")

        if name in element_names:
            return 0

        # 2) poles / manholes
        if name in ("stubovi", "poles", "okna", "manholes"):
            return 10

        # 3) lines: route, cables, pipes
        if gtype == QgsWkbTypes.GeometryType.LineGeometry:
            return 50

        # 4) polygons: objects, regions
        if gtype == QgsWkbTypes.GeometryType.PolygonGeometry:
            return 80

        # other
        return 100

    def _nearest_feature(self, lyr, pt, tol):
        """Return (fid, geom) of nearest feature within tolerance in map units; otherwise (None, None)."""
        try:
            rect = QgsRectangle(pt.x() - tol, pt.y() - tol, pt.x() + tol, pt.y() + tol)
            req = QgsFeatureRequest().setFilterRect(rect)
        except Exception:
            req = None

        gpt = QgsGeometry.fromPointXY(pt)
        best = (None, None, None)  # (dist, fid, geom)
        it = lyr.getFeatures(req) if req is not None else lyr.getFeatures()
        for f in it:
            try:
                geom = f.geometry()
                if not geom or geom.isEmpty():
                    continue
                d = geom.distance(gpt)
                if d <= tol and (best[0] is None or d < best[0]):
                    best = (d, f.id(), geom)
            except Exception as e:
                logger.debug(f"Skipping feature; could not compute distance: {e}")
                continue
        return (best[1], best[2]) if best[1] is not None else (None, None)

    def canvasReleaseEvent(self, e):
        # Right click -> cancel tool (without changing selection)
        try:
            if e.button() == Qt.MouseButton.RightButton:
                if self._marker:
                    try:
                        self._marker.hide()
                    except Exception as e:
                        logger.debug(f"Error in SmartMultiSelectTool.canvasReleaseEvent: {e}")
                try:
                    self.canvas.unsetMapTool(self)
                except Exception as e:
                    logger.debug(f"Error in SmartMultiSelectTool.canvasReleaseEvent: {e}")
                return
        except Exception as e:
            logger.debug(f"Error in SmartMultiSelectTool.canvasReleaseEvent: {e}")

        try:
            pt = self.toMapCoordinates(e.pos())
        except Exception:
            return

        # Tolerance ~10 px
        try:
            tol = self.canvas.extent().width() / max(1, self.canvas.width()) * 10.0
        except Exception:
            tol = 5.0

        gpt = QgsGeometry.fromPointXY(pt)

        # Collect candidates from all relevant layers
        candidates = []
        for lyr in self._candidate_layers():
            fid, geom = self._nearest_feature(lyr, pt, tol)
            if fid is None or geom is None:
                continue
            try:
                d = float(geom.distance(gpt))
            except Exception:
                d = 0.0
            candidates.append((d, self._layer_priority(lyr), lyr, fid, geom))

        if not candidates:
            if self._marker:
                self._marker.hide()
            return

        # If distances are very close, give priority to elements over poles/manholes
        min_d = min(c[0] for c in candidates)
        eps = max(tol * 0.4, 0.01)
        near = [c for c in candidates if c[0] <= min_d + eps]
        near.sort(key=lambda c: (c[1], c[0]))  # priority then distance
        _, _, lyr, fid, geom = near[0]

        # Toggle only on that layer
        try:
            if fid in lyr.selectedFeatureIds():
                lyr.deselect(fid)
            else:
                lyr.select(fid)
        except Exception as e:
            logger.debug(f"Error in SmartMultiSelectTool.canvasReleaseEvent: {e}")

        # Visual feedback
        try:
            cen = geom.asPoint() if geom.isGeosValid() and geom.isSingle() else geom.centroid().asPoint()
        except Exception:
            cen = pt
        if self._marker:
            self._marker.setCenter(QgsPointXY(cen))
            self._marker.show()

        # Remember selection
        try:
            if not hasattr(self.plugin, 'smart_selection'):
                self.plugin.smart_selection = []
            key = (lyr.id(), int(fid))
            if key in self.plugin.smart_selection:
                self.plugin.smart_selection.remove(key)
            else:
                self.plugin.smart_selection.append(key)
        except Exception as e:
            logger.debug(f"Error in SmartMultiSelectTool.canvasReleaseEvent: {e}")

    def keyPressEvent(self, e):
        """ESC cancels Smart selection tool."""
        try:
            if e.key() == Qt.Key.Key_Escape:
                if self._marker:
                    try:
                        self._marker.hide()
                    except Exception as e:
                        logger.debug(f"Error in SmartMultiSelectTool.keyPressEvent: {e}")
                try:
                    self.canvas.unsetMapTool(self)
                except Exception as e:
                    logger.debug(f"Error in SmartMultiSelectTool.keyPressEvent: {e}")
        except Exception as e:
            logger.debug(f"Error in SmartMultiSelectTool.keyPressEvent: {e}")

    def deactivate(self):
        try:
            if self._marker:
                self._marker.hide()
        except Exception as e:
            logger.debug(f"Error in SmartMultiSelectTool.deactivate: {e}")
        super().deactivate()

    def _candidate_layers(self):
        """Return list of layers relevant for smart selection.

        Includes:
        - all point elements from drop-down list "Placing elements"
        - 'Joint Closures' / 'Nastavci'
        - 'Poles' / 'Stubovi'
        - 'OKNA' / 'Manholes'
        - 'Route' / 'Trasa'
        - 'PE cevi' / 'PE pipes'
        - 'Prelazne cevi' / 'Transition pipes'
        - 'Objekti' / 'Objects'
        - 'Rejon' / 'Service Area'
        """
        try:
            # --- POINT layers: elements + poles/manholes ---
            valid_point_names = set()

            # 1) Joint Closure
            try:
                valid_point_names.add(NASTAVAK_DEF.get('name', 'Nastavci'))
            except Exception:
                valid_point_names.add('Nastavci')

            # 2) All elements from ELEMENT_DEFS
            try:
                for d in ELEMENT_DEFS:
                    nm = d.get('name')
                    if nm:
                        valid_point_names.add(nm)
            except Exception as e:
                logger.debug(f"Error in SmartMultiSelectTool._candidate_layers: {e}")

            # 3) Poles and Manholes
            valid_point_names.update(['Poles', 'Stubovi', 'OKNA', 'Manholes'])

            # --- LINE layers: route + pipes ---
            valid_line_names = {
                'Route', 'Trasa',
                'PE cevi', 'PE pipes',
                'Prelazne cevi', 'Transition pipes',
                'Kablovi_podzemni', 'Underground cables',
                'Kablovi_vazdusni', 'Aerial cables',
            }

            # --- POLYGON layers: objects + regions ---
            valid_poly_names = {
                'Objekti', 'Objects',
                'Rejon', 'Service Area', 'Service area',
            }

            low_point = {n.lower() for n in valid_point_names}
            low_line = {n.lower() for n in valid_line_names}
            low_poly = {n.lower() for n in valid_poly_names}

            layers = []

            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                        continue

                    name = (lyr.name() or "")
                    lname = name.lower()
                    gtype = lyr.geometryType()

                    if gtype == QgsWkbTypes.GeometryType.PointGeometry:
                        if name in valid_point_names or lname in low_point:
                            layers.append(lyr)
                    elif gtype == QgsWkbTypes.GeometryType.LineGeometry:
                        if name in valid_line_names or lname in low_line:
                            layers.append(lyr)
                    elif gtype == QgsWkbTypes.GeometryType.PolygonGeometry:
                        if name in valid_poly_names or lname in low_poly:
                            layers.append(lyr)
                except Exception as e:
                    logger.debug(f"Skipping layer during smart-select classification: {e}")
                    continue

            return layers

        except Exception as e:
            # Fallback – if something fails, keep old behavior (only some point layers)
            import re as _re
            logger.debug(f"Smart layer detection failed, using fallback: {e}")
            layers = []
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if isinstance(lyr, QgsVectorLayer) and lyr.isValid() and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry:
                        if _re.search(r"(nastav|stub|okno|zok|patch|ormar|panel|izvod|or)", (lyr.name() or "").lower()):
                            layers.append(lyr)
                except Exception as e2:
                    logger.debug(f"Error checking layer validity: {e2}")
            return layers


__all__ = ['SmartMultiSelectTool']
