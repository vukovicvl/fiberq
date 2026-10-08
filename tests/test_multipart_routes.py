"""A shapefile Route layer is multipart, and the plugin could not read one.

WP4 4.2 items R7 and R8. Branch ``fix/wp4-write-paths``.

``asPolyline()`` does **not** answer an empty list for a multipart geometry. It
raises ``TypeError``. Measured identically on QGIS 3.22.16, 3.44.15 and 4.0.3::

    LineString (0 0, 10 0)                          -> len 2
    MultiLineString ((0 0, 10 0))          1 part   -> TypeError
    MultiLineString ((0 0,10 0),(20 0,30 0))        -> TypeError
    MultiCurve, 2 parts                             -> TypeError
    CompoundCurve (CircularString ...)     1 part   -> len 181, segmentized

So the idiom this plugin reached for in four places --

    line = geom.asPolyline()
    if not line:
        multi = geom.asMultiPolyline()     # unreachable
        line = multi[0]

-- can never reach its own fallback. The fallback was written for the multipart
case and the multipart case is the one that raises before it.

**And the reason this is not an edge case.** An ESRI Shapefile line layer reads
back as ``MultiLineString`` even when every feature is a plain two-point line:
the format has no single/multi distinction, so OGR declares the layer from the
format rather than from the content. Measured::

    wrote LineString (0 0, 10 0) to .shp
    read back: wkbType MultiLineString, isMultipart True, parts 1
               asPolyline() -> TypeError

A shapefile is the ordinary way to bring an existing network into QGIS, and
``RouteManager._find_route_layer`` tests ``geometryType()`` -- the dimension,
which is ``LineGeometry`` for MultiLineString too -- so such a layer is accepted
as *the* Route layer and reaches every one of those four call sites.

A GeoPackage does it only when the column itself was declared MultiLineString.
FiberQ's own export writes a LineString column, so routes it saved read back
single-part; that is why this went unnoticed.

These tests pin the helper. The behaviour of the operations built on it --
laying a cable, merging routes, building the routing graph -- is pinned in the
tests next to each of those.
"""
import os

import pytest
from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

from fiberq.utils.geometry import line_endpoint, line_part_count, line_parts, line_vertices


def _geom(wkt):
    geom = QgsGeometry.fromWkt(wkt)
    assert not geom.isNull(), f"test's own WKT is bad: {wkt}"
    return geom


# ---------------------------------------------------------------------------
# the measured facts the helper exists for
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wkt", [
    "MultiLineString ((0 0, 10 0))",
    "MultiLineString ((0 0, 10 0),(20 0, 30 0))",
    "MultiCurve (CircularString (0 0, 5 5, 10 0), LineString (20 0, 30 0))",
])
def test_as_polyline_raises_on_multipart_so_the_old_fallback_was_dead(wkt):
    """The fact the whole branch rests on, asserted rather than trusted.

    If a future QGIS made ``asPolyline()`` answer ``[]`` instead of raising, the
    old idiom would start working and this test would be the thing that says so.
    """
    geom = _geom(wkt)
    assert geom.isMultipart()
    with pytest.raises(TypeError):
        geom.asPolyline()


def test_as_multi_polyline_raises_on_a_single_part_so_neither_call_is_safe():
    """The mirror image, which is why the fix cannot just swap the two calls."""
    with pytest.raises(TypeError):
        _geom("LineString (0 0, 10 0)").asMultiPolyline()


# ---------------------------------------------------------------------------
# line_parts
# ---------------------------------------------------------------------------

def test_a_single_line_is_one_part():
    parts = line_parts(_geom("LineString (0 0, 10 0, 20 5)"))
    assert len(parts) == 1
    assert [(p.x(), p.y()) for p in parts[0]] == [(0, 0), (10, 0), (20, 5)]


def test_a_one_part_multilinestring_is_also_one_part():
    """The shape a shapefile gives an ordinary route. This is the case that used
    to raise, and the only reason it ever reached a fallback was that it did
    not."""
    parts = line_parts(_geom("MultiLineString ((0 0, 10 0))"))
    assert len(parts) == 1
    assert [(p.x(), p.y()) for p in parts[0]] == [(0, 0), (10, 0)]


def test_every_part_is_returned_not_just_the_first():
    """The old fallback took ``multi[0]`` and dropped the rest, so a cable laid
    along a two-part route silently used half of it."""
    parts = line_parts(_geom("MultiLineString ((0 0, 10 0),(20 0, 30 0, 40 0))"))
    assert len(parts) == 2
    assert [(p.x(), p.y()) for p in parts[0]] == [(0, 0), (10, 0)]
    assert [(p.x(), p.y()) for p in parts[1]] == [(20, 0), (30, 0), (40, 0)]


def test_a_curve_is_one_part_even_though_it_segmentizes():
    """A CompoundCurve is ONE line made of several segments, not several lines.
    ``asPolyline()`` segmentizes it to 181 points; the part count stays 1."""
    parts = line_parts(_geom("CompoundCurve (CircularString (0 0, 5 5, 10 0))"))
    assert len(parts) == 1
    assert len(parts[0]) > 3, "the curve is segmentized, so this is not the stored count"


@pytest.mark.parametrize("wkt", [
    "Point (1 1)",
    "MultiPoint ((1 1),(2 2))",
    "Polygon ((0 0, 10 0, 10 10, 0 0))",
])
def test_something_that_is_not_a_line_answers_empty_rather_than_raising(wkt):
    """``asPolyline()`` on a point is ``TypeError``, which is how a point
    GeoJSON used to kill the route importer."""
    assert line_parts(_geom(wkt)) == []


def test_a_null_geometry_answers_empty():
    assert line_parts(QgsGeometry()) == []


def test_no_geometry_at_all_answers_empty():
    assert line_parts(None) == []


def test_a_part_with_one_point_is_dropped():
    """A one-point "line" is useless to a caller chaining routes or measuring
    length, and letting it through only moves the crash downstream."""
    parts = line_parts(_geom("MultiLineString ((0 0),(20 0, 30 0))"))
    assert len(parts) == 1
    assert [(p.x(), p.y()) for p in parts[0]] == [(20, 0), (30, 0)]


def test_the_three_line_helpers_agree_about_one_geometry():
    """``line_parts``, ``line_vertices`` and ``line_part_count`` answer three
    different questions about the same geometry and must not disagree -- the
    multipart fix that preceded this branch went wrong exactly by taking an
    index from one source and a point from another."""
    geom = _geom("MultiLineString ((0 0, 10 0),(20 0, 30 0, 40 0))")
    parts = line_parts(geom)
    assert len(parts) == line_part_count(geom) == 2
    assert sum(len(part) for part in parts) == len(line_vertices(geom)) == 5
    start, start_idx = line_endpoint(geom)
    end, end_idx = line_endpoint(geom, last=True)
    assert (start.x(), start.y()) == (0, 0) and start_idx == 0
    assert (end.x(), end.y()) == (40, 0) and end_idx == 4


# ---------------------------------------------------------------------------
# the shapefile fact, through a real file
# ---------------------------------------------------------------------------

def test_a_shapefile_route_layer_is_multipart_even_for_a_plain_line(qgis_app, tmp_path):
    """The reason any of this is reachable.

    Written through a real ``QgsVectorFileWriter`` and read back through OGR,
    because the claim is about the format and the provider, not about QGIS's
    in-memory classes.
    """
    source = QgsVectorLayer("LineString?crs=EPSG:3857&field=naziv:string", "Route", "memory")
    feature = QgsFeature(source.fields())
    feature.setGeometry(_geom("LineString (0 0, 10 0)"))
    feature.setAttribute("naziv", "an ordinary single-part route")
    assert source.dataProvider().addFeatures([feature])[0]

    path = str(tmp_path / "route.shp")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(
        source, path, QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    assert os.path.exists(path)

    layer = QgsVectorLayer(path, "Route", "ogr")
    assert layer.isValid()
    assert QgsWkbTypes.displayString(layer.wkbType()) == "MultiLineString", (
        "a shapefile line layer is declared MultiLineString by the format, not by its "
        "content -- if this ever changes, the whole premise of this module is stale")

    geom = next(layer.getFeatures()).geometry()
    assert geom.isMultipart()
    assert line_part_count(geom) == 1, "one part, but still multipart"
    with pytest.raises(TypeError):
        geom.asPolyline()

    parts = line_parts(geom)
    assert len(parts) == 1
    assert [(p.x(), p.y()) for p in parts[0]] == [(0, 0), (10, 0)]


def test_the_route_layer_resolver_accepts_a_multipart_layer(qgis_app):
    """``geometryType()`` is the dimension, so MultiLineString passes the Route
    test. That is why a shapefile Route layer reaches the broken call sites
    rather than being rejected early with a clear message."""
    layer = QgsVectorLayer("MultiLineString?crs=EPSG:3857", "Route", "memory")
    assert layer.isValid()
    assert layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry
