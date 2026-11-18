"""Count what the plugin's ``initGui()`` and ``unload()`` leave behind, in a child process.

A driver for ``run_driver(folder, <this file>)`` (``child.py``), run as a script and never imported by a test.
It starts a QgsApplication of its own with a private settings folder, sets FiberQ's language to Serbian, so
that the plugin installs its ``sr`` catalogue, and builds the plugin with ``LifecycleIface`` the way QGIS loads
and reloads it: a new plugin object from ``fiberq.classFactory()`` for each cycle, ``initGui()``, ``unload()``,
and the reference dropped. Unlike QGIS's reload, the cycles do not re-import fiberq's modules: what a module
makes on import is made once here, and again at every reload in QGIS. It takes a snapshot of the main window
before the first cycle ("plain") and after each step, and prints one line, ``RESULT`` and a JSON object:

- ``versions``, ``options``, ``language`` (the language it set), ``effective_language`` (the language FiberQ
  says its interface is shown in) and ``settings_file``;
- ``probes``: the positive controls, taken before "plain": ``one_shot`` (a pending one-shot timer counted: 1),
  ``filter`` (an event filter, its class found by ``spy_filters()`` as the plugin's are, seen on the canvas
  viewport, installed then removed: ``[1, 0]``) and
  ``receivers`` (a slot on ``QgsProject.readProject``, connected then disconnected: ``[1, 0]``);
- ``snapshots``: one per step, in order, each ``{"label", "settled", "settle_rounds", "counts",
  "diagnostic"}``. The labels are "plain", then for each cycle n "constructed n", "initGui n", "activated n"
  (only with ``activate``), "unload n" and "released n";
- ``modals``: the message boxes raised, each as its kind, title and text. Each answers No at once;
- ``iface_mocks``: each attribute of the iface that ``FakeIface`` answered with a MagicMock, with its number of
  calls. ``LifecycleIface`` models what initGui() and unload() use, so it is empty.

``options.json`` in the folder it runs in is optional: ``{"cycles": 2, "activate": null}``. ``activate``
names a plugin method, called after each ``initGui()``, such as one that sets a map tool.

A snapshot is taken after ``settle()``, which delivers posted events and deferred deletions and collects
garbage until two rounds count the same. It never runs a delayed timer: a pending one-shot is counted, never
fired. A 0 ms one-shot is a posted call, so it runs in the first settle after it, as it runs at once in QGIS.

A window that blocks, other than the four ``QMessageBox`` functions it answers, ends the child: a 200 ms
timer, which only runs inside such a window's own event loop, prints ``RESULT {"modal_window": {"class",
"title", "text"}}`` and exits with status 3.

Nothing here catches an exception: in the fast stage the child must die of the hidden ``qgis`` uncaught, so
that its output says so (docs/testing.md).
"""
import gc
import json
import os
import sys
import tempfile
import weakref

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(TESTS)

#: The options when the folder has no options.json.
DEFAULTS = {"cycles": 2, "activate": None}

#: The language the child runs FiberQ in.
LANGUAGE = "sr"

#: The most rounds ``settle()`` takes before it records a snapshot as not settled.
SETTLE_ROUNDS = 10

#: How often the modal watcher looks, in ms.
WATCH_MS = 200

#: The message boxes raised.
MODALS = []

#: The translators installed through ``QCoreApplication.installTranslator``, as weak references.
TRANSLATORS = []

#: The classes whose ``eventFilter()`` saw the probe event, filled by ``filters_on()``.
HITS = []


def modal(kind):
    """A stand-in for ``QMessageBox.<kind>``: it records the call and answers No."""
    from qgis.PyQt.QtWidgets import QMessageBox

    def show(*args, **kwargs):
        MODALS.append([kind] + [str(a) for a in args[1:3]])
        return QMessageBox.StandardButton.No
    return show


def watch_modals():
    """Start the modal watcher, an unparented 200 ms QTimer, and return it (the caller keeps it alive)."""
    from qgis.PyQt.QtCore import QTimer
    from qgis.PyQt.QtWidgets import QApplication

    def look():
        window = QApplication.activeModalWidget()
        if window is None or not window.isVisible():
            return
        text = ""
        for name in ("text", "labelText"):   # a message box, an input or a progress dialog
            getter = getattr(window, name, None)
            if callable(getter):
                text = str(getter())
                break
        seen = {"class": window.metaObject().className(), "title": window.windowTitle(), "text": text}
        print("RESULT " + json.dumps({"modal_window": seen}), flush=True)
        sys.stdout.flush()
        os._exit(3)

    timer = QTimer()
    timer.timeout.connect(look)
    timer.start(WATCH_MS)
    return timer


def wrap_translators():
    """Record each translator installed through the class, as FiberQ installs its catalogue."""
    from qgis.PyQt.QtCore import QCoreApplication

    install = QCoreApplication.installTranslator
    remove = QCoreApplication.removeTranslator

    def installTranslator(translator):
        done = install(translator)
        if done:
            TRANSLATORS.append(weakref.ref(translator))
        return done

    def removeTranslator(translator):
        done = remove(translator)
        if done:
            TRANSLATORS[:] = [ref for ref in TRANSLATORS if ref() is not None and ref() is not translator]
        return done

    QCoreApplication.installTranslator = staticmethod(installTranslator)
    QCoreApplication.removeTranslator = staticmethod(removeTranslator)


def lifecycle_iface():
    """A ``FakeIface`` that takes back what the plugin registers, as QGIS's iface does."""
    from qgis.PyQt import sip
    from qgis.PyQt.QtWidgets import QToolBar

    from support.fake_iface import FakeIface

    class LifecycleIface(FakeIface):
        """``FakeIface`` with what unload() undoes, so that a leftover can be counted.

        - ``addToolBar`` gives a toolbar that Python owns, in the window, as QGIS's does: dropping the last
          reference deletes it, with its actions.
        - ``removePluginMenu`` takes the action out of ``plugin_menu``.
        - ``addToolBarIcon`` and ``removeToolBarIcon`` keep the ledger ``toolbar_icons``.
        - ``addDockWidget`` and ``removeDockWidget`` dock on the real window and keep the ledger ``docks``.
        """

        def __init__(self):
            super().__init__()
            self.toolbar_icons = []
            self.docks = []

        def addToolBar(self, name):
            bar = QToolBar(name)
            self._window.addToolBar(bar)
            sip.transferback(bar)
            return bar

        def removePluginMenu(self, _menu, action):
            if action in self.plugin_menu:
                self.plugin_menu.remove(action)

        def addToolBarIcon(self, action):
            self.toolbar_icons.append(action)

        def removeToolBarIcon(self, action):
            if action in self.toolbar_icons:
                self.toolbar_icons.remove(action)

        def addDockWidget(self, area, dock):
            self.docks.append(dock)
            self._window.addDockWidget(area, dock)

        def removeDockWidget(self, dock):
            if dock in self.docks:
                self.docks.remove(dock)
            self._window.removeDockWidget(dock)

    return LifecycleIface()


def is_fiberq(cls):
    """Whether ``cls`` is defined in the plugin's package."""
    module = getattr(cls, "__module__", None) or ""
    return module == "fiberq" or module.startswith("fiberq.")


def spy(cls, probe):
    """Make ``cls.eventFilter`` record the probe event and pass it on; it handles every other event as before."""
    original = cls.__dict__.get("eventFilter")
    if original is None or getattr(original, "lifecycle_spy", False):
        return

    def eventFilter(self, watched, event, _original=original, _name=cls.__name__):
        if event.type() == probe:
            HITS.append(_name)
            return False
        return _original(self, watched, event)
    eventFilter.lifecycle_spy = True
    cls.eventFilter = eventFilter


def spy_filters(probe):
    """``spy()`` every class of the plugin's that defines ``eventFilter``, in two passes.

    The first takes each QObject class of a ``fiberq`` module imported so far. The second takes each live
    QObject whose class has a ``fiberq`` class in its MRO, and every ``fiberq`` class in that MRO: it finds a
    class made inside a function, which no module holds, and a mixin that brings ``eventFilter``. Only the
    plugin's classes are patched, never QObject, QWidget or any other class of sip's.

    Run again before each snapshot: the plugin imports some modules, and makes some objects, only when it needs
    them.
    """
    from qgis.PyQt.QtCore import QObject

    for name, module in list(sys.modules.items()):
        if module is None or not (name == "fiberq" or name.startswith("fiberq.")):
            continue
        for value in list(vars(module).values()):
            if isinstance(value, type) and issubclass(value, QObject) and value.__module__ == name:
                spy(value, probe)
    for cls in {type(obj) for obj in gc.get_objects()}:   # type(), never obj.__class__: see alive()
        if issubclass(cls, QObject):
            for base in cls.__mro__:
                if is_fiberq(base):
                    spy(base, probe)


def filters_on(target, probe):
    """The spied classes whose filter on ``target`` sees the probe event, sorted."""
    from qgis.PyQt.QtCore import QCoreApplication, QEvent

    del HITS[:]
    QCoreApplication.sendEvent(target, QEvent(probe))
    return sorted(HITS)


def signal_table(obj):
    """``[(signature, bound signal)]`` for each signal of ``obj``, overloads apart, clones left out.

    A clone is the copy moc writes right after a signal with a default argument, with that argument dropped,
    as ``destroyed()`` after ``destroyed(QObject*)``; it shares the original's receivers. PyQt has no
    ``QMetaMethod.attributes()``, so a clone is known by its place: the next signal, the same name, and its
    parameter types the start of the original's. An overloaded name has each overload picked by its types.
    """
    from qgis.PyQt.QtCore import QMetaMethod

    meta = obj.metaObject()
    found = []
    original = None
    for index in range(meta.methodCount()):
        method = meta.method(index)
        if method.methodType() != QMetaMethod.MethodType.Signal:
            continue
        name = bytes(method.name()).decode()
        types = [bytes(t).decode() for t in method.parameterTypes()]
        if original is not None and original[0] == index - 1 and original[1] == name:
            if len(types) < len(original[2]) and original[2][:len(types)] == types:
                original = (index, name, original[2])
                continue
        original = (index, name, types)
        found.append((bytes(method.methodSignature()).decode(), name, types))
    names = [name for _signature, name, _types in found]
    table = []
    for signature, name, types in found:
        bound = getattr(obj, name)
        if names.count(name) > 1:
            bound = bound[types[0] if len(types) == 1 else tuple(types)]
        table.append((signature, bound))
    return table


def receivers(obj, table):
    """``{signature: receivers}`` for every signal in ``table``."""
    return {signature: obj.receivers(bound) for signature, bound in table}


def single_shots():
    """The one-shot timers pending: the children of the event dispatcher that Qt makes for each."""
    from qgis.PyQt.QtCore import QAbstractEventDispatcher

    return [c for c in QAbstractEventDispatcher.instance().children()
            if c.metaObject().className() == "QSingleShotTimer"]


def alive():
    """``(FiberQ objects alive by class name, the active QTimers that have a Python wrapper)``.

    The timers are those made in Python, and those made in C++ whose wrapper a caller holds, as ``counts()``
    holds the window's timers.
    """
    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import QObject, QTimer

    fiberq = {}
    timers = 0
    for obj in gc.get_objects():
        cls = type(obj)   # never obj.__class__, which a dead weak proxy answers with an error
        if issubclass(cls, QTimer):
            if not sip.isdeleted(obj) and obj.isActive():
                timers += 1
        elif is_fiberq(cls):
            name = cls.__name__
            if issubclass(cls, QObject) and sip.isdeleted(obj):
                name = "(deleted) " + name
            fiberq[name] = fiberq.get(name, 0) + 1
    return dict(sorted(fiberq.items())), timers


def same(a, b):
    """Whether two wrappers hold the same C++ object."""
    from qgis.PyQt import sip

    return sip.unwrapinstance(a) == sip.unwrapinstance(b)


def by_class(objects):
    """``{class: count}``: a FiberQ class by its Python name, any other by its Qt class name."""
    out = {}
    for obj in objects:
        name = type(obj).__name__ if is_fiberq(type(obj)) else obj.metaObject().className()
        out[name] = out.get(name, 0) + 1
    return dict(sorted(out.items()))


def counts(iface, tables, probe):
    """Every count of a snapshot."""
    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import QObject, QTimer
    from qgis.PyQt.QtWidgets import QAction, QDockWidget, QMenu, QShortcut, QToolBar

    window = iface.mainWindow()
    canvas = iface.mapCanvas()
    actions = window.findChildren(QAction)
    parents = [a.parent() for a in actions]
    timers = window.findChildren(QTimer)
    fiberq, python_timers = alive()
    tool = canvas.mapTool()
    return {
        "qactions": len(actions),
        "qactions_parented": sum(1 for p in parents if p is not None and same(p, window)),
        "qmenus": len(window.findChildren(QMenu)),
        "qshortcuts": len(window.findChildren(QShortcut)),
        "toolbars": len(window.findChildren(QToolBar)),
        "docks": len(window.findChildren(QDockWidget)),
        "qtimers": len(timers),
        "qtimers_active": sum(1 for t in timers if t.isActive()),
        "python_qtimers_active": python_timers,
        "pending_one_shots": len(single_shots()),
        "project_receivers": receivers(*tables["project"]),
        "canvas_receivers": receivers(*tables["canvas"]),
        "canvas_children": len(canvas.children()),
        "viewport_filters": len(filters_on(canvas.viewport(), probe)),
        "canvas_filters": len(filters_on(canvas, probe)),
        "main_window_filters": len(filters_on(window, probe)),
        "plugins_alive": fiberq.get("FiberQPlugin", 0),
        "plugin_menu_entries": len(iface.plugin_menu),
        "toolbar_icons": len(iface.toolbar_icons),
        "translators": sum(1 for ref in TRANSLATORS if ref() is not None and not sip.isdeleted(ref())),
        "map_tool": type(tool).__name__ if tool is not None else None,
        "map_tool_fiberq": tool is not None and is_fiberq(type(tool)),
        "objects_by_class": by_class(window.findChildren(QObject)),
    }


def settle(app, take):
    """Deliver posted events and deferred deletions and collect garbage, then ``take()``, until two rounds agree.

    Returns ``(what the last round took, rounds, settled)``; ``settled`` is False when ``SETTLE_ROUNDS`` rounds
    never agreed. It runs no delayed timer: ``processEvents()`` would fire the plugin's pending one-shots. A 0 ms
    one-shot is a posted call, so the first round runs it, as QGIS runs it at once.
    """
    from qgis.PyQt.QtCore import QEvent

    last = None
    for rounds in range(1, SETTLE_ROUNDS + 1):
        app.sendPostedEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()
        now = take()
        if now == last:
            return now, rounds, True
        last = now
    return last, SETTLE_ROUNDS, False


def probes(app, iface, tables, probe):
    """The positive controls: each moves one count by a known amount, and back where it can."""
    from qgis.PyQt.QtCore import QObject, QTimer

    before = len(single_shots())
    QTimer.singleShot(3600000, lambda: None)   # an hour: still pending when the child ends with os._exit()
    one_shot = len(single_shots()) - before

    class ProbeFilter(QObject):
        """An event filter of the driver's own, made inside a function, found and spied as the plugin's are."""

        def eventFilter(self, watched, event):
            return False

    # A plugin module's name, which no module in sys.modules has: only the live instance leads spy_filters() to it.
    ProbeFilter.__module__ = "fiberq.lifecycle_probe"
    seen = ProbeFilter()
    spy_filters(probe)
    viewport = iface.mapCanvas().viewport()
    viewport.installEventFilter(seen)
    filter_counts = [len(filters_on(viewport, probe))]
    viewport.removeEventFilter(seen)
    filter_counts.append(len(filters_on(viewport, probe)))

    project, table = tables["project"]
    key = [signature for signature, _bound in table if signature.startswith("readProject(")][0]

    def take():
        return receivers(project, table)[key]

    def slot(*args):
        """The probe's slot: it does nothing."""

    start = take()
    project.readProject.connect(slot)
    connected = take() - start
    project.readProject.disconnect(slot)
    after, _rounds, _settled = settle(app, take)
    return {"one_shot": one_shot, "filter": filter_counts, "receivers": [connected, after - start]}


def main():
    # A private, fresh settings folder: no user's, checkout's or other test's settings are read or written.
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = tempfile.mkdtemp(prefix="fiberq-lifecycle-profile-")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path[:0] = [REPO_ROOT, TESTS]
    options = dict(DEFAULTS)
    if os.path.exists("options.json"):
        with open("options.json", encoding="utf-8") as fh:
            options.update(json.load(fh))

    from qgis.core import Qgis, QgsApplication, QgsProject, QgsSettings

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], True)
    app.initQgis()

    from qgis.PyQt.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QEvent
    from qgis.PyQt.QtWidgets import QMessageBox

    # FiberQ's own language choice, as its language menu stores it: __init__ installs the sr catalogue.
    settings = QgsSettings()
    settings.setValue("FiberQ/lang", LANGUAGE)
    settings.setValue("FiberQ/lang_picked", True)
    settings.sync()
    for kind in ("critical", "warning", "information", "question"):
        setattr(QMessageBox, kind, staticmethod(modal(kind)))
    wrap_translators()

    iface = lifecycle_iface()
    iface.mainWindow().statusBar()   # QGIS's window has one from the start; a QMainWindow makes it on first use
    probe = QEvent.Type(QEvent.registerEventType())
    tables = {"project": (QgsProject.instance(), signal_table(QgsProject.instance())),
              "canvas": (iface.mapCanvas(), signal_table(iface.mapCanvas()))}
    watcher = watch_modals()
    found = probes(app, iface, tables, probe)
    snapshots = []

    def take():
        return counts(iface, tables, probe)

    def snapshot(label):
        spy_filters(probe)
        now, rounds, settled = settle(app, take)
        snapshots.append({"label": label, "settled": settled, "settle_rounds": rounds, "counts": now,
                          "diagnostic": {"fiberq_live": alive()[0]}})

    snapshot("plain")
    import fiberq

    for n in range(1, options["cycles"] + 1):
        spy_filters(probe)
        plugin = fiberq.classFactory(iface)
        snapshot("constructed %d" % n)
        plugin.initGui()
        snapshot("initGui %d" % n)
        if options["activate"]:
            getattr(plugin, options["activate"])()
            snapshot("activated %d" % n)
        plugin.unload()
        snapshot("unload %d" % n)
        plugin = None
        snapshot("released %d" % n)

    from fiberq.i18n import effective_language

    result = {
        "versions": {"qgis": Qgis.version(), "qt": QT_VERSION_STR, "pyqt": PYQT_VERSION_STR,
                     "python": "%d.%d.%d" % sys.version_info[:3]},
        "options": options,
        "language": LANGUAGE,
        "effective_language": effective_language(),
        "settings_file": QgsSettings().fileName(),
        "probes": found,
        "snapshots": snapshots,
        "modals": MODALS,
        "iface_mocks": {name: len(m.mock_calls) for name, m in sorted(iface._mocks.items())},
    }
    watcher.stop()
    print("RESULT " + json.dumps(result), flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
