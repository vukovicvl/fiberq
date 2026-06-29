---
name: prepublish
description: Run the FiberQ pre-publish checklist for a release (version sync, changelog, scan-clean, tests green, package builds, GenAI disclosure, secrets, manual-test reminder). Use right before tagging/publishing a version. Reports a readiness status; never pushes or uploads.
---

Walk the release checklist and report status for each item. Do NOT push, tag, or upload — this is a readiness check only.

## Checklist (report ✓ / ✗ / N/A with evidence for each)
1. **Version sync** — `version=` in `fiberq/metadata.txt` equals `__version__` in `fiberq/__init__.py` (the smoke test enforces this).
2. **Changelog** — `changelog=` in `fiberq/metadata.txt` has an entry for this version.
3. **Scan clean** — run the `scan-check` gate: flake8 0 + Bandit medium/high 0.
4. **Tests green** — `green` passes on both QGIS images (or CI is green on the pushed commit).
5. **Package builds** — `make package` produces `dist/fiberq-<version>.zip`; verify a single top-level `fiberq/`, that it includes `metadata.txt`/`__init__.py`, and that it contains no `__pycache__` and no dev/hidden files.
6. **GenAI disclosure** — the "Use of Generative AI" section is present/current in both `fiberq/README.md` (shipped) and the repo-root `README.md` (public landing page).
7. **No secrets** — `fiberq/config.ini` has placeholders only; no credentials anywhere in the diff.
8. **Manual QGIS test** — remind the maintainer to install the built zip in a clean QGIS profile and test old + new projects before publishing (a human gate, not automated).
9. **Provenance** — AI-assisted commits in the release carry the agreed commit trailer.

## Output
A pass/fail table, then the remaining manual steps (push, tag, upload to plugins.qgis.org, publish docs) listed for the maintainer — never execute them here.
