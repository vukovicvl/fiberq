"""FiberQ validation rule registry (WP2, task 2.1).

The rules that :func:`fiberq.core.validation_manager.run_validation` executes. The
registry mirrors WP1's ``MIGRATIONS`` list: a list of small dataclass entries,
each carrying a ``check`` callable. Unlike the migration chain (which stops on the
first failure), validation rules are independent — the runner ``continue``s past a
failing rule.

i18n (read before adding a rule)
--------------------------------
Rule ``title`` strings are **module-level data**, which is exactly the shape that
hits the ``tr()`` context trap. They are therefore marked with
``QT_TRANSLATE_NOOP('ValidationRules', ...)`` at definition (returns the literal
unchanged, so the table built at import time is not frozen to English) and
translated at *display* time with ``QCoreApplication.translate('ValidationRules',
title)``. Rule *messages* are built at run time and use the explicit inline form
``QCoreApplication.translate('ValidationRules', "literal")`` directly at the call
site — never a module-level ``tr()`` helper, which pylupdate6 cannot extract.

Not translated: ``rule_id``, ``category``, ``severity`` values, and stored
layer/field names (passed through ``{field}``/``{layer}`` placeholders as data).

This module has no QGIS import at top level, so the registry can be imported and
asserted in a pure unit test; QGIS types (``NULL``, feature/geometry access) are
imported lazily inside the checks, which only run under QGIS.
"""
from ..models import schema
from .validation_manager import Severity, ValidationIssue, ValidationRule

try:
    from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP
except ImportError:  # pragma: no cover - keep importable without Qt (pure tests)
    def QT_TRANSLATE_NOOP(context, text):
        return text

    class _NoQtTranslate:
        @staticmethod
        def translate(context, text, *args):
            return text

    QCoreApplication = _NoQtTranslate

_CTX = "ValidationRules"

# Categories are stable identifiers (grouping keys in the report), not translated.
_CAT_IDENTITY = "identity"
_CAT_COMPLETENESS = "completeness"
_CAT_DOMAIN = "domain"
_CAT_TOPOLOGY = "topology"
_CAT_REFERENTIAL = "referential"

# Layer groupings used by the topology rules, by canonical name.
_CABLE_LAYERS = ("Aerial cables", "Underground cables")
# Everything a cable endpoint may legitimately terminate on.
_NODE_LAYERS = tuple(schema.ELEMENT_LAYER_NAMES) + (
    "Joint Closures", "Poles", "Manholes",
)
# Linear features an element is expected to sit on/near.
_LINEAR_LAYERS = _CABLE_LAYERS + ("Route",)
# Layers carrying a cable_layer_id + cable_fid foreign key.
_FK_LAYERS = ("Optical slack", "Fiber break")

# Required, domain-meaningful fields per layer type (fiberq_uuid is B4's concern,
# not repeated here). Element layers share one set; the rest are keyed by
# canonical layer name.
_ELEMENT_REQUIRED = ("naziv", "kapacitet")
_REQUIRED_BY_LAYER = {
    "Aerial cables": ("tip", "broj_vlakana"),
    "Underground cables": ("tip", "broj_vlakana"),
    "Route": ("naziv",),
    "PE pipes": ("fi",),
    "Transition pipes": ("fi",),
}


# ---------------------------------------------------------------------------
# Small helpers (QGIS-aware, called only from checks)
# ---------------------------------------------------------------------------

def _is_blank(value, null) -> bool:
    """True for a missing / null / whitespace-only attribute value."""
    if value is None or value == null:
        return True
    return isinstance(value, str) and value.strip() == ""


def _feature_xy(feat):
    """A representative (x, y) for navigation/zoom, or None."""
    geom = feat.geometry()
    if geom is None or geom.isNull() or geom.isEmpty():
        return None
    centroid = geom.centroid()
    if centroid.isNull() or centroid.isEmpty():
        return None
    point = centroid.asPoint()
    return (point.x(), point.y())


def _uuid_of(feat) -> str:
    from ..utils.uuid_utils import FIBERQ_UUID_FIELD
    idx = feat.fields().indexOf(FIBERQ_UUID_FIELD)
    if idx < 0:
        return ""
    value = feat.attribute(idx)
    return "" if value is None else str(value)


def _fmt(value) -> str:
    """Compact number for a message: trims trailing zeros so a tolerance of 5.0
    reads as "5" and a distance of 7.25 keeps its precision."""
    try:
        text = f"{float(value):.2f}".rstrip("0").rstrip(".")
        return text or "0"
    except (TypeError, ValueError):
        return str(value)


def _safe_format(translated, source, **kwargs):
    """Interpolate into a translated message, falling back to the English source
    if a volunteer renamed a placeholder (see ``fiberq.i18n.safe_format``)."""
    from ..i18n import safe_format
    return safe_format(translated, source, **kwargs)


def _allowed_domain(field_def):
    """The set of valid *stored* values for an enum field. ``value_map`` is
    ``{display: stored}``, so the stored domain is its values (e.g. cable ``tip``
    -> ``{opticki, bakarnI}`` — the as-built typo is honoured because the domain
    is read from the schema, not hardcoded)."""
    if field_def.value_map:
        return set(field_def.value_map.values())
    if field_def.options:
        return set(field_def.options)
    return set()


def _required_fields_for(canonical: str):
    if schema.is_element_layer(canonical):
        return _ELEMENT_REQUIRED
    return _REQUIRED_BY_LAYER.get(canonical, ())


# ---------------------------------------------------------------------------
# Geometry / spatial helpers (QGIS-aware, called only from checks)
# ---------------------------------------------------------------------------

def _first_point(geom):
    """First vertex of a point/multipoint geometry, or None. Avoids asPoint(),
    which raises on multipoint."""
    if geom is None or geom.isNull() or geom.isEmpty():
        return None
    from qgis.core import QgsPointXY
    for vertex in geom.vertices():
        return QgsPointXY(vertex)
    return None


def _line_parts(geom):
    """Vertex lists of every line part with at least two vertices."""
    if geom is None or geom.isNull() or geom.isEmpty():
        return []
    if geom.isMultipart():
        return [part for part in geom.asMultiPolyline() if len(part) >= 2]
    points = geom.asPolyline()
    return [points] if len(points) >= 2 else []


def _line_endpoints(geom):
    """``[(label, QgsPointXY)]`` for both ends of every part.

    ``label`` ("start"/"end", suffixed with the part number when multipart) is a
    stable identifier carried in ``details`` -- it is never translated and never
    interpolated into a message.
    """
    out = []
    parts = _line_parts(geom)
    multipart = len(parts) > 1
    for i, part in enumerate(parts):
        suffix = f" part {i + 1}" if multipart else ""
        out.append((f"start{suffix}", part[0]))
        out.append((f"end{suffix}", part[-1]))
    return out


def _rect_around(point, radius):
    from qgis.core import QgsRectangle
    return QgsRectangle(point.x() - radius, point.y() - radius,
                        point.x() + radius, point.y() + radius)


def _node_index(ctx):
    """``(QgsSpatialIndex, {id: (layer_name, fid, QgsPointXY)})`` over every point
    a cable endpoint may legally connect to.

    One combined index rather than one per layer, so an endpoint costs a single
    query instead of ~15. Built once per run and shared by A1/A2/A3.
    """
    cached = ctx.cache.get("node_index")
    if cached is not None:
        return cached

    from qgis.core import QgsFeature, QgsGeometry, QgsSpatialIndex

    index = QgsSpatialIndex()
    records = {}
    next_id = 0
    for layer in ctx.layers_for(*_NODE_LAYERS):
        for feat in layer.getFeatures():
            point = _first_point(feat.geometry())
            if point is None:
                continue
            holder = QgsFeature(next_id)
            holder.setGeometry(QgsGeometry.fromPointXY(point))
            index.addFeature(holder)
            records[next_id] = (layer.name(), feat.id(), point)
            next_id += 1

    cached = (index, records)
    ctx.cache["node_index"] = cached
    return cached


def _cable_endpoint_index(ctx):
    """``(QgsSpatialIndex, {id: (layer_name, layer_id, fid, label, QgsPointXY)})``
    over every cable endpoint, so endpoint-to-endpoint joins can be detected.

    A plain index over cable features would index their bounding boxes, which says
    nothing about where the ends are -- hence a synthetic point index.
    """
    cached = ctx.cache.get("cable_endpoint_index")
    if cached is not None:
        return cached

    from qgis.core import QgsFeature, QgsGeometry, QgsSpatialIndex

    index = QgsSpatialIndex()
    records = {}
    next_id = 0
    for layer in ctx.layers_for(*_CABLE_LAYERS):
        for feat in layer.getFeatures():
            for label, point in _line_endpoints(feat.geometry()):
                holder = QgsFeature(next_id)
                holder.setGeometry(QgsGeometry.fromPointXY(point))
                index.addFeature(holder)
                records[next_id] = (layer.name(), layer.id(), feat.id(), label, point)
                next_id += 1

    cached = (index, records)
    ctx.cache["cable_endpoint_index"] = cached
    return cached


def _endpoint_scan(ctx):
    """Classify every cable endpoint by its distance to the nearest legal partner.

    Returns ``[{layer_name, layer_id, feature_id, label, point, distance, target}]``
    where ``distance`` is ``None`` when nothing at all lies within 2*tol.
    Shared by A1 and A2 so the scan runs once.
    """
    cached = ctx.cache.get("endpoint_scan")
    if cached is not None:
        return cached

    tol = ctx.config.tol
    reach = tol * 2.0
    node_index, node_records = _node_index(ctx)
    ep_index, ep_records = _cable_endpoint_index(ctx)

    findings = []
    for holder_id, (layer_name, layer_id, fid, label, point) in ep_records.items():
        rect = _rect_around(point, reach)
        best_distance = None
        best_target = None

        for candidate in node_index.intersects(rect):
            target_layer, target_fid, target_point = node_records[candidate]
            distance = point.distance(target_point)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_target = (target_layer, target_fid)

        for candidate in ep_index.intersects(rect):
            if candidate == holder_id:
                continue
            other_layer, other_layer_id, other_fid, _lbl, other_point = ep_records[candidate]
            # An endpoint must join a *different* feature; its own other end does
            # not count as a connection.
            if other_layer_id == layer_id and other_fid == fid:
                continue
            distance = point.distance(other_point)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_target = (other_layer, other_fid)

        findings.append({
            "layer_name": layer_name,
            "layer_id": layer_id,
            "feature_id": fid,
            "label": label,
            "point": point,
            "distance": best_distance,
            "target": best_target,
        })

    ctx.cache["endpoint_scan"] = findings
    return findings


# ---------------------------------------------------------------------------
# A1 -- cable dangles
# ---------------------------------------------------------------------------

def _check_cable_dangles(ctx):
    """Every cable endpoint should terminate on a node or another cable's end.

    Fires for *every* unconnected endpoint, including the near-misses that A2 also
    reports -- so the A1 count is a clean "number of unconnected endpoints". A2
    refines those, it does not partition them.
    """
    tol = ctx.config.tol
    for finding in _endpoint_scan(ctx):
        distance = finding["distance"]
        if distance is not None and distance <= tol:
            continue
        src = "Cable endpoint is not connected to any element or cable (tolerance {tol})"
        yield ValidationIssue(
            rule_id="A1", severity=Severity.WARNING, category=_CAT_TOPOLOGY,
            message=_safe_format(
                QCoreApplication.translate(_CTX, src), src, tol=_fmt(tol)),
            layer_name=finding["layer_name"], layer_id=finding["layer_id"],
            feature_id=finding["feature_id"],
            where=(finding["point"].x(), finding["point"].y()),
            details={
                "endpoint": finding["label"],
                "nearest_distance": distance,
                "nearest": finding["target"],
                "tolerance": tol,
            },
        )


# ---------------------------------------------------------------------------
# A2 -- near miss / overshoot
# ---------------------------------------------------------------------------

def _check_near_miss(ctx):
    """An unconnected endpoint with something just outside tolerance: almost
    certainly meant to be snapped to it."""
    tol = ctx.config.tol
    for finding in _endpoint_scan(ctx):
        distance = finding["distance"]
        if distance is None or distance <= tol or distance > tol * 2.0:
            continue
        target = finding["target"]
        src = ("Cable endpoint is {distance} from {target} -- just outside the "
               "{tol} snapping tolerance; it probably should connect")
        yield ValidationIssue(
            rule_id="A2", severity=Severity.INFO, category=_CAT_TOPOLOGY,
            message=_safe_format(
                QCoreApplication.translate(_CTX, src), src,
                distance=_fmt(distance),
                target=target[0] if target else "",
                tol=_fmt(tol)),
            layer_name=finding["layer_name"], layer_id=finding["layer_id"],
            feature_id=finding["feature_id"],
            where=(finding["point"].x(), finding["point"].y()),
            details={
                "endpoint": finding["label"],
                "nearest_distance": distance,
                "nearest": target,
                "tolerance": tol,
            },
        )


# ---------------------------------------------------------------------------
# A3 -- orphan elements
# ---------------------------------------------------------------------------

def _check_orphan_elements(ctx):
    """A node that sits near no cable and no route is probably stranded."""
    from qgis.core import QgsGeometry

    tol = ctx.config.tol
    linears = ctx.layers_for(*_LINEAR_LAYERS)
    if not linears:
        return  # nothing to be connected to; not a finding

    for layer in ctx.layers_for(*_NODE_LAYERS):
        for feat in layer.getFeatures():
            point = _first_point(feat.geometry())
            if point is None:
                continue  # geometry health is E2's concern
            rect = _rect_around(point, tol)
            probe = QgsGeometry.fromPointXY(point)
            attached = False
            for linear in linears:
                index = ctx.spatial_index(linear)
                for candidate in index.intersects(rect):
                    other = linear.getFeature(candidate)
                    geom = other.geometry()
                    # Index hits are bbox-level; confirm with a real distance.
                    if geom is not None and not geom.isNull() and probe.distance(geom) <= tol:
                        attached = True
                        break
                if attached:
                    break
            if attached:
                continue
            src = "Element is not on or near any cable or route (tolerance {tol})"
            yield ValidationIssue(
                rule_id="A3", severity=Severity.WARNING, category=_CAT_TOPOLOGY,
                message=_safe_format(
                    QCoreApplication.translate(_CTX, src), src, tol=_fmt(tol)),
                layer_name=layer.name(), layer_id=layer.id(),
                feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                where=(point.x(), point.y()),
                details={"tolerance": tol},
            )


# ---------------------------------------------------------------------------
# B1 / B2 -- cable foreign keys, and B3 -- their spatial coherence
# ---------------------------------------------------------------------------

def _fk_rows(ctx, canonical):
    """Yield ``(layer, feat, cable_layer_id, cable_fid)`` for features carrying a
    populated cable reference. Rows with no reference at all are skipped -- an
    unlinked slack is incomplete (C1's concern), not a broken link."""
    from qgis.core import NULL

    for layer in ctx.layers_for(canonical):
        names = set(layer.fields().names())
        if not {"cable_layer_id", "cable_fid"} <= names:
            continue
        for feat in layer.getFeatures():
            raw_layer_id = feat.attribute("cable_layer_id")
            raw_fid = feat.attribute("cable_fid")
            if _is_blank(raw_layer_id, NULL) and _is_blank(raw_fid, NULL):
                continue
            yield layer, feat, raw_layer_id, raw_fid


def _resolve_cable(ctx, raw_layer_id, raw_fid):
    """``(layer, feature)`` for a cable reference, or ``(layer_or_None, None)``."""
    from qgis.core import NULL, QgsVectorLayer

    if _is_blank(raw_layer_id, NULL):
        return None, None
    layer = ctx.project.mapLayer(str(raw_layer_id))
    if layer is None or not isinstance(layer, QgsVectorLayer):
        return None, None
    if _is_blank(raw_fid, NULL):
        return layer, None
    try:
        feat = layer.getFeature(int(raw_fid))
    except (TypeError, ValueError):
        return layer, None
    return layer, (feat if feat.isValid() else None)


def _fk_checker(canonical, rule_id):
    """Build the B1/B2 check for one layer -- both carry the identical FK shape."""
    def check(ctx):
        for layer, feat, raw_layer_id, raw_fid in _fk_rows(ctx, canonical):
            cable_layer, cable_feat = _resolve_cable(ctx, raw_layer_id, raw_fid)
            if cable_feat is not None:
                continue
            if cable_layer is None:
                src = "Referenced cable layer {layer_id} is not in the project"
                message = _safe_format(
                    QCoreApplication.translate(_CTX, src), src, layer_id=raw_layer_id)
            else:
                src = "Referenced cable feature {fid} does not exist in layer {layer}"
                message = _safe_format(
                    QCoreApplication.translate(_CTX, src), src,
                    fid=raw_fid, layer=cable_layer.name())
            yield ValidationIssue(
                rule_id=rule_id, severity=Severity.ERROR, category=_CAT_REFERENTIAL,
                message=message,
                layer_name=layer.name(), layer_id=layer.id(),
                feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                where=_feature_xy(feat),
                details={"cable_layer_id": str(raw_layer_id), "cable_fid": raw_fid},
            )
    return check


def _check_fk_spatial(ctx):
    """A resolvable cable reference whose point sits far from that cable usually
    means the cable was re-routed after the slack/break was placed."""
    from qgis.core import QgsGeometry

    tol = ctx.config.tol
    for canonical in _FK_LAYERS:
        for layer, feat, raw_layer_id, raw_fid in _fk_rows(ctx, canonical):
            _cable_layer, cable_feat = _resolve_cable(ctx, raw_layer_id, raw_fid)
            if cable_feat is None:
                continue  # broken links are B1/B2's finding, not this one
            point = _first_point(feat.geometry())
            cable_geom = cable_feat.geometry()
            if point is None or cable_geom is None or cable_geom.isNull():
                continue
            distance = QgsGeometry.fromPointXY(point).distance(cable_geom)
            if distance <= tol:
                continue
            src = ("Feature is {distance} from the cable it references "
                   "(tolerance {tol}) -- the cable may have been re-routed")
            yield ValidationIssue(
                rule_id="B3", severity=Severity.WARNING, category=_CAT_REFERENTIAL,
                message=_safe_format(
                    QCoreApplication.translate(_CTX, src), src,
                    distance=_fmt(distance), tol=_fmt(tol)),
                layer_name=layer.name(), layer_id=layer.id(),
                feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                where=(point.x(), point.y()),
                details={"distance": distance, "tolerance": tol,
                         "cable_fid": raw_fid},
            )


# ---------------------------------------------------------------------------
# B4 — identity invariant (validates the WP1 fiberq_uuid guarantee at rest)
# ---------------------------------------------------------------------------

def _check_identity(ctx):
    from qgis.core import NULL
    from ..utils.uuid_utils import FIBERQ_UUID_FIELD

    seen = {}  # uuid value -> (layer_name, feature_id) of its first occurrence
    for layers in ctx.layers_by_canonical.values():
        for layer in layers:
            idx = layer.fields().indexOf(FIBERQ_UUID_FIELD)
            if idx < 0:
                yield ValidationIssue(
                    rule_id="B4", severity=Severity.ERROR, category=_CAT_IDENTITY,
                    message=QCoreApplication.translate(
                        _CTX, "Layer is missing the fiberq_uuid identity field"),
                    layer_name=layer.name(), layer_id=layer.id(),
                    fix_hint=QCoreApplication.translate(
                        _CTX, "Re-open the project so migration can add fiberq_uuid, "
                              "or re-create the layer."),
                )
                continue
            for feat in layer.getFeatures():
                value = feat.attribute(idx)
                if _is_blank(value, NULL):
                    yield ValidationIssue(
                        rule_id="B4", severity=Severity.ERROR, category=_CAT_IDENTITY,
                        message=QCoreApplication.translate(
                            _CTX, "Feature has no fiberq_uuid value"),
                        layer_name=layer.name(), layer_id=layer.id(),
                        feature_id=feat.id(), where=_feature_xy(feat),
                    )
                    continue
                key = str(value)
                if key in seen:
                    prev_layer, prev_fid = seen[key]
                    src = ("Duplicate fiberq_uuid — the same identity is already "
                           "used by feature {fid} in layer {layer}")
                    yield ValidationIssue(
                        rule_id="B4", severity=Severity.ERROR, category=_CAT_IDENTITY,
                        message=_safe_format(
                            QCoreApplication.translate(_CTX, src), src,
                            fid=prev_fid, layer=prev_layer),
                        layer_name=layer.name(), layer_id=layer.id(),
                        feature_id=feat.id(), fiberq_uuid=key, where=_feature_xy(feat),
                        details={"duplicate_of_layer": prev_layer,
                                 "duplicate_of_fid": prev_fid},
                    )
                else:
                    seen[key] = (layer.name(), feat.id())


# ---------------------------------------------------------------------------
# C1 — required attributes present
# ---------------------------------------------------------------------------

def _check_required_fields(ctx):
    from qgis.core import NULL

    for canonical, layers in ctx.layers_by_canonical.items():
        required = _required_fields_for(canonical)
        if not required:
            continue
        for layer in layers:
            names = set(layer.fields().names())
            for feat in layer.getFeatures():
                missing = [
                    f for f in required
                    if f not in names or _is_blank(feat.attribute(f), NULL)
                ]
                if not missing:
                    continue
                src = "Required field(s) missing or empty: {fields}"
                yield ValidationIssue(
                    rule_id="C1", severity=Severity.WARNING, category=_CAT_COMPLETENESS,
                    message=_safe_format(
                        QCoreApplication.translate(_CTX, src), src,
                        fields=", ".join(missing)),
                    layer_name=layer.name(), layer_id=layer.id(),
                    feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                    where=_feature_xy(feat), details={"missing": missing},
                )


# ---------------------------------------------------------------------------
# D1 — enum conformance (domains read from the schema, never hardcoded)
# ---------------------------------------------------------------------------

def _check_enum_conformance(ctx):
    from qgis.core import NULL

    for canonical, layers in ctx.layers_by_canonical.items():
        layer_schema = schema.get_layer_schema(canonical)
        if layer_schema is None:
            continue
        enum_fields = [
            (f.key, _allowed_domain(f)) for f in layer_schema.fields
            if f.value_map or f.options
        ]
        enum_fields = [(key, dom) for key, dom in enum_fields if dom]
        if not enum_fields:
            continue
        for layer in layers:
            names = set(layer.fields().names())
            active = [(key, dom) for key, dom in enum_fields if key in names]
            for feat in layer.getFeatures():
                for key, allowed in active:
                    value = feat.attribute(key)
                    if _is_blank(value, NULL):
                        continue  # emptiness is C1's concern, not D1's
                    if str(value) in allowed:
                        continue
                    src = ("Field {field}: value {value} is not one of the "
                           "allowed values ({allowed})")
                    yield ValidationIssue(
                        rule_id="D1", severity=Severity.WARNING, category=_CAT_DOMAIN,
                        message=_safe_format(
                            QCoreApplication.translate(_CTX, src), src,
                            field=key, value=value,
                            allowed=", ".join(sorted(allowed))),
                        layer_name=layer.name(), layer_id=layer.id(),
                        feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                        where=_feature_xy(feat),
                        details={"field": key, "value": str(value),
                                 "allowed": sorted(allowed)},
                    )


# ---------------------------------------------------------------------------
# Registry — [core] rules shipping in v1.4.0. Append as the engine grows;
# keep each rule independent (the runner continues past a failing one).
# ---------------------------------------------------------------------------

RULES = [
    ValidationRule(
        id="A1",
        title=QT_TRANSLATE_NOOP(_CTX, "Cable endpoints are connected"),
        category=_CAT_TOPOLOGY,
        default_severity=Severity.WARNING,
        check=_check_cable_dangles,
        applies_to=_CABLE_LAYERS,
    ),
    ValidationRule(
        id="A2",
        title=QT_TRANSLATE_NOOP(_CTX, "Cable endpoints are not near-misses"),
        category=_CAT_TOPOLOGY,
        default_severity=Severity.INFO,
        check=_check_near_miss,
        applies_to=_CABLE_LAYERS,
    ),
    ValidationRule(
        id="A3",
        title=QT_TRANSLATE_NOOP(_CTX, "Elements are attached to the network"),
        category=_CAT_TOPOLOGY,
        default_severity=Severity.WARNING,
        check=_check_orphan_elements,
        applies_to=_NODE_LAYERS,
    ),
    ValidationRule(
        id="B1",
        title=QT_TRANSLATE_NOOP(_CTX, "Optical slack references an existing cable"),
        category=_CAT_REFERENTIAL,
        default_severity=Severity.ERROR,
        check=_fk_checker("Optical slack", "B1"),
        applies_to=("Optical slack",),
    ),
    ValidationRule(
        id="B2",
        title=QT_TRANSLATE_NOOP(_CTX, "Fiber break references an existing cable"),
        category=_CAT_REFERENTIAL,
        default_severity=Severity.ERROR,
        check=_fk_checker("Fiber break", "B2"),
        applies_to=("Fiber break",),
    ),
    ValidationRule(
        id="B3",
        title=QT_TRANSLATE_NOOP(_CTX, "Cable references are spatially coherent"),
        category=_CAT_REFERENTIAL,
        default_severity=Severity.WARNING,
        check=_check_fk_spatial,
        applies_to=_FK_LAYERS,
    ),
    ValidationRule(
        id="B4",
        title=QT_TRANSLATE_NOOP(_CTX, "Feature identity present and unique"),
        category=_CAT_IDENTITY,
        default_severity=Severity.ERROR,
        check=_check_identity,
    ),
    ValidationRule(
        id="C1",
        title=QT_TRANSLATE_NOOP(_CTX, "Required attributes present"),
        category=_CAT_COMPLETENESS,
        default_severity=Severity.WARNING,
        check=_check_required_fields,
    ),
    ValidationRule(
        id="D1",
        title=QT_TRANSLATE_NOOP(_CTX, "Attribute values within allowed domain"),
        category=_CAT_DOMAIN,
        default_severity=Severity.WARNING,
        check=_check_enum_conformance,
    ),
]
