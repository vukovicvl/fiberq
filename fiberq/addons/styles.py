
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QComboBox, QLabel, QPushButton, QDialogButtonBox
from qgis.core import QgsProject, QgsVectorLayer

class ApplyStyleDialog(QDialog):
    def __init__(self, iface, plugin_root):
        super().__init__(iface.mainWindow())
        self.setWindowTitle("Apply style (.qml)")
        self.iface = iface
        self.plugin_root = plugin_root
        lay = QVBoxLayout(self)
        self.cmb_layer = QComboBox()
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer):
                self.cmb_layer.addItem(lyr.name(), lyr.id())
        lay.addWidget(QLabel("Layer:"))
        lay.addWidget(self.cmb_layer)
        self.cmb_style = QComboBox()
        self.cmb_style.addItem("Branch/offset (branch_index)", "styles/branch_offset.qml")
        self.cmb_style.addItem("Reserves", "styles/reserves.qml")
        self.cmb_style.addItem("Cable types", "styles/cables_by_type.qml")
        lay.addWidget(QLabel("Style:"))
        lay.addWidget(self.cmb_style)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.apply); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def apply(self):
        lyr_id = self.cmb_layer.currentData()
        qml_rel = self.cmb_style.currentData()
        lyr = QgsProject.instance().mapLayer(lyr_id)
        if lyr:
            import os
            qml_path = os.path.join(self.plugin_root, qml_rel).replace("\\","/")
            lyr.loadNamedStyle(qml_path)
            lyr.triggerRepaint()
        self.accept()
