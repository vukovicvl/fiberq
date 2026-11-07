"""
FiberQ v2 - Export Manager

This module centralizes all export operations including:
- Export layers to GeoPackage, GPX, KML/KMZ
- Save all layers to single GeoPackage
- Export individual layers with source redirection
- Write FiberQ metadata table for Designer compatibility (Phase 0.2)

Phase 8 of the modular refactoring.
"""

import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone

from qgis import core as qgis_core
from qgis.core import (
    Qgis, QgsAnnotationLayer, QgsProject, QgsVectorLayer, QgsVectorFileWriter,
    QgsCoordinateTransformContext, QgsCoordinateReferenceSystem,
    QgsMapLayerStyle, QgsMessageLog,
)
from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QInputDialog

# WP1a: canonical schema version + project marker
from ..models.schema import SCHEMA_VERSION
from .schema_version import mark_project_current

# Phase 5.2: Logging
from ..i18n import safe_format
from ..utils.compat import save_file_name, save_style_to_database
from ..utils.errors import OperationErrors, check_commit, describe
from ..utils.logger import PLUGIN_NAME, get_logger
from .gpkg_target import (
    NOTHING, file_identity, gpkg_target_problem, plan_tables, read_contents, same_file,
    sqlite_fold, styled_tables, table_name_for, table_state, unambiguous, used_tables,
)
logger = get_logger(__name__)

#: QGIS 3.24 brought group layers; on 3.22 there are none to find.
_GROUP_LAYER = getattr(qgis_core, "QgsGroupLayer", None)

#: WP4 4.2 item R3. These two sentences come from the duplicate export this
#: branch deleted (main_plugin._export_active_layer), where WP1 had put them --
#: and where nothing could reach them, because that copy only ran when this one
#: raised. The live path had the fragment-assembled form WP1 replaced:
#:
#:     scope_txt = "selected features" if only_selected else "all features"
#:     f"Successfully exported {scope_txt} from layer '{...}'"
#:
#: which is untranslatable into French: "de" + "les" contracts to the mandatory
#: "des", and no runtime substitution into a fixed "de {scope}" can produce it.
#: So WP1's delivered fix sat in unreachable code while the bug it fixed was
#: what users saw. Moving them here is what makes WP1 reachable.
#:
#: Keep each as ONE whole sentence; do not reassemble them from fragments. Only
#: the layer name and the path are placeholders.
#:
#: Confirmation shown after exporting ONLY the features the user had selected.
_EXPORTED_SELECTED = QT_TRANSLATE_NOOP(
    'FiberQExport',
    "Successfully exported the selected features of layer '{layer}'\nto:\n{path}")
#: Confirmation shown after exporting the WHOLE layer (no selection filter).
_EXPORTED_ALL = QT_TRANSLATE_NOOP(
    'FiberQExport', "Successfully exported all features of layer '{layer}'\nto:\n{path}")

#: Title on every message-bar entry this module pushes. Kept as it has always
#: read, so a user who has seen it before still recognises it.
GPKG_EXPORT = "GPKG export"

#: Title of the question below when "Save all layers to GeoPackage" asks it,
#: used only where the toolbar button's own text cannot be read: the same
#: words. "GeoPackage" is the file format (.gpkg).
_SAVE_ALL_TITLE = QT_TRANSLATE_NOOP('FiberQExport', "Save all layers to GeoPackage")

#: Asked before a save into a GeoPackage that already has a table named like
#: one of the project's layers while no layer of the project reads that table
#: -- typically left there by an earlier session. {file} is the file's name and
#: {tables} the table's name, neither translated. One table here; several below.
_UNUSED_ONE = QT_TRANSLATE_NOOP(
    'FiberQExport', "{file} already has a table named {tables}. No layer of this project uses it.")
#: As above, for several tables. {tables} is a comma-separated list of names.
_UNUSED_MANY = QT_TRANSLATE_NOOP(
    'FiberQExport', "{file} already has tables named {tables}. No layer of this project uses them.")
#: What each answer to the question above does, one line per button. {kept} is
#: the name the layer gets beside the old table when it is kept, not
#: translated. "it" in the last line is the file.
_UNUSED_DETAIL_ONE = QT_TRANSLATE_NOOP(
    'FiberQExport',
    "Replace it: the table is overwritten with this project's layer, and its old features "
    "and styles are gone.\n"
    "Keep it: this project's layer is saved next to it, as {kept}.\n"
    "Either way, the file's other tables stay as they are, and so does anything other "
    "programs stored in it.")
#: As above, for several tables. {kept} is a comma-separated list of names.
_UNUSED_DETAIL_MANY = QT_TRANSLATE_NOOP(
    'FiberQExport',
    "Replace them: the tables are overwritten with this project's layers, and their old "
    "features and styles are gone.\n"
    "Keep them: this project's layers are saved next to them, as {kept}.\n"
    "Either way, the file's other tables stay as they are, and so does anything other "
    "programs stored in it.")
#: Button of the question above, one table: write this project's layer over it.
_REPLACE_ONE = QT_TRANSLATE_NOOP('FiberQExport', "Replace it")
#: Button of the question above, several tables: write the layers over them.
_REPLACE_MANY = QT_TRANSLATE_NOOP('FiberQExport', "Replace them")
#: Button of the question above, one table: leave it, save the layer beside it.
_KEEP_ONE = QT_TRANSLATE_NOOP('FiberQExport', "Keep it")
#: Button of the question above, several tables: leave them, save beside them.
_KEEP_MANY = QT_TRANSLATE_NOOP('FiberQExport', "Keep them")

#: The success message of "Save all layers to GeoPackage", one line in the
#: message bar. {file} is the GeoPackage's file name there, and its full path
#: where the FiberQ log records the same sentence; not translated.
_SAVED = QT_TRANSLATE_NOOP('FiberQExport', "All layers saved to {file}.")
#: Added to a success message, on the same line, when the user chose to replace
#: an unused table. {tables} is the table's name, not translated.
_REPLACED_ONE = QT_TRANSLATE_NOOP('FiberQExport', "The old table {tables} was replaced.")
#: As above, for several tables. {tables} is a comma-separated list of names,
#: shortened in the message bar to its first few and "and 3 more" (see below).
_REPLACED_MANY = QT_TRANSLATE_NOOP('FiberQExport', "The old tables {tables} were replaced.")
#: A line of its own after a save, kept until the user closes it, when a layer
#: went to a table named other than itself because the file already has a
#: table of its name. {pairs} is the layer and its table, "Poles → Poles_2";
#: not translated.
_RENAMED_ONE = QT_TRANSLATE_NOOP('FiberQExport', "Saved next to a table of the same name: {pairs}.")
#: As above, for several layers. {pairs} lists each layer and its table,
#: "Poles → Poles_2, Scratch A → Scratch_A_2", shortened in the message bar to
#: its first few and "and 3 more"; not translated.
_RENAMED_MANY = QT_TRANSLATE_NOOP('FiberQExport', "Saved next to tables of the same names: {pairs}.")
#: A line of its own, kept until closed, when auto-save is on and this save
#: moved its file: new layers now go to the file just saved to. {file} is that
#: file's name.
_AUTO_SAVE_MOVED = QT_TRANSLATE_NOOP('FiberQExport', "Auto-save now writes to {file}.")
#: The end of a list shortened to fit the message bar: {names} are the first
#: few names, comma-separated, and {count} how many more there are. The whole
#: list is in the FiberQ log.
_AND_MORE = QT_TRANSLATE_NOOP('FiberQExport', "{names} and {count} more")

#: What happened to a layer, after the layer's name: its table was written --
#: the table now holds this layer's features -- but the table's old styles
#: could not be removed, so the layer was not pointed at it and still reads its
#: old source. {table} is the table's name and {reason} the database's own
#: words, neither translated.
_STYLES_STAY = QT_TRANSLATE_NOOP(
    'FiberQExport',
    "{table} now holds this layer, but the layer still reads its old source: the table's old styles "
    "could not be removed ({reason})")
#: Why a layer was not saved, when it was replacing an unused table the user
#: chose to replace and the write failed part-way: the old table is gone with
#: it. {table} is the old table's name and {reason} the writer's own words,
#: neither translated.
_OLD_TABLE_GONE = QT_TRANSLATE_NOOP(
    'FiberQExport', "not saved, and the old table {table} is no longer in the file: {reason}")
#: As above, when the failed write left a table of that name holding only part
#: of the layer, and none of the old table's features.
_OLD_TABLE_PART = QT_TRANSLATE_NOOP(
    'FiberQExport',
    "not saved, and the old table {table} was overwritten with only part of this layer: {reason}")

#: Shown before anything is asked or written when the chosen GeoPackage is a
#: folder. {file} is its name, not translated; the FiberQ log has the full path.
_TARGET_FOLDER = QT_TRANSLATE_NOOP('FiberQExport', "{file} is a folder, not a GeoPackage. Nothing was saved.")
#: As above, when the file cannot be written to: read-only, or in a folder the
#: user may not write in.
_TARGET_READ_ONLY = QT_TRANSLATE_NOOP('FiberQExport', "{file} cannot be written to. Nothing was saved.")
#: As above, when the file is not a GeoPackage at all.
_TARGET_NOT_GPKG = QT_TRANSLATE_NOOP('FiberQExport', "{file} is not a GeoPackage. Nothing was saved.")
#: As above, when the file's list of tables cannot be read -- another program
#: holds it, or it is damaged -- so FiberQ cannot tell which tables are in use.
#: {reason} is the database's own words, not translated.
_TARGET_UNREADABLE = QT_TRANSLATE_NOOP(
    'FiberQExport', "The tables of {file} could not be read ({reason}). Nothing was saved.")
#: Shown, and nothing written, when the user has answered the question about
#: unused tables and the GeoPackage or the project's layers are no longer what
#: the question was about: another program wrote to the file or replaced it,
#: or a layer was added or removed while the question was open. {file} is the
#: GeoPackage's file name, not translated.
_CHANGED_WHILE_ASKING = QT_TRANSLATE_NOOP(
    'FiberQExport', "{file} or this project changed while the question was open. Nothing was saved.")

#: How many characters of a green message-bar line, and of an Info line that
#: stays, a list may take them to. The bar shows one line of an item's text --
#: a newline is a space, and what does not fit is cut off -- and measured in a
#: QgsMessageBar 1366 pixels wide, a green line, which also carries a countdown
#: button, shows 112 characters beside its heading on QGIS 3.22.16 and 3.40.15
#: (DejaVu LGC Sans 12 in the test images) and 173 on 4.2.3 (Sans Serif 9); an
#: Info line shows 121 and 175. A tenth is left for wider words and fonts.
_SUCCESS_ROOM = 100
_NOTE_ROOM = 110

#: The answers of :func:`ask_about_unused_tables`. None is Cancel.
REPLACE = "replace"
KEEP = "keep"

#: What :meth:`ExportManager._table_state` answers when the file could not be
#: read, so that nothing is said about a table no one could look at.
_UNREAD = object()


def _tr(source):
    """``source`` in the user's language, from this module's context."""
    return QCoreApplication.translate('FiberQExport', source)


class _AutoSaveHold:
    """Whether auto-save's layer hook may write now, and what it put off until it may.

    Save all and turning auto-save on plan their tables, may ask, and then
    write. A layer added to the project meanwhile reaches auto-save's hook
    (``RoutingUI._on_layer_added_auto_gpkg``), which would write it into the
    file at once -- under a name the plan holds as free, or into the file the
    question is about. So those two hold the hook for that span
    (:func:`hold_auto_save`): it puts the layer off (:func:`defer_auto_save`),
    and once the hold is released -- after a Cancel or a failure too -- the
    layer goes the hook's own way.
    """

    def __init__(self):
        self.depth = 0
        self.waiting = []


_HOLD = _AutoSaveHold()


@contextmanager
def hold_auto_save():
    """Hold auto-save's layer hook for the ``with`` block; what it put off meanwhile runs after."""
    _HOLD.depth += 1
    try:
        yield
    finally:
        _HOLD.depth -= 1
        if _HOLD.depth == 0:
            _release_held()


def _release_held():
    """Run what the hook put off, now that nothing holds it."""
    waiting, _HOLD.waiting = _HOLD.waiting, []
    for callback in waiting:
        try:
            callback()
        except Exception as exc:  # a slot's body: nothing may escape the save that held it
            logger.warning(f"Auto-save could not take a layer added during a save: {describe(exc)}",
                           exc_info=exc)


def auto_save_held():
    """True while Save all or turning auto-save on is planning, asking or writing."""
    return _HOLD.depth > 0


def defer_auto_save(callback):
    """Run ``callback`` -- the hook, for a layer it put off -- once the hold is released."""
    _HOLD.waiting.append(callback)


def _reader(layer):
    """``(provider, source, valid, driver)`` of one project layer, as ``gpkg_target.used_tables`` reads it.

    An annotation layer and a group layer have no provider and no source --
    QGIS answers "" for both (measured on 3.22.16 and 4.2.3) -- and read
    nothing: they go by their kind's name, which gpkg_target knows. Any other
    layer without a provider is a plugin's, and stays unknown. ``driver`` is
    the GDAL driver an OGR layer's provider opened its file with, its storage
    type -- "GeoJSON", "ESRI Shapefile", "OGR_VRT" (measured on 3.22.16,
    3.40.15 and 4.2.3), "GDALG" (4.2.3 with GDAL 3.12.2) -- and None for any
    other layer: QGIS names no driver for a raster.
    """
    provider = layer.providerType()
    if not provider:
        if isinstance(layer, QgsAnnotationLayer):
            provider = "annotation"
        elif _GROUP_LAYER is not None and isinstance(layer, _GROUP_LAYER):
            provider = "group"
    driver = layer.storageType() if provider == "ogr" and isinstance(layer, QgsVectorLayer) else None
    return provider, layer.source(), layer.isValid(), driver


def _identify(path, raster=False):
    """The short name of the GDAL driver that opens ``path``, or None: what gpkg_target asks of another file.

    As a raster dataset when ``raster`` (a GDAL layer's file), else as a
    vector one (an OGR layer's): the flag each provider opens it with.
    gdal.IdentifyDriverEx picks the driver as an open does, by what the file
    holds and by its name -- measured on GDAL 3.4.1, 3.8.4, 3.10.3 and 3.12.2:
    an OGR VRT saved as .geojson, .csv or .shp is OGR_VRT, a tile index saved
    as .tif or .json GTI (GDAL 3.9 and later), a GDAL pipeline saved as .json
    GDALG (3.11 and later), and a plain file its own format. None too when
    GDAL's bindings are missing or it raises: the file is then not
    understood, and nothing is offered.
    """
    try:
        from osgeo import gdal
    except ImportError:
        return None
    try:
        driver = gdal.IdentifyDriverEx(str(path), gdal.OF_RASTER if raster else gdal.OF_VECTOR)
    except (RuntimeError, ValueError):
        # With GDAL's exceptions on, a file it cannot tell raises; a path it
        # cannot take is a ValueError. Either way, not understood.
        return None
    return driver.ShortName if driver is not None else None


def _project_state(project):
    """Every layer of ``project`` as ``(id, provider, source)``, in a fixed order: what a plan read of it."""
    return sorted((layer.id(),) + _reader(layer)[:2] for layer in project.mapLayers().values())


def unused_tables_question(parent, title, gpkg_path, plan):
    """The question a save asks before writing over, or beside, tables nothing uses.

    ``plan`` is the one made without replacing, so its ``tables`` are the names
    the layers would get beside the old tables. Returns ``(box, replace,
    keep)``: the box, not yet shown, and its two answer buttons.
    """
    indexes = sorted(plan.offers)
    many = len(indexes) > 1
    text = _UNUSED_MANY if many else _UNUSED_ONE
    detail = _UNUSED_DETAIL_MANY if many else _UNUSED_DETAIL_ONE

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(safe_format(_tr(text), text, file=os.path.basename(gpkg_path),
                            tables=", ".join(plan.offers[index] for index in indexes)))
    box.setInformativeText(safe_format(_tr(detail), detail,
                                       kept=", ".join(plan.tables[index] for index in indexes)))
    replace = box.addButton(_tr(_REPLACE_MANY if many else _REPLACE_ONE), QMessageBox.ButtonRole.YesRole)
    keep = box.addButton(_tr(_KEEP_MANY if many else _KEEP_ONE), QMessageBox.ButtonRole.NoRole)
    cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(replace)
    box.setEscapeButton(cancel)
    return box, replace, keep


def ask_about_unused_tables(parent, title, gpkg_path, plan):
    """Ask :func:`unused_tables_question`: :data:`REPLACE`, :data:`KEEP`, or None for Cancel."""
    box, replace, keep = unused_tables_question(parent, title, gpkg_path, plan)
    box.exec()
    clicked = box.clickedButton()
    if clicked == replace:
        return REPLACE
    if clicked == keep:
        return KEEP
    return None


def action_title(action, fallback):
    """The text of ``action`` -- the button the user clicked -- as a window title.

    ``fallback`` when there is no action to read, or it has no text. A "&"
    that marks a keyboard shortcut is dropped; "&&" is a real "&".
    """
    text = action.text() if action is not None and hasattr(action, "text") else ""
    text = str(text or "").replace("&&", "\0").replace("&", "").replace("\0", "&")
    return text or fallback


def _listed(names, room):
    """``names`` joined with ", " in at most ``room`` characters, or as few as one.

    A list too long for its line keeps its first names and ends "and N more"
    (:data:`_AND_MORE`).
    """
    names = [str(name) for name in names]
    shown = len(names)
    text = ", ".join(names)
    while len(text) > room and shown > 1:
        shown -= 1
        text = safe_format(_tr(_AND_MORE), _AND_MORE, names=", ".join(names[:shown]),
                           count=len(names) - shown)
    return text


def saved_report(outcome, plan, names, moved=None, room=_SUCCESS_ROOM, note_room=_NOTE_ROOM, saved=None):
    """What a save tells the user: ``(success, notes, sentences)``.

    ``success`` is the green line -- ``outcome``, "All layers saved to
    fu8.gpkg.", and the replaced tables after it while the line fits in
    ``room`` characters -- or None when ``outcome`` is None: a save that failed
    in part has no green line. ``notes`` are lines of their own, of
    ``note_room``: the layers stored under another table name, and ``moved``,
    auto-save's new file. A list too long for its line is shortened ("and 3
    more"); ``sentences`` holds each of those sentences with every name, for
    the FiberQ log.

    ``names`` are the layers' own names, in the plan's order. ``saved``, when
    given, holds the indexes of the layers that were saved: the others' tables
    are neither said to be replaced nor to be beside anything.
    """
    success, notes, sentences = outcome, [], []
    said = range(len(plan.tables)) if saved is None else saved
    replaced = [plan.offers[index] for index in sorted(plan.offers) if plan.replace and index in said]
    if replaced:
        source = _REPLACED_MANY if len(replaced) > 1 else _REPLACED_ONE
        sentences.append(safe_format(_tr(source), source, tables=", ".join(replaced)))
        if outcome is not None:
            free = room - len(outcome) - 1 - len(safe_format(_tr(source), source, tables=""))
            line = safe_format(_tr(source), source, tables=_listed(replaced, free))
            if len(outcome) + 1 + len(line) <= room:
                success = f"{outcome} {line}"
    renamed = [index for index in plan.renamed if index in said]
    if renamed:
        source = _RENAMED_MANY if len(renamed) > 1 else _RENAMED_ONE
        pairs = [f"{names[index]} → {plan.tables[index]}" for index in renamed]
        sentences.append(safe_format(_tr(source), source, pairs=", ".join(pairs)))
        free = note_room - len(safe_format(_tr(source), source, pairs=""))
        notes.append(safe_format(_tr(source), source, pairs=_listed(pairs, free)))
    if moved:
        notes.append(moved)
        sentences.append(moved)
    return success, notes, sentences


def push_saved(bar, heading, outcome, plan, names, logged=None, moved=None, saved=None):
    """Tell the user what a save did, one message-bar line at a time.

    The bar shows one line of text per item, and a green item closes itself
    after a few seconds: the success is :func:`saved_report`'s one line, and
    its notes are Info items that stay until the user closes them. The bar
    shows its newest item first and the others after it, newest first, so the
    notes go in last to first and the success after them -- it is read first,
    and the notes are what stays. Everything, in full and with ``logged`` --
    ``outcome`` naming the whole path -- goes to the FiberQ log.

    ``outcome`` None is a save that failed in part, whose failure the caller's
    collector says once this returns: no green line then, but the notes still
    say where the ``saved`` layers went and that auto-save moved, and the log
    which tables they replaced.
    """
    success, notes, sentences = saved_report(outcome, plan, names, moved, saved=saved)
    for note in reversed(notes):
        bar.pushMessage(heading, note, Qgis.MessageLevel.Info, 0)
    if success is not None:
        bar.pushSuccess(heading, success)
    lines = ([logged or outcome] if outcome is not None else []) + sentences
    if lines:
        QgsMessageLog.logMessage(" ".join(lines), PLUGIN_NAME, Qgis.MessageLevel.Info)


def _writer_result(result):
    """``(code, reason)`` from whichever shape ``writeAsVectorFormatV3`` returned.

    It answers with a bare error code on some QGIS builds and a tuple carrying
    the message on others. The message is the only part worth showing a user, so
    it is worth the two lines not to drop it.
    """
    if isinstance(result, tuple):
        return result[0], (result[1] if len(result) > 1 else "")
    return result, ""


class ExportManager:
    """
    Centralized export management for FiberQ plugin.

    Handles exporting layers to various formats (GeoPackage, GPX, KML).
    """

    # Supported export formats
    FORMATS = [
        ("GeoPackage (*.gpkg)", ".gpkg"),
        ("KML/KMZ (*.kml *.kmz)", ".kml"),
        ("GPX (*.gpx)", ".gpx"),
    ]

    # Driver mapping for extensions
    DRIVER_MAP = {
        ".gpkg": "GPKG",
        ".gpx": "GPX",
        ".kml": "KML",
        ".kmz": "KML",
    }

    def __init__(self, iface, plugin=None):
        """
        Initialize the export manager.

        Args:
            iface: QGIS interface instance
            plugin: Reference to main plugin (optional)
        """
        self.iface = iface
        self.plugin = plugin

    # =========================================================================
    # SINGLE LAYER EXPORT
    # =========================================================================

    def export_active_layer(self, only_selected=False):
        """
        Export the active vector layer to a file.

        Args:
            only_selected: If True, export only selected features
        """
        # Validate active layer
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
        items = [label for (label, _ext) in self.FORMATS]
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

        # Get extension for chosen format
        ext = None
        for label, e in self.FORMATS:
            if label == choice:
                ext = e
                break
        if not ext:
            return

        # Suggest filename
        project_path = QgsProject.instance().fileName()
        base_dir = os.path.dirname(project_path) if project_path else os.path.expanduser("~")
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

        # Perform export
        self._do_export(layer, filename, only_selected)

    def _do_export(self, layer, filename, only_selected):
        """
        Perform the actual export operation.

        Args:
            layer: Layer to export
            filename: Output filename
            only_selected: Export only selected features
        """
        lower_ext = os.path.splitext(filename)[1].lower()

        # GPX/KML/KMZ typically use WGS84
        if lower_ext in (".gpx", ".kml", ".kmz"):
            dest_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        else:
            dest_crs = layer.crs()

        # Get driver name
        driver_name = ""
        try:
            driver_name = QgsVectorFileWriter.driverForExtension(lower_ext)
        except Exception:
            driver_name = ""

        if not driver_name:
            driver_name = self.DRIVER_MAP.get(lower_ext, "")

        if not driver_name:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Export",
                f"Unknown driver for extension '{lower_ext}'."
            )
            return

        # Perform export using best available API
        try:
            result = None

            if hasattr(QgsVectorFileWriter, "writeAsVectorFormatV3"):
                opts = QgsVectorFileWriter.SaveVectorOptions()
                opts.driverName = driver_name
                opts.fileEncoding = "UTF-8"
                opts.onlySelectedFeatures = bool(only_selected)
                ctx = QgsProject.instance().transformContext()
                result = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer, filename, ctx, opts
                )
            elif hasattr(QgsVectorFileWriter, "writeAsVectorFormatV2"):
                opts = QgsVectorFileWriter.SaveVectorOptions()
                opts.driverName = driver_name
                opts.fileEncoding = "UTF-8"
                opts.onlySelectedFeatures = bool(only_selected)
                ctx = QgsProject.instance().transformContext()
                result = QgsVectorFileWriter.writeAsVectorFormatV2(
                    layer, filename, ctx, opts
                )
            else:
                # Fallback to deprecated API
                result = QgsVectorFileWriter.writeAsVectorFormat(
                    layer, filename, "UTF-8", dest_crs, driver_name,
                    onlySelected=bool(only_selected)
                )
        except Exception as ex:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Export",
                f"Error while exporting:\n{ex}"
            )
            return

        # Handle result
        if isinstance(result, tuple):
            res = result[0]
            err_message = result[1] if len(result) >= 2 else ""
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
            source = _EXPORTED_SELECTED if only_selected else _EXPORTED_ALL
            QMessageBox.information(
                self.iface.mainWindow(),
                "Export",
                safe_format(QCoreApplication.translate('FiberQExport', source), source,
                            layer=layer.name(), path=filename)
            )

    def export_selected_features(self):
        """Export only selected features of the active layer."""
        self.export_active_layer(only_selected=True)

    def export_all_features(self):
        """Export all features of the active layer."""
        self.export_active_layer(only_selected=False)

    # =========================================================================
    # GEOPACKAGE OPERATIONS
    # =========================================================================

    def save_all_layers_to_gpkg(self):
        """Export every vector layer to one GeoPackage and repoint the project at it.

        Each layer is committed, written, and only then repointed, and each of
        those three can fail on its own. They are collected rather than raised:
        one unreadable layer out of twelve should not stop the other eleven
        being saved, and the user needs to know which one it was.

        **A layer whose commit fails is left alone entirely** -- not written and
        not repointed. Repointing it would swap the data source out from under
        edits that are still only in the buffer, which turns a failed save into
        lost work. Its old source keeps the last good copy.

        **Nothing is written before the plan is settled** (:meth:`_plan`): a
        file holding tables no layer uses, named like the project's layers,
        is a question for the user first, and Cancel leaves the file, the
        layers and the project's entries exactly as they were. So does a file
        that cannot be saved into, or whose tables cannot be read, and one
        that, or a project that, changed while the question was open.

        **Auto-save's hook waits** (:func:`hold_auto_save`): a layer added
        while this plans, asks or writes would otherwise be written into the
        same file at once. It is taken the hook's own way once this is done.
        """
        with hold_auto_save(), OperationErrors(GPKG_EXPORT, self.iface, absorb=True) as errors:
            prj = QgsProject.instance()

            gpkg_path = self._ask_where_to_save(prj)
            if not gpkg_path:
                return

            layers = [l for l in prj.mapLayers().values() if isinstance(l, QgsVectorLayer)]  # noqa: E741
            if not layers:
                self._remember_target(prj, gpkg_path)
                self.iface.messageBar().pushWarning(GPKG_EXPORT, "No vector layers to save.")
                return

            title = action_title(getattr(self.plugin, "action_save_gpkg", None), _tr(_SAVE_ALL_TITLE))
            plan = self._plan(prj, layers, gpkg_path, title, [f"layer_{index + 1}" for index in range(len(layers))])
            if plan is None:
                return
            styled = styled_tables(gpkg_path)
            moved = self._auto_save_moves(prj, gpkg_path)
            self._remember_target(prj, gpkg_path)

            saved = set()
            for index, layer in enumerate(layers):
                if layer.isEditable() and not check_commit(layer, errors):
                    # Not written and not repointed: see the docstring.
                    continue

                if index in plan.kept:
                    # Already living in this file, so the commit above IS the
                    # save. OGR refuses to overwrite a layer it has open
                    # ("Cannot overwrite an OGR layer in place"), which is why
                    # every second Save all used to warn once per layer while
                    # the data on disk was perfectly correct.
                    #
                    # The style is not re-saved here. It is already in the
                    # file's layer_styles table and nothing about it changed,
                    # and on QGIS 3.22 saveStyleToDatabase over an existing
                    # entry opens a MODAL prompt -- which in a headless or
                    # scripted run never gets an answer.
                    saved.add(index)
                    continue

                # The plan's name, from the file as it was read just before (and
                # again after the question). Nothing of FiberQ's can take one
                # meanwhile: auto-save's hook waits (hold_auto_save). Reading
                # the file's tables again before every layer cost Save all a read
                # of the file's whole schema per layer -- 2% against v1.5.0 at 24
                # layers, and growing with layers times tables -- for another
                # program writing the same file during the save, which it could
                # narrow and never close (the final benchmark's save_gpkg row).
                name = plan.tables[index]
                old = plan.offers.get(index) if plan.replace else None
                written = (self._write_over(layer, gpkg_path, name, old, errors) if old is not None
                           else self._write_layer(layer, gpkg_path, name, errors))
                if not written:
                    continue
                # Only once the write is in: a write that fails leaves the old
                # table's styles where they were (v1.6.0 QA Q18).
                if not self._clear_styles(layer, gpkg_path, name, errors, old is not None, styled):
                    continue
                if not self._repoint(layer, prj, f"{gpkg_path}|layername={name}", errors):
                    continue
                saved.add(index)

            prj.setDirty(True)

            # Phase 0.2: metadata table for Designer compatibility
            self._write_metadata(gpkg_path, errors)
            self._clean_stored_aliases(gpkg_path)

            moved_to = (safe_format(_tr(_AUTO_SAVE_MOVED), _AUTO_SAVE_MOVED, file=os.path.basename(gpkg_path))
                        if moved else None)
            names = [layer.name() for layer in layers]
            if not errors.failed:
                push_saved(self.iface.messageBar(), GPKG_EXPORT,
                           safe_format(_tr(_SAVED), _SAVED, file=os.path.basename(gpkg_path)),
                           plan, names, safe_format(_tr(_SAVED), _SAVED, file=gpkg_path), moved_to)
                return
            # Failed in part: no green line -- the collector says what failed
            # as it closes -- but where the saved layers went, and that
            # auto-save follows the file, are as true as they would have been.
            push_saved(self.iface.messageBar(), GPKG_EXPORT, None, plan, names, moved=moved_to, saved=saved)
            if saved:
                logger.warning(f"{len(saved)} of {len(layers)} layers reached {gpkg_path}")

    def _remember_target(self, project, gpkg_path):
        """Store ``gpkg_path`` as the project's GeoPackage, under both keys.

        Both on purpose. Projects saved by older versions, and older versions
        reading this one, know only the "TelecomPlugin" key; auto-save
        (ui/routing_ui.py) reads "FiberQPlugin" first and falls back to it.
        Written only once the user has said yes to the save: a Cancel leaves
        the project's entries alone.
        """
        for scope in ("FiberQPlugin", "TelecomPlugin"):
            try:
                project.writeEntry(scope, "gpkg_path", gpkg_path)
            except (AttributeError, RuntimeError) as exc:
                # Only the remembered path for next time; the export runs on.
                logger.warning(f"Could not store the GeoPackage path under {scope}: {exc}")

    def _auto_save_moves(self, project, gpkg_path):
        """True when auto-save is on and this save is about to point it at another file.

        Save all stores its file as the project's GeoPackage, which is the one
        auto-save writes new layers to: saved somewhere new, auto-save follows.
        Read before :meth:`_remember_target` writes the new path.
        """
        action = getattr(self.plugin, "action_auto_gpkg", None)
        if action is None or not action.isChecked():
            return False
        previous = project.readEntry("FiberQPlugin", "gpkg_path", "")[0]
        if not previous:
            previous = project.readEntry("TelecomPlugin", "gpkg_path", "")[0]
        return not same_file(previous, gpkg_path)

    def _plan(self, project, layers, gpkg_path, title, fallbacks, heading=GPKG_EXPORT):
        """Where each of ``layers`` goes in ``gpkg_path``: a ``gpkg_target.TablePlan``.

        A table that has a layer's name while no layer of ``project`` reads it
        is a question for the user (:func:`ask_about_unused_tables`), asked
        once, under ``title`` -- and only when the whole situation is
        understood, by gpkg_target's allow-list: the file, and how every layer
        of the project reads, of any kind -- another file by the GDAL driver
        that opens it (:func:`_identify`). Anything else, and each layer goes
        beside the tables of its name, as before the question existed.

        The answer comes after a wait, so the file and the project's layers are
        looked at again before anything is written (:meth:`_unchanged`):
        another program may have written to the file or replaced it, or a
        layer come or gone, while the question was open.

        None when the user cancels; when the file cannot be saved into or its
        tables cannot be read (:meth:`_target_contents`); and when the file or
        the project changed while the question was open -- each said by one
        warning under ``heading`` by then.
        """
        identity = file_identity(gpkg_path)
        contents = self._target_contents(gpkg_path, heading)
        if contents is None:
            return None
        state = _project_state(project)
        entries = [(layer.name(), layer.source(), fallback) for layer, fallback in zip(layers, fallbacks)]
        used = used_tables([_reader(each) for each in project.mapLayers().values()], gpkg_path, _identify)
        plan = plan_tables(entries, gpkg_path, used, False, contents)
        if not plan.offers:
            return plan
        answer = ask_about_unused_tables(self.iface.mainWindow(), title, gpkg_path, plan)
        if answer not in (REPLACE, KEEP):
            return None
        if not self._unchanged(project, gpkg_path, (identity, contents, state), heading):
            return None
        return plan_tables(entries, gpkg_path, used, True, contents) if answer == REPLACE else plan

    def _unchanged(self, project, gpkg_path, before, heading):
        """True when the file and the project are as ``before`` -- ``(identity, contents, layers)`` -- found them.

        Looked at once the user has answered, before the first write: the
        file's identity and its tables (``gpkg_target.file_identity``,
        ``read_contents``), and every layer's id, provider and source. False,
        once one warning under ``heading`` has said why, when anything differs
        or the file can no longer be read.
        """
        name = os.path.basename(os.path.normpath(gpkg_path))
        try:
            now = (file_identity(gpkg_path), read_contents(gpkg_path), _project_state(project))
        except sqlite3.Error as exc:
            text = safe_format(_tr(_TARGET_UNREADABLE), _TARGET_UNREADABLE, file=name, reason=describe(exc))
            changed = "the tables"
        else:
            if now == before:
                return True
            text = safe_format(_tr(_CHANGED_WHILE_ASKING), _CHANGED_WHILE_ASKING, file=name)
            changed = ", ".join(what for what, old, new in zip(("the file", "its tables", "the layers"), before, now)
                                if old != new)
        logger.warning(f"{text} ({gpkg_path}: {changed})")
        self.iface.messageBar().pushWarning(heading, text)
        return False

    def _target_contents(self, gpkg_path, heading):
        """What the GeoPackage at ``gpkg_path`` holds; None, once a warning has said why, when it cannot be used.

        A file that is there gets the pre-flight first (``gpkg_target_problem``):
        a read-only file, a folder or something that is not a GeoPackage is
        one sentence, not a question about its tables and then one failure per
        layer. Then its tables are read, and a file that cannot be read --
        another program holds it, or it is damaged -- stops the save: planned
        as empty, every name in it would look free, and the writer replaces a
        table whose name it is given. A file that is not there yet holds
        nothing; whether it can be made is each layer's own result, as before.
        """
        if not os.path.exists(gpkg_path):
            return NOTHING
        name = os.path.basename(os.path.normpath(gpkg_path))
        problem = gpkg_target_problem(gpkg_path)
        if problem is None:
            try:
                return read_contents(gpkg_path)
            except sqlite3.Error as exc:
                text = safe_format(_tr(_TARGET_UNREADABLE), _TARGET_UNREADABLE, file=name, reason=describe(exc))
        else:
            source = {"is_directory": _TARGET_FOLDER, "not_a_geopackage": _TARGET_NOT_GPKG}.get(
                problem, _TARGET_READ_ONLY)
            text = safe_format(_tr(source), source, file=name)
        logger.warning(f"{text} ({gpkg_path})")
        self.iface.messageBar().pushWarning(heading, text)
        return None

    def _ask_where_to_save(self, project):
        """The GeoPackage to write, from the user. Empty when they cancel.

        Without the file dialog's own "replace?": FiberQ writes into the file
        and never replaces it, so that question would misdescribe the save.
        Tables of the same names are FiberQ's question (:meth:`_plan`). A path
        whose ".." QGIS 3.22 would read as another file is resolved here
        (``gpkg_target.unambiguous``), so that the plan and every write meet
        in one file.
        """
        default_dir = os.path.dirname(project.fileName()) if project.fileName() else os.path.expanduser("~")
        gpkg_path, _ = save_file_name(
            self.iface.mainWindow(),
            "Select GeoPackage file",
            os.path.join(default_dir, "FiberQ_Project.gpkg"),
            "GeoPackage (*.gpkg)"
        )
        if not gpkg_path:
            return ""
        if not gpkg_path.lower().endswith(".gpkg"):
            gpkg_path += ".gpkg"
        return unambiguous(gpkg_path)

    def _clear_styles(self, layer, gpkg_path, table, errors, replacing=False, styled=None):
        """Remove the old ``layer_styles`` rows of ``table``, once it has been written.

        True when no row of it is left in the way. No GDAL removes them with
        the table it overwrites or deletes (3.4.1, 3.8.4, 3.10.3, 3.12.2,
        measured), so a replaced table's old styles would outlive it -- and
        QGIS 3.22's saveStyleToDatabase, meeting the old default, opens a modal
        "overwrite?" prompt that a scripted run never answers. Done for a table
        being replaced, and for a new name the file still holds rows for
        (``styled``, read once by the caller).

        Only after the write: a write that fails -- a foreign key, a full disk,
        an unavailable layer -- leaves the old styles where they were. A
        failure here is the layer's: its table is written, but it stays on its
        old source, and the message says it was not saved.
        """
        if not os.path.isfile(gpkg_path):
            return True
        if not replacing:
            styled = styled_tables(gpkg_path) if styled is None else styled
            if sqlite_fold(table) not in {sqlite_fold(name) for name in styled}:
                return True
        try:
            with closing(sqlite3.connect(gpkg_path, isolation_level=None)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                                    "AND name = 'layer_styles' COLLATE NOCASE").fetchone():
                        conn.execute("DELETE FROM layer_styles WHERE lower(f_table_name) = lower(?)", (table,))
                    conn.execute("COMMIT")
                except sqlite3.Error:
                    try:
                        conn.execute("ROLLBACK")
                    except sqlite3.Error as rollback_exc:
                        logger.warning(f"Could not roll back the style removal: {rollback_exc}")
                    raise
        except sqlite3.Error as exc:
            errors.add(layer.name(), safe_format(_tr(_STYLES_STAY), _STYLES_STAY, table=table, reason=describe(exc)))
            return False
        return True

    def _write_layer(self, layer, gpkg_path, name, errors):
        """Write one layer into the GeoPackage. True when it got there."""
        code, reason = self._run_writer(layer, gpkg_path, name)
        if code != QgsVectorFileWriter.WriterError.NoError:
            errors.add(layer.name(), reason or f"the writer returned {code}")
            return False
        return True

    def _write_over(self, layer, gpkg_path, name, old, errors):
        """Write ``layer`` as ``name`` over ``old``, a table the user chose to replace. True when it got there.

        The writer drops the old table before it writes a feature, so a write
        that fails part-way -- a full disk, a feature the new table refuses --
        can leave the old table gone, or a new one of its name holding part of
        the layer, while the layer stays on its old source. What is left is
        looked at and said, because "not saved" alone reads as "nothing
        changed". A write refused before the old table was touched (a foreign
        key into it, a file held open) leaves it as it was, and says only why.
        """
        before = self._table_state(gpkg_path, old)
        code, reason = self._run_writer(layer, gpkg_path, name)
        if code == QgsVectorFileWriter.WriterError.NoError:
            return True
        reason = reason or f"the writer returned {code}"
        after = self._table_state(gpkg_path, old)
        if before is None or before is _UNREAD or after is _UNREAD:
            source = None
        elif after is None:
            source = _OLD_TABLE_GONE
        elif after != before:
            source = _OLD_TABLE_PART
        else:
            source = None
        errors.add(layer.name(), safe_format(_tr(source), source, table=old, reason=reason) if source else reason)
        return False

    def _table_state(self, gpkg_path, table):
        """``gpkg_target.table_state``, or :data:`_UNREAD` when the file cannot be read."""
        try:
            return table_state(gpkg_path, table)
        except sqlite3.Error as exc:
            logger.warning(f"Could not look at table {table} of {gpkg_path}: {exc}")
            return _UNREAD

    def _run_writer(self, layer, gpkg_path, name):
        """``(code, reason)`` of writing ``layer`` into ``gpkg_path`` as table ``name``."""
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        opts.layerName = name
        opts.actionOnExistingFile = (
            QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
            if os.path.exists(gpkg_path)
            else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        )

        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, gpkg_path, QgsCoordinateTransformContext(), opts
        )
        return _writer_result(result)

    def _repoint(self, layer, project, uri, errors):
        """Point ``layer`` at its new home in the GeoPackage. True when it took.

        ``setDataSource`` does not raise and does not return anything: a URI it
        cannot open leaves the layer **invalid and silent**, which is why the
        validity check below is the whole point of this method rather than an
        afterthought.
        """
        try:
            layer.setDataSource(uri, layer.name(), "ogr")
        except (AttributeError, RuntimeError) as exc:
            logger.warning(f"setDataSource raised on {layer.name()}: {exc}")

        if not layer.isValid():
            if not self._replace_with_fresh_layer(layer, project, uri, errors):
                return False
        else:
            self._save_style(layer, errors)
        return True

    def _replace_with_fresh_layer(self, layer, project, uri, errors):
        """Last resort: build the layer again from the GeoPackage and swap it in.

        Reached only when ``setDataSource`` left the layer invalid. The data is
        in the GeoPackage by this point -- ``_write_layer`` said so -- so a
        fresh layer reading the same URI gives the user working data back
        instead of a broken entry in the legend.

        Two things have to be carried across, and the reason is that other parts
        of FiberQ key on them:

        * **The appearance**, captured before the swap. A fresh layer loads the
          GeoPackage's *default* style, and saving that back would overwrite the
          one the user set.
        * **The layer id.** Picture and drawing links
          (``FeatureLinks/images_v1``, holding ``{layer id: {fid: path}}``, plus
          the pre-1.6.0 ``image_map/<layer id>/<fid>`` keys the fallback still
          reads) and the relation and latent-element stores are all keyed by it,
          so a new id silently orphans every one of them.
          :meth:`QgsMapLayer.setId` arrived in QGIS 3.36; below that the id
          cannot be kept, and the message says so rather than letting the user
          discover it.
        """
        fresh = QgsVectorLayer(uri, layer.name(), "ogr")
        if not fresh.isValid():
            errors.add(layer.name(), "the layer could not be reopened from the GeoPackage")
            return False

        name = layer.name()
        old_id = layer.id()
        appearance = QgsMapLayerStyle()
        appearance.readFromLayer(layer)

        node = project.layerTreeRoot().findLayer(old_id)
        parent = node.parent() if node is not None else project.layerTreeRoot()

        project.removeMapLayer(old_id)
        kept_id = bool(getattr(fresh, "setId", None)) and fresh.setId(old_id)
        if appearance.isValid():
            appearance.writeToLayer(fresh)
        project.addMapLayer(fresh, False)
        parent.insertLayer(0, fresh)
        self._save_style(fresh, errors)

        if kept_id:
            # Reported even though it worked: the layer the user is looking at
            # is not the object it was, and a green-only message would hide that.
            logger.warning(f"{name} was rebuilt from the GeoPackage, keeping its id")
        else:
            errors.add(name, "the layer had to be rebuilt and could not keep its id, so any "
                             "pictures, drawings or relations attached to it need re-linking")
        return True

    def _save_style(self, layer, errors):
        """Store the layer's style in the GeoPackage, and say so if it will not."""
        try:
            problem = save_style_to_database(layer, "default", "auto-saved by FiberQ", True, "")
        except (AttributeError, RuntimeError) as exc:
            errors.add(layer.name(), exc)
            return
        if problem:
            # The style is cosmetic, the data is not: reported, never fatal.
            errors.add(layer.name(), f"the style was not saved ({problem})")

    def _clean_stored_aliases(self, gpkg_path):
        """Take the "Cable feature ID" FiberQ up to 1.5.0 gave ``fid`` out of the file's styles.

        v1.6.0 QA Q17: the alias now comes off a layer in the project, but the
        default style a GeoPackage already holds for a layer living in it is
        not written again, so QGIS without FiberQ still showed it. See
        ``utils.field_aliases.clear_wrong_fid_alias_in_styles``. Cosmetic: a
        file that refuses is logged, and the save goes on.
        """
        from ..utils.field_aliases import clear_wrong_fid_alias_in_styles

        changed, reason = clear_wrong_fid_alias_in_styles(gpkg_path)
        if reason:
            logger.warning(f"Could not take the old fid alias out of the styles in {gpkg_path}: {reason}")
        elif changed:
            logger.info(f"Took the old fid alias out of {changed} style(s) in {gpkg_path}")

    def _write_metadata(self, gpkg_path, errors):
        """Write the Designer metadata table, and report it when it will not go."""
        try:
            written, reason = self._write_metadata_table(gpkg_path)
        except (OSError, RuntimeError, ValueError) as exc:
            errors.add("_fiberq_metadata", exc)
            return
        if not written:
            errors.add("_fiberq_metadata", reason)

    def export_one_layer_to_gpkg(self, layer, gpkg_path, errors=None, table=None, replacing=False):
        """Write one layer into the GeoPackage and point it at its new home.

        This is the auto-save path: it runs once per layer when the user ticks
        the box, and again for every layer added afterwards. Each of those is a
        separate chance to fail, and each used to fail without a word.

        Args:
            layer: The layer to move into the GeoPackage.
            gpkg_path: The GeoPackage to move it into.
            errors: The :class:`~fiberq.utils.errors.OperationErrors` collecting
                this operation. Auto-save converts a whole project's worth of
                layers in one go and wants one message for all of them, so it
                passes its own collector; a lone caller gets one made here and
                reported on the way out.
            table: The table to write, from a plan the caller made
                (:func:`plan_gpkg_tables`). Without one, a name nothing in
                the file has claimed.
            replacing: The unused table the user chose to replace, as the
                file spells it, when ``table`` is written over it (True: it is
                ``table`` itself); False or None when it replaces nothing.

        Returns:
            True when the data reached the GeoPackage **and** the layer now
            reads from it. A layer that returns False is still readable from
            wherever it was before.
        """
        if errors is not None:
            return self._export_one_layer(layer, gpkg_path, errors, table, replacing)
        with OperationErrors(GPKG_EXPORT, self.iface) as own:
            return self._export_one_layer(layer, gpkg_path, own, table, replacing)

    def _export_one_layer(self, layer, gpkg_path, errors, table=None, replacing=False):
        """The body of :meth:`export_one_layer_to_gpkg`, given a collector."""
        if layer.isEditable() and not check_commit(layer, errors):
            # Uncommitted edits plus a repoint is how work disappears. R1's
            # docstring has the long version.
            return False

        # Not simply the flattened layer name: that is what used to aim a new
        # "Poles" at the table an older, since-renamed "Poles" still owned, and
        # overwrite it. The writer reported NoError while the features went.
        try:
            name = table or table_name_for(layer.name(), layer.source(), gpkg_path)
        except sqlite3.Error as exc:
            # The file is there and its tables cannot be read: as none, every
            # name in it would look free, and the writer replaces the table
            # whose name it is given.
            errors.add(layer.name(), exc)
            return False
        old = name if replacing is True else (replacing or None)
        written = (self._write_over(layer, gpkg_path, name, old, errors) if old
                   else self._write_layer(layer, gpkg_path, name, errors))
        if not written:
            return False
        # Only once the write is in: a failed one keeps the old styles.
        if not self._clear_styles(layer, gpkg_path, name, errors, bool(old)):
            return False
        if not self._repoint(layer, QgsProject.instance(), f"{gpkg_path}|layername={name}", errors):
            return False
        self._clean_stored_aliases(gpkg_path)
        return True

    # =========================================================================
    # PHASE 0.2: FIBERQ METADATA TABLE
    # =========================================================================

    def _project_entry(self, scope, key):
        """A project entry's value, "" when it has none, or None to say nothing.

        ``readEntry`` returns ``(value, found)``: a key that is absent gives
        ``("", False)`` and one deliberately set to empty gives ``("", True)``.
        Measured on 3.44 and 4.0.

        An absent entry normally means the user has none, and "" is written so
        the GeoPackage matches the project. The exception is a project this QGIS
        cannot read at all -- QGIS 3 opening a QGIS 4 project reports *every*
        entry absent -- where writing the empty default over the stored copy is
        how a display problem becomes data loss. There, and only there, None
        says "leave what is in the file alone".

        The distinction matters because two projects can share one GeoPackage.
        Keeping the stored copy whenever an entry was merely absent let a
        project that had never opened the relations dialog inherit the relations
        of the last project exported to the same file.
        """
        value, found = QgsProject.instance().readEntry(scope, key, "")
        if found:
            return value
        return None if self._project_is_unreadable() else ""

    def _project_is_unreadable(self):
        """True when this QGIS cannot read the current project's entries.

        Exactly one case today: a project written by QGIS 4 and opened in
        QGIS 3, which stores custom properties in a form QGIS 3 cannot parse.
        See :mod:`fiberq.core.project_compat`.
        """
        from ..utils.compat import QGIS_VERSION_INT
        from .project_compat import opened_a_newer_project

        try:
            saved_major = QgsProject.instance().lastSaveVersion().majorVersion()
        except (AttributeError, RuntimeError) as exc:
            # Unknown provenance: assume readable, which is what every version
            # before this one assumed.
            logger.warning(f"Could not read the version this project was saved with: {exc}")
            return False
        return opened_a_newer_project(saved_major, QGIS_VERSION_INT // 10000, True)

    def _collect_metadata(self):
        """
        Collect all FiberQ metadata from the current project.

        Entries the project does not have are **omitted**, not defaulted: see
        :meth:`_project_entry`. The writer deletes and re-inserts only the keys
        it is given, so an omitted key keeps whatever the GeoPackage holds.

        Returns:
            dict: Key-value pairs to store in _fiberq_metadata table
        """
        prj = QgsProject.instance()
        metadata = {}

        # 1. Schema version (canonical). project_version is kept in sync for
        # backward-compat of the metadata table; both now track SCHEMA_VERSION.
        metadata["schema_version"] = SCHEMA_VERSION
        metadata["project_version"] = SCHEMA_VERSION

        # 2. Relations data
        relations_raw = self._project_entry("StuboviPlugin", "Relacije/relations_v1")
        if relations_raw is not None:
            try:
                json.loads(relations_raw or "{}")
                metadata["relations_json"] = relations_raw or json.dumps({"relations": []})
            except ValueError as exc:
                # Stored but unreadable. Reporting it and keeping the
                # GeoPackage's copy beats replacing it with an empty one.
                logger.warning(f"The project's relations are not valid JSON, keeping the stored copy: {exc}")

        # 3. Latent elements data
        latent_raw = self._project_entry("StuboviPlugin", "LatentElements/latent_v1")
        if latent_raw is not None:
            try:
                json.loads(latent_raw or "{}")
                metadata["latent_elements_json"] = latent_raw or json.dumps({"cables": {}})
            except ValueError as exc:
                logger.warning(f"The project's latent elements are not valid JSON, keeping the stored copy: {exc}")

        # 4. Color standard (active color code standard name)
        color_raw = self._project_entry("StuboviPlugin", "ColorCatalogs/catalogs_v1")
        if color_raw is not None:
            try:
                catalogs = json.loads(color_raw or "{}").get("catalogs", []) if color_raw else []
                metadata["color_catalog_json"] = color_raw or json.dumps({"catalogs": []})
                names = [entry.get("name", "") for entry in catalogs if entry.get("name")]
                metadata["color_standard"] = names[0] if names else "TIA-598-C"
            except (ValueError, AttributeError) as exc:
                logger.warning(f"The project's colour catalogues are not readable, keeping the stored copy: {exc}")

        # 5. CRS EPSG code
        try:
            crs = prj.crs()
            if crs.isValid():
                authid = crs.authid()  # e.g. "EPSG:32634"
                epsg = authid.split(":")[-1] if ":" in authid else authid
                metadata["crs_epsg"] = epsg
            else:
                metadata["crs_epsg"] = ""
        except Exception as e:
            logger.debug(f"Error reading CRS for metadata: {e}")
            metadata["crs_epsg"] = ""

        # 6. Export timestamp (ISO 8601 UTC)
        metadata["export_timestamp"] = datetime.now(timezone.utc).isoformat()

        # 7. Plugin settings (relevant config.ini values)
        try:
            import configparser
            cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.ini")
            settings = {}
            if os.path.isfile(cfg_path):
                cfg = configparser.ConfigParser(interpolation=None)
                cfg.read(cfg_path, encoding="utf-8")
                # Only export relevant non-sensitive sections
                for section in cfg.sections():
                    if section in ("postgis",):
                        # Skip database credentials
                        continue
                    settings[section] = dict(cfg[section])
            metadata["plugin_settings_json"] = json.dumps(settings)
        except Exception as e:
            logger.debug(f"Error reading plugin settings for metadata: {e}")
            metadata["plugin_settings_json"] = json.dumps({})

        return metadata

    def _write_metadata_table(self, gpkg_path):
        """
        Write the _fiberq_metadata non-spatial table into a GeoPackage.

        Creates the table when it is absent, with two columns:
            key   TEXT PRIMARY KEY
            value TEXT

        and otherwise keeps the one already in the file. It no longer *replaces*
        the table: replacing it is what used to leave it present, registered and
        EMPTY whenever anything interrupted the write, because the DROP and
        CREATE were durable before the first row was ever inserted. Only the
        keys this plugin computed are rewritten; a key another tool put there is
        left alone, and how many were left is logged.

        Each row stores one metadata key-value pair for FiberQ Designer.

        Args:
            gpkg_path: Path to the GeoPackage file

        Returns:
            ``(written, reason)``. ``reason`` is empty on success and carries
            sqlite's own words otherwise -- those words are usually the only
            account of why ("database is locked", "attempt to write a readonly
            database"), and they used to go to the debug log, which in a default
            install means nowhere.

        A failure to register the table in ``gpkg_contents`` counts as a
        failure. GDAL lists only what is registered there, so an unregistered
        table is one FiberQ Designer cannot see -- which is the entire purpose
        of writing it.
        """
        import sqlite3
        from contextlib import closing

        if not os.path.isfile(gpkg_path):
            return False, f"the GeoPackage is not there: {gpkg_path}"

        metadata = self._collect_metadata()

        # WP1a: also stamp the in-memory project so the schema version lives in
        # the .qgs project too (the metadata table below carries it in the GPKG).
        try:
            mark_project_current()
        except (AttributeError, RuntimeError) as exc:
            # The GeoPackage copy below is the one Designer reads, so this is
            # worth saying but not worth failing the export over.
            logger.warning(f"Could not stamp the project schema version: {exc}")

        kept = 0
        try:
            # isolation_level=None puts the transaction in our hands. The
            # sqlite3 module's legacy mode runs DDL outside any transaction,
            # which is what made the old DROP durable the instant it ran.
            with closing(sqlite3.connect(gpkg_path, isolation_level=None)) as conn:
                # IMMEDIATE takes the write lock now rather than at COMMIT, so a
                # GeoPackage another program is holding open fails here, before
                # anything in the file has been touched.
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS _fiberq_metadata "
                        "(key TEXT PRIMARY KEY, value TEXT)")
                    present = {str(row[0]) for row in
                               conn.execute("SELECT key FROM _fiberq_metadata")}

                    # Register in gpkg_contents so QGIS/GDAL recognizes it as an
                    # attributes table.
                    conn.execute("""
                        INSERT OR REPLACE INTO gpkg_contents (
                            table_name, data_type, identifier, description,
                            last_change, srs_id
                        ) VALUES (
                            '_fiberq_metadata', 'attributes', '_fiberq_metadata',
                            'FiberQ Designer metadata (relations, latent elements, color catalogs, project settings)',
                            ?, 0
                        )
                    """, (metadata.get("export_timestamp", datetime.now(timezone.utc).isoformat()),))

                    # Delete-then-insert rather than INSERT OR REPLACE: a table
                    # some other tool created may have no primary key on `key`,
                    # and INSERT OR REPLACE would then quietly add a second row
                    # for the same key instead of replacing the first. This
                    # shape repairs such a table as it writes.
                    for key, value in metadata.items():
                        conn.execute("DELETE FROM _fiberq_metadata WHERE key = ?", (key,))
                        conn.execute(
                            "INSERT INTO _fiberq_metadata (key, value) VALUES (?, ?)",
                            (key, value))

                    conn.execute("COMMIT")
                except sqlite3.Error:
                    try:
                        conn.execute("ROLLBACK")
                    except sqlite3.Error as rollback_exc:
                        logger.warning(
                            f"Could not roll back the metadata write: {rollback_exc}")
                    raise
                kept = len(present - set(metadata))
        except sqlite3.Error as exc:
            return False, describe(exc)

        also_kept = f", keeping {kept} written by another tool" if kept else ""
        logger.debug(
            f"Wrote {len(metadata)} metadata entries to _fiberq_metadata "
            f"in {gpkg_path}{also_kept}")
        return True, ""


# Module-level convenience function
def get_export_manager(iface, plugin=None):
    """Get an ExportManager instance."""
    return ExportManager(iface, plugin)


# Standalone functions for backward compatibility
def save_all_layers_to_gpkg(iface, plugin=None):
    """Save all layers to GeoPackage (standalone function).

    ``plugin`` is how the save learns whether auto-save is on, to say so when
    the save moves auto-save to another file.
    """
    em = ExportManager(iface, plugin)
    em.save_all_layers_to_gpkg()


def export_one_layer_to_gpkg(layer, gpkg_path, iface, errors=None, table=None, replacing=False):
    """Export one layer to GeoPackage (standalone function)."""
    em = ExportManager(iface)
    return em.export_one_layer_to_gpkg(layer, gpkg_path, errors, table, replacing)


def plan_gpkg_tables(layers, gpkg_path, iface, title, heading=GPKG_EXPORT):
    """Where ``layers`` go in ``gpkg_path``, asking about unused tables first.

    See :meth:`ExportManager._plan`: None on Cancel, when the file cannot be
    saved into, and when it or the project changed while the question was
    open, which a warning under ``heading`` has said. The fallback name of a
    layer whose name flattens to nothing is "layer", as for
    :func:`export_one_layer_to_gpkg`.
    """
    em = ExportManager(iface)
    return em._plan(QgsProject.instance(), layers, gpkg_path, title, ["layer"] * len(layers), heading)


def export_planned_layers(layers, gpkg_path, iface, errors, plan):
    """Write auto-save's ``layers`` where ``plan`` puts them; the indexes of the layers saved.

    Each as :func:`export_one_layer_to_gpkg` writes one, under the plan's
    name for it, as Save all does (see there why a name is not looked up
    again before each write).
    """
    em = ExportManager(iface)
    saved = set()
    for index, layer in enumerate(layers):
        table = plan.tables[index]
        replacing = plan.offers.get(index) if plan.replace else None
        if em._export_one_layer(layer, gpkg_path, errors, table, replacing):
            saved.add(index)
    return saved


__all__ = [
    'ExportManager',
    'KEEP',
    'REPLACE',
    'action_title',
    'ask_about_unused_tables',
    'auto_save_held',
    'defer_auto_save',
    'export_planned_layers',
    'get_export_manager',
    'hold_auto_save',
    'plan_gpkg_tables',
    'push_saved',
    'save_all_layers_to_gpkg',
    'saved_report',
    'export_one_layer_to_gpkg',
    'unused_tables_question',
]
