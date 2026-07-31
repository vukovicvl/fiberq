#!/usr/bin/env python3
"""Regenerate everything in ``docs/samples/`` from the demo project.

Run inside a QGIS environment (the CI containers work):

    python docs/samples/generate.py

Writes the demo GeoPackage, the QGIS project, and the three report formats of a
validation run over them. Everything here is committed, so the published sample
matches what the plugin actually produces -- but that only stays true if this is
re-run whenever the rules change. ``tests/test_sample_report.py`` fails if the
committed HTML drifts from a fresh run.

The timestamp is fixed rather than taken from the clock: a regenerated report
should differ only where the rules differ, so the diff is reviewable.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
for path in (REPO_ROOT, os.path.join(REPO_ROOT, "tests", "fixtures")):
    if path not in sys.path:
        sys.path.insert(0, path)

#: Fixed so regenerating produces a clean diff. Bump it when the demo changes
#: enough that "when was this generated" is a fair question.
TIMESTAMP = "2026-07-30T22:00:00"

GPKG = os.path.join(HERE, "demo_project.gpkg")
QGZ = os.path.join(HERE, "demo_project.qgz")
REPORT_STEM = os.path.join(HERE, "demo-validation")


def build(timestamp: str = TIMESTAMP):
    """Write the demo data and its reports. Returns the ValidationResult."""
    from qgis.core import QgsProject

    from make_demo_project import build_demo_gpkg, build_demo_project

    from fiberq import __version__ as plugin_version
    from fiberq.core.validation_manager import run_validation
    from fiberq.core.validation_report import write_report

    build_demo_gpkg(GPKG)
    build_demo_project(GPKG, QGZ)

    project = QgsProject()
    project.read(QGZ)

    result = run_validation(project=project, timestamp=timestamp,
                            plugin_version=plugin_version)
    result.project_name = "FiberQ demo project"

    for fmt in ("html", "json", "csv"):
        write_report(result, f"{REPORT_STEM}.{fmt}", fmt)
    return result


def main():
    from qgis.core import QgsApplication

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        result = build()
        counts = result.counts_by_severity()
        print(f"Demo project: {GPKG}")
        print(f"QGIS project: {QGZ}")
        print(f"Reports:      {REPORT_STEM}.{{html,json,csv}}")
        print(f"Result:       {counts['error']} error(s), "
              f"{counts['warning']} warning(s), {counts['info']} info")
    finally:
        app.exitQgis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
