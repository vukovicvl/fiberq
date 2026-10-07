"""The Designer metadata table survives a write that goes wrong.

Not claimed under WP4 4.2 -- an ordinary bug fix shipping in the same release
(plan item U7). It is here because of what the old sequence did when anything
interrupted it.

``_write_metadata_table`` used to open with ``DROP TABLE IF EXISTS
_fiberq_metadata`` and ``CREATE TABLE``, both of which sqlite runs in autocommit
when the driver is in its legacy ``isolation_level=''`` mode. They were durable
the instant they ran, and only the ``INSERT``s that followed were covered by the
``commit()``. So any failure in between -- the GeoPackage going read-only, the
disk filling, another program taking the lock, QGIS being closed -- left the
table **present, registered in gpkg_contents, and empty**. Relations, latent
elements, colour catalogues and anything FiberQ Designer had written were gone,
with no error above debug level and a file GDAL still considered valid.

The replacement owns its transaction: ``BEGIN IMMEDIATE`` takes the write lock
before touching anything, and a failure rolls back to exactly what was there
before.

:func:`test_an_interrupted_write_leaves_the_old_table_intact` is the one that
measures it, by killing a child process mid-write and reading the file back.
"""
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import textwrap

import pytest
from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

from fiberq.core.export_manager import ExportManager


class FakeBar:
    def pushWarning(self, title, text):
        pass

    def pushSuccess(self, title, text):
        pass


class FakeIface:
    def messageBar(self):
        return FakeBar()

    def mainWindow(self):
        return None


@pytest.fixture
def gpkg(tmp_path):
    """A real GeoPackage with one layer, so gpkg_contents is genuine."""
    path = tmp_path / "project.gpkg"
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer", "Poles", "memory")
    layer.startEditing()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1, 1)))
    feature.setAttribute("id", 1)
    layer.addFeature(feature)
    assert layer.commitChanges()
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "Poles"
    assert QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(path), QgsCoordinateTransformContext(), options
    )[0] == QgsVectorFileWriter.WriterError.NoError
    return path


def _rows(path):
    with sqlite3.connect(str(path)) as conn:
        try:
            return dict(conn.execute("SELECT key, value FROM _fiberq_metadata"))
        except sqlite3.OperationalError:
            return None


def _put(path, pairs, with_primary_key=True):
    key_type = "TEXT PRIMARY KEY" if with_primary_key else "TEXT"
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS _fiberq_metadata (key {key_type}, value TEXT)")
        conn.executemany(
            "INSERT INTO _fiberq_metadata (key, value) VALUES (?, ?)", list(pairs.items()))
        conn.commit()


# ---------------------------------------------------------------------------

def test_a_key_written_by_another_tool_survives(gpkg):
    """The headline: Designer's own keys are no longer dropped on every save."""
    _put(gpkg, {"designer_project_id": "abc-123", "designer_note": "do not lose me"})

    written, reason = ExportManager(FakeIface())._write_metadata_table(str(gpkg))

    assert (written, reason) == (True, "")
    rows = _rows(gpkg)
    assert rows["designer_project_id"] == "abc-123"
    assert rows["designer_note"] == "do not lose me"
    assert "schema_version" in rows, "FiberQ's own keys must still be written"


def test_fiberqs_own_keys_are_refreshed_not_duplicated(gpkg):
    _put(gpkg, {"schema_version": "0.1"})

    assert ExportManager(FakeIface())._write_metadata_table(str(gpkg))[0] is True

    with sqlite3.connect(str(gpkg)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM _fiberq_metadata WHERE key = 'schema_version'").fetchone()[0]
    assert count == 1
    assert _rows(gpkg)["schema_version"] != "0.1"


def test_a_table_with_no_primary_key_is_repaired_rather_than_duplicated(gpkg):
    """Another tool's table may have no PK; INSERT OR REPLACE would double up."""
    _put(gpkg, {"schema_version": "0.1", "designer_project_id": "abc"},
         with_primary_key=False)

    assert ExportManager(FakeIface())._write_metadata_table(str(gpkg))[0] is True

    with sqlite3.connect(str(gpkg)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM _fiberq_metadata WHERE key = 'schema_version'").fetchone()[0]
    assert count == 1
    assert _rows(gpkg)["designer_project_id"] == "abc"


def test_the_table_is_registered_so_gdal_can_see_it(gpkg):
    ExportManager(FakeIface())._write_metadata_table(str(gpkg))

    with sqlite3.connect(str(gpkg)) as conn:
        registered = conn.execute(
            "SELECT data_type FROM gpkg_contents WHERE table_name = '_fiberq_metadata'"
        ).fetchone()
    assert registered == ("attributes",)


def test_a_locked_geopackage_fails_before_touching_anything(gpkg):
    """BEGIN IMMEDIATE takes the lock up front, so a held file fails clean.

    ``schema_version`` is seeded deliberately: it is a key the writer DELETEs
    before re-inserting, so without the transaction the delete would stick and
    the row would be gone. A test seeded only with keys the writer never
    touches would pass with no transaction at all.
    """
    _put(gpkg, {"designer_project_id": "abc-123", "schema_version": "0.1"})
    before = _rows(gpkg)

    holder = sqlite3.connect(str(gpkg), isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        written, reason = ExportManager(FakeIface())._write_metadata_table(str(gpkg))
    finally:
        holder.execute("ROLLBACK")
        holder.close()

    assert written is False
    assert "locked" in reason
    assert _rows(gpkg) == before


def test_a_write_that_fails_part_way_rolls_back(gpkg):
    """A trigger that rejects one key must not cost the others.

    The seeded ``project_version`` is the point: the writer deletes and
    re-inserts it *before* reaching the key the trigger rejects, so only a real
    rollback brings it back. Without the transaction this test fails with that
    row missing -- which is what makes it a test of the transaction rather than
    of the trigger.
    """
    _put(gpkg, {"designer_project_id": "abc-123", "project_version": "0.1"})
    before = _rows(gpkg)
    with sqlite3.connect(str(gpkg)) as conn:
        conn.execute(
            "CREATE TRIGGER stop_schema BEFORE INSERT ON _fiberq_metadata "
            "WHEN NEW.key = 'schema_version' "
            "BEGIN SELECT RAISE(ABORT, 'disk full'); END;")
        conn.commit()

    written, reason = ExportManager(FakeIface())._write_metadata_table(str(gpkg))

    assert written is False
    assert "disk full" in reason
    assert _rows(gpkg) == before, "a partial write reached disk"
    assert before["project_version"] == "0.1", "the rolled-back row did not come back"

    with sqlite3.connect(str(gpkg)) as conn:
        registered = conn.execute(
            "SELECT COUNT(*) FROM gpkg_contents WHERE table_name='_fiberq_metadata'"
        ).fetchone()[0]
    assert registered == 0, "the failed write still registered the table"


def test_an_interrupted_write_leaves_the_old_table_intact(gpkg):
    """Kill the process part-way through the real write and read the file back.

    A child process runs the actual ``_write_metadata_table`` with sqlite's
    ``execute`` rigged to call ``os._exit`` on the sixth statement -- after the
    table is created and the first key written. On the old sequence that left
    the table present, registered and EMPTY, because DROP and CREATE were
    durable before the first INSERT ever ran.
    """
    _put(gpkg, {"designer_project_id": "abc-123", "relations_json": '{"relations":[]}'})
    before = _rows(gpkg)

    repo = str(pathlib.Path(__file__).resolve().parent.parent)
    # A plain string, not an f-string: the child needs braces of its own and
    # takes its two paths on argv instead of by interpolation.
    script = textwrap.dedent("""
        import os, sys, sqlite3
        repo, target = sys.argv[1], sys.argv[2]
        sys.path.insert(0, repo)
        from qgis.core import QgsApplication
        app = QgsApplication([], False); app.initQgis()

        real_connect = sqlite3.connect

        # Kills the process one statement after the first row reaches
        # _fiberq_metadata. Anchored on the writer's own statements rather than
        # a process-global ordinal, which would quietly drift to somewhere
        # harmless the next time the surrounding code changed and leave this
        # test passing while measuring nothing. conn.execute() and
        # cursor().execute() are both watched, so it bites the old DROP-based
        # sequence and the new one alike.
        state = {"inserted": 0}

        class Bomb:
            def __init__(self, inner):
                self._inner = inner

            def execute(self, *args, **kwargs):
                if state["inserted"] >= 1:
                    os._exit(9)
                sql = " ".join(str(args[0] if args else "").split()).upper()
                result = self._inner.execute(*args, **kwargs)
                if sql.startswith("INSERT") and "_FIBERQ_METADATA" in sql:
                    state["inserted"] += 1
                return result

            def cursor(self, *args, **kwargs):
                return Bomb(self._inner.cursor(*args, **kwargs))

            def __getattr__(self, name):
                return getattr(self._inner, name)

        sqlite3.connect = lambda *a, **k: Bomb(real_connect(*a, **k))

        from fiberq.core.export_manager import ExportManager
        ExportManager(None)._write_metadata_table(target)
        os._exit(0)
    """)
    killed = subprocess.run([sys.executable, "-c", script, repo, str(gpkg)],
                            capture_output=True, text=True)

    assert killed.returncode == 9, (
        f"the child did not reach the kill point: rc={killed.returncode}\n{killed.stderr[-2000:]}")
    assert _rows(gpkg) == before, "the interrupted write was not rolled back"


def test_a_missing_file_is_named(tmp_path):
    written, reason = ExportManager(FakeIface())._write_metadata_table(
        str(tmp_path / "nowhere.gpkg"))
    assert written is False
    assert "not there" in reason


def test_the_metadata_round_trips_as_json(gpkg):
    """Designer reads these values back, so they must stay parseable.

    The project entries are seeded first. Without them every ``_json`` key is
    something json.dumps produced moments earlier, and the loop proves only
    that json can read its own output.
    """
    from qgis.core import QgsProject

    project = QgsProject.instance()
    seeded = {
        "Relacije/relations_v1": '{"relations":[{"id":1,"from":"A","to":"B"}]}',
        "LatentElements/latent_v1": '{"cables":{"c1":["x"]}}',
        "ColorCatalogs/catalogs_v1": '{"catalogs":[{"name":"TIA-598-C"}]}',
    }
    for key, value in seeded.items():
        project.writeEntry("StuboviPlugin", key, value)
    try:
        assert ExportManager(FakeIface())._write_metadata_table(str(gpkg))[0] is True
        rows = _rows(gpkg)

        expected = {"relations_json", "latent_elements_json", "color_catalog_json"}
        assert expected <= set(rows), f"missing {expected - set(rows)}"
        for key in sorted(k for k in rows if k.endswith("_json")):
            json.loads(rows[key])
        assert json.loads(rows["relations_json"])["relations"][0]["from"] == "A"
        assert rows["color_standard"] == "TIA-598-C"
    finally:
        for key in seeded:
            project.removeEntry("StuboviPlugin", key)
    assert os.path.isfile(gpkg)
