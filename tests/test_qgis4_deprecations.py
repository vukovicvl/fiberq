"""Calls that print into QGIS's Python warning log must not reappear in the package.

FiberQ targets QGIS 3.22 LTR through QGIS 4 / Qt6. A deprecated call still
works, so nothing fails -- it emits a warning into the Python warning log,
which is exactly where it goes unnoticed until the removal lands and the
plugin breaks for everyone at once, and where it buries a warning that matters.

Found in field QA:

* QGIS 4.2: the locator dialog logged a traceback on every search because
  QgsCoordinateReferenceSystem(4326) is deprecated. The authid string form
  works identically on both QGIS 3 and 4.
* QGIS 3.40, the v1.6.0 QA: "QgsField constructor is deprecated", once for every
  place FiberQ builds a field, and "saveStyleToDatabase() is deprecated" from
  auto-save. ``fiberq/utils/compat.py`` picks the call each QGIS takes, so it is
  the one file allowed the old ones.
* QGIS 4.2, the v1.6.0 QA's suite logs: "unclosed database", from a sqlite3
  connection whose own ``with`` was taken to close it.
"""
import pathlib
import re

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "fiberq"

#: The module that decides between an old call and its replacement.
COMPAT = "utils/compat.py"


class Rule:
    """A pattern, what to write instead, and a line each way to prove it fires."""

    def __init__(self, name, pattern, advice, caught, passed, allowed=()):
        self.name = name
        self.pattern = re.compile(pattern)
        self.advice = advice
        self.caught = caught
        self.passed = passed
        self.allowed = allowed


#: Keep the advice actionable.
FORBIDDEN = [
    Rule("crs-integer",
         r"QgsCoordinateReferenceSystem\(\s*\d",
         "QgsCoordinateReferenceSystem('EPSG:<code>') -- the integer "
         "constructor is deprecated in QGIS 4",
         "crs = QgsCoordinateReferenceSystem(4326)",
         "crs = QgsCoordinateReferenceSystem('EPSG:4326')"),
    Rule("field-qvariant",
         r"\bQVariant\.(String|Int|LongLong|Double|Bool)\b",
         "FieldType.<type> from fiberq.utils.compat -- QgsField's QVariant "
         "constructor prints 'QgsField constructor is deprecated' on QGIS 3.38-3.44",
         'field = QgsField("naziv", QVariant.String)',
         'field = QgsField("naziv", FieldType.String)',
         allowed=(COMPAT,)),
    Rule("style-v1",
         r"\.saveStyleToDatabase\(",
         "save_style_to_database() from fiberq.utils.compat -- deprecated from QGIS 3.40",
         'problem = layer.saveStyleToDatabase("default", "", True, "")',
         'problem = save_style_to_database(layer, "default", "", True, "")',
         allowed=(COMPAT,)),
    Rule("sqlite-with",
         r"\bwith\s+sqlite3\.connect\(",
         "with closing(sqlite3.connect(...)) as conn: -- a connection's own `with` "
         "commits but never closes, and Python 3.13 (QGIS 4) logs 'unclosed database'",
         "with sqlite3.connect(path) as conn:",
         "with closing(sqlite3.connect(path)) as conn:"),
]


def test_no_call_that_prints_a_warning():
    problems = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            for rule in FORBIDDEN:
                if relative not in rule.allowed and rule.pattern.search(line):
                    problems.append(
                        f"fiberq/{relative}:{number}: {line.strip()}\n"
                        f"    use {rule.advice}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("rule", FORBIDDEN, ids=lambda rule: rule.name)
def test_the_scan_would_catch_a_reintroduction(rule):
    """A check that has never fired is not a check -- and that holds for every rule."""
    assert rule.pattern.search(rule.caught)
    assert not rule.pattern.search(rule.passed)


def test_the_exemption_names_a_real_file():
    """An exemption for a file that moved would exempt nothing and say nothing."""
    for rule in FORBIDDEN:
        for relative in rule.allowed:
            assert (PACKAGE / relative).is_file(), relative
