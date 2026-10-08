"""A translator cannot break a file dialog.

WP4 FU-2 item U10. Unclaimed: an ordinary bug fix shipping in v1.6.0.

A Qt file filter is one string mixing two audiences::

    "GIS files (*.kml *.kmz *.shp)"
     ^^^^^^^^^  ^^^^^^^^^^^^^^^^^^
     for people  for Qt

FiberQ passed the whole thing through ``tr()``, handing the patterns to the
translator along with the label. Translate ``*.kml``, lose a space, or change
the parentheses, and the dialog shows no files at all -- and nothing can notice,
because Qt accepts any string. The Serbian and French catalogues are the live
risk: both are volunteer-maintained, and ``docs/i18n.md`` already has a rule
against translating layer names for the same reason.

So the label is translated and the patterns are not. This test walks the AST of
the whole package and fails if a translated literal contains ``*.`` again --
which is the only way to keep the rule, since the mistake is invisible at
runtime.

It also pins what the patterns must cover, because the two importers had
drifted apart: the route importer's list was missing GeoJSON and the point
importer's was missing DXF.
"""
import ast
import io
import os

import pytest

from fiberq.utils import file_filters as ff

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO_ROOT, "fiberq")

#: Names that mark a string as going to a translator.
TRANSLATORS = frozenset({"tr", "translate", "QT_TRANSLATE_NOOP", "safe_format"})


def _python_files():
    for folder, _dirs, names in os.walk(PACKAGE):
        if "__pycache__" in folder:
            continue
        for name in sorted(names):
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def _called_name(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def test_no_translated_literal_carries_a_file_pattern():
    """The rule, enforced where it cannot be forgotten."""
    offenders = []
    for path in _python_files():
        if os.path.basename(path) == "file_filters.py":
            continue  # the one module whose job is to hold the patterns
        tree = ast.parse(io.open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _called_name(node) not in TRANSLATORS:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if "*." in arg.value:
                        offenders.append(
                            f"{os.path.relpath(path, REPO_ROOT)}:{node.lineno} {arg.value!r}")
    assert not offenders, (
        "A file pattern inside a translated string can be translated, and a "
        "translated pattern shows the user an empty file dialog. Put the label "
        "in tr() and the patterns in utils/file_filters.py. Found: " + str(offenders))


# ---------------------------------------------------------------------------
# What the patterns have to cover
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pattern", ["*.kml", "*.kmz", "*.shp", "*.gpx",
                                     "*.geojson", "*.json", "*.dxf", "*.dwg"])
def test_the_gis_list_covers_every_format_both_importers_accept(pattern):
    """The route importer was missing GeoJSON; the point one was missing DXF."""
    assert pattern in ff.GIS.split()


def test_the_gis_list_does_not_offer_a_geopackage():
    """Deliberate, and the build plan says so.

    A GeoPackage usually holds several layers, and QgsVectorLayer(path, ...,
    "ogr") silently opens the first one -- so offering it here would import
    whichever layer happened to be first and report success. It needs a
    sublayer picker first.
    """
    assert "*.gpkg" not in ff.GIS


def test_the_bundle_filter_does_name_a_geopackage():
    """A bundle is a known single-purpose file, which is the difference."""
    assert ff.BUNDLE == "*.gpkg"


def test_any_is_not_star_dot_star():
    """``*.*`` excludes files with no extension, which on Linux is real."""
    assert ff.ANY == "*"


# ---------------------------------------------------------------------------
# The builders
# ---------------------------------------------------------------------------

def test_named_builds_one_entry():
    assert ff.named("GIS files", "*.kml *.shp") == "GIS files (*.kml *.shp)"


def test_with_any_appends_an_all_files_entry():
    built = ff.with_any("GIS files", "*.kml", "All files")
    assert built == "GIS files (*.kml);;All files (*)"


def test_a_built_filter_has_the_shape_qt_expects():
    """Every entry is ``label (patterns)``, separated by ``;;``."""
    built = ff.with_any("GIS files", ff.GIS, "All files")
    for entry in built.split(";;"):
        assert entry.count("(") == 1 and entry.endswith(")")
        label, patterns = entry.split(" (", 1)
        assert label.strip() == label and label
        assert patterns.rstrip(")")


# ---------------------------------------------------------------------------
# The call sites use it
# ---------------------------------------------------------------------------

def test_every_open_dialog_filter_comes_from_this_module():
    """A literal filter at an OPEN dialog is how the two lists drifted apart.

    Open dialogs only, and the name says so now. A save dialog names one format
    of its own -- PNG, SVG, JSON, ``.gpkg`` -- shares its list with nothing, and
    passes the filter as a plain literal rather than through ``tr()``. Eight
    such sites keep their pattern inline on purpose (measured by AST:
    ``export_manager.py:350``, ``bom_dialog.py:237, :239``,
    ``color_dialog.py:180``, ``schematic_dialog.py:879, :892, :904``,
    ``routing_ui.py:342``), so widening this scan to ``getSaveFileName`` turns
    it red on all eight for no gain.

    The rule that can actually break a dialog -- a translator editing a pattern
    -- is carried by
    :func:`test_no_translated_literal_carries_a_file_pattern`, which walks every
    translated literal regardless of which dialog it reaches.
    """
    offenders = []
    for path in _python_files():
        if os.path.basename(path) == "file_filters.py":
            continue
        tree = ast.parse(io.open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _called_name(node) not in ("getOpenFileName", "getOpenFileNames"):
                continue
            # The filter is the 4th positional argument, or the `filter` keyword.
            candidates = list(node.args[3:4])
            candidates += [kw.value for kw in node.keywords if kw.arg == "filter"]
            for arg in candidates:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and "*." in arg.value:
                    offenders.append(
                        f"{os.path.relpath(path, REPO_ROOT)}:{node.lineno} {arg.value!r}")
    assert not offenders, (
        "Build the filter with utils/file_filters so the patterns stay in one "
        f"place. Found: {offenders}")
