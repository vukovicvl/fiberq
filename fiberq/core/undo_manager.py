"""
FiberQ v2 - Undo Manager

Independent undo/redo system for FiberQ toolbar operations.

This operates separately from QGIS's built-in undo (Ctrl+Z) to provide
reliable undo for plugin-created features across multiple layers.

Usage:
    # After placing a feature:
    undo_manager.record_add(layer, feature)

    # Before deleting a feature:
    undo_manager.record_delete(layer, feature)

    # Undo/Redo:
    undo_manager.undo()
    undo_manager.redo()
"""

import time
from collections import deque
from enum import Enum

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry
)

from ..utils.logger import get_logger
logger = get_logger(__name__)


# =============================================================================
# Operation Types
# =============================================================================

class OpType(Enum):
    """Types of undoable operations."""
    ADD = "add"          # Feature was added — undo = delete it
    DELETE = "delete"    # Feature was deleted — undo = re-add it
    MODIFY = "modify"   # Feature was modified — undo = restore old state


# =============================================================================
# Undo Operation Record
# =============================================================================

class UndoOp:
    """
    A single undoable operation.

    Stores enough information to reverse or replay the operation.
    Geometries are stored as WKT strings to avoid holding references
    to QGIS objects that may become invalid.
    """

    __slots__ = (
        'op_type', 'layer_id', 'layer_name', 'feature_id',
        'geometry_wkt', 'attributes', 'old_geometry_wkt', 'old_attributes',
        'timestamp', 'description'
    )

    def __init__(self, op_type, layer_id, layer_name, feature_id,
                 geometry_wkt=None, attributes=None,
                 old_geometry_wkt=None, old_attributes=None,
                 description=''):
        self.op_type = op_type
        self.layer_id = layer_id
        self.layer_name = layer_name
        self.feature_id = feature_id
        self.geometry_wkt = geometry_wkt          # current/new geometry
        self.attributes = attributes              # current/new attributes dict
        self.old_geometry_wkt = old_geometry_wkt  # previous geometry (MODIFY only)
        self.old_attributes = old_attributes      # previous attributes (MODIFY only)
        self.timestamp = time.time()
        self.description = description

    def __repr__(self):
        return (f"UndoOp({self.op_type.value}, {self.layer_name}, "
                f"fid={self.feature_id}, '{self.description}')")


# =============================================================================
# Helper: snapshot a feature
# =============================================================================

def _snapshot_feature(feature):
    """
    Take a serializable snapshot of a QgsFeature.

    Returns:
        Tuple of (geometry_wkt, attributes_dict)
    """
    geom = feature.geometry()
    geom_wkt = geom.asWkt() if geom and not geom.isEmpty() else None

    attrs = {}
    for i, field in enumerate(feature.fields()):
        val = feature.attribute(i)
        # QVariant NULL → None
        if val is None or (hasattr(val, 'isNull') and val.isNull()):
            attrs[field.name()] = None
        else:
            attrs[field.name()] = val

    return geom_wkt, attrs


def _make_description(op_type, layer_name, feature):
    """Build a human-readable description for the message bar."""
    # Try to find a useful identifier from common FiberQ fields
    id_fields = ['broj_okna', 'naziv', 'oznaka', 'name', 'tip']
    label = ''
    for field_name in id_fields:
        try:
            val = feature.attribute(field_name)
            if val and str(val).strip():
                label = str(val).strip()
                break
        except Exception:
            continue

    type_word = {
        OpType.ADD: 'Added',
        OpType.DELETE: 'Deleted',
        OpType.MODIFY: 'Modified',
    }.get(op_type, 'Changed')

    if label:
        return f"{type_word} {label} ({layer_name})"
    else:
        return f"{type_word} feature in {layer_name}"


# =============================================================================
# FiberQ Undo Manager
# =============================================================================

class FiberQUndoManager:
    """
    Independent undo/redo system for FiberQ operations.

    Maintains its own undo and redo stacks (max 50 entries each).
    All recording methods are safe to call — they silently handle errors
    so they never break the tool that's calling them.
    """

    MAX_STACK = 50

    def __init__(self, iface):
        self.iface = iface
        self._undo_stack = deque(maxlen=self.MAX_STACK)
        self._redo_stack = deque(maxlen=self.MAX_STACK)

    # -----------------------------------------------------------------
    # Recording operations
    # -----------------------------------------------------------------

    def record_add(self, layer, feature):
        """
        Record that a feature was added to a layer.

        Call this AFTER layer.addFeature() + layer.commitChanges().
        The feature must have a valid id() at this point.

        Args:
            layer:   QgsVectorLayer the feature was added to
            feature: QgsFeature that was added
        """
        try:
            geom_wkt, attrs = _snapshot_feature(feature)
            fid = feature.id()

            # After commitChanges, the original feature object may have
            # a temporary negative ID. Try to find the real committed FID
            # by matching geometry (most reliable for just-added features).
            if fid < 0:
                fid = self._find_committed_fid(layer, geom_wkt)

            op = UndoOp(
                op_type=OpType.ADD,
                layer_id=layer.id(),
                layer_name=layer.name(),
                feature_id=fid,
                geometry_wkt=geom_wkt,
                attributes=attrs,
                description=_make_description(OpType.ADD, layer.name(), feature)
            )
            self._undo_stack.append(op)
            self._redo_stack.clear()
            logger.debug(f"Undo recorded: {op}")
        except Exception as e:
            logger.debug(f"Error recording add for undo: {e}")

    def record_delete(self, layer, feature):
        """
        Record that a feature is about to be deleted from a layer.

        Call this BEFORE layer.deleteFeature().

        Args:
            layer:   QgsVectorLayer the feature will be deleted from
            feature: QgsFeature that will be deleted
        """
        try:
            geom_wkt, attrs = _snapshot_feature(feature)
            op = UndoOp(
                op_type=OpType.DELETE,
                layer_id=layer.id(),
                layer_name=layer.name(),
                feature_id=feature.id(),
                geometry_wkt=geom_wkt,
                attributes=attrs,
                description=_make_description(OpType.DELETE, layer.name(), feature)
            )
            self._undo_stack.append(op)
            self._redo_stack.clear()
            logger.debug(f"Undo recorded: {op}")
        except Exception as e:
            logger.debug(f"Error recording delete for undo: {e}")

    def record_modify(self, layer, feature, old_feature):
        """
        Record that a feature was modified.

        Call this AFTER the modification and commitChanges.

        Args:
            layer:       QgsVectorLayer
            feature:     QgsFeature with new state
            old_feature: QgsFeature with previous state
        """
        try:
            geom_wkt, attrs = _snapshot_feature(feature)
            old_geom_wkt, old_attrs = _snapshot_feature(old_feature)
            op = UndoOp(
                op_type=OpType.MODIFY,
                layer_id=layer.id(),
                layer_name=layer.name(),
                feature_id=feature.id(),
                geometry_wkt=geom_wkt,
                attributes=attrs,
                old_geometry_wkt=old_geom_wkt,
                old_attributes=old_attrs,
                description=_make_description(OpType.MODIFY, layer.name(), feature)
            )
            self._undo_stack.append(op)
            self._redo_stack.clear()
            logger.debug(f"Undo recorded: {op}")
        except Exception as e:
            logger.debug(f"Error recording modify for undo: {e}")

    # -----------------------------------------------------------------
    # Undo / Redo
    # -----------------------------------------------------------------

    def undo(self):
        """
        Undo the last FiberQ operation.

        Returns:
            True if the undo was successful, False otherwise.
        """
        if not self._undo_stack:
            self.iface.messageBar().pushInfo("FiberQ Undo", "Nothing to undo.")
            return False

        op = self._undo_stack.pop()
        layer = QgsProject.instance().mapLayer(op.layer_id)

        if not layer or not isinstance(layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning(
                "FiberQ Undo",
                f"Cannot undo — layer '{op.layer_name}' no longer exists."
            )
            return False

        success = False

        try:
            if op.op_type == OpType.ADD:
                # Undo add = delete the feature
                success = self._delete_feature(layer, op.feature_id)
                if success:
                    self.iface.messageBar().pushInfo(
                        "FiberQ Undo",
                        f"Undone: {op.description}"
                    )

            elif op.op_type == OpType.DELETE:
                # Undo delete = re-add the feature
                new_fid = self._add_feature(layer, op.geometry_wkt, op.attributes)
                if new_fid is not None:
                    # Update the op with the new FID for redo
                    op.feature_id = new_fid
                    success = True
                    self.iface.messageBar().pushInfo(
                        "FiberQ Undo",
                        f"Undone: {op.description}"
                    )

            elif op.op_type == OpType.MODIFY:
                # Undo modify = restore old geometry/attributes
                success = self._restore_feature(
                    layer, op.feature_id,
                    op.old_geometry_wkt, op.old_attributes
                )
                if success:
                    self.iface.messageBar().pushInfo(
                        "FiberQ Undo",
                        f"Undone: {op.description}"
                    )

        except Exception as e:
            logger.debug(f"Error during undo: {e}")
            self.iface.messageBar().pushWarning(
                "FiberQ Undo", f"Undo failed: {e}"
            )

        if success:
            self._redo_stack.append(op)
            layer.triggerRepaint()

        return success

    def redo(self):
        """
        Redo the last undone FiberQ operation.

        Returns:
            True if the redo was successful, False otherwise.
        """
        if not self._redo_stack:
            self.iface.messageBar().pushInfo("FiberQ Undo", "Nothing to redo.")
            return False

        op = self._redo_stack.pop()
        layer = QgsProject.instance().mapLayer(op.layer_id)

        if not layer or not isinstance(layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning(
                "FiberQ Undo",
                f"Cannot redo — layer '{op.layer_name}' no longer exists."
            )
            return False

        success = False

        try:
            if op.op_type == OpType.ADD:
                # Redo add = re-add the feature
                new_fid = self._add_feature(layer, op.geometry_wkt, op.attributes)
                if new_fid is not None:
                    op.feature_id = new_fid
                    success = True
                    self.iface.messageBar().pushInfo(
                        "FiberQ Undo",
                        f"Redone: {op.description}"
                    )

            elif op.op_type == OpType.DELETE:
                # Redo delete = delete the feature again
                success = self._delete_feature(layer, op.feature_id)
                if success:
                    self.iface.messageBar().pushInfo(
                        "FiberQ Undo",
                        f"Redone: {op.description}"
                    )

            elif op.op_type == OpType.MODIFY:
                # Redo modify = apply the new state again
                success = self._restore_feature(
                    layer, op.feature_id,
                    op.geometry_wkt, op.attributes
                )
                if success:
                    self.iface.messageBar().pushInfo(
                        "FiberQ Undo",
                        f"Redone: {op.description}"
                    )

        except Exception as e:
            logger.debug(f"Error during redo: {e}")
            self.iface.messageBar().pushWarning(
                "FiberQ Undo", f"Redo failed: {e}"
            )

        if success:
            self._undo_stack.append(op)
            layer.triggerRepaint()

        return success

    # -----------------------------------------------------------------
    # Stack state queries
    # -----------------------------------------------------------------

    def can_undo(self):
        """Return True if there are operations to undo."""
        return len(self._undo_stack) > 0

    def can_redo(self):
        """Return True if there are operations to redo."""
        return len(self._redo_stack) > 0

    def undo_description(self):
        """Get the description of the next undo operation, or empty string."""
        if self._undo_stack:
            return self._undo_stack[-1].description
        return ''

    def redo_description(self):
        """Get the description of the next redo operation, or empty string."""
        if self._redo_stack:
            return self._redo_stack[-1].description
        return ''

    def clear(self):
        """Clear both undo and redo stacks."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        logger.debug("Undo stacks cleared")

    # -----------------------------------------------------------------
    # Internal layer-editing helpers
    # -----------------------------------------------------------------

    def _ensure_editable(self, layer):
        """
        Make sure the layer is in edit mode.
        Returns True if we started editing (caller should commit).
        """
        if layer.isEditable():
            return False  # already editing, don't commit
        layer.startEditing()
        return True

    def _delete_feature(self, layer, fid):
        """Delete a feature by FID. Returns True on success."""
        # Verify the feature exists
        feat = layer.getFeature(fid)
        if not feat.isValid():
            logger.debug(f"Feature {fid} not found in {layer.name()}")
            return False

        we_started = self._ensure_editable(layer)
        ok = layer.deleteFeature(fid)
        if we_started:
            if ok:
                layer.commitChanges()
            else:
                layer.rollBack()
        return ok

    def _add_feature(self, layer, geom_wkt, attributes):
        """
        Add a feature to a layer from WKT geometry and attributes dict.

        Returns:
            The new feature ID, or None on failure.
        """
        f = QgsFeature(layer.fields())

        if geom_wkt:
            geom = QgsGeometry.fromWkt(geom_wkt)
            if geom and not geom.isEmpty():
                f.setGeometry(geom)

        if attributes:
            field_names = layer.fields().names()
            for name, value in attributes.items():
                if name in field_names:
                    try:
                        f.setAttribute(name, value)
                    except Exception as e:
                        logger.debug(f"Could not set attribute {name}: {e}")

        we_started = self._ensure_editable(layer)
        ok = layer.addFeature(f)
        if we_started:
            if ok:
                layer.commitChanges()
            else:
                layer.rollBack()
                return None

        # Find the committed FID
        return self._find_committed_fid(layer, geom_wkt) if ok else None

    def _restore_feature(self, layer, fid, geom_wkt, attributes):
        """
        Restore a feature's geometry and attributes.

        Returns True on success.
        """
        feat = layer.getFeature(fid)
        if not feat.isValid():
            logger.debug(f"Feature {fid} not found in {layer.name()} for restore")
            return False

        we_started = self._ensure_editable(layer)

        if geom_wkt:
            geom = QgsGeometry.fromWkt(geom_wkt)
            if geom and not geom.isEmpty():
                layer.changeGeometry(fid, geom)

        if attributes:
            field_names = layer.fields().names()
            for name, value in attributes.items():
                if name in field_names:
                    idx = layer.fields().indexFromName(name)
                    if idx >= 0:
                        layer.changeAttributeValue(fid, idx, value)

        if we_started:
            layer.commitChanges()

        return True

    def _find_committed_fid(self, layer, geom_wkt):
        """
        Find the FID of the most recently added feature matching a geometry.

        After commitChanges(), feature IDs are reassigned. This scans
        backwards through the layer to find the matching feature.
        """
        if not geom_wkt:
            # Fallback: return the highest FID
            max_fid = -1
            for f in layer.getFeatures():
                if f.id() > max_fid:
                    max_fid = f.id()
            return max_fid if max_fid >= 0 else None

        target_geom = QgsGeometry.fromWkt(geom_wkt)
        if not target_geom or target_geom.isEmpty():
            return None

        best_fid = None
        best_dist = float('inf')

        for f in layer.getFeatures():
            fg = f.geometry()
            if fg and not fg.isEmpty():
                # Use distance for tolerance — exact WKT match may fail
                # due to coordinate precision differences
                d = target_geom.distance(fg)
                if d < 0.001:  # within 1mm
                    # Prefer the highest FID (most recently added)
                    if best_fid is None or f.id() > best_fid:
                        best_fid = f.id()
                        best_dist = d  # noqa: F841

        return best_fid


__all__ = ['FiberQUndoManager', 'OpType']
