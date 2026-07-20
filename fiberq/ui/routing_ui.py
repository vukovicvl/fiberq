"""
FiberQ v2 - Routing UI

Toolbar group for route creation and management.
"""

import os

from qgis.PyQt.QtCore import QCoreApplication

from .base import (
    QAction, QMenu, QToolButton, QFileDialog, QgsProject,
    QgsVectorLayer, load_icon
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class RoutingUI:
    """
    Toolbar group for routing operations.

    Creates a drop-down menu with actions for:
    - Add pole
    - Create route
    - Merge selected routes
    - Import route from file
    - Add breakpoint
    - Create route manually
    - Change route type
    - Route correction
    """

    def __init__(self, core):
        """
        Initialize the routing UI.

        Args:
            core: Plugin core instance with iface and toolbar
        """
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Add pole
        icon_add = load_icon('ic_add_pole.svg')
        #: Menu entry, imperative verb + noun. Places one pole (the physical support
        #: that carries aerial cable) at a clicked point. The Quick toolbar exposes
        #: this same command as "Place Pole" - keep the two wordings consistent.
        core.action_add = QAction(icon_add, self.tr('Add pole'), core.iface.mainWindow())
        core.action_add.triggered.connect(core.activate_point_tool)
        core.actions.append(core.action_add)
        self.menu.addAction(core.action_add)

        # Create route
        icon_trasa = load_icon('ic_create_route.svg')
        #: Menu entry, imperative. "Route" here is the physical path/alignment on the
        #: ground that cables follow (fr: trace), NOT a network or file path. Builds
        #: the route line from the poles/manholes currently SELECTED - contrast with
        #: "Create a route manually" below. Quick toolbar wording: "Create Route".
        core.action_route = QAction(icon_trasa, self.tr('Create route'), core.iface.mainWindow())
        core.action_route.triggered.connect(core.create_route)
        core.actions.append(core.action_route)
        self.menu.addAction(core.action_route)

        # Merge selected routes
        icon_spoji = load_icon('ic_merge_selected_routes.svg')
        #: Menu entry, imperative. Joins the currently selected route lines into a
        #: single route feature. "Merge" is the geometry operation on the lines.
        core.action_merge = QAction(icon_spoji, self.tr('Merge selected routes'), core.iface.mainWindow())
        core.action_merge.triggered.connect(core.merge_all_routes)
        core.actions.append(core.action_merge)
        self.menu.addAction(core.action_merge)

        # Import route from file
        icon_import = load_icon('ic_import_route_from_file.svg')
        #: Menu entry, imperative. Loads route lines from an external GIS/CAD file on
        #: disk into the Route layer. "file" = a file on disk, not a QGIS project.
        core.action_import = QAction(icon_import, self.tr('Import route from file'), core.iface.mainWindow())
        core.action_import.triggered.connect(core.import_route_from_file)
        core.actions.append(core.action_import)
        self.menu.addAction(core.action_import)

        # Add breakpoint
        icon_lomna = load_icon('ic_add_breakpoint.svg')
        #: Menu entry, imperative. RESOLVED - this is a ROUTE GEOMETRY operation, not
        #: a fault: it SPLITS one route line into two at the clicked point (tool is
        #: BreakpointTool; every dialog it raises is titled "Split route"). NOT a
        #: fibre break/fault location - that is a separate feature ("Fiber break").
        #: fr: "point de coupure" (split point), never "coupure/rupture de fibre".
        core.action_breakpoint = QAction(icon_lomna, self.tr('Add breakpoint'), core.iface.mainWindow())
        core.action_breakpoint.triggered.connect(core.activate_breakpoint_tool)
        core.actions.append(core.action_breakpoint)
        self.menu.addAction(core.action_breakpoint)

        # Create route manually
        icon_rucna = load_icon('ic_create_route_manually.svg')
        #: Menu entry, imperative. Draws a route by clicking its vertices on the map.
        #: "manually" contrasts with "Create route" above, which derives the line
        #: automatically from the selected poles/manholes.
        core.action_manual = QAction(icon_rucna, self.tr('Create a route manually'), core.iface.mainWindow())
        core.action_manual.triggered.connect(core.activate_manual_route_tool)
        core.actions.append(core.action_manual)
        self.menu.addAction(core.action_manual)

        # Change route type
        icon_edit_tip_trase = load_icon('ic_change_route_type.svg')
        #: Menu entry, imperative. Edits the "route type" ATTRIBUTE of the selected
        #: routes (aerial / underground / ...), leaving the geometry untouched.
        core.action_edit_tip_trase = QAction(icon_edit_tip_trase, self.tr('Change route type'), core.iface.mainWindow())
        core.action_edit_tip_trase.triggered.connect(core.change_route_type)
        core.actions.append(core.action_edit_tip_trase)
        self.menu.addAction(core.action_edit_tip_trase)

        # Route correction
        icon_korekcija = load_icon('ic_route_correction.svg')
        #: Menu entry AND the title of the dialog it opens; noun phrase. A validation
        #: pass: it finds routes whose start or end vertex does not sit on a pole or
        #: manhole and offers to snap them. "correction" = repairing those errors.
        core.action_correction = QAction(icon_korekcija, self.tr('Route correction'), core.iface.mainWindow())
        core.action_correction.triggered.connect(core.check_consistency)
        core.actions.append(core.action_correction)
        self.menu.addAction(core.action_correction)

        # Toolbar button
        self.button = QToolButton()
        #: Toolbar drop-down button label, tooltip and status tip - the SAME string is
        #: reused 3x here, so one translation must serve all three. Noun: the group of
        #: route tools above. Keep it short enough for a toolbar button.
        self.button.setText(self.tr('Routing'))
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(load_icon('ic_routing.svg'))
        #: Toolbar drop-down button label, tooltip and status tip - the SAME string is
        #: reused 3x here, so one translation must serve all three. Noun: the group of
        #: route tools above. Keep it short enough for a toolbar button.
        self.button.setToolTip(self.tr('Routing'))
        #: Toolbar drop-down button label, tooltip and status tip - the SAME string is
        #: reused 3x here, so one translation must serve all three. Noun: the group of
        #: route tools above. Keep it short enough for a toolbar button.
        self.button.setStatusTip(self.tr('Routing'))
        core.toolbar.addWidget(self.button)

    def tr(self, message):
        """
        Translate a UI string using the RoutingUI translation context.

        Args:
            message: String literal to translate

        Returns:
            Translated string for the active locale
        """
        return QCoreApplication.translate('RoutingUI', message)

    # === Auto-save to GeoPackage methods ===

    def _project_gpkg_path(self):
        """Get the GeoPackage path from project settings."""
        try:
            val = QgsProject.instance().readEntry("TelecomPlugin", "gpkg_path", "")[0]
            return val or ""
        except Exception:
            return ""

    def _set_project_gpkg_path(self, path):
        """Set the GeoPackage path in project settings."""
        try:
            QgsProject.instance().writeEntry("TelecomPlugin", "gpkg_path", path or "")
        except Exception as e:
            logger.debug(f"Error in RoutingUI._set_project_gpkg_path: {e}")

    def _is_memory_vector(self, lyr):
        """Check if a layer is a memory vector layer."""
        try:
            if not isinstance(lyr, QgsVectorLayer):
                return False
            prov = ""
            try:
                prov = lyr.dataProvider().name().lower()
            except Exception as e:
                logger.debug(f"Error in RoutingUI._is_memory_vector: {e}")
            st = ""
            try:
                st = (lyr.storageType() or "").lower()
            except Exception as e:
                logger.debug(f"Error in RoutingUI._is_memory_vector: {e}")
            return ('memory' in prov) or st.startswith('memory')
        except Exception:
            return False

    def _toggle_auto_gpkg(self, enabled):
        """Toggle auto-save to GeoPackage."""
        from ..main_plugin import _telecom_export_one_layer_to_gpkg

        prj = QgsProject.instance()
        if enabled:
            gpkg = self._project_gpkg_path()
            if not gpkg:
                default_dir = os.path.dirname(prj.fileName()) if prj.fileName() else os.path.expanduser("~")
                gpkg, _ = QFileDialog.getSaveFileName(
                    self.core.iface.mainWindow(),
                    #: Title of the file-save dialog. "GeoPackage" is the OGC file
                    #: format (.gpkg) - keep the format name untranslated.
                    self.tr("Choose GeoPackage file for auto-save"),
                    os.path.join(default_dir, "Telecom.gpkg"),
                    "GeoPackage (*.gpkg)"
                )
                if not gpkg:
                    try:
                        self.core.action_auto_gpkg.blockSignals(True)
                        self.core.action_auto_gpkg.setChecked(False)
                        self.core.action_auto_gpkg.blockSignals(False)
                    except Exception as e:
                        logger.debug(f"Error in RoutingUI._toggle_auto_gpkg: {e}")
                    return
                if not gpkg.lower().endswith(".gpkg"):
                    gpkg += ".gpkg"
                self._set_project_gpkg_path(gpkg)

            # Convert existing memory layers
            layers = [l for l in prj.mapLayers().values() if isinstance(l, QgsVectorLayer)]  # noqa: E741
            for lyr in layers:
                if self._is_memory_vector(lyr):
                    _telecom_export_one_layer_to_gpkg(lyr, self._project_gpkg_path(), self.core.iface)

            # Connect signal
            try:
                prj.layerWasAdded.connect(self._on_layer_added_auto_gpkg)
            except Exception as e:
                logger.debug(f"Error in RoutingUI._toggle_auto_gpkg: {e}")
            try:
                #: Message-bar heading, reused for both the on and the off message.
                #: "Auto GPKG" = automatic saving to a GeoPackage; GPKG is that
                #: format's file extension. Keep "GPKG" as-is. The message beside it
                #: ("Autosave on GeoPackage.") means autosaving is now ENABLED.
                self.core.iface.messageBar().pushSuccess(self.tr("Auto GPKG"), self.tr("Autosave on GeoPackage."))
            except Exception as e:
                logger.debug(f"Error in RoutingUI._toggle_auto_gpkg: {e}")
        else:
            try:
                prj.layerWasAdded.disconnect(self._on_layer_added_auto_gpkg)
            except Exception as e:
                logger.debug(f"Error in RoutingUI._toggle_auto_gpkg: {e}")
            try:
                #: Message-bar heading, reused for both the on and the off message.
                #: "Auto GPKG" = automatic saving to a GeoPackage; GPKG is that
                #: format's file extension. Keep "GPKG" as-is. The message beside it
                #: ("Autosave on GeoPackage.") means autosaving is now ENABLED.
                self.core.iface.messageBar().pushInfo(self.tr("Auto GPKG"), self.tr("Autosave off."))
            except Exception as e:
                logger.debug(f"Error in RoutingUI._toggle_auto_gpkg: {e}")

    def _on_layer_added_auto_gpkg(self, lyr):
        """Handle layer added event for auto-gpkg."""
        from ..main_plugin import _telecom_export_one_layer_to_gpkg

        try:
            if not isinstance(lyr, QgsVectorLayer):
                return
            if self._is_memory_vector(lyr):
                gpkg = self._project_gpkg_path()
                if not gpkg:
                    return
                _telecom_export_one_layer_to_gpkg(lyr, gpkg, self.core.iface)
        except Exception as e:
            logger.debug(f"Error in RoutingUI._on_layer_added_auto_gpkg: {e}")


__all__ = ['RoutingUI']
