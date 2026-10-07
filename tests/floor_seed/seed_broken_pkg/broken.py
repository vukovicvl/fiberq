"""Raises ImportError at module scope, like a Qt6-only name on Qt5."""
from qgis.PyQt.QtGui import QAction, QShortcut  # noqa: F401
