# FiberQ

Open-source QGIS plugin for fiber optic network design (FTTH / GPON / FTTx).

**Latest release: v1.6.0 — 08.11.2026.** Added on GitHub as a new release.

v1.6.0 — WP4 · Performance and reliability

On a large design, the **Optical Schematic View**, the list of **latent
elements**, **route correction**, **Generate terminal slacks**, placing a slack,
FiberQ's own snapping in the placement tools, the undo record after every
placement and **Lay cable** now use spatial indexes and batched reads instead of
scanning every feature. And the operations that save, export, import or migrate
data now say when they fail, and why, instead of failing silently or reporting
success.

    On an 88,622-feature test city, the Optical Schematic View opens in 11 s, not 16 min 39 s
    The list of latent elements opens there in 5 s; in 1.5.0 it did not finish in 30 minutes
    Measured against 1.5.0 on QGIS 3.44 and 4.0, with the method, the raw data and the limits
    One message per failed operation; the details are in Log Messages > FiberQ
    A test stops silent error handlers from growing back

Guides: [performance on large projects](docs/performance.md) ·
[the 1.6.0 re-check, replayed in QGIS](docs/qa/1.6.0/)

Earlier: [moving a design between tools](docs/interchange-guide.md) ·
[the specification](docs/interchange-format.md) ·
[field mapping](docs/interchange-mapping.md) ·
[validating a design](docs/validation-guide.md) ·
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
  experience. Partial translations are welcome: every string you finish ships,
  and anything you leave stays in English. Open a
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
