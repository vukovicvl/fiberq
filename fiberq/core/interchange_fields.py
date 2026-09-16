"""Canonical field and value mapping for the interchange format (WP3 task 3.1).

A pure-data module, like ``models/schema.py`` and ``core/interchange.py``: no
QGIS imports, so the mapping is testable without a runtime.

**Why rename anything at all.** FiberQ's stored field names are the original
Serbian database names -- ``duzina_m``, ``slabljenje_dbkm``, ``vrsta_omotaca``
-- and several of its stored *values* are Serbian too (``vazdusna``,
``opticki``). They are the plugin's schema and they are not changing; renaming a
stored field is a data migration, not a cosmetic change.

But a bundle carrying them would not be a tool-neutral format. It would be
FiberQ's schema in a GeoPackage, and every other tool would have to learn
Serbian to read it -- which is mapping directly to one tool's schema, exactly
what spec rule 3 exists to prevent. So the bundle carries canonical English
names and canonical values, and this module is the bijection between the two.

**The mapping is per element type, not global.** ``tip`` means *cable type* on a
cable and *pole type* on a pole; ``podtip`` means *cable subtype* on one and
*segment type* on the other. One global rename table would quietly merge two
different meanings into one canonical field, and nothing downstream could tell
afterwards. Hence rosters.

Published as ``docs/interchange-mapping.md``, which a test keeps in step.
"""
from typing import Dict, Optional

#: The identity field keeps its name in a bundle. It is the one field every
#: conformant tool must already know (spec section 4), so translating it would
#: be renaming the join key.
IDENTITY_FIELD = "fiberq_uuid"

#: Stored fields that are *replaced* rather than renamed. The plugin records
#: which cable a slack loop or a fibre break belongs to as
#: ``(cable_layer_id, cable_fid)`` -- a QGIS layer id plus a feature id, both
#: local to one project file and meaningless anywhere else. A bundle carries
#: ``cable_uuid`` instead, resolved on the way out and resolved back on the way
#: in. This is the "structural" mismatch case: no canonical column corresponds,
#: because the canonical form is a different shape.
STRUCTURAL_FIELDS = frozenset({"cable_layer_id", "cable_fid"})

#: Canonical name for what those two fields together mean.
CABLE_REFERENCE_FIELD = "cable_uuid"

# ---------------------------------------------------------------------------
# Field rosters: plugin stored name -> canonical bundle name
# ---------------------------------------------------------------------------

#: The twelve point-element layers (ODF, OTB, TO, TB, patch panel) share one
#: roster, so they share one mapping.
ELEMENT_FIELDS: Dict[str, str] = {
    "naziv": "name",
    "proizvodjac": "manufacturer",
    "oznaka": "label",
    "kapacitet": "port_capacity",
    "ukupno_kj": "total_connections",
    "zahtev_kapaciteta": "required_capacity",
    "zahtev_rezerve": "reserve_capacity",
    "oznaka_izvoda": "port_label",
    "numeracija": "numbering",
    "naziv_objekta": "site_name",
    "adresa_ulica": "address_street",
    "adresa_broj": "address_number",
    "address_id": "address_id",
    "stanje": "status",
    "godina_ugradnje": "install_year",
}

CLOSURE_FIELDS: Dict[str, str] = {
    "naziv": "name",
}

POLE_FIELDS: Dict[str, str] = {
    "tip": "pole_type",
    "podtip": "segment_type",
    "visina": "height_m",
    "materijal": "material",
}

MANHOLE_FIELDS: Dict[str, str] = {
    "broj_okna": "manhole_id",
    "tip_okna": "manhole_type",
    "vrsta_okna": "construction_type",
    "polozaj_okna": "position",
    "adresa": "address",
    "stanje": "status",
    "god_ugrad": "install_year",
    "opis": "description",
    "dimenzije": "dimensions_cm",
    "mat_zida": "wall_material",
    "mat_poklop": "cover_material",
    "odvodnj": "drainage",
    "poklop_tes": "cover_heavy",
    "poklop_lak": "cover_light",
    "br_nosaca": "step_count",
    "debl_zida": "wall_thickness_cm",
    "lestve": "ladder",
}

ROUTE_FIELDS: Dict[str, str] = {
    "naziv": "name",
    "duzina": "length_m",
    "duzina_km": "length_km",
    "tip_trase": "route_type",
}

SLACK_FIELDS: Dict[str, str] = {
    "tip": "slack_type",
    "duzina_m": "length_m",
    "lokacija": "location",
    "strana": "side",
    "napomena": "note",
}

DUCT_FIELDS: Dict[str, str] = {
    "materijal": "material",
    "kapacitet": "capacity",
    "fi": "diameter_mm",
    "od": "from_label",
    "do": "to_label",
    "duzina_m": "length_m",
}

SERVICE_AREA_FIELDS: Dict[str, str] = {
    "name": "name",
    "created_at": "created_at",
    "area_m2": "area_m2",
    "perim_m": "perimeter_m",
    # Not a count of anything in the network: it records how many source parts
    # the area was built from. Named for what it is, so nobody reads it as a
    # subscriber count.
    "count": "source_part_count",
}

BUILDING_FIELDS: Dict[str, str] = {
    "tip": "building_type",
    "spratova": "floors_above",
    "podzemnih": "floors_below",
    "ulica": "street",
    "broj": "street_number",
    "naziv": "name",
    "napomena": "note",
}

CABLE_FIELDS: Dict[str, str] = {
    "tip": "cable_type",
    "podtip": "cable_subtype",
    "color_code": "color_code",
    "broj_cevcica": "tube_count",
    "broj_vlakana": "fiber_count",
    "tip_kabla": "cable_model",
    "vrsta_vlakana": "fiber_type",
    "vrsta_omotaca": "sheath_type",
    "vrsta_armature": "armour_type",
    "talasno_podrucje": "wavelength_band",
    "naziv": "name",
    "slabljenje_dbkm": "attenuation_db_km",
    "hrom_disp_ps_nmxkm": "chromatic_dispersion_ps_nm_km",
    "stanje_kabla": "status",
    "cable_laying": "installation_type",
    "vrsta_mreze": "network_type",
    "godina_ugradnje": "install_year",
    "konstr_vlakna_u_cevcicama": "constr_fibers_in_tubes",
    "konstr_sa_uzlepljenim_elementom": "constr_bonded_element",
    "konstr_punjeni_kabl": "constr_gel_filled",
    "konstr_sa_arm_vlaknima": "constr_aramid_armour",
    "konstr_bez_metalnih": "constr_non_metallic",
    "od": "from_label",
    "do": "to_label",
    "duzina_m": "length_m",
    "slack_m": "slack_m",
    "total_len_m": "total_length_m",
    "fibers_per_tube": "fibers_per_tube",
    "total_fibers": "total_fibers",
    "color_standard": "color_standard",
}

FIBER_BREAK_FIELDS: Dict[str, str] = {
    "naziv": "name",
    "distance_m": "distance_m",
    "segments_hit": "segments_hit",
    "vreme": "recorded_at",
}

#: roster id -> stored-name mapping.
ROSTERS: Dict[str, Dict[str, str]] = {
    "element": ELEMENT_FIELDS,
    "closure": CLOSURE_FIELDS,
    "pole": POLE_FIELDS,
    "manhole": MANHOLE_FIELDS,
    "route": ROUTE_FIELDS,
    "slack": SLACK_FIELDS,
    "duct": DUCT_FIELDS,
    "service_area": SERVICE_AREA_FIELDS,
    "building": BUILDING_FIELDS,
    "cable": CABLE_FIELDS,
    "fiber_break": FIBER_BREAK_FIELDS,
}

#: fq_type -> roster id. Every type in ``interchange.LAYER_TO_TYPE`` appears
#: here; a test asserts it, because a type with no roster would export its
#: fields under their Serbian names and nobody would notice.
TYPE_ROSTER: Dict[str, str] = {
    "odf": "element", "tb": "element", "patch_panel": "element",
    "otb": "element", "to": "element",
    "closure.joint": "closure",
    "pole": "pole",
    "manhole": "manhole",
    "route": "route",
    "slack": "slack",
    "duct.pe": "duct", "duct.transition": "duct",
    "service_area": "service_area",
    "building": "building",
    "cable.aerial": "cable", "cable.underground": "cable",
    "fiber_break": "fiber_break",
}

# ---------------------------------------------------------------------------
# Value domains: stored value -> canonical value
# ---------------------------------------------------------------------------

#: ``(roster, canonical field) -> {stored value: canonical value}``.
#:
#: Mirrors the value maps in ``models/schema.py``, inverted. Duplicated rather
#: than imported so this module stays free of package imports; a test asserts
#: the two agree, the same way the WP1 schema parity tests do.
#:
#: A value in neither domain is carried through verbatim. That is not laxity:
#: FiberQ projects genuinely hold both spellings (see validation rule D1), and a
#: writer that dropped what it did not recognise would be discarding the user's
#: data to tidy a vocabulary.
VALUE_DOMAINS: Dict[str, Dict[str, str]] = {
    "route/route_type": {
        "vazdusna": "aerial",
        "podzemna": "underground",
        "kroz objekat": "through_building",
    },
    "slack/location": {
        "OKNO": "manhole",
        "Stub": "pole",
        "Objekat": "building",
    },
    "slack/side": {
        "od": "from",
        "do": "to",
        "sredina": "mid_span",
    },
    "cable/cable_type": {
        "opticki": "optical",
        # As-built typo (capital I), preserved in the plugin's schema and
        # therefore present in real projects. Mapped, not corrected.
        "bakarnI": "copper",
        "bakarni": "copper",
    },
    "cable/cable_subtype": {
        "glavni": "backbone",
        "distributivni": "distribution",
        "razvodni": "drop",
    },
    "cable/status": {
        "Projektovano": "planned",
        "Postojeće": "existing",
        "U izgradnji": "under_construction",
    },
    "cable/installation_type": {
        "Podzemno": "underground",
        "Vazdusno": "aerial",
    },
}

#: The English display labels FiberQ also stores, depending on how and when a
#: feature was created. Both spellings are as-built and both must map.
ENGLISH_ALIASES: Dict[str, Dict[str, str]] = {
    "route/route_type": {
        "Aerial": "aerial", "Underground": "underground",
        "Through the object": "through_building",
    },
    "slack/location": {"Manhole": "manhole", "Pole": "pole", "Object": "building"},
    "slack/side": {"FROM": "from", "TO": "to", "MID SPAN": "mid_span"},
    "cable/cable_type": {"Optical": "optical", "Copper": "copper"},
    "cable/cable_subtype": {
        "Backbone": "backbone", "Distribution": "distribution", "Drop": "drop",
    },
    "cable/status": {
        "Planned": "planned", "Existing": "existing",
        "Under construction": "under_construction",
    },
    "cable/installation_type": {"Underground": "underground", "Aerial": "aerial"},
}


def _domain_key(roster: str, canonical_name: str) -> str:
    return f"{roster}/{canonical_name}"


def roster_for_type(fq_type: str) -> Optional[str]:
    """The field roster an element of this type uses, or ``None``."""
    return TYPE_ROSTER.get(fq_type)


def canonical_field(roster: str, stored_name: str) -> Optional[str]:
    """Canonical bundle name for a stored FiberQ field name.

    ``None`` means "this field has no canonical name in this roster" -- either
    it is structural (see :data:`STRUCTURAL_FIELDS`) or it is a field the
    format does not model, which travels in ``fq_extra_json`` rather than being
    dropped.
    """
    if stored_name == IDENTITY_FIELD:
        return IDENTITY_FIELD
    return ROSTERS.get(roster, {}).get(stored_name)


def stored_field(roster: str, canonical_name: str) -> Optional[str]:
    """The stored FiberQ field name for a canonical bundle name, or ``None``."""
    if canonical_name == IDENTITY_FIELD:
        return IDENTITY_FIELD
    for stored, canonical in ROSTERS.get(roster, {}).items():
        if canonical == canonical_name:
            return stored
    return None


def canonical_value(roster: str, canonical_name: str, value):
    """Translate a stored value to its canonical form, or return it unchanged."""
    if value is None:
        return value
    key = _domain_key(roster, canonical_name)
    domain = VALUE_DOMAINS.get(key)
    if domain is None:
        return value
    text = str(value)
    if text in domain:
        return domain[text]
    return ENGLISH_ALIASES.get(key, {}).get(text, value)


def stored_value(roster: str, canonical_name: str, value):
    """Translate a canonical value back to what FiberQ stores, or leave it be."""
    if value is None:
        return value
    domain = VALUE_DOMAINS.get(_domain_key(roster, canonical_name))
    if domain is None:
        return value
    text = str(value)
    for stored, canonical in domain.items():
        if canonical == text:
            return stored
    return value


__all__ = [
    "CABLE_REFERENCE_FIELD", "ENGLISH_ALIASES", "IDENTITY_FIELD", "ROSTERS",
    "STRUCTURAL_FIELDS", "TYPE_ROSTER", "VALUE_DOMAINS", "canonical_field",
    "canonical_value", "roster_for_type", "stored_field", "stored_value",
]
