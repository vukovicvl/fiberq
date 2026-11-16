#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/test.sh - the pytest stages: pure (no QGIS), the five QGIS legs, test-coverage, and local (in place only).
# Usage, started by ci/run-all.sh through ci/stage.sh:
#   sh ci/test.sh pure                     the fast stage: the tested tree's conftest.py (FIBERQ_PURE=1) hides QGIS
#                                          and picks every test file that imports without it; pytest-qgis and every
#                                          other plugin of the environment stay off. Each test file's pure items must
#                                          equal its line in the tested tree's ci/pure-count
#   sh ci/test.sh <322|340|344|40|42>      the whole suite in that leg's QGIS; the image must run that version (in
#                                          place, on another QGIS or none, the leg is skipped)
#   sh ci/test.sh coverage                 the test-coverage stage, in host mode only: test-42's suite under
#                                          coverage, configured by ci/coverage.ini alone, Python child processes
#                                          included; then the table of the core-logic modules (ci/report.py coverage)
#   sh ci/test.sh local                    in place only: the whole suite on this environment's QGIS
# The pinned tools (CI_DEPS) go in front of PYTHONPATH, and pytest (plus pytest_qgis, except for pure, and coverage
# for test-coverage) must load from there. junit.xml and result.txt go to CI_OUT (a skipped leg writes no junit.xml);
# basetemp, TMPDIR and coverage's data files go under CI_WORK.
# Exit: pytest's own code; 1 pure: the pure items differ from ci/pure-count or cannot be counted, test-coverage: the
#       suite passed but the coverage report failed, or no child process was measured or the data files cannot be
#       counted; 0 for a skip (in place: a leg not on its QGIS, and test-coverage); 2 usage or setup error (run by
#       hand, pinned tools not in use, the image's QGIS not the leg's, pure: no valid ci/pure-count in the tested
#       tree).
set -u
umask 022

leg=${1:-}
case $leg in
    pure) stage=pure ;;
    322|340|344|40|42|local) stage=test-$leg ;;
    coverage) stage=test-coverage ;;
    *) echo "test.sh: usage: sh ci/test.sh <pure|322|340|344|40|42|coverage|local>" >&2; exit 2 ;;
esac
if [ $# -ne 1 ]; then echo "test.sh: usage: sh ci/test.sh <pure|322|340|344|40|42|coverage|local>" >&2; exit 2; fi
if [ -z "${CI_DIR:-}" ] || [ -z "${CI_OUT:-}" ] || [ -z "${CI_WORK:-}" ] || [ ! -d "$CI_OUT" ] ||
    [ ! -d "$CI_WORK" ]; then
    if [ "$leg" = local ]; then
        echo "test.sh: run stages through ci/run-all.sh: CI_IN_PLACE=1 sh ci/run-all.sh --only test-local" >&2
    elif [ "$leg" = coverage ]; then
        echo "test.sh: run stages through ci/run-all.sh: sh ci/run-all.sh --only $stage (host mode only)" >&2
    else
        echo "test.sh: run stages through ci/run-all.sh: sh ci/run-all.sh --only $stage" \
            "(in place: CI_IN_PLACE=1 sh ci/run-all.sh --only $stage)" >&2
    fi
    exit 2
fi
if [ "$leg" = local ] && [ "${CI_IN_PLACE:-}" != 1 ]; then
    echo "test.sh: test-local runs in place only: CI_IN_PLACE=1 sh ci/run-all.sh --only test-local" >&2
    exit 2
fi
if [ -z "${CI_SRC:-}" ]; then echo "test.sh: no tested tree (CI_SRC is empty)" >&2; exit 2; fi
cd "$CI_SRC" || exit 2
deps=${CI_DEPS:-}
deps=${deps%/}
if [ -z "$deps" ]; then echo "test.sh: no pinned tools (CI_DEPS is empty)" >&2; exit 2; fi
PYTHONPATH=$deps${PYTHONPATH:+:$PYTHONPATH} PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen
export PYTHONPATH PYTHONDONTWRITEBYTECODE QT_QPA_PLATFORM
unset FIBERQ_PURE FIBERQ_PURE_REPORT   # conftest.py's fast stage: only pure switches it on, below

# what runs here, recorded before anything is judged (pure: the QGIS of the environment, which the stage hides)
py=$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])') || py=''
if [ "$leg" = pure ]; then
    qgis=$(python3 -c 'from qgis.core import Qgis; print(Qgis.QGIS_VERSION)' 2>/dev/null) || qgis=''
else
    qgis=$(python3 -c 'from qgis.core import Qgis; print(Qgis.QGIS_VERSION)') || qgis=''
fi
pyt=$(python3 -m pytest --version 2>&1 | head -n 1)
{
    printf 'leg=%s\n' "$leg"
    printf 'python=%s\n' "$py"
    printf 'pytest=%s\n' "$pyt"
    printf 'qgis=%s\n' "${qgis:-none}"
    printf 'uid=%s\n' "$(id -u)"
} >"$CI_OUT/result.txt" || exit 2

# test-coverage counts statements with the Python of the 42 image, as every column of its table does: in place, where
# the Python is this environment's, it is skipped
if [ "$leg" = coverage ] && [ "${CI_IN_PLACE:-}" = 1 ]; then
    echo "test.sh: $stage runs in host mode only (the 42 image, whose Python counts the statements); skipped"
    printf 'skipped=host mode only (the 42 image)\n' >>"$CI_OUT/result.txt" || exit 2
    exit 0
fi

# a leg runs in the QGIS it is named after: a mismatch means a wrong ci/legs line; in place, on any other QGIS (or
# none), the leg is skipped (test-local runs the suite on whatever QGIS is here)
want='' role=$leg
case $leg in 322) want=3.22 ;; 340) want=3.40 ;; 344) want=3.44 ;; 40) want=4.0 ;; 42) want=4.2 ;; esac
if [ "$leg" = coverage ]; then want=4.2 role=42; fi
if [ -n "$want" ]; then
    have=$(printf '%s\n' "$qgis" | sed -n 's/^\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p')
    if [ "$have" != "$want" ]; then
        if [ "${CI_IN_PLACE:-}" = 1 ]; then
            echo "test.sh: $stage needs QGIS $want, this environment has ${qgis:-no QGIS}; skipped"
            printf 'skipped=needs QGIS %s (the %s image)\n' "$want" "$role" >>"$CI_OUT/result.txt" || exit 2
            exit 0
        else
            echo "test.sh: $stage expects QGIS $want, the image ${CI_IMAGE_REF:-} has ${qgis:-no QGIS};" \
                "check the $role line of ci/legs" >&2
            exit 2
        fi
    fi
fi

# the proof that the pinned tools are the ones in use
test_proof() {   # <module>: exit 2 unless <module> loads from $deps
    if ! _tpf=$(python3 -c "import sys, $1; sys.stdout.write($1.__file__)"); then
        echo "test.sh: $1 does not import here (the error is above); it must load from the pinned tools in $deps" >&2
        exit 2
    fi
    case $_tpf in
        "$deps"/*) ;;
        *) echo "test.sh: pinned tools not in use: $1 loads from $_tpf, not from $deps" >&2; exit 2 ;;
    esac
}
test_proof pytest
if [ "$leg" != pure ]; then test_proof pytest_qgis; fi
if [ "$leg" = coverage ]; then test_proof coverage; fi
printf 'pythonpath=prepend\ntools=pinned\n' >>"$CI_OUT/result.txt" || exit 2

# pure: the pure items of each test file, as the tested tree pins them in its ci/pure-count, one "<number>
# tests/<file>.py" line per file (# lines are comments). It is read from the tested tree, not from these scripts, so
# a commit tested with --ref meets its own numbers; a tree without the file predates the automatic fast stage, and
# its conftest.py cannot pick
if [ "$leg" = pure ]; then
    if [ ! -f ci/pure-count ]; then
        echo "test.sh: the tested tree has no ci/pure-count: it predates the automatic fast stage, whose picking" \
            "lives in the tested tree's conftest.py; run the pure stage on a later commit" >&2
        printf 'failed=pure_count (the tested tree has no ci/pure-count)\n' >>"$CI_OUT/result.txt"
        exit 2
    fi
    if ! pins=$(python3 -I "$CI_DIR/report.py" pure-pin ci/pure-count); then
        echo "test.sh: ci/pure-count holds, besides its # lines, one \"<number> tests/<file>.py\" line per test" \
            "file with pure items (the error is above)" >&2
        printf 'failed=pure_count (ci/pure-count is not valid)\n' >>"$CI_OUT/result.txt"
        exit 2
    fi
    printf '%s\n' "$pins" >>"$CI_OUT/result.txt" || exit 2
fi

mkdir "$CI_WORK/tmp" || exit 2
TMPDIR=$CI_WORK/tmp
export TMPDIR
suite=${CI_STAGE:-$stage}
set -- -p no:cacheprovider -q --basetemp="$CI_WORK/basetemp" --junitxml="$CI_OUT/junit.xml" \
    -o junit_suite_name="$suite" --durations=25

# pure: pytest without exec, so that the count is checked after it. pytest runs as a job of this script, which
# passes a TERM, HUP or INT on to it, as ci/stage.sh does: timeout(1) signals the whole process group, but where
# there is no timeout(1), ci/stage.sh signals this script only
if [ "$leg" = pure ]; then
    set -- "$@" -p no:pytest_qgis --disable-plugin-autoload
    echo "test.sh: $stage: FIBERQ_PURE=1 python3 -m pytest $*"
    tp='' stop=''
    trap 'stop=1; [ -z "$tp" ] || kill -TERM "$tp" 2>/dev/null' TERM HUP INT
    FIBERQ_PURE=1 FIBERQ_PURE_REPORT=$CI_OUT/pure-files.tsv python3 -m pytest "$@" &
    tp=$!
    [ -z "$stop" ] || kill -TERM "$tp" 2>/dev/null
    wait "$tp"; rc=$?
    while [ -n "$stop" ] && kill -0 "$tp" 2>/dev/null; do wait "$tp"; rc=$?; done
    trap - TERM HUP INT
    if [ -n "$stop" ] && [ "$rc" = 0 ]; then rc=143; fi   # stopped: never counted, never a pass
    if [ "$rc" != 0 ]; then exit "$rc"; fi
    # the counts, once pytest passed: per test file, the tests run less the stage's own skips (ci/report.py pure),
    # each against its line in ci/pure-count
    keys=$(python3 -I "$CI_DIR/report.py" pure "$CI_OUT/junit.xml" "$CI_OUT/pure-files.tsv" ci/pure-count)
    rc=$?
    if [ -n "$keys" ]; then printf '%s\n' "$keys" >>"$CI_OUT/result.txt" || exit 2; fi
    items=$(printf '%s\n' "$keys" | sed -n 's/^pure_items=//p')
    nfiles=$(printf '%s\n' "$keys" | sed -n 's/^pure_files=//p')
    case $rc in
        0)
            echo "test.sh: pure: $items pure items in $nfiles test files, as ci/pure-count says"
            exit 0 ;;
        1)
            differ=$(printf '%s\n' "$keys" | sed -n 's/^pure_differ=//p')
            echo "test.sh: pure: test files that differ from ci/pure-count: $differ (each is named above)" >&2
            printf 'failed=pure_count (test files that differ from ci/pure-count: %s)\n' "$differ" \
                >>"$CI_OUT/result.txt"
            exit 1 ;;
        *)
            echo "test.sh: pure: the pure items could not be counted (ci/report.py pure, above)" >&2
            printf 'failed=pure_count (the pure items could not be counted)\n' >>"$CI_OUT/result.txt"
            exit 1 ;;
    esac
fi

if [ "$leg" != coverage ]; then
    echo "test.sh: $stage: python3 -m pytest $*"
    exec python3 -m pytest "$@"
fi

# test-coverage: test-42's suite under coverage. ci/coverage.ini is the only configuration coverage reads (never the
# tested tree's pyproject.toml), so every tree is measured alike, v1.6.0 through --ref too; the data files go to
# CI_WORK. The pinned tools sit in a pip --target folder, and Python reads no .pth file from a folder on PYTHONPATH,
# so a sitecustomize.py first on PYTHONPATH starts coverage in each Python child (ci/cov-sitecustomize.py)
rcf=$CI_DIR/coverage.ini
for f in "$rcf" "$CI_DIR/cov-sitecustomize.py"; do
    if [ ! -f "$f" ]; then echo "test.sh: $f not found" >&2; exit 2; fi
done
mkdir "$CI_WORK/cov" "$CI_WORK/cov-all" "$CI_WORK/cov-hook" || exit 2
cp "$CI_DIR/cov-sitecustomize.py" "$CI_WORK/cov-hook/sitecustomize.py" || exit 2
# only ci/coverage.ini decides: no setting of the environment's (in place) reaches coverage
unset COVERAGE_CORE COVERAGE_FORCE_CONFIG COVERAGE_PROCESS_CONFIG COVERAGE_PROCESS_START COVERAGE_RCFILE
PYTHONPATH=$CI_WORK/cov-hook:$PYTHONPATH COVERAGE_FILE=$CI_WORK/cov/data
export PYTHONPATH COVERAGE_FILE
covv=$(python3 -m coverage --version | sed -n '1s/^Coverage\.py, version \([^ ]*\).*/\1/p')
printf 'coverage=%s\nrcfile=ci/coverage.ini\n' "${covv:-unknown}" >>"$CI_OUT/result.txt" || exit 2
echo "test.sh: $stage: python3 -m coverage run --rcfile=$rcf -m pytest $*"
python3 -m coverage run --rcfile="$rcf" -m pytest "$@"
rc=$?
# the data files, one per process, and how many of them measured anything: the pytest process, and the children
# only if the hook started coverage in them (a child that ran no fiberq/ code from this tree leaves an empty one)
n=$(find "$CI_WORK/cov" -type f -name 'data.*' | wc -l | tr -d ' ')
measured=$(python3 - "$CI_WORK/cov" <<'PY'
import glob
import os
import sys

from coverage import CoverageData

count = 0
for path in glob.glob(os.path.join(sys.argv[1], "data.*")):
    data = CoverageData(basename=path)
    try:
        data.read()
    except Exception:   # an empty or half-written file of a process that ended early
        continue
    if any(data.lines(name) for name in data.measured_files()):
        count += 1
print(count)
PY
) || measured=''
printf 'data_files=%s\nprocesses_measured=%s\n' "$n" "${measured:-unknown}" >>"$CI_OUT/result.txt" || exit 2
fail=''
case $measured in
    ''|*[!0-9]*)
        echo "test.sh: $stage: the coverage data files could not be counted (the error is above)" >&2
        fail='coverage_children (the data files could not be counted)' ;;
    0|1)
        if [ "$n" -gt 1 ]; then
            why="coverage started in the children ($n data files), but none of them ran this tree's fiberq/"
        else
            why='the coverage hook, ci/cov-sitecustomize.py, did not start in the children'
        fi
        echo "test.sh: $stage: no child process was measured ($measured of $n data files hold lines): $why" >&2
        fail='coverage_children (no child process was measured)' ;;
esac
ok=yes
python3 -m coverage combine --rcfile="$rcf" --keep --data-file="$CI_WORK/cov-all/data" "$CI_WORK/cov" \
    >"$CI_OUT/coverage-combine.txt" 2>&1 || ok=no
cat "$CI_OUT/coverage-combine.txt"
if [ "$ok" = yes ]; then
    python3 -m coverage json --rcfile="$rcf" --data-file="$CI_WORK/cov-all/data" -o "$CI_OUT/coverage.json" || ok=no
fi
if [ "$ok" = yes ]; then
    if keys=$(python3 -I "$CI_DIR/report.py" coverage "$CI_OUT/coverage.json" "$CI_OUT"); then
        printf '%s\n' "$keys" >>"$CI_OUT/result.txt" || ok=no
    else
        ok=no
    fi
fi
if [ "$ok" = no ]; then
    echo "test.sh: $stage: the coverage report failed (see the lines above)" >&2
    fail="coverage_report${fail:+, $fail}"
fi
if [ -n "$fail" ]; then
    printf 'failed=%s\n' "$fail" >>"$CI_OUT/result.txt"
    if [ "$rc" = 0 ]; then rc=1; fi
fi
exit "$rc"
