"""Publish to PostGIS: which column becomes the table's primary key.

WP4 item U11, branch ``refactor/v160-cleanup``. Unclaimed: the PostGIS bridge is
pre-award code, and the Pro prompt in front of the dialog is not touched here.

``_ensure_pk_field`` took an integer field named id, pk or gid, else the first
integer field of any kind, else it added an ``id`` column to the layer being
published and saved it there. Both fallbacks were wrong:

- The first integer field of an unsaved FiberQ layer is a count, a year or a
  reference -- ``broj_cevcica`` on Cables, ``god_ugrad`` on Manholes,
  ``cable_fid`` on Optical slacks. Against a real PostGIS the export wrote
  0 rows: the second feature holding the same value broke the primary key.
- Adding the column changed the user's data, and the change stayed when the
  publish failed: a shapefile's .dbf on disk gained it, and a layer already in
  edit mode kept an empty column that rolling back did not remove.

Now the key is the layer's own -- an id/pk/gid field, or the provider's key such
as a GeoPackage fid, either one only when every feature holds a different whole
number -- or else a name the layer does not have in any case, which the
postgres provider creates itself as a serial key. The layer is never changed.

No test here needs a database: ``exportLayer`` is replaced by a stand-in with
the binding's own signature, which records the key in the URI it was handed
and answers Success. The dialog's configuration is replaced as well, never read
from ``config.ini``: the tracked file names localhost:5433, where a developer's
own PostGIS may well be listening.
"""
import re

import pytest
from qgis.core import (
    Qgis,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerExporter,
    QgsVectorLayerUtils,
)
from qgis.PyQt.QtWidgets import QMessageBox

from fiberq.addons import publish_pg
from fiberq.models import schema as fq_schema

#: Nothing listens on port 1, so a connection is refused at once: in CI, and in
#: a container started with ``--network none`` alike. An IP, so no name lookup.
UNREACHABLE = {
    "host": "127.0.0.1",
    "port": "1",
    "dbname": "gis",
    "user": "gis",
    "password": "gis",
    "schema": "public",
    "sslmode": "disable",
}

#: models/schema.py's logical field types, as memory-layer field types.
MEMORY_TYPES = {
    "text": "string",
    "enum": "string",
    "int": "integer",
    "year": "integer",
    "double": "double",
    "bool": "boolean",
}


class FakeIface:
    def __init__(self, layer):
        self._layer = layer

    def mainWindow(self):
        return None

    def activeLayer(self):
        return self._layer


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture
def modals(monkeypatch):
    """What the dialog would have shown, by kind."""
    said = {"info": [], "critical": [], "warning": []}
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: said["info"].append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: said["critical"].append(str(a[-1]))))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: said["warning"].append(str(a[-1]))))
    return said


def _memory(name, fields, rows, geometry="Point"):
    """A memory layer with ``fields`` given as ``name:type``, one feature per row."""
    uri = f"{geometry}?crs=EPSG:3857" + "".join(f"&field={field}" for field in fields)
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), uri
    features = []
    for i, values in enumerate(rows):
        feature = QgsFeature(layer.fields())
        wkt = f"Point ({i} 0)" if geometry == "Point" else f"LineString ({i} 0, {i} 1)"
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        feature.setAttributes(list(values))
        features.append(feature)
    assert layer.dataProvider().addFeatures(features)[0]
    return layer


def _saved(layer, path, driver, layer_options=()):
    """``layer`` written to a file and read back from it: a user's own file layer."""
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver
    options.layerName = layer.name()
    if layer_options:
        options.layerOptions = list(layer_options)
    written = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsCoordinateTransformContext(), options)
    assert written[0] == QgsVectorFileWriter.WriterError.NoError, written
    source = f"{path}|layername={layer.name()}" if driver == "GPKG" else str(path)
    saved = QgsVectorLayer(source, layer.name(), "ogr")
    assert saved.isValid(), source
    return saved


def _fiberq_layer(name, numbers):
    """An unsaved FiberQ layer with the fields models/schema.py lists for it.

    One feature per entry of ``numbers``, which go into the layer's first
    integer field -- the one the old rule made the key. Everything else is NULL.
    """
    roster = fq_schema.get_layer_schema(name)
    fields = [f for f in roster.fields if not f.on_demand]
    first_int = next(i for i, f in enumerate(fields) if MEMORY_TYPES[f.field_type] == "integer")
    rows = [[number if i == first_int else None for i in range(len(fields))] for number in numbers]
    layer = _memory(name, [f"{f.key}:{MEMORY_TYPES[f.field_type]}" for f in fields], rows, roster.geometry)
    return layer, fields[first_int].key


def _state(layer):
    """What publishing must leave exactly as it was."""
    return {
        "fields": [field.name() for field in layer.fields()],
        "editable": layer.isEditable(),
        "modified": layer.isModified(),
        "values": sorted(str(feature.attributes()) for feature in layer.getFeatures()),
    }


def _dialog(monkeypatch, layer, overwrite=True):
    """A real PublishDialog on ``UNREACHABLE``; ``accepted`` records it closing."""
    monkeypatch.setattr(publish_pg, "_load_pg_config", lambda: dict(UNREACHABLE))
    dlg = publish_pg.PublishDialog(FakeIface(layer))
    dlg.chk_overwrite.setChecked(overwrite)
    accepted = []
    dlg.accept = lambda: accepted.append(True)
    return dlg, accepted


def _answering(code, message, keys=None):
    """A stand-in with the binding's own signature, so a call QGIS would refuse
    with TypeError is refused here too. ``keys`` collects the key each call named."""
    def stand_in(layer, uri, providerKey, destCRS, onlySelected=False, options=None, feedback=None):
        if keys is not None:
            match = re.search(r"key='([^']*)'", uri)
            keys.append(match.group(1) if match else None)
        return code, message
    return staticmethod(stand_in)


def _publish(monkeypatch, source):
    """Press Publish on ``source`` with QGIS answering Success; the key the export named."""
    keys = []
    monkeypatch.setattr(QgsVectorLayerExporter, "exportLayer",
                        _answering(Qgis.VectorExportResult.Success, "", keys))
    dlg, accepted = _dialog(monkeypatch, source)
    dlg._do_export()
    assert accepted == [True]
    assert len(set(keys)) == 1, keys
    return keys[0]


@pytest.mark.parametrize("name, numbers", [
    ("Underground cables", [2, 2, 1]),
    ("Manholes", [2019, 2019, 2021]),
    ("Optical slack", [4, 4, 7]),
], ids=["cables", "manholes", "slacks"])
def test_fiberq_layers_get_a_key_postgis_creates(monkeypatch, modals, project, name, numbers):
    """v1.5.0 made broj_cevcica, god_ugrad and cable_fid the key, and wrote 0 rows."""
    layer, first_int = _fiberq_layer(name, numbers)
    project.addMapLayer(layer)
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    assert key == "id", f"the key was {key!r}; {first_int} holds {numbers}"
    assert "id" not in [field.lower() for field in before["fields"]]
    assert "Used PK column: id (new, created and numbered by PostGIS)" in modals["info"][0], modals
    assert _state(layer) == before


@pytest.mark.parametrize("storage, editing", [
    ("memory", False),
    ("memory", True),
    ("shapefile", False),
], ids=["memory", "memory-editing", "shapefile"])
def test_the_layer_being_published_is_never_changed(monkeypatch, modals, project, tmp_path, storage, editing):
    """v1.5.0 added and saved an ``id`` column here, and it stayed even when the
    publish then failed: in the .dbf on disk, and as an empty column a rollback
    did not remove."""
    layer = _memory("Poles", ["naziv:string"], [["p0"], ["p1"], ["p2"]])
    if storage == "shapefile":
        layer = _saved(layer, tmp_path / "poles.shp", "ESRI Shapefile")
    project.addMapLayer(layer)
    if editing:
        assert layer.startEditing()
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    assert key == "id"
    assert _state(layer) == before
    if storage == "shapefile":
        on_disk = QgsVectorLayer(str(tmp_path / "poles.shp"), "check", "ogr")
        assert [field.name() for field in on_disk.fields()] == ["naziv"]


@pytest.mark.parametrize("storage, fields, rows, expected", [
    ("gpkg", ["naziv:string", "broj:integer"], [["a", 7], ["b", 7], ["c", 9]], "fid"),
    ("gpkg-objectid", ["naziv:string"], [["a"], ["b"]], "OBJECTID"),
    ("gpkg", ["naziv:string", "id:integer"], [["a", 30], ["b", 10], ["c", 20]], "id"),
    ("memory", ["naziv:string", "id:integer"], [["a", 3], ["b", 1], ["c", 2]], "id"),
    ("memory", ["GID:long", "naziv:string"], [[11, "a"], [12, "b"]], "GID"),
    ("shapefile", ["naziv:string", "pk:integer"], [["a", 5], ["b", 6]], "pk"),
], ids=["gpkg-fid", "gpkg-objectid", "gpkg-with-id", "memory-id", "memory-GID", "shapefile-pk"])
def test_the_layers_own_unique_key_is_kept(monkeypatch, modals, project, tmp_path, storage, fields, rows, expected):
    """Characterisation: each of these was already the key on v1.5.0, and must stay it.

    An integer id/pk/gid field comes first, as it did; otherwise the provider's
    own key, which for a GeoPackage is its fid column whatever it is called.
    """
    layer = _memory("Poles", fields, rows)
    if storage.startswith("gpkg"):
        options = ["FID=OBJECTID"] if storage == "gpkg-objectid" else []
        layer = _saved(layer, tmp_path / "poles.gpkg", "GPKG", options)
    elif storage == "shapefile":
        layer = _saved(layer, tmp_path / "poles.shp", "ESRI Shapefile")
    project.addMapLayer(layer)
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    # In any case: the export asks QGIS to lowercase the column names.
    assert key.lower() == expected.lower()
    assert "created and numbered by PostGIS" not in modals["info"][0], modals
    assert _state(layer) == before


def test_a_repeated_id_gives_way_to_the_layers_own_key(monkeypatch, modals, project, tmp_path):
    """An integer id that repeats is no key, and the GeoPackage's own fid is
    taken instead of a new column: every candidate is tried in turn, not only
    the first. v1.5.0 took the repeated id, and the export wrote 0 rows."""
    layer = _saved(_memory("Poles", ["naziv:string", "id:integer"], [["a", 1], ["b", 1], ["c", 2]]),
                   tmp_path / "poles.gpkg", "GPKG")
    project.addMapLayer(layer)

    key = _publish(monkeypatch, layer)

    assert key.lower() == "fid"
    assert "created and numbered by PostGIS" not in modals["info"][0], modals


@pytest.mark.parametrize("fields, rows, expected", [
    (["id:integer", "naziv:string"], [[1, "a"], [1, "b"], [2, "c"]], "id_1"),
    (["id:integer", "naziv:string"], [[1, "a"], [None, "b"], [2, "c"]], "id_1"),
    (["ID:string", "naziv:string"], [["A-1", "a"], ["A-2", "b"]], "id_1"),
], ids=["repeated-id", "null-id", "text-ID"])
def test_a_key_must_hold_a_different_number_on_every_feature(monkeypatch, modals, project, fields, rows, expected):
    """An ``id`` that repeats, or is NULL somewhere, cannot be a primary key: the
    export would write nothing. The new key then needs a name the layer does not
    have in any case -- QGIS is asked to lowercase field names, and a field
    ``ID`` would land on a key called ``id``."""
    layer = _memory("Poles", fields, rows)
    project.addMapLayer(layer)
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    assert key == expected
    assert f"Used PK column: {expected} (new, created and numbered by PostGIS)" in modals["info"][0], modals
    assert _state(layer) == before


def test_a_geopackage_feature_not_saved_yet_has_no_fid(monkeypatch, modals, project, tmp_path):
    """A feature added in the edit buffer reads 'Autogenerate' in its fid until it is
    saved, so the fid is no key for what the export writes: buffer included."""
    layer = _saved(_memory("Poles", ["naziv:string"], [["a"], ["b"]]), tmp_path / "poles.gpkg", "GPKG")
    project.addMapLayer(layer)
    assert layer.startEditing()
    # The way the attribute form makes a new feature, fid default included.
    feature = QgsVectorLayerUtils.createFeature(layer, QgsGeometry.fromWkt("Point (9 9)"), {1: "new"})
    assert layer.addFeature(feature)
    before = _state(layer)

    key = _publish(monkeypatch, layer)

    assert key == "id"
    assert _state(layer) == before
    assert layer.editBuffer().addedFeatures(), "the unsaved feature is still waiting to be saved"
