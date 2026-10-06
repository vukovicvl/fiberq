"""Opening a QGIS 4 project in QGIS 3 says what it costs.

Not claimed under WP4 4.2 -- an ordinary fix shipping in the same release (plan
item U8).

QGIS 4 serialises project properties as nested ``<properties name="...">``
elements where QGIS 3 writes ``<FiberQPlugin><gpkg_path>``. QGIS 3 does not
understand the newer form, so it loses **every** FiberQ project entry, not a
selected few: relations, colour catalogues, latent elements, picture and
drawing links, the auto-save path, and WP3's interchange passthrough store.

Two of those fail quietly enough to be dangerous. Colour catalogues fall back to
the built-in defaults, so the user sees plausible colours rather than an
absence. And the passthrough store carries another tool's data through an
import, which is the one thing WP3 exists not to lose.

Then it gets worse: saving in QGIS 3 writes the project back without them.
Measured 4 -> 3 -> 4, the entries never come back. Hence the warning, and hence
:func:`test_an_absent_entry_does_not_overwrite_the_stored_copy` -- without that
guard, one "Save all layers" in QGIS 3 would put the empty defaults over the
GeoPackage's good copy as well, and the last backup would be gone too.
"""
import importlib.util
import pathlib

import pytest


def _load(name, relpath):
    path = pathlib.Path(__file__).resolve().parent.parent / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pc = _load("project_compat", "fiberq/core/project_compat.py")


# ---------------------------------------------------------------------------
# the rule, as plain Python
# ---------------------------------------------------------------------------

def test_a_qgis4_project_opened_in_qgis3_warns():
    assert pc.opened_a_newer_project(saved_major=4, running_major=3, has_fiberq_layers=True)


def test_qgis4_opening_its_own_project_says_nothing():
    assert not pc.opened_a_newer_project(saved_major=4, running_major=4, has_fiberq_layers=True)


def test_a_qgis3_project_opened_in_qgis3_says_nothing():
    assert not pc.opened_a_newer_project(saved_major=3, running_major=3, has_fiberq_layers=True)


def test_a_qgis3_project_opened_in_qgis4_says_nothing():
    """That direction keeps everything -- measured. Only 4 then 3 loses."""
    assert not pc.opened_a_newer_project(saved_major=3, running_major=4, has_fiberq_layers=True)


def test_a_project_with_nothing_of_ours_says_nothing():
    """Somebody else's QGIS 4 project has lost nothing of FiberQ's."""
    assert not pc.opened_a_newer_project(saved_major=4, running_major=3, has_fiberq_layers=False)


def test_a_project_that_was_never_saved_says_nothing():
    """lastSaveVersion() reports major 0 for a project with no file yet."""
    assert not pc.opened_a_newer_project(saved_major=0, running_major=3, has_fiberq_layers=True)


def test_a_project_from_an_even_newer_qgis_still_warns():
    assert pc.opened_a_newer_project(saved_major=5, running_major=3, has_fiberq_layers=True)


# ---------------------------------------------------------------------------
# the mechanism, against a real QGIS
# ---------------------------------------------------------------------------

@pytest.fixture
def qgis4_project(tmp_path):
    import sys
    fixtures = str(pathlib.Path(__file__).resolve().parent / "fixtures")
    if fixtures not in sys.path:
        sys.path.insert(0, fixtures)
    import make_qgis4_project
    return make_qgis4_project.generate(tmp_path / "qgis4_saved.qgs")


def test_qgis_reports_the_version_a_project_was_saved_with(qgis4_project):
    """The fact the warning turns on, read from a project QGIS 4 would write."""
    from qgis.core import QgsProject

    project = QgsProject()
    assert project.read(qgis4_project)
    assert project.lastSaveVersion().majorVersion() == 4


def test_qgis3_cannot_read_a_qgis4_projects_entries(qgis4_project):
    """The loss itself. On QGIS 4 these read back fine; on QGIS 3 they do not.

    Asserted as a statement of the mechanism rather than a pass/fail on one
    leg: what matters is that the two legs disagree, and that this is the
    reason the warning exists.
    """
    from qgis.core import Qgis, QgsProject

    project = QgsProject()
    assert project.read(qgis4_project)
    value, found = project.readEntry("FiberQPlugin", "gpkg_path", "")

    if int(Qgis.QGIS_VERSION.split(".")[0]) >= 4:
        assert (value, found) == ("/data/project.gpkg", True)
    else:
        assert (value, found) == ("", False), (
            "QGIS 3 read a QGIS 4 project entry; the warning may no longer be needed")


def test_an_absent_entry_does_not_overwrite_the_stored_copy(tmp_path):
    """The guard that stops a display problem becoming data loss.

    _collect_metadata used to default an unreadable entry to ``{"relations": []}``
    and the writer put that over the GeoPackage's good copy. One "Save all
    layers" in QGIS 3, and the last intact copy was gone too.
    """
    from qgis.core import QgsProject

    from fiberq.core.export_manager import ExportManager

    project = QgsProject.instance()
    project.removeEntry("StuboviPlugin", "Relacije/relations_v1")
    manager = ExportManager(None)

    assert manager._project_entry("StuboviPlugin", "Relacije/relations_v1") is None
    assert "relations_json" not in manager._collect_metadata()

    project.writeEntry("StuboviPlugin", "Relacije/relations_v1", '{"relations":[{"id":1}]}')
    try:
        assert manager._collect_metadata()["relations_json"] == '{"relations":[{"id":1}]}'
    finally:
        project.removeEntry("StuboviPlugin", "Relacije/relations_v1")


def test_an_entry_set_to_empty_is_still_an_answer():
    """Absent and empty are different: only absent means "say nothing"."""
    from qgis.core import QgsProject

    from fiberq.core.export_manager import ExportManager

    project = QgsProject.instance()
    project.writeEntry("StuboviPlugin", "Relacije/relations_v1", "")
    try:
        manager = ExportManager(None)
        assert manager._project_entry("StuboviPlugin", "Relacije/relations_v1") == ""
        assert manager._collect_metadata()["relations_json"] == '{"relations": []}'
    finally:
        project.removeEntry("StuboviPlugin", "Relacije/relations_v1")


# ---------------------------------------------------------------------------
# the slot
# ---------------------------------------------------------------------------

class _Bar:
    def __init__(self):
        self.warnings = []

    def pushWarning(self, title, text):
        self.warnings.append(text)


class _Iface:
    def __init__(self):
        self.bar = _Bar()

    def messageBar(self):
        return self.bar


@pytest.fixture
def plugin():
    """A FiberQPlugin with only what the warning slot reads.

    Building one properly means building the whole toolbar, which this does not
    need; the code under test is the real method.
    """
    from fiberq.main_plugin import FiberQPlugin

    instance = FiberQPlugin.__new__(FiberQPlugin)
    instance.iface = _Iface()
    return instance


def _fiberq_layer(name="Poles"):
    from qgis.core import QgsVectorLayer
    from fiberq.utils.uuid_utils import FIBERQ_UUID_FIELD

    layer = QgsVectorLayer(
        f"Point?crs=EPSG:3857&field=id:integer&field={FIBERQ_UUID_FIELD}:string", name, "memory")
    assert layer.isValid()
    return layer


@pytest.fixture
def clean_project():
    """A genuinely empty project.

    ``clear()`` rather than ``removeAllMapLayers()``: lastSaveVersion() survives
    the latter, so a test that had just read a QGIS 4 project would leave the
    next one believing it was looking at one too.
    """
    from qgis.core import QgsProject

    project = QgsProject.instance()
    project.clear()
    yield project
    project.clear()


def _running_major():
    from qgis.core import Qgis
    return int(Qgis.QGIS_VERSION.split(".")[0])


def test_the_warning_names_what_cannot_be_read(plugin, clean_project, qgis4_project):
    from qgis.core import QgsProject

    clean_project.addMapLayer(_fiberq_layer())
    QgsProject.instance().read(qgis4_project)
    clean_project.addMapLayer(_fiberq_layer())

    plugin._warn_if_project_is_from_a_newer_qgis()

    if _running_major() >= 4:
        assert plugin.iface.bar.warnings == [], "QGIS 4 reads its own projects"
    else:
        assert len(plugin.iface.bar.warnings) == 1
        said = plugin.iface.bar.warnings[0]
        assert "QGIS 4" in said
        assert "Do not save" in said


def test_no_warning_without_a_fiberq_layer(plugin, clean_project, qgis4_project):
    from qgis.core import QgsProject

    QgsProject.instance().read(qgis4_project)

    plugin._warn_if_project_is_from_a_newer_qgis()

    assert plugin.iface.bar.warnings == []


def test_no_warning_on_a_project_that_was_never_saved(plugin, clean_project):
    clean_project.addMapLayer(_fiberq_layer())

    plugin._warn_if_project_is_from_a_newer_qgis()

    assert plugin.iface.bar.warnings == []
