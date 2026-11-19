"""One project from before FiberQ 1.0, taken through the plugin end to end: opened and migrated, a cable laid,
validated, exported as an interchange bundle and imported again, with counts, identities and lengths compared at
every step.

``test_migrations.py`` migrates the same pre-1.0 GeoPackage into a fresh project and checks the migration alone, and
``test_interchange_roundtrip.py`` sends a bundle it builds by hand through an import and an export. Neither lays a cable
or validates, only the first starts from an old project, and neither compares a coordinate, or a length with a fraction.
This file runs the steps one after the other on one project, as a user does, so that a step which looks right on its own
but loses what a later step needs is caught: a bundle writer that rounds every length to two decimals fails here, and
passes ``test_interchange_roundtrip.py``, whose lengths (120.0 and 15.0) are whole numbers.

The project comes from ``tests/fixtures/make_sample_project.py``: five layers under their legacy names in UTM zone
34N (EPSG:32634), with no identities and no schema marker. It is opened into QGIS's project and migrated by what the
plugin runs after QGIS reads a project. The cable is laid as Cable laying > Underground > Backbone lays it
(``lay_cable_type``), from ODF-01 to manhole O-1 along the route, on a plugin whose managers are wired as the plugin
wires them, with the cable picker and the message boxes replaced. Then the project is validated, written as a
bundle and read into a new, empty project, which is validated too. Every expected value is worked out by hand from
the generator's coordinates: the new cable is sqrt(100**2 + 50**2) = 111.803399 m on the grid, and 111.845358 m on
the ground (the grid length over the point scale factor, 0.999624845 at 44,950 m west of the zone's central
meridian). The current schema version is compared with ``SCHEMA_VERSION``, never a literal; a project before the
migration reads as "0".

The steps run once, in a module fixture, each only while those before it passed. A test whose step, or an earlier
one, failed fails with that step's traceback; so a broken migration fails every test from the migration on with
the migration's own error, and the test of the project before it still runs. A step that changes a FiberQ setting
fails too, and the setting is put back. The fixture hands the tests plain values only: QGIS's project is cleared,
and the project the bundle was read into is cleared and dropped, before the first test runs, so no QGIS object
outlives the fixture. The session canvas does not render while the steps run.

One test is an expected failure: the imported project carries no schema marker.
"""
import importlib.util
import math
import os
import traceback
import uuid

import pytest
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer, QgsWkbTypes

from support.core_env import (CoreIface, canvas_not_rendering, fiberq_settings, is_null, patch_cable_picker,
                              record_message_boxes, sqlite_rows, undo_settings, wired_plugin)

from fiberq.core.interchange_bundle import InterchangeBundleWriter, read_bundle_metadata
from fiberq.core.interchange_import import InterchangeBundleReader
from fiberq.core.schema_version import read_project_schema_version
from fiberq.core.validation_manager import run_validation
from fiberq.models.schema import SCHEMA_VERSION, canonical_layer_name
from fiberq.utils.measure import distance_area, ground_length

#: The generator's tables, in its order, and the names FiberQ gives them now.
LEGACY = ("ODF", "Kablovi_podzemni", "Trasa", "OKNA", "Objekti")
CANONICAL = {"ODF": "ODF", "Kablovi_podzemni": "Underground cables", "Trasa": "Route", "OKNA": "Manholes",
             "Objekti": "Objects"}
COUNTS_BEFORE = {"ODF": 2, "Underground cables": 2, "Route": 1, "Manholes": 2, "Objects": 1}
COUNTS_AFTER = dict(COUNTS_BEFORE, **{"Underground cables": 3})

#: The steps, in the order the module fixture runs them.
STAGES = ("build", "open", "before", "migrate", "lay", "validate", "export", "import", "after")

#: The stretch ODF-01 (455000 4965000) to O-1 (455100 4965050) in UTM 34N: sqrt(100**2 + 50**2) on the grid, and
#: that over the point scale factor 0.999624845 on the WGS 84 ellipsoid (Snyder's inverse UTM then Vincenty, and the
#: grid length over the scale factor by Simpson's rule, agree to 1e-6 m).
NEW_CABLE_GRID_M = math.hypot(100.0, 50.0)
NEW_CABLE_GROUND_M = 111.845358

#: The length columns compared across the round trip, where the source layer has them.
LENGTHS = ("duzina_m", "slack_m", "total_len_m", "duzina", "duzina_km")

#: What the cable picker answers (the dialog is replaced): MC-03, an underground backbone cable of 12 fibres.
PICKED = {
    "vrsta": "podzemni", "tip": "Optical", "podtip": "glavni", "color_code": "", "broj_cevcica": 1,
    "broj_vlakana": 12, "tip_kabla": "TOSM-12", "vrsta_vlakana": "", "vrsta_omotaca": "", "vrsta_armature": "",
    "talasno_podrucje": "", "naziv": "MC-03", "slabljenje_dbkm": 0.0, "hrom_disp_ps_nmxkm": 0.0,
    "stanje_kabla": "Projektovano", "cable_laying": "Podzemno", "vrsta_mreze": "", "godina_ugradnje": 2026,
    "konstr_vlakna_u_cevcicama": 0, "konstr_sa_uzlepljenim_elementom": 0, "konstr_punjeni_kabl": 0,
    "konstr_sa_arm_vlaknima": 0, "konstr_bez_metalnih": 0, "fibers_per_tube": 12, "total_fibers": 12,
    "color_standard": "TIA-598-C",
}

#: A column the target layer lacks, in a comparison of length columns.
NO_COLUMN = "<no such column>"


class ImportLeftUnstamped(AssertionError):
    """WP5-FU-24 item 15: a project that FiberQ fills itself carries no schema marker, an imported one included."""


class Chain:
    """The steps of the scenario, run once and in order by the module fixture, and the plain values they keep.

    ``run`` runs a step only while none has failed, and keeps the first failure: the step's name and its traceback.
    A step that changed a FiberQ setting has failed too; the setting is put back. ``reached`` gives a test the
    record, or fails the test with that traceback when its own step or an earlier one failed.
    """

    def __init__(self):
        self.record = {}
        self.failure = None

    def run(self, stage, step, *args):
        if self.failure is not None:
            return
        before = fiberq_settings()
        try:
            step(self.record, *args)
        except Exception:
            self.failure = (stage, traceback.format_exc())
        changed = undo_settings(before)
        if changed and self.failure is None:
            self.failure = (stage, "FiberQ settings changed (now undone): %s" % changed)

    def reached(self, stage):
        if self.failure is not None and STAGES.index(self.failure[0]) <= STAGES.index(stage):
            pytest.fail("the scenario stopped at its %s step:\n%s" % self.failure, pytrace=False)
        return self.record


def _generator():
    """tests/fixtures/make_sample_project.py, loaded from its file (tests/fixtures is not a package)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "make_sample_project.py")
    spec = importlib.util.spec_from_file_location("make_sample_project", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plain(value):
    """A value read from a layer, with NULL as None on Qt 5 as on Qt 6."""
    return None if is_null(value) else value


def _text(value):
    return "" if is_null(value) else str(value)


def _uuids(layer):
    """The layer's identities, sorted; None for a layer with no identity column."""
    if layer.fields().indexOf("fiberq_uuid") < 0:
        return None
    return sorted(_text(feature["fiberq_uuid"]) for feature in layer.getFeatures())


def _canonical(name):
    """A layer's canonical name; a name FiberQ does not know stays as it is."""
    return canonical_layer_name(name) or name


def _by_canonical(project):
    """The project's vector layers by their canonical names."""
    return {_canonical(layer.name()): layer for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)}


def _issues(result):
    """A validation's issues as (rule, severity, identity), a layer-level issue by its layer's canonical name."""
    return sorted((issue.rule_id, issue.severity.value, issue.fiberq_uuid or _canonical(issue.layer_name))
                  for issue in result.issues)


def _bundle_uuids(path, table):
    """The identities in a table of the bundle at ``path``, sorted."""
    return sorted(value for (value,) in sqlite_rows(path, 'SELECT fiberq_uuid FROM "%s"' % table))


def _features(layer, project=None):
    """Each feature of ``layer`` by its identity: its length columns, its ground length (a line's) and its vertices."""
    columns = [name for name in LENGTHS if layer.fields().indexOf(name) >= 0]
    line = layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry
    out = {}
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        out[_text(feature["fiberq_uuid"])] = {
            "lengths": {name: _plain(feature[name]) for name in columns},
            "ground": ground_length(geometry, layer, project=project) if line else None,
            "vertices": [(vertex.x(), vertex.y()) for vertex in geometry.vertices()],
        }
    return out


# --- the steps: each keeps plain values in the record, and QGIS objects only in ``held`` ------------------------------

def _build(record, paths):
    QgsProject.instance().clear()
    _generator().build_pre_uuid_gpkg(paths["gpkg"])


def _open(record, held, paths):
    project = QgsProject.instance()
    layers = [QgsVectorLayer("%s|layername=%s" % (paths["gpkg"], name), name, "ogr") for name in LEGACY]
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:32634"))
    project.addMapLayers([layer for layer in layers if layer.isValid()])
    assert all(layer.isValid() for layer in layers), [layer.name() for layer in layers if not layer.isValid()]
    held["layers"] = dict(zip(LEGACY, layers))


def _before(record):
    result = run_validation(QgsProject.instance())
    record["before"] = {
        "marker": result.schema_version,
        "counts": dict(result.feature_counts),
        "b4": sorted((i.rule_id, i.severity.value, i.layer_name) for i in result.issues if i.rule_id == "B4"),
    }


def _migrate(record, held, paths, monkeypatch):
    """What QGIS runs a second after it reads a project (main_plugin.py:2328-2331)."""
    iface = CoreIface(units_per_pixel=1.0)
    # FiberQ reports to QGIS's global iface when it is given none (utils/errors.py), so this one stands in for it too.
    monkeypatch.setattr("qgis.utils.iface", iface)
    plugin = held["plugin"] = wired_plugin(iface)
    plugin._run_schema_migrations()
    rows = sqlite_rows(paths["gpkg"], 'SELECT fiberq_uuid FROM "OKNA" ORDER BY fid')
    record["migrate"] = {
        "pushed": list(plugin.iface.messageBar().messages),
        "marker": read_project_schema_version(QgsProject.instance()),
        "uuids": {CANONICAL[name]: _uuids(layer) for name, layer in held["layers"].items()},
        "okna_on_disk": sorted(_text(value) for (value,) in rows),
    }


def _lay(record, held, paths, said):
    """Lay cable as Cable laying > Underground > Backbone does, from ODF-01 to O-1 along Trasa-1."""
    plugin, layers = held["plugin"], held["layers"]
    odf, okna, cables = layers["ODF"], layers["OKNA"], layers["Kablovi_podzemni"]
    odf.selectByIds([f.id() for f in odf.getFeatures() if f["naziv"] == "ODF-01"])
    okna.selectByIds([f.id() for f in okna.getFeatures() if f["broj_okna"] == "O-1"])
    bar = plugin.iface.messageBar().messages
    pushed, shown = len(bar), len(said)
    measure = distance_area(cables.crs())
    plugin.lay_cable_type("podzemni", "glavni")
    known = set(record["migrate"]["uuids"]["Underground cables"])
    record["lay"] = {
        "said": said[shown:],
        "pushed": bar[pushed:],
        "layer": cables.name(),
        "wgs84": (measure.willUseEllipsoid(), measure.ellipsoid()),
        "new": [{"vertices": [(point.x(), point.y()) for point in f.geometry().asPolyline()],
                 "od": _plain(f["od"]), "do": _plain(f["do"]), "naziv": _plain(f["naziv"]),
                 "duzina_m": _plain(f["duzina_m"]), "total_len_m": _plain(f["total_len_m"]),
                 "slack_m": _plain(f["slack_m"])}
                for f in cables.getFeatures() if _text(f["fiberq_uuid"]) not in known],
        "tips_on_disk": sqlite_rows(paths["gpkg"], 'SELECT tip FROM "Kablovi_podzemni" ORDER BY fid'),
    }


def _validate(record, held):
    result = run_validation(QgsProject.instance())
    names = {_text(f["fiberq_uuid"]): _plain(f["naziv"]) for f in held["layers"]["Kablovi_podzemni"].getFeatures()}
    by_rule = {}
    for issue in result.issues:
        by_rule.setdefault(issue.rule_id, []).append(issue)
    record["validate"] = {
        "marker": result.schema_version,
        "counts": dict(result.feature_counts),
        "rule_errors": list(result.rule_errors),
        "severities": result.counts_by_severity(),
        "rules": sorted(by_rule),
        "d3": sorted(names.get(i.fiberq_uuid, i.layer_name) for i in by_rule.get("D3", [])),
        "d1": sorted((i.layer_name, i.details.get("value")) for i in by_rule.get("D1", [])),
        "a3": [(i.layer_name, i.where) for i in by_rule.get("A3", [])],
        "issues": _issues(result),
    }


def _export(record, paths):
    project = QgsProject.instance()
    exported = InterchangeBundleWriter(project).write(paths["bundle"])
    metadata = read_bundle_metadata(paths["bundle"])
    record["export"] = {
        "ok": exported.ok,
        "errors": list(exported.errors),
        "layers": dict(exported.layers),
        "skipped": list(exported.skipped),
        "warnings": list(exported.warnings),
        "summary": exported.summary(),
        "metadata": (metadata.get("crs_epsg"), metadata.get("schema_version")),
        "in_project": {name: _uuids(layer) for name, layer in _by_canonical(project).items()},
        "in_bundle": {name: _bundle_uuids(paths["bundle"], name) for name in exported.layers},
    }


def _import(record, held, paths):
    target = held["target"] = QgsProject()
    imported = InterchangeBundleReader(target).read(paths["bundle"])
    source, again = _by_canonical(QgsProject.instance()), _by_canonical(target)
    record["import"] = {
        "ok": imported.ok,
        "errors": list(imported.errors),
        "layers": dict(imported.layers),
        "created": sorted(imported.created),
        "already_present": imported.already_present,
        "summary": imported.summary(),
        "crs": target.crs().authid(),
        "uuids": {name: (_uuids(layer), _uuids(again[name]) if name in again else None)
                  for name, layer in source.items()},
        "source": {name: _features(layer) for name, layer in source.items()},
        "target": {name: _features(layer, project=target) for name, layer in again.items()},
    }


def _after(record, held):
    target = held["target"]
    record["after"] = {"issues": _issues(run_validation(target)), "marker": read_project_schema_version(target)}


@pytest.fixture(scope="module")
def chain(qgis_app, qgis_canvas, tmp_path_factory):
    """The scenario, run once for the module: the ``Chain`` with its record.

    QGIS's project is cleared before the first step and after the last, whatever failed; the project the bundle is
    read into is cleared and dropped then too. Only then, with the session canvas rendering again as before and the
    cable picker, the message boxes and QGIS's global iface back, is the chain handed over.
    """
    folder = tmp_path_factory.mktemp("scenario")
    paths = {"gpkg": str(folder / "legacy_pre_uuid.gpkg"), "bundle": str(folder / "scenario.gpkg")}
    scenario = Chain()
    with canvas_not_rendering(qgis_canvas), pytest.MonkeyPatch.context() as mp:
        said = record_message_boxes(mp)
        patch_cable_picker(mp, PICKED)
        held = {}
        try:
            scenario.run("build", _build, paths)
            scenario.run("open", _open, held, paths)
            scenario.run("before", _before)
            scenario.run("migrate", _migrate, held, paths, mp)
            scenario.run("lay", _lay, held, paths, said)
            scenario.run("validate", _validate, held)
            scenario.run("export", _export, paths)
            scenario.run("import", _import, held, paths)
            scenario.run("after", _after, held)
        finally:
            target = held.pop("target", None)
            if target is not None:
                target.clear()
            target = None
            held.clear()
            QgsProject.instance().clear()
    yield scenario


def _is_uuid4(text):
    try:
        return uuid.UUID(text).version == 4
    except (TypeError, ValueError):
        return False


def test_the_pre_1_0_project_reads_as_unmigrated(chain):
    """Before the migration the project has no marker (it reads as "0"), the generator's features, and in each of
    its five layers the validation's error for a layer with no identity column."""
    before = chain.reached("before")["before"]
    assert before["marker"] == "0"
    assert before["counts"] == COUNTS_BEFORE
    assert before["b4"] == sorted(("B4", "error", name) for name in LEGACY)


def test_project_open_migrates_and_says_so(chain):
    """Opening the project migrates it, says so on the message bar with the count (2 + 2 + 1 + 2 + 1 = 8 features in
    5 layers), stamps the marker and gives every feature an identity of its own, saved to the file."""
    migrate = chain.reached("migrate")["migrate"]
    assert migrate["pushed"] == [
        ("pushInfo", f"Upgraded project schema 0 -> {SCHEMA_VERSION} (assigned 8 UUIDs across 5 layers)")]
    assert migrate["marker"] == SCHEMA_VERSION
    for name, values in migrate["uuids"].items():
        assert values is not None and len(values) == COUNTS_BEFORE[name], (name, values)
        assert len(set(values)) == len(values), (name, values)
        assert all(_is_uuid4(value) for value in values), (name, values)
    assert migrate["okna_on_disk"] == migrate["uuids"]["Manholes"]


def test_the_cable_is_laid_along_the_route(chain):
    """Lay cable lays MC-03 along the route from ODF-01 to O-1 and stores its length on the ground, not on the grid.

    Its ends follow the layers' order in the project (the layer ids begin with the names, and "ODF" comes before
    "OKNA"), not the order of selection. Restyling the cable layer renames it and rewrites the legacy cable type of
    every cable in the file.
    """
    lay = chain.reached("lay")["lay"]
    assert lay["wgs84"] == (True, "EPSG:7030"), "premise: the length is measured on WGS 84"
    assert lay["layer"] == "Underground cables"
    assert lay["said"] == ["Cable has been laid along the route!"]
    assert lay["pushed"] == []
    assert len(lay["new"]) == 1, lay["new"]
    cable = lay["new"][0]
    assert cable["vertices"] == [(455000.0, 4965000.0), (455100.0, 4965050.0)]
    assert (cable["od"], cable["do"], cable["naziv"]) == ("ODF-01", "MH O-1", "MC-03")
    assert cable["duzina_m"] == pytest.approx(NEW_CABLE_GROUND_M, abs=1e-3)
    assert abs(cable["duzina_m"] - NEW_CABLE_GRID_M) > 0.03
    assert cable["total_len_m"] == cable["duzina_m"]
    assert cable["slack_m"] == 0.0
    assert lay["tips_on_disk"] == [("Optical",), ("Optical",), ("Optical",)]


def test_validation_finds_exactly_the_planted_faults(chain):
    """The generator's planted faults, and nothing else: ODF-02 at no cable's end (A3); two element states and a
    cable state the domain lacks (D1); and stored lengths far from the drawn ones on MC-01 (812.5 m for 111.8 m), on
    the route Trasa-1 drawn along it, and on MC-02 (204.0 m for 206.2 m, over the 1% allowed). All are warnings."""
    result = chain.reached("validate")["validate"]
    assert result["marker"] == SCHEMA_VERSION
    assert result["counts"] == COUNTS_AFTER
    assert result["rule_errors"] == []
    assert result["rules"] == ["A3", "D1", "D3"]
    assert result["severities"] == {"error": 0, "warning": 7, "info": 0}
    assert result["d3"] == ["MC-01", "MC-02", "Trasa"]
    assert result["d1"] == [("ODF", "Postojece"), ("ODF", "Projektovano"), ("Underground cables", "Postojece")]
    assert result["a3"] == [("ODF", (455120.0, 4965080.0))]


def test_the_bundle_holds_every_feature_under_its_identity(chain):
    """The bundle holds the five layers with every feature, the new cable among them, each under the identity it has
    in the project, and its metadata names the project's CRS and the schema."""
    export = chain.reached("export")["export"]
    assert export["ok"], export["errors"]
    assert export["layers"] == COUNTS_AFTER
    assert export["skipped"] == []
    assert export["warnings"] == []
    assert export["summary"] == "5 layer(s), 9 feature(s)"
    assert export["metadata"] == ("32634", SCHEMA_VERSION)
    assert sorted(export["in_bundle"]) == sorted(export["in_project"])
    for name, values in export["in_project"].items():
        assert export["in_bundle"][name] == values, name


def test_the_reimport_restores_counts_identities_and_lengths(chain):
    """Read into an empty project, the bundle gives back the five layers in the project's CRS, every feature under
    its identity, every stored length (NULL as NULL), the same ground lengths and the same vertices: the bundle
    stores EPSG:4326, and the way back to EPSG:32634 moves no vertex by as much as 1e-6 m (measured 9.5e-10 m)."""
    imported = chain.reached("import")["import"]
    assert imported["ok"], imported["errors"]
    assert imported["layers"] == COUNTS_AFTER
    assert imported["created"] == sorted(COUNTS_AFTER)
    assert imported["already_present"] == 0
    assert imported["summary"] == "5 layer(s), 9 feature(s)"
    assert imported["crs"] == "EPSG:32634"
    assert sorted(imported["target"]) == sorted(imported["source"])
    worst = 0.0
    for name, (before, after) in imported["uuids"].items():
        assert after == before, name
        old_layer, new_layer = imported["source"][name], imported["target"][name]
        for identity, old in old_layer.items():
            new = new_layer[identity]
            for column, value in old["lengths"].items():
                assert new["lengths"].get(column, NO_COLUMN) == value, (name, identity, column)
            if old["ground"] is not None:
                assert new["ground"] == pytest.approx(old["ground"], abs=1e-6), (name, identity)
            assert len(new["vertices"]) == len(old["vertices"]), (name, identity)
            for (x1, y1), (x2, y2) in zip(old["vertices"], new["vertices"]):
                worst = max(worst, math.hypot(x2 - x1, y2 - y1))
    assert worst < 1e-6


def test_the_reimported_project_validates_as_the_original(chain):
    """The validation of the imported project finds the same issues on the same features as the original's."""
    record = chain.reached("after")
    assert record["after"]["issues"] == record["validate"]["issues"]


@pytest.mark.xfail(strict=True, raises=ImportLeftUnstamped,
                   reason="WP5-FU-24 item 15: nothing stamps a project FiberQ fills itself (Project > New, or an "
                          "import), so it reads as schema 0 until it is reopened; the v1.8.0 fix removes this marker")
def test_the_reimported_project_carries_the_schema_marker(chain):
    """The imported project carries the schema marker. Its premises: the bundle was read whole, it declares the
    schema, and every feature has an identity of its own (a uuid4), which the import keeps. Measured: it reads as
    "0", so its next open announces an upgrade."""
    record = chain.reached("after")
    imported = record["import"]
    assert imported["ok"] and imported["layers"] == COUNTS_AFTER, "premise: the bundle was read whole: %r" % (
        imported["errors"],)
    assert record["export"]["metadata"] == ("32634", SCHEMA_VERSION), "premise: the bundle declares the schema"
    for before, after in imported["uuids"].values():
        distinct_uuid4s = bool(before) and len(set(before)) == len(before) and all(_is_uuid4(v) for v in before)
        assert distinct_uuid4s and after == before, "premise: every feature has its identity: %r" % (imported["uuids"],)
    every = [value for before, _ in imported["uuids"].values() for value in before]
    assert len(set(every)) == len(every), "premise: no two features share an identity: %r" % (imported["uuids"],)
    marker = record["after"]["marker"]
    if marker != SCHEMA_VERSION:
        # WP5-FU-24 item 15's effect and nothing else: the project reads as schema 0.
        assert marker == "0", "the imported project reads as schema %r" % (marker,)
        raise ImportLeftUnstamped("the imported project reads as schema %r, not %r" % (marker, SCHEMA_VERSION))
