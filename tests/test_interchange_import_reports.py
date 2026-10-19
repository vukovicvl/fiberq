"""What an import cannot keep it now says, instead of leaving it out without a word.

Unclaimed (WP3 code), found in the v1.6.0 review. Before FiberQ 1.6.0 an import
dropped, with nothing but a debug line:

- an ``fq_extra_json`` that is not a JSON object -- not JSON at all, or a list
  -- so there are no attributes in it to keep;
- the attributes FiberQ has no column for on a feature with no ``fiberq_uuid``,
  since they are kept against a feature's identity;
- a relation member row naming no relation of the bundle, or one with no uuid.

Each is now counted into a warning. Bundles are changed as another tool would,
through SQLite.
"""
import sqlite3
from contextlib import closing

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer)

from fiberq.core.interchange_bundle import InterchangeBundleWriter
from fiberq.core.interchange_import import InterchangeBundleReader

LON, LAT = 21.90, 43.32


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    yield prj
    prj.clear()


def _bundle(path, fields=("fiberq_uuid:string(64)",), values=None):
    source = QgsProject()
    source.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    poles = QgsVectorLayer("Point?crs=EPSG:4326&" + "&".join(f"field={f}" for f in fields),
                           "Poles", "memory")
    feature = QgsFeature(poles.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    for key, value in (values or {"fiberq_uuid": "p1"}).items():
        feature.setAttribute(key, value)
    assert poles.dataProvider().addFeatures([feature])[0]
    source.addMapLayer(poles)
    assert InterchangeBundleWriter(source).write(str(path), layers=[poles]).ok
    source.clear()
    return str(path)


def _sql(path, sql, params=()):
    """As another tool would: GDAL's R-tree triggers name spatial functions plain
    sqlite3 lacks, so they are stood in for; no geometry is touched."""
    with closing(sqlite3.connect(path)) as conn:
        conn.create_function("ST_IsEmpty", 1, lambda geom: 0)
        for name in ("ST_MinX", "ST_MaxX", "ST_MinY", "ST_MaxY"):
            conn.create_function(name, 1, lambda geom: 0.0)
        conn.execute(sql, params)
        conn.commit()


def _import(project, path):
    result = InterchangeBundleReader(project).read(path)
    assert result.ok, result.errors
    return result


@pytest.mark.parametrize("text", ["[1, 2]", "{not json", '"just text"'])
def test_an_fq_extra_json_that_is_not_an_object_is_reported(project, tmp_path, text):
    bundle = _bundle(tmp_path / "b.gpkg")
    _sql(bundle, 'UPDATE "Poles" SET fq_extra_json = ?', (text,))
    result = _import(project, bundle)
    assert any("not a JSON object" in w for w in result.warnings), result.warnings


def test_extras_on_a_feature_with_no_identity_are_reported(project, tmp_path):
    bundle = _bundle(tmp_path / "b.gpkg", ("fiberq_uuid:string(64)", "owner:string"),
                     {"fiberq_uuid": "p1", "owner": "ACME"})
    _sql(bundle, 'UPDATE "Poles" SET fiberq_uuid = NULL')
    result = _import(project, bundle)
    assert any("no fiberq_uuid" in w for w in result.warnings), result.warnings


def test_relation_members_naming_no_relation_are_reported(project, tmp_path):
    bundle = _bundle(tmp_path / "b.gpkg")
    # A relation with no uuid can be named by no member (relation_uuid is NOT
    # NULL), so its members, if a tool meant it to have any, are among these.
    _sql(bundle, "INSERT INTO fq_relation (uuid, name) VALUES (NULL, 'unnamed')")
    for relation in ("r-nowhere", "r-gone"):
        _sql(bundle, "INSERT INTO fq_relation_member (relation_uuid, member_uuid, order_index) "
                     "VALUES (?, 'p1', 0)", (relation,))
    result = _import(project, bundle)
    assert any("2 relation member row(s) name no relation" in w for w in result.warnings), (
        result.warnings)


def test_a_clean_bundle_reports_none_of_this(project, tmp_path):
    result = _import(project, _bundle(tmp_path / "b.gpkg"))
    for phrase in ("not a JSON object", "no fiberq_uuid", "name no relation"):
        assert not any(phrase in w for w in result.warnings), result.warnings
