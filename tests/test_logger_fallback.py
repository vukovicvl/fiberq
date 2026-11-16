"""The logger must import, and log, when QGIS is not there.

``fiberq/utils/logger.py`` falls back to a stand-in for ``qgis.core.Qgis`` when the
QGIS bindings cannot be imported, so that code which logs can still be imported in
plain Python. Up to v1.6.0 the stand-in defined ``Qgis.Info`` while the module read
``Qgis.MessageLevel.Info`` when it was imported, so the import itself failed without
QGIS, and with it every module that imports the logger.

The test hides ``qgis`` in a fresh interpreter, so it checks the same thing wherever
it runs: on the QGIS legs, where the bindings are importable, and in plain Python,
where they are not.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

LOGGER = Path(__file__).resolve().parent.parent / "fiberq" / "utils" / "logger.py"

# Runs in a fresh interpreter: hide every qgis module, load logger.py by its path
# (the fiberq package itself needs QGIS), then log one warning.
_SCRIPT = textwrap.dedent('''
    import importlib.abc
    import importlib.util
    import sys


    class _HideQgis(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name == "qgis" or name.startswith("qgis."):
                raise ModuleNotFoundError("No module named " + repr(name), name=name)
            return None


    sys.meta_path.insert(0, _HideQgis())
    for loaded in list(sys.modules):
        if loaded == "qgis" or loaded.startswith("qgis."):
            del sys.modules[loaded]

    spec = importlib.util.spec_from_file_location("fiberq_logger_without_qgis", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.QGIS_AVAILABLE is False, "qgis was not hidden"
    module.get_logger("fiberq.test").warning("logged without QGIS")
''')


def test_the_logger_imports_and_logs_without_qgis():
    # A known level and no log file, whatever the caller's environment says.
    env = dict(os.environ, FIBERQ_LOG_LEVEL="WARNING", FIBERQ_LOG_FILE="")
    result = subprocess.run(
        # -B: the child writes no bytecode into the tested tree.
        [sys.executable, "-B", "-c", _SCRIPT, str(LOGGER)],
        capture_output=True, text=True, timeout=60, env=env,
    )
    assert result.returncode == 0, (
        "fiberq/utils/logger.py does not import or log without QGIS:\n" + result.stderr[-3000:])
    assert "[FiberQ] fiberq.test - WARNING - logged without QGIS" in result.stdout, result.stdout
