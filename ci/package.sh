#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/package.sh - the package stage: the plugin zip, built from the last commit that changed fiberq/, then checked.
# Usage:
#   sh ci/package.sh build <run folder> <commit> <tree>    ci/run-all.sh runs this on the host for the package stage
#   sh ci/package.sh check                                 the part that runs in the python image of ci/legs
# build: "TZ=UTC git archive --format=zip <c> fiberq", where <c> is the last commit up to <commit> that changed
# fiberq/, into <run>/package/; a WARNING for each .qm catalog that is not committed or was last committed before
# its .ts; then the check in a container (ci/zipcheck.py: layout, modes, the file list and each file's content
# against git ls-tree, versions, CRCs; it writes the .sha256 and .contents.tsv files; then the .ts placeholder
# check of the Makefile on the extracted zip). After a pass, the zip goes to dist/ only from a run without --ref
# whose fiberq/ matches <c>, and only when dist/ holds none of the three names; nothing in dist/ is ever
# overwritten. Under --release, another build of that version in dist/ fails the stage; otherwise it is kept and
# reported.
# It reads set=, ref= and name_prefix= from <run>/run.txt, and writes <run>/stages/package/status once (result=
# last). In place (CI_IN_PLACE=1) the stage is skipped: host mode only.
# Exit: 0 the stage passed (or was skipped); 1 it failed; 2 usage or environment (no status written).
set -u
umask 022

usage() {
    echo "usage: sh ci/package.sh build <run folder> <commit> <tree>   (ci/run-all.sh runs it: --only package)"
    echo "       sh ci/package.sh check                                (in the container that build starts)"
}

pkg_check() {   # in the container: check $CI_IN/pkg/fiberq-<version>.zip, results into $CI_OUT
    if [ -z "${CI_DIR:-}" ] || [ -z "${CI_IN:-}" ] || [ -z "${CI_OUT:-}" ] || [ -z "${CI_WORK:-}" ] ||
        [ ! -d "$CI_OUT" ] || [ ! -d "$CI_WORK" ]; then
        echo "package.sh: 'check' runs in the container that ci/run-all.sh starts: sh ci/run-all.sh --only package" >&2
        exit 2
    fi
    _cp=$CI_IN/pkg
    for _cf in version ls-tree.txt Makefile info qm-warnings.txt; do
        if [ ! -f "$_cp/$_cf" ]; then echo "package.sh: pkg/$_cf is not in the input" >&2; exit 2; fi
    done
    _cv=$(sed -n '1p' "$_cp/version" | tr -d '[:space:]')
    case $_cv in ''|.*|*[!A-Za-z0-9._+-]*) echo "package.sh: bad version '$_cv' in pkg/version" >&2; exit 2 ;; esac
    _cz=$_cp/fiberq-$_cv.zip
    if [ ! -f "$_cz" ]; then echo "package.sh: pkg/fiberq-$_cv.zip is not in the input" >&2; exit 2; fi
    _cr=$CI_OUT/result.txt

    # 1. the zip itself: ci/zipcheck.py prints its counts as key=value lines and its problems on stderr
    python3 -I "$CI_DIR/zipcheck.py" check "$_cz" "$_cp/ls-tree.txt" "$_cv" "$CI_OUT" >"$CI_WORK/zipcheck.txt"
    _czr=$?
    { cat "$CI_WORK/zipcheck.txt"; printf 'zipcheck_rc=%s\n' "$_czr"; cat "$_cp/info"; } >"$_cr" || exit 2
    cat "$_cp/qm-warnings.txt" >"$CI_OUT/qm-warnings.txt" || exit 2

    # 2. the .ts placeholder check on the files that ship: the tested tree's Makefile block, never a copy in ci/
    python3 -I "$CI_DIR/zipcheck.py" extract "$_cz" "$CI_WORK/zip"
    _cxr=$?
    _cpf=$CI_WORK/i18n_placeholders.py _cpr='' _cpn=''
    sed -n '/^define I18N_PLACEHOLDER_PY$/,/^endef$/p' "$_cp/Makefile" | sed '1d;$d' >"$_cpf"
    if [ "$_cxr" != 0 ]; then
        _cpn="the zip could not be extracted"
    elif [ ! -s "$_cpf" ]; then
        _cpn="I18N_PLACEHOLDER_PY not found in the Makefile"
    elif grep -q '[$]' "$_cpf"; then
        _cpn="I18N_PLACEHOLDER_PY contains \$; ci/ cannot reproduce make's expansion"
    else
        ( cd "$CI_WORK/zip" && python3 -I "$_cpf" ) >"$CI_OUT/placeholders.txt" 2>&1
        _cpr=$?
        cat "$CI_OUT/placeholders.txt"
        if [ "$_cpr" = 0 ]; then
            _cpn=0
        else
            _cpn=$(sed -n 's/^\([0-9][0-9]*\) placeholder problem.*/\1/p' "$CI_OUT/placeholders.txt" | head -n 1)
            _cpn=${_cpn:-the check failed}
        fi
    fi
    printf 'extract_rc=%s\nplaceholders=%s\nplaceholders_rc=%s\n' "$_cxr" "$_cpn" "$_cpr" >>"$_cr" || exit 2

    _cfail=''
    [ "$_czr" = 0 ] || _cfail="$_cfail zipcheck"
    [ "$_cxr" = 0 ] || _cfail="$_cfail extract"
    [ "$_cpr" = 0 ] || _cfail="$_cfail placeholders"
    if [ -n "$_cfail" ]; then
        printf 'failed=%s\n' "${_cfail# }" >>"$_cr"
        echo "package.sh: FAILED:$_cfail"
        exit 1
    fi
    printf 'failed=none\n' >>"$_cr" || exit 2
    echo "package.sh: fiberq-$_cv.zip passed every check"
    exit 0
}

case ${1:-} in
    check)
        if [ $# -ne 1 ]; then usage >&2; exit 2; fi
        pkg_check ;;
    build)
        if [ $# -ne 4 ]; then usage >&2; exit 2; fi ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac
run=$2 commit_arg=$3 tree=$4
for a in "$run" "$commit_arg" "$tree"; do
    case $a in ''|-*) usage >&2; exit 2 ;; esac
done

case $0 in */*) CI_DIR=${0%/*} ;; *) CI_DIR=. ;; esac
# shellcheck source=common.sh
. "$CI_DIR/common.sh"

if [ ! -f "$run/run.txt" ]; then
    echo "package.sh: $run is not a run folder of ci/run-all.sh (no run.txt)" >&2
    exit 2
fi
run=$(cd "$run" && pwd -P) || exit 2
s=package dkey='' release=no
if [ -e "$run/stages/$s" ] || [ -e "$run/raw/$s.tar" ] || [ -e "$run/package" ] || [ -e "$run/input/pkg" ]; then
    echo "package.sh: $run already holds a package stage" >&2
    exit 2
fi

pkg_key() {   # <key>: print the value of the first <key>= line of run.txt
    sed -n "s/^$1=//p" "$run/run.txt" | head -n 1
}

if [ "${CI_IN_PLACE:-}" = 1 ]; then
    ci_init noengine
    ci_status "$s" skip "skipped: host mode only" || exit 2
    echo "package.sh: skipped: host mode only" >&2
    exit 0
fi

ci_init
prefix=$(pkg_key name_prefix)
case $prefix in
    ''|[!A-Za-z0-9]*|*[!A-Za-z0-9_.-]*)
        echo "package.sh: $run/run.txt needs name_prefix=, the prefix of the run's container names" >&2
        exit 2 ;;
esac
if [ "$(pkg_key set)" = release ]; then release=yes; fi
ref_given=$(pkg_key ref)
for x in input raw; do
    if [ ! -d "$run/$x" ]; then echo "package.sh: $run/$x is missing" >&2; exit 2; fi
done
ref=$(ci_image python) || exit 2
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
held=$run/input/$s.verdict

pkg_fail() {   # <reason>: the stage failed on the host; write its status and exit 1
    echo "package.sh: $1" >&2
    ci_status "$s" fail "$1" "image=$ref" "started=$started"
    exit 1
}

# ---- the zip, on the host
if [ "$CI_SHALLOW" = yes ]; then pkg_fail "needs full history (shallow clone): git fetch --unshallow --tags"; fi
commit=$(git -C "$CI_REPO" rev-parse --verify --quiet "$commit_arg^{commit}") || pkg_fail "$commit_arg is not a commit"
c=$(git -C "$CI_REPO" rev-list -1 "$commit" -- fiberq) || c=''
if [ -z "$c" ]; then pkg_fail "no fiberq/ in $commit"; fi
ver=$(git -C "$CI_REPO" show "$c:fiberq/metadata.txt" | sed -n 's/^version=//p' | head -n 1 | tr -d '[:space:]')
case $ver in
    '') pkg_fail "no version= in fiberq/metadata.txt at $c" ;;
    .*|*[!A-Za-z0-9._+-]*) pkg_fail "version=$ver in fiberq/metadata.txt at $c cannot name a file" ;;
esac
n=fiberq-$ver
mkdir "$run/package" || pkg_fail "cannot create $run/package"
zip=$run/package/$n.zip
TZ=UTC git -C "$CI_REPO" archive --format=zip -o "$zip" "$c" fiberq || pkg_fail "git archive of fiberq/ at $c failed"
echo "package.sh: built $zip from fiberq/ at $c (the last commit up to $commit that changed it)" >&2

p=$run/input/pkg
mkdir "$p" || pkg_fail "input build failed: mkdir input/pkg"
if ! ( set -C; cat "$zip" >"$p/$n.zip" ) || ! cmp -s "$zip" "$p/$n.zip"; then   # the checked zip is the one kept
    pkg_fail "input build failed: copy of $n.zip into input/pkg"
fi
( set -C; printf '%s\n' "$ver" >"$p/version" ) || pkg_fail "input build failed: input/pkg/version"
( set -C; git -C "$CI_REPO" ls-tree -r "$c" -- fiberq >"$p/ls-tree.txt" ) ||
    pkg_fail "input build failed: git ls-tree -r $c -- fiberq"
( set -C; ci_git show "$tree:Makefile" >"$p/Makefile" ) || pkg_fail "input build failed: git show $tree:Makefile"
( set -C; : >"$p/qm-warnings.txt" ) || pkg_fail "input build failed: input/pkg/qm-warnings.txt"

# .qm catalogs, judged by commit times so that every full clone gives the same answer (advisory, never a failure)
qmn=0
i18n=$(git -C "$CI_REPO" ls-tree --name-only "$c" fiberq/i18n/) || i18n=''
while IFS= read -r ts; do
    case $ts in *.ts) ;; *) continue ;; esac
    qm=${ts%.ts}.qm w=''
    if ! git -C "$CI_REPO" cat-file -e "$c:$qm" 2>/dev/null; then
        w="WARNING: $qm is not committed - that locale will NOT ship."
    else
        # log.showSignature=true would print gpg's lines before the time of a signed commit
        tt=$(git -C "$CI_REPO" -c log.showSignature=false log -1 --format=%ct "$c" -- "$ts") || tt=''
        qt=$(git -C "$CI_REPO" -c log.showSignature=false log -1 --format=%ct "$c" -- "$qm") || qt=''
        case $tt in ''|*[!0-9]*) tt=0 ;; esac
        case $qt in ''|*[!0-9]*) qt=0 ;; esac
        if [ "$tt" -gt "$qt" ]; then w="WARNING: $qm was last committed before $ts - run 'make i18n-compile'."; fi
    fi
    [ -n "$w" ] || continue
    echo "$w" >&2
    printf '%s\n' "$w" >>"$p/qm-warnings.txt" || pkg_fail "input build failed: input/pkg/qm-warnings.txt"
    qmn=$((qmn + 1))
done <<EOF
$i18n
EOF

# a dirty fiberq/ is not in the zip: say so, and never copy such a zip into dist/
zmt=yes
ft=$(ci_git rev-parse --verify --quiet "$tree:fiberq") || ft=''
fc=$(git -C "$CI_REPO" rev-parse --verify --quiet "$c:fiberq") || fc=''
if [ -z "$ft" ] || [ "$ft" != "$fc" ]; then
    zmt=no
    echo "WARNING: the zip holds committed fiberq/ only (commit $c)" >&2
fi
( set -C; printf 'fiberq_commit=%s\nzip_matches_tree=%s\nqm_warnings=%s\n' "$c" "$zmt" "$qmn" >"$p/info" ) ||
    pkg_fail "input build failed: input/pkg/info"
if [ -e "$run/input/pkg.tar" ]; then pkg_fail "input build failed: input/pkg.tar exists already"; fi
tar -cf "$run/input/pkg.tar" -C "$run/input" pkg || pkg_fail "input build failed: tar of input/pkg"

# ---- the check, in the python image
if ! ci_present "$ref"; then pkg_fail "missing image $ref; run: sh ci/pull.sh package"; fi
bytes=$(ci_bytes "$run/input/ci.tar" "$run/input/pkg.tar") ||
    pkg_fail "input build failed (an input part is missing or unreadable)"
ci_feed "$run/input/$s.feed-rc" "$run/input/ci.tar" "$run/input/pkg.tar" |
    ci_engine_run "$prefix-$s" "$ref" none "$(ci_timeout_of "$s")" "$bytes" package.sh check \
        >"$run/raw/$s.tar" 2>>"$run/$s.log"
erc=$?

# The verdict of the check (common.sh), held back: dist/ can still fail the stage, and the status file takes one
# block with result= last. In this subshell ci_status keeps result, reason and keys in input/package.verdict.
(
    ci_status() {   # <stage> <result> <reason> [<key=value>...]: held, one line each
        _hs=$2 _hw=$3
        shift 3
        ( set -C
          { printf '%s\n' "$_hs"
            printf '%s' "$_hw" | tr '\r\n' '  '; echo
            for _hk in "$@"; do printf '%s' "$_hk" | tr '\r\n' '  '; echo; done
          } >"$held" )
    }
    ci_verdict "$s" "$erc" "image=$ref" "started=$started"
)
pkg_final() {   # <result> <reason> [<dist>]: the stage's one status: the verdict's keys, then dist=, result last
    _fr=$1 _fw=$2 _fd=${3:-} _fi=0
    set --
    while IFS= read -r _fl || [ -n "$_fl" ]; do
        _fi=$((_fi + 1))
        if [ "$_fi" -gt 2 ]; then set -- "$@" "$_fl"; fi
    done <"$held"
    if [ -n "$_fd" ]; then set -- "$@" "dist=$_fd"; fi
    ci_status "$s" "$_fr" "$_fw" "$@"
}
vres='' vwhy=''
if [ -f "$held" ]; then
    { IFS= read -r vres; IFS= read -r vwhy; } <"$held"
fi
case $vres in
    pass) ;;
    skip|fail)
        pkg_final "$vres" "$vwhy"
        echo "package.sh: $vres: $vwhy (log: $run/$s.log)" >&2
        if [ "$vres" = fail ]; then exit 1; fi
        exit 0 ;;
    *) pkg_fail "no verdict for the check (engine status $erc; see $run/$s.log)" ;;
esac

# ---- after a pass: the run's copies, then dist/
out=$run/stages/$s/out
new=$(sed -n 's/^sha256=//p' "$out/result.txt" | head -n 1)
for x in sha256 contents.tsv; do
    if ! ( set -C; cat "$out/$n.$x" >"$run/package/$n.$x" ) || ! cmp -s "$out/$n.$x" "$run/package/$n.$x"; then
        pkg_final fail "cannot copy $n.$x into $run/package" "not copied (the copy into package/ failed)"
        exit 1
    fi
done

pkg_sha256() {   # <file>: print its sha256 with the host's tool (sha256sum, shasum or openssl), else unknown
    _sh=''
    if command -v sha256sum >/dev/null 2>&1; then
        _sh=$(sha256sum <"$1" 2>/dev/null)
    elif command -v shasum >/dev/null 2>&1; then
        _sh=$(shasum -a 256 <"$1" 2>/dev/null)
    elif command -v openssl >/dev/null 2>&1; then
        _sh=$(openssl dgst -sha256 -r <"$1" 2>/dev/null)
    fi
    _sh=${_sh%% *}
    case $_sh in *[!0-9a-f]*|'') _sh=unknown ;; esac
    printf '%s\n' "$_sh"
}

dd=$CI_REPO/dist
if [ -n "$ref_given" ]; then
    dist="not copied (--ref run)"
elif [ "$zmt" = no ]; then
    dist="not copied (fiberq/ differs from commit $c)"
else
    have='' same=yes
    for x in zip sha256 contents.tsv; do
        if [ -e "$dd/$n.$x" ] || [ -L "$dd/$n.$x" ]; then
            have="$have $n.$x"
            cmp -s "$dd/$n.$x" "$run/package/$n.$x" || same=no
        else
            same=no
        fi
    done
    if [ "$same" = yes ]; then
        dist="already holds this build"
    elif [ -n "$have" ]; then   # some name is taken: nothing is written, whatever it holds
        if [ ! -e "$dd/$n.zip" ] && [ ! -L "$dd/$n.zip" ]; then
            what="no $n.zip but${have} (this run: sha256 $new)"
            why="dist/ holds${have} but no $n.zip (this run: sha256 $new)"
        elif cmp -s "$dd/$n.zip" "$zip"; then
            what="this $n.zip but a different or missing $n.sha256 or $n.contents.tsv"
            why="dist/ holds this $n.zip but a different or missing $n.sha256 or $n.contents.tsv"
        else
            old=$(pkg_sha256 "$dd/$n.zip")
            what="a different $n.zip (sha256 $old, this run $new)"
            why="dist/$n.zip is a different build (sha256 $old, this run $new)"
        fi
        dist="kept: dist/ has $what"
        if [ "$release" = yes ]; then
            pkg_final fail "$why; move dist/$n.* aside by hand (the scripts never overwrite) and re-run" "$dist"
            echo "package.sh: $why; move dist/$n.* aside by hand (the scripts never overwrite) and re-run" >&2
            exit 1
        fi
        echo "WARNING: dist/ has $what; it was kept, this build is in $run/package/" >&2
    else
        if mkdir -p "$dd" &&
            ( set -C; cat "$zip" >"$dd/$n.zip" ) &&
            ( set -C; cat "$run/package/$n.sha256" >"$dd/$n.sha256" ) &&
            ( set -C; cat "$run/package/$n.contents.tsv" >"$dd/$n.contents.tsv" ) &&
            cmp -s "$zip" "$dd/$n.zip" && cmp -s "$run/package/$n.sha256" "$dd/$n.sha256" &&
            cmp -s "$run/package/$n.contents.tsv" "$dd/$n.contents.tsv"; then
            dist=copied
        else
            pkg_final fail "dist copy failed" "copy failed (what was written to dist/ is left as it is)"
            echo "package.sh: dist copy failed; what was written to $dd is left as it is" >&2
            exit 1
        fi
    fi
fi
pkg_final pass '' "$dist"
echo "package.sh: pass: $n.zip sha256 $new; dist: $dist" >&2
exit 0
