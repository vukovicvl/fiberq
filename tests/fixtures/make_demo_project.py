#!/usr/bin/env python3
"""Generate the FiberQ demo GeoPackage used by the WP2 sample validation report.

Synthetic on purpose. A published sample report has to be safe to hand to anyone,
so this invents a small GPON drop in a fictional street rather than anonymising a
real design. The *content* is deterministic -- same coordinates, same fiberq_uuids,
same lengths on every run -- so the findings a regenerated report contains change
only when the rules do.

Two things do change on every regeneration and are not worth chasing: QGIS mints a
fresh random layer id when a layer is loaded (so ``layer_id`` in the JSON report
and the .qgz differ), and GeoPackage stamps ``gpkg_contents.last_change``. Neither
is content; ``tests/test_sample_report.py`` compares rules, severities and issue
order rather than bytes.

The network is deliberately imperfect. Seven of the fourteen validation rules are
meant to fire, each from exactly one planted fault, so the sample report shows
what a real audit looks like instead of an empty table. See ``FAULTS`` below for
the catalogue; ``docs/samples/README.md`` repeats it for readers of the report.

Field rosters come from ``fiberq/models/schema.py``, never from a hand-copied
list, so the fixture cannot drift away from the real schema.

Usage:
    python tests/fixtures/make_demo_project.py [output.gpkg]
"""
import os
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fiberq.models import schema  # noqa: E402

#: Web Mercator, because that is what a basemap-traced design really uses -- and
#: it is where the length rules have something to say.
EPSG = 3857

#: A quiet corner of nowhere: far out in the Adriatic, so nobody mistakes the
#: demo for a real deployment, but at a European latitude where the Web Mercator
#: scale factor (~1.36x here) is representative.
ORIGIN_X, ORIGIN_Y = 1_900_000.0, 5_400_000.0

#: The planted faults, by rule. Kept next to the data that creates them so the
#: two cannot drift apart; asserted by tests/test_demo_project.py.
FAULTS = {
    "A1": ("Aerial cable 'AC-2' is stranded: neither end reaches anything. "
           "One fault, two findings -- a cable has two ends."),
    "A2": ("Aerial cable 'AC-3' starts 7 m from the third pole: outside the 5 m "
           "tolerance, close enough that it was plainly meant to connect. "
           "A2 refines A1 rather than replacing it, so this endpoint is "
           "reported by both."),
    "A3": "The fourth pole sits 45 m off the network, attached to nothing.",
    "B1": "Optical slack 'SL-2' references a cable layer that is not in the project.",
    "B2": ("The fibre break is recorded against the Route layer. The reference "
           "resolves, so only the layer-type check catches it -- a break on a "
           "trench is not a thing."),
    "B3": ("Optical slack 'SL-3' names a cable that exists, but sits 80 m away "
           "from it: a stale link, as if the cable were re-routed afterwards."),
    "B4": ("Two poles share one fiberq_uuid, the signature of a copied and "
           "pasted feature."),
    "C1": "Underground cable 'UC-2' has no cable type recorded.",
    "D1": "Underground cable 'UC-2' is in state 'Someday', not a permitted value.",
    "D2": "Aerial cable 'AC-2' claims 9999 fibres.",
    "D3": "Route 'R-3' stores 210.0 m against a real ground length of ~145 m.",
    "E2": "The fifth pole has no geometry, as an attribute-table edit leaves it.",
}

#: Rules a valid demo project cannot demonstrate, because each needs the project
#: itself to be wrong in a way that would invalidate everything else:
#:
#: * ``C2`` fires when a project contains no FiberQ layers at all.
#: * ``E1`` fires on a missing or mixed CRS. Mixing one in would change what the
#:   A-rule tolerance means for that layer and cascade into every topology
#:   finding here.
#:
#: Both are covered by unit tests instead (tests/test_validation*.py). Asserted
#: by tests/test_sample_report.py so this list cannot quietly go stale.
NOT_DEMONSTRABLE = ("C2", "E1")

#: Slack SL-1 must point at the real, runtime layer id of the Underground cables
#: layer, which only exists once a QgsProject has loaded it. build_demo_project()
#: patches this placeholder; a bare GeoPackage keeps it and B1 stays quiet,
#: because a blank reference is an unlinked slack, not a broken link.
CABLE_LAYER_PLACEHOLDER = ""

_OGR_TYPE = {
    "text": "OFTString",
    "enum": "OFTString",
    "int": "OFTInteger",
    "year": "OFTInteger",
    "bool": "OFTInteger",
    "double": "OFTReal",
    "real": "OFTReal",
    "date": "OFTString",
}

_OGR_GEOM = {
    "Point": "wkbPoint",
    "LineString": "wkbLineString",
    "Polygon": "wkbPolygon",
}


def _p(dx, dy):
    """A point offset from the origin, in metres of the projected CRS."""
    return (ORIGIN_X + dx, ORIGIN_Y + dy)


# ---------------------------------------------------------------------------
# The network
# ---------------------------------------------------------------------------
# A short street running east, with a spur north. Coordinates are projected
# metres; at this latitude the true ground length is about 0.735 of the drawn
# figure, which is why the stored lengths below are not the plan distances.

ROUTE_MAIN_A = [_p(0, 0), _p(120, 0)]
ROUTE_MAIN_B = [_p(120, 0), _p(280, 0)]
ROUTE_SPUR = [_p(120, 0), _p(120, 200)]

CABLE_BACKBONE = [_p(0, 0), _p(120, 0), _p(280, 0)]
CABLE_DISTRIBUTION = [_p(120, 0), _p(120, 200)]
#: Deliberately stranded -- nothing else reaches it (fault A1).
CABLE_STRANDED = [_p(360, 90), _p(430, 90)]
#: Starts 7 m from the pole at (280, 0): past the 5 m tolerance, inside 2x it, so
#: A2 calls it a near miss (fault A2). Its far end lands exactly on JC-2, so the
#: cable contributes one dangling endpoint rather than two.
CABLE_NEAR_MISS = [_p(287, 0), _p(287, -60)]

POLE_POSITIONS = [_p(0, 0), _p(120, 0), _p(280, 0)]
#: 45 m clear of every line (fault A3).
POLE_ORPHAN = _p(200, 45)
#: Shares POLE_POSITIONS[0]'s identity (fault B4) and sits on it, so it is
#: attached and only B4 has anything to say about it.
POLE_TWIN = _p(0, 0)

MANHOLE_POSITIONS = [_p(120, 0), _p(120, 200)]

#: Terminates CABLE_NEAR_MISS, so that cable's far end is properly connected.
JOINT_CLOSURE_POSITIONS = [_p(120, 0), _p(287, -60)]

#: On route R-1, but recorded against the Route layer instead of a cable (B2).
FIBER_BREAK_POSITION = _p(60, 0)

#: Names UC-1, which exists, but sits 80 m off it (fault B3).
SLACK_STALE = _p(60, 80)


def _ground_length(points):
    """Ellipsoidal length of a projected polyline, without importing QGIS.

    Web Mercator's scale factor is 1/cos(latitude), and latitude follows from the
    northing. Accurate enough for a fixture; the plugin uses QgsDistanceArea.
    """
    import math

    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        planar = math.hypot(x2 - x1, y2 - y1)
        mid_y = (y1 + y2) / 2.0
        lat = 2 * math.atan(math.exp(mid_y / 6378137.0)) - math.pi / 2
        total += planar * math.cos(lat)
    return total


def _uuid(n: int) -> str:
    """A stable, obviously-synthetic UUID. Deterministic by design."""
    return f"fe1b0000-0000-4000-8000-{n:012d}"


#: Held by two poles at once (fault B4). Numbered far above the sequential ids
#: so it can never collide with an auto-assigned one.
_TWIN_UUID = _uuid(900)


def _rows():
    """Every feature to write, as ``{layer: [(geometry, attributes), ...]}``.

    Attributes are given by field key; anything omitted is left NULL, which is
    how the C1 fault is planted.
    """
    n = iter(range(1, 500))

    def uid():
        return _uuid(next(n))

    routes = [
        (ROUTE_MAIN_A, {"naziv": "R-1", "tip_trase": "Underground",
                        "duzina": _ground_length(ROUTE_MAIN_A),
                        "duzina_km": round(_ground_length(ROUTE_MAIN_A) / 1000, 2)}),
        (ROUTE_MAIN_B, {"naziv": "R-2", "tip_trase": "Underground",
                        "duzina": _ground_length(ROUTE_MAIN_B),
                        "duzina_km": round(_ground_length(ROUTE_MAIN_B) / 1000, 2)}),
        # Fault D3: a stale length, as if the geometry was edited afterwards.
        (ROUTE_SPUR, {"naziv": "R-3", "tip_trase": "Aerial",
                      "duzina": 210.0, "duzina_km": 0.21}),
    ]

    underground = [
        (CABLE_BACKBONE, {"naziv": "UC-1", "tip": "Optical", "podtip": "Backbone",
                          "stanje_kabla": "Existing", "broj_vlakana": 48,
                          "duzina_m": _ground_length(CABLE_BACKBONE),
                          "slack_m": 0.0,
                          "total_len_m": _ground_length(CABLE_BACKBONE)}),
        # Faults C1 (no tip) and D1 (status outside the domain).
        (CABLE_DISTRIBUTION, {"naziv": "UC-2", "podtip": "Distribution",
                              "stanje_kabla": "Someday", "broj_vlakana": 24,
                              "duzina_m": _ground_length(CABLE_DISTRIBUTION),
                              "slack_m": 0.0,
                              "total_len_m": _ground_length(CABLE_DISTRIBUTION)}),
    ]

    aerial = [
        # Faults A1 (stranded) and D2 (implausible fibre count).
        (CABLE_STRANDED, {"naziv": "AC-2", "tip": "Optical", "podtip": "Drop",
                          "stanje_kabla": "Planned", "broj_vlakana": 9999,
                          "duzina_m": _ground_length(CABLE_STRANDED),
                          "slack_m": 0.0,
                          "total_len_m": _ground_length(CABLE_STRANDED)}),
        # Fault A2: one end just outside snapping tolerance.
        (CABLE_NEAR_MISS, {"naziv": "AC-3", "tip": "Optical", "podtip": "Drop",
                           "stanje_kabla": "Planned", "broj_vlakana": 12,
                           "duzina_m": _ground_length(CABLE_NEAR_MISS),
                           "slack_m": 0.0,
                           "total_len_m": _ground_length(CABLE_NEAR_MISS)}),
    ]

    # Poles and manholes have no free-text name field in the schema, so the
    # demo identifies them by feature id rather than inventing a column.
    poles = [(pt, {"tip": "Pole"}) for pt in POLE_POSITIONS]
    # Fault B4: one identity on two poles. Both ends of the duplication are
    # written explicitly -- deriving one from a positional index would silently
    # re-pair it with whatever layer happens to be numbered there.
    poles[0][1][schema.IDENTITY_FIELD] = _TWIN_UUID
    poles.append((POLE_ORPHAN, {"tip": "Pole"}))    # fault A3
    poles.append((None, {"tip": "Pole"}))           # fault E2: no geometry
    poles.append((POLE_TWIN, {"tip": "Pole", schema.IDENTITY_FIELD: _TWIN_UUID}))

    manholes = [(pt, {"tip": "Manhole"}) for pt in MANHOLE_POSITIONS]

    joint_closures = [(pt, {"naziv": f"JC-{i}"})
                      for i, pt in enumerate(JOINT_CLOSURE_POSITIONS, start=1)]

    slacks = [
        (_p(60, 0), {"napomena": "SL-1", "duzina_m": 15.0, "cable_fid": 1,
                     "cable_layer_id": CABLE_LAYER_PLACEHOLDER}),
        # Fault B1: points at a cable that was never created.
        (_p(120, 100), {"napomena": "SL-2", "duzina_m": 15.0, "cable_fid": 999,
                        "cable_layer_id": "no-such-layer-id"}),
        # Fault B3: names UC-1, which exists, but sits 80 m off it.
        (SLACK_STALE, {"napomena": "SL-3", "duzina_m": 15.0, "cable_fid": 1,
                       "cable_layer_id": CABLE_LAYER_PLACEHOLDER}),
    ]

    # Fault B2: a break recorded against the Route layer. Like SL-1 and SL-3 the
    # layer id is patched in once a project exists; unlike them the target is
    # Route, which is the whole point.
    fiber_breaks = [
        (FIBER_BREAK_POSITION, {"naziv": "FB-1", "distance_m": 60.0,
                                "cable_fid": 1,
                                "cable_layer_id": CABLE_LAYER_PLACEHOLDER}),
    ]

    data = {
        "Route": routes,
        "Underground cables": underground,
        "Aerial cables": aerial,
        "Poles": poles,
        "Manholes": manholes,
        "Joint Closures": joint_closures,
        "Optical slack": slacks,
        "Fiber break": fiber_breaks,
    }

    # Identity is not optional -- B4 is an ERROR rule, and a demo that trips it
    # would be teaching the wrong lesson.
    for features in data.values():
        for _, attrs in features:
            attrs.setdefault(schema.IDENTITY_FIELD, uid())
    return data


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _wkt(geometry_type, coords):
    if geometry_type == "Point":
        return f"POINT({coords[0]} {coords[1]})"
    pairs = ", ".join(f"{x} {y}" for x, y in coords)
    return f"LINESTRING({pairs})"


def build_demo_gpkg(path: str) -> str:
    """Write the demo GeoPackage to ``path``, replacing any existing file."""
    from osgeo import ogr, osr

    ogr.UseExceptions()
    if os.path.exists(path):
        os.remove(path)

    driver = ogr.GetDriverByName("GPKG")
    source = driver.CreateDataSource(path)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(EPSG)

    for layer_name, features in _rows().items():
        layer_schema = schema.LAYER_SCHEMAS[layer_name]
        geom_type = getattr(ogr, _OGR_GEOM[layer_schema.geometry])
        # GeoPackage table names cannot contain spaces in every reader; the
        # plugin resolves the canonical name from the layer name, not the table.
        table = layer_name.replace(" ", "_")
        layer = source.CreateLayer(table, srs, geom_type)

        for field_def in layer_schema.fields:
            ogr_type = getattr(ogr, _OGR_TYPE.get(field_def.field_type, "OFTString"))
            layer.CreateField(ogr.FieldDefn(field_def.key, ogr_type))

        for coords, attrs in features:
            feature = ogr.Feature(layer.GetLayerDefn())
            for key, value in attrs.items():
                if layer.GetLayerDefn().GetFieldIndex(key) >= 0:
                    feature.SetField(key, value)
            # ``None`` means write the row with no geometry at all, which is what
            # an attribute-table edit leaves behind and what E2 exists to catch.
            if coords is not None:
                feature.SetGeometry(ogr.CreateGeometryFromWkt(
                    _wkt(layer_schema.geometry, coords)))
            layer.CreateFeature(feature)
            feature = None

        layer = None

    source = None

    # The schema-version marker, written the same way ExportManager does.
    # `with sqlite3.connect(...)` commits but does not close, and an open handle
    # on a GeoPackage that QGIS is about to read is asking for trouble.
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS _fiberq_metadata "
                "(key TEXT PRIMARY KEY, value TEXT)")
            connection.execute(
                "INSERT OR REPLACE INTO _fiberq_metadata (key, value) VALUES (?, ?)",
                ("schema_version", schema.SCHEMA_VERSION))
    finally:
        connection.close()
    return path


def load_demo_layers(gpkg_path, project=None):
    """Load the demo GeoPackage into a ``QgsProject`` under canonical layer names.

    The GeoPackage stores tables with underscores (``Optical_slack``) because not
    every reader copes with spaces; the plugin resolves layers by their *layer*
    name, so they are renamed on load. Needs QGIS.
    """
    from osgeo import ogr
    from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer

    project = project or QgsProject.instance()
    project.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{EPSG}"))
    # setEllipsoid is a no-op until the CRS is set, and without it every length
    # would be measured in map units -- the exact bug D3 exists to catch.
    project.setEllipsoid("EPSG:7030")

    ogr.UseExceptions()
    source = ogr.Open(gpkg_path)
    tables = [source.GetLayer(i).GetName() for i in range(source.GetLayerCount())]
    source = None

    loaded = {}
    for table in tables:
        name = table.replace("_", " ")
        layer = QgsVectorLayer(f"{gpkg_path}|layername={table}", name, "ogr")
        if layer.isValid():
            project.addMapLayer(layer)
            loaded[name] = layer
    return loaded


def build_demo_project(gpkg_path, qgz_path):
    """Write a QGIS project alongside the GeoPackage, with a working slack link.

    ``cable_layer_id`` holds a runtime QGIS layer id, so a GeoPackage on its own
    cannot express a *valid* cable reference -- only a broken one. Writing the
    project lets slack SL-1 point at a real layer, which is what makes B1's single
    finding on SL-2 meaningful rather than the rule simply failing on everything.

    Needs QGIS. Returns the project path.
    """
    from qgis.core import QgsProject

    from fiberq.core.schema_version import mark_project_current

    project = QgsProject()
    layers = load_demo_layers(gpkg_path, project)

    # The schema version lives in a project entry, not in the GeoPackage, so a
    # project assembled programmatically reads as the pre-1.0 baseline. Stamping
    # it is what the plugin does on save; without it the sample report would tell
    # readers the demo needs migrating.
    mark_project_current(project)

    # Which feature points at which layer. The note/name field identifies the
    # row, because feature ids are the provider's business and the target layer
    # differs per fault -- SL-1 and SL-3 name a cable, FB-1 names Route, and that
    # mismatch is fault B2.
    _relink(layers, "Optical slack", "napomena", "SL-1", "Underground cables")
    _relink(layers, "Optical slack", "napomena", "SL-3", "Underground cables")
    _relink(layers, "Fiber break", "naziv", "FB-1", "Route")

    _set_view_extent(project, layers.values())
    project.write(qgz_path)
    return qgz_path


def _relink(layers, layer_name, key_field, key_value, target_layer_name):
    """Point one feature's ``cable_layer_id`` at a live layer id.

    A GeoPackage cannot express a *valid* reference on its own -- the value is a
    runtime QGIS layer id -- so the placeholder written into the file is filled
    in here, once the project exists.
    """
    layer = layers.get(layer_name)
    target = layers.get(target_layer_name)
    if layer is None or target is None:
        return False
    index = layer.fields().indexFromName("cable_layer_id")
    if index < 0:
        return False
    fid = next((f.id() for f in layer.getFeatures()
                if f.attribute(key_field) == key_value), None)
    if fid is None:
        return False
    layer.startEditing()
    layer.changeAttributeValue(fid, index, target.id())
    return bool(layer.commitChanges())


def _set_view_extent(project, layers):
    """Save the canvas extent, so the demo opens on the network.

    A project written headlessly has never had a canvas, so QGIS stores no
    ``<mapcanvas>`` and opens the demo on a blank white map -- which reads as a
    broken sample to anyone we hand it to. The union of the layer extents,
    padded, is what "Zoom to all layers" would give.

    Degenerate extents are normal here (a single joint closure is a point; the
    stranded cable runs due east) so the union is grown by an absolute margin
    rather than a percentage, which would be zero on a flat side.
    """
    from qgis.core import (QgsCoordinateReferenceSystem, QgsRectangle,
                           QgsReferencedRectangle)

    extent = QgsRectangle()
    extent.setNull()
    for layer in layers:
        rect = layer.extent()
        if not rect.isNull():
            extent.combineExtentWith(rect)
    if extent.isNull():
        return
    extent.grow(40.0)  # metres of the projected CRS
    project.viewSettings().setDefaultViewExtent(
        QgsReferencedRectangle(extent, QgsCoordinateReferenceSystem(f"EPSG:{EPSG}")))


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    out = argv[1] if len(argv) > 1 else os.path.join(here, "demo_project.gpkg")
    build_demo_gpkg(out)
    print(f"Wrote {out}")

    qgz = os.path.splitext(out)[0] + ".qgz"
    try:
        build_demo_project(out, qgz)
        print(f"Wrote {qgz}")
    except ImportError:
        print("QGIS not available -- GeoPackage written without a project file")
    print(f"Planted faults: {', '.join(sorted(FAULTS))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
