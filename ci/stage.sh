#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/stage.sh <script> [<arg>] - run one pipeline stage and record how it ended.
# ci/run-all.sh starts it, in a container or (CI_IN_PLACE=1) in this environment.
# Exit: the stage's own code; 2 started by hand (not by ci/run-all.sh); 99 the setup in the container failed (pinned
#       tools named in CI_DEPS_KEY but not in the input, no out/ or work/ folder) or the results tar could not be
#       written.
set -u
script=${1:?usage: stage.sh <script> [<arg>]}; shift
if [ "${CI_IN_PLACE:-}" = 1 ]; then
    if [ -z "${CI_DIR:-}" ] || [ -z "${CI_SRC:-}" ] || [ -z "${CI_OUT:-}" ] || [ -z "${CI_WORK:-}" ]; then
        echo "stage.sh: run stages through ci/run-all.sh, e.g. CI_IN_PLACE=1 sh ci/run-all.sh --only lint" >&2
        exit 2
    fi
else
    # only the container's boot (CI_BOOT in ci/common.sh) starts it here, with the stream's size in CI_IN_BYTES
    if [ "$0" != /tmp/w/ci/stage.sh ] || [ -z "${CI_IN_BYTES:-}" ]; then
        echo "stage.sh: run stages through ci/run-all.sh, e.g. sh ci/run-all.sh --only lint" \
            "(in place: CI_IN_PLACE=1 sh ci/run-all.sh --only lint)" >&2
        exit 2
    fi
    exec 3>&1 1>&2                                   # fd 3 = the results channel; all else -> stderr
    CI_IN=/tmp/w CI_DIR=/tmp/w/ci CI_OUT=/tmp/w/out CI_WORK=/tmp/w/work
    CI_SRC=''; [ -d /tmp/w/src ] && CI_SRC=/tmp/w/src
    CI_DEPS=''; [ -d /tmp/w/deps ] && CI_DEPS=/tmp/w/deps
    if [ -n "${CI_DEPS_KEY:-}" ] && [ -z "$CI_DEPS" ]; then
        echo "stage.sh: the pinned tools ($CI_DEPS_KEY) were not in the input" >&2
        exit 99
    fi
    mkdir "$CI_OUT" "$CI_WORK" || exit 99
    # A fresh QGIS profile in the tree. The tree keeps the modes git gave it: tests copy parts of it with
    # shutil.copy2 or copytree and write into the copies, which chmod a-w would make read-only.
    if [ -n "$CI_SRC" ]; then
        mkdir -p "$CI_SRC/.qgis-settings/profiles/default/QGIS"
    fi
fi
export CI_IN CI_DIR CI_SRC CI_OUT CI_WORK CI_DEPS
case $script in *.py) set -- python3 -I "$CI_DIR/$script" "$@" ;; *) set -- sh "$CI_DIR/$script" "$@" ;; esac
t=${CI_TIMEOUT:-600}; cpid=''; stop=''
trap 'stop=1; [ -z "$cpid" ] || kill -TERM "$cpid" 2>/dev/null' TERM HUP INT
start=$(date +%s)
if command -v timeout >/dev/null 2>&1; then
    timeout -k 60 "$t" "$@" </dev/null 3>&- &
else
    echo "stage.sh: no timeout command here; running without a time limit" >&2
    "$@" </dev/null 3>&- &
fi
cpid=$!
[ -z "$stop" ] || kill -TERM "$cpid" 2>/dev/null
wait "$cpid"; rc=$?
while [ -n "$stop" ] && kill -0 "$cpid" 2>/dev/null; do wait "$cpid"; rc=$?; done
trap - TERM HUP INT
printf '%s\n' "$rc" >"$CI_OUT/exit-code"
printf '%s\n' "$(( $(date +%s) - start ))" >"$CI_OUT/seconds"
if [ "${CI_IN_PLACE:-}" != 1 ]; then tar -c -f - -C "$CI_OUT" . >&3 || exit 99; fi
exit "$rc"
