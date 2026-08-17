"""Every safe_format() call site must pass exactly the placeholders it needs.

The v1.4.0 i18n sweep put ``safe_format(self.tr(src), src, ...)`` into roughly
thirty UI files. ``safe_format`` deliberately never raises -- a bad call site
would take down toolbar construction if it did -- so a missing keyword shows the
user a literal ``{count}`` in a label instead of crashing. Nothing fails, no test
notices, and the defect ships.

That makes it exactly the class of bug worth catching statically: the source
string is a literal at the call site, so the required placeholders and the
supplied keywords are both known without running QGIS. This replaces opening
every panel by hand.

Scoping matters. ``src`` is reused in nearly every method, so a source argument
given as a name resolves to the nearest preceding assignment inside the *same*
function body -- never a module-level or sibling-method one.
"""
import ast
import pathlib
import string

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "fiberq"

#: The wrapper in validation_rules.py forwards to fiberq.i18n.safe_format.
_CALL_NAMES = {"safe_format", "_safe_format"}


def _placeholders(text):
    """The field names ``str.format`` would require for ``text``."""
    names = set()
    for _literal, field, _spec, _conv in string.Formatter().parse(text):
        if field:
            names.add(field.split(".")[0].split("[")[0])
    return names


def _literal_of(node):
    """The string a source argument denotes directly, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call):  # QT_TRANSLATE_NOOP('Context', '...')
        args = [a for a in node.args if isinstance(a, ast.Constant)]
        if args and isinstance(args[-1].value, str):
            return args[-1].value
    return None


def _own_nodes(scope):
    """Nodes belonging to ``scope`` itself, excluding nested function bodies."""
    nested = set()
    for node in ast.walk(scope):
        if node is scope:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            nested.update(id(n) for n in ast.walk(node))
    return [n for n in ast.walk(scope) if id(n) not in nested]


def _scan(path):
    """``[(lineno, source, required, supplied)]`` for mismatched call sites."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    scopes = [tree]
    scopes += [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    problems = []
    for scope in scopes:
        nodes = _own_nodes(scope)
        assigns = []  # (lineno, name, literal)
        for node in nodes:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target, value = node.targets[0], _literal_of(node.value)
            if isinstance(target, ast.Name) and value is not None:
                assigns.append((node.lineno, target.id, value))

        for node in nodes:
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in _CALL_NAMES or len(node.args) < 2:
                continue
            if any(kw.arg is None for kw in node.keywords):
                continue  # **kwargs splat: the wrapper itself, not a call site
            argument = node.args[1]
            source = _literal_of(argument)
            if source is None and isinstance(argument, ast.Name):
                prior = [a for a in assigns
                         if a[1] == argument.id and a[0] <= node.lineno]
                if prior:
                    source = max(prior)[2]
            if source is None:
                continue  # a forwarded parameter; nothing to compare
            required = _placeholders(source)
            supplied = {kw.arg for kw in node.keywords}
            if required != supplied:
                problems.append((node.lineno, source,
                                 sorted(required), sorted(supplied)))
    return problems


def test_every_safe_format_call_site_matches_its_source():
    problems = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for lineno, source, required, supplied in _scan(path):
            problems.append(
                f"{path.relative_to(PACKAGE.parent)}:{lineno} {source!r} "
                f"needs {required}, got {supplied}")
    assert not problems, "\n".join(problems)


def test_the_scan_detects_a_seeded_mismatch(tmp_path):
    """A check that has never fired is not a check.

    Guards the scanner's own scoping: the decoy assignment to ``src`` in a
    sibling function must not be what the call site resolves against.
    """
    module = tmp_path / "seeded.py"
    module.write_text(
        "def decoy(self):\n"
        "    src = QT_TRANSLATE_NOOP('C', 'Fine {a}')\n"
        "    return safe_format(self.tr(src), src, a=1)\n"
        "\n"
        "def missing(self):\n"
        "    src = QT_TRANSLATE_NOOP('C', 'Placed {count} of {total}')\n"
        "    return safe_format(self.tr(src), src, count=1)\n"
        "\n"
        "def stray(self):\n"
        "    src = QT_TRANSLATE_NOOP('C', 'Saved {path}')\n"
        "    return safe_format(self.tr(src), src, path=1, extra=2)\n",
        encoding="utf-8")

    found = {lineno: (req, sup) for lineno, _src, req, sup in _scan(module)}
    assert sorted(found) == [7, 11], found
    assert found[7] == (["count", "total"], ["count"])
    assert found[11] == (["path"], ["extra", "path"])
