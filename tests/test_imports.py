"""Import points and Import route survive the files people actually have.

WP4 4.2 item R6. Both importers walked a file's features in one unguarded
loop, inside one editing session whose result nobody checked. Three separate
ways that ends badly, all three measured on 3.44.15 and 4.0.3:

**A geometry that is not a line.** ``asPolyline()`` on a point is
``TypeError: Point geometry cannot be converted to a polyline``, and on a null
geometry ``ValueError: Null geometry cannot be converted to a polyline``. The
route importer's own guard --

    polyline = geom.asPolyline()
    if polyline and len(polyline) >= 2:

-- could therefore never run: importing a point GeoJSON, which is the obvious
thing to try, ended the import with the Route layer **left in edit mode**
holding whatever had been added so far.

**A reprojection that cannot work.** This is the one that does not look like a
failure. ``QgsGeometry.transform`` does **not** raise for an out-of-domain
coordinate: it answers ``GeometryOperationResult.Success`` and leaves
``LineString (inf inf, inf inf)`` behind. So catching ``QgsCsException`` -- which
is what the build plan assumed -- would not have been enough. The importer
wrote infinite geometry into the project and reported success.
``utils.geometry.transformed`` treats both outcomes as "this feature cannot be
reprojected", and the caller skips and counts it.

**Discarded results.** ``addFeature``, ``addAttributes`` and ``commitChanges``
all answered a bool that was thrown away, so "Imported 42 points" was printed
without knowing whether any of the 42 had arrived.

Both importers are now scoped in an **edit command** and only commit if they
opened the editing session themselves. A user who already had unsaved edits
keeps them: the import joins their undo stack instead of committing their
buffer for them, and a failure destroys only the import's own command.
"""
import json
import os

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.utils.geometry import is_finite, line_vertices, transformed


class FakeBar:
    def __init__(self):
        self.warnings = []
        self.infos = []
        #: Every entry as ``(level, title, text)``, in the order it was pushed.
        self.entries = []

    def pushWarning(self, title, text):
        self.warnings.append(text)
        self.entries.append(("warning", title, text))

    def pushInfo(self, title, text):
        self.infos.append(text)
        self.entries.append(("info", title, text))


class FakeCanvas:
    def __init__(self, crs):
        self._crs = crs

    def mapSettings(self):
        return self

    def destinationCrs(self):
        return self._crs


class FakeIface:
    def __init__(self, crs=None):
        self.bar = FakeBar()
        self._canvas = FakeCanvas(crs or QgsCoordinateReferenceSystem("EPSG:3857"))

    def messageBar(self):
        return self.bar

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return None


@pytest.fixture(autouse=True)
def quiet_dialogs(monkeypatch):
    said = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: said.append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: said.append(str(a[-1]))))
    return said


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


def _geojson(tmp_path, name, features):
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection",
                   "crs": {"type": "name",
                           "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                   "features": features}, fh)
    return path


def _feature(geometry):
    return {"type": "Feature", "properties": {"name": "x"}, "geometry": geometry}


def _line(coords):
    return {"type": "LineString", "coordinates": coords}


def _point(xy):
    return {"type": "Point", "coordinates": list(xy)}


def _route_layer(project):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    layer.dataProvider().addAttributes([
        QgsField("naziv", QVariant.String),
        QgsField("duzina", QVariant.Double),
        QgsField("duzina_km", QVariant.Double),
        QgsField("tip_trase", QVariant.String),
    ])
    layer.updateFields()
    project.addMapLayer(layer)
    return layer


# ---------------------------------------------------------------------------
# The primitives
# ---------------------------------------------------------------------------

def test_as_polyline_raises_on_a_point(qgis_app):
    """The guard that could never run, pinned."""
    with pytest.raises(TypeError):
        QgsGeometry.fromPointXY(QgsPointXY(1, 1)).asPolyline()


def test_line_vertices_answers_empty_for_a_point(qgis_app):
    assert line_vertices(QgsGeometry.fromPointXY(QgsPointXY(1, 1))) == []


def test_line_vertices_answers_empty_for_a_null_geometry(qgis_app):
    assert line_vertices(QgsGeometry()) == []


def test_a_failed_reprojection_does_not_raise_but_is_not_finite(qgis_app):
    """The measured surprise: Success, and inf inf in the geometry."""
    xform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsCoordinateTransformContext())
    geom = QgsGeometry.fromPolylineXY([QgsPointXY(1e30, 1e30), QgsPointXY(2e30, 2e30)])
    geom.transform(xform)          # returns Success
    assert not is_finite(geom), "this is why catching QgsCsException is not enough"


def test_transformed_refuses_an_infinite_result(qgis_app):
    xform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsCoordinateTransformContext())
    bad = QgsGeometry.fromPolylineXY([QgsPointXY(1e30, 1e30), QgsPointXY(2e30, 2e30)])
    assert transformed(bad, xform) is None


def test_transformed_leaves_the_source_alone(qgis_app):
    """It works on a copy, so a rejected feature is not left half-moved."""
    xform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsCoordinateTransformContext())
    source = QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(1, 1)])
    before = source.asWkt()
    assert transformed(source, xform) is not None
    assert source.asWkt() == before


def test_transformed_moves_an_ordinary_geometry(qgis_app):
    xform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsCoordinateTransformContext())
    moved = transformed(QgsGeometry.fromPointXY(QgsPointXY(0.0, 0.0)), xform)
    assert moved is not None and is_finite(moved)


# ---------------------------------------------------------------------------
# Import route
# ---------------------------------------------------------------------------

def _route_manager(project, iface):
    from fiberq.core.route_manager import RouteManager

    manager = RouteManager.__new__(RouteManager)
    manager.iface = iface
    manager.style_manager = None
    return manager


def _import_routes(project, manager, path, route_layer):
    """Drive the importer with the file dialog and the type prompt answered."""
    from fiberq.core.route_manager import _ImportSource
    from fiberq.utils.errors import OperationErrors

    imported = QgsVectorLayer(path, "Import_route_tmp", "ogr")
    assert imported.isValid(), path
    with OperationErrors("Import route", manager.iface) as errors:
        result = manager._add_imported_routes(
            [_ImportSource(imported, route_layer.crs())], route_layer, "podzemna", errors)
    return result


def test_a_point_file_is_skipped_not_fatal(project, tmp_path):
    """v1.5.0: TypeError, and the Route layer left in edit mode."""
    path = _geojson(tmp_path, "points.geojson",
                    [_feature(_point((0.0, 0.0))), _feature(_point((1.0, 1.0)))])
    route = _route_layer(project)
    iface = FakeIface()
    manager = _route_manager(project, iface)

    added, skipped, saved = _import_routes(project, manager, path, route)

    assert (added, skipped) == (0, 2)
    assert saved is True, "the importer opened the session, so it owns the commit"
    assert route.featureCount() == 0
    assert not route.isEditable(), "the layer must not be left in edit mode"


def test_a_mixed_file_imports_the_lines_and_counts_the_rest(project, tmp_path):
    path = _geojson(tmp_path, "mixed.geojson", [
        _feature(_line([[0.0, 0.0], [0.001, 0.0]])),
        _feature(_point((0.0, 0.0))),
        _feature(_line([[0.002, 0.0], [0.003, 0.0]])),
        _feature(None),
    ])
    route = _route_layer(project)
    manager = _route_manager(project, FakeIface())

    added, skipped, saved = _import_routes(project, manager, path, route)

    assert added == 2
    assert skipped == 2
    assert saved is True
    assert route.featureCount() == 2
    assert not route.isEditable()


def test_a_multipart_line_imports_every_part(project, tmp_path):
    path = _geojson(tmp_path, "multi.geojson", [_feature({
        "type": "MultiLineString",
        "coordinates": [[[0.0, 0.0], [0.001, 0.0]], [[0.002, 0.0], [0.003, 0.0]]]})])
    route = _route_layer(project)
    manager = _route_manager(project, FakeIface())

    added, skipped, saved = _import_routes(project, manager, path, route)

    assert (added, skipped) == (2, 0)
    assert saved is True
    assert route.featureCount() == 2


def test_every_imported_route_gets_a_length_and_a_type(project, tmp_path):
    path = _geojson(tmp_path, "one.geojson",
                    [_feature(_line([[0.0, 0.0], [0.001, 0.0]]))])
    route = _route_layer(project)
    manager = _route_manager(project, FakeIface())

    _import_routes(project, manager, path, route)

    feat = next(route.getFeatures())
    assert feat["tip_trase"] == "podzemna"
    assert float(feat["duzina"]) > 0.0
    assert feat["duzina_km"] == pytest.approx(float(feat["duzina"]) / 1000.0, abs=0.01)


# ---------------------------------------------------------------------------
# f010/f039: the importer must say which of the four things happened
# ---------------------------------------------------------------------------

def test_ensuring_the_route_fields_does_not_touch_the_edit_session(project):
    """f007. The sibling test above calls _add_imported_routes directly, so it
    never reached this function -- which every real Import route goes through
    first, and which called startEditing() and commitChanges() unconditionally.

    Measured on 3.44.15: one unsaved route in the buffer before, committed to the
    provider and the session closed after, with nothing said. Every column here
    is added through the data provider, which bypasses the edit buffer, so the
    commit was never writing the fields -- only the user's work.
    """
    route = _route_layer(project)
    route.startEditing()
    pending = QgsFeature(route.fields())
    pending.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 9), QgsPointXY(1, 9)]))
    pending.setAttribute("naziv", "the user's own line")
    assert route.addFeature(pending)
    manager = _route_manager(project, FakeIface())

    manager._ensure_route_fields(route)

    assert route.isEditable(), "the session was not ours to close"
    assert len(route.editBuffer().addedFeatures()) == 1, "nor their work ours to save"
    assert len(list(route.dataProvider().getFeatures())) == 0
    route.rollBack()


@pytest.mark.parametrize("start_editing", [False, True])
def test_the_route_fields_are_still_added(project, start_editing):
    """And the columns do arrive, session or no session -- that is the point."""
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
    layer.updateFields()
    project.addMapLayer(layer)
    if start_editing:
        layer.startEditing()
    manager = _route_manager(project, FakeIface())

    manager._ensure_route_fields(layer)

    for column in ("naziv", "duzina", "duzina_km", "tip_trase"):
        assert column in layer.fields().names(), column
    assert layer.isEditable() is start_editing, "the session is left as it was found"


def test_a_route_layer_missing_a_column_is_reported_not_raised(project, tmp_path):
    """f009. QgsFeature.setAttribute RAISES KeyError for an absent field.

    _add_one_route sets four attributes outside any try, and the enclosing except
    tuple did not list KeyError -- so a Route layer without "naziv" sent
    KeyError('naziv') out of the Qt slot as a QGIS crash dialog, with the edit
    command still open and the layer still editable. Measured on main.
    """
    path = _geojson(tmp_path, "one.geojson",
                    [_feature(_line([[0.0, 0.0], [0.001, 0.0]]))])
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
    layer.updateFields()
    project.addMapLayer(layer)
    manager = _route_manager(project, FakeIface())

    added, _skipped, saved = _import_routes(project, manager, path, layer)

    assert added == 0
    assert saved is False
    assert not layer.isEditable(), "the edit command must not be left open"
    assert manager.iface.bar.warnings, "and the user has to be told"


def test_a_route_the_layer_refuses_is_counted_as_skipped(project, tmp_path):
    """It used to be counted in neither total, so it vanished from the report.

    Measured on 3.44.15 with a read-only Route layer and a 3-line file: added 0,
    skipped 0, and the user was told "No lines found for import in the file!"
    about a file that held three perfectly good lines.
    """
    path = _geojson(tmp_path, "three.geojson", [
        _feature(_line([[0.0, 0.0], [0.001, 0.0]])),
        _feature(_line([[0.0, 1.0], [0.001, 1.0]])),
        _feature(_line([[0.0, 2.0], [0.001, 2.0]])),
    ])
    route = _route_layer(project)
    route.setReadOnly(True)
    manager = _route_manager(project, FakeIface())

    added, skipped, _saved = _import_routes(project, manager, path, route)

    assert added == 0
    assert skipped == 3, "every refused route has to land in a total"


def test_a_refused_commit_does_not_zero_the_count(project, tmp_path, monkeypatch):
    """"Added" and "saved" are different facts, and this is where they diverge.

    QGIS keeps the features in the layer's buffer when a commit is refused, so
    they really are in the layer. Returning 0 is what made the caller announce
    that the file had held no lines.
    """
    path = _geojson(tmp_path, "two.geojson", [
        _feature(_line([[0.0, 0.0], [0.001, 0.0]])),
        _feature(_line([[0.0, 1.0], [0.001, 1.0]])),
    ])
    route = _route_layer(project)
    manager = _route_manager(project, FakeIface())
    monkeypatch.setattr(route, "commitChanges", lambda *a, **k: False)

    added, skipped, saved = _import_routes(project, manager, path, route)

    assert added == 2, "the routes are in the buffer, so they were added"
    assert skipped == 0
    assert saved is False, "and the caller has to know they are not on disk"


def test_joining_the_users_session_is_reported_as_unsaved_not_as_saved(project, tmp_path):
    """saved is None when the user owned the session: not an error, not 'saved'."""
    path = _geojson(tmp_path, "one.geojson",
                    [_feature(_line([[0.0, 0.0], [0.001, 0.0]]))])
    route = _route_layer(project)
    route.startEditing()
    manager = _route_manager(project, FakeIface())

    added, _skipped, saved = _import_routes(project, manager, path, route)

    assert added == 1
    assert saved is None, "their session, theirs to save"
    assert route.isEditable(), "and it is still open"


def test_an_import_does_not_commit_the_users_pending_edits(project, tmp_path):
    """The reason it is scoped in an edit command.

    A user mid-edit must not have their buffer committed by an import, and must
    not lose it either.
    """
    path = _geojson(tmp_path, "one.geojson",
                    [_feature(_line([[0.0, 0.0], [0.001, 0.0]]))])
    route = _route_layer(project)
    route.startEditing()
    pending = QgsFeature(route.fields())
    pending.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(500, 500), QgsPointXY(600, 600)]))
    pending.setAttribute("naziv", "the user's own line")
    assert route.addFeature(pending)
    manager = _route_manager(project, FakeIface())

    added, _skipped, _saved = _import_routes(project, manager, path, route)

    assert added == 1
    assert route.isEditable(), "the user's session must still be open"
    assert route.featureCount() == 2
    # Nothing reached the provider yet: the user has not saved.
    assert len(list(route.dataProvider().getFeatures())) == 0
    route.rollBack()


def test_an_import_into_a_clean_layer_commits(project, tmp_path):
    path = _geojson(tmp_path, "one.geojson",
                    [_feature(_line([[0.0, 0.0], [0.001, 0.0]]))])
    route = _route_layer(project)
    manager = _route_manager(project, FakeIface())

    _import_routes(project, manager, path, route)

    assert not route.isEditable()
    assert len(list(route.dataProvider().getFeatures())) == 1


# ---------------------------------------------------------------------------
# v1.6.0 QA, Q23: "The reason is in the message bar" -- so it has to be
# ---------------------------------------------------------------------------
#
# QA step E.4, on 4.2.3 and 3.40.15: Import route from file with a GeoJSON of
# three points answered "None of the 3 feature(s) in the file could be
# imported. The reason is in the message bar." over a bar that said only "3
# feature(s) in the file could not be imported and were skipped." A feature
# with no line in it was counted, and its reason was written down nowhere.
#
# These go through import_route_from_file, the code the Routing menu runs, with
# the file dialog and the route-type prompt answered: what the user reads is
# the box (quiet_dialogs) and the bar (FakeBar), and only the two together say
# whether the box is telling the truth.

#: The bar entry for features with no line in them, as OperationErrors renders
#: a single reason.
_NOT_LINES = ("{count} feature(s) in the file are not lines (points, areas or empty) and were"
              " left out. See Log Messages > FiberQ for the details.")
_NONE_IMPORTED = ("None of the {count} feature(s) in the file could be imported. The reason is in"
                  " the message bar.")


@pytest.fixture
def modals():
    """Any modal that opens anyway, closed and recorded, so a regression fails instead of hanging."""
    from qgis.PyQt.QtCore import QTimer
    from qgis.PyQt.QtWidgets import QApplication

    seen = []

    def close():
        widget = QApplication.activeModalWidget()
        if widget is not None:
            seen.append(widget.windowTitle())
            widget.reject()

    timer = QTimer()
    timer.timeout.connect(close)
    timer.start(50)
    yield seen
    timer.stop()


@pytest.fixture
def reasons(monkeypatch):
    """Every ``(what, reason)`` an operation's collector was given, in order."""
    from fiberq.utils.errors import OperationErrors

    seen = []
    add = OperationErrors.add

    def recorded(self, what, problem):
        add(self, what, problem)
        seen.append(self.problems[-1])

    monkeypatch.setattr(OperationErrors, "add", recorded)
    return seen


def _from_the_menu(manager, path, monkeypatch, kind="Aerial"):
    """Routing > Import route from file, with ``path`` picked and ``kind`` chosen."""
    from fiberq.core import route_manager

    monkeypatch.setattr(route_manager.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (path, "")))
    monkeypatch.setattr(route_manager.QInputDialog, "getItem",
                        staticmethod(lambda *a, **k: (kind, True)))
    manager.import_route_from_file()


def _the_route_layer(project):
    found = [lyr for lyr in project.mapLayers().values() if lyr.name() == "Route"]
    assert len(found) == 1, found
    return found[0]


def _saved(layer):
    """How many routes are in the data source, not just in an edit buffer."""
    return len(list(layer.dataProvider().getFeatures()))


def _qa16_points(tmp_path):
    """The maintainer's qa16-points.geojson: three points, in CRS84."""
    return _geojson(tmp_path, "qa16-points.geojson", [
        _feature(_point((21.0600, 44.7400))),
        _feature(_point((21.0610, 44.7405))),
        _feature(_point((21.0620, 44.7410))),
    ])


def test_a_file_of_points_says_on_the_bar_why_nothing_was_imported(
        project, tmp_path, monkeypatch, quiet_dialogs, modals):
    """QA step E.4, with the maintainer's file, into the project's own CRS (EPSG:3857)."""
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, _qa16_points(tmp_path), monkeypatch)

    assert quiet_dialogs == [_NONE_IMPORTED.format(count=3)]
    assert manager.iface.bar.entries == [("warning", "Import route", _NOT_LINES.format(count=3))]
    route = _the_route_layer(project)
    assert route.featureCount() == 0
    assert not route.isEditable(), "the crash fix under test: the layer is not left in edit mode"
    assert modals == []


def test_a_mixed_file_adds_the_lines_and_says_why_the_point_was_left_out(
        project, tmp_path, monkeypatch, quiet_dialogs, modals):
    path = _geojson(tmp_path, "mixed.geojson", [
        _feature(_line([[21.0600, 44.7400], [21.0610, 44.7405]])),
        _feature(_point((21.0605, 44.7402))),
        _feature(_line([[21.0620, 44.7410], [21.0630, 44.7415]])),
    ])
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == ["Imported 2 routes into the 'Route' layer!\n(All are of type: Aerial)"]
    assert manager.iface.bar.entries == [("warning", "Import route", _NOT_LINES.format(count=1))]
    route = _the_route_layer(project)
    assert _saved(route) == 2
    assert not route.isEditable()
    assert modals == []


@pytest.mark.parametrize("geometry", [
    pytest.param({"type": "Polygon", "coordinates": [
        [[21.06, 44.74], [21.061, 44.74], [21.061, 44.741], [21.06, 44.74]]]}, id="polygon"),
    pytest.param(None, id="null-geometry"),
    pytest.param({"type": "LineString", "coordinates": []}, id="empty-line"),
    pytest.param({"type": "LineString", "coordinates": [[21.06, 44.74]]}, id="one-point-line"),
])
def test_a_feature_with_no_line_in_it_is_named_on_the_bar(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, geometry):
    """Each reads back with no line part (measured on 3.22.16, 3.40.15 and 4.2.3)."""
    path = _geojson(tmp_path, "one-of-each.geojson", [
        _feature(_line([[21.0600, 44.7500], [21.0610, 44.7505]])),
        _feature(geometry),
    ])
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == ["Imported 1 routes into the 'Route' layer!\n(All are of type: Aerial)"]
    assert manager.iface.bar.entries == [("warning", "Import route", _NOT_LINES.format(count=1))]
    assert _saved(_the_route_layer(project)) == 1
    assert modals == []


def test_a_refused_save_keeps_its_reason_first_on_the_bar(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, reasons):
    """The box sends the user to the bar for why the save failed, so that reason
    comes first and the points are counted after it, not the other way round."""
    path = _geojson(tmp_path, "mixed.geojson", [
        _feature(_line([[21.0600, 44.7400], [21.0610, 44.7405]])),
        _feature(_point((21.0605, 44.7402))),
    ])
    route = _route_layer(project)
    monkeypatch.setattr(route, "commitChanges", lambda *a, **k: False)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [
        "1 route(s) were added to the Route layer but could not be saved. Close any program holding"
        " the file open, then use Layer > Save Layer Edits. The reason is in the message bar."]
    assert manager.iface.bar.entries == [(
        "warning", "Import route",
        "Route: QGIS refused the commit without saying why (+1 more). See Log Messages > FiberQ for"
        " the details.")]
    assert reasons == [
        ("Route", "QGIS refused the commit without saying why"),
        (None, "1 feature(s) in the file are not lines (points, areas or empty) and were left out")]
    assert modals == []
    route.rollBack()


def test_a_point_ahead_of_a_failed_import_keeps_its_reason(project, tmp_path):
    """The import that ends on an exception (f009) still says why the point was
    left out, after the exception that stopped it."""
    from fiberq.utils.compat import FieldType, new_field

    path = _geojson(tmp_path, "point-then-line.geojson", [
        _feature(_point((0.0, 0.0))),
        _feature(_line([[0.0, 0.0], [0.001, 0.0]])),
    ])
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    layer.dataProvider().addAttributes([new_field("duzina", FieldType.Double)])
    layer.updateFields()
    project.addMapLayer(layer)
    manager = _route_manager(project, FakeIface())

    added, skipped, saved = _import_routes(project, manager, path, layer)

    assert (added, skipped, saved) == (0, 1, False)
    assert not layer.isEditable()
    assert manager.iface.bar.entries == [(
        "warning", "Import route",
        "KeyError: 'naziv' (+1 more). See Log Messages > FiberQ for the details.")]


@pytest.mark.parametrize("cause", ["reprojection", "refusal"])
def test_a_reason_on_the_bar_is_not_repeated_as_a_bare_count(
        project, tmp_path, monkeypatch, modals, cause):
    """With every reason on the bar, the reason-free "{count} feature(s) in the
    file could not be imported and were skipped." only repeated their count."""
    path = _geojson(tmp_path, "lines.geojson", [
        _feature(_line([[1e30, 1e30], [2e30, 2e30]] if cause == "reprojection"
                       else [[21.0600, 44.7400], [21.0610, 44.7405]])),
    ])
    if cause == "refusal":
        _route_layer(project).setReadOnly(True)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert manager.iface.bar.warnings, "the reason"
    assert manager.iface.bar.infos == []
    assert modals == []


# What Import route from file said before Q23, and says still: the outcomes the
# fix had to leave as they were.

def test_a_file_of_lines_still_imports_every_line(project, tmp_path, monkeypatch, quiet_dialogs, modals):
    path = _geojson(tmp_path, "lines.geojson", [
        _feature(_line([[21.0600, 44.7400], [21.0610, 44.7405]])),
        _feature(_line([[21.0620, 44.7410], [21.0630, 44.7415]])),
    ])
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == ["Imported 2 routes into the 'Route' layer!\n(All are of type: Aerial)"]
    assert manager.iface.bar.entries == []
    route = _the_route_layer(project)
    assert _saved(route) == 2
    assert not route.isEditable()
    assert modals == []


def test_a_route_that_cannot_be_reprojected_is_still_named(project, tmp_path, monkeypatch, quiet_dialogs, modals):
    path = _geojson(tmp_path, "far.geojson", [_feature(_line([[1e30, 1e30], [2e30, 2e30]]))])
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_NONE_IMPORTED.format(count=1)]
    assert manager.iface.bar.warnings == [
        "a route could not be reprojected and was left out. See Log Messages > FiberQ for the details."]
    route = _the_route_layer(project)
    assert route.featureCount() == 0
    assert not route.isEditable()
    assert modals == []


def test_a_layer_that_refuses_the_routes_is_still_named(project, tmp_path, monkeypatch, quiet_dialogs, modals):
    path = _geojson(tmp_path, "three.geojson", [
        _feature(_line([[21.0600, 44.7400], [21.0610, 44.7405]])),
        _feature(_line([[21.0600, 44.7500], [21.0610, 44.7505]])),
        _feature(_line([[21.0600, 44.7600], [21.0610, 44.7605]])),
    ])
    route = _route_layer(project)
    monkeypatch.setattr(route, "addFeature", lambda *a, **k: False)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_NONE_IMPORTED.format(count=3)]
    assert manager.iface.bar.warnings == [
        "Route: a route was rejected by the layer (+2 more). See Log Messages > FiberQ for the details."]
    assert route.featureCount() == 0
    assert not route.isEditable()
    assert modals == []


def test_a_refused_save_still_says_the_routes_are_not_saved(
        project, tmp_path, monkeypatch, quiet_dialogs, modals):
    path = _geojson(tmp_path, "two.geojson", [
        _feature(_line([[21.0600, 44.7400], [21.0610, 44.7405]])),
        _feature(_line([[21.0620, 44.7410], [21.0630, 44.7415]])),
    ])
    route = _route_layer(project)
    monkeypatch.setattr(route, "commitChanges", lambda *a, **k: False)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [
        "2 route(s) were added to the Route layer but could not be saved. Close any program holding"
        " the file open, then use Layer > Save Layer Edits. The reason is in the message bar."]
    assert manager.iface.bar.entries == [(
        "warning", "Import route",
        "Route: QGIS refused the commit without saying why. See Log Messages > FiberQ for the details.")]
    assert route.isEditable(), "the refused routes stay in the buffer, for the user to save"
    assert _saved(route) == 0
    assert modals == []
    route.rollBack()


def test_an_import_into_the_users_open_session_still_leaves_it_to_them(
        project, tmp_path, monkeypatch, quiet_dialogs, modals):
    path = _geojson(tmp_path, "one.geojson", [
        _feature(_line([[21.0600, 44.7400], [21.0610, 44.7405]]))])
    route = _route_layer(project)
    route.startEditing()
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [
        "1 route(s) of type Aerial were added to the Route layer. They are not saved yet, because you"
        " already had the layer open for editing -- use Layer > Save Layer Edits when you are ready."]
    assert manager.iface.bar.entries == []
    assert route.isEditable()
    assert route.featureCount() == 1
    assert _saved(route) == 0
    assert modals == []
    route.rollBack()


# ---------------------------------------------------------------------------
# v1.6.0 QA, Q24: every layer of the file, not only the first
# ---------------------------------------------------------------------------
#
# QGIS opens a file by its path alone as its FIRST layer, and that was all
# Import route read. A KML whose two folders held 1 and 2 lines imported 1
# route and reported success, and a GPX, whose first layer is its waypoints,
# never had its tracks or routes read (3.40.15 and 4.2.3). A cable plant's KMZ
# has a folder for each kind of plant.
#
# OGR has two KML readers, and every leg's GDAL has both and reads with LIBKML
# first. They do not type a folder alike -- LIBKML types every folder as
# unknown, KML types a folder of points as points -- so the KML cases run
# under each (kml_driver) and have to come to the same thing.

_IMPORTED = "Imported {count} routes into the 'Route' layer!\n(All are of type: Aerial)"
_LEFT_OUT = ("{count} {kind}(s) in the file hold no lines and were left out: {names}. See Log Messages"
             " > FiberQ for the details.")
_WAYPOINTS = ("{count} waypoint(s) in the file are points, not lines, and were left out. See Log"
              " Messages > FiberQ for the details.")


@pytest.fixture(params=["LIBKML", "KML"])
def kml_driver(request, qgis_app):
    """The KML reader QGIS's OGR provider opens a .kml with, for one test.

    LIBKML is taken off GDAL's list and put back, never deleted. Skipping it
    through QgsApplication.skipGdalDriver() deletes the driver, and a dataset
    QGIS still holds open in its pool then closes through freed memory: a
    segmentation fault a few tests later (3.22.16, 3.40.15, 4.0.3, 4.2.3).
    """
    from osgeo import gdal

    libkml = gdal.GetDriverByName("LIBKML")
    if request.param == "KML" and libkml is not None:
        libkml.Deregister()
    yield request.param
    if request.param == "KML" and libkml is not None:
        # Back in GDAL's own order: LIBKML put back alone would go after KML,
        # and every later test would read its KML through KML.
        kml = gdal.GetDriverByName("KML")
        kml.Deregister()
        libkml.Register()
        kml.Register()


def _read_with(path, driver):
    """Fail unless QGIS reads ``path`` with ``driver``; skip where GDAL has no such driver."""
    layer = QgsVectorLayer(path, "probe", "ogr")
    found = layer.dataProvider().storageType()
    if found != driver and driver == "LIBKML":
        pytest.skip(f"this GDAL has no LIBKML: {path} is read by {found}")
    assert found == driver


def _kml_line(name, *coords):
    vertices = " ".join(f"{x},{y}" for x, y in coords)
    return f"<Placemark><name>{name}</name><LineString><coordinates>{vertices}</coordinates></LineString></Placemark>"


def _kml_point(name, x, y):
    return f"<Placemark><name>{name}</name><Point><coordinates>{x},{y}</coordinates></Point></Placemark>"


def _kml_folder(name, *placemarks):
    return f"<Folder><name>{name}</name>{''.join(placemarks)}</Folder>"


def _kml(tmp_path, name, *folders):
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">'
                 "<Document>" + "".join(folders) + "</Document></kml>")
    return path


def _gpx(tmp_path, name, body):
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="FiberQ tests"'
                 ' xmlns="http://www.topografix.com/GPX/1/1">' + body + "</gpx>")
    return path


_AERIAL = _kml_folder("Aerial", _kml_line("A1", (21.060, 44.790), (21.062, 44.791)))
_UNDERGROUND = _kml_folder("Underground", _kml_line("U1", (21.063, 44.792), (21.065, 44.793)),
                           _kml_line("U2", (21.066, 44.794), (21.067, 44.795)))
_POLES = _kml_folder("Poles", _kml_point("P1", 21.060, 44.790), _kml_point("P2", 21.062, 44.791))
_WAYPOINT = '<wpt lat="44.790" lon="21.060"><name>W1</name></wpt>'
_GPX_ROUTE = '<rte><name>R1</name><rtept lat="44.792" lon="21.063"/><rtept lat="44.793" lon="21.065"/></rte>'
_GPX_TRACK = ('<trk><name>T1</name><trkseg><trkpt lat="44.790" lon="21.060"/>'
              '<trkpt lat="44.791" lon="21.062"/></trkseg></trk>')


def test_a_kml_of_two_folders_of_lines_imports_all_three_routes(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, kml_driver):
    """The finding: 1 route and a success box, the second folder never read."""
    path = _kml(tmp_path, "two-folders.kml", _AERIAL, _UNDERGROUND)
    _read_with(path, kml_driver)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=3)]
    assert manager.iface.bar.entries == []
    route = _the_route_layer(project)
    assert _saved(route) == 3
    assert not route.isEditable()
    assert modals == []


def test_a_kml_folder_of_points_is_named_and_the_lines_beside_it_imported(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, kml_driver):
    """Poles first, as the first layer that was all the import read."""
    path = _kml(tmp_path, "poles-and-cables.kml", _POLES, _AERIAL)
    _read_with(path, kml_driver)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=1)]
    assert manager.iface.bar.entries == [
        ("warning", "Import route", _LEFT_OUT.format(count=1, kind="folder", names='"Poles"'))]
    assert _saved(_the_route_layer(project)) == 1
    assert modals == []


def test_a_kml_folder_of_points_and_lines_imports_its_lines_and_counts_its_points(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, kml_driver):
    """A folder that holds lines is read whole, and its point is counted as Q23 counts one."""
    mixed = _kml_folder("Mixed", _kml_point("P1", 21.064, 44.796),
                        _kml_line("L1", (21.063, 44.792), (21.065, 44.793)),
                        _kml_line("L2", (21.066, 44.794), (21.067, 44.795)))
    path = _kml(tmp_path, "mixed-folder.kml", _AERIAL, mixed)
    _read_with(path, kml_driver)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=3)]
    assert manager.iface.bar.entries == [("warning", "Import route", _NOT_LINES.format(count=1))]
    assert _saved(_the_route_layer(project)) == 3
    assert modals == []


def test_a_kmz_imports_as_the_kml_inside_it(project, tmp_path, monkeypatch, quiet_dialogs, modals):
    """LIBKML reads a .kmz itself; OGR's KML driver does not open one at all,
    before this change or after it (all five legs)."""
    import zipfile

    kml = _kml(tmp_path, "plant.kml", _POLES, _AERIAL, _UNDERGROUND)
    kmz = os.path.join(str(tmp_path), "plant.kmz")
    with zipfile.ZipFile(kmz, "w") as archive:
        archive.write(kml, "doc.kml")
    _read_with(kmz, "LIBKML")
    outcomes = []
    for path in (kml, kmz):
        project.removeAllMapLayers()
        del quiet_dialogs[:]
        manager = _route_manager(project, FakeIface())
        _from_the_menu(manager, path, monkeypatch)
        route = _the_route_layer(project)
        outcomes.append((list(quiet_dialogs), manager.iface.bar.entries,
                         sorted(f.geometry().asWkt(2) for f in route.dataProvider().getFeatures())))

    assert outcomes[1] == outcomes[0]
    assert outcomes[0][0] == [_IMPORTED.format(count=3)]
    assert outcomes[0][1] == [
        ("warning", "Import route", _LEFT_OUT.format(count=1, kind="folder", names='"Poles"'))]
    assert len(outcomes[0][2]) == 3
    assert modals == []


def test_a_gpx_imports_its_track_and_its_route_and_counts_its_waypoint(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, reasons):
    """route_points and track_points repeat the route and the track, so they
    are not read, and are not mentioned."""
    path = _gpx(tmp_path, "survey.gpx", _WAYPOINT + _GPX_ROUTE + _GPX_TRACK)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=2)]
    assert manager.iface.bar.entries == [("warning", "Import route", _WAYPOINTS.format(count=1))]
    assert reasons == [(None, "1 waypoint(s) in the file are points, not lines, and were left out")]
    route = _the_route_layer(project)
    assert _saved(route) == 2
    assert not route.isEditable()
    assert modals == []


def test_a_gpx_of_waypoints_only_imports_nothing_and_says_why(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, reasons):
    path = _gpx(tmp_path, "waypoints.gpx",
                _WAYPOINT + '<wpt lat="44.791" lon="21.061"><name>W2</name></wpt>')
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_NONE_IMPORTED.format(count=2)]
    assert manager.iface.bar.entries == [("warning", "Import route", _WAYPOINTS.format(count=2))]
    assert reasons == [(None, "2 waypoint(s) in the file are points, not lines, and were left out")]
    route = _the_route_layer(project)
    assert route.featureCount() == 0
    assert not route.isEditable()
    assert modals == []


def test_a_file_of_several_layers_is_one_undo_step_in_the_users_session(
        project, tmp_path, monkeypatch, quiet_dialogs, modals):
    path = _kml(tmp_path, "two-folders.kml", _AERIAL, _UNDERGROUND)
    route = _route_layer(project)
    route.startEditing()
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [
        "3 route(s) of type Aerial were added to the Route layer. They are not saved yet, because you"
        " already had the layer open for editing -- use Layer > Save Layer Edits when you are ready."]
    assert route.undoStack().count() == 1, "one import, one undo step"
    assert route.featureCount() == 3
    assert _saved(route) == 0, "the user's session, theirs to save"
    assert route.isEditable()
    assert modals == []
    route.rollBack()


def test_a_file_of_several_layers_is_saved_once(project, tmp_path, monkeypatch, quiet_dialogs, modals):
    path = _kml(tmp_path, "two-folders.kml", _AERIAL, _UNDERGROUND)
    route = _route_layer(project)
    commits = []
    commit = route.commitChanges

    def counted(*args, **kwargs):
        commits.append(len(route.editBuffer().addedFeatures()))
        return commit(*args, **kwargs)

    monkeypatch.setattr(route, "commitChanges", counted)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert commits == [3], "one commit, holding the routes of both folders"
    assert quiet_dialogs == [_IMPORTED.format(count=3)]
    assert _saved(route) == 3
    assert modals == []


def test_a_refused_save_of_several_layers_keeps_its_reason_first(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, reasons):
    path = _kml(tmp_path, "plant.kml", _POLES, _AERIAL, _UNDERGROUND)
    route = _route_layer(project)
    monkeypatch.setattr(route, "commitChanges", lambda *a, **k: False)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [
        "3 route(s) were added to the Route layer but could not be saved. Close any program holding"
        " the file open, then use Layer > Save Layer Edits. The reason is in the message bar."]
    assert manager.iface.bar.entries == [(
        "warning", "Import route",
        "Route: QGIS refused the commit without saying why (+1 more). See Log Messages > FiberQ for"
        " the details.")]
    assert reasons == [
        ("Route", "QGIS refused the commit without saying why"),
        (None, '1 folder(s) in the file hold no lines and were left out: "Poles"')]
    assert modals == []
    route.rollBack()


def _gpkg_layers(path, layers):
    """A GeoPackage of several layers, each ``(name, epsg, ogr geometry type, [wkt])``."""
    from osgeo import ogr, osr

    source = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    for name, epsg, geometry_type, shapes in layers:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(epsg)
        layer = source.CreateLayer(name, srs, geometry_type)
        for wkt in shapes:
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
            layer.CreateFeature(feature)
    source = None


def test_each_layer_is_reprojected_from_its_own_crs(project, tmp_path, monkeypatch, quiet_dialogs, modals):
    """The same line twice, in degrees and in UTM 34N metres, in two layers of
    one GeoPackage (a file of several CRSs), lands twice in the same place."""
    from osgeo import ogr
    from qgis.core import QgsCoordinateTransformContext

    line = QgsGeometry.fromPolylineXY([QgsPointXY(21.060, 44.790), QgsPointXY(21.070, 44.800)])
    utm = QgsGeometry(line)
    utm.transform(QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                                         QgsCoordinateReferenceSystem("EPSG:32634"),
                                         QgsCoordinateTransformContext()))
    path = os.path.join(str(tmp_path), "plant.gpkg")
    _gpkg_layers(path, [
        ("poles", 4326, ogr.wkbPoint, ["POINT (21.06 44.79)"]),
        ("aerial", 4326, ogr.wkbLineString, [line.asWkt(9)]),
        ("underground", 32634, ogr.wkbLineString, [utm.asWkt(6)]),
    ])
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=2)]
    assert manager.iface.bar.entries == [
        ("warning", "Import route", _LEFT_OUT.format(count=1, kind="layer", names='"poles"'))]
    first, second = [f.geometry() for f in _the_route_layer(project).getFeatures()]
    assert first.hausdorffDistance(second) < 0.01, (first.asWkt(2), second.asWkt(2))
    assert modals == []


def test_a_layer_of_the_file_that_cannot_be_opened_is_named(
        project, tmp_path, monkeypatch, quiet_dialogs, modals):
    from fiberq.core import route_manager

    path = _kml(tmp_path, "two-folders.kml", _AERIAL, _UNDERGROUND)
    opened = route_manager.QgsVectorLayer

    def opening(uri, *args):
        if uri.endswith("|layername=Underground"):
            return opened(os.path.join(str(tmp_path), "not-there.kml"), *args)
        return opened(uri, *args)

    monkeypatch.setattr(route_manager, "QgsVectorLayer", opening)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=1)]
    assert manager.iface.bar.entries == [
        ("warning", "Import route",
         "Underground: could not be read and was left out. See Log Messages > FiberQ for the details.")]
    assert modals == []


def test_a_folder_with_a_bar_in_its_name_is_read(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, kml_driver):
    """QGIS's own |layername= does not survive a "|" in the name, so that
    layer is opened by its number in the file."""
    ducts = _kml_folder("Ducts A|B", _kml_line("D1", (21.063, 44.792), (21.065, 44.793)),
                        _kml_line("D2", (21.066, 44.794), (21.067, 44.795)))
    path = _kml(tmp_path, "bar-in-a-name.kml", _AERIAL, ducts)
    _read_with(path, kml_driver)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=3)]
    assert manager.iface.bar.entries == []
    assert modals == []


def _two_lines_in(name):
    """A folder ``name`` of two lines, apart from _AERIAL's."""
    return _kml_folder(name, _kml_line("U1", (21.063, 44.792), (21.065, 44.793)),
                       _kml_line("U2", (21.066, 44.794), (21.067, 44.795)))


def _routes_imported(project):
    """The routes in the Route layer, as text: a line read twice shows twice."""
    return sorted(f.geometry().asWkt(1) for f in _the_route_layer(project).getFeatures())


@pytest.mark.parametrize("first, unnamed", [
    pytest.param("Aerial", "", id="empty-name"),
    pytest.param("Aerial", "   ", id="name-of-spaces"),
    pytest.param("Layer #1", "", id="beside-a-folder-layer-1"),
])
def test_a_kml_folder_with_no_name_is_read_and_not_taken_for_another(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, kml_driver, first, unnamed):
    """LIBKML reads <name></name>, or a name of spaces, as no name, and QGIS's
    uri for a folder of no name is the file's bare path, which opens the FIRST
    folder: its line went in twice, under "Imported 2 routes", and the unnamed
    folder's two never. OGR's KML driver names that folder "Layer #1" after
    its number, beside a folder of that name too, and one uri for both opened
    the first."""
    path = _kml(tmp_path, "unnamed-folder.kml",
                _kml_folder(first, _kml_line("A1", (21.060, 44.790), (21.062, 44.791))), _two_lines_in(unnamed))
    _read_with(path, kml_driver)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=3)]
    assert manager.iface.bar.entries == []
    routes = _routes_imported(project)
    assert len(set(routes)) == 3, routes
    assert modals == []


@pytest.mark.parametrize("container, name", [
    pytest.param("kmz", "", id="kmz-empty-name"),
    pytest.param("zip", "", id="zip-empty-name"),
    pytest.param("zip", "Ducts A|B", id="zip-bar-in-a-name"),
])
def test_a_folder_opened_by_its_number_is_found_in_a_kmz_and_in_a_zip(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, container, name):
    """By its number in the KML that holds it. A .zip of a KML, picked through
    "All files", is read as the KML inside, and a number on the .zip's own
    path does not open at all."""
    import zipfile

    kml = _kml(tmp_path, "plant.kml", _AERIAL, _two_lines_in(name))
    path = os.path.join(str(tmp_path), "plant." + container)
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(kml, "doc.kml")
    _read_with(path, "LIBKML")
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=3)]
    assert manager.iface.bar.entries == []
    routes = _routes_imported(project)
    assert len(set(routes)) == 3, routes
    assert modals == []


def test_a_zip_of_shapefiles_imports_the_lines_of_each(project, tmp_path, monkeypatch, quiet_dialogs, modals):
    """Through "All files". Each shapefile in a .zip is a layer of it with a
    uri of its own, and each one's layer number is 0."""
    import zipfile

    from osgeo import ogr, osr

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    for name, geometry_type, shapes in (
            ("poles", ogr.wkbPoint, ["POINT (21.06 44.79)"]),
            ("aerial", ogr.wkbLineString, ["LINESTRING (21.060 44.790,21.062 44.791)"]),
            ("underground", ogr.wkbLineString, ["LINESTRING (21.063 44.792,21.065 44.793)",
                                                "LINESTRING (21.066 44.794,21.067 44.795)"])):
        source = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(os.path.join(str(tmp_path), name + ".shp"))
        layer = source.CreateLayer(name, srs, geometry_type)
        for wkt in shapes:
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
            layer.CreateFeature(feature)
        source = None
    path = os.path.join(str(tmp_path), "plant.zip")
    with zipfile.ZipFile(path, "w") as archive:
        for name in ("poles", "aerial", "underground"):
            for extension in (".shp", ".shx", ".dbf", ".prj"):
                archive.write(os.path.join(str(tmp_path), name + extension), name + extension)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=3)]
    assert manager.iface.bar.entries == [
        ("warning", "Import route", _LEFT_OUT.format(count=1, kind="layer", names='"poles.shp"'))]
    assert _saved(_the_route_layer(project)) == 3
    assert modals == []


def test_a_kml_folder_qgis_gives_no_crs_is_read_as_wgs84(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, kml_driver):
    """A folder whose first placemark is a MultiGeometry of mixed parts has no
    CRS in QGIS, and the line after it went in unprojected, at (21, 45) in the
    project's metres. A KML is in WGS 84, whatever QGIS makes of a folder."""
    pole = ("<Placemark><name>Pole and plot</name><MultiGeometry>"
            "<Point><coordinates>21.064,44.796</coordinates></Point>"
            "<Polygon><outerBoundaryIs><LinearRing><coordinates>21.064,44.796 21.065,44.796 21.065,44.797"
            " 21.064,44.796</coordinates></LinearRing></outerBoundaryIs></Polygon></MultiGeometry></Placemark>")
    path = _kml(tmp_path, "pole-first.kml", _AERIAL,
                _kml_folder("Feeder", pole, _kml_line("F1", (21.063, 44.792), (21.065, 44.793))))
    _read_with(path, kml_driver)
    assert not _has_a_crs(path + "|layername=Feeder"), "QGIS gives this folder a CRS now; the case is gone"
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_IMPORTED.format(count=2)]
    assert manager.iface.bar.entries == [("warning", "Import route", _NOT_LINES.format(count=1))]
    expected = _in_the_project_crs((21.063, 44.792), (21.065, 44.793))
    routes = [f.geometry() for f in _the_route_layer(project).getFeatures()]
    assert [g for g in routes if g.hausdorffDistance(expected) < 0.01], [g.asWkt(0) for g in routes]
    assert modals == []


def _has_a_crs(uri):
    """Whether QGIS gives the layer at ``uri`` a CRS. The layer goes with the
    call: one kept in a failing test's frame until exit crashes QGIS 3.22."""
    return QgsVectorLayer(uri, "probe", "ogr").crs().isValid()


def _in_the_project_crs(*points):
    """A line through WGS 84 ``points``, in the tests' project CRS, EPSG:3857."""
    line = QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in points])
    line.transform(QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                                          QgsCoordinateReferenceSystem("EPSG:3857"), QgsProject.instance()))
    return line


def test_a_route_layer_that_cannot_be_edited_is_the_reason_given(
        project, tmp_path, monkeypatch, quiet_dialogs, modals):
    """Said as the merge says it, and nothing is read. startEditing()'s answer
    went unchecked, and three lines into a read-only Route layer led the bar
    with "a route was rejected by the layer (+3 more)": three rejections, then
    "the layer was not in edit mode". The session code this change rewrote."""
    path = _geojson(tmp_path, "three.geojson", [
        _feature(_line([[21.0600, 44.7400], [21.0610, 44.7405]])),
        _feature(_line([[21.0600, 44.7500], [21.0610, 44.7505]])),
        _feature(_line([[21.0600, 44.7600], [21.0610, 44.7605]])),
    ])
    route = _route_layer(project)
    route.setReadOnly(True)
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [_NONE_IMPORTED.format(count=3)]
    assert manager.iface.bar.warnings == [
        "Route: the Route layer could not be opened for editing, so nothing was changed. See Log"
        " Messages > FiberQ for the details."]
    assert route.featureCount() == 0
    assert not route.isEditable()
    assert modals == []


def _one_layer_file(tmp_path, kind):
    """A file of one layer, as each single-layer format holds two lines and a point."""
    from osgeo import ogr, osr

    lines = ["LINESTRING (21.060 44.740,21.061 44.7405)", "LINESTRING (21.062 44.741,21.063 44.7415)"]
    point = "POINT (21.0605 44.7402)"
    if kind == "geojson":
        return _geojson(tmp_path, "mixed.geojson", [
            _feature(_line([[21.060, 44.740], [21.061, 44.7405]])),
            _feature(_point((21.0605, 44.7402))),
            _feature(_line([[21.062, 44.741], [21.063, 44.7415]]))])
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    if kind == "dxf":
        # DXF keeps no CRS, so these are the project's own metres.
        path = os.path.join(str(tmp_path), "mixed.dxf")
        source = ogr.GetDriverByName("DXF").CreateDataSource(path)
        layer = source.CreateLayer("entities")
        shapes = ["LINESTRING (2344000 5592000,2344100 5592100)", "POINT (2344050 5592050)",
                  "LINESTRING (2344200 5592200,2344300 5592300)"]
    elif kind == "shapefile-lines":
        path = os.path.join(str(tmp_path), "lines.shp")
        source = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(path)
        layer = source.CreateLayer("lines", srs, ogr.wkbLineString)
        shapes = lines
    else:
        path = os.path.join(str(tmp_path), "points.shp")
        source = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(path)
        layer = source.CreateLayer("points", srs, ogr.wkbPoint)
        shapes = [point, "POINT (21.0615 44.7408)"]
    for wkt in shapes:
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
        layer.CreateFeature(feature)
    source = None
    return path


@pytest.mark.parametrize("kind, box, bar", [
    pytest.param("geojson", _IMPORTED.format(count=2), [_NOT_LINES.format(count=1)], id="geojson"),
    pytest.param("shapefile-lines", _IMPORTED.format(count=2), [], id="shapefile-lines"),
    pytest.param("shapefile-points", _NONE_IMPORTED.format(count=2), [_NOT_LINES.format(count=2)],
                 id="shapefile-points"),
    pytest.param("dxf", _IMPORTED.format(count=2), [_NOT_LINES.format(count=1)], id="dxf"),
])
def test_a_file_of_one_layer_imports_as_it_did(
        project, tmp_path, monkeypatch, quiet_dialogs, modals, kind, box, bar):
    """What a GeoJSON, a shapefile and a DXF came to before Q24, and still do."""
    path = _one_layer_file(tmp_path, kind)
    layer = QgsVectorLayer(path, "probe", "ogr")
    assert layer.dataProvider().subLayerCount() == 1
    manager = _route_manager(project, FakeIface())

    _from_the_menu(manager, path, monkeypatch)

    assert quiet_dialogs == [box]
    assert manager.iface.bar.warnings == bar
    assert manager.iface.bar.infos == []
    assert not _the_route_layer(project).isEditable()
    assert modals == []


# ---------------------------------------------------------------------------
# Import points
# ---------------------------------------------------------------------------

def _plugin(iface):
    from fiberq.main_plugin import FiberQPlugin

    obj = FiberQPlugin.__new__(FiberQPlugin)
    obj.iface = iface
    return obj


def _poles(project):
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "Poles", "memory")
    layer.dataProvider().addAttributes([
        QgsField("naziv", QVariant.String),
        QgsField("tip", QVariant.String),
    ])
    layer.updateFields()
    project.addMapLayer(layer)
    return layer


def _import_points(plugin, path, layer):
    from fiberq.utils.errors import OperationErrors

    imported = QgsVectorLayer(path, "tmp", "ogr")
    assert imported.isValid(), path
    transform = QgsCoordinateTransform(
        imported.crs(), layer.crs(), QgsProject.instance())
    with OperationErrors("Import points", plugin.iface) as errors:
        result = plugin._add_imported_points(
            imported, layer, imported.crs(), layer.crs(), transform, errors)
    return result


def test_points_import_and_commit(project, tmp_path):
    path = _geojson(tmp_path, "pts.geojson",
                    [_feature(_point((0.0, 0.0))), _feature(_point((0.001, 0.0)))])
    poles = _poles(project)
    plugin = _plugin(FakeIface())

    added, skipped = _import_points(plugin, path, poles)

    assert (added, skipped) == (2, 0)
    assert len(list(poles.dataProvider().getFeatures())) == 2
    assert not poles.isEditable()


def test_every_imported_pole_gets_its_type(project, tmp_path):
    path = _geojson(tmp_path, "pts.geojson", [_feature(_point((0.0, 0.0)))])
    poles = _poles(project)
    plugin = _plugin(FakeIface())

    _import_points(plugin, path, poles)

    assert next(poles.getFeatures())["tip"] == "POLE"


def test_a_renamed_stubovi_layer_still_gets_the_type(project, tmp_path):
    """The 'tip' default went through `layer.name() in ("Poles", "Poles")`."""
    path = _geojson(tmp_path, "pts.geojson", [_feature(_point((0.0, 0.0)))])
    poles = _poles(project)
    poles.setName("Stubovi")
    plugin = _plugin(FakeIface())

    _import_points(plugin, path, poles)

    assert next(poles.getFeatures())["tip"] == "POLE"


def test_a_line_file_is_skipped_not_imported(project, tmp_path):
    path = _geojson(tmp_path, "lines.geojson",
                    [_feature(_line([[0.0, 0.0], [0.001, 0.0]]))])
    poles = _poles(project)
    plugin = _plugin(FakeIface())

    added, skipped = _import_points(plugin, path, poles)

    assert (added, skipped) == (0, 1)
    assert poles.featureCount() == 0
    assert not poles.isEditable()


def test_a_multipoint_imports_every_point(project, tmp_path):
    path = _geojson(tmp_path, "mp.geojson", [_feature({
        "type": "MultiPoint", "coordinates": [[0.0, 0.0], [0.001, 0.0], [0.002, 0.0]]})])
    poles = _poles(project)
    plugin = _plugin(FakeIface())

    added, skipped = _import_points(plugin, path, poles)

    assert (added, skipped) == (3, 0)


def test_a_null_geometry_is_skipped(project, tmp_path):
    path = _geojson(tmp_path, "nulls.geojson",
                    [_feature(None), _feature(_point((0.0, 0.0)))])
    poles = _poles(project)
    plugin = _plugin(FakeIface())

    added, skipped = _import_points(plugin, path, poles)

    assert (added, skipped) == (1, 1)


def test_importing_points_does_not_commit_the_users_pending_edits(project, tmp_path):
    path = _geojson(tmp_path, "pts.geojson", [_feature(_point((0.0, 0.0)))])
    poles = _poles(project)
    poles.startEditing()
    pending = QgsFeature(poles.fields())
    pending.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(900, 900)))
    assert poles.addFeature(pending)
    plugin = _plugin(FakeIface())

    added, _skipped = _import_points(plugin, path, poles)

    assert added == 1
    assert poles.isEditable()
    assert len(list(poles.dataProvider().getFeatures())) == 0
    poles.rollBack()
