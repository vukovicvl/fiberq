"""
Unit tests for utility functions.
These tests do not require QGIS.
"""
import re
import pytest


def _sanitize_table_name(name: str) -> str:
    """
    Copy of sanitize function from publish_pg.py for testing.
    In production, import from the module.
    """
    base = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip())
    base = base.strip("_") or "layer_export"
    if base[0].isdigit():
        base = "_" + base
    return base.lower()


class TestSanitizeTableName:
    """Tests for table name sanitization."""

    def test_simple_name(self):
        """Simple alphanumeric name passes through."""
        assert _sanitize_table_name("my_table") == "my_table"

    def test_spaces_replaced(self):
        """Spaces are replaced with underscores."""
        assert _sanitize_table_name("my table name") == "my_table_name"

    def test_special_chars_replaced(self):
        """Special characters are replaced with underscores."""
        assert _sanitize_table_name("table@name#123") == "table_name_123"

    def test_leading_digit_prefixed(self):
        """Names starting with digit get underscore prefix."""
        assert _sanitize_table_name("123table") == "_123table"

    def test_uppercase_lowercased(self):
        """Uppercase is converted to lowercase."""
        assert _sanitize_table_name("MyTable") == "mytable"

    def test_empty_string_default(self):
        """Empty string returns default name."""
        assert _sanitize_table_name("") == "layer_export"

    def test_none_default(self):
        """None returns default name."""
        assert _sanitize_table_name(None) == "layer_export"

    def test_only_special_chars(self):
        """String with only special chars returns default."""
        assert _sanitize_table_name("@#$%") == "layer_export"

    def test_leading_trailing_underscores_stripped(self):
        """Leading/trailing underscores are stripped."""
        assert _sanitize_table_name("__table__") == "table"

    def test_cyrillic_replaced(self):
        """Cyrillic characters are replaced."""
        result = _sanitize_table_name("таблица")
        assert result == "layer_export"  # All chars replaced, falls back to default

    def test_mixed_valid_cyrillic(self):
        """Mixed valid and cyrillic characters."""
        # "table_" + "_" (replacement for таблица) + "_123" = "table___123"
        result = _sanitize_table_name("table_таблица_123")
        assert result == "table___123"


class TestResourcePaths:
    """Tests for resource file existence."""

    def test_icons_directory_exists(self, icons_dir):
        """Icons directory exists."""
        assert icons_dir.exists(), f"Icons directory not found: {icons_dir}"

    def test_styles_directory_exists(self, styles_dir):
        """Styles directory exists."""
        assert styles_dir.exists(), f"Styles directory not found: {styles_dir}"

    def test_has_svg_icons(self, icons_dir):
        """Plugin has SVG icons."""
        svg_files = list(icons_dir.glob("*.svg"))
        assert len(svg_files) > 0, "No SVG icons found"

    def test_has_qml_styles(self, styles_dir):
        """Plugin has QML style files."""
        qml_files = list(styles_dir.glob("*.qml"))
        assert len(qml_files) > 0, "No QML style files found"

    def test_fiber_break_style_exists(self, styles_dir):
        """Fiber_break.qml style file exists."""
        style_file = styles_dir / "Fiber_break.qml"
        assert style_file.exists(), f"Fiber_break.qml not found at {style_file}"


class TestPluginMetadata:
    """Tests for plugin metadata."""

    def test_metadata_exists(self, plugin_dir):
        """metadata.txt exists."""
        metadata = plugin_dir / "metadata.txt"
        assert metadata.exists()

    def test_metadata_has_required_fields(self, plugin_dir):
        """metadata.txt has required fields."""
        import configparser

        metadata = plugin_dir / "metadata.txt"
        cp = configparser.ConfigParser()
        cp.read(metadata)

        required = ["name", "version", "qgisMinimumVersion", "author", "email"]
        general = cp["general"]

        for field in required:
            assert field in general, f"Missing metadata field: {field}"

    def test_class_name_is_fiberq(self, plugin_dir):
        """Class name in metadata is FiberQPlugin."""
        import configparser

        metadata = plugin_dir / "metadata.txt"
        cp = configparser.ConfigParser()
        cp.read(metadata)

        class_name = cp["general"].get("class_name", "")
        assert class_name == "FiberQPlugin", f"Expected FiberQPlugin, got {class_name}"
