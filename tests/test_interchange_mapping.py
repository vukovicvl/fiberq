"""The published field mapping must match the code (WP3 task 3.1).

docs/interchange-mapping.md is generated from fiberq/models/schema.py and
fiberq/core/interchange_fields.py. A generated document is only trustworthy if
something fails when it goes stale, so these tests read the published page back
and hold it to the modules it came from.

The failure this catches is specific: a field added to the plugin schema, mapped
in the code, and never republished. The bundle would then be correct and the
public spec would be quietly wrong -- and the spec is the half other tools
implement against.
"""
import importlib.util
import pathlib
import re

DOC = pathlib.Path(__file__).resolve().parent.parent / "docs" / "interchange-mapping.md"
SPEC = pathlib.Path(__file__).resolve().parent.parent / "docs" / "interchange-format.md"


def _load(name, relpath):
    path = pathlib.Path(__file__).resolve().parent.parent / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fm = _load("fq_fields", "fiberq/core/interchange_fields.py")
ic = _load("fq_interchange", "fiberq/core/interchange.py")
schema = _load("fq_schema", "fiberq/models/schema.py")

TEXT = DOC.read_text(encoding="utf-8")
#: Every `code` span on the page, which is how field and value names are written.
CODE_SPANS = set(re.findall(r"`([^`]+)`", TEXT))


def test_the_mapping_document_exists_and_is_not_a_stub():
    assert len(TEXT) > 4000, "the published mapping is suspiciously short"


def test_every_canonical_field_is_published():
    """A canonical name only another tool's implementer can find by reading our
    source is not a published mapping."""
    missing = sorted({
        canonical
        for mapping in fm.ROSTERS.values()
        for canonical in mapping.values()
        if canonical not in CODE_SPANS
    })
    assert missing == [], f"canonical fields missing from the document: {missing}"


def test_every_stored_plugin_field_is_published():
    """The plugin column has to be complete too, or a reader cannot map back."""
    missing = sorted({
        stored
        for mapping in fm.ROSTERS.values()
        for stored in mapping
        if stored not in CODE_SPANS
    })
    assert missing == [], f"plugin fields missing from the document: {missing}"


def test_every_schema_field_reaches_the_document():
    """Closes the loop back to the plugin's own source of truth.

    Add a field to models/schema.py and this fails until it is both mapped in
    the code and republished here.
    """
    missing = []
    for layer_name, layer_schema in schema.LAYER_SCHEMAS.items():
        for field in layer_schema.fields:
            if field.key in fm.STRUCTURAL_FIELDS:
                continue
            if field.key not in CODE_SPANS:
                missing.append(f"{layer_name}.{field.key}")
    assert missing == [], f"schema fields absent from the mapping document: {missing}"


def test_every_element_type_code_is_published():
    missing = sorted({
        fq_type for fq_type, _p in ic.LAYER_TO_TYPE.values()
        if fq_type not in CODE_SPANS
    })
    assert missing == [], f"fq_type codes missing from the document: {missing}"


def test_every_canonical_value_and_its_stored_form_are_published():
    missing = []
    for key, domain in fm.VALUE_DOMAINS.items():
        for stored, canonical in domain.items():
            if stored not in CODE_SPANS:
                missing.append(f"{key} stored '{stored}'")
            if canonical not in CODE_SPANS:
                missing.append(f"{key} canonical '{canonical}'")
    assert missing == [], f"value domain entries missing from the document: {missing}"


def test_the_structural_case_is_documented_as_such():
    """cable_layer_id + cable_fid -> cable_uuid is the one conversion a reader
    cannot infer from a rename table."""
    for name in ("cable_layer_id", "cable_fid", "cable_uuid"):
        assert name in CODE_SPANS, name
    assert "structural" in TEXT.lower()


def test_the_document_never_names_the_bundle_columns_wrong():
    for column in ("fq_type", "placement", "fq_extra_json"):
        assert column in CODE_SPANS, column


def test_the_spec_and_the_mapping_link_to_each_other():
    """Two halves of one deliverable; either one alone is incomplete."""
    assert "interchange-mapping.md" in SPEC.read_text(encoding="utf-8")
    assert "interchange-format.md" in TEXT
