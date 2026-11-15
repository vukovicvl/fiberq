#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/floor-check.sh - the floor stage: tests/floor_check.py in the QGIS that qgisMinimumVersion promises.
# Usage, started by ci/run-all.sh through ci/stage.sh: sh ci/floor-check.sh
# floor_check.py parses and imports every fiberq/ module in this QGIS, after its own self-test on tests/floor_seed/.
# This stage also checks that the image's QGIS (major.minor) is fiberq/metadata.txt's qgisMinimumVersion. In place,
# on any other QGIS (or none), the stage is skipped: floor_check.py's self-test passes only on the floor's QGIS and
# Python. Its output goes to CI_OUT/floor.txt; result.txt records the counts.
# Exit: 0 pass, or (in place, not on the floor's QGIS) a skip; floor_check.py's own code when it fails (1 findings,
#       2 self-test, 3 no QGIS); else 1 when the image's QGIS is not qgisMinimumVersion; 2 usage or setup error.
set -u
umask 022

if [ $# -ne 0 ]; then echo "floor-check.sh: usage: sh ci/floor-check.sh (no arguments)" >&2; exit 2; fi
if [ -z "${CI_DIR:-}" ] || [ -z "${CI_OUT:-}" ] || [ -z "${CI_WORK:-}" ] || [ ! -d "$CI_OUT" ] ||
    [ ! -d "$CI_WORK" ]; then
    echo "floor-check.sh: run stages through ci/run-all.sh: sh ci/run-all.sh --only floor" \
        "(in place: CI_IN_PLACE=1 sh ci/run-all.sh --only floor)" >&2
    exit 2
fi
if [ -z "${CI_SRC:-}" ]; then echo "floor-check.sh: no tested tree (CI_SRC is empty)" >&2; exit 2; fi
cd "$CI_SRC" || exit 2
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen
export PYTHONDONTWRITEBYTECODE QT_QPA_PLATFORM

mm() {   # <version>: print its major.minor, nothing if it has none
    printf '%s\n' "$1" | sed -n 's/^\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p'
}
min=$(sed -n 's/^qgisMinimumVersion=//p' fiberq/metadata.txt 2>/dev/null | head -n 1 | tr -d '[:space:]')
qv=$(python3 -c 'from qgis.core import Qgis; print(Qgis.QGIS_VERSION)' 2>/dev/null) || qv=''
have=$(mm "$qv")
if [ "${CI_IN_PLACE:-}" = 1 ] && { [ -z "$have" ] || [ "$have" != "$(mm "$min")" ]; }; then
    echo "floor-check.sh: WARNING: this QGIS is ${qv:-not importable}, qgisMinimumVersion is ${min:-not set};" \
        "floor_check.py and its self-test only mean something on the floor, so the check is skipped here"
    {
        printf 'skipped=needs QGIS %s (the floor image); this environment has %s\n' "${min:-?}" "${qv:-no QGIS}"
        printf 'qgis=%s\nqgis_minimum=%s\nversion_check=warn\n' "${qv:-none}" "$min"
    } >"$CI_OUT/result.txt" || exit 2
    exit 0
fi
python3 tests/floor_check.py >"$CI_OUT/floor.txt"
rc=$?
cat "$CI_OUT/floor.txt"
seeds=$(sed -n 's/.*self-test saw \([0-9][0-9]*\) finding.*/\1/p' "$CI_OUT/floor.txt" | head -n 1)
if [ -z "$seeds" ]; then
    seeds=$(sed -n 's/.*self-test failed -- \([0-9][0-9]*\) finding.*/\1/p' "$CI_OUT/floor.txt" | head -n 1)
fi
modules=$(sed -n 's/^floor-check: \([0-9][0-9]*\) modules in .*/\1/p' "$CI_OUT/floor.txt" | head -n 1)
findings=$(sed -n 's/^floor-check: [0-9][0-9]* modules in .*, \([0-9][0-9]*\) findings.*/\1/p' "$CI_OUT/floor.txt" |
    head -n 1)
if [ -z "$findings" ]; then
    f2=$(sed -n 's/^floor-check FAILED: \([0-9][0-9]*\) unparsable, \([0-9][0-9]*\) unimportable.*/\1 \2/p' \
        "$CI_OUT/floor.txt" | head -n 1)
    if [ -n "$f2" ]; then findings=$((${f2% *} + ${f2#* })); fi
fi

if [ -n "$have" ] && [ "$have" = "$(mm "$min")" ]; then
    vc=ok
    echo "floor-check.sh: QGIS $have = qgisMinimumVersion $min"
else
    vc=fail
    echo "floor-check.sh: the image ${CI_IMAGE_REF:-} runs QGIS ${qv:-(not importable)}, but qgisMinimumVersion is" \
        "${min:-not set}; change the floor role in ci/legs and qgisMinimumVersion together" >&2
fi
{
    printf 'qgis=%s\n' "${qv:-none}"
    printf 'qgis_minimum=%s\n' "$min"
    printf 'version_check=%s\n' "$vc"
    printf 'modules=%s\n' "$modules"
    printf 'findings=%s\n' "$findings"
    printf 'seeds=%s\n' "$seeds"
    printf 'floor_check_rc=%s\n' "$rc"
} >"$CI_OUT/result.txt" || exit 2

if [ "$rc" != 0 ]; then exit "$rc"; fi
if [ "$vc" = fail ]; then exit 1; fi
exit 0
