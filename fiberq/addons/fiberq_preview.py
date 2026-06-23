from qgis.PyQt import QtCore, QtWidgets
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsDataSourceUri,
    QgsFeatureRequest,
    QgsRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsRectangle,
    QgsWkbTypes,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling, QgsTextFormat,
    QgsTextBufferSettings,
    QgsUnitTypes,
    Qgis
)
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsMapToolPan, QgsRubberBand
import os
import configparser
import json
import urllib.parse

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import QgsBlockingNetworkRequest

# Phase 5.3: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


def _http_get_json(url, user_agent, timeout_ms=15000):
    """Perform an http(s) GET using QGIS's native network stack and return parsed JSON.

    v1.2.2: Replaces urllib.request.urlopen to avoid Bandit B310 findings on the
    QGIS repository scan. The URL scheme is still validated defensively before the
    request is issued.
    """
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("Only http/https URLs are allowed")

    request = QNetworkRequest(QUrl(url))
    ua = user_agent.encode("utf-8") if isinstance(user_agent, str) else user_agent
    request.setRawHeader(b"User-Agent", ua)

    blocking = QgsBlockingNetworkRequest()
    try:
        blocking.setTimeout(timeout_ms)
    except Exception:
        pass

    err = blocking.get(request, forceRefresh=True)
    if err != QgsBlockingNetworkRequest.NoError:
        raise RuntimeError(blocking.errorMessage() or "Network request failed")

    reply = blocking.reply()
    payload = bytes(reply.content())
    if not payload:
        return []
    return json.loads(payload.decode("utf-8"))


def _plugin_root_dir():
    """
    Return the base plugin folder (where metadata.txt, main_plugin.py, config.ini are located).
    This file is in subfolder addons/, so we go one level up.
    """
    return os.path.dirname(os.path.dirname(__file__))


def _load_postgis_config():
    """
    Load PostGIS parameters from config.ini file in the plugin root.
    Expects [postgis] section with keys:
        host, port, dbname, user, password, schema
    """
    plugin_dir = _plugin_root_dir()
    cfg_path = os.path.join(plugin_dir, "config.ini")
    if not os.path.exists(cfg_path):
        raise RuntimeError(
            "config.ini file was not found in the plugin folder.\n"
            f"Expected path:\n{cfg_path}"
        )

    cp = configparser.ConfigParser()
    cp.read(cfg_path, encoding="utf-8")
    if "postgis" not in cp:
        raise RuntimeError("The [postgis] section is missing in config.ini.")

    s = cp["postgis"]

    def _get(key, default):
        return s.get(key, default).strip() or default

    params = {
        "host": _get("host", "localhost"),
        "port": _get("port", "5432"),
        "dbname": _get("dbname", ""),
        "user": _get("user", ""),
        "password": _get("password", ""),
        "schema": _get("schema", "fiberq"),
    }
    if not params["dbname"]:
        raise RuntimeError("The [postgis] section is missing dbname.")
    return params


def _get_project_crs():
    """
    Get the CRS from the current QGIS project.
    Falls back to EPSG:3857 if no valid CRS is found.
    """
    try:
        project = QgsProject.instance()
        crs = project.crs()
        if crs and crs.isValid():
            return crs
    except Exception as e:
        logger.debug(f"Error getting project CRS: {e}")

    # Fallback to Web Mercator
    return QgsCoordinateReferenceSystem("EPSG:3857")


class RectSelectTool(QgsMapTool):
    """
    Rectangle selection tool that works in older QGIS versions
    (QgsRectangle doesn't have bottomLeft/topRight, uses xMinimum/yMinimum...).
    """

    def __init__(self, canvas, get_target_layer_callback):
        super().__init__(canvas)
        self.canvas = canvas
        self.get_target_layer = get_target_layer_callback
        self.rubber = None
        self.start_point = None

    def canvasPressEvent(self, event):
        self.start_point = self.toMapCoordinates(event.pos())
        if self.rubber is None:
            self.rubber = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
            self.rubber.setFillColor(QtCore.Qt.GlobalColor.transparent)
            self.rubber.setStrokeColor(QtCore.Qt.GlobalColor.red)
            self.rubber.setWidth(1)
        self._update_rubber_band(self.start_point, self.start_point)
        self.rubber.show()

    def canvasMoveEvent(self, event):
        if not self.start_point or not self.rubber:
            return
        cur = self.toMapCoordinates(event.pos())
        self._update_rubber_band(self.start_point, cur)

    def canvasReleaseEvent(self, event):
        if not self.start_point or not self.rubber:
            return
        end_point = self.toMapCoordinates(event.pos())
        rect = QgsRectangle(self.start_point, end_point)
        layers = self.get_target_layer()  # can be layer or list of layers
        if layers is None:
            layers = []
        elif isinstance(layers, QgsVectorLayer):
            layers = [layers]
        for layer in layers:
            try:
                layer.selectByRect(rect)
            except Exception as e:
                logger.debug(f"Error in RectSelectTool.canvasReleaseEvent: {e}")
        self.rubber.hide()
        self.start_point = None

    def _update_rubber_band(self, p1, p2):
        """
        Set QgsRubberBand to rectangle defined by two points.
        """
        if not self.rubber:
            return
        rect = QgsRectangle(p1, p2)
        x_min = rect.xMinimum()
        x_max = rect.xMaximum()
        y_min = rect.yMinimum()
        y_max = rect.yMaximum()
        points = [
            QgsPointXY(x_min, y_min),
            QgsPointXY(x_min, y_max),
            QgsPointXY(x_max, y_max),
            QgsPointXY(x_max, y_min),
            QgsPointXY(x_min, y_min),
        ]
        self.rubber.reset(QgsWkbTypes.PolygonGeometry)
        for pt in points:
            self.rubber.addPoint(pt, False)
        self.rubber.addPoint(points[0], True)
        self.canvas.refresh()


class PreviewLocatorDialog(QtWidgets.QDialog):
    """
    Small dialog for address locator in preview map.
    Based on main LocatorDialog, but bound to FiberQPreviewDialog.
    """

    def __init__(self, preview_dialog):
        super().__init__(preview_dialog)
        self.preview = preview_dialog
        self.setWindowTitle("Locator")
        self.setMinimumWidth(380)

        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.edit_country = QtWidgets.QLineEdit()
        self.edit_city = QtWidgets.QLineEdit()
        self.edit_municipality = QtWidgets.QLineEdit()
        self.edit_street = QtWidgets.QLineEdit()
        self.edit_number = QtWidgets.QLineEdit()

        form.addRow("Country:", self.edit_country)
        form.addRow("City:", self.edit_city)
        form.addRow("Municipality (optional):", self.edit_municipality)
        form.addRow("Street:", self.edit_street)
        form.addRow("Number:", self.edit_number)
        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_find_clicked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_find_clicked(self):
        # Build query (same as in main LocatorDialog)
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
            QtWidgets.QMessageBox.warning(
                self,
                "Locator",
                "Please enter at least City and Country (Street/Number recommended).",
            )
            return

        query = ", ".join(parts)

        # Nominatim call – uses QGIS-native network stack (B310-safe).
        try:
            url = (
                "https://nominatim.openstreetmap.org/search"
                "?format=json&limit=1&q=" + urllib.parse.quote(query)
            )
            data = _http_get_json(
                url,
                user_agent="FiberQ/1.0 (contact: vukovicvl@fiberq.net; preview-map)",
                timeout_ms=15000,
            )

            if not data:
                QtWidgets.QMessageBox.information(
                    self, "Locator", f"No location found for: {query}"
                )
                return

            lat = float(data[0].get("lat"))
            lon = float(data[0].get("lon"))

            # center PREVIEW canvas (not the main one)
            self.preview._center_and_mark_wgs84(lon, lat)
            self.accept()

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Error during geocoding: {e}"
            )


class FiberQPreviewDialog(QtWidgets.QDialog):
    """
    Preview map dialog for FiberQ plugin.
    Automatically uses the same CRS as the QGIS project for consistency.
    """

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("FiberQ – Preview Map")
        self.resize(1200, 800)

        # Canvas
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QtCore.Qt.GlobalColor.white)

        # AUTO-DETECT CRS FROM PROJECT
        # This ensures Preview Map uses the same CRS as your QGIS project
        self._project_crs = _get_project_crs()

        try:
            self.canvas.setDestinationCrs(self._project_crs)
        except Exception as e:
            logger.debug(f"Error setting canvas CRS: {e}")
            # Fallback
            self._project_crs = QgsCoordinateReferenceSystem("EPSG:3857")
            self.canvas.setDestinationCrs(self._project_crs)

        # Store current CRS for display
        self._current_crs = self._project_crs

        # MapTools
        self.panTool = QgsMapToolPan(self.canvas)
        self.selectTool = RectSelectTool(self.canvas, self._selection_vector_layers)
        self.canvas.setMapTool(self.panTool)

        # Layer list
        self.layersList = QtWidgets.QListWidget()
        self.layersList.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.layersList.itemChanged.connect(self._on_layer_toggled)
        self.layersList.currentItemChanged.connect(self._on_current_layer_changed)

        # Layer filter
        self.layerFilterEdit = QtWidgets.QLineEdit()
        self.layerFilterEdit.setPlaceholderText("Filter layers (e.g. TO, OTB, Route)...")
        self.layerFilterEdit.textChanged.connect(self._on_layer_filter_changed)

        # ID / name locator
        self.searchEdit = QtWidgets.QLineEdit()
        self.searchEdit.setPlaceholderText("Search ID / name...")
        self.searchButton = QtWidgets.QPushButton("Find")

        # Address locator
        self.addressButton = QtWidgets.QPushButton("Address Locator")

        # Basemap selector
        self.basemapCombo = QtWidgets.QComboBox()
        self.basemapCombo.addItem("OSM", "osm")
        self.basemapCombo.addItem("ESRI Satellites", "esri")
        self.basemapCombo.addItem("None (No Basemap)", "none")
        self.basemapCombo.currentIndexChanged.connect(self._on_basemap_changed)
        self._current_basemap_key = "osm"

        # CRS Label - shows current CRS (auto-synced from project)
        self.crsLabel = QtWidgets.QLabel()
        self.crsLabel.setStyleSheet("QLabel { color: #666; font-size: 10px; }")
        self._update_crs_label()

        # Sync CRS button
        self.syncCrsButton = QtWidgets.QPushButton("↻ Sync CRS")
        self.syncCrsButton.setToolTip("Re-sync CRS from QGIS Project")
        self.syncCrsButton.clicked.connect(self._sync_crs_from_project)

        topBar = QtWidgets.QHBoxLayout()
        topBar.addWidget(self.searchEdit)
        topBar.addWidget(self.searchButton)
        topBar.addWidget(self.addressButton)
        topBar.addStretch(1)
        topBar.addWidget(self.crsLabel)
        topBar.addWidget(self.syncCrsButton)
        topBar.addWidget(self.basemapCombo)

        # Buttons
        self.btnPan = QtWidgets.QPushButton("Pan")
        self.btnSelect = QtWidgets.QPushButton("Select")
        self.btnZoomToLayers = QtWidgets.QPushButton("Zoom to layer(s)")
        self.btnRefreshLayers = QtWidgets.QPushButton("Refresh layers")
        self.btnFromProject = QtWidgets.QPushButton("Drawing -> map")
        self.btnToProject = QtWidgets.QPushButton("Map -> drawing")
        self.btnSendToProject = QtWidgets.QPushButton("Load selected layer into project")

        bottomBar = QtWidgets.QHBoxLayout()
        bottomBar.addWidget(self.btnPan)
        bottomBar.addWidget(self.btnSelect)
        bottomBar.addWidget(self.btnZoomToLayers)
        bottomBar.addWidget(self.btnRefreshLayers)
        bottomBar.addWidget(self.btnFromProject)
        bottomBar.addWidget(self.btnToProject)
        bottomBar.addStretch(1)
        bottomBar.addWidget(self.btnSendToProject)

        rightLayout = QtWidgets.QVBoxLayout()
        rightLayout.addLayout(topBar)
        rightLayout.addWidget(self.layerFilterEdit)
        rightLayout.addWidget(self.layersList)
        rightLayout.addLayout(bottomBar)

        mainLayout = QtWidgets.QHBoxLayout(self)
        mainLayout.addWidget(self.canvas, stretch=3)
        mainLayout.addLayout(rightLayout, stretch=1)

        self.previewLayers = {}
        self.baseLayers = []
        self.postgis_params = None

        # Signals
        self.searchButton.clicked.connect(self._on_search_clicked)
        self.addressButton.clicked.connect(self._on_address_locator)
        self.btnSendToProject.clicked.connect(self._send_selected_to_project)
        self.btnPan.clicked.connect(self._set_pan_mode)
        self.btnSelect.clicked.connect(self._set_select_mode)
        self.btnZoomToLayers.clicked.connect(self._zoom_to_selected_layers)
        self.btnRefreshLayers.clicked.connect(self._refresh_layers)
        self.btnFromProject.clicked.connect(self._sync_from_project)
        self.btnToProject.clicked.connect(self._sync_to_project)

        # Load layers
        try:
            self._init_postgis_and_layers()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "FiberQ – Preview Map",
                f"Error connecting to PostGIS:\n{e}",
            )
            self.reject()
            return

        try:
            self._sync_from_project()
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog.__init__: {e}")

    # --- CRS Management ---

    def _update_crs_label(self):
        """Update CRS label to show current CRS."""
        try:
            crs = self._current_crs
            if crs and crs.isValid():
                auth_id = crs.authid()
                if auth_id:
                    self.crsLabel.setText(f"CRS: {auth_id}")
                else:
                    self.crsLabel.setText("CRS: Custom")
            else:
                self.crsLabel.setText("CRS: Unknown")
        except Exception as e:
            logger.debug(f"Error in _update_crs_label: {e}")
            self.crsLabel.setText("CRS: ?")

    def _sync_crs_from_project(self):
        """Re-sync CRS from QGIS project and reload layers."""
        try:
            new_crs = _get_project_crs()

            if new_crs.authid() == self._current_crs.authid():
                QtWidgets.QMessageBox.information(
                    self,
                    "CRS Sync",
                    f"CRS is already synced with project: {new_crs.authid()}"
                )
                return

            # Store current extent
            old_extent = self.canvas.extent()

            # Transform extent to new CRS
            new_extent = None
            try:
                transform = QgsCoordinateTransform(self._current_crs, new_crs, QgsProject.instance())
                new_extent = transform.transformBoundingBox(old_extent)
            except Exception as e:
                logger.debug(f"Could not transform extent: {e}")

            # Update CRS
            self._current_crs = new_crs
            self._project_crs = new_crs
            self.canvas.setDestinationCrs(new_crs)
            self._update_crs_label()

            # Reload layers with new CRS
            self._refresh_layers()

            # Restore extent
            if new_extent and not new_extent.isEmpty():
                self.canvas.setExtent(new_extent)

            self.canvas.refresh()

            QtWidgets.QMessageBox.information(
                self,
                "CRS Synced",
                f"Preview Map CRS synced to project:\n{new_crs.authid()} - {new_crs.description()}"
            )

        except Exception as e:
            logger.debug(f"Error in _sync_crs_from_project: {e}")
            QtWidgets.QMessageBox.critical(
                self,
                "CRS Error",
                f"Error syncing CRS: {e}"
            )

    # --- PostGIS and layers ---

    def _init_postgis_and_layers(self):
        self.postgis_params = _load_postgis_config()
        self._load_preview_layers()
        self._init_id_completer()

    def _build_uri(self, table_name, geom_column="geom"):
        """
        Build PostGIS URI with SRID from project CRS.
        This ensures coordinates are interpreted in the correct CRS.
        """
        p = self.postgis_params
        uri = QgsDataSourceUri()
        uri.setConnection(
            p["host"],
            p["port"],
            p["dbname"],
            p["user"],
            p["password"],
        )
        uri.setDataSource(p["schema"], table_name, geom_column)

        # Set the SRID to match project CRS
        # This tells QGIS to interpret the coordinates in this CRS
        try:
            srid = self._project_crs.postgisSrid()
            if srid and srid > 0:
                uri.setSrid(str(srid))
        except Exception as e:
            logger.debug(f"Could not set SRID in URI: {e}")

        return uri

    def _create_osm_layer(self):
        try:
            uri = (
                "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                "&zmin=0&zmax=19"
            )
            layer = QgsRasterLayer(uri, "OpenStreetMap", "wms")
            if layer.isValid():
                return layer
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._create_osm_layer: {e}")
        return None

    def _load_basemap_urls_from_config(self):
        urls = {
            "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "esri": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            "none": None,
        }
        try:
            plugin_dir = _plugin_root_dir()
            cfg_path = os.path.join(plugin_dir, "config.ini")
            if os.path.exists(cfg_path):
                cp = configparser.ConfigParser()
                cp.read(cfg_path, encoding="utf-8")
                if cp.has_section("basemaps"):
                    sec = cp["basemaps"]
                    osm_url = sec.get("osm_url", "").strip()
                    esri_url = sec.get("esri_url", "").strip()
                    if osm_url:
                        urls["osm"] = osm_url
                    if esri_url:
                        urls["esri"] = esri_url
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._load_basemap_urls_from_config: {e}")
        return urls

    def _create_basemap_layer(self, key: str):
        if key == "none":
            return None
        url_map = self._load_basemap_urls_from_config()
        url = url_map.get(key)
        if not url:
            return None
        try:
            uri = f"type=xyz&url={url}&zmin=0&zmax=19"
            layer = QgsRasterLayer(uri, key, "wms")
            if layer.isValid():
                return layer
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._create_basemap_layer: {e}")
        return None

    def _on_basemap_changed(self, idx: int):
        if not hasattr(self, "basemapCombo"):
            return
        key = self.basemapCombo.itemData(idx)
        if key is None:
            return
        self._current_basemap_key = key

        try:
            current_layers = list(self.canvas.layers())
        except Exception:
            current_layers = []

        base_layers = getattr(self, "baseLayers", [])
        # keep all vector layers, remove old basemap layers
        vector_layers = [lyr for lyr in current_layers if lyr not in base_layers]
        self.baseLayers = []

        if key != "none":
            new_base = self._create_basemap_layer(key)
            if new_base and new_base.isValid():
                self.baseLayers.append(new_base)

        # order as in initial load: vectors + basemap
        visible_layers = vector_layers + list(self.baseLayers)

        if visible_layers:
            try:
                self.canvas.setLayers(visible_layers)
                self.canvas.refresh()
            except Exception as e:
                logger.debug(f"Error in FiberQPreviewDialog._on_basemap_changed: {e}")

    def _load_preview_layers(self):
        layer_defs = [
            ("Route", "Trasa"),
            ("Poles", "Stubovi"),
            ("Manholes", "OKNA"),
            ("ODF", "OR"),
            ("TB", "ZOK"),
            ("PE pipes", "PE cevi"),
            ("Transition pipes", "Prelazne cevi"),
            ("Underground cables", "Kablovi_podzemni"),
            ("Aerial cables", "Kablovi_vazdusni"),
            ("Joint Closures", "Nastavci"),
            ("Fiber break", "Prekid vlakna"),
            ("Service Area", "Rejon"),
            ("Optical slacks", "Opticke_rezerve"),
            ("Patch panel", "Patch panel"),
            ("OTB", "OD ormar"),
            ("Pole OTB", "OD ormar na stubu"),
            ("Outdoor OTB", "Spoljašnji OD ormar"),
            ("Indoor OTB", "Unutrašnji OD ormar"),
            ("TO", "TO Izvod"),
            ("Pole TO", "TO Izvod na stubu"),
            ("Joint Closure TO", "TO Izvod u nastavku"),
            ("Outdoor TO", "Spoljašnji TO Izvod"),
            ("Indoor TO", "Unutrašnji TO Izvod"),
        ]

        STYLE_FILES = {
            "Route": "Route.qml",
            "Poles": "Poles.qml",
            "Manholes": "Manholes.qml",
            "ODF": "ODF.qml",
            "TB": "TB.qml",
            "PE pipes": "PE pipes.qml",
            "Transition pipes": "Transition pipes.qml",
            "Underground cables": "Underground cables.qml",
            "Aerial cables": "Aerial cables.qml",
            "Joint Closures": "Joint Closures.qml",
            "Fiber break": "Fiber break.qml",
            "Service Area": "Service area.qml",
            "Optical slacks": "Optical slacks.qml",
            "Patch panel": "Patch Panel.qml",
            "OTB": "OTB.qml",
            "Pole OTB": "Pole OTB.qml",
            "Outdoor OTB": "Outdoor OTB.qml",
            "Indoor OTB": "Indoor OTB.qml",
            "TO": "TO.qml",
            "Pole TO": "Pole TO.qml",
            "Joint Closure TO": "Joint Closure TO.qml",
            "Outdoor TO": "Outdoor TO.qml",
            "Indoor TO": "Indoor TO.qml",
        }

        LAYER_ICONS = {
            "Route": "ic_create_route.svg",
            "Poles": "ic_add_pole.svg",
            "Manholes": "ic_place_manholes.svg",
            "ODF": "ic_place_odf.svg",
            "TB": "ic_place_tb.svg",
            "PE pipes": "ic_place_pe_pipe.svg",
            "Transition pipes": "ic_place_transition_pipe.svg",
            "Underground cables": "ic_cable_underground.svg",
            "Aerial cables": "ic_cable_aerial.svg",
            "Joint Closures": "ic_place_jc.svg",
            "Fiber break": "ic_fiber_break.svg",
            "Service Area": "ic_service_area.svg",
            "Optical slacks": "ic_slack_midspan.svg",
            "Patch panel": "ic_place_patch_panel.svg",
            "OTB": "ic_place_otb.svg",
            "Pole OTB": "ic_place_pole_otb.svg",
            "Outdoor OTB": "ic_place_outdoor_otb.svg",
            "Indoor OTB": "ic_place_indoor_otb.svg",
            "TO": "ic_place_to.svg",
            "Pole TO": "ic_place_pole_to.svg",
            "Joint Closure TO": "ic_place_joint_closure_to.svg",
            "Outdoor TO": "ic_place_outdoor_to.svg",
            "Indoor TO": "ic_place_indoor_to.svg",
        }

        layers_for_canvas = []

        # Only add basemap if not "none"
        if self._current_basemap_key != "none":
            base = self._create_basemap_layer(self._current_basemap_key)
            if base and base.isValid():
                self.baseLayers.append(base)
                layers_for_canvas.append(base)
            else:
                osm = self._create_osm_layer()
                if osm and osm.isValid():
                    self.baseLayers.append(osm)
                    layers_for_canvas.append(osm)

        proj = QgsProject.instance()  # noqa: F841

        # Load ALL layers directly from PostGIS with project CRS
        for label, table in layer_defs:
            try:
                uri = self._build_uri(table)
                vlayer = QgsVectorLayer(uri.uri(False), label, "postgres")
                if not vlayer.isValid():
                    continue

                # Force layer CRS to match project CRS
                # This is crucial for proper coordinate alignment
                try:
                    vlayer.setCrs(self._project_crs)
                except Exception as e:
                    logger.debug(f"Could not set layer CRS: {e}")

                applied_style = False
                try:
                    style_file = STYLE_FILES.get(label)
                    if style_file:
                        plugin_dir = _plugin_root_dir()
                        qml_path = os.path.join(plugin_dir, "styles", style_file)
                        if os.path.exists(qml_path):
                            vlayer.loadNamedStyle(qml_path)
                            # FORCE label fixes for Preview
                            lname = (label or "").lower()
                            if "aerial" in lname or "underground" in lname:
                                self._apply_preview_cable_labels(vlayer)
                            if "manhole" in lname:
                                self._apply_preview_manhole_labels(vlayer)
                            vlayer.triggerRepaint()
                            applied_style = True
                except Exception:
                    applied_style = False

                if not applied_style:
                    try:
                        vlayer.loadDefaultStyle()
                    except Exception as e:
                        logger.debug(f"Error in FiberQPreviewDialog._load_preview_layers: {e}")
                self.previewLayers[label] = vlayer
                layers_for_canvas.append(vlayer)

                item = QtWidgets.QListWidgetItem(label)
                icon_name = LAYER_ICONS.get(label)
                if icon_name:
                    icon_path = os.path.join(_plugin_root_dir(), "icons", icon_name)
                    if os.path.exists(icon_path):
                        try:
                            item.setIcon(QIcon(icon_path))
                        except Exception as e:
                            logger.debug(f"Error in FiberQPreviewDialog._load_preview_layers: {e}")
                try:
                    fc = vlayer.featureCount()
                    item.setToolTip(f"{label} - {fc} objects")
                except Exception as e:
                    logger.debug(f"Error in FiberQPreviewDialog._load_preview_layers: {e}")
                item.setCheckState(QtCore.Qt.CheckState.Checked)
                self.layersList.addItem(item)

            except Exception:
                continue

        if layers_for_canvas:
            vector_layers = [lyr for lyr in layers_for_canvas if lyr not in self.baseLayers]
            ordered_layers = vector_layers + list(self.baseLayers)
            self.canvas.setLayers(ordered_layers)
            try:
                main_canvas = self.iface.mapCanvas()
                if main_canvas:
                    self.canvas.setExtent(main_canvas.extent())
                else:
                    self.canvas.setExtent(layers_for_canvas[-1].extent())
            except Exception:
                self.canvas.setExtent(layers_for_canvas[-1].extent())
            self.canvas.refresh()
            if "Route" in self.previewLayers:
                self.canvas.setCurrentLayer(self.previewLayers["Route"])

    def _apply_preview_cable_labels(self, layer):
        try:
            s = QgsPalLayerSettings()
            s.enabled = True
            s.isExpression = True
            # Use stored total_len_m or duzina_m, avoid $length which can differ due to CRS
            s.fieldName = (
                "concat("
                "format_number(coalesce(\"total_len_m\", \"duzina_m\", length($geometry)), 0), ' m', '\n', "
                "CASE "
                " WHEN lower(coalesce(attribute($currentfeature,'tip'), attribute($currentfeature,'Tip'), attribute($currentfeature,'TIP'))) LIKE 'optick%' THEN 'Optical' "
                " WHEN lower(coalesce(attribute($currentfeature,'tip'), attribute($currentfeature,'Tip'), attribute($currentfeature,'TIP'))) LIKE 'bakarn%' THEN 'Copper' "
                " ELSE coalesce(attribute($currentfeature,'tip'), attribute($currentfeature,'Tip'), attribute($currentfeature,'TIP')) "
                "END, ' ', "
                "coalesce(attribute($currentfeature,'broj_vlakana'), ''), 'f'"
                ")"
            )

            # Above line (robust across versions)
            try:
                if hasattr(QgsPalLayerSettings, 'LinePlacement') and hasattr(QgsPalLayerSettings.LinePlacement, 'AboveLine'):
                    s.placement = QgsPalLayerSettings.LinePlacement.AboveLine
                elif hasattr(QgsPalLayerSettings, 'Line'):
                    s.placement = QgsPalLayerSettings.Line
            except Exception as e:
                logger.debug(f"Error in FiberQPreviewDialog._apply_preview_cable_labels: {e}")
            tf = QgsTextFormat()
            tf.setSize(8.0)
            tf.setSizeUnit(QgsUnitTypes.RenderMapUnits)

            tf.setColor(QColor(200, 0, 0))

            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.8)
            buf.setColor(QColor(255, 255, 255))
            tf.setBuffer(buf)

            s.setFormat(tf)

            layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
            layer.setLabelsEnabled(True)
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._apply_preview_cable_labels: {e}")

    def _apply_preview_manhole_labels(self, layer):
        try:
            s = QgsPalLayerSettings()
            s.enabled = True
            s.isExpression = True
            s.fieldName = (
                "CASE WHEN length(coalesce(\"broj_okna\", ''))>0 "
                "THEN concat('MH ', \"broj_okna\") ELSE '' END"
            )

            # Offset from point (robust)
            for cand in (
                getattr(Qgis, 'LabelPlacement', None) and getattr(Qgis.LabelPlacement, 'OffsetFromPoint', None),
                getattr(QgsPalLayerSettings, 'OffsetFromPoint', None),
                getattr(QgsPalLayerSettings, 'OverPoint', None),
            ):
                if cand is not None:
                    try:
                        s.placement = cand
                        break
                    except Exception as e:
                        logger.debug(f"Error in FiberQPreviewDialog._apply_preview_manhole_labels: {e}")
            # Small offset above
            try:
                s.xOffset = 0.0
                s.yOffset = 5.0
                s.offsetUnits = QgsUnitTypes.RenderMapUnits
            except Exception as e:
                logger.debug(f"Error in FiberQPreviewDialog._apply_preview_manhole_labels: {e}")
            tf = QgsTextFormat()
            tf.setSize(7.0)
            tf.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            tf.setColor(QColor(0, 0, 0))

            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            try:
                buf.setSizeUnit(QgsUnitTypes.RenderMapUnits)
            except Exception as e:
                logger.debug(f"Error in FiberQPreviewDialog._apply_preview_manhole_labels: {e}")
            buf.setSize(0.8)
            buf.setColor(QColor(255, 255, 255))
            tf.setBuffer(buf)

            s.setFormat(tf)

            layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
            layer.setLabelsEnabled(True)
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._apply_preview_manhole_labels: {e}")

    # --- helpers ---

    def _refresh_layers(self):
        try:
            current_extent = self.canvas.extent()
        except Exception:
            current_extent = None

        try:
            self.layersList.blockSignals(True)
            self.layersList.clear()
        finally:
            self.layersList.blockSignals(False)
        self.previewLayers = {}
        self.baseLayers = []

        try:
            self._load_preview_layers()
            self._init_id_completer()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "FiberQ - Preview Map",
                f"Error refreshing layers from PostGIS database:\n{e}",
            )
            return

        if current_extent is not None:
            try:
                self.canvas.setExtent(current_extent)
                self.canvas.refresh()
            except Exception as e:
                logger.debug(f"Error in FiberQPreviewDialog._refresh_layers: {e}")

    def _on_layer_filter_changed(self, text):
        text = (text or "").strip().lower()
        self.layersList.blockSignals(True)
        try:
            for i in range(self.layersList.count()):
                item = self.layersList.item(i)
                visible = not text or text in item.text().lower()
                item.setHidden(not visible)
        finally:
            self.layersList.blockSignals(False)

    def _zoom_to_selected_layers(self):
        items = self.layersList.selectedItems()
        if not items:
            current = self.layersList.currentItem()
            if current:
                items = [current]

        if not items:
            QtWidgets.QMessageBox.information(
                self, "Zoom", "Select at least one layer in the list."
            )
            return

        bbox = None
        for item in items:
            if item.isHidden():
                continue
            layer = self.previewLayers.get(item.text())
            if not isinstance(layer, QgsVectorLayer):
                continue
            try:
                ext = layer.extent()
            except Exception:
                continue
            if not ext or ext.isEmpty():
                continue
            if bbox is None:
                bbox = QgsRectangle(ext)
            else:
                bbox.combineExtentWith(ext)

        if bbox is None:
            QtWidgets.QMessageBox.information(
                self, "Zoom", "No visible geo-objects for the selected layers."
            )
            return

        try:
            self.canvas.setExtent(bbox)
            self.canvas.refresh()
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._zoom_to_selected_layers: {e}")

    def _current_vector_layer(self):
        item = self.layersList.currentItem()
        if not item:
            return None
        return self.previewLayers.get(item.text())

    def _update_id_completer_for_layer(self, layer):
        if layer is None or not isinstance(layer, QgsVectorLayer):
            self.searchEdit.setCompleter(None)
            return

        fields = {f.name(): f for f in layer.fields()}
        candidate_names = ["id_trase", "ID_trase", "id", "ID", "naziv", "name"]
        field_name = None
        for name in candidate_names:
            if name in fields:
                field_name = name
                break

        if not field_name:
            self.searchEdit.setCompleter(None)
            return

        values = set()
        try:
            for feat in layer.getFeatures():
                v = feat[field_name]
                if v is None:
                    continue
                s = str(v).strip()
                if s:
                    values.add(s)
        except Exception:
            self.searchEdit.setCompleter(None)
            return

        if not values:
            self.searchEdit.setCompleter(None)
            return

        completer = QtWidgets.QCompleter(sorted(values), self)
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        try:
            completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._update_id_completer_for_layer: {e}")
        self.searchEdit.setCompleter(completer)

    def _init_id_completer(self):
        layer = None
        if hasattr(self, "previewLayers") and self.previewLayers:
            layer = self.previewLayers.get("Route")
            if layer is None:
                for lyr in self.previewLayers.values():
                    layer = lyr
                    break
        self._update_id_completer_for_layer(layer)

    def _selection_vector_layers(self):
        layers = []
        items = self.layersList.selectedItems()
        if items:
            for item in items:
                lyr = self.previewLayers.get(item.text())
                if isinstance(lyr, QgsVectorLayer):
                    layers.append(lyr)
        else:
            lyr = self._current_vector_layer()
            if isinstance(lyr, QgsVectorLayer):
                layers.append(lyr)
        return layers

    # --- handlers ---

    def _on_layer_toggled(self, item):
        vector_layers = []
        for i in range(self.layersList.count()):
            it = self.layersList.item(i)
            lyr = self.previewLayers.get(it.text())
            if not lyr:
                continue
            if it.checkState() == QtCore.Qt.CheckState.Checked:
                vector_layers.append(lyr)

        visible_layers = vector_layers + list(self.baseLayers)
        self.canvas.setLayers(visible_layers)
        self.canvas.refresh()

    def _on_current_layer_changed(self, current, previous):
        if not current:
            self._update_id_completer_for_layer(None)
            return
        layer = self.previewLayers.get(current.text())
        if layer:
            self.canvas.setCurrentLayer(layer)
        self._update_id_completer_for_layer(layer)

    def _set_pan_mode(self):
        self.canvas.setMapTool(self.panTool)

    def _set_select_mode(self):
        self.canvas.setMapTool(self.selectTool)

    # --- Locators ---

    def _on_search_clicked(self):
        text_value = self.searchEdit.text().strip()
        if not text_value:
            return

        layer = self._current_vector_layer()
        if not layer:
            layer = self.previewLayers.get("Trasa")

        if not layer:
            QtWidgets.QMessageBox.information(
                self, "Locator", "No vector layer is active in the preview map."
            )
            return

        label = layer.name()

        fields = {f.name(): f for f in layer.fields()}
        candidate_names = ["id_trase", "ID_trase", "id", "ID", "naziv", "name"]
        field_name = None
        for n in candidate_names:
            if n in fields:
                field_name = n
                break

        if not field_name:
            QtWidgets.QMessageBox.information(
                self,
                "Locator",
                f"Cannot find ID/name column in layer '{label}' (id_trase, id, naziv, name...).",
            )
            return

        safe_value = text_value.replace("'", "''")
        expr = '"{}" = \'{}\''.format(field_name, safe_value)

        try:
            req = QgsFeatureRequest().setFilterExpression(expr)
        except Exception:
            QtWidgets.QMessageBox.warning(
                self, "Locator", "Invalid search expression."
            )
            return

        feats = [f for f in layer.getFeatures(req)]
        if not feats:
            QtWidgets.QMessageBox.information(
                self,
                "Locator",
                f"No features found in layer '{label}' for the given ID/name.",
            )
            return

        try:
            layer.removeSelection()
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._on_search_clicked: {e}")
        try:
            layer.selectByIds([f.id() for f in feats])
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._on_search_clicked: {e}")
        bbox = None
        for f in feats:
            g = f.geometry()
            if g is None:
                continue
            gbox = g.boundingBox()
            if bbox is None:
                bbox = QgsRectangle(gbox)
            else:
                bbox.combineExtentWith(gbox)

        if bbox is not None:
            self.canvas.setExtent(bbox)
            self.canvas.refresh()

    def _on_address_locator(self):
        """Open advanced address locator (PreviewLocatorDialog)."""
        dlg = PreviewLocatorDialog(self)
        dlg.exec()

    def _center_and_mark_wgs84(self, lon, lat):
        """
        Move the preview map to the given WGS84 coordinates.
        """
        wgs84 = QgsCoordinateReferenceSystem(4326)

        # Get current canvas CRS
        dest = self._current_crs
        if not dest or not dest.isValid():
            dest = wgs84

        # Transform coordinates to canvas CRS
        try:
            if dest.authid() == "EPSG:4326":
                pt = QgsPointXY(lon, lat)
            else:
                xform = QgsCoordinateTransform(wgs84, dest, QgsProject.instance())
                pt = xform.transform(QgsPointXY(lon, lat))
        except Exception as e:
            # Fallback to raw coordinates
            pt = QgsPointXY(lon, lat)
            logger.debug(f"Error transforming coordinates: {e}")

        try:
            self.canvas.setCenter(pt)
            self.canvas.zoomScale(1500)
            self.canvas.refresh()
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._center_and_mark_wgs84: {e}")

    # --- Export to project ---

    def _send_selected_to_project(self):
        """
        Load selected layers into active QGIS project.
        If there's a selection -> memory layer '(selection)' with those features.
        If no selection -> entire layer.
        """
        items = self.layersList.selectedItems()
        if not items:
            current = self.layersList.currentItem()
            if current:
                items = [current]

        if not items:
            QtWidgets.QMessageBox.warning(
                self, "FiberQ", "Select at least one layer from the list on the right."
            )
            return

        proj = QgsProject.instance()
        any_done = False

        for item in items:
            label = item.text()
            layer = self.previewLayers.get(label)
            if not layer:
                continue

            selected = layer.selectedFeatures()

            if selected:
                wkb_name = QgsWkbTypes.displayString(layer.wkbType())
                crs_auth = self._project_crs.authid() or "EPSG:3857"
                uri = f"{wkb_name}?crs={crs_auth}"
                mem_layer = QgsVectorLayer(uri, f"{label} (Database Layer)", "memory")
                mem_provider = mem_layer.dataProvider()
                mem_provider.addAttributes(layer.fields())
                mem_layer.updateFields()
                mem_provider.addFeatures(selected)

                try:
                    renderer = layer.renderer()
                    if renderer is not None:
                        mem_layer.setRenderer(renderer.clone())
                except Exception as e:
                    logger.debug(f"Error in FiberQPreviewDialog._send_selected_to_project: {e}")
                try:
                    if layer.labelsEnabled():
                        mem_layer.setLabelsEnabled(True)
                        labeling = layer.labeling()
                        if labeling is not None:
                            mem_layer.setLabeling(labeling.clone())
                except Exception as e:
                    logger.debug(f"Error in FiberQPreviewDialog._send_selected_to_project: {e}")
                proj.addMapLayer(mem_layer, addToLegend=True)
                any_done = True
            else:
                proj.addMapLayer(layer, addToLegend=True)
                any_done = True

        if any_done:
            QtWidgets.QMessageBox.information(
                self,
                "FiberQ",
                "Selected layers have been added to the project.\n"
                "Selected features have been extracted into '(selection)' layers.",
            )
        else:
            QtWidgets.QMessageBox.information(
                self,
                "FiberQ",
                "None of the selected layers could be added to the project.",
            )

    def _sync_from_project(self):
        """
        Drawing → map: Sync extent from main QGIS canvas to preview.
        """
        try:
            mc = self.iface.mapCanvas()
            extent = mc.extent()
            self.canvas.setExtent(extent)
            self.canvas.refresh()
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._sync_from_project: {e}")

    def _sync_to_project(self):
        """
        Map → drawing: Sync extent from preview to main QGIS canvas.
        """
        try:
            extent = self.canvas.extent()
            mc = self.iface.mapCanvas()
            mc.setExtent(extent)
            mc.refresh()
        except Exception as e:
            logger.debug(f"Error in FiberQPreviewDialog._sync_to_project: {e}")


def open_preview_dialog(iface):
    """
    Helper function called by main_plugin.py.
    """
    dlg = FiberQPreviewDialog(iface)
    dlg.exec()
