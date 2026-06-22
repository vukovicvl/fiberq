"""
FiberQ v2 - Fiber Color Catalogs Module

This module manages fiber color catalogs used for cable identification
according to various standards (TIA-598, IEC, ITU-T, etc.).
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


# =============================================================================
# STANDARD FIBER COLORS (ANSI/TIA-598-C)
# =============================================================================

@dataclass
class FiberColor:
    """Represents a single fiber color in a catalog."""
    name: str
    hex_code: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary format."""
        return {"name": self.name, "hex": self.hex_code}


# Standard 12-color fiber sequence (ANSI/TIA-598-C)
STANDARD_FIBER_COLORS: List[FiberColor] = [
    FiberColor("Blue", "#1f77b4"),
    FiberColor("Orange", "#ff7f0e"),
    FiberColor("Green", "#2ca02c"),
    FiberColor("Brown", "#8c564b"),
    FiberColor("Slate", "#7f7f7f"),
    FiberColor("White", "#ffffff"),
    FiberColor("Red", "#d62728"),
    FiberColor("Black", "#000000"),
    FiberColor("Yellow", "#bcbd22"),
    FiberColor("Violet", "#9467bd"),
    FiberColor("Pink", "#e377c2"),
    FiberColor("Aqua", "#17becf"),
]


# =============================================================================
# COLOR CATALOG DEFINITION
# =============================================================================

@dataclass
class ColorCatalog:
    """A named collection of fiber colors."""
    name: str
    colors: List[FiberColor] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for storage."""
        return {
            "name": self.name,
            "colors": [c.to_dict() for c in self.colors],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ColorCatalog':
        """Create from dictionary format."""
        colors = [
            FiberColor(c.get("name", ""), c.get("hex", "#000000"))
            for c in data.get("colors", [])
        ]
        return cls(name=data.get("name", ""), colors=colors)

    def get_color_by_index(self, index: int) -> Optional[FiberColor]:
        """Get color by fiber index (0-based)."""
        if 0 <= index < len(self.colors):
            return self.colors[index]
        return None

    def get_color_by_name(self, name: str) -> Optional[FiberColor]:
        """Get color by name (case-insensitive)."""
        name_lower = name.lower()
        for color in self.colors:
            if color.name.lower() == name_lower:
                return color
        return None


# =============================================================================
# DEFAULT CATALOGS
# =============================================================================

def get_default_color_catalogs() -> List[ColorCatalog]:
    """
    Get the default fiber color catalogs.

    Returns:
        List of default ColorCatalog objects
    """
    return [
        ColorCatalog(
            name="TIA-598-C",
            colors=STANDARD_FIBER_COLORS.copy()
        ),
    ]


def get_default_color_sets() -> List[Dict[str, Any]]:
    """
    Get default color sets in dictionary format.

    Returns:
        List of catalog dictionaries for storage
    """
    return [catalog.to_dict() for catalog in get_default_color_catalogs()]


# =============================================================================
# CATALOG MANAGER
# =============================================================================

class ColorCatalogManager:
    """
    Manages fiber color catalogs including loading, saving, and querying.

    Catalogs are stored in the QGIS project settings.
    """

    SETTINGS_KEY = "ColorCatalogs/catalogs_v1"

    # Base catalog names that should always be available
    BASE_CATALOG_NAMES: List[str] = [
        "ANSI/EIA/TIA-598-A",
        "IEC 60793-2-50",
        "ITU-T (generic)",
    ]

    def __init__(self, project=None):
        """
        Initialize the catalog manager.

        Args:
            project: QgsProject instance (optional, uses current project if None)
        """
        self._project = project
        self._catalogs: Optional[Dict[str, Any]] = None

    @property
    def project(self):
        """Get the QGIS project instance."""
        if self._project is None:
            try:
                from qgis.core import QgsProject
                return QgsProject.instance()
            except ImportError:
                return None
        return self._project

    def load_catalogs(self) -> Dict[str, Any]:
        """
        Load color catalogs from project settings.

        Returns:
            Dictionary containing catalogs list
        """
        if self.project is None:
            return {"catalogs": get_default_color_sets()}

        try:
            stored = self.project.readEntry(
                'StuboviPlugin',
                self.SETTINGS_KEY,
                ''
            )[0]

            if not stored:
                return {"catalogs": get_default_color_sets()}

            data = json.loads(stored)
            if not isinstance(data, dict) or "catalogs" not in data:
                return {"catalogs": get_default_color_sets()}

            return data

        except (json.JSONDecodeError, TypeError):
            return {"catalogs": get_default_color_sets()}
        except Exception as e:
            return {"catalogs": get_default_color_sets()}

    def save_catalogs(self, data: Dict[str, Any]) -> bool:
        """
        Save color catalogs to project settings.

        Args:
            data: Dictionary containing catalogs list

        Returns:
            True if save was successful, False otherwise
        """
        if self.project is None:
            return False

        try:
            self.project.writeEntry(
                'StuboviPlugin',
                self.SETTINGS_KEY,
                json.dumps(data)
            )
            self._catalogs = data
            return True
        except Exception as e:
            return False

    def get_catalog_names(self) -> List[str]:
        """
        Get list of available catalog names.

        Ensures base catalogs are always included.

        Returns:
            List of catalog names
        """
        data = self.load_catalogs()
        names = [
            c.get("name", "")
            for c in data.get("catalogs", [])
            if c.get("name")
        ]

        # Ensure base catalogs are always available
        for base_name in self.BASE_CATALOG_NAMES:
            if base_name not in names:
                names.append(base_name)

        return names

    def get_catalog(self, name: str) -> Optional[ColorCatalog]:
        """
        Get a specific catalog by name.

        Args:
            name: Catalog name

        Returns:
            ColorCatalog object or None if not found
        """
        data = self.load_catalogs()

        for catalog_data in data.get("catalogs", []):
            if catalog_data.get("name") == name:
                return ColorCatalog.from_dict(catalog_data)

        return None

    def add_catalog(self, catalog: ColorCatalog) -> bool:
        """
        Add or update a color catalog.

        Args:
            catalog: ColorCatalog to add

        Returns:
            True if successful, False otherwise
        """
        data = self.load_catalogs()
        catalogs = data.get("catalogs", [])

        # Check if catalog with same name exists
        existing_idx = None
        for i, c in enumerate(catalogs):
            if c.get("name") == catalog.name:
                existing_idx = i
                break

        if existing_idx is not None:
            catalogs[existing_idx] = catalog.to_dict()
        else:
            catalogs.append(catalog.to_dict())

        data["catalogs"] = catalogs
        return self.save_catalogs(data)

    def remove_catalog(self, name: str) -> bool:
        """
        Remove a color catalog by name.

        Args:
            name: Catalog name to remove

        Returns:
            True if successful, False otherwise
        """
        data = self.load_catalogs()
        catalogs = data.get("catalogs", [])

        # Filter out the catalog with matching name
        new_catalogs = [c for c in catalogs if c.get("name") != name]

        if len(new_catalogs) == len(catalogs):
            # Nothing was removed
            return False

        data["catalogs"] = new_catalogs
        return self.save_catalogs(data)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_fiber_color_by_position(
    position: int,
    tube_count: int = 12,
    catalog_name: str = "TIA-598-C"
) -> Optional[str]:
    """
    Get fiber color hex code by position in a buffer tube.

    Args:
        position: Fiber position (1-based)
        tube_count: Number of fibers per tube (default 12)
        catalog_name: Color catalog to use

    Returns:
        Hex color code or None if not found
    """
    # Convert to 0-based index within tube
    index = (position - 1) % tube_count

    manager = ColorCatalogManager()
    catalog = manager.get_catalog(catalog_name)

    if catalog is None:
        # Fall back to standard colors
        if 0 <= index < len(STANDARD_FIBER_COLORS):
            return STANDARD_FIBER_COLORS[index].hex_code
        return None

    color = catalog.get_color_by_index(index)
    return color.hex_code if color else None


def format_fiber_color_label(
    fiber_number: int,
    tube_count: int = 12,
    catalog_name: str = "TIA-598-C"
) -> str:
    """
    Format a label showing fiber number and color name.

    Args:
        fiber_number: Fiber number (1-based)
        tube_count: Number of fibers per tube
        catalog_name: Color catalog to use

    Returns:
        Formatted string like "Fiber 5 (Slate)"
    """
    index = (fiber_number - 1) % tube_count

    manager = ColorCatalogManager()
    catalog = manager.get_catalog(catalog_name)

    if catalog:
        color = catalog.get_color_by_index(index)
        if color:
            return f"Fiber {fiber_number} ({color.name})"

    # Fall back to standard colors
    if 0 <= index < len(STANDARD_FIBER_COLORS):
        return f"Fiber {fiber_number} ({STANDARD_FIBER_COLORS[index].name})"

    return f"Fiber {fiber_number}"
