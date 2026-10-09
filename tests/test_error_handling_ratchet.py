"""A handler that writes nothing anywhere is not error handling.

``FIBERQ_LOG_LEVEL`` defaults to WARNING, so ``except Exception as e:
logger.debug(...)`` reaches no log panel, no message bar and no user. It is
``pass`` with a comment. There were 816 handlers of that shape when this gate
was written; that figure is history and does not move. The live count is
``SILENCE_CEILING`` below -- what test D asserts by equality, and the one place
the number is maintained.

WP4's reliability work does not pretend it will fix all of them. It hardens the
operations that **write, export, import or migrate data** -- where a swallowed
error costs the user work rather than a cosmetic glitch -- and leaves styling,
dialogs and the preview alone. That is a promise about a specific list of
functions, so this file is the list, written down and enforced.

Four things are checked, and the fourth is the one that stops the other three
being quietly outgrown:

**A.** No silent handler on a hardened path, beyond what ``ALLOWED_SILENT``
still permits.

**B.** No allowance is looser than the code needs. An entry saying 5 where only
3 remain fails here, so the lists can only ever shrink. This is the ratchet: a
branch that fixes two handlers must come here and lower the number, which is
also where it is forced to notice the ones it did not fix.

**C.** No write call on a hardened path throws away its result. QGIS answers
``commitChanges()``, ``addFeature()`` and friends with a bool that says whether
the data reached the provider; discarding it turns a failed save into a success
message.

**D.** Package-wide, the number of silent handlers tracks a pinned count exactly
and no bare ``except:`` ever appears. The handlers outside the hardened
functions are out of scope for 4.2, but out of scope is not a licence to add
more -- nor to bank the ones a branch removes as headroom for the next.

**E.** The scanner is run against a seeded module holding one of each defect,
one of each correct form, and one of each way a defect might try to leave the
gate, because a check that has never fired is not a check.

Keying. Allowances are keyed by ``(path, qualname)``, never by line number: a
branch that fixes one handler moves every line below it, and a line-keyed list
would have to be rewritten wholesale on every edit, which is how allowlists stop
being read. A qualname that disappears is a failure, not a free pass, so
renaming a hardened function cannot silently empty the list.

Attribution. A finding inside a nested ``def`` is charged to the nearest
enclosing hardened function. Moving a swallow into a closure is not a fix.

Swallow-and-return is **not** counted, and that is a real blind spot worth
knowing before you trust a green run. ``except Exception: return None`` responds
to the caller, so :func:`is_silent` scores it zero -- which is the build plan's
own census rule ("body only pass/debug/continue/break"), and widening it would
move about 107 handlers package-wide and re-open the claim arithmetic. The cost
today is eight handlers inside hardened functions that this gate reads as
already clean: ``data_manager.py:69, :138, :217``,
``relations_manager.py:68, :220``, ``color_manager.py:124`` -- every site R5's
row names -- plus ``routing.py:229, :350``, which are R8's. Those
two rows are carried by their own behaviour tests, not by this file. Do not read
an empty ALLOWED row for them as "nothing to do".

What this file cannot tell you. It proves nothing is silent; it cannot prove the
handling that replaced the silence is *right*. That is each branch's own
behaviour tests, which fail on v1.5.0 and pass after. A ratchet alone would be
satisfied by rewriting ``logger.debug`` as ``logger.warning`` and changing
nothing the user sees. Nor can it follow an arbitrary refactor: a body moved
into a *sibling* method leaves the gate, where a body moved into a nested
``def`` does not. A branch whose diff deletes allowance rows it did not
obviously fix is a branch to read twice.

Pure AST: no QGIS, no Qt, milliseconds.
"""
import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO / "fiberq"

#: Logging that reaches nobody in a default install. ``FIBERQ_LOG_LEVEL``
#: defaults to WARNING and ``logger.py`` applies it to both the logger and the
#: QgsLogHandler, so DEBUG *and* INFO are filtered out before they reach the
#: panel: measured inside qgis/qgis:4.0-trixie, ``isEnabledFor(INFO)`` is False.
#: ``info`` is listed for that reason -- otherwise ``s/logger.debug/logger.info/``
#: would carry a handler out of this gate for the price of one word.
_DEBUG_CALLS = frozenset({"debug", "info", "log_debug", "log_info"})

#: QGIS writes that answer with a bool nobody is obliged to read. ``writeEntry``
#: is deliberately absent: it only edits the in-memory project and returns True
#: even for an empty key, so checking it would be noise rather than safety.
WRITE_CALLS = frozenset({
    "addAttributes",
    "addFeature",
    "addFeatures",
    "changeAttributeValue",
    "changeGeometry",
    "commitChanges",
    "deleteFeature",
    "deleteFeatures",
    "updateFeature",
})

#: FiberQ's own helpers that answer with a bool saying whether the write
#: happened. Section 2.3's R2 counts their discarded returns among the failures
#: the GeoPackage auto-save hides, and a rule keyed on QGIS method names alone
#: would never see them: the value thrown away is FiberQ's, not QGIS's.
FIBERQ_WRITE_CALLS = frozenset({
    "export_one_layer_to_gpkg",
    "save_all_layers_to_gpkg",
})

#: The functions behind the operations WP4 4.2 hardens, from section 2.3 of the
#: build plan. Every entry was resolved from that plan's line references and
#: must keep resolving: see ``test_the_hardened_set_still_names_real_code``.
CRITICAL = {
    # R9
    "fiberq/addons/fiber_break.py": frozenset({
        "FiberBreakTool._record_break",
        "FiberBreakTool.canvasReleaseEvent",
    }),
    # U9: the link storage R12 depends on -- a picture QGIS 4 can finally open
    # is no use if the QGIS 3 save dropped the link. Same precedent as U6's
    # gpkg_target: an unclaimed module a claimed path rests on.
    "fiberq/core/feature_links.py": frozenset({
        "_read_all",
        "_read_legacy",
        "_write_all",
        "link_clear",
        "link_get",
        "link_set",
    }),
    # R11
    "fiberq/dialogs/schematic_dialog.py": frozenset({
        "OpticalSchematicDialog._center_on",
        "OpticalSchematicDialog._drop_highlight",
    }),
    # R12
    "fiberq/utils/image_watcher.py": frozenset({
        "CanvasImageClickWatcher._show_picture_under",
        "CanvasImageClickWatcher.eventFilter",
    }),
    # R5. save_color_catalogs held TWO swallows -- one on the delegation, one
    # on the duplicate write it fell through to -- and the gate watched neither.
    "fiberq/core/color_manager.py": frozenset({
        "ColorManager.load_color_catalogs",
        "ColorManager.save_color_catalogs",
    }),
    # R5. save_latent and save_color_catalogs were never in here, so half the
    # defect was never watched: the gate saw the relations save and neither of
    # the other two, although all three had the identical swallow.
    "fiberq/core/data_manager.py": frozenset({
        "DataManager.load_color_catalogs",
        "DataManager.load_latent",
        "DataManager.load_relations",
        "DataManager.save_color_catalogs",
        "DataManager.save_latent",
        "DataManager.save_relations",
    }),
    # U6: the pure pre-flight and naming rules both export paths depend on
    "fiberq/core/gpkg_target.py": frozenset({
        "existing_tables",
        "flatten_name",
        "gpkg_target_problem",
        "is_geopackage",
        "table_in_use",
        "table_name_for",
    }),
    # R1, R2, R3. export_active_layer and _do_export are THE export path now
    # that main_plugin's duplicate is deleted; neither was named here before,
    # so the one that actually ran was the one the gate did not watch.
    "fiberq/core/export_manager.py": frozenset({
        "ExportManager._do_export",
        "ExportManager.export_active_layer",
        "ExportManager._ask_where_to_save",
        "ExportManager._export_one_layer",
        "ExportManager._project_entry",
        "ExportManager._project_is_unreadable",
        "ExportManager._replace_with_fresh_layer",
        "ExportManager._repoint",
        "ExportManager._save_style",
        "ExportManager._write_layer",
        "ExportManager._write_metadata",
        "ExportManager._write_metadata_table",
        "ExportManager.export_one_layer_to_gpkg",
        "ExportManager.save_all_layers_to_gpkg",
        "_writer_result",
    }),
    # R1, R2, R7
    "fiberq/core/layer_manager.py": frozenset({
        # _copy_attributes holds the body; the public name is now the wrapper
        # that owns the error collector. Both are named so the split cannot
        # carry the handlers out of this gate's sight.
        "_copy_attributes",
        "_copy_attributes_between_layers",
    }),
    # R5: the one module in core/ that is allowed to touch QgsProject, because
    # the store IS the project. It owns the whole read-parse-default policy that
    # used to be written out four times, so a silent handler here would put the
    # defect back in all twelve places at once.
    "fiberq/core/project_store.py": frozenset({
        "quarantine_unreadable",
        "read_json_entry",
        "write_json_entry",
        "_report",
        "_report_write",
    }),
    # R5. Same gap on the save side as data_manager's.
    "fiberq/core/relations_manager.py": frozenset({
        "RelationsManager.load_latent",
        "RelationsManager.load_relations",
        "RelationsManager.save_latent",
        "RelationsManager.save_relations",
    }),
    # R8. CableManager.lay_cable holds the whole cable-laying write path and was
    # never named here, so the gate watched the two main_plugin wrappers that
    # swallowed its failures and not the code producing them.
    "fiberq/core/cable_manager.py": frozenset({
        "CableManager.lay_cable",
    }),
    # R6, R7
    "fiberq/core/route_manager.py": frozenset({
        "RouteManager._add_imported_routes",
        "RouteManager._add_one_route",
        # The three the merge was split into. A new sibling method is a new
        # qualname, so without these rows an extract-a-helper refactor would
        # quietly carry its handlers out of this gate's sight.
        "RouteManager._chain_selected_routes",
        "RouteManager._set_merged_attributes",
        "RouteManager._write_merged_route",
        "RouteManager._route_parts",
        "RouteManager.change_route_type",
        "RouteManager.import_route_from_file",
        "RouteManager.merge_all_routes",
    }),
    # R9
    "fiberq/core/slack_manager.py": frozenset({
        "SlackManager._add_one_terminal_slack",
        "SlackManager._endpoints_of",
        "SlackManager._generate_terminal_slacks",
        "SlackManager._ground_length",
        "SlackManager._location_at",
        "SlackManager._record_slack_undo",
        "SlackManager._say_slacks_created",
        "SlackManager._slack_total",
        "SlackManager._stamp_uuid",
        "SlackManager._total_slack_onto_cable",
        "SlackManager.generate_terminal_slack_for_selected",
        "SlackManager.recompute_slack_for_cable",
    }),
    # R7
    # R7. undo/redo, _ensure_editable, _commit, _stack_back and clear were never
    # named here, although that is where the decision to commit is actually
    # made: the gate watched the three helpers and not the state machine
    # driving them, and _unsaved lives in the state machine.
    "fiberq/core/undo_manager.py": frozenset({
        "FiberQUndoManager._commit",
        "FiberQUndoManager._ensure_editable",
        "FiberQUndoManager._stack_back",
        "FiberQUndoManager.clear",
        "FiberQUndoManager.redo",
        "FiberQUndoManager.undo",
        "FiberQUndoManager._add_feature",
        "FiberQUndoManager._delete_feature",
        "FiberQUndoManager._restore_feature",
    }),
    # R4
    # R4. _export picks the writer and _measured_length / _note_lines are where
    # the counting lives, so a silent handler in any of them would put the
    # under-count straight back. _export_csv and _export_xlsx were already here.
    "fiberq/dialogs/bom_dialog.py": frozenset({
        "_BOMDialog._export",
        "_BOMDialog._measured_length",
        "_BOMDialog._note_lines",
        "_BOMDialog._remove_partial",
        "_BOMDialog._write_xlsx",
        "_BOMDialog._build",
        "_BOMDialog._export_csv",
        "_BOMDialog._export_xlsx",
    }),
    # R10, R6: the geometry primitives Route correction and the importers rest on
    "fiberq/utils/geometry.py": frozenset({
        "geometry_point",
        "is_finite",
        "line_vertices",
        "transformed",
    }),
    # R3, R5, R6, R7, R8, R10
    "fiberq/main_plugin.py": frozenset({
        "FiberQPlugin._add_imported_points",
        "FiberQPlugin._add_one_point",
        "FiberQPlugin._cables_behind",
        "FiberQPlugin.check_consistency",
        "FiberQPlugin.fix_route_to_pole",
        "FiberQPlugin._change_element_type",
        "FiberQPlugin._save_color_catalogs",
        "FiberQPlugin.delete_selected",
        "FiberQPlugin.export_all_features",
        "FiberQPlugin.export_selected_features",
        "FiberQPlugin.import_points",
        "FiberQPlugin.lay_cable",
        "FiberQPlugin.lay_cable_type",
    }),
    # R9
    "fiberq/tools/slack_tool.py": frozenset({
        "SlackPlaceTool._place_slack",
        "SlackPlaceTool._recompute",
        "SlackPlaceTool._slack_layer",
        "SlackPlaceTool.canvasReleaseEvent",
    }),
    # R2
    "fiberq/ui/routing_ui.py": frozenset({
        "RoutingUI._ask_for_auto_gpkg",
        "RoutingUI._project_gpkg_path",
        "RoutingUI._set_project_gpkg_path",
        "RoutingUI._target_problem_text",
        "RoutingUI._on_layer_added_auto_gpkg",
        "RoutingUI._stop_watching_for_new_layers",
        "RoutingUI._toggle_auto_gpkg",
        "RoutingUI._untick",
        "RoutingUI.on_project_target_changed",
        "RoutingUI.settle_auto_gpkg",
    }),
    # R8. build_network_graph joins the two path builders: it held the same
    # dead asPolyline()/asMultiPolyline() fallback, so the graph build died on
    # the first multipart route and the two builders above it could only ever
    # answer "no path".
    "fiberq/utils/routing.py": frozenset({
        "build_network_graph",
        "build_path_across_joined_routes",
        "build_path_across_network",
    }),
}

#: Silent handlers still standing on a hardened path, with the branch that
#: clears them. Seeded at R0 so the gate lands green; each later branch deletes
#: or lowers its own rows, and test B makes sure it does.
#:
#: A row may also survive as a deliberate allowance -- a toast that fails inside
#: an error path is cosmetic, and reporting a reporting failure helps nobody --
#: but then its reason must say so instead of naming a branch.
ALLOWED_SILENT = {
    # Not branch 9's to clear, and deliberately not presented as if they were.
    # R8's row is the multipart break, the two wrapper swallows and the
    # path-finding ones -- all fixed. These six are the colour-code lookup, the
    # cables-layer search, the display-name helper and the two attribute
    # setters: separate pre-award defects in the same long function. The
    # function is gated from here so the number can only fall, which is better
    # than leaving the whole write path unwatched because part of it is out of
    # scope. Recorded in docs/private/FiberQ-WP4-followups.md.
    ("fiberq/core/cable_manager.py",
     "CableManager.lay_cable"): (6, "pre-award swallows in the same function, not in R8's row"),
}

#: Write calls whose result is still discarded on a hardened path. Kept apart
#: from ALLOWED_SILENT because they are a different defect with a different fix:
#: one hides an exception, the other ignores an answer. Sharing one counter
#: would let a branch "fix" a swallowed exception by checking a return value.
ALLOWED_WRITES = {
    # As above: two dataProvider().addAttributes() calls that build the cable
    # layer's schema, neither of them R8's row. Gated so they cannot grow.
    ("fiberq/core/cable_manager.py",
     "CableManager.lay_cable"): (2, "pre-award schema writes in the same function, not in R8's row"),
}

#: What test D pins the package-wide silent-handler count to. Test D asserts
#: equality, not ``<=`` as the build plan's section 2.2 wrote it, so the number
#: follows the code down as well as up. The plan's wording ("<= 817, lowered by
#: each PR") leaves the lowering to whoever remembers: a branch that removes ten
#: handlers and does not touch this line banks ten as headroom, and the next
#: branch can spend them. Measured, not argued -- rewriting eighteen handlers in
#: `element_tool.py` to `logger.warning` and then adding eighteen fresh silent
#: ones elsewhere left a `<=` gate green throughout.
#:
#: The cost is that a PR which changes the count must change this line too. The
#: failure message gives the number to paste.
#:
#: Why 816 and not the build plan's 817. The plan counted only handlers written
#: ``except Exception``; that rule gives exactly 817 on v1.5.0 and 795 here, so
#: it is the plan's rule and the number is right. This gate counts every handler
#: type instead, because ``except ValueError: pass`` is every bit as silent and
#: a narrow rule would leave a free lane open. On the same two trees the wider
#: rule gives 830 and 816, and this branch took it to 786:
#: R1, R2 and U6 between them hardened nineteen and deleted twelve along with
#: the two duplicate GeoPackage exports. Branch 9 then took it down one commit
#: at a time, each in the commit that hardened the handler, and the figure is
#: always read off this gate's own failure message rather than computed in
#: advance -- six concurrent plans for this branch each predicted a number from
#: the 753 baseline and all six were wrong by the time they were written. The
#: fall of 14
#: from v1.5.0 is what branches 3 and 4 left behind
#: when they rewrote the placement tools: handlers deleted with the code around
#: them, less the few that ``length_sync.py`` brought in.
SILENCE_CEILING = 715


# ---------------------------------------------------------------------------
# the scanner
# ---------------------------------------------------------------------------

def _is_debug_only(statement):
    """True for ``logger.debug(...)`` and friends used as a whole statement."""
    if not isinstance(statement, ast.Expr):
        return False
    call = statement.value
    if not isinstance(call, ast.Call):
        return False
    name = getattr(call.func, "attr", None) or getattr(call.func, "id", None)
    return name in _DEBUG_CALLS


def _is_filler(statement):
    """A docstring or a bare ``...``: shaped like code, does nothing."""
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)


def is_silent(handler):
    """True when nothing in this handler reaches a log, a panel or a caller.

    ``raise``, ``return``, a message-bar push, a ``logger.warning`` -- any of
    them is a response, and none of them is counted here. Only the handlers
    that do nothing at all are.
    """
    inert = (ast.Pass, ast.Continue, ast.Break)
    return all(isinstance(node, inert) or _is_debug_only(node) or _is_filler(node) for node in handler.body)


def _unchecked_write(statement):
    """The method name when a write's result is thrown away, else None.

    A call used as a whole statement discards what it returned. Anything else --
    assigned, tested in an ``if``, returned, passed on -- is somebody's problem,
    and that is enough for this gate.
    """
    if not isinstance(statement, ast.Expr):
        return None
    # The whole expression is searched, not just its outermost call, so
    # ``bool(layer.commitChanges())`` is still a discarded result rather than a
    # way out of this gate.
    for node in ast.walk(statement.value):
        if not isinstance(node, ast.Call):
            continue
        # QGIS writes are always called on a layer or a provider, so only an
        # attribute access can be one. FiberQ's helpers are module-level and
        # are called by bare name, so those are matched either way.
        attribute = getattr(node.func, "attr", None)
        if attribute in WRITE_CALLS or attribute in FIBERQ_WRITE_CALLS:
            return attribute
        bare = getattr(node.func, "id", None)
        if bare in FIBERQ_WRITE_CALLS:
            return bare
    return None


def _charge_to(qualname, hardened):
    """The hardened function a finding in ``qualname`` belongs to, or None.

    A nested ``def`` is charged to its enclosing hardened function, so moving a
    swallow into a closure does not move it out of the gate.
    """
    parts = qualname.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in hardened:
            return candidate
        parts.pop()
    return None


def _own_statements(scope):
    """Nodes belonging to ``scope`` itself, excluding nested function bodies."""
    nested = set()
    for node in ast.walk(scope):
        if node is scope:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nested.update(id(inner) for inner in ast.walk(node))
    return [node for node in ast.walk(scope) if id(node) not in nested]


def _nested_definitions(node):
    """Every def and class ``node`` encloses, however deeply it is indented.

    ``ast.iter_child_nodes`` alone would only see a ``def`` written directly in
    a body, and miss one inside an ``if``, a ``try``, a ``with`` or a loop.
    ``_own_statements`` excludes nested defs at any depth, so anything in that
    gap would belong to nobody at all -- findings would vanish rather than move,
    and an ordinary extract-a-helper refactor would silently empty a row.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield child
        else:
            # A block statement: keep descending, but do not cross into a def.
            for found in _nested_definitions(child):
                yield found


def _definitions(tree):
    """``qualname -> own nodes`` for every def and class in a parsed module."""
    found = {}

    def walk(node, prefix):
        for child in _nested_definitions(node):
            qualname = prefix + child.name
            found[qualname] = _own_statements(child)
            walk(child, qualname + ".")

    walk(tree, "")
    return found


def scan(path, hardened):
    """``{qualname: (silent_lines, write_sites)}`` for the hardened functions.

    ``path`` is a real file; ``hardened`` is the set of qualnames to charge
    findings to. Functions with nothing to report are left out.
    """
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    found = {}
    for qualname, nodes in _definitions(tree).items():
        owner = _charge_to(qualname, hardened)
        if owner is None:
            continue
        silent, writes = found.setdefault(owner, ([], []))
        for node in nodes:
            if isinstance(node, ast.ExceptHandler) and is_silent(node):
                silent.append(node.lineno)
            write = _unchecked_write(node)
            if write is not None:
                writes.append((node.lineno, write))
    for silent, writes in found.values():
        silent.sort()
        writes.sort()
    return {name: value for name, value in found.items() if any(value)}


def _found(table, index):
    """``{(path, qualname): findings}`` across the whole hardened set."""
    out = {}
    for path, hardened in table.items():
        for qualname, value in scan(REPO / path, hardened).items():
            if value[index]:
                out[(path, qualname)] = value[index]
    return out


def _why(headline, problems):
    """The assertion message: the rule first, then every place it was broken."""
    return headline + "\n" + "\n".join(problems)


def _report(key, findings, budget, what):
    path, qualname = key
    places = ", ".join(str(item) for item in findings)
    return (f"{path}::{qualname} has {len(findings)} {what} "
            f"(allowed {budget}) at {places}")


# ---------------------------------------------------------------------------
# A -- nothing silent on a hardened path
# ---------------------------------------------------------------------------

def test_a_no_silent_handler_on_a_hardened_path():
    problems = []
    for key, lines in sorted(_found(CRITICAL, 0).items()):
        budget = ALLOWED_SILENT.get(key, (0, ""))[0]
        if len(lines) > budget:
            problems.append(_report(key, lines, budget, "silent handler(s)"))
    assert not problems, _why(
        "A handler that only writes to the debug log tells the user nothing. "
        "Report it through fiberq.utils.errors, or add a row to ALLOWED_SILENT "
        "with a reason.", problems)


# ---------------------------------------------------------------------------
# B -- the allowances may only shrink
# ---------------------------------------------------------------------------

def test_b_no_allowance_is_looser_than_the_code_needs():
    problems = []
    tables = ((ALLOWED_SILENT, 0, "silent handler(s)"),
              (ALLOWED_WRITES, 1, "unchecked write(s)"))
    for table, index, what in tables:
        actual = _found(CRITICAL, index)
        for key, (budget, reason) in sorted(table.items()):
            path, qualname = key
            if qualname not in CRITICAL.get(path, frozenset()):
                problems.append(f"{path}::{qualname} is allowed for but is not "
                                f"in CRITICAL; delete the row or harden it")
                continue
            if not reason.strip():
                problems.append(f"{path}::{qualname} has an allowance with no reason")
            left = len(actual.get(key, []))
            if budget > left:
                instead = " or delete the row" if left == 0 else ""
                problems.append(f"{path}::{qualname} allows {budget} {what} but only "
                                f"{left} remain; lower it to {left}{instead}")
    assert not problems, _why(
        "The allowance lists may only shrink -- that is the whole mechanism.",
        problems)


# ---------------------------------------------------------------------------
# C -- no write result discarded on a hardened path
# ---------------------------------------------------------------------------

def test_c_no_unchecked_write_on_a_hardened_path():
    problems = []
    for key, sites in sorted(_found(CRITICAL, 1).items()):
        budget = ALLOWED_WRITES.get(key, (0, ""))[0]
        if len(sites) > budget:
            problems.append(_report(key, sites, budget, "unchecked write(s)"))
    assert not problems, _why(
        "QGIS answers these calls with a bool saying whether the data reached "
        "the provider. Discarding it turns a failed save into a success "
        "message. Use fiberq.utils.errors.check_commit, or test the result.",
        problems)


# ---------------------------------------------------------------------------
# D -- the package as a whole does not get quieter
# ---------------------------------------------------------------------------

def test_d_package_wide_silence_does_not_grow():
    silent = []
    bare = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            where = f"{path.relative_to(REPO)}:{node.lineno}"
            if node.type is None:
                bare.append(where)
            if is_silent(node):
                silent.append(where)

    assert not bare, _why(
        "A bare `except:` also catches KeyboardInterrupt and SystemExit, so it "
        "can wedge QGIS on shutdown. Name the exceptions you mean.", bare)
    assert len(silent) == SILENCE_CEILING, (
        f"{len(silent)} silent handlers, against SILENCE_CEILING = "
        f"{SILENCE_CEILING}. Set SILENCE_CEILING = {len(silent)}.\n"
        f"Equality, not <=, so the number follows the code down as well as up. "
        f"A branch that removes handlers would otherwise bank the difference as "
        f"headroom for the next one to spend, and the ratchet would stop being "
        f"one. If the count went UP, say in the commit why that was necessary.")


#: How many functions CRITICAL names, across how many files. Pinned because
#: deleting a line from CRITICAL removes a whole operation from this gate with
#: nothing in fiberq/ changing -- and that diff looks exactly like the one
#: section 2.2 sanctions, where a branch deletes its own allowance rows.
#: 110 in 20 files after branch 9, and every one of the fourteen is a WIDENING.
#: Four came from splitting two hardened functions and naming every piece
#: (RouteManager._chain_selected_routes, ._set_merged_attributes,
#: ._write_merged_route; layer_manager._copy_attributes). Five are the new
#: core/project_store.py, which owns the whole read-parse-default policy R5
#: used to have written out four times -- a silent handler there would put the
#: defect back in all twelve places at once. The other five close a hole this
#: gate had from the start: DataManager.save_latent, .save_color_catalogs,
#: RelationsManager.save_latent, .save_relations and
#: ColorManager.save_color_catalogs were never named, although each held the
#: same swallow as the one save the gate did watch. The last six are
#: FiberQUndoManager's undo, redo, clear, _ensure_editable, _commit and
#: _stack_back -- the state machine that decides whether to commit at all,
#: which this gate watched not at all while watching the three helpers it
#: calls. The last two are CableManager.lay_cable -- the whole cable-laying
#: write path, which this gate watched not at all while watching the two
#: main_plugin wrappers that swallowed its failures -- and
#: routing.build_network_graph, and the last five are the BOM dialog's
#: _export, _measured_length, _note_lines, _remove_partial and _write_xlsx --
#: where R4's counting and reporting now live. The last two are
#: ExportManager.export_active_layer and ._do_export, which R3 made THE
#: export path by deleting main_plugin's duplicate -- the one that actually
#: ran was the one this gate did not watch. No R-row moved.
HARDENED_FUNCTIONS = 125
HARDENED_FILES = 21


def test_the_hardened_set_is_not_quietly_narrowed():
    """Shrinking the scope has to be a deliberate edit to a number."""
    functions = sum(len(names) for names in CRITICAL.values())
    assert (functions, len(CRITICAL)) == (HARDENED_FUNCTIONS, HARDENED_FILES), (
        f"CRITICAL now names {functions} functions in {len(CRITICAL)} files, "
        f"not {HARDENED_FUNCTIONS} in {HARDENED_FILES}. Widening it is welcome; "
        f"narrowing it drops an operation from sections 2.3's claim, so raise "
        f"or lower these two numbers in the same diff and say which R-row moved.")


def test_the_hardened_set_still_names_real_code():
    """A qualname that no longer exists is a hole, not a pass.

    Rename ``save_all_layers_to_gpkg`` and every row pointing at it would stop
    matching -- silently, because an empty scan finds no problems.
    """
    missing = []
    for path, hardened in sorted(CRITICAL.items()):
        full = REPO / path
        if not full.exists():
            missing.append(f"{path} no longer exists")
            continue
        known = set(_definitions(ast.parse(full.read_text(encoding="utf-8"))))
        missing += [f"{path}::{name}" for name in sorted(hardened - known)]
    assert not missing, _why(
        "CRITICAL names code that is not there any more. If it moved, move the "
        "row; if it went, delete the row and its allowances.", missing)


# ---------------------------------------------------------------------------
# E -- the scanner itself
# ---------------------------------------------------------------------------

SEEDED = '''
class Manager:
    def hardened(self, layer, errors):
        try:
            layer.startEditing()
        except Exception:
            pass                             # silent 1
        try:
            layer.reload()
        except Exception as exc:
            logger.debug(f"never seen: {exc}")   # silent 2
        try:
            layer.reload()
        except Exception as exc:
            logger.info(f"also never seen: {exc}")   # silent 3

        layer.commitChanges()                # write 1
        layer.addFeature(feature)            # write 2
        bool(layer.updateFeature(feature))   # write 3, wrapped

        def helper():
            try:
                layer.deleteFeature(1)       # write 4
            except Exception:
                pass                         # silent 4

        if layer.isEditable():
            def deeper():
                try:
                    layer.changeGeometry(1, geom)   # write 5
                except Exception:
                    pass                     # silent 5

            deeper()

        helper()

    def proper(self, layer, errors):
        """Everything here is correct and must not be reported."""
        try:
            layer.startEditing()
        except RuntimeError as exc:
            errors.add(layer.name(), exc)
        if not layer.commitChanges():
            errors.add(layer.name(), "refused")
        ok = layer.addFeature(feature)
        return ok

    def elsewhere(self, layer):
        try:
            layer.commitChanges()
        except Exception:
            pass
'''


def test_e_the_scan_finds_a_seeded_regression(tmp_path):
    """A check that has never fired is not a check.

    Guards both halves: the defects are found and charged to the right
    function, and the correct forms beside them are left alone -- including the
    identical code in ``elsewhere``, which is not on a hardened path.
    """
    module = tmp_path / "seeded.py"
    module.write_text(SEEDED, encoding="utf-8")

    found = scan(module, {"Manager.hardened", "Manager.proper"})

    assert sorted(found) == ["Manager.hardened"], found
    silent, writes = found["Manager.hardened"]

    # Five silent handlers and five unchecked writes, all charged to hardened().
    # The last two of each are the evasions: one pair inside a closure written
    # at body level, one pair inside a closure written under an ``if``. The
    # second shape was invisible until the traversal in _nested_definitions was
    # fixed -- the findings did not move to the closure, they vanished.
    assert len(silent) == 5, silent
    assert [name for _line, name in writes] == [
        "commitChanges", "addFeature", "updateFeature",
        "deleteFeature", "changeGeometry"], writes

    # ``bool(...)`` around a write is still a discarded result; ``logger.info``
    # is as silent as ``logger.debug`` at the default log level. Both are in the
    # counts above, and both are one-word edits away from a false green.
    assert "updateFeature" in [name for _line, name in writes]

    assert not scan(module, {"Manager.proper"}), "a correct handler was reported"
    assert scan(module, {"Manager.elsewhere"}), "the seed itself is wrong"
