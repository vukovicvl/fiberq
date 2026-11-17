"""What the plugin's initGui() and unload() leave behind may not grow.

QGIS reloads a plugin by calling ``unload()`` on it, dropping it, and building a new one with ``classFactory()``
and ``initGui()``. Whatever ``unload()`` does not take back stays in QGIS for the rest
of the session, one more copy per reload: actions, menus, shortcuts, timers, event filters, connections to
the project's and the canvas's signals, translators, docks, the plugin object itself. v1.6.0 already leaves
some of these behind (the 88 actions parented to the main window, the picture watcher, the schema
migration's one-shot timer). This file pins how much, so that a change which leaves more fails, and a change
which leaves less sets the new numbers.

The child is tests/support/lifecycle_driver.py. It runs two such cycles with ``LifecycleIface``, a stand-in
for QGIS's iface that takes back what the plugin registers (tests/support/fake_iface.py, extended), in
Serbian, so that the plugin installs a translator, and counts the main window and the canvas after each step.
The cycles do not re-import fiberq's modules, as QGIS's reload does: what a module makes on import is made
once here, and again at every reload in QGIS. The counts are kept as deltas from the plain window of the same
child: the absolute numbers differ between QGIS versions, the deltas do not. The driver never runs a delayed
timer, so a pending one-shot is counted, not fired; a 0 ms one-shot is a posted call, which runs in the first
settle after it, as it runs at once in QGIS. Every count is taken after deferred deletions are delivered and
garbage is collected.

Three positive controls run in the child before anything is counted: a one-shot timer, an event filter and a
slot on a project signal must each move their count by one. A Qt change in how one of these is held would
otherwise read as a fix, and lowering a pin for it would hide the next leak.

Why a subprocess: initGui() leaves toolbars, translators and project hooks behind, which in-process would
reach every later test, and a count of the main window's children needs a window that nothing else touched.
"""
import json
import os

import pytest

from support.child import run_driver

DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "support", "lifecycle_driver.py")

#: What one and two initGui()/unload() cycles leave behind, in Serbian: deltas from the plain window of the same
#: child, at v1.6.0 (76b4795) = main (b87cf55), the same on QGIS 3.22, 3.40, 3.44, 4.0 and 4.2. Equality, with a
#: message for each direction (as SILENCE_CEILING in test_error_handling_ratchet.py): a rise is a new leak; a fall
#: is a fix, and the PR that makes it sets the new numbers here.
PINS = {   # key: (after 1 cycle, after 2 cycles)
    "qactions": (101, 202),           # 88 parented to the window + 13 in FiberQ's 12 menus (WP5-FU-25: 109 in QGIS)
    "qactions_parented": (88, 176),
    "qmenus": (12, 24),
    "qshortcuts": (0, 0),
    "qtimers": (0, 0),
    "qtimers_active": (0, 0),
    "python_qtimers_active": (0, 0),
    "pending_one_shots": (1, 2),      # WP5-FU-9: the 2 s schema migration each initGui arms
    "project_receivers": ({}, {}),    # every QgsProject signal, each overload by its signature; nonzero deltas only
    "canvas_receivers": ({}, {}),
    "canvas_children": (1, 2),        # WP5-FU-8: the picture click watcher
    "viewport_filters": (1, 2),       # WP5-FU-8
    "canvas_filters": (0, 0),
    "main_window_filters": (0, 0),
    "plugins_alive": (1, 2),          # each unloaded FiberQPlugin, held by its leftover QActions
    "toolbars": (0, 0),
    "plugin_menu_entries": (0, 0),
    "toolbar_icons": (0, 0),
    "docks": (0, 0),
    "translators": (0, 0),
    "map_tool": (None, None),
    "objects_by_class": ({"QAction": 101, "QMenu": 12, "CanvasImageClickWatcher": 1, "DoubleTapSpaceFilter": 1},
                         {"QAction": 202, "QMenu": 24, "CanvasImageClickWatcher": 2, "DoubleTapSpaceFilter": 2}),
}

#: What lifecycle_driver.py counts and PINS leaves out on purpose: whether the canvas's map tool is the plugin's,
#: which test_unload_unsets_an_active_map_tool reads. Any other count PINS lacks fails the ratchet.
UNPINNED = {"map_tool_fiberq"}


class MapToolLeftActive(AssertionError):
    """``unload()`` left one of the plugin's map tools set on the canvas."""


@pytest.fixture(scope="module")
def lifecycle(tmp_path_factory):
    """Two cycles in one child: ``(returncode, result, output)``, as ``run_driver`` gives them."""
    folder = tmp_path_factory.mktemp("lifecycle")
    (folder / "options.json").write_text(json.dumps({"cycles": 2, "activate": None}), encoding="utf-8")
    return run_driver(folder, DRIVER)


def counts_at(result, label):
    """The counts of the snapshot ``label``."""
    return {s["label"]: s for s in result["snapshots"]}[label]["counts"]


def deltas(result, label):
    """The counts of the snapshot ``label`` less those of "plain".

    A number becomes its difference, a dict the differences of its keys (nonzero ones only), and anything else
    (the map tool's class name, or None) stays as it is.
    """
    plain = counts_at(result, "plain")
    out = {}
    for key, value in counts_at(result, label).items():
        if isinstance(value, dict):
            changed = {sub: value.get(sub, 0) - plain[key].get(sub, 0) for sub in set(value) | set(plain[key])}
            out[key] = {sub: d for sub, d in sorted(changed.items()) if d}
        elif isinstance(value, int) and not isinstance(value, bool):
            out[key] = value - plain[key]
        else:
            out[key] = value
    return out


def ratchet(have, pins, cycle):
    """One message for each count that differs from its pin after ``cycle`` cycles; [] when every pin holds.

    ``have`` is shaped as ``pins``: each key holds its values after 1 and after 2 cycles. A dict is compared key by
    key, so that one more receiver on a signal cannot hide behind one fewer on another. A key of ``have`` that
    ``pins`` lacks, other than those of ``UNPINNED``, gives a message of its own.
    """
    messages = []
    for key in sorted(set(have) - set(pins) - UNPINNED):
        messages.append("lifecycle_driver.py counts %s, which PINS does not pin" % key)
    for key, pinned in pins.items():
        if key not in have:
            messages.append("%s: lifecycle_driver.py no longer counts it, and PINS still pins it" % key)
            continue
        now, then = have[key][cycle - 1], pinned[cycle - 1]
        if isinstance(then, dict):
            pairs = [("%s[%s]" % (key, sub), now.get(sub, 0), then.get(sub, 0)) for sub in sorted(set(now) | set(then))]
        else:
            pairs = [(key, now, then)]
        for name, x, y in pairs:
            if x == y:
                continue
            numbers = isinstance(x, int) and isinstance(y, int)
            change = " (%+d)" % (x - y) if numbers else ""
            if (numbers and x < y) or (y is not None and x is None):
                messages.append("%s after %d cycle(s): %r, pinned at %r%s: good: set PINS[%r] to %r in this PR, "
                                "so that it cannot creep back" % (name, cycle, x, y, change, key, have[key]))
            else:
                messages.append("%s after %d cycle(s): %r, pinned at %r%s: unload() now leaves more behind than "
                                "PINS allows (v1.6.0's values until a fix lowers them)" % (name, cycle, x, y, change))
    return messages


def test_unload_leaves_no_more_than_pinned(lifecycle):
    """Two cycles leave exactly what PINS says, once the language and the controls are as expected."""
    code, result, output = lifecycle
    window = (result or {}).get("modal_window")
    assert window is None, f"a window blocked the child: {window}\n{output}"
    assert code == 0 and result is not None, output
    assert result["effective_language"] == "sr", (
        f"the language pin failed: FiberQ shows {result['effective_language']!r}, not 'sr', so the translator "
        f"count would see nothing. Either the setting did not reach FiberQ (settings in {result['settings_file']}), "
        "or fiberq/i18n/fiberq_sr.qm has no translations")
    assert result["modals"] == [], f"initGui() or unload() raised dialogs: {result['modals']}"
    assert result["iface_mocks"] == {}, (
        "initGui() or unload() now calls these iface methods, which FakeIface answers with a MagicMock, so what "
        "they add or take back is not counted: model them in LifecycleIface (tests/support/lifecycle_driver.py): "
        f"{result['iface_mocks']}")

    probes = result["probes"]
    assert probes == {"one_shot": 1, "filter": [1, 0], "receivers": [1, 0]}, (
        "the counting is broken on this Qt (%s): the controls gave %s, not one_shot 1, filter [1, 0] and receivers "
        "[1, 0]: fix lifecycle_driver.py; do not change PINS" % (result["versions"], probes))

    unsettled = [(s["label"], s["settle_rounds"]) for s in result["snapshots"] if not s["settled"]]
    assert not unsettled, f"these snapshots never counted the same twice in a row: {unsettled}"

    assert deltas(result, "constructed 1")["translators"] == 1, (
        "FiberQ installed no translator: the translator count would see nothing")
    built = deltas(result, "initGui 1")
    assert built["toolbars"] >= 1 and built["qactions"] >= 1, f"initGui() built nothing here: {built}"

    released = [deltas(result, "released 1"), deltas(result, "released 2")]
    have = {key: (released[0][key], released[1][key]) for key in released[0]}
    messages = ratchet(have, PINS, 1) + ratchet(have, PINS, 2)
    live = {s["label"]: s["diagnostic"]["fiberq_live"] for s in result["snapshots"]}
    assert not messages, "\n".join(messages + ["FiberQ objects alive after two cycles: %s" % live["released 2"]])


@pytest.mark.xfail(strict=True, raises=MapToolLeftActive,
                   reason="WP5-FU-27: unload() leaves an active FiberQ map tool set on the canvas; "
                          "the v1.8.0 fix removes this marker")
def test_unload_unsets_an_active_map_tool(tmp_path):
    """A map tool of the plugin's that is active at unload() does not stay set on the canvas.

    v1.6.0 leaves it set, and alive. ``raises=`` keeps every other failure real: a child that dies, a window
    that blocks, a tool that was never set, or an iface call that FakeIface answers with a MagicMock (FiberQ's
    own tools leave the canvas with ``iface.actionPan().trigger()``, which does nothing here) fails the test
    instead of counting as the known defect.
    """
    (tmp_path / "options.json").write_text(json.dumps({"cycles": 1, "activate": "activate_fiber_break_tool"}),
                                           encoding="utf-8")
    code, result, output = run_driver(tmp_path, DRIVER)
    window = (result or {}).get("modal_window")
    assert window is None, f"a window blocked the child: {window}\n{output}"
    assert code == 0 and result is not None, output
    assert result["iface_mocks"] == {}, (
        "initGui(), the tool or unload() now calls these iface methods, which FakeIface answers with a MagicMock, "
        "so what they do to the canvas is not seen: model them in LifecycleIface (tests/support/lifecycle_driver.py): "
        f"{result['iface_mocks']}")
    activated = counts_at(result, "activated 1")
    assert activated["map_tool"] == "FiberBreakTool", f"the fiber break tool was not set: {activated['map_tool']}"
    released = counts_at(result, "released 1")
    if released["map_tool_fiberq"]:
        raise MapToolLeftActive("after unload() the canvas still has the plugin's %s set" % released["map_tool"])


SAME = {"qactions": (101, 202), "project_receivers": ({}, {}), "map_tool": (None, None)}

RATCHET_CASES = {
    "same": (dict(SAME), []),
    "rose": (dict(SAME, project_receivers=({}, {"layersWillBeRemoved(QList<QgsMapLayer*>)": 1})),
             ["project_receivers[layersWillBeRemoved(QList<QgsMapLayer*>)] after 2 cycle(s): 1, pinned at 0 (+1): "
              "unload() now leaves more behind than PINS allows (v1.6.0's values until a fix lowers them)"]),
    "fell": (dict(SAME, qactions=(101, 201)),
             ["qactions after 2 cycle(s): 201, pinned at 202 (-1): good: set PINS['qactions'] to (101, 201) in this "
              "PR, so that it cannot creep back"]),
}


@pytest.mark.parametrize("case", sorted(RATCHET_CASES))
def test_the_ratchet_names_each_direction(case):
    """The ratchet's messages, on synthetic counts: nothing when they equal the pins, one line per change."""
    have, expected = RATCHET_CASES[case]
    assert ratchet(have, SAME, 1) + ratchet(have, SAME, 2) == expected
