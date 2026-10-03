"""Bring stored lengths back into line with the geometry they describe.

Companion to the D3 validation rule. D3 reports that a stored length disagrees
with the drawn feature; this rewrites it so it agrees. The two share a tolerance
(:class:`ValidationConfig`) on purpose, so "recalculate, then validate" is
guaranteed to clear every D3 finding rather than leaving a residue just under or
over the threshold.

Two reasons a stored length drifts:

* it was written in map units by a code path that predates
  :mod:`fiberq.utils.measure` -- 41% long in Web Mercator at Serbian latitudes;
* the geometry was edited afterwards and nothing recomputed the attribute.

Both look identical in the data, and both are fixed the same way.

The work is split into :func:`plan_recalculation` (reads, decides, writes
nothing) and :func:`apply_recalculation` (writes). That lets the UI show the user
exactly what is about to change to their project before anything is committed,
and lets the tests assert the decision without touching an edit buffer.

:func:`length_values` is the per-feature arithmetic on its own, with no QGIS
editing anywhere near it. Everything that stores a length goes through it --
this module, :mod:`fiberq.core.length_sync`, the route split and the
infrastructure cut -- so the value a feature ends up with does not depend on
which of them happened to write it.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..models import schema
from ..utils.logger import get_logger
from ..utils.measure import ground_length, measures_metres
from .validation_manager import ValidationConfig, ValidationContext

logger = get_logger(__name__)

#: Canonical layer name -> the field holding its length in metres. Mirrors
#: validation_rules._STORED_LENGTH_FIELD; D3 and this module must agree on which
#: field is authoritative or one would keep reporting what the other "fixed".
STORED_LENGTH_FIELD = {
    "Aerial cables": "duzina_m",
    "Underground cables": "duzina_m",
    "PE pipes": "duzina_m",
    "Transition pipes": "duzina_m",
    "Route": "duzina",
}

#: Fields derived from the metre value, recomputed alongside it.
KM_FIELD = "duzina_km"
TOTAL_FIELD = "total_len_m"
SLACK_FIELD = "slack_m"


@dataclass
class LengthChange:
    """One attribute that would be (or was) rewritten."""

    layer_name: str
    layer_id: str
    feature_id: int
    field_name: str
    old_value: Optional[float]
    new_value: float

    @property
    def delta(self) -> float:
        return self.new_value - (self.old_value or 0.0)

    @property
    def ratio(self) -> Optional[float]:
        if not self.old_value:
            return None
        return self.old_value / self.new_value if self.new_value else None


@dataclass
class RecalcPlan:
    """What :func:`plan_recalculation` decided, before anything is written."""

    changes: List[LengthChange] = field(default_factory=list)
    #: Layers that could not be measured meaningfully (no usable ellipsoid).
    skipped_layers: List[str] = field(default_factory=list)
    #: Layers examined and already correct, for an honest "nothing to do".
    layers_seen: List[str] = field(default_factory=list)
    #: Layers that raised while being planned, so "nothing to do" is never a lie.
    failed_layers: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.changes)

    @property
    def feature_count(self) -> int:
        """Features touched, not attributes -- one feature can carry three."""
        return len({(c.layer_id, c.feature_id) for c in self.changes})

    def counts_by_layer(self) -> Dict[str, int]:
        """Features per layer -- the same unit as :attr:`feature_count`.

        Counting attribute writes here instead would make the per-layer numbers
        add up to more than the headline, since one feature can carry three.
        """
        seen: Dict[str, set] = {}
        for c in self.changes:
            seen.setdefault(c.layer_name, set()).add(c.feature_id)
        return {name: len(ids) for name, ids in seen.items()}

    def largest_change(self) -> Optional[LengthChange]:
        """The change with the biggest absolute difference, for a preview line."""
        scored = [c for c in self.changes if c.old_value is not None]
        return max(scored, key=lambda c: abs(c.delta), default=None)


@dataclass
class RecalcOutcome:
    """What :func:`apply_recalculation` actually managed to commit."""

    applied: List[LengthChange] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    #: Layers left untouched because the user has them open for editing. Not a
    #: failure -- a "save your edits and run this again".
    blocked_by_edits: List[str] = field(default_factory=list)

    @property
    def feature_count(self) -> int:
        return len({(c.layer_id, c.feature_id) for c in self.applied})


def _disagrees(stored, computed, config) -> bool:
    """Same test D3 uses, so recalculating clears exactly what it reports."""
    if stored is None:
        return True
    allowed = max(config.length_abs_tol, abs(computed) * config.length_rel_tol)
    return abs(stored - computed) > allowed


def _as_float(value) -> Optional[float]:
    try:
        from qgis.core import NULL
        if value is None or value == NULL:
            return None
    except ImportError:
        if value is None:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


#: Returned by :func:`_attribute` when a value cannot be read at all. Distinct
#: from NULL on purpose: a NULL slack reads fine and means zero, an unreadable
#: one means "leave total_len_m alone".
_UNREADABLE = object()


def _attribute(feat, layer, name):
    """``feat[name]``, also on a feature that carries values but no field names.

    ``QgsVectorLayer.addFeature()`` keeps the feature it is handed and checks
    only the attribute *count*, so a feature built the short way --
    ``QgsFeature()`` then ``setAttributes([...])``, which is what the Python
    console and other plugins produce -- sits in the edit buffer with no field
    names at all, and ``feat.attribute("slack_m")`` raises ``KeyError`` on it.
    The values are still positional, so the layer's own field index reads them.

    Measured on 3.22, 3.44 and 4.0, before this existed: one such feature in a
    commit raised inside the length sweep and cost *every other feature in that
    layer* its refresh -- a vertex move of 655.81 m stayed stored as 0.0.
    """
    try:
        return feat.attribute(name)
    except KeyError:
        pass
    try:
        index = layer.fields().indexOf(name)
        if 0 <= index < len(feat.attributes()):
            return feat.attribute(index)
    except (AttributeError, RuntimeError, TypeError) as e:
        logger.debug(f"Could not read {name} by position either: {e}")
    return _UNREADABLE


def length_field_for(layer) -> Optional[str]:
    """The field holding ``layer``'s length in metres, or None if it stores none.

    Resolved from the **canonical layer name**, never from the fields a layer
    happens to carry. "Has a ``duzina_m`` field" is the trap: the Optical slack
    layer has one too, on a point geometry, and it holds the slack the user
    typed. Measuring a point and writing the result there would silently wipe
    every slack value in the project.
    """
    try:
        canonical = schema.canonical_layer_name(layer.name())
    except Exception as e:
        logger.warning(f"Could not resolve a layer name to the FiberQ schema: {e}")
        return None
    return STORED_LENGTH_FIELD.get(canonical) if canonical else None


def length_values(feat, layer, geom=None, length_field=None, names=None,
                  project=None) -> Dict[str, float]:
    """The values ``feat``'s length fields should hold, as ``{field: value}``.

    The one place the arithmetic lives: metres from
    :func:`~fiberq.utils.measure.ground_length`, ``duzina_km`` rounded to two
    decimals, ``total_len_m`` = those metres plus the stored slack. ``slack_m``
    is a user decision and is read, never returned.

    Pure on purpose -- it measures and divides and touches no edit buffer, no
    attribute and no project setting. That is what lets the live
    ``geometryChanged`` hook, the commit sweep, the manual recalculation and
    FiberQ's own creators (route split, infrastructure cut) all share it, so the
    number a feature gets cannot depend on which of them wrote it.

    ``geom`` overrides ``feat.geometry()``, for a caller holding the new
    geometry before the feature carries it (the live hook gets it from the
    signal). ``length_field`` and ``names`` are hoists for a loop that already
    resolved them once per layer.

    Returns an empty dict when there is nothing to write -- not a FiberQ layer
    that stores a length, the field is missing, the geometry is null or empty,
    or the measurement came back negative. Callers treat that as "skip this
    feature", never as "write zero".
    """
    if length_field is None:
        length_field = length_field_for(layer)
    if not length_field:
        return {}

    if names is None:
        names = set(layer.fields().names())
    if length_field not in names:
        return {}

    if geom is None:
        geom = feat.geometry()
    if geom is None or geom.isNull() or geom.isEmpty():
        return {}  # nothing to measure; E2 reports the geometry itself

    computed = ground_length(geom, layer, project=project)

    # A zero-length geometry is E2's finding, but its stored length is still
    # wrong and D3 still reports it. Setting it to 0 is the honest answer and
    # keeps the "recalculate, then validate" guarantee true. A negative result
    # cannot be honest, so it is skipped instead.
    if computed < 0:
        return {}

    values = {length_field: computed}

    # duzina_km is derived, and 2 decimals is the stored precision D3 checks.
    if KM_FIELD in names:
        values[KM_FIELD] = round(computed / 1000.0, 2)

    # total_len_m = laid length + slack. Only where the layer actually carries
    # the field: a cable table with total_len_m but no slack_m is reachable
    # today (cable_manager refuses to add fields on providers it cannot alter),
    # and feat.attribute() raises KeyError on a name the layer does not have.
    if TOTAL_FIELD in names:
        slack = 0.0
        if SLACK_FIELD in names:
            raw = _attribute(feat, layer, SLACK_FIELD)
            if raw is _UNREADABLE:
                # The length is still right, the total cannot be: writing
                # `computed + 0` here would throw the user's slack away.
                return values
            slack = _as_float(raw) or 0.0
        values[TOTAL_FIELD] = computed + slack

    return values


def length_writes(feat, layer, geom=None, length_field=None, names=None,
                  project=None) -> Dict[str, float]:
    """:func:`length_values`, minus the fields that already hold that value.

    Exact comparison, deliberately: D3's tolerance exists so that recalculating
    clears exactly what the rule reports, and it has no business deciding
    whether a write is worth making. The point here is only to leave the edit
    buffer alone when a gesture did not actually change a length, so a save
    stays as small as the user's own edit.
    """
    values = length_values(feat, layer, geom=geom, length_field=length_field,
                           names=names, project=project)
    writes = {}
    for name, value in values.items():
        # Unreadable, not NULL: the feature predates the field (an older table,
        # a field added mid-session) or carries no field names at all. Either
        # way it has no value to agree with, so write one.
        raw = _attribute(feat, layer, name)
        stored = None if raw is _UNREADABLE else _as_float(raw)
        if stored != value:
            writes[name] = value
    return writes


def plan_recalculation(project=None, config: Optional[ValidationConfig] = None) -> RecalcPlan:
    """Work out which stored lengths disagree with their geometry. Writes nothing."""
    if project is None:
        from qgis.core import QgsProject
        project = QgsProject.instance()

    config = config or ValidationConfig()
    ctx = ValidationContext(project, config)
    plan = RecalcPlan()

    for canonical, length_field in STORED_LENGTH_FIELD.items():
        for layer in ctx.layers_for(canonical):
            plan.layers_seen.append(layer.name())
            try:
                _plan_layer(plan, layer, length_field, config, project)
            except Exception as e:
                # One awkward layer must not cost the user every other fix in the
                # project, the way an escaping KeyError used to.
                logger.warning(f"Could not plan lengths for {layer.name()}: {e}")
                plan.failed_layers.append(f"{layer.name()}: {e}")

    return plan


def _plan_layer(plan, layer, length_field, config, project):
    """Decide the changes for one layer. Raises only on genuinely unexpected faults."""
    if not measures_metres(layer, project=project):
        # Measuring here would produce map units or degrees; refuse rather than
        # write a number that is confidently wrong.
        plan.skipped_layers.append(layer.name())
        return

    names = set(layer.fields().names())
    if length_field not in names:
        return

    for feat in layer.getFeatures():
        # One shared computation, via the same helper the live sync and the
        # creators use: a second copy of these rules here is how the manual
        # repair and the automatic one would start disagreeing.
        expected = length_values(feat, layer, length_field=length_field,
                                 names=names, project=project)
        if not expected:
            continue

        computed = expected[length_field]
        stored = _as_float(feat.attribute(length_field))
        if _disagrees(stored, computed, config):
            plan.changes.append(LengthChange(
                layer.name(), layer.id(), feat.id(),
                length_field, stored, computed))

        # duzina_km is derived; refresh it whenever it no longer follows,
        # even if the metre value itself was already right. Its own hard 0.005
        # matches D3's half-ulp check on a 2-decimal field.
        if KM_FIELD in expected:
            expected_km = expected[KM_FIELD]
            stored_km = _as_float(feat.attribute(KM_FIELD))
            if stored_km is None or abs(stored_km - expected_km) > 0.005:
                plan.changes.append(LengthChange(
                    layer.name(), layer.id(), feat.id(),
                    KM_FIELD, stored_km, expected_km))

        # total_len_m = laid length + slack. Slack is a user decision, so the
        # helper reads it and never returns it for writing.
        if TOTAL_FIELD in expected:
            expected_total = expected[TOTAL_FIELD]
            stored_total = _as_float(feat.attribute(TOTAL_FIELD))
            if _disagrees(stored_total, expected_total, config):
                plan.changes.append(LengthChange(
                    layer.name(), layer.id(), feat.id(),
                    TOTAL_FIELD, stored_total, expected_total))


def apply_recalculation(plan: RecalcPlan, project=None) -> RecalcOutcome:
    """Commit a plan produced by :func:`plan_recalculation`.

    Each layer is committed in its own edit session, so one uncooperative layer
    (read-only source, locked GeoPackage) does not roll back the others. Failures
    are collected and returned rather than raised -- the caller shows them.
    """
    if project is None:
        from qgis.core import QgsProject
        project = QgsProject.instance()

    outcome = RecalcOutcome()
    if not plan.changes:
        return outcome

    by_layer: Dict[str, List[LengthChange]] = {}
    for change in plan.changes:
        by_layer.setdefault(change.layer_id, []).append(change)

    for layer_id, changes in by_layer.items():
        layer = project.mapLayer(layer_id)
        if layer is None:
            outcome.failures.append(f"{changes[0].layer_name}: layer is gone")
            continue

        name = layer.name()
        try:
            # An already-open edit session is the everyday state right after
            # drawing something, and startEditing() simply returns False for it.
            # Committing here would also commit the user's unsaved work, so the
            # layer is left alone -- but say why, rather than implying the data
            # source is read-only.
            if layer.isEditable():
                outcome.blocked_by_edits.append(name)
                continue
            if not layer.startEditing():
                outcome.failures.append(
                    f"{name}: could not be opened for editing (read-only source?)")
                continue

            indexes = {}
            written = []
            for change in changes:
                idx = indexes.get(change.field_name)
                if idx is None:
                    idx = layer.fields().indexFromName(change.field_name)
                    indexes[change.field_name] = idx
                if idx < 0:
                    # The field vanished between planning and applying; do not
                    # later report it as applied.
                    logger.debug(f"{name}: field {change.field_name} is gone, skipping")
                    continue
                if layer.changeAttributeValue(change.feature_id, idx, change.new_value):
                    written.append(change)

            if layer.commitChanges():
                outcome.applied.extend(written)
                layer.triggerRepaint()
            else:
                errors = '; '.join(layer.commitErrors()[:3])
                outcome.failures.append(f"{name}: {errors or 'commit refused'}")
                layer.rollBack()
        except Exception as e:
            logger.warning(f"Length recalculation failed on {name}: {e}")
            outcome.failures.append(f"{name}: {e}")
            try:
                layer.rollBack()
            except Exception as rollback_error:
                logger.debug(f"Rollback also failed on {name}: {rollback_error}")

    return outcome


def recalculate_lengths(project=None, config: Optional[ValidationConfig] = None) -> RecalcOutcome:
    """Plan and apply in one call. The UI uses the two phases separately."""
    return apply_recalculation(plan_recalculation(project, config), project)
