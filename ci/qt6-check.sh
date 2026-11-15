#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/qt6-check.sh - the Qt6 stage: QGIS's pyqt5_to_pyqt6.py checker, as plugins.qgis.org runs it on every upload.
# Usage, started by ci/run-all.sh through ci/stage.sh: sh ci/qt6-check.sh
# The checker scans copies of fiberq/ and tests/qt6_seed/ (in CI_WORK). It writes its findings to its log file:
#   fiberq/          must give ZERO findings, and the checker must exit 0 there (else the site marks the plugin
#                    NOT_COMPATIBLE)
#   tests/qt6_seed/  must give at least QT6_MIN_SEED findings (4; only an in-place run reads QT6_MIN_SEED): the
#                    self-test that proves the checker still works and is still being read
# The findings go to CI_OUT/qt6-fiberq.txt and CI_OUT/qt6-qt6_seed.txt; result.txt records what ran.
# Exit: 0 pass, or (in place, no checker found) a skip; 1 findings in fiberq/ or a failing checker there;
#       2 self-test failed, or usage; 3 the checker or the copies are missing.
set -u
umask 022

if [ $# -ne 0 ]; then echo "qt6-check.sh: usage: sh ci/qt6-check.sh (no arguments)" >&2; exit 2; fi
if [ -z "${CI_DIR:-}" ] || [ -z "${CI_OUT:-}" ] || [ -z "${CI_WORK:-}" ] || [ ! -d "$CI_OUT" ] ||
    [ ! -d "$CI_WORK" ]; then
    echo "qt6-check.sh: run stages through ci/run-all.sh: sh ci/run-all.sh --only qt6" \
        "(in place: CI_IN_PLACE=1 sh ci/run-all.sh --only qt6)" >&2
    exit 2
fi
if [ -z "${CI_SRC:-}" ]; then echo "qt6-check.sh: no tested tree (CI_SRC is empty)" >&2; exit 2; fi

min=4
if [ "${CI_IN_PLACE:-}" = 1 ]; then min=${QT6_MIN_SEED:-4}; fi
case $min in
    ''|*[!0-9]*) echo "qt6-check.sh: QT6_MIN_SEED must be a whole number, not '$min'" >&2; exit 2 ;;
esac
image=${CI_IMAGE_REF:-}
if [ "${CI_IN_PLACE:-}" = 1 ]; then image='in place'; fi

checker=${QT6_CHECKER:-$(command -v pyqt5_to_pyqt6.py 2>/dev/null)}
if [ -z "$checker" ] && [ -f /usr/local/bin/pyqt5_to_pyqt6.py ]; then checker=/usr/local/bin/pyqt5_to_pyqt6.py; fi
if [ -z "$checker" ] || [ ! -f "$checker" ]; then
    if [ "${CI_IN_PLACE:-}" = 1 ]; then
        echo "qt6-check.sh: no pyqt5_to_pyqt6.py here (PATH, /usr/local/bin or QT6_CHECKER); skipped"
        {
            printf 'skipped=needs the Qt6 checker (ghcr.io/qgis/pyqgis4-checker)\n'
            printf 'image=%s\nmin_seed=%s\n' "$image" "$min"
        } >"$CI_OUT/result.txt" || exit 2
        exit 0
    fi
    echo "qt6-check.sh: ERROR: Qt6 checker not found (${checker:-pyqt5_to_pyqt6.py}) in ${image:-this image}" >&2
    exit 3
fi
csum=$(sha256sum "$checker" 2>/dev/null) || csum=$(shasum -a 256 "$checker" 2>/dev/null) || csum=''
csum=${csum%% *}

if ! cp -R "$CI_SRC/fiberq" "$CI_WORK/fiberq" || ! cp -R "$CI_SRC/tests/qt6_seed" "$CI_WORK/qt6_seed"; then
    echo "qt6-check.sh: cannot copy fiberq/ and tests/qt6_seed/ into $CI_WORK" >&2
    exit 3
fi
scan() {   # <fiberq|qt6_seed>: run the checker on the copy; findings to CI_OUT/qt6-<name>.txt, its status to <name>.rc
    python3 "$checker" --dry_run --logfile "$CI_WORK/$1.log" "$CI_WORK/$1" >"$CI_WORK/$1.out" 2>&1
    echo "$?" >"$CI_WORK/$1.rc"
    grep -E ':[0-9]+:[0-9]+ - ' "$CI_WORK/$1.log" 2>/dev/null \
        | sed -e "s#^$CI_WORK/fiberq/#fiberq/#" -e "s#^$CI_WORK/qt6_seed/#tests/qt6_seed/#" | sort >"$CI_OUT/qt6-$1.txt"
}
scan fiberq
scan qt6_seed
pkg_n=$(grep -c . "$CI_OUT/qt6-fiberq.txt")
seed_n=$(grep -c . "$CI_OUT/qt6-qt6_seed.txt")
pkg_rc=$(cat "$CI_WORK/fiberq.rc")
{
    printf 'checker=%s\n' "$checker"
    printf 'checker_sha256=%s\n' "$csum"
    printf 'image=%s\n' "$image"
    printf 'findings=%s\n' "$pkg_n"
    printf 'seed_findings=%s\n' "$seed_n"
    printf 'checker_rc=%s\n' "$pkg_rc"
    printf 'min_seed=%s\n' "$min"
} >"$CI_OUT/result.txt" || exit 2

case $seed_n in ''|*[!0-9]*) seed_n=0 ;; esac
if [ "$seed_n" -lt "$min" ]; then
    echo "ERROR: self-test failed - the checker found $seed_n findings in tests/qt6_seed/, expected >= $min."
    echo "       Either the checker could not run, or its output changed, or the seeds were"
    echo "       'cleaned up' (see tests/qt6_seed/README.md). Do NOT trust a green run."
    if [ -s "$CI_WORK/qt6_seed.out" ]; then
        echo "       The checker said:"
        sed -e 's/^/       | /' "$CI_WORK/qt6_seed.out" | tail -n 15
    fi
    exit 2
fi
if [ "$pkg_n" != 0 ]; then
    cat "$CI_OUT/qt6-fiberq.txt"
    echo ""
fi
if [ "$pkg_rc" != 0 ]; then
    echo "Qt6 check FAILED: the checker exited ${pkg_rc:-?} on fiberq/; plugins.qgis.org marks that NOT_COMPATIBLE."
    if [ -s "$CI_WORK/fiberq.out" ]; then
        echo "       The checker said:"
        sed -e 's/^/       | /' "$CI_WORK/fiberq.out" | tail -n 15
    fi
    exit 1
fi
if [ "$pkg_n" != 0 ]; then
    echo "Qt6 check FAILED: $pkg_n finding(s) in fiberq/."
    echo "plugins.qgis.org shows these on the plugin page's Qt6 Check tab."
    exit 1
fi
echo "Qt6 check: 0 findings in fiberq/ (self-test saw $seed_n findings in the seeds)."
exit 0
