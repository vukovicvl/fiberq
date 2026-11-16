---
name: green
description: Run the FiberQ pipeline's default set locally (sh ci/run-all.sh, the stages in their pinned containers; GitHub runs this set on a push to a branch other than release/*) and report pass/fail/skip per stage. Use to make the build green locally before pushing or opening a PR. Requires docker or podman.
---

Run the pipeline's default set locally (the set GitHub runs on a push to a branch other than release/*) and report the result per stage.

## Procedure
1. Confirm the container engine is available (`docker version`, or `podman version` with `CI_ENGINE=podman`; podman also needs an init binary such as catatonit, see "What the host needs" in `ci/README.md`). If there is none, stop and tell the user to start Docker (or run the `scan-check` skill for a lint-only check).
2. From the repo root, pull the images once, then run the default set. On Windows, use Git Bash or WSL2 (not tested yet).
   ```bash
   sh ci/pull.sh        # the default set's images, by their digests in ci/legs (about 28 GB); the only step that pulls
   sh ci/run-all.sh     # pure, lint, qt6, floor, package, then the whole suite on QGIS 3.22, 3.44 and 4.2
   ```
   Shorter runs: `sh ci/run-all.sh --quick` (no test legs, under two minutes), or `sh ci/run-all.sh --only 344,42` (the suite on QGIS 3 and QGIS 4). The default set takes about 45 minutes with one leg at a time; `--jobs 2` runs two legs at once.
3. Read the run's record, `ci-results/<run>/summary.md` (the run prints its folder): one row per stage with its counts, and the reason of any failure. A run that completes ends with `run-all.sh: PASS` (exit 0) or `run-all.sh: FAIL (run folder <run>)` (exit 1). When the summary stage failed there is no summary.md, and the run prints each stage's verdict instead. Exit 2 means a usage error, a refusal, or an engine, git or input that cannot be used (the message says which). Exit 130 means the run was interrupted.
4. Report per stage: pass, fail or skip, with the counts and the failing tests (from `ci-results/<run>/<stage>.log`), and the overall result.
5. If something fails, summarise the root cause and the smallest fix — do not just dump logs.

## Notes
- GitHub runs this set on each push to a branch other than `release/*` and on pull requests from forks, one job per stage: `sh ci/pull.sh <stage>`, then `sh ci/run-all.sh --only <stage>`. There a pull that fails fails the job; here a missing checker image only makes qt6 skipped (see below). A push to `release/*` or of a tag runs the release set instead, each job with `--release --only <stage>` (`ci/README.md`, "On a forge, or with no forge").
- In host mode no stage container mounts the checkout: they run as uid 1000, get their input on stdin and send their results back as a tar that run-all.sh unpacks as you, so nothing in the checkout ends up owned by root. Do not run `make lint` or `make test` as root inside a container on a mounted checkout: that leaves root-owned folders in `ci-results/` and `.ci-cache/`, and from `make test` also `.qgis-settings/` and maybe `symbology-style.db` in the checkout, which later runs as your own user cannot write into.
- qt6 is reported as skipped, and the run still passes, when the Qt6 checker image is not on the machine; `sh ci/pull.sh qt6` (or `make qt6-check`, which pulls it first) fixes that. The checker is pinned by digest in `ci/legs` and moves at each release (RELEASE.md, step 1).
- A qt6 failure saying the **self-test** found too few findings in `tests/qt6_seed/` does not mean the plugin is clean: the checker could not run or its output changed. Fix that before trusting any green run, and never "tidy up" the seed files.
- For a fast lint-only check with no container, use `scan-check`.
