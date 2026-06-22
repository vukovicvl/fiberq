from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox
from qgis.PyQt.QtGui import QShortcut

# Phase 5.3: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


def show_hotkeys_help(iface):
    dlg = QDialog(iface.mainWindow())
    dlg.setWindowTitle("Prečice")
    lay = QVBoxLayout(dlg)
    info = QLabel(
        "<b>Standardne prečice</b><br>"
        "Ctrl+B – BOM izveštaj<br>"
        "Ctrl+G – Razgrani cables (offset)<br>"
        "Ctrl+P – Publish to PostGIS<br>"
        "Ctrl+F – Prekid vlakna (klik na trasu)<br>"
        "R – Rezerve (završna)<br>"
    )
    info.setTextFormat(Qt.TextFormat.RichText)
    lay.addWidget(info)
    lay.addWidget(QDialogButtonBox(QDialogButtonBox.StandardButton.Close))
    dlg.exec()


def register_hotkeys(plugin):
    """Povezuje globalne prečice sa akcijama plugina. Kreira shortcut-e i na glavnom prozoru i na mapi."""
    try:
        win = plugin.iface.mainWindow()
        canvas = plugin.iface.mapCanvas()
        if not hasattr(plugin, '_hk_shortcuts'):
            plugin._hk_shortcuts = []

        def add(seq, slot):
            for parent in (win, canvas):
                sc = QShortcut(QKeySequence(seq), parent)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(slot)
                plugin._hk_shortcuts.append(sc)
        if hasattr(plugin, 'apply_cable_offset'): add('Ctrl+G', plugin.apply_cable_offset)
        if hasattr(plugin, 'open_bom_dialog'): add('Ctrl+B', plugin.open_bom_dialog)
        if hasattr(plugin, 'activate_fiber_break_tool'): add('Ctrl+F', plugin.activate_fiber_break_tool)
        pub = getattr(plugin, 'open_publish_dialog', None) or getattr(plugin, 'publish_to_postgis', None)
        if callable(pub): add('Ctrl+P', pub)
        if hasattr(plugin, '_start_rezerva_interaktivno'): add('R', lambda: plugin._start_rezerva_interaktivno('zavrsna'))
        # helper: Shift+R -> mid-span slack
        if hasattr(plugin, '_start_rezerva_interaktivno'): add('Shift+R', lambda: plugin._start_rezerva_interaktivno('prolazna'))
    except Exception as e:
        logger.debug(f"Error in add: {e}")
