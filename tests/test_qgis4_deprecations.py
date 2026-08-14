"""Constructors QGIS 4 has deprecated must not reappear in the package.

FiberQ targets QGIS 3.22 LTR through QGIS 4 / Qt6. A deprecated call still
works, so nothing fails -- it emits a DeprecationWarning into the Python
warning log, which is exactly where it goes unnoticed until the removal lands
and the plugin breaks for everyone at once.

Found in field QA on QGIS 4.2: the locator dialog logged a traceback on every
search because QgsCoordinateReferenceSystem(4326) is deprecated. The authid
string form works identically on both QGIS 3 and 4.
"""
import pathlib
import re

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "fiberq"

#: pattern -> what to write instead. Keep the message actionable.
FORBIDDEN = {
    r"QgsCoordinateReferenceSystem\(\s*\d":
        "QgsCoordinateReferenceSystem('EPSG:<code>') -- the integer "
        "constructor is deprecated in QGIS 4",
}


def test_no_deprecated_qgis4_constructors():
    problems = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern, advice in FORBIDDEN.items():
                if re.search(pattern, line):
                    problems.append(
                        f"{path.relative_to(PACKAGE.parent)}:{number}: "
                        f"{line.strip()}\n    use {advice}")
    assert not problems, "\n".join(problems)


def test_the_scan_would_catch_a_reintroduction(tmp_path):
    """A check that has never fired is not a check."""
    seeded = tmp_path / "seeded.py"
    seeded.write_text("crs = QgsCoordinateReferenceSystem(4326)\n", encoding="utf-8")
    pattern = next(iter(FORBIDDEN))
    assert re.search(pattern, seeded.read_text(encoding="utf-8"))
    assert not re.search(pattern, "crs = QgsCoordinateReferenceSystem('EPSG:4326')")
