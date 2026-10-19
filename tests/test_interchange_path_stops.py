"""Pass-through elements travel in the shape FiberQ's own dialog stores them.

Unclaimed (WP3 code), found in the v1.6.0 docs review. The project entry
``StuboviPlugin/LatentElements/latent_v1`` comes in two shapes:

* the pass-through dialog's (``dialogs/latent_dialog.py``, the only place a user
  edits it): ``{"cables": {key: {"elements": [{layer_id, fid, naziv,
  latent}]}}}`` -- every element along the cable, in order, marked latent or not;
* the one a v1.5.0 bundle import wrote: ``{"cables": {key: [{layer_id, fid,
  m}]}}``.

The writer read only the second and raised on the first, so a bundle export of
any project edited in the dialog failed outright (measured on 3.44:
``AttributeError: 'str' object has no attribute 'get'``). The dialog read only
the first, so it raised on any cable an import had written. Every interchange
test built the second shape by hand, which is why neither was ever seen.
"""
import json
import sqlite3
from contextlib import closing

import pytest
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

ENTRY = ("StuboviPlugin", "LatentElements/latent_v1")


def _layer(name, geometry, rows):
    layer = QgsVectorLayer(f"{geometry}?crs=EPSG:3857&field=fiberq_uuid:string(64)"
                           "&field=naziv:string&field=od:string&field=do:string", name, "memory")
    assert layer.isValid(), name
    features = []
    for geom, uuid in rows:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geom)
        feature.setAttribute("fiberq_uuid", uuid)
        features.append(feature)
    ok, added = layer.dataProvider().addFeatures(features)
    assert ok
    return layer, [f.id() for f in added]


def _network(project):
    """One cable and three manholes along it, in a project of its own."""
    cables, (cable,) = _layer("Underground cables", "LineString", [
        (QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(300, 0)]), "u-cable")])
    manholes, fids = _layer("Manholes", "Point", [
        (QgsGeometry.fromPointXY(QgsPointXY(x, 0)), f"u-mh-{x}") for x in (50, 150, 250)])
    project.addMapLayers([cables, manholes])
    return cables, cable, manholes, fids


def _stops(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(
            "SELECT cable_uuid, element_uuid, order_index, is_latent FROM fq_path_stop "
            "ORDER BY cable_uuid, order_index").fetchall()


@pytest.fixture
def project(qgis_app):
    prj = QgsProject()
    yield prj
    prj.clear()


def _export(project, layers, path):
    from fiberq.core.interchange_bundle import InterchangeBundleWriter

    result = InterchangeBundleWriter(project).write(str(path), layers=layers)
    assert result.ok, result.errors
    return result


def test_a_project_edited_in_the_dialog_exports_its_pass_through_elements(project, tmp_path):
    """What CablePitstopsDialog._on_save writes. The parent raised here."""
    cables, cable, manholes, (a, b, c) = _network(project)
    project.writeEntry(*ENTRY, json.dumps({"cables": {f"{cables.id()}:{cable}": {"elements": [
        {"layer_id": manholes.id(), "fid": a, "naziv": "MH-50", "latent": True},
        {"layer_id": manholes.id(), "fid": b, "naziv": "MH-150", "latent": False},
        {"layer_id": manholes.id(), "fid": c, "naziv": "MH-250", "latent": True},
    ]}}}))
    path = tmp_path / "dialog.gpkg"
    result = _export(project, [cables, manholes], path)

    assert result.sidecar_rows["fq_path_stop"] == 3
    # In the dialog's order, each with its own mark (spec 6.4: is_latent = 1
    # for an element the cable merely passes through).
    assert _stops(path) == [("u-cable", "u-mh-50", 0, 1), ("u-cable", "u-mh-150", 1, 0),
                            ("u-cable", "u-mh-250", 2, 1)]


def test_the_shape_a_v150_import_wrote_still_exports(project, tmp_path):
    """Characterisation: ordered by ``m``, every element latent, as before."""
    cables, cable, manholes, (a, b, _c) = _network(project)
    project.writeEntry(*ENTRY, json.dumps({"cables": {f"{cables.id()}:{cable}": [
        {"layer_id": manholes.id(), "fid": b, "m": 150.0},
        {"layer_id": manholes.id(), "fid": a, "m": 50.0},
    ]}}))
    path = tmp_path / "list.gpkg"
    _export(project, [cables, manholes], path)
    assert _stops(path) == [("u-cable", "u-mh-50", 0, 1), ("u-cable", "u-mh-150", 1, 1)]


def test_both_shapes_in_one_project(project, tmp_path):
    """The dialog rewrites one cable at a time, so a project a v1.5.0 import
    touched and a user then edited holds both shapes at once."""
    cables, cable, manholes, (a, b, c) = _network(project)
    other, (second,) = _layer("Aerial cables", "LineString", [
        (QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(300, 10)]), "u-aerial")])
    project.addMapLayer(other)
    project.writeEntry(*ENTRY, json.dumps({"cables": {
        f"{cables.id()}:{cable}": {"elements": [
            {"layer_id": manholes.id(), "fid": c, "naziv": "", "latent": False}]},
        f"{other.id()}:{second}": [{"layer_id": manholes.id(), "fid": a, "m": 5.0}],
    }}))
    path = tmp_path / "both.gpkg"
    _export(project, [cables, other, manholes], path)
    assert sorted(_stops(path)) == [("u-aerial", "u-mh-50", 0, 1), ("u-cable", "u-mh-250", 0, 0)]


# ---------------------------------------------------------------------------
# The dialog, on a cable a v1.5.0 import wrote
# ---------------------------------------------------------------------------

class _Bar:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _Iface:
    def __init__(self):
        self.bar = _Bar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


@pytest.fixture
def plugin(qgis_app):
    """A FiberQPlugin with the managers the list reads (as test_latent_elements)."""
    from fiberq.core.cable_manager import CableManager
    from fiberq.core.data_manager import DataManager
    from fiberq.core.relations_manager import RelationsManager
    from fiberq.main_plugin import FiberQPlugin

    QgsProject.instance().clear()
    obj = FiberQPlugin.__new__(FiberQPlugin)
    obj.iface = _Iface()
    obj.data_manager = DataManager(obj.iface, obj)
    obj.relations_manager = RelationsManager(obj.data_manager)
    obj.cable_manager = CableManager(obj.iface, None, obj.data_manager, None)
    yield obj
    QgsProject.instance().clear()


def test_the_dialog_opens_on_a_cable_an_old_import_wrote(plugin):
    """The parent raised ``'list' object has no attribute 'get'`` here."""
    from fiberq.dialogs.latent_dialog import LatentElementsDialog

    project = QgsProject.instance()
    cables, cable, manholes, (a, b, _c) = _network(project)
    project.writeEntry(*ENTRY, json.dumps({"cables": {f"{cables.id()}:{cable}": [
        {"layer_id": manholes.id(), "fid": a, "m": 50.0},
        {"layer_id": manholes.id(), "fid": b, "m": 150.0},
    ]}}))
    dialog = LatentElementsDialog(plugin)
    rows = {dialog.tbl.item(r, 1).text(): (dialog.tbl.item(r, 3).text(), dialog.tbl.item(r, 4).text())
            for r in range(dialog.tbl.rowCount())}
    # Two latent elements, none marked otherwise.
    assert rows[str(cable)] == ("2", "0")


def _closures_and_manholes(project):
    """A cable, a closure on it, a closure 30 m off it, and a manhole on it.

    Only the first is a candidate in the editor: candidates come from the placing
    element layers, within 5 map units of the line, and manholes are never one.
    """
    cables, (cable,) = _layer("Underground cables", "LineString", [
        (QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(300, 0)]), "u-cable")])
    closures, (near, far) = _layer("Joint Closures", "Point", [
        (QgsGeometry.fromPointXY(QgsPointXY(50, 1)), "u-jc-near"),
        (QgsGeometry.fromPointXY(QgsPointXY(150, 30)), "u-jc-far")])
    manholes, (mh,) = _layer("Manholes", "Point", [
        (QgsGeometry.fromPointXY(QgsPointXY(250, 0)), "u-mh")])
    project.addMapLayers([cables, closures, manholes])
    return cables, cable, closures, near, far, manholes, mh


def test_saving_the_editor_keeps_what_it_does_not_list(plugin):
    """The editor lists only nearby closures and the like. Save rewrote the record
    from that list, so one Save deleted every stop it does not list -- imported
    stops on manholes, poles or anything outside the search distance -- and
    every key an element carried beyond the four the editor writes."""
    from fiberq.core.interchange import latent_records
    from fiberq.dialogs.latent_dialog import CablePitstopsDialog

    project = QgsProject.instance()
    cables, cable, closures, near, far, manholes, mh = _closures_and_manholes(project)
    key = f"{cables.id()}:{cable}"
    store = {"cables": {key: {"elements": [
        {"layer_id": closures.id(), "fid": near, "naziv": "", "latent": True,
         "extra": {"vendor_ref": "v-1"}},
        {"layer_id": manholes.id(), "fid": mh, "naziv": "", "latent": True},
        {"layer_id": closures.id(), "fid": far, "naziv": "", "latent": False},
    ]}}}
    project.writeEntry(*ENTRY, json.dumps(store))
    feature = next(cables.getFeatures())
    editor = CablePitstopsDialog(plugin, cables, feature, {"layer_id": cables.id(), "fid": cable},
                                 store)
    assert [row["fid"] for row in editor.elements] == [near], "premise: one candidate"
    editor._on_save()

    saved = latent_records(json.loads(project.readEntry(*ENTRY, "")[0]))[key]
    assert [(e["layer_id"], e["fid"], e["latent"]) for e in saved] == [
        (closures.id(), near, True), (manholes.id(), mh, True), (closures.id(), far, False)]
    assert saved[0]["extra"] == {"vendor_ref": "v-1"}


def test_opening_the_list_reads_the_store_once(plugin, monkeypatch):
    """WP4 PF-2 made the list linear; asking latent_records for the whole store
    once per row made it quadratic again (30 s at 5,048 records, measured)."""
    from fiberq.dialogs import latent_dialog

    project = QgsProject.instance()
    cables, cable, closures, near, far, manholes, mh = _closures_and_manholes(project)
    project.writeEntry(*ENTRY, json.dumps({"cables": {f"{cables.id()}:{cable}": {"elements": [
        {"layer_id": closures.id(), "fid": near, "naziv": "", "latent": True}]}}}))
    calls = []
    real = latent_dialog.latent_records
    monkeypatch.setattr(latent_dialog, "latent_records",
                        lambda data: calls.append(1) or real(data))
    latent_dialog.LatentElementsDialog(plugin)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Import: the dialog's shape, and an import adds instead of replacing
# ---------------------------------------------------------------------------

def _source(tmp_path, name="source.gpkg", stop_rows=(), alter=()):
    """A bundle FiberQ wrote: two cables, three manholes, one record per cable.

    ``alter``/``stop_rows`` are SQL run on it afterwards, as another tool would.
    """
    project = QgsProject()
    cables, (x,) = _layer("Underground cables", "LineString", [
        (QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(300, 0)]), "u-cable-x")])
    aerial, (y,) = _layer("Aerial cables", "LineString", [
        (QgsGeometry.fromPolylineXY([QgsPointXY(0, 50), QgsPointXY(300, 50)]), "u-cable-y")])
    manholes, (m1, m2, m3) = _layer("Manholes", "Point", [
        (QgsGeometry.fromPointXY(QgsPointXY(px, 0)), f"u-mh-{px}") for px in (50, 150, 250)])
    project.addMapLayers([cables, aerial, manholes])
    project.writeEntry(*ENTRY, json.dumps({"cables": {
        f"{cables.id()}:{x}": {"elements": [
            {"layer_id": manholes.id(), "fid": m1, "naziv": "", "latent": True},
            {"layer_id": manholes.id(), "fid": m2, "naziv": "", "latent": False}]},
        f"{aerial.id()}:{y}": {"elements": [
            {"layer_id": manholes.id(), "fid": m3, "naziv": "", "latent": True}]},
    }}))
    path = str(tmp_path / name)
    _export(project, [cables, aerial, manholes], path)
    project.clear()
    with closing(sqlite3.connect(path)) as conn:
        for statement in list(alter) + list(stop_rows):
            conn.execute(statement)
        conn.commit()
    return path


def _import(project, path):
    from fiberq.core.interchange_import import InterchangeBundleReader

    result = InterchangeBundleReader(project).read(path)
    assert result.ok, result.errors
    return result


def _records(project):
    from fiberq.core.interchange import latent_records

    raw = project.readEntry(*ENTRY, "")[0]
    return latent_records(json.loads(raw)) if raw else {}


def _layer_named(project, name):
    return next(lyr for lyr in project.mapLayers().values() if lyr.name() == name)


def _again(project, tmp_path, name="again.gpkg"):
    path = tmp_path / name
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    _export(project, layers, path)
    return _stops(path)


def test_an_import_writes_the_shape_the_dialog_reads(project, tmp_path):
    _import(project, _source(tmp_path))
    raw = json.loads(project.readEntry(*ENTRY, "")[0])
    assert all(isinstance(record, dict) and "elements" in record
               for record in raw["cables"].values()), raw
    # ... in order, with each mark, and it goes out again as it came in.
    assert _again(project, tmp_path) == [
        ("u-cable-x", "u-mh-50", 0, 1), ("u-cable-x", "u-mh-150", 1, 0),
        ("u-cable-y", "u-mh-250", 0, 1)]


def test_an_import_keeps_the_projects_own_pass_through_elements(project, tmp_path):
    """It used to write the bundle's entry over the project's own."""
    bundle = _source(tmp_path)
    _import(project, bundle)
    cables = _layer_named(project, "Underground cables")
    manholes = _layer_named(project, "Manholes")
    key = next(k for k in _records(project) if k.startswith(cables.id()))
    mine = {"elements": [{"layer_id": manholes.id(), "fid": fid, "naziv": "", "latent": True}
                         for fid in sorted(f.id() for f in manholes.getFeatures())]}
    entry = json.loads(project.readEntry(*ENTRY, "")[0])
    entry["cables"][key] = mine
    project.writeEntry(*ENTRY, json.dumps(entry))

    result = _import(project, bundle)
    assert _records(project)[key] == [dict(e) for e in mine["elements"]]
    assert any("already had pass-through elements" in w for w in result.warnings), result.warnings


def test_reimporting_a_projects_own_bundle_changes_nothing_and_says_nothing(project, tmp_path):
    bundle = _source(tmp_path)
    _import(project, bundle)
    before = project.readEntry(*ENTRY, "")[0]
    result = _import(project, bundle)
    assert project.readEntry(*ENTRY, "")[0] == before
    assert not [w for w in result.warnings if "pass-through" in w], result.warnings


def test_a_stop_on_an_element_fiberq_does_not_draw_is_kept(project, tmp_path):
    bundle = _source(tmp_path, stop_rows=[
        "INSERT INTO fq_path_stop VALUES ('u-cable-x', 'u-splitter-1', 5, 1)"])
    result = _import(project, bundle)
    assert any("kept and written out again" in w for w in result.warnings), result.warnings
    assert ("u-cable-x", "u-splitter-1", 5, 1) in _again(project, tmp_path)


def test_a_stop_whose_cable_is_not_in_the_project_is_kept(project, tmp_path):
    bundle = _source(tmp_path, stop_rows=[
        "INSERT INTO fq_path_stop VALUES ('u-cable-elsewhere', 'u-mh-50', 0, 0)"])
    _import(project, bundle)
    assert ("u-cable-elsewhere", "u-mh-50", 0, 0) in _again(project, tmp_path)


def test_a_column_a_newer_version_adds_to_path_stops_travels_on(project, tmp_path):
    bundle = _source(tmp_path, alter=[
        "ALTER TABLE fq_path_stop ADD COLUMN distance_m REAL",
        "UPDATE fq_path_stop SET distance_m = 12.5 WHERE element_uuid = 'u-mh-50'"])
    _import(project, bundle)
    path = tmp_path / "again.gpkg"
    layers = [lyr for lyr in project.mapLayers().values() if isinstance(lyr, QgsVectorLayer)]
    _export(project, layers, path)
    with closing(sqlite3.connect(str(path))) as conn:
        rows = conn.execute("SELECT element_uuid, distance_m FROM fq_path_stop "
                            "WHERE cable_uuid = 'u-cable-x' ORDER BY order_index").fetchall()
    assert rows == [("u-mh-50", 12.5), ("u-mh-150", None)]


def test_a_stop_on_a_closure_the_project_already_has_resolves(project, tmp_path):
    """The index covered only the layers the import wrote into."""
    only_cables = QgsProject()
    cables, (x,) = _layer("Underground cables", "LineString", [
        (QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(300, 0)]), "u-cable-x")])
    only_cables.addMapLayer(cables)
    path = str(tmp_path / "cables-only.gpkg")
    _export(only_cables, [cables], path)
    only_cables.clear()
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("INSERT INTO fq_path_stop VALUES ('u-cable-x', 'u-jc-mine', 0, 1)")
        conn.commit()

    closures, (mine,) = _layer("Joint Closures", "Point", [
        (QgsGeometry.fromPointXY(QgsPointXY(100, 0)), "u-jc-mine")])
    project.addMapLayer(closures)
    _import(project, path)
    (elements,) = _records(project).values()
    assert [(e.get("layer_id"), e.get("fid")) for e in elements] == [(closures.id(), mine)]
