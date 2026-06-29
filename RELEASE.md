# Releasing FiberQ

The documented release process for the FiberQ QGIS plugin. All steps use the
forge-agnostic `Makefile`; none require GitHub specifically.

## Versioning

FiberQ uses semantic-style versioning `MAJOR.MINOR.PATCH` (e.g. `1.3.0`).

- The **single source of truth** is `version=` in `fiberq/metadata.txt`.
- `fiberq/__init__.py` also carries `__version__`; keep it identical. A smoke
  test (`tests/test_smoke.py`) fails the build if the two drift apart.
- The **schema version** is tracked separately (see WP1) inside the project's
  `_fiberq_metadata` table. Plugin version and schema version are deliberately
  decoupled: most releases bump the plugin version only.

When to bump which part:
- **PATCH** — bug fixes, cleanup, no behaviour change.
- **MINOR** — new backward-compatible features (a new capability delivery, typically).
- **MAJOR** — breaking changes to the data model or public behaviour.

## Pre-release checklist

- [ ] `make lint` is clean (flake8 + Bandit medium/high = 0 findings).
- [ ] `make test` passes (and CI is green on both QGIS images).
- [ ] `version=` bumped in `fiberq/metadata.txt`, and `__version__` in
      `fiberq/__init__.py` matches.
- [ ] `changelog=` block in `fiberq/metadata.txt` updated for this version.
- [ ] `fiberq/config.ini` contains no credentials or machine-specific paths.
- [ ] "Use of Generative AI" section present/current in `fiberq/README.md`
      (shipped) and the repo-root `README.md` (public landing page).
- [ ] AI-assisted commits carry the `Assisted-by:` trailer.
- [ ] Manual QGIS test done: install the built zip in a clean profile and open
      both an older project and a new one.

## Build, tag, push

```bash
make package          # builds dist/fiberq-<version>.zip from committed state
make release          # runs lint + test + package, then creates tag v<version>
git push && git push --tags
```

Notes:
- `make package` uses `git archive HEAD:fiberq`, so it packages **committed**
  state and the zip contains a single top-level `fiberq/` folder (what
  plugins.qgis.org requires). Commit before packaging a real release.
- `make release` refuses to create a tag that already exists — bump the version
  in `metadata.txt` first. It does not push or upload anything automatically;
  push and upload are deliberate, manual steps.

## Local development (Windows)

The maintainer's box is Windows; the `Makefile` is POSIX shell, so run `make`
either inside the QGIS container (as CI does) or from **Git Bash** (not
PowerShell/cmd):

- **Lint only, native and fast** (no Docker needed):
  ```bash
  python -m flake8 --isolated --max-line-length=120 --ignore=E501 fiberq tests conftest.py
  python -m bandit -r fiberq -ll -q -c pyproject.toml
  ```
- **Full gate (lint + tests) in the QGIS image** — from Git Bash, with Docker Desktop running:
  ```bash
  docker run --rm -v "$PWD:/src" -w /src -e QT_QPA_PLATFORM=offscreen \
    -e PIP_FLAGS=--break-system-packages qgis/qgis:4.0-trixie \
    bash -c "apt-get update -qq && apt-get install -y --no-install-recommends make >/dev/null && make deps && make lint && make test"
  ```
  Repeat with `qgis/qgis:3.44-trixie`. For a local non-Debian/venv run, set
  `PIP_FLAGS=` (empty).
- `make install` targets a Linux profile by default; on Windows override it, e.g.
  `make install QGIS_PROFILE="$APPDATA/QGIS/QGIS3/profiles/default"` (run from Git Bash).

CI is the authoritative green check for the test/package steps.

## Upload to the QGIS plugin repository

`dist/fiberq-<version>.zip` is the artifact to upload.

1. Sign in at <https://plugins.qgis.org/> with the OSGEO account.
2. Open the FiberQ plugin page → **Add version** → upload the zip.
3. plugins.qgis.org runs its Security & Quality scan (flake8 + Bandit). The local
   `make lint` mirrors that gate, so a clean local run should mean a clean scan.
4. Verify the new version appears in the QGIS Plugin Manager (it can take a few
   minutes to propagate).

Keep any upload credentials out of the repo — use environment variables or a forge
secret if the upload is ever scripted. The manual web upload is the documented default.

## After release (dissemination)

For each released task/version, publish: a summary of what was done plus updated
documentation / user guide on the project website; the tagged release and zip on
GitHub; video guide(s) where relevant; and a note to the mailing list.

## Tested QGIS versions

CI builds against `qgis/qgis:3.44-trixie` (QGIS 3, Qt5) and `qgis/qgis:4.0-trixie`
(QGIS 4, Qt6). `metadata.txt` declares `qgisMinimumVersion=3.22` and
`qgisMaximumVersion=4.99`.

Note: CI does **not** run a 3.22 image (old images are pruned upstream, and
`pytest-qgis` itself requires QGIS ≥ 3.34, so 3.34 is the realistic CI floor). The
3.22 LTR floor is held by careful API usage and the Qt5/Qt6 compatibility layer
(`fiberq/utils/compat.py`), **not** by CI — verify it manually before any release
that touches Qt/QGIS APIs. Re-pin the CI tags in `.github/workflows/ci.yml` as the
LTR/stable lines move.
