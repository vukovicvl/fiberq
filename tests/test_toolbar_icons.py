"""No two FiberQ actions may share an icon file.

Two buttons with the same glyph are indistinguishable on a toolbar -- the user
cannot tell them apart and reasonably reads one as a duplicate. It happened in
v1.4.0: the new "Validate project" action was given ic_health.svg, the same file
as the existing "Check (health check)", so the toolbar showed the same button
twice for two different features.

Source-level, because building FiberQPlugin needs a live iface and the whole
initGui chain (same approach as tests/test_validation_panel.py).
"""
import pathlib
import re

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "fiberq"
ICONS = PACKAGE / "icons"
MAIN = PACKAGE / "main_plugin.py"

_SET_ICON = re.compile(
    r"self\.(action_\w+)\.setIcon\(\s*_load_icon\(\s*['\"]([^'\"]+)['\"]")


def _icon_by_action():
    """``{action attribute: icon filename}`` for every _load_icon assignment."""
    out = {}
    for action, icon in _SET_ICON.findall(MAIN.read_text(encoding="utf-8")):
        out[action] = icon
    return out


def test_no_two_actions_share_an_icon():
    by_icon = {}
    for action, icon in _icon_by_action().items():
        by_icon.setdefault(icon, []).append(action)
    shared = {icon: sorted(actions) for icon, actions in by_icon.items()
              if len(actions) > 1}
    assert not shared, f"actions sharing one icon: {shared}"


def test_every_named_icon_exists():
    """A missing file is a blank button, and _load_icon swallows the error."""
    on_disk = {p.name for p in ICONS.glob("*.svg")}
    missing = {action: icon for action, icon in _icon_by_action().items()
               if icon not in on_disk}
    assert not missing, f"named in main_plugin.py but not in fiberq/icons/: {missing}"


def test_the_scan_found_the_actions():
    """Guards the two tests above from passing on an empty match."""
    found = _icon_by_action()
    assert len(found) >= 5, found
    assert found.get("action_validate") == "ic_validate.svg"
    assert found.get("action_health_check") == "ic_health.svg"


def test_shipped_icons_are_valid_svg():
    """A malformed SVG renders as nothing; Qt will not tell you."""
    bad = []
    for path in sorted(ICONS.glob("*.svg")):
        try:
            text = path.read_text(encoding="utf-8")
            if "<svg" not in text or "</svg>" not in text:
                bad.append(path.name)
        except UnicodeDecodeError:
            bad.append(path.name)
    assert not bad, bad
