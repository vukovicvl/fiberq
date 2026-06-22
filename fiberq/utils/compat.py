"""
FiberQ v1.1 - QGIS Compatibility Layer

This module provides compatibility aliases and utilities for supporting
multiple QGIS versions (3.22 LTR through 3.40+).

Key API Changes Handled:
- QGIS 3.30+: Some QgsUnitTypes enums moved to Qgis namespace
- QGIS 3.28+: Symbol layer API changes
- QGIS 3.34+: Label settings API changes

Usage:
    from .utils.compat import (
        QGIS_VERSION, QGIS_VERSION_INT,
        RenderUnit, DistanceUnit, GeometryType,
        get_render_unit, get_geometry_type
    )
"""

import warnings
from typing import Tuple

# =============================================================================
# VERSION DETECTION
# =============================================================================

try:
    from qgis.core import Qgis
    QGIS_VERSION = Qgis.QGIS_VERSION
    QGIS_VERSION_INT = Qgis.QGIS_VERSION_INT
except ImportError:
    QGIS_VERSION = "0.0.0"
    QGIS_VERSION_INT = 0

# Version thresholds
QGIS_3_22 = 32200  # LTR
QGIS_3_28 = 32800  # LTR
QGIS_3_30 = 33000  # API changes for units
QGIS_3_34 = 33400  # LTR
QGIS_3_36 = 33600
QGIS_3_40 = 34000  # Latest


def get_qgis_version() -> Tuple[int, int, int]:
    """Get QGIS version as tuple (major, minor, patch)."""
    try:
        major = QGIS_VERSION_INT // 10000
        minor = (QGIS_VERSION_INT % 10000) // 100
        patch = QGIS_VERSION_INT % 100
        return (major, minor, patch)
    except Exception:
        return (0, 0, 0)


def check_minimum_version(min_version: int = QGIS_3_22) -> bool:
    """Check if current QGIS version meets minimum requirement."""
    return QGIS_VERSION_INT >= min_version


def get_version_string() -> str:
    """Get human-readable version string."""
    return QGIS_VERSION


# =============================================================================
# RENDER UNIT COMPATIBILITY
# =============================================================================
# In QGIS 3.30+, RenderUnit enum was added to Qgis namespace
# We provide fallback to QgsUnitTypes for older versions

class RenderUnit:
    """
    Cross-version compatible render unit constants.

    Usage:
        from fiberq.utils.compat import RenderUnit
        symbol.setSizeUnit(RenderUnit.MetersInMapUnits)
    """

    @staticmethod
    def _get_unit(qgis_name: str, fallback_name: str):
        """Get render unit from Qgis namespace or QgsUnitTypes fallback."""
        try:
            # Try QGIS 3.30+ namespace first
            from qgis.core import Qgis
            if hasattr(Qgis, 'RenderUnit'):
                return getattr(Qgis.RenderUnit, qgis_name, None)
        except (ImportError, AttributeError):
            pass

        # Fallback to QgsUnitTypes
        try:
            from qgis.core import QgsUnitTypes
            return getattr(QgsUnitTypes, fallback_name, None)
        except (ImportError, AttributeError):
            return None

    # Common render units with both new and legacy names
    Millimeters = property(lambda self: RenderUnit._get_unit('Millimeters', 'RenderMillimeters'))
    MapUnits = property(lambda self: RenderUnit._get_unit('MapUnits', 'RenderMapUnits'))
    Pixels = property(lambda self: RenderUnit._get_unit('Pixels', 'RenderPixels'))
    Percentage = property(lambda self: RenderUnit._get_unit('Percentage', 'RenderPercentage'))
    Points = property(lambda self: RenderUnit._get_unit('Points', 'RenderPoints'))
    Inches = property(lambda self: RenderUnit._get_unit('Inches', 'RenderInches'))
    MetersInMapUnits = property(lambda self: RenderUnit._get_unit('MetersInMapUnits', 'RenderMetersInMapUnits'))


# Create singleton instance
_render_unit = RenderUnit()


def get_render_unit(unit_name: str):
    """
    Get render unit constant by name, compatible across QGIS versions.

    Args:
        unit_name: One of 'Millimeters', 'MapUnits', 'Pixels', 'MetersInMapUnits', etc.

    Returns:
        The appropriate enum value for the current QGIS version

    Example:
        unit = get_render_unit('MetersInMapUnits')
        symbol.setSizeUnit(unit)
    """
    # Try new Qgis namespace first (3.30+)
    try:
        from qgis.core import Qgis
        if hasattr(Qgis, 'RenderUnit'):
            unit = getattr(Qgis.RenderUnit, unit_name, None)
            if unit is not None:
                return unit
    except (ImportError, AttributeError):
        pass

    # Fallback to QgsUnitTypes (3.22-3.28)
    try:
        from qgis.core import QgsUnitTypes
        fallback_name = f"Render{unit_name}"
        unit = getattr(QgsUnitTypes, fallback_name, None)
        if unit is not None:
            return unit
    except (ImportError, AttributeError):
        pass

    # Last resort - try direct QgsUnitTypes attribute
    try:
        from qgis.core import QgsUnitTypes
        return getattr(QgsUnitTypes, unit_name, None)
    except (ImportError, AttributeError):
        return None


# Convenience constants for direct import
try:
    RenderMillimeters = get_render_unit('Millimeters')
    RenderMapUnits = get_render_unit('MapUnits')
    RenderPixels = get_render_unit('Pixels')
    RenderMetersInMapUnits = get_render_unit('MetersInMapUnits')
    RenderPoints = get_render_unit('Points')
    RenderInches = get_render_unit('Inches')
    RenderPercentage = get_render_unit('Percentage')
except Exception:
    # Fallback to None if all methods fail
    RenderMillimeters = None
    RenderMapUnits = None
    RenderPixels = None
    RenderMetersInMapUnits = None
    RenderPoints = None
    RenderInches = None
    RenderPercentage = None


# =============================================================================
# DISTANCE UNIT COMPATIBILITY
# =============================================================================

def get_distance_unit(unit_name: str):
    """
    Get distance unit constant by name, compatible across QGIS versions.

    Args:
        unit_name: One of 'Meters', 'Kilometers', 'Feet', 'Miles', etc.

    Returns:
        The appropriate enum value for the current QGIS version
    """
    # Try new Qgis namespace first (3.30+)
    try:
        from qgis.core import Qgis
        if hasattr(Qgis, 'DistanceUnit'):
            unit = getattr(Qgis.DistanceUnit, unit_name, None)
            if unit is not None:
                return unit
    except (ImportError, AttributeError):
        pass

    # Fallback to QgsUnitTypes (3.22-3.28)
    try:
        from qgis.core import QgsUnitTypes
        fallback_name = f"Distance{unit_name}"
        unit = getattr(QgsUnitTypes, fallback_name, None)
        if unit is not None:
            return unit
    except (ImportError, AttributeError):
        pass

    return None


# Convenience constants
try:
    DistanceMeters = get_distance_unit('Meters')
    DistanceKilometers = get_distance_unit('Kilometers')
    DistanceFeet = get_distance_unit('Feet')
    DistanceMiles = get_distance_unit('Miles')
    DistanceYards = get_distance_unit('Yards')
except Exception:
    DistanceMeters = None
    DistanceKilometers = None
    DistanceFeet = None
    DistanceMiles = None
    DistanceYards = None


# =============================================================================
# GEOMETRY TYPE COMPATIBILITY
# =============================================================================

def get_geometry_type(type_name: str):
    """
    Get geometry type constant by name, compatible across QGIS versions.

    Args:
        type_name: One of 'Point', 'Line', 'Polygon', 'Unknown', 'Null'

    Returns:
        The appropriate QgsWkbTypes.GeometryType value
    """
    try:
        from qgis.core import QgsWkbTypes
        # Map common names to QgsWkbTypes attributes
        type_map = {
            'Point': 'PointGeometry',
            'Line': 'LineGeometry',
            'Polygon': 'PolygonGeometry',
            'Unknown': 'UnknownGeometry',
            'Null': 'NullGeometry',
            # Also accept full names
            'PointGeometry': 'PointGeometry',
            'LineGeometry': 'LineGeometry',
            'PolygonGeometry': 'PolygonGeometry',
        }
        attr_name = type_map.get(type_name, type_name)
        return getattr(QgsWkbTypes, attr_name, None)
    except (ImportError, AttributeError):
        return None


# Convenience constants
try:
    from qgis.core import QgsWkbTypes
    PointGeometry = QgsWkbTypes.PointGeometry
    LineGeometry = QgsWkbTypes.LineGeometry
    PolygonGeometry = QgsWkbTypes.PolygonGeometry
    UnknownGeometry = QgsWkbTypes.UnknownGeometry
    NullGeometry = QgsWkbTypes.NullGeometry
except (ImportError, AttributeError):
    PointGeometry = 0
    LineGeometry = 1
    PolygonGeometry = 2
    UnknownGeometry = 3
    NullGeometry = 4


# =============================================================================
# LABEL SETTINGS COMPATIBILITY
# =============================================================================

def get_label_placement(placement_name: str):
    """
    Get label placement constant, compatible across QGIS versions.

    Args:
        placement_name: e.g., 'OverPoint', 'Line', 'Curved', 'Horizontal'

    Returns:
        The appropriate placement enum value
    """
    # Try Qgis.LabelPlacement (3.30+)
    try:
        from qgis.core import Qgis
        if hasattr(Qgis, 'LabelPlacement'):
            val = getattr(Qgis.LabelPlacement, placement_name, None)
            if val is not None:
                return val
    except (ImportError, AttributeError):
        pass

    # Fallback to QgsPalLayerSettings
    try:
        from qgis.core import QgsPalLayerSettings
        return getattr(QgsPalLayerSettings, placement_name, None)
    except (ImportError, AttributeError):
        pass

    return None


# =============================================================================
# WKB TYPE COMPATIBILITY
# =============================================================================

def get_wkb_type(type_name: str):
    """
    Get WKB type constant by name.

    Args:
        type_name: e.g., 'Point', 'LineString', 'Polygon', 'MultiPoint', etc.

    Returns:
        The appropriate QgsWkbTypes value
    """
    try:
        from qgis.core import QgsWkbTypes
        return getattr(QgsWkbTypes, type_name, None)
    except (ImportError, AttributeError):
        return None


# =============================================================================
# DEPRECATED API WARNINGS
# =============================================================================

def emit_deprecation_warning(old_api: str, new_api: str, version: str = "3.30"):
    """Emit a deprecation warning for old API usage."""
    warnings.warn(
        f"{old_api} is deprecated in QGIS {version}+. Use {new_api} instead.",
        DeprecationWarning,
        stacklevel=3
    )


# =============================================================================
# SAFE IMPORTS
# =============================================================================

def safe_import_qgis_core(*names):
    """
    Safely import multiple items from qgis.core.

    Returns a dict of {name: value} for successful imports, None for failures.

    Example:
        imports = safe_import_qgis_core('QgsProject', 'QgsVectorLayer', 'QgsWkbTypes')
        QgsProject = imports.get('QgsProject')
    """
    result = {}
    try:
        from qgis import core
        for name in names:
            result[name] = getattr(core, name, None)
    except ImportError:
        for name in names:
            result[name] = None
    return result


# =============================================================================
# VERSION-SPECIFIC FEATURE CHECKS
# =============================================================================

def has_feature(feature_name: str) -> bool:
    """
    Check if a QGIS feature is available in current version.

    Args:
        feature_name: Feature identifier

    Returns:
        True if feature is available
    """
    feature_requirements = {
        'qgis_renderunit_namespace': QGIS_3_30,
        'qgis_distanceunit_namespace': QGIS_3_30,
        'label_placement_enum': QGIS_3_30,
        'mesh_layer': QGIS_3_28,
        'annotation_layer': QGIS_3_22,
        'temporal_controller': QGIS_3_22,
    }

    min_version = feature_requirements.get(feature_name.lower(), 0)
    return QGIS_VERSION_INT >= min_version


# =============================================================================
# COMPATIBILITY WRAPPER FOR QgsUnitTypes
# =============================================================================

class CompatUnitTypes:
    """
    Wrapper class providing unified access to unit types across QGIS versions.

    Usage:
        from fiberq.utils.compat import UnitTypes
        symbol.setSizeUnit(UnitTypes.RenderMetersInMapUnits)
    """

    def __getattr__(self, name: str):
        """Dynamically resolve unit type attributes."""
        # Check if it's a Render unit
        if name.startswith('Render'):
            unit_name = name[6:]  # Strip 'Render' prefix
            result = get_render_unit(unit_name)
            if result is not None:
                return result

        # Check if it's a Distance unit
        if name.startswith('Distance'):
            unit_name = name[8:]  # Strip 'Distance' prefix
            result = get_distance_unit(unit_name)
            if result is not None:
                return result

        # Fall back to QgsUnitTypes
        try:
            from qgis.core import QgsUnitTypes
            return getattr(QgsUnitTypes, name)
        except (ImportError, AttributeError):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")


# Singleton for convenient import
UnitTypes = CompatUnitTypes()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Version info
    'QGIS_VERSION',
    'QGIS_VERSION_INT',
    'get_qgis_version',
    'check_minimum_version',
    'get_version_string',
    # Version thresholds
    'QGIS_3_22',
    'QGIS_3_28',
    'QGIS_3_30',
    'QGIS_3_34',
    'QGIS_3_36',
    'QGIS_3_40',
    # Unit helpers
    'get_render_unit',
    'get_distance_unit',
    'get_geometry_type',
    'get_label_placement',
    'get_wkb_type',
    # Render unit constants
    'RenderMillimeters',
    'RenderMapUnits',
    'RenderPixels',
    'RenderMetersInMapUnits',
    'RenderPoints',
    'RenderInches',
    'RenderPercentage',
    # Distance unit constants
    'DistanceMeters',
    'DistanceKilometers',
    'DistanceFeet',
    'DistanceMiles',
    'DistanceYards',
    # Geometry type constants
    'PointGeometry',
    'LineGeometry',
    'PolygonGeometry',
    'UnknownGeometry',
    'NullGeometry',
    # Wrapper classes
    'UnitTypes',
    'RenderUnit',
    # Utilities
    'has_feature',
    'safe_import_qgis_core',
    'emit_deprecation_warning',
]
