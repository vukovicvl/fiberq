"""The element catalogue the Placing elements menu offers, checked with no QGIS.

The menu lists the elements of ``models/element_defs.get_all_element_defs()`` (through
``ui/base.get_element_defs``) and hands each one's symbol, its map icon, to the placement tool. No earlier test
checks a map icon or the catalogue's names, and ``test_legacy_names.py``, which checks the other copies of the
catalogue, needs QGIS. This file needs neither QGIS nor Qt (``models/element_defs.py`` falls back to its own
``QT_TRANSLATE_NOOP``), so the fast stage runs it:

- the menu offers each element once, and each element of the icon table with its own icon;
- every icon the menu's elements name ships in the plugin's ``resources/map_icons`` folder;
- lay cable and the route tool know the joint closure layer by the name "Joint Closures".

The icon table is written out by hand from ``fiberq/resources/map_icons/``, as in ``test_legacy_names.py``. Each
element is checked on its own, so one added to the catalogue later breaks nothing here.
"""
import os

from fiberq.models import element_defs

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_DIR = os.path.join(REPO, "fiberq", "resources", "map_icons")

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


def test_the_placing_elements_menu_offers_each_element_once_with_its_map_icon():
    defs = element_defs.get_all_element_defs()
    names = [d["name"] for d in defs]
    assert sorted({name for name in names if names.count(name) > 1}) == [], "offered more than once"
    assert sorted(set(MAP_ICON) - set(names)) == [], "not offered"
    assert {d["name"]: os.path.basename(d["symbol"]["svg_path"]) for d in defs if d["name"] in MAP_ICON} == MAP_ICON


def test_every_map_icon_ships_in_the_plugins_map_icons_folder():
    symbols = [d.get("symbol") or {} for d in element_defs.get_all_element_defs()]
    paths = [symbol["svg_path"] for symbol in symbols if symbol.get("svg_path")]
    assert paths, "no element names an icon"
    assert [path for path in paths if not os.path.isfile(path)] == []
    assert [path for path in paths if not os.path.samefile(os.path.dirname(path), ICON_DIR)] == []


def test_lay_cable_and_the_route_tool_know_the_joint_closure_layer_by_name():
    """``core/cable_manager.py`` (lay cable) and ``tools/base.get_joint_closure_def`` (the route tool's snap list)
    read only this definition's name."""
    assert element_defs.NASTAVAK_DEF["name"] == "Joint Closures"
