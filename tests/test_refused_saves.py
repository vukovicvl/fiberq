"""A tool says it saved only what reached the file.

v1.6.0 QA finding Q14. Every write path below threw away the answers of
``startEditing()``, ``addFeature()`` and ``commitChanges()`` -- and then said
"Element placed!", "Manhole placed", "Route has been created!", "Pipe has been
laid.", "Service Area added", "Object added.", "The route has been split!" or
"Branching complete", over a GeoPackage another program held, a layer set
read-only, a trigger that refused the row, and (live, on PostGIS) a login that
may only read. Measured on 4.2.3 and 3.40.15 through each tool's own entry
point; the pole tool and Digitize from selection said nothing at all, so their
loss was silent. Split route did worse than lie: a GeoPackage commit is not
atomic across operations, its delete landed and its two inserts were refused,
and the route was gone from the file.

Every assertion reads the GeoPackage through SQLite, never through
``getFeatures()``, which reads through the edit buffer and would agree with the
bug. A save that cannot happen is a trigger that refuses the row (the R7
premise) or a layer set read-only -- never chmod, because CI runs as root. The
one locked-file test costs GDAL's busy wait. Each test collects plain values and
lets go of its layers before asserting, so a failure on an older tree reports
instead of crashing at teardown.
"""
import sqlite3

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsFeature, QgsGeometry,
    QgsPointXY, QgsProject, QgsRectangle, QgsVectorFileWriter, QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QPoint, Qt
from qgis.PyQt.QtWidgets import QDialog, QInputDialog, QMessageBox

UUID = "fiberq_uuid"
ROUTE = "naziv:string&field=duzina:double&field=duzina_km:double&field=tip_trase:string"


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------

class Bar:
    def __init__(self):
        self.warnings = []
        self.infos = []

    def pushWarning(self, title, text):
        self.warnings.append(f"{title}: {text}")

    def pushInfo(self, title, text):
        self.infos.append(f"{title}: {text}")

    def pushSuccess(self, title, text):
        self.infos.append(f"{title}: {text}")

    def pushCritical(self, title, text):
        self.warnings.append(f"{title}: {text}")


class Iface:
    def __init__(self, canvas):
        self.bar = Bar()
        self._canvas = canvas
        self.active = None

    def messageBar(self):
        return self.bar

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return None

    def activeLayer(self):
        return self.active

    def layerTreeView(self):
        return self

    def setCurrentLayer(self, *_a):
        return None

    def actionPan(self):
        return self

    def trigger(self):
        return None


class Undo:
    def __init__(self):
        self.recorded = []

    def record_add(self, layer, feature):
        self.recorded.append(layer.name())


class Env:
    """One canvas, one interface, every modal recorded."""

    def __init__(self, canvas, iface, said):
        self.canvas = canvas
        self.iface = iface
        self.said = said
        self.undo = Undo()

    @property
    def warnings(self):
        return self.iface.bar.warnings

    @property
    def infos(self):
        return self.iface.bar.infos

    def click(self, x, y, kind=QEvent.Type.MouseButtonRelease):
        device = self.canvas.getCoordinateTransform().transform(QgsPointXY(x, y))
        return QgsMapMouseEvent(self.canvas, kind, QPoint(int(device.x()), int(device.y())),
                                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                Qt.KeyboardModifier.NoModifier)


@pytest.fixture
def env(qgis_app, qgis_canvas, monkeypatch):
    """pytest-qgis's own canvas would render each layer added to the project in a
    worker thread, which on 4.2 can hold the GeoPackage a test is writing to."""
    import qgis.utils
    qgis_canvas.setRenderFlag(False)
    canvas = QgsMapCanvas()
    canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    canvas.resize(800, 800)
    canvas.show()
    canvas.setExtent(QgsRectangle(-400, -400, 400, 400))
    iface = Iface(canvas)
    monkeypatch.setattr(qgis.utils, "iface", iface)
    said = []
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name,
                            staticmethod(lambda *a, name=name, **k: said.append(f"{name}: {a[-1]}")))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("N1", True)))
    monkeypatch.setattr(QInputDialog, "getItem",
                        staticmethod(lambda *a, **k: (a[3][0] if len(a) > 3 else "Aerial", True)))
    from fiberq.core.schema_version import SCHEMA_VERSION_KEY, SCHEMA_VERSION_SCOPE
    project = QgsProject.instance()
    project.removeAllMapLayers()
    yield Env(canvas, iface, said)
    project.removeAllMapLayers()
    project.removeEntry(SCHEMA_VERSION_SCOPE, SCHEMA_VERSION_KEY)
    qgis_canvas.setRenderFlag(True)


def _gpkg(tmp_path, name, geometry, fields, rows=(), file="t.gpkg"):
    """A GeoPackage table "t" holding ``rows`` [(wkt, {column: value})], as layer ``name``."""
    path = tmp_path / file
    memory = QgsVectorLayer(f"{geometry}?crs=EPSG:3857&field={fields}", name, "memory")
    for wkt, values in rows:
        feature = QgsFeature(memory.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        for column, value in values.items():
            feature[column] = value
        assert memory.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "t"
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        memory, str(path), QgsCoordinateTransformContext(), options)
    assert result[0] == QgsVectorFileWriter.WriterError.NoError, result
    layer = QgsVectorLayer(f"{path}|layername=t", name, "ogr")
    assert layer.isValid()
    QgsProject.instance().addMapLayer(layer)
    return path, layer


def _block(path, operation):
    """A trigger that refuses every ``operation`` on the table: R7's premise."""
    con = sqlite3.connect(str(path))
    con.execute(f'CREATE TRIGGER no_{operation.lower()} BEFORE {operation} ON "t" '
                f"BEGIN SELECT RAISE(ABORT, 'blocked {operation}'); END;")
    con.commit()
    con.close()


def _on_disk(path, column):
    con = sqlite3.connect(str(path))
    try:
        return [row[0] for row in con.execute(f'SELECT "{column}" FROM "t" ORDER BY fid')]
    finally:
        con.close()


def _let_go(layer):
    """Roll back whatever a refused save left buffered, and drop the layer."""
    editable = layer.isEditable()
    if editable:
        layer.rollBack()
    QgsProject.instance().removeMapLayer(layer.id())
    return editable


def _said_blocked(env, operation="INSERT"):
    return [w for w in env.warnings if f"blocked {operation}" in w]


# ---------------------------------------------------------------------------
# the shared save
# ---------------------------------------------------------------------------

def test_add_and_save_keeps_a_refused_commit_for_the_user_to_save(env, tmp_path):
    from fiberq.utils.errors import OperationErrors, add_and_save
    path, layer = _gpkg(tmp_path, "Poles", "Point", "tip:string")
    _block(path, "INSERT")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1, 1)))
    errors = OperationErrors("test")
    saved = add_and_save(layer, [feature], errors)
    pending = len(layer.editBuffer().addedFeatures()) if layer.isEditable() else 0
    editable = _let_go(layer)
    assert (saved, editable, pending) == (False, True, 1)
    assert "blocked INSERT" in errors.problems[0][1], errors.problems


def test_add_and_save_says_a_layer_cannot_be_edited(env, tmp_path):
    from fiberq.utils.errors import OperationErrors, add_and_save
    path, layer = _gpkg(tmp_path, "Poles", "Point", "tip:string")
    layer.setReadOnly(True)
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1, 1)))
    errors = OperationErrors("test")
    saved = add_and_save(layer, [feature], errors)
    editable = _let_go(layer)
    assert (saved, editable, _on_disk(path, "tip")) == (False, False, [])
    assert errors.problems == [
        ("Poles", "the layer could not be opened for editing, so nothing was saved")]


def test_add_and_save_can_leave_an_open_session_unsaved(env, tmp_path):
    """The Objects tools' way: the user's session takes the feature, unsaved."""
    from fiberq.utils.errors import OperationErrors, add_and_save
    path, layer = _gpkg(tmp_path, "Objects", "Point", "naziv:string")
    assert layer.startEditing()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1, 1)))
    saved = add_and_save(layer, [feature], OperationErrors("test"), save_open_session=False)
    pending = len(layer.editBuffer().addedFeatures())
    editable = _let_go(layer)
    assert (saved, editable, pending, _on_disk(path, "naziv")) == (True, True, 1, [])


# ---------------------------------------------------------------------------
# point placements
# ---------------------------------------------------------------------------

def test_a_pole_the_file_refuses_is_said_and_not_recorded_for_undo(env, tmp_path):
    """The pole tool says nothing when it saves, so the loss was silent."""
    from fiberq.tools.point_tool import PointTool
    path, layer = _gpkg(tmp_path, "Poles", "Point", f"tip:string&field={UUID}:string",
                        [("Point (200 200)", {"tip": "POLE", UUID: "u0"})])
    _block(path, "INSERT")
    tool = PointTool(env.canvas, layer)
    tool.plugin = env
    tool.plugin.undo_manager = env.undo
    tool.canvasReleaseEvent(env.click(10, 10))
    _let_go(layer)
    assert len(_on_disk(path, "tip")) == 1
    assert _said_blocked(env), env.warnings
    assert env.undo.recorded == [], "an undo entry for a pole that never landed"


def test_a_manhole_the_file_refuses_is_not_called_placed(env, tmp_path):
    from fiberq.tools.manhole_tool import ManholePlaceTool
    path, layer = _gpkg(tmp_path, "Manholes", "Point", f"broj_okna:string&field={UUID}:string",
                        [("Point (200 200)", {"broj_okna": "MH0", UUID: "u0"})])
    _block(path, "INSERT")

    class Plugin:
        undo_manager = env.undo
        _manhole_pending_attrs = {"broj_okna": "MH1"}

        def _ensure_okna_layer(self):
            return layer

        def _apply_manhole_style(self, *a):
            return None

        def _move_layer_to_top(self, *a):
            return None

    ManholePlaceTool(env.iface, Plugin()).canvasReleaseEvent(env.click(10, 10))
    _let_go(layer)
    assert len(_on_disk(path, "broj_okna")) == 1
    assert not [i for i in env.infos if "Manhole placed" in i], env.infos
    assert _said_blocked(env), env.warnings
    assert env.undo.recorded == []


def _element_layer(tmp_path):
    from fiberq.utils.legacy_bridge import _default_fields_for
    kinds = {"int": "integer", "year": "integer", "double": "double"}
    fields = "&field=".join(f"{key}:{kinds.get(kind, 'string')}"
                            for key, _label, kind, _default, _options in _default_fields_for("ODF"))
    return _gpkg(tmp_path, "ODF", "Point", f"{fields}&field={UUID}:string",
                 [("Point (200 200)", {"naziv": "E0", UUID: "u0"})])


@pytest.fixture
def element_dialog(monkeypatch):
    from fiberq.tools import element_tool

    class Accepting:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {"naziv": "E1"}

    monkeypatch.setattr(element_tool, "PrePlaceAttributesDialog", Accepting)
    return element_tool


def test_an_element_on_a_layer_that_cannot_be_edited_is_not_called_placed(env, tmp_path, element_dialog):
    """Live, a read-only PostGIS login got "Element placed!" with nothing saved;
    a layer set read-only is the same refusal without a database."""
    path, layer = _element_layer(tmp_path)
    layer.setReadOnly(True)
    element_dialog.PlaceElementTool(env.canvas, "ODF").canvasPressEvent(
        env.click(10, 10, QEvent.Type.MouseButtonPress))
    _let_go(layer)
    assert _on_disk(path, "naziv") == ["E0"]
    assert not [s for s in env.said if "Element placed" in s], env.said
    assert [w for w in env.warnings if "could not be opened for editing" in w], env.warnings


def test_an_element_the_file_refuses_is_not_called_placed(env, tmp_path, element_dialog):
    path, layer = _element_layer(tmp_path)
    _block(path, "INSERT")
    element_dialog.PlaceElementTool(env.canvas, "ODF").canvasPressEvent(
        env.click(10, 10, QEvent.Type.MouseButtonPress))
    _let_go(layer)
    assert _on_disk(path, "naziv") == ["E0"]
    assert not [s for s in env.said if "Element placed" in s], env.said
    assert _said_blocked(env), env.warnings


def test_a_joint_closure_the_file_refuses_is_not_called_placed(env, tmp_path):
    from fiberq.tools.extension_tool import ExtensionTool
    path, layer = _gpkg(tmp_path, "Joint Closures", "Point", f"naziv:string&field={UUID}:string",
                        [("Point (200 200)", {"naziv": "J0", UUID: "u0"})])
    _block(path, "INSERT")
    ExtensionTool(env.canvas).canvasReleaseEvent(env.click(10, 10))
    _let_go(layer)
    assert _on_disk(path, "naziv") == ["J0"]
    assert not [s for s in env.said if "placed" in s], env.said
    assert _said_blocked(env), env.warnings


# ---------------------------------------------------------------------------
# lines and areas
# ---------------------------------------------------------------------------

def _route_layer(tmp_path, rows=(("LineString (100 200, 200 200)", {"naziv": "R0"}),)):
    return _gpkg(tmp_path, "Route", "LineString", f"{ROUTE}&field={UUID}:string", rows)


def test_a_manual_route_the_file_refuses_is_not_called_created(env, tmp_path):
    from fiberq.tools.route_tool import ManualRouteTool
    path, layer = _route_layer(tmp_path)
    _block(path, "INSERT")
    tool = ManualRouteTool(env.iface, None)
    tool.points = [QgsPointXY(0, 50), QgsPointXY(100, 50)]
    tool._finish_route()
    _let_go(layer)
    assert _on_disk(path, "naziv") == ["R0"]
    assert not [s for s in env.said if "has been created" in s], env.said
    assert _said_blocked(env), env.warnings
    assert tool.points == [], "the tool is reset either way"


def test_create_route_the_file_refuses_is_not_called_created(env, tmp_path, monkeypatch):
    from fiberq.core.route_manager import RouteManager
    path, layer = _route_layer(tmp_path)
    _block(path, "INSERT")
    poles = QgsVectorLayer("Point?crs=EPSG:3857&field=tip:string", "Poles", "memory")
    for x in (0, 80):
        pole = QgsFeature(poles.fields())
        pole.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, 70)))
        assert poles.dataProvider().addFeatures([pole])[0]
    QgsProject.instance().addMapLayer(poles)
    poles.selectAll()
    manager = RouteManager(env.iface)
    monkeypatch.setattr(manager, "_ask_route_type", lambda *a, **k: "podzemna")
    monkeypatch.setattr(manager, "stylize_route_layer", lambda *a, **k: None)
    manager.create_route()
    _let_go(layer)
    assert _on_disk(path, "naziv") == ["R0"]
    assert not [s for s in env.said if "has been created" in s], env.said
    assert _said_blocked(env), env.warnings


def test_a_pipe_the_file_refuses_is_not_called_laid(env, tmp_path):
    from fiberq.tools.pipe_tool import PipePlaceTool
    path, layer = _gpkg(
        tmp_path, "PE pipes", "LineString",
        "materijal:string&field=kapacitet:string&field=fi:integer&field=duzina_m:double"
        f"&field=od:string&field=do:string&field={UUID}:string",
        [("LineString (100 200, 200 200)", {"materijal": "P0", UUID: "u0"})])
    _block(path, "INSERT")

    class Plugin:
        undo_manager = env.undo

        def _ensure_pe_cev_layer(self):
            return layer

        def _build_path_across_network(self, *a):
            return None

        def _build_path_across_joined_trasa(self, *a):
            return None

        def _apply_pipe_style(self, *a):
            return None

    tool = PipePlaceTool(env.iface, Plugin(), "PE", {"materijal": "PE", "kapacitet": "1", "fi": 40})
    tool.points = [QgsPointXY(0, 60), QgsPointXY(100, 60)]
    tool._finish()
    _let_go(layer)
    assert _on_disk(path, "materijal") == ["P0"]
    assert not [i for i in env.infos if "has been laid" in i], env.infos
    assert _said_blocked(env), env.warnings
    assert tool.points == [], "the tool is reset either way"


def _area_layer(tmp_path):
    return _gpkg(tmp_path, "Service Area", "Polygon",
                 "name:string&field=created_at:string&field=area_m2:double&field=perim_m:double"
                 f"&field=count:integer&field={UUID}:string",
                 [("Polygon ((200 200, 220 200, 220 220, 200 200))", {"name": "A0", UUID: "u0"})])


def test_a_drawn_service_area_the_file_refuses_is_not_called_added(env, tmp_path):
    from fiberq.tools.region_tool import DrawRegionPolygonTool

    class Core:
        undo_manager = env.undo
        iface = env.iface

    path, layer = _area_layer(tmp_path)
    _block(path, "INSERT")
    tool = DrawRegionPolygonTool(env.iface, Core())
    tool.points = [QgsPointXY(0, 0), QgsPointXY(50, 0), QgsPointXY(50, 50)]
    tool._finish_polygon()
    _let_go(layer)
    assert _on_disk(path, "name") == ["A0"]
    assert not [i for i in env.infos if "Service Area added" in i], env.infos
    assert _said_blocked(env), env.warnings
    assert env.undo.recorded == []


def test_a_service_area_from_a_selection_the_file_refuses_is_not_called_created(env, tmp_path):
    from fiberq.core.layer_manager import _create_region_from_selection

    class Core:
        iface = env.iface

    path, layer = _area_layer(tmp_path)
    _block(path, "INSERT")
    poles = QgsVectorLayer("Point?crs=EPSG:3857&field=tip:string", "Poles", "memory")
    pole = QgsFeature(poles.fields())
    pole.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(5, 5)))
    assert poles.dataProvider().addFeatures([pole])[0]
    QgsProject.instance().addMapLayer(poles)
    poles.selectAll()
    answered = _create_region_from_selection(Core(), "R1", 10.0)
    _let_go(layer)
    assert answered is False
    assert _on_disk(path, "name") == ["A0"]
    assert not [s for s in env.said if "Created:" in s], env.said
    assert _said_blocked(env), env.warnings


@pytest.fixture
def object_dialog(monkeypatch):
    import fiberq.tools
    from fiberq.tools import object_tools

    class Accepting:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {"naziv": "B1", "tip": "house"}

    monkeypatch.setattr(object_tools, "ObjectPropertiesDialog", Accepting)
    monkeypatch.setattr(fiberq.tools, "ObjectPropertiesDialog", Accepting)
    return object_tools


def _objects_layer(tmp_path):
    return _gpkg(tmp_path, "Objects", "Polygon",
                 "tip:string&field=spratova:integer&field=podzemnih:integer&field=ulica:string"
                 f"&field=broj:string&field=naziv:string&field=napomena:string&field={UUID}:string",
                 [("Polygon ((200 200, 220 200, 220 220, 200 200))", {"naziv": "B0", UUID: "u0"})])


def test_an_object_the_file_refuses_is_not_called_added(env, tmp_path, object_dialog):
    path, layer = _objects_layer(tmp_path)
    _block(path, "INSERT")

    class Core:
        undo_manager = env.undo
        iface = env.iface

    object_dialog.DrawObjectNTool(env.iface, Core())._finish(
        QgsGeometry.fromWkt("Polygon ((0 0, 30 0, 30 30, 0 0))"))
    _let_go(layer)
    assert _on_disk(path, "naziv") == ["B0"]
    assert not [i for i in env.infos if "Object added" in i], env.infos
    assert _said_blocked(env), env.warnings
    assert env.undo.recorded == []


def test_a_digitized_object_the_file_refuses_is_said(env, tmp_path, object_dialog):
    """Digitize from selection said nothing either way, so a refusal was silent."""
    from fiberq.ui.objects_ui import ObjectsUI
    path, layer = _objects_layer(tmp_path)
    _block(path, "INSERT")
    source = QgsVectorLayer("Polygon?crs=EPSG:3857", "Footprints", "memory")
    footprint = QgsFeature(source.fields())
    footprint.setGeometry(QgsGeometry.fromWkt("Polygon ((0 0, 30 0, 30 30, 0 0))"))
    assert source.dataProvider().addFeatures([footprint])[0]
    QgsProject.instance().addMapLayer(source)
    source.selectAll()
    env.iface.active = source

    class Toolbar:
        def addWidget(self, *a):
            return None

    class Core:
        iface = env.iface
        toolbar = Toolbar()
        actions = []

    ObjectsUI(Core())
    digitize = [a for a in Core.actions if a.text() == "Digitized object (from selection)"]
    assert len(digitize) == 1, [a.text() for a in Core.actions]
    digitize[0].trigger()
    _let_go(layer)
    assert _on_disk(path, "naziv") == ["B0"]
    assert _said_blocked(env), env.warnings


def _draw_object(env, object_dialog):
    class Core:
        undo_manager = env.undo
        iface = env.iface

    object_dialog.DrawObjectNTool(env.iface, Core())._finish(
        QgsGeometry.fromWkt("Polygon ((0 0, 30 0, 30 30, 0 0))"))


def test_an_object_in_the_users_open_session_is_not_called_added(env, tmp_path, object_dialog):
    """The draw tool leaves the object in a session the user already had open,
    unsaved, and said "Object added." as if it had been saved."""
    path, layer = _objects_layer(tmp_path)
    assert layer.startEditing()
    _draw_object(env, object_dialog)
    pending = len(layer.editBuffer().addedFeatures())
    editable = _let_go(layer)
    assert (editable, pending, _on_disk(path, "naziv")) == (True, 1, ["B0"])
    assert not [i for i in env.infos if "Object added" in i], env.infos
    assert [i for i in env.infos if "not saved yet" in i], env.infos


def test_a_saved_object_is_still_called_added(env, tmp_path, object_dialog):
    """Characterisation: the saved path keeps its message."""
    path, layer = _objects_layer(tmp_path)
    _draw_object(env, object_dialog)
    editable = _let_go(layer)
    assert (editable, _on_disk(path, "naziv")) == (False, ["B0", "B1"])
    assert [i for i in env.infos if "Object added" in i] == ["Objects: Object added."], env.infos
    assert not [i for i in env.infos if "not saved yet" in i], env.infos


# ---------------------------------------------------------------------------
# Split route: the halves before the delete
# ---------------------------------------------------------------------------

def _split(env, layer):
    from fiberq.tools.breakpoint_tool import BreakpointTool
    tool = BreakpointTool(env.canvas, env.iface, None)
    feature = next(layer.getFeatures())
    tool.snap_info = {"feat": feature, "geom": feature.geometry(), "point": QgsPointXY(150, 200),
                      "seg_idx": 1, "dist": 0.0}
    tool.canvasReleaseEvent(env.click(150, 200))


def test_a_split_the_file_refuses_keeps_the_route(env, tmp_path):
    """Measured: two rows became one, and "The route has been split!"."""
    path, layer = _route_layer(tmp_path, rows=(
        ("LineString (100 200, 200 200)", {"naziv": "R0", "tip_trase": "podzemna", UUID: "u0"}),
        ("LineString (0 300, 50 300)", {"naziv": "R9", UUID: "u9"})))
    _block(path, "INSERT")
    _split(env, layer)
    _let_go(layer)
    assert _on_disk(path, "naziv") == ["R0", "R9"], "the split route was lost"
    assert not [s for s in env.said if "has been split" in s], env.said
    assert _said_blocked(env), env.warnings


def test_a_split_whose_original_cannot_be_removed_says_so(env, tmp_path):
    """The halves are saved first, so a refused delete leaves a duplicate the
    user is told about -- not a route that vanished."""
    path, layer = _route_layer(tmp_path, rows=(
        ("LineString (100 200, 200 200)", {"naziv": "R0", "tip_trase": "podzemna", UUID: "u0"}),))
    _block(path, "DELETE")
    _split(env, layer)
    _let_go(layer)
    assert _on_disk(path, "naziv") == ["R0", "R0_a", "R0_b"]
    assert [s for s in env.said if "could not be removed" in s], env.said
    assert not [s for s in env.said if "has been split" in s], env.said


def test_a_split_saves_both_halves(env, tmp_path):
    """Characterisation: the path that always worked still does."""
    path, layer = _route_layer(tmp_path, rows=(
        ("LineString (100 200, 200 200)", {"naziv": "R0", "tip_trase": "podzemna", UUID: "u0"}),))
    _split(env, layer)
    editable = _let_go(layer)
    assert _on_disk(path, "naziv") == ["R0_a", "R0_b"]
    assert editable is False
    assert [s for s in env.said if "has been split" in s], env.said
    assert env.warnings == []


def test_a_split_in_an_open_session_stays_unsaved_in_it(env, tmp_path):
    """As Merge routes does: the user's session takes the split, and is not
    saved behind their back -- the old one-session split committed it."""
    path, layer = _route_layer(tmp_path, rows=(
        ("LineString (100 200, 200 200)", {"naziv": "R0", "tip_trase": "podzemna", UUID: "u0"}),))
    assert layer.startEditing()
    _split(env, layer)
    buffered = (len(layer.editBuffer().addedFeatures()), len(layer.editBuffer().deletedFeatureIds()))
    editable = _let_go(layer)
    assert (editable, buffered) == (True, (2, 1))
    assert _on_disk(path, "naziv") == ["R0"]
    assert [s for s in env.said if "not saved yet" in s], env.said


# ---------------------------------------------------------------------------
# attribute writes
# ---------------------------------------------------------------------------

def _cables(tmp_path, tip="Optical"):
    return _gpkg(tmp_path, "Underground cables", "LineString",
                 f"tip:string&field=branch_index:integer&field={UUID}:string",
                 [("LineString (0 0, 100 0)", {"tip": tip, UUID: "u0"}),
                  ("LineString (100 0, 0 0)", {"tip": tip, UUID: "u1"})])


def test_branch_indices_the_file_refuses_are_not_called_complete(env, tmp_path):
    from fiberq.core.cable_manager import CableManager
    path, layer = _cables(tmp_path)
    _block(path, "UPDATE")
    env.iface.active = layer
    CableManager(env.iface).branch_cables_offset()
    _let_go(layer)
    assert _on_disk(path, "branch_index") == [None, None]
    assert not [i for i in env.infos if "Branching complete" in i], env.infos
    assert _said_blocked(env, "UPDATE"), env.warnings


def test_branch_indices_on_a_read_only_layer_are_not_counted(env, tmp_path):
    """Measured: "updated cables: 2" with every change refused."""
    from fiberq.core.cable_manager import CableManager
    path, layer = _cables(tmp_path)
    layer.setReadOnly(True)
    groups, updated = CableManager(env.iface).compute_branch_indices_for_layer(layer, tol_m=1.3)
    _let_go(layer)
    assert (groups, updated) == (1, 0)
    assert [w for w in env.warnings if "could not be opened for editing" in w], env.warnings


def test_a_cable_type_rewrite_the_file_refuses_is_said(env, tmp_path):
    """The restyle's rewrite of opticki -> Optical left the layer in edit mode
    with the change pending, and nothing said why."""
    from fiberq.utils.field_aliases import _migrate_cable_type_values
    path, layer = _cables(tmp_path, tip="opticki")
    _block(path, "UPDATE")
    _migrate_cable_type_values(layer)
    _let_go(layer)
    assert _on_disk(path, "tip") == ["opticki", "opticki"]
    assert _said_blocked(env, "UPDATE"), env.warnings


# ---------------------------------------------------------------------------
# the project-open migration counts only what it saved
# ---------------------------------------------------------------------------

def _poles_without_ids(tmp_path):
    return _gpkg(tmp_path, "Poles", "Point", f"tip:string&field={UUID}:string",
                 [("Point (200 200)", {"tip": "POLE"}), ("Point (210 210)", {"tip": "POLE"})])


def _empty(value):
    return value is None or (hasattr(value, "isNull") and value.isNull()) or str(value).strip() in ("", "NULL")


def test_ids_written_into_an_open_session_are_not_called_assigned(env):
    """Measured: "assigned 2 UUIDs", the project stamped 1.0 and never
    retried, the IDs only in the buffer. A memory layer is premise enough --
    the layer only has to be in edit mode -- and keeps GDAL out of it: on 4.2,
    deep in a full run, a GeoPackage read just after entering edit mode lost a
    race with another reader of the file and found it unopenable."""
    from fiberq.core import migrations, schema_version
    layer = QgsVectorLayer(f"Point?crs=EPSG:3857&field=tip:string&field={UUID}:string", "Poles", "memory")
    for x in (200, 210):
        pole = QgsFeature(layer.fields())
        pole.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, x)))
        pole["tip"] = "POLE"
        assert layer.dataProvider().addFeatures([pole])[0]
    project = QgsProject.instance()
    project.addMapLayer(layer)
    schema_version.write_project_schema_version("0", project)
    assert layer.startEditing()
    report = migrations.run_migrations(project)
    pending = len(layer.editBuffer().changedAttributeValues())
    stored = [feature[UUID] for feature in layer.dataProvider().getFeatures()]
    _let_go(layer)
    assert (report.ran, pending) == (False, 0), report
    assert "assigned" not in report.summary()
    assert schema_version.read_project_schema_version(project) == "0"
    assert all(_empty(value) for value in stored), stored


def test_project_open_says_when_the_upgrade_did_not_finish(env, tmp_path):
    """It was logged at debug level, which reaches nobody."""
    from fiberq.core import schema_version
    from fiberq.main_plugin import FiberQPlugin
    path, layer = _poles_without_ids(tmp_path)
    _block(path, "UPDATE")
    project = QgsProject.instance()
    schema_version.write_project_schema_version("0", project)

    class Stub:
        iface = env.iface

        def tr(self, text, *a):
            return text

    FiberQPlugin._run_schema_migrations(Stub())
    editable = _let_go(layer)
    assert editable is False, "the migration's own session was left open"
    assert _on_disk(path, UUID) == [None, None]
    upgrade = [w for w in env.warnings if "could not finish upgrading" in w]
    assert len(upgrade) == 1, env.warnings
    assert not [i for i in env.infos if "assigned" in i], env.infos


def test_a_locked_project_file_is_tried_once_per_open(env, tmp_path):
    """After a refused upgrade the identity backfill ran the same refused write
    again, after another busy wait on the same locked file."""
    from fiberq.core import schema_version
    from fiberq.main_plugin import FiberQPlugin
    from fiberq.utils import uuid_utils
    path, layer = _poles_without_ids(tmp_path)
    project = QgsProject.instance()
    schema_version.write_project_schema_version("0", project)
    calls = []
    real = uuid_utils.migrate_project_uuids

    def counted(*a, **k):
        calls.append(1)
        return real(*a, **k)

    class Stub:
        iface = env.iface

        def tr(self, text, *a):
            return text

    held = sqlite3.connect(str(path), isolation_level=None, timeout=1)
    held.execute("BEGIN EXCLUSIVE")
    try:
        uuid_utils.migrate_project_uuids = counted
        FiberQPlugin._run_schema_migrations(Stub())
    finally:
        uuid_utils.migrate_project_uuids = real
        held.execute("ROLLBACK")
        held.close()
    _let_go(layer)
    assert len(calls) == 1, f"migrate_project_uuids ran {len(calls)} times"
    assert [w for w in env.warnings if "could not finish upgrading" in w], env.warnings


# ---------------------------------------------------------------------------
# Delete selected counts what it saved
# ---------------------------------------------------------------------------

def _delete_selected(env):
    """``FiberQPlugin.delete_selected`` with only what it reads of the plugin."""
    from fiberq.main_plugin import FiberQPlugin

    class Plugin:
        iface = env.iface

        def tr(self, text, *a):
            return text

        def _cables_behind(self, *a):
            return set()

        def _recompute_slack_for_cable(self, *a):
            return None

    FiberQPlugin.delete_selected(Plugin())


def test_deletions_a_refused_placement_left_unsaved_are_not_called_deleted(env, tmp_path):
    """Measured on the RC: a pole the file refused stays buffered, as
    check_commit keeps every refused commit, so the layer is in edit mode.
    Delete selected then said "Deleted 2 selected features from all layers."
    with the row still in the file and the deletions only in that buffer."""
    from fiberq.tools.point_tool import PointTool
    path, layer = _gpkg(tmp_path, "Poles", "Point", f"tip:string&field={UUID}:string",
                        [("Point (200 200)", {"tip": "POLE", UUID: "u0"})])
    _block(path, "INSERT")
    tool = PointTool(env.canvas, layer)
    tool.plugin = env
    tool.plugin.undo_manager = env.undo
    tool.canvasReleaseEvent(env.click(10, 10))
    layer.selectByExpression("\"tip\" = 'POLE'")
    selected = layer.selectedFeatureCount()
    _delete_selected(env)
    _let_go(layer)
    assert selected == 2
    assert _on_disk(path, "tip") == ["POLE"]
    assert not [s for s in env.said if "Deleted" in s and "not saved yet" not in s], env.said
    assert [s for s in env.said if "2 of the selected features" in s and "not saved yet" in s], env.said


def test_saved_and_unsaved_deletions_are_counted_apart(env, tmp_path):
    """One layer saved, one the user had open: the RC said "Deleted 2" for both."""
    saved_path, saved = _gpkg(tmp_path, "Poles", "Point", "tip:string",
                              [("Point (200 200)", {"tip": "P0"})], file="a.gpkg")
    open_path, opened = _gpkg(tmp_path, "Manholes", "Point", "tip:string",
                              [("Point (210 210)", {"tip": "M0"})], file="b.gpkg")
    assert opened.startEditing()
    saved.selectAll()
    opened.selectAll()
    _delete_selected(env)
    pending = len(opened.editBuffer().deletedFeatureIds())
    editable = (_let_go(saved), _let_go(opened))
    assert (editable, pending) == ((False, True), 1)
    assert (_on_disk(saved_path, "tip"), _on_disk(open_path, "tip")) == ([], ["M0"])
    assert len(env.said) == 1, env.said
    assert "Deleted 1 selected features from all layers." in env.said[0], env.said
    assert "1 of the selected features" in env.said[0] and "not saved yet" in env.said[0], env.said
    assert env.warnings == []


def _csv_poles(tmp_path):
    """Poles on a data source that does not allow deleting: delimited text
    stands in for a database login that may only read."""
    from qgis.core import QgsVectorDataProvider
    path = tmp_path / "poles.csv"
    path.write_text('wkt,tip\n"POINT (200 200)",POLE\n', encoding="utf-8")
    layer = QgsVectorLayer(f"{path.as_uri()}?type=csv&delimiter=,&wktField=wkt&crs=EPSG:3857",
                           "Poles", "delimitedtext")
    assert layer.isValid()
    assert not layer.dataProvider().capabilities() & QgsVectorDataProvider.Capability.DeleteFeatures
    QgsProject.instance().addMapLayer(layer)
    return path, layer


@pytest.mark.parametrize("premise", ["no delete capability", "read-only layer"])
def test_a_layer_that_cannot_delete_is_named_not_passed_over(env, tmp_path, premise):
    """Live, as a login that may only read: the layer was skipped without a
    word and the dialog said "No selected features to delete." -- also after a
    refusal it had just reported, on a layer set read-only."""
    if premise == "no delete capability":
        path, layer = _csv_poles(tmp_path)
        reason = "Poles: its data source does not allow deleting features"
    else:
        path, layer = _gpkg(tmp_path, "Poles", "Point", "tip:string", [("Point (200 200)", {"tip": "POLE"})])
        layer.setReadOnly(True)
        reason = "Poles: this layer could not be opened for editing"
    layer.selectAll()
    _delete_selected(env)
    editable = _let_go(layer)
    if premise == "no delete capability":
        on_disk = path.read_text(encoding="utf-8").splitlines()[1:]
    else:
        on_disk = _on_disk(path, "tip")
    assert editable is False
    assert len(on_disk) == 1, on_disk
    assert not [s for s in env.said if "No selected features to delete." in s], env.said
    assert [w for w in env.warnings if reason in w], env.warnings


def test_nothing_selected_still_says_so(env, tmp_path):
    """Characterisation: with no selection anywhere the dialog is unchanged."""
    _path, layer = _gpkg(tmp_path, "Poles", "Point", "tip:string", [("Point (200 200)", {"tip": "POLE"})])
    _delete_selected(env)
    _let_go(layer)
    assert env.said == ["information: No selected features to delete."]
    assert env.warnings == []
