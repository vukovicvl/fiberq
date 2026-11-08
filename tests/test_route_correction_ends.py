"""Route correction knows what a route may end on, and Correct moves an end only a little.

v1.6.0 QA finding Q21 (unclaimed). Route correction counted only Poles and
Manholes as a place a route may end, so the ends FiberQ itself makes elsewhere
were errors: a drop ending at an OTB, a branch drawn from another route's
vertex, both halves of a split route. Correct then dragged the end onto the
nearest pole or manhole at any distance and saved it. On the maintainer's
project the one finding was a route ending on another route's vertex, beside
the lower end of a transition pipe, and Correct moved it 20.66 m onto a pole,
off both.

An end is connected now when it is within 1 cm of a point on one of the fifteen
layers FiberQ ends routes and cables on, or of another route's vertex; one that
touches another route between two vertices is reported with no Correct; and
Correct moves a loose end only onto the nearest of those points within 5 m on
the ground, never away from a cable or a duct, and says what it did.

Every case here fails on the parent of this change for the reason its name
gives, except the dialog's two first-sight cases, which fail there on the text
alone: the parent's one-line finding showed whole. They fail on these longer
texts when the dialog does not wrap them, and the loose end's also when the
dialog leaves no room for a scrollbar. The 4.9 m case is the control that the
limit still lets a short move through, and fails there only on the box, which
did not say where the end went or how far.
"""
import pytest
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QPoint, QRect, QTimer, QVariant
from qgis.PyQt.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QScrollArea

from fiberq.utils.geometry import line_vertices


class FakeBar:
    def __init__(self):
        self.warnings = []

    def pushWarning(self, title, text):
        self.warnings.append(text)

    def pushInfo(self, title, text):
        pass


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()
        self.canvas = None

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None

    def mapCanvas(self):
        if self.canvas is None:
            from qgis.gui import QgsMapCanvas
            self.canvas = QgsMapCanvas()
            self.canvas.resize(400, 300)
            self.canvas.setExtent(QgsRectangle(-10, -10, 10, 10))
        return self.canvas


@pytest.fixture(autouse=True)
def said(monkeypatch):
    """What Route correction said in its message boxes."""
    said = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: said.append(a[-1])))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: said.append(a[-1])))
    return said


@pytest.fixture
def shown(monkeypatch):
    """The findings Route correction would have put in its dialog."""
    captured = []

    class FakeDialog:
        def __init__(self, errors, parent=None, **kwargs):
            captured.append(list(errors))

        def exec(self):
            return 1

    import fiberq.main_plugin as mp
    monkeypatch.setattr(mp, "CorrectionDialog", FakeDialog)
    return captured


@pytest.fixture
def modals():
    """Any modal that opens anyway, closed and recorded, so a regression fails instead of hanging."""
    seen = []

    def close():
        widget = QApplication.activeModalWidget()
        if widget is not None:
            seen.append(widget.windowTitle())
            widget.reject()

    timer = QTimer()
    timer.timeout.connect(close)
    timer.start(50)
    yield seen
    timer.stop()


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.removeAllMapLayers()
    yield prj
    prj.removeAllMapLayers()


@pytest.fixture
def plugin(project):
    from fiberq.main_plugin import FiberQPlugin

    obj = FiberQPlugin.__new__(FiberQPlugin)
    obj.iface = FakeIface()
    obj.popravljive_greske = []
    return obj


def _lines(project, name, coords_list, crs="EPSG:3857", names=None):
    layer = QgsVectorLayer(f"LineString?crs={crs}", name, "memory")
    layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    layer.updateFields()
    for i, coords in enumerate(coords_list):
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*xy) for xy in coords]))
        if names:
            feat.setAttribute("naziv", names[i])
        layer.startEditing()
        assert layer.addFeature(feat)
        assert layer.commitChanges(), layer.commitErrors()
    project.addMapLayer(layer)
    return layer


def _points(project, name, coords, crs="EPSG:3857"):
    """A point layer; a coordinate of ``None`` makes a feature with no geometry."""
    layer = QgsVectorLayer(f"Point?crs={crs}", name, "memory")
    layer.dataProvider().addAttributes([QgsField("naziv", QVariant.String)])
    layer.updateFields()
    for xy in coords:
        feat = QgsFeature(layer.fields())
        if xy is not None:
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*xy)))
        layer.startEditing()
        layer.addFeature(feat)
        layer.commitChanges()
    project.addMapLayer(layer)
    return layer


def _ends(layer):
    vertices = line_vertices(next(layer.getFeatures()).geometry())
    return vertices[0], vertices[-1]


# ---------------------------------------------------------------------------
# What a route may end on: what FiberQ itself ends routes and cables on
# ---------------------------------------------------------------------------

NODE_LAYER_NAMES = [
    "Joint Closures", "Nastavci", "ODF", "TB", "Patch panel", "Patch Panel", "OTB", "Indoor OTB",
    "Outdoor OTB", "Pole OTB", "TO", "Indoor TO", "Outdoor TO", "Pole TO", "Joint Closure TO",
]


@pytest.mark.parametrize("name", NODE_LAYER_NAMES)
def test_an_end_on_an_element_or_closure_is_not_an_error(plugin, project, shown, said, name):
    """Create a route manually snaps to these, and Lay cable ends cables on them."""
    _lines(project, "Route", [[(0, 0), (50, 0)]])
    _points(project, "Poles", [(0, 0)])
    _points(project, name, [(50, 0)])

    plugin.check_consistency()

    assert shown == [], [e["msg"] for e in shown[0]]
    assert any("No errors found" in str(m) for m in said)


def test_an_end_on_another_route_s_vertex_is_not_an_error(plugin, project, shown):
    """A branch drawn from a vertex: Lay cable routes through that junction."""
    _lines(project, "Route", [[(0, 0), (50, 0), (100, 0)], [(50, 80), (50, 0)]])
    _points(project, "Poles", [(0, 0), (100, 0), (50, 80)])

    plugin.check_consistency()

    assert shown == [], [e["msg"] for e in shown[0]]


def test_the_two_halves_of_a_split_route_are_not_errors(plugin, project, shown):
    """Add breakpoint, Split route and Cut infrastructure leave this behind."""
    _lines(project, "Route", [[(0, 0), (40, 0)], [(40, 0), (100, 0)]])
    _points(project, "Poles", [(0, 0), (100, 0)])

    plugin.check_consistency()

    assert shown == [], [e["msg"] for e in shown[0]]


def test_an_end_touching_another_route_between_its_vertices_has_no_correct(plugin, project, shown):
    """Reported, because Lay cable cannot cross it -- but Correct would disconnect it.

    The manhole 2 m away is what the parent's Correct would have dragged the end onto.
    """
    _lines(project, "Route", [[(0, 0), (100, 0)], [(50, 80), (50, 0)]], names=["Main", "Branch"])
    _points(project, "Poles", [(0, 0), (100, 0), (50, 80)])
    _points(project, "Manholes", [(52, 0)])

    plugin.check_consistency()

    assert len(shown) == 1 and len(shown[0]) == 1, shown
    finding = shown[0][0]
    assert "popravka" not in finding, "no Correct for an end that is on another route"
    assert "'Main'" in finding["msg"] and "touches" in finding["msg"], finding["msg"]


def test_the_bar_counts_closures_and_elements_with_no_position(plugin, project, shown):
    _lines(project, "Route", [[(0, 0), (100, 0)]])
    _points(project, "Poles", [(0, 0), (100, 0)])
    _points(project, "Joint Closures", [None])

    plugin.check_consistency()

    assert len(plugin.iface.bar.warnings) == 1, plugin.iface.bar.warnings
    assert plugin.iface.bar.warnings[0].endswith(": 1"), plugin.iface.bar.warnings
    assert "manhole(s)" not in plugin.iface.bar.warnings[0]


def test_every_poles_layer_is_read_not_only_the_first(plugin, project, shown):
    """'Poles' and a pre-1.0 'Stubovi' in one project: the check read only the first."""
    _lines(project, "Route", [[(0, 0), (50, 0)]])
    _points(project, "Poles", [(0, 0)])
    _points(project, "Stubovi", [(50, 0)])

    plugin.check_consistency()

    assert shown == [], [e["msg"] for e in shown[0]]


def test_a_polygon_layer_called_manholes_does_not_stop_the_check(plugin, project, shown):
    """v1.5.0 and the parent: TypeError, Polygon geometry cannot be converted to a point."""
    _lines(project, "Route", [[(0, 0), (50, 0)]])
    _points(project, "Poles", [(0, 0), (50, 0)])
    polygons = QgsVectorLayer("Polygon?crs=EPSG:3857", "Manholes", "memory")
    feat = QgsFeature(polygons.fields())
    feat.setGeometry(QgsGeometry.fromWkt("Polygon ((0 0, 1 0, 1 1, 0 1, 0 0))"))
    polygons.dataProvider().addFeatures([feat])
    project.addMapLayer(polygons)

    plugin.check_consistency()

    assert shown == [], [e["msg"] for e in shown[0]]


# ---------------------------------------------------------------------------
# What Correct does
# ---------------------------------------------------------------------------

def test_correct_attaches_an_end_to_the_element_beside_it(plugin, project, said):
    """Not to the pole 7 m away, past the OTB the end was meant for."""
    route = _lines(project, "Route", [[(0, 0), (48, 0)]])
    _points(project, "Poles", [(0, 0), (55, 0)])
    _points(project, "OTB", [(50, 0)])

    plugin.fix_route_to_pole(next(route.getFeatures()).id(), must_start=False)

    assert _ends(route)[1] == QgsPointXY(50, 0)
    assert any("OTB" in str(m) and "2.0 m" in str(m) for m in said), said


@pytest.mark.parametrize("away, moves", [(4.9, True), (5.1, False), (30.0, False), (2000.0, False)])
def test_correct_moves_an_end_at_most_5_m(plugin, project, said, away, moves):
    """Measured on the ground: on the equator a Web Mercator unit is a metre.

    The route is 10 km long, so the pole its start is on is never the nearest.
    """
    route = _lines(project, "Route", [[(0, 0), (10000, 0)]])
    _points(project, "Poles", [(0, 0), (10000 + away, 0)])

    plugin.fix_route_to_pole(next(route.getFeatures()).id(), must_start=False)

    end = _ends(route)[1]
    if moves:
        assert end == QgsPointXY(10000 + away, 0)
        assert any(f"{away:.1f} m away" in str(m) for m in said), said
    else:
        assert end == QgsPointXY(10000, 0), f"moved {away} m: {end.toString()}"
        assert any("within 5 m" in w for w in plugin.iface.bar.warnings), plugin.iface.bar.warnings


def test_the_limit_is_in_metres_in_a_geographic_crs(plugin, project, said):
    """0.02 degrees east at 45 N is about 1.6 km. A limit in map units would be 5 degrees."""
    route = _lines(project, "Route", [[(20.0, 45.0), (20.05, 45.0)]], crs="EPSG:4326")
    _points(project, "Poles", [(20.0, 45.0), (20.07, 45.0)], crs="EPSG:4326")

    plugin.fix_route_to_pole(next(route.getFeatures()).id(), must_start=False)

    assert _ends(route)[1] == QgsPointXY(20.05, 45.0), _ends(route)[1].toString()
    assert any("within 5 m" in w for w in plugin.iface.bar.warnings), plugin.iface.bar.warnings


@pytest.mark.parametrize("name", ["Aerial cables", "Underground cables", "PE pipes", "Transition pipes",
                                  "Kablovi_podzemni"])
def test_correct_leaves_an_end_where_a_cable_or_duct_ends(plugin, project, said, name):
    """A cable keeps no link to its route: moving the route alone leaves it behind."""
    route = _lines(project, "Route", [[(0, 0), (49, 0)]])
    _points(project, "Poles", [(0, 0), (50, 0)])
    _lines(project, name, [[(0, 0), (49, 0)]], names=["Optical 12F"])

    plugin.fix_route_to_pole(next(route.getFeatures()).id(), must_start=False)

    assert _ends(route)[1] == QgsPointXY(49, 0)
    assert any(name in w and "Optical 12F" in w for w in plugin.iface.bar.warnings), plugin.iface.bar.warnings


def test_correct_never_pulls_an_end_off_another_route(plugin, project, said):
    """Called directly, as the dialog would after the data changed under it."""
    route = _lines(project, "Route", [[(0, 0), (50, 0), (100, 0)], [(50, 80), (50, 0)]])
    _points(project, "Poles", [(0, 0), (100, 0), (50, 80), (53, 0)])
    branch = [f.id() for f in route.getFeatures()][1]

    plugin.fix_route_to_pole(branch, must_start=False)

    moved = line_vertices(route.getFeature(branch).geometry())
    assert moved[-1] == QgsPointXY(50, 0), moved[-1].toString()
    assert any("already meets" in w for w in plugin.iface.bar.warnings), plugin.iface.bar.warnings


# ---------------------------------------------------------------------------
# The dialog
# ---------------------------------------------------------------------------

def _drive(monkeypatch, label):
    """Make the real dialog press its first ``label`` button instead of waiting for a user."""
    import fiberq.main_plugin as mp
    pressed = []

    def exec_(dialog):
        buttons = [b for b in dialog.findChildren(QPushButton) if b.text() == label]
        buttons[0].click()
        pressed.append(buttons[0])
        return 1

    monkeypatch.setattr(mp.CorrectionDialog, "exec", exec_)
    return pressed


def test_select_on_map_selects_the_route_and_centres_on_its_end(plugin, project, monkeypatch, modals):
    route = _lines(project, "Route", [[(0, 0), (1000, 0)], [(0, 500), (1000, 500)]])
    _points(project, "Poles", [(0, 0), (1000, 0), (0, 500)])
    loose = [f.id() for f in route.getFeatures()][1]
    _drive(monkeypatch, "Select on map")

    plugin.check_consistency()

    assert route.selectedFeatureIds() == [loose]
    centre = plugin.iface.mapCanvas().center()
    assert (round(centre.x(), 6), round(centre.y(), 6)) == (1000.0, 500.0), centre.toString()
    assert modals == []


def test_a_correct_that_moved_the_end_greys_out_its_button(plugin, project, monkeypatch, said, modals):
    route = _lines(project, "Route", [[(0, 0), (99, 0)]])
    _points(project, "Poles", [(0, 0), (100, 0)])
    pressed = _drive(monkeypatch, "Correct")

    plugin.check_consistency()

    assert _ends(route)[1] == QgsPointXY(100, 0)
    assert pressed and not pressed[0].isEnabled()
    assert modals == []


def _first_sight(monkeypatch):
    """Open the real dialog at the size it opens with, and note what of it is not in view."""
    import fiberq.main_plugin as mp
    seen = []

    def exec_(dialog):
        dialog.show()
        QApplication.processEvents()
        area = dialog.findChild(QScrollArea)
        view = area.viewport()
        labels = area.widget().findChildren(QLabel)
        widgets = labels + area.widget().findChildren(QPushButton)
        seen.append({
            "texts": [label.text() for label in labels],
            "out of view": [widget.text() for widget in widgets
                            if not view.rect().contains(QRect(widget.mapTo(view, QPoint(0, 0)), widget.size()))],
            "cut short": [label.text() for label in labels if label.height() < label.heightForWidth(label.width())],
            "scrollbars": [name for name, bar in (("horizontal", area.horizontalScrollBar()),
                                                  ("vertical", area.verticalScrollBar())) if bar.isVisible()],
        })
        dialog.close()
        return 1

    monkeypatch.setattr(mp.CorrectionDialog, "exec", exec_)
    return seen


@pytest.mark.parametrize("routes, names, poles, text", [
    ([[(0, 0), (99, 0)]], ["Route 9"], [(0, 0)], "is not connected to a pole"),
    ([[(0, 0), (100, 0)], [(50, 80), (50, 0)]], ["Merged route", "Route 10"], [(0, 0), (100, 0), (50, 80)],
     "Add a vertex to route 'Merged route'"),
], ids=["loose end", "end touching a route"])
def test_the_dialog_opens_with_the_whole_finding_and_its_buttons_in_view(
        plugin, project, monkeypatch, modals, routes, names, poles, text):
    """These findings run to 108-190 characters; v1.5.0's "NOT on a pole." line took 38.

    Unwrapped, the line was wider than the 36 font heights QScrollArea asks
    for, so the dialog opened with it cut off, both scrollbars showing and
    Select on map half hidden (seen in the QGIS 3.40.15 and 4.2.3 apps).
    Wrapped, but opened at exactly the width the label asks for, it kept a
    vertical scrollbar, and Select on map was out of view.
    """
    _lines(project, "Route", routes, names=names)
    _points(project, "Poles", poles)
    seen = _first_sight(monkeypatch)

    plugin.check_consistency()

    assert len(seen) == 1 and len(seen[0]["texts"]) == 1, seen
    assert text in seen[0]["texts"][0], seen
    assert seen[0]["out of view"] == [], seen
    assert seen[0]["cut short"] == [], seen
    assert seen[0]["scrollbars"] == [], seen
    assert modals == []
