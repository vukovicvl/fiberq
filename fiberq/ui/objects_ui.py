"""
FiberQ v2 - Objects UI

Toolbar group for drawing building objects on the map.
"""

from .base import (
    Qt, QAction, QMenu, QToolButton, QMessageBox, QDialog,
    load_icon
)
from qgis.core import QgsWkbTypes

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class ObjectsUI:
    """
    Toolbar group for object drawing operations.

    Creates a drop-down menu with actions for:
    - Object in 3 points
    - Object in N points
    - Object in N points (90°)
    - Digitized object (from selection)
    """

    def __init__(self, core):
        """
        Initialize the objects UI.

        Args:
            core: Plugin core instance with iface and toolbar
        """
        self.core = core
        self.menu = QMenu(core.iface.mainWindow())
        self.menu.setToolTipsVisible(True)

        # Object in 3 points
        act_3pt = QAction(load_icon('ic_object_3p.svg'), 'Object in 3 points', core.iface.mainWindow())

        def _activate_3pt():
            # Import here to avoid circular imports
            from ..tools import DrawObject3ptTool
            core._obj3 = DrawObject3ptTool(core.iface, core)
            core.iface.mapCanvas().setMapTool(core._obj3)
        act_3pt.triggered.connect(_activate_3pt)
        self.menu.addAction(act_3pt)
        core.actions.append(act_3pt)

        # Object in N points
        act_n = QAction(load_icon('ic_object_n.svg'), 'Object in N points', core.iface.mainWindow())

        def _activate_n():
            from ..tools import DrawObjectNTool
            core._objn = DrawObjectNTool(core.iface, core)
            core.iface.mapCanvas().setMapTool(core._objn)
        act_n.triggered.connect(_activate_n)
        self.menu.addAction(act_n)
        core.actions.append(act_n)

        # Object in N points (90°)
        act_orth = QAction(load_icon('ic_object_ortho.svg'), 'Object in N points (90°)', core.iface.mainWindow())

        def _activate_ortho():
            from ..tools import DrawObjectOrthoTool
            core._objo = DrawObjectOrthoTool(core.iface, core)
            core.iface.mapCanvas().setMapTool(core._objo)
        act_orth.triggered.connect(_activate_ortho)
        self.menu.addAction(act_orth)
        core.actions.append(act_orth)

        # Digitized object (from selection)
        act_dig = QAction(load_icon('ic_object_dig.svg'), 'Digitized object (from selection)', core.iface.mainWindow())

        def _activate_digitize():
            from ..tools import ObjectPropertiesDialog
            from ..core.layer_manager import _ensure_objects_layer, _stylize_objects_layer
            from qgis.core import QgsFeature

            lyr = core.iface.activeLayer()
            if lyr is None:
                QMessageBox.information(
                    core.iface.mainWindow(),
                    "Object",
                    "Activate a polygon layer and select geometry."
                )
                return

            sel = getattr(lyr, 'selectedFeatures', lambda: [])()
            if not sel:
                QMessageBox.information(
                    core.iface.mainWindow(),
                    "Objects",
                    "Select one polygon."
                )
                return

            g = sel[0].geometry()
            if not g or g.type() != QgsWkbTypes.PolygonGeometry:
                QMessageBox.information(
                    core.iface.mainWindow(),
                    "Objects",
                    "A polygon is required."
                )
                return

            dlg = ObjectPropertiesDialog(core.iface.mainWindow())
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            vals = dlg.values()
            obj = _ensure_objects_layer(core)
            if not obj:
                return

            obj.startEditing()
            f = QgsFeature(obj.fields())
            f.setGeometry(g)
            for k, v in vals.items():
                try:
                    idx = obj.fields().indexFromName(k)
                    f.setAttribute(idx, v)
                except Exception as e:
                    logger.debug(f"Error in ObjectsUI._activate_digitize: {e}")
            # Phase 0.1: Set UUID for FiberQ Designer
            try:
                from ..utils.uuid_utils import set_feature_uuid
                set_feature_uuid(f)
            except Exception as e:
                logger.debug(f"Could not set feature uuid: {e}")
            obj.addFeature(f)
            obj.commitChanges()
            _stylize_objects_layer(obj)
            core.iface.layerTreeView().setCurrentLayer(obj)

        act_dig.triggered.connect(_activate_digitize)
        self.menu.addAction(act_dig)
        core.actions.append(act_dig)

        # Toolbar drop-down button
        btn = QToolButton(core.iface.mainWindow())
        try:
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        except Exception as e:
            logger.debug(f"Error in ObjectsUI._activate_digitize: {e}")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setMenu(self.menu)
        btn.setIcon(load_icon('ic_drawing_object.svg'))
        btn.setToolTip('Drawing object')
        btn.setStatusTip('Drawing object')

        try:
            core.toolbar.addWidget(btn)
        except Exception:
            # Fallback
            act_root = QAction(load_icon('ic_drawing_object.svg'), 'Drawing object', core.iface.mainWindow())
            act_root.setMenu(self.menu)
            core.iface.addToolBarIcon(act_root)
            core.actions.append(act_root)


__all__ = ['ObjectsUI']
