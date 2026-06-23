"""
Legacy bridge module (Phase 2.1).

This module centralizes legacy globals that were previously injected into
`extracted_classes` at runtime from `main_plugin.py`.

In Phase 2.1 we add this module without changing behavior elsewhere.
Later phases will switch `extracted_classes.py` to import from here directly.
"""
from __future__ import annotations

from qgis.PyQt.QtCore import QSettings, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMessageBox

from qgis.core import (
    QgsField,
    QgsFillSymbol,
    QgsLinePatternFillSymbolLayer,
    QgsPalLayerSettings,
    QgsProject,
    QgsSimpleFillSymbolLayer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)

# Phase 5.2: Logging
from .logger import get_logger
logger = get_logger(__name__)

_FIBERQ_LANG_KEY = "FiberQ/lang"


def _get_lang():
    try:
        if QSettings is None:
            return "en"
        return QSettings().value(_FIBERQ_LANG_KEY, "en")
    except Exception:
        return "en"


def _fiberq_translate(text: str, lang: str) -> str:
    if not isinstance(text, str):
        return text
    text = text.strip()
    # Static phrase map
    sr2en = {
        'Publish to PostGIS': 'Publish to PostGIS',
        'Završna rezerva (prečica)': 'End slack (shortcut)',
        'Razgrani cables (offset)': 'Separate cables (offset)',
        'Show shortcuts': 'Show shortcuts',
        'BOM report (XLSX/CSV)': 'BOM report (XLSX/CSV)',
        'Check (health check)': 'Health check',
        'Cable laying': 'Cable laying',
        'Underground': 'Underground',
        'Aerial': 'Aerial', 'Main': 'Main',
        'Distribution': 'Distribution',
        'Drop': 'Drop',

        'Place extension': 'Place extension',
        'Drawings': 'Drawings',
        'Attach drawing': 'Attach drawing',
        'Open drawing (by click)': 'Open drawing (by click)',
        'Open FiberQ web': 'Open FiberQ web',
        'Selection': 'Selection',
        'Delete selected': 'Delete selected',
        'Duct infrastructure': 'Duct infrastructure',
        'Place manholes': 'Place manholes',
        'Place PE duct': 'Place PE duct',
        'Place transition duct': 'Place transition duct',
        'Import points': 'Import points',
        'Locator': 'Locator',
        'Hide locator': 'Hide locator',
        'Relations': 'Relations',
        'Latent elements list': 'Latent elements list',
        'Cut infrastructure': 'Cut infrastructure',
        'Fiber break': 'Fiber break',
        'Color catalog': 'Color catalog',
        'Save all layers to GeoPackage': 'Save all layers to GeoPackage',
        'Auto-save to GeoPackage': 'Auto-save to GeoPackage',
        'Optical schematic view': 'Optical schematic view',
        'Optical slack': 'Optical slack',
        'Add end slack (interactive)': 'Add end slack (interactive)',
        'Add thru slack (interactive)': 'Add thru slack (interactive)',
        'End slack at ends of selected cables': 'End slack at ends of selected cables',
        'Preview and export per-layer and summary': 'Preview and export per-layer and summary',
        'Export (.xlsx / .csv)': 'Export (.xlsx / .csv)',
        'By Layers': 'By Layers',
        'Summary': 'Summary',
        'Move element': 'Move elements',
        'Import image to element': 'Attach image to element',
        'Open image (by click)': 'Open image (by click)',
        'Kreiranje Rejona': 'Create region',
        'Kreiraj rejon': 'Create region',
        'Rejon': 'Region',
        'Nacrtaj region ručno': 'Draw region (manual)',
        'Nacrtaj region rucno': 'Draw region (manual)',

    }
    en2sr = {v: k for k, v in sr2en.items()}
    # Simple prefix rules
    if lang == 'en':
        if text.startswith('Place '):
            return 'Place ' + text[len('Place '):]
        return sr2en.get(text, text)
    else:
        if text.startswith('Place '):
            return 'Place ' + text[len('Place '):]
        return en2sr.get(text, text)


def _map_icon_path(filename: str) -> str:
    import os as _os_mod2
    try:
        base = _os_mod2.path.dirname(_os_mod2.path.dirname(__file__))  # plugin root
        return _os_mod2.path.join(base, 'resources', 'map_icons', filename)
    except Exception:
        return filename


def _normalize_name(s: str) -> str:
    try:
        import unicodedata
        import re
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = s.lower()
        s = re.sub(r"[^a-z0-9_]+", "_", s)
        return s.strip("_")
    except Exception:
        return s


def _default_fields_for(layer_name: str):
    """Return a list of (key, label, kind, default, options) for the dialog.
    kind: 'text' | 'int' | 'double' | 'enum' | 'year'
    """
    base = [
        ("naziv", "Name", "text", "", None),
        ("proizvodjac", "Manufacturer", "text", "", None),
        ("oznaka", "Label", "text", "", None),
        ("kapacitet", "Capacity", "int", 0, None),
        ("ukupno_kj", "Total", "int", 0, None),
        ("zahtev_kapaciteta", "Capacity Requirement", "int", 0, None),
        ("zahtev_rezerve", "Slack Requirement", "int", 0, None),
        ("oznaka_izvoda", "Outlet Label", "text", "", None),
        ("numeracija", "Numbering", "text", "", None),
        ("naziv_objekta", "Object Name", "text", "", None),
        ("adresa_ulica", "Address Street", "text", "", None),
        ("adresa_broj", "Address Number", "text", "", None),
        ("address_id", "Address ID", "text", "", None),
        ("stanje", "Status", "enum", "Planned", ["Planned", "Built", "Existing"]),
        ("godina_ugradnje", "Year of Installation", "year", 2025, None),
    ]
    ln = (layer_name or "").lower()
    if "od ormar" in ln:
        base = [(k, l, kind, (24 if k == "kapacitet" else d), opt) for (k, l, kind, d, opt) in base]
    return base


def _apply_element_aliases(layer):
    """Apply English field aliases to element layers (ODF, OTB, TB, etc.).

    Delegates to utils.field_aliases module.
    """
    from .field_aliases import apply_element_aliases
    apply_element_aliases(layer)


def _apply_fixed_text_label(layer, field_name='naziv', size_mu=8.0, yoff_mu=5.0):
    # Make labels fixed-size in screen millimeters, with a small offset above the point.
    # Similar to the OKNA style to avoid labels growing when zooming out.
    try:
        s = QgsPalLayerSettings()
        s.fieldName = field_name
        s.enabled = True
        # Prefer OverPoint with a small mm offset (robust for various QGIS versions)
        try:
            s.placement = getattr(QgsPalLayerSettings, 'OverPoint', s.placement)
        except Exception as e:
            logger.debug(f"Error in _apply_fixed_text_label: {e}")
        try:
            s.xOffset = 0.0
            s.yOffset = float(yoff_mu)
            s.offsetUnits = QgsUnitTypes.RenderMapUnits
        except Exception as e:
            logger.debug(f"Error in _apply_fixed_text_label: {e}")

        tf = QgsTextFormat()
        try:
            tf.setSize(float(size_mu))
            tf.setSizeUnit(QgsUnitTypes.RenderMapUnits)
        except Exception as e:
            logger.debug(f"Error in _apply_fixed_text_label: {e}")

        try:
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.8)
            buf.setColor(QColor(255, 255, 255))
            tf.setBuffer(buf)
        except Exception as e:
            logger.debug(f"Error in _apply_fixed_text_label: {e}")

        try:
            s.setFormat(tf)
        except Exception as e:
            logger.debug(f"Error in _apply_fixed_text_label: {e}")

        layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()
    except Exception:
        # Do not crash the plugin if labeling fails on some older QGIS.
        pass


ELEMENT_DEFS = [
    {"name": "ODF", "symbol": {"svg_path": _map_icon_path("map_odf.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "TB", "symbol": {"svg_path": _map_icon_path("map_tb.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Patch panel", "symbol": {"svg_path": _map_icon_path("map_patch_panel.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "OTB", "symbol": {"svg_path": _map_icon_path("map_otb.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Indoor OTB", "symbol": {"svg_path": _map_icon_path("map_place_otb_indoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Outdoor OTB", "symbol": {"svg_path": _map_icon_path("map_place_otb_outdoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Pole OTB", "symbol": {"svg_path": _map_icon_path("map_place_otb_pole.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "TO", "symbol": {"svg_path": _map_icon_path("map_place_to.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Indoor TO", "symbol": {"svg_path": _map_icon_path("map_place_to_indoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Outdoor TO", "symbol": {"svg_path": _map_icon_path("map_place_to_outdoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Pole TO", "symbol": {"svg_path": _map_icon_path("map_place_to_pole.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Joint Closure TO", "symbol": {"svg_path": _map_icon_path("map_place_to_joint_closure.svg"), "size": "10", "size_unit": "MapUnit"}},
]

NASTAVAK_DEF = {"name": "Joint Closures", "symbol": {"name": "diamond", "color": "red", "size": "5", "size_unit": "MapUnit"}}
# === UI GROUPS (modular menus/buttons) ===


def _img_key(layer, fid):
    return f"image_map/{layer.id()}/{int(fid)}"


def _img_get(layer, fid):
    """Get image path for a feature.

    Issue #6: Check both new key (FiberQPlugin) and legacy key (StuboviPlugin)
    for backward compatibility with old projects.
    """
    try:
        key = _img_key(layer, fid)
        # Try new key first
        path = QgsProject.instance().readEntry("FiberQPlugin", key, "")[0]
        if path:
            return path
        # Fall back to legacy key for backward compatibility
        path = QgsProject.instance().readEntry("StuboviPlugin", key, "")[0]
        return path
    except Exception:
        return ""


def _img_set(layer, fid, path):
    """Set image path for a feature."""
    try:
        QgsProject.instance().writeEntry("FiberQPlugin", _img_key(layer, fid), path or "")
    except Exception:
        pass


def _set_objects_layer_alias(layer):
    """Set the objects layer display name to 'Objects'.

    Delegates to utils.field_aliases module.
    """
    from .field_aliases import set_objects_layer_alias
    set_objects_layer_alias(layer)


def _apply_objects_field_aliases(layer):
    """Apply English field aliases to an objects layer.

    Delegates to utils.field_aliases module.
    """
    from .field_aliases import apply_objects_field_aliases
    apply_objects_field_aliases(layer)


def _ensure_region_layer(core):
    """
    Ensure a polygon layer for service areas exists.

    Interno smo ranije koristili ime 'Rejon', ali korisniku prikazujemo 'Service Area'.
    """
    try:
        proj = QgsProject.instance()

        # 1) Find existing layer (either 'Rejon' or 'Service Area')
        for lyr in proj.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.PolygonGeometry  # noqa: W503
                    and lyr.name() in ('Rejon', 'Service Area')  # noqa: W503
                ):
                    # If old name 'Rejon', rename so user sees 'Service Area'
                    if lyr.name() == 'Rejon':
                        try:
                            lyr.setName('Service Area')
                        except Exception as e:
                            logger.debug(f"Error in _ensure_region_layer: {e}")
                    return lyr
            except Exception:
                continue

        # 2) If doesn't exist – create new layer named 'Service Area'
        crs = proj.crs().authid() if proj and proj.crs().isValid() else 'EPSG:3857'
        region = QgsVectorLayer(f'Polygon?crs={crs}', 'Service Area', 'memory')
        pr = region.dataProvider()
        pr.addAttributes([
            QgsField('name', QVariant.String),
            QgsField('created_at', QVariant.String),
            QgsField('area_m2', QVariant.Double),
            QgsField('perim_m', QVariant.Double),
            QgsField('count', QVariant.Int),
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


def _ensure_objects_layer(core):
    """Create / return polygon layer 'Objects' with standard fields."""
    try:
        prj = QgsProject.instance()

        # 1) If layer exists - accept both "Objekti" and "Objects"
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
                    return lyr
            except Exception as e:
                logger.debug(f"Error in _ensure_objects_layer: {e}")

        # 2) If doesn't exist – create new layer named "Objects"
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
        ])
        layer.updateFields()

        prj.addMapLayer(layer)
        _stylize_objects_layer(layer)

        # English aliases + layer name display
        _apply_objects_field_aliases(layer)
        _set_objects_layer_alias(layer)

        return layer
    except Exception:
        return None


def _stylize_objects_layer(layer):
    """Apply black solid outline + diagonal hatch inside (DWG-like). Delegates to StyleManager."""
    # Phase 7: Delegate to StyleManager
    try:
        from .core.style_manager import stylize_objects_layer as sm_stylize
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
                    logger.debug(f"Could not set hatch color: {e}")
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
            logger.debug(f"Could not delete symbol layer: {e}")
        sym.appendSymbolLayer(hatch)
        sym.appendSymbolLayer(simple)

        from qgis.core import QgsSingleSymbolRenderer
        renderer = QgsSingleSymbolRenderer(sym)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
    except Exception as e:
        logger.debug(f"Error in _stylize_objects_layer: {e}")


RELACIJE_KATEGORIJE = [
    "Main",
    "Local",
    "International",
    "Metro network",
    "Regional",
]
