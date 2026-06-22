from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QCheckBox, QPushButton, QMessageBox
)
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsVectorLayerExporter,
    QgsField,
)
import os
import re
import configparser

# Phase 5.3: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


def _plugin_root_dir():
    """
    Vrati osnovni folder plugina (gde se nalaze metadata.txt, main_plugin.py, config.ini...).
    Ovaj fajl je u podfolderu addons/, zato idemo jedan nivo iznad.
    """
    return os.path.dirname(os.path.dirname(__file__))


def _load_pg_config():
    """
    Učita PostGIS parametre iz config.ini fajla u korenu plugina.
    Ako nešto nije kako treba, baca izuzetak sa jasnom porukom.
    """
    plugin_dir = _plugin_root_dir()
    cfg_path = os.path.join(plugin_dir, "config.ini")
    if not os.path.exists(cfg_path):
        raise RuntimeError(
            "config.ini file not found in the plugin folder.\n"
            f"Expected path:\n{cfg_path}"
        )

    cp = configparser.ConfigParser()
    cp.read(cfg_path, encoding="utf-8")
    if "postgis" not in cp:
        raise RuntimeError("The [postgis] section is missing in config.ini.")

    s = cp["postgis"]

    def _get(key, default):
        return s.get(key, default).strip() or default

    return {
        "host": _get("host", "localhost"),
        "port": _get("port", "5433"),
        "dbname": _get("dbname", "gis"),
        "user": _get("user", "gis"),
        "password": _get("password", "gis"),
        "schema": _get("schema", "public"),
        "sslmode": _get("sslmode", "disable"),
    }


def _sanitize_table_name(name: str) -> str:
    """
    Pojednostavljenje i čišćenje imena tabele:
    - zamena razmaka i spec. znakova sa _
    - uklanjanje vodećih/trailing _
    - ako počinje cifrom, dodaj '_' napred
    - pretvaranje u mala slova
    """
    base = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip())
    base = base.strip("_") or "layer_export"
    if base[0].isdigit():
        base = "_" + base
    return base.lower()


def _ensure_pk_field(layer: QgsVectorLayer) -> str:
    """
    Osiguraj da sloj ima neku integer kolonu koja se može koristiti kao primarni ključ
    za export u PostGIS.

    Strategija:
      1) Ako postoji integer polje sa imenom 'id', 'pk' ili 'gid' → koristi njega.
      2) Inače, ako postoji bilo koje integer polje → koristi prvo takvo.
      3) Ako NIŠTA od toga ne postoji → automatski kreiraj novu kolonu 'id'
         (ili 'id_1', 'id_2', ... ako već postoji), popuni je 1..N i vrati ime te kolone.
    """
    if layer is None or not isinstance(layer, QgsVectorLayer):
        raise RuntimeError("Invalid vector layer provided.")

    fields = layer.fields()
    int_fields = []
    pref_candidates = []

    for f in fields:
        if f.type() in (QVariant.Int, QVariant.LongLong):
            int_fields.append(f)
            name_low = f.name().lower()
            if name_low in ("id", "pk", "gid"):
                pref_candidates.append(f)

    # 1) Preferirani integer PK (id/pk/gid)
    if pref_candidates:
        return pref_candidates[0].name()

    # 2) Bilo koji integer field
    if int_fields:
        return int_fields[0].name()

    # 3) Nema integer polja → automatski dodaj novo 'id' polje
    existing_names = {f.name().lower() for f in fields}
    base_name = "id"
    new_name = base_name
    i = 1
    while new_name.lower() in existing_names:
        new_name = f"{base_name}_{i}"
        i += 1

    # Try to add field and populate it
    was_editing = layer.isEditable()
    if not was_editing:
        if not layer.startEditing():
            raise RuntimeError("I can't start editing the layer to add the ID column.")

    try:
        pr = layer.dataProvider()
        fld = QgsField(new_name, QVariant.Int)
        if not pr.addAttributes([fld]):
            raise RuntimeError("I can't add the ID column to the layer.")
        layer.updateFields()

        idx = layer.fields().indexFromName(new_name)
        if idx < 0:
            raise RuntimeError("I can't find the newly added ID column.")

        # Popuni vrednosti 1..N
        value = 1
        for feat in layer.getFeatures():
            layer.changeAttributeValue(feat.id(), idx, value)
            value += 1

        if not was_editing:
            if not layer.commitChanges():
                raise RuntimeError("Failed to commit the ID column to the layer.")
    finally:
        # If layer was in edit mode before, leave it - user decides when to save.
        pass

    return new_name


class PublishDialog(QDialog):
    """
    Dijalog za objavu vektorskog sloja u PostGIS.

    Koristi isključivo config.ini parametre – korisnik NE bira konekciju,
    već samo:
      - koji sloj
      - ime tabele (i po potrebi šemu)
      - da li da obriše postojeću tabelu (overwrite)
    """

    def __init__(self, iface):
        super().__init__(iface.mainWindow(), flags=Qt.WindowType.Window)
        self.iface = iface
        self.setWindowTitle("Publish to PostGIS")
        self.setModal(True)

        # Load PG configuration
        try:
            self.pg = _load_pg_config()
        except Exception as e:
            self.pg = None
            QMessageBox.critical(
                iface.mainWindow(),
                "PostGIS configuration",
                f"Error reading config.ini:\n\n{e}",
            )

        lay = QVBoxLayout(self)

        # Informacija o serveru
        lbl_info = QLabel()
        if self.pg:
            lbl_info.setText(
                f"Server: {self.pg['host']}:{self.pg['port']}  |  "
                f"Database: {self.pg['dbname']}  |  Schema: {self.pg['schema']}"
            )
        else:
            lbl_info.setText("Error: no valid PostGIS configuration (config.ini).")
        lay.addWidget(lbl_info)

        # Izbor sloja
        hlayer = QHBoxLayout()
        hlayer.addWidget(QLabel("Layer:"))
        self.cmb_layer = QComboBox()
        self.layers = []

        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer):
                self.layers.append(lyr)
                self.cmb_layer.addItem(lyr.name())

        hlayer.addWidget(self.cmb_layer, 1)
        lay.addLayout(hlayer)

        # Podrazumevano selektuj aktivni sloj ako postoji
        active = iface.activeLayer()
        if active is not None:
            for idx, lyr in enumerate(self.layers):
                if lyr == active:
                    self.cmb_layer.setCurrentIndex(idx)
                    break

        # Schema and table
        hschema = QHBoxLayout()
        hschema.addWidget(QLabel("Schema:"))
        default_schema = self.pg["schema"] if self.pg else "public"
        self.le_schema = QLineEdit(default_schema)
        hschema.addWidget(self.le_schema)

        hschema.addWidget(QLabel("Table:"))
        default_table = _sanitize_table_name(active.name() if active else "layer_export")
        self.le_table = QLineEdit(default_table)
        hschema.addWidget(self.le_table)

        lay.addLayout(hschema)

        # Overwrite opcija
        self.chk_overwrite = QCheckBox("Delete existing table and recreate (overwrite)")
        self.chk_overwrite.setChecked(True)
        lay.addWidget(self.chk_overwrite)

        # Dugmad
        hbtn = QHBoxLayout()
        hbtn.addStretch(1)
        btn_ok = QPushButton("Publish")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self._do_export)
        btn_cancel.clicked.connect(self.reject)
        hbtn.addWidget(btn_ok)
        hbtn.addWidget(btn_cancel)
        lay.addLayout(hbtn)

    def _do_export(self):
        if not self.pg:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "PostGIS",
                "No valid PostGIS configuration (config.ini).",
            )
            return

        if not self.layers:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "PostGIS",
                "No vector layers in the project.",
            )
            return

        idx_layer = self.cmb_layer.currentIndex()
        if idx_layer < 0 or idx_layer >= len(self.layers):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "PostGIS",
                "No layer selected.",
            )
            return

        layer = self.layers[idx_layer]

        schema = (self.le_schema.text() or "").strip() or self.pg["schema"]
        table_raw = (self.le_table.text() or "").strip()
        table = _sanitize_table_name(table_raw)

        if not table:
            table = "layer_export"

        # Ensure layer has integer primary key
        try:
            pk_field = _ensure_pk_field(layer)
        except Exception as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "PostGIS",
                f"Error preparing primary key (ID column):\n\n{e}",
            )
            return

        # Priprema URI stringa za PostGIS export
        uri = (
            f"dbname='{self.pg['dbname']}' "
            f"host={self.pg['host']} "
            f"port={self.pg['port']} "
            f"user='{self.pg['user']}' "
            f"password='{self.pg['password']}' "
            f"sslmode={self.pg['sslmode']} "
            f'table="{schema}"."{table}" (geom) '
            f"key='{pk_field}'"
        )

        overwrite = bool(self.chk_overwrite.isChecked())
        options = {
            "overwrite": overwrite,
            "lowercaseFieldNames": True,
        }

        # Execute export - catch only REAL errors (exceptions).
        try:
            QgsVectorLayerExporter.exportLayer(
                layer,
                uri,
                "postgres",
                layer.crs(),
                False,
                None,
                options,
                None,
            )
        except TypeError:
            # Fallback za starije verzije QGIS-a
            try:
                QgsVectorLayerExporter.exportLayer(
                    layer,
                    uri,
                    "postgres",
                    layer.crs(),
                )
            except Exception as e:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "PostGIS",
                    f"Error during export (fallback):\n\n{e}",
                )
                return
        except Exception as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "PostGIS",
                f"Error during export:\n\n{e}",
            )
            return

        # Ako nismo dobili exception, tretiramo kao uspeh.
        QMessageBox.information(
            self.iface.mainWindow(),
            "PostGIS",
            f"Layer '{layer.name()}' has been published to PostGIS as {schema}.{table}.\n"
            f"Used PK column: {pk_field}\n"
            "Check in pgAdmin if the table is visible.",
        )
        self.accept()


def open_publish_dialog(iface):
    dlg = PublishDialog(iface)
    dlg.exec()
