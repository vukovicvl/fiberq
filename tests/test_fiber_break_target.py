"""The fiber break tool must only ever target a cable.

It writes its hit into ``cable_layer_id``, and B1/B2 read that as a cable
reference. Until v1.4.0 the tool iterated *every* line layer in the project, so
a click near a trench recorded the break against Route -- found in a real
project, where the resulting reference resolved and so passed validation.

The tool needs a live canvas to construct, so this drives the layer-selection
method directly, which is where the defect was.
"""
import pytest
from qgis.core import QgsProject, QgsVectorLayer

from fiberq.addons.fiber_break import FiberBreakTool


def _line_layer(name):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857&field=fid:integer", name, "memory")
    assert layer.isValid()
    return layer


@pytest.fixture
def populated_project(qgis_app):
    project = QgsProject.instance()
    project.clear()
    added = {}
    for name in ("Underground cables", "Aerial cables", "Route",
                 "PE pipes", "Transition pipes"):
        layer = _line_layer(name)
        project.addMapLayer(layer)
        added[name] = layer
    yield added
    project.clear()


def test_only_cable_layers_are_offered(populated_project):
    tool = FiberBreakTool.__new__(FiberBreakTool)  # no canvas needed
    names = sorted(lyr.name() for lyr in tool._iter_line_layers())
    assert names == ["Aerial cables", "Underground cables"]


def test_routes_and_pipes_are_excluded(populated_project):
    """Named explicitly: these are the layers that produced the bad reference."""
    tool = FiberBreakTool.__new__(FiberBreakTool)
    names = {lyr.name() for lyr in tool._iter_line_layers()}
    for excluded in ("Route", "PE pipes", "Transition pipes"):
        assert excluded not in names
