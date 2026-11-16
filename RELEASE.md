# Releasing FiberQ

How a FiberQ release is made. The steps need git, docker or podman and the pipeline in
[`ci/`](ci/README.md), on a host that [ci/README.md](ci/README.md#what-the-host-needs) describes, and a
web browser for the upload. Step 1 moves the checker pin with `sh ci/pull.sh --bump`, which needs docker
with buildx (with podman, resolve the tag's digest with `skopeo inspect`); steps 2, 4 and 8 also need the
Qt translation tools (`pylupdate6`, `lrelease`), a QGIS install and WeasyPrint for `make docs-pdf`. No
step needs a particular forge. The forges run the same `ci/` scripts on pushes
([Where the pipeline runs](#where-the-pipeline-runs)), but the release record is the one your own run
writes in step 3.

## Versioning

FiberQ uses semantic-style versioning `MAJOR.MINOR.PATCH` (e.g. `1.3.0`).

- The **single source of truth** is `version=` in `fiberq/metadata.txt`.
- `fiberq/__init__.py` also carries `__version__`; keep it identical. A smoke
  test (`tests/test_smoke.py`) fails the build if the two drift apart.
- The **schema version** is tracked separately (see WP1) inside the project's
  `_fiberq_metadata` table. Plugin version and schema version are deliberately
  decoupled: most releases bump the plugin version only.

When to bump which part:
- **PATCH** — bug fixes, cleanup, no behaviour change.
- **MINOR** — new backward-compatible features (a new capability delivery, typically).
- **MAJOR** — breaking changes to the data model or public behaviour.

## Pre-release checklist

Every item is ticked before the tag. The release run of step 3 checks the items marked *(release run)*
again; the others are yours.

- [ ] The lint stage is clean: flake8 and Bandit at **all** severities find 0 (the plugins.qgis.org scan
      flags LOW findings too), detect-secrets finds 0 in `fiberq/`, and shellcheck, the `.ts` placeholder
      check and the forge-config check pass (`make lint`; *release run*).
- [ ] The test suite passes on all five QGIS versions of the release set (*release run*).
- [ ] The checker pin in `ci/legs` is the current build of the checker's `main-ubuntu` tag (step 1).
- [ ] The Qt6 check is clean: the same `pyqt5_to_pyqt6.py --dry_run` check plugins.qgis.org runs, so the
      plugin page's **Qt6 Check** tab is green on upload rather than after it (`make qt6-check`;
      *release run*).
- [ ] `version=` bumped in `fiberq/metadata.txt`, and `__version__` in `fiberq/__init__.py` matches
      (`tests/test_smoke.py` and the package stage check that the two agree; *release run*).
- [ ] `changelog=` block in `fiberq/metadata.txt` updated for this version.
- [ ] Release notes / `changelog=` include a one-line pointer to sponsorship
      (e.g. "If FiberQ helps your work, you can now sponsor its development.").
- [ ] `fiberq/config.ini` contains no credentials or machine-specific paths (the release check fails on
      a `user` or `password` value; the paths are yours to check).
- [ ] "Use of Generative AI" section present and current in `fiberq/README.md` (shipped) and the
      repo-root `README.md` (public landing page) (the release check fails if either heading is missing;
      "current" is yours to check).
- [ ] AI-assisted commits carry the `Assisted-by:` trailer (the release check lists the commits since the
      last tag that have none; merge commits are expected in that list).
- [ ] Manual QGIS test done: install the built zip in a clean profile and open both an older project and
      a new one (step 4).

## Steps

1. **Version, changelog and the checker pin.** On a release branch, `release/v<version>`, bump
   `version=` and `__version__`, write the `changelog=` entry, with the lines of a work-package
   deliverable kept apart from the other fixes, and update the release lines of the root `README.md`
   and of `fiberq/README.md`. Then move the checker pin: `sh ci/pull.sh --bump checker`. If it prints a
   new digest (not `(unchanged)`), replace the checker line of `ci/legs` with the line it prints, in a
   commit of its own. The other pins move only on purpose ("Moving a pin", below).

2. **Translations.** Run `make i18n-update` once and read the `.ts` diff.
   - If a translatable string changed: give the translators a window, announced in the translation
     issues; then run `make i18n-compile` and commit the `.ts` and `.qm` files.
   - If none changed, commit nothing, and put the catalogs back with `git restore fiberq/i18n/`:
     `make i18n-update` also rewrites the source line numbers in them, and step 3 refuses a dirty
     working tree.

3. **The release run.** On the head of the release branch, with a clean working tree and full history:
   ```bash
   sh ci/pull.sh --release                  # once: the images, about 36 GB; the only step that pulls
   sh ci/run-all.sh --release --jobs 2      # or: make release CI_ARGS='--jobs 2'
   ```
   It runs pure, lint, qt6, floor, package, the five test legs and the release check, and fails on any
   failure or skip. It refuses a dirty working tree or a shallow clone, and then runs nothing. It ends
   with `run-all.sh: PASS`; its record is `ci-results/<run>/summary.md` and `record.txt` (about an hour
   on one Linux machine with two legs at a time). The package stage copies the zip, its `.sha256` and its
   `.contents.tsv` into `dist/`. If `dist/` already holds another build of this version, the run fails:
   move those files aside by hand (nothing in the pipeline overwrites or deletes them) and run it again.

4. **Hand checks.** Install `dist/fiberq-<version>.zip` in a clean QGIS profile, and on Windows too when
   a Windows machine is at hand. Open an older project and a new one. The maintainer reviews the code.

5. **Merge, then tag.** Merge the release branch with a merge commit. Fast-forward the local `main` to
   that merge commit, and run `make tag` (`sh ci/tag.sh`) there, in the checkout that made the release
   run. It creates the annotated tag `v<version>` only when the newest full `--release` run of this tree
   in `ci-results/` passed with the pinned images and its zip is the one in `dist/`; the merge commit has
   the tested tree and takes `fiberq/` from the same commit, so the run of step 3 counts. It never
   pushes. If anything changed after step 3 (a fix from the review, or `main` moved), the tree differs:
   run step 3 again on the commit to tag; if the zip changes, move the old `dist/` files aside before
   that run, and repeat step 4 on the new zip.

6. **Push.** Push `main` and the tag, by name, to every remote: `git push <remote> main v<version>`. A
   remote with several push URLs gets them all in one push. Check that every remote shows the tag on the
   same commit, and that the pipeline runs for it pass ([ci/README.md](ci/README.md#where-to-see-the-runs)).

7. **Upload.** Upload `dist/fiberq-<version>.zip` at <https://plugins.qgis.org/>: sign in with the OSGeo
   account, open the FiberQ plugin page, **Add version**. Its Security & Quality scan (flake8, Bandit,
   detect-secrets) should be clean, as the lint stage was; check the scan and the **Qt6 Check** tab, and
   that the new version reaches the QGIS Plugin Manager (it can take a few minutes). The upload is a
   manual web step; keep any credentials out of the repository.

8. **Publish and announce.** Publish the release notes, with the zip and its `.sha256` file, on the
   forge release pages and on the project website. Render the changed guides as PDFs (`make docs-pdf`)
   and update them on the website. Announce the release with a note to the fiberq.net newsletter
   subscribers and a post on LinkedIn, and a YouTube video when there is one.

9. **The run record.** Copy `summary.md` of the release run that `make tag` named ("Release run:
   <folder>") to `docs/ci/<version>.md`, with the local path of the run folder in it shortened to
   `ci-results/<run>/`, and copy `dist/fiberq-<version>.contents.tsv` to `docs/ci/<version>-contents.tsv`.
   Commit both in a pull request of their own. After it merges, fast-forward the local `main` and push
   it to every remote (`git push <remote> main`), so that every forge has the record.

## Tested QGIS versions

`fiberq/metadata.txt` declares `qgisMinimumVersion=3.22` and `qgisMaximumVersion=4.99`. The pipeline
tests that range in the official QGIS images, each pinned by its digest in `ci/legs`:

| Stage | Image (role in `ci/legs`) | QGIS, Python | What it checks | Sets |
|---|---|---|---|---|
| `floor` | `qgis/qgis:3.22` (floor) | 3.22, Python 3.8 | every `fiberq/` module parses and imports on the oldest QGIS and Python, and the image's QGIS is `qgisMinimumVersion` | quick, default, release |
| `test-322` | `qgis/qgis:release-3_22` (322) | 3.22, Python 3.10 | the whole test suite on the oldest QGIS | default, release |
| `test-340` | `qgis/qgis:3.40` (340) | 3.40, Python 3.12 | the whole test suite | release |
| `test-344` | `qgis/qgis:3.44-trixie` (344) | 3.44, Python 3.13 | the whole test suite on QGIS 3 (Qt5) | default, release |
| `test-40` | `qgis/qgis:4.0-trixie` (40) | 4.0, Python 3.13 | the whole test suite | release |
| `test-42` | `qgis/qgis:4.2-trixie` (42) | 4.2, Python 3.13 | the whole test suite on QGIS 4 (Qt6) | default, release |
| `qt6` | `ghcr.io/qgis/pyqgis4-checker` (checker) | | no Qt5-only spelling in `fiberq/`, as the Qt6 Check tab | quick, default, release |

The floor takes two stages because pytest-qgis needs Python 3.10 and the `qgis/qgis:3.22` image has
Python 3.8. `floor` runs `tests/floor_check.py` there, which catches syntax and imports that only the
oldest Python rejects: a release once shipped a module that was a `SyntaxError` on Python 3.8, past a
green CI. `test-322` runs the suite on `release-3_22`, which has the same QGIS with Python 3.10. Two
caveats, both deliberate:

- Lint runs on Python 3.13, in the python image, never on the floor: `tests/floor_seed/` is invalid
  before Python 3.12 on purpose, so flake8 would report E999 there.
- pytest-qgis 4.x asks for QGIS 3.34 or later. It is used outside that range on 3.22 and the suite
  passes, but if only `test-322` goes red, first ask whether it is the plugin or the harness.

The QGIS 4 legs cannot replace `qt6`: `fiberq/utils/compat.py` maps old enum names at run time, so the
plugin can pass its tests on Qt6 while the source still carries spellings the checker rejects.

### Where the pipeline runs

- Any machine that ci/README.md's [What the host needs](ci/README.md#what-the-host-needs) describes runs
  every set: `sh ci/run-all.sh [--hook|--quick|--release]`. The release record is made this way (step 3).
- GitHub Actions runs the default set on every push to a branch other than a `release/` branch and on
  pull requests from forks, and the release set on `release/` branches, on tags and when it is started
  by hand; each stage is a job of its own.
- GitLab CI runs pure, lint and `test-42`, in place in their images, for `main`, `release/` branches and
  tags.

### Moving a pin

The checker's digest in `ci/legs` moves at every release (step 1): plugins.qgis.org follows the
checker's `main-ubuntu` tag, while the pipeline runs a pinned digest. The other image digests in
`ci/legs` and the tool pins in `ci/requirements-*.txt` move only on purpose: when an image is gone from
its registry, or when a release should be tested on a newer build of a QGIS version. Each move is a
commit of its own. `sh ci/pull.sh --bump <role>` (docker with buildx) prints a role's new line for
`ci/legs` (it edits nothing), and `sh ci/lock.sh` writes new lock files and prints the commands that
copy them over. A new
python or 4.2 digest goes into `.gitlab-ci.yml` too; the lint stage fails until both agree. The floor
role and `qgisMinimumVersion` change together, or the floor stage fails. A release compared with the
previous one test by test compares runs on the same digests: after moving a QGIS digest, run the
previous release's tag again on it, `sh ci/run-all.sh --release --ref v<previous>`, and compare with
that run.
