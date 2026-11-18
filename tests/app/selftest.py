"""Run one case of the app runner headless, in a child process, for tests/test_app_runner.py.

A driver for ``run_driver(folder, <this file>)`` (``tests/support/child.py``), run as a script and never imported.
It reads ``options.json`` in its folder, ``{"case": <a key of CASES>, "deadline_s": <seconds>}``, starts a
QgsApplication of its own with a new, empty profile, shows ``FakeIface``'s main window at 800 x 600 and runs the
case's scenario with ``app.runner.Runner`` (start ``selftest``). The runner writes its records to ``out/`` in the
folder and ends the process as it ends QGIS: its last line is ``RESULT`` and a JSON object, then its exit code.

The cases, each with the exit code the runner must end with:

- ``pass`` (0): a blocking question answered Yes through ``expect``, a wait for a 300 ms timer, a wait for a
  message-log line logged 300 ms later, a screenshot of the main window and five checks that hold, the ids of
  which it declares first;
- ``fail`` (1): the same, but its fourth check fails: it records a wait that times out on a condition that
  raises;
- ``unexpected`` (3): a blocking question that nothing expects;
- ``error_window`` (3): a blocking ``QgsMessageViewer``, the window QGIS opens for a Python error;
- ``deadline`` (4): a wait longer than the deadline;
- ``raises`` (5): a scenario that raises;
- ``python_line`` (1): a line on QGIS's "Python error" tag, then a required check that there is none, which
  ends the run;
- ``answer_raises`` (5): the answer to an expected window looks for a button the window does not have;
- ``match_raises`` (5): the ``match`` of an expected window raises, an error of the window watch;
- ``undeclared_check`` (5): a check whose id ``expect_checks()`` did not declare;
- ``drop_down`` (5): a click on a toolbar button that opens a drop-down, which ``trigger()`` refuses.

It catches no exception, so that in the fast stage it dies of the hidden ``qgis`` (docs/testing.md).
"""
import json
import os
import sys
import tempfile

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The title of the question the cases ask.
QUESTION = "Question"

#: The message-log line the pass and fail cases wait for, and its tag: the line that ends FiberQ's deferred
#: migration, which the app smoke waits for.
LOG_TAG = "FiberQ UUID"
LOG_LINE = "UUID migration summary: logged by the runner's selftest"

#: The line the python_line case logs on QGIS's "Python error" tag.
PYTHON_LINE = "Traceback (most recent call last): a line the runner's selftest logs"

#: The title of the error window, as QGIS gives it for an error in Python code.
ERROR_TITLE = "An error has occurred while executing Python code:"

#: The object name of the toolbar the drop_down case adds, and the label (the tooltip) of its drop-down button.
DROP_TOOLBAR = "SelftestToolbar"
DROP_LABEL = "Drop-down"


def ask(r, title):
    """Ask a blocking question, as a plugin action does, and return the button clicked."""
    from qgis.PyQt.QtWidgets import QMessageBox

    box = QMessageBox(QMessageBox.Icon.Question, title, "Go on?",
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, r.iface.mainWindow())
    return box.exec()


def press(r, text):
    """An answer for ``r.expect()``: click the button ``text``."""
    def answer(w):
        r.press_button(w, text)
    return answer


def not_there():
    """A condition for ``r.wait_until()`` that raises, as one does while what it reads is not there yet."""
    raise LookupError("nothing there yet")


def answered(r, holds):
    """The pass case (``holds``) and the fail case."""
    from qgis.core import Qgis, QgsMessageLog
    from qgis.PyQt.QtCore import QTimer
    from qgis.PyQt.QtWidgets import QMessageBox

    from app.runner import message_box

    last = "holds" if holds else "fails"
    r.expect_checks(["question.answer", "waits.timer", "waits.log", "waits." + last, "end.windows"])
    r.step("question", "a question a plugin action asks, answered Yes")
    r.expect(message_box(QUESTION), press(r, "&Yes"), "question")
    r.check("answer", int(QMessageBox.StandardButton.Yes), int(ask(r, QUESTION)))
    r.step("waits", "a timer, then a message-log line, each waited for")
    fired = []
    QTimer.singleShot(300, lambda: fired.append(True))
    r.check("timer", True, r.wait_until(lambda: fired, 3000))
    mark = r.log_mark()
    QTimer.singleShot(300, lambda: QgsMessageLog.logMessage(LOG_LINE, LOG_TAG, Qgis.MessageLevel.Info))
    r.check("log", True, r.wait_for_log(LOG_TAG, "UUID migration summary", mark, 5000))
    r.screenshot("main window")
    if holds:
        r.check("holds", 2, 2, what="a check that holds")
    else:
        r.check("fails", True, r.wait_until(not_there, 300), what="a check that fails: a wait that times out")
    r.step("end", "every expected window came")
    r.check("windows", [], r.expected_left())


def scenario_pass(r):
    answered(r, True)


def scenario_fail(r):
    answered(r, False)


def scenario_unexpected(r):
    r.step("question", "a question that nothing expects")
    ask(r, "Nobody expects this")


def scenario_error_window(r):
    from qgis.gui import QgsMessageViewer

    r.step("error", "the window QGIS opens for an error in Python code")
    viewer = QgsMessageViewer(r.iface.mainWindow())
    viewer.setTitle(ERROR_TITLE)
    viewer.setMessageAsPlainText("Traceback (most recent call last): the runner's selftest")
    viewer.showMessage(True)   # blocking, as qgis.utils shows it when there is no active window


def scenario_deadline(r):
    r.step("wait", "a wait longer than the deadline")
    r.wait(5000)


def scenario_raises(r):
    r.step("raise", "a scenario that raises")
    raise ValueError("a scenario that raises")


def scenario_python_line(r):
    from qgis.core import Qgis, QgsMessageLog

    r.step("log", "a line on QGIS's Python error tag")
    mark = r.log_mark()
    QgsMessageLog.logMessage(PYTHON_LINE, "Python error", Qgis.MessageLevel.Critical)
    r.wait_until(lambda: r.log_since(mark, "Python error"), 3000)
    r.require("no_python_lines", [], r.python_problems(mark))
    # not reached: require() ended the run with exit 1; this exit 5 would show that it did not
    raise AssertionError("require() let the run go on after its check failed")


def scenario_answer_raises(r):
    from app.runner import message_box

    r.step("question", "a question whose answer looks for a button it does not have")
    r.expect(message_box(QUESTION), press(r, "Maybe"), "question")
    ask(r, QUESTION)


def scenario_match_raises(r):
    r.step("question", "a question that the match of an expected window raises on")

    def broken(w):
        raise RuntimeError("a match that raises")
    r.expect(broken, press(r, "&Yes"), "question")
    ask(r, QUESTION)


def scenario_undeclared_check(r):
    r.expect_checks(["check.declared"])
    r.step("check", "a check that expect_checks() declared, then one that it did not")
    r.check("declared", True, True)
    r.check("undeclared", True, True)


def scenario_drop_down(r):
    from qgis.PyQt.QtWidgets import QMenu, QToolBar, QToolButton

    r.step("drop_down", "a click on a toolbar button that opens a drop-down, as each of FiberQ's drop-downs does")
    window = r.iface.mainWindow()
    bar = QToolBar("Selftest", window)
    bar.setObjectName(DROP_TOOLBAR)
    window.addToolBar(bar)
    menu = QMenu(window)
    menu.addAction("Entry")
    button = QToolButton()
    button.setToolTip(DROP_LABEL)
    button.setMenu(menu)
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    bar.addWidget(button)
    r.wait_until(button.isVisible, 3000, what="the drop-down's button shown")
    r.trigger(r.entry(DROP_TOOLBAR, DROP_LABEL))


CASES = {"pass": scenario_pass, "fail": scenario_fail, "unexpected": scenario_unexpected,
         "error_window": scenario_error_window, "deadline": scenario_deadline, "raises": scenario_raises,
         "python_line": scenario_python_line, "answer_raises": scenario_answer_raises,
         "match_raises": scenario_match_raises, "undeclared_check": scenario_undeclared_check,
         "drop_down": scenario_drop_down}


def main():
    with open("options.json", encoding="utf-8") as fh:
        options = json.load(fh)
    scenario = CASES[options["case"]]
    # a new, empty profile, before anything Qt: no user's, checkout's or other test's settings are read or written
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = tempfile.mkdtemp(prefix="fiberq-selftest-profile-")
    sys.path[:0] = [TESTS]

    from qgis.core import QgsApplication

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], True)
    app.initQgis()

    from app.runner import Runner
    from support.fake_iface import FakeIface

    iface = FakeIface()
    iface.mainWindow().resize(800, 600)
    iface.mainWindow().show()
    runner = Runner("selftest", out=os.path.join(os.getcwd(), "out"), deadline_s=options["deadline_s"], iface=iface)
    runner.run(scenario)


if __name__ == "__main__":
    main()
