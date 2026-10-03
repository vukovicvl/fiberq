#!/usr/bin/env python3
"""Run every WP4 benchmark scenario once, as a check on the harness itself.

    python3 tools/bench/bench_smoke.py --code . --out /tmp/smoke.json \\
        --data /tmp/fiberq-city/city_XS

Not a measurement, and never published. One cold call per scenario, in one
process, with the sanity pass on. It answers the question plan section 1.6 asks
of the harness -- "does every scenario still resolve its layers, hold its own
post-condition and run without logging an error on this dataset?" -- which is
also what ``tests/test_bench_harness.py`` asks in CI.

One process for all rows, where ``bench.py`` gives each row its own: fairness
rule 9 (nothing leaks between scenarios) is there to protect a published
number, and a smoke run publishes none. The 22 QgsApplication starts it saves
are most of the cost. The timings in the output are there to tell a human which
row is slow; they are not comparable with anything, having had no warm-up and
no repetitions.

But still a *process*, not something the test suite can call in-process:
``patch_modals`` replaces QMessageBox for good, ``quiet_logging`` disables the
logging module, and interpreter teardown after the dialog scenarios is a
deterministic SIGSEGV on QGIS 4.0 (see the README). A crash has to cost this
run and not the whole test suite.

Dev tooling. Never shipped: ``make package`` archives ``HEAD:fiberq`` only.
"""
import argparse
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bench_common as common                                        # noqa: E402
# Imported before fiberq is: bench_worker sets FIBERQ_LOG_LEVEL=DEBUG at module
# scope, and get_logger() reads it once per module logger.
import bench_worker as worker                                        # noqa: E402
import bench_support as support                                      # noqa: E402

#: Cables for the ``slack_generate`` row. The benchmark measures 50; a smoke run
#: only has to show the post-condition holds, and 50 cables are 11 of the 17
#: seconds the whole pass costs.
DEFAULT_K = 2


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--code", required=True,
                        help="directory holding the fiberq/ tree to exercise")
    parser.add_argument("--data", required=True, help="dataset directory")
    parser.add_argument("--out", required=True, help="result JSON to write")
    parser.add_argument("--scratch", default=None,
                        help="writable directory for the dataset copies")
    parser.add_argument("--scenario", action="append", default=[],
                        help="run only these rows; repeatable")
    parser.add_argument("--size", default=None, help="label for the dataset")
    parser.add_argument("--k", type=int, default=DEFAULT_K,
                        help="cables for slack_generate (default %d)" % DEFAULT_K)
    parser.add_argument("--expect-digest", default=None,
                        help="refuse to run unless the manifest digest matches")
    parser.add_argument("--keep-samples", type=int, default=3)
    return parser.parse_args(argv)


def run_row(session, spec, keep):
    """Build one scenario, call it once, and report what happened.

    Every failure is caught, including ``SystemExit``: the scenario factories
    raise it when the dataset cannot support a row, and one such row must be
    reported by name rather than take the other twenty-one with it.
    """
    row = spec.describe()
    started = time.perf_counter()
    try:
        run = session.prepare(spec.name)
        missing = spec.missing_layers()
        if missing:
            row.update(status="skipped",
                       detail="the dataset has no layer for %s" % missing)
            return row
        probe, restore = support.sanity_on(keep)
        try:
            value = run()
        finally:
            row["sanity"] = support.sanity_off(probe, restore)
        session.finish()
    except BaseException:
        row["status"] = "failed"
        row["traceback"] = traceback.format_exc().splitlines()[-12:]
        return row
    row.update(status="ok", result=value, result_digest=common.result_digest(value),
               seconds=round(time.perf_counter() - started, 3))
    return row


def main(argv=None):
    # Same refusal as the benchmark proper: under -O every post-condition in
    # bench_scenarios is compiled away, and this script's whole job is to check
    # that they hold.
    common.require_assertions("bench_smoke.py")
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    code_dir = support.prepend_code_path(args.code)
    bytecode = support.precompile_code(
        code_dir, support.pycache_root(args.scratch))
    app = support.start_qgis()
    code = dict(support.import_fiberq(code_dir), **bytecode)
    import bench_scenarios as scenarios

    manifest = common.read_manifest(args.data)
    redactor = common.Redactor({"code": code_dir, "data": args.data,
                                "out": os.path.dirname(os.path.abspath(args.out)),
                                "harness": HERE,
                                "tmp": args.scratch or "/tmp"})
    result = {"schema": common.BENCH_SCHEMA,
              "mode": "smoke",
              "not_a_measurement": "one cold call per row, no warm-up, no "
                                   "repetitions: these seconds are not comparable",
              "size": args.size or manifest.get("size"),
              "status": "error",
              "k": args.k,
              "code": code,
              "env": dict(support.qgis_env(), **common.host_env()),
              "dataset": common.dataset_summary(args.data, manifest),
              "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    unknown = [name for name in args.scenario if name not in scenarios.REGISTRY]
    if unknown:
        result["status"] = "unknown-scenario"
        result["detail"] = "%s is not one of %s" % (unknown, sorted(scenarios.REGISTRY))
        common.write_json(args.out, result, redactor)
        common.flush_and_exit(1)

    actual = common.manifest_digest(manifest)
    if args.expect_digest and actual != args.expect_digest:
        result["status"] = "digest-mismatch"
        result["detail"] = "dataset digest %s, expected %s" % (actual,
                                                               args.expect_digest)
        common.write_json(args.out, result, redactor)
        common.flush_and_exit(1)

    wanted = [n for n in scenarios.REGISTRY if not args.scenario or n in args.scenario]
    qgis_log = support.QgisLogProbe()
    support.quiet_logging()
    rows = []
    try:
        # The same Session the benchmark uses -- one stub iface, one set of
        # modal patches, a fresh dataset copy and a fresh plugin per row. It
        # reads --data, --scratch and --k off the namespace; the row comes from
        # prepare(), so our list-valued --scenario is never consulted.
        session = worker.Session(args, scenarios, manifest, app)
        for index, name in enumerate(wanted, start=1):
            row = run_row(session, scenarios.REGISTRY[name], args.keep_samples)
            rows.append(row)
            print("[%2d/%2d] %-24s %-8s err %s" % (
                index, len(wanted), name, row["status"],
                (row.get("sanity") or {}).get("errors")))
            sys.stdout.flush()
        result["patches"] = sorted(session.patches)
        result["canvas"] = {"size_px": session.iface.canvas_size(),
                            "metres_per_pixel": support.METRES_PER_PIXEL}
        result["fixed_layer_ids"] = session.fixed_ids
    except BaseException:
        result["status"] = "failed"
        result["traceback"] = traceback.format_exc().splitlines()[-25:]

    result["rows"] = rows
    result["qgis_log"] = qgis_log.report()
    tally = {state: sum(1 for row in rows if row.get("status") == state)
             for state in ("ok", "skipped", "failed")}
    tally["scenarios"] = len(rows)
    tally["errors"] = sum((row.get("sanity") or {}).get("errors", 0) for row in rows)
    result["counts"] = tally
    if result["status"] != "failed":
        result["status"] = "ok" if tally["failed"] == 0 else "failed"
    common.write_json(args.out, result, redactor)
    print("%d rows: %d ok, %d skipped, %d failed, %d error records"
          % (tally["scenarios"], tally["ok"], tally["skipped"], tally["failed"],
             tally["errors"]))
    for row in rows:
        if row.get("status") != "ok":
            why = row.get("detail") or row.get("traceback") or ""
            print("  not ok: %-24s %s" % (row["scenario"], str(why)[:160]))
    common.flush_and_exit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
