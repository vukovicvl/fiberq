"""Lay cable looks for its single route among the routes near the first element.

WP4 task 4.1, item PF-7 (the route search). Before trying the network, lay
cable asks whether one route passes within 1 of both selected elements, and
lays the cable along that stretch of it. It read every route to find out: a
Python pass over every vertex of the Route layer, ~0.06 s of a 0.29 s lay cable
at the benchmark's size S (cProfile, 3.44.15).

Now, on a GeoPackage nobody is editing, it reads only the routes the file's own
R-tree stores within 2 of the first element, plus every row that is not one
line (``core.cable_manager._routes_near``, ``utils.geopackage.rows_near``), in
fid order, and runs the same test over them. OGR's box request would drop rows
the search can take -- on 3.22 a row with a one-vertex part, which fails OGR's
own geometry test -- and GDAL's box of a multi-part row with a NaN starting a
part can leave out the part the search takes (code reviews); a table declared
LINESTRING can hold either. A row of one line is boxed in full. An edited
layer, a shapefile and a memory layer are still read whole.

**Counted, not timed**: routes handed out, against the parent's. Equivalence:
the search run as written and with ``_routes_near`` answering None, over
element pairs on the XS city and over the rows the code review built.
"""
import random
import shutil

import pytest
from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsLineString,
    QgsMultiLineString,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

import fiberq.core.cable_manager as cable_manager
from fiberq.utils.geometry import line_parts
from fiberq.utils.geopackage import rows_near
from fiberq.utils.spatial import box_around


@pytest.fixture(autouse=True)
def canvas_not_rendering(qgis_canvas):
    """pytest-qgis's canvas renders the project's layers in a worker thread,
    which made GeoPackage tests flaky on QGIS 4.2 (branch 12)."""
    qgis_canvas.setRenderFlag(False)
    yield
    qgis_canvas.setRenderFlag(True)


#: The size below which a route table is read whole, as shipped: the tests that
#: count and the one at the edge run with it; the rest, on small tables, without.
SHIPPED_FEWEST_ROUTES = cable_manager._FEWEST_ROUTES


@pytest.fixture(autouse=True)
def every_table_is_narrowed(monkeypatch):
    """The tables here are small; the size below which a table is read whole has its own tests."""
    monkeypatch.setattr(cable_manager, "_FEWEST_ROUTES", 0)


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


def _routes(tmp_path, geometries, storage="gpkg", name="Route", declared="LineString"):
    """A Route layer holding ``geometries`` in this order (fids 1, 2, ...)."""
    layer = QgsVectorLayer(f"{declared}?crs=EPSG:3857&field=naziv:string", name, "memory")
    features = []
    for geometry in geometries:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    if storage == "memory":
        return layer
    path = tmp_path / f"{name}-{declared}-{len(geometries)}.gpkg"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    written = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    saved = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
    assert saved.isValid()
    return saved


def _line(*points):
    return QgsGeometry(QgsLineString([QgsPoint(x, y) for x, y in points]))


def _wkt(geometry):
    return None if geometry is None else geometry.asWkt(6)


def _both(route, a, b):
    """The search as written, and reading every route: (narrowed, whole)."""
    narrowed = _wkt(cable_manager._along_one_route(route, a, b))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cable_manager, "_routes_near", lambda *args, **kwargs: None)
        whole = _wkt(cable_manager._along_one_route(route, a, b))
    return narrowed, whole


def _counting(patch):
    counts = {"features": 0}
    real_get = QgsVectorLayer.getFeatures

    def get(self, *args, **kwargs):
        for feat in real_get(self, *args, **kwargs):
            counts["features"] += 1
            yield feat

    patch.setattr(QgsVectorLayer, "getFeatures", get)
    return counts


def _street(n, z=False, m=False):
    def vertex(x, y):
        return QgsPoint(x, y, 1.5 if z else None, 2.5 if m else None)
    return [QgsGeometry(QgsLineString([vertex(i * 100.0, 0), vertex(i * 100.0 + 40, 0), vertex(i * 100.0 + 40, 30)]))
            for i in range(n)]


def _read_by_one_search(tmp_path, n, storage, declared="LineString"):
    route = _routes(tmp_path, _street(n, "Z" in declared, declared.endswith("M")), storage, declared=declared)
    last = (n - 1) * 100.0   # the scan stops at the first route it takes: make it the last
    with pytest.MonkeyPatch.context() as patch:
        counted = _counting(patch)
        cable = cable_manager._along_one_route(route, QgsPointXY(last, 0), QgsPointXY(last + 40, 30))
    assert _wkt(cable) == f"LineString ({last:g} 0, {last + 40:g} 0, {last + 40:g} 30)"
    return counted["features"]


@pytest.mark.parametrize("declared", ["LineString", "LineStringZ", "LineStringM", "LineStringZM",
                                      "MultiLineString", "MultiLineStringZ", "MultiLineStringM", "MultiLineStringZM"])
def test_the_route_search_reads_the_routes_near_the_element_not_every_route(
        qgis_app, tmp_path, declared, monkeypatch):
    """The parent read every route: 500 and 2,000. Now the same few at both, at
    the shipped size threshold, in a table of lines and in one of one-part
    multi-lines, as GDAL writes a shapefile's lines, with Z and M or without."""
    monkeypatch.setattr(cable_manager, "_FEWEST_ROUTES", SHIPPED_FEWEST_ROUTES)
    small = _read_by_one_search(tmp_path, 500, "gpkg", declared)
    large = _read_by_one_search(tmp_path, 2000, "gpkg", declared)
    assert small == large and small < 5, (small, large)


def test_a_row_of_two_parts_is_read_wherever_it_is(qgis_app, tmp_path):
    """Its stored box cannot be trusted to hold the part the search takes, so it
    is read with the routes near the element, however far it is."""
    far = [_multi([(90000 + i * 100, 0), (90040 + i * 100, 0)], [(90000 + i * 100, 50), (90040 + i * 100, 50)])
           for i in range(3)]
    route = _gpkg_rows(tmp_path, "two_parts_far", [geometry for geometry in _street(40)] + far)
    near = {f.id() for f in cable_manager._routes_near(route, QgsPointXY(3900, 0))}
    assert {41, 42, 43} <= near and len(near) < 8, near


def test_a_memory_route_layer_is_still_read_whole(qgis_app, tmp_path):
    """A memory layer's box can miss an arc QGIS cannot box, which the search would take."""
    assert _read_by_one_search(tmp_path, 40, "memory") == 40


def test_every_pair_on_the_xs_city_finds_the_route_the_whole_scan_found(project, city_xs_dataset, tmp_path):
    """Pairs of vertices of one route part (taken), of two routes (mostly not),
    nudged, and node positions: the same cable, or the same None."""
    for key in ("gpkg", "qgz"):
        shutil.copy(city_xs_dataset[key], tmp_path)
    assert project.read(str(tmp_path / "city_XS.qgz"))
    route = project.mapLayersByName("Route")[0]
    assert route.dataProvider().storageType() == "GPKG"
    rng = random.Random(1307)
    parts = [line for feature in route.getFeatures() for line in line_parts(feature.geometry())]
    nodes = [f.geometry().asPoint() for name in ("Poles", "Manholes", "Joint Closures")
             for layer in project.mapLayersByName(name) for f in layer.getFeatures()]
    pairs = []
    for line in rng.sample(parts, 120):
        i, j = rng.sample(range(len(line)), 2)
        pairs.append((line[i], line[j]))
        pairs.append((QgsPointXY(line[i].x() + 0.6, line[i].y() - 0.3), line[j]))
    for _ in range(120):
        pairs.append((rng.choice(nodes), rng.choice(nodes)))
        a, b = rng.choice(parts), rng.choice(parts)
        pairs.append((a[0], b[-1]))
    taken = 0
    for a, b in pairs:
        narrowed, whole = _both(route, QgsPointXY(a), QgsPointXY(b))
        assert narrowed == whole, (a.asWkt(), b.asWkt())
        taken += whole is not None
    assert taken > 100, taken


NAN = float("nan")


def _gpkg_rows(tmp_path, name, geometries, declared="LineString"):
    """A GeoPackage table declared ``declared`` holding ``geometries`` as rows 1, 2, ..., written by the provider.

    The provider writes a geometry as it is: GDAL stores a MultiLineString in a
    LINESTRING table (with a warning), as ogr2ogr does with a shapefile's lines.
    """
    empty = QgsVectorLayer(f"{declared}?crs=EPSG:3857&field=naziv:string", "Route", "memory")
    path = tmp_path / f"{name}.gpkg"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Route"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(empty, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
    for geometry in geometries:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        assert layer.dataProvider().addFeatures([feature])[0]
    layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
    assert layer.isValid()
    return layer


def _multi(*parts):
    shape = QgsMultiLineString()
    for part in parts:
        shape.addGeometry(QgsLineString([QgsPoint(x, y) for x, y in part]))
    return QgsGeometry(shape)


#: The part the search takes between the elements (1000, 2000) and (1020, 2000).
GOOD = [(1000, 2000), (1010, 2000), (1020, 2000)]
#: Routes far away, so that the rows read regardless stay under a quarter of the table.
FAR = [_line((50000 + i * 100, 0), (50040 + i * 100, 0)) for i in range(10)]

#: A route the scan takes through its good part, ahead of a plain one between
#: the same elements.
CORRUPT_ROWS = {
    # GDAL stores this row's box as (0, 0, 0, 0): OGR's box request drops it.
    "nan part": _multi(GOOD, [(NAN, NAN), (3000, 3000)]),
    # Fails OGR's geometry test on 3.22, which then drops it.
    "one-vertex part": _multi(GOOD, [(5000, 5000)]),
    # A plain two-part row in a LINESTRING table.
    "two parts": _multi(GOOD, [(4000, 4000), (4010, 4000)]),
    # A NaN starting a part leaves that bound of the row's box at 0, or at the
    # parts after it (code review): (0, 0, 2000, 3005) and (1000, 3005, 0, 0)
    # for these two, and for the last two a box of the far part only.
    "nan x starting the last part": _multi(GOOD, [(NAN, 2000), (3000, 3005)]),
    "nan y starting the last part": _multi(GOOD, [(3000, NAN), (3005, 3000)]),
    "nan starting a middle part": _multi(GOOD, [(NAN, NAN), (3000, 3005)], [(5000, 5000), (5030, 5000)]),
    "nan x starting a middle part": _multi(GOOD, [(NAN, 2000), (3000, 3005)], [(5000, 5000), (5030, 5000)]),
}


@pytest.mark.parametrize("declared", ["LineString", "MultiLineString"])
@pytest.mark.parametrize("case", sorted(CORRUPT_ROWS))
def test_a_row_ogrs_box_request_drops_is_still_taken(qgis_app, tmp_path, case, declared):
    """Code reviews: OGR's box request dropped the first two rows, the R-tree's
    box of the NaN ones misses their good part, and the scan laid the cable
    along it. Rows of more than one line are read regardless."""
    route = _gpkg_rows(tmp_path, f"{case.replace(' ', '_')}-{declared}",
                       [CORRUPT_ROWS[case], QgsGeometry.fromPolylineXY(
                           [QgsPointXY(1000, 2000), QgsPointXY(1010, 2005), QgsPointXY(1020, 2000)])] + FAR,
                       declared)
    first = min(f.id() for f in route.getFeatures())
    assert first in {f.id() for f in cable_manager._routes_near(route, QgsPointXY(1000, 2000))}
    narrowed, whole = _both(route, QgsPointXY(1000, 2000), QgsPointXY(1020, 2000))
    assert narrowed == whole == "LineString (1000 2000, 1010 2000, 1020 2000)"


@pytest.mark.parametrize("start", [(NAN, NAN), (NAN, 2000), (1000, NAN)])
def test_a_route_starting_at_nan_is_never_taken_either_way(qgis_app, tmp_path, start):
    """A row of one line, so left to its R-tree box, which a NaN first vertex
    puts at 0 on that axis, away from the elements: it is not read, and the
    scan cannot take it either (its min() is NaN), so both take the good one."""
    route = _routes(tmp_path, [_line(start, (1000, 2000), (1010, 2000), (1020, 2000)),
                               _line((1000, 2000), (1010, 2005), (1020, 2000))] + FAR)
    nan_route = min(f.id() for f in route.getFeatures())
    assert nan_route not in {f.id() for f in cable_manager._routes_near(route, QgsPointXY(1000, 2000))}
    narrowed, whole = _both(route, QgsPointXY(1000, 2000), QgsPointXY(1020, 2000))
    assert narrowed == whole == "LineString (1000 2000, 1010 2005, 1020 2000)"


def test_a_table_of_multi_part_routes_is_read_whole(qgis_app, tmp_path):
    """Reading a row by its fid costs 3-4 times reading it in a scan (round-4
    review: a table of two-part routes made the search up to twice as slow as
    the whole read). Where the rows to read -- the one near the element and
    every two-part row -- would be more than a quarter of the table, every
    route is read, as before; at a quarter, only those."""
    def table(two_parts):
        far = [_multi([(90000 + i * 100, 0), (90040 + i * 100, 0)], [(90000 + i * 100, 50), (90040 + i * 100, 50)])
               for i in range(two_parts)]
        return _routes(tmp_path, _street(40) + far, declared="MultiLineString")

    element = QgsPointXY(3900, 0)
    quarter, more = table(12), table(13)
    assert cable_manager._routes_near(quarter, element) is not None   # 13 rows of 52
    assert cable_manager._routes_near(more, element) is None          # 14 rows of 53
    for route in (quarter, more):
        narrowed, whole = _both(route, element, QgsPointXY(3940, 30))
        assert narrowed == whole == "LineString (3900 0, 3940 0, 3940 30)"


def test_the_search_stops_reading_at_the_route_it_takes(qgis_app, tmp_path):
    """The routes come a chunk at a time, in fid order, so a pair on the first
    route reads one chunk -- the whole read stops at its first route too --
    rather than every two-part row of the table first (round-4 review)."""
    far = [_multi([(90000 + i * 100, 0), (90040 + i * 100, 0)], [(90000 + i * 100, 50), (90040 + i * 100, 50)])
           for i in range(150)]
    route = _routes(tmp_path, _street(800) + far, declared="MultiLineString")
    with pytest.MonkeyPatch.context() as patch:
        counted = _counting(patch)
        cable = cable_manager._along_one_route(route, QgsPointXY(0, 0), QgsPointXY(40, 30))
    assert _wkt(cable) == "LineString (0 0, 40 0, 40 30)"
    assert counted["features"] <= 64, counted


def test_a_small_route_table_is_read_whole(qgis_app, tmp_path, monkeypatch):
    """Below 500 routes the whole read costs about what the narrowed read's
    fixed work does: on the XS city's 250 the narrowed search was the slower
    for every pair (round-5 review). At the shipped threshold, not a patched one."""
    monkeypatch.setattr(cable_manager, "_FEWEST_ROUTES", SHIPPED_FEWEST_ROUTES)
    assert cable_manager._routes_near(_routes(tmp_path, _street(499)), QgsPointXY(0, 0)) is None
    assert cable_manager._routes_near(_routes(tmp_path, _street(500)), QgsPointXY(0, 0)) is not None


def test_the_quarter_is_counted_in_the_file(qgis_app, tmp_path):
    """QGIS keeps the row count it last read, and another program deleting
    rows leaves it behind: measured against it, the narrowed read ran where
    the whole read was 1.5-1.9 times faster (round-5 review). The file's own
    count is used."""
    import sqlite3
    from contextlib import closing
    far = [_multi([(90000 + i * 100, 0), (90040 + i * 100, 0)], [(90000 + i * 100, 50), (90040 + i * 100, 50)])
           for i in range(12)]
    route = _routes(tmp_path, _street(40) + far, declared="MultiLineString")
    element = QgsPointXY(3900, 0)
    assert cable_manager._routes_near(route, element) is not None          # 13 rows of 52
    with closing(sqlite3.connect(route.source().split("|")[0])) as db:
        db.execute('DELETE FROM "Route" WHERE fid <= 20')
        db.commit()
    assert route.featureCount() == 52, "premise: QGIS still counts the rows another program deleted"
    assert cable_manager._routes_near(route, element) is None              # 13 rows of 32
    narrowed, whole = _both(route, element, QgsPointXY(3940, 30))
    assert narrowed == whole == "LineString (3900 0, 3940 0, 3940 30)"


@pytest.mark.parametrize("position", [63, 64, 191, 192])
def test_a_route_at_a_chunks_edge_is_taken_as_the_whole_read_takes_it(qgis_app, tmp_path, position):
    """The routes are read by fid in chunks of 64, 128, ...: the route taken sits
    last in one chunk or first in the next, and a second route joining the
    same elements right after it. Every fifth row is a far two-part route,
    read regardless (round-5 review: no test read past the first chunk)."""
    target = 5 * position + 1
    rows = []
    for fid in range(1, 1101):
        x = 90000 + fid * 100
        if fid == target:
            rows.append(_line(*GOOD))
        elif fid == target + 1:
            rows.append(_line((1000, 2000), (1020, 2000)))
        elif fid % 5 == 0:
            rows.append(_multi([(x, 0), (x + 40, 0)], [(x, 50), (x + 40, 50)]))
        else:
            rows.append(_line((x, 0), (x + 40, 0)))
    route = _routes(tmp_path, rows, declared="MultiLineString")
    ids = sorted(rows_near(route, box_around(QgsPointXY(1000, 2000), 2.0)).ids)
    assert ids.index(target) == position and ids.index(target + 1) == position + 1
    assert cable_manager._routes_near(route, QgsPointXY(1000, 2000)) is not None
    narrowed, whole = _both(route, QgsPointXY(1000, 2000), QgsPointXY(1020, 2000))
    assert narrowed == whole == "LineString (1000 2000, 1010 2000, 1020 2000)"


def test_routes_crowding_the_start_of_the_table_are_read_in_one_plain_read(qgis_app, tmp_path):
    """The table's first 200 rows are two-part routes, all read regardless: by
    fid each costs 3-4 times a scan row, and a pair after them was up to 1.7
    times slower than the whole read (round-5 review). Once the rows to read
    crowd the table's start, the rest come from one plain read, in fid order."""
    far = [_multi([(90000 + i * 100, 0), (90040 + i * 100, 0)], [(90000 + i * 100, 50), (90040 + i * 100, 50)])
           for i in range(200)]
    route = _routes(tmp_path, far + _street(800), declared="MultiLineString")
    by_fid = []
    real_get = QgsVectorLayer.getFeatures

    def get(self, *args, **kwargs):
        if args and isinstance(args[0], QgsFeatureRequest) and args[0].filterFids():
            by_fid.append(len(args[0].filterFids()))
        return real_get(self, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(QgsVectorLayer, "getFeatures", get)
        assert cable_manager._routes_near(route, QgsPointXY(0, 0)) is not None
        narrowed, whole = _both(route, QgsPointXY(0, 0), QgsPointXY(40, 30))
    assert narrowed == whole == "LineString (0 0, 40 0, 40 30)"
    assert by_fid == [], by_fid


def test_routes_crowding_the_start_of_a_table_written_again_are_read_in_one_plain_read(qgis_app, tmp_path):
    """GDAL's keys count on from the highest ever written, so a table whose
    routes were deleted and written again starts far from fid 1; measured
    from 1, its crowded start never switched to the plain read, and a pair
    after it was up to 2-3 times slower than the whole read (round-6 review)."""
    far = [_multi([(90000 + i * 100, 0), (90040 + i * 100, 0)], [(90000 + i * 100, 50), (90040 + i * 100, 50)])
           for i in range(200)]
    route = _routes(tmp_path, far + _street(800), declared="MultiLineString")
    geometries = [f.geometry() for f in sorted(route.getFeatures(), key=lambda f: f.id())]
    assert route.dataProvider().deleteFeatures([f.id() for f in route.getFeatures()])
    again = []
    for geometry in geometries:
        feature = QgsFeature(route.fields())
        feature.setGeometry(geometry)
        again.append(feature)
    assert route.dataProvider().addFeatures(again)[0]
    route = QgsVectorLayer(route.source(), "Route", "ogr")
    assert min(f.id() for f in route.getFeatures()) > 1000, "premise: the keys count on"
    by_fid = []
    real_get = QgsVectorLayer.getFeatures

    def get(self, *args, **kwargs):
        if args and isinstance(args[0], QgsFeatureRequest) and args[0].filterFids():
            by_fid.append(len(args[0].filterFids()))
        return real_get(self, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(QgsVectorLayer, "getFeatures", get)
        narrowed, whole = _both(route, QgsPointXY(0, 0), QgsPointXY(40, 30))
    assert narrowed == whole == "LineString (0 0, 40 0, 40 30)"
    assert by_fid == [], by_fid


def _keyed(tmp_path, declaration, rows):
    """A GeoPackage "Route" table keyed ``declaration``, holding ``rows`` -- (key, geometry) -- stored in this order
    (rowids 10, 20, ...), with the blobs and R-tree boxes GDAL writes, the R-tree keyed as GDAL keys it."""
    import sqlite3
    from contextlib import closing
    source = QgsVectorLayer("MultiLineString?crs=EPSG:3857", "base", "memory")
    features = []
    for _key, geometry in rows:
        feature = QgsFeature(source.fields())
        feature.setGeometry(geometry)
        features.append(feature)
    assert source.dataProvider().addFeatures(features)[0]
    path = tmp_path / (declaration.replace(" ", "_") + ".gpkg")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "base"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(source, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    alias, text = declaration == "INTEGER PRIMARY KEY", declaration.startswith("TEXT")
    with closing(sqlite3.connect(str(path))) as db:
        stored = db.execute("SELECT b.fid, b.geom, r.minx, r.maxx, r.miny, r.maxy FROM base AS b "
                            "JOIN rtree_base_geom AS r ON r.id = b.fid ORDER BY b.fid").fetchall()
        srs = db.execute("SELECT srs_id FROM gpkg_geometry_columns WHERE table_name = 'base'").fetchone()[0]
        db.execute('CREATE TABLE "Route" (pk %s, geom MULTILINESTRING)' % declaration)
        db.execute('CREATE VIRTUAL TABLE "rtree_Route_geom" USING rtree(id, minx, maxx, miny, maxy)')
        for (key, _geometry), (fid, blob, *box) in zip(rows, stored):
            rowid = key if alias else fid * 10
            if alias:
                db.execute('INSERT INTO "Route" (pk, geom) VALUES (?, ?)', (key, blob))
            else:
                db.execute('INSERT INTO "Route" (rowid, pk, geom) VALUES (?, ?, ?)',
                           (rowid, "k%d" % key if text else key, blob))
            db.execute('INSERT INTO "rtree_Route_geom" VALUES (?, ?, ?, ?, ?)', [rowid if text else key] + box)
        db.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) "
                   "VALUES ('Route', 'features', 'Route', ?)", (srs,))
        db.execute("INSERT INTO gpkg_geometry_columns VALUES ('Route', 'geom', 'MULTILINESTRING', ?, 0, 0)", (srs,))
        db.execute("INSERT INTO gpkg_extensions VALUES ('Route', 'geom', 'gpkg_rtree_index', "
                   "'http://www.geopackage.org/spec120/#extension_rtree', 'write-only')")
        db.commit()
    layer = QgsVectorLayer(f"{path}|layername=Route", "Route", "ogr")
    assert layer.isValid()
    return layer


#: The straight route stored first under key 7, the bent one second under key 3, a two-part row far away.
KEYED_ROWS = [(7, _line(*GOOD)), (3, _line((1000, 2000), (1010, 2005), (1020, 2000))),
              (100, _multi([(90000, 0), (90040, 0)], [(90000, 50), (90040, 50)]))]
KEYED_ROWS += [(101 + i, line) for i, line in enumerate(FAR)]


@pytest.mark.parametrize("declaration", ["INT PRIMARY KEY", "INTEGER PRIMARY KEY DESC", "TEXT PRIMARY KEY"])
def test_a_table_keyed_other_than_by_its_rowid_is_read_whole(qgis_app, tmp_path, declaration):
    """GDAL reads a GeoPackage table in rowid order. With an INT key, or
    INTEGER ... DESC, its fid is the key, and fid order put the bent route,
    key 3, ahead of the straight one the whole read takes first; with a TEXT
    key the fid is the rowid, and the two-part row's string key made lay cable
    raise (round-4 review). GDAL opens all three without a word; they are read
    whole."""
    route = _keyed(tmp_path, declaration, KEYED_ROWS)
    assert cable_manager._routes_near(route, QgsPointXY(1000.3, 2000)) is None
    narrowed, whole = _both(route, QgsPointXY(1000.3, 2000), QgsPointXY(1019.6, 2000))
    assert narrowed == whole == "LineString (1000 2000, 1010 2000, 1020 2000)"


def test_a_table_keyed_by_its_rowid_is_read_near_the_element(qgis_app, tmp_path):
    """The GeoPackage standard's key, INTEGER PRIMARY KEY: fid order is the order of a whole read."""
    route = _keyed(tmp_path, "INTEGER PRIMARY KEY", KEYED_ROWS)
    assert [f.id() for f in cable_manager._routes_near(route, QgsPointXY(1000.3, 2000))] == [3, 7, 100]
    narrowed, whole = _both(route, QgsPointXY(1000.3, 2000), QgsPointXY(1019.6, 2000))
    assert narrowed == whole == "LineString (1000 2000, 1010 2005, 1020 2000)"


def test_a_route_beyond_float32_is_read_whole(qgis_app, tmp_path):
    """A GeoPackage's R-tree keeps float32 bounds and stores one beyond
    +/-3.4e38 as an infinity on the inside of the box, so the search missed a
    route out there that the whole read took (round-4 review). No query
    reaching beyond 1e38 is asked of the R-tree."""
    route = _routes(tmp_path, [_line((1e39, 0), (1e39, 10), (1e39, 20))] + FAR)
    assert cable_manager._routes_near(route, QgsPointXY(1e39, 0.4)) is None
    narrowed, whole = _both(route, QgsPointXY(1e39, 0.4), QgsPointXY(1e39, 19.7))
    assert narrowed == whole and whole is not None


def test_a_shapefile_or_an_edited_route_layer_is_read_whole(qgis_app, tmp_path):
    """A shapefile drops a one-vertex part's row on 3.22 too and has no R-tree to
    read; an edited layer's routes are partly QGIS's buffer, not the file's."""
    route = _routes(tmp_path, _street(6))
    shapefile = tmp_path / "routes.shp"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(route, str(shapefile), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    assert cable_manager._routes_near(QgsVectorLayer(str(shapefile), "Route", "ogr"), QgsPointXY(0, 0)) is None
    assert cable_manager._routes_near(route, QgsPointXY(0, 0)) is not None
    assert route.startEditing()
    try:
        assert cable_manager._routes_near(route, QgsPointXY(0, 0)) is None
    finally:
        route.rollBack()


def test_an_edit_buffer_is_read_in_the_whole_scans_order(qgis_app, tmp_path):
    """Two routes added in the buffer and a saved one moved, all joining the
    same two points: the first in the whole read is an added one."""
    route = _routes(tmp_path, [_line((0, 0), (10, 0), (20, 0)), _line((500, 500), (600, 500))])
    assert route.startEditing()
    try:
        for geometry in (_line((0, 0), (10, -5), (20, 0)), _line((0, 0), (10, 7), (20, 0))):
            added = QgsFeature(route.fields())
            added.setGeometry(geometry)
            assert route.addFeature(added)
        saved = sorted(f.id() for f in route.getFeatures() if f.id() >= 0)
        assert route.changeGeometry(saved[1], _line((0, 0), (10, 3), (20, 0)))
        narrowed, whole = _both(route, QgsPointXY(0, 0), QgsPointXY(20, 0))
        assert narrowed == whole == "LineString (0 0, 10 -5, 20 0)"
    finally:
        route.rollBack()
