"""The published demo project and sample report must stay true.

docs/samples/ is a deliverable: people download the project, run the validator and
expect the numbers to match the report we shipped. These tests fail if the demo
stops producing what it claims, or if the committed report drifts away from a
fresh run -- so a rule change forces a regeneration instead of quietly
invalidating the published artefact.
"""
import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SAMPLES = REPO / "docs" / "samples"
FIXTURES = REPO / "tests" / "fixtures"

if str(FIXTURES) not in sys.path:
    sys.path.insert(0, str(FIXTURES))

from make_demo_project import FAULTS, build_demo_gpkg, build_demo_project  # noqa: E402


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """A freshly built demo project, loaded and validated."""
    from qgis.core import QgsProject

    from fiberq.core.validation_manager import run_validation

    work = tmp_path_factory.mktemp("demo")
    gpkg = str(work / "demo_project.gpkg")
    qgz = str(work / "demo_project.qgz")
    build_demo_gpkg(gpkg)
    build_demo_project(gpkg, qgz)

    project = QgsProject()
    assert project.read(qgz)
    result = run_validation(project=project, timestamp="2026-07-30T22:00:00",
                            plugin_version="1.4.0")
    return result


def _by_rule(result):
    out = {}
    for issue in result.issues:
        out.setdefault(issue.rule_id, []).append(issue)
    return out


# ---------------------------------------------------------------------------
# The demo does what its docstring says
# ---------------------------------------------------------------------------

def test_every_planted_fault_is_found(demo):
    missing = sorted(set(FAULTS) - set(_by_rule(demo)))
    assert not missing, f"planted but not reported: {missing}"


def test_nothing_unplanted_fires(demo):
    """A demo that trips a rule nobody meant to trip teaches the wrong lesson."""
    extra = sorted(set(_by_rule(demo)) - set(FAULTS))
    assert not extra, f"reported but not planted: {extra}"


def test_no_rule_crashes_on_the_demo(demo):
    assert demo.rule_errors == []


def test_every_registered_rule_actually_runs(demo):
    from fiberq.core.validation_rules import RULES

    assert len(demo.ran_rules) == len(RULES)


def test_the_headline_numbers_are_what_the_docs_promise(demo):
    counts = demo.counts_by_severity()
    assert (counts["error"], counts["warning"], counts["info"]) == (1, 7, 0)


def test_identity_is_clean_so_b4_stays_quiet(demo):
    """B4 is an ERROR rule; a demo that trips it would look broken, not instructive."""
    assert "B4" not in _by_rule(demo)


def test_the_working_slack_reference_resolves(demo):
    """SL-1 must be valid, or B1's finding on SL-2 proves nothing."""
    assert len(_by_rule(demo).get("B1", [])) == 1


def test_a_stranded_cable_reports_both_ends(demo):
    assert len(_by_rule(demo)["A1"]) == 2


def test_recalculating_lengths_clears_the_d3_finding(tmp_path):
    """docs/samples/README.md tells readers to try this; it had better work.

    Builds its own copy rather than reusing the module-scoped fixture, because
    recalculating writes to the GeoPackage and every other test here expects the
    demo in its published state.
    """
    from qgis.core import QgsProject

    from fiberq.core.length_manager import recalculate_lengths
    from fiberq.core.validation_manager import run_validation

    gpkg = str(tmp_path / "demo_project.gpkg")
    qgz = str(tmp_path / "demo_project.qgz")
    build_demo_gpkg(gpkg)
    build_demo_project(gpkg, qgz)

    project = QgsProject()
    assert project.read(qgz)

    before = run_validation(project=project, timestamp="t", plugin_version="v")
    assert "D3" in _by_rule(before)

    recalculate_lengths(project)

    after = run_validation(project=project, timestamp="t", plugin_version="v")
    assert "D3" not in _by_rule(after)
    # And nothing else changed: the count drops by exactly the one D3 finding.
    assert len(after.issues) == len(before.issues) - 1


# ---------------------------------------------------------------------------
# The committed artefacts match
# ---------------------------------------------------------------------------

def test_the_sample_files_are_committed():
    for name in ("demo_project.gpkg", "demo_project.qgz", "demo-validation.html",
                 "demo-validation.json", "demo-validation.csv", "README.md",
                 "generate.py"):
        assert (SAMPLES / name).exists(), f"docs/samples/{name} is missing"


def test_the_committed_json_matches_a_fresh_run(demo):
    """If this fails, run: python docs/samples/generate.py"""
    from fiberq.core.validation_report import result_to_dict

    committed = json.loads((SAMPLES / "demo-validation.json").read_text(
        encoding="utf-8"))
    fresh = result_to_dict(demo)

    assert committed["summary"]["by_rule"] == fresh["summary"]["by_rule"]
    assert committed["summary"]["by_severity"] == fresh["summary"]["by_severity"]
    assert committed["summary"]["passed"] == fresh["summary"]["passed"]
    assert [i["rule_id"] for i in committed["issues"]] == \
        [i["rule_id"] for i in fresh["issues"]]  # noqa: W504


def test_the_committed_html_is_self_contained():
    html = (SAMPLES / "demo-validation.html").read_text(encoding="utf-8")
    for forbidden in ("http://", "https://", "<script", "src="):
        assert forbidden not in html, forbidden


def test_the_readme_documents_every_planted_fault():
    readme = (SAMPLES / "README.md").read_text(encoding="utf-8")
    for rule_id in FAULTS:
        assert f"**{rule_id}**" in readme, f"{rule_id} is not in docs/samples/README.md"


def test_the_rules_doc_covers_every_registered_rule():
    """A rule with no documentation is a rule users cannot act on."""
    from fiberq.core.validation_rules import RULES

    doc = (REPO / "docs" / "validation-rules.md").read_text(encoding="utf-8")
    for rule in RULES:
        assert f"### {rule.id} " in doc, f"{rule.id} is undocumented"


def test_the_demo_is_stamped_with_the_current_schema_version(demo):
    """A sample report reading 'schema version 0' would tell readers to migrate."""
    from fiberq.models import schema

    assert demo.schema_version == schema.SCHEMA_VERSION
