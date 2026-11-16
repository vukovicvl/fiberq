# FiberQ - developer commands. The pipeline itself lives in ci/ (ci/README.md): POSIX sh
# scripts that run with git and docker or podman, with no forge, on the hosts that
# ci/README.md describes ("What the host needs"). The forge configs (.github/workflows/ci.yml,
# .gitlab-ci.yml) and the pre-push hook (ci/hooks/pre-push) call ci/ directly, not these
# targets.
#
# make lint and make test run their stage here, with no container (CI_IN_PLACE=1), on the
# python3 found on PATH (not $(PYTHON)). qt6-check, floor-check, package, ci, ci-quick,
# ci-release, release and tag are short names for sh ci/run-all.sh and sh ci/tag.sh in host
# mode, with CI_IN_PLACE cleared so that an exported CI_IN_PLACE=1 cannot skip their stages:
# the stages run in fresh containers, except that package builds its zip with the host's git
# and release-check runs on the host. qt6-check first runs sh ci/pull.sh qt6, so a checker
# image that cannot be pulled fails it instead of passing as a skip. make exits 2 whenever
# a command fails; sh ci/run-all.sh itself tells 1 (a stage failed) from 2 (a usage error,
# a refusal or a broken environment).
#
# Repo layout:
#   fiberq/   the QGIS plugin package (metadata.txt, __init__.py, core/, ...)
#   tests/    pytest suite
#   ci/       the pipeline (run-all.sh, the stage scripts, ci/legs, ci/hooks/)
#
# make test needs QGIS's Python bindings importable by python3: a local QGIS, conda or
# OSGeo4W. The qgis.org packages for Debian and Ubuntu put them in /usr/share/qgis/python:
#   PYTHONPATH=/usr/share/qgis/python make test
# Without them, run a test leg in its container instead: sh ci/run-all.sh --only 42

PLUGIN_NAME := fiberq
PKG := $(PLUGIN_NAME)

# Version comes from metadata.txt, NOT a git tag, so every target is self-contained
# and identical locally and in CI. `tr -d` strips the trailing CR on CRLF files.
VERSION := $(shell grep -E '^version=' $(PKG)/metadata.txt 2>/dev/null | head -n1 | cut -d= -f2 | tr -d '[:space:]')

PYTHON ?= python3
# PEP 668 systems (recent Debian/Ubuntu, incl. the QGIS images) need this for pip.
# Set PIP_FLAGS= (empty) when installing into a virtualenv.
PIP_FLAGS ?= --break-system-packages

# The docs PDFs are rendered with WeasyPrint, which is a repo-root dev
# dependency and is deliberately absent from the plugin. It lives in the root
# virtualenv when there is one, so docs-pdf prefers that interpreter and does
# not install anything into the system Python behind your back.
DOCS_PYTHON ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo $(PYTHON))

DIST_DIR := dist
ZIP := $(DIST_DIR)/$(PLUGIN_NAME)-$(VERSION).zip

# Flags for sh ci/run-all.sh in the targets below, e.g.  make ci CI_ARGS='--jobs 2'
CI_ARGS ?=

# ---- i18n -------------------------------------------------------------------
# Locales we ship catalogs for. Add one here, run `make i18n-update`, and a new
# fiberq/i18n/fiberq_<locale>.ts appears (seeded with the right language tag).
LOCALES ?= sr fr ka
I18N_DIR := $(PKG)/i18n

# pylupdate6 (Debian/Ubuntu: pyqt6-dev-tools) is a pure-Python rewrite: it does
# NOT understand .pro files, so the .py sources must be passed on the argv.
PYLUPDATE ?= pylupdate6
# lrelease comes from the Qt tools (qt6-l10n-tools / qttools5-dev-tools), not PyQt.
LRELEASE ?= lrelease
# lconvert ships alongside lrelease; used to normalise the .ts catalogs.
LCONVERT ?= lconvert
# Lazily evaluated (=, not :=) so the tree is only walked when an i18n target
# actually runs. Paths are relative to the repo root and contain no spaces.
I18N_SOURCES = $(shell find $(PKG) -name '*.py' \
	-not -path '*/__pycache__/*' \
	-not -path '*/tests/*' \
	-not -name 'conftest.py' \
	-not -name 'test_*' \
	-not -name '*_test.py' | sort)

.DEFAULT_GOAL := help

.PHONY: help deps lint test test-cov package install uninstall clean tag release version mapping-doc docs-pdf \
        i18n-update i18n-compile i18n-stats i18n-check \
        qt6-check floor-check \
        bench bench-list bench-smoke

help:
	@echo "FiberQ - make targets (current version: $(VERSION)); the pipeline is in ci/ (ci/README.md)"
	@echo "  lint         the lint stage, here, no container (python3 3.12 or later): flake8 and Bandit"
	@echo "               with the plugins.qgis.org scan's flags, detect-secrets as that scan runs it,"
	@echo "               shellcheck, the .ts placeholders, the forge configs"
	@echo "  test         the whole test suite, here, no container, on the QGIS that python3 imports"
	@echo "  deps         install the hash-pinned test and lint tools into $(PYTHON)"
	@echo "  test-cov     pytest with coverage in $(PYTHON) (after make deps)"
	@echo "  qt6-check    pull the checker image, then the Qt6 check plugins.qgis.org runs, in it"
	@echo "  floor-check  parse + import every module on QGIS 3.22, in its container"
	@echo "  package      build and check the zip in ci-results/<run>/package/; into dist/ only when"
	@echo "               dist/ holds none of its files (nothing there is overwritten)"
	@echo "  ci           the default set: pure lint qt6 floor package, test legs 3.22 3.44 4.2"
	@echo "  ci-quick     pure lint qt6 floor package"
	@echo "  release      the release set: the default set, legs 3.40 4.0, the release check (= ci-release)"
	@echo "  tag          tag v$(VERSION) when the newest full release run of this tree passed"
	@echo "               (RELEASE.md, step 5)"
	@echo "  install      copy the plugin into your local QGIS profile (manual testing)"
	@echo "  clean        remove pytest and coverage caches (never dist/, ci-results/, .ci-cache/)"
	@echo "  images: sh ci/pull.sh [--quick|--release|<stage>...]   flags: make ci CI_ARGS='--jobs 2'"
	@echo ""
	@echo "  documentation"
	@echo "    mapping-doc    regenerate docs/interchange-mapping.md from the code"
	@echo "    docs-pdf       render the published guides to dist/docs/*.pdf (website downloads)"
	@echo ""
	@echo "  benchmark (dev-only; see tools/bench/README.md)"
	@echo "    bench-list     the measurable scenarios, and which rows are controls"
	@echo "    bench          run them: make bench BENCH_DATA=<dataset dir>"
	@echo "    bench-smoke    run every scenario once, no timing (what CI checks)"
	@echo ""
	@echo "  translations (locales: $(LOCALES))"
	@echo "    i18n-update    refresh $(I18N_DIR)/*.ts from source (merges; keeps translations)"
	@echo "    i18n-compile   build the .qm files the plugin loads at runtime (needs lrelease)"
	@echo "    i18n-stats     per-locale translated / unfinished counts"

version:
	@echo $(VERSION)

# ---- tooling ----------------------------------------------------------------
# The hash-pinned test and lint tools of the pipeline (ci/requirements-test.txt and
# ci/requirements-lint.txt), installed into $(PYTHON): for running pytest or flake8 by hand, and
# for test-cov. make lint and make test do not need it: they install the same pins into
# .ci-cache/ on first use. The lint lock is made for Python 3.12 and later.
# PIP_FLAGS (above) is --break-system-packages unless you set PIP_FLAGS= (a virtualenv).
# --ignore-installed: the QGIS images ship some tools (pytest) from apt, without the RECORD file
# pip needs to uninstall them.
deps:
	$(PYTHON) -m pip install $(PIP_FLAGS) --ignore-installed --disable-pip-version-check \
		--only-binary=:all: --require-hashes -r ci/requirements-test.txt
	$(PYTHON) -m pip install $(PIP_FLAGS) --ignore-installed --disable-pip-version-check \
		--only-binary=:all: --require-hashes -r ci/requirements-lint.txt

# ---- lint and tests, here, with no container ---------------------------------
# lint: the lint stage (ci/lint.sh) in this environment: flake8 and Bandit with the flags of
# plugins.qgis.org's scan (every Bandit severity), detect-secrets as that scan runs it,
# shellcheck and flake8 on ci/, the .ts placeholder check and the checks of the forge configs.
# test: the whole test suite on the QGIS that python3 imports (the test-local stage).
# Both use python3 from PATH, not $(PYTHON): to use another interpreter, put its folder first,
# e.g.  PATH=/path/to/venv/bin:$PATH make lint  (the lint tools need Python 3.12 or later).
# Both install their pinned tools into .ci-cache/ on first use (network) and write their record
# to a new ci-results/<run>/.
lint:
	CI_IN_PLACE=1 sh ci/run-all.sh --only lint $(CI_ARGS)

test:
	CI_IN_PLACE=1 sh ci/run-all.sh --only test-local $(CI_ARGS)

# pytest with coverage in $(PYTHON) itself, outside the pipeline: run make deps first.
test-cov:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest --cov=$(PKG) --cov-report=term-missing --cov-report=xml

# ---- Qt6 and floor gates, each in its container ------------------------------
# qt6-check: QGIS's pyqt5_to_pyqt6.py in the checker image that plugins.qgis.org runs for its
#   "Qt6 Check" tab (ci/qt6-check.sh): 0 findings in fiberq/, and at least 4 in tests/qt6_seed/,
#   old-style code kept on purpose, so a checker that stops reporting fails the gate.
# floor-check: tests/floor_check.py on QGIS 3.22, the qgisMinimumVersion of metadata.txt
#   (ci/floor-check.sh): every fiberq/ module parses and imports there. The floor line of
#   ci/legs and qgisMinimumVersion change together.
# qt6-check pulls the checker image first (sh ci/pull.sh qt6, which pulls nothing when the
# pinned digest is here): without it the stage would be skipped, and a skip passes. floor-check
# fails on a missing image with the pull command in its reason. In place (a local checker, or a
# local QGIS 3.22):  CI_IN_PLACE=1 sh ci/run-all.sh --only qt6     (or --only floor)
qt6-check:
	CI_IN_PLACE= sh ci/pull.sh qt6 && CI_IN_PLACE= sh ci/run-all.sh --only qt6 $(CI_ARGS)

floor-check:
	CI_IN_PLACE= sh ci/run-all.sh --only floor $(CI_ARGS)

# ---- generated docs ---------------------------------------------------------
# docs/interchange-mapping.md is generated from models/schema.py and
# core/interchange_fields.py. tests/test_interchange_mapping.py fails if the
# published page falls behind the code, so run this after changing either.
mapping-doc:
	$(PYTHON) tools/gen_interchange_mapping.py

# The PDFs offered as downloads on fiberq.net. Dev-only: WeasyPrint is a
# repo-root dependency and never ships in the plugin zip (the plugin itself
# exports HTML, JSON and CSV). Output lands in dist/docs/, which is gitignored --
# the Markdown in docs/ is the source of truth, the PDF is a rendering of it.
# One-time setup:  .venv/bin/pip install weasyprint markdown
docs-pdf:
	$(DOCS_PYTHON) tools/make_docs_pdf.py

# ---- benchmark (WP4 Task 4.1) -----------------------------------------------
# Measures a fixed list of user actions on a seeded city-sized project and writes
# one JSON file per row. Dev-only and never shipped: `package` archives
# fiberq/ only, so nothing under tools/ reaches the zip. Deliberately NOT wired
# into lint, test or release -- it needs a generated dataset and takes minutes.
#
# Uses plain $(PYTHON), not $(DOCS_PYTHON): the benchmark has to run inside the
# QGIS container, not the root virtualenv.
#
#   make bench-list
#   make bench BENCH_DATA=/work/data/fiberq-city/city_S BENCH_OUT=/work/out/run1
#
# The dataset comes from tests/fixtures/make_city_project.py; the "before" side
# comes from `git archive v1.5.0:fiberq`. The full procedure and the fairness
# rules are in tools/bench/README.md.
BENCH_CODE ?= .
BENCH_DATA ?=
BENCH_OUT ?= $(DIST_DIR)/bench
BENCH_ARGS ?=

bench-list:
	$(PYTHON) tools/bench/bench.py --list

bench:
	@[ -n "$(BENCH_DATA)" ] || { echo "set BENCH_DATA=<dataset directory> - see tools/bench/README.md"; exit 2; }
	QT_QPA_PLATFORM=offscreen $(PYTHON) tools/bench/bench.py \
		--code $(BENCH_CODE) --data $(BENCH_DATA) --out $(BENCH_OUT) $(BENCH_ARGS)

# One cold call per scenario in one process: does every row still resolve its
# layers, hold its post-condition and run without logging an error on this
# dataset? Not a measurement -- run it on a freshly generated dataset before
# spending a night on a real benchmark. tests/test_bench_harness.py runs the
# same script, which is how CI covers the harness without timing anything.
bench-smoke:
	@[ -n "$(BENCH_DATA)" ] || { echo "set BENCH_DATA=<dataset directory> - see tools/bench/README.md"; exit 2; }
	QT_QPA_PLATFORM=offscreen $(PYTHON) tools/bench/bench_smoke.py \
		--code $(BENCH_CODE) --data $(BENCH_DATA) --out $(BENCH_OUT)/smoke.json $(BENCH_ARGS)

# ---- i18n -------------------------------------------------------------------
# Workflow:  make i18n-update  ->  translate the .ts in Qt Linguist  ->
#            make i18n-compile ->  git add fiberq/i18n/*.ts fiberq/i18n/*.qm
# Both .ts and .qm MUST be committed: `package` below archives committed fiberq/
# files only, so an uncommitted .qm never reaches users.

# Regenerate the catalogs. pylupdate6 MERGES into an existing .ts, so finished
# translations survive and only new strings show up as type="unfinished".
# A brand-new catalog is seeded with the language/sourcelanguage attributes
# first, because pylupdate6 does not write them itself (Qt Linguist would then
# have to ask for the target language, and plural rules would be unknown).
# The seed is only written when the file is absent, so re-runs are idempotent.
i18n-update:
	@command -v $(PYLUPDATE) >/dev/null 2>&1 || { \
		echo "$(PYLUPDATE) not found - install it with:"; \
		echo "    sudo apt install pyqt6-dev-tools      # Debian/Ubuntu"; \
		echo "    (or: pip install PyQt6)"; \
		exit 1; \
	}
	@mkdir -p $(I18N_DIR)
	@for loc in $(LOCALES); do \
		ts="$(I18N_DIR)/$(PLUGIN_NAME)_$$loc.ts"; \
		if [ ! -f "$$ts" ]; then \
			printf '%s\n' \
				'<?xml version="1.0" encoding="utf-8"?>' \
				'<!DOCTYPE TS>' \
				"<TS version=\"2.1\" language=\"$$loc\" sourcelanguage=\"en\">" \
				'</TS>' > "$$ts"; \
			echo "created $$ts"; \
		fi; \
		$(PYLUPDATE) --ts "$$ts" $(I18N_SOURCES) || exit 1; \
	done
	@$(MAKE) --no-print-directory i18n-normalize
	@echo "Catalogs updated. Translate them, then run: make i18n-compile"

# pylupdate6 emits one <message> per CALL SITE, so a string used in several places
# arrives duplicated, and strings deleted from the source linger as type="vanished".
# Both are noise a translator would have to wade through, and the duplicate count
# drifts every run - which makes the .ts diff unreadable in review. lconvert
# collapses duplicates and drops obsolete entries, so re-running i18n-update is
# idempotent. Finished translations are preserved. Silent no-op if lconvert is
# absent: normalising is hygiene, and must never block string extraction.
i18n-normalize:
	@lc=""; \
	for cand in $(LCONVERT) lconvert-qt6 /usr/lib/qt6/bin/lconvert \
	            /usr/lib/qt5/bin/lconvert /usr/lib/x86_64-linux-gnu/qt6/bin/lconvert; do \
		if command -v "$$cand" >/dev/null 2>&1 || [ -x "$$cand" ]; then lc="$$cand"; break; fi; \
	done; \
	if [ -z "$$lc" ]; then \
		echo "note: lconvert not found - catalogs left un-normalised (duplicates may remain)."; \
		exit 0; \
	fi; \
	for ts in $(wildcard $(I18N_DIR)/*.ts); do \
		"$$lc" -no-obsolete "$$ts" -o "$$ts" 2>/dev/null || exit 1; \
	done; \
	echo "Catalogs normalised (duplicates merged, obsolete entries dropped)."

# Compile .ts -> .qm. lrelease ships with the Qt tools, NOT with PyQt, so it can
# be missing even when pylupdate6 is present; fail loudly instead of silently
# shipping stale/absent .qm files. lrelease-qt6/-qt5 are the Debian alt names.
# -nounfinished: only translations a translator marked done ship. Plain lrelease
# also compiles entries still marked "unfinished" -- a volunteer's half-done
# draft -- and docs/TRANSLATING.md promises those are not shipped.
i18n-compile:
	@lr=""; \
	for cand in $(LRELEASE) lrelease-qt6 lrelease6 lrelease-qt5; do \
		if command -v "$$cand" >/dev/null 2>&1; then lr="$$cand"; break; fi; \
	done; \
	if [ -z "$$lr" ]; then \
		for cand in /usr/lib/qt6/bin/lrelease /usr/lib/qt5/bin/lrelease \
		            /usr/lib/x86_64-linux-gnu/qt6/bin/lrelease \
		            /usr/lib/x86_64-linux-gnu/qt5/bin/lrelease; do \
			if [ -x "$$cand" ]; then lr="$$cand"; break; fi; \
		done; \
	fi; \
	if [ -z "$$lr" ]; then \
		echo "ERROR: lrelease not found - cannot compile $(I18N_DIR)/*.ts into .qm."; \
		echo "Install it with:"; \
		echo "    sudo apt install qt6-l10n-tools       # Qt6 (QGIS 4)"; \
		echo "    sudo apt install qttools5-dev-tools   # Qt5 (QGIS 3.x)"; \
		echo "Override the binary with: make i18n-compile LRELEASE=/path/to/lrelease"; \
		exit 1; \
	fi; \
	set -- $(wildcard $(I18N_DIR)/*.ts); \
	if [ "$$#" -eq 0 ]; then \
		echo "No .ts catalogs in $(I18N_DIR) - run 'make i18n-update' first."; \
		exit 1; \
	fi; \
	"$$lr" -nounfinished "$$@" || exit 1; \
	echo "Compiled .qm in $(I18N_DIR) - remember to 'git add' them (see package)."

# Translation progress, straight out of the .ts XML. Pure stdlib, no extra deps.
define I18N_STATS_PY
import glob
import os
import sys
import xml.etree.ElementTree as ET

i18n_dir = sys.argv[1]
paths = sorted(glob.glob(os.path.join(i18n_dir, '*.ts')))
if not paths:
    print('No .ts catalogs in ' + i18n_dir + ' - run: make i18n-update')
    sys.exit(0)
row = '{:<10} {:>7} {:>7} {:>7} {:>9} {:>8}'
print(row.format('locale', 'total', 'done', 'todo', 'vanished', 'percent'))
for path in paths:
    stem = os.path.basename(path)[:-3]
    locale = stem.split('_', 1)[1] if '_' in stem else stem
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        print('{:<10} unreadable: {}'.format(locale, exc))
        continue
    done = todo = gone = 0
    for message in root.iter('message'):
        node = message.find('translation')
        kind = node.get('type') if node is not None else None
        if kind in ('vanished', 'obsolete'):
            gone += 1
        elif kind == 'unfinished' or node is None or not (node.text or '').strip():
            todo += 1
        else:
            done += 1
    live = done + todo
    pct = (100.0 * done / live) if live else 0.0
    print(row.format(locale, live, done, todo, gone, '{:.1f}%'.format(pct)))
endef
export I18N_STATS_PY

i18n-stats:
	@$(PYTHON) -c "$$I18N_STATS_PY" $(I18N_DIR)

# Advisory only - NEVER fails. The package stage gives the same .qm warnings, from commit
# times (ci/package.sh); this target compares file times.
i18n-check: i18n-check-placeholders
	@for ts in $(wildcard $(I18N_DIR)/*.ts); do \
		qm="$${ts%.ts}.qm"; \
		if ! git cat-file -e "HEAD:$$qm" 2>/dev/null; then \
			echo "WARNING: $$qm is not committed - that locale will NOT ship."; \
			echo "         run 'make i18n-compile' then 'git add $$qm'"; \
		elif [ -f "$$qm" ] && [ "$$ts" -nt "$$qm" ]; then \
			echo "WARNING: $$qm is older than $$ts - run 'make i18n-compile'."; \
		fi; \
	done

# Placeholder validation. Translations are hand-edited by volunteers, and a
# renamed or malformed placeholder ({nom} for {name}, a stray brace) makes
# str.format raise at the point the string is displayed. safe_format() in
# fiberq/i18n keeps that from taking the plugin down, but the label still falls
# back to English -- so catch it here, while it is still cheap to fix.
# Unlike the rest of i18n-check this target FAILS, because a broken placeholder
# is a real defect and reaches users silently.
define I18N_PLACEHOLDER_PY
import glob
import re
import sys
import xml.etree.ElementTree as ET

FIELD = re.compile(r'{([a-zA-Z_][a-zA-Z0-9_]*)?[^{}]*}')


def fields(text):
    """Named placeholders in a format string, ignoring {{ }} escapes."""
    return {m.group(1) for m in FIELD.finditer(text.replace('{{', '').replace('}}', ''))
            if m.group(1)}


bad = 0
for path in sorted(glob.glob('fiberq/i18n/*.ts')):
    for ctx in ET.parse(path).getroot().iter('context'):
        name = ctx.findtext('name')
        for msg in ctx.iter('message'):
            src = msg.findtext('source') or ''
            node = msg.find('translation')
            if node is None:
                continue
            for text in ([node.text] if node.text else
                         [n.text for n in node.iter('numerusform')]):
                if not text:
                    continue
                want, got = fields(src), fields(text)
                if want != got:
                    bad += 1
                    print('%s [%s] %r' % (path, name, src))
                    print('    translated : %r' % text)
                    print('    expected {%s}, found {%s}'
                          % (', '.join(sorted(want)) or '-',
                             ', '.join(sorted(got)) or '-'))
                try:
                    text.format(**{f: '' for f in got})
                except (ValueError, IndexError, KeyError) as exc:
                    bad += 1
                    print('%s [%s] malformed: %r (%s)' % (path, name, text, exc))

if bad:
    print('\n%d placeholder problem(s). Translators must keep placeholders '
          'spelled exactly as in the source.' % bad)
    sys.exit(1)
print('Placeholders OK in all catalogs.')
endef
export I18N_PLACEHOLDER_PY

i18n-check-placeholders:
	@$(PYTHON) -c "$$I18N_PLACEHOLDER_PY"

# ---- package (reproducible plugin zip) --------------------------------------
# The package stage (ci/package.sh): "TZ=UTC git archive --format=zip" of fiberq/ at the last
# commit that changed it, so the zip holds committed files only, under one fiberq/ folder, and
# the same commit gives the same bytes on any machine with the same git and zlib. It warns for
# each .qm catalog that is not committed or was last committed before its .ts (commit times),
# checks the zip in the python image and writes a .sha256 and a .contents.tsv beside it. The
# build goes to ci-results/<run>/package/, and into dist/ only when dist/ holds none of its three
# files and fiberq/ has no uncommitted change: nothing in dist/ is overwritten or deleted.
package:
	CI_IN_PLACE= sh ci/run-all.sh --only package $(CI_ARGS)

# ---- local install for manual QGIS testing ---------------------------------
# QGIS 4 moved its configuration root from .../QGIS/QGIS3 to .../QGIS/QGIS4.
# Hardcoding QGIS3 made `make install` a silent no-op for QGIS 4 users: files were
# copied, success was printed, and QGIS read a different directory entirely.
# So detect the root instead, newest first. QGIS_ROOT covers the per-OS location,
# QGIS_PROFILE the profile within it; either can be overridden:
#
#   make install QGIS_PROFILE_NAME=i18n-test          # different profile, same OS
#   make install QGIS_ROOT="$HOME/Library/Application Support/QGIS"   # macOS
#   make install QGIS_ROOT="$APPDATA/QGIS"            # Windows, from Git Bash
#   make install QGIS_PROFILE=/full/path/to/profile   # bypass detection entirely
QGIS_ROOT ?= $(HOME)/.local/share/QGIS
QGIS_PROFILE_NAME ?= default
# $(wildcard) tests existence; QGIS4 wins when both are present.
QGIS_VERSION_DIR := $(notdir $(lastword $(sort $(wildcard $(QGIS_ROOT)/QGIS3) \
                                               $(wildcard $(QGIS_ROOT)/QGIS4))))
QGIS_PROFILE ?= $(QGIS_ROOT)/$(or $(QGIS_VERSION_DIR),QGIS3)/profiles/$(QGIS_PROFILE_NAME)
PLUGIN_DEST := $(QGIS_PROFILE)/python/plugins/$(PLUGIN_NAME)

install:
	@if [ -z "$(QGIS_VERSION_DIR)" ]; then \
		echo "WARNING: no QGIS3/ or QGIS4/ directory under $(QGIS_ROOT)."; \
		echo "         Guessing QGIS3. If QGIS does not see the plugin, pass the"; \
		echo "         real path: make install QGIS_PROFILE=/path/to/profile"; \
	fi
	@mkdir -p "$(dir $(PLUGIN_DEST))"
	@rm -rf "$(PLUGIN_DEST)"
	@cp -r "$(PKG)" "$(PLUGIN_DEST)"
	@find "$(PLUGIN_DEST)" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Installed to $(PLUGIN_DEST)  (restart QGIS or use the Plugin Reloader)"
	@echo "Verify in QGIS: Settings > User Profiles shows '$(QGIS_PROFILE_NAME)'."

uninstall:
	@rm -rf "$(PLUGIN_DEST)"
	@echo "Removed $(PLUGIN_DEST)"

# ---- pipeline sets, release and tag (ci/run-all.sh, ci/tag.sh) ----------------
# The stages run in fresh containers (docker, or CI_ENGINE=podman), except that package builds
# its zip with the host's git and release-check runs on the host; CI_IN_PLACE is cleared, so they
# run in host mode. sh ci/pull.sh is the only step that pulls images, e.g. sh ci/pull.sh --quick
# (make qt6-check runs it for the checker). Results: ci-results/<run>/.
#   make ci          the default set: pure lint qt6 floor package, then the test legs 322 344 42
#   make ci-quick    pure lint qt6 floor package
#   make ci-release  the release set: the default set plus the legs 340 and 40 and the release
#                    check; it refuses a dirty working tree or a shallow clone
#   make release     the same as make ci-release (RELEASE.md, step 3)
#   make tag         the annotated tag v<version> on HEAD, made only when the newest full release
#                    run of HEAD's tree passed and its zip is the one in dist/; it never pushes
#                    (RELEASE.md, step 5)
.PHONY: ci ci-quick ci-release
ci:
	CI_IN_PLACE= sh ci/run-all.sh $(CI_ARGS)

ci-quick:
	CI_IN_PLACE= sh ci/run-all.sh --quick $(CI_ARGS)

ci-release:
	CI_IN_PLACE= sh ci/run-all.sh --release $(CI_ARGS)

release:
	CI_IN_PLACE= sh ci/run-all.sh --release $(CI_ARGS)

tag:
	CI_IN_PLACE= sh ci/tag.sh

# The caches of pytest and coverage runs. dist/, ci-results/ and .ci-cache/ are never deleted by
# a command of this repository: prune them by hand (ci/README.md, "Results, and pruning by hand").
clean:
	@rm -rf .pytest_cache .coverage coverage.xml
	@find . \( -path ./.git -o -path ./dist -o -path ./ci-results -o -path ./.ci-cache \) -prune \
		-o -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Removed the pytest and coverage caches; dist/, ci-results/ and .ci-cache/ are pruned by hand."
