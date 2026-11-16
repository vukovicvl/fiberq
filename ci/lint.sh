#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/lint.sh - the lint stage, run from the tested tree with the pinned lint tools.
# Usage, started by ci/run-all.sh through ci/stage.sh: sh ci/lint.sh
# Checks, all of them every time (each name is a key in result.txt):
#   flake8          fiberq tests conftest.py tools/bench, with the flags of plugins.qgis.org's scanner
#                   (--isolated --max-line-length=120 --ignore=E501)
#   bandit          fiberq, at every severity (the scanner reports LOW findings too), config in pyproject.toml
#   detect_secrets  fiberq, with the command and plugin set of plugins.qgis.org's scanner, counted its way
#                   (ci/report.py)
#   (ci/)           when the tested tree has a ci/: "shellcheck" on its *.sh and on the git hooks in ci/hooks/,
#                   and "flake8_ci" on its Python files
#   placeholders    the .ts placeholder check, read from the Makefile's I18N_PLACEHOLDER_PY block
#   wrappers        when the tested tree has a .gitlab-ci.yml or a ci/hooks/: both forge configs only call
#                   scripts in ci/, and their images and stage lists agree with ci/legs and ci/common.sh (check 6)
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

# 1. flake8, with the flags of plugins.qgis.org's scanner
python3 -m flake8 --isolated --max-line-length=120 --ignore=E501 fiberq tests conftest.py tools/bench \
    >"$CI_OUT/flake8.txt"
rc=$?
n=$(lint_count . "$CI_OUT/flake8.txt")
cat "$CI_OUT/flake8.txt"
ok=no; if [ "$rc" = 0 ] && [ "$n" = 0 ]; then ok=yes; fi
lint_record flake8 "${n:-unreadable output}" "$rc" "$ok"

# 2. Bandit, at every severity, as plugins.qgis.org's scanner
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

# 4. the tested tree's own ci/: shellcheck on the shell scripts and the git hooks, flake8 on the Python helpers
if [ ! -d ci ]; then
    lint_record shellcheck "no ci/ in the tested tree" '' yes
    lint_record flake8_ci "no ci/ in the tested tree" '' yes
else
    set --
    for f in ci/*.sh ci/hooks/*; do if [ -f "$f" ]; then set -- "$@" "$f"; fi; done
    nsh=$#
    npy=0
    for f in ci/*.py; do if [ -f "$f" ]; then npy=$((npy + 1)); fi; done
    if [ "$nsh" -gt 0 ]; then
        shellcheck -s sh -x -P SCRIPTDIR -f gcc "$@" >"$CI_OUT/shellcheck.txt" 2>&1
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

# 6. the forge wrappers, in a tested tree that has a .gitlab-ci.yml or a ci/hooks/ (both arrive with the wrappers;
#    a tree from before them, such as v1.6.0, is not judged by these rules). The rules read each file line by line,
#    in the one-line form both files are written in: they are not a YAML parser. Each problem is one line of
#    wrappers.txt:
#    .gitlab-ci.yml  every image: line reads "image: <ref>  # ci/legs: <role>", <ref> being <role>'s digest in
#                    ci/legs; every script: line reads "script: CI_IN_PLACE=1 sh ci/run-all.sh --strict --only
#                    <stage>" (so no before_script or after_script); the Nth image line is the ci/legs image of the
#                    Nth script line's stage (python for pure and lint, 42 for 42); no include, services, trigger,
#                    run, step, variables, parallel or allow_failure, and no when: but "when: always" (a manual job
#                    waits for someone to start it, and may fail without failing the pipeline; a delayed job starts
#                    only after its delay; an on_failure job runs only when a job of an earlier stage failed)
#    .github/workflows/*.yml, *.yaml
#                    every run: line reads "run: exec sh ci/<script>.sh", then optionally --release and --only, and
#                    last ${{ matrix.stage }}, which is required (exec, so that a cancelled job's SIGINT reaches the
#                    script's trap); every uses: line names actions/checkout or actions/upload-artifact at a 40-hex
#                    commit; no container, services, shell, env, defaults, working-directory, continue-on-error,
#                    matrix include or exclude, and no checkout input that fetches other code (repository, ref,
#                    token, ssh-key, github-server-url); the two "stage: [...]" lists of ci.yml are, in order,
#                    CI_DEFAULT_STAGES and CI_RELEASE_STAGES of ci/common.sh
#    both            no more indented line other than a blank or comment line follows a script:, run:, image: or
#                    uses: line (YAML would join it to the value, or reject the file); no key is written with a
#                    space before its colon (the rules read "key:"); and no line holds a CR, NEL, LS or PS
#                    character, which YAML reads as a line break, or a BOM, which libyaml skips at the start of a
#                    line: these rules see neither
#    A missing .gitlab-ci.yml or .github/workflows/ci.yml is a problem too: retiring a forge is a change to this
#    check, never a silent skip. The rules do not read when runs start: the triggers (on:), and a job or a step
#    switched off by its if: (GitHub) or by rules:, only: or except: (GitLab), are not seen, and review has to
#    catch them. The rules guard against drift; they are no security boundary (whoever can change the forge
#    configs can change ci/ too).
if [ ! -f .gitlab-ci.yml ] && [ ! -d ci/hooks ]; then
    lint_record wrappers "no .gitlab-ci.yml or ci/hooks/ in the tested tree" '' yes
else
    ww=$CI_OUT/wrappers.txt
    : >"$ww" || exit 2
    wrap_lines() {   # <file> <ERE>: "<line number>:<text>" of each line of <file> that matches and is no comment
        grep -n -E -e "$2" "$1" | grep -v -E '^[0-9]+:[[:space:]]*#'
    }
    wrap_bad() {   # <file> <line number, or empty> <problem>: one line of wrappers.txt
        if [ -n "$2" ]; then printf '%s:%s: %s\n' "$1" "$2" "$3"; else printf '%s: %s\n' "$1" "$3"; fi >>"$ww"
    }
    wrap_keys() {   # <file> <keys, as an ERE alternation> <reason>: one problem per line that sets one of the keys
        wrap_lines "$1" "^[[:space:]]*(- +)?($2)[[:space:]]*:" >"$CI_WORK/wrap-keys.txt"
        while IFS= read -r _wkl || [ -n "$_wkl" ]; do
            _wkk=$(printf '%s\n' "${_wkl#*:}" | sed 's/^[[:space:]]*//; s/^-[[:space:]]*//; s/[[:space:]]*:.*//')
            wrap_bad "$1" "${_wkl%%:*}" "$_wkk: not allowed; $3"
        done <"$CI_WORK/wrap-keys.txt"
    }
    wrap_cont() {   # <file>: one problem per more indented line after a script:, run:, image: or uses: line
        # The key's column counts a "- " that opens a sequence entry; blank and comment lines are skipped (after a
        # comment line, a more indented line is a YAML error anyway).
        awk '
            function keycol(s,   c) {
                c = match(s, /[^ ]/) - 1
                if (substr(s, c + 1, 2) == "- ") c += 2
                return c
            }
            pend && /^[ \t]*$/ { next }
            pend && /^[ \t]*#/ { next }
            pend { if (match($0, /[^ ]/) - 1 > kc) print NR ":" kl; pend = 0 }
            /^[ \t]*(- )?(script|run|image|uses):[ \t]/ { pend = 1; kc = keycol($0); kl = NR }
        ' "$1" >"$CI_WORK/wrap-cont.txt" || exit 2
        while IFS=: read -r _wcn _wck || [ -n "${_wcn:-}" ]; do
            wrap_bad "$1" "$_wcn" \
                "this line is more indented than line $_wck; a script:, run:, image: or uses: value ends on its line"
        done <"$CI_WORK/wrap-cont.txt"
    }
    wrap_breaks() {   # <file>: one problem per line holding a CR, NEL, LS, PS or BOM (YAML reads the first four as a
        # line break; libyaml skips a BOM that starts a line, so the key after it counts as indented)
        LC_ALL=C grep -n -e "$(printf '\r')" -e "$(printf '\302\205')" -e "$(printf '\342\200\250')" \
            -e "$(printf '\342\200\251')" -e "$(printf '\357\273\277')" "$1" >"$CI_WORK/wrap-breaks.txt"
        _wbm='a CR, NEL, LS, PS or BOM character: YAML reads it as a line break or skips it, these rules do not'
        _wbm="$_wbm (save the file as UTF-8 without a BOM, with LF line ends)"
        while IFS=: read -r _wbn _ || [ -n "${_wbn:-}" ]; do
            wrap_bad "$1" "$_wbn" "$_wbm"
        done <"$CI_WORK/wrap-breaks.txt"
    }
    wrap_spaced() {   # <file>: one problem per key written with a space before its colon, which the rules do not read
        wrap_lines "$1" '^[[:space:]]*(- +)?[A-Za-z0-9_.-]+[[:space:]]+:([[:space:]]|$)' >"$CI_WORK/wrap-spaced.txt"
        while IFS= read -r _wsl || [ -n "$_wsl" ]; do
            wrap_bad "$1" "${_wsl%%:*}" "a key takes no space before its colon: these rules read key: only"
        done <"$CI_WORK/wrap-spaced.txt"
    }
    wrap_role() {   # <stage, or a bare leg>: the ci/legs role whose image runs it, as ci_role_of in ci/common.sh
        case $1 in
            pure|lint|package) echo python ;;
            qt6) echo checker ;;
            floor) echo floor ;;
            322|340|344|40|42) echo "$1" ;;
            test-322|test-340|test-344|test-40|test-42) echo "${1#test-}" ;;
        esac
    }
    re_img='^[[:space:]]*image:[[:space:]]*\([^[:space:]#][^[:space:]#]*\)[[:space:]][[:space:]]*'
    re_img=$re_img'# ci/legs: \([a-z0-9][a-z0-9]*\)[[:space:]]*$'
    re_scr='^[[:space:]]+script:[[:space:]]+CI_IN_PLACE=1 sh ci/run-all\.sh --strict --only [a-z0-9-]+[[:space:]]*$'
    re_run='^[[:space:]]*(- )?run:[[:space:]]+exec sh ci/[a-z0-9-]+\.sh( --release| --only)*'
    re_run=$re_run' [$][{][{] matrix[.]stage [}][}][[:space:]]*$'
    re_uses='^[[:space:]]*(- )?uses:[[:space:]]+actions/(checkout|upload-artifact)@[0-9a-f]{40}([[:space:]]+#.*)?'
    re_uses=$re_uses'[[:space:]]*$'
    missing='missing: a tree with .gitlab-ci.yml or ci/hooks/ keeps both forge configs (to retire one, change'
    missing="$missing ci/lint.sh)"
    g=.gitlab-ci.yml nimg=0 nsl=0 nscr=0 nrun=0
    if [ ! -f "$g" ]; then
        wrap_bad "$g" '' "$missing"
    else
        : >"$CI_WORK/wrap-roles.txt" || exit 2
        : >"$CI_WORK/wrap-stages.txt" || exit 2
        wrap_lines "$g" '^[[:space:]]*image:' >"$CI_WORK/wrap-1.txt"
        while IFS= read -r l || [ -n "$l" ]; do
            nimg=$((nimg + 1))
            m=$(printf '%s\n' "${l#*:}" | sed -n "s|$re_img|\\1 \\2|p")
            if [ -z "$m" ]; then
                wrap_bad "$g" "${l%%:*}" "an image line must read: image: <ref>@sha256:<digest>  # ci/legs: <role>"
                echo - >>"$CI_WORK/wrap-roles.txt"
                continue
            fi
            printf '%s\n' "${m##* }" >>"$CI_WORK/wrap-roles.txt"
            want=$(sed -n "s/^${m##* }[[:space:]][[:space:]]*\([^[:space:]][^[:space:]]*\).*/\1/p" ci/legs 2>/dev/null |
                head -n 1)
            if [ -z "$want" ]; then
                wrap_bad "$g" "${l%%:*}" "role ${m##* } is not in ci/legs"
            elif [ "${m% *}" != "$want" ]; then
                wrap_bad "$g" "${l%%:*}" "${m% *} is not the ${m##* } image of ci/legs ($want)"
            fi
        done <"$CI_WORK/wrap-1.txt"
        wrap_lines "$g" 'script:' >"$CI_WORK/wrap-2.txt"
        while IFS= read -r l || [ -n "$l" ]; do   # also before_script, after_script and the like: each one fails
            if printf '%s\n' "${l#*:}" | grep -q -E "$re_scr"; then
                nsl=$((nsl + 1)) nscr=$((nscr + 1))
                st=$(printf '%s\n' "${l#*:}" | sed 's/[[:space:]]*$//; s/.* //')
                printf '%s %s\n' "${l%%:*}" "$st" >>"$CI_WORK/wrap-stages.txt"
                continue
            fi
            wrap_bad "$g" "${l%%:*}" \
                "a script must be one line: script: CI_IN_PLACE=1 sh ci/run-all.sh --strict --only <stage>"
            if printf '%s\n' "${l#*:}" | grep -q -E '^[[:space:]]*script:'; then   # a job's own script, paired
                nsl=$((nsl + 1))
                printf '%s -\n' "${l%%:*}" >>"$CI_WORK/wrap-stages.txt"
            fi
        done <"$CI_WORK/wrap-2.txt"
        [ "$nscr" -gt 0 ] || wrap_bad "$g" '' "no job runs CI_IN_PLACE=1 sh ci/run-all.sh --strict --only <stage>"
        if [ "$nimg" -ne "$nsl" ]; then
            wrap_bad "$g" '' "$nimg image lines for $nsl script lines: each job names its image"
        else
            paste -d ' ' "$CI_WORK/wrap-roles.txt" "$CI_WORK/wrap-stages.txt" >"$CI_WORK/wrap-pairs.txt"
            while read -r r ln st || [ -n "${r:-}" ]; do
                if [ "$r" = - ] || [ "$st" = - ]; then continue; fi
                w=$(wrap_role "$st")
                if [ -z "$w" ]; then
                    wrap_bad "$g" "$ln" "--only $st: no image of ci/legs runs that stage"
                elif [ "$w" != "$r" ]; then
                    wrap_bad "$g" "$ln" "--only $st runs in the $w image of ci/legs, but its job names the $r image"
                fi
            done <"$CI_WORK/wrap-pairs.txt"
        fi
        wrap_keys "$g" 'include|services|trigger|run|step|variables|parallel|allow_failure' \
            "a job runs its one script line only, and fails when it fails"
        wrap_lines "$g" '^[[:space:]]*(- +)?when[[:space:]]*:' |
            grep -v -E '^[0-9]+:[[:space:]]*(- +)?when[[:space:]]*:[[:space:]]+always[[:space:]]*(#.*)?$' \
            >"$CI_WORK/wrap-when.txt"
        msg='when: only "when: always" is allowed; a manual, delayed or on_failure job does not start with the'
        msg="$msg pipeline, and a manual one may fail without failing it"
        while IFS= read -r l || [ -n "$l" ]; do
            wrap_bad "$g" "${l%%:*}" "$msg"
        done <"$CI_WORK/wrap-when.txt"
        wrap_cont "$g"
        wrap_breaks "$g"
        wrap_spaced "$g"
    fi
    for y in .github/workflows/*.yml .github/workflows/*.yaml; do
        [ -f "$y" ] || continue
        wrap_lines "$y" 'run:' >"$CI_WORK/wrap-4.txt"
        while IFS= read -r l || [ -n "$l" ]; do
            if printf '%s\n' "${l#*:}" | grep -q -E "$re_run"; then
                nrun=$((nrun + 1))
            else
                wrap_bad "$y" "${l%%:*}" \
                    "a run step must be one line: run: exec sh ci/<script>.sh [--release] [--only] \${{ matrix.stage }}"
            fi
        done <"$CI_WORK/wrap-4.txt"
        wrap_lines "$y" 'uses:' >"$CI_WORK/wrap-5.txt"
        while IFS= read -r l || [ -n "$l" ]; do
            printf '%s\n' "${l#*:}" | grep -q -E "$re_uses" ||
                wrap_bad "$y" "${l%%:*}" "uses: names actions/checkout or actions/upload-artifact at a 40-hex commit"
        done <"$CI_WORK/wrap-5.txt"
        wrap_keys "$y" 'container|services|shell|env|defaults|working-directory|continue-on-error|include|exclude' \
            "the steps run the checked-out ci/ in the runner's plain shell, and fail when it fails"
        wrap_keys "$y" 'repository|ref|token|ssh-key|github-server-url' \
            "the checkout is the commit of this repository that the event names"
        wrap_cont "$y"
        wrap_breaks "$y"
        wrap_spaced "$y"
    done
    y=.github/workflows/ci.yml
    if [ ! -f "$y" ]; then
        wrap_bad "$y" '' "$missing"
    else
        have=$(sed -n 's/^[[:space:]]*stage:[[:space:]]*\[\(.*\)\][[:space:]]*$/\1/p' "$y" | tr -d ' ' | tr ',' ' ')
        want=$(sed -n "s/^CI_DEFAULT_STAGES='\(.*\)'\$/\1/p; s/^CI_RELEASE_STAGES='\(.*\)'\$/\1/p" ci/common.sh)
        [ "$have" = "$want" ] ||
            wrap_bad "$y" '' "its stage: lists are not CI_DEFAULT_STAGES and CI_RELEASE_STAGES of ci/common.sh"
    fi
    n=$(grep -c . "$ww")
    cat "$ww"
    ok=no; if [ "$n" = 0 ]; then ok=yes; fi
    lint_record wrappers "$n" '' "$ok"
    printf 'wrappers_gitlab_jobs=%s\nwrappers_github_runs=%s\n' "$nscr" "$nrun" >>"$res"
fi

if [ -n "$failed" ]; then
    printf 'failed=%s\n' "${failed# }" >>"$res"
    echo "lint.sh: FAILED:$failed"
    exit 1
fi
printf 'failed=none\n' >>"$res"
echo "lint.sh: every check passed"
exit 0
