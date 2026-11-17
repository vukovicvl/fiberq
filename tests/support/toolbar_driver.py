"""Build the plugin's toolbars in a child process and print what they show.

A driver for ``run_driver(folder, TOOLBAR_DRIVER)`` (``child.py``), run as a script and never imported by a
test: it starts a QgsApplication of its own, builds the plugin with ``FakeIface``, runs ``initGui()`` and
prints one line, ``RESULT`` and a JSON object with three keys:

- ``files``: each icon file in fiberq/icons/, by name, as ``drawn()`` gives it here;
- ``containers``: the FiberQ toolbar (key ``toolbar``), the Quick toolbar (``quick``), every drop-down of the
  two, nested ones included, and Plugins > FiberQ (``plugins``). Each has a ``title`` and its entries in
  order, as ``rows`` of ``[label, drawing]``: for a toolbar, each visible tool button, labelled by its
  action's text, else the button's tooltip, else its text; for a drop-down, each visible entry that is not a
  separator, labelled by its text; for Plugins > FiberQ, every action added, labelled by its text. A
  drop-down has the drawing of its button or entry as ``group`` instead of a ``key``;
- ``modals``: the message boxes that building the toolbars raised, each as its kind, title and text. Each
  answers No at once, where a real one would wait for a click until the timeout.

tests/test_toolbar_icons.py reads it.
"""
import hashlib
import json
import os
import sys

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(TESTS)

#: The message boxes raised while the toolbars were built.
MODALS = []


def modal(kind):
    """A stand-in for ``QMessageBox.<kind>``: it records the call and answers No."""
    from qgis.PyQt.QtWidgets import QMessageBox

    def show(*args, **kwargs):
        MODALS.append([kind] + [str(a) for a in args[1:3]])
        return QMessageBox.StandardButton.No
    return show


def drawn(icon):
    """What the icon draws: a digest at toolbar size and its 16 px RGBA, or None."""
    from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, QSize

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


def menu(containers, title, qmenu, group):
    """Add the drop-down ``qmenu``, and each drop-down inside it, to ``containers``."""
    rows = []
    containers.append({"title": title, "group": group, "rows": rows})
    for action in qmenu.actions():
        if action.isSeparator() or not action.isVisible():
            continue
        rows.append([action.text(), drawn(action.icon())])
        if action.menu() is not None:
            menu(containers, title + " > " + action.text(), action.menu(), drawn(action.icon()))


def toolbar(containers, title, key, bar):
    """Add the toolbar ``bar``, and each drop-down of its buttons, to ``containers``."""
    from qgis.PyQt.QtWidgets import QToolButton

    rows = []
    containers.append({"title": title, "key": key, "rows": rows})
    for action in bar.actions():
        button = bar.widgetForAction(action)
        if action.isSeparator() or not action.isVisible() or not isinstance(button, QToolButton):
            continue
        label = action.text() or button.toolTip() or button.text()
        rows.append([label, drawn(button.icon())])
        if button.menu() is not None:
            menu(containers, title + " > " + label, button.menu(), drawn(button.icon()))


def main():
    sys.path[:0] = [REPO_ROOT, TESTS]

    from qgis.core import QgsApplication

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], True)
    app.initQgis()

    from qgis.PyQt.QtGui import QIcon
    from qgis.PyQt.QtWidgets import QMessageBox

    from support.fake_iface import FakeIface

    for kind in ("critical", "warning", "information", "question"):
        setattr(QMessageBox, kind, staticmethod(modal(kind)))

    icons = os.path.join(REPO_ROOT, "fiberq", "icons")
    files = {name: drawn(QIcon(os.path.join(icons, name)))
             for name in sorted(os.listdir(icons)) if name.endswith(".svg")}

    from fiberq.main_plugin import FiberQPlugin

    # initGui() arms a 2 s one-shot schema migration; nothing here waits for it.
    FiberQPlugin._run_schema_migrations = lambda self: None
    iface = FakeIface()
    plugin = FiberQPlugin(iface)
    plugin.initGui()

    containers = []
    toolbar(containers, "FiberQ toolbar", "toolbar", plugin.toolbar)
    quick = getattr(plugin, "quick_toolbar", None)
    if quick is not None:
        toolbar(containers, "FiberQ Quick toolbar", "quick", quick.toolbar)
    containers.append({"title": "Plugins > FiberQ", "key": "plugins",
                       "rows": [[a.text(), drawn(a.icon())] for a in iface.plugin_menu]})

    print("RESULT " + json.dumps({"files": files, "containers": containers, "modals": MODALS}), flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
