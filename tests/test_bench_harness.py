"""The benchmark harness must refuse to produce a number it cannot stand behind.

``tools/bench/`` is dev-only tooling and CI never benchmarks anything -- a
timing taken on a shared runner is noise, and the plan says so. What CI can
check is the machinery that decides whether a timing is worth publishing:

* every scenario still runs on the XS dataset, holds its own post-condition and
  logs no error record. A scenario that quietly stopped doing the work would
  otherwise be published as a speed-up (`tools/bench/README.md`, fairness rule
  7). The post-conditions are the ``assert``s inside the scenario closures, so
  "the row came back ok" is the test for them.
* a dataset that is not the one the baseline was measured on is refused rather
  than measured (fairness rule 2).

Both go through a subprocess, deliberately. The harness replaces QMessageBox
for the life of the process and disables the logging module, and interpreter
teardown after the dialog scenarios is a reliable SIGSEGV on QGIS 4.0 -- which
is why the harness exits through ``os._exit``. A crash has to cost this test,
not the whole suite.

No timing is asserted anywhere here.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BENCH = REPO_ROOT / "tools" / "bench"
if str(BENCH) not in sys.path:
    sys.path.insert(0, str(BENCH))

import bench_common as common  # noqa: E402

#: Wall-clock ceiling for one harness subprocess. The suite has no timeout
#: plugin, so without this a wedged worker would run until the CI job's own
#: limit. Generous: the whole smoke pass is ~17 s on a laptop.
TIMEOUT_S = 900

#: Cables for the ``slack_generate`` row. The benchmark measures 50; two are
#: enough to show the post-condition ("two terminal slacks per selected cable")
#: holds per cable, and 50 would add 11 seconds to every CI run.
SMOKE_K = 2


def _bench(script, arguments, tmp_path, timeout=TIMEOUT_S):
    """Run a harness script in its own process; returns ``(rc, output)``.

    ``TMPDIR`` and the working directory are pointed at ``tmp_path`` so a
    scenario that writes (``save_gpkg``, the dataset copies) cannot touch the
    repository, and ``QT_QPA_PLATFORM=offscreen`` because the stub iface shows a
    real window.
    """
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(tmp_path), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(BENCH / script)] + arguments,
                          cwd=str(tmp_path), env=environment, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return done.returncode, done.stdout.decode("utf-8", "replace")


@pytest.mark.slow
def test_every_scenario_runs_once_on_the_xs_dataset(city_xs_dataset, tmp_path):
    """One cold call per registered row: ok, post-condition held, no errors.

    Marked slow for the sake of ``-m 'not slow'``, which is a developer's
    shortcut and not a CI setting: the suite runs plain ``pytest``, so this does
    run on both images. It is about 17 s of them, which is what one pass over 22
    scenarios costs; ``--k 2`` is what keeps the slack row from being 11 s of it.
    """
    from bench_scenarios import REGISTRY

    out = tmp_path / "smoke.json"
    code, output = _bench("bench_smoke.py", [
        "--code", str(REPO_ROOT),
        "--data", os.path.dirname(city_xs_dataset["gpkg"]),
        "--out", str(out),
        "--scratch", str(tmp_path),
        "--k", str(SMOKE_K),
        "--expect-digest", city_xs_dataset["digest"],
    ], tmp_path)

    assert out.exists(), f"the harness wrote no result file:\n{output[-4000:]}"
    report = json.loads(out.read_text(encoding="utf-8"))
    rows = report["rows"]

    failed = [(row["scenario"], row.get("detail") or row.get("traceback"))
              for row in rows if row["status"] == "failed"]
    assert failed == [], f"{failed}\n\n{output[-2000:]}"
    skipped = [row["scenario"] for row in rows if row["status"] == "skipped"]
    assert skipped == [], (
        f"{skipped} found no layer to work on, but the XS dataset carries every "
        f"canonical layer -- the layer names or the aliases have drifted")

    noisy = [(row["scenario"], row["sanity"]["error_sample"])
             for row in rows if row["sanity"]["errors"]]
    assert noisy == [], (
        f"error records were logged while the scenario ran: {noisy}. A "
        f"swallowed failure makes the work look cheaper than it is, which is "
        f"what the sanity pass exists to stop.")
    assert sum(row["sanity"]["records"] for row in rows) > 0, (
        "the sanity pass counted no log record at all, anywhere. 'no errors' "
        "then means nothing: get_logger sets propagate = False on every module "
        "logger (fiberq/utils/logger.py), so a probe wired to a handler on the "
        "fiberq parent reports a confident zero for every row")

    assert sorted(row["scenario"] for row in rows) == sorted(REGISTRY), (
        "the smoke run did not cover every registered scenario")
    assert all(row["result_digest"] for row in rows)
    assert all(row["post_condition"] for row in rows), (
        "every scenario documents the post-condition it asserts")
    assert report["dataset"]["digest"] == city_xs_dataset["digest"]
    assert report["counts"]["errors"] == 0
    assert report["status"] == "ok"
    assert code == 0, output[-4000:]


def test_the_harness_refuses_a_dataset_whose_digest_does_not_match(city_xs_dataset,
                                                                   tmp_path):
    """A mismatched dataset is not a slower or faster run. It is not a run."""
    out = tmp_path / "mismatch.json"
    code, output = _bench("bench_worker.py", [
        "--code", str(REPO_ROOT),
        "--data", os.path.dirname(city_xs_dataset["gpkg"]),
        "--scenario", "route_correction",
        "--size", "XS",
        "--out", str(out),
        "--scratch", str(tmp_path),
        "--expect-digest", "deadbeef",
    ], tmp_path, timeout=300)

    assert code == 1, output[-4000:]
    assert out.exists(), f"no result file:\n{output[-4000:]}"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "digest-mismatch"
    assert city_xs_dataset["digest"] in payload["detail"]
    assert "deadbeef" in payload["detail"]
    for key in ("timing", "result", "result_digest", "sanity"):
        assert key not in payload, f"it measured {key} anyway"


def test_an_incomplete_dataset_directory_is_refused(tmp_path):
    """The three shapes of half-generated dataset, each named in the message.

    Cheap: ``bench_common`` is the half of the harness that needs no QGIS.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit) as caught:
        common.read_manifest(str(empty))
    assert "manifest.json" in str(caught.value)

    with pytest.raises(SystemExit) as caught:
        common.read_manifest(str(tmp_path / "not-there"))
    assert "no dataset directory" in str(caught.value)

    two = tmp_path / "two"
    two.mkdir()
    (two / "manifest.json").write_text('{"digest": "x"}', encoding="utf-8")
    for name in ("city_XS.gpkg", "city_S.gpkg", "city_XS.qgz"):
        (two / name).write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        common.read_manifest(str(two))
    assert "2 .gpkg files" in str(caught.value)


# --- the gates that decide whether a timing may be published ---------------
#: A driver that patches one thing in the harness and then runs the worker
#: normally. Written into the test's own ``tmp_path``, never into
#: ``tools/bench``: a production hook that exists so a test can inject a
#: failure is itself a way for a real run to be tampered with.
DRIVER = '''\
import sys
sys.path.insert(0, {bench!r})
import bench_scenarios
import bench_support
import bench_worker
{patch}
bench_worker.main(sys.argv[1:])
'''

#: Log an ERROR record, in the fiberq namespace, from inside the measured call.
#: This is the shape of the thing the sanity pass exists for: on v1.5.0 a
#: failure on one of ~786 debug-only paths leaves the operation half done and
#: the row looking cheaper than it is.
INJECT_ERROR = '''
_original = bench_support.import_fiberq


def _noisy(code_dir):
    info = _original(code_dir)
    import logging
    from fiberq.main_plugin import FiberQPlugin
    inner = FiberQPlugin.check_consistency

    def wrapper(self, *a, **k):
        logging.getLogger("fiberq.injected").error("injected: a swallowed failure")
        return inner(self, *a, **k)
    FiberQPlugin.check_consistency = wrapper
    return info


bench_support.import_fiberq = _noisy
'''

#: Claim a mutating row does not mutate, which is how the fresh-copy rule gets
#: broken by accident -- `mutating` is a hand-written flag on each scenario.
UNMARK_MUTATING = '''
bench_scenarios.REGISTRY["slack_generate"].mutating = False
'''


def _driver(tmp_path, patch, name="driver.py"):
    path = tmp_path / name
    path.write_text(DRIVER.format(bench=str(BENCH), patch=patch), encoding="utf-8")
    return path


def _row(tmp_path, driver, arguments, timeout=TIMEOUT_S):
    """Run ``bench_worker`` through a driver; returns ``(rc, payload, output)``."""
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TMPDIR=str(tmp_path), FIBERQ_LOG_FILE="false")
    done = subprocess.run([sys.executable, str(driver)] + arguments,
                          cwd=str(tmp_path), env=environment, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = done.stdout.decode("utf-8", "replace")
    out = tmp_path / "row.json"
    payload = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return done.returncode, payload, output


def _arguments(city_xs_dataset, tmp_path, scenario, *extra):
    return ["--code", str(REPO_ROOT),
            "--data", os.path.dirname(city_xs_dataset["gpkg"]),
            "--scenario", scenario, "--size", "XS",
            "--out", str(tmp_path / "row.json"),
            "--scratch", str(tmp_path)] + list(extra)


@pytest.mark.slow
def test_a_row_that_logged_an_error_record_is_not_a_measurement(city_xs_dataset,
                                                                tmp_path):
    """Fairness rule 7 says ``errors`` is the number to gate on. So gate on it.

    Before this gate the count was only *reported*: an injected ERROR record
    during the measured call came back ``status: ok`` with a published median
    (measured on XS: median 0.1228 s, ``errors: 1``), and the orchestrator's
    exit code stayed 0 because it only looks at ``status``.
    """
    driver = _driver(tmp_path, INJECT_ERROR)
    code, payload, output = _row(tmp_path, driver,
                                 _arguments(city_xs_dataset, tmp_path,
                                            "route_correction"))
    assert payload is not None, output[-3000:]
    assert payload["status"] == "errors-logged", output[-3000:]
    assert payload["sanity"]["errors"] == 1
    assert "injected" in payload["detail"]
    assert "median_s" not in payload["timing"], "it published a median anyway"
    assert code == 1

    # And the escape hatch, so the gate can be worked around deliberately and
    # never by accident.
    code, payload, output = _row(tmp_path, driver,
                                 _arguments(city_xs_dataset, tmp_path,
                                            "route_correction",
                                            "--allow-error-records"))
    assert payload["status"] == "ok", output[-3000:]
    assert payload["sanity"]["errors"] == 1
    assert payload["timing"]["median_s"] > 0
    assert code == 0


@pytest.mark.slow
def test_a_mutating_row_that_claims_it_is_not_fails_instead_of_being_measured(
        city_xs_dataset, tmp_path):
    """The fresh-copy rule rests on a hand-written flag, so it is checked.

    With ``slack_generate`` marked ``mutating=False`` the repetitions ran on
    top of each other: the slack layer climbed 156 -> 236 features over seven
    calls, each doing more work than the last. The post-condition ("+2 per
    selected cable") still held and the result digest was *identical* to the
    correctly reset run, so nothing in the harness noticed until the pre-call
    state fingerprint existed.
    """
    driver = _driver(tmp_path, UNMARK_MUTATING)
    code, payload, output = _row(tmp_path, driver,
                                 _arguments(city_xs_dataset, tmp_path,
                                            "slack_generate", "--k", "2"))
    assert payload is not None, output[-3000:]
    assert payload["status"] == "unstable-state", output[-3000:]
    assert "Optical slack" in payload["detail"], payload["detail"]
    assert "median_s" not in payload["timing"]
    assert code == 1


@pytest.mark.slow
def test_the_same_row_left_as_registered_is_measured_normally(city_xs_dataset,
                                                              tmp_path):
    """The partner of the test above: the check must not fire on a sound row.

    Without this, ``unstable-state`` could be failing every repetition of
    every row and the suite would still be green.
    """
    code, payload, output = _row(
        tmp_path, BENCH / "bench_worker.py",
        _arguments(city_xs_dataset, tmp_path, "slack_generate", "--k", "2"))
    assert payload is not None, output[-3000:]
    assert payload["status"] == "ok", (payload.get("detail"), output[-3000:])
    assert payload["timing"]["prepares"] == payload["timing"]["n"] + 2, (
        "one dataset copy for the cold call, one for the warm-up and one per "
        "repetition")
    assert payload["state"]["layers"] == len(city_xs_dataset["counts"])
    assert code == 0


@pytest.mark.slow
def test_a_tree_measured_under_the_wrong_name_is_refused(city_xs_dataset, tmp_path):
    """``--label`` is free text; the tree's own ``metadata.txt`` is not.

    The sha256 in the result file proves *which* tree was measured, but only to
    somebody who already knows which one was meant. A run labelled ``v1.5.0``
    against a 1.6.0 tree used to produce a median quite happily.
    """
    code, payload, output = _row(
        tmp_path, BENCH / "bench_worker.py",
        _arguments(city_xs_dataset, tmp_path, "route_correction",
                   "--label", "v9.9.9"))
    assert payload is not None, output[-3000:]
    assert payload["status"] == "label-mismatch", output[-3000:]
    assert "metadata.txt" in payload["detail"]
    assert "timing" not in payload
    assert code == 1


@pytest.mark.slow
def test_a_code_tree_whose_digest_does_not_match_is_refused(city_xs_dataset,
                                                            tmp_path):
    """The code half of fairness rule 2, so an A/B/A session can pin both sides."""
    code, payload, output = _row(
        tmp_path, BENCH / "bench_worker.py",
        _arguments(city_xs_dataset, tmp_path, "route_correction",
                   "--expect-code-sha256", "deadbeef"))
    assert payload is not None, output[-3000:]
    assert payload["status"] == "code-digest-mismatch", output[-3000:]
    assert "deadbeef" in payload["detail"]
    assert payload["code"]["sha256"] in payload["detail"]
    assert "timing" not in payload
    assert code == 1


def test_the_harness_refuses_to_run_with_assertions_disabled(tmp_path):
    """Every post-condition in ``bench_scenarios`` is an ``assert``.

    Under ``-O`` they all vanish. Measured before the refusal existed: a
    ``generate_terminal_slack_for_selected`` patched to a no-op came back
    ``status: ok``, median 0.0012 s against the real 0.4438 s, ``errors: 0`` --
    a 383x speed-up out of nothing. Cheap test: ``--list`` touches no dataset.
    """
    environment = dict(os.environ, PYTHONOPTIMIZE="1", QT_QPA_PLATFORM="offscreen")
    for script in ("bench.py", "bench_worker.py", "bench_smoke.py"):
        done = subprocess.run([sys.executable, str(BENCH / script), "--list"],
                              cwd=str(tmp_path), env=environment, timeout=300,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = done.stdout.decode("utf-8", "replace")
        assert done.returncode != 0, f"{script} ran under -O:\n{output}"
        assert "assertions disabled" in output, f"{script}:\n{output}"


def test_the_state_fingerprint_notices_one_added_feature(qgis_app, city_xs_dataset,
                                                         tmp_path):
    """In-process, so the subprocess tests above are not the only evidence.

    On a copy: the fixture is session-scoped and two other tests read the same
    GeoPackage, so committing a feature into it would be this test rewriting
    the dataset whose digest the suite pins.
    """
    import shutil

    from qgis.core import QgsFeature, QgsProject

    import bench_support as support

    for key in ("gpkg", "qgz"):
        shutil.copy(city_xs_dataset[key], tmp_path)
    project = QgsProject.instance()
    project.clear()
    assert project.read(str(tmp_path / os.path.basename(city_xs_dataset["qgz"])))
    try:
        before = support.state_fingerprint()
        # Keyed by the *project* layer name, which is not always the canonical
        # schema name the manifest counts by ("Optical slacks" on the map,
        # "Optical slack" in the schema), so the lengths are what match.
        assert len(before) == len(city_xs_dataset["counts"]) > 0
        assert support.state_difference(before, before) == {}

        layer = [lyr for lyr in project.mapLayers().values()
                 if lyr.name() == "Poles"][0]
        assert layer.startEditing()
        assert layer.addFeature(QgsFeature(layer.fields()))
        assert layer.commitChanges(), layer.commitErrors()

        difference = support.state_difference(before, support.state_fingerprint())
        assert list(difference) == ["Poles"]
        assert difference["Poles"] == [before["Poles"], before["Poles"] + 1]
    finally:
        project.clear()


def test_the_redactor_drops_a_hostname_that_starts_with_the_username(monkeypatch,
                                                                     tmp_path):
    """Longest token first, or the username eats the start of the hostname.

    Measured on the author's machine, whose hostname is
    ``<user>-Precision-7510``: replacing the username first left
    ``<redacted>-Precision-7510`` in a file about to be published, and the
    "prove nothing is left" check then passed, because no whole token remained.
    """
    import getpass
    import socket

    monkeypatch.setattr(getpass, "getuser", lambda: "alice")
    monkeypatch.setattr(socket, "gethostname", lambda: "alice-Precision-7510")
    monkeypatch.setenv("HOME", "/home/alice")

    redactor = common.Redactor({"out": str(tmp_path)})
    scrubbed = redactor.scrub_text("alice ran this on alice-Precision-7510")
    assert "Precision" not in scrubbed, scrubbed
    assert redactor.leaks(scrubbed) == []


def test_the_redactor_drops_a_whole_home_directory(monkeypatch, tmp_path):
    """The home *pattern* has to be applied before the username token.

    Otherwise ``/home/alice/Documents/big.gpkg`` becomes
    ``/home/<redacted>/Documents/big.gpkg`` -- which the pattern can no longer
    match, so half a user path reaches the published file.
    """
    import getpass
    import socket

    monkeypatch.setattr(getpass, "getuser", lambda: "alice")
    monkeypatch.setattr(socket, "gethostname", lambda: "box")
    monkeypatch.setenv("HOME", "/home/alice")

    redactor = common.Redactor({"out": str(tmp_path)})
    scrubbed = redactor.scrub_text("could not open /home/alice/Documents/big.gpkg")
    assert scrubbed == "could not open <redacted>/Documents/big.gpkg", scrubbed
    assert redactor.leaks(scrubbed) == []


def test_write_json_refuses_a_payload_it_cannot_clean(monkeypatch, tmp_path):
    """The last line of defence: redact, prove, then write.

    Blanking a leaking field and recording its name is the first response; this
    checks the second, for a field the blanking cannot reach.
    """
    import getpass
    import socket

    monkeypatch.setattr(getpass, "getuser", lambda: "alice")
    monkeypatch.setattr(socket, "gethostname", lambda: "box")
    monkeypatch.setenv("HOME", "/home/alice")

    redactor = common.Redactor({"out": str(tmp_path)})
    target = tmp_path / "leaky.json"
    common.write_json(str(target), {"detail": "/home/alice/x"}, redactor)
    assert "alice" not in target.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        common.write_text(str(tmp_path / "leaky.txt"), "ran as alice",
                          _BrokenRedactor({"out": str(tmp_path)}))
    assert "refusing to write" in str(caught.value)


class _BrokenRedactor(common.Redactor):
    """A redactor that forgets to redact, to prove the proof step works."""

    def scrub_text(self, value):
        return value


def test_a_second_run_on_the_same_machine_is_refused(tmp_path):
    """Two benchmark runs at once measure each other, so the lock refuses.

    This is a regression test for a real incident, not a hypothetical: a second
    sequence (size L) was launched while the first (sizes S and M) was still
    going, both pinned to the same five cores. Every row of the first sequence
    then timed a machine running two QGIS processes. The numbers looked
    plausible and nothing objected -- the only hint was the performance governor
    coming out slower than powersave. Contention is a property of the machine,
    so no amount of per-process checking can see it.
    """
    lock = tmp_path / "bench.lock"
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import bench_common; "
         "bench_common.acquire_lock(%r); print('held', flush=True); "
         "sys.stdin.readline()" % (str(BENCH), str(lock))],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        assert holder.stdout.readline().strip() == b"held"
        second = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); import bench_common; "
             "bench_common.acquire_lock(%r)" % (str(BENCH), str(lock))],
            timeout=60, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert second.returncode != 0
        assert b"another benchmark run holds" in second.stdout
    finally:
        holder.stdin.close()
        holder.wait(timeout=60)

    # ... and the lock is released with the process, so the next run may start.
    after = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import bench_common; "
         "bench_common.acquire_lock(%r); print('ok')" % (str(BENCH), str(lock))],
        timeout=60, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert after.returncode == 0, after.stdout
    assert b"ok" in after.stdout


def test_a_busy_machine_is_refused(city_xs_dataset, tmp_path):
    """``--max-load`` stops a run that would measure someone else's work."""
    if common.load_average() is None:
        pytest.skip("no load average on this platform")
    code, output = _bench("bench.py", [
        "--code", str(REPO_ROOT), "--data", "XS=" + str(pathlib.Path(
            city_xs_dataset["manifest"]).parent),
        "--out", str(tmp_path / "out"), "--scratch", str(tmp_path),
        "--scenario", "record_add", "--max-load", "0.0001",
    ], tmp_path)
    assert code != 0
    assert "the machine is busy" in output
