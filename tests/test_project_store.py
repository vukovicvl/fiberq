"""Unreadable project data is kept and reported, not read as empty and saved over.

WP4 4.2 item R5. Branch ``fix/wp4-write-paths``.

The relations, the latent (pass-through) elements and the colour catalogues live
as JSON strings in QGIS project custom properties. Every loader turned "I cannot
read this" into "you have none", and the next save wrote that emptiness over the
text it could not read.

Measured end to end through the real ``DataManager`` before the fix::

    save_relations({"relations": [{id 1 Splice A->B}, {id 2 Splice B->C}]})
    stored   = '{"relations": [{"id": 1, "name": "Splice A->B", "cable": "C-001"}, ...'
    truncate the stored text          (a half-written project entry)
    load_relations()  ->  {'relations': []}        <-- silent, raises nothing
    the user adds one relation and saves
    stored   = '{"relations": [{"id": 3, "name": "Splice C->D", ...}]}'
    relations 1 and 2: GONE

The truncated text still held relation 1's name and cable, recoverable by hand.
After the save it was unrecoverable. That measurement is what decided the shape
of the fix: not "refuse to save" (which would leave the user unable to work) and
not "merge" (which cannot be done with text that will not parse), but **keep the
unreadable text under a sibling key, say so, and carry on**.

The colour-catalogue loader is the one to worry about most, because its fallback
is the built-in TIA-598-C list rather than an empty one, so the manager opens
looking exactly like a correct fresh install.

One measured fact carries the whole design. ``readEntry`` answers a tuple whose
second element is whether the key was there at all -- identical on 3.22.16 and
3.44.15::

    absent             ->  ('', False)
    present but empty  ->  ('', True)
    present, garbage   ->  (the garbage, True)

So a new project, which has no key, gets its default in silence, and only a key
that is present and unreadable warns. Without that distinction every new project
would warn, and a warning everybody sees is a warning nobody reads. The test
that pins it is :func:`test_a_project_that_never_stored_anything_says_nothing`.

Eight of the fifteen tests below go red against a module whose two public
functions are rewritten as the old read-parse-default idiom. The seven that do
not are the ones the old code happened to satisfy -- a fresh project staying
quiet, the happy round trip, the default still being returned, and the promise
that nothing in here raises into a loader. They are kept because they are what
stops the fix over-firing or turning reporting into refusing, which is a thing
only a future change can break.
"""
import json

import pytest
from qgis.core import QgsProject

from fiberq.core.project_store import (
    QUARANTINE_SUFFIX,
    quarantine_unreadable,
    read_json_entry,
    write_json_entry,
)

SCOPE = "StuboviPlugin"
KEY = "Relacije/relations_v1"
GOOD = {"relations": [{"id": 1, "name": "Splice A->B", "cable": "C-001"},
                      {"id": 2, "name": "Splice B->C", "cable": "C-002"}]}


class FakeBar:
    def __init__(self):
        self.messages = []

    def pushWarning(self, title, text):
        self.messages.append(text)

    def pushMessage(self, *args, **kwargs):
        self.messages.append(str(args[-1]) if args else "")

    def pushInfo(self, title, text):
        self.messages.append(text)

    def pushSuccess(self, title, text):
        self.messages.append(text)

    def pushCritical(self, title, text):
        self.messages.append(text)


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    for key in (KEY, KEY + QUARANTINE_SUFFIX, "other/key", "other/key" + QUARANTINE_SUFFIX):
        prj.removeEntry(SCOPE, key)
    yield prj
    for key in (KEY, KEY + QUARANTINE_SUFFIX, "other/key", "other/key" + QUARANTINE_SUFFIX):
        prj.removeEntry(SCOPE, key)


@pytest.fixture
def iface():
    return FakeIface()


def _truncate(project, key=KEY):
    """Store good data, then damage it the way a half-written project would."""
    assert write_json_entry(SCOPE, key, GOOD, "Optical relations", project=project)
    stored = project.readEntry(SCOPE, key, '')[0]
    damaged = stored[:len(stored) // 2]
    assert project.writeEntry(SCOPE, key, damaged)
    # The premise of the whole item: the damaged text still holds the data.
    assert "Splice A->B" in damaged, damaged
    return damaged


# ---------------------------------------------------------------------------
# the fact the design rests on
# ---------------------------------------------------------------------------

def test_a_project_that_never_stored_anything_says_nothing(project, iface):
    """A fresh project is the ordinary case, not a problem.

    If this fails, the fix warns on every new project and is worse than the bug.
    """
    default = {"relations": []}
    assert read_json_entry(SCOPE, KEY, default, "Optical relations",
                           project=project, iface=iface) == default
    assert iface.bar.messages == [], iface.bar.messages


def test_an_entry_stored_empty_also_says_nothing(project, iface):
    """``('', True)`` -- present but empty. Nothing was lost, so nothing to say."""
    project.writeEntry(SCOPE, KEY, "")
    default = {"relations": []}
    assert read_json_entry(SCOPE, KEY, default, "Optical relations",
                           project=project, iface=iface) == default
    assert iface.bar.messages == [], iface.bar.messages


def test_good_data_comes_back_unchanged(project, iface):
    """Characterisation: the round trip has to keep working."""
    assert write_json_entry(SCOPE, KEY, GOOD, "Optical relations", project=project)
    assert read_json_entry(SCOPE, KEY, {"relations": []}, "Optical relations",
                           project=project, iface=iface) == GOOD
    assert iface.bar.messages == []


# ---------------------------------------------------------------------------
# the data loss
# ---------------------------------------------------------------------------

def test_unreadable_text_survives_the_next_save(project, iface):
    """**The one that matters.** Before the fix the next save destroyed it.

    The sequence is exactly the measured one: damage the entry, load it (which
    answers the default), then save the default back -- which is what a dialog
    does when the user adds one item to what it believes is an empty list.
    """
    damaged = _truncate(project)

    loaded = read_json_entry(SCOPE, KEY, {"relations": []}, "Optical relations",
                             project=project, iface=iface)
    assert loaded == {"relations": []}, "the default is still what the dialog gets"

    # The dialog saves what the user built on top of the emptiness it was shown.
    loaded["relations"].append({"id": 3, "name": "Splice C->D", "cable": "C-003"})
    assert write_json_entry(SCOPE, KEY, loaded, "Optical relations", project=project)

    kept = project.readEntry(SCOPE, KEY + QUARANTINE_SUFFIX, '')[0]
    assert kept == damaged, (
        "the unreadable text must still be in the project after the save that "
        f"used to destroy it; found {kept!r}")
    assert "Splice A->B" in kept, "the rescued copy must still hold the user's data"


def test_unreadable_text_is_reported_with_a_reason_and_where_it_went(project, iface):
    _truncate(project)
    read_json_entry(SCOPE, KEY, {"relations": []}, "Optical relations",
                    project=project, iface=iface)

    assert iface.bar.messages, "the user was told nothing at all"
    said = " ".join(iface.bar.messages)
    assert "Optical relations" in said, said
    assert KEY + QUARANTINE_SUFFIX in said, (
        f"the message must say where the text was kept, or the rescue is useless: {said!r}")


def test_a_second_failed_load_does_not_overwrite_the_first_rescue(project, iface):
    """Otherwise the rescue is replaced by a copy of itself, and if anything
    wrote to the main key in between, the older copy was the one worth keeping."""
    damaged = _truncate(project)
    read_json_entry(SCOPE, KEY, {"relations": []}, "Optical relations",
                    project=project, iface=iface)
    assert project.readEntry(SCOPE, KEY + QUARANTINE_SUFFIX, '')[0] == damaged

    project.writeEntry(SCOPE, KEY, "something else that will not parse {")
    read_json_entry(SCOPE, KEY, {"relations": []}, "Optical relations",
                    project=project, iface=iface)

    assert project.readEntry(SCOPE, KEY + QUARANTINE_SUFFIX, '')[0] == damaged, (
        "the first rescue was overwritten by the second failure")


def test_valid_json_of_the_wrong_shape_is_a_failure_too(project, iface):
    """A list stored where a dict belongs used to be handed straight back, and
    raised ``AttributeError`` in the caller's ``data.get(...)`` instead."""
    project.writeEntry(SCOPE, KEY, json.dumps(["not", "a", "dict"]))
    default = {"relations": []}

    assert read_json_entry(SCOPE, KEY, default, "Optical relations", expect="relations",
                           project=project, iface=iface) == default
    assert iface.bar.messages, "wrong-shape JSON was accepted in silence"
    assert project.readEntry(SCOPE, KEY + QUARANTINE_SUFFIX, '')[0], (
        "wrong-shape text must be kept too -- it is still the user's data")


def test_a_dict_without_the_expected_member_is_a_failure(project, iface):
    project.writeEntry(SCOPE, KEY, json.dumps({"something_else": []}))
    default = {"relations": []}
    assert read_json_entry(SCOPE, KEY, default, "Optical relations", expect="relations",
                           project=project, iface=iface) == default
    assert iface.bar.messages


def test_the_default_is_still_returned_so_the_dialog_opens(project, iface):
    """A colour dialog with no catalogues at all is not an improvement on one
    showing the built-in list. Reporting must not become refusing."""
    _truncate(project)
    default = {"catalogs": [{"name": "TIA-598-C"}]}
    assert read_json_entry(SCOPE, KEY, default, "Colour catalogues",
                           project=project, iface=iface) == default


# ---------------------------------------------------------------------------
# the write side
# ---------------------------------------------------------------------------

def test_a_payload_that_cannot_be_serialised_answers_false(project, iface):
    """Measured: ``save_relations`` with a set inside a relation returned
    normally, pushed nothing, left the entry untouched, and the dialog called
    ``accept()``. The user's new relation existed only in the dialog that was
    about to close."""
    payload = {"relations": [{"id": 1, "cables": {"a", "b"}}]}
    assert write_json_entry(SCOPE, KEY, payload, "Optical relations",
                            project=project, iface=iface) is False
    assert iface.bar.messages, "a refused save said nothing"
    assert not project.readEntry(SCOPE, KEY, '')[1], "nothing should have been written"


def test_a_successful_write_answers_true(project, iface):
    assert write_json_entry(SCOPE, KEY, GOOD, "Optical relations",
                            project=project, iface=iface) is True
    assert iface.bar.messages == []


# ---------------------------------------------------------------------------
# quarantine_unreadable on its own
# ---------------------------------------------------------------------------

def test_quarantine_answers_the_key_it_used(project):
    assert quarantine_unreadable(project, SCOPE, KEY, "garbage {") == KEY + QUARANTINE_SUFFIX
    assert project.readEntry(SCOPE, KEY + QUARANTINE_SUFFIX, '')[0] == "garbage {"


def test_quarantine_keeps_nothing_for_empty_text(project):
    assert quarantine_unreadable(project, SCOPE, KEY, "") is None
    assert not project.readEntry(SCOPE, KEY + QUARANTINE_SUFFIX, '')[1]


def test_quarantine_never_raises_into_a_loader(project):
    """Nothing here may raise: the whole point of the loader is that the dialog
    opens. A project object that cannot be written to must be survivable."""
    class Hostile:
        def readEntry(self, *args):
            return ('', False)

        def writeEntry(self, *args):
            raise RuntimeError("no writing today")

    assert quarantine_unreadable(Hostile(), SCOPE, KEY, "garbage {") is None


def test_a_read_from_a_hostile_project_still_answers_the_default(iface):
    class Hostile:
        def readEntry(self, *args):
            raise RuntimeError("no reading today")

    default = {"relations": []}
    assert read_json_entry(SCOPE, KEY, default, "Optical relations",
                           project=Hostile(), iface=iface) == default
    assert iface.bar.messages, "even this has to be said out loud"


# ---------------------------------------------------------------------------
# through the real managers -- what proves the call sites were rewired
# ---------------------------------------------------------------------------
#
# The tests above pin the policy. These pin that the twelve call sites actually
# use it, which is a different question: the policy could be perfect and every
# loader still have its own copy of the old idiom, which is exactly the state
# this item found the code in -- four copies, each drifted.

def test_the_real_data_manager_keeps_unreadable_relations(project, iface):
    """The measurement this whole item started from, now asserted.

    Before: load answered ``{'relations': []}``, the next save overwrote the
    text, and both relations were gone with nothing said.
    """
    from fiberq.core.data_manager import DataManager

    manager = DataManager(iface=iface)
    assert manager.save_relations(GOOD)
    stored = project.readEntry(manager.PLUGIN_NAMESPACE, manager.RELATIONS_KEY, '')[0]
    damaged = stored[:len(stored) // 2]
    project.writeEntry(manager.PLUGIN_NAMESPACE, manager.RELATIONS_KEY, damaged)

    loaded = manager.load_relations()
    assert loaded == {"relations": []}
    assert iface.bar.messages, "the real manager said nothing"

    loaded["relations"].append({"id": 3, "name": "Splice C->D"})
    assert manager.save_relations(loaded)

    kept = project.readEntry(
        manager.PLUGIN_NAMESPACE, manager.RELATIONS_KEY + QUARANTINE_SUFFIX, '')[0]
    assert "Splice A->B" in kept, (
        f"the user's relations did not survive the save: {kept!r}")
    project.removeEntry(manager.PLUGIN_NAMESPACE, manager.RELATIONS_KEY)
    project.removeEntry(manager.PLUGIN_NAMESPACE, manager.RELATIONS_KEY + QUARANTINE_SUFFIX)


def test_the_real_data_manager_warns_about_unreadable_catalogues(project, iface):
    """The dangerous one: the fallback is the built-in TIA-598-C list, so the
    manager opened looking exactly like a correct fresh install.

    Measured before the fix: a truncated entry answered ``['TIA-598-C']`` with
    an empty message bar, and after one save the user's own ``MyShop-24`` was
    gone from the project file.
    """
    from fiberq.core.data_manager import DataManager

    manager = DataManager(iface=iface)
    mine = {"catalogs": [{"name": "MyShop-24", "colors": [{"name": "blue", "hex": "#0000ff"}]}]}
    assert manager.save_color_catalogs(mine)
    stored = project.readEntry(manager.PLUGIN_NAMESPACE, manager.COLOR_CATALOGS_KEY, '')[0]
    project.writeEntry(manager.PLUGIN_NAMESPACE, manager.COLOR_CATALOGS_KEY,
                       stored[:len(stored) // 2])

    loaded = manager.load_color_catalogs()
    names = [c.get("name") for c in loaded.get("catalogs", [])]
    assert "MyShop-24" not in names, "the default is still what the dialog gets"
    assert iface.bar.messages, (
        "the defaults arrived looking like a fresh install and nothing was said -- "
        "this is the one the user has no way to notice")

    assert manager.save_color_catalogs(loaded)
    kept = project.readEntry(
        manager.PLUGIN_NAMESPACE, manager.COLOR_CATALOGS_KEY + QUARANTINE_SUFFIX, '')[0]
    assert "MyShop-24" in kept, f"the user's catalogue was destroyed: {kept!r}"
    project.removeEntry(manager.PLUGIN_NAMESPACE, manager.COLOR_CATALOGS_KEY)
    project.removeEntry(manager.PLUGIN_NAMESPACE, manager.COLOR_CATALOGS_KEY + QUARANTINE_SUFFIX)


def test_a_relations_manager_with_no_data_manager_also_reports(project):
    """The degraded path, which is live rather than dead: ``main_plugin`` sets
    ``self.data_manager = None`` when DataManager construction fails and passes
    that None here -- exactly when the user is least likely to be told
    anything."""
    from fiberq.core.relations_manager import RelationsManager

    manager = RelationsManager(data_manager=None)
    project.writeEntry('StuboviPlugin', manager.RELATIONS_STORAGE_KEY,
                       '{"relations": [{"id": 9, "name": "keep me"}')

    assert manager.load_relations() == {"relations": []}
    kept = project.readEntry(
        'StuboviPlugin', manager.RELATIONS_STORAGE_KEY + QUARANTINE_SUFFIX, '')[0]
    assert "keep me" in kept, f"the fallback path lost the text: {kept!r}"
    project.removeEntry('StuboviPlugin', manager.RELATIONS_STORAGE_KEY)
    project.removeEntry('StuboviPlugin', manager.RELATIONS_STORAGE_KEY + QUARANTINE_SUFFIX)


def test_a_save_that_cannot_be_serialised_answers_false_through_the_manager(project, iface):
    """A dialog that closes on the strength of this needs the bool. Measured
    before the fix: ``save_relations`` with a set inside a relation returned
    normally, pushed nothing, left the entry untouched, and the dialog called
    ``accept()``."""
    from fiberq.core.data_manager import DataManager

    manager = DataManager(iface=iface)
    assert manager.save_relations({"relations": [{"id": 1, "cables": {"a", "b"}}]}) is False
    assert iface.bar.messages
