#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/run-all.sh - the one entry point of the pipeline: runs a set of stages, judges each, writes the run record.
# Usage:
#   sh ci/run-all.sh [--hook|--quick|--release] [--only <stage,...>] [--jobs N] [--ref <commit>] [--offline]
#   CI_IN_PLACE=1 sh ci/run-all.sh [--hook|--quick] [--only <stage,...>] [--offline]   here, with no containers
# Sets, in canonical order (the order of the record; the test legs run after the other stages, longest first:
# 42 340 344 40 322, in --jobs lanes; release-check runs last):
#   --hook      pure lint package
#   --quick     pure lint qt6 floor package
#   (none)      pure lint qt6 floor package test-322 test-344 test-42
#   --release   pure lint qt6 floor package test-322 test-340 test-344 test-40 test-42 release-check; host mode
#               only; it refuses a dirty working tree (also with --ref) and a shallow clone; a skip is a failure
# --only <stage,...>  exactly these stages, recorded in the order above, under the rules of the set flag given
#                     with it; a bare leg such as 42 means test-42; test-local (the suite on a local QGIS) runs in
#                     place only
# --ref <commit>      test that commit's tree; the scripts always come from the working tree
# --jobs N            run the test legs in N lanes (default 1; ignored in place)
# --offline           never fetch pinned tools; a stage whose tools are not cached fails
# Each stage runs in a fresh container of its ci/legs image (CI_ENGINE: docker or podman) with no network. This
# script never pulls (sh ci/pull.sh does); pinned tools that are not cached yet are fetched first (sh ci/deps.sh).
# The containers get ci/ from the snapshot taken at the start; deps.sh, package.sh and release-check.sh run on the
# host from the working tree, so a step whose ci/ files changed since the snapshot fails instead of starting.
# In place (CI_IN_PLACE=1) package is skipped, and qt6 needs pyqt5_to_pyqt6.py, floor the floor's QGIS and each
# test leg its own QGIS (test-322 3.22, test-340 3.40, test-344 3.44, test-40 4.0, test-42 4.2), else each of them
# is skipped; test-local runs the suite on whatever QGIS is here.
# The record goes to a new ci-results/<UTC time>-<commit12>[-N]/ (CI_RESULTS): run.txt, <stage>.log,
# stages/<stage>/{status,out/}, and summary.md and record.txt when the summary stage passed. The scripts delete
# nothing and never overwrite a file outside the run folder (dist/ and .ci-cache/ only get new files). In place
# the tests run in this checkout and environment: pytest-qgis writes the gitignored .qgis-settings/ there and
# headless QGIS may write symbology-style.db; but each stage runs with its own empty HOME, stages/<stage>/work/home,
# as each container runs with HOME=/tmp, so the floor stage's QGIS profile goes there and the caller's dotfiles and
# user site-packages are not seen.
# Exit: 0 every stage passed (a skip too, except under --release) and the summary passed; 1 a stage failed or has
#       no verdict, or the summary failed; 2 usage, environment, input or a refusal; 130 interrupted.
set -u
case $0 in */*) CI_DIR=${0%/*} ;; *) CI_DIR=. ;; esac
# shellcheck source=common.sh
. "$CI_DIR/common.sh"

ra_usage() {
    echo "usage: sh ci/run-all.sh [--hook|--quick|--release] [--only <stage,...>] [--jobs N] [--ref <commit>]"
    echo "                        [--offline]"
    echo "       CI_IN_PLACE=1 sh ci/run-all.sh [--hook|--quick] [--only <stage,...>] [--offline]   (no containers)"
    echo "sets: --hook: $CI_HOOK_STAGES"
    echo "      --quick: $CI_QUICK_STAGES"
    echo "      default: $CI_DEFAULT_STAGES"
    echo "      --release: $CI_RELEASE_STAGES"
    echo "stages: $CI_ALL_STAGES"
    echo "        (a bare leg such as 42 means test-42; test-local runs in place only)"
    echo "in place: each stage runs with its own HOME (stages/<stage>/work/home); package is skipped, and so are"
    echo "          qt6 without pyqt5_to_pyqt6.py, floor off the floor's QGIS and a test leg off its own QGIS"
}

ra_bad() {   # <message>: a usage error; exit 2
    echo "run-all.sh: $1" >&2
    ra_usage >&2
    exit 2
}

# ---- the command line
set_flag='' only_arg='' jobs=1 jobs_given=no ref_given='' ref_on=no offline=no
while [ $# -gt 0 ]; do
    case $1 in
        -h|--help) ra_usage; exit 0 ;;
        --hook|--quick|--release)
            if [ -n "$set_flag" ]; then ra_bad "give one of --hook, --quick and --release, not --$set_flag and $1"; fi
            set_flag=${1#--}
            shift ;;
        --offline) offline=yes; shift ;;
        --ref)
            if [ "$ref_on" = yes ]; then ra_bad "--ref is given twice"; fi
            if [ $# -lt 2 ]; then ra_bad "--ref needs a commit"; fi
            case $2 in ''|-*) ra_bad "--ref needs a commit, not '$2'" ;; esac
            ref_given=$2 ref_on=yes
            shift 2 ;;
        --only)
            if [ -n "$only_arg" ]; then ra_bad "--only is given twice"; fi
            if [ $# -lt 2 ]; then ra_bad "--only needs stage names, separated by commas"; fi
            case $2 in ''|-*) ra_bad "--only needs stage names, separated by commas, not '$2'" ;; esac
            only_arg=$2
            shift 2 ;;
        --jobs)
            if [ "$jobs_given" = yes ]; then ra_bad "--jobs is given twice"; fi
            if [ $# -lt 2 ] || ! ci_whole "$2"; then ra_bad "--jobs needs a whole number >= 1, not '${2:-}'"; fi
            jobs=$2 jobs_given=yes
            shift 2 ;;
        *) ra_bad "unknown argument '$1'" ;;
    esac
done
set_name=${set_flag:-default}
release=no
if [ "$set_name" = release ]; then release=yes; fi
mode=host
if [ "${CI_IN_PLACE:-}" = 1 ]; then mode=in-place; fi

if [ -n "$only_arg" ]; then
    case $only_arg in
        *[!A-Za-z0-9,-]*) ra_bad "--only takes stage names separated by commas, not '$only_arg'" ;;
    esac
    picked=' '
    for w in $(printf '%s\n' "$only_arg" | tr ',' ' '); do
        st=$(ci_stage_name "$w") || exit 2
        picked="$picked$st "
    done
    stages=''
    for st in $CI_ALL_STAGES; do
        case $picked in *" $st "*) stages="$stages $st" ;; esac
    done
    stages=${stages# }
    if [ -z "$stages" ]; then ra_bad "--only names no stage"; fi
    only=$(printf '%s\n' "$stages" | tr ' ' ',')
else
    stages=$(ci_set_stages "$set_name") || exit 2
    only=''
fi

# ---- refusals that need nothing but the command line
if [ "$mode" = in-place ]; then
    if [ "$release" = yes ]; then
        echo "run-all.sh: --release runs in host mode only (the release record is made in containers);" \
            "unset CI_IN_PLACE" >&2
        exit 2
    fi
    if [ "$ref_on" = yes ]; then
        echo "run-all.sh: --ref runs in host mode only; in place the checkout is tested as it is" >&2
        exit 2
    fi
else
    case " $stages " in
        *" test-local "*)
            echo "run-all.sh: test-local runs in place only: CI_IN_PLACE=1 sh ci/run-all.sh --only test-local" >&2
            exit 2 ;;
    esac
fi

# ---- the environment: engine, git, CI_TIMEOUT; then the tested commit and the images, all before the run folder
if [ "$mode" = in-place ]; then
    ci_init noengine   # in place ci_init checks no engine and takes git as optional anyway
    export CI_DIR      # ci/stage.sh and the stage scripts read it
else
    ci_init
fi
if [ "$release" = yes ]; then
    ci_refuse_shallow "--release needs full history (shallow clone): git fetch --unshallow --tags"
    # a dirty tree is refused here, before the run folder exists; this git status writes nothing to .git. The
    # snapshot comparison after ci_new_run stays, for what status cannot see (assume-unchanged, skip-worktree)
    dirt=$(git -C "$CI_REPO" --no-optional-locks status --porcelain --untracked-files=all 2>/dev/null)
    if [ -n "$dirt" ]; then
        dirt_n=$(printf '%s\n' "$dirt" | grep -c .) dirt_more=''
        if [ "$dirt_n" -gt 1 ]; then dirt_more=" and $((dirt_n - 1)) more"; fi
        echo "run-all.sh: refusing --release: the working tree is dirty (git status:" \
            "'$(printf '%s\n' "$dirt" | sed -n 1p)'$dirt_more); commit your changes first" >&2
        exit 2
    fi
fi
commit='' tree='' dirty='' head0=''
if [ "$CI_HAVE_GIT" = yes ]; then   # HEAD, read once: the run's commit (without --ref) and runner_dirty's
    head0=$(git -C "$CI_REPO" rev-parse --verify --quiet 'HEAD^{commit}') || head0=''
fi
if [ "$ref_on" = yes ]; then
    commit=$(git -C "$CI_REPO" rev-parse --verify --quiet "$ref_given^{commit}") || {
        echo "run-all.sh: --ref $ref_given is not a commit" >&2
        exit 2
    }
    tree=$(git -C "$CI_REPO" rev-parse --verify --quiet "$commit^{tree}") || exit 2
    dirty=no
elif [ "$mode" = host ]; then
    commit=$head0
    if [ -z "$commit" ]; then
        echo "run-all.sh: no commit is checked out" >&2
        exit 2
    fi
else
    commit=${CI_COMMIT_SHA:-}
    if [ -z "$commit" ]; then commit=$head0; fi
    case $commit in
        '') commit=unknown ;;
        *[!0-9a-f]*)
            echo "run-all.sh: CI_COMMIT_SHA must be a commit id (lowercase hex), not '$commit'" >&2
            exit 2 ;;
    esac
fi

ra_image() {   # <role>: the image ref this run uses for <role>, as recorded at its start
    printf '%s' "$images" | sed -n "s/^$1 //p"
}
ra_set_of() {   # <stage>: the pinned tool set <stage> uses, test or lint (the mapping of ci/deps.sh); else nothing
    case $1 in
        pure|test-*) echo test ;;
        lint) echo lint ;;
    esac
}
ra_key_of() {   # <stage>: the deps cache key of <stage>, as recorded at the start of the run; else nothing
    printf '%s' "$keys" | sed -n "s/^$1 //p"
}

images='' roles='' keys='' pyref=''
if [ "$mode" = host ]; then
    for st in $stages summary; do
        r=$(ci_role_of "$st") || exit 2
        if [ -z "$r" ]; then continue; fi
        case " $roles " in *" $r "*) ;; *) roles="$roles $r" ;; esac
    done
    roles=${roles# }
    for r in $roles; do
        ref=$(ci_image "$r") || exit 2
        images="$images$r $ref
"
    done
    pyref=$(ra_image python)
fi
for st in $stages; do
    tset=$(ra_set_of "$st")
    if [ -z "$tset" ]; then continue; fi
    if [ "$mode" = host ]; then
        k=$(ci_deps_key "$tset" "$(ra_image "$(ci_role_of "$st")")") || exit 2
    else
        k=$(ci_deps_key "$tset") || k=''   # no python3 here: the stage fails, it cannot run without its tools
    fi
    if [ -n "$k" ]; then keys="$keys$st $k
"; fi
done
if [ "$mode" = in-place ] && [ "$jobs_given" = yes ]; then
    echo "run-all.sh: WARNING: --jobs is ignored in place; the stages run one after another" >&2
    jobs=1
fi

# ---- the run folder, the snapshot of the working tree, the inputs
c12=$(printf '%s\n' "$commit" | sed 's/^\(.\{12\}\).*/\1/')
run=$(ci_new_run "$c12") || exit 2
ra_run=$run   # the run folder (run itself points at <run>/deps while an in-place deps verdict is written)
run_id=${run##*/}
ci_name_prefix=fiberq-ci-$run_id-$$
if ! mkdir "$run/input" "$run/stages"; then exit 2; fi
if [ "$mode" = host ] && ! mkdir "$run/raw"; then exit 2; fi

warnings=''
ra_warn() {   # <text>: a WARNING, now on stderr and again at the end of the run
    echo "run-all.sh: WARNING: $1" >&2
    warnings="${warnings}WARNING: $1
"
}

wt='' runner_dirty=unknown
if [ "$mode" = host ] || [ "$CI_HAVE_GIT" = yes ]; then
    ci_snapshot "$run/input/snapshot"
    wt=$CI_SNAP_TREE
    runner_dirty=$(ci_runner_dirty "$head0")
    export CI_SNAP_OBJECTS CI_SNAP_ALT   # package.sh and release-check.sh read the snapshot's objects
fi
if [ "$release" = yes ] && [ "$runner_dirty" != no ]; then
    htree=$(git -C "$CI_REPO" rev-parse --verify --quiet "$head0^{tree}") || htree=none
    ( set -C; printf 'run=%s\nset=release\nrefused=the working tree is dirty (snapshot %s, HEAD^{tree} %s)\n' \
        "$run_id" "$wt" "$htree" >"$run/run.txt" )
    echo "run-all.sh: refusing --release: the working tree is dirty (snapshot $wt, HEAD's tree $htree);" \
        "commit your changes first. This run folder holds only the snapshot: $run" >&2
    exit 2
fi
if [ "$ref_on" = no ]; then
    if [ -n "$wt" ]; then tree=$wt; else tree=unknown; fi
    dirty=$runner_dirty
fi
runner_ci_tree=unknown
if [ -n "$wt" ]; then
    if ! ci_git cat-file -e "$wt:ci" 2>/dev/null; then
        echo "run-all.sh: no ci/ in the working tree" >&2
        exit 2
    fi
    runner_ci_tree=$(ci_git rev-parse --verify --quiet "$wt:ci") || runner_ci_tree=unknown
fi

ra_tree_of() {   # <path>: the tree id of <path> in the tested tree; absent, or unknown without a tree
    if [ "$tree" = unknown ]; then echo unknown; return 0; fi
    ci_git rev-parse --verify --quiet "$tree:$1" || echo absent
}
ra_ci_same() {   # <file>...: (host) true when each ci/<file> in the working tree is still the blob of the snapshot
    for _csf in "$@"; do
        _csa=$(git -C "$CI_REPO" hash-object -- "ci/$_csf" 2>/dev/null) || return 1
        _csb=$(ci_git rev-parse --verify --quiet "$wt:ci/$_csf") || return 1
        [ "$_csa" = "$_csb" ] || return 1
    done
    return 0
}

if [ "$mode" = host ]; then
    if ! ci_git archive --format=tar -o "$run/input/ci.tar" "$wt" ci; then
        echo "run-all.sh: cannot build ci.tar" >&2
        exit 2
    fi
    need_src=no
    for st in $stages; do
        case $st in pure|lint|qt6|floor|test-*) need_src=yes ;; esac
    done
    if [ "$need_src" = yes ]; then
        if ! ci_git archive --format=tar --prefix=src/ -o "$run/input/src.tar" "$tree"; then
            echo "run-all.sh: cannot build the input: git archive of the tested tree failed" >&2
            exit 2
        fi
        n=$(ci_bytes "$run/input/src.tar") || n=0
        if [ "$n" -gt 104857600 ]; then
            ra_warn "the tested tree is $n bytes as a tar (input/src.tar); every container stage reads all of it"
        fi
    fi
fi

# ---- run.txt: the facts of the run, before the first stage
if [ "$mode" = host ]; then
    engine_v=$(ci_engine --version 2>/dev/null | head -n 1) || engine_v=''
    user=1000:1000
    shallow=$CI_SHALLOW
else
    engine_v='none (in place)'
    user=$(id -u):$(id -g)
    shallow=unknown
    if [ "$CI_HAVE_GIT" = yes ]; then shallow=$CI_SHALLOW; fi
fi
git_v=none
if command -v git >/dev/null 2>&1; then git_v=$(git --version 2>/dev/null) || git_v=unknown; fi
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if ! ( set -C
    {
        printf 'run=%s\nrun_dir=%s\nset=%s\nonly=%s\nstages=%s\nmode=%s\n' \
            "$run_id" "$run" "$set_name" "$only" "$stages" "$mode"
        printf 'engine=%s\ngit=%s\nhost=%s\n' "${engine_v:-unknown}" "$git_v" "$(uname -sm)"
        printf 'ref=%s\ncommit=%s\nroot_tree=%s\n' "$ref_given" "$commit" "$tree"
        printf 'fiberq_tree=%s\ntests_tree=%s\nci_tree=%s\nrunner_ci_tree=%s\n' \
            "$(ra_tree_of fiberq)" "$(ra_tree_of tests)" "$(ra_tree_of ci)" "$runner_ci_tree"
        printf 'dirty=%s\nrunner_dirty=%s\nshallow=%s\n' "$dirty" "$runner_dirty" "$shallow"
        printf 'name_prefix=%s\nstarted=%s\nuser=%s\njobs=%s\noffline=%s\n' \
            "$ci_name_prefix" "$started" "$user" "$jobs" "$offline"
        if [ "$mode" = in-place ]; then
            py=$(python3 -c 'import platform; print(platform.python_version())' 2>/dev/null) || py=none
            printf 'python=%s\n' "$py"
        fi
        for r in $roles; do
            o=no
            if [ -n "$(ci_override "$r")" ]; then o=yes; fi
            printf 'image.%s=%s\nimage_override.%s=%s\n' "$r" "$(ra_image "$r")" "$r" "$o"
        done
        for st in $stages summary; do printf 'timeout.%s=%s\n' "$st" "$(ci_timeout_of "$st")"; done
        for st in $stages; do
            k=$(ra_key_of "$st")
            if [ -n "$k" ]; then printf 'deps.%s=%s\n' "$st" "$k"; fi
        done
    } >"$run/run.txt" ); then
    echo "run-all.sh: cannot write $run/run.txt" >&2
    exit 2
fi

# ---- from here on every stage, deps fetch and the summary is a background job, so a signal stops the run at once
lane_pids=''
ci_abort() {
    trap - INT TERM HUP
    trap '' PIPE   # a reader that went away (sh ci/run-all.sh 2>&1 | head) must not end the abort half-way
    for p in $lane_pids; do kill -TERM "$p" 2>/dev/null; done
    if [ "$mode" = host ]; then
        # twice: ps lists running containers only, and the engine client of a lane that just died may have
        # created its container without starting it yet
        for ab in 1 2; do
            ci_engine ps -q --filter "name=^$ci_name_prefix-" 2>/dev/null |
                while IFS= read -r id; do ci_engine kill "$id" >/dev/null 2>&1; done
            if [ "$ab" = 1 ]; then sleep 2; fi
        done
    fi
    printf 'interrupted=yes\n' >>"$ra_run/run.txt"
    echo "run-all.sh: interrupted; partial results in $ra_run" >&2
    exit 130
}
trap ci_abort INT TERM HUP PIPE

ra_say() {   # <text>: a progress line on stderr
    echo "[$(date +%H:%M:%S)] $*" >&2
}
ra_utc() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}
ra_reason() {   # <stage>: the reason of its verdict (the last reason= line of its status)
    sed -n 's/^reason=//p' "$run/stages/$1/status" 2>/dev/null | tail -n 1
}
ra_done() {   # <stage> <start, in s since the epoch>: the progress line with the stage's verdict
    _dnr=$(ci_result_of "$1") _dnw=$(ra_reason "$1")
    _dnf=$run/stages/release-check/out/release-check.txt
    if [ "$1" = release-check ] && [ "$_dnr" != pass ] && [ -s "$_dnf" ]; then
        if [ "$_dnw" = "$(sed -n 1p "$_dnf")" ]; then   # the reason is the first finding (ra_rc_verdict)
            _dnm=$(sed 1d "$_dnf" | tr '\n' ';' | sed 's/;$//; s/;/; /g')
            _dnw="$_dnw${_dnm:+ (also: $_dnm)}"
        else
            _dnw="$_dnw ($(tr '\n' ';' <"$_dnf" | sed 's/;$//; s/;/; /g'))"
        fi
    fi
    ra_say "$1 $_dnr ($(( $(date +%s) - $2 )) s)${_dnw:+ $_dnw}"
}
ra_rc_verdict() {   # <stage status> [<key=value>...]: release-check's verdict, held back as package.sh holds its own
    # ci_verdict (ci/common.sh) runs in a subshell whose ci_status keeps result, reason and keys, one line each, in
    # input/release-check.verdict; a failure's bare "exit code 1" then becomes the first line of
    # out/release-check.txt, or "failed: <failed= of result.txt>" when that is empty; one status block, result= last
    _rvh=$run/input/release-check.verdict _rvo=$run/stages/release-check/out _rve=$1
    ( ci_status() {
          _rhs=$2 _rhw=$3
          shift 3
          ( set -C
            { printf '%s\n' "$_rhs"
              printf '%s' "$_rhw" | tr '\r\n' '  '; echo
              for _rhk in "$@"; do printf '%s' "$_rhk" | tr '\r\n' '  '; echo; done
            } >"$_rvh" )
      }
      ci_verdict release-check "$@" )
    _rvr='' _rvw='' _rvi=0
    if [ -f "$_rvh" ]; then { IFS= read -r _rvr; IFS= read -r _rvw; } <"$_rvh"; fi
    case $_rvr in
        pass|skip|fail) ;;
        *)
            shift
            ci_status release-check fail "no verdict (input/release-check.verdict was not written)" \
                "engine_rc=$_rve" code= seconds= "$@"
            return 0 ;;
    esac
    if [ "$_rvr" = fail ] && [ "$_rvw" = 'exit code 1' ]; then
        _rvf=$(sed -n 1p "$_rvo/release-check.txt" 2>/dev/null)
        if [ -z "$_rvf" ]; then
            _rvf=$(sed -n 's/^failed=//p' "$_rvo/result.txt" 2>/dev/null | head -n 1)
            _rvf=${_rvf:+failed: $_rvf}
        fi
        _rvw=${_rvf:-$_rvw}
    fi
    set --
    while IFS= read -r _rvl || [ -n "$_rvl" ]; do
        _rvi=$((_rvi + 1))
        if [ "$_rvi" -gt 2 ]; then set -- "$@" "$_rvl"; fi
    done <"$_rvh"
    ci_status release-check "$_rvr" "$_rvw" "$@"
}
ra_freeze() {   # <stage> <deps cache folder>: keep the freeze of the stage's pinned tools in its record
    if [ -f "$2/freeze.txt" ] && mkdir -p "$run/stages/$1"; then
        ( set -C; cat "$2/freeze.txt" >"$run/stages/$1/deps-freeze.txt" ) 2>/dev/null
    fi
}

ra_box() {   # <stage>: (host) one container stage, input to verdict; runs as the stage's job
    s=$1 dkey='' _obd='' _obsrc=$run/input/src.tar _obarg=''
    case $s in
        pure) _obsc=test.sh _obarg=pure ;;
        lint) _obsc=lint.sh ;;
        qt6) _obsc=qt6-check.sh ;;
        floor) _obsc=floor-check.sh ;;
        test-*) _obsc=test.sh _obarg=${s#test-} ;;
        summary) _obsc=report.py _obarg=summary _obsrc='' ;;
        *) ci_status "$s" fail "run-all.sh cannot run stage $s in a container"; return 0 ;;
    esac
    _obrole=$(ci_role_of "$s") || return 0
    _obref=$(ra_image "$_obrole") _obt=$(ci_timeout_of "$s") _obst=$(ra_utc)
    ra_say "$s started ($_obref)"
    if ! ci_present "$_obref"; then
        _obres=fail _obhint=$s
        if [ "$s" = summary ]; then _obhint=pure; fi
        _obw="missing image $_obref; run: sh ci/pull.sh $_obhint"
        if [ "$_obrole" = checker ]; then
            _obw="skipped: needs ghcr.io (missing image $_obref; run: sh ci/pull.sh qt6)" _obres=skip
            if [ "$release" = yes ]; then _obres=fail; fi
        fi
        printf 'run-all.sh: %s\n' "$_obw" >>"$run/$s.log"
        ci_status "$s" "$_obres" "$_obw" engine_rc= code= seconds= "image=$_obref" "started=$_obst"
        return 0
    fi
    if [ -n "$(ra_set_of "$s")" ]; then
        dkey=$(ra_key_of "$s")
        if [ -n "$dkey" ]; then _obd=$(ci_deps_find "$dkey") || _obd=''; fi
        if [ -z "$_obd" ]; then
            _obw="pinned tools not cached; run: sh ci/deps.sh $s"
            printf 'run-all.sh: %s\n' "$_obw" >>"$run/$s.log"
            ci_status "$s" fail "$_obw" engine_rc= code= seconds= "image=$_obref" "started=$_obst" "deps=$dkey"
            return 0
        fi
        ra_freeze "$s" "$_obd"
    fi
    set -- ${_obsrc:+"$_obsrc"} "$run/input/ci.tar" ${_obd:+"$_obd/deps.tar"}
    if [ "$s" = summary ]; then set -- "$@" "$run/input/summary.tar"; fi
    if ! _obb=$(ci_bytes "$@"); then
        ci_status "$s" fail "input build failed (an input part is missing or unreadable)" engine_rc= code= seconds= \
            "image=$_obref" "started=$_obst" ${dkey:+"deps=$dkey"}
        return 0
    fi
    ci_feed "$run/input/$s.feed-rc" "$@" |
        ci_engine_run "$ci_name_prefix-$s" "$_obref" none "$_obt" "$_obb" "$_obsc" ${_obarg:+"$_obarg"} \
            >"$run/raw/$s.tar" 2>>"$run/$s.log"
    _obe=$?
    ci_verdict "$s" "$_obe" "image=$_obref" "started=$_obst" ${dkey:+"deps=$dkey"}
}

ra_local() {   # <stage>: (in place) prepare, run ci/stage.sh as a job of this shell, wait, judge
    s=$1 dkey='' _ipd='' _iparg='' _ip0=$(date +%s) _ipst=$(ra_utc)
    case $s in
        pure) _ipsc=test.sh _iparg=pure ;;
        lint) _ipsc=lint.sh ;;
        qt6) _ipsc=qt6-check.sh ;;
        floor) _ipsc=floor-check.sh ;;
        test-*) _ipsc=test.sh _iparg=${s#test-} ;;
        release-check) _ipsc='release-check.sh' ;;
        summary) _ipsc=report.py _iparg=summary ;;
        *) ci_status "$s" fail "run-all.sh cannot run stage $s in place"; ra_done "$s" "$_ip0"; return 0 ;;
    esac
    ra_say "$s started (in place)"
    if [ -n "$(ra_set_of "$s")" ]; then
        dkey=$(ra_key_of "$s")
        if [ -n "$dkey" ]; then _ipd=$(ci_deps_find "$dkey") || _ipd=''; fi
        if [ -z "$_ipd" ]; then
            if [ -z "$dkey" ]; then
                _ipw="pinned tools not installed: no in-place cache key (python3 is needed)"
            elif [ "$offline" = yes ]; then
                _ipw="pinned tools not cached; run without --offline: CI_IN_PLACE=1 sh ci/run-all.sh --only $s"
            else
                _ipw="pinned tools not installed (see $run/deps/)"
            fi
            printf 'run-all.sh: %s\n' "$_ipw" >>"$run/$s.log"
            ci_status "$s" fail "$_ipw" engine_rc= code= seconds= "image=in place" "started=$_ipst" \
                ${dkey:+"deps=$dkey"}
            ra_done "$s" "$_ip0"
            return 0
        fi
        ra_freeze "$s" "$_ipd"
    fi
    _ipwd=$run/stages/$s/work
    if ! mkdir -p "$run/stages/$s" || ! mkdir "$run/stages/$s/out" "$_ipwd" "$_ipwd/home"; then
        ci_status "$s" fail "input build failed: cannot create stages/$s/out, work and work/home" engine_rc= code= \
            seconds= "image=in place" "started=$_ipst"
        ra_done "$s" "$_ip0"
        return 0
    fi
    # the stage's own HOME, as each container runs with HOME=/tmp: what it writes under ~ stays in the run folder
    HOME=$_ipwd/home CI_SRC=$CI_REPO CI_IN=$run CI_OUT=$run/stages/$s/out CI_WORK=$_ipwd CI_STAGE=$s \
        CI_TIMEOUT=$(ci_timeout_of "$s") CI_COMMIT_SHA=$commit CI_IMAGE_REF='' CI_DEPS=${_ipd:+$_ipd/deps} \
        sh "$CI_DIR/stage.sh" "$_ipsc" ${_iparg:+"$_iparg"} >>"$run/$s.log" 2>&1 &
    lane_pids=$!
    wait "$lane_pids"
    _ipe=$?
    lane_pids=''
    if [ "$s" = release-check ]; then
        ra_rc_verdict "$_ipe" "image=in place" "started=$_ipst"
    else
        ( case $s in   # a test leg skipped off its own QGIS (ci/test.sh) leaves no junit.xml
              test-322|test-340|test-344|test-40|test-42)
                  if grep -q '^skipped=' "$run/stages/$s/out/result.txt" 2>/dev/null; then ci_required() { :; }; fi ;;
          esac
          ci_verdict "$s" "$_ipe" "image=in place" "started=$_ipst" ${dkey:+"deps=$dkey"} )
    fi
    ra_done "$s" "$_ip0"
}

ra_run1() {   # <stage>: one stage as one background job of this shell, waited for, then its progress line
    _r1s=$1 _r1t=$(date +%s)
    if [ "$mode" = in-place ] && [ "$_r1s" != package ]; then
        ra_local "$_r1s"
        return 0
    fi
    case $_r1s in
        package)   # package.sh writes the stage's status itself (and skips it in place)
            if [ "$mode" = host ]; then ra_say "package started ($pyref)"; else ra_say "package started (in place)"; fi
            if [ "$mode" = host ] && ! ra_ci_same package.sh common.sh legs; then
                _r1w="ci/ changed during the run: package.sh, common.sh or legs differs from the snapshot"
                _r1w="$_r1w (runner_ci_tree $runner_ci_tree); start the run again"
                printf 'run-all.sh: %s\n' "$_r1w" >>"$run/package.log"
                ci_status package fail "$_r1w" engine_rc= code= seconds= "image=$pyref" "started=$(ra_utc)"
            else
                sh "$CI_DIR/package.sh" build "$run" "$commit" "$tree" >>"$run/package.log" 2>&1 &
                lane_pids=$!
                wait "$lane_pids"
                lane_pids=''
            fi ;;
        release-check)   # on the host, with the snapshot's objects; it writes exit-code and seconds itself
            _r1st=$(ra_utc)
            ra_say "release-check started (host)"
            if ! ra_ci_same release-check.sh common.sh; then
                _r1w="ci/ changed during the run: release-check.sh or common.sh differs from the snapshot"
                _r1w="$_r1w (runner_ci_tree $runner_ci_tree); start the run again"
                printf 'run-all.sh: %s\n' "$_r1w" >>"$run/release-check.log"
                ci_status release-check fail "$_r1w" engine_rc= code= seconds= "started=$_r1st"
            else
                sh "$CI_DIR/release-check.sh" --tree "$tree" --commit "$commit" \
                    --out "$run/stages/release-check/out" >>"$run/release-check.log" 2>&1 &
                lane_pids=$!
                wait "$lane_pids"
                _r1e=$?
                lane_pids=''
                ra_rc_verdict "$_r1e" "started=$_r1st"
            fi ;;
        *)
            ( ra_box "$_r1s" ) &
            lane_pids=$!
            wait "$lane_pids"
            lane_pids='' ;;
    esac
    ra_done "$_r1s" "$_r1t"
}

ra_fetch_local() {   # <set> <key>: (in place) install the pinned <set> tools into a new .ci-cache/deps/<key>[.N]/
    # through ci/stage.sh and the deps.sh worker (network); "complete" is written last, after its verdict passed
    _fls=$1 _flk=$2 _fln=deps-local-$1 _flr=$run/deps _fl0=$(date +%s) _flst=$(ra_utc)
    if [ ! -d "$_flr/stages" ] && ! mkdir -p "$_flr/stages"; then return 1; fi
    if ! mkdir -p "$CI_CACHE/deps"; then
        echo "run-all.sh: cannot create $CI_CACHE/deps (set CI_CACHE to a writable folder)" >&2
        return 1
    fi
    _fld=$(ci_newdir "$CI_CACHE/deps/$_flk" .) || return 1
    if ! mkdir "$_flr/stages/$_fln" "$_flr/stages/$_fln/out" "$_flr/stages/$_fln/work"; then return 1; fi
    ra_say "$_fln started (in place; pip installs ci/requirements-$_fls.txt into $_fld/deps)"
    CI_SRC=$CI_REPO CI_IN=$run CI_OUT=$_flr/stages/$_fln/out CI_WORK=$_flr/stages/$_fln/work \
        CI_STAGE=$_fln CI_TIMEOUT=$(ci_timeout_of "$_fln") CI_DEPS_TARGET=$_fld/deps \
        sh "$CI_DIR/stage.sh" deps.sh install "$_fls" >>"$_flr/$_fln.log" 2>&1 &
    lane_pids=$!
    wait "$lane_pids"
    _fle=$?
    lane_pids=''
    # The verdict of ci/common.sh, written into <run>/deps/stages/; in place the worker keeps no deps.tar (it
    # installs straight into the cache folder), so freeze.txt is the result file it must leave.
    run=$_flr
    ( ci_required() { echo freeze.txt; }
      ci_verdict "$_fln" "$_fle" "image=in place" "started=$_flst" "deps=$_flk" )
    _flres=$(ci_result_of "$_fln")
    run=$ra_run
    _flw=$(sed -n 's/^reason=//p' "$_flr/stages/$_fln/status" 2>/dev/null | tail -n 1)
    if [ "$_flres" = pass ]; then
        _flq=$(ci_filehash "$CI_DIR/requirements-$_fls.txt" 64) || _flq=''
        _flc=$(ci_filehash "$CI_DIR/deps.sh" 64) || _flc=''
        _fly=$(sed -n 's/^python=//p' "$_flr/stages/$_fln/out/result.txt" | head -n 1)
        if ! ( set -C; cat "$_flr/stages/$_fln/out/freeze.txt" >"$_fld/freeze.txt" ) ||
            ! cmp -s "$_flr/stages/$_fln/out/freeze.txt" "$_fld/freeze.txt" ||
            ! ( set -C
                { printf 'key=%s\nimage=in place\nrequirements=ci/requirements-%s.txt\n' "$_flk" "$_fls" &&
                  printf 'requirements_blob=%s\nrecipe=%s\npython=%s\n' "$_flq" "$_flc" "$_fly" &&
                  printf 'created=%s\n' "$(ra_utc)"; } >"$_fld/complete" ); then
            _flres=fail _flw="the marker of $_fld could not be written; the folder is never used"
        fi
    fi
    ra_say "$_fln $_flres ($(( $(date +%s) - _fl0 )) s)${_flw:+ $_flw}"
    if [ "$_flres" != pass ]; then
        ra_warn "the pinned $_fls tools were not installed: ${_flw:-see $_flr/$_fln.log}"
        return 1
    fi
    return 0
}

# ---- the pinned tools: every missing key is fetched before the first stage, so no lane races another
if [ "$mode" = host ]; then
    set --
    for st in $stages; do
        k=$(ra_key_of "$st")
        if [ -z "$k" ]; then continue; fi
        if ! ci_present "$(ra_image "$(ci_role_of "$st")")"; then continue; fi   # that stage fails on its image
        if ! ci_deps_find "$k" >/dev/null; then set -- "$@" "$st"; fi
    done
    if [ $# -gt 0 ] && [ "$offline" = yes ]; then
        ra_say "pinned tools not cached for: $* (--offline: nothing is fetched)"
    elif [ $# -gt 0 ] && ! ra_ci_same deps.sh common.sh legs requirements-test.txt requirements-lint.txt; then
        w="ci/ changed after the snapshot (deps.sh, common.sh, legs or a requirements file)"
        ra_warn "$w: nothing is fetched for $*, and those stages fail; start the run again"
    elif [ $# -gt 0 ]; then
        ra_say "pinned tools not cached for: $*; fetching them: sh ci/deps.sh $*"
        CI_RUN_DIR=$run CI_NAME_PREFIX=$ci_name_prefix sh "$CI_DIR/deps.sh" "$@" >&2 &
        lane_pids=$!
        wait "$lane_pids"
        n=$?
        lane_pids=''
        if [ "$n" = 2 ]; then ra_warn "sh ci/deps.sh exited 2 (usage or environment; see above)"; fi
    fi
else
    done_keys=' '
    for st in $stages; do
        k=$(ra_key_of "$st")
        if [ -z "$k" ]; then continue; fi
        case $done_keys in *" $k "*) continue ;; esac
        done_keys="$done_keys$k "
        if ci_deps_find "$k" >/dev/null; then continue; fi
        if [ "$offline" = yes ]; then
            ra_say "pinned tools not installed for $st: $k (--offline: nothing is fetched)"
            continue
        fi
        ra_fetch_local "$(ra_set_of "$st")" "$k"
    done
fi

# ---- the stages: the others one job at a time, then the test legs in lanes, then release-check
for st in $stages; do
    case $st in test-*|release-check) continue ;; esac
    ra_run1 "$st"
done
legs=''
for st in test-42 test-340 test-344 test-40 test-322 test-local; do   # the longest legs first
    case " $stages " in *" $st "*) legs="$legs $st" ;; esac
done
if [ -n "$legs" ] && [ "$mode" = in-place ]; then
    for st in $legs; do ra_run1 "$st"; done
elif [ -n "$legs" ]; then
    k=1
    while [ "$k" -le "$jobs" ]; do   # lane k takes legs k, k+N, ...
        i=0 mine=''
        for st in $legs; do
            if [ $((i % jobs + 1)) = "$k" ]; then mine="$mine $st"; fi
            i=$((i + 1))
        done
        if [ -n "$mine" ]; then
            ( for st in $mine; do t0=$(date +%s); ra_box "$st"; ra_done "$st" "$t0"; done ) &
            lane_pids="$lane_pids $!"
        fi
        k=$((k + 1))
    done
    wait
    lane_pids=''
fi
case " $stages " in *" release-check "*) ra_run1 release-check ;; esac

# ---- positive evidence: a stage without exactly one valid verdict failed
run_result=pass
for st in $stages; do
    r=$(ci_result_of "$st")
    case $r in
        pass) ;;
        skip) if [ "$release" = yes ]; then run_result=fail; fi ;;
        fail) run_result=fail ;;
        *)
            if [ "$mode" = host ]; then   # an orphan of a dead lane, if it still runs
                ci_engine kill "$ci_name_prefix-$st" >/dev/null 2>&1
            fi
            ci_status "$st" fail "no verdict (its lane died or the run was interrupted)"
            ra_say "$st fail: no verdict (its lane died or the run was interrupted)"
            run_result=fail ;;
    esac
done
printf 'run_result=%s\n' "$run_result" >>"$run/run.txt"

# ---- the summary: summary.md and record.txt, copied to the run folder only if the summary stage passed
s=summary
if [ "$mode" = host ]; then
    if ! ci_present "$pyref"; then
        ci_status summary fail "missing image $pyref; run: sh ci/pull.sh pure" engine_rc= code= seconds= \
            "image=$pyref"
        ra_warn "no summary: the python image is missing ($pyref; run: sh ci/pull.sh pure)"
    elif ! tar -cf "$run/input/summary.tar" -C "$run" run.txt stages 2>>"$run/summary.log"; then
        ci_status summary fail "input build failed: tar of run.txt and stages/" engine_rc= code= seconds= \
            "image=$pyref"
        ra_warn "no summary: the tar of run.txt and stages/ failed (see $run/summary.log)"
    else
        ra_run1 summary
    fi
elif python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    ra_run1 summary
else
    ci_status summary fail "no python3 >= 3.8 here for the summary" engine_rc= code= seconds= "image=in place"
    ra_warn "no summary: it needs python3 >= 3.8 in place"
fi
trap - INT TERM HUP PIPE
summary_ok=no
if [ "$(ci_result_of summary)" = pass ]; then
    summary_ok=yes
    for f in summary.md record.txt; do   # record.txt (read by tag.sh) only once summary.md was copied
        [ "$summary_ok" = yes ] || break
        if ! ( set -C; cat "$run/stages/summary/out/$f" >"$run/$f" ) || ! cmp -s "$run/stages/summary/out/$f" "$run/$f"
        then
            summary_ok=no
            ra_warn "cannot copy $f into $run"
        fi
    done
fi

echo "run-all.sh: run folder $run"
if [ -n "$warnings" ]; then printf '%s' "$warnings"; fi
if [ "$summary_ok" = yes ]; then
    sed '/^## Slowest/q' "$run/summary.md"
else
    echo "No summary.md; the verdicts from the status files:"
    printf '%-14s %-8s %s\n' stage result reason
    for st in $stages summary; do
        printf '%-14s %-8s %s\n' "$st" "$(ci_result_of "$st")" "$(ra_reason "$st")"
    done
    if [ -f "$run/package.log" ]; then grep '^WARNING' "$run/package.log"; fi
fi
if [ "$run_result" = pass ] && [ "$summary_ok" = yes ]; then
    echo "run-all.sh: PASS"   # the script ends here with exit status 0
else
    echo "run-all.sh: FAIL (run folder $run)"
    exit 1
fi
