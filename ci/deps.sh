#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/deps.sh - fill the cache of pinned test and lint tools, one folder per image and tool set.
# Usage:
#   sh ci/deps.sh [--hook|--quick|--release|<stage>...]
#   sh ci/deps.sh install <test|lint>      the worker, inside the container that the first form starts
# The first form takes the stages of the set (the default set if nothing is named) that use pinned tools: pure and
# the test legs use the test set, lint uses the lint set. For each image and set not cached yet, it installs
# ci/requirements-<set>.txt in that image with pip --require-hashes (network), then keeps deps.tar and freeze.txt
# in .ci-cache/deps/<digest16>-<set>-<req16>-<recipe8>[.N]/ and writes the marker file "complete" last.
# Records go to a new ci-results/<time>-deps/. ci/run-all.sh runs this script before its stages, with CI_RUN_DIR
# (its run folder: records go to <run>/deps/ and <run>/input/ci.tar is the input) and CI_NAME_PREFIX (the prefix
# of its container names) set.
# Exit: 0 all done; 1 some set failed (the others still ran); 2 usage or environment.
set -u

deps_worker() {   # <test|lint>: pip --require-hashes into CI_DEPS_TARGET (in place) or $CI_WORK/deps
    _ws=$1
    if [ -z "${CI_DIR:-}" ] || [ -z "${CI_OUT:-}" ] || { [ -z "${CI_DEPS_TARGET:-}" ] && [ -z "${CI_WORK:-}" ]; }; then
        echo "deps.sh: 'install' runs inside the container that sh ci/deps.sh starts; run: sh ci/deps.sh <stage>" >&2
        exit 2
    fi
    _wreq=$CI_DIR/requirements-$_ws.txt _wt=${CI_DEPS_TARGET:-$CI_WORK/deps}
    if [ ! -f "$_wreq" ]; then echo "deps.sh: $_wreq not found" >&2; exit 2; fi
    if [ -e "$_wt" ]; then echo "deps.sh: $_wt already exists; the tools go into a new folder" >&2; exit 2; fi
    python3 -m pip install --no-cache-dir --disable-pip-version-check --no-compile --only-binary=:all: \
        --require-hashes --target "$_wt" -r "$_wreq" || exit 1
    python3 -m pip list --disable-pip-version-check --path "$_wt" --format=freeze >"$CI_OUT/freeze.txt" || exit 1
    [ "${CI_IN_PLACE:-}" = 1 ] || tar -cf "$CI_OUT/deps.tar" -C "$(dirname "$_wt")" "$(basename "$_wt")" || exit 1
    _wpy=$(python3 -I -c 'import platform; print(platform.python_version())') || _wpy=''
    _wpip=$(python3 -m pip --version 2>/dev/null) || _wpip=''
    _wpip=${_wpip#pip } _wn=$(grep -c . "$CI_OUT/freeze.txt")
    {
        printf 'set=%s\n' "$_ws"
        printf 'python=%s\n' "$_wpy"
        printf 'pip=%s\n' "${_wpip%% from *}"
        printf 'packages=%s\n' "$_wn"
    } >"$CI_OUT/result.txt" || exit 1
    exit 0
}

case ${1:-} in
    install)
        if [ $# -ne 2 ]; then echo "deps.sh: usage: sh ci/deps.sh install <test|lint>" >&2; exit 2; fi
        case $2 in
            test|lint) deps_worker "$2" ;;
            *) echo "deps.sh: no tool set '$2' (test or lint)" >&2; exit 2 ;;
        esac ;;
esac

case $0 in */*) CI_DIR=${0%/*} ;; *) CI_DIR=. ;; esac
# shellcheck source=common.sh
. "$CI_DIR/common.sh"

usage() {
    echo "usage: sh ci/deps.sh [--hook|--quick|--release|<stage>...]"
    echo "       sh ci/deps.sh install <test|lint>   (the worker; it runs in the container the first form starts)"
    echo "stages: $CI_ALL_STAGES (a bare leg such as 42 means test-42)"
    echo "pure and the test legs use the test tools, lint the lint tools; the other stages use none"
}

deps_set_of() {   # <stage>: print the tool set <stage> uses (test or lint); nothing when it uses none
    case $1 in
        pure|test-*) echo test ;;
        lint) echo lint ;;
    esac
}

deps_split() {   # <role,set,stage,ref,key>: set the globals role, tset, st, ref and key from one work item
    _sp=$1
    role=${_sp%%,*} _sp=${_sp#*,}
    tset=${_sp%%,*} _sp=${_sp#*,}
    st=${_sp%%,*} _sp=${_sp#*,}
    ref=${_sp%%,*} key=${_sp#*,}
}

deps_note() {   # <role>: print " (override)" when CI_IMAGE_<ROLE> is set
    if [ -n "$(ci_override "$1")" ]; then echo ' (override)'; fi
}

deps_keep() {   # <out dir>: copy deps.tar and freeze.txt into a new cache folder for $key, then write complete
    # prints the folder; returns 1 if anything fails, and the folder then stays without a marker (never used)
    _dpo=$1
    _dpd=$(ci_newdir "$CI_CACHE/deps/$key" .) || return 1
    printf '%s\n' "$_dpd"
    ( set -C; cat "$_dpo/deps.tar" >"$_dpd/deps.tar" ) || return 1
    ( set -C; cat "$_dpo/freeze.txt" >"$_dpd/freeze.txt" ) || return 1
    if ! cmp -s "$_dpo/deps.tar" "$_dpd/deps.tar" || ! cmp -s "$_dpo/freeze.txt" "$_dpd/freeze.txt"; then return 1; fi
    _dpc=$(ci_cksum "$_dpd/deps.tar") || return 1
    _dpy=$(sed -n 's/^python=//p' "$_dpo/result.txt" | head -n 1)
    case $tset in test) _dpq=$blob_test ;; *) _dpq=$blob_lint ;; esac
    _dpt=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    ( set -C   # deps_cksum comes last: a cut-off marker has none, and the lookup skips the folder
      { printf 'key=%s\nimage=%s\nrequirements=%s\n' "$key" "$ref" "ci/requirements-$tset.txt" &&
        printf 'requirements_blob=%s\nrecipe=%s\npython=%s\n' "$_dpq" "$recipe" "$_dpy" &&
        printf 'created=%s\ndeps_cksum=%s\n' "$_dpt" "$_dpc"; } >"$_dpd/complete" ) || return 1
}

deps_fetch() {   # install the set $tset in the image of $role ($ref) and keep it as $key; print the result line
    s=deps-$role-$tset _fn=$(deps_note "$role")
    if [ -n "${CI_RUN_DIR:-}" ]; then
        _fin=$CI_RUN_DIR/input/ci.tar _fname=$CI_NAME_PREFIX-deps-$role-$tset
    else
        _fname=fiberq-ci-${run##*/}-$$-$role-$tset
        case $tset in test) _fin=$in_test ;; *) _fin=$in_lint ;; esac
    fi
    if [ -e "$run/stages/$s" ] || [ -e "$run/raw/$s.tar" ]; then
        echo "FAILED $role $tset$_fn: $s is already recorded in $run"
        return 1
    fi
    _fw=''
    if [ -z "$_fin" ]; then
        _fw="input build failed: tar of ci/stage.sh, ci/deps.sh and ci/requirements-$tset.txt"
    elif ! ci_present "$ref"; then
        _fw="missing image $ref; run: sh ci/pull.sh $st"
    elif ! _fb=$(ci_bytes "$_fin"); then
        _fw="input build failed (an input part is missing or unreadable)"
    fi
    if [ -n "$_fw" ]; then
        ci_status "$s" fail "$_fw" "image=$ref" "deps=$key"
        echo "FAILED $role $tset$_fn: $_fw"
        return 1
    fi
    _f0=$(date +%s) _fst=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "[$(date +%H:%M:%S)] $s started ($ref)" >&2
    ci_feed "$run/input/$s.feed-rc" "$_fin" |
        ci_engine_run "$_fname" "$ref" default "$(ci_timeout_of "$s")" "$_fb" deps.sh install "$tset" \
            >"$run/raw/$s.tar" 2>>"$run/$s.log"
    _fe=$?
    ci_verdict "$s" "$_fe" "image=$ref" "started=$_fst" "deps=$key"
    _fres=$(ci_result_of "$s")
    _fw=$(sed -n 's/^reason=//p' "$run/stages/$s/status" | tail -n 1)
    echo "[$(date +%H:%M:%S)] $s $_fres ($(( $(date +%s) - _f0 )) s) $_fw" >&2
    if [ "$_fres" != pass ]; then
        echo "FAILED $role $tset$_fn: $_fw (log: $run/$s.log)"
        return 1
    fi
    if ! _fd=$(deps_keep "$run/stages/$s/out"); then
        _fw="the copy into the cache failed${_fd:+; $_fd has no marker and is never used}"
        ci_status "$s" fail "$_fw" "image=$ref" "deps=$key"
        echo "FAILED $role $tset$_fn: $_fw"
        return 1
    fi
    echo "fetched $role $tset $_fd$_fn"
}

dset='' stages=''
case ${1:-} in
    -h|--help) usage; exit 0 ;;
    '') dset=default ;;
    --hook|--quick|--release)
        dset=${1#--}; shift
        if [ $# -ne 0 ]; then echo "deps.sh: --$dset takes no stage names" >&2; usage >&2; exit 2; fi ;;
esac
if [ -n "$dset" ]; then
    stages=$(ci_set_stages "$dset") || exit 2
else
    for a in "$@"; do
        case $a in -*) echo "deps.sh: unknown option '$a'" >&2; usage >&2; exit 2 ;; esac
        a=$(ci_stage_name "$a") || exit 2
        stages="$stages $a"
    done
fi
if [ "${CI_IN_PLACE:-}" = 1 ]; then
    echo "deps.sh: runs on the host, where it starts containers;" \
        "in place, CI_IN_PLACE=1 sh ci/run-all.sh installs the pinned tools itself" >&2
    exit 2
fi
case " $stages " in
    *" test-local "*)
        echo "deps.sh: test-local runs in place only; CI_IN_PLACE=1 sh ci/run-all.sh --only test-local" \
            "installs its tools" >&2
        exit 2 ;;
esac
if [ -n "${CI_RUN_DIR:-}" ]; then
    if [ ! -f "$CI_RUN_DIR/input/ci.tar" ]; then
        echo "deps.sh: CI_RUN_DIR must be a run folder of ci/run-all.sh with input/ci.tar; '$CI_RUN_DIR' is not" >&2
        exit 2
    fi
    case ${CI_NAME_PREFIX:-} in
        ''|[!A-Za-z0-9]*|*[!A-Za-z0-9_.-]*)
            echo "deps.sh: CI_RUN_DIR needs CI_NAME_PREFIX, the prefix of the run's container names" >&2
            exit 2 ;;
    esac
fi

ci_init nogit
commit=''
if [ "$CI_HAVE_GIT" = yes ]; then
    commit=$(git -C "$CI_REPO" rev-parse --verify --quiet 'HEAD^{commit}') || commit=''
fi
dkey='' release=no run='' in_test='' in_lint='' blob_test='' blob_lint=''

# the work: each image and tool set once, as "<role>,<set>,<first stage>,<ref>,<key>"
todo='' seen=' '
for a in $stages; do
    tset=$(deps_set_of "$a")
    [ -n "$tset" ] || continue
    role=$(ci_role_of "$a") || exit 2
    case $seen in *" $role,$tset "*) continue ;; esac
    seen="$seen$role,$tset "
    ref=$(ci_image "$role") || exit 2
    key=$(ci_deps_key "$tset" "$ref") || exit 2
    case $tset in
        test) [ -n "$blob_test" ] || blob_test=$(ci_filehash "$CI_DIR/requirements-test.txt" 64) || exit 2 ;;
        lint) [ -n "$blob_lint" ] || blob_lint=$(ci_filehash "$CI_DIR/requirements-lint.txt" 64) || exit 2 ;;
    esac
    todo="$todo $role,$tset,$a,$ref,$key"
done
if [ -z "$todo" ]; then
    echo "deps.sh: none of the selected stages uses pinned tools (pure, lint and the test legs do)"
    exit 0
fi
recipe=$(ci_filehash "$CI_DIR/deps.sh" 64) || exit 2
if ! mkdir -p "$CI_CACHE/deps"; then
    echo "deps.sh: cannot create $CI_CACHE/deps (set CI_CACHE to a writable folder)" >&2
    exit 2
fi

need=''
for p in $todo; do
    deps_split "$p"
    if d=$(ci_deps_find "$key"); then
        echo "cached $role $tset $d$(deps_note "$role")"
    else
        need="$need $p"
    fi
done
[ -n "$need" ] || exit 0

if [ -n "${CI_RUN_DIR:-}" ]; then
    run=$CI_RUN_DIR/deps
    if [ ! -d "$run" ] && ! mkdir "$run"; then exit 2; fi
else
    run=$(ci_new_run deps) || exit 2
fi
for x in input raw stages; do
    if [ ! -d "$run/$x" ] && ! mkdir "$run/$x"; then exit 2; fi
done
if [ -z "${CI_RUN_DIR:-}" ]; then   # the input of each set, taken from the working tree before any container runs
    for x in test lint; do
        case $need in *",$x,"*) ;; *) continue ;; esac
        if tar -cf "$run/input/ci-$x.tar" -C "$CI_REPO" ci/stage.sh ci/deps.sh "ci/requirements-$x.txt"; then
            case $x in test) in_test=$run/input/ci-test.tar ;; *) in_lint=$run/input/ci-lint.tar ;; esac
        fi
    done
fi

failed=0
for p in $need; do
    deps_split "$p"
    if d=$(ci_deps_find "$key"); then   # filled by an earlier item of this run (two roles on one image)
        echo "cached $role $tset $d$(deps_note "$role")"
    elif ! deps_fetch; then
        failed=1
    fi
done
echo "deps.sh: records in $run" >&2
exit "$failed"
