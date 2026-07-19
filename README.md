# FiberQ

Open-source QGIS plugin for fiber optic network design (FTTH / GPON / FTTx).

**Latest release: v1.3.0 — 15.07.2026.** Added on GitHub as a new release.

v1.3.0 — WP1 · Data model & migrations

Project schema versioning, safe automatic migrations, and a stable per-feature identity (fiberq_uuid). Verified end to end on QGIS 3.40 (Qt5) and QGIS 4.2 (Qt6), with both new and migrated older projects.

    Per-project schema-version marker, mirrored into the GeoPackage
    Automatic, lossless, idempotent on-load migration of older projects (schema 0 → 1.0)
    fiberq_uuid — a stable, cross-system ID on every feature
    Clean plugins.qgis.org security scan (100%); tested on Qt5 and Qt6

You can auto-update in QGIS, or download the folder manually from the GitHub release.

Download User Guide:
https://www.fiberq.net/documentation/

For the full feature list and install instructions, see [fiberq/README.md](fiberq/README.md).

## Community & Feedback

- 💡 **Feature requests & voting (Discussions → Ideas):** https://github.com/vukovicvl/fiberq/discussions/categories/ideas
- 🐛 **Bug reports (GitHub Issues):** https://github.com/vukovicvl/fiberq/issues
- 📊 **Polls (priorities & decisions):** https://github.com/vukovicvl/fiberq/discussions/categories/polls

## Use of Generative AI

Parts of FiberQ are developed with the help of generative AI tools (Anthropic's
Claude) — for example code, tests, refactoring, and documentation. All AI-assisted
changes are reviewed and tested by the maintainer before release, and AI-assisted
commits carry an `Assisted-by:` trailer. FiberQ remains human-authored and
human-reviewed software, released under GPL-3.0-or-later.

## License

GPL-3.0-or-later
