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
from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP

from ..i18n import safe_format
from ..utils.errors import OperationErrors, check_commit
from ..utils.logger import get_logger
logger = get_logger(__name__)

#: WP4 4.2 item R7, the undo/redo half. Strings in the FiberQUndo context, with
#: QT_TRANSLATE_NOOP at the literal so pylupdate6 can read it.
_UNDO_TITLE = QT_TRANSLATE_NOOP('FiberQUndo', "FiberQ Undo")
_NOT_EDITABLE = QT_TRANSLATE_NOOP(
    'FiberQUndo', "the layer could not be opened for editing, so nothing was undone")
_HELD_BACK = QT_TRANSLATE_NOOP(
    'FiberQUndo',
    "this could not be saved to {layer} and has been left on the undo list, still showing on the"
    " map. Clear whatever is holding the file and undo again.")
_FIELDS_GONE = QT_TRANSLATE_NOOP(
    'FiberQUndo',
    "{layer} no longer has the column(s) {columns}, so what was restored is missing those values")
_GEOMETRY_REFUSED = QT_TRANSLATE_NOOP(
    'FiberQUndo', "the layer would not take the earlier shape of this feature")
_ATTRIBUTES_REFUSED = QT_TRANSLATE_NOOP(
    'FiberQUndo', "{count} of this feature's earlier values were refused by the layer")


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
        except Exception as e:
            logger.debug(f"Could not read field {field_name} for undo label: {e}")
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
        #: Layers whose commit THIS manager asked for and did not get. A refused
        #: commit leaves the layer editable, and `_ensure_editable` used to read
        #: that as "somebody else owns this session, do not commit" -- so after
        #: one failure no later undo in the session ever committed again.
        #: Measured on 3.44.15: undo 1 refused by a DELETE trigger; the trigger
        #: then dropped so the provider would accept it; undo 2 reported success
        #: and never attempted a commit, and both rows were still on disk.
        self._unsaved = set()

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

        # absorb=True because this is reached from a Qt slot: an exception
        # leaving here is QGIS's "unhandled Python error" dialog.
        with OperationErrors(QCoreApplication.translate('FiberQUndo', _UNDO_TITLE),
                             self.iface, absorb=True) as errors:
            if op.op_type == OpType.ADD:
                # Undo add = delete the feature
                success = self._delete_feature(layer, op.feature_id, errors)

            elif op.op_type == OpType.DELETE:
                # Undo delete = re-add the feature
                new_fid = self._add_feature(layer, op.geometry_wkt, op.attributes, errors)
                if new_fid is not None:
                    # Update the op with the new FID for redo
                    op.feature_id = new_fid
                    success = True

            elif op.op_type == OpType.MODIFY:
                # Undo modify = restore old geometry/attributes
                success = self._restore_feature(
                    layer, op.feature_id,
                    op.old_geometry_wkt, op.old_attributes, errors
                )

        if success:
            # Hoisted out of the three arms, which pushed the identical text.
            self.iface.messageBar().pushInfo(
                "FiberQ Undo", f"Undone: {op.description}"
            )
            self._redo_stack.append(op)
            layer.triggerRepaint()
        else:
            self._stack_back(op, layer, errors)

        return success

    def _stack_back(self, op, layer, errors):
        """Decide what happens to an operation whose undo did not go through.

        It used to be dropped from BOTH stacks with nothing said: ``op`` was
        popped before the write, ``success`` stayed False, and the only message
        bar push sat inside the success branch. Measured -- remove the feature
        behind the top entry outside FiberQ, press undo, and ``undo()`` answers
        False with an empty message bar and the entry gone. Press undo again
        expecting that same operation and you undo the one BEFORE it instead.
        Two presses, one visible effect, no explanation.

        ``isModified()`` is the discriminator, and it is measured: True after a
        refused commit, because the edit is still buffered and a retry has
        something to save; False when the target feature was simply not there.
        So a recoverable operation goes back on the undo stack and says so, and
        a hopeless one is still dropped rather than blocking the stack forever.
        """
        try:
            recoverable = layer.isModified()
        except (AttributeError, RuntimeError):
            recoverable = False
        if not recoverable:
            return
        self._undo_stack.append(op)
        self.iface.messageBar().pushWarning(
            "FiberQ Undo",
            safe_format(QCoreApplication.translate('FiberQUndo', _HELD_BACK), _HELD_BACK,
                        layer=layer.name()))

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

        with OperationErrors(QCoreApplication.translate('FiberQUndo', _UNDO_TITLE),
                             self.iface, absorb=True) as errors:
            if op.op_type == OpType.ADD:
                # Redo add = re-add the feature
                new_fid = self._add_feature(layer, op.geometry_wkt, op.attributes, errors)
                if new_fid is not None:
                    op.feature_id = new_fid
                    success = True

            elif op.op_type == OpType.DELETE:
                # Redo delete = delete the feature again
                success = self._delete_feature(layer, op.feature_id, errors)

            elif op.op_type == OpType.MODIFY:
                # Redo modify = apply the new state again
                success = self._restore_feature(
                    layer, op.feature_id,
                    op.geometry_wkt, op.attributes, errors
                )

        if success:
            self.iface.messageBar().pushInfo(
                "FiberQ Undo", f"Redone: {op.description}"
            )
            self._undo_stack.append(op)
            layer.triggerRepaint()
        else:
            # Same reasoning as undo's, onto the stack this came off.
            try:
                recoverable = layer.isModified()
            except (AttributeError, RuntimeError):
                recoverable = False
            if recoverable:
                self._redo_stack.append(op)
                self.iface.messageBar().pushWarning(
                    "FiberQ Undo",
                    safe_format(QCoreApplication.translate('FiberQUndo', _HELD_BACK), _HELD_BACK,
                                layer=layer.name()))

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
        """Clear both undo and redo stacks.

        ``_unsaved`` goes with them: it records which layers THIS manager left
        with a refused commit, and that is only meaningful while the operations
        it belongs to are still on a stack.
        """
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._unsaved.clear()
        logger.debug("Undo stacks cleared")

    # -----------------------------------------------------------------
    # Internal layer-editing helpers
    # -----------------------------------------------------------------

    def _ensure_editable(self, layer, errors=None):
        """Put the layer in edit mode. True when this manager must commit it.

        WP4 4.2 item R7. The old version read ``isEditable()`` as "somebody else
        owns this session, do not commit" -- which is right for a session the
        USER opened, and wrong for one this manager's own refused commit left
        open. ``startEditing()``'s result was discarded too, so a layer that
        would not open for editing looked exactly like one that had.

        Measured on 3.44.15 and repeated on the floor:

            undo 1, with a DELETE trigger refusing the commit
                deleteFeature -> True, commitChanges -> False,
                the helper answered True, the layer was left editable,
                the row was still on disk
            the trigger is then dropped, so the provider would accept a delete
            undo 2
                answered True, attempted NO commit at all, row still on disk

        One failure stopped every later undo in the session from ever
        committing, long after the cause was gone. ``_unsaved`` is what tells
        the two kinds of open session apart.
        """
        if layer.isEditable():
            return layer.id() in self._unsaved
        if not layer.startEditing():
            if errors is not None:
                errors.add(layer.name(), QCoreApplication.translate('FiberQUndo', _NOT_EDITABLE))
            return False
        return True

    def _commit(self, layer, errors):
        """Commit what this manager buffered, and remember if it was refused.

        No ``rollBack()``: QGIS keeps a refused commit's edits buffered, so the
        user can clear the cause and undo again and the work is still there.
        That is ``fiberq.utils.errors``' rule and the reason ``_unsaved``
        exists -- the retry needs both the buffered edit and the knowledge that
        this manager owns it.
        """
        if check_commit(layer, errors, what=layer.name()):
            self._unsaved.discard(layer.id())
            return True
        self._unsaved.add(layer.id())
        return False

    def _delete_feature(self, layer, fid, errors):
        """Delete a feature by FID. True when the deletion reached the file.

        It used to answer ``ok`` -- the result of ``deleteFeature``, which is
        the BUFFER write. Measured with a BEFORE DELETE trigger:
        ``deleteFeature`` answered True, ``commitChanges`` answered False, and
        this answered True, so ``undo()`` pushed "Undone: Added p1 (poles)" and
        repainted the canvas while the GeoPackage still held the row. It came
        back on the next project open.
        """
        # Verify the feature exists
        feat = layer.getFeature(fid)
        if not feat.isValid():
            logger.warning("Feature %s not found in %s", fid, layer.name())
            return False

        we_started = self._ensure_editable(layer, errors)
        ok = layer.deleteFeature(fid)
        if not ok:
            if we_started:
                # Nothing of ours is buffered, so closing the session we opened
                # costs nobody anything.
                layer.rollBack()
            errors.add(layer.name(), QCoreApplication.translate('FiberQUndo', _NOT_EDITABLE)
                       if not layer.isEditable() else
                       QCoreApplication.translate('FiberQUndo', _GEOMETRY_REFUSED))
            return False
        if we_started:
            return self._commit(layer, errors)
        return True

    def _add_feature(self, layer, geom_wkt, attributes, errors):
        """
        Add a feature to a layer from WKT geometry and attributes dict.

        Returns:
            The new feature ID, or None when nothing reached the file.
        """
        f = QgsFeature(layer.fields())

        if geom_wkt:
            geom = QgsGeometry.fromWkt(geom_wkt)
            if geom and not geom.isEmpty():
                f.setGeometry(geom)

        if attributes:
            field_names = layer.fields().names()
            missing = []
            for name, value in attributes.items():
                if name in field_names:
                    # No handler here: setAttribute raises only KeyError, for a
                    # name the feature's fields do not have, and `field_names`
                    # comes from the same QgsFields the feature was built from
                    # (measured on all three legs -- object(), list, dict, float
                    # and None are all accepted). The handler that used to sit
                    # here could not fire. The real loss is the other arm.
                    f.setAttribute(name, value)
                else:
                    missing.append(name)
            if missing:
                # Undoing a delete after a schema change brought the feature
                # back with values missing and named none of them.
                errors.add(layer.name(), safe_format(
                    QCoreApplication.translate('FiberQUndo', _FIELDS_GONE), _FIELDS_GONE,
                    layer=layer.name(), columns=", ".join(sorted(missing))))

        we_started = self._ensure_editable(layer, errors)
        ok = layer.addFeature(f)
        if not ok:
            if we_started:
                layer.rollBack()
            errors.add(layer.name(), QCoreApplication.translate('FiberQUndo', _NOT_EDITABLE))
            return None
        if we_started and not self._commit(layer, errors):
            # Measured: without this, _find_committed_fid runs anyway and reads
            # THROUGH the edit buffer, so it answered -2 -- a buffer-only id.
            # undo()'s `if new_fid is not None` was satisfied, it set
            # op.feature_id = -2, said "Undone: Deleted p1 (poles)" and pushed
            # the op onto the redo stack. The GeoPackage never got the row, and
            # a later redo then operated on fid -2.
            return None

        # Find the committed FID
        return self._find_committed_fid(layer, geom_wkt)

    def _restore_feature(self, layer, fid, geom_wkt, attributes, errors):
        """
        Restore a feature's geometry and attributes.

        Returns True only when every write that was attempted was accepted AND
        reached the file.

        This was the sharpest of the three. It discarded ``changeGeometry``,
        discarded every ``changeAttributeValue``, discarded ``commitChanges``,
        and then ``return True`` unconditionally, whatever had happened above.
        Measured on all three legs with a BEFORE UPDATE trigger: it answered
        True, ``undo()`` said "Undone: Modified CHANGED (poles)" and pushed the
        op to the redo stack, and the GeoPackage row still read CHANGED. The
        stack then believed the feature was in its OLD state while the file held
        the NEW one, so the next undo of that feature worked from a baseline
        that had never existed.
        """
        feat = layer.getFeature(fid)
        if not feat.isValid():
            logger.warning("Feature %s not found in %s for restore", fid, layer.name())
            return False

        we_started = self._ensure_editable(layer, errors)
        restored = True

        if geom_wkt:
            geom = QgsGeometry.fromWkt(geom_wkt)
            if geom and not geom.isEmpty():
                # Measured: changeGeometry answers False when the layer is not
                # editable -- which is how a failed startEditing used to become
                # invisible here -- and True for an absent fid.
                if not layer.changeGeometry(fid, geom):
                    errors.add(layer.name(), QCoreApplication.translate(
                        'FiberQUndo', _GEOMETRY_REFUSED))
                    restored = False

        if attributes:
            field_names = layer.fields().names()
            missing = []
            refused = 0
            for name, value in attributes.items():
                if name not in field_names:
                    missing.append(name)
                    continue
                idx = layer.fields().indexFromName(name)
                if idx < 0:
                    missing.append(name)
                    continue
                if not layer.changeAttributeValue(fid, idx, value):
                    refused += 1
            # One line for all of them, not one per attribute: a feature with
            # thirty columns must not become thirty message-bar entries.
            if missing:
                errors.add(layer.name(), safe_format(
                    QCoreApplication.translate('FiberQUndo', _FIELDS_GONE), _FIELDS_GONE,
                    layer=layer.name(), columns=", ".join(sorted(missing))))
                restored = False
            if refused:
                errors.add(layer.name(), safe_format(
                    QCoreApplication.translate('FiberQUndo', _ATTRIBUTES_REFUSED),
                    _ATTRIBUTES_REFUSED, count=refused))
                restored = False

        if we_started and not self._commit(layer, errors):
            return False
        return restored

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
