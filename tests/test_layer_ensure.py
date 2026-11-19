"""The functions that find or make a FiberQ layer or layer group, run on memory layers.

Before they write, many of FiberQ's tools ask for their layer: ``LayerManager``'s ``ensure_*`` methods give the
poles, optical slacks, manholes and pipe layers and the pipe and drawing groups, and module functions give the
layers of Create Service Area, Draw region, the object tools and Change element type. Of the earlier tests that
check these functions, ``test_uuid_creation_invariant.py`` checks that some of them (and the managers' own
copies) give a new layer the identity column, ``test_schema_parity.py`` checks the field lists against the
schema, and ``test_service_area_measure.py`` measures what Create Service Area and Draw region write into a
Service Area layer already in the project. None of them runs a ``LayerManager`` method, hands a function a layer
under a legacy name or of another geometry, or calls one twice.
Over them this file adds what "ensure" promises:

- a first call makes one layer, with the identity column once, and a second call changes nothing;
- a layer under its current name or a legacy one ("Stubovi", "OKNA", "PE cevi", "Rejon", "Objekti", ...) is
  reused with its feature and values, and renamed where the code says so; a layer of another geometry under such
  a name is left alone;
- the legacy groups "CEVI" and "Crteži" are renamed, not doubled, and an empty group is found like a full one;
- the Manholes layer and the Pipes group go to the top of the layer tree, and the Manholes and pipe layers to the
  top of a custom rendering order;
- the two copies of the region function (Create Service Area's and Draw region's) and of the objects function
  reuse each other's layer and make the same one;
- a new layer takes the map canvas's CRS, the manholes style is applied once, and Change element type draws a
  new joint closure layer with a red diamond.

Never a roster: a field list is only compared with itself before and after a call, or with the layer the other
live copy makes.

The functions run as the tools call them, with ``CoreIface`` for QGIS's ``iface`` (a map canvas in EPSG:3857)
and no plugin object (the manholes style has its own test), in a project emptied before and after each test.
Both region copies end in a message box when they fail, and offscreen a message box waits for a click that never
comes: the boxes are answered at once, and the region cases assert that none came.

Known defects are expected failures, strict, each naming its follow-up; the fix removes the marker. Each marked
test raises its own exception for the defect alone, so a premise that fails is a plain failure, never the
expected one. QGIS 4.0's layer-tree nodes are false when they hold nothing, so five markers apply only where the
bindings say so (``NODES_CAN_BE_FALSE``).
"""
import os

import pytest
from qgis.core import (QgsLayerTree, QgsLayerTreeNode, QgsSimpleMarkerSymbolLayer, QgsSimpleMarkerSymbolLayerBase,
                       QgsSvgMarkerSymbolLayer)

from support.core_env import (Core, CoreIface, clean_project, empty_project, memory_layer, record_message_boxes,
                              tree_rows)

from fiberq.core import layer_manager
from fiberq.models.schema import canonical_layer_name
from fiberq.utils import legacy_bridge
from fiberq.utils.uuid_utils import FIBERQ_UUID_ALIAS

UUID = "fiberq_uuid"

#: QGIS 4.0's bindings give layer-tree nodes ``__len__`` (their number of children) and no ``__bool__``, so there
#: an empty group and every layer node are false, and FiberQ's ``if not group`` takes them as missing. 3.22, 3.40
#: and 3.44 have neither, 4.2 has both (measured). Read from the bindings, not from a version number.
NODES_CAN_BE_FALSE = hasattr(QgsLayerTreeNode, "__len__") and not hasattr(QgsLayerTreeNode, "__bool__")

#: A polygon for the region and objects layers.
SQUARE = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"


class SecondCallChanged(AssertionError):
    """A second call of an ensure function changed the project, and no known defect accounts for the change."""


class AliasAddedOnSecondCall(AssertionError):
    """WP5-FU-36: Create Service Area's copy made the identity column without its alias, and its second call added
    the alias and changed nothing else."""


class LayerNotReused(AssertionError):
    """WP5-FU-37: a layer the plugin recognises elsewhere (one of three legacy spellings the schema declares, or
    an Objects layer whose polygons have Z alone) was not reused, and a second layer was made beside it."""


class EmptyGroupTakenAsMissing(AssertionError):
    """WP5-FU-35: on QGIS 4.0 an empty group was taken as missing, and another group was made beside it."""


class TwoPipesGroups(AssertionError):
    """WP5-FU-38: with both a "CEVI" and a "Pipes" group, "CEVI" was renamed to a second "Pipes"."""


class NotMovedToTop(AssertionError):
    """WP5-FU-35: the layer or group was not moved to the top of the layer tree."""


class CopiesDiffer(AssertionError):
    """WP5-FU-36: the two copies of the function gave the identity column different aliases."""


class CustomOrderNotUpdated(AssertionError):
    """WP5-FU-35: on QGIS 4.0 the Manholes layer did not go to the top of the custom rendering order."""


class JointClosureNotDiamond(AssertionError):
    """WP5-FU-5: Change element type drew a new joint closure layer as a red circle, not a red diamond."""


_REGION_ALIAS = pytest.mark.xfail(
    strict=True, raises=AliasAddedOnSecondCall,
    reason="WP5-FU-36: Create Service Area's copy makes fiberq_uuid without its alias, and the next call adds it; "
           "the v1.8.0 fix removes this marker")
_SUBGROUP_TWICE = pytest.mark.xfail(
    NODES_CAN_BE_FALSE, strict=True, raises=EmptyGroupTakenAsMissing,
    reason="WP5-FU-35: on QGIS 4.0 the empty Joint Closures subgroup is taken as missing, so a second call adds "
           "another; the v1.8.0 fix removes this marker")


@pytest.fixture
def project(qgis_app):
    with clean_project() as prj:
        yield prj


@pytest.fixture(autouse=True)
def said(monkeypatch):
    """The texts of the message boxes the code raised. Both region copies end in ``QMessageBox.critical`` when
    they fail (``core/layer_manager.py`` and ``utils/legacy_bridge.py``, ``_ensure_region_layer``)."""
    return record_message_boxes(monkeypatch)


def _ensure(key):
    """Call the function behind ``key`` as its tool calls it; return what it gives back."""
    manager = layer_manager.LayerManager(CoreIface(), None)
    core = Core(CoreIface())
    calls = {
        "poles": manager.ensure_poles_layer,
        "slack": manager.ensure_slack_layer,
        "manholes": manager.ensure_manholes_layer,
        "pe_pipes": lambda: manager.ensure_pipe_layer("PE cevi"),
        "transition_pipes": lambda: manager.ensure_pipe_layer("Prelazne cevi"),
        "pipes_group": manager.ensure_pipes_group,
        "drawings_group": lambda: manager.ensure_drawings_group("Joint Closures"),
        "region_lm": lambda: layer_manager._ensure_region_layer(core),
        "region_lb": lambda: legacy_bridge._ensure_region_layer(core),
        "objects_lm": lambda: layer_manager._ensure_objects_layer(core),
        "objects_lb": lambda: legacy_bridge._ensure_objects_layer(core),
        "element_odf": lambda: layer_manager._ensure_element_layer_with_style(core, "ODF"),
        "joint_closures": lambda: layer_manager._ensure_element_layer_with_style(core, "Joint Closures"),
        "patch_panel": lambda: layer_manager._ensure_element_layer_with_style(core, "Patch panel"),
    }
    return calls[key]()


def _names(project):
    return sorted(layer.name() for layer in project.mapLayers().values())


def _top_rows(project):
    """The top level of the layer tree, as ``tree_rows`` gives it."""
    return [row for row in tree_rows(project.layerTreeRoot()) if not row.startswith(" ")]


def _snapshot(project):
    """Everything a call may change: the layer tree (groups by name, layers by id, nested) and each layer."""
    return {"tree": _tree(project.layerTreeRoot()),
            "layers": {layer_id: _layer_snapshot(layer) for layer_id, layer in project.mapLayers().items()}}


def _tree(node):
    out = []
    for child in node.children():
        if QgsLayerTree.isGroup(child):
            out.append(("group", child.name(), _tree(child)))
        else:
            out.append(("layer", child.layerId()))
    return out


def _changes(before, after):
    """What differs between two snapshots: the tree, a layer added or removed, or a property of a layer."""
    changes = [] if before["tree"] == after["tree"] else ["tree %r -> %r" % (before["tree"], after["tree"])]
    for layer_id in sorted(set(before["layers"]) | set(after["layers"])):
        old, new = before["layers"].get(layer_id), after["layers"].get(layer_id)
        if old is None or new is None:
            changes.append("%s %s" % ((new or old)["name"], "added" if old is None else "removed"))
        else:
            changes.extend("%s %s %r -> %r" % (old["name"], name, old[name], new[name])
                           for name in old if old[name] != new[name])
    return changes


def _layer_snapshot(layer):
    """A layer's name, fields with their aliases, styles, renderer type, number of symbol layers, labels on or off
    and number of features; never a size or a unit."""
    renderer = layer.renderer()
    symbol = renderer.symbol() if renderer is not None and hasattr(renderer, "symbol") else None
    return {
        "name": layer.name(),
        "fields": [(field.name(), layer.attributeAlias(index)) for index, field in enumerate(layer.fields())],
        "styles": list(layer.styleManager().styles()),
        "renderer": renderer.type() if renderer is not None else None,
        "symbol_layers": symbol.symbolLayerCount() if symbol is not None else None,
        "labels": layer.labelsEnabled(),
        "features": layer.featureCount(),
    }


def _layer_build(layer):
    """What _layer_snapshot leaves out of a layer: each field's type, length and precision, the geometry type, the CRS
    and the symbol's opacity."""
    renderer = layer.renderer()
    symbol = renderer.symbol() if renderer is not None and hasattr(renderer, "symbol") else None
    return {
        "fields": [(field.name(), field.typeName(), field.length(), field.precision()) for field in layer.fields()],
        "geometry": layer.wkbType(),
        "crs": layer.crs().authid(),
        "opacity": symbol.opacity() if symbol is not None else None,
    }


def _rows(layer):
    """Each feature of a layer as (geometry WKT, attribute values)."""
    return [(feature.geometry().asWkt(), feature.attributes()) for feature in layer.getFeatures()]


# ---------------------------------------------------------------------------
# A first call, and a second one
# ---------------------------------------------------------------------------

#: What a first call makes in an empty project: the layer's name, or the layer tree for the two groups.
FIRST = {
    "poles": "Poles",
    "slack": "Optical slacks",
    "manholes": "Manholes",
    "pe_pipes": "PE pipes",
    "transition_pipes": "Transition pipes",
    "pipes_group": ["G:Pipes"],
    "drawings_group": ["G:Drawings", "  G:Joint Closures"],
    "region_lm": "Service Area",
    "region_lb": "Service Area",
    "objects_lm": "Objects",
    "objects_lb": "Objects",
    "element_odf": "ODF",
}

_SECOND_CALL_MARKS = {"region_lm": _REGION_ALIAS, "drawings_group": _SUBGROUP_TWICE}


@pytest.mark.parametrize("key", [pytest.param(key, marks=_SECOND_CALL_MARKS.get(key, ())) for key in FIRST])
def test_a_first_call_makes_one_layer_and_a_second_call_changes_nothing(project, said, key):
    first = _ensure(key)
    assert said == [], "a message box came up: %s" % said
    assert first is not None, "the first call made nothing"
    if isinstance(FIRST[key], list):
        assert tree_rows(project.layerTreeRoot()) == FIRST[key]
        assert _names(project) == []
    else:
        assert list(project.mapLayers()) == [first.id()]
        assert first.name() == FIRST[key]
        assert first.fields().names().count(UUID) == 1
    before = _snapshot(project)
    built = None if isinstance(FIRST[key], list) else _layer_build(first)
    second = _ensure(key)
    after = _snapshot(project)
    assert said == [], "a message box came up: %s" % said
    assert second is not None, "the second call gave nothing back"
    same = second.name() == first.name() if isinstance(FIRST[key], list) else second.id() == first.id()
    changes = _changes(before, after) if same else ["it gave back another one"] + _changes(before, after)
    if changes and key == "region_lm":
        # WP5-FU-36's change and nothing else: on the layer given back, the identity column gains its alias.
        assert same and after["tree"] == before["tree"] and list(after["layers"]) == [first.id()], changes
        old, new = before["layers"][first.id()], after["layers"][first.id()]
        assert [name for name in old if old[name] != new[name]] == ["fields"], changes
        assert [f for f in old["fields"] if f[0] != UUID] == [f for f in new["fields"] if f[0] != UUID], changes
        assert dict(old["fields"])[UUID] == "" and dict(new["fields"])[UUID] == FIBERQ_UUID_ALIAS, changes
        assert _layer_build(first) == built, "the second call also changed %s" % (_layer_build(first),)
        raise AliasAddedOnSecondCall("the second call gave %s the alias %r" % (UUID, dict(new["fields"])[UUID]))
    if changes and key == "drawings_group":
        # WP5-FU-35's change on QGIS 4.0 and nothing else: a second empty Joint Closures subgroup under Drawings.
        assert same and after["layers"] == before["layers"], changes
        assert after["tree"] == [("group", "Drawings", [("group", "Joint Closures", [])] * 2)], changes
        assert second is project.layerTreeRoot().children()[0].children()[1], "the second call gave back another group"
        raise EmptyGroupTakenAsMissing("the second call added another empty Joint Closures subgroup")
    if changes:
        raise SecondCallChanged("the second call of %s changed the project: %s" % (key, "; ".join(changes)))


# ---------------------------------------------------------------------------
# A layer the project already holds
# ---------------------------------------------------------------------------

#: A layer under a current or legacy name the function looks for: id -> (key, geometry, name, fields, row WKT,
#: row values, its name after the call). The region copies rename "Rejon", and the pipe layers take their English
#: names (``utils/field_aliases.set_pipe_layer_alias``); the others keep theirs.
REUSED = {
    "poles_stubovi": ("poles", "Point", "Stubovi", ("tip", "visina:double"), "POINT(10 20)",
                      {"tip": "drveni", "visina": 9.0}, "Stubovi"),
    "manholes_okna": ("manholes", "Point", "OKNA", ("broj_okna",), "POINT(30 40)", {"broj_okna": "O-1"}, "OKNA"),
    "manholes_okna_space": ("manholes", "Point", "OKNA ", ("broj_okna",), "POINT(30 40)", {"broj_okna": "O-1"},
                            "OKNA "),
    "slack_opticke_rezerve": ("slack", "Point", "Opticke_rezerve", ("duzina_m:double",), "POINT(1 1)",
                              {"duzina_m": 20.0}, "Opticke_rezerve"),
    "slack_singular": ("slack", "Point", "Optical slack", ("duzina_m:double",), "POINT(1 1)", {"duzina_m": 15.0},
                       "Optical slack"),
    "pe_cevi": ("pe_pipes", "LineString", "PE cevi", ("materijal",), "LINESTRING(0 0, 50 0)", {"materijal": "PE"},
                "PE pipes"),
    "prelazne_cevi": ("transition_pipes", "LineString", "Prelazne cevi", ("materijal",), "LINESTRING(0 0, 0 50)",
                      {"materijal": "PVC"}, "Transition pipes"),
    "rejon_lm": ("region_lm", "Polygon", "Rejon", ("name",), SQUARE, {"name": "R1"}, "Service Area"),
    "rejon_lb": ("region_lb", "Polygon", "Rejon", ("name",), SQUARE, {"name": "R1"}, "Service Area"),
    "objekti_lm": ("objects_lm", "Polygon", "Objekti", ("tip",), SQUARE, {"tip": "stambeni"}, "Objekti"),
    "objekti_lb": ("objects_lb", "Polygon", "Objekti", ("tip",), SQUARE, {"tip": "stambeni"}, "Objekti"),
    "objekti_multipolygon": ("objects_lm", "MultiPolygon", "Objekti", ("tip",),
                             "MULTIPOLYGON(((0 0, 10 0, 10 10, 0 10, 0 0)))", {"tip": "stambeni"}, "Objekti"),
    "element_odf": ("element_odf", "Point", "ODF", ("naziv",), "POINT(5 5)", {"naziv": "ODF-1"}, "ODF"),
}


@pytest.mark.parametrize("case", list(REUSED))
def test_a_layer_under_a_current_or_legacy_name_is_reused(project, said, case):
    key, geometry, name, fields, wkt, values, name_after = REUSED[case]
    held = memory_layer(project, geometry, name, [(wkt, values)], fields)
    got = _ensure(key)
    assert said == [], "a message box came up: %s" % said
    assert got is not None and got.id() == held.id(), "a second layer was made: %s" % _names(project)
    assert len(project.mapLayers()) == 1
    assert got.name() == name_after
    assert got.featureCount() == 1
    feature = next(got.getFeatures())
    assert {field: feature[field] for field in values} == values
    assert got.fields().names().count(UUID) == 1
    before = _snapshot(project)
    _ensure(key)
    changes = _changes(before, _snapshot(project))
    if changes:
        raise SecondCallChanged("the second call of %s changed the project: %s" % (key, "; ".join(changes)))


#: A layer under a name or geometry the plugin recognises elsewhere, but the function does not: three of the
#: schema's legacy spellings (``models/schema.LAYER_NAME_ALIASES``; Place Joint Closure reuses "Nastavci") and
#: Objects polygons with Z alone: id -> (key, geometry, name, fields, row WKT, row values, the name of the layer
#: the call makes beside it today).
RECOGNISED = {
    "service_area_lm": ("region_lm", "Polygon", "Service area", ("name",), SQUARE, {"name": "R1"}, "Service Area"),
    "service_area_lb": ("region_lb", "Polygon", "Service area", ("name",), SQUARE, {"name": "R1"}, "Service Area"),
    "objekti_polygonz": ("objects_lm", "PolygonZ", "Objekti", ("tip",),
                         "POLYGONZ((0 0 1, 10 0 1, 10 10 1, 0 10 1, 0 0 1))", {"tip": "stambeni"}, "Objects"),
    "objects_multipolygonz": ("objects_lb", "MultiPolygonZ", "Objects", ("tip",),
                              "MULTIPOLYGONZ(((0 0 1, 10 0 1, 10 10 1, 0 10 1, 0 0 1)))", {"tip": "stambeni"},
                              "Objects"),
    "nastavci": ("joint_closures", "Point", "Nastavci", ("naziv",), "POINT(5 5)", {"naziv": "N-1"}, "Joint Closures"),
    "patch_panel": ("patch_panel", "Point", "Patch Panel", ("naziv",), "POINT(5 5)", {"naziv": "PP-1"}, "Patch panel"),
}


@pytest.mark.xfail(strict=True, raises=LayerNotReused,
                   reason="WP5-FU-37: the ensure functions miss three of the schema's legacy spellings and Objects "
                          "polygons with Z alone; the v1.8.0 fix removes this marker")
@pytest.mark.parametrize("case", list(RECOGNISED))
def test_a_layer_under_a_name_or_geometry_the_plugin_recognises_is_reused(project, said, case):
    key, geometry, name, fields, wkt, values, made = RECOGNISED[case]
    assert canonical_layer_name(name) == made, "premise: the schema takes %r for the layer %r" % (name, made)
    held = memory_layer(project, geometry, name, [(wkt, values)], fields)
    held_before, held_rows = _layer_snapshot(held), _rows(held)
    got = _ensure(key)
    assert said == [], "a message box came up: %s" % said
    assert got is not None, "the call made nothing"
    if got.id() != held.id():
        # WP5-FU-37's change and nothing else: the held layer stays as it was, and one more is made beside it.
        assert sorted(project.mapLayers()) == sorted([held.id(), got.id()]), _names(project)
        assert (held.name(), held.featureCount(), got.name()) == (name, 1, made), _names(project)
        assert (_layer_snapshot(held), _rows(held)) == (held_before, held_rows), "the held layer changed: %s %s" % (
            _layer_snapshot(held), _rows(held))
        raise LayerNotReused("%r was not reused: the project holds %s" % (name, _names(project)))


#: A layer under a name the function looks for, but of another geometry: id -> (key, geometry, name, the name of
#: the layer the call makes).
OTHER_GEOMETRY = {
    "stubovi_as_line": ("poles", "LineString", "Stubovi", "Poles"),
    "okna_as_polygon": ("manholes", "Polygon", "OKNA", "Manholes"),
    "objekti_as_point": ("objects_lm", "Point", "Objekti", "Objects"),
    "rejon_as_line": ("region_lb", "LineString", "Rejon", "Service Area"),
    "pe_cevi_as_point": ("pe_pipes", "Point", "PE cevi", "PE pipes"),
}


@pytest.mark.parametrize("case", list(OTHER_GEOMETRY))
def test_a_layer_of_another_geometry_is_left_alone(project, said, case):
    key, geometry, name, made = OTHER_GEOMETRY[case]
    other = memory_layer(project, geometry, name, fields=("a",))
    got = _ensure(key)
    assert said == [], "a message box came up: %s" % said
    assert got is not None and got.id() != other.id()
    assert got.name() == made
    assert other.name() == name
    assert other.fields().names() == ["a"], "the other layer got a column"
    assert len(project.mapLayers()) == 2


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def test_a_legacy_pipes_group_is_renamed_not_doubled(project):
    root = project.layerTreeRoot()
    memory_layer(project, "LineString", "in CEVI", fields=("a",), group=root.addGroup("CEVI"))
    _ensure("pipes_group")
    _ensure("pipes_group")
    assert tree_rows(root) == ["G:Pipes", "  L:in CEVI"]


def test_a_legacy_drawings_group_is_renamed_and_holds_the_subgroup(project):
    root = project.layerTreeRoot()
    memory_layer(project, "Point", "in Crteži", fields=("a",), group=root.addGroup("Crteži"))
    sub = _ensure("drawings_group")
    assert tree_rows(root) == ["G:Drawings", "  L:in Crteži", "  G:Joint Closures"]
    assert (sub.name(), sub.parent().name()) == ("Joint Closures", "Drawings")


def test_a_drawings_subgroup_that_holds_a_layer_is_reused(project):
    sub = _ensure("drawings_group")
    memory_layer(project, "Point", "dwg", fields=("a",), group=sub)
    again = _ensure("drawings_group")
    assert again.name() == "Joint Closures"
    assert tree_rows(project.layerTreeRoot()) == ["G:Drawings", "  G:Joint Closures", "    L:dwg"]


@pytest.mark.xfail(NODES_CAN_BE_FALSE, strict=True, raises=EmptyGroupTakenAsMissing,
                   reason="WP5-FU-35: on QGIS 4.0 an empty group is taken as missing, and another is made beside "
                          "it; the v1.8.0 fix removes this marker")
@pytest.mark.parametrize("group,key,rows,defect", [
    pytest.param("CEVI", "pipes_group", ["G:Pipes"], ["G:Pipes", "G:CEVI"], id="CEVI"),
    pytest.param("Crteži", "drawings_group", ["G:Drawings", "  G:Joint Closures"],
                 ["G:Crteži", "G:Drawings", "  G:Joint Closures"], id="Crtezi"),
    pytest.param("Drawings", "drawings_group", ["G:Drawings", "  G:Joint Closures"],
                 ["G:Drawings", "G:Drawings", "  G:Joint Closures"], id="Drawings"),
])
def test_an_empty_group_is_found_like_a_full_one(project, group, key, rows, defect):
    root = project.layerTreeRoot()
    root.addGroup(group)
    given = _ensure(key)
    got = tree_rows(root)
    if got != rows:
        # WP5-FU-35's change on QGIS 4.0 and nothing else: the empty group stays, and another is made beside it.
        assert got == defect, got
        made = root.children()[0] if key == "pipes_group" else root.children()[1].children()[0]
        assert given is made, "the call gave back %r" % (None if given is None else given.name(),)
        raise EmptyGroupTakenAsMissing("an empty %r gave %s, not %s" % (group, got, rows))


@pytest.mark.xfail(strict=True, raises=TwoPipesGroups,
                   reason="WP5-FU-38: with both a CEVI and a Pipes group, CEVI is renamed to a second Pipes; the "
                          "v1.8.0 fix removes this marker")
def test_cevi_and_pipes_together_give_one_pipes_group(project):
    root = project.layerTreeRoot()
    for name in ("CEVI", "Pipes"):
        memory_layer(project, "LineString", "in " + name, fields=("a",), group=root.addGroup(name))
    given = _ensure("pipes_group")
    layers = sorted(row.strip() for row in tree_rows(root) if row.strip().startswith("L:"))
    assert layers == ["L:in CEVI", "L:in Pipes"], "premise: both layers stay in the tree: %s" % tree_rows(root)
    if _top_rows(project).count("G:Pipes") != 1:
        # WP5-FU-38's change and nothing else: CEVI renamed to Pipes beside the Pipes group, each with its layer.
        assert tree_rows(root) == ["G:Pipes", "  L:in CEVI", "G:Pipes", "  L:in Pipes"], tree_rows(root)
        assert given is root.children()[0], "the call gave back %r" % (None if given is None else given.name(),)
        raise TwoPipesGroups("the top of the layer tree reads %s" % _top_rows(project))


# ---------------------------------------------------------------------------
# To the top of the layer tree
# ---------------------------------------------------------------------------

def test_the_manholes_layer_keeps_one_tree_node(project):
    manholes = memory_layer(project, "Point", "Manholes", fields=("broj_okna",))
    memory_layer(project, "Point", "Other", fields=("a",))
    got = [_ensure("manholes"), _ensure("manholes")]
    assert [None if layer is None else layer.id() for layer in got] == [manholes.id()] * 2
    nodes = [node for node in project.layerTreeRoot().findLayers() if node.layerId() == manholes.id()]
    assert len(nodes) == 1


@pytest.mark.xfail(strict=True, raises=NotMovedToTop,
                   reason="WP5-FU-35: move_layer_to_top hands takeChild an index, so it never moves a node, and on "
                          "QGIS 4.0 it stops before that; the v1.8.0 fix removes this marker")
def test_the_manholes_layer_is_moved_to_the_top(project):
    manholes = memory_layer(project, "Point", "Manholes", fields=("broj_okna",))
    memory_layer(project, "Point", "Other", fields=("a",))
    root = project.layerTreeRoot()
    assert tree_rows(root) == ["L:Other", "L:Manholes"]
    got = _ensure("manholes")
    assert got is not None and got.id() == manholes.id()
    if tree_rows(root)[0] != "L:Manholes":
        # WP5-FU-35's effect and nothing else: the tree as it was.
        assert tree_rows(root) == ["L:Other", "L:Manholes"], tree_rows(root)
        raise NotMovedToTop("the layer tree reads %s" % tree_rows(root))


@pytest.mark.xfail(strict=True, raises=NotMovedToTop,
                   reason="WP5-FU-35: move_group_to_top hands takeChild an index, so it never moves a node; the "
                          "v1.8.0 fix removes this marker")
def test_the_pipes_group_is_moved_to_the_top(project):
    root = project.layerTreeRoot()
    for name in ("Other", "Pipes"):
        memory_layer(project, "Point", "in " + name, fields=("a",), group=root.addGroup(name))
    assert _top_rows(project) == ["G:Other", "G:Pipes"]
    got = _ensure("pipes_group")
    # The pipe tool adds its new layer to the group this call gives back, so it must be the group in the tree.
    assert got is not None and got is root.findGroup("Pipes"), "premise: the call gives back the tree's Pipes group"
    if _top_rows(project) != ["G:Pipes", "G:Other"]:
        # WP5-FU-35's effect and nothing else: the tree as it was.
        assert tree_rows(root) == ["G:Other", "  L:in Other", "G:Pipes", "  L:in Pipes"], tree_rows(root)
        raise NotMovedToTop("the top of the layer tree reads %s" % _top_rows(project))


# ---------------------------------------------------------------------------
# The two copies of the region and objects functions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pair", [
    pytest.param(("region_lm", "region_lb"), id="region", marks=pytest.mark.xfail(
        strict=True, raises=CopiesDiffer,
        reason="WP5-FU-36: Create Service Area's copy makes fiberq_uuid without the alias Draw region's copy "
               "gives it; the v1.8.0 fix removes this marker")),
    pytest.param(("objects_lm", "objects_lb"), id="objects"),
])
def test_the_two_copies_reuse_each_others_layer_and_make_the_same_one(project, said, pair):
    for maker, user in (pair, pair[::-1]):
        empty_project(project)
        made = _ensure(maker)
        got = _ensure(user)
        assert said == [], "a message box came up: %s" % said
        assert made is not None and got is not None and got.id() == made.id(), "%s made a second layer" % user
        assert list(project.mapLayers()) == [made.id()]
    alone, built = [], []
    for key in pair:
        empty_project(project)
        layer = _ensure(key)
        alone.append(_layer_snapshot(layer))
        built.append(_layer_build(layer))
    assert said == [], "a message box came up: %s" % said
    differ = {name: (alone[0][name], alone[1][name]) for name in alone[0] if alone[0][name] != alone[1][name]}
    fields = differ.pop("fields", None)
    assert not differ, "%s and %s make different layers: %s" % (pair[0], pair[1], differ)
    if fields is not None:
        assert [name for name, _ in fields[0]] == [name for name, _ in fields[1]], fields
        aliased = sorted(name for (name, one), (_, other) in zip(*fields) if one != other)
        assert aliased == [UUID], "only the identity column's alias may differ: %s" % (fields,)
        # WP5-FU-36's difference and nothing else: Create Service Area's copy leaves out Draw region's alias.
        assert (dict(fields[0])[UUID], dict(fields[1])[UUID]) == ("", FIBERQ_UUID_ALIAS), fields
        assert built[0] == built[1], "%s and %s also build different layers: %s" % (pair[0], pair[1], built)
        raise CopiesDiffer("%s and %s give %s different aliases: %s" % (pair[0], pair[1], UUID, fields))


# ---------------------------------------------------------------------------
# A custom rendering order (Layers panel > Control rendering order)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(NODES_CAN_BE_FALSE, strict=True, raises=CustomOrderNotUpdated,
                   reason="WP5-FU-35: on QGIS 4.0 a layer node is taken as missing, so move_layer_to_top stops "
                          "before the custom order; the v1.8.0 fix removes this marker")
def test_the_manholes_layer_draws_on_top_in_a_custom_order(project):
    other = memory_layer(project, "Point", "Other", fields=("a",))
    manholes = memory_layer(project, "Point", "Manholes", fields=("broj_okna",))
    root = project.layerTreeRoot()
    root.setHasCustomLayerOrder(True)
    root.setCustomLayerOrder([other, manholes])
    assert [layer.id() for layer in root.customLayerOrder()] == [other.id(), manholes.id()]
    for call in (1, 2):
        got = _ensure("manholes")
        assert got is not None and got.id() == manholes.id()
        order = [layer.name() for layer in root.customLayerOrder()]
        if call == 1 and order != ["Manholes", "Other"]:
            # WP5-FU-35's effect on QGIS 4.0 and nothing else: the order as it was.
            assert order == ["Other", "Manholes"], "after call 1 the custom order reads %s" % order
            raise CustomOrderNotUpdated("after call 1 the custom order reads %s" % order)
        assert order == ["Manholes", "Other"], "after call %d the custom order reads %s" % (call, order)


def test_a_new_pipe_layer_draws_on_top_in_a_custom_order(project):
    other = memory_layer(project, "Point", "Other", fields=("a",))
    root = project.layerTreeRoot()
    root.setHasCustomLayerOrder(True)
    assert [layer.id() for layer in root.customLayerOrder()] == [other.id()]
    pipes = _ensure("pe_pipes")
    assert [layer.id() for layer in root.customLayerOrder()] == [pipes.id(), other.id()]


# ---------------------------------------------------------------------------
# The manholes style, the canvas CRS and Change element type's joint closure
# ---------------------------------------------------------------------------

class _ManholeStyle:
    """The plugin's manholes styler (``FiberQPlugin._apply_manhole_style``), keeping the ids it is handed."""

    def __init__(self):
        self.styled = []

    def _apply_manhole_style(self, layer):
        self.styled.append(layer.id())


def test_a_new_manholes_layer_is_styled_once(project):
    plugin = _ManholeStyle()
    manager = layer_manager.LayerManager(CoreIface(), plugin)
    first = manager.ensure_manholes_layer()
    manager.ensure_manholes_layer()
    assert plugin.styled == [first.id()]


def test_a_new_layer_takes_the_canvas_crs(project):
    """EPSG:32634, so that the EPSG:3857 the code falls back on cannot pass for it."""
    manager = layer_manager.LayerManager(CoreIface(crs="EPSG:32634"), None)
    made = [manager.ensure_poles_layer(), manager.ensure_slack_layer(), manager.ensure_manholes_layer(),
            manager.ensure_pipe_layer("PE cevi")]
    assert {layer.name(): layer.crs().authid() for layer in made} == {
        "Poles": "EPSG:32634", "Optical slacks": "EPSG:32634", "Manholes": "EPSG:32634", "PE pipes": "EPSG:32634"}


#: The two red diamonds a joint closure may be drawn with: the simple marker of the joint closure's own definition
#: (``NASTAVAK_DEF``), or the icon Place Joint Closure draws (``tools/extension_tool.py``).
RED_DIAMONDS = (("diamond", (255, 0, 0)), "map_joint_closure.svg")


def _drawn_as(marker):
    """What a symbol layer draws: (shape, colour) for a simple marker, the file name for an SVG marker, else its
    type. Never a size."""
    if isinstance(marker, QgsSimpleMarkerSymbolLayer):
        colour = marker.color()
        return (QgsSimpleMarkerSymbolLayerBase.encodeShape(marker.shape()),
                (colour.red(), colour.green(), colour.blue()))
    if isinstance(marker, QgsSvgMarkerSymbolLayer):
        return os.path.basename(marker.path())
    return marker.layerType()


@pytest.mark.xfail(strict=True, raises=JointClosureNotDiamond,
                   reason="WP5-FU-5: Change element type draws a new Joint Closures layer with a circle, not a red "
                          "diamond; the v1.8.0 fix removes this marker")
def test_change_element_type_draws_a_new_joint_closures_layer_as_a_red_diamond(project):
    layer = _ensure("joint_closures")
    assert _names(project) == ["Joint Closures"]
    renderer = layer.renderer()
    assert renderer is not None and renderer.type() == "singleSymbol"
    symbol = renderer.symbol()
    assert symbol.symbolLayerCount() == 1
    drawn = _drawn_as(symbol.symbolLayer(0))
    if drawn not in RED_DIAMONDS:
        # WP5-FU-5's effect and nothing else: a red circle.
        assert drawn == ("circle", (255, 0, 0)), drawn
        raise JointClosureNotDiamond("a new Joint Closures layer draws %r, not one of %r" % (drawn, RED_DIAMONDS))
