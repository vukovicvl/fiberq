"""Per-move cost of three placement tools on memory layers, at 4 to 20,000 features.

The numbers behind docs/performance.md's section on placement snapping in scratch
projects: the joint-closure tool, the pole tool and an element tool (ODF), each with
QGIS snapping off so that FiberQ's own snap answers, the mouse resting near a vertex
and then over a span. Memory layers have no spatial index of their own, so this is
where FiberQ's snapping costs the most; the city benchmark (bench.py) measures the
same tools on GeoPackage layers.

Not collected by the test suite (``testpaths`` is ``tests``). Run it in a QGIS image,
from the root of the tree whose ``fiberq/`` it should measure, with pytest and
pytest-qgis on the path::

    python3 -m pytest -p no:cacheprovider -q -s tools/bench/test_snap_memory_scaling.py

It prints the QGIS version and one JSON line per size: the best of seven rounds of
200 moves, in microseconds per move.
"""
import json
import time

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY, QgsProject,
                       QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QPoint, Qt

X0, Y0 = 2343983.02, 5589536.48


def memory(uri, name, geoms):
    layer = QgsVectorLayer(f"{uri}?crs=EPSG:3857&field=naziv:string", name, "memory")
    feats = []
    for g in geoms:
        f = QgsFeature(layer.fields())
        f.setGeometry(g)
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    return layer


def best_us(fn, n=200, rounds=7):
    for _ in range(20):
        fn()
    best = None
    for _ in range(rounds):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        dt = (time.perf_counter() - t0) / n * 1e6
        best = dt if best is None else min(best, dt)
    return round(best, 1)


def test_tools(qgis_app, capsys):
    from fiberq.tools.element_tool import PlaceElementTool
    from fiberq.tools.extension_tool import ExtensionTool
    from fiberq.tools.point_tool import PointTool
    prj = QgsProject.instance()
    rows = []
    for n in (1, 100, 1000, 5000):
        prj.removeAllMapLayers()
        routes, poles, manholes = [], [], []
        side = max(1, int(n ** 0.5))
        for i in range(n):
            x, y = X0 + (i % side) * 150.0, Y0 + (i // side) * 150.0
            a, b, c = QgsPointXY(x, y), QgsPointXY(x + 60, y + 5), QgsPointXY(x + 120, y + 40)
            routes.append(QgsGeometry.fromPolylineXY([a, b, c]))
            poles += [QgsGeometry.fromPointXY(a), QgsGeometry.fromPointXY(c)]
            manholes.append(QgsGeometry.fromPointXY(b))
        memory("LineString", "Route", routes)
        pole_layer = memory("Point", "Poles", poles)
        memory("Point", "Manholes", manholes)
        canvas = QgsMapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        canvas.resize(800, 800)
        canvas.show()
        size = canvas.mapSettings().outputSize()
        mupp = 286 * 0.0254 / 96.0
        at = QgsPointXY(X0 + 60, Y0 + 5)
        hw, hh = size.width() * mupp / 2.0, size.height() * mupp / 2.0
        canvas.setExtent(QgsRectangle(at.x() - hw, at.y() - hh, at.x() + hw, at.y() + hh))
        config = prj.snappingConfig()
        config.setEnabled(False)
        prj.setSnappingConfig(config)
        canvas.snappingUtils().setConfig(config)
        device = canvas.getCoordinateTransform().transform(at)
        near_vertex = QgsMapMouseEvent(canvas, QEvent.Type.MouseMove, QPoint(int(device.x()) + 6, int(device.y()) - 6),
                                       Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        span = canvas.getCoordinateTransform().transform(QgsPointXY(X0 + 30, Y0 + 2.5))
        on_span = QgsMapMouseEvent(canvas, QEvent.Type.MouseMove, QPoint(int(span.x()), int(span.y()) - 4),
                                   Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        tools = {"closure": ExtensionTool(canvas), "pole": PointTool(canvas, pole_layer),
                 "odf": PlaceElementTool(canvas, "ODF")}
        row = {"features": 4 * n}
        for name, tool in tools.items():
            row[name + "@vertex"] = best_us(lambda: tool.canvasMoveEvent(near_vertex))
            row[name + "@span"] = best_us(lambda: tool.canvasMoveEvent(on_span))
        rows.append(row)
    with capsys.disabled():
        print("\nQGIS", Qgis.version())
        for r in rows:
            print(json.dumps(r))
    prj.removeAllMapLayers()
