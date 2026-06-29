"""FiberQ canonical data-model schema — the single source of truth (WP1a).

This is a **pure-data** module: no QGIS imports, no filesystem side effects. It
describes every FiberQ layer type, its fields (name / type / units / domain /
default), the legacy<->canonical layer-name map, the per-layer field aliases and
value maps, and the project ``SCHEMA_VERSION`` marker.

Important invariants (do not break without a migration):

* **Field NAMES are the stored database schema** (legacy, mostly Serbian). The
  English strings here are display-only *aliases* / labels. Renaming a stored
  field is a data migration, not a cosmetic change.
* ``fiberq_uuid`` is the per-feature **identity** field; it is present on every
  layer (appended at layer creation by ``utils.uuid_utils``).
* The plugin version (``metadata.txt``) and the project ``SCHEMA_VERSION`` are
  tracked **separately** and bump independently.

This module is authored to match what the plugin creates today; the existing
modules (``element_defs``, ``field_aliases``, ``dialogs.base``, ``legacy_bridge``)
delegate to it so there is one definition. The human-readable reference generated
from this model lives in ``docs/schema.md``.

Known as-built inconsistencies are preserved here verbatim (not "fixed") and are
documented as deferred items for the interchange work — see ``docs/schema.md``.
"""
from dataclasses import dataclass, field as _dc_field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Version marker
# ---------------------------------------------------------------------------

#: FiberQ project schema version. Decoupled from the plugin version in
#: metadata.txt. Persisted into a project on save (see core/schema_version.py).
#: Projects created before this marker existed read back as absent -> treated as
#: the pre-marker baseline (schema version 0).
SCHEMA_VERSION = "1.0"

#: The per-feature identity field appended to every FiberQ layer.
IDENTITY_FIELD = "fiberq_uuid"

#: Accepted logical field types (stored representation in parentheses):
#: text(String), int(Int), double(Double), enum(String), year(Int), bool(Bool).
FIELD_TYPES = ("text", "int", "double", "enum", "year", "bool")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FieldDefinition:
    """One attribute field of a FiberQ layer.

    ``key`` is the stored field name (immutable schema). ``label`` is the
    English label used by the placement dialogs. ``options`` lists the choices
    for ``enum`` fields. ``value_map`` (when set) maps an English display value
    to the value actually stored (QGIS ValueMap widget).
    """
    key: str
    label: str
    field_type: str  # one of FIELD_TYPES
    default: Any = ""
    options: Optional[List[str]] = None
    units: str = ""
    value_map: Optional[Dict[str, str]] = None


@dataclass
class LayerSchema:
    """A FiberQ layer type: its canonical name, geometry, CRS source and fields."""
    canonical_name: str
    geometry: str            # 'Point' | 'LineString' | 'Polygon'
    crs_source: str          # 'canvas' (canvas destination CRS) | 'project'
    fields: List[FieldDefinition]
    legacy_names: List[str] = _dc_field(default_factory=list)
    aliases: Dict[str, str] = _dc_field(default_factory=dict)  # field key -> attribute-table alias
    identity_field: str = IDENTITY_FIELD
    notes: str = ""


def _uuid_field() -> FieldDefinition:
    """The identity field, as it is appended on every layer."""
    return FieldDefinition(IDENTITY_FIELD, "FiberQ UUID", "text", "")


# ---------------------------------------------------------------------------
# Value maps (English display label -> stored value). Verbatim as-built.
# ---------------------------------------------------------------------------

ROUTE_TYPE_VALUE_MAP: Dict[str, str] = {
    "Aerial": "vazdusna",
    "Underground": "podzemna",
    "Through the object": "kroz objekat",
}
SLACK_LOCATION_VALUE_MAP: Dict[str, str] = {
    "Manhole": "OKNO",
    "Pole": "Stub",
    "Object": "Objekat",
}
SLACK_SIDE_VALUE_MAP: Dict[str, str] = {
    "FROM": "od",
    "TO": "do",
    "MID SPAN": "sredina",
}
CABLE_TYPE_VALUE_MAP: Dict[str, str] = {
    "Optical": "opticki",
    "Copper": "bakarnI",  # NOTE: as-built typo (capital I); preserved, see docs/schema.md
}
CABLE_SUBTYPE_VALUE_MAP: Dict[str, str] = {
    "Backbone": "glavni",
    "Distribution": "distributivni",
    "Drop": "razvodni",
}
CABLE_STATUS_VALUE_MAP: Dict[str, str] = {
    "Planned": "Projektovano",
    "Existing": "Postojeće",
    "Under construction": "U izgradnji",
}
CABLE_LAYING_VALUE_MAP: Dict[str, str] = {
    "Underground": "Podzemno",
    "Aerial": "Vazdusno",
}


# ---------------------------------------------------------------------------
# Field-alias maps (stored field name -> attribute-table display alias).
# Layer-scoped: the same key maps to different labels on different layers.
# ---------------------------------------------------------------------------

ELEMENT_FIELD_ALIASES: Dict[str, str] = {
    "naziv": "Name",
    "proizvodjac": "Manufacturer",
    "oznaka": "Label",
    "kapacitet": "Capacity",
    "ukupno_kj": "Total SCs",
    "zahtev_kapaciteta": "Required capacity",
    "zahtev_rezerve": "Reserve capacity",
    "oznaka_izvoda": "Port label",
    "numeracija": "Numbering",
    "naziv_objekta": "Site name",
    "adresa_ulica": "Street",
    "adresa_broj": "Street No.",
    "address_id": "Address ID",
    "stanje": "Status",
    "godina_ugradnje": "Install year",
    "fiberq_uuid": "FiberQ UUID",
}
POLES_FIELD_ALIASES: Dict[str, str] = {
    "tip": "Type",
    "podtip": "Subtype",
    "visina": "Height (m)",
    "materijal": "Material",
    "fiberq_uuid": "FiberQ UUID",
}
ROUTE_FIELD_ALIASES: Dict[str, str] = {
    "naziv": "Route name",
    "duzina": "Length (m)",
    "duzina_km": "Length (km)",
    "tip_trase": "Route type",
    "fiberq_uuid": "FiberQ UUID",
}
CABLE_FIELD_ALIASES: Dict[str, str] = {
    "tip": "Cable type",
    "podtip": "Segment type",
    "color_code": "Color code",
    "broj_cevcica": "Number of ducts",
    "broj_vlakana": "Number of fibers",
    "tip_kabla": "Cable model",
    "vrsta_vlakana": "Fiber type",
    "vrsta_omotaca": "Sheath type",
    "vrsta_armature": "Armour type",
    "talasno_podrucje": "Wavelength band",
    "naziv": "Name",
    "slabljenje_dbkm": "Attenuation [dB/km]",
    "hrom_disp_ps_nmxkm": "Chromatic dispersion [ps/nm/km]",
    "stanje_kabla": "Status",
    "cable_laying": "Installation type",
    "vrsta_mreze": "Network type",
    "godina_ugradnje": "Installation year",
    "konstr_vlakna_u_cevcicama": "Fibers in ducts",
    "konstr_sa_uzlepljenim_elementom": "With bonded element",
    "konstr_punjeni_kabl": "Gel-filled cable",
    "konstr_sa_arm_vlaknima": "Aramid yarn armouring",
    "konstr_bez_metalnih": "Non-metallic",
    "od": "From",
    "do": "To",
    "duzina_m": "Length [m]",
    "slack_m": "Slack [m]",
    "total_len_m": "Total length [m]",
    "fiberq_uuid": "FiberQ UUID",
    "fibers_per_tube": "Fibers per tube",
    "total_fibers": "Total fibers",
    "color_standard": "Color standard",
}
MANHOLE_FIELD_ALIASES: Dict[str, str] = {
    "broj_okna": "Manhole ID",
    "tip_okna": "Manhole type",
    "vrsta_okna": "Construction type",
    "polozaj_okna": "Position",
    "adresa": "Address",
    "stanje": "Status",
    "god_ugrad": "Installation year",
    "opis": "Description",
    "dimenzije": "Dimensions (cm)",
    "mat_zida": "Wall material",
    "mat_poklop": "Cover material",
    "odvodnj": "Drainage",
    "poklop_tes": "Heavy cover",
    "poklop_lak": "Light cover",
    "br_nosaca": "Number of steps",
    "debl_zida": "Wall thickness (cm)",
    "lestve": "Ladder",
    "fiberq_uuid": "FiberQ UUID",
}
SLACK_FIELD_ALIASES: Dict[str, str] = {
    "tip": "Type",
    "duzina_m": "Length (m)",
    "lokacija": "Location",
    "cable_layer_id": "Cable layer ID",
    "cable_fid": "Cable feature ID",
    "strana": "Side",
    "napomena": "Note",
    "fiberq_uuid": "FiberQ UUID",
}
PIPE_FIELD_ALIASES: Dict[str, str] = {
    "materijal": "Material",
    "kapacitet": "Capacity",
    "fi": "Diameter (mm)",
    "od": "From",
    "do": "To",
    "duzina_m": "Length (m)",
    "fiberq_uuid": "FiberQ UUID",
}
JOINT_CLOSURE_FIELD_ALIASES: Dict[str, str] = {
    "naziv": "Name",
    "fiberq_uuid": "FiberQ UUID",
}
FIBER_BREAK_FIELD_ALIASES: Dict[str, str] = {
    "naziv": "Name",
    "cable_layer_id": "Cable layer ID",
    "cable_fid": "Cable feature ID",
    "distance_m": "Distance (m)",
    "segments_hit": "Segments hit",
    "vreme": "Time",
    "fiberq_uuid": "FiberQ UUID",
}
OBJECTS_FIELD_ALIASES: Dict[str, str] = {
    "tip": "Type",
    "spratova": "Floors above ground",
    "podzemnih": "Floors below ground",
    "ulica": "Street",
    "broj": "Number",
    "naziv": "Name",
    "napomena": "Note",
    "fiberq_uuid": "FiberQ UUID",
}


# ---------------------------------------------------------------------------
# Shared element roster (the 15-field point-element schema).
# fiberq_uuid is NOT part of the roster; it is appended separately at creation.
# This is the single definition; element_defs / dialogs.base / legacy_bridge /
# layer_manager delegate to get_default_fields_for_layer().
# ---------------------------------------------------------------------------

SHARED_ELEMENT_FIELDS: List[FieldDefinition] = [
    FieldDefinition("naziv", "Name", "text", ""),
    FieldDefinition("proizvodjac", "Manufacturer", "text", ""),
    FieldDefinition("oznaka", "Label", "text", ""),
    FieldDefinition("kapacitet", "Capacity", "int", 0, units="ports"),
    FieldDefinition("ukupno_kj", "Total", "int", 0),
    FieldDefinition("zahtev_kapaciteta", "Capacity Requirement", "int", 0),
    FieldDefinition("zahtev_rezerve", "Slack Requirement", "int", 0),
    FieldDefinition("oznaka_izvoda", "Outlet Label", "text", ""),
    FieldDefinition("numeracija", "Numbering", "text", ""),
    FieldDefinition("naziv_objekta", "Object Name", "text", ""),
    FieldDefinition("adresa_ulica", "Address Street", "text", ""),
    FieldDefinition("adresa_broj", "Address Number", "text", ""),
    FieldDefinition("address_id", "Address ID", "text", ""),
    FieldDefinition("stanje", "Status", "enum", "Planned", options=["Planned", "Built", "Existing"]),
    FieldDefinition("godina_ugradnje", "Year of Installation", "year", 2025, units="year"),
]

#: Element layer names that share SHARED_ELEMENT_FIELDS (one QGIS layer each).
ELEMENT_LAYER_NAMES: List[str] = [
    "ODF", "TB", "Patch panel", "OTB", "Indoor OTB", "Outdoor OTB", "Pole OTB",
    "TO", "Indoor TO", "Outdoor TO", "Pole TO", "Joint Closure TO",
]

#: Default capacity for OD cabinet ("od ormar") element layers.
OD_CABINET_CAPACITY_DEFAULT = 24


def get_default_fields_for_layer(
    layer_name: str,
) -> List[Tuple[str, str, str, Any, Optional[List[str]]]]:
    """Return the element default fields as ``(key, label, field_type, default, options)`` tuples.

    Mirrors the historical ``element_defs.get_default_fields_for_layer`` contract
    exactly (5-tuples, no ``fiberq_uuid`` — that is appended separately). The only
    per-layer variation is the OD-cabinet capacity default.
    """
    fields = [
        (f.key, f.label, f.field_type, f.default, f.options)
        for f in SHARED_ELEMENT_FIELDS
    ]
    if "od ormar" in (layer_name or "").lower():
        fields = [
            (key, label, ftype, (OD_CABINET_CAPACITY_DEFAULT if key == "kapacitet" else default), opts)
            for (key, label, ftype, default, opts) in fields
        ]
    return fields


# ---------------------------------------------------------------------------
# Non-element layer field rosters
# ---------------------------------------------------------------------------

POLES_FIELDS: List[FieldDefinition] = [
    FieldDefinition("tip", "Type", "text", ""),
    FieldDefinition("podtip", "Subtype", "text", ""),
    FieldDefinition("visina", "Height", "double", 0.0, units="m"),
    FieldDefinition("materijal", "Material", "text", ""),
    _uuid_field(),
]

MANHOLE_FIELDS: List[FieldDefinition] = [
    FieldDefinition("broj_okna", "Manhole ID", "text", ""),
    FieldDefinition("tip_okna", "Manhole type", "text", ""),
    FieldDefinition("vrsta_okna", "Construction type", "text", ""),
    FieldDefinition("polozaj_okna", "Position", "text", ""),
    FieldDefinition("adresa", "Address", "text", ""),
    FieldDefinition("stanje", "Status", "text", ""),  # free text on manholes (no enum)
    FieldDefinition("god_ugrad", "Installation year", "int", 0),
    FieldDefinition("opis", "Description", "text", ""),
    FieldDefinition("dimenzije", "Dimensions", "text", "", units="cm"),
    FieldDefinition("mat_zida", "Wall material", "text", ""),
    FieldDefinition("mat_poklop", "Cover material", "text", ""),
    FieldDefinition("odvodnj", "Drainage", "text", ""),
    FieldDefinition("poklop_tes", "Heavy cover", "bool", False),
    FieldDefinition("poklop_lak", "Light cover", "bool", False),
    FieldDefinition("br_nosaca", "Number of steps", "int", 0),
    FieldDefinition("debl_zida", "Wall thickness", "double", 0.0, units="cm"),
    FieldDefinition("lestve", "Ladder", "text", ""),
    _uuid_field(),
]

ROUTE_FIELDS: List[FieldDefinition] = [
    FieldDefinition("naziv", "Route name", "text", ""),
    FieldDefinition("duzina", "Length", "double", 0.0, units="m"),
    FieldDefinition("duzina_km", "Length", "double", 0.0, units="km"),
    FieldDefinition("tip_trase", "Route type", "text", "", value_map=ROUTE_TYPE_VALUE_MAP),
    _uuid_field(),
]

SLACK_FIELDS: List[FieldDefinition] = [
    FieldDefinition("tip", "Type", "text", ""),
    FieldDefinition("duzina_m", "Length", "double", 0.0, units="m"),
    FieldDefinition("lokacija", "Location", "text", "", value_map=SLACK_LOCATION_VALUE_MAP),
    FieldDefinition("cable_layer_id", "Cable layer ID", "text", ""),
    FieldDefinition("cable_fid", "Cable feature ID", "int", 0),
    FieldDefinition("strana", "Side", "text", "", value_map=SLACK_SIDE_VALUE_MAP),
    FieldDefinition("napomena", "Note", "text", ""),
    _uuid_field(),
]

PIPE_FIELDS: List[FieldDefinition] = [
    FieldDefinition("materijal", "Material", "text", ""),
    FieldDefinition("kapacitet", "Capacity", "text", ""),  # text on pipes (int on elements) - as-built
    FieldDefinition("fi", "Diameter", "int", 0, units="mm"),
    FieldDefinition("od", "From", "text", ""),
    FieldDefinition("do", "To", "text", ""),
    FieldDefinition("duzina_m", "Length", "double", 0.0, units="m"),
    _uuid_field(),
]

SERVICE_AREA_FIELDS: List[FieldDefinition] = [
    FieldDefinition("name", "Name", "text", ""),
    FieldDefinition("created_at", "Created at", "text", ""),
    FieldDefinition("area_m2", "Area", "double", 0.0, units="m²"),
    FieldDefinition("perim_m", "Perimeter", "double", 0.0, units="m"),
    FieldDefinition("count", "Count", "int", 0),
    _uuid_field(),
]

OBJECTS_FIELDS: List[FieldDefinition] = [
    FieldDefinition("tip", "Type", "text", ""),
    FieldDefinition("spratova", "Floors above ground", "int", 0),
    FieldDefinition("podzemnih", "Floors below ground", "int", 0),
    FieldDefinition("ulica", "Street", "text", ""),
    FieldDefinition("broj", "Number", "text", ""),
    FieldDefinition("naziv", "Name", "text", ""),
    FieldDefinition("napomena", "Note", "text", ""),
    _uuid_field(),
]

# Underground and Aerial cables share this roster (created identically).
# NOTE: branch_index (int) is added on demand when a cable is branched; it is not
# part of the freshly-created roster and is intentionally omitted here.
CABLE_FIELDS: List[FieldDefinition] = [
    FieldDefinition("tip", "Cable type", "text", "", value_map=CABLE_TYPE_VALUE_MAP),
    FieldDefinition("podtip", "Segment type", "text", "", value_map=CABLE_SUBTYPE_VALUE_MAP),
    FieldDefinition("color_code", "Color code", "text", ""),
    FieldDefinition("broj_cevcica", "Number of ducts", "int", 0),
    FieldDefinition("broj_vlakana", "Number of fibers", "int", 0),
    FieldDefinition("tip_kabla", "Cable model", "text", ""),
    FieldDefinition("vrsta_vlakana", "Fiber type", "text", ""),
    FieldDefinition("vrsta_omotaca", "Sheath type", "text", ""),
    FieldDefinition("vrsta_armature", "Armour type", "text", ""),
    FieldDefinition("talasno_podrucje", "Wavelength band", "text", ""),
    FieldDefinition("naziv", "Name", "text", ""),
    FieldDefinition("slabljenje_dbkm", "Attenuation", "double", 0.0, units="dB/km"),
    FieldDefinition("hrom_disp_ps_nmxkm", "Chromatic dispersion", "double", 0.0, units="ps/nm/km"),
    FieldDefinition("stanje_kabla", "Status", "text", "", value_map=CABLE_STATUS_VALUE_MAP),
    FieldDefinition("cable_laying", "Installation type", "text", "", value_map=CABLE_LAYING_VALUE_MAP),
    FieldDefinition("vrsta_mreze", "Network type", "text", ""),
    FieldDefinition("godina_ugradnje", "Installation year", "int", 0, units="year"),
    FieldDefinition("konstr_vlakna_u_cevcicama", "Fibers in ducts", "int", 0),
    FieldDefinition("konstr_sa_uzlepljenim_elementom", "With bonded element", "int", 0),
    FieldDefinition("konstr_punjeni_kabl", "Gel-filled cable", "int", 0),
    FieldDefinition("konstr_sa_arm_vlaknima", "Aramid yarn armouring", "int", 0),
    FieldDefinition("konstr_bez_metalnih", "Non-metallic", "int", 0),
    FieldDefinition("od", "From", "text", ""),
    FieldDefinition("do", "To", "text", ""),
    FieldDefinition("duzina_m", "Length", "double", 0.0, units="m"),
    FieldDefinition("slack_m", "Slack", "double", 0.0, units="m"),
    FieldDefinition("total_len_m", "Total length", "double", 0.0, units="m"),
    FieldDefinition("fibers_per_tube", "Fibers per tube", "int", 0),
    FieldDefinition("total_fibers", "Total fibers", "int", 0),
    FieldDefinition("color_standard", "Color standard", "text", ""),
    _uuid_field(),
]

FIBER_BREAK_FIELDS: List[FieldDefinition] = [
    FieldDefinition("naziv", "Name", "text", ""),
    FieldDefinition("cable_layer_id", "Cable layer ID", "text", ""),
    FieldDefinition("cable_fid", "Cable feature ID", "int", 0),
    FieldDefinition("distance_m", "Distance", "double", 0.0, units="m"),
    FieldDefinition("segments_hit", "Segments hit", "int", 0),
    FieldDefinition("vreme", "Time", "text", ""),
    _uuid_field(),
]

JOINT_CLOSURE_FIELDS: List[FieldDefinition] = [
    FieldDefinition("naziv", "Name", "text", ""),
    _uuid_field(),
]


def _element_fields() -> List[FieldDefinition]:
    """Element layer fields = the shared roster plus the identity field."""
    return list(SHARED_ELEMENT_FIELDS) + [_uuid_field()]


# ---------------------------------------------------------------------------
# Canonical layer catalogue
# ---------------------------------------------------------------------------

#: Legacy / accepted alternate names per canonical layer name. Used to recognise
#: older projects (Serbian names, plural/singular drift) as the same layer type.
LAYER_NAME_ALIASES: Dict[str, List[str]] = {
    "Poles": ["Stubovi"],
    "Manholes": ["OKNA"],
    "Patch panel": ["Patch Panel"],
    "Joint Closures": ["Nastavci"],
    "Optical slack": ["Optical slacks", "Opticke_rezerve"],
    "Fiber break": ["Prekid vlakna"],
    "Route": ["Trasa"],
    "Aerial cables": ["Kablovi_vazdusni"],
    "Underground cables": ["Kablovi_podzemni"],
    "PE pipes": ["PE cevi"],
    "Transition pipes": ["Prelazne cevi"],
    "Objects": ["Objekti"],
    "Service Area": ["Service area", "Rejon"],
}


def _build_layer_schemas() -> Dict[str, LayerSchema]:
    schemas: Dict[str, LayerSchema] = {}
    # 12 point-element layers sharing the roster
    for name in ELEMENT_LAYER_NAMES:
        schemas[name] = LayerSchema(
            canonical_name=name, geometry="Point", crs_source="canvas",
            fields=_element_fields(), aliases=ELEMENT_FIELD_ALIASES,
        )
    schemas["Joint Closures"] = LayerSchema(
        "Joint Closures", "Point", "canvas", JOINT_CLOSURE_FIELDS,
        legacy_names=["Nastavci"], aliases=JOINT_CLOSURE_FIELD_ALIASES,
    )
    schemas["Poles"] = LayerSchema(
        "Poles", "Point", "canvas", POLES_FIELDS,
        legacy_names=["Stubovi"], aliases=POLES_FIELD_ALIASES,
    )
    schemas["Manholes"] = LayerSchema(
        "Manholes", "Point", "canvas", MANHOLE_FIELDS,
        legacy_names=["OKNA"], aliases=MANHOLE_FIELD_ALIASES,
    )
    schemas["Route"] = LayerSchema(
        "Route", "LineString", "canvas", ROUTE_FIELDS,
        legacy_names=["Trasa"], aliases=ROUTE_FIELD_ALIASES,
    )
    schemas["Optical slack"] = LayerSchema(
        "Optical slack", "Point", "canvas", SLACK_FIELDS,
        legacy_names=["Optical slacks", "Opticke_rezerve"], aliases=SLACK_FIELD_ALIASES,
    )
    schemas["PE pipes"] = LayerSchema(
        "PE pipes", "LineString", "canvas", PIPE_FIELDS,
        legacy_names=["PE cevi"], aliases=PIPE_FIELD_ALIASES,
    )
    schemas["Transition pipes"] = LayerSchema(
        "Transition pipes", "LineString", "canvas", PIPE_FIELDS,
        legacy_names=["Prelazne cevi"], aliases=PIPE_FIELD_ALIASES,
    )
    schemas["Service Area"] = LayerSchema(
        "Service Area", "Polygon", "project", SERVICE_AREA_FIELDS,
        legacy_names=["Service area", "Rejon"],
    )
    schemas["Objects"] = LayerSchema(
        "Objects", "Polygon", "project", OBJECTS_FIELDS,
        legacy_names=["Objekti"], aliases=OBJECTS_FIELD_ALIASES,
    )
    schemas["Aerial cables"] = LayerSchema(
        "Aerial cables", "LineString", "canvas", CABLE_FIELDS,
        legacy_names=["Kablovi_vazdusni"], aliases=CABLE_FIELD_ALIASES,
    )
    schemas["Underground cables"] = LayerSchema(
        "Underground cables", "LineString", "canvas", CABLE_FIELDS,
        legacy_names=["Kablovi_podzemni"], aliases=CABLE_FIELD_ALIASES,
    )
    schemas["Fiber break"] = LayerSchema(
        "Fiber break", "Point", "canvas", FIBER_BREAK_FIELDS,
        legacy_names=["Prekid vlakna"], aliases=FIBER_BREAK_FIELD_ALIASES,
    )
    return schemas


#: The canonical catalogue of every FiberQ layer type, keyed by canonical name.
LAYER_SCHEMAS: Dict[str, LayerSchema] = _build_layer_schemas()


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def canonical_layer_name(name: str) -> Optional[str]:
    """Return the canonical layer name for ``name`` (canonical or legacy), or None."""
    if not name:
        return None
    if name in LAYER_SCHEMAS:
        return name
    for canonical, legacy in LAYER_NAME_ALIASES.items():
        if name in legacy:
            return canonical
    return None


def get_layer_schema(name: str) -> Optional[LayerSchema]:
    """Return the LayerSchema for a canonical or legacy layer name, or None."""
    canonical = canonical_layer_name(name)
    return LAYER_SCHEMAS.get(canonical) if canonical else None


def is_element_layer(name: str) -> bool:
    """True if ``name`` is one of the shared-roster point-element layers."""
    return name in ELEMENT_LAYER_NAMES
