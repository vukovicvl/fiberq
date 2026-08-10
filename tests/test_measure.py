"""Tests for ground-truth length measurement.

The bug these pin down was found by running the WP2 validator against two real
Serbian projects: routes and cables stored ``QgsGeometry.length()`` (map units)
while pipes stored an ellipsoidal measurement, so a trench and the duct inside it
disagreed by 41% in the same GeoPackage.
"""
import ast
import math
import pathlib

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from fiberq.utils.measure import clear_cache, ground_length, ground_length_km

#: Niš, Serbia -- where the projects that surfaced this live.
LAT = 43.32
LON = 21.90
#: Web Mercator inflates east-west distance by 1/cos(latitude).
SCALE = 1.0 / math.cos(math.radians(LAT))


@pytest.fixture
def project():
    """A standalone project, never QgsProject.instance().

    The singleton is shared by the whole session, so clearing it here would tear
    the ground out from under every other test file (the rest of the suite builds
    its own QgsProject() for the same reason).
    """
    prj = QgsProject()
    # setEllipsoid is a silent no-op until the project has a CRS.
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    prj.setEllipsoid("EPSG:7030")  # WGS 84
    clear_cache()
    yield prj
    clear_cache()


def _mercator_line(length_map_units=1000.0):
    """A horizontal line of the given length in EPSG:3857 metres, at LAT."""
    from qgis.core import QgsCoordinateTransform

    xform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsCoordinateTransformContext())
    start = xform.transform(QgsPointXY(LON, LAT))
    end = QgsPointXY(start.x() + length_map_units, start.y())
    return QgsGeometry.fromPolylineXY([start, end])


def _layer(crs="EPSG:3857"):
    layer = QgsVectorLayer(f"LineString?crs={crs}", "lines", "memory")
    assert layer.isValid()
    return layer


# ---------------------------------------------------------------------------
# The core claim
# ---------------------------------------------------------------------------

def test_ground_length_is_shorter_than_map_length_in_web_mercator(project):
    geom = _mercator_line(1000.0)
    planar = geom.length()
    ground = ground_length(geom, _layer(), project=project)

    assert planar == pytest.approx(1000.0, abs=1.0)
    assert ground < planar
    assert planar / ground == pytest.approx(SCALE, rel=0.01)


def test_ground_length_matches_the_qgis_measure_tool(project):
    """Same configuration the QGIS measure tool uses, so the numbers agree."""
    from qgis.core import QgsDistanceArea

    geom = _mercator_line(1000.0)
    da = QgsDistanceArea()
    da.setSourceCrs(QgsCoordinateReferenceSystem("EPSG:3857"),
                    project.transformContext())
    da.setEllipsoid("EPSG:7030")

    assert ground_length(geom, _layer(), project=project) == pytest.approx(da.measureLength(geom))


def test_km_helper_rounds_like_the_layer_stores_it(project):
    geom = _mercator_line(1000.0)
    assert ground_length_km(geom, _layer(), project=project) == pytest.approx(
        round(ground_length(geom, _layer(), project=project) / 1000.0, 2))


# ---------------------------------------------------------------------------
# Robustness -- a wrong number beats a lost attribute
# ---------------------------------------------------------------------------

def test_none_and_empty_geometries_measure_zero(project):
    assert ground_length(None) == 0.0
    assert ground_length(QgsGeometry()) == 0.0


def test_works_without_a_layer_argument(project):
    """Callers on the canvas can omit the layer; the project CRS is assumed."""
    geom = _mercator_line(1000.0)
    assert ground_length(geom, project=project) == pytest.approx(
        ground_length(geom, _layer(), project=project))


def test_an_unconfigured_project_still_measures_ground_metres(project):
    """The blocker this guards: QGIS leaves a new project on ellipsoid 'NONE',
    even after the CRS is set. Trusting that turned every measurement back into
    map units -- 1.37x too long here -- while the UI promised ellipsoidal."""
    project.setEllipsoid("NONE")
    clear_cache()
    geom = _mercator_line(1000.0)
    ground = ground_length(geom, _layer(), project=project)

    assert ground == pytest.approx(geom.length() / SCALE, rel=0.01)
    assert ground < geom.length()


def test_measures_metres_is_false_only_when_measurement_really_is_planar(project):
    """It must answer "will this be ellipsoidal?", not "is the CRS linear?"."""
    from fiberq.utils.measure import measures_metres

    project.setEllipsoid("NONE")
    clear_cache()
    # A projected CRS with no project ellipsoid still resolves one from the CRS.
    assert measures_metres(_layer(), project=project) is True


def test_the_crs_ellipsoid_is_the_fallback(project):
    """EPSG:3857 names EPSG:7030; that is what the QGIS measure tool falls back to."""
    from fiberq.utils.measure import resolve_ellipsoid

    project.setEllipsoid("NONE")
    clear_cache()
    assert resolve_ellipsoid(
        QgsCoordinateReferenceSystem("EPSG:3857"), project) == "EPSG:7030"

    # An explicit project ellipsoid always wins over the CRS default.
    project.setEllipsoid("EPSG:7004")
    clear_cache()
    assert resolve_ellipsoid(
        QgsCoordinateReferenceSystem("EPSG:3857"), project) == "EPSG:7004"


def test_geographic_crs_returns_metres_not_degrees(project):
    """A layer in EPSG:4326 must not report a length of 0.01."""
    geom = QgsGeometry.fromPolylineXY(
        [QgsPointXY(LON, LAT), QgsPointXY(LON + 0.01, LAT)])
    metres = ground_length(geom, _layer("EPSG:4326"), project=project)
    assert 700 < metres < 900  # ~810 m at this latitude


def test_cache_is_keyed_on_crs_and_ellipsoid(project):
    """Changing the project ellipsoid must change the answer, not reuse a stale one."""
    geom = _mercator_line(1000.0)
    on_wgs84 = ground_length(geom, _layer(), project=project)
    project.setEllipsoid("EPSG:7004")  # Bessel 1841 -- a different figure
    clear_cache()
    assert ground_length(geom, _layer(), project=project) != pytest.approx(on_wgs84)


# ---------------------------------------------------------------------------
# No caller may regress to planar maths for a stored length
# ---------------------------------------------------------------------------

#: (module, function) pairs that write a metre value into a field or show one.
LENGTH_WRITERS = [
    ("fiberq/core/route_manager.py", 4),
    ("fiberq/core/cable_manager.py", 1),
    ("fiberq/core/slack_manager.py", 1),
    ("fiberq/tools/route_tool.py", 1),
    ("fiberq/tools/breakpoint_tool.py", 2),
    ("fiberq/tools/branch_tool.py", 1),
    ("fiberq/dialogs/schematic_dialog.py", 1),
    ("fiberq/addons/reserve_hook.py", 1),
    ("fiberq/tools/pipe_tool.py", 1),
]

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("rel,count", LENGTH_WRITERS)
def test_length_writers_use_ground_length(rel, count):
    src = (REPO / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "ground_length"  # noqa: W503
    ]
    assert len(calls) == count, f"{rel} should call ground_length {count}x"
    assert "from ..utils.measure import ground_length" in src


def test_stored_length_fields_are_never_assigned_a_planar_length():
    """The regression itself: `duzina* = <something>.length()` must not come back."""
    offenders = []
    for path in (REPO / "fiberq").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not any(t.startswith("duzina") or "length" in t or "len" in t
                       for t in targets):
                continue
            for call in ast.walk(node.value):
                if (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)  # noqa: W503
                        and call.func.attr == "length"):  # noqa: W503
                    offenders.append(
                        f"{path.relative_to(REPO)}:{node.lineno} {targets}")
    # utils/geometry.py documents itself as map units and has no callers.
    offenders = [o for o in offenders if "utils/geometry.py" not in o]
    assert not offenders, "planar length assigned to a length variable: " + "; ".join(offenders)
