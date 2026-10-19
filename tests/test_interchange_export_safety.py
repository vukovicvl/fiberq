"""What an export cannot write it now says, instead of writing something else.

Unclaimed (WP3 code), found in the v1.6.0 review. Measured on 3.22, 3.44 and
4.2 before FiberQ 1.6.0:

- two layers that are one FiberQ layer by name -- "Poles" beside the pre-1.0
  "Stubovi" -- both became the table "Poles", and the second write replaced the
  first: the first layer's features were not in the bundle, and nothing said so;
- a layer with no valid CRS, or with one that has no transformation to
  EPSG:4326, was written with its coordinates unmoved into a table that
  declares EPSG:4326;
- a column of the user's own with the name of one the writer fills failed the
  whole export when the names differed only in case (`Name` beside FiberQ's
  `naziv`, `FQ_TYPE`, `geom`, a text `fid`, `Owner` beside `owner`), and lost a
  value when they matched exactly (an own `name` beside `naziv` was merged into
  it, an own `cable_uuid` on a slack layer was overwritten).

Results are read back with sqlite3 as plain data.
"""
import hashlib
import json
import os
import sqlite3
from contextlib import closing

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsFeature,
                       QgsGeometry, QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer)

from fiberq.core import interchange as ic
from fiberq.core.interchange_bundle import InterchangeBundleWriter
from fiberq.core.interchange_import import InterchangeBundleReader

LON, LAT = 21.90, 43.32
UUID = "Point?crs=EPSG:4326&field=fiberq_uuid:string(64)"


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    yield prj
    prj.clear()


def _layer(project, uri, name, rows, x=LON, y=LAT):
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), uri
    features = []
    for position, attrs in enumerate(rows):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x + position * 0.001, y)))
        for key, value in attrs.items():
            feature.setAttribute(key, value)
        features.append(feature)
    if features:
        assert layer.dataProvider().addFeatures(features)[0]
    project.addMapLayer(layer)
    return layer


def _write(project, path, layers, passthrough=None):
    return InterchangeBundleWriter(project).write(str(path), layers=layers,
                                                  passthrough=passthrough)


def _rows(path, sql):
    with closing(sqlite3.connect(str(path))) as conn:
        return conn.execute(sql).fetchall()


def _tables(path):
    return {name for (name,) in _rows(path, "SELECT table_name FROM gpkg_contents")}


def _extras(path, table):
    """``{fiberq_uuid: fq_extra_json as a dict}``, an empty dict for none."""
    return {uuid: json.loads(extra) if extra else {}
            for uuid, extra in _rows(path, f'SELECT fiberq_uuid, fq_extra_json FROM "{table}"')}


# -- one layer per bundle table -------------------------------------------------


def test_two_layers_with_one_fiberq_name_are_refused_and_nothing_is_written(project, tmp_path):
    poles = _layer(project, UUID, "Poles", [{"fiberq_uuid": "p1"}, {"fiberq_uuid": "p2"}])
    stubovi = _layer(project, UUID, "Stubovi", [{"fiberq_uuid": "s1"}])
    target = tmp_path / "b.gpkg"
    assert _write(project, target, [poles]).ok, "premise: a bundle is there to protect"
    before = hashlib.sha256(target.read_bytes()).hexdigest()

    result = _write(project, target, [poles, stubovi])

    assert not result.ok
    (error,) = result.errors
    assert "'Poles'" in error and "'Stubovi'" in error and "temporary scratch layer" in error
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before, (
        "a refused export changed the bundle it was refused for")


def test_the_refusal_says_where_each_layers_data_lives(project, tmp_path):
    source = str(tmp_path / "poles.gpkg")
    stored = QgsVectorLayer(UUID, "poles", "memory")
    feature = QgsFeature(stored.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    feature.setAttribute("fiberq_uuid", "g1")
    assert stored.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "poles"
    QgsVectorFileWriter.writeAsVectorFormatV3(stored, source, QgsCoordinateTransformContext(),
                                              options)
    on_disk = QgsVectorLayer(f"{source}|layername=poles", "Poles", "ogr")
    assert on_disk.isValid()
    project.addMapLayer(on_disk)
    stubovi = _layer(project, UUID, "Stubovi", [{"fiberq_uuid": "s1"}])

    result = _write(project, tmp_path / "b.gpkg", [on_disk, stubovi])
    assert not result.ok
    assert "poles.gpkg" in result.errors[0]
    assert not os.path.exists(tmp_path / "b.gpkg")


@pytest.mark.parametrize("empty_first", [True, False])
def test_an_empty_duplicate_is_left_out_whichever_comes_first(project, tmp_path, empty_first):
    empty = _layer(project, UUID, "Poles", [])
    filled = _layer(project, UUID, "Stubovi", [{"fiberq_uuid": "s1"}])
    layers = [empty, filled] if empty_first else [filled, empty]
    out = tmp_path / "b.gpkg"

    result = _write(project, out, layers)

    assert result.ok, result.errors
    assert _rows(out, 'SELECT fiberq_uuid FROM "Poles"') == [("s1",)]
    assert [name for name, _reason in result.skipped] == ["Poles"]


def test_the_same_layer_passed_twice_is_one_layer(project, tmp_path):
    """A guard for the refusal above rather than an old defect: one layer is not two."""
    poles = _layer(project, UUID, "Poles", [{"fiberq_uuid": "p1"}])
    result = _write(project, tmp_path / "b.gpkg", [poles, poles])
    assert result.ok, result.errors
    assert result.layers == {"Poles": 1}
    assert result.skipped == []


def test_the_geojson_profile_refuses_the_same_way(project, tmp_path):
    poles = _layer(project, UUID, "Poles", [{"fiberq_uuid": "p1"}])
    stubovi = _layer(project, UUID, "Stubovi", [{"fiberq_uuid": "s1"}])
    folder = tmp_path / "geojson"
    result = InterchangeBundleWriter(project).write_geojson(str(folder),
                                                            layers=[poles, stubovi])
    assert not result.ok
    assert not folder.exists()


# -- coordinates the bundle cannot place --------------------------------------------


ENGINEERING = ('LOCAL_CS["Undefined cartesian SRS",LOCAL_DATUM["unknown",32767],'
               'UNIT["unknown",0],AXIS["Easting",EAST],AXIS["Northing",NORTH]]')


def _unplaceable(project, crs="none"):
    """A Manholes layer with no CRS, or one QGIS accepts but cannot transform.

    Its CRS is set after it is in the project: outside the desktop, a layer that
    arrives without one is given EPSG:4326, which is not what this is about. The
    desktop leaves it unknown by default ("Leave as unknown CRS").
    """
    lost = _layer(project, "Point?field=fiberq_uuid:string(64)", "Manholes",
                  [{"fiberq_uuid": "m1"}], x=7500000.0, y=4800000.0)
    if crs == "engineering":
        lost.setCrs(QgsCoordinateReferenceSystem.fromWkt(ENGINEERING))
        assert lost.crs().isValid(), "premise: a CRS QGIS accepts but cannot transform"
    else:
        lost.setCrs(QgsCoordinateReferenceSystem())
        assert not lost.crs().isValid(), "premise: no CRS at all"
    return lost


@pytest.mark.parametrize("crs", ["none", "engineering"])
def test_a_layer_whose_coordinates_cannot_reach_epsg_4326_is_left_out(project, tmp_path, crs):
    lost = _unplaceable(project, crs)
    poles = _layer(project, UUID, "Poles", [{"fiberq_uuid": "p1"}])
    out = tmp_path / "b.gpkg"

    result = _write(project, out, [lost, poles])

    assert result.ok, result.errors
    assert "Manholes" not in _tables(out)
    assert result.layers == {"Poles": 1}
    assert any("'Manholes'" in warning and "EPSG:4326" in warning
               for warning in result.warnings), result.warnings
    assert "Manholes" in [name for name, _reason in result.skipped]


def test_nothing_placeable_is_an_error_not_an_empty_bundle(project, tmp_path):
    lost = _unplaceable(project)
    result = _write(project, tmp_path / "b.gpkg", [lost])
    assert not result.ok
    assert not os.path.exists(tmp_path / "b.gpkg")


# -- columns with a name FiberQ writes ------------------------------------------------


def test_a_column_differing_only_in_case_from_fiberqs_is_carried(project, tmp_path):
    odf = _layer(project, UUID + "&field=naziv:string&field=Name:string", "ODF",
                 [{"fiberq_uuid": "u1", "naziv": "N1", "Name": "own"}])
    out = tmp_path / "b.gpkg"

    result = _write(project, out, [odf])

    assert result.ok, result.errors
    assert _rows(out, 'SELECT name FROM "ODF"') == [("N1",)]
    assert _extras(out, "ODF") == {"u1": {"Name": "own"}}
    assert any("ODF.Name" in warning for warning in result.warnings), result.warnings


def test_an_own_column_with_fiberqs_name_keeps_its_value(project, tmp_path):
    """Before, the two were merged: the first value filled won, the other was lost."""
    odf = _layer(project, UUID + "&field=name:string&field=naziv:string", "ODF",
                 [{"fiberq_uuid": "u1", "name": "own", "naziv": "N1"},
                  {"fiberq_uuid": "u2", "name": None, "naziv": "N2"}])
    out = tmp_path / "b.gpkg"

    assert _write(project, out, [odf]).ok

    assert _rows(out, 'SELECT fiberq_uuid, name FROM "ODF" ORDER BY fiberq_uuid') == [
        ("u1", "N1"), ("u2", "N2")]
    assert _extras(out, "ODF") == {"u1": {"name": "own"}, "u2": {}}


def test_an_own_cable_uuid_on_a_slack_layer_is_not_overwritten(project, tmp_path):
    cables = QgsVectorLayer("LineString?crs=EPSG:4326&field=fiberq_uuid:string(64)",
                            "Underground cables", "memory")
    cable = QgsFeature(cables.fields())
    cable.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(LON, LAT),
                                                  QgsPointXY(LON + 0.01, LAT)]))
    cable.setAttribute("fiberq_uuid", "c1")
    ok, (cable,) = cables.dataProvider().addFeatures([cable])
    assert ok
    project.addMapLayer(cables)
    slack = _layer(project, UUID + "&field=cable_layer_id:string&field=cable_fid:integer"
                   "&field=cable_uuid:string", "Optical slack",
                   [{"fiberq_uuid": "s1", "cable_layer_id": cables.id(), "cable_fid": cable.id(),
                     "cable_uuid": "own-ref"}])
    out = tmp_path / "b.gpkg"

    assert _write(project, out, [cables, slack]).ok

    assert _rows(out, 'SELECT cable_uuid FROM "Optical slack"') == [("c1",)]
    assert _extras(out, "Optical slack") == {"s1": {"cable_uuid": "own-ref"}}


@pytest.mark.parametrize("row, carried", [
    ({"geom": "g"}, {"geom": "g"}),
    ({"GEOM": "g"}, {"GEOM": "g"}),
    ({"fid": "abc"}, {"fid": "abc"}),
    ({"FID": "abc"}, {"FID": "abc"}),
    ({"FQ_TYPE": "x", "Placement": "y"}, {"FQ_TYPE": "x", "Placement": "y"}),
    ({"Owner": "A", "owner": "b"}, {"owner": "b"}),
])
def test_a_column_that_failed_the_export_is_carried_instead(project, tmp_path, row, carried):
    uri = UUID + "".join(f"&field={name}:string" for name in row)
    odf = _layer(project, uri, "ODF", [{"fiberq_uuid": "u1", **row}])
    out = tmp_path / "b.gpkg"

    result = _write(project, out, [odf])

    assert result.ok, result.errors
    assert _extras(out, "ODF") == {"u1": carried}
    assert _rows(out, 'SELECT fq_type FROM "ODF"') == [("odf",)]
    if "Owner" in row:
        assert _rows(out, 'SELECT "Owner" FROM "ODF"') == [("A",)], "the first one stays a column"


def test_an_integer_fid_column_of_the_users_is_carried_too(project, tmp_path):
    """Not the layer's row id, so the user's: on QGIS 3.40 OGR took it for the
    row id and failed the write as soon as two features had one."""
    odf = _layer(project, UUID + "&field=fid:integer", "ODF",
                 [{"fiberq_uuid": "u1", "fid": 10}, {"fiberq_uuid": "u2", "fid": 20}])
    out = tmp_path / "b.gpkg"
    result = _write(project, out, [odf])
    assert result.ok, result.errors
    assert _extras(out, "ODF") == {"u1": {"fid": 10}, "u2": {"fid": 20}}


def test_a_geopackage_layers_own_fid_is_still_the_row_id(project, tmp_path):
    """Unchanged: the layer's primary key is the bundle's row id, as it always was."""
    source = str(tmp_path / "odf.gpkg")
    stored = QgsVectorLayer(UUID, "odf", "memory")
    features = []
    for position, uuid in enumerate(("u1", "u2", "u3")):
        feature = QgsFeature(stored.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON + position * 0.001, LAT)))
        feature.setAttribute("fiberq_uuid", uuid)
        features.append(feature)
    assert stored.dataProvider().addFeatures(features)[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "odf"
    QgsVectorFileWriter.writeAsVectorFormatV3(stored, source, QgsCoordinateTransformContext(),
                                              options)
    odf = QgsVectorLayer(f"{source}|layername=odf", "ODF", "ogr")
    assert odf.isValid() and odf.dataProvider().deleteFeatures([1])
    project.addMapLayer(odf)
    out = tmp_path / "b.gpkg"

    assert _write(project, out, [odf]).ok

    assert _rows(out, 'SELECT fid, fiberq_uuid FROM "ODF" ORDER BY fid') == [(2, "u2"), (3, "u3")]
    assert _extras(out, "ODF") == {"u2": {}, "u3": {}}


def test_carried_values_join_what_an_import_kept_and_the_features_own(project, tmp_path):
    odf = _layer(project, UUID + "&field=naziv:string&field=Name:string"
                 "&field=fq_extra_json:string", "ODF",
                 [{"fiberq_uuid": "u1", "naziv": "N1", "Name": "own",
                   "fq_extra_json": json.dumps({"b": 2})},
                  {"fiberq_uuid": "u2", "naziv": "N2", "Name": "own",
                   "fq_extra_json": json.dumps({"Name": "the feature's own"})}])
    kept = [{"kind": ic.EXTENSION_KIND_ATTRIBUTES, "namespace": ic.EXTENSION_NAMESPACE,
             "owner_uuid": uuid, "payload_json": json.dumps({"a": 1, "Name": "kept"})}
            for uuid in ("u1", "u2")]
    out = tmp_path / "b.gpkg"

    result = _write(project, out, [odf], passthrough=kept)

    assert result.ok, result.errors
    # The column the user sees and edits wins over a key of its name inside
    # the feature's own fq_extra_json, and the export says how many it replaced.
    assert _extras(out, "ODF") == {
        "u1": {"a": 1, "Name": "own", "b": 2},
        "u2": {"a": 1, "Name": "own"},
    }
    assert any("1 key(s) of a feature's own fq_extra_json were replaced" in w
               for w in result.warnings), result.warnings


def test_a_carried_column_survives_an_import_and_the_next_export(project, tmp_path):
    odf = _layer(project, UUID + "&field=naziv:string&field=Name:string", "ODF",
                 [{"fiberq_uuid": "u1", "naziv": "N1", "Name": "own"}])
    first = tmp_path / "first.gpkg"
    assert _write(project, first, [odf]).ok

    fresh = QgsProject()
    fresh.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    try:
        imported = InterchangeBundleReader(fresh).read(str(first))
        assert imported.ok, imported.errors
        layers = [lyr for lyr in fresh.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
        second = tmp_path / "second.gpkg"
        assert InterchangeBundleWriter(fresh).write(str(second), layers=layers).ok
        assert _extras(second, "ODF") == {"u1": {"Name": "own"}}
    finally:
        fresh.clear()


def test_a_bundle_copy_that_cannot_be_filled_is_an_error(project, tmp_path, monkeypatch):
    """WP5-FU-6. ``addFeatures()`` answers ``(ok, features)``; the old check
    tested the tuple, which is always true, so a refused fill went on to be
    written as if it had worked."""
    from qgis.core import QgsMemoryProviderUtils

    from fiberq.core import interchange_bundle as ib

    class _RefusingProvider:
        def __init__(self, provider):
            self._provider = provider

        def __getattr__(self, name):
            return getattr(self._provider, name)

        def addFeatures(self, features, *args):
            return False, []

    class _RefusingCopy:
        """The bundle copy, except that its provider refuses every feature."""

        def __init__(self, layer):
            self._layer = layer

        def __getattr__(self, name):
            return getattr(self._layer, name)

        def dataProvider(self):
            return _RefusingProvider(self._layer.dataProvider())

    class _Copies:
        @staticmethod
        def createMemoryLayer(name, fields, wkb, crs):
            return _RefusingCopy(QgsMemoryProviderUtils.createMemoryLayer(name, fields, wkb, crs))

    poles = _layer(project, UUID, "Poles", [{"fiberq_uuid": "p1"}])
    monkeypatch.setattr(ib, "QgsMemoryProviderUtils", _Copies)

    result = _write(project, tmp_path / "b.gpkg", [poles])

    assert not result.ok
    assert any("could not fill" in error for error in result.errors), result.errors
