"""Tests for the WP2 validation results panel and its wiring in main_plugin.

The panel is deliberately logic-free -- it renders a ValidationResult and emits
signals -- so it can be built and driven without a project, which is what these
tests do. The plugin-side wiring is checked at source level, because FiberQPlugin
needs a live iface and the whole initGui chain to instantiate (same approach as
tests/test_stray_poles_layer.py).
"""
import ast
import inspect
import textwrap

from fiberq.core import validation_manager as vm
from fiberq.ui.validation_panel import ValidationPanel


def _issue(rule_id="A1", severity=vm.Severity.WARNING, layer="Underground cables",
           fid=1, message="something is off", where=(10.0, 20.0)):
    return vm.ValidationIssue(
        rule_id=rule_id, severity=severity, category="topology",
        message=message, layer_name=layer, layer_id=f"{layer}_id",
        feature_id=fid, where=where,
    )


def _result(issues, rule_errors=None):
    result = vm.ValidationResult(project_name="t", crs="EPSG:3857")
    result.issues = list(issues)
    result.rule_errors = list(rule_errors or [])
    return result


def _rows(panel):
    return [panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())]


def _visible(panel):
    return [r for r in _rows(panel) if not r.isHidden()]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def test_panel_builds_without_a_project(qgis_app):
    panel = ValidationPanel()
    assert panel.objectName() == "FiberQValidationPanel"
    assert panel.tree.topLevelItemCount() == 0
    assert not panel.btn_export.isEnabled()


def test_set_result_populates_rows(qgis_app):
    panel = ValidationPanel()
    panel.set_result(_result([
        _issue(rule_id="A1"),
        _issue(rule_id="B4", severity=vm.Severity.ERROR, layer="ODF"),
    ]))
    assert len(_rows(panel)) == 2
    assert panel.btn_export.isEnabled()


def test_errors_sort_above_warnings(qgis_app):
    """sorted_issues() puts the most severe first, and the panel keeps that."""
    panel = ValidationPanel()
    panel.set_result(_result([
        _issue(rule_id="A1", severity=vm.Severity.INFO),
        _issue(rule_id="B4", severity=vm.Severity.ERROR),
        _issue(rule_id="C1", severity=vm.Severity.WARNING),
    ]))
    assert [r.text(1) for r in _rows(panel)] == ["B4", "C1", "A1"]


def test_summary_reports_counts(qgis_app):
    panel = ValidationPanel()
    panel.set_result(_result([
        _issue(severity=vm.Severity.ERROR),
        _issue(severity=vm.Severity.WARNING),
        _issue(severity=vm.Severity.WARNING),
    ]))
    text = panel.lbl_summary.text()
    assert "1" in text and "2" in text


def test_clean_result_says_so(qgis_app):
    panel = ValidationPanel()
    panel.set_result(_result([]))
    assert "No issues" in panel.lbl_summary.text()


def test_failed_rules_are_surfaced(qgis_app):
    """A rule that blew up must be visible, not silently absent."""
    panel = ValidationPanel()
    panel.set_result(_result([_issue()], rule_errors=["A1: boom"]))
    assert "1" in panel.lbl_summary.text()


def test_set_result_none_clears(qgis_app):
    panel = ValidationPanel()
    panel.set_result(_result([_issue()]))
    panel.set_result(None)
    assert _rows(panel) == []
    assert not panel.btn_export.isEnabled()


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def test_severity_filter_hides_other_rows(qgis_app):
    panel = ValidationPanel()
    panel.set_result(_result([
        _issue(rule_id="B4", severity=vm.Severity.ERROR),
        _issue(rule_id="A1", severity=vm.Severity.WARNING),
        _issue(rule_id="A2", severity=vm.Severity.INFO),
    ]))
    index = panel.cb_severity.findData(vm.Severity.ERROR.value)
    panel.cb_severity.setCurrentIndex(index)
    assert [r.text(1) for r in _visible(panel)] == ["B4"]


def test_layer_filter_hides_other_rows(qgis_app):
    panel = ValidationPanel()
    panel.set_result(_result([
        _issue(layer="ODF"),
        _issue(layer="Underground cables"),
    ]))
    panel.cb_layer.setCurrentIndex(panel.cb_layer.findData("ODF"))
    assert [r.text(2) for r in _visible(panel)] == ["ODF"]


def test_rule_filter_hides_other_rows(qgis_app):
    panel = ValidationPanel()
    panel.set_result(_result([_issue(rule_id="A1"), _issue(rule_id="D2")]))
    panel.cb_rule.setCurrentIndex(panel.cb_rule.findData("D2"))
    assert [r.text(1) for r in _visible(panel)] == ["D2"]


def test_filters_reset_to_all_shows_everything(qgis_app):
    panel = ValidationPanel()
    panel.set_result(_result([_issue(rule_id="A1"), _issue(rule_id="D2")]))
    panel.cb_rule.setCurrentIndex(panel.cb_rule.findData("D2"))
    panel.cb_rule.setCurrentIndex(0)  # "All"
    assert len(_visible(panel)) == 2


def test_filter_combos_only_offer_present_values(qgis_app):
    """No point offering a layer filter for a layer with no issues."""
    panel = ValidationPanel()
    panel.set_result(_result([_issue(layer="ODF")]))
    layers = [panel.cb_layer.itemData(i) for i in range(panel.cb_layer.count())]
    assert "Underground cables" not in layers
    assert "ODF" in layers


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def test_activating_a_row_emits_the_issue(qgis_app):
    panel = ValidationPanel()
    issue = _issue(rule_id="A3")
    panel.set_result(_result([issue]))

    seen = []
    panel.issueActivated.connect(seen.append)
    panel._on_item_activated(_rows(panel)[0])

    assert len(seen) == 1
    assert seen[0].rule_id == "A3"


def test_rerun_button_emits(qgis_app):
    panel = ValidationPanel()
    fired = []
    panel.rerunRequested.connect(lambda: fired.append(True))
    panel.btn_rerun.click()
    assert fired == [True]


def test_busy_state_disables_rerun(qgis_app):
    panel = ValidationPanel()
    panel.set_busy(True)
    assert not panel.btn_rerun.isEnabled()
    panel.set_busy(False)
    assert panel.btn_rerun.isEnabled()


# ---------------------------------------------------------------------------
# Plugin wiring (source level -- FiberQPlugin needs a live iface to build)
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


def test_plugin_exposes_the_validation_entry_points(qgis_app):
    import fiberq.main_plugin as mp

    for name in ("run_validation", "_ensure_validation_panel", "_zoom_to_issue"):
        assert callable(getattr(mp.FiberQPlugin, name, None)), name


def test_trigger_stays_thin(qgis_app):
    """All rule logic must live in validation_manager, not in the monolith."""
    import fiberq.main_plugin as mp

    src = inspect.getsource(mp.FiberQPlugin.run_validation)
    assert "run_validation as _run" in src
    # The trigger must not start reimplementing checks.
    assert "getFeatures" not in src
    assert "QgsSpatialIndex" not in src


def test_dock_is_removed_on_unload(qgis_app):
    """iface.addDockWidget is not covered by the self.actions cleanup loop, so
    unload must take the panel down explicitly or a reload leaves a dead dock."""
    import fiberq.main_plugin as mp

    assert "removeDockWidget" in _called_names(mp.FiberQPlugin.unload)


def test_validate_action_is_registered_for_cleanup(qgis_app):
    """Appending to self.actions is what gets the menu entry and toolbar icon
    removed on unload."""
    import fiberq.main_plugin as mp

    src = inspect.getsource(mp.FiberQPlugin.initGui)
    assert "self.action_validate" in src
    assert "self.actions.append(self.action_validate)" in src
    assert "self.action_validate.triggered.connect(self.run_validation)" in src


def test_panel_strings_use_the_class_context(qgis_app):
    """The context must equal the class name or every string silently reverts to
    English at runtime (docs/i18n.md, the tr() context trap)."""
    import fiberq.ui.validation_panel as vp

    src = inspect.getsource(vp)
    assert "QCoreApplication.translate(\n            'ValidationPanel'" in src \
        or "'ValidationPanel', message" in src
    # A module-level tr() helper is the trap the docs warn about.
    assert "\ndef tr(" not in src
