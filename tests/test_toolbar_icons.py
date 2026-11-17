"""Buttons the user sees side by side must not look the same.

Two buttons with the same glyph are indistinguishable on a toolbar -- the user
cannot tell them apart and reasonably reads one as a duplicate. It happened in
v1.4.0: the new "Validate project" action was given ic_health.svg, the icon of
the existing "Check (health check)" (removed since, WP4 U3), so the toolbar
showed the same button twice for two different features.

The first version of this test read ``self.action_x.setIcon(_load_icon(...))``
out of main_plugin.py with a regular expression. Most buttons are built as
``QAction(_load_icon(...), ...)``, from an icon held in a variable, or in a
fiberq/ui/ group, so it saw 5 of the toolbar's 37 icon buttons and passed while
"Import picture" and "Clear picture", and "Selection" and "Change element
type", showed one icon each. A list of call shapes is how that blind spot
happened, so this version does not read the source at all: it builds the
toolbars in a child process and reads back what Qt draws. An icon is
identified by its pixels, so a renamed copy of a file is still the same icon,
and two different files that look nearly the same are caught too: at 16 px at
least ``DISTINCT`` of the pixels either icon inks must differ.

Side by side means: the top level of each FiberQ toolbar, each drop-down menu,
and Plugins > FiberQ. A group button may show the icon of an entry in its own
menu, and the Quick toolbar repeats main-toolbar commands with their icons: one
command shown in two places is consistency, not a duplicate. A drop-down is
named by its group button's icon file, so the allowances below hold in any
interface language.

Why a subprocess: initGui() leaves toolbars, translators and project hooks
behind, which in-process would reach every later test (the same reason as
tests/test_schematic_lifecycle.py). The child is tests/support/toolbar_driver.py,
with the stand-in for QGIS's iface that both files use (tests/support/fake_iface.py).
"""
import ast
import os
import pathlib
import re
from itertools import combinations

import pytest

from support.child import TOOLBAR_DRIVER, run_driver

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = pathlib.Path(REPO_ROOT) / "fiberq"
ICONS = PACKAGE / "icons"

#: The share of inked pixels (alpha above 64 in either icon) that must differ
#: (any RGBA channel by more than 64) between two icons side by side, at 16 px.
#: Measured on 3.22, 3.44 and 4.2: genuinely different neighbours sit at 15 % and
#: up, and the near-twins this exists for at 3-6 %.
DISTINCT = 0.10

#: Drop-down entries that still share an icon, by (drop-down, icon file). Each
#: needs a glyph of its own, which is new artwork, so they are carried here
#: rather than failing the build. The list may only shrink: see the test below.
KNOWN_SHARED_IN_MENUS = {
    ("menu:ic_selection.svg", "ic_selection.svg"): "Clear selection shows Smart selection's icon",
    ("menu:ic_slack_midspan.svg", "ic_slack_midspan.svg"): "Place terminal slack shows the mid span glyph",
    ("menu:ic_export_features.svg", "ic_export_features.svg"): "Export all shows Export selected's icon",
}

#: Neighbours drawn differently, but too close to tell apart at 16 px, by
#: (container, the two icon files). Same rule: new artwork removes an entry.
KNOWN_NEAR_TWINS = {
    ("toolbar", frozenset({"ic_service_area.svg", "ic_draw_service_area.svg"})):
        "Create Service Area and Draw Service Area Manually differ by a few pixels",
}

#: Entries that draw no icon by design, counted per container: the interface
#: language button on the toolbar, and three text-only entries of Plugins >
#: FiberQ (Recalculate lengths, Export and Import interchange bundle). Counted,
#: not named, so the rule holds in any interface language.
TEXT_ONLY = {"toolbar": 1, "plugins": 3}

#: The drop-downs the toolbar is built with, by group icon file.
MENUS = {"menu:ic_laying_cable.svg", "menu:ic_cable_underground.svg", "menu:ic_aerial_backbone.svg",
         "menu:ic_routing.svg", "menu:ic_place_elements.svg", "menu:ic_ducting.svg",
         "menu:ic_selection.svg", "menu:ic_slack_midspan.svg", "menu:ic_drawing.svg",
         "menu:ic_drawing_object.svg", "menu:ic_export_features.svg"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build both toolbars once in a child process and name every container."""
    code, result, output = run_driver(tmp_path_factory.mktemp("toolbar_icons"), TOOLBAR_DRIVER)
    assert code == 0 and result is not None, f"returncode {code}\n{output}"
    names = {}
    for name, drawing in result["files"].items():
        if drawing:
            names.setdefault(drawing[0], []).append(name)
    result["names"] = names
    for container in result["containers"]:
        if "key" not in container:
            group = _files(result, container["group"])
            container["key"] = "menu:" + group[0] if group else "menu:" + container["title"]
    return result


def _files(built, drawing):
    """The icon files that draw ``drawing``, sorted; [] for none or for a drawing no file makes."""
    if not drawing:
        return []
    return sorted(built["names"].get(drawing[0], []))


def _inked_share_differing(a, b):
    """The share of pixels inked in either 16 px image that differ in any channel by more than 64."""
    inked = differing = 0
    for i in range(0, len(a), 8):
        pa = [int(a[i + k:i + k + 2], 16) for k in (0, 2, 4, 6)]
        pb = [int(b[i + k:i + k + 2], 16) for k in (0, 2, 4, 6)]
        if pa[3] > 64 or pb[3] > 64:
            inked += 1
            if max(abs(x - y) for x, y in zip(pa, pb)) > 64:
                differing += 1
    return differing / inked if inked else 0.0


def _shared(built):
    """``[(container key, title, icon files, labels)]`` for every icon shown twice in one container."""
    found = []
    for container in built["containers"]:
        by_icon = {}
        for label, drawing in container["rows"]:
            if drawing:
                by_icon.setdefault(drawing[0], []).append((label, drawing))
        for entries in by_icon.values():
            if len(entries) > 1:
                files = _files(built, entries[0][1]) or ["<not a fiberq/icons file>"]
                found.append((container["key"], container["title"], files, [label for label, _d in entries]))
    return found


def _near_twins(built):
    """``[(container key, title, files a, files b, labels, share)]`` for neighbours under DISTINCT."""
    found = []
    for container in built["containers"]:
        rows = [(label, drawing) for label, drawing in container["rows"] if drawing]
        for (la, da), (lb, db) in combinations(rows, 2):
            if da[0] == db[0]:
                continue  # the same icon: _shared's business
            share = _inked_share_differing(da[1], db[1])
            if share < DISTINCT:
                found.append((container["key"], container["title"], _files(built, da),
                              _files(built, db), [la, lb], round(share, 3)))
    return found


def _carried_share(key, files, labels):
    return len(labels) == 2 and any((key, name) in KNOWN_SHARED_IN_MENUS for name in files)


def _carried_twin(key, files_a, files_b):
    return any((key, frozenset({a, b})) in KNOWN_NEAR_TWINS for a in files_a for b in files_b)


def test_no_two_buttons_side_by_side_share_an_icon(built):
    problems = [f"{title}: {labels} all show {files}"
                for key, title, files, labels in _shared(built)
                if not _carried_share(key, files, labels)]
    assert not problems, "\n".join(problems)


def test_buttons_side_by_side_can_be_told_apart(built):
    problems = [f"{title}: {labels} ({a} vs {b}) differ in {share:.1%} of their inked pixels at 16 px"
                for key, title, a, b, labels, share in _near_twins(built)
                if not _carried_twin(key, a, b)]
    assert not problems, "\n".join(problems)


def test_the_allowances_only_shrink(built):
    """Each allowance covers the one pair it was written for. One that nobody
    needs any more is a hole waiting to be reused, so it must go."""
    shared = {(key, name) for key, _t, files, labels in _shared(built) for name in files if len(labels) == 2}
    stale = sorted(set(KNOWN_SHARED_IN_MENUS) - shared)
    assert not stale, f"no longer shared -- delete from KNOWN_SHARED_IN_MENUS: {stale}"
    twins = {(key, frozenset({x, y})) for key, _t, a, b, _l, _s in _near_twins(built) for x in a for y in b}
    gone = sorted(str(item) for item in set(KNOWN_NEAR_TWINS) - twins)
    assert not gone, f"no longer near twins -- delete from KNOWN_NEAR_TWINS: {gone}"


def test_the_build_saw_the_toolbars(built):
    """Guards the tests above from passing on a blank or half-built toolbar."""
    blank = sorted(name for name, drawing in built["files"].items() if not drawing)
    assert not blank, f"these icons render as nothing here, so nothing was compared: {blank}"
    assert built["modals"] == [], f"building the toolbars raised dialogs: {built['modals']}"

    by_key = {container["key"]: container for container in built["containers"]}
    top = [drawing for _label, drawing in by_key["toolbar"]["rows"] if drawing]
    assert len(top) >= 30, by_key["toolbar"]["rows"]
    shown = {name for drawing in top for name in _files(built, drawing)}
    # One of each way an icon reaches a button: setIcon(), QAction(_load_icon()),
    # an icon held in a variable, and a fiberq/ui/ group button.
    assert {"ic_validate.svg", "ic_import_picture.svg", "ic_relations.svg",
            "ic_selection.svg"} <= shown, sorted(shown)
    assert by_key.get("quick", {}).get("rows"), "the Quick toolbar was not built"

    empty = sorted(key for key in MENUS if not by_key.get(key, {}).get("rows"))
    assert not empty, f"these drop-downs are missing or empty: {empty}"
    routing = {name for _label, drawing in by_key["menu:ic_routing.svg"]["rows"] for name in _files(built, drawing)}
    # The health check ran Route correction; removing it (WP4 U3) kept the command here.
    assert "ic_route_correction.svg" in routing, sorted(routing)


def test_every_button_draws_an_icon(built):
    """An icon file that does not resolve draws nothing, and two such entries side
    by side look the same: blank. A name built at run time -- the element icons
    are f'ic_place_{slug}.svg' -- can only be checked this way. Every entry of
    every drop-down and of the Quick toolbar draws an icon; the toolbar and
    Plugins > FiberQ keep only their text-only entries (TEXT_ONLY)."""
    blank = {}
    for container in built["containers"]:
        key = container["key"]
        if key.startswith("menu:") and key not in MENUS:
            continue  # the interface-language menu: language names, text by design
        missing = [label for label, drawing in container["rows"] if not drawing]
        if len(missing) > TEXT_ONLY.get(key, 0):
            blank[container["title"]] = missing
    assert not blank, f"entries that draw no icon: {blank}"


_ICON_NAME = re.compile(r"ic_\w+\.svg")


def test_every_named_icon_exists():
    """A missing file is a blank button, and the icon loaders swallow the error.

    Every icon file named as a string anywhere in fiberq/, whatever the call
    around it. Names built at run time are checked by what the toolbars draw
    (test_every_button_draws_an_icon).
    """
    on_disk = {p.name for p in ICONS.glob("*.svg")}
    named = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _ICON_NAME.fullmatch(node.value):
                named.append((path.relative_to(PACKAGE), node.lineno, node.value))
    assert len(named) > 50, named
    missing = [f"{rel}:{line} {name}" for rel, line, name in named if name not in on_disk]
    assert not missing, f"named but not in fiberq/icons/: {missing}"


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
