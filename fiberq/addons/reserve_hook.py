from qgis.PyQt.QtCore import QObject, QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsWkbTypes, QgsGeometry,
    QgsRendererCategory, QgsCategorizedSymbolRenderer, QgsMarkerSymbol,
    QgsSvgMarkerSymbolLayer, QgsUnitTypes, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling
)
import os

# Phase 5.3: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class ReserveHook(QObject):
    """Prati sloj 'Opticke_rezerve' i ažurira slack_m/total_len_m na kablovima,
    i automatski postavlja simboliku (završna = C, prolazna = S ili SVG ako postoji)."""

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self._connected = False
        self._layer = None
        QgsProject.instance().layersAdded.connect(self._layers_added)

    # --- Wiring ---
    def ensure_connected(self):
        if self._connected:
            return
        for l in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(l, QgsVectorLayer) and l.geometryType() == QgsWkbTypes.PointGeometry and l.name().lower().startswith('opticke_rezerve'):
                    self._connect_layer(l)
                    self._connected = True
            except Exception as e:
                logger.debug(f"Error in ReserveHook.ensure_connected: {e}")

    def _layers_added(self, layers):
        try:
            for l in layers:
                if isinstance(l, QgsVectorLayer) and l.geometryType() == QgsWkbTypes.PointGeometry and l.name().lower().startswith('opticke_rezerve'):
                    self._connect_layer(l)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._layers_added: {e}")

    def _connect_layer(self, lyr: QgsVectorLayer):
        if self._layer is lyr:
            return
        self._layer = lyr
        # hook signals
        try:
            lyr.committedFeaturesAdded.connect(self._on_rez_added)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._connect_layer: {e}")
        try:
            lyr.committedFeaturesRemoved.connect(self._on_rez_removed)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._connect_layer: {e}")
        try:
            lyr.committedAttributeValuesChanges.connect(self._on_attr_changed)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._connect_layer: {e}")
        try:
            lyr.committedGeometriesChanges.connect(self._on_geom_changed)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._connect_layer: {e}")
        try:
            lyr.editingStopped.connect(self._on_editing_stopped)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._connect_layer: {e}")
        # style
        try:
            self._apply_style(lyr)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._connect_layer: {e}")
    # --- Style for reserves layer ---

    def _icons_dir(self):
        base = os.path.join(os.path.dirname(__file__), '..', 'resources', 'map_icons')
        return os.path.abspath(base)

    def _apply_style(self, rez: QgsVectorLayer):
        if not isinstance(rez, QgsVectorLayer) or rez.geometryType() != QgsWkbTypes.PointGeometry:
            return
        field = 'tip' if rez.fields().indexFromName('tip') != -1 else None
        if not field:
            return
        # Prefer SVG icons if present, fallback to font markers

        def _svg_symbol(svg_name):
            s = QgsMarkerSymbol.createSimple({"name": "circle", "size": "6"})
            try:
                path = os.path.join(self._icons_dir(), svg_name)
                if os.path.exists(path):
                    sl = QgsSvgMarkerSymbolLayer(path, 12, 0)
                    sl.setSizeUnit(QgsUnitTypes.RenderMapUnits)
                    s.changeSymbolLayer(0, sl)
                else:
                    s.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            except Exception as e:
                s.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            return s
        cats = [
            QgsRendererCategory('zavrsna', _svg_symbol('map_rezerva_c.svg'), 'Završna'),
            QgsRendererCategory('prolazna', _svg_symbol('map_rezerva_s.svg'), 'Prolazna'),
        ]
        r = QgsCategorizedSymbolRenderer(field, cats)
        rez.setRenderer(r)
        rez.triggerRepaint()

    # --- Signal handlers ---
    def _on_rez_added(self, layer_id, addedFeatures):
        try:
            rez = self._layer
            if not isinstance(rez, QgsVectorLayer):
                return
            idx_kid = rez.fields().indexFromName('cable_layer_id')
            idx_fid = rez.fields().indexFromName('cable_fid')
            if idx_kid == -1 or idx_fid == -1:
                return
            touched = set()
            for f in addedFeatures:
                kid = f.attribute(idx_kid)
                fid = f.attribute(idx_fid)
                if kid is None or fid is None:
                    continue
                touched.add((kid, int(fid)))
            for kid, fid in touched:
                self._update_cable(kid, fid)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._on_rez_added: {e}")

    def _on_rez_removed(self, layer_id, fids):
        try:
            rez = self._layer
            if not isinstance(rez, QgsVectorLayer):
                return
            # Find impacted cables by scanning remaining features (cheap unless many)
            idx_kid = rez.fields().indexFromName('cable_layer_id')
            idx_fid = rez.fields().indexFromName('cable_fid')
            impacted = set()
            for f in rez.getFeatures():
                try:
                    impacted.add((f.attribute(idx_kid), int(f.attribute(idx_fid))))
                except Exception as e:
                    logger.debug(f"Error in ReserveHook._on_rez_removed: {e}")
            # Unique set ensures we recompute all current ones; removed ones will be ignored safely
            for kid, fid in impacted:
                self._update_cable(kid, fid)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._on_rez_removed: {e}")

    def _on_attr_changed(self, layer_id, changedAttrsMap):
        # changedAttrsMap: dict(fid -> {idx: value})
        try:
            rez = self._layer
            if not isinstance(rez, QgsVectorLayer):
                return
            idx_kid = rez.fields().indexFromName('cable_layer_id')
            idx_fid = rez.fields().indexFromName('cable_fid')
            touched = set()
            for fid in changedAttrsMap.keys():
                f = next(rez.getFeatures(f'id={int(fid)}'), None)
                if f:
                    kid = f.attribute(idx_kid); kfid = f.attribute(idx_fid)
                    if kid is not None and kfid is not None:
                        touched.add((kid, int(kfid)))
            for kid, fid in touched:
                self._update_cable(kid, fid)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._on_attr_changed: {e}")

    def _on_geom_changed(self, layer_id, geomMap):
        # Just recompute for all referenced features
        try:
            rez = self._layer
            if not isinstance(rez, QgsVectorLayer):
                return
            idx_kid = rez.fields().indexFromName('cable_layer_id')
            idx_fid = rez.fields().indexFromName('cable_fid')
            touched = set()
            for fid in geomMap.keys():
                f = next(rez.getFeatures(f'id={int(fid)}'), None)
                if f:
                    kid = f.attribute(idx_kid); kfid = f.attribute(idx_fid)
                    if kid is not None and kfid is not None:
                        touched.add((kid, int(kfid)))
            for kid, fid in touched:
                self._update_cable(kid, fid)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._on_geom_changed: {e}")

    def _on_editing_stopped(self):
        # Safety net: recompute all
        try:
            rez = self._layer
            if not isinstance(rez, QgsVectorLayer):
                return
            idx_kid = rez.fields().indexFromName('cable_layer_id')
            idx_fid = rez.fields().indexFromName('cable_fid')
            touched = set()
            for f in rez.getFeatures():
                try:
                    kid = f.attribute(idx_kid); kfid = f.attribute(idx_fid)
                    if kid is not None and kfid is not None:
                        touched.add((kid, int(kfid)))
                except Exception as e:
                    logger.debug(f"Error in ReserveHook._on_editing_stopped: {e}")
            for kid, fid in touched:
                self._update_cable(kid, fid)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._on_editing_stopped: {e}")
    # --- Core recompute ---

    def _update_cable(self, cable_layer_id, cable_fid):
        proj = QgsProject.instance()
        lyr = proj.mapLayer(cable_layer_id)
        if not isinstance(lyr, QgsVectorLayer):
            return

        # Sum slack from all reserves for this cable
        rez = None
        for l in proj.mapLayers().values():
            if isinstance(l, QgsVectorLayer) and l.name().lower().startswith('opticke_rezerve'):
                rez = l; break
        if rez is None:
            return

        idx_kid = rez.fields().indexFromName('cable_layer_id')
        idx_fid = rez.fields().indexFromName('cable_fid')
        idx_len = rez.fields().indexFromName('duzina_m')
        total_slack = 0.0
        for f in rez.getFeatures():
            try:
                if f.attribute(idx_kid) == cable_layer_id and int(f.attribute(idx_fid)) == int(cable_fid):
                    val = f.attribute(idx_len) if idx_len != -1 else f.attribute('slack_m')
                    total_slack += float(val or 0.0)
            except Exception as e:
                logger.debug(f"Error in ReserveHook._update_cable: {e}")
        # Geometry length (meters)
        g_m = 0.0
        try:
            kf = next(lyr.getFeatures(f'id={int(cable_fid)}'))
            geom = kf.geometry()
            g_m = geom.length() if isinstance(geom, QgsGeometry) else 0.0
        except StopIteration:
            pass

        # Ensure fields exist
        slack_idx = lyr.fields().indexFromName('slack_m')
        tot_idx = lyr.fields().indexFromName('total_len_m')
        attrs_to_add = []
        if slack_idx == -1:
            attrs_to_add.append(QgsField('slack_m', QVariant.Double))
        if tot_idx == -1:
            attrs_to_add.append(QgsField('total_len_m', QVariant.Double))
        if attrs_to_add:
            lyr.startEditing(); lyr.dataProvider().addAttributes(attrs_to_add); lyr.updateFields(); lyr.commitChanges()
            slack_idx = lyr.fields().indexFromName('slack_m')
            tot_idx = lyr.fields().indexFromName('total_len_m')

        # Write values
        lyr.startEditing()
        try:
            lyr.changeAttributeValue(int(cable_fid), slack_idx, round(total_slack, 2))
            lyr.changeAttributeValue(int(cable_fid), tot_idx, round((g_m or 0) + total_slack, 2))
        finally:
            lyr.commitChanges(); lyr.triggerRepaint()

        # Ensure labeling on total_len_m so the user sees the update
        try:
            s = QgsPalLayerSettings()
            s.fieldName = 'round("total_len_m",2)'
            lbl = QgsVectorLayerSimpleLabeling(s)
            lyr.setLabeling(lbl)
            lyr.setLabelsEnabled(True)
        except Exception as e:
            logger.debug(f"Error in ReserveHook._update_cable: {e}")
