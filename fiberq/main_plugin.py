# pyright: reportMissingImports=false, reportMissingModuleSource=false
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QInputDialog, QDialog, QVBoxLayout, QLabel, QDialogButtonBox,
    QFileDialog)
from qgis.core import (
    QgsVectorFileWriter, QgsVectorLayer,
    QgsProject, QgsField, QgsFeature,
    QgsGeometry, QgsPointXY, QgsWkbTypes,
    QgsSymbol, QgsUnitTypes, QgsCoordinateTransform
)
from qgis.PyQt.QtGui import QIcon, QColor

# =============================================================================
# Phase 1.1: Icon and Translation helpers moved to utils/helpers.py
# =============================================================================
from .utils.helpers import (
    # Icon loading functions
    _load_icon,
    # Language/i18n functions
    _get_lang,
    _set_lang,
    _apply_text_and_tooltip,
    _apply_menu_language,
)

# =============================================================================
# Phase 5.1: Logging infrastructure
# =============================================================================
from .utils.logger import get_logger

# Module logger
logger = get_logger(__name__)

# For backward compatibility with QSettings import
try:
    from qgis.PyQt.QtCore import QSettings
except Exception:
    QSettings = None

# =============================================================================
# Phase 1.2: Pro License functions moved to core/license_manager.py
# =============================================================================
from .core.license_manager import (  # noqa: E402
    _fiberq_check_pro,
)

# =============================================================================
# Phase 1.3: Layer utility functions moved to core/layer_manager.py
# =============================================================================
from .core.layer_manager import (  # noqa: E402
    # Element definitions
    ELEMENT_DEFS,
    NASTAVAK_DEF,
    # Element layer functions
    _ensure_element_layer_with_style,
    _copy_attributes_between_layers,
    # Service area functions
    _create_region_from_selection,
    # GeoPackage export functions
    _telecom_save_all_layers_to_gpkg,
)

# Re-exported for ui/ (objects_ui, routing_ui); pending WP2 extraction
from .core.layer_manager import (  # noqa: E402, F401
    _ensure_objects_layer,
    _stylize_objects_layer,
    _telecom_export_one_layer_to_gpkg,
)

# =============================================================================
# Phase 1.1: The following functions were moved to utils/helpers.py:
# - _fiberq_translate, _apply_text_and_tooltip, _apply_menu_language, _element_icon_for
# =============================================================================

from qgis.gui import QgsVertexMarker  # noqa: E402
from qgis.PyQt.QtCore import QVariant  # noqa: E402
from qgis.PyQt import sip  # noqa: E402
import os  # noqa: E402

# === FIXED LABEL UTILITY (screen-fixed text in mm) ===
# =============================================================================
# Phase 1.3: The following functions/constants were moved to core/layer_manager.py:
# - _apply_fixed_text_label, _normalize_name, _default_fields_for
# - ELEMENT_DEFS, NASTAVAK_DEF
# =============================================================================


def _apply_element_aliases(layer):
    """Apply English field aliases to element layers (ODF, OTB, TB, etc.).

    Delegates to utils.field_aliases module.
    """
    from .utils.field_aliases import apply_element_aliases
    apply_element_aliases(layer)


# ============================================================================
# FiberQ v2.0 - Refactored Main Plugin
# ============================================================================
# This file has been refactored from v1 with the following changes:
# - Serbian identifiers translated to English
# - Constants extracted to utils/constants.py
# - Element definitions extracted to models/element_defs.py
# - Color catalogs extracted to models/color_catalogs.py
# - Configuration management in core/config_manager.py
# - Improved code organization and documentation
# ============================================================================

# PrePlaceAttributesDialog moved to dialogs/element_dialog.py (Phase 4)
pass
# === UI GROUPS (modular menus/buttons) ===
# RoutingUI moved to ui/routing_ui.py (Phase 5)
from .ui.routing_ui import RoutingUI  # noqa: E402


# DrawingsUI moved to ui/drawings_ui.py (Phase 5)
from .ui.drawings_ui import DrawingsUI  # noqa: E402

# CableLayingUI moved to ui/cable_ui.py (Phase 5)
from .ui.cable_ui import CableLayingUI  # noqa: E402

# ElementPlacementUI moved to ui/elements_ui.py (Phase 5)
from .ui.elements_ui import ElementPlacementUI  # noqa: E402

# DuctingUI moved to ui/ducting_ui.py (Phase 5)
from .ui.ducting_ui import DuctingUI  # noqa: E402

# SelectionUI moved to ui/selection_ui.py (Phase 5)
from .ui.selection_ui import SelectionUI  # noqa: E402

# Internal values written to field "tip_trase"
TRASA_TYPE_OPTIONS = ["vazdusna", "podzemna", "kroz objekat"]

# Labels for dialog display (user view)
TRASA_TYPE_LABELS = {
    "vazdusna": "Aerial",
    "podzemna": "Underground",
    "kroz objekat": "Through the object",
}

# Reverse mapping: EN labela -> SR kod
TRASA_LABEL_TO_CODE = {v: k for k, v in TRASA_TYPE_LABELS.items()}


# === BOM Report dialog ===


class FiberQPlugin:
    def _ensure_plugin_svg_search_path(self):
        """Ensure plugin SVG icons resolve (styles may reference only filenames)."""
        try:
            from qgis.core import QgsApplication
            import os
            svg_dir = os.path.join(os.path.dirname(__file__), 'resources', 'map_icons')
            paths = list(QgsApplication.svgPaths() or [])
            if svg_dir and os.path.isdir(svg_dir) and svg_dir not in paths:
                QgsApplication.setSvgPaths(paths + [svg_dir])
        except Exception as e:
            logger.debug(f"Could not set SVG search path: {e}")

    def _fiberq_apply_language(self, lang):
        """Apply language to toolbar actions, drop-down menus, and common dialogs."""
        try:
            self._fiberq_lang = lang
        except Exception as e:
            logger.debug(f"Could not set language attribute: {e}")

        # 1) Translate known QAction objects collected in self.actions (text + tooltip)
        try:
            for a in getattr(self, 'actions', []) or []:
                _apply_text_and_tooltip(a, lang)
        except Exception as e:
            logger.debug(f"Could not translate actions: {e}")

        # Also translate individual top-level actions not stored in the list (defensive)
        for name in [
            'action_publish_pg', 'action_slack_quick', 'action_branch', 'action_hotkeys',
            'action_bom', 'action_health_check', 'action_schematic', 'action_import_points',
            'action_locator', 'action_clear_locator', 'action_relations', 'action_latent_list',
            'action_fiber_break', 'action_color_catalog', 'action_save_gpkg', 'action_auto_gpkg'
        ]:
            try:
                a = getattr(self, name, None)
                if a:
                    _apply_text_and_tooltip(a, lang)
            except Exception as e:
                logger.debug(f"Could not translate action '{name}': {e}")

        # 2) Translate drop-down menus and buttons from UI groups if present
        for group_name in ['ui_crtezi', 'ui_kabl', 'ui_polaganje', 'ui_kanalizacija', 'ui_selekcija', 'ui_rezerve']:
            try:
                grp = getattr(self, group_name, None)
                if not grp:
                    continue
                # menu title + actions
                if hasattr(grp, 'menu') and grp.menu:
                    _apply_menu_language(grp.menu, lang)
                if hasattr(grp, 'menu_kabl') and grp.menu_kabl:
                    _apply_menu_language(grp.menu_kabl, lang)
                if hasattr(grp, 'menu_kabl_podzemni') and grp.menu_kabl_podzemni:
                    _apply_menu_language(grp.menu_kabl_podzemni, lang)
                if hasattr(grp, 'menu_kabl_vazdusni') and grp.menu_kabl_vazdusni:
                    _apply_menu_language(grp.menu_kabl_vazdusni, lang)
                # toolbar button text/tooltip
                if hasattr(grp, 'button') and grp.button:
                    _apply_text_and_tooltip(grp.button, lang)
                if hasattr(grp, 'btn_kabl') and grp.btn_kabl:
                    _apply_text_and_tooltip(grp.btn_kabl, lang)
            except Exception as e:
                logger.debug(f"Could not translate UI group '{group_name}': {e}")

        # 3) Update language toggle caption/tooltip
        try:
            if hasattr(self, '_fiberq_lang_action') and self._fiberq_lang_action:
                self._fiberq_lang_action.setText('EN' if lang == 'sr' else 'SR')
                self._fiberq_lang_action.setToolTip(
                    'Promeni jezik interfejsa na engleski' if lang == 'sr' else 'Switch UI language to Serbian'
                )
        except Exception as e:
            logger.debug(f"Could not update language toggle: {e}")

        # 4) Store preference
        try:
            _set_lang(lang)
        except Exception as e:
            logger.debug(f"Could not store language preference: {e}")

    def _fiberq_toggle_language(self):
        lang = getattr(self, '_fiberq_lang', None) or _get_lang()
        lang = 'en' if lang == 'sr' else 'sr'
        _set_lang(lang)
        self._fiberq_apply_language(lang)
    # === BOM: otvori dijalog ===

    def open_bom_dialog(self):
        try:
            dlg = _BOMDialog(self.iface, parent=self.iface.mainWindow())
            try:
                dlg.apply_language(_get_lang())
            except Exception as e:
                logger.debug(f"Could not apply language to BOM dialog: {e}")
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "BOM report", f"Error: {e}")

    # === LOCATOR: helper methods ===
    def open_locator_dialog(self):
        # Otvori dijalog za unos adrese i centriranje mape.
        try:
            dlg = LocatorDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Locator", f"Error opening locator: {e}")

    def _center_and_mark_wgs84(self, lon, lat, label=None):
        # Pomeri mapu na zadate WGS84 koordinate (lon, lat) i postavi marker.
        canvas = self.iface.mapCanvas()
        try:
            from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
            wgs84 = QgsCoordinateReferenceSystem(4326)
            dest = canvas.mapSettings().destinationCrs()
            xform = QgsCoordinateTransform(wgs84, dest, QgsProject.instance())
            pt = xform.transform(QgsPointXY(lon, lat))
        except Exception as e:
            logger.debug(f"Coordinate transform failed, using raw coordinates: {e}")
            pt = QgsPointXY(lon, lat)

        # Center and zoom
        try:
            canvas.setCenter(pt)
            canvas.zoomScale(1500)
            canvas.refresh()
        except Exception as e:
            logger.warning(f"Could not center map: {e}")

        # Mark with marker (remove previous if exists)
        try:
            if hasattr(self, "_locator_marker") and self._locator_marker is not None:
                try:
                    self.iface.mapCanvas().scene().removeItem(self._locator_marker)
                except Exception as e:
                    logger.debug(f"Could not remove marker from scene: {e}")
                    try:
                        self._locator_marker.hide()
                    except Exception as e2:
                        logger.debug(f"Could not hide old marker: {e2}")
                self._locator_marker = None

            m = QgsVertexMarker(canvas)
            m.setCenter(pt)
            m.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
            m.setIconSize(18)
            m.setPenWidth(3)
            try:
                m.setColor(QColor(255, 0, 0))
            except Exception as e:
                logger.debug(f"Could not set marker color: {e}")
            m.show()
            self._locator_marker = m
        except Exception as e:
            logger.warning(f"Could not create locator marker: {e}")

        if label:
            try:
                self.iface.messageBar().pushInfo("Locator", f"Found: {label}")
            except Exception as e:
                logger.debug(f"Could not show message bar info: {e}")

    def clear_locator_marker(self):
        if hasattr(self, "_locator_marker") and self._locator_marker:
            try:
                self.iface.mapCanvas().scene().removeItem(self._locator_marker)
            except Exception as e:
                logger.debug(f"Could not remove marker from scene, hiding instead: {e}")
                self._locator_marker.hide()
            self._locator_marker = None
            self.iface.mapCanvas().refresh()

    def __init__(self, iface):
        self.iface = iface
        self.layer = None
        self.toolbar = None
        self.point_tool = None
        self.actions = []
        self._hk_shortcuts = []
        self.breakpoint_tool = None  # === DODATO ===
        self.selected_cable_type = None
        self.selected_cable_subtype = None

        # Phase 6: Initialize LayerManager
        try:
            from .core.layer_manager import LayerManager
            self.layer_manager = LayerManager(iface, self)
        except Exception as e:
            logger.warning(f"Could not initialize LayerManager: {e}")
            self.layer_manager = None

        # Phase 7: Initialize StyleManager
        try:
            from .core.style_manager import StyleManager
            self.style_manager = StyleManager(iface, self)
        except Exception as e:
            logger.warning(f"Could not initialize StyleManager: {e}")
            self.style_manager = None

        # Phase 8: Initialize DataManager and ExportManager
        try:
            from .core.data_manager import DataManager
            self.data_manager = DataManager(iface, self)
        except Exception as e:
            logger.warning(f"Could not initialize DataManager: {e}")
            self.data_manager = None

        try:
            from .core.export_manager import ExportManager
            self.export_manager = ExportManager(iface, self)
        except Exception as e:
            logger.warning(f"Could not initialize ExportManager: {e}")
            self.export_manager = None

        # Phase 3.1: Initialize SlackManager
        try:
            from .core.slack_manager import SlackManager
            self.slack_manager = SlackManager(iface, self.layer_manager, self.style_manager)
            # Set callback for cable styling
            self.slack_manager.set_cable_style_callback(lambda lyr: self._stylize_cable_layer(lyr))
        except Exception as e:
            logger.warning(f"Could not initialize SlackManager: {e}")
            self.slack_manager = None

        # Phase 3.2: Initialize RouteManager
        try:
            from .core.route_manager import RouteManager
            self.route_manager = RouteManager(iface, self.style_manager)
        except Exception as e:
            logger.warning(f"Could not initialize RouteManager: {e}")
            self.route_manager = None

        # Phase 3.3: Initialize CableManager
        try:
            from .core.cable_manager import CableManager
            self.cable_manager = CableManager(iface, self.style_manager, self.data_manager, self.route_manager)
        except Exception as e:
            logger.warning(f"Could not initialize CableManager: {e}")
            self.cable_manager = None

        # Phase 3.4: Initialize RelationsManager
        try:
            from .core.relations_manager import RelationsManager
            self.relations_manager = RelationsManager(self.data_manager)
        except Exception as e:
            logger.warning(f"Could not initialize RelationsManager: {e}")
            self.relations_manager = None

        # Phase 3.5: Initialize DrawingManager
        try:
            from .core.drawing_manager import DrawingManager
            self.drawing_manager = DrawingManager(iface, self.layer_manager)
        except Exception as e:
            logger.warning(f"Could not initialize DrawingManager: {e}")
            self.drawing_manager = None

        # Phase 3.6: Initialize PipeManager
        try:
            from .core.pipe_manager import PipeManager
            self.pipe_manager = PipeManager(iface, self.layer_manager, self.style_manager, self.data_manager)
        except Exception as e:
            logger.warning(f"Could not initialize PipeManager: {e}")
            self.pipe_manager = None

        # Phase 3.7: Initialize ColorManager
        try:
            from .core.color_manager import ColorManager
            self.color_manager = ColorManager(iface, self.data_manager)
        except Exception as e:
            logger.warning(f"Could not initialize ColorManager: {e}")
            self.color_manager = None

        # Undo Manager (v1.2 — Feature 2)
        try:
            from .core.undo_manager import FiberQUndoManager
            self.undo_manager = FiberQUndoManager(iface)
        except Exception as e:
            logger.warning(f"Could not initialize UndoManager: {e}")
            self.undo_manager = None

        # Wire undo_manager into core managers that don't have a plugin ref
        if self.undo_manager:
            for mgr_name in ('cable_manager', 'route_manager', 'slack_manager'):
                mgr = getattr(self, mgr_name, None)
                if mgr:
                    mgr.undo_manager = self.undo_manager

        # Command Manager — repeat last command (v1.2 — Feature 3)
        try:
            from .tools.command_manager import CommandManager
            self.command_manager = CommandManager(self)
        except Exception as e:
            logger.warning(f"Could not initialize CommandManager: {e}")
            self.command_manager = None

    # --- FiberQ Pro gating ---

    def check_pro(self) -> bool:
        try:
            return _fiberq_check_pro(self.iface)
        except Exception as e:
            logger.debug(f"Pro check failed: {e}")
            return False

    # --- Publish to PostGIS ---

    def open_publish_dialog(self):
        try:
            try:
                if hasattr(self, "check_pro") and not self.check_pro():
                    return
            except Exception as e:
                logger.debug(f"check_pro method failed, using fallback: {e}")
                if not _fiberq_check_pro(self.iface):
                    return
            from .addons.publish_pg import open_publish_dialog as _open
            _open(self.iface)
        except Exception as e:
            try:
                from qgis.PyQt.QtWidgets import QMessageBox
                QMessageBox.critical(self.iface.mainWindow(), "Publish to PostGIS", f"Greška: {e}")
            except Exception as e2:
                logger.error(f"Could not show error dialog: {e2}")

    # --- Health check (toolbar action) ---
    def run_health_check(self):
        try:
            from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
            from qgis.PyQt.QtWidgets import QMessageBox

            msgs = []

            project = QgsProject.instance()
            layers = {
                lyr.name(): lyr
                for lyr in project.mapLayers().values()
                if isinstance(lyr, QgsVectorLayer)
            }

            # Key layers (accept both Serbian and English names if present)
            route_layer = layers.get("Route") or layers.get("Route")
            poles_layer = layers.get("Poles") or layers.get("Poles")
            manholes_layer = layers.get("Manholes") or layers.get("OKNA")

            # Route – line
            if route_layer and route_layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
                msgs.append("Routes: OK")
            else:
                msgs.append("Routes: MISSING or wrong type")

            # Poles – point
            if poles_layer and poles_layer.geometryType() == QgsWkbTypes.GeometryType.PointGeometry:
                msgs.append("Poles: OK")
            else:
                msgs.append("Poles: MISSING or wrong type")

            # Manholes – optional
            if manholes_layer:
                msgs.append("Manholes: OK")
            else:
                msgs.append("Manholes: MISSING")

            # 1) short summary
            try:
                self.iface.messageBar().pushInfo("Health check", " | ".join(msgs))
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.run_health_check: {e}")

            # 2) detailed route consistency (if available)
            try:
                if hasattr(self, "check_consistency"):
                    self.check_consistency()
            except Exception as e:
                try:
                    QMessageBox.warning(
                        self.iface.mainWindow(),
                        "Health check",
                        f"Error while running detailed route check:\n{e}",
                    )
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.run_health_check: {e}")

        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.run_health_check: {e}")

    # --- Change element type ---
    def _change_element_type(self, src_layer, src_fid, new_name: str):
        """Move feature from src_layer to target layer `new_name`.
        Safe against PK/UNIQUE constraints (won't copy fid; won't delete source if insert fails).
        """
        from qgis.core import QgsFeature, QgsGeometry

        # get source feature
        f = None
        for feat in src_layer.getFeatures():
            if int(feat.id()) == int(src_fid):
                f = feat
                break
        if f is None:
            raise RuntimeError("Selected element was not found.")

        # ensure target layer
        dst_layer = _ensure_element_layer_with_style(self, new_name)

        # copy attributes (without PK fields)
        vals = _copy_attributes_between_layers(f, dst_layer)

        # create new feature
        new_f = QgsFeature(dst_layer.fields())
        try:
            new_f.setGeometry(QgsGeometry(f.geometry()))
        except Exception as e:
            logger.debug(f"Could not create geometry copy, using original: {e}")
            new_f.setGeometry(f.geometry())

        for k, v in vals.items():
            try:
                new_f.setAttribute(k, v)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._change_element_type: {e}")

        # INSERT into destination (check success!)
        dst_layer.startEditing()
        ok = dst_layer.addFeature(new_f)
        if not ok:
            try:
                dst_layer.rollBack()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._change_element_type: {e}")
            raise RuntimeError("Failed to insert into target layer (constraint/PK conflict).")

        if not dst_layer.commitChanges():
            try:
                dst_layer.rollBack()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._change_element_type: {e}")
            raise RuntimeError("Failed to commit changes to target layer.")

        dst_layer.triggerRepaint()

        # delete old only after successful insert
        try:
            src_layer.startEditing()
            src_layer.deleteFeature(int(src_fid))
            src_layer.commitChanges()
            src_layer.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin._change_element_type: {e}")

    def activate_change_element_type_tool(self):
        try:
            self._change_elem_tool = ChangeElementTypeTool(self.iface, self)
            self.iface.mapCanvas().setMapTool(self._change_elem_tool)
        except Exception as e:
            try:
                from qgis.PyQt.QtWidgets import QMessageBox
                QMessageBox.critical(self.iface.mainWindow(), "Izmena tipa elementa", f"Greška: {e}")
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.activate_change_element_type_tool: {e}")

    # --- Infrastructure cut tool ---

    def open_fiberq_web(self):
        # Open FiberQ web app (URL from config.ini)
        return _open_fiberq_web(self.iface)

    def save_all_layers_to_gpkg(self):
        # Save all layers to GeoPackage
        return _telecom_save_all_layers_to_gpkg(self.iface)

    def run_create_service_area(self):
        try:
            dlg = CreateRegionDialog(self, parent=self.iface.mainWindow())
            if dlg.exec() == QDialog.DialogCode.Accepted:
                return _create_region_from_selection(self, dlg.region_name(), dlg.buffer_value())
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.run_create_service_area: {e}")
        return False

    def activate_draw_service_area_manual(self):
        try:
            if not hasattr(self, '_draw_region_tool') or self._draw_region_tool is None:
                self._draw_region_tool = DrawRegionPolygonTool(self.iface, self)
            self.iface.mapCanvas().setMapTool(self._draw_region_tool)
            self._record_cmd('draw_service_area')
            return True
        except Exception as e:
            logger.warning(f"Could not activate service area tool: {e}")
            return False

    def ui_import_image(self):
        # 1) require selection
        try:
            from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
        except Exception as e:
            logger.error(f"Could not import Qt widgets: {e}")
            return
        layer = self.iface.activeLayer()
        if not layer or layer.selectedFeatureCount() == 0:
            QMessageBox.information(self.iface.mainWindow(), 'FiberQ', 'Select one or more elements and try again.')
            return
        feats = layer.selectedFeatures()

        # 2) choose image
        path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            'Choose image',
            '',
            'Images (*.jpg *.jpeg *.png *.gif);;All files (*.*)'
        )
        if not path:
            return

        # 3) store mapping on each selected feature
        for f in feats:
            _img_set(layer, f.id(), path)

        QMessageBox.information(self.iface.mainWindow(), 'FiberQ', f'Image linked to {len(feats)} element(s).')

        # 4) switch to click-to-open tool
        try:
            self._open_img_tool
        except AttributeError:
            try:
                self._open_img_tool = OpenImageMapTool(self)
            except Exception as e:
                logger.warning(f"Could not create image tool: {e}")
                self._open_img_tool = None
        if self._open_img_tool is not None:
            try:
                self.iface.mapCanvas().setMapTool(self._open_img_tool)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.ui_import_image: {e}")
            try:
                self.iface.messageBar().pushInfo('Image', 'Click on an element to open its image (ESC to exit).')
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.ui_import_image: {e}")

    def ui_clear_image(self):
        try:
            from qgis.PyQt.QtWidgets import QMessageBox
        except Exception as e:
            logger.error(f"Could not import Qt widgets: {e}")
            return
        layer = self.iface.activeLayer()
        if not layer or layer.selectedFeatureCount() == 0:
            QMessageBox.information(self.iface.mainWindow(), 'FiberQ', 'Select one or more elements and try again.')
            return
        feats = layer.selectedFeatures()
        for f in feats:
            _img_set(layer, f.id(), '')
        QMessageBox.information(self.iface.mainWindow(), 'FiberQ', f'Image link removed for {len(feats)} element(s).')

    def ui_move_elements(self):
        try:
            if not hasattr(self, '_move_tool') or self._move_tool is None:
                self._move_tool = MoveFeatureTool(self.iface)
            self.iface.mapCanvas().setMapTool(self._move_tool)
            self.iface.messageBar().pushInfo('Move', 'Click on an element, move the mouse and confirm with left click (right click to cancel).')
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.ui_move_elements: {e}")

    def activate_infrastructure_cut_tool(self):
        try:
            from .addons.infrastructure_cut import InfrastructureCutTool
            self._infra_cut_tool = InfrastructureCutTool(self.iface, self)
            try:
                self._infra_cut_tool.setAction(self.action_infra_cut)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.activate_infrastructure_cut_tool: {e}")
            self.iface.mapCanvas().setMapTool(self._infra_cut_tool)
            try:
                self.iface.messageBar().pushInfo(
                    "Cutiing",
                    "Tool activated. Move mouse over line (red cross), left click to cut, right/ESC exit.",
                )
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.activate_infrastructure_cut_tool: {e}")
        except Exception as e:
            try:
                from qgis.PyQt.QtWidgets import QMessageBox
                QMessageBox.critical(self.iface.mainWindow(), "Infrastructure cutting", f"Error: {e}")
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.activate_infrastructure_cut_tool: {e}")
# --- Help/About ---

    def _fiberq_read_metadata(self) -> dict:
        import os
        import configparser
        md = {}
        try:
            md_path = os.path.join(os.path.dirname(__file__), 'metadata.txt')
            cp = configparser.ConfigParser()
            cp.read(md_path, encoding='utf-8')
            if cp.has_section('general'):
                md = dict(cp.items('general'))
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin._fiberq_read_metadata: {e}")
        return md

    def _fiberq_read_config_value(self, section: str, key: str, default: str = "") -> str:
        import os
        import configparser
        try:
            cfg_path = os.path.join(os.path.dirname(__file__), 'config.ini')
            cp = configparser.ConfigParser()
            cp.read(cfg_path, encoding='utf-8')
            if cp.has_section(section) and cp.has_option(section, key):
                return cp.get(section, key)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin._fiberq_read_config_value: {e}")
        return default

    def show_about_dialog(self):
        try:
            md = self._fiberq_read_metadata()
            name = (md.get('name') or 'FiberQ').strip()
            version = (md.get('version') or '1.0').strip()
            author = (md.get('author') or '').strip()
            email = (md.get('email') or '').strip()
            about = (md.get('about') or '').strip()
            viewer_url = (self._fiberq_read_config_value('web', 'viewer_url', '') or '').strip()
            support_url = (self._fiberq_read_config_value('web', 'support_url', '') or '').strip()

            dlg = QDialog(self.iface.mainWindow())
            dlg.setWindowTitle(f"{name} – About")
            layout = QVBoxLayout(dlg)

            # Rich text body
            parts = [
                f"<h3 style='margin:0 0 6px 0'>{name}</h3>",
                f"<b>Version:</b> {version}<br>",
            ]
            if author:
                parts.append(f"<b>Author:</b> {author}<br>")
            if email:
                parts.append(f"<b>Email:</b> <a href='mailto:{email}'>{email}</a><br>")
            if viewer_url:
                parts.append(f"<b>Preview map URL:</b> <a href='{viewer_url}'>{viewer_url}</a><br>")
            if support_url:
                parts.append(f"<b>Support URL:</b> <a href='{support_url}'>{support_url}</a><br>")
            # NEW: call-to-action text
            parts.append("<hr style='margin:10px 0'>")
            parts.append(
                "<div style='margin-top:6px'>"
                "<b>Get involved:</b> Want to help shape the next FiberQ release? "
                "Report bugs and share ideas at fiberq.net or email me."
                "</div>"
            )

            if about:
                parts.append("<hr style='margin:10px 0'>")
                parts.append(f"<div style='white-space:pre-wrap'>{about}</div>")

            lbl = QLabel(''.join(parts))
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setOpenExternalLinks(True)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
            bb.accepted.connect(dlg.accept)
            layout.addWidget(bb)

            dlg.resize(520, 280)
            dlg.exec()
        except Exception as e:
            try:
                QMessageBox.information(self.iface.mainWindow(), 'FiberQ', f'About dialog error: {e}')
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.show_about_dialog: {e}")

    # === OPTICAL SLACK: layer and logic ===

    def _set_slack_layer_alias(self, layer):
        """Set layer alias for optical slack layer."""
        if self.slack_manager:
            self.slack_manager.set_slack_layer_alias(layer)

    def _apply_slack_field_aliases(self, layer):
        """Apply English field aliases to optical slack layer."""
        if self.slack_manager:
            self.slack_manager.apply_slack_field_aliases(layer)

    def _ensure_slack_layer(self):
        """Create or return the Optical slack layer."""
        # Phase 3.1: Delegate to SlackManager
        if self.slack_manager:
            return self.slack_manager.ensure_slack_layer()
        return None

    def _stylize_slack_layer(self, vl):
        """Apply simple red circle style to slack layer."""
        # Phase 3.1: Delegate to SlackManager
        if self.slack_manager:
            self.slack_manager.stylize_slack_layer(vl)

    def _recompute_slack_for_cable(self, cable_layer_id: str, cable_fid: int):
        """Compute sum of slack for cable and update cable attributes."""
        # Phase 3.1: Delegate to SlackManager
        if self.slack_manager:
            self.slack_manager.recompute_slack_for_cable(cable_layer_id, cable_fid)

    def _start_slack_interactive(self, default_tip="Terminal"):
        """Start map tool for interactive slack placement."""
        # Phase 3.1: Delegate to SlackManager
        if self.slack_manager:
            self.slack_manager.start_slack_interactive(default_tip)
            self._record_cmd('place_slack', default_tip=default_tip)
            return

        # Minimal fallback
        try:
            dlg = SlackDialog(self.iface.mainWindow(), default_tip=default_tip)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            params = dlg.values()
            self._reserve_tool = SlackPlaceTool(self.iface, self, params)
            self.iface.mapCanvas().setMapTool(self._reserve_tool)
            self._record_cmd('place_slack', default_tip=default_tip)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin._start_slack_interactive: {e}")

    def generate_terminal_slack_for_selected(self):
        """For selected cables, create terminal slack at both endpoints."""
        # Phase 3.1: Delegate to SlackManager
        if self.slack_manager:
            self.slack_manager.generate_terminal_slack_for_selected()

    def stylize_route_layer(self, route_layer):
        """Apply route layer style."""
        # Phase 3.2: Delegate to RouteManager
        if self.route_manager:
            self.route_manager.stylize_route_layer(route_layer)
            return

        # Minimal fallback
        if self.style_manager:
            try:
                self.style_manager.stylize_route_layer(route_layer)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.stylize_route_layer: {e}")

    # === Helper functions for 'virtual merge' of routes when laying cables ===

    def _round_key(self, pt: QgsPointXY, tol: float):
        """Round point coordinates for use as dict key."""
        if self.route_manager:
            return self.route_manager.round_key(pt, tol)
        from .utils.geometry import round_key
        return round_key(pt, tol)

    def _first_last_points_of_geom(self, geom: QgsGeometry):
        """Get first and last points of a geometry."""
        if self.route_manager:
            return self.route_manager.first_last_points_of_geom(geom)
        from .utils.geometry import get_first_last_points
        return get_first_last_points(geom)

    def _build_path_across_network(self, route_layer, start_pt: QgsPointXY, end_pt: QgsPointXY, tol_units: float):
        """Route through ALL vertices without physically merging features."""
        if self.route_manager:
            return self.route_manager.build_path_across_network(route_layer, start_pt, end_pt, tol_units)
        from .utils.routing import build_path_across_network
        return build_path_across_network(route_layer, start_pt, end_pt, tol_units)

    def _build_path_across_joined_trasa(self, route_layer, start_pt: QgsPointXY, end_pt: QgsPointXY, tol_units: float):
        """Find path across joined routes at feature level."""
        if self.route_manager:
            return self.route_manager.build_path_across_joined_routes(route_layer, start_pt, end_pt, tol_units)
        from .utils.routing import build_path_across_joined_routes
        return build_path_across_joined_routes(route_layer, start_pt, end_pt, tol_units)

    def initGui(self):
        # Toolbar
        self.toolbar = self.iface.addToolBar('FiberQ Toolbar')
        self.toolbar.setObjectName('FiberQToolbar')

        # Make sure SVGs in styles resolve on every machine
        self._ensure_plugin_svg_search_path()

        # --- Language toggle button (SR/EN) ---
        try:
            self._fiberq_lang_action = QAction('EN', self.iface.mainWindow())
            self._fiberq_lang_action.setToolTip('Switch UI language to English')
            self._fiberq_lang_action.triggered.connect(self._fiberq_toggle_language)
            self.toolbar.addAction(self._fiberq_lang_action)
            try:
                from qgis.PyQt.QtCore import QTimer
                # Apply stored language after UI is ready
                QTimer.singleShot(0, lambda: self._fiberq_apply_language(_get_lang()))
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Label "FiberQ" at the start of toolbar
        try:
            _lbl_fiberq = QLabel("FiberQ")
            _lbl_fiberq.setStyleSheet("color:#334155; font-weight:600; padding-right:6px;")
            self.toolbar.addWidget(_lbl_fiberq)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # --- Undo / Redo buttons (v1.2 — Feature 2) ---
        try:
            pass

            # Undo button
            self.action_undo = QAction(
                _load_icon('ic_undo.svg'), 'Undo (FiberQ)', self.iface.mainWindow()
            )
            self.action_undo.setToolTip('Undo last FiberQ action (Ctrl+Shift+Z)')
            self.action_undo.setShortcut(QKeySequence('Ctrl+Shift+Z'))
            self.action_undo.triggered.connect(self._on_undo)
            self.toolbar.addAction(self.action_undo)
            self.actions.append(self.action_undo)

            # Redo button
            self.action_redo = QAction(
                _load_icon('ic_redo.svg'), 'Redo (FiberQ)', self.iface.mainWindow()
            )
            self.action_redo.setToolTip('Redo last undone FiberQ action (Ctrl+Shift+Y)')
            self.action_redo.setShortcut(QKeySequence('Ctrl+Shift+Y'))
            self.action_redo.triggered.connect(self._on_redo)
            self.toolbar.addAction(self.action_redo)
            self.actions.append(self.action_redo)

            # Separator after undo/redo
            self.toolbar.addSeparator()
        except Exception as e:
            logger.debug(f"Error adding Undo/Redo buttons: {e}")

        # Help/About (minimal popup)
        try:
            if not hasattr(self, 'action_help_about') or self.action_help_about is None:
                try:
                    icon_help = _load_icon('ic_help.svg')
                except Exception as e:
                    logger.debug(f"Could not load help icon: {e}")
                    try:
                        icon_help = QIcon.fromTheme('help-about')
                    except Exception as e2:
                        logger.debug(f"Could not load theme icon: {e2}")
                        icon_help = QIcon()
                self.action_help_about = QAction(icon_help, 'Help / About', self.iface.mainWindow())
                self.action_help_about.setToolTip('Help and information about FiberQ')
                try:
                    self.action_help_about.triggered.connect(self.show_about_dialog)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.initGui: {e}")

                try:
                    self.toolbar.addAction(self.action_help_about)
                except Exception as e:
                    logger.debug(f"Could not add to toolbar, trying iface: {e}")
                    try:
                        self.iface.addToolBarIcon(self.action_help_about)
                    except Exception as e2:
                        logger.debug(f"Could not add toolbar icon: {e2}")

                try:
                    self.iface.addPluginToMenu('FiberQ', self.action_help_about)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.initGui: {e}")

                try:
                    self.actions.append(self.action_help_about)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Publish to PostGIS

        try:

            self.action_publish_pg = QAction('Publish to PostGIS', self.iface.mainWindow())

            try:
                self.action_publish_pg.setIcon(_load_icon('ic_publish_pg.svg'))
            except Exception as e:
                logger.debug(f"Could not load publish_pg icon: {e}")
            self.action_publish_pg.setToolTip('Publish the active (or selected) layer to PostGIS')

            self.action_publish_pg.triggered.connect(self.open_publish_dialog)

            self.actions.append(self.action_publish_pg)

            try:

                self.toolbar.addAction(self.action_publish_pg)

            except Exception as e:

                logger.debug(f"Error in FiberQPlugin.initGui: {e}")

            try:

                self.iface.addPluginToMenu('FiberQ', self.action_publish_pg)

            except Exception as e:

                logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        except Exception as e:

            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Drop-down grupe
        self.ui_cable_laying_menu = CableLayingUI(self)
        self.ui_routing = RoutingUI(self)
        self.ui_cable_laying = ElementPlacementUI(self)
        self.ui_ducting = DuctingUI(self)
        self.ui_selection = SelectionUI(self)
        self.ui_slack = SlackUI(self)

        # Quick shortcut: 'R' opens interactive terminal slack
        try:
            self.action_slack_quick = QAction("Terminal slack (shortcut)", self.iface.mainWindow())
            self.action_slack_quick.setShortcut(QKeySequence('R'))
            self.action_slack_quick.setVisible(False)  # 'skrivena' akcija
            self.action_slack_quick.triggered.connect(lambda: self._start_slack_interactive("Terminal"))
            self.iface.mainWindow().addAction(self.action_slack_quick)
            self.actions.append(self.action_slack_quick)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        self.ui_drawings = DrawingsUI(self)
        self.ui_objects = ObjectsUI(self)
        # — NEW — Optical schematic view
        self.action_schematic = QAction(_load_icon('ic_optical_schematic_view.svg'), "Optical schematic view", self.iface.mainWindow())
        self.action_schematic.triggered.connect(self.open_optical_schematic)
        self.toolbar.addAction(self.action_schematic)

        # Dodatna dugmad koja ostaju van grupa (ako treba)
        # Import points remains as standalone button, per original behavior
        icon_import_points = _load_icon('ic_import_points.svg')
        self.action_import_points = QAction(icon_import_points, "Import points", self.iface.mainWindow())
        self.action_import_points.triggered.connect(self.import_points)
        self.toolbar.addAction(self.action_import_points)
        self.actions.append(self.action_import_points)

        # Export – active layer to GPX / KML/KMZ / GeoPackage
        try:
            from qgis.PyQt.QtWidgets import QToolButton, QMenu

            export_icon = _load_icon('ic_export_features.svg')

            self.menu_export = QMenu("Export", self.iface.mainWindow())
            self.menu_export.setToolTipsVisible(True)

            self.action_export_selected = QAction(
                export_icon,
                "Export selected...",
                self.iface.mainWindow()
            )
            self.action_export_selected.setToolTip(
                "Export selected features of the active layer to GPX / KML / KMZ / GeoPackage"
            )
            self.action_export_selected.triggered.connect(
                self.export_selected_features
            )
            self.menu_export.addAction(self.action_export_selected)
            self.actions.append(self.action_export_selected)

            self.action_export_all = QAction(
                export_icon,
                "Export all...",
                self.iface.mainWindow()
            )
            self.action_export_all.setToolTip(
                "Export all features of the active layer to GPX / KML / KMZ / GeoPackage"
            )
            self.action_export_all.triggered.connect(
                self.export_all_features
            )
            self.menu_export.addAction(self.action_export_all)
            self.actions.append(self.action_export_all)

            self.btn_export = QToolButton(self.toolbar)
            self.btn_export.setMenu(self.menu_export)
            self.btn_export.setDefaultAction(self.action_export_selected)
            self.btn_export.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            self.btn_export.setToolTip("Export active layer")
            self.toolbar.addWidget(self.btn_export)
        except Exception as e:
            # Failing to build export UI should not break plugin loading
            logger.debug(f"Could not build export UI: {e}")

        # Lokator
        icon_locator = _load_icon('ic_locator.svg')
        self.action_locator = QAction(icon_locator, "Locator", self.iface.mainWindow())
        self.action_locator.triggered.connect(self.open_locator_dialog)
        self.toolbar.addAction(self.action_locator)
        self.actions.append(self.action_locator)

        self.action_clear_locator = QAction(_load_icon('ic_hide_locator.svg'), "Hide locator", self.iface.mainWindow())
        self.action_clear_locator.triggered.connect(self.clear_locator_marker)
        self.toolbar.addAction(self.action_clear_locator)
        self.actions.append(self.action_clear_locator)

        # Relacije
        icon_rel = _load_icon('ic_relations.svg')
        self.action_relations = QAction(icon_rel, "Relations", self.iface.mainWindow())
        self.action_relations.triggered.connect(self.open_relations_dialog)
        self.toolbar.addAction(self.action_relations)
        self.actions.append(self.action_relations)
        # Lista latentnih elemenata
        self.action_latent_list = QAction(_load_icon('ic_list_of_latent_elements.svg'), "List of latent elements", self.iface.mainWindow())
        self.action_latent_list.triggered.connect(self.open_latent_elements_dialog)
        self.toolbar.addAction(self.action_latent_list)
        self.actions.append(self.action_latent_list)
        # Fiber break (new tool)
        icon_prekid = _load_icon('ic_fiber_break.svg')  # can later replace with QIcon(':/path/to/icon.svg')

        # Cut infrastructure (new tool)
        try:
            icon_sec = _load_icon('ic_infrastructure_cut.svg')
        except Exception:
            try:
                from qgis.PyQt.QtGui import QIcon as _QIconTmp
                icon_sec = _QIconTmp()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
                icon_sec = None
        try:
            self.action_infra_cut = QAction(icon_sec, "Cut infrastructure", self.iface.mainWindow())
        except Exception:
            self.action_infra_cut = QAction("Cut infrastructure")
        try:
            self.action_infra_cut.setObjectName("action_infrastructure_cut")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.action_infra_cut.setShortcut(QKeySequence('Ctrl+Shift+X'))
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.action_infra_cut.triggered.connect(self.activate_infrastructure_cut_tool)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        # robustly add to toolbar and menu
        _added_ok = False
        try:
            self.toolbar.addAction(self.action_infra_cut)
            _added_ok = True
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        if not _added_ok:
            try:
                self.iface.addToolBarIcon(self.action_infra_cut)
                _added_ok = True
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.iface.addPluginToMenu('FiberQ', self.action_infra_cut)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.actions.append(self.action_infra_cut)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        self.action_fiber_break = QAction(icon_prekid, "Fiber break", self.iface.mainWindow())
        try:
            self.action_fiber_break.setShortcut(QKeySequence('Ctrl+F'))
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        self.action_fiber_break.triggered.connect(self.activate_fiber_break_tool)
        self.toolbar.addAction(self.action_fiber_break)
        self.actions.append(self.action_fiber_break)

        # Color catalog (menu for fiber/tube color standards)
        self.action_color_catalog = QAction(_load_icon('ic_color_catalog.svg'), "Color catalog", self.iface.mainWindow())
        self.action_color_catalog.triggered.connect(self.open_color_catalog_manager)
        self.toolbar.addAction(self.action_color_catalog)
        self.actions.append(self.action_color_catalog)

        # === Auto-added button: Save all layers to GeoPackage ===
        try:
            icon_save_gpkg = _load_icon('ic_save_gpkg.svg')
        except Exception:
            from qgis.PyQt.QtGui import QIcon as _QIconTmp
            icon_save_gpkg = _QIconTmp()
        self.action_save_gpkg = QAction(icon_save_gpkg, "Save all layers to GeoPackage", self.iface.mainWindow())
        self.action_save_gpkg.setToolTip("Export all vector layers (including Temporary scratch) to a single .gpkg and redirect the project to it")
        self.action_save_gpkg.triggered.connect(self.save_all_layers_to_gpkg)
        # Add to toolbar and list for clean removal
        try:
            self.toolbar.addAction(self.action_save_gpkg)
        except Exception:
            # Ako plugin nema svoju toolbar promenljivu
            self.iface.addToolBarIcon(self.action_save_gpkg)
        try:
            self.actions.append(self.action_save_gpkg)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # === Auto-save to GeoPackage (toggle) ===
        try:
            icon_auto_gpkg = _load_icon('ic_auto_gpkg.svg')
        except Exception as e:
            logger.debug(f"Could not load auto_gpkg icon: {e}")
            from qgis.PyQt.QtGui import QIcon as _QIconTmp
            icon_auto_gpkg = _QIconTmp()
        self.action_auto_gpkg = QAction(icon_auto_gpkg, "Auto save to GeoPackage", self.iface.mainWindow())
        self.action_auto_gpkg.setCheckable(True)
        self.action_auto_gpkg.setToolTip("When enabled: every new or memory layer is automatically written to the selected .gpkg and redirected to it")
        self.action_auto_gpkg.toggled.connect(self.ui_routing._toggle_auto_gpkg)
        try:
            self.toolbar.addAction(self.action_auto_gpkg)
        except Exception as e:
            logger.debug(f"Could not add to toolbar, using iface: {e}")
            self.iface.addToolBarIcon(self.action_auto_gpkg)
        try:
            self.actions.append(self.action_auto_gpkg)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # === Dugme: Otvori FiberQ web ===
        try:
            icon_fiberq = _load_icon('ic_fiberq_web.svg')
        except Exception as e:
            logger.debug(f"Could not load fiberq_web icon: {e}")
            icon_fiberq = QIcon()
        self.action_open_fiberq_web = QAction(icon_fiberq, "Preview Map", self.iface.mainWindow())
        self.action_open_fiberq_web.setToolTip("Open the FiberQ Preview Map (PostGIS connection from config.ini)")
        self.action_open_fiberq_web.triggered.connect(self.open_fiberq_web)
        try:
            self.toolbar.addAction(self.action_open_fiberq_web)
        except Exception:
            self.iface.addToolBarIcon(self.action_open_fiberq_web)
        try:
            self.actions.append(self.action_open_fiberq_web)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Service Area tools
        try:
            icon_sa = _load_icon('ic_service_area.svg') if 'ic_service_area.svg' else QIcon()
            self.action_create_region = QAction(icon_sa, 'Create Service Area', self.iface.mainWindow())
            self.action_create_region.setToolTip('Create Service Area from selection (buffer around selected cables/elements)')
            self.action_create_region.triggered.connect(self.run_create_service_area)
            try:
                self.toolbar.addAction(self.action_create_region)
            except Exception:
                self.iface.addToolBarIcon(self.action_create_region)
            try:
                self.actions.append(self.action_create_region)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        try:
            icon_draw = _load_icon('ic_draw_service_area.svg') if 'ic_draw_service_area.svg' else QIcon()
            self.action_draw_region = QAction(icon_draw, 'Draw Service Area Manually', self.iface.mainWindow())
            self.action_draw_region.setToolTip('Manual Service Area drawing (like Google Earth) and entry into Service Area layer')
            self.action_draw_region.triggered.connect(self.activate_draw_service_area_manual)
            try:
                self.toolbar.addAction(self.action_draw_region)
            except Exception as e:
                logger.debug(f"Could not add to toolbar, using iface: {e}")
                self.iface.addToolBarIcon(self.action_draw_region)
            try:
                self.actions.append(self.action_draw_region)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Razgrani cables (offset)
        try:
            icon_branch = _load_icon('ic_branch.svg')
        except Exception as e:
            logger.debug(f"Could not load branch icon: {e}")
            icon_branch = QIcon()
        try:
            self.action_branch = QAction(icon_branch, "Branch info", self.iface.mainWindow())
        except Exception as e:
            logger.debug(f"Could not create action with parent: {e}")
            self.action_branch = QAction("Branch info")
        try:
            self.action_branch.setShortcut("Ctrl+G")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        self.action_branch.setToolTip("Click on cable to show number of cables/types/capacities at that point")
        try:
            self.action_branch.triggered.connect(self.activate_branch_info_tool)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.toolbar.addAction(self.action_branch)
        except Exception as e:
            logger.debug(f"Could not add to toolbar, using iface: {e}")
            self.iface.addToolBarIcon(self.action_branch)
        try:
            self.actions.append(self.action_branch)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Show shortcuts (overlay)
        try:
            self.action_hotkeys = QAction("Show shortcuts", self.iface.mainWindow())
        except Exception as e:
            logger.debug(f"Could not create action with parent: {e}")
            self.action_hotkeys = QAction("Show shortcuts")
        try:
            self.action_hotkeys.setIcon(_load_icon('ic_hotkeys.svg'))
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.action_hotkeys.setShortcut("F1")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.action_hotkeys.triggered.connect(self.toggle_hotkeys_overlay)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.toolbar.addAction(self.action_hotkeys)
        except Exception:
            try:
                self.iface.addToolBarIcon(self.action_hotkeys)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.actions.append(self.action_hotkeys)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # === BOM report (XLSX/CSV) ===
        try:
            self.action_bom = QAction("BOM izveštaj (XLSX/CSV)", self.iface.mainWindow())
            try:
                self.action_bom.setIcon(_load_icon('ic_bom.svg'))
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception:
            # fallback if QAction construction with parent fails
            self.action_bom = QAction("BOM izveštaj (XLSX/CSV)")

        try:
            self.action_bom.setShortcut("Ctrl+B")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        self.action_bom.setToolTip("BOM report")
        try:
            self.action_bom.triggered.connect(self.open_bom_dialog)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            self.toolbar.addAction(self.action_bom)
        except Exception:
            self.iface.addToolBarIcon(self.action_bom)
        try:
            self.actions.append(self.action_bom)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Fallback: global shortcuts
        try:
            self._ensure_global_shortcuts()
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Re-apply cable style/aliases when layer added to project (npr. export iz Preview Map)
        try:
            QgsProject.instance().layersAdded.disconnect(self._on_layers_added)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        try:
            QgsProject.instance().layersAdded.connect(self._on_layers_added)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # --- Hotkeys (addons/hotkeys.py) ---
        try:
            from .addons.hotkeys import register_hotkeys
            if not hasattr(self, '_hk_shortcuts'):
                self._hk_shortcuts = []
            register_hotkeys(self)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # --- Health check action ---
        try:
            self.action_health_check = QAction('Check (health check)', self.iface.mainWindow())
            try:
                self.action_health_check.setIcon(_load_icon('ic_health.svg'))
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
            self.action_health_check.triggered.connect(self.run_health_check)
            try:
                self.actions.append(self.action_health_check)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
            try:
                self.toolbar.addAction(self.action_health_check)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
            try:
                self.iface.addPluginToMenu('FiberQ', self.action_health_check)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # --- Reserve hook ---
        try:
            from .addons.reserve_hook import ReserveHook
            self._reserve_hook = ReserveHook(self.iface)
            self._reserve_hook.ensure_connected()
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # --- FiberQ Settings button (toolbar + menu) ---
        try:
            import os
            from qgis.PyQt.QtGui import QIcon
            if not hasattr(self, 'action_settings'):
                icon_path_settings = os.path.join(os.path.dirname(__file__), 'icons', 'ic_settings.svg')
                icon_settings = QIcon(icon_path_settings) if os.path.exists(icon_path_settings) else QIcon()
                self.action_settings = QAction(icon_settings, 'Settings', self.iface.mainWindow())
                self.action_settings.triggered.connect(self.open_fiberq_settings)
                try:
                    if self.toolbar is not None:
                        self.toolbar.addAction(self.action_settings)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.initGui: {e}")
                try:
                    self.iface.addPluginToMenu('FiberQ', self.action_settings)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.initGui: {e}")
                try:
                    self.actions.append(self.action_settings)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # --- Change element type (toolbar) ---
        try:
            if not hasattr(self, 'action_change_element_type'):
                icon = _load_icon('ic_selection.svg')
                self.action_change_element_type = QAction(icon, 'Change element type', self.iface.mainWindow())
                self.action_change_element_type.setToolTip('Smart selection + change element type (visual style)')
                self.action_change_element_type.triggered.connect(self.activate_change_element_type_tool)
                try:
                    self.toolbar.addAction(self.action_change_element_type)
                except Exception:
                    try:
                        self.iface.addToolBarIcon(self.action_change_element_type)
                    except Exception as e:
                        logger.debug(f"Error in FiberQPlugin.initGui: {e}")
                try:
                    self.actions.append(self.action_change_element_type)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # --- Move elements + link images to elements ---
        try:
            # Move elements
            self.action_move_elements = QAction(_load_icon('ic_move_elements.svg'), 'Move elements', self.iface.mainWindow())
            self.action_move_elements.setToolTip('Move elements on the map (click-move-click)')
            self.action_move_elements.triggered.connect(self.ui_move_elements)

            # Import picture
            self.action_import_image = QAction(_load_icon('ic_import_picture.svg'), 'Import picture to element', self.iface.mainWindow())
            self.action_import_image.setToolTip('Link a .jpg/.png picture to selected element(s)')
            self.action_import_image.triggered.connect(self.ui_import_image)

            # Clear picture
            self.action_clear_image = QAction(_load_icon('ic_import_picture.svg'), 'Clear picture from element', self.iface.mainWindow())
            self.action_clear_image.setToolTip('Unlink picture from selected element(s)')
            self.action_clear_image.triggered.connect(self.ui_clear_image)

            # Add actions to toolbar
            try:
                self.toolbar.addAction(self.action_move_elements)
                self.toolbar.addAction(self.action_import_image)
                self.toolbar.addAction(self.action_clear_image)
            except Exception:
                try:
                    self.iface.addToolBarIcon(self.action_move_elements)
                    self.iface.addToolBarIcon(self.action_import_image)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.initGui: {e}")

            # Keep for language toggling (match legacy behavior)
            try:
                self.actions.append(self.action_move_elements)
                self.actions.append(self.action_import_image)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Install image click watcher (once)
        try:
            if not hasattr(self, '_img_click_watcher'):
                self._img_click_watcher = CanvasImageClickWatcher(self)
                try:
                    self.iface.mapCanvas().viewport().installEventFilter(self._img_click_watcher)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.initGui: {e}")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.initGui: {e}")

        # Quick Toolbar (v1.2 — Feature 4)
        try:
            from .ui.quick_toolbar import QuickToolbar
            self.quick_toolbar = QuickToolbar(self)
        except Exception as e:
            logger.debug(f"Error creating Quick Toolbar: {e}")
            self.quick_toolbar = None

        # WP1b: run the versioned schema-migration runner on project load.
        # Deferred (~1s) so all layersAdded handlers (alias / name
        # canonicalisation) finish first. The slot is stored on self so unload()
        # can disconnect the *same* callable -- the previous code connected an
        # inline lambda but disconnected a bound method, so it never disconnected.
        # The one-shot at init covers a project already open when the plugin loads.
        try:
            from qgis.PyQt.QtCore import QTimer
            # Idempotent re-init: drop any slot from a previous initGui that ran
            # without a clean unload, so we never accumulate connections.
            prev_slot = getattr(self, "_schema_migration_slot", None)
            if prev_slot is not None:
                try:
                    QgsProject.instance().readProject.disconnect(prev_slot)
                except Exception as e:
                    logger.debug(f"Could not disconnect previous schema migration slot: {e}")
            self._schema_migration_slot = (
                lambda *args: QTimer.singleShot(1000, self._run_schema_migrations)
            )
            QgsProject.instance().readProject.connect(self._schema_migration_slot)
            QTimer.singleShot(2000, self._run_schema_migrations)
        except Exception as e:
            logger.debug(f"Error scheduling schema migration: {e}")

    def _color_catalogs_key(self):
        """Get color catalogs storage key."""
        # Phase 3.7: Delegate to ColorManager
        if self.color_manager:
            return self.color_manager.color_catalogs_key()
        return "ColorCatalogs/catalogs_v1"

    def _default_color_sets(self):
        """Get default color sets."""
        # Phase 3.7: Delegate to ColorManager
        if self.color_manager:
            try:
                return self.color_manager.get_default_color_sets()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._default_color_sets: {e}")
        return []

    def _load_color_catalogs(self):
        """Load color catalogs."""
        if self.color_manager:
            try:
                return self.color_manager.load_color_catalogs()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._load_color_catalogs: {e}")
        return {"catalogs": []}

    def _save_color_catalogs(self, data):
        """Save color catalogs."""
        if self.color_manager:
            try:
                self.color_manager.save_color_catalogs(data)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._save_color_catalogs: {e}")

    def _list_color_codes(self):
        """List color codes."""
        if self.color_manager:
            try:
                return self.color_manager.list_color_codes()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._list_color_codes: {e}")
        return []

    def open_color_catalog_manager(self):
        """Open the color catalog manager dialog."""
        if self.color_manager:
            try:
                self.color_manager.open_color_catalog_manager(self)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.open_color_catalog_manager: {e}")

    def activate_breakpoint_tool(self):
        """Aktivira alat za dodavanje tačke na lom trase (BreakpointTool)."""
        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            self.init_layer()
        self.breakpoint_tool = BreakpointTool(self.iface.mapCanvas(), self.iface, self)
        self.iface.mapCanvas().setMapTool(self.breakpoint_tool)
        self._record_cmd('split_route')

    def activate_manual_route_tool(self):
        self.manual_route_tool = ManualRouteTool(self.iface, self)
        self.iface.mapCanvas().setMapTool(self.manual_route_tool)
        self._record_cmd('manual_route')

    def activate_extension_tool(self):
        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            self.init_layer()
        self.extension_tool = ExtensionTool(self.iface.mapCanvas(), self.layer)
        self.extension_tool.plugin = self  # v1.2: for undo_manager access
        self.iface.mapCanvas().setMapTool(self.extension_tool)
        self._record_cmd('place_joint_closure')

    def activate_place_element_tool(self, layer_name, symbol_spec=None):
        try:
            self._place_element_tool = PlaceElementTool(self.iface.mapCanvas(), layer_name, symbol_spec)
            self._place_element_tool.plugin = self  # v1.2: for undo_manager access
            self.iface.mapCanvas().setMapTool(self._place_element_tool)
            self._record_cmd('place_element', layer_name=layer_name, symbol_spec=symbol_spec)
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Placing elements", f"Error: {e}")

    def activate_fiber_break_tool(self):
        """Activate the fiber-break map tool. Falls back to simple point placement if import fails."""
        try:
            # Prefer the dedicated FiberBreakTool from addons
            from .addons.fiber_break import FiberBreakTool
            self._fiber_break_tool = FiberBreakTool(self.iface)
            self.iface.mapCanvas().setMapTool(self._fiber_break_tool)
        except Exception:
            try:
                # fallback keeps previous behavior (compatibility)
                symbol_spec = {
                    'name': 'circle',
                    'color': 'black',
                    'size': '4',
                    'size_unit': 'MM',   # bitno: ekran, ne map units
                }
                self._place_element_tool = PlaceElementTool(self.iface.mapCanvas(), "Fiber break", symbol_spec)
                self._place_element_tool.plugin = self  # v1.2: for undo_manager access
                self.iface.mapCanvas().setMapTool(self._place_element_tool)
            except Exception as e:
                QMessageBox.critical(self.iface.mainWindow(), "Fiber break", f"Error activating: {e}")
                return

        # After activating tool, find all break layers and apply fixed style
        try:
            from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes

            for lyr in QgsProject.instance().mapLayers().values():
                if not isinstance(lyr, QgsVectorLayer):
                    continue
                if lyr.geometryType() != QgsWkbTypes.GeometryType.PointGeometry:
                    continue

                name = (lyr.name() or "").lower()
                # cover both English and Serbian names
                if "fiber break" in name or "prekid" in name:
                    self._apply_prekid_style(lyr)

                    # Field aliases (EN) - user view, field names ostaju isti radi kompatibilnosti koda
                    try:
                        fields = lyr.fields()
                        alias_map = {
                            "naziv": "Name",
                            "cable_layer_id": "Cable layer ID",
                            "cable_fid": "Cable feature ID",
                            "distance_m": "Distance (m)",
                            "segments_hit": "Segments hit",
                            "vreme": "Time",
                        }

                        for fn, al in alias_map.items():
                            idx = fields.indexOf(fn)
                            if idx != -1:
                                lyr.setFieldAlias(idx, al)

                        try:
                            lyr.updateFields()
                        except Exception as e:
                            logger.debug(f"Error in FiberQPlugin.activate_fiber_break_tool: {e}")
                        try:
                            lyr.triggerRepaint()
                        except Exception as e:
                            logger.debug(f"Error in FiberQPlugin.activate_fiber_break_tool: {e}")
                    except Exception as e:
                        logger.debug(f"Error in FiberQPlugin.activate_fiber_break_tool: {e}")

        except Exception as e:
            # if something fails, do not crash tool - just skip style
            logger.debug(f"Could not apply fiber break style: {e}")

        self._record_cmd('fiber_break')

    def activate_smart_select_tool(self):
        """Uključi pametnu višeslojnu selekciju (bez promene aktivnog sloja)."""
        try:
            self._smart_select_tool = SmartMultiSelectTool(self.iface, self)
            self.iface.mapCanvas().setMapTool(self._smart_select_tool)
            # create selection memory if doesn't exist
            if not hasattr(self, 'smart_selection'):
                self.smart_selection = []
            # informacija korisniku
            try:
                self.iface.messageBar().pushInfo("Smart selection", "Click on the elements to select/deselect them. Selections on other layers are not touched.")
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.activate_smart_select_tool: {e}")
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Smart selection", f"Error: {e}")

    def activate_branch_info_tool(self):
        """Aktiviraj alat: klik na cable → info o grananju u message baru."""
        try:
            self._branch_info_tool = BranchInfoTool(self)
            self.iface.mapCanvas().setMapTool(self._branch_info_tool)
            try:
                self.iface.messageBar().pushInfo(
                    "Branch info",
                    "Click on cable to show number of cables/types/capacities at that point "
                    "(right click or ESC to exit)."
                )
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.activate_branch_info_tool: {e}")
        except Exception as e:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(self.iface.mainWindow(), "Branch info", f"Error: {e}")

    def clear_all_selections(self):
        """Skloni selekciju sa svih slojeva (ne briše objekte)."""
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer):
                    lyr.removeSelection()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.clear_all_selections: {e}")
        # clear internal list too
        try:
            self.smart_selection = []
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.clear_all_selections: {e}")

    def open_optical_schematic(self):
        try:
            # keep reference so dialog is not collected by GC
            if not hasattr(self, "_schematic_dlg") or self._schematic_dlg is None:
                self._schematic_dlg = OpticalSchematicDialog(self)
            self._schematic_dlg.show()
            self._schematic_dlg.raise_()
            self._schematic_dlg.activateWindow()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Optical schematic", f"Error: {e}")

# === RELACIJE ===
    def open_relations_dialog(self):
        try:
            dlg = RelationsDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Relations", f"Error opening dialog: {e}")

    def _relations_storage_key(self):
        """Get relations storage key."""
        # Phase 3.4: Delegate to RelationsManager
        if self.relations_manager:
            return self.relations_manager.relations_storage_key()
        return "Relacije/relations_v1"

    def _load_relations(self):
        """Load relations."""
        if self.relations_manager:
            try:
                return self.relations_manager.load_relations()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._load_relations: {e}")
        return {"relations": []}

    def _save_relations(self, data):
        """Save relations."""
        if self.relations_manager:
            try:
                self.relations_manager.save_relations(data)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._save_relations: {e}")

    def _relation_by_id(self, data, rid):
        """Get relation by ID."""
        if self.relations_manager:
            try:
                return self.relations_manager.get_relation_by_id(data, rid)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._relation_by_id: {e}")
        return None

    def list_all_cables(self):
        """List all cables."""
        if self.cable_manager:
            try:
                return self.cable_manager.list_all_cables()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.list_all_cables: {e}")
        return []

    # === LATENT ELEMENTS (pass-through points) ===

    def _latent_storage_key(self):
        """Get latent storage key."""
        # Phase 3.4: Delegate to RelationsManager
        if self.relations_manager:
            return self.relations_manager.latent_storage_key()
        return "LatentElements/latent_v1"

    def _load_latent(self):
        """Load latent elements."""
        if self.relations_manager:
            try:
                return self.relations_manager.load_latent()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._load_latent: {e}")
        return {"cables": {}}

    def _save_latent(self, data):
        """Save latent elements."""
        if self.relations_manager:
            try:
                self.relations_manager.save_latent(data)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._save_latent: {e}")

    def _cable_key(self, layer_id, fid):
        """Generate cable key."""
        if self.relations_manager:
            try:
                return self.relations_manager.cable_key(layer_id, fid)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._cable_key: {e}")
        return f"{layer_id}:{int(fid)}"

    def _relation_name_by_cable(self):
        """Get relation name by cable."""
        if self.relations_manager:
            try:
                return self.relations_manager.get_relation_name_by_cable()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._relation_name_by_cable: {e}")
        return {}

    def list_all_pipes(self):
        """List all pipes."""
        if self.pipe_manager:
            try:
                return self.pipe_manager.list_all_pipes()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.list_all_pipes: {e}")
        return []

    def _find_candidate_elements_for_cable(self, cable_layer, cable_feature, tol=5.0):
        """Find candidate elements for cable."""
        if self.relations_manager:
            try:
                return self.relations_manager.find_candidate_elements_for_cable(cable_layer, cable_feature, tol)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._find_candidate_elements_for_cable: {e}")
        return []

    def open_latent_elements_dialog(self):
        try:
            dlg = LatentElementsDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "List of latent elements", f"Error: {e}")

    # =========================================================================
    # PHASE 0.1: UUID MIGRATION FOR FIBERQ DESIGNER
    # =========================================================================

    def _migrate_uuids(self):
        """
        Run UUID migration on all FiberQ layers in the current project.

        Called once after plugin loads (via QTimer) and on every project open.
        Adds fiberq_uuid field to layers that don't have it and backfills
        UUIDs for existing features.
        """
        try:
            from .utils.uuid_utils import migrate_project_uuids
            results = migrate_project_uuids()
            if results:
                total = sum(results.values())
                layers_str = ", ".join(f"{name} ({count})" for name, count in results.items())
                self.iface.messageBar().pushInfo(
                    "FiberQ",
                    f"UUID migration: assigned {total} UUIDs across {len(results)} layers ({layers_str})"
                )
                logger.debug(f"UUID migration results: {results}")
        except Exception as e:
            logger.debug(f"Error in UUID migration: {e}")

    def _run_schema_migrations(self):
        """Run the versioned schema-migration runner (WP1b) on the current project.

        Two responsibilities on every project load:
        1. The version-gated migration runner: reads the stored schema marker,
           upgrades an older project to the current version, and stamps the
           marker (only on success -- a failed step is retried on the next load).
        2. The fiberq_uuid identity invariant: an idempotent backfill that runs
           regardless of the marker, because imports / external edits can add
           NULL-uuid features to an already-migrated project. This keeps the old
           always-on healing behaviour that the version gate would otherwise drop.
        """
        prj = QgsProject.instance()
        steps_done = []
        try:
            from .core.migrations import run_migrations
            report = run_migrations(prj)
            steps_done = report.steps
            if report.ran:
                self.iface.messageBar().pushInfo("FiberQ", report.summary())
                logger.debug(f"Schema migration: {report}")
            elif report.errors:
                logger.debug(f"Schema migration not applied: {report.summary()}")
        except Exception as e:
            logger.debug(f"Error running schema migrations: {e}")

        # Standing identity invariant -- heal any features still lacking a UUID.
        # Skipped when the migration above already ran the uuid step this load.
        try:
            from .utils.uuid_utils import migrate_project_uuids
            if "uuid-identity" not in steps_done:
                healed = migrate_project_uuids(prj)
                if healed:
                    total = sum(healed.values())
                    logger.debug(f"UUID invariant backfilled {total} features: {healed}")
        except Exception as e:
            logger.debug(f"Error in UUID invariant backfill: {e}")

    def unload(self):
        # WP1b: disconnect the schema-migration slot -- the same callable we
        # connected, so the disconnect actually succeeds.
        try:
            slot = getattr(self, "_schema_migration_slot", None)
            if slot is not None:
                QgsProject.instance().readProject.disconnect(slot)
        except Exception as e:
            logger.debug(f"Could not disconnect schema migration slot: {e}")

        # Clear undo stacks (v1.2 — Feature 2)
        try:
            if hasattr(self, 'undo_manager') and self.undo_manager:
                self.undo_manager.clear()
        except Exception as e:
            logger.debug(f"Error clearing undo stacks: {e}")

        # Cleanup Command Manager (v1.2 — Feature 3)
        try:
            if hasattr(self, 'command_manager') and self.command_manager:
                self.command_manager.unload()
        except Exception as e:
            logger.debug(f"Error unloading command manager: {e}")

        # Cleanup Quick Toolbar (v1.2 — Feature 4)
        try:
            if hasattr(self, 'quick_toolbar') and self.quick_toolbar:
                self.quick_toolbar.unload()
        except Exception as e:
            logger.debug(f"Error unloading quick toolbar: {e}")

        # Cleanup hotkeys
        try:
            for sc in getattr(self, '_hk_shortcuts', []):
                try:
                    sc.activated.disconnect()
                    sc.setParent(None)
                    sc.deleteLater()
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.unload: {e}")
            self._hk_shortcuts = []
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.unload: {e}")

        # Auto cleanup for auto gpkg toggle
        try:
            self.iface.removeToolBarIcon(self.action_auto_gpkg)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.unload: {e}")
        try:
            self.action_auto_gpkg.setChecked(False)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.unload: {e}")
        # Disconnect project signal for auto GPKG if connected
        try:
            QgsProject.instance().layerWasAdded.disconnect(self.ui_routing._on_layer_added_auto_gpkg)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.unload: {e}")

        try:
            QgsProject.instance().layersAdded.disconnect(self._on_layers_added)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.unload: {e}")

        # Auto-cleanup for save_gpkg action (safety)
        try:
            self.iface.removeToolBarIcon(self.action_save_gpkg)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.unload: {e}")
        for action in self.actions:
            self.iface.removePluginMenu('FiberQ', action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar
        self.layer = None
        # Schematic view – clear
        try:
            if hasattr(self, 'action_schematic') and self.action_schematic:
                self.iface.removeToolBarIcon(self.action_schematic)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.unload: {e}")
        try:
            if hasattr(self, '_schematic_dlg') and self._schematic_dlg:
                self._schematic_dlg.close()
                self._schematic_dlg = None
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.unload: {e}")

    def _set_poles_alias(self):
        """Prikaži sloj 'Poles' kao 'Poles' u Layers panelu."""
        try:
            root = QgsProject.instance().layerTreeRoot()
            node = root.findLayer(self.layer.id())
            if node:
                node.setCustomLayerName("Poles")
        except Exception as e:
            # If something fails (e.g. layerTreeRoot not ready), just skip
            logger.debug(f"Could not set poles layer alias: {e}")

    def _apply_poles_field_aliases(self, layer):
        """Apply English field aliases to the poles layer.

        Delegates to utils.field_aliases module.
        """
        from .utils.field_aliases import apply_poles_field_aliases
        apply_poles_field_aliases(layer)

    def _set_route_layer_alias(self, layer):
        """Set the route layer display name to 'Route'.

        Delegates to utils.field_aliases module.
        """
        from .utils.field_aliases import set_route_layer_alias
        set_route_layer_alias(layer)

    def _apply_route_field_aliases(self, layer):
        """Apply English field aliases and value map to a route layer.

        Delegates to utils.field_aliases module.
        """
        from .utils.field_aliases import apply_route_field_aliases
        apply_route_field_aliases(layer)

    def _set_okna_layer_alias(self, layer: QgsVectorLayer) -> None:
        """Set the manhole layer display name to 'Manholes'.

        Delegates to utils.field_aliases module.
        """
        from .utils.field_aliases import set_manhole_layer_alias
        set_manhole_layer_alias(layer)

    def _apply_manhole_field_aliases(self, layer: QgsVectorLayer) -> None:
        """Apply English field aliases to a manhole layer.

        Delegates to utils.field_aliases module.
        """
        from .utils.field_aliases import apply_manhole_field_aliases
        apply_manhole_field_aliases(layer)

    def _apply_cable_field_aliases(self, layer):
        """Apply English field aliases to a cable layer.

        Delegates to utils.field_aliases module.
        """
        from .utils.field_aliases import apply_cable_field_aliases
        apply_cable_field_aliases(layer, migrate_values=True)

    def _set_cable_layer_alias(self, layer):
        """Set English layer names for cable layers.

        Converts:
        - 'Kablovi_podzemni' -> 'Underground cables'
        - 'Kablovi_vazdusni' -> 'Aerial cables'
        """
        if layer is None:
            return
        try:
            name = layer.name() or ""
            if name in ("Kablovi_podzemni", "Underground cables"):
                layer.setName("Underground cables")
            elif name in ("Kablovi_vazdusni", "Aerial cables"):
                layer.setName("Aerial cables")
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin._set_cable_layer_alias: {e}")

    def _on_layers_added(self, layers):
        from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes

        def _set_custom_name(vlayer, new_name: str):
            try:
                root = QgsProject.instance().layerTreeRoot()
                node = root.findLayer(vlayer.id())
                if node and new_name:
                    node.setCustomLayerName(new_name)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._set_custom_name: {e}")

        cable_names = {"Aerial cables", "Underground cables", "Kablovi_vazdusni", "Kablovi_podzemni"}

        for layer in layers:
            if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
                continue

            lname = (layer.name() or "")
            lname_l = lname.lower().strip()
            gtype = layer.geometryType()
            fset = {f.name() for f in layer.fields()}

            # 1) CABLES (Line)
            if gtype == QgsWkbTypes.GeometryType.LineGeometry and lname in cable_names:
                self._stylize_cable_layer(layer)      # EN legend labels
                self._apply_cable_field_aliases(layer)   # EN user view
                self._set_cable_layer_alias(layer)       # EN layer name
                layer.triggerRepaint()
                continue

            # 2) FIBER BREAK (Point)
            if gtype == QgsWkbTypes.GeometryType.PointGeometry and {
                "cable_layer_id", "cable_fid", "distance_m", "segments_hit", "vreme"
            }.issubset(fset):
                alias_map = {
                    "naziv": "Name",
                    "cable_layer_id": "Cable layer ID",
                    "cable_fid": "Cable feature ID",
                    "distance_m": "Distance (m)",
                    "segments_hit": "Segments hit",
                    "vreme": "Time",
                }
                fields = layer.fields()
                for fn, al in alias_map.items():
                    idx = fields.indexFromName(fn)
                    if idx != -1:
                        layer.setFieldAlias(idx, al)
                _set_custom_name(layer, "Fiber break")
                layer.triggerRepaint()
                continue

            # 3) JOINT CLOSURES (Point) - filtered to not catch ODF/TB/OTB/TO...
            # Dozvoli:
            # - by layer name (Joint Closures) even with suffixes
            # - or if layer actually has only id,fid,naziv fields
            if gtype == QgsWkbTypes.GeometryType.PointGeometry and (
                lname_l.startswith("joint closures")
                or lname_l.startswith("nastav")  # noqa: W503
                or fset.issubset({"id", "fid", "naziv"})  # noqa: W503
            ):
                alias_map = {
                    "id": "ID",
                    "fid": "Cable feature ID",
                    "naziv": "Name",
                }
                fields = layer.fields()
                for fn, al in alias_map.items():
                    idx = fields.indexFromName(fn)
                    if idx != -1:
                        layer.setFieldAlias(idx, al)
                _set_custom_name(layer, "Joint Closures")
                layer.triggerRepaint()
                continue

            # 3.5) ROUTE (Line) – EN field aliases + EN layer name (posle export/import iz Preview Map)
            if gtype == QgsWkbTypes.GeometryType.LineGeometry and (
                lname_l.startswith("route")
                or lname_l.startswith("trasa")  # noqa: W503
                or {"naziv", "duzina", "tip_trase"}.issubset(fset)  # noqa: W503
            ):
                try:
                    self._apply_route_field_aliases(layer)   # EN user view (aliases + valuemap)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin._set_custom_name: {e}")
                _set_custom_name(layer, "Route")
                layer.triggerRepaint()
                continue

            # 3.6) POLES (Point) – EN field aliases + EN layer name
            if gtype == QgsWkbTypes.GeometryType.PointGeometry and (
                lname_l.startswith("poles")
                or lname_l.startswith("stubov")  # noqa: W503
                or {"tip", "podtip", "visina", "materijal"}.issubset(fset)  # noqa: W503
            ):
                try:
                    self._apply_poles_field_aliases(layer)   # EN user view
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin._set_custom_name: {e}")
                _set_custom_name(layer, "Poles")
                layer.triggerRepaint()
                continue

            # 3.7) MANHOLES / OKNA (Point) – EN field aliases + EN layer name
            if gtype == QgsWkbTypes.GeometryType.PointGeometry and (
                lname_l.startswith("manholes")
                or lname_l.startswith("okna")  # noqa: W503
                or {"broj_okna", "tip_okna"}.issubset(fset)  # noqa: W503
            ):
                try:
                    self._apply_manhole_field_aliases(layer)    # EN user view
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin._set_custom_name: {e}")
                _set_custom_name(layer, "Manholes")
                layer.triggerRepaint()
                continue

            # 4) GENERIC “Placing elements” (ODF/TB/OTB/TO/Patch panel/Optical slacks…)
            if (
                gtype in (QgsWkbTypes.GeometryType.PointGeometry, QgsWkbTypes.GeometryType.PolygonGeometry)
                and (  # noqa: W503
                    "proizvodjac" in fset
                    or "kapacitet" in fset  # noqa: W503
                    or "oznaka" in fset  # noqa: W503
                    or "address_id" in fset  # noqa: W503
                    or "naziv_objekta" in fset  # noqa: W503
                    or "adresa_ulica" in fset  # noqa: W503
                    or "stanje" in fset  # noqa: W503
                )
            ):
                # SR->EN field aliases (user view)
                _apply_element_aliases(layer)

                # (optional) SR -> EN name in Layers panel (works even with suffix)
                if lname_l.startswith("nastav"):
                    _set_custom_name(layer, "Joint Closures")
                elif lname_l.startswith("okna"):
                    _set_custom_name(layer, "Manholes")
                elif lname_l.startswith("stubovi"):
                    _set_custom_name(layer, "Poles")
                else:
                    _set_custom_name(layer, lname)

                layer.triggerRepaint()
                continue

    def init_layer(self):
        """Create or return the Poles layer."""
        if self.layer_manager:
            try:
                self.layer = self.layer_manager.ensure_poles_layer()
                if self.layer:
                    self._apply_poles_field_aliases(self.layer)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.init_layer: {e}")

    def create_route(self):
        """Create a route from selected poles/manholes."""
        if self.route_manager:
            self.route_manager.create_route()
            self._record_cmd('create_route')

    def _record_cmd(self, name, **params):
        """Record a command for repeat-last-command (v1.2 Feature 3)."""
        if hasattr(self, 'command_manager') and self.command_manager:
            self.command_manager.record(name, **params)

    def activate_point_tool(self):
        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            self.init_layer()
        self.point_tool = PointTool(self.iface.mapCanvas(), self.layer)
        self.point_tool.plugin = self  # v1.2: for undo_manager access
        self.iface.mapCanvas().setMapTool(self.point_tool)
        self._record_cmd('place_pole')

    def delete_selected(self):
        from qgis.core import QgsProject, QgsVectorLayer, QgsVectorDataProvider

        obrisano = 0
        # set of cables affected by deleted slack
        affected_cables = set()   # (cable_layer_id, cable_fid)

        for lyr in QgsProject.instance().mapLayers().values():
            # THIS IS A CHECK THAT USES capabilities()
            if isinstance(lyr, QgsVectorLayer) and (
                lyr.isEditable()
                or lyr.dataProvider().capabilities() & QgsVectorDataProvider.Capability.DeleteFeatures  # noqa: W503
            ):
                selected_feats = list(lyr.selectedFeatures())

                # If deleting from Optical_slack layer - remember which cables it affected
                if lyr.name() in ("Opticke_rezerve", "Optical slack"):
                    for f in selected_feats:
                        try:
                            cable_layer_id = f["cable_layer_id"]
                            cable_fid = int(f["cable_fid"])
                            if cable_layer_id:
                                affected_cables.add((cable_layer_id, cable_fid))
                        except Exception as e:
                            logger.debug(f"Error in FiberQPlugin.delete_selected: {e}")

                selected_ids = [f.id() for f in selected_feats]
                if selected_ids:
                    lyr.startEditing()
                    for fid in selected_ids:
                        lyr.deleteFeature(fid)
                        obrisano += 1
                    lyr.commitChanges()
                    lyr.triggerRepaint()
                lyr.removeSelection()

        # AFTER deleting slack – recalculate slack for affected cables
        if affected_cables:
            for cable_layer_id, cable_fid in affected_cables:
                try:
                    self._recompute_slack_for_cable(cable_layer_id, cable_fid)
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.delete_selected: {e}")

        if obrisano == 0:
            QMessageBox.information(self.iface.mainWindow(), "Delete", "No selected features to delete.")
        else:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Delete",
                f"Deleted {obrisano} selected features from all layers."
            )

    def _stylize_cable_layer(self, cables_layer):
        """Apply cable layer style."""
        if self.cable_manager:
            try:
                self.cable_manager.stylize_cable_layer(cables_layer)
                return
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._stylize_cable_layer: {e}")
        if self.style_manager:
            try:
                self.style_manager.stylize_cable_layer(cables_layer)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._stylize_cable_layer: {e}")

    # === Grananje/offset preko branch_index ===

    def _ensure_branch_index_field(self, layer):
        """Ensure layer has branch_index field."""
        if self.cable_manager:
            try:
                self.cable_manager.ensure_branch_index_field(layer)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._ensure_branch_index_field: {e}")

    def _compute_branch_indices_for_layer(self, layer, tol_m=0.3):
        """Compute branch indices for cables with same endpoints."""
        if self.cable_manager:
            try:
                return self.cable_manager.compute_branch_indices_for_layer(layer, tol_m)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._compute_branch_indices_for_layer: {e}")
        return 0, 0

    def _apply_branch_offset_style(self, layer, offset_mm=2.0):
        """Apply data-defined offset based on branch_index."""
        if self.cable_manager:
            try:
                self.cable_manager.apply_branch_offset_style(layer, offset_mm)
                return
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._apply_branch_offset_style: {e}")
        if self.style_manager:
            try:
                self.style_manager.apply_branch_offset_style(layer, offset_mm)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._apply_branch_offset_style: {e}")

    def apply_cable_offset(self):
        """Handler for 'Branch cables (offset)' button."""
        if self.cable_manager:
            try:
                self.cable_manager.branch_cables_offset()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.apply_cable_offset: {e}")

    def toggle_hotkeys_overlay(self):
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        from qgis.PyQt.QtCore import Qt
        try:
            if getattr(self, '_hotkeys_dlg', None) and self._hotkeys_dlg.isVisible():
                self._hotkeys_dlg.hide()
                return
            self._hotkeys_dlg = QDialog(self.iface.mainWindow(), Qt.WindowType.Tool)
            self._hotkeys_dlg.setWindowTitle('Shortcuts')
            self._hotkeys_dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self._hotkeys_dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            lay = QVBoxLayout(self._hotkeys_dlg)
            lbl = QLabel(
                "<b>Shortcuts</b><br>"
                "Keyboard shortcuts are currently disabled in this version.<br>"
                "<br>"
                "Use the toolbar buttons for:<br>"
                "• BOM report<br>"
                "• Branch cables (offset)<br>"
                "• Publish (PostGIS)<br>"
                "• Fiber break<br>"
                "• Optical slack (interactive)"
            )
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(lbl)
            btn = QPushButton("Close")
            btn.clicked.connect(self._hotkeys_dlg.hide)
            lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
            self._hotkeys_dlg.resize(300, 180)
            self._hotkeys_dlg.show()
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.toggle_hotkeys_overlay: {e}")

    def merge_all_routes(self):
        """Merge selected routes into one."""
        if self.route_manager:
            self.route_manager.merge_all_routes()
        # Minimal fallback - needs RouteManager

    def lay_cable_type(self, tip, podtip):
        """Set cable type and subtype, then lay cable."""
        if self.cable_manager:
            try:
                self.cable_manager.lay_cable_type(tip, podtip)
                self._record_cmd('lay_cable', tip=tip, podtip=podtip)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.lay_cable_type: {e}")

    def lay_cable(self):
        """Lay a cable along a route between two selected elements."""
        if self.cable_manager:
            try:
                self.cable_manager.selected_cable_type = getattr(self, 'selected_cable_type', None)
                self.cable_manager.selected_cable_subtype = getattr(self, 'selected_cable_subtype', None)
                self.cable_manager.lay_cable(
                    color_codes_callback=self._list_color_codes,
                    path_callback=lambda tl, p1, p2, tol: self._build_path_across_network(tl, p1, p2, tol) or self._build_path_across_joined_trasa(tl, p1, p2, tol)
                )
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.lay_cable: {e}")

    def import_route_from_file(self):
        """Import routes from external file."""
        if self.route_manager:
            self.route_manager.import_route_from_file()

    def change_route_type(self):
        """Change the type of selected routes."""
        if self.route_manager:
            self.route_manager.change_route_type()

    def import_points(self):
        filename, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Izaberi fajl sa tačkama (KML/KMZ/DWG/Shape/GPX)",
            "",
            "GIS fajlovi (*.kml *.kmz *.shp *.dwg *.gpx);;Svi fajlovi (*)"
        )
        if not filename:
            return

        imported_layer = QgsVectorLayer(filename, "Uvezi_tacke_tmp", "ogr")
        if not imported_layer.isValid():
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Unable to load or invalid file!")
            return

        if imported_layer.geometryType() != QgsWkbTypes.GeometryType.PointGeometry:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "The selected file does not contain points!")
            return
        # Find all existing point layers relevant to plugin:
        # Poles, Manholes + all elements from Placing elements (+ Joint Closures)
        node_layer_names = ['Poles', 'Poles', 'OKNA', 'Manholes']
        try:
            # Joint Closures / Nastavci
            try:
                nm = NASTAVAK_DEF.get("name", "Joint Closures")
                if nm and nm not in node_layer_names:
                    node_layer_names.append(nm)
            except Exception:
                if 'Nastavci' not in node_layer_names:
                    node_layer_names.append('Nastavci')
            # all elements from Placing elements (ELEMENT_DEFS)
            for d in ELEMENT_DEFS:
                nm = d.get("name")
                if nm and nm not in node_layer_names:
                    node_layer_names.append(nm)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.import_points: {e}")

        existing_layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer)
            and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry  # noqa: W503
            and lyr.name() in node_layer_names  # noqa: W503
        ]
        layer_names = [lyr.name() for lyr in existing_layers]

        # Add option for creating new layer
        NEW_LAYER_OPTION_EN = "Create a new layer"
        NEW_LAYER_OPTION_SR = "Kreiraj novi sloj"  # for backward compatibility with old projects
        layer_names.append(NEW_LAYER_OPTION_EN)

        # Dialog for layer selection
        selected_layer_name, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Import points",
            "Select target layer for importing points:",
            layer_names,
            0, False
        )
        if not ok or not selected_layer_name:
            return

        # 1) If new layer option selected (Serbian or English)
        if selected_layer_name in (NEW_LAYER_OPTION_EN, NEW_LAYER_OPTION_SR):
            new_layer_name, ok2 = QInputDialog.getText(
                self.iface.mainWindow(),
                "New layer",
                "Enter the name of the new layer (e.g., Poles, Joint Closures, OTB):"
            )
            if not ok2:
                return
            new_layer_name = (new_layer_name or "").strip()
            if not new_layer_name:
                return

            # If user requests Poles - use standard Poles layer iz FiberQPlugin.init_layer
            if new_layer_name in ("Poles", "Poles"):
                try:
                    # init_layer creates or finds Poles layer with correct fields and style
                    self.init_layer()
                    layer = self.layer
                    if layer is None:
                        QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Unable to create or find 'Poles' layer!")
                        return
                except Exception:
                    QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Unable to create or find 'Poles' layer!")
                    return

            else:
                # Create new point layer for other types (Joint Closures, etc.)
                crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
                layer = QgsVectorLayer(f"Point?crs={crs}", new_layer_name, "memory")
                pr = layer.dataProvider()
                # Add fields depending on layer type
                if new_layer_name == "Nastavci":
                    pr.addAttributes([QgsField("naziv", QVariant.String)])
                elif new_layer_name == "ZOK":
                    pr.addAttributes([QgsField("naziv", QVariant.String)])
                else:
                    # generic layer with single 'naziv' field
                    pr.addAttributes([QgsField("naziv", QVariant.String)])

                layer.updateFields()
                QgsProject.instance().addMapLayer(layer, True)

                # jednostavan simbol – ovde ne diramo Poles stil
                symbol = QgsSymbol.defaultSymbol(layer.geometryType())
                symbol_layer = symbol.symbolLayer(0)
                if symbol_layer is not None:
                    symbol_layer.setSize(10)
                    symbol_layer.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMetersInMapUnits)
                layer.renderer().setSymbol(symbol)
                layer.triggerRepaint()

        else:

            # Find layer by name
            layer = next((l for l in existing_layers if l.name() == selected_layer_name), None)  # noqa: E741
            if layer is None:
                QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Unable to find the target layer!")
                return

        # Extra protection: if target is Poles, ensure 'tip' field exists
        try:
            if layer.name() in ("Poles", "Poles") and "tip" not in layer.fields().names():
                layer.startEditing()
                layer.dataProvider().addAttributes([QgsField("tip", QVariant.String)])
                layer.updateFields()
                layer.commitChanges()
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin.import_points: {e}")

        # Transformacija koordinata ako je potrebno
        src_crs = imported_layer.crs()
        dst_crs = layer.crs()
        transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

        layer.startEditing()
        broj_dodatih = 0
        for feat in imported_layer.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            # Transformacija ako je potrebno
            if src_crs != dst_crs:
                geom.transform(transform)

            # Add each individual Point (even from MultiPoint)
            if geom.type() == QgsWkbTypes.GeometryType.PointGeometry:
                if geom.isMultipart():
                    for pt in geom.asMultiPoint():
                        if pt:
                            new_feat = QgsFeature(layer.fields())
                            new_feat.setGeometry(QgsGeometry.fromPointXY(pt))
                            # For Poles layer set default tip = "POLE"
                            try:
                                if layer.name() in ("Poles", "Poles") and "tip" in layer.fields().names():
                                    new_feat["tip"] = "POLE"
                            except Exception as e:
                                logger.debug(f"Error in FiberQPlugin.import_points: {e}")
                            layer.addFeature(new_feat)
                            broj_dodatih += 1
                else:
                    pt = geom.asPoint()
                    if pt:
                        new_feat = QgsFeature(layer.fields())
                        new_feat.setGeometry(QgsGeometry.fromPointXY(pt))
                        try:
                            if layer.name() in ("Poles", "Poles") and "tip" in layer.fields().names():
                                new_feat["tip"] = "POLE"
                        except Exception as e:
                            logger.debug(f"Error in FiberQPlugin.import_points: {e}")
                        layer.addFeature(new_feat)
                        broj_dodatih += 1
            # If Line or Polygon, skip!

        layer.commitChanges()
        layer.triggerRepaint()

        QMessageBox.information(self.iface.mainWindow(), "FiberQ", f"Imported {broj_dodatih} points into layer '{layer.name()}'!")

    # Automatska korekcija

    def _export_active_layer(self, only_selected: bool):
        """Helper to export active vector layer (all or only selected features)
        to one of the common exchange formats (GPX, KML/KMZ, GeoPackage)."""
        # Active layer must be a vector layer
        if not isinstance(self.iface.activeLayer(), QgsVectorLayer):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Export",
                "Please select an active vector layer before exporting."
            )
            return

        layer = self.iface.activeLayer()

        # Check selection if needed
        if only_selected and layer.selectedFeatureCount() == 0:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Export",
                "There are no selected features on the active layer."
            )
            return

        # Let user choose format
        formats = [
            ("GeoPackage (*.gpkg)", ".gpkg"),
            ("KML/KMZ (*.kml *.kmz)", ".kml"),
            ("GPX (*.gpx)", ".gpx"),
        ]
        items = [label for (label, _ext) in formats]
        choice, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Export format",
            "Select output format:",
            items,
            0,
            False,
        )
        if not ok or not choice:
            return

        ext = None
        for label, e in formats:
            if label == choice:
                ext = e
                break
        if not ext:
            return

        # Suggest filename next to current project (if any)
        project_path = QgsProject.instance().fileName()
        if project_path:
            base_dir = os.path.dirname(project_path)
        else:
            base_dir = os.path.expanduser("~")

        safe_layer_name = layer.name().replace(" ", "_")
        suggested = os.path.join(base_dir, safe_layer_name + ext)

        filename, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Export layer",
            suggested,
            choice,
        )
        if not filename:
            return

        # Ensure extension
        if not filename.lower().endswith(ext):
            filename += ext

        from qgis.core import QgsCoordinateReferenceSystem

        lower_ext = os.path.splitext(filename)[1].lower()

        # GPX/KML/KMZ are typically in WGS84
        if lower_ext in (".gpx", ".kml", ".kmz"):
            dest_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        else:
            dest_crs = layer.crs()

        # Try to guess driver for extension
        driver_name = ""
        try:
            driver_name = QgsVectorFileWriter.driverForExtension(lower_ext)
        except Exception as e:
            logger.debug(f"Error in FiberQPlugin._export_active_layer: {e}")
            driver_name = ""

        if not driver_name:
            mapping = {
                ".gpkg": "GPKG",
                ".gpx": "GPX",
                ".kml": "KML",
                ".kmz": "KML",
            }
            driver_name = mapping.get(lower_ext, "")

        if not driver_name:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Export",
                f"Unknown driver for extension '{lower_ext}'."
            )
            return

        # Perform export using the best available API
        try:
            result = None

            if hasattr(QgsVectorFileWriter, "writeAsVectorFormatV3"):
                opts = QgsVectorFileWriter.SaveVectorOptions()
                opts.driverName = driver_name
                opts.fileEncoding = "UTF-8"
                opts.onlySelectedFeatures = bool(only_selected)
                ctx = QgsProject.instance().transformContext()
                result = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer,
                    filename,
                    ctx,
                    opts,
                )

            elif hasattr(QgsVectorFileWriter, "writeAsVectorFormatV2"):
                opts = QgsVectorFileWriter.SaveVectorOptions()
                opts.driverName = driver_name
                opts.fileEncoding = "UTF-8"
                opts.onlySelectedFeatures = bool(only_selected)
                ctx = QgsProject.instance().transformContext()
                result = QgsVectorFileWriter.writeAsVectorFormatV2(
                    layer,
                    filename,
                    ctx,
                    opts,
                )

            else:
                # Fallback to deprecated API
                result = QgsVectorFileWriter.writeAsVectorFormat(
                    layer,
                    filename,
                    "UTF-8",
                    dest_crs,
                    driver_name,
                    onlySelected=bool(only_selected),
                )

        except Exception as ex:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Export",
                f"Error while exporting:\n{ex}"
            )
            return

        # Normalize result: QGIS versions may return 1, 2 or more values.
        if isinstance(result, tuple):
            if len(result) >= 2:
                res = result[0]
                err_message = result[1] or ""
            else:
                res = result[0]
                err_message = ""
        else:
            res = result
            err_message = ""

        if res != QgsVectorFileWriter.WriterError.NoError:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Export",
                f"Export failed: {err_message}"
            )
        else:
            scope_txt = "selected features" if only_selected else "all features"
            QMessageBox.information(
                self.iface.mainWindow(),
                "Export",
                f"Successfully exported {scope_txt} from layer '{layer.name()}'\n"
                f"to:\n{filename}"
            )

    def export_selected_features(self):
        """Export only selected features of the active layer. Delegates to ExportManager."""
        # Phase 8: Delegate to ExportManager
        if self.export_manager:
            try:
                self.export_manager.export_selected_features()
                return
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.export_selected_features: {e}")
        self._export_active_layer(only_selected=True)

    def export_all_features(self):
        """Export all features of the active layer. Delegates to ExportManager."""
        # Phase 8: Delegate to ExportManager
        if self.export_manager:
            try:
                self.export_manager.export_all_features()
                return
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.export_all_features: {e}")
        self._export_active_layer(only_selected=False)

    def check_consistency(self):
        self.popravljive_greske = []
        layers = {
            lyr.name(): lyr
            for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer)
        }

        # support both Serbian and English names
        route_layer = layers.get("Route") or layers.get("Route")
        poles_layer = layers.get("Poles") or layers.get("Poles")
        manholes_layer = layers.get("Manholes") or layers.get("OKNA")

        if route_layer and (poles_layer or manholes_layer):
            pole_points = []
            if poles_layer:
                pole_points += [f.geometry().asPoint() for f in poles_layer.getFeatures()]
            if manholes_layer:
                pole_points += [f.geometry().asPoint() for f in manholes_layer.getFeatures()]

            for feat in route_layer.getFeatures():
                geom = feat.geometry()
                poly = geom.asPolyline()
                if not poly:
                    continue
                start = poly[0]
                end = poly[-1]
                # Start
                if not any(QgsPointXY(sp).distance(start) < 1e-2 for sp in pole_points):
                    greska = {
                        'msg': f"Start of route (ID {feat.id()}) is NOT on a pole.",
                        'feat': feat,
                        'layer': route_layer,
                        'popravka': lambda f=feat: self.fix_route_to_pole(f, must_start=True)
                    }
                    self.popravljive_greske.append(greska)
                # Kraj
                if not any(QgsPointXY(sp).distance(end) < 1e-2 for sp in pole_points):
                    greska = {
                        'msg': f"End of route (ID {feat.id()}) is NOT on a pole.",
                        'feat': feat,
                        'layer': route_layer,
                        'popravka': lambda f=feat: self.fix_route_to_pole(f, must_start=False)
                    }
                    self.popravljive_greske.append(greska)

        if not self.popravljive_greske:
            QMessageBox.information(self.iface.mainWindow(), "Route correction", "No errors found!")
        else:
            dlg = CorrectionDialog(self.popravljive_greske, self.iface.mainWindow())
            dlg.exec()

        # Automatska korekcija

    def fix_route_to_pole(self, route_feature, must_start=True):
        poles_layer = next((lyr for lyr in QgsProject.instance().mapLayers().values()
                            if lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry
                            and lyr.name() in ('Poles', 'Poles')), None)  # noqa: W503

        if not poles_layer:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Layer 'Poles' not found!")
            return

        geom = route_feature.geometry()
        poly = geom.asPolyline()
        if not poly:
            return

        # Find nearest pole for start/end
        if must_start:
            route_point = poly[0]
            idx = 0
        else:
            route_point = poly[-1]
            idx = -1

        min_dist = None
        nearest_stub = None
        for pole_feat in poles_layer.getFeatures():
            pole_pt = pole_feat.geometry().asPoint()
            dist = QgsPointXY(pole_pt).distance(route_point)
            if min_dist is None or dist < min_dist:
                min_dist = dist
                nearest_stub = pole_pt

        # If pole found, move start/end of route to pole
        if nearest_stub and min_dist > 1e-2:
            poly[idx] = QgsPointXY(nearest_stub)
            new_geom = QgsGeometry.fromPolylineXY(poly)

            # Find 'Route' layer in project (QgsFeature doesn't have .layer())
            route_layer = next(
                (lyr for lyr in QgsProject.instance().mapLayers().values()
                 if isinstance(lyr, QgsVectorLayer)
                 and lyr.name() in ('Route', 'Route')  # noqa: W503
                 and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry),  # noqa: W503
                None
            )
            if not route_layer:
                QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Route layer 'Route' not found!")
                return

            route_layer.startEditing()
            route_layer.changeGeometry(route_feature.id(), new_geom)
            route_layer.commitChanges()
            route_layer.triggerRepaint()
            QMessageBox.information(
                self.iface.mainWindow(),
                "FiberQ",
                "Route has been automatically attached to a pole."
            )

    # === DRAWINGS / ATTACHMENTS (DWG/DXF) ===
    def _drawing_key(self, layer, fid):
        """Get drawing storage key."""
        # Phase 3.5: Delegate to DrawingManager
        if self.drawing_manager:
            return self.drawing_manager.drawing_key(layer, fid)
        return f"drawing_map/{layer.id()}/{int(fid)}"

    def _drawing_layers_key(self, layer, fid):
        """Get drawing layers storage key."""
        # Phase 3.5: Delegate to DrawingManager
        if self.drawing_manager:
            return self.drawing_manager.drawing_layers_key(layer, fid)
        return f"drawing_layers/{layer.id()}/{int(fid)}"

    def _drawing_layers_get(self, layer, fid):
        """Get drawing layer IDs."""
        # Phase 3.5: Delegate to DrawingManager
        if self.drawing_manager:
            try:
                return self.drawing_manager.drawing_layers_get(layer, fid)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._drawing_layers_get: {e}")
        key = self._drawing_layers_key(layer, fid)
        s = QgsProject.instance().readEntry("FiberQPlugin", key, "")[0]
        return [x for x in (s.split(",") if s else []) if x]

    def _drawing_layers_set(self, layer, fid, layer_ids):
        """Set drawing layer IDs."""
        # Phase 3.5: Delegate to DrawingManager
        if self.drawing_manager:
            try:
                self.drawing_manager.drawing_layers_set(layer, fid, layer_ids)
                return
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._drawing_layers_set: {e}")
        key = self._drawing_layers_key(layer, fid)
        QgsProject.instance().writeEntry("FiberQPlugin", key, ",".join(layer_ids or []))

    def _drawing_get(self, layer, fid):
        """Get drawing path."""
        # Phase 3.5: Delegate to DrawingManager
        if self.drawing_manager:
            try:
                return self.drawing_manager.drawing_get(layer, fid)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._drawing_get: {e}")
        key = self._drawing_key(layer, fid)
        return QgsProject.instance().readEntry("FiberQPlugin", key, "")[0]

    def _drawing_set(self, layer, fid, path):
        """Set drawing path."""
        # Phase 3.5: Delegate to DrawingManager
        if self.drawing_manager:
            try:
                self.drawing_manager.drawing_set(layer, fid, path)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._drawing_set: {e}")

    def _ensure_drawings_group(self, subgroup_name):
        """Create or return a drawings subgroup."""
        if self.drawing_manager:
            try:
                return self.drawing_manager.ensure_drawings_group(subgroup_name)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._ensure_drawings_group: {e}")
        return None

    def _guess_category_for_layer(self, layer):
        """Guess the drawing category for a layer."""
        if self.drawing_manager:
            try:
                return self.drawing_manager.guess_category_for_layer(layer)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._guess_category_for_layer: {e}")
        return "Other"

    def _is_drawing_loaded(self, path: str) -> bool:
        """Check if a drawing is already loaded."""
        if self.drawing_manager:
            try:
                return self.drawing_manager.is_drawing_loaded(path)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._is_drawing_loaded: {e}")
        return False

    def _open_drawing_path(self, path):
        """Open a drawing file."""
        if self.drawing_manager:
            try:
                self.drawing_manager.open_drawing_path(path)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._open_drawing_path: {e}")

    def _try_add_dwg_to_group(self, path, subgroup):
        """Try to add DWG/DXF to a group."""
        if self.drawing_manager:
            try:
                return self.drawing_manager.try_add_dwg_to_group(path, subgroup)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._try_add_dwg_to_group: {e}")
        return []

    def ui_add_drawing(self):
        """UI handler for adding a drawing."""
        if self.drawing_manager:
            try:
                self.drawing_manager.add_drawing()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.ui_add_drawing: {e}")

    def ui_open_drawing_click(self):
        """UI handler for opening a drawing by click."""
        try:
            self._open_tool
        except AttributeError:
            self._open_tool = OpenDrawingMapTool(self)
        self.iface.mapCanvas().setMapTool(self._open_tool)
        self.iface.messageBar().pushInfo("Drawing", "Click on a feature to open its drawing (ESC or right click to exit).")

    def ui_clear_drawing(self):
        """UI handler for clearing/unlinking a drawing from selected features.

        Issue #7: Added missing unlink drawing functionality.
        """
        try:
            from qgis.PyQt.QtWidgets import QMessageBox
        except Exception as e:
            logger.error(f"Could not import Qt widgets: {e}")
            return

        layer = self.iface.activeLayer()
        if not layer or layer.selectedFeatureCount() == 0:
            QMessageBox.information(
                self.iface.mainWindow(),
                'FiberQ',
                'Select one or more elements and try again.'
            )
            return

        feats = layer.selectedFeatures()
        count = 0
        for f in feats:
            if self.drawing_manager:
                try:
                    self.drawing_manager.clear_drawing(layer, f.id())
                    count += 1
                except Exception as e:
                    logger.debug(f"Error in FiberQPlugin.ui_clear_drawing: {e}")

        QMessageBox.information(
            self.iface.mainWindow(),
            'FiberQ',
            f'Drawing link removed for {count} element(s).'
        )

    # === UNDO / REDO (v1.2 — Feature 2) ===

    def _on_undo(self):
        """Handle Undo toolbar button / Ctrl+Shift+Z."""
        if self.undo_manager:
            self.undo_manager.undo()
        else:
            self.iface.messageBar().pushWarning("FiberQ", "Undo system not available.")

    def _on_redo(self):
        """Handle Redo toolbar button / Ctrl+Shift+Y."""
        if self.undo_manager:
            self.undo_manager.redo()
        else:
            self.iface.messageBar().pushWarning("FiberQ", "Undo system not available.")

    # === OKNA (Kanalizacija) ===
    def open_manhole_workflow(self):
        """Sekvenca: 1) izbor tipa okna -> 2) unos podataka -> 3) klik na mapu i laying."""
        try:
            # 1) type selection
            dlg1 = ManholeTypeDialog(self)
            if dlg1.exec() != QDialog.DialogCode.Accepted:
                return
            manhole_type = dlg1.selected_type()

            # 2) detalji
            dlg2 = ManholeDetailsDialog(self, prefill_type=manhole_type)
            if dlg2.exec() != QDialog.DialogCode.Accepted:
                return
            attrs = dlg2.values()  # dict sa vrednostima polja

            # Extract auto-increment flag (not a layer attribute)
            auto_increment = attrs.pop('_auto_increment', False)
            initial_id = attrs.get('broj_okna', '') or ''

            # 3) aktiviraj map alat za klik
            self._manhole_pending_attrs = attrs
            self._manhole_place_tool = ManholePlaceTool(self.iface, self)

            # Configure auto-increment if enabled
            if auto_increment:
                self._manhole_place_tool.set_auto_increment(True, initial_id)
                # Update the message to show auto-increment info
                first_id = self._manhole_place_tool._get_current_id()
                self.iface.mapCanvas().setMapTool(self._manhole_place_tool)
                self.iface.messageBar().pushInfo(
                    "Placing manholes",
                    f"Auto-incrementing from {first_id} — click to place (ESC to exit)."
                )
                # Record with auto-increment state for repeat (v1.2 Feature 3)
                self._record_cmd('place_manhole',
                                 auto_increment=True,
                                 last_counter=self._manhole_place_tool._id_counter,
                                 id_prefix=self._manhole_place_tool._id_prefix,
                                 id_pad_width=self._manhole_place_tool._id_pad_width)
            else:
                self.iface.mapCanvas().setMapTool(self._manhole_place_tool)
                self.iface.messageBar().pushInfo("Placing manhole", "Click on the map to place the manhole (ESC to exit).")
                self._record_cmd('place_manhole')
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Manhole", f"Error: {e}")

    def _ensure_okna_layer(self):
        """Create or return the Manholes layer."""
        # Phase 6: Delegate to LayerManager
        if self.layer_manager:
            try:
                lyr = self.layer_manager.ensure_manholes_layer()
                if lyr:
                    try:
                        self._apply_manhole_style(lyr)
                        self._apply_manhole_field_aliases(lyr)
                        self._set_okna_layer_alias(lyr)
                        self._move_layer_to_top(lyr)
                    except Exception as e:
                        logger.debug(f"Error in FiberQPlugin._ensure_okna_layer: {e}")
                    return lyr
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._ensure_okna_layer: {e}")
        return None

    def _move_layer_to_top(self, layer):
        """Move layer to top of layer tree."""
        if self.layer_manager:
            try:
                self.layer_manager.move_layer_to_top(layer)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._move_layer_to_top: {e}")

    def _apply_manhole_style(self, layer):
        """Apply manhole layer style."""
        if not layer or not layer.isValid():
            return

        if self.style_manager:
            try:
                self.style_manager.stylize_manhole_layer(layer)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._apply_manhole_style: {e}")

    # === PIPES: layer and style utilities ===

    def _move_group_to_top(self, group_name="CEVI"):
        """Move group to top of layer tree."""
        if self.pipe_manager:
            try:
                self.pipe_manager.move_group_to_top(group_name)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._move_group_to_top: {e}")

    def _ensure_pipes_group(self):
        """Create or return the Pipes group."""
        if self.pipe_manager:
            try:
                return self.pipe_manager.ensure_pipes_group()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._ensure_pipes_group: {e}")
        return None

    def _apply_pipe_field_aliases(self, layer):
        """Apply English field aliases to a pipe layer."""
        if self.pipe_manager:
            try:
                self.pipe_manager.apply_pipe_field_aliases(layer)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._apply_pipe_field_aliases: {e}")

    def _set_pipe_layer_alias(self, layer):
        """Set English layer names for pipe layers."""
        if self.pipe_manager:
            try:
                self.pipe_manager.set_pipe_layer_alias(layer)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._set_pipe_layer_alias: {e}")

    def _ensure_pipe_layer(self, name):
        """Create or return a pipe layer."""
        if self.pipe_manager:
            try:
                return self.pipe_manager.ensure_pipe_layer(name)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._ensure_pipe_layer: {e}")
        return None

    def _ensure_pe_cev_layer(self):
        """Create or return the PE pipes layer."""
        if self.pipe_manager:
            try:
                return self.pipe_manager.ensure_pe_pipe_layer()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._ensure_pe_cev_layer: {e}")
        return None

    def _ensure_transition_duct_layer(self):
        """Create or return the Transition pipes layer."""
        if self.pipe_manager:
            try:
                return self.pipe_manager.ensure_transition_pipe_layer()
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._ensure_transition_duct_layer: {e}")
        return None

    def _apply_pipe_style(self, layer, color_hex, width_mm):
        """Apply pipe layer style."""
        if self.pipe_manager:
            try:
                self.pipe_manager.apply_pipe_style(layer, color_hex, width_mm)
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin._apply_pipe_style: {e}")

    # === CEVI: workflow-i ===
    def open_pe_cev_workflow(self):
        """Open PE duct placement workflow."""
        if self.pipe_manager:
            try:
                self.pipe_manager.open_pe_duct_workflow(self)
                self._record_cmd('place_pe_duct')
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.open_pe_cev_workflow: {e}")

    def open_transition_duct_workflow(self):
        """Open transition duct placement workflow."""
        if self.pipe_manager:
            try:
                self.pipe_manager.open_transition_duct_workflow(self)
                self._record_cmd('place_transition_duct')
            except Exception as e:
                logger.debug(f"Error in FiberQPlugin.open_transition_duct_workflow: {e}")

    def open_fiberq_settings(self):
        dlg = FiberQSettingsDialog(self.iface.mainWindow(), plugin=self)
        dlg.exec()


# ManholeTypeDialog and ManholeDetailsDialog moved to dialogs/manhole_dialog.py (Phase 4)
from .dialogs.manhole_dialog import ManholeTypeDialog, ManholeDetailsDialog  # noqa: E402


# CablePickerDialog moved to dialogs/cable_dialog.py (Phase 4)
pass


# === DODATO: BreakpointTool za split linije ===
# BreakpointTool moved to tools/breakpoint_tool.py (Phase 3)
from .tools.breakpoint_tool import BreakpointTool  # noqa: E402


# === NEW: SmartMultiSelectTool — multi-layer smart selection ===


# Automatska korekcija trase


# === RELACIJE DIALOGI ===


# === NEW: Optical schematic view ===


RELACIJE_KATEGORIJE = [
    "Main",
    "Local",
    "International",
    "Metro network",
    "Regional",
]


# === DIALOG: Lista latentnih elemenata (overview) ===


# === DIALOG: Editing pitstops for one cable ===


# ===================== KATALOG BOJA – DIALOGI =====================


# PEDuctDialog and TransitionDuctDialog moved to dialogs/pipe_dialog.py (Phase 4)
pass

# === MAP TOOL: laying cevi po trasi (klik start + kraj sa 'snap on') ===


# === AUTO-ADDED: Save all layers to GeoPackage ===


def _open_fiberq_web(iface):
    """
    Umesto otvaranja web browsera, sada otvara FiberQ preglednu mapu
    kao QDialog sa QgsMapCanvas-om i slojevima iz PostGIS baze.
    Parametri konekcije se čitaju iz [postgis] sekcije u config.ini.
    """
    try:
        if not _fiberq_check_pro(iface):
            return
        from .addons import fiberq_preview
        fiberq_preview.open_preview_dialog(iface)
    except Exception as e:
        try:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(
                iface.mainWindow(),
                "FiberQ – pregledna mapa",
                f"Greška pri otvaranju pregledne mape:\n{e}"
            )
        except Exception as e:
            # if even QMessageBox fails, just ignore
            logger.debug(f"Could not show preview error dialog: {e}")


# =============================================================================
# Phase 1.3: The following GPKG export functions were moved to core/layer_manager.py:
# - _telecom_save_all_layers_to_gpkg, _telecom_export_one_layer_to_gpkg
# =============================================================================


# (Removed: dead activate/deactivate map-tool fragment mis-pasted here during
#  the monolith split; never called.)


# SlackUI moved to ui/slack_ui.py (Phase 5)
from .ui.slack_ui import SlackUI  # noqa: E402

# SlackDialog moved to dialogs/slack_dialog.py (Phase 4)
from .dialogs.slack_dialog import SlackDialog  # noqa: E402


# === Map alat za laying rezerve ===


# === MAP TOOL: Change element type (Izmena tipa elementa) ===


# =============================================================================
# Phase 1.3: The following layer utility functions were moved to core/layer_manager.py:
# - _element_def_by_name, _ensure_element_layer_with_style, _copy_attributes_between_layers
# - _ensure_region_layer, _collect_selected_geometries, _create_region_from_selection
# - _set_objects_layer_alias, _apply_objects_field_aliases, _ensure_objects_layer, _stylize_objects_layer
# - _telecom_save_all_layers_to_gpkg, _telecom_export_one_layer_to_gpkg
# =============================================================================


# === Draw Region (manual polygon) ==============================================


# === Crtanje objekta (polygon tools + dialog) ==================================


# =============================================================================
# Phase 1.3: Objects layer functions moved to core/layer_manager.py:
# - _set_objects_layer_alias, _apply_objects_field_aliases, _ensure_objects_layer, _stylize_objects_layer
# =============================================================================

# ObjectsUI moved to ui/objects_ui.py (Phase 5)
from .ui.objects_ui import ObjectsUI  # noqa: E402


def _img_key(layer, fid):
    return f"image_map/{layer.id()}/{int(fid)}"


def _img_get(layer, fid):
    try:
        return QgsProject.instance().readEntry("FiberQPlugin", _img_key(layer, fid), "")[0]
    except Exception as e:
        logger.debug(f"Error in FiberQPlugin._img_get: {e}")
        return ""


def _img_set(layer, fid, path):
    try:
        QgsProject.instance().writeEntry("FiberQPlugin", _img_key(layer, fid), path or "")
    except Exception as e:
        logger.debug(f"Error in FiberQPlugin._img_set: {e}")


# ============================================================================
# Extracted classes (moved out of this file)
# ============================================================================
# The original v1.x monolith kept many QDialog/QgsMapTool classes inline.
# In v1.0.1 refactor, those classes live in fiberq/extracted_classes.py, while
# main_plugin.py keeps FiberQPlugin + shared helpers.
# Tools already modularized elsewhere
from .tools.manhole_tool import ManholePlaceTool  # noqa: E402
from .tools.route_tool import ManualRouteTool  # noqa: E402
pass
from .tools.slack_tool import SlackPlaceTool  # noqa: E402

# Remaining dialogs/tools extracted from the legacy monolith
# Phase 4.2: Import from dedicated packages instead of extracted_classes
from .tools import (  # noqa: E402
    OpenDrawingMapTool,
    PointTool,
    PlaceElementTool,
    ExtensionTool,
    SmartMultiSelectTool,
    ChangeElementTypeTool,
    DrawRegionPolygonTool,
    BranchInfoTool,
    OpenImageMapTool,
    MoveFeatureTool,
)

from .dialogs import (  # noqa: E402
    _BOMDialog,
    CorrectionDialog,
    LocatorDialog,
    OpticalSchematicDialog,
    RelationsDialog,
    LatentElementsDialog,
    CreateRegionDialog,
    FiberQSettingsDialog,
)

from .utils.image_watcher import CanvasImageClickWatcher  # noqa: E402


# ---------------------------------------------------------------------------
# Legacy bridge
# extracted_classes.py now imports needed helpers/constants from utils/legacy_bridge.py.
# (No runtime patching required.)
# ---------------------------------------------------------------------------
