"""FiberQ schema migration runner (WP1b).

Upgrades a project's data and its schema-version marker from an older schema to
the current :data:`fiberq.models.schema.SCHEMA_VERSION`, then stamps the marker.

Design
------
* The marker is read/written via :mod:`fiberq.core.schema_version` (WP1a). A
  project with no marker reads back as the baseline version ``"0"``.
* Migrations are an ordered chain of :class:`Migration` steps. Each declares the
  schema version it brings a project *up to* and an idempotent ``apply`` callable.
* :func:`run_migrations` reads the stored version, runs every step whose target
  is ``> stored`` and ``<= SCHEMA_VERSION`` in ascending order, and -- only if all
  steps succeed -- stamps the project with the current version. Re-running on an
  already-current project is a no-op.
* Version strings (``"0"``, ``"1.0"``, future ``"1.1"``/``"2.0"``) are compared
  with an ordered numeric parse. WP1a's :func:`schema_version.needs_upgrade` is
  only an equality check, so the *ordering* lives here. A project stamped *newer*
  than the plugin understands is left untouched (never downgraded).

Persistence note: the marker is a ``QgsProject`` entry, so an on-load stamp only
becomes durable once the user saves the project (or exports to GeoPackage, which
also stamps it). Until then a re-open simply re-runs the idempotent migration.
"""
import functools
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from ..models.schema import SCHEMA_VERSION
from ..utils.logger import get_logger
from .schema_version import (
    BASELINE_VERSION,
    mark_project_current,
    read_project_schema_version,
)

logger = get_logger(__name__)

#: A well-formed schema version is a dotted run of integers ("0", "1.0", "1.10").
#: Anything else (a foreign / decorated / hand-edited marker like "v2.0" or
#: "1.0-rc1") is treated as UNKNOWN rather than silently coerced -- coercion
#: would neutralise the newer-than-plugin downgrade guard.
_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


# ---------------------------------------------------------------------------
# Ordered version comparison (WP1a only offers equality via needs_upgrade)
# ---------------------------------------------------------------------------

def _is_valid_version(version) -> bool:
    """True if ``version`` is a dotted run of integers we can order/compare."""
    return bool(_VERSION_RE.match(str(version).strip()))


def _version_key(version) -> tuple:
    """Parse a dotted version string into a tuple of ints for ordered compare.

    Non-numeric or empty parts collapse to ``0`` so ``"0"`` -> ``(0,)`` and
    ``"1.0"`` -> ``(1, 0)``. Callers pad to equal length before comparing, so
    ``"1"`` and ``"1.0"`` compare equal. Only call on values that pass
    :func:`_is_valid_version`; malformed input is handled up front in
    :func:`run_migrations`.
    """
    parts = []
    for chunk in str(version).split("."):
        try:
            parts.append(int(chunk))
        except (TypeError, ValueError):
            parts.append(0)
    return tuple(parts) or (0,)


def _padded(a, b):
    ka, kb = _version_key(a), _version_key(b)
    n = max(len(ka), len(kb))
    return ka + (0,) * (n - len(ka)), kb + (0,) * (n - len(kb))


def _version_lt(a, b) -> bool:
    """True if version ``a`` is strictly older than version ``b``."""
    ka, kb = _padded(a, b)
    return ka < kb


def _version_eq(a, b) -> bool:
    """True if versions ``a`` and ``b`` are equal (``"1"`` == ``"1.0"``)."""
    ka, kb = _padded(a, b)
    return ka == kb


#: Sort key aligned to _version_lt/_version_eq (padding-consistent, not raw
#: tuple length), so the chain orders identically to how versions compare.
_by_version = functools.cmp_to_key(
    lambda a, b: -1 if _version_lt(a, b) else (1 if _version_lt(b, a) else 0)
)


# ---------------------------------------------------------------------------
# Migration steps
# ---------------------------------------------------------------------------

@dataclass
class Migration:
    """One ordered, idempotent upgrade step.

    ``to_version`` is the schema version a project is at *after* this step runs.
    ``apply(project)`` performs the (idempotent) upgrade and returns a small
    detail dict for reporting, e.g. ``{layer_name: uuids_assigned}``.
    """
    to_version: str
    name: str
    description: str
    apply: Callable[..., dict]


def _apply_uuid_identity(project=None) -> dict:
    """0 -> 1.0: ensure the ``fiberq_uuid`` identity field exists and is filled.

    Delegates to the existing, idempotent UUID migrator. Pre-1.0 projects have no
    ``fiberq_uuid`` column; this adds it and assigns a UUID to every feature.
    Running again once every feature has one is a no-op (returns ``{}``).
    """
    from ..utils.uuid_utils import migrate_project_uuids
    return migrate_project_uuids(project)


#: The ordered migration chain. Append new steps as the schema evolves; keep each
#: one idempotent so a partially-migrated project can be re-run safely.
MIGRATIONS: List[Migration] = [
    Migration(
        to_version="1.0",
        name="uuid-identity",
        description="Add and backfill the fiberq_uuid identity field on all FiberQ layers.",
        apply=_apply_uuid_identity,
    ),
]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class MigrationReport:
    """Outcome of a :func:`run_migrations` call. Falsy when nothing ran."""
    from_version: str = BASELINE_VERSION
    to_version: str = SCHEMA_VERSION
    ran: bool = False
    steps: List[str] = field(default_factory=list)
    details: Dict[str, dict] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ran

    def _assigned(self) -> int:
        return sum(
            sum(d.values()) for d in self.details.values() if isinstance(d, dict)
        )

    def summary(self) -> str:
        """Human-readable one-liner for the message bar / logs."""
        if self.errors and not self.ran:
            return (f"Schema migration skipped ({self.from_version} -> "
                    f"{self.to_version}): {'; '.join(self.errors)}")
        msg = f"Upgraded project schema {self.from_version} -> {self.to_version}"
        assigned = self._assigned()
        if assigned:
            layers = sorted({
                name
                for d in self.details.values() if isinstance(d, dict)
                for name in d
            })
            msg += f" (assigned {assigned} UUIDs across {len(layers)} layers)"
        if self.errors:
            msg += f" with warnings: {'; '.join(self.errors)}"
        return msg


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_migrations(project=None) -> MigrationReport:
    """Upgrade ``project`` to the current schema version and stamp the marker.

    Reads the stored schema version; runs every migration step whose target is
    newer than the stored version (and no newer than the plugin's current
    version), in ascending order; then -- only if all steps succeed -- stamps the
    project with the current version. A project already at the current version, or
    stamped *newer* than the plugin understands, is left untouched.

    ``project`` defaults to the current ``QgsProject`` instance. Returns a
    :class:`MigrationReport` (falsy if nothing ran). Never raises: a failing step
    is captured in ``report.errors`` and the current version is not stamped, so a
    later run retries.
    """
    stored = read_project_schema_version(project)
    report = MigrationReport(from_version=stored, to_version=SCHEMA_VERSION)

    if not _is_valid_version(stored):
        # A foreign / decorated marker we can't order -- refuse to touch it rather
        # than coerce it and risk downgrading a genuinely newer project.
        report.errors.append(
            f"unrecognised stored schema version {stored!r}; not migrating"
        )
        logger.warning(report.errors[-1])
        return report

    if _version_eq(stored, SCHEMA_VERSION):
        # Already current. Converge an equal-but-non-identical marker ("1" ->
        # "1.0") to the canonical string so schema_version.needs_upgrade() (a raw
        # string compare) agrees with us. No data work, so ran stays False.
        if str(stored) != str(SCHEMA_VERSION):
            mark_project_current(project)
        return report

    if _version_lt(SCHEMA_VERSION, stored):
        # Project was stamped by a newer plugin build; never downgrade it.
        report.errors.append(
            f"project schema {stored} is newer than plugin schema {SCHEMA_VERSION}"
        )
        logger.warning(report.errors[-1])
        return report

    for step in sorted(MIGRATIONS, key=lambda s: _by_version(s.to_version)):
        # Only steps in the half-open range (stored, current].
        if not _version_lt(stored, step.to_version):
            continue
        if _version_lt(SCHEMA_VERSION, step.to_version):
            continue
        try:
            detail = step.apply(project) or {}
            report.details[step.name] = detail if isinstance(detail, dict) else {}
            report.steps.append(step.name)
        except Exception as e:
            # Capture, log, and stop the chain; the stamp is withheld below.
            report.errors.append(f"{step.name}: {e}")
            logger.warning(f"Schema migration step '{step.name}' failed: {e}")
            break

    if report.errors:
        # A step failed to complete: do NOT stamp current, so the next load
        # retries the migration rather than leaving the marker lying.
        return report

    mark_project_current(project)
    report.ran = True
    return report
