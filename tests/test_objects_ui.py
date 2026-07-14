"""Regression: the Objects draw tools (3pt / N / ortho / digitize) crashed with
ImportError because objects_ui imported the tool classes from ..main_plugin,
where they no longer live after the monolith split. They must resolve from the
tools package (and the layer helpers from core.layer_manager), and objects_ui
must not import them from main_plugin any more."""
import inspect


def test_object_tools_importable_from_tools_package(qgis_app):
    from fiberq.tools import (
        DrawObject3ptTool,
        DrawObjectNTool,
        DrawObjectOrthoTool,
        ObjectPropertiesDialog,
    )
    assert all([DrawObject3ptTool, DrawObjectNTool, DrawObjectOrthoTool, ObjectPropertiesDialog])


def test_objects_layer_helpers_importable(qgis_app):
    from fiberq.core.layer_manager import _ensure_objects_layer, _stylize_objects_layer
    assert _ensure_objects_layer and _stylize_objects_layer


def test_objects_ui_has_no_stale_main_plugin_imports(qgis_app):
    """Guards the actual fix: the object-draw activations must not import their
    tool classes from ..main_plugin (that raised ImportError at click time)."""
    import fiberq.ui.objects_ui as objects_ui
    src = inspect.getsource(objects_ui)
    assert "from ..main_plugin import DrawObject" not in src
    assert "from ..main_plugin import ObjectPropertiesDialog" not in src
