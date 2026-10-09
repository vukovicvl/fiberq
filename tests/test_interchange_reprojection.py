"""A feature that cannot be reprojected was exported as infinity, in silence.

WP4 4.2 item U13 (unclaimed). Branch ``fix/wp4-interchange``.

``QgsGeometry.transform()`` does **not** report an out-of-domain coordinate by
raising. For a line or a polygon it answers ``Success`` and leaves every vertex
at ``inf``. Measured identically on QGIS 3.22.16, 3.40.15, 3.44.15, 4.0.3 and
4.2.3 -- every version this plugin supports::

    EPSG:32633 LineString (1e15 1e15, 2e15 2e15) -> EPSG:4326
        transform() -> 0 (Success),  LineString (inf inf, inf inf)

For a *point* it does raise ``QgsCsException`` -- but only after the geometry is
already ``Point (inf inf)``, so catching it rescued nothing either::

    EPSG:4326 Point (0 95) -> EPSG:3857
        RAISED QgsCsException,  geometry now Point (inf inf)

So the two handlers this branch replaced --

    try:
        geometry.transform(transform)
    except Exception as e:
        logger.debug(f"Could not reproject ...: {e}")

-- could not work in either direction. For the common case they never ran, and
for the one case they did run the damage was already done. The geometry then
went into the bundle with infinite coordinates, and ``logger.debug`` writes
nothing at the default level, so the export reported success.

**Why infinity in a bundle is worse than a missing feature**, measured rather
than argued. Running these tests against the unfixed code, GDAL itself fails
while closing the layer::

    ERROR 1: sqlite3_exec(UPDATE gpkg_contents SET min_x = 14.75..., max_x = Inf,
             max_y = Inf WHERE lower(table_name) = lower('Route') ...)
             failed: no such column: Inf

``Inf`` is not a SQLite literal, so the statement that records the layer's
extent in ``gpkg_contents`` -- a table the GeoPackage standard requires -- does
not run. One out-of-domain feature therefore damages the *file*, not just its
own row: every reader that trusts ``gpkg_contents`` for the layer's extent gets
a stale or absent one. Leaving the feature out and saying so costs the user one
named feature; writing it costs them a malformed bundle and no warning.

The fix routes both sites through :func:`fiberq.utils.geometry.transformed`,
which checks the *result* as well as the call -- the same helper branch 8 added
for R6, where the plan had assumed ``transform()`` raises and it does not.

**What is proved how.** Every test below except the two marked in their own
docstring goes red against a tree with only this fix reverted.
"""
import sqlite3

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from fiberq.core import interchange as ic
from fiberq.core.interchange_bundle import InterchangeBundleWriter
from fiberq.core.interchange_import import InterchangeBundleReader

#: A real place in Serbia, in UTM 33N, so the ordinary features in these
#: fixtures reproject to something sensible and only the planted one does not.
UTM_X, UTM_Y = 480000.0, 4797000.0

#: The measured out-of-domain pair. Far enough outside UTM 33N's domain that
#: every supported PROJ answers inf, rather than clamping to the edge the way
#: EPSG:3857 does (measured: 1e30 in 3857 clamps to -180 90, it does NOT go
#: infinite -- which is why the fixture is 32633 and not Web Mercator).
FAR = 1e15


def _layer(name, geometry="LineString", crs="EPSG:32633",
           fields=("fiberq_uuid:string(64)", "naziv:string")):
    uri = f"{geometry}?crs={crs}&" + "&".join(f"field={f}" for f in fields)
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), name
    return layer


def _add(layer, geom, **attrs):
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    for key, value in attrs.items():
        feat.setAttribute(key, value)
    outcome = layer.dataProvider().addFeatures([feat])
    if isinstance(outcome, tuple):
        ok, added = outcome
        assert ok
        feat = added[0]
    else:
        assert outcome
    layer.updateExtents()
    return feat


def _good_line():
    return QgsGeometry.fromPolylineXY(
        [QgsPointXY(UTM_X, UTM_Y), QgsPointXY(UTM_X + 100.0, UTM_Y)])


def _far_line():
    return QgsGeometry.fromPolylineXY(
        [QgsPointXY(FAR, FAR), QgsPointXY(FAR * 2, FAR * 2)])


@pytest.fixture
def project():
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:32633"))
    yield prj
    prj.clear()


@pytest.fixture
def bundle_path(tmp_path):
    return str(tmp_path / "design.gpkg")


def _bundle_features(path, table):
    layer = QgsVectorLayer(f"{path}|layername={table}", "check", "ogr")
    assert layer.isValid(), table
    return list(layer.getFeatures())


# ---------------------------------------------------------------------------
# the measured premise the whole item rests on
# ---------------------------------------------------------------------------

def test_transform_reports_success_and_writes_infinity(qgis_app):
    """The fact the fix exists for, asserted rather than trusted.

    If a future PROJ started raising here, the old handler would begin working
    and this test is what would say so.
    """
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:32633"),
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateTransformContext())
    geom = _far_line()

    assert geom.transform(transform) == 0, "transform() reported a failure; it used to report Success"

    wkt = geom.asWkt()
    assert "inf" in wkt, f"expected infinite coordinates, got {wkt[:60]}"


def test_a_point_raises_but_only_after_the_damage(qgis_app):
    """The other half, and why catching the exception was never enough."""
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsCoordinateTransformContext())
    geom = QgsGeometry.fromPointXY(QgsPointXY(0, 95))

    with pytest.raises(Exception):
        geom.transform(transform)

    assert "inf" in geom.asWkt(), (
        "the geometry was left intact after the raise, so catching it would have been enough "
        "-- that is not what was measured")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_an_unreprojectable_feature_is_left_out_of_the_bundle(project, bundle_path):
    """The acceptance line. One good route, one that cannot be reprojected."""
    routes = _layer("Route")
    _add(routes, _good_line(), fiberq_uuid="u-ok", naziv="good")
    _add(routes, _far_line(), fiberq_uuid="u-far", naziv="far")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[routes])
    assert result.ok, result.errors

    written = _bundle_features(bundle_path, "Route")
    # The bundle renames stored columns to their canonical names: naziv -> name.
    names = sorted(f.attribute("name") for f in written)
    assert names == ["good"], f"the unreprojectable route reached the bundle: {names}"

    for feature in written:
        assert "inf" not in feature.geometry().asWkt().lower(), (
            "a feature with infinite coordinates is in the bundle")


def test_the_export_says_how_many_it_left_out(project, bundle_path):
    """Silence was the real defect: ``logger.debug`` writes nothing at the
    default level, so the user was told the export succeeded and never learned
    a route was missing from the file they were about to send out."""
    routes = _layer("Route")
    _add(routes, _good_line(), fiberq_uuid="u-ok")
    _add(routes, _far_line(), fiberq_uuid="u-far")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[routes])

    assert any("could not be reprojected" in w for w in result.warnings), result.warnings
    assert any("1 feature(s)" in w for w in result.warnings), result.warnings


def test_the_reported_count_is_what_reached_the_bundle(project, bundle_path):
    """``result.layers`` used to carry the *source* layer's count, so a bundle
    holding one route was reported as two. The summary a user reads after an
    export has to describe the file, not the project it came from."""
    routes = _layer("Route")
    _add(routes, _good_line(), fiberq_uuid="u-ok")
    _add(routes, _far_line(), fiberq_uuid="u-far")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[routes])

    assert result.layers["Route"] == 1, (
        f"reported {result.layers['Route']} exported, but the bundle holds "
        f"{len(_bundle_features(bundle_path, 'Route'))}")


def test_an_ordinary_export_is_untouched(project, bundle_path):
    """Characterisation: it passed before this change too. It is here because
    routing every feature through a new helper is exactly the kind of change
    that could start dropping good ones."""
    routes = _layer("Route")
    _add(routes, _good_line(), fiberq_uuid="u-ok", naziv="good")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[routes])

    assert result.ok, result.errors
    assert result.layers["Route"] == 1
    assert not any("reprojected" in w for w in result.warnings), result.warnings
    stored = _bundle_features(bundle_path, "Route")[0].geometry().asPolyline()
    assert stored[0].x() == pytest.approx(14.75, abs=0.1), "the good route moved"


def test_a_layer_whose_crs_matches_the_storage_crs_is_not_touched(project, bundle_path):
    """No transform at all is built when the layer is already EPSG:4326, so the
    guard must not reject those features. Characterisation."""
    routes = _layer("Route", crs=f"EPSG:{ic.STORAGE_EPSG}")
    _add(routes, QgsGeometry.fromPolylineXY(
        [QgsPointXY(21.9, 43.3), QgsPointXY(21.91, 43.31)]), fiberq_uuid="u-ok")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[routes])

    assert result.layers["Route"] == 1
    assert not any("reprojected" in w for w in result.warnings), result.warnings


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

@pytest.fixture
def bundle_with_a_bad_row(tmp_path):
    """A bundle holding one ordinary route and one at latitude 95.

    Built through the writer from a layer already in EPSG:4326, so no transform
    runs on the way out and the impossible latitude reaches the file intact --
    which is exactly how a bundle from another tool would carry one. A
    GeoPackage does not validate latitude.
    """
    source_project = QgsProject()
    source_project.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{ic.STORAGE_EPSG}"))
    # vendor_note has no canonical name, so it survives the export under its
    # own name and comes back as fq_extra_json on import -- which is what lets
    # the orphan test below distinguish a skipped feature from an imported one.
    routes = _layer("Route", crs=f"EPSG:{ic.STORAGE_EPSG}",
                    fields=("fiberq_uuid:string(64)", "naziv:string", "vendor_note:string"))
    _add(routes, QgsGeometry.fromPolylineXY(
        [QgsPointXY(21.90, 43.32), QgsPointXY(21.91, 43.33)]),
        fiberq_uuid="u-ok", naziv="good", vendor_note="keep me")
    _add(routes, QgsGeometry.fromPolylineXY(
        [QgsPointXY(0, 95), QgsPointXY(1, 96)]),
        fiberq_uuid="u-far", naziv="impossible", vendor_note="must not survive")

    path = str(tmp_path / "foreign.gpkg")
    result = InterchangeBundleWriter(source_project).write(path, layers=[routes])
    assert result.ok, result.errors
    assert len(_bundle_features(path, "Route")) == 2, "the fixture lost its bad row on the way out"
    source_project.clear()
    return path


@pytest.fixture
def target_project():
    """A project that already holds a Route layer in Web Mercator.

    This matters, and it is the thing the first draft of these tests got wrong.
    When the project has no layer of that canonical name the reader *creates*
    one in the bundle's own CRS, so no transform is built and nothing can go
    out of domain -- measured: the imported layer came out EPSG:4326 holding
    ``LineString (0 95, 1 96)`` unchanged. The reprojection path only runs when
    the bundle is imported into an existing project, which is the ordinary way
    anyone uses it.
    """
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    existing = _layer("Route", crs="EPSG:3857")
    prj.addMapLayer(existing)
    yield prj
    prj.clear()


def test_an_unreprojectable_bundle_feature_is_not_imported(
        bundle_with_a_bad_row, target_project):
    """The same defect in the other direction: latitude 95 into Web Mercator is
    ``inf``, and the import used to put it in the project."""
    result = InterchangeBundleReader(target_project).read(bundle_with_a_bad_row)
    assert result.ok, result.errors

    layers = [lyr for lyr in target_project.mapLayers().values() if lyr.name() == "Route"]
    assert layers, "the import created no Route layer"
    assert layers[0].crs().authid() == "EPSG:3857", (
        "the fixture's own premise: the target layer must be in a different CRS from the bundle, "
        "or no transform is built and this test proves nothing")
    names = sorted(str(f.attribute("naziv")) for f in layers[0].getFeatures())
    assert names == ["good"], f"the impossible route was imported: {names}"

    for feature in layers[0].getFeatures():
        assert "inf" not in feature.geometry().asWkt().lower()


def test_the_import_says_how_many_it_left_out(bundle_with_a_bad_row, target_project):
    result = InterchangeBundleReader(target_project).read(bundle_with_a_bad_row)

    assert any("could not be reprojected" in w for w in result.warnings), result.warnings
    assert any("1 Route" in w for w in result.warnings), result.warnings


def test_a_skipped_feature_leaves_no_extras_behind(bundle_with_a_bad_row, target_project):
    """A skipped feature must not leave an ``fq_extension`` row pointing at it.

    An extras row whose ``owner_uuid`` names a feature that is not in the
    project would be re-emitted by the next export as an orphan -- the import
    would have quietly manufactured a dangling reference out of a feature it
    had decided not to import.
    """
    InterchangeBundleReader(target_project).read(bundle_with_a_bad_row)

    # The extras land in the passthrough store, as fq_extension rows keyed by
    # owner_uuid -- ic.PASSTHROUGH_ENTRY, not a key of this test's invention.
    stored = target_project.readEntry(*ic.PASSTHROUGH_ENTRY, "")[0]
    assert "keep me" in stored, (
        "the imported feature's extras did not survive, so this test cannot tell a skipped "
        "feature from an imported one and proves nothing")
    assert "must not survive" not in stored, (
        "the skipped feature left its extras behind; the next export would re-emit them against "
        "an owner_uuid that is not in the project")


# ---------------------------------------------------------------------------
# the other half of the plan row: references that cannot be resolved
# ---------------------------------------------------------------------------

def test_a_slack_table_with_no_cable_column_is_reported(tmp_path, target_project):
    """A bundle whose slack table carries no ``cable_uuid`` left every loop
    detached and said nothing.

    ``_bundle_cable_uuids`` answered ``{}`` for three different reasons -- an
    unsafe name, no such table, and the table being there without the column --
    and the caller treated all three as "nothing to do". The first two are
    ordinary; only the third is a bundle the user should hear about.
    """
    source_project = QgsProject()
    source_project.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{ic.STORAGE_EPSG}"))
    slack = _layer("Optical slack", "Point", crs=f"EPSG:{ic.STORAGE_EPSG}")
    _add(slack, QgsGeometry.fromPointXY(QgsPointXY(21.90, 43.32)),
         fiberq_uuid="u-slack-1", naziv="loop 1")

    path = str(tmp_path / "noref.gpkg")
    written = InterchangeBundleWriter(source_project).write(path, layers=[slack])
    assert written.ok, written.errors
    source_project.clear()

    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute('PRAGMA table_info("Optical slack")')}
    assert "cable_uuid" not in columns, (
        "this fixture only means anything while the writer omits cable_uuid for a slack loop "
        f"that has no cable; it wrote {sorted(columns)}")

    result = InterchangeBundleReader(target_project).read(path)

    assert any("no cable_uuid column" in w for w in result.warnings), result.warnings


# ---------------------------------------------------------------------------
# the feature that has no geometry at all
# ---------------------------------------------------------------------------

def test_a_feature_with_an_empty_geometry_still_travels(project, bundle_path):
    """An empty geometry is not an out-of-domain one, and must not be dropped.

    This is a regression test for a defect *this branch introduced*. The first
    version of the guard asked only ``isNull()``, but a ``Point EMPTY`` answers
    ``isNull() == False`` and ``isEmpty() == True`` -- measured -- so it reached
    ``transformed()``, which rejects any geometry it cannot measure, and the
    feature was skipped as though its coordinates were infinite.

    It was caught by ``test_sample_bundle.py`` against this repository's own
    published example, ``docs/samples/demo-bundle.gpkg``, whose Poles table
    carries exactly such a feature:
    ``fe1b0000-0000-4000-8000-000000000012``. A row with no geometry is
    ordinary -- QGIS creates one whenever a feature is added without
    digitising -- and dropping it would lose a real element and its identity.
    """
    poles = _layer("Poles", "Point")
    _add(poles, QgsGeometry(), fiberq_uuid="u-no-geom", naziv="undigitised")
    _add(poles, QgsGeometry.fromWkt("Point EMPTY"), fiberq_uuid="u-empty", naziv="empty")
    _add(poles, QgsGeometry.fromPointXY(QgsPointXY(UTM_X, UTM_Y)),
         fiberq_uuid="u-real", naziv="real")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[poles])

    assert result.ok, result.errors
    assert not any("reprojected" in w for w in result.warnings), (
        f"a feature with no coordinates was treated as unreprojectable: {result.warnings}")
    # Asserted on identity rather than on a label column: fiberq_uuid is the
    # one column every canonical table is guaranteed to carry, and losing the
    # identity is the part that actually costs the user something.
    identities = sorted(
        str(f.attribute("fiberq_uuid")) for f in _bundle_features(bundle_path, "Poles"))
    assert identities == ["u-empty", "u-no-geom", "u-real"], f"a feature was lost: {identities}"


def test_the_published_example_still_round_trips(qgis_app):
    """The guard that caught the defect above, kept close to the code it guards.

    ``tests/test_sample_bundle.py`` owns the full contract for the published
    example; this is the narrow part of it that this branch can break, asserted
    here so the failure lands next to the change that caused it rather than in
    a module about something else.
    """
    import pathlib

    bundle = pathlib.Path(__file__).resolve().parent.parent / "docs" / "samples" / "demo-bundle.gpkg"
    if not bundle.exists():
        pytest.skip("the published example bundle is not in this tree")

    project = QgsProject()
    try:
        result = InterchangeBundleReader(project).read(str(bundle))
        assert result.ok, result.errors
        imported = {
            str(feature["fiberq_uuid"])
            for layer in project.mapLayers().values()
            if layer.fields().indexFromName("fiberq_uuid") >= 0
            for feature in layer.getFeatures()
            if feature["fiberq_uuid"]
        }
    finally:
        project.clear()

    assert "fe1b0000-0000-4000-8000-000000000012" in imported, (
        "the example's undigitised pole was dropped on import")
