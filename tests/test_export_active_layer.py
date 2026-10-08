"""A failed export asked you where to save it a second time, and said nothing.

WP4 4.2 item R3. Branch ``fix/wp4-write-paths``.

Both export wrappers caught everything ``ExportManager`` raised into
``logger.debug`` -- which at the default log level writes nothing, anywhere --
and then re-ran the whole export through ``_export_active_layer``, a 198-line
near-identical second copy of the same code. Measured on 3.22, 3.44 and 4.0
through the real entry point:

* the user was asked for a format and a filename a **second** time;
* the one success message described only the second write, so the file the
  manager had already written sat on disk unmentioned;
* cancelling the second dialog said nothing at all, although that first file was
  complete;
* and when the cause was shared, the copy hit the same wall and the exception
  escaped the slot anyway.

The two writers produced structurally identical GeoPackages and byte-identical
KML, so the retry never could have rescued the first attempt. All it cost the
user was the knowledge that the export had failed, plus a stray file and two
extra dialogs.

**Why the copy was deleted rather than just unhooked**, which is the part worth
reading twice. The duplicate held WP1's two deliberately whole "Successfully
exported ..." sentences, with their translator comments. The live path --
``ExportManager`` -- still had the fragment-assembled form WP1 replaced::

    scope_txt = "selected features" if only_selected else "all features"
    f"Successfully exported {scope_txt} from layer '{...}'"

which is untranslatable into French: "de" + "les" contracts to the mandatory
"des", and no runtime substitution into a fixed "de {scope}" can produce it. So
WP1's delivered fix sat in code nothing could reach, while the bug it fixed was
what users actually saw. Moving those sentences into ``ExportManager`` is what
makes WP1 reachable for the first time, and it is why deleting the duplicate
*preserves* a claimed deliverable instead of destroying one.

**What is proved how, stated plainly.** Four of the seven tests below go red
against a tree with only this fix reverted: the two source assertions and the
two WP1 message tests. ``test_a_failed_export_is_reported`` and
``test_only_the_selected_features_reach_the_file`` do not, and each says why in
its own docstring -- the first because the reverted path hangs on an offscreen
modal rather than failing, the second because it is a characterisation test that
always passed. Nothing here is presented as a demonstrated red that is not one.
"""
import os
import textwrap

import pytest
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.core.export_manager import ExportManager


class FakeIface:
    def __init__(self, layer=None):
        self._active = layer

    def messageBar(self):
        return self

    def pushWarning(self, *a):
        pass

    def pushInfo(self, *a):
        pass

    def pushSuccess(self, *a):
        pass

    def pushCritical(self, *a):
        pass

    def mainWindow(self):
        return None

    def activeLayer(self):
        return self._active


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture
def modals(monkeypatch):
    said = {"info": [], "critical": [], "warning": []}
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: said["info"].append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: said["critical"].append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: said["warning"].append(str(a[-1]))))
    return said


@pytest.fixture
def poles(project):
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "Poles", "memory")
    layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    layer.updateFields()
    for i in range(3):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(f"Point ({i} 0)"))
        feature.setAttribute("naziv", f"p{i}")
        assert layer.dataProvider().addFeatures([feature])[0]
    project.addMapLayer(layer)
    return layer


def _dialogs(monkeypatch, target, fmt="GeoPackage (*.gpkg)"):
    """Answer both prompts and count how many times each was shown.

    Patched in **both** namespaces, and that is not belt-and-braces: the deleted
    duplicate asked through ``main_plugin``'s own imports, so patching only the
    manager's left the second dialog real. Against a reverted tree this test
    then blocked on an offscreen modal instead of failing -- a hanging test
    proves nothing, and worse, it proves nothing slowly. With both patched, the
    reverted tree reports the second dialog and the assertion does its job.
    """
    counts = {"format": 0, "save": 0}
    import fiberq.core.export_manager as em
    import fiberq.main_plugin as mp

    def fake_format(*a, **k):
        counts["format"] += 1
        return fmt, True

    def fake_save(*a, **k):
        counts["save"] += 1
        return target, ""

    for module in (em, mp):
        monkeypatch.setattr(module.QInputDialog, "getItem", staticmethod(fake_format))
        monkeypatch.setattr(module.QFileDialog, "getSaveFileName", staticmethod(fake_save))
    return counts


# ---------------------------------------------------------------------------
# the double dialog
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wrapper", ["export_all_features", "export_selected_features"])
def test_a_failed_export_does_not_re_run_the_whole_export(wrapper):
    """The acceptance line: a manager failure must not start a second export.

    **This is a source assertion, and it is one on purpose.** The behaviour
    version -- drive the wrapper with a manager that raises and count the
    dialogs -- cannot be shown red: against a tree with the fix reverted the
    fallback blocks on a modal that an offscreen run never answers, so the test
    hangs instead of failing. Located with ``faulthandler`` rather than guessed
    at: the blocking frame is ``main_plugin.py:3742`` in the deleted
    ``_export_active_layer``, a ``QMessageBox.warning`` on the
    "Please select an active vector layer before exporting." path.

    A hanging test proves nothing, slowly, and a test whose red cannot be
    demonstrated is exactly what this branch has spent its time removing. So the
    claim is checked the way the error-handling ratchet checks its own: on the
    parsed source, which is deterministic and does go red. The reporting
    behaviour has its own test below.
    """
    import ast
    import inspect

    from fiberq.main_plugin import FiberQPlugin

    source = inspect.getsource(getattr(FiberQPlugin, wrapper))
    tree = ast.parse(textwrap.dedent(source))
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name:
                called.add(name)

    assert "_export_active_layer" not in called, (
        f"{wrapper} still re-runs the export through the duplicate. The two writers produce "
        "byte-identical output, so the retry cannot rescue the first attempt -- all it costs "
        "the user is the knowledge that the export failed, plus a stray file and two dialogs.")
    assert "report_error" in called, (
        f"{wrapper} does not report the failure it catches")


def test_a_failed_export_is_reported(poles, tmp_path, monkeypatch):
    """It used to be ``logger.debug``, so at the default log level the user got
    nothing at all -- and then a second file dialog with no explanation.

    **No demonstrated red.** This exercises the fixed path only: against a
    reverted tree the fallback blocks on an offscreen modal, so the test hangs
    rather than failing. The structural half of the claim is covered by
    :func:`test_a_failed_export_does_not_re_run_the_whole_export`, which does go
    red. Kept because it is the only test here that checks the report actually
    reaches ``report_error`` with the real exception.
    """
    from fiberq.main_plugin import FiberQPlugin

    reported = []
    import fiberq.main_plugin as mp
    monkeypatch.setattr(mp, "report_error",
                        lambda op, what, exc, iface: reported.append(str(exc)))

    class Exploding:
        def export_selected_features(self):
            raise RuntimeError("the manager could not export")

    plugin = FiberQPlugin.__new__(FiberQPlugin)
    plugin.iface = FakeIface(poles)
    plugin.export_manager = Exploding()

    FiberQPlugin.export_selected_features(plugin)

    assert reported, "a failed export said nothing"
    assert "could not export" in reported[0], reported


def test_the_second_copy_of_the_export_is_gone():
    """A guard, not a behaviour test. The fallback and the copy have to go in
    the same change: unhooking the fallback and leaving 198 lines of unreachable
    export behind is how a future reader re-hooks it."""
    from fiberq.main_plugin import FiberQPlugin

    assert not hasattr(FiberQPlugin, "_export_active_layer"), (
        "the duplicate export is back; it only ever ran when the real one failed")


# ---------------------------------------------------------------------------
# WP1's sentences, now on the path that runs
# ---------------------------------------------------------------------------

def test_the_success_message_is_one_whole_translatable_sentence(
        poles, tmp_path, monkeypatch, modals):
    """WP1's fix, reachable at last.

    The live path used to assemble the sentence from a separately translated
    "selected features"/"all features" fragment, which cannot be translated into
    French. WP1 replaced that with two whole sentences -- in the copy that never
    ran.
    """
    target = str(tmp_path / "out.gpkg")
    _dialogs(monkeypatch, target)

    manager = ExportManager(FakeIface(poles))
    manager.export_all_features()

    assert os.path.exists(target), modals
    assert modals["info"], "a successful export said nothing"
    message = modals["info"][0]
    assert "all features of layer" in message, (
        f"the fragment-assembled form is back: {message!r}")
    assert "Poles" in message and target in message


def test_the_selected_features_message_is_its_own_sentence(
        poles, tmp_path, monkeypatch, modals):
    target = str(tmp_path / "sel.gpkg")
    _dialogs(monkeypatch, target)
    poles.selectByIds([1])

    manager = ExportManager(FakeIface(poles))
    manager.export_selected_features()

    assert modals["info"], modals
    message = modals["info"][0]
    assert "the selected features of layer" in message, (
        f"the fragment-assembled form is back: {message!r}")


def test_only_the_selected_features_reach_the_file(
        poles, tmp_path, monkeypatch, modals):
    """Characterisation, not proof: it passed before this change too. It is here
    because deleting one of two export implementations is exactly the kind of
    change that could silently start exporting the wrong set."""
    target = str(tmp_path / "sel.gpkg")
    _dialogs(monkeypatch, target)
    poles.selectByIds([1])

    ExportManager(FakeIface(poles)).export_selected_features()

    written = QgsVectorLayer(target, "out", "ogr")
    assert written.isValid(), modals
    assert written.featureCount() == 1, (
        f"expected only the selected feature, got {written.featureCount()}")
