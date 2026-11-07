"""Turn benchmark result directories into the tables ``docs/performance.md`` publishes.

Usage::

    python3 tools/bench/bench_report.py docs/performance/raw            # markdown on stdout
    python3 tools/bench/bench_report.py docs/performance/raw --json out.json

The raw directory holds one directory per run, named the way the final run named
them: ``final-v150-a1-qgis344-S``, ``final-v160-qgis344-S``,
``final-v150-a2-qgis344-S``, the middle columns ``final-mid-pf5-qgis344-S``,
``final-mid-pf7-qgis344-S``, ``final-mid-gate-qgis344-S``,
``final-mid-pf3-qgis344-S`` and ``final-mid-q9b-qgis344-S``, and the early
``baseline-v150-qgis344-S``. Each holds one ``<scenario>-<size>.json`` per row.

The rules, so a reader can check a published figure rather than trust it
(the WP4 plan, section 1.5 item 1):

* A row's v1.5.0 range is the hull of both v1.5.0 runs' median +/- MAD. The
  two runs bracket the v1.6.0 run in time, so drift during the session widens
  the range instead of turning into a speed-up.
* A change is shown only when v1.6.0's median +/- MAD lies wholly outside that
  range **and** every run computed the same result digest. Otherwise the row
  says "no measurable change", or why it cannot be compared.
* A row is flagged when its two v1.5.0 medians are more than 15% apart, or
  either is more than 15% from the early baseline.
* A middle column is one of two kinds. The parent of a claimed change is
  compared with v1.6.0: that is the change on its own. v1.6.0 without a later
  change of behaviour computes what v1.5.0 computed, so it is compared with
  v1.5.0, by the same rule as v1.6.0 is: the speed-up at equal results, on a
  row where v1.6.0 itself computes something else.

Pure stdlib: it reads JSON and needs no QGIS.
"""

import argparse
import json
import os
import re
import sys

#: Run directories this report understands: <kind>-<image>-<size>.
RUN_RE = re.compile(r"^(?P<kind>final-v150-a1|final-v150-a2|final-v160|final-mid-pf5|final-mid-pf7|"
                    r"final-mid-gate|final-mid-pf3|final-mid-q9b|baseline-v150)"
                    r"-qgis(?P<image>\d+)-(?P<size>[A-Z]+)$")

#: Which middle column applies to which rows, as ``kind: (label, short name, against, rows)``.
#: ``against`` is what it is compared with: "v1.6.0" for the parent of a claimed
#: change, "v1.5.0" for v1.6.0 without a later change of behaviour (see the rules).
MIDDLE = {
    "final-mid-pf5": ("PF-5's parent (`473a149`)", "PF-5's parent", "v1.6.0",
                      {"snap_move_element", "snap_move_point", "snap_move_route", "snap_move_pipe",
                       "snap_move_breakpoint", "snap_move_closure", "manhole_click"}),
    "final-mid-pf7": ("PF-7's parent (`69555e8`)", "PF-7's parent", "v1.6.0", {"lay_cable", "route_path"}),
    "final-mid-gate": ("v1.6.0 without the visibility gate", "v1.6.0 without the gate", "v1.6.0",
                       {"edit_after_schematic"}),
    "final-mid-pf3": ("v1.6.0 without the QA fix to route ends (`ef58e92`)", "with 1.5.0's findings", "v1.5.0",
                      {"route_correction"}),
    "final-mid-q9b": ("v1.6.0 with joint closures snapping to vertices only, as in 1.5.0", "snapping as 1.5.0 did",
                      "v1.5.0", {"snap_move_closure"}),
}

#: The plan's drift threshold between runs of the same code.
DRIFT = 0.15

IMAGES = {"344": "QGIS 3.44.15 (Qt5)", "40": "QGIS 4.0.3 (Qt6)"}
SIZE_ORDER = ["XS", "S", "M", "L"]


def load_runs(raw_dir):
    """``{(image, size): {kind: {scenario: row}}}`` for every recognised run directory."""
    groups = {}
    for name in sorted(os.listdir(raw_dir)):
        match = RUN_RE.match(name)
        path = os.path.join(raw_dir, name)
        if not match or not os.path.isdir(path):
            continue
        rows = {}
        for entry in sorted(os.listdir(path)):
            if not entry.endswith(".json") or entry in ("run.json", "env.json"):
                continue
            with open(os.path.join(path, entry), encoding="utf-8") as handle:
                row = json.load(handle)
            if isinstance(row, dict) and row.get("scenario"):
                rows[row["scenario"]] = row
        key = (match.group("image"), match.group("size"))
        groups.setdefault(key, {})[match.group("kind")] = rows
    return groups


def timing(row):
    """``(median, mad, cold)`` in seconds, or ``None`` for a row with no timing."""
    if not row or row.get("status") != "ok":
        return None
    t = row.get("timing") or {}
    if t.get("median_s") is None:
        return None
    return t["median_s"], t.get("mad_s") or 0.0, t.get("cold_s")


def fmt(seconds):
    """A duration as a person reads it: ms below a second, minutes above one."""
    if seconds is None:
        return "—"
    if seconds < 1.0:
        return "%.3g ms" % (seconds * 1000.0)
    if seconds < 60.0:
        return "%.3g s" % seconds
    minutes, rest = divmod(int(round(seconds)), 60)
    return "%d min" % minutes if rest == 0 else "%d min %02d s" % (minutes, rest)


def cell(row):
    """The table cell for one run of one row."""
    if row is None:
        return "—"
    status = row.get("status")
    if status == "dnf":
        # bench_worker records the budget only in its detail text.
        found = re.search(r"over the ([0-9.]+) s budget", row.get("detail") or "")
        return "did not finish" + (" in %s" % fmt(float(found.group(1))) if found else "")
    t = timing(row)
    if t is None:
        return str(status)
    return fmt(t[0])


def change_text(before, after):
    """``x21 faster`` for a large change; a percentage of the time for a small one."""
    if after < before:
        ratio = before / after
        if ratio < 1.5:
            return "%d%% faster" % round((1 - after / before) * 100)
        return ("x%d" % round(ratio) if ratio >= 10 else "x%.2g" % ratio) + " faster"
    ratio = after / before
    if ratio < 1.5:
        return "%d%% slower" % round((ratio - 1) * 100)
    return ("x%d" % round(ratio) if ratio >= 10 else "x%.2g" % ratio) + " slower"


def outside(reference, measured):
    """``measured`` compared with ``reference`` runs: ``"faster"``, ``"slower"`` or ``None`` (within)."""
    lo = min(t[0] - t[1] for t in reference)
    hi = max(t[0] + t[1] for t in reference)
    if measured[0] + measured[1] < lo:
        return "faster"
    if measured[0] - measured[1] > hi:
        return "slower"
    return None


def compare(scenario, runs):
    """One row's verdict across the runs of one image and size."""
    a1 = runs.get("final-v150-a1", {}).get(scenario)
    a2 = runs.get("final-v150-a2", {}).get(scenario)
    b = runs.get("final-v160", {}).get(scenario)
    base = runs.get("baseline-v150", {}).get(scenario)
    notes = []
    verdict = ""
    present = [r for r in (a1, a2, b) if r is not None]
    digests = {r.get("result_digest") for r in present if r.get("status") == "ok"}
    if len(digests) > 1:
        notes.append("result digests differ")

    ta1, ta2, tb = timing(a1), timing(a2), timing(b)
    a_runs = [t for t in (ta1, ta2) if t is not None]
    if ta1 and ta2:
        lo, hi = sorted((ta1[0], ta2[0]))
        if hi > lo * (1 + DRIFT):
            notes.append("v1.5.0 runs %.0f%% apart" % ((hi / lo - 1) * 100))
    tbase = timing(base)
    if tbase:
        for t in a_runs:
            if abs(t[0] / tbase[0] - 1) > DRIFT:
                notes.append("v1.5.0 %.0f%% off the baseline" % ((t[0] / tbase[0] - 1) * 100))
                break

    a_dnf = any(r is not None and r.get("status") == "dnf" for r in (a1, a2))
    if tb and a_dnf:
        verdict = "v1.5.0 did not finish"
    elif tb and a_runs:
        a_ref = sum(t[0] for t in a_runs) / len(a_runs)
        side = outside(a_runs, tb)
        if len(digests) > 1:
            verdict = "not comparable"
        elif side is None:
            verdict = "no measurable change"
        else:
            verdict = change_text(a_ref, tb[0])
    elif b is not None and b.get("status") != "ok":
        verdict = "v1.6.0: %s" % b.get("status")
    return verdict, notes


def middle_compares(scenario, runs):
    """``[(kind, middle row, verdict)]`` for every middle column that isolates this row.

    Against v1.6.0 the verdict is v1.6.0's: the claimed work on its own, with
    the supporting change already on both sides. Against v1.5.0 it is the middle
    column's, by the rule :func:`compare` applies to v1.6.0: the speed-up at
    equal results. Either way only where the two sides computed the same result.
    """
    found = []
    for kind, (_label, _short, against, rows) in MIDDLE.items():
        mid = runs.get(kind, {}).get(scenario)
        if scenario in rows and mid is not None:
            found.append((kind, mid, _middle_verdict(scenario, runs, mid, against)))
    return found


def _middle_verdict(scenario, runs, mid, against):
    tm = timing(mid)
    if against == "v1.6.0":
        b = runs.get("final-v160", {}).get(scenario)
        tb = timing(b)
        if not (tm and tb):
            return ""
        if mid.get("result_digest") != b.get("result_digest"):
            return "not comparable"
        side = outside([tm], tb)
        return "no measurable change" if side is None else change_text(tm[0], tb[0])
    olds = [runs.get(kind, {}).get(scenario) for kind in ("final-v150-a1", "final-v150-a2")]
    a_runs = [timing(r) for r in olds if timing(r)]
    if not (tm and a_runs):
        return ""
    if any(timing(r) and r.get("result_digest") != mid.get("result_digest") for r in olds):
        return "not comparable"
    side = outside(a_runs, tm)
    return "no measurable change" if side is None else change_text(sum(t[0] for t in a_runs) / len(a_runs), tm[0])


def middle_compare(scenario, runs):
    """``(label, middle row, verdict)`` of the first middle column that isolates this row, else ``None``."""
    found = middle_compares(scenario, runs)
    if not found:
        return None
    kind, mid, verdict = found[0]
    return MIDDLE[kind][0], mid, verdict


def middle_cell(scenario, runs):
    cells = []
    for kind, mid, verdict in middle_compares(scenario, runs):
        label, _short, against, _rows = MIDDLE[kind]
        if not verdict:
            note = ""
        elif against == "v1.6.0":
            note = " (v1.6.0 %s)" % verdict
        elif verdict == "not comparable":
            note = " (against v1.5.0: not comparable)"
        else:
            note = " (against v1.5.0, the same result: %s)" % verdict
        cells.append("%s: %s%s" % (label, cell(mid), note))
    return "; ".join(cells)


def first_call(row):
    t = timing(row)
    return fmt(t[2]) if t and t[2] is not None else "—"


def scenario_order(runs):
    """The rows of a table: those a v1.5.0 or v1.6.0 run measured, never a middle column's alone."""
    order = []
    for kind in ("final-v160", "final-v150-a1", "final-v150-a2", "baseline-v150"):
        for name in runs.get(kind, {}):
            if name not in order:
                order.append(name)
    return order


def is_control(scenario, runs):
    for rows in runs.values():
        if scenario in rows:
            return bool(rows[scenario].get("control"))
    return False


def group_table(runs):
    lines = ["| Row | | v1.5.0 (before / after the v1.6.0 run) | v1.6.0 | Change | Middle column | "
             "First call, v1.5.0 / v1.6.0 | Notes |",
             "|---|---|---|---|---|---|---|---|"]
    for scenario in scenario_order(runs):
        a1 = runs.get("final-v150-a1", {}).get(scenario)
        a2 = runs.get("final-v150-a2", {}).get(scenario)
        b = runs.get("final-v160", {}).get(scenario)
        verdict, notes = compare(scenario, runs)
        claim = "control" if is_control(scenario, runs) else "4.1"
        lines.append("| `%s` | %s | %s / %s | %s | %s | %s | %s / %s | %s |" % (
            scenario, claim, cell(a1), cell(a2), cell(b), verdict,
            middle_cell(scenario, runs), first_call(a1), first_call(b), "; ".join(notes)))
    return "\n".join(lines)


#: The rows the summary shows, in the order a user meets them, with the action in words.
SUMMARY_ROWS = [
    ("schematic_open", "Open the Optical Schematic View"),
    ("edit_after_schematic", "Any edit, once the view has been opened"),
    ("latent_open", "Open the list of latent elements"),
    ("route_correction", "Route correction (the check)"),
    ("slack_generate", "Generate terminal slacks for 50 cables"),
    ("slack_click", "Place one slack"),
    ("snap_move_route", "Nine mouse moves, route tool"),
    ("snap_move_element", "Nine mouse moves, element tool"),
    ("snap_move_closure", "Nine mouse moves, joint-closure tool"),
    ("manhole_click", "Place one manhole"),
    ("record_add", "FiberQ's undo record after a placement"),
    ("lay_cable", "Lay one cable"),
]


def mean_v150(runs, scenario):
    """The two v1.5.0 runs' mean median, or a did-not-finish cell."""
    rows = [runs.get(kind, {}).get(scenario) for kind in ("final-v150-a1", "final-v150-a2")]
    if any(r is not None and r.get("status") == "dnf" for r in rows):
        return cell(next(r for r in rows if r is not None and r.get("status") == "dnf"))
    times = [timing(r) for r in rows if timing(r)]
    return fmt(sum(t[0] for t in times) / len(times)) if times else "—"


def summary_table(raw_dir, image="344"):
    """One line per user action: v1.5.0 -> v1.6.0 at each size, with the change.

    Where v1.5.0 computed something else, the change is a middle column's. One
    that computes what v1.5.0 computed comes first, and the cell then gives its
    time and says what v1.6.0 as shipped takes; else the parent of the claimed
    change (the snap-distance fix changed what two tools snap to).
    """
    groups = load_runs(raw_dir)
    sizes = [s for s in SIZE_ORDER if (image, s) in groups and "final-v160" in groups[(image, s)]]
    lines = ["| User action | " + " | ".join("Size %s" % s for s in sizes) + " |",
             "|---|" + "---|" * len(sizes)]
    for scenario, action in SUMMARY_ROWS:
        cells = []
        for size in sizes:
            runs = groups[(image, size)]
            if scenario not in runs.get("final-v160", {}):
                cells.append("—")
                continue
            verdict, _notes = compare(scenario, runs)
            before, after = mean_v150(runs, scenario), cell(runs["final-v160"][scenario])
            if verdict == "not comparable":
                equal = [(kind, mid, found) for kind, mid, found in middle_compares(scenario, runs)
                         if MIDDLE[kind][2] == "v1.5.0" and found and found != "not comparable"]
                if equal:
                    kind, mid, found = equal[0]
                    cells.append("%s → %s %s (%s); %s as shipped" % (before, cell(mid), MIDDLE[kind][1], found, after))
                    continue
                parent = [(kind, found) for kind, _mid, found in middle_compares(scenario, runs)
                          if MIDDLE[kind][2] == "v1.6.0" and found and found != "not comparable"]
                if parent:
                    verdict = "%s than %s" % (parent[0][1], MIDDLE[parent[0][0]][1])
            cells.append("%s → %s (%s)" % (before, after, verdict))
        lines.append("| %s | %s |" % (action, " | ".join(cells)))
    return "\n".join(lines)


def report(raw_dir):
    groups = load_runs(raw_dir)
    out = []
    summary = {}
    for (image, size) in sorted(groups, key=lambda k: (k[0] != "344", k[0], SIZE_ORDER.index(k[1])
                                                       if k[1] in SIZE_ORDER else 9)):
        runs = groups[(image, size)]
        if "final-v160" not in runs:
            continue
        out.append("### %s, size %s\n" % (IMAGES.get(image, "QGIS " + image), size))
        out.append(group_table(runs))
        out.append("")
        for scenario in scenario_order(runs):
            verdict, notes = compare(scenario, runs)
            middles = [{"label": MIDDLE[kind][0], "against": MIDDLE[kind][2], "time": cell(mid), "verdict": found}
                       for kind, mid, found in middle_compares(scenario, runs)]
            summary.setdefault("%s-%s" % (image, size), {})[scenario] = {
                "verdict": verdict, "notes": notes,
                "middle": middles[0] if middles else None, "middles": middles,
                "v150_a1": cell(runs.get("final-v150-a1", {}).get(scenario)),
                "v150_a2": cell(runs.get("final-v150-a2", {}).get(scenario)),
                "v160": cell(runs.get("final-v160", {}).get(scenario)),
                "control": is_control(scenario, runs)}
    return "\n".join(out), summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("raw_dir")
    parser.add_argument("--json", default=None, help="also write the verdicts as JSON")
    parser.add_argument("--summary", action="store_true",
                        help="print the summary table (QGIS 3.44, every size) instead of the results")
    args = parser.parse_args(argv)
    text, summary = report(args.raw_dir)
    sys.stdout.write((summary_table(args.raw_dir) if args.summary else text) + "\n")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
