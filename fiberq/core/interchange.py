"""FiberQ interchange format — pure-logic core (WP3).

Everything here is deliberately free of QGIS imports so the format rules can be
tested without a QGIS runtime, the same way ``models/schema.py`` is. The
QGIS-facing writer that actually moves features lives alongside in
``export_manager``; this module owns the *contract*.

The format itself is specified in ``docs/interchange-format.md``. Where the two
disagree the specification wins and this module is the bug.

Three rules from the spec drive the code here:

* **Preserve, don't discard.** Anything a reader does not understand is carried
  through unchanged, so the passthrough store is a first-class concern rather
  than an error path.
* **Identity is permanent.** ``fiberq_uuid`` is never regenerated on export.
* **Merge, never replace, bundle metadata.** A writer that rebuilds
  ``_fiberq_metadata`` from scratch destroys whatever another tool recorded.
  This is not hypothetical -- it is the defect this module exists to not repeat.
"""
import uuid as _uuid
from typing import Dict, Optional, Tuple

#: Format identifier written into every bundle.
FORMAT = "fiberq-interchange"

#: Version of docs/interchange-format.md that this implementation targets.
FORMAT_VERSION = "1.0"

#: Where a writer stashes passthrough rows between an import and the next
#: export, so anything this plugin has no model for survives a round trip
#: through it (spec section 8). Read and written as a JSON list of fq_extension
#: rows; import and export must agree on this key or the passthrough is lost.
PASSTHROUGH_ENTRY = ("FiberQPlugin", "Interchange/passthrough_v1")

#: Fixed namespace for deriving stable identities for objects the plugin stores
#: without one of its own (see :func:`stable_uuid`).
UUID_NAMESPACE = _uuid.UUID("1f5b9c4e-3a76-5d0b-9c21-7e4a8d6f0b32")

#: Storage CRS for all geometry in a bundle. The authoring CRS is recorded
#: separately as ``crs_epsg`` and restored on import (spec section 5).
STORAGE_EPSG = 4326

#: Metadata keys this implementation owns and may overwrite on export. Any key
#: NOT in this set was written by another tool and must survive untouched.
OWNED_METADATA_KEYS = frozenset({
    "format", "format_version", "schema_version", "produced_by", "produced_at",
    "crs_epsg", "color_standard", "color_catalog_json", "profile",
    # Legacy keys this plugin has always written; kept for backward compat.
    "project_version", "export_timestamp", "relations_json",
    "latent_elements_json", "plugin_settings_json",
})

#: Canonical FiberQ layer name -> (fq_type, placement).
#:
#: Placement is an attribute rather than a family of type codes (spec 6.1), so
#: "Indoor OTB" is an ``otb`` that happens to be mounted indoors, not a separate
#: kind of equipment. The reverse map below is what restores the plugin's
#: per-placement layers on import, unchanged.
#:
#: ``to`` and ``otb`` are distinct types on purpose: a termination outlet is not
#: an optical termination box, and collapsing them loses information that cannot
#: be recovered afterwards.
LAYER_TO_TYPE: Dict[str, Tuple[str, Optional[str]]] = {
    "ODF": ("odf", None),
    "TB": ("tb", None),
    "Patch panel": ("patch_panel", None),
    "OTB": ("otb", None),
    "Indoor OTB": ("otb", "indoor"),
    "Outdoor OTB": ("otb", "outdoor"),
    "Pole OTB": ("otb", "pole"),
    "TO": ("to", None),
    "Indoor TO": ("to", "indoor"),
    "Outdoor TO": ("to", "outdoor"),
    "Pole TO": ("to", "pole"),
    "Joint Closure TO": ("to", "closure"),
    "Joint Closures": ("closure.joint", None),
    "Poles": ("pole", None),
    "Manholes": ("manhole", None),
    "Route": ("route", None),
    "Optical slack": ("slack", None),
    "PE pipes": ("duct.pe", None),
    "Transition pipes": ("duct.transition", None),
    "Service Area": ("service_area", None),
    "Objects": ("building", None),
    "Aerial cables": ("cable.aerial", None),
    "Underground cables": ("cable.underground", None),
    "Fiber break": ("fiber_break", None),
}

#: (fq_type, placement) -> canonical layer name. Built from LAYER_TO_TYPE so the
#: two can never drift; a test asserts the round trip.
TYPE_TO_LAYER: Dict[Tuple[str, Optional[str]], str] = {
    v: k for k, v in LAYER_TO_TYPE.items()
}

#: Side-car tables (spec section 6.2). Plain SQL so any SQLite client can read a
#: bundle without a FiberQ-aware tool, which is the point of the format.
SIDECAR_DDL = (
    """CREATE TABLE IF NOT EXISTS fq_splice_point (
        uuid TEXT PRIMARY KEY, element_uuid TEXT NOT NULL,
        port_count INTEGER, used_ports INTEGER, config_json TEXT, notes TEXT)""",
    """CREATE TABLE IF NOT EXISTS fq_fiber_connection (
        uuid TEXT PRIMARY KEY,
        source_element_uuid TEXT, source_cable_uuid TEXT,
        source_tube INTEGER, source_fiber INTEGER, source_port INTEGER,
        source_side TEXT, source_color_hex TEXT,
        dest_element_uuid TEXT, dest_cable_uuid TEXT,
        dest_tube INTEGER, dest_fiber INTEGER, dest_port INTEGER,
        dest_side TEXT, dest_color_hex TEXT,
        connection_type TEXT, loss_db REAL, tray_ref TEXT, notes TEXT)""",
    """CREATE TABLE IF NOT EXISTS fq_relation (
        uuid TEXT PRIMARY KEY, name TEXT, category TEXT)""",
    """CREATE TABLE IF NOT EXISTS fq_relation_member (
        relation_uuid TEXT NOT NULL, member_uuid TEXT NOT NULL,
        order_index INTEGER, role TEXT,
        PRIMARY KEY (relation_uuid, member_uuid))""",
    """CREATE TABLE IF NOT EXISTS fq_container (
        uuid TEXT PRIMARY KEY, host_uuid TEXT NOT NULL,
        host_kind TEXT NOT NULL DEFAULT 'feature',
        kind TEXT, name TEXT, geometry_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS fq_container_slot (
        uuid TEXT PRIMARY KEY, container_uuid TEXT NOT NULL,
        slot_index INTEGER, label TEXT, kind TEXT, spec_json TEXT, status TEXT)""",
    """CREATE TABLE IF NOT EXISTS fq_slot_assignment (
        slot_uuid TEXT NOT NULL, occupant_uuid TEXT NOT NULL,
        direction TEXT, notes TEXT, extra_json TEXT,
        PRIMARY KEY (slot_uuid, occupant_uuid))""",
    """CREATE TABLE IF NOT EXISTS fq_path_stop (
        cable_uuid TEXT NOT NULL, element_uuid TEXT NOT NULL,
        order_index INTEGER NOT NULL, is_latent INTEGER DEFAULT 0,
        PRIMARY KEY (cable_uuid, element_uuid, order_index))""",
    """CREATE TABLE IF NOT EXISTS fq_extension (
        uuid TEXT PRIMARY KEY, owner_uuid TEXT, kind TEXT, namespace TEXT,
        payload_json TEXT NOT NULL, produced_by TEXT)""",
)


#: Every side-car table a bundle may carry, in the order the DDL creates them.
SIDECAR_TABLES = (
    "fq_splice_point", "fq_fiber_connection", "fq_relation", "fq_relation_member",
    "fq_container", "fq_container_slot", "fq_slot_assignment", "fq_path_stop",
    "fq_extension",
)

#: The side-car tables this plugin has a real model for. Everything else in
#: :data:`SIDECAR_TABLES` is read into the passthrough store on import and
#: written back out unchanged on export -- the plugin does not model fibre
#: splices, trays or duct occupancy, and a bundle that carries them must still
#: leave through here complete (spec section 12).
MODELLED_SIDECAR_TABLES = ("fq_relation", "fq_relation_member", "fq_path_stop")

#: Kinds used in the passthrough store. The kind decides how a row leaves again:
#:
#: * ``feature_attributes`` is inlined into the feature's own ``fq_extra_json``
#:   column, because that is where per-feature extras belong (spec section 8);
#: * ``sidecar_table`` is written back into the real side-car table it came
#:   from, so a round trip reproduces the table rather than a blob describing it;
#: * ``unsupported_feature`` and anything else is emitted as an ``fq_extension``
#:   row verbatim.
#: ``bundle_metadata`` holds the ``_fiberq_metadata`` keys another tool wrote.
#: Merging them into the *same* file is section 7's rule; carrying them into the
#: *next* bundle is what makes a round trip through this plugin lossless, and a
#: project is the only place to keep them in between.
EXTENSION_KIND_METADATA = "bundle_metadata"
EXTENSION_KIND_ATTRIBUTES = "feature_attributes"
EXTENSION_KIND_SIDECAR = "sidecar_table"
EXTENSION_KIND_FEATURE = "unsupported_feature"

#: This implementation's namespace for rows it creates in the passthrough store.
EXTENSION_NAMESPACE = "net.fiberq.qgis"


def format_version_parts(value):
    """``(major, minor)`` of a format version string, or ``None`` if unreadable."""
    if not value:
        return None
    parts = str(value).strip().split(".")
    try:
        major = int(parts[0])
    except (ValueError, IndexError):
        return None
    try:
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        minor = 0
    return major, minor


def can_read_format_version(value) -> bool:
    """Whether a reader implementing this spec may read that bundle.

    Spec section 9: a reader must refuse, with a clear error, a bundle whose
    format version has a **major** number it does not implement -- rather than
    importing it partially, which is how a tool ends up confidently holding half
    a network. A newer *minor* version is readable: whatever it added is carried
    through the passthrough store.
    """
    theirs = format_version_parts(value)
    if theirs is None:
        return False
    ours = format_version_parts(FORMAT_VERSION)
    return theirs[0] == ours[0]


def stable_uuid(*parts) -> str:
    """A deterministic identity derived from ``parts``.

    Some things the plugin stores -- relations, most obviously -- are keyed by a
    project-local integer and have no identity of their own. Minting a fresh
    UUID for them on every export would mean the same relation arrives as a new
    object each time, which breaks exactly the diffing the format exists to
    make possible.

    Deriving from the parts instead keeps the identity stable for as long as the
    parts are. It is not a substitute for a real stored identity -- rename the
    relation and you get a different UUID -- but it is stable across repeated
    exports of an unchanged project, which is the case that matters.
    """
    return str(_uuid.uuid5(UUID_NAMESPACE, "|".join(str(p) for p in parts)))


def type_for_layer(layer_name: str) -> Optional[Tuple[str, Optional[str]]]:
    """``fq_type`` and placement for a canonical FiberQ layer name.

    Returns ``None`` for a layer this format has no code for, which the caller
    must treat as "carry it through the passthrough store", never as "skip it".
    """
    return LAYER_TO_TYPE.get(layer_name)


def layer_for_type(fq_type: str, placement: Optional[str] = None) -> Optional[str]:
    """The canonical FiberQ layer that an element of this type belongs in.

    Falls back to the placement-less layer when the exact placement is unknown,
    so an ``otb`` from a tool that does not record placement still lands in the
    OTB layer rather than nowhere.
    """
    exact = TYPE_TO_LAYER.get((fq_type, placement))
    if exact is not None:
        return exact
    return TYPE_TO_LAYER.get((fq_type, None))


def merge_metadata(existing: Dict[str, str], produced: Dict[str, str]) -> Dict[str, str]:
    """Merge bundle metadata, preserving keys written by other tools.

    ``produced`` holds what this export run computed. ``existing`` is whatever
    the target bundle already contained. Keys this implementation owns are
    refreshed; every other key is kept exactly as found.

    This is the whole point: rebuilding the table from scratch -- or dropping and
    recreating it -- silently destroys another tool's data, and the round trip
    that loses it looks successful from both ends.
    """
    merged = dict(existing or {})
    for key, value in (produced or {}).items():
        merged[key] = value
    return merged


def foreign_keys(existing: Dict[str, str]) -> Dict[str, str]:
    """The subset of ``existing`` that this implementation does not own.

    Useful for reporting what a bundle is carrying on behalf of another tool,
    and for asserting in tests that it survived a write.
    """
    return {k: v for k, v in (existing or {}).items() if k not in OWNED_METADATA_KEYS}


def build_metadata(schema_version: str, crs_epsg, plugin_version: str,
                   timestamp: str, color_standard: str = "TIA-598-C") -> Dict[str, str]:
    """The metadata keys this implementation writes for a bundle.

    ``format_version`` describes the *specification*, ``schema_version`` the
    *payload*, and ``produced_by`` the *writer*. Keeping the three apart is not
    pedantry: collapsing a producer's release number into a key that means the
    data-schema version makes version checks meaningless, and that is a mistake
    already present in the de-facto exchange this format replaces.
    """
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "schema_version": str(schema_version),
        "produced_by": f"FiberQ QGIS plugin {plugin_version}",
        "produced_at": timestamp,
        "crs_epsg": str(crs_epsg) if crs_epsg not in (None, "") else "",
        "color_standard": color_standard or "TIA-598-C",
    }
