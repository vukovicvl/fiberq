"""Shipped layer styles must not name a font that only exists on one platform.

QGIS logs "Loading layer X : Font <name> not available on system" for every
layer whose style names a missing family, then silently substitutes another
font -- so labels render at the wrong metrics and the user gets a wall of
warnings on every project load.

Found in QGIS 3.40 QA on Linux: fifteen styles carried "MS Shell Dlg 2" (a
Windows alias) and one carried "Open Sans" (a Google font). Neither resolves on
a stock Linux install, and "MS Shell Dlg 2" is meaningless on macOS too.

"Sans Serif" is one of Qt's generic families, so it resolves on every platform;
it is also QGIS 4's own default. Verified against QgsFontUtils in both the QGIS
3 and QGIS 4 containers, where Arial, Helvetica and Open Sans all fail.
"""
import pathlib
import re

STYLES = pathlib.Path(__file__).resolve().parent.parent / "fiberq" / "styles"

#: Qt generic families, guaranteed to resolve to something everywhere.
PORTABLE = {"Sans Serif", "Serif", "Monospace"}

_FAMILY = re.compile(r'fontFamily="([^"]*)"')


def _families():
    """``{family: [style file, ...]}`` over every shipped .qml."""
    found = {}
    for path in sorted(STYLES.glob("*.qml")):
        for family in _FAMILY.findall(path.read_text(encoding="utf-8")):
            found.setdefault(family, []).append(path.name)
    return found


def test_every_shipped_style_uses_a_portable_font():
    offenders = {fam: files for fam, files in _families().items()
                 if fam and fam not in PORTABLE}
    assert not offenders, (
        "styles name a platform-specific font; use one of "
        f"{sorted(PORTABLE)}: {offenders}")


def test_the_styles_actually_declare_a_font():
    """Guards the test above from passing because it found nothing to check."""
    families = _families()
    assert families, "no fontFamily= found in any shipped style"
    assert sum(len(f) for f in families.values()) >= 16


def test_the_named_families_resolve_in_this_qgis(qgis_app):
    """The real check: ask QGIS, not a hardcoded list.

    Runs in both CI images, so a family that resolves on QGIS 4 but not on
    QGIS 3 (or on one distro but not another) fails here rather than in a
    user's log.
    """
    from qgis.core import QgsFontUtils

    unresolved = []
    for family in _families():
        if not family:
            continue
        matched, _exact = QgsFontUtils.fontFamilyMatchOnSystem(family)
        if not matched:
            unresolved.append(family)
    assert not unresolved, f"QGIS cannot resolve: {unresolved}"
