---
name: prepublish
description: Run the FiberQ pre-publish checklist for a release (version sync, changelog, scan-clean, tests green, package builds, GenAI disclosure, secrets, manual-test reminder). Use right before tagging/publishing a version. Reports a readiness status; never pushes or uploads.
---

Walk the release checklist and report status for each item. Do NOT push, tag, or upload — this is a readiness check only.

## Checklist (report ✓ / ✗ / N/A with evidence for each)
1. **Version sync** — `version=` in `fiberq/metadata.txt` equals `__version__` in `fiberq/__init__.py` (the smoke test enforces this).
2. **Changelog** — `changelog=` in `fiberq/metadata.txt` has an entry for this version.
3. **Scan clean** — run the `scan-check` gate (`make lint`): every check 0, including flake8, Bandit at **all** severities (the upstream scanner flags LOW too, so `-ll` is not enough) and detect-secrets.
4. **Tests green** — a full release run passed on this tree. RELEASE.md, step 3, makes it with `sh ci/run-all.sh --release --jobs 2` (about an hour). It runs pure, lint, qt6, floor, package, the suite on the five QGIS versions of `ci/legs` and the release check. Use the newest folder in `ci-results/` whose `run.txt` has `set=release`, `mode=host`, an empty `only=` and `root_tree=` equal to `git rev-parse HEAD^{tree}`: the run that `make tag` (`ci/tag.sh`) takes as its evidence. It passed when its `record.txt` exists and has `result=pass` and `overrides=none`; its `summary.md` shows each stage. If there is no such folder, report that the release run has not run. GitHub's checks on the pushed commit are per stage and do not replace it.
5. **Qt6 check clean** — the release run's qt6 row (or `make qt6-check`) reports 0 findings in `fiberq/`, so the plugin page's "Qt6 Check" tab is green on upload, and the Qt6 checker pin in `ci/legs` is the current build (RELEASE.md, step 1). A self-test failure (too few findings in `tests/qt6_seed/`) means the checker itself is broken, not that the package is clean.
6. **Package builds** — the package stage (`make package`, or the release run) builds the zip from committed `fiberq/` files in `ci-results/<run>/package/` and checks it (`ci/zipcheck.py`); it copies the zip, its `.sha256` and its `.contents.tsv` into `dist/` only when `dist/` holds none of them and `fiberq/` has no uncommitted change. Check that the zip in `dist/` is that run's zip (same sha256), that it has a single top-level `fiberq/` with `metadata.txt` and `__init__.py`, and no `__pycache__` or dev/hidden files.
7. **GenAI disclosure** — the "Use of Generative AI" section is present/current in both `fiberq/README.md` (shipped) and the repo-root `README.md` (public landing page).
8. **No secrets** — `fiberq/config.ini` has placeholders only; no credentials anywhere in the diff.
9. **Manual QGIS test** — remind the maintainer to install the built zip in a clean QGIS profile and test old + new projects before publishing (a human gate, not automated).
10. **Provenance** — AI-assisted commits in the release carry the agreed commit trailer.

## Output
A pass/fail table, then the remaining manual steps (push, tag, upload to plugins.qgis.org, publish docs) listed for the maintainer — never execute them here.
