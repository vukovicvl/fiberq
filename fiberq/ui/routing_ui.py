"""
FiberQ v2 - Routing UI

Toolbar group for route creation and management.
"""

import os

from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP, QTimer

from .base import (
    QAction, QMenu, QToolButton, QFileDialog, QgsProject,
    QgsVectorLayer, load_icon
)

from ..core.gpkg_target import gpkg_target_problem
from ..i18n import safe_format

# Phase 5.2: Logging
from ..utils.errors import OperationErrors
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
        #: Whether this session connected the auto-save layer hook. Qt raises
        #: from disconnect() when nothing is connected, and that is the ordinary
        #: state, not an error worth catching.
        self._auto_gpkg_connected = False

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
        """The GeoPackage this project auto-saves to, or "" when it has none.

        Two keys, new one first, the way ``core/drawing_manager.py`` reads the
        picture links. "Save all layers to GeoPackage" writes the path under
        ``FiberQPlugin``; projects saved by older versions -- and this feature
        itself, until now -- carry it under ``TelecomPlugin``. Reading only the
        older key is why picking a file in Save all never reached the auto-save
        checkbox.
        """
        project = QgsProject.instance()
        path = project.readEntry("FiberQPlugin", "gpkg_path", "")[0]
        if not path:
            path = project.readEntry("TelecomPlugin", "gpkg_path", "")[0]
        return path or ""

    def _set_project_gpkg_path(self, path):
        """Remember the auto-save GeoPackage, under both keys.

        The older key is still written so a project saved here keeps working in
        an older FiberQ, which reads only that one.
        """
        project = QgsProject.instance()
        for scope in ("FiberQPlugin", "TelecomPlugin"):
            project.writeEntry(scope, "gpkg_path", path or "")

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
        """Turn auto-save to GeoPackage on or off.

        A Qt slot, so it must not raise -- QGIS answers an exception here with
        its "unhandled Python error" dialog. It used to not raise by swallowing
        five separate failures at debug level, which in a default install is the
        same as not noticing them. Now the collector absorbs what escapes and
        says so in one line.
        """
        from ..core.export_manager import export_one_layer_to_gpkg

        with OperationErrors(self.tr("Auto GPKG"), self.core.iface, absorb=True) as errors:
            prj = QgsProject.instance()
            if not enabled:
                self._stop_watching_for_new_layers(prj)
                #: Message-bar heading, reused for both the on and the off message.
                #: "Auto GPKG" = automatic saving to a GeoPackage; GPKG is that
                #: format's file extension. Keep "GPKG" as-is. The message beside it
                #: ("Autosave off.") means autosaving is now DISABLED.
                self.core.iface.messageBar().pushInfo(self.tr("Auto GPKG"), self.tr("Autosave off."))
                return

            gpkg = self._project_gpkg_path()
            problem = gpkg_target_problem(gpkg)
            if problem is not None:
                # One sentence naming the path, before the user is asked
                # anything. Without it, a project carried to another machine
                # fails once per layer with a raw OGR error apiece.
                if problem != "empty":
                    self.core.iface.messageBar().pushWarning(
                        self.tr("Auto GPKG"), self._target_problem_text(problem, gpkg))
                gpkg = self._ask_for_auto_gpkg(prj)
                if not gpkg:
                    self._untick()
                    return
                self._set_project_gpkg_path(gpkg)

            # Memory layers hold their features in RAM and lose them when the
            # project closes, so they are what auto-save exists to rescue.
            in_memory = [layer for layer in prj.mapLayers().values()
                         if isinstance(layer, QgsVectorLayer) and self._is_memory_vector(layer)]
            converted = sum(
                1 for layer in in_memory
                if export_one_layer_to_gpkg(layer, gpkg, self.core.iface, errors))
            if converted < len(in_memory):
                logger.warning(f"Auto-save converted {converted} of {len(in_memory)} layers into {gpkg}")

            prj.layerWasAdded.connect(self._on_layer_added_auto_gpkg)
            self._auto_gpkg_connected = True

            if not errors.failed:
                #: Message-bar heading, reused for both the on and the off message.
                #: "Auto GPKG" = automatic saving to a GeoPackage; GPKG is that
                #: format's file extension. Keep "GPKG" as-is. The message beside it
                #: ("Autosave on GeoPackage.") means autosaving is now ENABLED.
                self.core.iface.messageBar().pushSuccess(
                    self.tr("Auto GPKG"), self.tr("Autosave on GeoPackage."))

    def _target_problem_text(self, problem, path):
        """One sentence for a :mod:`fiberq.core.gpkg_target` problem code.

        The codes live in a module with no Qt import, so the words are made
        here where ``tr()`` can reach them.
        """
        if problem == "no_directory":
            #: Shown when the project's auto-save GeoPackage is on a folder that
            #: is not there -- typically a project opened on another machine, or
            #: an unplugged drive. {path} is a file path, not translated.
            source = QT_TRANSLATE_NOOP(
                'RoutingUI',
                "The auto-save folder is not there any more: {path}. Choose another file.")
        elif problem in ("not_writable", "directory_not_writable"):
            #: Shown when the auto-save GeoPackage, or the folder holding it,
            #: cannot be written to. {path} is a file path, not translated.
            source = QT_TRANSLATE_NOOP(
                'RoutingUI',
                "The auto-save file cannot be written to: {path}. Choose another file.")
        elif problem == "is_directory":
            #: Shown when the stored auto-save target names a folder rather than
            #: a file. {path} is a file path, not translated.
            source = QT_TRANSLATE_NOOP(
                'RoutingUI',
                "The auto-save target is a folder, not a GeoPackage: {path}. Choose a file.")
        else:
            #: Shown when the stored auto-save target is not a GeoPackage at all
            #: -- the file dialog does not stop the user picking something else.
            #: {path} is a file path, not translated.
            source = QT_TRANSLATE_NOOP(
                'RoutingUI',
                "That file is not a GeoPackage: {path}. Choose another file.")
        return safe_format(
            QCoreApplication.translate('RoutingUI', source), source, path=path)

    def on_project_target_changed(self):
        """Note that the project changed; decide once it has finished changing.

        Connected to **both** ``QgsProject.cleared`` and ``readProject``, and
        deliberately deciding nothing itself. Measured signal order: opening a
        project emits ``cleared`` first -- with the old project's entries gone
        and the new project's not yet read, so the path reads empty there no
        matter what the project carries -- and then ``readProject``. File > New
        emits ``cleared`` alone.

        Deciding inside ``cleared`` therefore unticked auto-save on *every*
        open, including a project that carries a perfectly good target, and new
        memory layers were then lost without a word. Deferring to the event loop
        lets both signals land first and asks the question once, of the project
        that is actually in front of the user.
        """
        QTimer.singleShot(0, self.settle_auto_gpkg)

    def settle_auto_gpkg(self):
        """Turn auto-save off when the project now open has nowhere to save to."""
        if self._project_gpkg_path():
            return
        self._stop_watching_for_new_layers(QgsProject.instance())
        if not self.core.action_auto_gpkg.isChecked():
            return
        self._untick()
        #: Shown when a project is opened or created that has no auto-save
        #: GeoPackage, so the setting could not be carried over. "Auto GPKG"
        #: is the heading; GPKG is the GeoPackage file extension, keep it as-is.
        self.core.iface.messageBar().pushInfo(
            self.tr("Auto GPKG"),
            self.tr("Autosave off: this project has no GeoPackage chosen yet."))

    def _ask_for_auto_gpkg(self, project):
        """Ask where to keep the auto-saved copy. Empty when the user cancels."""
        default_dir = os.path.dirname(project.fileName()) if project.fileName() else os.path.expanduser("~")
        gpkg, _ = QFileDialog.getSaveFileName(
            self.core.iface.mainWindow(),
            #: Title of the file-save dialog. "GeoPackage" is the OGC file
            #: format (.gpkg) - keep the format name untranslated.
            self.tr("Choose GeoPackage file for auto-save"),
            os.path.join(default_dir, "Telecom.gpkg"),
            "GeoPackage (*.gpkg)"
        )
        if not gpkg:
            return ""
        if not gpkg.lower().endswith(".gpkg"):
            gpkg += ".gpkg"
        return gpkg

    def _untick(self):
        """Put the checkbox back without re-entering this slot."""
        action = self.core.action_auto_gpkg
        action.blockSignals(True)
        action.setChecked(False)
        action.blockSignals(False)

    def _stop_watching_for_new_layers(self, project):
        """Disconnect the layer hook, if this session ever connected it.

        Qt raises ``TypeError`` from ``disconnect()`` when the slot was never
        connected, which is the ordinary state when auto-save has not been
        switched on. Tracking the connection says so without an exception, and
        the narrow guard below is for the case the flag and Qt disagree --
        a project replaced underneath us -- which is worth a log line.
        """
        if not self._auto_gpkg_connected:
            return
        try:
            project.layerWasAdded.disconnect(self._on_layer_added_auto_gpkg)
        except TypeError as exc:
            logger.warning(f"Auto-save was already disconnected: {exc}")
        self._auto_gpkg_connected = False

    def _on_layer_added_auto_gpkg(self, lyr):
        """Copy a newly added memory layer into the auto-save GeoPackage.

        A Qt slot on ``QgsProject.layerWasAdded``: it must not raise, and until
        now it did not by wrapping its whole body in a debug-level swallow. A
        layer that failed to save simply stayed in memory, and the user found
        out when the project was reopened without it.
        """
        from ..core.export_manager import export_one_layer_to_gpkg

        if not isinstance(lyr, QgsVectorLayer) or not self._is_memory_vector(lyr):
            return
        gpkg = self._project_gpkg_path()
        if not gpkg:
            return

        with OperationErrors(self.tr("Auto GPKG"), self.core.iface, absorb=True) as errors:
            # Returned so the result is answered for rather than dropped; Qt
            # ignores a slot's return value, the collector is what reaches the
            # user, and a caller that wants to know can still ask.
            return export_one_layer_to_gpkg(lyr, gpkg, self.core.iface, errors)


__all__ = ['RoutingUI']
