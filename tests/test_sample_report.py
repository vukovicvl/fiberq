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

from make_demo_project import (  # noqa: E402
    FAULTS, NOT_DEMONSTRABLE, build_demo_gpkg, build_demo_project)


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
    assert (counts["error"], counts["warning"], counts["info"]) == (4, 9, 1)


def test_the_demo_demonstrates_every_rule_it_can(demo):
    """The demo is the worked example for docs/validation-rules.md.

    A rule with no demonstrated finding is a rule a reader has never seen fire,
    so the two that a valid project cannot express are named explicitly rather
    than left as a silent gap.
    """
    from fiberq.core.validation_rules import RULES

    demonstrated = set(_by_rule(demo))
    every = {rule.id for rule in RULES}

    assert demonstrated == every - set(NOT_DEMONSTRABLE), (
        f"undemonstrated: {sorted(every - demonstrated - set(NOT_DEMONSTRABLE))}")
    assert set(NOT_DEMONSTRABLE) <= every, "NOT_DEMONSTRABLE names a rule that no longer exists"


def test_b4_fires_once_from_the_planted_duplicate(demo):
    """The duplicate is between the two poles, not whatever feature happened to
    be numbered first -- an earlier version derived the twin's id positionally
    and silently paired it with a Route."""
    b4 = _by_rule(demo)["B4"]
    assert len(b4) == 1
    assert b4[0].layer_name == "Poles"
    assert "Poles" in b4[0].message


def test_the_working_slack_reference_resolves(demo):
    """SL-1 must be valid, or B1's finding on SL-2 proves nothing."""
    assert len(_by_rule(demo).get("B1", [])) == 1


def test_a_stranded_cable_reports_both_ends(demo):
    """Two from AC-2's two ends, one from AC-3's near miss."""
    assert len(_by_rule(demo)["A1"]) == 3


def test_the_near_miss_is_reported_by_both_a1_and_a2(demo):
    """A2 refines A1 rather than partitioning it, so the same endpoint appears
    in both. If A2 ever stops overlapping, the docs are wrong."""
    a2 = _by_rule(demo)["A2"]
    assert len(a2) == 1
    a1_points = {(round(i.where[0], 3), round(i.where[1], 3))
                 for i in _by_rule(demo)["A1"]}
    assert (round(a2[0].where[0], 3), round(a2[0].where[1], 3)) in a1_points


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


def test_the_demo_opens_on_its_network(tmp_path):
    """The committed demo must not open on a blank canvas.

    A project written headlessly has never had a canvas, so unless the extent is
    set explicitly QGIS stores none and the sample opens on empty white -- which
    reads as a broken plugin to the first person who tries it.
    """
    from qgis.core import QgsProject, QgsRectangle, QgsVectorLayer

    project = QgsProject()
    assert project.read(str(SAMPLES / "demo_project.qgz"))

    saved = project.viewSettings().defaultViewExtent()
    assert not saved.isNull(), "demo_project.qgz saves no view extent"

    data = QgsRectangle()
    data.setNull()
    for layer in project.mapLayers().values():
        if isinstance(layer, QgsVectorLayer) and not layer.extent().isNull():
            data.combineExtentWith(layer.extent())
    assert saved.contains(data), f"saved view {saved} does not cover the data {data}"


def test_the_demo_is_stamped_with_the_current_schema_version(demo):
    """A sample report reading 'schema version 0' would tell readers to migrate."""
    from fiberq.models import schema

    assert demo.schema_version == schema.SCHEMA_VERSION
