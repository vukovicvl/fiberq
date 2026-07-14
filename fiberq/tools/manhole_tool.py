"""
FiberQ v2 - Manhole Tool

Tool for placing manholes on the route network.
Supports auto-incrementing manhole IDs on repeated placement.
"""

import re

from .base import (
    Qt,
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsWkbTypes,
    QgsMapToolEmitPoint
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


def parse_id_parts(id_string):
    """
    Parse a manhole ID string into prefix, number, and zero-padding width.

    Examples:
        'MH 1'      -> ('MH ', 1, 0)     — no zero-padding
        'OKNO-001'   -> ('OKNO-', 1, 3)   — 3-digit zero-padded
        'K-10'       -> ('K-', 10, 0)     — no zero-padding
        '5'          -> ('', 5, 0)         — number only
        'abc'        -> ('abc', None, 0)   — no number found

    Returns:
        Tuple (prefix, number, pad_width)
        prefix:    everything before the last numeric group
        number:    integer value of the last numeric group, or None
        pad_width: width of zero-padding (0 if not zero-padded)
    """
    if not id_string:
        return ('', None, 0)

    # Find the LAST contiguous group of digits in the string
    match = None
    for match in re.finditer(r'\d+', id_string):
        pass  # iterate to the last match

    if match is None:
        return (id_string, None, 0)

    num_str = match.group()
    prefix = id_string[:match.start()]
    number = int(num_str)

    # Determine zero-padding: only if the number string has leading zeros
    # or is longer than the minimal representation
    if len(num_str) > 1 and num_str[0] == '0':
        pad_width = len(num_str)
    elif len(num_str) > len(str(number)):
        pad_width = len(num_str)
    else:
        pad_width = 0

    return (prefix, number, pad_width)


def format_id(prefix, number, pad_width):
    """
    Format a manhole ID from its parts.

    Args:
        prefix:    string prefix (e.g. 'MH ', 'OKNO-')
        number:    integer to format
        pad_width: zero-padding width (0 = no padding)

    Returns:
        Formatted ID string, e.g. 'MH 3' or 'OKNO-003'
    """
    if pad_width > 0:
        return f"{prefix}{number:0{pad_width}d}"
    else:
        return f"{prefix}{number}"


class ManholePlaceTool(QgsMapToolEmitPoint):
    """
    Tool for placing manholes on the map.

    Snaps to route vertices and segment midpoints.
    Uses attributes previously set via the manhole dialog.

    Auto-increment mode:
        When enabled, each click auto-increments the manhole ID number.
        The prefix and zero-padding from the initial ID are preserved.
    """

    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin

        # Auto-increment state
        self._auto_increment = False
        self._id_prefix = ''
        self._id_counter = 1
        self._id_pad_width = 0
        self._placement_count = 0

    def set_auto_increment(self, enabled, initial_id=''):
        """
        Configure auto-increment from the user's initial ID string.

        Args:
            enabled:    True to enable auto-incrementing
            initial_id: The ID the user typed in the dialog (e.g. 'MH 1', 'OKNO-001')
        """
        self._auto_increment = enabled

        if not enabled:
            return

        prefix, number, pad_width = parse_id_parts(initial_id)
        self._id_prefix = prefix
        self._id_pad_width = pad_width

        if number is not None:
            self._id_counter = number
        else:
            # User typed a prefix with no number — start from 1
            self._id_counter = 1
            # Add a separator if prefix doesn't end with space or punctuation
            if prefix and prefix[-1] not in (' ', '-', '_', '.', '/'):
                self._id_prefix = prefix + ' '

        # Check existing manholes to avoid duplicates
        self._advance_past_existing_ids()

    def _advance_past_existing_ids(self):
        """
        Scan the manhole layer for existing IDs that match our prefix,
        and advance the counter past the highest one found.
        """
        try:
            manhole_layer = self._find_manhole_layer()
            if not manhole_layer:
                return

            highest = self._id_counter - 1  # start below our current value

            for feat in manhole_layer.getFeatures():
                existing_id = feat.attribute('broj_okna')
                if not existing_id:
                    continue

                existing_id = str(existing_id)
                prefix, number, _ = parse_id_parts(existing_id)

                # Only consider IDs with the same prefix
                if prefix == self._id_prefix and number is not None:
                    if number > highest:
                        highest = number

            # If we found existing IDs >= our start, advance past them
            if highest >= self._id_counter:
                old_counter = self._id_counter
                self._id_counter = highest + 1
                logger.debug(
                    f"Auto-increment: advanced from {old_counter} to "
                    f"{self._id_counter} (existing IDs found up to {highest})"
                )
        except Exception as e:
            logger.debug(f"Error scanning existing IDs: {e}")

    def _get_current_id(self):
        """Get the current formatted ID without incrementing."""
        return format_id(self._id_prefix, self._id_counter, self._id_pad_width)

    def _get_next_id(self):
        """Get the current ID and advance the counter for the next placement."""
        current_id = self._get_current_id()
        self._id_counter += 1
        return current_id

    def _find_manhole_layer(self):
        """Find the Manholes layer in the project."""
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.name() in ('Manholes', 'OKNA') and  # noqa: W504
                        lyr.geometryType() == QgsWkbTypes.GeometryType.PointGeometry):
                    return lyr
            except Exception as e:
                logger.debug(f"Error in ManholePlaceTool._find_manhole_layer: {e}")
        return None

    def _find_route_layer(self):
        """Find the Route layer in the project."""
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if (isinstance(lyr, QgsVectorLayer) and  # noqa: W504
                    lyr.name() in ('Route', 'Trasa') and  # noqa: W504
                        lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry):
                    return lyr
            except Exception as e:
                logger.debug(f"Error in ManholePlaceTool._find_route_layer: {e}")
        return None

    def _snap_to_route(self, point):
        """
        Snap a point to route vertices or segment midpoints.

        Returns:
            Tuple of (snapped_point, min_distance) or (None, None)
        """
        route_layer = self._find_route_layer()
        if route_layer is None or route_layer.featureCount() == 0:
            return None, None

        snap_point = None
        min_dist = None

        for feat in route_layer.getFeatures():
            geom = feat.geometry()
            if geom.isMultipart():
                lines = geom.asMultiPolyline()
            else:
                lines = [geom.asPolyline()]

            for line in lines:
                if not line:
                    continue

                # Check all vertices
                for p in line:
                    d = QgsPointXY(point).distance(QgsPointXY(p))
                    if min_dist is None or d < min_dist:
                        min_dist = d
                        snap_point = QgsPointXY(p)

                # Check segment midpoints
                for i in range(len(line) - 1):
                    mid = QgsPointXY(
                        (line[i].x() + line[i + 1].x()) / 2,
                        (line[i].y() + line[i + 1].y()) / 2
                    )
                    d = QgsPointXY(point).distance(mid)
                    if min_dist is None or d < min_dist:
                        min_dist = d
                        snap_point = mid

        return snap_point, min_dist

    def canvasReleaseEvent(self, event):
        """Handle mouse release - place manhole."""
        point = self.toMapCoordinates(event.pos())

        # Snap to route
        snap_point, min_dist = self._snap_to_route(point)
        tolerance = self.iface.mapCanvas().mapUnitsPerPixel() * 20

        if snap_point is not None and min_dist is not None and min_dist < tolerance:
            point = snap_point

        # Get or create manhole layer
        layer = self.plugin._ensure_okna_layer()

        # Create feature
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point)))

        # Get pending attributes from plugin
        attrs = getattr(self.plugin, '_manhole_pending_attrs', {}) or {}

        # Determine the manhole ID
        if self._auto_increment:
            broj = self._get_next_id()
        else:
            broj = attrs.get('broj_okna') or ''

        f['broj_okna'] = broj

        # Set other attributes
        attr_fields = [
            'tip_okna', 'vrsta_okna', 'polozaj_okna', 'adresa', 'stanje',
            'god_ugrad', 'opis', 'dimenzije', 'mat_zida', 'mat_poklop',
            'odvodnj', 'poklop_tes', 'poklop_lak', 'br_nosaca', 'debl_zida', 'lestve'
        ]

        for key in attr_fields:
            if key in attrs and key in layer.fields().names():
                f[key] = attrs.get(key)

        # Phase 0.1: Set UUID for FiberQ Designer
        try:
            from ..utils.uuid_utils import set_feature_uuid
            set_feature_uuid(f)
        except Exception as e:
            from ..utils.logger import get_logger
            get_logger(__name__).debug(f"Error setting UUID on manhole: {e}")

        # Add feature
        try:
            layer.startEditing()
            layer.addFeature(f)
            layer.commitChanges()
        except Exception:
            layer.dataProvider().addFeatures([f])

        layer.updateExtents()
        layer.triggerRepaint()

        # Record for undo (v1.2 — Feature 2)
        try:
            if hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                self.plugin.undo_manager.record_add(layer, f)
        except Exception as e:
            logger.debug(f"Error recording undo for manhole: {e}")

        # Apply style
        self.plugin._apply_manhole_style(layer)
        self.plugin._move_layer_to_top(layer)

        # Increment placement counter
        self._placement_count += 1

        # Show message with next ID preview if auto-incrementing
        if self._auto_increment:
            next_id = self._get_current_id()
            self.iface.messageBar().pushInfo(
                "Manholes",
                f"Manhole placed: {broj}  \u2014  next: {next_id}  (ESC to exit)"
            )
        else:
            self.iface.messageBar().pushInfo(
                "Manholes",
                f"Manhole placed: {broj or '(no ID)'}"
            )

    def keyPressEvent(self, event):
        """Handle ESC key to cancel tool."""
        if event.key() == Qt.Key.Key_Escape:
            try:
                if self._auto_increment and self._placement_count > 0:
                    self.iface.messageBar().pushInfo(
                        "Manholes",
                        f"Finished placing {self._placement_count} manholes."
                    )
                self.iface.mapCanvas().unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in ManholePlaceTool.keyPressEvent: {e}")

    def canvasPressEvent(self, event):
        """Handle right-click to cancel tool."""
        if event.button() == Qt.MouseButton.RightButton:
            try:
                if self._auto_increment and self._placement_count > 0:
                    self.iface.messageBar().pushInfo(
                        "Manholes",
                        f"Finished placing {self._placement_count} manholes."
                    )
                self.iface.mapCanvas().unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in ManholePlaceTool.canvasPressEvent: {e}")


__all__ = ['ManholePlaceTool']
