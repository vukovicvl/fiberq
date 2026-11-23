# FiberQ

Open-source QGIS plugin for fiber optic network design (FTTH / GPON / FTTx).

**Latest release: v1.7.0.** Added on GitHub as a new release.

v1.7.0 — WP5 · Automated tests and CI

Before each release, FiberQ's whole test suite now runs on five QGIS versions,
from 3.22 LTR to 4.2, in the official Linux images, and the plugin is installed
from a zip and used in the real QGIS desktop on 3.40 and 4.2. The pipeline that
does it is plain scripts in `ci/`, which anyone with git and docker or podman
can run, with or without a forge; they are tested on Linux x86-64 with Docker.

    2,554 tests on each of QGIS 3.22, 3.40, 3.44, 4.0 and 4.2
    The real QGIS desktop on 3.40 and 4.2: install from a zip, a short workflow, a reload
    WP5's new tests raise the statement coverage of the core logic from 71.8% to 76.9%
    The tests that need no QGIS or GDAL run on their own, in a plain Python image, in under a minute
    GitHub runs it on every push: three QGIS versions, and all five on release branches and tags
    GitLab runs part of it for main, release branches and tags

Guides: [running the pipeline](ci/README.md) · [the release process](RELEASE.md) ·
[what the tests cover](docs/testing.md) · [reporting a security problem](SECURITY.md)

Earlier: [performance on large projects](docs/performance.md) ·
[the 1.6.0 re-check, replayed in QGIS](docs/qa/1.6.0/) ·
[moving a design between tools](docs/interchange-guide.md) ·
[the specification](docs/interchange-format.md) ·
[field mapping](docs/interchange-mapping.md) ·
[validating a design](docs/validation-guide.md) ·
[rule reference](docs/validation-rules.md) ·
[demo project](docs/samples/) · [project versioning](docs/project-versioning-guide.md)

You can auto-update in QGIS, or download the folder manually from the GitHub release.

Download User Guide:
https://www.fiberq.net/documentation/

For the full feature list and install instructions, see [fiberq/README.md](fiberq/README.md).

## Tests and releases

Every push to GitHub runs FiberQ's checks and tests, on three QGIS versions (all five for release
branches and tags), and GitLab runs part of them for `main`, release branches and tags. Anyone can run
the same pipeline without a forge, with git and docker or podman (it is tested on Linux x86-64 with
Docker): [ci/README.md](ci/README.md) explains how, and lists
[where to see the runs](ci/README.md#where-to-see-the-runs). The release process is in
[RELEASE.md](RELEASE.md). [docs/testing.md](docs/testing.md) says what the tests cover and how to run
each tier.

## Community & Feedback

- 💡 **Feature requests & voting (Discussions → Ideas):** https://github.com/vukovicvl/fiberq/discussions/categories/ideas
- 🐛 **Bug reports (GitHub Issues):** https://github.com/vukovicvl/fiberq/issues
- 🔒 **Security problems:** report them privately by e-mail, as [SECURITY.md](SECURITY.md) says, not in
  an issue
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
