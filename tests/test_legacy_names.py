"""Legacy names: the phrase book two dialogs read, the cable-layer test on Serbian layer names, and the element
catalogue where Change element type and the Placing elements menu read it.

``test_fiber_break_target.py`` drives the fibre-break tool's cable picker with English layer names only, and
``test_schema.py`` covers ``canonical_layer_name``, the lookup of the schema's legacy layer names, which is not
repeated here. No earlier test calls the phrase book or the catalogue's lookups, or checks an element's map icon.
Over them this file adds:

- ``utils/legacy_bridge._fiberq_translate``, the phrase book the BOM report and the picture pop-up call: the
  strings they pass come back unchanged, which is what users see; and the book's own phrases both ways, with the
  round trip and the two phrases it loses (where two legacy phrases share an English text, the reverse lookup
  keeps the later one). The book stays until the dialogs move to Qt's translations (docs/i18n.md, Stage 2), and
  these tests go with it;
- ``utils/helpers.is_cable_layer``, the one lookup in ``helpers`` the plugin calls (the fibre-break tool's cable
  picker): the Serbian cable layers "Kablovi_vazdusni" and "Kablovi_podzemni" count as cables, and so do the
  English ones; the route and the ducts do not, nor a cable name on a point or polygon layer;
- the catalogue: a new layer for each element, made as Change element type makes it
  (``core/layer_manager._ensure_element_layer_with_style``), draws that element's map icon, and Change element type's
  lookup (``_element_def_by_name``) gives nothing for a name that is no element; the copies the Placing elements menu
  and Change element type draw from give each element the same icon; the copy the element and select tools read names
  from has every element; and every copy names the joint closure layer "Joint Closures", as placement, selection, Import
  points and lay cable read it.

The icon table is written out by hand from ``fiberq/resources/map_icons/``, as in ``test_element_catalogue.py``,
which checks the menu's copy with no QGIS. Each element is checked on its own, so one added to the catalogue later
breaks nothing here. Every test runs in an emptied project, whose guard fails a test that changed a FiberQ setting; only
the icon test adds layers to it, one element at a time.
"""
import os

import pytest
from qgis.core import QgsSvgMarkerSymbolLayer, QgsWkbTypes

from support.core_env import Core, CoreIface, clean_project, empty_project, memory_layer

from fiberq.core import layer_manager
from fiberq.models import element_defs
from fiberq.utils import helpers, legacy_bridge

#: The phrase book the dialogs call (``utils/helpers.py`` keeps a copy the plugin never runs).
translate = legacy_bridge._fiberq_translate

#: The strings the phrase book's two callers pass: the BOM report's title, tabs, column headers and Export button
#: (``dialogs/bom_dialog.py``, ``apply_language``) and the picture pop-up's title (``utils/image_watcher.py``).
CALLERS_PASS = ("BOM report (XLSX/CSV)", "By Layers", "Summary", "Layer", "Type", "Number of elements", "Length [m]",
                "Slack [m]", "Total [m]", "Export (.xlsx / .csv)", "Open image (click)")

#: A legacy phrase -> the English it shows (language "en").
TO_ENGLISH = {
    "Završna rezerva (prečica)": "End slack (shortcut)",
    "Razgrani cables (offset)": "Separate cables (offset)",
    "Kreiranje Rejona": "Create region",
    "Kreiraj rejon": "Create region",
    "Rejon": "Region",
    "Nacrtaj region ručno": "Draw region (manual)",
    "Nacrtaj region rucno": "Draw region (manual)",
    "Move element": "Move elements",
    "Import image to element": "Attach image to element",
}

#: English -> the legacy phrase it shows in Serbian. Where two phrases share an English text, the later one in the
#: book wins: "Kreiraj rejon", and the unaccented "rucno".
FROM_ENGLISH = {
    "End slack (shortcut)": "Završna rezerva (prečica)",
    "Separate cables (offset)": "Razgrani cables (offset)",
    "Create region": "Kreiraj rejon",
    "Region": "Rejon",
    "Draw region (manual)": "Nacrtaj region rucno",
    "Move elements": "Move element",
    "Attach image to element": "Import image to element",
}

#: (geometry, layer name, a cable layer?)
CABLE_LAYERS = (
    ("LineString", "Kablovi_vazdusni", True),
    ("LineString", "Kablovi_podzemni", True),
    ("LineString", "Aerial cables", True),
    ("MultiLineString", "Underground cables", True),
    ("Point", "Aerial cables", False),
    ("Polygon", "Kablovi_podzemni", False),
    ("LineString", "Trasa", False),
    ("LineString", "PE cevi", False),
    ("LineString", "Prelazne cevi", False),
)

#: Element name -> its map icon, as ``fiberq/resources/map_icons/`` names them. The folder's thirteenth file,
#: ``map_joint_closure.svg``, is the icon Place Joint Closure draws; it is in no copy of the catalogue.
MAP_ICON = {
    "ODF": "map_odf.svg",
    "TB": "map_tb.svg",
    "Patch panel": "map_patch_panel.svg",
    "OTB": "map_otb.svg",
    "Indoor OTB": "map_place_otb_indoor.svg",
    "Outdoor OTB": "map_place_otb_outdoor.svg",
    "Pole OTB": "map_place_otb_pole.svg",
    "TO": "map_place_to.svg",
    "Indoor TO": "map_place_to_indoor.svg",
    "Outdoor TO": "map_place_to_outdoor.svg",
    "Pole TO": "map_place_to_pole.svg",
    "Joint Closure TO": "map_place_to_joint_closure.svg",
}

#: Names that are no element. "Joint Closures" is left out: Change element type's lookup gives it nothing today,
#: which is why it draws a joint closure with a circle (test_layer_ensure.py pins that), and its fix changes it.
NOT_ELEMENTS = ("Poles", "Manholes", "Route", "odf", "ODF ", "", None)


@pytest.fixture
def project(qgis_app):
    with clean_project() as prj:
        yield prj


def _icons(defs):
    """{name: icon file name} for the elements of ``defs`` that the icon table names, and the paths that are not a
    file."""
    paths = {d["name"]: d["symbol"]["svg_path"] for d in defs if d["name"] in MAP_ICON}
    return {name: os.path.basename(path) for name, path in paths.items()}, [
        path for path in paths.values() if not os.path.isfile(path)]


def _repeated_and_missing(defs):
    """The element names ``defs`` gives more than once, and the elements of the icon table it lacks."""
    names = [d["name"] for d in defs]
    return sorted({name for name in names if names.count(name) > 1}), sorted(set(MAP_ICON) - set(names))


def _drawn(layer):
    """What a new element layer draws: the file name of its one SVG marker ("missing: <path>" when the file is
    not there), else the type of each of its symbol layers. Never a size or a unit."""
    markers = layer.renderer().symbol().symbolLayers()
    if [type(marker) for marker in markers] != [QgsSvgMarkerSymbolLayer]:
        return [marker.layerType() for marker in markers]
    path = markers[0].path()
    return os.path.basename(path) if os.path.isfile(path) else "missing: " + path


# ---------------------------------------------------------------------------
# The phrase book (utils/legacy_bridge)
# ---------------------------------------------------------------------------

def test_the_strings_the_dialogs_pass_come_back_as_they_are(project):
    for lang in ("en", "sr"):
        assert [translate(text, lang) for text in CALLERS_PASS] == list(CALLERS_PASS), lang


def test_a_legacy_phrase_shows_its_english(project):
    assert {phrase: translate(phrase, "en") for phrase in TO_ENGLISH} == TO_ENGLISH


def test_an_english_phrase_shows_its_legacy_text_in_serbian(project):
    assert {text: translate(text, "sr") for text in FROM_ENGLISH} == FROM_ENGLISH


def test_a_round_trip_keeps_the_english_and_loses_exactly_two_legacy_phrases(project):
    assert [translate(translate(text, "sr"), "en") for text in FROM_ENGLISH] == list(FROM_ENGLISH)
    back = {phrase: translate(translate(phrase, "en"), "sr") for phrase in TO_ENGLISH}
    assert {phrase: text for phrase, text in back.items() if text != phrase} == {
        "Kreiranje Rejona": "Kreiraj rejon", "Nacrtaj region ručno": "Nacrtaj region rucno"}


def test_text_is_stripped_and_unknown_text_or_a_non_string_passes_through(project):
    texts = ("  Rejon  ", "  not in the book  ", "Place anything", "")
    assert [translate(text, "en") for text in texts] == ["Region", "not in the book", "Place anything", ""]
    for value in (None, 42, ["Rejon"]):
        assert translate(value, "en") is value


# ---------------------------------------------------------------------------
# The cable-layer test (utils/helpers)
# ---------------------------------------------------------------------------

def test_a_cable_layer_is_known_by_its_legacy_and_english_names(project):
    layers = [memory_layer(None, geometry, name) for geometry, name, _ in CABLE_LAYERS]
    assert [QgsWkbTypes.displayString(layer.wkbType()) for layer in layers] == [row[0] for row in CABLE_LAYERS]
    assert [(geometry, name, helpers.is_cable_layer(layer))
            for (geometry, name, _), layer in zip(CABLE_LAYERS, layers)] == list(CABLE_LAYERS)
    assert helpers.is_cable_layer(None) is False


# ---------------------------------------------------------------------------
# The element catalogue
# ---------------------------------------------------------------------------

def test_change_element_type_draws_each_element_with_its_map_icon(project):
    """A new layer for each element, made as Change element type makes it, draws that element's map icon: the
    file, never its size or its unit."""
    drawn = {}
    for name in MAP_ICON:
        empty_project(project)
        drawn[name] = _drawn(layer_manager._ensure_element_layer_with_style(Core(CoreIface()), name))
    assert drawn == MAP_ICON


def test_a_name_that_is_not_an_element_has_no_definition(project):
    assert [name for name in NOT_ELEMENTS if layer_manager._element_def_by_name(name) is not None] == []


def test_the_placing_elements_menu_and_change_element_type_draw_the_same_icons(project):
    """The menu's copy is ``models/element_defs.py``'s (``ui/base.get_element_defs``), Change element type's is
    ``core/layer_manager.py``'s. The element and select tools read only the names of ``utils/legacy_bridge.py``'s."""
    for copy, defs in (("models.element_defs", element_defs.ELEMENT_DEFS),
                       ("core.layer_manager", layer_manager.ELEMENT_DEFS)):
        assert _repeated_and_missing(defs) == ([], []), copy
        assert _icons(defs) == (MAP_ICON, []), copy
    assert _repeated_and_missing(legacy_bridge.ELEMENT_DEFS) == ([], [])


def test_every_copy_names_the_joint_closure_layer_alike(project):
    names = {copy: module.NASTAVAK_DEF["name"] for copy, module in (
        ("core.layer_manager", layer_manager), ("utils.legacy_bridge", legacy_bridge),
        ("models.element_defs", element_defs))}
    assert names == dict.fromkeys(names, "Joint Closures")
