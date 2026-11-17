"""A stand-in for QGIS's ``iface``, with what the plugin's ``initGui()`` and ``unload()`` use.

It needs a running ``QgsApplication`` and imports QGIS. A child process imports it once it has started one
(``toolbar_driver.py``); a test in the pytest process has pytest-qgis's, and imports it where it needs QGIS
anyway.
"""
from unittest import mock

from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow, QToolBar


class FakeIface:
    """What initGui() and unload() really use; the rest answers with a MagicMock.

    A real main window with a map canvas in it, toolbars that belong to that window, and ``plugin_menu``, the
    actions added to Plugins > FiberQ, in order. Any other attribute is a ``MagicMock`` of its name, the same
    one each time; ``removePluginMenu`` is one of them, so nothing takes an action out of ``plugin_menu``.
    """

    def __init__(self):
        self._window = QMainWindow()
        self._canvas = QgsMapCanvas(self._window)
        self._window.setCentralWidget(self._canvas)
        self._mocks = {}
        self.plugin_menu = []

    def mainWindow(self):
        return self._window

    def mapCanvas(self):
        return self._canvas

    def addToolBar(self, name):
        return QToolBar(name, self._window)

    def addPluginToMenu(self, _menu, action):
        self.plugin_menu.append(action)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self.__dict__["_mocks"].setdefault(name, mock.MagicMock(name=name))
