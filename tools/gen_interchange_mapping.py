"""Regenerate docs/interchange-mapping.md from the single sources of truth.

    make mapping-doc

The published mapping is generated, not hand-maintained: the plugin column comes
from fiberq/models/schema.py and the canonical column from
fiberq/core/interchange_fields.py, so the page cannot describe a mapping the code
does not implement. tests/test_interchange_mapping.py fails when the two drift,
which is what makes running this a required step rather than a nicety.

Repo-root dev tooling; not shipped in the plugin zip.
"""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


schema = load("s", "fiberq/models/schema.py")
ic = load("ic", "fiberq/core/interchange.py")
fm = load("fm", "fiberq/core/interchange_fields.py")

ROSTER_TITLES = [
    ("element", "Point elements — ODF, OTB, TO, TB, patch panel"),
    ("closure", "Joint closures"),
    ("pole", "Poles"),
    ("manhole", "Manholes"),
    ("route", "Routes"),
    ("cable", "Cables — aerial and underground"),
    ("duct", "Ducts — PE and transition"),
    ("slack", "Optical slack"),
    ("fiber_break", "Fibre breaks"),
    ("service_area", "Service areas"),
    ("building", "Buildings / objects"),
]

TYPE_NAMES = {"text": "text", "int": "integer", "double": "real",
              "enum": "text (domain)", "year": "integer", "bool": "boolean"}


def roster_of(layer_name):
    fq_type, _p = ic.type_for_layer(layer_name)
    return fm.roster_for_type(fq_type)


def field_facts():
    """(roster, stored key) -> (field_type, units, has_value_map, options)."""
    facts = {}
    for layer_name, layer_schema in schema.LAYER_SCHEMAS.items():
        roster = roster_of(layer_name)
        for f in layer_schema.fields:
            facts.setdefault(
                (roster, f.key),
                (f.field_type, f.units, bool(f.value_map), tuple(f.options or ())))
    return facts


def types_for_roster(roster):
    return sorted({t for t, r in fm.TYPE_ROSTER.items() if r == roster})


facts = field_facts()
out = []
w = out.append

w("# FiberQ interchange — field mapping")
w("")
w("The canonical field and value mapping for the")
w("[FiberQ interchange format](interchange-format.md). Read that first: this page is")
w("the mapping table it refers to.")
w("")
w("**Generated from the code.** The plugin side comes from")
w("[`fiberq/models/schema.py`](../fiberq/models/schema.py) and the canonical side from")
w("[`fiberq/core/interchange_fields.py`](../fiberq/core/interchange_fields.py), with a")
w("test (`tests/test_interchange_mapping.py`) that fails if this page and the code drift")
w("apart. A field added to the plugin without a canonical name fails CI.")
w("")
w("---")
w("")
w("## Why names change at all")
w("")
w("FiberQ's stored field names are the original Serbian database names — `duzina_m`,")
w("`slabljenje_dbkm`, `vrsta_omotaca` — and several stored *values* are Serbian too")
w("(`vazdusna`, `opticki`). That is the plugin's schema, it is what is on disk in every")
w("existing project, and it is not changing: renaming a stored field is a data migration,")
w("not a cosmetic change.")
w("")
w("A bundle carrying those names would not be a tool-neutral format. It would be FiberQ's")
w("schema in a GeoPackage, and every other tool would have to learn Serbian to read it —")
w("which is mapping directly to one tool's schema, exactly what")
w("[rule 3](interchange-format.md#2-the-four-rules) exists to prevent. So a bundle carries")
w("canonical English names and canonical values, and this page is the bijection.")
w("")
w("**Nothing here changes your project.** The renaming happens on the copy written into")
w("the bundle. Your layers, their fields and their values are read and left exactly as")
w("they are.")
w("")
w("## The mapping is per element type")
w("")
w("`tip` means *cable type* on a cable and *pole type* on a pole. `podtip` means *subtype*")
w("on one and *segment type* on the other. A single global rename table would quietly")
w("merge two different meanings into one canonical field, and nothing downstream could")
w("tell them apart afterwards. So the tables below are per **roster** — a group of element")
w("types that share a field set.")
w("")
w("## The four mismatch cases")
w("")
w("| Case | What it means | How it is handled |")
w("|---|---|---|")
w("| **Both sides** | The canonical field and a plugin field mean the same thing | Renamed on export, renamed back on import |")
w("| **Plugin-only** | A field FiberQ has and other tools may not | Still gets a canonical name — the format is a *superset*, so nothing has to be dropped to fit |")
w("| **Format-only** | Something the format models and the plugin does not (fibre splices, trays, duct occupancy) | Carried in the [side-car tables](interchange-format.md#62-side-car-tables) and the passthrough store; the plugin never sees it and never destroys it |")
w("| **Structural** | The same fact, a different shape on each side | Converted, not renamed — see below |")
w("")
w("### The structural case")
w("")
w("FiberQ records which cable an optical slack loop or a fibre break belongs to as")
w("`cable_layer_id` + `cable_fid` — a QGIS layer id plus a feature id. Both are local to")
w("one project file. They mean nothing in another tool, and nothing in the same project")
w("after the layer is rebuilt.")
w("")
w("A bundle carries **`cable_uuid`** instead, resolved on export and resolved back on")
w("import. The local pair is not written. A reference that cannot be resolved — the cable")
w("was deleted — is **reported and left empty**, never pointed at the nearest plausible")
w("cable.")
w("")
w("| Plugin (stored) | Canonical | Rule |")
w("|---|---|---|")
w("| `cable_layer_id` + `cable_fid` | `cable_uuid` | Resolved through `fiberq_uuid`; unresolvable references are reported, not guessed |")
w("")
w("### The one field that is never renamed")
w("")
w("`fiberq_uuid` keeps its name everywhere. It is the join key every conformant tool must")
w("already know ([section 4](interchange-format.md#4-identity)), so translating it would")
w("be renaming the thing that makes a round trip verifiable.")
w("")
w("---")
w("")
w("## Field tables")
w("")

for roster, title in ROSTER_TITLES:
    mapping = fm.ROSTERS[roster]
    codes = ", ".join(f"`{t}`" for t in types_for_roster(roster))
    w(f"### {title}")
    w("")
    w(f"Element types: {codes}")
    w("")
    w("| Canonical field | Plugin field (stored) | Type | Units | Notes |")
    w("|---|---|---|---|---|")
    for stored, canonical in mapping.items():
        ftype, units, has_map, options = facts.get(
            (roster, stored), ("text", "", False, ()))
        notes = []
        if has_map:
            notes.append("controlled vocabulary — see below")
        elif options:
            notes.append("one of " + ", ".join(f"`{o}`" for o in options)
                         + " (stored and carried as-is)")
        if stored == canonical:
            notes.append("same name on both sides")
        w(f"| `{canonical}` | `{stored}` | {TYPE_NAMES.get(ftype, ftype)} | "
          f"{units or '—'} | {'; '.join(notes) or '—'} |")
    w(f"| `fiberq_uuid` | `fiberq_uuid` | text | — | identity, never renamed |")
    w("")

w("Every feature additionally carries the bundle's own columns: **`fq_type`**,")
w("**`placement`** and **`fq_extra_json`**")
w("([section 6.1](interchange-format.md#61-element-type-codes)).")
w("")
w("---")
w("")
w("## Value domains")
w("")
w("The fields below hold values from a controlled vocabulary, and FiberQ stores them")
w("in Serbian. A bundle carries the canonical form.")
w("")
w("Real projects hold **both spellings** — the English display label on some features and")
w("the stored Serbian value on others, depending on how and when the feature was created")
w("(see [validation rule D1](validation-rules.md#d1--attribute-values-within-allowed-domain)).")
w("Both are as-built, and both map to the same canonical value.")
w("")
w("A value in neither set is **carried through unchanged**. Tidying a vocabulary is not")
w("worth discarding what the user recorded.")
w("")

english = fm.ENGLISH_ALIASES
for key in fm.VALUE_DOMAINS:
    roster, _, canonical = key.partition("/")
    title = dict(ROSTER_TITLES).get(roster, roster)
    w(f"### `{canonical}` — {title.split('—')[0].strip().lower()}")
    w("")
    w("| Canonical value | Stored by FiberQ | Also accepted |")
    w("|---|---|---|")
    reverse_en = {}
    for label, canon in english.get(key, {}).items():
        reverse_en.setdefault(canon, []).append(label)
    by_canonical = {}
    for stored, canon in fm.VALUE_DOMAINS[key].items():
        by_canonical.setdefault(canon, []).append(stored)
    for canon, stored_values in by_canonical.items():
        primary = stored_values[0]
        alts = [f"`{a}`" for a in reverse_en.get(canon, [])]
        alts += [f"`{v}`" for v in stored_values[1:]]
        w(f"| `{canon}` | `{primary}` | {', '.join(alts) or '—'} |")
    w("")

w("---")
w("")
w("## Mapping another tool")
w("")
w("A second tool maps to the **canonical** column, never to FiberQ's stored column. That")
w("is what keeps adding a third tool from being a change to the first")
w("([rule 3](interchange-format.md#2-the-four-rules)).")
w("")
w("If a tool has a field with no canonical equivalent, the honest options are, in order:")
w("propose it for the canonical set (the format is meant to be a superset), or carry it in")
w("the feature's `fq_extra_json`, or carry the whole object in")
w("[`fq_extension`](interchange-format.md#8-the-passthrough-store). What is never")
w("acceptable is mapping it onto the nearest canonical field that nearly fits — that loses")
w("information irreversibly while looking like it worked.")
w("")
w("---")
w("")
w("*Part of the FiberQ QGIS plugin, developed with support from the [NLnet](https://nlnet.nl)")
w("NGI Zero Commons Fund. The specification and this mapping are CC-BY-4.0.*")

(ROOT / "docs" / "interchange-mapping.md").write_text("\n".join(out) + "\n")
print("wrote docs/interchange-mapping.md")
