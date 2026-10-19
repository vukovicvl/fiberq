"""docs/interchange-format.md names every table and column the code writes.

WP4 item U20 (unclaimed). The specification is the published contract a second
tool is built from. Until FiberQ 1.6.0 its text had drifted from the code in
six ways (spec section 13), three of them in what this file checks:
- the section 3 tree left out ``fq_path_stop``;
- section 6.2 called ``fq_container_slot.slot_index`` ``index``;
- ``fq_fiber_connection``'s column list left out the two advisory colour columns.
Nothing failed, because the only check (``test_interchange.py``) asked whether
each table's name appears somewhere on the page.

These tests read the page the way an implementer does: the section 3 tree, the
section 6.1 type codes, the ``fq_x(a, b)`` signatures, the lines of back-quoted
column names under a table's name, the section 7 metadata table, and every
back-quoted ``fq_*`` name in running prose. What they compare against comes from the code
itself: the DDL run in an in-memory SQLite database, ``LAYER_TO_TYPE``,
``build_metadata()``, and the writer's ``STAMP_COLUMNS`` read from its source.
So this file keeps no second list of its own to fall behind. Like
``test_interchange.py`` it loads the pure-data module by path: no QGIS,
milliseconds.
"""
import ast
import contextlib
import importlib.util
import pathlib
import re
import sqlite3

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SPEC = REPO / "docs" / "interchange-format.md"


def _load(name, relpath):
    """Import a pure-data module by path, bypassing the QGIS-importing package."""
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ic = _load("fq_interchange_doc", "fiberq/core/interchange.py")

#: A branch of the section 3 container tree: ``├── fq_relation``.
TREE_BRANCH = re.compile(r"[├└]── (fq_\w+)")
#: A table written as a signature: ```fq_relation(uuid, name, category)```.
SIGNATURE = re.compile(r"`(fq_\w+)\(([^)`]*)\)`")
#: A line that is nothing but back-quoted names, joined by commas or middle dots.
COLUMN_LINE = re.compile(r"^\s*`\w+`(\s*[,·]\s*`\w+`)*\s*[,·]?\s*$")
#: A table named in back quotes anywhere in a line.
TABLE_NAME = re.compile(r"`(fq_\w+)`")
#: A row of the section 7 table: ``| `format` | yes | ...``.
METADATA_ROW = re.compile(r"^\|\s*`(\w+)`\s*\|\s*(yes|no)\s*\|")
#: A row of the section 6.1 table: ``| `cable.aerial` | LineString | ...``.
TYPE_ROW = re.compile(r"^\|\s*`([a-z_.]+)`\s*\|")


def _lines():
    return SPEC.read_text(encoding="utf-8").splitlines()


def _code_columns():
    """Each side-car table's columns, in order, as the DDL creates them."""
    with contextlib.closing(sqlite3.connect(":memory:")) as conn:
        for ddl in ic.SIDECAR_DDL:
            conn.execute(ddl)
        return {table: [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
                for table in ic.SIDECAR_TABLES}


def _tree_tables(lines):
    """The ``fq_*`` branches of the section 3 tree, in page order."""
    start = lines.index("design.gpkg")
    end = lines.index("```", start)
    return [m.group(1) for line in lines[start:end] for m in TREE_BRANCH.finditer(line)]


def _documented_columns(lines):
    """Every column list on the page, as ``(table, [columns])`` in page order.

    A signature names its own table. A run of column-name lines belongs to the
    last table named before it, which is how the page reads: the table's name in
    bold, then its columns on the next line. A run with no table before it is
    returned with ``None``, so a test fails on it rather than skipping it.
    """
    found = []
    table = None
    i = 0
    while i < len(lines):
        if COLUMN_LINE.match(lines[i]):
            columns = []
            while i < len(lines) and COLUMN_LINE.match(lines[i]):
                columns += re.findall(r"`(\w+)`", lines[i])
                i += 1
            found.append((table, columns))
            continue
        for match in SIGNATURE.finditer(lines[i]):
            found.append((match.group(1), [c.strip() for c in match.group(2).split(",")]))
        named = TABLE_NAME.findall(lines[i])
        if named:
            table = named[-1]
        i += 1
    return found


def _type_codes(lines):
    """The codes in the section 6.1 table, in page order: the rows below its header."""
    start = lines.index("### 6.1 Element type codes")
    rule = next(i for i in range(start, len(lines)) if lines[i].startswith("|---"))
    codes = []
    for line in lines[rule + 1:]:
        match = TYPE_ROW.match(line)
        if not match:
            break
        codes.append(match.group(1))
    return codes


def _stamp_columns():
    """The columns the writer adds to every bundle feature (``STAMP_COLUMNS``).

    Read from the source rather than imported: ``interchange_bundle`` imports QGIS.
    """
    tree = ast.parse((REPO / "fiberq" / "core" / "interchange_bundle.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "STAMP_COLUMNS"
                for target in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("STAMP_COLUMNS is no longer a literal in interchange_bundle.py")


def _metadata_rows(lines):
    """Section 7's table as ``{key: required}``."""
    start = lines.index("## 7. Bundle metadata")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    rows = {}
    for line in lines[start:end]:
        match = METADATA_ROW.match(line)
        if match:
            rows[match.group(1)] = match.group(2) == "yes"
    return rows


def test_the_page_is_read_at_all():
    """The checks below prove nothing if the parsers find nothing to check."""
    lines = _lines()
    assert len(_tree_tables(lines)) > 5
    assert len(_documented_columns(lines)) > 5
    assert len(_metadata_rows(lines)) > 5
    assert len(_type_codes(lines)) > 10
    assert all(_code_columns().values()), "a side-car table without DDL"
    assert "fq_type" in _stamp_columns()


def test_the_type_code_table_lists_every_code_the_plugin_writes():
    """Section 6.1's table against ``LAYER_TO_TYPE``, once each."""
    codes = _type_codes(_lines())
    assert len(codes) == len(set(codes)), "a code is listed twice"
    assert sorted(codes) == sorted({fq_type for fq_type, _ in ic.LAYER_TO_TYPE.values()})


def test_the_container_tree_lists_every_side_car_table():
    """Section 3 is the page's map of a bundle. It used to show eight tables."""
    assert _tree_tables(_lines()) == list(ic.SIDECAR_TABLES)


@pytest.mark.parametrize("table", ic.SIDECAR_TABLES)
def test_each_side_car_table_is_documented_once_with_the_columns_the_code_creates(table):
    documented = [columns for name, columns in _documented_columns(_lines()) if name == table]
    assert documented == [_code_columns()[table]]


def test_the_page_documents_no_table_the_code_does_not_create():
    named = {name for name, _ in _documented_columns(_lines())}
    assert named <= set(ic.SIDECAR_TABLES), named - set(ic.SIDECAR_TABLES)


def test_the_required_metadata_keys_are_the_ones_the_writer_emits():
    rows = _metadata_rows(_lines())
    written = ic.build_metadata("1.0", 3857, "1.6.0", "2026-10-19T00:00:00")
    assert {key for key, required in rows.items() if required} == set(written)
    assert set(rows) <= ic.OWNED_METADATA_KEYS, set(rows) - ic.OWNED_METADATA_KEYS


def test_every_fq_name_on_the_page_is_a_table_or_a_column_the_format_has():
    """Running prose too: a typo or an invented table (``fq_tray``) in a sentence
    misleads an implementer as much as one in a column list."""
    known = set(ic.SIDECAR_TABLES) | {c for c in _stamp_columns() if c.startswith("fq_")}
    named = set(TABLE_NAME.findall(SPEC.read_text(encoding="utf-8")))
    assert named <= known, sorted(named - known)
