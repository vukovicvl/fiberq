"""FiberQ project validation engine (WP2, task 2.1).

A UI-independent, testable validation service. It runs a registry of rules over
the FiberQ layers in a project and returns a structured :class:`ValidationResult`
(severity, layer, feature id, message) rather than log lines, so the result can be
rendered to a panel (WP2 UI) or exported to a QA report (WP2 task 2.2).

Design notes
------------
* **No QGIS import at module top.** The data model (``Severity``,
  ``ValidationIssue``, ``ValidationResult``, ``ValidationRule``) and the rule
  registry are pure Python, so they can be imported and unit-tested without a
  running QGIS. Everything that needs QGIS (``QgsProject``, ``QgsSpatialIndex``,
  ``QgsVectorLayer``) is imported lazily inside the runner / context, which only
  execute under QGIS.
* **Canonical-name aware.** Layers are resolved via
  ``models.schema.canonical_layer_name`` over ``QgsProject.mapLayers()`` — never
  by ``mapLayersByName``, because some layers are created under a different name
  than their canonical one (e.g. the slack layer is created as "Optical slacks"
  but its canonical name is "Optical slack").
* **One failing rule never stops the run.** Each rule is wrapped; a failure is
  recorded in ``rule_errors`` (surfaced, not swallowed — WP4 theme) and the
  remaining rules still run. The runner never raises.

The rule registry and the individual checks live in :mod:`.validation_rules`.
"""
import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..models import schema
from ..utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Severity(enum.Enum):
    """Issue severity. The ``value`` is a stable identifier used in CSV/JSON
    exports and must not be translated."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# Sort/summary order: errors first.
SEVERITY_ORDER: Dict[Severity, int] = {
    Severity.ERROR: 0,
    Severity.WARNING: 1,
    Severity.INFO: 2,
}


@dataclass
class ValidationIssue:
    """One problem found by a rule, tied to a feature where possible."""
    rule_id: str
    severity: Severity
    category: str
    message: str
    layer_name: str = ""
    layer_id: str = ""
    feature_id: int = -1
    fiberq_uuid: str = ""
    where: Optional[Tuple[float, float]] = None  # map coords for zoom/flash
    details: Dict[str, Any] = field(default_factory=dict)
    fix_hint: str = ""


@dataclass
class ValidationRule:
    """A registry entry. ``check`` receives a :class:`ValidationContext` and
    yields :class:`ValidationIssue`. ``title`` is marked for translation with
    ``QT_TRANSLATE_NOOP('ValidationRules', ...)`` at its definition site and is
    translated at display time only. ``applies_to`` is a tuple of canonical layer
    names, or empty for a project-wide rule."""
    id: str
    title: str
    category: str
    default_severity: Severity
    check: Callable[["ValidationContext"], Iterable[ValidationIssue]]
    applies_to: Tuple[str, ...] = ()


@dataclass
class ValidationConfig:
    """Runtime configuration. Persisted to a project entry
    (``FiberQPlugin/validation``) by the UI layer so it travels with the project."""
    tol: float = 5.0  # snap tolerance in map units (reuses the relations default)
    disabled_rules: set = field(default_factory=set)
    severity_overrides: Dict[str, Severity] = field(default_factory=dict)

    def is_enabled(self, rule_id: str) -> bool:
        return rule_id not in self.disabled_rules

    def severity_for(self, rule: ValidationRule) -> Severity:
        return self.severity_overrides.get(rule.id, rule.default_severity)


@dataclass
class ValidationResult:
    """The structured outcome of a validation run."""
    project_name: str = ""
    crs: str = ""
    schema_version: str = ""
    plugin_version: str = ""
    timestamp: Optional[str] = None  # passed in — no wall-clock inside pure logic
    feature_counts: Dict[str, int] = field(default_factory=dict)
    issues: List[ValidationIssue] = field(default_factory=list)
    ran_rules: List[str] = field(default_factory=list)
    skipped_rules: List[str] = field(default_factory=list)
    rule_errors: List[str] = field(default_factory=list)

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)

    def counts_by_severity(self) -> Dict[str, int]:
        out = {s.value: 0 for s in Severity}
        for issue in self.issues:
            out[issue.severity.value] += 1
        return out

    def counts_by_category(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for issue in self.issues:
            out[issue.category] = out.get(issue.category, 0) + 1
        return out

    def sorted_issues(self) -> List[ValidationIssue]:
        """Issues ordered most-severe first, then by rule and layer."""
        return sorted(
            self.issues,
            key=lambda i: (SEVERITY_ORDER.get(i.severity, 9), i.rule_id, i.layer_name),
        )

    def summary(self) -> str:
        """Plain developer/log one-liner. The user-facing, translated message-bar
        text (with %n plurals) is built in the UI trigger, which is a QObject."""
        c = self.counts_by_severity()
        return (f"Validation: {c['error']} error(s), "
                f"{c['warning']} warning(s), {c['info']} info")


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

class ValidationContext:
    """Carries the resolved FiberQ layers, tolerances/config, and a lazily-built,
    shared ``QgsSpatialIndex`` per layer (built once, reused across topology
    rules). QGIS types are imported lazily so the module stays import-clean
    without QGIS."""

    def __init__(self, project, config: Optional[ValidationConfig] = None):
        self.project = project
        self.config = config or ValidationConfig()
        self._layers_by_canonical: Optional[Dict[str, list]] = None
        self._index_cache: Dict[str, Any] = {}

    @property
    def layers_by_canonical(self) -> Dict[str, list]:
        """Map canonical layer name -> list of live QgsVectorLayers, resolved via
        ``canonical_layer_name`` over every project layer (handles legacy/plural
        names). Cached for the lifetime of the run."""
        if self._layers_by_canonical is None:
            from qgis.core import QgsVectorLayer
            mapping: Dict[str, list] = {}
            for layer in self.project.mapLayers().values():
                if not isinstance(layer, QgsVectorLayer):
                    continue
                canonical = schema.canonical_layer_name(layer.name())
                if canonical is None:
                    continue
                mapping.setdefault(canonical, []).append(layer)
            self._layers_by_canonical = mapping
        return self._layers_by_canonical

    def layers_for(self, *canonical_names: str) -> list:
        """All live layers whose canonical name is one of ``canonical_names``
        (all resolved FiberQ layers when called with no argument)."""
        by = self.layers_by_canonical
        if not canonical_names:
            return [lyr for lst in by.values() for lyr in lst]
        return [lyr for name in canonical_names for lyr in by.get(name, [])]

    def spatial_index(self, layer):
        """Lazily build and cache a QgsSpatialIndex for ``layer`` (shared across
        topology rules; used from the wp2-topology branch onward)."""
        key = layer.id()
        if key not in self._index_cache:
            from qgis.core import QgsSpatialIndex
            self._index_cache[key] = QgsSpatialIndex(layer.getFeatures())
        return self._index_cache[key]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_validation(project=None, rules=None, config=None,
                   timestamp=None, plugin_version="") -> ValidationResult:
    """Run the validation rules over ``project`` and return a structured result.

    ``project`` defaults to the current ``QgsProject``. ``rules`` defaults to the
    full registry (:data:`fiberq.core.validation_rules.RULES`). Each rule is run
    inside a try/except: a failure is recorded in ``result.rule_errors`` and the
    remaining rules still run. Never raises.
    """
    from qgis.core import QgsProject

    if project is None:
        project = QgsProject.instance()
    cfg = config or ValidationConfig()
    ctx = ValidationContext(project, cfg)

    if rules is None:
        # Lazy import breaks the manager<->rules import cycle (rules imports the
        # data model above; the manager only needs the registry at call time).
        from .validation_rules import RULES
        rules = RULES

    result = ValidationResult(
        project_name=project.baseName() or project.fileName(),
        crs=_project_crs(project),
        schema_version=_project_schema_version(project),
        plugin_version=plugin_version,
        timestamp=timestamp,
        feature_counts=_feature_counts(ctx),
    )

    for rule in rules:
        if not cfg.is_enabled(rule.id):
            result.skipped_rules.append(rule.id)
            continue
        override = cfg.severity_overrides.get(rule.id)
        try:
            for issue in rule.check(ctx):
                # A rule sets each issue's severity; a configured per-rule override
                # (if any) wins, so a site can downgrade e.g. C1 to INFO.
                if override is not None:
                    issue.severity = override
                result.add(issue)
            result.ran_rules.append(rule.id)
        except Exception as e:  # one bad rule must not sink the run (WP4 theme)
            result.rule_errors.append(f"{rule.id}: {e}")
            logger.warning(f"Validation rule '{rule.id}' failed: {e}")

    logger.info(result.summary())
    return result


def _project_crs(project) -> str:
    crs = project.crs()
    return crs.authid() if crs and crs.isValid() else ""


def _project_schema_version(project) -> str:
    from .schema_version import read_project_schema_version
    return read_project_schema_version(project)


def _feature_counts(ctx: ValidationContext) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for canonical, layers in ctx.layers_by_canonical.items():
        counts[canonical] = sum(lyr.featureCount() for lyr in layers)
    return counts
