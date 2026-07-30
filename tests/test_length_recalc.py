"""Tests for core.length_manager -- rewriting stored lengths from geometry.

The contract that matters most is the one with D3: recalculate then validate must
leave nothing behind. Several tests below assert exactly that round trip rather
than just checking the arithmetic, because a tolerance drift between the rule and
the fix would be invisible to a unit test of either one alone.
"""
import ast
import inspect
import math
import textwrap

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from fiberq.core import validation_rules as vr
from fiberq.core.length_manager import (
    apply_recalculation,
    plan_recalculation,
    recalculate_lengths,
)
from fiberq.core.validation_manager import ValidationConfig, ValidationContext
from fiberq.utils.measure import clear_cache, ground_length

LAT, LON = 43.32, 21.90
SCALE = 1.0 / math.cos(math.radians(LAT))


@pytest.fixture
def project():
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    prj.setEllipsoid("EPSG:7030")
    clear_cache()
    yield prj
    clear_cache()


def _line(length_map_units=1000.0):
    xform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsCoordinateTransformContext())
    start = xform.transform(QgsPointXY(LON, LAT))
    return QgsGeometry.fromPolylineXY(
        [start, QgsPointXY(start.x() + length_map_units, start.y())])


def _layer(project, name, fields, rows, crs="EPSG:3857"):
    """A FiberQ line layer whose canonical name resolves, with `rows` features.

    `rows` is a list of (geometry, {field: value}).
    """
    layer = QgsVectorLayer(f"LineString?crs={crs}", name, "memory")
    assert layer.isValid()
    layer.dataProvider().addAttributes(
        [QgsField(f, QVariant.Double) for f in fields])
    layer.updateFields()

    feats = []
    for geom, attrs in rows:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        for key, value in attrs.items():
            feat.setAttribute(key, value)
        feats.append(feat)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    project.addMapLayer(layer)
    return layer


def _route(project, rows):
    return _layer(project, "Route", ["duzina", "duzina_km"], rows)


def _cables(project, rows):
    return _layer(project, "Aerial cables",
                  ["duzina_m", "slack_m", "total_len_m"], rows)


def _d3_messages(project):
    ctx = ValidationContext(project, ValidationConfig())
    return list(vr._check_length_coherence(ctx))


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def test_plan_finds_a_planar_length_and_proposes_the_ground_one(project):
    geom = _line()
    _route(project, [(geom, {"duzina": geom.length()})])  # the old, wrong value

    plan = plan_recalculation(project)

    change = next(c for c in plan.changes if c.field_name == "duzina")
    assert change.old_value == pytest.approx(geom.length())
    assert change.new_value == pytest.approx(ground_length(geom, project=project))
    assert change.ratio == pytest.approx(SCALE, rel=0.01)


def test_plan_writes_nothing(project):
    geom = _line()
    layer = _route(project, [(geom, {"duzina": geom.length()})])

    plan_recalculation(project)

    assert next(layer.getFeatures()).attribute("duzina") == pytest.approx(geom.length())
    assert not layer.isEditable()


def test_correct_lengths_produce_an_empty_plan(project):
    geom = _line()
    correct = ground_length(geom, project=project)
    _route(project, [(geom, {"duzina": correct,
                             "duzina_km": round(correct / 1000.0, 2)})])

    plan = plan_recalculation(project)

    assert not plan
    assert plan.layers_seen  # it did look, it just found nothing


def test_plan_counts_features_not_attributes(project):
    """One feature with a wrong metre AND a wrong km value is still one feature."""
    geom = _line()
    _route(project, [(geom, {"duzina": geom.length(), "duzina_km": 99.0})])

    plan = plan_recalculation(project)

    assert len(plan.changes) == 2
    assert plan.feature_count == 1


def test_null_stored_length_is_treated_as_needing_a_value(project):
    _route(project, [(_line(), {})])
    assert any(c.field_name == "duzina" for c in plan_recalculation(project).changes)


def test_empty_geometry_is_left_alone(project):
    """E2 reports the broken geometry; there is nothing to measure here."""
    _route(project, [(QgsGeometry(), {"duzina": 123.0})])
    assert not plan_recalculation(project).changes


def test_unmeasurable_layer_is_skipped_not_guessed(project):
    """Degrees must never be written into a metre field."""
    project.setEllipsoid("NONE")
    clear_cache()
    geom = QgsGeometry.fromPolylineXY(
        [QgsPointXY(LON, LAT), QgsPointXY(LON + 0.01, LAT)])
    _layer(project, "Route", ["duzina", "duzina_km"],
           [(geom, {"duzina": 810.0})], crs="EPSG:4326")

    plan = plan_recalculation(project)

    assert plan.skipped_layers == ["Route"]
    assert not plan.changes


def test_largest_change_is_reported_for_the_preview(project):
    _route(project, [
        (_line(100.0), {"duzina": 100.0}),
        (_line(5000.0), {"duzina": 5000.0}),
    ])
    biggest = plan_recalculation(project).largest_change()
    assert biggest.old_value == pytest.approx(5000.0, rel=1e-3)


# ---------------------------------------------------------------------------
# Derived fields
# ---------------------------------------------------------------------------

def test_km_field_follows_the_metre_field(project):
    geom = _line()
    layer = _route(project, [(geom, {"duzina": geom.length(), "duzina_km": 1.0})])

    recalculate_lengths(project)

    feat = next(layer.getFeatures())
    assert feat.attribute("duzina_km") == pytest.approx(
        round(feat.attribute("duzina") / 1000.0, 2))


def test_total_length_is_laid_length_plus_slack(project):
    geom = _line()
    layer = _cables(project, [(geom, {"duzina_m": geom.length(),
                                      "slack_m": 20.0,
                                      "total_len_m": geom.length() + 20.0})])

    recalculate_lengths(project)

    feat = next(layer.getFeatures())
    assert feat.attribute("total_len_m") == pytest.approx(
        feat.attribute("duzina_m") + 20.0)


def test_slack_is_never_rewritten(project):
    """Slack is a design decision, not something measurable from geometry."""
    geom = _line()
    layer = _cables(project, [(geom, {"duzina_m": geom.length(),
                                      "slack_m": 20.0,
                                      "total_len_m": 0.0})])

    plan = plan_recalculation(project)
    assert not any(c.field_name == "slack_m" for c in plan.changes)

    apply_recalculation(plan, project)
    assert next(layer.getFeatures()).attribute("slack_m") == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------

def test_apply_commits_the_new_values(project):
    geom = _line()
    layer = _route(project, [(geom, {"duzina": geom.length()})])

    outcome = apply_recalculation(plan_recalculation(project), project)

    assert not outcome.failures
    assert outcome.feature_count == 1
    stored = next(layer.getFeatures()).attribute("duzina")
    assert stored == pytest.approx(ground_length(geom, layer, project=project))
    assert not layer.isEditable()  # committed, not left open


def test_apply_leaves_no_edit_session_open_on_an_empty_plan(project):
    layer = _route(project, [(_line(), {"duzina": 0.0})])
    layer.rollBack()
    apply_recalculation(plan_recalculation(project), project)
    assert not layer.isEditable()


def test_a_missing_layer_is_a_failure_not_a_crash(project):
    geom = _line()
    layer = _route(project, [(geom, {"duzina": geom.length()})])
    plan = plan_recalculation(project)
    project.removeMapLayer(layer.id())

    outcome = apply_recalculation(plan, project)

    assert outcome.failures
    assert not outcome.applied


# ---------------------------------------------------------------------------
# The contract with D3
# ---------------------------------------------------------------------------

def test_recalculating_clears_every_d3_finding(project):
    """The whole point: run this, and the rule that prompted it goes quiet."""
    geom = _line()
    _route(project, [(geom, {"duzina": geom.length(), "duzina_km": 9.9})])
    _cables(project, [(geom, {"duzina_m": geom.length(),
                              "slack_m": 10.0,
                              "total_len_m": 1.0})])
    assert _d3_messages(project), "fixture must actually be broken first"

    recalculate_lengths(project)

    assert _d3_messages(project) == []


def test_recalculation_is_idempotent(project):
    geom = _line()
    layer = _route(project, [(geom, {"duzina": geom.length()})])

    recalculate_lengths(project)
    first = next(layer.getFeatures()).attribute("duzina")
    second_run = recalculate_lengths(project)

    assert not second_run.applied  # nothing left to do
    assert next(layer.getFeatures()).attribute("duzina") == pytest.approx(first)


def test_the_fix_and_the_rule_share_one_tolerance(project):
    """A drift between them would leave findings that recalculating cannot clear."""
    from fiberq.core import length_manager as lm

    assert lm.STORED_LENGTH_FIELD == vr._STORED_LENGTH_FIELD
    assert "config.length_abs_tol" in inspect.getsource(lm._disagrees)
    assert "config.length_rel_tol" in inspect.getsource(lm._disagrees)


# ---------------------------------------------------------------------------
# Plugin wiring (FiberQPlugin needs a live iface to instantiate)
# ---------------------------------------------------------------------------

def _called_names(func):
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                names.add(target.attr)
            elif isinstance(target, ast.Name):
                names.add(target.id)
    return names


def test_plugin_exposes_the_action(qgis_app):
    import fiberq.main_plugin as mp
    assert callable(getattr(mp.FiberQPlugin, "recalculate_lengths", None))


def test_the_user_is_asked_before_their_data_changes(qgis_app):
    """This rewrites attributes that may have been in the project for years."""
    import fiberq.main_plugin as mp

    called = _called_names(mp.FiberQPlugin.recalculate_lengths)
    assert "plan_recalculation" in called
    assert "apply_recalculation" in called
    assert "exec" in called  # the confirmation dialog

    src = inspect.getsource(mp.FiberQPlugin.recalculate_lengths)
    assert src.index("plan_recalculation(") < src.index("QMessageBox(")
    assert src.index("QMessageBox(") < src.index("apply_recalculation(")


def test_action_is_registered_for_cleanup(qgis_app):
    import fiberq.main_plugin as mp

    src = inspect.getsource(mp.FiberQPlugin.initGui)
    assert "self.actions.append(self.action_recalc_lengths)" in src
    assert "self.action_recalc_lengths.triggered.connect(self.recalculate_lengths)" in src
    # Menu-only: it edits data, so it should not be one stray click on the toolbar.
    assert "self.toolbar.addAction(self.action_recalc_lengths)" not in src
