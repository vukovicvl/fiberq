# Translating FiberQ — a step-by-step guide

Welcome, and thank you. This guide walks you through translating FiberQ from
start to finish. It assumes **no programming knowledge** and no experience with
Git, GitHub, or a terminal.

You know fibre networks. That is the part that cannot be automated. Everything
else in this document is mechanical, and we will go through it one step at a
time.

---

## Contents

- [What you are signing up for](#what-you-are-signing-up-for)
- [The three inviolable rules](#the-three-inviolable-rules)
- [What the file looks like](#what-the-file-looks-like)
- [Route A — Qt Linguist (recommended)](#route-a--qt-linguist-recommended)
- [Route B — the GitHub web editor](#route-b--the-github-web-editor)
- [Sending your work back](#sending-your-work-back)
- [Where each string appears in the plugin](#where-each-string-appears-in-the-plugin)
- [Translator notes, and when to ask](#translator-notes-and-when-to-ask)
- [Seeing your work in the plugin](#seeing-your-work-in-the-plugin)
- [Troubleshooting](#troubleshooting)
- [Credit and licence](#credit-and-licence)

---

## What you are signing up for

**The file:** `fiberq/i18n/fiberq_fr.ts` for French. (Serbian is
`fiberq_sr.ts`; other languages follow the same pattern.)

**The size:** **169 strings**, all currently untranslated. They are short — menu
entries, button labels, tooltips, a handful of error messages. The longest is
one sentence.

**The time:** budget around **9 hours** for a careful full pass. That is an
honest estimate, not a sales pitch. Much of FiberQ's vocabulary is specialised,
and the right French term often needs a moment's thought rather than a
dictionary lookup. Some strings will take you five seconds; a dozen will take
five minutes each.

**You do not have to finish.** This is the most important sentence in this
guide. The build step that turns your file into something the plugin loads
simply **skips** anything you have not translated, and those strings stay in
English. Nothing breaks. Nothing looks half-broken. A user just sees a mostly
French interface with some English left in it.

So: translate 20 strings and stop, and those 20 strings ship. Translate the
toolbar and menus only, and the toolbar and menus ship. Partial work is
genuinely useful and genuinely welcome. Please do not let "169" stop you from
starting.

If you would rather work in stages, the section
[Where each string appears in the plugin](#where-each-string-appears-in-the-plugin)
tells you which groups are most visible, so you can do the high-value ones
first.

---

## The three inviolable rules

Three things must not happen. Everything else is recoverable.

### Rule 1 — never change the text inside `<source>`

The English text is the **lookup key**. The running plugin asks for the
translation of the exact English phrase. Change one character — even a stray
space — and that phrase silently stops being translated. There is no error
message. It just quietly reverts to English.

```xml
<!-- CORRECT: source untouched, translation filled in -->
<source>Place Manhole</source>
<translation>Placer une chambre de tirage</translation>
```

```xml
<!-- WRONG: the source was edited. This string will never translate again. -->
<source>Placer une chambre de tirage</source>
<translation>Placer une chambre de tirage</translation>
```

If you spot a mistake in the **English**, that is a real and useful find — but
please open an issue about it rather than fixing it in the `.ts` file.

### Rule 2 — placeholders must survive exactly

Some phrases contain markers in curly braces that the plugin replaces with real
values while it runs. FiberQ currently uses these ten:

`{count}` `{details}` `{ext}` `{label}` `{language}` `{layer}` `{name}`
`{path}` `{scope}` `{shortcut}`

They must appear in your translation **spelled exactly as in the English**,
braces and all, in lowercase. You may **move** them anywhere the French sentence
needs them — word order is yours. You may not rename, translate, or drop them.

```
source:    Imported {count} points into layer '{layer}'!
CORRECT:   {count} points importés dans la couche '{layer}' !
CORRECT:   Dans la couche '{layer}', {count} points importés !     (reordered — fine)
WRONG:     {nombre} points importés dans la couche '{couche}' !    (renamed — breaks)
WRONG:     Des points importés dans la couche !                    (dropped — breaks)
```

A dropped or renamed placeholder is worse than a missing translation: the plugin
can raise an error when it tries to fill it in. Qt Linguist checks this for you
automatically (see Route A) — one more reason to prefer it.

Two smaller details in the same family:

- **`\n` means a line break.** Keep it. `Language set to {language}.\n\nLanguage
  will change when QGIS restarts.` has a blank line in the middle, and the two
  `\n\n` are what produce it.
- **Keep trailing `…` and `:`.** `Add drawing…` keeps its ellipsis
  (`Ajouter un dessin…`) — in Qt convention it signals "this opens a dialog".

You may also encounter `%1`, `%2` or `%n` in Qt projects generally. FiberQ's
current file has none, but if one appears later, treat it under exactly this
rule.

### Rule 3 — do not compile anything, and do not touch `.qm` files

You will see files named `fiberq_fr.qm` next to the `.ts` file. Those are the
compiled binary catalogues that the plugin actually loads, and **the maintainer
generates them**. You never need to.

Send back the `.ts` file only. In Qt Linguist specifically, this means: use
**File → Save**, and **never File → Release**.

---

## What the file looks like

Open the file in any text editor and you will see blocks like this. This is
copied verbatim from the real `fiberq/i18n/fiberq_fr.ts` in this repository:

```xml
<context>
    <name>CableLayingUI</name>
    <message>
        <location filename="../ui/cable_ui.py" line="33" />
        <source>Underground</source>
        <translation type="unfinished"></translation>
    </message>
```

Reading that:

- `<context>` … `<name>` — the group this string belongs to. Groups are named
  after the part of the plugin they come from. More on these
  [below](#where-each-string-appears-in-the-plugin).
- `<location .../>` — a bookmark telling the maintainer's tools which line of
  which source file the phrase came from. **Ignore it entirely.** It is
  regenerated automatically and you never edit it.
- `<source>` — the English. **Never edit** (Rule 1).
- `<translation type="unfinished"></translation>` — the empty slot, waiting for you.

### The `unfinished` marker

`type="unfinished"` is the to-do flag. Every one of the 169 entries currently
carries it. Note the exact shape in this file: it is **self-closing**, a single
tag ending in ` />` with no separate closing tag.

To translate the entry by hand, you replace that whole self-closing tag with a
normal opening tag, your text, and a closing tag:

```xml
<!-- BEFORE -->
        <source>Underground</source>
        <translation type="unfinished"></translation>
```

```xml
<!-- AFTER -->
        <source>Underground</source>
        <translation>Souterrain</translation>
```

Notice that **`type="unfinished"` is gone**. That is what marks the entry as
done. If you leave it in place, the build step treats the entry as still
outstanding and skips it — your text would not appear in the plugin.

**Qt Linguist does all of this for you.** It removes the marker the moment you
confirm a translation. This is precisely why Route A is recommended: hand-editing
XML is where mistakes come from.

---

## Route A — Qt Linguist (recommended)

Qt Linguist is a free desktop program built for exactly this job. It hides the
XML completely, shows English on one side and your translation on the other,
warns you when a placeholder does not match, and tracks how far along you are.

### Step 1 — install it

- **Linux (Debian, Ubuntu, Mint):** open a terminal and run
  `sudo apt install linguist-qt6`
  (The older Qt5 build, `sudo apt install qttools5-dev-tools`, opens these files
  equally well. Either is fine.)
- **Windows or macOS:** Qt Linguist ships with the free Qt online installer,
  <https://www.qt.io/download-qt-installer>. It is also bundled with many QGIS
  installations, so it may already be on your machine — search your programs for
  "Linguist" before installing anything.

### Step 2 — get the file

If Git means nothing to you, do not install Git. Just download the one file:

1. Go to
   <https://github.com/vukovicvl/fiberq/blob/main/fiberq/i18n/fiberq_fr.ts>
2. Click the **Download raw file** button (the download arrow, top right of the
   file view).
3. Save it somewhere you will find it again. Keep the name `fiberq_fr.ts`.

### Step 3 — open it

Start Qt Linguist. Choose **File → Open**, select `fiberq_fr.ts`.

If it asks you to confirm the target language, choose **French**, region
**France** (or your own region — FiberQ loads any `fr_*` variant from the same
file, so the region does not affect anything).

### Step 4 — understand the window

- **Left panel:** the list of context groups (`FiberQPlugin`, `RoutingUI`, …)
  with the strings inside each. Click a group to open it.
- **Middle:** the currently selected English phrase, and directly under it the
  box where you type the French.
- **Right / bottom:** *Phrases and guesses* — suggestions from similar strings.
  Useful, but check every one; they are not authoritative.
- **Beside the source string:** any **translator note** the maintainer has left
  for you. Read these — see
  [Translator notes](#translator-notes-and-when-to-ask).

### Step 5 — translate

1. Click the first string.
2. Type the French in the translation box.
3. Press **Ctrl+Enter**. This marks the string as done **and jumps to the next
   untranslated one**. It is the whole workflow — you will use it 169 times.
4. Repeat.

If you want to leave a string for later, just click past it without pressing
Ctrl+Enter. It stays marked as unfinished, which is exactly right.

### Step 6 — read the status marks

A small icon sits to the left of every string:

- **Yellow / question mark** — untranslated, or translated but still marked
  unfinished. Not shipped.
- **Green / check mark** — translated and accepted. This is what Ctrl+Enter
  produces. Shipped.
- **Red or orange warning triangle** — Linguist has found a problem, almost
  always a **placeholder mismatch**: your text is missing a `{name}`, or has one
  the English does not. Fix it before moving on. This is Rule 2 catching you
  automatically, and it is worth more than any amount of proofreading.

The status bar shows your running total, so you always know where you are.

### Step 7 — save

Press **Ctrl+S**, or **File → Save**.

**Do not use File → Release.** That produces a `.qm` file, which is the
maintainer's job (Rule 3). Saving is all you ever need to do.

You can close Linguist and come back tomorrow. Your progress, including the
green/yellow marks, is stored in the `.ts` file itself.

---

## Route B — the GitHub web editor

You can edit the file directly in your web browser with no software at all. Be
aware of what this actually means before choosing it:

- You are hand-editing **XML in a browser text box**.
- There is **no placeholder checking**, no progress tracking, no
  accept-and-advance. Every one of Rules 1–3 is yours to enforce by eye.
- For 169 entries this is genuinely tedious and mistake-prone. Route A exists
  precisely to avoid it.

**Use Route B for small fixes** — correcting a term, finishing a handful of
strings someone else left. For a full translation, please use Qt Linguist.

If you still want it:

1. Sign in to GitHub (a free account is enough).
2. Open
   <https://github.com/vukovicvl/fiberq/blob/main/fiberq/i18n/fiberq_fr.ts>
3. Click the **pencil icon** (✏️, tooltip "Edit this file") near the top right
   of the file box. GitHub will offer to make you a copy of the project — accept;
   this is normal and expected.
4. Scroll to the entry you want. Replace
   `<translation type="unfinished"></translation>`
   with
   `<translation>Votre texte</translation>`
   — exactly as shown in
   [The `unfinished` marker](#the-unfinished-marker) above.
5. When you are done, click **Commit changes…** at the top right.
6. Write one line describing what you did (e.g. "French: translate routing
   toolbar").
7. Choose **Create a new branch for this commit and start a pull request**, then
   click **Propose changes**, then **Create pull request**.

That is it. The maintainer takes it from there.

---

## Sending your work back

Any of these is fine. Pick whichever is least friction for you — none is
considered more "proper" than another.

**Email — the simplest.** Attach the `fiberq_fr.ts` file to a message to
**<vukovicvlmma@gmail.com>** and say which language it is. The maintainer commits
it with credit to you. If Git or GitHub is a barrier of any size, use this.
There is no penalty and no lesser status for it.

**Open an issue and attach the file.** Use the
[translation issue template](https://github.com/vukovicvl/fiberq/issues/new/choose)
and drag the `.ts` file into the comment box. This has the advantage of giving
you a public place to ask terminology questions along the way.

**A pull request**, if you already know Git. Branch, commit the `.ts` file only
(never the `.qm`), and open a PR.

Whichever you choose, **send in batches if you like**. Finishing the toolbar and
sending it is better than holding 169 half-done strings for a month.

---

## Where each string appears in the plugin

The 169 strings are grouped by which part of the plugin they come from. The
group name is the `<context>` name in the file and the folder name in Qt
Linguist's left panel.

Here are the real groups in `fiberq_fr.ts`, with counts, roughly in the order
worth doing them:

| Group | Strings | What it covers |
|---|---:|---|
| `FiberQ` | 12 | The **main toolbar buttons** — Place Pole, Place Manhole, Create Route, Aerial/Underground Cable, ODF, OTB, TO, Optical Slack, Undo. The most visible text in the whole plugin. |
| `RoutingUI` | 13 | The **Routing** toolbar group: creating, merging, importing and correcting routes, breakpoints, GeoPackage auto-save. |
| `CableLayingUI` | 6 | The **Cable laying** group: Underground, Aerial, and the cable classes Backbone / Distributive / Drop. Terminology-heavy — the glossary matters most here. |
| `ObjectsUI` | 10 | Drawing objects on the map (object in 3 points, in N points, digitised object) and their warning messages. |
| `DrawingsUI` | 7 | Linking, opening and unlinking DWG/DXF drawings attached to elements. |
| `SlackUI` | 4 | Optical slack placement — terminal and mid-span. |
| `DuctingUI` | 4 | Ducting: PE pipe, transition pipe, manhole placement. |
| `SelectionUI` | 4 | Smart selection, clear selection, delete selected. |
| `ElementPlacementUI` | 3 | Placing network elements, including joint closures. |
| `QuickToolbar` | 1 | One label template for the quick-access toolbar. |
| `FiberQPlugin` | 105 | **Everything else** — menu entries, dialogs, tooltips, status messages and error messages from the plugin's main module: BOM report, locator, PostGIS publishing, health check, image linking, cutting tools, export, and the language menu. |

**Suggested order:** do `FiberQ`, `RoutingUI` and `CableLayingUI` first — that is
31 strings and covers almost everything a user sees on screen constantly. Then
the other small UI groups. Leave `FiberQPlugin` for last: it is by far the
biggest, and much of it is error text that a user meets rarely.

If you only ever do the first three groups, that is a real and shippable
contribution.

---

## Translator notes, and when to ask

Some strings carry a **translator note** written by the maintainer, explaining
what the term means in FiberQ specifically. In the XML these appear as an
`<extracomment>` line; in Qt Linguist they show up as a comment beside the
source string. **Read them.** They exist because the English on its own is
ambiguous — for example, whether "Drop" is a noun (the final cable to a
subscriber) or a verb.

### The terminology glossary

Before translating anything fibre-specific, read the
**[English → French glossary in CONTRIBUTING.md](../CONTRIBUTING.md#english--french-glossary)**.
It gives the terms used in French and EU FTTH practice — *chambre de tirage*,
*fourreau*, *câble de branchement*, *soudure* — and explicitly flags the ones
where the maintainer is **not** confident and would rather you decide.

The glossary is not duplicated here on purpose. It lives in one place so it can
be corrected in one place.

### When a string is unclear — ask, do not guess

If you cannot tell what a string means, **say so** rather than picking a
plausible term. Comment on the issue or the pull request, or email the
maintainer, and describe the ambiguity.

This is worth stating plainly: **a flagged gap is more useful than a confident
wrong term.** An untranslated string is visibly English and obviously pending. A
wrong term looks finished, gets copied into later work, ships to users, and
misleads engineers who trust it. If you are unsure, leave it and flag it. You
will be doing the project a favour, not letting it down.

The same goes in reverse: if the glossary gives a term you know to be wrong for
French practice, say so. You are the domain expert here.

---

## Seeing your work in the plugin

Translators cannot preview their own work directly, because the plugin loads the
compiled `.qm` file and that is built by the maintainer (Rule 3). The sequence
is:

1. You send the `.ts` file.
2. The maintainer compiles it to `fiberq_fr.qm` and commits both.
3. It ships in the next FiberQ release.

To see it once it has shipped:

1. In QGIS, go to **Settings → Options → General → User interface translation**.
2. Set the language to **French**.
3. **Restart QGIS.** This is required, not optional — FiberQ installs its
   translation catalogue once, when the plugin loads at startup, so a language
   change cannot take effect until QGIS starts again.

FiberQ follows QGIS's own language setting rather than your operating system's,
which is what most users expect. Regional variants collapse to the base
language: `fr_BE` and `fr_FR` both load the same French catalogue.

If you want to check your work before a release, ask on the issue — the
maintainer can build a test copy for you.

---

## Troubleshooting

**My editor says the file is TypeScript and shows hundreds of errors.**
Harmless, and not your fault. Qt translation files use the extension `.ts`, which
many editors and GitHub assume means TypeScript. It is XML. The repository now
tells GitHub this explicitly, but your local editor may still guess wrong — set
the file's language mode to **XML** manually, or just use Qt Linguist, which
never has this problem.

**Accented characters look wrong — é appears as Ã©.**
The file is **UTF-8** and must stay UTF-8. Your editor opened or saved it in a
different encoding. In your editor, reopen the file specifying UTF-8, or save it
as UTF-8, and check the accents again. Qt Linguist always handles this correctly,
which is another argument for Route A. Do not try to fix the characters by hand —
re-save with the right encoding instead.

**Qt Linguist will not open the file.**
Usually one of:
- You downloaded the GitHub *page* rather than the file. Make sure you used
  **Download raw file** and that the file starts with `<?xml version="1.0"`.
- Hand-edits broke the XML — for instance a `<translation>` opened but never
  closed. See "How do I undo" below.
- You picked the `.qm` file by mistake. Open the `.ts`.

**A placeholder warning appeared and will not go away.**
Compare your text with the English character by character. The placeholder must
be identical: `{count}`, not `{Count}`, `{ count }`, or `{nombre}`. Both braces
must be present. If the English has two placeholders, your translation needs both.

**How do I undo?**
- *In Qt Linguist:* **Ctrl+Z**, as in any editor.
- *In the GitHub web editor:* Ctrl+Z while editing; if you already committed,
  just say so in the pull request — nothing is lost and the maintainer can roll
  it back.
- *Worst case:* delete your copy and download the file again. Nothing you do
  locally can damage the project. The original is always at
  <https://github.com/vukovicvl/fiberq/blob/main/fiberq/i18n/fiberq_fr.ts>.

**I translated something but it did not appear in the plugin.**
Most likely `type="unfinished"` was left on the entry, so the build skipped it.
Check that the line reads `<translation>…</translation>` with no `type=`
attribute. Alternatively the `<source>` was edited at some point (Rule 1), which
breaks the link silently.

**Something else.**
Open an issue. A confused translator is a bug in this guide, and worth fixing.

---

## Credit and licence

- Translations are part of FiberQ and are released under the same
  **GPL-3.0-or-later** licence as the rest of the plugin. By contributing one you
  agree to that.
- **There is no CLA to sign.** No contributor agreement, no copyright
  assignment, no paperwork. You keep authorship of your work; it is simply
  licensed under the same terms as everything else here.
- **You are credited** in the README and in the release notes for the version
  your work first ships in. If you would prefer a specific name, a handle, or no
  credit at all, just say so and that is what happens.

---

## In one paragraph

Install Qt Linguist. Download `fiberq/i18n/fiberq_fr.ts`. Open it, type French
into the right-hand box, press Ctrl+Enter, repeat. Never touch the `<source>`
text, keep every `{placeholder}` exactly as written, never use File → Release.
Save with Ctrl+S and email the file to <vukovicvlmma@gmail.com>. Stop whenever
you like — whatever you finish will ship, and the rest stays English until
someone gets to it.

Thank you. Genuinely — accurate fibre terminology in a user's own language is
something no amount of engineering effort can substitute for.
