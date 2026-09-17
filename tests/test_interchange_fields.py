"""Tests for the canonical field/value mapping (fiberq/core/interchange_fields.py).

Pure data, so no QGIS: the modules load by path, bypassing the package.

The mapping is what makes the bundle a format rather than a dump of FiberQ's
own schema, so the tests that matter are the completeness ones. A plugin field
with no canonical name would leave the bundle under its Serbian stored name and
nothing would fail; a canonical name reused by two stored fields would merge two
meanings and nothing could tell them apart afterwards. Both are asserted here.
"""
import importlib.util
import pathlib


def _load(name, relpath):
    path = pathlib.Path(__file__).resolve().parent.parent / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fm = _load("fq_fields", "fiberq/core/interchange_fields.py")
ic = _load("fq_interchange", "fiberq/core/interchange.py")
schema = _load("fq_schema", "fiberq/models/schema.py")


def _roster_of(layer_name):
    fq_type, _placement = ic.type_for_layer(layer_name)
    return fm.roster_for_type(fq_type)


# ---------------------------------------------------------------------------
# Completeness: nothing leaves under its stored name by accident
# ---------------------------------------------------------------------------

def test_every_element_type_has_a_field_roster():
    """A type with no roster exports Serbian field names and looks fine."""
    missing = sorted({
        fq_type for fq_type, _p in ic.LAYER_TO_TYPE.values()
        if fm.roster_for_type(fq_type) is None
    })
    assert missing == [], f"fq_type with no field roster: {missing}"


def test_every_stored_field_has_a_canonical_name():
    """Add a field to the plugin schema and this fails until it is mapped.

    That is the point: a new field silently shipping under its stored name is
    exactly the drift the format cannot detect on its own.
    """
    unmapped = []
    for layer_name, layer_schema in schema.LAYER_SCHEMAS.items():
        roster = _roster_of(layer_name)
        for field in layer_schema.fields:
            if field.key in fm.STRUCTURAL_FIELDS:
                continue
            if fm.canonical_field(roster, field.key) is None:
                unmapped.append(f"{layer_name}.{field.key}")
    assert unmapped == [], f"stored fields with no canonical name: {unmapped}"


def test_no_two_stored_fields_share_a_canonical_name():
    """Two stored fields collapsing into one canonical field is unrecoverable."""
    for roster, mapping in fm.ROSTERS.items():
        seen = {}
        for stored, canonical in mapping.items():
            assert canonical not in seen, (
                f"{roster}: '{stored}' and '{seen.get(canonical)}' both map to "
                f"'{canonical}'")
            seen[canonical] = stored


def test_the_field_mapping_round_trips():
    """stored -> canonical -> stored must be the identity, both ways."""
    for roster, mapping in fm.ROSTERS.items():
        for stored, canonical in mapping.items():
            assert fm.stored_field(roster, canonical) == stored
            assert fm.canonical_field(roster, stored) == canonical


def test_the_identity_field_is_never_renamed():
    """fiberq_uuid is the join key every conformant tool already knows."""
    for roster in fm.ROSTERS:
        assert fm.canonical_field(roster, "fiberq_uuid") == "fiberq_uuid"
        assert fm.stored_field(roster, "fiberq_uuid") == "fiberq_uuid"


def test_the_local_cable_reference_has_no_canonical_column():
    """(cable_layer_id, cable_fid) is a QGIS-local pair; the bundle carries a uuid."""
    for stored in ("cable_layer_id", "cable_fid"):
        assert stored in fm.STRUCTURAL_FIELDS
        assert fm.canonical_field("slack", stored) is None
        assert fm.canonical_field("fiber_break", stored) is None


def test_the_same_stored_name_can_mean_different_things_per_roster():
    """'tip' is a cable type on a cable and a pole type on a pole.

    A single global rename table would merge them; this is why rosters exist.
    """
    assert fm.canonical_field("cable", "tip") == "cable_type"
    assert fm.canonical_field("pole", "tip") == "pole_type"
    assert fm.canonical_field("slack", "tip") == "slack_type"
    assert fm.canonical_field("building", "tip") == "building_type"


# ---------------------------------------------------------------------------
# Value domains
# ---------------------------------------------------------------------------

def _schema_value_maps():
    """``roster/canonical -> {English label: stored value}`` straight from schema.py."""
    out = {}
    for layer_name, layer_schema in schema.LAYER_SCHEMAS.items():
        roster = _roster_of(layer_name)
        for field in layer_schema.fields:
            if not field.value_map:
                continue
            canonical = fm.canonical_field(roster, field.key)
            out[f"{roster}/{canonical}"] = dict(field.value_map)
    return out


def test_every_value_map_in_the_schema_has_a_canonical_domain():
    """A controlled vocabulary left untranslated ships Serbian values."""
    missing = sorted(set(_schema_value_maps()) - set(fm.VALUE_DOMAINS))
    assert missing == [], f"value maps with no canonical domain: {missing}"


def test_the_canonical_domains_cover_every_stored_value():
    """Locked against schema.py the way the WP1 parity tests are.

    Change a stored value in the plugin schema and this fails, rather than the
    bundle quietly carrying a value no reader has a meaning for.
    """
    for key, value_map in _schema_value_maps().items():
        stored_values = set(value_map.values())
        covered = set(fm.VALUE_DOMAINS[key])
        assert stored_values <= covered, (
            f"{key}: stored value(s) {sorted(stored_values - covered)} not in the "
            "canonical domain")


def test_both_spellings_reach_the_same_canonical_value():
    """Real projects hold the English label on some features and the stored
    Serbian value on others (validation rule D1). Both are as-built."""
    for key, value_map in _schema_value_maps().items():
        roster, _, canonical = key.partition("/")
        for english, stored in value_map.items():
            from_stored = fm.canonical_value(roster, canonical, stored)
            from_english = fm.canonical_value(roster, canonical, english)
            assert from_stored == from_english, (
                f"{key}: '{stored}' -> {from_stored!r} but '{english}' -> "
                f"{from_english!r}")
            assert from_stored != stored or stored == from_stored == english


def test_values_round_trip_back_to_what_the_plugin_stores():
    for key, value_map in _schema_value_maps().items():
        roster, _, canonical = key.partition("/")
        for stored in value_map.values():
            canonical_form = fm.canonical_value(roster, canonical, stored)
            assert fm.stored_value(roster, canonical, canonical_form) == stored


def test_an_unrecognised_value_is_carried_through_not_dropped():
    """Rule 1. Tidying a vocabulary is not worth discarding the user's data."""
    assert fm.canonical_value("cable", "cable_type", "hybrid") == "hybrid"
    assert fm.stored_value("cable", "cable_type", "hybrid") == "hybrid"
    assert fm.canonical_value("cable", "cable_type", None) is None


def test_a_field_with_no_domain_leaves_its_value_alone():
    assert fm.canonical_value("cable", "name", "Feeder A") == "Feeder A"
    assert fm.stored_value("manhole", "address", "Main St 1") == "Main St 1"


def test_the_as_built_copper_typo_is_mapped_not_corrected():
    """The plugin stores 'bakarnI' with a capital I. Real projects contain it."""
    assert fm.canonical_value("cable", "cable_type", "bakarnI") == "copper"
    assert fm.canonical_value("cable", "cable_type", "bakarni") == "copper"
    assert fm.stored_value("cable", "cable_type", "copper") == "bakarnI"
