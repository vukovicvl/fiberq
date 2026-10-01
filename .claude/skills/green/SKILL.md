---
name: green
description: Run the FiberQ lint+test gate inside the official QGIS Docker images (the same thing CI runs) and report pass/fail per image. Use to make the build green locally before pushing or opening a PR. Requires Docker.
---

Run the project's lint + test gate inside the QGIS containers, exactly as CI does, and report the result for each image.

## Procedure
1. Confirm Docker is available (`docker version`). If not, stop and tell the user to start Docker Desktop (or run the `scan-check` skill for a fast lint-only check).
2. For each image in the CI matrix — `qgis/qgis:3.44-trixie` (Qt5) and `qgis/qgis:4.0-trixie` (Qt6) — run from the repo root. The Makefile needs a POSIX shell, so on Windows use **Git Bash** (not PowerShell).

   Linux / macOS:
   ```bash
   docker run --rm -v "$PWD:/src" -w /src \
     -e QT_QPA_PLATFORM=offscreen -e PIP_FLAGS=--break-system-packages \
     qgis/qgis:<tag> \
     bash -c "apt-get update -qq && apt-get install -y --no-install-recommends make >/dev/null && make deps && make lint && make test"
   ```

   Windows (Git Bash) — `MSYS_NO_PATHCONV=1` stops MSYS mangling `/src`, and `$(pwd -W)` gives Docker a Windows path:
   ```bash
   MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/src" -w /src \
     -e QT_QPA_PLATFORM=offscreen -e PIP_FLAGS=--break-system-packages \
     qgis/qgis:<tag> \
     bash -c "apt-get update -qq && apt-get install -y --no-install-recommends make >/dev/null && make deps && make lint && make test"
   ```
3. Run the Qt6 source check once (not per image) from the repo root: `make qt6-check`. It runs `pyqt5_to_pyqt6.py --dry_run` in `ghcr.io/qgis/pyqgis4-checker:main-ubuntu`, the same check plugins.qgis.org shows on the plugin page's "Qt6 Check" tab. The QGIS 4 leg above cannot replace it: `utils/compat.py` maps old enum names at runtime, so the tests can pass on Qt6 while the source still carries Qt5-only spellings.
4. Report per image: lint result, test result (pass/fail with the failing test names), the Qt6 check result, and overall green/red.
5. If something fails, summarise the root cause and the smallest fix — do not just dump logs.

## Notes
- This mirrors `.github/workflows/ci.yml`. Keep the image tags in sync with the CI matrix (the Qt6 checker image lives in the Makefile as `QT6_IMAGE` and deliberately tracks `main`, because the website's copy does).
- A `make qt6-check` failure saying the **self-test** found too few findings in `tests/qt6_seed/` does not mean the plugin is clean: it means the checker could not run or its output changed. Fix that before trusting any green run, and never "tidy up" the seed files.
- `make deps` installs with `pip --ignore-installed` because the QGIS images ship some tools (e.g. pytest) via apt without a RECORD file (a plain `-U` upgrade fails to uninstall them).
- The headless run writes a disposable `.qgis-settings/` profile into the repo; it's gitignored.
- For a fast lint-only check without Docker, use `scan-check`.
