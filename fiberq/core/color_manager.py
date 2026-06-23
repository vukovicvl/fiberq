# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Color Catalog Manager.

This module provides color catalog management functionality:
- Loading and saving color catalogs
- Default color sets (TIA-598-C standard)
- Color code listing
- Color catalog manager dialog
"""

import json
from typing import Optional, List, Dict, Any

from qgis.PyQt.QtWidgets import QMessageBox

from qgis.core import QgsProject

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class ColorManager:
    """Manager for color catalog operations."""

    # Storage key
    COLOR_CATALOGS_KEY = "ColorCatalogs/catalogs_v1"

    # Default TIA-598-C color standard
    DEFAULT_TIA_598_C_COLORS = [
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

    # Base color code standards
    BASE_COLOR_CODES = [
        "ANSI/EIA/TIA-598-A",
        "IEC 60793-2-50",
        "ITU-T (generički)",
    ]

    def __init__(self, iface, data_manager=None):
        """
        Initialize ColorManager.

        Args:
            iface: QGIS interface
            data_manager: Optional DataManager instance for delegation
        """
        self.iface = iface
        self.data_manager = data_manager

    # -------------------------------------------------------------------------
    # Storage key
    # -------------------------------------------------------------------------

    def color_catalogs_key(self) -> str:
        """Get the storage key for color catalogs."""
        return self.COLOR_CATALOGS_KEY

    # -------------------------------------------------------------------------
    # Default color sets
    # -------------------------------------------------------------------------

    def get_default_color_sets(self) -> List[Dict[str, Any]]:
        """
        Get default color sets.

        Returns:
            List of color catalog dicts with name and colors
        """
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.get_default_color_sets()
            except Exception as e:
                logger.debug(f"Error in ColorManager.get_default_color_sets: {e}")

        # Fallback: TIA-598-C standard
        return [
            {
                "name": "TIA-598-C",
                "colors": [{"name": n, "hex": h} for n, h in self.DEFAULT_TIA_598_C_COLORS]
            },
        ]

    # -------------------------------------------------------------------------
    # Load/Save catalogs
    # -------------------------------------------------------------------------

    def load_color_catalogs(self) -> Dict[str, Any]:
        """
        Load color catalogs from project storage.

        Returns:
            Dict with 'catalogs' key containing list of color catalogs
        """
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.load_color_catalogs()
            except Exception as e:
                logger.debug(f"Error in ColorManager.load_color_catalogs: {e}")

        # Fallback: direct project access
        s = QgsProject.instance().readEntry('StuboviPlugin', self.COLOR_CATALOGS_KEY, '')[0]
        if not s:
            return {"catalogs": self.get_default_color_sets()}
        try:
            obj = json.loads(s)
            if not isinstance(obj, dict) or "catalogs" not in obj:
                obj = {"catalogs": self.get_default_color_sets()}
            return obj
        except Exception:
            return {"catalogs": self.get_default_color_sets()}

    def save_color_catalogs(self, data: Dict[str, Any]) -> None:
        """
        Save color catalogs to project storage.

        Args:
            data: Dict with 'catalogs' key containing list of color catalogs
        """
        # Try DataManager first
        if self.data_manager:
            try:
                self.data_manager.save_color_catalogs(data)
                return
            except Exception as e:
                logger.debug(f"Error in ColorManager.save_color_catalogs: {e}")

        # Fallback: direct project access
        try:
            QgsProject.instance().writeEntry('StuboviPlugin', self.COLOR_CATALOGS_KEY, json.dumps(data))
        except Exception as e:
            logger.debug(f"Error in ColorManager.save_color_catalogs: {e}")

    # -------------------------------------------------------------------------
    # Color code listing
    # -------------------------------------------------------------------------

    def list_color_codes(self) -> List[str]:
        """
        List all available color code names.

        Returns:
            List of color code/catalog names
        """
        # Try DataManager first
        if self.data_manager:
            try:
                return self.data_manager.list_color_codes()
            except Exception as e:
                logger.debug(f"Error in ColorManager.list_color_codes: {e}")

        # Fallback: inline implementation
        data = self.load_color_catalogs()
        names = [c.get("name", "") for c in data.get("catalogs", []) if c.get("name")]

        # Add base standards if not already present
        for b in self.BASE_COLOR_CODES:
            if b not in names:
                names.append(b)

        return names

    # -------------------------------------------------------------------------
    # Catalog management
    # -------------------------------------------------------------------------

    def get_catalog_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a color catalog by name.

        Args:
            name: Catalog name

        Returns:
            Catalog dict or None if not found
        """
        data = self.load_color_catalogs()
        for catalog in data.get("catalogs", []):
            if catalog.get("name") == name:
                return catalog
        return None

    def add_catalog(self, name: str, colors: List[Dict[str, str]]) -> bool:
        """
        Add a new color catalog.

        Args:
            name: Catalog name
            colors: List of color dicts with 'name' and 'hex' keys

        Returns:
            True if added successfully
        """
        data = self.load_color_catalogs()

        # Check if name already exists
        for catalog in data.get("catalogs", []):
            if catalog.get("name") == name:
                return False

        data.setdefault("catalogs", []).append({
            "name": name,
            "colors": colors
        })
        self.save_color_catalogs(data)
        return True

    def update_catalog(self, name: str, colors: List[Dict[str, str]]) -> bool:
        """
        Update an existing color catalog.

        Args:
            name: Catalog name
            colors: New list of color dicts

        Returns:
            True if updated, False if not found
        """
        data = self.load_color_catalogs()

        for catalog in data.get("catalogs", []):
            if catalog.get("name") == name:
                catalog["colors"] = colors
                self.save_color_catalogs(data)
                return True
        return False

    def delete_catalog(self, name: str) -> bool:
        """
        Delete a color catalog by name.

        Args:
            name: Catalog name

        Returns:
            True if deleted, False if not found
        """
        data = self.load_color_catalogs()
        original_count = len(data.get("catalogs", []))
        data["catalogs"] = [c for c in data.get("catalogs", []) if c.get("name") != name]

        if len(data.get("catalogs", [])) < original_count:
            self.save_color_catalogs(data)
            return True
        return False

    def rename_catalog(self, old_name: str, new_name: str) -> bool:
        """
        Rename a color catalog.

        Args:
            old_name: Current catalog name
            new_name: New catalog name

        Returns:
            True if renamed, False if not found or new name exists
        """
        data = self.load_color_catalogs()

        # Check if new name already exists
        for catalog in data.get("catalogs", []):
            if catalog.get("name") == new_name:
                return False

        # Find and rename
        for catalog in data.get("catalogs", []):
            if catalog.get("name") == old_name:
                catalog["name"] = new_name
                self.save_color_catalogs(data)
                return True
        return False

    # -------------------------------------------------------------------------
    # Color utilities
    # -------------------------------------------------------------------------

    def get_colors_for_catalog(self, name: str) -> List[Dict[str, str]]:
        """
        Get colors for a specific catalog.

        Args:
            name: Catalog name

        Returns:
            List of color dicts with 'name' and 'hex' keys
        """
        catalog = self.get_catalog_by_name(name)
        if catalog:
            return catalog.get("colors", [])
        return []

    def get_color_by_index(self, catalog_name: str, index: int) -> Optional[Dict[str, str]]:
        """
        Get a specific color by index from a catalog.

        Args:
            catalog_name: Catalog name
            index: Color index (0-based)

        Returns:
            Color dict or None
        """
        colors = self.get_colors_for_catalog(catalog_name)
        if 0 <= index < len(colors):
            return colors[index]
        return None

    # -------------------------------------------------------------------------
    # UI method
    # -------------------------------------------------------------------------

    def open_color_catalog_manager(self, plugin) -> None:
        """
        Open the color catalog manager dialog.

        Args:
            plugin: The main plugin instance
        """
        try:
            from ..dialogs.color_dialog import ColorCatalogManagerDialog
            dlg = ColorCatalogManagerDialog(plugin)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Color Catalog",
                f"Error: {e}"
            )


__all__ = ['ColorManager']
