"""Keep the stored length of a feature in step with the geometry the user edits.

:mod:`fiberq.core.length_manager` repairs lengths **on demand** -- the user runs
"Recalculate lengths..." and the drift is gone. This module stops the drift
happening in the first place: drag a vertex of a route and its ``duzina`` /
``duzina_km`` follow the drag; move a cable and ``duzina_m`` and
``total_len_m`` follow it, with ``slack_m`` left exactly as the user set it.

There are two paths, and the split between them is not an implementation detail
-- it is the whole design:

**1. The live path** (``geometryChanged``) writes while the user's own edit
command is still open, so the attribute write joins that command. One gesture
stays one undo step: Ctrl+Z puts the vertex *and* the length back, Ctrl+Shift+Z
brings both forward. It runs only under :func:`_user_edit_command_is_open` and
only for features that already exist.

**2. The commit sweep** (``beforeCommitChanges``) re-measures every geometry in
the edit buffer just before it reaches disk. It exists because the live path
deliberately misses things, and each of them is a real gesture:

* features added in this session -- see the warning below, nothing may be
  written from ``featureAdded``;
* the half of a QGIS "Split features" that is a *new* feature (the shortened
  original arrives through the live path, the new one does not);
* a bare ``layer.changeGeometry()`` with no edit command: FiberQ's own move
  tool, Route correction, the Python console, another plugin;
* a nested ``beginEditCommand`` whose inner ``endEditCommand`` clears QGIS's
  "command active" flag while the outer macro is still composing, so later
  changes in the same macro arrive unguarded (measured on 3.22, 3.44 and 4.0).

**Never write from ``featureAdded``.** A hook that does segfaults QGIS on the
*redo* of an add, a split or a paste -- on 3.22, 3.44 and 4.0, and with the
guard below in place, because the guard passes at add time and the damage only
surfaces later. The crash is not a race that careful coding avoids; the fix is
to let the sweep handle added features, which it does, from a point where the
undo stack is not being replayed. ``tests/test_length_sync.py`` runs those
gestures in a subprocess for exactly this reason.

**Buffered transaction groups** (Project Properties -> Data Sources, QGIS 3.26+)
never emit ``beforeCommitChanges``, not even for an explicit
``layer.commitChanges()``, and ``QgsVectorLayerEditBufferGroup`` has no
pre-commit signal of its own, so there is nothing to hook. The live path still
works there, so an edited feature is still updated the moment it moves; what is
lost is the sweep, so added features and bare ``changeGeometry()`` edits keep
their stale value until "Recalculate lengths..." is run. The module says so in
the log once per layer rather than pretending otherwise.

**Undo-manager restores.** :mod:`fiberq.core.undo_manager` puts the geometry
back and then the recorded attributes, with no edit command, so the live path
skips it and the sweep re-measures at commit. If the recorded length disagreed
with the recorded geometry, the sweep's value wins. That is intended: the
sweep's number is the one that matches what is on the map.

Nothing here is user-visible. No dialog, no message bar, no new string: a length
that quietly stays right is the feature.
"""
import functools
from typing import Dict, Optional, Set

from ..utils.logger import get_logger
from ..utils.measure import measures_metres
from .length_manager import length_field_for, length_writes

logger = get_logger(__name__)


def _user_edit_command_is_open(layer) -> bool:
    """Whether a write right now would join the gesture the user is performing.

    Both halves are load-bearing, and both were measured on 3.22, 3.44 and 4.0:

    * ``isEditCommandActive()`` on its own is also True while QGIS unwinds a
      ``destroyEditCommand()`` -- a tool abandoning its own edit -- where a
      write either disappears with the rest or, worse, outlives it.
    * ``not undoStack().canUndo()`` on its own is also True for a bare
      ``changeGeometry()`` with no command open. Writing there pushes a *second*
      command onto the stack, so one user gesture needs two Ctrl+Z; and a write
      during an undo replay pushes a command onto a stack that is mid-undo,
      which rewrites the history under the user. Measured with the guard taken
      out: the stack grew 1 -> 3 on the first undo/redo of a vertex move, the
      same on the redo of a split, and clicking around the Undo/Redo panel swung
      it 5 -> 13 -> 11 while the stored length came back out of step with the
      geometry. That one does not segfault on 3.44 or 4.0, hard as it was tried;
      the segfault is the ``featureAdded`` write this module's docstring
      forbids, which dies on 3.22, 3.44 and 4.0 with this guard in front of it
      as surely as without.

    Qt suppresses ``canUndo()`` for as long as a macro is composing, so the pair
    reads "a user edit command is open *right now*" at any history depth -- it
    is emphatically not "this is the first edit of the session". Measured: five
    sequential vertex moves, the stack growing 1 -> 5, wrote on all five.
    """
    try:
        if not layer.isEditCommandActive():
            return False
        return not layer.undoStack().canUndo()
    except (AttributeError, RuntimeError) as e:
        # Not a vector layer, or the C++ object is already gone.
        logger.debug(f"Could not inspect the edit command state: {e}")
        return False


class LengthSync:
    """Wires the two paths onto every FiberQ layer that stores a length.

    One instance per plugin load. :meth:`attach` connects, :meth:`detach`
    disconnects, and both are safe to call twice -- a plugin reload that left a
    live connection behind would write twice per gesture.
    """

    def __init__(self, project=None):
        self._project = project
        #: layer id -> the partial connected to that layer's geometryChanged.
        #: Partials, not lambdas, and kept here so the disconnect passes the
        #: *same* callable: a slot the plugin can no longer name is a slot it
        #: can no longer disconnect, and a plugin reload would then leave live
        #: wiring behind on a layer it no longer owns.
        self._geometry_slots: Dict[str, object] = {}
        #: layer id -> the partial connected to beforeCommitChanges.
        self._commit_slots: Dict[str, object] = {}
        #: Layer ids whose sweep is running, so a commit triggered from inside
        #: one (the reserve hook commits cables from the slack layer's signals)
        #: cannot re-enter it.
        self._sweeping: Set[str] = set()
        #: Layer ids already reported as unmeasurable, so that warning is once
        #: per layer and not once per vertex moved.
        self._warned_unmeasurable: Set[str] = set()
        #: Layer ids already reported as living in a buffered transaction group.
        self._warned_buffered: Set[str] = set()
        self._attached = False

    # --- wiring -----------------------------------------------------------

    @property
    def project(self):
        if self._project is None:
            from qgis.core import QgsProject
            self._project = QgsProject.instance()
        return self._project

    def attach(self):
        """Follow every length-bearing layer in the project, now and later."""
        if self._attached:
            return
        project = self.project
        # Disconnect first: an initGui() that ran without a clean unload would
        # otherwise accumulate a second connection on the same project.
        self._disconnect(project.layersAdded, self._layers_added, "layersAdded")
        self._disconnect(project.layersWillBeRemoved, self._layers_will_be_removed,
                         "layersWillBeRemoved")
        project.layersAdded.connect(self._layers_added)
        project.layersWillBeRemoved.connect(self._layers_will_be_removed)
        self._attached = True
        self._layers_added(list(project.mapLayers().values()))

    def detach(self):
        """Stop following anything. Safe to call twice, and on a dead project."""
        for layer_id in set(self._geometry_slots) | set(self._commit_slots):
            self._disconnect_layer(layer_id)
        if self._attached:
            project = self.project
            self._disconnect(project.layersAdded, self._layers_added, "layersAdded")
            self._disconnect(project.layersWillBeRemoved, self._layers_will_be_removed,
                             "layersWillBeRemoved")
        self._attached = False
        self._warned_unmeasurable.clear()
        self._warned_buffered.clear()
        self._sweeping.clear()

    @staticmethod
    def _disconnect(signal, slot, what):
        """Drop ``slot`` from ``signal``; "was not connected" is not an error."""
        try:
            signal.disconnect(slot)
        except (TypeError, RuntimeError) as e:
            logger.debug(f"Nothing to disconnect from {what}: {e}")

    def _layers_added(self, layers):
        for layer in layers or []:
            try:
                self._connect_layer(layer)
            except Exception as e:
                logger.warning(f"Could not follow length edits on a layer: {e}")

    def _layers_will_be_removed(self, payload):
        """``layersWillBeRemoved`` carries layer ids; the overload carries layers.

        Removing a layer *while it is being edited* is step 13 of the manual QA
        script, and a connection left pointing at a deleted C++ object is how
        that turns into a crash rather than a shrug.
        """
        for item in payload or []:
            if isinstance(item, str):
                self._disconnect_layer(item)
            else:
                try:
                    self._disconnect_layer(item.id())
                except (AttributeError, RuntimeError) as e:
                    logger.debug(f"Could not identify a layer being removed: {e}")

    def _connect_layer(self, layer):
        """Connect one layer, if it is a FiberQ layer that stores a length."""
        from qgis.core import QgsVectorLayer
        if not isinstance(layer, QgsVectorLayer):
            return
        layer_id = layer.id()
        if layer_id in self._geometry_slots:
            return  # already following it; connecting twice writes twice
        # By canonical layer name, never by "has a duzina_m field": the Optical
        # slack layer has that field too and it holds the user's slack value.
        if length_field_for(layer) is None:
            return

        geometry_slot = functools.partial(self._geometry_changed, layer_id)
        commit_slot = functools.partial(self._before_commit, layer_id)
        # Each slot is recorded as it is connected, not once both are: a second
        # connect that raised would otherwise leave the first connection live
        # and nameless, and detach() can only disconnect what it can name.
        layer.geometryChanged.connect(geometry_slot)
        self._geometry_slots[layer_id] = geometry_slot
        layer.beforeCommitChanges.connect(commit_slot)
        self._commit_slots[layer_id] = commit_slot

        if self._uses_buffered_groups() and layer_id not in self._warned_buffered:
            self._warned_buffered.add(layer_id)
            logger.warning(
                f"{layer.name()}: the project saves through buffered transaction "
                "groups, which emit no pre-commit signal. Edited features still "
                "get their length updated, but features added in this session "
                "keep theirs until FiberQ > Recalculate lengths is run.")

    def _disconnect_layer(self, layer_id):
        # Our own references go first, so one layer that cannot be reached does
        # not strand the rest of them.
        geometry_slot = self._geometry_slots.pop(layer_id, None)
        commit_slot = self._commit_slots.pop(layer_id, None)
        self._warned_unmeasurable.discard(layer_id)
        self._warned_buffered.discard(layer_id)
        self._sweeping.discard(layer_id)
        try:
            layer = self.project.mapLayer(layer_id)
        except RuntimeError as e:
            logger.debug(f"The project holding {layer_id} is already gone: {e}")
            return
        if layer is None:
            return  # already gone; dropping our reference is all there is to do
        if geometry_slot is not None:
            self._disconnect(layer.geometryChanged, geometry_slot, "geometryChanged")
        if commit_slot is not None:
            self._disconnect(layer.beforeCommitChanges, commit_slot, "beforeCommitChanges")

    def _uses_buffered_groups(self) -> bool:
        try:
            from qgis.core import Qgis
            return self.project.transactionMode() == Qgis.TransactionMode.BufferedGroups
        except AttributeError:
            # QGIS < 3.26 has no transaction modes at all, buffered or otherwise.
            return False

    # --- the live path ----------------------------------------------------

    def _geometry_changed(self, layer_id, fid, geom, *_signal_extras):
        """One existing feature just changed shape inside an open edit command."""
        if fid < 0:
            # Still in the add buffer. Writing to a feature that has never been
            # committed is the featureAdded crash by another door, and the
            # commit sweep writes it from safety instead.
            return
        layer = self.project.mapLayer(layer_id)
        if layer is None or not _user_edit_command_is_open(layer):
            return
        try:
            self._write(layer, fid, geom=geom)
        except Exception as e:
            # Never let this reach the editing tool: a failed length write must
            # not cost the user the vertex they just moved.
            logger.warning(f"Could not update the stored length on {layer.name()}: {e}")

    # --- the commit sweep -------------------------------------------------

    def _before_commit(self, layer_id, *_signal_extras):
        """Last chance before the buffer reaches disk: re-measure what changed."""
        if layer_id in self._sweeping:
            return
        layer = self.project.mapLayer(layer_id)
        if layer is None:
            return
        buffer = layer.editBuffer()
        if buffer is None:
            return

        self._sweeping.add(layer_id)
        try:
            # Copied before writing: changeAttributeValue() edits the very maps
            # being walked.
            added = dict(buffer.addedFeatures())
            changed = dict(buffer.changedGeometries())
            # Moved and then deleted in the same session: there is nothing left
            # to carry a length, and the write would only fail and complain.
            for fid in buffer.deletedFeatureIds():
                added.pop(fid, None)
                changed.pop(fid, None)
            for fid, feat in added.items():
                # Added features are the keys of addedFeatures(), whatever the
                # sign of the key: in passthrough mode they are real positive
                # fids (measured), so "fid < 0 means new" is wrong here.
                geom = changed[fid] if fid in changed else feat.geometry()
                self._sweep_one(layer, fid, geom, feat)
            for fid, geom in changed.items():
                if fid in added:
                    continue
                self._sweep_one(layer, fid, geom, None)
        except Exception as e:
            logger.warning(
                f"Could not refresh stored lengths on {layer.name()} before saving: {e}")
        finally:
            self._sweeping.discard(layer_id)

    def _sweep_one(self, layer, fid, geom, feat) -> bool:
        """One feature of the sweep, isolated: a failure costs only that feature.

        The sweep is the one path that walks a whole edit buffer, so an
        exception raised for a single feature used to abandon every feature
        after it. Measured before this existed: one console-made feature with no
        field names raised ``KeyError`` on ``slack_m``, and a 655.81 m vertex
        move in the same commit stayed stored as ``0.0``.
        """
        try:
            self._write(layer, fid, geom=geom, feat=feat)
            return True
        except Exception as e:
            logger.warning(f"Could not refresh the stored length of feature {fid} "
                           f"on {layer.name()}: {e}")
            return False

    # --- the write itself -------------------------------------------------

    def _write(self, layer, fid, geom=None, feat=None) -> int:
        """Write one feature's length fields. Returns how many were written."""
        if not measures_metres(layer, project=self.project):
            # The same gate the manual recalculation applies: without a usable
            # ellipsoid this would store map units -- 37% long in Web Mercator
            # at Serbian latitudes -- so store nothing and say why, once.
            layer_id = layer.id()
            if layer_id not in self._warned_unmeasurable:
                self._warned_unmeasurable.add(layer_id)
                logger.warning(
                    f"{layer.name()}: no usable ellipsoid, so stored lengths are "
                    "left alone. Set one in Project Properties > General.")
            return 0

        if feat is None:
            feat = layer.getFeature(fid)
            if not feat.isValid():
                # Nothing to read the slack from, so total_len_m would be wrong.
                logger.debug(f"{layer.name()}: feature {fid} is not readable yet")
                return 0

        writes = length_writes(feat, layer, geom=geom, project=self.project)
        if not writes:
            return 0

        fields = layer.fields()
        written = 0
        for name, value in writes.items():
            index = fields.indexOf(name)
            if index < 0:
                continue
            if layer.changeAttributeValue(fid, index, value):
                written += 1
            else:
                logger.warning(f"{layer.name()}: could not store {name} on feature {fid}")
        return written


def install(project=None) -> Optional[LengthSync]:
    """Build and attach a :class:`LengthSync`, or return None if it cannot."""
    try:
        sync = LengthSync(project)
        sync.attach()
        return sync
    except Exception as e:
        logger.warning(f"Stored lengths will not follow edits this session: {e}")
        return None
