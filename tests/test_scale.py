"""Validation must not degrade superlinearly as a design grows.

Every real project used to test v1.4.0 had under 60 features. A design with
25,000 is ordinary in FTTH, and the topology rules are the ones that could
quietly become quadratic -- A3 compares every element against every linear
feature, and only the shared QgsSpatialIndex keeps that linear.

This does not assert wall-clock seconds, which would be flaky on shared CI.
It compares the time at two sizes: quadratic work would grow ~16x when the
feature count quadruples, so a ceiling well above linear still catches the
regression that matters while tolerating a noisy machine.
"""
import pathlib
import sys
import time

import pytest

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
if str(FIXTURES) not in sys.path:
    sys.path.insert(0, str(FIXTURES))

from make_scale_project import build, build_project  # noqa: E402

SMALL, LARGE = 150, 600      # street segments; x4, so ~750 and ~3000 features


def _run(tmp_path, n, name):
    from qgis.core import QgsProject

    from fiberq.core.validation_manager import run_validation

    gpkg = str(tmp_path / f"{name}.gpkg")
    qgz = str(tmp_path / f"{name}.qgz")
    _path, total = build(gpkg, n)
    build_project(gpkg, qgz)

    project = QgsProject()
    assert project.read(qgz)

    start = time.perf_counter()
    result = run_validation(project=project, plugin_version="test")
    return time.perf_counter() - start, result, total


def test_a_correct_design_stays_clean_at_scale(qgis_app, tmp_path):
    """The generated grid is fully connected, so any finding is a real defect --
    which makes this a correctness test that happens to run at volume."""
    _elapsed, result, total = _run(tmp_path, SMALL, "clean")
    assert total > 700
    assert result.rule_errors == []
    assert result.issues == [], [(i.rule_id, i.message) for i in result.issues[:5]]


@pytest.mark.slow
def test_validation_does_not_go_quadratic(qgis_app, tmp_path):
    small, _r1, n1 = _run(tmp_path, SMALL, "small")
    large, _r2, n2 = _run(tmp_path, LARGE, "large")

    assert n2 > n1 * 3            # the fixture really did grow
    if small < 0.05:              # too fast to time meaningfully
        pytest.skip(f"baseline {small:.3f}s is below timer resolution")

    ratio = large / small
    assert ratio < 10.0, (
        f"{n1} features took {small:.2f}s, {n2} took {large:.2f}s "
        f"(ratio {ratio:.1f}); quadratic growth would be ~16x")
