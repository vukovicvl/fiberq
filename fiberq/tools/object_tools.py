"""
FiberQ v2 - Object Drawing Tools

Map tools for drawing building/object polygons.
Phase 2.1: Extracted from extracted_classes.py
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QSpinBox, QGroupBox, QDialogButtonBox, QMessageBox
)

from qgis.core import (
    QgsFeature, QgsGeometry, QgsPointXY, QgsWkbTypes
)
from qgis.gui import QgsMapTool, QgsRubberBand

# Import from legacy bridge for compatibility
from ..utils.legacy_bridge import (
    _ensure_objects_layer,
    _stylize_objects_layer,
    _apply_objects_field_aliases,
    _set_objects_layer_alias,
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class ObjectPropertiesDialog(QDialog):
    """Simple dialog for entering object attributes (kept minimal and clean)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Object data")
        lay = QVBoxLayout(self)
        gb = QGroupBox("Basic data")
        form = QFormLayout(gb)
        self.ed_tip = QLineEdit()
        self.sb_spr = QSpinBox()
        self.sb_spr.setRange(0, 50)
        self.sb_spr.setValue(1)
        self.sb_pod = QSpinBox()
        self.sb_pod.setRange(0, 10)
        self.sb_pod.setValue(0)
        self.ed_ulica = QLineEdit()
        self.ed_broj = QLineEdit()
        self.ed_naziv = QLineEdit()
        self.ed_napomena = QLineEdit()
        form.addRow("Type:", self.ed_tip)
        form.addRow("Number of floors:", self.sb_spr)
        form.addRow("Number of underground floors:", self.sb_pod)
        form.addRow("Street:", self.ed_ulica)
        form.addRow("Number:", self.ed_broj)
        form.addRow("Name/Description:", self.ed_naziv)
        form.addRow("Note:", self.ed_napomena)
        lay.addWidget(gb)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self):
        return {
            "tip": self.ed_tip.text().strip(),
            "spratova": int(self.sb_spr.value()),
            "podzemnih": int(self.sb_pod.value()),
            "ulica": self.ed_ulica.text().strip(),
            "broj": self.ed_broj.text().strip(),
            "naziv": self.ed_naziv.text().strip(),
            "napomena": self.ed_napomena.text().strip()
        }


class _BaseObjMapTool(QgsMapTool):
    """Base class with rubber band helpers."""

    def __init__(self, iface, core):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.core = core
        self.canvas = iface.mapCanvas()
        self.points = []
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        try:
            self.rb.setWidth(2)
            # semi-transparent fill
            s = self.rb.symbol()
            if s and s.symbolLayerCount() > 0:
                try:
                    s.symbolLayer(0).setStrokeColor(QColor(0, 0, 0, 180))
                    s.symbolLayer(0).setFillColor(QColor(10, 10, 10, 40))
                except Exception as e:
                    logger.debug(f"Error in _BaseObjMapTool.__init__: {e}")
        except Exception as e:
            logger.debug(f"Error in _BaseObjMapTool.__init__: {e}")

    def _update_rb(self, pts):
        try:
            self.rb.setToGeometry(QgsGeometry.fromPolygonXY([pts]), None)
        except Exception as e:
            logger.debug(f"Error in _BaseObjMapTool._update_rb: {e}")

    def _reset(self):
        """Clear current drawing (without exiting tool)."""
        self.points = []
        try:
            self._update_rb([])
        except Exception as e:
            try:
                self.rb.reset(QgsWkbTypes.PolygonGeometry)
            except Exception as e:
                logger.debug(f"Error in _BaseObjMapTool._reset: {e}")

    def _finish(self, geom):
        obj_layer = _ensure_objects_layer(self.core)
        if not obj_layer or geom is None:
            return

        # Open dialog for attribute input
        dlg = ObjectPropertiesDialog(self.iface.mainWindow())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        vals = dlg.values()

        try:
            was_editing = obj_layer.isEditable()
        except Exception as e:
            was_editing = False

        try:
            if not was_editing:
                obj_layer.startEditing()

            f = QgsFeature(obj_layer.fields())
            f.setGeometry(geom)

            # Write attributes by field name
            for k, v in (vals or {}).items():
                try:
                    idx = obj_layer.fields().indexFromName(k)
                    if idx != -1:
                        f.setAttribute(idx, v)
                except Exception as e:
                    logger.debug(f"Error in _BaseObjMapTool._finish: {e}")

            # Phase 0.1: Set UUID for FiberQ Designer
            try:
                from ..utils.uuid_utils import set_feature_uuid
                set_feature_uuid(f)
            except Exception:
                pass

            obj_layer.addFeature(f)

            if not was_editing:
                obj_layer.commitChanges()
            else:
                obj_layer.triggerRepaint()

            # Record for undo (v1.2 — Feature 2)
            try:
                if hasattr(self, 'core') and self.core and hasattr(self.core, 'undo_manager') and self.core.undo_manager:
                    self.core.undo_manager.record_add(obj_layer, f)
                elif hasattr(self, 'plugin') and self.plugin and hasattr(self.plugin, 'undo_manager') and self.plugin.undo_manager:
                    self.plugin.undo_manager.record_add(obj_layer, f)
            except Exception as e:
                logger.debug(f"Error recording undo for object: {e}")

            # Style + aliases (keep "DWG look" and ENG user-view)
            try:
                _stylize_objects_layer(obj_layer)
            except Exception as e:
                logger.debug(f"Error in _BaseObjMapTool._finish: {e}")
            try:
                _apply_objects_field_aliases(obj_layer)
                _set_objects_layer_alias(obj_layer)
            except Exception as e:
                logger.debug(f"Error in _BaseObjMapTool._finish: {e}")

            try:
                self.core.iface.layerTreeView().setCurrentLayer(obj_layer)
            except Exception as e:
                logger.debug(f"Error in _BaseObjMapTool._finish: {e}")

            try:
                self.iface.messageBar().pushSuccess("Objects", "Object added.")
            except Exception as e:
                logger.debug(f"Error in _BaseObjMapTool._finish: {e}")

            # Auto-exit tool after successful add
            try:
                self.core.iface.actionPan().trigger()  # return to Pan (easiest)
            except Exception as e:
                try:
                    self.core.iface.mapCanvas().unsetMapTool(self)
                except Exception as e:
                    logger.debug(f"Error in _BaseObjMapTool._finish: {e}")

        except Exception as e:
            try:
                if not was_editing:
                    obj_layer.rollBack()
            except Exception as e:
                logger.debug(f"Error in _BaseObjMapTool._finish: {e}")
            try:
                QMessageBox.warning(self.iface.mainWindow(), "Objects", f"Cannot add object:\n{e}")
            except Exception as e:
                logger.debug(f"Error in _BaseObjMapTool._finish: {e}")

    def keyPressEvent(self, event):
        """ESC – cancel current drawing, but keep tool active."""
        try:
            if event.key() == Qt.Key.Key_Escape:
                self._reset()
                return
        except Exception as e:
            logger.debug(f"Error in _BaseObjMapTool.keyPressEvent: {e}")
        try:
            super().keyPressEvent(event)
        except Exception as e:
            logger.debug(f"Error in _BaseObjMapTool.keyPressEvent: {e}")

    def deactivate(self):
        """When user changes tool, clear rubber band."""
        try:
            self._reset()
        except Exception as e:
            logger.debug(f"Error in _BaseObjMapTool.deactivate: {e}")
        try:
            super().deactivate()
        except Exception as e:
            logger.debug(f"Error in _BaseObjMapTool.deactivate: {e}")


class DrawObjectNTool(_BaseObjMapTool):
    """Click-to-add vertices; right click to finish."""

    def canvasPressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            p = self.toMapCoordinates(e.pos())
            self.points.append(QgsPointXY(p))
            self._update_rb(self.points)
        elif e.button() == Qt.MouseButton.RightButton:
            # If enough points – finish, in any case clear drawing
            if len(self.points) >= 3:
                self._finish(QgsGeometry.fromPolygonXY([self.points]))
            self._reset()

    def canvasMoveEvent(self, e):
        if not self.points:
            return
        p = self.toMapCoordinates(e.pos())
        tmp = self.points + [QgsPointXY(p)]
        self._update_rb(tmp)


class DrawObjectOrthoTool(_BaseObjMapTool):
    """Orthogonal segments (90°)."""

    def canvasPressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            mappt = self.toMapCoordinates(e.pos())
            if not self.points:
                self.points.append(QgsPointXY(mappt))
            else:
                last = self.points[-1]
                dx, dy = mappt.x() - last.x(), mappt.y() - last.y()
                # Snap to horizontal or vertical by dominant axis
                if abs(dx) >= abs(dy):
                    p = QgsPointXY(mappt.x(), last.y())
                else:
                    p = QgsPointXY(last.x(), mappt.y())
                self.points.append(p)
            self._update_rb(self.points)
        elif e.button() == Qt.MouseButton.RightButton:
            # If enough points – finish, in any case clear drawing
            if len(self.points) >= 3:
                self._finish(QgsGeometry.fromPolygonXY([self.points]))
            self._reset()

    def canvasMoveEvent(self, e):
        if not self.points:
            return
        last = self.points[-1]
        mappt = self.toMapCoordinates(e.pos())
        dx, dy = mappt.x() - last.x(), mappt.y() - last.y()
        if abs(dx) >= abs(dy):
            p = QgsPointXY(mappt.x(), last.y())
        else:
            p = QgsPointXY(last.x(), mappt.y())
        tmp = self.points + [p]
        self._update_rb(tmp)


class DrawObject3ptTool(_BaseObjMapTool):
    """Rectangle from 3 points: first edge (p1->p2), third defines width (perpendicular)."""

    def canvasPressEvent(self, e):
        # Right click – just cancel current drawing
        if e.button() == Qt.MouseButton.RightButton:
            self._reset()
            return

        if e.button() != Qt.MouseButton.LeftButton:
            return

        mappt = self.toMapCoordinates(e.pos())
        self.points.append(QgsPointXY(mappt))
        if len(self.points) == 3:
            p1, p2, p3 = self.points
            # Vector along edge
            vx, vy = (p2.x() - p1.x(), p2.y() - p1.y())
            # Perpendicular vector normalized
            L = (vx**2 + vy**2) ** 0.5
            if L == 0:
                self._reset()
                return
            nx, ny = -vy / L, vx / L
            # Width from signed distance of p3 to line p1-p2
            wx = p3.x() - p1.x()
            wy = p3.y() - p1.y()
            w = wx * nx + wy * ny
            # Corners
            c1 = p1
            c2 = p2
            c3 = QgsPointXY(p2.x() + nx * w, p2.y() + ny * w)
            c4 = QgsPointXY(p1.x() + nx * w, p1.y() + ny * w)
            geom = QgsGeometry.fromPolygonXY([[c1, c2, c3, c4]])
            self._finish(geom)
            self._reset()
        else:
            self._update_rb(self.points)

    def canvasMoveEvent(self, e):
        if len(self.points) < 2:
            return
        p1, p2 = self.points[0], self.points[1]
        mappt = self.toMapCoordinates(e.pos())
        p3 = QgsPointXY(mappt)
        # Preview rectangle
        vx, vy = (p2.x() - p1.x(), p2.y() - p1.y())
        L = (vx**2 + vy**2) ** 0.5
        if L == 0:
            return
        nx, ny = -vy / L, vx / L
        wx = p3.x() - p1.x()
        wy = p3.y() - p1.y()
        w = wx * nx + wy * ny
        c1 = p1
        c2 = p2
        c3 = QgsPointXY(p2.x() + nx * w, p2.y() + ny * w)
        c4 = QgsPointXY(p1.x() + nx * w, p1.y() + ny * w)
        tmp = [c1, c2, c3, c4]
        self._update_rb(tmp)


__all__ = [
    'ObjectPropertiesDialog',
    '_BaseObjMapTool',
    'DrawObjectNTool',
    'DrawObjectOrthoTool',
    'DrawObject3ptTool',
]
