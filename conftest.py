"""Shared pytest fixtures for FiberQ.

Lives at the repo root so pytest makes the root importable (`import fiberq`
resolves to the fiberq/ package). pytest-qgis bootstraps a headless
QgsApplication automatically and exposes fixtures such as `qgis_app` and
`qgis_iface` to every test. Add project-wide fixtures here as the suite grows
(WP5).

Note: this file is loaded very early, so it avoids importing `fiberq` at module
top level; fixtures resolve paths from __file__ instead.

The block at the end belongs to the fast stage, the pure stage of ci/
(ci/README.md): it does nothing unless FIBERQ_PURE=1.
"""
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope="session")
def fiberq_dir():
    """Absolute path to the fiberq/ plugin package."""
    return os.path.join(REPO_ROOT, "fiberq")


@pytest.fixture(scope="session")
def city_xs_dataset(qgis_app, tmp_path_factory):
    """The WP4 benchmark's XS city project, generated once for the whole session.

    Several test modules want it and it costs a second and a half, so it is
    built once. Nothing is committed:
    `tests/fixtures/` holds the generator, not its output -- `.gitignore` matches
    neither `*.gpkg` nor `*.qgz`, so a generated dataset would sit in
    `git status` waiting to be added.

    Returns the generator's `meta` dict, which carries the paths (`gpkg`, `qgz`,
    `manifest`), the row digest and the per-layer counts. Deliberately no
    QgsProject: a project that outlived the test which read it would be
    destroyed during interpreter teardown, and that is a reliable segfault on
    QGIS 4.0. Each test reads the project into a local one instead.
    """
    import sys

    from qgis.core import QgsMapLayer
    if not hasattr(QgsMapLayer, "setId"):
        pytest.skip(
            "QgsMapLayer.setId() arrived in QGIS 3.36 and the benchmark fixture "
            "pins every layer id with it. Generating the dataset therefore needs "
            "3.36+; reading one does not -- a project written on 3.44 reads back "
            "on 3.22 with all 24 ids and the project entries intact (measured). "
            "CI runs 3.44 and 4.0, so the pinned digest is still gated.")

    fixtures = os.path.join(REPO_ROOT, "tests", "fixtures")
    if fixtures not in sys.path:
        sys.path.insert(0, fixtures)
    import make_city_project

    folder = tmp_path_factory.mktemp("city_xs")
    return make_city_project.generate(size="XS", out=str(folder / "city_XS.gpkg"))


@pytest.fixture(scope="session")
def city_xs4_dataset(city_xs_dataset, tmp_path_factory):
    """Size XS4, the ratio partner of XS: 7,707 features against 1,895 (x4.07).

    WP4 plan 1.6: work that grows with the square of the project grows ~16x
    between the two, linear work ~4x. Generated once per session (~2.5 s on
    3.44.15). It depends on ``city_xs_dataset`` for that fixture's skip below
    QGIS 3.36 and for its ``sys.path`` setup.
    """
    import make_city_project

    folder = tmp_path_factory.mktemp("city_xs4")
    return make_city_project.generate(size="XS4", out=str(folder / "city_XS4.gpkg"))


@pytest.fixture(scope="session")
def sample_project_path():
    """Path to the demo GeoPackage fixture (added in Phase 0 / WP6).

    Tests that need a real project skip cleanly until the fixture exists, so
    the suite stays green before the demo dataset lands.
    """
    path = os.path.join(REPO_ROOT, "tests", "fixtures", "sample_project.gpkg")
    if not os.path.exists(path):
        pytest.skip("tests/fixtures/sample_project.gpkg not present yet")
    return path


# ---------------------------------------------------------------------------
# The fast stage: the test files that run with no QGIS installed (the pure
# stage of ci/, ci/README.md).
#
# Active only when FIBERQ_PURE=1, which ci/test.sh sets for that stage alone.
# Without it nothing below runs: no hook is defined and no import changes, so
# the QGIS legs collect and run exactly what they did before. With it:
#   1. qgis, PyQt5, PyQt6, sip and osgeo cannot be imported, whether they are
#      installed or not, here and in every Python child process that inherits
#      the environment (a sitecustomize.py first on PYTHONPATH). So the stage
#      runs the same tests on a machine with QGIS and GDAL as in a plain
#      Python image.
#   2. fiberq.core, fiberq.utils and fiberq.models load without running their
#      __init__.py, which imports the QGIS managers: "from fiberq.core import
#      gpkg_target" runs gpkg_target.py and nothing else. A name that only a
#      package __init__.py defines cannot be imported here.
#   3. Every test file is collected, and picked if it imports. A file whose
#      import stops on a hidden module is left out, with its reason; any other
#      import error stays a collection error, and the stage fails. So does a
#      file that skips itself as a whole, unless the skip is
#      pytest.importorskip of a hidden module or is raised inside the except
#      that caught one: its tests would count where it runs and not where it
#      skips.
#   4. A test that asks for a pytest-qgis fixture (qgis_*) or carries the
#      qgis marker is deselected: pytest-qgis is not loaded here.
#   5. The stage turns a test's failure into a skip, with a reason that starts
#      "pure stage:", only when a hidden module caused it: the exception the
#      test ends with is that module's ModuleNotFoundError, or a child process
#      it started died of one, uncaught (the children's sitecustomize.py then
#      writes PURE_CHILD to the child's stderr). An xfail that such an error
#      ended, and a skip or an xfail called while handling one, become the
#      same skip, whatever their reason (so a skip there must not depend on the
#      machine). Any other failure fails, also one raised while handling a
#      hidden module's ImportError. pytest.importorskip of a hidden module
#      skips with a reason that ends with PURE_MARK, also when the test gives
#      its own reason.
# FIBERQ_PURE_REPORT names a new file for the record: one tab-separated line
# per picked file, left-out file and deselected test. It is taken out of the
# environment, so a pytest that a test starts does not write there.
# ---------------------------------------------------------------------------
if os.environ.get("FIBERQ_PURE") == "1":
    import importlib.abc
    import importlib.machinery
    import re
    import sys
    import tempfile
    import unittest

    PURE_HIDDEN = ("qgis", "PyQt5", "PyQt6", "sip", "osgeo")
    PURE_STUBS = ("fiberq.core", "fiberq.utils", "fiberq.models")
    PURE_MARK = "(hidden in the pure stage)"
    PURE_CHILD = "fiberq pure stage: this child process stopped on a hidden module:"
    _pure_report = os.environ.pop("FIBERQ_PURE_REPORT", "")
    _pure_record = []

    def _pure_hidden(name):
        """True for a hidden module or one of its submodules."""
        return isinstance(name, str) and name.split(".", 1)[0] in PURE_HIDDEN

    def _pure_text(value):
        """One field of the record: tabs and line breaks become single spaces."""
        return " ".join(str(value).split())

    class _PureHider(importlib.abc.MetaPathFinder):
        """The hidden modules are missing, whether they are installed or not."""

        def find_spec(self, name, path=None, target=None):
            if _pure_hidden(name):
                raise ModuleNotFoundError("No module named %r %s" % (name, PURE_MARK), name=name)
            return None

    class _PureStubLoader(importlib.abc.Loader):
        """Creates the package module and runs nothing of its __init__.py."""

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            return None

    class _PureStubFinder(importlib.abc.MetaPathFinder):
        """fiberq.core, fiberq.utils and fiberq.models: their folders, without their __init__.py."""

        def find_spec(self, name, path=None, target=None):
            if name not in PURE_STUBS:
                return None
            leaf = name.rsplit(".", 1)[1]
            where = [os.path.join(p, leaf) for p in (path or ())
                     if os.path.isfile(os.path.join(p, leaf, "__init__.py"))]
            if not where:
                return None
            spec = importlib.machinery.ModuleSpec(name, _PureStubLoader(), is_package=True)
            spec.submodule_search_locations = where
            return spec

    _pure_early = sorted({m.split(".", 1)[0] for m in sys.modules if _pure_hidden(m) or m in PURE_STUBS})
    if _pure_early:
        raise RuntimeError(
            "the fast stage (FIBERQ_PURE=1) hides qgis, PyQt5, PyQt6, sip and osgeo, but %s was imported before "
            "conftest.py: run pytest with -p no:pytest_qgis --disable-plugin-autoload" % ", ".join(_pure_early))
    sys.meta_path.insert(0, _PureHider())
    sys.meta_path.insert(1, _PureStubFinder())

    _pure_importorskip_pytest = pytest.importorskip

    def _pure_importorskip(modname, minversion=None, reason=None, **kwargs):
        """pytest.importorskip, whose skip ends with PURE_MARK when a hidden module stops the import, also when the
        test gives its own reason (pytest then uses that reason as it is)."""
        __tracebackhide__ = True
        if reason is not None:
            try:
                importlib.import_module(modname)
            except ImportError as exc:   # pytest's own call below skips, or raises, as it would
                if isinstance(exc, ModuleNotFoundError) and _pure_hidden(exc.name):
                    reason = "%s %s" % (reason, PURE_MARK)
        return _pure_importorskip_pytest(modname, minversion, reason, **kwargs)

    pytest.importorskip = _pure_importorskip

    # The child processes' hider: the same rule, as a sitecustomize.py that a
    # child Python imports at start-up from the first folder on PYTHONPATH.
    # When a child dies of a hidden module's error, uncaught, it says so on its
    # stderr after the traceback, in the words of PURE_CHILD (rule 5).
    _pure_site = tempfile.mkdtemp(prefix="fiberq-pure-site-")
    with open(os.path.join(_pure_site, "sitecustomize.py"), "x", encoding="utf-8") as _pure_fh:
        _pure_fh.write("\n".join([
            '"""The fast stage: written by conftest.py for the tests\' child processes."""',
            "import importlib.abc",
            "import sys",
            "",
            "HIDDEN = %r" % (PURE_HIDDEN,),
            "MARK = %r" % (PURE_MARK,),
            "CHILD = %r" % (PURE_CHILD,),
            "",
            "",
            "class PureHider(importlib.abc.MetaPathFinder):",
            "    def find_spec(self, name, path=None, target=None):",
            "        if name.split('.', 1)[0] in HIDDEN:",
            "            raise ModuleNotFoundError('No module named %r %s' % (name, MARK), name=name)",
            "        return None",
            "",
            "",
            "sys.meta_path.insert(0, PureHider())",
            "_excepthook = sys.excepthook",
            "",
            "",
            "def _pure_excepthook(kind, value, tb):",
            "    _excepthook(kind, value, tb)",
            "    if issubclass(kind, ModuleNotFoundError) and (value.name or '').split('.', 1)[0] in HIDDEN:",
            "        sys.stderr.write('%s %s\\n' % (CHILD, value.name))",
            "",
            "",
            "sys.excepthook = _pure_excepthook",
            ""]))
    os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (_pure_site, os.environ.get("PYTHONPATH")) if p)

    def _pure_rel(path):
        return os.path.relpath(str(path), REPO_ROOT).replace(os.sep, "/")

    class _PureModule(pytest.Module):
        """A test file of the fast stage: left out, with its reason, when its import stops on a hidden module."""

        def collect(self):
            try:
                self.obj   # imports the test file
            except self.CollectError as err:
                cause = err.__cause__
                if isinstance(cause, ModuleNotFoundError) and _pure_hidden(cause.name):
                    _pure_record.append(("left_out", _pure_rel(self.path), "needs " + cause.name.split(".", 1)[0]))
                    return []
                if isinstance(cause, ImportError) and cause.name in PURE_STUBS:
                    raise self.CollectError(
                        "%s\nThe fast stage loads %s without its __init__.py, so a name that only the package "
                        "defines cannot be imported: import it from its module (from %s.<module> import ...), "
                        "and in a test file that needs QGIS, import qgis first." % (err, cause.name, cause.name)
                    ) from cause
                raise
            except (pytest.skip.Exception, unittest.SkipTest) as exc:   # the whole file skips itself
                ctx = exc.__context__   # skipped while handling a hidden module's error: left out, as on import
                if isinstance(ctx, ModuleNotFoundError) and _pure_hidden(ctx.name):
                    _pure_record.append(("left_out", _pure_rel(self.path), "needs " + ctx.name.split(".", 1)[0]))
                    return []
                if PURE_MARK not in str(exc):
                    raise self.CollectError(
                        "%s skips itself as a whole (%s), and not while handling a hidden module's ImportError. In "
                        "the fast stage a test file skips itself only for a hidden module, in a form the stage sees: "
                        "qgis imported at the top, pytest.importorskip(\"qgis\"), or a skip inside the except block "
                        "of its qgis import (not after that block, behind a flag); for any other reason it skips "
                        "inside its tests (pytest.mark.skipif), so that each test counts wherever the stage runs" % (
                            _pure_rel(self.path), _pure_text(exc))) from exc
                _pure_record.append(("left_out", _pure_rel(self.path), "skips itself: " + _pure_text(exc)))
                raise
            _pure_record.append(("picked", _pure_rel(self.path), ""))
            return super().collect()

    def pytest_pycollect_makemodule(module_path, parent):
        return _PureModule.from_parent(parent, path=module_path)

    def pytest_collection_modifyitems(config, items):
        keep, drop = [], []
        for item in items:
            why = sorted(n for n in getattr(item, "fixturenames", ()) if n.startswith("qgis_"))
            if item.get_closest_marker("qgis") is not None:
                why.append("the qgis marker")
            if why:
                drop.append(item)
                _pure_record.append(("deselected", item.nodeid, ", ".join(why)))
            else:
                keep.append(item)
        if drop:
            config.hook.pytest_deselected(items=drop)
            items[:] = keep

    def _pure_skip_cause(exc):
        """The hidden module whose ModuleNotFoundError was being handled when exc, a skip or an xfail, was raised."""
        while isinstance(exc, (pytest.skip.Exception, pytest.xfail.Exception, unittest.SkipTest)):
            exc = exc.__context__
        if isinstance(exc, ModuleNotFoundError) and _pure_hidden(exc.name):
            return exc.name.split(".", 1)[0]
        return None

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(item, call):
        raised = call.excinfo.value if call.excinfo is not None else None   # before unittest's hook replaces it
        report = yield
        if call.when not in ("setup", "call"):
            return report
        exc = call.excinfo.value if call.excinfo is not None else None
        xfailed = report.skipped and hasattr(report, "wasxfail")   # skipping.py has already turned an xfail
        if report.failed or xfailed:
            child = re.search(re.escape(PURE_CHILD) + r" ([A-Za-z0-9_]+)", str(report.longrepr))
            why = None
            if isinstance(exc, ModuleNotFoundError) and _pure_hidden(exc.name):
                why = "needs %s while it runs" % exc.name.split(".", 1)[0]
            elif child is not None:
                why = "a child process needs %s" % child.group(1)
            elif xfailed and _pure_skip_cause(exc):   # pytest.xfail() called while handling a hidden module's error
                why = "needs %s while it runs" % _pure_skip_cause(exc)
            if why is not None:
                if xfailed:
                    del report.wasxfail
                report.outcome = "skipped"
                report.longrepr = (str(item.path), (item.location[1] or 0) + 1, "Skipped: pure stage: " + why)
        elif report.skipped:
            # pytest.skip(), unittest.SkipTest or TestCase.skipTest() called while handling a hidden module's error
            cause = _pure_skip_cause(exc) or _pure_skip_cause(raised)
            if cause is not None:
                report.longrepr = (str(item.path), (item.location[1] or 0) + 1,
                                   "Skipped: pure stage: needs %s while it runs" % cause)
        return report

    def pytest_terminal_summary(terminalreporter):
        kinds = [kind for kind, _name, _why in _pure_record]
        terminalreporter.write_sep("-", "pure stage: %d test files picked, %d left out, %d tests deselected" % (
            kinds.count("picked"), kinds.count("left_out"), kinds.count("deselected")))
        for kind, name, why in sorted(_pure_record):
            if kind != "picked":
                terminalreporter.write_line("%s: %s (%s)" % (kind.replace("_", " "), name, _pure_text(why)))

    def pytest_sessionfinish(session, exitstatus):
        if _pure_report:
            with open(_pure_report, "x", encoding="utf-8") as fh:
                fh.writelines("\t".join(_pure_text(field) for field in row) + "\n" for row in sorted(_pure_record))
