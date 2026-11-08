"""fid is a GeoPackage's key, never a cable (v1.6.0 QA finding Q17).

``FiberQPlugin._on_layers_added`` runs on every layer added to the project. Its
joint-closure branch takes any point layer named Joint Closures, or whose fields
are among id, fid and naziv -- which takes in a GeoPackage layer with no field
but its key -- and it aliased ``fid`` "Cable feature ID". In a GeoPackage
``fid`` is the table's INTEGER PRIMARY KEY. The cable's feature id is
``cable_fid``, which the Fiber break branch aliases "Cable feature ID", rightly.

Save all and auto-save stored the wrong alias in the GeoPackage's default style
(``layer_styles``), and a saved project stored it too, so taking it out of the
branch was not enough: a layer that arrives with it -- a project opened, Add
Layer, the layer auto-save rebuilds -- now has it taken off, and only that
alias, only on ``fid``. QGIS's own Add Layer loads the default style after the
layer is added, so it is taken off again whenever a layer's style loads (Q31).

The hook is the plugin's own method, on a plugin made with ``__new__``: none of
these layers reaches a branch that reads anything else of the plugin.
"""
import json
import os
import subprocess
import sys

import pytest
from qgis.core import (
    QgsCoordinateTransformContext,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

from fiberq.main_plugin import FiberQPlugin
from fiberq.utils.compat import save_style_to_database

WRONG = "Cable feature ID"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FIBER_BREAK_FIELDS = ["naziv:string", "cable_layer_id:string", "cable_fid:integer",
                      "distance_m:double", "segments_hit:integer", "vreme:string"]

SLACK_FIELDS = ["tip:string", "duzina_m:double", "lokacija:string", "cable_layer_id:string",
                "cable_fid:integer", "strana:string", "napomena:string", "fiberq_uuid:string"]


@pytest.fixture
def project(qgis_app):
    """A standalone project with FiberQ's layersAdded hook on it.

    Standalone, so the singleton is never touched: a project that outlives the
    test which made it is destroyed during interpreter teardown, which
    segfaults on QGIS 4.0.
    """
    plugin = FiberQPlugin.__new__(FiberQPlugin)
    prj = QgsProject()
    prj.layersAdded.connect(plugin._on_layers_added)
    yield prj
    prj.layersAdded.disconnect(plugin._on_layers_added)
    prj.clear()


def _table(tmp_path, name, fields=()):
    """Write a point table ``name`` with ``fields`` into one GeoPackage; its URI."""
    path = str(tmp_path / "data.gpkg")
    source = QgsVectorLayer("Point?crs=EPSG:3857" + "".join("&field=" + f for f in fields), name, "memory")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    options.actionOnExistingFile = (
        QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer if os.path.exists(path)
        else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile)
    result = QgsVectorFileWriter.writeAsVectorFormatV3(source, path, QgsCoordinateTransformContext(), options)
    assert result[0] == QgsVectorFileWriter.WriterError.NoError, result
    return f"{path}|layername={name}"


def _layer(uri, name):
    """The table as Add Layer opens it, default style and all."""
    layer = QgsVectorLayer(uri, name, "ogr")
    assert layer.isValid(), uri
    return layer


def _aliases(layer):
    return {field.name(): layer.attributeAlias(i) for i, field in enumerate(layer.fields())}


def _alias(layer, field, alias):
    layer.setFieldAlias(layer.fields().indexFromName(field), alias)


def _save_project(path, layers):
    """Write a project holding ``layers`` as they are, through no FiberQ hook."""
    prj = QgsProject()
    for layer in layers:
        prj.addMapLayer(layer)
    assert prj.write(str(path))
    prj.clear()


def _save_default_style(layer):
    assert save_style_to_database(layer, "default", "test", True, "") == ""


def test_a_point_layer_with_only_fid_gets_no_alias_on_it(project, tmp_path):
    layer = _layer(_table(tmp_path, "Points"), "Points")
    assert layer.fields().names() == ["fid"]

    project.addMapLayer(layer)

    assert _aliases(layer) == {"fid": ""}


def test_a_joint_closures_layer_names_naziv_and_leaves_fid_alone(project, tmp_path):
    layer = _layer(_table(tmp_path, "Joint Closures", ["naziv:string"]), "Joint Closures")

    project.addMapLayer(layer)

    assert _aliases(layer) == {"fid": "", "naziv": "Name"}


def test_a_project_saved_with_the_wrong_alias_opens_without_it(project, tmp_path):
    """Any layer's fid, not only a joint closure layer's: Survey reaches no branch.

    And the project opens unmodified: neither removing an alias nor setting one
    marks a project modified (measured on 3.22.16, 3.40.15 and 4.2.3), so it is
    unmodified right after the read before this fix and after it, on all five
    legs.
    """
    closures = _layer(_table(tmp_path, "Joint Closures", ["naziv:string"]), "Joint Closures")
    survey = _layer(_table(tmp_path, "Survey", ["kind:string"]), "Survey")
    for layer in (closures, survey):
        _alias(layer, "fid", WRONG)
    _save_project(tmp_path / "saved.qgz", [closures, survey])

    assert project.read(str(tmp_path / "saved.qgz"))

    opened = {layer.name(): _aliases(layer) for layer in project.mapLayers().values()}
    assert opened == {"Joint Closures": {"fid": "", "naziv": "Name"},
                      "Survey": {"fid": "", "kind": ""}}
    assert not project.isDirty()


def test_a_geopackage_default_style_with_the_wrong_alias_is_taken_off_on_add(project, tmp_path):
    uris = {"Joint Closures": _table(tmp_path, "Joint Closures", ["naziv:string"]),
            "Survey": _table(tmp_path, "Survey", ["kind:string"])}
    for name, uri in uris.items():
        layer = _layer(uri, name)
        _alias(layer, "fid", WRONG)
        _save_default_style(layer)

    added = {}
    for name, uri in uris.items():
        layer = _layer(uri, name)
        assert _aliases(layer)["fid"] == WRONG, "the default style did not load, so nothing was tested"
        project.addMapLayer(layer)
        added[name] = _aliases(layer)

    assert added == {"Joint Closures": {"fid": "", "naziv": "Name"},
                     "Survey": {"fid": "", "kind": ""}}


def test_fiber_break_still_names_cable_fid_and_not_fid(project, tmp_path):
    """As FiberQ makes it, no style saved. Passes on the parent as well."""
    layer = _layer(_table(tmp_path, "Fiber break", FIBER_BREAK_FIELDS), "Fiber break")

    project.addMapLayer(layer)

    aliases = _aliases(layer)
    assert (aliases["fid"], aliases["cable_fid"]) == ("", "Cable feature ID")


@pytest.mark.parametrize("name,fields", [("Fiber break", FIBER_BREAK_FIELDS),
                                         ("Optical slacks", SLACK_FIELDS)],
                         ids=["fiber-break", "optical-slacks"])
def test_cable_fid_keeps_cable_feature_id_while_fid_loses_it(project, tmp_path, name, fields):
    """The right "Cable feature ID" stays where it belongs, beside the wrong one going.

    Optical slacks reaches no branch of the hook, so nothing there would put the
    alias back: a clear that took it off whatever field carries it fails here.
    """
    uri = _table(tmp_path, name, fields)
    layer = _layer(uri, name)
    _alias(layer, "fid", WRONG)
    _alias(layer, "cable_fid", "Cable feature ID")
    _save_default_style(layer)
    layer = _layer(uri, name)

    project.addMapLayer(layer)

    aliases = _aliases(layer)
    assert (aliases["fid"], aliases["cable_fid"]) == ("", "Cable feature ID")


def test_an_alias_the_user_gave_fid_is_kept(project, tmp_path):
    """Only FiberQ's alias goes. The joint-closure branch used to write over
    whatever fid was called, so this fails on the parent as well."""
    layer = _layer(_table(tmp_path, "Joint Closures", ["naziv:string"]), "Joint Closures")
    _alias(layer, "fid", "Closure number")
    _save_project(tmp_path / "own.qgz", [layer])

    assert project.read(str(tmp_path / "own.qgz"))

    (opened,) = project.mapLayers().values()
    assert _aliases(opened) == {"fid": "Closure number", "naziv": "Name"}


# ---------------------------------------------------------------------------
# QGIS's own Add Layer loads the default style after the hook (v1.6.0 QA Q31)
# ---------------------------------------------------------------------------
#
# The tests above open the layer with its default style already loaded, and
# QGIS's Add Layer does not: Layer > Add Layer > Add Vector Layer..., the Browser
# panel and a file dropped on QGIS make the layer without its style, add it to
# the project -- the hook runs and finds no alias yet -- and only then load the
# default style, which brought the stored alias back
# (QgsAppLayerHandling::addSublayers on 3.40 and 4.2, QgisApp::addSublayers on
# 3.22). The maintainer's re-check of Q17 met exactly that: Poles removed and
# added back with Add Vector Layer, as "q17 — Poles", showed "Cable feature ID".

def _added_as_qgis_adds_it(project, uri, name):
    """The table as Add Layer adds it: made without its default style, added to
    the project, and only then given that style."""
    options = QgsVectorLayer.LayerOptions(project.transformContext())
    options.loadDefaultStyle = False
    if hasattr(options, "loadAllStoredStyle"):  # set by 3.40 and 4.2; 3.22 has no such option
        options.loadAllStoredStyle = True
    layer = QgsVectorLayer(uri, name, "ogr", options)
    assert layer.isValid(), uri
    assert _aliases(layer)["fid"] == "", "made with its style after all, so nothing was tested"
    project.addMapLayer(layer)
    message, loaded = layer.loadDefaultStyle()
    assert loaded, message
    return layer


def _stored(tmp_path, table, fields, aliases):
    """``table`` in data.gpkg, its default style giving ``aliases``; its URI."""
    uri = _table(tmp_path, table, fields)
    layer = _layer(uri, table)
    for field, alias in aliases.items():
        _alias(layer, field, alias)
    _save_default_style(layer)
    return uri


@pytest.mark.parametrize("table,name,fields", [("Poles", "q17 — Poles", []),
                                               ("Survey", "q17 — Survey", ["kind:string"])],
                         ids=["the-maintainers-poles", "a-layer-no-branch-reaches"])
def test_the_alias_goes_when_qgis_loads_the_style_after_the_add(project, tmp_path, table, name, fields):
    uri = _stored(tmp_path, table, fields, {"fid": WRONG})

    layer = _added_as_qgis_adds_it(project, uri, name)

    assert _aliases(layer)["fid"] == ""


def test_cable_fid_keeps_its_alias_and_a_name_the_user_gave_fid_stays(project, tmp_path):
    """Only that alias on fid goes, also when the style loads after the add.
    Optical slacks reaches no branch of the hook that would put it back."""
    slacks = _stored(tmp_path, "Optical slacks", SLACK_FIELDS, {"fid": WRONG, "cable_fid": "Cable feature ID"})
    survey = _stored(tmp_path, "Survey", ["kind:string"], {"fid": "Key"})

    slacks = _added_as_qgis_adds_it(project, slacks, "data — Optical slacks")
    survey = _added_as_qgis_adds_it(project, survey, "data — Survey")

    assert (_aliases(slacks)["fid"], _aliases(slacks)["cable_fid"]) == ("", "Cable feature ID")
    assert _aliases(survey)["fid"] == "Key"


def test_restore_default_style_does_not_bring_it_back(project, tmp_path):
    """Layer Properties > Style > Restore Default reloads the default style of a
    layer already in the project."""
    uri = _stored(tmp_path, "Survey", ["kind:string"], {"fid": WRONG})
    layer = _layer(uri, "Survey")
    project.addMapLayer(layer)
    assert _aliases(layer)["fid"] == ""

    message, loaded = layer.loadDefaultStyle()

    assert loaded, message
    assert _aliases(layer)["fid"] == ""


def test_a_layer_added_again_is_followed_once(project, tmp_path, monkeypatch):
    """The hook runs on every add of the same layer; one style load still runs
    the clear once, not once per add."""
    from fiberq.utils import field_aliases

    uri = _stored(tmp_path, "Survey", ["kind:string"], {"fid": WRONG})
    layer = _layer(uri, "Survey")
    project.addMapLayer(layer)
    layer = project.takeMapLayer(layer)
    project.addMapLayer(layer)
    cleared = []
    clear = field_aliases.clear_wrong_fid_alias
    monkeypatch.setattr(field_aliases, "clear_wrong_fid_alias", lambda lyr: (cleared.append(lyr.id()), clear(lyr)))

    layer.loadDefaultStyle()

    assert cleared == [layer.id()]
    assert _aliases(layer)["fid"] == ""


#: initGui() and unload() for real, on QgsProject.instance(), so in a child with
#: its own HOME (the settings they read and write stay out of the suite), with
#: test_language_preference's stand-in iface.
UNLOAD_DRIVER = '''
import json
import os
import sys
from unittest import mock

sys.path.insert(0, {repo!r})

from qgis.core import QgsApplication

QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()

from qgis.core import QgsProject, QgsVectorLayer
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow, QToolBar


class Iface:
    """What initGui() and unload() really use; the rest answers with a MagicMock."""

    def __init__(self):
        self._window = QMainWindow()
        self._canvas = QgsMapCanvas(self._window)
        self._window.setCentralWidget(self._canvas)
        self._mocks = {{}}

    def mainWindow(self):
        return self._window

    def mapCanvas(self):
        return self._canvas

    def addToolBar(self, name):
        return QToolBar(name, self._window)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self.__dict__["_mocks"].setdefault(name, mock.MagicMock(name=name))


from fiberq.main_plugin import FiberQPlugin

# initGui() arms a 2 s one-shot schema migration; it is not what this is about.
FiberQPlugin._run_schema_migrations = lambda self: None

plugin = FiberQPlugin(Iface())
plugin.initGui()

options = QgsVectorLayer.LayerOptions(QgsProject.instance().transformContext())
options.loadDefaultStyle = False
layer = QgsVectorLayer({uri!r}, "q17 \\u2014 Poles", "ogr", options)
QgsProject.instance().addMapLayer(layer)
fid = layer.fields().indexFromName("fid")
out = {{"loaded": layer.loadDefaultStyle()[1], "after_add": layer.attributeAlias(fid)}}
plugin.unload()
out["reloaded"] = layer.loadDefaultStyle()[1]
out["after_unload"] = layer.attributeAlias(fid)
QgsProject.instance().removeAllMapLayers()
print("RESULT " + json.dumps(out), flush=True)
sys.stdout.flush()
os._exit(0)
'''


def test_after_unload_a_style_load_runs_nothing_of_fiberq(tmp_path):
    """Whatever the hook connects goes with unload(): a default style loaded
    after it keeps the old name, as QGIS without FiberQ shows it."""
    uri = _stored(tmp_path, "Poles", [], {"fid": WRONG})
    script = tmp_path / "fid_alias_unload.py"
    script.write_text(UNLOAD_DRIVER.format(repo=REPO_ROOT, uri=uri), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", TMPDIR=str(tmp_path),
                       HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                       FIBERQ_LOG_FILE="false")
    # pytest-qgis points QGIS at <checkout>/.qgis-settings; inherited, the child
    # would write its settings there, into the checkout CI tests.
    environment.pop("QGIS_CUSTOM_CONFIG_PATH", None)

    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path), env=environment,
                          timeout=120, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    output = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 0, f"returncode {done.returncode} (-11/139 is SIGSEGV)\n{output}"
    results = [line for line in output.splitlines() if line.startswith("RESULT ")]
    assert results, output
    assert json.loads(results[-1][len("RESULT "):]) == {
        "loaded": True, "after_add": "", "reloaded": True, "after_unload": WRONG}, output


# ---------------------------------------------------------------------------
# the styles a GeoPackage already stores (v1.6.0 QA Q17, second round)
# ---------------------------------------------------------------------------
#
# The hook takes the alias off a layer in the project, and the next save writes
# that layer's style -- except Save all writes no style for a layer already
# living in its file (QGIS 3.22 would ask "overwrite?" in a modal box), and
# auto-save writes only the layers it converts. So a default style saved before
# 1.6.0 kept "Cable feature ID" on fid, and QGIS without FiberQ still showed it.
# A save now takes it out of the file's layer_styles: that one attribute value,
# in that one element, and no other byte.

class _Bar:
    def __init__(self):
        self.pushed = []

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.pushed.append((name,) + tuple(str(a) for a in args))


class _Iface:
    def __init__(self):
        self.bar = _Bar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


@pytest.fixture
def saving_project():
    """QgsProject.instance(), which Save all saves, emptied before and after."""
    def wipe(instance):
        instance.removeAllMapLayers()
        for scope in ("FiberQPlugin", "TelecomPlugin"):
            instance.removeEntry(scope, "gpkg_path")

    instance = QgsProject.instance()
    wipe(instance)
    yield instance
    wipe(instance)


@pytest.fixture
def no_modal():
    """Any modal box that opens (QGIS 3.22's style "overwrite?"), closed and recorded, not waited on."""
    from qgis.PyQt.QtCore import QTimer
    from qgis.PyQt.QtWidgets import QApplication

    seen = []

    def close():
        widget = QApplication.activeModalWidget()
        if widget is not None:
            seen.append(widget.windowTitle())
            widget.reject()

    timer = QTimer()
    timer.timeout.connect(close)
    timer.start(50)
    yield seen
    timer.stop()


def _stored_styles(path):
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(str(path))) as conn:
        return {table: qml for table, qml in conn.execute("SELECT f_table_name, styleQML FROM layer_styles")}


def _expected(qml):
    """``qml`` with the one change the clean-up may make, found here without its code."""
    import re

    elements = re.findall(r"<alias [^>]*/>", qml)
    wrong = [element for element in elements
             if 'field="fid"' in element and f'name="{WRONG}"' in element]
    assert len(wrong) <= 1, wrong
    if not wrong:
        return qml
    return qml.replace(wrong[0], wrong[0].replace(f'name="{WRONG}"', 'name=""'), 1)


def _styled_file(tmp_path):
    """data.gpkg as 1.5.0 left it: Fiber break and Joint Closures with "Cable
    feature ID" on fid in their default styles, and a Survey layer whose fid
    the user named."""
    uris = {"Fiber break": _table(tmp_path, "Fiber break", FIBER_BREAK_FIELDS),
            "Joint Closures": _table(tmp_path, "Joint Closures", ["naziv:string"]),
            "Survey": _table(tmp_path, "Survey", ["kind:string"])}
    aliases = {"Fiber break": {"fid": WRONG, "cable_fid": "Cable feature ID", "naziv": "Name"},
               "Joint Closures": {"fid": WRONG, "naziv": "Name"},
               "Survey": {"fid": "Closure number"}}
    for name, uri in uris.items():
        layer = _layer(uri, name)
        for field, alias in aliases[name].items():
            _alias(layer, field, alias)
        _save_default_style(layer)
    return tmp_path / "data.gpkg", uris


def test_save_all_takes_the_stored_alias_off_fid_in_the_layers_own_file(
        saving_project, no_modal, tmp_path, monkeypatch):
    """The maintainer's case: Save all into the file the layers already live in,
    which writes no style of theirs. Runs on 3.22 too, which asks before it
    writes over a default style through QGIS -- this goes around QGIS."""
    from qgis.PyQt.QtWidgets import QFileDialog

    from fiberq.core.export_manager import ExportManager

    path, uris = _styled_file(tmp_path)
    before = _stored_styles(path)
    assert sum(WRONG in qml for qml in before.values()) == 2, "the file was not set up as 1.5.0 left it"
    for name, uri in uris.items():
        saving_project.addMapLayer(_layer(uri, name))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(path), "")))
    iface = _Iface()

    ExportManager(iface).save_all_layers_to_gpkg()

    assert [entry[0] for entry in iface.bar.pushed] == ["pushSuccess"], iface.bar.pushed
    after = _stored_styles(path)
    assert after == {table: _expected(qml) for table, qml in before.items()}, (
        "only the fid alias may change, every other byte of every style stays")
    assert after["Survey"] == before["Survey"], "the user's own name for fid is kept"
    fresh = {name: _aliases(QgsVectorLayer(uri, name, "ogr")) for name, uri in uris.items()}
    assert fresh["Fiber break"]["fid"] == "" and fresh["Fiber break"]["cable_fid"] == "Cable feature ID"
    assert fresh["Fiber break"]["naziv"] == "Name"
    assert fresh["Joint Closures"] == {"fid": "", "naziv": "Name"}
    assert fresh["Survey"] == {"fid": "Closure number", "kind": ""}
    assert no_modal == []


def test_auto_save_takes_the_stored_alias_off_fid_in_its_file(saving_project, no_modal, tmp_path):
    """Auto-save writing a new layer into the file cleans the styles already there."""
    from fiberq.core.export_manager import export_one_layer_to_gpkg

    path, uris = _styled_file(tmp_path)
    before = _stored_styles(path)
    scratch = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer", "Scratch", "memory")
    saving_project.addMapLayer(scratch)

    assert export_one_layer_to_gpkg(scratch, str(path), _Iface()) is True

    after = _stored_styles(path)
    assert {table: qml for table, qml in after.items() if table in before} == {
        table: _expected(qml) for table, qml in before.items()}
    assert _aliases(QgsVectorLayer(uris["Joint Closures"], "Joint Closures", "ogr"))["fid"] == ""
    assert no_modal == []


@pytest.mark.parametrize("element, cleaned", [
    # A Qt 5 build (3.22.16, 3.40.15) changes the attributes' order from one
    # run to the next -- this is one of its orders -- and 4.2.3 writes field,
    # index, name, the next.
    ('<alias index="0" name="Cable feature ID" field="fid"/>', '<alias index="0" name="" field="fid"/>'),
    ('<alias field="fid" index="0" name="Cable feature ID"/>', '<alias field="fid" index="0" name=""/>'),
    ("<alias field='fid' name='Cable feature ID' index='0'/>", "<alias field='fid' name='' index='0'/>"),
    # Not FiberQ's wrong alias, or not fid: kept as it is.
    ('<alias field="cable_fid" index="2" name="Cable feature ID"/>', None),
    ('<alias field="fid" index="0" name="Closure number"/>', None),
    ('<alias field="fid2" index="0" name="Cable feature ID"/>', None),
    ('<alias field="FID" index="0" name="Cable feature ID"/>', None),
    ('<alias field="fid" index="0" name="Cable feature ID (old)"/>', None),
])
def test_only_that_alias_on_fid_is_taken_out_of_a_style(element, cleaned):
    from fiberq.utils.field_aliases import without_wrong_fid_alias

    qml = f"<qgis>\n <aliases>\n  {element}\n  <alias field=\"naziv\" index=\"1\" name=\"Name\"/>\n </aliases>\n</qgis>"

    assert without_wrong_fid_alias(qml) == qml.replace(element, cleaned or element)
