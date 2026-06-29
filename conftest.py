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
def sample_project_path():
    """Path to the demo GeoPackage fixture (added in Phase 0 / WP6).

    Tests that need a real project skip cleanly until the fixture exists, so
    the suite stays green before the demo dataset lands.
    """
    path = os.path.join(REPO_ROOT, "tests", "fixtures", "sample_project.gpkg")
    if not os.path.exists(path):
        pytest.skip("tests/fixtures/sample_project.gpkg not present yet")
    return path
