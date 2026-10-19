"""FiberQ follows QGIS's language until the user picks one of its own.

Unclaimed (found in the v1.6.0 docs review). ``i18n.current_locale()`` prefers
FiberQ's own choice (``FiberQ/lang``) over QGIS's language setting, so that a
user can run FiberQ in one language and QGIS in another. But the language that
was merely *shown* at start-up was stored as that choice: initGui read
``_get_lang()``, which answers "en" when nothing is stored, and the deferred
``_fiberq_apply_language`` wrote it back. From the second start a French QGIS
had an English FiberQ, and the guide's "set QGIS's language and restart" never
worked again.

Two more things kept it from working, both measured:
- every start before 1.6.0 stored the language, so an upgraded install already
  holds an "en" nobody picked. ``forget_unpicked_language`` removes it once.
  An explicit pick now also writes a marker, which keeps a real choice of
  English;
- ``make i18n-compile`` writes a .qm even for an untranslated catalogue (the
  shipped French one is 30 bytes), and a .qm on disk counted as a language.
  The button said "Français" while nothing was translated.

Run in a subprocess with its own HOME and settings directory: the plugin needs a
real ``initGui()`` and ``unload()``, and the settings it reads and writes must
not leak into the rest of the suite or into the checkout.
"""
import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wall-clock ceiling for each child. The suite has no timeout plugin.
TIMEOUT_S = 120

DRIVER = '''
import json
import os
import sys
from unittest import mock

sys.path.insert(0, {repo!r})

from qgis.core import QgsApplication

QgsApplication.setPrefixPath("/usr", True)
APP = QgsApplication([], True)
APP.initQgis()

from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QMainWindow, QMessageBox, QToolBar

settings = QSettings()
settings.remove("FiberQ/lang")
settings.remove("FiberQ/lang_picked")
if {preset!r} is not None:
    settings.setValue("FiberQ/lang", {preset!r})
if {marker!r}:
    settings.setValue("FiberQ/lang_picked", True)
settings.setValue("locale/userLocale", {locale!r})
settings.sync()

# _fiberq_set_language confirms with a modal box, which would block the child.
QMessageBox.information = staticmethod(lambda *a, **k: None)


class Iface:
    """What initGui() and unload() really use; the rest answers with a MagicMock."""

    def __init__(self):
        self._window = QMainWindow()
        self._canvas = QgsMapCanvas(self._window)
        self._window.setCentralWidget(self._canvas)
        self._mocks = {{}}

    def mainWindow(self):
        return self._window

    def mapCanvas(self):
        return self._canvas

    def addToolBar(self, name):
        return QToolBar(name, self._window)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self.__dict__["_mocks"].setdefault(name, mock.MagicMock(name=name))


from fiberq.main_plugin import FiberQPlugin

# initGui() arms a 2 s one-shot schema migration; it is not what this is about.
FiberQPlugin._run_schema_migrations = lambda self: None

plugin = FiberQPlugin(Iface())
plugin.initGui()
for _ in range(50):
    APP.processEvents()     # the deferred _fiberq_apply_language runs here

out = {{
    "stored_after_start": QSettings().value("FiberQ/lang", None),
    "button": plugin._fiberq_lang_button.text(),
    "menu": sorted(plugin._fiberq_lang_actions),
    "checked": sorted(code for code, action in plugin._fiberq_lang_actions.items()
                      if action.isChecked()),
}}
plugin._fiberq_set_language("sr")
out["stored_after_pick"] = QSettings().value("FiberQ/lang", None)
out["picked_after_pick"] = str(QSettings().value("FiberQ/lang_picked", "")).lower()
plugin.unload()
print("RESULT " + json.dumps(out), flush=True)
sys.stdout.flush()
os._exit(0)
'''


def _run(tmp_path, locale, preset=None, marker=False):
    script = tmp_path / "language_preference.py"
    script.write_text(DRIVER.format(repo=REPO_ROOT, locale=locale, preset=preset,
                                    marker=marker), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", TMPDIR=str(tmp_path),
                       HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                       FIBERQ_LOG_FILE="false")
    # pytest-qgis points QGIS at <checkout>/.qgis-settings; inherited, the child
    # would write its settings there, into the checkout CI tests.
    environment.pop("QGIS_CUSTOM_CONFIG_PATH", None)
    done = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path),
                          env=environment, timeout=TIMEOUT_S,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 0, f"returncode {done.returncode}\n{output}"
    lines = [ln for ln in output.splitlines() if ln.startswith("RESULT ")]
    assert lines, output
    return json.loads(lines[-1][len("RESULT "):])


@pytest.mark.parametrize("locale, shown", [
    ("sr", "sr"),   # a catalogue ships for it, so FiberQ is in Serbian
    ("de", "en"),   # none does, so FiberQ is in English and must say so
])
def test_the_first_start_stores_no_language_and_shows_the_one_in_use(tmp_path, locale, shown):
    from fiberq.i18n import language_name

    result = _run(tmp_path, locale)
    assert result["stored_after_start"] is None, (
        "a start-up stored a language nobody picked, so QGIS's setting would be "
        "ignored from the next start")
    assert result["button"] == language_name(shown)
    assert result["checked"] == [shown]


def test_an_explicit_pick_is_stored_and_marked(tmp_path):
    result = _run(tmp_path, "de")
    assert result["stored_after_pick"] == "sr"
    assert result["picked_after_pick"] == "true"


def test_an_upgraded_install_follows_qgis_again(tmp_path):
    """Every start before 1.6.0 stored "en"; nobody picked it."""
    from fiberq.i18n import language_name

    result = _run(tmp_path, "sr", preset="en")
    assert result["stored_after_start"] is None
    assert result["button"] == language_name("sr")


def test_a_real_choice_of_english_is_kept(tmp_path):
    from fiberq.i18n import language_name

    result = _run(tmp_path, "sr", preset="en", marker=True)
    assert result["stored_after_start"] == "en"
    assert result["button"] == language_name("en")


def test_a_language_with_nothing_translated_is_not_offered(tmp_path):
    """The French catalogue ships empty: French QGIS, English FiberQ, and the
    button and menu must say so."""
    from fiberq.i18n import language_name

    result = _run(tmp_path, "fr")
    assert result["button"] == language_name("en")
    assert result["checked"] == ["en"]
    assert "fr" not in result["menu"]
