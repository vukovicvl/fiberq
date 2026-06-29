---
name: scan-check
description: Predict the plugins.qgis.org Security & Quality scan locally (flake8 + Bandit), no Docker needed. Use before any upload/release, or after a change, to confirm the plugin still scans with zero findings.
---

Run the same checks the plugins.qgis.org scanner runs, locally and fast, and report the counts.

## Procedure (from the repo root)
1. flake8 in isolated mode — mirrors the scanner exactly (config files are ignored):
   ```bash
   python -m flake8 --isolated --max-line-length=120 --ignore=E501 fiberq
   ```
2. Bandit, medium/high only (the scan policy):
   ```bash
   python -m bandit -r fiberq -ll -q
   ```
3. Report: flake8 finding count and Bandit medium/high count. **The gate is 0 / 0.**
4. If anything fires, list each finding with `file:line` and the code, and say whether it should be fixed or (rarely, with a stated reason) silenced with an inline `# noqa: <code>` / Bandit annotation.

## Notes
- "0 findings" today rests partly on intentional inline `# noqa`s for style codes that are tracked debt — do not strip those as "cleanup".
- This is lint-only. For the full gate including running tests in QGIS, use `green`.
