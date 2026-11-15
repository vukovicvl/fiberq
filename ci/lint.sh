#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/lint.sh - the lint stage, run from the tested tree with the pinned lint tools.
# Usage, started by ci/run-all.sh through ci/stage.sh: sh ci/lint.sh
# Checks, all of them every time (each name is a key in result.txt):
#   flake8          fiberq tests conftest.py tools/bench, as "make flake8" runs it (plugins.qgis.org's flags)
#   bandit          fiberq, as "make bandit" runs it (all severities, config in pyproject.toml)
#   detect_secrets  fiberq, with the command and plugin set of plugins.qgis.org's scanner, counted its way
#                   (ci/report.py)
#   (ci/)           when the tested tree has a ci/: "shellcheck" on its *.sh and "flake8_ci" on its Python files
#   placeholders    the .ts placeholder check, read from the Makefile's I18N_PLACEHOLDER_PY block
# result.txt records each check's count and exit status; the outputs go to CI_OUT.
# Exit: 0 every check passed; 1 a check failed; 2 usage or setup error (run by hand, pinned tools not in use).
set -u
umask 022

if [ $# -ne 0 ]; then echo "lint.sh: usage: sh ci/lint.sh (no arguments)" >&2; exit 2; fi
if [ -z "${CI_DIR:-}" ] || [ -z "${CI_OUT:-}" ] || [ -z "${CI_WORK:-}" ] || [ ! -d "$CI_OUT" ] ||
    [ ! -d "$CI_WORK" ]; then
    echo "lint.sh: run stages through ci/run-all.sh: sh ci/run-all.sh --only lint" \
        "(in place: CI_IN_PLACE=1 sh ci/run-all.sh --only lint)" >&2
    exit 2
fi
if [ -z "${CI_SRC:-}" ]; then echo "lint.sh: no tested tree (CI_SRC is empty)" >&2; exit 2; fi
cd "$CI_SRC" || exit 2
deps=${CI_DEPS:-}
deps=${deps%/}
if [ -z "$deps" ]; then echo "lint.sh: no pinned tools (CI_DEPS is empty)" >&2; exit 2; fi
PYTHONPATH=$deps${PYTHONPATH:+:$PYTHONPATH} PATH=$deps/bin:$PATH PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH PATH PYTHONDONTWRITEBYTECODE

# the proof that the pinned tools are the ones in use
lint_proof() {   # <module>: exit 2 unless <module> loads from $deps
    if ! _lpf=$(python3 -c "import sys, $1; sys.stdout.write($1.__file__)"); then
        echo "lint.sh: $1 does not import here (the error is above); it must load from the pinned tools in $deps" >&2
        exit 2
    fi
    case $_lpf in
        "$deps"/*) ;;
        *) echo "lint.sh: pinned tools not in use: $1 loads from $_lpf, not from $deps" >&2; exit 2 ;;
    esac
}
for m in flake8 bandit detect_secrets; do lint_proof "$m"; done
sc=$(command -v shellcheck) || sc=''
if [ "$sc" != "$deps/bin/shellcheck" ]; then
    echo "lint.sh: pinned tools not in use: shellcheck is ${sc:-not found}, not $deps/bin/shellcheck" >&2
    exit 2
fi
res=$CI_OUT/result.txt
printf 'pythonpath=prepend\ntools=pinned\n' >"$res" || exit 2

ds() {   # <detect-secrets arguments>: the detect-secrets command line, from the pinned package
    python3 -c 'import sys; from detect_secrets.main import main; sys.exit(main())' "$@"
}
v=$(python3 -m flake8 --version 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')
printf 'flake8_version=%s\n' "$v" >>"$res"
v=$(python3 -m bandit --version 2>/dev/null | sed -n '1s/^[^ ]* //p')
printf 'bandit_version=%s\n' "$v" >>"$res"
v=$(ds --version 2>/dev/null | head -n 1)
printf 'detect_secrets_version=%s\n' "$v" >>"$res"
v=$(shellcheck --version 2>/dev/null | sed -n 's/^version: //p')
printf 'shellcheck_version=%s\n' "$v" >>"$res"

failed=''
lint_record() {   # <check> <count or text> <exit status> <passed: yes|no>: append to result.txt and the log
    printf '%s=%s\n%s_rc=%s\n' "$1" "$2" "$1" "$3" >>"$res"
    if [ "$4" = yes ]; then
        echo "lint.sh: $1: pass ($2)"
    else
        echo "lint.sh: $1: FAIL ($2, exit status ${3:-none})"
        failed="$failed $1"
    fi
}
lint_count() {   # <pattern> <file>: print the number of lines of <file> matching <pattern>; nothing if unreadable
    if [ -f "$2" ]; then grep -c -e "$1" "$2"; fi
}

# 1. flake8, as Makefile's flake8 target
python3 -m flake8 --isolated --max-line-length=120 --ignore=E501 fiberq tests conftest.py tools/bench \
    >"$CI_OUT/flake8.txt"
rc=$?
n=$(lint_count . "$CI_OUT/flake8.txt")
cat "$CI_OUT/flake8.txt"
ok=no; if [ "$rc" = 0 ] && [ "$n" = 0 ]; then ok=yes; fi
lint_record flake8 "${n:-unreadable output}" "$rc" "$ok"

# 2. Bandit, as Makefile's bandit target
python3 -m bandit -r fiberq -q -c pyproject.toml >"$CI_OUT/bandit.txt" 2>&1
rc=$?
n=$(lint_count '^>> Issue: ' "$CI_OUT/bandit.txt")
if [ "$rc" != 0 ] || [ "$n" != 0 ]; then cat "$CI_OUT/bandit.txt"; fi
ok=no; if [ "$rc" = 0 ] && [ "$n" = 0 ]; then ok=yes; fi
lint_record bandit "${n:-unreadable output}" "$rc" "$ok"

# 3. detect-secrets on the files that ship, with the command of plugins.qgis.org's scanner; ci/report.py counts the
#    JSON
ds scan --all-files --exclude-files 'metadata\.txt' --exclude-files '\.secrets\.baseline' \
    --disable-plugin IPPublicDetector fiberq >"$CI_OUT/detect-secrets.json"
rc=$?
ok=no
if [ "$rc" != 0 ]; then
    n="the scan failed"
elif [ ! -s "$CI_OUT/detect-secrets.json" ]; then
    n="no JSON written"
elif ! n=$(python3 -I "$CI_DIR/report.py" secrets "$CI_OUT/detect-secrets.json"); then
    n="the JSON is missing or unparsable (ci/report.py secrets failed)"
else
    case $n in
        ''|*[!0-9]*) n="the count is not a number: '$n'" ;;
        *) if [ "$n" -eq 0 ]; then ok=yes; fi ;;
    esac
fi
if [ "$ok" = no ]; then cat "$CI_OUT/detect-secrets.json"; fi
lint_record detect_secrets "$n" "$rc" "$ok"

# 4. the tested tree's own ci/: shellcheck on the shell scripts, flake8 on the Python helpers
if [ ! -d ci ]; then
    lint_record shellcheck "no ci/ in the tested tree" '' yes
    lint_record flake8_ci "no ci/ in the tested tree" '' yes
else
    nsh=0
    for f in ci/*.sh; do if [ -f "$f" ]; then nsh=$((nsh + 1)); fi; done
    npy=0
    for f in ci/*.py; do if [ -f "$f" ]; then npy=$((npy + 1)); fi; done
    if [ "$nsh" -gt 0 ]; then
        shellcheck -s sh -x -P SCRIPTDIR -f gcc ci/*.sh >"$CI_OUT/shellcheck.txt" 2>&1
        rc=$?
    else
        : >"$CI_OUT/shellcheck.txt"
        rc=0
    fi
    n=$(lint_count . "$CI_OUT/shellcheck.txt")
    cat "$CI_OUT/shellcheck.txt"
    ok=no; if [ "$rc" = 0 ] && [ "$n" = 0 ]; then ok=yes; fi
    lint_record shellcheck "${n:-unreadable output}" "$rc" "$ok"
    printf 'shellcheck_files=%s\n' "$nsh" >>"$res"
    python3 -m flake8 --isolated --max-line-length=120 --ignore=E501 ci >"$CI_OUT/flake8-ci.txt" 2>&1
    rc=$?
    n=$(lint_count . "$CI_OUT/flake8-ci.txt")
    cat "$CI_OUT/flake8-ci.txt"
    ok=no; if [ "$rc" = 0 ] && [ "$n" = 0 ]; then ok=yes; fi
    lint_record flake8_ci "${n:-unreadable output}" "$rc" "$ok"
    printf 'flake8_ci_files=%s\n' "$npy" >>"$res"
fi

# 5. the .ts placeholder check: the Makefile's own I18N_PLACEHOLDER_PY, extracted, never copied into ci/
pf=$CI_WORK/i18n_placeholders.py
rc='' n=''
if [ ! -f Makefile ]; then
    n="no Makefile in the tested tree"
else
    sed -n '/^define I18N_PLACEHOLDER_PY$/,/^endef$/p' Makefile | sed '1d;$d' >"$pf"
    if [ ! -s "$pf" ]; then
        n="I18N_PLACEHOLDER_PY not found in the Makefile"
    elif grep -q '[$]' "$pf"; then
        n="I18N_PLACEHOLDER_PY contains \$; ci/ cannot reproduce make's expansion"
    else
        python3 -I "$pf" >"$CI_OUT/placeholders.txt" 2>&1
        rc=$?
        cat "$CI_OUT/placeholders.txt"
        if [ "$rc" = 0 ]; then
            n=0
        else
            n=$(sed -n 's/^\([0-9][0-9]*\) placeholder problem.*/\1/p' "$CI_OUT/placeholders.txt" | head -n 1)
            n=${n:-the check failed}
        fi
    fi
fi
ok=no; if [ "$rc" = 0 ]; then ok=yes; fi
lint_record placeholders "$n" "$rc" "$ok"

if [ -n "$failed" ]; then
    printf 'failed=%s\n' "${failed# }" >>"$res"
    echo "lint.sh: FAILED:$failed"
    exit 1
fi
printf 'failed=none\n' >>"$res"
echo "lint.sh: every check passed"
exit 0
