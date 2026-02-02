# pyright: reportMissingImports=false, reportMissingModuleSource=false
from logging import root
from platform import node
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QKeySequence, QDesktopServices
import math
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QInputDialog, QDialog, QVBoxLayout, QLineEdit, QLabel,
    QDialogButtonBox, QFileDialog, QFormLayout,QCheckBox, QVBoxLayout, QHBoxLayout, QComboBox, QTreeWidget, QTreeWidgetItem, QSplitter, QHBoxLayout, QGroupBox, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsView, QGraphicsScene, QPushButton)
from qgis.core import (
    QgsVectorFileWriter, QgsCoordinateTransformContext,
    QgsVectorLayer, QgsProject, QgsField,
    QgsFeature, QgsGeometry, QgsPointXY,
    QgsWkbTypes, QgsMarkerSymbol, QgsSymbol, QgsUnitTypes,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling,
    QgsSimpleLineSymbolLayer, QgsMarkerLineSymbolLayer, QgsSvgMarkerSymbolLayer,
    QgsCoordinateTransform, QgsVectorDataProvider,QgsTextFormat, QgsTextBufferSettings, QgsSingleSymbolRenderer, Qgis, QgsSettings, QgsEditorWidgetSetup,QgsRectangle, QgsFeatureRequest 
    )
from qgis.PyQt.QtGui import QIcon, QDesktopServices, QPen, QColor, QPainterPath, QFont
import textwrap

# --- ICON LOADER (auto-added) ---
import os as _os_mod
def _icon_path(filename: str) -> str:
    return _os_mod.path.join(_os_mod.path.dirname(__file__), 'icons', filename)
def _load_icon(filename: str) -> QIcon:
    try:
        p = _icon_path(filename)
        return QIcon(p) if _os_mod.path.exists(p) else QIcon()
    except Exception:
        return QIcon()

def _map_icon_path(filename: str) -> str:
    import os as _os_mod2
    try:
        base = _os_mod2.path.dirname(__file__)
        return _os_mod2.path.join(base, 'resources', 'map_icons', filename)
    except Exception:
        return filename

# === FiberQ Language Support (toolbar SR/EN toggle) ===
try:
    from qgis.PyQt.QtCore import QSettings
except Exception:
    QSettings = None

_FIBERQ_LANG_KEY = "FiberQ/lang"

def _get_lang():
    try:
        if QSettings is None: return "en"
        return QSettings().value(_FIBERQ_LANG_KEY, "en")
    except Exception:
        return "en"

def _set_lang(lang):
    try:
        if QSettings is None: return
        QSettings().setValue(_FIBERQ_LANG_KEY, lang)
    except Exception:
        pass


# === FiberQ Pro License (locks Preview Map + Publish to PostGIS) ===
# Lightweight local unlock using QSettings.
# Users unlock once by entering a key; status persists across updates.
# (Open-source note: this is not DRM; it's a practical paywall.)

_FIBERQ_PRO_SETTINGS_ORG = "FiberQ"
_FIBERQ_PRO_SETTINGS_APP = "FiberQ"
_FIBERQ_PRO_ENABLED_KEY = "pro_enabled"

# Change this whenever you want to rotate the shared key.
_FIBERQ_PRO_MASTER_KEY = "FIBERQ-PRO-2025"


def _fiberq_is_pro_enabled() -> bool:
    try:
        if QSettings is None:
            return False
        s = QSettings(_FIBERQ_PRO_SETTINGS_ORG, _FIBERQ_PRO_SETTINGS_APP)
        return s.value(_FIBERQ_PRO_ENABLED_KEY, False, type=bool)
    except Exception:
        return False


def _fiberq_set_pro_enabled(value: bool) -> None:
    try:
        if QSettings is None:
            return
        s = QSettings(_FIBERQ_PRO_SETTINGS_ORG, _FIBERQ_PRO_SETTINGS_APP)
        s.setValue(_FIBERQ_PRO_ENABLED_KEY, bool(value))
    except Exception:
        pass


def _fiberq_validate_pro_key(key: str) -> bool:
    try:
        if not isinstance(key, str):
            return False
        k = key.strip().upper()
        # Simple shared key (Option A). Replace with your own validation later.
        return k == _FIBERQ_PRO_MASTER_KEY
    except Exception:
        return False


def _fiberq_check_pro(iface, feature_label: str = "FiberQ Pro") -> bool:
    # Returns True if Pro is enabled; otherwise prompts for a license key.
    try:
        if _fiberq_is_pro_enabled():
            return True

        res = QMessageBox.question(
            iface.mainWindow(),
            "FiberQ Pro",
            "Preview Map and Publish to PostGIS are part of FiberQ Pro.\n\nDo you want to enter a license key now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if res != QMessageBox.Yes:
            return False

        key, ok = QInputDialog.getText(
            iface.mainWindow(),
            "FiberQ Pro",
            "Enter license key:",
            QLineEdit.Normal,
            ""
        )
        if not ok:
            return False

        if _fiberq_validate_pro_key(key):
            _fiberq_set_pro_enabled(True)
            QMessageBox.information(
                iface.mainWindow(),
                "FiberQ Pro",
                "Activated! Pro options are now unlocked on this computer."
            )
            return True
        else:
            QMessageBox.warning(
                iface.mainWindow(),
                "FiberQ Pro",
                "Invalid license key."
            )
            return False
    except Exception:
        return False
# Element icon resolver

# === FiberQ i18n phrase-level translator ===
def _fiberq_translate(text: str, lang: str) -> str:
    if not isinstance(text, str):
        return text
    text = text.strip()
    # Static phrase map
    sr2en = {
        'Publish to PostGIS': 'Publish to PostGIS',
        'Završna rezerva (prečica)': 'End slack (shortcut)',
        'Razgrani kablove (offset)': 'Separate cables (offset)',
        'Show shortcuts': 'Show shortcuts',
        'BOM report (XLSX/CSV)': 'BOM report (XLSX/CSV)',
        'Check (health check)': 'Health check',
        'Cable laying': 'Cable laying',
        'Underground': 'Underground',
        'Aerial': 'Aerial',        'Main': 'Main',
        'Distribution': 'Distribution',
        'Drop': 'Drop',

        'Place extension': 'Place extension',
        'Drawings': 'Drawings',
        'Attach drawing': 'Attach drawing',
        'Open drawing (by click)': 'Open drawing (by click)',
        'Open FiberQ web': 'Open FiberQ web',
        'Selection': 'Selection',
        'Delete selected': 'Delete selected',
        'Duct infrastructure': 'Duct infrastructure',
        'Place manholes': 'Place manholes',
        'Place PE duct': 'Place PE duct',
        'Place transition duct': 'Place transition duct',
        'Import points': 'Import points',
        'Locator': 'Locator',
        'Hide locator': 'Hide locator',
        'Relations': 'Relations',
        'Latent elements list': 'Latent elements list',
        'Cut infrastructure': 'Cut infrastructure',
        'Fiber break': 'Fiber break',
        'Color catalog': 'Color catalog',
        'Save all layers to GeoPackage': 'Save all layers to GeoPackage',
        'Auto-save to GeoPackage': 'Auto-save to GeoPackage',
        'Optical schematic view': 'Optical schematic view',
        'Optical slack': 'Optical slack',
        'Add end slack (interactive)': 'Add end slack (interactive)',
        'Add thru slack (interactive)': 'Add thru slack (interactive)',
        'End slack at ends of selected cables': 'End slack at ends of selected cables',
        'Preview and export per-layer and summary': 'Preview and export per-layer and summary',
        'Export (.xlsx / .csv)': 'Export (.xlsx / .csv)',
        'By Layers': 'By Layers',
        'Summary': 'Summary',
        'Move element': 'Move elements',
        'Import image to element': 'Attach image to element',
        'Open image (by click)': 'Open image (by click)',

    }
    en2sr = {v:k for k,v in sr2en.items()}
    # Simple prefix rules
    if lang == 'en':
        if text.startswith('Place '):
            return 'Place ' + text[len('Place '):]
        return sr2en.get(text, text)
    else:
        if text.startswith('Place '):
            return 'Place ' + text[len('Place '):]
        return en2sr.get(text, text)

def _apply_text_and_tooltip(obj, lang: str):
    try:
        if hasattr(obj, 'text'):
            t = obj.text()
            nt = _fiberq_translate(t, lang)
            if nt != t:
                obj.setText(nt)
    except Exception:
        pass
    # ToolTip
    try:
        tip = obj.toolTip()
        if tip:
            ntip = _fiberq_translate(tip, lang)
            if ntip != tip:
                obj.setToolTip(ntip)
    except Exception:
        pass

def _apply_menu_language(menu, lang: str):
    try:
        # Title
        try:
            title = menu.title()
            if title:
                menu.setTitle(_fiberq_translate(title, lang))
        except Exception:
            pass
        # Actions (recursively)
        for a in menu.actions():
            try:
                _apply_text_and_tooltip(a, lang)
                sub = a.menu()
                if sub:
                    _apply_menu_language(sub, lang)
            except Exception:
                pass
    except Exception:
        pass

def _element_icon_for(name: str) -> QIcon:
    m = {
        'ODF': 'odf',
        'TB': 'tb',
        'Patch panel': 'patch_panel',
        'OTB': 'otb',
        'Indoor OTB': 'indoor_otb',
        'Outdoor OTB': 'outdoor_otb',
        'Pole OTB': 'pole_otb',
        'TO': 'to',
        'Indoor TO': 'indoor_to',
        'Outdoor TO': 'outdoor_to',
        'Pole TO': 'pole_to',
        'Joint Closure TO': 'joint_closure_to',
    }
    slug = m.get(name)
    if slug:
        return _load_icon(f'ic_place_{slug}.svg')
    return _load_icon('ic_place_elements.svg')
# --- END ICON LOADER ---

from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand, QgsMapTool, QgsVertexMarker, QgsMapToolIdentify
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QVariant, QSize, QRect
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QListWidget
import sip
import os

# === FIXED LABEL UTILITY (screen-fixed text in mm) ===
def _apply_fixed_text_label(layer, field_name='naziv', size_mu=8.0, yoff_mu=5.0):
    # Make labels fixed-size in screen millimeters, with a small offset above the point.
    # Similar to the OKNA style to avoid labels growing when zooming out.
    try:
        s = QgsPalLayerSettings()
        s.fieldName = field_name
        s.enabled = True
        # Prefer OverPoint with a small mm offset (robust for various QGIS versions)
        try:
            s.placement = getattr(QgsPalLayerSettings, 'OverPoint', s.placement)
        except Exception:
            pass
        try:
            s.xOffset = 0.0
            s.yOffset = float(yoff_mu)
            s.offsetUnits = QgsUnitTypes.RenderMapUnits
        except Exception:
            pass

        tf = QgsTextFormat()
        try:
            tf.setSize(float(size_mu))
            tf.setSizeUnit(QgsUnitTypes.RenderMapUnits)
        except Exception:
            pass

        try:
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.8)
            buf.setColor(QColor(255, 255, 255))
            tf.setBuffer(buf)
        except Exception:
            pass

        try:
            s.setFormat(tf)
        except Exception:
            pass

        layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()
    except Exception:
        # Do not crash the plugin if labeling fails on some older QGIS.
        pass



# === Pre-placement attributes dialog for point elements ===
def _normalize_name(s: str) -> str:
    try:
        import unicodedata, re
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = s.lower()
        s = re.sub(r"[^a-z0-9_]+", "_", s)
        return s.strip("_")
    except Exception:
        return s

def _default_fields_for(layer_name: str):
    """Return a list of (key, label, kind, default, options) for the dialog.
    kind: 'text' | 'int' | 'double' | 'enum' | 'year'
    """
    base = [
        ("naziv", "Name", "text", "", None),
        ("proizvodjac", "Manufacturer", "text", "", None),
        ("oznaka", "Label", "text", "", None),
        ("kapacitet", "Capacity", "int", 0, None),
        ("ukupno_kj", "Total", "int", 0, None),
        ("zahtev_kapaciteta", "Capacity Requirement", "int", 0, None),
        ("zahtev_rezerve", "Slack Requirement", "int", 0, None),
        ("oznaka_izvoda", "Outlet Label", "text", "", None),
        ("numeracija", "Numbering", "text", "", None),
        ("naziv_objekta", "Object Name", "text", "", None),
        ("adresa_ulica", "Address Street", "text", "", None),
        ("adresa_broj", "Address Number", "text", "", None),
        ("address_id", "Address ID", "text", "", None),
        ("stanje", "Status", "enum", "Planned", ["Planned", "Built", "Existing"]),
        ("godina_ugradnje", "Year of Installation", "year", 2025, None),
    ]
    ln = (layer_name or "").lower()
    if "od ormar" in ln:
        base = [(k,l,kind,(24 if k=="kapacitet" else d),opt) for (k,l,kind,d,opt) in base]
    return base


def _apply_element_aliases(layer):
    """
    English aliases for standard fields on ODF/OTB/TB/Patch panel layers.
    Does not change field names, only what user sees in attribute table.
    """
    if layer is None:
        return

    mapping = {
        "naziv":           "Name",
        "proizvodjac":     "Manufacturer",
        "oznaka":          "Label",
        "kapacitet":       "Capacity",
        "ukupno_kj":       "Total SCs",
        "zahtev_kapaciteta": "Required capacity",
        "zahtev_rezerve":  "Reserve capacity",
        "oznaka_izvoda":   "Port label",
        "numeracija":      "Numbering",
        "naziv_objekta":   "Site name",
        "adresa_ulica":    "Street",
        "adresa_broj":     "Street No.",
        "address_id":      "Address ID",
        "stanje":          "Status",
        "godina_ugradnje": "Install year",
    }

    try:
        fields = layer.fields()
    except Exception:
        return

    for fname, alias in mapping.items():
        try:
            idx = fields.indexFromName(fname)
        except Exception:
            idx = -1
        if idx != -1:
            try:
                layer.setFieldAlias(idx, alias)
            except Exception:
                pass


class PrePlaceAttributesDialog(QDialog):
    def __init__(self, layer_name: str, layer: QgsVectorLayer|None):
        super().__init__()
        self.setWindowTitle(f"Element information — {layer_name}")
        from qgis.PyQt.QtWidgets import QFormLayout, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDialogButtonBox
        form = QFormLayout(self)
        self._editors = {}
        existing = set()
        try:
            if isinstance(layer, QgsVectorLayer):
                for f in layer.fields():
                    existing.add(_normalize_name(f.name()))
        except Exception:
            pass
        fields = _default_fields_for(layer_name)
        if existing:
            kept = []
            for (key,label,kind,default,opts) in fields:
                if key == "naziv" or key in existing:
                    kept.append((key,label,kind,default,opts))
            fields = kept
        try:
            from datetime import datetime as _dt
            current_year = _dt.now().year
        except Exception:
            current_year = 2025
        for (key,label,kind,default,opts) in fields:
            if kind == "enum":
                w = QComboBox(); 
                try: w.addItems(opts or [])
                except Exception: pass
                try: w.setCurrentText(str(default))
                except Exception: pass
            elif kind == "int" or kind == "year":
                w = QSpinBox(); 
                try:
                    w.setRange(0, 999999)
                    w.setValue(int(current_year if kind=="year" and (default in (None,0,"")) else default or 0))
                except Exception: pass
            elif kind == "double":
                w = QDoubleSpinBox();
                try:
                    w.setDecimals(3); w.setRange(-1e9, 1e9); w.setValue(float(default or 0))
                except Exception: pass
            else:
                w = QLineEdit(); 
                try: w.setText(str(default or ""))
                except Exception: pass
            form.addRow(label, w)
            self._editors[key]=w

        bb = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel, parent=self)
        form.addRow(bb)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

    def values(self) -> dict:
        out = {}
        from qgis.PyQt.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit
        for key, w in self._editors.items():
            try:
                if isinstance(w, QComboBox):
                    out[key] = w.currentText()
                elif isinstance(w, QSpinBox):
                    out[key] = int(w.value())
                elif isinstance(w, QDoubleSpinBox):
                    out[key] = float(w.value())
                else:
                    out[key] = w.text()
            except Exception:
                pass
        return out

# === DEFINICIJE ELEMENATA ZA POLAGANJE ===
ELEMENT_DEFS = [
    {"name": "ODF", "symbol": {"svg_path": _map_icon_path("map_odf.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "TB", "symbol": {"svg_path": _map_icon_path("map_tb.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Patch panel", "symbol": {"svg_path": _map_icon_path("map_patch_panel.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "OTB", "symbol": {"svg_path": _map_icon_path("map_otb.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Indoor OTB", "symbol": {"svg_path": _map_icon_path("map_place_otb_indoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Outdoor OTB", "symbol": {"svg_path": _map_icon_path("map_place_otb_outdoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Pole OTB", "symbol": {"svg_path": _map_icon_path("map_place_otb_pole.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "TO", "symbol": {"svg_path": _map_icon_path("map_place_to.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Indoor TO", "symbol": {"svg_path": _map_icon_path("map_place_to_indoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Outdoor TO", "symbol": {"svg_path": _map_icon_path("map_place_to_outdoor.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Pole TO", "symbol": {"svg_path": _map_icon_path("map_place_to_pole.svg"), "size": "10", "size_unit": "MapUnit"}},
    {"name": "Joint Closure TO", "symbol": {"svg_path": _map_icon_path("map_place_to_joint_closure.svg"), "size": "10", "size_unit": "MapUnit"}},
]
NASTAVAK_DEF = {"name": "Joint Closures", "symbol": {"name": "diamond", "color": "red", "size": "5", "size_unit": "MapUnit"}}
# === UI GROUPS (modular menus/buttons) ===
class RoutingUI:
    """
    Grupise sve akcije vezane za trasiranje u jedan drop-down.
    Ne menja logiku; samo kreira akcije/meni i povezuje na postojece metode core-a.
    """
    def __init__(self, core):
        from qgis.PyQt.QtWidgets import QMenu, QToolButton
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Add pole
        icon_add = _load_icon('ic_add_pole.svg')
        core.action_add = QAction(icon_add, 'Add pole', core.iface.mainWindow())
        core.action_add.triggered.connect(core.activate_point_tool)
        core.actions.append(core.action_add)
        self.menu.addAction(core.action_add)

        # Create route
        icon_trasa = _load_icon('ic_create_route.svg')
        core.action_trasa = QAction(icon_trasa, 'Create route', core.iface.mainWindow())
        core.action_trasa.triggered.connect(core.create_route)
        core.actions.append(core.action_trasa)
        self.menu.addAction(core.action_trasa)

        # Merge selected routes
        icon_spoji = _load_icon('ic_merge_selected_routes.svg')
        core.action_spoji = QAction(icon_spoji, 'Merge selected routes', core.iface.mainWindow())
        core.action_spoji.triggered.connect(core.merge_all_routes)
        core.actions.append(core.action_spoji)
        self.menu.addAction(core.action_spoji)

        # Import route from file
        icon_import = _load_icon('ic_import_route_from_file.svg')
        core.action_import = QAction(icon_import, 'Import route from file', core.iface.mainWindow())
        core.action_import.triggered.connect(core.import_route_from_file)
        core.actions.append(core.action_import)
        self.menu.addAction(core.action_import)

        # Add breakpoint
        icon_lomna = _load_icon('ic_add_breakpoint.svg')
        core.action_lomna = QAction(icon_lomna, 'Add breakpoint', core.iface.mainWindow())
        core.action_lomna.triggered.connect(core.activate_breakpoint_tool)
        core.actions.append(core.action_lomna)
        self.menu.addAction(core.action_lomna)

        # Create route manually
        icon_rucna = _load_icon('ic_create_route_manually.svg')
        core.action_rucna = QAction(icon_rucna, 'Create a route manually', core.iface.mainWindow())
        core.action_rucna.triggered.connect(core.activate_manual_route_tool)
        core.actions.append(core.action_rucna)
        self.menu.addAction(core.action_rucna)

        # Change route type
        icon_edit_tip_trase = _load_icon('ic_change_route_type.svg')
        core.action_edit_tip_trase = QAction(icon_edit_tip_trase, 'Change route type', core.iface.mainWindow())
        core.action_edit_tip_trase.triggered.connect(core.change_route_type)
        core.actions.append(core.action_edit_tip_trase)
        self.menu.addAction(core.action_edit_tip_trase)

        # Route correction
        icon_korekcija = _load_icon('ic_route_correction.svg')
        core.action_korekcija = QAction(icon_korekcija, 'Route correction', core.iface.mainWindow())
        core.action_korekcija.triggered.connect(core.check_consistency)
        core.actions.append(core.action_korekcija)
        self.menu.addAction(core.action_korekcija)

        # Dugme
        self.button = QToolButton()
        self.button.setText('Routing')
        self.button.setPopupMode(QToolButton.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(_load_icon('ic_routing.svg'))
        self.button.setToolTip('Routing')
        self.button.setStatusTip('Routing')
        core.toolbar.addWidget(self.button)


    # === AUTO-ADDED: Auto-save to GeoPackage (methods) ===
    def _project_gpkg_path(self):
        try:
            val = QgsProject.instance().readEntry("TelecomPlugin", "gpkg_path", "")[0]
            return val or ""
        except Exception:
            return ""

    def _set_project_gpkg_path(self, path):
        try:
            QgsProject.instance().writeEntry("TelecomPlugin", "gpkg_path", path or "")
        except Exception:
            pass

    def _is_memory_vector(self, lyr):
        try:
            if not isinstance(lyr, QgsVectorLayer):
                return False
            prov = ""
            try:
                prov = lyr.dataProvider().name().lower()
            except Exception:
                pass
            st = ""
            try:
                st = (lyr.storageType() or "").lower()
            except Exception:
                pass
            return ('memory' in prov) or st.startswith('memory')
        except Exception:
            return False

    def _toggle_auto_gpkg(self, enabled):
        prj = QgsProject.instance()
        if enabled:
            gpkg = self._project_gpkg_path()
            if not gpkg:
                default_dir = os.path.dirname(prj.fileName()) if prj.fileName() else os.path.expanduser("~")
                gpkg, _ = QFileDialog.getSaveFileName(self.core.iface.mainWindow(), "Izaberi GeoPackage fajl za auto-snimanje", os.path.join(default_dir, "Telecom.gpkg"), "GeoPackage (*.gpkg)")
                if not gpkg:
                    try:
                        self.core.action_auto_gpkg.blockSignals(True)
                        self.core.action_auto_gpkg.setChecked(False)
                        self.core.action_auto_gpkg.blockSignals(False)
                    except Exception:
                        pass
                    return
                if not gpkg.lower().endswith(".gpkg"):
                    gpkg += ".gpkg"
                self._set_project_gpkg_path(gpkg)

            # immediately convert existing memory layers
            layers = [l for l in prj.mapLayers().values() if isinstance(l, QgsVectorLayer)]
            for lyr in layers:
                if self._is_memory_vector(lyr):
                    _telecom_export_one_layer_to_gpkg(lyr, self._project_gpkg_path(), self.core.iface)

            # connect signal
            try:
                prj.layerWasAdded.connect(self._on_layer_added_auto_gpkg)
            except Exception:
                pass
            try:
                self.core.iface.messageBar().pushSuccess("Auto GPKG", "Autosave on GeoPackage.")
            except Exception:
                pass
        else:
            try:
                prj.layerWasAdded.disconnect(self._on_layer_added_auto_gpkg)
            except Exception:
                pass
            try:
                self.core.iface.messageBar().pushInfo("Auto GPKG", "Autosave off.")
            except Exception:
                pass

    def _on_layer_added_auto_gpkg(self, lyr):
        try:
            if not isinstance(lyr, QgsVectorLayer):
                return
            if self._is_memory_vector(lyr):
                gpkg = self._project_gpkg_path()
                if not gpkg:
                    return
                _telecom_export_one_layer_to_gpkg(lyr, gpkg, self.core.iface)
        except Exception:
            pass


class OpenDrawingMapTool(QgsMapToolIdentify):
    """
    Map tool: click an element to open its attached drawing (DWG/DXF) in the OS default app.
    Right click or ESC cancels the command.
    """
    def __init__(self, core):
        from qgis.PyQt.QtCore import Qt
        super().__init__(core.iface.mapCanvas())
        self.core = core
        self._Qt = Qt
        self.setCursor(Qt.PointingHandCursor)

    def _cancel(self):
        try:
            self.core.iface.mapCanvas().unsetMapTool(self)
        except Exception:
            pass
        try:
            self.core.iface.messageBar().pushInfo("Drawing", "Command cancelled.")
        except Exception:
            pass

    def canvasReleaseEvent(self, e):
        # Right click = exit tool
        try:
            if e.button() == self._Qt.RightButton:
                self._cancel()
                return
        except Exception:
            pass

        # Left click = identify + open drawing if exists
        res = self.identify(e.x(), e.y(), self.TopDownAll, self.VectorLayer)
        if not res:
            QMessageBox.information(self.core.iface.mainWindow(), "Drawing", "You did not click on any feature.")
            return

        for hit in res:
            layer = hit.mLayer
            fid = hit.mFeature.id()
            path = self.core._drawing_get(layer, fid)
            if path:
                ids = self.core._drawing_layers_get(layer, fid)

                # Legacy: ako nema ids (stari projekti), samo otvori
                if not ids:
                    self.core._open_drawing_path(path)
                    return

                # Open only if at least one of those DWG layers is still in the project
                root = QgsProject.instance().layerTreeRoot()

                def _node_present_and_visible(lid: str) -> bool:
                    node = root.findLayer(lid)  # search in Layers panel
                    if node is None:
                        return False
                    # If the group/layer is disabled (invisible), treat as "not loaded"
                    try:
                        return node.isVisible()
                    except Exception:
                        try:
                            return node.itemVisibilityChecked()
                        except Exception:
                            return True

                any_loaded = any(_node_present_and_visible(lid) for lid in ids) 

                if not any_loaded:
                    QMessageBox.information(self.core.iface.mainWindow(), "Drawing",
                                "This drawing is linked, but its DWG/DXF layer is not loaded in the project anymore (layer was removed).")
                    return

                self.core._open_drawing_path(path)
                return


    def keyPressEvent(self, e):
        # ESC = exit tool
        try:
            if e.key() == self._Qt.Key_Escape:
                self._cancel()
                return
        except Exception:
            pass
        try:
            super().keyPressEvent(e)
        except Exception:
            pass


class DrawingsUI:
    """
    Drop-down 'Crteži' sa akcijama: 'Dodaj crtež' i 'Otvori crtež (klikom)'.
    """
    def __init__(self, core):
        from qgis.PyQt.QtWidgets import QMenu, QToolButton
        self.core = core
        self.menu = QMenu("Drawings", core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        act_add = QAction(_load_icon('ic_add_drawing.svg'), "Add drawing…", core.iface.mainWindow())
        act_add.triggered.connect(core.ui_add_drawing)
        self.menu.addAction(act_add)

        act_open = QAction(_load_icon('ic_drawing.svg'), "Open drawing (by click)", core.iface.mainWindow())
        act_open.triggered.connect(core.ui_open_drawing_click)
        self.menu.addAction(act_open)

        # Dugme
        self.button = QToolButton()
        self.button.setText("Drawings")
        self.button.setPopupMode(QToolButton.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(_load_icon('ic_drawing.svg'))
        self.button.setToolTip('Drawings')
        self.button.setStatusTip('Drawings')
        core.toolbar.addWidget(self.button)
class CableLayingUI:
    """
    Existing drop-down 'Lay cable' extracted to separate class.
    """
    def __init__(self, core):
        from qgis.PyQt.QtWidgets import QMenu, QToolButton
        self.core = core
        self.menu_cables = QMenu("Cable laying", core.iface.mainWindow())
        self.menu_cables.setToolTipsVisible(True)

        # Podzemni
        self.menu_underground = QMenu("Underground", self.menu_cables)
        self.menu_underground.setIcon(_load_icon('ic_cable_underground.svg'))
        act_pg = QAction(_load_icon('ic_underground_backbone.svg'), "Backbone", core.iface.mainWindow()); act_pg.triggered.connect(lambda: core.lay_cable_by_type("podzemni", "glavni")); self.menu_underground.addAction(act_pg)
        act_pd = QAction(_load_icon('ic_underground_distributive.svg'), "Distributive", core.iface.mainWindow()); act_pd.triggered.connect(lambda: core.lay_cable_by_type("podzemni", "distributivni")); self.menu_underground.addAction(act_pd)
        act_pr = QAction(_load_icon('ic_underground_drop.svg'), "Drop", core.iface.mainWindow()); act_pr.triggered.connect(lambda: core.lay_cable_by_type("podzemni", "razvodni")); self.menu_underground.addAction(act_pr)

        # Vazdušni
        self.menu_aerial = QMenu("Aerial", self.menu_cables)
        self.menu_aerial.setIcon(_load_icon('ic_cable_aerial.svg'))
        act_vg = QAction(_load_icon('ic_aerial_backbone.svg'), "Backbone", core.iface.mainWindow()); act_vg.triggered.connect(lambda: core.lay_cable_by_type("vazdusni", "glavni")); self.menu_aerial.addAction(act_vg)
        act_vd = QAction(_load_icon('ic_aerial_distributive.svg'), "Distributive", core.iface.mainWindow()); act_vd.triggered.connect(lambda: core.lay_cable_by_type("vazdusni", "distributivni")); self.menu_aerial.addAction(act_vd)
        act_vr = QAction(_load_icon('ic_aerial_drop.svg'), "Drop", core.iface.mainWindow()); act_vr.triggered.connect(lambda: core.lay_cable_by_type("vazdusni", "razvodni")); self.menu_aerial.addAction(act_vr)

        self.menu_cables.addMenu(self.menu_underground)
        self.menu_cables.addMenu(self.menu_aerial)

        self.btn_cables = QToolButton()
        self.btn_cables.setText("Cable laying")
        self.btn_cables.setPopupMode(QToolButton.InstantPopup)
        self.btn_cables.setMenu(self.menu_cables)
        self.btn_cables.setIcon(_load_icon('ic_laying_cable.svg'))
        self.btn_cables.setToolTip('Cable laying')
        self.btn_cables.setStatusTip('Cable laying')
        core.toolbar.addWidget(self.btn_cables)



class PolaganjeElemenataUI:
    """Drop-down za polaganje elemenata (tačaka) na trasi."""
    def __init__(self, core):
        from qgis.PyQt.QtWidgets import QMenu, QToolButton
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Existing 'Place Joint Closure'
        action_nast = QAction(_load_icon('ic_place_jc.svg'), 'Place Joint Closure', core.iface.mainWindow())
        action_nast.triggered.connect(core.activate_extension_tool)
        core.actions.append(action_nast)
        self.menu.addAction(action_nast)

        self.menu.addSeparator()
        # Novi elementi iz mape
        self.element_actions = []
        for edef in ELEMENT_DEFS:
            a = QAction(_element_icon_for(edef['name']), f"Place {edef['name']}", core.iface.mainWindow())
            a.triggered.connect(lambda _=False, n=edef['name'], s=edef.get('symbol'): core.activate_place_element_tool(n, s))
            self.menu.addAction(a)
            self.element_actions.append(a)
            core.actions.append(a)

        self.button = QToolButton()
        self.button.setText('Placing elements')
        self.button.setPopupMode(QToolButton.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(_load_icon('ic_place_elements.svg'))
        self.button.setToolTip('Placing elements')
        self.button.setStatusTip('Placing elements')
        core.toolbar.addWidget(self.button)

class DuctInfrastructureUI:
    """Drop-down 'Kanalizacija' sa akcijom 'Polaganje okana'."""
    def __init__(self, core):
        from qgis.PyQt.QtWidgets import QMenu, QToolButton
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        act = QAction(_load_icon('ic_place_manholes.svg'), "Placing manholes", core.iface.mainWindow())
        act.triggered.connect(core.open_okno_workflow)
        self.menu.addAction(act)
        core.actions.append(act)

        # === NOVO: Cevi ===
        act_pe = QAction(_load_icon('ic_place_pe_pipe.svg'), "Place PE pipe", core.iface.mainWindow())
        act_pe.triggered.connect(core.open_pe_cev_workflow)
        self.menu.addAction(act_pe)
        core.actions.append(act_pe)

        act_pr = QAction(_load_icon('ic_place_transition_pipe.svg'), "Place transition pipe", core.iface.mainWindow())
        act_pr.triggered.connect(core.open_prelazna_cev_workflow)
        self.menu.addAction(act_pr)
        core.actions.append(act_pr)

        self.button = QToolButton()
        self.button.setText("Ducting")
        self.button.setPopupMode(QToolButton.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(_load_icon('ic_ducting.svg'))
        self.button.setToolTip('Ducting')
        self.button.setStatusTip('Ducting')
        core.toolbar.addWidget(self.button)


class SelectionUI:
    """
    Selection group – added options:
    - Smart selection (multiple layers)
    - Clear selection (without deleting objects)
    - Delete selected (existing behavior)
    """
    def __init__(self, core):
        from qgis.PyQt.QtWidgets import QMenu, QToolButton
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Pametna selekcija
        icon_sel = _load_icon('ic_selection.svg')
        core.action_smart_select = QAction(icon_sel, 'Smart selection (Multiple Layers)', core.iface.mainWindow())
        core.action_smart_select.triggered.connect(core.activate_smart_select_tool)
        core.actions.append(core.action_smart_select)
        self.menu.addAction(core.action_smart_select)

        # Clear selection (only removes selection from all layers)
        core.action_clear_selection = QAction(icon_sel, 'Clear selection', core.iface.mainWindow())
        core.action_clear_selection.triggered.connect(core.clear_all_selections)
        core.actions.append(core.action_clear_selection)
        self.menu.addAction(core.action_clear_selection)

        # Delete selected (existing behavior)
        icon_del = _load_icon('ic_delete_selected.svg')
        core.action_del = QAction(icon_del, 'Delete selected', core.iface.mainWindow())
        core.action_del.triggered.connect(core.obrisi_selektovane)
        core.actions.append(core.action_del)
        self.menu.addAction(core.action_del)

        self.button = QToolButton()

        self.button.setText('Selection')
        self.button.setPopupMode(QToolButton.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setIcon(_load_icon('ic_selection.svg'))
        self.button.setToolTip('Selection')
        self.button.setStatusTip('Selection')
        core.toolbar.addWidget(self.button)

# internal values that are written to the "tip_trase" field
TRASA_TYPE_OPTIONS = ["vazdusna", "podzemna", "kroz objekat"]

# labels for display in dialog (user view)
TRASA_TYPE_LABELS = {
    "vazdusna": "Aerial",
    "podzemna": "Underground",
    "kroz objekat": "Through the object",
}

# reverse mapping: EN label -> SR code
TRASA_LABEL_TO_CODE = {v: k for k, v in TRASA_TYPE_LABELS.items()}



# === BOM Izveštaj dijalog ===
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QHBoxLayout, QFileDialog, QLabel
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes, QgsUnitTypes, QgsCoordinateTransform,
    QgsCoordinateReferenceSystem, QgsDistanceArea, QgsCoordinateTransformContext
)

class _BOMDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("BOM report (XLSX/CSV)")
        self.resize(820, 520)

        self.tabs = QTabWidget(self)
        self.tab_layers = QWidget(self)
        self.tab_summary = QWidget(self)

        self.tabs.addTab(self.tab_layers, "By Layers")
        self.tabs.addTab(self.tab_summary, "Summary")

        # By layers table
        self.tbl_layers = QTableWidget(self.tab_layers)
        self.tbl_layers.setColumnCount(6)
        self.tbl_layers.setHorizontalHeaderLabels([
            "Layer", "Type", "Number of elements", "Length [m]", "Slack [m]", "Total [m]"
        ])
        self.tbl_layers.horizontalHeader().setStretchLastSection(True)

        v1 = QVBoxLayout(self.tab_layers)
        v1.addWidget(self.tbl_layers)

        # Summary
        self.lbl_summary = QLabel(self.tab_summary)
        self.lbl_summary.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v2 = QVBoxLayout(self.tab_summary)
        v2.addWidget(self.lbl_summary)

        # Buttons
        btn_export = QPushButton("Export (.xlsx / .csv)", self)
        btn_export.clicked.connect(self._export)

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)
        root.addWidget(btn_export)

        # build data now
        self._build()

    def apply_language(self, lang: str):
        try:
            self.setWindowTitle(_fiberq_translate("BOM report (XLSX/CSV)", lang))
            self.tabs.setTabText(0, _fiberq_translate("By Layers", lang))
            self.tabs.setTabText(1, _fiberq_translate("Summary", lang))
            try:
                # Header labels
                hs = [
                    _fiberq_translate("Layer", lang),
                    _fiberq_translate("Type", lang),
                    _fiberq_translate("Number of elements", lang),
                    _fiberq_translate("Length [m]", lang),
                    _fiberq_translate("Slack [m]", lang),
                    _fiberq_translate("Total [m]", lang),
                ]
                self.tbl_layers.setHorizontalHeaderLabels(hs)
            except Exception:
                pass
            # Export button (last widget in root layout)
            try:
                for i in range(self.layout().count()-1, -1, -1):
                    w = self.layout().itemAt(i).widget()
                    if isinstance(w, QPushButton):
                        w.setText(_fiberq_translate("Export (.xlsx / .csv)", lang))
                        break
            except Exception:
                pass
        except Exception:
            pass



    def _distance_area(self):
        d = QgsDistanceArea()
        try:
            d.setSourceCrs(self.iface.mapCanvas().mapSettings().destinationCrs(),
                           QgsProject.instance().transformContext())
        except Exception:
            try:
                d.setSourceCrs(QgsProject.instance().crs(),
                               QgsProject.instance().transformContext())
            except Exception:
                pass
        d.setEllipsoid(QgsProject.instance().ellipsoid())
        return d

    def _build(self):
        project = QgsProject.instance()
        layers = [l for l in project.mapLayers().values() if isinstance(l, QgsVectorLayer)]
        d = self._distance_area()

        rows = []
        totals = {
            "line_len": 0.0,
            "line_slack": 0.0,
            "line_total": 0.0,
            "points": 0
        }

        for lyr in layers:
            try:
                gtype = lyr.geometryType()
            except Exception:
                continue

            # Gather stats
            feat_count = 0
            length_m = 0.0
            slack_m = 0.0

            # attribute names tolerant (latin/serbian variations)
            attr_duz = None
            attr_slack = None
            for f in lyr.fields():
                n = f.name().lower()
                if n in ("duzina_m", "dužina_m", "duzina", "dužina", "length_m", "len_m"):
                    attr_duz = f.name()
                if n in ("slack_m", "slack", "rezerva_m", "rezerve_m"):
                    attr_slack = f.name()

            for f in lyr.getFeatures():
                feat_count += 1
                if gtype == QgsWkbTypes.LineGeometry:
                    # prefer attribute duzina if it exists and >0, else compute geometry
                    val_len = None
                    if attr_duz is not None:
                        try:
                            val_len = float(f[attr_duz]) if f[attr_duz] is not None else None
                        except Exception:
                            val_len = None
                    if val_len is None or not (val_len >= 0):
                        try:
                            geom = f.geometry()
                            if geom is not None:
                                val_len = d.measureLength(geom)
                        except Exception:
                            val_len = 0.0
                    length_m += (val_len or 0.0)

                    if attr_slack is not None:
                        try:
                            slack_m += float(f[attr_slack] or 0.0)
                        except Exception:
                            pass
                elif gtype == QgsWkbTypes.PointGeometry:
                    # nothing to compute; just counting
                    pass

            if gtype == QgsWkbTypes.LineGeometry:
                total_m = length_m + slack_m
                rows.append([lyr.name(), "Line", feat_count, length_m, slack_m, total_m])
                totals["line_len"] += length_m
                totals["line_slack"] += slack_m
                totals["line_total"] += total_m
            elif gtype == QgsWkbTypes.PointGeometry:
                rows.append([lyr.name(), "Point", feat_count, "", "", ""])
                totals["points"] += feat_count
            else:
                # ignore polygonal for now
                continue

        # fill table
        self.tbl_layers.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem("" if val is None else (f"{val:.3f}" if isinstance(val, float) else str(val)))
                if c in (3,4,5):  # numeric align right
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_layers.setItem(r, c, item)

        # summary text
        s = textwrap.dedent(f"""
        <b>Total</b><br>
        Total length of lines: <b>{totals['line_len']:.3f} m</b><br>
        Total slack (reserves): <b>{totals['line_slack']:.3f} m</b><br>
        Line + slack: <b>{totals['line_total']:.3f} m</b><br>
        Total number of point elements: <b>{totals['points']}</b>
        """).strip()
        self.lbl_summary.setText(s)
        self._rows = rows
        self._totals = totals

    def _export(self):
        # prefer XLSX if xlsxwriter is available
        has_xlsx = False
        try:
            import xlsxwriter  # noqa: F401
            has_xlsx = True
        except Exception:
            has_xlsx = False

        if has_xlsx:
            path, _ = QFileDialog.getSaveFileName(self, "Save as", "", "Excel (*.xlsx);;CSV (*.csv)")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Save as", "", "CSV (*.csv);;Excel (*.xlsx)")
        if not path:
            return

        p = path.lower()
        if p.endswith(".xlsx") and has_xlsx:
            self._export_xlsx(path)
        else:
            if not p.endswith(".csv"):
                path = path + ".csv"
            self._export_csv(path)

    def _export_csv(self, path):
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Layer", "Type", "Number", "Length_m", "Slack_m", "Total_m"])
            for row in self._rows:
                w.writerow(row)
            # add a blank and totals
            w.writerow([])
            t = self._totals
            w.writerow(["TOTAL","", t["points"], t["line_len"], t["line_slack"], t["line_total"]])
        QMessageBox.information(self, "Export", f"CSV exported:\n{path}")

    def _export_xlsx(self, path):
        import xlsxwriter
        wb = xlsxwriter.Workbook(path)
        ws = wb.add_worksheet("By layers")
        headers = ["Layer", "Type", "Number", "Length_m", "Slack_m", "Total_m"]
        for c,h in enumerate(headers):
            ws.write(0,c,h)
        for r,row in enumerate(self._rows, start=1):
            for c,val in enumerate(row):
                ws.write(r,c,val)
        # totals sheet
        ws2 = wb.add_worksheet("Total")
        t = self._totals
        ws2.write(0,0,"Total length of lines [m]"); ws2.write(0,1, t["line_len"])
        ws2.write(1,0,"Total slack [m]"); ws2.write(1,1, t["line_slack"])
        ws2.write(2,0,"Line + slack [m]"); ws2.write(2,1, t["line_total"])
        ws2.write(3,0,"Total number of point elements"); ws2.write(3,1, t["points"])
        wb.close()
        QMessageBox.information(self, "Export", f"XLSX exported:\n{path}")

class FiberQPlugin:
    def _ensure_plugin_svg_search_path(self):
        """Ensure plugin SVG icons resolve (styles may reference only filenames)."""
        try:
            from qgis.core import QgsApplication
            import os
            svg_dir = os.path.join(os.path.dirname(__file__), 'resources', 'map_icons')
            paths = list(QgsApplication.svgPaths() or [])
            if svg_dir and os.path.isdir(svg_dir) and svg_dir not in paths:
                QgsApplication.setSvgPaths(paths + [svg_dir])
        except Exception:
            pass



    def _fiberq_apply_language(self, lang):

        """Apply language to toolbar actions, drop-down menus, and common dialogs."""
        try:
            self._fiberq_lang = lang
        except Exception:
            pass

        # 1) Translate known QAction objects collected in self.actions (text + tooltip)
        try:
            for a in getattr(self, 'actions', []) or []:
                _apply_text_and_tooltip(a, lang)
        except Exception:
            pass

        # Also translate individual top-level actions not stored in the list (defensive)
        for name in [
            'action_publish_pg','action_rezerva_quick','action_branch','action_hotkeys',
            'action_bom','action_health_check','action_schematic','action_import_points',
            'action_locator','action_clear_locator','action_relations','action_latent_list',
            'action_fiber_break','action_color_catalog','action_save_gpkg','action_auto_gpkg'
        ]:
            try:
                a = getattr(self, name, None)
                if a: _apply_text_and_tooltip(a, lang)
            except Exception:
                pass

        # 2) Translate drop-down menus and buttons from UI groups if present
        for group_name in ['ui_drawings','ui_cables','ui_placement','ui_ducts','ui_selection','ui_reserves']:
            try:
                grp = getattr(self, group_name, None)
                if not grp: 
                    continue
                # menu title + actions
                if hasattr(grp, 'menu') and grp.menu:
                    _apply_menu_language(grp.menu, lang)
                if hasattr(grp, 'menu_cables') and grp.menu_cables:
                    _apply_menu_language(grp.menu_cables, lang)
                if hasattr(grp, 'menu_underground') and grp.menu_underground:
                    _apply_menu_language(grp.menu_underground, lang)
                if hasattr(grp, 'menu_aerial') and grp.menu_aerial:
                    _apply_menu_language(grp.menu_aerial, lang)
                # toolbar button text/tooltip
                if hasattr(grp, 'button') and grp.button:
                    _apply_text_and_tooltip(grp.button, lang)
                if hasattr(grp, 'btn_cables') and grp.btn_cables:
                    _apply_text_and_tooltip(grp.btn_cables, lang)
            except Exception:
                pass

        # 3) Update language toggle caption/tooltip
        try:
            if hasattr(self, '_fiberq_lang_action') and self._fiberq_lang_action:
                self._fiberq_lang_action.setText('EN' if lang=='sr' else 'SR')
                self._fiberq_lang_action.setToolTip(
                    'Promeni jezik interfejsa na engleski' if lang=='sr' else 'Switch UI language to Serbian'
                )
        except Exception:
            pass

        # 4) Store preference
        try:
            _set_lang(lang)
        except Exception:
            pass


    def _fiberq_toggle_language(self):
        lang = getattr(self, '_fiberq_lang', None) or _get_lang()
        lang = 'en' if lang == 'sr' else 'sr'
        _set_lang(lang)
        self._fiberq_apply_language(lang)
    # === BOM: otvori dijalog ===
    def open_bom_dialog(self):
        try:
            dlg = _BOMDialog(self.iface, parent=self.iface.mainWindow())
            try:
                dlg.apply_language(_get_lang())
            except Exception:
                pass
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "BOM report", f"Error: {e}")
    
    # === LOKATOR: pomoćne metode ===
    def open_locator_dialog(self):
        # Open dialog for entering address and centering the map.
        try:
            dlg = LocatorDialog(self)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Locator", f"Error opening locator: {e}")

    def _center_and_mark_wgs84(self, lon, lat, label=None):
        # Move map to given WGS84 coordinates (lon, lat) and set marker.
        canvas = self.iface.mapCanvas()
        try:
            from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
            wgs84 = QgsCoordinateReferenceSystem(4326)
            dest = canvas.mapSettings().destinationCrs()
            xform = QgsCoordinateTransform(wgs84, dest, QgsProject.instance())
            pt = xform.transform(QgsPointXY(lon, lat))
        except Exception:
            pt = QgsPointXY(lon, lat)

        # Centriraj i približi
        try:
            canvas.setCenter(pt)
            canvas.zoomScale(1500)
            canvas.refresh()
        except Exception:
            pass

        # Mark with marker (remove previous if exists)
        try:
            if hasattr(self, "_locator_marker") and self._locator_marker is not None:
                try:
                    self.iface.mapCanvas().scene().removeItem(self._locator_marker)
                except Exception:
                    try:
                        self._locator_marker.hide()
                    except Exception:
                        pass
                self._locator_marker = None

            m = QgsVertexMarker(canvas)
            m.setCenter(pt)
            m.setIconType(QgsVertexMarker.ICON_CROSS)
            m.setIconSize(18)
            m.setPenWidth(3)
            try:
                m.setColor(QColor(255, 0, 0))
            except Exception:
                pass
            m.show()
            self._locator_marker = m
        except Exception:
            pass

        if label:
            try:
                self.iface.messageBar().pushInfo("Locator", f"Found: {label}")
            except Exception:
                pass

    def clear_locator_marker(self):
        if hasattr(self, "_locator_marker") and self._locator_marker:
            try:
                self.iface.mapCanvas().scene().removeItem(self._locator_marker)
            except Exception:
                self._locator_marker.hide()
            self._locator_marker = None
            self.iface.mapCanvas().refresh()


    def __init__(self, iface):
        self.iface = iface
        self.layer = None
        self.toolbar = None
        self.point_tool = None
        self.actions = []
        self.lomna_tool = None  # === DODATO ===
        self.selected_cable_type = None
        self.selected_cable_subtype = None


    # --- FiberQ Pro gating ---
    def check_pro(self) -> bool:
        try:
            return _fiberq_check_pro(self.iface)
        except Exception:
            return False

    # --- Help/About ---
    def _fiberq_read_metadata(self) -> dict:
        import os, configparser
        md = {}
        try:
            md_path = os.path.join(os.path.dirname(__file__), 'metadata.txt')
            cp = configparser.ConfigParser()
            cp.read(md_path, encoding='utf-8')
            if cp.has_section('general'):
                md = dict(cp.items('general'))
        except Exception:
            pass
        return md

    def _fiberq_read_config_value(self, section: str, key: str, default: str = "") -> str:
        import os, configparser
        try:
            cfg_path = os.path.join(os.path.dirname(__file__), 'config.ini')
            cp = configparser.ConfigParser()
            cp.read(cfg_path, encoding='utf-8')
            if cp.has_section(section) and cp.has_option(section, key):
                return cp.get(section, key)
        except Exception:
            pass
        return default

    def show_about_dialog(self):
        try:
            md = self._fiberq_read_metadata()
            name = (md.get('name') or 'FiberQ').strip()
            version = (md.get('version') or '1.0').strip()
            author = (md.get('author') or '').strip()
            email = (md.get('email') or '').strip()
            about = (md.get('about') or '').strip()
            viewer_url = (self._fiberq_read_config_value('web', 'viewer_url', '') or '').strip()
            support_url = (self._fiberq_read_config_value('web', 'support_url', '') or '').strip()

            dlg = QDialog(self.iface.mainWindow())
            dlg.setWindowTitle(f"{name} – About")
            layout = QVBoxLayout(dlg)

            # Rich text body
            parts = [
                f"<h3 style='margin:0 0 6px 0'>{name}</h3>",
                f"<b>Version:</b> {version}<br>",
            ]
            if author:
                parts.append(f"<b>Author:</b> {author}<br>")
            if email:
                parts.append(f"<b>Email:</b> <a href='mailto:{email}'>{email}</a><br>")
            if viewer_url:
                parts.append(f"<b>Preview map URL:</b> <a href='{viewer_url}'>{viewer_url}</a><br>")  
            if support_url:
                parts.append(f"<b>Support URL:</b> <a href='{support_url}'>{support_url}</a><br>")
            # NEW: call-to-action text
            parts.append("<hr style='margin:10px 0'>")
            parts.append(
                "<div style='margin-top:6px'>"
                "<b>Get involved:</b> Want to help shape the next FiberQ release? "
                "Report bugs and share ideas at fiberq.net or email me."
                "</div>"
            )

            if about:
                parts.append(f"<hr style='margin:10px 0'>")
                parts.append(f"<div style='white-space:pre-wrap'>{about}</div>")

            lbl = QLabel(''.join(parts))
            lbl.setTextFormat(Qt.RichText)
            lbl.setOpenExternalLinks(True)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

            bb = QDialogButtonBox(QDialogButtonBox.Ok)
            bb.accepted.connect(dlg.accept)
            layout.addWidget(bb)

            dlg.resize(520, 280)
            dlg.exec_()
        except Exception as e:
            try:
                QMessageBox.information(self.iface.mainWindow(), 'FiberQ', f'About dialog error: {e}')
            except Exception:
                pass

    # === OPTICAL SLACKS: layer and logic ===

    def _set_reserves_layer_alias(self, layer):
        """Display layer 'Opticke_rezerve' as 'Optical slack' in Layers panel."""
        try:
            from qgis.core import QgsProject
            root = QgsProject.instance().layerTreeRoot()
            node = root.findLayer(layer.id())
            if node:
                node.setCustomLayerName("Optical slack")
        except Exception:
            # If something fails (e.g. layerTreeRoot is not ready yet), just skip
            pass

    def _apply_reserves_field_aliases(self, layer):
        """Set English alias field names + ValueMap (EN display, SR value in database)."""
        alias_map = {
            "tip": "Type",
            "duzina_m": "Length (m)",
            "lokacija": "Location",
            "kabl_layer_id": "Cable layer ID",
            "kabl_fid": "Cable feature ID",
            "strana": "Side",
            "napomena": "Note",
        }

        try:
            # Aliasi
            for field_name, alias in alias_map.items():
                idx = layer.fields().indexOf(field_name)
                if idx != -1:
                    layer.setFieldAlias(idx, alias)

            from qgis.core import QgsEditorWidgetSetup

            # ✅ Location: user vidi EN, u bazi ostaje SR (OKNO/Stub/Objekat)
            idx_loc = layer.fields().indexOf("lokacija")
            if idx_loc != -1:
                cfg_loc = {
                    "map": {
                        "Manhole": "OKNO",
                        "Pole": "Stub",
                        "Object": "Objekat",
                    }
                }
                layer.setEditorWidgetSetup(idx_loc, QgsEditorWidgetSetup("ValueMap", cfg_loc))

            # ✅ Side: user vidi EN, u bazi ostaje SR (od/do)
            idx_side = layer.fields().indexOf("strana")
            if idx_side != -1:
                cfg_side = {
                    "map": {
                        "FROM": "od",
                        "TO": "do",
                        "MID SPAN": "sredina",
                    }
                }
                layer.setEditorWidgetSetup(idx_side, QgsEditorWidgetSetup("ValueMap", cfg_side))

            layer.updateFields()

        except Exception:
            pass

    def _ensure_reserves_layer(self):
        """Create or return point layer 'Opticke_rezerve' with required fields."""
        from qgis.core import QgsProject, QgsVectorLayer, QgsFields, QgsField, QgsWkbTypes
        # exists?
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.PointGeometry
                    and lyr.name() in ("Optical_reserves",)
                ):
                    # apply English alias names and English layer name in panel
                    self._apply_reserves_field_aliases(lyr)
                    self._set_reserves_layer_alias(lyr)
                    return lyr
            except Exception:
                pass

        # napravi
        crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        vl = QgsVectorLayer(f"Point?crs={crs}", "Optical slack", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("tip", QVariant.String),
            QgsField("duzina_m", QVariant.Double),
            QgsField("lokacija", QVariant.String),
            QgsField("kabl_layer_id", QVariant.String),
            QgsField("kabl_fid", QVariant.Int),
            QgsField("strana", QVariant.String),
            QgsField("napomena", QVariant.String),
        ])
        vl.updateFields()
        # apply alias names and English layer name
        self._apply_reserves_field_aliases(vl)
        self._set_reserves_layer_alias(vl)
        QgsProject.instance().addMapLayer(vl)
        try:
            self._style_reserves_layer(vl)
        except Exception:
            pass
        return vl


    
    def _style_reserves_layer(self, vl):
        """
        Jednostavan stil: sve optičke rezerve su male crvene tačke.
        Nema više C/S font markera, tako da i posle reload-a ostaju samo tačke.
        """
        try:
            from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsUnitTypes
            from qgis.PyQt.QtGui import QColor
        except Exception:
            return

        try:
            # mala crvena kružna tačka
            sym = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "size": "3",
            })
            try:
                sym.setColor(QColor(255, 0, 0))
            except Exception:
                pass
            try:
                sym.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            except Exception:
                # stari QGIS – ignore
                pass

            renderer = QgsSingleSymbolRenderer(sym)
            vl.setRenderer(renderer)
            vl.triggerRepaint()
        except Exception:
            pass

    
        
    def _recompute_slack_for_cable(self, kabl_layer_id: str, kabl_fid: int):
        """
        Sum 'duzina_m' from layer Opticke_rezerve for given cable and write to cable:
        - slack_m (if corresponding field exists: 'slack_m' / 'slack' / 'rezerva_m' / 'rezerve_m')
        - total_len_m = geom.length() + slack_m (if field 'total_len_m' exists)
        """
        try:
            from qgis.core import QgsProject, QgsFeatureRequest
            prj = QgsProject.instance()
            rez = self._ensure_reserves_layer()
            if rez is None:
                return
            # 1) Izračunaj slack sumu
            slack = 0.0
            expr = f'"kabl_layer_id" = \'{kabl_layer_id}\' AND "kabl_fid" = {int(kabl_fid)}'
            try:
                it = rez.getFeatures(QgsFeatureRequest().setFilterExpression(expr))
            except Exception:
                it = rez.getFeatures()
            for f in it:
                try:
                    if f["kabl_layer_id"] == kabl_layer_id and int(f["kabl_fid"]) == int(kabl_fid):
                        try:
                            slack += float(f["duzina_m"] or 0.0)
                        except Exception:
                            pass
                except Exception:
                    pass

            # 2) Nađi kabl i upiši atribute
            kabl_lyr = prj.mapLayer(kabl_layer_id)
            if kabl_lyr is None:
                return
            kabl_f = next((f for f in kabl_lyr.getFeatures(QgsFeatureRequest(int(kabl_fid)))), None)
            if kabl_f is None:
                return

            # pripremi nazive polja
            fld_slack = None
            for name in ("slack_m", "slack", "rezerva_m", "rezerve_m"):
                if kabl_lyr.fields().indexOf(name) != -1:
                    fld_slack = name
                    break
            has_total = kabl_lyr.fields().indexOf("total_len_m") != -1

            if fld_slack is None and (not has_total):
                # ništa da upišemo
                return

            kabl_lyr.startEditing()
            if fld_slack:
                kabl_f[fld_slack] = float(slack)
            if has_total:
                try:
                    geom_len = float(kabl_f.geometry().length())
                except Exception:
                    geom_len = 0.0
                kabl_f["total_len_m"] = geom_len + float(slack)
            kabl_lyr.updateFeature(kabl_f)
            kabl_lyr.commitChanges()

            # 🔧 Workaround za QGIS bug:
            # Posle programskog editovanja memory lejera
            # QGIS ponekad "zaboravi" labele dok se ponovo ne primeni stil.
            # Ovo radi isto što i kod kreiranja novog kabla.
            try:
                self._stilizuj_kablovi_layer(kabl_lyr)
            except Exception:
                pass

            kabl_lyr.triggerRepaint()
        except Exception as e:
            # Ne ruši alat ako ne uspe upis
            try:
                self.iface.messageBar().pushWarning("Optical slacks", f"Failed updating slack: {e}")
            except Exception:
                pass
    def _start_reserve_interactive(self, default_tip="Terminal"):
        """Starts map-tool for interactive slack placement."""
        dlg = RezervaDialog(self.iface.mainWindow(), default_tip=default_tip)
        if dlg.exec_() != QDialog.Accepted:
            return
        params = dlg.values()
        self._reserve_tool = ReservePlaceTool(self.iface, self, params)
        self.iface.mapCanvas().setMapTool(self._reserve_tool)

    def generate_terminal_reserves_for_selected(self):
        """
        For selected cables (in Underground_cables / Aerial_cables) leave terminal slack at both ends.
        """
        from qgis.core import QgsWkbTypes, QgsGeometry, QgsFeature, QgsProject
        vl = self._ensure_reserves_layer()
        kabl_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.geometryType() == QgsWkbTypes.LineGeometry and lyr.name() in ("Underground_cables", "Aerial_cables"):
                    kabl_layers.append(lyr)
            except Exception:
                pass
        count = 0
        for kl in kabl_layers:
            sel = kl.selectedFeatures()
            for kf in sel:
                geom = kf.geometry()
                line = geom.asPolyline()
                if not line:
                    parts = geom.asMultiPolyline()
                    if parts: line = parts[0]
                if not line:
                    continue
                for lbl, ep in (("od", line[0]), ("do", line[-1])):
                    f = QgsFeature(vl.fields())
                    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(ep)))
                    f["tip"] = "Terminal"
                    f["duzina_m"] = 20
                    # Auto-lokacija: pokušaj da prepozna Stub/OKNO
                    lok = "Objekat"
                    (nl, nf, nd) = ReservePlaceTool(self.iface, self, {})._nearest_node(QgsPointXY(ep))
                    if nl and nf:
                        if nl.name() in ("Poles",):
                            lok = "Stub"
                        elif nl.name() in ("Manholes",):
                            lok = "OKNO"
                        else:
                            lok = "Objekat"

                    f["lokacija"] = lok
                    f["kabl_layer_id"] = kl.id()
                    f["kabl_fid"] = int(kf.id())
                    f["strana"] = lbl
                    vl.startEditing(); vl.addFeature(f); vl.commitChanges()
                    # Auto-pračun slack-a za kabl
                    try:
                        self._recompute_slack_for_cable(kl.id(), int(kf.id()))
                    except Exception:
                        pass
                    count += 1
        vl.triggerRepaint()
        try:
            QMessageBox.information(self.iface.mainWindow(), "Optical slacks", f"Created {count} slacks.")
        except Exception:
            pass

    def style_route_layer(self, trasa_layer):
        # Set alias field names and user-visible layer name
        try:
            self._apply_route_field_aliases(trasa_layer)
            self._set_route_layer_alias(trasa_layer)
        except Exception:
            pass

        symbol = QgsSymbol.defaultSymbol(trasa_layer.geometryType())
        symbol_layer = symbol.symbolLayer(0)
        symbol_layer.setWidth(0.8)
        symbol_layer.setWidthUnit(QgsUnitTypes.RenderMetersInMapUnits)
        symbol_layer.setPenStyle(Qt.DashLine)
        trasa_layer.renderer().setSymbol(symbol)
        trasa_layer.triggerRepaint()




    # === Pomocne funkcije za 'virtuelni merge' trasa prilikom polaganja kabla ===
    def _round_key(self, pt: QgsPointXY, tol: float):
        return (round(pt.x() / tol), round(pt.y() / tol))

    def _first_last_points_of_geom(self, geom: QgsGeometry):
        line = geom.asPolyline()
        if not line:
            multi = geom.asMultiPolyline()
            if multi and len(multi) > 0:
                line = multi[0]
        if not line or len(line) < 2:
            return None, None, []
        return QgsPointXY(line[0]), QgsPointXY(line[-1]), [QgsPointXY(p) for p in line]


    def _build_path_across_network(self, trasa_layer, start_pt: QgsPointXY, end_pt: QgsPointXY, tol_units: float):
        """Routing across ALL vertices (including breakpoints) without physical feature joining.
        Returns list of QgsPointXY or None if no connection exists in network.
        """
        try:
            from qgis.core import QgsPointXY, QgsGeometry
            import math
            # 1) Prikupi sva temena i segmente
            def key_for(p, tol=tol_units):
                # Fuzzy ključ da objedini vrlo bliske tacke
                return (int(round(p.x() / tol)), int(round(p.y() / tol)))
            key_to_pt = {}
            segments = []  # list of (u_key, v_key)

            for f in trasa_layer.getFeatures():
                geom = f.geometry()
                if not geom or geom.isEmpty():
                    continue

                line = geom.asPolyline()
                if not line:
                    mline = geom.asMultiPolyline()
                    if mline:
                        for part in mline:
                            if len(part) < 2:
                                continue
                            for i in range(len(part)):
                                p = QgsPointXY(part[i])
                                k = key_for(p)
                                if k not in key_to_pt:
                                    key_to_pt[k] = p
                            for i in range(len(part) - 1):
                                u = key_for(QgsPointXY(part[i]))
                                v = key_for(QgsPointXY(part[i+1]))
                                if u != v:
                                    segments.append((u, v))
                    continue
                # LineString
                if len(line) < 2:
                    continue
                for i in range(len(line)):
                    p = QgsPointXY(line[i])
                    k = key_for(p)
                    if k not in key_to_pt:
                        key_to_pt[k] = p
                for i in range(len(line) - 1):
                    u = key_for(QgsPointXY(line[i]))
                    v = key_for(QgsPointXY(line[i+1]))
                    if u != v:
                        segments.append((u, v))

            if not key_to_pt or not segments:
                return None

            # 2) Snap start/end na najbliža temena
            def nearest_key(q):
                best_k, best_d2 = None, float('inf')
                for k, p in key_to_pt.items():
                    dx = p.x() - q.x(); dy = p.y() - q.y()
                    d2 = dx*dx + dy*dy
                    if d2 < best_d2:
                        best_k, best_d2 = k, d2
                # prihvati samo u razumnom dometu
                if math.sqrt(best_d2) <= tol_units * 3.0:
                    return best_k
                return None

            start_k = nearest_key(start_pt)
            end_k   = nearest_key(end_pt)
            if start_k is None or end_k is None:
                return None

            # 3) Građenje grafa i BFS najkraćeg puta
            from collections import defaultdict, deque
            adj = defaultdict(list)
            for u, v in segments:
                adj[u].append(v)
                adj[v].append(u)

            parent = {start_k: None}
            q = deque([start_k])
            while q:
                u = q.popleft()
                if u == end_k:
                    break
                for w in adj.get(u, []):
                    if w not in parent:
                        parent[w] = u
                        q.append(w)

            if end_k not in parent:
                return None

            # 4) Rekonstruiši putanju kao liste tačaka
            path_keys = []
            cur = end_k
            while cur is not None:
                path_keys.append(cur)
                cur = parent[cur]
            path_keys.reverse()
            return [key_to_pt[k] for k in path_keys]
        except Exception:
            return None

    def _build_path_across_joined_trasa(self, trasa_layer, start_pt: QgsPointXY, end_pt: QgsPointXY, tol_units: float):
        node_to_edges = {}
        edge_to_points = {}
        endpoints = {}

        for f in trasa_layer.getFeatures():
            p_first, p_last, pts = self._first_last_points_of_geom(f.geometry())
            if not pts:
                continue
            edge_to_points[f.id()] = pts
            endpoints[f.id()] = (p_first, p_last)
            k1 = self._round_key(p_first, tol_units)
            k2 = self._round_key(p_last,  tol_units)
            node_to_edges.setdefault(k1, []).append((f.id(), False))
            node_to_edges.setdefault(k2, []).append((f.id(), True))

        start_key = self._round_key(start_pt, tol_units)
        end_key   = self._round_key(end_pt,   tol_units)
        if start_key not in node_to_edges or end_key not in node_to_edges:
            return None

        from collections import deque
        q = deque([start_key])
        parent = {start_key: None}
        via_edge = {start_key: None}

        while q:
            u = q.popleft()
            if u == end_key:
                break
            for (fid, _) in node_to_edges.get(u, []):
                p0, p1 = endpoints[fid]
                k0 = self._round_key(p0, tol_units)
                k1 = self._round_key(p1, tol_units)
                v = k1 if u == k0 else k0
                if v not in parent:
                    parent[v] = u
                    via_edge[v] = fid
                    q.append(v)

        if end_key not in parent:
            return None

        order_edges = []
        v = end_key
        while via_edge[v] is not None:
            order_edges.append(via_edge[v])
            v = parent[v]
        order_edges.reverse()

        path_pts = []
        current_node = start_key
        for fid in order_edges:
            pts = edge_to_points[fid]
            p_first, p_last = endpoints[fid]
            k_first = self._round_key(p_first, tol_units)
            k_last  = self._round_key(p_last,  tol_units)
            if k_first == current_node:
                seq = pts
                current_node = k_last
            else:
                seq = list(reversed(pts))
                current_node = k_first
            if not path_pts:
                path_pts.extend(seq)
            else:
                if path_pts[-1].x() == seq[0].x() and path_pts[-1].y() == seq[0].y():
                    path_pts.extend(seq[1:])
                else:
                    path_pts.extend(seq)

        if self._round_key(path_pts[-1], tol_units) != end_key:
            return None
        return path_pts


    def initGui(self):
        # Toolbar
        self.toolbar = self.iface.addToolBar('FiberQ Toolbar')
        self.toolbar.setObjectName('FiberQToolbar')

        # Make sure SVGs in styles resolve on every machine
        self._ensure_plugin_svg_search_path()

        # --- Language toggle button (SR/EN) ---
        try:
            self._fiberq_lang_action = QAction('EN', self.iface.mainWindow())
            self._fiberq_lang_action.setToolTip('Switch UI language to English')
            self._fiberq_lang_action.triggered.connect(self._fiberq_toggle_language)
            self.toolbar.addAction(self._fiberq_lang_action)
            try:
                from qgis.PyQt.QtCore import QTimer
                # Apply stored language after UI is ready
                QTimer.singleShot(0, lambda: self._fiberq_apply_language(_get_lang()))
            except Exception:
                pass
        except Exception:
            pass

        # Label "FiberQ" at the start of toolbar
        try:
            _lbl_fiberq = QLabel("FiberQ")
            _lbl_fiberq.setStyleSheet("color:#334155; font-weight:600; padding-right:6px;")
            self.toolbar.addWidget(_lbl_fiberq)
        except Exception:
            pass

        # Help/About (minimal popup)
        try:
            if not hasattr(self, 'action_help_about') or self.action_help_about is None:
                try:
                    icon_help = _load_icon('ic_help.svg')
                except Exception:
                    try:
                        icon_help = QIcon.fromTheme('help-about')
                    except Exception:
                        icon_help = QIcon()
                self.action_help_about = QAction(icon_help, 'Help / About', self.iface.mainWindow())
                self.action_help_about.setToolTip('Help and information about FiberQ')
                try:
                    self.action_help_about.triggered.connect(self.show_about_dialog)
                except Exception:
                    pass

                try:
                    self.toolbar.addAction(self.action_help_about)
                except Exception:
                    try:
                        self.iface.addToolBarIcon(self.action_help_about)
                    except Exception:
                        pass

                try:
                    self.iface.addPluginToMenu('FiberQ', self.action_help_about)
                except Exception:
                    pass

                try:
                    self.actions.append(self.action_help_about)
                except Exception:
                    pass
        except Exception:
            pass

        # Publish to PostGIS

        try:

            self.action_publish_pg = QAction('Publish to PostGIS', self.iface.mainWindow())

            try: self.action_publish_pg.setIcon(_load_icon('ic_publish_pg.svg'))
            except Exception: pass
            self.action_publish_pg.setToolTip('Publish the active (or selected) layer to PostGIS')

            self.action_publish_pg.triggered.connect(self.open_publish_dialog)

            self.actions.append(self.action_publish_pg)

            try:

                self.toolbar.addAction(self.action_publish_pg)

            except Exception:

                pass

            try:

                self.iface.addPluginToMenu('FiberQ', self.action_publish_pg)

            except Exception:

                pass

        except Exception:

            pass


        # Drop-down grupe
        self.ui_cables = CableLayingUI(self)
        self.ui_trasiranje = RoutingUI(self)
        self.ui_placement = PolaganjeElemenataUI(self)
        self.ui_ducts = DuctInfrastructureUI(self)
        self.ui_selection = SelectionUI(self)
        self.ui_reserves = ReservesUI(self)


        # Brza prečica: 'R' otvara interaktivnu završnu rezervu
        try:
            self.action_rezerva_quick = QAction("Terminal slack (shortcut)", self.iface.mainWindow())
            self.action_rezerva_quick.setShortcut(QKeySequence('R'))
            self.action_rezerva_quick.setVisible(False)  # 'skrivena' akcija
            self.action_rezerva_quick.triggered.connect(lambda: self._start_reserve_interactive("Terminal"))
            self.iface.mainWindow().addAction(self.action_rezerva_quick)
            self.actions.append(self.action_rezerva_quick)
        except Exception:
            pass
        self.ui_drawings = DrawingsUI(self)
        self.ui_objekti = ObjektiUI(self)
        # — NOVO — Optički šematski prikaz
        self.action_schematic = QAction(_load_icon('ic_optical_schematic_view.svg'), "Optical schematic view", self.iface.mainWindow())
        self.action_schematic.triggered.connect(self.open_optical_schematic)
        self.toolbar.addAction(self.action_schematic)

        # Dodatna dugmad koja ostaju van grupa (ako treba)
        # Import tačaka ostaje kao samostalan taster, po starom ponasanju
        icon_import_points = _load_icon('ic_import_points.svg')
        self.action_import_points = QAction(icon_import_points, "Import points", self.iface.mainWindow())
        self.action_import_points.triggered.connect(self.import_points)
        self.toolbar.addAction(self.action_import_points)
        self.actions.append(self.action_import_points)


        # Export – active layer to GPX / KML/KMZ / GeoPackage
        try:
            from qgis.PyQt.QtWidgets import QToolButton, QMenu

            export_icon = _load_icon('ic_export_features.svg')

            self.menu_export = QMenu("Export", self.iface.mainWindow())
            self.menu_export.setToolTipsVisible(True)

            self.action_export_selected = QAction(
                export_icon,
                "Export selected...",
                self.iface.mainWindow()
            )
            self.action_export_selected.setToolTip(
                "Export selected features of the active layer to GPX / KML / KMZ / GeoPackage"
            )
            self.action_export_selected.triggered.connect(
                self.export_selected_features
            )
            self.menu_export.addAction(self.action_export_selected)
            self.actions.append(self.action_export_selected)

            self.action_export_all = QAction(
                export_icon,
                "Export all...",
                self.iface.mainWindow()
            )
            self.action_export_all.setToolTip(
                "Export all features of the active layer to GPX / KML / KMZ / GeoPackage"
            )
            self.action_export_all.triggered.connect(
                self.export_all_features
            )
            self.menu_export.addAction(self.action_export_all)
            self.actions.append(self.action_export_all)

            self.btn_export = QToolButton(self.toolbar)
            self.btn_export.setMenu(self.menu_export)
            self.btn_export.setDefaultAction(self.action_export_selected)
            self.btn_export.setPopupMode(QToolButton.MenuButtonPopup)
            self.btn_export.setToolTip("Export active layer")
            self.toolbar.addWidget(self.btn_export)
        except Exception:
            # Failing to build export UI should not break plugin loading
            pass

        # Lokator
        icon_locator = _load_icon('ic_locator.svg')
        self.action_locator = QAction(icon_locator, "Locator", self.iface.mainWindow())
        self.action_locator.triggered.connect(self.open_locator_dialog)
        self.toolbar.addAction(self.action_locator)
        self.actions.append(self.action_locator)

        self.action_clear_locator = QAction(_load_icon('ic_hide_locator.svg'), "Hide locator", self.iface.mainWindow())
        self.action_clear_locator.triggered.connect(self.clear_locator_marker)
        self.toolbar.addAction(self.action_clear_locator)
        self.actions.append(self.action_clear_locator)

        # Relacije
        icon_rel = _load_icon('ic_relations.svg')
        self.action_relations = QAction(icon_rel, "Relations", self.iface.mainWindow())
        self.action_relations.triggered.connect(self.open_relations_dialog)
        self.toolbar.addAction(self.action_relations)
        self.actions.append(self.action_relations)
        # Lista latentnih elemenata
        self.action_latent_list = QAction(_load_icon('ic_list_of_latent_elements.svg'), "List of latent elements", self.iface.mainWindow())
        self.action_latent_list.triggered.connect(self.open_latent_elements_dialog)
        self.toolbar.addAction(self.action_latent_list)
        self.actions.append(self.action_latent_list)
        # Prekid vlakna (novi alat)
        icon_prekid = _load_icon('ic_fiber_break.svg')  # možete kasnije zameniti sa QIcon(':/path/do/ikonice.svg')
        
        # Sečenje infrastrukture (novi alat)
        try:
            icon_sec = _load_icon('ic_infrastructure_cut.svg')
        except Exception:
            try:
                from qgis.PyQt.QtGui import QIcon as _QIconTmp
                icon_sec = _QIconTmp()
            except Exception:
                icon_sec = None
        try:
            self.action_infra_cut = QAction(icon_sec, "Cut infrastructure", self.iface.mainWindow())
        except Exception:
            self.action_infra_cut = QAction("Cut infrastructure")
        try:
            self.action_infra_cut.setObjectName("action_infrastructure_cut")
        except Exception:
            pass
        try:
            self.action_infra_cut.setShortcut(QKeySequence('Ctrl+Shift+X'))
        except Exception:
            pass
        try:
            self.action_infra_cut.triggered.connect(self.activate_infrastructure_cut_tool)
        except Exception:
            pass
        # robustly add to toolbar and menu
        _added_ok = False
        try:
            self.toolbar.addAction(self.action_infra_cut)
            _added_ok = True
        except Exception:
            pass
        if not _added_ok:
            try:
                self.iface.addToolBarIcon(self.action_infra_cut)
                _added_ok = True
            except Exception:
                pass
        try:
            self.iface.addPluginToMenu('FiberQ', self.action_infra_cut)
        except Exception:
            pass
        try:
            self.actions.append(self.action_infra_cut)
        except Exception:
            pass



        self.action_fiber_break = QAction(icon_prekid, "Fiber break", self.iface.mainWindow())
        try:
            self.action_fiber_break.setShortcut(QKeySequence('Ctrl+F'))
        except Exception:
            pass
        self.action_fiber_break.triggered.connect(self.activate_fiber_break_tool)
        self.toolbar.addAction(self.action_fiber_break)
        self.actions.append(self.action_fiber_break)





        # Color catalog (menu for fiber/tube color standards)
        self.action_color_catalog = QAction(_load_icon('ic_color_catalog.svg'), "Color catalog", self.iface.mainWindow())
        self.action_color_catalog.triggered.connect(self.open_color_catalog_manager)
        self.toolbar.addAction(self.action_color_catalog)
        self.actions.append(self.action_color_catalog)

        # === Auto-added button: Sačuvaj sve lejere u GeoPackage ===
        try:
            icon_save_gpkg = _load_icon('ic_save_gpkg.svg')
        except Exception:
            from qgis.PyQt.QtGui import QIcon as _QIconTmp
            icon_save_gpkg = _QIconTmp()
        self.action_save_gpkg = QAction(icon_save_gpkg, "Save all layers to GeoPackage", self.iface.mainWindow())
        self.action_save_gpkg.setToolTip("Export all vector layers (including Temporary scratch) to a single .gpkg and redirect the project to it")
        self.action_save_gpkg.triggered.connect(lambda: _telecom_save_all_layers_to_gpkg(self.iface))
        # Add to toolbar and to list for proper removal
        try:
            self.toolbar.addAction(self.action_save_gpkg)
        except Exception:
            # If plugin doesn't have its own toolbar variable
            self.iface.addToolBarIcon(self.action_save_gpkg)
        try:
            self.actions.append(self.action_save_gpkg)
        except Exception:
            pass


        # === Auto-čuvanje u GeoPackage (toggle) ===
        try:
            icon_auto_gpkg = _load_icon('ic_auto_gpkg.svg')
        except Exception:
            from qgis.PyQt.QtGui import QIcon as _QIconTmp
            icon_auto_gpkg = _QIconTmp()
        self.action_auto_gpkg = QAction(icon_auto_gpkg, "Auto save to GeoPackage", self.iface.mainWindow())
        self.action_auto_gpkg.setCheckable(True)
        self.action_auto_gpkg.setToolTip("When enabled: every new or memory layer is automatically written to the selected .gpkg and redirected to it")
        self.action_auto_gpkg.toggled.connect(self.ui_trasiranje._toggle_auto_gpkg)
        try:
            self.toolbar.addAction(self.action_auto_gpkg)
        except Exception:
            self.iface.addToolBarIcon(self.action_auto_gpkg)
        try:
            self.actions.append(self.action_auto_gpkg)
        except Exception:
            pass

        # === Dugme: Otvori FiberQ web ===
        try:
            icon_fiberq = _load_icon('ic_fiberq_web.svg')
        except Exception:
            icon_fiberq = QIcon()
        self.action_open_fiberq_web = QAction(icon_fiberq, "Open FiberQ web", self.iface.mainWindow())
        self.action_open_fiberq_web.setToolTip("Open FiberQ web browser (URL from config.ini)")
        self.action_open_fiberq_web.triggered.connect(lambda: _open_fiberq_web(self.iface))
        try:
            self.toolbar.addAction(self.action_open_fiberq_web)
        except Exception:
            self.iface.addToolBarIcon(self.action_open_fiberq_web)
        try:
            self.actions.append(self.action_open_fiberq_web)
        except Exception:
            pass


        # Separate cables (offset)
        try:
            icon_branch = _load_icon('ic_branch.svg')
        except Exception:
            icon_branch = QIcon()
        try:
            self.action_branch = QAction(icon_branch, "Branch info", self.iface.mainWindow())
        except Exception:
            self.action_branch = QAction("Branch info")
        try:
            self.action_branch.setShortcut("Ctrl+G")
        except Exception:
            pass
        self.action_branch.setToolTip("Click on cable to show number of cables/types/capacities at that point")
        try:
            self.action_branch.triggered.connect(self.activate_branch_info_tool)
        except Exception:
            pass
        try:
            self.toolbar.addAction(self.action_branch)
        except Exception:
            self.iface.addToolBarIcon(self.action_branch)
        try:
            self.actions.append(self.action_branch)
        except Exception:
            pass

        # Show shortcuts (overlay)
        try:
            self.action_hotkeys = QAction("Show shortcuts", self.iface.mainWindow())
        except Exception:
            self.action_hotkeys = QAction("Show shortcuts")
        try:
            self.action_hotkeys.setIcon(_load_icon('ic_hotkeys.svg'))
        except Exception:
            pass
        try:
            self.action_hotkeys.setShortcut("F1")
        except Exception:
            pass
        try:
            self.action_hotkeys.triggered.connect(self.toggle_hotkeys_overlay)
        except Exception:
            pass
        try:
            self.toolbar.addAction(self.action_hotkeys)
        except Exception:
            try:
                self.iface.addToolBarIcon(self.action_hotkeys)
            except Exception:
                pass
        try:
            self.actions.append(self.action_hotkeys)
        except Exception:
            pass

        # === BOM izveštaj (XLSX/CSV) ===
        try:
            self.action_bom = QAction("BOM izveštaj (XLSX/CSV)", self.iface.mainWindow())
            try:
                self.action_bom.setIcon(_load_icon('ic_bom.svg'))
            except Exception:
                pass
        except Exception:
            # fallback if QAction construction with parent fails
            self.action_bom = QAction("BOM izveštaj (XLSX/CSV)")

        try:
            self.action_bom.setShortcut("Ctrl+B")
        except Exception:
            pass
        self.action_bom.setToolTip("BOM report")
        try:
            self.action_bom.triggered.connect(self.open_bom_dialog)
        except Exception:
            pass
        try:
            self.toolbar.addAction(self.action_bom)
        except Exception:
            self.iface.addToolBarIcon(self.action_bom)
        try:
            self.actions.append(self.action_bom)
        except Exception:
            pass

        # Fallback: global shortcuts
        try:
            self._ensure_global_shortcuts()
        except Exception:
            pass

        # Re-apply kablovi stil/aliasi kad se layer doda u projekat (npr. export iz Preview Map)
        try:
            QgsProject.instance().layersAdded.disconnect(self._on_layers_added)
        except Exception:
            pass
        try:
            QgsProject.instance().layersAdded.connect(self._on_layers_added)
        except Exception:
            pass


    def _color_catalogs_key(self):
        return "ColorCatalogs/catalogs_v1"

    def _default_color_sets(self):
        # Standard 12 colors for fibers (ANSI/TIA), with HEX values
        std12 = [
            ("Blue", "#1f77b4"),
            ("Orange", "#ff7f0e"),
            ("Green", "#2ca02c"),
            ("Brown", "#8c564b"),
            ("Slate", "#7f7f7f"),
            ("White", "#ffffff"),
            ("Red", "#d62728"),
            ("Black", "#000000"),
            ("Yellow", "#bcbd22"),
            ("Violet", "#9467bd"),
            ("Pink", "#e377c2"),
            ("Aqua", "#17becf"),
        ]
        return [
            {"name": "TIA-598-C", "colors": [{"name": n, "hex": h} for n, h in std12]},
        ]

    def _load_color_catalogs(self):
        import json
        s = QgsProject.instance().readEntry('FiberQPlugin', self._color_catalogs_key(), '')[0]
        if not s:
            data = {"catalogs": self._default_color_sets()}
            return data
        try:
            obj = json.loads(s)
            if not isinstance(obj, dict) or "catalogs" not in obj:
                obj = {"catalogs": self._default_color_sets()}
            return obj
        except Exception:
            return {"catalogs": self._default_color_sets()}

    def _save_color_catalogs(self, data):
        import json
        try:
            QgsProject.instance().writeEntry('FiberQPlugin', self._color_catalogs_key(), json.dumps(data))
        except Exception:
            pass

    def _list_color_codes(self):
        # Returns list of catalog names for display in 'Lay cable' dialog
        data = self._load_color_catalogs()
        names = [c.get("name","") for c in data.get("catalogs", []) if c.get("name")]
        # ensure three basic ones exist, without duplicates
        base = ["ANSI/EIA/TIA-598-A", "IEC 60793-2-50", "ITU-T (generički)"]
        for b in base:
            if b not in names:
                names.append(b)
        return names

    def open_color_catalog_manager(self):
        try:
            dlg = ColorCatalogManagerDialog(self)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Color catalog", f"Error: {e}")



    def activate_breakpoint_tool(self):
        """Activate tool for adding breakpoint to route (LomnaTackaTool)."""
        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            self.init_layer()
        self.lomna_tool = LomnaTackaTool(self.iface.mapCanvas(), self.iface, self)
        self.iface.mapCanvas().setMapTool(self.lomna_tool)
    def activate_manual_route_tool(self):
        self.manual_route_tool = ManualRouteTool(self.iface, self)
        self.iface.mapCanvas().setMapTool(self.manual_route_tool)

    def activate_extension_tool(self):
        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            self.init_layer()
        self.extension_tool = ExtensionTool(self.iface.mapCanvas(), self.layer)
        self.iface.mapCanvas().setMapTool(self.extension_tool)
        # self.init_layer()  # već smo je pozvali po potrebi iznad
    def activate_place_element_tool(self, layer_name, symbol_spec=None):
        try:
            # ZADRŽI REFERENCU na alat da ga Python GC ne bi obrisao odmah nakon aktivacije.
            # Bez ovoga, događaji miša ne bi stizali do alata i izgledalo bi kao da se "ništa ne dešava".
            self._place_element_tool = PlaceElementTool(self.iface.mapCanvas(), layer_name, symbol_spec)
            self.iface.mapCanvas().setMapTool(self._place_element_tool)
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Placing elements", f"Error: {e}")

    
    def activate_fiber_break_tool(self):
        """Activate the fiber-break map tool. Falls back to simple point placement if import fails."""
        try:
            # Prefer the dedicated FiberBreakTool from addons
            from .addons.fiber_break import FiberBreakTool
            self._fiber_break_tool = FiberBreakTool(self.iface)
            self.iface.mapCanvas().setMapTool(self._fiber_break_tool)
        except Exception as e:
            try:
                # fallback keeps previous behavior (compatibility)
                symbol_spec = {
                    'name': 'circle',
                    'color': 'black',
                    'size': '4',
                    'size_unit': 'MM',   # important: screen, not map units
                }
                self._place_element_tool = PlaceElementTool(self.iface.mapCanvas(), "Fiber break", symbol_spec)
                self.iface.mapCanvas().setMapTool(self._place_element_tool)
            except Exception:
                QMessageBox.critical(self.iface.mainWindow(), "Fiber break", f"Error activating: {e}")
                return

        # After activating the tool, find all fiber break layers and apply fixed style
        try:
            from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes

            for lyr in QgsProject.instance().mapLayers().values():
                if not isinstance(lyr, QgsVectorLayer):
                    continue
                if lyr.geometryType() != QgsWkbTypes.PointGeometry:
                    continue

                name = (lyr.name() or "").lower()
                # cover both English and Serbian name
                if "fiber break" in name or "prekid" in name:
                    self._apply_prekid_style(lyr)

                    # Field aliases (EN) - user view, field names stay the same for code compatibility
                    try:
                        fields = lyr.fields()
                        alias_map = {
                            "naziv": "Name",
                            "kabl_layer_id": "Cable layer ID",
                            "kabl_fid": "Cable feature ID",
                            "distance_m": "Distance (m)",
                            "segments_hit": "Segments hit",
                            "vreme": "Time",
                        }

                        for fn, al in alias_map.items():
                            idx = fields.indexOf(fn)
                            if idx != -1:
                                lyr.setFieldAlias(idx, al)

                        try:
                            lyr.updateFields()
                        except Exception:
                            pass
                        try:
                            lyr.triggerRepaint()
                        except Exception:
                            pass
                    except Exception:
                        pass

                    
        except Exception:
            # if something fails, don't crash the tool – just skip style
            pass


    def activate_smart_select_tool(self):
        """Enable smart multi-layer selection (without changing active layer)."""
        try:
            self._smart_select_tool = SmartMultiSelectTool(self.iface, self)
            self.iface.mapCanvas().setMapTool(self._smart_select_tool)
            # create selection memory if doesn't exist
            if not hasattr(self, 'smart_selection'):
                self.smart_selection = []
            # information for user
            try:
                self.iface.messageBar().pushInfo("Smart selection", "Click on the elements to select/deselect them. Selections on other layers are not touched.")
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Smart selection", f"Error: {e}")
    def activate_branch_info_tool(self):
        """Activate tool: click on cable -> branch info in message bar."""
        try:
            self._branch_info_tool = BranchInfoTool(self)
            self.iface.mapCanvas().setMapTool(self._branch_info_tool)
            try:
                self.iface.messageBar().pushInfo(
                    "Branch info",
                    "Click on cable to show number of cables/types/capacities at that point "
                    "(right click or ESC to exit)."
                )
            except Exception:
                pass
        except Exception as e:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(self.iface.mainWindow(), "Branch info", f"Error: {e}")


    def clear_all_selections(self):
        """Remove selection from all layers (does not delete objects)."""
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer):
                    lyr.removeSelection()
            except Exception:
                pass
        # clear internal list too
        try:
            self.smart_selection = []
        except Exception:
            pass


    def open_optical_schematic(self):
        try:
            # keep reference so dialog is not garbage collected
            if not hasattr(self, "_schematic_dlg") or self._schematic_dlg is None:
                self._schematic_dlg = OpticalSchematicDialog(self)
            self._schematic_dlg.show()
            self._schematic_dlg.raise_()
            self._schematic_dlg.activateWindow()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Optical schematic", f"Error: {e}")

# === RELACIJE ===
    def open_relations_dialog(self):
        try:
            dlg = RelationsDialog(self)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Relations", f"Error opening dialog: {e}")

    def _relations_storage_key(self):
        return "Relacije/relations_v1"

    def _load_relations(self):
        import json
        s = QgsProject.instance().readEntry('FiberQPlugin', self._relations_storage_key(), '')[0]
        if not s:
            return {"relations": []}
        try:
            return json.loads(s)
        except Exception:
            return {"relations": []}

    def _save_relations(self, data):
        import json
        QgsProject.instance().writeEntry('FiberQPlugin', self._relations_storage_key(), json.dumps(data))

    def _relation_by_id(self, data, rid):
        for r in data.get("relations", []):
            if r.get("id") == rid:
                return r
        return None

    def list_all_cables(self):
        """
        Return list of ALL laid cables from layers
        Underground_cables / Aerial_cables / Underground cables / Aerial cables.
        Each record is a dict with keys:
        layer_id, layer_name, fid, opis, tip, podtip, kapacitet, color_code, od, do
        """
        items = []

        # Accept both old (Serbian) and new (English) layer names
        candidate_names = {
            "Underground_cables",
            "Aerial_cables",
            "Underground cables",
            "Aerial cables",
        }

        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (
                    not isinstance(lyr, QgsVectorLayer)
                    or lyr.geometryType() != QgsWkbTypes.LineGeometry
                    or lyr.name() not in candidate_names
                ):
                    continue
            except Exception:
                continue

            fields = lyr.fields()
            for feat in lyr.getFeatures():
                # read all attributes into dict
                attrs = {fld.name(): feat[fld.name()] for fld in fields}

                tip = attrs.get("tip") or ""
                podtip_code = attrs.get("podtip") or ""
                kap = attrs.get("kapacitet") or ""
                cc = attrs.get("color_code") or ""
                od = attrs.get("od") or ""
                do = attrs.get("do") or ""

                # mapping for NICE DISPLAY in table (internally code remains)
                podtip_labels = {
                    "glavni": "Backbone",
                    "distributivni": "Distribution",
                    "razvodni": "Drop",
                    "Backbone": "Backbone",
                    "Distribution": "Distribution",
                    "Drop": "Drop",
                }
                podtip_label = podtip_labels.get(str(podtip_code), str(podtip_code))

                # opis = what you see in "Cable" column
                opis_parts = []
                if tip:
                    opis_parts.append(str(tip))          # e.g. "Optical"
                if podtip_label:
                    opis_parts.append(str(podtip_label)) # e.g. "Distribution"
                if kap:
                    opis_parts.append(str(kap))          # e.g. "1x96"

                if opis_parts:
                    opis = " ".join(opis_parts)
                else:
                    opis = f"FID {int(feat.id())}"

                items.append({
                    "layer_id": lyr.id(),
                    "layer_name": lyr.name(),
                    "fid": int(feat.id()),
                    "opis": opis,
                    "tip": tip,
                    "podtip": podtip_code,   # ORIGINAL: glavni/distributivni/razvodni
                    "kapacitet": kap,
                    "color_code": cc,
                    "od": od,
                    "do": do,
                })

        return items


    # === LATENTNI ELEMENTI (pitstops) ===
    def _latent_storage_key(self):
        return "LatentElements/latent_v1"

    def _load_latent(self):
        import json
        s = QgsProject.instance().readEntry('FiberQPlugin', self._latent_storage_key(), '')[0]
        if not s:
            return {"cables": {}}
        try:
            return json.loads(s)
        except Exception:
            return {"cables": {}}

    def _save_latent(self, data):
        import json
        QgsProject.instance().writeEntry('FiberQPlugin', self._latent_storage_key(), json.dumps(data))

    def _cable_key(self, layer_id, fid):
        return f"{layer_id}:{int(fid)}"

    def _relation_name_by_cable(self):
        """Mapa {(layer_id,fid)->relation name} iz Relacije storage-a."""
        data = self._load_relations()
        out = {}
        for r in data.get("relations", []):
            nm = r.get("name", "")
            for c in r.get("cables", []):
                key = (c.get("layer_id"), int(c.get("fid")))
                out[key] = nm
        return out


    def list_all_pipes(self):
        """Return list of all laid pipes from layers 'PE_ducts' and 'Transition_ducts'.
        Each record is a dict with keys: layer_id, layer_name, fid, opis, tip, podtip, kapacitet, color_code, od, do
        Note: 'podtip' is used as 'cev' for differentiation in schematic; 'kapacitet' is text (e.g. 'O 40 mm' or value from field).
        """
        items = []
        layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.LineGeometry and lyr.name() in ('PE_ducts', 'Transition_ducts'):
                    layers.append(lyr)
            except Exception:
                pass

        for lyr in layers:
            fields = lyr.fields()
            for f in lyr.getFeatures():
                attrs = {fld.name(): f[fld.name()] for fld in fields}
                materijal = attrs.get('materijal', '') or ''
                kap = attrs.get('kapacitet', '') or ''
                fi = attrs.get('fi', '') or ''
                # Text for capacity/label in schematic
                cap_text = ''
                try:
                    if fi not in (None, ''):
                        cap_text = f"Ø {int(fi)} mm"
                except Exception:
                    pass
                if (kap or '').strip():
                    cap_text = (cap_text + (' | ' if cap_text else '')) + str(kap)
                items.append({
                    'layer_id': lyr.id(),
                    'layer_name': lyr.name(),
                    'fid': int(f.id()),
                    'opis': (str(materijal).strip() or 'Cev') + (f" {cap_text}" if cap_text else ''),
                    'tip': 'cev',
                    'podtip': 'cev',
                    'kapacitet': cap_text,
                    'color_code': '',
                    'od': attrs.get('od', '') or '',
                    'do': attrs.get('do', '') or ''
                })
        return items

    def _find_candidate_elements_for_cable(self, cable_layer, cable_feature, tol=5.0):
        """Find all point elements that lie near the cable route.
        Returns list of dicts: {layer_id, layer_name, fid, naziv, m, distance}
        Sorted by m (distance along line).
        'od' and 'do' elements are skipped by name if they exist."""
        geom = cable_feature.geometry()
        if geom is None or geom.isEmpty():
            return []
        # Load od/do names if they exist
        try:
            od = str(cable_feature['od']) if 'od' in cable_layer.fields().names() and cable_feature['od'] is not None else ''
            do = str(cable_feature['do']) if 'do' in cable_layer.fields().names() and cable_feature['do'] is not None else ''
        except Exception:
            od = ''; do = ''
        cands = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.geometryType() != QgsWkbTypes.PointGeometry:
                    continue
                fields = lyr.fields()
                has_naziv = fields.indexFromName('naziv') != -1
                # Take layers that have 'naziv' or are called 'Poles'
                if not has_naziv and lyr.name() != 'Poles':
                    continue
                for f in lyr.getFeatures():
                    pgeom = f.geometry()
                    if pgeom is None or pgeom.isEmpty():
                        continue
                    d = geom.distance(pgeom)
                    if d > tol:
                        continue
                    try:
                        m = geom.lineLocatePoint(pgeom)
                        m = float(m)
                    except Exception:
                        # Fallback: project nearest point then measure distance from start
                        nearest = geom.closestSegmentWithContext(pgeom.asPoint())[1] if hasattr(geom, 'closestSegmentWithContext') else None
                        m = float(geom.length()) if nearest is None else float(geom.lineLocatePoint(QgsGeometry.fromPointXY(QgsPointXY(nearest))))
                    name = ''
                    if has_naziv:
                        val = f['naziv']
                        if val is not None:
                            name = str(val).strip()
                    # Skip end points by name
                    if name and (name == od or name == do):
                        continue
                    cands.append({
                        "layer_id": lyr.id(),
                        "layer_name": lyr.name(),
                        "fid": int(f.id()),
                        "naziv": name if name else f"{lyr.name()}:{int(f.id())}",
                        "m": m,
                        "distance": float(d),
                    })
            except Exception:
                continue
        # Sort and remove duplicates
        out = []
        seen = set()
        for it in sorted(cands, key=lambda x: x.get('m', 0.0)):
            key = (it['layer_id'], it['fid'])
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    def open_latent_elements_dialog(self):
        try:
            dlg = LatentElementsDialog(self)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "List of latent elements", f"Error: {e}")

    def unload(self):
        # Auto cleanup for auto gpkg toggle
        try:
            self.iface.removeToolBarIcon(self.action_auto_gpkg)
        except Exception:
            pass
        try:
            self.action_auto_gpkg.setChecked(False)
        except Exception:
            pass
        # Disconnect project signal for auto GPKG if connected
        try:
            QgsProject.instance().layerWasAdded.disconnect(self.ui_trasiranje._on_layer_added_auto_gpkg)
        except Exception:
            pass

        try:
            QgsProject.instance().layersAdded.disconnect(self._on_layers_added)
        except Exception:
            pass
   

        # Auto-cleanup for save_gpkg action (safety)
        try:
            self.iface.removeToolBarIcon(self.action_save_gpkg)
        except Exception:
            pass
        for action in self.actions:
            self.iface.removePluginMenu('FiberQ', action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar
        self.layer = None
        # Schematic view – cleanup
        try:
            if hasattr(self, 'action_schematic') and self.action_schematic:
                self.iface.removeToolBarIcon(self.action_schematic)
        except Exception:
            pass
        try:
            if hasattr(self, '_schematic_dlg') and self._schematic_dlg:
                self._schematic_dlg.close()
                self._schematic_dlg = None
        except Exception:
            pass


    def _set_poles_alias(self):
        """Display layer 'Stubovi' as 'Poles' in Layers panel."""
        try:
            root = QgsProject.instance().layerTreeRoot()
            node = root.findLayer(self.layer.id())
            if node:
                node.setCustomLayerName("Poles")
        except Exception:
            # If something fails (e.g. layerTreeRoot is not ready yet), just skip
            pass


    def _apply_poles_field_aliases(self, layer):
        """Set English alias field names for layer Stubovi/Poles."""
        alias_map = {
            "tip": "Type",
            "podtip": "Subtype",
            "visina": "Height (m)",
            "materijal": "Material",
        }
        try:
            for field_name, alias in alias_map.items():
                idx = layer.fields().indexOf(field_name)
                if idx != -1:
                    layer.setFieldAlias(idx, alias)
        except Exception:
            # if something fails (old project etc.) just skip
            pass

    def _set_route_layer_alias(self, layer):
        """Display layer 'Trasa' as 'Route' in Layers panel."""
        try:
            root = QgsProject.instance().layerTreeRoot()
            node = root.findLayer(layer.id())
            if node:
                node.setCustomLayerName("Route")
        except Exception:
            # if something fails (old project etc.) just skip
            pass

    def _apply_route_field_aliases(self, layer):
        """Set English alias field names for layer Trasa/Route
        and ValueMap for 'tip_trase' (SR code, EN display).
        """
        alias_map = {
            "naziv": "Route name",
            "duzina": "Length (m)",
            "duzina_km": "Length (km)",
            "tip_trase": "Route type",
        }
        try:
            from qgis.core import QgsEditorWidgetSetup

            # aliasi
            for field_name, alias in alias_map.items():
                idx = layer.fields().indexOf(field_name)
                if idx != -1:
                    layer.setFieldAlias(idx, alias)

            # ValueMap for tip_trase: value = SR, label = EN
            idx_tip = layer.fields().indexOf("tip_trase")
            if idx_tip != -1:
                cfg = {
                    "map": {
                        "Aerial": "vazdusna",
                        "Underground": "podzemna",
                        "Through the object": "kroz objekat",
                    }
                }
                layer.setEditorWidgetSetup(idx_tip, QgsEditorWidgetSetup("ValueMap", cfg))
                layer.setFieldEditable(idx_tip, True)
                layer.updateFields()

        except Exception:
            # if something fails (old project etc.) just skip
            pass

    
    def _set_okna_layer_alias(self, layer: QgsVectorLayer) -> None:
        """Set user-visible layer name for manholes."""
        try:
            proj = QgsProject.instance()
            root = proj.layerTreeRoot()
            node = root.findLayer(layer.id())
            if node:
                node.setCustomLayerName("Manholes")
        except Exception:
            pass


    def _apply_okna_field_aliases(self, layer: QgsVectorLayer) -> None:
        """English aliases for manhole fields."""
        try:
            alias_map = {
                "broj_okna": "Manhole ID",
                "tip_okna": "Manhole type",
                "vrsta_okna": "Construction type",
                "polozaj_okna": "Position",
                "adresa": "Address",
                "stanje": "Status",
                "god_ugrad": "Installation year",
                "opis": "Description",
                "dimenzije": "Dimensions (cm)",
                "mat_zida": "Wall material",
                "mat_poklop": "Cover material",
                "odvodnj": "Drainage",
                "poklop_tes": "Heavy cover",
                "poklop_lak": "Light cover",
                "br_nosaca": "Number of steps",
                "debl_zida": "Wall thickness (cm)",
                "lestve": "Ladder",
            }
            for field_name, alias in alias_map.items():
                idx = layer.fields().indexOf(field_name)
                if idx >= 0:
                    layer.setFieldAlias(idx, alias)
            layer.triggerRepaint()
        except Exception:
            pass
        

    def _apply_cable_field_aliases(self, layer):
        """English aliases for cable columns (user view)."""
        try:
            alias_map = {
                "tip": "Cable type",
                "podtip": "Segment type",          # glavni / distributivni / razvodni
                "color_code": "Color code",
                "broj_cevcica": "Number of ducts",
                "broj_vlakana": "Number of fibers",
                "tip_kabla": "Cable model",
                "vrsta_vlakana": "Fiber type",
                "vrsta_omotaca": "Sheath type",
                "vrsta_armature": "Armour type",
                "talasno_podrucje": "Wavelength band",
                "naziv": "Name",
                "slabljenje_dbkm": "Attenuation [dB/km]",
                "hrom_disp_ps_nmxkm": "Chromatic dispersion [ps/nm/km]",
                "stanje_kabla": "Status",
                "polaganje_kabla": "Installation type",
                "vrsta_mreze": "Network type",
                "godina_ugradnje": "Installation year",
                "konstr_vlakna_u_cevcicama": "Fibers in ducts",
                "konstr_sa_uzlepljenim_elementom": "With bonded element",
                "konstr_punjeni_kabl": "Gel-filled cable",
                "konstr_sa_arm_vlaknima": "Aramid yarn armouring",
                "konstr_bez_metalnih": "Non-metallic",
                "od": "From",
                "do": "To",
                "duzina_m": "Length [m]",
                "slack_m": "Slack [m]",
                "total_len_m": "Total length [m]",
            }

            for field_name, alias in alias_map.items():
                idx = layer.fields().indexOf(field_name)
                if idx >= 0:
                    layer.setFieldAlias(idx, alias)

            # --- Field 'tip' – switch from Serbian codes to EN (Optical/Copper) ---
            from qgis.core import QgsEditorWidgetSetup

            tip_idx = layer.fields().indexOf("tip")
            if tip_idx >= 0:
                # 1) Migracija starih vrednosti u atributima:
                #    opticki  -> Optical
                #    bakarnI -> Copper
                try:
                    started_edit = False
                    if not layer.isEditable():
                        layer.startEditing()
                        started_edit = True

                    changed = False
                    for f in layer.getFeatures():
                        val = f["tip"]
                        if val == "opticki":
                            layer.changeAttributeValue(f.id(), tip_idx, "Optical")
                            changed = True
                        elif val == "bakarnI":
                            layer.changeAttributeValue(f.id(), tip_idx, "Copper")
                            changed = True

                    if started_edit:
                        if changed:
                            layer.commitChanges()
                        else:
                            layer.rollBack()
                except Exception:
                    # if something fails, don't crash the plugin
                    pass

                # 2) Editor widget: i label i vrednost su EN
                cfg = {
                    "map": {
                        "Optical": "Optical",
                        "Copper":  "Copper",
                    }
                }
                layer.setEditorWidgetSetup(tip_idx, QgsEditorWidgetSetup("ValueMap", cfg))

            # --- ValueMap za polje 'podtip' (glavni/distributivni/razvodni) ---
            podtip_idx = layer.fields().indexOf("podtip")
            if podtip_idx >= 0:
                cfg_podtip = {
                    "map": {
                        "Backbone": "glavni",
                        "Distribution": "distributivni",
                        "Drop": "razvodni",
                    }
                }
                layer.setEditorWidgetSetup(podtip_idx, QgsEditorWidgetSetup("ValueMap", cfg_podtip))

            # --- ValueMap za 'stanje_kabla' (SR kod u bazi, EN prikaz u formi) ---
            stanje_idx = layer.fields().indexOf("stanje_kabla")
            if stanje_idx >= 0:
                cfg_stanje = {
                    "map": {
                        "Planned": "Projektovano",
                        "Existing": "Postojeće",
                        "Under construction": "U izgradnji",
                    }
                }
                layer.setEditorWidgetSetup(stanje_idx, QgsEditorWidgetSetup("ValueMap", cfg_stanje))

            # --- ValueMap za 'polaganje_kabla' (SR kod u bazi, EN prikaz u formi) ---
            pol_idx = layer.fields().indexOf("polaganje_kabla")
            if pol_idx >= 0:
                cfg_pol = {
                    "map": {
                        "Underground": "Podzemno",
                        "Aerial": "Vazdusno",
                    }
                }
                layer.setEditorWidgetSetup(pol_idx, QgsEditorWidgetSetup("ValueMap", cfg_pol))



        except Exception:
            pass

    def _set_cable_layer_alias(self, layer):
        """
        Set English layer names for cables.

        Internally, for compatibility, we accept both Serbian and English names,
        but layer is always called 'Underground cables' or 'Aerial cables' in the end.
        """
        if layer is None:
            return
        try:
            name = layer.name() or ""
        except Exception:
            return

        try:
            if name in ("Underground_cables",):
                layer.setName("Underground cables")
            elif name in ("Aerial_cables",):
                layer.setName("Aerial cables")
        except Exception:
            # if something goes wrong, don't crash the plugin
            pass

    def _on_layers_added(self, layers):
        from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes

        def _set_custom_name(vlayer, new_name: str):
            try:
                root = QgsProject.instance().layerTreeRoot()
                node = root.findLayer(vlayer.id())
                if node and new_name:
                    node.setCustomLayerName(new_name)
            except Exception:
                pass

        cable_names = {"Aerial_cables", "Underground_cables"}

        for layer in layers:
            if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
                continue

            lname = (layer.name() or "")
            lname_l = lname.lower().strip()
            gtype = layer.geometryType()
            fset = {f.name() for f in layer.fields()}

            # 1) CABLES (Line)
            if gtype == QgsWkbTypes.LineGeometry and lname in cable_names:
                self._stilizuj_kablovi_layer(layer)      # EN legend labels
                self._apply_cable_field_aliases(layer)   # EN user view
                self._set_cable_layer_alias(layer)       # EN layer name
                layer.triggerRepaint()
                continue

            # 2) FIBER BREAK (Point)
            if gtype == QgsWkbTypes.PointGeometry and {
                "kabl_layer_id", "kabl_fid", "distance_m", "segments_hit", "vreme"
            }.issubset(fset):
                alias_map = {
                    "naziv": "Name",
                    "kabl_layer_id": "Cable layer ID",
                    "kabl_fid": "Cable feature ID",
                    "distance_m": "Distance (m)",
                    "segments_hit": "Segments hit",
                    "vreme": "Time",
                }
                fields = layer.fields()
                for fn, al in alias_map.items():
                    idx = fields.indexFromName(fn)
                    if idx != -1:
                        layer.setFieldAlias(idx, al)
                _set_custom_name(layer, "Fiber break")
                layer.triggerRepaint()
                continue

            # 3) JOINT CLOSURES (Point)  ✅ SUŽENO da ne hvata ODF/TB/OTB/TO...
            # Allow:
            # - by layer name (Joint Closures / Nastavci / Nastavak) even with suffixes
            # - or if layer really has only id,fid,naziv
            if gtype == QgsWkbTypes.PointGeometry and (
                lname_l.startswith("joint closures")
                or lname_l.startswith("nastav")
                or fset.issubset({"id", "fid", "naziv"})
            ):
                alias_map = {
                    "id": "ID",
                    "fid": "Cable feature ID",
                    "naziv": "Name",
                }
                fields = layer.fields()
                for fn, al in alias_map.items():
                    idx = fields.indexFromName(fn)
                    if idx != -1:
                        layer.setFieldAlias(idx, al)
                _set_custom_name(layer, "Joint Closures")
                layer.triggerRepaint()
                continue

            # 3.5) ROUTE (Line) – EN field aliases + EN layer name (posle export/import iz Preview Map)
            if gtype == QgsWkbTypes.LineGeometry and (
                lname_l.startswith("route")
                or lname_l.startswith("trasa")
                or {"naziv", "duzina", "tip_trase"}.issubset(fset)
            ):
                try:
                    self._apply_route_field_aliases(layer)   # EN user view (aliases + valuemap)
                except Exception:
                    pass
                _set_custom_name(layer, "Route")
                layer.triggerRepaint()
                continue

            # 3.6) POLES (Point) – EN field aliases + EN layer name
            if gtype == QgsWkbTypes.PointGeometry and (
                lname_l.startswith("poles")
                or lname_l.startswith("stubov")
                or {"tip", "podtip", "visina", "materijal"}.issubset(fset)
            ):
                try:
                    self._apply_poles_field_aliases(layer)   # EN user view
                except Exception:
                    pass
                _set_custom_name(layer, "Poles")
                layer.triggerRepaint()
                continue

            # 3.7) MANHOLES / OKNA (Point) – EN field aliases + EN layer name
            if gtype == QgsWkbTypes.PointGeometry and (
                lname_l.startswith("manholes")
                or lname_l.startswith("okna")
                or {"broj_okna", "tip_okna"}.issubset(fset)
            ):
                try:
                    self._apply_okna_field_aliases(layer)    # EN user view
                except Exception:
                    pass
                _set_custom_name(layer, "Manholes")
                layer.triggerRepaint()
                continue

            # 4) GENERIC “Placing elements” (ODF/TB/OTB/TO/Patch panel/Optical slacks…)
            if (
                gtype in (QgsWkbTypes.PointGeometry, QgsWkbTypes.PolygonGeometry)
                and (
                    "proizvodjac" in fset
                    or "kapacitet" in fset
                    or "oznaka" in fset
                    or "address_id" in fset
                    or "naziv_objekta" in fset
                    or "adresa_ulica" in fset
                    or "stanje" in fset
                )
            ):
                # SR->EN field aliases (user view)
                _apply_element_aliases(layer)

                # (opciono) SR -> EN naziv u Layers panelu (radi i ako ima sufiks)
                if lname_l.startswith("nastav"):
                    _set_custom_name(layer, "Joint Closures")
                elif lname_l.startswith("okna"):
                    _set_custom_name(layer, "Manholes")
                elif lname_l.startswith("stubovi"):
                    _set_custom_name(layer, "Poles")
                else:
                    _set_custom_name(layer, lname)

                layer.triggerRepaint()
                continue


    def init_layer(self):
        project = QgsProject.instance()

        # 1) If layer already exists – accept both "Stubovi" and "Poles"
        for lyr in project.mapLayers().values():
            if (
                isinstance(lyr, QgsVectorLayer) and
                lyr.geometryType() == QgsWkbTypes.PointGeometry and
                lyr.name() in ("Poles",)
            ):
                self.layer = lyr
                # apply alias field names immediately
                self._apply_poles_field_aliases(self.layer)
                return

        # 2) If doesn't exist – create new layer named "Poles"
        crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        self.layer = QgsVectorLayer(f"Point?crs={crs}", "Poles", "memory")
        pr = self.layer.dataProvider()
        pr.addAttributes([
            QgsField("tip", QVariant.String),
            QgsField("podtip", QVariant.String),
            QgsField("visina", QVariant.Double),
            QgsField("materijal", QVariant.String),
        ])
        self.layer.updateFields()

        # engleski aliasi za polja
        self._apply_poles_field_aliases(self.layer)

        project.addMapLayer(self.layer)

        symbol = QgsSymbol.defaultSymbol(self.layer.geometryType())
        symbol_layer = symbol.symbolLayer(0)
        symbol_layer.setSize(10)
        symbol_layer.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
        self.layer.renderer().setSymbol(symbol)
        self.layer.triggerRepaint()





    def create_route(self):
        # Allow route creation even when 'Stubovi' layer doesn't exist.
        # If poles layer is not set, we don't block – route can be created from OKNA selection.
        try:
            if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
                # No poles? Not an error. We'll try to continue.
                pass
        except Exception:
            pass
        # Allow route with OKNA (in addition to poles)
        selected_features = []
        # collect selections from 'Stubovi' and 'OKNA' layers
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() in ('Poles', 'Manholes'):
                    if lyr.selectedFeatureCount() > 0:
                        selected_features.extend(lyr.selectedFeatures())
            except Exception:
                pass
        if len(selected_features) < 2:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Select at least two points (Pole/MH) for the route!")
            return

        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                trasa_layer = lyr
                break
        if trasa_layer is None:
            crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
            trasa_layer = QgsVectorLayer(f"LineString?crs={crs}", "Route", "memory")
            QgsProject.instance().addMapLayer(trasa_layer)

        # === DODATO: PROVERA POLJA ===
        added_fields = []
        trasa_layer.startEditing()
        if trasa_layer.fields().indexFromName("naziv") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
            added_fields.append("naziv")
        if trasa_layer.fields().indexFromName("duzina") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
            added_fields.append("duzina")
        if trasa_layer.fields().indexFromName("duzina_km") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("duzina_km", QVariant.Double)])
            added_fields.append("duzina_km")
        if trasa_layer.fields().indexFromName("tip_trase") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("tip_trase", QVariant.String)])
            added_fields.append("tip_trase")
        if added_fields:
            trasa_layer.updateFields()
        trasa_layer.commitChanges()
        # === KRAJ DODATKA ===

        self.style_route_layer(trasa_layer)

        pts = [f.geometry().asPoint() for f in selected_features]
        if len(pts) == 2:
            coords = [QgsPointXY(pts[0]), QgsPointXY(pts[1])]
        else:
            start_pt = min(pts, key=lambda p: (p.x(), p.y()))
            coords = [QgsPointXY(start_pt)]
            remaining = [QgsPointXY(p) for p in pts if p != start_pt]
            while remaining:
                last = coords[-1]
                nearest = min(
                    remaining,
                    key=lambda p:
            QgsGeometry.fromPointXY(last).distance(QgsGeometry.fromPointXY(p))
                )
                coords.append(nearest)
                remaining.remove(nearest)

        line_geom = QgsGeometry.fromPolylineXY(coords)

        # === DODATO: DIJALOG ZA TIP TRASE ===
        items = [TRASA_TYPE_LABELS.get(code, code) for code in TRASA_TYPE_OPTIONS]
        tip_label, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Route type",
            "Select route type:",
            items,
            0, False
        )
        if not ok or not tip_label:
            tip_trase = TRASA_TYPE_OPTIONS[0]
        else:
            tip_trase = TRASA_LABEL_TO_CODE.get(tip_label, TRASA_TYPE_OPTIONS[0])
        # === KRAJ DODATKA ===

        # === DODATO: DUZINA U m I km ===
        duzina_m = line_geom.length()
        duzina_km = round(duzina_m / 1000.0, 2)
        # === KRAJ DODATKA ===

        trasa_feat = QgsFeature(trasa_layer.fields())
        trasa_feat.setGeometry(line_geom)
        trasa_feat.setAttribute("naziv", "Route {}".format(trasa_layer.featureCount() + 1))
        trasa_feat.setAttribute("duzina", duzina_m)
        trasa_feat.setAttribute("duzina_km", duzina_km)
        trasa_feat.setAttribute("tip_trase", tip_trase)

        trasa_layer.startEditing()
        trasa_layer.addFeature(trasa_feat)
        trasa_layer.commitChanges()
        self.style_route_layer(trasa_layer)

         # show EN label in message, but code stays in database (tip_trase)
        tip_label_display = TRASA_TYPE_LABELS.get(tip_trase, tip_trase)
        QMessageBox.information(
            self.iface.mainWindow(),
            "FiberQ",
            f"Route has been created!\nLength: {duzina_m:.2f} m ({duzina_km:.2f} km)\nType: {tip_label_display}"
        )

    def activate_point_tool(self):
        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            self.init_layer()
        self.point_tool = PointTool(self.iface.mapCanvas(), self.layer)
        self.iface.mapCanvas().setMapTool(self.point_tool)

    def obrisi_selektovane(self):
        from qgis.core import QgsProject, QgsVectorLayer, QgsVectorDataProvider

        obrisano = 0
        # set of cables affected by deleted reserves
        affected_cables = set()   # (kabl_layer_id, kabl_fid)

        for lyr in QgsProject.instance().mapLayers().values():
            # THIS IS A CHECK THAT USES capabilities()
            if isinstance(lyr, QgsVectorLayer) and (
                lyr.isEditable()
                or lyr.dataProvider().capabilities() & QgsVectorDataProvider.DeleteFeatures
            ):
                selected_feats = list(lyr.selectedFeatures())

                # If deleting from Opticke_rezerve layer - remember which cables were affected
                if lyr.name() in ("Optical_reserves",):
                    for f in selected_feats:
                        try:
                            kabl_layer_id = f["kabl_layer_id"]
                            kabl_fid = int(f["kabl_fid"])
                            if kabl_layer_id:
                                affected_cables.add((kabl_layer_id, kabl_fid))
                        except Exception:
                            pass

                selected_ids = [f.id() for f in selected_feats]
                if selected_ids:
                    lyr.startEditing()
                    for fid in selected_ids:
                        lyr.deleteFeature(fid)
                        obrisano += 1
                    lyr.commitChanges()
                    lyr.triggerRepaint()
                lyr.removeSelection()

        # AFTER deleting reserves – recalculate slack for affected cables
        if affected_cables:
            for kabl_layer_id, kabl_fid in affected_cables:
                try:
                    self._recompute_slack_for_cable(kabl_layer_id, kabl_fid)
                except Exception:
                    pass

        if obrisano == 0:
            QMessageBox.information(self.iface.mainWindow(), "Delete", "No selected features to delete.")
        else:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Delete",
                f"Deleted {obrisano} selected features from all layers."
            )


    def _stilizuj_kablovi_layer(self, kablovi_layer):
        """
        Cable styling.
        - Underground: dashed line.
        - Aerial: solid line (without cross-hatches).
        Labels remain unchanged.
        """
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtGui import QColor
        from qgis.core import (
            QgsSymbol, QgsSimpleLineSymbolLayer,
            QgsCategorizedSymbolRenderer, QgsRendererCategory,
            QgsProject, QgsWkbTypes, QgsUnitTypes,
            QgsVectorLayerSimpleLabeling, QgsPalLayerSettings,
            QgsTextFormat, QgsTextBufferSettings
        )

        # cable width – take from route if exists, then a bit thicker
        base_width = 0.8
        base_unit = QgsUnitTypes.RenderMetersInMapUnits
        try:
            trasa_layer = next(
                (
                    lyr for lyr in QgsProject.instance().mapLayers().values()
                    if lyr.name().lower().strip() in ("trasa", "route")
                    and lyr.geometryType() == QgsWkbTypes.LineGeometry
                ),
                None
            )
            if trasa_layer and trasa_layer.renderer() and trasa_layer.renderer().symbol():
                sl = trasa_layer.renderer().symbol().symbolLayer(0)
                if hasattr(sl, "width"):
                    base_width = sl.width()
                if hasattr(sl, "widthUnit"):
                    base_unit = sl.widthUnit()
        except Exception:
            pass
        cable_width = max(base_width * 1.6, base_width + 0.6)

        name_l = kablovi_layer.name().lower()
        is_podzemni = "podzem" in name_l
        is_vazdusni = "vazdus" in name_l or "vazduš" in name_l

        COLOR_GLAVNI = QColor(0, 51, 153)
        COLOR_DISTR  = QColor(204, 0, 0)
        COLOR_RAZV   = QColor(165, 42, 42)

        # label-e u legendi na engleskom, vrednosti u atributima ostaju srpske
        label_map = {
            "glavni": "Backbone",
            "distributivni": "Distribution",
            "razvodni": "Drop",
        }

        categories = []
        for value, color in [
            ("glavni", COLOR_GLAVNI),
            ("distributivni", COLOR_DISTR),
            ("razvodni", COLOR_RAZV),
        ]:
            sym = QgsSymbol.defaultSymbol(kablovi_layer.geometryType())
            try:
                if sym.symbolLayerCount() > 0:
                    sym.deleteSymbolLayer(0)
            except Exception:
                pass

            # 1) OSNOVNA LINIJA
            ln = QgsSimpleLineSymbolLayer()
            ln.setColor(color)
            ln.setWidth(cable_width)
            ln.setWidthUnit(base_unit)
            ln.setPenStyle(Qt.DashLine if is_podzemni else Qt.SolidLine)
            sym.appendSymbolLayer(ln)

            # Nema više poprečnih crtica

            label = label_map.get(value, value.capitalize())
            categories.append(QgsRendererCategory(value, sym, label))


        kablovi_layer.setRenderer(QgsCategorizedSymbolRenderer('podtip', categories))

        # --- Labels: keep existing behavior ---
        try:
            s = QgsPalLayerSettings()
            s.fieldName = (
                "concat("
                "format_number(coalesce(\"total_len_m\", $length, length($geometry)), 0), ' m', '\n', "
                "CASE "
                " WHEN lower(coalesce(attribute($currentfeature,'tip'), attribute($currentfeature,'Tip'), attribute($currentfeature,'TIP'))) LIKE 'optick%' THEN 'Optical' "
                " WHEN lower(coalesce(attribute($currentfeature,'tip'), attribute($currentfeature,'Tip'), attribute($currentfeature,'TIP'))) LIKE 'bakarn%' THEN 'Copper' "
                " ELSE coalesce(attribute($currentfeature,'tip'), attribute($currentfeature,'Tip'), attribute($currentfeature,'TIP')) "
                "END, ' ', "
                "coalesce(attribute($currentfeature,'broj_cevcica'), ''), 'x', "
                "coalesce(attribute($currentfeature,'broj_vlakana'), '')"
                ")"
            )


            s.isExpression = True
            try:
                if hasattr(QgsPalLayerSettings, 'LinePlacement') and hasattr(QgsPalLayerSettings.LinePlacement, 'AboveLine'):
                    s.placement = QgsPalLayerSettings.LinePlacement.AboveLine
                elif hasattr(QgsPalLayerSettings, 'Line'):
                    s.placement = QgsPalLayerSettings.Line
            except Exception:
                pass

            tf = QgsTextFormat()
            tf.setSize(9)
            tf.setColor(QColor(200, 0, 0))
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.8)
            buf.setColor(QColor(255, 255, 255))
            tf.setBuffer(buf)
            s.setFormat(tf)

            kablovi_layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
            kablovi_layer.setLabelsEnabled(True)
        except Exception:
            pass

        # English aliases for cables + English layer name in legend
        try:
            self._apply_cable_field_aliases(kablovi_layer)
            self._set_cable_layer_alias(kablovi_layer)
        except Exception:
            pass


        kablovi_layer.triggerRepaint()

        


    
    # === Branching/offset via branch_index ===
        # === Branching/offset via branch_index ===

    def _ensure_branch_index_field(self, layer):
        """Ensure layer has INT field 'branch_index'."""
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant

        try:
            if layer.fields().indexFromName("branch_index") != -1:
                return
            pr = layer.dataProvider()
            pr.addAttributes([QgsField("branch_index", QVariant.Int)])
            layer.updateFields()
        except Exception:
            pass

    def _compute_branch_indices_for_layer(self, layer, tol_m=0.3):
        """
        Assign branch_index for cables that have the same endpoints
        (regardless of direction). tol_m is grouping tolerance in meters.
        """
        from qgis.core import QgsWkbTypes

        if layer is None or layer.geometryType() != QgsWkbTypes.LineGeometry:
            return 0, 0

        tol_units = float(tol_m)

        def round_key(pt):
            return (int(round(pt.x() / tol_units)),
                    int(round(pt.y() / tol_units)))

        groups = {}  # key = ((x1,y1),(x2,y2)), value = [fid,...]

        for f in layer.getFeatures():
            g = f.geometry()
            if g is None or g.isEmpty():
                continue

            try:
                if g.isMultipart():
                    line = g.asMultiPolyline()[0]
                else:
                    line = g.asPolyline()
            except Exception:
                continue

            if len(line) < 2:
                continue

            p1 = line[0]
            p2 = line[-1]
            k1 = round_key(p1)
            k2 = round_key(p2)
            # key independent of direction
            key = (k1, k2) if k1 <= k2 else (k2, k1)
            groups.setdefault(key, []).append(f.id())

        if not groups:
            return 0, 0

        # write branch_index values
        self._ensure_branch_index_field(layer)
        idx = layer.fields().indexFromName("branch_index")
        if idx == -1:
            return 0, 0

        layer.startEditing()
        updated = 0

        for key, ids in groups.items():
            ids_sorted = sorted(ids)
            n = len(ids_sorted)

            if n == 1:
                # samo jedan kabl između ova dva čvora → nema offseta
                try:
                    layer.changeAttributeValue(ids_sorted[0], idx, 0)
                    updated += 1
                except Exception:
                    pass
                continue

            # n >= 2 → dodeli simetrične vrednosti oko nule
            for i, fid in enumerate(ids_sorted):
                pos = i * 2 - (n - 1)
                try:
                    layer.changeAttributeValue(fid, idx, int(pos))
                    updated += 1
                except Exception:
                    pass

        layer.commitChanges()
        return len(groups), updated

    def _apply_branch_offset_style(self, layer, offset_mm=2.0):
        """
        Uključi data-defined offset (u mm) zasnovan na branch_index polju.
        Radi i za SingleSymbol i za Categorized renderer.
        """
        from qgis.core import (
            QgsWkbTypes,
            QgsProperty,
            QgsSymbolLayer,
            QgsUnitTypes,
            QgsSingleSymbolRenderer,
            QgsCategorizedSymbolRenderer,
        )

        if layer is None or layer.renderer() is None:
            return
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            return

        renderer = layer.renderer()

        # izraz kao čist string
        expr = f'coalesce("branch_index",0) * {float(offset_mm)}'

        def apply_on_symbol(sym):
            """Podesi offset na svim symbol layer-ima datog simbola."""
            if sym is None:
                return
            try:
                for sl in sym.symbolLayers():
                    # 1) bazni offset 0, jedinice = mm
                    try:
                        if hasattr(sl, "setOffsetUnit"):
                            sl.setOffsetUnit(QgsUnitTypes.RenderMillimeters)
                        if hasattr(sl, "setOffset"):
                            sl.setOffset(0.0)
                    except Exception:
                        pass
                    # 2) data-defined offset po branch_index
                    try:
                        prop_enum = getattr(QgsSymbolLayer, "PropertyOffset", None)
                        if prop_enum is not None and hasattr(sl, "setDataDefinedProperty"):
                            sl.setDataDefinedProperty(
                                prop_enum,
                                QgsProperty.fromExpression(expr),
                            )
                    except Exception:
                        pass
                    # 3) ako ima podsimbole (marker line i sl.)
                    if hasattr(sl, "subSymbol") and callable(sl.subSymbol):
                        subsym = sl.subSymbol()
                        if subsym is not None:
                            apply_on_symbol(subsym)
            except Exception:
                pass

        # --- Single / Graduated / sl. rendereri ---
        if not isinstance(renderer, QgsCategorizedSymbolRenderer):
            sym = None
            if hasattr(renderer, "symbol"):
                try:
                    sym = renderer.symbol()
                except Exception:
                    sym = None
            if sym is not None:
                apply_on_symbol(sym)

        # --- Categorized renderer – obradi sve kategorije ---
        else:
            cats = renderer.categories()
            for cat in cats:
                apply_on_symbol(cat.symbol())
            layer.setRenderer(renderer)

        try:
            layer.triggerRepaint()
        except Exception:
            pass

    def separate_cables_offset(self):
        """
        Handler for 'Branch cables (offset)' button.
        Calculate branch_index and apply offset for active line layer.
        """
        from qgis.core import QgsVectorLayer, QgsWkbTypes

        try:
            layer = self.iface.activeLayer()
        except Exception:
            layer = None

        if not (layer and isinstance(layer, QgsVectorLayer)
                and layer.geometryType() == QgsWkbTypes.LineGeometry):
            try:
                self.iface.messageBar().pushWarning(
                    "Branch cables",
                    "Activate a cable line layer first."
                )
            except Exception:
                pass
            return

        groups, updated = self._compute_branch_indices_for_layer(layer, tol_m=1.3)
        self._apply_branch_offset_style(layer, offset_mm=2.0)

        try:
            msg = (
                f"Branching finished – groups: {groups}, "
                f"updated cables: {updated}. "
                "If you don't see separation, refresh view (Ctrl+R)."
            )
            self.iface.messageBar().pushInfo("Branch cables", msg)
        except Exception:
            pass

        try:
            layer.triggerRepaint()
        except Exception:
            pass


    def toggle_hotkeys_overlay(self):
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        from qgis.PyQt.QtCore import Qt
        try:
            if getattr(self, '_hotkeys_dlg', None) and self._hotkeys_dlg.isVisible():
                self._hotkeys_dlg.hide()
                return
            self._hotkeys_dlg = QDialog(self.iface.mainWindow(), Qt.Tool)
            self._hotkeys_dlg.setWindowTitle('Shortcuts')
            self._hotkeys_dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self._hotkeys_dlg.setAttribute(Qt.WA_DeleteOnClose, False)
            lay = QVBoxLayout(self._hotkeys_dlg)
            lbl = QLabel(
                "<b>Shortcuts</b><br>"
                "Keyboard shortcuts are currently disabled in this version.<br>"
                "<br>"
                "Use the toolbar buttons for:<br>"
                "• BOM report<br>"
                "• Branch cables (offset)<br>"
                "• Publish (PostGIS)<br>"
                "• Fiber break<br>"
                "• Optical slack (interactive)"
            )
            lbl.setTextFormat(Qt.RichText)
            lay.addWidget(lbl)
            btn = QPushButton("Close")
            btn.clicked.connect(self._hotkeys_dlg.hide)
            lay.addWidget(btn, alignment=Qt.AlignRight)
            self._hotkeys_dlg.resize(300, 180)
            self._hotkeys_dlg.show()
        except Exception:
            pass

    def merge_all_routes(self):
        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                trasa_layer = lyr
                break
        if trasa_layer is None:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Layer 'Route' is not found!")
            return

        # === DODATO: PROVERA POLJA ===
        added_fields = []
        trasa_layer.startEditing()
        if trasa_layer.fields().indexFromName("naziv") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
            added_fields.append("naziv")
        if trasa_layer.fields().indexFromName("duzina") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
            added_fields.append("duzina")
        if trasa_layer.fields().indexFromName("duzina_km") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("duzina_km", QVariant.Double)])
            added_fields.append("duzina_km")
        if trasa_layer.fields().indexFromName("tip_trase") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("tip_trase", QVariant.String)])
            added_fields.append("tip_trase")
        if added_fields:
            trasa_layer.updateFields()
        trasa_layer.commitChanges()
        # === KRAJ DODATKA ===

        selected_feats = trasa_layer.selectedFeatures()
        if len(selected_feats) < 2:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Select at least two routes to merge!")
            return

        polylines = []
        for feat in selected_feats:
            geom = feat.geometry()
            pts = geom.asPolyline()
            if not pts:
                multi = geom.asMultiPolyline()
                if multi and len(multi) > 0:
                    pts = multi[0]
            if pts and len(pts) >= 2:
                polylines.append(list(pts))
        if len(polylines) < 2:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Not enough valid lines to merge!")
            return

        chain = polylines.pop(0)
        while polylines:
            min_dist = None
            min_poly_idx = None
            reverse_this = False
            reverse_chain = False
            for idx, poly in enumerate(polylines):
                dists = [
                    (chain[-1], poly[0], False, False),
                    (chain[-1], poly[-1], False, True),
                    (chain[0], poly[0], True, False),
                    (chain[0], poly[-1], True, True),
                ]
                for pt1, pt2, rev_chain, rev_poly in dists:
                    dist = pt1.distance(pt2)
                    if min_dist is None or dist < min_dist:
                        min_dist = dist
                        min_poly_idx = idx
                        reverse_this = rev_poly
                        reverse_chain = rev_chain
            next_poly = polylines.pop(min_poly_idx)
            if reverse_this:
                next_poly.reverse()
            if reverse_chain:
                chain.reverse()
            if chain[-1] == next_poly[0]:
                chain += next_poly[1:]
            else:
                chain += next_poly

        geom = QgsGeometry.fromPolylineXY(chain)

        # PROVERA I KONVERZIJA AKO JE MULTILINESTRING!
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
            if lines and len(lines) == 1:
                geom = QgsGeometry.fromPolylineXY(lines[0])
            else:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Spoji trase",
                    "Nije moguće spojiti u jednu liniju! Trase nisu povezane krajem u kraj."
                )
                return

        # === DODATO: DIJALOG ZA TIP TRASE ===
        items = [TRASA_TYPE_LABELS.get(code, code) for code in TRASA_TYPE_OPTIONS]
        tip_label, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Type of connected route",
            "Select route type:",
            items,
            0, False
        )
        if not ok or not tip_label:
            tip_trase = TRASA_TYPE_OPTIONS[0]
        else:
            tip_trase = TRASA_LABEL_TO_CODE.get(tip_label, TRASA_TYPE_OPTIONS[0])

        # === KRAJ DODATKA ===

        duzina_m = geom.length()
        duzina_km = round(duzina_m / 1000.0, 2)

        trasa_layer.startEditing()
        for f in selected_feats:
            trasa_layer.deleteFeature(f.id())
        feat = QgsFeature(trasa_layer.fields())
        feat.setGeometry(geom)
        feat.setAttribute("naziv", "Merged route")
        feat.setAttribute("duzina", duzina_m)
        feat.setAttribute("duzina_km", duzina_km)
        feat.setAttribute("tip_trase", tip_trase)
        trasa_layer.addFeature(feat)
        trasa_layer.commitChanges()
        self.style_route_layer(trasa_layer)

        tip_label_display = TRASA_TYPE_LABELS.get(tip_trase, tip_trase)
        QMessageBox.information(
            self.iface.mainWindow(),
            "FiberQ",
            f"Route has been created!\nLength: {duzina_m:.2f} m ({duzina_km:.2f} km)\nType: {tip_label_display}"
        )


    def lay_cable_by_type(self, tip, podtip):
        self.selected_cable_type = tip
        self.selected_cable_subtype = podtip
        self.polozi_kabl()

    
    def polozi_kabl(self):
        # Collect selections from all element layers (+ Poles + OKNA)
        relevant_names = [NASTAVAK_DEF['name']] + [d['name'] for d in ELEMENT_DEFS] + ['Poles', 'Manholes']
        selected = []
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() in relevant_names:
                feats = lyr.selectedFeatures()
                for f in feats:
                    selected.append((lyr, f))
        if len(selected) != 2:
            QMessageBox.warning(self.iface.mainWindow(), "Cable", "Select exactly 2 elements (of any type)!")
            return

        # Sloj trasa
        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                trasa_layer = lyr
                break
        if trasa_layer is None or trasa_layer.featureCount() == 0:
            QMessageBox.warning(self.iface.mainWindow(), "Cable", "Layer 'Route' not found or has no line!")
            return

        point1 = selected[0][1].geometry().asPoint()
        point2 = selected[1][1].geometry().asPoint()

        # Nastavak ostatka postojeće logike – dijalog za izbor tipa/podtipa, kreiranje odgovarajućeg sloja kablova itd.


        # Odredi tip/podtip i ciljnu liniju (po tipu)
        tip = getattr(self, 'selected_cable_type', None)
        podtip = getattr(self, 'selected_cable_subtype', None)
        
        # Uvek prikaži dijalog za izbor parametara kabla – sa unapred podešenim vrednostima
        tip = getattr(self, "selected_cable_type", None)
        podtip = getattr(self, "selected_cable_subtype", None)

        # mapiraj tip -> vrsta (podzemni/vazdusni)
        def _infer_vrsta(t):
            if not t:
                return None
            tl = str(t).lower()
            if "vazdu" in tl:
                return "vazdusni"
            return "podzemni"

        default_vrsta = "vazdusni" if _infer_vrsta(tip) == "vazdusni" else "podzemni"
        dlg = CablePickerDialog(self.iface.mainWindow(), default_vrsta=default_vrsta, default_podtip=podtip, color_codes=self._list_color_codes())
        if dlg.exec_() != QDialog.Accepted:
            return
        
        vals = dlg.values()
        vrsta = vals["vrsta"]
        tip = vals["tip"]
        podtip = vals["podtip"]
        color_code = vals["color_code"]
        broj_cevcica = vals["broj_cevcica"]
        broj_vlakana = vals["broj_vlakana"]
        tip_kabla = vals["tip_kabla"]
        vrsta_vlakana = vals["vrsta_vlakana"]
        vrsta_omotaca = vals["vrsta_omotaca"]
        vrsta_armature = vals["vrsta_armature"]
        talasno_podrucje = vals["talasno_podrucje"]
        naziv = vals["naziv"]
        slabljenje_dbkm = vals["slabljenje_dbkm"]
        hrom_disp_ps_nmxkm = vals["hrom_disp_ps_nmxkm"]
        stanje_kabla = vals["stanje_kabla"]
        polaganje_kabla = vals["polaganje_kabla"]
        vrsta_mreze = vals["vrsta_mreze"]
        godina_ugradnje = vals["godina_ugradnje"]
        konstr_vlakna_u_cevcicama = vals["konstr_vlakna_u_cevcicama"]
        konstr_sa_uzlepljenim_elementom = vals["konstr_sa_uzlepljenim_elementom"]
        konstr_punjeni_kabl = vals["konstr_punjeni_kabl"]
        konstr_sa_arm_vlaknima = vals["konstr_sa_arm_vlaknima"]
        konstr_bez_metalnih = vals["konstr_bez_metalnih"]


        layer_suffix = "vazdusni" if str(vrsta).lower().startswith("vazdu") else "podzemni"

        # Accept both old (Serbian) and new (English) layer names
        if layer_suffix == "vazdusni":
            candidate_names = ("Aerial_cables",)
        else:
            candidate_names = ("Underground_cables",)

                # --- Izbor sloja za kablove (Aerial/Underground) ---

        layer_suffix = "vazdusni" if str(vrsta).lower().startswith("vazdu") else "podzemni"

        # Accept both old (Serbian) and new (English) layer names
        if layer_suffix == "vazdusni":
            candidate_names = ("Aerial_cables",)
            default_name = "Aerial cables"
        else:
            candidate_names = ("Underground_cables",)
            default_name = "Underground cables"

        kablovi_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.LineGeometry
                    and lyr.name() in candidate_names
                ):
                    kablovi_layer = lyr
                    break
            except Exception:
                # if we encounter raster or something without geometryType, just skip
                pass

        if kablovi_layer is None:
            crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
            kablovi_layer = QgsVectorLayer(f"LineString?crs={crs}", default_name, "memory")
            pr = kablovi_layer.dataProvider()

            pr.addAttributes([
                QgsField("tip", QVariant.String),
                QgsField("podtip", QVariant.String),
                QgsField("color_code", QVariant.String),
                QgsField("broj_cevcica", QVariant.Int),
                QgsField("broj_vlakana", QVariant.Int),
                QgsField("tip_kabla", QVariant.String),
                QgsField("vrsta_vlakana", QVariant.String),
                QgsField("vrsta_omotaca", QVariant.String),
                QgsField("vrsta_armature", QVariant.String),
                QgsField("talasno_podrucje", QVariant.String),
                QgsField("naziv", QVariant.String),
                QgsField("slabljenje_dbkm", QVariant.Double),
                QgsField("hrom_disp_ps_nmxkm", QVariant.Double),
                QgsField("stanje_kabla", QVariant.String),
                QgsField("polaganje_kabla", QVariant.String),
                QgsField("vrsta_mreze", QVariant.String),
                QgsField("godina_ugradnje", QVariant.Int),
                QgsField("konstr_vlakna_u_cevcicama", QVariant.Int),
                QgsField("konstr_sa_uzlepljenim_elementom", QVariant.Int),
                QgsField("konstr_punjeni_kabl", QVariant.Int),
                QgsField("konstr_sa_arm_vlaknima", QVariant.Int),
                QgsField("konstr_bez_metalnih", QVariant.Int),
                QgsField("od", QVariant.String),
                QgsField("do", QVariant.String),
                QgsField("duzina_m", QVariant.Double),
                QgsField("slack_m", QVariant.Double),
                QgsField("total_len_m", QVariant.Double),
            ])

            kablovi_layer.updateFields()
            QgsProject.instance().addMapLayer(kablovi_layer)
            
        
        # Ensure layer has all required fields (if it existed from before)
        needed_fields = {
            "tip": QVariant.String,
            "podtip": QVariant.String,
            "color_code": QVariant.String,
            "broj_cevcica": QVariant.Int,
            "broj_vlakana": QVariant.Int,
            "tip_kabla": QVariant.String,
            "vrsta_vlakana": QVariant.String,
            "vrsta_omotaca": QVariant.String,
            "vrsta_armature": QVariant.String,
            "talasno_podrucje": QVariant.String,
            "naziv": QVariant.String,
            "slabljenje_dbkm": QVariant.Double,
            "hrom_disp_ps_nmxkm": QVariant.Double,
            "stanje_kabla": QVariant.String,
            "polaganje_kabla": QVariant.String,
            "vrsta_mreze": QVariant.String,
            "godina_ugradnje": QVariant.Int,
            "konstr_vlakna_u_cevcicama": QVariant.Int,
            "konstr_sa_uzlepljenim_elementom": QVariant.Int,
            "konstr_punjeni_kabl": QVariant.Int,
            "konstr_sa_arm_vlaknima": QVariant.Int,
            "konstr_bez_metalnih": QVariant.Int,
            "od": QVariant.String,
            "do": QVariant.String,
            "duzina_m": QVariant.Double, 
            "slack_m": QVariant.Double,      # NOVO
            "total_len_m": QVariant.Double,  # NOVO
        }
        to_add = []
        for fname, ftype in needed_fields.items():
            if kablovi_layer.fields().indexFromName(fname) == -1:
                to_add.append(QgsField(fname, ftype))
        if to_add:
            prov = (kablovi_layer.providerType() or "").lower()
            if prov in ("memory", "ogr", "spatialite"):
                kablovi_layer.dataProvider().addAttributes(to_add)
                kablovi_layer.updateFields()
            else:
                # PostGIS/WFS/itd — ne diramo šemu, samo upozorimo
                self.iface.messageBar().pushWarning(
                    "FiberQ",
                    "Cable layer is missing fields (slack_m/total_len_m). Add them in the database schema."
                )

        # Uvek osveži stil da odgovara tipu sloja

        self._stilizuj_kablovi_layer(kablovi_layer)

        def _disp_name(layer, feat):
            try:
                if layer.name() in ('OKNA', 'Manholes'):
                    if 'broj_okna' in layer.fields().names():
                        broj = feat['broj_okna']
                        if broj is not None and str(broj).strip():
                            return f"KO {str(broj).strip()}"
                idx = layer.fields().indexFromName('naziv')
                if idx != -1:
                    val = feat['naziv']
                    if val is not None and str(val).strip():
                        return str(val).strip()
                if layer.name() == 'Poles':
                    tip = str(feat['tip']) if 'tip' in layer.fields().names() and feat['tip'] is not None else ''
                    return ("Stub " + tip).strip() or f"Stub {int(feat.id())}"
            except Exception:
                pass
            return f"{layer.name()}:{int(feat.id())}"
        
        od_naziv = _disp_name(selected[0][0], selected[0][1])
        do_naziv = _disp_name(selected[1][0], selected[1][1])


        kabl_geom = None
        found_feature = None
        for feat in trasa_layer.getFeatures():
            geom = feat.geometry()
            if geom.type() != QgsWkbTypes.LineGeometry:
                continue
            line = geom.asPolyline()
            if not line:
                multi = geom.asMultiPolyline()
                if multi and len(multi) > 0:
                    line = multi[0]
            dists1 = [QgsPointXY(point1).distance(QgsPointXY(p)) for p in line]
            dists2 = [QgsPointXY(point2).distance(QgsPointXY(p)) for p in line]
            min_dist1 = min(dists1)
            min_dist2 = min(dists2)
            idx1 = dists1.index(min_dist1)
            idx2 = dists2.index(min_dist2)
            if min_dist1 < 1 and min_dist2 < 1 and idx1 != idx2:
                found_feature = feat
                if idx1 < idx2:
                    kabl_geom = QgsGeometry.fromPolylineXY(line[idx1:idx2+1])
                else:
                    kabl_geom = QgsGeometry.fromPolylineXY(list(reversed(line[idx2:idx1+1])))
                break

        if kabl_geom is None:
            # New: try through joined route parts (virtual merge)
            tol_units = self.iface.mapCanvas().mapUnitsPerPixel() * 6
            path_pts = self._build_path_across_network(trasa_layer, point1, point2, tol_units)
            if not path_pts:
                path_pts = self._build_path_across_joined_trasa(trasa_layer, point1, point2, tol_units)
            if path_pts:
                kabl_geom = QgsGeometry.fromPolylineXY(path_pts)

        if kabl_geom is None:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Joint closures or elements are not at the ends of the same route or connected routes.")
            return

        
        feat = QgsFeature(kablovi_layer.fields())
        feat.setGeometry(kabl_geom)
        feat.setAttribute("tip", tip)
        feat.setAttribute("podtip", podtip)
        feat.setAttribute("color_code", color_code)
        feat.setAttribute("broj_cevcica", broj_cevcica)
        feat.setAttribute("broj_vlakana", broj_vlakana)
        feat.setAttribute("tip_kabla", tip_kabla)
        feat.setAttribute("vrsta_vlakana", vrsta_vlakana)
        feat.setAttribute("vrsta_omotaca", vrsta_omotaca)
        feat.setAttribute("vrsta_armature", vrsta_armature)
        feat.setAttribute("talasno_podrucje", talasno_podrucje)
        feat.setAttribute("naziv", naziv)
        feat.setAttribute("slabljenje_dbkm", slabljenje_dbkm)
        feat.setAttribute("hrom_disp_ps_nmxkm", hrom_disp_ps_nmxkm)
        feat.setAttribute("stanje_kabla", stanje_kabla)
        feat.setAttribute("polaganje_kabla", polaganje_kabla)
        feat.setAttribute("vrsta_mreze", vrsta_mreze)
        feat.setAttribute("godina_ugradnje", godina_ugradnje)
        feat.setAttribute("konstr_vlakna_u_cevcicama", konstr_vlakna_u_cevcicama)
        feat.setAttribute("konstr_sa_uzlepljenim_elementom", konstr_sa_uzlepljenim_elementom)
        feat.setAttribute("konstr_punjeni_kabl", konstr_punjeni_kabl)
        feat.setAttribute("konstr_sa_arm_vlaknima", konstr_sa_arm_vlaknima)
        feat.setAttribute("konstr_bez_metalnih", konstr_bez_metalnih)
        feat.setAttribute("od", od_naziv)
        feat.setAttribute("do", do_naziv)
        # write length
        try:
            feat.setAttribute("duzina_m", kabl_geom.length())
        except Exception:
            pass
        kablovi_layer.startEditing()
        kablovi_layer.addFeature(feat)
        kablovi_layer.commitChanges()
        kablovi_layer.updateExtents()
        kablovi_layer.triggerRepaint()

        QMessageBox.information(self.iface.mainWindow(), "FiberQ", "Cable has been laid along the route!")

    def import_route_from_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Choose route file (KML/KMZ/DWG/GPX/Shape)", "",
            "GIS files (*.kml *.kmz *.dwg *.gpx *.shp);;All files (*)"
        )
        if not filename:
            return

        imported_layer = QgsVectorLayer(filename, "Uvezi_trasa_tmp", "ogr")
        if not imported_layer.isValid():
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "File cannot be loaded or is not valid!")
            return

        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                trasa_layer = lyr
                break
        if trasa_layer is None:
            crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
            trasa_layer = QgsVectorLayer(f"LineString?crs={crs}", "Route", "memory")
            QgsProject.instance().addMapLayer(trasa_layer)

        # === DODATO: PROVERA POLJA ===
        added_fields = []
        trasa_layer.startEditing()
        if trasa_layer.fields().indexFromName("naziv") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
            added_fields.append("naziv")
        if trasa_layer.fields().indexFromName("duzina") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
            added_fields.append("duzina")
        if trasa_layer.fields().indexFromName("duzina_km") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("duzina_km", QVariant.Double)])
            added_fields.append("duzina_km")
        if trasa_layer.fields().indexFromName("tip_trase") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("tip_trase", QVariant.String)])
            added_fields.append("tip_trase")
        if added_fields:
            trasa_layer.updateFields()
        trasa_layer.commitChanges()
        # === KRAJ DODATKA ===

        src_crs = imported_layer.crs()
        dst_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

        trasa_layer.startEditing()
        broj_dodatih = 0

        # === DODATO: DIJALOG ZA TIP TRASE ===
        items = [TRASA_TYPE_LABELS.get(code, code) for code in TRASA_TYPE_OPTIONS]
        tip_label, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Imported route type",
            "Select route type:",
            items,
            0, False
        )
        if not ok or not tip_label:
            tip_trase = TRASA_TYPE_OPTIONS[0]
        else:
            tip_trase = TRASA_LABEL_TO_CODE.get(tip_label, TRASA_TYPE_OPTIONS[0])
        # === KRAJ DODATKA ===

        # === KRAJ DODATKA ===

        for feat in imported_layer.getFeatures():
            geom = feat.geometry()
            if geom.isMultipart():
                multi = geom.asMultiPolyline()
                if multi:
                    for polyline in multi:
                        if polyline and len(polyline) >= 2:
                            new_feat = QgsFeature(trasa_layer.fields())
                            geom_line = QgsGeometry.fromPolylineXY(polyline)
                            if src_crs != dst_crs:
                                geom_line.transform(transform)
                            duzina_m = geom_line.length()
                            duzina_km = round(duzina_m / 1000.0, 2)
                            new_feat.setGeometry(geom_line)
                            new_feat.setAttribute("naziv", "Imported route {}".format(trasa_layer.featureCount() + 1))
                            new_feat.setAttribute("duzina", duzina_m)
                            new_feat.setAttribute("duzina_km", duzina_km)
                            new_feat.setAttribute("tip_trase", tip_trase)
                            trasa_layer.addFeature(new_feat)
                            broj_dodatih += 1
            else:
                polyline = geom.asPolyline()
                if polyline and len(polyline) >= 2:
                    new_feat = QgsFeature(trasa_layer.fields())
                    geom_line = QgsGeometry.fromPolylineXY(polyline)
                    if src_crs != dst_crs:
                        geom_line.transform(transform)
                    duzina_m = geom_line.length()
                    duzina_km = round(duzina_m / 1000.0, 2)
                    new_feat.setGeometry(geom_line)
                    new_feat.setAttribute("naziv", "Imported route {}".format(trasa_layer.featureCount() + 1))
                    new_feat.setAttribute("duzina", duzina_m)
                    new_feat.setAttribute("duzina_km", duzina_km)
                    new_feat.setAttribute("tip_trase", tip_trase)
                    trasa_layer.addFeature(new_feat)
                    broj_dodatih += 1

        trasa_layer.commitChanges()
        self.style_route_layer(trasa_layer)
        
         # show EN label for type
        tip_label_display = TRASA_TYPE_LABELS.get(tip_trase, tip_trase)

        if broj_dodatih:
            QMessageBox.information(
                self.iface.mainWindow(),
                "FiberQ",
                f"Imported {broj_dodatih} routes into the 'Route' layer!\n(All are of type: {tip_label_display})"
            )
        else:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "FiberQ",
                "No lines found for import in the file!"
            )

    def change_route_type(self):
        # Find layer Trasa
        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                trasa_layer = lyr
                break
        if trasa_layer is None:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Route layer 'Route' not found!")
            return

        selected_feats = trasa_layer.selectedFeatures()
        if not selected_feats:
            QMessageBox.information(self.iface.mainWindow(), "Change route type", "No routes selected!")
            return

        # Dijalog za izbor novog tipa
        items = [TRASA_TYPE_LABELS.get(code, code) for code in TRASA_TYPE_OPTIONS]
        tip_label, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Change route type",
            "Select new route type for selected routes:",
            items,
            0, False
        )
        if not ok or not tip_label:
            return
        tip_trase = TRASA_LABEL_TO_CODE.get(tip_label, TRASA_TYPE_OPTIONS[0])


        # Izmena svih selektovanih
        trasa_layer.startEditing()
        brojac = 0
        idx_tip = trasa_layer.fields().indexFromName("tip_trase")
        for feat in selected_feats:
            trasa_layer.changeAttributeValue(feat.id(), idx_tip, tip_trase)
            brojac += 1


        trasa_layer.commitChanges()
        self.style_route_layer(trasa_layer)

        tip_label_display = TRASA_TYPE_LABELS.get(tip_trase, tip_trase)

        QMessageBox.information(
            self.iface.mainWindow(),
            "Change route type",
            f"Route type has been changed to '{tip_label_display}' for {brojac} route(s)."
        )

    def import_points(self):
        filename, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Izaberi fajl sa tačkama (KML/KMZ/DWG/Shape/GPX)",
            "",
            "GIS fajlovi (*.kml *.kmz *.shp *.dwg *.gpx);;Svi fajlovi (*)"
        )
        if not filename:
            return

        imported_layer = QgsVectorLayer(filename, "Uvezi_tacke_tmp", "ogr")
        if not imported_layer.isValid():
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Unable to load or invalid file!")
            return

        if imported_layer.geometryType() != QgsWkbTypes.PointGeometry:
            QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "The selected file does not contain points!")
            return
        # Find all existing point layers relevant for plugin:
        # Poles/Stubovi, Manholes/OKNA + svi elementi iz Placing elements (+ Joint Closures)
        node_layer_names = ['Poles', 'Manholes']
        try:
            # Joint Closures / Nastavci
            try:
                nm = NASTAVAK_DEF.get("name", "Joint Closures")
                if nm and nm not in node_layer_names:
                    node_layer_names.append(nm)
            except Exception:
                if 'Joint_closures' not in node_layer_names:
                    node_layer_names.append('Joint_closures')
            # svi elementi iz Placing elements (ELEMENT_DEFS)
            for d in ELEMENT_DEFS:
                nm = d.get("name")
                if nm and nm not in node_layer_names:
                    node_layer_names.append(nm)
        except Exception:
            pass

        existing_layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer)
            and lyr.geometryType() == QgsWkbTypes.PointGeometry
            and lyr.name() in node_layer_names
        ]
        layer_names = [lyr.name() for lyr in existing_layers]

        # Add option for creating new layer
        NEW_LAYER_OPTION_EN = "Create a new layer"
        NEW_LAYER_OPTION_SR = "Kreiraj novi sloj"  # for compatibility with old projects
        layer_names.append(NEW_LAYER_OPTION_EN)

        # Dialog for layer selection
        selected_layer_name, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Import points",
            "Select target layer for importing points:",
            layer_names,
            0, False
        )
        if not ok or not selected_layer_name:
            return

        # 1) Ako je izabrana opcija za novi sloj (bilo srpska ili engleska)
                # If new layer option is selected (either Serbian or English)
        if selected_layer_name in (NEW_LAYER_OPTION_EN, NEW_LAYER_OPTION_SR):
            new_layer_name, ok2 = QInputDialog.getText(
                self.iface.mainWindow(),
                "New layer",
                "Enter the name of the new layer (e.g., Poles, Joint Closures, OTB):"
            )
            if not ok2:
                return
            new_layer_name = (new_layer_name or "").strip()
            if not new_layer_name:
                return

            # If user asks for Poles/Stubovi – use standard Poles layer from StuboviPlugin.init_layer
            if new_layer_name == "Poles":
                try:
                    # init_layer creates or finds Poles layer with correct fields and style
                    self.init_layer()
                    layer = self.layer
                    if layer is None:
                        QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Unable to create or find 'Poles' layer!")
                        return
                except Exception:
                    QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Unable to create or find 'Poles' layer!")
                    return

            else:
                # Create new point layer for other types (Nastavci, ZOK, etc.)
                crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
                layer = QgsVectorLayer(f"Point?crs={crs}", new_layer_name, "memory")
                pr = layer.dataProvider()
                # Add fields depending on layer type
                if new_layer_name == "Joint_closures":
                    pr.addAttributes([QgsField("naziv", QVariant.String)])
                elif new_layer_name == "ZOK":
                    pr.addAttributes([QgsField("naziv", QVariant.String)])
                else:
                    # generički sloj sa jednim 'naziv' poljem
                    pr.addAttributes([QgsField("naziv", QVariant.String)])

                layer.updateFields()
                QgsProject.instance().addMapLayer(layer, True)

                # jednostavan simbol – ovde ne diramo Poles stil
                symbol = QgsSymbol.defaultSymbol(layer.geometryType())
                symbol_layer = symbol.symbolLayer(0)
                if symbol_layer is not None:
                    symbol_layer.setSize(10)
                    symbol_layer.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
                layer.renderer().setSymbol(symbol)
                layer.triggerRepaint()

        else:

            # Traži sloj po imenu
            layer = next((l for l in existing_layers if l.name() == selected_layer_name), None)
            if layer is None:
                QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Unable to find the target layer!")
                return
        
        # Additional safety: if target is Poles/Stubovi, ensure field 'tip' exists
        try:
            if layer.name() == "Poles" and "tip" not in layer.fields().names():
                layer.startEditing()
                layer.dataProvider().addAttributes([QgsField("tip", QVariant.String)])
                layer.updateFields()
                layer.commitChanges()
        except Exception:
            pass

        # Transformacija koordinata ako je potrebno
        src_crs = imported_layer.crs()
        dst_crs = layer.crs()
        transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

        layer.startEditing()
        broj_dodatih = 0
        for feat in imported_layer.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            # Transformacija ako je potrebno
            if src_crs != dst_crs:
                geom.transform(transform)

            # Add each individual Point (even from MultiPoint)
            if geom.type() == QgsWkbTypes.PointGeometry:
                if geom.isMultipart():
                    for pt in geom.asMultiPoint():
                        if pt:
                            new_feat = QgsFeature(layer.fields())
                            new_feat.setGeometry(QgsGeometry.fromPointXY(pt))
                            # Za Poles sloj podrazumevano postavi tip = "POLE"
                            try:
                                if layer.name() == "Poles" and "tip" in layer.fields().names():
                                    new_feat["tip"] = "POLE"
                            except Exception:
                                pass
                            layer.addFeature(new_feat)
                            broj_dodatih += 1
                else:
                    pt = geom.asPoint()
                    if pt:
                        new_feat = QgsFeature(layer.fields())
                        new_feat.setGeometry(QgsGeometry.fromPointXY(pt))
                        try:
                            if layer.name() == "Poles" and "tip" in layer.fields().names():
                                new_feat["tip"] = "POLE"
                        except Exception:
                            pass
                        layer.addFeature(new_feat)
                        broj_dodatih += 1
            # If it's Line or Polygon, skip!

        layer.commitChanges()
        layer.triggerRepaint()

        QMessageBox.information(self.iface.mainWindow(), "FiberQ", f"Imported {broj_dodatih} points into layer '{layer.name()}'!")

                

    #Automatska korekcija
    def _export_active_layer(self, only_selected: bool):
        """Helper to export active vector layer (all or only selected features)
        to one of the common exchange formats (GPX, KML/KMZ, GeoPackage)."""
        # Active layer must be a vector layer
        if not isinstance(self.iface.activeLayer(), QgsVectorLayer):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Export",
                "Please select an active vector layer before exporting."
            )
            return

        layer = self.iface.activeLayer()

        # Check selection if needed
        if only_selected and layer.selectedFeatureCount() == 0:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Export",
                "There are no selected features on the active layer."
            )
            return

        # Let user choose format
        formats = [
            ("GeoPackage (*.gpkg)", ".gpkg"),
            ("KML/KMZ (*.kml *.kmz)", ".kml"),
            ("GPX (*.gpx)", ".gpx"),
        ]
        items = [label for (label, _ext) in formats]
        choice, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Export format",
            "Select output format:",
            items,
            0,
            False,
        )
        if not ok or not choice:
            return

        ext = None
        for label, e in formats:
            if label == choice:
                ext = e
                break
        if not ext:
            return

        # Suggest filename next to current project (if any)
        project_path = QgsProject.instance().fileName()
        if project_path:
            base_dir = os.path.dirname(project_path)
        else:
            base_dir = os.path.expanduser("~")

        safe_layer_name = layer.name().replace(" ", "_")
        suggested = os.path.join(base_dir, safe_layer_name + ext)

        filename, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Export layer",
            suggested,
            choice,
        )
        if not filename:
            return

        # Ensure extension
        if not filename.lower().endswith(ext):
            filename += ext

        from qgis.core import QgsCoordinateReferenceSystem

        lower_ext = os.path.splitext(filename)[1].lower()

        # GPX/KML/KMZ are typically in WGS84
        if lower_ext in (".gpx", ".kml", ".kmz"):
            dest_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        else:
            dest_crs = layer.crs()

        # Try to guess driver for extension
        driver_name = ""
        try:
            driver_name = QgsVectorFileWriter.driverForExtension(lower_ext)
        except Exception:
            driver_name = ""

        if not driver_name:
            mapping = {
                ".gpkg": "GPKG",
                ".gpx": "GPX",
                ".kml": "KML",
                ".kmz": "KML",
            }
            driver_name = mapping.get(lower_ext, "")

        if not driver_name:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Export",
                f"Unknown driver for extension '{lower_ext}'."
            )
            return

        # Perform export using the best available API
                # Perform export using the best available API
        try:
            result = None

            if hasattr(QgsVectorFileWriter, "writeAsVectorFormatV3"):
                opts = QgsVectorFileWriter.SaveVectorOptions()
                opts.driverName = driver_name
                opts.fileEncoding = "UTF-8"
                opts.onlySelectedFeatures = bool(only_selected)
                ctx = QgsProject.instance().transformContext()
                result = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer,
                    filename,
                    ctx,
                    opts,
                )

            elif hasattr(QgsVectorFileWriter, "writeAsVectorFormatV2"):
                opts = QgsVectorFileWriter.SaveVectorOptions()
                opts.driverName = driver_name
                opts.fileEncoding = "UTF-8"
                opts.onlySelectedFeatures = bool(only_selected)
                ctx = QgsProject.instance().transformContext()
                result = QgsVectorFileWriter.writeAsVectorFormatV2(
                    layer,
                    filename,
                    ctx,
                    opts,
                )

            else:
                # Fallback to deprecated API
                result = QgsVectorFileWriter.writeAsVectorFormat(
                    layer,
                    filename,
                    "UTF-8",
                    dest_crs,
                    driver_name,
                    onlySelected=bool(only_selected),
                )

        except Exception as ex:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Export",
                f"Error while exporting:\n{ex}"
            )
            return

        # Normalize result: QGIS verzije mogu vraćati 1, 2 ili više vrednosti.
        if isinstance(result, tuple):
            if len(result) >= 2:
                res = result[0]
                err_message = result[1] or ""
            else:
                res = result[0]
                err_message = ""
        else:
            res = result
            err_message = ""

        if res != QgsVectorFileWriter.NoError:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Export",
                f"Export failed: {err_message}"
            )
        else:
            scope_txt = "selected features" if only_selected else "all features"
            QMessageBox.information(
                self.iface.mainWindow(),
                "Export",
                f"Successfully exported {scope_txt} from layer '{layer.name()}'\n"
                f"to:\n{filename}"
            )


    def export_selected_features(self):
        """Export only selected features of the active layer."""
        self._export_active_layer(only_selected=True)

    def export_all_features(self):
        """Export all features of the active layer."""
        self._export_active_layer(only_selected=False)


    def check_consistency(self):
        self.popravljive_greske = []
        layers = {
            lyr.name(): lyr
            for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer)
        }

        # podrži i srpske i engleske nazive
        trasa_layer = layers.get("Route")
        stubovi_layer = layers.get("Poles")
        okna_layer = layers.get("Manholes") or layers.get("OKNA")

        if trasa_layer and (stubovi_layer or okna_layer):
            stub_points = []
            if stubovi_layer:
                stub_points += [f.geometry().asPoint() for f in stubovi_layer.getFeatures()]
            if okna_layer:
                stub_points += [f.geometry().asPoint() for f in okna_layer.getFeatures()]

            for feat in trasa_layer.getFeatures():
                geom = feat.geometry()
                poly = geom.asPolyline()
                if not poly:
                    continue
                start = poly[0]
                end = poly[-1]
                # Početak
                if not any(QgsPointXY(sp).distance(start) < 1e-2 for sp in stub_points):
                    greska = {
                        'msg': f"Start of route (ID {feat.id()}) is NOT on a pole.",
                        'feat': feat,
                        'layer': trasa_layer,
                        'popravka': lambda f=feat: self.popravi_trasa_na_stub(f, must_start=True)
                    }
                    self.popravljive_greske.append(greska)
                # Kraj
                if not any(QgsPointXY(sp).distance(end) < 1e-2 for sp in stub_points):
                    greska = {
                        'msg': f"End of route (ID {feat.id()}) is NOT on a pole.",
                        'feat': feat,
                        'layer': trasa_layer,
                        'popravka': lambda f=feat: self.popravi_trasa_na_stub(f, must_start=False)
                    }
                    self.popravljive_greske.append(greska)

        if not self.popravljive_greske:
            QMessageBox.information(self.iface.mainWindow(), "Route correction", "No errors found!")
        else:
            dlg = KorekcijaDialog(self.popravljive_greske, self.iface.mainWindow())
            dlg.exec_()


        #Automatska korekcija
    def popravi_trasa_na_stub(self, trasa_feat, must_start=True):
            stubovi_layer = next((lyr for lyr in QgsProject.instance().mapLayers().values()
                                if lyr.geometryType() == QgsWkbTypes.PointGeometry 
                                and lyr.name() in ('Stubovi', 'Poles')), None)

            if not stubovi_layer:
                QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Layer 'Poles' not found!")
                return

            geom = trasa_feat.geometry()
            poly = geom.asPolyline()
            if not poly:
                return

            # Trazi najbliži stub za početak/kraj
            if must_start:
                trasa_point = poly[0]
                idx = 0
            else:
                trasa_point = poly[-1]
                idx = -1

            min_dist = None
            nearest_stub = None
            for stub_feat in stubovi_layer.getFeatures():
                stub_pt = stub_feat.geometry().asPoint()
                dist = QgsPointXY(stub_pt).distance(trasa_point)
                if min_dist is None or dist < min_dist:
                    min_dist = dist
                    nearest_stub = stub_pt

            # If pole is found, move route start/end to pole
            if nearest_stub and min_dist > 1e-2:
                poly[idx] = QgsPointXY(nearest_stub)
                new_geom = QgsGeometry.fromPolylineXY(poly)

                # Find layer 'Trasa' in project (QgsFeature doesn't have .layer())
                trasa_layer = next(
                    (lyr for lyr in QgsProject.instance().mapLayers().values()
                    if isinstance(lyr, QgsVectorLayer)
                    and lyr.name() in ('Route',)
                    and lyr.geometryType() == QgsWkbTypes.LineGeometry),
                    None
                )
                if not trasa_layer:
                    QMessageBox.warning(self.iface.mainWindow(), "FiberQ", "Route layer 'Route' not found!")
                    return


                trasa_layer.startEditing()
                trasa_layer.changeGeometry(trasa_feat.id(), new_geom)
                trasa_layer.commitChanges()
                trasa_layer.triggerRepaint()
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "FiberQ",
                    "Route has been automatically attached to a pole."
                )       

    # === CRTEŽI / ATTACHMENTS (DWG/DXF) ===
    def _drawing_key(self, layer, fid):
        return f"drawing_map/{layer.id()}/{int(fid)}"

    def _drawing_layers_key(self, layer, fid):
        return f"drawing_layers/{layer.id()}/{int(fid)}"

    def _drawing_layers_get(self, layer, fid):
        key = self._drawing_layers_key(layer, fid)
        s = QgsProject.instance().readEntry("StuboviPlugin", key, "")[0]
        return [x for x in (s.split(",") if s else []) if x]

    def _drawing_layers_set(self, layer, fid, layer_ids):
        key = self._drawing_layers_key(layer, fid)
        QgsProject.instance().writeEntry("StuboviPlugin", key, ",".join(layer_ids or []))

    def _drawing_get(self, layer, fid):
        key = self._drawing_key(layer, fid)
        return QgsProject.instance().readEntry("StuboviPlugin", key, "")[0]

    def _drawing_set(self, layer, fid, path):
        key = self._drawing_key(layer, fid)
        QgsProject.instance().writeEntry("StuboviPlugin", key, path)

    def _ensure_crtezi_group(self, subgroup_name):
        root = QgsProject.instance().layerTreeRoot()

        # Main group in Layers panel – now in English
        group = root.findGroup("Drawings")
        if not group:
            # backward-compat: if old group "Crtezi" already exists, rename it
            legacy = root.findGroup("Crteži")
            if legacy:
                try:
                    legacy.setName("Drawings")
                except Exception:
                    pass
                group = legacy
            else:
                group = root.addGroup("Drawings")

        # Podgrupa (Splices / Customers / ZOK / ODF / ODO / Other)
        sub = group.findGroup(subgroup_name)
        if not sub:
            sub = group.addGroup(subgroup_name)

        return sub


    def _guess_category_for_layer(self, layer):
        name = (layer.name() or "").lower()

        # still detecting by Serbian words in layer name,
        # but returning English subgroup names
        if "nastav" in name:
            return "Joint Closures"       # former "Nastavci"
        if "koris" in name:
            return "Customers"     # former "Korisnici"
        if "zok" in name:
            return "TB"
        if "odf" in name:
            return "ODF"
        if "odo" in name:
            return "OTB"
        return "Other"             # bivše "Ostalo"

    def _is_drawing_loaded(self, path: str) -> bool:
        import os, re
        if not path:
            return False

        def norm(p: str) -> str:
            try:
                return os.path.normcase(os.path.abspath(p)).replace("\\", "/")
            except Exception:
                return (p or "").replace("\\", "/")

        target = norm(path)
        target_base = os.path.basename(target)

        for lyr in QgsProject.instance().mapLayers().values():
            try:
                src = (lyr.source() or "")
                src_norm = src.replace("\\", "/")

                # 1) najčešće: "C:/x/file.dwg|layername=entities"
                if target and target in norm(src.split("|", 1)[0]):
                    return True

                # 2) dbname='C:/x/file.dwg' ...
                m = re.search(r"dbname\s*=\s*['\"]([^'\"]+)['\"]", src, flags=re.IGNORECASE)
                if m and norm(m.group(1)) == target:
                    return True

                # 3) path=C:/x/file.dwg (nekad u URI)
                m2 = re.search(r"(?:^|[&? ])path\s*=\s*([^& ]+)", src, flags=re.IGNORECASE)
                if m2 and norm(m2.group(1).strip("'\"")) == target:
                    return True

                # 4) fallback: basename match (da izbegnemo false-negative na egzotičnim URI formatima)
                if target_base and target_base.lower() in src_norm.lower():
                    return True

            except Exception:
                continue

        return False


    def _open_drawing_path(self, path):
        import os
        if not path or not os.path.exists(path):
            QMessageBox.warning(self.iface.mainWindow(), "Drawing", "The drawing path is invalid or the file does not exist.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _try_add_dwg_to_group(self, path, subgroup):
        # Pokušaj da učitaš DWG/DXF kao OGR slojeve; ako ne uspe, vrati [].
        import os
        base_name = os.path.basename(path)

        tmp = QgsVectorLayer(path, base_name, "ogr")
        added_ids = []

        if tmp.isValid():
            sublayers = []
            try:
                sublayers = tmp.dataProvider().subLayers() or tmp.subLayers() or []
            except Exception:
                sublayers = tmp.subLayers() if hasattr(tmp, "subLayers") else []

            if not sublayers:
                lyr = QgsVectorLayer(path, base_name, "ogr")
                if lyr.isValid():
                    QgsProject.instance().addMapLayer(lyr, False)
                    subgroup.addLayer(lyr)
                    added_ids.append(lyr.id())
            else:
                for s in sublayers:
                    parts = str(s).split(":")
                    lname = parts[1] if len(parts) > 1 else parts[0]
                    for key in ("layername", "layer"):
                        ds = f"{path}|{key}={lname}"
                        vl = QgsVectorLayer(ds, f"{base_name}:{lname}", "ogr")
                        if vl.isValid():
                            QgsProject.instance().addMapLayer(vl, False)
                            subgroup.addLayer(vl)
                            added_ids.append(vl.id())
                            break
        return added_ids


    def ui_add_drawing(self):
        layer = self.iface.activeLayer()

        # Guard: only vector layers can have selected features
        from qgis.core import QgsVectorLayer
        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.information(self.iface.mainWindow(), "Drawing",
                                "Select a VECTOR layer and one or more features, then try again.")
            return

        if layer.selectedFeatureCount() == 0:
            QMessageBox.information(self.iface.mainWindow(), "Drawing",
                                "Select one or more features and try again.")
            return

        feats = layer.selectedFeatures()

        # 2) Izbor fajla
        path, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(), "Select drawing", "", "DWG/DXF (*.dwg *.dxf);;All files (*.*)")
        if not path:
            return
        # 3) Izbor pot-odra (kategorije)
        default_cat = self._guess_category_for_layer(layer)
        cats = ["Joint Closures", "Customers", "TB", "OTB", "ODF", "Other"]
        ok = True
        cat = default_cat
        try:
            cat, ok = QInputDialog.getItem(
                self.iface.mainWindow(),
                "Drawing layer",
                "Select a sub-layer in 'Drawings':",
                cats,
                cats.index(default_cat) if default_cat in cats else 0,
                False
            )

        except Exception:
            ok = True
            cat = default_cat
        if not ok:
            return
        # 4) Kreiraj grupu i probaj da učitaš DWG/DXF
        subgroup = self._ensure_crtezi_group(cat)
        added_layer_ids = self._try_add_dwg_to_group(path, subgroup)
        # 5) Upamti asocijaciju za svaku selektovanu geometriju
        for f in feats:
            self._drawing_set(layer, f.id(), path)
            self._drawing_layers_set(layer, f.id(), added_layer_ids)
        QMessageBox.information(self.iface.mainWindow(), "Drawing", f"Drawing is associated with {len(feats)} feature(s).")

    def ui_open_drawing_click(self):
        try:
            self._open_tool
        except AttributeError:
            self._open_tool = OpenDrawingMapTool(self)
        self.iface.mapCanvas().setMapTool(self._open_tool)
        self.iface.messageBar().pushInfo("Drawing", "Click on a feature to open its drawing (ESC or right click to exit).")


    # === OKNA (Kanalizacija) ===
    def open_okno_workflow(self):
        """Sekvenca: 1) izbor tipa okna -> 2) unos podataka -> 3) klik na mapu i polaganje."""
        try:
            # 1) izbor tipa
            dlg1 = OknoTypeDialog(self)
            if dlg1.exec_() != QDialog.Accepted:
                return
            okno_tip = dlg1.selected_type()

            # 2) detalji
            dlg2 = OknoDetailsDialog(self, prefill_type=okno_tip)
            if dlg2.exec_() != QDialog.Accepted:
                return
            attrs = dlg2.values()  # dict sa vrednostima polja

            # 3) aktiviraj map alat za klik
            self._okno_pending_attrs = attrs
            self._okno_place_tool = OknoPlaceTool(self.iface, self)
            self.iface.mapCanvas().setMapTool(self._okno_place_tool)
            self.iface.messageBar().pushInfo("Placing manhole", "Click on the map to place the manhole (ESC to exit).")
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Manhole", f"Error: {e}")

    def _ensure_okna_layer(self):
        """Vrati (kreiraj ako treba) sloj za okna / manholes."""
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                name = lyr.name().strip()
                if name in ("Manholes",) and lyr.geometryType() == QgsWkbTypes.PointGeometry:
                    try:
                        self._apply_okna_style(lyr)
                        self._apply_okna_field_aliases(lyr)
                        self._set_okna_layer_alias(lyr)
                        self._move_layer_to_top(lyr)
                    except Exception:
                        pass
                    return lyr
            except Exception:
                continue

        crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        # novi sloj će se zvati "Manholes" u projektima
        layer = QgsVectorLayer(f"Point?crs={crs}", "Manholes", "memory")
        pr = layer.dataProvider()
        fields = [
            QgsField("broj_okna", QVariant.String),
            QgsField("tip_okna", QVariant.String),
            QgsField("vrsta_okna", QVariant.String),
            QgsField("polozaj_okna", QVariant.String),
            QgsField("adresa", QVariant.String),
            QgsField("stanje", QVariant.String),
            QgsField("god_ugrad", QVariant.Int),
            # Detalji
            QgsField("opis", QVariant.String),
            QgsField("dimenzije", QVariant.String),
            QgsField("mat_zida", QVariant.String),
            QgsField("mat_poklop", QVariant.String),
            QgsField("odvodnj", QVariant.String),
            QgsField("poklop_tes", QVariant.Bool),
            QgsField("poklop_lak", QVariant.Bool),
            QgsField("br_nosaca", QVariant.Int),
            QgsField("debl_zida", QVariant.Double),
            QgsField("lestve", QVariant.String),
        ]
        pr.addAttributes(fields)
        layer.updateFields()
        QgsProject.instance().addMapLayer(layer, True)
        self._apply_okna_style(layer)
        self._apply_okna_field_aliases(layer)
        self._set_okna_layer_alias(layer)
        self._move_layer_to_top(layer)
        return layer


    
    def _move_layer_to_top(self, layer):
        """Move layer to top in layer tree and in 'Custom Layer Order' (if enabled)."""
        try:
            proj = QgsProject.instance()
            root = proj.layerTreeRoot()
            node = root.findLayer(layer.id())
            if not node:
                proj.addMapLayer(layer, True)
                node = root.findLayer(layer.id())
                if not node:
                    return
            parent = node.parent() or root
            children = list(parent.children())
            idx = None
            for i, ch in enumerate(children):
                try:
                    if hasattr(ch, "layerId") and ch.layerId() == layer.id():
                        idx = i
                        break
                except Exception:
                    pass
            if idx is not None and idx > 0:
                taken = parent.takeChild(idx)
                parent.insertChildNode(0, taken)
            # custom layer order
            try:
                if root.hasCustomLayerOrder():
                    order = list(root.customLayerOrder())
                    order = [l for l in order if l and l.id() != layer.id()]
                    order.insert(0, layer)
                    root.setCustomLayerOrder(order)
            except Exception:
                pass
        except Exception:
            try:
                QgsProject.instance().addMapLayer(layer, True)
            except Exception:
                pass


    

    
    def _apply_okna_style(self, layer):
        """OKNA: kvadrat u map jedinicama (metri) + fiksna oznaka "KO <broj>"
        koja je UVEK IZNAD simbola i ima konstantnu veličinu (ne menja se pri zumiranju).
        - marker: RenderMetersInMapUnits (ponaša se kao stub pri zumiranju)
        - outline: u mm (uvek ista debljina crtanja)
        - label: OffsetFromPoint, Quadrant ABOVE, offset i veličina u mm (fiksno)
        """
        if not layer or not layer.isValid():
            return
        try:
            from qgis.core import (
    QgsVectorFileWriter, QgsCoordinateTransformContext,
                QgsMarkerSymbol, QgsSingleSymbolRenderer,
                QgsVectorLayerSimpleLabeling, QgsPalLayerSettings,
                QgsTextFormat, QgsTextBufferSettings,
                QgsUnitTypes, Qgis, QgsSymbolLayer, QgsMapUnitScale
            )
            from qgis.PyQt.QtGui import QColor, QFont

            # --- SIMBOL (map units / meters) ---
            size_m = 10.0  # ivica kvadrata u metrima
            sym = QgsMarkerSymbol.createSimple({
                'name': 'square',
                'size': str(size_m),
                'color': '255,255,255,0',
                'outline_color': '#000000',
                'outline_width': '0.8'
            })
            sl = sym.symbolLayer(0)

            # key: marker size in METERS on map
            try:
                sl.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
            except Exception:
                sl.setSizeUnit(QgsUnitTypes.RenderMapUnits)

            # kontura u mm (uvek isto debela)
            try:
                sl.setOutlineWidthUnit(QgsUnitTypes.RenderMillimeters)
            except Exception:
                try:
                    sl.setStrokeWidthUnit(QgsUnitTypes.RenderMillimeters)
                except Exception:
                    pass

            # reset svih potencijalnih data-defined/scale osobina
            try:
                ddp = sl.dataDefinedProperties()
                if ddp:
                    from qgis.core import QgsProperty
                    ddp.setProperty(QgsSymbolLayer.PropertySize, QgsProperty())
                    sl.setDataDefinedProperties(ddp)
            except Exception:
                pass
            try:
                sl.setMapUnitScale(QgsMapUnitScale())
            except Exception:
                pass

            layer.setRenderer(QgsSingleSymbolRenderer(sym))

            # --- LABEL: uvek iznad + fiksna veličina ---
            s = QgsPalLayerSettings()
            s.enabled = True
            s.isExpression = True
            s.fieldName = (
                "CASE WHEN length(coalesce(\"broj_okna\", ''))>0 "
                "THEN concat('MH ', \"broj_okna\") ELSE '' END"
            )

            # Forsiraj 'offset from point' – pozicija neće skakati
            placed = False
            for cand in (
                getattr(Qgis, 'LabelPlacement', None) and getattr(Qgis.LabelPlacement, 'OffsetFromPoint', None),
                getattr(QgsPalLayerSettings, 'OffsetFromPoint', None),
            ):
                if cand is not None:
                    try:
                        s.placement = cand
                        placed = True
                        break
                    except Exception:
                        pass
            if not placed:
                # poslednja opcija – ostavi OverPoint, ali ćemo dodati offset
                try:
                    s.placement = getattr(QgsPalLayerSettings, 'OverPoint', s.placement)
                except Exception:
                    pass

            # Kvadrant IZNAD tačke (robustno za različite verzije QGIS-a)
            for attr_name in ('quadrantPosition', 'quadOffset'):
                if hasattr(s, attr_name):
                    enum_val = getattr(QgsPalLayerSettings, 'QuadrantAbove', None)
                    if enum_val is None:
                        try:
                            enum_val = getattr(Qgis, 'LabelQuadrantPosition').Above
                        except Exception:
                            enum_val = None
                    if enum_val is not None:
                        try:
                            setattr(s, attr_name, enum_val)
                            break
                        except Exception:
                            pass

            # Fiksni offset malo iznad markera
            s.xOffset = 0.0
            s.yOffset =  5.0
            s.offsetUnits = QgsUnitTypes.RenderMapUnits

            tf = QgsTextFormat()
            # veličina u milimetrima -> ne menja se pri zumu
            tf.setSize( 8.0)
            try:
                tf.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            except Exception:
                pass
            f = QFont(); f.setBold(True); tf.setFont(f)
            buf = QgsTextBufferSettings()
            buf.setEnabled(True); buf.setSize(1.0)
            buf.setColor(QColor(255, 255, 255)); buf.setOpacity(1.0)
            tf.setBuffer(buf)

            s.setFormat(tf)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
            layer.setLabelsEnabled(True)
            layer.triggerRepaint()
        except Exception:
            pass

    # === CEVI: utili za slojeve i stil ===
    
    def _move_group_to_top(self, group_name="CEVI"):
        """Pomeri grupu na vrh u layer tree-u; u 'Custom Layer Order' slojeve grupe postavi na početak redosleda."""
        try:
            proj = QgsProject.instance()
            root = proj.layerTreeRoot()

            # if "CEVI" was requested, try with English group name too
            group = root.findGroup(group_name)
            if group is None and group_name == "CEVI":
                group = root.findGroup("Pipes")

            if not group:
                return

            parent = group.parent() or root
            children = list(parent.children())

            # nađi indeks grupe po imenu
            idx = None
            try:
                gname = group.name()
            except Exception:
                gname = group_name
            for i, ch in enumerate(children):
                try:
                    if getattr(ch, "name", lambda: None)() == gname and not hasattr(ch, "layerId"):
                        idx = i
                        break
                except Exception:
                    pass
            if idx is not None and idx > 0:
                taken = parent.takeChild(idx)
                parent.insertChildNode(0, taken)

            # custom layer order – sve slojeve iz grupe na početak
            try:
                if root.hasCustomLayerOrder():
                    order = list(root.customLayerOrder())

                    def _collect_layers(node):
                        out = []
                        for ch in getattr(node, 'children', lambda: [])():
                            try:
                                if hasattr(ch, "layer") and ch.layer():
                                    out.append(ch.layer())
                                else:
                                    out.extend(_collect_layers(ch))
                            except Exception:
                                pass
                        return out

                    group_layers = _collect_layers(group)
                    keep = [l for l in order if l not in group_layers]
                    root.setCustomLayerOrder(list(group_layers) + keep)
            except Exception:
                pass
        except Exception:
            pass

    def _ensure_cevi_group(self):
        """Return or create group for pipes in legend.
        Internally we still use name 'CEVI', but display 'Pipes' to user.
        """
        proj = QgsProject.instance()
        root = proj.layerTreeRoot()

        # prihvati i staro i novo ime grupe
        group = root.findGroup("CEVI") or root.findGroup("Pipes")
        if group is None:
            try:
                group = root.insertGroup(0, "Pipes")  # top of tree, novo ime
            except Exception:
                group = root.addGroup("Pipes")
        else:
            # if still old name, rename only for user-view
            try:
                if group.name() == "CEVI":
                    group.setName("Pipes")
            except Exception:
                pass

        # sigurnosno podizanje na vrh i prilagođavanje render order-a
        try:
            self._move_group_to_top("CEVI")
        except Exception:
            pass
        return group

    def _apply_pipe_field_aliases(self, layer):
        """English aliases for PE / transition pipe layer fields."""
        alias_map = {
            "materijal": "Material",
            "kapacitet": "Capacity",
            "fi": "Diameter (mm)",
            "od": "From",
            "do": "To",
            "duzina_m": "Length (m)",
        }
        try:
            for field_name, alias in alias_map.items():
                idx = layer.fields().indexOf(field_name)
                if idx != -1:
                    layer.setFieldAlias(idx, alias)
        except Exception:
            pass

    def _set_pipe_layer_alias(self, layer):
        """
        Display pipe layer names in English.
        Supports both old and new names, to not break existing projects.
        """
        try:
            lname = (layer.name() or "").strip()

            # PE cevi -> PE pipes
            if lname in ("PE cevi", "PE pipes"):
                layer.setName("PE pipes")

            # Prelazne cevi -> Transition pipes
            elif lname in ("Prelazne cevi", "Transition pipes"):
                layer.setName("Transition pipes")
        except Exception:
            pass


    def _ensure_pipe_layer(self, name):
        """
        Create/return line memory layer in CEVI group with basic fields.

        `name` is the old internal Serbian name ("PE cevi" or "Prelazne cevi").
        In project we display English name to user, but here we support both.
        """
        prj = QgsProject.instance()

        alias_map = {
            "PE cevi": "PE pipes",
            "Prelazne cevi": "Transition pipes",
        }
        target_names = {name}
        if name in alias_map:
            target_names.add(alias_map[name])

        # 1) Find if layer with Serbian or English name already exists
        for lyr in prj.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.LineGeometry
                    and lyr.name() in target_names
                ):
                    try:
                        self._apply_pipe_field_aliases(lyr)
                        self._set_pipe_layer_alias(lyr)
                    except Exception:
                        pass
                    return lyr
            except Exception:
                pass

        # 2) If doesn't exist – create new layer with internal Serbian name
        crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        layer = QgsVectorLayer(f"LineString?crs={crs}", name, "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("materijal", QVariant.String),
            QgsField("kapacitet", QVariant.String),
            QgsField("fi", QVariant.Int),
            QgsField("od", QVariant.String),
            QgsField("do", QVariant.String),
            QgsField("duzina_m", QVariant.Double),
        ])
        layer.updateFields()

        # map tip (hover)
        try:
            layer.setMapTipTemplate(
                "<b>[% \"materijal\" %] [% \"kapacitet\" %]</b><br/>Ø [% \"fi\" %] mm"
            )
        except Exception:
            pass

        # Add to CEVI/Pipes group
        prj.addMapLayer(layer, False)
        try:
            group = self._ensure_cevi_group()
            group.addLayer(layer)
        except Exception:
            prj.addMapLayer(layer, True)

        # Pomeri grupu na vrh (iznad OSM)
        try:
            self._move_group_to_top("CEVI")
        except Exception:
            pass

        # Move layer to top within group
        try:
            self._move_layer_to_top(layer)
        except Exception:
            pass

        # field aliases + user-visible layer name
        try:
            self._apply_pipe_field_aliases(layer)
            self._set_pipe_layer_alias(layer)
        except Exception:
            pass

        return layer


    def _ensure_pe_cev_layer(self):
        # Interno ime sloja ostaje 'PE cevi'
        return self._ensure_pipe_layer("PE cevi")

    def _ensure_prelazna_cev_layer(self):
        # Interno ime sloja ostaje 'Prelazne cevi'
        return self._ensure_pipe_layer("Prelazne cevi")


    def _apply_pipe_style(self, layer, color_hex, width_mm):
        """Jednostavan line renderer sa zadatom bojom i širinom u mm (fiksno na ekranu)."""
        try:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            sl = QgsSimpleLineSymbolLayer()
            sl.setColor(QColor(color_hex))
            sl.setWidth(float(width_mm))
            sl.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            # malo zaobljeni uglovi za lepši izgled
            try:
                sl.setJoinStyle(Qt.RoundJoin)
                sl.setCapStyle(Qt.RoundCap)
            except Exception:
                pass
            symbol.deleteSymbolLayer(0)
            symbol.appendSymbolLayer(sl)
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.triggerRepaint()
        except Exception:
            pass

    # === CEVI: workflow-i ===
    def open_pe_cev_workflow(self):
        try:
            dlg = PECevDialog(self)
            if dlg.exec_() != QDialog.Accepted:
                return
            vals = dlg.values()
            self._pending_pipe = {'kind':'PE', **vals}
            tool = PipePlaceTool(self.iface, self, 'PE', vals)
            self.iface.mapCanvas().setMapTool(tool)
            self.iface.messageBar().pushInfo("PE duct", "Click start and end on the route/manhole to place the PE duct.")
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "PE duct", f"Error: {e}")

    def open_prelazna_cev_workflow(self):
        try:
            dlg = PrelaznaCevDialog(self)
            if dlg.exec_() != QDialog.Accepted:
                return
            vals = dlg.values()
            self._pending_pipe = {'kind':'PRELAZ', **vals}
            tool = PipePlaceTool(self.iface, self, 'PRELAZ', vals)
            self.iface.mapCanvas().setMapTool(tool)
            self.iface.messageBar().pushInfo("Transition duct", "Click start and end on the route/manhole to place the transition duct.")
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Transition duct", f"Error: {e}")

    def open_fiberq_settings(self):
        dlg = FiberQSettingsDialog(self.iface.mainWindow())
        dlg.exec_()


class OknoTypeDialog(QDialog):
    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        self.setWindowTitle("Choose manhole type")
        self.resize(420, 520)
        v = QVBoxLayout(self)
        self.list = QListWidget()
        v.addWidget(self.list)
        # Minimalni skup tipova po uzoru na slike (možete naknadno proširiti)
        types = [
            "Standard cable manhole",
            "Existing standard cable manhole",
            "Standard octagonal 200x130x190",
            "Standard octagonal 250x150x190",
            "Standard octagonal cut 200x120x190",
            "Standard octagonal cut 220x128x190",
            "Mounted mini cable manhole",
            "Existing mini cable manhole",
            "Mounted mini manhole type MB 1",
            "Mounted mini manhole type MB 2",
            "Mounted mini manhole type MB 3",
            "Mounted mini manhole type MB 5",
            "Mounted mini manhole type MBi",
            "Mounted mini manhole type MB1i",
            "Mounted mini manhole type MBr",
            "Mounted mini manhole type Mufa (micro ducts)",
            "Mounted mini manhole type Duct End (micro ducts)",
        ]
        for t in types:
            self.list.addItem(t)
        if self.list.count() > 0:
            self.list.setCurrentRow(0)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        v.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def selected_type(self):
        it = self.list.currentItem()
        return it.text() if it else ""

class OknoDetailsDialog(QDialog):
    """Drugi korak – unos detalja okna (po uzoru na sliku)."""
    def __init__(self, core, prefill_type=""):
        super().__init__(core.iface.mainWindow())
        self.setWindowTitle("Enter manhole details")
        self.resize(520, 520)
        v = QVBoxLayout(self)
        form = QFormLayout()
        v.addLayout(form)

        from qgis.PyQt.QtWidgets import QComboBox, QSpinBox
        self.ed_broj = QLineEdit()
        self.ed_tip = QLineEdit(prefill_type)
        self.cmb_vrsta = QComboBox(); self.cmb_vrsta.addItems(["Standard", "Mounted", "Existing"])
        self.ed_polozaj = QLineEdit()
        self.ed_adresa = QLineEdit()
        self.cmb_stanje = QComboBox(); self.cmb_stanje.addItems(["Planned", "Executed", "Existing"])
        self.spin_god = QSpinBox(); self.spin_god.setRange(1900, 2100); self.spin_god.setValue(2025)

        # Detaljnije
        self.ed_opis = QLineEdit()
        self.ed_dim = QLineEdit()
        self.ed_mat_zid = QLineEdit()
        self.ed_mat_poklop = QLineEdit()
        self.ed_odvod = QLineEdit()
        self.chk_poklop_teski = QCheckBox()
        self.chk_poklop_laki = QCheckBox()
        self.spin_br_nos = QSpinBox(); self.spin_br_nos.setRange(0, 20)
        self.spin_debl = QLineEdit()  # keep as text/double
        self.ed_lestve = QLineEdit()

        form.addRow("Manhole ID:", self.ed_broj)
        form.addRow("Manhole type:", self.ed_tip)
        form.addRow("Manhole category:", self.cmb_vrsta)
        form.addRow("Manhole location:", self.ed_polozaj)
        form.addRow("Address:", self.ed_adresa)
        form.addRow("Manhole status:", self.cmb_stanje)
        form.addRow("Installation year:", self.spin_god)

        # Separator
        form.addRow(QLabel("Detailed manhole information"), QLabel(""))
        form.addRow("Manhole description:", self.ed_opis)
        form.addRow("Dimensions (cm):", self.ed_dim)
        form.addRow("Wall material:", self.ed_mat_zid)
        form.addRow("Cover material:", self.ed_mat_poklop)
        form.addRow("Drainage:", self.ed_odvod)
        form.addRow("Heavy covers:", self.chk_poklop_teski)
        form.addRow("Light covers:", self.chk_poklop_laki)
        form.addRow("Number of supports:", self.spin_br_nos)
        form.addRow("Wall thickness (cm):", self.spin_debl)
        form.addRow("Ladders:", self.ed_lestve)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        v.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def values(self):
        def val(w):
            if isinstance(w, QComboBox):
                return w.currentText()
            if isinstance(w, QCheckBox):
                return bool(w.isChecked())
            if hasattr(w, 'value'):
                try:
                    return w.value()
                except Exception:
                    pass
            return w.text() if hasattr(w, 'text') else None

        return {
            'broj_okna': val(self.ed_broj),
            'tip_okna': val(self.ed_tip),
            'vrsta_okna': val(self.cmb_vrsta),
            'polozaj_okna': val(self.ed_polozaj),
            'adresa': val(self.ed_adresa),
            'stanje': val(self.cmb_stanje),
            'god_ugrad': val(self.spin_god),
            'opis': val(self.ed_opis),
            'dimenzije': val(self.ed_dim),
            'mat_zida': val(self.ed_mat_zid),
            'mat_poklop': val(self.ed_mat_poklop),
            'odvodnj': val(self.ed_odvod),
            'poklop_tes': val(self.chk_poklop_teski),
            'poklop_lak': val(self.chk_poklop_laki),
            'br_nosaca': val(self.spin_br_nos),
            'debl_zida': float(self.spin_debl.text()) if self.spin_debl.text().strip() else None,
            'lestve': val(self.ed_lestve),
        }

class OknoPlaceTool(QgsMapToolEmitPoint):
    """Treći korak – klik na mapu da se doda 'OKNA' feature sa prethodno unetim atributima."""
    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin

    def canvasReleaseEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        snap_point = None
        min_dist = None
        
        # Snap to route (vertices + segment midpoints)
        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                    trasa_layer = lyr
                    break
            except Exception:
                pass
        if trasa_layer and trasa_layer.featureCount() > 0:
            for feat in trasa_layer.getFeatures():
                geom = feat.geometry()
                if geom.isMultipart():
                    lines = geom.asMultiPolyline()
                else:
                    lines = [geom.asPolyline()]
                for line in lines:
                    if not line:
                        continue
                    for p in line:
                        d = QgsPointXY(point).distance(QgsPointXY(p))
                        if min_dist is None or d < min_dist:
                            min_dist = d
                            snap_point = QgsPointXY(p)
                    for i in range(len(line)-1):
                        mid = QgsPointXY((line[i].x()+line[i+1].x())/2, (line[i].y()+line[i+1].y())/2)
                        d = QgsPointXY(point).distance(mid)
                        if min_dist is None or d < min_dist:
                            min_dist = d
                            snap_point = mid
        tol = self.iface.mapCanvas().mapUnitsPerPixel() * 20
        if snap_point is not None and min_dist is not None and min_dist < tol:
            point = snap_point
        layer = self.plugin._ensure_okna_layer()
        pr = layer.dataProvider()

        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point)))
        attrs = getattr(self.plugin, '_okno_pending_attrs', {}) or {}

        # obavezno ime/oznaka
        broj = attrs.get('broj_okna') or ''
        f['broj_okna'] = broj
        # ostali
        for key in ['tip_okna','vrsta_okna','polozaj_okna','adresa','stanje','god_ugrad','opis','dimenzije','mat_zida','mat_poklop','odvodnj','poklop_tes','poklop_lak','br_nosaca','debl_zida','lestve']:
            if key in attrs and key in layer.fields().names():
                f[key] = attrs.get(key)

        try:
            layer.startEditing()
            layer.addFeature(f)
            layer.commitChanges()
        except Exception:
            pr.addFeatures([f])
        layer.updateExtents()
        layer.triggerRepaint()
        self.plugin._apply_okna_style(layer)
        self.plugin._move_layer_to_top(layer)

        # ostani u alatu za ponavljanje polaganja; izlaz na ESC / desni klik
        self.iface.messageBar().pushInfo("Manholes", f"Manhole placed: {broj or '(bez oznake)'}")

    def keyPressEvent(self, event):
        """ESC prekida alat za polaganje okna."""
        if event.key() == Qt.Key_Escape:
            try:
                self.iface.mapCanvas().unsetMapTool(self)
            except Exception:
                pass

    def canvasPressEvent(self, event):
        """Desni klik takođe prekida alat bez polaganja novog okna."""
        if event.button() == Qt.RightButton:
            try:
                self.iface.mapCanvas().unsetMapTool(self)
            except Exception:
                pass

class CablePickerDialog(QDialog):
    """
    Dijalog za izbor i unos parametara položenog kabla.
    - Umesto "kapacitet" sada se unose "Broj cevcica" i "Broj vlakana".
    - Dopunjeno poljima iz specifikacije (slika u prilogu).
    """
    def __init__(self, parent=None, default_vrsta=None, default_podtip=None, default_tip=None, default_color=None, color_codes=None):
        super().__init__(parent)
        from qgis.PyQt.QtWidgets import QFormLayout, QComboBox, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QLineEdit, QCheckBox, QLabel
        self.setWindowTitle("Parametri kabla")

                # --- Basic lists (INTERNAL values remain in Serbian) ---
        # kodovi
        self.vrste = ["podzemni", "vazdusni"]
        self.podtipi = ["glavni", "distributivni", "razvodni"]

        # English labels for display in dialog
        self.vrste_labels = {
            "podzemni": "Underground",
            "vazdusni": "Aerial",
        }
        self.podtipi_labels = {
            "glavni": "Backbone",
            "distributivni": "Distribution",
            "razvodni": "Drop",
        }

        # tipovi po vrsti – od sada i kodovi i prikaz su EN
        self.tipovi_po_vrsti = {
            "podzemni": ["Optical", "Copper"],
            "vazdusni": ["Optical", "Copper"],
        }
        self.tip_labels = {
            "Optical": "Optical",
            "Copper": "Copper",
        }


        # stanje / polaganje – kodovi + etikete
        self.stanja = ["Projektovano", "Postojeće", "U izgradnji"]
        self.stanja_labels = {
            "Projektovano": "Planned",
            "Postojeće": "Existing",
            "U izgradnji": "Under construction",
        }
        self.polaganja = ["Podzemno", "Vazdusno"]
        self.polaganja_labels = {
            "Podzemno": "Underground",
            "Vazdusno": "Aerial",
        }

        self.color_codes = color_codes or []


        layout = QFormLayout(self)

        # --- Osnovno ---
        self.cb_vrsta = QComboBox()
        for code in self.vrste:
            self.cb_vrsta.addItem(self.vrste_labels.get(code, code), code)  # text = EN, data = SR

        self.cb_podtip = QComboBox()
        for code in self.podtipi:
            self.cb_podtip.addItem(self.podtipi_labels.get(code, code), code)

        self.cb_tip = QComboBox()

        self.cb_color = QComboBox()
        self.cb_color.addItems(self.color_codes)

        # --- Novi kapacitet (zamenjuje staro "kapacitet") ---
        self.sb_cevcice = QSpinBox(); self.sb_cevcice.setRange(0, 96); self.sb_cevcice.setValue(0)
        self.sb_vlakna = QSpinBox(); self.sb_vlakna.setRange(0, 864); self.sb_vlakna.setValue(0)

        # --- Detalji iz specifikacije ---
        self.le_tip_kabla = QLineEdit()
        self.cb_vrsta_vlakana = QComboBox(); self.cb_vrsta_vlakana.addItems(["SM", "MM"])
        self.le_vrsta_omotaca = QLineEdit()
        self.le_vrsta_armature = QLineEdit()
        self.le_talasno = QLineEdit()
        self.le_naziv = QLineEdit()
        self.ds_slabljenje = QDoubleSpinBox(); self.ds_slabljenje.setDecimals(3); self.ds_slabljenje.setRange(0.0, 999.0)
        self.ds_hrom_disp = QDoubleSpinBox(); self.ds_hrom_disp.setDecimals(3); self.ds_hrom_disp.setRange(0.0, 9999.0)

        self.cb_stanje = QComboBox()
        for code in self.stanja:
            self.cb_stanje.addItem(self.stanja_labels.get(code, code), code)

        self.cb_polaganje = QComboBox()
        for code in self.polaganja:
            self.cb_polaganje.addItem(self.polaganja_labels.get(code, code), code)

        self.le_vrsta_mreze = QLineEdit()
        self.sb_godina = QSpinBox(); self.sb_godina.setRange(1900, 2100); self.sb_godina.setValue(2025)


        # Učitaj default cable type iz FiberQ Settings i upiši u "Tip kabla"
        try:
            from qgis.core import QgsSettings
            s = QgsSettings()
            default_cable = s.value("FiberQ/default_cable_type", "", type=str)
            if default_cable:
                self.le_tip_kabla.setText(default_cable)
        except Exception:
            pass


        # konstruktivne karakteristike (checkbox -> 0/1)
        self.ch_vlakna_u_cevcicama = QCheckBox()
        self.ch_sa_uzlepljenim = QCheckBox()
        self.ch_punjeni = QCheckBox()
        self.ch_sa_arm_vlaknima = QCheckBox()
        self.ch_bez_metalnih = QCheckBox()

        # default vrednosti
        if default_vrsta and default_vrsta in self.vrste:
            idx = self.cb_vrsta.findData(default_vrsta)
            if idx >= 0:
                self.cb_vrsta.setCurrentIndex(idx)
            # laying mapped from kind (code remains Serbian)
            pol_code = "Vazdusno" if "vazdu" in default_vrsta.lower() else "Podzemno"
            idx_pol = self.cb_polaganje.findData(pol_code)
            if idx_pol >= 0:
                self.cb_polaganje.setCurrentIndex(idx_pol)

        if default_podtip and default_podtip in self.podtipi:
            idx = self.cb_podtip.findData(default_podtip)
            if idx >= 0:
                self.cb_podtip.setCurrentIndex(idx)

        # povezivanje da se lista tipova menja kada se promeni vrsta
        def refresh_tipovi():
            vr_code = self.cb_vrsta.currentData()
            self.cb_tip.clear()
            for code in self.tipovi_po_vrsti.get(vr_code, []):
                self.cb_tip.addItem(self.tip_labels.get(code, code), code)

        self.cb_vrsta.currentIndexChanged.connect(lambda _=None: refresh_tipovi())
        refresh_tipovi()

        if default_tip:
            idx_tip = self.cb_tip.findData(default_tip)
            if idx_tip >= 0:
                self.cb_tip.setCurrentIndex(idx_tip)

        if default_color and default_color in self.color_codes:
            self.cb_color.setCurrentText(default_color)


        # --- Redovi ---
        layout.addRow("Cable route type:", self.cb_vrsta)
        layout.addRow("Cable class:", self.cb_podtip)
        layout.addRow("Type:", self.cb_tip)
        layout.addRow("Color code:", self.cb_color)
        layout.addRow("Number of tubes:", self.sb_cevcice)
        layout.addRow("Number of fibers:", self.sb_vlakna)
        layout.addRow(QLabel("— Additional data —"))
        layout.addRow("Cable type:", self.le_tip_kabla)
        layout.addRow("Fiber type:", self.cb_vrsta_vlakana)
        layout.addRow("Sheath type:", self.le_vrsta_omotaca)
        layout.addRow("Armature type:", self.le_vrsta_armature)
        layout.addRow("Wavelength region:", self.le_talasno)
        layout.addRow("Name:", self.le_naziv)
        layout.addRow("Attenuation (dB/km):", self.ds_slabljenje)
        layout.addRow("Chromatic dispersion (ps/nm×km):", self.ds_hrom_disp)
        layout.addRow("Cable condition:", self.cb_stanje)
        layout.addRow("Cable laying:", self.cb_polaganje)
        layout.addRow("Network type:", self.le_vrsta_mreze)
        layout.addRow("Installation year:", self.sb_godina)
        layout.addRow("With fibers in tubes:", self.ch_vlakna_u_cevcicama)
        layout.addRow("With glued element:", self.ch_sa_uzlepljenim)
        layout.addRow("Filled cable:", self.ch_punjeni)
        layout.addRow("With armature fibers:", self.ch_sa_arm_vlaknima)
        layout.addRow("Without metal elements:", self.ch_bez_metalnih)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addRow(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def values(self):
        # Pokupi trenutne vrednosti sa forme
        tip_kabla = self.le_tip_kabla.text().strip()
        broj_cevcica = int(self.sb_cevcice.value())
        broj_vlakana = int(self.sb_vlakna.value())

        try:
            import re
            tip_lower = tip_kabla.lower()

            # 1) Ako su i cevi i vlakna 0 – probaj da pročitaš pattern tipa "4x6", "2x12" itd.
            if broj_cevcica == 0 and broj_vlakana == 0:
                m = re.search(r'(\d+)\s*[x×]\s*(\d+)', tip_lower)
                if m:
                    broj_cevcica = int(m.group(1))
                    broj_vlakana = int(m.group(2))

            # 2) Ako i dalje nemamo broj vlakana, probaj iz "12F", "24F", ...
            if broj_vlakana == 0:
                if "12f" in tip_lower or "12 f" in tip_lower:
                    broj_vlakana = 12
                elif "24f" in tip_lower or "24 f" in tip_lower:
                    broj_vlakana = 24
                elif "48f" in tip_lower or "48 f" in tip_lower:
                    broj_vlakana = 48
                elif "96f" in tip_lower or "96 f" in tip_lower:
                    broj_vlakana = 96
                elif "144f" in tip_lower or "144 f" in tip_lower:
                    broj_vlakana = 144

            # 3) Ako i dalje nemamo broj cevi, probaj da pogodiš razuman default
            if broj_cevcica == 0 and broj_vlakana > 0:
                # Ovo su samo "default" pretpostavke – korisnik uvek može da promeni.
                if broj_vlakana == 12:
                    broj_cevcica = 1          # 1x12
                elif broj_vlakana == 6:
                    broj_cevcica = 4          # default 4x6
                elif broj_vlakana == 12:
                    broj_cevcica = 4          # 4x12
                elif broj_vlakana == 12:
                    broj_cevcica = 8          # 8x12
                elif broj_vlakana == 12:
                    broj_cevcica = 12         # 12x12
                else:
                    broj_cevcica = 1          # neki minimalni default
        except Exception:
            # If anything fails – just leave what the user entered
            pass

        # >>> THIS IS THE KEY CHANGE <<<
        # currentData() will hold SERBIAN code (e.g. "podzemni"),
        # and currentText() is what user sees (English).
        vrsta = self.cb_vrsta.currentData() or self.cb_vrsta.currentText()
        podtip = self.cb_podtip.currentData() or self.cb_podtip.currentText()
        tip = self.cb_tip.currentData() or self.cb_tip.currentText()
        color_code = self.cb_color.currentData() or self.cb_color.currentText()
        vrsta_vlakana = self.cb_vrsta_vlakana.currentData() or self.cb_vrsta_vlakana.currentText()
        stanje_kabla = self.cb_stanje.currentData() or self.cb_stanje.currentText()
        polaganje_kabla = self.cb_polaganje.currentData() or self.cb_polaganje.currentText()

        return {
        "vrsta": vrsta,
        "podtip": podtip,
        "tip": tip,
        "color_code": color_code,
        "broj_cevcica": broj_cevcica,
        "broj_vlakana": broj_vlakana,
        "tip_kabla": tip_kabla,
        "vrsta_vlakana": vrsta_vlakana,
        "vrsta_omotaca": self.le_vrsta_omotaca.text().strip(),
        "vrsta_armature": self.le_vrsta_armature.text().strip(),
        "talasno_podrucje": self.le_talasno.text().strip(),
        "naziv": self.le_naziv.text().strip(),
        "slabljenje_dbkm": float(self.ds_slabljenje.value()),
        "hrom_disp_ps_nmxkm": float(self.ds_hrom_disp.value()),
        "stanje_kabla": stanje_kabla,
        "polaganje_kabla": polaganje_kabla,
        "vrsta_mreze": self.le_vrsta_mreze.text().strip(),
        "godina_ugradnje": int(self.sb_godina.value()),
        "konstr_vlakna_u_cevcicama": 1 if self.ch_vlakna_u_cevcicama.isChecked() else 0,
        "konstr_sa_uzlepljenim_elementom": 1 if self.ch_sa_uzlepljenim.isChecked() else 0,
        "konstr_punjeni_kabl": 1 if self.ch_punjeni.isChecked() else 0,
        "konstr_sa_arm_vlaknima": 1 if self.ch_sa_arm_vlaknima.isChecked() else 0,
        "konstr_bez_metalnih": 1 if self.ch_bez_metalnih.isChecked() else 0,
    }





class CableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unesi podatke o kablu")
        layout = QVBoxLayout(self)
        self.tip_edit = QLineEdit()
        self.kapacitet_edit = QLineEdit()
        layout.addWidget(QLabel("Tip:"))
        layout.addWidget(self.tip_edit)
        layout.addWidget(QLabel("Kapacitet:"))
        layout.addWidget(self.kapacitet_edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

class PointTool(QgsMapToolEmitPoint):
    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setColor(QColor(0, 255, 0))
        self.snap_marker.setIconType(QgsVertexMarker.ICON_CROSS)
        self.snap_marker.setIconSize(14)
        self.snap_marker.setPenWidth(3)
        self.snap_marker.hide()

    def _snap_candidate(self, point):
        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                trasa_layer = lyr
                break

        snap_point = None
        min_dist = None
        # Snapping distanca u pikselima iz FiberQ Settings
        try:
            from qgis.core import QgsSettings
            s = QgsSettings()
            snap_px = int(s.value("FiberQ/default_snap_distance", "20"))
        except Exception:
            snap_px = 20

        snap_tolerance = self.canvas.mapUnitsPerPixel() * snap_px

        if trasa_layer and trasa_layer.featureCount() > 0:
            for feat in trasa_layer.getFeatures():
                geom = feat.geometry()
                if geom.isMultipart():
                    lines = geom.asMultiPolyline()
                else:
                    lines = [geom.asPolyline()]

                for line in lines:
                    if not line:
                        continue
                    # --- NOVO: proveri sve verteksa (krajevi + lomne tačke) ---
                    for pt in line:
                        dist = QgsPointXY(point).distance(QgsPointXY(pt))
                        if min_dist is None or dist < min_dist:
                            min_dist = dist
                            snap_point = QgsPointXY(pt)

                    # --- zadrži i sredine segmenata ---
                    for i in range(len(line)-1):
                        mid = QgsPointXY(
                            (line[i].x() + line[i+1].x()) / 2,
                            (line[i].y() + line[i+1].y()) / 2
                        )
                        dist = QgsPointXY(point).distance(mid)
                        if min_dist is None or dist < min_dist:
                            min_dist = dist
                            snap_point = mid

        if snap_point and min_dist is not None and min_dist < snap_tolerance:
            return snap_point
        return None

    def canvasMoveEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        snap_point = self._snap_candidate(point)
        if snap_point:
            self.snap_marker.setCenter(snap_point)
            self.snap_marker.show()
        else:
            self.snap_marker.hide()

    def canvasReleaseEvent(self, event):
        # desni klik – prekid komande bez dodavanja stuba
        if event.button() == Qt.RightButton:
            try:
                self.snap_marker.hide()
            except Exception:
                pass
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass
            return

        # bilo šta što nije levi klik – ignorisi
        if event.button() != Qt.LeftButton:
            return

        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            QMessageBox.warning(None, "FiberQ", "Layer not found or invalid!")
            return

        point = self.toMapCoordinates(event.pos())
        snap_point = self._snap_candidate(point)
        final_point = snap_point if snap_point else point

        feature = QgsFeature(self.layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(final_point))
        feature.setAttribute("tip", "POLE")
        self.layer.startEditing()
        self.layer.addFeature(feature)
        self.layer.commitChanges()
        self.layer.triggerRepaint()
        self.snap_marker.hide()



class PlaceElementTool(QgsMapToolEmitPoint):
    """Generalized tool for placing point elements on route.
    target_layer_name: layer name to write to (automatically creates if doesn't exist)
    symbol_spec: dict for QgsMarkerSymbol.createSimple or {'svg_path': '/path/to/icon.svg'}
    """
    def __init__(self, canvas, target_layer_name, symbol_spec=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.target_layer_name = target_layer_name
        self.symbol_spec = symbol_spec or {'name':'diamond','color':'red','size':'5','size_unit':'MapUnit'}
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setColor(QColor(255, 0, 0))
        self.snap_marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.snap_marker.setIconSize(14)
        self.snap_marker.setPenWidth(3)
        self.snap_marker.hide()

    def _apply_prekid_style(self, layer):
        """
        Specijalan stil za tačke prekida vlakna:
        - mali crni krug
        - fiksna veličina u milimetrima (ne menja se pri zumiranju)
        - bez labela
        """
        try:
            from qgis.core import QgsSimpleMarkerSymbolLayer, QgsMarkerSymbol, QgsUnitTypes
            from qgis.PyQt.QtGui import QColor
        except Exception:
            return

        if layer is None:
            return

        try:
            simple = QgsSimpleMarkerSymbolLayer()
        except Exception:
            return

        # Krug kao za "Add pole", ali mali
        try:
            # oblik
            try:
                simple.setShape(QgsSimpleMarkerSymbolLayer.Circle)
            except Exception:
                pass

            # veličina i jedinice
            simple.setSize(2.4)  # mm
            simple.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)

            # boje
            simple.setColor(QColor(0, 0, 0))          # crno punjenje
            simple.setOutlineColor(QColor(0, 0, 0))   # crni rub
            simple.setOutlineWidth(0.2)
            simple.setOutlineWidthUnit(QgsUnitTypes.RenderMetersInMapUnits)
        except Exception:
            pass

        try:
            sym = QgsMarkerSymbol()
            sym.changeSymbolLayer(0, simple)
            layer.renderer().setSymbol(sym)
            layer.triggerRepaint()
        except Exception:
            pass


    def canvasMoveEvent(self, event):
        # snap na linije (Kablovi/Trasa) ILI na čvor (Stub/OKNA)
        point = self.toMapCoordinates(event.pos())

        line_layers = []
        node_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.geometryType() == QgsWkbTypes.LineGeometry and lyr.name() in ("Kablovi_podzemni", "Kablovi_vazdusni", "Underground cables", "Aerial cables", "Trasa", "Route"):
                    line_layers.append(lyr)
                if lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() in ("Stubovi", "Poles", "OKNA", "Manholes"):
                    node_layers.append(lyr)
            except Exception:
                pass

        min_dist = None
        snapped_point = None
        tolerance = self.canvas.mapUnitsPerPixel() * 10

        # linije
        for layer in line_layers:
            for feat in layer.getFeatures():
                geom = feat.geometry()
                if not geom:
                    continue
                dist, snap, vAfter, seg_idx = geom.closestSegmentWithContext(point)
                if min_dist is None or dist < min_dist:
                    min_dist = dist
                    snapped_point = snap

        # čvorovi
        for lyr in node_layers:
            for f in lyr.getFeatures():
                geom = f.geometry()
                if not geom or geom.isEmpty():
                    continue
                try:
                    pt = geom.asPoint()
                except Exception:
                    continue
                d = QgsPointXY(point).distance(QgsPointXY(pt))
                if min_dist is None or d < min_dist:
                    min_dist = d
                    snapped_point = QgsPointXY(pt)

        if snapped_point and min_dist is not None and min_dist < tolerance:
            self.snap_marker.setCenter(snapped_point)
            self.snap_marker.show()
            self._last_snap_point = snapped_point
        else:
            self.snap_marker.hide()
            self._last_snap_point = None

    def canvasPressEvent(self, event):
        # desni klik – prekid komande
        if event.button() == Qt.RightButton:
            try:
                self.snap_marker.hide()
            except Exception:
                pass
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass
            return

        if event.button() != Qt.LeftButton:
            return

        final_point = getattr(self, '_last_snap_point', None)
        if final_point is None:
            # dozvoli i bez snap-a (klik gde je korisnik kliknuo)
            final_point = self.toMapCoordinates(event.pos())

        # Pre-placement dialog (dynamic attributes)
        existing_layer = None
        try:
            for lyr in QgsProject.instance().mapLayers().values():
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() == self.target_layer_name:
                    existing_layer = lyr
                    break
        except Exception:
            existing_layer = None

        # If target is 'Fiber break', automatically set name without dialog
        if 'prekid' in self.target_layer_name.lower():
            _attrs = {'naziv': 'Prekid'}
            ok = True
        else:
            try:
                dlg = PrePlaceAttributesDialog(self.target_layer_name, existing_layer)
                ok = (dlg.exec_() == QDialog.Accepted)
                _attrs = dlg.values() if ok else {}
            except Exception:
                naziv, ok = QInputDialog.getText(None, "Placing elements", f"Name ({self.target_layer_name}):")
                _attrs = {'naziv': naziv} if ok and naziv else {}
        if not ok or not _attrs.get('naziv'):
            QMessageBox.warning(None, "Element", "Name not entered!")
            self.snap_marker.hide()
            return

        # Find or create layer
        elem_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() == self.target_layer_name:
                elem_layer = lyr
                break
        if elem_layer is None:
            crs = self.canvas.mapSettings().destinationCrs().authid()
            elem_layer = QgsVectorLayer(f"Point?crs={crs}", self.target_layer_name, "memory")
            pr = elem_layer.dataProvider()
            # Add fields based on dialog spec (so attribute table matches the dialog)
            try:
                specs = _default_fields_for(self.target_layer_name)
            except Exception:
                specs = [("naziv", "Naziv", "text", "", None)]
            fields = []
            for (key, label, kind, default, opts) in specs:
                qt = QVariant.String
                if kind in ("int", "year"):
                    qt = QVariant.Int
                elif kind == "double":
                    qt = QVariant.Double
                elif kind == "enum":
                    qt = QVariant.String
                fields.append(QgsField(key, qt))
            # Always ensure 'naziv' exists
            if not any(f.name() == "naziv" for f in fields):
                fields.insert(0, QgsField("naziv", QVariant.String))
            pr.addAttributes(fields)
            elem_layer.updateFields()
            pr.addAttributes(fields)
            elem_layer.updateFields()
            _apply_element_aliases(elem_layer)


            # Stil
            spec = self.symbol_spec
            if isinstance(spec, dict) and 'svg_path' in spec:
                symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'size': '5', 'size_unit': 'MapUnit'})
                try:
                    svg_layer = QgsSvgMarkerSymbolLayer(spec['svg_path'])
                    try:
                        svg_layer.setSize(float(spec.get('size', 6)))
                    except Exception:
                        pass
                    try:
                        svg_layer.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
                    except Exception:
                        svg_layer.setSizeUnit(QgsUnitTypes.RenderMapUnits)
                    symbol.changeSymbolLayer(0, svg_layer)
                except Exception:
                    pass
            else:
                symbol = QgsMarkerSymbol.createSimple(spec)
            elem_layer.renderer().setSymbol(symbol)
            # Label
            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "naziv"
            label_settings.enabled = True
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            elem_layer.setLabeling(labeling)
            elem_layer.setLabelsEnabled(True)
            _apply_fixed_text_label(elem_layer, 'naziv', 8.0, 5.0)
            QgsProject.instance().addMapLayer(elem_layer)
        else:
            # Ensure all fields used by the dialog exist on the layer
            try:
                specs = _default_fields_for(self.target_layer_name)
            except Exception:
                specs = [("naziv", "Naziv", "text", "", None)]
            to_add = []
            for (key, label, kind, default, opts) in specs:
                if elem_layer.fields().indexFromName(key) == -1:
                    qt = QVariant.String
                    if kind in ("int", "year"):
                        qt = QVariant.Int
                    elif kind == "double":
                        qt = QVariant.Double
                    elif kind == "enum":
                        qt = QVariant.String
                    to_add.append(QgsField(key, qt))
            if to_add:
                elem_layer.startEditing()
                elem_layer.dataProvider().addAttributes(to_add)
                elem_layer.updateFields()
                elem_layer.commitChanges()

            # <<< NOVO >>>
            _apply_element_aliases(elem_layer)

        # If this is 'Fiber break' layer, apply special style (label above and triangle point on route)
        if 'prekid' in self.target_layer_name.lower():
            self._apply_prekid_style(elem_layer)

        # Write point
        feat = QgsFeature(elem_layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(final_point))
        name_map = {_normalize_name(f.name()): f.name() for f in elem_layer.fields()}
        for k, v in _attrs.items():
            fname = name_map.get(k, k)
            try:
                feat.setAttribute(fname, v)
            except Exception:
                pass
        elem_layer.startEditing()
        elem_layer.addFeature(feat)
        elem_layer.commitChanges()

        elem_layer.triggerRepaint()
        self.snap_marker.hide()
        QMessageBox.information(None, "FiberQ", "Element placed!")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            try:
                self.snap_marker.hide()
            except Exception:
                pass
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass



class ExtensionTool(QgsMapToolEmitPoint):
    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setColor(QColor(255, 0, 0))
        self.snap_marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.snap_marker.setIconSize(14)
        self.snap_marker.setPenWidth(3)
        self.snap_marker.hide()

    def keyPressEvent(self, event):
        # ESC -> otkaži alat
        if event.key() == Qt.Key_Escape:
            try:
                self.snap_marker.hide()
            except Exception:
                pass
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass

    def canvasPressEvent(self, event):
        # desni klik -> otkaži alat (bez postavljanja joint closure-a)
        if event.button() == Qt.RightButton:
            try:
                self.snap_marker.hide()
            except Exception:
                pass
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass

    def _snap_candidate(self, point):
        """
        Snap na:
        - point slojeve (Poles/Manholes + opcionalno Infrastructure cuts)
        - vertex-e line slojeva kablova (da Joint Closure može tačno na mesto sečenja)
        """
        tol = self.canvas.mapUnitsPerPixel() * 20
        rect = QgsRectangle(point.x() - tol, point.y() - tol, point.x() + tol, point.y() + tol)

        snap_point = None
        min_dist = None

        def consider(pt):
            nonlocal snap_point, min_dist
            d = QgsPointXY(point).distance(QgsPointXY(pt))
            if min_dist is None or d < min_dist:
                min_dist = d
                snap_point = QgsPointXY(pt)

        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                    continue

                gtype = lyr.geometryType()
                lname = (lyr.name() or "").lower()

                # --- POINT slojevi (stubovi/okna + opcionalno cut marker sloj) ---
                is_node_layer = (
                    lyr.name() in ("Stubovi", "Poles", "OKNA", "Okna", "Manholes")
                    or "infrastructure cut" in lname
                    or "infrastructure cuts" in lname
                    or lname.strip() in ("cuts", "cut")
                )

                if gtype == QgsWkbTypes.PointGeometry and is_node_layer:
                    req = QgsFeatureRequest().setFilterRect(rect)
                    for feat in lyr.getFeatures(req):
                        geom = feat.geometry()
                        if not geom or geom.isEmpty():
                            continue
                        # najbezbednije: vertices() radi i za point/multipoint
                        for v in geom.vertices():
                            consider(v)
                    continue

                # --- LINE slojevi kablova (tu je vertex na mestu sečenja) ---
                is_cable_layer = (
                    "cable" in lname
                    or "kabl" in lname
                    or lyr.name() in ("Trasa", "Route")
                )

                if gtype == QgsWkbTypes.LineGeometry and is_cable_layer:
                    req = QgsFeatureRequest().setFilterRect(rect)
                    for feat in lyr.getFeatures(req):
                        geom = feat.geometry()
                        if not geom or geom.isEmpty():
                            continue
                        for v in geom.vertices():
                            consider(v)

            except Exception:
                # if any layer "goes crazy", skip it
                pass

        if snap_point is not None and min_dist is not None and min_dist < tol:
            return snap_point
        return None



    def canvasMoveEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        snap_point = self._snap_candidate(point)
        if snap_point:
            self.snap_marker.setCenter(snap_point)
            self.snap_marker.show()
        else:
            self.snap_marker.hide()

    def _apply_joint_closure_aliases(self, layer):
        """Alias za polje 'naziv' i prikaz imena lejera u legendi."""
        if layer is None:
            return

        # 1) Alias za kolonu 'naziv' -> 'Name'
        try:
            idx = layer.fields().indexFromName('naziv')
        except Exception:
            idx = -1

        if idx != -1:
            try:
                layer.setFieldAlias(idx, "Name")
            except Exception:
                pass

        # 2) Alias imena lejera u Layers panelu (user view)
        try:
            root = QgsProject.instance().layerTreeRoot()
            node = root.findLayer(layer.id())
            if node:
                node.setCustomLayerName("Joint Closures")
        except Exception:
            pass

    def canvasReleaseEvent(self, event):
        
        # samo levi klik postavlja joint closure
        if event.button() != Qt.LeftButton:
            return

        if self.layer is None or sip.isdeleted(self.layer) or not self.layer.isValid():
            QMessageBox.warning(None, "FiberQ", "Layer not found or invalid!")
            return

        click_point = self.toMapCoordinates(event.pos())
        snap_point = self._snap_candidate(click_point)
        final_point = snap_point if snap_point else click_point

        naziv, ok = QInputDialog.getText(
            None,
            "Joint closure",
            "Enter joint closure name:"
        )
        if not ok or not naziv:
            QMessageBox.warning(None, "FiberQ", "No joint closure name entered!")
            self.snap_marker.hide()
            return

        # Find existing layer Joint Closures (also supports old name "Nastavci")
        nastavak_layer = None
        target_names = {
            NASTAVAK_DEF.get("name", "Joint Closures"),
            "Nastavci",
        }
        for lyr in QgsProject.instance().mapLayers().values():
            if (
                isinstance(lyr, QgsVectorLayer)
                and lyr.geometryType() == QgsWkbTypes.PointGeometry
                and lyr.name() in target_names
            ):
                nastavak_layer = lyr
                self._apply_joint_closure_aliases(nastavak_layer)
                break


        # 2) If doesn't exist – create new
        if nastavak_layer is None:
            crs = self.canvas.mapSettings().destinationCrs().authid()
            nastavak_layer = QgsVectorLayer(
                f"Point?crs={crs}",
                NASTAVAK_DEF.get("name", "Joint Closures"),
                "memory",
            )

            pr = nastavak_layer.dataProvider()
            pr.addAttributes([QgsField("naziv", QVariant.String)])
            nastavak_layer.updateFields()

            symbol = QgsMarkerSymbol.createSimple(
                {"name": "circle", "size": "10", "size_unit": "MapUnit"}
            )
            try:
                svg_layer = QgsSvgMarkerSymbolLayer(
                    _map_icon_path("map_joint_closure.svg")
                )
                svg_layer.setSize(10)
                try:
                    svg_layer.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
                except Exception:
                    svg_layer.setSizeUnit(QgsUnitTypes.RenderMapUnits)
                symbol.changeSymbolLayer(0, svg_layer)
            except Exception:
                pass

            nastavak_layer.renderer().setSymbol(symbol)
            QgsProject.instance().addMapLayer(nastavak_layer)

            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "naziv"
            label_settings.enabled = True
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            nastavak_layer.setLabeling(labeling)
            nastavak_layer.setLabelsEnabled(True)
            _apply_fixed_text_label(nastavak_layer, "naziv", 8.0, 5.0)
            nastavak_layer.triggerRepaint()

            # immediately after creating layer – aliases
            self._apply_joint_closure_aliases(nastavak_layer)

        # 3) If layer exists but doesn't have field 'naziv' – add it + labeling + alias
        elif nastavak_layer.fields().indexFromName("naziv") == -1:
            nastavak_layer.startEditing()
            nastavak_layer.dataProvider().addAttributes(
                [QgsField("naziv", QVariant.String)]
            )
            nastavak_layer.updateFields()
            nastavak_layer.commitChanges()
            nastavak_layer.triggerRepaint()

            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "naziv"
            label_settings.enabled = True
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            nastavak_layer.setLabeling(labeling)
            nastavak_layer.setLabelsEnabled(True)
            _apply_fixed_text_label(nastavak_layer, "naziv", 8.0, 5.0)
            nastavak_layer.triggerRepaint()

            self._apply_joint_closure_aliases(nastavak_layer)

        # 4) Dodaj novi joint-closure feature
        nastavak_feat = QgsFeature(nastavak_layer.fields())
        nastavak_feat.setGeometry(QgsGeometry.fromPointXY(final_point))
        nastavak_feat.setAttribute("naziv", naziv)

        nastavak_layer.startEditing()
        nastavak_layer.addFeature(nastavak_feat)
        nastavak_layer.commitChanges()
        nastavak_layer.triggerRepaint()
        self.snap_marker.hide()

        QMessageBox.information(None, "FiberQ", "Joint closure placed!")

    
    

# === DODATO: LomnaTackaTool za split linije ===
class LomnaTackaTool(QgsMapToolEmitPoint):
    def __init__(self, canvas, iface, plugin):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.plugin = plugin
        self.rubber = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.rubber.setColor(QColor(0, 255, 0))
        self.rubber.setWidth(10)
        self.snap_info = None

    def canvasMoveEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                trasa_layer = lyr
                break
        if trasa_layer is None or trasa_layer.featureCount() == 0:
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            self.snap_info = None
            return

        min_dist = None
        snapped_point = None
        min_feat = None
        min_geom = None
        min_seg_idx = None

        for feat in trasa_layer.getFeatures():
            geom = feat.geometry()
            dist, snap, vertexAfter, seg_idx = geom.closestSegmentWithContext(point)
            if min_dist is None or dist < min_dist:
                min_dist = dist
                snapped_point = snap
                min_feat = feat
                min_geom = geom
                min_seg_idx = seg_idx

        tolerance = self.canvas.mapUnitsPerPixel() * 10
        if snapped_point and min_dist < tolerance:
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            self.rubber.addPoint(snapped_point)
            self.snap_info = {
                'feat': min_feat,
                'geom': min_geom,
                'point': snapped_point,
                'seg_idx': min_seg_idx,
                'dist': min_dist
            }
        else:
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            self.snap_info = None

    def canvasReleaseEvent(self, event):
        # DESNI KLIK = prekid komande
        if event.button() == Qt.RightButton:
            self.snap_info = None
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            self.iface.mapCanvas().unsetMapTool(self)
            return

        # ignorisi sve osim levog klika
        if event.button() != Qt.LeftButton:
            return

        if self.snap_info is None:
            QMessageBox.warning(self.iface.mainWindow(), "Split route", "Click closer to a route!")
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            return

        min_feat = self.snap_info['feat']
        min_geom = self.snap_info['geom']
        snapped_point = self.snap_info['point']
        min_seg_idx = self.snap_info['seg_idx']

        if min_geom.isMultipart():
            # Pokušaj da konvertuješ u običnu liniju ako ima samo jednu pod-liniju
            lines = min_geom.asMultiPolyline()
            if lines and len(lines) == 1:
                min_geom = QgsGeometry.fromPolylineXY(lines[0])
            else:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Split route",
                    "The route is a multi-line (multipart) geometry with multiple lines and cannot be split with this tool!\n"
                    "Merge the lines so that there is ONE line (not a MultiLineString)."
                )
                self.rubber.reset(QgsWkbTypes.PointGeometry)
                return

        # Konverzija svih verteksa u QgsPointXY zbog QGIS API zahteva
        line_points = [QgsPointXY(pt) for pt in min_geom.vertices()]
        idx = min_seg_idx

        # --- Poseban slučaj za liniju sa 2 verteksa ---
        if len(line_points) == 2:
            p0, p1 = line_points
            tol = self.canvas.mapUnitsPerPixel() * 2
            if QgsGeometry.fromPointXY(snapped_point).distance(QgsGeometry.fromPointXY(p0)) < tol or \
               QgsGeometry.fromPointXY(snapped_point).distance(QgsGeometry.fromPointXY(p1)) < tol:
                QMessageBox.warning(self.iface.mainWindow(), "Split route", "Click closer to the middle of the segment.")
                self.rubber.reset(QgsWkbTypes.PointGeometry)
                return

            geom1 = QgsGeometry.fromPolylineXY([p0, snapped_point])
            geom2 = QgsGeometry.fromPolylineXY([snapped_point, p1])
        else:
            # --- Standardna split logika za linije sa više verteksa ---
            res, new_geoms, topo_test = min_geom.splitGeometry([snapped_point], False)

            if res != 0 or not new_geoms:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Split route",
                    "Cannot split the route at this location."
                )
                self.rubber.reset(QgsWkbTypes.PointGeometry)
                return

            geom1 = min_geom
            geom2 = new_geoms[0]

        naziv = min_feat['naziv'] if 'naziv' in min_feat.fields().names() else ''
        tip_trase = min_feat['tip_trase'] if 'tip_trase' in min_feat.fields().names() else 'nepoznat'

        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                trasa_layer = lyr
                break
        if trasa_layer is None:
            QMessageBox.warning(self.iface.mainWindow(), "Split route", "Route layer 'Route' not found!")
            self.rubber.reset(QgsWkbTypes.PointGeometry)
            return

        trasa_layer.startEditing()
        trasa_layer.deleteFeature(min_feat.id())

        feat1 = QgsFeature(trasa_layer.fields())
        feat1.setGeometry(geom1)
        feat1.setAttribute('naziv', naziv + "_a")
        feat1.setAttribute('tip_trase', tip_trase)
        duzina_m1 = geom1.length()
        feat1.setAttribute('duzina', duzina_m1)
        feat1.setAttribute('duzina_km', round(duzina_m1 / 1000.0, 2))

        feat2 = QgsFeature(trasa_layer.fields())
        feat2.setGeometry(geom2)
        feat2.setAttribute('naziv', naziv + "_b")
        feat2.setAttribute('tip_trase', tip_trase)
        duzina_m2 = geom2.length()
        feat2.setAttribute('duzina', duzina_m2)
        feat2.setAttribute('duzina_km', round(duzina_m2 / 1000.0, 2))

        trasa_layer.addFeatures([feat1, feat2])
        trasa_layer.commitChanges()
        self.plugin.style_route_layer(trasa_layer)

        self.rubber.reset(QgsWkbTypes.PointGeometry)
        QMessageBox.information(
            self.iface.mainWindow(), "Split route",
            f"The route has been split!\nFirst part: {duzina_m1:.2f} m, second part: {duzina_m2:.2f} m."
        )


# === NOVO: SmartMultiSelectTool — više-slojna pametna selekcija ===
class SmartMultiSelectTool(QgsMapTool):

    def _layer_priority(self, lyr):
        """
        Niži broj = veći prioritet.

        0  - elementi (drop-down "Placing elements", Nastavci)
        10 - stubovi / okna (Poles, Manholes)
        50 - linije (Route/Trasa, kablovi, cevi)
        80 - poligoni (Objects, Service Area/Rejon)
        100 - ostalo
        """
        try:
            from qgis.core import QgsWkbTypes
            name = (lyr.name() or "").lower()
            gtype = lyr.geometryType()
        except Exception:
            return 100

        # 1) elementi + nastavci (najveći prioritet)
        element_names = set()
        try:
            try:
                element_names.add(NASTAVAK_DEF.get('name', 'Nastavci').lower())
            except Exception:
                element_names.add('nastavci')
            try:
                for d in ELEMENT_DEFS:
                    nm = d.get('name')
                    if nm:
                        element_names.add(nm.lower())
            except Exception:
                pass
        except Exception:
            pass

        if name in element_names:
            return 0

        # 2) stubovi / okna
        if name in ("stubovi", "poles", "okna", "manholes"):
            return 10

        # 3) linije: trasa, kablovi, cevi
        if gtype == QgsWkbTypes.LineGeometry:
            return 50

        # 4) poligoni: objekti, rejoni
        if gtype == QgsWkbTypes.PolygonGeometry:
            return 80

        # ostalo
        return 100

    
    """Omogućava selekciju objekata klikom bez prebacivanja aktivnog sloja.
    - Radi nad tačkastim slojevima čije ime sadrži 'nastav', 'stub' ili 'okno' (nije osetljivo na mala/VELIKA slova).
    - Klik na objekat: toggle selekcije (selektuj/deselektuj) samo na tom sloju.
    - Ne dira selekcije na drugim slojevima.
    - Prikazuje mali marker na mestu klika kao vizuelnu potvrdu (samo privremeno).
    """
    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()
        # marker za vizuelni feedback
        try:
            self._marker = QgsVertexMarker(self.canvas)
            self._marker.setIconType(QgsVertexMarker.ICON_CROSS)
            self._marker.setColor(QColor(0, 170, 255))
            self._marker.setIconSize(12)
            self._marker.setPenWidth(3)
            self._marker.hide()
        except Exception:
            self._marker = None

    def _nearest_feature(self, lyr, pt, tol):
        """Vrati (fid, geom) najbližeg featura u okviru tolerancije u map jedinicama; inače (None, None)."""
        try:
            from qgis.core import QgsFeatureRequest, QgsRectangle
            rect = QgsRectangle(pt.x()-tol, pt.y()-tol, pt.x()+tol, pt.y()+tol)
            req = QgsFeatureRequest().setFilterRect(rect)
        except Exception:
            req = None

        gpt = QgsGeometry.fromPointXY(pt)
        best = (None, None, None)  # (dist, fid, geom)
        it = lyr.getFeatures(req) if req is not None else lyr.getFeatures()
        for f in it:
            try:
                geom = f.geometry()
                if not geom or geom.isEmpty():
                    continue
                d = geom.distance(gpt)
                if d <= tol and (best[0] is None or d < best[0]):
                    best = (d, f.id(), geom)
            except Exception:
                continue
        return (best[1], best[2]) if best[1] is not None else (None, None)

    def canvasReleaseEvent(self, e):
        # desni klik -> prekid alata (bez menjanja selekcije)
        try:
            from qgis.PyQt.QtCore import Qt
            if e.button() == Qt.RightButton:
                if self._marker:
                    try:
                        self._marker.hide()
                    except Exception:
                        pass
                try:
                    self.canvas.unsetMapTool(self)
                except Exception:
                    pass
                return
        except Exception:
            pass

        try:
            pt = self.toMapCoordinates(e.pos())
        except Exception:
            return

        # tolerancija ~10 px
        try:
            tol = self.canvas.extent().width() / max(1, self.canvas.width()) * 10.0
        except Exception:
            tol = 5.0

        from qgis.core import QgsGeometry
        gpt = QgsGeometry.fromPointXY(pt)

        # Skupi kandidate iz svih relevantnih slojeva
        candidates = []
        for lyr in self._candidate_layers():
            fid, geom = self._nearest_feature(lyr, pt, tol)
            if fid is None or geom is None:
                continue
            try:
                d = float(geom.distance(gpt))
            except Exception:
                d = 0.0
            candidates.append((d, self._layer_priority(lyr), lyr, fid, geom))

        if not candidates:
            if self._marker:
                self._marker.hide()
            return

        # If distances are very close, give priority to elements over pole/manhole
        min_d = min(c[0] for c in candidates)
        eps = max(tol * 0.4, 0.01)
        near = [c for c in candidates if c[0] <= min_d + eps]
        near.sort(key=lambda c: (c[1], c[0]))  # prioritet pa distanca
        _, _, lyr, fid, geom = near[0]

        # Toggle samo na tom sloju
        try:
            if fid in lyr.selectedFeatureIds():
                lyr.deselect(fid)
            else:
                lyr.select(fid)
        except Exception:
            pass

        # vizuelni feedback
        try:
            cen = geom.asPoint() if geom.isGeosValid() and geom.isSingle() else geom.centroid().asPoint()
        except Exception:
            cen = pt
        if self._marker:
            self._marker.setCenter(QgsPointXY(cen))
            self._marker.show()

        # zapamti izbor
        try:
            if not hasattr(self.plugin, 'smart_selection'):
                self.plugin.smart_selection = []
            key = (lyr.id(), int(fid))
            if key in self.plugin.smart_selection:
                self.plugin.smart_selection.remove(key)
            else:
                self.plugin.smart_selection.append(key)
        except Exception:
            pass

    def keyPressEvent(self, e):
        """ESC prekida Smart selection alat."""
        try:
            from qgis.PyQt.QtCore import Qt as _Qt
            if e.key() == _Qt.Key_Escape:
                if self._marker:
                    try:
                        self._marker.hide()
                    except Exception:
                        pass
                try:
                    self.canvas.unsetMapTool(self)
                except Exception:
                    pass
        except Exception:
            pass    

    def deactivate(self):
        try:
            if self._marker:
                self._marker.hide()
        except Exception:
            pass
        super().deactivate()

    def _candidate_layers(self):
        """
        Vrati listu slojeva koji su relevantni za pametnu selekciju.

        Uključujemo:
        - sve point elemente iz drop-down liste "Placing elements"
        - 'Nastavci'
        - 'Stubovi' / 'Poles'
        - 'OKNA' / 'Manholes'
        - 'Trasa' / 'Route'
        - 'PE cevi' / 'PE pipes'
        - 'Prelazne cevi' / 'Transition pipes'
        - 'Objekti' / 'Objects'
        - 'Rejon' / 'Service Area'
        """
        try:
            # --- POINT slojevi: elementi + stubovi/okna ---
            valid_point_names = set()

            # 1) Nastavak
            try:
                valid_point_names.add(NASTAVAK_DEF.get('name', 'Nastavci'))
            except Exception:
                valid_point_names.add('Nastavci')

            # 2) Svi elementi iz ELEMENT_DEFS
            try:
                for d in ELEMENT_DEFS:
                    nm = d.get('name')
                    if nm:
                        valid_point_names.add(nm)
            except Exception:
                pass

            # 3) Stubovi / Poles i OKNA / Manholes
            valid_point_names.update(['Poles', 'Manholes'])

            # --- LINE slojevi: trasa + cevi ---
            valid_line_names = {
                'Trasa', 'Route',
                'PE cevi', 'PE pipes',
                'Prelazne cevi', 'Transition pipes',
                'Kablovi_podzemni', 'Underground cables',
                'Kablovi_vazdusni', 'Aerial cables',
            }

            # --- POLYGON slojevi: objekti + rejoni ---
            valid_poly_names = {
                'Objekti', 'Objects',
                'Rejon', 'Service Area', 'Service area',
            }

            low_point = {n.lower() for n in valid_point_names}
            low_line  = {n.lower() for n in valid_line_names}
            low_poly  = {n.lower() for n in valid_poly_names}

            layers = []
            from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes

            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                        continue

                    name = (lyr.name() or "")
                    lname = name.lower()
                    gtype = lyr.geometryType()

                    if gtype == QgsWkbTypes.PointGeometry:
                        if name in valid_point_names or lname in low_point:
                            layers.append(lyr)
                    elif gtype == QgsWkbTypes.LineGeometry:
                        if name in valid_line_names or lname in low_line:
                            layers.append(lyr)
                    elif gtype == QgsWkbTypes.PolygonGeometry:
                        if name in valid_poly_names or lname in low_poly:
                            layers.append(lyr)
                except Exception:
                    continue

            return layers

        except Exception:
            # Fallback – ako nešto pukne, zadrži staro ponašanje (samo neki point slojevi)
            import re as _re
            from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
            layers = []
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if isinstance(lyr, QgsVectorLayer) and lyr.isValid() and lyr.geometryType() == QgsWkbTypes.PointGeometry:
                        if _re.search(r"(nastav|stub|okno|zok|patch|ormar|panel|izvod|or)", (lyr.name() or "").lower()):
                            layers.append(lyr)
                except Exception:
                    pass
            return layers



class ManualRouteTool(QgsMapTool):
    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.rb.setColor(QColor(0, 0, 255, 150))
        self.rb.setWidth(2)
        self.points = []

        # Snap indikator
        self.snap_rubber = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.snap_rubber.setColor(QColor(255, 0, 0, 180))  # Crveni kružić, možeš promeniti
        self.snap_rubber.setWidth(12)  # Veličina kružića

    def canvasPressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.zavrsi_trasu()
            return

        point = self.toMapCoordinates(event.pos())

        # SLOJEVI za snap: Stubovi, OKNA + svi iz ELEMENT_DEFS + Nastavci
        node_layer_names = ['Poles', 'Manholes']
        try:
            # Nastavci
            try:
                nm = NASTAVAK_DEF.get('name', 'Nastavci')
                if nm and nm not in node_layer_names:
                    node_layer_names.append(nm)
            except Exception:
                if 'Joint_closures' not in node_layer_names:
                    node_layer_names.append('Joint_closures')
            # svi elementi iz Polaganje elemenata
            for d in ELEMENT_DEFS:
                nm = d.get('name')
                if nm and nm not in node_layer_names:
                    node_layer_names.append(nm)
        except Exception:
            pass

        node_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer)
                        and lyr.geometryType() == QgsWkbTypes.PointGeometry
                        and lyr.name() in node_layer_names):
                    node_layers.append(lyr)
            except Exception:
                pass

        snap_point = None
        min_dist = None

        # 1) SNAP na čvorove (stubovi, okna, elementi)
        for nl in node_layers:
            for feature in nl.getFeatures():
                geom = feature.geometry()
                if not geom or geom.isEmpty():
                    continue
                try:
                    pt = geom.asPoint()
                except Exception:
                    continue
                d = QgsPointXY(point).distance(QgsPointXY(pt))
                if min_dist is None or d < min_dist:
                    min_dist = d
                    snap_point = QgsPointXY(pt)

        # 2) ***NOVO*** – SNAP na postojeću trasu (verteksi + sredine segmenata)
        try:
            trasa_layers = []
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if (isinstance(lyr, QgsVectorLayer)
                            and lyr.geometryType() == QgsWkbTypes.LineGeometry
                            and lyr.name() in ('Route',)):
                        trasa_layers.append(lyr)
                except Exception:
                    pass

            for tl in trasa_layers:
                for feat in tl.getFeatures():
                    geom = feat.geometry()
                    if not geom or geom.isEmpty():
                        continue
                    if geom.isMultipart():
                        lines = geom.asMultiPolyline()
                    else:
                        lines = [geom.asPolyline()]

                    for line in lines:
                        if not line:
                            continue
                        # svi verteksi (uključujući krajeve)
                        for pt in line:
                            d = QgsPointXY(point).distance(QgsPointXY(pt))
                            if min_dist is None or d < min_dist:
                                min_dist = d
                                snap_point = QgsPointXY(pt)
                        # sredine segmenata – da može da se spoji i "u sredinu" trase
                        for i in range(len(line) - 1):
                            mid = QgsPointXY(
                                (line[i].x() + line[i + 1].x()) / 2.0,
                                (line[i].y() + line[i + 1].y()) / 2.0
                            )
                            d = QgsPointXY(point).distance(mid)
                            if min_dist is None or d < min_dist:
                                min_dist = d
                                snap_point = mid
        except Exception:
            pass

        snap_tolerance = self.canvas.mapUnitsPerPixel() * 15
        if min_dist is not None and min_dist < snap_tolerance and snap_point is not None:
            point = snap_point
            self.snap_rubber.reset(QgsWkbTypes.PointGeometry)
            self.snap_rubber.addPoint(snap_point)
        else:
            self.snap_rubber.reset(QgsWkbTypes.PointGeometry)

        self.points.append(point)
        self.rb.addPoint(point)


    def canvasMoveEvent(self, event):
        point = self.toMapCoordinates(event.pos())

        # SLOJEVI za snap: Stubovi, OKNA + svi iz ELEMENT_DEFS + Nastavci
        node_layer_names = ['Poles', 'Manholes']
        try:
            try:
                nm = NASTAVAK_DEF.get('name', 'Nastavci')
                if nm and nm not in node_layer_names:
                    node_layer_names.append(nm)
            except Exception:
                if 'Joint_closures' not in node_layer_names:
                    node_layer_names.append('Joint_closures')
            for d in ELEMENT_DEFS:
                nm = d.get('name')
                if nm and nm not in node_layer_names:
                    node_layer_names.append(nm)
        except Exception:
            pass

        node_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer)
                        and lyr.geometryType() == QgsWkbTypes.PointGeometry
                        and lyr.name() in node_layer_names):
                    node_layers.append(lyr)
            except Exception:
                pass

        snap_point = None
        min_dist = None

        # 1) SNAP na čvorove
        for nl in node_layers:
            for feature in nl.getFeatures():
                geom = feature.geometry()
                if not geom or geom.isEmpty():
                    continue
                try:
                    pt = geom.asPoint()
                except Exception:
                    continue
                d = QgsPointXY(point).distance(QgsPointXY(pt))
                if min_dist is None or d < min_dist:
                    min_dist = d
                    snap_point = QgsPointXY(pt)

        # 2) ***NOVO*** – SNAP na postojeću trasu (verteksi + sredine segmenata)
        try:
            trasa_layers = []
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if (isinstance(lyr, QgsVectorLayer)
                            and lyr.geometryType() == QgsWkbTypes.LineGeometry
                            and lyr.name() in ('Route',)):
                        trasa_layers.append(lyr)
                except Exception:
                    pass

            for tl in trasa_layers:
                for feat in tl.getFeatures():
                    geom = feat.geometry()
                    if not geom or geom.isEmpty():
                        continue
                    if geom.isMultipart():
                        lines = geom.asMultiPolyline()
                    else:
                        lines = [geom.asPolyline()]

                    for line in lines:
                        if not line:
                            continue
                        # svi verteksi
                        for pt in line:
                            d = QgsPointXY(point).distance(QgsPointXY(pt))
                            if min_dist is None or d < min_dist:
                                min_dist = d
                                snap_point = QgsPointXY(pt)
                        # sredine segmenata
                        for i in range(len(line) - 1):
                            mid = QgsPointXY(
                                (line[i].x() + line[i + 1].x()) / 2.0,
                                (line[i].y() + line[i + 1].y()) / 2.0
                            )
                            d = QgsPointXY(point).distance(mid)
                            if min_dist is None or d < min_dist:
                                min_dist = d
                                snap_point = mid
        except Exception:
            pass

        tol = self.canvas.mapUnitsPerPixel() * 15
        disp_point = snap_point if (min_dist is not None and min_dist < tol and snap_point is not None) else point

        # Show / hide snap indicator
        if snap_point is not None and min_dist is not None and min_dist < tol:
            self.snap_rubber.reset(QgsWkbTypes.PointGeometry)
            self.snap_rubber.addPoint(snap_point)
        else:
            self.snap_rubber.reset(QgsWkbTypes.PointGeometry)

        # Ažuriraj privremenu liniju (rubber band)
        pts = (list(self.points) + [disp_point]) if self.points else [disp_point]
        self.rb.setToGeometry(QgsGeometry.fromPolylineXY(pts), None)




    def canvasDoubleClickEvent(self, event):
        self.zavrsi_trasu()

    def zavrsi_trasu(self):
        # clean up snap marker
        self.snap_rubber.reset(QgsWkbTypes.PointGeometry)

        # if less than 2 points – abort
        if len(self.points) < 2:
            self.rb.reset(QgsWkbTypes.LineGeometry)
            self.points = []
            self.canvas.unsetMapTool(self)
            return

        # nađi ili napravi sloj Route / Trasa
        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                trasa_layer = lyr
                break
        if trasa_layer is None:
            crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
            trasa_layer = QgsVectorLayer(f"LineString?crs={crs}", "Route", "memory")
            QgsProject.instance().addMapLayer(trasa_layer)

        # obezbedi polja
        trasa_layer.startEditing()
        if trasa_layer.fields().indexFromName("naziv") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
        if trasa_layer.fields().indexFromName("duzina") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
        if trasa_layer.fields().indexFromName("duzina_km") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("duzina_km", QVariant.Double)])
        if trasa_layer.fields().indexFromName("tip_trase") == -1:
            trasa_layer.dataProvider().addAttributes([QgsField("tip_trase", QVariant.String)])
        trasa_layer.updateFields()
        trasa_layer.commitChanges()

        # stil + aliasi za Route
        self.plugin.style_route_layer(trasa_layer)

        # geometrija + dužina
        line_geom = QgsGeometry.fromPolylineXY(self.points)
        duzina_m = line_geom.length()
        duzina_km = round(duzina_m / 1000.0, 2)

        # --- dijalog sa ENG imenima, ali čuvamo SRB kod ---
        items = [TRASA_TYPE_LABELS.get(code, code) for code in TRASA_TYPE_OPTIONS]
        tip_label, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Route type",
            "Select route type:",
            items,
            0,
            False
        )
        if not ok or not tip_label:
            tip_trase = TRASA_TYPE_OPTIONS[0]
        else:
            tip_trase = TRASA_LABEL_TO_CODE.get(tip_label, TRASA_TYPE_OPTIONS[0])

        # upis feature-a
        trasa_layer.startEditing()
        feat = QgsFeature(trasa_layer.fields())
        feat.setGeometry(line_geom)
        feat.setAttribute("naziv", f"Route {trasa_layer.featureCount() + 1}")
        feat.setAttribute("duzina", duzina_m)
        feat.setAttribute("duzina_km", duzina_km)
        feat.setAttribute("tip_trase", tip_trase)   # in database stays 'vazdusna/podzemna/kroz objekat'
        trasa_layer.addFeature(feat)
        trasa_layer.commitChanges()

        # style once more (in case of new layer)
        self.plugin.style_route_layer(trasa_layer)

        # message to user – EN label
        nice_label = TRASA_TYPE_LABELS.get(tip_trase, tip_trase)
        QMessageBox.information(
            self.iface.mainWindow(),
            "FiberQ",
            f"Manual route has been created!\n"
            f"Length: {duzina_m:.2f} m ({duzina_km:.2f} km)\n"
            f"Type: {nice_label}"
        )

        # reset alata
        self.points = []
        self.rb.reset(QgsWkbTypes.LineGeometry)
        self.canvas.unsetMapTool(self)

#Automatska korekcija trase
class KorekcijaDialog(QDialog):
    def __init__(self, greske, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Route correction - found errors")
        layout = QVBoxLayout(self)
        area = QScrollArea(self)
        widget = QWidget()
        vbox = QVBoxLayout()
        for g in greske:
            lbl = QLabel(g['msg'])
            vbox.addWidget(lbl)
            # Button for repair (if exists)
            if 'popravka' in g:
                btn = QPushButton("Correct")
                # Qt sends bool (checked), here we ignore it and call function without arguments
                btn.clicked.connect(lambda checked=False, func=g['popravka']: func())
                vbox.addWidget(btn)

            # Button for selecting on map (if feat and layer exist)
            if 'feat' in g and 'layer' in g:
                btn_sel = QPushButton("Select on map")
                # Create function that selects and zooms to feature
                def sel_func(feat_id=g['feat'].id(), layer=g['layer']):
                    # Clear selection on all layers
                    for lyr in QgsProject.instance().mapLayers().values():
                        if isinstance(lyr, QgsVectorLayer):
                            lyr.removeSelection()
                    layer.selectByIds([feat_id])
                    # Zumiraj na feature
                    parent_iface = self.parent().iface if hasattr(self.parent(), 'iface') else None
                    if parent_iface:
                        parent_iface.mapCanvas().zoomToSelected(layer)
                btn_sel.clicked.connect(sel_func)
                vbox.addWidget(btn_sel)
        widget.setLayout(vbox)
        area.setWidget(widget)
        area.setWidgetResizable(True)
        layout.addWidget(area)
        btn_zatvori = QPushButton("Close")
        btn_zatvori.clicked.connect(self.accept)
        layout.addWidget(btn_zatvori)


class LocatorDialog(QDialog):
    """Dijalog za unos adrese i pozicioniranje na mapi (OSM Nominatim)."""
    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        self.core = core
        self.setWindowTitle("Locator - Find Address on Map")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.edit_country = QLineEdit()
        self.edit_city = QLineEdit()
        self.edit_municipality = QLineEdit()
        self.edit_street = QLineEdit()
        self.edit_number = QLineEdit()

        form.addRow("Country:", self.edit_country)
        form.addRow("City:", self.edit_city)
        form.addRow("Municipality (optional):", self.edit_municipality)
        form.addRow("Street:", self.edit_street)
        form.addRow("Number:", self.edit_number)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        self.btn_find = QPushButton("Find on map")
        btns.addButton(self.btn_find, QDialogButtonBox.ActionRole)
        self.btn_find.clicked.connect(self._on_find_clicked)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_find_clicked(self):
        # Sastavi upit
        s = self.edit_street.text().strip()
        n = self.edit_number.text().strip()
        parts = []
        if s:
            parts.append(s + (f" {n}" if n else ""))

        m = self.edit_municipality.text().strip()
        if m:
            parts.append(m)

        c = self.edit_city.text().strip()
        if c:
            parts.append(c)

        co = self.edit_country.text().strip()
        if co:
            parts.append(co)

        if not parts:
            QMessageBox.warning(self, "Locator", "Please enter at least City and Country (Street/Number recommended).")
            return

        query = ", ".join(parts)

        # Pozovi Nominatim (OSM) – bez dodatnih biblioteka
        try:
            import urllib.parse, urllib.request, json, ssl
            url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + urllib.parse.quote(query)
            headers = {"User-Agent": "FiberQ/1.0 (contact: vukovicvl@fiberq.net)"}
            req = urllib.request.Request(url, headers=headers)
            context = ssl.create_default_context()
            with urllib.request.urlopen(req, context=context, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if not data:
                QMessageBox.information(self, "Locator", f"No location found for: {query}")
                return

            lat = float(data[0].get("lat"))
            lon = float(data[0].get("lon"))
            self.core._center_and_mark_wgs84(lon, lat, label=query)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error during geocoding: {e}")

# === RELACIJE DIALOGI ===
from qgis.PyQt.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QSplitter, QHBoxLayout, QGroupBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from qgis.PyQt.QtCore import Qt
import uuid
import json
from datetime import datetime


# === NOVO: Optički šematski prikaz ===
class SchematicView(QGraphicsView):
    """QGraphicsView sa praktičnim zumiranjem; pan se pali kao ScrollHandDrag."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from qgis.PyQt.QtGui import QPainter
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        self.scale(factor, factor)


class OpticalSchematicDialog(QDialog):
    """
    Optički šematski prikaz sa:
      - pan/zoom (točkić, Pan toggle, Zoom+/Zoom-, Fit)
      - filterima (glavni/distrib/razvodni, podzemni/vazdušni, kapacitet, relacija, prikaži oznake)
      - pretragom i centriranjem na element
      - pravilom rasporeda: OR → glavni (osa), grane naniže
      - mini legendom boja
      - export PNG/SVG
    """
    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        from qgis.PyQt.QtWidgets import (
            QCheckBox, QToolButton, QFrame, QLabel, QLineEdit, QSpinBox, QCompleter
        )
        self.core = core
        self.setWindowTitle("Optical Schematic View")
        self.resize(1200, 760)

        # Scene & View
        self.scene = QGraphicsScene(self)
        self.view = SchematicView(self.scene, self)

        # --- Gornja traka: kontrole ---
        top = QHBoxLayout()

        # Pan / Zoom kontrole
        self.btn_pan = QToolButton(); self.btn_pan.setText("Pan"); self.btn_pan.setCheckable(True)
        self.btn_pan.toggled.connect(self._toggle_pan)
        self.btn_zoom_in = QPushButton("Zoom +"); self.btn_zoom_in.clicked.connect(lambda: self.view.scale(1.25, 1.25))
        self.btn_zoom_out = QPushButton("Zoom −"); self.btn_zoom_out.clicked.connect(lambda: self.view.scale(0.8, 0.8))
        self.btn_fit = QPushButton("Fit"); self.btn_fit.clicked.connect(self._fit)

        # Filteri po tipu
        self.chk_glavni = QCheckBox("Backbone"); self.chk_glavni.setChecked(True)
        self.chk_distrib = QCheckBox("Distributive"); self.chk_distrib.setChecked(True)
        self.chk_razvod = QCheckBox("Drop"); self.chk_razvod.setChecked(True)
        self.chk_podzemni = QCheckBox("Underground"); self.chk_podzemni.setChecked(True)
        self.chk_vazdusni = QCheckBox("Aerial"); self.chk_vazdusni.setChecked(True)
        self.chk_labels = QCheckBox("Show labels"); self.chk_labels.setChecked(True)
        self.chk_map_layout = QCheckBox("Match map styling"); self.chk_map_layout.setChecked(False)

        # Filteri kapacitet/relacija
        self.cap_min = QSpinBox(); self.cap_min.setPrefix("Cap ≥ "); self.cap_min.setMaximum(9999); self.cap_min.setValue(0)
        self.cap_max = QSpinBox(); self.cap_max.setPrefix("Cap ≤ "); self.cap_max.setMaximum(9999); self.cap_max.setValue(0)
        self.txt_rel = QLineEdit(); self.txt_rel.setPlaceholderText("Relation contains…")

        # Pretraga / centriranje
        self.txt_search = QLineEdit(); self.txt_search.setPlaceholderText("Find element…")
        self.btn_center = QPushButton("Center"); self.btn_center.clicked.connect(self._center_on_query)
        self._completer = QCompleter([]); self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.txt_search.setCompleter(self._completer)

        # Dugmad primeni/osveži + export
        self.btn_apply = QPushButton("Apply"); self.btn_apply.clicked.connect(self.rebuild)
        self.btn_refresh = QPushButton("Refresh"); self.btn_refresh.clicked.connect(self.rebuild)
        self.btn_png = QPushButton("PNG"); self.btn_png.clicked.connect(self._export_png)
        self.btn_jpg = QPushButton("JPG"); self.btn_jpg.clicked.connect(self._export_jpg)
        self.btn_svg = QPushButton("SVG"); self.btn_svg.clicked.connect(self._export_svg)

        for w in [self.btn_pan, self.btn_zoom_in, self.btn_zoom_out, self.btn_fit, self.chk_map_layout,
                  self.chk_glavni, self.chk_distrib, self.chk_razvod,
                  self.chk_podzemni, self.chk_vazdusni, self.chk_labels,
                  self.cap_min, self.cap_max, self.txt_rel,
                  self.txt_search, self.btn_center,
                  self.btn_apply, self.btn_refresh, self.btn_png, self.btn_jpg, self.btn_svg]:
            top.addWidget(w)
        top.addStretch()

        # --- Legenda (mala traka) ---
        legend = QHBoxLayout()
        legend.addWidget(QLabel("Legend:"))
        def swatch(color, text):
            box = QFrame(); box.setFixedSize(20, 10); box.setStyleSheet("background:%s; border:1px solid #333;" % color)
            legend.addWidget(box); legend.addWidget(QLabel(text))
        swatch("#003399", "Backbone")
        swatch("#cc0000", "Distributive")
        swatch("#a52a2a", "Drop")
        swatch("#ff8c00", "Pipes")
        legend_w = QWidget(); legend_w.setLayout(legend)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(legend_w)
        lay.addWidget(self.view)

         # Debounce timer za automatski rebuild
        from qgis.PyQt.QtCore import QTimer
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(400)  # ms, po želji 200–500
        self._rebuild_timer.timeout.connect(self._do_rebuild_if_needed)
        self._rebuild_pending = False


        # Auto-osvežavanje
        self._wired_layers = set()
        self._wire_all_layers()

        self.rebuild()

    # ---------- UTIL ----------
    def _toggle_pan(self, on):
        self.view.setDragMode(QGraphicsView.ScrollHandDrag if on else QGraphicsView.NoDrag)

    def _fit(self):
        rect = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.view.setSceneRect(rect)
        self.view.fitInView(rect, Qt.KeepAspectRatio)

    def _parse_capacity(self, value):
        """Izvuci prvi broj iz kapaciteta; ako nema broja, vrati None."""
        import re as _re
        if value is None:
            return None
        m = _re.search(r'\d+', str(value))
        return int(m.group(0)) if m else None

    def _center_on_query(self):
        name = self.txt_search.text().strip()
        if name:
            self._center_on(name)

    def _center_on(self, name):
        pos = getattr(self, "_last_positions", {})
        if name in pos:
            x, y = pos[name]
            self.view.centerOn(x, y)
            # naglasi na trenutak
            r = 12.0
            item = self.scene.addEllipse(x-r, y-r, 2*r, 2*r, QPen(QColor(255,165,0), 2.4), Qt.NoBrush)
            item.setZValue(10)
            from qgis.PyQt.QtCore import QTimer
            def _remove():
                self.scene.removeItem(item)
            QTimer.singleShot(1300, _remove)

    # ---------- PODACI ----------
    
    def _collect_nodes(self):
        nodes = {}
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry:
                    lname = lyr.name()
                    fields = lyr.fields()
                    has_naziv = fields.indexFromName('naziv') != -1

                    # >>> dodato <<<
                    is_manhole_layer = lname in ('OKNA', 'Manholes')
                    has_broj_okna = (
                        fields.indexFromName('broj_okna') != -1
                        if is_manhole_layer
                        else False
                    )

                    for f in lyr.getFeatures():
                        nm = None
                        # 1) Manholes (OKNA): KO + broj_okna
                        if is_manhole_layer and has_broj_okna:
                            val = f['broj_okna']
                            if val is not None and str(val).strip():
                                nm = f"KO {str(val).strip()}"

                        # 2) ostali slojevi sa poljem 'naziv'
                        if nm is None and has_naziv:
                            val = f['naziv']
                            if val is not None and str(val).strip():
                                nm = str(val).strip()

                        # 3) Stubovi fallback
                        if nm is None and lname == 'Stubovi':
                            try:
                                tip = (
                                    str(f['tip']).strip()
                                    if fields.indexFromName('tip') != -1 and f['tip'] is not None
                                    else ''
                                )
                            except Exception:
                                tip = ''
                            nm = ("Stub " + tip).strip() or f"Stub {int(f.id())}"

                        if nm and nm not in nodes:
                            nodes[nm] = {
                                "layer_id": lyr.id(),
                                "layer_name": lname,
                                "fid": int(f.id()),
                            }
            except Exception:
                continue
        return nodes


    def _collect_edges(self):
        """List_all_cables + očitavanje atributa sa sloja; vraća listu dict-ova."""
        items = self.core.list_all_cables() + self.core.list_all_pipes()
        edges = []
        for it in items:
            lyr = QgsProject.instance().mapLayer(it.get('layer_id'))
            if not lyr or not isinstance(lyr, QgsVectorLayer):
                continue
            feat = None
            for _f in lyr.getFeatures():
                if int(_f.id()) == int(it.get('fid')):
                    feat = _f; break
            if not feat:
                continue

            geom = feat.geometry()
            # prikupljanje koordinata geometrije (transformisano u projekcioni CRS)
            try:
                srcCrs = lyr.crs()
                dstCrs = QgsProject.instance().crs()
                xform = QgsCoordinateTransform(srcCrs, dstCrs, QgsProject.instance())
                coords = []
                if geom.isMultipart():
                    parts = geom.asMultiPolyline()
                    for pl in parts:
                        for p in pl:
                            pt = xform.transform(QgsPointXY(p.x(), p.y()))
                            coords.append((pt.x(), pt.y()))
                else:
                    pl = geom.asPolyline()
                    for p in pl:
                        pt = xform.transform(QgsPointXY(p.x(), p.y()))
                        coords.append((pt.x(), pt.y()))
            except Exception:
                coords = []
            try:
                length_m = float(geom.length())
            except Exception:
                length_m = 0.0

            lname = (it.get('layer_name') or lyr.name() or '').lower()
            vrsta = 'vazdusni' if 'vazdu' in lname else 'podzemni'

            # Atributi: uzmi iz 'it' ako ima, inače iz feature polja
            def gv(key):
                if it.get(key) not in (None, ''):
                    return it.get(key)
                idx = lyr.fields().indexFromName(key)
                return feat[key] if idx != -1 else ''

            edges.append({
                "from": str(gv('od')).strip(),
                "to":   str(gv('do')).strip(),
                "podtip": str(gv('podtip')).lower(),
                "kapacitet": gv('kapacitet'),
                "geom_coords": coords,
                "length": length_m,
                "vrsta": vrsta,
                "relacija": str(gv('relacija')).lower()
            })
        return edges

    # ---------- LAYOUT ----------
    def _rank_for_layer(self, layer_name: str):
        lname = (layer_name or "").lower()
        if lname.strip() == "or":
            return 0
        if "nastav" in lname:
            return 1
        return 2

    def _main_chain_from_or(self, nodes, edges):
        # adjacency za 'glavni'
        adj = {}
        for e in edges:
            if e['podtip'] != 'glavni':
                continue
            a, b = e['from'], e['to']
            if not a or not b:
                continue
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)

        if not adj:
            return []

        layer_by_name = {n: nodes[n]['layer_name'] for n in nodes}
        or_nodes = [n for n in adj if self._rank_for_layer(layer_by_name.get(n, "")) == 0]
        start = max(or_nodes, key=lambda n: len(adj.get(n, []))) if or_nodes else max(adj, key=lambda n: len(adj.get(n, [])))

        chain = []
        visited = set()
        cur = start; prev = None
        while cur is not None:
            chain.append(cur); visited.add(cur)
            nxts = [n for n in adj.get(cur, []) if n != prev]
            if not nxts:
                break
            prev, cur = cur, nxts[0]
        return chain

    def _build_layout(self, nodes, edges):
        """Filtriranje + pozicije čvorova + orto-polilinije grana."""
        # Filteri podtip/vrsta
        keep_podtip = {
            t for t, chk in [
                ('glavni', self.chk_glavni),
                ('distributivni', self.chk_distrib),
                ('razvodni', self.chk_razvod),
            ]
            if chk.isChecked()
        }
        keep_vrsta = {
            t for t, chk in [
                ('podzemni', self.chk_podzemni),
                ('vazdusni', self.chk_vazdusni),
            ]
            if chk.isChecked()
        }

        # Filter relacije
        rel_q = self.txt_rel.text().strip().lower()
        # Filter kapaciteta
        cap_min = self.cap_min.value() or 0
        cap_max = self.cap_max.value() or 0  # 0 = bez gornje granice

        def pass_filters(e):
            if e['podtip'] not in keep_podtip or e['vrsta'] not in keep_vrsta:
                return False
            if rel_q and rel_q not in (e.get('relacija') or ''):
                return False
            cap_val = self._parse_capacity(e.get('kapacitet'))
            if cap_min and (cap_val is None or cap_val < cap_min):
                return False
            if cap_max and (cap_val is not None and cap_val > cap_max):
                return False
            return e['from'] and e['to']

        edges_f = [e for e in edges if pass_filters(e)]

        # --- MAP LAYOUT: use real coordinates from map ---
        if getattr(self, 'chk_map_layout', None) and self.chk_map_layout.isChecked():
            # Prepare node positions according to centroids/points
            pos = {}
            world_points = []
            from qgis.core import QgsGeometry
            for name, info in nodes.items():
                try:
                    lyr = QgsProject.instance().mapLayer(info.get('layer_id'))
                    fid = int(info.get('fid'))
                    feat = next((f for f in lyr.getFeatures() if int(f.id()) == fid), None)
                    if not feat:
                        continue
                    g = feat.geometry()
                    # Izvuci jednu reprezentativnu tačku
                    pt = None
                    if g.isEmpty():
                        continue
                    if g.type() == QgsWkbTypes.PointGeometry:
                        pt = g.asPoint()
                    elif g.type() == QgsWkbTypes.LineGeometry:
                        try:
                            d = g.length()
                            pt = g.interpolate(d / 2.0).asPoint()
                        except Exception:
                            ps = g.asPolyline()
                            pt = ps[len(ps) // 2] if ps else None
                    else:
                        try:
                            pt = g.centroid().asPoint()
                        except Exception:
                            pt = None
                    if pt is None:
                        continue
                    # transformiši u projekcioni CRS
                    src = lyr.crs()
                    dst = QgsProject.instance().crs()
                    tr = QgsCoordinateTransform(src, dst, QgsProject.instance())
                    ptt = tr.transform(QgsPointXY(pt.x(), pt.y()))
                    pos[name] = (ptt.x(), ptt.y())
                    world_points.append((ptt.x(), ptt.y()))
                except Exception:
                    continue

            # Add all points from cable/pipe geometry
            for e in edges_f:
                coords = e.get('geom_coords') or []
                for x, y in coords:
                    world_points.append((x, y))

            # If no points, return empty layout
            if not world_points:
                return {}, []

            minx = min(x for x, _ in world_points)
            maxx = max(x for x, _ in world_points)
            miny = min(y for _, y in world_points)
            maxy = max(y for _, y in world_points)
            w = max(1.0, maxx - minx)
            h = max(1.0, maxy - miny)
            target_w, target_h = 1600.0, 1000.0
            scale = min(target_w / w, target_h / h)
            pad = 20.0

            def tx(x, y):
                # zadrži sever na gore (invertuj Y za QGraphics)
                X = (x - minx) * scale + pad
                Y = (maxy - y) * scale + pad
                return (X, Y)

            # transformiši pozicije čvorova
            pos = {name: tx(x, y) for name, (x, y) in pos.items()}

            # izgradi putanje linija na osnovu originalne geometrije
            lines = []
            for e in edges_f:
                coords = e.get('geom_coords') or []
                if coords:
                    path = [tx(x, y) for (x, y) in coords]
                else:
                    a = pos.get(e.get('from'))
                    b = pos.get(e.get('to'))
                    if not a or not b:
                        continue
                    path = [a, b]
                lines.append((e, path))

            # sačuvaj pozicije za pretragu
            self._last_positions = pos
            try:
                model = self._completer.model()
                from qgis.PyQt.QtCore import QStringListModel
                if not isinstance(model, QStringListModel):
                    model = QStringListModel()
                    self._completer.setModel(model)
                model.setStringList(sorted(pos.keys()))
            except Exception:
                pass

            return pos, lines

        # ---------- ŠEMATSKI LAYOUT (bez 'Kao na mapi') ----------

        # Indeksi po čvorovima
        by_from = {}
        for e in edges_f:
            by_from.setdefault(e['from'], []).append(e)
            by_from.setdefault(e['to'], []).append({**e, 'from': e['to'], 'to': e['from']})

        # Glavna osa (OR lanac po glavnim kablovima)
        main_nodes = self._main_chain_from_or(nodes, edges_f)
        pos = {}
        x_step = 190.0
        y_step = 140.0

        if main_nodes:
            # --- Postoje glavni kablovi: zadrži stari algoritam ---
            for i, n in enumerate(main_nodes):
                pos[n] = (i * x_step, 0.0)

            # Grane naniže
            branch_rank = {'distributivni': 0, 'razvodni': 1}
            taken = set()
            for src in main_nodes:
                outs = [e for e in by_from.get(src, []) if e['podtip'] != 'glavni']
                outs.sort(key=lambda e: branch_rank.get(e['podtip'], 99))
                col = 0
                for e in outs:
                    child = e['to']
                    if (src, child) in taken:
                        continue
                    taken.add((src, child))
                    taken.add((child, src))
                    bx, by = pos[src]
                    x = bx + 35 + col * 26
                    chain = [src, child]
                    seen = set(chain)
                    cur = child
                    while True:
                        nxts = [
                            ed for ed in by_from.get(cur, [])
                            if ed['podtip'] != 'glavni' and ed['to'] not in seen
                        ]
                        if not nxts:
                            break
                        cur = nxts[0]['to']
                        chain.append(cur)
                        seen.add(cur)
                    for j, node_name in enumerate(chain[1:], start=1):
                        pos[node_name] = (x, -j * y_step)
                    col += 1

            # Neinicirani čvorovi – desno od glavne ose
            leftovers = [n for n in nodes.keys() if n not in pos]
            leftovers.sort(
                key=lambda n: (self._rank_for_layer(nodes[n].get('layer_name', '')), n)
            )
            for i, n in enumerate(leftovers, start=1):
                pos[n] = (len(main_nodes) * x_step + (i // 8) * x_step,
                          -(i % 8) * y_step)
        else:
            # --- NEMA glavnih kablova: grupiši po komponentama ---
            # adj lista po svim kablovima (bez obzira na podtip)
            adj = {}
            for e in edges_f:
                a, b = e['from'], e['to']
                if not a or not b:
                    continue
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
            # ensure isolated nodes also appear
            for n in nodes.keys():
                adj.setdefault(n, set())

            # split into components
            visited = set()
            components = []

            for n in nodes.keys():
                if n in visited:
                    continue
                stack = [n]
                comp = []
                while stack:
                    cur = stack.pop()
                    if cur in visited:
                        continue
                    visited.add(cur)
                    comp.append(cur)
                    for nb in adj.get(cur, []):
                        if nb not in visited:
                            stack.append(nb)
                components.append(comp)

            def node_sort_key(nn):
                return (self._rank_for_layer(nodes[nn].get('layer_name', '')), nn)

            # sort komponente po "najvažnijem" čvoru
            components.sort(key=lambda comp: min(node_sort_key(nn) for nn in comp))

            # svaka komponenta dobija svoju kolonu
            for ci, comp in enumerate(components):
                comp_sorted = sorted(comp, key=node_sort_key)
                x = ci * x_step
                for j, n in enumerate(comp_sorted):
                    pos[n] = (x, -j * y_step)

        # Polilinije
        lines = []
        for e in edges_f:
            a, b = e['from'], e['to']
            if a in pos and b in pos:
                ax, ay = pos[a]
                bx, by = pos[b]
                midy = (ay + by) / 2.0
                path = [(ax, ay), (ax, midy), (bx, midy), (bx, by)]
                lines.append((e, path))

        # zapamti za pretragu
        self._last_positions = pos
        # osveži completer
        try:
            model = self._completer.model()
            from qgis.PyQt.QtCore import QStringListModel
            if not isinstance(model, QStringListModel):
                model = QStringListModel()
                self._completer.setModel(model)
            model.setStringList(sorted(pos.keys()))
        except Exception:
            pass

        return pos, lines


    # ---------- CRTANJE ----------
    def rebuild(self):
        self.scene.clear()
        nodes = self._collect_nodes()
        edges = self._collect_edges()
        pos, lines = self._build_layout(nodes, edges)

        def color_for(e):
            t = (e.get('podtip') or '').lower()
            lname = (e.get('layer_name') or '').lower()
            if 'glavni' in t:      return QColor(0, 51, 153)
            if 'distribut' in t:   return QColor(204, 0, 0)
            if 'razvod' in t:      return QColor(165, 42, 42)
            if 'cev' in t or 'cevi' in lname: return QColor(255, 140, 0)
            return QColor(60, 60, 60)

        # izbegavanje sudara etiketa
        occupied = []

        def place_text(x, y, txt, color):
            if not txt:
                return
            ti = self.scene.addText(txt, QFont("Arial", 9))
            ti.setDefaultTextColor(color)
            offsets = [(8, -8), (10, 10), (-22, -10), (-22, 12), (8, 12), (12, 0)]
            for dx, dy in offsets:
                ti.setPos(x + dx, y + dy)
                rect = ti.mapRectToScene(ti.boundingRect())
                if not any(rect.intersects(r) for r in occupied):
                    bg = rect.adjusted(-2, -1, 2, 2)
                    self.scene.addRect(bg, QPen(Qt.NoPen), QColor(255,255,255,210)).setZValue(ti.zValue()-1)
                    occupied.append(bg)
                    return
            occupied.append(ti.mapRectToScene(ti.boundingRect()))

        # grane + labele
        for e, path in lines:
            pen = QPen(color_for(e)); pen.setWidthF(2.2)
            # Cevi – iscrtaj isprekidano radi lakše razlike
            try:
                if 'cevi' in (e.get('layer_name') or '').lower() or (e.get('podtip') or '').lower() == 'cev':
                    pen.setStyle(Qt.DashLine)
            except Exception:
                pass
            gp = QPainterPath(); x0, y0 = path[0]; gp.moveTo(x0, y0)
            for x, y in path[1:]: gp.lineTo(x, y)
            self.scene.addPath(gp, pen)
            if self.chk_labels.isChecked():
                mid_idx = len(path) // 2; mx, my = path[mid_idx]
                text = f"{e.get('kapacitet','')}".strip()
                if e.get('length', 0.0):
                    text = (text + (" / " if text else "")) + f"{round(e['length'],1)} m"
                place_text(mx, my, text, pen.color())

        # čvorovi + labele
        for name, meta in nodes.items():
            x, y = pos.get(name, (0.0, 0.0))
            r = 6.0
            self.scene.addEllipse(x-r, y-r, 2*r, 2*r, QPen(Qt.black), QColor(240,240,240))
            if self.chk_labels.isChecked():
                place_text(x, y, str(name), QColor(10,10,10))

        self._fit()

    # ---------- EXPORT ----------
    def _export_png(self):
        from qgis.PyQt.QtGui import QImage, QPainter
        rect = self.scene.itemsBoundingRect().adjusted(10,10,10,10)
        img = QImage(int(rect.width())+40, int(rect.height())+40, QImage.Format_ARGB32)
        img.fill(0x00ffffff)
        p = QPainter(img)
        p.translate(-rect.x()+20, -rect.y()+20)
        self.scene.render(p)
        p.end()
        from qgis.PyQt.QtWidgets import QFileDialog
        fn, _ = QFileDialog.getSaveFileName(self, "Sačuvaj PNG", "opticki_sematski.png", "PNG (*.png)")
        if fn:
            img.save(fn, "PNG")

    def _export_jpg(self):
        from qgis.PyQt.QtGui import QImage, QPainter
        rect = self.scene.itemsBoundingRect().adjusted(10,10,10,10)
        img = QImage(int(rect.width())+40, int(rect.height())+40, QImage.Format_RGB32)
        img.fill(0xffffffff)
        p = QPainter(img)
        p.translate(-rect.x()+20, -rect.y()+20)
        self.scene.render(p)
        p.end()
        from qgis.PyQt.QtWidgets import QFileDialog
        fn, _ = QFileDialog.getSaveFileName(self, "Sačuvaj JPG", "opticki_sematski.jpg", "JPG (*.jpg)")
        if fn:
            img.save(fn, "JPG")

    def _export_svg(self):
        try:
            from qgis.PyQt.QtSvg import QSvgGenerator
            from qgis.PyQt.QtGui import QPainter
            from qgis.PyQt.QtWidgets import QFileDialog
        except Exception:
            return
        rect = self.scene.itemsBoundingRect().adjusted(10,10,10,10)
        fn, _ = QFileDialog.getSaveFileName(self, "Sačuvaj SVG", "opticki_sematski.svg", "SVG (*.svg)")
        if not fn:
            return
        gen = QSvgGenerator()
        gen.setFileName(fn)
        gen.setSize(QSize(int(rect.width())+40, int(rect.height())+40))
        gen.setViewBox(QRect(0,0,int(rect.width())+40,int(rect.height())+40))
        p = QPainter(gen)
        p.translate(-rect.x()+20, -rect.y()+20)
        self.scene.render(p)
        p.end()

    def _schedule_rebuild(self):
        """
        Debounced rebuild – koristi se za automatske promene na slojevima.
        """
        try:
            self._rebuild_pending = True
            if getattr(self, "_rebuild_timer", None) is not None:
                # restart timer – multiple changes in short time -> one rebuild
                self._rebuild_timer.start()
            else:
                # fallback, if no timer
                self._rebuild_pending = False
                self.rebuild()
        except Exception:
            # if something goes wrong, don't block – do direct rebuild
            self._rebuild_pending = False
            self.rebuild()

    def _do_rebuild_if_needed(self):
        """
        Poziva se iz QTimer.timeout – stvarno radi rebuild ako je nešto tražilo.
        """
        if not getattr(self, "_rebuild_pending", False):
            return
        self._rebuild_pending = False
        self.rebuild()


    # ---------- SIGNALI ----------
    def _wire_all_layers(self):
        prj = QgsProject.instance()
        try:
            prj.layersAdded.connect(lambda *_: self._schedule_rebuild())
            prj.layerWillBeRemoved.connect(lambda *_: self._schedule_rebuild())
        except Exception:
            pass
        for lyr in QgsProject.instance().mapLayers().values():
            self._wire_layer(lyr)

    def _layer_committed(self, *args, **kwargs):
        # umesto direktnog rebuild-a radimo debounce
        self._schedule_rebuild()


    def _wire_layer(self, lyr):
        if not isinstance(lyr, QgsVectorLayer):
            return
        if lyr.id() in getattr(self, "_wired_layers", set()):
            return
        self._wired_layers.add(lyr.id())
        try:
            lyr.committedFeaturesAdded.connect(self._layer_committed)
            lyr.committedFeaturesRemoved.connect(self._layer_committed)
            lyr.committedAttributeValuesChanges.connect(self._layer_committed)
            lyr.committedGeometriesChanges.connect(self._layer_committed)
            lyr.layerModified.connect(self._layer_committed)
        except Exception:
            pass

RELACIJE_KATEGORIJE = [
    "Main",
    "Local",
    "International",
    "Metro network",
    "Regional",
]


class NewRelationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Optical Relation")
        self.setMinimumWidth(380)

        v = QVBoxLayout(self)
        title = QLabel("<b>New main relation</b>")
        v.addWidget(title)

        form = QFormLayout()
        self.edit_name = QLineEdit()
        self.cmb_cat = QComboBox()
        self.cmb_cat.addItems(RELACIJE_KATEGORIJE)
        form.addRow("Name:", self.edit_name)
        form.addRow("Category:", self.cmb_cat)
        v.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def values(self):
        return {
            "id": str(uuid.uuid4()),
            "name": self.edit_name.text().strip(),
            "category": self.cmb_cat.currentText(),
            "created": datetime.utcnow().isoformat() + "Z",
            "cables": []  # list of {"layer_id":, "fid":}
        }


class RelationsDialog(QDialog):
    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        self.core = core
        self.setWindowTitle("Optical relations management")
        self.setMinimumSize(700, 520)

        # Load data
        self.data = self.core._load_relations()

        # UI
        main = QVBoxLayout(self)
        splitter = QSplitter(Qt.Vertical)
        main.addWidget(splitter)

        # Top: relations + buttons
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("New relation")
        self.btn_delete = QPushButton("Delete relation")
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch()
        top_layout.addLayout(btn_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Relation", "Category"])
        self.tree.setColumnWidth(0, 320)
        top_layout.addWidget(self.tree)

        splitter.addWidget(top_widget)

        # Bottom: cables list and assign buttons
        bottom = QWidget()
        bl = QVBoxLayout(bottom)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(3)
        self.tbl.setHorizontalHeaderLabels(["Cable", "Layer", "Relation"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        bl.addWidget(self.tbl)

        row_btns = QHBoxLayout()
        self.btn_assign = QPushButton("Add to selected relation")
        self.btn_remove = QPushButton("Remove from relation")
        row_btns.addWidget(self.btn_assign)
        row_btns.addWidget(self.btn_remove)
        row_btns.addStretch()
        bl.addLayout(row_btns)

        splitter.addWidget(bottom)

        # Signals
        self.btn_new.clicked.connect(self._on_add_relation)
        self.btn_delete.clicked.connect(self._on_delete_relation)
        self.btn_assign.clicked.connect(self._on_assign_to_relation)
        self.btn_remove.clicked.connect(self._on_remove_from_relation)
        self.tree.itemSelectionChanged.connect(self._refresh_cables_relation_column)

        # Populate
        self._refresh_relations_tree()
        self._load_cables()

    # --- Data helpers
    def _refresh_relations_tree(self):
        self.tree.clear()
        for r in self.data.get("relations", []):
            it = QTreeWidgetItem([r.get("name",""), r.get("category","")])
            it.setData(0, Qt.UserRole, r.get("id"))
            self.tree.addTopLevelItem(it)
        if self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _current_relation_id(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def _on_add_relation(self):
        dlg = NewRelationDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            vals = dlg.values()
            if not vals["name"]:
                QMessageBox.warning(self, "Relations", "Relation name is required.")
                return
            self.data.setdefault("relations", []).append(vals)
            self.core._save_relations(self.data)
            self._refresh_relations_tree()

    def _on_delete_relation(self):
        rid = self._current_relation_id()
        if not rid:
            return
        reply = QMessageBox.question(self, "Relations", "Delete selected relation?")
        if reply != QMessageBox.Yes:
            return
        self.data["relations"] = [r for r in self.data.get("relations", []) if r.get("id") != rid]
        self.core._save_relations(self.data)
        self._refresh_relations_tree()
        self._refresh_cables_relation_column()

    def _load_cables(self):
        self.cables = self.core.list_all_cables()
        self.tbl.setRowCount(len(self.cables))
        for row, c in enumerate(self.cables):
            self.tbl.setItem(row, 0, QTableWidgetItem(c["opis"]))
            self.tbl.setItem(row, 1, QTableWidgetItem(c["layer_name"]))
        self._refresh_cables_relation_column()

    def _refresh_cables_relation_column(self):
        # Defensive guard if dialog reopened before cables are loaded
        if not hasattr(self, 'cables') or self.cables is None:
            self.cables = []
        rid = self._current_relation_id()
        # Show assigned relation names for all cables (not only the selected relation).
        rel_name_by_cable = {}
        for r in self.data.get("relations", []):
            for c in r.get("cables", []):
                key = (c.get("layer_id"), int(c.get("fid")))
                rel_name_by_cable[key] = r.get("name")
        for row, c in enumerate(self.cables):
            key = (c["layer_id"], c["fid"])
            nm = rel_name_by_cable.get(key, "")
            self.tbl.setItem(row, 2, QTableWidgetItem(nm))

    def _on_assign_to_relation(self):
        rid = self._current_relation_id()
        if not rid:
            QMessageBox.information(self, "Relations", "Select a relation in the upper list.")
            return
        rel = self.core._relation_by_id(self.data, rid)
        if not rel:
            return
        rows = {i.row() for i in self.tbl.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "Relations", "Select cables in the table.")
            return
        assigned = set((c.get("layer_id"), int(c.get("fid"))) for c in rel.get("cables", []))
        for row in rows:
            c = self.cables[row]
            key = (c["layer_id"], c["fid"])
            if key not in assigned:
                rel.setdefault("cables", []).append({"layer_id": c["layer_id"], "fid": int(c["fid"])})
        self.core._save_relations(self.data)
        self._refresh_cables_relation_column()

    def _on_remove_from_relation(self):
        rid = self._current_relation_id()
        if not rid:
            return
        rel = self.core._relation_by_id(self.data, rid)
        if not rel:
            return
        rows = {i.row() for i in self.tbl.selectedIndexes()}
        if not rows:
            return
        # remove only from current relation
        keep = []
        remove_keys = set()
        for row in rows:
            c = self.cables[row]
            remove_keys.add((c["layer_id"], c["fid"]))
        for c in rel.get("cables", []):
            key = (c.get("layer_id"), int(c.get("fid")))
            if key not in remove_keys:
                keep.append(c)
        rel["cables"] = keep
        self.core._save_relations(self.data)
        self._refresh_cables_relation_column()

# === DIALOG: Lista latentnih elemenata (overview) ===
class LatentElementsDialog(QDialog):
    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        from qgis.PyQt.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QCheckBox
        self.core = core
        self.setWindowTitle("List of latent elements")
        self.resize(820, 520)

        self.data = self.core._load_latent()
        self._rel_map = self.core._relation_name_by_cable()

        layout = QVBoxLayout(self)
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(6)
        self.tbl.setHorizontalHeaderLabels(["", "ID", "Name", "M", "SM", "Edit"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setSelectionBehavior(self.tbl.SelectRows)
        layout.addWidget(self.tbl)

        self._load_cables()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _load_cables(self):
        self.cables = self.core.list_all_cables()
        self.tbl.setRowCount(len(self.cables))
        for row, c in enumerate(self.cables):
            layer = QgsProject.instance().mapLayer(c["layer_id"])
            feat = None
            # Select checkbox
            chk = QCheckBox()
            def on_toggled(checked, lyr=layer, fid=int(c["fid"])):
                try:
                    if lyr is None:
                        return
                    if checked:
                        # deselect others
                        for l in QgsProject.instance().mapLayers().values():
                            if isinstance(l, QgsVectorLayer):
                                l.removeSelection()
                        lyr.selectByIds([fid])
                        self.core.iface.mapCanvas().zoomToSelected(lyr)
                    else:
                        lyr.removeSelection()
                except Exception:
                    pass
            chk.toggled.connect(on_toggled)
            self.tbl.setCellWidget(row, 0, chk)

            # ID
            self.tbl.setItem(row, 1, QTableWidgetItem(str(c["fid"])))
            # Name from relations
            nm = self._rel_map.get((c["layer_id"], c["fid"]), "")
            self.tbl.setItem(row, 2, QTableWidgetItem(nm))
            # M/SM counts from latent store
            m_cnt, sm_cnt = self._latent_counts_for_cable(c)
            self.tbl.setItem(row, 3, QTableWidgetItem(str(m_cnt)))
            self.tbl.setItem(row, 4, QTableWidgetItem(str(sm_cnt)))
            # Edit button enable if there are >0 candidates
            btn = QPushButton("Edit")
            can_edit = False
            if layer and feat is None:
                # fetch feature by scanning (fallback)
                for f in layer.getFeatures():
                    if int(f.id()) == int(c["fid"]):
                        feat = f; break
            if layer and feat:
                cands = self.core._find_candidate_elements_for_cable(layer, feat)
                can_edit = len(cands) > 0
            btn.setEnabled(can_edit)
            def open_edit(lyr=layer, feat=feat, cdict=c, row=row):
                try:
                    d = CablePitstopsDialog(self.core, lyr, feat, cdict, self.data)
                    if d.exec_() == QDialog.Accepted:
                        # save updated data already saved in dialog; just refresh counts
                        m_cnt, sm_cnt = self._latent_counts_for_cable(cdict)
                        self.tbl.setItem(row, 3, QTableWidgetItem(str(m_cnt)))
                        self.tbl.setItem(row, 4, QTableWidgetItem(str(sm_cnt)))
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))
            btn.clicked.connect(open_edit)
            self.tbl.setCellWidget(row, 5, btn)

    def _latent_counts_for_cable(self, c):
        key = self.core._cable_key(c["layer_id"], c["fid"])
        rec = self.data.get("cables", {}).get(key, {})
        elems = rec.get("elements", [])
        m_cnt = sum(1 for e in elems if e.get("latent"))
        sm_cnt = sum(1 for e in elems if not e.get("latent"))
        return m_cnt, sm_cnt


# === DIALOG: Uređivanje pitstopova za jedan kabl ===
class CablePitstopsDialog(QDialog):
    def __init__(self, core, cable_layer, cable_feat, cable_dict, store):
        super().__init__(core.iface.mainWindow())
        from qgis.PyQt.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QPushButton
        self.core = core
        self.cable_layer = cable_layer
        self.cable_feat = cable_feat
        self.cable_dict = cable_dict
        self.store = store
        self.setWindowTitle("Latent elements - editing")
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(3)
        self.tbl.setHorizontalHeaderLabels(["#", "Element", "Latent"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tbl)

        # Buttons
        rowbtn = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")
        rowbtn.addWidget(self.btn_save); rowbtn.addWidget(self.btn_cancel); rowbtn.addStretch()
        layout.addLayout(rowbtn)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self._on_save)

        self._load_elements()

        # double-click toggles
        self.tbl.itemDoubleClicked.connect(self._toggle_row)

    def _load_elements(self):
        # candidates ordered
        cands = self.core._find_candidate_elements_for_cable(self.cable_layer, self.cable_feat)
        key = self.core._cable_key(self.cable_dict["layer_id"], self.cable_dict["fid"])
        saved = { (e.get("layer_id"), int(e.get("fid"))): bool(e.get("latent")) for e in self.store.get("cables", {}).get(key, {}).get("elements", []) }
        self.elements = []
        self.tbl.setRowCount(len(cands))
        for i, it in enumerate(cands, start=1):
            latent = saved.get((it["layer_id"], it["fid"]), False)
            self.elements.append({**it, "latent": latent})
            self.tbl.setItem(i-1, 0, QTableWidgetItem(str(i)))
            self.tbl.setItem(i-1, 1, QTableWidgetItem(it.get("naziv", f"{it['layer_name']}:{it['fid']}")))
            self.tbl.setItem(i-1, 2, QTableWidgetItem("YES" if latent else "NO"))

    def _toggle_row(self, item):
        row = item.row()
        if 0 <= row < len(self.elements):
            self.elements[row]["latent"] = not self.elements[row]["latent"]
            self.tbl.setItem(row, 2, QTableWidgetItem("YES" if self.elements[row]["latent"] else "NO"))

    def _on_save(self):
        # save to store and project
        key = self.core._cable_key(self.cable_dict["layer_id"], self.cable_dict["fid"])
        rec = {"elements": [
            {"layer_id": e["layer_id"], "fid": int(e["fid"]), "naziv": e.get("naziv",""), "latent": bool(e.get("latent"))}
            for e in self.elements
        ]}
        data = dict(self.store)
        data.setdefault("cables", {})[key] = rec
        self.core._save_latent(data)
        self.store.clear(); self.store.update(data)
        self.accept()


# ===================== KATALOG BOJA – DIALOGI =====================
class ColorCatalogManagerDialog(QDialog):
    """Pregled i uređivanje kataloga boja (standard za cevi/vlakna).
    Levo: lista kataloga; desno: raspored boja; Dole: + (novi), - (obriši), Sačuvaj/Zatvori.
    """
    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        from qgis.PyQt.QtWidgets import QListWidget, QListWidgetItem, QHBoxLayout, QGridLayout, QToolButton, QDialogButtonBox
        self.core = core
        self.setWindowTitle("Choose color catalogs")
        self.resize(720, 520)

        self.data = self.core._load_color_catalogs()
        self.catalogs = list(self.data.get("catalogs", []))

        # UI
        main = QVBoxLayout(self)
        grid = QGridLayout()
        main.addLayout(grid)

        lbl_left = QLabel("Standard")
        lbl_right = QLabel("Color arrangement")
        grid.addWidget(lbl_left, 0, 0)
        grid.addWidget(lbl_right, 0, 1)

        self.list_catalogs = QListWidget()
        self.list_colors = QListWidget()
        self.list_colors.setAlternatingRowColors(True)
        grid.addWidget(self.list_catalogs, 1, 0)
        grid.addWidget(self.list_colors, 1, 1)

        # Row of + / - for catalogs
        row_btns = QHBoxLayout()
        self.btn_add = QPushButton("+")
        self.btn_edit = QPushButton("✎")
        self.btn_del = QPushButton("-")
        self.btn_import = QPushButton("Import")
        self.btn_export = QPushButton("Export")
        self.btn_add.setFixedWidth(28); self.btn_edit.setFixedWidth(28); self.btn_del.setFixedWidth(28)
        row_btns.addWidget(self.btn_add)
        row_btns.addWidget(self.btn_edit)
        row_btns.addWidget(self.btn_del)
        row_btns.addSpacing(8)
        row_btns.addWidget(self.btn_import)
        row_btns.addWidget(self.btn_export)
        row_btns.addStretch()
        main.addLayout(row_btns)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        main.addWidget(btns)

        # Signals
        self.list_catalogs.currentRowChanged.connect(self._on_select_catalog)
        self.btn_add.clicked.connect(self._on_add_catalog)
        self.btn_edit.clicked.connect(self._on_edit_catalog)
        self.btn_del.clicked.connect(self._on_delete_catalog)
        self.btn_import.clicked.connect(self._on_import_catalog)
        self.btn_export.clicked.connect(self._on_export_catalog)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)

        self._refresh_catalog_list()
        if self.list_catalogs.count() > 0:
            self.list_catalogs.setCurrentRow(0)

    def _refresh_catalog_list(self):
        from qgis.PyQt.QtWidgets import QListWidgetItem
        self.list_catalogs.clear()
        for c in self.catalogs:
            it = QListWidgetItem(c.get("name",""))
            self.list_catalogs.addItem(it)

    def _on_select_catalog(self, row):
        from qgis.PyQt.QtWidgets import QListWidgetItem
        self.list_colors.clear()
        if 0 <= row < len(self.catalogs):
            cols = self.catalogs[row].get("colors", [])
            for col in cols:
                name = col.get("name","")
                hx = col.get("hex","#cccccc")
                it = QListWidgetItem(name)
                it.setBackground(QColor(hx))
                # if dark color, use white text
                try:
                    c = QColor(hx)
                    if c.red()*0.299 + c.green()*0.587 + c.blue()*0.114 < 140:
                        it.setForeground(QColor(255,255,255))
                except Exception:
                    pass
                self.list_colors.addItem(it)

    def _on_add_catalog(self):
        dlg = NewColorCatalogDialog(self.core, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            c = dlg.result_catalog()
            if c and c.get("name"):
                # replace if same name exists
                names = [x.get("name","") for x in self.catalogs]
                if c["name"] in names:
                    self.catalogs[names.index(c["name"])] = c
                else:
                    self.catalogs.append(c)
                self._refresh_catalog_list()
                self.list_catalogs.setCurrentRow(len(self.catalogs)-1)

    def _on_edit_catalog(self):
        row = self.list_catalogs.currentRow()
        if 0 <= row < len(self.catalogs):
            current = self.catalogs[row]
            dlg = NewColorCatalogDialog(self.core, parent=self, initial=current)
            if dlg.exec_() == QDialog.Accepted:
                updated = dlg.result_catalog()
                if updated and updated.get("name"):
                    names = [x.get("name","") for x in self.catalogs]
                    if updated["name"] in names and names.index(updated["name"]) != row:
                        self.catalogs[names.index(updated["name"])] = updated
                        del self.catalogs[row]
                        self._refresh_catalog_list()
                        self.list_catalogs.setCurrentRow(names.index(updated["name"]))
                    else:
                        self.catalogs[row] = updated
                        self._refresh_catalog_list()
                        self.list_catalogs.setCurrentRow(row)

    def _on_export_catalog(self):
        from qgis.PyQt.QtWidgets import QFileDialog
        row = self.list_catalogs.currentRow()
        if not (0 <= row < len(self.catalogs)):
            QMessageBox.warning(self, "Export", "Select a catalog to export.")
            return
        cat = self.catalogs[row]
        path, _ = QFileDialog.getSaveFileName(self, "Save catalog", f"{cat.get('name','catalog')}.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cat, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Export", "Catalog exported.")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Error saving: {e}")

    def _on_import_catalog(self):
        from qgis.PyQt.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Import catalog", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cat = json.load(f)
            if not isinstance(cat, dict) or 'name' not in cat or 'colors' not in cat:
                raise ValueError('Nepoznat format JSON-a')
            names = [x.get('name','') for x in self.catalogs]
            if cat['name'] in names:
                self.catalogs[names.index(cat['name'])] = cat
            else:
                self.catalogs.append(cat)
            self._refresh_catalog_list()
            self.list_catalogs.setCurrentRow(max(0, len(self.catalogs)-1))
            QMessageBox.information(self, "Import", "Catalog imported.")
        except Exception as e:
            QMessageBox.critical(self, "Import", f"Error: {e}")
    def _on_delete_catalog(self):
        row = self.list_catalogs.currentRow()
        if 0 <= row < len(self.catalogs):
            del self.catalogs[row]
            self._refresh_catalog_list()
            self.list_colors.clear()

    def _on_save(self):
        self.data["catalogs"] = self.catalogs
        self.core._save_color_catalogs(self.data)
        QMessageBox.information(self, "Color Catalog", "Saved.")
        self.accept()


    def _on_edit_catalog(self):
        row = self.list_catalogs.currentRow()
        if 0 <= row < len(self.catalogs):
            current = self.catalogs[row]
            dlg = NewColorCatalogDialog(self.core, parent=self, initial=current)
            if dlg.exec_() == QDialog.Accepted:
                updated = dlg.result_catalog()
                if updated and updated.get("name"):
                    names = [x.get("name","") for x in self.catalogs]
                    if updated["name"] in names and names.index(updated["name"]) != row:
                        self.catalogs[names.index(updated["name"])] = updated
                        del self.catalogs[row]
                        self._refresh_catalog_list()
                        self.list_catalogs.setCurrentRow(names.index(updated["name"]))
                    else:
                        self.catalogs[row] = updated
                        self._refresh_catalog_list()
                        self.list_catalogs.setCurrentRow(row)

    def _on_export_catalog(self):
        from qgis.PyQt.QtWidgets import QFileDialog
        row = self.list_catalogs.currentRow()
        if not (0 <= row < len(self.catalogs)):
            QMessageBox.warning(self, "Export", "Select a catalog to export.")
            return
        cat = self.catalogs[row]
        path, _ = QFileDialog.getSaveFileName(self, "Save catalog", f"{cat.get('name','catalog')}.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cat, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Export", "Catalog exported.")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Error saving: {e}")

    def _on_import_catalog(self):
        from qgis.PyQt.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Uvezi katalog", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cat = json.load(f)
            if not isinstance(cat, dict) or 'name' not in cat or 'colors' not in cat:
                raise ValueError('Nepoznat format JSON-a')
            names = [x.get('name','') for x in self.catalogs]
            if cat['name'] in names:
                self.catalogs[names.index(cat['name'])] = cat
            else:
                self.catalogs.append(cat)
            self._refresh_catalog_list()
            self.list_catalogs.setCurrentRow(max(0, len(self.catalogs)-1))
            QMessageBox.information(self, "Import", "Catalog imported.")
        except Exception as e:
            QMessageBox.critical(self, "Import", f"Error: {e}")

    def _on_delete_catalog(self):
        row = self.list_catalogs.currentRow()
        if 0 <= row < len(self.catalogs):
            del self.catalogs[row]
            self._refresh_catalog_list()
            self.list_colors.clear()

    def _on_save(self):
        self.data["catalogs"] = self.catalogs
        self.core._save_color_catalogs(self.data)
        QMessageBox.information(self, "Color Catalog", "Saved.")
        self.accept()

class NewColorCatalogDialog(QDialog):
    """Dijalog (slika 2): ime + sastavljanje rasporeda boja kroz + dugmad i strelice gore/dole.
    Ako se prosledi `initial`, koristi se za uređivanje postojećeg kataloga.
    """
    def __init__(self, core, parent=None, initial=None):
        super().__init__(parent or core.iface.mainWindow())
        from qgis.PyQt.QtWidgets import QListWidget, QListWidgetItem, QToolButton, QAbstractItemView, QDialogButtonBox
        self.core = core
        self._initial = initial
        self.setWindowTitle("Edit color scheme" if initial else "Create color scheme")
        self.resize(360, 520)

        v = QVBoxLayout(self)
        v.addWidget(QLabel("Color scheme name"))
        self.edit_name = QLineEdit()
        v.addWidget(self.edit_name)

        self.list = QListWidget()
        self.list.setSelectionMode(self.list.SingleSelection)
        v.addWidget(self.list)

        # Controls on side (+ for colors, - remove, up/down)
        row = QHBoxLayout()
        col_btns = QVBoxLayout()
        # Standard colors as vertical array of buttons with +
        std = self.core._default_color_sets()[0]["colors"]
        self._std = std
        for col in std:
            btn = QPushButton("+")
            btn.setStyleSheet("background:%s;" % col.get("hex","#cccccc"))
            btn.setToolTip(col.get("name",""))
            btn.clicked.connect(lambda _=False, c=col: self._add_color(c))
            btn.setFixedWidth(28)
            col_btns.addWidget(btn)
        col_btns.addStretch()

        # Right side minor controls
        right_controls = QVBoxLayout()
        self.btn_remove = QPushButton("-")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        for b in (self.btn_remove, self.btn_up, self.btn_down):
            b.setFixedWidth(28)
            right_controls.addWidget(b)
        right_controls.addStretch()

        row.addLayout(col_btns)
        row.addWidget(self.list)
        row.addLayout(right_controls)
        v.addLayout(row)

        # Bottom buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Save" if self._initial else "Create")
        btns.button(QDialogButtonBox.Cancel).setText("Cancel")
        v.addWidget(btns)

        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down.clicked.connect(self._move_down)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        # Prepopulate: ako uređujemo – koristi postojeće vrednosti, inače standardnih 12 boja
        if self._initial:
            self.edit_name.setText(self._initial.get('name',''))
            for c in self._initial.get('colors', []):
                self._add_color(c)
        else:
            for c in std:
                self._add_color(c)

    def _add_color(self, col):
        from qgis.PyQt.QtWidgets import QListWidgetItem
        it = QListWidgetItem(col.get("name",""))
        hx = col.get("hex","#cccccc")
        it.setBackground(QColor(hx))
        try:
            c = QColor(hx)
            if c.red()*0.299 + c.green()*0.587 + c.blue()*0.114 < 140:
                it.setForeground(QColor(255,255,255))
        except Exception:
            pass
        self.list.addItem(it)

    def _remove_selected(self):
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)

    def _move_up(self):
        row = self.list.currentRow()
        if row > 0:
            it = self.list.takeItem(row)
            self.list.insertItem(row-1, it)
            self.list.setCurrentRow(row-1)

    def _move_down(self):
        row = self.list.currentRow()
        if 0 <= row < self.list.count()-1:
            it = self.list.takeItem(row)
            self.list.insertItem(row+1, it)
            self.list.setCurrentRow(row+1)

    def result_catalog(self):
        # Returns dict {name, colors:[{name,hex},]}
        cols = []
        for i in range(self.list.count()):
            txt = self.list.item(i).text()
            # nađi HEX iz standardne tabele
            hex_val = next((c.get("hex") for c in self._std if c.get("name")==txt), "#cccccc")
            cols.append({"name": txt, "hex": hex_val})
        return {"name": self.edit_name.text().strip(), "colors": cols}



# === DIALOG: Izbor kapaciteta PE cevi ===
class PECevDialog(QDialog):
    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        from qgis.PyQt.QtWidgets import QDialogButtonBox, QListWidget, QVBoxLayout, QLabel
        self.setWindowTitle("Place PE duct")
        self.list = QListWidget(self)
        # Text options (only UI labels – values stay the same)
        self._options = [
            ("Design PE duct (1x1)", {"materijal": "PE", "kapacitet": "1x1", "fi": 40}),
            ("Install duct bank (1x2)", {"materijal": "PE", "kapacitet": "1x2", "fi": 40}),
            ("Install duct bank (2x1)", {"materijal": "PE", "kapacitet": "2x1", "fi": 40}),
            ("Install duct bank (2x2)", {"materijal": "PE", "kapacitet": "2x2", "fi": 40}),
            ("Install duct bank (1x3)", {"materijal": "PE", "kapacitet": "1x3", "fi": 40}),
            ("Install duct bank (2x3)", {"materijal": "PE", "kapacitet": "2x3", "fi": 40}),
            ("Install duct bank (3x3)", {"materijal": "PE", "kapacitet": "3x3", "fi": 40}),
        ]
        for label, _ in self._options:
            self.list.addItem(label)
        self.list.setCurrentRow(0)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Choose PE duct capacity:"))
        lay.addWidget(self.list); lay.addWidget(btns)


    def values(self):
        idx = self.list.currentRow()
        if idx < 0: idx = 0
        # Uvek vrati kopiju dict-a
        v = dict(self._options[idx][1])
        return v

# === DIALOG: Izbor kapaciteta prelazne cevi (PVC/PE/Oki/FeZn) ===
class PrelaznaCevDialog(QDialog):
    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        from qgis.PyQt.QtWidgets import QDialogButtonBox, QListWidget, QVBoxLayout, QLabel
        self.setWindowTitle("Place transition duct")
        self.list = QListWidget(self)
        self._options = [
            ("Transition with PVC ducts 1x1 (Ø110)", {"materijal": "PVC", "kapacitet": "1x1", "fi": 110}),
            ("Transition with PVC ducts 1x2 (Ø110)", {"materijal": "PVC", "kapacitet": "1x2", "fi": 110}),
            ("Transition with PE ducts 1x1 (Ø110)", {"materijal": "PE", "kapacitet": "1x1", "fi": 110}),
            ("Transition with PE ducts 1x2 (Ø110)", {"materijal": "PE", "kapacitet": "1x2", "fi": 110}),
            ("Transition with Oki ducts 1x1 (Ø110)", {"materijal": "Oki", "kapacitet": "1x1", "fi": 110}),
            ("Transition with Oki ducts 1x2 (Ø110)", {"materijal": "Oki", "kapacitet": "1x2", "fi": 110}),
            ("Transition with FeZn ducts 1x1 (Ø110)", {"materijal": "FeZn", "kapacitet": "1x1", "fi": 110}),
            ("Transition with FeZn ducts 1x2 (Ø110)", {"materijal": "FeZn", "kapacitet": "1x2", "fi": 110}),
        ]
        for label, _ in self._options:
            self.list.addItem(label)
        self.list.setCurrentRow(0)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Choose transition duct capacity/material:"))
        lay.addWidget(self.list)
        lay.addWidget(btns)


    def values(self):
        idx = self.list.currentRow()
        if idx < 0: idx = 0
        return dict(self._options[idx][1])

# === MAP TOOL: polaganje cevi po trasi (klik start + kraj sa 'snap on') ===
class PipePlaceTool(QgsMapTool):
    def __init__(self, iface, plugin, target_kind, attrs):
        """
        target_kind: 'PE' ili 'PRELAZ'
        attrs: dict sa ključevima materijal, kapacitet, fi
        """
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()
        self.kind = target_kind
        self.attrs = attrs or {}
        self.points = []

        # privremena linija
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.rb.setLineStyle(Qt.SolidLine)
        self.rb.show()
        self.rb.setWidth(1.5)
        self.rb.setColor(QColor(0, 255, 0, 180))

        # snaп indikator – mnogo vidljiviji od rubber banda
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setIconType(QgsVertexMarker.ICON_CROSS)
        self.snap_marker.setPenWidth(3)
        self.snap_marker.setIconSize(14)
        self.snap_marker.setColor(QColor(0, 200, 0))
        self.snap_marker.hide()
    def _event_map_point(self, event):
        """Return QgsPointXY from a map mouse event in a version-safe way."""
        try:
            # QGIS 3.22+
            mp = event.mapPoint()
            return QgsPointXY(mp)
        except Exception:
            try:
                return self.toMapCoordinates(event.pos())
            except Exception:
                return QgsPointXY(0, 0)

    def _snap_via_utils(self, qpt):
        """Try snapping using canvas snapping utils; fallback to manual snap."""
        try:
            su = self.canvas.snappingUtils()
            if su is not None:
                match = su.snapToMap(qpt)
                # match may be QgsPointLocator.Match
                try:
                    if match.isValid():
                        try:
                            pt = match.point()
                        except Exception:
                            pt = match.point()
                        return QgsPointXY(pt)
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def _snap_point(self, qpt):
        point = QgsPointXY(qpt)
        snap_point = None; min_dist = None
        # 1) čvorovi (OKNA)
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() in ("Stubovi", "Poles", "OKNA", "Manholes"):
                    for f in lyr.getFeatures():
                        p = f.geometry().asPoint()
                        d = QgsPointXY(point).distance(QgsPointXY(p))
                        if min_dist is None or d < min_dist:
                            min_dist = d; snap_point = QgsPointXY(p)
            except Exception:
                pass
        # 2) verteksi & sredine segmenata trase
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                    for g in lyr.getFeatures():
                        line = g.geometry().asPolyline()
                        if not line:
                            multi = g.geometry().asMultiPolyline()
                            if multi:
                                for ln in multi:
                                    for p in ln:
                                        d = QgsPointXY(point).distance(QgsPointXY(p))
                                        if min_dist is None or d < min_dist:
                                            min_dist = d; snap_point = QgsPointXY(p)
                                    for i in range(len(ln)-1):
                                        mid = QgsPointXY((ln[i].x()+ln[i+1].x())/2, (ln[i].y()+ln[i+1].y())/2)
                                        d = QgsPointXY(point).distance(mid)
                                        if min_dist is None or d < min_dist:
                                            min_dist = d; snap_point = mid
                        else:
                            for p in line:
                                d = QgsPointXY(point).distance(QgsPointXY(p))
                                if min_dist is None or d < min_dist:
                                    min_dist = d; snap_point = QgsPointXY(p)
                            for i in range(len(line)-1):
                                mid = QgsPointXY((line[i].x()+line[i+1].x())/2, (line[i].y()+line[i+1].y())/2)
                                d = QgsPointXY(point).distance(mid)
                                if min_dist is None or d < min_dist:
                                    min_dist = d; snap_point = mid
            except Exception:
                pass
        tol = self.canvas.mapUnitsPerPixel() * 20
        if snap_point is not None and min_dist is not None and min_dist < tol:
            return snap_point
        return point

    def canvasPressEvent(self, event):
        pass

    def canvasReleaseEvent(self, event):

        if event.button() != Qt.LeftButton:
            # Right click finishes if at least 2 points
            if event.button() == Qt.RightButton and len(self.points) >= 2:
                self._finish()
            return
        p0 = self._event_map_point(event)
        sp = self._snap_via_utils(p0)
        p = sp if sp is not None else self._snap_point(p0)
        self.points.append(QgsPointXY(p))
        # update preview
        try:
            self.snap_marker.setCenter(QgsPointXY(p))
            self.snap_marker.show()
            self.rb.setToGeometry(QgsGeometry.fromPolylineXY(self.points), None)
            self.rb.show()
        except Exception:
            pass
        # if we have two clicks, finish
        if len(self.points) >= 2:
            self._finish()

    def canvasMoveEvent(self, event):

        p0 = self._event_map_point(event)
        sp = self._snap_via_utils(p0)
        p = sp if sp is not None else self._snap_point(p0)
        # show marker and preview
        try:
            self.snap_marker.setCenter(QgsPointXY(p))
            self.snap_marker.show()
        except Exception:
            pass
        if self.points:
            pts = list(self.points) + [p]
        else:
            pts = [p]
        try:
            self.rb.setToGeometry(QgsGeometry.fromPolylineXY(pts), None)
            self.rb.show()
        except Exception:
            pass

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cleanup(cancel=True)

    
    def _finish(self):
        # Get layer 'Trasa' if exists – not mandatory
        trasa_layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if lyr.name() in ('Route',) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                    trasa_layer = lyr
                    break
            except Exception:
                pass

        p1, p2 = self.points[0], self.points[1]
        # Geometry along same route (if exists), otherwise direct line
        geom = None
        if trasa_layer is not None and trasa_layer.featureCount() > 0:
            try:
                # try to build path by joining segments of multiple features (virtual merge)
                tol_units = self.canvas.mapUnitsPerPixel() * 6
                path_pts = self.plugin._build_path_across_network(trasa_layer, p1, p2, tol_units)
                if not path_pts:
                    path_pts = self.plugin._build_path_across_joined_trasa(trasa_layer, p1, p2, tol_units)
                if path_pts:
                    geom = QgsGeometry.fromPolylineXY(path_pts)
            except Exception:
                pass
        if geom is None:
            geom = QgsGeometry.fromPolylineXY([p1, p2])
        # Determine target layer and style
        if self.kind == 'PE':
            layer = self.plugin._ensure_pe_cev_layer()
            color_hex = "#FF9900"  # orange
            width_mm = 1.0
        else:
            layer = self.plugin._ensure_prelazna_cev_layer()
            color_hex = "#D0FF00"  # yellow
            width_mm = 2.2

        # Create feature
        f = QgsFeature(layer.fields())
        f.setGeometry(geom)
        f['materijal'] = self.attrs.get('materijal')
        f['kapacitet'] = self.attrs.get('kapacitet')
        try:
            f['fi'] = int(self.attrs.get('fi')) if self.attrs.get('fi') is not None else None
        except Exception:
            f['fi'] = None

        # Izračunaj dužinu geometrije u metrima
        try:
            d = QgsDistanceArea()
            try:
                d.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
            except Exception:
                try:
                    d.setSourceCrs(self.iface.mapCanvas().mapSettings().destinationCrs(),
                                   QgsProject.instance().transformContext())
                except Exception:
                    pass
            d.setEllipsoid(QgsProject.instance().ellipsoid())
            length_m = d.measureLength(geom) if geom is not None else None
            if length_m is None:
                length_m = 0.0
            f['duzina_m'] = float(length_m)
        except Exception:
            try:
                f['duzina_m'] = float(geom.length()) if geom is not None else None
            except Exception:
                f['duzina_m'] = None

        # 'od'/'do' pokušaj da nađeš najbliža imena (OKNA broj_okna) kao za kabl
        def _disp_name(layer, feat):
            try:
                if layer.name() == 'OKNA':
                    if 'broj_okna' in layer.fields().names():
                        broj = feat['broj_okna']
                        if broj is not None and str(broj).strip():
                            return f"KO {str(broj).strip()}"
                idx = layer.fields().indexFromName('naziv')
                if idx != -1:
                    val = feat['naziv']
                    if val is not None and str(val).strip():
                        return str(val).strip()
                if layer.name() == 'Poles':
                    tip = str(feat['tip']) if 'tip' in layer.fields().names() and feat['tip'] is not None else ''
                    return ("Stub " + tip).strip() or f"Stub {int(feat.id())}"
            except Exception:
                pass
            return f"{layer.name()}:{int(feat.id())}"

        # nađi najbliže tačke u OKNA/Stubovi oko p1 i p2
        od_naziv = None; do_naziv = None
        node_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() in ("Stubovi", "Poles", "OKNA", "Manholes"):

                    node_layers.append(lyr)
            except Exception:
                pass
        def _nearest_name(pt):
            best=None; bdist=None; bl=None; bf=None
            for nl in node_layers:
                for ft in nl.getFeatures():
                    d=QgsPointXY(pt).distance(QgsPointXY(ft.geometry().asPoint()))
                    if bdist is None or d<bdist:
                        bdist=d; bl=nl; bf=ft
            return _disp_name(bl,bf) if bl and bf else None
        od_naziv=_nearest_name(p1); do_naziv=_nearest_name(p2)
        if 'od' in layer.fields().names(): f['od']=od_naziv
        if 'do' in layer.fields().names(): f['do']=do_naziv

        layer.startEditing()
        # Ensure field 'duzina_m' exists if not present
        try:
            if 'duzina_m' not in layer.fields().names():
                layer.addAttribute(QgsField('duzina_m', QVariant.Double))
                layer.updateFields()
        except Exception:
            pass
        
        layer.addFeature(f)
        layer.commitChanges()
        layer.updateExtents()
        try:
            self.plugin._apply_pipe_style(layer, color_hex, width_mm)
        except Exception:
            pass
        self._cleanup(stay_active=True)

    def _cleanup(self, cancel=False, stay_active=False):
        # skloni marker i preview liniju
        try:
            if getattr(self, "snap_marker", None) is not None:
                try:
                    # potpuno ukloni marker sa scene – da ne ostaju zeleni krstići
                    self.canvas.scene().removeItem(self.snap_marker)
                except Exception:
                    try:
                        self.snap_marker.hide()
                    except Exception:
                        pass
                self.snap_marker = None

            if getattr(self, "rb", None) is not None:
                try:
                    self.rb.reset(QgsWkbTypes.LineGeometry)
                    self.rb.hide()
                except Exception:
                    pass
        except Exception:
            pass

        self.points = []

        # If we want tool to stay active (repeat), don't touch map tool
        if not stay_active:
            try:
                self.iface.mapCanvas().unsetMapTool(self)
            except Exception:
                pass

        if not cancel:
            self.iface.messageBar().pushInfo("Pipes", "Pipe has been laid.")

    def deactivate(self):
        """QGIS poziva ovo kada se prebaciš na drugi alat."""
        try:
            # počisti sve, ali bez poruke i bez dodatnog unsetMapTool
            self._cleanup(cancel=True, stay_active=True)
        except Exception:
            pass
        try:
            super().deactivate()
        except Exception:
            pass






# === AUTO-ADDED: Save all layers to GeoPackage ===

    
def activate_infrastructure_cut_tool(self):
    """Aktivira alat za sečenje infrastrukture."""
    try:
        from .addons.infrastructure_cut import InfrastructureCutTool
        self._infra_cut_tool = InfrastructureCutTool(self.iface, self)
        try:
            # Link action so QGIS može da "čekira" dugme dok je alat aktivan
            self._infra_cut_tool.setAction(self.action_infra_cut)
        except Exception:
            pass
        self.iface.mapCanvas().setMapTool(self._infra_cut_tool)
        try:
            self.iface.messageBar().pushInfo("Cutiing", "Tool activated. Move mouse over line (red cross), left click to cut, right/ESC exit.")
        except Exception:
            pass
    except Exception as e:
        try:
            QMessageBox.critical(self.iface.mainWindow(), "Infrastructure cutting", f"Error: {e}")
        except Exception:
            pass



def _open_fiberq_web(iface):
    """
    Umesto otvaranja web browsera, sada otvara FiberQ preglednu mapu
    kao QDialog sa QgsMapCanvas-om i slojevima iz PostGIS baze.
    Parametri konekcije se čitaju iz [postgis] sekcije u config.ini.
    """
    try:
        if not _fiberq_check_pro(iface):
            return
        from .addons import fiberq_preview
        fiberq_preview.open_preview_dialog(iface)
    except Exception as e:
        try:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(
                iface.mainWindow(),
                "FiberQ – pregledna mapa",
                f"Greška pri otvaranju pregledne mape:\n{e}"
            )
        except Exception:
            # if even QMessageBox doesn't work, just ignore
            pass



def _telecom_save_all_layers_to_gpkg(iface):
    """
    Export all vector layers (including Temporary scratch) to a single GeoPackage
    and repoint the layers in the project to the GPKG source.
    """
    try:
        from qgis.core import (
            QgsProject, QgsVectorLayer, QgsVectorFileWriter, QgsCoordinateTransformContext
        )
        from qgis.PyQt.QtWidgets import QFileDialog
        import os, re

        prj = QgsProject.instance()

        default_dir = os.path.dirname(prj.fileName()) if prj.fileName() else os.path.expanduser("~")
        gpkg_path, _ = QFileDialog.getSaveFileName(
            iface.mainWindow(),
            "Izaberi GeoPackage fajl",
            os.path.join(default_dir, "Telecom.gpkg"),
            "GeoPackage (*.gpkg)"
        )
        if not gpkg_path:
            return
        if not gpkg_path.lower().endswith(".gpkg"):
            gpkg_path += ".gpkg"

        # zapamti putanju u projektu
        try:
            prj.writeEntry("TelecomPlugin", "gpkg_path", gpkg_path)
        except Exception:
            pass

        layers = [l for l in prj.mapLayers().values() if isinstance(l, QgsVectorLayer)]
        if not layers:
            iface.messageBar().pushWarning("GPKG export", "Nema vektorskih lejera za snimanje.")
            return

        # Commit edits
        for lyr in layers:
            try:
                if lyr.isEditable():
                    lyr.commitChanges()
            except Exception:
                pass

        used = set()
        errors = []

        for idx, lyr in enumerate(layers):
            base = re.sub(r"[^A-Za-z0-9_]+", "_", lyr.name()).strip("_") or f"layer_{idx+1}"
            name = base
            c = 1
            while name in used:
                c += 1
                name = f"{base}_{c}"
            used.add(name)

            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName = name
            opts.actionOnExistingFile = (
                QgsVectorFileWriter.CreateOrOverwriteLayer
                if os.path.exists(gpkg_path)
                else QgsVectorFileWriter.CreateOrOverwriteFile
            )

            result = QgsVectorFileWriter.writeAsVectorFormatV3(
                lyr, gpkg_path, QgsCoordinateTransformContext(), opts
            )
            if isinstance(result, tuple):
                err_code = result[0]
                err_msg = result[1] if len(result) > 1 else ""
            else:
                err_code = result
                err_msg = ""

            if err_code != QgsVectorFileWriter.NoError:
                errors.append(f"{lyr.name()}: {err_msg}")
                continue

            uri = f"{gpkg_path}|layername={name}"
            try:
                lyr.setDataSource(uri, lyr.name(), "ogr")
                try:
                    lyr.saveStyleToDatabase("default", "auto-saved by Telecom plugin", True, "")
                except Exception:
                    pass
            except Exception:
                # Fallback: add new layer
                new_lyr = QgsVectorLayer(uri, lyr.name(), "ogr")
                if new_lyr and new_lyr.isValid():
                    parent = prj.layerTreeRoot().findLayer(lyr.id()).parent()
                    prj.removeMapLayer(lyr.id())
                    prj.addMapLayer(new_lyr, False)
                    parent.insertLayer(0, new_lyr)
                    try:
                        new_lyr.saveStyleToDatabase("default", "auto-saved by Telecom plugin", True, "")
                    except Exception:
                        pass
                else:
                    errors.append(f"{lyr.name()}: i can't load new layer from GPKG ({uri})")

        prj.setDirty(True)
        if errors:
            iface.messageBar().pushWarning("GPKG export", "Completed with errors:\n" + "\n".join(errors))
        else:
            iface.messageBar().pushSuccess("GPKG export", f"All layers are recorded in:\n{gpkg_path}")
    except Exception as e:
        try:
            iface.messageBar().pushCritical("GPKG export", f"Unexpected error: {e}")
        except Exception:
            pass

# === AUTO-ADDED: helper to export one layer to GPKG and redirect ===

def _telecom_export_one_layer_to_gpkg(lyr, gpkg_path, iface):
    """
    Export a single vector layer to the GeoPackage and repoint it in the project.
    Returns True/False.
    """
    from qgis.core import QgsVectorFileWriter, QgsCoordinateTransformContext, QgsVectorLayer, QgsProject
    import os, re

    base = re.sub(r"[^A-Za-z0-9_]+", "_", lyr.name()).strip("_") or "layer"
    name = base

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = name
    opts.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteLayer
        if os.path.exists(gpkg_path)
        else QgsVectorFileWriter.CreateOrOverwriteFile
    )

    try:
        if lyr.isEditable():
            lyr.commitChanges()
    except Exception:
        pass

    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        lyr, gpkg_path, QgsCoordinateTransformContext(), opts
    )
    if isinstance(result, tuple):
        err_code = result[0]
        err_msg = result[1] if len(result) > 1 else ""
    else:
        err_code = result
        err_msg = ""

    if err_code != QgsVectorFileWriter.NoError:
        try:
            iface.messageBar().pushWarning("GPKG export", f"{lyr.name()}: {err_msg}")
        except Exception:
            pass
        return False

    uri = f"{gpkg_path}|layername={name}"
    try:
        lyr.setDataSource(uri, lyr.name(), "ogr")
        try:
            lyr.saveStyleToDatabase("default", "auto-saved by Telecom plugin", True, "")
        except Exception:
            pass
        return True
    except Exception:
        new_lyr = QgsVectorLayer(uri, lyr.name(), "ogr")
        if new_lyr and new_lyr.isValid():
            prj = QgsProject.instance()
            parent = prj.layerTreeRoot().findLayer(lyr.id()).parent()
            prj.removeMapLayer(lyr.id())
            prj.addMapLayer(new_lyr, False)
            parent.insertLayer(0, new_lyr)
            try:
                new_lyr.saveStyleToDatabase("default", "auto-saved by Telecom plugin", True, "")
            except Exception:
                pass
            return True
        else:
            try:
                iface.messageBar().pushWarning("GPKG export", f"{lyr.name()}: ne mogu da učitam novi sloj iz GPKG ({uri})")
            except Exception:
                pass
            return False


# === UI grupa: Rezerve (drop-down dugme) ===
    def activate(self):
        try:
            self.canvas.setCursor(Qt.CrossCursor)
        except Exception:
            pass
        try:
            self.rb.show()
        except Exception:
            pass
        try:
            self.snap_marker.show()
        except Exception:
            pass
        super().activate()

    def deactivate(self):
        try:
            self.snap_marker.hide()
        except Exception:
            pass
        try:
            self.rb.hide()
        except Exception:
            pass
        super().deactivate()

class ReservesUI:
    def __init__(self, core):
        from qgis.PyQt.QtWidgets import QMenu, QToolButton
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Interaktivno: Završna
        act_zav = QAction(_load_icon('ic_slack_midspan.svg'), 'Place terminal slack (interactive)', core.iface.mainWindow())
        act_zav.triggered.connect(lambda: core._start_reserve_interactive("Terminal"))
        core.actions.append(act_zav); self.menu.addAction(act_zav)

        # Interaktivno: Prolazna
        act_prol = QAction(_load_icon('ic_slack_midspan.svg'), 'Place mid span slack (interactive)', core.iface.mainWindow())
        act_prol.triggered.connect(lambda: core._start_reserve_interactive("Mid span"))
        core.actions.append(act_prol); self.menu.addAction(act_prol)

        # Batch: završne na krajevima selektovanih
        act_batch = QAction(_load_icon('ic_slack_batch.svg'), 'Generate terminal slacks at the ends of selected cables', core.iface.mainWindow())
        act_batch.triggered.connect(core.generate_terminal_reserves_for_selected)
        core.actions.append(act_batch); self.menu.addAction(act_batch)

        btn = QToolButton()
        btn.setText('')
        try: btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        except Exception: pass
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setMenu(self.menu)
        btn.setIcon(_load_icon('ic_slack_midspan.svg'))
        btn.setToolTip('Optical slacks')
        btn.setStatusTip('Optical slacks')
        core.toolbar.addWidget(btn)

# === Dijalog za unos parametara rezerve ===
class RezervaDialog(QDialog):
    def __init__(self, parent=None, default_tip="Terminal"):
        super().__init__(parent)
        from qgis.PyQt.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QDialogButtonBox
        self.setWindowTitle("Optical slack")

        self.cmb_tip = QComboBox()
        self.cmb_tip.addItems(["Terminal", "Mid span"])
        if default_tip in ("Terminal", "Mid span"):
            self.cmb_tip.setCurrentText(default_tip)

        self.spn_duz = QSpinBox()
        self.spn_duz.setRange(1, 200)
        self.spn_duz.setValue(20)   
        # Display in English, internally Serbian codes
        self.cmb_lok = QComboBox()
        self.cmb_lok.addItem("Auto", "Auto")          # auto detection
        self.cmb_lok.addItem("Pole", "Stub")         # pole
        self.cmb_lok.addItem("Manhole", "OKNO")      # manhole
        self.cmb_lok.addItem("Object", "Objekat")    # object
        lay = QVBoxLayout(self)
        row1 = QHBoxLayout(); row1.addWidget(QLabel("Type:"));      row1.addWidget(self.cmb_tip)
        row2 = QHBoxLayout(); row2.addWidget(QLabel("Length [m]:")); row2.addWidget(self.spn_duz)
        row3 = QHBoxLayout(); row3.addWidget(QLabel("Location:"));  row3.addWidget(self.cmb_lok)
        lay.addLayout(row1); lay.addLayout(row2); lay.addLayout(row3)

        
        btns = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); lay.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

    def values(self):
        return {
            "tip": self.cmb_tip.currentText(),
            "duzina_m": int(self.spn_duz.value()),
            # koristimo interne kodove iz userData
            "lokacija": self.cmb_lok.currentData() or self.cmb_lok.currentText(),
        }


# === Map alat za polaganje rezerve ===
class ReservePlaceTool(QgsMapTool):
    def __init__(self, iface, plugin, params):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()
        self.params = dict(params or {})
        self.snap_marker = QgsVertexMarker(self.canvas)
        self.snap_marker.setIconType(QgsVertexMarker.ICON_CROSS)
        self.snap_marker.setPenWidth(3)
        self.snap_marker.setIconSize(14)
        self.snap_marker.setColor(QColor(0, 200, 0))
        self.snap_marker.hide()

    def activate(self):
        try:
            self.snap_marker.show()
        except Exception:
            pass

    def deactivate(self):
        try:
            self.snap_marker.hide()
        except Exception:
            pass

    def _iter_kabl_layers(self):
        from qgis.core import QgsVectorLayer, QgsWkbTypes, QgsProject
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.LineGeometry
                    and lyr.name() in (
                        "Kablovi_podzemni", "Kablovi_vazdusni",
                        "Underground cables", "Aerial cables"
                    )
                ):
                    yield lyr
            except Exception:
                pass


    def _iter_node_layers(self):
        from qgis.core import QgsVectorLayer, QgsWkbTypes, QgsProject
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() in ("Stubovi", "Poles", "OKNA", "Manholes"):
                    yield lyr
            except Exception:
                pass

    def _nearest_node(self, pt):
        from qgis.core import QgsPointXY
        best = (None, None, None)
        for nl in self._iter_node_layers():
            for f in nl.getFeatures():
                p = f.geometry().asPoint()
                d = QgsPointXY(p).distance(pt)
                if best[2] is None or d < best[2]:
                    best = (nl, f, d)
        return best

    def _nearest_kabl_endpoint(self, pt, tol):
        from qgis.core import QgsGeometry, QgsPointXY
        best = (None, None, None, None, None)  # (layer, feat, which, end_pt, dist)
        for kl in self._iter_kabl_layers():
            for f in kl.getFeatures():
                geom = f.geometry()
                line = geom.asPolyline()
                if not line:
                    parts = geom.asMultiPolyline()
                    if parts: line = parts[0]
                if not line:
                    continue
                ends = [QgsPointXY(line[0]), QgsPointXY(line[-1])]
                labels = ["od","do"]
                for lbl, ep in zip(labels, ends):
                    d = QgsPointXY(ep).distance(pt)
                    if (best[4] is None or d < best[4]) and d <= tol:
                        best = (kl, f, lbl, ep, d)
        return best

    def _nearest_kabl_on_line(self, pt, tol):
        from qgis.core import QgsGeometry
        best = (None, None, None)  # (layer, feat, dist)
        for kl in self._iter_kabl_layers():
            for f in kl.getFeatures():
                d = f.geometry().distance(QgsGeometry.fromPointXY(pt))
                if d <= tol and (best[2] is None or d < best[2]):
                    best = (kl, f, d)
        return best

    def canvasMoveEvent(self, e):
        p = self.toMapCoordinates(e.pos())
        self.snap_marker.setCenter(p)
        self.snap_marker.show()

    def canvasReleaseEvent(self, e):
        from qgis.core import QgsGeometry, QgsPointXY, QgsFeature
        p = self.toMapCoordinates(e.pos())
        tol = self.canvas.mapUnitsPerPixel() * 20

        (kl, kf, strana, ep, dd) = self._nearest_kabl_endpoint(p, tol)
        kabl_layer_id = None; kabl_fid = None; strana_val = None; place_pt = p
        if kl and kf:
            kabl_layer_id = kl.id(); kabl_fid = int(kf.id()); strana_val = strana; place_pt = ep
        else:
            (kl2, kf2, d2) = self._nearest_kabl_on_line(p, tol)
            if kl2 and kf2:
                kabl_layer_id = kl2.id(); kabl_fid = int(kf2.id()); strana_val = "sredina"; place_pt = p

        if kabl_layer_id is None:
            QMessageBox.information(self.iface.mainWindow(), "Optical slacks", "No cable found nearby.")
            return

        (nl, nf, nd) = self._nearest_node(place_pt)
        lok = self.params.get("lokacija", "Auto")
        if lok == "Auto":
            if nl and nf:
                lok = "Stub" if nl.name() in ("Poles",) else "OKNO"

            else:
                lok = "Objekat"

        vl = self.plugin._ensure_reserves_layer()
        f = QgsFeature(vl.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(place_pt)))
        f["tip"] = self.params.get("tip","Terminal")
        f["duzina_m"] = int(self.params.get("duzina_m", 20))
        f["lokacija"] = lok
        f["kabl_layer_id"] = kabl_layer_id
        f["kabl_fid"] = kabl_fid
        f["strana"] = strana_val or "sredina"
        vl.startEditing(); vl.addFeature(f); vl.commitChanges(); vl.triggerRepaint()

        # Auto-pračun slack-a za dati kabl
        try:
            self.plugin._recompute_slack_for_cable(kabl_layer_id, kabl_fid)
        except Exception:
            pass

        try:
            self.iface.messageBar().pushInfo("Optical slacks", "Slack saved.")
        except Exception:
            pass
        # ostani u alatu za ponavljanje; izlaz na ESC / desni klik

    def keyPressEvent(self, event):
        """ESC prekida alat za polaganje optičke rezerve."""
        if event.key() == Qt.Key_Escape:
            try:
                self.snap_marker.hide()
            except Exception:
                pass
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass

    def canvasPressEvent(self, event):
        """Desni klik prekida alat bez dodavanja nove rezerve."""
        if event.button() == Qt.RightButton:
            try:
                self.snap_marker.hide()
            except Exception:
                pass
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass

    def _ensure_global_shortcuts(self):
        """
        (DISABLED) Global keyboard shortcuts.

        Ostavljamo funkciju kao stub samo da ne puca poziv iz initGui,
        ali realne prečice više ne registrujemo – da ne ulazimo u konflikte
        sa QGIS globalnim shortcut-ovima.
        """
        return

        
        if not hasattr(self, '_global_shortcuts'):
            self._global_shortcuts = []
        win = self.iface.mainWindow()
        # helper
        def add_shortcut(seq, slot):
            try:
                sc = QShortcut(QKeySequence(seq), win)
                sc.setContext(Qt.ApplicationShortcut)
                sc.activated.connect(slot)
                self._global_shortcuts.append(sc)
            except Exception:
                pass
               # Mapiranja – ka ACTION.trigger, isto kao da si kliknuo dugme
        if hasattr(self, 'action_branch'):
            add_shortcut('Ctrl+G', self.action_branch.trigger)
        elif hasattr(self, 'separate_cables_offset'):
            add_shortcut('Ctrl+G', self.separate_cables_offset)

        if hasattr(self, 'action_bom'):
            add_shortcut('Ctrl+B', self.action_bom.trigger)
        elif hasattr(self, 'open_bom_dialog'):
            add_shortcut('Ctrl+B', self.open_bom_dialog)

        if hasattr(self, 'action_fiber_break'):
            add_shortcut('Ctrl+F', self.action_fiber_break.trigger)
        elif hasattr(self, 'activate_fiber_break_tool'):
            add_shortcut('Ctrl+F', self.activate_fiber_break_tool)

        pub_action = getattr(self, 'action_publish', None)
        if pub_action is not None:
            add_shortcut('Ctrl+P', pub_action.trigger)
        else:
            pub_slot = getattr(self, 'open_publish_dialog', None) or getattr(self, 'publish_to_postgis', None)
            if callable(pub_slot):
                add_shortcut('Ctrl+P', pub_slot)

        # Rezerva 'R'
        rez_slot = None
        try:
            rez_slot = lambda: self._start_reserve_interactive('Terminal')
        except Exception:
            rez_slot = None
        if rez_slot:
            add_shortcut('R', rez_slot)




# === AUTO PATCH (safe): hotkeys + reserve hook + safe unload ===
try:
    # ensure __init__ stores iface and basics (if missing)
    _cls = globals().get('FiberQPlugin')
    if _cls is not None and (not hasattr(_cls, '__init__') or _cls.__init__ is object.__init__):
        def __init__(self, iface):
            self.iface = iface
            self.actions = []
            self.toolbar = None
            self._hk_shortcuts = []
        try:
            setattr(_cls, '__init__', __init__)
        except Exception:
            pass
    # wrap initGui to add hotkeys & health-check & reserve hook
    _orig_initGui = getattr(globals().get('FiberQPlugin'), 'initGui', None)
    if callable(_orig_initGui):
        def _patched_initGui(self, *a, **kw):
            _orig_initGui(self, *a, **kw)
            try:
                from .addons.hotkeys import register_hotkeys
                if not hasattr(self, '_hk_shortcuts'):
                    self._hk_shortcuts = []
                register_hotkeys(self)
            except Exception:
                pass
            # add Health-check action (menu+toolbar)
            try:
                from qgis.PyQt.QtWidgets import QAction
                def _health_check():
                    from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
                    from qgis.PyQt.QtWidgets import QMessageBox

                    msgs = []

                    project = QgsProject.instance()
                    layers = {
                        lyr.name(): lyr
                        for lyr in project.mapLayers().values()
                        if isinstance(lyr, QgsVectorLayer)
                    }

                        # Ključni lejeri – prihvati i srpska i engleska imena
                    trasa_layer = layers.get("Route")
                    stubovi_layer = layers.get("Poles")
                    okna_layer = layers.get("Manholes") or layers.get("OKNA")

                    # Trasa – line
                    if trasa_layer and trasa_layer.geometryType() == QgsWkbTypes.LineGeometry:
                        msgs.append("Routes: OK")
                    else:
                        msgs.append("Routes: MISSING or wrong type")

                    # Stubovi – point
                    if stubovi_layer and stubovi_layer.geometryType() == QgsWkbTypes.PointGeometry:
                        msgs.append("Poles: OK")
                    else:
                        msgs.append("Poles: MISSING or wrong type")

                    # OKNA – opciono
                    if okna_layer:
                        msgs.append("Manholes: OK")
                    else:
                        msgs.append("Manholes: MISSING")

                    # 1) Kratak rezime u message baru
                    try:
                        self.iface.messageBar().pushInfo("Health check", " | ".join(msgs))
                    except Exception:
                        pass

                    # 2) Detailed route check (Route correction logic)
                    try:
                        if hasattr(self, "check_consistency"):
                            self.check_consistency()
                    except Exception as e:
                        try:
                            QMessageBox.warning(
                                self.iface.mainWindow(),
                                "Health check",
                                f"Error while running detailed route check:\n{e}",
                            )
                        except Exception:
                            pass

                self.action_health_check = QAction('Check (health check)', self.iface.mainWindow())
                self.action_health_check.setIcon(_load_icon('ic_health.svg'))
                self.action_health_check.triggered.connect(_health_check)
                self.actions.append(self.action_health_check)
                try: self.toolbar.addAction(self.action_health_check)
                except Exception: pass
                try: self.iface.addPluginToMenu('FiberQ', self.action_health_check)
                except Exception: pass
            except Exception:
                pass
            
            # reserve hook
            try:
                from .addons.reserve_hook import ReserveHook
                self._reserve_hook = ReserveHook(self.iface)
                self._reserve_hook.ensure_connected()
            except Exception:
                pass
        _cls = globals().get('FiberQPlugin')
        if _cls is not None:
            _cls.initGui = _patched_initGui

    # wrap unload to cleanup hotkeys
    _orig_unload = getattr(globals().get('FiberQPlugin'), 'unload', None)
    if callable(_orig_unload):
        def _patched_unload(self, *a, **kw):
            try:
                for sc in getattr(self, '_hk_shortcuts', []):
                    try:
                        sc.activated.disconnect()
                        sc.setParent(None); sc.deleteLater()
                    except Exception: pass
                self._hk_shortcuts = []
            except Exception:
                pass
            return _orig_unload(self, *a, **kw)
        _cls = globals().get('FiberQPlugin')
        if _cls is not None:
            _cls.unload = _patched_unload
except Exception:
    pass


# === Publish to PostGIS integration (method binder) ===
def _stubovi_open_publish_dialog(self):
    try:
        try:
            if hasattr(self, "check_pro") and not self.check_pro():
                return
        except Exception:
            if not _fiberq_check_pro(self.iface):
                return
        from .addons.publish_pg import open_publish_dialog as _open
        _open(self.iface)
    except Exception as e:
        try:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(self.iface.mainWindow(), "Publish to PostGIS", f"Greška: {e}")
        except Exception:
            pass

try:
    if 'FiberQPlugin' in globals() and hasattr(StuboviPlugin, '__dict__'):
        (_tmp_cls := globals().get('FiberQPlugin')) and (_tmp_cls and setattr(_tmp_cls, 'open_publish_dialog', _stubovi_open_publish_dialog))
except Exception:
    pass



# === AUTO PATCH: Publish to PostGIS (Append/Upsert/Analyze) ===
try:
    # Bind method if missing
    if not hasattr(StuboviPlugin, 'open_publish_dialog'):
        def open_publish_dialog(self):
            try:
                try:
                    if hasattr(self, "check_pro") and not self.check_pro():
                        return
                except Exception:
                    if not _fiberq_check_pro(self.iface):
                        return
                from .addons.publish_pg import open_publish_dialog as _open
                _open(self.iface)
            except Exception as e:
                from qgis.PyQt.QtWidgets import QMessageBox
                try:
                    QMessageBox.critical(self.iface.mainWindow(), 'Publish to PostGIS', f'Greška: {e}')
                except Exception:
                    pass
        (_tmp_cls := globals().get('FiberQPlugin')) and (_tmp_cls and setattr(_tmp_cls, 'open_publish_dialog', open_publish_dialog))

    # Wrap initGui to ensure toolbar/menu action is added
    _orig_initGui_pg = getattr(globals().get('FiberQPlugin'), 'initGui', None)
    def _pg_initGui_wrapper(self, *a, **kw):
        if callable(_orig_initGui_pg):
            _orig_initGui_pg(self, *a, **kw)

        try:
            from qgis.PyQt.QtWidgets import QAction
            from qgis.PyQt.QtGui import QKeySequence, QIcon
            import os

            # ------------------------------------------------------------------------------
            # Ensure toolbar exists
            # ------------------------------------------------------------------------------
            try:
                if not hasattr(self, 'toolbar') or self.toolbar is None:
                    self.toolbar = self.iface.addToolBar('FiberQ Toolbar')
                    self.toolbar.setObjectName('FiberQToolbar')
            except Exception:
                pass

            # Make sure SVGs in styles resolve on every machine
            try:
                if hasattr(self, "_ensure_plugin_svg_search_path"):
                    self._ensure_plugin_svg_search_path()
            except Exception:
                pass


            # ------------------------------------------------------------------------------
            # Publish to PostGIS (existing button)
            # ------------------------------------------------------------------------------
            try:
                if not hasattr(self, 'action_publish_pg') or self.action_publish_pg is None:
                    icon_path = os.path.join(os.path.dirname(__file__), 'icons', 'ic_publish_pg.svg')
                    icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

                    self.action_publish_pg = QAction(icon, 'Publish to PostGIS', self.iface.mainWindow())

                    try:
                        self.action_publish_pg.setShortcut(QKeySequence('Ctrl+P'))
                    except Exception:
                        pass

                    self.action_publish_pg.triggered.connect(self.open_publish_dialog)

                    # Toolbar
                    try:
                        if self.toolbar is not None:
                            self.toolbar.addAction(self.action_publish_pg)
                    except Exception:
                        pass

                    # Menu
                    try:
                        self.iface.addPluginToMenu('FiberQ', self.action_publish_pg)
                    except Exception:
                        pass

                    # Register action
                    try:
                        self.actions.append(self.action_publish_pg)
                    except Exception:
                        pass
            except Exception:
                pass

            # ------------------------------------------------------------------------------
            # FiberQ Settings (NEW button)
            # ------------------------------------------------------------------------------
            try:
                if not hasattr(self, "action_settings"):
                    icon_path_settings = os.path.join(os.path.dirname(__file__), "icons", "ic_settings.svg")
                    icon_settings = QIcon(icon_path_settings) if os.path.exists(icon_path_settings) else QIcon()

                    self.action_settings = QAction(icon_settings, "Settings", self.iface.mainWindow())
                    self.action_settings.triggered.connect(self.open_fiberq_settings)

                    # Toolbar
                    try:
                        if self.toolbar is not None:
                            self.toolbar.addAction(self.action_settings)
                    except Exception:
                        pass
                    # Menu
                    try:
                        self.iface.addPluginToMenu("FiberQ", self.action_settings)
                    except Exception:
                        pass

                    # Register action
                    try:
                        self.actions.append(self.action_settings)
                    except Exception:
                        pass
            except Exception:
                pass

        except Exception:
            pass


    # Patch the class method
    _cls = globals().get('FiberQPlugin')
    if _cls is not None:
        _cls.initGui = _pg_initGui_wrapper
except Exception:   
    pass
# === MAP TOOL: Change element type (Izmena tipa elementa) ===
try:
    from qgis.gui import QgsMapTool, QgsMapToolIdentify
    from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes, QgsFeature, QgsGeometry, QgsPointXY, QgsField, QgsVectorLayerSimpleLabeling, QgsMarkerSymbol, QgsSvgMarkerSymbolLayer, QgsPalLayerSettings, QgsUnitTypes
    from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog, QComboBox
    from qgis.PyQt.QtCore import QVariant
    from qgis.PyQt.QtGui import QColor
except Exception:
    pass

class ChangeElementTypeTool(QgsMapToolIdentify):
    """Klik na element (iz 'Polaganje elemenata'), pa izbor novog tipa i premeštanje u odgovarajući sloj uz stil."""
    def __init__(self, iface, core):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.core = core
        self.canvas = iface.mapCanvas()
        try:
            from qgis.gui import QgsVertexMarker
            self.snap_marker = QgsVertexMarker(self.canvas)
            self.snap_marker.setIconType(QgsVertexMarker.ICON_CROSS)
            self.snap_marker.setPenWidth(3)
            self.snap_marker.setIconSize(14)
            self.snap_marker.setColor(QColor(0, 200, 0))
            self.snap_marker.hide()
        except Exception:
            self.snap_marker = None

    def activate(self):
        try:
            if self.snap_marker: self.snap_marker.show()
            self.iface.messageBar().pushInfo("Change element type", "Click on an element and choose a new type.")
        except Exception:
            pass
        super().activate()

    def deactivate(self):
        try:
            if self.snap_marker: self.snap_marker.hide()
        except Exception:
            pass
        super().deactivate()

    def _element_names(self):
        """
        Tipovi koji se nude u combo-u – samo engleska imena
        (isto kao u Placing elements listi).
        """
        names = []
        try:
            for edef in ELEMENT_DEFS:
                nm = edef.get("name")
                if nm and nm not in names:
                    names.append(nm)
        except Exception:
            pass

        # If using Joint Closures (nastavci), leave this;
        # if you don't want it in the list either, feel free to delete this whole block.
        try:
            from .joint_closure_tool import NASTAVAK_DEF  # if import already exists, ignore this line
        except Exception:
            NASTAVAK_DEF = None

        try:
            if NASTAVAK_DEF:
                jc_name = NASTAVAK_DEF.get("name", "Joint Closures")
                if jc_name and jc_name not in names:
                    names.append(jc_name)
        except Exception:
            pass

        return names



    def _is_element_layer(self, lyr):
        try:
            if not (isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry):
                return False

            name = (lyr.name() or "").strip()

            # Eng imena (Placing elements)
            if name in self._element_names():
                return True

            # Legacy srpska imena da stari projekti i dalje rade
            return name in ("Nastavci", "Nastavak")
        except Exception:
            return False



    def canvasReleaseEvent(self, e):
        # Identify hit on point layers that match element names
        res = self.identify(e.x(), e.y(), self.TopDownAll, self.VectorLayer)
        if not res:
            try:
                QMessageBox.information(self.iface.mainWindow(), "Change element type", "You did not click on any element.")
            except Exception:
                pass
            return

        hit_layer, hit_fid = None, None
        for hit in res:
            layer = getattr(hit, "mLayer", None) or getattr(hit, "layer", None)
            feature = getattr(hit, "mFeature", None) or getattr(hit, "feature", None)
            if layer is not None and feature is not None and self._is_element_layer(layer):
                hit_layer = layer
                try:
                    hit_fid = int(feature.id())
                except Exception:
                    hit_fid = feature.id()
                break

        if hit_layer is None or hit_fid is None:
            try:
                QMessageBox.information(self.iface.mainWindow(), "Change element type", "Click exactly on a point element from the placement list.")
            except Exception:
                pass
            return

        # Ask for new type (combo)
        names = self._element_names()
        try:
            current = hit_layer.name()
        except Exception:
            current = ""
        try:
            new_name, ok = QInputDialog.getItem(self.iface.mainWindow(), "Change element type", "New type:", names, max(0, names.index(current)) if current in names else 0, False)
        except Exception:
            new_name, ok = (names[0] if names else "", True)

        if not ok or not new_name or new_name == current:
            return

        try:
            self.core._change_element_type(hit_layer, hit_fid, new_name)
            try:
                self.iface.messageBar().pushSuccess("Change element type", f"Element changed to: {new_name}")
            except Exception:
                pass
        except Exception as e:
            try:
                QMessageBox.critical(self.iface.mainWindow(), "Change element type", f"Error: {e}")
            except Exception:
                pass
        finally:
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass



# === CORE: helpers for ChangeElementTypeTool ===
def _element_def_by_name(name: str):
    try:
        for ed in ELEMENT_DEFS:
            if ed.get("name") == name:
                return ed
    except Exception:
        pass
    return None

def _ensure_element_layer_with_style(plugin, layer_name: str):
    """Find or create a point layer named 'layer_name' and apply style/labels from ELEMENT_DEFS."""
    from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes, QgsField, QgsMarkerSymbol, QgsSvgMarkerSymbolLayer, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsUnitTypes
    from qgis.PyQt.QtCore import QVariant
    # find existing
    elem_layer = None
    for lyr in QgsProject.instance().mapLayers().values():
        try:
            if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry and lyr.name() == layer_name:
                elem_layer = lyr; break
        except Exception:
            pass
    if elem_layer is None:
        crs = plugin.iface.mapCanvas().mapSettings().destinationCrs().authid()
        elem_layer = QgsVectorLayer(f"Point?crs={crs}", layer_name, "memory")
        pr = elem_layer.dataProvider()
        # add default attrs for that element
        try:
            specs = _default_fields_for(layer_name)
        except Exception:
            specs = [("naziv","Naziv","text","",None)]
        fields = []
        for (key,label,kind,default,opts) in specs:
            qt = QVariant.String
            if kind in ("int","year"):
                qt = QVariant.Int
            elif kind == "double":
                qt = QVariant.Double
            elif kind == "enum":
                qt = QVariant.String
            fields.append(QgsField(key, qt))
        if not any(f.name()=="naziv" for f in fields):
            fields.insert(0, QgsField("naziv", QVariant.String))
        pr.addAttributes(fields); elem_layer.updateFields()

        # Style
        edef = _element_def_by_name(layer_name) or {}
        spec = edef.get("symbol") if isinstance(edef, dict) else None
        if isinstance(spec, dict) and spec.get('svg_path'):
            symbol = QgsMarkerSymbol.createSimple({'name':'circle','size':'5','size_unit':'MapUnit'})
            try:
                svg_layer = QgsSvgMarkerSymbolLayer(spec['svg_path'])
                try: svg_layer.setSize(float(spec.get('size', 6)))
                except Exception: pass
                try: svg_layer.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
                except Exception: svg_layer.setSizeUnit(QgsUnitTypes.RenderMapUnits)
                symbol.changeSymbolLayer(0, svg_layer)
            except Exception:
                pass
        elif isinstance(spec, dict):
            symbol = QgsMarkerSymbol.createSimple(spec)
        else:
            symbol = QgsMarkerSymbol.createSimple({'name':'circle','size':'5'})
        try:
            elem_layer.renderer().setSymbol(symbol)
        except Exception:
            pass

        # Labels
        try:
            _apply_fixed_text_label(elem_layer, 'naziv', 8.0, 5.0)
        except Exception:
            try:
                s = QgsPalLayerSettings(); s.fieldName = "naziv"; s.enabled = True
                elem_layer.setLabeling(QgsVectorLayerSimpleLabeling(s)); elem_layer.setLabelsEnabled(True)
            except Exception:
                pass

        QgsProject.instance().addMapLayer(elem_layer)

    # Uvek osveži engleske alias-e za taj sloj
    try:
        _apply_element_aliases(elem_layer)
    except Exception:
        pass

    return elem_layer

def _copy_attributes_between_layers(src_feat, dst_layer):
    """Map attributes by normalized names; add missing fields on destination (only when safe).
    IMPORTANT: never copy PK fields (fid/id/gid...) into destination.
    """
    from qgis.core import QgsField
    from qgis.PyQt.QtCore import QVariant

    # normalized field name maps
    src_map = {_normalize_name(f.name()): f for f in src_feat.fields()}
    dst_map = {_normalize_name(f.name()): f for f in dst_layer.fields()}

    # detect destination PK fields and always skip them
    skip = {"fid", "id", "gid"}
    try:
        pk_idxs = dst_layer.dataProvider().pkAttributeIndexes()
        for i in pk_idxs:
            if 0 <= i < dst_layer.fields().count():
                skip.add(_normalize_name(dst_layer.fields()[i].name()))
    except Exception:
        pass

    # Allow schema change only for local/OGR/memory style providers (avoid PostGIS ALTER TABLE from plugin)
    prov = ""
    try:
        prov = (dst_layer.providerType() or "").lower()
    except Exception:
        pass
    allow_schema_change = prov in ("ogr", "memory")  # gpkg/shp/dxf/kml/memory OK; postgres NO

    # add missing non-PK fields (only when allowed)
    to_add = []
    for key, f in src_map.items():
        if key in skip:
            continue
        if key not in dst_map:
            try:
                to_add.append(QgsField(f.name(), f.type() if hasattr(f, "type") else QVariant.String))
            except Exception:
                to_add.append(QgsField(f.name(), QVariant.String))

    if to_add and allow_schema_change:
        dst_layer.startEditing()
        dst_layer.dataProvider().addAttributes(to_add)
        dst_layer.updateFields()
        dst_layer.commitChanges()
        dst_map = {_normalize_name(f.name()): f for f in dst_layer.fields()}

    # build attribute dict (skip PK fields)
    vals = {}
    for key, f in src_map.items():
        if key in skip:
            continue
        if key in dst_map:
            try:
                vals[dst_map[key].name()] = src_feat[f.name()]
            except Exception:
                pass
    return vals


def _change_element_type(self, src_layer, src_fid, new_name: str):
    """Move feature from src_layer to target layer `new_name`.
    Safe against PK/UNIQUE constraints (won't copy fid; won't delete source if insert fails).
    """
    from qgis.core import QgsFeature, QgsGeometry

    # get source feature
    f = None
    for feat in src_layer.getFeatures():
        if int(feat.id()) == int(src_fid):
            f = feat
            break
    if f is None:
        raise RuntimeError("Selected element was not found.")

    # ensure target layer
    dst_layer = _ensure_element_layer_with_style(self, new_name)

    # copy attributes (without PK fields)
    vals = _copy_attributes_between_layers(f, dst_layer)

    # create new feature
    new_f = QgsFeature(dst_layer.fields())
    try:
        new_f.setGeometry(QgsGeometry(f.geometry()))
    except Exception:
        new_f.setGeometry(f.geometry())

    for k, v in vals.items():
        try:
            new_f.setAttribute(k, v)
        except Exception:
            pass

    # INSERT into destination (check success!)
    dst_layer.startEditing()
    ok = dst_layer.addFeature(new_f)
    if not ok:
        try:
            dst_layer.rollBack()
        except Exception:
            pass
        raise RuntimeError("Failed to insert into target layer (constraint/PK conflict).")

    if not dst_layer.commitChanges():
        try:
            dst_layer.rollBack()
        except Exception:
            pass
        raise RuntimeError("Failed to commit changes to target layer.")

    dst_layer.triggerRepaint()

    # delete old only after successful insert
    try:
        src_layer.startEditing()
        src_layer.deleteFeature(int(src_fid))
        src_layer.commitChanges()
        src_layer.triggerRepaint()
    except Exception:
        pass

# Dummy reference for linters (function is used via dynamic binding / setattr)
_ = _change_element_type

# Bind function as method on plugin class so map tool can call self.core._change_element_type(...)
try:
    if 'FiberQPlugin' in globals():
        setattr(StuboviPlugin, '_change_element_type', _change_element_type)
except Exception:
    pass

def activate_change_element_type_tool(self):
    try:
        self._change_elem_tool = ChangeElementTypeTool(self.iface, self)
        self.iface.mapCanvas().setMapTool(self._change_elem_tool)
    except Exception as e:
        try:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(self.iface.mainWindow(), "Izmena tipa elementa", f"Greška: {e}")
        except Exception:
            pass

try:
    if 'FiberQPlugin' in globals():
        setattr(StuboviPlugin, 'activate_change_element_type_tool', activate_change_element_type_tool)
except Exception:
    pass



# === AUTO PATCH: add "Izmena tip elementa" toolbar button ===
try:
    _orig_initGui_edit_elem = getattr(globals().get('FiberQPlugin'), 'initGui', None)
    def _edit_elem_initGui_wrapper(self, *a, **kw):
        if callable(_orig_initGui_edit_elem):
            _orig_initGui_edit_elem(self, *a, **kw)
        try:
            from qgis.PyQt.QtWidgets import QAction
            icon = _load_icon('ic_selection.svg')  # reuse selection icon style
            self.action_change_element_type = QAction(icon, "Change element type", self.iface.mainWindow())
            self.action_change_element_type.setToolTip("Smart selection + change element type (visual style)")
            self.action_change_element_type.triggered.connect(self.activate_change_element_type_tool)
            # add to toolbar
            try:
                self.toolbar.addAction(self.action_change_element_type)
            except Exception:
                self.iface.addToolBarIcon(self.action_change_element_type)
            try:
                self.actions.append(self.action_change_element_type)
            except Exception:
                pass
        except Exception:
            pass
    _cls = globals().get('FiberQPlugin')
    if _cls is not None:
        _cls.initGui = _edit_elem_initGui_wrapper
except Exception:
    pass


# === Kreiranje Rejona (Create Region) =========================================
try:
    from qgis.PyQt.QtCore import QVariant
    from qgis.core import (
        QgsVectorLayer, QgsProject, QgsField, QgsFeature, QgsGeometry,
        QgsWkbTypes, QgsDistanceArea, QgsUnitTypes
    )
    from qgis.PyQt.QtWidgets import QAction, QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QDialogButtonBox, QLabel, QMessageBox
    from qgis.PyQt.QtGui import QIcon
except Exception:
    # If imports fail in static analyzers
    pass

def _fiberq_extend_translations_for_region():
    """Monkey-patch translator to include our new phrases."""
    try:
        old_fn = globals().get('_fiberq_translate')
        if not callable(old_fn):
            return
        def _patched(text: str, lang: str):
            try:
                if isinstance(text, str) and lang and lang.upper().startswith('EN'):
                    key = text.strip()
                    if key in ('Kreiranje Rejona', 'Kreiraj rejon', 'Rejon'):
                        m = {
                            'Kreiranje Rejona': 'Create region',
                            'Kreiraj rejon': 'Create region',
                            'Rejon': 'Region'
                        }
                        return m.get(key, key)
            except Exception:
                pass
            return old_fn(text, lang)
        globals()['_fiberq_translate'] = _patched
    except Exception:
        pass

_fiberq_extend_translations_for_region()


def _ensure_rejon_layer(core):
    """
    Ensure a polygon layer for service areas exists.

    Internally we previously used name 'Rejon', but display 'Service Area' to user.
    """
    try:
        proj = QgsProject.instance()

        # 1) Pronađi postojeći sloj (bilo 'Rejon' ili 'Service Area')
        for lyr in proj.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.PolygonGeometry
                    and lyr.name() in ('Rejon', 'Service Area')
                ):
                    # If old name is 'Rejon', rename it so user sees 'Service Area'
                    if lyr.name() == 'Rejon':
                        try:
                            lyr.setName('Service Area')
                        except Exception:
                            pass
                    return lyr
            except Exception:
                continue

        # 2) If doesn't exist – create new layer named 'Service Area'
        crs = proj.crs().authid() if proj and proj.crs().isValid() else 'EPSG:3857'
        rejon = QgsVectorLayer(f'Polygon?crs={crs}', 'Service Area', 'memory')
        pr = rejon.dataProvider()
        pr.addAttributes([
            QgsField('name', QVariant.String),
            QgsField('created_at', QVariant.String),
            QgsField('area_m2', QVariant.Double),
            QgsField('perim_m', QVariant.Double),
            QgsField('count', QVariant.Int),
        ])
        rejon.updateFields()

        # Jednostavan poluprovidan stil
        try:
            sym = rejon.renderer().symbol()
            sym.setOpacity(0.25)
        except Exception:
            pass

        proj.addMapLayer(rejon)
        return rejon

    except Exception as e:
        try:
            QMessageBox.critical(core.iface.mainWindow(), 'Service Area', f'Error creating layer: {e}')
        except Exception:
            pass
        return None




def _collect_selected_geometries(core):
    """Collect selected geometries from all visible vector layers (points/lines/polygons)."""
    geoms = []
    try:
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if not isinstance(lyr, QgsVectorLayer):
                    continue
                if lyr.selectedFeatureCount() == 0:
                    continue
                # Take all selected
                for f in lyr.selectedFeatures():
                    g = f.geometry()
                    if not g or g.isEmpty():
                        continue
                    geoms.append((lyr, f, g))
            except Exception:
                continue
    except Exception:
        pass
    return geoms


class CreateRegionDialog(QDialog):
    def __init__(self, core, parent=None):
        super().__init__(parent or core.iface.mainWindow())
        self.core = core
        self.setWindowTitle('Service Area')
        lay = QFormLayout(self)

        self.edt_name = QLineEdit()
        self.edt_name.setPlaceholderText('e.g. Service Area 1')
        lay.addRow(QLabel('Service Area Name'), self.edt_name)

        self.spin_buffer = QDoubleSpinBox()
        self.spin_buffer.setDecimals(1)
        self.spin_buffer.setMinimum(0.0)
        self.spin_buffer.setMaximum(9999.0)
        self.spin_buffer.setSingleStep(1.0)
        self.spin_buffer.setValue(5.0)
        self.spin_buffer.setSuffix(' m')
        lay.addRow(QLabel('Margin (buffer)'), self.spin_buffer)

        self.lbl_info = QLabel('Use selection from map (cables/elements).')
        self.lbl_info.setStyleSheet('color: #475569')
        lay.addRow(self.lbl_info)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def buffer_value(self) -> float:
        try:
            return float(self.spin_buffer.value())
        except Exception:
            return 0.0

    def region_name(self) -> str:
        return (self.edt_name.text() or '').strip() or 'Rejon'


def _create_region_from_selection(core, name: str, buf_m: float):
    geoms = _collect_selected_geometries(core)
    if not geoms:
        try:
            QMessageBox.information(core.iface.mainWindow(), 'Create Service Area', 'No selected objects. Select cables/elements and try again.')
        except Exception:
            pass
        return False

    # Prepare buffers for point/line features; polygons keep geometry (optional small buffer)
    polys = []
    for lyr, feat, g in geoms:
        try:
            g = QgsGeometry(g)  # copy
            gtype = lyr.geometryType()
            if gtype in (QgsWkbTypes.PointGeometry, QgsWkbTypes.LineGeometry):
                if buf_m > 0:
                    polys.append(g.buffer(buf_m, 8))
                else:
                    # zero buffer to get minimal area around lines/points
                    polys.append(g.buffer(0.01, 8))
            else:
                # polygon - optionally buffer outward by buf_m (small)
                if buf_m > 0:
                    polys.append(g.buffer(buf_m, 8))
                else:
                    polys.append(g)
        except Exception:
            continue

    if not polys:
        try:
            QMessageBox.warning(core.iface.mainWindow(), 'Create Service Area', 'Cannot calculate geometries.')
        except Exception:
            pass
        return False

    # Union/Dissolve all
    try:
        u = QgsGeometry.unaryUnion(polys)
    except Exception:
        # fallback: iterative union
        u = None
        for p in polys:
            if u is None:
                u = QgsGeometry(p)
            else:
                try:
                    u = u.combine(p)
                except Exception:
                    pass

    if not u or u.isEmpty():
        try:
            QMessageBox.warning(core.iface.mainWindow(), 'Create Service Area', 'Result is empty.')
        except Exception:
            pass
        return False

    # Ensure polygon geometry (polygonize buffers already are)
    if u.type() != QgsWkbTypes.PolygonGeometry:
        try:
            u = u.buffer(0.01, 8)
        except Exception:
            pass

    # Explode multi into parts
    parts = []
    try:
        if u.isMultipart():
            for poly in u.asMultiPolygon():
                try:
                    parts.append(QgsGeometry.fromPolygonXY(poly))
                except Exception:
                    pass
        else:
            parts.append(u)
    except Exception:
        parts = [u]

    rejon = _ensure_rejon_layer(core)
    if not rejon:
        return False

    # Measure area/perimeter with project settings
    d = QgsDistanceArea()
    try:
        prj = QgsProject.instance()
        if prj.ellipsoid():
            d.setEllipsoid(prj.ellipsoid())
        d.setSourceCrs(prj.crs(), QgsProject.instance().transformContext())
        d.setEllipsoidalMode(True)
    except Exception:
        pass

    # Add features
    added = 0
    try:
        rejon.startEditing()
        for part in parts:
            if not part or part.isEmpty():
                continue
            area = d.measureArea(part) if d else part.area()
            peri = d.measurePerimeter(part) if d else part.length()
            f = QgsFeature(rejon.fields())
            try:
                f.setGeometry(part)
            except Exception:
                pass
            f['name'] = name
            f['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f['area_m2'] = float(area)
            f['perim_m'] = float(peri)
            f['count'] = len(geoms)
            rejon.addFeature(f)
            added += 1
        rejon.commitChanges()
        rejon.triggerRepaint()
    except Exception as e:
        try:
            rejon.rollBack()
        except Exception:
            pass
        try:
            QMessageBox.critical(core.iface.mainWindow(), 'Create Service Area', f'Error: {e}')
        except Exception:
            pass
        return False

    try:
        QMessageBox.information(core.iface.mainWindow(), 'Create Service Area', f'Created: {added} polygon(s) in "Service Area" layer.')
    except Exception:
        pass
    return True


# ---- Hook into plugin toolbar ---- KREIRANJE REJONA
try:
    _orig_initGui_rejon = getattr(globals().get('FiberQPlugin'), 'initGui', None)
    def _initGui_with_rejon(self, *args, **kwargs):
        if callable(_orig_initGui_rejon):
            _orig_initGui_rejon(self, *args, **kwargs)
        try:
            icon = _load_icon('ic_service_area.svg') if 'ic_service_area.svg' else QIcon()
            self.action_create_region = QAction(icon, 'Create Service Area', self.iface.mainWindow())
            self.action_create_region.setToolTip('Create Service Area from selection (buffer around selected cables/elements)')
            def _run():
                dlg = CreateRegionDialog(self, parent=self.iface.mainWindow())
                if dlg.exec_() == QDialog.Accepted:
                    _create_region_from_selection(self, dlg.region_name(), dlg.buffer_value())
            self.action_create_region.triggered.connect(_run)
            try:
                self.toolbar.addAction(self.action_create_region)
            except Exception:
                self.iface.addToolBarIcon(self.action_create_region)
            try:
                # keep for language updates
                if hasattr(self, 'actions') and isinstance(self.actions, list):
                    self.actions.append(self.action_create_region)
            except Exception:
                pass
        except Exception:
            pass
    _cls = globals().get('FiberQPlugin')
    if _cls is not None:
        _cls.initGui = _initGui_with_rejon
except Exception:
    pass
# === /Kreiranje Rejona ========================================================


# === Draw Region (manual polygon) ==============================================
try:
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QInputDialog
    from qgis.gui import QgsMapTool, QgsRubberBand
    from qgis.core import QgsPointXY, QgsGeometry, QgsWkbTypes, QgsDistanceArea
except Exception:
    pass

def _fiberq_extend_translations_for_region_manual():
    """Extend translator for manual draw strings."""
    try:
        old_fn = globals().get('_fiberq_translate')
        if not callable(old_fn):
            return
        def _patched(text: str, lang: str):
            try:
                if isinstance(text, str) and lang and lang.upper().startswith('EN'):
                    m = {
                        'Nacrtaj rejon ručno': 'Draw region (manual)',
                        'Nacrtaj rejon rucno': 'Draw region (manual)',
                        'Kreiranje Rejona': 'Create region',
                        'Kreiraj rejon': 'Create region',
                        'Rejon': 'Region',
                    }
                    if text.strip() in m:
                        return m[text.strip()]
            except Exception:
                pass
            return old_fn(text, lang)
        globals()['_fiberq_translate'] = _patched
    except Exception:
        pass

_fiberq_extend_translations_for_region_manual()

class DrawRegionPolygonTool(QgsMapTool):
    """Freehand polygon drawing tool with rubber band (finish with right-click)"""
    def __init__(self, iface, core):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.core = core
        self.canvas = iface.mapCanvas()
        self.points = []
        self.rb = None
        self._setup_rb()

    def _setup_rb(self):
        try:
            self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
            # Style similar to other toolbar icons: soft slate stroke, semi-transparent fill
            self.rb.setWidth(2)
            from qgis.PyQt.QtGui import QColor
            self.rb.setStrokeColor(QColor('#334155'))  # slate-700
            c = QColor('#60a5fa')  # blue-400
            c.setAlpha(60)
            self.rb.setFillColor(c)
        except Exception:
            self.rb = None

    def activate(self):
        try:
            if self.rb is None:
                self._setup_rb()
            self.points = []
            if self.rb: self.rb.reset(QgsWkbTypes.PolygonGeometry)
            self.iface.messageBar().pushInfo('Draw Service Area (manual)', 'Left click adds vertices, Backspace removes, right click finishes.')
        except Exception:
            pass
        super().activate()

    def deactivate(self):
        try:
            if self.rb: self.rb.reset(QgsWkbTypes.PolygonGeometry)
        except Exception:
            pass
        super().deactivate()

    def keyPressEvent(self, e):
        try:
            if e.key() in (Qt.Key_Backspace, Qt.Key_Delete):
                if self.points:
                    self.points.pop()
                    self._update_rb()
            elif e.key() == Qt.Key_Escape:
                self.points = []
                self._update_rb()
        except Exception:
            pass

    def canvasPressEvent(self, e):
        if e.button() == Qt.LeftButton:
            # dodavanje tačke u poligon
            self.points.append(self.toMapCoordinates(e.pos()))
            self._update_rb()

        elif e.button() == Qt.RightButton:
            # desni klik: ako nema dovoljno tačaka -> odustani i izađi
            if len(self.points) < 3:
                self.points = []
                self._update_rb()
                try:
                    self.canvas.unsetMapTool(self)
                except Exception:
                    pass
            else:
                # imamo validan poligon -> završi crtanje i izađi iz alata
                self._finish_polygon()


    def canvasMoveEvent(self, e):
        try:
            if self.points:
                p = self.toMapCoordinates(e.pos())
                self._update_rb(temp_point=QgsPointXY(p))
        except Exception:
            pass

    def _update_rb(self, temp_point=None):
        try:
            if not self.rb: return
            self.rb.reset(QgsWkbTypes.PolygonGeometry)
            pts = list(self.points)
            if temp_point is not None:
                pts.append(temp_point)
            if len(pts) >= 2:
                self.rb.setToGeometry(QgsGeometry.fromPolygonXY([pts]), None)
        except Exception:
            pass

    def _finish_polygon(self):
        try:
            if len(self.points) < 3:
                self.iface.messageBar().pushWarning('Draw Service Area manually', 'At least 3 vertices are required..')
                return
            geom = QgsGeometry.fromPolygonXY([self.points])
            rejon = _ensure_rejon_layer(self.core)
            if not rejon:
                return
            # Ask for name
            try:
                name, ok = QInputDialog.getText(self.iface.mainWindow(), 'Service Area', 'Name:')
            except Exception:
                name, ok = ('Rejon', True)
            if not ok:
                return

            d = QgsDistanceArea()
            try:
                prj = QgsProject.instance()
                if prj.ellipsoid(): d.setEllipsoid(prj.ellipsoid())
                d.setSourceCrs(prj.crs(), QgsProject.instance().transformContext())
                d.setEllipsoidalMode(True)
            except Exception:
                pass

            area = d.measureArea(geom) if d else geom.area()
            peri = d.measurePerimeter(geom) if d else geom.length()

            rejon.startEditing()
            f = QgsFeature(rejon.fields())
            f.setGeometry(geom)
            from datetime import datetime as _dt
            f['name'] = (name or 'Rejon')
            f['created_at'] = _dt.now().strftime('%Y-%m-%d %H:%M:%S')
            f['area_m2'] = float(area)
            f['perim_m'] = float(peri)
            f['count'] = 0
            rejon.addFeature(f)
            rejon.commitChanges()
            rejon.triggerRepaint()
            self.iface.messageBar().pushSuccess('Service Area', 'Service Area added to "Service Area" layer.')
            # Reset for next polygon
            self.points = []
            self._update_rb()
            # posle uspešnog crtanja – izađi iz alata
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass
        except Exception as e:
            try:
                self.iface.messageBar().pushCritical('Service Area', f'Error: {e}')
            except Exception:
                pass

# ---- Hook: add "Nacrtaj rejon ručno" button to toolbar ------------------------
try:
    _orig_initGui_rejon_draw = getattr(globals().get('FiberQPlugin'), 'initGui', None)
    def _initGui_with_rejon_draw(self, *args, **kwargs):
        if callable(_orig_initGui_rejon_draw):
            _orig_initGui_rejon_draw(self, *args, **kwargs)
        try:
            icon = _load_icon('ic_draw_service_area.svg') if 'ic_draw.svg' else QIcon()
            self.action_draw_region = QAction(icon, 'Draw Service Area Manually', self.iface.mainWindow())
            self.action_draw_region.setToolTip('Manual Service Area drawing (like Google Earth) and entry into "Service Area" layer')
            # Lazily create tool on first use
            def _activate():
                try:
                    if not hasattr(self, '_draw_region_tool') or self._draw_region_tool is None:
                        self._draw_region_tool = DrawRegionPolygonTool(self.iface, self)
                    self.iface.mapCanvas().setMapTool(self._draw_region_tool)
                except Exception:
                    pass
            self.action_draw_region.triggered.connect(_activate)
            try:
                self.toolbar.addAction(self.action_draw_region)
            except Exception:
                self.iface.addToolBarIcon(self.action_draw_region)
            try:
                if hasattr(self, 'actions') and isinstance(self.actions, list):
                    self.actions.append(self.action_draw_region)
            except Exception:
                pass
        except Exception:
            pass
    _cls = globals().get('FiberQPlugin')
    if _cls is not None:
        _cls.initGui = _initGui_with_rejon_draw
except Exception:
    pass
# === /Draw Region (manual polygon) =============================================

# === Crtanje objekta (polygon tools + dialog) ==================================
try:
    from qgis.gui import QgsMapTool
    from qgis.PyQt.QtWidgets import (QMenu, QToolButton, QDialog, QFormLayout, QLineEdit,
                                     QSpinBox, QDialogButtonBox, QRadioButton, QGroupBox, QVBoxLayout, QLabel)
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import QVariant
    from qgis.core import (QgsProject, QgsVectorLayer, QgsWkbTypes, QgsField, QgsFeature,
                           QgsGeometry, QgsPointXY, QgsRubberBand, QgsDistanceArea, QgsCoordinateTransformContext,
                           QgsUnitTypes, QgsLineSymbol, QgsFillSymbol, QgsLinePatternFillSymbolLayer, QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer)
except Exception:
    pass


def _set_objects_layer_alias(layer):
    """Display layer 'Objekti/Objects' as 'Objects' in Layers panel."""
    try:
        root = QgsProject.instance().layerTreeRoot()
        node = root.findLayer(layer.id())
        if node:
            node.setCustomLayerName("Objects")
    except Exception:
        # if something fails (e.g. layerTreeRoot is not ready yet), just skip
        pass


def _apply_objects_field_aliases(layer):
    """Set English alias field names for layer Objekti/Objects."""
    alias_map = {
        "tip": "Type",
        "spratova": "Floors above ground",
        "podzemnih": "Floors below ground",
        "ulica": "Street",
        "broj": "Number",
        "naziv": "Name",
        "napomena": "Note",
    }
    try:
        for field_name, alias in alias_map.items():
            idx = layer.fields().indexOf(field_name)
            if idx != -1:
                layer.setFieldAlias(idx, alias)
    except Exception:
        # stari projekat itd. – samo preskoči
        pass


def _ensure_objekti_layer(core):
    """Create / return polygon layer 'Objects' with standard fields."""
    try:
        prj = QgsProject.instance()

        # 1) If layer already exists – accept both "Objekti" and "Objects"
        for lyr in prj.mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.wkbType() in (
                        QgsWkbTypes.Polygon,
                        QgsWkbTypes.MultiPolygon,
                        QgsWkbTypes.PolygonZM,
                        QgsWkbTypes.MultiPolygonZM,
                    )
                    and lyr.name() in ("Objekti", "Objects")
                ):
                    _apply_objects_field_aliases(lyr)
                    _set_objects_layer_alias(lyr)
                    return lyr
            except Exception:
                pass

        # 2) If doesn't exist – create new layer named "Objects"
        crs = core.iface.mapCanvas().mapSettings().destinationCrs().authid()
        layer = QgsVectorLayer(f"Polygon?crs={crs}", "Objects", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("tip", QVariant.String),
            QgsField("spratova", QVariant.Int),
            QgsField("podzemnih", QVariant.Int),
            QgsField("ulica", QVariant.String),
            QgsField("broj", QVariant.String),
            QgsField("naziv", QVariant.String),
            QgsField("napomena", QVariant.String),
        ])
        layer.updateFields()

        prj.addMapLayer(layer)
        _stylize_objekti_layer(layer)

        # engleski aliasi + prikaz imena sloja
        _apply_objects_field_aliases(layer)
        _set_objects_layer_alias(layer)

        return layer
    except Exception:
        return None


def _stylize_objekti_layer(layer):
    """Apply black solid outline + diagonal hatch inside (DWG-like)."""
    try:
        # Build composite fill: transparent interior + black outline
        simple = QgsSimpleFillSymbolLayer()
        simple.setFillColor(QColor(0, 0, 0, 0))  # transparent fill, outline only
        simple.setStrokeColor(QColor(0, 0, 0))   # solid black border
        simple.setStrokeWidth(0.8)
        simple.setStrokeWidthUnit(QgsUnitTypes.RenderMillimeters)

        # Hatch lines at an angle
        hatch = QgsLinePatternFillSymbolLayer()
        try:
            # QGIS API names differ; try both
            try:
                hatch.setLineAngle(60.0)
            except Exception:
                try:
                    hatch.setAngle(60.0)
                except Exception:
                    pass
        except Exception:
            pass
        hatch.setDistance(2.2)
        hatch.setDistanceUnit(QgsUnitTypes.RenderMillimeters)
        # Tune hatch sub symbol (line style, color, width)
        try:
            sub = hatch.subSymbol()
            if sub and sub.symbolLayerCount() > 0:
                sl = sub.symbolLayer(0)
                try: sl.setColor(QColor(0, 0, 0))
                except Exception: pass
                try:
                    sl.setWidth(0.3)
                    sl.setWidthUnit(QgsUnitTypes.RenderMillimeters)
                except Exception:
                    pass
        except Exception:
            pass

        sym = QgsFillSymbol()
        try: sym.deleteSymbolLayer(0)  # remove default
        except Exception: pass
        sym.appendSymbolLayer(hatch)
        sym.appendSymbolLayer(simple)

        from qgis.core import QgsSingleSymbolRenderer
        renderer = QgsSingleSymbolRenderer(sym)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
    except Exception:
        pass

class ObjectPropertiesDialog(QDialog):
    """Simple dialog for entering object attributes (kept minimal and clean)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Object data")
        lay = QVBoxLayout(self)
        gb = QGroupBox("Basic data")
        form = QFormLayout(gb)
        self.ed_tip = QLineEdit()
        self.sb_spr = QSpinBox(); self.sb_spr.setRange(0, 50); self.sb_spr.setValue(1)
        self.sb_pod = QSpinBox(); self.sb_pod.setRange(0, 10); self.sb_pod.setValue(0)
        self.ed_ulica = QLineEdit()
        self.ed_broj = QLineEdit()
        self.ed_naziv = QLineEdit()
        self.ed_napomena = QLineEdit()
        form.addRow("Type:", self.ed_tip)
        form.addRow("Number of floors:", self.sb_spr)
        form.addRow("Number of underground floors:", self.sb_pod)
        form.addRow("Street:", self.ed_ulica)
        form.addRow("Number:", self.ed_broj)
        form.addRow("Name/Description:", self.ed_naziv)
        form.addRow("Note:", self.ed_napomena)
        lay.addWidget(gb)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self):
        return {
            "tip": self.ed_tip.text().strip(),
            "spratova": int(self.sb_spr.value()),
            "podzemnih": int(self.sb_pod.value()),
            "ulica": self.ed_ulica.text().strip(),
            "broj": self.ed_broj.text().strip(),
            "naziv": self.ed_naziv.text().strip(),
            "napomena": self.ed_napomena.text().strip()
        }

class _BaseObjMapTool(QgsMapTool):
    """Base class with rubber band helpers."""
    def __init__(self, iface, core):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.core = core
        self.canvas = iface.mapCanvas()
        self.points = []
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        try:
            self.rb.setWidth(2)
            # semi-transparent fill
            s = self.rb.symbol()
            if s and s.symbolLayerCount()>0:
                try:
                    s.symbolLayer(0).setStrokeColor(QColor(0,0,0,180))
                    s.symbolLayer(0).setFillColor(QColor(10,10,10,40))
                except Exception:
                    pass
        except Exception:
            pass

    def _update_rb(self, pts):
        try:
            self.rb.setToGeometry(QgsGeometry.fromPolygonXY([pts]), None)
        except Exception:
            pass

    def _reset(self):
        """Očisti trenutni crtež (bez izlaska iz alata)."""
        self.points = []
        try:
            self._update_rb([])
        except Exception:
            try:
                self.rb.reset(QgsWkbTypes.PolygonGeometry)
            except Exception:
                pass

    def _finish(self, geom):
        obj_layer = _ensure_objekti_layer(self.core)
        if not obj_layer or geom is None:
            return

        # Open dialog for entering attributes
        dlg = ObjectPropertiesDialog(self.iface.mainWindow())
        if dlg.exec_() != QDialog.Accepted:
            return

        vals = dlg.values()

        try:
            was_editing = obj_layer.isEditable()
        except Exception:
            was_editing = False

        try:
            if not was_editing:
                obj_layer.startEditing()

            f = QgsFeature(obj_layer.fields())
            f.setGeometry(geom)

            # write attributes by field name
            for k, v in (vals or {}).items():
                try:
                    idx = obj_layer.fields().indexFromName(k)
                    if idx != -1:
                        f.setAttribute(idx, v)
                except Exception:
                    pass

            obj_layer.addFeature(f)

            if not was_editing:
                obj_layer.commitChanges()
            else:
                obj_layer.triggerRepaint()

            # stil + aliasi (da ostane “DWG look” i ENG user-view)
            try:
                _stylize_objekti_layer(obj_layer)
            except Exception:
                pass
            try:
                _apply_objects_field_aliases(obj_layer)
                _set_objects_layer_alias(obj_layer)
            except Exception:
                pass

            try:
                self.core.iface.layerTreeView().setCurrentLayer(obj_layer)
            except Exception:
                pass

            try:
                self.iface.messageBar().pushSuccess("Objects", "Object added.")
            except Exception:
                pass

            # auto-exit tool after successful add
            try:
                self.core.iface.actionPan().trigger()  # return to Pan (safest)
            except Exception:
                try:
                    self.core.iface.mapCanvas().unsetMapTool(self)
                except Exception:
                    pass

        except Exception as e:
            try:
                if not was_editing:
                    obj_layer.rollBack()
            except Exception:
                pass
            try:
                QMessageBox.warning(self.iface.mainWindow(), "Objects", f"Cannot add object:\n{e}")
            except Exception:
                pass


    def keyPressEvent(self, event):
        """ESC – poništi trenutni crtež, ali ostavi alat aktivan."""
        from qgis.PyQt.QtCore import Qt
        try:
            if event.key() == Qt.Key_Escape:
                self._reset()
                return
        except Exception:
            pass
        try:
            super().keyPressEvent(event)
        except Exception:
            pass

    def deactivate(self):
        """Kad korisnik promeni alat, očisti gumicu."""
        try:
            self._reset()
        except Exception:
            pass
        try:
            super().deactivate()
        except Exception:
            pass


class DrawObjectNTool(_BaseObjMapTool):
    """Click-to-add vertices; right click to finish."""
    def canvasPressEvent(self, e):
        from qgis.PyQt.QtCore import Qt
        if e.button() == Qt.LeftButton:
            p = self.toMapCoordinates(e.pos())
            self.points.append(QgsPointXY(p))
            self._update_rb(self.points)
        elif e.button() == Qt.RightButton:
            # if enough points – finish, in any case clear drawing
            if len(self.points) >= 3:
                self._finish(QgsGeometry.fromPolygonXY([self.points]))
            self._reset()

    def canvasMoveEvent(self, e):
        if not self.points:
            return
        p = self.toMapCoordinates(e.pos())
        tmp = self.points + [QgsPointXY(p)]
        self._update_rb(tmp)


class DrawObjectOrthoTool(_BaseObjMapTool):
    """Orthogonal segments (90°)."""
    def canvasPressEvent(self, e):
        from qgis.PyQt.QtCore import Qt
        if e.button() == Qt.LeftButton:
            mappt = self.toMapCoordinates(e.pos())
            if not self.points:
                self.points.append(QgsPointXY(mappt))
            else:
                last = self.points[-1]
                dx, dy = mappt.x() - last.x(), mappt.y() - last.y()
                # snap to horizontal or vertical by dominant axis
                if abs(dx) >= abs(dy):
                    p = QgsPointXY(mappt.x(), last.y())
                else:
                    p = QgsPointXY(last.x(), mappt.y())
                self.points.append(p)
            self._update_rb(self.points)
        elif e.button() == Qt.RightButton:
            # if enough points – finish, in any case clear drawing
            if len(self.points) >= 3:
                self._finish(QgsGeometry.fromPolygonXY([self.points]))
            self._reset()

    def canvasMoveEvent(self, e):
        if not self.points:
            return
        last = self.points[-1]
        mappt = self.toMapCoordinates(e.pos())
        dx, dy = mappt.x() - last.x(), mappt.y() - last.y()
        if abs(dx) >= abs(dy):
            p = QgsPointXY(mappt.x(), last.y())
        else:
            p = QgsPointXY(last.x(), mappt.y())
        tmp = self.points + [p]
        self._update_rb(tmp)


class DrawObject3ptTool(_BaseObjMapTool):
    """Rectangle from 3 points: first edge (p1->p2), third defines width (perpendicular)."""
    def canvasPressEvent(self, e):
        from qgis.PyQt.QtCore import Qt

        # desni klik – samo poništi trenutni crtež
        if e.button() == Qt.RightButton:
            self._reset()
            return

        if e.button() != Qt.LeftButton:
            return

        mappt = self.toMapCoordinates(e.pos())
        self.points.append(QgsPointXY(mappt))
        if len(self.points) == 3:
            p1, p2, p3 = self.points
            # vector along edge
            vx, vy = (p2.x() - p1.x(), p2.y() - p1.y())
            # perpendicular vector normalized
            L = (vx**2 + vy**2) ** 0.5
            if L == 0:
                self._reset()
                return
            nx, ny = -vy / L, vx / L
            # width from signed distance of p3 to line p1-p2
            wx = p3.x() - p1.x(); wy = p3.y() - p1.y()
            w = wx * nx + wy * ny
            # corners
            c1 = p1
            c2 = p2
            c3 = QgsPointXY(p2.x() + nx * w, p2.y() + ny * w)
            c4 = QgsPointXY(p1.x() + nx * w, p1.y() + ny * w)
            geom = QgsGeometry.fromPolygonXY([[c1, c2, c3, c4]])
            self._finish(geom)
            self._reset()
        else:
            self._update_rb(self.points)

    def canvasMoveEvent(self, e):
        if len(self.points) < 2:
            return
        p1, p2 = self.points[0], self.points[1]
        mappt = self.toMapCoordinates(e.pos())
        p3 = QgsPointXY(mappt)
        # preview rectangle
        vx, vy = (p2.x() - p1.x(), p2.y() - p1.y())
        L = (vx**2 + vy**2) ** 0.5
        if L == 0:
            return
        nx, ny = -vy / L, vx / L
        wx = p3.x() - p1.x(); wy = p3.y() - p1.y()
        w = wx * nx + wy * ny
        c1 = p1
        c2 = p2
        c3 = QgsPointXY(p2.x() + nx * w, p2.y() + ny * w)
        c4 = QgsPointXY(p1.x() + nx * w, p1.y() + ny * w)
        tmp = [c1, c2, c3, c4]
        self._update_rb(tmp)

class ObjektiUI:
    """Drop-down button 'Crtanje objekta' with multiple drawing modes and digitize-from-selected."""
    def __init__(self, core):
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        act_3pt = QAction(_load_icon('ic_object_3p.svg'), 'Object in 3 points', core.iface.mainWindow())
        def _a3():
            core._obj3 = DrawObject3ptTool(core.iface, core)
            core.iface.mapCanvas().setMapTool(core._obj3)
        act_3pt.triggered.connect(_a3)
        self.menu.addAction(act_3pt); core.actions.append(act_3pt)

        act_n = QAction(_load_icon('ic_object_n.svg'), 'Object in N points', core.iface.mainWindow())
        def _an():
            core._objn = DrawObjectNTool(core.iface, core)
            core.iface.mapCanvas().setMapTool(core._objn)
        act_n.triggered.connect(_an)
        self.menu.addAction(act_n); core.actions.append(act_n)

        act_orth = QAction(_load_icon('ic_object_ortho.svg'), 'Object in N points (90°)', core.iface.mainWindow())
        def _ao():
            core._objo = DrawObjectOrthoTool(core.iface, core)
            core.iface.mapCanvas().setMapTool(core._objo)
        act_orth.triggered.connect(_ao)
        self.menu.addAction(act_orth); core.actions.append(act_orth)

        act_dig = QAction(_load_icon('ic_object_dig.svg'), 'Digitized object (from selection)', core.iface.mainWindow())
        def _ad():
            lyr = core.iface.activeLayer()
            if lyr is None:
                QMessageBox.information(core.iface.mainWindow(), "Object", "Activate a polygon layer and select geometry.")
                return
            sel = getattr(lyr, 'selectedFeatures', lambda: [])()
            if not sel:
                QMessageBox.information(core.iface.mainWindow(), "Objects", "Select one polygon.")
                return
            g = sel[0].geometry()
            if not g or g.type() != QgsWkbTypes.PolygonGeometry:
                QMessageBox.information(core.iface.mainWindow(), "Objects", "A polygon is required.")
                return
            dlg = ObjectPropertiesDialog(core.iface.mainWindow())
            if dlg.exec_() != QDialog.Accepted:
                return
            vals = dlg.values()
            obj = _ensure_objekti_layer(core)
            if not obj: return
            obj.startEditing()
            f = QgsFeature(obj.fields()); f.setGeometry(g)
            for k,v in vals.items():
                try:
                    idx = obj.fields().indexFromName(k); f.setAttribute(idx, v)
                except Exception: pass
            obj.addFeature(f); obj.commitChanges()
            _stylize_objekti_layer(obj)
            core.iface.layerTreeView().setCurrentLayer(obj)
        act_dig.triggered.connect(_ad)
        self.menu.addAction(act_dig); core.actions.append(act_dig)

        # Toolbar drop-down button
        btn = QToolButton(core.iface.mainWindow())
        try: btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        except Exception: pass
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setMenu(self.menu)
        btn.setIcon(_load_icon('ic_drawing_object.svg'))
        btn.setToolTip('Drawing object')
        btn.setStatusTip('Drawing object')
        try:
            core.toolbar.addWidget(btn)
        except Exception:
            # fallback
            act_root = QAction(_load_icon('ic_drawing_object.svg'), 'Drawing object', core.iface.mainWindow())
            act_root.setMenu(self.menu)
            core.iface.addToolBarIcon(act_root)
            core.actions.append(act_root)



try:
    from qgis.PyQt.QtCore import Qt, QSize
    from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox, QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget
    from qgis.PyQt.QtGui import QIcon, QPixmap, QCursor
    from qgis.core import QgsProject, QgsFeature, QgsGeometry, QgsPointXY, QgsWkbTypes, QgsVectorLayer, QgsRectangle
    from qgis.gui import QgsMapTool, QgsRubberBand, QgsMapToolIdentify
except Exception:
    pass

def _img_key(layer, fid):
    return f"image_map/{layer.id()}/{int(fid)}"

def _img_get(layer, fid):
    try:
        return QgsProject.instance().readEntry("StuboviPlugin", _img_key(layer, fid), "")[0]
    except Exception:
        return ""

def _img_set(layer, fid, path):
    try:
        QgsProject.instance().writeEntry("StuboviPlugin", _img_key(layer, fid), path or "")
    except Exception:
        pass

class _ImagePopup(QDialog):
    def __init__(self, path, parent=None, title="FiberQ Image"):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        scr = QScrollArea(self)
        scr.setWidgetResizable(True)
        cont = QWidget()
        scr.setWidget(cont)
        lay2 = QVBoxLayout(cont)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        pm = QPixmap(path)
        if not pm or pm.isNull():
            lbl.setText(f"I can't load the image.:\n{path}")
        else:
            # scale down if huge
            maxw, maxh = 800, 600
            if pm.width() > maxw or pm.height() > maxh:
                pm = pm.scaled(maxw, maxh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl.setPixmap(pm)
        lay2.addWidget(lbl)
        lay.addWidget(scr)

        # veliko dugme za zatvaranje
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close)


class FiberQSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("FiberQ Settings")
        self.settings = QgsSettings()

        layout = QVBoxLayout()

        # Default cable type
        self.cb_default_cable = QComboBox()
        self.cb_default_cable.addItems([
            "Optical – 12F", "Optical – 24F", "Optical – 48F",
            "Optical – 96F", "Optical – 144F"
        ])

        saved = self.settings.value("FiberQ/default_cable_type", "", type=str)
        if saved:
            idx = self.cb_default_cable.findText(saved)
            if idx >= 0:
                self.cb_default_cable.setCurrentIndex(idx)

        layout.addWidget(QLabel("Default Cable Type:"))
        layout.addWidget(self.cb_default_cable)

        # Default slack length (m)
        self.ed_slack = QLineEdit()
        self.ed_slack.setPlaceholderText("10")
        self.ed_slack.setText(self.settings.value("FiberQ/default_slack_length", "10"))
        layout.addWidget(QLabel("Default Slack Length (m):"))
        layout.addWidget(self.ed_slack)

        # Default snapping distance (px)
        self.ed_snap = QLineEdit()
        self.ed_snap.setPlaceholderText("15")
        self.ed_snap.setText(self.settings.value("FiberQ/default_snap_distance", "15"))
        layout.addWidget(QLabel("Default Snapping Distance (px):"))
        layout.addWidget(self.ed_snap)

        # Auto labels
        self.chk_labels = QCheckBox("Enable automatic labels")
        self.chk_labels.setChecked(
            self.settings.value("FiberQ/auto_labels", "true") == "true"
        )
        layout.addWidget(self.chk_labels)

        # Default semantic diagram style
        self.cb_semantic = QComboBox()
        self.cb_semantic.addItems(["Classic", "Compact", "Detailed"])
        saved_style = self.settings.value("FiberQ/default_semantic_style", "Classic")
        idx = self.cb_semantic.findText(saved_style)
        if idx >= 0:
            self.cb_semantic.setCurrentIndex(idx)

        layout.addWidget(QLabel("Default Semantic Diagram Style:"))
        layout.addWidget(self.cb_semantic)

        # Save button
        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self.save)
        layout.addWidget(btn_save)

        self.setLayout(layout)

    def save(self):
        self.settings.setValue("FiberQ/default_cable_type", self.cb_default_cable.currentText())
        self.settings.setValue("FiberQ/default_slack_length", self.ed_slack.text())
        self.settings.setValue("FiberQ/default_snap_distance", self.ed_snap.text())
        self.settings.setValue("FiberQ/auto_labels", "true" if self.chk_labels.isChecked() else "false")
        self.settings.setValue("FiberQ/default_semantic_style", self.cb_semantic.currentText())
        self.accept()

from collections import Counter
from qgis.gui import QgsMapToolIdentify
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsVectorLayer, QgsWkbTypes

class BranchInfoTool(QgsMapToolIdentify):
    """Klik na kabl → info o broju kablova, tipu/kapacitetu i dužini u message baru."""

    def __init__(self, core):
        super().__init__(core.iface.mapCanvas())
        self.core = core
        self.iface = core.iface
        self.setCursor(Qt.PointingHandCursor)

    def _attr(self, f, names, default=""):
        """Vrati prvo popunjeno polje iz liste naziva."""
        try:
            field_names = f.fields().names()
        except Exception:
            field_names = []
        for n in names:
            if n in field_names:
                v = f[n]
                if v not in (None, ""):
                    return v
        return default

    def canvasReleaseEvent(self, e):
        # Desni klik = izlaz iz alata
        if e.button() == Qt.RightButton:
            try:
                self.iface.mapCanvas().unsetMapTool(self)
            except Exception:
                pass
            return

        if e.button() != Qt.LeftButton:
            return

        # Identifikuj objekte ispod klika
        hits = self.identify(e.x(), e.y(), self.TopDownAll, self.VectorLayer)

        cable_hits = []
        for h in hits or []:
            lyr = h.mLayer
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                    name = (lyr.name() or "").lower().strip()
                    # Prihvatamo i stara i nova imena kablovskih slojeva
                    if name in (
                        "kablovi_podzemni",
                        "kablovi_vazdusni",
                        "underground cables",
                        "aerial cables",
                    ):
                        cable_hits.append(h)
            except Exception:
                pass


        if not cable_hits:
            self.iface.messageBar().pushInfo("Branch info", "No cables at this location.")
            return

        feats = [h.mFeature for h in cable_hits]
        total_len = 0.0
        by_type = Counter()

        for f in feats:
            tip = self._attr(f, ["tip", "Tip", "TIP"], "n/a")
            br_c = self._attr(f, ["broj_cevcica", "cevi"], "")
            br_v = self._attr(f, ["broj_vlakana", "vlakna"], "")
            cap = f"{br_c}x{br_v}" if br_c or br_v else ""
            key = f"{tip} {cap}".strip() or "unknown"
            by_type[key] += 1

            try:
                geom = f.geometry()
                if geom:
                    total_len += float(geom.length())
            except Exception:
                pass

        parts = [f"{cnt}× {k}" for k, cnt in by_type.items()]
        msg = f"Cables at click: {len(feats)}"
        if parts:
            msg += " | " + "; ".join(parts)
        if total_len > 0:
            msg += f" | Length of those segments: {total_len:.0f} m ({total_len/1000.0:.2f} km)"
        self.iface.messageBar().pushInfo("Branch info", msg)

    def keyPressEvent(self, e):
        # ESC = izlaz
        try:
            if e.key() == Qt.Key_Escape:
                self.iface.mapCanvas().unsetMapTool(self)
        except Exception:
            pass



class OpenImageMapTool(QgsMapToolIdentify):
    """Click an element to open its attached image (jpg/png) in a popup."""
    def __init__(self, core):
        super().__init__(core.iface.mapCanvas())
        self.core = core
        self.setCursor(Qt.PointingHandCursor)

    def canvasReleaseEvent(self, e):
        res = self.identify(e.x(), e.y(), self.TopDownAll, self.VectorLayer)
        for hit in res or []:
            layer = hit.mLayer
            fid = hit.mFeature.id()
            path = _img_get(layer, fid)
            if path:
                dlg = _ImagePopup(path, self.core.iface.mainWindow(), title="Element picture")
                dlg.exec_()
                return
        QMessageBox.information(self.core.iface.mainWindow(), "FiberQ", "No image is attached to the selected element.")

class MoveFeatureTool(QgsMapTool):
    """Select a feature by click, preview translation with a rubber band, left-click to place; right-click to cancel."""
    def __init__(self, iface):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.layer = None
        self.orig_feat = None
        self.orig_geom = None
        self.anchor = None
        self.rb = None
        self.dragging = False
        self.setCursor(QCursor(Qt.OpenHandCursor))

    def deactivate(self):
        self._clear()
        super().deactivate()

    def _clear(self):
        try:
            if self.rb:
                self.rb.reset(QgsWkbTypes.PolygonGeometry)
                self.canvas.scene().removeItem(self.rb)
        except Exception:
            pass
        self.rb = None
        self.orig_feat = None
        self.orig_geom = None
        self.anchor = None
        self.dragging = False

    def canvasPressEvent(self, e):
        if e.button() == Qt.RightButton:
            # cancel
            self._clear()
            try:
                self.canvas.unsetMapTool(self)
            except Exception:
                pass
            self.iface.messageBar().pushInfo("Moving", "Command aborted (ESC or right click).")
            return
        if self.dragging:
            # Confirm placement
            self._apply_move(e.mapPoint())
            return
        # Identify topmost feature
        from qgis.gui import QgsMapToolIdentify
        ident = QgsMapToolIdentify(self.canvas)
        res = ident.identify(e.x(), e.y(), ident.TopDownAll, ident.VectorLayer)
        if not res:
            self.iface.messageBar().pushInfo("Moving", "No element at this position.")
            return
        hit = res[0]
        self.layer = hit.mLayer
        f = hit.mFeature
        if not isinstance(self.layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning("Moving", "Layer is not vector.")
            return
        self.orig_feat = f
        self.orig_geom = QgsGeometry(f.geometry())
        self.anchor = e.mapPoint()
        # Rubber band
        try:
            self.rb = QgsRubberBand(self.canvas, self.layer.geometryType())
            self.rb.setWidth(2)
            self.rb.setColor(QColor(59,130,246,100))  # blue-ish, semi
        except Exception:
            self.rb = None
        self.dragging = True
        self.setCursor(QCursor(Qt.ClosedHandCursor))


    def keyPressEvent(self, e):
        try:
            from qgis.PyQt.QtCore import Qt as _Qt
            if e.key() == _Qt.Key_Escape:
                self._clear()
                try:
                    self.canvas.unsetMapTool(self)
                except Exception:
                    pass
                self.iface.messageBar().pushInfo("Moving", "Command cancelled (ESC).")
        except Exception:
            pass
    def canvasMoveEvent(self, e):
        if not self.dragging or not self.orig_geom:
            return
        p = e.mapPoint()
        dx = p.x() - self.anchor.x()
        dy = p.y() - self.anchor.y()
        geom = QgsGeometry(self.orig_geom)
        try:
            geom.translate(dx, dy)
        except Exception:
            # fallback manual translate
            try:
                geom = QgsGeometry.fromWkt(self.orig_geom.asWkt())
                geom.translate(dx, dy)
            except Exception:
                return
        if self.rb:
            try:
                self.rb.setToGeometry(geom, self.layer)
            except Exception:
                pass

    def _apply_move(self, p):
        dx = p.x() - self.anchor.x()
        dy = p.y() - self.anchor.y()
        new_geom = QgsGeometry(self.orig_geom)
        try:
            new_geom.translate(dx, dy)
        except Exception:
            pass
        lyr = self.layer
        if not lyr.isEditable():
            lyr.startEditing()
        ok = lyr.changeGeometry(self.orig_feat.id(), new_geom)
        if ok:
            lyr.triggerRepaint()
            self.iface.messageBar().pushSuccess("Moving", "Element is moved.")
        else:
            self.iface.messageBar().pushWarning("Moving", "Cannot change geometry.")
        self._clear()
        self.setCursor(QCursor(Qt.OpenHandCursor))
        try:
            self.canvas.unsetMapTool(self)
        except Exception:
            pass

# Bind helper methods to the core plugin object
def _ui_import_image(self):
    # 1) require selection
    layer = self.iface.activeLayer()
    if not layer or layer.selectedFeatureCount() == 0:
        QMessageBox.information(self.iface.mainWindow(), "FiberQ", "Select one or more elements and try again.")
        return
    feats = layer.selectedFeatures()
    # 2) choose image
    path, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(), "Choose image", "", "Images (*.jpg *.jpeg *.png *.gif);;All files (*.*)")
    if not path:
        return
    # 3) store mapping on each selected feature
    for f in feats:
        _img_set(layer, f.id(), path)
    QMessageBox.information(self.iface.mainWindow(), "FiberQ", f"Image linked to {len(feats)} element(s).")
    # 4) switch to click-to-open tool
    try:
        self._open_img_tool
    except AttributeError:
        self._open_img_tool = OpenImageMapTool(self)
    self.iface.mapCanvas().setMapTool(self._open_img_tool)
    self.iface.messageBar().pushInfo("Image", "Click on an element to open its image (ESC to exit).")

def _ui_clear_image(self):
    # 1) zahtevaj selekciju
    layer = self.iface.activeLayer()
    if not layer or layer.selectedFeatureCount() == 0:
        QMessageBox.information(
            self.iface.mainWindow(),
            "FiberQ",
            "Select one or more elements and try again."
        )
        return

    feats = layer.selectedFeatures()

    # 2) obriši link na sliku (prazan string u project settings)
    for f in feats:
        _img_set(layer, f.id(), "")

    QMessageBox.information(
        self.iface.mainWindow(),
        "FiberQ",
        f"Image link removed for {len(feats)} element(s)."
    )


def _ui_move_elements(self):
    try:
        self._move_tool
    except AttributeError:
        self._move_tool = MoveFeatureTool(self.iface)
    self.iface.mapCanvas().setMapTool(self._move_tool)
    self.iface.messageBar().pushInfo("Move", "Click on an element, move the mouse and confirm with left click (right click to cancel).")

# Attach methods to class (if available) so they survive reloads
try:
    if 'FiberQPlugin' in globals():
        setattr(FiberQPlugin, 'ui_import_image', _ui_import_image)
        setattr(FiberQPlugin, 'ui_clear_image', _ui_clear_image)
        setattr(FiberQPlugin, 'ui_move_elements', _ui_move_elements)
except Exception:
    pass

# Extend initGui to add two new actions
def _initGui_add_move_and_image(self):
    # chain previous
    try:
        if hasattr(self, '_initGui_prev'):
            self._initGui_prev()
        else:
            try:
                super(type(self), self).initGui()
            except Exception:
                pass
    except Exception:
        pass

    try:
        # Pomeranje elemenata
        self.action_move_elements = QAction(_load_icon('ic_move_elements.svg'), 'Move elements', self.iface.mainWindow())
        self.action_move_elements.setToolTip('Move elements on the map (click-move-click)')
        self.action_move_elements.triggered.connect(self.ui_move_elements)
        # Import picture
        self.action_import_image = QAction(_load_icon('ic_import_picture.svg'), 'Import picture to element', self.iface.mainWindow())
        self.action_import_image.setToolTip('Link a .jpg/.png picture to selected element(s)')
        self.action_import_image.triggered.connect(self.ui_import_image)

        # Clear picture
        self.action_clear_image = QAction(_load_icon('ic_import_picture.svg'), 'Clear picture from element', self.iface.mainWindow())
        self.action_clear_image.setToolTip('Unlink picture from selected element(s)')
        self.action_clear_image.triggered.connect(self.ui_clear_image)

        # Add actions to toolbar
        try:
            self.toolbar.addAction(self.action_move_elements)
            self.toolbar.addAction(self.action_import_image)
            self.toolbar.addAction(self.action_clear_image)
        except Exception:
            try:
                self.iface.addToolBarIcon(self.action_move_elements)
                self.iface.addToolBarIcon(self.action_import_image)
            except Exception:
                pass

        # Keep for language toggling
        try:
            self.actions.append(self.action_move_elements)
            self.actions.append(self.action_import_image)
        except Exception:
            pass
    except Exception as e:
        try:
            QMessageBox.warning(self.iface.mainWindow(), "Stubovi", f"Greška pri dodavanju novih dugmadi: {e}")
        except Exception:
            pass

try:
    _cls = globals().get('FiberQPlugin')
    if _cls is not None:
        # Keep previous chain
        if not hasattr(_cls, '_initGui_prev') and hasattr(_cls, 'initGui'):
            _cls._initGui_prev = _cls.initGui
        _cls.initGui = _initGui_add_move_and_image
except Exception:
    pass

from qgis.PyQt.QtCore import QObject, QEvent

class CanvasImageClickWatcher(QObject):
    """Global watcher: on left-click over any element that has an attached image, show popup."""
    def __init__(self, core):
        super().__init__(core.iface.mapCanvas())
        self.core = core

    def eventFilter(self, obj, event):
        try:
            from qgis.gui import QgsMapToolIdentify
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                canvas = self.core.iface.mapCanvas()
                # Don't interfere while our explicit tools are active
                active = canvas.mapTool()
                if active and (active.__class__.__name__ in ("MoveFeatureTool","OpenImageMapTool")):
                    return False
                ident = QgsMapToolIdentify(canvas)
                res = ident.identify(event.x(), event.y(), ident.TopDownAll, ident.VectorLayer)
                for hit in res or []:
                    layer = hit.mLayer
                    fid = hit.mFeature.id()
                    path = _img_get(layer, fid)
                    if path:
                        dlg = _ImagePopup(path, self.core.iface.mainWindow(), title=_fiberq_translate("Open image (click)", _get_lang()))
                        dlg.exec_()
                        # Do not swallow the event; let normal selection continue
                        return False
        except Exception:
            pass
        return False
# === END MOVE & IMAGE ==========================================================
try:
    _cls = globals().get('FiberQPlugin')
    if _cls is not None:
        old_init = getattr(_cls, 'initGui', None)
        def _initGui_with_image_click(self):
            try:
                old_init(self)
            except Exception:
                pass
            try:
                if not hasattr(self, '_img_click_watcher'):
                    self._img_click_watcher = CanvasImageClickWatcher(self)
                    self.iface.mapCanvas().viewport().installEventFilter(self._img_click_watcher)
            except Exception:
                pass
        _cls.initGui = _initGui_with_image_click
except Exception:
    pass




# === AUTO PATCH: bind infrastructure cut activation onto StuboviPlugin ===
try:
    if 'FiberQPlugin' in globals() and 'activate_infrastructure_cut_tool' in globals():
        setattr(StuboviPlugin, 'activate_infrastructure_cut_tool', activate_infrastructure_cut_tool)
except Exception:
    pass
