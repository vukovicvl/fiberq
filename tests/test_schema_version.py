"""Tests for the project schema-version marker (WP1a).

These need a QgsApplication (provided by pytest-qgis) because they read/write a
QgsProject entry. They use fresh QgsProject() instances so the singleton project
is never touched.
"""
from qgis.core import QgsProject

from fiberq.core import schema_version as sv


def test_absent_reads_baseline(qgis_app):
    p = QgsProject()
    assert sv.read_project_schema_version(p) == sv.BASELINE_VERSION


def test_mark_then_read_current(qgis_app):
    p = QgsProject()
    assert sv.mark_project_current(p) is True
    assert sv.read_project_schema_version(p) == sv.SCHEMA_VERSION


def test_needs_upgrade_transitions(qgis_app):
    p = QgsProject()
    assert sv.needs_upgrade(p) is True   # absent -> baseline != current
    sv.mark_project_current(p)
    assert sv.needs_upgrade(p) is False


def test_explicit_version_roundtrip(qgis_app):
    p = QgsProject()
    assert sv.write_project_schema_version("0.9", p) is True
    assert sv.read_project_schema_version(p) == "0.9"
    assert sv.needs_upgrade(p) is True   # 0.9 != current
