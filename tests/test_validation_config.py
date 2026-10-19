"""A project's validation settings live in the project and every run reads them.

Unclaimed fix (WP2 code), found in the v1.6.0 review. WP2's plan put the snap
tolerance, the length tolerances, per-rule enable/disable and per-rule severity
overrides in a project entry, ``FiberQPlugin/validation``, "so it travels with
the project". Nothing read or wrote that entry: ``ValidationConfig`` said "Not
persisted", and every run, the plugin's own included, used the defaults.

Now :meth:`ValidationConfig.from_project` reads the entry and
:meth:`ValidationConfig.save` writes it. A run with no config passed (the
plugin's) and the length recalculation both use it, so "recalculate, then
validate" still clears every D3 finding. A setting that cannot be used is named,
and its default stands in for it.
"""
import json

import pytest
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCoordinateTransformContext, QgsFeature, QgsField, QgsGeometry,
                       QgsPointXY, QgsProject, QgsVectorLayer)
from qgis.PyQt.QtCore import QVariant

from fiberq.core import validation_manager as vm
from fiberq.core.length_manager import plan_recalculation
from fiberq.utils.measure import clear_cache, ground_length


class _Entries:
    """Just the project-entry API, so the pure tests need no QgsProject."""

    def __init__(self, raw=None):
        self.entries = {} if raw is None else {vm.CONFIG_ENTRY: raw}

    def readEntry(self, scope, key, default=""):
        value = self.entries.get((scope, key))
        return (default, False) if value is None else (value, True)

    def writeEntry(self, scope, key, value):
        self.entries[(scope, key)] = value
        return True


# -- reading and writing ------------------------------------------------------------


def test_a_project_with_no_settings_uses_the_defaults():
    config = vm.ValidationConfig.from_project(_Entries())
    assert config == vm.ValidationConfig()
    assert config.problems == []


def test_saved_settings_are_read_back():
    store = _Entries()
    saved = vm.ValidationConfig(tol=2.5, length_rel_tol=0.02, length_abs_tol=1.0,
                                disabled_rules={"D3", "A2"},
                                severity_overrides={"C1": vm.Severity.INFO})
    assert saved.save(store)
    assert vm.ValidationConfig.from_project(store) == saved


def test_each_setting_that_cannot_be_used_is_named_and_the_others_are_kept():
    store = _Entries(json.dumps({
        "tol": "five", "length_rel_tol": 0.05, "length_abs_tol": -1,
        "disabled_rules": "D3",
        "severity_overrides": {"C1": "low", "B4": "INFO"},
    }))
    config = vm.ValidationConfig.from_project(store)
    assert config.tol == vm.ValidationConfig().tol
    assert config.length_rel_tol == 0.05
    assert config.length_abs_tol == vm.ValidationConfig().length_abs_tol
    assert config.disabled_rules == set()
    assert config.severity_overrides == {"B4": vm.Severity.INFO}
    named = " ".join(config.problems)
    for name in ("tol", "length_abs_tol", "disabled_rules", "severity_overrides.C1"):
        assert name in named, (name, config.problems)
    assert "length_rel_tol" not in named


@pytest.mark.parametrize("raw", ["{not json", "[1, 2]"])
def test_an_entry_that_is_not_a_json_object_gives_the_defaults_and_says_so(raw):
    config = vm.ValidationConfig.from_project(_Entries(raw))
    assert config.tol == vm.ValidationConfig().tol
    assert config.problems


# -- a run uses them ----------------------------------------------------------------


def _layer(name, fields, rows, crs="EPSG:3857"):
    uri = f"Point?crs={crs}" + "".join(f"&field={f}" for f in fields)
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid()
    features = []
    for attrs, point in rows:
        feature = QgsFeature(layer.fields())
        for key, value in attrs.items():
            feature.setAttribute(key, value)
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    return layer


def _cable_with_no_type():
    """A cable C1 flags (no type), with an identity B4 accepts."""
    return _layer("Underground cables",
                  ["fiberq_uuid:string", "tip:string", "broj_vlakana:integer"],
                  [({"fiberq_uuid": "u1", "tip": "", "broj_vlakana": 12}, QgsPointXY(0, 0))])


def test_a_run_follows_the_settings_the_project_keeps(qgis_app):
    project = QgsProject()
    project.addMapLayer(_cable_with_no_type())
    assert vm.ValidationConfig(disabled_rules={"B4"},
                               severity_overrides={"C1": vm.Severity.INFO}).save(project)

    result = vm.run_validation(project)

    c1 = [issue for issue in result.issues if issue.rule_id == "C1"]
    assert c1 and all(issue.severity == vm.Severity.INFO for issue in c1)
    assert "B4" in result.skipped_rules
    assert result.config_problems == []
    project.clear()


def test_a_rule_id_no_rule_has_is_reported(qgis_app):
    project = QgsProject()
    assert vm.ValidationConfig(disabled_rules={"D33"}).save(project)
    result = vm.run_validation(project)
    assert any("D33" in problem for problem in result.config_problems), result.config_problems
    project.clear()


def test_the_settings_travel_with_the_project_file(qgis_app, tmp_path):
    project = QgsProject()
    saved = vm.ValidationConfig(tol=1.5, disabled_rules={"E1"},
                                severity_overrides={"D3": vm.Severity.ERROR})
    assert saved.save(project)
    path = str(tmp_path / "design.qgz")
    assert project.write(path)
    project.clear()

    reopened = QgsProject()
    assert reopened.read(path)
    assert vm.ValidationConfig.from_project(reopened) == saved
    reopened.clear()


# -- and so does the length recalculation ----------------------------------------------


@pytest.fixture
def mercator(qgis_app):
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    prj.setEllipsoid("EPSG:7030")
    clear_cache()
    yield prj
    clear_cache()
    prj.clear()


def _route_three_percent_long(project):
    xform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                                   QgsCoordinateReferenceSystem("EPSG:3857"),
                                   QgsCoordinateTransformContext())
    start = xform.transform(QgsPointXY(21.90, 43.32))
    geom = QgsGeometry.fromPolylineXY([start, QgsPointXY(start.x() + 1000.0, start.y())])
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    layer.dataProvider().addAttributes([QgsField("duzina", QVariant.Double)])
    layer.updateFields()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(geom)
    feature.setAttribute("duzina", ground_length(geom, project=project) * 1.03)
    assert layer.dataProvider().addFeatures([feature])[0]
    project.addMapLayer(layer)


def test_the_length_recalculation_uses_the_projects_tolerance(mercator):
    _route_three_percent_long(mercator)
    assert plan_recalculation(mercator).changes, "premise: 3 % is outside the default 1 %"

    assert vm.ValidationConfig(length_rel_tol=0.05).save(mercator)

    assert not plan_recalculation(mercator).changes
    d3 = [i for i in vm.run_validation(mercator).issues if i.rule_id == "D3"]
    assert d3 == [], "D3 and the recalculation must read the same tolerance"
