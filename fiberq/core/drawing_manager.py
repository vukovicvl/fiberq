# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Drawing Manager.

This module provides drawing management functionality:
- Associating drawings (DWG/DXF) with features
- Loading drawings into layer tree groups
- Opening external drawings

Phase 5.2: Added logging infrastructure
"""

import os
import re
from typing import List

from qgis.PyQt.QtCore import QCoreApplication, QUrl
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QInputDialog
from qgis.PyQt.QtGui import QDesktopServices

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
)

# Phase 5.2: Logging
from . import feature_links
from ..utils import file_filters
from ..utils.logger import get_logger
logger = get_logger(__name__)


class DrawingManager:
    """Manager for drawing operations."""

    # Category mappings for drawing subgroups
    CATEGORIES = ["Joint Closures", "Customers", "TB", "OTB", "ODF", "Other"]

    def __init__(self, iface, layer_manager=None):
        """
        Initialize DrawingManager.

        Args:
            iface: QGIS interface
            layer_manager: Optional LayerManager instance
        """
        self.iface = iface
        self.layer_manager = layer_manager

    # -------------------------------------------------------------------------
    # Storage key methods
    # -------------------------------------------------------------------------

    def drawing_key(self, layer: QgsVectorLayer, fid: int) -> str:
        """The pre-1.6.0 per-feature key. Kept so the fallback can be tested."""
        return f"drawing_map/{layer.id()}/{int(fid)}"

    def drawing_layers_key(self, layer: QgsVectorLayer, fid: int) -> str:
        """The pre-1.6.0 per-feature key. Kept so the fallback can be tested."""
        return f"drawing_layers/{layer.id()}/{int(fid)}"

    # -------------------------------------------------------------------------
    # Drawing path get/set
    # -------------------------------------------------------------------------

    def drawing_layers_get(self, layer: QgsVectorLayer, fid: int) -> List[str]:
        """The layer IDs that make up one feature's drawing.

        U9: through :mod:`fiberq.core.feature_links`. The old per-feature key
        ended in the feature id, which QGIS 3 cannot write as an XML element
        name, so every drawing link was dropped at save. The old key is still
        read -- under both scopes -- and migrated when it answers.
        """
        stored = feature_links.link_get(
            feature_links.DRAWING_LAYERS, layer.id(), fid, default=[])
        if isinstance(stored, str):
            # A legacy value that reached here as the old comma-joined string.
            stored = stored.split(",")
        return [str(x) for x in stored if x]

    def drawing_layers_set(self, layer: QgsVectorLayer, fid: int, layer_ids: List[str]) -> None:
        """Record which layers make up one feature's drawing."""
        feature_links.link_set(
            feature_links.DRAWING_LAYERS, layer.id(), fid,
            [str(x) for x in (layer_ids or [])])

    def drawing_get(self, layer: QgsVectorLayer, fid: int) -> str:
        """The drawing attached to one feature, or ``''``. See U9 above."""
        return feature_links.link_get(feature_links.DRAWINGS, layer.id(), fid)

    def drawing_set(self, layer: QgsVectorLayer, fid: int, path: str) -> None:
        """Attach a drawing to one feature, or clear it when ``path`` is empty."""
        feature_links.link_set(
            feature_links.DRAWINGS, layer.id(), fid, path or "")

    def drawing_set_many(self, layer: QgsVectorLayer, fids, path: str) -> None:
        """Attach one drawing to many features, in a single project write.

        One JSON entry holds every drawing link in the project, so writing it
        per feature re-parses and re-serialises a growing blob each time --
        cleanly quadratic, and "Attach drawing" runs over the whole selection.
        """
        feature_links.link_set_many(
            feature_links.DRAWINGS, layer.id(), {fid: path or "" for fid in fids})

    def drawing_layers_set_many(self, layer: QgsVectorLayer, fids, layer_ids) -> None:
        """Record one drawing's layer ids against many features, in one write."""
        value = [str(x) for x in (layer_ids or [])]
        feature_links.link_set_many(
            feature_links.DRAWING_LAYERS, layer.id(), {fid: list(value) for fid in fids})

    # -------------------------------------------------------------------------
    # Group management
    # -------------------------------------------------------------------------

    def ensure_drawings_group(self, subgroup_name: str):
        """
        Create or return a drawings subgroup.

        Args:
            subgroup_name: Name of the subgroup (e.g., "Joint Closures", "ODF")

        Returns:
            QgsLayerTreeGroup for the subgroup
        """
        # Try LayerManager first
        if self.layer_manager:
            try:
                return self.layer_manager.ensure_drawings_group(subgroup_name)
            except Exception as e:
                logger.debug(f"Error in DrawingManager.ensure_drawings_group: {e}")

        # Fallback: inline implementation
        root = QgsProject.instance().layerTreeRoot()

        group = root.findGroup("Drawings")
        if not group:
            legacy = root.findGroup("Crteži")
            if legacy:
                try:
                    legacy.setName("Drawings")
                except Exception as e:
                    logger.debug(f"Error in DrawingManager.ensure_drawings_group: {e}")
                group = legacy
            else:
                group = root.addGroup("Drawings")

        sub = group.findGroup(subgroup_name)
        if not sub:
            sub = group.addGroup(subgroup_name)

        return sub

    # -------------------------------------------------------------------------
    # Category detection
    # -------------------------------------------------------------------------

    def guess_category_for_layer(self, layer: QgsVectorLayer) -> str:
        """
        Guess the drawing category based on layer name.

        Args:
            layer: The layer to categorize

        Returns:
            Category name (e.g., "Joint Closures", "ODF", "Other")
        """
        name = (layer.name() or "").lower()

        # Detection by Serbian words in layer name,
        # but returns English subgroup names
        if "nastav" in name or "joint" in name:
            return "Joint Closures"
        if "koris" in name or "customer" in name:
            return "Customers"
        if "zok" in name or name == "tb":
            return "TB"
        if "odf" in name:
            return "ODF"
        if "odo" in name or "otb" in name:
            return "OTB"
        return "Other"

    # -------------------------------------------------------------------------
    # Drawing loading/checking
    # -------------------------------------------------------------------------

    def is_drawing_loaded(self, path: str) -> bool:
        """
        Check if a drawing file is already loaded in the project.

        Args:
            path: Path to the drawing file

        Returns:
            True if the drawing is already loaded
        """
        if not path:
            return False

        def norm(p: str) -> str:
            try:
                return os.path.normcase(os.path.abspath(p)).replace("\\", "/")
            except Exception:
                return (p or "").replace("\\", "/")

        target = norm(path)
        target_base = os.path.basename(target)

        for lyr in QgsProject.instance().mapLayers().values():
            try:
                src = (lyr.source() or "")
                src_norm = src.replace("\\", "/")

                # 1) Most common: "C:/x/file.dwg|layername=entities"
                if target and target in norm(src.split("|", 1)[0]):
                    return True

                # 2) dbname='C:/x/file.dwg' ...
                m = re.search(r"dbname\s*=\s*['\"]([^'\"]+)['\"]", src, flags=re.IGNORECASE)
                if m and norm(m.group(1)) == target:
                    return True

                # 3) path=C:/x/file.dwg (sometimes in URI)
                m2 = re.search(r"(?:^|[&? ])path\s*=\s*([^& ]+)", src, flags=re.IGNORECASE)
                if m2 and norm(m2.group(1).strip("'\"")) == target:
                    return True

                # 4) Fallback: basename match (to avoid false-negative on exotic URI formats)
                if target_base and target_base.lower() in src_norm.lower():
                    return True

            except Exception as e:
                logger.debug(f"Skipping layer while checking if drawing is loaded: {e}")
                continue

        return False

    def open_drawing_path(self, path: str) -> None:
        """
        Open a drawing file in the system default application.

        Args:
            path: Path to the drawing file
        """
        if not path or not os.path.exists(path):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Drawing",
                "The drawing path is invalid or the file does not exist."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def try_add_dwg_to_group(self, path: str, subgroup) -> List[str]:
        """
        Try to load DWG/DXF as OGR layers and add to a group.

        Args:
            path: Path to the DWG/DXF file
            subgroup: Layer tree group to add layers to

        Returns:
            List of added layer IDs (empty if failed)
        """
        base_name = os.path.basename(path)

        tmp = QgsVectorLayer(path, base_name, "ogr")
        added_ids = []

        if tmp.isValid():
            sublayers = []
            try:
                sublayers = tmp.dataProvider().subLayers() or tmp.subLayers() or []
            except Exception:
                sublayers = tmp.subLayers() if hasattr(tmp, "subLayers") else []

            if not sublayers:
                lyr = QgsVectorLayer(path, base_name, "ogr")
                if lyr.isValid():
                    QgsProject.instance().addMapLayer(lyr, False)
                    subgroup.addLayer(lyr)
                    added_ids.append(lyr.id())
            else:
                for s in sublayers:
                    parts = str(s).split(":")
                    lname = parts[1] if len(parts) > 1 else parts[0]
                    for key in ("layername", "layer"):
                        ds = f"{path}|{key}={lname}"
                        vl = QgsVectorLayer(ds, f"{base_name}:{lname}", "ogr")
                        if vl.isValid():
                            QgsProject.instance().addMapLayer(vl, False)
                            subgroup.addLayer(vl)
                            added_ids.append(vl.id())
                            break
        return added_ids

    # -------------------------------------------------------------------------
    # UI methods
    # -------------------------------------------------------------------------

    def add_drawing(self) -> None:
        """
        UI handler for adding a drawing to selected features.
        Shows file dialog, category selection, and associates drawing with features.
        """
        layer = self.iface.activeLayer()

        # Guard: only vector layers can have selected features
        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.information(
                self.iface.mainWindow(),
                "Drawing",
                "Select a VECTOR layer and one or more features, then try again."
            )
            return

        if layer.selectedFeatureCount() == 0:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Drawing",
                "Select one or more features and try again."
            )
            return

        feats = layer.selectedFeatures()

        # File selection
        path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Select drawing",
            "",
            file_filters.with_any(
                QCoreApplication.translate('FiberQDrawings', "DWG/DXF drawings"),
                file_filters.DRAWINGS,
                QCoreApplication.translate('FiberQDrawings', "All files"))
        )
        if not path:
            return

        # Category selection
        default_cat = self.guess_category_for_layer(layer)
        ok = True
        cat = default_cat
        try:
            cat, ok = QInputDialog.getItem(
                self.iface.mainWindow(),
                "Drawing layer",
                "Select a sub-layer in 'Drawings':",
                self.CATEGORIES,
                self.CATEGORIES.index(default_cat) if default_cat in self.CATEGORIES else 0,
                False
            )
        except Exception:
            ok = True
            cat = default_cat
        if not ok:
            return

        # Create group and try to load DWG/DXF
        subgroup = self.ensure_drawings_group(cat)
        added_layer_ids = self.try_add_dwg_to_group(path, subgroup)

        # Two project writes for the whole selection, not two per feature: the
        # per-feature form is quadratic in the size of the selection (see
        # feature_links.link_set_many), and this loop did it twice over.
        fids = [f.id() for f in feats]
        self.drawing_set_many(layer, fids, path)
        self.drawing_layers_set_many(layer, fids, added_layer_ids)

        QMessageBox.information(
            self.iface.mainWindow(),
            "Drawing",
            f"Drawing is associated with {len(feats)} feature(s)."
        )

    def open_drawing_for_feature(self, layer: QgsVectorLayer, fid: int) -> bool:
        """
        Open the drawing associated with a feature.

        Args:
            layer: The layer containing the feature
            fid: Feature ID

        Returns:
            True if a drawing was found and opened
        """
        path = self.drawing_get(layer, fid)
        if path:
            self.open_drawing_path(path)
            return True
        return False

    def get_drawing_info(self, layer: QgsVectorLayer, fid: int) -> dict:
        """
        Get drawing information for a feature.

        Args:
            layer: The layer containing the feature
            fid: Feature ID

        Returns:
            Dict with 'path' and 'layer_ids' keys
        """
        return {
            "path": self.drawing_get(layer, fid),
            "layer_ids": self.drawing_layers_get(layer, fid)
        }

    def clear_drawing(self, layer: QgsVectorLayer, fid: int) -> None:
        """
        Clear the drawing association for a feature.

        Args:
            layer: The layer containing the feature
            fid: Feature ID
        """
        self.drawing_set(layer, fid, "")
        self.drawing_layers_set(layer, fid, [])


__all__ = ['DrawingManager']
