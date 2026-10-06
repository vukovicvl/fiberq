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
from datetime import datetime, timezone

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsVectorFileWriter,
    QgsCoordinateTransformContext, QgsCoordinateReferenceSystem,
)
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QInputDialog

# WP1a: canonical schema version + project marker
from ..models.schema import SCHEMA_VERSION
from .schema_version import mark_project_current

# Phase 5.2: Logging
from ..utils.errors import OperationErrors, check_commit, describe
from ..utils.logger import get_logger
from .gpkg_target import table_in_use, table_name_for
logger = get_logger(__name__)

#: Title on every message-bar entry this module pushes. Kept as it has always
#: read, so a user who has seen it before still recognises it.
GPKG_EXPORT = "GPKG export"


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
            scope_txt = "selected features" if only_selected else "all features"
            QMessageBox.information(
                self.iface.mainWindow(),
                "Export",
                f"Successfully exported {scope_txt} from layer '{layer.name()}'\n"
                f"to:\n{filename}"
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
        """
        with OperationErrors(GPKG_EXPORT, self.iface, absorb=True) as errors:
            prj = QgsProject.instance()

            gpkg_path = self._ask_where_to_save(prj)
            if not gpkg_path:
                return

            # Both keys on purpose. The auto-save checkbox reads the older
            # "TelecomPlugin" one (ui/routing_ui.py), and the inline duplicate
            # deleted with this change was the only other thing writing it --
            # so dropping it here would quietly stop Save all from seeding the
            # path that auto-save then offers. U6 teaches the reader to try the
            # FiberQ key first; until then both are written, and a project saved
            # by this version still opens correctly in an older one.
            for scope in ("FiberQPlugin", "TelecomPlugin"):
                try:
                    prj.writeEntry(scope, "gpkg_path", gpkg_path)
                except (AttributeError, RuntimeError) as exc:
                    # Only the remembered path for next time; the export runs on.
                    logger.warning(f"Could not store the GeoPackage path under {scope}: {exc}")

            layers = [l for l in prj.mapLayers().values() if isinstance(l, QgsVectorLayer)]  # noqa: E741
            if not layers:
                self.iface.messageBar().pushWarning(GPKG_EXPORT, "No vector layers to save.")
                return

            used = set()
            saved = 0
            for index, layer in enumerate(layers):
                if layer.isEditable() and not check_commit(layer, errors):
                    # Not written and not repointed: see the docstring.
                    continue

                name = table_name_for(layer.name(), layer.source(), gpkg_path,
                                      f"layer_{index + 1}", used)
                used.add(name)

                if table_in_use(layer.source(), gpkg_path) == name:
                    # Already living in this file, so the commit above IS the
                    # save. OGR refuses to overwrite a layer it has open
                    # ("Cannot overwrite an OGR layer in place"), which is why
                    # every second Save all used to warn once per layer while
                    # the data on disk was perfectly correct.
                    self._save_style(layer, errors)
                    saved += 1
                    continue

                if not self._write_layer(layer, gpkg_path, name, errors):
                    continue
                if not self._repoint(layer, prj, f"{gpkg_path}|layername={name}", errors):
                    continue
                saved += 1

            prj.setDirty(True)

            # Phase 0.2: metadata table for Designer compatibility
            self._write_metadata(gpkg_path, errors)

            if not errors.failed:
                self.iface.messageBar().pushSuccess(
                    GPKG_EXPORT, f"All layers saved to:\n{gpkg_path}")
            elif saved:
                logger.warning(f"{saved} of {len(layers)} layers reached {gpkg_path}")

    def _ask_where_to_save(self, project):
        """The GeoPackage to write, from the user. Empty when they cancel."""
        default_dir = os.path.dirname(project.fileName()) if project.fileName() else os.path.expanduser("~")
        gpkg_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Select GeoPackage file",
            os.path.join(default_dir, "FiberQ_Project.gpkg"),
            "GeoPackage (*.gpkg)"
        )
        if not gpkg_path:
            return ""
        if not gpkg_path.lower().endswith(".gpkg"):
            gpkg_path += ".gpkg"
        return gpkg_path

    def _write_layer(self, layer, gpkg_path, name, errors):
        """Write one layer into the GeoPackage. True when it got there."""
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
        code, reason = _writer_result(result)
        if code != QgsVectorFileWriter.WriterError.NoError:
            errors.add(layer.name(), reason or f"the writer returned {code}")
            return False
        return True

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
        """Last resort: build the layer again from the GeoPackage and swap it in."""
        fresh = QgsVectorLayer(uri, layer.name(), "ogr")
        if not fresh.isValid():
            errors.add(layer.name(), "the layer could not be reopened from the GeoPackage")
            return False

        node = project.layerTreeRoot().findLayer(layer.id())
        parent = node.parent() if node is not None else project.layerTreeRoot()
        project.removeMapLayer(layer.id())
        project.addMapLayer(fresh, False)
        parent.insertLayer(0, fresh)
        self._save_style(fresh, errors)
        return True

    def _save_style(self, layer, errors):
        """Store the layer's style in the GeoPackage, and say so if it will not."""
        try:
            problem = layer.saveStyleToDatabase("default", "auto-saved by FiberQ", True, "")
        except (AttributeError, RuntimeError) as exc:
            errors.add(layer.name(), exc)
            return
        if problem:
            # The style is cosmetic, the data is not: reported, never fatal.
            errors.add(layer.name(), f"the style was not saved ({problem})")

    def _write_metadata(self, gpkg_path, errors):
        """Write the Designer metadata table, and report it when it will not go."""
        try:
            written, reason = self._write_metadata_table(gpkg_path)
        except (OSError, RuntimeError, ValueError) as exc:
            errors.add("_fiberq_metadata", exc)
            return
        if not written:
            errors.add("_fiberq_metadata", reason)

    def export_one_layer_to_gpkg(self, layer, gpkg_path, errors=None):
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

        Returns:
            True when the data reached the GeoPackage **and** the layer now
            reads from it. A layer that returns False is still readable from
            wherever it was before.
        """
        if errors is not None:
            return self._export_one_layer(layer, gpkg_path, errors)
        with OperationErrors(GPKG_EXPORT, self.iface) as own:
            return self._export_one_layer(layer, gpkg_path, own)

    def _export_one_layer(self, layer, gpkg_path, errors):
        """The body of :meth:`export_one_layer_to_gpkg`, given a collector."""
        if layer.isEditable() and not check_commit(layer, errors):
            # Uncommitted edits plus a repoint is how work disappears. R1's
            # docstring has the long version.
            return False

        # Not simply the flattened layer name: that is what used to aim a new
        # "Poles" at the table an older, since-renamed "Poles" still owned, and
        # overwrite it. The writer reported NoError while the features went.
        name = table_name_for(layer.name(), layer.source(), gpkg_path)
        if not self._write_layer(layer, gpkg_path, name, errors):
            return False
        return self._repoint(layer, QgsProject.instance(), f"{gpkg_path}|layername={name}", errors)

    # =========================================================================
    # PHASE 0.2: FIBERQ METADATA TABLE
    # =========================================================================

    @staticmethod
    def _project_entry(scope, key):
        """A project entry's value, or None when the project does not have it.

        None and "" are different answers and the difference matters here.
        ``readEntry`` returns ``(value, found)``; a key that is absent gives
        ``("", False)`` and a key deliberately set to empty gives ``("", True)``.
        Measured on 3.44 and 4.0.

        A QGIS 4 project opened in QGIS 3 reports every entry absent, because
        QGIS 3 cannot read the newer properties format at all. Writing the empty
        default over the GeoPackage's good copy in that situation is how a
        display problem becomes data loss -- so an absent entry is omitted and
        whatever the GeoPackage already holds is left alone.
        """
        value, found = QgsProject.instance().readEntry(scope, key, "")
        return value if found else None

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

        Creates (or replaces) a table with two columns:
            key   TEXT PRIMARY KEY
            value TEXT

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
def save_all_layers_to_gpkg(iface):
    """Save all layers to GeoPackage (standalone function)."""
    em = ExportManager(iface)
    em.save_all_layers_to_gpkg()


def export_one_layer_to_gpkg(layer, gpkg_path, iface, errors=None):
    """Export one layer to GeoPackage (standalone function)."""
    em = ExportManager(iface)
    return em.export_one_layer_to_gpkg(layer, gpkg_path, errors)


__all__ = [
    'ExportManager',
    'get_export_manager',
    'save_all_layers_to_gpkg',
    'export_one_layer_to_gpkg',
]
