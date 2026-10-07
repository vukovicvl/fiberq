"""Seeds the Qt6-only home of QAction and QShortcut.

Qt6 moved both from QtWidgets to QtGui. Importing them from QtGui works on
QGIS 3.40 and up and raises ImportError on 3.22 — and at module scope, which is
how one such line took the whole fiberq/addons package down with it.

qgis.PyQt.QtWidgets serves both stacks and is what fiberq/ui/base.py uses.
"""
from qgis.PyQt.QtGui import QAction, QShortcut  # noqa: F401

__all__ = ['QAction', 'QShortcut']
