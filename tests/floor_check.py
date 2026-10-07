# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Parse and import every module in the plugin on the QGIS the floor declares.

``make floor-check`` runs this inside the image for the ``qgisMinimumVersion``
in ``fiberq/metadata.txt``. It is not a pytest file, because the point is to run
on the OLDEST Python any supported QGIS ships: ``qgis/qgis:3.22`` has Python
3.8, and pytest-qgis declares ``Requires-Python >= 3.10``, so it cannot even be
imported there.

That is a Python floor, not a QGIS one, and the distinction matters: the other
3.22 image, ``qgis/qgis:release-3_22``, ships Python 3.10.6 with the same QGIS
3.22.16, and the whole pytest suite DOES run there. CI runs both -- this script
on 3.8 for the syntax a newer Python would accept, and the real suite on
``release-3_22`` for behaviour. Neither replaces the other.

What it catches, and nothing else does:

* **Syntax a newer Python accepts.** ``fiberq/core/validation_report.py`` nested
  single quotes inside a single-quoted f-string in seven places. That is PEP 701,
  Python 3.12 and later. QGIS 3.22 ships Python 3.8, so the module was a hard
  ``SyntaxError`` there and "Export validation report" threw an unhandled error
  out of its Qt slot. QGIS 3.40 ships 3.12 and 3.44 ships 3.13, so both CI legs
  stayed green and it shipped in a release.
* **A package that takes its own submodules down.** ``addons/__init__.py``
  imports all six addons, so one bad import there makes every one of them
  unavailable -- including the fibre-break tool, reached lazily as
  ``from .addons.fiber_break import FiberBreakTool``, which must import the
  failing ``__init__`` first.
* **Imports from the wrong Qt module.** ``QAction`` and ``QShortcut`` moved from
  ``QtWidgets`` to ``QtGui`` in Qt6. Importing them from ``QtGui`` works from
  3.40 up and fails on 3.22, and because the failure is at module scope it took
  the whole ``fiberq/addons`` package and ``fiberq/ui/quick_toolbar`` with it.
  ``qgis.PyQt.QtWidgets`` serves both (verified on 3.22.16, 3.40.15, 3.44.15,
  4.0.3 and 4.2.3).

Both classes are invisible to flake8, to Bandit and to the Qt6 checker, and
invisible to a suite that never imports the module on the floor.

Two runs, every time, the same shape as ``make qt6-check``:

    fiberq/            must report ZERO findings
    tests/floor_seed/  must report at least FLOOR_MIN_SEED -- the self-test that
                       proves this script can still see a problem

A gate that silently stops reporting is the failure mode that second run guards.

Every module in ``fiberq/`` must import, with no allowlist. An optional
dependency belongs behind a function-level import, not behind a module that
cannot load -- that is what ``utils/compat.py`` is for. If a module legitimately
cannot import on the floor, the honest answer is to raise
``qgisMinimumVersion``, not to add an exception here.
"""
import importlib
import os
import pathlib
import subprocess
import sys
import traceback

PACKAGE = "fiberq"
SEED = os.path.join("tests", "floor_seed")
#: Six, and the sixth is the point. ``seed_broken_pkg`` contributes three: the
#: package, its broken submodule, and ``fine`` -- which only shows up if the
#: fresh-interpreter re-check in ``_import_failures`` is working. If that
#: regresses, the count drops to 5 and this gate refuses to call the package
#: clean. That is the whole reason the number is pinned rather than counted.
MIN_SEED = int(os.environ.get("FLOOR_MIN_SEED", "6"))


def _module_names(root, repo):
    """Every importable dotted module name under ``root``.

    Relative to ``repo``, not to the filesystem: ``root`` is absolute so this
    works from any working directory, and taking ``.parts`` of an absolute path
    would build names like ``.src.fiberq.utils``.
    """
    names = []
    for path in sorted(root.rglob("*.py")):
        parts = list(path.relative_to(repo).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            names.append(".".join(parts))
    return names


def _syntax_failures(root):
    """Every file that does not parse -- not just the first one.

    ``compileall`` stops at the first error per file and wants to write
    bytecode, which fails on the read-only mount CI uses. Compiling each file in
    memory reports every file. Note that Python still raises only the FIRST
    ``SyntaxError`` per file, so a file with several (validation_report.py had
    seven) needs a re-run per fix; the output says so.
    """
    failures = []
    for path in sorted(root.rglob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            failures.append((str(path), exc.lineno, exc.msg))
        except (OSError, UnicodeDecodeError) as exc:
            failures.append((str(path), None, f"{type(exc).__name__}: {exc}"))
    return failures


#: Imports one module in a fresh interpreter. Used only to re-check the
#: submodules of a package whose own ``__init__`` failed -- see
#: ``_import_failures``.
_CHILD = """
import sys, importlib
sys.path.insert(0, sys.argv[2])
from qgis.core import QgsApplication
QgsApplication.setPrefixPath('/usr', True)
_app = QgsApplication([], False)
_app.initQgis()
importlib.import_module(sys.argv[1])
"""


def _import_failures(root, repo, already_broken):
    """Every module that will not import, skipping ones that did not parse.

    A file that does not parse raises ``SyntaxError`` from ``import_module``
    too; listing it twice is noise, so the syntax pass owns it. Everything else
    -- a wrong Qt module, a missing name, a module-scope call that fails --
    shows up here.

    **Why the second pass.** One interpreter is not enough. When a package's
    ``__init__`` imports its submodules and one of them fails, the ones that
    already succeeded stay in ``sys.modules``, while the package itself is
    removed. Importing such a submodule afterwards then finds it cached and
    answers a false OK. Measured on qgis/qgis:3.22 with only
    ``addons/hotkeys.py`` broken: one interpreter reported 5 failures, a fresh
    one per module reported 7 -- and the two it missed were
    ``addons.fiber_break`` and ``addons.fiberq_preview``, the break-distance
    tool and a user-facing dialog. ``addons/__init__.py`` imports those before
    ``hotkeys``, which is the only reason they looked fine. An invisible
    allowlist in a gate whose docstring promises none.

    So: after the in-process pass, every module under a package that FAILED is
    re-checked in a fresh interpreter. On a clean tree no package fails, so this
    costs nothing -- zero subprocesses. It is only the failing run that pays,
    and a failing run is allowed to be slow.
    """
    failures = []
    for name in _module_names(root, repo):
        if name in already_broken:
            continue
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - any import failure IS the finding
            failures.append((name, exc, traceback.format_exc()))

    failed_packages = {name for name, _exc, _tb in failures}
    if not failed_packages:
        return failures

    reported = set(failed_packages)
    for name in _module_names(root, repo):
        if name in reported or name in already_broken:
            continue
        if not any(name.startswith(pkg + ".") for pkg in failed_packages):
            continue
        child = subprocess.run(
            [sys.executable, "-c", _CHILD, name, str(repo)],
            capture_output=True, text=True)
        if child.returncode != 0:
            tail = child.stderr.strip().splitlines() or ["(no stderr)"]
            failures.append((name, RuntimeError(tail[-1]),
                             "\n".join(tail[-6:]) + "\n  (fresh interpreter)"))
            reported.add(name)
    return failures


def _scan(root, repo):
    """``(syntax failures, import failures)`` for one tree."""
    syntax = _syntax_failures(root)
    broken = set()
    for path, _line, _msg in syntax:
        parts = list(pathlib.Path(path).relative_to(repo).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        broken.add(".".join(parts))
    return syntax, _import_failures(root, repo, broken)


def _report(label, syntax, imports):
    if syntax:
        print(f"\n{label} SYNTAX -- {len(syntax)} file(s) do not parse:")
        for path, line, msg in syntax:
            print(f"  {path}:{line}  {msg}")
        print("  (Python raises only the FIRST error per file -- re-run after each fix.)")
    if imports:
        print(f"\n{label} IMPORT -- {len(imports)} module(s) will not import:")
        for name, exc, trace in imports:
            print(f"\n  {name}")
            print(f"    {type(exc).__name__}: {exc}")
            for line in trace.strip().splitlines()[-6:]:
                print(f"    | {line}")


def main():
    version = ".".join(str(n) for n in sys.version_info[:3])
    repo = pathlib.Path(__file__).resolve().parent.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    package_root = repo / PACKAGE
    if not package_root.is_dir():
        print(f"ERROR: {package_root} is not a directory")
        return 3

    try:
        from qgis.core import Qgis, QgsApplication
    except ImportError:
        print("ERROR: no QGIS bindings on sys.path. Run this inside a qgis/qgis image, or")
        print("       with PYTHONPATH=/usr/share/qgis/python on QGIS 4.")
        return 3

    print(f"floor-check: QGIS {Qgis.QGIS_VERSION}, Python {version}")

    # A real QgsApplication, because module-scope code may touch the registry.
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()

    pkg_syntax, pkg_imports = _scan(package_root, repo)

    seed_root = repo / SEED
    seed_syntax, seed_imports = ([], [])
    if seed_root.is_dir():
        seed_syntax, seed_imports = _scan(seed_root, repo)
    seed_n = len(seed_syntax) + len(seed_imports)

    # The self-test comes FIRST: a clean package means nothing if this script
    # has stopped being able to see a problem.
    if not seed_root.is_dir():
        print(f"\nERROR: the self-test directory {SEED} is missing.")
        print("       Do not delete it -- see its README. Without it a green run proves nothing.")
        return 2
    if seed_n < MIN_SEED:
        print(f"\nERROR: self-test failed -- {seed_n} finding(s) in {SEED}, expected >= {MIN_SEED}.")
        print("       Either this script has stopped working, or the seeds were 'cleaned up'")
        print(f"       (see {SEED}/README.md). Do NOT trust a green run.")
        _report("seed", seed_syntax, seed_imports)
        return 2

    if pkg_syntax or pkg_imports:
        _report(PACKAGE, pkg_syntax, pkg_imports)
        print(f"\nfloor-check FAILED: {len(pkg_syntax)} unparsable, {len(pkg_imports)} unimportable in {PACKAGE}/.")
        print(f"qgisMinimumVersion in {PACKAGE}/metadata.txt promises this QGIS works.")
        print("Either fix it or raise that number -- do not add an exception to this script.")
        return 1

    total = len(_module_names(package_root, repo))
    print(f"floor-check: {total} modules in {PACKAGE}/ parse and import, 0 findings "
          f"(self-test saw {seed_n} findings in {SEED}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
