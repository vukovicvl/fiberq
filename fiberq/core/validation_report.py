"""Audit-ready reports from a validation run (WP2, task 2.2).

Three formats, one source of truth. :func:`result_to_dict` builds the whole
report as plain Python; JSON serialises it, CSV flattens the issue list, and HTML
renders it. Adding a fourth format means writing a renderer, not re-deriving what
a report contains.

Design constraints worth stating, because they are easy to break later:

* **No QGIS import.** This module runs on a ``ValidationResult`` and nothing else,
  so reports can be generated and diffed in a plain pytest process.
* **No wall clock.** The timestamp comes from the run, not from ``datetime.now()``
  at render time -- a report re-rendered tomorrow must not claim to be new.
* **Machine fields stay untranslated.** ``rule_id``, ``severity`` and ``category``
  are stable identifiers that WP3 interchange and any downstream tooling will key
  on. Only human-readable prose is translated, and only in the HTML renderer.
* **Self-contained HTML.** No CDN, no external CSS or fonts: an audit document has
  to open from a USB stick in five years.
"""
import csv
import html
import io
import json
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from .validation_manager import SEVERITY_ORDER, Severity, ValidationResult

logger = get_logger(__name__)

#: Bumped when the JSON shape changes in a way a consumer would notice. WP3 will
#: read this before parsing.
REPORT_FORMAT_VERSION = "1.0"

#: Column order for the CSV. Chosen so the file is readable left-to-right without
#: horizontal scrolling: what, how bad, where, then the prose.
CSV_COLUMNS = [
    "rule_id",
    "severity",
    "category",
    "layer",
    "feature_id",
    "fiberq_uuid",
    "x",
    "y",
    "message",
    "fix_hint",
]


# ---------------------------------------------------------------------------
# The report, as data
# ---------------------------------------------------------------------------

def issue_to_dict(issue) -> Dict[str, Any]:
    """One issue as plain data. Keys are stable; do not translate them."""
    where = issue.where or (None, None)
    return {
        "rule_id": issue.rule_id,
        "severity": issue.severity.value,
        "category": issue.category,
        "message": issue.message,
        "layer": issue.layer_name,
        "layer_id": issue.layer_id,
        "feature_id": issue.feature_id if issue.feature_id >= 0 else None,
        "fiberq_uuid": issue.fiberq_uuid or None,
        "x": where[0],
        "y": where[1],
        "fix_hint": issue.fix_hint or None,
        "details": issue.details or {},
    }


def result_to_dict(result: ValidationResult) -> Dict[str, Any]:
    """The full report as plain data -- the single source every format renders."""
    counts = result.counts_by_severity()
    issues = [issue_to_dict(i) for i in result.sorted_issues()]

    by_rule: Dict[str, int] = {}
    by_layer: Dict[str, int] = {}
    for issue in result.issues:
        by_rule[issue.rule_id] = by_rule.get(issue.rule_id, 0) + 1
        if issue.layer_name:
            by_layer[issue.layer_name] = by_layer.get(issue.layer_name, 0) + 1

    return {
        "format": "fiberq-validation-report",
        "format_version": REPORT_FORMAT_VERSION,
        "project": {
            "name": result.project_name,
            "crs": result.crs,
            "schema_version": result.schema_version,
            "feature_counts": dict(result.feature_counts),
        },
        "run": {
            "timestamp": result.timestamp,
            "plugin_version": result.plugin_version,
            "rules_run": list(result.ran_rules),
            "rules_skipped": list(result.skipped_rules),
            "rule_errors": list(result.rule_errors),
        },
        "summary": {
            "total": len(result.issues),
            "by_severity": counts,
            "by_category": result.counts_by_category(),
            "by_rule": dict(sorted(by_rule.items())),
            "by_layer": dict(sorted(by_layer.items())),
            # The one judgement the report makes: errors mean the project is not
            # fit to hand over. Warnings and info do not.
            "passed": counts["error"] == 0,
        },
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def to_json(result: ValidationResult, indent: int = 2) -> str:
    """The report as JSON. Sorted keys so two runs diff cleanly in git."""
    return json.dumps(result_to_dict(result), indent=indent,
                      ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def to_csv(result: ValidationResult) -> str:
    """The issue list as CSV, for spreadsheets and issue trackers.

    Only the issues: a summary block above the header would break every CSV
    reader in existence. The counts live in the JSON and HTML reports.

    Written with CRLF because that is what the csv module and Excel both expect;
    callers must open files with ``newline=""`` to avoid doubling it.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS,
                            extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for issue in result.sorted_issues():
        row = issue_to_dict(issue)
        writer.writerow({k: ("" if row.get(k) is None else row.get(k))
                         for k in CSV_COLUMNS})
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_SEVERITY_COLOUR = {
    "error": "#c83c3c",
    "warning": "#c88c1e",
    "info": "#5a8cc8",
}

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font: 15px/1.55 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  margin: 0; padding: 2rem 1.5rem; background: #fff; color: #1c1c1c;
}
main { max-width: 70rem; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
h2 { font-size: 1.1rem; margin: 2rem 0 .75rem; }
.sub { color: #666; margin: 0 0 1.5rem; font-size: .9rem; }
.verdict {
  display: inline-block; padding: .45rem .9rem; border-radius: .3rem;
  font-weight: 600; margin-bottom: 1.5rem;
}
.verdict.pass { background: #e6f4e6; color: #1f6f2b; }
.verdict.fail { background: #fbe6e6; color: #a32020; }
.cards { display: flex; flex-wrap: wrap; gap: .75rem; margin-bottom: .5rem; }
.card {
  border: 1px solid #ddd; border-radius: .35rem; padding: .6rem 1rem; min-width: 7rem;
}
.card .n { font-size: 1.5rem; font-weight: 600; display: block; }
.card .k { font-size: .8rem; color: #666; text-transform: uppercase;
           letter-spacing: .04em; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .88rem; }
th, td { text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #e6e6e6;
         vertical-align: top; }
th { background: #f6f6f6; font-weight: 600; white-space: nowrap; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.sev { font-weight: 600; white-space: nowrap; }
.rule { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
.hint { color: #666; font-size: .85em; display: block; margin-top: .15rem; }
.meta { font-size: .85rem; color: #666; }
.meta dt { font-weight: 600; color: #333; }
.meta dl { display: grid; grid-template-columns: max-content 1fr;
           gap: .2rem 1rem; margin: 0; }
.empty { padding: 2rem; text-align: center; color: #666; border: 1px dashed #ccc;
         border-radius: .35rem; }
footer { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #e6e6e6;
         font-size: .8rem; color: #888; }
@media (prefers-color-scheme: dark) {
  body { background: #1b1b1d; color: #e8e8e8; }
  .sub, .card .k, .hint, .meta, footer { color: #a0a0a0; }
  .card, .empty { border-color: #3a3a3d; }
  th { background: #26262a; }
  th, td { border-bottom-color: #313135; }
  .meta dt { color: #d0d0d0; }
  .verdict.pass { background: #1e3524; color: #7fd18f; }
  .verdict.fail { background: #3a1f1f; color: #e88b8b; }
}
@media print {
  body { padding: 0; }
  .card, th { background: #fff !important; }
}
"""


def _tr(text: str) -> str:
    """Translate a report string if Qt is available, else pass it through.

    The exporters are deliberately importable without QGIS (see the module
    docstring), so translation has to be optional rather than assumed.
    """
    try:
        from qgis.PyQt.QtCore import QCoreApplication
        return QCoreApplication.translate("ValidationReport", text)
    except Exception:
        return text


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _card(number, label) -> str:
    return (f'<div class="card"><span class="n">{_esc(number)}</span>'
            f'<span class="k">{_esc(label)}</span></div>')


def to_html(result: ValidationResult, title: Optional[str] = None) -> str:
    """A self-contained HTML report: no external CSS, fonts, scripts or images.

    Styled for light and dark, and for paper -- this is the artefact that gets
    attached to a handover email or printed for an audit file.
    """
    data = result_to_dict(result)
    project = data["project"]
    run = data["run"]
    summary = data["summary"]
    counts = summary["by_severity"]

    doc_title = title or _tr("FiberQ validation report")
    heading = project["name"] or _tr("Untitled project")

    passed = summary["passed"]
    verdict_class = "pass" if passed else "fail"
    verdict_text = (_tr("No errors — project is structurally sound")
                    if passed else _tr("Errors found — not ready to hand over"))

    parts: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(doc_title)} — {_esc(heading)}</title>",
        f"<style>{_CSS}</style>",
        "</head><body><main>",
        f"<h1>{_esc(doc_title)}</h1>",
        f'<p class="sub">{_esc(heading)}</p>',
        f'<p class="verdict {verdict_class}">{_esc(verdict_text)}</p>',
        "<div class=\"cards\">",
        _card(counts["error"], _tr("Errors")),
        _card(counts["warning"], _tr("Warnings")),
        _card(counts["info"], _tr("Info")),
        _card(summary["total"], _tr("Total")),
        "</div>",
    ]

    # --- run metadata -------------------------------------------------------
    meta_rows = [
        (_tr("Coordinate system"), project["crs"]),
        (_tr("Schema version"), project["schema_version"]),
        (_tr("Plugin version"), run["plugin_version"]),
        (_tr("Run at"), run["timestamp"]),
        (_tr("Rules run"), len(run["rules_run"])),
    ]
    if run["rules_skipped"]:
        meta_rows.append((_tr("Rules skipped"), ", ".join(run["rules_skipped"])))
    parts.append(f'<h2>{_esc(_tr("Run"))}</h2><div class="meta"><dl>')
    for key, value in meta_rows:
        if value in (None, "", []):
            continue
        parts.append(f"<dt>{_esc(key)}</dt><dd>{_esc(value)}</dd>")
    parts.append("</dl></div>")

    # A rule that crashed is a gap in coverage, not a clean result. Say so loudly
    # rather than letting the summary imply the project was fully checked.
    if run["rule_errors"]:
        parts.append(f'<h2>{_esc(_tr("Rules that failed to run"))}</h2><ul>')
        for err in run["rule_errors"]:
            parts.append(f"<li>{_esc(err)}</li>")
        parts.append("</ul>")

    # --- issues -------------------------------------------------------------
    parts.append(f'<h2>{_esc(_tr("Issues"))}</h2>')
    if not data["issues"]:
        parts.append(f'<p class="empty">{_esc(_tr("No issues found."))}</p>')
    else:
        parts.append('<div class="scroll"><table><thead><tr>')
        for column in (_tr("Severity"), _tr("Rule"), _tr("Layer"),
                       _tr("Feature"), _tr("Message")):
            parts.append(f"<th>{_esc(column)}</th>")
        parts.append("</tr></thead><tbody>")

        labels = {"error": _tr("Error"), "warning": _tr("Warning"),
                  "info": _tr("Info")}
        for issue in data["issues"]:
            colour = _SEVERITY_COLOUR.get(issue["severity"], "#666")
            label = labels.get(issue["severity"], issue["severity"])
            feature = "" if issue["feature_id"] is None else issue["feature_id"]
            hint = (f'<span class="hint">{_esc(issue["fix_hint"])}</span>'
                    if issue["fix_hint"] else "")
            parts.append(
                "<tr>"
                f'<td class="sev" style="color:{colour}">{_esc(label)}</td>'
                f'<td class="rule">{_esc(issue["rule_id"])}</td>'
                f'<td>{_esc(issue["layer"])}</td>'
                f'<td class="num">{_esc(feature)}</td>'
                f'<td>{_esc(issue["message"])}{hint}</td>'
                "</tr>"
            )
        parts.append("</tbody></table></div>")

    # --- breakdown ----------------------------------------------------------
    if summary["by_layer"]:
        parts.append(f'<h2>{_esc(_tr("Issues by layer"))}</h2>'
                     '<div class="scroll"><table><thead><tr>'
                     f'<th>{_esc(_tr("Layer"))}</th>'
                     f'<th>{_esc(_tr("Issues"))}</th>'
                     "</tr></thead><tbody>")
        for layer, count in sorted(summary["by_layer"].items(),
                                   key=lambda kv: (-kv[1], kv[0])):
            parts.append(f'<tr><td>{_esc(layer)}</td>'
                         f'<td class="num">{_esc(count)}</td></tr>')
        parts.append("</tbody></table></div>")

    parts += [
        "<footer>",
        _esc(_tr("Generated by the FiberQ QGIS plugin.")),
        " ",
        _esc(_tr("Machine-readable JSON and CSV of the same run are available "
                 "from the same export menu.")),
        "</footer>",
        "</main></body></html>",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

#: Extension -> renderer. Drives both the file-dialog filter and the writer, so
#: the two cannot fall out of step.
FORMATS = {
    "html": ("HTML", to_html),
    "json": ("JSON", to_json),
    "csv": ("CSV", to_csv),
}


def format_for_path(path: str) -> str:
    """The format key implied by a filename, defaulting to HTML."""
    lowered = (path or "").lower()
    for key in FORMATS:
        if lowered.endswith("." + key):
            return key
    return "html"


def render(result: ValidationResult, fmt: str) -> str:
    """Render ``result`` in ``fmt`` ("html", "json" or "csv")."""
    try:
        _, renderer = FORMATS[fmt]
    except KeyError:
        raise ValueError(f"Unknown report format: {fmt!r}")
    return renderer(result)


def write_report(result: ValidationResult, path: str, fmt: Optional[str] = None) -> str:
    """Render and write, returning the format used.

    ``newline=""`` matters: the csv module already emits CRLF, and letting Python
    translate the line endings again produces a file with blank rows between
    every record in Excel.
    """
    fmt = fmt or format_for_path(path)
    text = render(result, fmt)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    logger.info(f"Wrote {fmt.upper()} validation report to {path}")
    return fmt


def severity_rank(severity: Severity) -> int:
    """Exposed so report consumers can sort without importing the manager."""
    return SEVERITY_ORDER.get(severity, 9)
