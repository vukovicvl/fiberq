"""
QGIS integration tests for plugin loading.
These tests require QGIS and pytest-qgis.

Run with: pytest tests/qgis/ --qgis_disable_gui
"""
import pytest

# Skip all tests in this module if QGIS is not available
pytest.importorskip("qgis.core")


class TestPluginInitialization:
    """Tests for FiberQPlugin initialization."""

    def test_plugin_class_imports(self):
        """FiberQPlugin can be imported."""
        from fiberq.main_plugin import FiberQPlugin
        assert FiberQPlugin is not None

    def test_plugin_instantiates(self, qgis_iface):
        """Plugin instantiates without errors."""
        from fiberq.main_plugin import FiberQPlugin

        plugin = FiberQPlugin(qgis_iface)
        assert plugin is not None
        assert plugin.iface == qgis_iface

    def test_plugin_has_initgui_method(self, qgis_iface):
        """Plugin has initGui method."""
        from fiberq.main_plugin import FiberQPlugin

        plugin = FiberQPlugin(qgis_iface)
        assert hasattr(plugin, "initGui")
        assert callable(plugin.initGui)

    def test_plugin_has_unload_method(self, qgis_iface):
        """Plugin has unload method."""
        from fiberq.main_plugin import FiberQPlugin

        plugin = FiberQPlugin(qgis_iface)
        assert hasattr(plugin, "unload")
        assert callable(plugin.unload)


class TestClassFactory:
    """Tests for classFactory entry point."""

    def test_class_factory_exists(self):
        """classFactory function exists in __init__.py."""
        from fiberq import classFactory
        assert classFactory is not None
        assert callable(classFactory)

    def test_class_factory_returns_plugin(self, qgis_iface):
        """classFactory returns FiberQPlugin instance."""
        from fiberq import classFactory
        from fiberq.main_plugin import FiberQPlugin

        plugin = classFactory(qgis_iface)
        assert isinstance(plugin, FiberQPlugin)


class TestAddonImports:
    """Tests for addon module imports."""

    def test_fiber_break_imports(self):
        """FiberBreakTool can be imported."""
        from fiberq.addons.fiber_break import FiberBreakTool
        assert FiberBreakTool is not None

    def test_reserve_hook_imports(self):
        """ReserveHook can be imported."""
        from fiberq.addons.reserve_hook import ReserveHook
        assert ReserveHook is not None

    def test_publish_pg_imports(self):
        """publish_pg module can be imported."""
        from fiberq.addons.publish_pg import PublishDialog, open_publish_dialog
        assert PublishDialog is not None
        assert open_publish_dialog is not None

    def test_hotkeys_imports(self):
        """hotkeys module can be imported."""
        from fiberq.addons.hotkeys import show_hotkeys_help
        assert show_hotkeys_help is not None

    def test_fiberq_preview_imports(self):
        """fiberq_preview module can be imported."""
        from fiberq.addons.fiberq_preview import FiberQPreviewDockWidget
        assert FiberQPreviewDockWidget is not None
