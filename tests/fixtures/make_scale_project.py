#!/usr/bin/env python3
"""Generate a large, synthetic FiberQ project for scale testing.

The demo project in ``docs/samples/`` is deliberately tiny: it is a *worked
example*, small enough that a reader can check every finding by hand. This is the
other fixture -- a realistic-sized design nobody is meant to read, for answering
"does the validator still work at 25,000 features?" without needing anyone's real
network data.

Nothing here is committed. Generate what you need, when you need it:

    python tests/fixtures/make_scale_project.py 5000 /tmp/big.gpkg

The design is a grid of street segments, each with a route, a cable, two poles
and a manhole, all correctly connected -- so a clean run is the expected result
and any finding is a real regression. Pass ``--faulty`` to detach every element
instead, which makes the rules fire on roughly two thirds of the features and is
how to exercise the panel and the report at volume.

Layer and field names come from ``fiberq.models.schema``, like the demo, so this
cannot drift away from the real data model.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from fiberq.models import schema  # noqa: E402
from make_demo_project import (  # noqa: E402
    EPSG, _OGR_GEOM, _OGR_TYPE, _ground_length, _uuid, _wkt)

#: Same quiet corner of the Adriatic the demo uses.
ORIGIN_X, ORIGIN_Y = 1_900_000.0, 5_400_000.0

#: Street segment geometry, in projected metres.
SEGMENT_LENGTH = 120.0
ROW_SPACING = 80.0
PER_ROW = 40

#: How far a detached element sits from the network in --faulty mode. Well past
#: the 5-unit default tolerance, so A3 is unambiguous.
DETACH_OFFSET = 500.0


def _cell(index):
    """``(x0, y0)`` of street segment ``index`` in the grid."""
    row, col = divmod(index, PER_ROW)
    return ORIGIN_X + col * SEGMENT_LENGTH, ORIGIN_Y + row * ROW_SPACING


def rows(n_segments, faulty=False):
    """``{layer: [(geometry, attributes), ...]}`` for a grid of ``n_segments``."""
    routes, cables, poles, manholes = [], [], [], []
    counter = iter(range(1, 20_000_000))

    for i in range(n_segments):
        x0, y0 = _cell(i)
        line = [(x0, y0), (x0 + SEGMENT_LENGTH, y0)]
        length = _ground_length(line)
        offset = DETACH_OFFSET if faulty else 0.0

        routes.append((line, {
            "naziv": f"R-{i}", "tip_trase": "Underground",
            "duzina": length, "duzina_km": round(length / 1000.0, 2),
            schema.IDENTITY_FIELD: _uuid(next(counter))}))

        cables.append((line, {
            "naziv": f"UC-{i}", "tip": "Optical", "podtip": "Distribution",
            "stanje_kabla": "Existing", "broj_vlakana": 24, "broj_cevcica": 2,
            "slabljenje_dbkm": 0.35, "duzina_m": length, "slack_m": 0.0,
            "total_len_m": length,
            schema.IDENTITY_FIELD: _uuid(next(counter))}))

        for dx in (0.0, SEGMENT_LENGTH):
            poles.append(((x0 + dx, y0 + offset), {
                "tip": "Pole", schema.IDENTITY_FIELD: _uuid(next(counter))}))

        manholes.append(((x0 + SEGMENT_LENGTH / 2, y0 + offset), {
            "tip": "Manhole", schema.IDENTITY_FIELD: _uuid(next(counter))}))

    return {
        "Route": routes,
        "Underground cables": cables,
        "Poles": poles,
        "Manholes": manholes,
    }


def build(path, n_segments, faulty=False):
    """Write the scale GeoPackage. Returns ``(path, feature_count)``."""
    from osgeo import ogr, osr

    ogr.UseExceptions()
    if os.path.exists(path):
        os.remove(path)

    driver = ogr.GetDriverByName("GPKG")
    source = driver.CreateDataSource(path)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(EPSG)

    total = 0
    for layer_name, features in rows(n_segments, faulty).items():
        layer_schema = schema.LAYER_SCHEMAS[layer_name]
        layer = source.CreateLayer(
            layer_name.replace(" ", "_"), srs,
            getattr(ogr, _OGR_GEOM[layer_schema.geometry]))
        for field_def in layer_schema.fields:
            layer.CreateField(ogr.FieldDefn(
                field_def.key,
                getattr(ogr, _OGR_TYPE.get(field_def.field_type, "OFTString"))))

        definition = layer.GetLayerDefn()
        layer.StartTransaction()   # one commit per layer, not per feature
        for coords, attrs in features:
            feature = ogr.Feature(definition)
            for key, value in attrs.items():
                if definition.GetFieldIndex(key) >= 0:
                    feature.SetField(key, value)
            feature.SetGeometry(ogr.CreateGeometryFromWkt(
                _wkt(layer_schema.geometry, coords)))
            layer.CreateFeature(feature)
            feature = None
            total += 1
        layer.CommitTransaction()
        layer = None

    source = None
    return path, total


def build_project(gpkg_path, qgz_path):
    """A QGIS project over the scale GeoPackage. Needs QGIS."""
    from make_demo_project import _set_view_extent, load_demo_layers

    from qgis.core import QgsProject

    from fiberq.core.schema_version import mark_project_current

    project = QgsProject()
    layers = load_demo_layers(gpkg_path, project)
    mark_project_current(project)
    _set_view_extent(project, layers.values())
    project.write(qgz_path)
    return qgz_path


def main(argv):
    faulty = "--faulty" in argv
    argv = [a for a in argv if a != "--faulty"]
    n = int(argv[1]) if len(argv) > 1 else 2000
    out = argv[2] if len(argv) > 2 else os.path.join(HERE, "scale_project.gpkg")

    path, total = build(out, n, faulty)
    print(f"Wrote {path}  ({n} street segments, {total} features"
          f"{', all elements detached' if faulty else ''})")

    try:
        from qgis.core import QgsApplication
    except ImportError:
        print("QGIS not available -- GeoPackage written without a project file")
        return 0

    # Writing the project needs a running application. Without one QGIS still
    # produces a file, but prints "Application path not initialized" for every
    # layer, which makes a working run look broken.
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        qgz = os.path.splitext(out)[0] + ".qgz"
        build_project(out, qgz)
        print(f"Wrote {qgz}")
    finally:
        app.exitQgis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
