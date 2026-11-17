"""ci/report.py app-junit: the app stages' junit.xml and exit codes, from each QGIS start's records.

ci/app-smoke.sh starts the real QGIS desktop twice and hands each start's records to ``ci/report.py app-junit``:
report.json (tests/app/runner.py writes it), guard.json (the startup guard, tests/app/guard.py, when it ended
QGIS) and steps.jsonl, with the start's exit status, how long it ran and its time limit. app-junit writes one test
case per check, ``app.<start>::<check id>``, and ``app.<start>::run.ended``, which says how the start ended; it
prints each start's code, which ci/app-smoke.sh exits with. The code comes from the records, never from the exit
status alone: xvfb-run has exit codes of its own, and a crash leaves no report. These tests run it on synthetic
records, with no QGIS, and read back what it wrote: each asserts its exit code first, with its output in the
message, then the keys it printed and the test cases of junit.xml.
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(REPO_ROOT, "ci", "report.py")

#: The time limit of every start here, in seconds.
LIMIT = 280


def _check(cid, ok=True, expected=True, seen=True, what=""):
    """A check as report.json holds it."""
    step, name = cid.split(".")
    return {"id": cid, "step": step, "name": name, "what": what or "what " + cid, "expected": expected,
            "seen": seen, "ok": ok, "t": 1.0, "seconds": 0.25}


def _start(folder, checks=None, exit_code=0, reason=None, expected=None, runner=1, windows=(), error=None):
    """A start's records folder holding a report.json as the runner writes it; ``checks=None``: no report.json."""
    folder.mkdir()
    if checks is not None:
        report = {"runner": runner, "start": folder.name, "qgis": "4.2.3", "qt": "6.8.2", "python": "3.13.5",
                  "platform": "xcb", "started": "2026-11-17T12:00:00Z", "seconds": 9.5, "exit": exit_code,
                  "exit_reason": reason or {0: "passed", 1: "a check failed"}.get(exit_code, "exit %d" % exit_code),
                  "steps": [], "expected": [c["id"] for c in checks] if expected is None else expected,
                  "checks": checks, "windows": list(windows), "screenshots": [], "notes": [],
                  "expected_windows_left": [], "error": error, "memory": {}, "log": []}
        (folder / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return folder


def _app_junit(tmp_path, *groups, junit=None):
    """Run ci/report.py app-junit on the groups ``(start, folder, exit, seconds, limit)``: ``(exit code, keys,
    output, junit.xml path)``; junit.xml goes into ``tmp_path`` unless ``junit`` names another path."""
    junit = junit or tmp_path / "junit.xml"
    args = [sys.executable, "-I", REPORT, "app-junit", "app-42", str(junit)]
    for group in groups:
        args += [str(part) for part in group]
    done = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    out = done.stdout.decode("utf-8", "replace")
    output = "exit %d\nstdout:\n%s\nstderr:\n%s" % (done.returncode, out, done.stderr.decode("utf-8", "replace"))
    keys = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return done.returncode, keys, output, junit


def _cases(junit):
    """``{"<classname>::<name>": (passed|failed|skipped, message)}``: each test case of junit.xml."""
    found = {}
    for case in ET.parse(str(junit)).getroot().iter("testcase"):
        status, message = "passed", ""
        for child in case:
            status = {"failure": "failed", "skipped": "skipped"}.get(child.tag, child.tag)
            message = child.get("message", "")
        found["%s::%s" % (case.get("classname"), case.get("name"))] = (status, message)
    return found


def _text(junit, test_id):
    """The text of the failure of the test case ``test_id`` (``"<classname>::<name>"``) in junit.xml; ``""`` when
    it did not fail."""
    for case in ET.parse(str(junit)).getroot().iter("testcase"):
        if "%s::%s" % (case.get("classname"), case.get("name")) == test_id:
            failure = case.find("failure")
            return "" if failure is None else failure.text or ""
    raise KeyError(test_id)


def test_two_starts_that_pass(tmp_path):
    """Every check a test case that passes, run.ended passed, code 0, and the install start opens the gate."""
    install = _start(tmp_path / "install", [_check("install.installed"), _check("install.enabled")])
    workflow = _start(tmp_path / "workflow", [_check("load.loaded")])
    code, keys, output, junit = _app_junit(tmp_path, ("install", install, 0, 9, LIMIT),
                                           ("workflow", workflow, 0, 17, LIMIT))
    assert code == 0 and junit.is_file(), output
    assert _cases(junit) == {"app.install::install.installed": ("passed", ""),
                             "app.install::install.enabled": ("passed", ""),
                             "app.install::run.ended": ("passed", ""),
                             "app.workflow::load.loaded": ("passed", ""),
                             "app.workflow::run.ended": ("passed", "")}
    assert keys == {"install_code": "0", "install_gate": "yes", "workflow_code": "0",
                    "checks": "5", "checks_failed": "0", "checks_skipped": "0",
                    "install_checks": "3", "install_failed": "0", "install_failed_ids": "", "install_report": "yes",
                    "install_report_exit": "0", "install_verdict": "pass", "install_reason": "passed",
                    "workflow_checks": "2", "workflow_failed": "0", "workflow_failed_ids": "", "workflow_report": "yes",
                    "workflow_report_exit": "0", "workflow_verdict": "pass", "workflow_reason": "passed"}, output
    suite = ET.parse(str(junit)).getroot().find("testsuite")
    assert (suite.get("name"), suite.get("tests"), suite.get("failures"), suite.get("skipped")) == (
        "app-42", "5", "0", "0")


def test_a_failed_check_is_a_failure_with_what_was_expected(tmp_path):
    """A check that failed is a test case that failed, with what it checked, expected and saw; the start ended as
    the runner says it ends a start whose check failed, so run.ended passes, and the code is 1."""
    checks = [_check("install.installed"), _check("install.enabled"),
              _check("install.golden_entries", ok=False, expected=[], seen=["FiberQ Toolbar[5]: tooltip: ..."],
                     what="every entry")]
    install = _start(tmp_path / "install", checks, exit_code=1)
    code, keys, output, junit = _app_junit(tmp_path, ("install", install, 1, 9, LIMIT))
    assert code == 0 and junit.is_file(), output
    cases = _cases(junit)
    assert cases["app.install::install.golden_entries"] == (
        "failed", 'every entry: expected [], seen ["FiberQ Toolbar[5]: tooltip: ..."]'), cases
    assert cases["app.install::run.ended"] == ("passed", ""), cases
    assert (keys["install_code"], keys["install_verdict"], keys["install_failed_ids"], keys["install_gate"]) == (
        "1", "fail", "install.golden_entries", "yes"), output


def test_a_window_at_startup_leaves_the_guards_record(tmp_path):
    """A start the startup guard ended (exit 3, guard.json, no report.json): run.ended fails with the window's
    kind and title and the last step; code 3. The next start did not run: its run.ended is skipped, code 0."""
    install = _start(tmp_path / "install")
    guard = {"exit": 3, "kind": "python error window", "title": "Couldn't load plugin 'fiberq'",
             "text": "Traceback (most recent call last): ...", "png": "guard-window.png", "t": 4.9, "log_tail": []}
    (install / "guard.json").write_text(json.dumps(guard), encoding="utf-8")
    (install / "steps.jsonl").write_text(json.dumps({"event": "begin", "step": "install", "t": 2.4}) + "\n",
                                         encoding="utf-8")
    code, keys, output, junit = _app_junit(tmp_path, ("install", install, 3, 5, LIMIT),
                                           ("workflow", tmp_path / "workflow", "none", 0, LIMIT))
    assert code == 0 and junit.is_file(), output
    cases = _cases(junit)
    assert cases["app.install::run.ended"] == ("failed", (
        "QGIS ended with exit 3 and wrote no report.json (last step: install); the startup guard ended QGIS "
        "(python error window): Couldn't load plugin 'fiberq'")), cases
    assert cases["app.workflow::run.ended"] == (
        "skipped", "not run: FiberQ was not installed (install ended with exit 3)"), cases
    assert (keys["install_code"], keys["install_gate"], keys["install_report"], keys["workflow_code"],
            keys["workflow_verdict"], keys["checks"], keys["checks_failed"], keys["checks_skipped"]) == (
        "3", "no", "no", "0", "none", "2", "1", "1"), output


#: The start of run.ended's message for a start that wrote no report.json and recorded no step.
NO_REPORT = "QGIS ended with exit %d and wrote no report.json (last step: none recorded)"

#: Each case: (the start's exit status, the report's exit or None for no report.json, guard.json there, seconds
#: it ran, the code it gets, run.ended's outcome, what run.ended's message and its text both say when it failed).
CODES = {
    "passed": (0, 0, False, 20, 0, "passed", ""),
    "a_check_failed": (1, 1, False, 20, 1, "passed", ""),
    "a_window": (3, 3, False, 20, 3, "failed", "Select exactly 2 elements"),
    "the_guard": (3, None, True, 5, 3, "failed",
                  NO_REPORT % 3 + "; the startup guard ended QGIS (unexpected window): A window"),
    "the_deadline": (4, 4, False, 250, 4, "failed", "exit 4"),
    "the_scenario_raised": (5, 5, False, 20, 5, "failed", "ValueError: boom"),
    "the_time_limit": (124, None, False, LIMIT, 4, "failed", NO_REPORT % 124 + "; stopped by its time limit (280 s)"),
    "the_time_limit_killed": (137, None, False, LIMIT + 10, 4, "failed",
                              NO_REPORT % 137 + "; stopped by its time limit (280 s)"),
    "killed_before_the_limit": (137, None, False, 100, 6, "failed",
                                NO_REPORT % 137 + "; killed after 100 s, before its time limit (280 s)"),
    "a_crash": (134, None, False, 23, 6, "failed", NO_REPORT % 134),
    "xvfb_run_1_without_report": (1, None, False, 3, 6, "failed", NO_REPORT % 1),
    "xvfb_run_5_after_a_pass": (5, 0, False, 20, 6, "failed", "QGIS ended with exit 5, but the report says 0"),
    "a_3_without_records": (3, None, False, 1, 6, "failed", NO_REPORT % 3),
    "a_0_without_report": (0, None, False, 20, 6, "failed", NO_REPORT % 0),
}


@pytest.mark.parametrize("case", list(CODES))
def test_each_code_comes_from_the_evidence(case, tmp_path):
    """A start's code is its exit status only when its records confirm it; anything else is 6. When run.ended
    fails, its message says why, and so does its text, which a JUnit viewer shows."""
    raw, report_exit, guard, seconds, want, ended, said = CODES[case]
    folder = tmp_path / "workflow"
    if report_exit is None:
        _start(folder)
    else:
        checks = [_check("load.loaded"), _check("load.logged", ok=report_exit != 1)]
        windows = [{"step": "load", "kind": "unexpected", "label": "", "class": "QMessageBox", "title": "Oops",
                    "text": "Select exactly 2 elements", "png": None, "t": 3.0}] if report_exit == 3 else []
        error = "Traceback (most recent call last):\nValueError: boom" if report_exit == 5 else None
        _start(folder, checks, exit_code=report_exit, windows=windows, error=error)
    if guard:
        (folder / "guard.json").write_text(json.dumps({"exit": 3, "kind": "unexpected window", "title": "A window"}),
                                           encoding="utf-8")
    code, keys, output, junit = _app_junit(tmp_path, ("workflow", folder, raw, seconds, LIMIT))
    assert code == 0 and junit.is_file(), output
    assert keys["workflow_code"] == str(want), output
    status, message = _cases(junit)["app.workflow::run.ended"]
    text = _text(junit, "app.workflow::run.ended")
    assert status == ended, output
    if ended == "passed":
        assert (message, text) == ("", ""), output
    else:
        assert said in message and said in text, "message: %s\ntext:\n%s" % (message, text)
    assert keys["workflow_verdict"] == ("pass" if case == "passed" else "fail"), output


@pytest.mark.parametrize("case", ["after_a_pass", "after_a_required_check"])
def test_an_expected_check_that_did_not_run_fails_run_ended(case, tmp_path):
    """A check the start declared and did not record fails run.ended, by its id: a start that silently skipped a
    check never passes (after a pass, code 6), and one that a required check ended says what did not run."""
    if case == "after_a_pass":
        folder = _start(tmp_path / "workflow", [_check("load.loaded")], exit_code=0,
                        expected=["load.loaded", "load.logged"])
        raw, want = 0, ("6", "load.logged")
    else:
        folder = _start(tmp_path / "workflow", [_check("load.loaded", ok=False, expected=True, seen=False)],
                        exit_code=1, expected=["load.loaded", "load.logged", "end.windows"])
        raw, want = 1, ("1", "load.logged, end.windows")
    code, keys, output, junit = _app_junit(tmp_path, ("workflow", folder, raw, 20, LIMIT))
    assert code == 0 and junit.is_file(), output
    status, message = _cases(junit)["app.workflow::run.ended"]
    assert status == "failed" and message.endswith("did not run: " + want[1]), message
    assert (keys["workflow_code"], keys["workflow_verdict"]) == (want[0], "fail"), output


def test_a_gate_check_counts_as_expected(tmp_path):
    """The install start's gate checks (install.installed and install.enabled, APP_GATE in ci/report.py) count
    among its expected checks, declared or not. An install start that passed without install.enabled, as a tested
    tree whose check ids drifted from ci/'s would, fails run.ended by that id with code 6 and keeps the gate
    closed: the stage cannot pass with the workflow start not run."""
    install = _start(tmp_path / "install", [_check("install.installed")])
    code, keys, output, junit = _app_junit(tmp_path, ("install", install, 0, 9, LIMIT),
                                           ("workflow", tmp_path / "workflow", "none", 0, LIMIT))
    assert code == 0 and junit.is_file(), output
    cases = _cases(junit)
    assert cases["app.install::run.ended"] == (
        "failed", "passed; 1 expected check did not run: install.enabled"), cases
    assert cases["app.workflow::run.ended"] == (
        "skipped", "not run: FiberQ was not installed (install ended with exit 0)"), cases
    assert (keys["install_code"], keys["install_verdict"], keys["install_gate"], keys["workflow_code"]) == (
        "6", "fail", "no", "0"), output


def test_characters_xml_cannot_hold_are_escaped(tmp_path):
    """An escape sequence in a check's text and a lone surrogate in what it saw still give a junit.xml that
    parses, with each such character written as #xNN. A lone surrogate that no encoding can write, in the
    report's reason here, reaches the printed result.txt lines as a backslash escape."""
    checks = [_check("load.logged", ok=False, expected=[], seen=["bad \udc8b byte"], what="colour \x1b[31mred")]
    folder = _start(tmp_path / "workflow", checks, exit_code=1, reason="a check failed \ud800")
    code, keys, output, junit = _app_junit(tmp_path, ("workflow", folder, 1, 20, LIMIT))
    assert code == 0 and junit.is_file(), output
    status, message = _cases(junit)["app.workflow::load.logged"]
    assert (status, message) == ("failed", 'colour #x1B[31mred: expected [], seen ["bad #xDC8B byte"]'), message
    assert keys["workflow_reason"] == "a check failed \\ud800", output


#: Each case: a field of a passing report.json given another shape, and what app-junit says of it.
SHAPES = {"exit_not_a_number": ("exit", "0", "its exit is not a whole number"),
          "windows_not_a_list": ("windows", 7, "its windows are not a list"),
          "log_not_a_list": ("log", 5, "its log is not a list")}


@pytest.mark.parametrize("case", ["a_later_format", "not_json"] + list(SHAPES))
def test_a_report_it_cannot_read_is_named(case, tmp_path):
    """A report.json in a format this ci/ does not read, that does not parse, or that does not have its format's
    shape, is said to be exactly that."""
    if case == "a_later_format":
        folder = _start(tmp_path / "workflow", [_check("load.loaded")], runner=99)
        said = "report.json is runner format 99; this ci/ reads 1..1"
    elif case == "not_json":
        folder = _start(tmp_path / "workflow")
        (folder / "report.json").write_text('{"runner": 1, "checks": [', encoding="utf-8")
        said = "report.json does not parse: "
    else:
        folder = _start(tmp_path / "workflow", [_check("load.loaded")])
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        field, value, said = SHAPES[case]
        report[field] = value
        (folder / "report.json").write_text(json.dumps(report), encoding="utf-8")
        said = "report.json is not runner format 1: " + said
    code, keys, output, junit = _app_junit(tmp_path, ("workflow", folder, 0, 20, LIMIT))
    assert code == 0 and junit.is_file(), output
    status, message = _cases(junit)["app.workflow::run.ended"]
    assert status == "failed" and message.startswith("QGIS ended with exit 0; " + said), message
    assert (keys["workflow_code"], keys["workflow_report"]) == ("6", "bad"), output


def test_a_guard_log_tail_that_is_not_a_list_is_passed_over(tmp_path):
    """guard.json's log_tail is a list of message-log lines; one of another shape is passed over, and the start
    is still judged by guard.json: run.ended names the window, code 3."""
    folder = _start(tmp_path / "install")
    guard = {"exit": 3, "kind": "unexpected window", "title": "A window", "text": "Its text", "log_tail": {"a": 1}}
    (folder / "guard.json").write_text(json.dumps(guard), encoding="utf-8")
    code, keys, output, junit = _app_junit(tmp_path, ("install", folder, 3, 5, LIMIT))
    assert code == 0 and junit.is_file(), output
    assert _cases(junit)["app.install::run.ended"] == (
        "failed", NO_REPORT % 3 + "; the startup guard ended QGIS (unexpected window): A window"), output
    assert (keys["install_code"], keys["install_gate"]) == ("3", "no"), output


def test_the_last_step_comes_from_steps_jsonl_lines_that_parse(tmp_path):
    """A crash can cut steps.jsonl's last line short: the last line that parses gives the step. Without
    steps.jsonl, the message says that no step was recorded."""
    cut = _start(tmp_path / "install")
    lines = [json.dumps({"event": "begin", "step": step, "t": t}) for step, t in (("route", 4.1), ("export", 7.9))]
    (cut / "steps.jsonl").write_text("\n".join(lines) + '\n{"event": "click", "st', encoding="utf-8")
    bare = _start(tmp_path / "workflow")
    code, keys, output, junit = _app_junit(tmp_path, ("install", cut, 134, 39, LIMIT),
                                           ("workflow", bare, 134, 39, LIMIT))
    assert code == 0 and junit.is_file(), output
    cases = _cases(junit)
    assert cases["app.install::run.ended"] == (
        "failed", "QGIS ended with exit 134 and wrote no report.json (last step: export)"), cases
    assert cases["app.workflow::run.ended"] == (
        "failed", "QGIS ended with exit 134 and wrote no report.json (last step: none recorded)"), cases


#: Each case: the install start's report (its exit, and whether install.installed passed), and the gate.
GATES = {"a_failed_check": (1, True, "yes"), "not_installed": (1, False, "no"), "a_window": (3, True, "no")}


@pytest.mark.parametrize("case", list(GATES))
def test_the_gate_opens_only_on_an_installed_and_enabled_plugin(case, tmp_path):
    """install_gate=yes, which lets ci/app-smoke.sh run the workflow start, needs the install start's report to
    end with exit 0 or 1 and its install.installed and install.enabled checks to have passed."""
    report_exit, installed, gate = GATES[case]
    checks = [_check("install.installed", ok=installed), _check("install.enabled"),
              _check("install.golden_entries", ok=False, expected=[], seen=["a line"])]
    folder = _start(tmp_path / "install", checks, exit_code=report_exit)
    code, keys, output, junit = _app_junit(tmp_path, ("install", folder, report_exit, 9, LIMIT))
    assert code == 0 and junit.is_file(), output
    assert keys["install_gate"] == gate, output


@pytest.mark.parametrize("case", ["junit_exists", "bad_exit_status"])
def test_usage_errors_write_nothing(case, tmp_path):
    """An existing junit.xml is never overwritten, and an exit status that is not a number or none is refused:
    exit 2 either way."""
    folder = _start(tmp_path / "install", [_check("install.installed")])
    raw = 0
    if case == "junit_exists":
        (tmp_path / "junit.xml").write_text("kept", encoding="utf-8")
    else:
        raw = "crashed"
    code, keys, output, junit = _app_junit(tmp_path, ("install", folder, raw, 9, LIMIT))
    assert code == 2 and keys == {}, output
    if case == "junit_exists":
        assert junit.read_text(encoding="utf-8") == "kept", output
    else:
        assert not junit.exists(), output


def test_the_codes_come_before_junit_xml(tmp_path):
    """app-junit prints each start's code before it writes junit.xml, so that ci/app-smoke.sh has the codes when
    the file cannot be written: here its folder does not exist, exit 2, the codes printed and nothing after them."""
    install = _start(tmp_path / "install", [_check("install.installed"), _check("install.enabled")])
    workflow = _start(tmp_path / "workflow", [_check("load.loaded", ok=False)], exit_code=1)
    junit = tmp_path / "missing" / "junit.xml"
    code, keys, output, _junit = _app_junit(tmp_path, ("install", install, 0, 9, LIMIT),
                                            ("workflow", workflow, 1, 17, LIMIT), junit=junit)
    assert code == 2 and keys == {"install_code": "0", "install_gate": "yes", "workflow_code": "1"}, output
    assert not junit.parent.exists(), output
