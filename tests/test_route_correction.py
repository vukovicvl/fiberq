"""Route correction survives the projects people actually have.

WP4 4.2 item R10 (crashes, claimed) and FU-2 item U15 (the logic, unclaimed).

Route correction walks the Route layer and reports any end that does not meet a
pole or manhole, then offers to drag it onto the nearest one. Four separate
unhandled Python errors were reachable from the first button, all four measured
on 3.44.15 and 4.0.3:

====================================  ==========================================
A pole with no position yet           ``ValueError: Null geometry cannot be
                                      converted to a point.``
A multipart Route feature             ``TypeError: MultiLineString geometry
                                      cannot be converted to a polyline.``
A raster basemap in the project       ``AttributeError: 'QgsRasterLayer' object
                                      has no attribute 'geometryType'``
A multipart route, in Correct         the same ``TypeError`` again
====================================  ==========================================

The raster one is the widest. ``mapLayers()`` is a dict keyed by layer id, and
a layer id starts with the layer name, so iteration is roughly name order --
which means a basemap called ``2024_ortho`` or ``AAA_satellite`` is reached
before ``Poles`` and **Correct** dies before it starts. Most real projects have
a basemap.

Two of the four are the same mistake as FU-10: ``asPolyline()`` raises on a
MultiLineString instead of answering an empty list, so

    poly = geom.asPolyline()
    if not poly:
        multi = geom.asMultiPolyline()

can never reach its own fallback. ``utils.geometry.line_vertices`` tests the
multipart case first, and the two shared helpers in that module that had the
same dead branch -- ``get_first_last_points`` and ``extract_line_vertices`` --
go through it now too.

``CorrectionDialog`` is modal, so the tests replace that one class. Everything
else is the real code.
"""
import os
import tempfile

import pytest
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.utils.geometry import (
    extract_line_vertices,
    geometry_point,
    get_first_last_points,
    line_vertices,
)


class FakeBar:
    def __init__(self):
        self.warnings = []

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushInfo(self, title, text):
        pass


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


@pytest.fixture(autouse=True)
def quiet_dialogs(monkeypatch):
    """Route correction ends in a modal either way; an offscreen run hangs on one."""
    said = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: said.append(a[-1])))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: said.append(a[-1])))
    return said


@pytest.fixture
def shown(monkeypatch):
    """The errors Route correction would have put in its dialog."""
    captured = []

    class FakeDialog:
        def __init__(self, errors, parent=None):
            captured.append(list(errors))

        def exec(self):
            return 1

    import fiberq.main_plugin as mp
    monkeypatch.setattr(mp, "CorrectionDialog", FakeDialog)
    return captured


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture
def plugin(project):
    from fiberq.main_plugin import FiberQPlugin

    obj = FiberQPlugin.__new__(FiberQPlugin)
    obj.iface = FakeIface()
    obj.popravljive_greske = []
    return obj


def _route(project, geometries, name="Route"):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", name, "memory")
    layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    layer.updateFields()
    for geom in geometries:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        layer.startEditing()
        layer.addFeature(feat)
        layer.commitChanges()
    project.addMapLayer(layer)
    return layer


def _points(project, name, coords):
    """A point layer; a coordinate of ``None`` makes a feature with no geometry."""
    layer = QgsVectorLayer("Point?crs=EPSG:3857", name, "memory")
    layer.dataProvider().addAttributes([QgsField("tip", QVariant.String)])
    layer.updateFields()
    for xy in coords:
        feat = QgsFeature(layer.fields())
        if xy is not None:
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*xy)))
        layer.startEditing()
        layer.addFeature(feat)
        layer.commitChanges()
    project.addMapLayer(layer)
    return layer


def _straight(x1, y1, x2, y2):
    return QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])


def _multipart():
    return QgsGeometry.fromMultiPolylineXY(
        [[QgsPointXY(0, 0), QgsPointXY(10, 0)],
         [QgsPointXY(20, 0), QgsPointXY(30, 0)]])


# ---------------------------------------------------------------------------
# The shared helpers, which had the dead fallback too
# ---------------------------------------------------------------------------

def test_as_polyline_really_raises_on_a_multipart(qgis_app):
    """The defect behind two of the four crashes, pinned."""
    with pytest.raises(TypeError):
        _multipart().asPolyline()


def test_line_vertices_handles_a_multipart(qgis_app):
    assert line_vertices(_multipart(), first_part_only=True) == [
        QgsPointXY(0, 0), QgsPointXY(10, 0)]
    assert len(line_vertices(_multipart())) == 4


def test_line_vertices_handles_a_simple_line(qgis_app):
    assert line_vertices(_straight(0, 0, 5, 0)) == [QgsPointXY(0, 0), QgsPointXY(5, 0)]


def test_line_vertices_handles_a_null_geometry(qgis_app):
    assert line_vertices(QgsGeometry()) == []
    assert line_vertices(None) == []


def test_get_first_last_points_handles_a_multipart(qgis_app):
    first, last, pts = get_first_last_points(_multipart())
    assert (first, last) == (QgsPointXY(0, 0), QgsPointXY(10, 0))
    assert len(pts) == 2


def test_extract_line_vertices_handles_a_multipart(qgis_app):
    assert len(extract_line_vertices(_multipart())) == 4


def test_geometry_point_handles_a_null_geometry(qgis_app):
    assert geometry_point(QgsGeometry()) is None
    assert geometry_point(None) is None


def test_as_point_really_raises_on_a_null_geometry(qgis_app):
    with pytest.raises(ValueError):
        QgsGeometry().asPoint()


def test_geometry_point_reads_a_real_point(qgis_app):
    assert geometry_point(QgsGeometry.fromPointXY(QgsPointXY(3, 4))) == QgsPointXY(3, 4)


# ---------------------------------------------------------------------------
# R10: the four crashes
# ---------------------------------------------------------------------------

def test_a_pole_with_no_position_does_not_stop_the_check(plugin, project, shown):
    """v1.5.0: ValueError, and the user saw none of their route errors."""
    _route(project, [_straight(0, 0, 100, 0)])
    _points(project, "Poles", [None, (0, 0)])

    plugin.check_consistency()

    assert shown, "the check has to reach its dialog"
    assert len(shown[0]) == 1, "the far end is the one real error"
    assert any("no position yet" in w for w in plugin.iface.bar.warnings)


def test_a_multipart_route_does_not_stop_the_check(plugin, project, shown):
    """v1.5.0: TypeError from asPolyline()."""
    _route(project, [_multipart()])
    _points(project, "Poles", [(0, 0)])

    plugin.check_consistency()

    assert shown
    # First part is (0,0)->(10,0): the start is on the pole, the end is not.
    assert [e["msg"].startswith("End") for e in shown[0]] == [True]


def test_a_raster_basemap_does_not_stop_correct(plugin, project, quiet_dialogs):
    """v1.5.0: AttributeError, on any project with a basemap."""
    raster_path = _tiny_raster()
    if raster_path is None:
        pytest.skip("no GDAL python bindings to build a raster with")
    # Named so its layer id sorts before 'Poles', which is the order
    # mapLayers() iterates in.
    basemap = QgsRasterLayer(raster_path, "AAA_basemap")
    assert basemap.isValid()
    project.addMapLayer(basemap)
    route = _route(project, [_straight(0, 0, 100, 0)])
    _points(project, "Poles", [(0, 0), (101, 0)])
    feature = next(route.getFeatures())

    plugin.fix_route_to_pole(feature, must_start=False)

    moved = next(route.getFeatures())
    assert line_vertices(moved.geometry())[-1] == QgsPointXY(101, 0)


def test_a_multipart_route_does_not_stop_correct(plugin, project, quiet_dialogs):
    """v1.5.0: the same TypeError in the Correct path."""
    route = _route(project, [_multipart()])
    _points(project, "Poles", [(31, 0)])
    feature = next(route.getFeatures())

    plugin.fix_route_to_pole(feature, must_start=False)

    # The first part's end moved to the pole; nothing raised.
    moved = next(route.getFeatures())
    assert line_vertices(moved.geometry(), first_part_only=True)[-1] == QgsPointXY(31, 0)


def test_a_pole_with_no_position_is_not_a_correction_target(plugin, project, quiet_dialogs):
    route = _route(project, [_straight(0, 0, 100, 0)])
    _points(project, "Poles", [None, (105, 0)])
    feature = next(route.getFeatures())

    plugin.fix_route_to_pole(feature, must_start=False)

    moved = next(route.getFeatures())
    assert line_vertices(moved.geometry())[-1] == QgsPointXY(105, 0)


def test_a_clean_route_reports_no_errors(plugin, project, quiet_dialogs, shown):
    _route(project, [_straight(0, 0, 100, 0)])
    _points(project, "Poles", [(0, 0), (100, 0)])

    plugin.check_consistency()

    assert not shown, "nothing to correct, so no dialog"
    assert any("No errors found" in str(m) for m in quiet_dialogs)


def test_a_project_with_no_route_layer_does_not_raise(plugin, project, quiet_dialogs, shown):
    """The counter is read outside the block that fills it.

    Assigning it only inside was an UnboundLocalError on exactly the projects
    that skip the body -- no Route layer, or no Poles and no Manholes.
    """
    _points(project, "Poles", [(0, 0)])

    plugin.check_consistency()

    assert not shown


def test_a_project_with_no_pole_or_manhole_layer_does_not_raise(plugin, project, quiet_dialogs, shown):
    _route(project, [_straight(0, 0, 100, 0)])

    plugin.check_consistency()

    assert not shown


# ---------------------------------------------------------------------------
# U15: the logic
# ---------------------------------------------------------------------------

def test_correcting_one_end_does_not_revert_the_other(plugin, project, quiet_dialogs, shown):
    """Measured on v1.5.0: ends (1, 99) -> (0, 99) -> (1, 100).

    The error dicts captured the feature OBJECT, which holds the geometry as it
    was when the check ran. Correcting the start wrote a new shape; correcting
    the end then wrote the stale shape back with only the end moved, undoing
    the first correction. The user saw one end snap and the other let go.
    """
    route = _route(project, [_straight(1, 0, 99, 0)])
    _points(project, "Poles", [(0, 0), (100, 0)])

    plugin.check_consistency()
    assert len(shown[0]) == 2, "both ends are off a pole"
    for error in shown[0]:
        error["popravka"]()

    moved = line_vertices(next(route.getFeatures()).geometry())
    assert (moved[0], moved[-1]) == (QgsPointXY(0, 0), QgsPointXY(100, 0))


def test_a_renamed_trasa_project_is_checked(plugin, project, quiet_dialogs, shown):
    """``layers.get("Route") or layers.get("Route")`` -- the same key twice.

    Under a comment promising "support both Serbian and English names", so the
    Serbian fallback it was written for had been English-ified away. A Trasa /
    Stubovi project was reported as having no errors because nothing was
    looked at.
    """
    _route(project, [_straight(1, 0, 99, 0)], name="Trasa")
    _points(project, "Stubovi", [(0, 0), (100, 0)])

    plugin.check_consistency()

    assert shown, "a renamed project has to be checked at all"
    assert len(shown[0]) == 2


def test_a_renamed_trasa_project_can_be_corrected(plugin, project, quiet_dialogs, shown):
    route = _route(project, [_straight(1, 0, 99, 0)], name="Trasa")
    _points(project, "Stubovi", [(0, 0), (100, 0)])

    plugin.check_consistency()
    for error in shown[0]:
        error["popravka"]()

    moved = line_vertices(next(route.getFeatures()).geometry())
    assert (moved[0], moved[-1]) == (QgsPointXY(0, 0), QgsPointXY(100, 0))


def test_an_end_is_corrected_onto_a_manhole(plugin, project, quiet_dialogs, shown):
    """The check counts manholes; the corrector only looked at Poles.

    So an end near a manhole was reported as an error and then either dragged
    to a distant pole or not corrected at all.
    """
    route = _route(project, [_straight(1, 0, 99, 0)])
    _points(project, "Manholes", [(0, 0), (100, 0)])

    plugin.check_consistency()
    for error in shown[0]:
        error["popravka"]()

    moved = line_vertices(next(route.getFeatures()).geometry())
    assert (moved[0], moved[-1]) == (QgsPointXY(0, 0), QgsPointXY(100, 0))


def test_an_end_already_on_a_manhole_is_not_an_error(plugin, project, quiet_dialogs, shown):
    _route(project, [_straight(0, 0, 100, 0)])
    _points(project, "Poles", [(0, 0)])
    _points(project, "OKNA", [(100, 0)])

    plugin.check_consistency()

    assert not shown, "an end on a manhole is a correct end"


def test_the_nearest_candidate_wins_across_both_layers(plugin, project, quiet_dialogs, shown):
    route = _route(project, [_straight(0, 0, 99, 0)])
    _points(project, "Poles", [(0, 0), (150, 0)])
    _points(project, "Manholes", [(100, 0)])

    plugin.check_consistency()
    for error in shown[0]:
        error["popravka"]()

    moved = line_vertices(next(route.getFeatures()).geometry())
    assert moved[-1] == QgsPointXY(100, 0), "the manhole is nearer than the far pole"


def test_no_route_layer_says_so_instead_of_no_errors(plugin, project, quiet_dialogs, shown):
    """"No errors found!" is the one answer a check must never give blind."""
    _points(project, "Poles", [(0, 0)])

    plugin.check_consistency()

    assert not shown
    assert any("no Route layer" in str(m) for m in quiet_dialogs), quiet_dialogs
    assert not any("No errors found" in str(m) for m in quiet_dialogs)


def test_no_poles_or_manholes_says_so_instead_of_no_errors(plugin, project, quiet_dialogs, shown):
    _route(project, [_straight(1, 0, 99, 0)])

    plugin.check_consistency()

    assert not shown
    assert any("no Poles or Manholes" in str(m) for m in quiet_dialogs), quiet_dialogs


def test_correcting_by_feature_id_works(plugin, project, quiet_dialogs):
    """What the check now passes. A feature is still accepted."""
    route = _route(project, [_straight(0, 0, 99, 0)])
    _points(project, "Poles", [(0, 0), (100, 0)])
    fid = next(route.getFeatures()).id()

    plugin.fix_route_to_pole(fid, must_start=False)

    assert line_vertices(next(route.getFeatures()).geometry())[-1] == QgsPointXY(100, 0)


def test_correcting_by_feature_object_still_works(plugin, project, quiet_dialogs):
    route = _route(project, [_straight(0, 0, 99, 0)])
    _points(project, "Poles", [(0, 0), (100, 0)])

    plugin.fix_route_to_pole(next(route.getFeatures()), must_start=False)

    assert line_vertices(next(route.getFeatures()).geometry())[-1] == QgsPointXY(100, 0)


def test_correcting_a_feature_that_has_gone_is_a_no_op(plugin, project, quiet_dialogs):
    """Re-reading by id means the feature may no longer be there."""
    route = _route(project, [_straight(0, 0, 99, 0)])
    _points(project, "Poles", [(0, 0), (100, 0)])
    fid = next(route.getFeatures()).id()
    route.startEditing()
    route.deleteFeature(fid)
    route.commitChanges()

    plugin.fix_route_to_pole(fid, must_start=False)

    assert route.featureCount() == 0


def _tiny_raster():
    """A 4x4 GeoTIFF, or None when GDAL's python bindings are unavailable."""
    try:
        from osgeo import gdal
    except ImportError:  # pragma: no cover - depends on the image
        return None
    path = os.path.join(tempfile.mkdtemp(), "basemap.tif")
    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(path, 4, 4, 1)
    dataset.SetGeoTransform([0, 1, 0, 4, 0, -1])
    dataset = None
    return path
