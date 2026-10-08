# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Read and write the plugin's JSON in the project file, without losing it.

WP4 4.2 item R5. Three things of the user's live in QGIS project custom
properties as JSON strings under the ``StuboviPlugin`` scope: the optical
**relations**, the **latent** (pass-through) elements recorded per cable, and
the **colour catalogues**. Between them that is most of what a FiberQ project
knows that its layers do not.

Every loader turned "I cannot read this" into "you have none"::

    s = QgsProject.instance().readEntry(SCOPE, KEY, '')[0]
    if not s:
        return {"relations": []}
    try:
        return json.loads(s)
    except Exception:
        return {"relations": []}

-- and the very next save wrote the empty answer back over the text it could not
read. Measured end to end through the real ``DataManager``: a relations entry
that had lost its last 40 characters still contained both relation names in
readable form; the dialog opened showing none; one save and they were gone from
the project file, with nothing in the log and nothing in the message bar.

The colour-catalogue copy is the worst of the three, because its fallback is the
built-in TIA-598-C list rather than an empty one. The manager opens looking
exactly like a correct fresh install, so there is nothing to suspect. Measured:
a truncated entry answered ``['TIA-598-C']`` and after one save the user's own
``MyShop-24`` was gone from the project.

**What this module does instead**, and why it is one module rather than a fix in
each of the twelve places that had the bug: the same read-parse-default and
write-swallow pair was written out four times, and each copy had drifted. Only
the colour copies checked the parsed shape; only ``ColorManager`` wrapped its
fallback write in a second ``try``; a fourth copy in ``models/color_catalogs.py``
was never touched at all. One policy in one place is the only version of this
fix that stays fixed.

The policy, in order:

1. **An absent key says nothing.** ``readEntry`` answers a *tuple*, and its
   second element is whether the key was there at all. Measured identically on
   3.22.16 and 3.44.15::

       absent             ->  ('', False)
       present but empty  ->  ('', True)
       present, garbage   ->  (the garbage, True)
       present and good   ->  ('{"relations": []}', True)

   That distinction is what makes this safe to ship: a new project has no key,
   so it gets the default in silence. Only a key that is **present and
   unreadable** is a problem, and only that warns. Without the second element
   every new project would warn, and a warning everybody sees is a warning
   nobody reads.

2. **Unreadable text is kept, not overwritten.** The raw string is copied to a
   sibling key -- ``Relacije/relations_v1`` becomes
   ``Relacije/relations_v1_unreadable`` -- before anything else happens, and
   only if that sibling is not already occupied, so a second failed load cannot
   overwrite the first rescue with a copy of itself. The user's data survives in
   the project file where someone can get it out by hand, which is exactly what
   measurement showed was possible right up until the save destroyed it.

3. **The user is told, and the dialog still opens.** The default is still
   returned, because a colour dialog with no catalogues at all is not an
   improvement. What changes is that the failure is now on the message bar with
   the reason, instead of nowhere.

4. **A failed write answers False.** ``json.dumps`` refuses a payload it cannot
   serialise -- measured, a set inside a relation -- and the old code swallowed
   that, returned normally, and let the dialog call ``accept()``. The caller can
   now hold back its success path.

This module is the one in ``core/`` that is allowed to touch ``QgsProject``:
``project_compat`` and ``gpkg_target`` are deliberately pure, and this one
cannot be, because the store *is* the project.

i18n: the strings here are in the ``FiberQStore`` context, with
``QT_TRANSLATE_NOOP`` at the literal and ``QCoreApplication.translate`` at the
call site, so the context stays a literal argument that ``pylupdate6`` can read.
"""
import json

from qgis.core import QgsProject
from qgis.PyQt.QtCore import QCoreApplication, QT_TRANSLATE_NOOP

from ..i18n import safe_format
from ..utils.errors import describe, report_error
from ..utils.logger import get_logger

logger = get_logger(__name__)

#: Appended to a key to hold text that could not be parsed. Chosen rather than a
#: separate scope so the rescued copy travels with the project file and cannot be
#: separated from the data it came from.
QUARANTINE_SUFFIX = "_unreadable"

_STORE_TITLE = QT_TRANSLATE_NOOP('FiberQStore', "Project data")
_UNREADABLE = QT_TRANSLATE_NOOP(
    'FiberQStore',
    "{what} could not be read from this project and has been left out, so you may see fewer than"
    " you saved. The unreadable text has been kept in the project under {key} -- do not save over"
    " it if you need it back. Reason: {reason}")
_WRONG_SHAPE = QT_TRANSLATE_NOOP(
    'FiberQStore',
    "{what} is stored in this project in a form FiberQ does not recognise and has been left out."
    " The original text has been kept under {key}. Reason: {reason}")
_WRITE_FAILED = QT_TRANSLATE_NOOP(
    'FiberQStore', "{what} could not be saved into the project. Reason: {reason}")


def quarantine_unreadable(project, scope, key, raw):
    """Keep ``raw`` under ``<key>_unreadable`` so a later save cannot destroy it.

    Answers the key it was kept under, or None when it was not kept.

    **Never overwrites an existing rescue.** The second failed load of the same
    entry would otherwise replace the first rescue with a copy of itself, and if
    anything had written to the main key in between, the thing worth keeping
    would be the older copy.
    """
    if not raw:
        return None
    sibling = f"{key}{QUARANTINE_SUFFIX}"
    try:
        existing, present = project.readEntry(scope, sibling, '')
        if present and existing:
            logger.warning("%s already holds a rescued copy; leaving it alone", sibling)
            return sibling
        if not project.writeEntry(scope, sibling, raw):
            logger.warning("could not keep the unreadable text under %s", sibling)
            return None
    except (AttributeError, RuntimeError, TypeError) as exc:
        # Nothing here may raise into a loader: the point of the loader is that
        # the dialog opens. A failed rescue is still logged at WARNING.
        logger.warning("could not keep the unreadable text under %s: %s", sibling, describe(exc))
        return None
    return sibling


def read_json_entry(scope, key, default, what, expect=None, project=None, iface=None):
    """One JSON entry from the project, or ``default`` -- never silently.

    Args:
        scope: The project property scope, e.g. ``'StuboviPlugin'``.
        key: The property key, e.g. ``'Relacije/relations_v1'``.
        default: What to answer when there is nothing to read. Returned as
            given, so callers that pass a mutable default pass a fresh one.
        what: What this is, already translated, for the message the user sees:
            "Optical relations", "Colour catalogues".
        expect: A top-level member the parsed object must have, e.g.
            ``'relations'``. Valid JSON of the wrong shape is a failure too --
            a list stored where a dict belongs used to be handed straight back
            and raised ``AttributeError`` in the caller instead.
        project: The project to read. Defaults to ``QgsProject.instance()``.
        iface: The QGIS interface for the message bar. ``None`` falls back to
            ``qgis.utils.iface`` inside :func:`utils.errors.report_error`.

    Returns:
        The parsed dict, or ``default``.
    """
    project = project if project is not None else QgsProject.instance()
    try:
        raw, present = project.readEntry(scope, key, '')
    except (AttributeError, RuntimeError, TypeError) as exc:
        report_error(what, None, exc, iface)
        return default

    # A project that has never stored this is the ordinary case, not a problem.
    if not present or not raw:
        return default

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        kept = quarantine_unreadable(project, scope, key, raw)
        _report(_UNREADABLE, what, kept or key, exc, iface)
        return default

    if not isinstance(parsed, dict) or (expect is not None and expect not in parsed):
        kept = quarantine_unreadable(project, scope, key, raw)
        wanted = f"expected an object with a {expect!r} member" if expect else "expected an object"
        _report(_WRONG_SHAPE, what, kept or key, f"{wanted}, found {type(parsed).__name__}", iface)
        return default

    return parsed


def write_json_entry(scope, key, data, what, project=None, iface=None):
    """Store one JSON entry in the project. True when it got there.

    ``json.dumps`` is inside the same guard as the write on purpose: a payload
    it refuses is the failure the old code hid most often, and from the caller's
    side "not serialised" and "not written" need the same answer.

    The ``writeEntry`` result is read too, but do not mistake that for the
    safety here. The ratchet's ``WRITE_CALLS`` leaves ``writeEntry`` out on
    purpose, with the reason that it only edits the in-memory project and
    answers True even for an empty key, so checking it is noise rather than
    safety. That is right, and it is checked only because this function has to
    answer a bool anyway. **The failure this catches in practice is
    ``json.dumps``**, measured: a set inside a relation, swallowed, with the
    dialog then calling ``accept()``.
    """
    project = project if project is not None else QgsProject.instance()
    try:
        text = json.dumps(data)
    except (TypeError, ValueError) as exc:
        _report_write(what, exc, iface)
        return False
    try:
        if not project.writeEntry(scope, key, text):
            _report_write(what, "the project refused the entry", iface)
            return False
    except (AttributeError, RuntimeError, TypeError) as exc:
        _report_write(what, exc, iface)
        return False
    return True


def _report(source, what, key, reason, iface):
    """One message-bar line for a load that could not be trusted."""
    report_error(
        QCoreApplication.translate('FiberQStore', _STORE_TITLE),
        None,
        safe_format(QCoreApplication.translate('FiberQStore', source), source,
                    what=what, key=key, reason=describe(reason)),
        iface)


def _report_write(what, reason, iface):
    report_error(
        QCoreApplication.translate('FiberQStore', _STORE_TITLE),
        None,
        safe_format(QCoreApplication.translate('FiberQStore', _WRITE_FAILED), _WRITE_FAILED,
                    what=what, reason=describe(reason)),
        iface)


__all__ = ['QUARANTINE_SUFFIX', 'quarantine_unreadable', 'read_json_entry', 'write_json_entry']
