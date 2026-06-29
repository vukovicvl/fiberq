"""Parity tests for the WP1a de-dup.

The legacy roster functions now delegate to the canonical schema, and the
remaining legacy data copies (element_defs roster, field_aliases maps) are
asserted equal to the schema. These lock the single-source-of-truth so any
future drift fails CI. Require QGIS (pytest-qgis) because the modules under test
import qgis.
"""
from fiberq.models import schema


def test_roster_functions_delegate_to_schema(qgis_app):
    from fiberq.models.element_defs import get_default_fields_for_layer as ed
    from fiberq.dialogs.base import default_fields_for as db
    from fiberq.utils.legacy_bridge import _default_fields_for as lb
    from fiberq.core.layer_manager import _default_fields_for as lm
    for name in ("ODF", "OD ormar 1", "TO", "Patch panel"):
        expected = schema.get_default_fields_for_layer(name)
        assert ed(name) == expected, name
        assert db(name) == expected, name
        assert lb(name) == expected, name
        assert lm(name) == expected, name


def test_element_defs_roster_data_matches_schema(qgis_app):
    from fiberq.models import element_defs
    legacy = [(f.key, f.label, f.field_type, f.default, f.options)
              for f in element_defs.DEFAULT_ELEMENT_FIELDS]
    canonical = [(f.key, f.label, f.field_type, f.default, f.options)
                 for f in schema.SHARED_ELEMENT_FIELDS]
    assert legacy == canonical


def test_field_alias_maps_match_schema(qgis_app):
    from fiberq.utils import field_aliases as fa
    for name, canonical in [
        ("ELEMENT_FIELD_ALIASES", schema.ELEMENT_FIELD_ALIASES),
        ("POLES_FIELD_ALIASES", schema.POLES_FIELD_ALIASES),
        ("ROUTE_FIELD_ALIASES", schema.ROUTE_FIELD_ALIASES),
        ("CABLE_FIELD_ALIASES", schema.CABLE_FIELD_ALIASES),
        ("MANHOLE_FIELD_ALIASES", schema.MANHOLE_FIELD_ALIASES),
        ("SLACK_FIELD_ALIASES", schema.SLACK_FIELD_ALIASES),
        ("PIPE_FIELD_ALIASES", schema.PIPE_FIELD_ALIASES),
        ("JOINT_CLOSURE_FIELD_ALIASES", schema.JOINT_CLOSURE_FIELD_ALIASES),
        ("FIBER_BREAK_FIELD_ALIASES", schema.FIBER_BREAK_FIELD_ALIASES),
        ("OBJECTS_FIELD_ALIASES", schema.OBJECTS_FIELD_ALIASES),
    ]:
        assert getattr(fa, name) == canonical, name


def test_value_maps_match_schema(qgis_app):
    from fiberq.utils import field_aliases as fa
    for name, canonical in [
        ("ROUTE_TYPE_VALUE_MAP", schema.ROUTE_TYPE_VALUE_MAP),
        ("SLACK_LOCATION_VALUE_MAP", schema.SLACK_LOCATION_VALUE_MAP),
        ("SLACK_SIDE_VALUE_MAP", schema.SLACK_SIDE_VALUE_MAP),
        ("CABLE_TYPE_VALUE_MAP", schema.CABLE_TYPE_VALUE_MAP),
        ("CABLE_SUBTYPE_VALUE_MAP", schema.CABLE_SUBTYPE_VALUE_MAP),
        ("CABLE_STATUS_VALUE_MAP", schema.CABLE_STATUS_VALUE_MAP),
        ("CABLE_LAYING_VALUE_MAP", schema.CABLE_LAYING_VALUE_MAP),
    ]:
        assert getattr(fa, name) == canonical, name
