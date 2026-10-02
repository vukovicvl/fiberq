#!/usr/bin/env python3
"""Run the WP4 benchmark: one subprocess per scenario x dataset size.

    python3 tools/bench/bench.py --code /fq-base --label v1.5.0 \\
        --data S=/bench/city-S --data M=/bench/city-M \\
        --out /bench/out/20261003-qgis344-v150

One worker process per row, so a crash, a leak or a stray signal connection in
one scenario cannot reach the next one. Each worker writes its own JSON; this
script only collects them, writes ``run.json`` and prints the table.

    --list                 what can be run, and which rows are controls
    --scenario NAME        run only these rows (repeatable)
    --no-controls          skip the control rows
    --profile              cProfile instead of timing, top 25, one file per row
    --expect-digest SHA    refuse a dataset whose manifest digest differs
    --expect-code-sha256   refuse a fiberq tree whose digest differs
    --dry-run              print the worker command lines and stop

Dev tooling. Never shipped: ``make package`` archives ``HEAD:fiberq`` only.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bench_common as common                                        # noqa: E402

WORKER = os.path.join(HERE, "bench_worker.py")

#: Wall-clock ceiling per worker. The worker has its own --budget-s for the cold
#: call; this one catches a process that wedged instead of running slowly.
DEFAULT_TIMEOUT_S = 7200.0


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--code", help="directory holding the fiberq/ tree to measure")
    parser.add_argument("--data", action="append", default=[], metavar="[LABEL=]DIR",
                        help="dataset directory; repeatable, one per size")
    parser.add_argument("--size", default=None,
                        help="label for a --data given without one")
    parser.add_argument("--out", help="directory for the result JSON and profiles")
    parser.add_argument("--label", default=None,
                        help="name for the measured code, e.g. v1.5.0")
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--no-controls", action="store_true")
    parser.add_argument("--only-controls", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--k", type=int, default=None,
                        help="cables for slack_generate (default %d)" % common.DEFAULT_K)
    parser.add_argument("--budget-s", type=float, default=None,
                        help="DNF budget for one cold call")
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--expect-digest", action="append", default=[],
                        metavar="[LABEL=]SHA256")
    parser.add_argument("--expect-code-sha256", default=None,
                        help="refuse to run unless the fiberq tree digest matches")
    parser.add_argument("--allow-label-mismatch", action="store_true",
                        help="permit --label to disagree with the tree's metadata.txt")
    parser.add_argument("--allow-error-records", action="store_true",
                        help="report, instead of failing, a row that logged an error")
    parser.add_argument("--scratch", default=None,
                        help="writable directory for dataset copies (default $TMPDIR)")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--lock", default=None,
                        help="lock file proving no other run is active "
                             "(default <scratch>/bench.lock)")
    parser.add_argument("--max-load", type=float, default=2.0,
                        help="refuse to start when the 1-minute load average is "
                             "above this (default 2.0; 0 disables the check)")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def labelled(values, what):
    """``[LABEL=]VALUE`` pairs into an ordered list of ``(label, value)``."""
    out = []
    for index, raw in enumerate(values):
        if "=" in raw and not os.path.exists(raw):
            label, value = raw.split("=", 1)
        else:
            label, value = None, raw
        if label is None:
            label = "s%d" % (index + 1) if len(values) > 1 else what
        out.append((label, value))
    return out


def chosen(registry, args):
    """The scenario names to run, in registration order."""
    if args.scenario:
        unknown = [n for n in args.scenario if n not in registry]
        if unknown:
            raise SystemExit("unknown scenario(s): %s\nknown: %s"
                             % (unknown, " ".join(registry)))
        wanted = [n for n in registry if n in args.scenario]
    else:
        wanted = list(registry)
    if args.no_controls:
        wanted = [n for n in wanted if not registry[n].control]
    if args.only_controls:
        wanted = [n for n in wanted if registry[n].control]
    return wanted


def worker_command(args, name, size, data, out_dir, digest):
    cmd = [args.python, WORKER, "--code", args.code, "--data", data,
           "--scenario", name, "--size", size,
           "--out", os.path.join(out_dir, "%s-%s.json" % (name, size))]
    if args.label:
        cmd += ["--label", args.label]
    if args.k is not None:
        cmd += ["--k", str(args.k)]
    if args.budget_s is not None:
        cmd += ["--budget-s", str(args.budget_s)]
    if args.scratch:
        cmd += ["--scratch", args.scratch]
    if digest:
        cmd += ["--expect-digest", digest]
    if args.expect_code_sha256:
        cmd += ["--expect-code-sha256", args.expect_code_sha256]
    if args.allow_label_mismatch:
        cmd += ["--allow-label-mismatch"]
    if args.allow_error_records:
        cmd += ["--allow-error-records"]
    if args.profile:
        cmd += ["--profile", os.path.join(out_dir, "profile-%s-%s.txt" % (name, size))]
    return cmd


def run_one(cmd, result_path, timeout_s):
    """Spawn a worker; return ``(status, seconds, stderr_tail)``."""
    if os.path.exists(result_path):
        os.remove(result_path)
    started = time.perf_counter()
    try:
        done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout_s)
        rc, err = done.returncode, done.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as expired:
        rc, err = None, (expired.stderr or b"").decode("utf-8", "replace")
    elapsed = time.perf_counter() - started
    tail = [line for line in err.splitlines() if line.strip()][-8:]
    if rc is None:
        return "timeout", elapsed, tail
    if not os.path.exists(result_path):
        return "crashed(rc=%s)" % rc, elapsed, tail
    return "wrote", elapsed, tail


def main(argv=None):
    common.require_assertions("bench.py")
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        import bench_scenarios as scenarios
    except ImportError as missing:
        # The registry imports qgis.core, so `make bench-list` on a host whose
        # python has no QGIS bindings used to print an import traceback. The
        # whole harness runs inside the QGIS image; say so instead.
        raise SystemExit("the scenario registry needs the QGIS Python bindings "
                         "(%s). Run this inside one of the QGIS images -- see "
                         "tools/bench/README.md, \"Reproducing a run\"." % missing)
    registry = scenarios.REGISTRY

    if args.list:
        print("%-24s %-6s %-9s %s" % ("scenario", "pf", "kind", "post-condition"))
        for name in registry:
            spec = registry[name]
            print("%-24s %-6s %-9s %s" % (name, spec.pf or "-",
                                          "control" if spec.control else "4.1",
                                          spec.post))
        print("\n%d scenarios, %d of them controls (never shown as a 4.1 result)"
              % (len(registry), sum(1 for s in registry.values() if s.control)))
        return 0

    for required in ("code", "data", "out"):
        if not getattr(args, required):
            raise SystemExit("--%s is required (see --help, or --list)" % required)

    datasets = labelled(args.data, args.size or "S")
    digests = dict(labelled(args.expect_digest, datasets[0][0]))
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    run_id = args.run_id or time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    wanted = chosen(registry, args)

    plan = []
    for size, data in datasets:
        common.read_manifest(data)             # fail now, not after an hour
        for name in wanted:
            plan.append((name, size, data, digests.get(size)))

    if args.dry_run:
        for name, size, data, digest in plan:
            print(" ".join(worker_command(args, name, size, data, out_dir, digest)))
        return 0

    # Two guards against measuring a busy machine, which no per-process rule can
    # see. The lock stops a second run of this harness; the load check stops
    # everything else (a build, a backup, a browser).
    scratch = args.scratch or os.environ.get("TMPDIR") or tempfile.gettempdir()
    os.makedirs(scratch, exist_ok=True)
    common.acquire_lock(args.lock or os.path.join(scratch, "bench.lock"))
    load = common.load_average()
    if args.max_load and load and load["1m"] > args.max_load:
        raise SystemExit(
            "the machine is busy: 1-minute load %.2f is above --max-load %.2f. "
            "Timings taken now measure the other work too. Wait, or raise the "
            "limit deliberately." % (load["1m"], args.max_load))

    print("run %s: %d rows (%d scenarios x %d sizes) -> %s"
          % (run_id, len(plan), len(wanted), len(datasets), os.path.basename(out_dir)))
    if load:
        print("         load %.2f before the first row (limit %.2f)"
              % (load["1m"], args.max_load))
    results = []
    environment = None
    for index, (name, size, data, digest) in enumerate(plan, start=1):
        cmd = worker_command(args, name, size, data, out_dir, digest)
        result_path = os.path.join(out_dir, "%s-%s.json" % (name, size))
        print("[%2d/%2d] %-24s %-3s %-4s" % (index, len(plan), name, size,
                                             "ctl" if registry[name].control else "4.1"),
              end="")
        sys.stdout.flush()
        status, elapsed, tail = run_one(cmd, result_path, args.timeout_s)
        row = {"scenario": name, "size": size, "worker": status,
               "worker_s": round(elapsed, 3)}
        if status == "wrote":
            import json
            with open(result_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            timing = payload.get("timing") or {}
            sanity = payload.get("sanity") or {}
            row.update({"status": payload.get("status"),
                        "control": payload.get("control"),
                        "pf": payload.get("pf"),
                        "median_s": timing.get("median_s"),
                        "cold_s": timing.get("cold_s"),
                        "mad_s": timing.get("mad_s"),
                        "n": timing.get("n"),
                        "result_digest": payload.get("result_digest"),
                        "errors": sanity.get("errors"),
                        "swallowed_debug": sanity.get("swallowed_debug"),
                        "detail": payload.get("detail"),
                        "file": os.path.basename(result_path)})
            if payload.get("code", {}).get("sha256"):
                row["code_sha256"] = payload["code"]["sha256"]
            if environment is None and payload.get("env"):
                environment = {"env": payload["env"], "code": payload.get("code"),
                               "canvas": payload.get("canvas"),
                               "dataset": payload.get("dataset")}
            print("%-14s %s" % (row["status"], _one_line(row)))
        else:
            row["status"] = status
            row["stderr_tail"] = tail
            print("%-14s %.1fs" % (status, elapsed))
            for line in tail[-3:]:
                print("         | %s" % line[:160])
        results.append(row)

    shas = {r.get("code_sha256") for r in results if r.get("code_sha256")}
    # The dataset directories and this script's own directory were missing from
    # this map while the worker already had them, and `run.json` is the file
    # that carries `stderr_tail` -- so a worker that died quoting the dataset
    # path published it verbatim (measured: a path outside /home survives the
    # token pass untouched).
    paths = {"out": out_dir, "code": args.code, "harness": HERE,
             "tmp": args.scratch or "/tmp"}
    for size, data in datasets:
        paths["data" if len(datasets) == 1 else "data-%s" % size] = data
    redactor = common.Redactor(paths)
    if environment is not None:
        # One self-describing file for the published raw directory, so a reader
        # does not have to open a result file to learn what it was measured on.
        environment["run_id"] = run_id
        environment["host"] = common.host_env()
        environment["schema"] = common.BENCH_SCHEMA
        common.write_json(os.path.join(out_dir, "env.json"), environment, redactor)
    index_path = os.path.join(out_dir, "run.json")
    common.write_json(index_path, {
        "schema": common.BENCH_SCHEMA,
        "run_id": run_id,
        "label": args.label,
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "code_sha256": sorted(shas),
        "sizes": [size for size, _ in datasets],
        "scenarios": wanted,
        # Split out, not just flagged per row: the controls detect noise and are
        # never shown as a 4.1 result (plan section 1.1, README rule 10), so the
        # index says which is which without a reader having to join on a flag.
        "targets_41": [n for n in wanted if not registry[n].control],
        "controls": [n for n in wanted if registry[n].control],
        "profile_run": bool(args.profile),
        "k": args.k or common.DEFAULT_K,
        "host": common.host_env(),
        "results": results,
    }, redactor)

    bad = [r for r in results if r.get("status") not in ("ok", "skipped", "profiled")]
    print("\n%d rows: %d ok, %d skipped, %d not ok -> %s"
          % (len(results), sum(1 for r in results if r.get("status") == "ok"),
             sum(1 for r in results if r.get("status") == "skipped"),
             len(bad), os.path.basename(index_path)))
    mixed = len(shas) > 1
    if mixed:
        # Not a warning any more. A run whose rows disagree about which tree
        # they measured is not one measurement, so it cannot be published as
        # one -- `--expect-code-sha256` is how a run pins both sides up front.
        print("NOT OK: the rows do not agree on the code digest: %s" % sorted(shas))
    noisy = [r["scenario"] for r in results if r.get("errors")]
    if noisy:
        print("WARNING: error records were logged by: %s" % noisy)
    for row in bad:
        print("  not ok: %-24s %-3s %s %s" % (row["scenario"], row["size"],
                                              row.get("status"),
                                              str(row.get("detail") or "")[:120]))
    return 1 if (bad or mixed) else 0


def _one_line(row):
    """The one-line summary printed per finished row."""
    if row.get("median_s") is None:
        return str(row.get("detail") or "")[:90]
    return ("median %8.3fs  mad %7.4fs  n=%s  cold %8.3fs  err %s/%s"
            % (row["median_s"], row["mad_s"] or 0.0, row["n"], row["cold_s"] or 0.0,
               row.get("errors"), row.get("swallowed_debug")))


if __name__ == "__main__":
    raise SystemExit(main())
