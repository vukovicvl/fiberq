"""Tests for the error-reporting helper.

Three of the four defects these pin down were in the first draft of
``fiberq/utils/errors.py``, which is the argument for the file existing: a
reporting helper that is wrong reports the wrong thing confidently, and the
failures it mishandles are by definition the ones nobody is watching.

* :func:`test_report_pushes_each_problem_once` -- ``report()`` did not remember
  what it had pushed, so the documented "report, then carry on" pattern showed
  the user the same failure twice.
* :func:`test_a_layer_that_cannot_commit_is_named` -- a raster reaching a
  per-layer save loop has no ``commitChanges()`` at all, and the resolved layer
  name was being discarded in exactly that path. In a loop over every project
  layer, the name is the only part of the message worth reading.
* :func:`test_a_layer_not_in_edit_mode_says_so` -- the friendlier sentence was
  unreachable, because QGIS fills ``commitErrors()`` with its own untranslated
  "ERROR: layer not editable" and the fold won.
* :func:`test_many_commit_errors_fold_to_a_readable_line` -- a GeoPackage
  trigger that rejects twenty thousand features answers with twenty thousand
  near-identical lines. Folding them with a list membership test was quadratic:
  1.6 seconds, on the UI thread, while reporting an error.

``absorb`` is tested hardest of all. It exists so a Qt slot can report instead
of raising, and a context manager that swallows is one typo away from being the
very thing this module was written to stop.
"""
import time

import pytest
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer

from fiberq.utils.errors import (
    OperationErrors,
    check_commit,
    describe,
    report_error,
)
from fiberq.utils import errors as errors_module

TAIL = "See Log Messages > FiberQ for the details."


class FakeBar:
    """Records what reached the message bar, in order."""

    def __init__(self):
        self.pushed = []

    def pushWarning(self, title, text):
        self.pushed.append((title, text))


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar


@pytest.fixture
def iface():
    return FakeIface()


@pytest.fixture
def layer():
    made = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer", "Poles", "memory")
    assert made.isValid()
    return made


def _one_point(target, x=1.0, y=2.0, fid=1):
    feature = QgsFeature(target.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
    feature.setAttribute("id", fid)
    return feature


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("problem, expected", [
    (ValueError("bad crs"), "ValueError: bad crs"),
    (RuntimeError(), "RuntimeError"),
    ("the file is read-only", "the file is read-only"),
    ("", "''"),
    (7, "7"),
])
def test_describe_keeps_the_exception_type(problem, expected):
    """An empty message is common in Qt and OGR errors; the type is what is left."""
    assert describe(problem) == expected


# ---------------------------------------------------------------------------
# the one line the user reads
# ---------------------------------------------------------------------------

def test_nothing_failed_says_nothing():
    assert OperationErrors("Save all layers").message() == ""


def test_one_problem_names_the_part_that_failed():
    errors = OperationErrors("Save all layers")
    errors.add("Poles", "the file is read-only")
    assert errors.message() == f"Poles: the file is read-only. {TAIL}"


def test_many_problems_are_one_line_with_a_count():
    """Twelve failed layers must not be twelve pop-ups."""
    errors = OperationErrors("Save all layers")
    for name in ("Poles", "Routes", "Cables"):
        errors.add(name, "the file is read-only")
    assert errors.message() == f"Poles: the file is read-only (+2 more). {TAIL}"


def test_a_failure_with_no_part_to_name_just_says_what_happened():
    errors = OperationErrors("Lay cable")
    errors.add(None, ValueError("no path"))
    assert errors.message() == f"ValueError: no path. {TAIL}"


def test_failed_is_true_as_soon_as_anything_is_added():
    errors = OperationErrors("Save all layers")
    assert not errors.failed
    errors.add("Poles", "locked")
    assert errors.failed
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def test_report_pushes_each_problem_once(iface):
    """The regression: report() did not remember what it had already said."""
    errors = OperationErrors("Auto-save", iface)
    errors.add("Poles", "locked")

    assert errors.report() is True
    assert len(iface.bar.pushed) == 1

    assert errors.report() is False
    assert len(iface.bar.pushed) == 1

    errors.add("Routes", "locked")
    assert errors.report() is True
    assert iface.bar.pushed[-1] == ("Auto-save", f"Routes: locked. {TAIL}")


def test_reporting_by_hand_and_then_leaving_the_block_says_it_once(iface):
    with OperationErrors("Export", iface) as errors:
        errors.add("Poles", "locked")
        errors.report()
    assert len(iface.bar.pushed) == 1


def test_the_entry_is_titled_with_the_operation(iface):
    with OperationErrors("Save all layers", iface) as errors:
        errors.add("Poles", "locked")
    assert iface.bar.pushed[0][0] == "Save all layers"


def test_without_an_interface_it_logs_and_does_not_raise():
    """Headless runs and processing algorithms must not fail on the report."""
    errors = OperationErrors("Headless", None)
    errors.add("Poles", RuntimeError("boom"))
    assert errors.report() is True


def test_report_error_is_the_one_off_form(iface):
    report_error("BOM export", "bom.xlsx", OSError("read-only"), iface)
    assert iface.bar.pushed == [
        ("BOM export", f"bom.xlsx: OSError: read-only. {TAIL}")]


def test_a_message_bar_that_throws_does_not_break_the_operation(iface):
    def angry(title, text):
        raise RuntimeError("the bar is gone")

    iface.bar.pushWarning = angry
    errors = OperationErrors("Save all layers", iface)
    errors.add("Poles", "locked")
    assert errors.report() is True


# ---------------------------------------------------------------------------
# absorb
# ---------------------------------------------------------------------------

def test_by_default_an_exception_is_reported_and_still_raised(iface):
    with pytest.raises(TypeError):
        with OperationErrors("Lay cable", iface):
            raise TypeError("no path")
    assert iface.bar.pushed[0][1] == f"TypeError: no path. {TAIL}"


def test_absorb_reports_instead_of_raising(iface):
    with OperationErrors("Lay cable", iface, absorb=True) as errors:
        raise TypeError("no path")
    assert errors.failed
    assert len(iface.bar.pushed) == 1


@pytest.mark.parametrize("escape", [KeyboardInterrupt, SystemExit])
def test_absorb_never_swallows_an_interrupt(iface, escape):
    """Ctrl+C and interpreter shutdown are not ours to report."""
    with pytest.raises(escape):
        with OperationErrors("Lay cable", iface, absorb=True):
            raise escape()


def test_a_block_that_finishes_cleanly_reports_nothing(iface):
    with OperationErrors("Save all layers", iface) as errors:
        pass
    assert not errors.failed
    assert iface.bar.pushed == []


# ---------------------------------------------------------------------------
# check_commit
# ---------------------------------------------------------------------------

def test_a_good_commit_is_silent(layer, iface):
    layer.startEditing()
    layer.addFeature(_one_point(layer))
    errors = OperationErrors("Save all layers", iface)

    assert check_commit(layer, errors) is True
    assert errors.problems == []
    assert layer.featureCount() == 1


def test_a_layer_not_in_edit_mode_says_so(layer, iface):
    """QGIS's own words here are "ERROR: layer not editable", untranslated."""
    errors = OperationErrors("Save all layers", iface)

    assert check_commit(layer, errors) is False
    assert errors.problems == [("Poles", "the layer was not in edit mode")]


def test_a_failed_commit_is_not_rolled_back(layer, iface):
    """The edits stay buffered so the user can clear the cause and save again."""
    layer.startEditing()
    layer.addFeature(_one_point(layer))
    layer.commitChanges()

    errors = OperationErrors("Save all layers", iface)
    assert check_commit(layer, errors) is False
    assert layer.featureCount() == 1


def test_a_layer_that_cannot_commit_is_named(iface):
    """A raster in a per-layer loop has no commitChanges() at all."""
    class Raster:
        def name(self):
            return "Orthophoto 2024"

    errors = OperationErrors("Save all layers", iface)
    assert check_commit(Raster(), errors) is False
    assert errors.problems[0][0] == "Orthophoto 2024"
    assert "AttributeError" in errors.problems[0][1]


def test_an_explicit_name_wins(layer, iface):
    errors = OperationErrors("Save all layers", iface)
    check_commit(layer, errors, what="the pole layer")
    assert errors.problems[0][0] == "the pole layer"


def test_many_commit_errors_fold_to_a_readable_line():
    """20,000 rejected features used to take 1.6 s and 1.5 MB, on the UI thread."""
    class Rejecting:
        def isEditable(self):
            return True

        def commitErrors(self):
            return [f"ERROR: feature {n} rejected" for n in range(20000)]

    started = time.monotonic()
    reason = errors_module._commit_reason(Rejecting())
    elapsed = time.monotonic() - started

    assert reason.count(";") == errors_module._MAX_REASONS
    assert reason.endswith("+19997 more")
    assert len(reason) < 200
    assert elapsed < 1.0, f"folding took {elapsed:.2f}s"


def test_duplicate_commit_errors_are_folded_once():
    class Repetitive:
        def isEditable(self):
            return True

        def commitErrors(self):
            return ["ERROR: locked\nERROR: locked", "ERROR: locked"]

    assert errors_module._commit_reason(Repetitive()) == "ERROR: locked"


def test_a_refusal_with_no_reason_still_says_something():
    class Mute:
        def isEditable(self):
            return True

        def commitErrors(self):
            return []

    assert errors_module._commit_reason(Mute()) == (
        "QGIS refused the commit without saying why")
