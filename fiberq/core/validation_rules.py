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
