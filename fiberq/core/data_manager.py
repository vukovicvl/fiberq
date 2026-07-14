"""
FiberQ v2 - Data Manager

This module centralizes all data management operations including:
- Relations storage (cable-element associations)
- Latent elements storage (pass-through elements)
- Color catalogs management
- Project data persistence
- GPKG metadata import/export for FiberQ Designer (Phase 0.2)

Phase 8 of the modular refactoring.
"""

import json
import os
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes

# WP1a: schema version marker
from .schema_version import write_project_schema_version

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class DataManager:
    """
    Centralized data management for FiberQ plugin.

    Handles persistent storage of relations, latent elements,
    and color catalogs within QGIS projects.
    """

    # Storage keys
    RELATIONS_KEY = "Relacije/relations_v1"
    LATENT_KEY = "LatentElements/latent_v1"
    COLOR_CATALOGS_KEY = "ColorCatalogs/catalogs_v1"
    PLUGIN_NAMESPACE = "StuboviPlugin"

    def __init__(self, iface=None, plugin=None):
        """
        Initialize the data manager.

        Args:
            iface: QGIS interface instance (optional)
            plugin: Reference to main plugin (optional)
        """
        self.iface = iface
        self.plugin = plugin

    # =========================================================================
    # RELATIONS MANAGEMENT
    # =========================================================================

    def load_relations(self):
        """
        Load relations data from project storage.

        Returns:
            dict: Relations data with 'relations' list
        """
        s = QgsProject.instance().readEntry(
            self.PLUGIN_NAMESPACE, self.RELATIONS_KEY, ''
        )[0]
        if not s:
            return {"relations": []}
        try:
            return json.loads(s)
        except Exception:
            return {"relations": []}

    def save_relations(self, data):
        """
        Save relations data to project storage.

        Args:
            data: dict with 'relations' list
        """
        try:
            QgsProject.instance().writeEntry(
                self.PLUGIN_NAMESPACE,
                self.RELATIONS_KEY,
                json.dumps(data)
            )
        except Exception as e:
            logger.debug(f"Error in DataManager.save_relations: {e}")

    def get_relation_by_id(self, data, relation_id):
        """
        Find a relation by its ID.

        Args:
            data: Relations data dict
            relation_id: Relation ID to find

        Returns:
            dict or None: The relation if found
        """
        for r in data.get("relations", []):
            if r.get("id") == relation_id:
                return r
        return None

    def get_relation_name_by_cable(self):
        """
        Build mapping from cable to relation name.

        Returns:
            dict: {(layer_id, fid) -> relation_name}
        """
        data = self.load_relations()
        out = {}
        for r in data.get("relations", []):
            name = r.get("name", "")
            for c in r.get("cables", []):
                key = (c.get("layer_id"), int(c.get("fid")))
                out[key] = name
        return out

    # =========================================================================
    # LATENT ELEMENTS MANAGEMENT
    # =========================================================================

    def load_latent(self):
        """
        Load latent elements data from project storage.

        Returns:
            dict: Latent elements data with 'cables' dict
        """
        s = QgsProject.instance().readEntry(
            self.PLUGIN_NAMESPACE, self.LATENT_KEY, ''
        )[0]
        if not s:
            return {"cables": {}}
        try:
            return json.loads(s)
        except Exception:
            return {"cables": {}}

    def save_latent(self, data):
        """
        Save latent elements data to project storage.

        Args:
            data: dict with 'cables' dict
        """
        try:
            QgsProject.instance().writeEntry(
                self.PLUGIN_NAMESPACE,
                self.LATENT_KEY,
                json.dumps(data)
            )
        except Exception as e:
            logger.debug(f"Error in DataManager.save_latent: {e}")

    @staticmethod
    def cable_key(layer_id, fid):
        """
        Generate a unique key for a cable feature.

        Args:
            layer_id: Layer ID string
            fid: Feature ID

        Returns:
            str: Unique cable key
        """
        return f"{layer_id}:{int(fid)}"

    # =========================================================================
    # COLOR CATALOGS MANAGEMENT
    # =========================================================================

    def get_default_color_sets(self):
        """
        Get default fiber color standards.

        Returns:
            list: Default color catalogs (TIA-598-C)
        """
        std12 = [
            ("Blue", "#1f77b4"),
            ("Orange", "#ff7f0e"),
            ("Green", "#2ca02c"),
            ("Brown", "#8c564b"),
            ("Slate", "#7f7f7f"),
            ("White", "#ffffff"),
            ("Red", "#d62728"),
            ("Black", "#000000"),
            ("Yellow", "#bcbd22"),
            ("Violet", "#9467bd"),
            ("Pink", "#e377c2"),
            ("Aqua", "#17becf"),
        ]
        return [
            {"name": "TIA-598-C", "colors": [{"name": n, "hex": h} for n, h in std12]},
        ]

    def load_color_catalogs(self):
        """
        Load color catalogs from project storage.

        Returns:
            dict: Color catalogs data with 'catalogs' list
        """
        s = QgsProject.instance().readEntry(
            self.PLUGIN_NAMESPACE, self.COLOR_CATALOGS_KEY, ''
        )[0]
        if not s:
            return {"catalogs": self.get_default_color_sets()}
        try:
            obj = json.loads(s)
            if not isinstance(obj, dict) or "catalogs" not in obj:
                obj = {"catalogs": self.get_default_color_sets()}
            return obj
        except Exception:
            return {"catalogs": self.get_default_color_sets()}

    def save_color_catalogs(self, data):
        """
        Save color catalogs to project storage.

        Args:
            data: dict with 'catalogs' list
        """
        try:
            QgsProject.instance().writeEntry(
                self.PLUGIN_NAMESPACE,
                self.COLOR_CATALOGS_KEY,
                json.dumps(data)
            )
        except Exception as e:
            logger.debug(f"Error in DataManager.save_color_catalogs: {e}")

    def list_color_codes(self):
        """
        Get list of available color catalog names.

        Returns:
            list: Color catalog names
        """
        data = self.load_color_catalogs()
        names = [c.get("name", "") for c in data.get("catalogs", []) if c.get("name")]
        # Ensure base standards are included
        base = ["ANSI/EIA/TIA-598-A", "IEC 60793-2-50", "ITU-T (generički)"]
        for b in base:
            if b not in names:
                names.append(b)
        return names

    # =========================================================================
    # PHASE 0.2: GPKG METADATA IMPORT (FiberQ Designer round-trip)
    # =========================================================================

    @staticmethod
    def read_metadata_from_gpkg(gpkg_path):
        """
        Read the _fiberq_metadata table from a GeoPackage.

        Args:
            gpkg_path: Path to the GeoPackage file

        Returns:
            dict: Key-value metadata pairs, or empty dict if table not found
        """
        import sqlite3

        if not os.path.isfile(gpkg_path):
            return {}

        try:
            conn = sqlite3.connect(gpkg_path)
            cur = conn.cursor()

            # Check if table exists
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='_fiberq_metadata'"
            )
            if not cur.fetchone():
                conn.close()
                return {}

            # Read all key-value pairs
            cur.execute("SELECT key, value FROM _fiberq_metadata")
            metadata = {}
            for key, value in cur.fetchall():
                metadata[key] = value

            conn.close()
            logger.debug(f"Read {len(metadata)} metadata entries from {gpkg_path}")
            return metadata
        except Exception as e:
            logger.debug(f"Error reading metadata from GPKG: {e}")
            try:
                conn.close()
            except Exception as e:
                logger.debug(f"Error closing GPKG connection after read failure: {e}")
            return {}

    def restore_metadata_to_project(self, metadata):
        """
        Restore FiberQ metadata from a GPKG import into the current project.

        This writes relations, latent elements, and color catalogs back
        into QgsProject storage so they appear in the plugin UI.

        Args:
            metadata: dict from read_metadata_from_gpkg()

        Returns:
            dict: Summary of what was restored {key: bool_success}
        """
        prj = QgsProject.instance()
        results = {}

        # 1. Restore relations
        if "relations_json" in metadata:
            try:
                # Validate JSON
                data = json.loads(metadata["relations_json"])
                if isinstance(data, dict) and "relations" in data:
                    prj.writeEntry(
                        self.PLUGIN_NAMESPACE,
                        self.RELATIONS_KEY,
                        metadata["relations_json"]
                    )
                    count = len(data.get("relations", []))
                    results["relations"] = True
                    logger.debug(f"Restored {count} relations from GPKG metadata")
            except Exception as e:
                results["relations"] = False
                logger.debug(f"Error restoring relations: {e}")

        # 2. Restore latent elements
        if "latent_elements_json" in metadata:
            try:
                data = json.loads(metadata["latent_elements_json"])
                if isinstance(data, dict):
                    prj.writeEntry(
                        self.PLUGIN_NAMESPACE,
                        self.LATENT_KEY,
                        metadata["latent_elements_json"]
                    )
                    count = len(data.get("cables", {}))
                    results["latent_elements"] = True
                    logger.debug(f"Restored latent elements for {count} cables from GPKG metadata")
            except Exception as e:
                results["latent_elements"] = False
                logger.debug(f"Error restoring latent elements: {e}")

        # 3. Restore color catalogs
        if "color_catalog_json" in metadata:
            try:
                data = json.loads(metadata["color_catalog_json"])
                if isinstance(data, dict) and "catalogs" in data:
                    prj.writeEntry(
                        self.PLUGIN_NAMESPACE,
                        self.COLOR_CATALOGS_KEY,
                        metadata["color_catalog_json"]
                    )
                    count = len(data.get("catalogs", []))
                    results["color_catalogs"] = True
                    logger.debug(f"Restored {count} color catalogs from GPKG metadata")
            except Exception as e:
                results["color_catalogs"] = False
                logger.debug(f"Error restoring color catalogs: {e}")

        # 4. Restore the schema version into the project marker (WP1a). Prefer the
        #    dedicated schema_version key; fall back to legacy project_version.
        version = metadata.get("schema_version") or metadata.get("project_version")
        if version:
            try:
                write_project_schema_version(version, prj)
                results["schema_version"] = True
                logger.debug(f"Restored schema_version = {version} from GPKG metadata")
            except Exception as e:
                results["schema_version"] = False
                logger.debug(f"Error restoring schema_version: {e}")

        # 5. Log other metadata (informational, not restored to project storage)
        for key in ("project_version", "crs_epsg", "export_timestamp", "color_standard"):
            if key in metadata:
                logger.debug(f"GPKG metadata: {key} = {metadata[key]}")

        return results

    # =========================================================================
    # CABLE AND PIPE LISTING
    # =========================================================================

    def list_all_cables(self):
        """
        Get list of all cable features from cable layers.

        Returns:
            list: Cable records with layer_id, fid, opis, tip, podtip, etc.
        """
        items = []

        # Accept both Serbian and English layer names
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
                    or lyr.geometryType() != QgsWkbTypes.LineGeometry  # noqa: W503
                    or lyr.name() not in candidate_names  # noqa: W503
                ):
                    continue
            except Exception as e:
                logger.debug(f"Skipping layer while listing cables: {e}")
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

                # Display label mapping
                podtip_labels = {
                    "glavni": "Backbone",
                    "distributivni": "Distribution",
                    "razvodni": "Drop",
                    "Backbone": "Backbone",
                    "Distribution": "Distribution",
                    "Drop": "Drop",
                }
                podtip_label = podtip_labels.get(str(podtip_code), str(podtip_code))

                # Build description
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

    def list_all_pipes(self):
        """
        Get list of all pipe features from pipe layers.

        Returns:
            list: Pipe records with layer_id, fid, opis, etc.
        """
        items = []
        layers = []

        pipe_names = ('PE cevi', 'Prelazne cevi', 'PE pipes', 'Transition pipes',
                      'PE ducts', 'Transition ducts')

        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.LineGeometry  # noqa: W503
                        and lyr.name() in pipe_names):  # noqa: W503
                    layers.append(lyr)
            except Exception as e:
                logger.debug(f"Error in DataManager.list_all_pipes: {e}")

        for lyr in layers:
            fields = lyr.fields()
            for f in lyr.getFeatures():
                attrs = {fld.name(): f[fld.name()] for fld in fields}
                materijal = attrs.get('materijal', '') or ''
                kap = attrs.get('kapacitet', '') or ''
                fi = attrs.get('fi', '') or ''

                # Build capacity text
                cap_text = ''
                try:
                    if fi not in (None, ''):
                        cap_text = f"Ø {int(fi)} mm"
                except Exception as e:
                    logger.debug(f"Error in DataManager.list_all_pipes: {e}")
                if (kap or '').strip():
                    cap_text = (cap_text + (' | ' if cap_text else '')) + str(kap)

                items.append({
                    'layer_id': lyr.id(),
                    'layer_name': lyr.name(),
                    'fid': int(f.id()),
                    'opis': (str(materijal).strip() or 'Pipe') + (f" {cap_text}" if cap_text else ''),
                    'tip': 'pipe',
                    'podtip': 'pipe',
                    'kapacitet': cap_text,
                    'color_code': '',
                    'od': attrs.get('od', '') or '',
                    'do': attrs.get('do', '') or ''
                })

        return items

    def find_candidate_elements_for_cable(self, cable_layer, cable_feature, tol=5.0):
        """
        Find point elements near a cable route.

        Only includes elements from "Placing elements" layers (passive optical elements),
        not poles, manholes, or other infrastructure elements.

        Args:
            cable_layer: Cable layer
            cable_feature: Cable feature
            tol: Tolerance distance

        Returns:
            list: Candidate elements sorted by distance along cable
        """
        from qgis.core import QgsGeometry, QgsPointXY

        # Issue #5: Only include "Placing elements" layer names (passive optical elements)
        PLACING_ELEMENT_LAYERS = {
            # English names
            'Joint Closures', 'ODF', 'TB', 'Patch panel', 'Patch Panel',
            'OTB', 'Indoor OTB', 'Outdoor OTB', 'Pole OTB',
            'TO', 'Indoor TO', 'Outdoor TO', 'Pole TO', 'Joint Closure TO',
            # Serbian names (backward compatibility)
            'Nastavci', 'Optički razdelnik', 'Završna optička kutija',
        }

        geom = cable_feature.geometry()
        if geom is None or geom.isEmpty():
            return []

        # Get from/to names to exclude endpoints
        try:
            od = str(cable_feature['od']) if 'od' in cable_layer.fields().names() and cable_feature['od'] is not None else ''
            do = str(cable_feature['do']) if 'do' in cable_layer.fields().names() and cable_feature['do'] is not None else ''
        except Exception:
            od = ''
            do = ''

        cands = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.geometryType() != QgsWkbTypes.PointGeometry:
                    continue

                # Issue #5: Only include layers from "Placing elements"
                if lyr.name() not in PLACING_ELEMENT_LAYERS:
                    continue

                fields = lyr.fields()
                has_naziv = fields.indexFromName('naziv') != -1

                for f in lyr.getFeatures():
                    pgeom = f.geometry()
                    if pgeom is None or pgeom.isEmpty():
                        continue

                    d = geom.distance(pgeom)
                    if d > tol:
                        continue

                    try:
                        m = geom.lineLocatePoint(pgeom)
                        m = float(m)
                    except Exception:
                        nearest = geom.closestSegmentWithContext(pgeom.asPoint())[1] if hasattr(geom, 'closestSegmentWithContext') else None
                        m = float(geom.length()) if nearest is None else float(geom.lineLocatePoint(QgsGeometry.fromPointXY(QgsPointXY(nearest))))

                    name = ''
                    if has_naziv:
                        val = f['naziv']
                        if val is not None:
                            name = str(val).strip()

                    # Skip endpoints by name
                    if name and (name == od or name == do):
                        continue

                    cands.append({
                        "layer_id": lyr.id(),
                        "layer_name": lyr.name(),
                        "fid": int(f.id()),
                        "naziv": name if name else f"{lyr.name()}:{int(f.id())}",
                        "m": m,
                        "distance": float(d),
                    })
            except Exception as e:
                logger.debug(f"Skipping layer while finding candidate elements: {e}")
                continue

        # Sort and deduplicate
        out = []
        seen = set()
        for it in sorted(cands, key=lambda x: x.get('m', 0.0)):
            key = (it['layer_id'], it['fid'])
            if key in seen:
                continue
            seen.add(key)
            out.append(it)

        return out


# Module-level convenience function
def get_data_manager(iface=None, plugin=None):
    """Get a DataManager instance."""
    return DataManager(iface, plugin)


__all__ = [
    'DataManager',
    'get_data_manager',
]
