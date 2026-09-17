# FiberQ demo project, sample report and example bundle

A small, deliberately imperfect fibre design; the validation report it produces;
and the same design exported as an interchange bundle. Everything here is
generated — see [Regenerating](#regenerating).

| File | What it is |
|---|---|
| [`demo_project.qgz`](demo_project.qgz) | QGIS project — **open this** |
| [`demo_project.gpkg`](demo_project.gpkg) | The data it points at |
| [`demo-validation.html`](demo-validation.html) | The report, as delivered to a client |
| [`demo-validation.json`](demo-validation.json) | The same run, machine-readable |
| [`demo-validation.csv`](demo-validation.csv) | The same issues, one row each |
| [`demo-bundle.gpkg`](demo-bundle.gpkg) | The same design as an **interchange bundle** |
| [`demo-bundle-geojson/`](demo-bundle-geojson/) | The same bundle in the **GeoJSON profile** |

## Try it

1. Open `demo_project.qgz` in QGIS with the FiberQ plugin installed.
2. **Plugins → FiberQ → Validate project**.
3. You should see **4 errors, 9 warnings and 1 info** — matching
   [`demo-validation.html`](demo-validation.html).
4. Click any row to jump to it on the map.
5. **Export report…** to write your own copy.

Then try **Plugins → FiberQ → Recalculate lengths…** and validate again: the D3
finding disappears and the warning count drops to 8.

## The example bundle

[`demo-bundle.gpkg`](demo-bundle.gpkg) is this same design written in the
[interchange format](../interchange-format.md). Open it next to
`demo_project.qgz` and the mapping is visible directly: layers under their
canonical names, fields under their canonical names, geometry in EPSG:4326 with
the authoring CRS recorded in `_fiberq_metadata`, and `fq_type` / `placement` on
every feature.

The part worth looking at is `Optical slack`. In the project, a slack loop points
at its cable through `cable_layer_id` and `cable_fid` — a QGIS layer id and a row
number, both meaningless outside that one project file. In the bundle the same
loops carry `cable_uuid` instead. One of the three is deliberately `NULL`: that is
the planted B1 fault, a slack loop whose cable reference is broken in the source
design, and the format carries the break honestly rather than inventing a target
for it.

All nine side-car tables are present, and empty. This design has no named cable
groupings and no recorded pass-through elements, so there is nothing to put in
them — but an implementer needs to see the tables and their columns, which an
omitted table would not show. For a worked example of side-car data surviving a
round trip, see `tests/test_interchange_roundtrip.py`, which round-trips a bundle
carrying fibre splices, an element type the plugin has no layer for and a third
tool's passthrough rows.

[`demo-bundle-geojson/`](demo-bundle-geojson/) is the same export in the GeoJSON
profile: one file per element type, named for the type rather than the layer, plus
`_fiberq_metadata.json`.

## The data

A short street running east with a spur north — three route segments, four cables,
six poles, two manholes, two joint closures, three slack loops and a fibre break.
It is **synthetic**: invented coordinates in an empty stretch of the Adriatic, at a
European latitude so the Web Mercator scale factor is realistic. No real network,
no customer data.

It is in **EPSG:3857** on purpose. That is what a design traced over a web basemap
really uses, and it is where the length rules have something to say.

## The planted faults

Twelve of the fourteen rules fire, each from exactly one planted fault. Nothing
else fires — that is asserted by `tests/test_sample_report.py`, so a rule that
starts reporting something new here fails the build rather than quietly changing
the published sample.

| Rule | Severity | Planted fault |
|---|---|---|
| **B1** | Error | Slack `SL-2` references a cable layer that is not in the project. |
| **B2** | Error | The fibre break is recorded against the **Route** layer. The reference resolves, so only the layer-type check catches it — a break on a trench is not a thing. |
| **B4** | Error | Two poles share one `fiberq_uuid` — the signature of a copied and pasted feature. |
| **E2** | Error | The fifth pole has no geometry, as an attribute-table edit leaves it. |
| **A1** | Warning | Aerial cable `AC-2` is stranded — neither end reaches anything. *One fault, two findings: a cable has two ends.* Plus `AC-3`'s near miss below, so A1 reports three endpoints in total. |
| **A3** | Warning | The fourth pole sits 45 m off the network, attached to nothing. |
| **B3** | Warning | Slack `SL-3` names a cable that exists but sits 80 m from it — a stale link, as if the cable were re-routed afterwards. |
| **C1** | Warning | Underground cable `UC-2` has no cable type recorded. |
| **D1** | Warning | `UC-2` is in state `Someday`, which is not a permitted value. |
| **D2** | Warning | `AC-2` claims 9999 fibres. |
| **D3** | Warning | Route `R-3` stores 210 m against a real ground length of ~145 m. |
| **A2** | Info | Aerial cable `AC-3` starts 7 m from the third pole: outside the 5 m tolerance, close enough that it was plainly meant to connect. A2 refines A1 rather than replacing it, so that endpoint appears in both. |

**Two rules are not demonstrated here, and cannot be.** Each needs the project
itself to be wrong in a way that would invalidate everything else:

- **C2** fires when a project contains no FiberQ layers at all.
- **E1** fires on a missing or mixed CRS. Mixing one in would change what the
  A-rule tolerance means for that layer and cascade into every topology finding.

Both are covered by unit tests instead.

Passing cases matter as much as the faults: slack `SL-1` carries a *working*
cable reference, so B1's finding on `SL-2` means something, and `AC-3`'s far end
lands exactly on `JC-2` rather than dangling.

`R-3`'s stale length is the interesting one. It is not a projection artefact — the
demo stores it as if someone moved a vertex and nothing recomputed the attribute.
That is a real failure mode, and D3 is how you catch it.

## Regenerating

Needs QGIS on the path (the `qgis/qgis` Docker images work):

```sh
python docs/samples/generate.py
```

This rewrites the GeoPackage, the project, all three reports and both interchange
bundles. The report's run timestamp is fixed rather than taken from the clock, so a
regenerated report differs only where the rules differ and the diff stays
reviewable. (A bundle records the real time it was written, so `produced_at` moves
on every regeneration — that field is provenance, not content.)

**Re-run it whenever the rules or the format change.** `tests/test_sample_report.py`
fails if the committed report no longer matches a fresh run, and
`tests/test_sample_bundle.py` fails if the committed bundle stops declaring the
format this plugin implements or stops round-tripping through its own importer. The
published samples cannot silently go stale.

---

See [`../validation-rules.md`](../validation-rules.md) for what each rule checks and
what to do about a finding.
