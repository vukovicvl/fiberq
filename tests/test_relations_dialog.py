"""A new relation is stored without a warning, and with the "created" it has always had.

v1.6.0 QA finding Q15: on QGIS 4.2.3 with Python 3.14, creating a relation in
the Relations dialog put "datetime.datetime.utcnow() is deprecated" in QGIS's
Python warning tab. Python 3.12 deprecates that call, so QGIS 3.40 and QGIS 4
printed it too; the Python of QGIS 3.22 does not. The relation was stored all
the same, so what it stores is pinned as well: no FiberQ code reads
``created`` back, but each relation the dialog made carries it in the project,
and in the copy of the relations a GeoPackage export writes into its metadata.
"""
import json
import os
import re
import time
import warnings
from datetime import datetime, timedelta, timezone

import pytest
from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import QDialog

RELATIONS = ("StuboviPlugin", "Relacije/relations_v1")

#: What a relation stores as ``created``: UTC, to the microsecond, with a Z.
CREATED = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")
CREATED_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

#: What counts as a deprecation here. QGIS shows each of them in its log: its
#: Python runs ``warnings.simplefilter("default")`` and sends what that lets
#: through to the log's "Python warning" tab (qgis/utils.py, 3.22-4.2).
DEPRECATIONS = (DeprecationWarning, PendingDeprecationWarning, FutureWarning)


class _Bar:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


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
def plugin(project):
    """A FiberQPlugin with the managers the Relations dialog uses, and nothing else."""
    from fiberq.core.cable_manager import CableManager
    from fiberq.core.data_manager import DataManager
    from fiberq.core.relations_manager import RelationsManager
    from fiberq.main_plugin import FiberQPlugin

    obj = FiberQPlugin.__new__(FiberQPlugin)
    obj.iface = _Iface()
    obj.data_manager = DataManager(obj.iface, obj)
    obj.relations_manager = RelationsManager(obj.data_manager)
    obj.cable_manager = CableManager(obj.iface, None, obj.data_manager, None)
    return obj


@pytest.fixture
def named_feeder_a(monkeypatch):
    """New relation answers as if "Feeder A" was typed and OK pressed, with no modal loop."""
    from fiberq.dialogs.relations_dialog import NewRelationDialog

    def accept(dialog):
        dialog.edit_name.setText("Feeder A")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(NewRelationDialog, "exec", accept)


@pytest.fixture
def east_of_utc():
    """The local clock 5 h 45 min ahead of UTC, so local time cannot pass for UTC."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset() is Unix-only, so the local clock cannot be moved here")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("TZ", "FQT-05:45")
        try:
            time.tzset()
            assert datetime.now().astimezone().utcoffset() == timedelta(hours=5, minutes=45)
            yield
        finally:
            patch.undo()
            time.tzset()


def _stored(project):
    raw = project.readEntry(*RELATIONS, "")[0]
    return json.loads(raw)["relations"] if raw else []


def _fiberq_deprecations(caught):
    """The recorded deprecations raised from a file of the fiberq package, as text."""
    import fiberq
    package = os.path.dirname(os.path.realpath(fiberq.__file__)) + os.sep
    found = []
    for warning in caught:
        if not issubclass(warning.category, DEPRECATIONS):
            continue
        if os.path.realpath(warning.filename).startswith(package):
            found.append(warnings.formatwarning(
                warning.message, warning.category, warning.filename, warning.lineno).rstrip())
    return found


def test_a_new_relation_puts_no_deprecation_in_the_log(project, plugin, named_feeder_a):
    """Open the dialog, New relation, OK -- and no deprecation from FiberQ's code on the way.

    Recorded, not raised: opening the dialog lists the cables through
    ``FiberQPlugin.list_all_cables``, which catches every exception, so a
    deprecation raised as an error there would be swallowed and the test would
    pass, while QGIS, which only shows the warning, still puts it in its log.
    """
    from fiberq.dialogs.relations_dialog import RelationsDialog
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        RelationsDialog(plugin)._on_add_relation()
    found = _fiberq_deprecations(caught)
    assert not found, "\n".join(found)
    assert [r["name"] for r in _stored(project)] == ["Feeder A"]


def test_created_is_utc_in_the_shape_relations_have_always_stored(
        project, plugin, named_feeder_a, east_of_utc):
    """UTC to the microsecond, with a Z: never "+00:00", never the local clock."""
    from fiberq.dialogs.relations_dialog import RelationsDialog
    before = datetime.now(timezone.utc)
    RelationsDialog(plugin)._on_add_relation()
    after = datetime.now(timezone.utc)
    created = _stored(project)[0]["created"]
    assert CREATED.fullmatch(created), created
    moment = datetime.strptime(created, CREATED_FORMAT).replace(tzinfo=timezone.utc)
    assert before <= moment <= after, (before, created, after)
