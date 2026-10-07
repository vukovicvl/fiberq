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
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.utils.geometry import (
    extract_line_vertices,
    geometry_point,
    get_first_last_points,
    line_endpoint,
    line_part_count,
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


def _route(project, geometries, name="Route", wkb="LineString"):
    """A Route layer.

    ``wkb`` matters more than it looks. A ``LineString`` memory layer CANNOT
    store a multipart feature: the add is accepted into the edit buffer and
    ``commitChanges()`` then answers False with "geometry type is not
    compatible with the current layer" (measured on 3.44.15). Because
    ``getFeatures()`` reads through the buffer, a test that never checks the
    commit sees its multipart feature and looks like it is exercising a real
    layer while the provider holds nothing. The multipart tests below ask for
    ``MultiLineString``, which is also the type a Route layer really has once
    it has been through a GeoPackage or an imported shapefile.
    """
    layer = QgsVectorLayer(f"{wkb}?crs=EPSG:3857", name, "memory")
    layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    layer.updateFields()
    for geom in geometries:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        layer.startEditing()
        assert layer.addFeature(feat)
        assert layer.commitChanges(), layer.commitErrors()
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


# ---------------------------------------------------------------------------
# line_endpoint, and the two QGIS behaviours it rests on
# ---------------------------------------------------------------------------

def test_line_endpoint_reads_a_multipart_s_real_ends(qgis_app):
    assert line_endpoint(_multipart()) == (QgsPointXY(0, 0), 0)
    assert line_endpoint(_multipart(), last=True) == (QgsPointXY(30, 0), 3)


def test_line_endpoint_reads_a_simple_line(qgis_app):
    line = _straight(0, 0, 5, 0)
    assert line_endpoint(line) == (QgsPointXY(0, 0), 0)
    assert line_endpoint(line, last=True) == (QgsPointXY(5, 0), 1)


def test_line_endpoint_has_nothing_to_say_about_an_empty_geometry(qgis_app):
    for geom in (QgsGeometry(), None, QgsGeometry.fromPointXY(QgsPointXY(1, 1))):
        assert line_endpoint(geom) == (None, -1)
        assert line_endpoint(geom, last=True) == (None, -1)


def test_a_global_vertex_index_is_the_concatenation_order(qgis_app):
    """What line_endpoint's index means, pinned.

    ``line_endpoint`` counts vertices by walking the parts in order and handing
    the position straight to ``moveVertex``, which numbers them globally. The
    two orders agreeing is load-bearing and is not written down anywhere in the
    QGIS API docs, so it is measured here.
    """
    geom = _multipart()
    vertices = line_vertices(geom)
    assert len(vertices) == geom.constGet().nCoordinates()
    for index, vertex in enumerate(vertices):
        assert QgsPointXY(geom.vertexAt(index)) == vertex, f"index {index}"


def test_move_vertex_really_keeps_the_part_structure(qgis_app):
    """Why Correct moves a vertex instead of rebuilding the line."""
    geom = _multipart()
    assert geom.moveVertex(31.0, 0.0, 3) is True
    assert geom.isMultipart()
    assert len(geom.asMultiPolyline()) == 2
    assert geom.length() == pytest.approx(21.0)


def test_line_endpoint_indexes_stored_coordinates_not_segmentized_ones(qgis_app):
    """A curved route, which is where the first cut of this fix went wrong.

    ``asPolyline()`` segmentizes a curve before returning, so a vertex list
    taken from it cannot be used to index ``moveVertex``, which addresses the
    coordinates the geometry really holds. The counts are not even in a fixed
    relation: a gentle arc segmentizes to FEWER points than it stores, a tight
    one to far more. Measured on 3.22.16, 3.40.15, 3.44.15, 4.0.3 and 4.2.3.

    The 1 km arc with 1 m of sag is an ordinary road curve. Indexing the
    segmentized list gave 1, which is the arc's middle CONTROL point, and
    ``moveVertex`` answered True -- so Correct dragged the control point onto
    the pole, left the end where it was, and reported success. 1000 m of route
    became a 6.28 m circle.
    """
    gentle = QgsGeometry.fromWkt("CircularString (0 0, 500 1, 1000 0)")
    assert gentle.constGet().nCoordinates() == 3
    assert len(line_vertices(gentle)) == 2, "asPolyline() segmentized it to fewer"
    assert line_endpoint(gentle, last=True) == (QgsPointXY(1000, 0), 2), \
        "the index must be 2, the stored end; 1 is the arc's control point"

    tight = QgsGeometry.fromWkt("CircularString (0 0, 5 5, 10 0)")
    assert tight.constGet().nCoordinates() == 3
    assert len(line_vertices(tight)) > 100, "and this one to far more"
    assert line_endpoint(tight, last=True) == (QgsPointXY(10, 0), 2)

    compound = QgsGeometry.fromWkt(
        "CompoundCurve ((0 0, 500 0), CircularString (500 0, 750 1, 1000 0))")
    assert line_endpoint(compound, last=True) == (QgsPointXY(1000, 0), 3)

    multi = QgsGeometry.fromWkt(
        "MultiCurve ((0 0, 1000 0), CircularString (2000 0, 2500 1, 3000 0))")
    assert line_endpoint(multi, last=True) == (QgsPointXY(3000, 0), 4), \
        "4, not 3 -- 3 is part 2's START"


def test_moving_a_curve_s_end_by_its_stored_index_keeps_the_curve(qgis_app):
    """What the corrected index does, against what the segmentized one did."""
    for wkt, good, bad in (
        ("CircularString (0 0, 500 1, 1000 0)", 2, 1),
        ("CompoundCurve ((0 0, 500 0), CircularString (500 0, 750 1, 1000 0))", 3, 2),
    ):
        right = QgsGeometry.fromWkt(wkt)
        assert right.moveVertex(1010.0, 0.0, good)
        assert right.length() > 1000.0, f"{wkt} kept its shape: {right.asWkt(0)}"

        wrong = QgsGeometry.fromWkt(wkt)
        assert wrong.moveVertex(1010.0, 0.0, bad), "and it answered True, so nothing noticed"
        assert wrong.length() < 600.0, f"{wkt} was wrecked: {wrong.asWkt(0)}"


def test_line_part_count_counts_pieces_not_multipart_ness(qgis_app):
    """isMultipart() is a different question, and the wrong one."""
    one_part_multi = QgsGeometry.fromMultiPolylineXY([[QgsPointXY(0, 0), QgsPointXY(10, 0)]])
    assert one_part_multi.isMultipart(), "a GeoPackage column gives every route this"
    assert line_part_count(one_part_multi) == 1

    assert line_part_count(_multipart()) == 2
    assert line_part_count(_straight(0, 0, 5, 0)) == 1
    assert line_part_count(QgsGeometry.fromWkt(
        "CompoundCurve ((0 0, 500 0), CircularString (500 0, 750 1, 1000 0))")) == 1, \
        "one line made of two segments is one piece"
    assert line_part_count(QgsGeometry.fromWkt(
        "MultiCurve ((0 0, 1000 0), CircularString (2000 0, 2500 1, 3000 0))")) == 2
    for empty in (QgsGeometry(), None, QgsGeometry.fromPointXY(QgsPointXY(1, 1))):
        assert line_part_count(empty) == 0


def test_move_vertex_refuses_an_index_it_does_not_hold(qgis_app):
    """It answers False rather than raising, so the result has to be checked."""
    geom = _multipart()
    assert geom.moveVertex(1.0, 1.0, 99) is False
    assert geom.moveVertex(1.0, 1.0, -1) is False
    assert geom.length() == pytest.approx(20.0), "and it changed nothing"


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
    _route(project, [_multipart()], wkb="MultiLineString")
    _points(project, "Poles", [(0, 0)])

    plugin.check_consistency()

    assert shown
    # The route runs (0,0)..(10,0) then (20,0)..(30,0). Its ends are (0,0),
    # which is on the pole, and (30,0), which is not. Being in two pieces is
    # reported as well, and separately.
    assert [e["msg"].startswith("End") for e in shown[0]] == [False, True]
    assert "2 separate pieces" in shown[0][0]["msg"]


def test_the_check_reads_a_multipart_route_s_real_ends(plugin, project, shown):
    """Both ends on poles, so the only thing left to say is that it is in pieces.

    Reading the ends off the first part alone called this route's real end
    unattached: it looked at where part 1 stops, at (10,0), which is a gap.
    """
    _route(project, [_multipart()], wkb="MultiLineString")
    _points(project, "Poles", [(0, 0), (30, 0)])

    plugin.check_consistency()

    assert len(shown[0]) == 1, [e["msg"] for e in shown[0]]
    assert "2 separate pieces" in shown[0][0]["msg"]
    assert "popravka" not in shown[0][0], "there is no safe automatic fix for a gap"


def test_a_route_stored_back_to_front_is_never_called_clean(plugin, project, shown):
    """The false negative that reading only the outer two ends creates.

    Part order is storage order: whatever a merge, a shapefile or the provider
    produced. The user cannot see it and cannot control it. Stored this way
    round, the junction at (10,0) sits at BOTH outer positions, so both outer
    ends are on the pole while the route's REAL ends, (0,0) and (20,0), are on
    nothing. Measured: without the pieces check this answered "No errors
    found!" -- the one answer a consistency check must never give.
    """
    _route(project, [QgsGeometry.fromMultiPolylineXY(
        [[QgsPointXY(10, 0), QgsPointXY(20, 0)],
         [QgsPointXY(0, 0), QgsPointXY(10, 0)]])], wkb="MultiLineString")
    _points(project, "Poles", [(10, 0)])

    plugin.check_consistency()

    assert shown, "a route with two bare ends must not read as clean"
    assert any("2 separate pieces" in e["msg"] for e in shown[0])


def test_a_single_part_route_is_not_reported_as_being_in_pieces(plugin, project, shown):
    """A GeoPackage column makes every ordinary route isMultipart() with 1 part."""
    _route(project, [QgsGeometry.fromMultiPolylineXY(
        [[QgsPointXY(0, 0), QgsPointXY(100, 0)]])], wkb="MultiLineString")
    _points(project, "Poles", [(0, 0), (100, 0)])

    plugin.check_consistency()

    assert not shown, "one part is one route, however it is stored"


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
    route = _route(project, [_multipart()], wkb="MultiLineString")
    _points(project, "Poles", [(31, 0)])
    feature = next(route.getFeatures())

    plugin.fix_route_to_pole(feature, must_start=False)

    moved = next(route.getFeatures()).geometry()
    assert line_vertices(moved)[-1] == QgsPointXY(31, 0), "the end reached the pole"


def test_correcting_a_multipart_route_keeps_every_part(plugin, project, quiet_dialogs):
    """The regression this file's first version of the fix introduced.

    Correct used to read the first part's vertices and write back
    ``QgsGeometry.fromPolylineXY(poly)``, which is single-part. So attaching
    one end of a 2-part route deleted the other part and still said "Route has
    been automatically attached to a pole." Measured on 3.44.15 with this
    test's own pole at (31,0): 2 parts and 20 m in, 1 part and 31 m out.

    The old test asserted only that the first part's end had moved, so it
    passed the whole time the data was being destroyed. This one asserts the
    part count and the total length, which is what was actually lost.
    """
    route = _route(project, [_multipart()], wkb="MultiLineString")
    _points(project, "Poles", [(31, 0)])
    feature = next(route.getFeatures())

    plugin.fix_route_to_pole(feature, must_start=False)

    moved = next(route.getFeatures()).geometry()
    assert moved.isMultipart(), "a multipart route must stay multipart"
    parts = moved.asMultiPolyline()
    assert len(parts) == 2, f"both parts must survive, got {moved.asWkt(0)}"
    assert [QgsPointXY(p) for p in parts[0]] == [QgsPointXY(0, 0), QgsPointXY(10, 0)], \
        "part 1 is untouched"
    assert [QgsPointXY(p) for p in parts[1]] == [QgsPointXY(20, 0), QgsPointXY(31, 0)], \
        "part 2 keeps its start and its end moved to the pole"
    assert moved.length() == pytest.approx(21.0), "10 m + 11 m, not 31 m"


def test_correcting_a_multipart_route_at_the_start_keeps_every_part(plugin, project, quiet_dialogs):
    """The start is part 1's first vertex, and part 2 must not notice."""
    route = _route(project, [_multipart()], wkb="MultiLineString")
    _points(project, "Poles", [(-1, 0)])
    feature = next(route.getFeatures())

    plugin.fix_route_to_pole(feature, must_start=True)

    moved = next(route.getFeatures()).geometry()
    parts = moved.asMultiPolyline()
    assert len(parts) == 2, f"both parts must survive, got {moved.asWkt(0)}"
    assert QgsPointXY(parts[0][0]) == QgsPointXY(-1, 0)
    assert [QgsPointXY(p) for p in parts[1]] == [QgsPointXY(20, 0), QgsPointXY(30, 0)]
    assert moved.length() == pytest.approx(21.0)


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


# ---------------------------------------------------------------------------
# The same thing on a real file, because that is where the loss was permanent
# ---------------------------------------------------------------------------

def _gpkg_route(project, geom, wkb="MultiLineString"):
    """A GeoPackage-backed Route layer holding one feature."""
    path = os.path.join(tempfile.mkdtemp(), "routes.gpkg")
    mem = QgsVectorLayer(f"{wkb}?crs=EPSG:3857", "Route", "memory")
    mem.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    mem.updateFields()
    feat = QgsFeature(mem.fields())
    feat.setGeometry(geom)
    mem.startEditing()
    assert mem.addFeature(feat)
    assert mem.commitChanges(), mem.commitErrors()

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Route"
    # writeAsVectorFormatV3 is present on the 3.22 floor too (checked on 3.22.16),
    # so there is no fallback to write here.
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem, path, QgsProject.instance().transformContext(), options)
    assert result[0] == QgsVectorFileWriter.WriterError.NoError, result

    layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
    assert layer.isValid()
    project.addMapLayer(layer)
    return layer, path


def _read_once(path):
    """``(part count, length, wkt)`` of the Route layer at ``path``, as plain values.

    It takes a PATH, not a layer, and that is not tidiness. A failing assertion
    makes pytest hold the test's traceback, which holds its frame, which holds
    every local -- so a ``QgsVectorLayer`` opened in the test body stays alive
    until interpreter shutdown and is then destroyed after QGIS itself has gone
    down. On 3.40 and 3.44 the whole file segfaulted at that point, BEFORE
    pytest printed anything: ``.........FF...............F.....`` and exit 139,
    no summary, no FAILED lines, no tracebacks. CI went red with no way to tell
    why, and the one test that says WHAT was destroyed on disk said nothing.

    Opening and dropping the layer inside this function keeps it out of the
    caller's frame, so it is released here, while QGIS is still up, whatever the
    assertions downstream do.
    """
    layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
    assert layer.isValid(), path
    geom = next(layer.getFeatures()).geometry()
    parts = len(geom.asMultiPolyline()) if geom.isMultipart() else 1
    length = geom.length()
    wkt = geom.asWkt(0)
    del geom, layer
    return parts, length, wkt


def test_a_corrected_multipart_route_keeps_both_parts_on_disk(plugin, project, quiet_dialogs):
    """The blocker in the shape that actually loses a customer's data.

    A GeoPackage Route column is MultiLineString, and OGR happily stores a
    single-part LineString in one: ``changeGeometry`` answered True,
    ``commitChanges`` answered "SUCCESS: 1 geometries were changed", and the
    file came back holding ``MultiLineString ((0 0, 31 0))`` -- one part, 31 m,
    where 2 parts and 20 m went in (measured on 3.44.15). Nothing anywhere
    reported a problem. A memory layer hides this, so the check is done against
    a file and after a reload.
    """
    route, path = _gpkg_route(project, _multipart())
    _points(project, "Poles", [(31, 0)])

    plugin.fix_route_to_pole(next(route.getFeatures()), must_start=False)

    parts, length, wkt = _read_once(path)
    assert parts == 2, f"both parts must be on disk, got {wkt}"
    assert length == pytest.approx(21.0)
    assert not plugin.iface.bar.warnings, plugin.iface.bar.warnings


def test_a_single_part_route_on_disk_is_corrected_as_before(plugin, project, quiet_dialogs):
    """The ordinary case, through a real provider: unchanged behaviour."""
    route, path = _gpkg_route(
        project, QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(99, 0)]))
    _points(project, "Poles", [(0, 0), (100, 0)])

    plugin.fix_route_to_pole(next(route.getFeatures()), must_start=False)

    parts, length, wkt = _read_once(path)
    assert (parts, wkt) == (1, "MultiLineString ((0 0, 100 0))"), wkt


def test_correcting_a_curved_route_on_disk_keeps_its_length(plugin, project, quiet_dialogs):
    """End to end, through a real GeoPackage: the curve blocker.

    Before the index was taken from the stored coordinates, this came back as
    ``CircularString (0 0, 1010 0, 1000 0)`` -- 6.28 m, with the end still
    unattached and "Route has been automatically attached to a pole." on
    screen. 1 km of route, gone, reported as a success.
    """
    route, path = _gpkg_route(
        project, QgsGeometry.fromWkt("CircularString (0 0, 500 1, 1000 0)"),
        wkb="CircularString")
    _points(project, "Poles", [(1010, 0)])

    plugin.fix_route_to_pole(next(route.getFeatures()), must_start=False)

    parts, length, wkt = _read_once(path)
    assert length > 1000.0, f"the arc must still span the route, got {wkt}"
    assert "1010 0" in wkt, f"and its END must be the vertex that moved: {wkt}"


# ---------------------------------------------------------------------------
# The edit session Correct opens -- nothing covered this, which is how a
# rollBack() that destroys the user's unsaved work got in with the suite green
# ---------------------------------------------------------------------------

def _mid_edit(route):
    """Put one unsaved route in the layer's buffer, as a digitising user would."""
    route.startEditing()
    feat = QgsFeature(route.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(500, 500), QgsPointXY(600, 500)]))
    assert route.addFeature(feat)
    assert len(route.editBuffer().addedFeatures()) == 1
    return feat


def test_a_refused_correction_keeps_the_user_s_unsaved_routes(plugin, project, quiet_dialogs,
                                                              monkeypatch):
    """The regression that matters most here, because it is silent.

    ``rollBack()`` on the refused branch discarded the WHOLE edit buffer -- the
    correction and everything the user had digitised and not saved -- and said
    only "the route would not take its new shape". Measured on 3.44.15 against
    a GeoPackage: one unsaved route in, nothing out, no mention of it.
    ``utils/errors.py``, which this function imports, states the policy: a
    failed write is never tidied up by throwing the user's work away.
    """
    route = _route(project, [_straight(0, 0, 99, 0)])
    _points(project, "Poles", [(100, 0)])
    target = next(route.getFeatures()).id()
    _mid_edit(route)
    monkeypatch.setattr(route, "changeGeometry", lambda *a, **k: False)

    plugin.fix_route_to_pole(target, must_start=False)

    assert route.isEditable(), "the user's edit session must still be open"
    assert len(route.editBuffer().addedFeatures()) == 1, "their unsaved route must survive"
    assert any("would not take its new shape" in w for w in plugin.iface.bar.warnings)


def test_a_correction_does_not_save_the_user_s_session_for_them(plugin, project, quiet_dialogs):
    """And the success path must not commit work the user did not ask to save."""
    route = _route(project, [_straight(0, 0, 99, 0)])
    _points(project, "Poles", [(100, 0)])
    target = next(route.getFeatures()).id()
    _mid_edit(route)

    plugin.fix_route_to_pole(target, must_start=False)

    assert route.isEditable(), "Correct must not close a session it did not open"
    assert len(route.editBuffer().addedFeatures()) == 1, "still unsaved, still theirs"
    moved = next(f for f in route.getFeatures() if f.id() == target)
    assert line_vertices(moved.geometry())[-1] == QgsPointXY(100, 0), "and it still corrected"


def test_a_correction_still_commits_when_it_opened_the_session(plugin, project, quiet_dialogs):
    """The ordinary case: nobody was editing, so Correct saves its own work."""
    route = _route(project, [_straight(0, 0, 99, 0)])
    _points(project, "Poles", [(100, 0)])
    target = next(route.getFeatures()).id()
    assert not route.isEditable()

    plugin.fix_route_to_pole(target, must_start=False)

    assert not route.isEditable(), "and leaves the layer as it found it"
    moved = next(f for f in route.getFeatures() if f.id() == target)
    assert line_vertices(moved.geometry())[-1] == QgsPointXY(100, 0)


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
