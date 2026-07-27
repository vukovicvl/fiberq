"""Tests for the WP2 topology (A1-A3) and referential-integrity (B1-B3) rules.

Each test builds a tiny project with one known defect and asserts exactly that
issue. Geometry is in EPSG:3857 (metres) so the default 5.0 map-unit tolerance
means 5 metres and the distances below are easy to reason about.
"""
from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from fiberq.core import validation_manager as vm
from fiberq.core import validation_rules as vr

CRS = "EPSG:3857"


def _point_layer(name, rows, fields=("fiberq_uuid:string",)):
    """rows: [(attrs, QgsPointXY|None)]"""
    uri = f"Point?crs={CRS}"
    for spec in fields:
        uri += "&field=" + spec
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), name
    feats = []
    for attrs, point in rows:
        feat = QgsFeature(layer.fields())
        for key, value in attrs.items():
            feat.setAttribute(key, value)
        if point is not None:
            feat.setGeometry(QgsGeometry.fromPointXY(point))
        feats.append(feat)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


def _line_layer(name, lines, fields=("fiberq_uuid:string",)):
    """lines: [(attrs, [QgsPointXY, ...])]"""
    uri = f"LineString?crs={CRS}"
    for spec in fields:
        uri += "&field=" + spec
    layer = QgsVectorLayer(uri, name, "memory")
    assert layer.isValid(), name
    feats = []
    for attrs, pts in lines:
        feat = QgsFeature(layer.fields())
        for key, value in attrs.items():
            feat.setAttribute(key, value)
        feat.setGeometry(QgsGeometry.fromPolylineXY(pts))
        feats.append(feat)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


def _run(project, rule_ids):
    """Run only the named rules and return their issues."""
    rules = [r for r in vr.RULES if r.id in rule_ids]
    assert len(rules) == len(rule_ids)
    result = vm.run_validation(project, rules=rules)
    assert not result.rule_errors, result.rule_errors
    return result


def _ids(result, rule_id):
    return [i for i in result.issues if i.rule_id == rule_id]


# ---------------------------------------------------------------------------
# A1 -- cable dangles
# ---------------------------------------------------------------------------

def test_a1_connected_cable_is_clean(qgis_app):
    """Both ends land exactly on an ODF -> no issue."""
    project = QgsProject()
    project.addMapLayer(_point_layer("ODF", [
        ({"fiberq_uuid": "n1"}, QgsPointXY(0, 0)),
        ({"fiberq_uuid": "n2"}, QgsPointXY(100, 0)),
    ]))
    project.addMapLayer(_line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(100, 0)]),
    ]))
    assert _ids(_run(project, {"A1"}), "A1") == []


def test_a1_flags_a_dangling_end(qgis_app):
    """One end on a node, the far end alone in space."""
    project = QgsProject()
    project.addMapLayer(_point_layer("ODF", [
        ({"fiberq_uuid": "n1"}, QgsPointXY(0, 0)),
    ]))
    project.addMapLayer(_line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(500, 0)]),
    ]))
    issues = _ids(_run(project, {"A1"}), "A1")
    assert len(issues) == 1
    assert issues[0].severity == vm.Severity.WARNING
    assert issues[0].details["endpoint"] == "end"
    assert issues[0].where == (500.0, 0.0)


def test_a1_accepts_cable_to_cable_joins(qgis_app):
    """Two cables meeting end-to-end are connected, with no node present."""
    project = QgsProject()
    project.addMapLayer(_line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(100, 0)]),
        ({"fiberq_uuid": "c2"}, [QgsPointXY(100, 0), QgsPointXY(200, 0)]),
    ]))
    # The outer ends (0,0) and (200,0) still dangle; the shared join does not.
    issues = _ids(_run(project, {"A1"}), "A1")
    assert len(issues) == 2
    assert {i.where for i in issues} == {(0.0, 0.0), (200.0, 0.0)}


def test_a1_does_not_let_a_cable_connect_to_itself(qgis_app):
    """A cable's own other end must not count as a connection."""
    project = QgsProject()
    project.addMapLayer(_line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(300, 0)]),
    ]))
    assert len(_ids(_run(project, {"A1"}), "A1")) == 2


def test_a1_respects_a_configured_tolerance(qgis_app):
    """A 12 m gap dangles at the default 5 m tolerance and is fine at 20 m."""
    project = QgsProject()
    project.addMapLayer(_point_layer("ODF", [
        ({"fiberq_uuid": "n1"}, QgsPointXY(0, 0)),
        ({"fiberq_uuid": "n2"}, QgsPointXY(112, 0)),
    ]))
    project.addMapLayer(_line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(100, 0)]),
    ]))
    rules = [r for r in vr.RULES if r.id == "A1"]
    assert len(vm.run_validation(project, rules=rules).issues) == 1

    loose = vm.ValidationConfig(tol=20.0)
    assert vm.run_validation(project, rules=rules, config=loose).issues == []


# ---------------------------------------------------------------------------
# A2 -- near miss
# ---------------------------------------------------------------------------

def test_a2_flags_an_endpoint_just_outside_tolerance(qgis_app):
    """7 m from a node: outside the 5 m tolerance, inside the 10 m near band."""
    project = QgsProject()
    project.addMapLayer(_point_layer("ODF", [
        ({"fiberq_uuid": "n1"}, QgsPointXY(0, 0)),
        ({"fiberq_uuid": "n2"}, QgsPointXY(107, 0)),
    ]))
    project.addMapLayer(_line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(100, 0)]),
    ]))
    result = _run(project, {"A1", "A2"})
    near = _ids(result, "A2")
    assert len(near) == 1
    assert near[0].severity == vm.Severity.INFO
    assert round(near[0].details["nearest_distance"], 3) == 7.0
    # A2 refines A1 rather than replacing it: the endpoint is still unconnected.
    assert len(_ids(result, "A1")) == 1


def test_a2_ignores_a_far_dangle(qgis_app):
    """Nothing within 2*tol -> A1 only, no near-miss hint."""
    project = QgsProject()
    project.addMapLayer(_point_layer("ODF", [
        ({"fiberq_uuid": "n1"}, QgsPointXY(0, 0)),
    ]))
    project.addMapLayer(_line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(500, 0)]),
    ]))
    result = _run(project, {"A1", "A2"})
    assert _ids(result, "A2") == []
    assert len(_ids(result, "A1")) == 1


# ---------------------------------------------------------------------------
# A3 -- orphan elements
# ---------------------------------------------------------------------------

def test_a3_flags_an_element_off_the_network(qgis_app):
    project = QgsProject()
    project.addMapLayer(_point_layer("ODF", [
        ({"fiberq_uuid": "n1"}, QgsPointXY(0, 0)),      # on the cable
        ({"fiberq_uuid": "n2"}, QgsPointXY(50, 400)),   # stranded
    ]))
    project.addMapLayer(_line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(100, 0)]),
    ]))
    issues = _ids(_run(project, {"A3"}), "A3")
    assert len(issues) == 1
    assert issues[0].where == (50.0, 400.0)
    assert issues[0].fiberq_uuid == "n2"


def test_a3_counts_a_route_as_attachment(qgis_app):
    """An element on a Route but no cable is still attached."""
    project = QgsProject()
    project.addMapLayer(_point_layer("Manholes", [
        ({"fiberq_uuid": "m1"}, QgsPointXY(50, 0)),
    ]))
    project.addMapLayer(_line_layer("Route", [
        ({"fiberq_uuid": "r1"}, [QgsPointXY(0, 0), QgsPointXY(100, 0)]),
    ]))
    assert _ids(_run(project, {"A3"}), "A3") == []


def test_a3_is_silent_when_there_is_no_network_at_all(qgis_app):
    """Elements with no cables/routes anywhere are not each an orphan finding."""
    project = QgsProject()
    project.addMapLayer(_point_layer("ODF", [
        ({"fiberq_uuid": "n1"}, QgsPointXY(0, 0)),
        ({"fiberq_uuid": "n2"}, QgsPointXY(10, 10)),
    ]))
    assert _ids(_run(project, {"A3"}), "A3") == []


# ---------------------------------------------------------------------------
# B1 / B2 -- cable foreign keys
# ---------------------------------------------------------------------------

_FK_FIELDS = ("fiberq_uuid:string", "cable_layer_id:string", "cable_fid:integer")


def _project_with_cable():
    project = QgsProject()
    cables = _line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(100, 0)]),
    ])
    project.addMapLayer(cables)
    cable_fid = next(cables.getFeatures()).id()
    return project, cables, cable_fid


def test_b1_resolvable_reference_is_clean(qgis_app):
    project, cables, fid = _project_with_cable()
    project.addMapLayer(_point_layer("Optical slacks", [
        ({"fiberq_uuid": "s1", "cable_layer_id": cables.id(), "cable_fid": fid},
         QgsPointXY(50, 0)),
    ], fields=_FK_FIELDS))
    assert _ids(_run(project, {"B1"}), "B1") == []


def test_b1_flags_a_missing_cable_feature(qgis_app):
    project, cables, _fid = _project_with_cable()
    project.addMapLayer(_point_layer("Optical slacks", [
        ({"fiberq_uuid": "s1", "cable_layer_id": cables.id(), "cable_fid": 9999},
         QgsPointXY(50, 0)),
    ], fields=_FK_FIELDS))
    issues = _ids(_run(project, {"B1"}), "B1")
    assert len(issues) == 1
    assert issues[0].severity == vm.Severity.ERROR
    assert issues[0].details["cable_fid"] == 9999


def test_b1_flags_a_missing_cable_layer(qgis_app):
    project, _cables, fid = _project_with_cable()
    project.addMapLayer(_point_layer("Optical slacks", [
        ({"fiberq_uuid": "s1", "cable_layer_id": "no_such_layer_id", "cable_fid": fid},
         QgsPointXY(50, 0)),
    ], fields=_FK_FIELDS))
    issues = _ids(_run(project, {"B1"}), "B1")
    assert len(issues) == 1
    assert "no_such_layer_id" in issues[0].message


def test_b1_ignores_an_unlinked_slack(qgis_app):
    """No reference at all is incompleteness (C1), not a broken link."""
    project, _cables, _fid = _project_with_cable()
    project.addMapLayer(_point_layer("Optical slacks", [
        ({"fiberq_uuid": "s1"}, QgsPointXY(50, 0)),
    ], fields=_FK_FIELDS))
    assert _ids(_run(project, {"B1"}), "B1") == []


def test_b2_checks_fiber_break_the_same_way(qgis_app):
    project, cables, _fid = _project_with_cable()
    project.addMapLayer(_point_layer("Fiber break", [
        ({"fiberq_uuid": "b1", "cable_layer_id": cables.id(), "cable_fid": 4242},
         QgsPointXY(50, 0)),
    ], fields=_FK_FIELDS))
    issues = _ids(_run(project, {"B2"}), "B2")
    assert len(issues) == 1
    assert issues[0].severity == vm.Severity.ERROR
    assert issues[0].layer_name == "Fiber break"


# ---------------------------------------------------------------------------
# B3 -- spatial coherence of a resolvable reference
# ---------------------------------------------------------------------------

def test_b3_flags_a_slack_far_from_its_cable(qgis_app):
    project, cables, fid = _project_with_cable()
    project.addMapLayer(_point_layer("Optical slacks", [
        ({"fiberq_uuid": "s1", "cable_layer_id": cables.id(), "cable_fid": fid},
         QgsPointXY(50, 250)),
    ], fields=_FK_FIELDS))
    issues = _ids(_run(project, {"B3"}), "B3")
    assert len(issues) == 1
    assert issues[0].severity == vm.Severity.WARNING
    assert round(issues[0].details["distance"]) == 250


def test_b3_is_clean_when_the_slack_sits_on_the_cable(qgis_app):
    project, cables, fid = _project_with_cable()
    project.addMapLayer(_point_layer("Optical slacks", [
        ({"fiberq_uuid": "s1", "cable_layer_id": cables.id(), "cable_fid": fid},
         QgsPointXY(50, 2)),
    ], fields=_FK_FIELDS))
    assert _ids(_run(project, {"B3"}), "B3") == []


def test_b3_stays_quiet_when_the_link_is_broken(qgis_app):
    """A broken link is B1/B2's finding; B3 must not double-report it."""
    project, cables, _fid = _project_with_cable()
    project.addMapLayer(_point_layer("Optical slacks", [
        ({"fiberq_uuid": "s1", "cable_layer_id": cables.id(), "cable_fid": 9999},
         QgsPointXY(50, 250)),
    ], fields=_FK_FIELDS))
    assert _ids(_run(project, {"B3"}), "B3") == []


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------

def test_plural_slack_layer_is_actually_checked(qgis_app):
    """Regression guard for the canonical-name divergence.

    The layer is created as "Optical slacks" (plural) but its canonical name is
    "Optical slack". A mapLayersByName() lookup would silently skip it and B1
    would report nothing at all.
    """
    project, cables, _fid = _project_with_cable()
    slacks = _point_layer("Optical slacks", [
        ({"fiberq_uuid": "s1", "cable_layer_id": cables.id(), "cable_fid": 9999},
         QgsPointXY(50, 0)),
    ], fields=_FK_FIELDS)
    project.addMapLayer(slacks)

    ctx = vm.ValidationContext(project)
    assert "Optical slack" in ctx.layers_by_canonical
    assert len(_ids(_run(project, {"B1"}), "B1")) == 1


def test_topology_rules_are_registered(qgis_app):
    """The full rule list is pinned once, in test_validation_domain.py."""
    ids = {r.id for r in vr.RULES}
    assert {"A1", "A2", "A3", "B1", "B2", "B3"} <= ids


def test_line_rules_survive_a_layer_with_unexpected_geometry(qgis_app):
    """A layer whose real geometry differs from its declared type must not crash.

    A1/A2 previously called asPolyline() on whatever the layer held, so a point
    layer named like a cable raised "Point geometry cannot be converted to a
    polyline". The runner caught it, but the rule produced nothing useful.
    """
    project = QgsProject()
    project.addMapLayer(_point_layer("Underground cables", [
        ({"fiberq_uuid": "odd"}, QgsPointXY(0, 0)),
    ]))
    result = _run(project, {"A1", "A2"})
    assert result.rule_errors == []
    assert result.issues == []


def test_endpoint_scan_is_built_once_per_run(qgis_app):
    """A1 and A2 share the scan through the context cache."""
    project = QgsProject()
    project.addMapLayer(_line_layer("Underground cables", [
        ({"fiberq_uuid": "c1"}, [QgsPointXY(0, 0), QgsPointXY(100, 0)]),
    ]))
    ctx = vm.ValidationContext(project)
    first = vr._endpoint_scan(ctx)
    assert vr._endpoint_scan(ctx) is first
    assert "endpoint_scan" in ctx.cache
