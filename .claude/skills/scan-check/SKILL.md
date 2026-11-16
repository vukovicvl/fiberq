---
name: scan-check
description: Predict the plugins.qgis.org Security & Quality scan locally with the pipeline's lint stage (flake8, Bandit and detect-secrets with the scanner's settings, plus the repo's own checks), no container needed. Use before any upload/release, or after a change, to confirm the plugin still scans with zero findings.
---

Run the pipeline's lint stage here and report the counts: `make lint`, which is `CI_IN_PLACE=1 sh ci/run-all.sh --only lint`.

## Procedure (from the repo root)
1. Run `make lint`. It needs `python3` 3.12 or later on `PATH`; the first run installs the pinned tools into `.ci-cache/`, which needs the network. It runs:
   - flake8 with the scanner's flags (`--isolated --max-line-length=120 --ignore=E501`; config files are ignored) on `fiberq/`, `tests/`, `conftest.py` and `tools/bench`;
   - Bandit at ALL severities on `fiberq/` (the scanner flags LOW too — e.g. B110/B112 try/except/pass|continue — so `-ll` is not enough);
   - detect-secrets on `fiberq/`, as the scanner runs it;
   - shellcheck on `ci/`, flake8 on `ci/*.py`, the `.ts` placeholder check and the check of the forge configs.
2. Read the lint row of `ci-results/<run>/summary.md` (one count per check), and the outputs in `ci-results/<run>/stages/lint/out/`: `flake8.txt`, `bandit.txt`, `detect-secrets.json`, `shellcheck.txt`, `flake8-ci.txt`, `placeholders.txt` and `wrappers.txt`. `result.txt` there holds each count and exit status.
3. Report each count. **The gate is 0 on every check.**
4. If anything fires, list each finding with `file:line` and the code, and say whether it should be fixed or (rarely, with a stated reason) silenced with an inline `# noqa: <code>` / Bandit annotation.

## Notes
- "0 findings" today rests partly on intentional inline `# noqa`s for style codes that are tracked debt — do not strip those as "cleanup".
- This is lint only. For the tests, use `green`.
