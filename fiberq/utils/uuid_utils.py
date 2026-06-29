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
    QgsProject, QgsVectorLayer, QgsField, QgsMessageLog,
    Qgis
)
from qgis.PyQt.QtCore import QVariant

from .logger import get_logger

logger = get_logger(__name__)

# Field name constant — used everywhere
FIBERQ_UUID_FIELD = "fiberq_uuid"


def _log(msg):
    """Log to both FiberQ logger and QGIS Message Log panel."""
    try:
        logger.debug(msg)
    except Exception:
        pass
    try:
        QgsMessageLog.logMessage(msg, "FiberQ UUID", Qgis.MessageLevel.Info)
    except Exception:
        pass


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


def ensure_uuid_field(layer):
    """
    Ensure a layer has the fiberq_uuid field. Add it if missing.

    Works for both memory layers and file-backed layers (GPKG, Shapefile, etc).

    Args:
        layer: QgsVectorLayer to check/modify

    Returns:
        True if field exists (or was added), False on error
    """
    if not isinstance(layer, QgsVectorLayer):
        return False

    try:
        # Check current fields
        current_fields = [f.name() for f in layer.fields()]
        if FIBERQ_UUID_FIELD in current_fields:
            return True

        provider_type = (layer.dataProvider().name() if layer.dataProvider() else "unknown")
        _log(f"ensure_uuid_field: '{layer.name()}' provider={provider_type}, fields={len(current_fields)}, attempting to add...")

        new_field = QgsField(FIBERQ_UUID_FIELD, QVariant.String)

        # Method 1: Direct provider add (best for memory/ogr layers)
        if layer.dataProvider():
            caps = layer.dataProvider().capabilities()
            can_add = bool(caps & layer.dataProvider().AddAttributes)
            _log(f"  Method 1: provider supports AddAttributes={can_add}")

            if can_add:
                try:
                    ok = layer.dataProvider().addAttributes([new_field])
                    _log(f"  Method 1: addAttributes returned {ok}")
                    if ok:
                        layer.updateFields()
                        updated_fields = [f.name() for f in layer.fields()]
                        if FIBERQ_UUID_FIELD in updated_fields:
                            _log(f"  Method 1: SUCCESS - field added to '{layer.name()}'")
                            return True
                        else:
                            _log(f"  Method 1: addAttributes ok but field not in layer.fields()! updated_fields={updated_fields}")
                except Exception as e:
                    _log(f"  Method 1: exception: {e}")

        # Method 2: Via editing session
        try:
            was_editing = layer.isEditable()
            _log(f"  Method 2: was_editing={was_editing}")

            if not was_editing:
                started = layer.startEditing()
                _log(f"  Method 2: startEditing returned {started}")
                if not started:
                    _log(f"  Method 2: FAILED - cannot start editing on '{layer.name()}'")
                    return False

            ok = layer.addAttribute(new_field)
            _log(f"  Method 2: addAttribute returned {ok}")

            if not was_editing:
                if ok:
                    committed = layer.commitChanges()
                    _log(f"  Method 2: commitChanges returned {committed}")
                    if not committed:
                        errors = layer.commitErrors()
                        _log(f"  Method 2: commit errors: {errors}")
                else:
                    layer.rollBack()

            final_fields = [f.name() for f in layer.fields()]
            if FIBERQ_UUID_FIELD in final_fields:
                _log(f"  Method 2: SUCCESS - field added to '{layer.name()}'")
                return True
            else:
                _log(f"  Method 2: field NOT found after commit. final_fields={final_fields}")
        except Exception as e:
            _log(f"  Method 2: exception: {e}")
            try:
                if layer.isEditable():
                    layer.rollBack()
            except Exception:
                pass

        _log(f"ensure_uuid_field: ALL METHODS FAILED for '{layer.name()}'")
        return False
    except Exception as e:
        _log(f"ensure_uuid_field: top-level exception for '{layer.name()}': {e}")
        return False


def migrate_layer_uuids(layer):
    """
    Backfill fiberq_uuid for existing features that don't have one.

    Call this on project load to migrate v1.0–v1.2 projects.

    Args:
        layer: QgsVectorLayer to migrate

    Returns:
        int: Number of features that were assigned new UUIDs
    """
    if not isinstance(layer, QgsVectorLayer):
        return 0

    try:
        field_names = [f.name() for f in layer.fields()]
        if FIBERQ_UUID_FIELD not in field_names:
            return 0

        field_idx = layer.fields().indexFromName(FIBERQ_UUID_FIELD)
        if field_idx < 0:
            return 0

        # Find features missing UUID
        count = 0
        features_to_update = {}
        for feat in layer.getFeatures():
            val = feat.attribute(field_idx)
            if val is None or (hasattr(val, 'isNull') and val.isNull()) or str(val).strip() == '':
                features_to_update[feat.id()] = generate_uuid()
                count += 1

        if count == 0:
            return 0

        # Batch update
        was_editing = layer.isEditable()
        if not was_editing:
            layer.startEditing()

        for fid, new_uuid in features_to_update.items():
            layer.changeAttributeValue(fid, field_idx, new_uuid)

        if not was_editing:
            layer.commitChanges()

        _log(f"Migrated {count} features with UUID in layer '{layer.name()}'")
        return count
    except Exception as e:
        _log(f"Error migrating UUIDs in '{layer.name()}': {e}")
        try:
            if layer.isEditable():
                layer.rollBack()
        except Exception:
            pass
        return 0


def migrate_project_uuids():
    """
    Run UUID migration on all FiberQ-managed layers in the current project.

    This should be called once on project load. It:
    1. Identifies all vector layers that are FiberQ-managed
    2. Adds fiberq_uuid field if missing
    3. Backfills UUIDs for features that don't have one

    Returns:
        dict: {layer_name: count_migrated} for layers that were updated
    """
    project = QgsProject.instance()
    results = {}
    field_added_layers = []

    # FiberQ layer names (English and Serbian legacy, all known variants)
    fiberq_layer_names = {
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
    }

    # Also detect FiberQ layers by checking for known FiberQ field names
    # This catches layers that were renamed or custom layers with FiberQ fields
    fiberq_field_signatures = {
        "naziv", "broj_okna", "tip_trase", "tip_kabla",
        "cable_layer_id", "broj_cevcica", "kapacitet",
        "fibers_per_tube", "total_fibers", "color_standard",
    }

    all_vector_layers = []
    for layer in project.mapLayers().values():
        try:
            if not isinstance(layer, QgsVectorLayer):
                continue

            layer_name = layer.name()
            field_names = {f.name() for f in layer.fields()}
            all_vector_layers.append(layer_name)

            # Match by name OR by having FiberQ-characteristic fields
            is_fiberq = (
                layer_name in fiberq_layer_names
                or bool(field_names & fiberq_field_signatures)  # noqa: W503
            )

            if not is_fiberq:
                _log(f"UUID migration: SKIPPING '{layer_name}' (not recognized as FiberQ layer)")
                continue

            _log(f"UUID migration: processing '{layer_name}' (fields: {sorted(field_names)})")

            # Ensure field exists
            had_field = FIBERQ_UUID_FIELD in field_names
            if not had_field:
                added = ensure_uuid_field(layer)
                if added:
                    field_added_layers.append(layer_name)
                    _log(f"UUID migration: added field to '{layer_name}'")
                else:
                    _log(f"UUID migration: FAILED to add field to '{layer_name}'")
                    continue

            # Backfill missing UUIDs
            count = migrate_layer_uuids(layer)
            if count > 0:
                results[layer_name] = count
        except Exception as e:
            _log(f"Error migrating layer: {e}")

    if field_added_layers:
        _log(f"UUID migration: added fiberq_uuid field to {len(field_added_layers)} layers: {', '.join(field_added_layers)}")

    _log(f"UUID migration summary: {len(all_vector_layers)} vector layers in project: {all_vector_layers}")

    if results:
        total = sum(results.values())
        _log(f"UUID migration complete: {total} features across {len(results)} layers")

    return results


__all__ = [
    'FIBERQ_UUID_FIELD',
    'generate_uuid',
    'set_feature_uuid',
    'ensure_uuid_field',
    'migrate_layer_uuids',
    'migrate_project_uuids',
]
