"""Tests for the WP2 domain rules: D2 numeric ranges, D3 length coherence,
E1 CRS consistency, E2 geometry health.

Geometry is in EPSG:3857 (metres) unless a test is specifically about a
geographic CRS, so lengths in these fixtures are directly comparable to the
stored values.
"""
from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from fiberq.core import validation_manager as vm
from fiberq.core import validation_rules as vr

METRIC = "EPSG:3857"
GEOGRAPHIC = "EPSG:4326"


def _layer(name, geom_type, fields, rows, crs=METRIC):
    """rows: [(attrs, QgsGeometry|None)]"""
    uri = f"{geom_type}?crs={crs}"
    for spec in fields:
        uri += "&field=" + spec
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), name
    feats = []
    for attrs, geom in rows:
        feat = QgsFeature(layer.fields())
        for key, value in attrs.items():
            feat.setAttribute(key, value)
        if geom is not None:
            feat.setGeometry(geom)
        feats.append(feat)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


def _line(*xy):
    return QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in xy])


def _run(project, rule_ids, config=None):
    rules = [r for r in vr.RULES if r.id in rule_ids]
    assert len(rules) == len(rule_ids)
    result = vm.run_validation(project, rules=rules, config=config)
    assert not result.rule_errors, result.rule_errors
    return result


def _ids(result, rule_id):
    return [i for i in result.issues if i.rule_id == rule_id]


CABLE_FIELDS = (
    "fiberq_uuid:string", "broj_vlakana:integer", "broj_cevcica:integer",
    "slabljenje_dbkm:double", "duzina_m:double", "slack_m:double",
    "total_len_m:double",
)


# ---------------------------------------------------------------------------
# D2 -- numeric ranges
# ---------------------------------------------------------------------------

def test_d2_accepts_plausible_values(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1", "broj_vlakana": 24, "broj_cevcica": 4,
          "slabljenje_dbkm": 0.35}, _line((0, 0), (100, 0))),
    ]))
    assert _ids(_run(project, {"D2"}), "D2") == []


def test_d2_flags_zero_and_excessive_fibre_counts(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1", "broj_vlakana": 0}, _line((0, 0), (100, 0))),
        ({"fiberq_uuid": "c2", "broj_vlakana": 5000}, _line((0, 10), (100, 10))),
        ({"fiberq_uuid": "c3", "broj_vlakana": 1152}, _line((0, 20), (100, 20))),
    ]))
    issues = _ids(_run(project, {"D2"}), "D2")
    # 1152 is the documented maximum and must be accepted.
    assert len(issues) == 2
    assert {i.details["value"] for i in issues} == {0.0, 5000.0}
    assert all(i.severity == vm.Severity.WARNING for i in issues)


def test_d2_flags_a_negative_duct_count(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1", "broj_vlakana": 12, "broj_cevcica": -2},
         _line((0, 0), (100, 0))),
    ]))
    issues = _ids(_run(project, {"D2"}), "D2")
    assert [i.details["field"] for i in issues] == ["broj_cevcica"]


def test_d2_flags_implausible_attenuation(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1", "broj_vlakana": 12, "slabljenje_dbkm": 250.0},
         _line((0, 0), (100, 0))),
    ]))
    issues = _ids(_run(project, {"D2"}), "D2")
    assert [i.details["field"] for i in issues] == ["slabljenje_dbkm"]


def test_d2_skips_blank_values(qgis_app):
    """An unset number is incompleteness (C1), not an out-of-range value."""
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1"}, _line((0, 0), (100, 0))),
    ]))
    assert _ids(_run(project, {"D2"}), "D2") == []


def test_d2_ignores_text_capacity_on_pipes(qgis_app):
    """Pipe `kapacitet` is text as-built, so it must not be range-checked."""
    project = QgsProject()
    project.addMapLayer(_layer(
        "PE pipes", "LineString",
        ("fiberq_uuid:string", "kapacitet:string", "fi:integer", "duzina_m:double"),
        [({"fiberq_uuid": "p1", "kapacitet": "not a number", "fi": 40},
          _line((0, 0), (100, 0)))],
    ))
    assert _ids(_run(project, {"D2"}), "D2") == []


def test_d2_flags_a_zero_pipe_diameter(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer(
        "PE pipes", "LineString",
        ("fiberq_uuid:string", "fi:integer", "duzina_m:double"),
        [({"fiberq_uuid": "p1", "fi": 0}, _line((0, 0), (100, 0)))],
    ))
    assert [i.details["field"] for i in _ids(_run(project, {"D2"}), "D2")] == ["fi"]


# ---------------------------------------------------------------------------
# D3 -- length coherence
# ---------------------------------------------------------------------------

def test_d3_accepts_a_matching_stored_length(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1", "duzina_m": 100.0}, _line((0, 0), (100, 0))),
    ]))
    assert _ids(_run(project, {"D3"}), "D3") == []


def test_d3_flags_a_stored_length_that_contradicts_geometry(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1", "duzina_m": 750.0}, _line((0, 0), (100, 0))),
    ]))
    issues = _ids(_run(project, {"D3"}), "D3")
    assert len(issues) == 1
    assert issues[0].details["stored"] == 750.0
    assert round(issues[0].details["computed"]) == 100


def test_d3_tolerates_small_rounding_differences(qgis_app):
    """100.4 vs 100.0 is inside the 1% / 0.5-unit allowance."""
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1", "duzina_m": 100.4}, _line((0, 0), (100, 0))),
    ]))
    assert _ids(_run(project, {"D3"}), "D3") == []


def test_d3_checks_total_equals_length_plus_slack(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "ok", "duzina_m": 100.0, "slack_m": 10.0,
          "total_len_m": 110.0}, _line((0, 0), (100, 0))),
        ({"fiberq_uuid": "bad", "duzina_m": 100.0, "slack_m": 10.0,
          "total_len_m": 999.0}, _line((0, 10), (100, 10))),
    ]))
    issues = _ids(_run(project, {"D3"}), "D3")
    assert len(issues) == 1
    assert issues[0].details["total_len_m"] == 999.0
    assert issues[0].details["expected"] == 110.0


def test_d3_checks_route_kilometres_against_metres(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer(
        "Route", "LineString",
        ("fiberq_uuid:string", "duzina:double", "duzina_km:double"),
        [({"fiberq_uuid": "r1", "duzina": 1000.0, "duzina_km": 7.5},
          _line((0, 0), (1000, 0)))],
    ))
    issues = _ids(_run(project, {"D3"}), "D3")
    km = [i for i in issues if "duzina_km" in i.details]
    assert len(km) == 1
    assert km[0].details["expected"] == 1.0


def test_d3_skips_and_says_so_in_a_geographic_crs(qgis_app):
    """The whole point: degrees vs metres would produce nonsense warnings."""
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1", "duzina_m": 100.0}, _line((0, 0), (1, 0))),
    ], crs=GEOGRAPHIC))
    issues = _ids(_run(project, {"D3"}), "D3")
    assert len(issues) == 1
    assert issues[0].severity == vm.Severity.INFO
    assert issues[0].details["skipped"] is True
    assert issues[0].details["crs"] == GEOGRAPHIC


def test_d3_tolerance_is_configurable(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1", "duzina_m": 130.0}, _line((0, 0), (100, 0))),
    ]))
    assert len(_ids(_run(project, {"D3"}), "D3")) == 1
    loose = vm.ValidationConfig(length_rel_tol=0.5)
    assert _ids(_run(project, {"D3"}, config=loose), "D3") == []


# ---------------------------------------------------------------------------
# E1 -- CRS consistency
# ---------------------------------------------------------------------------

def test_e1_is_clean_for_one_projected_crs(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1"}, _line((0, 0), (100, 0))),
    ]))
    project.addMapLayer(_layer(
        "ODF", "Point", ("fiberq_uuid:string",),
        [({"fiberq_uuid": "n1"}, QgsGeometry.fromPointXY(QgsPointXY(0, 0)))]))
    assert _ids(_run(project, {"E1"}), "E1") == []


def test_e1_flags_mixed_crs(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1"}, _line((0, 0), (100, 0))),
    ]))
    project.addMapLayer(_layer(
        "ODF", "Point", ("fiberq_uuid:string",),
        [({"fiberq_uuid": "n1"}, QgsGeometry.fromPointXY(QgsPointXY(0, 0)))],
        crs=GEOGRAPHIC))
    mixed = [i for i in _ids(_run(project, {"E1"}), "E1") if "crs_list" in i.details]
    assert len(mixed) == 1
    assert set(mixed[0].details["crs_list"]) == {METRIC, GEOGRAPHIC}


def test_e1_flags_a_geographic_crs_where_lengths_are_stored(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1"}, _line((0, 0), (1, 0))),
    ], crs=GEOGRAPHIC))
    geographic = [i for i in _ids(_run(project, {"E1"}), "E1")
                  if i.details.get("geographic")]
    assert len(geographic) == 1
    assert geographic[0].severity == vm.Severity.WARNING


# ---------------------------------------------------------------------------
# E2 -- geometry health
# ---------------------------------------------------------------------------

def test_e2_flags_missing_geometry_as_an_error(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer(
        "ODF", "Point", ("fiberq_uuid:string",),
        [({"fiberq_uuid": "n1"}, None)]))
    issues = _ids(_run(project, {"E2"}), "E2")
    assert len(issues) == 1
    assert issues[0].severity == vm.Severity.ERROR


def test_e2_flags_a_zero_length_line(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1"}, _line((5, 5), (5, 5))),
    ]))
    issues = _ids(_run(project, {"E2"}), "E2")
    assert len(issues) == 1
    assert issues[0].severity == vm.Severity.WARNING


def test_e2_flags_a_self_crossing_line(qgis_app):
    """A self-crossing LineString is OGC-valid, so this needs isSimple()."""
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1"}, _line((0, 0), (100, 100), (0, 100), (100, 0))),
    ]))
    issues = _ids(_run(project, {"E2"}), "E2")
    assert len(issues) == 1
    assert issues[0].details["expected_geometry"] == "LineString"


def test_e2_accepts_a_normal_line(qgis_app):
    project = QgsProject()
    project.addMapLayer(_layer("Underground cables", "LineString", CABLE_FIELDS, [
        ({"fiberq_uuid": "c1"}, _line((0, 0), (100, 0), (200, 50))),
    ]))
    assert _ids(_run(project, {"E2"}), "E2") == []


def test_e2_flags_a_bowtie_polygon(qgis_app):
    project = QgsProject()
    bowtie = QgsGeometry.fromPolygonXY([[
        QgsPointXY(0, 0), QgsPointXY(100, 100),
        QgsPointXY(100, 0), QgsPointXY(0, 100), QgsPointXY(0, 0),
    ]])
    project.addMapLayer(_layer(
        "Service Area", "Polygon",
        ("fiberq_uuid:string", "area_m2:double", "perim_m:double"),
        [({"fiberq_uuid": "a1"}, bowtie)]))
    issues = _ids(_run(project, {"E2"}), "E2")
    assert len(issues) == 1
    assert issues[0].details["expected_geometry"] == "Polygon"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_holds_the_full_v140_core_set(qgis_app):
    ids = [r.id for r in vr.RULES]
    assert ids == ["A1", "A2", "A3", "B1", "B2", "B3", "B4",
                   "C1", "D1", "D2", "D3", "E1", "E2"]
    assert len(ids) == len(set(ids))
    for rule in vr.RULES:
        assert rule.title and rule.category and callable(rule.check)
        assert isinstance(rule.default_severity, vm.Severity)


def test_a_clean_project_passes_every_rule(qgis_app):
    """End-to-end: a small, correct project produces no issues at all."""
    project = QgsProject()
    cables = _layer("Underground cables", "LineString", CABLE_FIELDS + (
        "tip:string", "naziv:string"), [
        ({"fiberq_uuid": "c1", "tip": "opticki", "broj_vlakana": 24,
          "broj_cevcica": 2, "slabljenje_dbkm": 0.35, "duzina_m": 100.0,
          "slack_m": 10.0, "total_len_m": 110.0}, _line((0, 0), (100, 0))),
    ])
    project.addMapLayer(cables)
    project.addMapLayer(_layer(
        "ODF", "Point", ("fiberq_uuid:string", "naziv:string",
                         "kapacitet:integer", "stanje:string"),
        [({"fiberq_uuid": "n1", "naziv": "ODF-1", "kapacitet": 48,
           "stanje": "Planned"}, QgsGeometry.fromPointXY(QgsPointXY(0, 0))),
         ({"fiberq_uuid": "n2", "naziv": "ODF-2", "kapacitet": 48,
           "stanje": "Built"}, QgsGeometry.fromPointXY(QgsPointXY(100, 0)))]))

    result = vm.run_validation(project)
    assert not result.rule_errors, result.rule_errors
    assert result.issues == [], [(i.rule_id, i.message) for i in result.issues]
    assert len(result.ran_rules) == len(vr.RULES)
