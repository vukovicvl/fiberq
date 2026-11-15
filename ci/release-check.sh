#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/release-check.sh - the release check: no credentials in fiberq/config.ini, the Generative AI heading in both
# READMEs, and the list of commits since the last tag that carry no Assisted-by: trailer.
# Usage:
#   sh ci/release-check.sh          the working tree: a snapshot in a new ci-results/<time>-release-check/
#   sh ci/release-check.sh --tree <id> --commit <id> --out <dir>
#                                   as ci/run-all.sh runs it (the snapshot's object folder exported)
#   In place, ci/run-all.sh runs it through ci/stage.sh: CI_IN_PLACE=1 sh ci/run-all.sh --only release-check
# Every check fails closed: a file that cannot be read fails it. Commits without the trailer are listed, they do not
# fail the check; a list that cannot be made does (a shallow clone, no tag before the commit). In place, without
# git, in a shallow clone or with no tag reachable, the list is skipped and result.txt says why.
# Results: result.txt (config_ini, genai_headings, assisted_by, since, commits, commits_without_trailer,
# merges_among_them, failed), release-check.txt (the findings) and commits-without-trailer.txt; with --out, and
# standalone, also exit-code and seconds.
# Exit: 0 the checks pass; 1 a check failed; 2 usage or environment.
set -u

usage() {
    echo "usage: sh ci/release-check.sh                                   (the working tree)"
    echo "       sh ci/release-check.sh --tree <id> --commit <id> --out <dir>   (as ci/run-all.sh runs it)"
    echo "in place: CI_IN_PLACE=1 sh ci/run-all.sh --only release-check"
}

tree_arg='' commit_arg='' out_arg=''
while [ $# -gt 0 ]; do
    case $1 in
        --tree|--commit|--out)
            if [ $# -lt 2 ]; then echo "release-check.sh: $1 needs a value" >&2; usage >&2; exit 2; fi
            case $2 in ''|-*) echo "release-check.sh: $1 needs a value, not '$2'" >&2; usage >&2; exit 2 ;; esac
            case $1 in
                --tree) tree_arg=$2 ;;
                --commit) commit_arg=$2 ;;
                *) out_arg=$2 ;;
            esac
            shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "release-check.sh: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
    esac
done
given=0
for a in "$tree_arg" "$commit_arg" "$out_arg"; do
    if [ -n "$a" ]; then given=$((given + 1)); fi
done
if [ "$given" != 0 ] && [ "$given" != 3 ]; then
    echo "release-check.sh: --tree, --commit and --out go together" >&2
    usage >&2
    exit 2
fi

case $0 in */*) CI_DIR=${0%/*} ;; *) CI_DIR=. ;; esac
# shellcheck source=common.sh
. "$CI_DIR/common.sh"

mode=standalone
if [ "${CI_IN_PLACE:-}" = 1 ]; then
    mode=inplace
    if [ "$given" != 0 ] || [ -z "${CI_SRC:-}" ] || [ -z "${CI_OUT:-}" ] || [ ! -d "$CI_OUT" ]; then
        echo "release-check.sh: in place, run stages through ci/run-all.sh:" \
            "CI_IN_PLACE=1 sh ci/run-all.sh --only release-check" >&2
        exit 2
    fi
    if [ ! -d "$CI_SRC" ]; then echo "release-check.sh: no tested tree at $CI_SRC" >&2; exit 2; fi
elif [ "$given" = 3 ]; then
    mode=run
fi
ci_init noengine
t0=$(date +%s) started=$(date -u +%Y-%m-%dT%H:%M:%SZ)

case $mode in
    inplace)
        out=$CI_OUT tree='' commit=${CI_COMMIT_SHA:-}
        if [ -z "$commit" ] && [ "$CI_HAVE_GIT" = yes ]; then
            commit=$(git -C "$CI_REPO" rev-parse --verify --quiet 'HEAD^{commit}') || commit=''
        fi ;;
    run)
        tree=$(ci_git rev-parse --verify --quiet "$tree_arg^{tree}") || {
            echo "release-check.sh: --tree $tree_arg is not a tree here (ci/run-all.sh exports the snapshot's" \
                "object folder in CI_SNAP_OBJECTS and CI_SNAP_ALT)" >&2
            exit 2
        }
        commit=$(git -C "$CI_REPO" rev-parse --verify --quiet "$commit_arg^{commit}") || {
            echo "release-check.sh: --commit $commit_arg is not a commit" >&2
            exit 2
        }
        out=$out_arg
        if [ ! -d "$out" ] && ! mkdir -p "$out"; then exit 2; fi ;;
    *)
        commit=$(git -C "$CI_REPO" rev-parse --verify --quiet 'HEAD^{commit}') || {
            echo "release-check.sh: no commit is checked out" >&2
            exit 2
        }
        run=$(ci_new_run release-check) || exit 2
        if ! mkdir "$run/input" "$run/stages" "$run/stages/release-check" "$run/stages/release-check/out"; then
            exit 2
        fi
        ci_snapshot "$run/input/snapshot"
        tree=$CI_SNAP_TREE
        out=$run/stages/release-check/out ;;
esac
for f in result.txt release-check.txt commits-without-trailer.txt exit-code seconds; do
    if [ -e "$out/$f" ]; then echo "release-check.sh: $out already holds $f" >&2; exit 2; fi
done
msgs=$out/release-check.txt
( set -C; : >"$msgs" ) || exit 2

rc_say() {   # <finding>: on stderr and in release-check.txt
    printf '%s\n' "$1" >&2
    printf '%s\n' "$1" >>"$msgs"
}

rc_read() {   # <path>: print the tested tree's file <path>; false if it is not there or cannot be read
    if [ "$mode" = inplace ]; then
        [ -f "$CI_SRC/$1" ] || return 1
        cat "$CI_SRC/$1"
    else
        ci_git cat-file blob "$tree:$1" 2>/dev/null
    fi
}

failed=''

# 1. fiberq/config.ini: the user and password keys stay empty; the message names the key, never the value
if ! cfg=$(rc_read fiberq/config.ini); then
    rc_say "fiberq/config.ini: not found in the tested tree"
    config_ini=missing failed="$failed config_ini"
else
    hits=$(printf '%s\n' "$cfg" | tr -d '\r' |
        grep -i -E '^[[:space:]]*(user|password)[[:space:]]*[=:][[:space:]]*[^[:space:]]')
    case $? in
        0)
            config_ini=fail failed="$failed config_ini"
            while IFS= read -r h; do
                rc_say "fiberq/config.ini: $(printf '%s\n' "$h" | sed 's/[=:].*/= <not empty>/')"
            done <<EOF
$hits
EOF
            ;;
        1) config_ini=ok ;;
        *) config_ini=error failed="$failed config_ini"; rc_say "fiberq/config.ini: grep failed" ;;
    esac
fi

# 2. the Generative AI heading, in both READMEs
nh=0
for f in README.md fiberq/README.md; do
    if ! txt=$(rc_read "$f"); then
        rc_say "$f: not found in the tested tree"
    elif printf '%s\n' "$txt" | grep -q -E '^## Use of Generative AI[[:space:]]*$'; then
        nh=$((nh + 1))
    else
        rc_say "$f: no '## Use of Generative AI' heading"
    fi
done
if [ "$nh" != 2 ]; then failed="$failed genai_headings"; fi

# 3. the commits since the last tag without an Assisted-by: trailer (listed; a list that cannot be made fails)
since='' ncommits='' nwo='' nmerge='' why='' revs=''
if [ "$mode" = inplace ]; then
    if [ "$CI_HAVE_GIT" != yes ]; then
        why="no git"
    elif [ "$CI_SHALLOW" = yes ]; then
        why="shallow clone"
    elif [ -z "$commit" ] || ! git -C "$CI_REPO" cat-file -e "$commit^{commit}" 2>/dev/null; then
        why="commit ${commit:-unknown} is not in this clone"
    fi
elif [ "$CI_SHALLOW" = yes ]; then
    why="needs full history (shallow clone): git fetch --unshallow --tags"
fi
if [ -z "$why" ]; then
    since=$(git -C "$CI_REPO" describe --tags --abbrev=0 "$commit^" 2>/dev/null) || since=''
    if [ -z "$since" ]; then
        why="no tag before $commit; fetch the tags: git fetch --tags"
        if [ "$mode" = inplace ]; then why="no tag reachable before $commit"; fi
    fi
fi
if [ -z "$why" ]; then
    revs=$(git -C "$CI_REPO" rev-list --parents "$since..$commit") || why="git rev-list $since..$commit failed"
fi
list=$out/commits-without-trailer.txt
( set -C; : >"$list" ) || exit 2
if [ -z "$why" ]; then
    ncommits=0 nwo=0 nmerge=0
    while read -r cc parents; do
        [ -n "$cc" ] || continue
        ncommits=$((ncommits + 1))
        # log.showSignature=true would put gpg's lines first, and the subject below is the first line
        if ! body=$(git -C "$CI_REPO" -c log.showSignature=false show -s --format=%B "$cc"); then
            why="git show $cc failed"
            break
        fi
        if printf '%s\n' "$body" | grep -q '^Assisted-by:'; then continue; fi
        nwo=$((nwo + 1)) kind=commit
        case $parents in *' '*) kind=merge nmerge=$((nmerge + 1)) ;; esac
        subject=$(printf '%s\n' "$body" | sed -n '1p')
        printf '%s %s %s\n' "$cc" "$kind" "$subject" >>"$list" || exit 2
    done <<EOF
$revs
EOF
fi
if [ -n "$why" ]; then
    ncommits='' nwo='' nmerge=''
    if [ "$mode" = inplace ]; then
        assisted="skipped ($why)"
        echo "release-check.sh: the Assisted-by: list is skipped: $why" >&2
    else
        assisted="failed ($why)" failed="$failed assisted_by"
        rc_say "Assisted-by: list: $why"
    fi
else
    assisted=listed
    echo "release-check.sh: $nwo of $ncommits commits since $since have no Assisted-by: trailer" \
        "($nmerge of them merges)" >&2
    sed 's/^/  /' "$list" >&2
fi

{
    printf 'config_ini=%s\n' "$config_ini"
    printf 'genai_headings=%s/2\n' "$nh"
    printf 'assisted_by=%s\n' "$assisted"
    printf 'since=%s\ncommits=%s\n' "$since" "$ncommits"
    printf 'commits_without_trailer=%s\nmerges_among_them=%s\n' "$nwo" "$nmerge"
    f=${failed# }
    printf 'failed=%s\n' "${f:-none}"
} >"$out/result.txt" || exit 2
rc=0
if [ -n "$failed" ]; then rc=1; fi
if [ "$mode" = inplace ]; then exit "$rc"; fi   # ci/stage.sh records exit-code and seconds

( set -C; printf '%s\n' "$rc" >"$out/exit-code" ) || exit 2
( set -C; printf '%s\n' "$(( $(date +%s) - t0 ))" >"$out/seconds" ) || exit 2
if [ "$mode" = standalone ]; then
    # The verdict of ci/common.sh, held back as ci/package.sh holds its own (ci_status redefined in a subshell), so
    # that a failure's bare "exit code 1" becomes the first finding, or "failed: <checks>" when there is none; the
    # status then takes one block, result= last.
    release=no held=$run/input/release-check.verdict
    ( ci_status() {
          _hs=$2 _hw=$3
          shift 3
          ( set -C
            { printf '%s\n' "$_hs"
              printf '%s' "$_hw" | tr '\r\n' '  '; echo
              for _hk in "$@"; do printf '%s' "$_hk" | tr '\r\n' '  '; echo; done
            } >"$held" )
      }
      ci_verdict release-check "$rc" "started=$started" )
    vres='' vwhy=''
    set --
    if [ -f "$held" ]; then
        { IFS= read -r vres; IFS= read -r vwhy; } <"$held"
        i=0
        while IFS= read -r line || [ -n "$line" ]; do
            i=$((i + 1))
            if [ "$i" -gt 2 ]; then set -- "$@" "$line"; fi
        done <"$held"
    fi
    if [ "$vres" = fail ] && [ "$vwhy" = 'exit code 1' ]; then
        first=$(sed -n 1p "$msgs")
        vwhy=${first:-failed: ${failed# }}
    fi
    case $vres in
        pass|skip|fail) ci_status release-check "$vres" "$vwhy" "$@" ;;
        *) ci_status release-check fail "no verdict (input/release-check.verdict was not written)" "started=$started" ;;
    esac
    echo "release-check.sh: $(ci_result_of release-check)${failed:+ (failed:$failed)}; records in $run" >&2
fi
exit "$rc"
