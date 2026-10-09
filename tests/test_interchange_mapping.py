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


# ---------------------------------------------------------------------------
# the gate, both ways round (WP4 4.2 item U21)
# ---------------------------------------------------------------------------
#
# Everything above asks "is each thing in the code also on the page?". That
# catches an ADDITION that was never republished, which is the common mistake,
# and nothing else. A row deleted from the page, a type changed from integer to
# text, a unit dropped, a vocabulary value remapped -- none of those make any
# assertion above fail, because each one only ever looks for the presence of
# something it already knows about.
#
# So the gate is closed the other way too: regenerate the page from the code in
# a scratch copy of the tree, and require the result to equal the committed one
# byte for byte. That is only worth doing because the generator is
# deterministic -- measured: no timestamp, no absolute path, no unordered set
# reaches the output.
#
# The gap, measured rather than argued. One field's units changed from metres to
# kilometres in fiberq/models/schema.py, with the published page left exactly as
# committed:
#
#     the nine tests above          9 passed
#     test_the_published_page_...   1 failed
#
# The field's NAME did not move, and the name is all the nine ever looked for.
# A consumer reading the published page would have written kilometres into a
# column the plugin fills with metres, and nothing in CI would have said a word.

import os            # noqa: E402
import shutil        # noqa: E402
import subprocess    # noqa: E402
import sys           # noqa: E402

import pytest        # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "tools" / "gen_interchange_mapping.py"

#: Everything the generator reads. All four are pure-stdlib modules it loads by
#: path, so a scratch copy of exactly these files regenerates the page -- the
#: repo itself is mounted read-only in CI and must not be written to.
GENERATOR_INPUTS = (
    "tools/gen_interchange_mapping.py",
    "fiberq/models/schema.py",
    "fiberq/core/interchange.py",
    "fiberq/core/interchange_fields.py",
)


def _scratch_tree(tmp_path):
    for relative in GENERATOR_INPUTS:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    (tmp_path / "docs").mkdir(exist_ok=True)
    return tmp_path


def _regenerate(tree):
    """Run the generator in ``tree`` and return its page text."""
    done = subprocess.run(  # nosec B603 - fixed script path, no shell, no user input
        [sys.executable, str(tree / "tools" / "gen_interchange_mapping.py")],
        cwd=str(tree), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        timeout=120, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert done.returncode == 0, done.stdout.decode("utf-8", "replace")
    return (tree / "docs" / "interchange-mapping.md").read_text(encoding="utf-8")


@pytest.fixture
def scratch(tmp_path):
    return _scratch_tree(tmp_path)


def test_the_published_page_is_what_the_code_generates(scratch):
    """The two-way gate. Regenerate and compare, byte for byte.

    If this fails, the page is stale: run ``make mapping-doc`` and commit the
    result. It fails for a removal, a renamed canonical field, a changed type or
    unit, and a remapped vocabulary value -- none of which any other test here
    can see.
    """
    assert _regenerate(scratch) == TEXT, (
        "docs/interchange-mapping.md is not what tools/gen_interchange_mapping.py produces "
        "from the current code. Run `make mapping-doc` and commit the page.")


def test_the_generator_is_deterministic(scratch, tmp_path):
    """The comparison above is only meaningful if two runs agree.

    A generator that emitted a timestamp, an absolute path or an unordered set
    would make the gate fail at random, and the first reaction to a flaky gate
    is to delete it.
    """
    first = _regenerate(scratch)
    second = _regenerate(_scratch_tree(tmp_path / "again"))
    assert first == second


def test_a_row_removed_from_the_page_fails_the_gate(scratch):
    """Seeded: the removal case, which is the whole reason for this gate."""
    page = scratch / "docs" / "interchange-mapping.md"
    lines = TEXT.splitlines()
    rows = [i for i, line in enumerate(lines) if line.startswith("| `")]
    assert rows, "no field rows on the page; this test is stale"
    del lines[rows[len(rows) // 2]]
    page.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert page.read_text(encoding="utf-8") != TEXT
    assert _regenerate(scratch) == TEXT, (
        "the generator did not restore the deleted row, so the comparison in "
        "test_the_published_page_is_what_the_code_generates could not have caught it")


def test_a_changed_unit_fails_the_gate(scratch):
    """Seeded: a field that keeps its name and changes its meaning.

    This is the quiet one. Every other test on this page looks for the field's
    *name*, and the name does not move -- so the published units would say
    metres while the code said kilometres, and nothing would fail.
    """
    source = scratch / "fiberq" / "models" / "schema.py"
    text = source.read_text(encoding="utf-8")
    assert 'units="m"' in text, "no metre-units field in the schema; this test is stale"
    source.write_text(text.replace('units="m"', 'units="km"', 1), encoding="utf-8")

    regenerated = _regenerate(scratch)
    assert regenerated != TEXT, (
        "a unit changed in the code and the regenerated page was identical; the gate "
        "cannot see a field whose meaning changed while its name stayed")


def test_a_changed_type_fails_the_gate(scratch):
    """Seeded: integer becomes text. A consumer that trusted the published type
    would write a column of the wrong kind."""
    source = scratch / "fiberq" / "models" / "schema.py"
    text = source.read_text(encoding="utf-8")
    assert '"Fibers per tube", "int"' in text, "roster changed; this test is stale"
    source.write_text(
        text.replace('"Fibers per tube", "int"', '"Fibers per tube", "text"', 1),
        encoding="utf-8")

    assert _regenerate(scratch) != TEXT


def test_a_field_removed_from_the_code_fails_the_gate(scratch):
    """Seeded: the mirror of the first one. A field deleted from the schema must
    make the committed page wrong, not silently shrink it."""
    source = scratch / "fiberq" / "core" / "interchange_fields.py"
    text = source.read_text(encoding="utf-8")
    needle = '    "color_standard": "color_standard",\n'
    assert needle in text, "roster changed; this test is stale"
    source.write_text(text.replace(needle, "", 1), encoding="utf-8")

    assert _regenerate(scratch) != TEXT
