"""Add drawing: the category it offers, the drawing it loads, the features it links; and Clear drawing.

"Add drawing" asks for a DWG or DXF file and a subgroup of Drawings to load it into, offering the one that matches
the active layer's name, loads the drawing's layers there and links the drawing to every selected feature. "Clear
drawing" unlinks one feature. No earlier test ran any of this: test_feature_links.py checks where the links are
stored, and that storage is not tested again here. These tests run the drawing manager as the plugin wires it,
with its file dialog and category prompt replaced by stand-ins that record what they were asked, and the message
boxes answered at once.

One expected failure: a DXF is never loaded. The link is still made, with no layers, so the drawing tool opens
the file outside QGIS instead.
"""
import pytest
from qgis.core import QgsVectorLayer

from support.core_env import CoreIface, clean_project, memory_layer, record_message_boxes, tree_rows, wired_plugin

from fiberq.core import drawing_manager


class DrawingNotLoaded(AssertionError):
    """WP5-FU-46: the drawing manager loaded no layer from a DXF that GDAL reads."""


#: The subgroups of Drawings that Add drawing offers, in the order it offers them.
CATEGORIES = ["Joint Closures", "Customers", "TB", "OTB", "ODF", "Other"]

#: A layer's name and the subgroup Add drawing offers for it: FiberQ's own element layers, then the Serbian names
#: of older projects, then a name it does not know and no name at all.
CATEGORY_OF = {
    "ODF": "ODF", "TB": "TB", "OTB": "OTB", "Indoor OTB": "OTB", "Pole OTB": "OTB",
    "Joint Closures": "Joint Closures", "Joint Closure TO": "Joint Closures",
    "TO": "Other", "Pole TO": "Other", "Indoor TO": "Other", "Patch panel": "Other", "Poles": "Other",
    "Nastavci": "Joint Closures", "Korisnici": "Customers", "ZOK": "TB", "ODO": "OTB",
    "Stubovi": "Other", "": "Other", None: "Other",
}

#: The smallest DXF that GDAL reads: one LINE on layer 0, written by hand.
ONE_LINE_DXF = "\n".join([
    "0", "SECTION", "2", "ENTITIES",
    "0", "LINE", "8", "0", "10", "0.0", "20", "0.0", "30", "0.0", "11", "10.0", "21", "0.0", "31", "0.0",
    "0", "ENDSEC", "0", "EOF", ""])


@pytest.fixture
def project(qgis_app):
    with clean_project() as prj:
        yield prj


class _Named:
    """Anything with a name, as the category guess reads a layer."""

    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _Dialogs:
    """Add drawing's file dialog and category prompt, replaced on the drawing manager's module.

    The file dialog answers ``path`` (an empty one is a cancel) and counts how often it opened, in ``files``. The
    prompt takes the category offered and records ``(categories, index offered)`` in ``asked``.
    """

    def __init__(self, monkeypatch, path):
        self.path, self.files, self.asked = path, 0, []
        dialogs = self

        class FileDialog:
            @staticmethod
            def getOpenFileName(*args, **kwargs):
                dialogs.files += 1
                return dialogs.path, ""

        class InputDialog:
            @staticmethod
            def getItem(parent, title, label, items, current, editable):
                dialogs.asked.append((list(items), current))
                return items[current], True

        monkeypatch.setattr(drawing_manager, "QFileDialog", FileDialog)
        monkeypatch.setattr(drawing_manager, "QInputDialog", InputDialog)


def _plan(tmp_path):
    plan = tmp_path / "plan.dxf"
    plan.write_text(ONE_LINE_DXF)
    return plan


def _odf(project):
    """An ODF layer with three points (fids 1, 2, 3), none of them selected."""
    return memory_layer(project, "Point", "ODF", [("POINT(%d %d)" % (i, i), {"naziv": "ODF %d" % i}) for i in range(3)],
                        fields=("naziv",))


def test_the_category_offered_follows_the_layer_name(qgis_app):
    drawings = wired_plugin(CoreIface()).drawing_manager
    assert {name: drawings.guess_category_for_layer(_Named(name)) for name in CATEGORY_OF} == CATEGORY_OF
    assert set(CATEGORY_OF.values()) <= set(CATEGORIES)


def _gdal_reads(path):
    """Whether GDAL reads the DXF's entities layer, and its number of features, from a layer that is gone when this
    returns (QGIS 3.22 crashes at exit when a failed test's traceback keeps a valid OGR layer alive that no project
    owns)."""
    layer = QgsVectorLayer("%s|layername=entities" % path, "probe", "ogr")
    return layer.isValid(), layer.featureCount()


def test_gdal_reads_the_hand_written_dxf(project, tmp_path):
    """GDAL reads the hand-written DXF: one feature in its entities layer, the premise the next test asserts before
    it looks for its defect."""
    layer = QgsVectorLayer("%s|layername=entities" % _plan(tmp_path), "plan", "ogr")
    assert layer.isValid()
    assert project.addMapLayer(layer) is not None
    assert layer.featureCount() == 1


@pytest.mark.xfail(strict=True, raises=DrawingNotLoaded,
                   reason="WP5-FU-46: Add drawing never loads a DXF or DWG; the v1.8.0 fix removes this marker")
def test_a_dxf_is_loaded_under_its_category(project, tmp_path):
    """The drawing's layer is loaded into its subgroup of Drawings. Today the drawing manager splits QGIS's list
    of the file's layers on ":", which is not the separator QGIS uses, asks GDAL for a layer with no name and loads
    nothing."""
    drawings = wired_plugin(CoreIface()).drawing_manager
    subgroup = drawings.ensure_drawings_group("ODF")
    assert subgroup is not None
    assert tree_rows(project.layerTreeRoot()) == ["G:Drawings", "  G:ODF"]
    assert subgroup is project.layerTreeRoot().children()[0].children()[0], (
        "premise: the call gave back the ODF subgroup of Drawings")

    plan = _plan(tmp_path)
    assert _gdal_reads(plan) == (True, 1), "premise: GDAL reads the hand-written DXF"

    ids = drawings.try_add_dwg_to_group(str(plan), subgroup)
    if ids == []:
        # WP5-FU-46's effect and nothing else: no layer at all, in the project or under Drawings.
        assert (list(project.mapLayers()), tree_rows(project.layerTreeRoot())) == ([], ["G:Drawings", "  G:ODF"]), (
            "no layer id, but the project holds %s" % tree_rows(project.layerTreeRoot()))
        raise DrawingNotLoaded("the DXF gave the layer ids %r" % ids)
    assert len(ids) == 1, "the DXF gave the layer ids %r" % (ids,)
    added = project.mapLayer(ids[0])
    assert added is not None and added.isValid()
    assert added.featureCount() == 1
    assert subgroup.findLayer(ids[0]) is not None


def test_add_drawing_links_every_selected_feature_and_offers_the_layers_category(project, tmp_path, monkeypatch):
    """A file GDAL cannot read loads no layer, but the link is still made, for the selected features only."""
    note = tmp_path / "plan.pdf"
    note.write_text("not a drawing")
    layer = _odf(project)
    layer.selectByIds([1, 2])
    told = record_message_boxes(monkeypatch)
    dialogs = _Dialogs(monkeypatch, str(note))
    iface = CoreIface()
    iface.active_layer = layer
    drawings = wired_plugin(iface).drawing_manager

    drawings.add_drawing()

    assert dialogs.files == 1
    assert dialogs.asked == [(CATEGORIES, CATEGORIES.index("ODF"))]
    assert [drawings.drawing_get(layer, fid) for fid in (1, 2, 3)] == [str(note), str(note), ""]
    assert [drawings.drawing_layers_get(layer, fid) for fid in (1, 2)] == [[], []]
    assert tree_rows(project.layerTreeRoot()) == ["L:ODF", "G:Drawings", "  G:ODF"]
    assert told == ["Drawing is associated with 2 feature(s)."]


def test_add_drawing_without_a_selection_a_layer_or_a_file_links_nothing(project, tmp_path, monkeypatch):
    """With nothing selected, or no active layer, Add drawing says what to do and opens no file dialog; when the
    file dialog is cancelled, it asks nothing more and links nothing."""
    layer = _odf(project)
    told = record_message_boxes(monkeypatch)
    dialogs = _Dialogs(monkeypatch, str(_plan(tmp_path)))
    iface = CoreIface()
    drawings = wired_plugin(iface).drawing_manager

    iface.active_layer = layer
    drawings.add_drawing()
    iface.active_layer = None
    drawings.add_drawing()
    assert told == ["Select one or more features and try again.",
                    "Select a VECTOR layer and one or more features, then try again."]
    assert dialogs.files == 0

    layer.selectByIds([1])
    iface.active_layer = layer
    dialogs.path = ""
    drawings.add_drawing()
    assert (dialogs.files, dialogs.asked, len(told)) == (1, [], 2)
    assert drawings.drawing_get(layer, 1) == ""
    assert tree_rows(project.layerTreeRoot()) == ["L:ODF"]


def test_clearing_a_drawing_leaves_the_other_features_linked(project):
    layer = _odf(project)
    drawings = wired_plugin(CoreIface()).drawing_manager
    drawings.drawing_set_many(layer, [1, 2], "/plans/a.dxf")
    drawings.drawing_layers_set_many(layer, [1, 2], ["L1", "L2"])

    drawings.clear_drawing(layer, 1)
    assert (drawings.drawing_get(layer, 1), drawings.drawing_layers_get(layer, 1)) == ("", [])
    assert (drawings.drawing_get(layer, 2), drawings.drawing_layers_get(layer, 2)) == ("/plans/a.dxf", ["L1", "L2"])
