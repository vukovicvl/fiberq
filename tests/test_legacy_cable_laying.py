"""Laying a cable on a pre-1.0 layer does not split its installation-type column.

WP4 FU-2c, item U4. Unclaimed: an ordinary bug fix, shipping in v1.6.0.

A cable layer made before the English field rename calls the installation type
``polaganje_kabla``. ``lay_cable`` tested for the column by its modern name
only::

    if cables_layer.fields().indexFromName(fname) == -1:
        to_add.append(QgsField(fname, ftype))

so it found nothing, **added a second column** called ``cable_laying``, and
wrote the new cable's installation type there. The layer was left with two
columns meaning the same thing, each holding half the cables' values -- and the
user, looking at the attribute table they have always used, saw their new
cable's Installation type blank.

The damage did not stop at the project. Both names map to the one canonical
``installation_type``, so the bundle exporter planned a destination for each:

    fields.append(field)                                   # answers False
    plan.append((src, fields.count() - 1, canonical))      # the WRONG index

``QgsFields.append`` refuses a duplicate name and answers False, leaving
``count()`` unchanged (measured on 3.44.15 and 4.0.3), so ``count() - 1``
pointed at the **previously added** field. The duplicate therefore stole the
destination of whichever column happened to come just before it, and what that
destroyed depended on the layer's column order. Both outcomes were measured:

* ``… duzina_m, fiberq_uuid, cable_laying`` -- the duplicate steals
  ``fiberq_uuid``. Every exported cable lost its identity: one came out
  ``NULL``, the next came out with the literal string ``underground`` as its
  uuid. That is the one column the whole format is keyed on -- the importer
  matches on it and the relations travel by it -- so the bundle cannot be
  re-imported at all.
* ``… fiberq_uuid, duzina_m, cable_laying`` -- the duplicate steals
  ``length_m``. The text value is then written into a Double column, the memory
  provider rejects that whole feature, ``addFeatures`` answers **True** anyway,
  and the cable simply is not in the bundle. The writer reported
  ``ok=True, errors=[]``. The surviving cable's length was ``NULL``, because the
  other cable's empty laying column had overwritten it.

So the same defect either forges the identities or loses a cable, and in both
cases it says the export succeeded.

Nothing on disk is migrated. Renaming a user's column would rewrite their data
and break every expression, label and form that names it (the plan rules
FU-2e out for exactly that reason), so a project already split is repaired at
the point it is read: the exporter merges the two columns, and the importer
writes back into whichever one the layer actually has.

``lay_cable`` always shows ``CablePickerDialog``, so these tests replace that
one class and let the rest of the function run as written.
"""
import os

import pytest
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from fiberq.core import interchange_fields as fm
from fiberq.core.cable_manager import CableManager
from fiberq.models.schema import IDENTITY_FIELD

LEGACY_LAYING = "polaganje_kabla"
MODERN_LAYING = "cable_laying"

#: Every key ``lay_cable`` reads off the picker dialog.
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


class FakeIface:
    def messageBar(self):
        return self

    def pushWarning(self, *a):
        pass

    def pushInfo(self, *a):
        pass

    def mainWindow(self):
        return None

    def mapCanvas(self):
        return self

    def mapUnitsPerPixel(self):
        return 1.0


@pytest.fixture(autouse=True)
def quiet_dialogs(monkeypatch):
    """``lay_cable`` ends with a modal, which hangs an offscreen run."""
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))


@pytest.fixture
def picker(monkeypatch):
    """Replace the one modal in ``lay_cable``; everything else is real code."""
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


def _legacy_cable_layer(project, extra=()):
    """A pre-1.0 underground cable layer: polaganje_kabla, no cable_laying.

    ``fiberq_uuid`` is deliberately placed AFTER the laying column, because
    that is the order the real defect needs: the exporter's shift wrote into
    whatever field preceded the duplicate.
    """
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Kablovi_podzemni", "memory")
    attrs = [
        QgsField("naziv", QVariant.String),
        QgsField("tip", QVariant.String),
        QgsField(LEGACY_LAYING, QVariant.String),
        QgsField(IDENTITY_FIELD, QVariant.String),
        QgsField("duzina_m", QVariant.Double),
    ]
    attrs.extend(QgsField(name, QVariant.String) for name in extra)
    layer.dataProvider().addAttributes(attrs)
    layer.updateFields()
    project.addMapLayer(layer)
    return layer


def _add_cable(layer, uuid, laying_field, laying_value, name="C1"):
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(0, 0), QgsPointXY(50, 0)]))
    feat["naziv"] = name
    feat["tip"] = "Distribucioni"
    # A real length, so a test can tell "never set" from "overwritten with
    # NULL by the stolen destination".
    feat["duzina_m"] = 50.0
    feat[IDENTITY_FIELD] = uuid
    if laying_field:
        feat[laying_field] = laying_value
    layer.startEditing()
    assert layer.addFeature(feat)
    assert layer.commitChanges()
    return feat


def _route_and_two_poles(project):
    """A route with two poles sitting exactly on two of its vertices.

    That keeps ``lay_cable`` on its direct route-matching path, so the test
    never reaches the routing engine or needs a path callback.
    """
    route = QgsVectorLayer("LineString?crs=EPSG:3857", "Route", "memory")
    route.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    route.updateFields()
    feat = QgsFeature(route.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY(
        [QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(20, 0)]))
    route.startEditing()
    route.addFeature(feat)
    route.commitChanges()
    project.addMapLayer(route)

    poles = QgsVectorLayer("Point?crs=EPSG:3857", "Poles", "memory")
    poles.dataProvider().addAttributes([QgsField("tip", QVariant.String)])
    poles.updateFields()
    ids = []
    for x in (0, 20):
        p = QgsFeature(poles.fields())
        p.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, 0)))
        p["tip"] = "A"
        poles.startEditing()
        poles.addFeature(p)
        poles.commitChanges()
    project.addMapLayer(poles)
    ids = [f.id() for f in poles.getFeatures()]
    poles.selectByIds(ids)
    return route, poles


# ---------------------------------------------------------------------------
# lay_cable
# ---------------------------------------------------------------------------

def test_laying_on_an_old_layer_adds_no_second_column(project, picker):
    """The headline: v1.5.0 grew a ``cable_laying`` column here."""
    cables = _legacy_cable_layer(project)
    _route_and_two_poles(project)
    manager = CableManager(FakeIface())
    manager.selected_cable_type = "Distribucioni"
    manager.selected_cable_subtype = "Backbone"

    manager.lay_cable()

    names = cables.fields().names()
    assert MODERN_LAYING not in names, f"a second laying column appeared: {names}"
    assert LEGACY_LAYING in names


def test_the_new_cable_gets_its_installation_type_in_the_old_column(project, picker):
    """And it is not blank, which is what the user actually noticed."""
    cables = _legacy_cable_layer(project)
    _route_and_two_poles(project)
    manager = CableManager(FakeIface())
    manager.selected_cable_type = "Distribucioni"
    manager.selected_cable_subtype = "Backbone"

    manager.lay_cable()

    laid = [f for f in cables.getFeatures()]
    assert len(laid) == 1
    assert laid[0][LEGACY_LAYING] == "underground"


def test_a_modern_layer_is_untouched_by_the_fix(project, picker):
    cables = QgsVectorLayer("LineString?crs=EPSG:3857", "Kablovi_podzemni", "memory")
    cables.dataProvider().addAttributes([
        QgsField("naziv", QVariant.String),
        QgsField(MODERN_LAYING, QVariant.String),
        QgsField(IDENTITY_FIELD, QVariant.String),
    ])
    cables.updateFields()
    project.addMapLayer(cables)
    _route_and_two_poles(project)
    manager = CableManager(FakeIface())
    manager.selected_cable_type = "Distribucioni"
    manager.selected_cable_subtype = "Backbone"

    manager.lay_cable()

    assert LEGACY_LAYING not in cables.fields().names()
    laid = [f for f in cables.getFeatures()]
    assert len(laid) == 1
    assert laid[0][MODERN_LAYING] == "underground"


# ---------------------------------------------------------------------------
# The exporter: a layer the old bug already split
# ---------------------------------------------------------------------------

def _export(project, tmp_path, layer):
    """Export one layer as a bundle and return the written rows."""
    import sqlite3

    from fiberq.core.interchange_bundle import InterchangeBundleWriter
    out = os.path.join(str(tmp_path), "bundle.gpkg")
    result = InterchangeBundleWriter(project).write(out, layers=[layer])
    assert result.ok, result.errors
    rows = []
    with sqlite3.connect(out) as conn:
        conn.row_factory = sqlite3.Row
        table = conn.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
        ).fetchone()[0]
        for row in conn.execute(f'SELECT * FROM "{table}"'):
            rows.append(dict(row))
    return rows


def test_a_split_layer_keeps_every_uuid_through_the_exporter(project, tmp_path):
    """The one the whole format is keyed on.

    Before the fix the cable's installation type landed in ``fiberq_uuid``.
    """
    cables = _legacy_cable_layer(project, extra=(MODERN_LAYING,))
    _add_cable(cables, "11111111-1111-4111-8111-111111111111",
               LEGACY_LAYING, "Podzemno", name="old")
    _add_cable(cables, "22222222-2222-4222-8222-222222222222",
               MODERN_LAYING, "underground", name="new")

    rows = _export(project, tmp_path, cables)

    assert len(rows) == 2
    identities = {r[IDENTITY_FIELD] for r in rows}
    assert identities == {"11111111-1111-4111-8111-111111111111",
                          "22222222-2222-4222-8222-222222222222"}, (
        f"the uuids were overwritten: {identities}")


def test_a_split_layer_loses_no_cable_through_the_exporter(project, tmp_path):
    """The column order where the duplicate steals a numeric destination.

    At HEAD this wrote the text "underground" into ``length_m``; the provider
    rejected the feature, ``addFeatures`` answered True, and the export
    reported success with one of the two cables missing.
    """
    cables = _legacy_cable_layer(project, extra=(MODERN_LAYING,))
    _add_cable(cables, "77777777-7777-4777-8777-777777777777",
               LEGACY_LAYING, "Podzemno", name="old")
    _add_cable(cables, "88888888-8888-4888-8888-888888888888",
               MODERN_LAYING, "underground", name="new")

    rows = _export(project, tmp_path, cables)

    assert len(rows) == 2, "a cable went missing from the bundle"
    assert {r["name"] for r in rows} == {"old", "new"}
    # The other half of the same theft: a real length overwritten with NULL.
    assert all(r["length_m"] is not None for r in rows), rows


def test_a_split_layer_keeps_its_uuids_when_the_uuid_is_the_victim(project, tmp_path):
    """The column order the build plan named: ``fiberq_uuid`` is what shifts.

    At HEAD one cable's uuid came back NULL and the other's came back as the
    string "underground".
    """
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "Kablovi_podzemni", "memory")
    layer.dataProvider().addAttributes([
        QgsField("naziv", QVariant.String),
        QgsField(LEGACY_LAYING, QVariant.String),
        QgsField("duzina_m", QVariant.Double),
        QgsField(IDENTITY_FIELD, QVariant.String),
        QgsField(MODERN_LAYING, QVariant.String),
    ])
    layer.updateFields()
    project.addMapLayer(layer)
    for name, uuid, field, value in (
            ("old", "99999999-9999-4999-8999-999999999999", LEGACY_LAYING, "Podzemno"),
            ("new", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", MODERN_LAYING, "underground")):
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(50, 0)]))
        feat["naziv"] = name
        feat["duzina_m"] = 50.0
        feat[IDENTITY_FIELD] = uuid
        feat[field] = value
        layer.startEditing()
        assert layer.addFeature(feat)
        assert layer.commitChanges()

    rows = _export(project, tmp_path, layer)

    assert len(rows) == 2
    assert {r[IDENTITY_FIELD] for r in rows} == {
        "99999999-9999-4999-8999-999999999999",
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}
    by_name = {r["name"]: r for r in rows}
    assert by_name["old"]["installation_type"] == "underground"
    assert by_name["new"]["installation_type"] == "underground"


def test_the_exporter_merges_the_two_laying_columns(project, tmp_path):
    """One canonical column, carrying whichever spelling held the value."""
    cables = _legacy_cable_layer(project, extra=(MODERN_LAYING,))
    _add_cable(cables, "11111111-1111-4111-8111-111111111111",
               LEGACY_LAYING, "Podzemno", name="old")
    _add_cable(cables, "22222222-2222-4222-8222-222222222222",
               MODERN_LAYING, "underground", name="new")

    rows = _export(project, tmp_path, cables)

    by_name = {r["name"]: r for r in rows}
    assert "installation_type" in rows[0], sorted(rows[0])
    assert by_name["old"]["installation_type"] == "underground"
    assert by_name["new"]["installation_type"] == "underground"


def test_the_exporter_writes_one_installation_type_column_only(project, tmp_path):
    cables = _legacy_cable_layer(project, extra=(MODERN_LAYING,))
    _add_cable(cables, "11111111-1111-4111-8111-111111111111",
               LEGACY_LAYING, "Podzemno")

    rows = _export(project, tmp_path, cables)

    columns = sorted(rows[0])
    assert columns.count("installation_type") == 1
    assert LEGACY_LAYING not in columns
    assert MODERN_LAYING not in columns


def test_an_unsplit_legacy_layer_still_exports_its_laying_value(project, tmp_path):
    """The ordinary old project, which never met v1.5.0's lay_cable."""
    cables = _legacy_cable_layer(project)
    _add_cable(cables, "33333333-3333-4333-8333-333333333333",
               LEGACY_LAYING, "Podzemno")

    rows = _export(project, tmp_path, cables)

    assert rows[0][IDENTITY_FIELD] == "33333333-3333-4333-8333-333333333333"
    assert rows[0]["installation_type"] == "underground"


# ---------------------------------------------------------------------------
# The importer: writing back into the column the layer actually has
# ---------------------------------------------------------------------------

def test_the_importer_writes_back_into_the_old_column(project, tmp_path):
    """Round trip: export from a legacy layer, import into a fresh one.

    Before the fix the value took the "column the format does not model" path
    into ``fq_extra_json`` and the real column stayed empty.
    """
    from fiberq.core.interchange_import import InterchangeBundleReader

    source = _legacy_cable_layer(project)
    _add_cable(source, "44444444-4444-4444-8444-444444444444",
               LEGACY_LAYING, "Podzemno")
    out = os.path.join(str(tmp_path), "bundle.gpkg")
    from fiberq.core.interchange_bundle import InterchangeBundleWriter
    assert InterchangeBundleWriter(project).write(out, layers=[source]).ok

    project.removeAllMapLayers()
    target = _legacy_cable_layer(project)
    assert target.featureCount() == 0

    result = InterchangeBundleReader(project).read(out)
    assert result.ok, result.errors

    imported = [f for f in target.getFeatures()]
    assert len(imported) == 1
    assert imported[0][LEGACY_LAYING] == "Podzemno", (
        "the value must reach the column the layer really has, and come back "
        "as the Serbian term the domain maps to 'underground'")
    assert MODERN_LAYING not in target.fields().names()


def test_the_importer_warns_when_slack_has_no_cable_reference(project, tmp_path):
    """v1.5.0 left the loops detached and said nothing.

    QA section C step 9: "Imported loops have Cable layer ID/feature ID
    filled, or a warning (v1.5.0: empty, no warning)."
    """
    from fiberq.core.interchange_import import InterchangeBundleReader
    from fiberq.core.interchange_bundle import InterchangeBundleWriter

    cables = _legacy_cable_layer(project)
    _add_cable(cables, "55555555-5555-4555-8555-555555555555",
               LEGACY_LAYING, "Podzemno")
    slack = QgsVectorLayer("Point?crs=EPSG:3857", "Optical slack", "memory")
    slack.dataProvider().addAttributes([
        QgsField("tip", QVariant.String),
        QgsField("duzina_m", QVariant.Double),
        QgsField("cable_layer_id", QVariant.String),
        QgsField("cable_fid", QVariant.Int),
        QgsField(IDENTITY_FIELD, QVariant.String),
    ])
    slack.updateFields()
    loop = QgsFeature(slack.fields())
    loop.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
    loop["tip"] = "Terminal"
    loop["duzina_m"] = 30.0
    loop["cable_layer_id"] = cables.id()
    loop["cable_fid"] = int(next(cables.getFeatures()).id())
    loop[IDENTITY_FIELD] = "66666666-6666-4666-8666-666666666666"
    slack.startEditing()
    slack.addFeature(loop)
    slack.commitChanges()
    project.addMapLayer(slack)

    out = os.path.join(str(tmp_path), "bundle.gpkg")
    assert InterchangeBundleWriter(project).write(out, layers=[cables, slack]).ok

    # Import into a project whose slack layer has neither spelling.
    project.removeAllMapLayers()
    _legacy_cable_layer(project)
    bare = QgsVectorLayer("Point?crs=EPSG:3857", "Optical slack", "memory")
    bare.dataProvider().addAttributes([
        QgsField("tip", QVariant.String),
        QgsField("duzina_m", QVariant.Double),
        QgsField(IDENTITY_FIELD, QVariant.String),
    ])
    bare.updateFields()
    project.addMapLayer(bare)

    result = InterchangeBundleReader(project).read(out)
    assert any("no cable reference columns" in w for w in result.warnings), (
        f"expected a warning, got {result.warnings}")


# ---------------------------------------------------------------------------
# The resolver, on the field U4 is about
# ---------------------------------------------------------------------------

def test_actual_field_knows_the_laying_column():
    assert fm.actual_field([LEGACY_LAYING], MODERN_LAYING) == LEGACY_LAYING
    assert fm.actual_field([MODERN_LAYING], MODERN_LAYING) == MODERN_LAYING
    assert fm.actual_field([MODERN_LAYING, LEGACY_LAYING], MODERN_LAYING) == MODERN_LAYING


def test_both_laying_spellings_map_to_one_canonical_name():
    """Which is why the exporter had two sources for one destination."""
    assert fm.canonical_field("cable", MODERN_LAYING) == "installation_type"
    assert fm.canonical_field("cable", LEGACY_LAYING) == "installation_type"
