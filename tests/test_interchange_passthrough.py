"""A date column in a bundle ended the import halfway, and said so vaguely.

WP4 4.2 item U19 (unclaimed), which is the fix for FU-9. Branch
``fix/wp4-interchange``.

``_restore_attributes`` put the raw provider value of a column FiberQ has no
field for straight into the passthrough extras, and the import then called
``json.dumps`` on it. A ``QDate`` is not JSON-serialisable. Measured on
``qgis/qgis:3.40`` and ``4.2-trixie``, Qt5 and Qt6 alike::

    TypeError: Object of type QDate is not JSON serializable

**It is the mid-import failure that makes this more than a crash.** Bundle
tables are read in ``gpkg_contents`` order, so the project keeps whatever was
added before the raise and never reads the rest, and ``main_plugin`` turns the
exception into *"Could not read the bundle: ..."*. The user is left with a
warning and a half-imported project that looks finished. Spec section 9 says a
conformant reader must read every feature layer, and refuse a bundle it cannot
handle **rather than importing it partially** -- so this was the one path that
contradicted the format's own promise.

**The second site corrupted instead of crashing.** ``_keep_unsupported`` fell
back to ``str(value)``, which is not a crash and not a value either. Measured
payloads for the same bundle::

    3.40:  "surveyed_on": "PyQt5.QtCore.QDate(2026, 1, 2)"
    4.2:   "surveyed_on": "PyQt6.QtCore.QDate(2026, 1, 2)"

So the **PyQt binding version leaked into a published interchange payload**, and
one bundle round-tripped to different bytes on Qt5 and Qt6. For a format whose
first rule is *preserve, don't discard*, that is worse than the crash: it looks
like it worked.

Both sites now use one helper, :func:`fiberq.core.interchange.json_safe`.

**The plan's two further limits, each checked rather than assumed.**

* *Extras from a newer minor version should be re-emitted into the next
  bundle.* Measured: this **already worked** before this branch --
  ``_load_passthrough`` collects them and ``_canonical_layer`` inlines them into
  ``fq_extra_json``. It is pinned below as characterisation rather than claimed
  as a fix.
* *A ``placement`` with no matching layer should be kept.* Measured: it was
  **dropped in silence**. ``fq_type=otb`` with ``placement="wall"`` imported into
  the plain OTB layer and re-exported as ``placement`` NULL with nothing in
  ``fq_extra_json`` -- no warning anywhere. Spec section 6.1 says placement is
  an attribute, not a type, so the value is the user's data. Now kept.
"""
import json

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QTime, QVariant

from fiberq.core import interchange as ic
from fiberq.core.interchange_bundle import InterchangeBundleWriter
from fiberq.core.interchange_import import InterchangeBundleReader

LON, LAT = 21.90, 43.32


# ---------------------------------------------------------------------------
# the helper, on its own
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    (QDate(2025, 3, 17), "2025-03-17"),
    (QDateTime(QDate(2025, 3, 17), QTime(14, 5, 6)), "2025-03-17T14:05:06"),
    (QTime(14, 5, 6), "14:05:06"),
])
def test_a_qt_date_becomes_iso_text(value, expected):
    """ISO, not ``str()``.

    ``str(QDate(2025, 3, 17))`` is ``'PyQt5.QtCore.QDate(2025, 3, 17)'`` --
    measured -- which no consumer of this format could read back, and which
    differs between Qt5 and Qt6. The ISO text round-trips and is identical on
    every supported version.
    """
    assert ic.json_safe(value) == expected
    json.dumps(ic.json_safe(value))


def test_a_null_date_is_absent_rather_than_empty():
    """A null QDate formats as ``''``, which a reader cannot tell from a real
    empty string. ``None`` says "this had no value"."""
    assert ic.json_safe(QDate()) is None


def test_a_null_qvariant_is_none():
    assert ic.json_safe(QVariant()) is None


def test_a_qvariant_is_unwrapped_to_its_value():
    """Asserted on the type and on json.dumps, not on ``== 7``.

    ``QVariant(7) == 7`` is True, so an equality check alone passes even when
    nothing was unwrapped at all -- it would have been a test that could not
    fail. What matters is that a real ``int`` comes out and that the result
    survives ``json.dumps``, which a QVariant does not.
    """
    out = ic.json_safe(QVariant(7))
    assert type(out) is int, f"still a {type(out).__name__}"
    assert json.dumps(out) == "7"


@pytest.mark.parametrize("value", ["text", 7, 7.5, True, None])
def test_what_json_already_accepts_is_untouched(value):
    assert ic.json_safe(value) is value


def test_nested_containers_are_coerced_all_the_way_down():
    out = ic.json_safe({"when": [QDate(2025, 3, 17), None], "t": (QTime(1, 2, 3),)})
    assert out == {"when": ["2025-03-17", None], "t": ["01:02:03"]}
    json.dumps(out)


def test_something_with_no_rule_keeps_its_text_rather_than_raising():
    """Rule 1 of the format is *preserve, don't discard*. An unknown type is
    worth its text; it is not worth ending the import for."""
    class Odd:
        def __str__(self):
            return "odd-value"

    assert ic.json_safe(Odd()) == "odd-value"
    json.dumps(ic.json_safe(Odd()))


# ---------------------------------------------------------------------------
# through a real bundle
# ---------------------------------------------------------------------------

def _bundle_layer(name, fields, geometry="Point"):
    uri = f"{geometry}?crs=EPSG:4326&" + "&".join(f"field={f}" for f in fields)
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), name
    return layer


@pytest.fixture
def project():
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    yield prj
    prj.clear()


@pytest.fixture
def target_project():
    prj = QgsProject()
    prj.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    yield prj
    prj.clear()


def _foreign_bundle(tmp_path, name="foreign.gpkg", extra_fields=(), values=None,
                    layer_name="Joint Closures"):
    """A bundle carrying columns FiberQ has no field for.

    Built with the real writer from a layer that happens to have the extra
    columns, which is how a bundle from another tool looks: the writer keeps a
    column it has no canonical name for under the name it arrived with.
    """
    source = QgsProject()
    source.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    layer = _bundle_layer(
        layer_name, ("fiberq_uuid:string(64)", "naziv:string") + tuple(extra_fields))
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    feature.setAttribute("fiberq_uuid", "u-1")
    feature.setAttribute("naziv", "C1")
    for key, value in (values or {}).items():
        feature.setAttribute(key, value)
    assert layer.dataProvider().addFeatures([feature])[0]

    path = str(tmp_path / name)
    written = InterchangeBundleWriter(source).write(path, layers=[layer])
    assert written.ok, written.errors
    source.clear()
    return path


def test_a_date_column_no_longer_ends_the_import(tmp_path, target_project):
    """The acceptance line, and FU-9's regression.

    Fails before this fix with ``TypeError: Object of type QDate is not JSON
    serializable``, raised from inside ``read()``.
    """
    bundle = _foreign_bundle(
        tmp_path, extra_fields=("surveyed_on:date",),
        values={"surveyed_on": QDate(2026, 1, 2)})

    result = InterchangeBundleReader(target_project).read(bundle)

    assert result.ok, result.errors
    assert not result.errors


def test_the_date_survives_in_a_form_a_reader_can_use(tmp_path, target_project):
    bundle = _foreign_bundle(
        tmp_path, extra_fields=("surveyed_on:date",),
        values={"surveyed_on": QDate(2026, 1, 2)})

    InterchangeBundleReader(target_project).read(bundle)

    stored = target_project.readEntry(*ic.PASSTHROUGH_ENTRY, "")[0]
    assert "2026-01-02" in stored, f"the date is not ISO in the store: {stored[:200]}"
    assert "QDate" not in stored, (
        "the PyQt repr is in a published payload; the same bundle would round-trip to "
        "different bytes on Qt5 and Qt6")


def test_a_null_foreign_column_does_not_end_the_import(tmp_path, target_project):
    """The other half of FU-9's reproduction. On 3.40 this raised
    ``TypeError: Object of type QVariant is not JSON serializable`` before the
    date did, purely because ``sort_keys=True`` reached it first."""
    bundle = _foreign_bundle(
        tmp_path, extra_fields=("surveyed_on:date", "owner_ref:string"),
        values={"surveyed_on": QDate(2026, 1, 2)})

    result = InterchangeBundleReader(target_project).read(bundle)

    assert result.ok, result.errors


def test_a_date_survives_a_whole_round_trip(tmp_path, target_project):
    """Import, then export again: the value has to reach the next bundle's
    ``fq_extra_json``, not merely survive being read."""
    bundle = _foreign_bundle(
        tmp_path, extra_fields=("surveyed_on:date",),
        values={"surveyed_on": QDate(2026, 1, 2)})
    assert InterchangeBundleReader(target_project).read(bundle).ok

    again = str(tmp_path / "again.gpkg")
    layers = [lyr for lyr in target_project.mapLayers().values()
              if isinstance(lyr, QgsVectorLayer)]
    written = InterchangeBundleWriter(target_project).write(again, layers=layers)
    assert written.ok, written.errors

    out = QgsVectorLayer(f"{again}|layername=Joint Closures", "check", "ogr")
    assert out.isValid()
    carried = [str(f.attribute("fq_extra_json") or "") for f in out.getFeatures()]
    assert any("2026-01-02" in text for text in carried), (
        f"the date did not reach the next bundle: {carried}")


def test_extras_from_a_newer_version_are_re_emitted(tmp_path, target_project):
    """Characterisation, and the plan's first "limit" -- which turned out not to
    be one.

    Measured against the parent commit: this already worked.
    ``_load_passthrough`` collects the stored ``feature_attributes`` rows and
    ``_canonical_layer`` inlines them into the next bundle's ``fq_extra_json``.
    It is pinned here because it is the mechanism the date fix rides on, and
    because a plan row asserting otherwise should not be taken on trust by the
    next person to read it.
    """
    bundle = _foreign_bundle(
        tmp_path, extra_fields=("tray_count:integer",), values={"tray_count": 12})
    assert InterchangeBundleReader(target_project).read(bundle).ok

    again = str(tmp_path / "again.gpkg")
    layers = [lyr for lyr in target_project.mapLayers().values()
              if isinstance(lyr, QgsVectorLayer)]
    assert InterchangeBundleWriter(target_project).write(again, layers=layers).ok

    out = QgsVectorLayer(f"{again}|layername=Joint Closures", "check", "ogr")
    carried = [str(f.attribute("fq_extra_json") or "") for f in out.getFeatures()]
    assert any("tray_count" in text for text in carried), carried


# ---------------------------------------------------------------------------
# placement
# ---------------------------------------------------------------------------

def test_a_placement_the_plugin_does_not_model_is_kept(tmp_path, target_project):
    """The plan's second limit, and a real one.

    ``layer_for_type("otb", "wall")`` falls back to the plain OTB layer, which
    is the right place for it. But ``placement`` is a bundle column, so
    ``_restore_attributes`` skipped it and the value was gone: measured, the
    re-exported row read ``placement`` NULL with an empty ``fq_extra_json`` and
    no warning anywhere.
    """
    source = QgsProject()
    source.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    layer = _bundle_layer("OTB", ("fiberq_uuid:string(64)", "naziv:string"))
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    feature.setAttribute("fiberq_uuid", "u-otb-1")
    feature.setAttribute("naziv", "B1")
    assert layer.dataProvider().addFeatures([feature])[0]
    bundle = str(tmp_path / "otb.gpkg")
    assert InterchangeBundleWriter(source).write(bundle, layers=[layer]).ok
    source.clear()

    # Rewrite placement to a value this plugin has no layer for. Done on the
    # file rather than through the writer because the writer only ever emits
    # placements it models -- a foreign tool is the only way this arises.
    out = QgsVectorLayer(f"{bundle}|layername=OTB", "edit", "ogr")
    assert out.isValid()
    index = out.fields().indexFromName("placement")
    assert index >= 0, "the bundle has no placement column; this fixture is stale"
    fid = next(out.getFeatures()).id()
    assert out.dataProvider().changeAttributeValues({fid: {index: "wall"}})
    del out

    assert not ic.placement_is_modelled("otb", "wall"), (
        "this test only means anything while 'wall' is a placement with no layer of its own")

    assert InterchangeBundleReader(target_project).read(bundle).ok

    stored = target_project.readEntry(*ic.PASSTHROUGH_ENTRY, "")[0]
    assert "wall" in stored, (
        f"the placement was dropped instead of kept in the extras: {stored[:200]}")


def test_a_placement_the_plugin_does_model_is_not_duplicated(tmp_path, target_project):
    """The mirror: ``indoor`` has a layer of its own, so it must travel as the
    layer choice it already is and not be copied into the extras as well."""
    assert ic.placement_is_modelled("otb", "indoor"), (
        "this test's premise: 'indoor' is a modelled placement for otb")

    source = QgsProject()
    source.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    layer = _bundle_layer("Indoor OTB", ("fiberq_uuid:string(64)", "naziv:string"))
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    feature.setAttribute("fiberq_uuid", "u-otb-2")
    assert layer.dataProvider().addFeatures([feature])[0]
    bundle = str(tmp_path / "indoor.gpkg")
    assert InterchangeBundleWriter(source).write(bundle, layers=[layer]).ok
    source.clear()

    assert InterchangeBundleReader(target_project).read(bundle).ok

    stored = target_project.readEntry(*ic.PASSTHROUGH_ENTRY, "")[0]
    assert '"placement"' not in stored, (
        f"a modelled placement was copied into the extras as well: {stored[:200]}")
    names = {lyr.name() for lyr in target_project.mapLayers().values()}
    assert "Indoor OTB" in names, names


def test_an_unknown_type_still_keeps_its_date_readably(tmp_path, target_project):
    """The second site: a whole feature the plugin has no layer for.

    This never crashed -- it wrote ``'PyQt5.QtCore.QDate(2026, 1, 2)'`` into the
    payload instead. Same helper now, so the payload is the same bytes on both
    binding stacks.
    """
    source = QgsProject()
    source.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    layer = _bundle_layer("Joint Closures", ("fiberq_uuid:string(64)", "naziv:string"))
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(LON, LAT)))
    feature.setAttribute("fiberq_uuid", "u-odd-1")
    assert layer.dataProvider().addFeatures([feature])[0]
    bundle = str(tmp_path / "odd.gpkg")
    assert InterchangeBundleWriter(source).write(bundle, layers=[layer]).ok
    source.clear()

    out = QgsVectorLayer(f"{bundle}|layername=Joint Closures", "edit", "ogr")
    assert out.isValid()
    assert out.dataProvider().addAttributes([QgsField("surveyed_on", QVariant.Date)])
    out.updateFields()
    fid = next(out.getFeatures()).id()
    type_index = out.fields().indexFromName("fq_type")
    date_index = out.fields().indexFromName("surveyed_on")
    assert out.dataProvider().changeAttributeValues(
        {fid: {type_index: "splitter", date_index: QDate(2026, 1, 2)}})
    del out

    result = InterchangeBundleReader(target_project).read(bundle)
    assert result.ok, result.errors
    assert result.unsupported, "the fixture's unknown fq_type was modelled after all"

    stored = target_project.readEntry(*ic.PASSTHROUGH_ENTRY, "")[0]
    assert "QDate" not in stored, (
        f"the PyQt repr reached the payload: {stored[:300]}")
    assert "2026-01-02" in stored, f"the date was lost: {stored[:300]}"
