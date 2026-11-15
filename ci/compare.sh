#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/compare.sh - compare the JUnit results of two runs: the tests that passed in the old run and no longer pass.
# Usage: sh ci/compare.sh [--stages <stage,...>] <old run> <new run>
# A run is a folder name under ci-results/ (CI_RESULTS) or a path to a run folder of ci/run-all.sh.
# Strict by default: every stage of the old run that has a junit.xml is compared, and one that the new run did not
# run, or ran without a junit.xml, loses all its old passes. --stages compares exactly the named stages, each of
# which must have a junit.xml in the old run. Lost: passed in the old run, and absent, failed, errored or skipped
# in the new one. ci/report.py compares in the python image of ci/legs, with no network; compare.md (printed at
# the end) lists the stages compared and left out, the image each run used, the lost and new test ids, and the
# tests now failing (skipped or absent in the old run; listed, not counted as lost). The records go to a new
# ci-results/<time>-compare/.
# Exit: 0 no test lost; 1 a test lost, or a compared stage missing or without junit.xml in the new run; 2 usage or
#       environment, a run folder without stages= in its run.txt, a named stage without junit.xml in the old run,
#       or nothing to compare (no stage of the old run has a junit.xml).
set -u
case $0 in */*) CI_DIR=${0%/*} ;; *) CI_DIR=. ;; esac
# shellcheck source=common.sh
. "$CI_DIR/common.sh"

usage() {
    echo "usage: sh ci/compare.sh [--stages <stage,...>] <old run> <new run>"
    echo "a run is a folder name under ci-results/ or a path to a run folder of ci/run-all.sh"
    echo "stages: $CI_ALL_STAGES (a bare leg such as 42 means test-42)"
}

bad() {   # <message>: a usage error; exit 2
    echo "compare.sh: $1" >&2
    usage >&2
    exit 2
}

wanted='' old_arg='' new_arg='' nargs=0
while [ $# -gt 0 ]; do
    case $1 in
        -h|--help) usage; exit 0 ;;
        --stages)
            if [ -n "$wanted" ]; then bad "--stages is given twice"; fi
            if [ $# -lt 2 ]; then bad "--stages needs stage names, separated by commas"; fi
            case $2 in ''|-*) bad "--stages needs stage names, separated by commas, not '$2'" ;; esac
            wanted=$2
            shift 2 ;;
        -*) bad "unknown option '$1'" ;;
        *)
            nargs=$((nargs + 1))
            case $nargs in
                1) old_arg=$1 ;;
                2) new_arg=$1 ;;
                *) bad "takes two runs, not more" ;;
            esac
            shift ;;
    esac
done
if [ "$nargs" != 2 ]; then bad "needs two runs: <old run> <new run>"; fi
stages=''
if [ -n "$wanted" ]; then
    case $wanted in *[!A-Za-z0-9,-]*) bad "--stages takes stage names separated by commas, not '$wanted'" ;; esac
    for w in $(printf '%s\n' "$wanted" | tr ',' ' '); do
        st=$(ci_stage_name "$w") || exit 2
        case ",$stages," in *",$st,"*) ;; *) stages="$stages,$st" ;; esac
    done
    stages=${stages#,}
    if [ -z "$stages" ]; then bad "--stages names no stage"; fi
fi
if [ "${CI_IN_PLACE:-}" = 1 ]; then
    echo "compare.sh: runs on the host, where it starts a container; unset CI_IN_PLACE" >&2
    exit 2
fi

ci_init nogit

cmp_dir() {   # <run>: print the run folder it names: a folder name under CI_RESULTS, or a path; else return 2
    case $1 in
        */*) _cdd=$1 ;;
        *)
            _cdd=$1
            if [ -d "$CI_RESULTS/$1" ]; then _cdd=$CI_RESULTS/$1; fi ;;
    esac
    if [ ! -d "$_cdd" ]; then
        echo "compare.sh: no run folder '$1' (a folder name under $CI_RESULTS, or a path)" >&2
        return 2
    fi
    if ! grep -q '^stages=' "$_cdd/run.txt" 2>/dev/null; then
        echo "compare.sh: $_cdd has no run.txt with stages= (not a run folder of ci/run-all.sh)" >&2
        return 2
    fi
    ( cd "$_cdd" && pwd -P )
}
old=$(cmp_dir "$old_arg") || exit 2
new=$(cmp_dir "$new_arg") || exit 2
ref=$(ci_image python) || exit 2
if [ ! -f "$CI_DIR/report.py" ] || [ ! -f "$CI_DIR/stage.sh" ]; then
    echo "compare.sh: ci/report.py and ci/stage.sh are needed" >&2
    exit 2
fi
if ! ci_present "$ref"; then
    echo "compare.sh: missing image $ref; run: sh ci/pull.sh pure" >&2
    exit 2
fi

run=$(ci_new_run compare) || exit 2
if ! mkdir "$run/input" "$run/raw" "$run/stages"; then exit 2; fi
s=compare commit='' dkey='' release=no
in=$run/input

cmp_take() {   # <run folder> <old|new>: copy run.txt and each stage's status, out/junit.xml and out/result.txt
    _ctr=$1 _ctd=$in/$2
    mkdir "$_ctd" "$_ctd/stages" || return 1
    ( set -C; cat "$_ctr/run.txt" >"$_ctd/run.txt" ) || return 1
    for _ctf in "$_ctr"/stages/*/; do
        [ -d "$_ctf" ] || continue
        _ctn=${_ctf%/}
        _ctn=${_ctn##*/}
        case $_ctn in ''|*[!a-z0-9-]*) continue ;; esac
        mkdir "$_ctd/stages/$_ctn" "$_ctd/stages/$_ctn/out" || return 1
        if [ -f "$_ctf/status" ]; then
            ( set -C; cat "$_ctf/status" >"$_ctd/stages/$_ctn/status" ) || return 1
        fi
        for _ctx in junit.xml result.txt; do
            if [ -f "$_ctf/out/$_ctx" ]; then
                ( set -C; cat "$_ctf/out/$_ctx" >"$_ctd/stages/$_ctn/out/$_ctx" ) || return 1
            fi
        done
    done
}
cmp_fail() {   # <reason>: the input could not be built; record it and exit 2
    ci_status "$s" fail "input build failed: $1" "image=$ref"
    echo "compare.sh: input build failed: $1 (records in $run)" >&2
    exit 2
}
cmp_take "$old" old || cmp_fail "copy of the old run's run.txt and stage results"
cmp_take "$new" new || cmp_fail "copy of the new run's run.txt and stage results"
tar -cf "$in/runs.tar" -C "$in" old new 2>>"$run/compare.log" || cmp_fail "tar of the two runs"
tar -cf "$in/ci.tar" -C "$CI_REPO" ci/stage.sh ci/report.py 2>>"$run/compare.log" ||
    cmp_fail "tar of ci/stage.sh and ci/report.py"
bytes=$(ci_bytes "$in/ci.tar" "$in/runs.tar") || cmp_fail "an input part is missing or unreadable"

started=$(date -u +%Y-%m-%dT%H:%M:%SZ) t0=$(date +%s)
echo "[$(date +%H:%M:%S)] compare started ($ref)" >&2
ci_feed "$in/compare.feed-rc" "$in/ci.tar" "$in/runs.tar" |
    ci_engine_run "fiberq-ci-${run##*/}-$$" "$ref" none "$(ci_timeout_of compare)" "$bytes" report.py compare \
        /tmp/w/old /tmp/w/new /tmp/w/out ${stages:+"$stages"} >"$run/raw/compare.tar" 2>>"$run/compare.log"
erc=$?
ci_verdict compare "$erc" "image=$ref" "started=$started"
res=$(ci_result_of compare)
why=$(sed -n 's/^reason=//p' "$run/stages/compare/status" | tail -n 1)
echo "[$(date +%H:%M:%S)] compare $res ($(( $(date +%s) - t0 )) s)${why:+ $why}" >&2
out=$run/stages/compare/out
code=$(cat "$out/exit-code" 2>/dev/null) || code=''
if [ -f "$out/compare.md" ]; then cat "$out/compare.md"; fi
echo "compare.sh: records in $run" >&2
if [ "$res" = pass ]; then exit 0; fi
if [ "$erc" = 1 ] && [ "$code" = 1 ] && [ -f "$out/compare.md" ]; then exit 1; fi
sed -n 's/^report\.py: /compare.sh: /p' "$run/compare.log" >&2
echo "compare.sh: the compare did not finish: ${why:-no verdict} (log: $run/compare.log)" >&2
exit 2
