"""Generate terminal slacks opens one edit session per layer, not two per slack.

WP4 task 4.1, item PF-4 (the batch). For every end of every selected cable,
v1.5.0 opened the slack layer for editing, added one point, committed it,
recorded it for Undo and recomputed the cable -- which opened the cable layer,
updated the cable and committed it again, then restyled the layer. Two edit
sessions and two commits per slack, each a reopen of the GeoPackage: 26 s per
100 cables at 25k features.

Now, where one session can stand in for many (``SlackManager._batch_allowed``),
the slacks are built as the loop builds them and committed together, each is
recorded under the fid its commit gave it, and each cable layer is recomputed
in one session and restyled once. Anything refused puts the batch back and the
loop runs as it always ran, so the failures and the partial saves are the
loop's own; a cable layer that refuses is recomputed slack by slack with the
totals the loop saw at each step.

**Counted, not timed**: edit sessions and commits per layer for 4 and then 16
cables of one dataset. The equivalence tests run the loop itself next to the
batch, on fresh copies of one GeoPackage, and compare what reached the file,
the Undo stack and every message, keyed by cable and end rather than by fid.
"""
import re
import sqlite3
from contextlib import closing

import pytest
from qgis.core import (
    Qgis,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.core.interchange_fields import cable_link_fields
from fiberq.core.slack_manager import SlackManager
from fiberq.core.undo_manager import FiberQUndoManager
from fiberq.utils.field_aliases import _migrate_cable_type_values

STRING, DOUBLE, INT = QVariant.String, QVariant.Double, QVariant.Int
SLACK_FIELDS = [("tip", STRING), ("duzina_m", DOUBLE), ("lokacija", STRING), ("cable_layer_id", STRING),
                ("cable_fid", INT), ("strana", STRING), ("napomena", STRING), ("fiberq_uuid", STRING)]
CABLE_FIELDS = [("naziv", STRING), ("tip", STRING), ("duzina_m", DOUBLE), ("slack_m", DOUBLE),
                ("total_len_m", DOUBLE), ("fiberq_uuid", STRING)]
#: A pre-1.0 project: the cable reference under its Serbian names, as
#: core/interchange_fields.LEGACY_FIELD_NAMES records them.
LEGACY_SLACK_FIELDS = [({"cable_layer_id": "kabl_layer_id", "cable_fid": "kabl_fid"}.get(name, name), kind)
                       for name, kind in SLACK_FIELDS]
#: UG1/UG2 and AE1/AE2 share an end, so two slacks land on one point there.
UG = [("UG1", [(0, 0), (100, 0)]), ("UG2", [(100, 0), (200, 0)]), ("UG3", [(300, 0), (400, 50)])]
AE = [("AE1", [(0, 100), (100, 100)]), ("AE2", [(100, 100), (100, 200)])]
POLES = [(0, 100.5), (100, 100)]
MANHOLES = [(0, 0.5), (100, 0), (400, 50)]


class _Bar:
    def __init__(self):
        self.warnings, self.infos = [], []

    def pushWarning(self, title, text):
        self.warnings.append(str(text))

    def pushInfo(self, title, text):
        self.infos.append(str(text))

    def pushCritical(self, title, text):
        self.warnings.append("critical: " + str(text))

    def pushSuccess(self, title, text):
        self.infos.append(str(text))


class _Iface:
    def __init__(self):
        from qgis.gui import QgsMapCanvas
        self.bar = _Bar()
        self.canvas = QgsMapCanvas()

    def messageBar(self):
        return self.bar

    def mapCanvas(self):
        return self.canvas

    def mainWindow(self):
        return None


@pytest.fixture
def project(qgis_app, monkeypatch):
    prj = QgsProject.instance()
    prj.clear()
    dialogs = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: dialogs.append(str(a[-1]))))
    prj.dialogs = dialogs
    yield prj
    for layer in prj.mapLayers().values():
        if layer.isEditable():
            layer.rollBack()
    prj.clear()


@pytest.fixture(autouse=True)
def canvas_not_rendering(qgis_canvas):
    """pytest-qgis's canvas renders every layer added to the project, in a worker thread.

    On QGIS 4.2 a render opening a GeoPackage a test had just written, while
    the test opened it for editing, left the test's own connection unable
    to read the file (35 of 40 tries in the code review). No test here needs
    the canvas to draw.
    """
    qgis_canvas.setRenderFlag(False)
    yield
    qgis_canvas.setRenderFlag(True)


def _memory(geometry, fields, name):
    layer = QgsVectorLayer(f"{geometry}?crs=EPSG:3857", name, "memory")
    layer.dataProvider().addAttributes([QgsField(n, t) for n, t in fields])
    layer.updateFields()
    return layer


def _tables(ug=UG, ae=AE, slack_fields=SLACK_FIELDS):
    tables = [("slacks", _memory("Point", slack_fields, "slacks"))]
    for table, rows in (("ug", ug), ("ae", ae)):
        layer = _memory("LineString", CABLE_FIELDS, table)
        features = []
        for name, points in rows:
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in points]))
            feat["naziv"], feat["tip"], feat["slack_m"], feat["total_len_m"] = name, "Optical", 0.0, 0.0
            features.append(feat)
        assert layer.dataProvider().addFeatures(features)[0]
        tables.append((table, layer))
    for table, points in (("poles", POLES), ("manholes", MANHOLES)):
        layer = _memory("Point", [("tip", STRING)], table)
        features = []
        for x, y in points:
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            features.append(feat)
        assert layer.dataProvider().addFeatures(features)[0]
        tables.append((table, layer))
    return tables


NAMES = {"slacks": "Optical slacks", "ug": "Underground cables", "ae": "Aerial cables",
         "poles": "Poles", "manholes": "Manholes"}
LEGACY_NAMES = {"slacks": "Opticke_rezerve", "ug": "Kablovi_podzemni", "ae": "Kablovi_vazdusni",
                "poles": "Stubovi", "manholes": "OKNA"}


def _load(project, tmp_path, storage, ug=UG, ae=AE, names=NAMES, slack_fields=SLACK_FIELDS):
    """Every layer in one GeoPackage (or in memory), selected cables and all, and a manager."""
    tables = _tables(ug, ae, slack_fields)
    layers = {}
    if storage == "memory":
        for table, layer in tables:
            layer.setName(names[table])
            layers[table] = layer
    else:
        path = str(tmp_path / "project.gpkg")
        for i, (table, layer) in enumerate(tables):
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = table
            if i:
                options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
            written = QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, QgsCoordinateTransformContext(), options)
            assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
        for table, _layer in tables:
            layers[table] = QgsVectorLayer(f"{path}|layername={table}", names[table], "ogr")
            assert layers[table].isValid()
        layers["path"] = path
    project.addMapLayers([layer for key, layer in layers.items() if key != "path"])
    for key in ("ug", "ae"):
        layers[key].selectByIds(sorted(f.id() for f in layers[key].getFeatures()))
    iface = _Iface()
    manager = SlackManager(iface)
    manager.undo_manager = FiberQUndoManager(iface)
    restyled = []

    def restyle(layer):
        # The real restyle's one write: the cable type migration.
        restyled.append(layer.name())
        _migrate_cable_type_values(layer)

    manager.set_cable_style_callback(restyle)
    return layers, manager, iface, restyled


# ---------------------------------------------------------------------------
# The work per batch
# ---------------------------------------------------------------------------

def _sessions(project, tmp_path, storage, cables, names=NAMES, slack_fields=SLACK_FIELDS):
    project.clear()
    street = [(f"UG{i}", [(i * 100.0, 0), (i * 100.0 + 40, 0)]) for i in range(16)]
    layers, manager, _iface, restyled = _load(project, tmp_path / f"{storage}{cables}", storage, ug=street, ae=AE,
                                              names=names, slack_fields=slack_fields)
    layers["ug"].selectByIds(sorted(f.id() for f in layers["ug"].getFeatures())[:cables])
    layers["ae"].removeSelection()
    counts = {}
    real_start, real_commit = QgsVectorLayer.startEditing, QgsVectorLayer.commitChanges

    def start(self, *args):
        counts[(self.name(), "sessions")] = counts.get((self.name(), "sessions"), 0) + 1
        return real_start(self, *args)

    def commit(self, *args):
        counts[(self.name(), "commits")] = counts.get((self.name(), "commits"), 0) + 1
        return real_commit(self, *args)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(QgsVectorLayer, "startEditing", start)
        patch.setattr(QgsVectorLayer, "commitChanges", commit)
        manager.generate_terminal_slack_for_selected()
    assert layers["slacks"].featureCount() == 2 * cables
    return counts, restyled


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_generating_opens_one_session_per_layer_not_two_per_slack(project, tmp_path, storage):
    """The parent opened and committed each layer once per slack: 8 then 32 times here.

    Now the slack layer and the one cable layer touched each get one session
    and one commit, and the cable layer one restyle, for 4 cables or 16.
    """
    (tmp_path / f"{storage}4").mkdir()
    (tmp_path / f"{storage}16").mkdir()
    few, few_restyles = _sessions(project, tmp_path, storage, 4)
    many, many_restyles = _sessions(project, tmp_path, storage, 16)
    assert few == many, (few, many)
    assert few == {("Optical slacks", "sessions"): 1, ("Optical slacks", "commits"): 1,
                   ("Underground cables", "sessions"): 1, ("Underground cables", "commits"): 1}
    assert few_restyles == many_restyles == ["Underground cables"]


@pytest.mark.parametrize("storage", ["memory", "gpkg"])
def test_a_pre_1_0_project_is_generated_in_one_session_too(project, tmp_path, storage):
    """``Opticke_rezerve`` with ``kabl_layer_id`` / ``kabl_fid``, as a pre-1.0 project stores it.

    The batch used to step aside for any slack layer named ``opticke_rezerve*``,
    because ``addons/reserve_hook.py`` could rewrite cables after a slack commit
    there. The hook is retired (WP4 U12), so nothing rides on those commits any
    more, and the parent's 8 sessions for 4 cables become one per layer here too.
    """
    (tmp_path / f"{storage}4").mkdir()
    counts, restyled = _sessions(project, tmp_path, storage, 4, names=LEGACY_NAMES, slack_fields=LEGACY_SLACK_FIELDS)
    assert counts == {("Opticke_rezerve", "sessions"): 1, ("Opticke_rezerve", "commits"): 1,
                      ("Kablovi_podzemni", "sessions"): 1, ("Kablovi_podzemni", "commits"): 1}
    assert restyled == ["Kablovi_podzemni"]


# ---------------------------------------------------------------------------
# The outcome: the loop's, whatever goes wrong
# ---------------------------------------------------------------------------

#: A refused commit names the unsaved feature by its temporary id. QGIS deals
#: those from one counter for the whole session, so the number depends on every
#: feature added before -- and a refused batch has added its own before the loop
#: runs. The message is compared without it.
_TEMPORARY_ID = re.compile(r"feature -\d+")


def _rows(path, table, columns):
    with closing(sqlite3.connect(path)) as con, con:
        return con.execute(f'SELECT fid, {", ".join(columns)} FROM "{table}" ORDER BY fid').fetchall()


def _link_columns(slacks):
    """The slack layer's cable reference pair: ``kabl_*`` on a pre-1.0 project."""
    return cable_link_fields(slacks.fields().names())


def _outcome(project, layers, manager, iface):
    path = layers["path"]
    names = {layers[key].id(): key for key in ("ug", "ae")}
    cables = {(key, f.id()): f["naziv"] for key in ("ug", "ae") for f in layers[key].getFeatures()}
    slacks = {row[0]: (names.get(row[1]), cables.get((names.get(row[1]), row[2])), row[3], row[4], row[5])
              for row in _rows(path, "slacks", [*_link_columns(layers["slacks"]), "strana", "lokacija", "duzina_m"])}
    columns = ["naziv", "slack_m", "total_len_m"]
    totals = {key: [(row[1], row[2], round(row[3] or 0, 9)) for row in _rows(path, key, columns)]
              for key in ("ug", "ae") if "slack_m" in layers[key].fields().names()}
    undo = [(slacks.get(op.feature_id), op.description) for op in manager.undo_manager._undo_stack]
    with closing(sqlite3.connect(path)) as con, con:
        audit = (con.execute("SELECT * FROM cable_audit ORDER BY rowid").fetchall()
                 if con.execute("SELECT 1 FROM sqlite_master WHERE name = 'cable_audit'").fetchone() else None)
        types = con.execute("SELECT fid, tip FROM ug ORDER BY fid").fetchall()
    revisions = [(f["naziv"], f["rev"]) for f in layers["ug"].getFeatures()] if "rev" in layers["ug"].fields().names() else None
    return {"slacks": sorted(slacks.values(), key=repr), "totals": totals, "undo": undo, "revisions": revisions,
            "audit": audit, "types": types,
            "unsaved": {key: layers[key].undoStack().count() for key in ("slacks", "ug", "ae") if layers[key].isEditable()},
            "warnings": [_TEMPORARY_ID.sub("feature <unsaved>", text) for text in iface.bar.warnings],
            "infos": iface.bar.infos, "dialogs": list(project.dialogs),
            "editing": {key: layers[key].isEditable() for key in ("slacks", "ug", "ae")}}


SCENARIOS = {
    "plain": [],
    "one slack per end": ["CREATE UNIQUE INDEX one_per_end ON slacks(cable_layer_id, cable_fid, strana)"],
    "to-ends refused": ["CREATE TRIGGER no_to BEFORE INSERT ON slacks WHEN NEW.strana = 'do' "
                        "BEGIN SELECT RAISE(ABORT, 'TO-end slacks are entered by hand'); END"],
    "every slack refused": ["CREATE TRIGGER no_slacks BEFORE INSERT ON slacks "
                            "BEGIN SELECT RAISE(ABORT, 'locked'); END"],
    "one cable frozen": ["CREATE TRIGGER frozen BEFORE UPDATE ON ug WHEN NEW.naziv = 'UG2' "
                         "AND NEW.slack_m IS NOT OLD.slack_m BEGIN SELECT RAISE(ABORT, 'UG2 is frozen'); END"],
    "at most 30 m of slack": ["CREATE TRIGGER at_most_30 BEFORE UPDATE ON ug WHEN NEW.slack_m > 30 "
                              "BEGIN SELECT RAISE(ABORT, 'at most 30 m of slack'); END"],
    "cable history kept by a trigger": ["CREATE TABLE cable_audit (cable INTEGER, slack REAL)",
                                        "CREATE TRIGGER audit AFTER UPDATE OF slack_m ON ug BEGIN "
                                        "INSERT INTO cable_audit VALUES (NEW.fid, NEW.slack_m); END"],
    "old cable types, migration refused": ["CREATE TRIGGER types_frozen BEFORE UPDATE OF tip ON ug "
                                           "WHEN OLD.tip = 'opticki' BEGIN SELECT RAISE(ABORT, 'types frozen'); END"],
}


def _run(project, tmp_path, scenario, loop, setup=None):
    project.clear()
    project.dialogs.clear()
    legacy = scenario == "legacy slack layer"
    layers, manager, iface, _restyled = _load(project, tmp_path, "gpkg", names=LEGACY_NAMES if legacy else NAMES,
                                              slack_fields=LEGACY_SLACK_FIELDS if legacy else SLACK_FIELDS)
    statements = [sql.format(ug=layers["ug"].id()) for sql in SCENARIOS.get(scenario, [])]
    if statements:
        with closing(sqlite3.connect(layers["path"])) as con, con:
            for sql in statements:
                con.execute(sql)
    kept = setup(layers) if setup else None
    ran = []
    if loop:
        manager._batch_allowed = lambda *args: False
    elif legacy:
        batch = manager._generate_in_one_session
        manager._generate_in_one_session = lambda *args, **kwargs: ran.append(batch(*args, **kwargs)) or ran[-1]
    manager.generate_terminal_slack_for_selected()
    if legacy and not loop:
        # The pre-1.0 schema's batch must run to its end: one that hands back to
        # the loop (answering None) would make loop == batch hold trivially.
        assert ran and ran[-1] is not None, "premise: the batch ran on the pre-1.0 schema: " + repr(ran)
    del kept
    return _outcome(project, layers, manager, iface)


def _a_slack_already_at_ug2s_start(layers):
    """With the unique index, the loop saves every slack before UG2's FROM end and none after."""
    slacks, ug = layers["slacks"], layers["ug"]
    feat = QgsFeature(slacks.fields())
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(100, 0)))
    feat["tip"], feat["duzina_m"], feat["strana"] = "Terminal", 15, "od"
    feat["cable_layer_id"] = ug.id()
    feat["cable_fid"] = next(f.id() for f in ug.getFeatures() if f["naziv"] == "UG2")
    assert slacks.dataProvider().addFeatures([feat])[0]


def _revision_on_every_update(layers):
    """A cable field whose default is applied again on every update: v1.5.0 updated each cable twice."""
    from qgis.core import QgsDefaultValue
    ug = layers["ug"]
    assert ug.dataProvider().addAttributes([QgsField("rev", INT)])
    ug.updateFields()
    ug.setDefaultValueDefinition(ug.fields().indexOf("rev"), QgsDefaultValue('coalesce("rev", 0) + 1', True))


def _slack_layer_filtered(layers):
    """v1.5.0's Undo lookup reads through the filter: it records no slack, or a visible one."""
    assert layers["slacks"].setSubsetString("\"tip\" <> 'Terminal'")


def _underground_typed_opticki(layers):
    ug = layers["ug"]
    tip = ug.fields().indexOf("tip")
    assert ug.dataProvider().changeAttributeValues({f.id(): {tip: "opticki"} for f in ug.getFeatures()})


def _read_only_underground(layers):
    layers["ug"].setReadOnly(True)


def _aerial_without_totals(layers):
    provider = layers["ae"].dataProvider()
    assert provider.deleteAttributes([layers["ae"].fields().indexOf(name) for name in ("slack_m", "total_len_m")])
    layers["ae"].updateFields()


SETUPS = {"one slack per end": _a_slack_already_at_ug2s_start,
          "old cable types, migration refused": _underground_typed_opticki}
CASES = [(name, SETUPS.get(name)) for name in SCENARIOS] + [
    ("filtered slack layer", _slack_layer_filtered),
    ("read-only cable layer", _read_only_underground),
    ("cable layer without totals", _aerial_without_totals),
    ("revision on every update", _revision_on_every_update),
    # A pre-1.0 project: Serbian layer names and the kabl_* reference columns.
    ("legacy slack layer", None),
]


@pytest.mark.parametrize("scenario, setup", CASES, ids=[name for name, _setup in CASES])
def test_the_batch_ends_where_the_per_slack_loop_ends(project, tmp_path, scenario, setup):
    (tmp_path / "loop").mkdir()
    (tmp_path / "batch").mkdir()
    loop = _run(project, tmp_path / "loop", scenario, True, setup)
    batch = _run(project, tmp_path / "batch", scenario, False, setup)
    assert batch == loop


@pytest.mark.skipif(not hasattr(Qgis, "TransactionMode"), reason="transaction modes arrived in QGIS 3.26")
@pytest.mark.parametrize("mode", ["AutomaticGroups", "BufferedGroups"])
def test_a_project_saving_layers_together_keeps_the_per_slack_loop(project, tmp_path, mode):
    """One layer's commit reaches others there, so the batch steps aside and the loop runs."""
    calls = []

    def setup(layers):
        project.setTransactionMode(getattr(Qgis.TransactionMode, mode))

    real = SlackManager._recompute_in_one_session
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(SlackManager, "_recompute_in_one_session",
                      lambda self, *a: calls.append(a) or real(self, *a))
        (tmp_path / "batch").mkdir()
        _run(project, tmp_path / "batch", "plain", False, setup)
    assert calls == []


def test_a_filtered_memory_cable_layer_keeps_the_per_slack_totals(project, tmp_path):
    """Its first total moves a cable out of "slack_m" = 0, and v1.5.0's second recompute does not find it again."""
    totals = {}
    for flow in ("loop", "batch"):
        project.clear()
        layers, manager, _iface, _restyled = _load(project, tmp_path, "memory")
        assert layers["ug"].setSubsetString('"slack_m" = 0')
        layers["ug"].selectByIds(sorted(f.id() for f in layers["ug"].getFeatures()))
        if flow == "loop":
            manager._batch_allowed = lambda *args: False
        manager.generate_terminal_slack_for_selected()
        assert layers["ug"].setSubsetString("")
        totals[flow] = sorted((f["naziv"], f["slack_m"], round(f["total_len_m"], 9)) for f in layers["ug"].getFeatures())
    assert totals["batch"] == totals["loop"]
    assert totals["loop"][0][1] == 20.0, "premise: the loop kept each cable's first total"
