"""Run a driver script in a child Python and read back what it prints.

A test that starts QGIS, or the plugin's ``initGui()`` and ``unload()``, does it in a child process: a crash
there fails that test and not the whole run, and what ``initGui()`` leaves behind (toolbars, translators,
project hooks) never reaches a later test. The driver prints one line, ``RESULT`` and a JSON value, and ends
with ``os._exit(0)``.

This module imports only the standard library, so the fast stage still picks a test file that imports it.
The child gets this process's environment with ``PYTHONPATH`` in it, so the fast stage's import hider and the
coverage stage's start-up hook reach it. A test asserts the child's exit code and result before it reads the
result, with ``output`` in that assertion's message: the fast stage turns a child that died of a hidden module
into a skip only when that output is in the failure (docs/testing.md).
"""
import json
import os
import subprocess
import sys

#: The toolbar driver, run as a script by its path; it is never imported.
TOOLBAR_DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "toolbar_driver.py")

#: Wall-clock ceiling for a child. The suite has no timeout plugin.
TIMEOUT_S = 120


def run_driver(folder, script, timeout=TIMEOUT_S):
    """Run the driver ``script`` with this Python, in ``folder``: ``(returncode, result, output)``.

    The child draws offscreen, keeps its temporary files in ``folder`` and writes no FiberQ log file.
    ``output`` is its stdout and stderr together. ``result`` is the JSON of its last ``RESULT`` line, or None
    when it printed none or that line is not JSON (in that case the reason is added to ``output``).
    """
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(folder), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(folder),
                          env=environment, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT ")]
    result = None
    if lines:
        try:
            result = json.loads(lines[-1][len("RESULT "):])
        except ValueError as exc:   # a line cut short: the caller's assertion shows the output, and why
            output += "\nrun_driver: the last RESULT line is not JSON (%s)\n" % exc
    return done.returncode, result, output
