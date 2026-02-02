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


def _plugin_root_dir():
    """
    Return the root folder of the plugin (where metadata.txt, main_plugin.py, config.ini are located).
    This file is in the addons/ subfolder, so we go one level up.
    """
    return os.path.dirname(os.path.dirname(__file__))


def _load_pg_config():
    """
    Load PostGIS parameters from the config.ini file in the plugin root.
    If something is not right, throws an exception with a clear message.
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
    Simplification and cleaning of table name:
    - replace spaces and special chars with _
    - remove leading/trailing _
    - if starts with a digit, add '_' in front
    - convert to lowercase
    """
    base = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip())
    base = base.strip("_") or "layer_export"
    if base[0].isdigit():
        base = "_" + base
    return base.lower()


def _ensure_pk_field(layer: QgsVectorLayer) -> str:
    """
    Ensure that the layer has an integer column that can be used as a primary key
    for export to PostGIS.

    Strategy:
      1) If an integer field named 'id', 'pk' or 'gid' exists -> use it.
      2) Otherwise, if any integer field exists -> use the first such field.
      3) If NONE of that exists -> automatically create a new 'id' column
         (or 'id_1', 'id_2', ... if already exists), populate it with 1..N and return that column name.
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

    # 1) Preferred integer PK (id/pk/gid)
    if pref_candidates:
        return pref_candidates[0].name()

    # 2) Any integer field
    if int_fields:
        return int_fields[0].name()

    # 3) No integer field -> automatically add a new 'id' field
    existing_names = {f.name().lower() for f in fields}
    base_name = "id"
    new_name = base_name
    i = 1
    while new_name.lower() in existing_names:
        new_name = f"{base_name}_{i}"
        i += 1

    # Try to add the field and populate it
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

        # Fill values 1..N
        value = 1
        for feat in layer.getFeatures():
            layer.changeAttributeValue(feat.id(), idx, value)
            value += 1

        if not was_editing:
            if not layer.commitChanges():
                raise RuntimeError("Failed to commit the ID column to the layer.")
    finally:
        # If the layer was in edit mode before, leave it that way - user decides when to save.
        pass

    return new_name


class PublishDialog(QDialog):
    """
    Dialog for publishing a vector layer to PostGIS.

    Uses only config.ini parameters - user does NOT choose the connection,
    only:
      - which layer
      - table name (and schema if needed)
      - whether to delete existing table (overwrite)
    """

    def __init__(self, iface):
        super().__init__(iface.mainWindow(), flags=Qt.Window)
        self.iface = iface
        self.setWindowTitle("Publish to PostGIS")
        self.setModal(True)

        # Loading PG configuration
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

        # Server information
        lbl_info = QLabel()
        if self.pg:
            lbl_info.setText(
                f"Server: {self.pg['host']}:{self.pg['port']}  |  "
                f"Database: {self.pg['dbname']}  |  Schema: {self.pg['schema']}"
            )
        else:
            lbl_info.setText("Error: no valid PostGIS configuration (config.ini).")
        lay.addWidget(lbl_info)

        # Layer selection
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

        # By default select the active layer if it exists
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

        # Overwrite option
        self.chk_overwrite = QCheckBox("Delete existing table and recreate (overwrite)")
        self.chk_overwrite.setChecked(True)
        lay.addWidget(self.chk_overwrite)

        # Buttons
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

        # Ensure the layer has an integer primary key
        try:
            pk_field = _ensure_pk_field(layer)
        except Exception as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "PostGIS",
                f"Error preparing primary key (ID column):\n\n{e}",
            )
            return

        # Prepare URI string for PostGIS export
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

        # Execute export - we only catch TRUE errors (exceptions).
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
            # Fallback for older QGIS versions
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

        # If we didn't get an exception, we treat it as success.
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
    dlg.exec_()
