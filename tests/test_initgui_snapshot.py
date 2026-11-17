"""Every toolbar, drop-down and menu entry that initGui() builds, and the keys it binds, against one golden file.

A child process builds the plugin with FakeIface, runs initGui() and records what it built
(tests/support/initgui_snapshot.py): the FiberQ toolbar, the Quick toolbar, every drop-down of the two,
nested ones included, and Plugins > FiberQ, each entry in order with its kind, text, tooltip, keys, object
name, icon file, and whether it is visible, enabled and checkable; then the actions and QShortcuts it adds
to the main window and the map canvas. A renamed, moved, re-keyed or re-iconed entry fails this test, and so
does an entry that is added or lost.

The record is the same on every QGIS the tests run on, from 3.22 to 4.2, so one golden file,
tests/initgui_golden.json, serves them all. Icons are named by the files in fiberq/icons/ that draw the same
in the child, not by their pixels, which differ between Qt 5 and Qt 6. The child pins the plugin's language
to English in a fresh profile of its own, so neither the environment's language nor anyone's settings can
change the record; the test checks that the pin held before it compares.

The golden file changes only on purpose: docs/testing.md, "The initGui golden file", says how to write it
anew. This test never writes into the tree.

One more test reads the same record: the key R that initGui() binds to terminal slack never fires today,
because the action that holds it is hidden and Qt never fires a hidden action's shortcut. It is a known
defect, marked as an expected failure until the fix lands; the fix removes the marker.

The other tests here need no QGIS. They check the comparison itself, on a small record made up here, so that
a comparison that finds nothing cannot pass the test above unnoticed, and that the golden file is in the one
form the writer gives it.
"""
import copy
import difflib
import os

import pytest

from support.child import run_driver
from support.initgui_snapshot import (CONTAINER_KEYS, FIELDS, FORMAT, GOLDEN, OUTSIDE_KEYS, differences,
                                      dump_golden, load_golden)

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, "support", "initgui_snapshot.py")

#: What a failure says after the differences.
UPDATE = ("\n\nIf this change is intended, write the file anew and commit it with the change, saying why in the PR:\n"
          "python3 tests/support/initgui_snapshot.py --write <a new file> (with QGIS; "
          "PYTHONPATH=/usr/share/qgis/python for the qgis.org packages), then copy it over tests/initgui_golden.json.\n"
          "This run's record (kept only when the suite runs in place, as make test does, under "
          "ci-results/<run>/stages/<stage>/work/): %s")


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    """The child's record, made once for this file: ``(returncode, result, output, folder)``."""
    folder = tmp_path_factory.mktemp("initgui_snapshot")
    code, result, output = run_driver(folder, DRIVER)
    return code, result, output, folder


def _built(snapshot):
    """The child's result, once the checks every test here makes first have passed."""
    code, result, output, _folder = snapshot
    window = (result or {}).get("modal_window")   # the window watch ends the child with exit code 3
    assert window is None, f"initGui() opened a window that waits for a click: {window}\n{output}"
    assert code == 0 and result is not None, f"returncode {code}\n{output}"
    return result


def test_initgui_matches_the_golden_file(snapshot):
    result = _built(snapshot)
    assert result["modals"] == [], f"initGui() raised message boxes: {result['modals']}"
    assert result["iface_mocks"] == {}, (
        "initGui now calls iface.X, which FakeIface answers with a MagicMock; what it adds is not in the snapshot: "
        f"model it in snapshot_iface (tests/support/initgui_snapshot.py): {result['iface_mocks']}")
    assert result["env"]["effective_language"] == "en", f"the language pin failed: {result['env']}"
    problems = differences(load_golden(), result["record"])
    if problems:
        written = snapshot[3] / "initgui_golden.json"
        with open(written, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(dump_golden(result["record"]))
        lines = "\n".join(problems)
        message = f"the plugin's toolbars, menus or keys differ from tests/initgui_golden.json:\n{lines}"
        pytest.fail(message + UPDATE % written, pytrace=False)


class TerminalSlackKeyDead(AssertionError):
    """Nothing enabled holds the key R that initGui() binds to terminal slack."""


@pytest.mark.xfail(strict=True, raises=TerminalSlackKeyDead,
                   reason="WP5-FU-28: the key R for terminal slack never fires, because the action that holds it is "
                          "hidden; the fix removes this marker")
def test_the_terminal_slack_key_can_fire(snapshot):
    """initGui() binds R to terminal slack through a hidden QAction, and Qt disables a hidden action together
    with its shortcut. The key works once something enabled holds it: an action or QShortcut outside the
    toolbars and menus, or an entry of one, that is enabled and has R among its keys. A failing child or record
    is a real failure here, not the expected one, and so is a record in which nothing binds R any more."""
    record = _built(snapshot)["record"]
    items = [item for name in ("main_window_actions", "shortcuts") for item in record["outside"][name]]
    items += [entry for container in record["containers"] for entry in container["entries"]
              if entry["kind"] != "separator"]
    bound = [item for item in items if "R" in item["keys"]]
    if not bound:
        pytest.fail("nothing binds R any more: if dropping the key was intended, delete this test")
    if not any(item["enabled"] for item in bound):
        raise TerminalSlackKeyDead(f"nothing enabled holds the key R: {bound}")


def test_the_golden_file_is_in_canonical_form():
    """The golden file is exactly what dump_golden() writes for it: its format, each container with its kind's
    identity, each entry with the fields of FIELDS, one entry per line. So an edit by hand that --write would
    not reproduce fails here, and a change to the file reads as a change of whole lines."""
    with open(GOLDEN, encoding="utf-8") as fh:   # universal newlines: a checkout with CRLF reads the same
        text = fh.read()
    golden = load_golden()
    problems = []
    if sorted(golden) != sorted(["format", "note", "language", "containers", "outside"]):
        problems.append(f"top-level keys {sorted(golden)}")
    if golden.get("format") != FORMAT:
        problems.append(f"format {golden.get('format')!r}, not {FORMAT}")
    paths = [container.get("path") for container in golden.get("containers", [])]
    twice = sorted({path for path in paths if paths.count(path) > 1})
    if twice:
        problems.append(f"container paths that occur twice: {twice}")
    for container in golden.get("containers", []):
        keys = CONTAINER_KEYS.get(container.get("kind"))
        if keys is None or sorted(container) != sorted(keys + ("entries",)):
            problems.append(f"{container.get('path')}: container keys {sorted(container)}")
            continue
        for n, entry in enumerate(container["entries"]):
            if entry != {"kind": "separator"} and (entry.get("kind") == "separator" or sorted(entry) != sorted(FIELDS)):
                problems.append(f"{container['path']}[{n}]: entry keys {sorted(entry)}")
    outside = golden.get("outside")
    if outside is not None:
        if sorted(outside) != sorted(OUTSIDE_KEYS):
            problems.append(f"outside keys {sorted(outside)}")
        else:
            for name, keys in OUTSIDE_KEYS.items():
                problems += [f"outside {name}[{n}]: keys {sorted(item)}"
                             for n, item in enumerate(outside[name]) if sorted(item) != sorted(keys)]
    assert not problems, f"tests/initgui_golden.json is not a golden file of format {FORMAT}:\n" + "\n".join(problems)
    canonical = dump_golden(golden)
    diff = difflib.unified_diff(text.splitlines(), canonical.splitlines(), "tests/initgui_golden.json",
                                "as dump_golden() writes it", lineterm="", n=0)
    assert text == canonical, ("tests/initgui_golden.json is not in the form dump_golden() writes; write it with "
                               "--write (docs/testing.md, 'The initGui golden file'):\n" + "\n".join(list(diff)[:40]))


def _entry(text, **fields):
    """An action entry of the made-up record."""
    entry = {"kind": "action", "text": text, "tooltip": text, "keys": [], "objectName": "",
             "icon": ["ic_%s.svg" % text.lower()], "visible": True, "enabled": True, "checkable": False}
    entry.update(fields)
    return entry


def _record():
    """A made-up record: a toolbar with a drop-down, and the keys bound outside them."""
    return {
        "language": "en",
        "containers": [
            {"path": "Bar", "kind": "toolbar", "title": "Bar", "objectName": "Bar", "hidden": False,
             "entries": [_entry("Group", kind="submenu"), {"kind": "separator"}, _entry("Undo", keys=["Ctrl+Z"]),
                         _entry("Redo")]},
            {"path": "Bar > Group", "kind": "menu", "title": "Group", "objectName": "",
             "entries": [_entry("One"), _entry("Two")]},
        ],
        "outside": {
            "main_window_actions": [{"text": "Slack", "keys": ["R"], "objectName": "", "visible": False,
                                     "enabled": False}],
            "shortcuts": [{"parent": "canvas", "keys": ["Ctrl+B"], "context": "ApplicationShortcut", "enabled": True},
                          {"parent": "main window", "keys": ["Ctrl+B"], "context": "ApplicationShortcut",
                           "enabled": True}],
        },
    }


def _tooltip(seen):
    seen["containers"][0]["entries"][2]["tooltip"] = "Undo it"


def _added(seen):
    seen["containers"][0]["entries"].append(_entry("Help"))


def _removed(seen):
    del seen["containers"][0]["entries"][3]


def _moved(seen):
    entries = seen["containers"][0]["entries"]
    entries[2], entries[3] = entries[3], entries[2]


def _separator(seen):
    seen["containers"][0]["entries"][2] = {"kind": "separator"}


def _container_added(seen):
    seen["containers"].append({"path": "Bar > Extra", "kind": "menu", "title": "Extra", "objectName": "",
                               "entries": [_entry("Three")]})


def _container_missing(seen):
    del seen["containers"][1]


def _container_title(seen):
    seen["containers"][1]["title"] = "Groups"


def _outside_action(seen):
    seen["outside"]["main_window_actions"][0]["keys"] = []


def _outside_shortcut(seen):
    seen["outside"]["shortcuts"][1]["keys"] = ["Ctrl+Shift+B"]


def _outside_missing(seen):
    seen["outside"] = None


def _language(seen):
    seen["language"] = "sr"


def _language_and_title(seen):
    _language(seen)
    _container_title(seen)


def _unchanged(seen):
    return None


#: case: (change made to the record seen, differences()'s keyword arguments, the lines differences() must give)
CASES = {
    "same": (_unchanged, {}, []),
    "tooltip": (_tooltip, {}, ['Bar[2]: tooltip: golden "Undo", now "Undo it"']),
    "tooltip-skipped": (_tooltip, {"skip_fields": ("tooltip",)}, []),
    "added": (_added, {}, ['Bar[4]: added {"kind": "action", "text": "Help", "tooltip": "Help", "keys": [], '
                           '"objectName": "", "icon": ["ic_help.svg"], "visible": true, "enabled": true, '
                           '"checkable": false}']),
    "removed": (_removed, {}, ['Bar[3]: removed {"kind": "action", "text": "Redo", "tooltip": "Redo", "keys": [], '
                               '"objectName": "", "icon": ["ic_redo.svg"], "visible": true, "enabled": true, '
                               '"checkable": false}']),
    "moved": (_moved, {}, ['Bar[2]: added {"kind": "action", "text": "Redo", "tooltip": "Redo", "keys": [], '
                           '"objectName": "", "icon": ["ic_redo.svg"], "visible": true, "enabled": true, '
                           '"checkable": false}',
                           'Bar[3]: removed {"kind": "action", "text": "Redo", "tooltip": "Redo", "keys": [], '
                           '"objectName": "", "icon": ["ic_redo.svg"], "visible": true, "enabled": true, '
                           '"checkable": false}']),
    "separator": (_separator, {}, ['Bar[2]: removed {"kind": "action", "text": "Undo", "tooltip": "Undo", "keys": '
                                   '["Ctrl+Z"], "objectName": "", "icon": ["ic_undo.svg"], "visible": true, '
                                   '"enabled": true, "checkable": false}',
                                   'Bar[2]: added {"kind": "separator"}']),
    "container-added": (_container_added, {}, ["Bar > Extra: container added (1 entry)"]),
    "container-missing": (_container_missing, {}, ["Bar > Group: container missing"]),
    "container-title": (_container_title, {}, ['Bar > Group: title: golden "Group", now "Groups"']),
    "outside-action": (_outside_action, {}, ['outside actions[0]: keys: golden ["R"], now []']),
    "outside-shortcut": (_outside_shortcut, {}, [
        'outside shortcuts: missing {"parent": "main window", "keys": ["Ctrl+B"], "context": "ApplicationShortcut", '
        '"enabled": true}',
        'outside shortcuts: added {"parent": "main window", "keys": ["Ctrl+Shift+B"], "context": '
        '"ApplicationShortcut", "enabled": true}']),
    "outside-missing": (_outside_missing, {}, ["outside: not recorded"]),
    "language": (_language, {}, ['language: golden "en", now "sr"']),
    "limit": (_language_and_title, {"limit": 1}, ['language: golden "en", now "sr"', "... and 1 more"]),
}


@pytest.mark.parametrize("case", list(CASES))
def test_differences_name_each_change(case):
    """Each kind of change gives its own line, and an equal record or a skipped field gives none: a comparison
    that finds nothing would let the golden file test pass whatever initGui() builds. Past ``limit`` lines, one
    line says how many more there are."""
    change, options, expected = CASES[case]
    golden = _record()
    seen = copy.deepcopy(golden)
    change(seen)
    assert differences(golden, seen, **options) == expected
