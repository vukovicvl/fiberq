"""The schematic view's Center button, which has never worked.

WP4 4.2 item R11. Two defects in four lines, the second hidden by the first.

**The brush.** The highlight ring was added with::

    self.scene.addEllipse(x, y, w, h, QPen(...), Qt.BrushStyle.NoBrush)

``addEllipse`` wants a ``QBrush`` there. Passing the enum is

    TypeError: argument 6 has unexpected type 'BrushStyle'

measured on **3.44.15 as well as 4.0.3** -- so this is not a Qt6 regression,
it is a button that has never once centred anything on any supported version.
``QBrush(Qt.BrushStyle.NoBrush)`` is the brush that means "no fill".

**The use-after-free underneath.** Removal was a closure over a local ``item``
fired by a 1300 ms timer. ``rebuild()`` calls ``scene.clear()``, which destroys
the item's C++ object, and ``removeItem`` on it afterwards is a **SIGSEGV** --
measured, child process returncode -11 on both stacks, not an exception
anything could catch. The schematic view rebuilds on ``layersAdded`` and
``layerWillBeRemoved``, so adding a layer within 1.3 s of pressing Center
would have taken QGIS down. Fixing only the brush would have turned a dead
button into a hard crash, which is why both are one commit.

The crash regression runs in a **subprocess** and asserts the exit code:
pytest-qgis starts its ``QgsApplication`` in ``pytest_configure``, so a
segfault anywhere takes the whole run with it rather than failing one test.
"""
import os
import subprocess
import sys

import pytest
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor, QPen
from qgis.PyQt.QtWidgets import QGraphicsScene, QGraphicsView

from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for the crash-regression child. The suite has no timeout
#: plugin, so without this a wedged child would run to the CI job's own limit.
TIMEOUT_S = 120


@pytest.fixture
def dialog(qgis_app):
    """The real ``_center_on`` / ``_drop_highlight`` on a real scene.

    ``OpticalSchematicDialog.__init__`` builds a whole dialog against a live
    ``iface``, which these two methods do not need and a headless run cannot
    cheaply provide. The methods under test are the real ones.
    """
    dlg = OpticalSchematicDialog.__new__(OpticalSchematicDialog)
    dlg.scene = QGraphicsScene()
    dlg.view = QGraphicsView(dlg.scene)
    dlg._highlight = None
    dlg._last_positions = {"ODF-1": (10.0, 20.0), "TB-2": (30.0, 40.0)}
    yield dlg
    dlg.scene.clear()


# ---------------------------------------------------------------------------
# The brush
# ---------------------------------------------------------------------------

def test_the_enum_really_is_rejected_as_a_brush(qgis_app):
    """The defect itself, so nobody writes it back."""
    scene = QGraphicsScene()
    pen = QPen(QColor(255, 165, 0), 2.4)
    with pytest.raises(TypeError):
        scene.addEllipse(0, 0, 10, 10, pen, Qt.BrushStyle.NoBrush)
    # and the form the fix uses
    assert scene.addEllipse(0, 0, 10, 10, pen, QBrush(Qt.BrushStyle.NoBrush)) is not None
    scene.clear()


def test_centering_on_a_known_element_adds_the_ring(dialog):
    dialog._center_on("ODF-1")
    assert dialog._highlight is not None
    assert dialog._highlight in dialog.scene.items()
    assert dialog._highlight.zValue() == 10


def test_centering_on_an_unknown_name_does_nothing(dialog):
    dialog._center_on("not in the layout")
    assert dialog._highlight is None
    assert dialog.scene.items() == []


def test_centering_twice_leaves_one_ring(dialog):
    """The second press drops the first ring rather than stacking them."""
    dialog._center_on("ODF-1")
    first = dialog._highlight
    dialog._center_on("TB-2")
    assert dialog._highlight is not first
    assert first not in dialog.scene.items()
    assert len(dialog.scene.items()) == 1


# ---------------------------------------------------------------------------
# The use-after-free
# ---------------------------------------------------------------------------

def test_dropping_the_highlight_is_idempotent(dialog):
    """The timer, the next press and rebuild() all call it, in any order."""
    dialog._center_on("ODF-1")
    dialog._drop_highlight()
    assert dialog._highlight is None
    dialog._drop_highlight()
    dialog._drop_highlight()
    assert dialog.scene.items() == []


def test_dropping_after_a_scene_clear_does_not_reach_the_dead_item(dialog):
    """``rebuild()`` drops the reference BEFORE clearing, which is the guard.

    Simulated here in the order that used to crash: clear the scene, then ask
    for the removal the timer would have asked for.
    """
    dialog._center_on("ODF-1")
    dialog._highlight = None          # what rebuild() does first
    dialog.scene.clear()              # what destroyed the C++ object
    dialog._drop_highlight()          # what the 1300 ms timer then calls
    assert dialog._highlight is None


CRASH_DRIVER = '''
import os, sys
sys.path.insert(0, {repo!r})
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication
app = QgsApplication([], True)
from qgis.PyQt.QtWidgets import QGraphicsScene, QGraphicsView
from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog

dlg = OpticalSchematicDialog.__new__(OpticalSchematicDialog)
dlg.scene = QGraphicsScene()
dlg.view = QGraphicsView(dlg.scene)
dlg._highlight = None
dlg._last_positions = {{"ODF-1": (10.0, 20.0)}}

dlg._center_on("ODF-1")
print("centred", flush=True)
# What rebuild() does. The old code left the pending timer holding this item.
dlg._drop_highlight()
dlg.scene.clear()
print("rebuilt", flush=True)
# What the 1300 ms timer then fires. The old code segfaulted here.
dlg._drop_highlight()
print("SURVIVED", flush=True)
sys.stdout.flush()
os._exit(0)
'''


OLD_PATTERN_DRIVER = '''
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication
app = QgsApplication([], True)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor, QPen
from qgis.PyQt.QtWidgets import QGraphicsScene

# Exactly what _center_on used to do, with the brush already corrected so the
# TypeError does not mask what is underneath.
scene = QGraphicsScene()
item = scene.addEllipse(0, 0, 24, 24, QPen(QColor(255, 165, 0), 2.4),
                        QBrush(Qt.BrushStyle.NoBrush))

def _remove():                 # the closure the 1300 ms timer held
    scene.removeItem(item)

scene.clear()                  # what rebuild() does
print("cleared", flush=True)
_remove()                      # what the timer then fired
print("SURVIVED", flush=True)
sys.stdout.flush()
os._exit(0)
'''


def _child(tmp_path, name, source):
    script = tmp_path / name
    script.write_text(source, encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(tmp_path), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def test_the_old_closure_pattern_really_does_crash(tmp_path):
    """The hazard itself, pinned in a child so it costs this test only.

    Measured returncode -11 (SIGSEGV) on 3.44.15 and 4.0.3. Asserted as
    "did not exit cleanly" rather than exactly -11, because the signal is the
    platform's business; what matters is that it is not an exception the
    plugin could have caught, which is why ``_drop_highlight`` clears the
    reference instead of guarding the call.
    """
    code, output = _child(tmp_path, "old_pattern.py", OLD_PATTERN_DRIVER)
    assert "cleared" in output, output
    assert code != 0, (
        "removeItem() on an item destroyed by scene.clear() exited cleanly "
        f"here, so this QGIS no longer has the hazard: {output}")
    assert "SURVIVED" not in output, output


def test_rebuilding_then_firing_the_timer_does_not_crash_qgis(tmp_path):
    """Exit code is the only reliable signal: a SIGSEGV is not catchable."""
    script = tmp_path / "center_then_rebuild.py"
    script.write_text(CRASH_DRIVER.format(repo=str(REPO_ROOT)), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(tmp_path), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 0, f"returncode {done.returncode}\n{output}"
    assert "SURVIVED" in output, output
