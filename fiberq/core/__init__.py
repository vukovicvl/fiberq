"""
FiberQ v2 - Core Package

This package contains the core functionality of the FiberQ plugin
including configuration management, layer management, style management,
data management, export functionality, and license management.

Modules:
- config_manager.py: Configuration handling (Phase 1)
- license_manager.py: Pro license management (Phase 1.2)
- layer_manager.py: Layer creation and management (Phase 6)
- style_manager.py: Layer styling (Phase 7)
- data_manager.py: Data persistence and management (Phase 8)
- export_manager.py: Export functionality (Phase 8)
"""

from .config_manager import (
    ConfigManager,
    PluginConfig,
    WebConfig,
    LayerConfig,
    get_config_manager,
    get_config,
    get_language,
    set_language,
    is_pro_enabled,
    validate_pro_key,
)

# Phase 1.2: License Manager
from .license_manager import (
    # Legacy API (backward compatibility)
    _fiberq_is_pro_enabled,
    _fiberq_set_pro_enabled,
    _fiberq_validate_pro_key,
    _fiberq_check_pro,
    # New API
    is_pro_enabled as license_is_pro_enabled,
    set_pro_enabled,
    validate_license_key,
    check_pro_access,
    reset_pro_license,
)

from .layer_manager import (
    LayerManager,
    get_layer_manager,
    # Phase 1.3: Layer utility functions
    ELEMENT_DEFS,
    NASTAVAK_DEF,
    _normalize_name,
    _default_fields_for,
    _apply_fixed_text_label,
    _element_def_by_name,
    _ensure_element_layer_with_style,
    _copy_attributes_between_layers,
    _ensure_region_layer,
    _collect_selected_geometries,
    _create_region_from_selection,
    _set_objects_layer_alias,
    _apply_objects_field_aliases,
    _ensure_objects_layer,
    _stylize_objects_layer,
    _telecom_save_all_layers_to_gpkg,
    _telecom_export_one_layer_to_gpkg,
)

from .style_manager import (
    StyleManager,
    get_style_manager,
    stylize_objects_layer,
)

from .data_manager import (
    DataManager,
    get_data_manager,
)

from .export_manager import (
    ExportManager,
    get_export_manager,
    save_all_layers_to_gpkg,
    export_one_layer_to_gpkg,
)

# Phase 3.1: Slack Manager
from .slack_manager import SlackManager

# Phase 3.2: Route Manager
from .route_manager import (
    RouteManager,
    ROUTE_TYPE_OPTIONS,
    ROUTE_TYPE_LABELS,
    ROUTE_LABEL_TO_CODE,
    TRASA_TYPE_OPTIONS,
    TRASA_TYPE_LABELS,
    TRASA_LABEL_TO_CODE,
)

# Phase 3.3: Cable Manager
from .cable_manager import CableManager

# Phase 3.4: Relations Manager
from .relations_manager import RelationsManager

# Phase 3.5: Drawing Manager
from .drawing_manager import DrawingManager

# Phase 3.6: Pipe Manager
from .pipe_manager import PipeManager

# Phase 3.7: Color Manager
from .color_manager import ColorManager

__all__ = [
    # Config Manager
    'ConfigManager',
    'PluginConfig',
    'WebConfig',
    'LayerConfig',
    'get_config_manager',
    'get_config',
    'get_language',
    'set_language',
    'is_pro_enabled',
    'validate_pro_key',

    # License Manager (Phase 1.2) - Legacy API
    '_fiberq_is_pro_enabled',
    '_fiberq_set_pro_enabled',
    '_fiberq_validate_pro_key',
    '_fiberq_check_pro',

    # License Manager (Phase 1.2) - New API
    'license_is_pro_enabled',
    'set_pro_enabled',
    'validate_license_key',
    'check_pro_access',
    'reset_pro_license',

    # Layer Manager (Phase 6)
    'LayerManager',
    'get_layer_manager',

    # Layer Manager (Phase 1.3) - Layer utility functions
    'ELEMENT_DEFS',
    'NASTAVAK_DEF',
    '_normalize_name',
    '_default_fields_for',
    '_apply_fixed_text_label',
    '_element_def_by_name',
    '_ensure_element_layer_with_style',
    '_copy_attributes_between_layers',
    '_ensure_region_layer',
    '_collect_selected_geometries',
    '_create_region_from_selection',
    '_set_objects_layer_alias',
    '_apply_objects_field_aliases',
    '_ensure_objects_layer',
    '_stylize_objects_layer',
    '_telecom_save_all_layers_to_gpkg',
    '_telecom_export_one_layer_to_gpkg',

    # Style Manager (Phase 7)
    'StyleManager',
    'get_style_manager',
    'stylize_objects_layer',

    # Data Manager (Phase 8)
    'DataManager',
    'get_data_manager',

    # Export Manager (Phase 8)
    'ExportManager',
    'get_export_manager',
    'save_all_layers_to_gpkg',
    'export_one_layer_to_gpkg',

    # Slack Manager (Phase 3.1)
    'SlackManager',

    # Route Manager (Phase 3.2)
    'RouteManager',
    'ROUTE_TYPE_OPTIONS',
    'ROUTE_TYPE_LABELS',
    'ROUTE_LABEL_TO_CODE',
    'TRASA_TYPE_OPTIONS',
    'TRASA_TYPE_LABELS',
    'TRASA_LABEL_TO_CODE',

    # Cable Manager (Phase 3.3)
    'CableManager',

    # Relations Manager (Phase 3.4)
    'RelationsManager',

    # Drawing Manager (Phase 3.5)
    'DrawingManager',

    # Pipe Manager (Phase 3.6)
    'PipeManager',

    # Color Manager (Phase 3.7)
    'ColorManager',
]
