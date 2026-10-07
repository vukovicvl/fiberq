"""File-dialog filters: translated labels, fixed patterns.

WP4 FU-2 item U10. A Qt file filter is one string that mixes two things::

    "GIS files (*.kml *.kmz *.shp)"
     ^^^^^^^^^  ^^^^^^^^^^^^^^^^^^
     for people  for Qt

FiberQ passed the whole string through ``tr()``, so a translator was handed the
patterns along with the label. Translating ``*.kml`` -- or just losing a space,
or helpfully changing the parentheses -- produces a dialog that shows no files
at all, and the plugin has no way to notice: Qt takes any string.

So the label is translated here and the patterns are not. The patterns live in
this module as constants, which also means they are in **one** place: the two
importers had slightly different lists, and the route importer's was missing
GeoJSON while the point importer's was missing DXF.

``tests/test_file_filters.py`` walks the AST of the whole package and fails if
any translated literal contains ``*.`` again.

**No ``*.gpkg`` in the GIS list**, deliberately. A GeoPackage usually holds
several layers, and ``QgsVectorLayer(path, …, "ogr")`` silently opens the first
one -- so offering it here would import whichever layer happened to be first
and report success. It needs a sublayer picker first; the build plan says so and
leaves it out until then. The interchange-bundle dialog is a different case: a
bundle is a known single-purpose file and that filter names it on purpose.
"""

#: Everything the "choose a file" dialogs accept, in one place.
#: ``*.json`` sits beside ``*.geojson`` because both spellings are in the wild.
GIS = "*.kml *.kmz *.shp *.gpx *.geojson *.json *.dxf *.dwg"

#: Pictures that can be attached to a feature.
IMAGES = "*.jpg *.jpeg *.png *.gif"

#: CAD drawings that can be attached to a feature.
DRAWINGS = "*.dwg *.dxf"

#: A FiberQ interchange bundle.
BUNDLE = "*.gpkg"

#: A colour catalogue.
JSON = "*.json"

#: Qt's "anything" pattern. Not ``*.*``: that excludes files with no
#: extension, which on Linux is a real thing to exclude by accident.
ANY = "*"


def named(label: str, patterns: str) -> str:
    """One filter entry: ``"GIS files (*.kml *.kmz)"``.

    Args:
        label: Already translated, and without parentheses.
        patterns: One of this module's constants.
    """
    return f"{label} ({patterns})"


def with_any(label: str, patterns: str, any_label: str) -> str:
    """A filter entry followed by an "All files" entry.

    Args:
        label: Already translated.
        patterns: One of this module's constants.
        any_label: Already translated, e.g. ``tr("All files")``.
    """
    return f"{named(label, patterns)};;{named(any_label, ANY)}"


__all__ = ['ANY', 'BUNDLE', 'DRAWINGS', 'GIS', 'IMAGES', 'JSON',
           'named', 'with_any']
