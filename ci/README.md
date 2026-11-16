# The FiberQ pipeline

`ci/` holds FiberQ's whole test and release pipeline: POSIX `sh` scripts and two Python helpers,
`report.py` and `zipcheck.py`. It needs no forge and no account: anyone with git, tar and docker or
podman runs it with one command. GitHub Actions and GitLab CI only call these scripts
([On a forge, or with no forge](#on-a-forge-or-with-no-forge)).

## Start

```sh
git clone https://gitlab.com/vukovicvl/fiberq.git      # or https://github.com/vukovicvl/fiberq.git
cd fiberq
sh ci/pull.sh --quick       # once: the images of the quick set, about 7.4 GB; the only step that pulls
sh ci/run-all.sh --quick    # the one command: pure, lint, qt6, floor and package
```

A run that completes prints the path of its folder in `ci-results/` and its summary up to the slowest
tests, then ends with `run-all.sh: PASS` (exit 0) or `run-all.sh: FAIL` (exit 1).

## What the host needs

Git, tar, and docker or podman (`CI_ENGINE=podman`); besides those, the scripts use only standard
shell tools (`sed`, `grep`, `cmp`, `cksum` and the like). Every image runs as `linux/amd64`, pinned by
its digest in `ci/legs`.

- Linux x86-64: tested, with Docker 29.9.3, and with Podman 5.7.0 for the pure and lint stages.
- Windows, through WSL2, or Git Bash with Docker Desktop: not tested yet.
- An Intel Mac with Docker Desktop: not tested yet.
- Apple Silicon only under amd64 emulation, and slowly: not tested.

The pipeline starts every container with `--init`. Under Podman that needs an init binary: catatonit
(on Debian and Ubuntu, `apt install catatonit`; the podman package only recommends it), or an
`init_path` in `containers.conf`. Without one, podman cannot start the stage containers. Tested with
catatonit 0.2.1.

## Stages and sets

| Stage | Runs in | What it checks |
|---|---|---|
| `pure` | the python image | the test files listed in `ci/pure-tests.txt`, which run with no QGIS installed (in the python image, those that need GDAL or lrelease skip) |
| `lint` | the python image | flake8 (on `fiberq/`, `tests/`, `conftest.py` and `tools/bench`) and Bandit (on `fiberq/`, every severity) with the flags of plugins.qgis.org's scan, detect-secrets on `fiberq/` as that scan runs it, shellcheck on `ci/*.sh` and `ci/hooks/`, flake8 on the Python files of `ci/`, the `.ts` placeholder check, and the forge configs ([below](#what-the-lint-stage-checks-in-the-forge-configs)) |
| `qt6` | the Qt6 checker image | QGIS's `pyqt5_to_pyqt6.py`, as plugins.qgis.org runs it for its Qt6 Check tab: 0 findings in `fiberq/`, where the checker must also succeed, and at least 4 in `tests/qt6_seed/`, so a checker that stops reporting fails |
| `floor` | the QGIS 3.22 image | every `fiberq/` module parses and imports on QGIS 3.22, which must be `qgisMinimumVersion` |
| `package` | the host's git, then the python image | the reproducible zip, with its `.sha256` and `.contents.tsv` ([Results](#results-and-pruning-by-hand)) |
| `test-322`, `test-340`, `test-344`, `test-40`, `test-42` | the image of that QGIS version | the whole test suite |
| `release-check` | the host | `fiberq/config.ini` holds no user or password, and both READMEs have their "Use of Generative AI" heading; it also lists, for review, the commits since the last tag without an `Assisted-by:` trailer |
| `test-local` | in place only | the whole test suite on the QGIS that `python3` imports here |

| Set | Stages | Images to pull | Time here |
|---|---|---|---|
| `--hook` | pure, lint, package | the python image, about 0.2 GB | about a minute |
| `--quick` | the hook set, qt6, floor | about 7.4 GB | under two minutes |
| default | the quick set, test-322, test-344, test-42 | about 28 GB | 43 minutes, one leg at a time |
| `--release` | the default set, test-340, test-40, release-check | about 36 GB | 52 minutes with `--jobs 2` |

The times were measured on one Linux machine with Docker, with the images already pulled. The sizes are
what the images take on disk, counted one by one; they share some layers. A stage can be skipped: qt6
when its image is missing, and the in-place skips below. A skipped stage passes the run, except under
`--release` or `--strict`, where it fails the run.

The package stage builds the zip on the host with `TZ=UTC git archive --format=zip` of `fiberq/` at the
last commit that changed it, so it holds committed files only, under one `fiberq/` folder, and the same
commit gives the same bytes with the same git and zlib. Across machines, compare the `.contents.tsv`
files (the path, mode and sha256 of each file). The stage warns when a `.qm` catalog is not committed,
or was last committed before its `.ts`. That warning compares commit times only, so a `.ts` change that
touches no finished translation (new unfinished strings, for example) warns too, although compiling
would give the same `.qm`.

## Commands and options

```
sh ci/run-all.sh [--hook|--quick|--release] [--only <stage,...>] [--jobs N] [--ref <commit>] [--offline] [--strict]
```

- `--only <stage,...>`: exactly these stages, under the rules of the set flag given with it. A bare leg
  name means its test stage: `--only 42` is `--only test-42`.
- `--ref <commit>`: test that commit's tree instead of the working tree. The scripts still come from the
  working tree, so an older commit, even v1.6.0, which has no `ci/`, can be tested. A `--ref` run never
  copies into `dist/`.
- `--jobs N`: run the test legs in N lanes (default 1).
- `--offline`: never fetch pinned tools; a stage whose tools are not cached fails.
- `--strict`: a skipped stage fails the run, as under `--release`, without `--release`'s refusals; it
  works in place too, and the GitLab jobs use it. A test that pytest skips is not a skipped stage.
- `--release` refuses a dirty working tree (also with `--ref`) and a shallow clone, and runs nothing.

Without `--ref`, the tested tree is the working tree as it is: the tracked files and the new files git
does not ignore, marked dirty in the record when that differs from `HEAD`.

| Variable | Meaning |
|---|---|
| `CI_ENGINE` | `docker` (the default) or `podman` |
| `CI_IN_PLACE=1` | run the stages here, with no container ([Host mode and in-place mode](#host-mode-and-in-place-mode)) |
| `CI_RESULTS`, `CI_CACHE` | where the run folders and the pinned tools go (default `ci-results/` and `.ci-cache/`) |
| `CI_TIMEOUT` | a time limit in seconds for every stage of the run (each stage has its own by default) |
| `CI_IMAGE_<ROLE>` | another image for one role, for one run, as `<registry>/<repository>@sha256:<digest>`; the record marks it, and `ci/tag.sh` never accepts such a run |

The other scripts:

- `sh ci/pull.sh [--hook|--quick|--release|<stage>...]` pulls the images those stages need, and the
  python image for the summary, by their digests in `ci/legs`. `sh ci/pull.sh --bump <role>` (docker
  only) resolves a role's tag to its current digest, pulls it, and prints the new line for `ci/legs`; it
  edits nothing.
- `sh ci/deps.sh [--hook|--quick|--release|<stage>...]` fetches the pinned tools; `run-all.sh` does it
  itself, before the first stage, for the tools that are not cached.
- `sh ci/compare.sh [--stages <stage,...>] <old run> <new run>` lists every test that passed in the old
  run and does not pass in the new one. It is strict by default: an old stage that the new run lacks
  loses all its passes.
- `sh ci/lock.sh` regenerates `ci/requirements-test.txt` and `ci/requirements-lint.txt` (network) into a
  new folder in `ci-results/` and prints the `cp` commands that take them over; it never writes into
  `ci/`.
- `sh ci/release-check.sh` runs the release check on the working tree.
- `sh ci/tag.sh` creates the annotated tag `v<version>` ([RELEASE.md](../RELEASE.md), step 5).

A stage script started by hand prints the `run-all.sh` command to use, and exits 2.

## Exit codes

| Command | 0 | 1 | 2 | Other |
|---|---|---|---|---|
| `run-all.sh` | every stage passed (a skip too, except under `--release` or `--strict`) and the summary passed | a stage failed or has no verdict, or the summary failed | a usage error, a refusal, or an engine, git or input that cannot be used | 130: interrupted |
| `pull.sh`, `deps.sh` | all done | an item failed (the others still ran) | a usage error or the environment | |
| `lock.sh` | done | the lock failed | a usage error or the environment | |
| `release-check.sh` | the checks pass | a check failed | a usage error or the environment | |
| `tag.sh` | the tag was created | refused | a usage error or the environment (a shallow clone, no git) | |
| `compare.sh` | no test lost | a test lost, or a compared stage missing in the new run | a usage error, a run folder it cannot read, or nothing to compare | |
| `make <target>` | the command passed | | the command failed, whatever its own code (make's rule) | |
| `ci/hooks/pre-push` | every commit it tested passed, or there was nothing to test | a stage failed on a pushed commit | started by hand from a terminal, or a run refused or could not start (an engine that is down, a usage error) | 130: interrupted |

git refuses the push whenever the hook exits with anything but 0.

## Results, and pruning by hand

Each run writes a new folder, `ci-results/<UTC time>-<commit12>/` (`-2`, `-3` on a clash):

- `run.txt`: the facts of the run (the commit, the trees, the images, the engine, the mode), written
  before the first stage;
- `<stage>.log`, `stages/<stage>/status` (the verdict) and `stages/<stage>/out/` (what the stage wrote:
  `result.txt`, and `junit.xml` from pure and the test legs);
- `summary.md` (for people) and `record.txt` (for `tag.sh`), only when the summary stage passed; an
  interrupted run has neither;
- `input/`: the snapshot of the working tree, when git is there, and what the stages read (in host mode,
  the input streams of the containers);
- `deps/`: the records of the pinned tools fetched during the run;
- in host mode also `package/` (the zip, its `.sha256` and its `.contents.tsv`) and `raw/` (the results
  tars).

The pinned tools are cached in `.ci-cache/deps/`, one folder per image digest (in place, per Python
version), tool set, lock file and `ci/deps.sh`; a folder without its `complete` file is never used. The
package stage copies its three files into `dist/` only from a run without `--ref` whose `fiberq/` has no
uncommitted change, and only when `dist/` holds none of them. Under `--release`, another build of that
version in `dist/` fails the stage.

The scripts never delete or overwrite anything in those folders: prune them by hand. Delete old run
folders when you no longer need them (keep a release run until its record is in `docs/ci/`, step 9 of
[RELEASE.md](../RELEASE.md)), cache folders (the next run fetches what is missing) and old builds in
`dist/`. A host-mode run folder takes about 30 MB, mostly the tested tree as a tar. A run that fetched
pinned tools also keeps two copies of each tool tar in `deps/`, about 16 MB per test set and 60 MB for
the lint set: with nothing cached, about 75 MB more for the hook or quick set, 125 MB for the default
set and 157 MB for the release set. A cache folder takes 8 to 31 MB.

## Host mode and in-place mode

Host mode is the default, and its record is the reference. `CI_IN_PLACE=1 sh ci/run-all.sh --only
<stages>` runs the same stage scripts in the current environment instead: a CI job that already runs in
the right image (GitLab, below), or a machine with QGIS installed (`make lint`, `make test`).

| | Host mode | In place |
|---|---|---|
| where the stages run | pure, lint, qt6, floor, the test legs and the summary each in a fresh container (`--network none`, uid 1000, `--pull=never`); package builds the zip on the host and checks it in a container; release-check runs on the host | here, with no container; each stage gets its own empty `HOME` in its run folder |
| the tested tree | the working tree, or `--ref <commit>` | the checkout as it is |
| the commit in the record | from git | `CI_COMMIT_SHA`, else from git, else `unknown` |
| network during the tests | none | whatever the environment has |
| user | 1000:1000 | the environment's (root in GitLab's jobs, where a few more tests skip) |
| Python | each image's own | `python3` from `PATH` (3.12 or later for lint), not make's `$(PYTHON)` |
| pinned tools | fetched in a container, cached per image digest | pip-installed into `.ci-cache/deps/local-py<version>-…` on first use (network) |
| package | runs | skipped |
| qt6 | the checker image; without it, skipped | `pyqt5_to_pyqt6.py` on `PATH`, in `/usr/local/bin` or in `QT6_CHECKER`, else skipped |
| floor and the test legs | each in its image | skipped unless this QGIS is the version the stage needs |
| test-local | refused | the whole suite on this QGIS |
| `--release`, `--ref` | allowed | refused (exit 2) |
| `--strict` | allowed | allowed (the GitLab jobs use it) |
| `--jobs` | lanes | ignored, with a warning |
| files written in the checkout | none outside `ci-results/`, `.ci-cache/` and new files in `dist/` | also `.qgis-settings/` (pytest-qgis) and maybe `symbology-style.db` (headless QGIS), both ignored by git |

## Make targets

| Target | Runs |
|---|---|
| `make lint` | `CI_IN_PLACE=1 sh ci/run-all.sh --only lint` |
| `make test` | `CI_IN_PLACE=1 sh ci/run-all.sh --only test-local`: the whole suite on the QGIS that `python3` imports. The qgis.org packages for Debian and Ubuntu put the bindings in `/usr/share/qgis/python`: `PYTHONPATH=/usr/share/qgis/python make test` |
| `make deps` | pip installs `ci/requirements-test.txt` and `ci/requirements-lint.txt`, hash-locked, into `$(PYTHON)`, with `PIP_FLAGS` (`--break-system-packages` unless you set it empty, as in a virtualenv) |
| `make test-cov` | pytest with `--cov=fiberq` in `$(PYTHON)` itself, outside the pipeline (after `make deps`) |
| `make qt6-check` | `sh ci/pull.sh qt6`, then `sh ci/run-all.sh --only qt6`: when the checker image cannot be pulled it fails, rather than pass with qt6 skipped |
| `make floor-check`, `make package` | `sh ci/run-all.sh --only floor`, `sh ci/run-all.sh --only package` |
| `make ci`, `make ci-quick` | `sh ci/run-all.sh`, `sh ci/run-all.sh --quick` |
| `make ci-release`, `make release` | `sh ci/run-all.sh --release` |
| `make tag` | `sh ci/tag.sh` |

The targets from `make qt6-check` down clear `CI_IN_PLACE`, so they run in host mode even when your
shell exports `CI_IN_PLACE=1`. `make lint` and `make test` use `python3` from `PATH`, not `$(PYTHON)`;
for another interpreter, put its folder first, as in `PATH=/path/to/venv/bin:$PATH make lint`. The lint
tools need Python 3.12 or later. Both install their pinned tools into `.ci-cache/` on first use, so that
first run needs the network. Run them as the owner of the checkout: run as root in a container with the
checkout mounted, they leave root-owned folders in `ci-results/` and `.ci-cache/` that later runs as
your own user cannot write into. Flags reach `run-all.sh` through `CI_ARGS`, for example
`make ci CI_ARGS='--jobs 2'`. make exits 2 whenever the command fails; run the command itself to tell
its 1 from its 2.

## Registries

The QGIS and python images come from Docker Hub. The Qt6 checker, `ghcr.io/qgis/pyqgis4-checker`, the
image plugins.qgis.org itself runs, comes from ghcr.io. Without the checker image the qt6 stage reports
`skipped: needs ghcr.io`, which passes the run except under `--release` or `--strict`; there is no
fallback. `sh ci/pull.sh qt6` fetches the image once, and from then on the stage needs no network.
`make qt6-check` runs that pull first and fails when it cannot.

## On a forge, or with no forge

### GitHub Actions

`.github/workflows/ci.yml` runs one job per stage on GitHub's `ubuntu-26.04` runners. Each job checks
out the commit with full history, runs `exec sh ci/pull.sh <stage>` and `exec sh ci/run-all.sh --only
<stage>`, and uploads the run folder as an artifact named `ci-results-<set>-<stage>-<attempt>`, without
`input/`, `raw/` and the tool tars, also when the stage failed. `exec` makes the script the step's own
process: when a job is cancelled or reaches its time limit, the runner's interrupt reaches
`run-all.sh`, which kills the run's containers and writes `interrupted=yes` into `run.txt` before the
upload runs.

- A push to a branch other than a `release/` branch runs the default set, as the jobs
  `default (<stage>)`.
- A push to a `release/` branch, a push of a tag, and "Run workflow" on a branch or tag run the release
  set (`--release`), as the jobs `release (<stage>)`. These runs are split by stage (`--only`); the tag
  comes from a full run on your own machine ([RELEASE.md](../RELEASE.md), steps 3 and 5).
- A pull request runs the default set only when it comes from a fork. A branch of this repository has
  already run on its push, so its pull_request run shows as skipped.
- A push that deletes a branch or a tag runs nothing.

Each job pulls its images first. When a pull fails (Docker Hub or ghcr.io out of reach, for example),
the job fails at "Pull the stage's images" and the stage does not run. For qt6 this is stricter, on
purpose, than a run on your own machine, which reports the stage as skipped. On GitHub's hosted runners
Docker Hub's rate limit does not apply to public images (GitHub's documentation), so a pull that fails
there is most likely an outage. Re-run the failed jobs once ("Re-run failed jobs"); each attempt that
got as far as a run folder uploads its own artifact, `ci-results-<set>-<stage>-<attempt>`.

### GitLab CI

`.gitlab-ci.yml` runs pure, lint and test-42 in place, each as `CI_IN_PLACE=1 sh ci/run-all.sh --strict
--only <stage>` in the python and QGIS 4.2 images of `ci/legs`, for `main`, `release/` branches and tags
only. `--strict` makes a skipped stage fail its job: in place, a test leg is skipped when the QGIS that
`python3` imports is not its version, and without `--strict` the job would pass having run no test. The
jobs run as root. They need no git: the record takes the commit from `CI_COMMIT_SHA` (the python image
has no git; the QGIS 4.2 image has it). Each run folder, without the stages' `work/` folders, is a job
artifact kept for 90 days.

### What the lint stage checks in the forge configs

In a tree that has `.gitlab-ci.yml` or `ci/hooks/`, the lint stage checks both forge configs
(`wrappers` in its record, "forge configs" in the summary):

- `.gitlab-ci.yml`: every image is the digest that its `# ci/legs: <role>` comment names, and the image
  that `ci/legs` gives the stage of its job; every script is one line,
  `CI_IN_PLACE=1 sh ci/run-all.sh --strict --only <stage>`; no `include`, `services`, `trigger`, `run`,
  `step`, `variables`, `parallel` or `allow_failure`, and no `when:` but `when: always` (a manual job
  waits for someone to start it, and may fail without failing the pipeline; a delayed job starts only
  after its delay; an on_failure job runs only when a job of an earlier stage failed).
- `.github/workflows/`: every `run:` is one line: `exec sh ci/<script>.sh`, then optionally `--release`
  and `--only`, and last `${{ matrix.stage }}`, which is required; every `uses:` is `actions/checkout`
  or `actions/upload-artifact` pinned to a commit; no `container`, `services`, `shell`, `env`,
  `defaults`, `working-directory`, `continue-on-error`, matrix `include` or `exclude`, and no checkout
  input that fetches other code (`repository`, `ref`, `token`, `ssh-key`, `github-server-url`); and the
  two stage lists of `ci.yml` are the default and release sets of `ci/common.sh`, so every stage of
  those sets has its job.
- In both files, no more indented line other than a blank or comment line may follow a `script:`,
  `run:`, `image:` or `uses:` line: YAML would join it to the value, or reject the file. No key may be
  written with a space before its colon, since the rules read `key:` only. Neither file may hold a CR,
  NEL, LS or PS character, which YAML reads as a line break, or a BOM, which libyaml (GitLab's parser)
  skips at the start of a line: the rules see neither.
- A missing `.gitlab-ci.yml` or `.github/workflows/ci.yml` fails the check: retiring a forge takes a
  change to `ci/lint.sh`.

The rules read the files line by line, in the one-line form they are written in, so a command written
another way fails them. They are not a YAML parser: a key spelled in a form they do not read (quoted,
or inside a flow mapping, for example) is not checked, and review has to catch it. Nor do they read
when runs start: the workflow's triggers (`on:`), a job or a step switched off by its `if:` on GitHub,
and a job switched off by `rules:`, `only:` or `except:` on GitLab are not seen, and review has to
catch them too. These rules guard the files against drift; they are no security boundary, since
whoever can change the forge configs can change `ci/` too. A tree with neither `.gitlab-ci.yml` nor
`ci/hooks/`, such as v1.6.0, is not judged by these rules.

### Where each v1.6.0 check went

| v1.6.0 GitHub check | What it ran | Stage now | GitHub job now |
|---|---|---|---|
| `QGIS 3.44-trixie` | `make lint` and `make test` in qgis/qgis:3.44-trixie | lint (once, on Python 3.13) and test-344 | `default (lint)`, `default (test-344)` |
| `QGIS 4.2-trixie` | the same in qgis/qgis:4.2-trixie | lint and test-42 | `default (lint)`, `default (test-42)` |
| `Declared floor (QGIS 3.22)` | `tests/floor_check.py` in qgis/qgis:3.22 | floor | `default (floor)` |
| `Declared floor (test suite)` | `make test` in qgis/qgis:release-3_22 | test-322 | `default (test-322)` |
| `Qt6 check (pyqt5_to_pyqt6)` | `make qt6-check` | qt6 | `default (qt6)` |
| `Package (build zip)` | `make package`, and the zip as the artifact `fiberq-plugin` | package | `default (package)`; the zip, its `.sha256` and its `.contents.tsv` are in the artifact `ci-results-default-package-<attempt>`, under `<run>/package/` |
| | | pure (new) | `default (pure)` |

### No forge: the pre-push hook

`ci/hooks/pre-push` runs the hook set as `sh ci/run-all.sh --hook --ref <commit>` on the commit at the
tip of each ref the push updates (commits below a tip are sent but not tested on their own): the commit
that goes out is the one tested, not the working tree, and nothing is copied into `dist/`. It is
opt-in, once per clone:

```sh
git config core.hooksPath ci/hooks
sh ci/pull.sh --hook
```

A push that only deletes refs tests nothing, several refs on one commit test it once, and a commit that
the remote's tracking refs (`refs/remotes/<remote>/`) already reach is not tested again. When the hook
set fails, git refuses the push; `git push --no-verify` skips the hook once. git runs the hook once for
each push URL of a remote, and after each URL's push it moves the tracking branch of each ref that URL
accepted, if the remote's fetch refspec maps it (by default every branch). So the next URL's run skips
a commit that a branch the first URL accepted reaches, and tests the rest; a commit that only a tag
carries is tested once for each push URL.
`core.hooksPath` replaces `.git/hooks/` for that clone. If git says that the hook was ignored because
it is not executable, run `chmod +x ci/hooks/pre-push` once.

The hook and the scripts it starts come from the checked-out tree: after checking out a branch you
have not reviewed, push with `git push --no-verify`, or review its `ci/` first. Over SSH, git keeps the
connection open while the hook runs; if a hooked push ends with "the remote end hung up unexpectedly",
set `ServerAliveInterval 60` for that host in `~/.ssh/config`.

### No forge: a schedule

One crontab line runs the default set every night at 03:00, in a clone kept for it, and appends each
night's output to a log:

```
0 3 * * * cd "$HOME/fiberq-ci" && { git pull -q --ff-only; sh ci/pull.sh; sh ci/run-all.sh; } >>"$HOME/fiberq-ci.log" 2>&1
```

The run starts even when a pull failed, and the log shows why: a missing checker image then shows as
qt6 skipped, and any other missing image as its stage failing.

### Other forges

A sketch for Forgejo Actions, not tested. It assumes a runner whose label runs jobs on its own host,
with git, node and docker or podman installed there (for example a runner registered with
`--labels fiberq-host:host`):

```yaml
# .forgejo/workflows/ci.yml
on: [push]
jobs:
  quick:
    runs-on: fiberq-host
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: sh ci/pull.sh --quick
      - run: sh ci/run-all.sh --quick
```

## Where to see the runs

- GitHub Actions: <https://github.com/vukovicvl/fiberq/actions/workflows/ci.yml>, each run with its
  stages' records as artifacts, kept for the repository's retention period (90 days by default).
- GitLab: <https://gitlab.com/vukovicvl/fiberq/-/pipelines>, for `main`, release branches and tags.
- `docs/ci/` in this repository: the run record of each release, starting with v1.7.0, committed after
  the release in a pull request of its own ([RELEASE.md](../RELEASE.md), step 9): `docs/ci/<version>.md`,
  with the zip's contents file `docs/ci/<version>-contents.tsv`.

## Check it without GitHub in about ten minutes

With git and docker (or podman) on Linux x86-64:

1. `git clone https://gitlab.com/vukovicvl/fiberq.git && cd fiberq && git checkout v1.7.0`
2. `sh ci/pull.sh --hook` (one image, about 0.2 GB), then `sh ci/run-all.sh --hook` (pure, lint and
   package; `run-all.sh` never pulls).
3. `git show origin/main:docs/ci/1.7.0-contents.tsv | diff - dist/fiberq-1.7.0.contents.tsv` prints
   nothing when every file in the zip you built is the released one.

Until v1.7.0 is tagged and its record is committed to `main`, steps 1 and 3 cannot run. The full
`--quick` set first pulls about 7.4 GB.

## Keeping it current

The checker's digest in `ci/legs` moves at each release ([RELEASE.md](../RELEASE.md), step 1):
plugins.qgis.org follows the checker's `main-ubuntu` tag, while the pipeline runs a pinned digest. The
other image digests and the tool pins in `ci/requirements-*.txt` move on purpose, each change in a
commit of its own ("Moving a pin" in RELEASE.md): `sh ci/pull.sh --bump <role>` prints a role's new
`ci/legs` line, and `sh ci/lock.sh` writes new lock files to copy over. A new python or 4.2 digest goes
into `.gitlab-ci.yml` too: the lint stage fails until both agree.

## Licence

The pipeline is part of FiberQ and is free software under the GNU General Public License, version 3 or
later; each script carries the line `SPDX-License-Identifier: GPL-3.0-or-later`.
