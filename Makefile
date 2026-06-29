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

.DEFAULT_GOAL := help

.PHONY: help deps lint flake8 bandit test test-cov package install uninstall clean tag release version

help:
	@echo "FiberQ - make targets (current version: $(VERSION))"
	@echo "  deps      install lint/test tooling (flake8, bandit, pytest, pytest-qgis)"
	@echo "  lint      flake8 + bandit  (mirrors the plugins.qgis.org scan gate)"
	@echo "  test      run the pytest suite (needs QGIS bindings - see header)"
	@echo "  package   build $(ZIP) for upload to the QGIS plugin repository"
	@echo "  install   copy the plugin into your local QGIS profile (manual testing)"
	@echo "  clean     remove dist/ and caches"
	@echo "  release   lint + test + package + tag v$(VERSION)  (see RELEASE.md)"

version:
	@echo $(VERSION)

# ---- tooling ----------------------------------------------------------------
deps:
	$(PYTHON) -m pip install $(PIP_FLAGS) -U pytest pytest-cov "pytest-qgis>=3.0,<5" flake8 "bandit[toml]"

# ---- lint (mirror of the repository Security & Quality scan) ----------------
lint: flake8 bandit

flake8:
	$(PYTHON) -m flake8 --isolated --max-line-length=120 --ignore=E501 $(PKG) tests conftest.py

bandit:
	# Medium/high severity only (-ll), matching the scan policy. Config in pyproject.toml.
	$(PYTHON) -m bandit -r $(PKG) -ll -q -c pyproject.toml

# ---- tests ------------------------------------------------------------------
# QT_QPA_PLATFORM=offscreen runs Qt without a display. The qgis/qgis image also
# ships xvfb if a real X server is ever needed: `xvfb-run make test`.
test:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest

test-cov:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest --cov=$(PKG) --cov-report=term-missing --cov-report=xml

# ---- package (reproducible plugin zip) --------------------------------------
# Archives ONLY the fiberq/ subtree, prefixed so the zip contains fiberq/...
# Dev/CI files live at the repo root and are therefore never shipped.
# Uses git (local; no GitHub needed) and packages committed state.
package:
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
