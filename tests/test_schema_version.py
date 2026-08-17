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


# ---------------------------------------------------------------------------
# Cross-version durability (found in QGIS 3.40 field QA)
# ---------------------------------------------------------------------------

def test_falls_back_to_the_geopackage_when_the_entry_is_unreadable(qgis_app, tmp_path):
    """A project saved in QGIS 4 must not read as unstamped in QGIS 3.

    QGIS 4 serialises project properties as <properties name="X">, where QGIS 3
    wrote <X>, and QGIS 3 cannot read the new form. So a QGIS 4 project opened in
    QGIS 3.22-3.44 loses the marker and the migration re-runs on every open,
    dirtying the project. Reproduced in both containers before this fallback.

    A project with no entry at all is exactly what QGIS 3 sees in that case.
    """
    import pathlib
    import sys

    fixtures = pathlib.Path(__file__).resolve().parent / "fixtures"
    if str(fixtures) not in sys.path:
        sys.path.insert(0, str(fixtures))
    from make_demo_project import build_demo_gpkg

    from qgis.core import QgsVectorLayer

    gpkg = str(tmp_path / "demo.gpkg")
    build_demo_gpkg(gpkg)

    p = QgsProject()
    layer = QgsVectorLayer(f"{gpkg}|layername=Route", "Route", "ogr")
    assert layer.isValid()
    p.addMapLayer(layer)

    assert p.readEntry(sv.SCHEMA_VERSION_SCOPE, sv.SCHEMA_VERSION_KEY, "")[0] == ""
    assert sv.read_project_schema_version(p) == sv.SCHEMA_VERSION
    assert sv.needs_upgrade(p) is False


def test_the_project_entry_still_wins(qgis_app, tmp_path):
    """The GeoPackage is the fallback, not the source of truth -- a project
    mid-migration must report what the project says."""
    import pathlib
    import sys

    fixtures = pathlib.Path(__file__).resolve().parent / "fixtures"
    if str(fixtures) not in sys.path:
        sys.path.insert(0, str(fixtures))
    from make_demo_project import build_demo_gpkg

    from qgis.core import QgsVectorLayer

    gpkg = str(tmp_path / "demo.gpkg")
    build_demo_gpkg(gpkg)

    p = QgsProject()
    p.addMapLayer(QgsVectorLayer(f"{gpkg}|layername=Route", "Route", "ogr"))
    sv.write_project_schema_version("0.9", p)

    assert sv.read_project_schema_version(p) == "0.9"


def test_no_geopackage_still_reads_the_baseline(qgis_app):
    """Memory-layer projects have nothing to fall back to; that must not raise."""
    from qgis.core import QgsVectorLayer

    p = QgsProject()
    p.addMapLayer(QgsVectorLayer("Point?crs=EPSG:3857", "Poles", "memory"))
    assert sv.read_project_schema_version(p) == sv.BASELINE_VERSION
