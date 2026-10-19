"""The translator guide must not misdescribe the work it is asking for.

docs/TRANSLATING.md is aimed at a volunteer donating their time, so a wrong
figure in it is worse than a wrong figure in developer docs. It said "169
strings" for months while the catalogue grew to 306 through WP2 -- someone would
have committed to a job nearly twice the size they were told.

The guide now states an approximate figure on purpose. This checks it is still
approximately right, with enough slack that ordinary string additions do not
fail the build -- only a genuinely misleading number does.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
GUIDE = REPO / "docs" / "TRANSLATING.md"
CATALOGUES = sorted((REPO / "fiberq" / "i18n").glob("*.ts"))

#: How far the stated figure may drift before it misleads.
TOLERANCE = 0.35


def _untranslated(path):
    return len(re.findall(r'type="unfinished"', path.read_text(encoding="utf-8")))


def test_the_stated_size_is_approximately_true():
    text = GUIDE.read_text(encoding="utf-8")
    match = re.search(r"around \*\*(\d+) strings\*\*", text)
    assert match, 'TRANSLATING.md no longer states a size as "around **N strings**"'

    stated = int(match.group(1))
    actual = max(_untranslated(p) for p in CATALOGUES)
    drift = abs(stated - actual) / actual

    assert drift <= TOLERANCE, (
        f"TRANSLATING.md says ~{stated} strings; the catalogues have {actual} "
        f"untranslated ({drift:.0%} out). Update the guide.")


def test_no_exact_count_is_repeated_through_the_guide():
    """The original bug was one number hardcoded in six places, so five of them
    were missed. Prose should say "every entry", not a figure."""
    text = GUIDE.read_text(encoding="utf-8")
    actual = max(_untranslated(p) for p in CATALOGUES)
    for stale in ("169", str(actual)):
        # One statement of the approximate size is fine; a scatter of exact
        # counts through the prose is what goes stale.
        assert text.count(stale) <= 1, f"{stale!r} appears {text.count(stale)} times"


def test_the_guide_is_reachable_from_the_readme():
    """A guide nobody can find does not recruit anybody."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "docs/TRANSLATING.md" in readme


def test_a_volunteer_can_reach_the_guide_from_the_issue_template():
    """The template does not link the guide directly -- it points at
    CONTRIBUTING.md, which points at the guide. Both hops must hold, or the
    step-by-step instructions are orphaned and nobody finds them."""
    template = REPO / ".github" / "ISSUE_TEMPLATE" / "translation.yml"
    assert template.exists(), "the translation issue template is missing"

    text = template.read_text(encoding="utf-8")
    assert "CONTRIBUTING.md#translations" in text, (
        "the issue template no longer points at CONTRIBUTING's Translations section")

    contributing = (REPO / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "## Translations" in contributing
    assert "docs/TRANSLATING.md" in contributing, (
        "CONTRIBUTING.md no longer links the step-by-step guide")


def _compile_recipe():
    """The shell recipe of ``make i18n-compile``, as one string."""
    lines = (REPO / "Makefile").read_text(encoding="utf-8").splitlines()
    start = lines.index("i18n-compile:")
    recipe = []
    for line in lines[start + 1:]:
        if not line.startswith("\t"):
            break
        recipe.append(line)
    return "\n".join(recipe)


def test_the_build_ships_only_finished_translations():
    """The guide tells a volunteer that an entry still marked unfinished is not
    shipped. Plain lrelease compiles those too, so the promise holds only while
    the build passes -nounfinished."""
    recipe = _compile_recipe()
    invocation = [line for line in recipe.splitlines() if line.strip().startswith('"$$lr"')]
    assert invocation, "i18n-compile no longer runs the lrelease it found"
    assert all("-nounfinished" in line for line in invocation), invocation


def test_an_unfinished_draft_does_not_reach_the_compiled_catalogue(tmp_path):
    """The flag does what the guide says, with whichever lrelease is installed."""
    import shutil
    import subprocess

    import pytest

    lrelease = next((shutil.which(name) or name for name in (
        "lrelease", "lrelease-qt6", "lrelease6", "lrelease-qt5",
        "/usr/lib/qt6/bin/lrelease", "/usr/lib/qt5/bin/lrelease")
        if shutil.which(name) or pathlib.Path(name).is_file()), None)
    if lrelease is None:
        pytest.skip("no lrelease in this environment")
    source = tmp_path / "fiberq_xx.ts"
    source.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
        '<TS version="2.1" language="fr" sourcelanguage="en"><context><name>FiberQ</name>'
        '<message><source>Finished</source><translation>Fini</translation></message>'
        '<message><source>Draft</source>'
        '<translation type="unfinished">Brouillon</translation></message>'
        '</context></TS>\n', encoding="utf-8")
    compiled = tmp_path / "fiberq_xx.qm"
    subprocess.run([lrelease, "-nounfinished", str(source), "-qm", str(compiled)],
                   check=True, capture_output=True)
    text = compiled.read_bytes().decode("utf-16-be", "ignore")
    assert "Fini" in text
    assert "Brouillon" not in text
