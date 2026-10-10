"""Route correction measures each route end against the poles near it, not all of them.

WP4 task 4.1, item PF-3. v1.5.0 asked ``any()`` over every pole and manhole in
the project for every route end: 96,339 ``QgsPointXY.distance`` calls on the XS
city (500 ends), 5,110,731 on S, and ~15x the time for 4x the data (measured in
one process on QGIS 3.44.15). The check now asks a ``ScanOrderIndex`` for the
points inside a 1 cm box first, and runs the same test over those.

**Counted, not timed.** The indexed check finishes the XS city in ~0.03 s, below
the 0.05 s a timing test can trust on a shared CI runner (``test_scale.py``
skips there), so a timing ratio would skip on exactly the code it guards. The
number of distances measured is deterministic and is what the index changes.

On v1.5.0 the two count tests fail, and so does the golden at its closing
distance count -- its 86 findings and their digest pass there, which shows
they are v1.5.0's. The two boundary tests pin answers v1.5.0 gave, which the
index must keep. The XS findings are identical on v1.5.0 and on main before
this change (branches 8 and B changed nothing on that dataset: no multipart
route, no pole without a position, English names).
"""
import hashlib
import shutil

import pytest
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
from qgis.PyQt.QtWidgets import QMessageBox

#: The XS city's findings, one message per line in the order check_consistency
#: produced them, captured from the v1.5.0 tag. Identical on 3.22.16, 3.44.15
#: and 4.2.3.
XS_FINDINGS = 86
XS_FINDINGS_SHA256 = "100439f5f74fec294e7e3aadcf9dfe75b27b479699b3944b86b4465c4e69cd3b"


class _Bar:
    def __init__(self):
        self.warnings = []

    def pushWarning(self, title, text):
        self.warnings.append(text)


class _Iface:
    def __init__(self):
        self.bar = _Bar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None


@pytest.fixture
def project(qgis_app):
    prj = QgsProject.instance()
    prj.clear()
    yield prj
    prj.clear()


@pytest.fixture
def shown(monkeypatch):
    """The messages Route correction would have listed in its (modal) dialog."""
    captured = []

    class _Dialog:
        def __init__(self, errors, parent=None):
            captured.append([error["msg"] for error in errors])

        def exec(self):
            return 1

    import fiberq.main_plugin as mp
    monkeypatch.setattr(mp, "CorrectionDialog", _Dialog)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    return captured


@pytest.fixture
def plugin(project, shown):
    from fiberq.main_plugin import FiberQPlugin

    obj = FiberQPlugin.__new__(FiberQPlugin)
    obj.iface = _Iface()
    obj.popravljive_greske = []
    return obj


@pytest.fixture
def distance_calls(monkeypatch):
    """How often QgsPointXY.distance ran from Python, which is where the check calls it."""
    real = QgsPointXY.distance
    calls = [0]

    def counting(self, *args):
        calls[0] += 1
        return real(self, *args)

    monkeypatch.setattr(QgsPointXY, "distance", counting)
    return calls


def _layer(project, uri, name, geometries):
    """A memory layer filled in one provider call."""
    layer = QgsVectorLayer(uri, name, "memory")
    features = []
    for geom in geometries:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        features.append(feat)
    ok, _added = layer.dataProvider().addFeatures(features)
    assert ok
    project.addMapLayer(layer)
    return layer


def _drops(project, routes, poles):
    """``poles`` poles 10 m apart; ``routes`` drops, each from a pole to a house 3 m off it."""
    side = int(poles ** 0.5) + 1
    spots = [QgsPointXY(10.0 * (k % side), 10.0 * (k // side)) for k in range(poles)]
    _layer(project, "Point?crs=EPSG:3857", "Poles", [QgsGeometry.fromPointXY(p) for p in spots])
    step = max(1, poles // routes)
    _layer(project, "LineString?crs=EPSG:3857", "Route",
           [QgsGeometry.fromPolylineXY([spots[k * step],
                                        QgsPointXY(spots[k * step].x() + 3.0, spots[k * step].y())])
            for k in range(routes)])


def _kinds(messages):
    return [message.split(" (")[0] for message in messages]


def test_a_route_end_is_measured_only_against_the_poles_near_it(plugin, project, shown,
                                                                distance_calls):
    """2,000 poles and 50 drops. v1.5.0: 149,050 distances. Now one per end on a pole."""
    _drops(project, routes=50, poles=2000)

    plugin.check_consistency()

    assert _kinds(shown[0]) == ["End of route"] * 50
    assert distance_calls[0] <= 100, (
        f"{distance_calls[0]} distance measurements for 100 route ends: the check "
        f"is measuring every pole again")


def test_the_work_grows_with_the_project_not_with_its_square(plugin, project, shown,
                                                             distance_calls):
    """Plan 1.6's ratio test, counted: 4x the data must not cost ~16x the work.

    v1.5.0: 23,840 distances at 400 poles and 40 routes, 383,360 at 1,600 and
    160 -- x16.1. Indexed: 40 and 160, x4.0.
    """
    _drops(project, routes=40, poles=400)
    plugin.check_consistency()
    small = distance_calls[0]

    project.clear()
    distance_calls[0] = 0
    _drops(project, routes=160, poles=1600)
    plugin.check_consistency()
    large = distance_calls[0]

    assert small > 0
    assert large <= 8 * small, (
        f"{small} distances at 400 poles, {large} at 1,600 (x{large / small:.1f}); "
        f"quadratic growth would be ~16x")


def test_an_end_exactly_on_the_box_edge_is_still_on_its_pole(plugin, project, shown):
    """(1, 2.01) sits on the edge of the 1 cm box around (1, 2) and is 0.00999... away.

    v1.5.0's ``distance < 1e-2`` called it attached. A box query that left out
    its own edge would not, and this is the case that tells them apart.
    """
    _layer(project, "Point?crs=EPSG:3857", "Poles",
           [QgsGeometry.fromPointXY(QgsPointXY(1.0, 2.01)),
            QgsGeometry.fromPointXY(QgsPointXY(50.0, 2.0))])
    _layer(project, "LineString?crs=EPSG:3857", "Route",
           [QgsGeometry.fromPolylineXY([QgsPointXY(1.0, 2.0), QgsPointXY(50.0, 2.0)])])

    plugin.check_consistency()

    assert shown == [], shown


def test_an_end_one_step_beyond_the_box_edge_is_not(plugin, project, shown):
    """The next double up, 2.0100000000000002, is 0.010000000000000231 away: not attached."""
    _layer(project, "Point?crs=EPSG:3857", "Poles",
           [QgsGeometry.fromPointXY(QgsPointXY(1.0, 2.0100000000000002)),
            QgsGeometry.fromPointXY(QgsPointXY(50.0, 2.0))])
    _layer(project, "LineString?crs=EPSG:3857", "Route",
           [QgsGeometry.fromPolylineXY([QgsPointXY(1.0, 2.0), QgsPointXY(50.0, 2.0)])])

    plugin.check_consistency()

    assert _kinds(shown[0]) == ["Start of route"]


def test_the_xs_city_gets_the_findings_v150_gave(city_xs_dataset, plugin, project, shown,
                                                 distance_calls, tmp_path):
    """v1.5.0's findings, message for message, and the count that shows the index did the work."""
    for key in ("gpkg", "qgz"):
        shutil.copy(city_xs_dataset[key], tmp_path)
    assert project.read(str(tmp_path / "city_XS.qgz"))

    plugin.check_consistency()

    messages = shown[0]
    assert len(messages) == XS_FINDINGS
    assert hashlib.sha256("\n".join(messages).encode("utf-8")).hexdigest() == XS_FINDINGS_SHA256
    # 500 route ends, 414 of them on a pole; v1.5.0 measured 96,339 distances here.
    assert distance_calls[0] <= 500, distance_calls[0]
