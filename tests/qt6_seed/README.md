# Qt6 checker seeds — deliberately broken, do not fix

These files are **intentionally** written in PyQt5 style. They are the self-test for
`make qt6-check`: the target runs the same checker plugins.qgis.org runs
(`pyqt5_to_pyqt6.py --dry_run`, in `ghcr.io/qgis/pyqgis4-checker:main-ubuntu`) over this
directory and **fails if the checker reports fewer than four findings here**.

Why: the checker writes its findings to a log and exits 0 either way. A gate that only
looked at the exit code, or that grepped for a message the checker stopped emitting, would
go quietly green and stop protecting the release. Seeding known-bad code proves the gate
can still see a problem before it is allowed to say the plugin is clean.

Each file is named after the mistake it seeds:

| File | Seeds |
|---|---|
| `seed_imports.py` | `from PyQt5...` instead of `from qgis.PyQt...` |
| `seed_enums.py` | unscoped Qt and QGIS enums (`Qt.AlignLeft`, `QgsWkbTypes.Point`) |
| `seed_exec.py` | `exec_()`, renamed to `exec()` in Qt6 |

Rules for this directory:

- **Never "clean up" these files.** `tests/test_qt6_seed.py` fails if the patterns go
  missing, which is the other half of the self-test.
- Nothing imports them, and pytest does not collect them (no `test_` prefix).
- They are kept flake8-clean, because `make lint` lints `tests/` as well — the point is the
  Qt6 mistakes, not stray lint.
- The real plugin code lives in `fiberq/` and must report **zero** findings.
