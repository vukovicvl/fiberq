"""Unit tests for the canonical schema model (WP1a).

These are pure-Python tests — they exercise ``fiberq.models.schema`` (no QGIS
needed). They lock the as-built data model so any accidental drift is caught,
and they guard the contract that the de-dup delegations rely on.
"""
import importlib.util
import os

# Load schema.py standalone (it has no intra-package imports), so these tests run
# without QGIS bindings / the package __init__ chain.
_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fiberq", "models", "schema.py",
)
_spec = importlib.util.spec_from_file_location("fiberq_schema_under_test", _SCHEMA_PATH)
schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schema)


# Golden copy of the element roster: (key, label, field_type, default, options).
# If this drifts, it is a deliberate schema change — update intentionally.
EXPECTED_ELEMENT_ROSTER = [
    ("naziv", "Name", "text", "", None),
    ("proizvodjac", "Manufacturer", "text", "", None),
    ("oznaka", "Label", "text", "", None),
    ("kapacitet", "Capacity", "int", 0, None),
    ("ukupno_kj", "Total", "int", 0, None),
    ("zahtev_kapaciteta", "Capacity Requirement", "int", 0, None),
    ("zahtev_rezerve", "Slack Requirement", "int", 0, None),
    ("oznaka_izvoda", "Outlet Label", "text", "", None),
    ("numeracija", "Numbering", "text", "", None),
    ("naziv_objekta", "Object Name", "text", "", None),
    ("adresa_ulica", "Address Street", "text", "", None),
    ("adresa_broj", "Address Number", "text", "", None),
    ("address_id", "Address ID", "text", "", None),
    ("stanje", "Status", "enum", "Planned", ["Planned", "Built", "Existing"]),
    ("godina_ugradnje", "Year of Installation", "year", 2025, None),
]


def test_schema_version_is_nonempty_string():
    assert isinstance(schema.SCHEMA_VERSION, str)
    assert schema.SCHEMA_VERSION
    # MAJOR.MINOR style, decoupled from the plugin version
    assert schema.SCHEMA_VERSION[0].isdigit()


def test_all_field_types_are_valid():
    for name, ls in schema.LAYER_SCHEMAS.items():
        for f in ls.fields:
            assert f.field_type in schema.FIELD_TYPES, f"{name}.{f.key}={f.field_type}"


def test_every_layer_has_identity_field_last():
    for name, ls in schema.LAYER_SCHEMAS.items():
        keys = [f.key for f in ls.fields]
        assert schema.IDENTITY_FIELD in keys, f"{name} missing {schema.IDENTITY_FIELD}"
        assert keys[-1] == schema.IDENTITY_FIELD, f"{name}: identity field not last"
        assert ls.identity_field == schema.IDENTITY_FIELD


def test_no_duplicate_field_keys_per_layer():
    for name, ls in schema.LAYER_SCHEMAS.items():
        keys = [f.key for f in ls.fields]
        assert len(keys) == len(set(keys)), f"{name} has duplicate field keys"


def test_shared_element_roster_is_15_without_uuid():
    assert len(schema.SHARED_ELEMENT_FIELDS) == 15
    keys = [f.key for f in schema.SHARED_ELEMENT_FIELDS]
    assert schema.IDENTITY_FIELD not in keys


def test_get_default_fields_shape_and_content():
    fields = schema.get_default_fields_for_layer("ODF")
    assert len(fields) == 15
    for tup in fields:
        assert len(tup) == 5  # (key, label, field_type, default, options)
    assert fields == EXPECTED_ELEMENT_ROSTER


def test_od_cabinet_capacity_override():
    normal = dict((k, d) for (k, _, _, d, _) in schema.get_default_fields_for_layer("ODF"))
    cabinet = dict((k, d) for (k, _, _, d, _) in schema.get_default_fields_for_layer("OD ormar 1"))
    assert normal["kapacitet"] == 0
    assert cabinet["kapacitet"] == schema.OD_CABINET_CAPACITY_DEFAULT == 24
    # only kapacitet differs
    assert {k: v for k, v in cabinet.items() if k != "kapacitet"} == \
        {k: v for k, v in normal.items() if k != "kapacitet"}


def test_element_layers_use_roster_plus_uuid():
    expected = [k for (k, *_rest) in EXPECTED_ELEMENT_ROSTER] + [schema.IDENTITY_FIELD]
    for name in schema.ELEMENT_LAYER_NAMES:
        ls = schema.LAYER_SCHEMAS[name]
        assert [f.key for f in ls.fields] == expected, name


def test_cables_share_identical_roster():
    aerial = [f.key for f in schema.LAYER_SCHEMAS["Aerial cables"].fields]
    under = [f.key for f in schema.LAYER_SCHEMAS["Underground cables"].fields]
    assert aerial == under
    assert "fibers_per_tube" in aerial and "color_standard" in aerial


def test_joint_closures_minimal():
    keys = [f.key for f in schema.LAYER_SCHEMAS["Joint Closures"].fields]
    assert keys == ["naziv", "fiberq_uuid"]


def test_aliases_reference_existing_fields():
    for name, ls in schema.LAYER_SCHEMAS.items():
        field_keys = {f.key for f in ls.fields}
        for alias_key in ls.aliases:
            assert alias_key in field_keys, f"{name}: alias for unknown field {alias_key}"


def test_legacy_names_resolve_to_canonical():
    assert schema.canonical_layer_name("Stubovi") == "Poles"
    assert schema.canonical_layer_name("OKNA") == "Manholes"
    assert schema.canonical_layer_name("Trasa") == "Route"
    assert schema.canonical_layer_name("Kablovi_podzemni") == "Underground cables"
    assert schema.canonical_layer_name("Rejon") == "Service Area"
    assert schema.canonical_layer_name("Optical slacks") == "Optical slack"
    assert schema.canonical_layer_name("ODF") == "ODF"  # canonical passes through
    assert schema.canonical_layer_name("does-not-exist") is None


def test_get_layer_schema_via_legacy_name():
    ls = schema.get_layer_schema("Trasa")
    assert ls is not None and ls.canonical_name == "Route"


def test_value_maps_present_where_expected():
    cable = {f.key: f for f in schema.LAYER_SCHEMAS["Underground cables"].fields}
    assert cable["tip"].value_map == {"Optical": "opticki", "Copper": "bakarnI"}
    route = {f.key: f for f in schema.LAYER_SCHEMAS["Route"].fields}
    assert route["tip_trase"].value_map["Aerial"] == "vazdusna"
