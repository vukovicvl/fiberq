"""Publish to PostGIS: the table's primary key, the table written, and what the user is told.

WP4 item U11, branch ``refactor/v160-cleanup``. Unclaimed: the PostGIS bridge is
pre-award code, and the Pro prompt in front of the dialog is not touched here.

The key. ``_ensure_pk_field`` took an integer field named id, pk or gid, else
the first integer field of any kind, else it added an ``id`` column to the
layer being published and saved it there. Both fallbacks were wrong:

- The first integer field of an unsaved FiberQ layer is a count, a year or a
  reference -- ``broj_cevcica`` on Cables, ``god_ugrad`` on Manholes,
  ``cable_fid`` on Optical slacks. Against a real PostGIS the export wrote
  0 rows: the second feature holding the same value broke the primary key.
- Adding the column changed the user's data, and the change stayed when the
  publish failed: a shapefile's .dbf on disk gained it, and a layer already in
  edit mode kept an empty column that rolling back did not remove.

Now the key is the layer's own -- an id/pk/gid field, or the provider's key such
as a GeoPackage fid, either one only when every feature holds a different whole
number -- or else a name the layer does not have in any case, which the
postgres provider creates itself as a serial key. The layer is never changed.

The export. ``exportLayer`` was called with eight arguments. No QGIS from 3.22
to 4.2 has that signature, so the call raised TypeError every time and a
fallback ran the export again with four: no options at all. "Delete existing
table and recreate (overwrite)" and ``lowercaseFieldNames`` never reached QGIS,
the fallback's answer was thrown away, and the success box was shown regardless
-- also when QGIS had answered ErrorConnectionFailed. Now one six-argument call
carries the options, and only Success is reported as a publication.

The table. FiberQ writes only new tables. The overwrite checkbox is gone, every
call carries overwrite off, and a name the database already has is refused
before the export -- FiberQ looks it up in pg_class first. When that lookup
cannot run, QGIS is asked all the same, and refuses a taken name by itself. The
Table field shows the name PostgreSQL keeps. After Success the rows are counted:
QGIS also answers Success when reading the layer stops part way.

No test here needs a database. FiberQ's own statements go to ``FakeConnection``,
which records them, answers the lookup and the count, and raises on anything
else; ``exportLayer`` is replaced by a stand-in with the binding's own signature,
except where a test hands the calls on to the real binding, or lets the real
exporter and QGIS's real connection try 127.0.0.1:1, where nothing listens. The
dialog's configuration is replaced as well, never read from ``config.ini``: the
tracked file names localhost:5433, where a developer's own PostGIS may well be
listening.
"""
import re

import pytest
from qgis.core import (
    Qgis,
    QgsCoordinateTransformContext,
    QgsDataSourceUri,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsProviderConnectionException,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerExporter,
    QgsVectorLayerUtils,
)
from qgis.PyQt.QtWidgets import QCheckBox, QMessageBox

from fiberq.addons import publish_pg
from fiberq.models import schema as fq_schema

#: Nothing listens on port 1, so a connection is refused at once: in CI, and in
#: a container started with ``--network none`` alike. An IP, so no name lookup.
UNREACHABLE = {
    "host": "127.0.0.1",
    "port": "1",
    "dbname": "gis",
    "user": "gis",
    "password": "gis",
    "schema": "public",
    "sslmode": "disable",
}

#: models/schema.py's logical field types, as memory-layer field types.
MEMORY_TYPES = {
    "text": "string",
    "enum": "string",
    "int": "integer",
    "year": "integer",
    "double": "double",
    "bool": "boolean",
}

Result = Qgis.VectorExportResult


class FakeIface:
    def __init__(self, layer):
        self._layer = layer

    def mainWindow(self):
        return None

    def activeLayer(self):
        return self._layer


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture
def modals(monkeypatch):
    """What the dialog would have shown, by kind."""
    said = {"info": [], "critical": [], "warning": []}
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: said["info"].append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: said["critical"].append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: said["warning"].append(str(a[-1]))))
    return said


def _memory(name, fields, rows, geometry="Point"):
    """A memory layer with ``fields`` given as ``name:type``, one feature per row."""
    uri = f"{geometry}?crs=EPSG:3857" + "".join(f"&field={field}" for field in fields)
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), uri
    features = []
    for i, values in enumerate(rows):
        feature = QgsFeature(layer.fields())
        if geometry != "None":
            wkt = {"Point": f"Point ({i} 0)",
                   "GeometryCollection": f"GeometryCollection (Point ({i} 0), LineString ({i} 0, {i} 1))",
                   }.get(geometry, f"LineString ({i} 0, {i} 1)")
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
        feature.setAttributes(list(values))
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    return layer


def _saved(layer, path, driver, layer_options=()):
    """``layer`` written to a file and read back from it: a user's own file layer."""
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver
    options.layerName = layer.name()
    if layer_options:
        options.layerOptions = list(layer_options)
    written = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    source = f"{path}|layername={layer.name()}" if driver == "GPKG" else str(path)
    saved = QgsVectorLayer(source, layer.name(), "ogr")
    assert saved.isValid(), source
    return saved


def _fiberq_layer(name, numbers):
    """An unsaved FiberQ layer with the fields models/schema.py lists for it.

    One feature per entry of ``numbers``, which go into the layer's first
    integer field -- the one the old rule made the key. Everything else is NULL.
    """
    roster = fq_schema.get_layer_schema(name)
    fields = [f for f in roster.fields if not f.on_demand]
    first_int = next(i for i, f in enumerate(fields) if MEMORY_TYPES[f.field_type] == "integer")
    rows = [[number if i == first_int else None for i in range(len(fields))] for number in numbers]
    layer = _memory(name, [f"{f.key}:{MEMORY_TYPES[f.field_type]}" for f in fields], rows, roster.geometry)
    return layer, fields[first_int].key


def _state(layer):
    """What publishing must leave exactly as it was."""
    return {
        "fields": [field.name() for field in layer.fields()],
        "editable": layer.isEditable(),
        "modified": layer.isModified(),
        "values": sorted(str(feature.attributes()) for feature in layer.getFeatures()),
    }


# ---------------------------------------------------------------------------
# the database, as FiberQ's own statements see it
# ---------------------------------------------------------------------------

#: The two statements FiberQ runs itself. Each name or value in them is a quoted
#: identifier or an SQL literal, which _unquote reads back as the server would.
LITERAL = r"(?:E'(?:[^'\\]|''|\\.)*'|'(?:[^']|'')*')"
IDENT = r'"(?:[^"]|"")*"'
LOOKUP = re.compile(r"SELECT c\.relkind::text FROM pg_catalog\.pg_class c JOIN pg_catalog\.pg_namespace n "
                    rf"ON n\.oid = c\.relnamespace WHERE n\.nspname = ({LITERAL}) AND c\.relname = ({LITERAL})")
COUNT = re.compile(rf"SELECT count\(\*\) FROM ({IDENT})\.({IDENT})")


def _unquote(token):
    """An SQL literal -- E'' included -- or a quoted identifier, as PostgreSQL reads it."""
    if token.startswith('"'):
        return token[1:-1].replace('""', '"')
    escaped = token.startswith("E")
    body, text, i = token[2 if escaped else 1:-1], [], 0
    while i < len(body):
        if escaped and body[i] == "\\":
            text.append(body[i + 1])
            i += 2
        elif body[i] == "'":
            text.append("'")
            i += 2
        else:
            text.append(body[i])
            i += 1
    return "".join(text)


#: QGIS's text of a refused connection: the whole connection string, password
#: included (measured on 3.22.16 to 4.2.3).
REFUSED = ("Connection failed: dbname='gis' host=127.0.0.1 port=1 user='gis' password='pw-in-the-uri' "
           "sslmode=disable")
#: The advice for a table left incomplete, as FiberQ gives it for public.poles.
ONLY_COPY = ('Check its rows before you remove it in your database tool (DROP TABLE "public"."poles";): if the layer\'s source has changed or gone, they may be the only copy of those rows left.')


class FakeConnection:
    """QGIS's postgres connection as publish_pg uses it -- executeSql -- without a database.

    It knows FiberQ's two statements and fails a test on any other: FiberQ
    looks a name up and counts rows, and never drops, alters or writes. The
    lookup is answered from ``relations``, {(schema, name): relkind}, the count
    from ``rows``, {(schema, name): rows}. ``fail`` names the statements --
    "lookup", "count" -- that raise QgsProviderConnectionException instead, with
    ``failure`` as its text. ``asked`` records what each statement named.
    """

    def __init__(self, relations=None, fail=(), failure=REFUSED):
        self.relations = dict(relations or {})
        self.rows = {}
        self.fail = set(fail)
        self.failure = failure
        self.statements = []
        self.asked = []

    def add(self, schema, name, rows):
        """A table QGIS has just written."""
        self.relations[(schema, name)] = "r"
        self.rows[(schema, name)] = rows

    def executeSql(self, sql):
        self.statements.append(sql)
        lookup, count = LOOKUP.fullmatch(sql), COUNT.fullmatch(sql)
        assert lookup or count, f"FiberQ ran a statement it never should: {sql}"
        what = "lookup" if lookup else "count"
        key = tuple(_unquote(token) for token in (lookup or count).groups())
        self.asked.append((what, key))
        if what in self.fail:
            raise QgsProviderConnectionException(self.failure)
        if lookup:
            return [[self.relations[key]]] if key in self.relations else []
        if key not in self.rows:
            raise QgsProviderConnectionException(f'SQL error: {sql} returned 7 [ERROR:  relation "{key[1]}" '
                                                 'does not exist]')
        return [[self.rows[key]]]


def _dialog(monkeypatch, layer, connection=None, config=None, real_connection=False):
    """A real PublishDialog on ``UNREACHABLE``; ``accepted`` records it closing.

    FiberQ's own statements go to ``connection`` -- a FakeConnection that knows
    no table, unless one is given -- or, with ``real_connection``, to QGIS's own
    postgres connection."""
    monkeypatch.setattr(publish_pg, "_load_pg_config", lambda: dict(config or UNREACHABLE))
    if not real_connection:
        fake = connection if connection is not None else FakeConnection()
        monkeypatch.setattr(publish_pg, "_connection", lambda pg: fake, raising=False)
    dlg = publish_pg.PublishDialog(FakeIface(layer))
    accepted = []
    dlg.accept = lambda: accepted.append(True)
    return dlg, accepted


def _exporter(monkeypatch, connection=None, code=Result.Success, message="", raises=None, written=None,
              meanwhile=None):
    """``exportLayer`` answering ``code``, with the binding's own signature, so a
    call QGIS would refuse with TypeError is refused here too; the calls it got.

    Each call records its URI's schema, table, key and geometry column, and its
    options. Unless QGIS could not connect or create the table, the table then
    is in ``connection``, holding ``written`` rows: every feature, by default.
    ``meanwhile`` runs first: what another session does between FiberQ's lookup
    and QGIS's create step."""
    calls = []

    def stand_in(layer, uri, providerKey, destCRS, onlySelected=False, options=None, feedback=None):
        parsed = QgsDataSourceUri(uri)
        calls.append({"uri": uri, "schema": parsed.schema(), "table": parsed.table(), "key": parsed.keyColumn(),
                      "geometry": parsed.geometryColumn(), "options": options})
        if meanwhile is not None:
            meanwhile()
        if raises is not None:
            raise raises
        created = code not in (Result.ErrorConnectionFailed, Result.ErrorCreatingLayer)
        if connection is not None and created:
            connection.add(parsed.schema(), parsed.table(), layer.featureCount() if written is None else written)
        return code, message

    monkeypatch.setattr(QgsVectorLayerExporter, "exportLayer", staticmethod(stand_in))
    return calls


def _publish(monkeypatch, source):
    """Press Publish on ``source`` with QGIS answering Success and writing every
    feature; the key the export named."""
    connection = FakeConnection()
    calls = _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, source, connection=connection)
    dlg._do_export()
    assert accepted == [True]
    assert len({call["key"] for call in calls}) == 1, calls
    return calls[0]["key"]


def _said(modals):
    """Everything the dialog showed, as one text."""
    return "\n".join(text for texts in modals.values() for text in texts)


# ---------------------------------------------------------------------------
# the key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name, numbers", [
    ("Underground cables", [2, 2, 1]),
    ("Manholes", [2019, 2019, 2021]),
    ("Optical slack", [4, 4, 7]),
], ids=["cables", "manholes", "slacks"])
def test_fiberq_layers_get_a_key_postgis_creates(monkeypatch, modals, project, name, numbers):
    """v1.5.0 made broj_cevcica, god_ugrad and cable_fid the key, and wrote 0 rows."""
    layer, first_int = _fiberq_layer(name, numbers)
    project.addMapLayer(layer)
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    assert key == "id", f"the key was {key!r}; {first_int} holds {numbers}"
    assert "id" not in [field.lower() for field in before["fields"]]
    assert "Used PK column: id (new, created and numbered by PostGIS)" in modals["info"][0], modals
    assert _state(layer) == before


@pytest.mark.parametrize("storage, editing", [
    ("memory", False),
    ("memory", True),
    ("shapefile", False),
], ids=["memory", "memory-editing", "shapefile"])
def test_the_layer_being_published_is_never_changed(monkeypatch, modals, project, tmp_path, storage, editing):
    """v1.5.0 added and saved an ``id`` column here, and it stayed even when the
    publish then failed: in the .dbf on disk, and as an empty column a rollback
    did not remove."""
    layer = _memory("Poles", ["naziv:string"], [["p0"], ["p1"], ["p2"]])
    if storage == "shapefile":
        layer = _saved(layer, tmp_path / "poles.shp", "ESRI Shapefile")
    project.addMapLayer(layer)
    if editing:
        assert layer.startEditing()
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    assert key == "id"
    assert _state(layer) == before
    if storage == "shapefile":
        on_disk = QgsVectorLayer(str(tmp_path / "poles.shp"), "check", "ogr")
        assert [field.name() for field in on_disk.fields()] == ["naziv"]


@pytest.mark.parametrize("storage, fields, rows, expected", [
    ("gpkg", ["naziv:string", "broj:integer"], [["a", 7], ["b", 7], ["c", 9]], "fid"),
    ("gpkg-objectid", ["naziv:string"], [["a"], ["b"]], "OBJECTID"),
    ("gpkg", ["naziv:string", "id:integer"], [["a", 30], ["b", 10], ["c", 20]], "id"),
    ("memory", ["naziv:string", "id:integer"], [["a", 3], ["b", 1], ["c", 2]], "id"),
    ("memory", ["GID:long", "naziv:string"], [[11, "a"], [12, "b"]], "GID"),
    ("shapefile", ["naziv:string", "pk:integer"], [["a", 5], ["b", 6]], "pk"),
], ids=["gpkg-fid", "gpkg-objectid", "gpkg-with-id", "memory-id", "memory-GID", "shapefile-pk"])
def test_the_layers_own_unique_key_is_kept(monkeypatch, modals, project, tmp_path, storage, fields, rows, expected):
    """Characterisation: each of these was already the key on v1.5.0, and must stay it.

    An integer id/pk/gid field comes first, as it did; otherwise the provider's
    own key, which for a GeoPackage is its fid column whatever it is called.
    """
    layer = _memory("Poles", fields, rows)
    if storage.startswith("gpkg"):
        options = ["FID=OBJECTID"] if storage == "gpkg-objectid" else []
        layer = _saved(layer, tmp_path / "poles.gpkg", "GPKG", options)
    elif storage == "shapefile":
        layer = _saved(layer, tmp_path / "poles.shp", "ESRI Shapefile")
    project.addMapLayer(layer)
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    # In any case: the export asks QGIS to lowercase the column names.
    assert key.lower() == expected.lower()
    assert "created and numbered by PostGIS" not in modals["info"][0], modals
    assert _state(layer) == before


def test_a_repeated_id_gives_way_to_the_layers_own_key(monkeypatch, modals, project, tmp_path):
    """An integer id that repeats is no key, and the GeoPackage's own fid is
    taken instead of a new column: every candidate is tried in turn, not only
    the first. v1.5.0 took the repeated id, and the export wrote 0 rows."""
    layer = _saved(_memory("Poles", ["naziv:string", "id:integer"], [["a", 1], ["b", 1], ["c", 2]]),
                   tmp_path / "poles.gpkg", "GPKG")
    project.addMapLayer(layer)

    key = _publish(monkeypatch, layer)

    assert key.lower() == "fid"
    assert "created and numbered by PostGIS" not in modals["info"][0], modals


@pytest.mark.parametrize("fields, rows, expected", [
    (["id:integer", "naziv:string"], [[1, "a"], [1, "b"], [2, "c"]], "id_1"),
    (["id:integer", "naziv:string"], [[1, "a"], [None, "b"], [2, "c"]], "id_1"),
    (["ID:string", "naziv:string"], [["A-1", "a"], ["A-2", "b"]], "id_1"),
], ids=["repeated-id", "null-id", "text-ID"])
def test_a_key_must_hold_a_different_number_on_every_feature(monkeypatch, modals, project, fields, rows, expected):
    """An ``id`` that repeats, or is NULL somewhere, cannot be a primary key: the
    export would write nothing. The new key then needs a name the layer does not
    have in any case -- QGIS is asked to lowercase field names, and a field
    ``ID`` would land on a key called ``id``."""
    layer = _memory("Poles", fields, rows)
    project.addMapLayer(layer)
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    assert key == expected
    assert f"Used PK column: {expected} (new, created and numbered by PostGIS)" in modals["info"][0], modals
    assert _state(layer) == before


def test_a_geopackage_feature_not_saved_yet_has_no_fid(monkeypatch, modals, project, tmp_path):
    """A feature added in the edit buffer reads 'Autogenerate' in its fid until it is
    saved, so the fid is no key for what the export writes: buffer included."""
    layer = _saved(_memory("Poles", ["naziv:string"], [["a"], ["b"]]), tmp_path / "poles.gpkg", "GPKG")
    project.addMapLayer(layer)
    assert layer.startEditing()
    # The way the attribute form makes a new feature, fid default included.
    feature = QgsVectorLayerUtils.createFeature(layer, QgsGeometry.fromWkt("Point (9 9)"), {1: "new"})
    assert layer.addFeature(feature)
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    assert key == "id"
    assert _state(layer) == before
    assert layer.editBuffer().addedFeatures(), "the unsaved feature is still waiting to be saved"


# ---------------------------------------------------------------------------
# the export call and its answer
# ---------------------------------------------------------------------------

@pytest.fixture
def poles(project):
    """Three points with a unique integer ``id``, which is their key: these tests
    are about the export."""
    layer = _memory("Poles", ["id:integer", "naziv:string"], [[1, "p0"], [2, "p1"], [3, "p2"]])
    project.addMapLayer(layer)
    return layer


def test_a_refused_connection_is_an_error_not_a_publication(monkeypatch, modals, poles):
    """The real exporter, and QGIS's real connection, against no server.

    v1.5.0 showed one information box -- "Layer 'Poles' has been published to
    PostGIS as public.poles" -- and closed the dialog. QGIS had answered
    ErrorConnectionFailed. FiberQ's own lookup fails first, and its text, which
    holds the password, is not shown: the export goes on and QGIS says what is
    wrong.
    """
    config = dict(UNREACHABLE, password="pw-never-shown")
    dlg, accepted = _dialog(monkeypatch, poles, config=config, real_connection=True)

    dlg._do_export()

    assert modals["info"] == [] and modals["warning"] == [], "reported as published: " + repr(modals)
    assert modals["critical"] == ["Layer 'Poles' was not published to PostGIS as public.poles.\n\n"
                                  "Connection to database failed"], modals
    assert "pw-never-shown" not in _said(modals)
    assert accepted == [], "the dialog closed as if the layer had been published"


def test_there_is_no_overwrite_checkbox(monkeypatch, poles):
    """v1.5.0 offered 'Delete existing table and recreate (overwrite)', ticked by
    default. It never took effect -- the eight-argument call it rode on always
    fell back to one without options -- and replacing a table has data-loss paths
    no guard closes, so it is gone: FiberQ writes only new tables. On v1.5.0 the
    checkbox is there."""
    dlg, _accepted = _dialog(monkeypatch, poles)

    assert not hasattr(dlg, "chk_overwrite")
    assert dlg.findChildren(QCheckBox) == [], [box.text() for box in dlg.findChildren(QCheckBox)]


@pytest.mark.parametrize("lookup", ["name-free", "lookup-failed"])
def test_every_export_asks_qgis_for_a_new_table(monkeypatch, modals, poles, lookup):
    """The one call QGIS accepts carries overwrite off and lowercased field names,
    so QGIS can never drop a table -- also when FiberQ's own lookup could not run.

    The spy hands every call on to the real binding, so QGIS itself decides
    which calls are valid, and only a call it accepted counts. On v1.5.0 the
    binding refused the eight-argument call, and the four-argument fallback it
    accepted carried no options at all."""
    real = QgsVectorLayerExporter.exportLayer
    calls = []

    def spy(*args, **kwargs):
        call = {"args": args, "kwargs": kwargs, "accepted": False}
        calls.append(call)
        answer = real(*args, **kwargs)
        call["accepted"] = True
        return answer

    monkeypatch.setattr(QgsVectorLayerExporter, "exportLayer", staticmethod(spy))
    connection = FakeConnection(fail={"lookup"} if lookup == "lookup-failed" else ())
    dlg, _accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    ran = [call for call in calls if call["accepted"]]
    assert len(ran) == 1, calls
    args, kwargs = ran[0]["args"], ran[0]["kwargs"]
    options = args[5] if len(args) > 5 else kwargs.get("options")
    assert options == {"overwrite": False, "lowercaseFieldNames": True}, (args, kwargs)
    assert len(calls) == 1, "one call, and no retry with fewer arguments: " + repr(calls)


@pytest.mark.parametrize("relkind, what", [
    ("r", "a table"),
    ("p", "a partitioned table"),
    ("v", "a view"),
    ("m", "a materialized view"),
    ("f", "a foreign table"),
    ("S", "a sequence"),
    ("i", "an index"),
    ("c", "a composite type"),
], ids=["table", "partitioned", "view", "matview", "foreign", "sequence", "index", "composite-type"])
def test_a_name_the_database_has_is_refused_before_the_export(monkeypatch, modals, poles, relkind, what):
    """Whatever holds the name in pg_class -- a partition and an inheritance child
    are tables too -- nothing is sent: FiberQ writes only new tables, and the
    user is told what is there and what to do. The advice is another name, not
    removing that relation: a layer read from it, directly or through a view, a
    query, a virtual or an OGR layer, would then publish nothing. On v1.5.0 the
    export ran."""
    connection = FakeConnection({("public", "poles"): relkind})
    calls = _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert calls == [], "the export ran: " + repr(calls)
    assert modals["critical"] == [
        f"Layer 'Poles' was not published: there is already {what} public.poles in the database. FiberQ writes "
        "only new tables, so nothing was written. Choose another table name."], modals
    assert modals["info"] == [] and accepted == [], modals
    assert connection.asked == [("lookup", ("public", "poles"))], connection.asked


def test_when_the_lookup_fails_qgis_refuses_a_taken_name_itself(monkeypatch, modals, poles):
    """FiberQ could not look the name up, so the export goes on -- overwrite off,
    so QGIS's CREATE TABLE refuses a name that is taken and changes nothing
    (measured on 3.22.16 to 4.2.3) -- and QGIS's reason is shown without the
    newline it ends with. The lookup's own text, which holds the password, is
    not. No incomplete table is reported: QGIS created none. On v1.5.0 the call
    carried no options, and the answer was reported as a publication."""
    connection = FakeConnection(fail={"lookup"})
    reason = 'Creation of data source "public"."poles" failed: \nERROR:  relation "poles" already exists'
    calls = _exporter(monkeypatch, connection, code=Result.ErrorCreatingLayer, message=reason + "\n")
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert [call["options"] for call in calls] == [{"overwrite": False, "lowercaseFieldNames": True}], calls
    assert modals["critical"] == [f"Layer 'Poles' was not published to PostGIS as public.poles.\n\n{reason}"], modals
    assert modals["info"] == [] and accepted == [], modals
    assert "pw-in-the-uri" not in _said(modals)


def test_success_is_reported_when_qgis_answers_success(monkeypatch, modals, poles):
    """Characterisation: this passes on v1.5.0 as well, which reported success
    whatever the answer. It is here so the fix cannot get there by reporting
    nothing."""
    connection = FakeConnection()
    _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert modals["critical"] == [], modals["critical"]
    assert len(modals["info"]) == 1, modals
    assert "has been published to PostGIS as public.poles" in modals["info"][0]
    assert accepted == [True]


def test_the_rows_written_are_counted_and_said(monkeypatch, modals, poles):
    """After Success FiberQ counts the table's rows through QGIS's own connection,
    and says so when they are all there. On v1.5.0 nothing was counted."""
    connection = FakeConnection()
    _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert modals["info"] == ["Layer 'Poles' has been published to PostGIS as public.poles.\n"
                              "Used PK column: id\nFeatures written: 3 of 3"], modals
    assert connection.asked == [("lookup", ("public", "poles")), ("count", ("public", "poles"))], connection.asked
    assert accepted == [True]


def test_success_with_rows_missing_is_reported_not_published(monkeypatch, modals, poles):
    """QGIS answers Success when reading the layer stops part way: a source table
    another session dropped, a reader connection the server ended (measured on
    3.22.16 to 4.2.3, 0 of 5 and 2000 of 2600 rows). The table QGIS has just
    made is left -- FiberQ never drops one -- and the user is told it is
    incomplete, and to check its rows before removing it: when the source has
    gone they are the only copy. The dialog stays open. v1.5.0 reported a
    publication."""
    connection = FakeConnection()
    _exporter(monkeypatch, connection, written=2)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert modals["info"] == [] and accepted == [], "reported as published: " + repr(modals)
    assert modals["critical"] == [
        "Layer 'Poles' was not published completely to PostGIS as public.poles. QGIS reported success, but it "
        "wrote 2 of the layer's 3 features: the table is incomplete. " + ONLY_COPY], modals
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in connection.statements), \
        "FiberQ ran more than its lookup and count: " + repr(connection.statements)


def test_an_empty_layer_publishes_an_empty_table(monkeypatch, modals, project):
    """A layer with no features -- a FiberQ layer not drawn yet -- gets an empty
    table, and the message says so in words. v1.5.0 counted nothing."""
    layer = _memory("Poles", ["naziv:string"], [])
    project.addMapLayer(layer)
    connection = FakeConnection()
    _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, layer, connection=connection)

    dlg._do_export()

    assert modals["info"] == ["Layer 'Poles' has been published to PostGIS as public.poles.\n"
                              "Used PK column: id (new, created and numbered by PostGIS)\n"
                              "Features written: 0 (the layer has no features)"], modals
    assert accepted == [True]


@pytest.mark.parametrize("written, said", [
    (1, "info:Features written: 1 of 1"),
    (0, "critical:QGIS reported success, but it wrote 0 of the layer's 1 feature: the table is incomplete."),
    (2, "warning:but it holds 2 rows while the layer has 1 feature:"),
], ids=["all", "fewer", "more"])
def test_one_feature_is_one_feature(monkeypatch, modals, project, written, said):
    """A layer of one feature is told in the singular, whatever QGIS wrote.
    v1.5.0 counted nothing."""
    layer = _memory("Poles", ["naziv:string"], [["a"]])
    project.addMapLayer(layer)
    connection = FakeConnection()
    _exporter(monkeypatch, connection, written=written)
    dlg, _accepted = _dialog(monkeypatch, layer, connection=connection)

    dlg._do_export()

    kind, words = said.split(":", 1)
    assert len(modals[kind]) == 1 and words in modals[kind][0], modals


def test_more_rows_than_the_layer_has_is_a_warning(monkeypatch, modals, poles):
    """More rows than the layer reports is no incomplete table: another session
    wrote into it meanwhile, or the layer counted its source before others added
    to it. Published, with a warning that names both numbers. v1.5.0 counted
    nothing and showed a plain success."""
    connection = FakeConnection()
    _exporter(monkeypatch, connection, written=4)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert modals["info"] == [] and modals["critical"] == [], modals
    assert modals["warning"] == [
        "Layer 'Poles' has been published to PostGIS as public.poles, but it holds 4 rows while the layer has "
        "3 features: check it in your database tool before you use it.\nUsed PK column: id"], modals
    assert accepted == [True]


def _without_an_exact_count(monkeypatch, layer, why, estimate=None):
    """Make ``layer`` give no exact count: QGIS's 'unknown' (-1), or a PostgreSQL
    layer with estimated table metadata whose count is ``estimate``."""
    if why == "unknown":
        monkeypatch.setattr(layer, "featureCount", lambda: -1)
        return
    monkeypatch.setattr(layer, "providerType", lambda: "postgres")
    monkeypatch.setattr(layer, "source", lambda: "dbname='gis' host=10.0.0.9 user='gis' key='id' "
                                                 "estimatedmetadata=true table=\"fiberq\".\"stubovi\" (geom)")
    if estimate is not None:
        monkeypatch.setattr(layer, "featureCount", lambda: estimate)


@pytest.mark.parametrize("why", ["unknown", "estimated"])
@pytest.mark.parametrize("written, said", [
    (3, "info:Features written: 3 of 3"),
    (2, "critical:QGIS reported success, but it wrote 2 of the layer's 3 features: the table is incomplete."),
    (7, "warning:but it holds 7 rows while the layer has 3 features:"),
], ids=["all", "fewer", "more"])
def test_a_count_the_layer_does_not_know_is_taken_by_reading_it(monkeypatch, modals, poles, why, written, said):
    """A layer that gives no feature count -- or a PostgreSQL layer with estimated
    table metadata, whose count comes from the table statistics: -1 for a table
    never analysed, 3 for a table of 7 once rows were added (measured on
    3.22.16 to 4.2.3) -- is counted by reading it before the export, so a
    read that stops part way is caught for it too: 2000 of 2600 rows written
    after the server ended the reader's connection, with estimated metadata,
    was reported as published before this check. v1.5.0 counted nothing."""
    # Old statistics count one feature where the layer has three: trusting that
    # figure would call three rows "more" and two rows "all", so the verdicts
    # below hold only when the layer is read.
    _without_an_exact_count(monkeypatch, poles, why, estimate=1 if why == "estimated" else None)
    connection = FakeConnection()
    _exporter(monkeypatch, connection, written=written)
    dlg, _accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    kind, words = said.split(":", 1)
    assert len(modals[kind]) == 1 and words in modals[kind][0], modals


def test_fewer_features_than_the_statistics_count_is_a_warning(monkeypatch, modals, poles):
    """A PostgreSQL layer with estimated metadata whose source another session
    dropped before Publish: the layer reads nothing, QGIS writes nothing and
    answers Success, and only the table statistics (5) remember the rows. That
    is a warning naming both numbers, not a plain success; the statistics can
    be old either way, so it is no error. v1.5.0 counted nothing."""
    _without_an_exact_count(monkeypatch, poles, "estimated", estimate=5)
    monkeypatch.setattr(poles, "getFeatures", lambda *args: iter([]))
    connection = FakeConnection()
    _exporter(monkeypatch, connection, written=0)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert modals["info"] == [] and modals["critical"] == [], modals
    assert modals["warning"] == [
        "Layer 'Poles' has been published to PostGIS as public.poles, with 0 features, but the statistics of the "
        "layer's source count about 5: check in your database tool that the layer read them all.\n"
        "Used PK column: id"], modals
    assert accepted == [True]


def test_rows_that_cannot_be_counted_are_said_so(monkeypatch, modals, poles):
    """QGIS answered Success, and the count then failed: the layer is reported as
    published, with a warning to check the table, and the failure's text --
    which, for a lost connection, holds the password -- is not shown. v1.5.0
    counted nothing."""
    connection = FakeConnection(fail={"count"})
    _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert modals["warning"] == [
        "Layer 'Poles' has been published to PostGIS as public.poles: QGIS reported success.\nUsed PK column: id\n"
        "FiberQ could not count the rows written, so check in your database tool that public.poles holds the "
        "layer's 3 features."], modals
    assert modals["info"] == [] and modals["critical"] == [], modals
    assert accepted == [True]


@pytest.mark.parametrize("code, message, shown", [
    (Result.ErrorCreatingLayer,
     'Creation of data source "public"."poles" failed: \nERROR:  relation "poles" already exists\n',
     'Creation of data source "public"."poles" failed: \nERROR:  relation "poles" already exists'),
    (Result.ErrorConnectionFailed, "", "QGIS reported ErrorConnectionFailed."),
], ids=["with-reason", "no-reason"])
def test_any_other_answer_is_an_error_with_its_reason(monkeypatch, modals, poles, code, message, shown):
    """QGIS's own words when it gives some -- without the newline it ends them
    with -- and the result's name when it does not. v1.5.0 reported each of
    these as published."""
    connection = FakeConnection()
    _exporter(monkeypatch, connection, code=code, message=message)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert modals["info"] == [], "reported as published: " + repr(modals["info"])
    assert modals["critical"] == [
        f"Layer 'Poles' was not published to PostGIS as public.poles.\n\n{shown}"], modals["critical"]
    assert accepted == []


@pytest.mark.parametrize("code, written, note", [
    (Result.ErrorAttributeCreationFailed, 0, True),
    (Result.ErrorFeatureWriteFailed, 1, True),
    (Result.ErrorInvalidLayer, 0, True),
    (Result.ErrorProjectingFeatures, 2, True),
    (Result.ErrorCreatingLayer, 4, False),
    (Result.ErrorConnectionFailed, 4, False),
], ids=["fields-failed", "write-failed", "invalid-layer", "projecting-failed", "create-failed", "no-connection"])
def test_a_table_qgis_began_and_left_is_reported_not_removed(monkeypatch, modals, poles, code, written, note):
    """With overwrite off QGIS gets past its create step only for a free name, so
    after a later failure the table there is the one it began, incomplete. The
    user is told how many rows it holds and how to remove it; FiberQ runs no
    DROP. ErrorCreatingLayer and ErrorConnectionFailed leave nothing: a table
    there then -- here one another session made in the meantime, with 4 rows --
    is not QGIS's, and is not called incomplete. v1.5.0 reported a
    publication."""
    connection = FakeConnection()
    another_session = None if note else (lambda: connection.add("public", "poles", 4))
    _exporter(monkeypatch, connection, code=code, message="QGIS's reason", written=written, meanwhile=another_session)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert modals["info"] == [] and accepted == [], "reported as published: " + repr(modals)
    expected = "Layer 'Poles' was not published to PostGIS as public.poles.\n\nQGIS's reason"
    if note:
        expected += (f"\n\nQGIS had created public.poles before it failed, and wrote {written} of the layer's 3 "
                     "features to it: the table is incomplete. " + ONLY_COPY)
    assert modals["critical"] == [expected], modals
    assert ("public", "poles") in connection.relations


def test_a_table_left_that_cannot_be_looked_at_is_still_mentioned(monkeypatch, modals, poles):
    """A failure after QGIS's create step, and the connection gone before FiberQ
    could look: the user is told QGIS may have left an incomplete table, and how
    to remove it. v1.5.0 reported a publication."""
    connection = FakeConnection()
    _exporter(monkeypatch, connection, code=Result.ErrorFeatureWriteFailed, message="QGIS's reason")
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)
    real = connection.executeSql

    def lookup_fails_after_the_export(sql):
        if connection.statements:
            connection.fail.add("lookup")
        return real(sql)
    monkeypatch.setattr(connection, "executeSql", lookup_fails_after_the_export)

    dlg._do_export()

    assert modals["info"] == [] and accepted == [], "reported as published: " + repr(modals)
    assert modals["critical"] == [
        "Layer 'Poles' was not published to PostGIS as public.poles.\n\nQGIS's reason\n\nQGIS may have created "
        "public.poles before it failed. If it is there, it is incomplete. " + ONLY_COPY], modals


#: A QGIS URI with a password holding a quote, a space and a backslash, as QgsDataSourceUri writes it.
FULL_URI = ("dbname='gis' host=127.0.0.1 port=1 user='gis' password='pw-in-the-uri\\'s \\\\ x' sslmode=disable "
            "key='id' table=\"public\".\"poles\" (geom)")


@pytest.mark.parametrize("path", ["lookup", "reason", "uri", "exception", "count"])
def test_the_password_is_never_shown(monkeypatch, modals, poles, path):
    """QGIS writes a refused connection as "Connection failed: " and the whole
    connection string, password included. FiberQ never shows the text of its
    own lookup or count, and in what QGIS's export says or raises a connection
    string is replaced and a password masked. On v1.5.0 a raised text was shown
    as it came, and every answer was reported as a publication."""
    fail = {"lookup": {"lookup"}, "count": {"count"}}.get(path, ())
    connection = FakeConnection(fail=fail)
    if path == "lookup":
        _exporter(monkeypatch, connection, code=Result.ErrorConnectionFailed, message="Connection to database failed")
    elif path == "reason":
        _exporter(monkeypatch, connection, code=Result.ErrorCreatingLayer,
                  message=f"{REFUSED} | postgresql://gis:pw-in-the-uri@127.0.0.1/gis | password=pw-in-the-uri")
    elif path == "uri":
        _exporter(monkeypatch, connection, code=Result.ErrorCreatingLayer, message=f"Could not open {FULL_URI}")
    elif path == "exception":
        _exporter(monkeypatch, connection, raises=RuntimeError(f"export refused: {REFUSED}"))
    else:
        _exporter(monkeypatch, connection)
    dlg, _accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert "pw-in-the-uri" not in _said(modals), modals
    expected = {
        "lookup": ("critical", "Layer 'Poles' was not published to PostGIS as public.poles.\n\n"
                               "Connection to database failed"),
        "reason": ("critical", "Layer 'Poles' was not published to PostGIS as public.poles.\n\nConnection failed: "
                               "[connection string] | postgresql://gis:********@127.0.0.1/gis | password=********"),
        "uri": ("critical", "Layer 'Poles' was not published to PostGIS as public.poles.\n\nCould not open "
                            "[connection string] (geom)"),
        "exception": ("critical", "Error during export:\n\nexport refused: Connection failed: [connection string]"),
        "count": ("warning", "FiberQ could not count the rows written"),
    }[path]
    assert len(modals[expected[0]]) == 1 and expected[1] in modals[expected[0]][0], modals


def test_the_key_is_named_as_the_table_will_have_it(monkeypatch, modals, project):
    """QGIS lowercases the column names, the key's too, and finds the key's field
    by its lowercased name from 3.34.4 on (qgis/QGIS#56243), by its own spelling
    before. Named the other way, a 64-bit key became a 32-bit serial column
    (measured on 3.22.16, and on 3.34.15 to 4.2.3), which a value above 2^31 no
    longer fits. v1.5.0 named it 'GID' everywhere, the message included."""
    layer = _memory("Poles", ["GID:long", "naziv:string"], [[11, "a"], [3000000000, "b"]])
    project.addMapLayer(layer)

    key = _publish(monkeypatch, layer)

    assert key == ("gid" if Qgis.QGIS_VERSION_INT >= 33404 else "GID")
    assert "Used PK column: gid\n" in modals["info"][0], modals


def test_names_are_quoted_in_every_statement(monkeypatch, modals, poles):
    """A schema holding a double quote, a single quote, a backslash and SQL of its
    own: FiberQ's lookup names it as one literal and its count as one quoted
    identifier, and PostgreSQL reads back exactly the schema typed -- the fake
    reads them as the server does. The export's URI names it whole, through
    QgsDataSourceUri. v1.5.0 ran no statement, and wrote the schema into the
    URI unescaped."""
    hostile = 'we"ird\'s\\ ; DROP TABLE x; --'
    connection = FakeConnection()
    calls = _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)
    dlg.le_schema.setText(hostile)

    dlg._do_export()

    assert connection.asked == [("lookup", (hostile, "poles")), ("count", (hostile, "poles"))], connection.asked
    assert [call["schema"] for call in calls] == [hostile], calls
    assert accepted == [True], modals


def test_a_schema_is_cut_where_postgresql_cuts_it(monkeypatch, modals, poles):
    """PostgreSQL keeps the first 63 bytes of a name, a character never cut in
    half. A schema typed longer is looked up, and named, as PostgreSQL has it.
    v1.5.0 looked nothing up."""
    typed = "s" * 62 + "šema"
    kept = "s" * 62
    connection = FakeConnection({(kept, "poles"): "r"})
    calls = _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)
    dlg.le_schema.setText(typed)

    dlg._do_export()

    assert calls == [], "the export ran: " + repr(calls)
    assert connection.asked == [("lookup", (kept, "poles"))], connection.asked
    assert f"there is already a table {kept}.poles in the database" in modals["critical"][0], modals


# ---------------------------------------------------------------------------
# the Table field
# ---------------------------------------------------------------------------

def test_the_table_follows_the_layer_picked(monkeypatch, project, poles):
    """Opened on Poles, then Ducts picked: Publish must not target Poles' table.
    A name the user typed is kept. v1.5.0 kept 'poles' for Ducts."""
    ducts = _memory("Ducts", ["materijal:string"], [["PE"]], geometry="LineString")
    project.addMapLayer(ducts)
    dlg, _accepted = _dialog(monkeypatch, poles)
    assert dlg.le_table.text() == "poles"

    dlg.cmb_layer.setCurrentIndex(dlg.layers.index(ducts))
    assert dlg.le_table.text() == "ducts"

    dlg.le_table.setText("my_table")
    dlg.cmb_layer.setCurrentIndex(dlg.layers.index(poles))
    assert dlg.le_table.text() == "my_table", "a name the user typed is kept"


def test_with_no_active_layer_the_table_names_the_layer_shown(monkeypatch, project, poles):
    """v1.5.0 offered 'layer_export' here while the combo showed a layer, so every
    publish made with no active layer went to that one table."""
    dlg, _accepted = _dialog(monkeypatch, None)

    assert dlg.cmb_layer.currentText() == "Poles"
    assert dlg.le_table.text() == "poles"


LONG = "Underground cables - Faza 2 - Opstina Novi Sad - stanje na dan 2026-10-01"
LONG_KEPT = "underground_cables_faza_2_opstina_novi_sad_stanje_na_dan_2026_1"


@pytest.mark.parametrize("name, kept", [
    (LONG, LONG_KEPT),
    ("a" * 62 + " b", "a" * 62),
    ("Trasa-2026", "trasa_2026"),
    ("Каблови", "layer_export"),
    ("2026 trasa", "_2026_trasa"),
    ("9" * 70, "_" + "9" * 62),
], ids=["long", "cut-after-underscore", "dash", "cyrillic", "digit-first", "digits-long"])
def test_a_table_name_is_one_postgresql_keeps_as_it_is(name, kept):
    """At most 63 bytes, the most of a name PostgreSQL keeps, and cleaning it
    again changes nothing -- the Table field is cleaned each time the user
    leaves it. v1.5.0 left a long name whole: the field and the messages named
    a table that never exists, and two layers alike in their first 63 bytes
    went to one table unseen. dash, cyrillic and digit-first are
    characterisation: v1.5.0 cleaned those names the same way."""
    assert publish_pg._sanitize_table_name(name) == kept
    assert len(kept.encode("utf-8")) <= 63
    assert publish_pg._sanitize_table_name(kept) == kept


def test_the_table_field_shows_the_name_postgresql_keeps(monkeypatch, modals, project):
    """The name filled in for a layer, and a name typed once the user leaves the
    field, are the names written: 63 bytes at most, cleaned as the export
    cleans them. v1.5.0 showed the long name whole and left a typed name as
    typed."""
    layer = _memory(LONG, ["naziv:string"], [["a"]], geometry="LineString")
    project.addMapLayer(layer)
    dlg, _accepted = _dialog(monkeypatch, layer)
    assert dlg.le_table.text() == LONG_KEPT

    for typed, kept in (("Trasa-2026", "trasa_2026"), ("Каблови", "layer_export")):
        dlg.le_table.setText(typed)
        dlg.le_table.editingFinished.emit()
        assert dlg.le_table.text() == kept, typed


def test_the_name_looked_up_and_written_is_the_name_shown(monkeypatch, modals, poles):
    """Publish pressed while the field still holds what was typed: the field is
    cleaned first, so the lookup, the export and the message all name the table
    the field shows. On v1.5.0 the field kept the typed text, and FiberQ looked
    nothing up."""
    connection = FakeConnection()
    calls = _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)
    dlg.le_table.setText("Trasa 2026 (faza 1)")

    dlg._do_export()

    assert dlg.le_table.text() == "trasa_2026_faza_1"
    assert connection.asked[0] == ("lookup", ("public", "trasa_2026_faza_1")), connection.asked
    assert [call["table"] for call in calls] == ["trasa_2026_faza_1"], calls
    assert "as public.trasa_2026_faza_1." in modals["info"][0], modals
    assert accepted == [True]


@pytest.mark.parametrize("typed, taken", [
    ("Trasa-2026", "trasa_2026"),
    ("Каблови", "layer_export"),
    (LONG + " (copy)", LONG_KEPT),
], ids=["dash", "cyrillic", "same-first-63-bytes"])
def test_a_typed_name_cleaned_onto_a_taken_table_is_refused(monkeypatch, modals, poles, typed, taken):
    """A typed name the export cleans into the name of a table that is there: the
    field shows that name, and nothing is written. On v1.5.0 the export ran
    onto the other table's name, and its answer was reported as a
    publication."""
    connection = FakeConnection({("public", taken): "r"})
    calls = _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)
    dlg.le_table.setText(typed)

    dlg._do_export()

    assert calls == [], "the export ran: " + repr(calls)
    assert dlg.le_table.text() == taken
    assert f"there is already a table public.{taken} in the database" in modals["critical"][0], modals
    assert accepted == []


# ---------------------------------------------------------------------------
# refused before the export, and the geometry column
# ---------------------------------------------------------------------------

def test_an_unavailable_layer_is_refused(monkeypatch, modals, project, tmp_path):
    """A layer whose file has moved stays in the project, unavailable. v1.5.0
    handed it to the export, and reported the answer as a publication."""
    gone = QgsVectorLayer(str(tmp_path / "moved" / "poles.shp"), "Poles", "ogr")
    assert not gone.isValid()
    project.addMapLayer(gone)
    calls = _exporter(monkeypatch)
    dlg, accepted = _dialog(monkeypatch, gone)

    dlg._do_export()

    assert calls == [], "the export ran: " + repr(modals)
    assert modals["info"] == [] and accepted == [], modals
    assert modals["critical"] == ["Layer 'Poles' is unavailable: QGIS cannot read its data source. "
                                  "Repair its data source, or pick another layer."], modals


@pytest.mark.parametrize("geometry", ["Point", "None", "GeometryCollection"],
                         ids=["point", "no-geometry", "geometrycollection"])
def test_a_layer_without_geometry_gets_no_geometry_column(monkeypatch, modals, project, geometry):
    """v1.5.0 named the geometry column '(geom)' for every layer. A layer without
    geometry got a table without that column, which QGIS then failed to open --
    'Loading of layer failed'. Without it, the table and every row are
    published. The point layer is the control, characterisation: it keeps its
    geometry column. So does a GeometryCollection layer, although QGIS does not
    call it spatial: isSpatial() is False for it on 3.22.16 to 4.2.3, and a
    rule built on isSpatial() published its features without their geometries,
    as a success."""
    layer = _memory("Poles", ["naziv:string"], [["a"], ["b"]], geometry)
    project.addMapLayer(layer)
    connection = FakeConnection()
    calls = _exporter(monkeypatch, connection)
    dlg, accepted = _dialog(monkeypatch, layer, connection=connection)

    dlg._do_export()

    assert accepted == [True] and len(modals["info"]) == 1, modals
    assert [call["geometry"] for call in calls] == ["" if geometry == "None" else "geom"], calls


# ---------------------------------------------------------------------------
# a shapefile's key
# ---------------------------------------------------------------------------

def test_a_shapefile_key_is_named_in_lowercase(monkeypatch, modals, project, tmp_path):
    """exportLayer lowercases a shapefile's field names itself, on every version.
    Named 'GID', as v1.5.0 named it, the key was not found on 3.22.16: it became
    a 32-bit serial, and the row holding 3,000,000,000 failed. Named 'gid', the
    column is bigint and both rows are published (3.22.16 to 4.2.3)."""
    layer = _saved(_memory("Poles", ["GID:long(10)", "naziv:string"], [[11, "a"], [3000000000, "b"]]),
                   tmp_path / "poles.shp", "ESRI Shapefile")
    project.addMapLayer(layer)

    assert _publish(monkeypatch, layer) == "gid"


class _QgisAt:
    """``Qgis`` as publish_pg sees it on another QGIS version: only the version differs."""

    def __init__(self, version):
        self.QGIS_VERSION_INT = version

    def __getattr__(self, name):
        return getattr(Qgis, name)


@pytest.mark.parametrize("storage, version, expected", [
    ("memory", 32216, "GID"),
    ("memory", 33403, "GID"),
    ("memory", 33404, "gid"),
    ("shapefile", 32216, "gid"),
    ("shapefile", 33404, "gid"),
], ids=["memory-3.22", "memory-3.34.3", "memory-3.34.4", "shapefile-3.22", "shapefile-3.34.4"])
def test_the_key_is_spelled_as_that_qgis_looks_it_up(monkeypatch, modals, project, tmp_path,
                                                     storage, version, expected):
    """The version QGIS reports is replaced, so both sides of 3.34.4 run on every
    leg. A memory layer's 'GID' is found by its own spelling before 3.34.4 and as
    'gid' from then on; a shapefile's as 'gid' only. Measured with 3,000,000,000 in
    the key: 3.22.16 (memory 'GID', shapefile 'gid'), 3.34.15 to 4.2.3 ('gid').
    memory-3.22 and memory-3.34.3 are characterisation: v1.5.0 named the key
    in the field's own spelling everywhere, which they expect."""
    layer = _memory("Poles", ["GID:long(10)", "naziv:string"], [[11, "a"], [12, "b"]])
    if storage == "shapefile":
        layer = _saved(layer, tmp_path / "poles.shp", "ESRI Shapefile")
    project.addMapLayer(layer)
    monkeypatch.setattr(publish_pg, "Qgis", _QgisAt(version), raising=False)

    assert _publish(monkeypatch, layer) == expected


def test_the_count_checked_is_the_one_taken_before_the_export(monkeypatch, modals, poles):
    """The rows written are checked against the count the layer had when Publish
    was pressed. A source that shrinks while QGIS reads it -- rows deleted by
    another session -- then counts what is left, which would hide the loss.
    v1.5.0 counted nothing."""
    connection = FakeConnection()
    shrink = (lambda: monkeypatch.setattr(poles, "featureCount", lambda: 2))
    _exporter(monkeypatch, connection, written=2, meanwhile=shrink)
    dlg, accepted = _dialog(monkeypatch, poles, connection=connection)

    dlg._do_export()

    assert accepted == [] and "wrote 2 of the layer's 3 features" in modals["critical"][0], modals


def test_a_backslash_in_a_name_is_written_as_an_escape_string(monkeypatch, modals, poles):
    """A literal holding a backslash is written E'...', so the lookup stays right
    on a server where standard_conforming_strings is off. v1.5.0 looked nothing
    up."""
    connection = FakeConnection()
    _exporter(monkeypatch, connection)
    dlg, _accepted = _dialog(monkeypatch, poles, connection=connection)
    dlg.le_schema.setText("a\\b")

    dlg._do_export()

    assert connection.statements and "n.nspname = E'a\\\\b'" in connection.statements[0], connection.statements


def test_only_the_whole_layer_is_exported(monkeypatch, modals, poles):
    """Characterisation: the export passes onlySelected False, so a selection on
    the layer never cuts what is published. It passes on v1.5.0 too, whose
    fallback call left onlySelected at its default."""
    seen = []

    def stand_in(layer, uri, providerKey, destCRS, onlySelected=False, options=None, feedback=None):
        seen.append(onlySelected)
        return Result.ErrorConnectionFailed, ""
    monkeypatch.setattr(QgsVectorLayerExporter, "exportLayer", staticmethod(stand_in))
    dlg, _accepted = _dialog(monkeypatch, poles)

    dlg._do_export()

    assert seen == [False], seen


def test_the_password_reaches_qgis_as_it_is(monkeypatch, modals, poles):
    """A password holding a quote, a backslash and a space is written into the
    URI quoted, so QGIS reads back exactly the password config.ini gives.
    v1.5.0 pasted it into an f-string, where the quote ended the value and
    QGIS read another password."""
    password = "pw'q \\ x"
    connection = FakeConnection()
    calls = _exporter(monkeypatch, connection)
    dlg, _accepted = _dialog(monkeypatch, poles, connection=connection, config=dict(UNREACHABLE, password=password))

    dlg._do_export()

    assert calls, modals
    assert [QgsDataSourceUri(call["uri"]).password() for call in calls] == [password], calls
