"""FiberQ's two starts in the app stages: the install from the zip, and a short core workflow with a reload.

ci/app-smoke.sh starts the real QGIS desktop twice, in one fresh profile, with ``--code tests/app/start.py``, which
runs the start that ``APP_START`` names through the app runner (tests/app/runner.py):

- ``install``: QGIS starts without FiberQ. The start installs the zip the stage built with QGIS's own Install from
  ZIP code (``installFromZipFile`` of ``pyplugin_installer``, without the tab's file chooser and its question). It
  checks that FiberQ loaded from the profile and logged no Python line, and that its toolbars, drop-downs, Plugins
  menu entries and keys are what the initGui golden file (tests/initgui_golden.json) records, every field;
- ``workflow``: FiberQ is enabled now, so QGIS loads it at startup. The start checks that load the same way, less
  the tooltips, which QGIS rewrites for the actions it registers at startup, and less the keys outside the menus,
  since QGIS loads FiberQ before the start can record what was there without it. After Project > New, with the
  project in WGS 84 / UTM zone 34N, it does what a person does, through FiberQ's own buttons, drop-downs, map
  tools and dialogs: a route drawn by hand, an ODF and a TB placed on its two ends, both selected, an underground
  backbone cable laid between them, the project validated and exported as an interchange bundle. Last it reloads
  FiberQ and checks it again, every field.

``STARTS`` maps each start's slug to its scenario, and ``EXPECTED`` lists the ids of the checks each one records;
the start declares them first, and ``ci/report.py app-junit`` fails it for each one that did not run. The ids stay
the same from run to run, so ci/compare.sh compares them between runs as test ids: a new check gets a new id.

What makes the starts the same on every run: each load is followed by a wait for the line that ends FiberQ's
deferred migration (``settled()``), before the plugin's toolbars and keys are recorded (the golden checks) or
anything is clicked; every other wait is for a condition, with a time limit; pixel tolerances derive from the map's
units per pixel after the zoom; counts and snapped points are exact. A check the rest of the start depends on is a
``require()``: when it fails, the start ends there with exit code 1. The environment is read with
``os.environ[...]``, so a missing variable raises and the start ends with exit code 5: ``APP_ZIP`` (the zip) and
``APP_GOLDEN`` (the golden file); the runner reads ``APP_OUT`` and ``APP_DEADLINE_S``. FiberQ is reached through
QGIS (``qgis.utils.plugins``) and ``sys.modules``, never imported from the tested tree.
"""
import os
import re
import sqlite3
import sys
from urllib.parse import quote

import pyplugin_installer
import qgis.utils
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsProject, QgsRectangle, QgsSettings
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QFileDialog, QInputDialog

from app.runner import layer_named, message_box, title_starts
from support.initgui_snapshot import differences, dump_golden, load_golden, outside_baseline, record

#: FiberQ's package and plugin name in QGIS.
PLUGIN = "fiberq"

#: The object name of FiberQ's toolbar, and the name of its menu under Plugins.
TOOLBAR = "FiberQToolbar"
PLUGIN_MENU = "FiberQ"

#: The workflow's project: WGS 84 / UTM zone 34N (metres), the route's two ends (the ODF at A, the TB at B, 160 m
#: east) and the extent the map is zoomed to, as (x min, y min, x max, y max).
CRS = "EPSG:32634"
A = (500040.0, 4950050.0)
B = (500200.0, 4950050.0)
VIEW = (499980.0, 4949990.0, 500260.0, 4950110.0)

#: The window's place and size, set first in each start: with no window manager it opens small. QGIS 3.40 draws at
#: a device pixel ratio of 1.04 under Xvfb, so its screenshots are 1666 x 937 pixels, 1600 x 900 logical ones.
WINDOW = (0, 0, 1600, 900)

#: Lines on QGIS's "Python error" and "Python warning" tags that a ``no_python_lines`` check leaves out, each as
#: (tag, regular expression searched in the message, reason). Empty: no such line was seen on either leg. An entry
#: names the image digest it was seen with, and why the line is not FiberQ's, in its comment.
PYTHON_LINES_ALLOWED = ()

#: The message-log line that ends FiberQ's deferred migration, and how long to wait for it. Each load arms the
#: migration on a 2 s timer, and fiberq/utils/uuid_utils.py logs this line on each run of it. A change to the
#: deferred migration that drops the line changes ``settled()`` in the same change.
SETTLED_TAG = "FiberQ UUID"
SETTLED_LINE = "UUID migration summary"
SETTLED_MS = 15000

#: The checks of the install start, in the order it records them.
INSTALL_IDS = (
    "install.not_loaded_before", "install.installed", "install.logged_success", "install.enabled",
    "install.from_zip", "install.deferred_migration_ran", "install.language", "install.golden_entries",
    "install.golden_containers", "install.golden_outside", "install.no_python_lines", "end.windows")

#: The checks of the workflow start, in the order it records them.
WORKFLOW_IDS = (
    "load.loaded", "load.logged", "load.from_zip", "load.deferred_migration_ran", "load.language",
    "load.golden_entries", "load.golden_containers", "load.no_python_lines",
    "project.canvas_shown", "project.output_size", "project.crs", "project.extent",
    "route.features", "route.type", "route.vertices", "route.drawn_length", "route.stored_length",
    "place_odf.features", "place_odf.snapped", "place_odf.name",
    "place_tb.features", "place_tb.snapped", "place_tb.name",
    "select.selected",
    "cable.features", "cable.ends", "cable.length", "cable.attributes",
    "validate.ran", "validate.counts", "validate.layers", "validate.panel_shown",
    "export.message", "export.file", "export.tables",
    "reload.started", "reload.loaded", "reload.from_zip", "reload.deferred_migration_ran", "reload.golden_entries",
    "reload.golden_containers", "reload.golden_outside", "reload.no_python_lines",
    "end.no_python_lines", "end.windows")

#: Each start's checks, by its slug.
EXPECTED = {"install": INSTALL_IDS, "workflow": WORKFLOW_IDS}


# ---- helpers ------------------------------------------------------------------------------------------------------
def fiberq():
    """FiberQ's plugin object in QGIS, or None when it is not loaded."""
    return qgis.utils.plugins.get(PLUGIN)


def language():
    """FiberQ's interface language, from the loaded copy's ``fiberq.i18n``."""
    return sys.modules[PLUGIN + ".i18n"].effective_language()


def profile_plugin():
    """The folder FiberQ is installed in, in the profile QGIS runs with."""
    return os.path.realpath(os.path.join(QgsApplication.qgisSettingsDirPath(), "python", "plugins", PLUGIN))


def loaded_from():
    """The file the loaded ``fiberq`` package comes from, or None when none is loaded."""
    module = sys.modules.get(PLUGIN)
    path = getattr(module, "__file__", None)
    return os.path.realpath(path) if path else None


def from_zip(r, required=False):
    """Check ``from_zip``: the loaded ``fiberq`` package is the profile's copy, which the install wrote from the zip,
    never the tested tree's; return whether it is. ``required``: a ``require()``, which ends the start if not."""
    home, path = profile_plugin(), loaded_from()
    inside = path is not None and path.startswith(home + os.sep)
    checked = r.require if required else r.check
    return checked("from_zip", True, inside, what="fiberq is loaded from the profile's copy %s: %s" % (home, path))


def settled(r, since):
    """Wait until FiberQ's deferred migration logged its last line after the mark ``since``; return whether it did."""
    return r.wait_for_log(SETTLED_TAG, SETTLED_LINE, since, SETTLED_MS)


def python_lines(r, since):
    """The lines on QGIS's Python error and Python warning tags after the mark ``since``, as ``"<tag>: <message>"``
    (its first 400 characters), less those that ``PYTHON_LINES_ALLOWED`` leaves out."""
    lines = []
    for entry in r.python_problems(since):
        if any(entry["tag"] == tag and re.search(pattern, entry["message"])
               for tag, pattern, _reason in PYTHON_LINES_ALLOWED):
            continue
        lines.append("%s: %s" % (entry["tag"], entry["message"][:400]))
    return lines


def plugin_menus(iface):
    """Each entry of the Plugins menu whose text, ``&`` left out, is ``PLUGIN_MENU`` and that opens a menu, as
    ``(its text, its entries without separators)``: the menus FiberQ added under Plugins. Two such menus give two
    containers, which the golden file fails."""
    found = []
    for action in iface.pluginMenu().actions():
        menu = action.menu()
        if menu is not None and action.text().replace("&", "") == PLUGIN_MENU:
            found.append((action.text(), [entry for entry in menu.actions() if not entry.isSeparator()]))
    return found


def golden_checks(r, golden_path, prefix, baseline=None, skip=()):
    """Record FiberQ's toolbars, drop-downs, Plugins menu entries and keys as they are now, as the golden file has
    them, into ``actions-<prefix>.json``, and check them against the golden file at ``golden_path``:
    ``golden_entries`` (the entries of each container, less the fields in ``skip``), ``golden_containers`` (which
    containers there are, and what they are) and, with a ``baseline`` taken before FiberQ loaded,
    ``golden_outside`` (the keys it binds outside them)."""
    iface = r.iface
    seen = record(fiberq(), plugin_menus(iface), iface.mainWindow(), iface.mapCanvas(), language(), baseline)
    with open(os.path.join(r.out, "actions-%s.json" % prefix), "x", encoding="utf-8", newline="\n") as fh:
        fh.write(dump_golden(seen))
    golden = load_golden(golden_path)
    what = "every entry of every container, in order, as the golden file has it"
    if skip:
        what += ", less its %s" % ", ".join(skip)
    r.check("golden_entries", [], differences(golden, seen, ("entries",), skip), what=what)
    r.check("golden_containers", [], differences(golden, seen, ("containers",)),
            what="the toolbars, drop-downs and Plugins menus, each with its title, object name and state")
    if baseline is not None:
        r.check("golden_outside", [], differences(golden, seen, ("outside",)),
                what="the actions and QShortcuts FiberQ adds to the main window and the map canvas")


def features_within(r, name, count, timeout_ms=5000):
    """The number of features on the layer ``name`` once it is ``count``, or when ``timeout_ms`` passed; None when
    there is no such layer."""
    r.wait_until(lambda: layer_named(name) is not None and layer_named(name).featureCount() == count, timeout_ms,
                 what='%d feature(s) on the layer "%s"' % (count, name))
    layer = layer_named(name)
    return layer.featureCount() if layer is not None else None


def first_feature(name):
    """The first feature of the layer ``name``."""
    return next(layer_named(name).getFeatures())


def xy(point, digits=3):
    """A point as ``[x, y]``, rounded to ``digits``."""
    return [round(point[0], digits), round(point[1], digits)]


def distance(a, b):
    """The distance between two points ``(x, y)``, in map units."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def gpkg_tables(path):
    """``{table: rows}`` of every feature and attribute table that the GeoPackage at ``path`` lists, read with
    sqlite3, read only."""
    con = sqlite3.connect("file:%s?mode=ro" % quote(path), uri=True)
    try:
        names = [name for (name,) in con.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type IN ('features', 'attributes') ORDER BY 1")]
        return {name: con.execute('SELECT COUNT(*) FROM "%s"' % name.replace('"', '""')).fetchone()[0]
                for name in names}
    finally:
        con.close()


def window(r):
    """Put QGIS's main window where ``WINDOW`` says."""
    main_window = r.iface.mainWindow()
    main_window.move(WINDOW[0], WINDOW[1])
    main_window.resize(WINDOW[2], WINDOW[3])
    r.note("main window", size=[main_window.width(), main_window.height()],
           guard="fiberq_app_guard" in sys.modules)


# ---- the install start -------------------------------------------------------------------------------------------
def install(r):
    """The install start: Install from ZIP in a profile without FiberQ, and the checks of what it loaded."""
    r.expect_checks(EXPECTED["install"])
    window(r)
    zip_path, golden = os.environ["APP_ZIP"], os.environ["APP_GOLDEN"]
    iface = r.iface
    r.step("install", "Plugins > Manage and Install Plugins > Install from ZIP, with the zip this stage built")
    r.check("not_loaded_before", False, PLUGIN in qgis.utils.plugins, what="FiberQ is not loaded before the install")
    baseline = outside_baseline(iface.mainWindow(), iface.mapCanvas())
    mark = r.log_mark()
    # the tab's Install Plugin button; what it returns differs (None on QGIS 3.40, True on 4.2), so it is not read
    pyplugin_installer.instance().installFromZipFile(zip_path)
    active = r.wait_until(lambda: PLUGIN in qgis.utils.active_plugins, 10000, what="FiberQ in the active plugins")
    r.require("installed", True, active, what="FiberQ is among QGIS's active plugins within 10 s")
    r.check("logged_success", True,
            any("Plugin installed successfully" in e["message"] for e in r.log_since(mark, "Messages")),
            what='QGIS logged "Plugin installed successfully" on its Messages tag')
    r.check("enabled", True, QgsSettings().value("PythonPlugins/" + PLUGIN, False, bool),
            what="the profile has FiberQ enabled (PythonPlugins/fiberq)")
    from_zip(r)
    r.check("deferred_migration_ran", True, settled(r, mark),
            what="FiberQ's deferred migration logged %r within %d s" % (SETTLED_LINE, SETTLED_MS // 1000))
    r.check("language", "en", language(), what="FiberQ's interface language, which --lang en_US sets")
    golden_checks(r, golden, "install", baseline)
    r.check("no_python_lines", [], python_lines(r, 0), what="no line on QGIS's Python tags since QGIS started")
    r.screenshot("installed")
    r.step("end", "The whole start")
    r.check("windows", [], r.expected_left(), what="every window the start expected came")


# ---- the workflow start ------------------------------------------------------------------------------------------
def workflow(r):
    """The workflow start: the startup load, the core workflow through FiberQ's own controls, and a reload."""
    r.expect_checks(EXPECTED["workflow"])
    window(r)
    golden = os.environ["APP_GOLDEN"]
    load(r, golden)
    mupp = project(r)
    vertices, length = route(r, mupp)
    place(r, "place_odf", "ODF", "ODF 1", vertices[0], "first", mupp)
    place(r, "place_tb", "TB", "TB 1", vertices[-1], "last", mupp)
    select(r, vertices)
    cable(r, length)
    validate(r)
    export(r)
    reload(r, golden)
    r.step("end", "The whole session")
    r.check("no_python_lines", [], python_lines(r, 0), what="no line on QGIS's Python tags since QGIS started")
    r.check("windows", [], r.expected_left(), what="every window the start expected came")


def load(r, golden):
    """FiberQ as QGIS loaded it at startup."""
    r.step("load", "Start QGIS with FiberQ installed and enabled: QGIS loads it at startup")
    r.require("loaded", True, PLUGIN in qgis.utils.active_plugins, what="FiberQ is among QGIS's active plugins")
    r.check("logged", True,
            any(e["tag"] == "Plugins" and e["message"] == "Loaded FiberQ (package: fiberq)" for e in r.log()),
            what='QGIS logged "Loaded FiberQ (package: fiberq)" on its Plugins tag')
    from_zip(r, required=True)
    r.check("deferred_migration_ran", True, settled(r, 0),
            what="FiberQ's deferred migration logged %r since QGIS started" % SETTLED_LINE)
    r.check("language", "en", language(), what="FiberQ's interface language, which --lang en_US sets")
    golden_checks(r, golden, "load", skip=("tooltip",))
    r.check("no_python_lines", [], python_lines(r, 0), what="no line on QGIS's Python tags since QGIS started")
    r.screenshot("loaded")


def project(r):
    """A new project in metres, the map zoomed to the work area; return the map units per pixel."""
    r.step("project", "Project > New; the project in WGS 84 / UTM zone 34N, zoomed to the work area")
    canvas = r.iface.mapCanvas()
    r.note("canvas before", visible=canvas.isVisible(), size=[canvas.width(), canvas.height()])
    r.iface.actionNewProject().trigger()   # QGIS 3.40 shows its welcome page instead of the map until a project
    shown = r.wait_until(lambda: canvas.isVisible() and canvas.width() > 800, 5000,
                         what="the map shown and wider than 800 px")
    r.check("canvas_shown", True, shown, what="the map is shown and wider than 800 px within 5 s")
    QgsProject.instance().setCrs(QgsCoordinateReferenceSystem(CRS))
    # The map takes its new size a moment after the window's (QGIS 3.40 holds it back on a timer): zoom only once
    # the map's output size is the canvas's, or a click lands on a map drawn for the old size.
    sized = r.wait_until(lambda: abs(canvas.mapSettings().outputSize().width() - canvas.viewport().width()) <= 2,
                         5000, what="the map's output width the canvas's, within 2 px")
    r.check("output_size", True, sized, what="the map's output width is the canvas's, within 2 px, within 5 s")
    canvas.setExtent(QgsRectangle(*VIEW))
    canvas.refresh()
    r.wait_until(lambda: canvas.mapSettings().destinationCrs().authid() == CRS, 3000, what="the map in " + CRS)
    canvas.waitWhileRendering()
    r.check("crs", CRS, canvas.mapSettings().destinationCrs().authid(), what="the map's CRS")
    extent = canvas.extent()
    seen = [round(v, 3) for v in (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())]
    inside = seen[0] <= VIEW[0] and seen[1] <= VIEW[1] and seen[2] >= VIEW[2] and seen[3] >= VIEW[3]
    r.check("extent", list(VIEW), seen, ok=inside, what="the map shows the whole work area, to the millimetre")
    mupp = canvas.mapUnitsPerPixel()
    r.note("canvas", size=[canvas.width(), canvas.height()],
           viewport=[canvas.viewport().width(), canvas.viewport().height()],
           output=[canvas.mapSettings().outputSize().width(), canvas.mapSettings().outputSize().height()],
           units_per_pixel=mupp)
    r.screenshot("project")
    return mupp


def route(r, mupp):
    """A route drawn by hand from A to B; return its vertices and its stored length."""
    r.step("route", "Routing > Create a route manually: click A, click B, right-click B; route type Underground")

    def route_type(w):
        r.choose(w.findChild(QComboBox), "Underground")
        r.press_ok(w)
    r.expect(lambda w: isinstance(w, QInputDialog) and w.windowTitle() == "Route type", route_type, "route type")
    r.expect(message_box("FiberQ", "Manual route has been created!"), r.press_ok, "route created")
    r.trigger(r.entry(TOOLBAR, "Routing", "Create a route manually"))
    r.click_map(A)
    r.wait(150)
    r.click_map(B)
    r.wait(150)
    r.click_map(B, Qt.MouseButton.RightButton)
    r.require("features", 1, features_within(r, "Route", 1), what='features on the layer "Route", within 5 s')
    feature = first_feature("Route")
    r.check("type", "podzemna", feature["tip_trase"], what="the route type, tip_trase (Underground)")
    vertices = [(v.x(), v.y()) for v in feature.geometry().vertices()]
    near = len(vertices) == 2 and distance(vertices[0], A) <= 1.5 * mupp and distance(vertices[-1], B) <= 1.5 * mupp
    r.check("vertices", [xy(A), xy(B)], [xy(v) for v in vertices], ok=near,
            what="2 vertices, each within 1.5 px (%.3f m) of the clicks" % (1.5 * mupp))
    planar = feature.geometry().length()
    r.check("drawn_length", 160.0, round(planar, 3), ok=abs(planar - 160.0) <= 3 * mupp,
            what="the route's length on the map, within 3 px (%.3f m) of 160 m" % (3 * mupp))
    stored = feature["duzina"]
    ratio = stored / planar - 1 if planar else None
    r.check("stored_length", 0.0, None if ratio is None else round(ratio, 6),
            ok=ratio is not None and abs(ratio) <= 0.002,
            what="duzina, the stored length, over the length on the map, less 1: within 0.002 (UTM's scale "
                 "factor makes it 0.0004 here)")
    r.note("route", stored_length=stored, planar_length=planar, vertices=vertices)
    r.screenshot("route")
    return vertices, stored


def place(r, step, kind, name, vertex, which, mupp):
    """An element of ``kind`` placed by a click 3 px off the route's vertex ``vertex``, named ``name``."""
    r.step(step, "Placing elements > Place %s: click 3 px off the route's %s vertex; Name %s, OK"
           % (kind, which, name))

    def element_information(w):
        r.type_into(r.field(w, "Name"), name)
        r.press_ok(w)
    r.expect(title_starts("Element information"), element_information, "element information")
    r.expect(message_box("FiberQ", "Element placed!"), r.press_ok, "element placed")
    r.trigger(r.entry(TOOLBAR, "Placing elements", "Place " + kind))
    r.click_map((vertex[0] + 3 * mupp, vertex[1] + 3 * mupp))   # inside the tool's 10 px snap
    r.require("features", 1, features_within(r, kind, 1), what='features on the layer "%s", within 5 s' % kind)
    feature = first_feature(kind)
    point = feature.geometry().asPoint()
    point = (point.x(), point.y())
    r.check("snapped", xy(vertex), xy(point), ok=distance(point, vertex) <= 0.001,
            what="the element is on the route's %s vertex, within 1 mm: the tool snapped it" % which)
    r.check("name", name, feature["naziv"], what="the element's name, naziv")
    r.screenshot(step)


def select(r, vertices):
    """The ODF and the TB, selected by clicks on the route's two vertices, where they are."""
    r.step("select", "Selection > Smart selection (Multiple Layers): click the ODF, then the TB")
    r.trigger(r.entry(TOOLBAR, "Selection", "Smart selection (Multiple Layers)"))
    r.click_map(vertices[0])
    r.wait(150)
    r.click_map(vertices[-1])

    def selected():
        return {name: layer_named(name).selectedFeatureCount() for name in ("ODF", "TB")}
    r.wait_until(lambda: selected() == {"ODF": 1, "TB": 1}, 5000, what="one ODF and one TB selected")
    r.require("selected", {"ODF": 1, "TB": 1}, selected(), what="the selected features of each layer, within 5 s")
    r.screenshot("select")


def cable(r, route_length):
    """An underground backbone cable laid between the two selected elements."""
    r.step("cable", "Cable laying > Underground > Backbone: Number of fibers 12, Name Cable 1, OK")

    def cable_parameters(w):
        r.type_into(r.field(w, "Number of fibers"), 12)
        r.type_into(r.field(w, "Name"), "Cable 1")
        r.press_ok(w)
    r.expect(title_starts("Cable parameters"), cable_parameters, "cable parameters")
    r.expect(message_box("FiberQ", "Cable has been laid along the route!"), r.press_ok, "cable laid")
    r.trigger(r.entry(TOOLBAR, "Cable laying", "Underground", "Backbone"))
    r.require("features", 1, features_within(r, "Underground cables", 1),
              what='features on the layer "Underground cables", within 5 s')
    feature = first_feature("Underground cables")
    r.check("ends", ["ODF 1", "TB 1"], [feature["od"], feature["do"]], what="the cable's ends, od and do")
    length = feature["duzina_m"]
    r.check("length", round(route_length, 3), round(length, 3), ok=abs(length - route_length) <= 0.01,
            what="the cable's length, duzina_m, is the route's, within 1 cm")
    r.check("attributes", ["Optical", "glavni", 12, "Cable 1"],
            [feature["tip"], feature["podtip"], feature["broj_vlakana"], feature["naziv"]],
            what="the cable's tip, podtip, broj_vlakana and naziv")
    r.screenshot("cable")


def validate(r):
    """The project validated with FiberQ's Validate project button."""
    r.step("validate", "Validate project (the toolbar button)")
    plugin = fiberq()
    r.trigger(plugin.action_validate)

    def result():
        panel = getattr(plugin, "_validation_panel", None)
        return panel.result() if panel is not None else None
    r.wait_until(lambda: result() is not None, 10000, what="a result in FiberQ's validation panel")
    found = result()
    item = r.iface.messageBar().currentItem()
    bar = item.text() if item is not None else None
    if found is None:
        r.note("no validation result within 10 s", message_bar=bar)
    else:
        r.note("validation", rules=len(found.ran_rules), feature_counts=found.feature_counts,
               issues=[str(issue) for issue in found.issues][:20], message_bar=bar)
    r.check("ran", [], found.rule_errors if found is not None else ["no validation result"],
            what="every rule ran (the result's rule errors), within 10 s")
    r.check("counts", {"error": 0, "warning": 0, "info": 0}, found.counts_by_severity() if found is not None else None,
            what="the issues found, by severity")
    r.check("layers", 4, len(found.feature_counts) if found is not None else None, what="the layers it checked")
    panel = getattr(plugin, "_validation_panel", None)
    r.check("panel_shown", True, panel is not None and panel.isVisible(), what="the validation panel is shown")
    r.screenshot("validate")


def export(r):
    """The project exported as an interchange bundle, through Plugins > FiberQ."""
    r.step("export", "Plugins > FiberQ > Export interchange bundle...: type the file name, Save")
    target = os.path.join(r.out, "bundle.gpkg")
    r.expect(lambda w: isinstance(w, QFileDialog), lambda w: r.save_file_as(w, target), "file window")
    r.trigger(fiberq().action_export_bundle)

    def written():
        item = r.iface.messageBar().currentItem()
        return os.path.exists(target) and item is not None and item.text().startswith("Wrote ")
    written_ok = r.wait_until(written, 15000, what='the bundle written and "Wrote ..." on the message bar')
    item = r.iface.messageBar().currentItem()
    r.note("message bar", bar=item.text() if item is not None else None)
    r.check("message", True, written_ok, what='the message bar says "Wrote ..." within 15 s')
    exists = os.path.exists(target)
    r.check("file", True, exists, what="the bundle file exists")
    tables = gpkg_tables(target) if exists else None
    r.note("bundle tables", tables=tables)
    r.check("tables", {"ODF": 1, "Route": 1, "TB": 1, "Underground cables": 1, "_fiberq_metadata": 8},
            {name: rows for name, rows in tables.items() if rows} if tables is not None else None,
            what="the rows of every table of the bundle that has rows")
    r.screenshot("export")


def reload(r, golden):
    """FiberQ reloaded in place, and its checks again."""
    r.step("reload", "Reload FiberQ with qgis.utils.reloadPlugin")
    iface = r.iface
    baseline = outside_baseline(iface.mainWindow(), iface.mapCanvas())
    mark = r.log_mark()
    r.check("started", True, bool(qgis.utils.reloadPlugin(PLUGIN)), what="reloadPlugin started FiberQ again")
    r.require("loaded", True, PLUGIN in qgis.utils.active_plugins, what="FiberQ is among QGIS's active plugins")
    from_zip(r)
    r.check("deferred_migration_ran", True, settled(r, mark),
            what="FiberQ's deferred migration logged %r within %d s" % (SETTLED_LINE, SETTLED_MS // 1000))
    golden_checks(r, golden, "reload", baseline)
    r.check("no_python_lines", [], python_lines(r, mark), what="no line on QGIS's Python tags since the reload")
    r.screenshot("reloaded")


#: Each start's scenario, by its slug: what ``APP_START`` names.
STARTS = {"install": install, "workflow": workflow}
