"""Smoke tests - the first safety net for Phase 0 CI.

They prove the harness works end to end: QGIS bindings load (via pytest-qgis),
the `fiberq` package imports, and the declared version is internally consistent.
Real unit/integration coverage (WP5) builds on top of this.
"""
import os

import fiberq


def _metadata_version():
    meta = os.path.join(os.path.dirname(fiberq.__file__), "metadata.txt")
    with open(meta, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("version="):
                return line.split("=", 1)[1].strip()
    return None


def test_package_imports():
    assert fiberq.__version__


def test_version_matches_metadata():
    """metadata.txt and __init__.py must agree (guards the release checklist)."""
    assert _metadata_version() == fiberq.__version__


def test_qgis_bindings_available(qgis_app):
    """pytest-qgis provides qgis_app; a Qgis-dependent module must import and
    expose its expected constants."""
    from fiberq.utils import constants

    assert len(constants.ROUTE_TYPE_OPTIONS) == 3
