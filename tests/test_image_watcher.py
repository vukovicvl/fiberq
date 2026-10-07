"""Clicking an element with a picture opens it, on Qt6 as well as Qt5.

WP4 4.2 item R12. The canvas watcher read the click position with
``event.x()`` / ``event.y()``. Those accessors were removed from
``QMouseEvent`` in Qt6: measured ``AttributeError`` on 4.0.3, present on
3.44.15. The handler wrapped its whole body in
``except Exception: logger.debug(...)``, which at the default log level writes
nothing anywhere -- so on QGIS 4, clicking an element with a picture did
nothing at all, for every element, with no error and nothing in the log. The
feature looked like it had simply been dropped.

``event.pos()`` exists on both and answers integers on both, which is what
``QgsMapToolIdentify.identify`` wants. ``event.position()`` is the Qt6 spelling
but is absent on Qt5 and returns floats, so it is not the portable choice --
which is the whole reason this is worth a test rather than a one-line edit.

The swallow is replaced by ``report_error``: a swallow at exactly this spot is
what hid the defect for a release, so the one place that must never be silent
is the handler guarding it.
"""
import pytest
from qgis.core import QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QEvent, QPointF, Qt
from qgis.PyQt.QtGui import QMouseEvent

from fiberq.core import feature_links as fl
from fiberq.utils.image_watcher import CanvasImageClickWatcher


class FakeBar:
    def __init__(self):
        self.warnings = []

    def pushWarning(self, title, text):
        self.warnings.append(text)


class FakeCanvas:
    def mapTool(self):
        return None


class FakeIface:
    def __init__(self):
        self.bar = FakeBar()
        self.canvas = FakeCanvas()

    def messageBar(self):
        return self.bar

    def mapCanvas(self):
        return self.canvas

    def mainWindow(self):
        return None


class FakeCore:
    def __init__(self):
        self.iface = FakeIface()


def _release_at(x, y):
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


@pytest.fixture
def watcher(qgis_app):
    core = FakeCore()
    obj = CanvasImageClickWatcher.__new__(CanvasImageClickWatcher)
    obj.core = core
    return obj


# ---------------------------------------------------------------------------
# The accessor itself
# ---------------------------------------------------------------------------

def test_pos_is_the_accessor_that_exists_on_both_stacks(qgis_app):
    """One of ``x()`` and ``position()`` is missing, depending on the stack."""
    event = _release_at(12.0, 34.0)
    point = event.pos()
    assert (int(point.x()), int(point.y())) == (12, 34)
    # Exactly one of the two version-specific spellings is present.
    assert hasattr(event, "x") != hasattr(event, "position"), (
        "both or neither present; the portable form would need revisiting")


def test_the_watcher_reads_the_position_without_raising(watcher, monkeypatch):
    """On 4.0 this used to raise AttributeError and be swallowed at debug."""
    seen = []
    monkeypatch.setattr(watcher, "_show_picture_under",
                        lambda event: seen.append(event.pos()))
    assert watcher.eventFilter(None, _release_at(7.0, 8.0)) is False
    assert [(int(p.x()), int(p.y())) for p in seen] == [(7, 8)]


def test_the_identify_call_gets_integers(watcher, monkeypatch):
    """``identify`` takes pixel coordinates; Qt6's position() answers floats."""
    captured = {}

    class FakeIdentify:
        TopDownAll = object()
        VectorLayer = object()

        def __init__(self, canvas):
            pass

        def identify(self, x, y, mode, kind):
            captured["args"] = (x, y)
            return []

    import qgis.gui
    monkeypatch.setattr(qgis.gui, "QgsMapToolIdentify", FakeIdentify)
    watcher._show_picture_under(_release_at(21.0, 43.0))
    assert captured["args"] == (21, 43)
    assert all(isinstance(v, int) for v in captured["args"])


# ---------------------------------------------------------------------------
# No longer silent
# ---------------------------------------------------------------------------

def test_a_failure_is_reported_not_logged_at_debug(watcher, monkeypatch):
    def explode(event):
        raise AttributeError("'QMouseEvent' object has no attribute 'x'")

    monkeypatch.setattr(watcher, "_show_picture_under", explode)
    assert watcher.eventFilter(None, _release_at(1.0, 2.0)) is False
    assert watcher.core.iface.bar.warnings, "the failure has to reach the user"
    assert "AttributeError" in watcher.core.iface.bar.warnings[0]


def test_the_event_is_never_swallowed(watcher, monkeypatch):
    """Normal selection must still happen after the popup."""
    monkeypatch.setattr(watcher, "_show_picture_under", lambda event: None)
    assert watcher.eventFilter(None, _release_at(1.0, 2.0)) is False


def test_a_non_release_event_is_ignored_cheaply(watcher, monkeypatch):
    def fail(event):
        raise AssertionError("should not have looked at this event")

    monkeypatch.setattr(watcher, "_show_picture_under", fail)
    move = QMouseEvent(QEvent.Type.MouseMove, QPointF(1.0, 2.0),
                       Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)
    assert watcher.eventFilter(None, move) is False


def test_a_right_click_is_ignored(watcher, monkeypatch):
    def fail(event):
        raise AssertionError("should not have looked at this event")

    monkeypatch.setattr(watcher, "_show_picture_under", fail)
    right = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(1.0, 2.0),
                        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
                        Qt.KeyboardModifier.NoModifier)
    assert watcher.eventFilter(None, right) is False


# ---------------------------------------------------------------------------
# End to end against the storage R12 ships with
# ---------------------------------------------------------------------------

def test_the_picture_found_is_the_one_u9_stored(watcher, monkeypatch):
    """R12 and U9 together: the accessor works and the link is still there."""
    project = QgsProject()
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=a:string", "Poles", "memory")
    project.addMapLayer(layer)
    monkeypatch.setattr(QgsProject, "instance", staticmethod(lambda: project))
    fl.link_set(fl.IMAGES, layer.id(), 3, "/photos/pole-3.jpg", project)

    class Hit:
        mLayer = layer

        class mFeature:
            @staticmethod
            def id():
                return 3

    class FakeIdentify:
        TopDownAll = object()
        VectorLayer = object()

        def __init__(self, canvas):
            pass

        def identify(self, x, y, mode, kind):
            return [Hit()]

    opened = []

    import qgis.gui
    monkeypatch.setattr(qgis.gui, "QgsMapToolIdentify", FakeIdentify)
    import fiberq.utils.image_watcher as iw
    monkeypatch.setattr(iw, "_ImagePopup",
                        lambda path, parent, title=None: _FakeDialog(path, opened))

    watcher._show_picture_under(_release_at(5.0, 6.0))
    assert opened == ["/photos/pole-3.jpg"]
    project.clear()


class _FakeDialog:
    def __init__(self, path, sink):
        self.path = path
        self.sink = sink

    def exec(self):
        self.sink.append(self.path)
        return 1
