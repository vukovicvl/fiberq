#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/app-smoke.sh - the app stages, app-340 and app-42: the real QGIS desktop installs and runs the tested FiberQ.
# Usage, started by ci/run-all.sh through ci/stage.sh: sh ci/app-smoke.sh <340|42>   (host mode only)
# In the 3.40 or 4.2 image of ci/legs, under xvfb-run, with no window manager, a fresh profile and HOME, as uid 1000
# and with no network, QGIS starts twice. The tested tree's tests/app/ drives it (tests/app/smoke.py says what each
# start does and checks); this script builds the zip, starts QGIS, and judges each start by its records:
#   install    the zip this stage built from the tested tree's fiberq/, installed with QGIS's own Install from ZIP
#              code; then the checks of what it loaded, against the tested tree's tests/initgui_golden.json
#   workflow   QGIS loads FiberQ at startup; a short workflow through FiberQ's own buttons, drop-downs, map tools
#              and dialogs; a reload of the plugin. It runs only when install's records show FiberQ installed and
#              enabled (install_gate=yes of ci/report.py app-junit), so after a failed check too
# The contract with tests/app/, the same for each start: HOME=<work>/home, LC_ALL=C.UTF-8, QT_QPA_PLATFORM=xcb and
# PYTHONDONTWRITEBYTECODE=1, with LANG, LANGUAGE, LC_MESSAGES, QGIS_CUSTOM_CONFIG_PATH, WAYLAND_DISPLAY and DISPLAY
# unset, and
#   APP_START       install or workflow: the start tests/app/start.py runs (tests/app/smoke.py's STARTS)
#   APP_OUT         a new folder for the start's records
#   APP_ZIP         the zip; APP_GOLDEN: the tested tree's tests/initgui_golden.json
#   APP_TESTS       the tested tree's tests/, which start.py appends to sys.path
#   APP_DEADLINE_S  the runner's deadline: the start's time limit less 30 s
#   PYQGIS_STARTUP  the tested tree's tests/app/guard.py
# then: timeout -k 10 <limit> xvfb-run -a -e <APP_OUT>/xvfb.err -s "-screen 0 1920x1080x24" qgis --nologo
#           --noversioncheck --lang en_US --profiles-path <work>/profiles --code <tested tree>/tests/app/start.py
# The APP_* variables are only ever added, never renamed or dropped, and ci/report.py app-junit reads every earlier
# format of the runner's report.json: an older tree, tested with --ref, still runs and is still read.
# Outputs in CI_OUT: result.txt; junit.xml (one test case per check, plus run.ended per start, from ci/report.py
# app-junit); zip-list.txt (the zip's entries: path, size, CRC-32); install/ and workflow/: qgis.out, xvfb.err (what
# Xvfb and xauth said), log.jsonl, steps.jsonl, report.json, actions-*.json, the screenshots NNN_<step>_<label>.png,
# in workflow/ the exported bundle.gpkg, and guard.json with guard-window.png when the startup guard ended QGIS.
# The profile and HOME stay in CI_WORK.
# In place (CI_IN_PLACE=1) the stage is skipped, as test-coverage is: it needs the image's QGIS and xvfb-run.
# Exit: the largest code of the two starts, each taken from its records (ci/report.py app-junit):
#   0 both starts passed every check (and an in-place skip); 1 a check failed, junit.xml could not be written, or
#     the workflow start did not run although nothing failed;
#   2 usage or setup: started by hand, the image's QGIS not the leg's, no qgis, xvfb-run, xauth, Xvfb or timeout,
#     CI_TIMEOUT too short (at least 210 s), the zip could not be built, or the tested tree predates the app stage
#     (no junit.xml then); 3 a window that QGIS opened for a Python error, or a window nothing expected (the runner's
#     or the guard's watch); 4 a start passed its deadline, or its time limit stopped QGIS; 5 a scenario raised;
#   6 QGIS ended without a verdict its records confirm: a crash (QGIS died on a signal), no report.json, or an exit
#     code that the report or guard.json does not give, such as xvfb-run's own (1 Xvfb or its cleanup, 2 usage,
#     3 no xauth, 5 its temporary folder, 6 options). A TERM, HUP or INT stops the stage with the largest code so
#     far, or 143 when that is 0.
set -u
umask 022

leg=${1:-}
case $leg in
    340) want=3.40 ;;
    42) want=4.2 ;;
    *) echo "app-smoke.sh: usage: sh ci/app-smoke.sh <340|42>" >&2; exit 2 ;;
esac
if [ $# -ne 1 ]; then echo "app-smoke.sh: usage: sh ci/app-smoke.sh <340|42>" >&2; exit 2; fi
if [ -z "${CI_DIR:-}" ] || [ -z "${CI_OUT:-}" ] || [ -z "${CI_WORK:-}" ] || [ ! -d "$CI_OUT" ] ||
    [ ! -d "$CI_WORK" ]; then
    echo "app-smoke.sh: run stages through ci/run-all.sh: sh ci/run-all.sh --only app-$leg (host mode only)" >&2
    exit 2
fi
res=$CI_OUT/result.txt
suite=${CI_STAGE:-app-$leg}

# what runs here, recorded before anything is judged
py=$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null) || py=''
qgis=$(python3 -c 'from qgis.core import Qgis; print(Qgis.QGIS_VERSION)' 2>/dev/null) || qgis=''
{
    printf 'leg=%s\n' "$leg"
    printf 'python=%s\n' "$py"
    printf 'qgis=%s\n' "${qgis:-none}"
    printf 'uid=%s\n' "$(id -u)"
} >"$res" || exit 2

if [ "${CI_IN_PLACE:-}" = 1 ]; then
    echo "app-smoke.sh: app-$leg runs in host mode only (the $leg image, with its QGIS and xvfb-run); skipped"
    printf 'skipped=host mode only (the %s image)\n' "$leg" >>"$res" || exit 2
    exit 0
fi

setup_failed() {   # <failed= value> <message>: a setup error: say it, record it, exit 2 (no junit.xml)
    echo "app-smoke.sh: $2" >&2
    printf 'failed=%s\n' "$1" >>"$res"
    exit 2
}
if [ -z "${CI_SRC:-}" ]; then setup_failed 'setup (no tested tree)' 'no tested tree (CI_SRC is empty)'; fi
for tool in qgis xvfb-run xauth Xvfb timeout; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        setup_failed "setup (no $tool)" "$tool is not on PATH in the $leg image (${CI_IMAGE_REF:-})"
    fi
done
have=$(printf '%s\n' "$qgis" | sed -n 's/^\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p')
if [ "$have" != "$want" ]; then
    setup_failed "setup (QGIS ${qgis:-none}, not $want)" \
        "app-$leg expects QGIS $want, the image ${CI_IMAGE_REF:-} has ${qgis:-no QGIS}; check the $leg line of ci/legs"
fi
limit=${CI_TIMEOUT:-900}
case $limit in ''|*[!0-9]*) setup_failed 'setup (CI_TIMEOUT)' "CI_TIMEOUT must be whole seconds, not '$limit'" ;; esac
budget=$((limit - 60))
if [ "$budget" -lt 150 ]; then
    setup_failed 'setup (CI_TIMEOUT too short)' "CI_TIMEOUT is too short for the app stage (at least 210 s): $limit"
fi

# the tested tree must hold the app stage's code and the golden file: a tree from before it (--ref v1.6.0) fails
# here, as the pure stage fails a tree without ci/pure-count
for f in tests/app/start.py tests/app/guard.py tests/support/initgui_snapshot.py tests/initgui_golden.json; do
    if [ ! -f "$CI_SRC/$f" ]; then
        setup_failed "app (the tested tree has no $f: it predates the app stage)" \
            "the tested tree has no $f: it predates the app stage; run app-$leg on a later commit"
    fi
done

# nothing of the environment reaches QGIS's language or profile: LANGUAGE would beat LC_ALL in QLocale
cd "$CI_WORK" || exit 2
unset LANG LANGUAGE LC_MESSAGES QGIS_CUSTOM_CONFIG_PATH WAYLAND_DISPLAY DISPLAY
mkdir "$CI_WORK/home" "$CI_WORK/profiles" || exit 2

# the zip, from the tested tree's fiberq/ (a git archive of the snapshot in host mode, so nothing ignored is in it)
zip=$CI_WORK/fiberq.zip
zl=$CI_OUT/zip-list.txt
if ! python3 -I -m zipfile -c "$zip" "$CI_SRC/fiberq" || ! python3 -I "$CI_DIR/zipcheck.py" list "$zip" >"$zl"; then
    setup_failed 'zip (the zip of the tested fiberq/ could not be built or listed)' \
        "the zip of $CI_SRC/fiberq could not be built or listed (the error is above)"
fi
n=$(grep -c . "$zl")
outside=$(grep -c -v '^fiberq/' "$zl")
if [ "$n" = 0 ] || [ "$outside" != 0 ]; then
    setup_failed "zip ($n entries, $outside outside fiberq/)" "the zip has $n entries, $outside of them outside fiberq/"
fi
zls=$(sha256sum "$zl" | cut -d ' ' -f 1)
printf 'zip_entries=%s\nzip_list_sha256=%s\n' "$n" "$zls" >>"$res" || exit 2

# the time limits: the install start gets a third of the budget, the workflow start the rest less 20 s; each
# start's runner ends it 30 s before its limit, counted from when the runner starts (3 to 6 s after QGIS
# starts here), and timeout(1) kills QGIS 10 s after the limit
t1=$((budget / 3))
t2=$((budget - t1 - 20))
printf 'budget=%s\ninstall_timeout=%s\nworkflow_timeout=%s\n' "$budget" "$t1" "$t2" >>"$res" || exit 2

# Each QGIS start runs as a job of this script, which passes a TERM, HUP or INT on to it and waits for it, as
# ci/test.sh does: timeout(1) puts QGIS in a process group of its own, which ci/stage.sh's own timeout does not
# reach. Once a signal came, no further start begins.
tp='' stop=''
trap 'stop=1; [ -z "$tp" ] || kill -TERM "$tp" 2>/dev/null' TERM HUP INT
app_start() {   # <start> <time limit in s>: one QGIS start; sets rc (its exit status) and secs
    mkdir "$CI_OUT/$1" || exit 2
    _as0=$(date +%s)
    HOME=$CI_WORK/home APP_START=$1 APP_OUT=$CI_OUT/$1 APP_ZIP=$zip APP_GOLDEN=$CI_SRC/tests/initgui_golden.json \
    APP_TESTS=$CI_SRC/tests APP_DEADLINE_S=$(($2 - 30)) PYQGIS_STARTUP=$CI_SRC/tests/app/guard.py \
    QT_QPA_PLATFORM=xcb LC_ALL=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
        timeout -k 10 "$2" xvfb-run -a -e "$CI_OUT/$1/xvfb.err" -s "-screen 0 1920x1080x24" \
        qgis --nologo --noversioncheck --lang en_US --profiles-path "$CI_WORK/profiles" \
        --code "$CI_SRC/tests/app/start.py" >"$CI_OUT/$1/qgis.out" 2>&1 </dev/null &
    tp=$!
    [ -z "$stop" ] || kill -TERM "$tp" 2>/dev/null
    wait "$tp"; rc=$?
    while [ -n "$stop" ] && kill -0 "$tp" 2>/dev/null; do wait "$tp"; rc=$?; done
    tp=''
    secs=$(($(date +%s) - _as0))
    echo "app-smoke.sh: the $1 start ended with exit $rc after $secs s"
}
key() {   # <key> <lines>: the value of the first <key>= line
    printf '%s\n' "$2" | sed -n "s/^$1=//p" | head -n 1
}

r1=none s1=0 r2=none s2=0
if [ -z "$stop" ]; then app_start install "$t1"; r1=$rc s1=$secs; fi
printf 'install_exit=%s\ninstall_seconds=%s\n' "$r1" "$s1" >>"$res"
# the workflow start runs only on install's evidence: its report.json shows FiberQ installed and enabled
gate=no
if [ -z "$stop" ] && [ "$r1" != none ]; then
    first=$(python3 -I "$CI_DIR/report.py" app-junit "$suite" "$CI_WORK/install-junit.xml" \
        install "$CI_OUT/install" "$r1" "$s1" "$t1")
    gate=$(key install_gate "$first")
fi
if [ -z "$stop" ] && [ "$gate" = yes ]; then app_start workflow "$t2"; r2=$rc s2=$secs; fi
printf 'workflow_exit=%s\nworkflow_seconds=%s\n' "$r2" "$s2" >>"$res"
trap - TERM HUP INT

# the JUnit record of both starts, and each start's code from its evidence
keys=$(python3 -I "$CI_DIR/report.py" app-junit "$suite" "$CI_OUT/junit.xml" \
    install "$CI_OUT/install" "$r1" "$s1" "$t1" workflow "$CI_OUT/workflow" "$r2" "$s2" "$t2")
jrc=$?
if [ -n "$keys" ]; then printf '%s\n' "$keys" >>"$res"; fi
shots=$(find "$CI_OUT" -type f -name '*.png' | wc -l | tr -d ' ')
printf 'screenshots=%s\n' "$shots" >>"$res"

raw_code() {   # <raw exit|none>: a start's code from its exit status alone, for when app-junit gave none
    case $1 in
        none|0) echo 0 ;;
        1|3|4|5) echo "$1" ;;
        124|137) echo 4 ;;
        *) echo 6 ;;
    esac
}
code=0 failed='' coded=yes
for st in install workflow; do
    if [ "$st" = install ]; then raw=$r1; else raw=$r2; fi
    c=$(key "${st}_code" "$keys")
    case $c in
        ''|*[!0-9]*) coded=no c=$(raw_code "$raw") ;;
    esac
    if [ "$c" -gt "$code" ]; then code=$c; fi
    if [ "$raw" = 0 ] && [ "$c" = 0 ] && [ "$(key "${st}_verdict" "$keys")" = pass ]; then continue; fi
    why=$(key "${st}_reason" "$keys")
    if [ "$raw" = none ]; then
        if [ "$st" = workflow ] && [ "$r1" != none ]; then
            failed="$failed; workflow (${why:-not run})"
            # a backstop: a workflow start that did not run never passes, though install's code says nothing failed
            if [ -z "$stop" ] && [ "$code" = 0 ]; then code=1; fi
        fi
        continue
    fi
    ids=$(key "${st}_failed_ids" "$keys" | sed 's/,/, /g')
    if [ "$c" = 1 ] && [ -n "$ids" ]; then why="${why:-a check failed}; failed: $ids"; fi
    failed="$failed; $st (exit $raw: ${why:-no verdict from ci/report.py app-junit})"
done
if [ "$jrc" != 0 ] || [ "$coded" = no ]; then
    # no junit.xml, or not all of app-junit's lines: never a pass
    if [ "$code" -lt 1 ]; then code=1; fi
    said='junit.xml was not written'
    if [ -f "$CI_OUT/junit.xml" ]; then said='junit.xml written, its result lines not'; fi
    failed="$failed; junit (ci/report.py app-junit exited $jrc: $said)"
fi
if [ -n "$stop" ]; then
    failed="$failed; stopped by a signal"
    if [ "$code" = 0 ]; then code=143; fi
fi
failed=${failed#; }
printf 'failed=%s\n' "${failed:-none}" >>"$res"
if [ "$code" = 0 ]; then
    echo "app-smoke.sh: app-$leg: both starts passed every check"
else
    echo "app-smoke.sh: app-$leg: exit $code: $failed" >&2
fi
exit "$code"
