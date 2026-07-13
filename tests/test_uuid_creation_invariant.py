"""WP1b: FiberQ layer factories must add the fiberq_uuid identity column at
layer-creation time, not only via the on-load migrator.

Regression guard for the manual-test finding that Route / Service Area / Optical
slacks / pipe layers were created WITHOUT fiberq_uuid (so set_feature_uuid then
silently no-opped), while Poles/Manholes -- created through the field-complete
LayerManager path -- had it. Each test drives the real factory and asserts the
column exists on the returned layer.

The element-placement tool (Route/TO/OTB/ODF/... via PlaceElementTool) uses the
same ensure_uuid_field call but is driven by a canvas mouse event, so it is
covered by manual QGIS testing rather than here.
"""
from qgis.core import QgsProject, QgsVectorLayer

UUID = "fiberq_uuid"


def _has_uuid(layer):
    return isinstance(layer, QgsVectorLayer) and layer.fields().indexOf(UUID) >= 0


def _clear():
    QgsProject.instance().removeAllMapLayers()


def test_route_layer_created_with_uuid(qgis_app, qgis_iface):
    from fiberq.core.route_manager import RouteManager
    _clear()
    layer = RouteManager(qgis_iface)._ensure_route_layer()
    assert _has_uuid(layer), "Route layer created without fiberq_uuid"


def test_slack_layer_created_with_uuid(qgis_app, qgis_iface):
    from fiberq.core.slack_manager import SlackManager
    _clear()
    # layer_manager=None forces the inline fallback factory (the field-less path).
    layer = SlackManager(qgis_iface, layer_manager=None).ensure_slack_layer()
    assert _has_uuid(layer), "Optical slacks layer created without fiberq_uuid"


def test_pipe_layer_created_with_uuid(qgis_app, qgis_iface):
    from fiberq.core.pipe_manager import PipeManager
    _clear()
    layer = PipeManager(qgis_iface, layer_manager=None).ensure_pipe_layer("PE cevi")
    assert _has_uuid(layer), "Pipe layer created without fiberq_uuid"


def test_service_area_layer_created_with_uuid(qgis_app, qgis_iface):
    from fiberq.utils import legacy_bridge
    _clear()
    core = type("Core", (), {"iface": qgis_iface})()
    layer = legacy_bridge._ensure_region_layer(core)
    assert _has_uuid(layer), "Service Area layer created without fiberq_uuid"


def test_objects_layer_created_with_uuid(qgis_app, qgis_iface):
    from fiberq.utils import legacy_bridge
    _clear()
    core = type("Core", (), {"iface": qgis_iface})()
    layer = legacy_bridge._ensure_objects_layer(core)
    assert _has_uuid(layer), "Objects layer created without fiberq_uuid"
