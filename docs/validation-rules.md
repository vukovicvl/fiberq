# FiberQ validation rules

FiberQ can audit a fibre design before it leaves your desk. **Plugins → FiberQ →
Validate project** runs fourteen rules over the project and lists what it finds in
a dockable panel; from there you can jump to any issue on the map or export the
whole run as HTML, JSON or CSV.

This page documents every rule: what it checks, why that matters in the field, and
what to do about a finding.

- **Sample report:** [`samples/demo-validation.html`](samples/demo-validation.html)
- **Demo project:** [`samples/demo_project.qgz`](samples/demo_project.qgz) — open it
  and run the validator yourself
- **Schema reference:** [`schema.md`](schema.md)

---

## How to read a finding

Every issue carries a **rule id** (`A1`, `D3`, …), a **severity**, the **layer** and
**feature** it came from, and a message.

| Severity | Meaning | What it should stop |
|---|---|---|
| **Error** | The project is internally inconsistent. Something references what is not there, or a geometry is unusable. | Handover, export, and anything downstream. |
| **Warning** | Probably wrong, or incomplete. A human needs to look. | A final sign-off, but not your work in progress. |
| **Info** | Worth knowing. Often a near-miss that may be deliberate. | Nothing on its own. |

A design still being drawn is *expected* to produce warnings. The number that
matters at handover is the error count.

Rule ids are stable and untranslated, in the panel and in every export, so you can
filter on them and reference them in a report or a ticket.

---

## A — Topology and connectivity

Whether the network actually joins up. These rules use a snap tolerance (default
**5 map units**) that you can think of as "close enough to be the same point".

> **A note on tolerance and your CRS.** The tolerance is in *map units*. In a
> national grid those are true metres. In Web Mercator (EPSG:3857) they are not:
> distances there are inflated by 1/cos(latitude), so a 5-unit tolerance behaves
> like 3.6 m in Serbia and 3.2 m in the Netherlands — the A-rules are stricter
> than the number suggests. Raise the tolerance if that matters to you. (E1
> reports a *geographic* CRS, where the effect is drastic enough to break the
> rules outright; it does not report Web Mercator, where they still work.)

### A1 — Cable endpoints are connected
**Warning · every cable layer**

Each end of every cable should land on an element (pole, manhole, joint closure,
ODF, termination box) or on another cable's end. An end that reaches nothing is
either an unfinished run or a drawing slip.

Fires once per unconnected endpoint, so a completely stranded cable produces two
findings — it has two ends.

**Typical causes:** the run was left half-drawn; snapping was off while digitising;
an element was moved after the cable was laid.

**What to do:** connect the end, or accept it if the run is genuinely still in
progress.

### A2 — Cable endpoints are not near-misses
**Info · every cable layer**

An endpoint that sits *just* outside tolerance — close enough that it was clearly
meant to connect, far enough that it does not. These are the ones that look right
on screen and are wrong in the data.

A2 refines A1 rather than replacing it: an endpoint reported here is also reported
by A1.

**What to do:** snap it. This is the single most common real defect in a
hand-digitised design.

### A3 — Elements are attached to the network
**Warning · all point-element layers**

A pole, manhole, closure or termination that lies near no cable and no route. It
exists in the project but takes part in nothing.

**Typical causes:** elements dropped in during planning and never connected;
elements left behind after a route was re-drawn.

**What to do:** connect it, delete it, or leave it if the design is unfinished —
this is a warning precisely because "planned but not yet connected" is a legitimate
state.

---

## B — Referential integrity and identity

Whether the links between features still resolve.

### B1 — Optical slack references an existing cable
**Error · Optical slack**

Every slack loop records which cable it belongs to (`cable_layer_id` +
`cable_fid`). This checks the reference resolves *and points at a cable*: the
layer is in the project, it is a cable layer, and the feature is in it.

The layer check is not pedantry. A reference to a route or a duct resolves
perfectly well, so without it a slack loop recorded against a trench reads as a
valid link and the whole bill of materials inherits the error.

**Typical causes:** the cable was deleted; the layer was removed or replaced; the
project was rebuilt from parts; the feature was placed by clicking near a trench
rather than the cable.

**What to do:** re-link the slack, or delete it. A slack whose cable is gone
inflates the bill of materials for a cable that no longer exists.

### B2 — Fiber break references an existing cable
**Error · Fiber break**

The same check for fibre-break records. A break recorded against the Route layer
is reported here: a fibre break is a break in a fibre, and before v1.4.0 the
break tool would accept a click near any line — including a trench or a duct.

### B3 — Cable references are spatially coherent
**Warning · Optical slack, Fiber break**

The reference resolves, but the feature sits far from the cable it names — beyond
tolerance. Usually the cable was re-routed after the slack or break was placed, so
the link is stale even though it still points somewhere.

**What to do:** move the feature onto its cable, or re-link it to the cable it is
actually on now.

### B4 — Feature identity present and unique
**Error · every FiberQ layer**

Every feature carries a `fiberq_uuid`: a stable identity that survives export,
re-import and round trips through other tools. This checks each feature has one and
that no two share it.

**Typical causes:** features copied and pasted (which duplicates the id); features
created by another tool that does not know about the field; a project older than
the identity migration that has not been opened and migrated yet.

**What to do:** open and re-save the project so the migration runs. Duplicate ids
need the copy deleted and redrawn.

---

## C — Completeness

### C1 — Required attributes present
**Warning · every FiberQ layer**

Fields the schema marks as required are filled in. Missing values are exactly what
turn up as blanks in a bill of materials or an as-built document.

**What to do:** fill them in. A single unnamed cable is what makes a whole schedule
unusable.

### C2 — Project contains FiberQ layers
**Warning · project-wide**

There is at least one FiberQ layer to check. Every other rule works by iterating
layers, so a project with none sails through all of them and reports nothing —
which reads as a clean bill of health for a project that was never checked at all.

**What to do:** open a FiberQ project, or create the layers from the FiberQ
toolbar. If you meant to validate a project made in another tool, its layers need
FiberQ's canonical names before the rules can see them.

---

## D — Value domains and attribute sanity

Whether the values recorded are values the schema allows, and whether the numbers
are physically plausible.

### D1 — Attribute values within allowed domain
**Warning · every layer with a controlled vocabulary**

Fields with a fixed set of choices (cable type, subtype, state, route type, slack
location and side) hold one of them.

Both spellings are accepted: FiberQ stores some vocabularies as English display
labels and some as their Serbian equivalents, depending on when and how the feature
was created. Both are as-built and both pass; only a value that is in neither set
is reported.

**What to do:** correct the value using the layer's dropdown rather than by typing.

### D2 — Numeric attributes within plausible ranges
**Warning · every layer with numeric fields**

Lengths, fibre counts, tube counts, attenuation and dispersion figures fall inside
sane bounds — positive where they must be, and below a physical ceiling (fibre
count, for instance, cannot exceed 1152).

**Typical causes:** a typo; a unit mix-up; a placeholder value never replaced.

### D3 — Stored lengths agree with geometry
**Warning · Route, all cable and pipe layers**

The length recorded on a feature matches the length of the line drawn. Lengths are
measured **on the project ellipsoid**, the same way the QGIS measure tool does — so
the figure is what a surveyor would find on site, not what the map projection makes
it look like.

**Two things make a stored length wrong:**

1. **The geometry was edited afterwards.** Move a vertex and the attribute keeps its
   old value.
2. **It was written in map units.** Versions of FiberQ before 1.4.0 stored the
   projected length for routes and cables. In Web Mercator that is inflated by
   1/cos(latitude) — about 41% at Serbian latitudes, 55% in the Netherlands, 86% in
   Finland. A bill of materials built on those numbers over-orders by the same
   margin.

**What to do:** run **Plugins → FiberQ → Recalculate lengths…**. It shows you
exactly what will change before writing anything, and rewrites `duzina`,
`duzina_m`, `duzina_km` and `total_len_m` from the geometry. Slack values are read
but never changed.

Lengths are measured on the project's ellipsoid if one is set, and otherwise on
the ellipsoid the CRS itself names — so D3 works in a geographic CRS too. Only a
CRS that names no ellipsoid at all is skipped, and D3 says so rather than
comparing metres to map units.

---

## E — Coordinate systems and geometry health

### E1 — Coordinate reference systems are consistent
**Warning · project-wide**

All FiberQ layers share one CRS, and that CRS expresses the connectivity
tolerance meaningfully. Mixed CRSs make every tolerance in every other rule mean
something different per layer.

A **geographic CRS** (EPSG:4326 and friends) is flagged separately. Lengths are
fine there — they are measured on the ellipsoid — but the A-rule tolerance is in
*map units*, and a map unit in a geographic CRS is a degree. The default 5 then
means roughly 550 km, and A1/A2/A3 stop meaning anything.

**What to do:** reproject the odd layer out, and work in a projected CRS —
ideally your national grid rather than Web Mercator.

### E2 — Geometries are present and well formed
**Error · every FiberQ layer**

Every feature has a geometry, it is not empty, and it is valid — no
self-intersections, no single-point lines, no null shapes.

**Typical causes:** an interrupted digitising session; an import that dropped
geometry; a feature created by an attribute-table edit.

**What to do:** redraw the feature. A null geometry cannot be exported, measured or
located.

---

## Exporting a report

With a result in the panel, **Export report…** writes it in whichever format the
filename asks for:

| Format | Use it for |
|---|---|
| **HTML** | Handover and audit files. Self-contained — no internet needed, prints cleanly, opens in any browser years later. |
| **JSON** | Tooling. Stable keys, machine-readable, and the basis of the WP3 interchange format. |
| **CSV** | Spreadsheets and issue trackers. One row per issue. |

Rule ids, severities and categories stay in English in every format so that
downstream tools can key on them; only prose is translated.

The JSON carries a `format_version` — check it before parsing if you are building
something on top.

---

## Configuring the rules

The snap tolerance and the length-agreement tolerances live in `ValidationConfig`
and travel with the project. Individual rules can be disabled or have their
severity overridden.

A rule that fails to run is reported as such rather than passing silently — if a
rule crashes on your data, the run continues and the panel tells you which rule
gave up. Please [open an issue](https://github.com/vukovicvl/fiberq/issues) if you
see one.

---

*Part of the FiberQ QGIS plugin, funded by the [NLnet](https://nlnet.nl) NGI Zero
Commons Fund.*
