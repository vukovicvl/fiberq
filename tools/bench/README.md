# `tools/bench` — the WP4 before/after benchmark harness

Dev tooling for Task 4.1 ("large-project performance ... with a documented
before/after benchmark"). It measures a fixed list of user actions on a seeded
city-sized project, once against the released code and once against the new
code, and writes one JSON file per measurement.

Never shipped. `make package` archives `HEAD:fiberq` only, so nothing under
`tools/` can reach the plugin zip.

| File | What it is |
|---|---|
| `bench.py` | the orchestrator: one subprocess per scenario x size, then `run.json` |
| `bench_worker.py` | one scenario in one process; writes one JSON file |
| `bench_smoke.py` | every scenario once, in one process, no timing — the harness's own check |
| `bench_scenarios.py` | the scenario registry: one closure per measured action |
| `bench_support.py` | code pinning, stub iface, modal patches, dataset copy, probes |
| `bench_common.py` | digests, timing policy, environment probe, redaction |

## Reproducing a run

Everything happens inside the QGIS Docker images, because the host's QGIS
floats. Pin the image by digest for a run whose numbers get published; the tag
moves across point releases.

```sh
# 1. the dataset (once per size; keep it outside git -- an L dataset is ~20 MB)
mkdir -p /tmp/bench
docker run --rm -v "$PWD:/src:ro" -v /tmp/bench:/work -e TMPDIR=/work/data \
  -e QT_QPA_PLATFORM=offscreen qgis/qgis:3.44-trixie \
  python3 /src/tests/fixtures/make_city_project.py --size S

# 2. the "before" code, extracted from the tag -- never the working tree
mkdir -p /tmp/bench/code/v150/fiberq
git archive v1.5.0:fiberq | tar -x -C /tmp/bench/code/v150/fiberq

# 3. the run
docker run --rm -v "$PWD:/src:ro" -v /tmp/bench:/work -w /work \
  -e QT_QPA_PLATFORM=offscreen -e TMPDIR=/work/tmp \
  -e FIBERQ_BENCH_IMAGE=qgis/qgis:3.44-trixie \
  -e FIBERQ_BENCH_IMAGE_DIGEST=sha256:... \
  --cpuset-cpus 2-3 \
  qgis/qgis:3.44-trixie \
  python3 /src/tools/bench/bench.py \
      --code /work/code/v150 --label v1.5.0 \
      --data S=/work/data/fiberq-city/city_S \
      --out /work/out/20261003-qgis344-v150 \
      --scratch /work/tmp
```

The container runs as root, so never write generated data into the mounted
repository: point `--out`, `--scratch` and `TMPDIR` at a scratch mount.

Useful flags: `--list` (what can be run, and which rows are controls),
`--scenario NAME` (repeatable), `--no-controls`, `--profile` (cProfile instead
of timing), `--dry-run`, `--expect-digest SHA256`, `--expect-code-sha256 SHA256`,
`--budget-s`. For a run whose numbers get published, pass both `--expect-digest`
and `--expect-code-sha256`: they pin the dataset and the code tree before the
first row instead of leaving a reviewer to check the digests afterwards.

A profile run is a *separate* run: profiling changes the numbers, so it never
shares a process with a timed one.

```sh
python3 /src/tools/bench/bench.py --code ... --data S=... --out ... --profile \
    --scenario schematic_open --scenario latent_open
```

## Is the harness still honest? (`bench_smoke.py`)

Run this on a freshly generated dataset before spending a night on a real
benchmark. It calls every scenario once, in one process, with the sanity pass
on, and asserts nothing about time:

```sh
make bench-smoke BENCH_DATA=/work/data/fiberq-city/city_XS BENCH_OUT=/work/out
# or, with the flags spelled out:
D=/tmp/fiberq-city/city_XS
python3 tools/bench/bench_smoke.py --code . --out /tmp/smoke.json --data $D \
    --expect-digest $(python3 -c "import json;print(json.load(open('$D/manifest.json'))['digest'])")
```

Each row comes back `ok`, `skipped` (the dataset has no layer for it) or
`failed` with a traceback, and the exit code is non-zero if anything failed. It
is the one piece of this directory CI exercises, through
`tests/test_bench_harness.py` on the XS dataset: a scenario whose layer lookup,
post-condition or dialog constructor has rotted fails there instead of being
published as a speed-up. CI measures nothing — the plan's rule that no
benchmark JSON is produced or compared in CI still holds.

It takes `--k 2` by default instead of the benchmark's 50 cables, because the
post-condition ("two terminal slacks per selected cable") does not need 50 and
CI pays for every second. One process for all 22 rows is a deliberate departure
from fairness rule 9: that rule protects a published number, and this publishes
none. The 22 QgsApplication starts it saves are most of the cost.

## What a row can come back as

A result file always says which of these it is, and `bench.py` exits non-zero
unless every row is `ok`, `skipped` or `profiled`.

| `status` | Meaning |
|---|---|
| `ok` | measured; the timings may be published |
| `skipped` | the dataset has no layer for this row |
| `profiled` | a `--profile` run: the timings are explicitly not comparable |
| `dnf` | the cold call ran past `--budget-s` |
| `unstable` | a repetition produced a different result digest |
| `unstable-state` | a call did not start from the state the cold call did, so the repetitions measured different amounts of work |
| `errors-logged` | an error record was logged while the measured call ran (`--allow-error-records` to measure anyway) |
| `digest-mismatch` | not the dataset the baseline was measured on |
| `code-digest-mismatch` | not the code tree `--expect-code-sha256` named |
| `label-mismatch` | `--label` disagrees with the measured tree's own `metadata.txt` |
| `failed` | the scenario raised: a post-condition, or the code under test |
| missing file | the process died; `run.json` records it with the stderr tail |

## Output

```
<out>/<scenario>-<size>.json          one measurement
<out>/profile-<scenario>-<size>.txt   cProfile, top 25 by cumulative and by tottime
<out>/run.json                        the index: every row, with the code digest
```

Published raw data goes to `docs/performance/raw/<run-id>/`. Keep every filename
`.json`, `.txt` or `.md`, and never name a directory `build`, `var`, `target`,
`cover`, `profile_default` or `env`: `.gitignore` swallows all of those at any
depth, and `*.log`, `*.zip`, `*.manifest` and `*.spec` with them.

## Fairness rules

These are the rules that make a number worth publishing. Break one and the
comparison is between two different measurements, not two versions of the code.

1. **The code is pinned, not labelled.** `--code` goes first on `sys.path` and
   the worker asserts `fiberq.__file__` is inside it, then records a sha256 over
   the whole `fiberq` tree. A decoy directory (`<code>/fiberq` with no
   `__init__.py`) is a namespace portion, so Python keeps searching and imports
   the *other* fiberq from `PYTHONPATH`; that is exactly the mistake the
   assertion exists for. Verified by running it: with `PYTHONPATH` pointing at
   another tree, `--code` still wins, and a `--code` with no `fiberq/__init__.py`
   is refused before QGIS starts.
   The digest alone proves *which* tree, not which tree was meant, so
   `--expect-code-sha256` refuses a tree the run did not ask for, and a
   `--label` that names a version (`v1.5.0`) is checked against the imported
   tree's own `metadata.txt` — `--label v1.5.0` against a 1.6.0 tree used to
   produce a median quite happily. If the rows of one run disagree on the
   digest, the run fails.
   Bytecode is part of the measurement too: a tree from `git archive` has no
   `__pycache__` while a working tree has a full set from the test suite (one
   row left 80 `.pyc` for 98 `.py`), so the worker compiles the measured tree
   up front, outside everything it times, and records `pyc_before`,
   `pyc_after` and `precompiled`.
2. **The dataset is pinned.** The generator's manifest digest is over row
   content, and `--expect-digest` refuses a dataset that does not match. The
   worker also checks the project still carries the manifest's fixed layer ids.
3. **Same canvas on both sides.** The canvas is the central widget of a shown
   `QMainWindow` at exactly 0.5 m/px, asserted after the layout settles. The
   placement tools derive their snap tolerance from `mapUnitsPerPixel()`, so a
   different zoom is a different amount of work. (Offscreen, the first
   `outputSize()` is pre-layout: using it leaves the canvas at 0.5168 m/px.)
4. **Same modals on both sides.** `QMessageBox` (statics and `exec`),
   `QFileDialog` (four statics), `CablePickerDialog.exec` and
   `CorrectionDialog.exec` are patched, and the worker fails if any patch did
   not apply. A renamed class must show up as a failed run, never as a faster
   one.
5. **Project snapping off.** v1.5.0 ignores the project's snapping config;
   WP4-FU-6 makes the tools honour it. The placement rows measure FiberQ's own
   fallback snap on both sides, so the PF-5 index is compared against something.
6. **A fresh dataset before every mutating repetition**, made outside the timed
   region — along with a fresh project read and a fresh `FiberQPlugin`. Setup
   that is not the measured action (adding the feature `record_add` then
   resolves, copying the file `project_open` then reads, selecting the cables
   `slack_generate` then works on, unlinking the file `save_gpkg` then writes)
   also happens outside. The timed region holds the measured call and its
   post-condition, nothing else.
   `mutating` is a hand-written flag per row, so it is not taken on trust: the
   per-layer feature counts are fingerprinted outside the timed region before
   **every** call and compared with the cold call's, and a row whose state
   drifted is `unstable-state` rather than a measurement. Measured with
   `slack_generate` deliberately marked `mutating=False`: the slack layer
   climbed 156 → 236 features across seven repetitions, each doing more work
   than the last, while the post-condition held and the result digest stayed
   *identical* to the correctly reset run. Nothing noticed until this check
   existed.
7. **The cold call is the sanity pass.** It runs with every `fiberq*` logger at
   DEBUG and counts ERROR-level records, WARNING records, and debug records whose
   text reads like a swallowed error. The count is fed from a `logging` record
   factory, not from a handler: `get_logger` sets `propagate = False` on every
   module logger (`fiberq/utils/logger.py:181`), so a handler on the `fiberq`
   parent sees nothing and every row reports a confident 0 — which is how this
   harness first lied to its author. It also checks a post-condition (cable +1,
   slack +2K, path found, ...) and takes a digest of the result.
   `errors` is the number the row is gated on — an error record while the
   measured call ran makes the row `errors-logged` and publishes no timing,
   because until that gate existed an injected ERROR came back `ok` with a
   median beside it. `swallowed_debug` is a screening signal
   and over-reports by design -- it matches any debug or info line whose text
   reads like a failure, which catches `validation_manager`'s benign
   "Validation: 0 error(s)" summary too. A false positive is safe here; a false
   negative is what the WP4 census is about. `cold_s` is the one call measured
   with the probe installed, which the result file says in
   `timing.cold_with_sanity_probe`, so a cold number is compared with another
   cold number and never with a median. The timed repetitions then run at the default WARNING level,
   which is what a user gets, and every repetition's digest must match the cold
   one or the row is reported `unstable`. A swallowed error cannot be published
   as a speed-up.
8. **Timing policy.** Cold first call recorded separately, then one warm-up,
   then N=7 under 2 s, N=3 for 2–60 s, N=1 above 60 s. Reported as median, min,
   max and MAD (median absolute deviation, so one slow run does not widen the
   spread that decides whether two ranges overlap).
9. **One process per row.** A crash, a leak or a signal connection left behind
   cannot reach the next scenario. A process that dies leaves no JSON, and
   `run.json` records that as a crash with the stderr tail.
10. **Controls are marked as controls** in every result file, in the console
    table (`ctl` against `4.1`), and in `run.json` — which lists `controls` and
    `targets_41` separately as well as flagging each row, so the two cannot be
    added up by accident. `run_validation` (WP2), `save_gpkg` (pre-award),
    `project_open`, `bom_open`, `branch_offset` and `plan_recalculation` should
    *not* change: they are there to detect noise, and they are never presented
    as a 4.1 result.
11. **No hostnames, no user paths.** The result files are published, so every
    string is run through a redactor (paths replaced by `<code>`, `<data>`,
    `<harness>`, `<out>`, `<tmp>`) and the write is refused if anything
    identifying is left. Tracebacks and log samples are the realistic leak.
    Order matters twice over, and both were wrong until a crafted payload was
    run through it: the home-directory pattern has to go before the username
    token, or `/home/<user>/Documents/x` becomes `/home/<redacted>/Documents/x`
    and the pattern can no longer match it; and the tokens have to be applied
    longest first, or a hostname of `<user>-Precision-7510` leaves the machine
    model behind. In both cases the "prove nothing is left" check then passed,
    because no whole token remained to find.
12. **Assertions must be on.** Every post-condition in `bench_scenarios` is an
    `assert`, so under `-O` or `PYTHONOPTIMIZE=1` they are all compiled away.
    Measured: a `generate_terminal_slack_for_selected` patched to a no-op came
    back `status: ok`, median 0.0012 s against the real 0.4438 s, `errors: 0`.
    All three entry points now refuse to start.

### Three deliberate exceptions, so they are not mistaken for mistakes

- **`edit_after_schematic` calls `_do_rebuild_if_needed()` inside the timed
  region** instead of waiting out the dialog's 400 ms debounce timer. The work
  is the same; the wait is not. Whether the hidden view scheduled a rebuild at
  all is reported as `_rebuild_scheduled_while_hidden` and deliberately *not*
  asserted: on v1.5.0 it is `True` (the PF-1 defect), and after the fix it is
  `False`.
- **A dialog a repetition is finished with gets its rebuild scheduler
  neutralised.** The schematic view connects project signals to lambdas
  capturing `self` (`schematic_dialog.py:898-899`), which PyQt cannot
  auto-disconnect, so without this each extra repetition leaves another view
  scheduling rebuilds: the seven `edit_after_schematic` repetitions climbed
  0.770 -> 0.901 s, monotonically. That is the harness accumulating, not the
  code — a user has one view open, not nine. The cold call, the one that must
  behave exactly like v1.5.0, is untouched.
- **Keys starting with `_` are left out of the result digest.** They describe how
  the work happened — was a rebuild scheduled, was the fid still negative after
  the commit, how many bytes were written — which an optimisation is allowed to
  change. Everything else is data the user would see, and it must match.

### Why `os._exit(0)`

Implicit interpreter teardown after the schematic dialog plus a project clear is
a deterministic SIGSEGV on QGIS 4.0 (5/5 runs; `exitQgis()` happened to survive
~90 runs, but it still runs the destructors that crash). `os._exit` runs no
destructor at all. It also skips Python's buffer flush, which leaves a result
file under ~8 KB at 0 bytes — measured — so every output file is closed and
`fsync`ed, and stdout flushed, immediately before the exit.

### What this harness does not measure

Rendering time, memory, and QGIS 3.22 (no `QgsMapLayer.setId`, so the fixture
cannot be generated there; it reads a 3.44-written project fine). Project-entry
state is not compared between images either: QGIS 3.x uses the entry key as an
XML tag name and silently drops keys that are not valid tag names, where 4.0
keeps them. The numbers come from a laptop inside Docker; `--cpuset-cpus` and a
pinned governor are what keep them comparable, not an absolute claim.
