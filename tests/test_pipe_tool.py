"""The duct tools open on every QGIS the plugin declares, QGIS 3.22 included.

Branch 13 (unclaimed; found by the snap tests, the first to build this tool).
``PipePlaceTool.__init__`` drew its preview line with
``QgsRubberBand.setWidth(1.5)``. Until QGIS 3.40 the method took an int, and
with sip 6 a float is ``TypeError: argument 1 has unexpected type 'float'``:
on QGIS 3.22.16 (Python 3.10) both the PE duct and the transition duct tool
ended in an error box the moment their dialog was accepted. From 3.40 the
method takes a float and draws a 1.5 px line -- ``width()`` answers 2 only
because it rounds -- so 1.5 is still what the tool asks for wherever QGIS takes
it, and the int 2 only where it raises.
"""
import pytest
from qgis.gui import QgsMapCanvas, QgsRubberBand

from fiberq.tools.pipe_tool import PipePlaceTool


class _Iface:
    def __init__(self, canvas):
        self._canvas = canvas

    def mapCanvas(self):
        return self._canvas


def _takes_a_float(canvas):
    try:
        QgsRubberBand(canvas).setWidth(1.5)
    except TypeError:
        return False
    return True


@pytest.mark.parametrize("kind", ["PE", "PRELAZ"])
def test_both_duct_tools_open_and_keep_their_1_5_px_line_wherever_qgis_takes_it(qgis_app, monkeypatch, kind):
    canvas = QgsMapCanvas()
    expected = [1.5] if _takes_a_float(canvas) else [1.5, 2]
    asked = []
    real = QgsRubberBand.setWidth

    def recording(band, width):
        asked.append(width)
        return real(band, width)

    monkeypatch.setattr(QgsRubberBand, "setWidth", recording)
    tool = PipePlaceTool(_Iface(canvas), None, kind, {})
    assert tool.rb is not None
    assert asked == expected
