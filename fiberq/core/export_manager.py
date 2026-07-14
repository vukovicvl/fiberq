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
import re
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
from ..utils.logger import get_logger
logger = get_logger(__name__)


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
        """
        Export all vector layers to a single GeoPackage and redirect sources.
        """
        try:
            prj = QgsProject.instance()

            # Get save path
            default_dir = os.path.dirname(prj.fileName()) if prj.fileName() else os.path.expanduser("~")
            gpkg_path, _ = QFileDialog.getSaveFileName(
                self.iface.mainWindow(),
                "Select GeoPackage file",
                os.path.join(default_dir, "FiberQ_Project.gpkg"),
                "GeoPackage (*.gpkg)"
            )
            if not gpkg_path:
                return
            if not gpkg_path.lower().endswith(".gpkg"):
                gpkg_path += ".gpkg"

            # Store path in project
            try:
                prj.writeEntry("FiberQPlugin", "gpkg_path", gpkg_path)
            except Exception as e:
                logger.debug(f"Error in ExportManager.save_all_layers_to_gpkg: {e}")

            # Get all vector layers
            layers = [l for l in prj.mapLayers().values() if isinstance(l, QgsVectorLayer)]  # noqa: E741
            if not layers:
                self.iface.messageBar().pushWarning("GPKG export", "No vector layers to save.")
                return

            # Commit any pending edits
            for lyr in layers:
                try:
                    if lyr.isEditable():
                        lyr.commitChanges()
                except Exception as e:
                    logger.debug(f"Error in ExportManager.save_all_layers_to_gpkg: {e}")

            used = set()
            errors = []

            for idx, lyr in enumerate(layers):
                # Generate unique layer name
                base = re.sub(r"[^A-Za-z0-9_]+", "_", lyr.name()).strip("_") or f"layer_{idx + 1}"
                name = base
                c = 1
                while name in used:
                    c += 1
                    name = f"{base}_{c}"
                used.add(name)

                # Export layer
                opts = QgsVectorFileWriter.SaveVectorOptions()
                opts.driverName = "GPKG"
                opts.layerName = name
                opts.actionOnExistingFile = (
                    QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                    if os.path.exists(gpkg_path)
                    else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
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

                if err_code != QgsVectorFileWriter.WriterError.NoError:
                    errors.append(f"{lyr.name()}: {err_msg}")
                    continue

                # Redirect layer source to GPKG
                uri = f"{gpkg_path}|layername={name}"
                try:
                    lyr.setDataSource(uri, lyr.name(), "ogr")
                    try:
                        lyr.saveStyleToDatabase("default", "auto-saved by FiberQ", True, "")
                    except Exception as e:
                        logger.debug(f"Error in ExportManager.save_all_layers_to_gpkg: {e}")
                except Exception:
                    # Fallback: add new layer
                    new_lyr = QgsVectorLayer(uri, lyr.name(), "ogr")
                    if new_lyr and new_lyr.isValid():
                        parent = prj.layerTreeRoot().findLayer(lyr.id()).parent()
                        prj.removeMapLayer(lyr.id())
                        prj.addMapLayer(new_lyr, False)
                        parent.insertLayer(0, new_lyr)
                        try:
                            new_lyr.saveStyleToDatabase("default", "auto-saved by FiberQ", True, "")
                        except Exception as e:
                            logger.debug(f"Error in ExportManager.save_all_layers_to_gpkg: {e}")
                    else:
                        errors.append(f"{lyr.name()}: Failed to reload from GPKG")

            prj.setDirty(True)

            # Phase 0.2: Write metadata table for Designer compatibility
            try:
                meta_ok = self._write_metadata_table(gpkg_path)
                if meta_ok:
                    logger.debug("FiberQ metadata table written to GPKG")
                else:
                    errors.append("_fiberq_metadata: Failed to write metadata table")
            except Exception as e:
                errors.append(f"_fiberq_metadata: {e}")
                logger.debug(f"Error writing metadata table: {e}")

            if errors:
                self.iface.messageBar().pushWarning(
                    "GPKG export",
                    "Completed with errors:\n" + "\n".join(errors)
                )
            else:
                self.iface.messageBar().pushSuccess(
                    "GPKG export",
                    f"All layers saved to:\n{gpkg_path}"
                )
        except Exception as e:
            try:
                self.iface.messageBar().pushCritical("GPKG export", f"Unexpected error: {e}")
            except Exception as e:
                logger.debug(f"Error in ExportManager.save_all_layers_to_gpkg: {e}")

    def export_one_layer_to_gpkg(self, layer, gpkg_path):
        """
        Export a single layer to GeoPackage and redirect its source.

        Args:
            layer: Layer to export
            gpkg_path: GeoPackage file path

        Returns:
            bool: True if successful
        """
        base = re.sub(r"[^A-Za-z0-9_]+", "_", layer.name()).strip("_") or "layer"
        name = base

        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        opts.layerName = name
        opts.actionOnExistingFile = (
            QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
            if os.path.exists(gpkg_path)
            else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        )

        try:
            if layer.isEditable():
                layer.commitChanges()
        except Exception as e:
            logger.debug(f"Error in ExportManager.export_one_layer_to_gpkg: {e}")

        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, gpkg_path, QgsCoordinateTransformContext(), opts
        )

        if isinstance(result, tuple):
            err_code = result[0]
            err_msg = result[1] if len(result) > 1 else ""
        else:
            err_code = result
            err_msg = ""

        if err_code != QgsVectorFileWriter.WriterError.NoError:
            try:
                self.iface.messageBar().pushWarning(
                    "GPKG export",
                    f"Error exporting {layer.name()}: {err_msg}"
                )
            except Exception as e:
                logger.debug(f"Error in ExportManager.export_one_layer_to_gpkg: {e}")
            return False

        # Redirect source
        uri = f"{gpkg_path}|layername={name}"
        try:
            layer.setDataSource(uri, layer.name(), "ogr")
            try:
                layer.saveStyleToDatabase("default", "auto-saved by FiberQ", True, "")
            except Exception as e:
                logger.debug(f"Error in ExportManager.export_one_layer_to_gpkg: {e}")
            return True
        except Exception:
            return False

    # =========================================================================
    # PHASE 0.2: FIBERQ METADATA TABLE
    # =========================================================================

    def _collect_metadata(self):
        """
        Collect all FiberQ metadata from the current project.

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
        try:
            relations_raw = prj.readEntry("StuboviPlugin", "Relacije/relations_v1", "")[0]
            if relations_raw:
                # Validate it's valid JSON
                json.loads(relations_raw)
                metadata["relations_json"] = relations_raw
            else:
                metadata["relations_json"] = json.dumps({"relations": []})
        except Exception as e:
            logger.debug(f"Error reading relations for metadata: {e}")
            metadata["relations_json"] = json.dumps({"relations": []})

        # 3. Latent elements data
        try:
            latent_raw = prj.readEntry("StuboviPlugin", "LatentElements/latent_v1", "")[0]
            if latent_raw:
                json.loads(latent_raw)
                metadata["latent_elements_json"] = latent_raw
            else:
                metadata["latent_elements_json"] = json.dumps({"cables": {}})
        except Exception as e:
            logger.debug(f"Error reading latent elements for metadata: {e}")
            metadata["latent_elements_json"] = json.dumps({"cables": {}})

        # 4. Color standard (active color code standard name)
        try:
            color_raw = prj.readEntry("StuboviPlugin", "ColorCatalogs/catalogs_v1", "")[0]
            if color_raw:
                color_obj = json.loads(color_raw)
                catalogs = color_obj.get("catalogs", [])
                # Store the full catalog data
                metadata["color_catalog_json"] = color_raw
                # Extract first catalog name as "active" standard
                if catalogs:
                    names = [c.get("name", "") for c in catalogs if c.get("name")]
                    metadata["color_standard"] = names[0] if names else "TIA-598-C"
                else:
                    metadata["color_standard"] = "TIA-598-C"
            else:
                metadata["color_standard"] = "TIA-598-C"
                metadata["color_catalog_json"] = json.dumps({"catalogs": []})
        except Exception as e:
            logger.debug(f"Error reading color catalogs for metadata: {e}")
            metadata["color_standard"] = "TIA-598-C"
            metadata["color_catalog_json"] = json.dumps({"catalogs": []})

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
                cfg = configparser.ConfigParser()
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
            bool: True if successful
        """
        import sqlite3

        if not os.path.isfile(gpkg_path):
            logger.debug(f"_write_metadata_table: GPKG not found at {gpkg_path}")
            return False

        metadata = self._collect_metadata()

        # WP1a: also stamp the in-memory project so the schema version lives in
        # the .qgs project too (the metadata table below carries it in the GPKG).
        try:
            mark_project_current()
        except Exception as e:
            logger.debug(f"Could not stamp project schema version: {e}")

        try:
            conn = sqlite3.connect(gpkg_path)
            cur = conn.cursor()

            # Drop existing metadata table if present
            cur.execute("DROP TABLE IF EXISTS _fiberq_metadata")

            # Create the metadata table
            cur.execute("""
                CREATE TABLE _fiberq_metadata (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Register in gpkg_contents so QGIS/GDAL recognizes it as an attributes table
            try:
                cur.execute("""
                    INSERT OR REPLACE INTO gpkg_contents (
                        table_name, data_type, identifier, description,
                        last_change, srs_id
                    ) VALUES (
                        '_fiberq_metadata', 'attributes', '_fiberq_metadata',
                        'FiberQ Designer metadata (relations, latent elements, color catalogs, project settings)',
                        ?, 0
                    )
                """, (metadata.get("export_timestamp", datetime.now(timezone.utc).isoformat()),))
            except Exception as e:
                # gpkg_contents might not exist for some GPKG files — not fatal
                logger.debug(f"Could not register in gpkg_contents: {e}")

            # Insert all metadata key-value pairs
            for key, value in metadata.items():
                cur.execute(
                    "INSERT INTO _fiberq_metadata (key, value) VALUES (?, ?)",
                    (key, value)
                )

            conn.commit()
            conn.close()

            logger.debug(f"Wrote {len(metadata)} metadata entries to _fiberq_metadata in {gpkg_path}")
            return True
        except Exception as e:
            logger.debug(f"Error writing metadata table: {e}")
            try:
                conn.close()
            except Exception as e:
                logger.debug(f"Could not close GPKG connection after error: {e}")
            return False


# Module-level convenience function
def get_export_manager(iface, plugin=None):
    """Get an ExportManager instance."""
    return ExportManager(iface, plugin)


# Standalone functions for backward compatibility
def save_all_layers_to_gpkg(iface):
    """Save all layers to GeoPackage (standalone function)."""
    em = ExportManager(iface)
    em.save_all_layers_to_gpkg()


def export_one_layer_to_gpkg(layer, gpkg_path, iface):
    """Export one layer to GeoPackage (standalone function)."""
    em = ExportManager(iface)
    return em.export_one_layer_to_gpkg(layer, gpkg_path)


__all__ = [
    'ExportManager',
    'get_export_manager',
    'save_all_layers_to_gpkg',
    'export_one_layer_to_gpkg',
]
