"""The app runner's own test: each case runs headless, offscreen, in a child process.

tests/app/runner.py drives the real QGIS desktop app in the app stages (ci/app-smoke.sh). It answers the windows a
scenario expects; it fails the run on a window QGIS opens for a Python error and on any other window that waits for
an answer; it ends the run at its deadline; and it writes report.json, which ci/report.py reads. Here it drives
FakeIface's main window instead, through tests/app/selftest.py, so the test runs on every QGIS leg with no display.

Each case asserts the child's exit code and its RESULT line first, with the child's output in the message
(docs/testing.md), and then what report.json says.
"""
import json
import os

import pytest

from support.child import run_driver

SELFTEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "selftest.py")

#: report.json's keys at format 1: ci/report.py app-junit reads them.
REPORT_KEYS = {"runner", "start", "qgis", "qt", "python", "platform", "started", "seconds", "exit", "exit_reason",
               "steps", "expected", "checks", "windows", "screenshots", "notes", "expected_windows_left", "error",
               "memory", "log"}
CHECK_KEYS = {"id", "step", "name", "what", "expected", "seen", "ok", "t", "seconds"}
WINDOW_KEYS = {"step", "kind", "label", "class", "title", "text", "png", "t"}
SCREENSHOT_KEYS = {"step", "label", "file", "size", "dpr"}

#: The ids the pass case declares and records, in order.
PASS_IDS = ["question.answer", "waits.timer", "waits.log", "waits.holds", "end.windows"]


def _lines(out):
    """The lines of steps.jsonl, in order."""
    with open(out / "steps.jsonl", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def _events(out):
    """The events of steps.jsonl, in order."""
    return [line["event"] for line in _lines(out)]


def _png(out, name):
    return name is not None and os.path.getsize(out / name) > 0


def _says_pass(report, out):
    assert report["exit_reason"] == "passed" and report["error"] is None, report
    assert set(report) == REPORT_KEYS, sorted(set(report) ^ REPORT_KEYS)
    assert report["expected"] == PASS_IDS
    assert [(c["id"], c["ok"]) for c in report["checks"]] == [(i, True) for i in PASS_IDS], report["checks"]
    assert all(set(c) == CHECK_KEYS for c in report["checks"]), report["checks"]
    assert [(w["kind"], w["label"], w["class"]) for w in report["windows"]] == [
        ("expected", "question", "QMessageBox")], report["windows"]
    assert set(report["windows"][0]) == WINDOW_KEYS and _png(out, report["windows"][0]["png"]), report["windows"]
    shots = [s for s in report["screenshots"] if s["label"] == "main window"]
    assert len(shots) == 1 and set(shots[0]) == SCREENSHOT_KEYS, report["screenshots"]
    assert shots[0]["size"] == [800, 600] and _png(out, shots[0]["file"]), shots   # logical pixels, at any dpr
    assert report["expected_windows_left"] == []
    with open(out / "log.jsonl", encoding="utf-8") as fh:
        logged = [json.loads(line) for line in fh]
    assert [e["tag"] for e in logged if e["message"].startswith("UUID migration summary")] == ["FiberQ UUID"]
    events = _events(out)
    assert events[0] == "start" and events[-1] == "finish", events
    assert {"begin", "check", "window", "screenshot", "click"} <= set(events), events


def _says_fail(report, out):
    assert report["exit_reason"] == "a check failed", report["exit_reason"]
    failed = [c for c in report["checks"] if not c["ok"]]
    assert [(c["id"], c["expected"], c["seen"]) for c in failed] == [("waits.fails", True, False)], report["checks"]
    assert len(report["checks"]) == 5
    assert [(n["text"], n["last_error"]) for n in report["notes"]] == [
        ("a wait timed out after 300 ms: not_there", "LookupError: nothing there yet")], report["notes"]


def _says_unexpected(report, out):
    assert [(w["kind"], w["title"]) for w in report["windows"]] == [("unexpected", "Nobody expects this")]
    assert _png(out, report["windows"][0]["png"]), report["windows"]
    assert report["exit_reason"] == "an unexpected window: Nobody expects this", report["exit_reason"]


def _says_error_window(report, out):
    title = "An error has occurred while executing Python code:"
    assert [(w["kind"], w["class"], w["title"]) for w in report["windows"]] == [
        ("python error window", "QgsMessageViewer", title)], report["windows"]
    assert "Traceback" in report["windows"][0]["text"] and _png(out, report["windows"][0]["png"])
    assert report["exit_reason"] == "a Python error window: " + title, report["exit_reason"]


def _says_deadline(report, out):
    assert report["exit_reason"] == "the deadline passed (2 s) in step wait", report["exit_reason"]
    assert _events(out)[-2:] == ["deadline", "finish"]


def _says_raises(report, out):
    assert report["exit_reason"] == "the scenario raised: ValueError: a scenario that raises", report["exit_reason"]
    assert "ValueError: a scenario that raises" in report["error"], report["error"]


def _says_python_line(report, out):
    assert report["exit_reason"] == "a check failed", report["exit_reason"]
    failed = [c for c in report["checks"] if not c["ok"]]
    assert [c["id"] for c in failed] == ["log.no_python_lines"], report["checks"]
    assert [(e["tag"], e["message"]) for e in failed[0]["seen"]] == [
        ("Python error", "Traceback (most recent call last): a line the runner's selftest logs")], failed
    assert [n["text"] for n in report["notes"]] == [
        "a required check failed, so the run ends here: log.no_python_lines"], report["notes"]


def _says_answer_raises(report, out):
    reason = "the scenario raised: answer to question: LookupError: no button 'Maybe' in 'Question'"
    assert report["exit_reason"].startswith(reason), report["exit_reason"]
    assert [(w["kind"], w["label"]) for w in report["windows"]] == [("expected", "question")], report["windows"]
    assert report["windows"][0]["answer_error"].startswith("LookupError: no button 'Maybe'"), report["windows"]
    assert report["error"].startswith("answer to question:") and "LookupError" in report["error"], report["error"]


def _says_match_raises(report, out):
    reason = "the scenario raised: the window watch: RuntimeError: a match that raises"
    assert report["exit_reason"] == reason, report["exit_reason"]
    assert report["error"].startswith("the window watch:\n"), report["error"]
    assert "RuntimeError: a match that raises" in report["error"], report["error"]
    assert (report["windows"], report["expected_windows_left"]) == ([], ["question"]), report
    errors = [line for line in _lines(out) if line["event"] == "error"]
    assert [line["where"] for line in errors] == ["the window watch"], errors


def _says_undeclared_check(report, out):
    reason = "the scenario raised: ValueError: the check 'check.undeclared' is not declared in expect_checks()"
    assert report["exit_reason"] == reason, report["exit_reason"]
    assert report["expected"] == ["check.declared"], report["expected"]
    assert [(c["id"], c["ok"]) for c in report["checks"]] == [("check.declared", True)], report["checks"]


def _says_drop_down(report, out):
    reason = ("the scenario raised: ValueError: the button 'Drop-down' opens a drop-down: name its entry, "
              "r.entry(toolbar, label, entry)")
    assert report["exit_reason"] == reason, report["exit_reason"]
    assert "click" not in _events(out), _events(out)


#: Each case: (the exit code the runner ends with, its deadline in seconds, what report.json must say).
CASES = {
    "pass": (0, 30, _says_pass),
    "fail": (1, 30, _says_fail),
    "unexpected": (3, 30, _says_unexpected),
    "error_window": (3, 30, _says_error_window),
    "deadline": (4, 2, _says_deadline),
    "raises": (5, 30, _says_raises),
    "python_line": (1, 30, _says_python_line),
    "answer_raises": (5, 30, _says_answer_raises),
    "match_raises": (5, 30, _says_match_raises),
    "undeclared_check": (5, 30, _says_undeclared_check),
    "drop_down": (5, 30, _says_drop_down),
}


@pytest.mark.parametrize("case", list(CASES))
def test_runner_case(case, tmp_path):
    """One case, in a child process: its exit code and RESULT line, then what report.json says."""
    code, deadline_s, says = CASES[case]
    (tmp_path / "options.json").write_text(json.dumps({"case": case, "deadline_s": deadline_s}), encoding="utf-8")
    returncode, result, output = run_driver(tmp_path, SELFTEST)
    assert returncode == code and result is not None, output
    out = tmp_path / "out"
    with open(out / "report.json", encoding="utf-8") as fh:
        report = json.load(fh)
    assert (report["runner"], report["start"], report["exit"]) == (1, "selftest", code), output
    failed = [c for c in report["checks"] if not c["ok"]]
    assert (result["exit"], result["failed"], result["checks"]) == (code, len(failed), len(report["checks"])), output
    assert os.path.samefile(result["report"], out / "report.json"), result
    says(report, out)
