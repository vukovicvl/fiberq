"""The health check is gone, and stays gone (WP4 item U3, unclaimed).

"Check (health check)" pushed one line to the message bar -- is there a layer
called Route, Poles or Manholes, of the right geometry type -- and then ran
Route correction. v1.6.0 removes it rather than rebuilding it on
``run_validation``. Validate project is the data-quality audit, and Route
correction stays on the Routing menu. The one-line layer summary itself has no
replacement: Validate project reports a missing FiberQ layer only when the
project has none at all (rule C2), not a missing Route, Poles or Manholes
layer or one of the wrong geometry type. That loss was accepted when the
removal was planned.

Package-wide rather than ``main_plugin.py`` alone: the toolbar groups live in
``fiberq/ui/``, and a re-introduction could come through any of them.
Pure AST: no QGIS, milliseconds.
"""
import ast
import pathlib

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "fiberq"

#: The identifiers the feature lived under.
NAMES = {"run_health_check", "action_health_check"}
#: The action's label. It was also a key of the two deprecated phrase maps
#: (utils/helpers.py, utils/legacy_bridge.py), which only ever translated it.
LABEL = "Check (health check)"
ICON = "ic_health.svg"


def _modules():
    paths = sorted(PACKAGE.rglob("*.py"))
    # The scans prove nothing if they read nothing: they must see the plugin itself.
    assert PACKAGE / "main_plugin.py" in paths and len(paths) > 50, len(paths)
    for path in paths:
        yield path.relative_to(PACKAGE.parent), ast.parse(path.read_text(encoding="utf-8"))


def _identifier(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def test_no_health_check_code():
    found = [f"{rel}:{node.lineno} {_identifier(node)}"
             for rel, tree in _modules() for node in ast.walk(tree)
             if _identifier(node) in NAMES]
    assert not found, found


def _forbidden_string(node):
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return False
    return ICON in node.value or node.value == LABEL or node.value in NAMES


def test_no_health_check_label_or_icon():
    """Strings too: ``getattr(self, "run_health_check")`` and the icon name."""
    found = [f"{rel}:{node.lineno} {node.value!r}"
             for rel, tree in _modules() for node in ast.walk(tree)
             if _forbidden_string(node)]
    assert not found, found


def test_the_icon_is_not_shipped():
    assert not (PACKAGE / "icons" / ICON).exists()


def _connects(tree, method):
    """Whether any ``<signal>.connect(<something>.<method>)`` call names ``method``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "connect" or not node.args:
            continue
        if isinstance(node.args[0], ast.Attribute) and node.args[0].attr == method:
            return True
    return False


def test_route_correction_stays():
    """The health check ran Route correction; removing it must not take that too."""
    main = ast.parse((PACKAGE / "main_plugin.py").read_text(encoding="utf-8"))
    methods = {node.name for node in ast.walk(main) if isinstance(node, ast.FunctionDef)}
    assert "check_consistency" in methods
    routing = ast.parse((PACKAGE / "ui" / "routing_ui.py").read_text(encoding="utf-8"))
    assert _connects(routing, "check_consistency")
