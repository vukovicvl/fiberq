# Declared-floor seeds — deliberately broken, do not fix

These files **intentionally** use syntax and imports that the plugin's declared floor
rejects. They are the self-test for `make floor-check`: the target scans this directory as
well as `fiberq/`, and **fails if it reports fewer than six findings here** (`FLOOR_MIN_SEED`).

Why: a gate that stops reporting goes quietly green and stops protecting the release.
Both defects this gate exists for shipped through a green CI, a clean flake8, a clean
Bandit and a clean Qt6 check — nothing was watching the floor. Seeding known-bad code
proves the gate can still see a problem before it is allowed to call the plugin clean.

| File | Seeds | Fails on | Findings |
|---|---|---|---|
| `seed_pep701.py` | single quotes nested inside a single-quoted f-string | Python < 3.12 (`qgis/qgis:3.22` ships 3.8) | 1 |
| `seed_walrus_py312.py` | a type-parameter list (`def f[T]()`), PEP 695 | Python < 3.12 | 1 |
| `seed_qt6_import.py` | `QAction`/`QShortcut` from `qgis.PyQt.QtGui`, their Qt6 home | QGIS 3.22 (Qt5 keeps them in `QtWidgets`) | 1 |
| `seed_broken_pkg/` | a package whose `__init__` imports a good submodule **before** a bad one | QGIS 3.22 | 3 |

**Six findings from four seeds**, and the arithmetic matters. `seed_broken_pkg`
contributes three: the package, its `broken` submodule, and `fine` — which imports
perfectly well on its own. `fine` is a finding because no user can reach it through a
package whose `__init__` raises, and it is reported **only** if the gate re-checks a
failed package's submodules in a fresh interpreter.

That is what the pinned number really guards. The first version of this gate imported
everything in one interpreter, so `fine` was found already cached in `sys.modules` and
reported OK — measured on the real package, it under-reported `fiberq/addons` as 5
broken modules when the truth was 7, silently excusing `addons.fiber_break` and
`addons.fiberq_preview`. If that re-check ever regresses, the count here falls to 5 and
the gate refuses to call the plugin clean instead of going quietly green.

Rules for this directory:

- **Never "clean up" these files.** `tests/test_floor_seed.py` fails if the patterns go
  missing, which is the other half of the self-test.
- Nothing imports them, and pytest does not collect them (no `test_` prefix).
- They are kept flake8-clean, like `tests/qt6_seed/`, because `make lint` lints `tests/`
  as well. That works because lint runs on the *developer's* Python, which is new enough
  to parse them — the whole point is that these files are only invalid on the floor. If
  you ever lint with a Python older than 3.12, flake8 will report E999 here; that is the
  seed doing its job, not a problem to fix.
- The real plugin code lives in `fiberq/` and must report **zero** findings.

If the floor is ever raised (`qgisMinimumVersion` in `fiberq/metadata.txt` and
`FLOOR_IMAGE` in the `Makefile`), check that these seeds still fail on the new floor — a
seed that the new floor accepts is a seed that no longer proves anything.
