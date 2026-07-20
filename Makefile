# FiberQ - forge-agnostic automation. ALL real logic lives here.
# CI on any forge (GitHub, GitLab, Codeberg) is a thin wrapper that only
# calls these targets, so everything below also runs on a bare laptop.
#
# Assumed repo layout (set up in Phase 0):
#   repo/
#     fiberq/        <- the QGIS plugin package (metadata.txt, __init__.py, core/, ...)
#     tests/         <- pytest suite
#     Makefile  RELEASE.md  pyproject.toml  .flake8  .gitignore  conftest.py
#
# Requirements: python3 + git locally. For `make test`, QGIS Python bindings must
# be importable - use the qgis/qgis Docker image, or a venv created with
# --system-site-packages on a machine that has QGIS installed. QGIS itself is
# NOT pip-installable.

PLUGIN_NAME := fiberq
PKG := $(PLUGIN_NAME)

# Version comes from metadata.txt, NOT a git tag, so every target is self-contained
# and identical locally and in CI. `tr -d` strips the trailing CR on CRLF files.
VERSION := $(shell grep -E '^version=' $(PKG)/metadata.txt 2>/dev/null | head -n1 | cut -d= -f2 | tr -d '[:space:]')

PYTHON ?= python3
# PEP 668 systems (recent Debian/Ubuntu, incl. the QGIS images) need this for pip.
# Set PIP_FLAGS= (empty) when installing into a virtualenv.
PIP_FLAGS ?= --break-system-packages

DIST_DIR := dist
ZIP := $(DIST_DIR)/$(PLUGIN_NAME)-$(VERSION).zip

# ---- i18n -------------------------------------------------------------------
# Locales we ship catalogs for. Add one here, run `make i18n-update`, and a new
# fiberq/i18n/fiberq_<locale>.ts appears (seeded with the right language tag).
LOCALES ?= sr fr
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

.PHONY: help deps lint flake8 bandit test test-cov package install uninstall clean tag release version \
        i18n-update i18n-compile i18n-stats i18n-check

help:
	@echo "FiberQ - make targets (current version: $(VERSION))"
	@echo "  deps      install lint/test tooling (flake8, bandit, pytest, pytest-qgis)"
	@echo "  lint      flake8 + bandit  (mirrors the plugins.qgis.org scan gate)"
	@echo "  test      run the pytest suite (needs QGIS bindings - see header)"
	@echo "  package   build $(ZIP) for upload to the QGIS plugin repository"
	@echo "  install   copy the plugin into your local QGIS profile (manual testing)"
	@echo "  clean     remove dist/ and caches"
	@echo "  release   lint + test + package + tag v$(VERSION)  (see RELEASE.md)"
	@echo ""
	@echo "  translations (locales: $(LOCALES))"
	@echo "    i18n-update    refresh $(I18N_DIR)/*.ts from source (merges; keeps translations)"
	@echo "    i18n-compile   build the .qm files the plugin loads at runtime (needs lrelease)"
	@echo "    i18n-stats     per-locale translated / unfinished counts"

version:
	@echo $(VERSION)

# ---- tooling ----------------------------------------------------------------
deps:
	$(PYTHON) -m pip install $(PIP_FLAGS) --ignore-installed pytest pytest-cov "pytest-qgis>=3.0,<5" flake8 "bandit[toml]"

# ---- lint (mirror of the repository Security & Quality scan) ----------------
lint: flake8 bandit

flake8:
	$(PYTHON) -m flake8 --isolated --max-line-length=120 --ignore=E501 $(PKG) tests conftest.py

bandit:
	# ALL severities — the plugins.qgis.org scanner flags LOW too (e.g. B110/B112
	# try/except/pass|continue), so -ll (medium/high only) is NOT enough. Config in pyproject.toml.
	$(PYTHON) -m bandit -r $(PKG) -q -c pyproject.toml

# ---- tests ------------------------------------------------------------------
# QT_QPA_PLATFORM=offscreen runs Qt without a display. The qgis/qgis image also
# ships xvfb if a real X server is ever needed: `xvfb-run make test`.
test:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest

test-cov:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest --cov=$(PKG) --cov-report=term-missing --cov-report=xml

# ---- i18n -------------------------------------------------------------------
# Workflow:  make i18n-update  ->  translate the .ts in Qt Linguist  ->
#            make i18n-compile ->  git add fiberq/i18n/*.ts fiberq/i18n/*.qm
# Both .ts and .qm MUST be committed: `package` below archives HEAD:fiberq, so
# an uncommitted .qm never reaches users.

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
	"$$lr" "$$@" || exit 1; \
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

# Advisory only - NEVER fails. See the note on `package` below.
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
# Archives ONLY the fiberq/ subtree, prefixed so the zip contains fiberq/...
# Dev/CI files live at the repo root and are therefore never shipped.
# Uses git (local; no GitHub needed) and packages committed state.
#
# i18n-check, NOT i18n-compile, is the prerequisite - deliberately. Because this
# target archives HEAD, running lrelease here could not change the zip anyway:
# only committed .qm files ship. A hard `package: i18n-compile` would therefore
# buy nothing while breaking `make package` (and so `make release`) on every
# machine without qt6-l10n-tools, including the qgis/qgis CI images. i18n-check
# gives the same warning at the same moment and always exits 0.
package: i18n-check
	@rm -rf $(DIST_DIR)
	@mkdir -p $(DIST_DIR)
	git archive --format=zip --prefix=$(PLUGIN_NAME)/ -o $(ZIP) HEAD:$(PKG)
	@echo "Built $(ZIP)"

# ---- local install for manual QGIS testing ---------------------------------
# Override QGIS_PROFILE for your OS, e.g.:
#   macOS:   ~/Library/Application Support/QGIS/QGIS3/profiles/default
#   Windows: %APPDATA%/QGIS/QGIS3/profiles/default
QGIS_PROFILE ?= $(HOME)/.local/share/QGIS/QGIS3/profiles/default
PLUGIN_DEST := $(QGIS_PROFILE)/python/plugins/$(PLUGIN_NAME)

install:
	@mkdir -p "$(dir $(PLUGIN_DEST))"
	@rm -rf "$(PLUGIN_DEST)"
	@cp -r "$(PKG)" "$(PLUGIN_DEST)"
	@find "$(PLUGIN_DEST)" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Installed to $(PLUGIN_DEST)  (restart QGIS or use the Plugin Reloader)"

uninstall:
	@rm -rf "$(PLUGIN_DEST)"
	@echo "Removed $(PLUGIN_DEST)"

# ---- release ----------------------------------------------------------------
# Intentionally does NOT bump the version or upload anything. See RELEASE.md.
release: lint test package tag
	@echo ""
	@echo "Artifact: $(ZIP)"
	@echo "Next (manual, see RELEASE.md): git push && git push --tags, then upload the zip."

tag:
	@if [ -z "$(VERSION)" ]; then echo "No version found in $(PKG)/metadata.txt"; exit 1; fi
	@if git rev-parse "v$(VERSION)" >/dev/null 2>&1; then \
		echo "Tag v$(VERSION) already exists - bump 'version=' in $(PKG)/metadata.txt first."; exit 1; \
	fi
	git tag -a "v$(VERSION)" -m "FiberQ $(VERSION)"
	@echo "Created tag v$(VERSION) (not pushed)."

clean:
	@rm -rf $(DIST_DIR) .pytest_cache .coverage coverage.xml
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
