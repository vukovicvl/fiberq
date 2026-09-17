"""Tests for the WP3 interchange bundle writer (fiberq/core/interchange_bundle.py).

These need QGIS: the writer's job is to move real features out of a real
project. The contract they hold it to comes from docs/interchange-format.md --
above all rule 1, *preserve, don't discard*, which is the rule the exchange this
format replaces breaks in two independent ways.

Two tests here are regressions for defects found in the Phase 0 inventory:

* ``test_metadata_written_by_another_tool_survives_an_export`` -- the existing
  exporter runs ``DROP TABLE IF EXISTS _fiberq_metadata``, so exporting into a
  GeoPackage another tool also writes destroys that tool's keys. Round trip and
  nothing is left.
* ``test_an_unknown_fq_type_is_not_relabelled`` -- reclassifying an element to
  the nearest familiar type is irreversible, and is how an exchange loses data
  while reporting success.
"""
import json
import os
import sqlite3

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from fiberq.core import interchange as ic
from fiberq.core.interchange_bundle import (
    InterchangeBundleWriter,
    read_bundle_metadata,
)

# Somewhere in Serbia, in Web Mercator, so the reprojection to the storage CRS
# is a real transform rather than a no-op.
LON, LAT = 21.90, 43.32
X, Y = 2438000.0, 5360000.0


def _layer(name, geometry="Point", fields=("fiberq_uuid:string(64)", "naziv:string")):
    uri = f"{geometry}?crs=EPSG:3857&" + "&".join(f"field={f}" for f in fields)
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), name
    return layer


def _add(layer, geom, **attrs):
    """Add one feature and return it *as the provider stored it*.

    The provider assigns the feature id; it does not write it back onto the
    QgsFeature handed in, which still reports the unset sentinel. Returning the
    provider's own copy is the only way these tests see the fid that relations
    and latent elements are actually keyed by.
    """
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
    assert feat.id() > 0, "provider did not assign a feature id"
    return feat


def _point(dx=0.0, dy=0.0):
    return QgsGeometry.fromPointXY(QgsPointXY(X + dx, Y + dy))


def _line(length=100.0):
    return QgsGeometry.fromPolylineXY([QgsPointXY(X, Y), QgsPointXY(X + length, Y)])


@pytest.fixture
def project():
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    yield prj
    prj.clear()


@pytest.fixture
def bundle_path(tmp_path):
    return str(tmp_path / "design.gpkg")


def _tables(path):
    with sqlite3.connect(path) as conn:
        return {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}


def _rows(path, sql, params=()):
    with sqlite3.connect(path) as conn:
        return conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# Feature layers: canonical names, stable types, storage CRS
# ---------------------------------------------------------------------------

def test_layers_land_under_their_canonical_names(project, bundle_path):
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1", naziv="P1")
    cables = _layer("Underground cables", "LineString")
    _add(cables, _line(), fiberq_uuid="u-cable-1", naziv="C1")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[poles, cables])

    assert result.ok, result.errors
    assert set(result.layers) == {"Poles", "Underground cables"}
    assert _tables(bundle_path) >= {"Poles", "Underground cables"}


def test_a_legacy_named_layer_is_exported_under_the_canonical_name(project, bundle_path):
    """An old Serbian-named project must produce the same bundle as a new one.

    The de-facto exchange maps none of the thirteen legacy names, so a project
    made before the English rename exports as nothing at all.
    """
    stubovi = _layer("Stubovi")
    _add(stubovi, _point(), fiberq_uuid="u-legacy-1", naziv="S1")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[stubovi])

    assert result.ok, result.errors
    assert list(result.layers) == ["Poles"]
    assert _rows(bundle_path, 'SELECT fq_type FROM "Poles"') == [("pole",)]


def test_every_feature_carries_its_fq_type(project, bundle_path):
    slack = _layer("Optical slack")
    _add(slack, _point(), fiberq_uuid="u-slack-1")

    InterchangeBundleWriter(project).write(bundle_path, layers=[slack])

    assert _rows(bundle_path, 'SELECT fq_type FROM "Optical slack"') == [("slack",)]


def test_placement_travels_as_an_attribute_not_a_type(project, bundle_path):
    """Spec 6.1: an Indoor OTB is an ``otb`` mounted indoors, not its own type."""
    indoor = _layer("Indoor OTB")
    _add(indoor, _point(), fiberq_uuid="u-otb-1")

    InterchangeBundleWriter(project).write(bundle_path, layers=[indoor])

    assert _rows(bundle_path, 'SELECT fq_type, placement FROM "Indoor OTB"') == [
        ("otb", "indoor")
    ]


def test_geometry_is_stored_in_the_storage_crs(project, bundle_path):
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")

    InterchangeBundleWriter(project).write(bundle_path, layers=[poles])

    written = QgsVectorLayer(f"{bundle_path}|layername=Poles", "check", "ogr")
    assert written.isValid()
    assert written.crs().authid() == f"EPSG:{ic.STORAGE_EPSG}"
    point = next(written.getFeatures()).geometry().asPoint()
    assert point.x() == pytest.approx(LON, abs=0.01)
    assert point.y() == pytest.approx(LAT, abs=0.01)


def test_identity_is_never_regenerated(project, bundle_path):
    """Spec rule 2. A writer that reassigns identities breaks every relation."""
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="keep-me-exactly")

    InterchangeBundleWriter(project).write(bundle_path, layers=[poles])

    assert _rows(bundle_path, 'SELECT fiberq_uuid FROM "Poles"') == [("keep-me-exactly",)]


def test_a_non_fiberq_layer_is_skipped_with_a_reason(project, bundle_path):
    """Silent loss is the conformance failure; a named omission is not."""
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")
    basemap = _layer("Some survey import")

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[poles, basemap])

    assert list(result.layers) == ["Poles"]
    assert [name for name, _reason in result.skipped] == ["Some survey import"]
    assert result.skipped[0][1]


def test_a_project_with_no_fiberq_layers_is_an_error_not_an_empty_bundle(project, bundle_path):
    """An empty bundle that reports success is worse than a refusal."""
    result = InterchangeBundleWriter(project).write(bundle_path, layers=[_layer("Random")])

    assert not result.ok
    assert not os.path.exists(bundle_path)


# ---------------------------------------------------------------------------
# Rule 1: preserve, don't discard
# ---------------------------------------------------------------------------

def test_metadata_written_by_another_tool_survives_an_export(project, bundle_path):
    """Regression for the Phase 0 defect: DROP TABLE destroys foreign keys.

    A second tool writing into the same bundle records its own keys. Exporting
    again must refresh what this plugin owns and leave the rest exactly as it
    found it -- otherwise a QGIS -> other tool -> QGIS -> other tool round trip
    silently destroys that tool's data while looking successful from both ends.
    """
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")
    writer = InterchangeBundleWriter(project)
    writer.write(bundle_path, layers=[poles])

    with sqlite3.connect(bundle_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO _fiberq_metadata (key, value) VALUES (?, ?)",
            ("other_tool_state", '{"trays": 12}'),
        )

    result = writer.write(bundle_path, layers=[poles])

    after = read_bundle_metadata(bundle_path)
    assert after.get("other_tool_state") == '{"trays": 12}'
    assert result.preserved == {"other_tool_state": '{"trays": 12}'}


def test_required_metadata_keys_are_all_written(project, bundle_path):
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")

    InterchangeBundleWriter(project, plugin_version="9.9.9").write(
        bundle_path, layers=[poles])

    meta = read_bundle_metadata(bundle_path)
    for key in ("format", "format_version", "schema_version", "produced_by",
                "produced_at", "crs_epsg", "color_standard"):
        assert meta.get(key), f"missing required metadata key {key}"
    assert meta["format"] == ic.FORMAT
    assert meta["crs_epsg"] == "3857"
    assert "9.9.9" in meta["produced_by"]
    assert meta["schema_version"] != meta["produced_by"]


def test_an_unknown_fq_type_is_not_relabelled(project, bundle_path):
    """Spec 6.1: a reader must never reclassify a type it does not recognise.

    A feature that arrived from a tool modelling something this plugin does not
    keeps the type it came with. Overwriting the whole column with the layer's
    own type is exactly the irreversible loss the rule forbids.
    """
    poles = _layer("Poles", fields=("fiberq_uuid:string(64)", "fq_type:string"))
    _add(poles, _point(), fiberq_uuid="u-known", fq_type=None)
    _add(poles, _point(10), fiberq_uuid="u-exotic", fq_type="micro_duct_vault")

    InterchangeBundleWriter(project).write(bundle_path, layers=[poles])

    got = dict(_rows(bundle_path, 'SELECT fiberq_uuid, fq_type FROM "Poles"'))
    assert got["u-exotic"] == "micro_duct_vault"
    assert got["u-known"] == "pole"


def test_the_passthrough_store_is_written_back_verbatim(project, bundle_path):
    """Spec section 8: whatever an import could not model leaves again unchanged."""
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")
    carried = [{
        "uuid": "ext-1", "owner_uuid": "u-pole-1", "kind": "splice_tray",
        "namespace": "example.tool", "payload_json": '{"trays": 3}',
        "produced_by": "Example Tool 2.0",
    }]

    result = InterchangeBundleWriter(project).write(
        bundle_path, layers=[poles], passthrough=carried)

    assert result.sidecar_rows["fq_extension"] == 1
    assert _rows(
        bundle_path,
        "SELECT owner_uuid, kind, namespace, payload_json FROM fq_extension"
    ) == [("u-pole-1", "splice_tray", "example.tool", '{"trays": 3}')]


def test_the_passthrough_store_is_read_from_the_project_when_not_given(project, bundle_path):
    """Import and export must agree on one key, or the store is lost between them."""
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")
    project.writeEntry(*ic.PASSTHROUGH_ENTRY, json.dumps([{
        "uuid": "ext-9", "owner_uuid": "u-pole-1", "kind": "whatever",
        "namespace": "ns", "payload_json": "{}", "produced_by": "t",
    }]))

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[poles])

    assert result.sidecar_rows["fq_extension"] == 1


# ---------------------------------------------------------------------------
# Side-car: local ids become identities
# ---------------------------------------------------------------------------

def test_every_sidecar_table_is_created(project, bundle_path):
    """A reader should find the tables whether or not this project fills them."""
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")

    InterchangeBundleWriter(project).write(bundle_path, layers=[poles])

    tables = _tables(bundle_path)
    for name in ("fq_splice_point", "fq_fiber_connection", "fq_relation",
                 "fq_relation_member", "fq_container", "fq_container_slot",
                 "fq_slot_assignment", "fq_path_stop", "fq_extension"):
        assert name in tables, f"side-car table {name} missing from the bundle"


def test_relations_are_exported_keyed_by_uuid_not_by_feature_id(project, bundle_path):
    """The plugin stores relations against (layer_id, fid), which is local to one
    QGIS project and means nothing after a round trip. The bundle must carry
    identities instead."""
    cables = _layer("Underground cables", "LineString")
    first = _add(cables, _line(), fiberq_uuid="u-cable-1", naziv="C1")
    second = _add(cables, _line(200), fiberq_uuid="u-cable-2", naziv="C2")
    project.writeEntry("StuboviPlugin", "Relacije/relations_v1", json.dumps({
        "relations": [{
            "id": 1, "name": "Feeder A",
            "cables": [
                {"layer_id": cables.id(), "fid": first.id()},
                {"layer_id": cables.id(), "fid": second.id()},
            ],
        }]
    }))

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[cables])

    assert result.sidecar_rows["fq_relation"] == 1
    assert result.sidecar_rows["fq_relation_member"] == 2
    (name,) = _rows(bundle_path, "SELECT name FROM fq_relation")[0]
    assert name == "Feeder A"
    members = _rows(
        bundle_path,
        "SELECT member_uuid, order_index, role FROM fq_relation_member ORDER BY order_index")
    assert members == [("u-cable-1", 0, "cable"), ("u-cable-2", 1, "cable")]


def test_a_relation_uuid_is_stable_across_repeated_exports(project, bundle_path, tmp_path):
    """Minting a new identity each export makes every bundle look like a new
    network, which defeats the diffing the format exists to allow."""
    cables = _layer("Underground cables", "LineString")
    feat = _add(cables, _line(), fiberq_uuid="u-cable-1")
    project.setFileName(str(tmp_path / "p.qgz"))
    project.writeEntry("StuboviPlugin", "Relacije/relations_v1", json.dumps({
        "relations": [{"id": 1, "name": "Feeder A",
                       "cables": [{"layer_id": cables.id(), "fid": feat.id()}]}]
    }))
    writer = InterchangeBundleWriter(project)

    writer.write(bundle_path, layers=[cables])
    first = _rows(bundle_path, "SELECT uuid FROM fq_relation")
    second_path = str(tmp_path / "again.gpkg")
    writer.write(second_path, layers=[cables])

    assert first == _rows(second_path, "SELECT uuid FROM fq_relation")


def test_an_unresolvable_relation_member_is_reported_not_guessed(project, bundle_path):
    """A reference to a deleted cable must not become a reference to some other
    cable, and must not disappear without a word."""
    cables = _layer("Underground cables", "LineString")
    _add(cables, _line(), fiberq_uuid="u-cable-1")
    project.writeEntry("StuboviPlugin", "Relacije/relations_v1", json.dumps({
        "relations": [{"id": 1, "name": "Feeder A",
                       "cables": [{"layer_id": cables.id(), "fid": 9999}]}]
    }))

    result = InterchangeBundleWriter(project).write(bundle_path, layers=[cables])

    assert result.sidecar_rows["fq_relation_member"] == 0
    assert any("could not be resolved" in w for w in result.warnings)


def test_path_stops_are_ordered_along_the_cable(project, bundle_path):
    """fq_path_stop is an *ordered* traversal; the order is the whole point."""
    cables = _layer("Underground cables", "LineString")
    cable = _add(cables, _line(), fiberq_uuid="u-cable-1")
    manholes = _layer("Manholes")
    near = _add(manholes, _point(10), fiberq_uuid="u-mh-near")
    far = _add(manholes, _point(60), fiberq_uuid="u-mh-far")
    project.writeEntry("StuboviPlugin", "LatentElements/latent_v1", json.dumps({
        "cables": {
            f"{cables.id()}:{cable.id()}": [
                {"layer_id": manholes.id(), "fid": far.id(), "m": 60.0},
                {"layer_id": manholes.id(), "fid": near.id(), "m": 10.0},
            ]
        }
    }))

    result = InterchangeBundleWriter(project).write(
        bundle_path, layers=[cables, manholes])

    assert result.sidecar_rows["fq_path_stop"] == 2
    assert _rows(
        bundle_path,
        "SELECT element_uuid, order_index, is_latent FROM fq_path_stop ORDER BY order_index"
    ) == [("u-mh-near", 0, 1), ("u-mh-far", 1, 1)]


def test_the_bundle_does_not_redirect_the_project_layers(project, bundle_path):
    """A bundle is an export artefact. save_all_layers_to_gpkg repoints the
    project at the file it wrote; this must not, or exporting would quietly
    move where the user's project lives."""
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")
    before = poles.source()

    InterchangeBundleWriter(project).write(bundle_path, layers=[poles])

    assert poles.source() == before
    assert poles.providerType() == "memory"


# ---------------------------------------------------------------------------
# Canonical names and values (spec rule 3 — the format is the contract)
# ---------------------------------------------------------------------------

def test_stored_field_names_become_canonical_in_the_bundle(project, bundle_path):
    """A bundle carrying `duzina_m` would be FiberQ's schema in a GeoPackage,
    not a tool-neutral format: every other tool would have to learn Serbian."""
    cables = _layer(
        "Underground cables", "LineString",
        fields=("fiberq_uuid:string(64)", "naziv:string", "duzina_m:double",
                "slabljenje_dbkm:double"))
    _add(cables, _line(), fiberq_uuid="u-cable-1", naziv="C1",
         duzina_m=120.0, slabljenje_dbkm=0.22)

    InterchangeBundleWriter(project).write(bundle_path, layers=[cables])

    written = QgsVectorLayer(
        f"{bundle_path}|layername=Underground cables", "check", "ogr")
    names = set(written.fields().names())
    assert {"name", "length_m", "attenuation_db_km"} <= names
    assert not {"naziv", "duzina_m", "slabljenje_dbkm"} & names
    assert _rows(
        bundle_path,
        'SELECT name, length_m, attenuation_db_km FROM "Underground cables"'
    ) == [("C1", 120.0, 0.22)]


def test_the_projects_own_field_names_are_left_alone(project, bundle_path):
    """Renaming happens on the copy in the bundle. Touching the project's own
    schema would be a data migration, not an export."""
    cables = _layer("Underground cables", "LineString",
                    fields=("fiberq_uuid:string(64)", "naziv:string", "duzina_m:double"))
    _add(cables, _line(), fiberq_uuid="u-cable-1", naziv="C1", duzina_m=10.0)
    before = cables.fields().names()

    InterchangeBundleWriter(project).write(bundle_path, layers=[cables])

    assert cables.fields().names() == before


def test_the_project_is_byte_for_byte_unchanged_by_an_export(project, bundle_path):
    """An export must read the project and write somewhere else. Nothing more.

    The field-name test above covers the schema; this covers the *values*, which
    is the half a user would not notice until much later. Both spellings the
    plugin stores are present here on purpose -- the canonical vocabulary is
    something a bundle carries, never something an export imposes on the
    project it was run on.
    """
    cables = _layer("Underground cables", "LineString",
                    fields=("fiberq_uuid:string(64)", "naziv:string",
                            "duzina_m:double", "tip:string", "stanje_kabla:string"))
    _add(cables, _line(), fiberq_uuid="u-a", naziv="C1", duzina_m=8.613,
         tip="opticki", stanje_kabla="Projektovano")
    _add(cables, _line(50), fiberq_uuid="u-b", naziv="C2", duzina_m=4.0,
         tip="Optical", stanje_kabla="Planned")
    routes = _layer("Route", "LineString",
                    fields=("fiberq_uuid:string(64)", "tip_trase:string"))
    _add(routes, _line(), fiberq_uuid="u-r", tip_trase="vazdusna")

    def snapshot(layer):
        return [
            (f.attributes(), f.geometry().asWkt())
            for f in sorted(layer.getFeatures(), key=lambda x: x.id())
        ]

    before = {lyr.name(): snapshot(lyr) for lyr in (cables, routes)}

    result = InterchangeBundleWriter(project).write(
        bundle_path, layers=[cables, routes])

    assert result.ok, result.errors
    for lyr in (cables, routes):
        assert snapshot(lyr) == before[lyr.name()], (
            f"{lyr.name()}: the export changed the project's own data")
    # And the bundle did get the canonical form, from both spellings.
    assert dict(_rows(
        bundle_path, 'SELECT fiberq_uuid, cable_type FROM "Underground cables"')
    ) == {"u-a": "optical", "u-b": "optical"}
    assert _rows(bundle_path, 'SELECT route_type FROM "Route"') == [("aerial",)]


def test_stored_values_are_translated_to_the_canonical_vocabulary(project, bundle_path):
    """`vazdusna` means aerial. A reader should not have to know that."""
    routes = _layer("Route", "LineString",
                    fields=("fiberq_uuid:string(64)", "tip_trase:string"))
    _add(routes, _line(), fiberq_uuid="u-route-1", tip_trase="vazdusna")

    InterchangeBundleWriter(project).write(bundle_path, layers=[routes])

    assert _rows(bundle_path, 'SELECT route_type FROM "Route"') == [("aerial",)]


def test_both_as_built_spellings_reach_the_same_canonical_value(project, bundle_path):
    """FiberQ projects hold the English label on some features and the stored
    Serbian value on others (validation rule D1). Both are as-built."""
    cables = _layer("Aerial cables", "LineString",
                    fields=("fiberq_uuid:string(64)", "tip:string"))
    _add(cables, _line(), fiberq_uuid="u-a", tip="opticki")
    _add(cables, _line(50), fiberq_uuid="u-b", tip="Optical")

    InterchangeBundleWriter(project).write(bundle_path, layers=[cables])

    got = dict(_rows(bundle_path, 'SELECT fiberq_uuid, cable_type FROM "Aerial cables"'))
    assert got == {"u-a": "optical", "u-b": "optical"}


def test_a_value_outside_the_domain_is_carried_through(project, bundle_path):
    """Rule 1 again: tidying a vocabulary is not worth discarding the data."""
    cables = _layer("Aerial cables", "LineString",
                    fields=("fiberq_uuid:string(64)", "tip:string"))
    _add(cables, _line(), fiberq_uuid="u-a", tip="hybrid coax")

    InterchangeBundleWriter(project).write(bundle_path, layers=[cables])

    assert _rows(bundle_path, 'SELECT cable_type FROM "Aerial cables"') == [("hybrid coax",)]


def test_a_local_cable_reference_becomes_a_uuid(project, bundle_path):
    """The plugin records which cable a slack loop belongs to as a QGIS layer id
    plus a feature id. Neither means anything in another tool, or in the same
    project after a rebuild. The bundle carries the identity instead."""
    cables = _layer("Underground cables", "LineString")
    cable = _add(cables, _line(), fiberq_uuid="u-cable-1")
    slack = _layer(
        "Optical slack",
        fields=("fiberq_uuid:string(64)", "duzina_m:double",
                "cable_layer_id:string", "cable_fid:integer"))
    _add(slack, _point(20), fiberq_uuid="u-slack-1", duzina_m=15.0,
         cable_layer_id=cables.id(), cable_fid=cable.id())

    result = InterchangeBundleWriter(project).write(
        bundle_path, layers=[cables, slack])

    assert result.ok, result.errors
    written = QgsVectorLayer(f"{bundle_path}|layername=Optical slack", "check", "ogr")
    names = set(written.fields().names())
    assert "cable_uuid" in names
    assert not {"cable_layer_id", "cable_fid"} & names
    assert _rows(bundle_path, 'SELECT cable_uuid, length_m FROM "Optical slack"') == [
        ("u-cable-1", 15.0)
    ]


def test_an_unresolvable_cable_reference_is_reported_not_guessed(project, bundle_path):
    """A slack loop pointing at a deleted cable must not acquire a different one."""
    cables = _layer("Underground cables", "LineString")
    _add(cables, _line(), fiberq_uuid="u-cable-1")
    slack = _layer("Optical slack",
                   fields=("fiberq_uuid:string(64)", "cable_layer_id:string",
                           "cable_fid:integer"))
    _add(slack, _point(20), fiberq_uuid="u-slack-1",
         cable_layer_id=cables.id(), cable_fid=4242)

    result = InterchangeBundleWriter(project).write(
        bundle_path, layers=[cables, slack])

    assert _rows(bundle_path, 'SELECT cable_uuid FROM "Optical slack"') == [(None,)]
    assert any("could not be resolved" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# The GeoJSON profile (spec section 3) — useful, and honest about being lossy
# ---------------------------------------------------------------------------

def test_the_geojson_profile_writes_one_file_per_element_type(project, tmp_path):
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1", naziv="P1")
    indoor = _layer("Indoor OTB")
    _add(indoor, _point(5), fiberq_uuid="u-otb-1")
    out = str(tmp_path / "bundle")

    result = InterchangeBundleWriter(project).write_geojson(
        out, layers=[poles, indoor])

    assert result.ok, result.errors
    written = sorted(os.listdir(out))
    assert written == ["_fiberq_metadata.json", "otb.indoor.geojson", "pole.geojson"]


def test_the_geojson_profile_carries_canonical_names_and_types(project, tmp_path):
    """The two profiles come from one canonicalisation, so they cannot disagree
    about what a field is called."""
    cables = _layer("Underground cables", "LineString",
                    fields=("fiberq_uuid:string(64)", "naziv:string",
                            "duzina_m:double", "tip:string"))
    _add(cables, _line(), fiberq_uuid="u-cable-1", naziv="C1", duzina_m=42.0,
         tip="opticki")
    out = str(tmp_path / "bundle")

    InterchangeBundleWriter(project).write_geojson(out, layers=[cables])

    with open(os.path.join(out, "cable.underground.geojson"), encoding="utf-8") as fh:
        payload = json.load(fh)
    props = payload["features"][0]["properties"]
    assert props["name"] == "C1"
    assert props["length_m"] == 42.0
    assert props["cable_type"] == "optical"
    assert props["fq_type"] == "cable.underground"
    assert props["fiberq_uuid"] == "u-cable-1"
    assert "duzina_m" not in props


def test_the_geojson_metadata_file_carries_the_required_keys(project, tmp_path):
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")
    out = str(tmp_path / "bundle")

    InterchangeBundleWriter(project, plugin_version="9.9.9").write_geojson(
        out, layers=[poles])

    with open(os.path.join(out, "_fiberq_metadata.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    for key in ("format", "format_version", "schema_version", "produced_by",
                "produced_at", "crs_epsg", "color_standard"):
        assert meta.get(key), key


def test_a_geojson_bundle_that_drops_side_car_data_says_so(project, tmp_path):
    """Spec section 3: lossy by construction, and the reader must be able to
    tell. A bundle that lost the splice data and looks complete is worse than
    one that refuses."""
    cables = _layer("Underground cables", "LineString")
    cable = _add(cables, _line(), fiberq_uuid="u-cable-1")
    project.writeEntry("StuboviPlugin", "Relacije/relations_v1", json.dumps({
        "relations": [{"id": 1, "name": "Feeder A",
                       "cables": [{"layer_id": cables.id(), "fid": cable.id()}]}]
    }))
    out = str(tmp_path / "bundle")

    result = InterchangeBundleWriter(project).write_geojson(out, layers=[cables])

    with open(os.path.join(out, "_fiberq_metadata.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["profile"] == "geojson-lite"
    assert any("side-car" in w for w in result.warnings)


def test_a_geojson_bundle_with_nothing_to_drop_is_not_marked_lossy(project, tmp_path):
    """Marking a complete bundle lossy is as misleading as not marking a lossy one."""
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")
    out = str(tmp_path / "bundle")

    InterchangeBundleWriter(project).write_geojson(out, layers=[poles])

    with open(os.path.join(out, "_fiberq_metadata.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    assert "profile" not in meta


def test_the_geojson_profile_leaves_no_staging_file_behind(project, tmp_path):
    """It is produced by staging a GeoPackage; that must not survive."""
    poles = _layer("Poles")
    _add(poles, _point(), fiberq_uuid="u-pole-1")
    out = str(tmp_path / "bundle")

    InterchangeBundleWriter(project).write_geojson(out, layers=[poles])

    assert not [n for n in os.listdir(out) if n.endswith(".gpkg")]
