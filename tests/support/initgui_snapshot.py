"""The record of what the plugin's ``initGui()`` builds, its golden file, and the child driver that records it.

What is recorded, in order:

- the containers: the FiberQ toolbar, every drop-down it opens (nested ones depth first), the Quick toolbar
  with its drop-downs, and each menu the plugin adds under Plugins. Each container has its identity (path,
  kind, title, object name, and for a toolbar whether it is hidden) and every entry, separators and
  invisible entries included. An entry has the fields of ``FIELDS``; its icon is named by the files in
  fiberq/icons/ that draw the same at 32 px, matched in the process that draws them, so no pixel digest
  leaves the process and one golden file serves Qt 5 and Qt 6;
- the keys the plugin binds outside its toolbars and menus: the actions it adds to the main window and the
  ``QShortcut`` objects it creates under the main window or the map canvas. These are the objects that are
  new since ``outside_baseline()`` was taken.

Two ways in:

- as a driver script, ``run_driver(folder, <this file>)`` (``child.py``): ``main()`` starts a QgsApplication
  of its own in a fresh profile, pins the language to English, builds the plugin with ``FakeIface``, runs
  ``initGui()`` and prints one line, ``RESULT`` and a JSON object (``main()`` says what it holds). With
  ``--write <a new file>`` it also writes the record there as a golden file; it never overwrites a file;
- imported, in the real QGIS app: ``record()`` walks what QGIS built (tests/app/smoke.py).

tests/test_initgui_snapshot.py compares the record with ``GOLDEN`` (``differences()``). The golden file is
written by ``dump_golden()`` only, one entry per line, so that a change shows as a short diff.

The module imports only the standard library at its top; each function that needs QGIS imports it itself.
So a test file can import this module at its top and still be picked by the fast stage. It runs from
tests/support/ as a script, so it imports the other modules there as ``support.<module>``, and it never
imports ``support.toolbar_driver``.
"""
import collections
import difflib
import hashlib
import json
import os
import sys
import tempfile

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(TESTS)

#: The golden file, one for every QGIS version the tests run on.
GOLDEN = os.path.join(TESTS, "initgui_golden.json")

#: The golden file's format. A change to its layout or to what it records raises it.
FORMAT = 1

#: The golden file's ``note``.
NOTE = "FiberQ's initGui snapshot. Change it on purpose only: docs/testing.md, 'The initGui golden file'."

#: An entry's fields, in the order the golden file writes them. A separator is ``{"kind": "separator"}`` only.
FIELDS = ("kind", "text", "tooltip", "keys", "objectName", "icon", "visible", "enabled", "checkable")

#: A container's identity, by kind, in the order the golden file writes it.
CONTAINER_KEYS = {"toolbar": ("path", "kind", "title", "objectName", "hidden"),
                  "menu": ("path", "kind", "title", "objectName"),
                  "plugins": ("path", "kind")}

#: The two lists of the outside section and the fields of their items, in the order the golden file writes them.
OUTSIDE_KEYS = {"main_window_actions": ("text", "keys", "objectName", "visible", "enabled"),
                "shortcuts": ("parent", "keys", "context", "enabled")}

#: What ``differences()`` can compare.
SECTIONS = ("language", "containers", "entries", "outside")

#: The icon of an entry that draws an icon that no file in fiberq/icons/ draws.
FOREIGN_ICON = "<drawn, not a fiberq/icons file>"

#: Qt's shortcut contexts by value, so that PyQt5 and PyQt6 give the same name.
CONTEXTS = {0: "WidgetShortcut", 1: "WindowShortcut", 2: "ApplicationShortcut", 3: "WidgetWithChildrenShortcut"}

#: The message boxes the plugin raised in the child, each as its kind, title and text.
MODALS = []

USAGE = "usage: python3 tests/support/initgui_snapshot.py [--write <a new file>]"


def load_golden(path=GOLDEN):
    """The golden file at ``path``, as a dict."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _text(value):
    """``value`` as JSON text, with non-ASCII characters as they are."""
    return json.dumps(value, ensure_ascii=False)


def _comma(position, items):
    """The comma after item ``position`` of ``items``, or nothing after the last one."""
    return "," if position < len(items) - 1 else ""


def dump_golden(record):
    """The golden file's text for ``record``: the canonical form, one entry per line, UTF-8 characters as they are.

    ``record`` is what ``record()`` returns, or a golden file read back; its ``format`` and ``note``, if any, are
    not used: the text gets ``FORMAT`` and ``NOTE``. Each container is written with its kind's identity keys,
    each entry with the keys of ``FIELDS``, each outside item with its list's keys, in that order.
    """
    lines = ["{", ' "format": %d,' % FORMAT, ' "note": %s,' % _text(NOTE),
             ' "language": %s,' % _text(record["language"]), ' "containers": [']
    containers = record["containers"]
    for n, container in enumerate(containers):
        identity = {key: container[key] for key in CONTAINER_KEYS[container["kind"]]}
        lines.append("  " + _text(identity)[:-1] + ', "entries": [')
        entries = container["entries"]
        for m, entry in enumerate(entries):
            if entry["kind"] == "separator":
                entry = {"kind": "separator"}
            else:
                entry = {field: entry[field] for field in FIELDS}
            lines.append("   " + _text(entry) + _comma(m, entries))
        lines.append("  ]}" + _comma(n, containers))
    lines.append(" ],")
    outside = record["outside"]
    if outside is None:
        lines.append(' "outside": null')
    else:
        lines.append(' "outside": {')
        names = list(OUTSIDE_KEYS)
        for n, name in enumerate(names):
            items = outside[name]
            lines.append("  %s: [" % _text(name))
            for m, item in enumerate(items):
                lines.append("   " + _text({key: item[key] for key in OUTSIDE_KEYS[name]}) + _comma(m, items))
            lines.append("  ]" + _comma(n, names))
        lines.append(" }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _key(item, skip_fields=()):
    """The comparable form of an entry or an outside item: JSON with sorted keys, without ``skip_fields``."""
    return json.dumps({k: v for k, v in item.items() if k not in skip_fields}, sort_keys=True)


def _shown(item, skip_fields=()):
    """An entry or an outside item as a difference line shows it: JSON in its own key order, without ``skip_fields``."""
    return _text({k: v for k, v in item.items() if k not in skip_fields})


def _sequence(path, golden, seen, skip_fields):
    """The lines for two lists of entries (or outside actions) that are compared in order."""
    lines = []
    matcher = difflib.SequenceMatcher(None, [_key(e, skip_fields) for e in golden],
                                      [_key(e, skip_fields) for e in seen], autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                old = {f: v for f, v in golden[i1 + k].items() if f not in skip_fields}
                new = {f: v for f, v in seen[j1 + k].items() if f not in skip_fields}
                if set(old) != set(new):   # a separator against an entry: the fields do not pair up
                    lines.append("%s[%d]: removed %s" % (path, i1 + k, _text(old)))
                    lines.append("%s[%d]: added %s" % (path, j1 + k, _text(new)))
                    continue
                for field in old:
                    if old[field] != new[field]:
                        change = (path, i1 + k, field, _text(old[field]), _text(new[field]))
                        lines.append("%s[%d]: %s: golden %s, now %s" % change)
            continue
        lines.extend("%s[%d]: removed %s" % (path, i, _shown(golden[i], skip_fields)) for i in range(i1, i2))
        lines.extend("%s[%d]: added %s" % (path, j, _shown(seen[j], skip_fields)) for j in range(j1, j2))
    return lines


def _multiset(label, golden, seen):
    """The lines for two lists of outside items compared as multisets: what is missing, then what was added."""
    have = collections.Counter(_key(item) for item in seen)
    want = collections.Counter(_key(item) for item in golden)
    lines = []
    for item in golden:
        if have[_key(item)] > 0:
            have[_key(item)] -= 1
        else:
            lines.append("%s: missing %s" % (label, _shown(item)))
    for item in seen:
        if want[_key(item)] > 0:
            want[_key(item)] -= 1
        else:
            lines.append("%s: added %s" % (label, _shown(item)))
    return lines


def differences(golden, seen, sections=SECTIONS, skip_fields=(), limit=40):
    """What differs between two records (a golden file read back, or what ``record()`` returns): [] when equal.

    ``sections`` is a subset of ``SECTIONS``; the lines come in the order of ``SECTIONS``:

    - ``language``: ``language: golden "en", now "sr"``;
    - ``containers``: a container of the golden file that is missing (``<path>: container missing``), an
      identity field that differs (``<path>: <field>: golden X, now Y``), then a container that was added
      (``<path>: container added (N entries)``);
    - ``entries``: for each container on both sides, the entries in order, compared without the fields in
      ``skip_fields``: ``<path>[i]: removed {...}``, ``<path>[j]: added {...}``, or for an entry in the same
      place, ``<path>[i]: <field>: golden X, now Y``. ``i`` counts in the golden file, ``j`` in the record seen;
    - ``outside``: the main window's actions in the same way, under the path ``outside actions``; the
      shortcuts as a multiset (``outside shortcuts: missing {...}`` or ``added {...}``); ``outside: not
      recorded`` when either side has no outside section.

    Values are shown as JSON. After ``limit`` lines, one more line says how many were left out.
    """
    lines = []
    if "language" in sections and golden["language"] != seen["language"]:
        lines.append("language: golden %s, now %s" % (_text(golden["language"]), _text(seen["language"])))
    gold = {c["path"]: c for c in golden["containers"]}
    now = {c["path"]: c for c in seen["containers"]}
    if "containers" in sections:
        for path, old in gold.items():
            new = now.get(path)
            if new is None:
                lines.append("%s: container missing" % path)
                continue
            fields = list(CONTAINER_KEYS.get(old["kind"], ("path", "kind")))
            fields += [f for f in CONTAINER_KEYS.get(new["kind"], ()) if f not in fields]
            for field in fields:
                if field != "path" and old.get(field) != new.get(field):
                    change = (path, field, _text(old.get(field)), _text(new.get(field)))
                    lines.append("%s: %s: golden %s, now %s" % change)
        for path, new in now.items():
            if path not in gold:
                count = len(new["entries"])
                lines.append("%s: container added (%d %s)" % (path, count, "entry" if count == 1 else "entries"))
    if "entries" in sections:
        for path, old in gold.items():
            if path in now:
                lines.extend(_sequence(path, old["entries"], now[path]["entries"], skip_fields))
    if "outside" in sections:
        old, new = golden["outside"], seen["outside"]
        if old is None or new is None:
            lines.append("outside: not recorded")
        else:
            lines.extend(_sequence("outside actions", old["main_window_actions"], new["main_window_actions"],
                                   skip_fields))
            lines.extend(_multiset("outside shortcuts", old["shortcuts"], new["shortcuts"]))
    if len(lines) > limit:
        lines = lines[:limit] + ["... and %d more" % (len(lines) - limit)]
    return lines


def _digest(icon):
    """sha1 of the icon's 32 px PNG; None for a null icon or one that draws nothing."""
    from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, QSize

    if icon is None or icon.isNull():
        return None
    pixmap = icon.pixmap(QSize(32, 32))
    if pixmap.isNull():
        return None
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.toImage().save(buffer, "PNG")
    buffer.close()
    return hashlib.sha1(bytes(data)).hexdigest()


def _icon_index(icons_dir):
    """``({digest: [file names]}, [every .svg file name])`` for the icon files in ``icons_dir``, drawn here."""
    from qgis.PyQt.QtGui import QIcon

    index = {}
    names = sorted(name for name in os.listdir(icons_dir) if name.endswith(".svg"))
    for name in names:
        digest = _digest(QIcon(os.path.join(icons_dir, name)))
        if digest is not None:
            index.setdefault(digest, []).append(name)
    return index, names


def _icon(icon, index):
    """The icon files that draw ``icon``, sorted; None for no icon; ``FOREIGN_ICON`` when no file draws it."""
    digest = _digest(icon)
    if digest is None:
        return None
    return sorted(index.get(digest, [])) or FOREIGN_ICON


def _portable(sequences):
    """The non-empty key sequences, as PortableText."""
    from qgis.PyQt.QtGui import QKeySequence

    return [s.toString(QKeySequence.SequenceFormat.PortableText) for s in sequences if not s.isEmpty()]


def _action_entry(action, index):
    """A QAction as an entry: a separator, a submenu (it has a menu) or an action."""
    if action.isSeparator():
        return {"kind": "separator"}
    return {"kind": "action" if action.menu() is None else "submenu", "text": action.text(),
            "tooltip": action.toolTip(), "keys": _portable(action.shortcuts()), "objectName": action.objectName(),
            "icon": _icon(action.icon(), index), "visible": action.isVisible(), "enabled": action.isEnabled(),
            "checkable": action.isCheckable()}


def _widget_entry(action, widget, index):
    """A toolbar's QWidgetAction as an entry, from its widget: ``(entry, menu, label)``.

    A tool button is a submenu when it has a menu (a drop-down), else a widget; either way its own text, key,
    icon and checkability are recorded. Any other widget (the "FiberQ" label) is a widget with no key or icon.
    """
    from qgis.PyQt.QtWidgets import QToolButton

    if isinstance(widget, QToolButton):
        entry = {"kind": "widget" if widget.menu() is None else "submenu", "text": widget.text(),
                 "tooltip": widget.toolTip(), "keys": _portable([widget.shortcut()]),
                 "objectName": widget.objectName(), "icon": _icon(widget.icon(), index),
                 "visible": action.isVisible(), "enabled": widget.isEnabled(), "checkable": widget.isCheckable()}
        return entry, widget.menu(), widget.text() or widget.toolTip() or "?"
    text = widget.text() if callable(getattr(widget, "text", None)) else ""
    entry = {"kind": "widget", "text": text if isinstance(text, str) else "", "tooltip": widget.toolTip(),
             "keys": [], "objectName": widget.objectName(), "icon": None, "visible": action.isVisible(),
             "enabled": widget.isEnabled(), "checkable": False}
    return entry, None, None


def _unique(path, containers):
    """``path``, or ``path (2)``, ``path (3)``... when a container already has it."""
    used = {c["path"] for c in containers}
    candidate, n = path, 1
    while candidate in used:
        n += 1
        candidate = "%s (%d)" % (path, n)
    return candidate


def _menu(containers, path, menu, index):
    """Add the drop-down ``menu`` as a container, then each drop-down inside it."""
    entries = []
    path = _unique(path, containers)
    containers.append({"path": path, "kind": "menu", "title": menu.title(), "objectName": menu.objectName(),
                       "entries": entries})
    for action in menu.actions():
        entry = _action_entry(action, index)
        entries.append(entry)
        if entry["kind"] == "submenu":
            _menu(containers, path + " > " + (action.text() or "?"), action.menu(), index)


def _toolbar(containers, bar, index):
    """Add the toolbar ``bar`` as a container, then each drop-down of its buttons."""
    from qgis.PyQt.QtWidgets import QToolButton, QWidgetAction

    entries = []
    path = _unique(bar.windowTitle(), containers)
    containers.append({"path": path, "kind": "toolbar", "title": bar.windowTitle(), "objectName": bar.objectName(),
                       "hidden": bar.isHidden(), "entries": entries})
    for action in bar.actions():
        widget = action.defaultWidget() if isinstance(action, QWidgetAction) else None
        if widget is not None and not action.isSeparator():
            entry, menu, label = _widget_entry(action, widget, index)
        else:
            entry, menu, label = _action_entry(action, index), action.menu(), action.text() or "?"
            button = bar.widgetForAction(action)
            if menu is None and entry["kind"] != "separator" and isinstance(button, QToolButton):
                menu = button.menu()
                if menu is not None:
                    entry["kind"] = "submenu"
        entries.append(entry)
        if menu is not None:
            _menu(containers, path + " > " + label, menu, index)


def _plugins(containers, name, actions, index):
    """Add one menu under Plugins, with the actions the plugin added to it, as a container."""
    entries = []
    path = _unique("Plugins > " + name, containers)
    containers.append({"path": path, "kind": "plugins", "entries": entries})
    for action in actions:
        entry = _action_entry(action, index)
        entries.append(entry)
        if entry["kind"] == "submenu":
            _menu(containers, path + " > " + (action.text() or "?"), action.menu(), index)


def _shortcuts(main_window, canvas):
    """Every QShortcut under the main window or the map canvas, each once."""
    from qgis.PyQt.QtWidgets import QShortcut

    found, held = [], set()
    for shortcut in list(main_window.findChildren(QShortcut)) + list(canvas.findChildren(QShortcut)):
        if id(shortcut) not in held:
            held.add(id(shortcut))
            found.append(shortcut)
    return found


def outside_baseline(main_window, canvas):
    """The main window's actions and the QShortcuts under it or the canvas now, before the plugin loads.

    It holds the objects themselves. Holding them keeps their Python wrappers alive, so ``record()`` finds the
    same objects again by identity and lists only the ones created since; an object deleted later cannot hand
    its identity to a new one, as it can hand on its C++ address.
    """
    return {"main_window_actions": list(main_window.actions()), "shortcuts": _shortcuts(main_window, canvas)}


def _outside(main_window, canvas, baseline):
    """The outside section: the actions and QShortcuts that are not in ``baseline``."""
    from qgis.PyQt import sip

    held_actions = {id(a) for a in baseline["main_window_actions"]}
    held_shortcuts = {id(s) for s in baseline["shortcuts"]}
    actions = [{"text": a.text(), "keys": _portable(a.shortcuts()), "objectName": a.objectName(),
                "visible": a.isVisible(), "enabled": a.isEnabled()}
               for a in main_window.actions() if id(a) not in held_actions]
    places = {sip.unwrapinstance(main_window): "main window", sip.unwrapinstance(canvas): "canvas"}
    shortcuts = []
    for shortcut in _shortcuts(main_window, canvas):
        if id(shortcut) in held_shortcuts:
            continue
        parent = shortcut.parent()
        place = places.get(sip.unwrapinstance(parent)) or parent.metaObject().className()
        sequences = shortcut.keys() if hasattr(shortcut, "keys") else [shortcut.key()]
        context = shortcut.context()
        context = int(getattr(context, "value", context))
        shortcuts.append({"parent": place, "keys": _portable(sequences), "context": CONTEXTS.get(context, str(context)),
                          "enabled": shortcut.isEnabled()})
    shortcuts.sort(key=lambda s: (s["parent"], s["keys"], s["context"], s["enabled"]))
    return {"main_window_actions": actions, "shortcuts": shortcuts}


def record(plugin, plugin_menus, main_window, canvas, language, baseline=None, icons_dir=None):
    """What the plugin's ``initGui()`` built: ``{"language", "containers", "outside"}``.

    ``plugin_menus`` lists ``(menu name, [QAction])`` for each menu the plugin added under Plugins, in order:
    the child takes it from its iface, the real app from the Plugins menu. ``language`` is the plugin's interface
    language, as recorded. ``outside`` is None without a ``baseline`` (``outside_baseline()``, taken before the
    plugin loads). ``icons_dir`` defaults to the icons folder next to the module of the plugin's class: the tree's
    icons in the child, the installed plugin's in the real app.

    Take it once the event loop has run since ``initGui()``: a toolbar added to a visible main window stays
    hidden until its queued show runs.
    """
    if icons_dir is None:
        module = os.path.abspath(sys.modules[type(plugin).__module__].__file__)
        icons_dir = os.path.join(os.path.dirname(module), "icons")
    index = _icon_index(icons_dir)[0]
    containers = []
    _toolbar(containers, plugin.toolbar, index)
    quick = getattr(plugin, "quick_toolbar", None)
    if quick is not None and getattr(quick, "toolbar", None) is not None:
        _toolbar(containers, quick.toolbar, index)
    for name, actions in plugin_menus:
        _plugins(containers, name, actions, index)
    outside = None if baseline is None else _outside(main_window, canvas, baseline)
    return {"language": language, "containers": containers, "outside": outside}


def _recorder(kind):
    """A stand-in for ``QMessageBox.<kind>``: it records the call in ``MODALS`` and answers No."""
    from qgis.PyQt.QtWidgets import QMessageBox

    def show(*args, **kwargs):
        MODALS.append([kind] + [str(a) for a in args[1:3]])
        return QMessageBox.StandardButton.No
    return show


def _watch_modal():
    """End the child, exit code 3, when a modal window is open: offscreen nobody can answer it.

    It prints ``RESULT {"modal_window": {"class", "title", "text"}}`` first. The 200 ms timer that calls it
    also fires inside the window's own event loop.
    """
    from qgis.PyQt.QtWidgets import QApplication

    window = QApplication.activeModalWidget()
    if window is None or not window.isVisible():
        return
    text = ""
    for name in ("text", "labelText"):
        getter = getattr(window, name, None)
        if callable(getter):
            text = str(getter())
            break
    found = {"class": window.metaObject().className(), "title": window.windowTitle(), "text": text}
    print("RESULT " + json.dumps({"modal_window": found}, ensure_ascii=False), flush=True)
    sys.stdout.flush()
    os._exit(3)


def _snapshot_iface():
    """A ``FakeIface`` that also keeps each ``addPluginToMenu()`` by menu name, in order, in ``plugin_menus``."""
    from support.fake_iface import FakeIface

    class SnapshotIface(FakeIface):
        def __init__(self):
            super().__init__()
            self.plugin_menus = {}

        def addPluginToMenu(self, menu, action):
            super().addPluginToMenu(menu, action)
            self.plugin_menus.setdefault(menu, []).append(action)

    return SnapshotIface()


def main(argv=None):
    """The child driver: build the plugin, record it, print ``RESULT`` and the JSON object, end with exit code 0.

    The object holds ``record`` (``record()``), ``modals`` (the message boxes raised, each answered No),
    ``iface_mocks`` (``{name: calls}`` for each iface attribute that ``FakeIface`` answered with a MagicMock),
    ``env`` (the QGIS, Qt and Python versions, FiberQ's locale and language, the settings file) and the icon
    files: how many, and the groups that draw alike. A modal window ends the child with exit code 3
    (``_watch_modal()``).

    The child reads and writes no one's settings: it makes a fresh profile in TMPDIR (under ``run_driver`` the
    test's folder) and pins FiberQ's language to English there and in QLocale. Nothing here catches an
    exception: in the fast stage the child must die of the hidden qgis, uncaught (docs/testing.md).

    ``argv`` ``["--write", <a new file>]`` (by hand) also writes the record as a golden file.
    """
    argv = sys.argv[1:] if argv is None else argv
    if argv and (len(argv) != 2 or argv[0] != "--write"):
        sys.exit(USAGE)
    write = argv[1] if argv else None
    if write is not None and os.path.exists(write):
        sys.exit("initgui_snapshot.py: %s exists; --write writes a new file only" % write)

    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = tempfile.mkdtemp(prefix="fiberq-initgui-profile-")
    sys.path[:0] = [REPO_ROOT, TESTS]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from qgis.core import QgsApplication

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], True)
    app.initQgis()

    from qgis.core import Qgis, QgsSettings
    from qgis.PyQt.QtCore import QT_VERSION_STR, QLocale, QTimer
    from qgis.PyQt.QtWidgets import QMessageBox

    settings = QgsSettings()
    settings.setValue("FiberQ/lang", "en")
    settings.setValue("FiberQ/lang_picked", True)
    settings.sync()
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))

    for kind in ("critical", "warning", "information", "question"):
        setattr(QMessageBox, kind, staticmethod(_recorder(kind)))

    iface = _snapshot_iface()
    window, canvas = iface.mainWindow(), iface.mapCanvas()
    baseline = outside_baseline(window, canvas)
    watch = QTimer()
    watch.timeout.connect(_watch_modal)
    watch.start(200)

    import fiberq
    import fiberq.i18n
    from fiberq.main_plugin import FiberQPlugin

    # initGui() arms a 2 s one-shot schema migration; nothing here waits for it.
    FiberQPlugin._run_schema_migrations = lambda self: None
    plugin = fiberq.classFactory(iface)
    plugin.initGui()
    app.processEvents()   # the 0 ms language re-apply, as in the real app

    rec = record(plugin, list(iface.plugin_menus.items()), window, canvas, fiberq.i18n.effective_language(),
                 baseline)
    module = os.path.abspath(sys.modules[type(plugin).__module__].__file__)
    index, names = _icon_index(os.path.join(os.path.dirname(module), "icons"))
    result = {"record": rec, "modals": MODALS,
              "iface_mocks": {name: len(m.mock_calls) for name, m in sorted(iface._mocks.items())},
              "env": {"qgis": Qgis.QGIS_VERSION, "qt": QT_VERSION_STR, "python": sys.version.split()[0],
                      "current_locale": fiberq.i18n.current_locale(),
                      "effective_language": fiberq.i18n.effective_language(),
                      "settings_file": QgsSettings().fileName()},
              "icon_files": len(names),
              "icon_files_drawn_alike": sorted(group for group in index.values() if len(group) > 1)}
    print("RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
    if write is not None:
        with open(write, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(dump_golden(rec))
        print("wrote " + write, flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
