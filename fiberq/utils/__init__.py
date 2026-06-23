"""
FiberQ v2 - Utilities Package

This package contains utility modules for the FiberQ plugin.

Modules:
- constants.py: All constants and enums
- helpers.py: General helper functions
- geometry.py: Geometry utility functions (Phase 2)
- routing.py: Path finding algorithms (Phase 2)
- field_aliases.py: Field alias mappings and functions (Phase 2)
- logger.py: Centralized logging infrastructure (Phase 5.1)
- layer_names.py: Layer name constants for backward compatibility (Phase 6.1)
"""

from .helpers import (
    # Path utilities
    get_plugin_dir,
    get_icon_path,
    get_map_icon_path,
    get_style_path,

    # Icon loading
    load_icon,
    get_element_icon,

    # Icon loading (legacy names - Phase 1.1)
    _icon_path,
    _load_icon,
    _map_icon_path,
    _element_icon_for,

    # Text utilities
    normalize_name,
    clean_layer_name,

    # Label utilities
    apply_fixed_text_label,
    apply_field_aliases as apply_field_aliases_generic,

    # Language settings
    get_language,
    set_language,

    # Language settings (legacy names - Phase 1.1)
    _get_lang,
    _set_lang,
    _fiberq_translate,
    _apply_text_and_tooltip,
    _apply_menu_language,
    translate_text,

    # Layer detection
    find_layer_by_name,
    find_layers_by_names,
    is_pole_layer,
    # NOTE: is_route_layer / is_cable_layer are re-exported below from
    # .layer_names (Phase 6.1), which already shadowed these at runtime.
)

from .constants import (
    # Route types
    RouteType,
    ROUTE_TYPE_OPTIONS,
    ROUTE_TYPE_LABELS,
    ROUTE_LABEL_TO_CODE,

    # Cable types
    CableSubtype,
    CABLE_SUBTYPE_LABELS,

    # Location types
    LocationType,
    LOCATION_TYPE_LABELS,

    # Slack types
    SlackType,
    SLACK_TYPE_LABELS,

    # Colors
    COLOR_BACKBONE,
    COLOR_DISTRIBUTION,
    COLOR_DROP,

    # Field names and aliases
    FieldNames,
    FIELD_ALIASES,

    # Layer names
    # NOTE: LayerNames is re-exported below from .layer_names (Phase 6.1),
    # which already shadowed the .constants version at runtime.
    LAYER_NAME_MAPPING,

    # Status
    ElementStatus,
    STATUS_OPTIONS,

    # Settings
    SettingsKeys,

    # Backward compatibility
    TRASA_TYPE_OPTIONS,
    TRASA_TYPE_LABELS,
    TRASA_LABEL_TO_CODE,
    COLOR_GLAVNI,
    COLOR_DISTR,
    COLOR_RAZV,
)

# Phase 2: Geometry utilities
from .geometry import (
    round_key,
    fuzzy_key,
    get_first_last_points,
    extract_line_vertices,
    convert_to_simple_line,
    snap_point_to_layer,
    find_nearest_vertex,
    points_equal,
    point_distance,
    point_distance_squared,
    split_line_at_point,
    merge_lines,
    get_layer_extent_center,
    calculate_geometry_length,
)

# Phase 2: Routing utilities
from .routing import (
    build_network_graph,
    build_adjacency_list,
    find_path_bfs,
    build_path_across_network,
    build_path_across_joined_routes,
    find_route_between_points,
    get_network_connectivity,
    find_endpoints_on_network,
)

# Phase 2: Field alias utilities
from .field_aliases import (
    # Alias mappings
    POLES_FIELD_ALIASES,
    ROUTE_FIELD_ALIASES,
    CABLE_FIELD_ALIASES,
    MANHOLE_FIELD_ALIASES,
    SLACK_FIELD_ALIASES,
    PIPE_FIELD_ALIASES,
    JOINT_CLOSURE_FIELD_ALIASES,
    FIBER_BREAK_FIELD_ALIASES,
    OBJECTS_FIELD_ALIASES,
    ELEMENT_FIELD_ALIASES,

    # Value maps
    ROUTE_TYPE_VALUE_MAP,
    SLACK_LOCATION_VALUE_MAP,
    SLACK_SIDE_VALUE_MAP,
    CABLE_TYPE_VALUE_MAP,
    CABLE_SUBTYPE_VALUE_MAP,

    # Application functions
    apply_field_aliases,
    apply_value_map,
    apply_poles_field_aliases,
    apply_route_field_aliases,
    apply_cable_field_aliases,
    apply_manhole_field_aliases,
    apply_slack_field_aliases,
    apply_pipe_field_aliases,
    apply_joint_closure_aliases,
    apply_fiber_break_aliases,
    apply_objects_field_aliases,
    apply_element_aliases,

    # Layer name aliases
    set_layer_display_name,
    set_route_layer_alias,
    set_manhole_layer_alias,
    set_slack_layer_alias,
    set_joint_closure_layer_alias,
    set_pipe_layer_alias,
    set_objects_layer_alias,
)

# Phase 5.1: Logging infrastructure
from .logger import (
    # Main logger function
    get_logger,

    # Convenience functions
    log_exception,
    log_warning,
    log_error,
    log_debug,
    log_info,

    # Configuration
    set_log_level,
    get_log_file_path,
    is_debug_enabled,

    # Handler class
    QgsLogHandler,
)

# Phase 6.1: Layer names and project keys
from .layer_names import (
    # Layer name constants
    LayerNames,
    ProjectKeys,
    CableTypes,
    GroupNames,

    # Helper functions
    get_route_names,
    get_poles_names,
    get_manholes_names,
    get_joint_closures_names,
    get_aerial_cable_names,
    get_underground_cable_names,
    get_slacks_names,
    get_region_names,
    is_route_layer,
    is_cable_layer,
    is_pipe_layer,

    # Translation mappings
    SERBIAN_TO_ENGLISH,
    ENGLISH_TO_SERBIAN,
)

# Phase 1.1 (v1.1): QGIS Version Compatibility
from .compat import (
    # Version info
    QGIS_VERSION,
    QGIS_VERSION_INT,
    get_qgis_version,
    check_minimum_version,
    get_version_string,

    # Version thresholds
    QGIS_3_22,
    QGIS_3_28,
    QGIS_3_30,
    QGIS_3_34,
    QGIS_3_36,
    QGIS_3_40,

    # Unit helpers
    get_render_unit,
    get_distance_unit,
    get_geometry_type,
    get_label_placement,
    get_wkb_type,

    # Render unit constants
    RenderMillimeters,
    RenderMapUnits,
    RenderPixels,
    RenderMetersInMapUnits,
    RenderPoints,
    RenderInches,
    RenderPercentage,

    # Distance unit constants
    DistanceMeters,
    DistanceKilometers,
    DistanceFeet,
    DistanceMiles,
    DistanceYards,

    # Geometry type constants
    PointGeometry,
    LineGeometry,
    PolygonGeometry,
    UnknownGeometry,
    NullGeometry,

    # Wrapper classes
    UnitTypes,

    # Utilities
    has_feature,
    safe_import_qgis_core,
)

__all__ = [
    # Path utilities
    'get_plugin_dir',
    'get_icon_path',
    'get_map_icon_path',
    'get_style_path',

    # Icon loading
    'load_icon',
    'get_element_icon',

    # Icon loading (legacy names - Phase 1.1)
    '_icon_path',
    '_load_icon',
    '_map_icon_path',
    '_element_icon_for',

    # Text utilities
    'normalize_name',
    'clean_layer_name',

    # Label utilities
    'apply_fixed_text_label',
    'apply_field_aliases_generic',

    # Language settings
    'get_language',
    'set_language',

    # Language settings (legacy names - Phase 1.1)
    '_get_lang',
    '_set_lang',
    '_fiberq_translate',
    '_apply_text_and_tooltip',
    '_apply_menu_language',
    'translate_text',

    # Layer detection
    'find_layer_by_name',
    'find_layers_by_names',
    'is_route_layer',
    'is_cable_layer',
    'is_pole_layer',

    # Route types
    'RouteType',
    'ROUTE_TYPE_OPTIONS',
    'ROUTE_TYPE_LABELS',
    'ROUTE_LABEL_TO_CODE',

    # Cable types
    'CableSubtype',
    'CABLE_SUBTYPE_LABELS',

    # Location types
    'LocationType',
    'LOCATION_TYPE_LABELS',

    # Slack types
    'SlackType',
    'SLACK_TYPE_LABELS',

    # Colors
    'COLOR_BACKBONE',
    'COLOR_DISTRIBUTION',
    'COLOR_DROP',

    # Field names and aliases
    'FieldNames',
    'FIELD_ALIASES',

    # Layer names
    'LayerNames',
    'LAYER_NAME_MAPPING',

    # Status
    'ElementStatus',
    'STATUS_OPTIONS',

    # Settings
    'SettingsKeys',

    # Backward compatibility
    'TRASA_TYPE_OPTIONS',
    'TRASA_TYPE_LABELS',
    'TRASA_LABEL_TO_CODE',
    'COLOR_GLAVNI',
    'COLOR_DISTR',
    'COLOR_RAZV',

    # Phase 2: Geometry utilities
    'round_key',
    'fuzzy_key',
    'get_first_last_points',
    'extract_line_vertices',
    'convert_to_simple_line',
    'snap_point_to_layer',
    'find_nearest_vertex',
    'points_equal',
    'point_distance',
    'point_distance_squared',
    'split_line_at_point',
    'merge_lines',
    'get_layer_extent_center',
    'calculate_geometry_length',

    # Phase 2: Routing utilities
    'build_network_graph',
    'build_adjacency_list',
    'find_path_bfs',
    'build_path_across_network',
    'build_path_across_joined_routes',
    'find_route_between_points',
    'get_network_connectivity',
    'find_endpoints_on_network',

    # Phase 2: Field alias mappings
    'POLES_FIELD_ALIASES',
    'ROUTE_FIELD_ALIASES',
    'CABLE_FIELD_ALIASES',
    'MANHOLE_FIELD_ALIASES',
    'SLACK_FIELD_ALIASES',
    'PIPE_FIELD_ALIASES',
    'JOINT_CLOSURE_FIELD_ALIASES',
    'FIBER_BREAK_FIELD_ALIASES',
    'OBJECTS_FIELD_ALIASES',
    'ELEMENT_FIELD_ALIASES',

    # Phase 2: Value maps
    'ROUTE_TYPE_VALUE_MAP',
    'SLACK_LOCATION_VALUE_MAP',
    'SLACK_SIDE_VALUE_MAP',
    'CABLE_TYPE_VALUE_MAP',
    'CABLE_SUBTYPE_VALUE_MAP',

    # Phase 2: Alias application functions
    'apply_field_aliases',
    'apply_value_map',
    'apply_poles_field_aliases',
    'apply_route_field_aliases',
    'apply_cable_field_aliases',
    'apply_manhole_field_aliases',
    'apply_slack_field_aliases',
    'apply_pipe_field_aliases',
    'apply_joint_closure_aliases',
    'apply_fiber_break_aliases',
    'apply_objects_field_aliases',
    'apply_element_aliases',

    # Phase 2: Layer name aliases
    'set_layer_display_name',
    'set_route_layer_alias',
    'set_manhole_layer_alias',
    'set_slack_layer_alias',
    'set_joint_closure_layer_alias',
    'set_pipe_layer_alias',
    'set_objects_layer_alias',

    # Phase 5.1: Logging infrastructure
    'get_logger',
    'log_exception',
    'log_warning',
    'log_error',
    'log_debug',
    'log_info',
    'set_log_level',
    'get_log_file_path',
    'is_debug_enabled',
    'QgsLogHandler',

    # Phase 6.1: Layer names and project keys
    'LayerNames',
    'ProjectKeys',
    'CableTypes',
    'GroupNames',
    'get_route_names',
    'get_poles_names',
    'get_manholes_names',
    'get_joint_closures_names',
    'get_aerial_cable_names',
    'get_underground_cable_names',
    'get_slacks_names',
    'get_region_names',
    'is_route_layer',
    'is_cable_layer',
    'is_pipe_layer',
    'SERBIAN_TO_ENGLISH',
    'ENGLISH_TO_SERBIAN',

    # Phase 1.1 (v1.1): QGIS Version Compatibility
    'QGIS_VERSION',
    'QGIS_VERSION_INT',
    'get_qgis_version',
    'check_minimum_version',
    'get_version_string',
    'QGIS_3_22',
    'QGIS_3_28',
    'QGIS_3_30',
    'QGIS_3_34',
    'QGIS_3_36',
    'QGIS_3_40',
    'get_render_unit',
    'get_distance_unit',
    'get_geometry_type',
    'get_label_placement',
    'get_wkb_type',
    'RenderMillimeters',
    'RenderMapUnits',
    'RenderPixels',
    'RenderMetersInMapUnits',
    'RenderPoints',
    'RenderInches',
    'RenderPercentage',
    'DistanceMeters',
    'DistanceKilometers',
    'DistanceFeet',
    'DistanceMiles',
    'DistanceYards',
    'PointGeometry',
    'LineGeometry',
    'PolygonGeometry',
    'UnknownGeometry',
    'NullGeometry',
    'UnitTypes',
    'has_feature',
    'safe_import_qgis_core',
]
