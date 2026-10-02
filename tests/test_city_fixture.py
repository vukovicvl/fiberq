"""The WP4 benchmark dataset is a constant of the measurement, not a variable.

``tests/fixtures/make_city_project.py`` generates the project the before/after
benchmark runs on. Three properties are what make a published speed-up mean
something, and each of them is easy to break by accident:

* It is the *same* dataset. The XS content digest is pinned here, so a change
  that moves a coordinate, a laying type, a stored value or one of the project
  entries turns into a failing test rather than a quiet re-baselining of
  numbers already published.
* It is *clean*: zero validation issues, and every value in a constrained field
  inside the domain rule D1 enforces. A dataset that trips a rule measures the
  fixture instead of the plugin.
* It is *complete*: every canonical layer carries features, or a scenario
  measures an empty layer and reports a fast nothing.

Cheap on purpose. The row model is built from the schema and hashed with no
GDAL and no application, so only the validation test pays for a real project.
"""
import ast
import json
import pathlib
import sys

import pytest

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
if str(FIXTURES) not in sys.path:
    sys.path.insert(0, str(FIXTURES))

from make_city_project import DEFAULT_SEED, SIZES, build_model  # noqa: E402

#: sha256 over the *content* of size XS -- every row and the three project
#: entries -- at the default seed, with the default layer names. The number
#: ``manifest.json`` carries and the benchmark's ``--expect-digest`` compares
#: against. Taken by running the generator; identical on
#: ``qgis/qgis:3.44-trixie`` (3.44.15) and ``qgis/qgis:4.0-trixie``, over
#: repeated runs, under a forced ``PYTHONHASHSEED``, and whether it comes from
#: the model or from the manifest written beside the GeoPackage.
#:
#: Changing it is a decision, not a diff: every published "before" number was
#: measured on the dataset this digest identifies, so a new digest means the
#: baseline has to be re-run before any "after" number is comparable.
XS_DIGEST = "29b868715a0a37204df689eaa60d97e61eb17454e5a62af17397aed81bb462ab"

#: Constrained values present at XS (fields with ``options`` or a ``value_map``,
#: across 23 field/layer pairs). A floor, not the exact count: it is here so a
#: generator that stopped writing those fields fails the test instead of passing
#: it by checking nothing.
MIN_CONSTRAINED_VALUES = 1000


@pytest.fixture(scope="module")
def xs_model():
    """``(rows, meta)`` for size XS at the default seed. No GDAL, no project."""
    return build_model(SIZES["XS"], DEFAULT_SEED)


def test_xs_content_digest_is_the_pinned_constant(xs_model):
    """The generator is deterministic, and this is the dataset it produces."""
    _rows, meta = xs_model
    assert meta["seed"] == DEFAULT_SEED
    assert meta["legacy_names"] is False
    assert meta["digest"] == XS_DIGEST, (
        f"size XS at seed {meta['seed']} now digests to {meta['digest']}, not the "
        f"pinned {XS_DIGEST}. The benchmark dataset changed: re-measure the "
        f"v1.5.0 baseline before comparing anything against it, then update "
        f"XS_DIGEST here and in the generator's docstring.")


def test_the_manifest_carries_what_the_harness_reads(city_xs_dataset):
    """``bench_common`` reads the dataset's identity out of ``manifest.json``."""
    assert city_xs_dataset["digest"] == XS_DIGEST
    manifest = json.loads(
        pathlib.Path(city_xs_dataset["manifest"]).read_text(encoding="utf-8"))
    assert manifest["digest"] == XS_DIGEST
    missing = [key for key in ("size", "n", "seed", "features", "counts",
                               "layer_ids", "generator", "legacy_names")
               if key not in manifest]
    assert missing == [], (
        f"manifest.json no longer carries {missing}; bench_common.dataset_summary "
        f"and the worker's fixed-layer-id check read those keys")
    assert manifest["features"] == sum(manifest["counts"].values())
    assert sorted(manifest["layer_ids"]) == sorted(manifest["counts"])
    assert all(str(value).startswith("fiberq_bench_")
               for value in manifest["layer_ids"].values())


def test_xs_is_validation_clean(qgis_app, city_xs_dataset):
    """Zero findings, with every rule actually having run.

    "0 issues" is worth nothing on its own: a project the rules skipped reports
    the same zero. So the rules that ran are compared against the registry.
    """
    from qgis.core import QgsProject

    from fiberq.core.validation_manager import run_validation
    from fiberq.core.validation_rules import RULES

    project = QgsProject()
    assert project.read(city_xs_dataset["qgz"])
    assert len(project.mapLayers()) == len(city_xs_dataset["counts"])

    result = run_validation(project=project, plugin_version="test")
    assert result.rule_errors == []
    assert sorted(result.ran_rules) == sorted(rule.id for rule in RULES)
    assert result.skipped_rules == []
    assert result.issues == [], [(i.rule_id, i.message) for i in result.issues[:5]]


def test_every_constrained_value_is_inside_the_validation_domain(xs_model):
    """What the tools store, not what the dialogs show (plan section 1.1).

    The fixture writes ``tip_trase podzemna``, ``podtip glavni``,
    ``cable_laying Podzemno`` -- the stored codes. Checking them against the
    same helper rule D1 uses is what keeps the dataset validation-clean for a
    reason rather than by luck.
    """
    from fiberq.core.validation_rules import _allowed_domain
    from fiberq.models import schema

    rows, _meta = xs_model
    checked = 0
    pairs = 0
    outside = []
    for canonical, layer_schema in schema.LAYER_SCHEMAS.items():
        constrained = [(field.key, _allowed_domain(field))
                       for field in layer_schema.fields]
        constrained = [(key, allowed) for key, allowed in constrained if allowed]
        pairs += len(constrained)
        for fid, _wkt, attrs in rows.get(canonical, ()):
            for key, allowed in constrained:
                value = attrs.get(key)
                if value is None or str(value) == "":
                    continue          # emptiness is C1's business, not D1's
                checked += 1
                if str(value) not in allowed:
                    outside.append((canonical, fid, key, value, sorted(allowed)))

    assert pairs > 0, "no field in the schema declares options or a value_map"
    assert checked > MIN_CONSTRAINED_VALUES, (
        f"only {checked} constrained values at XS across {pairs} field/layer "
        f"pairs; the generator has stopped filling the enum fields, so this "
        f"test is no longer checking anything")
    assert outside == [], outside[:5]


def test_the_digest_covers_the_project_entries(xs_model):
    """The relations, the latent elements and the colour catalogue count too.

    They are written into the ``.qgz``, not into the GeoPackage, so a digest
    over the rows alone left them unpinned -- and the latent payload is exactly
    what the ``latent_open`` benchmark scenario is timed opening. Measured on
    the row-only digest: ``LATENT_EVERY`` 97 -> 13 took the latent payload from
    3 cables to 22 and the digest did not move.
    """
    import copy

    import make_city_project as gen

    rows, meta = xs_model
    entries = meta["entry_rows"]
    assert sorted(entries) == ["catalogs", "latent", "relations"]
    assert gen.dataset_digest(rows, meta["layer_names"], False,
                              entries) == XS_DIGEST

    probes = {
        "relations": lambda e: e["relations"].append(
            {"id": "r-99999", "name": "REL-9999", "category": "Main",
             "created": "", "cables": []}),
        "latent": lambda e: e["latent"].update(
            {"fiberq_bench_Aerial_cables:1": {"elements": []}}),
        "catalogs": lambda e: e["catalogs"].append({"name": "x",
                                                    "colors": []}),
    }
    for name, mutate in sorted(probes.items()):
        mutated = copy.deepcopy(entries)
        mutate(mutated)
        assert gen.dataset_digest(rows, meta["layer_names"], False,
                                  mutated) != XS_DIGEST, (
            f"changing the {name} project entry leaves the digest alone, so "
            f"the pinned constant no longer identifies the whole dataset")


def test_the_digest_tells_a_dropped_column_from_an_empty_one(xs_model):
    """A NULL column must not hash like a column full of ``""``.

    Six text fields are stored empty on purpose, so this is the cheap mistake
    to make. Measured before ``_digest_value`` grew its NULL sentinel: deleting
    ``napomena`` from all 156 ``Optical slack`` rows left the digest unchanged.
    """
    import copy

    import make_city_project as gen

    rows, meta = xs_model
    assert gen._digest_value(None) != gen._digest_value("")
    mutated = copy.deepcopy(rows)
    dropped = 0
    for _fid, _wkt, attrs in mutated["Optical slack"]:
        del attrs["napomena"]
        dropped += 1
    assert dropped > 0, "the slack rows no longer carry napomena"
    assert gen.dataset_digest(mutated, meta["layer_names"], False,
                              meta["entry_rows"]) != XS_DIGEST


def test_every_canonical_layer_has_features_at_xs(xs_model):
    """A scenario must never measure an empty layer.

    The plan asks for at least one of every element layer, which the generator
    guarantees with an explicit seeding pass; the other twelve canonical layers
    come out populated too, so all 24 are checked.
    """
    from fiberq.models import schema

    _rows, meta = xs_model
    counts = meta["counts"]
    elements = sorted(name for name in schema.LAYER_SCHEMAS
                      if schema.is_element_layer(name))
    assert elements, "the schema declares no element layers"
    assert [name for name in elements if not counts.get(name)] == []
    assert [name for name in schema.LAYER_SCHEMAS if not counts.get(name)] == []
    assert len(counts) == len(schema.LAYER_SCHEMAS)


def _import_time_nodes(tree):
    """Every AST node that runs when the module is imported.

    That is the whole tree minus the bodies of its functions: a function body
    runs when it is called, which is where the generator's own ``sys.path``
    insert lives.
    """
    found = []
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        found.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return found


def _sys_path_writes(name):
    """Where ``name`` reaches for ``sys.path`` while being imported."""
    source = (FIXTURES / name).read_text(encoding="utf-8")
    found = []
    for node in _import_time_nodes(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == "path":
            if isinstance(node.value, ast.Name) and node.value.id == "sys":
                found.append(f"{name}: sys.path at line {node.lineno}")
        elif isinstance(node, ast.ImportFrom) and node.module == "sys":
            if [alias for alias in node.names if alias.name == "path"]:
                found.append(f"{name}: from sys import path at line {node.lineno}")
    return found


def test_the_generator_does_not_touch_sys_path_at_import_time():
    """Otherwise a benchmark worker would measure the wrong code.

    ``--code`` goes first on ``sys.path`` and the worker asserts that
    ``fiberq.__file__`` is inside it (plan section 1.1). A fixture that inserted
    the repository root while being imported would put the working tree ahead of
    the extracted v1.5.0 tree, and the "before" run would quietly measure the
    "after" code. The insert therefore lives inside ``main()``.

    The other two fixtures do it at module scope, which is why this is a test
    and not a comment.
    """
    offenders = _sys_path_writes("make_city_project.py")
    assert offenders == [], (
        f"make_city_project.py mutates sys.path while being imported "
        f"({offenders}). A benchmark worker imports this module after putting "
        f"the code tree under test first on sys.path; an insert here would hand "
        f"the 'before' run the 'after' code. Do it inside main() instead.")


def test_the_sys_path_check_can_still_see_a_violation():
    """The test above is worth nothing if the walk stopped finding anything.

    ``make_scale_project.py`` inserts the repository root at module scope -- the
    very thing being forbidden -- and it is WP2's file, which this work package
    is not allowed to touch. So it makes a dependable sample of the mistake.
    """
    found = _sys_path_writes("make_scale_project.py")
    assert found, (
        "make_scale_project.py no longer inserts on sys.path at import time, so "
        "this self-test has nothing to detect. Either the AST walk above is "
        "broken (fix it) or that fixture was changed (point this test at "
        "another module that still does it, or drop it).")
