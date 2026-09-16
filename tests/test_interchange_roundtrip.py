"""The WP3 round-trip test: import a bundle, export it, lose nothing.

This is the test the interchange format exists to pass, and the one the build
plan names as the deliverable of task 3.3. Everything else in WP3 is machinery
for it.

The bundle it round-trips is deliberately **richer than the plugin**. It carries
an element type FiberQ has no layer for, an attribute FiberQ has no column for,
fibre-splice side-car tables FiberQ does not model at all, a passthrough row from
a third tool, and a metadata key FiberQ did not write. None of that is
hypothetical: the plugin and the tools it exchanges with are at different feature
levels, and staying lossless while that is true is the whole point.

If the plugin later gains real support for any of it, the mapping is upgraded and
those objects start importing properly -- and bundles written today still work,
because nothing was ever discarded.
"""
import json
import sqlite3

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
    QgsVectorLayer,
)

from fiberq.core import interchange as ic
from fiberq.core.interchange_bundle import InterchangeBundleWriter, read_bundle_metadata
from fiberq.core.interchange_import import InterchangeBundleReader

LON, LAT = 21.90, 43.32
X, Y = 2438000.0, 5360000.0

#: What the exporting tool knew and FiberQ does not.
FOREIGN_TYPE = "splitter"
FOREIGN_ATTRIBUTE = "owner_ref"
FOREIGN_METADATA = ("other_tool_state", '{"trays": 12}')

SPLICE_ROW = {
    "uuid": "sp-1", "element_uuid": "u-closure-1", "port_count": 24,
    "used_ports": 6, "config_json": '{"tray": 1}', "notes": "kept verbatim",
}
CONNECTION_ROW = {
    "uuid": "fc-1", "source_cable_uuid": "u-cable-1", "source_tube": 1,
    "source_fiber": 7, "dest_cable_uuid": "u-cable-1", "dest_tube": 2,
    "dest_fiber": 3, "connection_type": "fusion", "loss_db": 0.05,
}
THIRD_PARTY_EXTENSION = {
    "uuid": "ext-third", "owner_uuid": "u-cable-1", "kind": "route_plan",
    "namespace": "example.other", "payload_json": '{"approved": true}',
    "produced_by": "Another Tool 3.1",
}


# ---------------------------------------------------------------------------
# Building a bundle richer than the plugin
# ---------------------------------------------------------------------------

def _memory_layer(name, geometry, fields):
    uri = f"{geometry}?crs=EPSG:3857&" + "&".join(f"field={f}" for f in fields)
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


def _point(dx=0.0, dy=0.0):
    return QgsGeometry.fromPointXY(QgsPointXY(X + dx, Y + dy))


def _line(length=100.0):
    return QgsGeometry.fromPolylineXY([QgsPointXY(X, Y), QgsPointXY(X + length, Y)])


def _rows(path, sql):
    with sqlite3.connect(path) as conn:
        return conn.execute(sql).fetchall()


def _tables(path):
    with sqlite3.connect(path) as conn:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}


@pytest.fixture
def source_project():
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    yield prj
    prj.clear()


@pytest.fixture
def target_project():
    prj = QgsProject()
    yield prj
    prj.clear()


@pytest.fixture
def foreign_bundle(source_project, tmp_path):
    """A bundle carrying more than this plugin models.

    Built by exporting a normal FiberQ project and then adding what a
    better-equipped tool would have written, which is exactly the shape of the
    bundles this format has to survive.
    """
    path = str(tmp_path / "foreign.gpkg")

    cables = _memory_layer("Underground cables", "LineString",
                           ("fiberq_uuid:string(64)", "naziv:string",
                            "duzina_m:double", "tip:string"))
    cable = _add(cables, _line(), fiberq_uuid="u-cable-1", naziv="Feeder A",
                 duzina_m=120.0, tip="opticki")
    closures = _memory_layer("Joint Closures", "Point",
                             ("fiberq_uuid:string(64)", "naziv:string"))
    _add(closures, _point(10), fiberq_uuid="u-closure-1", naziv="JC-1")
    manholes = _memory_layer("Manholes", "Point",
                             ("fiberq_uuid:string(64)", "broj_okna:string"))
    manhole = _add(manholes, _point(40), fiberq_uuid="u-mh-1", broj_okna="MH 1")
    slack = _memory_layer("Optical slack", "Point",
                          ("fiberq_uuid:string(64)", "duzina_m:double",
                           "lokacija:string", "cable_layer_id:string",
                           "cable_fid:integer"))
    _add(slack, _point(45), fiberq_uuid="u-slack-1", duzina_m=15.0,
         lokacija="OKNO", cable_layer_id=cables.id(), cable_fid=cable.id())

    source_project.writeEntry("StuboviPlugin", "Relacije/relations_v1", json.dumps({
        "relations": [{"id": 1, "name": "Feeder A",
                       "cables": [{"layer_id": cables.id(), "fid": cable.id()}]}]
    }))
    source_project.writeEntry("StuboviPlugin", "LatentElements/latent_v1", json.dumps({
        "cables": {f"{cables.id()}:{cable.id()}": [
            {"layer_id": manholes.id(), "fid": manhole.id(), "m": 40.0}]}
    }))

    result = InterchangeBundleWriter(source_project).write(
        path, layers=[cables, closures, manholes, slack])
    assert result.ok, result.errors

    _add_foreign_layer(path)
    _add_foreign_attribute(path)
    with sqlite3.connect(path) as conn:
        _insert(conn, "fq_splice_point", SPLICE_ROW)
        _insert(conn, "fq_fiber_connection", CONNECTION_ROW)
        _insert(conn, "fq_extension", THIRD_PARTY_EXTENSION)
        conn.execute(
            "INSERT OR REPLACE INTO _fiberq_metadata (key, value) VALUES (?, ?)",
            FOREIGN_METADATA)
    return path


def _insert(conn, table, row):
    columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    used = [c for c in columns if c in row]
    conn.execute(
        f'INSERT OR REPLACE INTO "{table}" ({", ".join(used)}) '
        f'VALUES ({", ".join("?" for _ in used)})',
        [row[c] for c in used])


def _add_foreign_layer(path):
    """A whole element type this plugin has no layer for."""
    layer = _memory_layer("Splitters", "Point",
                          ("fiberq_uuid:string(64)", "fq_type:string",
                           "name:string", "split_ratio:string"))
    _add(layer, QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)),
         fiberq_uuid="u-splitter-1", fq_type=FOREIGN_TYPE, name="SPL-1",
         split_ratio="1:16")
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = "Splitters"
    opts.destCRS = QgsCoordinateReferenceSystem.fromEpsgId(4326)
    opts.actionOnExistingFile = (
        QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer)
    code = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, path, QgsCoordinateTransformContext(), opts)
    assert (code[0] if isinstance(code, tuple) else code) == \
        QgsVectorFileWriter.WriterError.NoError


def _add_foreign_attribute(path):
    """An attribute on a known element that this plugin has no column for."""
    layer = QgsVectorLayer(f"{path}|layername=Joint Closures", "jc", "ogr")
    assert layer.isValid()
    from qgis.PyQt.QtCore import QVariant
    from qgis.core import QgsField
    assert layer.dataProvider().addAttributes([QgsField(FOREIGN_ATTRIBUTE, QVariant.String)])
    layer.updateFields()
    idx = layer.fields().indexFromName(FOREIGN_ATTRIBUTE)
    changes = {f.id(): {idx: "asset-4417"} for f in layer.getFeatures()}
    assert layer.dataProvider().changeAttributeValues(changes)


# ---------------------------------------------------------------------------
# The round trip
# ---------------------------------------------------------------------------

@pytest.fixture
def round_tripped(foreign_bundle, target_project, tmp_path):
    """import(foreign) -> export(again), with both results."""
    imported = InterchangeBundleReader(target_project).read(foreign_bundle)
    assert imported.ok, imported.errors
    again = str(tmp_path / "again.gpkg")
    exported = InterchangeBundleWriter(target_project).write(again)
    assert exported.ok, exported.errors
    return imported, exported, again


def test_the_import_itself_succeeds_and_creates_the_layers(foreign_bundle, target_project):
    result = InterchangeBundleReader(target_project).read(foreign_bundle)

    assert result.ok, result.errors
    assert set(result.layers) == {
        "Underground cables", "Joint Closures", "Manholes", "Optical slack"}
    assert result.feature_count == 4


def test_the_authoring_crs_is_restored(foreign_bundle, target_project):
    """Spec section 5: storage is 4326, but the user gets their CRS back."""
    assert not target_project.crs().isValid() or target_project.crs().authid() != "EPSG:3857"

    InterchangeBundleReader(target_project).read(foreign_bundle)

    assert target_project.crs().authid() == "EPSG:3857"


def test_identities_survive_the_round_trip(round_tripped):
    """Rule 2. Without this nothing else here can even be checked."""
    _imported, _exported, again = round_tripped
    assert _rows(again, 'SELECT fiberq_uuid FROM "Underground cables"') == [("u-cable-1",)]
    assert _rows(again, 'SELECT fiberq_uuid FROM "Manholes"') == [("u-mh-1",)]


def test_canonical_attributes_and_values_survive(round_tripped):
    """Serbian on the way in, canonical in the bundle, Serbian in the project,
    canonical again on the way out -- and the same value at both ends."""
    _imported, _exported, again = round_tripped
    assert _rows(
        again,
        'SELECT name, length_m, cable_type FROM "Underground cables"'
    ) == [("Feeder A", 120.0, "optical")]
    assert _rows(again, 'SELECT manhole_id FROM "Manholes"') == [("MH 1",)]


def test_an_element_type_the_plugin_lacks_survives(round_tripped):
    """The heart of it. A splitter has no FiberQ layer, and must still come out
    the other side -- never reclassified to the nearest familiar type."""
    imported, _exported, again = round_tripped
    assert imported.unsupported == {FOREIGN_TYPE: 1}

    kept = _rows(
        again,
        "SELECT owner_uuid, payload_json FROM fq_extension "
        f"WHERE kind = '{ic.EXTENSION_KIND_FEATURE}'")
    assert len(kept) == 1
    owner, payload = kept[0]
    assert owner == "u-splitter-1"
    body = json.loads(payload)
    assert body["fq_type"] == FOREIGN_TYPE
    assert body["attributes"]["split_ratio"] == "1:16"
    assert body["geometry_wkt"]


def test_the_splitter_is_not_quietly_filed_as_something_else(round_tripped):
    """Reclassifying is irreversible and the import would look like it worked."""
    _imported, _exported, again = round_tripped
    for table in ("Poles", "Manholes", "Joint Closures"):
        if table not in _tables(again):
            continue
        assert "u-splitter-1" not in [
            r[0] for r in _rows(again, f'SELECT fiberq_uuid FROM "{table}"')]


def test_an_attribute_the_plugin_has_no_column_for_survives(round_tripped):
    """Carried against the feature's identity and re-emitted into its own
    fq_extra_json, rather than dropped because there was nowhere to put it."""
    imported, _exported, again = round_tripped
    assert imported.extra_attributes == 1

    rows = _rows(again, 'SELECT fiberq_uuid, fq_extra_json FROM "Joint Closures"')
    assert len(rows) == 1
    identity, extra = rows[0]
    assert identity == "u-closure-1"
    assert json.loads(extra)[FOREIGN_ATTRIBUTE] == "asset-4417"


def test_side_car_tables_the_plugin_does_not_model_survive_as_rows(round_tripped):
    """Fibre splicing is the data this format exists to carry and the plugin
    does not hold. It must arrive still relational, not as a blob describing a
    table -- a tool that does model splicing has to be able to query it."""
    imported, _exported, again = round_tripped
    assert imported.sidecar_kept.get("fq_splice_point") == 1
    assert imported.sidecar_kept.get("fq_fiber_connection") == 1

    assert _rows(
        again,
        "SELECT uuid, element_uuid, port_count, notes FROM fq_splice_point"
    ) == [("sp-1", "u-closure-1", 24, "kept verbatim")]
    assert _rows(
        again,
        "SELECT uuid, source_tube, source_fiber, dest_fiber, connection_type, loss_db "
        "FROM fq_fiber_connection"
    ) == [("fc-1", 1, 7, 3, "fusion", 0.05)]


def test_a_third_tools_passthrough_row_survives_untouched(round_tripped):
    """Rule 1 applies to what another tool could not model either."""
    _imported, _exported, again = round_tripped
    assert _rows(
        again,
        "SELECT owner_uuid, kind, namespace, payload_json, produced_by "
        "FROM fq_extension WHERE uuid = 'ext-third'"
    ) == [(
        THIRD_PARTY_EXTENSION["owner_uuid"], THIRD_PARTY_EXTENSION["kind"],
        THIRD_PARTY_EXTENSION["namespace"], THIRD_PARTY_EXTENSION["payload_json"],
        THIRD_PARTY_EXTENSION["produced_by"],
    )]


def test_metadata_another_tool_wrote_reaches_the_next_bundle(round_tripped):
    """Section 7 says do not delete another tool's keys. Across a round trip
    that means carrying them through the project, because the second bundle is
    a different file and has never seen them."""
    imported, exported, again = round_tripped
    key, value = FOREIGN_METADATA
    assert imported.foreign_metadata.get(key) == value
    assert read_bundle_metadata(again).get(key) == value
    assert exported.preserved.get(key) == value


def test_relations_survive_as_relations(round_tripped):
    """Not as a blob: they go out uuid-keyed, come back as project relations,
    and go out uuid-keyed again."""
    imported, _exported, again = round_tripped
    assert imported.relations == 1
    assert _rows(again, "SELECT name FROM fq_relation") == [("Feeder A",)]
    assert _rows(again, "SELECT member_uuid FROM fq_relation_member") == [("u-cable-1",)]


def test_path_stops_survive(round_tripped):
    imported, _exported, again = round_tripped
    assert imported.path_stops == 1
    assert _rows(
        again, "SELECT cable_uuid, element_uuid FROM fq_path_stop"
    ) == [("u-cable-1", "u-mh-1")]


def test_a_cable_reference_survives_as_a_reference(round_tripped):
    """The slack loop points at a cable through a project-local pair here and a
    uuid in the bundle. Both ends of that conversion have to work or the loop
    silently detaches."""
    _imported, _exported, again = round_tripped
    assert _rows(
        again, 'SELECT cable_uuid, length_m, location FROM "Optical slack"'
    ) == [("u-cable-1", 15.0, "manhole")]


def test_nothing_is_lost_in_total(round_tripped, foreign_bundle):
    """The blunt version: every fiberq_uuid in the original bundle is somewhere
    in the second one, whether as a feature or as a carried object."""
    _imported, _exported, again = round_tripped

    def identities(path):
        found = set()
        with sqlite3.connect(path) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'")]
            for table in tables:
                columns = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
                if "fiberq_uuid" not in columns:
                    continue
                found |= {r[0] for r in conn.execute(
                    f'SELECT fiberq_uuid FROM "{table}"') if r[0]}
            found |= {r[0] for r in conn.execute(
                "SELECT owner_uuid FROM fq_extension") if r[0]}
        return found

    before = identities(foreign_bundle)
    after = identities(again)
    assert before <= after, f"lost in the round trip: {sorted(before - after)}"


def test_importing_the_same_bundle_twice_changes_nothing(
        foreign_bundle, target_project):
    """Identity is permanent, so re-importing is a no-op rather than a doubling.

    A second import that duplicated every feature would put duplicate
    fiberq_uuids in the project -- which validation rule B4 reports as an error,
    correctly -- and a passthrough store that grew each time would eventually be
    the largest thing in the project.
    """
    reader = InterchangeBundleReader(target_project)
    first = reader.read(foreign_bundle)
    second = reader.read(foreign_bundle)

    assert first.passthrough == second.passthrough
    assert second.feature_count == 0
    assert second.already_present == first.feature_count


def test_a_bundle_from_a_newer_major_version_is_refused(foreign_bundle, target_project):
    """Spec section 9: refuse rather than import partially. Half a network,
    imported confidently, is worse than an error."""
    with sqlite3.connect(foreign_bundle) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO _fiberq_metadata (key, value) VALUES "
            "('format_version', '9.0')")

    result = InterchangeBundleReader(target_project).read(foreign_bundle)

    assert not result.ok
    assert "9.0" in result.errors[0]
    assert result.layers == {}


def test_a_newer_minor_version_is_still_read(foreign_bundle, target_project):
    """Whatever a newer minor version added travels in the passthrough store."""
    with sqlite3.connect(foreign_bundle) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO _fiberq_metadata (key, value) VALUES "
            "('format_version', '1.7')")

    result = InterchangeBundleReader(target_project).read(foreign_bundle)

    assert result.ok, result.errors
    assert result.feature_count == 4


def test_a_file_that_is_not_a_bundle_is_refused_clearly(tmp_path, target_project):
    plain = str(tmp_path / "plain.gpkg")
    layer = _memory_layer("Poles", "Point", ("fiberq_uuid:string(64)",))
    _add(layer, _point(), fiberq_uuid="u-1")
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = "Poles"
    QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, plain, QgsCoordinateTransformContext(), opts)

    result = InterchangeBundleReader(target_project).read(plain)

    assert not result.ok
    assert "interchange bundle" in result.errors[0]
