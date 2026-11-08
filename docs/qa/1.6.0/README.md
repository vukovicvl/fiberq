# FiberQ 1.6.0: the re-check, replayed in QGIS

Before a release, FiberQ goes through a written re-check list: each step says
what to click and what you should see. For 1.6.0, tests 19 to 31 of that list
were replayed click by click in the real QGIS desktop application, in QGIS
4.2.3 and QGIS 3.40.15, and every check compares what QGIS showed with the
words the list expects. **589 of 589 checks came out as expected.**

| File | What it is |
|---|---|
| [`FiberQ-1.6.0-QA-Tests-19-29.html`](FiberQ-1.6.0-QA-Tests-19-29.html) | Tests 19 to 29: Save all and auto-save, route import, BOM export, the Python warning tab. One QGIS session per version. |
| [`FiberQ-1.6.0-QA-Tests-30-31-Language.html`](FiberQ-1.6.0-QA-Tests-30-31-Language.html) | Tests 30 and 31: FiberQ speaks the language QGIS speaks. Five QGIS starts. |

Each report is a single HTML file with every screenshot inside it. GitHub shows
its source, so download it and open it in a browser. Or read them on fiberq.net: [tests 19 to 29](https://www.fiberq.net/wp-content/uploads/2026/11/FiberQ-1.6.0-QA-Tests-19-29.html) · [tests 30 and 31](https://www.fiberq.net/wp-content/uploads/2026/11/FiberQ-1.6.0-QA-Tests-30-31-Language.html).

## Results

| Test | What it checks | QGIS 4.2.3 | QGIS 3.40.15 |
|---|---|---|---|
| 19 | Save all: Esc, Cancel, Keep, Replace | 35 of 35 | 35 of 35 |
| 20 | A renamed layer's table is never offered | 9 of 9 | — |
| 21 | Turning auto-save on into a file that has such a table | 33 of 33 | 27 of 27 |
| 22 | A layer added later, with auto-save on | 9 of 9 | — |
| 23 | Save all moves auto-save, and says so | 6 of 6 | — |
| 24 | A file FiberQ cannot read or write: one warning, no question; and a GeoPackage it now accepts | 35 of 35 | 35 of 35 |
| 25 | A layer FiberQ cannot trace: no question, the note instead | 10 of 10 | 10 of 10 |
| 26 | The file changes while the question is open | 15 of 15 | 15 of 15 |
| 27 | Import route from file | 72 of 72 | 72 of 72 |
| 28 | BOM export to a read-only file | 34 of 34 | 34 of 34 |
| 29 | No FiberQ line in the Python warning tab | 26 of 26 | 26 of 26 |
| 30 | Language follows QGIS (three QGIS starts) | 33 of 33 | — |
| 31 | The same with `qgis --lang sr` (two QGIS starts) | 11 of 11 | — |
|  | At the end of every QGIS session: no FiberQ line on a Python tab of the Log Messages panel | 6 of 6 | 1 of 1 |

Tests 20, 22, 23, 30 and 31 are QGIS 4.2 only, and in QGIS 3.40 test 21 has
steps 1 to 8, as the list says.

## How the tests were replayed

- **QGIS:** the official QGIS Docker images, `qgis/qgis:4.2-trixie` (QGIS
  4.2.3) and `qgis/qgis:3.40` (QGIS 3.40.15). The desktop application ran on a
  virtual screen, with no network.
- **FiberQ:** the plugin folder of the v1.6.0 release (git tree `cf7ce22b9999`),
  installed into a fresh QGIS profile and enabled, as **Plugins → Install from
  ZIP** leaves it.
- **Steps:** every click and key went to the real QGIS windows, and the console
  lines are the list's own. A check reads what QGIS shows (the message bar, the
  Log Messages panel, a question and its buttons, the layer sources, the tables
  in the file) and compares it with the list's words.
- **One session:** tests 19 to 29 ran one after another in a single QGIS
  session per version, as a person would do them, so each test starts where the
  one before it left QGIS.
- **Screenshots:** the QGIS window with its open dialogs, at every step. Click
  one in a report to see it full size.

## Checked by hand

A container has no desktop of its own, so the steps that depend on the
desktop's own windows were also done by hand, in QGIS 4.2.3 on Ubuntu with
GNOME, on 6 November 2026, with the 1.6.0 test build that came before the
release's last fixes. Those fixes do not touch what these steps check, and
the replays above ran on the release itself. Everything came out as the
list expects:

| Test | Steps | What was seen |
|---|---|---|
| 19 | Save all to a new file, then onto a file that already has those tables | GNOME's file window asked nothing either time. The new file saved with the green "All layers saved to q18.gpkg."; on the existing file FiberQ's own question came, and **Replace them** gave "All layers saved to q18.gpkg. The old tables Manholes, Poles, Scratch_A were replaced." |
| 27 | 2, 4 to 7 | Double-clicking OpenStreetMap in the Browser adds it; GNOME's "Choose a route file" window, file type GIS files; the box and the yellow bar word for word |
| 28 | 3 to 8 | GNOME's Save window asks to replace the read-only file; FiberQ then says "Could not write the bill of materials to …" with the reason, and the file is unchanged |
| 29 | 6, at the end of that session | No FiberQ line on the Python warning tab |
