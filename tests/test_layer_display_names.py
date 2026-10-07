"""Delete selected knows the plural slack layer, and the dead alias API is gone.

WP4 FU-2d, item U5. Unclaimed: ordinary bug fixes shipping in v1.6.0.

Two findings that turned out to be the same mistake twice.

**The layer name.** ``delete_selected`` decided whether it was deleting slack
loops with::

    if lyr.name() in ("Opticke_rezerve", "Optical slack"):

That list leaves out ``"Optical slacks"`` -- the **plural**, which is the name
the plugin itself creates the layer with, in both ``layer_manager`` and
``slack_manager``. So on every project FiberQ has made since that rename,
deleting a slack loop re-totalled nothing: the layer the user was deleting from
was not one this line recognised. The canonical name is the singular, so the
check now goes through ``schema.canonical_layer_name``, which knows all three
spellings, and the plugin keeps creating the plural as before.

**The display name.** Five "layer alias" helpers plus ``SlackManager``'s own
copy existed to show a Serbian-named layer under an English label in the Layers
panel, all of them reaching ``QgsLayerTreeLayer.setCustomLayerName``. That is a
QGIS **2.x** method. It exists on no QGIS this plugin supports -- measured
``AttributeError`` on 3.22.16, 3.40.15, 3.44.15, 4.0.3 and 4.2.3 -- so every
call raised, every caller caught it at debug level, and no label was ever set.
Six functions and fourteen call sites across eight files, all of it reaching
for something that was never there.

They are not replaced by ``node.setName()``. That is the modern API, but with
``useLayerName`` true it renames the **layer** as well as the node (measured on
all five versions), and this plugin identifies its layers by name in well over
a hundred places -- including the check above. Honouring the old intent would
break Delete selected, Save all layers, validation and cable laying at once.

So the test here is a static one. ``test_qgis4_deprecations.py`` cannot carry it:
its re-introduction check only looks for that file's first pattern.
"""
import ast
import io
import os

import pytest
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.models.schema import canonical_layer_name

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO_ROOT, "fiberq")

#: The QGIS 2.x layer-tree method, and the helpers that existed only to call it.
DEAD_API = "setCustomLayerName"
DEAD_HELPERS = frozenset({
    "set_layer_display_name",
    "set_route_layer_alias",
    "set_manhole_layer_alias",
    "set_slack_layer_alias",
    "set_joint_closure_layer_alias",
    "set_objects_layer_alias",
})


def _python_files():
    for folder, _dirs, names in os.walk(PACKAGE):
        if "__pycache__" in folder:
            continue
        for name in sorted(names):
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def _relative(path):
    return os.path.relpath(path, REPO_ROOT)


# ---------------------------------------------------------------------------
# The static half: nothing reaches for the QGIS 2.x method again
# ---------------------------------------------------------------------------

def test_no_module_calls_the_qgis2_layer_tree_method():
    """A grep would do, but an AST walk cannot be fooled by a comment."""
    offenders = []
    for path in _python_files():
        tree = ast.parse(io.open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == DEAD_API:
                offenders.append(f"{_relative(path)}:{node.lineno}")
    assert not offenders, (
        f"{DEAD_API} is a QGIS 2.x method and raises AttributeError on every "
        f"QGIS FiberQ supports (3.22 to 4.2, measured). It is not replaced by "
        f"node.setName(), which renames the layer itself and would break every "
        f"layer-name check in the plugin. Found at: {offenders}")


def test_the_dead_alias_helpers_are_not_defined_again():
    """Including as a no-op, which would read as though it still did something."""
    offenders = []
    for path in _python_files():
        tree = ast.parse(io.open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in DEAD_HELPERS:
                    offenders.append(f"{_relative(path)}:{node.lineno} {node.name}")
    assert not offenders, offenders


def test_the_dead_alias_helpers_are_not_exported():
    exported = io.open(
        os.path.join(PACKAGE, "utils", "__init__.py"), encoding="utf-8").read()
    still_there = sorted(n for n in DEAD_HELPERS if f"'{n}'" in exported)
    assert not still_there, still_there


def test_set_pipe_layer_alias_survives():
    """The one that was never dead: it calls layer.setName() on purpose."""
    from fiberq.utils import field_aliases

    assert hasattr(field_aliases, "set_pipe_layer_alias")
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "PE cevi", "memory")
    field_aliases.set_pipe_layer_alias(layer)
    assert layer.name() == "PE pipes", "this one really does rename, and must"


# ---------------------------------------------------------------------------
# canonical_layer_name knows every spelling of the slack layer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["Optical slack", "Optical slacks", "Opticke_rezerve"])
def test_every_slack_layer_spelling_resolves(name):
    assert canonical_layer_name(name) == "Optical slack"


def test_an_unrelated_layer_does_not_resolve_to_slack():
    assert canonical_layer_name("Underground cables") != "Optical slack"
    assert canonical_layer_name("Some user layer") is None


# ---------------------------------------------------------------------------
# The behaviour half: deleting from the plural layer re-totals the cable
# ---------------------------------------------------------------------------

class FakeBar:
    def __init__(self):
        self.warnings = []

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushInfo(self, title, text):
        pass


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None

    def mapCanvas(self):
        return None


@pytest.fixture(autouse=True)
def quiet_dialogs(monkeypatch):
    """``delete_selected`` ends with a modal, which hangs an offscreen run."""
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


def _cable(project):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Aerial cables", "memory")
    layer.dataProvider().addAttributes([
        QgsField("duzina_m", QVariant.Double),
        QgsField("slack_m", QVariant.Double),
        QgsField("total_len_m", QVariant.Double),
    ])
    layer.updateFields()
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(0, 0), QgsPointXY(100, 0)]))
    feat.setAttributes([100.0, 70.0, 170.0])
    layer.startEditing()
    layer.addFeature(feat)
    layer.commitChanges()
    project.addMapLayer(layer)
    return layer, next(layer.getFeatures()).id()


def _slacks(project, name, cable_id, cable_fid, metres):
    layer = QgsVectorLayer("Point?crs=EPSG:3857", name, "memory")
    layer.dataProvider().addAttributes([
        QgsField("duzina_m", QVariant.Double),
        QgsField("cable_layer_id", QVariant.String),
        QgsField("cable_fid", QVariant.Int),
    ])
    layer.updateFields()
    for i, value in enumerate(metres):
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i * 10, 0)))
        feat["duzina_m"] = value
        feat["cable_layer_id"] = cable_id
        feat["cable_fid"] = int(cable_fid)
        layer.startEditing()
        assert layer.addFeature(feat)
        assert layer.commitChanges()
    project.addMapLayer(layer)
    return layer


def _plugin(project):
    from fiberq.core.slack_manager import SlackManager
    from fiberq.main_plugin import FiberQPlugin

    iface = FakeIface()
    plugin = FiberQPlugin.__new__(FiberQPlugin)
    plugin.iface = iface
    plugin.slack_manager = SlackManager(iface)
    return plugin, iface


def _cable_values(layer, fid):
    feat = next(f for f in layer.getFeatures() if f.id() == fid)
    return float(feat["slack_m"]), pytest.approx(float(feat["total_len_m"]))


@pytest.mark.parametrize("layer_name", ["Optical slacks", "Optical slack", "Opticke_rezerve"])
def test_deleting_a_loop_retotals_the_cable(project, layer_name):
    """The plural is the one v1.5.0 missed, and the one FiberQ creates."""
    cable, fid = _cable(project)
    slacks = _slacks(project, layer_name, cable.id(), fid, [30.0, 40.0])
    plugin, _iface = _plugin(project)
    victim = next(f for f in slacks.getFeatures() if float(f["duzina_m"]) == 30.0)
    slacks.selectByIds([victim.id()])

    plugin.delete_selected()

    assert slacks.featureCount() == 1
    assert _cable_values(cable, fid) == (40.0, 140.0)


def test_deleting_from_a_layer_that_is_not_slack_leaves_cables_alone(project):
    cable, fid = _cable(project)
    _slacks(project, "Optical slacks", cable.id(), fid, [30.0, 40.0])
    other = QgsVectorLayer("Point?crs=EPSG:3857", "Some user layer", "memory")
    other.dataProvider().addAttributes([QgsField("a", QVariant.String)])
    other.updateFields()
    feat = QgsFeature(other.fields())
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(5, 5)))
    other.startEditing()
    other.addFeature(feat)
    other.commitChanges()
    project.addMapLayer(other)
    plugin, _iface = _plugin(project)
    other.selectByIds([next(other.getFeatures()).id()])

    plugin.delete_selected()

    assert other.featureCount() == 0
    assert _cable_values(cable, fid) == (70.0, 170.0), "untouched"


def test_deleting_every_loop_zeroes_the_cable(project):
    cable, fid = _cable(project)
    slacks = _slacks(project, "Optical slacks", cable.id(), fid, [30.0, 40.0])
    plugin, _iface = _plugin(project)
    slacks.selectByIds([f.id() for f in slacks.getFeatures()])

    plugin.delete_selected()

    assert slacks.featureCount() == 0
    assert _cable_values(cable, fid) == (0.0, 100.0)
