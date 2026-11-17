"""The ``--code`` script of the app stages: it runs the start that ``APP_START`` names (tests/app/smoke.py).

ci/app-smoke.sh starts QGIS with ``--code tests/app/start.py``. QGIS runs this file before its event loop starts,
and with no ``__file__``, so it takes the tests folder from ``APP_TESTS`` and appends it to ``sys.path``. Appended,
never put first, so that nothing in the tested tree can stand in for a module QGIS already has; and the tested
tree's own root is never added, so ``fiberq`` can only come from the profile, where the install start put it.
``app.runner.begin()`` then runs the start once the event loop runs, and QGIS ends with the start's exit code.

A missing variable, or a start that ``STARTS`` does not name, raises here; QGIS shows that in a window, and the
startup guard (tests/app/guard.py), which still watches until the runner takes over, ends QGIS with exit code 3.
"""
import os
import sys


def main():
    """Run the start that ``APP_START`` names, once QGIS's event loop runs."""
    sys.path.append(os.environ["APP_TESTS"])

    from app import smoke
    from app.runner import begin

    start = os.environ["APP_START"]
    begin(smoke.STARTS[start], start=start)


main()
