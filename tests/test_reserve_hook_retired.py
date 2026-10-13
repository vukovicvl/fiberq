"""ReserveHook is retired, and nothing wires it back in.

WP4 item U12, unclaimed. ``addons/reserve_hook.py`` watched any point layer
whose name starts ``opticke_rezerve`` and re-totalled cables from that layer's
commit signals. Measured on 3.22.16, 3.44.15 and 4.2.3 before it went:

* On a pre-1.0 project (``kabl_layer_id`` / ``kabl_fid``) its handlers
  returned early, or read field index -1 and swallowed the ``KeyError`` at
  debug level, so it never changed a cable. What it did do was replace the
  slack layer's renderer with one that draws only ``tip`` = ``zavrsna`` /
  ``prolazna``, so every slack FiberQ 1.x writes (``Terminal``, ``Mid span``)
  disappeared from the map.
* On an ``Opticke_rezerve`` layer whose link columns had been renamed to the
  English ``cable_layer_id`` / ``cable_fid`` (no release writes that pair, so
  only by hand), every slack commit re-totalled every cable holding a slack.
  It looked each cable up with the expression ``id=<fid>``, which matches
  nothing (``$id`` is the feature id), swallowed the ``StopIteration`` and
  wrote ``total_len_m = slack_m``: a 100 m cable with 30 m of slack read
  30 / 30 instead of 30 / 130, even when the slack placed was on another cable.
  Its ``slack_m`` after an attribute-table edit was right; the total never was.
* ``initGui`` created it and nothing ever disconnected it, so every plugin
  reload added one more copy, and each copy rewrote the cables again.

``SlackManager.recompute_slack_for_cable`` is the one implementation, reached
from Place slack, Generate terminal slacks and Delete selected.

The module is deleted, so these tests are static: nothing in ``fiberq/`` may
import it, define it again, or keep the attribute ``initGui`` held it on.
"""
import ast
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO / "fiberq"

#: Every spelling that would bring it back: the module, the class, and the
#: plugin attribute ``initGui`` kept it on.
RETIRED = frozenset({"reserve_hook", "ReserveHook", "_reserve_hook"})


def _names(node):
    """The identifiers, and exact strings, a node carries."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or ""] + [alias.name for alias in node.names]
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        # An ``__all__`` entry, import_module("fiberq.addons.reserve_hook"),
        # getattr(plugin, "_reserve_hook"). Prose in a docstring never equals
        # one of these names, so a sentence about the history is not a hit.
        return [node.value]
    return []


def test_the_module_is_gone(qgis_app):
    assert importlib.util.find_spec("fiberq.addons.reserve_hook") is None


def test_nothing_in_the_plugin_imports_or_names_it():
    scanned = sorted(PACKAGE.rglob("*.py"))
    # The scan proves nothing if it read nothing: it must see the plugin itself.
    assert PACKAGE / "main_plugin.py" in scanned and len(scanned) > 50, len(scanned)
    offenders = []
    for path in scanned:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for name in _names(node):
                if name.rsplit(".", 1)[-1] in RETIRED:
                    offenders.append(f"{path.relative_to(REPO)}:{getattr(node, 'lineno', '?')} {name}")
    assert not offenders, (
        "ReserveHook is retired (WP4 U12): it hid every modern slack on an old "
        "project and wrote total_len_m = slack_m on a hand-migrated one. "
        "SlackManager.recompute_slack_for_cable is the one implementation. "
        f"Found: {offenders}")
