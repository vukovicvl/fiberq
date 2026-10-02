"""The Qt6 checker seeds must stay broken.

`make qt6-check` runs the checker plugins.qgis.org runs (`pyqt5_to_pyqt6.py
--dry_run`) twice: over `fiberq/`, which must report nothing, and over
`tests/qt6_seed/`, which must report at least four findings. The second run is
what proves the gate can still see a problem -- the checker writes findings to a
log and exits 0 either way, so a gate reading only the exit code would go
quietly green.

That self-test is worth nothing if the seeds get tidied up. They look like
mistakes, because they are mistakes, so this test is the note that says they are
deliberate -- in a form that fails the build rather than hoping the reader finds
the README.
"""
import pathlib

SEED_DIR = pathlib.Path(__file__).resolve().parent / "qt6_seed"

#: file -> a substring that must survive, and why it is seeded.
SEEDS = {
    "seed_imports.py": ("from PyQt5.", "PyQt5 imported directly, not via qgis.PyQt"),
    "seed_enums.py": ("Qt.AlignLeft", "unscoped Qt enum"),
    "seed_exec.py": (".exec_()", "exec_(), renamed to exec() in Qt6"),
}


def test_seed_files_exist():
    assert SEED_DIR.is_dir(), f"{SEED_DIR} is missing -- make qt6-check needs it"
    found = {path.name for path in SEED_DIR.glob("*.py")}
    assert found == set(SEEDS), (
        "the seed set changed; update SEEDS (and the README table) to match, "
        f"found {sorted(found)}")


def test_seeds_are_still_broken():
    """Each seed still carries the mistake it was written to carry."""
    problems = []
    for name, (needle, why) in sorted(SEEDS.items()):
        path = SEED_DIR / name
        if needle not in path.read_text(encoding="utf-8"):
            problems.append(
                f"tests/qt6_seed/{name}: '{needle}' is gone, so the "
                f"self-test no longer covers {why}. These files are "
                "deliberately Qt5-style -- see tests/qt6_seed/README.md.")
    assert not problems, "\n".join(problems)


def test_seeds_cover_at_least_four_findings():
    """The target requires >= 4 findings; the seeds must be able to produce them."""
    unscoped = (SEED_DIR / "seed_enums.py").read_text(encoding="utf-8")
    enum_findings = sum(
        unscoped.count(token) for token in
        ("Qt.AlignLeft", "Qt.AlignVCenter", "QMessageBox.Yes", "QMessageBox.No",
         "QgsWkbTypes.Point", "QgsMapLayer.VectorLayer"))
    imports = (SEED_DIR / "seed_imports.py").read_text(encoding="utf-8")
    import_findings = imports.count("from PyQt5.")
    exec_findings = (SEED_DIR / "seed_exec.py").read_text(encoding="utf-8").count(".exec_()")
    assert enum_findings + import_findings + exec_findings >= 4
