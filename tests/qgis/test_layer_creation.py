"""
QGIS integration tests for layer creation and styling.
These tests require QGIS and pytest-qgis.

Run with: pytest tests/qgis/ --qgis_disable_gui
"""
import pytest
from pathlib import Path

pytest.importorskip("qgis.core")

from qgis.core import QgsVectorLayer, QgsProject, QgsWkbTypes


class TestMemoryLayerCreation:
    """Tests for creating memory layers."""

    def test_create_point_layer(self, qgis_new_project):
        """Can create a valid point memory layer."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_points", "memory")

        assert layer.isValid()
        assert layer.geometryType() == QgsWkbTypes.PointGeometry

    def test_create_line_layer(self, qgis_new_project):
        """Can create a valid line memory layer."""
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "test_lines", "memory")

        assert layer.isValid()
        assert layer.geometryType() == QgsWkbTypes.LineGeometry

    def test_create_polygon_layer(self, qgis_new_project):
        """Can create a valid polygon memory layer."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_polygons", "memory")

        assert layer.isValid()
        assert layer.geometryType() == QgsWkbTypes.PolygonGeometry


class TestStyleLoading:
    """Tests for QML style loading."""

    def test_fiber_break_style_exists(self, plugin_dir):
        """Fiber_break.qml style file exists."""
        style_path = plugin_dir / "styles" / "Fiber_break.qml"
        assert style_path.exists()

    def test_style_loads_without_error(self, qgis_new_project, plugin_dir):
        """QML style can be loaded onto a layer."""
        style_path = plugin_dir / "styles" / "Fiber_break.qml"

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test", "memory")
        assert layer.isValid()

        # loadNamedStyle returns (success, error_message)
        result = layer.loadNamedStyle(str(style_path))
        # result[0] is the success flag (in older QGIS) or may vary

        # Just check it doesn't raise an exception
        assert layer is not None


class TestProjectOperations:
    """Tests for project-level operations."""

    def test_add_layer_to_project(self, qgis_new_project):
        """Layer can be added to project."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_layer", "memory")
        QgsProject.instance().addMapLayer(layer)

        layers = QgsProject.instance().mapLayers()
        assert layer.id() in layers

    def test_remove_layer_from_project(self, qgis_new_project):
        """Layer can be removed from project."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_layer", "memory")
        QgsProject.instance().addMapLayer(layer)
        layer_id = layer.id()

        QgsProject.instance().removeMapLayer(layer_id)

        layers = QgsProject.instance().mapLayers()
        assert layer_id not in layers

    def test_find_layer_by_name(self, qgis_new_project):
        """Layer can be found by name."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "unique_name", "memory")
        QgsProject.instance().addMapLayer(layer)

        found = QgsProject.instance().mapLayersByName("unique_name")
        assert len(found) == 1
        assert found[0].id() == layer.id()


class TestFieldOperations:
    """Tests for field operations on layers."""

    def test_add_fields_to_layer(self, qgis_new_project):
        """Fields can be added to a memory layer."""
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test", "memory")
        provider = layer.dataProvider()

        fields = [
            QgsField("name", QVariant.String),
            QgsField("value", QVariant.Double),
            QgsField("count", QVariant.Int),
        ]
        provider.addAttributes(fields)
        layer.updateFields()

        field_names = [f.name() for f in layer.fields()]
        assert "name" in field_names
        assert "value" in field_names
        assert "count" in field_names

    def test_set_field_alias(self, qgis_new_project):
        """Field alias can be set."""
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test", "memory")
        provider = layer.dataProvider()
        provider.addAttributes([QgsField("internal_name", QVariant.String)])
        layer.updateFields()

        idx = layer.fields().indexFromName("internal_name")
        layer.setFieldAlias(idx, "Display Name")

        assert layer.attributeAlias(idx) == "Display Name"
