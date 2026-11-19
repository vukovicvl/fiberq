"""The colour catalogues a project starts with, and the colour codes the cable picker offers.

The plugin's colour-catalogue dialog loads and saves its catalogues through the colour manager, and the cable
picker takes its colour codes from the data manager, to which the colour manager's own list hands over. In the
plugin the colour manager hands all three to the data manager, so these tests drive the colour manager as the
plugin wires it and check the data manager's catalogue code through that hand-over: of color_manager.py itself
they run only the delegating lines, four of which no earlier test ran.
The colour manager's own copies, for when the data manager failed to build, do not run while the data manager answers,
and are not tested.

test_project_store.py already checks the data manager's catalogues on their own: a saved catalogue reads back, an
entry it cannot read is kept aside and reported, and a save that cannot be written answers False. Over that, these
tests pin what a new project shows (one catalogue, TIA-598-C, its twelve colours in the standard's order) and the
list of codes the cable picker offers: the saved catalogues by name, then each standard not among them.
"""
import re

import pytest

from support.core_env import CoreIface, clean_project, wired_plugin

#: TIA-598-C's twelve fibre colours, in the standard's order. The standard calls the eleventh "Rose"; FiberQ calls
#: it "Pink".
TIA_598_C = ["Blue", "Orange", "Green", "Brown", "Slate", "White", "Red", "Black", "Yellow", "Violet", "Pink", "Aqua"]

#: The standards the cable picker always offers, after the saved catalogues, unless one of them is saved already.
STANDARDS = ["ANSI/EIA/TIA-598-A", "IEC 60793-2-50", "ITU-T (generički)"]

#: Where a project keeps its colour catalogues. Projects saved by earlier versions hold them there.
SCOPE, KEY = "StuboviPlugin", "ColorCatalogs/catalogs_v1"


@pytest.fixture
def project(qgis_app):
    with clean_project() as prj:
        yield prj


def test_a_fresh_project_loads_the_tia_598_c_catalogue_in_its_order_and_says_nothing(project):
    iface = CoreIface()
    loaded = wired_plugin(iface).color_manager.load_color_catalogs()

    assert list(loaded) == ["catalogs"]
    assert [catalogue["name"] for catalogue in loaded["catalogs"]] == ["TIA-598-C"]
    colours = loaded["catalogs"][0]["colors"]
    assert [colour["name"] for colour in colours] == TIA_598_C
    hexes = [colour["hex"] for colour in colours]
    assert all(re.fullmatch(r"#[0-9a-f]{6}", value) for value in hexes), hexes
    assert len(set(hexes)) == 12
    assert iface.messageBar().messages == []


def test_the_colour_codes_are_the_saved_names_then_the_missing_standards(project):
    """A saved standard is not offered twice, and a catalogue with no name is left out of the codes."""
    iface = CoreIface()
    colours = wired_plugin(iface).color_manager
    assert colours.list_color_codes() == ["TIA-598-C"] + STANDARDS

    saved = {"catalogs": [{"name": "IEC 60793-2-50", "colors": []},
                          {"name": "", "colors": []},
                          {"name": "MyShop-24", "colors": [{"name": "Blue", "hex": "#0000ff"}]}]}
    assert colours.save_color_catalogs(saved) is True
    assert colours.load_color_catalogs() == saved
    assert project.readEntry(SCOPE, KEY, "")[1] is True
    assert colours.list_color_codes() == ["IEC 60793-2-50", "MyShop-24", "ANSI/EIA/TIA-598-A", "ITU-T (generički)"]
    assert iface.messageBar().messages == []
