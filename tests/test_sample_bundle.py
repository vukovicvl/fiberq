"""The published example bundle must stay a valid bundle.

``docs/samples/demo-bundle.gpkg`` is a deliverable: it is the file someone
downloads to see what the interchange format actually looks like before writing
a reader for it. If the format moves and the committed example does not, the
published artefact becomes a wrong example of a real format -- worse than none,
because it is the one an implementer copies.

These tests do not diff bytes. A GeoPackage is not byte-reproducible and
``produced_at`` changes on every run, so a byte comparison would fail for
reasons that say nothing about the format. They check the things a reader
actually depends on: that it declares itself, that it is readable by this
plugin's own importer, and that every identity in it survives that round trip.
"""
import json
import pathlib
import sqlite3

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SAMPLES = REPO / "docs" / "samples"
BUNDLE = SAMPLES / "demo-bundle.gpkg"
GEOJSON = SAMPLES / "demo-bundle-geojson"


def _identities(path):
    found = set()
    with sqlite3.connect(str(path)) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'")]
        for table in tables:
            columns = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            if "fiberq_uuid" not in columns:
                continue
            found |= {r[0] for r in conn.execute(
                f'SELECT fiberq_uuid FROM "{table}"') if r[0]}
    return found


@pytest.fixture(scope="module")
def metadata():
    assert BUNDLE.is_file(), (
        f"{BUNDLE} is missing. Regenerate it: python docs/samples/generate.py")
    with sqlite3.connect(str(BUNDLE)) as conn:
        return dict(conn.execute("SELECT key, value FROM _fiberq_metadata"))


def test_the_example_declares_the_format_this_plugin_implements(metadata):
    """A published example of a format nobody can read is not an example."""
    from fiberq.core import interchange as ic

    assert metadata.get("format") == ic.FORMAT
    assert ic.can_read_format_version(metadata.get("format_version", ""))


def test_the_example_carries_every_required_metadata_key(metadata):
    for key in ("format", "format_version", "schema_version", "produced_by",
                "produced_at", "crs_epsg", "color_standard"):
        assert metadata.get(key), f"missing required key {key}"


def test_the_example_declares_the_crs_the_demo_was_authored_in(metadata):
    """Geometry is stored in 4326; this is how a reader gets the design back
    into the CRS it was drawn in."""
    assert metadata["crs_epsg"] == "3857"


def test_every_side_car_table_is_present_even_when_empty():
    """The shape of the format is part of the example.

    The demo design has no cable groupings or recorded pass-through elements, so
    these tables are empty -- but a reader writing an importer needs to see that
    they exist and what their columns are, which an omitted table would not
    show.
    """
    from fiberq.core import interchange as ic

    with sqlite3.connect(str(BUNDLE)) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    missing = [t for t in ic.SIDECAR_TABLES if t not in names]
    assert missing == [], f"side-car tables missing from the example: {missing}"


def test_the_example_imports_back_without_losing_an_identity():
    """The round trip the format exists to pass, run against the published file.

    This is what makes the example trustworthy rather than merely present: it is
    checked by reading it the way a consumer would, not by trusting the writer
    that produced it.
    """
    from qgis.core import QgsProject

    from fiberq.core.interchange_import import InterchangeBundleReader

    project = QgsProject()
    try:
        result = InterchangeBundleReader(project).read(str(BUNDLE))
        assert result.ok, result.errors

        imported = set()
        for layer in project.mapLayers().values():
            if layer.fields().indexFromName("fiberq_uuid") < 0:
                continue
            for feature in layer.getFeatures():
                value = feature["fiberq_uuid"]
                if value:
                    imported.add(str(value))
    finally:
        project.clear()

    published = _identities(BUNDLE)
    assert published, "the example bundle carries no identities at all"
    assert published <= imported, (
        f"lost on import: {sorted(published - imported)}")


def test_the_geojson_example_is_named_by_element_type():
    """A receiving tool reads pole.geojson without knowing FiberQ ever called
    that layer "Poles"."""
    assert GEOJSON.is_dir(), f"{GEOJSON} is missing"
    names = {p.name for p in GEOJSON.iterdir()}
    assert "_fiberq_metadata.json" in names
    assert "pole.geojson" in names
    assert "cable.underground.geojson" in names
    assert not any(n.endswith(".gpkg") for n in names), "staging file published"


def test_the_geojson_example_publishes_no_row_ids():
    """Spec section 4 and writer conformance rule 6. The example is what an
    implementer copies, so a row id in it propagates."""
    with open(GEOJSON / "pole.geojson", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["features"], "no features in the GeoJSON example"
    for feature in payload["features"]:
        assert "fid" not in feature["properties"]
        assert feature["properties"]["fiberq_uuid"]
