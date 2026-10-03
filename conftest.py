"""Shared pytest fixtures for FiberQ.

Lives at the repo root so pytest makes the root importable (`import fiberq`
resolves to the fiberq/ package). pytest-qgis bootstraps a headless
QgsApplication automatically and exposes fixtures such as `qgis_app` and
`qgis_iface` to every test. Add project-wide fixtures here as the suite grows
(WP5).

Note: this file is loaded very early, so it avoids importing `fiberq` at module
top level; fixtures resolve paths from __file__ instead.
"""
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope="session")
def fiberq_dir():
    """Absolute path to the fiberq/ plugin package."""
    return os.path.join(REPO_ROOT, "fiberq")


@pytest.fixture(scope="session")
def city_xs_dataset(qgis_app, tmp_path_factory):
    """The WP4 benchmark's XS city project, generated once for the whole session.

    Two test modules want it (`test_city_fixture.py`, `test_bench_harness.py`)
    and it costs a second and a half, so it is built once. Nothing is committed:
    `tests/fixtures/` holds the generator, not its output -- `.gitignore` matches
    neither `*.gpkg` nor `*.qgz`, so a generated dataset would sit in
    `git status` waiting to be added.

    Returns the generator's `meta` dict, which carries the paths (`gpkg`, `qgz`,
    `manifest`), the row digest and the per-layer counts. Deliberately no
    QgsProject: a project that outlived the test which read it would be
    destroyed during interpreter teardown, and that is a reliable segfault on
    QGIS 4.0. Each test reads the project into a local one instead.
    """
    import sys

    from qgis.core import QgsMapLayer
    if not hasattr(QgsMapLayer, "setId"):
        pytest.skip(
            "QgsMapLayer.setId() arrived in QGIS 3.36 and the benchmark fixture "
            "pins every layer id with it. Generating the dataset therefore needs "
            "3.36+; reading one does not -- a project written on 3.44 reads back "
            "on 3.22 with all 24 ids and the project entries intact (measured). "
            "CI runs 3.44 and 4.0, so the pinned digest is still gated.")

    fixtures = os.path.join(REPO_ROOT, "tests", "fixtures")
    if fixtures not in sys.path:
        sys.path.insert(0, fixtures)
    import make_city_project

    folder = tmp_path_factory.mktemp("city_xs")
    return make_city_project.generate(size="XS", out=str(folder / "city_XS.gpkg"))


@pytest.fixture(scope="session")
def sample_project_path():
    """Path to the demo GeoPackage fixture (added in Phase 0 / WP6).

    Tests that need a real project skip cleanly until the fixture exists, so
    the suite stays green before the demo dataset lands.
    """
    path = os.path.join(REPO_ROOT, "tests", "fixtures", "sample_project.gpkg")
    if not os.path.exists(path):
        pytest.skip("tests/fixtures/sample_project.gpkg not present yet")
    return path
