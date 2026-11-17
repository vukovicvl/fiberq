"""The app stages' startup guard: QGIS runs it through ``PYQGIS_STARTUP``, before it loads any plugin.

QGIS runs this file once its Python is up, before it loads the plugins and before the ``--code`` script. Until the
runner (tests/app/runner.py) takes over, it does two things:

- it keeps QGIS's message log from the start: each line goes into ``LOG`` and onto ``$APP_OUT/log.jsonl``, as
  ``{"t", "step", "tag", "level", "message"}``, ``t`` in seconds since ``T0`` and ``step`` the runner's step at
  that moment (``STEP``). It goes on after the runner took over; the runner reads ``LOG``;
- every 200 ms (``TIMER``) it looks for a window that blocks QGIS: a ``QgsMessageViewer``, the window QGIS opens
  for a Python error (kind ``python error window``), or any other window that is the active modal one (kind
  ``unexpected window``). It saves that window as ``guard-window.png``, writes ``guard.json`` (``{"exit", "kind",
  "title", "text", "png", "t", "log_tail"}``) and ends QGIS with exit code 3. Under Xvfb with no window manager no
  window is ever the active one, so QGIS shows a plugin's load error in such a blocking window, not in the message
  bar: without the guard, a plugin that fails to load at startup would hold QGIS there until its time limit, and the
  ``--code`` script would never run.

It leaves the module ``fiberq_app_guard`` in ``sys.modules``, with ``LOG``, ``STEP``, ``T0`` (QGIS's start, a
``time.time()``) and ``TIMER``; the runner stops ``TIMER`` when it starts its own window watch. Without ``$APP_OUT``
it writes into the current folder. QGIS runs the file in the namespace of ``__main__``, with no ``__file__``, and
the ``--code`` script runs in the same namespace later, so the names here start with ``GUARD_`` or ``_guard_``.
QGIS shows anything the file raises in a window of its own, which nothing would answer; so it reads nothing that
may be missing, and its two slots catch only the error of a file that cannot be written. It writes log.jsonl and
guard.json as the runner writes its records, in UTF-8, each lone surrogate as its escape (``\\udcff``). It imports
only QGIS and the standard library.
"""
import json
import os
import sys
import time
import types

from qgis.core import Qgis, QgsApplication
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QTextEdit

#: The exit code of a window that blocks QGIS, as the runner's ``EXIT_WINDOW``.
GUARD_EXIT = 3

#: How often the guard looks for a blocking window, in milliseconds.
GUARD_WATCH_MS = 200

#: How long a window's text and a log line's message may be in the records, as in the runner.
GUARD_TEXT_MAX = 4000

#: How many of the last message-log lines guard.json keeps.
GUARD_LOG_TAIL = 20

#: QGIS's message levels by number: the names PyQt5's enum values do not carry.
GUARD_LEVELS = {0: "Info", 1: "Warning", 2: "Critical", 3: "Success", 4: "NoLevel"}


def _guard_level(level):
    """A message level's name."""
    name = getattr(level, "name", None)
    return name if isinstance(name, str) else GUARD_LEVELS.get(int(level), str(level))


def _guard_utf8(text):
    """``text`` as UTF-8 can hold it, each lone surrogate as its escape: the runner's ``_utf8()``, which the guard
    cannot import."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def _guard_text(window):
    """What a window says: a message box's texts, else its text boxes', else its visible labels'."""
    if isinstance(window, QMessageBox):
        parts = [window.text(), window.informativeText()]
    else:
        parts = [box.toPlainText() for box in window.findChildren(QTextEdit)]
        if not any(parts):
            parts = [label.text() for label in window.findChildren(QLabel) if label.isVisible()]
    return "\n".join(part for part in parts if part)[:GUARD_TEXT_MAX]


def _guard_blocking():
    """The window that blocks QGIS now and its kind, or ``(None, None)``."""
    for window in QApplication.topLevelWidgets():
        if not (window.isVisible() and isinstance(window, QDialog)):
            continue
        if window.metaObject().className() == "QgsMessageViewer":
            return window, "python error window"
    modal = QApplication.activeModalWidget()
    if modal is not None and modal.isVisible():
        return modal, "unexpected window"
    return None, None


def _guard_start():
    """Make the module ``fiberq_app_guard``, connect the message log and start the window watch."""
    guard = types.ModuleType("fiberq_app_guard")
    guard.__doc__ = "The app stages' startup guard (tests/app/guard.py): its log, its window watch and its clock."
    guard.OUT = os.environ.get("APP_OUT") or os.getcwd()
    guard.LOG = []
    guard.STEP = "startup"
    guard.T0 = time.time()

    def now():
        return round(time.time() - guard.T0, 3)

    def logged(message, tag, level, *_rest):
        entry = {"t": now(), "step": guard.STEP, "tag": tag, "level": _guard_level(level),
                 "message": message[:GUARD_TEXT_MAX]}
        guard.LOG.append(entry)
        try:
            with open(os.path.join(guard.OUT, "log.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(_guard_utf8(json.dumps(entry, ensure_ascii=False)) + "\n")
        except (OSError, ValueError) as exc:   # the line stays in LOG; a slot that raised opens a window of its own
            print("APP guard: could not append to log.jsonl: %s" % exc, file=sys.stderr, flush=True)

    def watch():
        window, kind = _guard_blocking()
        if window is None:
            return
        found = {"exit": GUARD_EXIT, "kind": kind, "title": window.windowTitle(), "text": _guard_text(window),
                 "png": "guard-window.png", "t": now(), "log_tail": guard.LOG[-GUARD_LOG_TAIL:]}
        if not window.grab().save(os.path.join(guard.OUT, found["png"])):
            found["png"] = None
        try:
            text = _guard_utf8(json.dumps(found, indent=1, ensure_ascii=False))
            with open(os.path.join(guard.OUT, "guard.json"), "x", encoding="utf-8") as fh:
                fh.write(text)
        except (OSError, ValueError) as exc:   # QGIS still ends here, with the window's exit code
            print("APP guard: could not write guard.json: %s" % exc, file=sys.stderr, flush=True)
        print("APP guard: %s %r: QGIS ends with exit code %d" % (kind, found["title"], GUARD_EXIT), flush=True)
        sys.stderr.flush()
        os._exit(GUARD_EXIT)

    messages = QgsApplication.messageLog()
    if hasattr(messages, "messageReceivedWithFormat"):
        messages.messageReceivedWithFormat.connect(logged)
    else:
        messages.messageReceived[str, str, Qgis.MessageLevel].connect(logged)
    guard.listener = logged
    guard.watch = watch
    guard.TIMER = QTimer()
    guard.TIMER.timeout.connect(watch)
    guard.TIMER.start(GUARD_WATCH_MS)
    sys.modules["fiberq_app_guard"] = guard
    print(_guard_utf8("APP guard: watching from QGIS's start; records in %s" % guard.OUT), flush=True)


_guard_start()
