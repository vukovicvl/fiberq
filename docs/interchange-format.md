# FiberQ Interchange Format v1 — draft

**Status: DRAFT.** This document is under active development as part of WP3 and is
not yet stable. Version `1.0` of the format is frozen when this notice is removed.

A tool-neutral, open format for exchanging a complete fibre-access-network design —
geometry, attributes, identity, and the relationships between elements — between the
FiberQ QGIS plugin and any other conformant tool, without losing anything on the way.

- **Format identifier:** `fiberq-interchange`
- **This revision:** `1.0-draft`
- **Container:** GeoPackage (OGC GeoPackage 1.3), with a GeoJSON profile for the
  geometry-only subset
- **Licence:** this specification is published under CC-BY-4.0 so it can be
  implemented in any tool, open or closed, without licence conflict. The reference
  implementation inside the FiberQ plugin remains GPL-3.0-or-later.

Related: [schema reference](schema.md) · [validation rules](validation-rules.md) ·
[project versioning](project-versioning-guide.md)

---

## 1. Why this exists

A fibre design is not a pile of lines and points. It is a set of **typed objects with
relationships**: this cable enters that closure, fibre 7 of tube 2 is spliced to fibre
3 of tube 1, this slack loop belongs to that cable, this duct carries those cables.

Generic GIS formats carry the geometry and lose the rest. Exchanging designs through
plain Shapefile or a hand-rolled GeoPackage means the receiving tool gets a drawing and
has to guess the engineering. Every exchange loses a little more.

This format exists so that a design can move between tools and come back **unchanged** —
including the parts the receiving tool does not understand.

## 2. The four rules

Everything below follows from these. A conformant implementation must honour all four.

1. **Preserve, don't discard.** A reader that encounters an element type, an attribute,
   or a relation it does not understand **must carry it through unchanged** on the next
   write. Silent loss is a conformance failure, not a limitation.
2. **Identity is permanent.** Every object carries a `fiberq_uuid`. It is assigned once,
   at creation, and **never regenerated** — not on import, not on export, not on
   reprojection. It is the only thing that makes a round trip verifiable.
3. **The format is the contract, not any one tool's schema.** Tools map to and from this
   canonical middle; they never map directly to each other. Adding a second tool must not
   require changing the first.
4. **Versioned and self-describing.** A bundle declares its format version and what wrote
   it. A reader that meets a newer minor version must still read what it recognises and
   pass through the rest.

## 3. Container layout

A bundle is a single `.gpkg` file containing three kinds of table.

```
design.gpkg
├── <feature layers>        one per element type, canonical names, OGC-standard
│   ├── Route
│   ├── Underground cables
│   ├── Poles
│   └── …
├── _fiberq_metadata        key/value; bundle-level facts  (§7)
└── fq_*                    relational side-car tables     (§6)
    ├── fq_splice_point
    ├── fq_fiber_connection
    ├── fq_relation
    ├── fq_relation_member
    ├── fq_container
    ├── fq_container_slot
    ├── fq_slot_assignment
    └── fq_extension        the passthrough store          (§8)
```

Feature layers are ordinary GeoPackage vector layers: any GIS tool can open the file and
see the network. The `fq_*` tables are ordinary attribute tables: any SQLite client can
read them. **Nothing in this format requires a FiberQ-aware tool to be useful** — that is
deliberate.

### GeoJSON profile

For exchanges that only need geometry and attributes (web maps, quick handover), a
bundle may instead be a directory of GeoJSON files, one per element type, plus
`_fiberq_metadata.json`. The relational side-car is **not** representable in the GeoJSON
profile; a writer emitting GeoJSON while holding side-car data must say so
(`profile = "geojson-lite"`) so the receiver knows the bundle is lossy by construction.

## 4. Identity

`fiberq_uuid` — a string of at most 64 characters, unique across the whole bundle,
present on every feature and on every side-car row that represents a real object.

Rules:

- assigned **once**, when the object is first created, by whichever tool created it;
- **never** regenerated — a tool that reassigns identities breaks every relation in the
  bundle and fails conformance;
- splitting one object into two produces **two new** identities, and the original is
  gone. Merging produces one new identity;
- relations reference objects **by `fiberq_uuid` only**, never by row id, feature id, or
  layer name — those are local to a file and do not survive a round trip.

Validation rule **B4** enforces presence and uniqueness inside the plugin.

## 5. Coordinates and measurement

- **Storage CRS is EPSG:4326.** All geometry in a bundle is WGS84 longitude/latitude.
  One storage CRS means a bundle is unambiguous without reading metadata first.
- **`crs_epsg` declares the restore target** — the CRS the design was authored in. A
  reader should reproject to it on import so the user gets their working CRS back, and a
  writer should record it.
- **Lengths are ellipsoidal metres**, measured on the ellipsoid, never in map units.
  A projected length is a property of a map, not of the ground, and does not survive
  reprojection. See the [validation rules](validation-rules.md) rule **D3**.
- Bearings, offsets and any other derived geometry values are likewise stored in
  real-world units, not map units.

## 6. Element types and the relational side-car

### 6.1 Element type codes

Every feature carries `fq_type` — a stable, untranslated code identifying what it is.
The layer it happens to sit in is a presentation detail; `fq_type` is the contract.

Codes are lowercase, dot-free, and stable forever once published:

| `fq_type` | Geometry | Meaning |
|---|---|---|
| `route` | LineString | Trench/span route the plant follows |
| `cable.aerial` | LineString | Aerial optical cable |
| `cable.underground` | LineString | Underground optical cable |
| `duct.pe` | LineString | PE duct |
| `duct.transition` | LineString | Transition duct |
| `pole` | Point | Pole |
| `manhole` | Point | Manhole / chamber |
| `closure.joint` | Point | Joint closure |
| `odf` | Point | Optical distribution frame |
| `otb` | Point | Optical termination box |
| `otb.indoor` / `otb.outdoor` / `otb.pole` | Point | OTB placement variants |
| `to` | Point | Termination outlet |
| `to.indoor` / `to.outdoor` / `to.pole` / `to.closure` | Point | TO placement variants |
| `tb` | Point | Termination box |
| `patch_panel` | Point | Patch panel |
| `slack` | Point | Optical slack loop |
| `fiber_break` | Point | Recorded fibre break |
| `service_area` | Polygon | Service area |
| `building` | Polygon | Building / object |

A tool encountering an unknown `fq_type` **must not** reclassify it to something it does
recognise. Mapping an unknown point to the nearest familiar type destroys information
irreversibly and is the most common way an exchange goes wrong. Carry it through
unchanged (§8).

### 6.2 Side-car tables

These carry what is not geometry. All references are `fiberq_uuid` strings.

**`fq_splice_point`** — an element's splice capability.
`uuid`, `element_uuid`, `port_count`, `used_ports`, `config_json`, `notes`

**`fq_fiber_connection`** — one fibre spliced or connected to another. This is the table
that makes the format worth having.
`uuid`, `source_element_uuid`, `source_cable_uuid`, `source_tube`, `source_fiber`,
`source_port`, `source_side`, `dest_element_uuid`, `dest_cable_uuid`, `dest_tube`,
`dest_fiber`, `dest_port`, `dest_side`, `connection_type`, `loss_db`, `tray_ref`, `notes`

Tube and fibre numbers are **1-based**. Fibre colour is *derived* from the colour
standard (§7) and the tube/fibre index — it is not stored, so a bundle cannot contradict
itself about which standard it follows.

**`fq_relation`** + **`fq_relation_member`** — named groupings of objects: an optical
path, a feeder, a named route. `fq_relation(uuid, name, category)` and
`fq_relation_member(relation_uuid, member_uuid, order_index, role)`.

**`fq_container`**, **`fq_container_slot`**, **`fq_slot_assignment`** — the generic model
for "a thing with numbered positions that other things occupy": duct holes in a manhole
wall, ports on a panel, trays in a closure.
`fq_container(uuid, host_uuid, kind, name, geometry_json)`,
`fq_container_slot(uuid, container_uuid, index, label, kind, spec_json, status)`,
`fq_slot_assignment(slot_uuid, occupant_uuid, direction, notes, extra_json)`

Generic on purpose: modelling duct holes, tray positions and panel ports as three
different table sets would mean a new table set for every tool's next idea.

### 6.3 Ordered traversal

**`fq_path_stop`** — the ordered list of elements a linear object passes through.
`cable_uuid`, `element_uuid`, `order_index`, `is_latent`

A cable's geometry says where it goes; `fq_path_stop` says what it *visits*, in order,
including elements it merely passes through without terminating at.

## 7. Bundle metadata

The `_fiberq_metadata` table is `key TEXT PRIMARY KEY, value TEXT`.

| Key | Required | Meaning |
|---|---|---|
| `format` | yes | `fiberq-interchange` |
| `format_version` | yes | e.g. `1.0` — the version of **this specification** |
| `schema_version` | yes | the FiberQ data-schema version of the payload |
| `produced_by` | yes | free text naming the writing tool **and its version** |
| `produced_at` | yes | ISO-8601 UTC timestamp |
| `crs_epsg` | yes | the authoring CRS to restore on import (§5) |
| `color_standard` | yes | fibre colour standard, e.g. `TIA-598-C` |
| `color_catalog_json` | no | full colour catalogue if non-standard |
| `profile` | no | `geojson-lite` when the side-car is absent by construction (§3) |

> **Do not** put a producing tool's release number in a key that means the data-schema
> version. `format_version` and `schema_version` describe the *payload*; `produced_by`
> describes the *writer*. Conflating them makes a bundle unreadable by version checks.

A writer **must not** delete metadata keys it did not write. Rebuilding this table from
scratch on every export silently discards whatever another tool recorded. Merge; do not
replace.

## 8. The passthrough store

`fq_extension` is how rule 1 is actually honoured.

`uuid` · `owner_uuid` · `kind` · `namespace` · `payload_json` · `produced_by`

When a reader meets something it has no model for — an unknown `fq_type`, an attribute
with no column, a side-car table it does not implement — it writes the whole thing here
verbatim, keyed to the object it belongs to, and emits it again untouched on the next
write.

Consequences worth stating plainly:

- A design can pass through a tool that understands **none** of the advanced data and
  come out the other side complete.
- When a tool later gains real support for something it used to pass through, the mapping
  is upgraded and those objects start importing properly — **older bundles still work**,
  because nothing was ever thrown away.
- Per-feature attributes with no canonical column travel in the feature's own
  `fq_extra_json` column rather than here; `fq_extension` is for whole objects and whole
  tables.

## 9. Conformance

A **conformant reader** must:
1. read every feature layer and the metadata table;
2. preserve `fiberq_uuid` exactly;
3. store anything it does not understand in the passthrough store;
4. refuse, with a clear error, a bundle whose `format_version` has a **major** number it
   does not implement — rather than importing it partially.

A **conformant writer** must:
1. emit all required metadata keys (§7);
2. merge, never replace, metadata keys written by other tools;
3. emit the passthrough store contents unchanged;
4. never regenerate an identity it did not create.

A **conformant round trip** is the real test: import a bundle, change nothing, export it,
and every object, attribute and relation is still present — *including everything the
tool does not support*. The FiberQ plugin asserts exactly this in CI.

## 10. What v1 deliberately does not cover

- **Styling and symbology.** Presentation is a tool concern. A bundle describes the
  network, not how to draw it.
- **Rendering geometry for schematic views.** Derived, not source.
- **Access control, users, projects-as-workspaces.** Out of scope for a file format.
- **Product catalogues as normative content.** A bundle may carry a catalogue reference
  on a feature, and the resolved values alongside it, so a receiver without the catalogue
  still has the numbers it needs.

## 11. Open questions before v1 freezes

1. Should `fq_type` placement variants (`otb.indoor` vs `otb`) be a separate
   `placement` attribute instead of distinct types? Cleaner, but changes the layer mapping.
2. Colour: derive from standard + index (current draft) or store resolved colour too, for
   readers with no catalogue?
3. Does `fq_container` adequately cover tray-within-closure nesting, or is one level of
   nesting needed?
4. Is a GeoPackage-only v1 acceptable, with the GeoJSON profile deferred to v1.1?

---

*Part of the FiberQ QGIS plugin, developed with support from the [NLnet](https://nlnet.nl)
NGI Zero Commons Fund. The specification is CC-BY-4.0; comments and implementations from
other tools are welcome via [GitHub issues](https://github.com/vukovicvl/fiberq/issues).*
