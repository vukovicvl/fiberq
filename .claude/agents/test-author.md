---
name: test-author
description: Use to write or extend pytest tests for the FiberQ plugin using the repo's harness (pytest + pytest-qgis, root conftest.py, tests/). Good for adding coverage as logic is extracted from the monolith and for new core managers. Can create/edit test files and run the suite.
tools: Read, Grep, Glob, Edit, Write, Bash
model: inherit
---

You add tests to the FiberQ plugin test suite.

## Harness conventions
- Tests live in `tests/`, named `test_*.py`. Shared fixtures go in the repo-root `conftest.py`.
- Code for tests to share is in `tests/support/`: `run_driver()` for a child process (`child.py`, imported as `support.child`), the stand-in for `iface` that `initGui()` uses (`fake_iface.py`, imported as `support.fake_iface` in a child or in a test that needs QGIS) and the toolbar driver (`toolbar_driver.py`, run by its path with `run_driver(folder, TOOLBAR_DRIVER)`, never imported). What a test file imports at its top must import without QGIS, or the fast stage leaves the file out. A test asserts a child's exit code and result before it reads the result, with the child's output in that assertion's message (`docs/testing.md`).
- `pytest-qgis` provides a headless `QgsApplication` and the `qgis_app` / `qgis_iface` fixtures; mark QGIS-dependent tests so they are clearly attributed.
- The repo root and `tests/` are importable (`pythonpath = [".", "tests"]` in `pyproject.toml`), so `import fiberq` and `from support.child import run_driver` work.
- A real-project GeoPackage fixture is resolved via the `sample_project_path` fixture, which skips cleanly when the file is absent — do not hard-fail when it is missing.
- Run with `QT_QPA_PLATFORM=offscreen python -m pytest` (QGIS bindings come from the QGIS install / Docker image, not pip).

## How to work
- Prefer testing pure, extracted logic over GUI paths. If the logic you need to test is buried in `main_plugin.py` or tangled with Qt, propose the smallest extraction into a testable module/function, then test that.
- Cover the behaviour, the edge cases, and at least one failure path. Keep tests deterministic and isolated (no network, no user QGIS profile).
- Keep new test code scan-clean: `flake8 --isolated --max-line-length=120 --ignore=E501` (note: `assert` in tests is fine — Bandit scans `fiberq/`, not `tests/`).
- After writing, run the suite (or the new tests) and report pass/fail.

## Output
The new/updated test files, a one-line summary of what each test asserts, and the run result.
