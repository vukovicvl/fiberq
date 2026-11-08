"""Starting FiberQ calls nothing that is not there (v1.6.0 QA finding Q19).

``initGui`` called ``self._ensure_global_shortcuts()``, a method v1.2.2 removed
(b704d95) -- since FiberQ's first commit it had been a stub that returned at
once, and the shortcuts come from ``addons/hotkeys.register_hotkeys``. The call
raised AttributeError at every start, alone in a handler that logged it at
debug level, which a default install (``FIBERQ_LOG_LEVEL`` WARNING) never
shows. This runs ``initGui`` with FiberQ's logging at DEBUG and fails on any
AttributeError it logs.

Why a subprocess: ``initGui()`` leaves toolbars, translators and project hooks
behind, which in-process would reach every later test (the same reason as
tests/test_toolbar_icons.py, whose fake iface this borrows), and the log level
is read once, when ``fiberq.utils.logger`` is imported.
"""
import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for the child. The suite has no timeout plugin.
TIMEOUT_S = 120

#: A line the child logs through FiberQ's own logger before initGui, so a
#: capture that hears nothing fails instead of passing.
PROBE = "FiberQ test: is the log heard here?"

DRIVER = '''
import json
import os
import sys
from unittest import mock

sys.path.insert(0, {repo!r})

from qgis.core import QgsApplication

QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()

from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow, QMessageBox, QToolBar

# A dialog raised during initGui would wait for a click until the timeout.
for kind in ("critical", "warning", "information", "question"):
    setattr(QMessageBox, kind, staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))

from fiberq.utils import logger as fiberq_logger

LINES = []
_emit = fiberq_logger.QgsLogHandler.emit


def emit(self, record):
    """Every FiberQ logger has one of these handlers; keep what it is given."""
    LINES.append([record.name, record.levelname, record.getMessage()])
    return _emit(self, record)


fiberq_logger.QgsLogHandler.emit = emit


class Iface:
    """What initGui() really uses; the rest answers with a MagicMock."""

    def __init__(self):
        self._window = QMainWindow()
        self._canvas = QgsMapCanvas(self._window)
        self._window.setCentralWidget(self._canvas)
        self._mocks = {{}}

    def mainWindow(self):
        return self._window

    def mapCanvas(self):
        return self._canvas

    def addToolBar(self, name):
        return QToolBar(name, self._window)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self.__dict__["_mocks"].setdefault(name, mock.MagicMock(name=name))


fiberq_logger.get_logger("fiberq.tests").debug({probe!r})
probe = list(LINES)

from fiberq.main_plugin import FiberQPlugin

# initGui() arms a 2 s one-shot schema migration; nothing here waits for it.
FiberQPlugin._run_schema_migrations = lambda self: None
plugin = FiberQPlugin(Iface())
del LINES[:]
plugin.initGui()

print("RESULT " + json.dumps({{"probe": probe, "initGui": LINES}}), flush=True)
sys.stdout.flush()
os._exit(0)
'''


@pytest.fixture(scope="module")
def logged(tmp_path_factory):
    """``{"probe": [...], "initGui": [...]}``: ``[logger, level, message]`` lines."""
    folder = tmp_path_factory.mktemp("initgui_log")
    script = folder / "initgui_log.py"
    script.write_text(DRIVER.format(repo=REPO_ROOT, probe=PROBE), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", TMPDIR=str(folder),
                       FIBERQ_LOG_LEVEL="DEBUG", FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(folder),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT ")]
    assert done.returncode == 0 and lines, f"returncode {done.returncode}\n{output}"
    return json.loads(lines[-1][len("RESULT "):])


def test_the_child_hears_fiberq_at_debug_level(logged):
    """A check that has never fired is not a check."""
    assert ["fiberq.tests", "DEBUG", PROBE] in logged["probe"], logged["probe"]


def test_initgui_logs_no_attribute_error(logged):
    missing = [line for line in logged["initGui"] if "has no attribute" in line[2]]
    assert not missing, missing
