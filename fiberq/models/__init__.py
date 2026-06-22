"""
FiberQ v2 - Models Package

This package contains data models and definitions for the FiberQ plugin.
"""

from .element_defs import (
    # Symbol and element definitions
    SymbolSpec,
    ElementDefinition,
    ELEMENT_DEFS,
    JOINT_CLOSURE_DEF,
    NASTAVAK_DEF,  # Backward compatibility

    # Icon mapping
    ELEMENT_ICON_MAP,
    get_element_icon_filename,
    get_element_def_by_name,

    # Field definitions
    FieldDefinition,
    DEFAULT_ELEMENT_FIELDS,
    get_default_fields_for_layer,

    # Aliases
    ELEMENT_FIELD_ALIASES,
    apply_element_aliases,
)

from .color_catalogs import (
    # Color definitions
    FiberColor,
    STANDARD_FIBER_COLORS,

    # Catalog management
    ColorCatalog,
    ColorCatalogManager,
    get_default_color_catalogs,
    get_default_color_sets,

    # Utilities
    get_fiber_color_by_position,
    format_fiber_color_label,
)

__all__ = [
    # Element definitions
    'SymbolSpec',
    'ElementDefinition',
    'ELEMENT_DEFS',
    'JOINT_CLOSURE_DEF',
    'NASTAVAK_DEF',

    # Icon mapping
    'ELEMENT_ICON_MAP',
    'get_element_icon_filename',
    'get_element_def_by_name',

    # Field definitions
    'FieldDefinition',
    'DEFAULT_ELEMENT_FIELDS',
    'get_default_fields_for_layer',

    # Aliases
    'ELEMENT_FIELD_ALIASES',
    'apply_element_aliases',

    # Color definitions
    'FiberColor',
    'STANDARD_FIBER_COLORS',

    # Catalog management
    'ColorCatalog',
    'ColorCatalogManager',
    'get_default_color_catalogs',
    'get_default_color_sets',

    # Utilities
    'get_fiber_color_by_position',
    'format_fiber_color_label',
]
