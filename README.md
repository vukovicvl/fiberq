# FiberQ

Open-source QGIS plugin for fiber optic network design (FTTH / GPON / FTTx).

**Latest release: v1.5.0 — 17.09.2026.** Added on GitHub as a new release.

v1.5.0 — WP3 · An open interchange format

A fibre design is not a pile of points and lines. A slack loop belongs to a
*particular* cable; a cable passes *through* particular manholes, in order;
cables are grouped into named routes. An ordinary GeoPackage export drops all of
that, because those relationships live in identifiers local to one QGIS project.
**Export interchange bundle** carries them, keyed by an identity that survives
the trip, and **Import interchange bundle** reads them back.

    A GeoPackage any GIS tool can open, or a folder of GeoJSON files per element type
    Cable references, pass-through elements and cable groupings, keyed by fiberq_uuid
    An element type, attribute or side-car table FiberQ cannot model survives a round trip
    Nothing is reclassified to the nearest familiar type, and nothing is silently dropped
    Published as a CC-BY-4.0 specification anyone can implement, with a conformance list

Guides: [moving a design between tools](docs/interchange-guide.md) ·
[the specification](docs/interchange-format.md) ·
[field mapping](docs/interchange-mapping.md)

Earlier: [validating a design](docs/validation-guide.md) ·
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
