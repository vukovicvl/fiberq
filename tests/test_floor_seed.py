"""The other half of `make floor-check`'s self-test.

``tests/floor_seed/`` holds code that is deliberately invalid on the plugin's
declared floor, and ``make floor-check`` fails if it cannot find at least three
findings there. That protects against the gate breaking. This file protects
against the *seeds* being tidied away -- someone running a formatter, or
"fixing" a file that looks broken, would leave the gate reporting zero and still
green, and nothing would be watching the floor again.

Same arrangement as ``tests/test_qt6_seed.py`` for the Qt6 checker's seeds, and
for the same reason.

These tests do NOT import the seeds. They cannot: two of them are syntax the
floor rejects, and on a developer Python older than 3.12 they would not parse
here either. The patterns are checked as text.
"""
import pathlib

import pytest

SEED_DIR = pathlib.Path(__file__).resolve().parent / "floor_seed"

#: file -> (substring that must be present, what it seeds)
SEEDS = {
    "seed_pep701.py": (
        """f'<h2>{_esc(_tr('Run'))}</h2>""",
        "single quotes nested inside a single-quoted f-string (PEP 701, Python 3.12+)",
    ),
    "seed_qt6_import.py": (
        "from qgis.PyQt.QtGui import QAction, QShortcut",
        "QAction/QShortcut from their Qt6 home, which QGIS 3.22's Qt5 does not have",
    ),
    "seed_walrus_py312.py": (
        "def first[T](",
        "a PEP 695 type-parameter list (Python 3.12+)",
    ),
}


def test_the_seed_directory_is_still_there():
    assert SEED_DIR.is_dir(), (
        f"{SEED_DIR} is gone. make floor-check needs it: without seeds a green run only "
        "means the gate found nothing, not that there is nothing to find.")
    assert (SEED_DIR / "README.md").is_file(), "the README explains why not to fix these"


@pytest.mark.parametrize("name", sorted(SEEDS))
def test_each_seed_still_seeds_what_it_claims(name):
    """A seed that has been 'cleaned up' stops proving anything."""
    pattern, what = SEEDS[name]
    path = SEED_DIR / name
    assert path.is_file(), f"{name} is gone -- it seeded {what}"
    text = path.read_text(encoding="utf-8")
    assert pattern in text, (
        f"{name} no longer contains the pattern it exists for ({what}). "
        f"Expected to find: {pattern!r}. Do not fix these files -- see "
        f"{SEED_DIR.name}/README.md.")


def test_the_seed_count_matches_what_the_gate_demands():
    """FLOOR_MIN_SEED in tests/floor_check.py must not outrun the seeds.

    If someone adds a seed, the floor can be raised. If someone removes one
    without lowering the minimum, `make floor-check` fails for the wrong reason
    and the next person "fixes" it by lowering the bar.
    """
    gate = (SEED_DIR.parent / "floor_check.py").read_text(encoding="utf-8")
    assert 'MIN_SEED = int(os.environ.get("FLOOR_MIN_SEED", "3"))' in gate, (
        "floor_check.py's default minimum changed. Keep it equal to the number of seeds "
        f"({len(SEEDS)}) and update this test and the README together.")
    assert len(SEEDS) == 3, "this file and floor_check.py's default must agree"
