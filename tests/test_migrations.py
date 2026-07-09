"""Tests for the WP1b schema migration runner + versioning lifecycle.

These need a QgsApplication (provided by pytest-qgis) because the runner
reads/writes QgsProject entries and edits QgsVectorLayers. Fresh QgsProject()
instances keep the singleton project untouched. The pre-1.0 GeoPackage fixture is
generated on the fly into ``tmp_path`` by tests/fixtures/make_sample_project.py,
so no binary blob is committed.
"""
import importlib.util
import os

import pytest
from qgis.core import QgsProject, QgsVectorLayer

from fiberq.core import migrations as m
from fiberq.core import schema_version as sv

_LAYER_NAMES = ["ODF", "Kablovi_podzemni", "Trasa", "OKNA", "Objekti"]

# One pre-existing text field per layer, used to prove existing values survive.
_CHECK_FIELD = {
    "ODF": "naziv",
    "Kablovi_podzemni": "naziv",
    "Trasa": "naziv",
    "OKNA": "broj_okna",
    "Objekti": "naziv",
}


def _load_generator():
    """Import tests/fixtures/make_sample_project.py (fixtures is not a package)."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "fixtures", "make_sample_project.py")
    spec = importlib.util.spec_from_file_location("make_sample_project", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_and_load(tmp_path, with_metadata_table=True):
    """Build a pre-1.0 fixture and load its layers into a fresh QgsProject."""
    gen = _load_generator()
    gpkg = str(tmp_path / "legacy_pre_uuid.gpkg")
    gen.build_pre_uuid_gpkg(gpkg, with_metadata_table=with_metadata_table)
    project = QgsProject()
    layers = {}
    for name in _LAYER_NAMES:
        vl = QgsVectorLayer(f"{gpkg}|layername={name}", name, "ogr")
        assert vl.isValid(), f"fixture layer {name!r} failed to load"
        project.addMapLayer(vl)
        layers[name] = vl
    return project, gpkg, layers


def _counts(layers):
    return {name: vl.featureCount() for name, vl in layers.items()}


def _uuid_values(vl):
    idx = vl.fields().indexOf("fiberq_uuid")
    if idx < 0:
        return None
    return [f.attribute(idx) for f in vl.getFeatures()]


# ---------------------------------------------------------------------------
# Ordered version comparison
# ---------------------------------------------------------------------------

def test_version_ordering(qgis_app):
    assert m._version_lt("0", "1.0")
    assert m._version_lt("0.9", "1.0")
    assert m._version_lt("1.0", "1.1")
    assert m._version_lt("1.1", "2.0")
    assert m._version_lt("1.9", "1.10")          # numeric, not lexical
    assert not m._version_lt("1.0", "1.0")
    assert not m._version_lt("1.0", "0")
    assert not m._version_lt("2.0", "1.1")
    assert m._version_eq("1", "1.0")             # padded equality
    assert m._version_eq("1.0", "1.0")
    assert not m._version_eq("1.0", "1.1")


# ---------------------------------------------------------------------------
# The fixture itself represents a genuine pre-1.0 project
# ---------------------------------------------------------------------------

def test_fixture_is_pre_uuid(qgis_app, tmp_path):
    project, _gpkg, layers = _build_and_load(tmp_path)
    for name, vl in layers.items():
        assert vl.fields().indexOf("fiberq_uuid") < 0, f"{name} unexpectedly has uuid"
        assert vl.featureCount() > 0, name
    # No marker anywhere -> reads as baseline "0".
    assert sv.read_project_schema_version(project) == sv.BASELINE_VERSION


# ---------------------------------------------------------------------------
# Upgrade: adds + backfills uuid on every layer and stamps the marker
# ---------------------------------------------------------------------------

def test_run_migrations_upgrades_old_project(qgis_app, tmp_path):
    project, _gpkg, layers = _build_and_load(tmp_path)
    before = _counts(layers)
    assert sv.needs_upgrade(project) is True

    report = m.run_migrations(project)

    assert report.ran is True
    assert report.from_version == sv.BASELINE_VERSION
    assert report.to_version == sv.SCHEMA_VERSION
    assert "uuid-identity" in report.steps
    assert not report.errors

    # Marker advanced to current.
    assert sv.read_project_schema_version(project) == sv.SCHEMA_VERSION
    assert sv.needs_upgrade(project) is False

    # Every layer now has a fully-populated, unique fiberq_uuid.
    for name, vl in layers.items():
        idx = vl.fields().indexOf("fiberq_uuid")
        assert idx >= 0, f"{name} missing uuid field after migration"
        vals = _uuid_values(vl)
        assert all(v not in (None, "") and str(v).strip() for v in vals), name
        assert len(set(vals)) == len(vals), f"{name} uuids not unique"

    # Lossless: no features gained or lost.
    assert _counts(layers) == before


def test_migration_preserves_existing_attributes(qgis_app, tmp_path):
    """Adding the uuid column must not disturb existing attribute values."""
    project, _gpkg, layers = _build_and_load(tmp_path)
    watched = ("naziv", "kapacitet", "stanje")
    odf = layers["ODF"]
    before = {
        f.id(): {k: f[k] for k in watched} for f in odf.getFeatures()
    }

    m.run_migrations(project)

    after = {
        f.id(): {k: f[k] for k in watched} for f in odf.getFeatures()
    }
    assert after == before


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_run_migrations_is_idempotent(qgis_app, tmp_path):
    project, _gpkg, layers = _build_and_load(tmp_path)
    m.run_migrations(project)
    first = {name: _uuid_values(vl) for name, vl in layers.items()}
    # Guard against a vacuous pass: the values compared must actually be populated.
    for name, vals in first.items():
        assert vals and all(v not in (None, "") and str(v).strip() for v in vals), name

    # Second run: marker already current -> no-op, no re-assignment.
    report2 = m.run_migrations(project)
    assert report2.ran is False
    assert report2.details == {}
    second = {name: _uuid_values(vl) for name, vl in layers.items()}
    assert second == first


def test_uuid_backfill_is_idempotent(qgis_app, tmp_path):
    """The underlying uuid step is a no-op on a second pass (data-level)."""
    from fiberq.utils.uuid_utils import migrate_project_uuids

    project, _gpkg, _layers = _build_and_load(tmp_path)
    first = migrate_project_uuids(project)
    assert sum(first.values()) > 0          # real work the first time
    second = migrate_project_uuids(project)
    assert second == {}                      # nothing left to do


# ---------------------------------------------------------------------------
# Guards: current project is a no-op; a newer project is never downgraded
# ---------------------------------------------------------------------------

def test_current_project_is_noop(qgis_app):
    p = QgsProject()
    sv.mark_project_current(p)
    report = m.run_migrations(p)
    assert report.ran is False
    assert report.details == {}
    assert not report.errors


def test_newer_project_is_not_downgraded(qgis_app):
    p = QgsProject()
    sv.write_project_schema_version("99.0", p)
    report = m.run_migrations(p)
    assert report.ran is False
    assert report.errors                     # refused, with a reason
    assert sv.read_project_schema_version(p) == "99.0"   # left untouched


def test_malformed_marker_is_not_migrated(qgis_app):
    """A foreign/decorated marker must not be coerced (which would bypass the
    newer-than-plugin guard and silently downgrade a real newer project)."""
    p = QgsProject()
    sv.write_project_schema_version("v2.0", p)
    report = m.run_migrations(p)
    assert report.ran is False
    assert report.errors
    assert sv.read_project_schema_version(p) == "v2.0"   # untouched


def test_equal_but_aliased_marker_is_canonicalised(qgis_app):
    """A marker equal-but-not-identical to current ("1" vs "1.0") converges to
    the canonical string so needs_upgrade() and the runner agree."""
    p = QgsProject()
    sv.write_project_schema_version("1", p)
    report = m.run_migrations(p)
    assert report.ran is False
    assert not report.errors
    assert sv.read_project_schema_version(p) == sv.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Durability: prove the backfill reaches disk, not just the edit buffer
# ---------------------------------------------------------------------------

def test_migration_persists_to_disk(qgis_app, tmp_path):
    project, gpkg, layers = _build_and_load(tmp_path)
    before_counts = _counts(layers)
    before_vals = {
        name: sorted(str(f[_CHECK_FIELD[name]]) for f in layers[name].getFeatures())
        for name in _LAYER_NAMES
    }

    report = m.run_migrations(project)
    assert report.ran is True

    # Release the live handles and read the file back with fresh layers -- only a
    # disk re-read proves the commit actually persisted (a lost commit would still
    # look complete through the original layers' edit buffer).
    project.removeAllMapLayers()
    for name in _LAYER_NAMES:
        vl = QgsVectorLayer(f"{gpkg}|layername={name}", name, "ogr")
        assert vl.isValid(), name
        idx = vl.fields().indexOf("fiberq_uuid")
        assert idx >= 0, f"{name}: fiberq_uuid not persisted to disk"
        vals = [f.attribute(idx) for f in vl.getFeatures()]
        assert vals, name
        assert all(v not in (None, "") and str(v).strip() for v in vals), \
            f"{name}: NULL/empty uuid on disk"
        assert len(set(vals)) == len(vals), f"{name}: uuids not unique on disk"
        assert vl.featureCount() == before_counts[name], f"{name}: feature count changed"
        after = sorted(str(f[_CHECK_FIELD[name]]) for f in vl.getFeatures())
        assert after == before_vals[name], f"{name}: existing values not preserved"


# ---------------------------------------------------------------------------
# Partial-failure: a step that can't persist must NOT stamp the marker
# ---------------------------------------------------------------------------

def test_failed_step_withholds_stamp(qgis_app, monkeypatch):
    """If a migration step fails, run_migrations must not stamp current, so the
    next load retries instead of leaving the marker lying."""
    p = QgsProject()
    sv.write_project_schema_version("0", p)

    def _boom(project=None):
        raise RuntimeError("simulated locked layer")

    monkeypatch.setattr(m, "MIGRATIONS",
                        [m.Migration("1.0", "boom", "simulated failure", _boom)])
    report = m.run_migrations(p)
    assert report.ran is False
    assert report.errors and "boom" in report.errors[0]
    assert sv.read_project_schema_version(p) == "0"   # NOT stamped -> retried


def test_uuid_migration_raises_on_failed_layer(qgis_app, tmp_path, monkeypatch):
    """migrate_project_uuids surfaces a failed layer (no silent partial success)."""
    from fiberq.utils import uuid_utils

    project, _gpkg, _layers = _build_and_load(tmp_path)
    monkeypatch.setattr(uuid_utils, "ensure_uuid_field", lambda layer: False)
    with pytest.raises(uuid_utils.UuidMigrationError):
        uuid_utils.migrate_project_uuids(project)


# ---------------------------------------------------------------------------
# The migration chain is well-formed (guards a future SCHEMA_VERSION bump)
# ---------------------------------------------------------------------------

def test_migration_chain_wellformed(qgis_app):
    targets = [s.to_version for s in m.MIGRATIONS]
    assert all(m._is_valid_version(t) for t in targets)
    # No two steps target the same (semantic) version.
    for i in range(len(targets)):
        for j in range(i + 1, len(targets)):
            assert not m._version_eq(targets[i], targets[j]), "duplicate step target"
    # No step targets a version beyond the current schema.
    for t in targets:
        assert not m._version_lt(sv.SCHEMA_VERSION, t), f"step targets {t} > current"
