#!/usr/bin/env python3
"""The QGIS half of the WP4 benchmark harness: code pinning, stub iface, probes.

Everything in here exists to make one number trustworthy. The code digest pins
*which* tree was measured, the stub iface pins the canvas the tools read their
tolerance from, the modal patches stop a dialog blocking a headless run, and the
probes make sure a swallowed error can never be published as a speed-up.

Dev tooling. Never shipped: ``make package`` archives ``HEAD:fiberq`` only.
"""
import logging
import os
import re
import shutil
import sys
import tempfile
import time

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsPointXY,
                       QgsProject, QgsRectangle, QgsSnappingConfig, Qgis)

from bench_common import dataset_files, tree_sha256

#: The canvas scale every scenario is measured at. The placement tools derive
#: their snap tolerance from ``mapUnitsPerPixel()``, so the scale is part of the
#: measurement: at a different zoom the tools do a different amount of work.
METRES_PER_PIXEL = 0.5

#: Canvas size in pixels. Asserted, not hoped for -- an offscreen QMainWindow
#: that never got shown hands out a 0x0 canvas and every snap silently misses.
CANVAS_W, CANVAS_H = 1000, 800
CANVAS_MIN_W, CANVAS_MIN_H = 900, 700

#: A debug-level record whose text matches this is a *swallowed error*: the
#: ~786 `except Exception as e: logger.debug(...)` blocks WP4 section 2 counts. They are
#: invisible at the default WARNING level, which is exactly why they are counted.
SWALLOW_RE = re.compile(r"(?i)(error|fail|could not|cannot|unable|exception|traceback)")


# --- code under measurement ------------------------------------------------
def prepend_code_path(code_dir):
    """Put ``code_dir`` first on ``sys.path`` and refuse an obvious mistake.

    ``--code`` is the whole point of the before/after method: the "before" run
    must import the v1.5.0 tree extracted with ``git archive``, never the working
    tree that already has the WP4 patches in it.
    """
    code_dir = os.path.realpath(code_dir)
    init = os.path.join(code_dir, "fiberq", "__init__.py")
    if not os.path.exists(init):
        raise SystemExit("--code must be a directory containing fiberq/: %s has no %s"
                         % (code_dir, os.path.join("fiberq", "__init__.py")))
    while code_dir in sys.path:
        sys.path.remove(code_dir)
    sys.path.insert(0, code_dir)
    return code_dir


def precompile_code(code_dir, cache_root=None):
    """Byte-compile the measured tree before anything is timed.

    Python caches bytecode next to the source, so the state of ``__pycache__``
    is part of the measurement: a tree freshly extracted with ``git archive``
    has none, while a working tree has a full set from the test suite. One
    ``route_correction`` row left 80 ``.pyc`` files for 98 ``.py`` files in the
    extracted tree (measured), which means the first worker to touch a tree
    pays for compiling it and the other side of the comparison does not.

    Compiling both sides up front removes the asymmetry, and the counts are
    recorded so a reviewer can see that both sides started from the same place.
    A read-only code mount cannot be compiled; then nothing is cached on either
    side, which is equally fair, and ``precompiled`` says so.

    ``cache_root`` keeps the bytecode out of the measured tree. Writing it next
    to the source would put root-owned ``__pycache__`` directories inside the
    extracted v1.5.0 tree -- or, with ``BENCH_CODE=.``, inside the working tree,
    where ``.gitignore`` hides them until a later non-root ``make test`` cannot
    overwrite them. ``sys.pycache_prefix`` (Python 3.8+) sends every ``.pyc``
    into the scratch directory instead, which ``compileall`` honours as well, so
    the fairness argument above survives without touching the tree. The returned
    counts prove the tree gained nothing.
    """
    import compileall
    package = os.path.join(code_dir, "fiberq")
    if cache_root:
        os.makedirs(cache_root, exist_ok=True)
        sys.pycache_prefix = cache_root
    before = _count_pyc(package)
    done = compileall.compile_dir(package, quiet=2, force=False)
    after = _count_pyc(package)
    if cache_root and after != before:
        raise SystemExit("precompile wrote %d .pyc files into the measured tree "
                         "despite sys.pycache_prefix=%s" % (after - before, cache_root))
    return {"pyc_before": before, "pyc_after": after,
            "pycache_prefix": sys.pycache_prefix,
            "precompiled": bool(done)}


def pycache_root(scratch):
    """Where a worker's bytecode goes: inside its own scratch, never the tree."""
    return os.path.join(scratch or os.environ.get("TMPDIR") or tempfile.gettempdir(),
                        "bench_pycache")


def _count_pyc(package):
    return sum(len([n for n in files if n.endswith(".pyc")])
               for _root, _dirs, files in os.walk(package))


def import_fiberq(code_dir):
    """Import ``fiberq`` from ``code_dir`` and prove that is where it came from.

    A decoy directory (``<code>/fiberq`` with no ``__init__.py``) is a namespace
    portion, so Python keeps searching and happily imports the *other* fiberq
    from PYTHONPATH. Without this assertion the run would be labelled "v1.5.0"
    and measure the working tree. Hence the check, not a comment.
    """
    code_dir = os.path.realpath(code_dir)
    import fiberq
    where = getattr(fiberq, "__file__", None)
    if not where or not os.path.realpath(where).startswith(code_dir + os.sep):
        raise SystemExit("fiberq was imported from %r, not from --code %r"
                         % (where, code_dir))
    digest, files, nbytes = tree_sha256(os.path.join(code_dir, "fiberq"))
    return {"sha256": digest, "files": files, "bytes": nbytes,
            "version": _metadata_version(code_dir),
            "module": os.path.relpath(os.path.realpath(where), code_dir)}


#: A label that names a version, so it can be checked against the tree that was
#: actually imported. ``--label v1.5.0`` measuring a 1.6.0 tree is the one
#: mistake the whole before/after method cannot survive, and the sha256 alone
#: does not catch it: it proves *which* tree, not which tree was meant.
VERSION_LABEL_RE = re.compile(r"^v?(\d+\.\d+(?:\.\d+)?)$")


def label_complaint(label, version):
    """Why ``--label`` and the tree's own ``metadata.txt`` disagree, or ``None``."""
    if not label or not version:
        return None
    match = VERSION_LABEL_RE.match(str(label).strip())
    if not match:
        return None                            # a free-text label promises nothing
    if match.group(1) == str(version).strip():
        return None
    return ("--label %s but the imported tree's metadata.txt says version %s. "
            "Either --code points at the wrong tree or the label is wrong; "
            "pass --allow-label-mismatch if the label is deliberate."
            % (label, version))


def _metadata_version(code_dir):
    """The plugin version of the measured tree, read from its own metadata.txt."""
    path = os.path.join(code_dir, "fiberq", "metadata.txt")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("version="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        return None
    return None


def start_qgis():
    """A GUI-enabled QgsApplication. Needed: the scenarios build real widgets."""
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], True)
    app.initQgis()
    return app


def qgis_env():
    """The software half of the environment table."""
    from qgis.PyQt.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
    try:
        from osgeo import gdal
        gdal_version = gdal.__version__
    except Exception:                          # pragma: no cover - GDAL always there
        gdal_version = None
    return {"qgis": Qgis.QGIS_VERSION,
            "qgis_int": Qgis.QGIS_VERSION_INT,
            "qt": QT_VERSION_STR,
            "pyqt": PYQT_VERSION_STR,
            "gdal": gdal_version,
            "python": sys.version.split()[0]}


# --- modal dialogs ---------------------------------------------------------
def patch_modals(save_path):
    """Patch out every modal the scenarios hit, identically on both sides.

    Returns the list of patches actually applied. The worker asserts the list is
    complete: a patch that silently stopped applying (a renamed class) would turn
    one side of the comparison into a different measurement.
    """
    from qgis.PyQt.QtWidgets import QDialog, QFileDialog, QMessageBox
    applied = []
    accepted = QDialog.DialogCode.Accepted
    ok = QMessageBox.StandardButton.Ok
    #: A confirmation must answer Yes, not Ok. The plugin asks with Yes/No or
    #: Yes/Cancel and compares against Yes (main_plugin.py:525,
    #: license_manager.py:115, relations_dialog.py:173), so answering Ok would
    #: silently take the cancel branch -- the scenario would then time the
    #: refusal instead of the work, on both sides of the comparison.
    yes = QMessageBox.StandardButton.Yes

    for name in ("information", "warning", "critical", "about"):
        if hasattr(QMessageBox, name):
            setattr(QMessageBox, name, staticmethod(lambda *a, **k: ok))
            applied.append("QMessageBox.%s" % name)
    if hasattr(QMessageBox, "question"):
        QMessageBox.question = staticmethod(lambda *a, **k: yes)
        applied.append("QMessageBox.question")
    for name in ("exec", "exec_"):
        if hasattr(QMessageBox, name):
            setattr(QMessageBox, name, lambda self, *a, **k: int(yes))
            applied.append("QMessageBox.%s" % name)

    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (save_path, "GeoPackage (*.gpkg)"))
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
    QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
    QFileDialog.getExistingDirectory = staticmethod(
        lambda *a, **k: os.path.dirname(save_path))
    applied += ["QFileDialog.getSaveFileName", "QFileDialog.getOpenFileName",
                "QFileDialog.getOpenFileNames", "QFileDialog.getExistingDirectory"]

    from fiberq.dialogs.cable_dialog import CablePickerDialog
    from fiberq.dialogs.correction_dialog import CorrectionDialog
    for cls in (CablePickerDialog, CorrectionDialog):
        cls.exec = lambda self, *a, **k: int(accepted)
        applied.append("%s.exec" % cls.__name__)
    return applied


#: Every patch patch_modals() must end up applying. Checked, so a renamed class
#: shows up as a failed run instead of as a faster one.
EXPECTED_PATCHES = ("QMessageBox.information", "QMessageBox.warning",
                    "QMessageBox.critical", "QMessageBox.question",
                    "QMessageBox.exec", "QFileDialog.getSaveFileName",
                    "QFileDialog.getOpenFileName", "QFileDialog.getOpenFileNames",
                    "QFileDialog.getExistingDirectory",
                    "CablePickerDialog.exec", "CorrectionDialog.exec")


# --- stub iface ------------------------------------------------------------
class MessageBarStub:
    """Records what the plugin told the user instead of showing it.

    Kept in the result file: "no error was reported" is part of the sanity pass,
    and a run that pushed a critical message is not a clean run.
    """

    def __init__(self):
        self.log = []

    def pushMessage(self, *args, **kwargs):
        self.log.append(("pushMessage", [str(a)[:120] for a in args[:3]]))

    def pushInfo(self, *args):
        self.log.append(("pushInfo", [str(a)[:120] for a in args[:2]]))

    def pushWarning(self, *args):
        self.log.append(("pushWarning", [str(a)[:120] for a in args[:2]]))

    def pushCritical(self, *args):
        self.log.append(("pushCritical", [str(a)[:120] for a in args[:2]]))

    def pushSuccess(self, *args):
        self.log.append(("pushSuccess", [str(a)[:120] for a in args[:2]]))

    def pushWidget(self, *args, **kwargs):
        self.log.append(("pushWidget", []))

    def createMessage(self, *args, **kwargs):
        from qgis.PyQt.QtWidgets import QWidget
        return QWidget()

    def clearWidgets(self):
        pass

    def levels(self):
        return [kind for kind, _ in self.log]


class StubIface:
    """The slice of ``QgisInterface`` the measured code actually calls."""

    def __init__(self):
        from qgis.gui import QgsMapCanvas
        from qgis.PyQt.QtWidgets import QMainWindow
        self._window = QMainWindow()
        self._canvas = QgsMapCanvas(self._window)
        self._window.setCentralWidget(self._canvas)
        self._window.resize(CANVAS_W, CANVAS_H)
        self._window.show()
        QgsApplication.processEvents()
        self._canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self._bar = MessageBarStub()
        self._active = None
        size = settled_size(self._canvas)
        if size.width() < CANVAS_MIN_W or size.height() < CANVAS_MIN_H:
            raise SystemExit("canvas is %dx%d, expected at least %dx%d -- the window "
                             "was not shown, so every snap tolerance would be wrong"
                             % (size.width(), size.height(), CANVAS_MIN_W, CANVAS_MIN_H))

    def canvas_size(self):
        size = settled_size(self._canvas)
        return [size.width(), size.height()]

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return self._window

    def messageBar(self):
        return self._bar

    def activeLayer(self):
        return self._active

    def setActiveLayer(self, layer):
        self._active = layer

    def addToolBarIcon(self, action):
        pass

    def removeToolBarIcon(self, action):
        pass

    def addPluginToMenu(self, menu, action):
        pass

    def removePluginMenu(self, menu, action):
        pass

    def layerTreeView(self):
        return None


def settled_size(canvas):
    """The canvas size once the layout has stopped changing it.

    Offscreen, a freshly shown QMainWindow hands out its pre-layout size first
    and the real one a paint later. Setting the extent from the stale size leaves
    the canvas at 0.5168 m/px instead of 0.5 (measured), which silently changes
    every snap tolerance the placement tools derive from it.
    """
    previous = None
    for _ in range(20):
        QgsApplication.processEvents()
        size = canvas.mapSettings().outputSize()
        current = (size.width(), size.height())
        if current == previous:
            return size
        previous = current
    return canvas.mapSettings().outputSize()


def centre_canvas(iface, x, y, mupp=METRES_PER_PIXEL):
    """Centre the canvas on a map point at exactly ``mupp`` metres per pixel."""
    canvas = iface.mapCanvas()
    for _ in range(10):
        size = settled_size(canvas)
        half_w = size.width() * mupp / 2.0
        half_h = size.height() * mupp / 2.0
        canvas.setExtent(QgsRectangle(x - half_w, y - half_h, x + half_w, y + half_h))
        QgsApplication.processEvents()
        after = canvas.mapSettings().outputSize()
        stable = (after.width(), after.height()) == (size.width(), size.height())
        if stable and abs(canvas.mapUnitsPerPixel() - mupp) <= 1e-9:
            return canvas
    raise SystemExit("canvas settled at %.6f m/px on a %dx%d canvas, expected %.6f"
                     % (canvas.mapUnitsPerPixel(),
                        canvas.mapSettings().outputSize().width(),
                        canvas.mapSettings().outputSize().height(), mupp))


# --- dataset ---------------------------------------------------------------
def copy_dataset(data_dir, scratch):
    """A private copy of the dataset, so a mutating scenario never reuses one.

    Made before every mutating repetition, outside the timed region. Without it
    the second repetition of ``lay_cable`` would start from a project that
    already has the first repetition's cable in it.
    """
    files = dataset_files(data_dir)
    target = tempfile.mkdtemp(prefix="bench_data_", dir=scratch)
    for name in (files["gpkg"], files["qgz"]):
        shutil.copy(os.path.join(data_dir, name), target)
    return target, files


def read_project(work_dir, files):
    """Read the project from ``work_dir``; returns ``(seconds, layer_count)``.

    Asserts the layers resolved into the copy. A project that stored absolute
    paths would have every repetition reading -- and mutating -- the pristine
    dataset instead, and the second repetition would measure different data.
    """
    project = QgsProject.instance()
    project.clear()
    started = time.perf_counter()
    ok = project.read(os.path.join(work_dir, files["qgz"]))
    elapsed = time.perf_counter() - started
    if not ok:
        raise SystemExit("could not read %s in the working copy" % files["qgz"])
    sources = [lyr for lyr in project.mapLayers().values() if hasattr(lyr, "source")]
    outside = [lyr.name() for lyr in sources
               if files["gpkg"] in lyr.source()
               if not lyr.source().startswith(work_dir)]
    if outside:
        raise SystemExit("project layers point outside the working copy (%s): the "
                         "generator must write relative paths" % outside[:3])
    disable_project_snapping(project)
    return elapsed, len(project.mapLayers())


def disable_project_snapping(project):
    """Project snapping off, so the placement rows measure FiberQ's own snap.

    v1.5.0 ignores the project's snapping config altogether; WP4-FU-6 makes the
    tools honour it. Measuring with it off keeps both sides on the same code
    path, which is the only way the PF-5 index can be compared to anything.
    """
    config = project.snappingConfig()
    config.setEnabled(False)
    config.setMode(QgsSnappingConfig.SnappingMode.ActiveLayer)
    project.setSnappingConfig(config)


def state_fingerprint():
    """Per-layer feature counts for the loaded project: what a repetition starts from.

    The fairness rule is "a fresh dataset before every mutating repetition", and
    ``Scenario.mutating`` is how a row claims it needs one -- a hand-maintained
    flag. Flipping ``slack_generate`` to ``mutating=False`` was measured: the
    slack layer climbed 156 -> 236 features across the seven repetitions, each
    one doing more work than the last, and the harness still reported
    ``status: ok`` with a result digest identical to the correctly reset run
    (the post-condition is "+2 per cable", which holds against a dirtier
    layer). Nothing noticed. So the state is fingerprinted outside the timed
    region before every call and compared with the cold call's.

    Taken deliberately without a try/except: a layer that cannot be counted is
    a failed row, not a quiet gap in the evidence.
    """
    counts = {}
    for layer in QgsProject.instance().mapLayers().values():
        if hasattr(layer, "featureCount"):
            counts[layer.name()] = int(layer.featureCount())
    return counts


def state_difference(cold, now):
    """``{layer: [cold, now]}`` for every layer the two fingerprints disagree on."""
    return {name: [cold.get(name), now.get(name)]
            for name in sorted(set(cold) | set(now))
            if cold.get(name) != now.get(name)}


def layer_by_name(name):
    """The one project layer called ``name``; raises when it is missing."""
    found = [lyr for lyr in QgsProject.instance().mapLayers().values()
             if lyr.name() == name]
    if not found:
        raise SystemExit("the dataset has no layer called %r" % name)
    return found[0]


def first_name(*names):
    """The first of ``names`` that exists in the project, else ``None``."""
    have = {lyr.name(): lyr for lyr in QgsProject.instance().mapLayers().values()}
    for name in names:
        if name in have:
            return have[name]
    return None


def polyline(feature):
    """The vertex list of a line feature, single- or multi-part."""
    geom = feature.geometry()
    if geom.isMultipart():
        parts = geom.asMultiPolyline()
        return parts[0] if parts else []
    return geom.asPolyline() or []


def point_of(feature):
    """The ``QgsPointXY`` of a point feature."""
    return QgsPointXY(feature.geometry().asPoint())


# --- probes ----------------------------------------------------------------
class LogProbe:
    """Counts what the measured code logged, by level and by shape.

    Fed from a ``logging`` record factory rather than from a handler, because
    ``fiberq.utils.logger.get_logger`` sets ``propagate = False`` on every module
    logger (``logger.py:181``). A handler on the ``fiberq`` parent therefore sees
    nothing at all, and the sanity pass would report a confident 0 records for
    every scenario -- which is exactly the kind of silence it exists to catch.
    The factory also covers loggers created after the probe is installed.
    """

    #: The three buckets the sanity pass reports. "swallowed" is the WP4 section 2
    #: shape: a debug record that is really an error nobody ever sees.
    BUCKETS = ("errors", "warnings", "swallowed")

    def __init__(self, keep=5):
        self.keep = keep
        self.levels = {}
        self.counts = dict.fromkeys(self.BUCKETS, 0)
        self.samples = {name: [] for name in self.BUCKETS}
        self.total = 0

    def observe(self, record):
        """Count one record. Called for every record in the fiberq namespace."""
        self.total += 1
        self.levels[record.levelname] = self.levels.get(record.levelname, 0) + 1
        try:
            text = "%s: %s" % (record.name, record.getMessage()[:200])
        except Exception:                      # pragma: no cover - bad format string
            text = "%s: <unformattable>" % record.name
        if record.levelno >= logging.ERROR:
            bucket = "errors"
        elif record.levelno >= logging.WARNING:
            bucket = "warnings"
        elif SWALLOW_RE.search(text):
            bucket = "swallowed"
        else:
            return
        self.counts[bucket] += 1
        if len(self.samples[bucket]) < self.keep:
            self.samples[bucket].append(text)

    def report(self):
        """Counts are complete; the samples are capped at ``keep`` per bucket."""
        return {"records": self.total,
                "levels": dict(self.levels),
                "errors": self.counts["errors"],
                "error_sample": list(self.samples["errors"]),
                "warnings": self.counts["warnings"],
                "warning_sample": list(self.samples["warnings"]),
                "swallowed_debug": self.counts["swallowed"],
                "swallowed_sample": list(self.samples["swallowed"])}


def quiet_logging():
    """The default user experience: DEBUG and INFO dropped everywhere.

    The worker sets ``FIBERQ_LOG_LEVEL=DEBUG`` before importing fiberq so that
    every module logger can be read by the probe. That would also make the
    plugin's own QGIS log handler fire on every swallowed error, which costs real
    time, so outside the sanity call the records are disabled again -- the level
    a user runs at.
    """
    logging.disable(logging.INFO)


def sanity_on(keep=5):
    """Let DEBUG records through and start counting them, for the cold call only.

    Returns ``(probe, restore)``; ``restore`` is passed back to ``sanity_off``.
    The plugin's own QGIS log handlers are muted to WARNING while the probe runs,
    so the cold call is not inflated by pushing every swallowed error into the
    QGIS message log -- something no user at the default level pays for.
    """
    logging.disable(logging.NOTSET)
    probe = LogProbe(keep=keep)
    previous_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous_factory(*args, **kwargs)
        if record.name.split(".", 1)[0] == "fiberq":
            probe.observe(record)
        return record

    logging.setLogRecordFactory(factory)
    muted = []
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if not name.startswith("fiberq") or not isinstance(logger, logging.Logger):
            continue
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            if type(handler).__name__ == "QgsLogHandler":
                muted.append((handler, handler.level))
                handler.setLevel(logging.WARNING)
    return probe, (previous_factory, muted)


def sanity_off(probe, restore):
    """Stop counting, restore the handlers, go back to the quiet default."""
    previous_factory, muted = restore
    logging.setLogRecordFactory(previous_factory)
    for handler, level in muted:
        handler.setLevel(level)
    quiet_logging()
    return probe.report()


class QgisLogProbe:
    """Counts QGIS's own message log, which is where C++ complaints land."""

    def __init__(self):
        self.counts = {}
        self.samples = []
        self.hooked = False
        try:
            QgsApplication.messageLog().messageReceived.connect(self._got)
            self.hooked = True
        except Exception:                      # pragma: no cover - overload drift
            self.hooked = False

    def _got(self, message, tag, level):
        key = "%s/%s" % (tag, int(level))
        self.counts[key] = self.counts.get(key, 0) + 1
        if int(level) >= int(Qgis.MessageLevel.Warning) and len(self.samples) < 5:
            self.samples.append("%s: %s" % (tag, str(message)[:160]))

    def report(self):
        return {"hooked": self.hooked, "counts": dict(self.counts),
                "samples": list(self.samples)}
