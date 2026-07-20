# Contributing to FiberQ

FiberQ is an open-source QGIS plugin for fibre optic network design (FTTH / GPON
/ FTTx), released under **GPL-3.0-or-later**. It is maintained by one person, so
the fastest way to get a change in is to make it easy to review: small, focused,
and green on the automated gate.

**You do not need to be a programmer to contribute.** Translations, terminology
corrections, documentation fixes and good bug reports are as valuable as code —
see [Translations](#translations) below, which is written for non-programmers.

- Bugs: <https://github.com/vukovicvl/fiberq/issues>
- Ideas and feature voting: <https://github.com/vukovicvl/fiberq/discussions/categories/ideas>

---

## Table of contents

- [Ground rules](#ground-rules)
- [Development setup](#development-setup)
- [The gate: `make lint` and `make test`](#the-gate-make-lint-and-make-test)
- [Branch and pull-request workflow](#branch-and-pull-request-workflow)
- [Qt5 / Qt6 compatibility: the scoped-enum rule](#qt5--qt6-compatibility-the-scoped-enum-rule)
- [Translations](#translations)
  - [English → French glossary](#english--french-glossary)
  - [English → Serbian glossary](#english--serbian-glossary)
- [Licence](#licence)

---

## Ground rules

1. **Open an issue first** for anything substantial. A short conversation before
   the code saves a rejected PR after it.
2. **Check open issues and pull requests** before you start, so two people don't
   fix the same thing.
3. **One concern per pull request.** A bug fix and a refactor in one diff is two
   pull requests.
4. **The lint gate is 0 findings, not "nearly zero".** See below — this mirrors
   the plugins.qgis.org publication scan, so a finding literally blocks release.
5. **No new third-party runtime dependencies.** A QGIS plugin ships as a zip into
   an environment we don't control; the plugin must run on a stock QGIS install
   with only the QGIS/Qt Python bindings available.
6. **No credentials, tokens, connection strings or machine-specific paths** in
   the repository. `fiberq/config.ini` holds placeholders and defaults only.

## Repository layout

Only the `fiberq/` subfolder is the plugin — that is what gets packaged and
shipped. Everything at the repository root is development tooling and is *not*
in the released zip.

```
fiberq/               the plugin package (this is what ships)
  main_plugin.py      entry point
  core/               managers: cable, layer, route, export, undo, data, style, ...
  tools/              map tools: element, route, manhole, slack, select, ...
  ui/                 panels and toolbars
  dialogs/            Qt dialogs
  models/             element_defs.py, color_catalogs.py, schema.py (schema source of truth)
  utils/              helpers, field_aliases.py, uuid_utils.py, compat.py
  addons/             optional feature modules
  i18n/               translation catalogues (.ts sources, .qm compiled)
  styles/ icons/ resources/
tests/                pytest suite
docs/                 schema.md, i18n.md, project-versioning-guide.md
Makefile              all real automation lives here (CI just calls it)
RELEASE.md            the release process
```

Documentation worth reading before a first code change:

- [`docs/schema.md`](docs/schema.md) — the data model, field names and value
  domains. Note that stored field names are mostly the original Serbian names;
  the English text in the attribute table is a display **alias**. Renaming a
  stored field is a data migration, not a cosmetic change.
- [`docs/i18n.md`](docs/i18n.md) — how the translation pipeline works
  (maintainer-facing).
- [`RELEASE.md`](RELEASE.md) — versioning and the release process.

## Development setup

You need **Python 3**, **git**, and — for running the tests — the **QGIS Python
bindings**. QGIS is not pip-installable, so the tests need either a real QGIS
install or the official QGIS Docker image.

### 1. Clone and install the tooling

```bash
git clone https://github.com/vukovicvl/fiberq.git
cd fiberq
make deps        # flake8, bandit, pytest, pytest-qgis
```

On a virtualenv, set `PIP_FLAGS=` (empty) — the default
`--break-system-packages` exists for PEP 668 systems such as recent Debian and
the QGIS containers:

```bash
make deps PIP_FLAGS=
```

### 2. Run the plugin from your working tree

`make install` copies the plugin into your local QGIS profile so you can test it
in a real QGIS:

```bash
make install                                     # Linux default profile
make install QGIS_PROFILE="$APPDATA/QGIS/QGIS3/profiles/default"   # Windows, from Git Bash
```

Then restart QGIS (or use the *Plugin Reloader* plugin). Testing in a **clean
QGIS profile** is strongly recommended before you claim a bug is fixed.

### 3. A note for Windows contributors

The `Makefile` is POSIX shell. Run it from **Git Bash**, not PowerShell or
`cmd`. Alternatively run everything inside the QGIS container (see below).

### 4. Useful targets

```bash
make help        # list everything
make lint        # flake8 + bandit — the publication gate
make test        # pytest
make test-cov    # pytest with coverage
make package     # build dist/fiberq-<version>.zip from committed state
make i18n-stats  # translation progress per locale
```

## The gate: `make lint` and `make test`

### Lint must be 0/0

plugins.qgis.org runs a Security & Quality scan on every uploaded version. A
single finding blocks publication. `make lint` mirrors that scan **exactly**:

```bash
python -m flake8 --isolated --max-line-length=120 --ignore=E501 fiberq tests conftest.py
python -m bandit -r fiberq -q -c pyproject.toml
```

Two things people get wrong here:

- **`--isolated`** means the repo's `.flake8` is deliberately *not* applied for
  the gate. Don't rely on local config to make a finding disappear.
- **Bandit runs at all severities**, not `-ll`. The upstream scanner flags LOW
  findings too — notably `B110` / `B112` (`try: ... except: pass` and
  `except: continue`). A bare swallow will fail the gate.

Your change must add **zero** findings. If you genuinely need an exception,
raise it in the pull request rather than adding a broad ignore.

### Do not remove existing `# noqa` comments

The tree carries roughly 171 inline `# noqa` markers (mostly `W503`/`W504`,
`E402`, `E741`) plus a few deliberate `F841`. These are *tracked, deferred style
debt with a plan*, not litter. Removing them as "cleanup" produces a large,
unreviewable diff that buries the actual change. Leave them alone unless the
issue you are fixing is specifically about them.

### Tests

```bash
make test
```

The suite needs QGIS bindings. If you don't have QGIS available to Python, run
the whole gate inside the official image — this is exactly what CI does:

```bash
docker run --rm -v "$PWD:/src" -w /src \
  -e QT_QPA_PLATFORM=offscreen -e PIP_FLAGS=--break-system-packages \
  qgis/qgis:4.0-trixie \
  bash -c "apt-get update -qq && apt-get install -y --no-install-recommends make >/dev/null && make deps && make lint && make test"
```

CI runs this against **two** images — `qgis/qgis:3.44-trixie` (QGIS 3, Qt5) and
`qgis/qgis:4.0-trixie` (QGIS 4, Qt6). Both must be green.

New behaviour should come with a test. Bug fixes should come with a test that
fails before the fix.

## Branch and pull-request workflow

1. **Branch off `main`.** Never commit substantive work directly to `main`.
   Use a descriptive prefix: `feat/`, `fix/`, `docs/`, `refactor/`, `test/`,
   `chore/`.

   ```bash
   git switch -c fix/slack-length-rounding
   ```

2. **Keep the diff focused.** Match the existing code conventions in the file
   you're editing. Respect `.flake8`.

3. **Run the gate locally before pushing.**

   ```bash
   make lint && make test
   ```

4. **Write a clear commit message.** Conventional-commit style subject, then a
   body explaining *why*:

   ```
   fix(slack): round stored slack length to millimetres

   Slack lengths were stored with full float precision, so two visually
   identical values compared unequal on export. Round at the write site.
   ```

5. **If you used an AI assistant**, disclose it. FiberQ discloses AI assistance
   publicly, and AI-assisted commits carry a trailer:

   ```
   Assisted-by: <tool name> — <one-line summary of what it did>
   ```

   This is a transparency requirement, not a judgement — AI-assisted
   contributions are welcome, reviewed on the same terms as any other.

6. **Open a pull request** describing what changed, why, and how you tested it.
   Mention the QGIS version(s) you tested on. Screenshots help a lot for UI
   changes.

7. **Expect review.** This is a solo-maintained project; review may take a few
   days. Being responsive to comments is the fastest path to merge.

## Qt5 / Qt6 compatibility: the scoped-enum rule

FiberQ supports **QGIS 3.22 LTR (Qt5) through QGIS 4 (Qt6)** from a single code
base. The single most common way to break this is Qt enum access.

In PyQt5, enum members were available directly on the class. In **PyQt6 they are
not** — they live inside their enum's own namespace, and the old form raises
`AttributeError` at runtime. Because the failure happens on attribute access, it
often shows up not as a crash on import but as a tool that silently refuses to
open, so it can survive review and reach users.

**Always use the fully scoped form.** It works on both Qt5 and Qt6.

```python
# WRONG — AttributeError under PyQt6 (QGIS 4)
button.setPopupMode(QToolButton.InstantPopup)
toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
action.setShortcutContext(Qt.ApplicationShortcut)

# RIGHT — works on PyQt5 and PyQt6
button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
```

The pattern is `Class.EnumTypeName.MEMBER`. If you don't know the enum type
name, it is in the Qt documentation for the property you're setting.

Never "simplify" an existing scoped enum back to the unscoped form — the
verbosity is the point.

Other cross-version rules:

- Import Qt through **`qgis.PyQt`** (`from qgis.PyQt.QtWidgets import ...`), not
  `PyQt5`/`PyQt6` directly. QGIS re-exports the right binding for the running
  version.
- Use **`exec()`**, not `exec_()` (removed in PyQt6).
- Where a genuine API difference exists, put the shim in
  `fiberq/utils/compat.py` rather than sprinkling version checks.
- CI does not run a 3.22 image (upstream prunes old images, and `pytest-qgis`
  needs QGIS ≥ 3.34). The 3.22 floor is held by careful API usage and
  `compat.py`, **not** by CI. If you touch Qt or QGIS APIs, say so in the pull
  request so it can be checked manually.

---

## Translations

**This section is for everyone, including non-programmers.** Translating FiberQ
is one of the most useful contributions you can make, and it needs no
development environment, no Python, and no command line.

FiberQ is written in English. Every piece of text you see in the plugin —
button labels, menu entries, tooltips, error messages — can be translated into
another language. Translating means filling in the missing text in one file.

> **Doing a full translation?** Read
> **[`docs/TRANSLATING.md`](docs/TRANSLATING.md)** — a numbered, step-by-step
> guide that assumes no Git, no terminal and no XML: installing Qt Linguist,
> what each screen does, how far along you are, and how to send the work back.
> This section is the summary; that document is the walkthrough.

### What is a `.ts` file?

A `.ts` file is a plain-text **translation catalogue**: a list of every English
phrase in the plugin, each with an empty slot for your translation. They live in
`fiberq/i18n/` and are named after the language, for example:

- `fiberq/i18n/fiberq_fr.ts` — French
- `fiberq/i18n/fiberq_sr.ts` — Serbian

Inside, each phrase looks like this:

```xml
<message>
    <location filename="../ui/quick_toolbar.py" line="48" />
    <source>Place Manhole</source>
    <translation type="unfinished"></translation>
</message>
```

- `<location>` is a bookmark to the line of source the phrase came from. It is
  regenerated automatically — **ignore it**.
- `<source>` is the English text. **You never change this.**
- `<translation>` is where your text goes. Note that the empty slot is a
  **self-closing** tag ending in ` />`, with no separate closing tag — that is
  the exact form used throughout FiberQ's catalogues. You replace the whole tag:

```xml
<message>
    <location filename="../ui/quick_toolbar.py" line="48" />
    <source>Place Manhole</source>
    <translation>Placer une chambre de tirage</translation>
</message>
```

When you fill in a translation, the `type="unfinished"` marker must disappear
along with the self-closing form — it is what marks the entry as still to-do,
and anything still carrying it is skipped when the catalogue is compiled. (Qt
Linguist, below, does all of this for you automatically.)

Don't worry about entries you can't translate. Leave them untouched and
translate what you can — a partial translation is genuinely useful, and the
plugin simply falls back to English for anything missing.

### The three inviolable rules

1. **Never edit the `<source>` text.** It is the key that links the translation
   to the running program. Change one character and that phrase silently stops
   being translated — with no error message. If the English is wrong, open an
   issue about the English; don't fix it in the `.ts` file.

2. **Keep placeholders exactly as they are.** Some phrases contain markers that
   the program replaces with real values at runtime — `%1`, `%2`, `{n}`,
   `{name}`, `%s`. They must appear in your translation exactly as written,
   including case and braces. You may move them to wherever the sentence needs
   them.

   ```
   source:      Imported %1 features into %2
   correct:     %1 entités importées dans %2
   correct:     Dans %2, %1 entités importées      (reordered — fine)
   WRONG:       %I entités importées dans %2       (changed the placeholder)
   WRONG:       Des entités importées              (dropped the placeholders)
   ```

   Also keep any `&` in menu labels (it marks the keyboard shortcut letter) and
   any trailing `...` or `:` — those are part of the interface convention.

3. **Don't compile anything.** You may see mention of `.qm` files. Those are the
   compiled binary version that the plugin actually loads, and the **maintainer
   generates them**. Send or commit only the `.ts` file. If you try to build the
   `.qm` yourself you will need Qt tooling you almost certainly don't want to
   install.

### Three ways to contribute a translation

All three are welcome. They are not equally easy, so they are listed best-first.

**1. With Qt Linguist (recommended — and the only sensible route for a full translation)**

Qt Linguist is a free graphical editor made exactly for this. It shows the
English on one side and a box for your translation on the other, **warns you
when placeholders don't match**, clears the `unfinished` marker for you, and
tracks your progress. It removes every opportunity to break the XML by hand.

- Linux (Debian/Ubuntu): `sudo apt install linguist-qt6` — or
  `sudo apt install qttools5-dev-tools` for the Qt5 build. Either opens FiberQ's
  `.ts` files fine.
- Windows/macOS: it ships with the free Qt installer
  (<https://www.qt.io/download-qt-installer>); it is also bundled with many
  QGIS installations

Open the `.ts` file, translate, save. **Do not** use *File → Release* — that
produces the `.qm` file, which is the maintainer's job. Then send the `.ts` file
back by either of the other two methods.

[`docs/TRANSLATING.md`](docs/TRANSLATING.md) walks through this route screen by
screen, including the keyboard shortcut you will use for every string.

**2. In your web browser (no software to install — but only for small fixes)**

1. Open the file on GitHub, e.g.
   `https://github.com/vukovicvl/fiberq/blob/main/fiberq/i18n/fiberq_fr.ts`
2. Click the **pencil icon** (✏️, "Edit this file") in the top right.
3. Fill in the `<translation>` slots.
4. Scroll to the bottom, write a short description of what you did, choose
   **"Create a new branch for this commit and start a pull request"**, and click
   **Propose changes**.

You need a free GitHub account. Be clear about the trade-off: this is
hand-editing XML in a browser text box, with **no placeholder validation and no
progress tracking**. It is fine for correcting a term or finishing a handful of
strings; for a catalogue of a hundred-plus entries it is tedious and
mistake-prone. Use Qt Linguist instead.

**3. Email it to the maintainer**

If git and GitHub aren't your thing, that is completely fine. Download the
`.ts` file, edit it, and email it back — the maintainer will commit it with
credit to you. Open an issue using the
[translation issue template](https://github.com/vukovicvl/fiberq/issues/new/choose)
to get in touch first.

### Starting a brand-new language

Open an issue with the
[translation template](https://github.com/vukovicvl/fiberq/issues/new/choose)
saying which language you want to add. The maintainer generates the empty
catalogue for you and points you at it — you do not have to create the file
yourself.

### Machine translation

Please don't submit raw machine-translated output. The plugin is full of
specialised fibre-optic terminology that translation engines get confidently and
consistently wrong (see the glossaries below — this is exactly why they exist).
Using a machine translation as a *first draft that you then review and correct as
someone who knows the field* is fine and sensible; submitting untouched engine
output is not, because it looks finished while being unusable.

### Credit and licence

- Translations are part of FiberQ and are released under the same
  **GPL-3.0-or-later** licence as the rest of the plugin. By contributing one you
  agree to that.
- **Translators are credited** in the README and in the release notes for the
  version their work first ships in. If you'd prefer a specific name, handle, or
  no credit at all, just say so in the pull request or issue.

---

### English → French glossary

**The French column is yours to decide, not ours.** The maintainer does not speak
French and is not in a position to judge these terms. They are collected here as a
*starting point* — a shortlist of what appears in French/EU FTTH practice (Arcep,
the Objectif Fibre guides) so you are not starting from a blank page.

**If your professional experience says a term is wrong, it is wrong — use yours.**
We would rather have the word a French fibre engineer actually says on site than
the word a document says. Tell us what you changed and we will correct the table.

**The column that matters is the last one.** "What it means in FiberQ" is the
maintainer's own domain knowledge, and it is the part you can rely on. Translate
from the *meaning*, not from the English word — several English strings in this
plugin are ambiguous or imprecise, and a few are outright legacy wording.

The same applies to the acronyms: **ODF, OTB, TO, TB, PBO, PM, NRO** are kept as
acronyms in the interface. If French practice uses a different acronym for the
same object, use it. If it keeps the English one, keep it.

#### Structures and civil works

| English | Suggested French *(your call)* | What it means in FiberQ |
|---|---|---|
| manhole / chamber | **chambre de tirage** | The standard term. Small ones may be *regard*. Never *trou d'homme*. |
| duct | **fourreau** | Also *conduite*. The buried conduit itself. |
| subduct | **sous-fourreau** | Both are in use; *micro-conduite* / *microgaine* for microduct. Please pick one and stay consistent. |
| trench | **tranchée** | Trenching = *ouverture de tranchée*; micro-trenching = *micro-tranchée*. |
| pole | **poteau** | *appui* is the generic word for any support (shared poles = *appuis communs*). |
| cabinet | **armoire (de rue)** | The FTTH street cabinet is the **SRO** (*sous-répartiteur optique*), which houses the **PM**. |
| aerial | **aérien** | *en aérien*, *réseau aérien*. |
| underground | **souterrain** | *en souterrain*; *enterré* for directly buried. |

#### Cables and network segments

| English | Suggested French *(your call)* | What it means in FiberQ |
|---|---|---|
| feeder / transport cable | **câble de transport** | The NRO → PM segment. *collecte* is the upstream backhaul, a different thing. |
| distribution cable | **câble de distribution** | The PM → PBO segment. |
| drop cable | **câble de branchement** | The PBO → subscriber segment; the operation is *le raccordement*. |
| route | **tracé** | The physical path/alignment. *cheminement* for the cable's run. |
| span | **portée** | *portée* = the aerial span between two poles. If the plugin means a cable **section** between two points, it is *tronçon* or *section*. Please check which sense the string is used in and tell us. |
| slack / loop | **lovage** | *lovage* = the coiling operation, *love* = the coil itself, *réserve de câble* / *sur-longueur* = the stored spare length. As a UI label for a stored reserve, *love* or *réserve* is likely better than *lovage*. |
| blown fibre | **fibre soufflée** | The installation technique is *soufflage*, sometimes *portage*. Confirm which term your region uses. |
| fibre count | **nombre de fibres** | Also *capacité*. A 144-fibre cable is a *câble 144 FO*. |
| breakpoint | **point de coupure** | Ambiguous in English. A **fault** in the fibre = *coupure* / *rupture de fibre*; a deliberate **split point on a route** = *point de coupure*. Please check which the plugin means. |

#### Equipment

| English | Suggested French *(your call)* | What it means in FiberQ |
|---|---|---|
| splice | **soudure** | Fusion splicing; the machine is a *soudeuse*. *épissure* is the formal term and also correct. |
| splice closure | **boîtier de protection d'épissure (BPE)** | BPE is the universally used acronym. Inline closures may be *manchon*. |
| splitter | **coupleur** | e.g. *coupleur 1:8*. Not *diviseur*, not *séparateur*. |
| ODF — Optical Distribution Frame | **répartiteur optique** | The frame at the NRO. An individual drawer/tray is a *tiroir optique* — confirm which level the plugin's "ODF" means. |
| patch panel | **tiroir optique** | *panneau de brassage* is the structured-cabling term. Overlaps with ODF above; the two need to be distinguished consistently. |
| OLT | **OLT** | Not translated. Housed at the NRO. |
| ONT | **ONT** | Not translated. The subscriber socket is the **PTO** (*prise terminale optique*); the in-home termination device is the **DTIo**. |
| attenuation | **affaiblissement** | The industry term. *affaiblissement linéique* for dB/km; the link budget is the *bilan optique*. |

#### Coverage and architecture

| English | Suggested French *(your call)* | What it means in FiberQ |
|---|---|---|
| service area | **zone de desserte** | French FTTH regulation says *zone arrière du PM* (**ZAPM**) or *zone arrière du PBO* (**ZAPBO**) for the area served by a specific node. *zone de desserte* is the safe general term. |
| FTTH | **FTTH** | Keep the acronym; expanded as *fibre jusqu'au domicile* / *fibre jusqu'à l'abonné*. |
| GPON | **GPON** | Not translated. |
| PON | **PON** | Not translated; expanded as *réseau optique passif*. |

#### French FTTH architecture reference

These acronyms have no English equivalent but are what a French user expects to
see. Use them where the plugin's concept maps onto one:

| Acronym | Expansion | Roughly |
|---|---|---|
| **NRO** | Nœud de Raccordement Optique | Central office / head end; where the OLT lives |
| **PM** | Point de Mutualisation | The mutualisation / handover point |
| **SRO** | Sous-Répartiteur Optique | The street cabinet housing the PM |
| **PBO** | Point de Branchement Optique | The drop point serving nearby premises |
| **PTO** | Prise Terminale Optique | The subscriber's optical wall socket |
| **BPE** | Boîtier de Protection d'Épissure | Splice closure |
| **FO** | Fibre Optique | Used as a unit: *câble 144 FO* |

---

### English → Serbian glossary

**Status: stub — needs a fibre-literate Serbian speaker.**

Unlike the French table, this one is not a researched recommendation. It is
seeded from terms that are **already in the FiberQ code base**, which makes them
authentic but not necessarily the terms a translator would choose for a user
interface.

Two sources, and the difference matters:

- **`fiberq/utils/helpers.py`** (`_TRANSLATION_MAP`) — the deprecated
  phrase-map from the plugin's original bilingual UI. These are real UI strings.
- **[`docs/schema.md`](docs/schema.md)** — the legacy *layer and field* names.
  These are the original database names and are the strongest evidence of the
  domain vocabulary actually used in practice, but they are data identifiers
  rather than polished UI labels.

Both are **Serbian in Latin script**. Whether the shipped translation should be
Latin or Cyrillic (or both, as `sr_Latn` / `sr_Cyrl`) is an open question — if
you take this on, please state your preference in the issue.

| English | Serbian | Source / confidence |
|---|---|---|
| manhole | **okno** (pl. *okna*) | schema legacy layer `OKNA`; fields `broj_okna`, `tip_okna` — attested |
| duct / pipe | **cev** (pl. *cevi*) | schema legacy `PE cevi`, `Prelazne cevi` — attested |
| subduct / tube | **cevčica** | schema field `broj_cevcica` = "Number of ducts" — attested |
| splice closure / joint closure | **nastavak** (pl. *nastavci*) | schema legacy layer `Nastavci` — attested |
| pole | **stub** (pl. *stubovi*) | schema legacy layer `Stubovi` — attested |
| cabinet | **ormar** | element type "OD cabinet" = *od ormar* — attested |
| route | **trasa** | schema legacy layer `Trasa` — attested |
| cable | **kabl** (pl. *kablovi*) | schema legacy `Kablovi_vazdusni` / `Kablovi_podzemni` — attested |
| aerial | **vazdušni** / *vazdušna* | schema value map `Aerial → vazdusna` — attested |
| underground | **podzemni** / *podzemna* | schema value map `Underground → podzemna` — attested |
| slack / reserve | **rezerva** | `_TRANSLATION_MAP`: *Završna rezerva (prečica)* = "End slack (shortcut)"; legacy layer `Opticke_rezerve` — attested |
| service area / region | **rejon** | `_TRANSLATION_MAP`: *Kreiraj rejon* = "Create region", *Rejon* = "Region"; legacy layer name `Rejon` — attested |
| object / building | **objekat** (pl. *objekti*) | schema legacy layer `Objekti` — attested |
| fibre | **vlakno** (pl. *vlakna*) | schema field `broj_vlakana` = "Number of fibers" — attested |
| fibre break | **prekid vlakna** | schema legacy layer `Prekid vlakna` — attested |
| fibre count | **broj vlakana** | schema field `broj_vlakana` — attested |
| attenuation | **slabljenje** | schema field `slabljenje_dbkm` = "Attenuation [dB/km]" — attested |
| optical | **optički** | schema value map `Optical → opticki` — attested |
| feeder / backbone | **glavni** | schema value map `Backbone → glavni` — attested (adjective, not a noun) |
| distribution | **distributivni** | schema value map `Distribution → distributivni` — attested (adjective) |
| drop | **razvodni** | schema value map `Drop → razvodni` — attested (adjective) |
| splice | | not in the code base — likely *spoj* / *spajanje* / *varenje vlakana* |
| splitter | | not in the code base — likely *splliter* / *razdelnik* / *optički razdelnik* |
| ODF | | present only as the acronym "ODF" |
| patch panel | | present only as the English "Patch panel" |
| distribution cable | | compose from *kabl* + *distributivni* |
| feeder / transport cable | | compose from *kabl* + *glavni* |
| drop cable | | compose from *kabl* + *razvodni* |
| trench | | not in the code base — likely *rov* |
| blown fibre | | not in the code base — likely *uduvavanje vlakna* |
| span | | not in the code base; same English ambiguity as in the French table (aerial span vs. cable section) |
| breakpoint | | not in the code base; same ambiguity as in the French table |
| OLT / ONT / FTTH / GPON / PON | | almost certainly kept as the English acronyms, as in French — please confirm |

If you correct or extend this table, please do it in the same pull request as
the `.ts` file so the two stay consistent.

---

## Licence

FiberQ is licensed under the **GNU General Public License v3.0 or later**
(GPL-3.0-or-later); see [`LICENSE`](LICENSE).

By contributing — code, documentation, or translations — you agree that your
contribution is licensed under the same terms. New source files should carry the
standard header used elsewhere in the tree:

```python
"""
FiberQ - <short module description>

Copyright (C) Vladimir Vukovic
SPDX-License-Identifier: GPL-3.0-or-later

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.
"""
```

Do not weaken, remove, or relicense the GPL headers.
