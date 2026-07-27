"""Regression: Place Joint Closure / Split route created an empty "Poles" layer.

Both activators called init_layer() -> ensure_poles_layer() -> project.addMapLayer(),
so an empty "Poles" entry appeared in the Layers panel as soon as the user clicked
the toolbar button, before placing anything and regardless of whether anything was
ever placed.

Neither tool needs it. BreakpointTool.__init__(canvas, iface, plugin) never receives
a layer at all; ExtensionTool was passed one but only ever used it for a validity
guard -- it writes exclusively to the Joint Closures layer, which it resolves or
creates from the project on each click.

FiberQPlugin is not instantiable in the test harness (it needs a live iface and the
full initGui chain), so the activator behaviour is guarded at source level, matching
the precedent in test_objects_ui.py.
"""
import ast
import inspect
import textwrap

from qgis.core import QgsProject
from qgis.gui import QgsMapCanvas


def _called_names(func):
    """Names of everything actually *called* in ``func``.

    Parsed from the AST rather than grepped from the source text, so prose in a
    docstring explaining what the function no longer calls cannot trip the
    assertions below.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                names.add(target.attr)
            elif isinstance(target, ast.Name):
                names.add(target.id)
    return names


def test_extension_tool_constructs_without_a_layer(qgis_app):
    """The tool must be usable with no layer argument at all."""
    from fiberq.tools.extension_tool import ExtensionTool

    canvas = QgsMapCanvas()
    tool = ExtensionTool(canvas)
    assert tool is not None
    # The layer is no longer stored as an instance attribute. (Do not use
    # hasattr: the QgsMapTool C++ base exposes an unrelated layer() method, so
    # hasattr is True regardless.)
    assert "layer" not in vars(tool)


def test_extension_tool_still_accepts_a_layer_argument(qgis_app):
    """The parameter is kept (and ignored) so out-of-tree callers keep working."""
    from fiberq.tools.extension_tool import ExtensionTool

    canvas = QgsMapCanvas()
    tool = ExtensionTool(canvas, None)
    assert tool is not None

    sig = inspect.signature(ExtensionTool.__init__)
    assert sig.parameters["layer"].default is None, "layer must be optional"


def test_constructing_the_tool_creates_no_layers(qgis_app):
    """The heart of the bug: activating the tool must not add anything to the project."""
    from fiberq.tools.extension_tool import ExtensionTool

    project = QgsProject.instance()
    project.removeAllMapLayers()
    before = len(project.mapLayers())

    ExtensionTool(QgsMapCanvas())

    assert len(project.mapLayers()) == before
    assert project.mapLayersByName("Poles") == []
    assert project.mapLayersByName("Stubovi") == []


def test_activators_do_not_create_the_poles_layer(qgis_app):
    """Guards the actual fix in main_plugin.py.

    Both activators must not call init_layer(); ExtensionTool must be constructed
    without self.layer. A source check is used because FiberQPlugin cannot be
    instantiated here (see module docstring).
    """
    import fiberq.main_plugin as mp

    for name in ("activate_extension_tool", "activate_breakpoint_tool"):
        called = _called_names(getattr(mp.FiberQPlugin, name))
        assert "init_layer" not in called, (
            f"{name} must not call init_layer() -- that is what created the stray "
            f"empty Poles layer"
        )

    ext_src = inspect.getsource(mp.FiberQPlugin.activate_extension_tool)
    assert "ExtensionTool(self.iface.mapCanvas())" in ext_src, (
        "ExtensionTool must be constructed without the Poles layer"
    )
    # Behaviour that must survive the change.
    assert "self.extension_tool.plugin = self" in ext_src, "undo wiring must be kept"
    assert "_record_cmd('place_joint_closure')" in ext_src, "repeat-command must be kept"

    bp_src = inspect.getsource(mp.FiberQPlugin.activate_breakpoint_tool)
    assert "_record_cmd('split_route')" in bp_src, "repeat-command must be kept"


def test_place_pole_still_creates_the_poles_layer(qgis_app):
    """The Poles layer must still be created where it is genuinely wanted."""
    import fiberq.main_plugin as mp

    assert "init_layer" in _called_names(mp.FiberQPlugin.activate_point_tool), (
        "Place Pole legitimately creates the Poles layer -- do not strip this one"
    )


def test_extension_tool_has_no_dead_layer_references(qgis_app):
    """The guard and its now-orphaned sip import must both be gone.

    Deleting the guard without the import leaves flake8 F401, which fails the
    plugins.qgis.org scan gate (make lint must stay 0/0).
    """
    import fiberq.tools.extension_tool as et

    src = inspect.getsource(et)
    assert "self.layer" not in src
    assert "from qgis.PyQt import sip" not in src
    assert "Layer not found or invalid!" not in src
