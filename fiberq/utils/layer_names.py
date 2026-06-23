"""
FiberQ Layer Names and Project Keys - Compatibility Constants

Phase 6.1: These string constants are used for backward compatibility with
existing .qgz project files and GeoPackage databases.

IMPORTANT: These strings MUST NOT be changed as they are persisted in:
- .qgz project files (layer names, project entries)
- GeoPackage files (table names)
- User data files

For user-facing display, use layer aliases (set_layer_alias functions).
"""


class LayerNames:
    """
    Internal layer names saved in projects and databases.

    These are the actual layer names used in QgsProject.mapLayersByName().
    They should not be changed to maintain backward compatibility.

    For user-friendly display, layer aliases can be applied separately.
    """

    # ==== Route/Trasa ====
    ROUTE = 'Route'
    ROUTE_SR = 'Trasa'  # Legacy Serbian name

    # ==== Cables/Kablovi ====
    CABLES_AERIAL = 'Aerial cables'
    CABLES_UNDERGROUND = 'Underground cables'
    CABLES_AERIAL_SR = 'Kablovi_vazdusni'  # Legacy
    CABLES_UNDERGROUND_SR = 'Kablovi_podzemni'  # Legacy

    # ==== Poles/Stubovi ====
    POLES = 'Poles'
    POLES_SR = 'Stubovi'  # Legacy

    # ==== Manholes/Okna ====
    MANHOLES = 'Manholes'
    MANHOLES_SR = 'Okna'  # Legacy
    MANHOLES_SR_ALT = 'OKNA'  # Legacy variant

    # ==== Joint Closures/Nastavci ====
    JOINT_CLOSURES = 'Joint Closures'
    JOINT_CLOSURES_SR = 'Nastavci'  # Legacy

    # ==== Pipes/Cevi ====
    PIPES_PE = 'PE pipes'
    PIPES_TRANSITION = 'Transition pipes'
    PIPES_PE_SR = 'PE cevi'  # Legacy
    PIPES_TRANSITION_SR = 'Prelazne cevi'  # Legacy

    # ==== Slacks/Optical Reserves ====
    SLACKS = 'Optical slacks'
    SLACKS_SR = 'Rezerve'  # Legacy

    # ==== Drawings/Crtezi ====
    DRAWINGS = 'Drawings'
    DRAWINGS_SR = 'Crtezi'  # Legacy

    # ==== Service Area/Region ====
    SERVICE_AREA = 'Service area'
    REGION = 'Rejon'  # Internal name (kept for backward compat)

    # ==== Objects ====
    OBJECTS = 'Objects'
    OBJECTS_SR = 'Objekti'  # Legacy

    # ==== Fiber Break ====
    FIBER_BREAK = 'Fiber break'

    # ==== Element Types ====
    # These are used for element layer names
    ODF = 'ODF'
    TB = 'TB'
    OTB = 'OTB'
    PATCH_PANEL = 'Patch panel'
    TO = 'TO'
    INDOOR_OTB = 'Indoor OTB'
    OUTDOOR_OTB = 'Outdoor OTB'
    POLE_OTB = 'Pole OTB'
    INDOOR_TO = 'Indoor TO'
    OUTDOOR_TO = 'Outdoor TO'
    POLE_TO = 'Pole TO'
    JOINT_CLOSURE_TO = 'Joint Closure TO'


class ProjectKeys:
    """
    QgsProject custom property keys.

    These are saved in .qgz project files and MUST NOT be changed
    for backward compatibility.
    """
    # Main scope for all FiberQ project entries
    SCOPE = 'StuboviPlugin'  # Keep original name for compatibility

    # Data storage keys
    RELATIONS = 'relations_data'
    LATENT = 'latent_data'
    COLOR_CATALOGS = 'color_catalogs'
    GPKG_PATH = 'gpkg_path'
    AUTO_GPKG_ENABLED = 'auto_gpkg_enabled'
    LANGUAGE = 'lang'

    # Drawing associations
    DRAWING_PREFIX = 'drawing_'

    # Image associations
    IMAGE_PREFIX = 'fiberq_image_'


class CableTypes:
    """Cable type identifiers used in data storage."""

    # Route types
    AERIAL = 'vazdusni'
    UNDERGROUND = 'podzemni'
    THROUGH_BUILDING = 'kroz objekat'

    # Cable classes
    BACKBONE = 'glavni'
    DISTRIBUTION = 'distributivni'
    DROP = 'razvodnik'

    # Display labels (English)
    AERIAL_LABEL = 'Aerial'
    UNDERGROUND_LABEL = 'Underground'
    THROUGH_BUILDING_LABEL = 'Through the object'
    BACKBONE_LABEL = 'Backbone'
    DISTRIBUTION_LABEL = 'Distribution'
    DROP_LABEL = 'Drop'


class GroupNames:
    """Layer tree group names."""

    # Main group
    FIBERQ = 'FiberQ'

    # Subgroups
    CABLES = 'Cables'
    ELEMENTS = 'Elements'
    PIPES = 'Pipes'
    DRAWINGS = 'Drawings'

    # Legacy Serbian names
    CABLES_SR = 'Kablovi'
    ELEMENTS_SR = 'Elementi'
    PIPES_SR = 'Cevi'
    DRAWINGS_SR = 'Crtezi'


# =============================================================================
# Helper functions for finding layers by name (with fallback to legacy names)
# =============================================================================

def get_route_names():
    """Get all possible route layer names."""
    return [LayerNames.ROUTE, LayerNames.ROUTE_SR]


def get_poles_names():
    """Get all possible poles layer names."""
    return [LayerNames.POLES, LayerNames.POLES_SR]


def get_manholes_names():
    """Get all possible manholes layer names."""
    return [LayerNames.MANHOLES, LayerNames.MANHOLES_SR, LayerNames.MANHOLES_SR_ALT]


def get_joint_closures_names():
    """Get all possible joint closures layer names."""
    return [LayerNames.JOINT_CLOSURES, LayerNames.JOINT_CLOSURES_SR]


def get_aerial_cable_names():
    """Get all possible aerial cable layer names."""
    return [LayerNames.CABLES_AERIAL, LayerNames.CABLES_AERIAL_SR]


def get_underground_cable_names():
    """Get all possible underground cable layer names."""
    return [LayerNames.CABLES_UNDERGROUND, LayerNames.CABLES_UNDERGROUND_SR]


def get_slacks_names():
    """Get all possible slacks layer names."""
    return [LayerNames.SLACKS, LayerNames.SLACKS_SR]


def get_region_names():
    """Get all possible region/service area layer names."""
    return [LayerNames.SERVICE_AREA, LayerNames.REGION]


def is_route_layer(layer_name: str) -> bool:
    """Check if layer name matches route layer."""
    return layer_name in get_route_names()


def is_cable_layer(layer_name: str) -> bool:
    """Check if layer name matches any cable layer."""
    return (layer_name in get_aerial_cable_names() or  # noqa: W504
            layer_name in get_underground_cable_names())


def is_pipe_layer(layer_name: str) -> bool:
    """Check if layer name matches any pipe layer."""
    return layer_name in [
        LayerNames.PIPES_PE, LayerNames.PIPES_PE_SR,
        LayerNames.PIPES_TRANSITION, LayerNames.PIPES_TRANSITION_SR
    ]


# =============================================================================
# Translation mappings (for internal code, not persisted strings)
# =============================================================================

SERBIAN_TO_ENGLISH = {
    # Nouns
    'trasa': 'route',
    'stub': 'pole',
    'stubovi': 'poles',
    'okno': 'manhole',
    'okna': 'manholes',
    'cev': 'pipe',
    'cevi': 'pipes',
    'rezerva': 'slack',
    'rezerve': 'slacks',
    'crtez': 'drawing',
    'crtezi': 'drawings',
    'rejon': 'region',
    'objekt': 'object',
    'objekti': 'objects',
    'kabl': 'cable',
    'kablovi': 'cables',
    'nastavak': 'joint_closure',
    'nastavci': 'joint_closures',

    # Adjectives
    'vazdusni': 'aerial',
    'podzemni': 'underground',
    'glavni': 'backbone',
    'distributivni': 'distribution',
    'razvodnik': 'drop',

    # Verbs/Actions
    'obrisi': 'delete',
    'selektovane': 'selected',
    'razgrani': 'offset',
    'postavi': 'place',
    'kreiraj': 'create',
    'laying': 'laying',
    'kanalizacija': 'ducting',
    'selection': 'selection',
}

ENGLISH_TO_SERBIAN = {v: k for k, v in SERBIAN_TO_ENGLISH.items()}


__all__ = [
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
]
