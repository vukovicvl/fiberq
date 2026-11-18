"""Code that drives the real QGIS desktop app, for the app stages. It holds no tests itself.

- ``runner.py``: the app runner. A scenario, a plain function, does what a person does through it and records what
  it sees, as checks with stable ids, notes and screenshots. The runner answers the windows the scenario expects,
  fails on a window QGIS opens for a Python error and on any other window that waits for an answer, ends the run
  at a deadline, writes ``report.json`` and ends QGIS with the run's exit code. It imports QGIS and the standard
  library, never FiberQ, so any scenario can use it.
- ``selftest.py``: a driver that runs the runner headless, with ``FakeIface``, one case at a time, for
  ``tests/test_app_runner.py``. It runs as a script, in a child process.
- ``guard.py``: run by QGIS through ``PYQGIS_STARTUP`` before it loads any plugin. It keeps the message log from
  QGIS's start and ends QGIS (exit 3) on a window that would block it before the runner starts.
- ``smoke.py``: FiberQ's two starts: the install from the zip, and a short core workflow with a reload.
- ``start.py``: the ``--code`` script. ``ci/app-smoke.sh`` starts QGIS with ``--code tests/app/start.py``, and it
  runs the start that ``APP_START`` names.

A script puts ``tests/`` on its ``sys.path`` and imports the modules here as ``app.<module>``; code here imports
another module here the same way, never by its bare name. Python puts a script's folder first on ``sys.path``, and
``selftest.py`` runs from this folder, so no module here may be named like a standard-library, QGIS or installed
module. No file here is named ``test_*.py``, so pytest never collects one.
"""
