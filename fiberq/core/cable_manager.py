# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Cable Manager.

This module provides cable management functionality:
- Styling cable layers
- Laying cables along routes
- Branch offset visualization
- Listing all cables

Phase 5.2: Added logging infrastructure
"""

from typing import List, Dict, Any, Tuple

from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import QMessageBox, QDialog
from qgis.PyQt.QtGui import QColor

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsSymbol,
    QgsSimpleLineSymbolLayer,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsUnitTypes,
    QgsVectorLayerSimpleLabeling,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsTextBufferSettings,
    QgsProperty,
    QgsSymbolLayer,
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)

# Phase 0.1: UUID support for FiberQ Designer
from ..utils.uuid_utils import FIBERQ_UUID_FIELD, generate_uuid  # noqa: E402


class CableManager:
    """Manager for cable operations."""

    def __init__(self, iface, style_manager=None, data_manager=None, route_manager=None):
        """
        Initialize CableManager.

        Args:
            iface: QGIS interface
            style_manager: Optional StyleManager instance
            data_manager: Optional DataManager instance
            route_manager: Optional RouteManager instance
        """
        self.iface = iface
        self.style_manager = style_manager
        self.data_manager = data_manager
        self.route_manager = route_manager

        # State for cable type selection
        self.selected_cable_type = None
        self.selected_cable_subtype = None

    # -------------------------------------------------------------------------
    # Layer alias methods
    # -------------------------------------------------------------------------

    def apply_cable_field_aliases(self, layer: QgsVectorLayer) -> None:
        """Apply English field aliases to a cable layer."""
        try:
            from ..utils.field_aliases import apply_cable_field_aliases
            apply_cable_field_aliases(layer, migrate_values=True)
        except Exception as e:
            logger.debug(f"Error in CableManager.apply_cable_field_aliases: {e}")

    def set_cable_layer_alias(self, layer: QgsVectorLayer) -> None:
        """Set English layer names for cable layers."""
        if layer is None:
            return
        try:
            name = layer.name() or ""
            if name in ("Kablovi_podzemni", "Underground cables"):
                layer.setName("Underground cables")
            elif name in ("Kablovi_vazdusni", "Aerial cables"):
                layer.setName("Aerial cables")
        except Exception as e:
            logger.debug(f"Error in CableManager.set_cable_layer_alias: {e}")

    # -------------------------------------------------------------------------
    # Cable Label Expression (Phase 1.4)
    # -------------------------------------------------------------------------

    def get_cable_label_expression(self) -> str:
        """
        Get the QGIS expression for cable labels.

        Returns a label showing:
        - Line 1: Length in meters (from total_len_m or duzina_m or geometry)
        - Line 2: Cable type (Optical/Copper) + fiber count

        Fiber count logic:
        - If tubes (broj_cevcica) > 0 OR fibers (broj_vlakana) > 0: Show "tubes×fibers"
        - Else if tip_kabla contains a number followed by 'F': Extract and show as "Xf"
        - Else: Show nothing

        Examples:
        - tubes=2, fibers=12 → "2x12"
        - tubes=0, fibers=0, tip_kabla="Optical – 48F" → "48f"
        - tubes=0, fibers=0, tip_kabla="" → ""

        Returns:
            QGIS expression string for cable labels
        """
        return (
            "concat("
            # Line 1: Length in meters
            "format_number(coalesce(\"total_len_m\", \"duzina_m\", length($geometry)), 0), ' m', '\\n', "
            # Line 2: Cable type
            "CASE "
            " WHEN lower(coalesce(\"tip\", '')) LIKE 'optick%' THEN 'Optical' "
            " WHEN lower(coalesce(\"tip\", '')) LIKE 'bakarn%' THEN 'Copper' "
            " WHEN coalesce(\"tip\", '') != '' THEN \"tip\" "
            " ELSE '' "
            "END, ' ', "
            # Fiber count - smart logic
            "CASE "
            # Priority 1: If tubes or fibers are explicitly set (non-zero), use tubes×fibers
            " WHEN coalesce(\"broj_cevcica\", 0) > 0 OR coalesce(\"broj_vlakana\", 0) > 0 "
            "  THEN concat(coalesce(\"broj_cevcica\", 0), 'x', coalesce(\"broj_vlakana\", 0)) "
            # Priority 2: Extract fiber count from tip_kabla (e.g., "Optical – 48F" → "48f")
            " WHEN coalesce(\"tip_kabla\", '') LIKE '%F' OR coalesce(\"tip_kabla\", '') LIKE '%f' "
            "  THEN concat(regexp_substr(coalesce(\"tip_kabla\", ''), '(\\\\d+)[Ff]'), 'f') "
            # Priority 3: Check for pattern like "48F" anywhere in tip_kabla
            " WHEN regexp_match(coalesce(\"tip_kabla\", ''), '\\\\d+[Ff]') "
            "  THEN concat(regexp_substr(coalesce(\"tip_kabla\", ''), '(\\\\d+)[Ff]'), 'f') "
            # Fallback: Empty string
            " ELSE '' "
            "END"
            ")"
        )

    def get_cable_fiber_label(self, feature) -> str:
        """
        Get fiber count label for a single cable feature (Python method).

        This is the Python equivalent of the expression logic, useful for
        programmatic access to cable labels.

        Args:
            feature: QgsFeature or dict-like object with cable attributes

        Returns:
            Fiber count label string (e.g., "2x12", "48f", or "")
        """
        import re

        # Get attribute values (handle both QgsFeature and dict)
        def get_attr(name, default=None):
            try:
                if hasattr(feature, 'attribute'):
                    val = feature.attribute(name)
                    return val if val is not None else default
                elif hasattr(feature, 'get'):
                    return feature.get(name, default)
                elif hasattr(feature, '__getitem__'):
                    try:
                        return feature[name] if feature[name] is not None else default
                    except (KeyError, IndexError):
                        return default
                return default
            except Exception:
                return default

        tubes = get_attr('broj_cevcica', 0) or 0
        fibers = get_attr('broj_vlakana', 0) or 0
        cable_type = get_attr('tip_kabla', '') or ''

        # Priority 1: Use explicit tube/fiber counts if set
        if tubes > 0 or fibers > 0:
            return f"{tubes}x{fibers}"

        # Priority 2: Extract fiber count from cable_type string
        if cable_type:
            match = re.search(r'(\d+)[Ff]', cable_type)
            if match:
                return f"{match.group(1)}f"

        return ""

    # -------------------------------------------------------------------------
    # Styling
    # -------------------------------------------------------------------------

    def stylize_cable_layer(self, cables_layer: QgsVectorLayer) -> None:
        """Apply cable layer style."""
        # Try StyleManager first
        if self.style_manager:
            try:
                self.style_manager.stylize_cable_layer(cables_layer)
                try:
                    self.apply_cable_field_aliases(cables_layer)
                    self.set_cable_layer_alias(cables_layer)
                except Exception as e:
                    logger.debug(f"Error in CableManager.stylize_cable_layer: {e}")
                return
            except Exception as e:
                logger.debug(f"Error in CableManager.stylize_cable_layer: {e}")

        # Fallback: inline implementation
        base_width = 0.8
        base_unit = QgsUnitTypes.RenderUnit.RenderMetersInMapUnits
        try:
            route_layer = next(
                (
                    lyr for lyr in QgsProject.instance().mapLayers().values()
                    if lyr.name().lower().strip() in ("trasa", "route")
                    and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry  # noqa: W503
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
            logger.debug(f"Error in CableManager.stylize_cable_layer: {e}")
        cable_width = max(base_width * 1.6, base_width + 0.6)

        name_l = cables_layer.name().lower()
        is_podzemni = "podzem" in name_l or "underground" in name_l

        COLOR_GLAVNI = QColor(0, 51, 153)
        COLOR_DISTR = QColor(204, 0, 0)
        COLOR_RAZV = QColor(165, 42, 42)

        label_map = {
            "glavni": "Backbone",
            "distributivni": "Distribution",
            "razvodni": "Drop",
        }

        categories = []
        for value, color in [
            ("glavni", COLOR_GLAVNI),
            ("distributivni", COLOR_DISTR),
            ("razvodni", COLOR_RAZV),
        ]:
            sym = QgsSymbol.defaultSymbol(cables_layer.geometryType())
            try:
                if sym.symbolLayerCount() > 0:
                    sym.deleteSymbolLayer(0)
            except Exception as e:
                logger.debug(f"Error in CableManager.stylize_cable_layer: {e}")

            ln = QgsSimpleLineSymbolLayer()
            ln.setColor(color)
            ln.setWidth(cable_width)
            ln.setWidthUnit(base_unit)
            ln.setPenStyle(Qt.PenStyle.DashLine if is_podzemni else Qt.PenStyle.SolidLine)
            sym.appendSymbolLayer(ln)

            label = label_map.get(value, value.capitalize())
            categories.append(QgsRendererCategory(value, sym, label))

        cables_layer.setRenderer(QgsCategorizedSymbolRenderer('podtip', categories))

        try:
            s = QgsPalLayerSettings()
            # Phase 1.4: Improved cable label logic
            # - Shows length in meters
            # - Shows cable type (Optical/Copper)
            # - Smart fiber count: tubes×fibers when set, or extract from tip_kabla (e.g., "48F" → "48f")
            s.fieldName = self.get_cable_label_expression()

            s.isExpression = True
            try:
                if hasattr(QgsPalLayerSettings, 'LinePlacement') and hasattr(QgsPalLayerSettings.LinePlacement, 'AboveLine'):
                    s.placement = QgsPalLayerSettings.LinePlacement.AboveLine
                elif hasattr(QgsPalLayerSettings, 'Line'):
                    s.placement = QgsPalLayerSettings.Placement.Line
            except Exception as e:
                logger.debug(f"Error in CableManager.stylize_cable_layer: {e}")

            tf = QgsTextFormat()
            tf.setSize(9)
            tf.setColor(QColor(200, 0, 0))
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.8)
            buf.setColor(QColor(255, 255, 255))
            tf.setBuffer(buf)
            s.setFormat(tf)

            cables_layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
            cables_layer.setLabelsEnabled(True)
        except Exception as e:
            logger.debug(f"Error in CableManager.stylize_cable_layer: {e}")

        try:
            self.apply_cable_field_aliases(cables_layer)
            self.set_cable_layer_alias(cables_layer)
        except Exception as e:
            logger.debug(f"Error in CableManager.stylize_cable_layer: {e}")

        cables_layer.triggerRepaint()

    # -------------------------------------------------------------------------
    # Branch offset methods
    # -------------------------------------------------------------------------

    def ensure_branch_index_field(self, layer: QgsVectorLayer) -> None:
        """Ensure layer has INT field 'branch_index'."""
        try:
            if layer.fields().indexFromName("branch_index") != -1:
                return
            pr = layer.dataProvider()
            pr.addAttributes([QgsField("branch_index", QVariant.Int)])
            layer.updateFields()
        except Exception as e:
            logger.debug(f"Error in CableManager.ensure_branch_index_field: {e}")

    def compute_branch_indices_for_layer(self, layer: QgsVectorLayer, tol_m: float = 0.3) -> Tuple[int, int]:
        """
        Assign branch_index for cables with same endpoints (direction-independent).

        Args:
            layer: Cable layer
            tol_m: Tolerance for grouping in meters

        Returns:
            Tuple of (groups_count, updated_count)
        """
        if layer is None or layer.geometryType() != QgsWkbTypes.GeometryType.LineGeometry:
            return 0, 0

        tol_units = float(tol_m)

        def round_key(pt):
            return (int(round(pt.x() / tol_units)),
                    int(round(pt.y() / tol_units)))

        groups = {}  # key = ((x1,y1),(x2,y2)), value = [fid,...]

        for f in layer.getFeatures():
            g = f.geometry()
            if g is None or g.isEmpty():
                continue

            try:
                if g.isMultipart():
                    line = g.asMultiPolyline()[0]
                else:
                    line = g.asPolyline()
            except Exception as e:
                logger.debug(f"Skipping feature; could not read cable geometry: {e}")
                continue

            if len(line) < 2:
                continue

            p1 = line[0]
            p2 = line[-1]
            k1 = round_key(p1)
            k2 = round_key(p2)
            # Direction-independent key
            key = (k1, k2) if k1 <= k2 else (k2, k1)
            groups.setdefault(key, []).append(f.id())

        if not groups:
            return 0, 0

        # Write branch_index values
        self.ensure_branch_index_field(layer)
        idx = layer.fields().indexFromName("branch_index")
        if idx == -1:
            return 0, 0

        layer.startEditing()
        updated = 0

        for key, ids in groups.items():
            ids_sorted = sorted(ids)
            n = len(ids_sorted)

            if n == 1:
                # Single cable between these nodes - no offset
                try:
                    layer.changeAttributeValue(ids_sorted[0], idx, 0)
                    updated += 1
                except Exception as e:
                    logger.debug(f"Error in CableManager.round_key: {e}")
                continue

            # n >= 2 - assign symmetric values around zero
            for i, fid in enumerate(ids_sorted):
                pos = i * 2 - (n - 1)
                try:
                    layer.changeAttributeValue(fid, idx, int(pos))
                    updated += 1
                except Exception as e:
                    logger.debug(f"Error in CableManager.round_key: {e}")

        layer.commitChanges()
        return len(groups), updated

    def apply_branch_offset_style(self, layer: QgsVectorLayer, offset_mm: float = 2.0) -> None:
        """Apply data-defined offset based on branch_index."""
        # Try StyleManager first
        if self.style_manager:
            try:
                self.style_manager.apply_branch_offset_style(layer, offset_mm)
                return
            except Exception as e:
                logger.debug(f"Error in CableManager.apply_branch_offset_style: {e}")

        # Fallback: inline implementation
        if layer is None or layer.renderer() is None:
            return
        if layer.geometryType() != QgsWkbTypes.GeometryType.LineGeometry:
            return

        renderer = layer.renderer()
        expr = f'coalesce("branch_index",0) * {float(offset_mm)}'

        def apply_on_symbol(sym):
            if sym is None:
                return
            try:
                for sl in sym.symbolLayers():
                    try:
                        if hasattr(sl, "setOffsetUnit"):
                            sl.setOffsetUnit(QgsUnitTypes.RenderUnit.RenderMillimeters)
                        if hasattr(sl, "setOffset"):
                            sl.setOffset(0.0)
                    except Exception as e:
                        logger.debug(f"Error in CableManager.apply_on_symbol: {e}")
                    try:
                        prop_enum = getattr(QgsSymbolLayer, "PropertyOffset", None)
                        if prop_enum is not None and hasattr(sl, "setDataDefinedProperty"):
                            sl.setDataDefinedProperty(
                                prop_enum,
                                QgsProperty.fromExpression(expr),
                            )
                    except Exception as e:
                        logger.debug(f"Error in CableManager.apply_on_symbol: {e}")
                    if hasattr(sl, "subSymbol") and callable(sl.subSymbol):
                        subsym = sl.subSymbol()
                        if subsym is not None:
                            apply_on_symbol(subsym)
            except Exception as e:
                logger.debug(f"Error in CableManager.apply_on_symbol: {e}")

        if not isinstance(renderer, QgsCategorizedSymbolRenderer):
            sym = None
            if hasattr(renderer, "symbol"):
                try:
                    sym = renderer.symbol()
                except Exception:
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
            logger.debug(f"Error in CableManager.apply_on_symbol: {e}")

    def branch_cables_offset(self) -> None:
        """
        Handler for 'Branch cables (offset)' button.
        Computes branch_index and applies offset for active line layer.
        """
        try:
            layer = self.iface.activeLayer()
        except Exception:
            layer = None

        if not (layer and isinstance(layer, QgsVectorLayer)
                and layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry):  # noqa: W503
            try:
                self.iface.messageBar().pushWarning(
                    "Branch cables",
                    "Activate a cable line layer first."
                )
            except Exception as e:
                logger.debug(f"Error in CableManager.branch_cables_offset: {e}")
            return

        groups, updated = self.compute_branch_indices_for_layer(layer, tol_m=1.3)
        self.apply_branch_offset_style(layer, offset_mm=2.0)

        try:
            msg = (
                f"Branching complete – groups: {groups}, "
                f"updated cables: {updated}. "
                "If you don't see separation, refresh view (Ctrl+R)."
            )
            self.iface.messageBar().pushInfo("Branch cables", msg)
        except Exception as e:
            logger.debug(f"Error in CableManager.branch_cables_offset: {e}")

        try:
            layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in CableManager.branch_cables_offset: {e}")

    # -------------------------------------------------------------------------
    # Cable listing
    # -------------------------------------------------------------------------

    def list_all_cables(self) -> List[Dict[str, Any]]:
        """List all cables from cable layers."""
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.list_all_cables()
            except Exception as e:
                logger.debug(f"Error in CableManager.list_all_cables: {e}")

        # Fallback: inline implementation
        items = []
        candidate_names = {
            "Kablovi_podzemni",
            "Kablovi_vazdusni",
            "Underground cables",
            "Aerial cables",
        }

        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (
                    not isinstance(lyr, QgsVectorLayer)
                    or lyr.geometryType() != QgsWkbTypes.GeometryType.LineGeometry  # noqa: W503
                    or lyr.name() not in candidate_names  # noqa: W503
                ):
                    continue
            except Exception as e:
                logger.debug(f"Skipping layer; could not check cable layer type: {e}")
                continue

            fields = lyr.fields()
            for feat in lyr.getFeatures():
                attrs = {fld.name(): feat[fld.name()] for fld in fields}
                tip = attrs.get("tip") or ""
                podtip_code = attrs.get("podtip") or ""
                kap = attrs.get("kapacitet") or ""
                cc = attrs.get("color_code") or ""
                od = attrs.get("od") or ""
                do = attrs.get("do") or ""

                podtip_labels = {
                    "glavni": "Backbone",
                    "distributivni": "Distribution",
                    "razvodni": "Drop",
                    "Backbone": "Backbone",
                    "Distribution": "Distribution",
                    "Drop": "Drop",
                }
                podtip_label = podtip_labels.get(str(podtip_code), str(podtip_code))

                opis_parts = []
                if tip:
                    opis_parts.append(str(tip))
                if podtip_label:
                    opis_parts.append(str(podtip_label))
                if kap:
                    opis_parts.append(str(kap))

                opis = " ".join(opis_parts) if opis_parts else f"FID {int(feat.id())}"

                items.append({
                    "layer_id": lyr.id(),
                    "layer_name": lyr.name(),
                    "fid": int(feat.id()),
                    "opis": opis,
                    "tip": tip,
                    "podtip": podtip_code,
                    "kapacitet": kap,
                    "color_code": cc,
                    "od": od,
                    "do": do,
                })

        return items

    # -------------------------------------------------------------------------
    # Cable laying
    # -------------------------------------------------------------------------

    def lay_cable_type(self, tip: str, podtip: str) -> None:
        """Set cable type and subtype, then lay cable."""
        self.selected_cable_type = tip
        self.selected_cable_subtype = podtip
        self.lay_cable()

    def lay_cable(self, color_codes_callback=None, path_callback=None) -> None:
        """
        Lay a cable along a route between two selected elements.

        Args:
            color_codes_callback: Optional callable returning list of color codes
            path_callback: Optional callable (route_layer, pt1, pt2, tol) returning path points
        """
        from ..dialogs.cable_dialog import CablePickerDialog
        from ..models.element_defs import NASTAVAK_DEF, ELEMENT_DEFS

        # Collect selections from all element layers (+ Poles + Manholes)
        relevant_names = [NASTAVAK_DEF['name']] + [d['name'] for d in ELEMENT_DEFS] + ['Poles', 'Stubovi', 'OKNA', 'Manholes']
        selected = []
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry and lyr.name() in relevant_names:
                feats = lyr.selectedFeatures()
                for f in feats:
                    selected.append((lyr, f))

        if len(selected) != 2:
            QMessageBox.warning(self.iface.mainWindow(), "Cable", "Select exactly 2 elements (of any type)!")
            return

        # Find route layer
        route_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route', 'Trasa') and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
                route_layer = lyr
                break
        if route_layer is None or route_layer.featureCount() == 0:
            QMessageBox.warning(self.iface.mainWindow(), "Cable", "Layer 'Route' not found or has no line!")
            return

        point1 = selected[0][1].geometry().asPoint()
        point2 = selected[1][1].geometry().asPoint()

        # Determine type/subtype
        tip = self.selected_cable_type
        podtip = self.selected_cable_subtype

        def _infer_vrsta(t):
            if not t:
                return None
            tl = str(t).lower()
            if "vazdu" in tl or "aerial" in tl:
                return "vazdusni"
            return "podzemni"

        default_vrsta = "vazdusni" if _infer_vrsta(tip) == "vazdusni" else "podzemni"

        # Get color codes
        color_codes = []
        if color_codes_callback:
            try:
                color_codes = color_codes_callback()
            except Exception as e:
                logger.debug(f"Error in CableManager._infer_vrsta: {e}")
        elif self.data_manager:
            try:
                color_codes = self.data_manager.list_color_codes()
            except Exception as e:
                logger.debug(f"Error in CableManager._infer_vrsta: {e}")

        dlg = CablePickerDialog(self.iface.mainWindow(), default_vrsta=default_vrsta, default_podtip=podtip, color_codes=color_codes)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        vals = dlg.values()
        vrsta = vals["vrsta"]
        tip = vals["tip"]
        podtip = vals["podtip"]
        color_code = vals["color_code"]
        broj_cevcica = vals["broj_cevcica"]
        broj_vlakana = vals["broj_vlakana"]
        tip_kabla = vals["tip_kabla"]
        vrsta_vlakana = vals["vrsta_vlakana"]
        vrsta_omotaca = vals["vrsta_omotaca"]
        vrsta_armature = vals["vrsta_armature"]
        talasno_podrucje = vals["talasno_podrucje"]
        naziv = vals["naziv"]
        slabljenje_dbkm = vals["slabljenje_dbkm"]
        hrom_disp_ps_nmxkm = vals["hrom_disp_ps_nmxkm"]
        stanje_kabla = vals["stanje_kabla"]
        cable_laying = vals["cable_laying"]
        vrsta_mreze = vals["vrsta_mreze"]
        godina_ugradnje = vals["godina_ugradnje"]
        konstr_vlakna_u_cevcicama = vals["konstr_vlakna_u_cevcicama"]
        konstr_sa_uzlepljenim_elementom = vals["konstr_sa_uzlepljenim_elementom"]
        konstr_punjeni_kabl = vals["konstr_punjeni_kabl"]
        konstr_sa_arm_vlaknima = vals["konstr_sa_arm_vlaknima"]
        konstr_bez_metalnih = vals["konstr_bez_metalnih"]
        # Phase 0.3: Fiber schema for FiberQ Designer
        fibers_per_tube = vals.get("fibers_per_tube", 0)
        total_fibers = vals.get("total_fibers", 0)
        color_standard = vals.get("color_standard", "")

        # Select cable layer
        layer_suffix = "vazdusni" if str(vrsta).lower().startswith("vazdu") else "podzemni"
        if layer_suffix == "vazdusni":
            candidate_names = ("Kablovi_vazdusni", "Aerial cables")
            default_name = "Aerial cables"
        else:
            candidate_names = ("Kablovi_podzemni", "Underground cables")
            default_name = "Underground cables"

        cables_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry  # noqa: W503
                    and lyr.name() in candidate_names  # noqa: W503
                ):
                    cables_layer = lyr
                    break
            except Exception as e:
                logger.debug(f"Error in CableManager._infer_vrsta: {e}")

        if cables_layer is None:
            crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
            cables_layer = QgsVectorLayer(f"LineString?crs={crs}", default_name, "memory")
            pr = cables_layer.dataProvider()

            pr.addAttributes([
                QgsField("tip", QVariant.String),
                QgsField("podtip", QVariant.String),
                QgsField("color_code", QVariant.String),
                QgsField("broj_cevcica", QVariant.Int),
                QgsField("broj_vlakana", QVariant.Int),
                QgsField("tip_kabla", QVariant.String),
                QgsField("vrsta_vlakana", QVariant.String),
                QgsField("vrsta_omotaca", QVariant.String),
                QgsField("vrsta_armature", QVariant.String),
                QgsField("talasno_podrucje", QVariant.String),
                QgsField("naziv", QVariant.String),
                QgsField("slabljenje_dbkm", QVariant.Double),
                QgsField("hrom_disp_ps_nmxkm", QVariant.Double),
                QgsField("stanje_kabla", QVariant.String),
                QgsField("cable_laying", QVariant.String),
                QgsField("vrsta_mreze", QVariant.String),
                QgsField("godina_ugradnje", QVariant.Int),
                QgsField("konstr_vlakna_u_cevcicama", QVariant.Int),
                QgsField("konstr_sa_uzlepljenim_elementom", QVariant.Int),
                QgsField("konstr_punjeni_kabl", QVariant.Int),
                QgsField("konstr_sa_arm_vlaknima", QVariant.Int),
                QgsField("konstr_bez_metalnih", QVariant.Int),
                QgsField("od", QVariant.String),
                QgsField("do", QVariant.String),
                QgsField("duzina_m", QVariant.Double),
                QgsField("slack_m", QVariant.Double),
                QgsField("total_len_m", QVariant.Double),
                QgsField(FIBERQ_UUID_FIELD, QVariant.String),
                # Phase 0.3: Fiber schema for FiberQ Designer
                QgsField("fibers_per_tube", QVariant.Int),
                QgsField("total_fibers", QVariant.Int),
                QgsField("color_standard", QVariant.String),
            ])

            cables_layer.updateFields()
            QgsProject.instance().addMapLayer(cables_layer)

        # Ensure layer has all needed fields
        needed_fields = {
            "tip": QVariant.String,
            "podtip": QVariant.String,
            "color_code": QVariant.String,
            "broj_cevcica": QVariant.Int,
            "broj_vlakana": QVariant.Int,
            "tip_kabla": QVariant.String,
            "vrsta_vlakana": QVariant.String,
            "vrsta_omotaca": QVariant.String,
            "vrsta_armature": QVariant.String,
            "talasno_podrucje": QVariant.String,
            "naziv": QVariant.String,
            "slabljenje_dbkm": QVariant.Double,
            "hrom_disp_ps_nmxkm": QVariant.Double,
            "stanje_kabla": QVariant.String,
            "cable_laying": QVariant.String,
            "vrsta_mreze": QVariant.String,
            "godina_ugradnje": QVariant.Int,
            "konstr_vlakna_u_cevcicama": QVariant.Int,
            "konstr_sa_uzlepljenim_elementom": QVariant.Int,
            "konstr_punjeni_kabl": QVariant.Int,
            "konstr_sa_arm_vlaknima": QVariant.Int,
            "konstr_bez_metalnih": QVariant.Int,
            "od": QVariant.String,
            "do": QVariant.String,
            "duzina_m": QVariant.Double,
            "slack_m": QVariant.Double,
            "total_len_m": QVariant.Double,
            FIBERQ_UUID_FIELD: QVariant.String,
            # Phase 0.3: Fiber schema for FiberQ Designer
            "fibers_per_tube": QVariant.Int,
            "total_fibers": QVariant.Int,
            "color_standard": QVariant.String,
        }
        to_add = []
        for fname, ftype in needed_fields.items():
            if cables_layer.fields().indexFromName(fname) == -1:
                to_add.append(QgsField(fname, ftype))
        if to_add:
            prov = (cables_layer.providerType() or "").lower()
            if prov in ("memory", "ogr", "spatialite"):
                cables_layer.dataProvider().addAttributes(to_add)
                cables_layer.updateFields()
            else:
                self.iface.messageBar().pushWarning(
                    "FiberQ",
                    "Cable layer is missing fields (slack_m/total_len_m). Add them in the database schema."
                )

        self.stylize_cable_layer(cables_layer)

        def _disp_name(layer, feat):
            try:
                if layer.name() in ('OKNA', 'Manholes'):
                    if 'broj_okna' in layer.fields().names():
                        broj = feat['broj_okna']
                        if broj is not None and str(broj).strip():
                            return f"MH {str(broj).strip()}"  # Issue #9: KO -> MH
                idx = layer.fields().indexFromName('naziv')
                if idx != -1:
                    val = feat['naziv']
                    if val is not None and str(val).strip():
                        return str(val).strip()
                if layer.name() == 'Poles':
                    tip = str(feat['tip']) if 'tip' in layer.fields().names() and feat['tip'] is not None else ''
                    return ("Pole " + tip).strip() or f"Pole {int(feat.id())}"  # Stub -> Pole
            except Exception as e:
                logger.debug(f"Error in CableManager._disp_name: {e}")
            return f"{layer.name()}:{int(feat.id())}"

        od_naziv = _disp_name(selected[0][0], selected[0][1])
        do_naziv = _disp_name(selected[1][0], selected[1][1])

        # Find cable geometry along route
        cable_geom = None
        for feat in route_layer.getFeatures():
            geom = feat.geometry()
            if geom.type() != QgsWkbTypes.GeometryType.LineGeometry:
                continue
            line = geom.asPolyline()
            if not line:
                multi = geom.asMultiPolyline()
                if multi and len(multi) > 0:
                    line = multi[0]
            dists1 = [QgsPointXY(point1).distance(QgsPointXY(p)) for p in line]
            dists2 = [QgsPointXY(point2).distance(QgsPointXY(p)) for p in line]
            min_dist1 = min(dists1)
            min_dist2 = min(dists2)
            idx1 = dists1.index(min_dist1)
            idx2 = dists2.index(min_dist2)
            if min_dist1 < 1 and min_dist2 < 1 and idx1 != idx2:
                if idx1 < idx2:
                    cable_geom = QgsGeometry.fromPolylineXY(line[idx1:idx2 + 1])
                else:
                    cable_geom = QgsGeometry.fromPolylineXY(list(reversed(line[idx2:idx1 + 1])))
                break

        if cable_geom is None:
            # Try through joined route segments (virtual merge)
            tol_units = self.iface.mapCanvas().mapUnitsPerPixel() * 6
            path_pts = None

            if path_callback:
                try:
                    path_pts = path_callback(route_layer, point1, point2, tol_units)
                except Exception as e:
                    logger.debug(f"Error in CableManager._disp_name: {e}")
            elif self.route_manager:
                try:
                    path_pts = self.route_manager.build_path_across_network(route_layer, QgsPointXY(point1), QgsPointXY(point2), tol_units)
                    if not path_pts:
                        path_pts = self.route_manager.build_path_across_joined_routes(route_layer, QgsPointXY(point1), QgsPointXY(point2), tol_units)
                except Exception as e:
                    logger.debug(f"Error in CableManager._disp_name: {e}")

            if path_pts:
                cable_geom = QgsGeometry.fromPolylineXY(path_pts)

        if cable_geom is None:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Joint closures or elements are not at the ends of the same route or connected routes.")
            return

        # Create cable feature
        feat = QgsFeature(cables_layer.fields())
        feat.setGeometry(cable_geom)
        feat.setAttribute("tip", tip)
        feat.setAttribute("podtip", podtip)
        feat.setAttribute("color_code", color_code)
        feat.setAttribute("broj_cevcica", broj_cevcica)
        feat.setAttribute("broj_vlakana", broj_vlakana)
        feat.setAttribute("tip_kabla", tip_kabla)
        feat.setAttribute("vrsta_vlakana", vrsta_vlakana)
        feat.setAttribute("vrsta_omotaca", vrsta_omotaca)
        feat.setAttribute("vrsta_armature", vrsta_armature)
        feat.setAttribute("talasno_podrucje", talasno_podrucje)
        feat.setAttribute("naziv", naziv)
        feat.setAttribute("slabljenje_dbkm", slabljenje_dbkm)
        feat.setAttribute("hrom_disp_ps_nmxkm", hrom_disp_ps_nmxkm)
        feat.setAttribute("stanje_kabla", stanje_kabla)
        feat.setAttribute("cable_laying", cable_laying)
        feat.setAttribute("vrsta_mreze", vrsta_mreze)
        feat.setAttribute("godina_ugradnje", godina_ugradnje)
        feat.setAttribute("konstr_vlakna_u_cevcicama", konstr_vlakna_u_cevcicama)
        feat.setAttribute("konstr_sa_uzlepljenim_elementom", konstr_sa_uzlepljenim_elementom)
        feat.setAttribute("konstr_punjeni_kabl", konstr_punjeni_kabl)
        feat.setAttribute("konstr_sa_arm_vlaknima", konstr_sa_arm_vlaknima)
        feat.setAttribute("konstr_bez_metalnih", konstr_bez_metalnih)
        feat.setAttribute("od", od_naziv)
        feat.setAttribute("do", do_naziv)
        # Phase 0.3: Set fiber schema fields for FiberQ Designer
        try:
            if "fibers_per_tube" in cables_layer.fields().names():
                feat.setAttribute("fibers_per_tube", fibers_per_tube)
            if "total_fibers" in cables_layer.fields().names():
                feat.setAttribute("total_fibers", total_fibers)
            if "color_standard" in cables_layer.fields().names():
                feat.setAttribute("color_standard", color_standard)
        except Exception as e:
            logger.debug(f"Error setting fiber schema on cable: {e}")
        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            if FIBERQ_UUID_FIELD in cables_layer.fields().names():
                feat.setAttribute(FIBERQ_UUID_FIELD, generate_uuid())
        except Exception as e:
            logger.debug(f"Error setting UUID on cable: {e}")
        try:
            cable_length = cable_geom.length()
            feat.setAttribute("duzina_m", cable_length)
            feat.setAttribute("slack_m", 0.0)  # Issue #1: Initialize slack to 0
            feat.setAttribute("total_len_m", cable_length)  # Issue #1: Set total_len_m = duzina_m initially
        except Exception as e:
            logger.debug(f"Error in CableManager.lay_cable setting length: {e}")

        cables_layer.startEditing()
        cables_layer.addFeature(feat)
        cables_layer.commitChanges()
        cables_layer.updateExtents()
        cables_layer.triggerRepaint()

        # Record for undo (v1.2 — Feature 2)
        try:
            undo_mgr = getattr(self, 'undo_manager', None)
            if undo_mgr:
                undo_mgr.record_add(cables_layer, feat)
        except Exception as e:
            logger.debug(f"Error recording undo for cable: {e}")

        QMessageBox.information(self.iface.mainWindow(), "FiberQ", "Cable has been laid along the route!")


__all__ = ['CableManager']
