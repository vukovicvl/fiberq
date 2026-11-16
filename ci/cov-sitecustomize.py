# SPDX-License-Identifier: GPL-3.0-or-later
"""Start coverage in every Python process of the test-coverage stage, child processes included.

ci/test.sh copies this file to $CI_WORK/cov-hook/sitecustomize.py and puts that
folder first on PYTHONPATH. The pinned tools are installed with pip --target into
a folder on PYTHONPATH, which is not a site folder, so Python never reads the
a1_coverage.pth that coverage installs there: this file does its job. coverage's
[run] patch = subprocess passes the configuration to the children in
COVERAGE_PROCESS_CONFIG; where neither variable is set, nothing starts. Then the
sitecustomize.py this file shadows, if there is one (the QGIS images' own, in
/usr/lib/python3.X), runs as it would have.
"""
import os
import sys

if os.environ.get("COVERAGE_PROCESS_CONFIG") or os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage
    except ImportError:
        pass
    else:
        coverage.process_startup()


def _run_shadowed():
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in sys.path:
        if not folder or os.path.abspath(folder) == here:
            continue
        shadowed = os.path.join(folder, "sitecustomize.py")
        if os.path.isfile(shadowed):
            import runpy
            runpy.run_path(shadowed, run_name="sitecustomize")
            return


_run_shadowed()
