#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/test.sh - the pytest stages: pure (no QGIS), the five QGIS legs, and local (in place only).
# Usage, started by ci/run-all.sh through ci/stage.sh:
#   sh ci/test.sh pure                     the files listed in ci/pure-tests.txt, with pytest-qgis off
#   sh ci/test.sh <322|340|344|40|42>      the whole suite in that leg's QGIS; the image must run that version (in
#                                          place, on another QGIS or none, the leg is skipped)
#   sh ci/test.sh local                    in place only: the whole suite on this environment's QGIS
# The pinned tools (CI_DEPS) go in front of PYTHONPATH, and pytest (plus pytest_qgis, except for pure) must load
# from there. junit.xml and result.txt go to CI_OUT (a skipped leg writes no junit.xml); basetemp and TMPDIR go
# under CI_WORK.
# Exit: pytest's own code; 0 for a skip (in place, not on the leg's QGIS); 2 usage or setup error (run by hand,
#       pinned tools not in use, the image's QGIS not the leg's).
set -u
umask 022

leg=${1:-}
case $leg in
    pure) stage=pure ;;
    322|340|344|40|42|local) stage=test-$leg ;;
    *) echo "test.sh: usage: sh ci/test.sh <pure|322|340|344|40|42|local>" >&2; exit 2 ;;
esac
if [ $# -ne 1 ]; then echo "test.sh: usage: sh ci/test.sh <pure|322|340|344|40|42|local>" >&2; exit 2; fi
if [ -z "${CI_DIR:-}" ] || [ -z "${CI_OUT:-}" ] || [ -z "${CI_WORK:-}" ] || [ ! -d "$CI_OUT" ] ||
    [ ! -d "$CI_WORK" ]; then
    if [ "$leg" = local ]; then
        echo "test.sh: run stages through ci/run-all.sh: CI_IN_PLACE=1 sh ci/run-all.sh --only test-local" >&2
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

# pure: the seed list, each file read relative to the tested tree
set --
if [ "$leg" = pure ]; then
    if [ ! -f "$CI_DIR/pure-tests.txt" ]; then echo "test.sh: ci/pure-tests.txt not found" >&2; exit 2; fi
    while IFS= read -r f || [ -n "$f" ]; do
        case $f in ''|'#'*) continue ;; esac
        if [ ! -f "$f" ]; then
            echo "test.sh: ci/pure-tests.txt names '$f', which is not a file in the tested tree" >&2
            exit 2
        fi
        set -- "$@" "$f"
    done <"$CI_DIR/pure-tests.txt"
    if [ $# -eq 0 ]; then echo "test.sh: ci/pure-tests.txt lists no test files" >&2; exit 2; fi
fi
nfiles=$#

# what runs here, recorded before anything is judged
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
    if [ "$leg" = pure ]; then printf 'files=%s\n' "$nfiles"; fi
} >"$CI_OUT/result.txt" || exit 2

# a leg runs in the QGIS it is named after: a mismatch means a wrong ci/legs line; in place, on any other QGIS (or
# none), the leg is skipped (test-local runs the suite on whatever QGIS is here)
want=''
case $leg in 322) want=3.22 ;; 340) want=3.40 ;; 344) want=3.44 ;; 40) want=4.0 ;; 42) want=4.2 ;; esac
if [ -n "$want" ]; then
    have=$(printf '%s\n' "$qgis" | sed -n 's/^\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p')
    if [ "$have" != "$want" ]; then
        if [ "${CI_IN_PLACE:-}" = 1 ]; then
            echo "test.sh: $stage needs QGIS $want, this environment has ${qgis:-no QGIS}; skipped"
            printf 'skipped=needs QGIS %s (the %s image)\n' "$want" "$leg" >>"$CI_OUT/result.txt" || exit 2
            exit 0
        else
            echo "test.sh: $stage expects QGIS $want, the image ${CI_IMAGE_REF:-} has ${qgis:-no QGIS};" \
                "check the $leg line of ci/legs" >&2
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
printf 'pythonpath=prepend\ntools=pinned\n' >>"$CI_OUT/result.txt" || exit 2

mkdir "$CI_WORK/tmp" || exit 2
TMPDIR=$CI_WORK/tmp
export TMPDIR
suite=${CI_STAGE:-$stage}
if [ "$leg" = pure ]; then
    set -- -p no:cacheprovider -q --basetemp="$CI_WORK/basetemp" --junitxml="$CI_OUT/junit.xml" \
        -o junit_suite_name="$suite" --durations=25 -p no:pytest_qgis "$@"
else
    set -- -p no:cacheprovider -q --basetemp="$CI_WORK/basetemp" --junitxml="$CI_OUT/junit.xml" \
        -o junit_suite_name="$suite" --durations=25
fi
echo "test.sh: $stage: python3 -m pytest $*"
exec python3 -m pytest "$@"
