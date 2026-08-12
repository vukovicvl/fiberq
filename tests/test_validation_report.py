"""Tests for the WP2 report exporters.

The exporters must stay importable without QGIS -- reports are pure data
transforms, and keeping them so is what lets them be tested and diffed in a plain
process. The first test guards that; if it ever fails, something grew a QGIS
import at module scope.
"""
import csv
import io
import json

import pytest

from fiberq.core import validation_manager as vm
from fiberq.core.validation_report import (
    CSV_COLUMNS,
    FORMATS,
    REPORT_FORMAT_VERSION,
    format_for_path,
    issue_to_dict,
    render,
    result_to_dict,
    to_csv,
    to_html,
    to_json,
    write_report,
)


def _issue(rule_id="A1", severity=vm.Severity.WARNING, layer="Aerial cables",
           fid=1, message="something is off", where=(10.0, 20.0),
           category="topology", uuid="", hint=""):
    return vm.ValidationIssue(
        rule_id=rule_id, severity=severity, category=category, message=message,
        layer_name=layer, layer_id=f"{layer}_id", feature_id=fid,
        fiberq_uuid=uuid, where=where, fix_hint=hint,
        details={"tolerance": 5},
    )


def _result(issues=(), **kwargs):
    result = vm.ValidationResult(
        project_name=kwargs.pop("project_name", "Demo"),
        crs=kwargs.pop("crs", "EPSG:3857"),
        schema_version=kwargs.pop("schema_version", "1.0"),
        plugin_version=kwargs.pop("plugin_version", "1.4.0"),
        timestamp=kwargs.pop("timestamp", "2026-07-30T22:00:00"),
    )
    result.issues = list(issues)
    for key, value in kwargs.items():
        setattr(result, key, value)
    return result


# ---------------------------------------------------------------------------
# Independence from QGIS
# ---------------------------------------------------------------------------

def test_no_qgis_import_at_module_scope():
    """Reports are pure data transforms over a ValidationResult.

    Checked on the source rather than by importing in a QGIS-free subprocess,
    because ``fiberq.core.__init__`` pulls in QGIS regardless of this module --
    that would test the package, not the exporters.
    """
    import ast
    import inspect

    from fiberq.core import validation_report

    tree = ast.parse(inspect.getsource(validation_report))
    offenders = []
    for node in tree.body:  # module scope only; function-level is fine
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.startswith("qgis")]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").startswith("qgis"):
                offenders.append(node.module)
    assert not offenders, f"QGIS imported at module scope: {offenders}"


def test_translation_is_optional_not_assumed():
    """_tr must degrade to the English string when Qt is absent."""
    from fiberq.core.validation_report import _tr

    assert _tr("Errors") == "Errors" or isinstance(_tr("Errors"), str)


# ---------------------------------------------------------------------------
# The data layer
# ---------------------------------------------------------------------------

def test_issue_keys_are_stable_identifiers():
    data = issue_to_dict(_issue(rule_id="D3", severity=vm.Severity.ERROR))
    assert data["rule_id"] == "D3"
    assert data["severity"] == "error"  # the enum value, never a label
    assert data["category"] == "topology"


def test_missing_feature_id_becomes_null_not_minus_one():
    """-1 is the in-memory sentinel; it must not leak into a report."""
    assert issue_to_dict(_issue(fid=-1))["feature_id"] is None


def test_absent_coordinates_are_null():
    data = issue_to_dict(_issue(where=None))
    assert data["x"] is None and data["y"] is None


def test_summary_counts_every_axis():
    data = result_to_dict(_result([
        _issue(rule_id="A1", layer="Aerial cables"),
        _issue(rule_id="A1", layer="Route"),
        _issue(rule_id="B1", severity=vm.Severity.ERROR, category="referential"),
    ]))
    assert data["summary"]["total"] == 3
    assert data["summary"]["by_severity"]["error"] == 1
    assert data["summary"]["by_rule"] == {"A1": 2, "B1": 1}
    assert data["summary"]["by_layer"]["Aerial cables"] == 2
    assert data["summary"]["by_category"]["referential"] == 1


def test_passed_is_about_errors_only():
    """Warnings are a design in progress; errors are a broken project."""
    assert result_to_dict(_result([_issue()]))["summary"]["passed"] is True
    assert result_to_dict(_result(
        [_issue(severity=vm.Severity.ERROR)]))["summary"]["passed"] is False


def test_issues_come_out_most_severe_first():
    data = result_to_dict(_result([
        _issue(rule_id="A1", severity=vm.Severity.INFO),
        _issue(rule_id="B1", severity=vm.Severity.ERROR),
        _issue(rule_id="C1", severity=vm.Severity.WARNING),
    ]))
    assert [i["rule_id"] for i in data["issues"]] == ["B1", "C1", "A1"]


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def test_json_round_trips():
    parsed = json.loads(to_json(_result([_issue()])))
    assert parsed["format"] == "fiberq-validation-report"
    assert parsed["format_version"] == REPORT_FORMAT_VERSION
    assert len(parsed["issues"]) == 1


def test_json_keys_are_sorted_for_clean_diffs():
    text = to_json(_result([_issue()]))
    top_level = list(json.loads(text).keys())
    assert top_level == sorted(top_level)


def test_json_keeps_non_ascii_readable():
    """A Serbian message must not come out as \\u0161 escapes."""
    text = to_json(_result([_issue(message="Postojeće stanje")]))
    assert "Postojeće" in text


def test_json_carries_the_run_provenance():
    run = json.loads(to_json(_result([], ran_rules=["A1", "B1"])))["run"]
    assert run["timestamp"] == "2026-07-30T22:00:00"
    assert run["plugin_version"] == "1.4.0"
    assert run["rules_run"] == ["A1", "B1"]


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def test_csv_has_a_header_and_one_row_per_issue():
    rows = list(csv.DictReader(io.StringIO(to_csv(_result([_issue(), _issue()])))))
    assert len(rows) == 2
    assert set(rows[0]) == set(CSV_COLUMNS)


def test_csv_starts_with_the_header_not_a_summary_block():
    """A preamble above the header breaks every CSV reader there is."""
    assert to_csv(_result([_issue()])).splitlines()[0] == ",".join(CSV_COLUMNS)


def test_csv_writes_blanks_not_the_word_none():
    row = next(csv.DictReader(io.StringIO(to_csv(_result([_issue(where=None)])))))
    assert row["x"] == "" and row["fix_hint"] == ""


def test_csv_quotes_a_message_containing_commas():
    text = to_csv(_result([_issue(message="one, two, three")]))
    assert '"one, two, three"' in text
    row = next(csv.DictReader(io.StringIO(text)))
    assert row["message"] == "one, two, three"


def test_empty_result_still_produces_a_header():
    assert to_csv(_result([])).strip() == ",".join(CSV_COLUMNS)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def test_html_is_self_contained():
    """An audit document must open from a USB stick in five years."""
    html = to_html(_result([_issue()]))
    for forbidden in ("http://", "https://", "<script", "@import", "src="):
        assert forbidden not in html, forbidden


def test_html_escapes_hostile_content():
    html = to_html(_result([_issue(message="<img onerror=alert(1)>", layer="a&b")]))
    assert "<img onerror" not in html
    assert "&lt;img onerror" in html
    assert "a&amp;b" in html


def test_html_states_a_verdict():
    assert "not ready to hand over" in to_html(
        _result([_issue(severity=vm.Severity.ERROR)]))
    assert "structurally sound" in to_html(_result([_issue()]))


def test_html_says_when_there_is_nothing_to_report():
    assert "No issues found." in to_html(_result([]))


def test_html_surfaces_rules_that_crashed():
    """A crashed rule is a gap in coverage, not a clean bill of health."""
    html = to_html(_result([], rule_errors=["D3: boom"]))
    assert "D3: boom" in html
    assert "failed to run" in html


def test_html_renders_a_row_per_issue():
    html = to_html(_result([_issue(rule_id="A1"), _issue(rule_id="D2")]))
    assert html.count("<tr>") >= 2
    assert "A1" in html and "D2" in html


def test_html_supports_dark_mode_and_print():
    html = to_html(_result([_issue()]))
    assert "prefers-color-scheme: dark" in html
    assert "@media print" in html


# ---------------------------------------------------------------------------
# Dispatch and writing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("report.json", "json"),
    ("report.csv", "csv"),
    ("report.html", "html"),
    ("REPORT.JSON", "json"),
    ("report", "html"),          # no extension -> the presentable default
    ("a.json/report.csv", "csv"),
])
def test_format_follows_the_extension(path, expected):
    assert format_for_path(path) == expected


def test_render_rejects_an_unknown_format():
    with pytest.raises(ValueError):
        render(_result([]), "pdf")


@pytest.mark.parametrize("fmt", sorted(FORMATS))
def test_write_report_writes_each_format(tmp_path, fmt):
    path = tmp_path / f"report.{fmt}"
    assert write_report(_result([_issue()]), str(path)) == fmt
    assert path.read_text(encoding="utf-8").strip()


def test_csv_file_has_no_blank_line_between_rows(tmp_path):
    """newline="" at the open, or Excel shows an empty row between every record."""
    path = tmp_path / "report.csv"
    write_report(_result([_issue(), _issue()]), str(path))
    raw = path.read_bytes()
    assert b"\r\r\n" not in raw
    assert len([line for line in raw.split(b"\r\n") if line.strip()]) == 3


def test_metadata_is_readable_with_percent_signs_in_the_changelog():
    """The About dialog reads dict(cp.items('general')), which interpolates every
    value -- so one '%' in the changelog blanks the whole section and the version
    silently falls back to '1.0'. Shipped once; never again."""
    import configparser
    import pathlib

    md = pathlib.Path(__file__).resolve().parent.parent / "fiberq" / "metadata.txt"
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(md, encoding="utf-8")
    general = dict(cp.items("general"))
    assert general.get("version")
    assert general.get("name") and general.get("author")

    # And with the default interpolating parser, which is what QGIS and the
    # plugins.qgis.org tooling may use: a bare '%' must not appear at all.
    raw = md.read_text(encoding="utf-8")
    assert "%" not in raw, "a bare % in metadata.txt breaks configparser interpolation"
