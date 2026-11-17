# FiberQ's tests

FiberQ's test suite is in `tests/`: 114 test files and 2,315 tests, run by pytest with the shared fixtures
of the root [`conftest.py`](../conftest.py). The pipeline in [`ci/`](../ci/README.md) runs it in the
official QGIS images, from QGIS 3.22 to 4.2, and runs the part that needs no QGIS on its own, in a plain
Python image. This page says what each tier of tests runs and how to run it, what "core logic" means here,
how coverage is measured, the code the tests share, and the rules for flaky tests, temporary folders,
platforms and test data.

WP5, named below, is the work package "Automated tests and CI" of FiberQ's NLnet NGI0 Commons Fund
grant.

The tools are pinned with their hashes in `ci/requirements-test.txt` (pytest 9.1.1, pytest-qgis 4.1.1,
coverage 7.16.2), and every test stage runs them from the pipeline's tool cache
([ci/README.md](../ci/README.md)).

## The tiers, and how to run each

| Tier | Stage | Runs in | What it runs | Time here |
|---|---|---|---|---|
| Fast | `pure` | the python image, with no QGIS | the 36 test files that import with no QGIS, GDAL or Qt: 512 of their tests run, and the 361 that do not stop on QGIS or GDAL are its pure items (360 of them pass in the python image, which has no `lrelease`) | under a minute |
| QGIS legs | `test-322`, `test-340`, `test-344`, `test-40`, `test-42` | the QGIS 3.22, 3.40, 3.44, 4.0 and 4.2 images | the whole suite, the fast tests included: 2,315 tests on each leg | 7 to 24 minutes per leg, two legs at a time |
| Coverage | `test-coverage` | the QGIS 4.2 image, in host mode only | the whole suite under coverage.py, child processes included | about 17 minutes, on its own |
| Gates | `lint`, `qt6`, `floor` | the python image, the Qt6 checker, the QGIS 3.22 image | static checks, the Qt6 source check and the declared minimum QGIS ([ci/README.md](../ci/README.md)) | seconds each |

The times were measured on one Linux machine with Docker. Every stage starts through `ci/run-all.sh`;
in host mode, the default, each test stage runs in a fresh container with no network. `sh ci/pull.sh
<stage>` fetches a stage's image once; it is the only step that pulls.

### The fast stage

The fast stage runs every test that can run with neither QGIS nor GDAL installed, and picks them itself:
there is no list of files to keep. `ci/test.sh` starts pytest over the whole of `tests/` with
`FIBERQ_PURE=1`, which switches on a block at the end of `conftest.py`; without that variable the block
does nothing, and the QGIS legs collect the same tests as before. With it:

1. `qgis`, `PyQt5`, `PyQt6`, `sip` and GDAL's `osgeo` cannot be imported, whether they are installed or
   not, in the pytest process and in every Python child process that inherits its environment: the stage
   puts a `sitecustomize.py` first on `PYTHONPATH`. A child started with `-I`, `-E` or `-S`, or with
   `PYTHONPATH` taken out of its environment, gets no hider, so tests start their children with
   `sys.executable` and `dict(os.environ, ...)`. So the stage runs the same tests on a machine with QGIS
   and GDAL as in the python image.
2. The packages `fiberq.core`, `fiberq.utils` and `fiberq.models` load without their `__init__.py`, which
   imports the QGIS managers: `from fiberq.core import gpkg_target` runs `gpkg_target.py` and nothing else.
3. A test file is picked when it imports. A file whose import stops on one of the hidden modules is left
   out, with that reason. Any other import error stays an error, and the stage fails. A file that skips
   itself as a whole is left out when the skip is `pytest.importorskip` of a hidden module or is raised
   in the `except` block that caught a hidden module's `ImportError` itself (not in an `except` nested in
   it); any other whole-file skip is an error
   too, also one that a flag set in such an `except` triggers later, since its tests would count where it
   runs and not where it skips.
4. A test that asks for a pytest-qgis fixture (`qgis_app`, `qgis_iface` and the other `qgis_*` fixtures) or
   carries the `qgis` marker is deselected: pytest-qgis is not loaded in this stage, and neither is any other
   pytest plugin installed in the environment.
5. The stage turns a test's failure into a skip only when a hidden module caused it: the exception the
   test ends with is that module's `ModuleNotFoundError`, or a child process the test started dies of one,
   uncaught. An `xfail` that such an error ended, and a skip or an `xfail` called while handling one,
   become the same skip, whatever their reason. Its reason starts `pure stage:` (or, when the test itself
   asks with `pytest.importorskip`, it ends `(hidden in the pure stage)`, also after a reason of the
   test's own). Any other failure fails the stage, also one raised while a test or a child process
   handles a hidden module's `ImportError`, so code that runs only when QGIS is missing fails here like
   any other code, unless it stops on a hidden module itself.

The stage then counts its **pure items**: the tests it ran, less the ones it skipped because a hidden module
stopped them. It counts them per test file, and `ci/pure-count` pins each file's number, one line per test
file with at least one pure item (`14 tests/test_schema.py`). The stage fails when a file's count differs
from its line, or a file has pure items and no line, and names each such file. Fewer usually means that a
test file stopped importing without QGIS, that a test was removed or renamed, or that a test now needs QGIS;
more means that new tests run without QGIS, and their file's line is set to the new count in the same change.
The count is per file, not per test: a test that starts to need QGIS in the same change that adds a pure
test to its file leaves the count as it was; `pure_skips` in `result.txt` then rises, and
`sh ci/compare.sh --stages pure <run before> <run after>` names the test as lost.

**The total in `ci/pure-count` may only rise:** a change that lowers it, such as one that removes tests on
purpose, needs the maintainer's explicit approval in its pull request; without that approval, a line falls
only when the same change moves those tests to another file. The stage compares each file with its line in
the tree it tests, never with an earlier commit, so this rule is kept in review, where every change to
`ci/pure-count` shows in the pull request's diff.

A test that skips for any other reason, such as a missing `lrelease`, still counts. So that the counts are
the same wherever the stage runs, a test that needs QGIS or GDAL stops on it first: its import, or
`pytest.importorskip`, comes before any skip that depends on the machine (a tool on `PATH`, root, the
platform).

The stage's record holds the counts in `result.txt` (`files`, `files_left_out`, `deselected`, `pure_skips`,
`pure_items`, `pure_files`, `pure_count`, `pure_count_files`, `pure_differ`) and, in `pure-files.tsv`, every
test file picked or left out, with the reason, and every test deselected.

```sh
sh ci/pull.sh pure                               # once: the python image, about 0.2 GB
sh ci/run-all.sh --only pure                     # in a container: python 3.13, no QGIS, no network
CI_IN_PLACE=1 sh ci/run-all.sh --only pure       # here, with python3 3.11 or later
```

In place, the first run installs the pinned test tools into `.ci-cache/` with pip, which needs the
network; QGIS and GDAL stay hidden there as well.

By hand, from the repository root, after `make deps` (with a new folder for `--basetemp`, see
[Temporary folders](#temporary-folders)); this runs the tests and the picking, not the per-file check:

```sh
FIBERQ_PURE=1 python3 -m pytest -p no:pytest_qgis --disable-plugin-autoload -p no:cacheprovider --basetemp=/tmp/fiberq-fast-1
```

A new test file that needs no QGIS is picked automatically if it keeps these rules, and its line goes into
`ci/pure-count` in the same change:

- no `qgis`, `PyQt5`, `PyQt6`, `sip` or `osgeo` import at the top of the file;
- FiberQ code imported from its modules (`from fiberq.core.gpkg_target import X`, or
  `from fiberq.core import gpkg_target`), never a name that only a package's `__init__.py` defines
  (`from fiberq.core import CableManager`), because this stage skips those `__init__.py` files;
- the file skips itself as a whole only for a hidden module, in a form the stage sees: `qgis` imported at
  the top, `pytest.importorskip("qgis")`, or the skip inside the `except` block of its `qgis` import (not
  after that block, behind a flag); for any other reason it skips inside its tests (`pytest.mark.skipif`);
- a test that needs QGIS or GDAL while it runs imports it, or calls `pytest.importorskip`, before any skip
  that depends on the machine; a skip in the test's own words after a helper caught the `ImportError` and
  returned `None` still counts as a pure item;
- a skip raised in the `except` block of a hidden module's `ImportError` itself (not in an `except` nested
  in it), in a test or at the top of a file, is taken as that module's, whatever it says, so a skip there
  must never depend on the machine (a tool on `PATH`, root, the platform): such a skip goes after the
  `except` block, inside the test;
- a test that needs QGIS or GDAL names `qgis` or `osgeo` itself in that import, `pytest.importorskip` or
  `except`, never a package installed only beside them whose modules import them, such as GDAL's
  `osgeo_utils`: on a machine with GDAL its import stops on the hidden `osgeo` and the test is the stage's
  own skip, while in the python image it is missing and the skip counts.

A test file that needs QGIS imports `qgis` before any `fiberq` package name, as PEP 8 orders third-party
imports before the project's own; it is then left out here and runs on the five legs.

### The QGIS legs

Each leg runs the whole suite in the official image of its QGIS version, pinned by its digest in
`ci/legs`: 3.22 (the declared minimum), 3.40, 3.44, 4.0 and 4.2. GitHub runs the legs 3.22, 3.44 and 4.2 on
every push, and all five on release branches and tags; GitLab runs the 4.2 leg for `main`, release branches
and tags.

```sh
sh ci/pull.sh 344 42                             # once: the QGIS 3.44 and 4.2 images
sh ci/run-all.sh --only 344,42                   # the whole suite on QGIS 3 (Qt5) and QGIS 4 (Qt6)
sh ci/run-all.sh --only 322,340,344,40,42 --jobs 2
PYTHONPATH=/usr/share/qgis/python make test      # here, on the QGIS that python3 imports (test-local)
```

Inside a leg, the tests are of a few kinds, told apart by what they build rather than by a marker:

- tests on in-memory layers, with QGIS but no files;
- tests that open the canvas, a dialog or a stand-in for QGIS's `iface`;
- tests on real GeoPackages, projects and exported files, written to temporary folders;
- tests that start QGIS, or the plugin's `initGui` and `unload`, in a child Python process, so that a
  crash fails one test and not the whole run;
- the fast tests above, which run on every leg as well.

A test that cannot run on a leg skips, with its reason in the leg's record: for example, the benchmark
city's fixture needs QGIS 3.36 or later, and the Excel export needs `xlsxwriter`, which no image has.

### Coverage

The `test-coverage` stage runs test-42's suite under coverage.py in the QGIS 4.2 image, and writes the
statement coverage of each core-logic module. Its settings are `ci/coverage.ini`, the only configuration it
reads, so every commit is measured the same way, older ones through `--ref` too. It runs in host mode only:
in place it is skipped, because the statements are counted with the 4.2 image's Python. It is measured, not
gated: it fails only when a test fails, when the report cannot be written, or when no child process was
measured or its data files cannot be counted. It is in no set, so no forge runs it.

```sh
sh ci/pull.sh test-coverage                      # once: the QGIS 4.2 image
sh ci/run-all.sh --only test-coverage            # the working tree
sh ci/run-all.sh --only test-coverage --ref v1.6.0
```

The stage's record holds `coverage.json` (every file of `fiberq/`, line by line), `coverage-core.tsv` and
`coverage-core.md` (the table below, for one commit), and in `result.txt` the totals, the number of
coverage data files and the number of processes that measured anything. `make test-cov` is a quick look at
the current Python, with the tree's own settings and without child processes; its figures differ, and the
stage is the reference.

## Core logic

Core logic is the 50 modules of `fiberq/core/`, `fiberq/utils/` and `fiberq/models/`, without the
packages' `__init__.py` files: 29,277 lines at v1.6.0, blank lines and comments included. These are the
managers, their helpers, and the schema. This command counts their lines on any checkout (29277 on
v1.6.0):

```sh
git ls-files 'fiberq/core/*.py' 'fiberq/utils/*.py' 'fiberq/models/*.py' | grep -v '/__init__\.py$' | xargs cat | wc -l
```

WP5's tests target **core logic and the plugin entry points it runs through**: `initGui`, `unload` and the
toolbar actions.

WP5 adds no tests for two groups of modules:

- **Dead code:** `core/config_manager`, `utils/layer_names` and `models/color_catalogs`, 1,083 lines that
  nothing calls. Only their packages' `__init__.py` files import them.
- **The two Pro features and their licence check:** `core/license_manager` (the licence check),
  `addons/publish_pg` (Publish to PostGIS) and `addons/fiberq_preview` (Preview Map). Earlier work tests
  `addons/publish_pg` (`tests/test_publish_pg.py`), and those tests stay.

Importing the three packages still runs the import-time statements of the dead modules and of
`core/license_manager`, so their coverage is not zero. The table lists them, marked, and leaves them out of
the in-scope total.

## WP5's test files

| File | Item | Kind | Tests | Pure items |
|---|---|---|---|---|
| `tests/test_floor_seed.py`, with `tests/floor_check.py` and `tests/floor_seed/` | the seeds of the floor gate, in v1.6.0 already | checks the seed files as text | 7 | 7 |
| `tests/test_qt6_seed.py`, with `tests/qt6_seed/` | the seeds of the Qt6 check, in v1.6.0 already | checks the seed files as text | 3 | 3 |
| added since v1.6.0 | none yet | | | |

## The fast-stage count

Measured with the tests of the commit that added this page:

| | Python image, uid 1000 (host mode) | Python image, root (GitLab, in place) | A machine with QGIS, GDAL and lrelease (in place) |
|---|--:|--:|--:|
| test files picked | 36 | 36 | 36 |
| test files left out | 78 | 78 | 78 |
| tests collected | 539 | 539 | 539 |
| tests deselected (a pytest-qgis fixture) | 27 | 27 | 27 |
| tests run | 512 | 512 | 512 |
| skipped by the stage (a hidden module stopped them) | 151 | 151 | 151 |
| **pure items** (in 27 test files) | **361** | **361** | **361** |
| of which passed | 360 | 359 | 361 |
| of which skipped for another reason | 1 (no lrelease) | 2 (no lrelease; root ignores the write bit) | 0 |

`ci/pure-count` holds the 361 pure items, file by file. Of them, **10** come from WP5's test files:
`tests/test_floor_seed.py` (7) and `tests/test_qt6_seed.py` (3), which v1.6.0 already has; none yet from
test files added since. The other **351** come from earlier work. In the python image 360 of the 361
pass, and one skips because the image has no `lrelease` (as root, one more skips). The 151 tests the
stage skips run on the five QGIS legs: 88 of them need GDAL's Python bindings (`osgeo`), and 63 import
QGIS while they run, 32 of them in a child process.

## Coverage of core logic

Statement coverage per core-logic module, as coverage.py 7.16.2 counts statements (12,093 in core logic at
v1.6.0), measured by the `test-coverage` stage on the QGIS 4.2 leg (Python 3.13), in host mode. The three
columns are measured in one go, with one checkout of `ci/`, one image digest and one set of tool pins; each
column's run record names the `ci/` tree it ran.

- **v1.6.0**: before the test files WP5 adds. Its only WP5 test files, the two seed tests above, read text
  files and run no `fiberq/` code, so they add nothing to this table;
- **v1.7.0 without WP5's test files**: the measured commit with every path listed under
  [WP5's test files](#wp5s-test-files) removed, the two seed tests and their seed folders too;
- **v1.7.0**: the whole suite of the measured commit. WP5's share is the difference between the last two
  columns, in percentage points.

On the commit measured for v1.7.0, in a clean clone:

```sh
sh ci/run-all.sh --only test-coverage --ref v1.6.0    # v1.6.0
sh ci/run-all.sh --only test-coverage                 # v1.7.0
git switch -c coverage-without-wp5                    # a throwaway branch
git rm -rq tests/test_floor_seed.py tests/floor_check.py tests/floor_seed \
    tests/test_qt6_seed.py tests/qt6_seed             # and every other path under WP5's test files
git commit -qm 'coverage: without WP5 test files'
sh ci/run-all.sh --only test-coverage                 # v1.7.0 without WP5's test files
```

The files are removed, not deselected: pytest still imports a deselected file, and the statements that run
when it is imported would count. That run's record names its trees: its `fiberq/` tree is the measured
commit's, and its `tests/` tree is the one these commands give on any clone. The v1.6.0 column below was
measured when this page was added, and it is measured again with the two v1.7.0 columns, which are measured
when WP5's test files are complete, before the v1.7.0 release.

What the figures include, and what they do not:

- Measured: the whole suite on the QGIS 4.2 leg, the fast tests included, and every Python child process
  the tests start that runs this tree's `fiberq/` (the QGIS drivers that run `initGui` and `unload`, and the
  logger loaded without QGIS).
- Not measured: the other four legs, so code that runs only on Qt5 or on QGIS 3 (for example the fallbacks
  in `utils/compat.py`) counts as not run; the fast stage on its own, so code that runs only when QGIS is
  missing counts only where a test runs it in a child process on the 4.2 leg; code that a child process runs
  from a copy of the plugin (the mapping generator's test copies three core modules into a temporary folder,
  and one language test copies `fiberq/`); a child process that is killed or crashes, which leaves no data.

Each column's percentage is over the statements of the commit it measures.

| Module | Statements at v1.6.0 | v1.6.0 | Statements at v1.7.0 | v1.7.0 without WP5's test files | v1.7.0 | WP5's share |
|---|--:|--:|--:|--:|--:|--:|
| `core/cable_manager.py` | 614 | 71.0% | | | | |
| `core/color_manager.py` | 102 | 30.4% | | | | |
| `core/config_manager.py` (dead code) | 169 | 43.8% | | | | |
| `core/data_manager.py` | 278 | 69.8% | | | | |
| `core/drawing_manager.py` | 171 | 23.4% | | | | |
| `core/export_manager.py` | 628 | 83.0% | | | | |
| `core/feature_links.py` | 88 | 98.9% | | | | |
| `core/gpkg_target.py` | 355 | 94.9% | | | | |
| `core/interchange.py` | 195 | 91.3% | | | | |
| `core/interchange_bundle.py` | 1,061 | 89.5% | | | | |
| `core/interchange_fields.py` | 78 | 100.0% | | | | |
| `core/interchange_import.py` | 751 | 91.7% | | | | |
| `core/layer_manager.py` | 909 | 27.2% | | | | |
| `core/length_manager.py` | 222 | 82.0% | | | | |
| `core/length_sync.py` | 187 | 81.8% | | | | |
| `core/license_manager.py` (licence check of the Pro features) | 57 | 31.6% | | | | |
| `core/migrations.py` | 102 | 86.3% | | | | |
| `core/pipe_manager.py` | 247 | 37.7% | | | | |
| `core/project_compat.py` | 8 | 100.0% | | | | |
| `core/project_store.py` | 69 | 89.9% | | | | |
| `core/relations_manager.py` | 179 | 27.4% | | | | |
| `core/route_ends.py` | 156 | 92.3% | | | | |
| `core/route_manager.py` | 529 | 84.5% | | | | |
| `core/schema_version.py` | 44 | 84.1% | | | | |
| `core/slack_manager.py` | 432 | 80.8% | | | | |
| `core/style_manager.py` | 404 | 43.1% | | | | |
| `core/undo_manager.py` | 323 | 81.1% | | | | |
| `core/validation_manager.py` | 200 | 98.0% | | | | |
| `core/validation_report.py` | 125 | 93.6% | | | | |
| `core/validation_rules.py` | 484 | 93.2% | | | | |
| `models/color_catalogs.py` (dead code) | 130 | 27.7% | | | | |
| `models/element_defs.py` | 84 | 60.7% | | | | |
| `models/schema.py` | 99 | 99.0% | | | | |
| `utils/batch.py` | 17 | 94.1% | | | | |
| `utils/compat.py` | 240 | 44.6% | | | | |
| `utils/constants.py` | 102 | 100.0% | | | | |
| `utils/errors.py` | 187 | 92.5% | | | | |
| `utils/field_aliases.py` | 217 | 81.6% | | | | |
| `utils/file_filters.py` | 11 | 100.0% | | | | |
| `utils/geometry.py` | 318 | 67.6% | | | | |
| `utils/geopackage.py` | 151 | 88.1% | | | | |
| `utils/helpers.py` | 253 | 21.3% | | | | |
| `utils/image_watcher.py` | 38 | 97.4% | | | | |
| `utils/layer_names.py` (dead code) | 97 | 88.7% | | | | |
| `utils/legacy_bridge.py` | 231 | 59.7% | | | | |
| `utils/logger.py` | 80 | 57.5% | | | | |
| `utils/measure.py` | 107 | 77.6% | | | | |
| `utils/routing.py` | 205 | 49.3% | | | | |
| `utils/spatial.py` | 188 | 98.9% | | | | |
| `utils/uuid_utils.py` | 171 | 76.0% | | | | |
| **In scope (46 modules)** | **11,640** | **72.7%** | | | | |
| **Core logic (50 modules)** | **12,093** | **71.7%** | | | | |

## Code the tests share

`tests/support/` holds code for tests to share, and no tests of its own:

- `child.py`: `run_driver()` runs a driver script in a child Python with `sys.executable` and
  `dict(os.environ, ...)`, as the fast stage asks, offscreen, in the folder it is given (also its `TMPDIR`)
  and with a time limit. It returns the child's exit code, the JSON of its last `RESULT` line (None if there
  is none, or if it is not JSON) and its output. It imports only the standard library.
- `fake_iface.py`: `FakeIface`, a stand-in for QGIS's `iface` with what the plugin's `initGui` and `unload`
  use: a real main window and map canvas, toolbars that belong to that window, and the actions added to
  Plugins > FiberQ, in order (nothing takes them out). Anything else asked of it is a `MagicMock`. It
  imports QGIS.
- `toolbar_driver.py`: a driver that builds the plugin's toolbars with `FakeIface` and prints each toolbar,
  drop-down and Plugins > FiberQ entry with what its icon draws, for `tests/test_toolbar_icons.py`.

`pyproject.toml` puts `tests/` on pytest's `sys.path`, so a test file imports the runner with
`from support.child import run_driver`, in any import mode. A driver that uses `FakeIface` puts the repository
root and `tests/` on its own `sys.path`, and imports `support.fake_iface` once it has started a
`QgsApplication`. What a test file imports at its top must import without QGIS, or the fast stage leaves the
file out: `child.py` does, `fake_iface.py` does not. A test asserts the child's exit code and result before it
reads the result, with the child's output in that assertion's message
(`assert code == 0 and result is not None, output`), as both test files do: the fast stage turns a child that
died of a hidden module into a skip only when that output is in the failure. Python puts a script's folder
first on `sys.path`, and `toolbar_driver.py` runs from `tests/support/`, so no module there may be named like
a standard-library, QGIS or installed module.

## Flaky tests

A test that fails at random is marked `xfail(strict=False)`, with a reason that names the flaky behaviour
and the follow-up that tracks it, or moved into a child process of its own. Failed tests are never re-run
automatically. A failed run on a push is re-run once by hand; a re-run on the release commit is noted in
that release's run record (`docs/ci/<version>.md`; [RELEASE.md](../RELEASE.md), step 9).

## Temporary folders

Every test stage runs pytest with `-p no:cacheprovider` and a new `--basetemp` and `TMPDIR`: inside the
container in host mode, and under `ci-results/<run>/stages/<stage>/work/` in place. When you run pytest by
hand, give `--basetemp` a folder that does not exist yet: pytest deletes the folder it is given if it
exists.

## Platforms

The pipeline's runs on the forges and in the release record are on Linux only. The stages run in
`linux/amd64` containers pinned by digest in `ci/legs` (the official qgis/qgis images, QGIS's Qt6 checker
image and python 3.13-slim); the package stage also runs steps on the Linux host, and release-check runs
there. In place (`make test`, `CI_IN_PLACE=1`) the suite runs on whatever system runs it; no Windows or
macOS run is part of the pipeline or its records. Before a release, the zip is installed by hand in QGIS,
on Windows too when a Windows machine is at hand ([RELEASE.md](../RELEASE.md), step 4).

## Test data

Every dataset the tests use is synthetic and comes from this repository: the generators in
`tests/fixtures/` build them during the run, tests build small layers and tables in their own code, and the
demo project and bundles in `docs/samples/` are written by `docs/samples/generate.py`. No test downloads
anything, and in host mode the stage containers have no network. The suite uses no third-party data. The
other files the tests read are the repository's own: the plugin's styles, icons, translation catalogues and
`metadata.txt`, its source code, and the documents that some tests check against the code.

---

*The fast stage, the coverage measurement and this page were developed with support from the
[NLnet](https://nlnet.nl) NGI0 Commons Fund, as part of WP5.*
