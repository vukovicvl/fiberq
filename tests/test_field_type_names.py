"""Every column FiberQ adds carries a type name, and nothing says a column was
added when its data source does not have it.

v1.6.0 QA finding Q13, measured live on QGIS 3.22.16, 3.40.15 and 4.2.3 against
PostGIS 16, connected as the tables' owner. ``QgsField(name, FieldType.String)``
has an empty type name, and the PostgreSQL provider writes the type name
straight into ``ALTER TABLE ... ADD COLUMN "fiberq_uuid" `` -- a syntax error,
for every kind of field. ``ensure_uuid_field`` then fell back to adding the
column through an edit session whose commit failed the same way, left the layer
in edit mode with the column pending, and answered True. Every later save on
that layer failed with "1 new attribute(s) not added" while the tools said
"placed", and the project-open migration reported UUIDs it never wrote.

No database here, and none is needed:

* The SpatiaLite provider writes the type name into its SQL the same way.
  SQLite accepts a column with no type, so the empty name does not fail there:
  it makes a column QGIS reads back as text, which a test can see.
* The honesty half needs only a save that cannot happen: a GeoPackage held by
  another sqlite3 connection (``BEGIN EXCLUSIVE``) or a layer set read-only --
  never chmod, because CI runs as root. Each locked test costs about five
  seconds of GDAL's busy wait, so there are only three.
* A shapefile is its own case. DBF keeps ten characters of a column name, so
  OGR stored ``fiberq_uuid`` as ``fiberq_uui``, the next look-up by the full
  name did not find it, and every call added another copy.

Every behaviour test collects plain values, rolls back and drops its layers
before asserting, so a failure on an older tree reports instead of crashing at
teardown with QGIS objects still alive in the failing frame. A map canvas and
its tool hold each other, so letting go of them frees neither: the tests that
make one collect them right away, while QGIS is still up. Left to pytest's last
collection, after QGIS has shut down, they ended a 3.22.16 run of this file on
an older tree in a segfault, with no summary.
"""
import ast
import gc
import logging
import pathlib
import sqlite3

import pytest
from qgis.core import (
    QgsCoordinateTransformContext, QgsDataSourceUri, QgsFeature, QgsField, QgsGeometry,
    QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer,
)

from fiberq.utils.compat import FieldType

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "fiberq"
UUID = "fiberq_uuid"
KINDS = ["String", "Int", "LongLong", "Double", "Bool"]


def _number(kind):
    return int(getattr(kind, "value", kind))


class FakeBar:
    def __init__(self):
        self.warnings = []

    def pushWarning(self, title, text):
        self.warnings.append(f"{title}: {text}")

    def pushInfo(self, *a):
        pass

    def pushSuccess(self, *a):
        pass


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


@pytest.fixture
def bar(monkeypatch):
    """What reached the message bar, through qgis.utils.iface as well."""
    import qgis.utils
    iface = FakeIface()
    monkeypatch.setattr(qgis.utils, "iface", iface)
    return iface


def _seed(name="Poles"):
    memory = QgsVectorLayer("Point?crs=EPSG:4326&field=naziv:string", name, "memory")
    feature = QgsFeature(memory.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1, 1)))
    feature["naziv"] = "seed"
    memory.dataProvider().addFeatures([feature])
    return memory


def _write(path, driver, options=()):
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = driver
    opts.layerName = "t"
    opts.datasourceOptions = list(options)
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        _seed(), str(path), QgsCoordinateTransformContext(), opts)
    assert result[0] == QgsVectorFileWriter.WriterError.NoError, result


def _gpkg(tmp_path, name="p.gpkg", layer_name="Poles"):
    path = tmp_path / name
    _write(path, "GPKG")
    layer = QgsVectorLayer(f"{path}|layername=t", layer_name, "ogr")
    assert layer.isValid()
    return path, layer


def _spatialite(tmp_path, name="p.sqlite", layer_name="Poles"):
    path = tmp_path / name
    _write(path, "SQLite", ["SPATIALITE=YES"])
    uri = QgsDataSourceUri()
    uri.setDatabase(str(path))
    uri.setDataSource("", "t", "GEOMETRY")
    layer = QgsVectorLayer(uri.uri(), layer_name, "spatialite")
    assert layer.isValid()
    return path, layer


def _declared(path, column):
    """The column's declared SQL type as the file stores it; None when absent."""
    con = sqlite3.connect(str(path))
    try:
        return {row[1]: row[2] for row in con.execute('PRAGMA table_info("t")')}.get(column)
    finally:
        con.close()


def _hold(path):
    """Another program holding the GeoPackage: the busy wait ends in a refusal."""
    con = sqlite3.connect(str(path), isolation_level=None, timeout=1)
    con.execute("BEGIN EXCLUSIVE")
    return con


def _release(con):
    con.execute("ROLLBACK")
    con.close()


# ---------------------------------------------------------------------------
# the helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,name", [
    ("String", "text"), ("Int", "integer"), ("LongLong", "bigint"),
    ("Double", "double precision"), ("Bool", "boolean")])
def test_new_field_carries_a_type_name(qgis_app, kind, name):
    from fiberq.utils.compat import new_field
    field = new_field("f", getattr(FieldType, kind))
    assert field.typeName() == name
    assert _number(field.type()) == _number(getattr(FieldType, kind))


@pytest.mark.parametrize("kind", KINDS)
def test_memory_and_geopackage_get_the_same_column_as_before(qgis_app, tmp_path, kind):
    """No regression where FiberQ layers usually live: the same field type on a
    memory layer, and the same type and declared column in a GeoPackage, typed
    or not. Characterisation: it passes before the fix too, by design."""
    from fiberq.utils.compat import new_field
    qtype = getattr(FieldType, kind)
    got = []
    for typed in (False, True):
        field = new_field("f", qtype) if typed else QgsField("f", qtype)
        memory = _seed()
        assert memory.dataProvider().addAttributes([field])
        memory.updateFields()
        path, gpkg = _gpkg(tmp_path, f"{kind}_{typed}.gpkg")
        assert gpkg.dataProvider().addAttributes([field])
        gpkg.updateFields()
        got.append((_number(memory.fields().field("f").type()),
                    _number(gpkg.fields().field("f").type()), _declared(path, "f")))
    assert got[0] == got[1]


def test_no_field_is_built_without_its_type_name():
    """``QgsField(name, type)`` anywhere in the package but utils/compat.py is
    the defect waiting for a database: a field list written for a new memory
    layer is one refactor away from being added to an existing table. The
    one-argument copy, ``QgsField(source)``, keeps the source's type name."""
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        if relative == "utils/compat.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", None) != "QgsField":
                continue
            if len(node.args) + len(node.keywords) > 1:
                found.append(f"fiberq/{relative}:{node.lineno}")
    assert not found, "use compat.new_field(name, FieldType.X):\n" + "\n".join(found)


def test_the_scan_would_catch_a_reintroduction():
    """A check that has never fired is not a check."""
    calls = [node for node in ast.walk(ast.parse(
        'a = QgsField("naziv", FieldType.String)\nb = QgsField(source)\n'))
        if isinstance(node, ast.Call)]
    caught = [c for c in calls if len(c.args) + len(c.keywords) > 1]
    assert len(caught) == 1 and caught[0].lineno == 1


# ---------------------------------------------------------------------------
# type names reach the SQL (SpatiaLite stands in for PostgreSQL)
# ---------------------------------------------------------------------------

def test_the_identity_column_is_declared_text(qgis_app, tmp_path):
    from fiberq.utils.uuid_utils import ensure_uuid_field
    path, layer = _spatialite(tmp_path)
    answered = ensure_uuid_field(layer)
    del layer
    assert answered is True
    assert (_declared(path, UUID) or "").upper() == "TEXT"


def test_branch_index_is_a_number_column(qgis_app, tmp_path):
    from fiberq.core.cable_manager import CableManager
    path, layer = _spatialite(tmp_path, layer_name="Underground cables")
    CableManager(FakeIface()).ensure_branch_index_field(layer)
    kind = _number(layer.fields().field("branch_index").type())
    del layer
    assert (_declared(path, "branch_index") or "").upper() == "INTEGER"
    assert kind in (_number(FieldType.Int), _number(FieldType.LongLong))


def test_route_lengths_are_number_columns(qgis_app, tmp_path):
    from fiberq.core.route_manager import RouteManager
    path, layer = _spatialite(tmp_path, layer_name="Route")
    iface = FakeIface()
    RouteManager(iface)._ensure_route_fields(layer)
    kinds = {column: _number(layer.fields().field(column).type())
             for column in ("duzina", "duzina_km")}
    del layer
    assert kinds == {"duzina": _number(FieldType.Double), "duzina_km": _number(FieldType.Double)}
    assert _declared(path, "duzina") and _declared(path, "duzina_km")
    assert iface.bar.warnings == []


def test_an_element_layer_gets_its_missing_columns_typed(qgis_app, tmp_path, monkeypatch, bar):
    """The element tool's own add, on a layer it found rather than made. An
    ODF layer with only naziv gets the dialog's numeric columns as numbers."""
    from fiberq.tools import element_tool
    from qgis.gui import QgsMapCanvas
    from qgis.PyQt.QtCore import QEvent, QPoint, Qt
    from qgis.gui import QgsMapMouseEvent
    from qgis.PyQt.QtWidgets import QDialog, QMessageBox

    class Accepting:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {"naziv": "E1"}

    monkeypatch.setattr(element_tool, "PrePlaceAttributesDialog", Accepting)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    path, layer = _spatialite(tmp_path, layer_name="ODF")
    project = QgsProject.instance()
    project.addMapLayer(layer)
    canvas = QgsMapCanvas()
    try:
        tool = element_tool.PlaceElementTool(canvas, "ODF")
        tool.canvasPressEvent(QgsMapMouseEvent(
            canvas, QEvent.Type.MouseButtonPress, QPoint(5, 5),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        if layer.isEditable():
            layer.rollBack()
    finally:
        project.removeMapLayer(layer.id())
        tool = canvas = None
        gc.collect()
    numeric = {"kapacitet": _declared(path, "kapacitet"), UUID: _declared(path, UUID)}
    assert numeric == {"kapacitet": "INTEGER", UUID: "TEXT"}, numeric
    assert bar.bar.warnings == []


# ---------------------------------------------------------------------------
# a refused column is said, not thrown away
# ---------------------------------------------------------------------------

def test_add_columns_names_a_read_only_layer(qgis_app, tmp_path):
    from fiberq.utils.compat import new_field
    from fiberq.utils.errors import OperationErrors, add_columns
    path, layer = _gpkg(tmp_path)
    layer.setReadOnly(True)
    errors = OperationErrors("test")
    answered = add_columns(layer, [new_field("tip", FieldType.String)], errors)
    del layer
    assert answered is False
    assert _declared(path, "tip") is None, "a read-only layer's file was altered"
    assert errors.problems == [("Poles", "could not add the column(s) tip: the layer is read-only")]


def test_add_columns_carries_the_provider_s_reason(qgis_app, tmp_path):
    from fiberq.utils.compat import new_field
    from fiberq.utils.errors import OperationErrors, add_columns
    path, layer = _gpkg(tmp_path)
    errors = OperationErrors("test")
    held = _hold(path)
    try:
        answered = add_columns(layer, [new_field("tip", FieldType.String)], errors)
        editable = layer.isEditable()
    finally:
        _release(held)
    del layer
    assert answered is False and editable is False
    assert len(errors.problems) == 1
    reason = errors.problems[0][1]
    assert reason.startswith("could not add the column(s) tip: "), reason
    assert "refused them without saying why" not in reason, "the provider's reason was lost"


def test_a_route_column_the_layer_refuses_is_reported(qgis_app, tmp_path):
    """Import route and merge went on with "naziv" and "duzina" missing and
    nothing said about why: the add's answer was thrown away."""
    from fiberq.core.route_manager import RouteManager
    path, layer = _gpkg(tmp_path, layer_name="Route")
    layer.setReadOnly(True)
    iface = FakeIface()
    RouteManager(iface)._ensure_route_fields(layer)
    del layer
    assert len(iface.bar.warnings) == 1, iface.bar.warnings
    assert "duzina, duzina_km, tip_trase: the layer is read-only" in iface.bar.warnings[0]


def test_a_pipe_layer_without_a_length_column_still_takes_the_pipe(qgis_app, tmp_path, bar):
    """The pipe tool added duzina_m inside its edit session, after setting it on
    the feature -- which raises KeyError on a layer without the column, so the
    add never ran and no pipe was laid. Now the column comes first."""
    from qgis.gui import QgsMapCanvas
    from fiberq.tools.pipe_tool import PipePlaceTool

    path = tmp_path / "pipes.gpkg"
    memory = QgsVectorLayer(
        "LineString?crs=EPSG:3857&field=materijal:string&field=kapacitet:string"
        "&field=fi:integer&field=od:string&field=do:string", "PE pipes", "memory")
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = "t"
    assert QgsVectorFileWriter.writeAsVectorFormatV3(
        memory, str(path), QgsCoordinateTransformContext(), opts)[0] == \
        QgsVectorFileWriter.WriterError.NoError
    held = {"layer": QgsVectorLayer(f"{path}|layername=t", "PE pipes", "ogr")}
    assert held["layer"].isValid()

    class Plugin:
        undo_manager = None

        def _ensure_pe_cev_layer(self):
            return held["layer"]

        def _build_path_across_network(self, *a):
            return None

        def _build_path_across_joined_trasa(self, *a):
            return None

        def _apply_pipe_style(self, *a):
            return None

    class Iface(FakeIface):
        def __init__(self, canvas):
            super().__init__()
            self._canvas = canvas

        def mapCanvas(self):
            return self._canvas

    canvas = QgsMapCanvas()
    tool = PipePlaceTool(Iface(canvas), Plugin(), "PE", {"materijal": "PE", "kapacitet": "1", "fi": 40})
    tool.points = [QgsPointXY(0, 0), QgsPointXY(100, 0)]
    tool._finish()
    if held["layer"].isEditable():
        held["layer"].rollBack()
    held.clear()
    tool = canvas = None
    gc.collect()
    con = sqlite3.connect(str(path))
    try:
        rows = con.execute('SELECT duzina_m FROM "t"').fetchall()
    finally:
        con.close()
    assert (_declared(path, "duzina_m") or "").upper() == "REAL"
    assert len(rows) == 1 and rows[0][0] == pytest.approx(100.0, rel=0.01), rows


# ---------------------------------------------------------------------------
# ensure_uuid_field answers for the data source
# ---------------------------------------------------------------------------

def test_a_column_that_cannot_be_saved_is_not_reported(qgis_app, tmp_path):
    """The RC answered True here and left the layer in edit mode with the
    column pending, so the next save failed on it."""
    from fiberq.utils.uuid_utils import ensure_uuid_field
    _path, layer = _gpkg(tmp_path)
    held = _hold(_path)
    try:
        answered = ensure_uuid_field(layer)
        editable = layer.isEditable()
        in_layer = layer.fields().indexOf(UUID) >= 0
    finally:
        _release(held)
    if layer.isEditable():
        layer.rollBack()
    del layer
    assert (answered, editable, in_layer) == (False, False, False)


def test_the_users_open_session_is_left_alone(qgis_app, tmp_path):
    """With the layer already in edit mode, the RC slipped its column into the
    user's own session, to be committed -- or refused -- with their work."""
    from fiberq.utils.uuid_utils import ensure_uuid_field
    path, layer = _gpkg(tmp_path)
    layer.startEditing()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(5, 5)))
    assert layer.addFeature(feature)
    held = _hold(path)
    try:
        answered = ensure_uuid_field(layer)
    finally:
        _release(held)
    state = (answered, layer.isEditable(), len(layer.editBuffer().addedAttributes()),
             len(layer.editBuffer().addedFeatures()))
    layer.rollBack()
    del layer
    assert state == (False, True, 0, 1), state


def test_an_open_session_keeps_its_work_when_the_column_is_added(qgis_app, tmp_path):
    """The other half: where the column can be added, it is, at the provider,
    and the user's buffered feature still saves. Characterisation -- the RC's
    first attempt did the same -- kept so the fix cannot trade one for the other."""
    from fiberq.utils.uuid_utils import ensure_uuid_field
    path, layer = _gpkg(tmp_path)
    layer.startEditing()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(5, 5)))
    assert layer.addFeature(feature)
    answered = ensure_uuid_field(layer)
    pending = len(layer.editBuffer().addedFeatures())
    saved = layer.commitChanges()
    del layer
    con = sqlite3.connect(str(path))
    try:
        rows = con.execute('SELECT COUNT(*) FROM "t"').fetchone()[0]
    finally:
        con.close()
    assert (answered, pending, saved, rows) == (True, 1, True, 2)
    assert (_declared(path, UUID) or "").upper() == "TEXT"


def test_a_read_only_layer_is_not_altered(qgis_app, tmp_path):
    """The RC's provider add went round the layer's read-only flag and wrote
    the column into the file."""
    from fiberq.utils.uuid_utils import ensure_uuid_field
    path, layer = _gpkg(tmp_path)
    layer.setReadOnly(True)
    answered = ensure_uuid_field(layer)
    del layer
    assert answered is False
    assert _declared(path, UUID) is None


def test_a_column_only_in_the_edit_buffer_does_not_count(qgis_app, tmp_path):
    from fiberq.utils.uuid_utils import ensure_uuid_field
    _path, layer = _gpkg(tmp_path)
    layer.startEditing()
    assert layer.addAttribute(QgsField(UUID, FieldType.String))
    answered = ensure_uuid_field(layer)
    layer.rollBack()
    del layer
    assert answered is False


def test_project_open_migration_does_not_claim_a_locked_layer(qgis_app, tmp_path):
    """The RC answered {'Poles': 2}: two UUIDs "assigned" into a column that was
    only pending in an edit buffer the save had already refused."""
    from fiberq.utils import uuid_utils
    path, layer = _gpkg(tmp_path)
    project = QgsProject()
    project.addMapLayer(layer)
    held = _hold(path)
    outcome = None
    try:
        try:
            outcome = uuid_utils.migrate_project_uuids(project)
        except uuid_utils.UuidMigrationError as exc:
            outcome = exc
    finally:
        _release(held)
        editable = layer.isEditable()
        if editable:
            layer.rollBack()
        project.removeAllMapLayers()
    assert isinstance(outcome, uuid_utils.UuidMigrationError), outcome
    assert editable is False
    assert _declared(path, UUID) is None


# ---------------------------------------------------------------------------
# a shapefile keeps ten characters of a column name
# ---------------------------------------------------------------------------

#: The shapefile refusal, as add_columns words it.
TOO_LONG = "a shapefile keeps only 10 characters of a column name"


def _shapefile(tmp_path, layer_name="Poles"):
    """A shapefile holding only ``naziv``, written the way a user exports one."""
    path = tmp_path / "t.shp"
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "ESRI Shapefile"
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        _seed(), str(path), QgsCoordinateTransformContext(), opts)
    assert result[0] == QgsVectorFileWriter.WriterError.NoError, result
    layer = QgsVectorLayer(str(path), layer_name, "ogr")
    assert layer.isValid()
    return path, layer


def _shapefile_columns(path):
    """The columns a fresh read of the file finds."""
    return QgsVectorLayer(str(path), "again", "ogr").fields().names()


@pytest.fixture
def logged(qgis_app):
    """What the column add and the identity column log, read off their own
    loggers: FiberQ's loggers do not propagate, so caplog never sees them, and
    on 4.2 the QGIS message log did not hand them back to Python here."""
    from fiberq.utils import errors, uuid_utils
    lines = []

    class Lines(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    handler = Lines(logging.WARNING)
    for logger in (errors.logger, uuid_utils.logger):
        logger.addHandler(handler)
    yield lines
    for logger in (errors.logger, uuid_utils.logger):
        logger.removeHandler(handler)


def test_a_shapefile_does_not_grow_a_column_per_call(qgis_app, tmp_path, logged):
    """The RC added fiberq_uuid as fiberq_uui, did not find it by its full name
    at the next call, and added it again: ['naziv', 'fiberq_uui', 'fiberq_u_1',
    'fiberq_u_2'] after three calls, one more at every placement and every
    project open, each logged as a column 'only in its edit buffer'."""
    from fiberq.utils.uuid_utils import ensure_uuid_field
    path, layer = _shapefile(tmp_path)
    answers = [ensure_uuid_field(layer) for _ in range(3)]
    del layer
    assert (answers, _shapefile_columns(path)) == ([False, False, False], ["naziv"])
    assert len([line for line in logged if f"fiberq_uuid: {TOO_LONG}" in line]) == 3, logged
    assert not [line for line in logged if "only in its edit buffer" in line], logged


def test_a_shapefile_takes_the_short_names_and_refuses_the_long_ones(qgis_app, tmp_path):
    """The element and cable tools ask for a mix. The short name is added as it
    always was; the long one is refused with the reason, where the RC answered
    True and the file got 'proizvodja'."""
    from fiberq.utils.compat import new_field
    from fiberq.utils.errors import OperationErrors, add_columns
    path, layer = _shapefile(tmp_path)
    errors = OperationErrors("test")
    answered = add_columns(layer, [new_field("kapacitet", FieldType.Int),
                                   new_field("proizvodjac", FieldType.String)], errors)
    in_layer = layer.fields().names()
    del layer
    assert answered is False
    assert (in_layer, _shapefile_columns(path)) == (["naziv", "kapacitet"], ["naziv", "kapacitet"])
    assert errors.problems == [("Poles", f"could not add the column(s) proizvodjac: {TOO_LONG}")]


def test_a_shapefile_branch_index_is_refused_not_renamed(qgis_app, tmp_path):
    """Branch cables' column is twelve characters. The RC answered True for a
    column the file holds as 'branch_ind', and added 'branch_i_1' next time."""
    from fiberq.core.cable_manager import CableManager
    path, layer = _shapefile(tmp_path, layer_name="Underground cables")
    iface = FakeIface()
    manager = CableManager(iface)
    answers = [manager.ensure_branch_index_field(layer) for _ in range(2)]
    del layer
    assert (answers, _shapefile_columns(path)) == ([False, False], ["naziv"])
    assert len(iface.bar.warnings) == 2, iface.bar.warnings
    assert all(f"branch_index: {TOO_LONG}" in w for w in iface.bar.warnings), iface.bar.warnings


def test_an_element_shapefile_does_not_grow_columns_per_placement(qgis_app, tmp_path, monkeypatch, bar):
    """The element tool asks for its columns at every placement. On a shapefile
    the RC added each long one again every time, shortened, and said nothing.
    Now the short ones are added once, the long ones are refused and said, and
    the element is still placed."""
    from fiberq.tools import element_tool
    from qgis.gui import QgsMapCanvas, QgsMapMouseEvent
    from qgis.PyQt.QtCore import QEvent, QPoint, Qt
    from qgis.PyQt.QtWidgets import QDialog, QMessageBox

    class Accepting:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {"naziv": "E1"}

    said = []
    monkeypatch.setattr(element_tool, "PrePlaceAttributesDialog", Accepting)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: said.append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: said.append(str(a[-1]))))
    path, layer = _shapefile(tmp_path, layer_name="ODF")
    project = QgsProject.instance()
    project.addMapLayer(layer)
    canvas = QgsMapCanvas()
    columns = []
    try:
        tool = element_tool.PlaceElementTool(canvas, "ODF")
        for _ in range(2):
            tool.canvasPressEvent(QgsMapMouseEvent(
                canvas, QEvent.Type.MouseButtonPress, QPoint(5, 5),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            columns.append(_shapefile_columns(path))
        if layer.isEditable():
            layer.rollBack()
        rows = layer.dataProvider().featureCount()
    finally:
        project.removeMapLayer(layer.id())
        tool = canvas = None
        gc.collect()
    short = ["naziv", "oznaka", "kapacitet", "ukupno_kj", "numeracija", "address_id", "stanje"]
    assert columns == [short, short], columns
    assert (rows, said.count("Element placed!")) == (3, 2), (rows, said)
    refused = [w for w in bar.bar.warnings if TOO_LONG in w]
    assert len(refused) == 2 and "proizvodjac" in refused[0], bar.bar.warnings
