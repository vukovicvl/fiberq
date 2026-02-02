# -*- coding: utf-8 -*-
"""FiberQ QGIS plugin."""

def classFactory(iface):
    from .main_plugin import FiberQPlugin
    return FiberQPlugin(iface)
