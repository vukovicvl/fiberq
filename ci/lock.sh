#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/lock.sh - regenerate the hash-locked tool lists ci/requirements-test.txt and ci/requirements-lint.txt.
# Usage:
#   sh ci/lock.sh            maintainer step, with network
#   sh ci/lock.sh worker     the part that runs inside the container the first form starts
# In the python image of ci/legs it installs the uv of ci/requirements-lock.txt (pip --require-hashes), then runs
# "uv pip compile --universal --generate-hashes" on ci/requirements-test.in (Python 3.10 and later) and on
# ci/requirements-lint.in (Python 3.12 and later, with the test pins as constraints). The new files go to a new
# ci-results/<time>-lock/stages/lock/out/. It prints their diff against ci/ and the cp commands that take them
# over; it never writes into ci/.
# Exit: 0 done; 1 the lock failed; 2 usage or environment (including a missing python image).
set -u

lock_worker() {   # in the container: run from the input root, so the "# via" lines name ci/...
    if [ -z "${CI_IN:-}" ] || [ -z "${CI_OUT:-}" ] || [ -z "${CI_WORK:-}" ]; then
        echo "lock.sh: 'worker' runs inside the container that sh ci/lock.sh starts; run: sh ci/lock.sh" >&2
        exit 2
    fi
    cd "$CI_IN" || exit 2
    python3 -m pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes \
        --target "$CI_WORK/uv" -r ci/requirements-lock.txt || exit 1
    # --python-version is only the floor of the universal resolution; uv must not download an interpreter for it
    UV_CACHE_DIR=$CI_WORK/uv-cache UV_PYTHON_DOWNLOADS=never; export UV_CACHE_DIR UV_PYTHON_DOWNLOADS
    "$CI_WORK/uv/bin/uv" pip compile --universal --python-version 3.10 --generate-hashes \
        --custom-compile-command 'sh ci/lock.sh' -o "$CI_WORK/test.txt" ci/requirements-test.in || exit 1
    "$CI_WORK/uv/bin/uv" pip compile --universal --python-version 3.12 --generate-hashes \
        -c ci/requirements-test.in \
        --custom-compile-command 'sh ci/lock.sh' -o "$CI_WORK/lint.txt" ci/requirements-lint.in || exit 1
    for _wx in test lint; do
        { echo '# SPDX-License-Identifier: GPL-3.0-or-later'; cat "$CI_WORK/$_wx.txt"; } \
            >"$CI_OUT/requirements-$_wx.txt" || exit 1
    done
    _wv=$("$CI_WORK/uv/bin/uv" --version) || exit 1
    printf 'uv=%s\n' "$_wv" >"$CI_OUT/result.txt" || exit 1
    exit 0
}

case ${1:-} in
    worker)
        if [ $# -ne 1 ]; then echo "lock.sh: usage: sh ci/lock.sh worker" >&2; exit 2; fi
        lock_worker ;;
esac

case $0 in */*) CI_DIR=${0%/*} ;; *) CI_DIR=. ;; esac
# shellcheck source=common.sh
. "$CI_DIR/common.sh"

usage() {
    echo "usage: sh ci/lock.sh            (maintainer step, with network)"
    echo "       sh ci/lock.sh worker     (the part that runs in the container the first form starts)"
}

lock_quote() {   # <text>: print <text> as one single-quoted shell word
    printf "'%s'\n" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

case ${1:-} in
    '') ;;
    -h|--help) usage; exit 0 ;;
    *) echo "lock.sh: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
esac
if [ "${CI_IN_PLACE:-}" = 1 ]; then
    echo "lock.sh: runs on the host, where it starts a container; unset CI_IN_PLACE" >&2
    exit 2
fi

ci_init nogit
ref=$(ci_image python) || exit 2
for f in stage.sh lock.sh requirements-lock.txt requirements-test.in requirements-lint.in; do
    if [ ! -f "$CI_DIR/$f" ]; then echo "lock.sh: ci/$f not found" >&2; exit 2; fi
done
if ! ci_present "$ref"; then
    echo "lock.sh: missing image $ref; run: sh ci/pull.sh pure" >&2
    exit 2
fi

run=$(ci_new_run lock) || exit 2
if ! mkdir "$run/input" "$run/raw" "$run/stages"; then exit 2; fi
s=lock commit='' dkey='' release=no
in=$run/input out=$run/stages/lock/out
if ! tar -cf "$in/lock.tar" -C "$CI_REPO" ci/stage.sh ci/lock.sh ci/requirements-lock.txt \
    ci/requirements-test.in ci/requirements-lint.in 2>>"$run/lock.log"; then
    ci_status lock fail "input build failed: tar of the ci/ files"
    echo "lock.sh: input build failed: tar of the ci/ files (see $run/lock.log)" >&2
    exit 1
fi
if ! bytes=$(ci_bytes "$in/lock.tar"); then
    ci_status lock fail "input build failed (an input part is missing or unreadable)"
    echo "lock.sh: input build failed (an input part is missing or unreadable)" >&2
    exit 1
fi
started=$(date -u +%Y-%m-%dT%H:%M:%SZ) t0=$(date +%s)
echo "[$(date +%H:%M:%S)] lock started ($ref)" >&2
ci_feed "$in/lock.feed-rc" "$in/lock.tar" |
    ci_engine_run "fiberq-ci-${run##*/}-$$" "$ref" default "$(ci_timeout_of lock)" "$bytes" lock.sh worker \
        >"$run/raw/lock.tar" 2>>"$run/lock.log"
erc=$?
ci_verdict lock "$erc" "image=$ref" "started=$started"
res=$(ci_result_of lock)
why=$(sed -n 's/^reason=//p' "$run/stages/lock/status" | tail -n 1)
echo "[$(date +%H:%M:%S)] lock $res ($(( $(date +%s) - t0 )) s) $why" >&2
if [ "$res" != pass ]; then
    echo "lock.sh: the lock failed: $why (log: $run/lock.log)" >&2
    exit 1
fi
for x in test lint; do
    if [ ! -s "$out/requirements-$x.txt" ]; then
        echo "lock.sh: the stage passed but wrote no requirements-$x.txt (log: $run/lock.log)" >&2
        exit 1
    fi
done

echo "lock.sh: $(sed -n 's/^uv=//p' "$out/result.txt" | head -n 1) wrote new lock files to $out"
changed=''
for x in test lint; do
    if [ ! -f "$CI_DIR/requirements-$x.txt" ]; then
        echo "ci/requirements-$x.txt does not exist yet"
        changed="$changed $x"
    elif cmp -s "$CI_DIR/requirements-$x.txt" "$out/requirements-$x.txt"; then
        echo "ci/requirements-$x.txt: unchanged"
    else
        ( cd "$CI_REPO" && diff -u "ci/requirements-$x.txt" "$out/requirements-$x.txt" )
        changed="$changed $x"
    fi
done
if [ -z "$changed" ]; then
    echo "ci/ already holds these lock files; nothing to copy."
    exit 0
fi
echo "To take them over, run from $CI_REPO:"
for x in $changed; do
    echo "  cp $(lock_quote "$out/requirements-$x.txt") ci/requirements-$x.txt"
done
exit 0
