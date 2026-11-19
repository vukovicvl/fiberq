"""The set-up the core-logic tests share: a project emptied without ``QgsProject.clear()``, a stand-in ``iface``,
memory layers that keep the project's layer order fixed, and the plugin's managers wired as the plugin wires them.

The earlier tests of the managers each built these for themselves, in different ways. Over them it adds:

- one reset, ``clean_project()``, that is cheap on every QGIS. The earlier tests called ``clear()``
  (``test_latent_elements.py``), which costs about 1 ms a call on QGIS 3.22, 0.15 s on 3.44 and 0.35 s on 4.2, or
  ``removeAllMapLayers()`` alone (``test_lay_cable_route_search.py``), which leaves FiberQ's project entries, the
  layer-tree groups and the project's CRS behind. It also starts each test with no project CRS or ellipsoid, and
  puts back any FiberQ setting the test changed;
- ``CoreIface``, a map canvas with a CRS and a scale. pytest-qgis's canvas has no CRS, and neither has
  ``FakeIface``'s (``fake_iface.py``, made for ``initGui()``), so a manager given either one makes its layers
  without a CRS;
- ``memory_layer()``, which refuses a layer whose place in the project's layer order would be random;
- ``wired_plugin()``, every manager wired as ``main_plugin.py`` wires it. Earlier tests built a manager with
  ``None`` for the managers it uses (``test_uuid_creation_invariant.py``), so they ran its own copy for "another
  manager failed to build", which the plugin runs only if the manager it hands the work to raises;
- the cable picker and the message boxes replaced, the session canvas kept from rendering, NULL tested alike on
  Qt 5 and Qt 6, and SQLite read with the connection closed.

It imports QGIS at its top and FiberQ's modules inside its functions, so importing it runs no plugin code. A test
file that uses it needs QGIS, so it imports ``qgis`` first, then ``support.core_env``, then ``fiberq`` (the fast
stage leaves such a file out, docs/testing.md), and declares its own ``project`` fixture::

    @pytest.fixture
    def project(qgis_app):
        with clean_project() as prj:
            yield prj

No earlier test file or module imports it.
"""
import contextlib
import sqlite3
import time

from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsLayerTreeGroup, QgsLayerTreeLayer,
                       QgsProject, QgsVectorLayer)
from qgis.PyQt.QtCore import QCoreApplication, QSettings
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

#: The entries FiberQ's managers write into the project, as ``(scope, key)``: relations, latent elements and colour
#: catalogues (``DataManager``, ``ColorManager``), picture and drawing links (``core/feature_links.py``) and the
#: schema marker (``core/schema_version.py``). ``removeAllMapLayers()`` leaves entries in place.
ENTRIES = (
    ("StuboviPlugin", "Relacije/relations_v1"),
    ("StuboviPlugin", "LatentElements/latent_v1"),
    ("StuboviPlugin", "ColorCatalogs/catalogs_v1"),
    ("FiberQPlugin", "FeatureLinks/images_v1"),
    ("FiberQPlugin", "FeatureLinks/drawings_v1"),
    ("FiberQPlugin", "FeatureLinks/drawing_layers_v1"),
    ("FiberQPlugin", "schema/schema_version"),
)

#: Where QGIS keeps a project's ellipsoid.
_ELLIPSOID = ("Measure", "/Ellipsoid")

#: The prefix of FiberQ's own keys in QGIS's settings (``FiberQ/lang``, ``FiberQ/default_cable_type``, ...).
_SETTINGS_PREFIX = "FiberQ/"

_ABSENT = object()


def _entries():
    """``ENTRIES``, the same entries under the names FiberQ's modules give them now, and each one's quarantine copy."""
    from fiberq.core import feature_links, schema_version
    from fiberq.core.color_manager import ColorManager
    from fiberq.core.data_manager import DataManager
    from fiberq.core.project_store import QUARANTINE_SUFFIX

    keys = set(ENTRIES)
    for key in (DataManager.RELATIONS_KEY, DataManager.LATENT_KEY, DataManager.COLOR_CATALOGS_KEY,
                ColorManager.COLOR_CATALOGS_KEY):
        keys.add((DataManager.PLUGIN_NAMESPACE, key))
    for kind in (feature_links.IMAGES, feature_links.DRAWINGS, feature_links.DRAWING_LAYERS):
        keys.add((feature_links.SCOPE, "FeatureLinks/%s" % kind))
    keys.add((schema_version.SCHEMA_VERSION_SCOPE, schema_version.SCHEMA_VERSION_KEY))
    quarantined = [(scope, key + QUARANTINE_SUFFIX) for scope, key in keys]
    return sorted(keys.union(quarantined))


def empty_project(project):
    """Take out of ``project`` what ``removeAllMapLayers()`` leaves behind and the core managers write.

    The layers; then every layer-tree node, since a group (Pipes, Drawings) outlives its layers; the custom layer
    order; and FiberQ's entries. The entries are removed under the keys in ``ENTRIES``, under the keys FiberQ's
    modules name today (so a test run against a changed key leaves no entry behind for the next test), and under
    each of these with ``project_store``'s quarantine suffix, where FiberQ keeps an entry it could not read.
    """
    project.removeAllMapLayers()
    root = project.layerTreeRoot()
    root.removeAllChildren()
    root.setHasCustomLayerOrder(False)
    for scope, key in _entries():
        project.removeEntry(scope, key)


def fiberq_settings():
    """FiberQ's keys in QGIS's settings (those under ``FiberQ/``), with their values."""
    settings = QSettings()
    return {key: settings.value(key) for key in settings.allKeys() if key.startswith(_SETTINGS_PREFIX)}


def undo_settings(before):
    """Put FiberQ's settings back as ``before`` (from ``fiberq_settings()``) had them; return the keys that differed.

    A changed key gets its old value back and an added key is removed; then the settings are written to disk.
    """
    after = fiberq_settings()
    changed = sorted(key for key in set(before) | set(after) if before.get(key, _ABSENT) != after.get(key, _ABSENT))
    settings = QSettings()
    for key in changed:
        if key in before:
            settings.setValue(key, before[key])
        else:
            settings.remove(key)
    settings.sync()
    return changed


@contextlib.contextmanager
def clean_project():
    """QGIS's project, emptied before and after the ``with`` block, with no CRS and no ellipsoid during it.

    It empties the project with ``empty_project()``, never ``QgsProject.clear()``: ``clear()`` costs about 1 ms a
    call on QGIS 3.22, 0.15 s on 3.44 and 0.35 s on 4.2 (``removeAllMapLayers()`` about 0.1 ms), and the first
    versions of these test files took 36 to 62 s each on QGIS 4.2 with a ``clear()`` before and after each test,
    against about 1 s without.

    ``removeAllMapLayers()`` keeps the project's CRS and its ellipsoid, so a CRS or ellipsoid left by an earlier test
    file would reach the test, and a single file would start from another state than a whole leg. So the block
    starts with no CRS and no ``Measure/Ellipsoid`` entry, and the CRS and the entry are put back afterwards. The
    entry is what is recorded, not ``ellipsoid()``: QGIS stores an ellipsoid set on a project with no CRS but reads
    it as "NONE" until the project has a CRS. With neither, FiberQ measures on the ellipsoid of the layer's own CRS
    (``utils/measure.py``: WGS 84, EPSG:7030, for EPSG:3857); a test that relies on that asserts it, and never sets
    an ellipsoid.

    pytest-qgis keeps QGIS's settings in ``<rootdir>/.qgis-settings``, which a run in place keeps for the next run.
    So FiberQ's settings are recorded before the block and, after it, any that changed get their old value back and
    any that were added are removed, whatever happened inside. Then, on a normal exit only, it fails naming the
    keys. In the ``project`` fixture that is a teardown error after every test whose code changed one, whether the
    test passed, failed or was an expected failure, since pytest never throws a test's exception into a fixture;
    used directly, a test's own exception goes on out unchanged.
    """
    project = QgsProject.instance()
    empty_project(project)
    crs = project.crs()
    ellipsoid, has_ellipsoid = project.readEntry(*_ELLIPSOID)
    before = fiberq_settings()
    project.setCrs(QgsCoordinateReferenceSystem())
    project.removeEntry(*_ELLIPSOID)
    try:
        yield project
    finally:
        changed = undo_settings(before)
        empty_project(project)
        project.setCrs(crs)
        if has_ellipsoid:
            project.writeEntry(_ELLIPSOID[0], _ELLIPSOID[1], ellipsoid)
        else:
            project.removeEntry(*_ELLIPSOID)
    _report_settings(changed)


def _report_settings(changed):
    """Fail naming the FiberQ settings a test changed. A function of its own, so that pytest's report of the failure
    shows this short function rather than the whole of ``clean_project()``."""
    assert not changed, "FiberQ settings changed (now undone): %s" % changed


class MessageBar:
    """A message bar that keeps what it is told: each ``push*`` call as ``(method, text)`` in ``messages``.

    ``text`` is the message, the last positional argument that is a string (``pushInfo(title, text)``,
    ``pushMessage(title, text, level, duration)``), else ``""``.
    """

    def __init__(self):
        self.messages = []

    def __getattr__(self, name):
        if not name.startswith("push"):
            raise AttributeError(name)

        def push(*args, **kwargs):
            texts = [arg for arg in args if isinstance(arg, str)]
            self.messages.append((name, texts[-1] if texts else ""))
        return push


class _MapSettings:
    def __init__(self, crs):
        self._crs = crs

    def destinationCrs(self):
        return self._crs


class _Canvas:
    def __init__(self, crs, units_per_pixel):
        self._settings = _MapSettings(crs)
        self._units_per_pixel = units_per_pixel

    def mapSettings(self):
        return self._settings

    def mapUnitsPerPixel(self):
        return self._units_per_pixel


class CoreIface:
    """What the core managers read from QGIS's ``iface``, with a map canvas in the CRS and at the scale given.

    The core modules read ``mapCanvas().mapSettings().destinationCrs()`` (the CRS a new layer is made in),
    ``mapCanvas().mapUnitsPerPixel()`` (lay cable takes 6 pixels of it as its tolerance), ``messageBar().push*()``
    (a ``MessageBar`` here), ``mainWindow()`` (a parent for dialogs: None here) and ``activeLayer()`` (the attribute
    ``active_layer``, None until a test sets it). Anything else asked of it raises AttributeError.

    pytest-qgis's canvas has no CRS on any leg (authid "", 1.0 map units per pixel), so ``LayerManager.get_crs()``
    answers "" and every ``ensure_*`` function makes its layer without a CRS: a test of it would pass for the wrong
    reason. Setting that canvas's CRS would carry over into later tests. This canvas is a plain object: it never
    renders, and nothing of it outlives the test.
    """

    def __init__(self, crs="EPSG:3857", units_per_pixel=0.5):
        self._canvas = _Canvas(QgsCoordinateReferenceSystem(crs), units_per_pixel)
        self._bar = MessageBar()
        self.active_layer = None

    def mapCanvas(self):
        return self._canvas

    def messageBar(self):
        return self._bar

    def mainWindow(self):
        return None

    def activeLayer(self):
        return self.active_layer


class Core:
    """What the module-level layer functions take for the plugin: an object with ``iface``.

    ``layer_manager._ensure_region_layer(core)``, ``_ensure_objects_layer(core)`` and
    ``_ensure_element_layer_with_style(core, name)``.
    """

    def __init__(self, iface):
        self.iface = iface


def _stem(layer_id):
    """The part of a layer id that comes from the layer's name: the id less its 36-character uuid."""
    if len(layer_id) > 37 and layer_id[-37] == "_":
        return layer_id[:-36]
    return layer_id


def memory_layer(project, uri, name, rows=(), fields=(), crs="EPSG:3857", group=None):
    """A memory layer, valid, holding ``rows``, added to ``project`` (into ``group`` if one is given).

    ``uri`` is the geometry type ("Point", "LineString", "None", ...); ``fields`` are "name" (a string field) or
    "name:type" as a memory layer's URI takes them ("visina:double", "broj:integer"). Each row is ``(geometry,
    {field: value})``, the geometry a ``QgsGeometry``, a WKT string or None. QGIS reads some broken WKT without a
    word ("LINESTRING(0 0, 1)" as "LineString (0 0)"); a string it cannot read, or reads as an empty geometry that
    the string does not call EMPTY ("POINT("), is refused.

    A URI "double" field has 5 decimals on the memory provider: a value added with its feature keeps every digit,
    but one changed later (``changeAttributeValue``) is rounded to 5 decimals. For a figure compared to more than
    that, make the field "double(20,0)", or add it with ``utils.compat.new_field`` after the call.

    The project lists its layers (``mapLayers()``) in the order of their ids, and QGIS makes a layer's id from the
    name it is made with: every character other than an ASCII letter, a digit or "_" becomes "_", and "_" and a
    random uuid of 36 characters follow. So two layers come back in either order when the stem of one id (the id
    less its uuid) begins the other's: "Route" and "Route control" ("Route_" and "Route_control_"), or "ODF" and
    "ODF 2"; "ODF" and "OKNA", or "Joint Closures" and "Joint Closure TO", come back in one order (measured on
    QGIS 3.22 and 4.2). So the layer is refused if its stem begins the stem of a layer already in the project, or
    the other way round; two layers of one name are the plain case. The check reads ids, because a layer renamed
    after it was made keeps the stem of its first name.

    Without a group, the layer's node goes first in the layer tree, where QGIS puts a new layer; with one, it goes
    into that group only. With ``project=None`` the layer is left out of any project; that is only for a layer the
    code under test is handed directly.
    """
    spec = "".join("&field=%s" % (field if ":" in field else field + ":string") for field in fields)
    layer = QgsVectorLayer("%s?crs=%s%s" % (uri, crs, spec), name, "memory")
    assert layer.isValid(), "the memory layer %r (%s, %s) is not valid" % (name, uri, spec)
    features = []
    for geometry, values in rows:
        feature = QgsFeature(layer.fields())
        if isinstance(geometry, str):
            parsed = QgsGeometry.fromWkt(geometry)
            assert not parsed.isNull(), "not a WKT geometry: %r" % geometry
            assert not parsed.isEmpty() or "EMPTY" in geometry.upper(), "a broken WKT geometry: %r" % geometry
            feature.setGeometry(parsed)
        elif geometry is not None:
            feature.setGeometry(geometry)
        for field, value in values.items():
            feature[field] = value
        features.append(feature)
    if features:
        added, _ = layer.dataProvider().addFeatures(features)
        assert added, "the memory layer %r refused its rows: %s" % (name, layer.dataProvider().errors())
    layer_id = layer.id()
    assert len(layer_id) > 37 and layer_id[-37] == "_", "a layer id not of the form <name>_<uuid>: %r" % layer_id
    if project is None:
        return layer
    stem = layer_id[:-36]
    for other in project.mapLayers().values():
        other_stem = _stem(other.id())
        assert not stem.startswith(other_stem) and not other_stem.startswith(stem), (
            "layers %r and %r: the id stem %r begins %r or the other way round, so mapLayers() lists them in either "
            "order; name one of them otherwise" % (other.name(), name, other_stem, stem))
    if group is None:
        assert project.addMapLayer(layer) is not None, "the project refused the layer %r" % name
    else:
        assert project.addMapLayer(layer, False) is not None, "the project refused the layer %r" % name
        assert group.addLayer(layer) is not None, "the group %r refused the layer %r" % (group.name(), name)
    return layer


def tree_rows(node):
    """The layer tree under ``node`` as rows: "G:<name>" for a group and "L:<name>" for a layer, in the tree's order,
    two spaces deeper for each level (``["G:Pipes", "  L:PE pipes", "G:Routes"]``).

    It never tests a node for truth: on QGIS 4.0 an empty group and every layer node are false.
    """
    rows = []
    _add_tree_rows(node, "", rows)
    return rows


def _add_tree_rows(node, indent, rows):
    for child in node.children():
        if isinstance(child, QgsLayerTreeLayer):
            rows.append("%sL:%s" % (indent, child.name()))
        elif isinstance(child, QgsLayerTreeGroup):
            rows.append("%sG:%s" % (indent, child.name()))
            _add_tree_rows(child, indent + "  ", rows)
        else:
            rows.append("%s?:%s" % (indent, child.name()))


def wired_plugin(iface):
    """A ``FiberQPlugin`` that holds only its managers, built and wired as ``main_plugin.py:897-984`` builds them.

    ``FiberQPlugin.__init__`` is not run: before line 897 it installs the plugin's translator and forgets a language
    the user never picked (``main_plugin.py:880-886``), both of which read or write settings, and after line 984 it
    builds the undo manager, which it hands to the cable, route and slack managers, and the command manager. Those
    three managers read it with ``getattr(self, 'undo_manager', None)``, so here nothing is recorded for FiberQ Undo.

    The object gets ``iface``, ``selected_cable_type`` and ``selected_cable_subtype`` (None, as at :894-895), and the
    eleven managers of :897-984 in the plugin's order and with its arguments, SlackManager's cable-style callback
    included. Each of those constructors only stores what it is given. As in the plugin, none of the managers is
    missing, so a manager's own copy for "another manager failed to build" runs only if a manager it hands work to
    raises, which no input here makes it do. When the plugin's wiring changes, this changes with it.
    """
    from fiberq.core.cable_manager import CableManager
    from fiberq.core.color_manager import ColorManager
    from fiberq.core.data_manager import DataManager
    from fiberq.core.drawing_manager import DrawingManager
    from fiberq.core.export_manager import ExportManager
    from fiberq.core.layer_manager import LayerManager
    from fiberq.core.pipe_manager import PipeManager
    from fiberq.core.relations_manager import RelationsManager
    from fiberq.core.route_manager import RouteManager
    from fiberq.core.slack_manager import SlackManager
    from fiberq.core.style_manager import StyleManager
    from fiberq.main_plugin import FiberQPlugin

    plugin = FiberQPlugin.__new__(FiberQPlugin)
    plugin.iface = iface
    plugin.selected_cable_type = None
    plugin.selected_cable_subtype = None
    plugin.layer_manager = LayerManager(iface, plugin)
    plugin.style_manager = StyleManager(iface, plugin)
    plugin.data_manager = DataManager(iface, plugin)
    plugin.export_manager = ExportManager(iface, plugin)
    plugin.slack_manager = SlackManager(iface, plugin.layer_manager, plugin.style_manager)
    plugin.slack_manager.set_cable_style_callback(lambda lyr: plugin._stylize_cable_layer(lyr))
    plugin.route_manager = RouteManager(iface, plugin.style_manager)
    plugin.cable_manager = CableManager(iface, plugin.style_manager, plugin.data_manager, plugin.route_manager)
    plugin.relations_manager = RelationsManager(plugin.data_manager)
    plugin.drawing_manager = DrawingManager(iface, plugin.layer_manager)
    plugin.pipe_manager = PipeManager(iface, plugin.layer_manager, plugin.style_manager, plugin.data_manager)
    plugin.color_manager = ColorManager(iface, plugin.data_manager)
    return plugin


def patch_cable_picker(monkeypatch, values):
    """Replace the cable picker with one that is accepted at once and answers ``values``; return its class.

    Lay cable imports ``CablePickerDialog`` from ``fiberq.dialogs.cable_dialog`` when it runs
    (``cable_manager.py:684``), so the class is replaced on that module. The stand-in takes any arguments, its
    ``exec()`` returns ``QDialog.DialogCode.Accepted`` and its ``values()`` a copy of ``values``. ``monkeypatch`` is
    pytest's fixture or a ``pytest.MonkeyPatch.context()``.
    """
    from fiberq.dialogs import cable_dialog

    answer = dict(values)

    class CablePicker:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return dict(answer)

    monkeypatch.setattr(cable_dialog, "CablePickerDialog", CablePicker)
    return CablePicker


def record_message_boxes(monkeypatch):
    """Answer ``QMessageBox.information``, ``.warning`` and ``.critical`` at once; return the list of their texts.

    Offscreen, a message box waits for a click that never comes, until the stage's time limit. Each of the three
    now appends its text (its third argument) to the list and returns ``QMessageBox.StandardButton.Ok``.
    ``monkeypatch`` is pytest's fixture or a ``pytest.MonkeyPatch.context()``.
    """
    said = []

    def answer(*args, **kwargs):
        said.append(str(args[2] if len(args) > 2 else kwargs.get("text", "")))
        return QMessageBox.StandardButton.Ok

    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(answer))
    return said


@contextlib.contextmanager
def canvas_not_rendering(canvas):
    """``canvas`` with its rendering off in the ``with`` block; afterwards its earlier flag is put back.

    pytest-qgis's session canvas renders the project's layers in a worker thread, which made GeoPackage tests flaky
    on QGIS 4.2 (``test_lay_cable_route_search.py``). A test file run alone never renders, since the canvas starts
    with invalid settings, but a whole leg does, from the first test that reads a project file into QGIS's project.
    The flag stops new refreshes only: a refresh the canvas scheduled before it went off still starts its render job
    the next time events are processed (measured on QGIS 4.2.3). So the block first lets such a job start and stops
    it, and no render job holds the layers the block adds. The earlier flag is put back, not True, so a block inside
    another leaves rendering off.
    """
    previous = canvas.renderFlag()
    canvas.setRenderFlag(False)
    _stop_scheduled_render(canvas)
    try:
        yield canvas
    finally:
        canvas.setRenderFlag(previous)


def _stop_scheduled_render(canvas, rounds=20):
    """Process events for about 0.1 s and stop each render job that starts meanwhile (a refresh runs on a 1 ms
    timer)."""
    for _ in range(rounds):
        time.sleep(0.005)
        QCoreApplication.processEvents()
        if canvas.isDrawing():
            canvas.stopRendering()


def sqlite_rows(path, sql):
    """The rows ``sql`` selects from the SQLite file at ``path``, read with a connection that is then closed.

    ``with sqlite3.connect(path)`` commits at the end of the block but does not close the connection: earlier tests
    that read GeoPackages that way left 49 "unclosed database" warnings on Python 3.14.
    """
    with contextlib.closing(sqlite3.connect(path)) as conn:
        return conn.execute(sql).fetchall()


def is_null(value):
    """True for a NULL read from a layer, however this QGIS hands it back: None on Qt 6, a null QVariant on Qt 5.

    The same test as ``core/interchange_import.py``'s ``_is_null``. Two values read from a provider compare with
    ``==`` on both; ``is None`` and ``type()`` do not.
    """
    return value is None or (hasattr(value, "isNull") and value.isNull())
