# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Slack Manager.

This module provides slack (optical reserve) management functionality:
- Creating and ensuring slack layers
- Styling slack layers
- Computing slack totals for cables
- Batch slack generation
"""

from typing import Optional

from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP, QVariant
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from qgis.core import (
    Qgis,
    QgsProject,
    QgsVectorLayer,
    QgsExpression,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsFeatureRequest,
    QgsMarkerSymbol,
    QgsSingleSymbolRenderer,
    QgsUnitTypes,
)
from qgis.PyQt.QtGui import QColor

from ..i18n import safe_format
# R9: the cable reference may be stored under its pre-1.0 Serbian name, and a
# write to the modern name on such a layer raises KeyError rather than missing
# quietly. Every column this module touches is resolved through here.
from . import interchange_fields as fm
# Phase 5.2: Logging
from ..utils.errors import OperationErrors, check_commit, describe
from ..utils.geopackage import database_answers_writes
from ..utils.logger import get_logger
from ..utils.measure import ground_length
logger = get_logger(__name__)


def slack_operation() -> str:
    """Title on the message-bar entries the slack code pushes.

    Public and shared with :mod:`fiberq.tools.slack_tool`: the two halves of
    one operation -- generate in batch, place by hand -- must appear under one
    heading, and a second copy of the literal would be a second translation
    context for the same words.
    """
    src = QT_TRANSLATE_NOOP('FiberQSlack', "Optical slacks")
    return QCoreApplication.translate('FiberQSlack', src)


class _HeldErrors:
    """What a batch attempt found wrong, kept for the attempt and not logged.

    When the attempt is abandoned, v1.5.0's per-slack sequence runs instead and
    reports its own problems in its own order; logging the attempt's as well
    would put warnings in the log that v1.5.0 never wrote.
    """

    def __init__(self):
        self.problems = []

    def add(self, what, problem) -> None:
        self.problems.append((what, problem))

    @property
    def failed(self) -> bool:
        return bool(self.problems)


def _plain_edit_mode() -> bool:
    """True when the project's layers are edited and saved one by one.

    In "Automatic transaction groups" a layer's session reaches every layer in
    its GeoPackage, and in "Buffered transaction groups" (QGIS 3.26+) a commit
    or a roll-back reaches the whole project. One session cannot stand in for
    many there: measured on 3.22.16, 3.44.15 and 4.2.3 in the design review,
    the per-slack commits saved other layers' edits as they went.
    """
    project = QgsProject.instance()
    if hasattr(project, "transactionMode"):
        return project.transactionMode() == Qgis.TransactionMode.Disabled
    return not project.autoTransaction()


def _saves_all_or_nothing(layer) -> bool:
    """A memory layer or a GeoPackage: a refused commit has saved nothing.

    That is what lets a refused batch be put back and redone slack by slack.
    A GeoPackage commits in one SQLite transaction, and a memory layer that
    refuses one feature keeps none of the session's: four points, one with a
    value its integer column cannot take, left 0 rows (3.22.16, 3.44.15 and
    4.2.3). Other providers may keep the rows before the refused one.
    """
    provider = layer.dataProvider()
    if provider is None:
        return False
    return provider.name() == "memory" or (
        provider.name() == "ogr" and provider.storageType() == "GPKG")


def _database_answers_writes(layer) -> bool:
    """A GeoPackage table whose database refuses or follows writes itself (``utils.geopackage``)."""
    return layer.dataProvider().name() == "ogr" and database_answers_writes(layer)


def _holds_old_cable_types(layer) -> bool:
    """True when a cable restyle would migrate one of the layer's rows (``_migrate_cable_type_values``)."""
    if layer.fields().indexOf("tip") < 0:
        return False
    request = QgsFeatureRequest().setFlags(QgsFeatureRequest.Flag.NoGeometry).setNoAttributes().setLimit(1)
    request.setFilterExpression(f"{QgsExpression.quotedColumnRef('tip')} IN ('opticki', 'bakarnI')")
    return any(True for _feature in layer.getFeatures(request))


class SlackManager:
    """Manager for optical slack/reserve operations."""

    def __init__(self, iface, layer_manager=None, style_manager=None):
        """
        Initialize SlackManager.

        Args:
            iface: QGIS interface
            layer_manager: Optional LayerManager instance
            style_manager: Optional StyleManager instance
        """
        self.iface = iface
        self.layer_manager = layer_manager
        self.style_manager = style_manager
        self._reserve_tool = None  # Active reserve placement tool

        # Callbacks for cable styling (set by plugin)
        self._stylize_cable_layer_callback = None

    def set_cable_style_callback(self, callback):
        """Set callback for styling cable layers after slack updates."""
        self._stylize_cable_layer_callback = callback

    def apply_slack_field_aliases(self, layer: QgsVectorLayer) -> None:
        """Apply English field aliases and value maps to an optical slack layer."""
        try:
            from ..utils.field_aliases import apply_slack_field_aliases
            apply_slack_field_aliases(layer)
        except Exception as e:
            logger.debug(f"Error in SlackManager.apply_slack_field_aliases: {e}")

    def ensure_slack_layer(self) -> Optional[QgsVectorLayer]:
        """Create or return the Optical slacks layer.

        Returns:
            The optical slacks vector layer, or None if creation failed.
        """
        # Try LayerManager first
        if self.layer_manager:
            try:
                lyr = self.layer_manager.ensure_slack_layer()
                if lyr:
                    self.apply_slack_field_aliases(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Error in SlackManager.ensure_slack_layer: {e}")

        # Fallback: find existing or create new
        # Issue #2: Check for all possible slack layer names
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (
                    isinstance(lyr, QgsVectorLayer)
                    and lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry  # noqa: W503
                    and lyr.name() in ("Opticke_rezerve", "Optical slacks", "Optical slack")  # noqa: W503
                ):
                    self.apply_slack_field_aliases(lyr)
                    return lyr
            except Exception as e:
                logger.debug(f"Error in SlackManager.ensure_slack_layer: {e}")

        # Create new memory layer
        crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        vl = QgsVectorLayer(f"Point?crs={crs}", "Optical slacks", "memory")  # Issue #2: Use plural name
        pr = vl.dataProvider()
        pr.addAttributes([
            QgsField("tip", QVariant.String),
            QgsField("duzina_m", QVariant.Double),
            QgsField("lokacija", QVariant.String),
            QgsField("cable_layer_id", QVariant.String),
            QgsField("cable_fid", QVariant.Int),
            QgsField("strana", QVariant.String),
            QgsField("napomena", QVariant.String),
        ])
        vl.updateFields()
        # WP1b identity invariant: ensure the fiberq_uuid column exists.
        try:
            from ..utils.uuid_utils import ensure_uuid_field
            ensure_uuid_field(vl)
        except Exception as e:
            logger.debug(f"Error ensuring fiberq_uuid on slack layer: {e}")
        self.apply_slack_field_aliases(vl)
        QgsProject.instance().addMapLayer(vl)
        try:
            self.stylize_slack_layer(vl)
        except Exception as e:
            logger.debug(f"Error in SlackManager.ensure_slack_layer: {e}")
        return vl

    def stylize_slack_layer(self, vl: QgsVectorLayer) -> None:
        """Apply simple red circle style to slack layer."""
        # Try StyleManager first
        if self.style_manager:
            try:
                self.style_manager.stylize_slack_layer(vl)
                return
            except Exception as e:
                logger.debug(f"Error in SlackManager.stylize_slack_layer: {e}")

        # Fallback: inline implementation
        try:
            sym = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "size": "3",
            })
            try:
                sym.setColor(QColor(255, 0, 0))
            except Exception as e:
                logger.debug(f"Error in SlackManager.stylize_slack_layer: {e}")
            try:
                sym.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMapUnits)
            except Exception as e:
                logger.debug(f"Error in SlackManager.stylize_slack_layer: {e}")

            renderer = QgsSingleSymbolRenderer(sym)
            vl.setRenderer(renderer)
            vl.triggerRepaint()
        except Exception as e:
            logger.debug(f"Error in SlackManager.stylize_slack_layer: {e}")

    def recompute_slack_for_cable(self, cable_layer_id: str, cable_fid: int,
                                  errors=None, excluding=()) -> bool:
        """Re-total the slack recorded against one cable and write it back.

        Args:
            cable_layer_id: Layer ID of the cable.
            cable_fid: Feature ID of the cable.
            errors: An :class:`~fiberq.utils.errors.OperationErrors` to report
                into. One gesture often touches several cables -- a single
                Delete selected can touch a dozen -- so the caller owns the
                collector and the user reads one line instead of a dozen.
            excluding: Slack feature ids to leave out of the total. Only the
                batch's replay passes any (``_generate_in_one_session``): its
                slacks are all saved by then, and each recompute must total
                what the per-slack loop saw when it ran.

        Returns:
            True when the cable's ``slack_m`` / ``total_len_m`` were updated.

        **A slack layer with no cable-reference columns is refused here, not
        answered with zero.** The sum runs through a filter expression, and an
        expression naming a column the layer does not have raises nothing at
        all: it matches no rows (measured, 3.44 and 4.0). So a pre-1.0 project
        whose slack layer still carries ``kabl_layer_id`` used to total 0.0 and
        write that over the cable's real figure -- the user's 70 m became 0 and
        nothing said so. Resolving the legacy names fixes the ordinary case;
        refusing when neither name is present is what stops the fix from being
        a quieter version of the same bug.
        """
        reporting = errors if errors is not None else OperationErrors(
            slack_operation(), self.iface)
        updated = False
        try:
            updated = self._total_slack_onto_cable(
                cable_layer_id, cable_fid, reporting, excluding)
        except (ArithmeticError, AttributeError, KeyError, RuntimeError,
                TypeError, ValueError) as exc:
            reporting.add(None, exc)
        if errors is None:
            reporting.report()
        return updated

    def _total_slack_onto_cable(self, cable_layer_id, cable_fid, errors, excluding=()) -> bool:
        """The body of :meth:`recompute_slack_for_cable`, free to raise.

        Split out so the public method is only error plumbing and this is only
        the arithmetic. It is in the ratchet's hardened set for the same reason
        its caller is.
        """
        slack_layer = self.ensure_slack_layer()
        if slack_layer is None:
            errors.add(None, QCoreApplication.translate(
                'FiberQSlack', "there is no optical slack layer to total"))
            return False

        names = slack_layer.fields().names()
        layer_id_field, fid_field = fm.cable_link_fields(names)
        if not layer_id_field:
            # Refuse rather than write. See the method docstring.
            src = QT_TRANSLATE_NOOP(
                'FiberQSlack',
                "'{layer}' has no cable reference columns, so the slack total was left alone")
            errors.add(slack_layer.name(), safe_format(
                QCoreApplication.translate('FiberQSlack', src), src,
                layer=slack_layer.name()))
            return False
        length_field = fm.actual_field(names, "duzina_m")
        if not length_field:
            src = QT_TRANSLATE_NOOP(
                'FiberQSlack',
                "'{layer}' has no slack length column, so the slack total was left alone")
            errors.add(slack_layer.name(), safe_format(
                QCoreApplication.translate('FiberQSlack', src), src,
                layer=slack_layer.name()))
            return False

        slack = self._slack_total(
            slack_layer, layer_id_field, fid_field, length_field,
            cable_layer_id, cable_fid, errors, excluding)

        cable_layer = QgsProject.instance().mapLayer(cable_layer_id)
        if cable_layer is None:
            # The slack rows point at a layer that has left the project. Said
            # out loud: on an old project this is how a stale kabl_layer_id
            # from a different design announces itself.
            src = QT_TRANSLATE_NOOP(
                'FiberQSlack', "the cable layer this slack belongs to is not in the project")
            errors.add(None, QCoreApplication.translate('FiberQSlack', src))
            return False
        cable_f = next(iter(cable_layer.getFeatures(
            QgsFeatureRequest(int(cable_fid)))), None)
        if cable_f is None:
            return False

        fld_slack = next(
            (name for name in ("slack_m", "slack", "slacks_m")
             if cable_layer.fields().indexOf(name) != -1), None)
        has_total = cable_layer.fields().indexOf("total_len_m") != -1
        if fld_slack is None and not has_total:
            return False

        # was_editing, because a recompute must not touch an edit session it did
        # not open. This runs whenever a slack is placed, moved or deleted, and
        # the cable layer is one the user digitises -- so all three of
        # startEditing(), rollBack() and the commit have to be conditional.
        #
        # Measured on 3.44.15 and 4.0.3, with one unsaved cable in the buffer and
        # a refused write: the unsaved cable was gone, the layer was out of edit
        # mode, and the only thing said was "the cable would not take its new
        # slack total". utils/errors.py states the policy this module imports
        # from it -- a failed write is never tidied up by throwing the user's
        # work away -- and route_manager._add_imported_routes is the pattern.
        was_editing = cable_layer.isEditable()
        if not was_editing:
            cable_layer.startEditing()
        if fld_slack:
            cable_f[fld_slack] = float(slack)
        if has_total:
            cable_f["total_len_m"] = self._ground_length(cable_f, cable_layer, errors) + float(slack)
        if not cable_layer.updateFeature(cable_f):
            # The buffer refused the change, so committing would save nothing
            # and still answer True. Said here, where the reason is still known.
            errors.add(cable_layer.name(), QCoreApplication.translate(
                'FiberQSlack', "the cable would not take its new slack total"))
            if not was_editing:
                cable_layer.rollBack()
            return False
        # Left uncommitted on purpose when the user was already editing: the new
        # total joins their session and they save it with the rest of their work.
        if not was_editing and not check_commit(cable_layer, errors):
            return False

        # Workaround for a QGIS quirk: after programmatic editing of a memory
        # layer the labels stay stale until the style is reapplied.
        if self._stylize_cable_layer_callback:
            try:
                self._stylize_cable_layer_callback(cable_layer)
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                # Cosmetic, and the number is already saved: a label that
                # redraws late is not worth a message bar entry of its own.
                logger.warning(f"Could not restyle {cable_layer.name()!r} after a slack update: {exc}")
        cable_layer.triggerRepaint()
        return True

    def _slack_total(self, slack_layer, layer_id_field, fid_field, length_field,
                     cable_layer_id, cable_fid, errors, excluding=()) -> float:
        """Sum the slack lengths stored against one cable.

        The filter expression is the fast path; every row it returns is checked
        again in Python, because the expression is built from field names that
        may be the pre-1.0 ones and a near-miss there must not quietly widen
        the sum.
        """
        wanted_fid = int(cable_fid)
        expr = (f"{QgsExpression.quotedColumnRef(layer_id_field)} = "
                f"{QgsExpression.quotedString(str(cable_layer_id))} AND "
                f"{QgsExpression.quotedColumnRef(fid_field)} = {wanted_fid}")
        request = QgsFeatureRequest().setFilterExpression(expr)
        if not QgsExpression(expr).isValid():
            # Cannot happen with resolved names, so if it ever does the sum is
            # not to be trusted and the caller must hear about it.
            errors.add(slack_layer.name(), f"could not build the slack filter: {expr}")
            request = QgsFeatureRequest()

        slack = 0.0
        for feat in slack_layer.getFeatures(request):
            if feat.id() in excluding:
                continue
            if str(feat[layer_id_field] or "") != str(cable_layer_id):
                continue
            raw_fid = feat[fid_field]
            if raw_fid is None or str(raw_fid).strip() in ("", "NULL"):
                continue
            try:
                if int(raw_fid) != wanted_fid:
                    continue
                slack += float(feat[length_field] or 0.0)
            except (TypeError, ValueError) as exc:
                # One unreadable row must not silently shrink the total.
                errors.add(slack_layer.name(), f"slack feature {feat.id()}: {describe(exc)}")
        return slack

    def _ground_length(self, feat, layer, errors) -> float:
        """The cable's length on the ground, or 0.0 with the reason reported."""
        try:
            return float(ground_length(feat.geometry(), layer))
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            errors.add(layer.name(), f"could not measure the cable: {describe(exc)}")
            return 0.0

    def start_slack_interactive(self, default_tip: str = "Terminal") -> None:
        """Start map tool for interactive slack placement.

        Args:
            default_tip: Default slack type ('Terminal' or 'Thru')
        """
        from ..dialogs.slack_dialog import SlackDialog
        from ..tools.slack_tool import SlackPlaceTool

        dlg = SlackDialog(self.iface.mainWindow(), default_tip=default_tip)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        params = dlg.values()
        self._reserve_tool = SlackPlaceTool(self.iface, self, params)
        self.iface.mapCanvas().setMapTool(self._reserve_tool)

    def generate_terminal_slack_for_selected(self) -> None:
        """For every selected cable, create a terminal slack at both ends."""
        errors = OperationErrors(slack_operation(), self.iface)
        count = 0
        try:
            count = self._generate_terminal_slacks(errors)
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            errors.add(None, exc)
        errors.report()
        self._say_slacks_created(count, errors.failed)

    def _generate_terminal_slacks(self, errors) -> int:
        """Create the slack points and return how many reached the layer.

        Separated from the reporting so the count is the return value rather
        than something a caller has to dig out of a collector. Hardened as its
        caller is: it is the same operation.
        """
        from ..tools.slack_tool import SlackPlaceTool

        vl = self.ensure_slack_layer()
        if vl is None:
            errors.add(None, QCoreApplication.translate(
                'FiberQSlack', "there is no optical slack layer to write to"))
            return 0

        names = vl.fields().names()
        layer_id_field, fid_field = fm.cable_link_fields(names)
        if not layer_id_field:
            # Without the pair there is nothing to attach a slack to. Creating
            # the points anyway would look like success and leave every cable
            # total permanently wrong, so this operation declines instead.
            src = QT_TRANSLATE_NOOP(
                'FiberQSlack',
                "'{layer}' has no cable reference columns, so no slack was created")
            errors.add(vl.name(), safe_format(
                QCoreApplication.translate('FiberQSlack', src), src, layer=vl.name()))
            return 0

        cable_layers = []
        for lyr in QgsProject.instance().mapLayers().values():
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                continue
            if lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry and lyr.name() in (
                "Kablovi_podzemni", "Kablovi_vazdusni",
                "Underground cables", "Aerial cables"
            ):
                cable_layers.append(lyr)

        batched = self._generate_in_one_session(
            vl, cable_layers, layer_id_field, fid_field, SlackPlaceTool, errors)
        if batched is not None:
            vl.triggerRepaint()
            return batched

        count = 0
        for cable_layer in cable_layers:
            for cable_f in cable_layer.selectedFeatures():
                line = self._endpoints_of(cable_f)
                if not line:
                    continue
                for side, point in (("od", line[0]), ("do", line[-1])):
                    if self._add_one_terminal_slack(
                            vl, cable_layer, cable_f, side, point,
                            layer_id_field, fid_field, SlackPlaceTool, errors):
                        count += 1
        vl.triggerRepaint()
        return count

    @staticmethod
    def _endpoints_of(feat):
        """The feature's vertex list, taking the first part of a multipart line.

        The multipart branch is checked **first**, and that is the whole point.
        ``asPolyline()`` does not answer an empty list for a MultiLineString:
        it raises ``TypeError`` (measured, 3.44 and 4.0), so v1.5.0's

            line = geom.asPolyline()
            if not line:
                parts = geom.asMultiPolyline()

        could never reach its own fallback. One multipart cable in the
        selection took the whole operation down with an unhandled Python error,
        and old projects -- the ones R9 is about -- are exactly where multipart
        cables are found.
        """
        geom = feat.geometry()
        if geom is None or geom.isNull():
            return []
        if QgsWkbTypes.isMultiType(geom.wkbType()):
            parts = geom.asMultiPolyline()
            return list(parts[0]) if parts else []
        return geom.asPolyline()

    def _add_one_terminal_slack(self, vl, cable_layer, cable_f, side, point,
                                layer_id_field, fid_field, tool_class, errors) -> bool:
        """One slack point at one cable end. True when it reached the layer."""
        f = self._terminal_slack(vl, cable_layer, cable_f, side, point,
                                 layer_id_field, fid_field, tool_class, errors)

        vl.startEditing()
        if not vl.addFeature(f):
            errors.add(vl.name(), QCoreApplication.translate(
                'FiberQSlack', "the slack point was rejected by the layer"))
            return False
        if not check_commit(vl, errors):
            return False

        self._record_slack_undo(vl, f, errors)
        self.recompute_slack_for_cable(cable_layer.id(), int(cable_f.id()), errors)
        return True

    def _batch_allowed(self, vl, cable_layers) -> bool:
        """True when one edit session per layer can stand in for v1.5.0's many (WP4 4.1, PF-4).

        v1.5.0 commits the slack layer once per cable end and the cable layer
        once per recompute, two recomputes per cable. One session per layer
        gives the same result only when nothing else rides on those sessions:
        layers edited and saved one by one (``_plain_edit_mode``), no session
        of the user's on a layer the batch writes (it would join it), layers
        that save all or nothing (``_saves_all_or_nothing``), and no cable
        field whose default is applied again on every update (it would count
        one update where v1.5.0 made two). The slack layer's name is not one
        of them. A pre-1.0 ``Opticke_rezerve`` layer was refused while
        ``addons/reserve_hook.py`` could rewrite cables from its commits (it
        did so only on one carrying the English link columns); the hook is
        gone (WP4 U12), nothing in the batch reads the layer's name, and its
        ``kabl_layer_id`` / ``kabl_fid`` columns resolve here exactly as in
        the loop (the "legacy slack layer" scenario in
        ``tests/test_slack_generate.py``).

        The code review found four more, each measured: a filter on the
        slack layer (v1.5.0's Undo lookup reads through it and records
        another slack, or none), a filter on a memory cable layer (a cable
        its first total moves out of the filter is not found again, so
        v1.5.0 kept that first total), a GeoPackage table whose database
        refuses or follows writes itself (a refused trial commit shows its
        own errors, and a trigger counts one update instead of two), and old
        cable type values (the restyle between v1.5.0's recomputes migrates
        them, and a refused migration leaves the totals after it unsaved).
        Otherwise v1.5.0's loop runs unchanged.
        """
        if not _plain_edit_mode():
            return False
        if vl.isEditable() or not _saves_all_or_nothing(vl) or vl.subsetString():
            return False
        if _database_answers_writes(vl):
            return False
        for layer in cable_layers:
            if layer.selectedFeatureCount() == 0:
                continue
            if layer.isEditable() or not _saves_all_or_nothing(layer) or layer.subsetString():
                return False
            if any(layer.defaultValueDefinition(i).applyOnUpdate() for i in range(layer.fields().count())):
                return False
            if _database_answers_writes(layer) or _holds_old_cable_types(layer):
                return False
        return True

    def _generate_in_one_session(self, vl, cable_layers, layer_id_field, fid_field,
                                 tool_class, errors):
        """Both end slacks of every selected cable in one session (WP4 4.1, PF-4).

        Returns the number of slacks created, as v1.5.0's loop counts them, or
        None when the loop has to run instead -- and then nothing has been
        written.

        The slacks are built as the loop builds them, added in its order and
        committed once. If any is refused, the session is put back, so nothing
        reached the layer, and the loop runs and fails as it always failed:
        slack by slack, saving the ones before the refused one. Each new slack
        is then recorded for Undo under the fid its commit gave it, which is
        the fid the loop recorded. Then each cable is recomputed once, in one
        session per cable layer, and each layer restyled once. A cable layer
        that refuses anything is put back and recomputed as the loop did it,
        once per slack, each total leaving out the slacks the loop had not
        created yet at that point -- so every figure and every message is the
        loop's.

        What the batch does not repeat is the loop's in-between writes: the
        first of a cable's two totals, overwritten by the second, and the
        commits and signals that came with it. And when a write is refused
        for a reason the file does not show beforehand (a locked or full
        disk), QGIS also reports the abandoned attempt's own provider errors.
        """
        if not self._batch_allowed(vl, cable_layers):
            return None
        held = _HeldErrors()
        try:
            ends = []
            for cable_layer in cable_layers:
                for cable_f in cable_layer.selectedFeatures():
                    line = self._endpoints_of(cable_f)
                    if line:
                        ends += [(cable_layer, cable_f, "od", line[0]), (cable_layer, cable_f, "do", line[-1])]
            slacks = [self._terminal_slack(vl, cable_layer, cable_f, side, point,
                                           layer_id_field, fid_field, tool_class, held)
                      for cable_layer, cable_f, side, point in ends]
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            # The loop meets the same problem part-way, after saving the
            # slacks before it; only the loop can say so in its own words.
            return None
        if not ends:
            return 0
        if held.failed or not vl.startEditing():
            return None
        if not all(vl.addFeature(f) for f in slacks):
            vl.rollBack()
            return None
        saved = []

        def took(_layer_id, features):
            saved.extend(features)

        vl.committedFeaturesAdded.connect(took)
        try:
            committed = vl.commitChanges()
        finally:
            vl.committedFeaturesAdded.disconnect(took)
        if not committed:
            vl.rollBack()
            return None
        self._take_saved_ids(vl, slacks, saved)
        for f in slacks:
            self._record_slack_undo(vl, f, errors)

        for cable_layer in cable_layers:
            mine = [i for i, end in enumerate(ends) if end[0] is cable_layer]
            if not mine or self._recompute_in_one_session(
                    cable_layer, list(dict.fromkeys(int(ends[i][1].id()) for i in mine))):
                continue
            for i in mine:
                later = {f.id() for f in slacks[i + 1:]}
                self.recompute_slack_for_cable(cable_layer.id(), int(ends[i][1].id()), errors, excluding=later)
        return len(slacks)

    @staticmethod
    def _take_saved_ids(vl, slacks, saved) -> None:
        """Give each new slack the fid its commit saved it under.

        ``committedFeaturesAdded`` lists the session's adds in the order they
        were added, with their new fids (measured on 3.22.16, 3.44.15 and
        4.2.3), and the session held nothing else. Each is checked against its
        slack -- the same uuid, or the same point on a layer without a uuid
        column -- and a list that does not match changes nothing: the slacks
        keep their temporary ids and ``record_add`` finds each by its point.
        """
        if len(saved) != len(slacks):
            return
        has_uuid = vl.fields().indexOf("fiberq_uuid") != -1
        for f, row in zip(slacks, saved):
            same = f["fiberq_uuid"] == row["fiberq_uuid"] if has_uuid else f.geometry().equals(row.geometry())
            if not same:
                return
        for f, row in zip(slacks, saved):
            f.setId(row.id())

    def _recompute_in_one_session(self, cable_layer, cable_fids) -> bool:
        """Each cable re-totalled once, in one session, as ``_total_slack_onto_cable`` does it.

        True when every cable took its total and the layer saved them, or
        there was nothing to write. False when anything went wrong, with the
        layer as it was: the caller then recomputes as v1.5.0 did, which says
        what went wrong in v1.5.0's words and order.
        """
        held = _HeldErrors()
        slack_layer = self.ensure_slack_layer()
        if slack_layer is None:
            return False
        names = slack_layer.fields().names()
        layer_id_field, fid_field = fm.cable_link_fields(names)
        length_field = fm.actual_field(names, "duzina_m")
        if not layer_id_field or not length_field:
            return False
        fld_slack = next((name for name in ("slack_m", "slack", "slacks_m")
                          if cable_layer.fields().indexOf(name) != -1), None)
        has_total = cable_layer.fields().indexOf("total_len_m") != -1
        opened = False
        updated = False
        for cable_fid in cable_fids:
            slack = self._slack_total(slack_layer, layer_id_field, fid_field, length_field,
                                      cable_layer.id(), cable_fid, held)
            cable_f = next(iter(cable_layer.getFeatures(QgsFeatureRequest(int(cable_fid)))), None)
            if cable_f is None or (fld_slack is None and not has_total):
                continue
            if not opened:
                if not cable_layer.startEditing():
                    return False
                opened = True
            if fld_slack:
                cable_f[fld_slack] = float(slack)
            if has_total:
                cable_f["total_len_m"] = self._ground_length(cable_f, cable_layer, held) + float(slack)
            if not cable_layer.updateFeature(cable_f):
                cable_layer.rollBack()
                return False
            updated = True
        if held.failed:
            if opened:
                cable_layer.rollBack()
            return False
        if opened and not cable_layer.commitChanges():
            cable_layer.rollBack()
            return False
        if updated:
            if self._stylize_cable_layer_callback:
                try:
                    self._stylize_cable_layer_callback(cable_layer)
                except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                    logger.warning(f"Could not restyle {cable_layer.name()!r} after a slack update: {exc}")
            cable_layer.triggerRepaint()
        return True

    def _terminal_slack(self, vl, cable_layer, cable_f, side, point,
                        layer_id_field, fid_field, tool_class, errors):
        """The slack point for one cable end, not yet added to the layer."""
        f = QgsFeature(vl.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point)))
        f["tip"] = "Terminal"
        f["duzina_m"] = 20
        f["lokacija"] = self._location_at(point, tool_class, errors)
        # Through the resolved names: on a pre-1.0 project these are
        # kabl_layer_id / kabl_fid, and writing the modern name there raises
        # KeyError and takes the whole operation down with it.
        f[layer_id_field] = cable_layer.id()
        f[fid_field] = int(cable_f.id())
        f["strana"] = side
        self._stamp_uuid(f, errors)
        return f

    def _location_at(self, point, tool_class, errors) -> str:
        """``Stub`` / ``OKNO`` / ``Objekat`` for whatever is nearest the point."""
        try:
            (nl, nf, _nd) = tool_class(self.iface, self, {})._nearest_node(QgsPointXY(point))
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            # The location is a convenience the user can correct in the
            # attribute table; the slack itself is still worth creating. Logged
            # at WARNING so it is not invisible, not collected so it does not
            # read as a failed operation.
            logger.warning(f"Could not identify what the slack sits on: {exc}")
            return "Objekat"
        if nl and nf:
            if nl.name() in ("Poles", "Stubovi"):
                return "Stub"
            if nl.name() in ("OKNA", "Manholes"):
                return "OKNO"
        return "Objekat"

    def _stamp_uuid(self, f, errors) -> None:
        """Give the slack feature its ``fiberq_uuid``, or say why it has none."""
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(f)
        except (AttributeError, ImportError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            # A slack with no identity does not travel into a bundle and cannot
            # be matched on the way back, so this is a real loss, not a detail.
            errors.add(None, f"could not give the slack an identity: {describe(exc)}")

    def _record_slack_undo(self, vl, f, errors) -> None:
        """Record the new slack with the undo manager, if there is one."""
        undo_mgr = getattr(self, 'undo_manager', None)
        if not undo_mgr:
            return
        try:
            undo_mgr.record_add(vl, f)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            # The slack is saved; only the undo entry is missing. Worth saying,
            # not worth failing the operation over.
            logger.warning(f"Could not record the new slack for undo: {exc}")

    def _say_slacks_created(self, count: int, had_problems: bool) -> None:
        """Tell the user how many slacks were created.

        Suppressed when something failed: the collector has already pushed a
        message bar entry naming the problem, and a cheerful "Created 0 slacks."
        on top of it is how a user learns to read neither.
        """
        if had_problems:
            return
        src = QT_TRANSLATE_NOOP('FiberQSlack', "Created {count} slacks.")
        text = safe_format(
            QCoreApplication.translate('FiberQSlack', src), src, count=count)
        try:
            QMessageBox.information(self.iface.mainWindow(), slack_operation(), text)
        except (AttributeError, RuntimeError, TypeError) as exc:
            logger.warning(f"Could not show the slack count: {exc}")


__all__ = ['SlackManager', 'slack_operation']
