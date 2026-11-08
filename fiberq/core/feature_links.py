"""Per-feature links (pictures, drawings) that survive being saved.

WP4 FU-2 item U9. FiberQ attaches a picture or a drawing to a single feature
and remembers it in the project, under a key naming the layer and the feature::

    FiberQPlugin/image_map/<layer id>/<feature id>  ->  /photos/pole-12.jpg

QGIS 3 writes project properties as **nested XML elements**, one per path
segment, so that key becomes ``<image_map><Poles_a8c6…><12>``. ``<12>`` is not
a legal XML element name -- a name may not begin with a digit -- so Qt refuses
it, prints ``Calling appendChild() on a null node does nothing.`` and writes the
parent as an empty element. The value is gone. Measured on 3.44.15: a project
saved and reopened loses **every** picture and drawing link, and nothing in the
UI says so.

QGIS 4 writes ``<properties name="12" …>``, putting the key in an *attribute*,
where digits are fine. Measured on 4.0.3: all the same keys survive. So this is
a QGIS 3 defect that a QGIS 4 user never sees, and it is the reason R12's fix
alone was not enough -- the picture a QGIS 4 user can finally open is one a
QGIS 3 save would have unlinked.

**The shape that works.** One entry per kind, at a key with no numeric segment,
holding JSON::

    FiberQPlugin/FeatureLinks/images_v1  ->  {"<layer id>": {"<fid>": "<path>"}}

Measured to survive on both 3.44.15 and 4.0.3.

**Reading the old keys.** :func:`link_get` falls back to the per-feature keys,
under ``FiberQPlugin`` and then the pre-1.0 ``StuboviPlugin`` scope, and
migrates whatever it finds into the JSON entry as it goes, lazily, because the
layer and feature id are always known at the point of use.

It *lists* the layer's old keys before it reads one, and that is not a nicety.
QGIS 3 checks every key segment of a ``readEntry`` -- a read, not only a write
-- and logs "Entry token invalid : '12'. The token will not be saved to file."
at Critical level for a numeric one, whether or not the key exists (measured
on 3.22.16, 3.40.15 and 3.44.15; QGIS 4 no longer has the message -- it is not
in 4.2.3's libqgis_core). The picture watcher asks about every
feature under every click on the map, so reading blind filled QGIS 3's log with
two Critical lines per feature clicked (found in the v1.6.0 QA on 3.40).
``entryList(scope, "image_map/<layer id>")`` names no numeric segment, lists
the feature ids that do have a key, before and after a save, and puts no line
in the log (measured on 3.22.16, 3.40.15, 3.44.15, 4.0.3 and 4.2.3).
``subkeyList`` is the wrong call for this: it lists keys that have keys under
them, and answers ``[]`` here, which is what an earlier version of this note
measured and took to mean the keys could not be enumerated.

**What cannot be recovered.** A link destroyed by an earlier QGIS 3 save is not
in the file any more, so nothing here can bring it back -- after a round trip
``subkeyList`` is empty and ``readEntry`` finds nothing, because the save, not
the load, is where the value was dropped. Links created or re-attached from
v1.6.0 on are safe; older ones have to be attached once more. The release notes
say so.
"""
import json
import re

from qgis.core import Qgis, QgsProject

from ..utils.logger import get_logger

logger = get_logger(__name__)

#: Scope every FiberQ project entry is written under today.
SCOPE = "FiberQPlugin"

#: The pre-1.0 scope, still read so an old project keeps working.
LEGACY_SCOPE = "StuboviPlugin"

#: Kinds of link, as ``(entry key, legacy key prefix)``. The ``_v1`` suffix is
#: part of the contract: a later shape becomes ``_v2`` and this one keeps being
#: read, exactly as the legacy keys are read now.
IMAGES = "images_v1"
DRAWINGS = "drawings_v1"
DRAWING_LAYERS = "drawing_layers_v1"

_LEGACY_PREFIX = {
    IMAGES: "image_map",
    DRAWINGS: "drawing_map",
    DRAWING_LAYERS: "drawing_layers",
}

#: Where the JSON for one kind lives. No segment is numeric, which is the
#: whole point -- see the module docstring.
_ENTRY = "FeatureLinks/%s"


def _project(project=None):
    return project if project is not None else QgsProject.instance()


def _read_all(kind, project=None) -> dict:
    """Every link of one kind, as ``{layer id: {fid: value}}``.

    A key that is missing, empty or not valid JSON reads as "no links": this
    runs on project open, and a damaged entry must not stop the plugin loading.
    """
    raw, _found = _project(project).readEntry(SCOPE, _ENTRY % kind, "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        logger.warning(f"Could not read the {kind} links from the project: {exc}")
        return {}
    if not isinstance(data, dict):
        logger.warning(f"The {kind} links in the project are not a mapping; ignoring them.")
        return {}
    return data


def _write_all(kind, data, project=None) -> bool:
    """Store every link of one kind. True when the project took it."""
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return bool(_project(project).writeEntry(SCOPE, _ENTRY % kind, payload))


def _legacy_parent(kind, layer_id) -> str:
    return f"{_LEGACY_PREFIX[kind]}/{layer_id}"


def _legacy_key(kind, layer_id, fid) -> str:
    return f"{_legacy_parent(kind, layer_id)}/{int(fid)}"


#: A key segment QGIS 3 accepts: an XML name, so no digit, "-" or "." first.
_XML_NAME = re.compile(r"(?![\d.\-])[\w.\-:]+")


def _legacy_fids(prj, scope, kind, layer_id) -> set:
    """The feature ids of one layer that still have an old key under ``scope``.

    Listed, never read blind: see "Reading the old keys" in the module
    docstring. A layer id QGIS 3 would itself log as an invalid token (one that
    starts with a digit: a layer named "2024 survey") is not listed there at
    all, because QGIS 3 cannot have saved a key under it in the first place.
    """
    if Qgis.QGIS_VERSION_INT < 40000 and not _XML_NAME.fullmatch(str(layer_id)):
        return set()
    return set(prj.entryList(scope, _legacy_parent(kind, layer_id)))


def _read_legacy(kind, layer_id, fid, project=None) -> str:
    """The per-feature key's value, under either scope, or ``''``."""
    prj = _project(project)
    key = _legacy_key(kind, layer_id, fid)
    for scope in (SCOPE, LEGACY_SCOPE):
        if str(int(fid)) not in _legacy_fids(prj, scope, kind, layer_id):
            continue
        value = prj.readEntry(scope, key, "")[0]
        if value:
            return value
    return ""


def link_get(kind, layer_id, fid, project=None, default=""):
    """The link stored against one feature, or ``default``.

    Looks in the JSON entry first. A feature absent from it falls back to the
    old per-feature keys, and anything found there is written into the JSON
    entry straight away, so the next save keeps it. A feature *present* in the
    JSON entry is answered from there even when its value is empty: an empty
    value means the user cleared the link, and falling through to a stale old
    key would bring it back.
    """
    layer_id = str(layer_id)
    fid = str(int(fid))
    data = _read_all(kind, project)
    stored = data.get(layer_id)
    if isinstance(stored, dict) and fid in stored:
        return stored[fid]

    legacy = _read_legacy(kind, layer_id, fid, project)
    if not legacy:
        return default
    # Migrate on the way past, where the layer and feature id are known (see
    # "Reading the old keys" in the module docstring). The old keys can be
    # listed a layer at a time, as _legacy_fids does, but nothing sweeps them
    # into the JSON entry in one go.
    if kind == DRAWING_LAYERS:
        value = [part for part in str(legacy).split(",") if part]
    else:
        value = legacy
    link_set(kind, layer_id, fid, value, project)
    return value


def link_set_many(kind, layer_id, values, project=None) -> bool:
    """Store links against many features at once. True when the project took them.

    ``values`` is ``{fid: value}``. The JSON entry is read once and written once
    for the whole batch, which is the whole point: one entry holds every feature
    of a kind, so reading and rewriting it per feature is quadratic in the size
    of the selection -- the blob is parsed and re-serialised each time, and it
    grows with every feature added. Measured on 3.44.15, per feature:

        n=  100    0.061 ms
        n= 1000    0.327 ms
        n= 2000    0.480 ms
        n= 4000    0.936 ms

    Each doubling costs about four times as much in total. "Attach picture" and
    "Clear picture" run over the whole selection, and this project's own largest
    benchmark city has 10,083 poles, so select-all is not a hypothetical size.

    The old per-feature keys are cleared for exactly the features named, as
    :func:`link_set` does for one.
    """
    layer_id = str(layer_id)
    if not values:
        return True
    data = _read_all(kind, project)
    per_layer = data.get(layer_id)
    if not isinstance(per_layer, dict):
        per_layer = {}
        data[layer_id] = per_layer
    for fid, value in values.items():
        per_layer[str(int(fid))] = value
    written = _write_all(kind, data, project)

    prj = _project(project)
    for scope in (SCOPE, LEGACY_SCOPE):
        present = _legacy_fids(prj, scope, kind, layer_id)
        for fid in values:
            if str(int(fid)) in present:
                prj.removeEntry(scope, _legacy_key(kind, layer_id, fid))
    return written


def link_set(kind, layer_id, fid, value, project=None) -> bool:
    """Store a link against one feature. True when the project took it.

    The old per-feature key is cleared at the same time, so a project that
    still has one cannot later contradict this entry.

    One write path: this is :func:`link_set_many` with a single entry, so the
    two cannot drift.
    """
    return link_set_many(kind, layer_id, {fid: value}, project)


def link_clear(kind, layer_id, fid, project=None) -> bool:
    """Forget the link against one feature.

    Recorded as an empty value rather than a removal, so :func:`link_get` does
    not fall back to an old per-feature key and resurrect what the user just
    cleared.
    """
    return link_set(kind, layer_id, fid, "" if kind != DRAWING_LAYERS else [], project)


__all__ = [
    'DRAWINGS', 'DRAWING_LAYERS', 'IMAGES', 'LEGACY_SCOPE', 'SCOPE',
    'link_clear', 'link_get', 'link_set', 'link_set_many',
]
