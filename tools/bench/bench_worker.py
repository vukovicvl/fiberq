#!/usr/bin/env python3
"""Run ONE WP4 benchmark scenario in its own process and write one JSON file.

    python3 tools/bench/bench_worker.py --code DIR --data DIR --scenario NAME \\
        --size S --out /tmp/out/schematic_open-S.json

Normally driven by ``bench.py``, which spawns one of these per scenario x size
so a crash, a leak or a stray signal connection cannot reach another scenario.
Run it by hand to debug a single row.

Exit code 0 means the JSON was written and the scenario ran or was skipped; 1
means the JSON was written and says why it failed. A missing file means the
process died -- which is a result too, and ``bench.py`` records it as a crash.

Dev tooling. Never shipped: ``make package`` archives ``HEAD:fiberq`` only.
"""
import argparse
import io
import os
import shutil
import signal
import sys
import time
import traceback

# The probe has to be in place before fiberq is imported: get_logger() reads this
# once per module logger and would otherwise fix every logger at WARNING, where
# the ~786 debug-only handlers are invisible. bench_support.quiet_logging() puts
# the levels back for the timed region, so this costs nothing it measures.
#
# Assigned, not setdefault: an operator who happens to have FIBERQ_LOG_LEVEL
# exported would otherwise blind the sanity pass to exactly the records it is
# there to count, and FIBERQ_LOG_FILE=true would put file I/O in the timed
# region. The measurement cannot depend on the shell it was started from.
os.environ["FIBERQ_LOG_LEVEL"] = "DEBUG"
os.environ["FIBERQ_LOG_FILE"] = "false"

import bench_common as common                                        # noqa: E402
import bench_support as support                                      # noqa: E402

#: Seconds a single cold call may take before the scenario is recorded DNF
#: instead of measured. The L dataset has quadratic paths that would otherwise
#: run for hours; the plan's section 1.1 table calls for a DNF budget.
DEFAULT_BUDGET_S = 1800.0


class BudgetExceeded(Exception):
    """The cold call ran past --budget-s."""


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--code", required=True,
                        help="directory holding the fiberq/ tree to measure")
    parser.add_argument("--data", required=True,
                        help="dataset directory (city.gpkg, city.qgz, manifest.json)")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--size", default=None, help="label for the dataset, e.g. S")
    parser.add_argument("--out", required=True, help="result JSON to write")
    parser.add_argument("--scratch", default=None,
                        help="writable directory for the dataset copies")
    parser.add_argument("--k", type=int, default=common.DEFAULT_K,
                        help="cables for slack_generate (default %d)" % common.DEFAULT_K)
    parser.add_argument("--label", default=None, help="name for the measured code")
    parser.add_argument("--expect-digest", default=None,
                        help="refuse to run unless the manifest digest matches")
    parser.add_argument("--expect-code-sha256", default=None,
                        help="refuse to run unless the fiberq tree digest matches")
    parser.add_argument("--allow-label-mismatch", action="store_true",
                        help="permit --label to disagree with the tree's metadata.txt")
    parser.add_argument("--allow-error-records", action="store_true",
                        help="report, instead of failing, a row that logged an error")
    parser.add_argument("--budget-s", type=float, default=DEFAULT_BUDGET_S)
    parser.add_argument("--profile", default=None,
                        help="write a cProfile report here instead of timing")
    parser.add_argument("--keep-samples", type=int, default=5)
    return parser.parse_args(argv)


def budget(seconds):
    """Arm a wall-clock budget for the next call. Returns a disarm callable.

    SIGALRM only lands between Python bytecodes, so a scenario stuck inside one
    long C++ call runs past the budget. That is a limitation, not a bug: every
    hot path WP4 measures loops in Python.
    """
    def fired(signum, frame):
        raise BudgetExceeded("over the %.0f s budget" % seconds)
    previous = signal.signal(signal.SIGALRM, fired)
    signal.setitimer(signal.ITIMER_REAL, seconds)

    def disarm():
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)
    return disarm


def timed(call):
    """``(seconds, value)`` for one call of the scenario body."""
    started = time.perf_counter()
    value = call()
    return time.perf_counter() - started, value


class Session:
    """Everything a scenario needs, rebuilt from scratch for each repetition."""

    def __init__(self, args, scenarios, manifest, app):
        self.args = args
        self.scenarios = scenarios
        self.manifest = manifest
        #: Held for the life of the run: a collected QgsApplication takes the
        #: canvas and every widget with it.
        self.app = app
        self.scratch = args.scratch or os.environ.get("TMPDIR") or "/tmp"
        self.iface = support.StubIface()
        self.save_dir = os.path.join(self.scratch, "bench_save")
        os.makedirs(self.save_dir, exist_ok=True)
        self.patches = support.patch_modals(os.path.join(self.save_dir, "saved.gpkg"))
        missing = [p for p in support.EXPECTED_PATCHES if p not in self.patches]
        if missing:
            raise SystemExit("modal patches did not apply: %s" % missing)
        self.prepares = 0
        self.fixed_ids = None
        self.load_s = None
        self.layer_count = None
        self.plugin = None
        self.after = None
        #: Dataset copies the previous repetition finished with. Deleted once the
        #: next project read has replaced them: an L repetition copies ~20 MB, and
        #: 22 scenarios x 9 repetitions of that would be several GB of scratch.
        self.stale = []
        common.before_exit(self.discard_copies)

    def discard_copies(self):
        """Delete the dataset copies on the way out, including the last one."""
        for path in self.stale + [self.save_dir]:
            shutil.rmtree(path, ignore_errors=True)
        self.stale = []

    def prepare(self, scenario=None):
        """Fresh dataset copy, fresh project, fresh plugin, fresh closure.

        ``scenario`` is the row to build, and defaults to the one this process
        was started for. ``bench_smoke.py`` passes a name per call, because it
        runs every row once in one process where this module runs one row many
        times.
        """
        from fiberq.main_plugin import FiberQPlugin

        name = scenario or self.args.scenario
        work, files = support.copy_dataset(self.args.data, self.scratch)
        self.load_s, self.layer_count = support.read_project(work, files)
        for path in self.stale:                # nothing references these any more:
            shutil.rmtree(path, ignore_errors=True)   # read_project cleared them
        self.stale = []
        self.fixed_ids = self.check_layer_ids()
        self.plugin = FiberQPlugin(self.iface)
        for manager in ("cable_manager", "slack_manager", "route_manager",
                        "undo_manager"):
            if getattr(self.plugin, manager, None) is None:
                raise SystemExit("the plugin came up without a %s" % manager)
        ctx = {"iface": self.iface, "plugin": self.plugin, "app": self.app,
               "data": self.args.data, "work": work, "files": files,
               "scratch": self.scratch,
               "k": self.args.k, "keep": [],
               "save_path": os.path.join(self.save_dir, "saved.gpkg"),
               "layer_count": self.layer_count, "temp_dirs": []}
        built = self.scenarios.REGISTRY[name].factory(ctx)
        self.stale = [work] + list(ctx["temp_dirs"])
        self.prepares += 1
        if isinstance(built, tuple):
            run, self.after = built
        else:
            run, self.after = built, None
        return run

    def check_layer_ids(self):
        """Prove the project is the one the manifest describes.

        The generator pins every layer id (``fiberq_bench_<table>``) precisely so
        a result can name a layer without a random uuid in it. If the ids do not
        match, the dataset is not the one the digest belongs to.
        """
        from qgis.core import QgsProject
        wanted = set((self.manifest.get("layer_ids") or {}).values())
        if not wanted:
            return None
        have = set(QgsProject.instance().mapLayers().keys())
        missing = sorted(wanted - have)
        if missing:
            raise SystemExit("the project is missing the manifest's fixed layer ids: %s"
                             % missing[:4])
        return len(wanted)

    def finish(self):
        if self.after is not None:
            self.after()


def same_state(cold_state, which):
    """``None`` when this call starts from the cold call's state, else why not.

    Called outside the timed region, immediately before each call, so every
    repetition is known to have done the same amount of work -- not assumed to,
    on the strength of a hand-written ``mutating`` flag.
    """
    now = support.state_fingerprint()
    difference = support.state_difference(cold_state, now)
    if not difference:
        return None
    return ("%s did not start from the state the cold call did: %s. A mutating "
            "scenario gets a fresh dataset copy before every repetition; this "
            "one did not, so the repetitions measured different amounts of "
            "work. Check the row's mutating flag."
            % (which, dict(list(difference.items())[:6])))


def profile_run(session, run, args, result):
    """One profiled call in its own process, reported two ways, top 25 each."""
    import cProfile
    import pstats
    profiler = cProfile.Profile()
    profiler.enable()
    value = run()
    profiler.disable()
    session.finish()
    text = io.StringIO()
    text.write("# FiberQ WP4 benchmark profile\n")
    text.write("# scenario   %s\n" % args.scenario)
    text.write("# size       %s\n" % (args.size or "?"))
    text.write("# code        %s (%s)\n" % (result["code"]["version"],
                                            result["code"]["sha256"][:16]))
    text.write("# qgis       %s / Qt %s / PyQt %s\n" % (result["env"]["qgis"],
                                                        result["env"]["qt"],
                                                        result["env"]["pyqt"]))
    text.write("# dataset    %s features, digest %s\n"
               % (result["dataset"]["features"],
                  (result["dataset"]["digest"] or "?")[:16]))
    text.write("# result     %s\n\n" % common.canonical(value)[:300])
    for sort in ("cumulative", "tottime"):
        text.write("\n==== sorted by %s (top 25) ====\n" % sort)
        pstats.Stats(profiler, stream=text).sort_stats(sort).print_stats(25)
    return value, text.getvalue()


def main(argv):
    common.require_assertions("bench_worker.py")
    args = parse_args(argv)
    code_dir = support.prepend_code_path(args.code)
    bytecode = support.precompile_code(
        code_dir, support.pycache_root(args.scratch))
    app = support.start_qgis()
    code = dict(support.import_fiberq(code_dir), **bytecode)
    import bench_scenarios as scenarios

    manifest = common.read_manifest(args.data)
    redactor = common.Redactor({"code": code_dir, "data": args.data,
                                "out": os.path.dirname(os.path.abspath(args.out)),
                                "harness": os.path.dirname(os.path.abspath(__file__)),
                                "tmp": args.scratch or "/tmp"})
    result = {"schema": common.BENCH_SCHEMA,
              "scenario": args.scenario,
              "size": args.size or manifest.get("size"),
              "status": "error",
              "label": args.label,
              "code": code,
              "env": dict(support.qgis_env(), **common.host_env()),
              "dataset": common.dataset_summary(args.data, manifest),
              "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    if args.scenario not in scenarios.REGISTRY:
        result["status"] = "unknown-scenario"
        result["detail"] = "not one of %s" % sorted(scenarios.REGISTRY)
        common.write_json(args.out, result, redactor)
        common.flush_and_exit(1)

    spec = scenarios.REGISTRY[args.scenario]
    result.update(spec.describe())
    expected = args.expect_digest
    actual = common.manifest_digest(manifest)
    if expected and actual != expected:
        result["status"] = "digest-mismatch"
        result["detail"] = "dataset digest %s, expected %s" % (actual, expected)
        common.write_json(args.out, result, redactor)
        common.flush_and_exit(1)

    # The code half of the same rule. The sha256 pins which tree was measured;
    # these two stop a tree being measured under the wrong name. Measured
    # before they existed: --label v1.5.0 against a tree whose metadata.txt
    # says 1.6.0 ran to completion and published a median.
    if args.expect_code_sha256 and code["sha256"] != args.expect_code_sha256:
        result["status"] = "code-digest-mismatch"
        result["detail"] = ("fiberq tree digest %s, expected %s"
                            % (code["sha256"], args.expect_code_sha256))
        common.write_json(args.out, result, redactor)
        common.flush_and_exit(1)
    complaint = support.label_complaint(args.label, code.get("version"))
    if complaint and not args.allow_label_mismatch:
        result["status"] = "label-mismatch"
        result["detail"] = complaint
        common.write_json(args.out, result, redactor)
        common.flush_and_exit(1)
    if complaint:
        result["label_mismatch_allowed"] = complaint

    qgis_log = support.QgisLogProbe()
    support.quiet_logging()
    session = None
    try:
        session = Session(args, scenarios, manifest, app)
        run = session.prepare()
        missing = spec.missing_layers()
        if missing:
            result["status"] = "skipped"
            result["detail"] = "the dataset has no layer for %s" % missing
            common.write_json(args.out, result, redactor)
            common.flush_and_exit(0)

        result["patches"] = sorted(session.patches)
        result["canvas"] = {"size_px": session.iface.canvas_size(),
                            "metres_per_pixel": support.METRES_PER_PIXEL}
        result["fixed_layer_ids"] = session.fixed_ids

        # --- the cold call doubles as the sanity pass ---------------------
        # The machine's load is recorded around the measurement because no
        # per-process check can see contention: a second benchmark run, or a
        # build, inflates every row here while this process looks healthy.
        load_before = common.load_average()
        cold_state = support.state_fingerprint()
        probe, restore = support.sanity_on(args.keep_samples)
        disarm = budget(args.budget_s)
        try:
            cold_s, value = timed(run)
        except BudgetExceeded as exc:
            result["status"] = "dnf"
            result["detail"] = str(exc)
            result["sanity"] = support.sanity_off(probe, restore)
            common.write_json(args.out, result, redactor)
            common.flush_and_exit(0)
        finally:
            disarm()
        sanity = support.sanity_off(probe, restore)
        session.finish()

        result["sanity"] = dict(sanity, qgis_log=qgis_log.report(),
                                message_bar=session.iface.messageBar().log[-4:])
        result["result"] = value
        result["result_digest"] = common.result_digest(value)
        result["state"] = {"layers": len(cold_state),
                           "digest": common.plain_digest(cold_state),
                           "cold": cold_state}
        result["timing"] = {"cold_s": round(cold_s, 6), "load_s": session.load_s,
                            # cold_s is the one call the sanity probe is
                            # installed for: every fiberq logger is at DEBUG and
                            # a record factory counts what they emit. Comparable
                            # with another cold_s, not with a median.
                            "cold_with_sanity_probe": True,
                            "cold_log_records": sanity.get("records")}

        # The sanity pass is worth nothing if its count is only reported.
        # README fairness rule 7 says `errors` is the number to gate on; until
        # this was here, an injected ERROR record during the measured call came
        # back `status: ok` with a published median (measured).
        if sanity.get("errors") and not args.allow_error_records:
            result["status"] = "errors-logged"
            result["detail"] = ("%d error record(s) while the measured call ran: "
                                "%s -- pass --allow-error-records to measure it "
                                "anyway" % (sanity["errors"],
                                            sanity.get("error_sample")))
            common.write_json(args.out, result, redactor)
            common.flush_and_exit(1)

        if args.profile:
            if spec.mutating:
                run = session.prepare()
            value, report = profile_run(session, run, args, result)
            common.write_text(args.profile, report, redactor)
            result["status"] = "profiled"
            result["profile"] = os.path.basename(args.profile)
            result["timing"]["policy"] = "profiled run: timings not comparable"
            common.write_json(args.out, result, redactor)
            common.flush_and_exit(0)

        # --- one warm-up, then the repetitions the policy allows ----------
        if spec.mutating:
            run = session.prepare()
        drift = same_state(cold_state, "the warm-up")
        if drift:
            result["status"] = "unstable-state"
            result["detail"] = drift
            common.write_json(args.out, result, redactor)
            common.flush_and_exit(1)
        warm_s, _ = timed(run)
        session.finish()
        reps, policy = common.repetitions(warm_s)
        times = []
        for _ in range(reps):
            if spec.mutating:
                run = session.prepare()
            drift = same_state(cold_state, "repetition %d" % (len(times) + 1))
            if drift:
                result["status"] = "unstable-state"
                result["detail"] = drift
                break
            seconds, repeat_value = timed(run)
            session.finish()
            times.append(seconds)
            if common.result_digest(repeat_value) != result["result_digest"]:
                result["status"] = "unstable"
                result["detail"] = ("repetition %d produced a different result: %s"
                                    % (len(times), common.canonical(repeat_value)[:200]))
                break
        result["timing"].update(common.summarise(times))
        result["timing"]["load"] = {"before": load_before,
                                    "after": common.load_average()}
        result["timing"].update({"warmup_s": round(warm_s, 6), "policy": policy,
                                 "runs": [round(t, 6) for t in times],
                                 "prepares": session.prepares})
        if result["status"] == "error":
            result["status"] = "ok"
        common.write_json(args.out, result, redactor)
        common.flush_and_exit(0 if result["status"] == "ok" else 1)
    except BaseException:
        result["status"] = "failed"
        result["traceback"] = traceback.format_exc().splitlines()[-25:]
        if session is not None:
            result["message_bar"] = session.iface.messageBar().log[-4:]
        common.write_json(args.out, result, redactor)
        common.flush_and_exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
