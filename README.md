# FiberQ

Open-source QGIS plugin for fiber optic network design (FTTH / GPON / FTTx).

**Latest release: v1.4.0 — 19.08.2026.** Added on GitHub as a new release.

v1.4.0 — WP2 · Validation & reporting

**Validate project** runs fourteen checks over the whole design — topology and
connectivity, referential integrity, feature identity, required attributes, value
domains, length coherence, CRS consistency and geometry health — and lists what it
finds in a dockable panel you can filter, click through, and export.

    Fourteen rules, one command; filter by severity, layer or rule, click any issue to jump to it
    Export the run as HTML (handover), JSON (tooling) or CSV (spreadsheets)
    Lengths now measured on the project ellipsoid — true ground metres, not map units
    "Recalculate lengths…" repairs existing projects, showing every change before writing
    Now translatable; clean plugins.qgis.org security scan; tested on Qt5 and Qt6

Guides: [validating a design](docs/validation-guide.md) ·
[rule reference](docs/validation-rules.md) ·
[demo project](docs/samples/) · [project versioning](docs/project-versioning-guide.md)

You can auto-update in QGIS, or download the folder manually from the GitHub release.

Download User Guide:
https://www.fiberq.net/documentation/

For the full feature list and install instructions, see [fiberq/README.md](fiberq/README.md).

## Community & Feedback

- 💡 **Feature requests & voting (Discussions → Ideas):** https://github.com/vukovicvl/fiberq/discussions/categories/ideas
- 🐛 **Bug reports (GitHub Issues):** https://github.com/vukovicvl/fiberq/issues
- 📊 **Polls (priorities & decisions):** https://github.com/vukovicvl/fiberq/discussions/categories/polls
- 🌍 **Translate FiberQ into your language:** [docs/TRANSLATING.md](docs/TRANSLATING.md)
  — a step-by-step guide that assumes no programming, Git or terminal
  experience. Partial translations are welcome and ship as-is; anything you
  leave stays in English. Open a
  [translation issue](https://github.com/vukovicvl/fiberq/issues/new?template=translation.yml)
  to claim a language.

## Support FiberQ

FiberQ is open source (GPL-3.0) and developed with support from the **NLnet NGI0
Commons Fund**. Sponsorship keeps it maintained and moving beyond that grant —
independent of any single funder.

- ❤️ **Sponsor development (GitHub Sponsors):** https://github.com/sponsors/vukovicvl
- 🌐 **Other ways to give (one-off / card):** https://www.fiberq.net/donate/

## Use of Generative AI

Parts of FiberQ are developed with the help of generative AI tools (Anthropic's
Claude) — for example code, tests, refactoring, and documentation. All AI-assisted
changes are reviewed and tested by the maintainer before release, and AI-assisted
commits carry an `Assisted-by:` trailer. FiberQ remains human-authored and
human-reviewed software, released under GPL-3.0-or-later.

## License

GPL-3.0-or-later
