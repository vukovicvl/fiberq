#!/usr/bin/env python3
"""Pieces of the WP4 benchmark harness that need no QGIS.

Imported by both the orchestrator (``bench.py``, which never touches QGIS) and
the worker (``bench_worker.py``, which does). Everything here is deliberately
boring: digests, the timing policy, the environment probe and the redactor that
keeps user paths and hostnames out of the published JSON.

Dev tooling. Never shipped: ``make package`` archives ``HEAD:fiberq`` only.
"""
import getpass
import hashlib
import json
import os
import platform
import re
import socket
import statistics
import sys

#: Bumped when the shape of a result file changes, so an old file is never
#: silently compared against a new one.
BENCH_SCHEMA = "fiberq-bench/1"

#: How many cables "Generate terminal slacks" is measured over (plan section
#: 1.1). Lives here, not in the scenario module, so the CLI default and the
#: scenario cannot drift apart.
DEFAULT_K = 50

#: Files that are part of the measured code but carry no behaviour, so they are
#: skipped by the code digest (a stale .pyc must not change the identity of a
#: tree that is otherwise byte-identical to the tag).
_CODE_SKIP_DIRS = ("__pycache__", ".git")
_CODE_SKIP_SUFFIX = (".pyc", ".pyo")


def require_assertions(who):
    """Refuse to run with assertions stripped. Called first by every entry point.

    Every scenario post-condition in ``bench_scenarios`` is an ``assert``, so
    under ``-O`` or ``PYTHONOPTIMIZE=1`` they all vanish and an operation that
    silently did nothing is timed and published. Measured on the XS dataset: a
    ``generate_terminal_slack_for_selected`` patched to a no-op came back
    ``status: ok``, median 0.0012 s against the real 0.4438 s -- a 383x speed-up
    out of thin air.
    """
    if not __debug__:
        raise SystemExit(
            "%s refuses to run with assertions disabled (-O / PYTHONOPTIMIZE): "
            "every scenario post-condition is an assert, so an operation that "
            "did nothing at all would be timed and published as a speed-up"
            % who)


def tree_sha256(root):
    """``(hexdigest, file_count, byte_count)`` over the contents of ``root``.

    Path-and-content, in sorted relative-path order, so the digest does not
    depend on the directory walk order or on where the tree is mounted. This is
    the number that makes a "before" measurement checkable: it pins the code
    that was measured, not the label somebody typed.
    """
    digest = hashlib.sha256()
    count = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _CODE_SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(_CODE_SKIP_SUFFIX):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            with open(full, "rb") as handle:
                payload = handle.read()
            digest.update(rel.replace(os.sep, "/").encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(payload).digest())
            count += 1
            total += len(payload)
    return digest.hexdigest(), count, total


def canonical(obj):
    """A stable text form of a scenario result, for the result digest."""
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=repr)
    except (TypeError, ValueError):
        return repr(obj)


def result_digest(obj):
    """sha256 over the canonical form of a scenario result.

    Keys starting with ``_`` are reported but left out of the digest: they are
    facts about *how* the work happened (was a hidden rebuild scheduled?), which
    is exactly what an optimisation is allowed to change. Everything else is
    data the user would see, and it must match before and after.
    """
    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if not str(k).startswith("_")}
    return plain_digest(obj)


def plain_digest(obj):
    """sha256 over the canonical form, with no key filtered out.

    Used for the pre-call state fingerprint, where every key matters: a layer
    whose name happens to start with an underscore must still be compared.
    """
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def repetitions(seconds):
    """``(n, policy)`` for a call that takes ``seconds`` -- the plan's section 1.1 rule."""
    if seconds < 2.0:
        return 7, "N=7 (warm-up under 2 s)"
    if seconds <= 60.0:
        return 3, "N=3 (warm-up 2-60 s)"
    return 1, "N=1 (warm-up over 60 s)"


def summarise(times):
    """Median, min, max and MAD of a list of seconds (``None`` when empty).

    MAD is the median absolute deviation, not the standard deviation: a single
    slow run (a page fault, a neighbour process) must not widen the spread that
    decides whether two ranges overlap.
    """
    if not times:
        return {"median_s": None, "min_s": None, "max_s": None, "mad_s": None, "n": 0}
    median = statistics.median(times)
    return {"median_s": round(median, 6),
            "min_s": round(min(times), 6),
            "max_s": round(max(times), 6),
            "mad_s": round(statistics.median([abs(t - median) for t in times]), 6),
            "n": len(times)}


def dataset_files(data_dir):
    """``{"gpkg": name, "qgz": name}`` for a dataset directory, by basename only.

    ``make_city_project.py`` names its output after the size (``city_S.gpkg``),
    so the harness discovers the pair instead of hard-coding a name -- and
    refuses a directory holding two datasets, where "which one did we measure?"
    would have no answer.
    """
    found = {}
    for suffix in ("gpkg", "qgz"):
        names = sorted(n for n in os.listdir(data_dir) if n.endswith("." + suffix))
        if len(names) != 1:
            raise SystemExit("dataset %s holds %d .%s files, expected exactly one: %s"
                             % (os.path.basename(data_dir), len(names), suffix, names))
        found[suffix] = names[0]
    return found


def read_manifest(data_dir):
    """The dataset manifest beside the GeoPackage, as a dict.

    Raises if the three files the harness needs are not all there, because a
    half-generated dataset measured as if it were complete is worse than no
    measurement.
    """
    if not os.path.isdir(data_dir):
        raise SystemExit("no dataset directory at %s" % data_dir)
    path = os.path.join(data_dir, "manifest.json")
    if not os.path.exists(path):
        raise SystemExit("dataset %s has no manifest.json -- generate it with "
                         "tests/fixtures/make_city_project.py"
                         % os.path.basename(data_dir))
    dataset_files(data_dir)
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise SystemExit("manifest.json is not an object")
    return manifest


def manifest_digest(manifest):
    """The generator's row-content digest, whatever key it was stored under."""
    for key in ("digest", "rows_digest", "row_digest", "sha256"):
        value = manifest.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def dataset_summary(data_dir, manifest):
    """What goes in the result file about the data: no paths, only identity."""
    counts = manifest.get("counts") or {}
    files = dataset_files(data_dir)
    return {"size": manifest.get("size"),
            "n": manifest.get("n"),
            "seed": manifest.get("seed"),
            "features": manifest.get("features") or sum(counts.values()) or None,
            "layers": len(counts) or None,
            "counts": counts,
            "digest": manifest_digest(manifest),
            "generator": manifest.get("generator"),
            "legacy_names": manifest.get("legacy_names"),
            "files": files,
            "gpkg_bytes": os.path.getsize(os.path.join(data_dir, files["gpkg"]))}


# --- environment -----------------------------------------------------------
def _first_line(path, needle=None):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if needle is None or line.startswith(needle):
                    return line.strip()
    except OSError:
        return None
    return None


def host_env():
    """The machine half of the environment table. No hostname, no user paths."""
    cpu = _first_line("/proc/cpuinfo", "model name")
    mem = _first_line("/proc/meminfo", "MemTotal")
    governor = _first_line("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    cpuset = _first_line("/sys/fs/cgroup/cpuset.cpus.effective")
    if cpuset is None:
        cpuset = _first_line("/sys/fs/cgroup/cpuset/cpuset.cpus")
    return {"python": platform.python_version(),
            "kernel": platform.release(),
            "machine": platform.machine(),
            "cpu_model": cpu.split(":", 1)[1].strip() if cpu and ":" in cpu else None,
            "cpu_count": os.cpu_count(),
            "cpuset_effective": cpuset,
            "cpu_governor": governor,
            "mem_total": mem.split(":", 1)[1].strip() if mem and ":" in mem else None,
            "in_container": os.path.exists("/.dockerenv"),
            "image": os.environ.get("FIBERQ_BENCH_IMAGE"),
            "image_digest": os.environ.get("FIBERQ_BENCH_IMAGE_DIGEST")}


# --- redaction -------------------------------------------------------------
class Redactor:
    """Replaces run-specific paths with placeholders, then proves none are left.

    The result files are published next to ``docs/performance.md``, so they must
    not carry the operator's home directory or the machine's name. Tracebacks and
    log samples are the realistic leak: they quote absolute file paths.
    """

    def __init__(self, paths=None):
        pairs = []
        for label, path in sorted((paths or {}).items()):
            if path:
                pairs.append(("<%s>" % label, os.path.realpath(path)))
                if os.path.realpath(path) != path:
                    pairs.append(("<%s>" % label, path))
        # Longest first: /data/city-S must win over /data.
        self._pairs = sorted(pairs, key=lambda pair: len(pair[1]), reverse=True)
        # Longest first here too, and for the same reason: on this machine the
        # hostname is "<user>-Precision-7510", so replacing the *username*
        # first left "<redacted>-Precision-7510" in a published file -- and
        # leaks() then reported the file clean, because no token was left to
        # find. The machine model is exactly what rule 11 promises not to
        # publish.
        self._tokens = sorted((t for t in self._secrets() if t), key=len,
                              reverse=True)

    @staticmethod
    def _secrets():
        try:
            user = getpass.getuser()
        except Exception:                      # pragma: no cover - no passwd entry
            user = None
        try:
            host = socket.gethostname()
        except Exception:                      # pragma: no cover
            host = None
        home = os.path.expanduser("~")
        out = [user, host, home if home not in ("/", "/root") else None]
        return [t for t in out if t and len(t) > 2]

    #: Home directories of any shape, for text the prefix map did not cover --
    #: a traceback or a profile quotes absolute paths from anywhere.
    HOME_RE = re.compile(r"/(?:home|Users|root)/[A-Za-z0-9._-]+")

    def text(self, value):
        """Prefix replacement only: the known run paths become placeholders."""
        for label, path in self._pairs:
            value = value.replace(path, label)
        return value

    def scrub_text(self, value):
        """Prefix replacement, then anything else identifying, inline.

        Used for free text -- tracebacks, log samples, profile reports -- where
        blanking the whole field would throw away the evidence.
        """
        value = self.text(value)
        # HOME_RE before the tokens, not after: the token pass turns
        # "/home/<user>/Documents/big.gpkg" into "/home/<redacted>/Documents/
        # big.gpkg", which HOME_RE can no longer match ("<" is not in its
        # character class), so half a home path was published and leaks() found
        # nothing left to complain about. This way the whole directory goes.
        value = self.HOME_RE.sub("<redacted>", value)
        for token in self._tokens:
            value = value.replace(token, "<redacted>")
        return value

    def obj(self, value):
        if isinstance(value, dict):
            return {k: self.obj(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.obj(v) for v in value]
        if isinstance(value, str):
            return self.scrub_text(value)
        return value

    def leaks(self, value):
        """Every remaining user path or hostname, as ``(where, token)`` pairs."""
        found = []
        self._walk("", value, found)
        return found

    def _walk(self, where, value, found):
        if isinstance(value, dict):
            for key, item in value.items():
                self._walk("%s.%s" % (where, key), item, found)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                self._walk("%s[%d]" % (where, index), item, found)
        elif isinstance(value, str):
            for token in self._tokens:
                if token in value:
                    found.append((where, token))
            for match in self.HOME_RE.findall(value):
                found.append((where, match))


def write_json(path, payload, redactor=None):
    """Redact, prove there is nothing left to redact, then write and fsync.

    ``os._exit(0)`` skips Python's buffer flush, so a result file smaller than
    the 8 KB stdio buffer is left 0 bytes and the run looks like it produced
    nothing (measured). Hence the explicit flush + fsync here.
    """
    redactor = redactor or Redactor()
    payload = redactor.obj(payload)
    leaks = redactor.leaks(payload)
    if leaks:
        payload = _blank(payload, {where for where, _ in leaks})
        payload["redacted_fields"] = sorted({where for where, _ in leaks})
        leaks = redactor.leaks(payload)
    if leaks:
        raise SystemExit("refusing to write %s: %s" % (os.path.basename(path), leaks[:3]))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    handle = open(path, "w", encoding="utf-8")
    try:
        json.dump(payload, handle, indent=1, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    return path


def write_text(path, body, redactor=None):
    """Redact, prove there is nothing left to redact, then write and fsync."""
    redactor = redactor or Redactor()
    body = redactor.scrub_text(body)
    leaks = redactor.leaks(body)
    if leaks:
        raise SystemExit("refusing to write %s: %s" % (os.path.basename(path),
                                                       leaks[:3]))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    handle = open(path, "w", encoding="utf-8")
    try:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    return path


def _blank(payload, wheres, prefix=""):
    """Replace the string leaves named in ``wheres`` with a marker."""
    if isinstance(payload, dict):
        return {k: _blank(v, wheres, "%s.%s" % (prefix, k)) for k, v in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_blank(v, wheres, "%s[%d]" % (prefix, i)) for i, v in enumerate(payload)]
    if isinstance(payload, str) and prefix in wheres:
        return "<redacted>"
    return payload


def load_average():
    """The machine's 1/5/15 minute load, or None where it is unavailable."""
    try:
        one, five, fifteen = os.getloadavg()
    except (AttributeError, OSError):          # not Linux, or /proc unavailable
        return None
    return {"1m": round(one, 2), "5m": round(five, 2), "15m": round(fifteen, 2)}


def acquire_lock(path):
    """Hold an exclusive lock for the whole run, or refuse to start.

    Learned the hard way: a second benchmark sequence was started while the
    first was still going, both pinned to the same five cores. Every row of the
    first sequence then measured a machine running two QGIS processes. The
    numbers looked plausible -- the giveaway was the performance governor coming
    out *slower* than powersave -- and nothing in the harness objected, because
    every fairness rule here watches one process and contention is a property of
    the machine.

    The lock is advisory between benchmark runs only (flock on a file both runs
    can see; inside the images that means a path on the shared scratch mount).
    It is not security: it stops an accident, which is what happened.
    """
    import fcntl
    handle = open(path, "w")                   # noqa: SIM115 - held for the run
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise SystemExit(
            "another benchmark run holds %s. Two runs on one machine measure "
            "each other's contention, so this one refuses to start. Wait for it, "
            "or pass --lock with a different path if you are certain the machines "
            "are separate." % path)
    handle.write("%d\n" % os.getpid())
    handle.flush()
    before_exit(handle.close)
    return handle


#: Callbacks to run just before the process goes away. ``atexit`` is useless
#: here: every exit goes through ``os._exit``, which skips it by design (see the
#: README). A dataset copy is ~1 MB at XS and ~20 MB at L, and the last
#: repetition's copy has nothing left to replace it, so without this a full
#: sweep leaves one copy per scenario behind in scratch.
_BEFORE_EXIT = []


def before_exit(callback):
    """Register a cleanup to run on the way out of ``flush_and_exit``."""
    _BEFORE_EXIT.append(callback)
    return callback


def flush_and_exit(code=0):
    """The only exit the harness uses. See README, "Why os._exit"."""
    while _BEFORE_EXIT:
        callback = _BEFORE_EXIT.pop()
        try:
            callback()
        except Exception as exc:               # cleanup must never hide a result
            sys.stderr.write("cleanup failed: %r\n" % (exc,))
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(code)
