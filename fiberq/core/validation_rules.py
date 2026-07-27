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

# D2 numeric bounds: field -> (minimum, maximum, exclusive_min). ``None`` means
# unbounded on that side. Only applied to fields the schema declares int/double,
# which is why pipe ``kapacitet`` (text, as-built) is skipped rather than
# mis-parsed -- the same schema-driven approach D1 uses for enums.
_NUMERIC_BOUNDS = {
    "broj_vlakana": (0, 1152, True),    # a cable with zero fibres is not a cable
    "broj_cevcica": (0, None, False),
    "fi": (0, None, True),              # duct diameter in mm
    "visina": (0, None, True),          # pole height in m
    "kapacitet": (0, None, False),
    "slabljenje_dbkm": (0, 10, False),  # dB/km; typical single-mode is 0.2-0.4
    "duzina_m": (0, None, False),
    "duzina": (0, None, False),
    "duzina_km": (0, None, False),
    "total_len_m": (0, None, False),
    "slack_m": (0, None, False),
    "area_m2": (0, None, False),
    "perim_m": (0, None, False),
}

# D3: the field holding a line layer's stored length. Route is the odd one out --
# it stores ``duzina`` (m) plus ``duzina_km``, every other line layer uses
# ``duzina_m``.
_STORED_LENGTH_FIELD = {
    "Aerial cables": "duzina_m",
    "Underground cables": "duzina_m",
    "PE pipes": "duzina_m",
    "Transition pipes": "duzina_m",
    "Route": "duzina",
}

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
    """Vertex lists of every line part with at least two vertices.

    Guards on the *actual* geometry type rather than trusting the schema: a layer
    whose real geometry differs from its declared type would otherwise raise
    ("Point geometry cannot be converted to a polyline") instead of simply having
    no endpoints to check.
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return []
    from qgis.core import QgsWkbTypes
    if geom.type() != QgsWkbTypes.GeometryType.LineGeometry:
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
# D2 -- numeric ranges
# ---------------------------------------------------------------------------

def _as_number(value, null):
    """Coerce an attribute to float, or None when blank / not numeric."""
    if _is_blank(value, null):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bound_text(low, high, exclusive) -> str:
    """Human-readable bound, e.g. "> 0 and <= 1152". Not translated: it is a
    mathematical expression, and its pieces are numbers."""
    low_part = f"> {_fmt(low)}" if exclusive else f">= {_fmt(low)}"
    if high is None:
        return low_part
    return f"{low_part} and <= {_fmt(high)}"


def _check_numeric_ranges(ctx):
    from qgis.core import NULL

    for canonical, layers in ctx.layers_by_canonical.items():
        layer_schema = schema.get_layer_schema(canonical)
        if layer_schema is None:
            continue
        # Only fields the schema declares numeric. Pipe `kapacitet` is text
        # (as-built) and is skipped rather than mis-parsed -- the same
        # schema-driven approach D1 uses for enum domains.
        checks = [
            (fd.key, _NUMERIC_BOUNDS[fd.key], fd.units)
            for fd in layer_schema.fields
            if fd.key in _NUMERIC_BOUNDS and fd.field_type in ("int", "double")
        ]
        if not checks:
            continue
        for layer in layers:
            names = set(layer.fields().names())
            active = [c for c in checks if c[0] in names]
            for feat in layer.getFeatures():
                for key, (low, high, exclusive), units in active:
                    number = _as_number(feat.attribute(key), NULL)
                    if number is None:
                        continue  # emptiness is C1's concern
                    too_low = number <= low if exclusive else number < low
                    too_high = high is not None and number > high
                    if not (too_low or too_high):
                        continue
                    src = "Field {field}: {value} is out of range (expected {bound})"
                    yield ValidationIssue(
                        rule_id="D2", severity=Severity.WARNING, category=_CAT_DOMAIN,
                        message=_safe_format(
                            QCoreApplication.translate(_CTX, src), src,
                            field=key, value=_fmt(number),
                            bound=_bound_text(low, high, exclusive)),
                        layer_name=layer.name(), layer_id=layer.id(),
                        feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                        where=_feature_xy(feat),
                        details={"field": key, "value": number, "units": units,
                                 "min": low, "max": high, "exclusive_min": exclusive},
                    )


# ---------------------------------------------------------------------------
# D3 -- length coherence (needs a projected CRS; see E1)
# ---------------------------------------------------------------------------

def _is_metric(layer) -> bool:
    """True when the layer's CRS measures in linear units rather than degrees."""
    crs = layer.crs()
    return bool(crs and crs.isValid() and not crs.isGeographic())


def _disagrees(stored, computed, cfg) -> bool:
    """Whether two lengths differ by more than the configured tolerance."""
    allowed = max(cfg.length_abs_tol, abs(computed) * cfg.length_rel_tol)
    return abs(stored - computed) > allowed


def _check_length_coherence(ctx):
    """Stored lengths should agree with the geometry, and with each other.

    Length comparisons are meaningless in a geographic CRS -- geometry length
    comes out in degrees while the stored value is metres -- so the check is
    skipped there and *says so*, rather than emitting a page of false warnings.
    """
    from qgis.core import NULL

    cfg = ctx.config
    for canonical, stored_field in _STORED_LENGTH_FIELD.items():
        for layer in ctx.layers_for(canonical):
            names = set(layer.fields().names())

            if not _is_metric(layer):
                src = ("Length checks skipped: they need a projected (metric) CRS, "
                       "but this layer uses {crs}")
                yield ValidationIssue(
                    rule_id="D3", severity=Severity.INFO, category=_CAT_DOMAIN,
                    message=_safe_format(
                        QCoreApplication.translate(_CTX, src), src,
                        crs=layer.crs().authid() or "?"),
                    layer_name=layer.name(), layer_id=layer.id(),
                    details={"skipped": True, "crs": layer.crs().authid()},
                )
                continue

            for feat in layer.getFeatures():
                geom = feat.geometry()
                if geom is None or geom.isNull() or geom.isEmpty():
                    continue  # E2's concern
                computed = geom.length()

                # 1. stored length vs the geometry it describes
                if stored_field in names:
                    stored = _as_number(feat.attribute(stored_field), NULL)
                    if stored is not None and stored > 0 and _disagrees(stored, computed, cfg):
                        src = ("Stored {field} ({stored}) does not match the drawn "
                               "geometry ({computed})")
                        yield ValidationIssue(
                            rule_id="D3", severity=Severity.WARNING, category=_CAT_DOMAIN,
                            message=_safe_format(
                                QCoreApplication.translate(_CTX, src), src,
                                field=stored_field, stored=_fmt(stored),
                                computed=_fmt(computed)),
                            layer_name=layer.name(), layer_id=layer.id(),
                            feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                            where=_feature_xy(feat),
                            details={"field": stored_field, "stored": stored,
                                     "computed": computed},
                        )

                # 2. cable total = laid length + slack
                if {"total_len_m", "duzina_m", "slack_m"} <= names:
                    total = _as_number(feat.attribute("total_len_m"), NULL)
                    base = _as_number(feat.attribute("duzina_m"), NULL)
                    slack = _as_number(feat.attribute("slack_m"), NULL)
                    if None not in (total, base, slack) and total > 0:
                        expected = base + slack
                        if _disagrees(total, expected, cfg):
                            src = ("total_len_m ({total}) should equal duzina_m + "
                                   "slack_m ({expected})")
                            yield ValidationIssue(
                                rule_id="D3", severity=Severity.WARNING,
                                category=_CAT_DOMAIN,
                                message=_safe_format(
                                    QCoreApplication.translate(_CTX, src), src,
                                    total=_fmt(total), expected=_fmt(expected)),
                                layer_name=layer.name(), layer_id=layer.id(),
                                feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                                where=_feature_xy(feat),
                                details={"total_len_m": total, "expected": expected},
                            )

                # 3. route kilometres agree with metres
                if {"duzina", "duzina_km"} <= names:
                    metres = _as_number(feat.attribute("duzina"), NULL)
                    km = _as_number(feat.attribute("duzina_km"), NULL)
                    if None not in (metres, km) and km > 0:
                        expected = metres / 1000.0
                        allowed = max(cfg.length_abs_tol / 1000.0,
                                      abs(expected) * cfg.length_rel_tol)
                        if abs(km - expected) > allowed:
                            src = ("duzina_km ({km}) does not match duzina/1000 "
                                   "({expected})")
                            yield ValidationIssue(
                                rule_id="D3", severity=Severity.WARNING,
                                category=_CAT_DOMAIN,
                                message=_safe_format(
                                    QCoreApplication.translate(_CTX, src), src,
                                    km=_fmt(km), expected=_fmt(expected)),
                                layer_name=layer.name(), layer_id=layer.id(),
                                feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                                where=_feature_xy(feat),
                                details={"duzina_km": km, "expected": expected},
                            )


# ---------------------------------------------------------------------------
# E1 -- CRS consistency
# ---------------------------------------------------------------------------

def _check_crs_consistency(ctx):
    """FiberQ layers should share one CRS, and a metric one where lengths matter."""
    seen = {}
    for canonical, layers in ctx.layers_by_canonical.items():
        for layer in layers:
            crs = layer.crs()
            authid = (crs.authid() if crs and crs.isValid() else "") or "?"
            seen.setdefault(authid, []).append(layer.name())

            if canonical in _STORED_LENGTH_FIELD and not _is_metric(layer):
                src = ("Layer uses a geographic CRS ({crs}); length and area checks "
                       "need a projected CRS in metres")
                yield ValidationIssue(
                    rule_id="E1", severity=Severity.WARNING, category=_CAT_DOMAIN,
                    message=_safe_format(
                        QCoreApplication.translate(_CTX, src), src, crs=authid),
                    layer_name=layer.name(), layer_id=layer.id(),
                    details={"crs": authid, "geographic": True},
                )

    if len(seen) > 1:
        src = "FiberQ layers do not all share one CRS: {list}"
        yield ValidationIssue(
            rule_id="E1", severity=Severity.WARNING, category=_CAT_DOMAIN,
            message=_safe_format(
                QCoreApplication.translate(_CTX, src), src,
                list=", ".join(sorted(seen))),
            details={"crs_list": sorted(seen), "layers_by_crs": seen},
        )


# ---------------------------------------------------------------------------
# E2 -- geometry health
# ---------------------------------------------------------------------------

def _check_geometry_validity(ctx):
    """Missing geometry is an error; degenerate or self-crossing shapes warn.

    Dispatches on the feature's *actual* geometry type, not the schema's declared
    one. Trusting the schema would call ``length()`` on a point (always 0) and
    report a phantom zero-length line whenever a layer's real geometry differs
    from its declaration.
    """
    from qgis.core import QgsWkbTypes

    for canonical, layers in ctx.layers_by_canonical.items():
        layer_schema = schema.get_layer_schema(canonical)
        expected = layer_schema.geometry if layer_schema else ""
        for layer in layers:
            for feat in layer.getFeatures():
                geom = feat.geometry()

                if geom is None or geom.isNull() or geom.isEmpty():
                    src = "Feature has no geometry"
                    yield ValidationIssue(
                        rule_id="E2", severity=Severity.ERROR, category=_CAT_DOMAIN,
                        message=QCoreApplication.translate(_CTX, src),
                        layer_name=layer.name(), layer_id=layer.id(),
                        feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                        details={"expected_geometry": expected},
                    )
                    continue

                gtype = geom.type()
                if gtype == QgsWkbTypes.GeometryType.LineGeometry:
                    if geom.length() <= 0:
                        src = "Line has zero length"
                    elif not geom.isSimple():
                        # A self-crossing LineString is OGC-valid, so
                        # isGeosValid() will not catch it -- isSimple() does.
                        src = "Line crosses itself"
                    else:
                        continue
                elif gtype == QgsWkbTypes.GeometryType.PolygonGeometry:
                    if geom.area() <= 0:
                        src = "Polygon has zero area"
                    elif not geom.isGeosValid():
                        src = "Polygon boundary is self-intersecting"
                    else:
                        continue
                else:
                    continue

                yield ValidationIssue(
                    rule_id="E2", severity=Severity.WARNING, category=_CAT_DOMAIN,
                    message=QCoreApplication.translate(_CTX, src),
                    layer_name=layer.name(), layer_id=layer.id(),
                    feature_id=feat.id(), fiberq_uuid=_uuid_of(feat),
                    where=_feature_xy(feat),
                    details={"expected_geometry": expected},
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
    ValidationRule(
        id="D2",
        title=QT_TRANSLATE_NOOP(_CTX, "Numeric attributes within plausible ranges"),
        category=_CAT_DOMAIN,
        default_severity=Severity.WARNING,
        check=_check_numeric_ranges,
    ),
    ValidationRule(
        id="D3",
        title=QT_TRANSLATE_NOOP(_CTX, "Stored lengths agree with geometry"),
        category=_CAT_DOMAIN,
        default_severity=Severity.WARNING,
        check=_check_length_coherence,
        applies_to=tuple(_STORED_LENGTH_FIELD),
    ),
    ValidationRule(
        id="E1",
        title=QT_TRANSLATE_NOOP(_CTX, "Coordinate reference systems are consistent"),
        category=_CAT_DOMAIN,
        default_severity=Severity.WARNING,
        check=_check_crs_consistency,
    ),
    ValidationRule(
        id="E2",
        title=QT_TRANSLATE_NOOP(_CTX, "Geometries are present and well formed"),
        category=_CAT_DOMAIN,
        default_severity=Severity.ERROR,
        check=_check_geometry_validity,
    ),
]
