"""Tests for the WP2 validation engine (core: runner + registry + B4/C1/D1).

These need a QgsApplication (provided by pytest-qgis): the rules read features
from in-memory QgsVectorLayers. Each test builds a tiny project with a known
defect and asserts exactly the expected issue(s). No translator is installed, so
``QCoreApplication.translate`` returns the English source — issue text is English.
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


def _mk_layer(name, fields, rows, geom_type="Point", crs="EPSG:3857"):
    """Build a valid in-memory layer. ``fields`` are "key:type" strings; ``rows``
    are (attrs_dict, QgsPointXY|None) tuples."""
    uri = geom_type + "?crs=" + crs
    for field_spec in fields:
        uri += "&field=" + field_spec
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), f"failed to build memory layer {name!r}"
    feats = []
    for attrs, point in rows:
        feat = QgsFeature(layer.fields())
        for key, value in attrs.items():
            feat.setAttribute(key, value)
        if point is not None:
            feat.setGeometry(QgsGeometry.fromPointXY(point))
        feats.append(feat)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


def _issues(result, rule_id):
    return [i for i in result.issues if i.rule_id == rule_id]


# ---------------------------------------------------------------------------
# Registry integrity (pure metadata)
# ---------------------------------------------------------------------------

def test_registry_ids_unique_and_wellformed():
    """The rules this module covers are registered, and every entry is sane.

    The exact full rule list is pinned in test_validation_topology.py -- asserting
    it here too would mean two tests to update every time a rule lands.
    """
    ids = [r.id for r in vr.RULES]
    assert {"B4", "C1", "D1"} <= set(ids)
    assert len(ids) == len(set(ids))
    for rule in vr.RULES:
        assert rule.id and rule.title and rule.category
        assert callable(rule.check)
        assert isinstance(rule.default_severity, vm.Severity)


# ---------------------------------------------------------------------------
# Layer resolution — the "Optical slacks" plural / canonical divergence
# ---------------------------------------------------------------------------

def test_plural_slack_layer_resolves_to_canonical():
    project = QgsProject()
    project.addMapLayer(_mk_layer("Optical slacks", ["fiberq_uuid:string"], []))
    ctx = vm.ValidationContext(project)
    # Created as the plural "Optical slacks"; canonical name is "Optical slack".
    assert "Optical slack" in ctx.layers_by_canonical


# ---------------------------------------------------------------------------
# B4 — identity invariant
# ---------------------------------------------------------------------------

def test_b4_flags_missing_and_duplicate_uuid():
    project = QgsProject()
    project.addMapLayer(_mk_layer(
        "ODF", ["fiberq_uuid:string", "naziv:string", "kapacitet:integer"],
        [({"fiberq_uuid": "a", "naziv": "x", "kapacitet": 1}, QgsPointXY(0, 0)),
         ({"fiberq_uuid": "", "naziv": "y", "kapacitet": 1}, QgsPointXY(1, 1)),
         ({"fiberq_uuid": "a", "naziv": "z", "kapacitet": 1}, QgsPointXY(2, 2))],
    ))
    b4 = _issues(vm.run_validation(project), "B4")
    assert len(b4) == 2
    assert {i.severity for i in b4} == {vm.Severity.ERROR}
    kinds = sorted(
        "dup" if i.details.get("duplicate_of_fid") is not None else "blank"
        for i in b4
    )
    assert kinds == ["blank", "dup"]


def test_b4_flags_layer_missing_uuid_field():
    project = QgsProject()
    project.addMapLayer(_mk_layer(
        "ODF", ["naziv:string", "kapacitet:integer"],
        [({"naziv": "x", "kapacitet": 1}, QgsPointXY(0, 0))],
    ))
    b4 = _issues(vm.run_validation(project), "B4")
    assert len(b4) == 1
    assert b4[0].feature_id == -1  # a layer-level issue, not a feature one


# ---------------------------------------------------------------------------
# C1 — required attributes present
# ---------------------------------------------------------------------------

def test_c1_flags_missing_required_on_cable():
    project = QgsProject()
    project.addMapLayer(_mk_layer(
        "Underground cables",
        ["fiberq_uuid:string", "tip:string", "broj_vlakana:integer"],
        [({"fiberq_uuid": "u1", "tip": "opticki", "broj_vlakana": 12}, QgsPointXY(0, 0)),
         ({"fiberq_uuid": "u2", "tip": "", "broj_vlakana": 24}, QgsPointXY(1, 1))],
    ))
    c1 = _issues(vm.run_validation(project), "C1")
    assert len(c1) == 1
    assert c1[0].details["missing"] == ["tip"]
    assert c1[0].severity == vm.Severity.WARNING


# ---------------------------------------------------------------------------
# D1 — enum conformance (domains read from the schema, as-built typo honoured)
# ---------------------------------------------------------------------------

def test_d1_accepts_asbuilt_typo_and_flags_bad_value():
    project = QgsProject()
    project.addMapLayer(_mk_layer(
        "Underground cables",
        ["fiberq_uuid:string", "tip:string", "broj_vlakana:integer"],
        [({"fiberq_uuid": "u1", "tip": "opticki", "broj_vlakana": 12}, QgsPointXY(0, 0)),
         ({"fiberq_uuid": "u2", "tip": "bakarnI", "broj_vlakana": 12}, QgsPointXY(1, 1)),
         ({"fiberq_uuid": "u3", "tip": "banana", "broj_vlakana": 12}, QgsPointXY(2, 2))],
    ))
    d1 = _issues(vm.run_validation(project), "D1")
    assert len(d1) == 1  # opticki + the bakarnI typo are both valid stored values
    assert d1[0].details["field"] == "tip"
    assert d1[0].details["value"] == "banana"
    assert "bakarnI" in d1[0].details["allowed"]
    assert "opticki" in d1[0].details["allowed"]


# ---------------------------------------------------------------------------
# Runner behaviour
# ---------------------------------------------------------------------------

def test_clean_project_has_no_issues():
    project = QgsProject()
    project.addMapLayer(_mk_layer(
        "Underground cables",
        ["fiberq_uuid:string", "tip:string", "broj_vlakana:integer"],
        [({"fiberq_uuid": "u1", "tip": "opticki", "broj_vlakana": 12}, QgsPointXY(0, 0))],
    ))
    result = vm.run_validation(project)
    assert result.issues == []
    assert result.feature_counts.get("Underground cables") == 1


def test_empty_project_says_nothing_was_checked():
    """Silence here would read as a clean bill of health for a project that was
    never validated at all -- every rule iterates layers, and there are none."""
    result = vm.run_validation(QgsProject())
    assert [i.rule_id for i in result.issues] == ["C2"]
    assert result.issues[0].severity == vm.Severity.WARNING
    assert result.ran_rules  # every rule still ran (over zero layers)
    assert not result.rule_errors


def test_failing_rule_is_recorded_not_raised():
    def boom(ctx):
        raise RuntimeError("kaboom")
        yield  # noqa: unreachable — makes boom a generator like a real check

    bad = vm.ValidationRule(
        id="X1", title="x", category="c",
        default_severity=vm.Severity.INFO, check=boom,
    )
    good = next(r for r in vr.RULES if r.id == "B4")
    result = vm.run_validation(QgsProject(), rules=[bad, good])
    assert any("X1" in e for e in result.rule_errors)
    assert "B4" in result.ran_rules  # the good rule still ran after the bad one


def test_severity_override_downgrades_rule():
    project = QgsProject()
    project.addMapLayer(_mk_layer(
        "Underground cables",
        ["fiberq_uuid:string", "tip:string", "broj_vlakana:integer"],
        [({"fiberq_uuid": "u1", "tip": "", "broj_vlakana": 12}, QgsPointXY(0, 0))],
    ))
    cfg = vm.ValidationConfig(severity_overrides={"C1": vm.Severity.INFO})
    c1 = _issues(vm.run_validation(project, config=cfg), "C1")
    assert c1 and all(i.severity == vm.Severity.INFO for i in c1)
