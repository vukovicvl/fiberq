"""
FiberQ v2 - Branch Info Tool

Map tool for displaying cable information at click location.
Phase 2.1: Extracted from extracted_classes.py
"""

from collections import Counter

from qgis.PyQt.QtCore import Qt

from qgis.core import QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapToolIdentify

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class BranchInfoTool(QgsMapToolIdentify):
    """Click on cable → info about number of cables, type/capacity and length in message bar."""

    def __init__(self, core):
        super().__init__(core.iface.mapCanvas())
        self.core = core
        self.iface = core.iface
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _attr(self, f, names, default=""):
        """Return first populated field from list of names."""
        try:
            field_names = f.fields().names()
        except Exception:
            field_names = []
        for n in names:
            if n in field_names:
                v = f[n]
                if v not in (None, ""):
                    return v
        return default

    def canvasReleaseEvent(self, e):
        # Right click = exit tool
        if e.button() == Qt.MouseButton.RightButton:
            try:
                self.iface.mapCanvas().unsetMapTool(self)
            except Exception as e:
                logger.debug(f"Error in BranchInfoTool.canvasReleaseEvent: {e}")
            return

        if e.button() != Qt.MouseButton.LeftButton:
            return

        # Identify objects under click
        hits = self.identify(e.pos().x(), e.pos().y(), self.TopDownAll, self.VectorLayer)

        cable_hits = []
        for h in hits or []:
            lyr = h.mLayer
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
                    name = (lyr.name() or "").lower().strip()
                    # Accept both old and new cable layer names
                    if name in (
                        "kablovi_podzemni",
                        "kablovi_vazdusni",
                        "underground cables",
                        "aerial cables",
                    ):
                        cable_hits.append(h)
            except Exception as e:
                logger.debug(f"Error in BranchInfoTool.canvasReleaseEvent: {e}")

        if not cable_hits:
            self.iface.messageBar().pushInfo("Branch info", "No cables at this location.")
            return

        feats = [h.mFeature for h in cable_hits]
        total_len = 0.0
        by_type = Counter()

        for f in feats:
            tip = self._attr(f, ["tip", "Tip", "TIP"], "n/a")
            br_c = self._attr(f, ["broj_cevcica", "cevi"], "")  # noqa: F841
            br_v = self._attr(f, ["broj_vlakana", "vlakna"], "")
            cap = f"{br_v}f" if br_v else ""  # Issue #3: Show just fiber count with 'f'
            key = f"{tip} {cap}".strip() or "unknown"
            by_type[key] += 1

            try:
                geom = f.geometry()
                if geom:
                    total_len += float(geom.length())
            except Exception as e:
                logger.debug(f"Error in BranchInfoTool.canvasReleaseEvent: {e}")

        parts = [f"{cnt}× {k}" for k, cnt in by_type.items()]
        msg = f"Cables at click: {len(feats)}"
        if parts:
            msg += " | " + "; ".join(parts)
        if total_len > 0:
            msg += f" | Length of those segments: {total_len:.0f} m ({total_len / 1000.0:.2f} km)"
        self.iface.messageBar().pushInfo("Branch info", msg)

    def keyPressEvent(self, e):
        # ESC = exit
        try:
            if e.key() == Qt.Key.Key_Escape:
                self.iface.mapCanvas().unsetMapTool(self)
        except Exception as e:
            logger.debug(f"Error in BranchInfoTool.keyPressEvent: {e}")


__all__ = ['BranchInfoTool']
