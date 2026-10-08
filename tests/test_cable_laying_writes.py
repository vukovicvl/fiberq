"""Lay cable did nothing at all on a shapefile route layer, and said nothing.

WP4 4.2 item R8. Branch ``fix/wp4-write-paths``.

``CableManager.lay_cable`` searched the route with::

    line = geom.asPolyline()
    if not line:
        multi = geom.asMultiPolyline()      # unreachable
        line = multi[0]

``asPolyline()`` raises ``TypeError`` on **any** multipart geometry, so the
fallback below it could never run and the ``TypeError`` left the method --
straight into ``FiberQPlugin.lay_cable``'s ``except Exception as e:
logger.debug(...)``, which at the default log level writes nothing anywhere.

Measured through the real entry point: the user fills in the whole cable picker,
clicks OK, and gets **no cable, no dialog, no message bar and no log line**.

And this was not an exotic shape. An ESRI Shapefile line layer reads back as
MultiLineString for every feature, single-part or not, because the format has no
single/multi distinction and OGR declares the layer from the format rather than
the content (measured; see ``tests/test_multipart_routes.py``). A shapefile is
the ordinary way to bring an existing network into QGIS, so this was every
shapefile Route layer.

Three more defects in the same path, all measured:

* ``startEditing``, ``addFeature`` and ``commitChanges`` all had their results
  discarded, so a GeoPackage that refuses the insert still produced "Cable has
  been laid along the route!" with zero rows on disk.
* ``startEditing()`` was unguarded, so laying a cable committed whatever else
  the user had unsaved on the cable layer.
* ``utils/routing.py`` turned every exception in its path finding into "no path
  found", and the caller then told the user their closures were "not at the ends
  of the same route or connected routes" -- blaming their data for the plugin's
  own failure. Those handlers still answer "no path", deliberately: the caller's
  ``or`` runs a coarser feature-level search when the fine one comes back
  falsy, and raising would skip that rescue. What changed is that the reason is
  recorded rather than discarded.

Five of the seven tests below go red against a tree with only this fix reverted.
The two that do not are marked **characterisation**: a single-part route and a
single-part graph, which always worked and must keep working.
"""
import sqlite3

import pytest
from qgis.core import (
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
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from fiberq.core.cable_manager import CableManager
from fiberq.utils.routing import build_network_graph

PICKED = {
    "vrsta": "podzemni", "tip": "Distribucioni", "podtip": "Backbone",
    "color_code": "", "broj_cevcica": 1, "broj_vlakana": 12,
    "tip_kabla": "", "vrsta_vlakana": "", "vrsta_omotaca": "",
    "vrsta_armature": "", "talasno_podrucje": "", "naziv": "C-new",
    "slabljenje_dbkm": 0.0, "hrom_disp_ps_nmxkm": 0.0, "stanje_kabla": "",
    "cable_laying": "underground", "vrsta_mreze": "", "godina_ugradnje": 2026,
    "konstr_vlakna_u_cevcicama": 0, "konstr_sa_uzlepljenim_elementom": 0,
    "konstr_punjeni_kabl": 0, "konstr_sa_arm_vlaknima": 0,
    "konstr_bez_metalnih": 0, "fibers_per_tube": 12, "total_fibers": 12,
    "color_standard": "",
}


class FakeBar:
    def __init__(self):
        self.messages = []

    def pushWarning(self, *a):
        self.messages.append(str(a[-1]) if a else "")

    def pushInfo(self, *a):
        self.messages.append(str(a[-1]) if a else "")

    def pushSuccess(self, *a):
        self.messages.append(str(a[-1]) if a else "")

    def pushCritical(self, *a):
        self.messages.append(str(a[-1]) if a else "")


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None

    def mapCanvas(self):
        return self

    def mapUnitsPerPixel(self):
        return 1.0


@pytest.fixture
def said(monkeypatch):
    """Every modal ``lay_cable`` would have shown."""
    collected = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: collected.append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: collected.append(str(a[-1]))))
    return collected


@pytest.fixture
def picker(monkeypatch):
    class FakePicker:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        @staticmethod
        def values():
            return dict(PICKED)

    import fiberq.dialogs.cable_dialog as cable_dialog
    monkeypatch.setattr(cable_dialog, "CablePickerDialog", FakePicker)
    return FakePicker


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


def _cables_layer(project):
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Kablovi_podzemni", "memory")
    layer.dataProvider().addAttributes([
        QgsField("naziv", QVariant.String),
        QgsField("tip", QVariant.String),
        QgsField("duzina_m", QVariant.Double),
        QgsField("slack_m", QVariant.Double),
        QgsField("total_len_m", QVariant.Double),
    ])
    layer.updateFields()
    project.addMapLayer(layer)
    return layer


def _routes_and_poles(project, route_wkts, declared="LineString"):
    route = QgsVectorLayer(f"{declared}?crs=EPSG:3857", "Route", "memory")
    route.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    route.updateFields()
    for wkt in route_wkts:
        feature = QgsFeature(route.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        assert route.dataProvider().addFeatures([feature])[0]
    project.addMapLayer(route)

    poles = QgsVectorLayer("Point?crs=EPSG:3857", "Poles", "memory")
    poles.dataProvider().addAttributes([QgsField("tip", QVariant.String)])
    poles.updateFields()
    for x, tip in ((0, "A"), (20, "B")):
        p = QgsFeature(poles.fields())
        p.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, 0)))
        p["tip"] = tip
        assert poles.dataProvider().addFeatures([p])[0]
    project.addMapLayer(poles)
    poles.selectByIds([f.id() for f in poles.getFeatures()])
    return route, poles


def _manager(iface=None):
    manager = CableManager(iface or FakeIface())
    manager.selected_cable_type = "Distribucioni"
    manager.selected_cable_subtype = "Backbone"
    return manager


# ---------------------------------------------------------------------------
# the silent no-op
# ---------------------------------------------------------------------------

def test_a_cable_is_laid_along_a_multipart_route(project, picker, said):
    """**The one that matters.** Before the fix this did nothing at all, with no
    message of any kind -- the shape a shapefile Route layer always has."""
    cables = _cables_layer(project)
    _routes_and_poles(project, ["MultiLineString ((0 0, 10 0, 20 0))"],
                      declared="MultiLineString")

    _manager().lay_cable()

    assert cables.featureCount() == 1, (
        f"no cable was laid on a multipart route: {cables.featureCount()} cables, "
        f"messages {said}")
    assert any("laid" in text for text in said), said


def test_a_cable_can_be_laid_along_the_second_part_of_a_route(project, picker, said):
    """The old code took ``multi[0]`` even where it was reachable, so a cable
    could only ever be found along the first piece of a route."""
    cables = _cables_layer(project)
    _routes_and_poles(
        project,
        ["MultiLineString ((100 100, 110 100),(0 0, 10 0, 20 0))"],
        declared="MultiLineString")

    _manager().lay_cable()

    assert cables.featureCount() == 1, (
        f"the cable was only looked for along part 0: {said}")


def test_a_cable_on_a_plain_route_still_works(project, picker, said):
    """Characterisation, not proof: single-part routes always worked and must
    keep working. Passes against the pre-fix code."""
    cables = _cables_layer(project)
    _routes_and_poles(project, ["LineString (0 0, 10 0, 20 0)"])

    _manager().lay_cable()

    assert cables.featureCount() == 1, said


# ---------------------------------------------------------------------------
# the discarded writes
# ---------------------------------------------------------------------------

def _gpkg_cables(project, tmp_path):
    """A cable layer on disk, so a trigger can refuse the insert."""
    path = str(tmp_path / "cables.gpkg")
    mem = QgsVectorLayer("LineString?crs=EPSG:3857", "Kablovi_podzemni", "memory")
    mem.dataProvider().addAttributes([
        QgsField("naziv", QVariant.String),
        QgsField("tip", QVariant.String),
        QgsField("duzina_m", QVariant.Double),
        QgsField("slack_m", QVariant.Double),
        QgsField("total_len_m", QVariant.Double),
    ])
    mem.updateFields()
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Kablovi_podzemni"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem, path, QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    con = sqlite3.connect(path)
    con.execute('''CREATE TRIGGER no_insert BEFORE INSERT ON "Kablovi_podzemni"
                   BEGIN SELECT RAISE(ABORT, 'FiberQ test: inserts blocked'); END;''')
    con.commit()
    con.close()
    layer = QgsVectorLayer(f"{path}|layername=Kablovi_podzemni", "Kablovi_podzemni", "ogr")
    assert layer.isValid()
    project.addMapLayer(layer)
    return layer, path


def _rows(path):
    con = sqlite3.connect(path)
    try:
        return con.execute('SELECT COUNT(*) FROM "Kablovi_podzemni"').fetchone()[0]
    finally:
        con.close()


def test_a_refused_insert_does_not_claim_the_cable_was_laid(
        project, picker, said, tmp_path):
    """Measured: "Cable has been laid along the route!" with zero rows on disk."""
    _cables, path = _gpkg_cables(project, tmp_path)
    _routes_and_poles(project, ["LineString (0 0, 10 0, 20 0)"])

    iface = FakeIface()
    _manager(iface).lay_cable()

    assert _rows(path) == 0, "nothing should have reached the file"
    assert not any("laid" in text for text in said), (
        f"a refused insert was reported as laid: {said}")
    assert iface.bar.messages, "nothing was said about the refusal"


def test_laying_a_cable_does_not_save_the_user_s_other_unsaved_work(
        project, picker, said, tmp_path):
    cables, path = _gpkg_cables(project, tmp_path)
    con = sqlite3.connect(path)
    con.execute("DROP TRIGGER no_insert")
    con.commit()
    con.close()

    cables.startEditing()
    theirs = QgsFeature(cables.fields())
    theirs.setGeometry(QgsGeometry.fromWkt("LineString (500 500, 510 500)"))
    theirs.setAttribute("naziv", "the user's unsaved cable")
    assert cables.addFeature(theirs)

    _routes_and_poles(project, ["LineString (0 0, 10 0, 20 0)"])
    _manager().lay_cable()

    con = sqlite3.connect(path)
    try:
        names = [str(r[0]) for r in con.execute('SELECT naziv FROM "Kablovi_podzemni"')]
    finally:
        con.close()
    assert "the user's unsaved cable" not in names, (
        f"laying a cable committed the user's own unsaved work: {names}")
    assert cables.isEditable(), "the user's edit session was closed for them"
    assert any("not saved yet" in text for text in said), (
        f"the user was not told the cable is only in the layer: {said}")


# ---------------------------------------------------------------------------
# the routing graph
# ---------------------------------------------------------------------------

def test_the_network_graph_reads_a_multipart_route(project):
    """``build_network_graph`` held the same dead fallback, so the graph build
    died on the first multipart route and every path search above it could only
    ever answer "no path found"."""
    route = QgsVectorLayer("MultiLineString?crs=EPSG:3857", "Route", "memory")
    feature = QgsFeature(route.fields())
    feature.setGeometry(QgsGeometry.fromWkt("MultiLineString ((0 0, 10 0),(10 0, 20 0))"))
    assert route.dataProvider().addFeatures([feature])[0]

    key_to_point, segments = build_network_graph(route, 0.1)

    assert segments, "a multipart route produced no graph at all"
    assert len(key_to_point) == 3, (
        f"expected the three distinct vertices of the two parts: {key_to_point}")


def test_the_network_graph_still_reads_a_plain_route(project):
    """Characterisation, as above."""
    route = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    feature = QgsFeature(route.fields())
    feature.setGeometry(QgsGeometry.fromWkt("LineString (0 0, 10 0, 20 0)"))
    assert route.dataProvider().addFeatures([feature])[0]

    key_to_point, segments = build_network_graph(route, 0.1)

    assert len(segments) == 2
    assert len(key_to_point) == 3
