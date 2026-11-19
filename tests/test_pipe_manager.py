"""The pipe tool's two layers, made once in the Pipes group, and the list of pipes with their descriptions.

The pipe tool asks the pipe manager for its PE and transition pipe layers, and the pipe list reads every pipe
through it. In the plugin the pipe manager hands the layers to the layer manager and the list to the data manager.
No earlier test ran the hand-over of the layers (test_uuid_creation_invariant.py builds a pipe manager with no
layer manager, so it runs the pipe manager's own copy, which the plugin runs only if the layer manager raises), and none
checked what the pipe list says. These tests drive the pipe manager as the plugin wires it, and give the first known
answers for the descriptions the pipe list shows.

The order of the two layers inside the Pipes group is not pinned: today the newer layer stays below the older one,
because the move to the top of the group does nothing, and a fix of that move turns the order round.
"""
import operator

import pytest
from qgis.core import QgsWkbTypes

from support.core_env import CoreIface, clean_project, memory_layer, tree_rows, wired_plugin

#: The pipe rows of the list test and what the list shows for each, as (attributes, (description, capacity, from,
#: to)). The capacity is the diameter and the capacity text, joined by " | " when both are there; the description
#: puts the material, or "Pipe" when there is none, before it.
ROWS = [
    ({"materijal": "PE", "kapacitet": "2x40", "fi": 40, "od": "MH1", "do": "MH2"},
     ("PE Ø 40 mm | 2x40", "Ø 40 mm | 2x40", "MH1", "MH2")),
    ({"materijal": None, "kapacitet": "", "fi": None}, ("Pipe", "", "", "")),
    ({"materijal": "HDPE", "kapacitet": None, "fi": 110}, ("HDPE Ø 110 mm", "Ø 110 mm", "", "")),
]


@pytest.fixture
def project(qgis_app):
    with clean_project() as prj:
        yield prj


def test_the_pipe_tools_two_layers_are_made_once_in_the_pipes_group(project):
    """Each layer is made on the first call, in the map canvas's CRS, and found again on the second; both go into
    a new Pipes group above the project's other groups."""
    root = project.layerTreeRoot()
    root.addGroup("Routes")
    pipes = wired_plugin(CoreIface(crs="EPSG:32634")).pipe_manager

    pe, transition = pipes.ensure_pe_pipe_layer(), pipes.ensure_transition_pipe_layer()
    assert (pe.name(), transition.name()) == ("PE pipes", "Transition pipes")
    for layer in (pe, transition):
        assert layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry
        assert layer.crs().authid() == "EPSG:32634"
        assert layer.fields().names().count("fiberq_uuid") == 1

    again = [pipes.ensure_pe_pipe_layer(), pipes.ensure_transition_pipe_layer()]
    assert [layer.id() for layer in again] == [pe.id(), transition.id()]
    assert len(project.mapLayers()) == 2
    rows = tree_rows(root)
    assert len(rows) == 4
    assert [rows[0], rows[3]] == ["G:Pipes", "G:Routes"]
    assert sorted(rows[1:3]) == ["  L:PE pipes", "  L:Transition pipes"]


def test_every_pipe_is_listed_with_its_description(project):
    """Every feature of a pipe layer is listed, with its description, capacity and ends; a line layer of another
    name is not."""
    pe = memory_layer(project, "LineString", "PE pipes", [("LINESTRING(0 0, 10 0)", attributes)
                                                          for attributes, _ in ROWS],
                      fields=("materijal", "kapacitet", "fi:integer", "od", "do"))
    memory_layer(project, "LineString", "Routes not pipes", [("LINESTRING(0 5, 10 5)", {"materijal": "PE"})],
                 fields=("materijal", "kapacitet", "fi:integer", "od", "do"))

    listed = sorted(wired_plugin(CoreIface()).pipe_manager.list_all_pipes(), key=operator.itemgetter("fid"))
    assert [row["fid"] for row in listed] == [1, 2, 3]
    assert [(row["opis"], row["kapacitet"], row["od"], row["do"]) for row in listed] == [shown for _, shown in ROWS]
    assert {(row["layer_id"], row["layer_name"], row["tip"], row["podtip"], row["color_code"]) for row in listed} == {
        (pe.id(), "PE pipes", "pipe", "pipe", "")}
