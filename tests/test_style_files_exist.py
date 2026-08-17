"""Every style file the code names must exist, with exactly that spelling.

Style lookups go through hardcoded filenames, and the shipped names do not all
match their layer names in case -- the "Patch panel" layer loads "Patch
Panel.qml", the "Service Area" layer loads "Service area.qml". That mapping is
deliberate, but it is one rename away from breaking, and it breaks *by platform*:
Windows and macOS resolve a mismatched name happily, Linux does not, so the
style silently fails to apply for Linux users only.

The comparison is against the directory listing rather than os.path.exists,
because on a case-insensitive filesystem exists() would answer True for a name
that fails on Linux -- the test would pass everywhere except where it matters.
"""
import pathlib
import re

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "fiberq"
STYLES = PACKAGE / "styles"

_QML = re.compile(r'["\']([^"\']+\.qml)["\']')


def _referenced():
    """``{filename: [source file, ...]}`` for every .qml named in the package."""
    found = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        for name in _QML.findall(path.read_text(encoding="utf-8")):
            found.setdefault(name, []).append(path.name)
    return found


def test_every_referenced_style_exists_with_that_exact_name():
    on_disk = {p.name for p in STYLES.glob("*.qml")}
    missing = {name: where for name, where in _referenced().items()
               if name not in on_disk}
    assert not missing, (
        f"named in code but not in fiberq/styles/ (case-sensitively): {missing}")


def test_the_scan_finds_the_styles_it_should():
    """Guards the test above from passing because the regex matched nothing."""
    referenced = _referenced()
    assert len(referenced) >= 10, referenced
    assert "Fiber break.qml" in referenced


def test_a_wrong_case_name_would_be_caught():
    """The check has to be case-sensitive to be worth anything."""
    on_disk = {p.name for p in STYLES.glob("*.qml")}
    assert "Patch Panel.qml" in on_disk
    assert "Patch panel.qml" not in on_disk   # the layer name, not the file name
