"""
Pytest configuration and fixtures for FiberQ plugin tests.

This module provides:
- Common fixtures for both unit and QGIS tests
- Plugin directory paths
- Mock objects for testing without full QGIS environment
"""
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Add plugin directory to path for imports
PLUGIN_DIR = Path(__file__).parent.parent / "fiberq"
if str(PLUGIN_DIR.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR.parent))


@pytest.fixture
def plugin_dir():
    """Return the plugin root directory path."""
    return PLUGIN_DIR


@pytest.fixture
def config_path(plugin_dir):
    """Return the path to config.ini."""
    return plugin_dir / "config.ini"


@pytest.fixture
def styles_dir(plugin_dir):
    """Return the path to styles directory."""
    return plugin_dir / "styles"


@pytest.fixture
def icons_dir(plugin_dir):
    """Return the path to icons directory."""
    return plugin_dir / "icons"


@pytest.fixture
def temp_config(tmp_path):
    """
    Create a temporary config.ini for testing.
    Returns path to the temporary config file.
    """
    config_content = """[postgis]
host = localhost
port = 5432
dbname = test_db
user = test_user
password = test_pass
schema = public
sslmode = disable

[web]
viewer_url = https://example.com/

[basemaps]
osm_url = https://tile.openstreetmap.org/{z}/{x}/{y}.png
"""
    config_file = tmp_path / "config.ini"
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def mock_iface():
    """
    Create a minimal mock QgisInterface for unit tests.
    For full QGIS tests, use qgis_iface from pytest-qgis.
    """
    iface = mock.MagicMock()

    # Mock main window
    main_window = mock.MagicMock()
    iface.mainWindow.return_value = main_window

    # Mock map canvas
    canvas = mock.MagicMock()
    canvas.mapSettings.return_value.destinationCrs.return_value.authid.return_value = "EPSG:4326"
    iface.mapCanvas.return_value = canvas

    # Mock message bar
    message_bar = mock.MagicMock()
    iface.messageBar.return_value = message_bar

    # Mock layer tree view
    iface.layerTreeView.return_value = mock.MagicMock()

    # Mock for addToolBar
    toolbar = mock.MagicMock()
    iface.addToolBar.return_value = toolbar

    return iface


@pytest.fixture
def sample_line_coords():
    """Sample coordinates for a polyline (for geometry tests)."""
    return [
        (0.0, 0.0),
        (100.0, 0.0),
        (100.0, 100.0),
        (200.0, 100.0),
    ]


@pytest.fixture
def sample_point_coords():
    """Sample coordinates for points (for geometry tests)."""
    return [
        (50.0, 0.0),
        (100.0, 50.0),
        (150.0, 100.0),
    ]


# Markers for test categorization
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (no QGIS required)")
    config.addinivalue_line("markers", "qgis: Tests requiring QGIS API")
    config.addinivalue_line("markers", "slow: Slow running tests")
