# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Relations and Latent Elements Manager.

This module provides management for:
- Cable relations (groupings)
- Latent/planned elements
- Finding candidate elements along cables

Phase 5.2: Added logging infrastructure
"""

import json
from typing import Optional, List, Dict, Any, Tuple

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class RelationsManager:
    """Manager for relations and latent elements."""

    # Storage keys
    RELATIONS_STORAGE_KEY = "Relacije/relations_v1"
    LATENT_STORAGE_KEY = "LatentElements/latent_v1"

    def __init__(self, data_manager=None):
        """
        Initialize RelationsManager.

        Args:
            data_manager: Optional DataManager instance for delegation
        """
        self.data_manager = data_manager

    # -------------------------------------------------------------------------
    # Relations methods
    # -------------------------------------------------------------------------

    def relations_storage_key(self) -> str:
        """Get storage key for relations."""
        return self.RELATIONS_STORAGE_KEY

    def load_relations(self) -> Dict[str, Any]:
        """Load relations from project storage."""
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.load_relations()
            except Exception as e:
                logger.debug(f"Error in RelationsManager.load_relations: {e}")

        # Fallback: direct project access
        s = QgsProject.instance().readEntry('StuboviPlugin', self.RELATIONS_STORAGE_KEY, '')[0]
        if not s:
            return {"relations": []}
        try:
            return json.loads(s)
        except Exception:
            return {"relations": []}

    def save_relations(self, data: Dict[str, Any]) -> None:
        """Save relations to project storage."""
        # Try DataManager first
        if self.data_manager:
            try:
                self.data_manager.save_relations(data)
                return
            except Exception as e:
                logger.debug(f"Error in RelationsManager.save_relations: {e}")

        # Fallback: direct project access
        QgsProject.instance().writeEntry('StuboviPlugin', self.RELATIONS_STORAGE_KEY, json.dumps(data))

    def get_relation_by_id(self, data: Dict[str, Any], rid: Any) -> Optional[Dict[str, Any]]:
        """Get relation by ID from data dict."""
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.get_relation_by_id(data, rid)
            except Exception as e:
                logger.debug(f"Error in RelationsManager.get_relation_by_id: {e}")

        # Fallback
        for r in data.get("relations", []):
            if r.get("id") == rid:
                return r
        return None

    def get_relation_name_by_cable(self) -> Dict[Tuple[str, int], str]:
        """
        Get mapping of (layer_id, fid) -> relation_name for all cables.

        Returns:
            Dict mapping (layer_id, fid) tuples to relation names
        """
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.get_relation_name_by_cable()
            except Exception as e:
                logger.debug(f"Error in RelationsManager.get_relation_name_by_cable: {e}")

        # Fallback
        data = self.load_relations()
        out = {}
        for r in data.get("relations", []):
            nm = r.get("name", "")
            for c in r.get("cables", []):
                key = (c.get("layer_id"), int(c.get("fid")))
                out[key] = nm
        return out

    def add_relation(self, name: str, cables: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Add a new relation.

        Args:
            name: Relation name
            cables: List of cable dicts with layer_id and fid

        Returns:
            The newly created relation dict
        """
        data = self.load_relations()

        # Generate new ID
        existing_ids = [r.get("id", 0) for r in data.get("relations", [])]
        new_id = max(existing_ids, default=0) + 1

        relation = {
            "id": new_id,
            "name": name,
            "cables": cables
        }

        data.setdefault("relations", []).append(relation)
        self.save_relations(data)

        return relation

    def delete_relation(self, rid: Any) -> bool:
        """
        Delete a relation by ID.

        Args:
            rid: Relation ID to delete

        Returns:
            True if deleted, False if not found
        """
        data = self.load_relations()
        original_count = len(data.get("relations", []))
        data["relations"] = [r for r in data.get("relations", []) if r.get("id") != rid]

        if len(data.get("relations", [])) < original_count:
            self.save_relations(data)
            return True
        return False

    def update_relation(self, rid: Any, name: Optional[str] = None,
                        cables: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Update an existing relation.

        Args:
            rid: Relation ID to update
            name: New name (optional)
            cables: New cables list (optional)

        Returns:
            True if updated, False if not found
        """
        data = self.load_relations()
        relation = self.get_relation_by_id(data, rid)

        if relation is None:
            return False

        if name is not None:
            relation["name"] = name
        if cables is not None:
            relation["cables"] = cables

        self.save_relations(data)
        return True

    # -------------------------------------------------------------------------
    # Latent elements methods
    # -------------------------------------------------------------------------

    def latent_storage_key(self) -> str:
        """Get storage key for latent elements."""
        return self.LATENT_STORAGE_KEY

    def load_latent(self) -> Dict[str, Any]:
        """Load latent elements from project storage."""
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.load_latent()
            except Exception as e:
                logger.debug(f"Error in RelationsManager.load_latent: {e}")

        # Fallback: direct project access
        s = QgsProject.instance().readEntry('StuboviPlugin', self.LATENT_STORAGE_KEY, '')[0]
        if not s:
            return {"cables": {}}
        try:
            return json.loads(s)
        except Exception:
            return {"cables": {}}

    def save_latent(self, data: Dict[str, Any]) -> None:
        """Save latent elements to project storage."""
        # Try DataManager first
        if self.data_manager:
            try:
                self.data_manager.save_latent(data)
                return
            except Exception as e:
                logger.debug(f"Error in RelationsManager.save_latent: {e}")

        # Fallback: direct project access
        QgsProject.instance().writeEntry('StuboviPlugin', self.LATENT_STORAGE_KEY, json.dumps(data))

    def cable_key(self, layer_id: str, fid: int) -> str:
        """
        Generate unique cable key from layer ID and feature ID.

        Args:
            layer_id: Layer ID
            fid: Feature ID

        Returns:
            String key in format "layer_id:fid"
        """
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.cable_key(layer_id, fid)
            except Exception as e:
                logger.debug(f"Error in RelationsManager.cable_key: {e}")

        return f"{layer_id}:{int(fid)}"

    def get_latent_for_cable(self, layer_id: str, fid: int) -> List[Dict[str, Any]]:
        """
        Get latent elements for a specific cable.

        Args:
            layer_id: Cable layer ID
            fid: Cable feature ID

        Returns:
            List of latent element dicts
        """
        data = self.load_latent()
        key = self.cable_key(layer_id, fid)
        return data.get("cables", {}).get(key, [])

    def add_latent_to_cable(self, layer_id: str, fid: int,
                            element: Dict[str, Any]) -> None:
        """
        Add a latent element to a cable.

        Args:
            layer_id: Cable layer ID
            fid: Cable feature ID
            element: Latent element dict (should have m, name, etc.)
        """
        data = self.load_latent()
        key = self.cable_key(layer_id, fid)

        if "cables" not in data:
            data["cables"] = {}
        if key not in data["cables"]:
            data["cables"][key] = []

        data["cables"][key].append(element)
        self.save_latent(data)

    def remove_latent_from_cable(self, layer_id: str, fid: int,
                                 element_index: int) -> bool:
        """
        Remove a latent element from a cable by index.

        Args:
            layer_id: Cable layer ID
            fid: Cable feature ID
            element_index: Index of element to remove

        Returns:
            True if removed, False if not found
        """
        data = self.load_latent()
        key = self.cable_key(layer_id, fid)

        elements = data.get("cables", {}).get(key, [])
        if 0 <= element_index < len(elements):
            elements.pop(element_index)
            if not elements:
                # Remove empty list
                del data["cables"][key]
            self.save_latent(data)
            return True
        return False

    def clear_latent_for_cable(self, layer_id: str, fid: int) -> None:
        """
        Clear all latent elements for a cable.

        Args:
            layer_id: Cable layer ID
            fid: Cable feature ID
        """
        data = self.load_latent()
        key = self.cable_key(layer_id, fid)

        if key in data.get("cables", {}):
            del data["cables"][key]
            self.save_latent(data)

    # -------------------------------------------------------------------------
    # Candidate elements finder
    # -------------------------------------------------------------------------

    def find_candidate_elements_for_cable(self, cable_layer: QgsVectorLayer,
                                          cable_feature: QgsFeature,
                                          tol: float = 5.0) -> List[Dict[str, Any]]:
        """
        Find candidate elements (points) along a cable within tolerance.

        Args:
            cable_layer: The cable layer
            cable_feature: The cable feature
            tol: Tolerance in map units (default 5.0)

        Returns:
            List of candidate dicts sorted by distance along cable (m)
        """
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.find_candidate_elements_for_cable(cable_layer, cable_feature, tol)
            except Exception as e:
                logger.debug(f"Error in RelationsManager.find_candidate_elements_for_cable: {e}")

        # Fallback: inline implementation
        geom = cable_feature.geometry()
        if geom is None or geom.isEmpty():
            return []

        # Get cable endpoints names
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

                fields = lyr.fields()
                has_naziv = fields.indexFromName('naziv') != -1

                # Take layers that have 'naziv' or are named 'Poles'
                if not has_naziv and lyr.name() != 'Poles':
                    continue

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
                        # Fallback: project nearest point and measure distance from start
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
            except Exception:
                continue

        # Sort and remove duplicates
        out = []
        seen = set()
        for it in sorted(cands, key=lambda x: x.get('m', 0.0)):
            key = (it['layer_id'], it['fid'])
            if key in seen:
                continue
            seen.add(key)
            out.append(it)

        return out


__all__ = ['RelationsManager']
