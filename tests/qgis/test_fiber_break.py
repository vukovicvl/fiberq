"""
QGIS integration tests for FiberBreakTool.
These tests require QGIS and pytest-qgis.

Run with: pytest tests/qgis/ --qgis_disable_gui
"""
import pytest

pytest.importorskip("qgis.core")

from qgis.core import QgsVectorLayer, QgsWkbTypes, QgsProject


class TestFiberBreakTool:
    """Tests for FiberBreakTool functionality."""

    def test_tool_instantiates(self, qgis_iface):
        """FiberBreakTool can be instantiated."""
        from fiberq.addons.fiber_break import FiberBreakTool

        tool = FiberBreakTool(qgis_iface)
        assert tool is not None

    def test_tool_has_canvas(self, qgis_iface):
        """Tool has reference to map canvas."""
        from fiberq.addons.fiber_break import FiberBreakTool

        tool = FiberBreakTool(qgis_iface)
        assert tool.canvas is not None


class TestFiberBreakLayerCreation:
    """Tests for Fiber_break layer creation."""

    def test_ensure_break_layer_creates_layer(self, qgis_iface, qgis_new_project):
        """_ensure_break_layer creates a valid layer."""
        from fiberq.addons.fiber_break import FiberBreakTool

        tool = FiberBreakTool(qgis_iface)
        layer = tool._ensure_break_layer()

        assert layer is not None
        assert isinstance(layer, QgsVectorLayer)
        assert layer.isValid()

    def test_layer_is_point_geometry(self, qgis_iface, qgis_new_project):
        """Created layer has Point geometry."""
        from fiberq.addons.fiber_break import FiberBreakTool

        tool = FiberBreakTool(qgis_iface)
        layer = tool._ensure_break_layer()

        assert layer.geometryType() == QgsWkbTypes.PointGeometry

    def test_layer_has_required_fields(self, qgis_iface, qgis_new_project):
        """Layer has all required attribute fields."""
        from fiberq.addons.fiber_break import FiberBreakTool

        tool = FiberBreakTool(qgis_iface)
        layer = tool._ensure_break_layer()

        field_names = [f.name() for f in layer.fields()]
        required_fields = [
            "naziv",
            "kabl_layer_id",
            "kabl_fid",
            "distance_m",
            "segments_hit",
            "vreme",
        ]

        for field in required_fields:
            assert field in field_names, f"Missing field: {field}"

    def test_layer_name_is_fiber_break(self, qgis_iface, qgis_new_project):
        """Layer name is 'Fiber_break'."""
        from fiberq.addons.fiber_break import FiberBreakTool

        tool = FiberBreakTool(qgis_iface)
        layer = tool._ensure_break_layer()

        assert layer.name() == "Fiber_break"

    def test_layer_added_to_project(self, qgis_iface, qgis_new_project):
        """Layer is added to the current project."""
        from fiberq.addons.fiber_break import FiberBreakTool

        tool = FiberBreakTool(qgis_iface)
        layer = tool._ensure_break_layer()

        project_layers = QgsProject.instance().mapLayers()
        assert layer.id() in project_layers

    def test_existing_layer_is_reused(self, qgis_iface, qgis_new_project):
        """Calling _ensure_break_layer twice returns same layer."""
        from fiberq.addons.fiber_break import FiberBreakTool

        tool = FiberBreakTool(qgis_iface)
        layer1 = tool._ensure_break_layer()
        layer2 = tool._ensure_break_layer()

        assert layer1.id() == layer2.id()


class TestFiberBreakGeometryHelpers:
    """Tests for geometry helper methods."""

    def test_flatten_polyline_simple(self, qgis_iface):
        """_flatten_polyline works with simple linestring."""
        from fiberq.addons.fiber_break import FiberBreakTool
        from qgis.core import QgsGeometry, QgsPointXY

        tool = FiberBreakTool(qgis_iface)

        # Create a simple line geometry
        points = [QgsPointXY(0, 0), QgsPointXY(100, 0), QgsPointXY(100, 100)]
        geom = QgsGeometry.fromPolylineXY(points)

        result = tool._flatten_polyline(geom)

        assert len(result) == 3
        assert result[0].x() == 0
        assert result[0].y() == 0
        assert result[2].x() == 100
        assert result[2].y() == 100

    def test_flatten_polyline_empty(self, qgis_iface):
        """_flatten_polyline handles empty geometry."""
        from fiberq.addons.fiber_break import FiberBreakTool
        from qgis.core import QgsGeometry

        tool = FiberBreakTool(qgis_iface)
        geom = QgsGeometry()

        result = tool._flatten_polyline(geom)

        assert result == []

    def test_iter_line_layers_empty_project(self, qgis_iface, qgis_new_project):
        """_iter_line_layers returns empty for new project."""
        from fiberq.addons.fiber_break import FiberBreakTool

        tool = FiberBreakTool(qgis_iface)
        layers = list(tool._iter_line_layers())

        assert len(layers) == 0

    def test_iter_line_layers_finds_lines(self, qgis_iface, qgis_new_project):
        """_iter_line_layers finds line layers in project."""
        from fiberq.addons.fiber_break import FiberBreakTool

        # Add a line layer to project
        line_layer = QgsVectorLayer("LineString?crs=EPSG:4326", "test_cables", "memory")
        QgsProject.instance().addMapLayer(line_layer)

        tool = FiberBreakTool(qgis_iface)
        layers = list(tool._iter_line_layers())

        assert len(layers) == 1
        assert layers[0].name() == "test_cables"
