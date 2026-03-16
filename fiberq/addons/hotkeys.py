from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QShortcut

def show_hotkeys_help(iface):
    dlg = QDialog(iface.mainWindow())
    dlg.setWindowTitle("Shortcuts")
    lay = QVBoxLayout(dlg)
    info = QLabel(
        "<b>Standard Shortcuts</b><br>"
        "Ctrl+B – BOM report<br>"
        "Ctrl+G – Separate cables (offset)<br>"
        "Ctrl+P – Publish to PostGIS<br>"
        "Ctrl+F – Fiber break (click on route)<br>"
        "R – Reserves (terminal)<br>"
    )
    info.setTextFormat(Qt.RichText)
    lay.addWidget(info)
    lay.addWidget(QDialogButtonBox(QDialogButtonBox.Close))
    dlg.exec_()

def register_hotkeys(plugin):
    """Connect global shortcuts to plugin actions. Creates shortcuts on main window and map."""
    try:
        win = plugin.iface.mainWindow()
        canvas = plugin.iface.mapCanvas()
        if not hasattr(plugin, '_hk_shortcuts'):
            plugin._hk_shortcuts = []
        def add(seq, slot):
            for parent in (win, canvas):
                sc = QShortcut(QKeySequence(seq), parent)
                sc.setContext(Qt.ApplicationShortcut)
                sc.activated.connect(slot)
                plugin._hk_shortcuts.append(sc)
        if hasattr(plugin, 'separate_cables_offset'): add('Ctrl+G', plugin.separate_cables_offset)
        if hasattr(plugin, 'open_bom_dialog'): add('Ctrl+B', plugin.open_bom_dialog)
        if hasattr(plugin, 'activate_fiber_break_tool'): add('Ctrl+F', plugin.activate_fiber_break_tool)
        pub = getattr(plugin, 'open_publish_dialog', None) or getattr(plugin, 'publish_to_postgis', None)
        if callable(pub): add('Ctrl+P', pub)
        if hasattr(plugin, '_start_reserve_interactive'): add('R', lambda: plugin._start_reserve_interactive('terminal'))
        # helper: Shift+R → pass-through
        if hasattr(plugin, '_start_reserve_interactive'): add('Shift+R', lambda: plugin._start_reserve_interactive('pass-through'))
    except Exception:
        pass
