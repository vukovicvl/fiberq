"""
FiberQ v2 - Layer Manager

This module centralizes all layer creation and management logic.
It provides methods to ensure layers exist (create if needed) and manage
layer tree organization.

Phase 6 of the modular refactoring.
Phase 1.3: Added module-level layer utility functions from main_plugin.py
Phase 5.2: Added logging infrastructure
"""

import os
import re
import unicodedata
from datetime import datetime

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsWkbTypes,
    QgsMarkerSymbol, QgsSymbol, QgsUnitTypes,
    QgsSingleSymbolRenderer, QgsSvgMarkerSymbolLayer,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling,
    QgsFeature, QgsGeometry, QgsDistanceArea,
    QgsVectorFileWriter, QgsCoordinateTransformContext,
    QgsFillSymbol, QgsLinePatternFillSymbolLayer, QgsSimpleFillSymbolLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMessageBox, QFileDialog

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)

# Phase 0.1: UUID support for FiberQ Designer
from ..utils.uuid_utils import FIBERQ_UUID_FIELD, ensure_uuid_field, set_feature_uuid  # noqa: E402


# =============================================================================
# ELEMENT DEFINITIONS (used by _element_def_by_name, _ensure_element_layer_with_style)
# =============================================================================

def _get_map_icon_path(filename: str) -> str:
    """Get the full path to a map icon file."""
    try:
        base = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(base, 'resources', 'map_icons', filename)
    except Exception:
        return filename


# Element definitions for placement tools
ELEMENT_DEFS = [
    {"name": "ODF", "symbol": {"svg_path": _get_map_icon_path("map_odf.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "TB", "symbol": {"svg_path": _get_map_icon_path("map_tb.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Patch panel", "symbol": {"svg_path": _get_map_icon_path("map_patch_panel.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "OTB", "symbol": {"svg_path": _get_map_icon_path("map_otb.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Indoor OTB", "symbol": {"svg_path": _get_map_icon_path("map_place_otb_indoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Outdoor OTB", "symbol": {"svg_path": _get_map_icon_path("map_place_otb_outdoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Pole OTB", "symbol": {"svg_path": _get_map_icon_path("map_place_otb_pole.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "TO", "symbol": {"svg_path": _get_map_icon_path("map_place_to.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Indoor TO", "symbol": {"svg_path": _get_map_icon_path("map_place_to_indoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Outdoor TO", "symbol": {"svg_path": _get_map_icon_path("map_place_to_outdoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Pole TO", "symbol": {"svg_path": _get_map_icon_path("map_place_to_pole.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Joint Closure TO", "symbol": {"svg_path": _get_map_icon_path("map_place_to_joint_closure.svg"), "size": "10", "size_unit": "MapUnit"}},
]

NASTAVAK_DEF = {"name": "Joint Closures", "symbol": {"name": "diamond", "color": "red", "size": "5", "size_unit": "MapUnit"}}


# =============================================================================
# HELPER FUNCTIONS (Phase 1.3)
# =============================================================================

def _normalize_name(s: str) -> str:
    """Normalize a name for comparison by removing diacritics and special characters."""
    try:
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = s.lower()
        s = re.sub(r"[^a-z0-9_]+", "_", s)
        return s.strip("_")
    except Exception:
        return s


def _default_fields_for(layer_name: str):
    """
    Return a list of (key, label, kind, default, options) for element dialogs.
    kind: 'text' | 'int' | 'double' | 'enum' | 'year'
    """
    # Delegates to the canonical schema (single source of truth, WP1a).
    from ..models.schema import get_default_fields_for_layer as _schema_fields
    return _schema_fields(layer_name)


def _apply_fixed_text_label(layer, field_name='naziv', size_mu=8.0, yoff_mu=5.0):
    """Apply fixed-size text labels to a layer."""
    try:
        from qgis.core import QgsTextFormat, QgsTextBufferSettings

        s = QgsPalLayerSettings()
        s.fieldName = field_name
        s.enabled = True
        try:
            s.placement = getattr(QgsPalLayerSettings, 'OverPoint', s.placement)
        except Exception as e:
            logger.debug(f"Could not set label placement: {e}")
        try:
            s.xOffset = 0.0
            s.yOffset = float(yoff_mu)
            s.offsetUnits = QgsUnitTypes.RenderMapUnits
        except Exception as e:
            logger.debug(f"Could not set label offset: {e}")

        tf = QgsTextFormat()
        try:
            tf.setSize(float(size_mu))
            tf.setSizeUnit(QgsUnitTypes.RenderMapUnits)
        except Exception as e:
            logger.debug(f"Could not set text format size: {e}")

        try:
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.8)
            buf.setColor(QColor(255, 255, 255))
            tf.setBuffer(buf)
        except Exception as e:
            logger.debug(f"Could not set text buffer: {e}")

        try:
            s.setFormat(tf)
        except Exception as e:
            logger.debug(f"Could not set label format: {e}")

        layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()
    except Exception as e:
        logger.debug(f"Error in label configuration: {e}")


# =============================================================================
# ELEMENT LAYER FUNCTIONS (Phase 1.3)
# =============================================================================

def _element_def_by_name(name: str):
    """Find element definition by name from ELEMENT_DEFS."""
    try:
        for ed in ELEMENT_DEFS:
            if ed.get("name") == name:
                return ed
    except Exception as e:
        logger.debug(f"Could not find element definition: {e}")
    return None


def _ensure_element_layer_with_style(plugin, layer_name: str):
    """
    Find or create a point layer named 'layer_name' and apply style/labels from ELEMENT_DEFS.

    Args:
        plugin: Plugin instance with iface
        layer_name: Name of the element layer (e.g., 'ODF', 'TB')

    Returns:
        QgsVectorLayer: The element layer
    """
    # Find existing layer
    elem_layer = None
    for lyr in QgsProject.instance().mapLayers().values():
        try:
            if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() == layer_name:
                elem_layer = lyr
                break
        except Exception as e:
            logger.debug(f"Error in element layer creation: {e}")

    if elem_layer is None:
        # Create new layer
        crs = plugin.iface.mapCanvas().mapSettings().destinationCrs().authid()
        elem_layer = QgsVectorLayer(f"Point?crs={crs}", layer_name, "memory")
        pr = elem_layer.dataProvider()

        # Add default attrs for that element
        try:
            specs = _default_fields_for(layer_name)
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

        if not any(f.name() == "naziv" for f in fields):
            fields.insert(0, QgsField("naziv", QVariant.String))

        # Phase 0.1: Add fiberq_uuid field for Designer compatibility
        if not any(f.name() == FIBERQ_UUID_FIELD for f in fields):
            fields.append(QgsField(FIBERQ_UUID_FIELD, QVariant.String))

        pr.addAttributes(fields)
        elem_layer.updateFields()

        # Apply style
        edef = _element_def_by_name(layer_name) or {}
        spec = edef.get("symbol") if isinstance(edef, dict) else None
        if isinstance(spec, dict) and spec.get('svg_path'):
            symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'size': '5', 'size_unit': 'MapUnit'})
            try:
                svg_layer = QgsSvgMarkerSymbolLayer(spec['svg_path'])
                try:
                    svg_layer.setSize(float(spec.get('size', 6)))
                except Exception as e:
                    logger.debug(f"Error in element layer creation: {e}")
                try:
                    svg_layer.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
                except Exception:
                    svg_layer.setSizeUnit(QgsUnitTypes.RenderMapUnits)
                symbol.changeSymbolLayer(0, svg_layer)
            except Exception as e:
                logger.debug(f"Error in element layer creation: {e}")
        elif isinstance(spec, dict):
            symbol = QgsMarkerSymbol.createSimple(spec)
        else:
            symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'size': '5'})

        try:
            elem_layer.renderer().setSymbol(symbol)
        except Exception as e:
            logger.debug(f"Error in element layer creation: {e}")

        # Apply labels
        try:
            _apply_fixed_text_label(elem_layer, 'naziv', 8.0, 5.0)
        except Exception:
            try:
                s = QgsPalLayerSettings()
                s.fieldName = "naziv"
                s.enabled = True
                elem_layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
                elem_layer.setLabelsEnabled(True)
            except Exception as e:
                logger.debug(f"Error in element layer creation: {e}")

        QgsProject.instance().addMapLayer(elem_layer)

    # Always apply English aliases
    try:
        from ..utils.field_aliases import apply_element_aliases
        apply_element_aliases(elem_layer)
    except Exception as e:
        logger.debug(f"Error in element layer creation: {e}")

    # Phase 0.1: Ensure UUID field exists (covers both new and existing layers)
    ensure_uuid_field(elem_layer)

    return elem_layer


def _copy_attributes_between_layers(src_feat, dst_layer):
    """
    Map attributes by normalized names; add missing fields on destination (only when safe).
    IMPORTANT: never copy PK fields (fid/id/gid...) into destination.

    Args:
        src_feat: Source feature with attributes
        dst_layer: Destination layer

    Returns:
        dict: Attribute values keyed by destination field names
    """
    # Normalized field name maps
    src_map = {_normalize_name(f.name()): f for f in src_feat.fields()}
    dst_map = {_normalize_name(f.name()): f for f in dst_layer.fields()}

    # Detect destination PK fields and always skip them
    skip = {"fid", "id", "gid"}
    try:
        pk_idxs = dst_layer.dataProvider().pkAttributeIndexes()
        for i in pk_idxs:
            if 0 <= i < dst_layer.fields().count():
                skip.add(_normalize_name(dst_layer.fields()[i].name()))
    except Exception as e:
        logger.debug(f"Error in _copy_attributes_between_layers: {e}")

    # Allow schema change only for local/OGR/memory style providers
    prov = ""
    try:
        prov = (dst_layer.providerType() or "").lower()
    except Exception as e:
        logger.debug(f"Error in _copy_attributes_between_layers: {e}")
    allow_schema_change = prov in ("ogr", "memory")

    # Add missing non-PK fields (only when allowed)
    to_add = []
    for key, f in src_map.items():
        if key in skip:
            continue
        if key not in dst_map:
            try:
                to_add.append(QgsField(f.name(), f.type() if hasattr(f, "type") else QVariant.String))
            except Exception:
                to_add.append(QgsField(f.name(), QVariant.String))

    if to_add and allow_schema_change:
        dst_layer.startEditing()
        dst_layer.dataProvider().addAttributes(to_add)
        dst_layer.updateFields()
        dst_layer.commitChanges()
        dst_map = {_normalize_name(f.name()): f for f in dst_layer.fields()}

    # Build attribute dict (skip PK fields)
    vals = {}
    for key, f in src_map.items():
        if key in skip:
            continue
        if key in dst_map:
            try:
                vals[dst_map[key].name()] = src_feat[f.name()]
            except Exception as e:
                logger.debug(f"Error in _copy_attributes_between_layers: {e}")
    return vals


# =============================================================================
# SERVICE AREA / REGION FUNCTIONS (Phase 1.3)
# =============================================================================

def _ensure_region_layer(core):
    """
    Ensure a polygon layer for service areas exists.

    Args:
        core: Plugin instance with iface

    Returns:
        QgsVectorLayer: The service area layer
    """
    try:
        proj = QgsProject.instance()

        # Find existing layer ('Rejon' or 'Service Area')
        for lyr in proj.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.PolygonGeometry  # noqa: W503
                    and lyr.name() in ('Rejon', 'Service Area')  # noqa: W503
                ):
                    # Rename old 'Rejon' to 'Service Area'
                    if lyr.name() == 'Rejon':
                        try:
                            lyr.setName('Service Area')
                        except Exception as e:
                            logger.debug(f"Error in _ensure_region_layer: {e}")
                    ensure_uuid_field(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Skipping layer while locating region layer: {e}")
                continue

        # Create new layer
        crs = proj.crs().authid() if proj and proj.crs().isValid() else 'EPSG:3857'
        region = QgsVectorLayer(f'Polygon?crs={crs}', 'Service Area', 'memory')
        pr = region.dataProvider()
        pr.addAttributes([
            QgsField('name', QVariant.String),
            QgsField('created_at', QVariant.String),
            QgsField('area_m2', QVariant.Double),
            QgsField('perim_m', QVariant.Double),
            QgsField('count', QVariant.Int),
            QgsField(FIBERQ_UUID_FIELD, QVariant.String),
        ])
        region.updateFields()

        # Simple semi-transparent style
        try:
            sym = region.renderer().symbol()
            sym.setOpacity(0.25)
        except Exception as e:
            logger.debug(f"Error in _ensure_region_layer: {e}")

        proj.addMapLayer(region)
        return region

    except Exception as e:
        try:
            QMessageBox.critical(core.iface.mainWindow(), 'Service Area', f'Error creating layer: {e}')
        except Exception as e:
            logger.debug(f"Error in _ensure_region_layer: {e}")
        return None


def _collect_selected_geometries(core):
    """
    Collect selected geometries from all visible vector layers.

    Args:
        core: Plugin instance (unused, for API consistency)

    Returns:
        list: List of (layer, feature, geometry) tuples
    """
    geoms = []
    try:
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if not isinstance(lyr, QgsVectorLayer):
                    continue
                if lyr.selectedFeatureCount() == 0:
                    continue
                for f in lyr.selectedFeatures():
                    g = f.geometry()
                    if not g or g.isEmpty():
                        continue
                    geoms.append((lyr, f, g))
            except Exception as e:
                logger.debug(f"Skipping layer while collecting selected geometries: {e}")
                continue
    except Exception as e:
        logger.debug(f"Error in _collect_selected_geometries: {e}")
    return geoms


def _create_region_from_selection(core, name: str, buf_m: float):
    """
    Create a service area polygon from selected features.

    Args:
        core: Plugin instance with iface
        name: Name for the new service area
        buf_m: Buffer distance in meters

    Returns:
        bool: True if successful
    """
    geoms = _collect_selected_geometries(core)
    if not geoms:
        try:
            QMessageBox.information(core.iface.mainWindow(), 'Create Service Area',
                                    'No selected objects. Select cables/elements and try again.')
        except Exception as e:
            logger.debug(f"Error in _create_region_from_selection: {e}")
        return False

    # Prepare buffers for point/line features; polygons keep geometry
    polys = []
    for lyr, feat, g in geoms:
        try:
            g = QgsGeometry(g)  # copy
            gtype = lyr.geometryType()
            if gtype in (QgsWkbTypes.PointGeometry, QgsWkbTypes.LineGeometry):
                if buf_m > 0:
                    polys.append(g.buffer(buf_m, 8))
                else:
                    polys.append(g.buffer(0.01, 8))
            else:
                if buf_m > 0:
                    polys.append(g.buffer(buf_m, 8))
                else:
                    polys.append(g)
        except Exception as e:
            logger.debug(f"Skipping geometry while buffering selection: {e}")
            continue

    if not polys:
        try:
            QMessageBox.warning(core.iface.mainWindow(), 'Create Service Area', 'Cannot calculate geometries.')
        except Exception as e:
            logger.debug(f"Error in _create_region_from_selection: {e}")
        return False

    # Union/Dissolve all
    try:
        u = QgsGeometry.unaryUnion(polys)
    except Exception:
        u = None
        for p in polys:
            if u is None:
                u = QgsGeometry(p)
            else:
                try:
                    u = u.combine(p)
                except Exception as e:
                    logger.debug(f"Error in _create_region_from_selection: {e}")

    if not u or u.isEmpty():
        try:
            QMessageBox.warning(core.iface.mainWindow(), 'Create Service Area', 'Result is empty.')
        except Exception as e:
            logger.debug(f"Error in _create_region_from_selection: {e}")
        return False

    # Ensure polygon geometry
    if u.type() != QgsWkbTypes.PolygonGeometry:
        try:
            u = u.buffer(0.01, 8)
        except Exception as e:
            logger.debug(f"Error in _create_region_from_selection: {e}")

    # Explode multi into parts
    parts = []
    try:
        if u.isMultipart():
            for poly in u.asMultiPolygon():
                try:
                    parts.append(QgsGeometry.fromPolygonXY(poly))
                except Exception as e:
                    logger.debug(f"Error in _create_region_from_selection: {e}")
        else:
            parts.append(u)
    except Exception:
        parts = [u]

    region = _ensure_region_layer(core)
    if not region:
        return False

    # Measure area/perimeter with project settings
    d = QgsDistanceArea()
    try:
        prj = QgsProject.instance()
        if prj.ellipsoid():
            d.setEllipsoid(prj.ellipsoid())
        d.setSourceCrs(prj.crs(), QgsProject.instance().transformContext())
        d.setEllipsoidalMode(True)
    except Exception as e:
        logger.debug(f"Error in _create_region_from_selection: {e}")

    # Add features
    added = 0
    try:
        region.startEditing()
        for part in parts:
            if not part or part.isEmpty():
                continue
            area = d.measureArea(part) if d else part.area()
            peri = d.measurePerimeter(part) if d else part.length()
            f = QgsFeature(region.fields())
            try:
                f.setGeometry(part)
            except Exception as e:
                logger.debug(f"Error in _create_region_from_selection: {e}")
            f['name'] = name
            f['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f['area_m2'] = float(area)
            f['perim_m'] = float(peri)
            f['count'] = len(geoms)
            # WP1b identity invariant: stamp a uuid on each part before adding it,
            # matching the manual-draw path (the from-selection path previously
            # persisted Service Area features with a NULL fiberq_uuid).
            try:
                set_feature_uuid(f)
            except Exception as e:
                logger.debug(f"Error in _create_region_from_selection: {e}")
            region.addFeature(f)
            added += 1
        region.commitChanges()
        region.triggerRepaint()
    except Exception as e:
        try:
            region.rollBack()
        except Exception as e:
            logger.debug(f"Error in _create_region_from_selection: {e}")
        try:
            QMessageBox.critical(core.iface.mainWindow(), 'Create Service Area', f'Error: {e}')
        except Exception as e:
            logger.debug(f"Error in _create_region_from_selection: {e}")
        return False

    try:
        QMessageBox.information(core.iface.mainWindow(), 'Create Service Area',
                                f'Created: {added} polygon(s) in "Service Area" layer.')
    except Exception as e:
        logger.debug(f"Error in _create_region_from_selection: {e}")
    return True


# =============================================================================
# OBJECTS LAYER FUNCTIONS (Phase 1.3)
# =============================================================================

def _set_objects_layer_alias(layer):
    """Set the objects layer display name to 'Objects'."""
    try:
        from ..utils.field_aliases import set_objects_layer_alias
        set_objects_layer_alias(layer)
    except Exception as e:
        logger.debug(f"Error in _set_objects_layer_alias: {e}")


def _apply_objects_field_aliases(layer):
    """Apply English field aliases to an objects layer."""
    try:
        from ..utils.field_aliases import apply_objects_field_aliases
        apply_objects_field_aliases(layer)
    except Exception as e:
        logger.debug(f"Error in _apply_objects_field_aliases: {e}")


def _ensure_objects_layer(core):
    """
    Create / return polygon layer 'Objects' with standard fields.

    Args:
        core: Plugin instance with iface

    Returns:
        QgsVectorLayer: The objects layer
    """
    try:
        prj = QgsProject.instance()

        # Find existing layer ('Objekti' or 'Objects')
        for lyr in prj.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.wkbType() in (  # noqa: W503
                        QgsWkbTypes.Polygon,
                        QgsWkbTypes.MultiPolygon,
                        QgsWkbTypes.PolygonZM,
                        QgsWkbTypes.MultiPolygonZM,
                    )
                    and lyr.name() in ("Objekti", "Objects")  # noqa: W503
                ):
                    _apply_objects_field_aliases(lyr)
                    _set_objects_layer_alias(lyr)
                    ensure_uuid_field(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Error in _ensure_objects_layer: {e}")

        # Create new layer
        crs = core.iface.mapCanvas().mapSettings().destinationCrs().authid()
        layer = QgsVectorLayer(f"Polygon?crs={crs}", "Objects", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("tip", QVariant.String),
            QgsField("spratova", QVariant.Int),
            QgsField("podzemnih", QVariant.Int),
            QgsField("ulica", QVariant.String),
            QgsField("broj", QVariant.String),
            QgsField("naziv", QVariant.String),
            QgsField("napomena", QVariant.String),
            QgsField(FIBERQ_UUID_FIELD, QVariant.String),
        ])
        layer.updateFields()

        prj.addMapLayer(layer)
        _stylize_objects_layer(layer)

        _apply_objects_field_aliases(layer)
        _set_objects_layer_alias(layer)

        return layer
    except Exception:
        return None


def _stylize_objects_layer(layer):
    """Apply black solid outline + diagonal hatch inside (DWG-like)."""
    # Try to delegate to StyleManager
    try:
        from .style_manager import stylize_objects_layer as sm_stylize
        sm_stylize(layer)
        return
    except Exception as e:
        logger.debug(f"Error in _stylize_objects_layer: {e}")

    # Fallback: inline implementation
    try:
        simple = QgsSimpleFillSymbolLayer()
        simple.setFillColor(QColor(0, 0, 0, 0))
        simple.setStrokeColor(QColor(0, 0, 0))
        simple.setStrokeWidth(0.8)
        simple.setStrokeWidthUnit(QgsUnitTypes.RenderMillimeters)

        hatch = QgsLinePatternFillSymbolLayer()
        try:
            try:
                hatch.setLineAngle(60.0)
            except Exception:
                try:
                    hatch.setAngle(60.0)
                except Exception as e:
                    logger.debug(f"Error in _stylize_objects_layer: {e}")
        except Exception as e:
            logger.debug(f"Error in _stylize_objects_layer: {e}")
        hatch.setDistance(2.2)
        hatch.setDistanceUnit(QgsUnitTypes.RenderMillimeters)
        try:
            sub = hatch.subSymbol()
            if sub and sub.symbolLayerCount() > 0:
                sl = sub.symbolLayer(0)
                try:
                    sl.setColor(QColor(0, 0, 0))
                except Exception as e:
                    logger.debug(f"Error in _stylize_objects_layer: {e}")
                try:
                    sl.setWidth(0.3)
                    sl.setWidthUnit(QgsUnitTypes.RenderMillimeters)
                except Exception as e:
                    logger.debug(f"Error in _stylize_objects_layer: {e}")
        except Exception as e:
            logger.debug(f"Error in _stylize_objects_layer: {e}")

        sym = QgsFillSymbol()
        try:
            sym.deleteSymbolLayer(0)
        except Exception as e:
            logger.debug(f"Error in _stylize_objects_layer: {e}")
        sym.appendSymbolLayer(hatch)
        sym.appendSymbolLayer(simple)

        renderer = QgsSingleSymbolRenderer(sym)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
    except Exception as e:
        logger.debug(f"Error in _stylize_objects_layer: {e}")


# =============================================================================
# GEOPACKAGE EXPORT FUNCTIONS (Phase 1.3)
# =============================================================================

def _telecom_save_all_layers_to_gpkg(iface):
    """
    Export all vector layers to a single GeoPackage and repoint layers in the project.

    Args:
        iface: QGIS interface
    """
    # Try to delegate to ExportManager
    try:
        from .export_manager import save_all_layers_to_gpkg
        save_all_layers_to_gpkg(iface)
        return
    except Exception as e:
        logger.debug(f"Error in _telecom_save_all_layers_to_gpkg: {e}")

    # Fallback: inline implementation
    try:
        prj = QgsProject.instance()

        default_dir = os.path.dirname(prj.fileName()) if prj.fileName() else os.path.expanduser("~")
        gpkg_path, _ = QFileDialog.getSaveFileName(
            iface.mainWindow(),
            "Choose GeoPackage file",
            os.path.join(default_dir, "Telecom.gpkg"),
            "GeoPackage (*.gpkg)"
        )
        if not gpkg_path:
            return
        if not gpkg_path.lower().endswith(".gpkg"):
            gpkg_path += ".gpkg"

        try:
            prj.writeEntry("TelecomPlugin", "gpkg_path", gpkg_path)
        except Exception as e:
            logger.debug(f"Error in _telecom_save_all_layers_to_gpkg: {e}")

        layers = [l for l in prj.mapLayers().values() if isinstance(l, QgsVectorLayer)]  # noqa: E741
        if not layers:
            iface.messageBar().pushWarning("GPKG export", "No vector layers to save.")
            return

        # Commit edits
        for lyr in layers:
            try:
                if lyr.isEditable():
                    lyr.commitChanges()
            except Exception as e:
                logger.debug(f"Error in _telecom_save_all_layers_to_gpkg: {e}")

        used = set()
        errors = []

        for idx, lyr in enumerate(layers):
            base = re.sub(r"[^A-Za-z0-9_]+", "_", lyr.name()).strip("_") or f"layer_{idx + 1}"
            name = base
            c = 1
            while name in used:
                c += 1
                name = f"{base}_{c}"
            used.add(name)

            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName = name
            opts.actionOnExistingFile = (
                QgsVectorFileWriter.CreateOrOverwriteLayer
                if os.path.exists(gpkg_path)
                else QgsVectorFileWriter.CreateOrOverwriteFile
            )

            result = QgsVectorFileWriter.writeAsVectorFormatV3(
                lyr, gpkg_path, QgsCoordinateTransformContext(), opts
            )
            if isinstance(result, tuple):
                err_code = result[0]
                err_msg = result[1] if len(result) > 1 else ""
            else:
                err_code = result
                err_msg = ""

            if err_code != QgsVectorFileWriter.NoError:
                errors.append(f"{lyr.name()}: {err_msg}")
                continue

            uri = f"{gpkg_path}|layername={name}"
            try:
                lyr.setDataSource(uri, lyr.name(), "ogr")
                try:
                    lyr.saveStyleToDatabase("default", "auto-saved by Telecom plugin", True, "")
                except Exception as e:
                    logger.debug(f"Error in _telecom_save_all_layers_to_gpkg: {e}")
            except Exception:
                new_lyr = QgsVectorLayer(uri, lyr.name(), "ogr")
                if new_lyr and new_lyr.isValid():
                    parent = prj.layerTreeRoot().findLayer(lyr.id()).parent()
                    prj.removeMapLayer(lyr.id())
                    prj.addMapLayer(new_lyr, False)
                    parent.insertLayer(0, new_lyr)
                    try:
                        new_lyr.saveStyleToDatabase("default", "auto-saved by Telecom plugin", True, "")
                    except Exception as e:
                        logger.debug(f"Error in _telecom_save_all_layers_to_gpkg: {e}")
                else:
                    errors.append(f"{lyr.name()}: cannot load new layer from GPKG ({uri})")

        prj.setDirty(True)
        if errors:
            iface.messageBar().pushWarning("GPKG export", "Completed with errors:\n" + "\n".join(errors))
        else:
            iface.messageBar().pushSuccess("GPKG export", f"All layers saved to:\n{gpkg_path}")
    except Exception as e:
        try:
            iface.messageBar().pushCritical("GPKG export", f"Unexpected error: {e}")
        except Exception as e:
            logger.debug(f"Error in _telecom_save_all_layers_to_gpkg: {e}")


def _telecom_export_one_layer_to_gpkg(lyr, gpkg_path, iface):
    """
    Export a single vector layer to the GeoPackage and repoint it in the project.

    Args:
        lyr: QgsVectorLayer to export
        gpkg_path: Path to GeoPackage file
        iface: QGIS interface

    Returns:
        bool: True if successful
    """
    # Try to delegate to ExportManager
    try:
        from .export_manager import export_one_layer_to_gpkg
        return export_one_layer_to_gpkg(lyr, gpkg_path, iface)
    except Exception as e:
        logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    # Fallback: inline implementation
    base = re.sub(r"[^A-Za-z0-9_]+", "_", lyr.name()).strip("_") or "layer"
    name = base

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = name
    opts.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteLayer
        if os.path.exists(gpkg_path)
        else QgsVectorFileWriter.CreateOrOverwriteFile
    )

    try:
        if lyr.isEditable():
            lyr.commitChanges()
    except Exception as e:
        logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        lyr, gpkg_path, QgsCoordinateTransformContext(), opts
    )
    if isinstance(result, tuple):
        err_code = result[0]
        err_msg = result[1] if len(result) > 1 else ""
    else:
        err_code = result
        err_msg = ""

    if err_code != QgsVectorFileWriter.NoError:
        try:
            iface.messageBar().pushWarning("GPKG export", f"{lyr.name()}: {err_msg}")
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
        return False

    uri = f"{gpkg_path}|layername={name}"
    try:
        lyr.setDataSource(uri, lyr.name(), "ogr")
        try:
            lyr.saveStyleToDatabase("default", "auto-saved by Telecom plugin", True, "")
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
        return True
    except Exception:
        new_lyr = QgsVectorLayer(uri, lyr.name(), "ogr")
        if new_lyr and new_lyr.isValid():
            prj = QgsProject.instance()
            parent = prj.layerTreeRoot().findLayer(lyr.id()).parent()
            prj.removeMapLayer(lyr.id())
            prj.addMapLayer(new_lyr, False)
            parent.insertLayer(0, new_lyr)
            try:
                new_lyr.saveStyleToDatabase("default", "auto-saved by Telecom plugin", True, "")
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
            return True
        else:
            try:
                iface.messageBar().pushWarning("GPKG export", f"{lyr.name()}: cannot load new layer from GPKG ({uri})")
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
            return False


# =============================================================================
# LAYER MANAGER CLASS
# =============================================================================

class LayerManager:
    """
    Centralized layer management for FiberQ plugin.

    Handles creation, lookup, and organization of all FiberQ layers.
    """

    def __init__(self, iface, plugin=None):
        """
        Initialize the layer manager.

        Args:
            iface: QGIS interface instance
            plugin: Optional reference to main plugin for callbacks
        """
        self.iface = iface
        self.plugin = plugin

    def get_crs(self):
        """Get the current map CRS authority ID."""
        try:
            return self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        except Exception:
            return 'EPSG:3857'

    # =========================================================================
    # POLES LAYER
    # =========================================================================

    def ensure_poles_layer(self):
        """
        Create or return the Poles layer.

        Returns:
            QgsVectorLayer: The poles layer
        """
        project = QgsProject.instance()

        # Check if layer exists
        for lyr in project.mapLayers().values():
            if (
                isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                lyr.geometryType() == QgsWkbTypes.PointGeometry and  # noqa: W504
                lyr.name() in ("Poles", "Stubovi")
            ):
                self._apply_poles_aliases(lyr)
                ensure_uuid_field(lyr)
                return lyr

        # Create new layer
        crs = self.get_crs()
        layer = QgsVectorLayer(f"Point?crs={crs}", "Poles", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("tip", QVariant.String),
            QgsField("podtip", QVariant.String),
            QgsField("visina", QVariant.Double),
            QgsField("materijal", QVariant.String),
            QgsField(FIBERQ_UUID_FIELD, QVariant.String),
        ])
        layer.updateFields()

        self._apply_poles_aliases(layer)
        project.addMapLayer(layer)

        # Apply default style
        try:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol_layer = symbol.symbolLayer(0)
            symbol_layer.setSize(10)
            symbol_layer.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
            layer.renderer().setSymbol(symbol)
            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

        return layer

    def _apply_poles_aliases(self, layer):
        """Apply field aliases to poles layer."""
        try:
            from ..utils.field_aliases import apply_poles_field_aliases
            apply_poles_field_aliases(layer)
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    # =========================================================================
    # SLACK (OPTICAL RESERVE) LAYER
    # =========================================================================

    def ensure_slack_layer(self):
        """
        Create or return the Optical slacks layer.

        Returns:
            QgsVectorLayer: The slack layer
        """
        project = QgsProject.instance()

        # Check if layer exists
        # Issue #2: Check for all possible slack layer names
        for lyr in project.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.PointGeometry  # noqa: W503
                    and lyr.name() in ("Opticke_rezerve", "Optical slacks", "Optical slack")  # noqa: W503
                ):
                    self._apply_slack_aliases(lyr)
                    ensure_uuid_field(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Error in ensure_slack_layer: {e}")

        # Create new layer
        crs = self.get_crs()
        vl = QgsVectorLayer(f"Point?crs={crs}", "Optical slacks", "memory")  # Issue #2: Use plural name
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("tip", QVariant.String),
            QgsField("duzina_m", QVariant.Double),
            QgsField("lokacija", QVariant.String),
            QgsField("cable_layer_id", QVariant.String),
            QgsField("cable_fid", QVariant.Int),
            QgsField("strana", QVariant.String),
            QgsField("napomena", QVariant.String),
            QgsField(FIBERQ_UUID_FIELD, QVariant.String),
        ])
        vl.updateFields()

        self._apply_slack_aliases(vl)
        project.addMapLayer(vl)
        self._stylize_slack_layer(vl)

        return vl

    def _apply_slack_aliases(self, layer):
        """Apply field aliases to slack layer."""
        try:
            from ..utils.field_aliases import apply_slack_field_aliases
            apply_slack_field_aliases(layer)
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    def _stylize_slack_layer(self, vl):
        """Apply simple red circle style to slack layer."""
        try:
            sym = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "size": "3",
            })
            try:
                sym.setColor(QColor(255, 0, 0))
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
            try:
                sym.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

            renderer = QgsSingleSymbolRenderer(sym)
            vl.setRenderer(renderer)
            vl.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    # =========================================================================
    # MANHOLES LAYER
    # =========================================================================

    def ensure_manholes_layer(self):
        """
        Create or return the Manholes layer.

        Returns:
            QgsVectorLayer: The manholes layer
        """
        project = QgsProject.instance()

        # Check if layer exists
        for lyr in project.mapLayers().values():
            try:
                name = lyr.name().strip()
                if name in ("OKNA", "Manholes") and lyr.geometryType() == QgsWkbTypes.PointGeometry:
                    self._apply_manholes_aliases(lyr)
                    ensure_uuid_field(lyr)
                    self.move_layer_to_top(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Skipping layer while locating manholes layer: {e}")
                continue

        # Create new layer
        crs = self.get_crs()
        layer = QgsVectorLayer(f"Point?crs={crs}", "Manholes", "memory")
        pr = layer.dataProvider()
        fields = [
            QgsField("broj_okna", QVariant.String),
            QgsField("tip_okna", QVariant.String),
            QgsField("vrsta_okna", QVariant.String),
            QgsField("polozaj_okna", QVariant.String),
            QgsField("adresa", QVariant.String),
            QgsField("stanje", QVariant.String),
            QgsField("god_ugrad", QVariant.Int),
            QgsField("opis", QVariant.String),
            QgsField("dimenzije", QVariant.String),
            QgsField("mat_zida", QVariant.String),
            QgsField("mat_poklop", QVariant.String),
            QgsField("odvodnj", QVariant.String),
            QgsField("poklop_tes", QVariant.Bool),
            QgsField("poklop_lak", QVariant.Bool),
            QgsField("br_nosaca", QVariant.Int),
            QgsField("debl_zida", QVariant.Double),
            QgsField("lestve", QVariant.String),
            QgsField(FIBERQ_UUID_FIELD, QVariant.String),
        ]
        pr.addAttributes(fields)
        layer.updateFields()

        project.addMapLayer(layer, True)
        self._apply_manholes_aliases(layer)
        self.move_layer_to_top(layer)

        # Apply style via plugin callback if available
        if self.plugin and hasattr(self.plugin, '_apply_manhole_style'):
            try:
                self.plugin._apply_manhole_style(layer)
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

        return layer

    def _apply_manholes_aliases(self, layer):
        """Apply field aliases to manholes layer."""
        try:
            from ..utils.field_aliases import apply_manhole_field_aliases, set_manhole_layer_alias
            apply_manhole_field_aliases(layer)
            set_manhole_layer_alias(layer)
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    # =========================================================================
    # PIPES LAYERS
    # =========================================================================

    def ensure_pipes_group(self):
        """
        Create or return the Pipes layer group.

        Returns:
            QgsLayerTreeGroup: The pipes group
        """
        proj = QgsProject.instance()
        root = proj.layerTreeRoot()

        # Accept both old and new group names
        group = root.findGroup("CEVI") or root.findGroup("Pipes")
        if group is None:
            try:
                group = root.insertGroup(0, "Pipes")
            except Exception:
                group = root.addGroup("Pipes")
        else:
            # Rename old group if needed
            try:
                if group.name() == "CEVI":
                    group.setName("Pipes")
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

        self.move_group_to_top("Pipes")
        return group

    def ensure_pipe_layer(self, name):
        """
        Create or return a pipe layer by name.

        Args:
            name: Layer name (e.g., "PE cevi" or "Prelazne cevi")

        Returns:
            QgsVectorLayer: The pipe layer
        """
        prj = QgsProject.instance()

        alias_map = {
            "PE cevi": "PE pipes",
            "Prelazne cevi": "Transition pipes",
        }
        target_names = {name}
        if name in alias_map:
            target_names.add(alias_map[name])

        # Find existing layer
        for lyr in prj.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.LineGeometry  # noqa: W503
                    and lyr.name() in target_names  # noqa: W503
                ):
                    self._apply_pipe_aliases(lyr)
                    ensure_uuid_field(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

        # Create new layer
        crs = self.get_crs()
        layer = QgsVectorLayer(f"LineString?crs={crs}", name, "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("materijal", QVariant.String),
            QgsField("kapacitet", QVariant.String),
            QgsField("fi", QVariant.Int),
            QgsField("od", QVariant.String),
            QgsField("do", QVariant.String),
            QgsField("duzina_m", QVariant.Double),
            QgsField(FIBERQ_UUID_FIELD, QVariant.String),
        ])
        layer.updateFields()

        # Map tip
        try:
            layer.setMapTipTemplate(
                "<b>[% \"materijal\" %] [% \"kapacitet\" %]</b><br/>Ø [% \"fi\" %] mm"
            )
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

        # Add to pipes group
        prj.addMapLayer(layer, False)
        try:
            group = self.ensure_pipes_group()
            group.addLayer(layer)
        except Exception:
            prj.addMapLayer(layer, True)

        self.move_group_to_top("Pipes")
        self.move_layer_to_top(layer)
        self._apply_pipe_aliases(layer)

        return layer

    def ensure_pe_pipe_layer(self):
        """Create or return the PE pipes layer."""
        return self.ensure_pipe_layer("PE cevi")

    def ensure_transition_pipe_layer(self):
        """Create or return the Transition pipes layer."""
        return self.ensure_pipe_layer("Prelazne cevi")

    def _apply_pipe_aliases(self, layer):
        """Apply field aliases to pipe layer."""
        try:
            from ..utils.field_aliases import apply_pipe_field_aliases, set_pipe_layer_alias
            apply_pipe_field_aliases(layer)
            set_pipe_layer_alias(layer)
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    # =========================================================================
    # DRAWINGS GROUP
    # =========================================================================

    def ensure_drawings_group(self, subgroup_name):
        """
        Create or return a drawings subgroup.

        Args:
            subgroup_name: Name of the subgroup (e.g., "Joint Closures", "ODF")

        Returns:
            QgsLayerTreeGroup: The subgroup
        """
        root = QgsProject.instance().layerTreeRoot()

        # Main drawings group
        group = root.findGroup("Drawings")
        if not group:
            # Backward compat: rename old group
            legacy = root.findGroup("Crteži")
            if legacy:
                try:
                    legacy.setName("Drawings")
                except Exception as e:
                    logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
                group = legacy
            else:
                group = root.addGroup("Drawings")

        # Subgroup
        sub = group.findGroup(subgroup_name)
        if not sub:
            sub = group.addGroup(subgroup_name)

        return sub

    # =========================================================================
    # SERVICE AREA LAYER
    # =========================================================================

    def ensure_service_area_layer(self):
        """
        Create or return the Service Area layer.

        Returns:
            QgsVectorLayer: The service area layer
        """
        try:
            proj = QgsProject.instance()

            # Find existing layer
            for lyr in proj.mapLayers().values():
                try:
                    if (
                        isinstance(lyr, QgsVectorLayer)
                        and lyr.geometryType() == QgsWkbTypes.PolygonGeometry  # noqa: W503
                        and lyr.name() in ('Rejon', 'Service Area')  # noqa: W503
                    ):
                        if lyr.name() == 'Rejon':
                            try:
                                lyr.setName('Service Area')
                            except Exception as e:
                                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
                        ensure_uuid_field(lyr)
                        return lyr
                except Exception as e:
                    logger.debug(f"Skipping layer while locating region layer: {e}")
                    continue

            # Create new layer
            crs = proj.crs().authid() if proj and proj.crs().isValid() else 'EPSG:3857'
            region = QgsVectorLayer(f'Polygon?crs={crs}', 'Service Area', 'memory')
            pr = region.dataProvider()
            pr.addAttributes([
                QgsField('name', QVariant.String),
                QgsField('created_at', QVariant.String),
                QgsField('area_m2', QVariant.Double),
                QgsField('perim_m', QVariant.Double),
                QgsField('count', QVariant.Int),
                QgsField(FIBERQ_UUID_FIELD, QVariant.String),
            ])
            region.updateFields()

            # Simple semi-transparent style
            try:
                sym = region.renderer().symbol()
                sym.setOpacity(0.25)
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

            proj.addMapLayer(region)
            return region

        except Exception:
            return None

    # =========================================================================
    # OBJECTS LAYER
    # =========================================================================

    def ensure_objects_layer(self):
        """
        Create or return the Objects (buildings) layer.

        Returns:
            QgsVectorLayer: The objects layer
        """
        try:
            prj = QgsProject.instance()

            # Find existing layer
            for lyr in prj.mapLayers().values():
                try:
                    if (
                        isinstance(lyr, QgsVectorLayer)
                        and lyr.wkbType() in (  # noqa: W503
                            QgsWkbTypes.Polygon,
                            QgsWkbTypes.MultiPolygon,
                            QgsWkbTypes.PolygonZM,
                            QgsWkbTypes.MultiPolygonZM,
                        )
                        and lyr.name() in ("Objekti", "Objects")  # noqa: W503
                    ):
                        self._apply_objects_aliases(lyr)
                        ensure_uuid_field(lyr)
                        return lyr
                except Exception as e:
                    logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

            # Create new layer
            crs = self.get_crs()
            layer = QgsVectorLayer(f"Polygon?crs={crs}", "Objects", "memory")
            pr = layer.dataProvider()
            pr.addAttributes([
                QgsField("tip", QVariant.String),
                QgsField("spratova", QVariant.Int),
                QgsField("podzemnih", QVariant.Int),
                QgsField("ulica", QVariant.String),
                QgsField("broj", QVariant.String),
                QgsField("naziv", QVariant.String),
                QgsField("napomena", QVariant.String),
                QgsField(FIBERQ_UUID_FIELD, QVariant.String),
            ])
            layer.updateFields()

            prj.addMapLayer(layer)
            self._apply_objects_aliases(layer)

            return layer
        except Exception:
            return None

    def _apply_objects_aliases(self, layer):
        """Apply field aliases to objects layer."""
        try:
            from ..utils.field_aliases import apply_objects_field_aliases, set_objects_layer_alias
            apply_objects_field_aliases(layer)
            set_objects_layer_alias(layer)
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    # =========================================================================
    # ELEMENT LAYERS (ODF, OTB, TB, TO, etc.)
    # =========================================================================

    def ensure_element_layer(self, layer_name):
        """
        Create or return an element layer with appropriate style.

        Args:
            layer_name: Name of the element type (e.g., "ODF", "TB")

        Returns:
            QgsVectorLayer: The element layer
        """
        prj = QgsProject.instance()

        # Find existing layer
        for lyr in prj.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.PointGeometry  # noqa: W503
                    and lyr.name() == layer_name  # noqa: W503
                ):
                    self._apply_element_aliases(lyr)
                    ensure_uuid_field(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

        # Create new layer
        crs = self.get_crs()
        layer = QgsVectorLayer(f"Point?crs={crs}", layer_name, "memory")
        pr = layer.dataProvider()

        # Get default fields for this element type
        fields = self._get_element_fields(layer_name)
        pr.addAttributes(fields)
        layer.updateFields()

        # Apply symbol from element definitions
        self._apply_element_symbol(layer, layer_name)

        # Apply labels
        try:
            s = QgsPalLayerSettings()
            s.fieldName = "naziv"
            s.enabled = True
            layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
            layer.setLabelsEnabled(True)
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

        prj.addMapLayer(layer)
        self._apply_element_aliases(layer)

        return layer

    def _get_element_fields(self, layer_name):
        """Get default fields for an element type."""
        try:
            from ..dialogs.base import default_fields_for
            specs = default_fields_for(layer_name)
        except Exception:
            specs = [("naziv", "Naziv", "text", "", None)]

        fields = []
        for (key, label, kind, default, opts) in specs:
            qt = QVariant.String
            if kind in ("int", "year"):
                qt = QVariant.Int
            elif kind == "double":
                qt = QVariant.Double
            fields.append(QgsField(key, qt))

        if not any(f.name() == "naziv" for f in fields):
            fields.insert(0, QgsField("naziv", QVariant.String))

        # Phase 0.1: Add fiberq_uuid field for Designer compatibility
        if not any(f.name() == FIBERQ_UUID_FIELD for f in fields):
            fields.append(QgsField(FIBERQ_UUID_FIELD, QVariant.String))

        return fields

    def _apply_element_symbol(self, layer, layer_name):
        """Apply appropriate symbol to element layer."""
        try:
            from ..models.element_defs import get_element_def_by_name
            edef = get_element_def_by_name(layer_name) or {}
            spec = edef.get("symbol") if isinstance(edef, dict) else None

            if isinstance(spec, dict) and spec.get('svg_path'):
                symbol = QgsMarkerSymbol.createSimple({
                    'name': 'circle',
                    'size': '5',
                    'size_unit': 'MapUnit'
                })
                try:
                    svg_layer = QgsSvgMarkerSymbolLayer(spec['svg_path'])
                    try:
                        svg_layer.setSize(float(spec.get('size', 6)))
                    except Exception as e:
                        logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
                    try:
                        svg_layer.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
                    except Exception:
                        svg_layer.setSizeUnit(QgsUnitTypes.RenderMapUnits)
                    symbol.changeSymbolLayer(0, svg_layer)
                except Exception as e:
                    logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
            elif isinstance(spec, dict):
                symbol = QgsMarkerSymbol.createSimple(spec)
            else:
                symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'size': '5'})

            try:
                layer.renderer().setSymbol(symbol)
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    def _apply_element_aliases(self, layer):
        """Apply field aliases to element layer."""
        try:
            from ..utils.field_aliases import apply_element_aliases
            apply_element_aliases(layer)
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    # =========================================================================
    # ROUTE LAYER
    # =========================================================================

    def ensure_route_layer(self):
        """
        Create or return the Route layer.

        Returns:
            QgsVectorLayer: The route layer
        """
        prj = QgsProject.instance()

        # Find existing layer
        for lyr in prj.mapLayers().values():
            if (
                isinstance(lyr, QgsVectorLayer)
                and lyr.name() in ('Route', 'Trasa')  # noqa: W503
                and lyr.geometryType() == QgsWkbTypes.LineGeometry  # noqa: W503
            ):
                ensure_uuid_field(lyr)
                return lyr

        # Create new layer
        crs = self.get_crs()
        layer = QgsVectorLayer(f"LineString?crs={crs}", "Route", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("naziv", QVariant.String),
            QgsField("duzina", QVariant.Double),
            QgsField("duzina_km", QVariant.Double),
            QgsField("tip_trase", QVariant.String),
            QgsField(FIBERQ_UUID_FIELD, QVariant.String),
        ])
        layer.updateFields()

        prj.addMapLayer(layer)
        return layer

    # =========================================================================
    # LAYER TREE UTILITIES
    # =========================================================================

    def move_layer_to_top(self, layer):
        """
        Move a layer to the top of the layer tree.

        Args:
            layer: QgsVectorLayer to move
        """
        try:
            proj = QgsProject.instance()
            root = proj.layerTreeRoot()
            node = root.findLayer(layer.id())
            if not node:
                proj.addMapLayer(layer, True)
                node = root.findLayer(layer.id())
                if not node:
                    return

            parent = node.parent() or root
            children = list(parent.children())
            idx = None
            for i, ch in enumerate(children):
                try:
                    if hasattr(ch, "layerId") and ch.layerId() == layer.id():
                        idx = i
                        break
                except Exception as e:
                    logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

            if idx is not None and idx > 0:
                taken = parent.takeChild(idx)
                parent.insertChildNode(0, taken)

            # Custom layer order
            try:
                if root.hasCustomLayerOrder():
                    order = list(root.customLayerOrder())
                    order = [l for l in order if l and l.id() != layer.id()]  # noqa: E741
                    order.insert(0, layer)
                    root.setCustomLayerOrder(order)
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
        except Exception:
            try:
                QgsProject.instance().addMapLayer(layer, True)
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    def move_group_to_top(self, group_name="Pipes"):
        """
        Move a layer group to the top of the layer tree.

        Args:
            group_name: Name of the group to move
        """
        try:
            proj = QgsProject.instance()
            root = proj.layerTreeRoot()

            # Handle both old and new names
            group = root.findGroup(group_name)
            if group is None and group_name == "Pipes":
                group = root.findGroup("CEVI")
            if group is None and group_name == "CEVI":
                group = root.findGroup("Pipes")

            if not group:
                return

            parent = group.parent() or root
            children = list(parent.children())

            # Find group index
            idx = None
            try:
                gname = group.name()
            except Exception:
                gname = group_name

            for i, ch in enumerate(children):
                try:
                    if getattr(ch, "name", lambda: None)() == gname and not hasattr(ch, "layerId"):
                        idx = i
                        break
                except Exception as e:
                    logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

            if idx is not None and idx > 0:
                taken = parent.takeChild(idx)
                parent.insertChildNode(0, taken)

            # Custom layer order - move group layers to front
            try:
                if root.hasCustomLayerOrder():
                    order = list(root.customLayerOrder())

                    def _collect_layers(node):
                        out = []
                        for ch in getattr(node, 'children', lambda: [])():
                            try:
                                if hasattr(ch, "layer") and ch.layer():
                                    out.append(ch.layer())
                                else:
                                    out.extend(_collect_layers(ch))
                            except Exception as e:
                                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
                        return out

                    group_layers = _collect_layers(group)
                    keep = [l for l in order if l not in group_layers]  # noqa: E741
                    root.setCustomLayerOrder(list(group_layers) + keep)
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
        except Exception as e:
            logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")

    # =========================================================================
    # LAYER LOOKUP UTILITIES
    # =========================================================================

    def find_layer_by_name(self, name, geometry_type=None):
        """
        Find a layer by name and optionally geometry type.

        Args:
            name: Layer name to search for
            geometry_type: Optional QgsWkbTypes geometry type

        Returns:
            QgsVectorLayer or None
        """
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.name() == name:
                    if geometry_type is None:
                        return lyr
                    if lyr.geometryType() == geometry_type:
                        return lyr
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
        return None

    def find_layers_by_names(self, names, geometry_type=None):
        """
        Find layers matching any of the given names.

        Args:
            names: List of layer names to search for
            geometry_type: Optional QgsWkbTypes geometry type

        Returns:
            List of matching QgsVectorLayer instances
        """
        result = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.name() in names:
                    if geometry_type is None or lyr.geometryType() == geometry_type:
                        result.append(lyr)
            except Exception as e:
                logger.debug(f"Error in _telecom_export_one_layer_to_gpkg: {e}")
        return result


# Module-level convenience functions for backward compatibility

def get_layer_manager(iface, plugin=None):
    """Get a LayerManager instance."""
    return LayerManager(iface, plugin)


__all__ = [
    # Layer Manager class
    'LayerManager',
    'get_layer_manager',

    # Element definitions
    'ELEMENT_DEFS',
    'NASTAVAK_DEF',

    # Helper functions
    '_normalize_name',
    '_default_fields_for',
    '_apply_fixed_text_label',

    # Element layer functions (Phase 1.3)
    '_element_def_by_name',
    '_ensure_element_layer_with_style',
    '_copy_attributes_between_layers',

    # Service area / region functions (Phase 1.3)
    '_ensure_region_layer',
    '_collect_selected_geometries',
    '_create_region_from_selection',

    # Objects layer functions (Phase 1.3)
    '_set_objects_layer_alias',
    '_apply_objects_field_aliases',
    '_ensure_objects_layer',
    '_stylize_objects_layer',

    # GeoPackage export functions (Phase 1.3)
    '_telecom_save_all_layers_to_gpkg',
    '_telecom_export_one_layer_to_gpkg',
]
