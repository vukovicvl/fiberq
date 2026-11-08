"""
FiberQ v1.3 - UUID Utilities

Provides UUID generation and migration for FiberQ Designer compatibility.
Every feature created by FiberQ gets a stable `fiberq_uuid` field that
persists across GPKG export/import and enables cross-system identification
between the QGIS plugin and FiberQ Designer web app.

Phase 0.1 of FiberQ Designer preparation.
"""

import uuid

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsMessageLog,
    Qgis
)
from .compat import FieldType, new_field

from .errors import OperationErrors, add_columns
from .logger import get_logger

logger = get_logger(__name__)

# Field name constant — used everywhere
FIBERQ_UUID_FIELD = "fiberq_uuid"
# Canonical display alias for the identity field. Applied consistently on every
# FiberQ layer via ensure_uuid_field so the attribute table never shows the raw
# column name on some layers and the alias on others.
FIBERQ_UUID_ALIAS = "FiberQ UUID"

# FiberQ layer recognition — the single source of truth shared by the uuid
# backfill (which layers to touch) and the WP1b migration runner's
# "is this a FiberQ project?" guard (project_has_fiberq_layers). Names cover the
# English and Serbian-legacy variants; the field signatures also catch renamed or
# custom layers that carry characteristic FiberQ fields.
FIBERQ_LAYER_NAMES = frozenset({
    # Point layers
    "Poles", "Stubovi",
    "Manholes", "OKNA",
    "ODF", "TB", "Patch panel", "Patch Panel",
    "OTB", "Indoor OTB", "Outdoor OTB", "Pole OTB",
    "TO", "Indoor TO", "Outdoor TO", "Pole TO", "Joint Closure TO",
    "Joint Closures", "Nastavci",
    "Optical slacks", "Opticke_rezerve", "Optical slack",
    "Fiber break", "Prekid vlakna",
    # Line layers
    "Route", "Trasa",
    "Aerial cables", "Kablovi_vazdusni",
    "Underground cables", "Kablovi_podzemni",
    "PE pipes", "PE cevi",
    "Transition pipes", "Prelazne cevi",
    # Polygon layers
    "Objects", "Objekti",
    "Service Area", "Service area", "Rejon",
})

FIBERQ_FIELD_SIGNATURES = frozenset({
    "naziv", "broj_okna", "tip_trase", "tip_kabla",
    "cable_layer_id", "broj_cevcica", "kapacitet",
    "fibers_per_tube", "total_fibers", "color_standard",
})


def layer_is_fiberq(layer) -> bool:
    """True if ``layer`` is a FiberQ-managed vector layer.

    Recognised by its (English or Serbian-legacy) name or by carrying
    characteristic FiberQ fields -- the same test the uuid backfill uses to
    decide which layers to touch. Non-vector layers are never FiberQ.
    """
    if not isinstance(layer, QgsVectorLayer):
        return False
    try:
        if layer.name() in FIBERQ_LAYER_NAMES:
            return True
        field_names = {f.name() for f in layer.fields()}
        return bool(field_names & FIBERQ_FIELD_SIGNATURES)
    except Exception:
        return False


def project_has_fiberq_layers(project=None) -> bool:
    """True if ``project`` contains at least one FiberQ-managed layer.

    The WP1b migration runner uses this to avoid stamping / announcing on a blank
    or non-FiberQ project: an unmarked project with no FiberQ layers is left
    completely untouched (no marker written, no dirty flag, no message).
    """
    project = project if project is not None else QgsProject.instance()
    try:
        return any(layer_is_fiberq(lyr) for lyr in project.mapLayers().values())
    except Exception:
        return False


def _log(msg):
    """Log to both FiberQ logger and QGIS Message Log panel."""
    try:
        logger.debug(msg)
    except Exception:
        # best-effort logging; nothing to fall back to
        pass  # nosec B110
    try:
        QgsMessageLog.logMessage(msg, "FiberQ UUID", Qgis.MessageLevel.Info)
    except Exception:
        # best-effort logging; nothing to fall back to
        pass  # nosec B110


def generate_uuid() -> str:
    """Generate a new UUID4 string for a FiberQ feature."""
    return str(uuid.uuid4())


def set_feature_uuid(feature, force_new=False):
    """
    Set fiberq_uuid on a feature if the field exists.

    Args:
        feature: QgsFeature to set UUID on
        force_new: If True, always generate new UUID (e.g. for copy/paste).
                   If False, only set if field is empty/NULL.
    """
    try:
        field_names = [f.name() for f in feature.fields()]
        if FIBERQ_UUID_FIELD not in field_names:
            return

        if force_new:
            feature.setAttribute(FIBERQ_UUID_FIELD, generate_uuid())
        else:
            current = feature.attribute(FIBERQ_UUID_FIELD)
            if current is None or (hasattr(current, 'isNull') and current.isNull()) or str(current).strip() == '':
                feature.setAttribute(FIBERQ_UUID_FIELD, generate_uuid())
    except Exception as e:
        _log(f"Error in set_feature_uuid: {e}")


class UuidMigrationError(RuntimeError):
    """A FiberQ layer's fiberq_uuid field could not be added or persisted.

    Raised by :func:`migrate_project_uuids` (and :func:`migrate_layer_uuids`) so
    the WP1b migration runner can withhold the schema-version stamp and retry on
    the next project load, instead of marking a project migrated while some layer
    never actually received its identity field on disk (a routine GPKG lock /
    read-only / no-ALTER condition).
    """


def _set_uuid_alias(layer):
    """Apply the canonical 'FiberQ UUID' display alias to the identity column.

    Only writes when the alias actually differs, so re-running on an already
    aliased layer does not needlessly mark the project modified.
    """
    try:
        idx = layer.fields().indexOf(FIBERQ_UUID_FIELD)
        if idx >= 0 and layer.attributeAlias(idx) != FIBERQ_UUID_ALIAS:
            layer.setFieldAlias(idx, FIBERQ_UUID_ALIAS)
    except Exception as e:
        logger.debug(f"could not set fiberq_uuid display alias: {e}")


def ensure_uuid_field(layer):
    """True when ``layer``'s data source has the fiberq_uuid column, which is
    added if it can be.

    The answer is about the data source, not the layer: ``layer.fields()`` also
    lists a column only an edit buffer holds. Until 1.6.0 that counted, and on
    a PostgreSQL table it was the usual outcome. The field had no type name, so
    the provider sent ``ADD COLUMN "fiberq_uuid"`` with nothing after it and
    refused it; a fallback then added the column through an edit session, whose
    commit failed the same way and left the layer in edit mode with the column
    pending -- and the answer was True. Every later save on that layer failed
    with "1 new attribute(s) not added" while the tools said "placed", and the
    project-open migration counted UUIDs it never wrote (measured on 3.22.16,
    3.40.15 and 4.2.3, PostGIS 16, the table's owner). A locked GeoPackage got
    the same pending column, slipped into the user's own session when the layer
    was already in edit mode; a layer set read-only had the column written to
    its file regardless.

    Now the column is added typed (``compat.new_field``) and only through the
    provider (``errors.add_columns``): nothing is started, committed or rolled
    back here, so the user's session is never touched. False when the layer is
    read-only, when its data source does not allow new columns (a database
    login that does not own the table), when the add is refused (a locked file),
    when the data source is a shapefile -- DBF keeps ten characters of a column
    name, so the column arrived as ``fiberq_uui`` and every call added another
    copy -- and when the column is only in an edit buffer; the reason is logged
    at WARNING. A caller carries on without the column -- ``set_feature_uuid``
    does nothing where there is none and the feature is saved without an ID --
    and the project-open migration holds its schema marker back and tries again
    on the next load.
    """
    if not isinstance(layer, QgsVectorLayer):
        return False
    try:
        name = layer.name()
        provider = layer.dataProvider()
        if provider is None:
            logger.warning(f"'{name}' has no data source to add {FIBERQ_UUID_FIELD} to")
            return False
        if layer.fields().indexOf(FIBERQ_UUID_FIELD) < 0:
            # Logged at WARNING, never pushed: most callers are layer look-ups
            # that run on every placement. Project open says it once, through
            # the migration that fails on it (main_plugin._run_schema_migrations).
            log_only = OperationErrors(f"Adding the {FIBERQ_UUID_FIELD} column")
            if not add_columns(layer, [new_field(FIBERQ_UUID_FIELD, FieldType.String)], log_only):
                return False
        if provider.fields().indexOf(FIBERQ_UUID_FIELD) < 0:
            logger.warning(f"'{name}' has {FIBERQ_UUID_FIELD} only in its edit buffer; the column is "
                           f"not in the data source until that buffer is saved")
            return False
    except RuntimeError as exc:
        # A layer whose C++ object is already gone.
        logger.warning(f"could not check the {FIBERQ_UUID_FIELD} column: {exc}")
        return False
    _set_uuid_alias(layer)
    return True


def migrate_layer_uuids(layer):
    """
    Backfill fiberq_uuid for existing features that don't have one.

    Call this on project load to migrate v1.0–v1.2 projects.

    Args:
        layer: QgsVectorLayer to migrate

    Returns:
        int: Number of features that were assigned new UUIDs

    Raises:
        UuidMigrationError: if the backfill could not be committed to the layer
            (e.g. a locked / read-only GeoPackage). The caller must treat this as
            a failed layer so the migration is retried rather than stamped done.
    """
    if not isinstance(layer, QgsVectorLayer):
        return 0

    field_names = [f.name() for f in layer.fields()]
    if FIBERQ_UUID_FIELD not in field_names:
        return 0

    field_idx = layer.fields().indexFromName(FIBERQ_UUID_FIELD)
    if field_idx < 0:
        return 0

    # Scan for features missing a UUID. A scan error is non-fatal (return 0).
    try:
        count = 0
        features_to_update = {}
        for feat in layer.getFeatures():
            val = feat.attribute(field_idx)
            if val is None or (hasattr(val, 'isNull') and val.isNull()) or str(val).strip() == '':
                features_to_update[feat.id()] = generate_uuid()
                count += 1
    except Exception as e:
        _log(f"Error scanning UUIDs in '{layer.name()}': {e}")
        return 0

    if count == 0:
        return 0

    # Apply + persist. A failure here MUST propagate (not be swallowed): otherwise
    # the runner would stamp the project migrated while the UUIDs never reached
    # disk, and the marker gate would stop it ever retrying.
    #
    # Only into a session of its own, and only counted once saved. A layer
    # already in edit mode -- the user's session, or one a refused save left
    # behind -- used to take the changes into its buffer and have them counted:
    # "Upgraded project schema 0 -> 1.0 (assigned 2 UUIDs across 1 layers)",
    # the project stamped 1.0 and never retried, nothing on disk (v1.6.0 QA,
    # finding Q14, measured on a locked GeoPackage). Its session is left alone
    # now and the layer fails, so the next load tries again.
    if layer.isEditable():
        raise UuidMigrationError(
            f"'{layer.name()}' was already in edit mode, so its features were not given FiberQ IDs")
    if not layer.startEditing():
        raise UuidMigrationError(f"'{layer.name()}' could not be opened for editing")
    try:
        refused = sum(1 for fid, new_uuid in features_to_update.items()
                      if not layer.changeAttributeValue(fid, field_idx, new_uuid))
        if refused:
            layer.rollBack()
            raise UuidMigrationError(
                f"{refused} feature(s) in '{layer.name()}' would not take a FiberQ ID")
        if not layer.commitChanges():
            errors = layer.commitErrors()
            # This session holds nothing but the IDs: the layer was not in edit
            # mode before, so there is no work of the user's to keep.
            layer.rollBack()
            raise UuidMigrationError(
                f"commit failed for '{layer.name()}': {errors}"
            )
    except UuidMigrationError:
        raise
    except Exception as e:
        _log(f"Error persisting UUIDs in '{layer.name()}': {e}")
        try:
            if layer.isEditable():
                layer.rollBack()
        except Exception as rollback_err:
            logger.warning(f"rollback after persist failure raised: {rollback_err}")
        raise UuidMigrationError(f"error persisting UUIDs in '{layer.name()}': {e}")

    _log(f"Migrated {count} features with UUID in layer '{layer.name()}'")
    return count


def migrate_project_uuids(project=None):
    """
    Run UUID migration on all FiberQ-managed layers in a project.

    This should be called once on project load. It:
    1. Identifies all vector layers that are FiberQ-managed
    2. Adds fiberq_uuid field if missing
    3. Backfills UUIDs for features that don't have one

    Args:
        project: the QgsProject to migrate; defaults to the current instance.
                 Explicit projects let the WP1b migration runner (and tests)
                 target a project other than the singleton.

    Returns:
        dict: {layer_name: count_migrated} for layers that were updated
    """
    project = project if project is not None else QgsProject.instance()
    results = {}
    field_added_layers = []
    failed_layers = []

    all_vector_layers = []
    for layer in project.mapLayers().values():
        try:
            if not isinstance(layer, QgsVectorLayer):
                continue

            layer_name = layer.name()
            field_names = {f.name() for f in layer.fields()}
            all_vector_layers.append(layer_name)

            # Match by name OR by FiberQ-characteristic fields -- shared
            # recognition, see layer_is_fiberq / FIBERQ_LAYER_NAMES above.
            if not layer_is_fiberq(layer):
                _log(f"UUID migration: SKIPPING '{layer_name}' (not recognized as FiberQ layer)")
                continue

            _log(f"UUID migration: processing '{layer_name}' (fields: {sorted(field_names)})")

            # Ensure the field exists (idempotent) and stamp the display alias.
            # Run unconditionally so layers that already have the column still get
            # the 'FiberQ UUID' alias applied on load, not only at first creation.
            had_field = FIBERQ_UUID_FIELD in field_names
            added = ensure_uuid_field(layer)
            if not added:
                _log(f"UUID migration: FAILED to add field to '{layer_name}'")
                failed_layers.append(layer_name)
                continue
            if not had_field:
                field_added_layers.append(layer_name)
                _log(f"UUID migration: added field to '{layer_name}'")

            # Backfill missing UUIDs (raises UuidMigrationError if it can't persist)
            count = migrate_layer_uuids(layer)
            if count > 0:
                results[layer_name] = count
        except Exception as e:
            try:
                failed_layers.append(layer.name())
            except Exception:
                failed_layers.append("<unknown>")
            _log(f"Error migrating layer: {e}")
            # The reason, where the project-open message sends the user to look.
            logger.warning(f"FiberQ IDs were not saved: {e}")

    if field_added_layers:
        _log(f"UUID migration: added fiberq_uuid field to {len(field_added_layers)} layers: {', '.join(field_added_layers)}")

    _log(f"UUID migration summary: {len(all_vector_layers)} vector layers in project: {all_vector_layers}")

    if results:
        total = sum(results.values())
        _log(f"UUID migration complete: {total} features across {len(results)} layers")

    if failed_layers:
        # Surface partial failure so the migration runner does NOT stamp the
        # project as migrated (it would otherwise never retry these layers).
        raise UuidMigrationError(
            "could not add/persist fiberq_uuid on %d layer(s): %s"
            % (len(failed_layers), ", ".join(failed_layers))
        )

    return results


__all__ = [
    'FIBERQ_UUID_FIELD',
    'FIBERQ_UUID_ALIAS',
    'FIBERQ_LAYER_NAMES',
    'FIBERQ_FIELD_SIGNATURES',
    'layer_is_fiberq',
    'project_has_fiberq_layers',
    'generate_uuid',
    'set_feature_uuid',
    'ensure_uuid_field',
    'migrate_layer_uuids',
    'migrate_project_uuids',
]
