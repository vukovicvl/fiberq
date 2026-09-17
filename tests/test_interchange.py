"""Tests for the WP3 interchange-format core (fiberq/core/interchange.py).

No QGIS needed: the module is pure data and pure functions on purpose, so the
format's contract is testable without a runtime. The rules asserted here come
straight from docs/interchange-format.md -- if the spec changes, these fail.
"""
import importlib.util
import pathlib

import pytest

_SPEC_PATH = pathlib.Path(__file__).resolve().parent.parent / "docs" / "interchange-format.md"


def _load(name, relpath):
    """Import a pure-data module by path, bypassing the QGIS-importing package."""
    path = pathlib.Path(__file__).resolve().parent.parent / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ic = _load("fq_interchange", "fiberq/core/interchange.py")
schema = _load("fq_schema", "fiberq/models/schema.py")


# ---------------------------------------------------------------------------
# Type mapping — every layer covered, and the round trip closes
# ---------------------------------------------------------------------------

def test_every_plugin_layer_has_a_type():
    """A layer with no fq_type would be silently unexportable.

    This is the defect that makes the existing de-facto exchange lose data: the
    plugin's canonical 'Optical slack' is absent from its mapping table, so a
    current project's slack layer maps to nothing at all.
    """
    missing = [name for name in schema.LAYER_SCHEMAS if ic.type_for_layer(name) is None]
    assert missing == [], f"layers with no fq_type: {missing}"


def test_type_mapping_round_trips_to_the_same_layer():
    """layer -> type -> layer must be the identity, or import puts features in
    the wrong layer while looking like it worked."""
    for name in schema.LAYER_SCHEMAS:
        fq_type, placement = ic.type_for_layer(name)
        assert ic.layer_for_type(fq_type, placement) == name


def test_no_two_layers_share_a_type_and_placement():
    """Collisions silently merge two element kinds into one on import."""
    seen = {}
    for name, key in ic.LAYER_TO_TYPE.items():
        assert key not in seen, f"{name} collides with {seen.get(key)} on {key}"
        seen[key] = name


def test_to_and_otb_are_different_types():
    """The existing exchange maps TO -> OTB, which cannot be undone.

    Guarding it here because it is the kind of 'close enough' mapping that gets
    reintroduced by someone tidying up the table.
    """
    assert ic.type_for_layer("TO")[0] != ic.type_for_layer("OTB")[0]
    for variant in ("Indoor TO", "Outdoor TO", "Pole TO", "Joint Closure TO"):
        assert ic.type_for_layer(variant)[0] == "to"


def test_placement_is_an_attribute_not_a_type_code():
    """Placement variants share one type code and differ only by placement."""
    otbs = {ic.type_for_layer(n) for n in ("OTB", "Indoor OTB", "Outdoor OTB", "Pole OTB")}
    assert {t for t, _ in otbs} == {"otb"}
    assert {p for _, p in otbs} == {None, "indoor", "outdoor", "pole"}


def test_unknown_layer_returns_none_rather_than_guessing():
    """A reader must passthrough what it cannot type, never reclassify it."""
    assert ic.type_for_layer("Somebody Else's Layer") is None


def test_unknown_placement_falls_back_to_the_base_layer():
    """A tool that does not record placement should still land in the OTB layer."""
    assert ic.layer_for_type("otb", "orbital") == "OTB"
    assert ic.layer_for_type("otb", None) == "OTB"


# ---------------------------------------------------------------------------
# Metadata merge — the defect this module exists to not repeat
# ---------------------------------------------------------------------------

def test_merge_preserves_foreign_keys():
    """The whole point. Another tool's keys must survive our export."""
    existing = {
        "schema_version": "1.0",
        "splice_connections_json": '[{"source_fiber": 7}]',
        "some_future_tool_json": '{"x": 1}',
    }
    produced = ic.build_metadata("1.0", 3857, "1.5.0", "2026-09-01T10:00:00")
    merged = ic.merge_metadata(existing, produced)

    assert merged["splice_connections_json"] == '[{"source_fiber": 7}]'
    assert merged["some_future_tool_json"] == '{"x": 1}'


def test_merge_refreshes_our_own_keys():
    existing = {"schema_version": "0.9", "produced_by": "something old"}
    produced = ic.build_metadata("1.0", 4326, "1.5.0", "2026-09-01T10:00:00")
    merged = ic.merge_metadata(existing, produced)

    assert merged["schema_version"] == "1.0"
    assert merged["produced_by"] == "FiberQ QGIS plugin 1.5.0"


def test_merge_on_an_empty_bundle_is_just_our_keys():
    produced = ic.build_metadata("1.0", 4326, "1.5.0", "t")
    assert ic.merge_metadata({}, produced) == produced
    assert ic.merge_metadata(None, produced) == produced


def test_foreign_keys_identifies_what_we_do_not_own():
    existing = {"schema_version": "1.0", "splice_points_json": "[]", "mystery": "1"}
    assert ic.foreign_keys(existing) == {"splice_points_json": "[]", "mystery": "1"}


def test_version_keys_describe_three_different_things():
    """format_version = the spec, schema_version = the payload, produced_by = the
    writer. The de-facto exchange conflates the last two and its bundles cannot
    be version-checked as a result."""
    md = ic.build_metadata("1.0", 4326, "1.5.0", "t")
    assert md["format_version"] == ic.FORMAT_VERSION
    assert md["schema_version"] == "1.0"
    assert "1.5.0" in md["produced_by"]
    assert md["schema_version"] != md["produced_by"]


def test_required_metadata_keys_are_all_present():
    md = ic.build_metadata("1.0", 3909, "1.5.0", "2026-09-01T10:00:00")
    for key in ("format", "format_version", "schema_version", "produced_by",
                "produced_at", "crs_epsg", "color_standard"):
        assert md.get(key), f"missing required key {key}"
    assert md["format"] == "fiberq-interchange"
    assert md["crs_epsg"] == "3909"


def test_missing_crs_is_empty_not_the_string_none():
    """A project with no CRS must not record the literal 'None' as an EPSG code."""
    assert ic.build_metadata("1.0", None, "1.5.0", "t")["crs_epsg"] == ""


# ---------------------------------------------------------------------------
# Side-car DDL
# ---------------------------------------------------------------------------

def test_sidecar_ddl_executes_against_sqlite():
    """The tables must be plain SQLite so any client can read a bundle."""
    sqlite3 = pytest.importorskip("sqlite3")
    conn = sqlite3.connect(":memory:")
    for ddl in ic.SIDECAR_DDL:
        conn.execute(ddl)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "fq_extension" in names, "the passthrough store is not optional"
    assert "fq_fiber_connection" in names
    assert len(names) == len(ic.SIDECAR_DDL)


def test_containers_can_nest():
    """host_kind is what lets a tray inside a closure be expressed at all."""
    ddl = next(d for d in ic.SIDECAR_DDL if "fq_container " in d)
    assert "host_kind" in ddl


def test_storage_crs_is_pinned():
    assert ic.STORAGE_EPSG == 4326


# ---------------------------------------------------------------------------
# The spec and the code must agree
# ---------------------------------------------------------------------------

def test_spec_document_exists_and_matches_the_implemented_version():
    """Published spec and shipped code drifting apart is how a format dies."""
    text = _SPEC_PATH.read_text(encoding="utf-8")
    assert ic.FORMAT in text
    assert f"`{ic.FORMAT_VERSION}" in text or ic.FORMAT_VERSION in text


def test_every_sidecar_table_is_named_in_the_spec():
    text = _SPEC_PATH.read_text(encoding="utf-8")
    for ddl in ic.SIDECAR_DDL:
        table = ddl.split("IF NOT EXISTS", 1)[1].split("(", 1)[0].strip()
        assert table in text, f"{table} is implemented but undocumented"
