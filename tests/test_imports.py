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

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushInfo(self, title, text):
        self.infos.append(text)


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
    from fiberq.utils.errors import OperationErrors

    imported = QgsVectorLayer(path, "Import_route_tmp", "ogr")
    assert imported.isValid(), path
    transform = QgsCoordinateTransform(
        imported.crs(), route_layer.crs(), QgsProject.instance())
    with OperationErrors("Import route", manager.iface) as errors:
        result = manager._add_imported_routes(
            imported, route_layer, imported.crs(), route_layer.crs(),
            transform, "podzemna", errors)
    return result


def test_a_point_file_is_skipped_not_fatal(project, tmp_path):
    """v1.5.0: TypeError, and the Route layer left in edit mode."""
    path = _geojson(tmp_path, "points.geojson",
                    [_feature(_point((0.0, 0.0))), _feature(_point((1.0, 1.0)))])
    route = _route_layer(project)
    iface = FakeIface()
    manager = _route_manager(project, iface)

    added, skipped = _import_routes(project, manager, path, route)

    assert (added, skipped) == (0, 2)
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

    added, skipped = _import_routes(project, manager, path, route)

    assert added == 2
    assert skipped == 2
    assert route.featureCount() == 2
    assert not route.isEditable()


def test_a_multipart_line_imports_every_part(project, tmp_path):
    path = _geojson(tmp_path, "multi.geojson", [_feature({
        "type": "MultiLineString",
        "coordinates": [[[0.0, 0.0], [0.001, 0.0]], [[0.002, 0.0], [0.003, 0.0]]]})])
    route = _route_layer(project)
    manager = _route_manager(project, FakeIface())

    added, skipped = _import_routes(project, manager, path, route)

    assert (added, skipped) == (2, 0)
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

    added, _skipped = _import_routes(project, manager, path, route)

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
