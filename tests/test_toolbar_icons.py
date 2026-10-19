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
tests/test_schematic_lifecycle.py, whose fake iface this borrows).
"""
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
from itertools import combinations

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = pathlib.Path(REPO_ROOT) / "fiberq"
ICONS = PACKAGE / "icons"

#: Wall-clock ceiling for the child. The suite has no timeout plugin.
TIMEOUT_S = 120

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

DRIVER = '''
import hashlib
import json
import os
import sys
from unittest import mock

sys.path.insert(0, {repo!r})

from qgis.core import QgsApplication

QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()

from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, QSize
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMainWindow, QMessageBox, QToolBar, QToolButton

PLUGIN_MENU = []
MODALS = []


def modal(kind):
    def show(*args, **kwargs):
        MODALS.append([kind] + [str(a) for a in args[1:3]])
        return QMessageBox.StandardButton.No
    return show


# A dialog raised while the toolbar is built would wait for a click until the
# timeout; record it instead, and the test below fails on it.
for kind in ("critical", "warning", "information", "question"):
    setattr(QMessageBox, kind, staticmethod(modal(kind)))


class Iface:
    """What initGui() really uses; the rest answers with a MagicMock."""

    def __init__(self):
        self._window = QMainWindow()
        self._canvas = QgsMapCanvas(self._window)
        self._window.setCentralWidget(self._canvas)
        self._mocks = {{}}

    def mainWindow(self):
        return self._window

    def mapCanvas(self):
        return self._canvas

    def addToolBar(self, name):
        return QToolBar(name, self._window)

    def addPluginToMenu(self, _menu, action):
        PLUGIN_MENU.append(action)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self.__dict__["_mocks"].setdefault(name, mock.MagicMock(name=name))


def drawn(icon):
    """What the icon draws: a digest at toolbar size and its 16 px RGBA, or None."""
    if icon.isNull():
        return None
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    icon.pixmap(QSize(32, 32)).toImage().save(buffer, "PNG")
    buffer.close()
    small = icon.pixmap(QSize(16, 16)).toImage()
    pixels = []
    for y in range(16):
        for x in range(16):
            if x < small.width() and y < small.height():
                c = small.pixelColor(x, y)
                pixels.append("%02x%02x%02x%02x" % (c.red(), c.green(), c.blue(), c.alpha()))
            else:
                pixels.append("00000000")
    return [hashlib.sha1(bytes(data)).hexdigest(), "".join(pixels)]


icons = os.path.join({repo!r}, "fiberq", "icons")
files = {{name: drawn(QIcon(os.path.join(icons, name)))
         for name in sorted(os.listdir(icons)) if name.endswith(".svg")}}

from fiberq.main_plugin import FiberQPlugin

# initGui() arms a 2 s one-shot schema migration; nothing here waits for it.
FiberQPlugin._run_schema_migrations = lambda self: None
plugin = FiberQPlugin(Iface())
plugin.initGui()

containers = []


def menu(title, qmenu, group):
    rows = []
    containers.append({{"title": title, "group": group, "rows": rows}})
    for action in qmenu.actions():
        if action.isSeparator() or not action.isVisible():
            continue
        rows.append([action.text(), drawn(action.icon())])
        if action.menu() is not None:
            menu(title + " > " + action.text(), action.menu(), drawn(action.icon()))


def toolbar(title, key, bar):
    rows = []
    containers.append({{"title": title, "key": key, "rows": rows}})
    for action in bar.actions():
        button = bar.widgetForAction(action)
        if action.isSeparator() or not action.isVisible() or not isinstance(button, QToolButton):
            continue
        label = action.text() or button.toolTip() or button.text()
        rows.append([label, drawn(button.icon())])
        if button.menu() is not None:
            menu(title + " > " + label, button.menu(), drawn(button.icon()))


toolbar("FiberQ toolbar", "toolbar", plugin.toolbar)
quick = getattr(plugin, "quick_toolbar", None)
if quick is not None:
    toolbar("FiberQ Quick toolbar", "quick", quick.toolbar)
containers.append({{"title": "Plugins > FiberQ", "key": "plugins",
                   "rows": [[a.text(), drawn(a.icon())] for a in PLUGIN_MENU]}})

print("RESULT " + json.dumps({{"files": files, "containers": containers, "modals": MODALS}}), flush=True)
sys.stdout.flush()
os._exit(0)
'''


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build both toolbars once in a child process and name every container."""
    folder = tmp_path_factory.mktemp("toolbar_icons")
    script = folder / "toolbar_icons.py"
    script.write_text(DRIVER.format(repo=REPO_ROOT), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(folder), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(folder),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT ")]
    assert done.returncode == 0 and lines, f"returncode {done.returncode}\n{output}"
    result = json.loads(lines[-1][len("RESULT "):])
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
