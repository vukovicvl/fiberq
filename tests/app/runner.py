"""The app runner: drive the real QGIS desktop app from a ``qgis --code`` script, as a person would, and record it.

A scenario is a plain function, ``scenario(r)``. Through ``r``, a ``Runner``, it does what a person does (toolbar
buttons, menu entries, clicks on the map, answers in dialogs) and records what it sees: checks with stable ids,
notes and screenshots. A ``--code`` script calls ``begin(scenario, start="<slug>")``. Once QGIS's event loop runs,
the runner runs the scenario, and QGIS then ends with the run's exit code:

- 0 (``EXIT_PASS``): every check held;
- 1 (``EXIT_CHECK``): a check failed;
- 3 (``EXIT_WINDOW``): a window QGIS opens for a Python error (a ``QgsMessageViewer``), or a window that nothing
  expected and that waits for an answer (the active modal one);
- 4 (``EXIT_DEADLINE``): the deadline passed, counted from when the runner starts (in the app stages, 3 to 6 s
  after QGIS starts);
- 5 (``EXIT_SCRIPT``): the scenario raised, or the answer to a window did, or the window watch did.

A headless run, outside the QGIS app, makes the runner itself with a stand-in for QGIS's ``iface`` and calls
``Runner(start, out, deadline_s, iface=...).run(scenario)``, as ``tests/app/selftest.py`` does.

What a scenario calls:

- ``r.expect_checks(ids)``: the ids of the checks the start records, declared first. report.json lists them as
  ``expected``, and a reader fails the start for each one that is missing (``ci/report.py app-junit``); a check
  whose id they do not list raises ValueError;
- ``r.step(name, text)``: starts a step. ``name`` is ``[a-z0-9_]+`` and unique in the start; ``text`` says what a
  person does in it. The checks, notes, windows and screenshots that follow belong to it;
- ``r.check(name, expected, seen, ok=None, what="")``: records the check ``<step>.<name>`` and returns whether it
  holds. ``r.require(...)`` is the same, and ends the run at once (exit 1) when the check fails;
- ``r.note(text, **data)``: evidence without a verdict. ``r.screenshot(label)``: the main window as it is now,
  with every open dialog painted where it is;
- ``r.expect(match, answer, label)``: answers the next window for which ``match(window)`` holds with
  ``answer(window)``, once. The watch runs every 120 ms, also while a dialog's own event loop runs.
  ``r.expected_left()`` gives the labels of the windows that did not come;
- ``r.wait(ms)``, ``r.wait_until(condition, timeout_ms, poll_ms, what)`` and ``r.wait_for_log(tag, starts, since,
  timeout_ms)``: waits that run the event loop. The last two return whether the condition came true; one that
  times out adds a note that names it (``what``), with the condition's last exception if it raised;
- ``r.log()``, ``r.log_mark()``, ``r.log_since(mark, tag)`` and ``r.python_problems(since)``: QGIS's message-log
  lines, each ``{"t", "step", "tag", "level", "message"}``;
- a person's actions: ``r.trigger(action)``, ``r.entry(toolbar, *labels)``, ``r.menu_entry(menu, *texts)``,
  ``r.click_map(point)``, ``r.map_to_pixel(point)``, ``r.press_ok(w)``, ``r.press_button(w, text)``,
  ``r.field(w, label)``, ``r.type_into(edit, text)``, ``r.choose(combo, text)`` and ``r.save_file_as(w, path)``;
- ``r.finish(code=None)``: ends the run now. ``layer_named(name)``, ``title_starts(prefix)`` and
  ``message_box(title, text_starts)`` help to write scenarios.

The records, in the folder ``out`` (``$APP_OUT`` by default):

- ``report.json``, written at the end, format ``FORMAT``: ``runner`` (the format), ``start``, ``qgis``, ``qt``,
  ``python``, ``platform``, ``started`` (UTC), ``seconds``, ``exit``, ``exit_reason``, ``steps``, ``expected``,
  ``checks``, ``windows``, ``screenshots``, ``notes``, ``expected_windows_left``, ``error`` (a traceback, or null),
  ``memory`` and ``log``. Each check is ``{"id", "step", "name", "what", "expected", "seen", "ok", "t",
  "seconds"}``; each window ``{"step", "kind", "label", "class", "title", "text", "png", "t"}`` (kind ``expected``,
  ``unexpected`` or ``python error window``), plus ``answer_error`` when its answer raised; each screenshot
  ``{"step", "label", "file", "size", "dpr"}``, ``size`` in logical pixels. ``ci/report.py app-junit`` reads it: a
  change to it bumps ``FORMAT``, and ``ci/report.py`` keeps reading every earlier format;
- ``steps.jsonl``: one line per event, ``{"event", "step", "t", ...}``, written as it happens, so that a crash
  keeps them. The events: start, begin (a step), check, note, window, screenshot, click, type, choose, map_click,
  deadline, error and finish;
- ``log.jsonl``: one line per message-log line. ``tests/app/guard.py`` writes it from QGIS's start; without the
  guard, the runner writes it from its own start;
- ``NNN_<step>_<label>.png``: the screenshots, numbered in the order they were taken.

The three JSON records and the lines on stdout are UTF-8: a lone surrogate (as a file name decoded with
``surrogateescape`` brings) is written as its escape, ``\\udcff``, which JSON reads back as the same value.

The guard (``tests/app/guard.py``, which QGIS runs through ``PYQGIS_STARTUP`` before it loads any plugin) leaves
the module ``fiberq_app_guard`` in ``sys.modules``, with ``TIMER`` (its window watch, a QTimer), ``T0`` (QGIS's
start, a ``time.time()``), ``LOG`` (the message-log lines so far, in the form above, which the guard goes on adding
to, and to log.jsonl) and ``STEP``. When it is there, the runner stops ``TIMER``, counts time from ``T0``, reads
``LOG`` and sets ``STEP`` to the current step. The runner imports only QGIS and the standard library, never
FiberQ, so it can run any scenario.
"""
import contextlib
import json
import os
import re
import sys
import time
import traceback
from functools import partial

from qgis.core import Qgis, QgsApplication, QgsPointXY, QgsProject, QgsSettings
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QPoint, Qt, QTimer, qVersion
from qgis.PyQt.QtGui import QGuiApplication, QPainter
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import (QAbstractButton, QAbstractSpinBox, QApplication, QComboBox, QDialog,
                                 QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QTextEdit,
                                 QToolBar, QToolButton)

EXIT_PASS, EXIT_CHECK, EXIT_WINDOW, EXIT_DEADLINE, EXIT_SCRIPT = 0, 1, 3, 4, 5

#: The format of report.json, its "runner" key.
FORMAT = 1

#: The deadline when neither ``deadline_s`` nor ``$APP_DEADLINE_S`` gives one, in seconds.
DEADLINE_S = 300

#: How often the window watch looks, and how long a window shows before its answer, in milliseconds.
WATCH_MS = 120
ANSWER_MS = 150

#: A start's slug, and a step's or a check's name.
NAME = re.compile(r"[a-z0-9_]+")

#: A check's id: ``<step>.<name>``.
CHECK_ID = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+")

#: The message-log tags of QGIS's Python errors and Python warnings.
PYTHON_TAGS = ("Python error", "Python warning")

#: QGIS's message levels by number: the names PyQt5's enum values do not carry.
LEVELS = {0: "Info", 1: "Warning", 2: "Critical", 3: "Success", 4: "NoLevel"}

#: How long a window's text and a log line's message may be in the records.
TEXT_MAX = 4000

#: The dynamic property that marks a window the watch has handled, while it stays visible.
SEEN = "app_runner_seen"

#: begin()'s timer, and the runner it makes: kept here, so that Python does not collect them.
_KEEP = []


def begin(scenario, start, delay_ms=500, out=None, deadline_s=None):
    """Run ``scenario`` as the start ``start`` once QGIS's event loop runs; QGIS then ends with the run's exit code.

    Called from a ``qgis --code`` script, which QGIS runs before its event loop starts. ``out`` and ``deadline_s``
    go to ``Runner``. If the runner cannot be made (no ``out`` folder, a bad slug), the traceback goes to stderr
    and QGIS ends with exit 5, without a report.
    """
    def go():
        try:
            runner = Runner(start, out=out, deadline_s=deadline_s)
        except Exception:   # no runner, so no report: say why, and end QGIS rather than leave it open
            traceback.print_exc()
            sys.stderr.flush()
            os._exit(EXIT_SCRIPT)
        _KEEP.append(runner)
        runner.run(scenario)

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(go)
    timer.start(int(delay_ms))
    _KEEP.append(timer)


class Runner:
    """One start: a scenario run in QGIS, its records in ``out``, and the exit code QGIS ends with.

    ``start`` is the start's slug (``install``, ``workflow``, ``selftest``). ``out`` defaults to ``$APP_OUT`` and is
    made if it does not exist; ``deadline_s`` to ``$APP_DEADLINE_S``, else ``DEADLINE_S``; ``iface`` to
    ``qgis.utils.iface``. A stand-in needs ``mainWindow()`` and ``mapCanvas()``. The window watch and the deadline
    start here. A scenario reads ``r.iface``, ``r.out`` and ``r.start``.
    """

    def __init__(self, start, out=None, deadline_s=None, iface=None):
        if not (isinstance(start, str) and NAME.fullmatch(start)):
            raise ValueError("a start's slug is [a-z0-9_]+: %r" % (start,))
        if out is None:
            out = os.environ.get("APP_OUT")
        if not out:
            raise ValueError("no folder for the records: pass out= or set APP_OUT")
        if deadline_s is None:
            deadline_s = os.environ.get("APP_DEADLINE_S", DEADLINE_S)
        deadline_s = float(deadline_s)
        if deadline_s <= 0:
            raise ValueError("the deadline must be above 0 s: %r" % (deadline_s,))
        if iface is None:
            import qgis.utils   # the QGIS app's; imported only when needed: importing it replaces __import__
            iface = qgis.utils.iface
        if iface is None:
            raise ValueError("qgis.utils.iface is None outside the QGIS app: pass iface=")
        os.makedirs(out, exist_ok=True)
        self.start = start
        self.out = out
        self.deadline_s = deadline_s
        self.iface = iface
        self.current_step = "startup"
        self._handlers = []
        self._steps = set()
        self._ids = set()
        self._shots = 0
        self._finishing = False
        self._reason = None
        self._guard = sys.modules.get("fiberq_app_guard")
        if self._guard is not None:
            self._guard.TIMER.stop()   # the runner watches the windows from here on
            self._t0 = self._guard.T0
            self._log = self._guard.LOG
        else:
            self._t0 = time.time()
            self._log = []
            messages = QgsApplication.messageLog()
            if hasattr(messages, "messageReceivedWithFormat"):
                messages.messageReceivedWithFormat.connect(self._logged)
            else:
                messages.messageReceived[str, str, Qgis.MessageLevel].connect(self._logged)
        self._last_check = time.time()
        self.report = {
            "runner": FORMAT, "start": start, "qgis": _qgis_version(), "qt": qVersion(),
            "python": "%d.%d.%d" % sys.version_info[:3], "platform": QGuiApplication.platformName(),
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._t0)), "seconds": None,
            "exit": None, "exit_reason": None, "steps": [], "expected": [], "checks": [], "windows": [],
            "screenshots": [], "notes": [], "expected_windows_left": [], "error": None, "memory": {}, "log": []}
        self._watch_timer = QTimer()
        self._watch_timer.timeout.connect(self._watch_tick)
        self._watch_timer.start(WATCH_MS)
        self._deadline_timer = QTimer()
        self._deadline_timer.setSingleShot(True)
        self._deadline_timer.timeout.connect(self._deadline_passed)
        self._deadline_timer.start(int(deadline_s * 1000))

    # ---- the run ------------------------------------------------------------------------------------------------
    def run(self, scenario):
        """Run ``scenario(self)``, then end the process with the run's exit code: it never returns.

        Whatever the scenario raises is recorded, its traceback as ``error``, and the run ends with exit 5.
        """
        self._last_check = time.time()
        self._event("start", start=self.start, qgis=self.report["qgis"], deadline_s=self.deadline_s)
        try:
            scenario(self)
        except BaseException:   # any raise is the scenario's failure, recorded; the run still ends with its report
            self._fail("the scenario", traceback.format_exc())
        self.finish()

    def finish(self, code=None):
        """End the run now: write report.json, sync QGIS's settings, print ``RESULT``, then ``os._exit(code)``.

        ``code`` defaults to 1 if a check failed, else 0. The last line on stdout is ``RESULT`` and a JSON object,
        ``{"exit", "failed", "checks", "report"}``, as ``tests/support/child.py`` reads it. ``os._exit`` skips
        Qt's teardown, so QGIS asks nothing on the way out; the settings are synced first, because it also skips
        QSettings' own write. report.json is written before anything goes to stdout, and the process ends with
        ``code`` even when a write fails. It never returns.
        """
        if self._finishing:
            return
        self._finishing = True
        failed = self._failed()
        if code is None:
            code = EXIT_CHECK if failed else EXIT_PASS
        reason = self._reason
        if reason is None and code == EXIT_PASS and not failed:
            reason = "passed"
        elif reason is None and code == EXIT_CHECK and failed:
            reason = "a check failed"
        elif reason is None:
            reason = "the scenario ended the run with exit %d" % code
        try:
            self.report.update(seconds=self.now(), exit=code, exit_reason=reason,
                               expected_windows_left=self.expected_left(), memory=_memory(), log=list(self._log))
            path = os.path.join(self.out, "report.json")
            text = _utf8(json.dumps(self.report, indent=1, default=str, ensure_ascii=False))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            QgsSettings().sync()
            self._event("finish", exit=code, exit_reason=reason)
            print(_utf8("RESULT " + json.dumps({"exit": code, "failed": len(failed),
                                                "checks": len(self.report["checks"]), "report": path})), flush=True)
        except BaseException:   # the process ends here whatever happens; the traceback says what was not written
            with contextlib.suppress(BaseException):   # stderr may fail too, and nothing is left to say so on
                traceback.print_exc()
        finally:
            for stream in (sys.stdout, sys.stderr):
                with contextlib.suppress(BaseException):   # a stream that cannot flush must not keep QGIS open
                    stream.flush()
            os._exit(code)

    def _end(self, code, reason):
        if self._finishing:
            return
        self._reason = reason
        self.finish(code)

    def _fail(self, where, tb):
        """Record a raise (the scenario's, an answer's, the watch's) and end the run with exit 5."""
        if self._finishing:
            return
        last = _last_line(tb)
        self._event("error", where=where, traceback=tb)
        if where == "the scenario":
            self.report["error"] = tb
            reason = "the scenario raised: " + last
        else:
            self.report["error"] = "%s:\n%s" % (where, tb)
            reason = "the scenario raised: %s: %s" % (where, last)
        self._end(EXIT_SCRIPT, reason)

    def _deadline_passed(self):
        if self._finishing:
            return
        self._event("deadline", seconds=self.deadline_s)
        self._end(EXIT_DEADLINE, "the deadline passed (%g s) in step %s" % (self.deadline_s, self.current_step))

    def _failed(self):
        return [c for c in self.report["checks"] if not c["ok"]]

    # ---- recording ------------------------------------------------------------------------------------------------
    def now(self):
        """Seconds since the start: since QGIS started, with the guard; else since the runner was made."""
        return round(time.time() - self._t0, 3)

    def _event(self, event, **data):
        """One line of steps.jsonl, appended and flushed at once, and the same on stdout."""
        line = dict(data, event=event, step=self.current_step, t=self.now())
        text = _utf8(json.dumps(line, default=str, ensure_ascii=False, sort_keys=True))
        print("APP " + text[:2000], flush=True)
        _append(os.path.join(self.out, "steps.jsonl"), text)

    def expect_checks(self, ids):
        """Declare the ids of the checks this start records, each ``"<step>.<name>"``.

        report.json lists them, in this order, as ``expected``; a reader fails the start for each one that is
        missing, so a check that silently did not run is a failure too. Call it first, so that a run that ends
        early still lists them, and so that ``check()`` refuses an id they do not list. A second call adds to the
        list.
        """
        ids = list(ids)
        for cid in ids:
            if not (isinstance(cid, str) and CHECK_ID.fullmatch(cid)):
                raise ValueError("a check id is <step>.<name>, each [a-z0-9_]+: %r" % (cid,))
            if cid in self.report["expected"] or ids.count(cid) > 1:
                raise ValueError("the check id %r is declared twice" % cid)
        self.report["expected"].extend(ids)

    def step(self, name, text=""):
        """Start the step ``name`` (``[a-z0-9_]+``, unique in the start); ``text`` says what a person does in it."""
        if not (isinstance(name, str) and NAME.fullmatch(name)):
            raise ValueError("a step name is [a-z0-9_]+: %r" % (name,))
        if name in self._steps:
            raise ValueError("the step %r is started twice in this start" % name)
        self._steps.add(name)
        self.current_step = name
        if self._guard is not None:
            self._guard.STEP = name
        self.report["steps"].append({"step": name, "text": text, "t": self.now()})
        self._event("begin", text=text)

    def check(self, name, expected, seen, ok=None, what=""):
        """Record the check ``<step>.<name>`` in the current step (so ``r.step()`` comes first) and return whether
        it holds.

        It holds when ``expected == seen`` (Python's equality: a tuple is not equal to a list), unless ``ok`` is
        given. ``name`` is ``[a-z0-9_]+`` and unique in its step, so the id stays the same from run to run;
        ``what`` says what is checked. ``expected`` and ``seen`` are recorded as JSON as they are now, anything
        JSON cannot hold as its ``str()``. Once ``expect_checks()`` declared ids, an id it did not declare raises
        ValueError, so the run ends with exit 5, as for any other bug in the scenario.
        """
        if not self._steps:
            raise ValueError("the check %r comes before the first step: call r.step() first" % (name,))
        if not (isinstance(name, str) and NAME.fullmatch(name)):
            raise ValueError("a check name is [a-z0-9_]+: %r" % (name,))
        cid = "%s.%s" % (self.current_step, name)
        if self.report["expected"] and cid not in self.report["expected"]:
            raise ValueError("the check %r is not declared in expect_checks()" % cid)
        if cid in self._ids:
            raise ValueError("the check %r is recorded twice" % cid)
        self._ids.add(cid)
        ok = (expected == seen) if ok is None else bool(ok)
        now = time.time()
        entry = {"id": cid, "step": self.current_step, "name": name, "what": what, "expected": _plain(expected),
                 "seen": _plain(seen), "ok": ok, "t": self.now(), "seconds": round(now - self._last_check, 3)}
        self._last_check = now
        self.report["checks"].append(entry)
        self._event("check", id=cid, ok=ok, expected=entry["expected"], seen=entry["seen"], what=what)
        return ok

    def require(self, name, expected, seen, ok=None, what=""):
        """``check()``, for a check the rest of the start depends on: when it fails, the run ends at once (exit 1)."""
        if self.check(name, expected, seen, ok, what):
            return True
        self.note("a required check failed, so the run ends here: %s.%s" % (self.current_step, name))
        self.finish()
        return False

    def note(self, text, **data):
        """Record evidence without a verdict: ``text`` and ``data``, each value as JSON holds it now."""
        entry = {"step": self.current_step, "text": text}
        entry.update((key, _plain(value)) for key, value in data.items() if key not in entry)
        self.report["notes"].append(entry)
        self._event("note", **{key: value for key, value in entry.items() if key != "step"})

    def screenshot(self, label, widget=None):
        """Save a PNG of the main window as it is now, with every open dialog painted where it is, the active
        modal one last (or of ``widget`` alone), as ``NNN_<step>_<label>.png`` in ``out``; return its name.

        It waits for the map canvas to finish rendering first. The picture is rendered by Qt, not read back from
        the screen. Its size is recorded in logical pixels, with the device pixel ratio as ``dpr``.
        """
        self.iface.mapCanvas().waitWhileRendering()
        self._shots += 1
        name = "%03d_%s_%s.png" % (self._shots, _slug(self.current_step), _slug(label))
        pixmap = widget.grab() if widget is not None else self._grab_window()
        if not pixmap.save(os.path.join(self.out, name)):
            raise OSError("the screenshot %s could not be written to %s" % (name, self.out))
        dpr = pixmap.devicePixelRatio()
        size = [int(round(pixmap.width() / dpr)), int(round(pixmap.height() / dpr))]
        self.report["screenshots"].append({"step": self.current_step, "label": label, "file": name, "size": size,
                                           "dpr": dpr})
        self._event("screenshot", file=name, size=size, dpr=dpr)
        return name

    def _grab_window(self):
        window = self.iface.mainWindow()
        pixmap = window.grab()
        painter = QPainter(pixmap)
        origin = window.mapToGlobal(QPoint(0, 0))
        modal = QApplication.activeModalWidget()
        shown = [w for w in self._windows(window, modal) if w.isVisible()]
        shown.sort(key=lambda w: (w is modal, w.isModal()))
        for w in shown:
            painter.drawPixmap(w.mapToGlobal(QPoint(0, 0)) - origin, w.grab())
        painter.end()
        return pixmap

    # ---- the message log ------------------------------------------------------------------------------------------
    def _logged(self, message, tag, level, *_rest):
        entry = {"t": self.now(), "step": self.current_step, "tag": tag, "level": _level(level),
                 "message": message[:TEXT_MAX]}
        self._log.append(entry)
        _append(os.path.join(self.out, "log.jsonl"), _utf8(json.dumps(entry, ensure_ascii=False)))

    def log(self):
        """Every message-log line so far: since QGIS started, with the guard; else since the runner was made."""
        return list(self._log)

    def log_mark(self):
        """A mark for ``log_since()`` and the waits: the number of lines so far."""
        return len(self._log)

    def log_since(self, mark, tag=None):
        """The lines after ``mark``, those on ``tag`` only when it is given."""
        return [e for e in self._log[mark:] if tag is None or e["tag"] == tag]

    def python_problems(self, since=0):
        """The lines on QGIS's "Python error" and "Python warning" tags after the mark ``since``."""
        return [e for e in self._log[since:] if e["tag"] in PYTHON_TAGS]

    # ---- waiting ------------------------------------------------------------------------------------------------
    def wait(self, ms):
        """Let QGIS run for ``ms`` milliseconds."""
        QTest.qWait(int(ms))

    def wait_until(self, condition, timeout_ms=5000, poll_ms=50, what=""):
        """Let QGIS run until ``condition()`` is true; return False if it was not within ``timeout_ms``.

        It never raises: a condition that raises is not true yet. When the wait times out, a note says so, naming
        the wait by ``what`` (else by the condition's name), with the condition's last exception if it raised one.
        """
        return self._wait(condition, timeout_ms, poll_ms, what or getattr(condition, "__name__", repr(condition)))

    def wait_for_log(self, tag, starts, since=0, timeout_ms=15000):
        """Let QGIS run until a message-log line on ``tag`` whose message starts with ``starts`` is there, after
        the mark ``since``; return False if none came within ``timeout_ms``. It never raises."""
        def logged():
            return any(e["tag"] == tag and e["message"].startswith(starts) for e in self._log[since:])
        what = "a log line on %r that starts %r, after line %d" % (tag, starts, since)
        return self._wait(logged, timeout_ms, 50, what)

    def _wait(self, condition, timeout_ms, poll_ms, what):
        end = time.monotonic() + timeout_ms / 1000.0
        error = None
        while True:
            try:
                if condition():
                    return True
            except Exception as exc:   # not readable yet is not true yet; the note below keeps the last one
                error = "%s: %s" % (type(exc).__name__, exc)
            if time.monotonic() >= end:
                break
            QTest.qWait(int(poll_ms))
        self.note("a wait timed out after %d ms: %s" % (timeout_ms, what), last_error=error)
        return False

    # ---- windows ------------------------------------------------------------------------------------------------
    def expect(self, match, answer, label):
        """Answer the next window for which ``match(window)`` is true with ``answer(window)``, once.

        The window is recorded (kind ``expected``, with ``label``) and screenshotted when the watch first sees it,
        and answered 150 ms later. An answer that raises ends the run with exit 5, its last line recorded as the
        window's ``answer_error``. So does a ``match`` that raises.
        """
        self._handlers.append({"match": match, "answer": answer, "label": label})

    def expected_left(self):
        """The labels of the expected windows that have not come."""
        return [h["label"] for h in self._handlers]

    @staticmethod
    def _windows(main_window, modal):
        """The windows the watch looks at: the dialogs, and the active modal window if it is not a dialog."""
        return [w for w in QApplication.topLevelWidgets()
                if w is not main_window and (isinstance(w, QDialog) or w is modal)]

    def _watch_tick(self):
        if self._finishing:
            return
        try:
            self._watch()
        except Exception:   # a broken watch would leave a window open until the deadline
            self._fail("the window watch", traceback.format_exc())

    def _watch(self):
        modal = QApplication.activeModalWidget()
        for w in self._windows(self.iface.mainWindow(), modal):
            if sip.isdeleted(w):   # closed and deleted while an earlier window's screenshot let QGIS run
                continue
            if not w.isVisible():
                if w.property(SEEN):
                    w.setProperty(SEEN, False)   # shown again later, it is a new window
                continue
            if w.property(SEEN):
                continue
            if w.metaObject().className() == "QgsMessageViewer":
                w.setProperty(SEEN, True)
                self._window(w, "python error window", "")
                self._end(EXIT_WINDOW, "a Python error window: " + w.windowTitle())
                return
            handler = next((h for h in self._handlers if h["match"](w)), None)
            if handler is not None:
                w.setProperty(SEEN, True)
                self._handlers.remove(handler)
                entry = self._window(w, "expected", handler["label"])
                QTimer.singleShot(ANSWER_MS, partial(self._answer, handler, w, entry))
            elif w is modal:
                w.setProperty(SEEN, True)
                self._window(w, "unexpected", "")
                self._end(EXIT_WINDOW, "an unexpected window: " + w.windowTitle())
                return

    def _window(self, w, kind, label):
        entry = {"step": self.current_step, "kind": kind, "label": label, "class": w.metaObject().className(),
                 "title": w.windowTitle(), "text": _window_text(w), "png": None, "t": self.now()}
        self.report["windows"].append(entry)
        self._event("window", kind=kind, label=label, title=entry["title"], text=entry["text"])
        entry["png"] = self.screenshot("window_" + (label or kind))
        return entry

    def _answer(self, handler, w, entry):
        if self._finishing:
            return
        try:
            handler["answer"](w)
        except Exception:   # recorded on the window and as the run's error: the run ends with 5
            tb = traceback.format_exc()
            entry["answer_error"] = _last_line(tb)
            self._fail("answer to " + str(handler["label"]), tb)

    # ---- a person's actions ---------------------------------------------------------------------------------------
    def trigger(self, action):
        """Click ``action``'s toolbar button when one is on screen, else trigger it as its menu entry does.

        It returns when the action's slot returns; the watch answers the windows the slot opens meanwhile. A
        disabled action raises ValueError: a person cannot click it. So does a button that opens a drop-down when
        it is clicked (a QToolButton in InstantPopup mode with a menu or with actions of its own, as each of
        FiberQ's drop-downs is): the drop-down would hold the run until the deadline, since the watch answers
        windows, not menus. Name the entry instead, ``r.entry(toolbar, label, entry)``.
        """
        if not action.isEnabled():
            raise ValueError("%r is disabled, so a person cannot click it" % _text(action))
        button = None
        for bar in self.iface.mainWindow().findChildren(QToolBar):
            widget = bar.widgetForAction(action)
            if widget is not None and widget.isVisible():
                button = widget
                break
        if _drops_down(button):
            label = (action.text() or button.toolTip() or button.text()).replace("&", "")
            raise ValueError("the button %r opens a drop-down: name its entry, r.entry(toolbar, label, entry)"
                             % label)
        self._event("click", action=_text(action), on_toolbar=button is not None)
        if button is not None:
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        else:
            action.trigger()

    def entry(self, toolbar, *labels):
        """The QAction a person reaches from the toolbar whose object name is ``toolbar``.

        ``labels[0]`` is the label of a visible button on it: its action's text, else the button's tooltip, else
        its text. The labels after it go down the button's drop-down by entry text (``"Cable laying",
        "Underground", "Backbone"``), as ``menu_entry()`` does. ``&`` is left out of every label. With one label
        it returns the button's own action, which ``trigger()`` refuses when the button opens its drop-down at a
        click: name the entry then.
        """
        if not labels:
            raise ValueError("entry() needs the label of a button")
        bar = self.iface.mainWindow().findChild(QToolBar, toolbar)
        if bar is None:
            raise LookupError("no toolbar %r" % toolbar)
        for action in bar.actions():
            button = bar.widgetForAction(action)
            if not isinstance(button, QToolButton) or not action.isVisible():
                continue
            label = action.text() or button.toolTip() or button.text()
            if label.replace("&", "") != labels[0]:
                continue
            if len(labels) == 1:
                return action
            if button.menu() is None:
                raise LookupError("the button %r on the toolbar %r has no drop-down" % (labels[0], toolbar))
            return self.menu_entry(button.menu(), *labels[1:])
        raise LookupError("no button %r on the toolbar %r" % (labels[0], toolbar))

    def menu_entry(self, menu, *texts):
        """The QAction a person reaches in the QMenu ``menu`` by the visible entries' texts, ``&`` left out: one
        text for an entry of ``menu``, more for the entries of its submenus in turn (``"FiberQ", "Export…"``)."""
        if not texts:
            raise ValueError("menu_entry() needs the text of an entry")
        found = None
        for want in texts:
            if menu is None:
                where = "no menu was given" if found is None else "the entry %r has no submenu" % _text(found)
                raise LookupError("no menu to look for %r in: %s" % (want, where))
            entries = [a for a in menu.actions() if a.isVisible() and not a.isSeparator()]
            hits = [a for a in entries if a.text().replace("&", "") == want]
            if not hits:
                raise LookupError("no entry %r in the menu %r: %s" % (want, menu.title(), [_text(a) for a in entries]))
            found, menu = hits[0], hits[0].menu()
        return found

    def map_to_pixel(self, point):
        """The map canvas viewport's pixel at ``point``, a QgsPointXY or ``(x, y)`` in the canvas's map units."""
        point = QgsPointXY(*point) if isinstance(point, (tuple, list)) else QgsPointXY(point)
        pixel = self.iface.mapCanvas().getCoordinateTransform().transform(point)
        return QPoint(int(round(pixel.x())), int(round(pixel.y())))

    def click_map(self, point, button=Qt.MouseButton.LeftButton, modifier=Qt.KeyboardModifier.NoModifier):
        """Move the mouse to ``point`` on the map (as ``map_to_pixel()``), wait 60 ms, and click there."""
        viewport = self.iface.mapCanvas().viewport()
        pixel = self.map_to_pixel(point)
        QTest.mouseMove(viewport, pixel)
        self.wait(60)
        self._event("map_click", point=[_plain(c) for c in _xy(point)], px=[pixel.x(), pixel.y()],
                    button=_enum_name(button))
        QTest.mouseClick(viewport, button, modifier, pixel)

    def press_button(self, w, text):
        """Click the visible button of the window ``w`` whose text, ``&`` left out, is ``text``."""
        want = text.replace("&", "")
        buttons = [b for b in w.findChildren(QAbstractButton) if b.isVisible()]
        for button in buttons:
            if button.text().replace("&", "") == want:
                self._event("click", window=w.windowTitle(), button=want)
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                return
        raise LookupError("no button %r in %r: %s" % (text, w.windowTitle(),
                                                      [b.text().replace("&", "") for b in buttons]))

    def press_ok(self, w):
        """Click the OK button of the window ``w``: its button box's, or a message box's own."""
        for box in w.findChildren(QDialogButtonBox):
            ok = box.button(QDialogButtonBox.StandardButton.Ok)
            if ok is not None and ok.isVisible():
                self._event("click", window=w.windowTitle(), button="OK")
                QTest.mouseClick(ok, Qt.MouseButton.LeftButton)
                return
        ok = w.button(QMessageBox.StandardButton.Ok) if isinstance(w, QMessageBox) else None
        if ok is None:
            raise LookupError("no OK button in %r" % w.windowTitle())
        self._event("click", window=w.windowTitle(), button="OK")
        QTest.mouseClick(ok, Qt.MouseButton.LeftButton)

    def field(self, w, label):
        """The field of the form row of ``w`` whose label reads ``label``, ``&`` and a trailing colon left out."""
        want = label.replace("&", "").rstrip(":")
        for form in w.findChildren(QFormLayout):
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if item is None or not isinstance(item.widget(), QLabel):
                    continue
                if item.widget().text().replace("&", "").rstrip(":") != want:
                    continue
                field = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
                if field is not None and field.widget() is not None:
                    return field.widget()
        raise LookupError("no form row %r in %r" % (label, w.windowTitle()))

    def type_into(self, edit, text):
        """Select what ``edit`` holds and type ``text`` over it, key by key (a spin box or a combo box: into its
        line edit)."""
        target = edit
        if isinstance(edit, (QAbstractSpinBox, QComboBox)):
            target = edit.findChild(QLineEdit)
            if target is None:
                raise LookupError("this %s has no line edit to type into" % edit.metaObject().className())
        target.setFocus()
        target.selectAll()
        self._event("type", field=edit.objectName() or edit.metaObject().className(), text=str(text))
        QTest.keyClicks(target, str(text))
        if isinstance(edit, QAbstractSpinBox):
            edit.interpretText()

    def choose(self, combo, text):
        """Pick the entry ``text`` in the combo box ``combo``."""
        index = combo.findText(text)
        if index < 0:
            raise LookupError("no %r in the list %r" % (text, [combo.itemText(i) for i in range(combo.count())]))
        self._event("choose", field=combo.objectName() or "QComboBox", text=text)
        combo.setCurrentIndex(index)

    def save_file_as(self, w, path):
        """In Qt's own file window ``w``: type ``path`` into its file name field and click its accept button."""
        edit = w.findChild(QLineEdit, "fileNameEdit")
        box = w.findChild(QDialogButtonBox, "buttonBox")
        if edit is None or box is None:
            raise LookupError("%r is not Qt's own file window (no fileNameEdit or buttonBox)" % w.windowTitle())
        self.type_into(edit, path)
        accept = [b for b in box.buttons() if box.buttonRole(b) == QDialogButtonBox.ButtonRole.AcceptRole]
        if not accept:
            raise LookupError("no accept button in %r" % w.windowTitle())
        self._event("click", window=w.windowTitle(), button=accept[0].text().replace("&", ""))
        QTest.mouseClick(accept[0], Qt.MouseButton.LeftButton)


# ---- helpers for scenarios ----------------------------------------------------------------------------------------
def layer_named(name):
    """The project's first layer named ``name``, or None."""
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def title_starts(prefix):
    """A ``match`` for ``r.expect()``: a window whose title starts with ``prefix``."""
    def match(w):
        return w.windowTitle().startswith(prefix)
    return match


def message_box(title=None, text_starts=None):
    """A ``match`` for ``r.expect()``: a QMessageBox, titled ``title`` and with a text that starts with
    ``text_starts``, each when it is given."""
    def match(w):
        if not isinstance(w, QMessageBox):
            return False
        if title is not None and w.windowTitle() != title:
            return False
        return text_starts is None or w.text().startswith(text_starts)
    return match


# ---- internals ----------------------------------------------------------------------------------------------------
def _qgis_version():
    return Qgis.version() if hasattr(Qgis, "version") else Qgis.QGIS_VERSION


def _plain(value):
    """``value`` as JSON holds it now: lists for tuples, the ``str()`` of anything else JSON cannot hold."""
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except (TypeError, ValueError):   # keys JSON cannot hold, or a value that contains itself
        return str(value)


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_")[:40] or "x"


def _last_line(tb):
    lines = [line for line in tb.strip().splitlines() if line.strip()]
    return lines[-1].strip() if lines else ""


def _level(level):
    name = getattr(level, "name", None)
    return name if isinstance(name, str) else LEVELS.get(int(level), str(level))


def _enum_name(value):
    name = getattr(value, "name", None)
    return name if isinstance(name, str) else str(int(value))


def _text(action):
    return action.text().replace("&", "") if action is not None else None


def _drops_down(button):
    """Whether a click on ``button`` opens a drop-down, as Qt decides it: a QToolButton in InstantPopup mode with a
    menu, a default action with a menu, or actions of its own besides its default action."""
    if not isinstance(button, QToolButton):
        return False
    if button.popupMode() != QToolButton.ToolButtonPopupMode.InstantPopup:
        return False
    default = button.defaultAction()
    if button.menu() is not None or (default is not None and default.menu() is not None):
        return True
    return len(button.actions()) > (0 if default is None else 1)


def _xy(point):
    if isinstance(point, (tuple, list)):
        return list(point)
    return [point.x(), point.y()]


def _window_text(w):
    """What a window says: a message box's texts, else its text boxes', else its labels', at most TEXT_MAX."""
    if isinstance(w, QMessageBox):
        parts = [w.text(), w.informativeText()]
    else:
        parts = [e.toPlainText() for e in w.findChildren(QTextEdit)]
        if not any(parts):
            parts = [label.text() for label in w.findChildren(QLabel) if label.isVisible()]
    return "\n".join(p for p in parts if p)[:TEXT_MAX]


def _utf8(text):
    """``text`` as UTF-8 can hold it: each lone surrogate (as a file name decoded with ``surrogateescape`` brings)
    becomes its escape, ``\\udcff``. Every record and stdout line the runner writes goes through it; in a JSON
    text, the escape reads back as the same value."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def _append(path, line):
    """Append ``line`` to the file ``path``. A record that cannot be written is said on stderr, and the run goes
    on, so that it still ends with its exit code."""
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except (OSError, ValueError) as exc:   # ValueError: text that UTF-8 cannot hold, had _utf8() been left out
        print("APP could not append to %s: %s" % (path, exc), file=sys.stderr, flush=True)


def _memory():
    """QGIS's peak and current resident memory (``VmHWM``, ``VmRSS``), where /proc gives them."""
    memory = {}
    try:
        with open("/proc/self/status", encoding="ascii", errors="replace") as fh:
            for line in fh:
                key, _sep, value = line.partition(":")
                if key in ("VmHWM", "VmRSS"):
                    memory[key] = value.strip()
    except OSError:   # no /proc here
        pass
    return memory
