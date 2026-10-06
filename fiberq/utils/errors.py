"""Say when an operation fails, instead of leaving the reason in the debug log.

A FiberQ operation -- save all layers, import a route, lay a cable -- touches
many features across many layers, and any one of them can fail on its own: a
GeoPackage held open by another program, a provider that refuses a geometry, a
coordinate that will not reproject. Nearly all of those failures currently land
in ``except Exception as e: logger.debug(...)``, which at the default log level
writes nothing, anywhere. The operation then reports success, and the user finds
the missing features much later, or never.

This module is the one place that decides what a failure looks like. Three
pieces, and they exist together on purpose:

:class:`OperationErrors`
    A collector for one operation. Each failing part calls
    :meth:`~OperationErrors.add`, which logs it at WARNING **with the
    traceback**; when the operation ends the collector pushes a **single**
    message-bar entry naming the first problem and counting the rest. One failed
    layer out of twelve is one line, not twelve pop-ups -- and twelve failed
    layers are still one line, because a message bar the user has to dismiss
    twelve times is a message bar the user learns to ignore.

:func:`report_error`
    The same thing for a failure that has no siblings.

:func:`check_commit`
    ``layer.commitChanges()`` answers with a bool that most of this plugin's
    call sites throw away. This wraps it and, on failure, adds the provider's
    own ``commitErrors()`` text -- usually the only place the real reason is
    written down.

**A failed commit is never rolled back here.** When QGIS refuses a commit it
keeps the edits in the layer's buffer, so the user can clear the cause -- close
the other program, fix the permission -- and save again. Calling ``rollBack()``
to tidy up would throw that work away, which is a worse outcome than the failure
the user is being told about.

**Nothing in here may be silent itself.** Every handler below logs at WARNING,
including the ones guarding the message bar. A module whose whole job is to stop
errors disappearing cannot be allowed to lose its own.

i18n: the user-facing strings here belong to the ``FiberQErrors`` context and use
the explicit inline form -- ``QT_TRANSLATE_NOOP('FiberQErrors', ...)`` at the
literal, ``QCoreApplication.translate('FiberQErrors', src)`` at the call site.
Never a module-level ``tr()`` helper and never a context held in a constant:
``pylupdate6`` reads the literal argument and can extract neither.
"""
from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP

from .logger import get_logger

logger = get_logger(__name__)

#: Distinct provider lines carried into the message bar before it gives up and
#: counts the rest. A GeoPackage trigger that rejects 20,000 features answers
#: with 20,002 commitErrors() lines; the first few say what is wrong and the
#: rest say it again with a different feature id.
_MAX_REASONS = 3


def _safe_format(translated, source, **kwargs):
    """Interpolate into a translated message, falling back to the English source
    if a volunteer renamed a placeholder (see ``fiberq.i18n.safe_format``)."""
    from ..i18n import safe_format
    return safe_format(translated, source, **kwargs)


def describe(problem) -> str:
    """One readable line for an exception, or for a reason given as plain text.

    The exception's type is kept: "the file is open in another program" is the
    operating system's half of the story and ``PermissionError`` is ours, and
    the type alone is what makes a bug report actionable when the message is
    empty -- which, for several Qt and OGR errors, it is.
    """
    if isinstance(problem, BaseException):
        text = str(problem).strip()
        name = type(problem).__name__
        return f"{name}: {text}" if text else name
    text = str(problem).strip()
    return text if text else repr(problem)


def _line(what, reason) -> str:
    """``"Underground cables: ERROR: ..."``, or the bare reason when the failure
    belongs to the operation as a whole rather than to one of its parts."""
    return f"{what}: {reason}" if what else reason


class OperationErrors:
    """Everything that went wrong in one operation, said once at the end.

    Typical use, with the collector handed to each part that can fail::

        with OperationErrors(self.tr("Save all layers"), self.iface) as errors:
            for layer in layers:
                if not check_commit(layer, errors):
                    continue
                ...
            if not errors.failed:
                self.iface.messageBar().pushSuccess(...)

    Args:
        operation: What the user asked for, already translated. It becomes the
            title of the message-bar entry, so keep it short: "Save all layers".
        iface: The QGIS interface. ``None`` falls back to ``qgis.utils.iface``,
            and where there is no interface at all -- tests, headless runs, a
            processing algorithm -- the problems are logged and nothing is
            pushed. Never a reason for the operation itself to fail.
        absorb: For a Qt slot, which must not raise. An exception leaving the
            block is then recorded and reported like any other problem instead
            of reaching QGIS's "unhandled Python error" dialog.
            ``KeyboardInterrupt`` and ``SystemExit`` are never absorbed.
    """

    def __init__(self, operation, iface=None, absorb=False):
        self.operation = operation
        self.iface = iface
        self.absorb = absorb
        #: ``[(what, reason)]`` in the order the failures happened.
        self.problems = []
        #: How many of them have already reached the message bar.
        self._reported = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        absorbed = False
        if isinstance(exc, Exception):
            # Not BaseException: Ctrl+C and interpreter shutdown are not ours
            # to report, and absorbing them would hang the host.
            self.add(None, exc)
            absorbed = self.absorb
        self.report()
        return absorbed

    def __len__(self):
        return len(self.problems)

    @property
    def failed(self) -> bool:
        """True once anything has been added, so the caller can hold back its
        success message without counting the list itself."""
        return bool(self.problems)

    def add(self, what, problem) -> None:
        """Record one failure, and log it at WARNING with the traceback.

        Args:
            what: The part that failed -- a layer name, a file path, a feature
                id. ``None`` when the operation as a whole failed and naming a
                part would be a guess.
            problem: The exception, or a string where there is no exception to
                carry: a provider that answered False and left its reason in a
                separate error list.
        """
        reason = describe(problem)
        self.problems.append((what, reason))
        logger.warning(
            f"{self.operation}: {_line(what, reason)}",
            exc_info=problem if isinstance(problem, BaseException) else False)

    def message(self) -> str:
        """The single line the user reads. Empty when nothing has failed."""
        return self._render(self.problems)

    def _render(self, problems) -> str:
        """That line, for any list of problems. Pure: it reads no state."""
        if not problems:
            return ""
        first = _line(*problems[0])
        others = len(problems) - 1
        if others:
            src = QT_TRANSLATE_NOOP(
                'FiberQErrors',
                "{problem} (+{count} more). See Log Messages > FiberQ for the details.")
            return _safe_format(
                QCoreApplication.translate('FiberQErrors', src), src,
                problem=first, count=others)
        src = QT_TRANSLATE_NOOP(
            'FiberQErrors', "{problem}. See Log Messages > FiberQ for the details.")
        return _safe_format(
            QCoreApplication.translate('FiberQErrors', src), src, problem=first)

    def report(self) -> bool:
        """Push the one message-bar entry. True when there was something to say.

        Called automatically on leaving the ``with`` block. Calling it by hand
        is for the rare operation that reports and then carries on; only the
        problems added since the last call are pushed, so doing both does not
        show the user the same failure twice.
        """
        fresh = self.problems[self._reported:]
        if not fresh:
            return False
        # Counted as said before it is said, so a message bar that throws does
        # not make the next call repeat what the user has already read.
        self._reported = len(self.problems)
        bar = self._message_bar()
        if bar is not None:
            try:
                bar.pushWarning(self.operation, self._render(fresh))
            except (AttributeError, RuntimeError) as exc:
                # The user still learns of it: every problem is already in the
                # log at WARNING, which is what the message points them at.
                logger.warning(f"Could not push the FiberQ message bar entry: {exc}")
        return True

    def _message_bar(self):
        """The message bar to push to, or None when running without a GUI."""
        iface = self.iface
        if iface is None:
            try:
                from qgis.utils import iface as qgis_iface
            except ImportError:  # pragma: no cover - outside QGIS
                return None
            iface = qgis_iface
        if iface is None:
            return None
        try:
            return iface.messageBar()
        except (AttributeError, RuntimeError) as exc:
            logger.warning(f"No message bar to report {self.operation!r} on: {exc}")
            return None


def report_error(operation, what, problem, iface=None) -> None:
    """Report a single failure: :class:`OperationErrors` for one problem.

    For a handler that has nothing else to collect::

        except OSError as exc:
            report_error(self.tr("BOM export"), path, exc, self.iface)
            return
    """
    errors = OperationErrors(operation, iface=iface)
    errors.add(what, problem)
    errors.report()


def _commit_reason(layer) -> str:
    """The provider's own account of a refused commit, folded onto one line.

    ``commitErrors()`` returns a list whose entries carry embedded newlines --
    a summary line and then one per rejected feature, so a trigger that rejects
    twenty thousand features answers with twenty thousand near-identical lines.
    The message bar shows one line, so the first :data:`_MAX_REASONS` distinct
    ones are joined and the rest are counted. Membership is tested against a
    set, not the list being built: the list form was quadratic, and measured at
    1.6 seconds on the UI thread for that twenty-thousand case.
    """
    if not layer.isEditable():
        # Asked first, because QGIS answers this case with its own untranslated
        # "ERROR: layer not editable" in commitErrors(); folding that would win
        # and the friendlier sentence would never be reached.
        src = QT_TRANSLATE_NOOP('FiberQErrors', "the layer was not in edit mode")
        return QCoreApplication.translate('FiberQErrors', src)

    reasons = []
    seen = set()
    extra = 0
    for entry in layer.commitErrors() or []:
        for part in str(entry).splitlines():
            part = part.strip()
            if not part or part in seen:
                continue
            seen.add(part)
            if len(reasons) < _MAX_REASONS:
                reasons.append(part)
            else:
                extra += 1
    if reasons:
        folded = "; ".join(reasons)
        return f"{folded}; +{extra} more" if extra else folded
    src = QT_TRANSLATE_NOOP('FiberQErrors', "QGIS refused the commit without saying why")
    return QCoreApplication.translate('FiberQErrors', src)


def check_commit(layer, errors, what=None) -> bool:
    """``layer.commitChanges()``, with the failure reported instead of discarded.

    Args:
        layer: The vector layer to commit.
        errors: The :class:`OperationErrors` collecting this operation.
        what: What to call the layer in the message. Defaults to its own name.

    Returns:
        True when the edits reached the provider.

    The layer is **not** rolled back on failure, and that is the point: QGIS
    keeps the rejected edits buffered, so the user can clear the cause and save
    again. See the module docstring.
    """
    # Resolved before the try, so a raster layer reaching a per-layer loop --
    # it has no commitChanges() at all -- is still reported BY NAME, which in a
    # loop over every project layer is the only useful part of the message.
    name = what
    try:
        name = what or layer.name()
        if layer.commitChanges():
            return True
        reason = _commit_reason(layer)
    except (AttributeError, RuntimeError) as exc:
        # Something that is not a vector layer, or one whose C++ object is
        # already gone. Both are worth saying out loud.
        errors.add(name, exc)
        return False
    errors.add(name, reason)
    return False


__all__ = ['OperationErrors', 'check_commit', 'describe', 'report_error']
