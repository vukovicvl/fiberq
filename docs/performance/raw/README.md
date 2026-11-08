# Raw benchmark results

Machine-readable output from [`tools/bench`](../../../tools/bench/README.md), the WP4 before/after
benchmark. [`docs/performance.md`](../../performance.md), the WP4 task 4.1 deliverable, is written from these
files and links back to them, so the published tables can be checked rather than taken on trust.

## What is here

| Directories | What they hold |
|---|---|
| `baseline-v150-qgis344-{S,M,L}`, `baseline-v150-qgis40-{S,M}` | the October 2026 "before" numbers, v1.5.0 only |
| `final-<kind>-qgis344-{S,M,L}`, `final-<kind>-qgis40-{S,M}` | the final run of 7 and 8 November 2026: eight kinds (`v150-a1`, `v160`, `mid-pf5`, `mid-pf7`, `mid-gate`, `mid-pf3`, `mid-q9b`, `v150-a2`; see "The measured trees"), five image and size pairs, 40 directories |
| `profile-v150-qgis344-S`, `profile-v160-qgis344-S` | cProfile passes, 12 rows at size S |
| `profile2-v150-qgis344-M`, `profile2-v160-qgis344-M` | cProfile passes, 5 rows at size M |
| `snap-memory-scaling/` | the memory-layer script's output, QGIS 3.40 and 4.2 |
| `session-log.txt` | the final session's console output: each run's start, load average and governor, every row's one-line result, each run's exit code, the measured trees' code sha256 and the memory-layer runs' image digests |

A run directory holds one `<row>-<size>.json` per row, plus `env.json` (the environment, the measured code
and the dataset) and `run.json` (the run's index: every row with its status and code digest, and the lists
`controls` and `targets_41`). A profile directory also holds one `profile-<row>-<size>.txt` per row.

No hostnames, usernames or home paths: these files are published. The harness runs every string through a
redactor (paths become `<code>`, `<data>`, `<harness>`, `<out>` or `<tmp>`) and refuses to write a file in
which anything identifying is left. The memory-layer files are pytest's output as printed, not the
harness's; the one path in them, `/tmp/runtime-ubuntu`, is the container's own. `session-log.txt` is the
console output of the script that ran the session, and holds no local path.

## Reading a result

- `timing.median_s` with `mad_s`, `min_s`, `max_s`, `n` and every repetition in `runs`. `warmup_s` and
  `policy` say how many repetitions were made: 7 when the warm-up took under 2 s, 3 up to 60 s, 1 above.
  `cold_s` is the first call, kept separate because it is measured with the sanity probe on
  (`cold_with_sanity_probe`) and pays for the first use of the code in a fresh process. Compare it only with
  another `cold_s`.
- `status`: `ok`; `dnf` when the first call ran past `--budget-s` (`detail` says so); `profiled` in a
  cProfile run, whose timings are not comparable. A did-not-finish is a result, not a gap: `latent_open` at
  size L does not finish in 1,800 s on v1.5.0, in October or in November.
- `control`: `true` for a control (`run_validation`, `plan_recalculation`, `save_gpkg`, `project_open`,
  `bom_open`, `branch_offset`). Controls are expected **not** to improve; they exist to detect noise and are
  never presented as a 4.1 result. `pf` names the performance item a measured row belongs to (`PF-1` to
  `PF-7`).
- `result` and `result_digest`: what the row computed, and a sha256 over it, keys starting with `_` left out.
  Every repetition must compute the first call's digest, or the row is `unstable`. In the final run every
  digest of v1.5.0 and of v1.6.0 is the same on QGIS 3.44 and 4.0, and every v1.5.0 digest is the October
  baseline's. Where v1.6.0's differs from v1.5.0's, 1.6.0 computes something else on purpose, and
  `docs/performance.md` compares the row through a middle column.
- `sanity.errors`: error records logged during the first call. Any row with a non-zero count publishes no
  timing, because an exception that got swallowed mid-operation would otherwise look like a speed-up. Every
  row of the final run has 0.
- `sanity.qgis_log`: the lines QGIS's own message log received. The October QGIS 4 runs
  (`baseline-v150-qgis40-*`) were made before the probe listened on `messageReceivedWithFormat`, so they
  recorded no log lines and their counts are not measurements; their `hooked: true` says only that the probe
  connected to `messageReceived`, where QGIS 4 no longer delivers a line. The final run's QGIS 4.0 rows use
  `messageReceivedWithFormat`, and the probe says `hooked` only once a line it logs itself has arrived.
- `state`: the layers' feature counts, fingerprinted before every call and compared with the first call's,
  so a row whose data drifted between repetitions is reported `unstable-state` instead of measured.
- `code.sha256`: a sha256 over the path and content of every file of the measured `fiberq/` tree except
  bytecode (`__pycache__/`, `.pyc`, `.pyo`) and `.git`, with `code.files` and `code.version` (from its
  `metadata.txt`). `code.pyc_before` and `pyc_after` count the `.pyc` files inside the tree before and after
  the precompile pass; bytecode is read and written under `code.pycache_prefix` instead, so the 45 that an
  earlier use had left in the final run's v1.5.0 tree were never loaded, and none was added. `dataset.digest`: a sha256 over the dataset's
  rows and project entries, not over the file.
- `timing.load` and `env.json`: the load average around the measurement, the CPU governor (cpu0's) and the
  cpuset. They are recorded because the first attempt at the baseline was ruined by a second benchmark
  running alongside it ([`tools/bench/README.md`](../../../tools/bench/README.md), fairness rule 13).
- `started_utc` (each row) and `finished_utc` (`run.json`): when a row started and a run ended. A run's first
  row starts a few seconds after the run start the order table below gives, the time its container takes
  to get going.

## The baseline (October 2026)

| Directory | Code | Image | Dataset |
|---|---|---|---|
| `baseline-v150-qgis344-S` | v1.5.0 | QGIS 3.44.15 | S, 13,812 features |
| `baseline-v150-qgis344-M` | v1.5.0 | QGIS 3.44.15 | M, 34,078 features |
| `baseline-v150-qgis344-L` | v1.5.0 | QGIS 3.44.15 | L, 88,622 features |
| `baseline-v150-qgis40-S` | v1.5.0 | QGIS 4.0.3 | S |
| `baseline-v150-qgis40-M` | v1.5.0 | QGIS 4.0.3 | M |

These are the **"before" numbers, recorded before any WP4 change to a hot path**, from 22:18 UTC on 2 October
to 05:18 UTC on 3 October 2026, and committed in `d321e85`
([PR #49](https://github.com/vukovicvl/fiberq/pull/49)) before the first optimisation merged
([PR #60](https://github.com/vukovicvl/fiberq/pull/60)). The measured tree is `git archive v1.5.0:fiberq`, and
every file carries its sha256 (`code.sha256`, `c208d1a607bf74998fca62cbcf7bd7dc7d1d1cddb0db59700def56b379749fac`)
and version so that can be verified rather than believed. Committing them before the first optimisation is
the point: a "before" measured afterwards is not one.

They have 22 rows. `snap_move_closure` was added at the release, so its v1.5.0 numbers come from the final run
alone. These runs did not record the image digest (`image_digest` is null), and the kernel was then
7.0.0-31-generic. `docs/performance.md` publishes the final run only; `bench_report.py` reads the baseline to
flag a v1.5.0 run more than 15% away from it, which happens once (`save_gpkg` on QGIS 3.44 at S).

The datasets come from `tests/fixtures/make_city_project.py` at seed 20260921. They are not committed (an L
dataset is about 23 MB, 22,847,488 bytes); `dataset.digest` in each file is a sha256 over the rows and the
project's entries (relations, latent elements, colour catalogue), so a rerun can prove it measured the same
data. Regenerate with `--size L --seed 20260921`.

| Size | Features | Digest |
|---|---|---|
| S | 13,812 | `ae4011b9fe9cf3a50b9c611936c2a38ae1f19735a05e3e74ce941cd55ca7df52` |
| M | 34,078 | `ff084aa367b5b010fa2ae0c0451226c1550c1cadf6a09b6ab065edd2c2ae01a9` |
| L | 88,622 | `5ff4e28820e74496ee76c517e7ab239ea8180c23c1b1ccb82a560457d48670ca` |

## The final run (7 and 8 November 2026)

One session, strictly sequential, one container at a time, with `--cpuset-cpus 2-6`, the `performance`
governor, `--network none` and `QT_QPA_PLATFORM=offscreen`. Every `bench.py` run had `--budget-s 1800`,
`--timeout-s 7200`, `--expect-digest` (the dataset) and `--expect-code-sha256` (the tree), and started only
once the 1-minute load average was below 1.5. The session began at 14:26:53 UTC on 7 November, waited for the
load to settle, started its first run at 14:28:23 and ended at 01:41:07 UTC on 8 November. These times, the
run starts in the order table below and the memory-layer runs' times and image digests come from the
session's console output, [`session-log.txt`](session-log.txt); for the timed and profile runs, the result files'
`started_utc` and `finished_utc` agree with them to within a few seconds.

### Order

Start of each run, UTC, 7 November 2026 unless marked (from [`session-log.txt`](session-log.txt)):

| Image, size | v1.5.0, first run | v1.6.0 | middle columns | v1.5.0, second run | done |
|---|---|---|---|---|---|
| QGIS 3.44, S | 14:28 | 14:43 | 14:45–14:47 | 14:47 | 15:02 |
| QGIS 4.0, S | 15:02 | 15:16 | 15:19–15:21 | 15:21 | 15:35 |
| QGIS 3.44, M | 15:35 | 16:18 | 16:22–16:25 | 16:25 | 17:09 |
| QGIS 4.0, M | 17:09 | 17:57 | 18:01–18:04 | 18:04 | 18:52 |
| QGIS 3.44, L | 18:52 | 21:50 | 21:58–22:03 | 22:03 | 00:59 (8 Nov) |

The middle columns ran in the order `mid-pf5`, `mid-pf7`, `mid-gate`, `mid-pf3`, `mid-q9b`. Then, on 8
November: the profile passes from 00:59 to 01:06 (`profile-v150-qgis344-S`, `profile-v160-qgis344-S`,
`profile2-v150-qgis344-M`, `profile2-v160-qgis344-M`), and the memory-layer script from 01:06 to 01:41 (by
`session-log.txt`; the script's own output records no time): QGIS 3.40 with v1.5.0, v1.6.0 and v1.5.0 again, then QGIS 4.2
the same.

At size L both v1.5.0 runs exit non-zero, because `latent_open` does not finish (`dnf`). The timed runs
hold 405 rows: those two, and 403 `ok`.

### The measured trees

| Kind | `label` | Code sha256 | Files | The tree |
|---|---|---|---|---|
| `v150-a1`, `v150-a2` | `v1.5.0` | `c208d1a607bf74998fca62cbcf7bd7dc7d1d1cddb0db59700def56b379749fac` | 221 | `git archive v1.5.0:fiberq` |
| `v160` | `v1.6.0` | `d01d1ea87e3eff23de7087bce7fe86e307ff0e92463e4e61f8447b46014d1f82` | 234 | the plugin folder of the 1.6.0 release, git tree `cf7ce22b9999514c8567328a2fc487abbdef0e4b` |
| `mid-pf5` | `mid-pf5-parent-473a149` | `26b73b69a90fb660ae3b108cc1d7137c93946b84c6701c82dcd573a58f411eec` | 232 | `git archive 473a149:fiberq`, PF-5's parent |
| `mid-pf7` | `mid-pf7-parent-69555e8` | `8bbfaf4c5df4a1c18053660fa77a41b6eaaf880f8ab236bb336e82c8a1c83d11` | 232 | `git archive 69555e8:fiberq`, PF-7's parent |
| `mid-gate` | `mid-v160-without-581273c` | `e34597460b92d53231bb982e9ca32eff1029f443a33449d7e42c78eb11c8642f` | 234 | the release tree without the schematic view's visibility gate |
| `mid-pf3` | `mid-v160-without-q21-ef58e92` | `4f4a9e8dce7e9ee039427c6380c50f64699ddeb3496c2210d44bb66abd30cdea` | 233 | the release tree with the QA fix to route ends, `ef58e92`, reversed |
| `mid-q9b` | `mid-v160-closure-vertex-only` | `093d59df69544931043f20384e87b45018f438f4be3cd84f959d1bb3bb5ede3f` | 234 | the release tree with joint closures snapping to vertices only, `7044c4f` reversed |

Every tree was extracted from git objects, never from a working tree. The two parents' `metadata.txt` still
says 1.5.0, so their `code.version` is `1.5.0`; their labels name no version, so the label check does not
apply to them. The three release-based columns differ from the release in these files only:

- `mid-gate`: `dialogs/schematic_dialog.py`, without the gate's two early returns (`if not self.isVisible():`,
  which mark the view stale and return) in `_schedule_rebuild` and `_do_rebuild_if_needed`, so a closed view
  rebuilds after every commit as it did before `581273c`. The edit was an exact text replacement that refuses
  to run if the code has moved.
- `mid-pf3`: `git show ef58e92 -- fiberq` applied in reverse: `core/route_ends.py` removed, and ef58e92's
  changes to `main_plugin.py`, `dialogs/correction_dialog.py` and `ui/routing_ui.py` undone (`main_plugin.py`
  keeps the changes made to it after ef58e92, such as `579cf80`). The tree was assembled from an earlier
  middle tree, with the files changed since then (the two benchmark fixes and the translation catalogues)
  taken from the release, and it is byte for byte the release with that diff reversed.
- `mid-q9b`: `git show 7044c4f -- fiberq` applied in reverse: `segments=False` and its comment back in
  `tools/extension_tool.py`.

Which rows each kind measures:

| Kind | Rows | Compared with |
|---|---|---|
| `v150-a1`, `v160`, `v150-a2` | all 23 | — |
| `mid-pf5` | `snap_move_element`, `_point`, `_route`, `_pipe`, `_breakpoint`, `_closure`, `manhole_click` | v1.6.0 |
| `mid-pf7` | `lay_cable`, `route_path` | v1.6.0 |
| `mid-gate` | `edit_after_schematic` | v1.6.0 |
| `mid-pf3` | `route_correction` | v1.5.0 |
| `mid-q9b` | `snap_move_closure` | v1.5.0 |

## The profile passes

| Directories | Rows |
|---|---|
| `profile-v150-qgis344-S`, `profile-v160-qgis344-S` | `schematic_open`, `edit_after_schematic`, `latent_open`, `route_correction`, `slack_generate`, `slack_click`, `snap_move_element`, `snap_move_route`, `snap_move_closure`, `record_add`, `lay_cable`, `route_path` |
| `profile2-v150-qgis344-M`, `profile2-v160-qgis344-M` | `snap_move_closure`, `run_validation`, `plan_recalculation`, `save_gpkg`, `branch_offset` |

QGIS 3.44, the same trees (v1.5.0 and v1.6.0) and datasets as the timed runs. Each `profile-<row>-<size>.txt`
starts with a header (the row, the size, the code's version and the first 16 hex digits of its sha256, QGIS,
Qt and PyQt, the dataset and the row's result), then lists cProfile's top 25 functions by cumulative time and
by own time. The JSON beside it has `status: profiled` and `timing.policy` "profiled run: timings not
comparable". A profile run never shares a process with a timed one, because profiling changes the numbers,
and `bench_report.py` does not read these directories.

## The memory-layer output (`snap-memory-scaling/`)

Six text files, one per run, named after the QGIS version and the code, in the order they ran:
`qgis340-v150-a1.txt`, `qgis340-v160.txt`, `qgis340-v150-a2.txt`, then `qgis42-v150-a1.txt`,
`qgis42-v160.txt`, `qgis42-v150-a2.txt` (pytest's output as printed, kept as `.txt` because the repository
ignores `*.log`).

They were made by [`tools/bench/test_snap_memory_scaling.py`](../../../tools/bench/test_snap_memory_scaling.py),
the same file for every run, run under pytest from the root of a whole tree: `git archive v1.5.0` with the
script copied in, or the release tree. Same CPUs, `--network none`, `PYTHONDONTWRITEBYTECODE=1`, pytest 9.1.1
and pytest-qgis 4.1.1 (the versions installed for the session; the output does not record them).

| Image | Digest (from `session-log.txt`) | QGIS |
|---|---|---|
| `qgis/qgis:3.40` | `sha256:d664f1eca1ef4f615efd92b944c90896622bc75f0446357dc50c2e56b379ddd9` | 3.40.15-Bratislava |
| `qgis/qgis:4.2-trixie` | `sha256:56c69c92e316aa679e5c30ebf7fcfd89fd1124ec728106ec0cced1c71a28d877` | 4.2.3-Belém do Pará |

Each file holds the container's start-up lines, then `QGIS <version>`, then one JSON line per size, then
pytest's summary. In a JSON line, `features` is the number of memory-layer features: n three-vertex routes, a
pole at each end and a manhole on the middle vertex, 4n in all. Every other key is one tool at one cursor
position: `closure` the joint-closure tool, `pole` the pole tool, `odf` the element tool placing an ODF;
`@vertex` with the mouse resting near a route vertex, `@span` over a span. The value is microseconds per
mouse move, the best of seven rounds of 200 moves after 20 warm-up moves, with QGIS snapping off. The script
times the moves and compares no results. A v1.5.0 run takes about eight to nine minutes, a v1.6.0 run about
17 seconds (pytest's summary line).

## Regenerating the tables

From the repository root; `bench_report.py` is pure Python and needs no QGIS:

```sh
python3 tools/bench/bench_report.py docs/performance/raw                          # the results tables
python3 tools/bench/bench_report.py docs/performance/raw --summary                # the summary table
python3 tools/bench/bench_report.py docs/performance/raw --json /tmp/verdicts.json  # every verdict, as JSON
```

The JSON is written outside the checkout, so the command leaves no stray file in it. The script reads the
`final-*` and `baseline-*` directories and nothing else. The rules it applies are in its docstring and in
[`docs/performance.md`](../../performance.md), section 2; how to run the benchmark itself is in section 10
there, which follows the session's commands; [`tools/bench/README.md`](../../../tools/bench/README.md)
documents the harness and its fairness rules.
