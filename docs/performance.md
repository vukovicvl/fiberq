# FiberQ 1.6.0 — Performance on large projects

The before/after benchmark for FiberQ 1.6.0's large-project work: spatial indexes and batched reads and
writes in the operations that used to go through a whole layer, or every label already placed, once per
edge, label, cable, route end, slack, click or mouse move. Twenty-three user actions were timed in QGIS 3.44
and 4.0 on three generated test cities of 13,812, 34,078 and 88,622 features, FiberQ 1.5.0 against the 1.6.0
release (its plugin folder is git tree `cf7ce22b9999`), in one interleaved session on 7 and 8 November 2026.

Every figure here comes from the result files in [`raw/`](performance/raw/), and the tables are generated
from them by [`tools/bench/bench_report.py`](../tools/bench/bench_report.py), so each one can be checked
rather than taken on trust. The few figures that come from elsewhere, measurements made during development,
say where they come from.

## Summary

| User action | Size S | Size M | Size L |
|---|---|---|---|
| Open the Optical Schematic View | 23 s → 1.73 s (x13 faster) | 2 min 10 s → 4.33 s (x30 faster) | 16 min 39 s → 11.3 s (x88 faster) |
| Any edit, once the view has been opened | 21.4 s → 109 ms (x196 faster) | 2 min 03 s → 202 ms (x605 faster) | 13 min 39 s → 456 ms (x1798 faster) |
| Open the list of latent elements | 59.2 s → 751 ms (x79 faster) | 5 min 38 s → 1.87 s (x180 faster) | did not finish in 30 min → 5.04 s (v1.5.0 did not finish) |
| Route correction (the check) | 5.4 s → 208 ms with 1.5.0's findings (x26 faster); 112 ms as shipped | 32 s → 520 ms with 1.5.0's findings (x62 faster); 277 ms as shipped | 3 min 22 s → 1.36 s with 1.5.0's findings (x149 faster); 733 ms as shipped |
| Generate terminal slacks for 50 cables | 17 s → 355 ms (x48 faster) | 23.8 s → 368 ms (x65 faster) | 42.5 s → 398 ms (x107 faster) |
| Place one slack | 229 ms → 136 ms (x1.7 faster) | 361 ms → 140 ms (x2.6 faster) | 694 ms → 155 ms (x4.5 faster) |
| Nine mouse moves, route tool | 716 ms → 35.5 ms (x20 faster) | 1.78 s → 35.4 ms (x50 faster) | 4.52 s → 35.8 ms (x126 faster) |
| Nine mouse moves, element tool | 534 ms → 10 ms (x54 faster than PF-5's parent) | 1.33 s → 10.1 ms (x128 faster than PF-5's parent) | 3.44 s → 10.2 ms (x326 faster than PF-5's parent) |
| Nine mouse moves, joint-closure tool | 12.8 ms → 9.9 ms snapping as 1.5.0 did (22% faster); 11.4 ms as shipped | 13.2 ms → 10.7 ms (19% faster) | 13.1 ms → 10 ms snapping as 1.5.0 did (24% faster); 10.9 ms as shipped |
| Place one manhole | 119 ms → 82.9 ms (30% faster) | 187 ms → 90 ms (x2.1 faster) | 359 ms → 100 ms (x3.6 faster) |
| FiberQ's undo record after a placement | 13.8 ms → 6.42 ms (x2.2 faster) | 25.7 ms → 6.47 ms (x4 faster) | 57.2 ms → 6.52 ms (x8.8 faster) |
| Lay one cable | 239 ms → 148 ms (x1.6 faster) | 458 ms → 243 ms (x1.9 faster) | 1.06 s → 471 ms (x2.2 faster) |

QGIS 3.44, medians. One line per user action: twelve of the 17 claimed rows, in this order: `schematic_open`,
`edit_after_schematic`, `latent_open`, `route_correction`, `slack_generate`, `slack_click`, `snap_move_route`,
`snap_move_element`, `snap_move_closure`, `manhole_click`, `record_add`, `lay_cable`. The other five claimed
rows (`route_path`, `record_add_memory`, `snap_move_point`, `snap_move_pipe`, `snap_move_breakpoint`) and the
six controls are in section 4.

Each cell reads v1.5.0 (the mean of its two runs) → v1.6.0, with the change by the rule in section 2. Where
1.6.0 computes something different on purpose (section 7), the change comes from a middle column instead:
*with 1.5.0's findings* and *snapping as 1.5.0 did* give the time of v1.6.0 with that one change of behaviour
taken out, which computes what 1.5.0 computed, and its speed-up over 1.5.0, followed by v1.6.0's own time *as
shipped* (for route correction that is the unclaimed QA fix's own check, section 6); *than PF-5's parent* is
v1.6.0's speed-up over the commit before PF-5, which already snaps the way 1.6.0 does. In the element-tool
row the time before the arrow is still 1.5.0's, which snapped on fewer of the nine moves (section 7); PF-5's
parent took 538 ms, 1.3 s and 3.33 s. *Any edit* is an edit made after the view has been opened and closed,
and its factors include the unclaimed visibility gate; the first bullet below gives the claimed part.

By the rule in section 2, no row, controls included, is measurably slower than in 1.5.0 on either QGIS
version at any size: six control medians are above both v1.5.0 medians, by 1.3% at most, but in each the
median ± MAD overlaps the v1.5.0 range, so the rule reads no measurable change. The 18 rows the rule cannot
compare with 1.5.0 (section 7 says why) take less time in v1.6.0 too; their middle columns give the gain at
equal results.

Outside the rule, slowdowns were measured. On memory layers, which the city rows do not snap on, each of the
three tools measured pays about 0.06–0.10 ms a move more than in 1.5.0, so the pole and ODF tools are slower
at 4 features and the joint-closure tool at every size (section 8). In these cities, the joint-closure tool's
first nine moves in a fresh process are slower than 1.5.0's in four of the five tables (section 9). Section 9
also lists the slowdowns measured during development.

Some rows of the summary also contain work that is not spatial indexing or batching. The middle columns
separate most of it (sections 2 and 6):

- **Any edit, after the view has been opened and closed**: part of the factor is the visibility gate, which
  is not claimed: x16, x21 and x24 at S, M and L (8%, 3% and 1% of the seconds saved). Without it the edit
  takes 1.77 s, 4.3 s and 11.1 s at S, M and L, x12, x29 and x74 faster than 1.5.0 at the same result: that
  part is the claimed batching and indexing. While the view is open, each commit still rebuilds it; that
  rebuild is what the column without the gate times, in a closed view.
- **Lay one cable**: v1.6.0 is 10%, 18% and 28% faster than PF-7's parent commit, on a pair where PF-7's
  narrowed search helps most (section 9). The rest of the gain over 1.5.0 comes mostly from the undo record
  (PF-6) and the cable-type migration changes, one supporting and one unclaimed (section 6): in the profiles at
  S the migration takes 55 ms of v1.5.0's 278 ms and 6 ms of v1.6.0's 203 ms.
- **Place one manhole**: v1.6.0 is 9% faster, 25% faster and x1.7 faster than PF-5's parent. The rest of its
  gain over 1.5.0 is already in that parent, which holds PF-6's undo record and the unclaimed snapping rewrite
  among other changes; no column separates them.
- **Nine mouse moves**: v1.6.0 also carries two unclaimed changes that stop each move redoing work (section
  6). No middle column takes them out, so the factors over 1.5.0 and over PF-5's parent include them: a few
  milliseconds of nine moves where v1.6.0 saves 95 ms to 4.7 s over PF-5's parent, but v1.6.0 itself takes
  only 3.4–36 ms, so they carry part of each factor. On the **joint-closure tool** they are the whole of the lead over 1.5.0: 1.5.0's tool
  already read through a box, and before the first of them (`d4a252f`) v1.6.0 took 17.7 ms against 1.5.0's
  12.8–12.9 ms at S on QGIS 3.44 (measured during development, its commit message). That row is there to show
  that the indexed snap is no slower on a GeoPackage, not as a result of PF-5; on memory layers it is slower
  (section 8).
- **Place one slack** has no middle column. It includes the changes to the cable-type migration that every
  cable restyle runs (`641882b`, supporting; `c7da6e8`, unclaimed): in v1.5.0's profile at S the migration
  takes 45 ms of the click's 240 ms, against 6 ms in v1.6.0's. It also includes two unclaimed fixes to the
  slack tool's search (section 6). In **Generate terminal slacks** the batching itself restyles each layer
  once instead of once per slack.

One row's factors rest partly on a difference the result files do not explain: in **Open the Optical
Schematic View**, 1.5.0's warm-up and median timed call are 5–28% slower than its own first call. Taken from the
first calls (the mean of both v1.5.0 runs' against v1.6.0's), the factors on QGIS 3.44 are x12, x27 and x71
where the table shows x13, x30 and x88 (section 9).

---

## 1. What is measured, and why

Each row is one user action, or one step of one, run headless in QGIS against a generated test city. A row
calls FiberQ's own code for it as the plugin does: a map tool's mouse handler with a mouse event, a dialog's
constructor, a plugin command, or the function a command runs (`record_add`, `route_path`,
`plan_recalculation` and `project_open` time one step of an action, as the table says), with the modal
dialogs answered the same way on both sides.

| Row | User action | Work |
|---|---|---|
| `schematic_open` | Open the Optical Schematic View | PF-1 |
| `edit_after_schematic` | One attribute edit and commit, after the view has been opened once and closed | PF-1 |
| `latent_open` | Open the list of latent elements (one row per cable) | PF-2 |
| `route_correction` | Routing → Route correction: the check that lists loose route ends | PF-3 |
| `slack_generate` | Generate terminal slacks for 50 selected cables (100 slacks) | PF-4 |
| `slack_click` | One click with the slack tool, at a cable's end | PF-4 |
| `snap_move_element`, `_point`, `_route`, `_pipe`, `_breakpoint`, `_closure` | Nine mouse moves with the element tool (placing an ODF), the pole, route, pipe, breakpoint or joint-closure tool, QGIS snapping off | PF-5 |
| `manhole_click` | One manhole placed | PF-5 |
| `record_add`, `record_add_memory` | FiberQ's undo record after a placement: on the GeoPackage's Poles layer, and on a memory-layer copy of it | PF-6 |
| `lay_cable`, `route_path` | Lay one cable between two joint closures; five route searches on their own | PF-7 |
| `run_validation` | Validate project | control |
| `plan_recalculation` | Plan a recalculation of the stored lengths | control |
| `save_gpkg` | Save all layers to GeoPackage | control |
| `project_open` | Read the project with FiberQ's layer hooks, then run its migrations | control |
| `bom_open` | Open the bill of materials | control |
| `branch_offset` | Compute and style the branch offsets of the underground cables | control |

PF-1 to PF-7 are the seven performance items, as the pull requests in section 6 name them; the tables mark
their rows `4.1` (WP4 task 4.1, large-project performance).

The placement rows make nine mouse moves around a route vertex: four within 3.6 m of it, inside every tool's
snap tolerance (10 to 20 px, so 5 to 10 m at the benchmark's 0.5 m per pixel), and five 30 to 50 m away,
where a tool can still find a span or another feature in reach. Between 2 and 7 of the nine snap, depending
on the tool, the size and the version (section 7). QGIS snapping is off, so FiberQ's own snap answers in
every tool, and that is the snap PF-5 indexes. `snap_move_closure` was added at the release: the
joint-closure tool was the one placement tool 1.5.0 already read through a box, so its row is there to show
that the shared, indexed snap is no slower there on a GeoPackage; on memory layers it is slower (section 8). It has no October baseline, and its v1.5.0 figures come
from this session alone.

**The controls are not a 4.1 target.** They are measured the same way and are expected not to change: they
are there to show the noise floor, and they are never presented as results of this work. Three of them move
in every table (`project_open`, `bom_open`, `plan_recalculation`), and two by 1% in one table each
(`run_validation` on QGIS 3.44 at L, `save_gpkg` on 4.0 at M); section 6 says why.

## 2. Method

### Datasets

[`tests/fixtures/make_city_project.py`](../tests/fixtures/make_city_project.py), seed `20260921`: a street
grid with routes, poles, manholes, every element type, cables along shortest paths, slacks, pipes, fibre
breaks, service areas, relations and latent elements, in one GeoPackage of 24 layers with its project file,
in EPSG:3857. Validation reports no issue at any size (the `run_validation` control's result, in every
run). The manifest's digest is a sha256 over the rows and the project's entries (the relations, latent
elements and colour catalogue the project file holds), not over the file. Every run was started with
`--expect-digest`, which refuses a dataset that does not match, and every result file records the digest.

| Size | Street grid | Features | Routes | GeoPackage | Digest |
|---|---|---|---|---|---|
| S | 32 × 32 | 13,812 | 1,816 | 4,038,656 bytes | `ae4011b9fe9cf3a50b9c611936c2a38ae1f19735a05e3e74ce941cd55ca7df52` |
| M | 50 × 50 | 34,078 | 4,472 | 9,138,176 bytes | `ff084aa367b5b010fa2ae0c0451226c1550c1cadf6a09b6ab065edd2c2ae01a9` |
| L | 80 × 80 | 88,622 | 11,619 | 22,847,488 bytes | `5ff4e28820e74496ee76c517e7ab239ea8180c23c1b1ccb82a560457d48670ca` |

### Code

"Before" is `git archive v1.5.0:fiberq`, code sha256 `c208d1a607bf…`. "After" is the plugin folder of the
1.6.0 release, git tree `cf7ce22b9999514c8567328a2fc487abbdef0e4b`, code sha256 `d01d1ea87e3e…`. The code
sha256 is taken over every file of the `fiberq/` tree except bytecode, path and content, and recorded in every result file.
Every run was started with `--expect-code-sha256`, which refuses any other tree, and a label naming a version
is checked against the tree's own `metadata.txt`. The measured tree is compiled to bytecode before anything
is timed. The full digests of all seven trees are in [`raw/README.md`](performance/raw/README.md).

### Timing

- **One process per row** ([`tools/bench/bench.py`](../tools/bench/bench.py)), so a crash, a leak or a
  signal connection left behind cannot reach the next row.
- **A first call**, timed on its own, with a sanity probe: every FiberQ logger at DEBUG, error records
  counted, a post-condition checked (one more cable, two slacks per cable, every path found, …) and a digest
  taken of what the action computed. A row that logs an error publishes no timing.
- **One warm-up, then 7 timed repetitions** when the warm-up took under 2 s, 3 up to 60 s, and 1 above. Each
  repetition must compute the first call's digest. A row that changes data gets a fresh copy of the dataset,
  a fresh project read and a fresh plugin before every repetition, outside the timed region, and the layers'
  feature counts are checked before every call.
- **Median, min, max and MAD**, the median absolute deviation, so that one slow repetition does not widen the
  spread.
- **Did not finish**: a first call that runs past 1,800 s (30 minutes). A worker is stopped after 7,200 s.
- **Fairness**: the same canvas (0.5 m per pixel), the same answered dialogs, project snapping off,
  assertions on, one benchmark on the machine at a time. The full list, with why each rule exists, is in
  [`tools/bench/README.md`](../tools/bench/README.md).

A row's digest is taken over the facts its action returns
([`tools/bench/bench_scenarios.py`](../tools/bench/bench_scenarios.py)): findings, table rows, scene items,
the vertex count of each path, features added. Keys starting with `_` are left out, because they describe
how the work was done, which an optimisation may change. For the placement rows the facts are how many of
the nine moves snapped (section 9).

### One session, interleaved

The whole session ran strictly one container at a time, each run starting only once the 1-minute load
average was below 1.5: the timed runs from 14:28 UTC on 7 November 2026 to 00:59 UTC on 8 November, then the
profile passes to 01:06, then the memory-layer script, which ended at 01:41 by the session's log, [`raw/session-log.txt`](performance/raw/session-log.txt) (the script's
own output records no time). For each image and size, in the order QGIS 3.44 at S, 4.0 at S, 3.44 at M, 4.0 at M
and 3.44 at L, it ran v1.5.0, v1.6.0, the five middle columns, then v1.5.0 again. The two v1.5.0 runs bracket
the v1.6.0 run in time, so drift during the session (heat, the machine) widens the "before" range instead of
passing for a speed-up. The order and the start of every run, to the minute, are in
[`raw/README.md`](performance/raw/README.md) (the middle columns as one range per image and size); in the
result files, each row's `started_utc` and each `run.json`'s `finished_utc` date them.

### The rule for a published change

As `bench_report.py` applies it:

- A row's v1.5.0 range is the hull of both v1.5.0 runs' median ± MAD. The two runs bracket the v1.6.0 run
  in time, so drift during the session widens the range instead of turning into a speed-up.
- A change is shown only when v1.6.0's median ± MAD lies wholly outside that range **and** every run
  computed the same result digest. Otherwise the row says "no measurable change", or why it cannot be
  compared.
- A row is flagged when its two v1.5.0 medians are more than 15% apart, or either is more than 15% from the
  early baseline.
- A middle column is one of three kinds. The parent of a claimed change is compared with v1.6.0: that is
  the change plus whatever was merged after it on the same path (see below). v1.6.0 without the unclaimed
  visibility gate is also compared with v1.6.0: that is the gate's share. It computes v1.5.0's result
  digest, so v1.5.0 against it is the claimed work; the summary takes that factor from the two medians, as
  `bench_report.py` does not print it. v1.6.0 without a later change of behaviour computes what v1.5.0
  computed, so it is compared with v1.5.0, by the same rule as v1.6.0 is: the speed-up at equal results, on
  a row where v1.6.0 itself computes something else.

A change is written as a factor (x21) from 1.5 times up and as a percentage below, against the mean of the
two v1.5.0 medians, or against the median of a middle column compared with v1.6.0. The early baseline is the
v1.5.0 run of 2 and 3 October 2026 in `raw/baseline-*`, recorded before any change to a hot path.

### Middle columns

| Column | Tree | Rows | Compared with | What it shows |
|---|---|---|---|---|
| PF-5's parent | `473a149` | the six `snap_move_*` rows, `manhole_click` | v1.6.0 | PF-5's box reads, plus the two unclaimed per-move changes merged after them (section 6). The parent already has the rewritten placement snap (`a264610`) and the broken-geometry skip (`e407550`), which are not indexing |
| PF-7's parent | `69555e8` | `lay_cable`, `route_path` | v1.6.0 | PF-7, plus what was merged after it on the same path. The parent already has PF-6's undo record, the cable-type migration changes and `a430e24`, the repair of a routing slowdown 1.6.0 itself had introduced |
| v1.6.0 without the visibility gate | the release, with the gate's two early returns removed | `edit_after_schematic` | v1.6.0 | how much of the row is the gate, which is supporting work and not claimed |
| v1.6.0 without the QA fix to route ends | the release with `ef58e92` reversed | `route_correction` | v1.5.0 | PF-3's speed-up at 1.5.0's own findings |
| v1.6.0 with joint closures snapping to vertices only, as in 1.5.0 | the release with `7044c4f` reversed | `snap_move_closure` | v1.5.0 | the closure row at 1.5.0's own snapping |

A parent column holds everything merged before its claimed commit, so the gap between it and v1.6.0 is that
commit plus whatever was merged after it on the same path. For the placement rows that includes two
unclaimed changes that stop each mouse move redoing work (section 6).

## 3. Environment

From each run's `env.json`; nothing in it differs between the runs of one image.

| Machine | |
|---|---|
| CPU | Intel Core i7-6820HQ @ 2.70 GHz, a laptop processor, 8 logical CPUs |
| CPUs used | five, 2 to 6: `docker run --cpuset-cpus 2-6` |
| Frequency governor | `performance` (cpu0's, as recorded) |
| Memory | 31,438,232 kB |
| Kernel | Linux 7.0.0-38-generic (7.0.0-31-generic for the October baseline) |
| Containers | the official QGIS images, `--network none`, `QT_QPA_PLATFORM=offscreen`, one at a time |

| Image | QGIS 3.44 | QGIS 4.0 |
|---|---|---|
| Tag | `qgis/qgis:3.44-trixie` | `qgis/qgis:4.0-trixie` |
| Digest | `sha256:6df39d4b09c7ccceb18b80644a377e27829f408f64b33ca55e6fd7d7eaa92006` | `sha256:23c12670e69909e8659a5c098aa307996735a5763b9ff9c3268bdeeee1a10916` |
| QGIS | 3.44.15-Solothurn | 4.0.3-Norrköping |
| Qt / PyQt | 5.15.15 / 5.15.11 | 6.8.2 / 6.9.0 |
| Python | 3.13.5 | 3.13.5 |
| GDAL | 3.10.3 | 3.10.3 |
| Canvas | 998 × 772 px at 0.5 m per pixel | 998 × 776 px at 0.5 m per pixel |

The memory-layer script (section 8) ran on the same CPUs, with pytest 9.1.1 and pytest-qgis 4.1.1 (the
versions installed for the session; no output file records them). Its output records the QGIS version only;
the two image digests come from the session's log, [`raw/session-log.txt`](performance/raw/session-log.txt), and are also listed in
[`raw/README.md`](performance/raw/README.md).

| Image (section 8) | QGIS 3.40 | QGIS 4.2 |
|---|---|---|
| Tag | `qgis/qgis:3.40` | `qgis/qgis:4.2-trixie` |
| Digest | `sha256:d664f1eca1ef4f615efd92b944c90896622bc75f0446357dc50c2e56b379ddd9` | `sha256:56c69c92e316aa679e5c30ebf7fcfd89fd1124ec728106ec0cced1c71a28d877` |
| QGIS | 3.40.15-Bratislava | 4.2.3-Belém do Pará |
| Qt, PyQt, Python, GDAL | not recorded | not recorded |

## 4. Results

Five tables, one per image and size, generated by `bench_report.py` from `raw/`; nothing in them is edited.
Size L is measured on QGIS 3.44 only.

- **v1.5.0 (before / after the v1.6.0 run)**: the medians of the session's two v1.5.0 runs, the first before
  v1.6.0 and the second after the middle columns. **v1.6.0**: the release's median.
- **Change**: by the rule in section 2. *Not comparable* when the runs computed different results; *v1.5.0
  did not finish* when 1.5.0's first call ran past 30 minutes.
- **Middle column**: its median, and what it shows against v1.6.0 (a parent, or v1.6.0 without the gate) or
  against v1.5.0 (an equal-result column), by the same rule.
- **First call, v1.5.0 / v1.6.0**: the first call of the first v1.5.0 run and of the v1.6.0 run. It is
  measured with the sanity probe on, so it is compared only with the other first call, and it includes
  whatever a first use costs (section 9).
- **Notes**: *result digests differ* (section 7 says why), and the drift flag.
- **did not finish in 30 min**: the first call ran past the 1,800 s budget, so there is no median:
  `latent_open` at L, both v1.5.0 runs.

### QGIS 3.44.15 (Qt5), size S

| Row | | v1.5.0 (before / after the v1.6.0 run) | v1.6.0 | Change | Middle column | First call, v1.5.0 / v1.6.0 | Notes |
|---|---|---|---|---|---|---|---|
| `bom_open` | control | 101 ms / 107 ms | 98.1 ms | 6% faster |  | 119 ms / 113 ms |  |
| `branch_offset` | control | 92.7 ms / 90.3 ms | 90.1 ms | no measurable change |  | 89.6 ms / 89.1 ms |  |
| `edit_after_schematic` | 4.1 | 21.2 s / 21.5 s | 109 ms | x196 faster | v1.6.0 without the visibility gate: 1.77 s (v1.6.0 x16 faster) | 21 s / 108 ms |  |
| `latent_open` | 4.1 | 58.7 s / 59.7 s | 751 ms | x79 faster |  | 58.8 s / 776 ms |  |
| `lay_cable` | 4.1 | 244 ms / 234 ms | 148 ms | x1.6 faster | PF-7's parent (`69555e8`): 164 ms (v1.6.0 10% faster) | 289 ms / 204 ms |  |
| `manhole_click` | 4.1 | 120 ms / 119 ms | 82.9 ms | 30% faster | PF-5's parent (`473a149`): 91.2 ms (v1.6.0 9% faster) | 121 ms / 78.4 ms |  |
| `plan_recalculation` | control | 173 ms / 179 ms | 138 ms | 22% faster |  | 210 ms / 145 ms |  |
| `project_open` | control | 874 ms / 883 ms | 711 ms | 19% faster |  | 962 ms / 770 ms |  |
| `record_add` | 4.1 | 13.9 ms / 13.7 ms | 6.42 ms | x2.2 faster |  | 15.3 ms / 8.13 ms |  |
| `record_add_memory` | 4.1 | 3.14 ms / 3.08 ms | 0.992 ms | x3.1 faster |  | 4.33 ms / 1.92 ms |  |
| `route_correction` | 4.1 | 5.28 s / 5.52 s | 112 ms | not comparable | v1.6.0 without the QA fix to route ends (`ef58e92`): 208 ms (against v1.5.0, the same result: x26 faster) | 5.34 s / 131 ms | result digests differ |
| `route_path` | 4.1 | 183 ms / 185 ms | 175 ms | 5% faster | PF-7's parent (`69555e8`): 191 ms (v1.6.0 9% faster) | 217 ms / 206 ms |  |
| `run_validation` | control | 3.06 s / 3.03 s | 3.04 s | no measurable change |  | 3.1 s / 3.11 s |  |
| `save_gpkg` | control | 2.47 s / 2.53 s | 2.49 s | no measurable change |  | 7.76 s / 2.48 s | v1.5.0 15% off the baseline |
| `schematic_open` | 4.1 | 22.9 s / 23.1 s | 1.73 s | x13 faster |  | 21.8 s / 1.83 s |  |
| `slack_click` | 4.1 | 228 ms / 230 ms | 136 ms | x1.7 faster |  | 275 ms / 186 ms |  |
| `slack_generate` | 4.1 | 17 s / 16.9 s | 355 ms | x48 faster |  | 16.7 s / 407 ms |  |
| `snap_move_breakpoint` | 4.1 | 92.4 ms / 92.6 ms | 4.22 ms | not comparable | PF-5's parent (`473a149`): 98.9 ms (v1.6.0 x23 faster) | 99.7 ms / 18.7 ms | result digests differ |
| `snap_move_closure` | 4.1 | 12.8 ms / 12.7 ms | 11.4 ms | not comparable | PF-5's parent (`473a149`): 479 ms (v1.6.0 not comparable); v1.6.0 with joint closures snapping to vertices only, as in 1.5.0: 9.9 ms (against v1.5.0, the same result: 22% faster) | 20.6 ms / 24.8 ms | result digests differ |
| `snap_move_element` | 4.1 | 525 ms / 543 ms | 10 ms | not comparable | PF-5's parent (`473a149`): 538 ms (v1.6.0 x54 faster) | 568 ms / 23.8 ms | result digests differ |
| `snap_move_pipe` | 4.1 | 485 ms / 475 ms | 10.4 ms | x46 faster | PF-5's parent (`473a149`): 515 ms (v1.6.0 x50 faster) | 491 ms / 22.8 ms |  |
| `snap_move_point` | 4.1 | 278 ms / 289 ms | 3.7 ms | x77 faster | PF-5's parent (`473a149`): 122 ms (v1.6.0 x33 faster) | 284 ms / 15.7 ms |  |
| `snap_move_route` | 4.1 | 720 ms / 713 ms | 35.5 ms | x20 faster | PF-5's parent (`473a149`): 743 ms (v1.6.0 x21 faster) | 767 ms / 55 ms |  |

### QGIS 3.44.15 (Qt5), size M

| Row | | v1.5.0 (before / after the v1.6.0 run) | v1.6.0 | Change | Middle column | First call, v1.5.0 / v1.6.0 | Notes |
|---|---|---|---|---|---|---|---|
| `bom_open` | control | 253 ms / 246 ms | 236 ms | 5% faster |  | 273 ms / 254 ms |  |
| `branch_offset` | control | 158 ms / 159 ms | 160 ms | no measurable change |  | 167 ms / 173 ms |  |
| `edit_after_schematic` | 4.1 | 2 min 01 s / 2 min 04 s | 202 ms | x605 faster | v1.6.0 without the visibility gate: 4.3 s (v1.6.0 x21 faster) | 2 min 01 s / 222 ms |  |
| `latent_open` | 4.1 | 5 min 41 s / 5 min 35 s | 1.87 s | x180 faster |  | 5 min 41 s / 1.89 s |  |
| `lay_cable` | 4.1 | 464 ms / 453 ms | 243 ms | x1.9 faster | PF-7's parent (`69555e8`): 296 ms (v1.6.0 18% faster) | 519 ms / 305 ms |  |
| `manhole_click` | 4.1 | 188 ms / 187 ms | 90 ms | x2.1 faster | PF-5's parent (`473a149`): 120 ms (v1.6.0 25% faster) | 181 ms / 91.3 ms |  |
| `plan_recalculation` | control | 439 ms / 447 ms | 332 ms | 25% faster |  | 447 ms / 347 ms |  |
| `project_open` | control | 1.12 s / 1.11 s | 878 ms | 21% faster |  | 1.2 s / 927 ms |  |
| `record_add` | 4.1 | 25.8 ms / 25.6 ms | 6.47 ms | x4 faster |  | 28.2 ms / 8.19 ms |  |
| `record_add_memory` | 4.1 | 8.15 ms / 7.75 ms | 2.27 ms | x3.5 faster |  | 9.1 ms / 3.61 ms |  |
| `route_correction` | 4.1 | 32.5 s / 31.5 s | 277 ms | not comparable | v1.6.0 without the QA fix to route ends (`ef58e92`): 520 ms (against v1.5.0, the same result: x62 faster) | 31.6 s / 304 ms | result digests differ |
| `route_path` | 4.1 | 463 ms / 454 ms | 437 ms | 5% faster | PF-7's parent (`69555e8`): 480 ms (v1.6.0 9% faster) | 493 ms / 458 ms |  |
| `run_validation` | control | 7.54 s / 7.54 s | 7.55 s | no measurable change |  | 7.63 s / 7.58 s |  |
| `save_gpkg` | control | 2.87 s / 2.88 s | 2.88 s | no measurable change |  | 2.81 s / 2.79 s |  |
| `schematic_open` | 4.1 | 2 min 10 s / 2 min 11 s | 4.33 s | x30 faster |  | 1 min 59 s / 4.41 s |  |
| `slack_click` | 4.1 | 369 ms / 353 ms | 140 ms | x2.6 faster |  | 410 ms / 190 ms |  |
| `slack_generate` | 4.1 | 23.8 s / 23.7 s | 368 ms | x65 faster |  | 23.8 s / 420 ms |  |
| `snap_move_breakpoint` | 4.1 | 220 ms / 233 ms | 4.31 ms | not comparable | PF-5's parent (`473a149`): 239 ms (v1.6.0 x56 faster) | 229 ms / 15.2 ms | result digests differ |
| `snap_move_closure` | 4.1 | 13 ms / 13.4 ms | 10.7 ms | 19% faster | PF-5's parent (`473a149`): 1.2 s (v1.6.0 x113 faster); v1.6.0 with joint closures snapping to vertices only, as in 1.5.0: 10 ms (against v1.5.0, the same result: 24% faster) | 25.3 ms / 24.3 ms |  |
| `snap_move_element` | 4.1 | 1.33 s / 1.32 s | 10.1 ms | not comparable | PF-5's parent (`473a149`): 1.3 s (v1.6.0 x128 faster) | 1.34 s / 25.3 ms | result digests differ |
| `snap_move_pipe` | 4.1 | 1.19 s / 1.19 s | 10.4 ms | x115 faster | PF-5's parent (`473a149`): 1.26 s (v1.6.0 x121 faster) | 1.21 s / 22.6 ms |  |
| `snap_move_point` | 4.1 | 685 ms / 682 ms | 3.65 ms | x187 faster | PF-5's parent (`473a149`): 293 ms (v1.6.0 x80 faster) | 683 ms / 16.3 ms |  |
| `snap_move_route` | 4.1 | 1.81 s / 1.75 s | 35.4 ms | x50 faster | PF-5's parent (`473a149`): 1.87 s (v1.6.0 x53 faster) | 1.84 s / 54.4 ms |  |

### QGIS 3.44.15 (Qt5), size L

| Row | | v1.5.0 (before / after the v1.6.0 run) | v1.6.0 | Change | Middle column | First call, v1.5.0 / v1.6.0 | Notes |
|---|---|---|---|---|---|---|---|
| `bom_open` | control | 636 ms / 652 ms | 604 ms | 6% faster |  | 670 ms / 614 ms |  |
| `branch_offset` | control | 357 ms / 363 ms | 353 ms | no measurable change |  | 379 ms / 352 ms |  |
| `edit_after_schematic` | 4.1 | 13 min 44 s / 13 min 35 s | 456 ms | x1798 faster | v1.6.0 without the visibility gate: 11.1 s (v1.6.0 x24 faster) | 13 min 49 s / 487 ms |  |
| `latent_open` | 4.1 | did not finish in 30 min / did not finish in 30 min | 5.04 s | v1.5.0 did not finish |  | — / 4.81 s |  |
| `lay_cable` | 4.1 | 1.05 s / 1.06 s | 471 ms | x2.2 faster | PF-7's parent (`69555e8`): 651 ms (v1.6.0 28% faster) | 1.14 s / 556 ms |  |
| `manhole_click` | 4.1 | 357 ms / 362 ms | 100 ms | x3.6 faster | PF-5's parent (`473a149`): 174 ms (v1.6.0 x1.7 faster) | 342 ms / 97.9 ms |  |
| `plan_recalculation` | control | 1.12 s / 1.13 s | 866 ms | 23% faster |  | 1.18 s / 868 ms |  |
| `project_open` | control | 1.82 s / 1.78 s | 1.33 s | 26% faster |  | 1.87 s / 1.42 s |  |
| `record_add` | 4.1 | 57.9 ms / 56.5 ms | 6.52 ms | x8.8 faster |  | 58.2 ms / 8.4 ms |  |
| `record_add_memory` | 4.1 | 21.9 ms / 20.2 ms | 5.99 ms | x3.5 faster |  | 23.9 ms / 8.04 ms |  |
| `route_correction` | 4.1 | 3 min 23 s / 3 min 22 s | 733 ms | not comparable | v1.6.0 without the QA fix to route ends (`ef58e92`): 1.36 s (against v1.5.0, the same result: x149 faster) | 3 min 25 s / 775 ms | result digests differ |
| `route_path` | 4.1 | 1.23 s / 1.23 s | 1.18 s | 4% faster | PF-7's parent (`69555e8`): 1.3 s (v1.6.0 9% faster) | 1.29 s / 1.21 s |  |
| `run_validation` | control | 19.7 s / 19.6 s | 19.4 s | 1% faster |  | 19.5 s / 19.3 s |  |
| `save_gpkg` | control | 3.87 s / 3.87 s | 3.92 s | no measurable change |  | 3.78 s / 3.88 s |  |
| `schematic_open` | 4.1 | 17 min 11 s / 16 min 08 s | 11.3 s | x88 faster |  | 13 min 27 s / 11.2 s |  |
| `slack_click` | 4.1 | 689 ms / 700 ms | 155 ms | x4.5 faster |  | 724 ms / 216 ms |  |
| `slack_generate` | 4.1 | 42.2 s / 42.9 s | 398 ms | x107 faster |  | 42 s / 444 ms |  |
| `snap_move_breakpoint` | 4.1 | 606 ms / 578 ms | 4.21 ms | not comparable | PF-5's parent (`473a149`): 660 ms (v1.6.0 x157 faster) | 606 ms / 15.3 ms | result digests differ |
| `snap_move_closure` | 4.1 | 13.3 ms / 13 ms | 10.9 ms | not comparable | PF-5's parent (`473a149`): 3.04 s (v1.6.0 not comparable); v1.6.0 with joint closures snapping to vertices only, as in 1.5.0: 10 ms (against v1.5.0, the same result: 24% faster) | 21.3 ms / 25.8 ms | result digests differ |
| `snap_move_element` | 4.1 | 3.45 s / 3.44 s | 10.2 ms | not comparable | PF-5's parent (`473a149`): 3.33 s (v1.6.0 x326 faster) | 3.57 s / 24.1 ms | result digests differ |
| `snap_move_pipe` | 4.1 | 3.02 s / 3.05 s | 10.4 ms | x291 faster | PF-5's parent (`473a149`): 3.26 s (v1.6.0 x313 faster) | 3.09 s / 24.2 ms |  |
| `snap_move_point` | 4.1 | 1.85 s / 1.8 s | 3.99 ms | x457 faster | PF-5's parent (`473a149`): 755 ms (v1.6.0 x189 faster) | 1.81 s / 15.7 ms |  |
| `snap_move_route` | 4.1 | 4.54 s / 4.49 s | 35.8 ms | x126 faster | PF-5's parent (`473a149`): 4.74 s (v1.6.0 x132 faster) | 4.54 s / 55 ms |  |

### QGIS 4.0.3 (Qt6), size S

| Row | | v1.5.0 (before / after the v1.6.0 run) | v1.6.0 | Change | Middle column | First call, v1.5.0 / v1.6.0 | Notes |
|---|---|---|---|---|---|---|---|
| `bom_open` | control | 116 ms / 113 ms | 110 ms | 4% faster |  | 126 ms / 126 ms |  |
| `branch_offset` | control | 96.3 ms / 97.9 ms | 94.2 ms | no measurable change |  | 104 ms / 94.8 ms |  |
| `edit_after_schematic` | 4.1 | 25.3 s / 25.1 s | 108 ms | x233 faster | v1.6.0 without the visibility gate: 1.85 s (v1.6.0 x17 faster) | 24.6 s / 114 ms |  |
| `latent_open` | 4.1 | 1 min 03 s / 1 min 05 s | 839 ms | x76 faster |  | 1 min 03 s / 849 ms |  |
| `lay_cable` | 4.1 | 244 ms / 245 ms | 150 ms | x1.6 faster | PF-7's parent (`69555e8`): 172 ms (v1.6.0 13% faster) | 313 ms / 210 ms |  |
| `manhole_click` | 4.1 | 120 ms / 121 ms | 84.5 ms | 30% faster | PF-5's parent (`473a149`): 92.4 ms (v1.6.0 8% faster) | 116 ms / 83.6 ms |  |
| `plan_recalculation` | control | 166 ms / 168 ms | 138 ms | 17% faster |  | 215 ms / 169 ms |  |
| `project_open` | control | 883 ms / 870 ms | 715 ms | 18% faster |  | 939 ms / 764 ms |  |
| `record_add` | 4.1 | 14.7 ms / 14.7 ms | 6.48 ms | x2.3 faster |  | 14.9 ms / 7 ms |  |
| `record_add_memory` | 4.1 | 3.53 ms / 3.71 ms | 0.887 ms | x4.1 faster |  | 4.64 ms / 1.53 ms |  |
| `route_correction` | 4.1 | 5.48 s / 5.73 s | 116 ms | not comparable | v1.6.0 without the QA fix to route ends (`ef58e92`): 222 ms (against v1.5.0, the same result: x25 faster) | 5.53 s / 131 ms | result digests differ |
| `route_path` | 4.1 | 191 ms / 190 ms | 182 ms | 5% faster | PF-7's parent (`69555e8`): 197 ms (v1.6.0 8% faster) | 214 ms / 208 ms |  |
| `run_validation` | control | 3 s / 3.01 s | 3.04 s | no measurable change |  | 3.03 s / 3.06 s |  |
| `save_gpkg` | control | 2.24 s / 2.23 s | 2.23 s | no measurable change |  | 2.2 s / 2.27 s |  |
| `schematic_open` | 4.1 | 26.5 s / 26.3 s | 1.85 s | x14 faster |  | 24.2 s / 1.84 s |  |
| `slack_click` | 4.1 | 238 ms / 234 ms | 134 ms | x1.8 faster |  | 294 ms / 191 ms |  |
| `slack_generate` | 4.1 | 17.4 s / 17.1 s | 346 ms | x50 faster |  | 17.3 s / 418 ms |  |
| `snap_move_breakpoint` | 4.1 | 107 ms / 102 ms | 3.86 ms | not comparable | PF-5's parent (`473a149`): 111 ms (v1.6.0 x29 faster) | 111 ms / 15 ms | result digests differ |
| `snap_move_closure` | 4.1 | 12.2 ms / 11.9 ms | 9.62 ms | not comparable | PF-5's parent (`473a149`): 536 ms (v1.6.0 not comparable); v1.6.0 with joint closures snapping to vertices only, as in 1.5.0: 9.1 ms (against v1.5.0, the same result: 24% faster) | 19.9 ms / 24.2 ms | result digests differ |
| `snap_move_element` | 4.1 | 581 ms / 589 ms | 9.32 ms | not comparable | PF-5's parent (`473a149`): 580 ms (v1.6.0 x62 faster) | 581 ms / 28.9 ms | result digests differ |
| `snap_move_pipe` | 4.1 | 514 ms / 492 ms | 9.84 ms | x51 faster | PF-5's parent (`473a149`): 554 ms (v1.6.0 x56 faster) | 522 ms / 22.3 ms |  |
| `snap_move_point` | 4.1 | 299 ms / 301 ms | 3.38 ms | x89 faster | PF-5's parent (`473a149`): 133 ms (v1.6.0 x39 faster) | 305 ms / 15.2 ms |  |
| `snap_move_route` | 4.1 | 766 ms / 763 ms | 34.5 ms | x22 faster | PF-5's parent (`473a149`): 791 ms (v1.6.0 x23 faster) | 781 ms / 54.9 ms |  |

### QGIS 4.0.3 (Qt6), size M

| Row | | v1.5.0 (before / after the v1.6.0 run) | v1.6.0 | Change | Middle column | First call, v1.5.0 / v1.6.0 | Notes |
|---|---|---|---|---|---|---|---|
| `bom_open` | control | 278 ms / 273 ms | 261 ms | 5% faster |  | 291 ms / 276 ms |  |
| `branch_offset` | control | 172 ms / 168 ms | 169 ms | no measurable change |  | 164 ms / 179 ms |  |
| `edit_after_schematic` | 4.1 | 2 min 18 s / 2 min 18 s | 203 ms | x679 faster | v1.6.0 without the visibility gate: 4.58 s (v1.6.0 x23 faster) | 2 min 18 s / 196 ms |  |
| `latent_open` | 4.1 | 6 min 09 s / 6 min 09 s | 2.08 s | x178 faster |  | 6 min 08 s / 2.08 s |  |
| `lay_cable` | 4.1 | 456 ms / 462 ms | 250 ms | x1.8 faster | PF-7's parent (`69555e8`): 302 ms (v1.6.0 17% faster) | 506 ms / 299 ms |  |
| `manhole_click` | 4.1 | 191 ms / 190 ms | 91.6 ms | x2.1 faster | PF-5's parent (`473a149`): 121 ms (v1.6.0 24% faster) | 184 ms / 102 ms |  |
| `plan_recalculation` | control | 419 ms / 416 ms | 348 ms | 17% faster |  | 430 ms / 352 ms |  |
| `project_open` | control | 1.17 s / 1.16 s | 913 ms | 22% faster |  | 1.21 s / 1 s |  |
| `record_add` | 4.1 | 27.4 ms / 27.8 ms | 6.52 ms | x4.2 faster |  | 27.5 ms / 7.84 ms |  |
| `record_add_memory` | 4.1 | 8.43 ms / 8.7 ms | 2.12 ms | x4 faster |  | 10.4 ms / 2.51 ms |  |
| `route_correction` | 4.1 | 32.3 s / 33.2 s | 287 ms | not comparable | v1.6.0 without the QA fix to route ends (`ef58e92`): 554 ms (against v1.5.0, the same result: x59 faster) | 32.1 s / 324 ms | result digests differ |
| `route_path` | 4.1 | 494 ms / 515 ms | 464 ms | 8% faster | PF-7's parent (`69555e8`): 503 ms (v1.6.0 8% faster) | 527 ms / 475 ms |  |
| `run_validation` | control | 7.46 s / 7.41 s | 7.46 s | no measurable change |  | 7.49 s / 7.39 s |  |
| `save_gpkg` | control | 2.67 s / 2.69 s | 2.65 s | 1% faster |  | 2.65 s / 2.64 s |  |
| `schematic_open` | 4.1 | 2 min 34 s / 2 min 36 s | 4.66 s | x33 faster |  | 2 min 16 s / 4.62 s |  |
| `slack_click` | 4.1 | 374 ms / 376 ms | 144 ms | x2.6 faster |  | 420 ms / 5.67 s |  |
| `slack_generate` | 4.1 | 25.4 s / 25.2 s | 360 ms | x70 faster |  | 25 s / 428 ms |  |
| `snap_move_breakpoint` | 4.1 | 246 ms / 255 ms | 3.92 ms | not comparable | PF-5's parent (`473a149`): 258 ms (v1.6.0 x66 faster) | 253 ms / 14.6 ms | result digests differ |
| `snap_move_closure` | 4.1 | 12.5 ms / 12.3 ms | 9.57 ms | 23% faster | PF-5's parent (`473a149`): 1.33 s (v1.6.0 x139 faster); v1.6.0 with joint closures snapping to vertices only, as in 1.5.0: 9.67 ms (against v1.5.0, the same result: 22% faster) | 20 ms / 22.9 ms |  |
| `snap_move_element` | 4.1 | 1.46 s / 1.44 s | 10.1 ms | not comparable | PF-5's parent (`473a149`): 1.5 s (v1.6.0 x149 faster) | 1.46 s / 23 ms | result digests differ |
| `snap_move_pipe` | 4.1 | 1.26 s / 1.24 s | 10 ms | x125 faster | PF-5's parent (`473a149`): 1.37 s (v1.6.0 x137 faster) | 1.25 s / 22.2 ms |  |
| `snap_move_point` | 4.1 | 766 ms / 750 ms | 3.83 ms | x198 faster | PF-5's parent (`473a149`): 314 ms (v1.6.0 x82 faster) | 754 ms / 16.5 ms |  |
| `snap_move_route` | 4.1 | 1.93 s / 1.89 s | 34.3 ms | x56 faster | PF-5's parent (`473a149`): 1.99 s (v1.6.0 x58 faster) | 1.97 s / 55.5 ms |  |

## 5. Profile evidence

Separate runs with cProfile instead of timing (`--profile`), on QGIS 3.44: twelve rows at S and five at M,
on the same trees and datasets. Profiling slows Python code down, so these times are not the benchmark's; the
call counts are the evidence. Each file lists the top 25 functions by cumulative and by own time.

- **Route correction, S**
  ([1.5.0](performance/raw/profile-v150-qgis344-S/profile-route_correction-S.txt),
  [1.6.0](performance/raw/profile-v160-qgis344-S/profile-route_correction-S.txt)). 1.5.0 makes 5,110,731
  point-to-point `distance` calls, from the two generator expressions at `main_plugin.py:3730` and `:3739`
  that `any()` runs over every pole and manhole for each of the 3,632 route ends: the `any()` calls take
  7.37 s of the profiled 7.48 s.
  1.6.0 makes 334,787 calls in all, in 0.218 s, filling its point grid in 0.074 s
  (`route_ends.node_index`). This is the check as shipped, which also counts more ends as connected (602
  findings against 4, section 7); PF-3's own index, at 1.5.0's findings, is the middle column.
- **Optical Schematic View, S**
  ([1.5.0](performance/raw/profile-v150-qgis344-S/profile-schematic_open-S.txt),
  [1.6.0](performance/raw/profile-v160-qgis344-S/profile-schematic_open-S.txt)). 1.5.0: 39,377,242 calls in
  31.1 s. Collecting the edges (`schematic_dialog.py:346`) takes 21.4 s, 18.7 s of it in the function's own
  loop; the whole action makes 3,940 feature requests; the label check takes 9.3 s, with 17,229,707
  `intersects` calls from the generator expression at `:782`. 1.6.0: 1,378,203 calls in 2.36 s. The edges
  take 0.92 s, with one batched read per layer (`utils/batch.py`, 0.095 s), and the labels 1.13 s, of which
  the grid's collision test (`RectGrid.any_passes`, 11,290 calls) is 0.18 s. Both draw the same 14,846 scene
  items.
- **List of latent elements, S**
  ([1.5.0](performance/raw/profile-v150-qgis344-S/profile-latent_open-S.txt),
  [1.6.0](performance/raw/profile-v160-qgis344-S/profile-latent_open-S.txt)). 1.5.0: 65.3 s. The element
  search per cable (`data_manager.py:524`, 2,041 calls) takes 51.4 s, with 4,531,020 GEOS `distance` calls,
  and the list makes 28,576 feature requests. 1.6.0: 0.91 s. The same search takes 0.23 s and 7,032
  `distance` calls. Both list 2,041 cables, 1,297 of them with Edit enabled.
- **Generate terminal slacks, S**
  ([1.5.0](performance/raw/profile-v150-qgis344-S/profile-slack_generate-S.txt),
  [1.6.0](performance/raw/profile-v160-qgis344-S/profile-slack_generate-S.txt)). 1.5.0: 17.2 s for 100
  slacks, with 300 `startEditing` (3.95 s) and 200 `commitChanges` (4.25 s), 100 cable restyles (4.81 s, the
  cable-type migration 4.68 s of it) and 100 node searches (`slack_tool._nearest_node`, 3.07 s). 1.6.0:
  0.41 s, with 2 `startEditing`, 2 `commitChanges`, one restyle (8 ms), and the node searches in 0.22 s
  through box reads.
- **Route tool, nine moves, S**
  ([1.5.0](performance/raw/profile-v150-qgis344-S/profile-snap_move_route-S.txt),
  [1.6.0](performance/raw/profile-v160-qgis344-S/profile-snap_move_route-S.txt)). 1.5.0: 1.00 s in
  `route_tool._find_snap_point`, with 125,640 `distance` and 16,344 `asPolyline` calls. 1.6.0: 0.040 s in
  all, for 144 box reads (`utils.spatial.features_within`: 16 layers, nine moves). Both snap on 6 of the
  nine moves.
- **Planning a length recalculation, a control, M**
  ([1.5.0](performance/raw/profile2-v150-qgis344-M/profile-plan_recalculation-M.txt),
  [1.6.0](performance/raw/profile2-v160-qgis344-M/profile-plan_recalculation-M.txt)). 1.5.0 looks the
  measurer up again for every feature: 14,138 calls to `measure.distance_area`, and as many to
  `measure.resolve_ellipsoid`, for 14,133 features measured, in 0.64 s. 1.6.0 makes 10 calls to
  `distance_area`, in 0.46 s, for the same plan of 56 changes (section 6 says why a control moved).

## 6. What changed, row by row

| Row | Technique | Commits | PR |
|---|---|---|---|
| `schematic_open` | one feature request per layer (`utils.batch.features_by_id`) instead of reading the layer until each edge's feature came up; label collisions checked in a uniform grid (`utils.spatial.RectGrid`), which stops at the first overlap | `6984857`, `c0a82db` | [#60](https://github.com/vukovicvl/fiberq/pull/60) |
| `edit_after_schematic` | the same rebuild, cheaper; and (supporting, unclaimed) a closed view no longer rebuilds after every commit, only when it is shown again | `6984857`, `c0a82db`; the gate `581273c` | [#60](https://github.com/vukovicvl/fiberq/pull/60) |
| `latent_open` | one batched read of the cables; the elements near each cable from an index that hands them back in scan order (`utils.spatial.ScanOrderIndex`) | `1d6b14d` | [#60](https://github.com/vukovicvl/fiberq/pull/60) |
| `route_correction` | the poles and manholes near each route end from the same index (PF-3), as the middle column measures it. As shipped, the unclaimed QA fix `ef58e92` checks fifteen node layers and files their points in a grid of 2 cm cells instead (`route_ends.node_index`), and checks an end on no point against the other routes through a `ScanOrderIndex`, so the as-shipped times are not PF-3's | `da40487`; as shipped also `ef58e92` | [#60](https://github.com/vukovicvl/fiberq/pull/60); `ef58e92` in [#68](https://github.com/vukovicvl/fiberq/pull/68) |
| `slack_generate` | one edit session per layer instead of one per slack; each cable recomputed once and each layer restyled once | `d4cb97a` | [#61](https://github.com/vukovicvl/fiberq/pull/61) |
| `slack_click` | the cables and nodes near the click, read through the file's R-tree | `b8353ae` | [#61](https://github.com/vukovicvl/fiberq/pull/61) |
| `snap_move_*`, `manhole_click` | FiberQ's own snap reads only the features whose box comes within its tolerance of the cursor, through the file's R-tree, instead of every feature of every layer it snaps to (the joint-closure tool already read through a box in 1.5.0, and lost it in the rewrite PF-5's parent holds; see that rewrite below) | `69555e8` | [#62](https://github.com/vukovicvl/fiberq/pull/62) |
| `record_add`, `record_add_memory` | the features near the new one, then one primary-key query, instead of a GEOS distance to every feature; on a memory layer both reads are C++ passes, over every feature's box and then over its list of feature ids | `d4a8464` | [#61](https://github.com/vukovicvl/fiberq/pull/61) |
| `lay_cable`, `route_path` | the routes near the first element, read through the file's R-tree; the nearest graph vertex from the graph's own grid | `bfc99fa`, `f3d489b` | [#62](https://github.com/vukovicvl/fiberq/pull/62) |

The shared helpers are `fiberq/utils/spatial.py` (`0b47dde`, [#60](https://github.com/vukovicvl/fiberq/pull/60)),
`fiberq/utils/batch.py` (`6984857`) and `fiberq/utils/geopackage.py` (`b8353ae`,
[#61](https://github.com/vukovicvl/fiberq/pull/61)). Each narrowed search keeps its own test and runs it over
what the index hands back: in the order the whole layer would have handed it out wherever a first match or a
tie decides, and in any order where the only question is whether anything passes (the label grid, the
route-end grid). So it answers what the scan answered. Where a box cannot answer exactly, the layer is read
whole, as before (section 9). On a GeoPackage a box read is an R-tree lookup; on a memory layer it is a C++
pass over the features' boxes, which saves the Python loop and the measuring per feature, not the pass
(section 8).

Which middle column isolates which claim is in section 2: PF-5's parent for PF-5, PF-7's parent for PF-7,
v1.6.0 without the gate for PF-1's edit row, and the two equal-result columns for PF-3 and for the closure
row. The other rows have none, and their v1.5.0 → v1.6.0 change is the claimed work plus any of the changes
listed below that sit on the same path.

### Supporting and unclaimed changes in the v1.6.0 column

- **The visibility gate** (`581273c`, [#60](https://github.com/vukovicvl/fiberq/pull/60); supporting,
  unclaimed): a closed Optical Schematic View no longer rebuilds after every commit, and catches up when it is
  shown again. Its middle column takes it out. The claimed batching and index take the edit from 21.4 s to
  1.77 s at S, and the gate takes it from there to 109 ms: x16 of the x196 at S (x21 of x605 at M, x24 of
  x1798 at L), but 8% of the seconds saved at S, 3% at M and 1% at L.
- **The placement-snapping rewrite** (`a264610`,
  [#51](https://github.com/vukovicvl/fiberq/pull/51); unclaimed): QGIS's snapping when the magnet is on and
  a corrected fallback when it is off (section 7). It is in PF-5's parent, so outside the PF-5 comparison.
  On the pole tool the rewritten scan is itself faster than 1.5.0's (122 ms against 278 and 289 ms at S on
  3.44), which is why that row's factor over its parent (x33) is lower than its factor over 1.5.0 (x77).
  On the joint-closure tool it went the other way. 1.5.0's tool read each layer through a box; the rewrite
  gave it the shared snap, which in PF-5's parent reads every feature, so the parent takes 479 ms, 1.2 s and
  3.04 s at S, M and L on QGIS 3.44, against 1.5.0's 12.7–13.4 ms. PF-5's box reads give that back: v1.6.0's
  factors over that parent on the closure row (x113 and x139 at M on QGIS 3.44 and 4.0) repair a slowdown
  1.6.0's own rewrite brought in, and are no gain over 1.5.0. One more of the rewrite's changes moves the
  parent column for reasons other than indexing: a vertex test beside the segment test for each line
  feature (1.5.0's element tool tested segments only), so that a vertex wins over a point on a segment. The
  rewrite also finds layers under their pre-1.0 names, which this benchmark's English-named layers do not
  exercise.
- **The broken-geometry skip** (`e407550`, [#62](https://github.com/vukovicvl/fiberq/pull/62); unclaimed),
  which lets a box read answer what the scan does (section 7). It is in PF-5's parent.
- **`a430e24`** ([#62](https://github.com/vukovicvl/fiberq/pull/62); supporting, unclaimed): `line_parts`
  stops copying every point it reads, repairing a routing slowdown introduced earlier in 1.6.0's own
  development. It is in PF-7's parent.
- **The slack tool's search fixes** (`2da4b56`, [#61](https://github.com/vukovicvl/fiberq/pull/61), and
  `473a149`, [#62](https://github.com/vukovicvl/fiberq/pull/62); unclaimed): the slack tool finds its cable
  whatever else is in the layer (a multipart cable among them), and a click survives an infinite coordinate
  in a node layer. Both sit on the `slack_click` path, which has no middle column.
- **The cable-type migration** that every cable restyle runs: after Lay cable, after a slack recompute, and
  twice per cable layer when a project opens. `641882b` ([#61](https://github.com/vukovicvl/fiberq/pull/61),
  supporting) makes it read only the rows that hold an old type value, and `c7da6e8` (#61, unclaimed) makes it
  open an edit session only when a row needs migrating; in the "Buffered groups" transaction mode the old
  no-op session rolled back every unsaved edit in the project. Both parent columns have them. The slack rows,
  which have no middle column, include them: in v1.5.0's profile at S the migration takes 45 ms of the slack
  click's 240 ms, and 6 ms in v1.6.0's
  ([1.5.0](performance/raw/profile-v150-qgis344-S/profile-slack_click-S.txt),
  [1.6.0](performance/raw/profile-v160-qgis344-S/profile-slack_click-S.txt)). In Lay cable's it takes 55 ms
  of 278 ms, and 6 ms of 203 ms
  ([1.5.0](performance/raw/profile-v150-qgis344-S/profile-lay_cable-S.txt),
  [1.6.0](performance/raw/profile-v160-qgis344-S/profile-lay_cable-S.txt)).
- **Per-move caching in the shared snap** (`d4a252f`, [#67](https://github.com/vukovicvl/fiberq/pull/67), and
  `bf50c14`, [#68](https://github.com/vukovicvl/fiberq/pull/68); supporting, unclaimed): each mouse move
  stops working out again what has not changed (which layers qualify, whether a layer's box query can be
  trusted, the snap marker it already shows), and box reads fetch no attributes. Both are in v1.6.0 and not
  in PF-5's parent, so the placement rows' factors over the parent include them. Measured during development
  on the closure row at S, `d4a252f` took nine moves from 17.7 ms to 11.7–11.9 ms, against 12.8–12.9 ms for
  1.5.0 (its commit message): a few milliseconds where PF-5 saves hundreds, but the whole of the closure
  row's lead over 1.5.0, whose closure tool already read through a box.
- **The QA fix to route ends** (`ef58e92`, [#68](https://github.com/vukovicvl/fiberq/pull/68); unclaimed)
  and **closures snapping along spans** (`7044c4f`, #68; unclaimed): section 7. Each has its own middle
  column, compared with v1.5.0. As shipped, the route-end check no longer uses PF-3's index: it files the
  fifteen layers' points in its own grid (`route_ends._PointGrid`).

### The controls that move

- **`project_open`, 18–26% faster.** When a project opens, 1.5.0 migrates each cable layer's type values
  twice (its layer-added hook restyles the layer and applies its field aliases), and every migration opened
  an edit session and read the whole layer: `641882b` and `c7da6e8` above. In v1.5.0's profiles one
  migration of the S city's underground cables takes 45–55 ms
  ([`profile-slack_click-S.txt`](performance/raw/profile-v150-qgis344-S/profile-slack_click-S.txt),
  [`profile-lay_cable-S.txt`](performance/raw/profile-v150-qgis344-S/profile-lay_cable-S.txt)). This row was
  not profiled; the attribution rests on the migration's cost in those two rows' profiles and on what the
  code runs when a project opens.
- **`bom_open`, 4–6% faster.** The bill of materials was rewritten by a 1.6.0 reliability fix (`c9caa24`,
  [#58](https://github.com/vukovicvl/fiberq/pull/58)) that counts and reports what it cannot measure and
  measures in each layer's own CRS (section 7). Among the differences, 1.6.0 reads each line feature's
  stored length once where 1.5.0 read it twice. This row was not profiled, so the 4–6% is reported, not
  attributed. Its digest is the number of layers the dialog lists (22 in every run), so the benchmark does
  not compare the lengths the dialog prints.
- **`plan_recalculation`, 17–25% faster.** An earlier run of this benchmark found it 3–9% slower than 1.5.0
  at S and M (`6973f05`'s commit message): the lengths-follow-edits work had added two Python calls per
  feature to a loop that, in 1.5.0 already, resolved the project's ellipsoid, the layer's CRS and the
  measurer again for every feature. `6973f05` ([#68](https://github.com/vukovicvl/fiberq/pull/68),
  unclaimed) resolves them once per layer, which removes 1.5.0's per-feature cost as well, hence faster than
  1.5.0 with the same plan: 14,138 measurer lookups at M in 1.5.0's profile, 10 in 1.6.0's (section 5).
- **`save_gpkg`: no measurable change** (1% faster on QGIS 4.0 at M). An earlier run of this benchmark found
  Save all 2–3% slower than 1.5.0 (`2822204`'s commit message): a fix made during the 1.6.0 QA (`d8f297e`,
  unclaimed) read the file's tables again before each layer's write. `2822204` (#68, unclaimed) drops that
  re-read, by the maintainer's decision. The profile at M shows the same 24 writes taking 1.84–1.85 s in both
  ([1.5.0](performance/raw/profile2-v150-qgis344-M/profile-save_gpkg-M.txt),
  [1.6.0](performance/raw/profile2-v160-qgis344-M/profile-save_gpkg-M.txt)). On QGIS 3.44 at S the row
  carries the drift flag: both v1.5.0 runs (2.47 and 2.53 s) are 15–18% slower than the October baseline's
  2.14 s, and v1.6.0's 2.49 s lies between them. The result files do not say why this session differs from
  October; the verdict uses the interleaved session only.
- **`run_validation` on 3.44 at L and `save_gpkg` on 4.0 at M come out 1% faster**: outside both v1.5.0 runs'
  ranges, so the rule shows them, and too small to read as more than the noise the controls are there to
  show. `branch_offset` does not move.

## 7. Intentional behaviour changes (not presented as performance results)

These change what a user sees, and some change what a benchmark row computes; none of them is presented as a
result of the performance work.

- **Generate terminal slacks** (`d4cb97a`, [#61](https://github.com/vukovicvl/fiberq/pull/61); since
  `2f6b6a1`, [#63](https://github.com/vukovicvl/fiberq/pull/63), unclaimed, on pre-1.0 slack layers too) runs
  as one edit session per layer only where that answers exactly as 1.5.0's per-slack loop did: layers saved
  one by one (no transaction group), memory or GeoPackage layers with no edit session of the user's, no
  filter, no default applied on update and no trigger or constraint of the database's own, and no old cable
  type values. Elsewhere the loop runs unchanged. Two differences remain. The loop's in-between cable writes
  are not repeated: the first of a cable's two totals, overwritten by the second, and the commit and signals
  that came with it. And a write refused for a reason the file does not show beforehand (a locked or full
  disk) is reported twice over: QGIS also shows the abandoned attempt's own provider errors, and FiberQ's
  message names the unsaved slack by a lower temporary id than 1.5.0 would, because QGIS deals those ids from
  one counter for the whole session and the batch drew its own first.
- **The placement snaps' corrections** (`a264610`, [#51](https://github.com/vukovicvl/fiberq/pull/51);
  unclaimed). The element and breakpoint tools compared a squared distance with a linear tolerance, so a
  vertex in reach often did not snap; every distance is now linear. A vertex wins over a point on a segment,
  layers are found under their pre-1.0 names too, the pole and manhole tools snap along a segment rather than
  only to its midpoint, and with QGIS's magnet on, the element, pole, manhole and joint-closure tools follow
  the project's snapping settings and show QGIS's snap marker; the slack tool keeps its own search for a
  cable end or span, with the magnet on or off, and shows QGIS's snap marker on the place it will use. In the
  benchmark more of the nine moves snap: with the element tool 5 where 1.5.0 snapped 4 at S, and 6 where it
  snapped 5 at M and L; with the breakpoint tool 5 where it snapped 2 at S, and 6 where it snapped 5 at M and
  L. That is why those two rows are compared through PF-5's parent, which already has the correction.
- **FiberQ's own snaps skip geometry a box query can miss** (`e407550`,
  [#62](https://github.com/vukovicvl/fiberq/pull/62); unclaimed), the price of exact box reads: a line with a
  coordinate that is not a finite number, a MultiLineString with a one-vertex part, an arc through three
  points in a row, and on QGIS 3.22 an arc starting at (0, 0); with QGIS snapping off also a MultiPoint with a
  part whose coordinate is not a number, and a GeometryCollection or polygon with such a part or ring.
  Well-formed data is untouched.
- **Joint closures also snap along a span** (`7044c4f`, [#68](https://github.com/vukovicvl/fiberq/pull/68);
  unclaimed). With the magnet off the closure tool snapped to vertices and nodes only, so on a straight
  two-vertex route there was nothing to land on between its ends. It now snaps along route and cable spans as
  the other placement tools do, and a vertex or node within reach still wins. In the benchmark the closure
  snaps on 6 of the nine moves where 1.5.0 snapped on 4 at S, and on 7 where it snapped on 6 at L (6 and 6 at
  M). The row is compared through the column that puts vertex-only snapping back.
- **Route correction** (`ef58e92`, [#68](https://github.com/vukovicvl/fiberq/pull/68); unclaimed). An end on
  any of the fifteen layers FiberQ ends routes and cables on (poles, manholes, joint closures and the twelve
  element layers) or on another route's vertex is connected, not an error; 1.5.0 accepted poles and manholes
  only. Correct moves an end at most 5 m on the ground, onto the nearest pole, manhole, joint closure or
  element, and never pulls it away from a cable or duct laid along the route; 1.5.0 moved it at any
  distance. The findings on the benchmark cities drop from 602, 1,394 and 3,500 to 4, 3 and 4 at S, M and L,
  which is why the row is compared through the column without this fix.
- **The bill of materials** (`c9caa24`, [#58](https://github.com/vukovicvl/fiberq/pull/58), a 1.6.0
  reliability fix) uses each line's stored length when it is a number above 0, and otherwise measures the
  line on the ground in its layer's own CRS, as FiberQ's stored lengths are measured. 1.5.0 seeded that
  measurement from the map CRS and the project's ellipsoid: one case measured during development gave
  100.0 m in the report against 70.93 m in the table (the commit's message). It also stops trusting a stored
  length of 0 over the geometry, and counts and reports each line it cannot measure, which 1.5.0 added in as
  0 without a word, so its figures can differ from 1.5.0's.

## 8. Placement snapping on memory layers (scratch projects)

FiberQ creates its layers as memory layers, and they stay memory layers until they are saved to a
GeoPackage. A project that has not been saved yet therefore snaps on memory layers, which the city benchmark
does not measure. [`tools/bench/test_snap_memory_scaling.py`](../tools/bench/test_snap_memory_scaling.py)
does: it builds Route, Poles and Manholes memory layers of 4 to 20,000 features (n three-vertex routes, a
pole at each end and a manhole on the middle vertex), turns QGIS snapping off so that FiberQ's own snap
answers, and moves the mouse near a route vertex and over a span with the joint-closure tool, the pole tool
and the element tool placing an ODF. Each figure is the best of seven rounds of 200 moves, in microseconds
per move. It ran at the end of the same session on QGIS 3.40.15 and 4.2.3, v1.5.0, v1.6.0, then v1.5.0
again, and its six output files are in [`raw/snap-memory-scaling/`](performance/raw/snap-memory-scaling/).

Microseconds per mouse move, v1.5.0's first and second run → v1.6.0. Differences and factors in the bullets
below are against the mean of v1.5.0's two runs. The script times the moves and compares no results, so
none of these figures is a verdict by the rule of section 2.

**QGIS 3.40.15-Bratislava**

| Tool | Cursor | 4 features | 400 | 4,000 | 20,000 |
|---|---|---|---|---|---|
| Joint closure | near a vertex | 89.0 / 89.4 → 164.8 | 117.6 / 116.0 → 189.6 | 316.4 / 311.1 → 383.4 | 1353.2 / 1395.3 → 1554.2 |
| Joint closure | over a span | 78.9 / 79.1 → 154.4 | 104.1 / 102.3 → 181.8 | 297.4 / 294.5 → 370.6 | 1343.5 / 1362.6 → 1552.0 |
| Pole | near a vertex | 101.5 / 101.9 → 161.0 | 1462.6 / 1454.1 → 167.6 | 14239.0 / 13823.2 → 217.0 | 72311.9 / 71134.3 → 426.0 |
| Pole | over a span | 101.1 / 100.9 → 160.6 | 1469.7 / 1452.1 → 167.7 | 14196.8 / 13963.7 → 216.6 | 71498.3 / 70882.8 → 426.4 |
| Element (ODF) | near a vertex | 66.1 / 67.6 → 166.0 | 1532.9 / 1491.0 → 189.4 | 15015.9 / 14750.5 → 383.1 | 78347.9 / 77187.9 → 1536.3 |
| Element (ODF) | over a span | 66.7 / 70.4 → 154.3 | 1529.9 / 1500.9 → 179.6 | 14846.6 / 14760.2 → 374.8 | 78228.9 / 76877.8 → 1527.3 |

**QGIS 4.2.3-Belém do Pará**

| Tool | Cursor | 4 features | 400 | 4,000 | 20,000 |
|---|---|---|---|---|---|
| Joint closure | near a vertex | 84.8 / 87.4 → 160.1 | 115.1 / 116.7 → 192.0 | 307.1 / 308.7 → 394.1 | 1415.9 / 1382.3 → 1501.4 |
| Joint closure | over a span | 73.8 / 75.9 → 149.5 | 105.0 / 106.2 → 179.8 | 301.3 / 293.1 → 377.9 | 1386.6 / 1379.9 → 1509.2 |
| Pole | near a vertex | 87.0 / 89.4 → 145.9 | 1408.1 / 1427.0 → 156.2 | 12892.2 / 13087.8 → 206.7 | 64333.0 / 66158.5 → 414.2 |
| Pole | over a span | 86.7 / 88.1 → 145.1 | 1412.2 / 1423.8 → 155.7 | 12740.0 / 12994.7 → 206.0 | 65206.0 / 66517.0 → 419.2 |
| Element (ODF) | near a vertex | 62.7 / 63.7 → 159.3 | 1495.3 / 1454.1 → 192.7 | 13898.3 / 13538.6 → 386.8 | 73058.9 / 71282.2 → 1516.0 |
| Element (ODF) | over a span | 62.4 / 65.7 → 151.1 | 1499.9 / 1456.3 → 182.4 | 13826.0 / 13579.7 → 374.0 | 73152.0 / 71485.5 → 1514.8 |

Both halves, plainly:

- **Each of the three tools pays a fixed cost of about 0.06–0.10 ms a move more than in 1.5.0.** At 4
  features v1.6.0 takes 58–60 µs more than 1.5.0 with the pole tool, 74–76 µs more with the closure tool and
  86–99 µs more with the ODF tool, on both QGIS versions. That is the shared snap's own work on each move,
  which 1.5.0's per-tool snaps did not do: checking whether QGIS's snapping is on, checking that each layer's
  box read can be trusted and sorting what it returns into scan order, and the broken-geometry check on a
  feature that would win (section 7); the joint-closure tool now also tests each span. The script does not
  break the cost down further. QGIS's snap marker is not part of it: the script repeats one mouse position,
  and a match already shown is not sent again.
- **The joint-closure tool stays at least that much slower at every size.** 1.5.0's closure tool already
  asked each layer for a box, so there is no scan for 1.6.0 to remove. Up to 4,000 features it takes
  70–86 µs a move more than 1.5.0 on both versions; at 20,000 features 0.18–0.20 ms more on QGIS 3.40, and
  0.10–0.13 ms more on 4.2.
- **The pole and ODF tools are many times faster from 400 features on**, because 1.5.0 measured every
  feature of the layers they snap to, in Python, on every move: 7.7–9.1 times faster at 400 features, 35–65
  times at 4,000 and 48–168 times at 20,000. The pole tool, which snaps to the Route layer alone, gains the
  most; the ODF tool reads Route, Poles and Manholes, as the closure tool does.

FiberQ gives its memory layers no spatial index. During development an indexed memory layer crashed QGIS (a
segmentation fault) as soon as two points beyond ±2e154 were committed to it, on QGIS 3.22, 3.44 and 4.2,
while the same data without an index was fine, and FiberQ cannot guard QGIS's own writes
([PR #62](https://github.com/vukovicvl/fiberq/pull/62)). So on a memory layer a box read is a C++ pass over
every feature's box, and its cost still grows with the layer, as the 20,000-feature column shows. PR #62's description, written
before these measurements, says the joint-closure tool is back to 1.5.0's speed on memory layers; the figures
above replace that statement. A memory
layer the user gave an index of their own (Layer Properties, Processing) is read whole by the snaps. On a
GeoPackage, where both versions' box reads go through the file's R-tree, the same closure tool is 19–24%
faster than 1.5.0 at equal snapping (section 4); that lead comes from the unclaimed per-move caching
(section 6), not from PF-5, whose box read only brings the tool back to 1.5.0's way of reading.

## 9. Limitations

- **One machine.** A laptop processor inside Docker, five pinned logical CPUs and the `performance`
  governor: the figures compare two versions on one machine, and are not a claim about anyone else's.
- **Not measured**: rendering time and memory use; QGIS 3.22, where the fixture cannot be generated (it has
  no `QgsMapLayer.setId`; 3.22 reads the projects the benchmark measures); QGIS 4.0 at size L; shapefile,
  PostGIS and WFS layers (the cities are one GeoPackage; memory layers are measured only by the
  `record_add_memory` row and by section 8's script).
- **What a digest covers.** For several rows the facts are counts: how many of the nine moves snapped, one
  slack or manhole added, one cable added between the same two closures, the vertex count of each path, the
  number of layers the bill of materials lists. That the narrowed searches land on the same point and lay the
  same cable as the whole scan is checked by the test suite, not by this benchmark:
  `tests/test_snap_reads_near.py` runs each snap search both ways, `tests/test_lay_cable_route_search.py` runs
  lay cable's one-route search both ways, and before PF-5 and PF-7 merged, captures of cursor positions,
  manhole clicks, laid cables and route paths came out identical before and after them
  ([PR #62](https://github.com/vukovicvl/fiberq/pull/62); the captured cables went through the network
  search, not the one-route search).
- **Single repetitions above a minute.** Such a call is timed once after its warm-up (MAD 0), so the v1.5.0
  range of such a row is the two runs' single timings. 1.5.0's schematic view is slower on its warm-up and
  its median timed call than on its first call (by 5–10% at S, 9–13% at M and 18–28% at L), which the result
  files do not explain; 1.6.0's warm-up and median are at most 1% slower than its own first call. Taken from the first calls instead (the
  mean of both v1.5.0 runs' first calls against v1.6.0's), the schematic view's factors on QGIS 3.44 are x12,
  x27 and x71 at S, M and L, where the tables show x13, x30 and x88.
- **First calls** are the first use of the code in a fresh process, and pay for it. Two stand out, and
  neither result file records an error: `save_gpkg` in the session's very first run (v1.5.0, QGIS 3.44, S)
  took 7.76 s, against 2.48 and 2.50 s for the other two runs' first calls there; `slack_click`'s v1.6.0
  first call on QGIS 4.0 at M took 5.67 s, against 0.19–0.22 s at the other sizes and images, with the
  1-minute load average at 1.66 before it, among the session's highest. The timed repetitions of both are in
  line with the other runs.
- **Layers read whole.** Every source other than a GeoPackage, a shapefile or a memory layer keeps the
  whole-layer scan (PostGIS, WFS and other OGR formats such as GeoJSON among them), because FiberQ cannot rely
  on their order being feature-id order. So do a GeoPackage or shapefile layer with a filter, a GeoPackage
  view, a GeoPackage table not keyed by SQLite's rowid, a GeoPackage line table that registers a curve
  extension (arcs), a layer declared as a curve type (CompoundCurve, MultiCurve), a GeoPackage that cannot be
  read at that moment (a locked file is asked again a second later), and, for the snaps, a memory layer with
  a spatial index of its own. There the snaps read every feature, as before, and the joint-closure tool reads
  them whole where 1.5.0 asked each for a box, so it is expected to be slower than 1.5.0 there. This
  benchmark measures none of them.
- **Schema re-read after each write.** After any write to a GeoPackage, the first search of one of its layers
  reads the file's schema again. Measured during development
  ([PR #62](https://github.com/vukovicvl/fiberq/pull/62)): about 3–4 ms with the benchmark's 24 tables, more
  with more tables. On the generator's XS city (a 12 × 12 street grid of about 2,000 features, used in CI and
  not part of this benchmark) that made the first snap move after a commit 2–3 times slower than before PF-5
  for the pole, manhole and breakpoint tools, every later move far faster, and a slack click 1–1.5 ms slower
  after each slack it places. A fresh process's first move reads the schema too: the joint-closure tool's
  first nine moves take 22.9–25.8 ms in v1.6.0 against 19.9–25.3 ms in 1.5.0's first run (the first-call
  column), slower in four of the five tables.
- **Lay cable's one-route search** (PF-7) reads the route layer whole unless it is an unfiltered GeoPackage
  table nobody is editing, keyed by its rowid, without arcs, with its R-tree, in a file it can read, and with
  500 routes or more; so shapefile, memory, PostGIS, edited, filtered, view, arc-holding and
  non-standard-key route layers are read whole. It also reads whole whenever the rows near the first element
  plus every multi-part row would be more than a quarter of the table. Its fixed work, about 4 ms of schema
  after a write plus 15–21 ms at L for the R-tree query and a pass over the rows, makes a pair on one of the
  first several hundred routes in feature-id order (about #800 at L) slower than the whole read, which stops
  at its route; on tables of multi-part routes some early pairs are up to about four times slower. Every
  later pair on a table of single lines is faster, the last ones about ten times (measured during
  development, [PR #62](https://github.com/vukovicvl/fiberq/pull/62)). The benchmark's pair is one no single
  route joins, so its search reads to the end of the table, where narrowing helps most.
- **Large unsaved edits.** With thousands of unsaved geometry changes in one layer, the first search after
  each edit reads the edit buffer: 24 ms with all 11,619 routes of the L city changed. Each move after it
  takes 2–3 ms (measured during development, [PR #62](https://github.com/vukovicvl/fiberq/pull/62)).
- **The label grid's worst case.** The schematic view's grid is bounded by the labels in the cells a query
  covers, not by 1.5.0's scan, so a scene built against it (two piles of coincident nodes a label apart) can
  cost more than the scan; the benchmark cities stay at 57 tests per query or fewer
  ([PR #60](https://github.com/vukovicvl/fiberq/pull/60)).
- **The memory-layer script** measures three tools on synthetic layers and compares no results: in the span
  position v1.6.0's closure tool lands on the span, where 1.5.0's found nothing to snap to (section 7). It
  ran on QGIS 3.40 and 4.2, not on the benchmark's 3.44 and 4.0.

## 10. Reproducing a run

From a full clone of the repository with its tags (the middle trees come from earlier commits, so a release
archive or a shallow clone will not do), with Docker. The containers write only under `/tmp/bench` here; any
scratch directory outside the repository will do. The session's frequency governor was `performance`
(checked on cpu0 before it started, and recorded in every result file), and each run started only once the
1-minute load average was below 1.5; `bench.py` itself only refuses a load above `--max-load` (2.0 by
default) and does not check the governor. The images are named by digest, because a tag moves with each
point release.

```sh
# The images as measured: qgis/qgis:3.44-trixie and qgis/qgis:4.0-trixie.
IMG=qgis/qgis@sha256:6df39d4b09c7ccceb18b80644a377e27829f408f64b33ca55e6fd7d7eaa92006
IMG40=qgis/qgis@sha256:23c12670e69909e8659a5c098aa307996735a5763b9ff9c3268bdeeee1a10916

# The datasets, once per size. Their digests must be the ones in section 2.
mkdir -p /tmp/bench/data /tmp/bench/code /tmp/bench/out /tmp/bench/tmp
for size in S M L; do
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e QT_QPA_PLATFORM=offscreen \
    -v "$PWD:/src:ro" -v /tmp/bench:/work $IMG \
    python3 /src/tests/fixtures/make_city_project.py --size $size --seed 20260921 \
      --out /work/data/city_$size/city_$size.gpkg
done

# The trees, from git objects only. `git rev-parse v1.6.0:fiberq` prints cf7ce22b9999514c8567328a2fc487abbdef0e4b.
extract() { mkdir -p /tmp/bench/code/$1/fiberq && git archive $2:fiberq | tar -x -C /tmp/bench/code/$1/fiberq; }
extract v150 v1.5.0; extract v160 v1.6.0; extract mid-pf5 473a149; extract mid-pf7 69555e8
extract mid-pf3 v1.6.0 && git show --format= ef58e92 -- fiberq | (cd /tmp/bench/code/mid-pf3 && git apply -R)
extract mid-q9b v1.6.0 && git show --format= 7044c4f -- fiberq | (cd /tmp/bench/code/mid-q9b && git apply -R)
extract mid-gate v1.6.0
# ...then delete the two `if not self.isVisible():` blocks (each sets self._stale and returns) from
# _schedule_rebuild and _do_rebuild_if_needed in /tmp/bench/code/mid-gate/fiberq/dialogs/schematic_dialog.py.

# Before every run: the governor, then the load.
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | sort -u   # must print only: performance
until awk '{ exit !($1 < 1.5) }' /proc/loadavg; do sleep 30; done      # the 1-minute load below 1.5

# One run: here v1.5.0's first run on QGIS 3.44 at S (on 4.0: $IMG40 and qgis/qgis:4.0-trixie).
docker run --rm --user "$(id -u):$(id -g)" --cpuset-cpus 2-6 --network none \
  -v "$PWD:/src:ro" -v /tmp/bench:/work -w /work \
  -e QT_QPA_PLATFORM=offscreen -e TMPDIR=/work/tmp -e HOME=/tmp \
  -e FIBERQ_BENCH_IMAGE=qgis/qgis:3.44-trixie -e FIBERQ_BENCH_IMAGE_DIGEST="${IMG#*@}" \
  $IMG python3 /src/tools/bench/bench.py \
    --code /work/code/v150 --label v1.5.0 \
    --data S=/work/data/city_S --expect-digest ae4011b9fe9cf3a50b9c611936c2a38ae1f19735a05e3e74ce941cd55ca7df52 \
    --expect-code-sha256 c208d1a607bf74998fca62cbcf7bd7dc7d1d1cddb0db59700def56b379749fac \
    --out /work/out/final-v150-a1-qgis344-S --scratch /work/tmp \
    --budget-s 1800 --timeout-s 7200 --run-id final-v150-a1-qgis344-S
```

The session ran that command for every image, size and tree in the order of section 2, each with its own
label and code digest ([`raw/README.md`](performance/raw/README.md) lists them). Name each run's `--out`
directory as the session did, `final-<kind>-qgis<344|40>-<S|M|L>` with the kinds `v150-a1`, `v160`,
`mid-pf5`, `mid-pf7`, `mid-gate`, `mid-pf3`, `mid-q9b` and `v150-a2`: `bench_report.py` reads only
directories named that way (and `baseline-v150-…`) and skips any other. A middle column takes only its rows,
one `--scenario <row>` each, and a label that names no version, such as `mid-pf5-parent-473a149`; a profile
pass adds `--profile` and the rows to profile.

```sh
# The tables, from the repository root (pure Python, no QGIS).
python3 tools/bench/bench_report.py docs/performance/raw              # section 4
python3 tools/bench/bench_report.py docs/performance/raw --summary    # the summary
python3 tools/bench/bench_report.py /tmp/bench/out                    # the same tables from your own runs

# The memory-layer script, from the root of a whole tree whose fiberq/ it measures.
IMG340=qgis/qgis@sha256:d664f1eca1ef4f615efd92b944c90896622bc75f0446357dc50c2e56b379ddd9   # qgis/qgis:3.40
IMG42=qgis/qgis@sha256:56c69c92e316aa679e5c30ebf7fcfd89fd1124ec728106ec0cced1c71a28d877    # qgis/qgis:4.2-trixie
mkdir -p /tmp/bench/mem/v150/tools/bench /tmp/bench/mem/v160
git archive v1.5.0 | tar -x -C /tmp/bench/mem/v150
git archive v1.6.0 | tar -x -C /tmp/bench/mem/v160
cp tools/bench/test_snap_memory_scaling.py /tmp/bench/mem/v150/tools/bench/
python3 -m pip install --target /tmp/bench/pp pytest==9.1.1 pytest-qgis==4.1.1    # as in the session
docker run --rm --user "$(id -u):$(id -g)" --cpuset-cpus 2-6 --network none \
  -v /tmp/bench/mem/v150:/src -v /tmp/bench/pp:/pp -w /src \
  -e PYTHONPATH=/pp -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e QT_QPA_PLATFORM=offscreen \
  $IMG340 python3 -m pytest -p no:cacheprovider -q -s tools/bench/test_snap_memory_scaling.py \
  > /tmp/bench/qgis340-v150-a1.txt 2>&1
# Then the same with /tmp/bench/mem/v160, and both again on $IMG42 with
# PYTHONPATH=/pp:/usr/share/qgis/python, naming each output as raw/README.md does. The tree is mounted
# writable because pytest-qgis keeps its QGIS settings inside it.
```

The raw files, how to read them and the session's exact order: [`raw/README.md`](performance/raw/README.md).
The harness's own documentation, with every fairness rule and why it exists:
[`tools/bench/README.md`](../tools/bench/README.md). Its "Reproducing a run" is a generic example (two CPUs,
a dated output name, nothing pinned); the commands above follow the published session. The 1.6.0 re-check,
replayed in QGIS 4.2 and 3.40 on the same release tree: [`qa/1.6.0/README.md`](qa/1.6.0/README.md).

---

*The spatial indexing and batching measured here, and this benchmark, were developed with support from the
[NLnet](https://nlnet.nl) NGI0 Commons Fund. The changes this page marks as unclaimed were not funded by
it.*
