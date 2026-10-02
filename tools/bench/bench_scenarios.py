#!/usr/bin/env python3
"""The WP4 benchmark scenarios: one closure per user action being measured.

Each factory takes the run context, does the setup *outside* the timed region
and returns the callable that is timed. The callable asserts its own
post-condition and returns the facts the result digest is taken over, so a run
that silently did less work fails instead of looking faster.

Keys starting with ``_`` in the returned facts are reported but left out of the
digest: they describe *how* the work happened, which an optimisation is allowed
to change.

Dev tooling. Never shipped: ``make package`` archives ``HEAD:fiberq`` only.
"""
import os
import random

from qgis.core import (QgsFeature, QgsGeometry, QgsPointXY, QgsProject,
                       QgsVectorLayer)

from bench_support import (centre_canvas, first_name, layer_by_name, point_of,
                           polyline)

#: Nine mouse positions around a route vertex, in metres, used by every
#: placement row. Three of them are inside the snap tolerance at 0.5 m/px and
#: six are not, so one call exercises both branches. Divide a reported median by
#: ``events`` for the per-move cost the plan's section 1.2 table quotes.
SNAP_OFFSETS = [(dx, dy) for dx in (-3.0, 0.0, 40.0) for dy in (-2.0, 0.0, 30.0)]

#: Candidate names for the layers the scenarios need, newest canonical name
#: first. The old Serbian names are listed because the generator can emit them
#: with --legacy-names, and a scenario that quietly skipped on an old project
#: would hide the very paths WP4-FU-2 is about.
LAYER_ALIASES = {
    "route": ("Route", "Trasa"),
    "poles": ("Poles", "Stubovi"),
    "manholes": ("Manholes", "OKNA"),
    "joint_closures": ("Joint Closures", "Nastavci"),
    "underground": ("Underground cables", "Kablovi_podzemni"),
    "aerial": ("Aerial cables", "Kablovi_vazdusni"),
    "slack": ("Optical slack", "Optical slacks", "Rezerva"),
}

REGISTRY = {}


class Scenario:
    """One measurable user action."""

    def __init__(self, name, factory, pf=None, control=False, mutating=False,
                 post="", needs=()):
        self.name = name
        self.factory = factory
        self.pf = pf
        self.control = control
        self.mutating = mutating
        self.post = post
        self.needs = tuple(needs)

    def describe(self):
        return {"scenario": self.name, "pf": self.pf, "control": self.control,
                "mutating": self.mutating, "post_condition": self.post,
                "needs": list(self.needs)}

    def missing_layers(self):
        """The roles this scenario needs that the loaded project has no layer for."""
        return [role for role in self.needs if first_name(*LAYER_ALIASES[role]) is None]


def scenario(name, **kwargs):
    """Register a scenario factory under ``name``."""
    def register(factory):
        for role in kwargs.get("needs", ()):
            if role not in LAYER_ALIASES:
                raise KeyError("unknown layer role %r" % role)
        REGISTRY[name] = Scenario(name, factory, **kwargs)
        return factory
    return register


def role(name):
    """The project layer for a role, by whichever alias the dataset used."""
    return layer_by_name(first_name(*LAYER_ALIASES[name]).name())


def cable_layers():
    """Underground then aerial, whichever of the two the project has."""
    out = []
    for key in ("underground", "aerial"):
        found = first_name(*LAYER_ALIASES[key])
        if found is not None:
            out.append(found)
    return out


def sorted_fids(layer):
    """Feature ids in a stable order; provider order is not guaranteed."""
    return sorted(int(f.id()) for f in layer.getFeatures())


def clear_selections():
    for layer in QgsProject.instance().mapLayers().values():
        if hasattr(layer, "removeSelection"):
            layer.removeSelection()


def a_route_vertex():
    """A deterministic mid vertex of the lowest-fid route feature."""
    route = role("route")
    first = min(sorted_fids(route))
    line = polyline(route.getFeature(first))
    if len(line) < 3:
        raise SystemExit("route %d has %d vertices, expected a 3-vertex route"
                         % (first, len(line)))
    return QgsPointXY(line[1])


def move_events(canvas, origin):
    """One ``QgsMapMouseEvent`` per SNAP_OFFSETS entry, built up front."""
    from qgis.gui import QgsMapMouseEvent
    from qgis.PyQt.QtCore import QEvent, QPoint, Qt
    transform = canvas.getCoordinateTransform()
    events = []
    for dx, dy in SNAP_OFFSETS:
        device = transform.transform(QgsPointXY(origin.x() + dx, origin.y() + dy))
        events.append(QgsMapMouseEvent(
            canvas, QEvent.Type.MouseMove,
            QPoint(int(round(device.x())), int(round(device.y()))),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))
    return events


def release_event(canvas, point):
    """A left-button release at a map point."""
    from qgis.gui import QgsMapMouseEvent
    from qgis.PyQt.QtCore import QEvent, QPoint, Qt
    device = canvas.getCoordinateTransform().transform(QgsPointXY(point))
    return QgsMapMouseEvent(
        canvas, QEvent.Type.MouseButtonRelease,
        QPoint(int(round(device.x())), int(round(device.y()))),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)


def _noop(*args, **kwargs):
    """Replacement for a retired dialog's rebuild scheduler."""


def close_dialogs(ctx):
    """Close and retire the dialogs a repetition opened. Outside the timed region.

    The schematic view connects project signals to lambdas capturing ``self``
    (``schematic_dialog.py:898-899``), which PyQt cannot auto-disconnect on
    destruction, so every dialog an extra repetition leaves behind keeps
    scheduling rebuilds on the next commit. Measured before this was added:
    the seven ``edit_after_schematic`` repetitions climbed 0.770 -> 0.901 s,
    monotonically. That is the harness accumulating, not the code being slow --
    a user has one view open, not nine. Neutralising the scheduler on a retired
    dialog leaves the cold call, which is the one that must behave exactly like
    v1.5.0, completely untouched.
    """
    while ctx["keep"]:
        held = ctx["keep"].pop()
        if hasattr(held, "_schedule_rebuild"):
            held._schedule_rebuild = _noop
        if hasattr(held, "close"):
            held.close()
        if hasattr(held, "deleteLater"):
            held.deleteLater()
    ctx["app"].processEvents()


# --- PF-1: optical schematic view -----------------------------------------
@scenario("schematic_open", pf="PF-1", needs=("underground",),
          post="the scene is rebuilt and holds at least one item")
def sc_schematic_open(ctx):
    from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog
    plugin = ctx["plugin"]
    open_dialogs = ctx["keep"]

    def run():
        dialog = OpticalSchematicDialog(plugin)
        items = len(dialog.scene.items())
        open_dialogs.append(dialog)
        assert items > 0, "the schematic scene came out empty"
        return {"scene_items": items}

    return run, lambda: close_dialogs(ctx)


@scenario("edit_after_schematic", pf="PF-1", mutating=True, needs=("underground",),
          post="the attribute change commits; a hidden rebuild is reported, not required")
def sc_edit_after_schematic(ctx):
    """One attribute edit after the view has been opened and closed once.

    On v1.5.0 every commit anywhere rebuilds the schematic even though it is
    hidden. PF-1 stops that, so ``_rebuild_scheduled`` is a fact in the result,
    never an assertion: asserting it would make the fixed code fail.
    """
    from fiberq.dialogs.schematic_dialog import OpticalSchematicDialog
    plugin = ctx["plugin"]
    dialog = OpticalSchematicDialog(plugin)
    dialog.show()
    ctx["app"].processEvents()
    dialog.close()
    ctx["app"].processEvents()
    ctx["keep"].append(dialog)

    layer = cable_layers()[0]
    field = next((n for n in ("opis", "naziv", "oznaka") if n in layer.fields().names()),
                 None)
    if field is None:
        raise SystemExit("no text field to edit on %r" % layer.name())
    fid = min(sorted_fids(layer))
    index = layer.fields().indexFromName(field)

    def run():
        dialog._rebuild_pending = False
        assert layer.startEditing()
        assert layer.changeAttributeValue(fid, index, "bench-edit")
        assert layer.commitChanges(), layer.commitErrors()
        scheduled = bool(getattr(dialog, "_rebuild_pending", False))
        dialog._do_rebuild_if_needed()
        assert layer.getFeature(fid)[field] == "bench-edit"
        return {"edited_field": field, "edited_fid": fid,
                "_rebuild_scheduled_while_hidden": scheduled,
                "_scene_items": len(dialog.scene.items())}

    return run, lambda: close_dialogs(ctx)


# --- PF-2: latent elements -------------------------------------------------
@scenario("latent_open", pf="PF-2", needs=("underground",),
          post="one table row per cable in the project")
def sc_latent_open(ctx):
    from fiberq.dialogs.latent_dialog import LatentElementsDialog
    plugin = ctx["plugin"]
    expected = len(plugin.list_all_cables())
    open_dialogs = ctx["keep"]

    def enabled(dialog, row):
        """Is the row's Edit button live? That is the per-cable candidate scan."""
        button = dialog.tbl.cellWidget(row, 5)
        return button is not None and button.isEnabled()

    def run():
        dialog = LatentElementsDialog(plugin)
        rows = dialog.tbl.rowCount()
        open_dialogs.append(dialog)
        assert rows == expected, (rows, expected)
        return {"rows": rows,
                "editable": sum(1 for r in range(rows) if enabled(dialog, r))}

    return run, lambda: close_dialogs(ctx)


# --- PF-3: route correction ------------------------------------------------
@scenario("route_correction", pf="PF-3", needs=("route", "poles"),
          post="the same finding count every time, and the dialog is built")
def sc_route_correction(ctx):
    plugin = ctx["plugin"]

    def run():
        plugin.check_consistency()
        findings = len(plugin.popravljive_greske)
        return {"findings": findings,
                "messages": [kind for kind, _ in ctx["iface"].messageBar().log[-1:]]}
    return run


# --- PF-4: slack -----------------------------------------------------------
@scenario("slack_generate", pf="PF-4", mutating=True,
          needs=("underground", "slack"),
          post="two terminal slacks per selected cable")
def sc_slack_generate(ctx):
    plugin = ctx["plugin"]
    cables = cable_layers()[0]
    fids = sorted_fids(cables)[:int(ctx["k"])]
    if not fids:
        raise SystemExit("no cables to generate slack for")
    slack = role("slack")
    start = polyline(cables.getFeature(fids[0]))[0]
    centre_canvas(ctx["iface"], start.x(), start.y())
    clear_selections()
    # Selecting the cables is the click before the one being measured, so it
    # happens here -- as it already did for lay_cable. The row is mutating, so
    # this factory runs again before every repetition and the selection is
    # always fresh.
    cables.selectByIds(fids)
    before = slack.featureCount()

    def run():
        plugin.generate_terminal_slack_for_selected()
        after_count = slack.featureCount()
        assert after_count == before + 2 * len(fids), (before, after_count, len(fids))
        return {"k": len(fids), "slacks_added": after_count - before}
    return run


@scenario("slack_click", pf="PF-4", mutating=True, needs=("underground", "slack"),
          post="one slack feature per click")
def sc_slack_click(ctx):
    from fiberq.tools.slack_tool import SlackPlaceTool
    cables = cable_layers()[0]
    slack = role("slack")
    fid = min(sorted_fids(cables))
    end = polyline(cables.getFeature(fid))[-1]
    canvas = centre_canvas(ctx["iface"], end.x(), end.y())
    tool = SlackPlaceTool(ctx["iface"], ctx["plugin"], {"tip": "Terminal", "duzina_m": 20})
    event = release_event(canvas, end)

    def run():
        before = slack.featureCount()
        tool.canvasReleaseEvent(event)
        after_count = slack.featureCount()
        assert after_count == before + 1, (before, after_count)
        return {"slacks_added": after_count - before}
    return run


# --- PF-5: placement tools -------------------------------------------------
def _snap_move(ctx, make_tool, snapped):
    """Shared body of the snap_move_* rows: N mouse moves, count the snaps."""
    origin = a_route_vertex()
    canvas = centre_canvas(ctx["iface"], origin.x(), origin.y())
    tool = make_tool(canvas)
    events = move_events(canvas, origin)

    def run():
        hits = 0
        for event in events:
            tool.canvasMoveEvent(event)
            hits += 1 if snapped(tool) else 0
        assert hits > 0, "not one of the %d moves snapped" % len(events)
        return {"events": len(events), "snapped": hits}
    return run


@scenario("snap_move_element", pf="PF-5", needs=("route", "poles"),
          post="at least one of the moves snaps")
def sc_snap_move_element(ctx):
    from fiberq.tools.element_tool import PlaceElementTool
    return _snap_move(ctx, lambda canvas: PlaceElementTool(canvas, "ODF"),
                      lambda tool: tool._last_snap_point is not None)


@scenario("snap_move_point", pf="PF-5", needs=("route", "poles"),
          post="at least one of the moves snaps")
def sc_snap_move_point(ctx):
    from fiberq.tools.point_tool import PointTool
    poles = role("poles")
    return _snap_move(ctx, lambda canvas: PointTool(canvas, poles),
                      lambda tool: tool.snap_marker.isVisible())


@scenario("snap_move_route", pf="PF-5", needs=("route", "poles"),
          post="at least one of the moves snaps")
def sc_snap_move_route(ctx):
    from fiberq.tools.route_tool import ManualRouteTool
    iface = ctx["iface"]
    plugin = ctx["plugin"]
    return _snap_move(ctx, lambda canvas: ManualRouteTool(iface, plugin),
                      lambda tool: tool.snap_rubber.numberOfVertices() > 0)


@scenario("snap_move_pipe", pf="PF-5", needs=("route", "poles"),
          post="at least one of the moves snaps")
def sc_snap_move_pipe(ctx):
    from fiberq.tools.pipe_tool import PipePlaceTool
    iface = ctx["iface"]
    plugin = ctx["plugin"]
    origin = a_route_vertex()

    def make(canvas):
        tool = PipePlaceTool(iface, plugin, "PE", {})
        if not hasattr(tool.snap_marker, "center"):
            raise SystemExit("QgsVertexMarker has no center(): no post-condition")
        return tool

    def snapped(tool):
        centre = tool.snap_marker.center()
        return QgsPointXY(centre).distance(origin) < 0.5
    return _snap_move(ctx, make, snapped)


@scenario("snap_move_breakpoint", pf="PF-5", needs=("route",),
          post="at least one of the moves snaps")
def sc_snap_move_breakpoint(ctx):
    from fiberq.tools.breakpoint_tool import BreakpointTool
    iface = ctx["iface"]
    plugin = ctx["plugin"]
    return _snap_move(ctx, lambda canvas: BreakpointTool(canvas, iface, plugin),
                      lambda tool: tool.snap_info is not None)


@scenario("manhole_click", pf="PF-5", mutating=True, needs=("route",),
          post="one manhole feature per click")
def sc_manhole_click(ctx):
    from fiberq.tools.manhole_tool import ManholePlaceTool
    plugin = ctx["plugin"]
    origin = a_route_vertex()
    canvas = centre_canvas(ctx["iface"], origin.x(), origin.y())
    layer = plugin._ensure_okna_layer()
    if layer is None:
        raise SystemExit("the plugin could not provide a Manholes layer")
    plugin._manhole_pending_attrs = {"broj_okna": "BENCH-1", "tip_okna": "Standard"}
    tool = ManholePlaceTool(ctx["iface"], plugin)
    event = release_event(canvas, origin)

    def run():
        before = layer.featureCount()
        tool.canvasReleaseEvent(event)
        after_count = layer.featureCount()
        assert after_count == before + 1, (before, after_count)
        return {"manholes_added": after_count - before}
    return run


# --- PF-6: undo record after every add ------------------------------------
def _record_add(ctx, layer, geometry):
    """Add + commit outside the timed region, then time ``record_add`` alone."""
    undo = ctx["plugin"].undo_manager
    if undo is None:
        raise SystemExit("the plugin has no undo manager")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(geometry)
    assert layer.startEditing()
    assert layer.addFeature(feature)
    assert layer.commitChanges(), layer.commitErrors()
    fid_after_commit = int(feature.id())
    depth_before = len(undo._undo_stack)

    def run():
        undo.record_add(layer, feature)
        assert len(undo._undo_stack) == depth_before + 1
        op = undo._undo_stack[-1]
        found = layer.getFeature(int(op.feature_id)) if op.feature_id is not None else None
        assert found is not None and found.isValid(), op.feature_id
        return {"resolved_fid_is_real": True,
                "_fid_after_commit": fid_after_commit,
                "_scanned_for_fid": fid_after_commit < 0,
                "_features": layer.featureCount()}

    def after():
        while len(undo._undo_stack) > depth_before:
            undo._undo_stack.pop()
    return run, after


@scenario("record_add", pf="PF-6", mutating=True, needs=("poles",),
          post="the undo op resolves to a real committed feature")
def sc_record_add(ctx):
    layer = role("poles")
    origin = a_route_vertex()
    return _record_add(ctx, layer, QgsGeometry.fromPointXY(
        QgsPointXY(origin.x() + 1.0, origin.y() + 1.0)))


@scenario("record_add_memory", pf="PF-6", mutating=True, needs=("poles",),
          post="the undo op resolves to a real committed feature")
def sc_record_add_memory(ctx):
    """The same add on a memory layer, which has no R-tree to fall back on.

    Every layer the plugin creates itself is a memory layer, and none of them
    calls ``createSpatialIndex()`` on v1.5.0, so this row is the one that shows
    what the provider index in PF-5 is worth.
    """
    source = role("poles")
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "bench memory nodes", "memory")
    layer.dataProvider().addAttributes(source.fields().toList())
    layer.updateFields()
    copies = []
    for feature in source.getFeatures():
        clone = QgsFeature(layer.fields())
        clone.setGeometry(feature.geometry())
        clone.setAttributes(feature.attributes())
        copies.append(clone)
    assert layer.dataProvider().addFeatures(copies)[0]
    layer.updateExtents()
    ctx["keep"].append(layer)
    origin = a_route_vertex()
    return _record_add(ctx, layer, QgsGeometry.fromPointXY(
        QgsPointXY(origin.x() + 2.0, origin.y() + 2.0)))


# --- PF-7: lay cable -------------------------------------------------------
@scenario("lay_cable", pf="PF-7", mutating=True,
          needs=("route", "joint_closures", "underground"),
          post="exactly one new cable feature")
def sc_lay_cable(ctx):
    plugin = ctx["plugin"]
    closures = role("joint_closures")
    fids = sorted_fids(closures)
    if len(fids) < 2:
        raise SystemExit("need two joint closures to lay a cable between")
    ends = (fids[0], fids[-1])
    anchor = point_of(closures.getFeature(ends[0]))
    centre_canvas(ctx["iface"], anchor.x(), anchor.y())
    cables = cable_layers()
    clear_selections()
    closures.selectByIds(list(ends))

    def run():
        before = sum(layer.featureCount() for layer in cables)
        plugin.lay_cable()
        after_count = sum(layer.featureCount() for layer in cables)
        assert after_count == before + 1, (before, after_count)
        return {"cables_added": after_count - before, "between": list(ends)}
    return run


@scenario("route_path", pf="PF-7", needs=("route",),
          post="every requested path is found, with the same vertex counts")
def sc_route_path(ctx):
    """Five seeded origin/destination pairs that are known to be connected.

    The pairs are resolved in the factory, so a dataset where the graph happens
    to be split fails during setup instead of quietly measuring five searches
    that all return None in a fraction of the time.
    """
    from fiberq.utils.routing import build_path_across_network
    route = role("route")
    fids = sorted_fids(route)
    rnd = random.Random(7)
    pairs = []
    for _ in range(200):
        if len(pairs) == 5:
            break
        start = polyline(route.getFeature(fids[int(rnd.random() * len(fids))]))
        end = polyline(route.getFeature(fids[int(rnd.random() * len(fids))]))
        if not start or not end:
            continue
        first, last = QgsPointXY(start[0]), QgsPointXY(end[-1])
        if build_path_across_network(route, first, last, 1.0):
            pairs.append((first, last))
    if len(pairs) < 5:
        raise SystemExit("only %d of 200 seeded pairs were connected" % len(pairs))

    def run():
        lengths = []
        for first, last in pairs:
            path = build_path_across_network(route, first, last, 1.0)
            assert path, "no path between two pairs that were connected at setup"
            lengths.append(len(path))
        return {"paths": len(lengths), "vertices": lengths}
    return run


# --- controls: these must NOT change. They detect noise. ------------------
@scenario("run_validation", control=True, needs=("route",),
          post="the same issue and rule-error counts every time")
def sc_run_validation(ctx):
    from fiberq.core.validation_manager import run_validation

    def run():
        result = run_validation(project=QgsProject.instance(), plugin_version="bench")
        return {"issues": len(result.issues), "rule_errors": len(result.rule_errors)}
    return run


@scenario("plan_recalculation", control=True, needs=("route",),
          post="the same plan every time; nothing is written")
def sc_plan_recalculation(ctx):
    from fiberq.core.length_manager import plan_recalculation

    def run():
        plan = plan_recalculation(project=QgsProject.instance())
        return {"layers_seen": sorted(plan.layers_seen),
                "changes": len(getattr(plan, "changes", []) or []),
                "failed_layers": list(plan.failed_layers)}
    return run


@scenario("save_gpkg", control=True, mutating=True, needs=("route",),
          post="a non-empty GeoPackage is written")
def sc_save_gpkg(ctx):
    plugin = ctx["plugin"]
    target = ctx["save_path"]
    # Unlinking the previous run's GeoPackage is not part of saving one, so it
    # happens here. The row is mutating, so the factory runs again before every
    # repetition and each timed call starts from no file at all.
    if os.path.exists(target):
        os.remove(target)

    def run():
        plugin.save_all_layers_to_gpkg()
        assert os.path.exists(target), "no file at the patched save path"
        size = os.path.getsize(target)
        assert size > 0, "the saved GeoPackage is empty"
        return {"_bytes": size, "layers": len(QgsProject.instance().mapLayers())}
    return run


@scenario("project_open", control=True, mutating=True,
          post="every layer in the dataset comes back")
def sc_project_open(ctx):
    """Read the project with the two hooks ``initGui`` wires, then migrate.

    The fresh copy is made in the factory, so the timed region is the read and
    the migration pass -- not ``shutil.copy`` of an 8 MB GeoPackage.
    """
    from bench_support import copy_dataset, disable_project_snapping
    plugin = ctx["plugin"]
    project = QgsProject.instance()
    work, files = copy_dataset(ctx["data"], ctx["scratch"])
    ctx["temp_dirs"].append(work)              # cleaned up with the session's copy
    expected = ctx["layer_count"]

    def run():
        project.clear()
        project.layersAdded.connect(plugin._on_layers_added)
        try:
            assert project.read(os.path.join(work, files["qgz"]))
            plugin._run_schema_migrations()
        finally:
            project.layersAdded.disconnect(plugin._on_layers_added)
        disable_project_snapping(project)
        count = len(project.mapLayers())
        assert count == expected, (count, expected)
        return {"layers": count}
    return run


@scenario("bom_open", control=True, needs=("route",),
          post="the layer table is populated")
def sc_bom_open(ctx):
    from fiberq.dialogs.bom_dialog import _BOMDialog
    iface = ctx["iface"]
    open_dialogs = ctx["keep"]

    def run():
        dialog = _BOMDialog(iface, parent=iface.mainWindow())
        rows = dialog.tbl_layers.rowCount()
        open_dialogs.append(dialog)
        assert rows > 0, "the BOM dialog listed no layers"
        return {"rows": rows}

    return run, lambda: close_dialogs(ctx)


@scenario("branch_offset", control=True, mutating=True, needs=("underground",),
          post="the same group and update counts every time")
def sc_branch_offset(ctx):
    plugin = ctx["plugin"]
    layer = cable_layers()[0]

    def run():
        plugin._ensure_branch_index_field(layer)
        counted = plugin._compute_branch_indices_for_layer(layer, tol_m=1.3)
        assert counted is not None, "computing branch indices returned nothing"
        plugin._apply_branch_offset_style(layer)
        groups, updated = counted
        return {"groups": int(groups), "updated": int(updated)}
    return run


def names(include_controls=True):
    """Registered scenario names, PF rows first, in registration order."""
    return [n for n, s in REGISTRY.items() if include_controls or not s.control]
