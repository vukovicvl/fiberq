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
from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
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


# -- found in the final review of the 1.6.0 branch ----------------------------------------

@pytest.mark.parametrize("raw", [
    '{"tol": 1' + "0" * 400 + "}",          # an integer too large for a float
    "[" * 100000 + "]" * 100000,             # nesting deep enough to stop the parser
], ids=["huge-integer", "deep-nesting"])
def test_a_setting_that_breaks_the_reader_is_a_problem_not_a_crash(raw):
    """``math.isfinite`` raised OverflowError and ``json.loads`` RecursionError,
    so run_validation raised although it is documented never to."""
    config = vm.ValidationConfig.from_project(_Entries(raw))
    assert config.problems
    assert config.tol == vm.ValidationConfig().tol


def test_recalculate_says_which_settings_it_could_not_use(mercator):
    """It used the defaults for them without a word, while the validation run
    over the same project reported them."""
    mercator.writeEntry(*vm.CONFIG_ENTRY, json.dumps({"length_rel_tol": "five"}))
    plan = plan_recalculation(mercator)
    assert any("length_rel_tol" in problem for problem in plan.config_problems), (
        plan.config_problems)


# -- and the message bar shows the ones it could not use ----------------------------------

class _Iface:
    """What Validate project asks of iface: a real QgsMessageBar, so the message
    read as shown is the one QGIS shows."""

    def __init__(self):
        from qgis.gui import QgsMessageBar
        self.bar = QgsMessageBar()

    def messageBar(self):
        return self.bar


class _Panel:
    """Stands in for the results dock, which needs QGIS's main window."""

    result = None

    def set_busy(self, busy):
        pass

    def set_result(self, result):
        self.result = result

    def show(self):
        pass

    def raise_(self):
        pass


def _validate_project():
    """Validate project, as FiberQ's toolbar button runs it."""
    from fiberq.main_plugin import FiberQPlugin

    plugin = FiberQPlugin.__new__(FiberQPlugin)
    plugin.iface = _Iface()
    plugin._validation_panel = _Panel()
    FiberQPlugin.run_validation(plugin)
    return plugin.iface.bar, plugin._validation_panel.result


def _in_turn(bar):
    """The bar's messages as the user meets them, each (level, timeout, text): the
    one shown, then the one the bar shows when that is closed, and so on."""
    seen = []
    while bar.currentItem() is not None:
        item = bar.currentItem()
        seen.append((item.level(), item.duration(), item.text()))
        bar.popWidget()
    return seen


NOT_USED = ("Some of this project's validation settings could not be used, and the "
            "defaults stood in for them: ")


@pytest.fixture
def current_project(qgis_app):
    """QgsProject.instance(), the project Validate project reads."""
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    prj.removeEntry(*vm.CONFIG_ENTRY)
    yield prj
    prj.removeAllMapLayers()
    prj.removeEntry(*vm.CONFIG_ENTRY)


@pytest.mark.parametrize("entry, named", [
    ({"tol": "abc"}, "tol ('abc' is not a number >= 0)"),
    ({"disabled_rules": ["E22"]}, "E22 (no rule has this id)"),
], ids=["K3-tol", "rule-id-typo"])
def test_the_settings_it_could_not_use_are_the_message_the_bar_shows(current_project, entry, named):
    """QA finding Q26, step K.3: writeEntry('{"tol": "abc"}'), then Validate project.
    The warning was pushed before the summary, so the bar showed "2 error(s), 0
    warning(s), 0 info" and counted the warning as "1 more". A summary of errors is
    a warning, which never times out, and the bar's Close All dropped both."""
    current_project.addMapLayer(_layer("Underground cables", ["tip:string"],
                                       [({"tip": "x"}, QgsPointXY(0, 0))]))
    current_project.writeEntry(*vm.CONFIG_ENTRY, json.dumps(entry))

    bar, result = _validate_project()

    counts = result.counts_by_severity()
    assert counts["error"], "premise: a summary of errors, which is a warning"
    assert _in_turn(bar) == [
        (Qgis.MessageLevel.Warning, 0, NOT_USED + named),
        (Qgis.MessageLevel.Warning, 0,
         f"{counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info"),
    ]


def _issue(severity):
    return vm.ValidationIssue(rule_id="C1", severity=severity, category="completeness",
                              message="Required field(s) missing or empty: tip",
                              layer_name="Underground cables", layer_id="cables")


@pytest.mark.parametrize("issues, rule_errors, summary", [
    ([vm.Severity.ERROR], [], (Qgis.MessageLevel.Warning, "1 error(s), 0 warning(s), 0 info")),
    ([vm.Severity.WARNING], [], (Qgis.MessageLevel.Info, "0 error(s), 1 warning(s), 0 info")),
    ([], ["B1: boom"], (Qgis.MessageLevel.Warning,
                        "1 rule(s) failed to run; the rules that did found no issues")),
    ([], [], (Qgis.MessageLevel.Success, "Validation found no issues (2 rules, 0 layers).")),
], ids=["errors", "issues", "rules-failed", "no-issues"])
def test_the_settings_warning_is_shown_ahead_of_every_summary(qgis_app, monkeypatch,
                                                              issues, rule_errors, summary):
    """Each of the four summaries. An info or success summary used to cover the
    warning for its five seconds; without a setting it could not use, the summary
    is the only message, as before."""
    def bar_after(problems):
        result = vm.ValidationResult(project_name="t", crs="EPSG:3857")
        result.issues = [_issue(severity) for severity in issues]
        result.rule_errors = list(rule_errors)
        result.ran_rules = ["A1", "B1"]
        result.config_problems = list(problems)
        monkeypatch.setattr(vm, "run_validation", lambda **_kwargs: result)
        bar, _result = _validate_project()
        return [(level, text) for level, _timeout, text in _in_turn(bar)]

    assert bar_after([]) == [summary]
    assert bar_after(["tol ('abc' is not a number >= 0)"]) == [
        (Qgis.MessageLevel.Warning, NOT_USED + "tol ('abc' is not a number >= 0)"),
        summary,
    ]
