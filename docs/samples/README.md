# FiberQ demo project and sample validation report

A small, deliberately imperfect fibre design, and the validation report it
produces. Everything here is generated — see [Regenerating](#regenerating).

| File | What it is |
|---|---|
| [`demo_project.qgz`](demo_project.qgz) | QGIS project — **open this** |
| [`demo_project.gpkg`](demo_project.gpkg) | The data it points at |
| [`demo-validation.html`](demo-validation.html) | The report, as delivered to a client |
| [`demo-validation.json`](demo-validation.json) | The same run, machine-readable |
| [`demo-validation.csv`](demo-validation.csv) | The same issues, one row each |

## Try it

1. Open `demo_project.qgz` in QGIS with the FiberQ plugin installed.
2. **Plugins → FiberQ → Validate project**.
3. You should see **1 error and 7 warnings** — matching
   [`demo-validation.html`](demo-validation.html).
4. Click any row to jump to it on the map.
5. **Export report…** to write your own copy.

Then try **Plugins → FiberQ → Recalculate lengths…** and validate again: the D3
finding disappears and the count drops to 1 error, 6 warnings.

## The data

A short street running east with a spur north — three route segments, three cables,
four poles, two manholes, a joint closure and two slack loops. It is **synthetic**:
invented coordinates in an empty stretch of the Adriatic, at a European latitude so
the Web Mercator scale factor is realistic. No real network, no customer data.

It is in **EPSG:3857** on purpose. That is what a design traced over a web basemap
really uses, and it is where the length rules have something to say.

## The planted faults

Seven of the thirteen rules fire, each from exactly one planted fault. Nothing else
fires — that is asserted by `tests/test_demo_project.py`, so a rule that starts
reporting something new here fails the build rather than quietly changing the
published sample.

| Rule | Severity | Planted fault |
|---|---|---|
| **B1** | Error | Slack `SL-2` references a cable layer that is not in the project. |
| **A1** | Warning | Aerial cable `AC-2` is stranded — neither end reaches anything. *One fault, two findings: a cable has two ends.* |
| **A3** | Warning | The fourth pole sits 45 m off the network, attached to nothing. |
| **C1** | Warning | Underground cable `UC-2` has no cable type recorded. |
| **D1** | Warning | `UC-2` is in state `Someday`, which is not a permitted value. |
| **D2** | Warning | `AC-2` claims 9999 fibres. |
| **D3** | Warning | Route `R-3` stores 210 m against a real ground length of ~145 m. |

The other six rules (A2, B2, B3, B4, E1, E2) stay quiet, which is the point: the
demo also demonstrates what passing looks like. Slack `SL-1` carries a *working*
cable reference, so B1's single finding on `SL-2` means something.

`R-3`'s stale length is the interesting one. It is not a projection artefact — the
demo stores it as if someone moved a vertex and nothing recomputed the attribute.
That is a real failure mode, and D3 is how you catch it.

## Regenerating

Needs QGIS on the path (the `qgis/qgis` Docker images work):

```sh
python docs/samples/generate.py
```

This rewrites the GeoPackage, the project and all three reports. The run timestamp
is fixed rather than taken from the clock, so a regenerated report differs only
where the rules differ and the diff stays reviewable.

**Re-run it whenever the rules change.** `tests/test_sample_report.py` fails if the
committed report no longer matches a fresh run, so the published sample cannot
silently go stale.

---

See [`../validation-rules.md`](../validation-rules.md) for what each rule checks and
what to do about a finding.
