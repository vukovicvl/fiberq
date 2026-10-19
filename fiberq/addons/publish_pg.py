from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QMessageBox
)
from qgis.core import (
    Qgis,
    QgsDataSourceUri,
    QgsFeatureRequest,
    QgsProject,
    QgsProviderConnectionException,
    QgsProviderRegistry,
    QgsVectorLayer,
    QgsVectorLayerExporter,
    QgsWkbTypes,
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

    cp = configparser.ConfigParser(interpolation=None)
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


#: The longest name PostgreSQL keeps, in bytes. It cuts a longer one there itself.
_NAME_BYTES = 63


def _pg_name(name: str) -> str:
    """``name`` as PostgreSQL keeps it: its first 63 bytes, no character cut in half."""
    return name.encode("utf-8")[:_NAME_BYTES].decode("utf-8", "ignore")


def _sanitize_table_name(name: str) -> str:
    """
    Pojednostavljenje i čišćenje imena tabele:
    - zamena razmaka i spec. znakova sa _
    - uklanjanje vodećih/trailing _
    - ako počinje cifrom, dodaj '_' napred
    - pretvaranje u mala slova
    - at most 63 bytes, the most of a name PostgreSQL keeps, with no '_' left at
      the end of the cut: the name shown is the table checked and written, and
      cleaning it a second time changes nothing
    """
    base = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip())
    base = base.strip("_") or "layer_export"
    if base[0].isdigit():
        base = "_" + base
    # Only ASCII is left, so 63 characters are 63 bytes.
    return base.lower()[:_NAME_BYTES].rstrip("_")


#: Names an integer key column usually goes by. Such a field becomes the table's
#: primary key only when every feature holds a different whole number in it.
_KEY_NAMES = ("id", "pk", "gid")


def _holds_distinct_integers(layer: QgsVectorLayer, index: int) -> bool:
    """True when every feature of ``layer`` holds a different integer in field ``index``.

    The features are read through the layer, edit buffer included, because that
    is what the export writes. A NULL fails -- None on QGIS 4, a null QVariant
    on QGIS 3 -- and so does a GeoPackage feature still in the edit buffer,
    whose fid reads 'Autogenerate' until it is saved.
    """
    request = QgsFeatureRequest().setFlags(QgsFeatureRequest.Flag.NoGeometry).setSubsetOfAttributes([index])
    seen = set()
    for feature in layer.getFeatures(request):
        value = feature.attribute(index)
        if not isinstance(value, int) or value in seen:
            return False
        seen.add(value)
    return True


def _choose_pk_field(layer: QgsVectorLayer):
    """The column the PostGIS table gets as its primary key: ``(name, made_by_postgis)``.

    1) An integer field named id, pk or gid (in any case), or else the
       provider's own key such as a GeoPackage fid -- either one only when
       every feature holds a different whole number in it.
    2) Otherwise a name no field of the layer has: id, id_1, id_2, ...
       compared without case, because the export asks QGIS to lowercase field
       names and a field 'ID' would then land on the key column. The postgres
       provider creates that column itself, as a serial primary key numbered
       1 to N.

    The layer is never changed. Any other integer field -- a count, a year, a
    reference to another layer -- is not a key: taking the first one made
    every unsaved FiberQ Cables, Manholes and Optical slacks layer publish 0
    rows, because two of its features held the same value.
    """
    if layer is None or not isinstance(layer, QgsVectorLayer):
        raise RuntimeError("Invalid vector layer provided.")

    fields = layer.fields()
    candidates = [i for i, f in enumerate(fields) if f.name().lower() in _KEY_NAMES]
    own_key = list(layer.primaryKeyAttributes())
    if len(own_key) == 1:
        candidates.append(own_key[0])
    for index in dict.fromkeys(candidates):
        if fields.at(index).type() in (QVariant.Int, QVariant.LongLong) and _holds_distinct_integers(layer, index):
            return fields.at(index).name(), False

    taken = {f.name().lower() for f in fields}
    name, number = "id", 0
    while name in taken:
        number += 1
        name = f"id_{number}"
    return name, True


# ---------------------------------------------------------------------------
# What FiberQ asks the database itself: two SELECTs, nothing else
# ---------------------------------------------------------------------------

class _StatementFailed(Exception):
    """A statement FiberQ ran did not go through. It carries no text: QGIS's
    text of a failed connection is the whole connection string, password
    included."""


def _ident(name: str) -> str:
    """``name`` as an SQL identifier: in double quotes, a double quote inside doubled."""
    return '"' + name.replace('"', '""') + '"'


def _literal(text: str) -> str:
    """``text`` as an SQL string literal: in single quotes, a single quote inside doubled.

    standard_conforming_strings is on by default since PostgreSQL 9.1, and then
    that is all. A text holding a backslash is written E'...' with the backslash
    doubled as well, which reads the same whichever way that setting is.
    """
    quoted = text.replace("'", "''")
    if "\\" in text:
        return "E'" + quoted.replace("\\", "\\\\") + "'"
    return "'" + quoted + "'"


def _connection_uri(pg: dict) -> QgsDataSourceUri:
    """The configured database. QgsDataSourceUri quotes every part itself, so a
    quote, a backslash or a space in a value stays inside it."""
    uri = QgsDataSourceUri()
    uri.setConnection(pg["host"], str(pg["port"]), pg["dbname"], pg["user"], pg["password"],
                      QgsDataSourceUri.decodeSslMode(pg["sslmode"]))
    return uri


def _export_uri(pg: dict, schema: str, table: str, geometry: str, key: str) -> str:
    """The export's destination: ``schema.table`` with ``geometry`` ('' for none) and ``key``."""
    uri = _connection_uri(pg)
    uri.setDataSource(schema, table, geometry, "", key)
    return uri.uri(False)


def _connection(pg: dict):
    """QGIS's own postgres connection to the configured database, which connects
    when a statement runs; None when this QGIS has no postgres provider."""
    metadata = QgsProviderRegistry.instance().providerMetadata("postgres")
    if metadata is None:
        return None
    return metadata.createConnection(_connection_uri(pg).uri(False), {})


def _run(connection, sql: str) -> list:
    """The rows ``sql`` answers on ``connection``; _StatementFailed when it does not run."""
    if connection is None:
        raise _StatementFailed()
    try:
        return connection.executeSql(sql)
    except QgsProviderConnectionException:
        raise _StatementFailed() from None


def _relation_kind(connection, schema: str, name: str):
    """The relkind of ``schema.name`` in pg_class -- a table, a view, a
    partition, an index, any relation -- or None when the name is free."""
    # Both values are SQL literals from _literal.
    rows = _run(connection, "SELECT c.relkind::text FROM pg_catalog.pg_class c"  # nosec B608
                " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
                f" WHERE n.nspname = {_literal(schema)} AND c.relname = {_literal(name)}")
    return str(rows[0][0]) if rows else None


def _row_count(connection, schema: str, name: str) -> int:
    """The number of rows in the table ``schema.name``."""
    # Both names are SQL identifiers from _ident.
    rows = _run(connection, f"SELECT count(*) FROM {_ident(schema)}.{_ident(name)}")  # nosec B608
    return int(rows[0][0])


def _drop_statement(schema: str, name: str) -> str:
    """The statement that removes the table ``schema.name``, for the user to
    run in their database tool. FiberQ never runs it."""
    return f"DROP TABLE {_ident(schema)}.{_ident(name)};"


#: What a relation is, by its relkind, when the name the user chose is taken.
_KINDS = {
    "r": "a table",
    "p": "a partitioned table",
    "v": "a view",
    "m": "a materialized view",
    "f": "a foreign table",
    "S": "a sequence",
    "i": "an index",
    "I": "an index",
    "c": "a composite type",
}

#: QGIS's answers that leave nothing in the database: it could not connect, or
#: its create step -- CREATE TABLE and the geometry column, one transaction --
#: failed and was rolled back. With overwrite off that is also its answer for a
#: name that is taken, by a relation or by a type: it never gets past CREATE
#: TABLE there (measured on 3.22.16 to 4.2.3). After any other answer but
#: Success, the table it had just created is there, incomplete.
_NOTHING_CREATED = (
    Qgis.VectorExportResult.ErrorConnectionFailed,
    Qgis.VectorExportResult.ErrorCreatingLayer,
)

#: A connection string, as libpq and QGIS write one: two or more key=value
#: pairs of their keywords, a value quoted or not.
_CONNECTION_KEYS = (r"(?:dbname|host|hostaddr|port|user|password|passfile|service|authcfg|sslmode|sslcert|sslkey"
                    r"|sslrootcert|connect_timeout|application_name|options|key|table|srid|type|estimatedmetadata"
                    r"|checkPrimaryKeyUnicity|sql)")
_CONNECTION_VALUE = r"(?:'(?:[^'\\]|\\.)*'|\S+)"
_CONNECTION_STRING = re.compile(rf"\b{_CONNECTION_KEYS}\s*=\s*{_CONNECTION_VALUE}"
                                rf"(?:\s+{_CONNECTION_KEYS}\s*=\s*{_CONNECTION_VALUE})+", re.IGNORECASE)
#: A password written alone, quoted or not, and the user:password@ of a postgresql:// URI.
_PASSWORD = re.compile(r"(password\s*=\s*)('(?:[^'\\]|\\.)*'?|\S+)", re.IGNORECASE)
_URI_PASSWORD = re.compile(r"(postgres(?:ql)?://[^:/?#@\s]*:)[^@/?#\s]*@", re.IGNORECASE)


def _scrub(text: str) -> str:
    """``text`` with any connection string in it replaced, and any password
    masked. QGIS's and PostgreSQL's own words are shown to the user as they
    come, and QGIS writes a failed connection with the whole connection
    string, password included."""
    text = _CONNECTION_STRING.sub("[connection string]", text)
    text = _PASSWORD.sub(r"\1********", text)
    return _URI_PASSWORD.sub(r"\1********@", text)


def _count(number: int, noun: str) -> str:
    """``number`` and ``noun``, the noun plural unless the number is 1: '1 feature', '3 features'."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _expected_rows(layer: QgsVectorLayer):
    """What the rows written are checked against: ``(count, estimate)``.

    ``count`` is how many features the export will read: the layer's own count
    when it is exact, and otherwise the features read through the layer now,
    its edit buffer included. A count below zero is QGIS's 'unknown', and a
    PostgreSQL layer with estimated table metadata takes its count from the
    table's statistics -- -1 for a table never analysed, 3 for a table of 7
    once rows were added (measured on 3.22.16 to 4.2.3) -- so neither is a
    count to check against. ``estimate`` is that statistics figure when there
    is one, None otherwise: statistics can be old either way, so fewer rows
    than they say is worth a warning, never an error.
    """
    count = layer.featureCount()
    estimated = layer.providerType() == "postgres" and QgsDataSourceUri(layer.source()).useEstimatedMetadata()
    if count >= 0 and not estimated:
        return count, None
    request = QgsFeatureRequest().setFlags(QgsFeatureRequest.Flag.NoGeometry).setNoAttributes()
    counted = sum(1 for _feature in layer.getFeatures(request))
    return counted, (count if count >= 0 else None)


def _only_copy(schema: str, table: str) -> str:
    """The advice for a table left incomplete: look before removing it."""
    return (f"Check its rows before you remove it in your database tool ({_drop_statement(schema, table)}): if "
            "the layer's source has changed or gone, they may be the only copy of those rows left.")


def _left_behind(connection, schema: str, table: str, expected) -> str:
    """What the user is told about the table a failed export left: '' when there is none.

    With overwrite off QGIS gets past its create step only for a name that was
    free, so a table there now is the one QGIS began. FiberQ does not remove
    it: another session can write into it as soon as QGIS has created it, and
    its rows can be the only copy of rows whose source has gone since.
    """
    target = f"{schema}.{table}"
    remove = _only_copy(schema, table)
    try:
        if _relation_kind(connection, schema, table) is None:
            return ""
        written = _row_count(connection, schema, table)
    except _StatementFailed:
        return f"\n\nQGIS may have created {target} before it failed. If it is there, it is incomplete. {remove}"
    wrote = f"{written} of the layer's {_count(expected, 'feature')}"
    return f"\n\nQGIS had created {target} before it failed, and wrote {wrote} to it: the table is incomplete. {remove}"


class PublishDialog(QDialog):
    """
    Dijalog za objavu vektorskog sloja u PostGIS.

    Koristi isključivo config.ini parametre – korisnik NE bira konekciju,
    već samo:
      - koji sloj
      - ime tabele (i po potrebi šemu)

    Only a new table is ever written. A name the database already has is
    refused, and QGIS is never asked to drop or replace anything.
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
        current = self.cmb_layer.currentIndex()
        default_table = _sanitize_table_name(self.layers[current].name() if self.layers else "layer_export")
        self.le_table = QLineEdit(default_table)
        hschema.addWidget(self.le_table)
        # The Table field follows the Layer combo until the user types a name of
        # their own, and shows the name PostgreSQL will keep once they leave it.
        self._auto_table = default_table
        self.cmb_layer.currentIndexChanged.connect(self._follow_layer)
        self.le_table.editingFinished.connect(self._settle_table)

        lay.addLayout(hschema)

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

    def _follow_layer(self, index):
        """Keep the Table field on the layer picked, unless the user typed a name of their own."""
        if self.le_table.text() != self._auto_table or not 0 <= index < len(self.layers):
            return
        self._auto_table = _sanitize_table_name(self.layers[index].name())
        self.le_table.setText(self._auto_table)

    def _settle_table(self):
        """Put the name PostgreSQL will keep into the Table field, and answer it.

        Run when the user leaves the field and before every export, so the name
        the user sees is the name looked up and written."""
        table = _sanitize_table_name(self.le_table.text())
        if self.le_table.text() != table:
            self.le_table.setText(table)
        return table

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
        if not layer.isValid():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "PostGIS",
                f"Layer '{layer.name()}' is unavailable: QGIS cannot read its data source. "
                "Repair its data source, or pick another layer.",
            )
            return

        schema = _pg_name((self.le_schema.text() or "").strip() or self.pg["schema"])
        table = self._settle_table()
        target = f"{schema}.{table}"

        # FiberQ writes only new tables. A name the database already has -- a
        # table, a view, a partition, an index, any relation -- is refused
        # before anything is sent. When the lookup cannot run, the export goes
        # on: with overwrite off QGIS refuses a taken name by itself, and says why.
        connection = None
        try:
            connection = _connection(self.pg)
            found = _relation_kind(connection, schema, table)
        except (_StatementFailed, QgsProviderConnectionException):
            # Not known to be taken.
            found = None
        if found is not None:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "PostGIS",
                f"Layer '{layer.name()}' was not published: there is already {_KINDS.get(found, 'a relation')} "
                f"{target} in the database. FiberQ writes only new tables, so nothing was written. "
                "Choose another table name.",
            )
            return

        # The table's primary key. The layer itself is never edited for it.
        try:
            pk_field, pk_is_new = _choose_pk_field(layer)
        except Exception as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "PostGIS",
                f"Error preparing primary key (ID column):\n\n{e}",
            )
            return

        # QGIS gives the key column the type of the layer field the key names.
        # With lowercaseFieldNames it finds that field by its lowercased name
        # from 3.34.4 on (qgis/QGIS#56243) and by its own spelling before; a key
        # it does not find becomes a 32-bit serial, which 64-bit values overflow.
        # exportLayer lowercases a shapefile's field names itself, on every
        # version, so a shapefile's key is found by its lowercased name only.
        shapefile = layer.providerType() == "ogr" and layer.storageType() == "ESRI Shapefile"
        uri_key = pk_field.lower() if Qgis.QGIS_VERSION_INT >= 33404 or shapefile else pk_field

        # A layer without geometry gets a table without a geometry column.
        # Named anyway, QGIS created the table without it and then failed to
        # open it. Any other layer keeps the column -- also a GeometryCollection
        # layer, which QGIS does not call spatial (isSpatial() is False for it on
        # 3.22.16 to 4.2.3) although its features have geometries.
        geometry = "" if layer.geometryType() == QgsWkbTypes.GeometryType.NullGeometry else "geom"

        # What the rows written are checked against: the count the layer had
        # when Publish was pressed, before anything could change its source.
        expected, estimate = _expected_rows(layer)

        uri = _export_uri(self.pg, schema, table, geometry, uri_key)
        options = {
            "overwrite": False,
            "lowercaseFieldNames": True,
        }

        # One call that every supported QGIS accepts, 3.22 to 4.2: layer, uri,
        # provider, CRS, onlySelected, options. It raises only on a wrong
        # argument; a failed export comes back as the result, with QGIS's own
        # reason.
        try:
            result, message = QgsVectorLayerExporter.exportLayer(
                layer,
                uri,
                "postgres",
                layer.crs(),
                False,
                options,
            )
        except Exception as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "PostGIS",
                f"Error during export:\n\n{_scrub(str(e))}",
            )
            return

        if result != Qgis.VectorExportResult.Success:
            reason = _scrub((message or "").strip()) or f"QGIS reported {getattr(result, 'name', result)}."
            text = f"Layer '{layer.name()}' was not published to PostGIS as {target}.\n\n{reason}"
            if result not in _NOTHING_CREATED:
                text += _left_behind(connection, schema, table, expected)
            QMessageBox.critical(self.iface.mainWindow(), "PostGIS", text)
            return

        # QGIS answers Success when reading the layer stops part way -- its table
        # dropped by another session, its connection lost -- having written what
        # it had read (measured on 3.22.16 to 4.2.3). So the rows are counted.
        try:
            written = _row_count(connection, schema, table)
        except _StatementFailed:
            written = None

        if written is not None and written < expected:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "PostGIS",
                f"Layer '{layer.name()}' was not published completely to PostGIS as {target}. QGIS reported "
                f"success, but it wrote {written} of the layer's {_count(expected, 'feature')}: the table is "
                f"incomplete. {_only_copy(schema, table)}",
            )
            return

        # The table's column names are lowercase, the key's too.
        key_note = " (new, created and numbered by PostGIS)" if pk_is_new else ""
        published = f"Layer '{layer.name()}' has been published to PostGIS as {target}"
        key_line = f"Used PK column: {pk_field.lower()}{key_note}"
        if written is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "PostGIS",
                f"{published}: QGIS reported success.\n{key_line}\n"
                f"FiberQ could not count the rows written, so check in your database tool that {target} "
                f"holds the layer's {_count(expected, 'feature')}.",
            )
        elif written > expected:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "PostGIS",
                f"{published}, but it holds {_count(written, 'row')} while the layer has {_count(expected, 'feature')}: "
                f"check it in your database tool before you use it.\n{key_line}",
            )
        elif estimate is not None and written < estimate:
            # The layer read fewer features than its table's statistics count:
            # its source may have shrunk or gone before Publish was pressed.
            QMessageBox.warning(
                self.iface.mainWindow(),
                "PostGIS",
                f"{published}, with {_count(written, 'feature')}, but the statistics of the layer's source count "
                f"about {estimate}: check in your database tool that the layer read them all.\n{key_line}",
            )
        else:
            if written == 0:
                count_line = "Features written: 0 (the layer has no features)"
            else:
                count_line = f"Features written: {written} of {expected}"
            QMessageBox.information(
                self.iface.mainWindow(),
                "PostGIS",
                f"{published}.\n{key_line}\n{count_line}",
            )
        self.accept()


def open_publish_dialog(iface):
    dlg = PublishDialog(iface)
    dlg.exec()
