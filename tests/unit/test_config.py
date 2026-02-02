"""
Unit tests for configuration parsing.
These tests do not require QGIS.
"""
import os
import pytest
import configparser
from pathlib import Path


class TestConfigParsing:
    """Tests for config.ini parsing."""

    def test_config_file_exists(self, config_path):
        """Config file exists in plugin directory."""
        assert config_path.exists(), f"config.ini not found at {config_path}"

    def test_config_has_postgis_section(self, config_path):
        """Config has [postgis] section."""
        cp = configparser.ConfigParser()
        cp.read(config_path)
        assert "postgis" in cp, "Missing [postgis] section"

    def test_config_has_web_section(self, config_path):
        """Config has [web] section."""
        cp = configparser.ConfigParser()
        cp.read(config_path)
        assert "web" in cp, "Missing [web] section"

    def test_config_has_basemaps_section(self, config_path):
        """Config has [basemaps] section."""
        cp = configparser.ConfigParser()
        cp.read(config_path)
        assert "basemaps" in cp, "Missing [basemaps] section"

    def test_postgis_required_keys(self, config_path):
        """PostGIS section has all required keys."""
        cp = configparser.ConfigParser()
        cp.read(config_path)

        required_keys = ["host", "port", "dbname", "schema"]
        postgis = cp["postgis"]

        for key in required_keys:
            assert key in postgis, f"Missing key: {key}"

    def test_postgis_port_is_numeric(self, config_path):
        """PostGIS port should be a valid number."""
        cp = configparser.ConfigParser()
        cp.read(config_path)

        port = cp["postgis"].get("port", "5432")
        assert port.isdigit(), f"Port should be numeric, got: {port}"

    def test_web_viewer_url(self, config_path):
        """Web section has viewer_url."""
        cp = configparser.ConfigParser()
        cp.read(config_path)

        assert "viewer_url" in cp["web"]

    def test_basemaps_osm_url(self, config_path):
        """Basemaps section has osm_url."""
        cp = configparser.ConfigParser()
        cp.read(config_path)

        osm_url = cp["basemaps"].get("osm_url", "")
        assert "openstreetmap" in osm_url.lower() or osm_url == ""


class TestTempConfig:
    """Tests using temporary config file."""

    def test_temp_config_creation(self, temp_config):
        """Temporary config is created correctly."""
        assert temp_config.exists()

        cp = configparser.ConfigParser()
        cp.read(temp_config)

        assert cp["postgis"]["host"] == "localhost"
        assert cp["postgis"]["dbname"] == "test_db"
