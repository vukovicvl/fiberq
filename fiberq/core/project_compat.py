"""Whether the project in front of us was written by a QGIS that stores more than we can read.

A pure-data module like :mod:`fiberq.core.gpkg_target`: no QGIS import, so the
rule is testable as plain Python and the caller supplies the facts.

QGIS 4 changed how a project's custom properties are serialised. Where QGIS 3
writes ``<FiberQPlugin><gpkg_path .../></FiberQPlugin>``, QGIS 4 writes
``<properties name="FiberQPlugin"><properties name="gpkg_path" .../></properties>``.
QGIS 3 does not understand the newer form, so opening a QGIS 4 project in QGIS 3
loses **every** project entry -- not a selected few. Measured on 3.22, 3.44 and
4.0: relations, colour catalogues, latent elements, picture and drawing links,
the auto-save path and WP3's interchange passthrough store all read back empty.

Two of those fail quietly enough to be dangerous. Colour catalogues fall back to
the built-in defaults, so the user sees plausible colours rather than an absence.
And the passthrough store holds data carried through an import on behalf of
another tool, which is precisely what WP3 exists not to lose.

The direction matters: a project written by QGIS 3 opens on QGIS 4 with
everything intact. Only 4-then-3 loses, and saving in QGIS 3 after that makes
the loss permanent -- measured 4 -> 3 -> 4, the entries never come back. Hence
the advice attached to the warning: look, but do not save.

QGIS itself logs a generic "saved with a newer version of qgis" line to the log
panel. It does not say what FiberQ lost, and the log panel is not where a user
is looking. That is the gap this fills.
"""

#: The QGIS major version that changed the project-properties format.
QGIS_4 = 4


def opened_a_newer_project(saved_major, running_major, has_fiberq_layers):
    """True when this project's FiberQ settings cannot be read by this QGIS.

    Args:
        saved_major: ``QgsProject.lastSaveVersion().majorVersion()``. A project
            that has never been saved reports 0, which is why this is a
            ``>=`` test against :data:`QGIS_4` rather than a truthiness check.
        running_major: The major version of the QGIS actually running.
        has_fiberq_layers: Whether the project holds anything of ours. A user
            opening somebody else's QGIS 4 project has lost nothing of FiberQ's
            and does not need to hear about it.

    Returns:
        True when the user should be told, once.
    """
    if not has_fiberq_layers:
        return False
    if running_major >= QGIS_4:
        return False
    return saved_major >= QGIS_4


__all__ = ["QGIS_4", "opened_a_newer_project"]
