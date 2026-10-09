#!/usr/bin/env python3
"""Generate a seeded, city-sized FiberQ project for the WP4 benchmark.

The other two fixtures answer different questions. ``make_demo_project.py`` is a
worked example small enough to check by hand, with faults planted on purpose.
``make_scale_project.py`` is WP2's validator fixture: four layers in
disconnected rows, calibrated to its own ratio test, with no slack, elements or
cross streets -- so it cannot exercise routing, slack placement or the schematic
view. This is the third: a *connected* network big enough to measure, with every
layer type the plugin knows about, and clean enough that a finding is a real
regression.

What "clean" means here, and why it matters: the benchmark compares v1.5.0
against v1.6.0 on this dataset, so a scenario's cost must come from the code
under test and not from the data. A dataset that trips a rule, or that stores a
planar length where the plugin stores a ground length, measures the fixture
rather than the plugin. ``run_validation()`` therefore reports zero issues at
every size from XS to L -- measured, not assumed -- and the XS run is asserted
in CI, together with the manifest digest below.

    seed 20260921, size XS, default names:
    29b868715a0a37204df689eaa60d97e61eb17454e5a62af17397aed81bb462ab

Deterministic by construction. The street graph, the laying types, the jitter
and every placement come from one ``random.Random(seed)``; coordinates and
stored lengths are rounded before they are written. Two runs of the same size
and seed produce identical *content* -- the manifest digest is taken over the
rows and the project entries, not over the file, because GeoPackage stamps
``gpkg_contents.last_change`` once per table and GDAL writes header fields of
its own (75 of the 1,048,576 bytes of an XS file differ between two otherwise
identical runs, measured on 3.44). The *table* content, geometry blobs
included, does come out identical on both CI images -- but that is GDAL's
doing, and both images happen to ship GDAL 3.10.3, so it is a measurement and
not a guarantee. Generate each dataset once and keep it, as the WP4 plan says.

Layer rosters come from ``fiberq.models.schema``, never from a hand-copied list,
so the fixture cannot drift away from the real data model. Values are the ones
the *tools* store, not the English labels the dialogs show: ``tip_trase
podzemna``, ``podtip glavni``, ``cable_laying Podzemno``.

Usage:
    python tests/fixtures/make_city_project.py --size XS
    python tests/fixtures/make_city_project.py --size S --out /tmp/s/city_S.gpkg
    python tests/fixtures/make_city_project.py --size XS --legacy-names

``manifest.json`` is written beside the dataset under that fixed name, so give
each size a directory of its own -- which is what ``--out`` defaults to. Two
datasets in one directory would leave a single manifest claiming to describe
both; the harness refuses such a directory outright rather than guessing
(``tools/bench/bench_common.dataset_files``).

Sizes, as the WP4 plan budgets them:

    XS   n=12    144 intersections    ~2k features    CI
    XS4  n=24    576                  ~8k             CI ratio partner
    S    n=32   1024                 ~14k             benchmark + manual QA
    M    n=50   2500                 ~35k             benchmark
    L    n=80   6400                 ~90k             benchmark (overnight)

Nothing is written into the repository: ``--out`` defaults under the system
temporary directory, because an L dataset is ~20 MB of GeoPackage and
``.gitignore`` matches neither ``*.gpkg`` nor ``*.qgz``.

This module deliberately does **not** touch ``sys.path`` at import time (the
other two fixtures do). A benchmark worker puts the code tree under test first
on ``sys.path`` and then asserts where ``fiberq`` was imported from; a fixture
that inserted the repository root on import would silently hand the "before"
run the "after" code. ``main()`` does the insert, once, for command-line use.
The same rule is why ``_ground_length`` / ``_uuid`` / ``_wkt`` are
re-implemented here rather than imported from ``make_demo_project``: importing
that module runs its ``sys.path`` insert.
"""
import argparse
import hashlib
import heapq
import json
import math
import os
import random
import sqlite3
import sys
import tempfile

#: Default seed. Fixed so the dataset is a constant of the benchmark rather
#: than a variable of it; the manifest records it either way.
DEFAULT_SEED = 20260921

#: Web Mercator, because that is what a basemap-traced design really uses, and
#: it is where the length rules have something to say (the scale factor at this
#: latitude is ~1.38x, so a planar length is 38% wrong).
EPSG = 3857

#: The same quiet corner of the Adriatic the demo project uses.
ORIGIN_X, ORIGIN_Y = 1_900_000.0, 5_400_000.0

#: ``--size`` -> n, the side of the n x n grid of intersections.
SIZES = {"XS": 12, "XS4": 24, "S": 32, "M": 50, "L": 80}

#: Nominal city block, in projected metres (~80 m of ground at this latitude).
BLOCK = 110.0

#: Each intersection is displaced by up to this much on both axes, so nothing
#: lands on a round number and every length is distinct. Kept well below
#: BLOCK/2 so streets cannot cross each other.
NODE_JITTER = 11.0

#: Perpendicular displacement of a street's middle vertex. Routes are 3-vertex
#: on purpose: a 2-vertex grid would let a cable retrace a straight line
#: without GEOS noticing, and real trenches bend around things.
BEND = 7.0

#: Share of streets left out of the graph. Keeps cycles and cross streets, so
#: routing has real alternatives rather than one possible answer.
EDGE_DROP = 0.08

#: Share of streets dug rather than strung. Drives manholes vs poles, the route
#: type, and which cable layer a cable lands in.
UNDERGROUND_SHARE = 0.60

#: Share of dug streets that also carry a transition duct.
TRANSITION_SHARE = 0.75

#: Coordinates and stored lengths are rounded to this many decimals before
#: being written, so a 1-ULP difference in libm between two QGIS images cannot
#: move the manifest digest.
PRECISION = 3

#: Grid period of the ODF sites, the joint closures and the service areas, in
#: intersections. An ODF therefore shares no node with a closure it feeds
#: (ODF_STEP is a multiple of CLOSURE_STEP, so the closure on its own node is
#: skipped -- otherwise the backbone cable would be zero-length), and every
#: size from XS up has at least one of each.
ODF_STEP = 12
CLOSURE_STEP = 4
AREA_STEP = 2

#: Name prefixes, so a feature's ``naziv`` says what it is.
PREFIXES = {
    "ODF": "ODF", "TB": "TB", "Patch panel": "PP", "OTB": "OTB",
    "Indoor OTB": "IOTB", "Outdoor OTB": "OOTB", "Pole OTB": "POTB",
    "TO": "TO", "Indoor TO": "ITO", "Outdoor TO": "OTO", "Pole TO": "PTO",
    "Joint Closure TO": "JCTO",
}

#: The eight element layers with no bulk rule of their own. They are scattered
#: along the component so their counts grow with n; the guaranteed-seed pass is
#: what makes sure each one is non-empty even at XS.
SPARSE_ELEMENT_LAYERS = (
    "TB", "Patch panel", "OTB", "Indoor OTB",
    "Pole OTB", "TO", "Indoor TO", "Joint Closure TO",
)

#: One sparse element every this many nodes of the largest component.
SPARSE_STEP = 11

#: Cable-index periods for the features hung off a cable. Chosen so XS gets a
#: handful of each and L stays in the proportions of the prototype dataset the
#: WP4 plan sizes against (1 break at XS, ~33 at L).
SLACK_EVERY = 4
MIDSPAN_EVERY = 16
BREAK_EVERY = 400
LATENT_EVERY = 97

#: Metres of slack stored per loop, and the cap on cables per relation.
SLACK_LENGTH = 20.0
RELATION_CABLES = 4

#: Project entry scope and keys. ``StuboviPlugin`` is historical branding and is
#: still what the readers use (core/data_manager.py:30-38,
#: core/relations_manager.py:33-34). The schema marker is written through
#: core.schema_version instead, which owns its own scope and key.
LEGACY_SCOPE = "StuboviPlugin"
RELATIONS_KEY = "Relacije/relations_v1"
LATENT_KEY = "LatentElements/latent_v1"
COLOR_CATALOGS_KEY = "ColorCatalogs/catalogs_v1"

#: Relation categories the dialog's combo box offers (utils/legacy_bridge.py).
RELATION_CATEGORIES = ("Main", "Local", "International", "Metro network",
                       "Regional")

#: The TIA-598-C twelve, as core/data_manager.get_default_color_sets() builds
#: them. Copied rather than imported: that module needs QGIS, and the
#: GeoPackage half of this fixture does not.
TIA_598_C = (
    ("Blue", "#1f77b4"), ("Orange", "#ff7f0e"), ("Green", "#2ca02c"),
    ("Brown", "#8c564b"), ("Slate", "#7f7f7f"), ("White", "#ffffff"),
    ("Red", "#d62728"), ("Black", "#000000"), ("Yellow", "#bcbd22"),
    ("Violet", "#9467bd"), ("Pink", "#e377c2"), ("Aqua", "#17becf"),
)

#: Fixed timestamps for the ``created_at`` / ``vreme`` columns. Reading the
#: clock would put the one non-reproducible value in the dataset into the
#: digest.
FIXED_TIMESTAMP = "2026-09-21 09:00"
FIXED_ISO_TIMESTAMP = "2026-09-21T09:00:00Z"

#: Layer names as the *plugin* creates them, where that differs from the
#: canonical name. The slack layer is the load-bearing one: every real v1.5.0
#: project holds "Optical slacks" (core/layer_manager.py:1057), while Delete
#: selected only looks for the singular (main_plugin.py:3127). A fixture using
#: the canonical name would quietly not reproduce that.
AS_CREATED_LAYER_NAMES = {"Optical slack": "Optical slacks"}

#: ``--legacy-names``: the pre-1.0 Serbian names, taken from
#: schema.LAYER_NAME_ALIASES so they still resolve to their canonical layer.
#: The twelve element layers are absent on purpose -- the alias map lists no
#: Serbian name for them.
LEGACY_LAYER_NAMES = {
    "Joint Closures": "Nastavci",
    "Poles": "Stubovi",
    "Manholes": "OKNA",
    "Route": "Trasa",
    "Optical slack": "Opticke_rezerve",
    "PE pipes": "PE cevi",
    "Transition pipes": "Prelazne cevi",
    "Service Area": "Rejon",
    "Objects": "Objekti",
    "Aerial cables": "Kablovi_vazdusni",
    "Underground cables": "Kablovi_podzemni",
    "Fiber break": "Prekid vlakna",
}

#: ``--legacy-names``: the three stored *field* names a pre-1.0 project carries,
#: as core/interchange_fields.LEGACY_FIELD_NAMES records them. These are the
#: columns the slack/break link and the cable-laying migration read through
#: aliases, and the ones WP4-FU-2b's crashes hang off.
LEGACY_FIELD_NAMES = {
    "cable_layer_id": "kabl_layer_id",
    "cable_fid": "kabl_fid",
    "cable_laying": "polaganje_kabla",
}

#: Logical field type -> OGR field-type attribute name, resolved lazily so this
#: module imports without GDAL.
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

#: First explicit feature id. Benchmark scenarios store ``cable_fid`` foreign
#: keys, so the fids have to be ours rather than the provider's; starting well
#: above 1 makes an accidentally renumbered layer obvious at a glance.
FIRST_FID = 1000

#: Dijkstra's "not reached yet".
_INFINITY = float("inf")


# ---------------------------------------------------------------------------
# Seeded helpers -- only random() is used
# ---------------------------------------------------------------------------
# randint/choice/sample/shuffle happen to agree across the two QGIS images
# today (both run CPython 3.13.5), but none of them carries a cross-version
# guarantee and the image tags float across point releases. random() does.

def _jitter(rnd, span):
    """A displacement in ``[-span, +span]``."""
    return (rnd.random() * 2.0 - 1.0) * span


def _r(value):
    """Round to the dataset's coordinate/length precision."""
    return round(value, PRECISION)


def _uuid(n):
    """A stable, obviously-synthetic UUID.

    One counter for the whole project, not one per layer: B4 reports a
    duplicate identity across layers, not only within one.
    """
    return f"c1700000-0000-4000-8000-{n:012d}"


def _ground_length(points):
    """Ellipsoidal length of a projected polyline, without importing QGIS.

    Web Mercator's scale factor is 1/cos(latitude), and latitude follows from
    the northing. Agrees with ``QgsDistanceArea`` to ~0.2% here -- the
    difference is the ellipsoid's radius of curvature versus the sphere's --
    which is well inside D3's 1% tolerance. The plugin itself measures with
    QgsDistanceArea; storing ``QgsGeometry.length()`` instead is the exact bug
    D3 exists to catch, and at this latitude it would be 38% out.
    """
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        planar = math.hypot(x2 - x1, y2 - y1)
        lat = _latitude((y1 + y2) / 2.0)
        total += planar * math.cos(lat)
    return total


def _latitude(y):
    """Geodetic latitude, in radians, of a Web Mercator northing."""
    return 2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2


def _wkt(geometry, coords):
    """WKT for one row. ``coords`` is a point, a vertex list or a closed ring.

    The string is built once and then used by *both* the GeoPackage writer and
    the digest, so the two cannot disagree about what was written.
    """
    if geometry == "Point":
        return f"POINT({coords[0]} {coords[1]})"
    pairs = ", ".join(f"{x} {y}" for x, y in coords)
    if geometry == "Polygon":
        return f"POLYGON(({pairs}))"
    return f"LINESTRING({pairs})"


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def layer_names(legacy=False):
    """``{canonical layer name: the name this dataset gives it}``.

    Needs the schema, so it is imported here rather than at module scope.
    """
    from fiberq.models import schema

    out = {}
    for canonical in schema.LAYER_SCHEMAS:
        if legacy:
            out[canonical] = LEGACY_LAYER_NAMES.get(canonical, canonical)
        else:
            out[canonical] = AS_CREATED_LAYER_NAMES.get(canonical, canonical)
    return out


def table_name(name):
    """The GeoPackage table for a layer name. Spaces are not portable."""
    return name.replace(" ", "_")


def layer_id(name):
    """The fixed QGIS layer id for a layer name.

    Fixed ids are what let the ``cable_layer_id`` references live in the
    GeoPackage instead of being patched in after load, and what lets a
    benchmark scenario name a layer without first searching the project.
    ``setId()`` only works *before* ``addMapLayer()``; see :func:`build_project`.
    """
    return f"fiberq_bench_{table_name(name)}"


def field_key(key, legacy=False):
    """The stored column name for a canonical field key."""
    return LEGACY_FIELD_NAMES.get(key, key) if legacy else key


# ---------------------------------------------------------------------------
# The street graph
# ---------------------------------------------------------------------------

def _street_graph(n, rnd):
    """``(nodes, edges, adjacency)`` for an n x n grid of jittered streets.

    ``nodes`` maps ``(i, j)`` to ``(x, y)``; each edge is a dict with ``id``,
    ``a``, ``b``, ``pts`` (3 vertices), ``mid``, ``laying`` and ``len`` (ground
    metres).
    """
    nodes = {}
    for j in range(n):
        for i in range(n):
            x = ORIGIN_X + i * BLOCK + _jitter(rnd, NODE_JITTER)
            y = ORIGIN_Y + j * BLOCK + _jitter(rnd, NODE_JITTER)
            nodes[(i, j)] = (_r(x), _r(y))

    edges = []
    for j in range(n):
        for i in range(n):
            for a, b in (((i, j), (i + 1, j)), ((i, j), (i, j + 1))):
                if b not in nodes:
                    continue
                if rnd.random() < EDGE_DROP:
                    continue
                laying = "underground"
                if rnd.random() >= UNDERGROUND_SHARE:
                    laying = "aerial"
                edges.append(_street(len(edges), a, b, nodes, laying, rnd))

    adjacency = {}
    for edge in edges:
        adjacency.setdefault(edge["a"], []).append(edge)
        adjacency.setdefault(edge["b"], []).append(edge)
    return nodes, edges, adjacency


def _street(index, a, b, nodes, laying, rnd):
    """One street: three vertices, the middle one pushed off the straight line."""
    x1, y1 = nodes[a]
    x2, y2 = nodes[b]
    dx = x2 - x1
    dy = y2 - y1
    span = math.hypot(dx, dy) or 1.0
    off = _jitter(rnd, BEND)
    mid_x = (x1 + x2) / 2.0 - dy / span * off
    mid_y = (y1 + y2) / 2.0 + dx / span * off
    mid = (_r(mid_x), _r(mid_y))
    pts = [nodes[a], mid, nodes[b]]
    return {"id": index, "a": a, "b": b, "pts": pts, "mid": mid,
            "laying": laying, "len": _ground_length(pts)}


def _largest_component(nodes, adjacency):
    """The biggest connected set of intersections, as a sorted node list.

    Dropping streets can isolate a corner. Confining every element and every
    cable to one component means a shortest path always exists (so no cable is
    silently skipped) and every element sits on a street, which is what keeps
    A3 quiet.
    """
    seen = set()
    best = []
    for start in sorted(nodes):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        group = []
        while stack:
            node = stack.pop()
            group.append(node)
            for edge in adjacency.get(node, ()):
                other = edge["b"] if edge["a"] == node else edge["a"]
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        if len(group) > len(best):
            best = group
    return sorted(best)


def _shortest_path(adjacency, start, targets, blocked=None):
    """Streets of the cheapest route from ``start`` to any of ``targets``.

    A bounded Dijkstra: it returns as soon as one target is settled, so a drop
    cable costs a search of its own neighbourhood rather than of the whole
    city. ``blocked`` leaves one street out, which is what stops a drop from
    reaching its own street from the far end and then doubling back along the
    half it is about to use -- that retrace is not self-*intersecting*, so
    ``isGeosValid()`` passes it and only E2's ``isSimple()`` check objects.

    Returns ``(streets, arrival node)``, or ``None`` when nothing is reachable.
    """
    if start in targets:
        return [], start
    distance = {start: 0.0}
    came = {}
    heap = [(0.0, start)]
    while heap:
        cost, node = heapq.heappop(heap)
        if cost > distance.get(node, _INFINITY):
            continue        # a stale heap entry for an already-settled node
        if node in targets:
            return _unwind(came, start, node), node
        for edge in adjacency.get(node, ()):
            if edge["id"] == blocked:
                continue
            other = edge["b"] if edge["a"] == node else edge["a"]
            step = cost + edge["len"]
            if step < distance.get(other, _INFINITY):
                distance[other] = step
                came[other] = (node, edge)
                heapq.heappush(heap, (step, other))
    return None


def _unwind(came, start, node):
    """The street list from ``start`` to ``node``, in travel order."""
    path = []
    while node != start:
        node, edge = came[node]
        path.append(edge)
    path.reverse()
    return path


def _path_points(path, start, nodes):
    """Vertices of a street list walked from ``start``.

    The shared intersection is written once: a repeated vertex is a zero-length
    segment, which GEOS does not call simple.
    """
    node = start
    pts = [nodes[start]]
    for edge in path:
        forward = edge["a"] == node
        seq = edge["pts"] if forward else list(reversed(edge["pts"]))
        pts.extend(seq[1:])
        node = edge["b"] if forward else edge["a"]
    return pts


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------

class _Builder:
    """Accumulates rows, feature ids and identities for one dataset.

    A row is ``(fid, wkt, {canonical field key: value})``. Nothing here calls
    GDAL or a running QgsApplication, so the whole model can be built, hashed
    and compared from a plain interpreter -- though the QGIS bindings must be
    importable, because ``fiberq.models.__init__`` pulls them in.
    """

    def __init__(self, n, seed, legacy=False):
        from fiberq.models import schema

        self.schema = schema
        self.n = n
        self.seed = seed
        self.legacy = legacy
        self.rnd = random.Random(seed)
        self.names = layer_names(legacy)
        self.rows = {canonical: [] for canonical in schema.LAYER_SCHEMAS}
        self._fids = {canonical: FIRST_FID for canonical in schema.LAYER_SCHEMAS}
        self._labels = {canonical: 0 for canonical in schema.LAYER_SCHEMAS}
        self._uuid_n = 0
        self.relations = []
        self.latent = {}

    def add(self, canonical, coords, attrs):
        """Append one feature and return its explicit fid."""
        geometry = self.schema.LAYER_SCHEMAS[canonical].geometry
        fid = self._fids[canonical]
        self._fids[canonical] += 1
        self._uuid_n += 1
        attrs = dict(attrs)
        attrs[self.schema.IDENTITY_FIELD] = _uuid(self._uuid_n)
        self.rows[canonical].append((fid, _wkt(geometry, coords), attrs))
        return fid

    def label(self, canonical, prefix):
        """A per-layer running name, e.g. ``ODF-0003``."""
        self._labels[canonical] += 1
        return f"{prefix}-{self._labels[canonical]:04d}"

    def layer_id_of(self, canonical):
        """The fixed layer id this dataset gives a canonical layer."""
        return layer_id(self.names[canonical])

    def element(self, canonical, point, node, capacity=24):
        """One point element from the shared fifteen-field roster.

        ``kapacitet`` is written even though ``0`` would satisfy C1: a benchmark
        dataset that stores the schema default everywhere measures nothing about
        a real project's attribute table.
        """
        prefix = PREFIXES[canonical]
        name = self.label(canonical, prefix)
        self.add(canonical, point, {
            "naziv": name,
            "proizvodjac": "FiberQ Bench",
            "oznaka": f"{prefix}-{node[0]}-{node[1]}",
            "kapacitet": capacity,
            "ukupno_kj": 0,
            "zahtev_kapaciteta": 0,
            "zahtev_rezerve": 0,
            "oznaka_izvoda": "",
            "numeracija": "",
            "naziv_objekta": "",
            "adresa_ulica": f"Street {node[0]}",
            "adresa_broj": str(node[1] + 1),
            "address_id": "",
            "stanje": "Planned",
            "godina_ugradnje": 2025,
        })
        return name


def build_model(n, seed=DEFAULT_SEED, legacy=False):
    """Build the whole dataset in memory. Returns ``(rows, meta)``.

    ``rows`` is ``{canonical layer name: [(fid, wkt, attrs), ...]}``; ``meta``
    carries n, the seed, the per-layer counts, the project entries
    (``entry_rows``: relations, latent elements, colour catalogue) and the
    content digest over both halves. Needs ``fiberq.models.schema`` (and
    therefore the QGIS bindings, which that package imports), but no GDAL and
    no running QgsApplication.

    The order of the passes is load-bearing. Geometry first, then the lengths
    measured from it, then the slack rows, and only then the cables' ``slack_m``
    and ``total_len_m`` -- D3 compares all three against each other, so any
    other order makes the rule fire on data that is otherwise right.
    """
    build = _Builder(n, seed, legacy)
    nodes, edges, adjacency = _street_graph(n, build.rnd)
    component = _largest_component(nodes, adjacency)
    inside = set(component)
    streets = [edge for edge in edges if edge["a"] in inside]

    _add_routes(build, streets)
    _add_objects(build, streets)
    manholes, poles = _add_manholes_and_poles(build, streets, nodes)
    _add_pipes(build, streets)
    sites = _add_elements(build, nodes, streets, component, inside)
    cables = _add_cables(build, adjacency, nodes, sites)
    _add_slack_and_breaks(build, cables, manholes, poles)
    _finish_cables(build, cables)
    _add_relations(build, cables, sites)
    _add_latent(build, cables)

    counts = {name: len(rows) for name, rows in build.rows.items() if rows}
    # One object for the three project entries, so the digest and the ``.qgz``
    # cannot disagree about what the dataset contains -- the same reason
    # ``_wkt`` is shared between the GeoPackage writer and the digest.
    entries = {"relations": build.relations,
               "latent": build.latent,
               "catalogs": _color_catalogs()}
    meta = {
        "generator": os.path.basename(__file__),
        "n": n,
        "seed": seed,
        "legacy_names": bool(legacy),
        "crs": f"EPSG:{EPSG}",
        "schema_version": build.schema.SCHEMA_VERSION,
        "intersections": len(nodes),
        "component": len(component),
        "streets": len(streets),
        "cables": len(cables),
        "features": sum(counts.values()),
        "counts": counts,
        "layer_names": {key: build.names[key] for key in counts},
        "layer_ids": {key: layer_id(build.names[key]) for key in counts},
        "relations": len(build.relations),
        "latent_cables": len(build.latent),
        "entry_rows": entries,
        "digest": dataset_digest(build.rows, build.names, legacy, entries),
    }
    return build.rows, meta


def _add_routes(build, streets):
    """One Route per street, 60/40 by laying type."""
    for edge in streets:
        length = _r(edge["len"])
        kind = "podzemna" if edge["laying"] == "underground" else "vazdusna"
        build.add("Route", edge["pts"], {
            "naziv": build.label("Route", "R"),
            "duzina": length,
            "duzina_km": round(length / 1000.0, 2),
            "tip_trase": kind,
        })


def _add_objects(build, streets):
    """A building per street, set back from the kerb.

    Polygons are exempt from the topology rules but not from E2: the ring is
    convex, wound one way and closed explicitly, because a bow tie reports as
    "zero area" (the signed halves cancel) rather than as self-intersecting.
    """
    for edge in streets:
        (x1, y1), (x2, y2) = edge["pts"][0], edge["pts"][-1]
        span = math.hypot(x2 - x1, y2 - y1) or 1.0
        ux = (x2 - x1) / span
        uy = (y2 - y1) / span
        cx = (x1 + x2) / 2.0 - uy * 22.0
        cy = (y1 + y2) / 2.0 + ux * 22.0
        ring = []
        for along, across in ((-9.0, -7.0), (9.0, -7.0), (9.0, 7.0), (-9.0, 7.0)):
            ring.append((_r(cx + ux * along - uy * across),
                         _r(cy + uy * along + ux * across)))
        ring.append(ring[0])
        build.add("Objects", ring, {
            "tip": "residential",
            "spratova": 4,
            "podzemnih": 1,
            "ulica": f"Street {edge['a'][0]}",
            "broj": str(edge["a"][1] + 1),
            "naziv": build.label("Objects", "OBJ"),
            "napomena": "",
        })


def _add_manholes_and_poles(build, streets, nodes):
    """Manholes on the dug streets, poles on the strung ones.

    Returns the two point sets, which the slack pass reads to decide whether a
    loop is stored as sitting in a manhole, on a pole or in a building.
    """
    manhole_points = set()
    pole_points = set()
    pole_nodes = set()
    for edge in streets:
        if edge["laying"] == "underground":
            manhole_points.add(edge["mid"])
        else:
            pole_points.add(edge["mid"])
            pole_nodes.add(edge["a"])
            pole_nodes.add(edge["b"])

    for edge in streets:
        if edge["laying"] != "underground":
            continue
        build.add("Manholes", edge["mid"], {
            "broj_okna": build.label("Manholes", "MH"),
            "tip_okna": "cable",
            "vrsta_okna": "prefabricated",
            "polozaj_okna": "carriageway",
            "adresa": f"Street {edge['a'][0]}",
            "stanje": "Planned",
            "god_ugrad": 2025,
            "opis": "",
            "dimenzije": "120x80x100",
            "mat_zida": "concrete",
            "mat_poklop": "cast iron",
            "odvodnj": "yes",
            "poklop_tes": 1,
            "poklop_lak": 0,
            "br_nosaca": 2,
            "debl_zida": 12.0,
            "lestve": "no",
        })

    for point in sorted(pole_points):
        _add_pole(build, point)
    for node in sorted(pole_nodes):
        point = nodes[node]
        if point in pole_points:
            continue
        pole_points.add(point)
        _add_pole(build, point)
    return manhole_points, pole_points


def _add_pole(build, point):
    """One pole. ``visina`` must be > 0 or D2 reports it."""
    build.add("Poles", point, {
        "tip": "Pole",
        "podtip": "concrete",
        "visina": 9.0,
        "materijal": "concrete",
    })


def _add_pipes(build, streets):
    """A PE duct on every dug street, and a transition duct on most of them."""
    for edge in streets:
        if edge["laying"] != "underground":
            continue
        length = _r(edge["len"])
        ends = {"od": f"MH {edge['a'][0]}-{edge['a'][1]}",
                "do": f"MH {edge['b'][0]}-{edge['b'][1]}"}
        build.add("PE pipes", edge["pts"], dict(
            ends, materijal="PE", kapacitet="2x40", fi=40, duzina_m=length))
        if build.rnd.random() < TRANSITION_SHARE:
            build.add("Transition pipes", edge["pts"], dict(
                ends, materijal="PVC", kapacitet="1x110", fi=110,
                duzina_m=length))


def _add_elements(build, nodes, streets, component, inside):
    """Every element layer, plus the service areas, and who feeds whom.

    Returns the sites the cable pass reads: the head ends, the closures, the
    cabinets and the terminals, each as ``(node, point, name)``.
    """
    seeds = _seed_every_element_layer(build, nodes, component)
    head_ends = _add_head_ends(build, nodes, inside)
    closures = _add_closures(build, nodes, inside)
    areas, cabinets = _add_service_areas(build, nodes, inside)
    terminals = _add_terminals(build, streets)
    _add_sparse_elements(build, nodes, component)
    return {"seeds": seeds, "head_ends": head_ends, "closures": closures,
            "areas": areas, "cabinets": cabinets, "terminals": terminals}


def _seed_every_element_layer(build, nodes, component):
    """One feature in each of the twelve element layers, at every size.

    The bulk rules below are grid-periodic, so at XS several element layers
    would come out empty -- which the WP4 plan calls out as a defect of the
    prototype dataset, because a benchmark cannot report on a layer it never
    loaded. These sites are spread along the component by index, so they are
    deterministic, and they are intersections, which keeps A3 quiet.
    """
    names = build.schema.ELEMENT_LAYER_NAMES
    stride = max(1, len(component) // (len(names) + 1))
    seeds = []
    for index, canonical in enumerate(names):
        node = component[(index + 1) * stride % len(component)]
        name = build.element(canonical, nodes[node], node)
        seeds.append((node, nodes[node], name))
    return seeds


def _add_head_ends(build, nodes, inside):
    """The ODF sites, on a coarse grid."""
    out = []
    for node in sorted(inside):
        if node[0] % ODF_STEP or node[1] % ODF_STEP:
            continue
        name = build.element("ODF", nodes[node], node, capacity=48)
        out.append((node, nodes[node], name))
    return out


def _add_closures(build, nodes, inside):
    """Joint closures, on a finer grid than the ODFs."""
    out = []
    for node in sorted(inside):
        if node[0] % CLOSURE_STEP or node[1] % CLOSURE_STEP:
            continue
        name = build.label("Joint Closures", "JC")
        build.add("Joint Closures", nodes[node], {"naziv": name})
        out.append((node, nodes[node], name))
    return out


def _add_service_areas(build, nodes, inside):
    """A service area per superblock, with an outdoor cabinet at its centre."""
    areas = []
    cabinets = []
    span = AREA_STEP * BLOCK
    for cj in range(0, build.n - AREA_STEP, AREA_STEP):
        for ci in range(0, build.n - AREA_STEP, AREA_STEP):
            centre = (ci + 1, cj + 1)
            if centre not in inside:
                continue
            x0 = ORIGIN_X + ci * BLOCK - BLOCK / 2.0
            y0 = ORIGIN_Y + cj * BLOCK - BLOCK / 2.0
            ring = [(_r(x0), _r(y0)), (_r(x0 + span), _r(y0)),
                    (_r(x0 + span), _r(y0 + span)), (_r(x0), _r(y0 + span))]
            ring.append(ring[0])
            side = span * math.cos(_latitude(y0 + span / 2.0))
            fid = build.add("Service Area", ring, {
                "name": build.label("Service Area", "SA"),
                "created_at": FIXED_ISO_TIMESTAMP,
                "area_m2": _r(side * side),
                "perim_m": _r(4.0 * side),
                "count": 0,
            })
            cabinet = build.element("Outdoor OTB", nodes[centre], centre)
            areas.append({"fid": fid, "cabinet": cabinet})
            cabinets.append((centre, nodes[centre], cabinet))
    return areas, cabinets


def _add_terminals(build, streets):
    """A subscriber terminal on every street, at the street's middle vertex.

    The middle vertex, not a point part-way along a segment: a drop cable has
    to *end* on its terminal, and ending on a vertex the cable already walks to
    is what keeps the drop simple. The prototype dataset put the terminal past
    the vertex and produced 133 self-crossing drops at size S.
    """
    out = []
    for edge in streets:
        if edge["laying"] == "underground":
            canonical = "Outdoor TO"
        else:
            canonical = "Pole TO"
        name = build.element(canonical, edge["mid"], edge["a"], capacity=8)
        out.append({"edge": edge, "point": edge["mid"], "name": name})
    return out


def _add_sparse_elements(build, nodes, component):
    """The element layers with no bulk rule, scattered so they grow with n."""
    for step, index in enumerate(range(0, len(component), SPARSE_STEP)):
        node = component[index]
        canonical = SPARSE_ELEMENT_LAYERS[step % len(SPARSE_ELEMENT_LAYERS)]
        build.element(canonical, nodes[node], node)


# ---------------------------------------------------------------------------
# Cables
# ---------------------------------------------------------------------------

#: role -> (stored ``podtip``, fibre count, duct count). The codes are what the
#: cable dialog stores, not the English labels it shows.
CABLE_ROLES = {
    "backbone": ("glavni", 96, 4),
    "distribution": ("distributivni", 24, 2),
    "drop": ("razvodni", 12, 1),
}


def _add_cables(build, adjacency, nodes, sites):
    """Backbone, distribution and drop cables, each along a shortest path.

    A cable's layer is decided by the laying type of the majority of the streets
    it runs along, which is what the plugin's own Aerial/Underground split
    means. Returns the cable records the slack, break, relation and latent
    passes read.
    """
    cables = []
    closure_at = {node: name for node, _point, name in sites["closures"]}

    for node, _point, name in sites["head_ends"]:
        for target in _district_closures(node, closure_at):
            found = _shortest_path(adjacency, node, {target})
            if found is None:
                continue
            path, arrived = found
            if not path:
                continue
            pts = _path_points(path, node, nodes)
            _add_cable(build, cables, "backbone", path, pts, name,
                       closure_at[arrived])

    for node, _point, name in sites["cabinets"]:
        target = _nearest(node, closure_at)
        if target is None:
            continue
        found = _shortest_path(adjacency, node, {target})
        if found is None:
            continue
        path, arrived = found
        if not path:
            continue
        pts = _path_points(path, node, nodes)
        _add_cable(build, cables, "distribution", path, pts,
                   closure_at[arrived], name)

    served = _add_drops(build, cables, adjacency, nodes, sites)
    _fill_area_counts(build, sites, served)
    return cables


def _add_drops(build, cables, adjacency, nodes, sites):
    """One drop per terminal, from the cabinet of its own superblock.

    Returns ``{cabinet name: drops served}``, which the service areas record.
    """
    cabinet_by_cell = {}
    for node, point, name in sites["cabinets"]:
        cell = ((node[0] - 1) // AREA_STEP, (node[1] - 1) // AREA_STEP)
        cabinet_by_cell[cell] = (node, point, name)

    served = {}
    for terminal in sites["terminals"]:
        edge = terminal["edge"]
        cell = (edge["a"][0] // AREA_STEP, edge["a"][1] // AREA_STEP)
        cabinet = _nearest_cabinet(cell, cabinet_by_cell)
        if cabinet is None:
            continue
        start, _point, cabinet_name = cabinet
        found = _shortest_path(adjacency, start, {edge["a"], edge["b"]},
                               blocked=edge["id"])
        if found is None:
            continue
        path, _arrived = found
        pts = _path_points(path, start, nodes)
        pts.append(terminal["point"])
        _add_cable(build, cables, "drop", path + [edge], pts,
                   cabinet_name, terminal["name"])
        served[cabinet_name] = served.get(cabinet_name, 0) + 1
    return served


def _district_closures(node, closure_at):
    """The closures an ODF feeds: its own district, minus the one on its node."""
    reach = ODF_STEP // 2
    out = []
    for dj in range(-reach, reach + 1, CLOSURE_STEP):
        for di in range(-reach, reach + 1, CLOSURE_STEP):
            if not di and not dj:
                continue
            target = (node[0] + di, node[1] + dj)
            if target in closure_at:
                out.append(target)
    return out


def _nearest(node, candidates):
    """The grid-nearest member of ``candidates``, ties broken by node order."""
    best = None
    best_key = None
    for other in sorted(candidates):
        if other == node:
            continue
        key = abs(other[0] - node[0]) + abs(other[1] - node[1])
        if best_key is None or key < best_key:
            best_key = key
            best = other
    return best


def _nearest_cabinet(cell, cabinet_by_cell):
    """This superblock's cabinet, else the nearest one, searched in rings."""
    found = cabinet_by_cell.get(cell)
    if found is not None:
        return found
    for radius in range(1, 7):
        ring = []
        for dj in range(-radius, radius + 1):
            for di in range(-radius, radius + 1):
                if max(abs(di), abs(dj)) == radius:
                    ring.append((cell[0] + di, cell[1] + dj))
        for candidate in sorted(ring):
            found = cabinet_by_cell.get(candidate)
            if found is not None:
                return found
    return None


def _add_cable(build, cables, role, path, pts, from_name, to_name):
    """One cable row, in the layer its streets put it in."""
    podtip, fibres, ducts = CABLE_ROLES[role]
    aerial = sum(1 for edge in path if edge["laying"] == "aerial")
    if aerial * 2 > len(path):
        canonical, laying, prefix = "Aerial cables", "Vazdusno", "AC"
    else:
        canonical, laying, prefix = "Underground cables", "Podzemno", "UC"
    length = _r(_ground_length(pts))
    fid = build.add(canonical, pts, {
        "tip": "Optical",
        "podtip": podtip,
        "color_code": "TIA-598-C",
        "broj_cevcica": ducts,
        "broj_vlakana": fibres,
        "tip_kabla": "GYFTY",
        "vrsta_vlakana": "G.652.D",
        "vrsta_omotaca": "PE",
        "vrsta_armature": "none",
        "talasno_podrucje": "1310/1550",
        "naziv": build.label(canonical, prefix),
        "slabljenje_dbkm": 0.35,
        "hrom_disp_ps_nmxkm": 17.0,
        "stanje_kabla": "Projektovano",
        "cable_laying": laying,
        "vrsta_mreze": "FTTH",
        "godina_ugradnje": 2025,
        "konstr_vlakna_u_cevcicama": 1,
        "konstr_sa_uzlepljenim_elementom": 0,
        "konstr_punjeni_kabl": 1,
        "konstr_sa_arm_vlaknima": 0,
        "konstr_bez_metalnih": 1,
        "od": from_name,
        "do": to_name,
        "duzina_m": length,
        "slack_m": 0.0,
        "total_len_m": length,
        "fibers_per_tube": 12,
        "total_fibers": ducts * 12,
        "color_standard": "TIA-598-C",
    })
    cables.append({"layer": canonical, "fid": fid, "pts": pts, "role": role,
                   "length": length, "slack": 0.0, "from": from_name,
                   "to": to_name})


def _fill_area_counts(build, sites, served):
    """Write each service area's element count, now that the drops are known."""
    by_fid = {fid: attrs for fid, _wkt_text, attrs in build.rows["Service Area"]}
    for area in sites["areas"]:
        attrs = by_fid.get(area["fid"])
        if attrs is not None:
            attrs["count"] = served.get(area["cabinet"], 0) + 1


# ---------------------------------------------------------------------------
# Slack, breaks, project entries
# ---------------------------------------------------------------------------

def _add_slack_and_breaks(build, cables, manholes, poles):
    """Slack loops and fibre breaks, both on the cable they reference.

    ``cable_layer_id`` holds a runtime QGIS layer id, which is normally why a
    GeoPackage can express only a *broken* reference. Here the ids are fixed
    (``fiberq_bench_<table>``), so the real value is written into the file and
    the digest covers it -- no post-load edit session, and the reference is
    right the moment the project opens. :func:`build_project` asserts the id
    actually took.
    """
    for index, cable in enumerate(cables):
        if index % SLACK_EVERY == 0:
            _add_slack(build, cable, cable["pts"][0], "od", manholes, poles)
            _add_slack(build, cable, cable["pts"][-1], "do", manholes, poles)
        if index % MIDSPAN_EVERY == 0:
            middle = cable["pts"][len(cable["pts"]) // 2]
            _add_slack(build, cable, middle, "sredina", manholes, poles)
        if index % BREAK_EVERY == 0:
            _add_break(build, cable)


def _add_slack(build, cable, point, side, manholes, poles):
    """One slack loop, stored where ``slack_manager`` would store it.

    ``lokacija`` follows what is actually at the point, which is the same
    choice core/slack_manager.py:304-315 makes.
    """
    if point in manholes:
        location = "OKNO"
    elif point in poles:
        location = "Stub"
    else:
        location = "Objekat"
    build.add("Optical slack", point, {
        "tip": "Mid span" if side == "sredina" else "Terminal",
        "duzina_m": SLACK_LENGTH,
        "lokacija": location,
        "cable_layer_id": build.layer_id_of(cable["layer"]),
        "cable_fid": cable["fid"],
        "strana": side,
        "napomena": "",
    })
    cable["slack"] = cable["slack"] + SLACK_LENGTH


def _add_break(build, cable):
    """A fibre break, on a vertex of the cable it names.

    On a vertex rather than part-way along a segment: B3 measures the distance
    from the break to the cable it references, and a vertex is exactly zero
    away from it whatever the segment does.
    """
    pts = cable["pts"]
    cut = max(1, int(len(pts) * 0.4))
    build.add("Fiber break", pts[cut], {
        "naziv": "Fiber break",
        "cable_layer_id": build.layer_id_of(cable["layer"]),
        "cable_fid": cable["fid"],
        "distance_m": _r(_ground_length(pts[:cut + 1])),
        "segments_hit": 1,
        "vreme": FIXED_TIMESTAMP,
    })


def _finish_cables(build, cables):
    """Fold the slack totals back into the cables.

    D3 checks ``total_len_m == duzina_m + slack_m`` with ``slack_m`` the sum of
    that cable's loops -- the same arithmetic ``slack_manager`` applies when it
    recomputes a cable. It can only be done once every loop exists.
    """
    by_key = {}
    for cable in cables:
        by_key[(cable["layer"], cable["fid"])] = cable
    for canonical in ("Aerial cables", "Underground cables"):
        for fid, _wkt_text, attrs in build.rows[canonical]:
            cable = by_key.get((canonical, fid))
            if cable is None:
                continue
            attrs["slack_m"] = _r(cable["slack"])
            attrs["total_len_m"] = _r(cable["length"] + cable["slack"])


def _add_relations(build, cables, sites):
    """One relation per joint closure, naming the cables that reach it.

    ``id`` is a string: the dialog writes ``str(uuid4())``
    (dialogs/relations_dialog.py:67-74) while the unused
    ``RelationsManager.add_relation`` would write ``max(ids) + 1``, and every
    reader only compares for equality. ``cables`` entries are exactly
    ``{"layer_id": str, "fid": int}`` because three readers call ``int(fid)``
    unguarded.
    """
    by_endpoint = {}
    for cable in cables:
        for name in (cable["from"], cable["to"]):
            by_endpoint.setdefault(name, []).append(cable)
    for index, site in enumerate(sites["closures"], start=1):
        members = by_endpoint.get(site[2], [])[:RELATION_CABLES]
        build.relations.append({
            "id": f"r-{index:05d}",
            "name": f"REL-{index:04d}",
            "category": RELATION_CATEGORIES[index % len(RELATION_CATEGORIES)],
            "created": FIXED_ISO_TIMESTAMP,
            "cables": [{"layer_id": build.layer_id_of(cable["layer"]),
                        "fid": cable["fid"]} for cable in members],
        })


def _color_catalogs(name="TIA-598-C"):
    """The colour catalogue in the shape the project entry stores it.

    ``core/data_manager.get_default_color_sets()`` builds the same twelve; this
    is the copy the fixture writes, kept in one place so :func:`dataset_digest`
    hashes the object :func:`_write_project_entries` writes.
    """
    return [{"name": name,
             "colors": [{"name": colour, "hex": value}
                        for colour, value in TIA_598_C]}]


def _add_latent(build, cables):
    """Latent elements on a few cables, in the shape the dialog reads.

    The two readers disagree. ``LatentElementsDialog`` writes and reads a dict
    with an ``"elements"`` list (dialogs/latent_dialog.py:189-191), while WP3's
    bundle writer expects the value to be a bare list
    (core/interchange_bundle.py:468-469). This writes the dict, because that is
    what a project saved through the UI actually contains and what the
    ``latent_open`` benchmark scenario has to be able to open -- handed the list
    shape, the dialog raises ``AttributeError`` before any timing happens. ``m``
    is included although the dialog never writes it: the bundle writer orders by
    it and the dialog ignores it, so carrying it costs nothing.
    """
    terminals = [(fid, attrs["naziv"])
                 for fid, _wkt_text, attrs in build.rows["Outdoor TO"]]
    if not terminals:
        return
    terminal_layer = build.layer_id_of("Outdoor TO")
    for index, cable in enumerate(cables):
        if index % LATENT_EVERY:
            continue
        members = []
        for step in range(1, 4):
            fid, name = terminals[(index + step * 7) % len(terminals)]
            members.append({
                "layer_id": terminal_layer,
                "fid": fid,
                "naziv": name,
                "latent": True,
                "m": _r(cable["length"] * step / 4.0),
            })
        key = f"{build.layer_id_of(cable['layer'])}:{cable['fid']}"
        build.latent[key] = {"elements": members}


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------

def dataset_digest(rows, names, legacy, entries):
    """sha256 over the dataset's content: every row *and* every project entry.

    Over the content and not over the file, because the GeoPackage bytes are
    not reproducible: ``gpkg_contents.last_change`` is a wall-clock stamp and
    GDAL writes header fields of its own. The row half covers the table name,
    the stored column names in schema order, every explicit fid, the WKT
    exactly as written and every attribute value -- so ``--legacy-names`` has a
    digest of its own, which is the point.

    ``entries`` is folded in because it is part of the dataset and not of the
    GeoPackage: the relations, the latent elements and the colour catalogue
    live in the ``.qgz`` (:func:`_write_project_entries`), and the
    ``latent_open`` benchmark scenario is timed opening the latent payload. A
    digest over the rows alone stayed green while that payload grew sevenfold
    (``LATENT_EVERY`` 97 -> 13 moves it from 3 cables to 22), which would have
    let a published "before" number be compared against a different dataset.
    Required rather than defaulted: a caller that left it out would get a
    quietly weaker identity, which is the mistake this guards against.
    """
    from fiberq.models import schema

    digest = hashlib.sha256()
    for canonical in sorted(rows):
        if not rows[canonical]:
            continue
        # on_demand fields are skipped: the plugin adds such a column only when
        # a feature needs it, so a generated project must not carry it, and --
        # the part that matters here -- folding it into the digest would move
        # the identifier that every published "before" number was measured on.
        keys = [field.key for field in schema.LAYER_SCHEMAS[canonical].fields
                if not getattr(field, "on_demand", False)]
        columns = ",".join(field_key(key, legacy) for key in keys)
        digest.update(f"{table_name(names[canonical])}|{columns}\n".encode())
        for fid, wkt, attrs in rows[canonical]:
            cells = "|".join(_digest_value(attrs.get(key)) for key in keys)
            digest.update(f"{fid}|{wkt}|{cells}\n".encode())
    digest.update(b"entries\n")
    digest.update(json.dumps(entries, sort_keys=True,
                             separators=(",", ":")).encode())
    digest.update(b"\n")
    return digest.hexdigest()


def _digest_value(value):
    """One attribute, as a stable string. Floats are fixed-point, not repr.

    ``None`` does not collapse onto the empty string. Six text fields are
    stored as ``""`` today (``napomena``, ``opis``, ``address_id``,
    ``naziv_objekta``, ``numeracija``, ``oznaka_izvoda``); a generator that
    stopped writing one of them would leave the column NULL, which the
    GeoPackage keeps distinct from ``""`` -- so the digest has to as well.
    Nothing is ``None`` today, so the sentinel does not move the pinned digest;
    it stops the next such change from passing unnoticed.
    """
    if value is None:
        return "\x00"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.{PRECISION}f}"
    return str(value)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def build_gpkg(path, rows, names, legacy=False):
    """Write the GeoPackage. Returns ``(path, feature count)``. Needs GDAL."""
    from osgeo import gdal, ogr, osr

    from fiberq.models import schema

    # Fail fast rather than silently producing a malformed fixture.
    gdal.UseExceptions()
    ogr.UseExceptions()
    if os.path.exists(path):
        os.remove(path)

    driver = ogr.GetDriverByName("GPKG")
    if driver is None:
        raise RuntimeError("GDAL GPKG driver unavailable")
    source = driver.CreateDataSource(path)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(EPSG)

    total = 0
    for canonical in sorted(rows):
        if not rows[canonical]:
            continue
        layer_schema = schema.LAYER_SCHEMAS[canonical]
        layer = source.CreateLayer(
            table_name(names[canonical]), srs,
            getattr(ogr, _OGR_GEOM[layer_schema.geometry]))
        for field in layer_schema.fields:
            if getattr(field, "on_demand", False):
                continue  # see the note beside the digest above
            layer.CreateField(ogr.FieldDefn(
                field_key(field.key, legacy),
                getattr(ogr, _OGR_TYPE.get(field.field_type, "OFTString"))))

        definition = layer.GetLayerDefn()
        layer.StartTransaction()   # one commit per layer, not per feature
        for fid, wkt, attrs in rows[canonical]:
            feature = ogr.Feature(definition)
            # The fid is explicit: the slack and fibre-break rows carry
            # cable_fid foreign keys, so the numbering has to be ours. GPKG
            # honours SetFID; the memory provider renumbers from 1, which is
            # why this fixture is GeoPackage-backed.
            feature.SetFID(fid)
            for key, value in attrs.items():
                index = definition.GetFieldIndex(field_key(key, legacy))
                if index >= 0 and value is not None:
                    feature.SetField(index, value)
            feature.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
            layer.CreateFeature(feature)
            feature = None
            total += 1
        layer.CommitTransaction()
        layer = None

    source = None
    _write_metadata(path)
    return path, total


def _write_metadata(path):
    """The ``_fiberq_metadata`` marker, written the way ExportManager writes it.

    Raw sqlite3 rather than OGR, and closed explicitly: ``with
    sqlite3.connect(...)`` commits but does not close, and an open handle on a
    GeoPackage QGIS is about to read is asking for trouble.
    """
    from fiberq.models import schema

    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS _fiberq_metadata "
                "(key TEXT PRIMARY KEY, value TEXT)")
            connection.execute(
                "INSERT OR REPLACE INTO _fiberq_metadata (key, value) "
                "VALUES (?, ?)",
                ("schema_version", schema.SCHEMA_VERSION))
            connection.execute(
                "INSERT OR IGNORE INTO gpkg_contents "
                "(table_name, data_type, identifier, srs_id) "
                "VALUES (?, 'attributes', ?, 0)",
                ("_fiberq_metadata", "_fiberq_metadata"))
    finally:
        connection.close()


def build_project(gpkg_path, qgz_path, meta):
    """Write the ``.qgz`` over the GeoPackage. Needs QGIS. Returns the path.

    Three things here cannot be expressed by the GeoPackage alone: the fixed
    layer ids the benchmark addresses layers by, the project entries the
    relations / latent / colour readers look for, and the schema-version
    marker, without which the project reads as pre-1.0 and the WP1 migration
    runs on every open -- which would then be measured as part of
    ``project_open``.
    """
    from qgis.core import (QgsCoordinateReferenceSystem, QgsMapLayer,
                           QgsProject, QgsVectorLayer)

    from fiberq.core.schema_version import mark_project_current

    if not hasattr(QgsMapLayer, "setId"):
        raise RuntimeError(
            "QgsMapLayer.setId() is missing (QGIS 3.22 and older). The "
            "benchmark needs fixed layer ids, so generate the dataset on 3.44 "
            "or 4.0; a project written there reads back with its ids intact on "
            "3.22.")

    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{EPSG}"))
    # setEllipsoid is a no-op until the CRS is set, and without it every length
    # is measured in map units -- the exact error D3 exists to catch.
    project.setEllipsoid("EPSG:7030")

    loaded = []
    for canonical, name in sorted(meta["layer_names"].items()):
        table = table_name(name)
        layer = QgsVectorLayer(f"{gpkg_path}|layername={table}", name, "ogr")
        if not layer.isValid():
            raise RuntimeError(f"layer {table} did not load from {gpkg_path}")
        # setId() returns False once a layer is registered and the project then
        # keeps the random uuid id instead -- silently, which would leave every
        # cable_layer_id in the dataset dangling. So: before the add, and
        # checked. A duplicate id is accepted here and then rejected by
        # addMapLayer, which is why that return value is checked too.
        if not layer.setId(layer_id(name)):
            raise RuntimeError(f"could not fix the layer id of {name}")
        if project.addMapLayer(layer) is not layer:
            raise RuntimeError(f"{name} was rejected (duplicate layer id?)")
        loaded.append(layer)

    _write_project_entries(project, meta)
    mark_project_current(project)
    _set_view_extent(project, loaded)
    if not project.write(qgz_path):
        raise RuntimeError(f"could not write {qgz_path}")
    return qgz_path


def _write_project_entries(project, meta):
    """Relations, latent elements and the colour catalogue, as JSON entries.

    Every key here is a valid XML tag name. QGIS 3.x uses the entry key *as*
    the tag, so a key with a space or a leading digit is dropped on save while
    ``write()`` still reports success -- which is how the picture links go
    missing on QGIS 3 (WP4 U9).
    """
    entries = meta["entry_rows"]
    project.writeEntry(LEGACY_SCOPE, RELATIONS_KEY,
                       json.dumps({"relations": entries["relations"]}))
    project.writeEntry(LEGACY_SCOPE, LATENT_KEY,
                       json.dumps({"cables": entries["latent"]}))
    project.writeEntry(LEGACY_SCOPE, COLOR_CATALOGS_KEY,
                       json.dumps({"catalogs": entries["catalogs"]}))


def _set_view_extent(project, layers):
    """Save the canvas extent, so the dataset opens on the network.

    A project written headlessly has never had a canvas, so QGIS stores no
    ``<mapcanvas>`` and opens on a blank white map.
    """
    from qgis.core import (QgsCoordinateReferenceSystem, QgsRectangle,
                           QgsReferencedRectangle)

    # Not setNull(): that only arrived in QGIS 3.34 (measured: absent on
    # 3.22.16, present on 3.34.15), and this fixture is also
    # read on 3.22 LTR. A default-constructed QgsRectangle already reports
    # isNull(), and combineExtentWith() special-cases a null rectangle, so the
    # union is identical -- verified equal on 3.22.16, 3.44.15 and 4.0.3.
    extent = QgsRectangle()
    for layer in layers:
        rect = layer.extent()
        if not rect.isNull():
            extent.combineExtentWith(rect)
    if extent.isNull():
        return
    extent.grow(40.0)   # metres of the projected CRS
    project.viewSettings().setDefaultViewExtent(
        QgsReferencedRectangle(extent,
                               QgsCoordinateReferenceSystem(f"EPSG:{EPSG}")))


def write_manifest(path, meta):
    """Write the manifest beside the dataset and return its path.

    ``.json``, never ``.manifest``: ``.gitignore:32`` matches ``*.manifest``,
    so a manifest named that way would be invisible to git.
    """
    payload = {key: value for key, value in meta.items()
               if key != "entry_rows"}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True)
        handle.write("\n")
    return path


def default_out(size, legacy=False):
    """Where a dataset goes when ``--out`` is not given.

    Under the system temporary directory, never in the repository: nothing in
    ``.gitignore`` matches ``*.gpkg`` or ``*.qgz``, so an L dataset defaulted
    into ``tests/fixtures/`` would be ~20 MB sitting in ``git status``.
    """
    stem = f"city_{size}_legacy" if legacy else f"city_{size}"
    return os.path.join(tempfile.gettempdir(), "fiberq-city", stem,
                        f"{stem}.gpkg")


def generate(size="XS", seed=DEFAULT_SEED, out=None, legacy=False,
             project=True):
    """Build one dataset end to end. Returns ``meta`` with the paths added.

    Needs GDAL, and a running QgsApplication for the ``.qgz``. With
    ``project=False`` only the GeoPackage and the manifest are written, which
    is enough for the determinism and domain tests and needs no application.
    """
    out = out or default_out(size, legacy)
    folder = os.path.dirname(os.path.abspath(out))
    os.makedirs(folder, exist_ok=True)

    rows, meta = build_model(SIZES[size], seed, legacy)
    meta["size"] = size
    meta["gpkg"], meta["written"] = build_gpkg(
        out, rows, meta["layer_names"], legacy)
    if project:
        meta["qgz"] = build_project(
            meta["gpkg"], os.path.splitext(out)[0] + ".qgz", meta)
    meta["manifest"] = write_manifest(
        os.path.join(folder, "manifest.json"), meta)
    return meta


def _report(meta):
    """The one-line-per-artefact summary the other fixtures print."""
    print(f"Wrote {meta['gpkg']}")
    if meta.get("qgz"):
        print(f"Wrote {meta['qgz']}")
    print(f"Wrote {meta['manifest']}")
    print(f"  size      {meta['size']} (n={meta['n']}, seed={meta['seed']})")
    print(f"  streets   {meta['streets']} between "
          f"{meta['component']} of {meta['intersections']} intersections")
    print(f"  cables    {meta['cables']}")
    print(f"  layers    {len(meta['counts'])}")
    print(f"  features  {meta['features']}")
    print(f"  digest    {meta['digest']}")


def main(argv=None):
    """Command-line entry point."""
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(here))
    if repo_root not in sys.path:
        # Inside main() only; see the module docstring. A benchmark worker
        # imports this module and must keep control of sys.path.
        sys.path.insert(0, repo_root)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--size", default="XS", choices=sorted(SIZES),
                        help="dataset size (default: XS)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"random seed (default: {DEFAULT_SEED})")
    parser.add_argument("--out", default=None,
                        help="output .gpkg path (default: under the temp dir)")
    parser.add_argument("--legacy-names", action="store_true",
                        help="pre-1.0 Serbian layer and field names")
    args = parser.parse_args(argv)

    try:
        from qgis.core import QgsApplication
    except ImportError:
        _report(generate(args.size, args.seed, args.out, args.legacy_names,
                         project=False))
        print("QGIS not available -- GeoPackage written without a project file")
        return 0

    # Writing the project needs a running application. Without one QGIS still
    # produces a file, but prints "Application path not initialized" once per
    # layer, which makes a working run look broken.
    app = None
    if QgsApplication.instance() is None:
        QgsApplication.setPrefixPath("/usr", True)
        app = QgsApplication([], False)
        app.initQgis()
    try:
        meta = generate(args.size, args.seed, args.out, args.legacy_names)
    finally:
        if app is not None:
            app.exitQgis()
    _report(meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
