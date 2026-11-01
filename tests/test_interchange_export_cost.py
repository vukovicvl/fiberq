"""What a bundle export no longer does for every feature.

Found in the v1.6.0 QA (finding Q30): the GeoPackage bundle of the city_S
project (24 layers, 14,024 features) took 4.6-5.7% longer to export than in
v1.5.0 on QGIS 4.2.3, and 2.8-3.0% longer on 3.40.15, all of it CPU, in the
loop that builds each layer's bundle copy, ``_canonical_layer``:

* U13's check of each reprojected feature went through
  ``utils.geometry.transformed``: a second copy of the geometry, then
  ``is_finite`` -- a second null test, the bounding box, its four values read
  one by one and four ``math.isfinite`` in a generator. The loop now moves its
  own copy, as v1.5.0 did, and asks ``QgsRectangle.isFinite()`` of the same
  bounding box: ``transform_in_place``;
* ``canonical_value`` was called for every value of every column, though it can
  change a value only in a column with a value domain -- seven columns, in three
  rosters. The loop now asks ``has_value_domain`` once per column.

Each cut is pinned by a test below, so the cost cannot come back unseen. The
others hold that every answer stayed the same: the same features left out, the
same coordinates, the same values, the same log line.
"""
import itertools
import logging
import math
import sqlite3
from contextlib import closing

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)

from fiberq.core import interchange_bundle as bundle_module
from fiberq.core import interchange_fields as fm
from fiberq.core.interchange_bundle import InterchangeBundleWriter
from fiberq.utils import geometry as geometry_module

#: A place in Serbia in UTM 33N, and the out-of-domain pair U13 measured.
GOOD = "LineString (480000 4797000, 480100 4797000)"
FAR = "LineString (1e15 1e15, 2e15 2e15)"


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:32633"))
    yield prj
    prj.clear()


@pytest.fixture
def bundle_path(tmp_path):
    return str(tmp_path / "design.gpkg")


def _layer(name, rows, geometry="LineString", crs="EPSG:32633",
           fields=("fiberq_uuid:string(64)", "naziv:string")):
    uri = f"{geometry}?crs={crs}&" + "&".join(f"field={f}" for f in fields)
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), name
    features = []
    for wkt, attrs in rows:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        for key, value in attrs.items():
            feature.setAttribute(key, value)
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    return layer


def _column(path, table, column):
    with closing(sqlite3.connect(path)) as conn:
        return dict(conn.execute(f'SELECT fiberq_uuid, "{column}" FROM "{table}"').fetchall())


@pytest.fixture
def logged(qgis_app):
    """What utils.geometry logs, as the FiberQ panel shows it: FiberQ's loggers
    do not propagate, so caplog never sees them."""
    lines = []

    class Lines(logging.Handler):
        def emit(self, record):
            lines.append((record.name, record.levelname, record.getMessage()))

    handler = Lines(logging.WARNING)
    geometry_module.logger.addHandler(handler)
    yield lines
    geometry_module.logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# the check of each reprojected feature
# ---------------------------------------------------------------------------

def test_qgsrectangle_isfinite_tests_the_four_values_is_finite_tests(qgis_app):
    """The premise of the one-call check, on every combination of a number,
    inf, -inf and nan in the four values. Set one by one, so no normalising
    constructor reorders them."""
    for values in itertools.product((1.5, math.inf, -math.inf, math.nan), repeat=4):
        box = QgsRectangle()
        box.setXMinimum(values[0])
        box.setYMinimum(values[1])
        box.setXMaximum(values[2])
        box.setYMaximum(values[3])
        four = (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum())
        assert box.isFinite() == all(math.isfinite(value) for value in four), values


@pytest.mark.parametrize("source, target, wkt", [
    ("EPSG:32633", "EPSG:4326", GOOD),
    ("EPSG:32633", "EPSG:4326", FAR),                                   # inf, no raise
    ("EPSG:32633", "EPSG:4326", "LineString (480000 4797000, 1e15 1e15)"),
    ("EPSG:32633", "EPSG:4326", "MultiLineString ((480000 4797000, 480100 4797000),(1e15 1e15, 2e15 2e15))"),
    ("EPSG:32633", "EPSG:4326", "Polygon ((1e15 1e15, 2e15 1e15, 2e15 2e15, 1e15 1e15))"),
    ("EPSG:32633", "EPSG:4326", "Point (1e15 1e15)"),                   # raises, after the damage
    ("EPSG:32633", "EPSG:4326", "MultiPoint ((1e15 1e15),(480000 4797000))"),   # raises part way
    ("EPSG:32633", "EPSG:4326", "MultiPoint ((480000 4797000),(480010 4797010))"),
    ("EPSG:32633", "EPSG:4326", "CircularString (480000 4797000, 480050 4797050, 480100 4797000)"),
    ("EPSG:32633", "EPSG:4326", "LineString Z (480000 4797000 5, 480100 4797000 6)"),
    ("EPSG:3857", "EPSG:4326", "Point (1e30 1e30)"),                    # clamped, finite
    ("EPSG:3857", "EPSG:4326", "LineString (2333000 5490000, 2334000 5491000)"),
    ("EPSG:4326", "EPSG:3857", "Point (0 95)"),
    ("EPSG:4326", "EPSG:3857", "LineString (0 95, 1 96)"),
    ("EPSG:4326", "EPSG:3857", "Point (21.9 43.32)"),
])
def test_transform_in_place_answers_as_transformed_does(logged, source, target, wkt):
    """False for the same geometries, the same coordinates otherwise, and the
    same line in the log when the transform raises."""
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(source),
                                       QgsCoordinateReferenceSystem(target),
                                       QgsCoordinateTransformContext())
    geometry = QgsGeometry.fromWkt(wkt)
    assert not geometry.isNull() and not geometry.isEmpty(), wkt

    expected = geometry_module.transformed(QgsGeometry(geometry), transform)
    logged_by_transformed = list(logged)
    del logged[:]
    moved = QgsGeometry(geometry)
    answer = geometry_module.transform_in_place(moved, transform)

    assert answer == (expected is not None)
    if answer:
        assert moved.asWkb() == expected.asWkb()
    assert logged == logged_by_transformed


def test_the_export_checks_each_feature_without_a_second_copy(project, bundle_path, monkeypatch):
    """Through transformed() and is_finite(), not at all; and the feature that
    cannot be reprojected is still left out and counted."""
    asked = []
    real_transformed, real_is_finite = geometry_module.transformed, geometry_module.is_finite

    def transformed(geom, transform):
        asked.append("transformed")
        return real_transformed(geom, transform)

    def is_finite(geom):
        asked.append("is_finite")
        return real_is_finite(geom)

    monkeypatch.setattr(geometry_module, "transformed", transformed)
    monkeypatch.setattr(geometry_module, "is_finite", is_finite)
    monkeypatch.setattr(bundle_module, "transformed", transformed, raising=False)
    routes = _layer("Route", [(GOOD, {"fiberq_uuid": "u-1"}), (FAR, {"fiberq_uuid": "u-far"}),
                              ("LineString (480200 4797000, 480300 4797000)", {"fiberq_uuid": "u-2"})])

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[routes])

    assert result.ok, result.errors
    assert asked == []
    assert sorted(_column(bundle_path, "Route", "fiberq_uuid")) == ["u-1", "u-2"]
    assert "1 feature(s) could not be reprojected to EPSG:4326" in " ".join(result.warnings)


# ---------------------------------------------------------------------------
# the translation of each value
# ---------------------------------------------------------------------------

def test_has_value_domain_is_where_canonical_value_can_change_a_value(qgis_app):
    """Every column of every roster, and names no roster has, against every
    value any domain or alias holds: canonical_value changes one exactly where
    has_value_domain says it can."""
    probes = {"", "x", "NULL", 0, 1.5}
    for table in list(fm.VALUE_DOMAINS.values()) + list(fm.ENGLISH_ALIASES.values()):
        probes |= set(table) | set(table.values())
    names = {name for roster in fm.ROSTERS.values() for name in roster.values()}
    names |= {fm.IDENTITY_FIELD, fm.CABLE_REFERENCE_FIELD, "fq_type", "own column"}
    domains = 0
    for roster in list(fm.ROSTERS) + ["no roster"]:
        for name in sorted(names):
            changed = [value for value in probes if fm.canonical_value(roster, name, value) is not value]
            assert fm.has_value_domain(roster, name) == bool(changed), (roster, name, changed)
            domains += bool(changed)
    assert domains == len(fm.VALUE_DOMAINS)


def test_only_a_column_with_a_value_domain_is_translated(project, bundle_path, monkeypatch):
    """canonical_value is asked for route_type alone -- not for the identity,
    the name, nor any column of a layer whose roster has no domain -- and the
    values come out as they did."""
    asked = []
    real = fm.canonical_value

    def canonical_value(roster, canonical_name, value):
        asked.append((roster, canonical_name))
        return real(roster, canonical_name, value)

    monkeypatch.setattr(fm, "canonical_value", canonical_value)
    routes = _layer("Route", [
        (GOOD, {"fiberq_uuid": "u-1", "naziv": "one", "tip_trase": "podzemna"}),
        (GOOD, {"fiberq_uuid": "u-2", "naziv": "two", "tip_trase": "Aerial"}),
        (GOOD, {"fiberq_uuid": "u-3", "naziv": "three", "tip_trase": "own value"}),
    ], fields=("fiberq_uuid:string(64)", "naziv:string", "tip_trase:string"))
    poles = _layer("Poles", [("Point (480000 4797000)", {"fiberq_uuid": "p-1", "naziv": "P1"})],
                   geometry="Point")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[routes, poles])

    assert result.ok, result.errors
    assert asked == [("route", "route_type")] * 3
    assert _column(bundle_path, "Route", "route_type") == {
        "u-1": "underground", "u-2": "aerial", "u-3": "own value"}
    assert _column(bundle_path, "Route", "name") == {"u-1": "one", "u-2": "two", "u-3": "three"}
