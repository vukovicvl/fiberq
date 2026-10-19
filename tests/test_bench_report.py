"""tools/bench/bench_report.py: the rules docs/performance.md's verdicts come from.

A published "x20 faster" is only as good as the rule that produced it, so the
rule is pinned here on synthetic result files: a change is shown only outside
the hull of both v1.5.0 runs' median +/- MAD, and only when every run computed
the same result. Pure stdlib, no QGIS.
"""
import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent

# Loaded by path: tools/bench is not a package, and nothing here needs sys.path.
_SPEC = importlib.util.spec_from_file_location("bench_report", REPO / "tools" / "bench" / "bench_report.py")
report = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(report)


def _row(raw, kind, scenario, median=None, mad=0.0, status="ok", digest="same", control=False,
         detail=None, size="S", image="344"):
    folder = raw / ("%s-qgis%s-%s" % (kind, image, size))
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"scenario": scenario, "status": status, "result_digest": digest, "control": control,
               "timing": None if median is None else {"median_s": median, "mad_s": mad, "cold_s": median}}
    if detail:
        payload["detail"] = detail
    (folder / ("%s-%s.json" % (scenario, size))).write_text(json.dumps(payload), encoding="utf-8")


def _verdicts(raw):
    _text, summary = report.report(str(raw))
    return summary["344-S"]


def test_a_change_outside_both_v150_runs_is_shown_with_its_factor(tmp_path):
    _row(tmp_path, "final-v150-a1", "schematic_open", 20.0, 0.3)
    _row(tmp_path, "final-v150-a2", "schematic_open", 21.0, 0.3)
    _row(tmp_path, "final-v160", "schematic_open", 1.0, 0.02)
    assert _verdicts(tmp_path)["schematic_open"]["verdict"] == "x20 faster"


def test_a_v160_range_touching_the_v150_hull_is_no_measurable_change(tmp_path):
    # A1 3.20 +/- 0.05 and A2 3.30 +/- 0.05: the hull is 3.15 .. 3.35.
    _row(tmp_path, "final-v150-a1", "run_validation", 3.20, 0.05, control=True)
    _row(tmp_path, "final-v150-a2", "run_validation", 3.30, 0.05, control=True)
    _row(tmp_path, "final-v160", "run_validation", 3.10, 0.06, control=True)
    verdict = _verdicts(tmp_path)["run_validation"]
    assert verdict["verdict"] == "no measurable change"
    assert verdict["control"] is True


def test_a_slower_row_is_said_to_be_slower(tmp_path):
    _row(tmp_path, "final-v150-a1", "snap_move_closure", 0.010, 0.0002)
    _row(tmp_path, "final-v150-a2", "snap_move_closure", 0.011, 0.0002)
    _row(tmp_path, "final-v160", "snap_move_closure", 0.020, 0.0003)
    assert _verdicts(tmp_path)["snap_move_closure"]["verdict"] == "x1.9 slower"


def test_a_small_change_reads_as_a_percentage(tmp_path):
    _row(tmp_path, "final-v150-a1", "save_gpkg", 2.25, 0.01, control=True)
    _row(tmp_path, "final-v150-a2", "save_gpkg", 2.25, 0.01, control=True)
    _row(tmp_path, "final-v160", "save_gpkg", 2.32, 0.01, control=True)
    assert _verdicts(tmp_path)["save_gpkg"]["verdict"] == "3% slower"


def test_rows_whose_results_differ_are_never_given_a_factor(tmp_path):
    _row(tmp_path, "final-v150-a1", "bom_open", 2.0, 0.01, digest="old")
    _row(tmp_path, "final-v150-a2", "bom_open", 2.0, 0.01, digest="old")
    _row(tmp_path, "final-v160", "bom_open", 0.5, 0.01, digest="new")
    verdict = _verdicts(tmp_path)["bom_open"]
    assert verdict["verdict"] == "not comparable"
    assert "result digests differ" in verdict["notes"]


def test_a_v150_did_not_finish_is_reported_as_such(tmp_path):
    for kind in ("final-v150-a1", "final-v150-a2"):
        _row(tmp_path, kind, "latent_open", status="dnf", detail="over the 1800 s budget", size="L")
    _row(tmp_path, "final-v160", "latent_open", 4.0, 0.1, size="L")
    _text, summary = report.report(str(tmp_path))
    verdict = summary["344-L"]["latent_open"]
    assert verdict["verdict"] == "v1.5.0 did not finish"
    assert verdict["v150_a1"] == "did not finish in 30 min"


def test_drift_between_the_v150_runs_or_from_the_baseline_is_flagged(tmp_path):
    _row(tmp_path, "baseline-v150", "route_correction", 5.4, 0.1)
    _row(tmp_path, "final-v150-a1", "route_correction", 5.5, 0.1)
    _row(tmp_path, "final-v150-a2", "route_correction", 6.6, 0.1)
    _row(tmp_path, "final-v160", "route_correction", 0.2, 0.01)
    notes = _verdicts(tmp_path)["route_correction"]["notes"]
    assert any("apart" in note for note in notes), notes
    assert any("off the baseline" in note for note in notes), notes


def test_the_middle_column_is_shown_only_on_the_rows_it_isolates(tmp_path):
    for kind, seconds in (("final-v150-a1", 0.8), ("final-v150-a2", 0.8), ("final-v160", 0.05),
                          ("final-mid-pf5", 0.7)):
        _row(tmp_path, kind, "snap_move_route", seconds, 0.01)
    _row(tmp_path, "final-mid-pf5", "lay_cable", 0.3, 0.01)
    text, _summary = report.report(str(tmp_path))
    route_line = next(line for line in text.splitlines() if "`snap_move_route`" in line)
    assert "PF-5's parent" in route_line and "700 ms" in route_line
    assert "(v1.6.0 x14 faster)" in route_line
    assert "`lay_cable`" not in text, "a row with no v1.5.0 or v1.6.0 run is not a row of the table"


def test_durations_read_the_way_a_person_reads_them():
    assert report.fmt(0.00123) == "1.23 ms"
    assert report.fmt(24.61) == "24.6 s"
    assert report.fmt(1045.3) == "17 min 25 s"
    assert report.fmt(1800.0) == "30 min"


def test_the_middle_column_compares_when_v150_computed_something_else(tmp_path):
    """The U2 snap fix changed what v1.5.0's element tool snaps to; PF-5's parent already has it."""
    _row(tmp_path, "final-v150-a1", "snap_move_element", 0.596, 0.01, digest="v150")
    _row(tmp_path, "final-v150-a2", "snap_move_element", 0.534, 0.01, digest="v150")
    _row(tmp_path, "final-mid-pf5", "snap_move_element", 0.547, 0.01, digest="fixed")
    _row(tmp_path, "final-v160", "snap_move_element", 0.0178, 0.0003, digest="fixed")
    verdict = _verdicts(tmp_path)["snap_move_element"]
    assert verdict["verdict"] == "not comparable"
    assert verdict["middle"]["verdict"] == "x31 faster"
