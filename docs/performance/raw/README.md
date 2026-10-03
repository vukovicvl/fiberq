# Raw benchmark results

Machine-readable output from `tools/bench`. One directory per run, one JSON per
scenario, plus `env.json` (the environment) and `run.json` (the summary).
`docs/performance.md` — the WP4 task 4.1 deliverable — is written from these
files and links back to them, so the published table can be checked rather than
taken on trust.

## What is here

| Directory | Code | Image | Dataset |
|---|---|---|---|
| `baseline-v150-qgis344-S` | v1.5.0 | QGIS 3.44.15 | S, 13,812 features |
| `baseline-v150-qgis344-M` | v1.5.0 | QGIS 3.44.15 | M, 34,078 features |
| `baseline-v150-qgis344-L` | v1.5.0 | QGIS 3.44.15 | L, 88,622 features |
| `baseline-v150-qgis40-S` | v1.5.0 | QGIS 4.0.3 | S |
| `baseline-v150-qgis40-M` | v1.5.0 | QGIS 4.0.3 | M |

These are the **"before" numbers, recorded before any WP4 change to a hot
path**: the measured tree is `git archive v1.5.0:fiberq`, and every file carries
its sha256 (`code.sha256`) and version so that can be verified rather than
believed. Committing them before the first optimisation is the point — a
"before" measured afterwards is not one.

The datasets come from `tests/fixtures/make_city_project.py` at seed 20260921.
They are not committed (an L dataset is ~22 MB); `dataset.digest` in each file
is a sha256 over the row content, so a rerun can prove it measured the same
data. Regenerate with `--size L --seed 20260921`.

## Reading a result

- `timing.median_s` with `mad_s`, `min_s`, `max_s`, `n` — and `cold_s`, the
  first call, kept separate because it includes bytecode and QGIS warm-up.
- `status`: `ok`, or `dnf` when one cold call ran past `--budget-s`. A
  did-not-finish is a result, not a gap: `latent_open` at size L does not finish
  in 1800 s on v1.5.0.
- `claim`: `4.1` for a measured row, `ctl` for a control. Controls
  (`run_validation`, `save_gpkg`, `project_open`, `bom_open`,
  `plan_recalculation`, `branch_offset`) are expected **not** to improve; they
  exist to detect noise and are never presented as a 4.1 result.
- `sanity.errors` — error records logged during the cold call. Any run with a
  non-zero count publishes no timing, because an exception that got swallowed
  mid-operation would otherwise look like a speed-up.
- `result_digest` — what the scenario computed. All 22 digests are identical
  between QGIS 3.44 and 4.0, and the "after" run must match them or the
  comparison is between two different pieces of work.
- `timing.load` — the machine's load average around the measurement, and
  `env.json` records the CPU governor and the cpuset. Both are here because the
  first attempt at this baseline was ruined by a second benchmark running
  alongside it (see `tools/bench/README.md`, fairness rule 13).

No hostnames, usernames or home paths: these files are published.
