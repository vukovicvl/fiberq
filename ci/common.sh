#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/common.sh - host library of the pipeline: engine, stage sets, image pins, run folders, snapshot, stream, verdict.
# Usage, at the top of a host script in ci/:
#   set -u
#   case $0 in */*) CI_DIR=${0%/*} ;; *) CI_DIR=. ;; esac
#   # shellcheck source=common.sh
#   . "$CI_DIR/common.sh"
#   ci_init               (ci_init noengine: no container is started; ci_init nogit: git is not needed)
# Each function names its arguments on its first line. Names used inside functions start with "_" and a
# prefix of their own, so nested calls do not overwrite each other; callers must not rely on them.
# The verdict functions work on the run folder in $run (a deps fetch points run at a folder of the same layout).
# Callers also set s (the stage), commit, dkey (the deps key, or empty) and release (yes or no), and run-all.sh sets
# strict (yes or no): ci_engine_run passes s, commit and dkey into the container, and ci_verdict fails a skip when
# release=yes or strict=yes. ci_verdict calls ci_status and ci_required by name; package.sh redefines ci_status and
# run-all.sh redefines ci_required around it (in a subshell), so keep those calls.

umask 022
unset CDPATH   # a cd that finds its folder through CDPATH prints it, and $(cd ... && pwd -P) would capture that too
CI_SELF=${0##*/}
ENGINE=${CI_ENGINE:-docker}

# ---- stage sets, in canonical order (the order of run.txt, summary.md and record.txt; run-all.sh runs the test
# legs after the other stages, longest first, and release-check last); tag.sh requires every stage of
# CI_RELEASE_STAGES
CI_HOOK_STAGES='pure lint package'
CI_QUICK_STAGES='pure lint qt6 floor package'
CI_DEFAULT_STAGES='pure lint qt6 floor package test-322 test-344 test-42'
CI_RELEASE_STAGES='pure lint qt6 floor package test-322 test-340 test-344 test-40 test-42 release-check'
CI_ALL_STAGES='pure lint qt6 floor package test-322 test-340 test-344 test-40 test-42 test-local test-coverage'
CI_ALL_STAGES="$CI_ALL_STAGES release-check"   # test-local and test-coverage are in no set: --only names them

ci_set_stages() {   # <hook|quick|default|release>: print that set's stages, in canonical order
    case $1 in
        hook) printf '%s\n' "$CI_HOOK_STAGES" ;;
        quick) printf '%s\n' "$CI_QUICK_STAGES" ;;
        default) printf '%s\n' "$CI_DEFAULT_STAGES" ;;
        release) printf '%s\n' "$CI_RELEASE_STAGES" ;;
        *) echo "$CI_SELF: unknown set '$1'" >&2; return 2 ;;
    esac
}

ci_stage_name() {   # <word>: print the stage it names (a bare leg such as 42 or local means test-42, test-local)
    case $1 in
        322|340|344|40|42|local) printf 'test-%s\n' "$1" ;;
        *)
            case " $CI_ALL_STAGES " in
                *" $1 "*) printf '%s\n' "$1" ;;
                *) echo "$CI_SELF: unknown stage '$1' (stages: $CI_ALL_STAGES)" >&2; return 2 ;;
            esac ;;
    esac
}

ci_canonical() {   # <stage>...: print the given stages once each, in canonical order, space-separated
    _cno=''
    for _cns in $CI_ALL_STAGES; do
        for _cng in "$@"; do
            if [ "$_cng" = "$_cns" ]; then _cno="$_cno $_cns"; break; fi
        done
    done
    printf '%s\n' "${_cno# }"
}

ci_role_of() {   # <stage>: print the ci/legs role whose image runs <stage>; nothing for release-check and test-local
    case $1 in
        pure|lint|package|summary|lock|compare) echo python ;;
        qt6) echo checker ;;
        floor) echo floor ;;
        test-322|test-340|test-344|test-40|test-42) printf '%s\n' "${1#test-}" ;;
        test-coverage) echo 42 ;;
        release-check|test-local) ;;
        *) echo "$CI_SELF: no role for stage '$1'" >&2; return 2 ;;
    esac
}

ci_timeout_of() {   # <stage>: print the stage's timeout in seconds: CI_TIMEOUT when set, else the stage default
    if [ -n "${CI_TIMEOUT:-}" ]; then printf '%s\n' "$CI_TIMEOUT"; return 0; fi
    case $1 in
        pure|lint) echo 900 ;;
        qt6|floor) echo 600 ;;
        package|summary|compare*) echo 300 ;;
        test-*) echo 3600 ;;
        deps*|lock*) echo 1800 ;;
        *) echo 600 ;;
    esac
}

# ---- small helpers

ci_whole() {   # <value>: true when <value> is a whole number >= 1 (digits only, no leading zero)
    case $1 in ''|*[!0-9]*|0*) return 1 ;; esac
    return 0
}

ci_abspath() {   # <path>: print <path> made absolute against the current folder (it need not exist)
    case $1 in
        /*|[A-Za-z]:/*) printf '%s\n' "$1" ;;
        *) printf '%s/%s\n' "$(pwd -P)" "$1" ;;
    esac
}

ci_utc_stamp() {   # print the UTC time as YYYYmmddTHHMMSSZ, the start of every folder name in ci-results/
    date -u +%Y%m%dT%H%M%SZ
}

ci_newdir() {   # <path> [<sep>]: plain mkdir of <path>, else <path><sep>2, <path><sep>3, ... (sep -); print it
    _ndb=$1 _nds=${2:--} _ndt=$1 _ndk=1
    while ! mkdir "$_ndt" 2>/dev/null; do
        if [ ! -e "$_ndt" ]; then
            echo "$CI_SELF: cannot create $_ndt" >&2
            return 1
        fi
        _ndk=$((_ndk + 1)); _ndt=$_ndb$_nds$_ndk
    done
    printf '%s\n' "$_ndt"
}

ci_new_run() {   # <name suffix>: create and print a new folder $CI_RESULTS/<UTC time>-<suffix>[-N]
    if [ ! -d "$CI_RESULTS" ] && ! mkdir -p "$CI_RESULTS"; then
        echo "$CI_SELF: cannot create $CI_RESULTS (set CI_RESULTS to a writable folder)" >&2
        return 2
    fi
    ci_newdir "$CI_RESULTS/$(ci_utc_stamp)-$1" || {
        echo "$CI_SELF: set CI_RESULTS to a writable folder" >&2
        return 2
    }
}

# ---- the engine: every engine call goes through ci_engine

ci_engine() {   # <engine args>: run the engine, with MSYS path conversion off for it only (git keeps it)
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$ENGINE" "$@"
}

ci_engine_up() {   # exit 2 unless the engine is installed and answers (<engine> info)
    if ! command -v "$ENGINE" >/dev/null 2>&1; then
        echo "$CI_SELF: $ENGINE is not installed (CI_ENGINE is docker or podman)" >&2
        exit 2
    fi
    if ! _ue=$(ci_engine info 2>&1 >/dev/null); then
        printf '%s\n' "$_ue" | head -n 5 >&2
        echo "$CI_SELF: $ENGINE is not reachable (daemon or Docker Desktop not running, or DOCKER_HOST wrong)" >&2
        exit 2
    fi
}

ci_present() {   # <ref>: true when the engine holds image <ref>
    ci_engine image inspect "$1" >/dev/null 2>&1
}

# ---- setup

ci_init() {   # [noengine] [nogit]: check CI_ENGINE, CI_TIMEOUT, git and the engine, else exit 2; call it first
    # sets ENGINE CI_DIR CI_REPO CI_RESULTS CI_CACHE CI_HAVE_GIT CI_SHALLOW; in place: no engine check, git optional
    _icengine=yes _icgit=yes
    for _ica in "$@"; do
        case $_ica in
            noengine) _icengine=no ;;
            nogit) _icgit=no ;;
            *) echo "$CI_SELF: ci_init: unknown option '$_ica'" >&2; exit 2 ;;
        esac
    done
    [ "${CI_IN_PLACE:-}" != 1 ] || { _icengine=no; _icgit=no; }
    ENGINE=${CI_ENGINE:-docker}
    case $ENGINE in
        docker|podman) ;;
        *) echo "$CI_SELF: CI_ENGINE must be docker or podman, not '$ENGINE'" >&2; exit 2 ;;
    esac
    if [ -n "${CI_TIMEOUT:-}" ] && ! ci_whole "$CI_TIMEOUT"; then
        echo "$CI_SELF: CI_TIMEOUT must be whole seconds >= 1, not '$CI_TIMEOUT'" >&2
        exit 2
    fi
    CI_DIR=$(cd "${CI_DIR:?set CI_DIR to the ci/ folder before sourcing common.sh}" && pwd -P) || exit 2
    CI_REPO=$(cd "$CI_DIR/.." && pwd -P) || exit 2
    CI_HAVE_GIT=no
    if command -v git >/dev/null 2>&1 && _iccdup=$(cd "$CI_REPO" && git rev-parse --show-cdup 2>/dev/null) &&
        [ -z "$_iccdup" ]; then
        CI_HAVE_GIT=yes
    elif [ "$_icgit" = yes ]; then
        echo "$CI_SELF: needs git, run from a git checkout of the repository ($CI_REPO)" >&2
        exit 2
    fi
    CI_SHALLOW=no
    if [ "$CI_HAVE_GIT" = yes ] && ci_is_shallow; then CI_SHALLOW=yes; fi
    CI_RESULTS=$(ci_abspath "${CI_RESULTS:-$CI_REPO/ci-results}")
    CI_CACHE=$(ci_abspath "${CI_CACHE:-$CI_REPO/.ci-cache}")
    if [ "$_icengine" = yes ]; then ci_engine_up; fi
}

ci_is_shallow() {   # true in a shallow clone (git >= 2.15 says so; for older git the shallow file decides)
    [ "$(git -C "$CI_REPO" rev-parse --is-shallow-repository 2>/dev/null)" = true ] && return 0
    ( cd "$CI_REPO" && _isf=$(git rev-parse --git-path shallow 2>/dev/null) && [ -n "$_isf" ] && [ -f "$_isf" ] )
}

ci_refuse_shallow() {   # <message>: exit 2 with <message> in a shallow clone (CI_SHALLOW, from ci_init)
    if [ "${CI_SHALLOW:-no}" != no ]; then
        echo "$CI_SELF: $1" >&2
        exit 2
    fi
}

# ---- images: ci/legs holds "<role> <registry>/<repository>@sha256:<digest> <tag>" per line

ci_ref_ok() {   # <ref>: true when <ref> is <registry>/<repository>@sha256:<64 lowercase hex>
    case $1 in *@sha256:*) ;; *) return 1 ;; esac
    _rfr=${1%@sha256:*} _rfh=${1##*@sha256:}
    case $_rfh in *[!0-9a-f]*) return 1 ;; esac
    [ "${#_rfh}" -eq 64 ] || return 1
    case $_rfr in */*) ;; *) return 1 ;; esac
    case $_rfr in *[!A-Za-z0-9._:/-]*) return 1 ;; esac
    case ${_rfr%%/*} in *.*|*:*|localhost) return 0 ;; esac
    return 1
}

ci_legs_ref() {   # <role|''>: check every ci/legs line, then print <role>'s ref ('' only checks); else return 2
    _lw=$1 _lf='' _lseen=' ' _ln=0
    if [ ! -f "$CI_DIR/legs" ]; then
        echo "$CI_SELF: ci/legs not found" >&2
        return 2
    fi
    while read -r _lr _lref _lt _lx || [ -n "$_lr" ]; do
        _ln=$((_ln + 1))
        case $_lr in ''|'#'*) continue ;; esac
        _lbad=''
        if [ -z "$_lt" ] || [ -n "$_lx" ]; then
            _lbad='it needs three fields'
        elif ! ci_ref_ok "$_lref"; then
            _lbad="'$_lref' is not a digest reference"
        else
            case $_lr in *[!a-z0-9]*) _lbad="bad role name '$_lr'" ;; esac
            case $_lt in *[!A-Za-z0-9_.-]*) _lbad="bad tag '$_lt'" ;; esac
            case $_lseen in *" $_lr "*) _lbad="role $_lr appears twice" ;; esac
        fi
        if [ -n "$_lbad" ]; then
            echo "$CI_SELF: ci/legs line $_ln: $_lbad;" \
                "expected <role> <registry>/<repository>@sha256:<64 hex> <tag>" >&2
            return 2
        fi
        _lseen="$_lseen$_lr "
        if [ "$_lr" = "$_lw" ]; then _lf=$_lref; fi
    done <"$CI_DIR/legs"
    [ -n "$_lw" ] || return 0
    if [ -z "$_lf" ]; then
        echo "$CI_SELF: role $_lw not in ci/legs" >&2
        return 2
    fi
    printf '%s\n' "$_lf"
}

ci_override() {   # <role>: print CI_IMAGE_<ROLE>, empty when unset (a case statement, never eval)
    case $1 in
        python) printf '%s\n' "${CI_IMAGE_PYTHON:-}" ;;
        checker) printf '%s\n' "${CI_IMAGE_CHECKER:-}" ;;
        floor) printf '%s\n' "${CI_IMAGE_FLOOR:-}" ;;
        322) printf '%s\n' "${CI_IMAGE_322:-}" ;;
        340) printf '%s\n' "${CI_IMAGE_340:-}" ;;
        344) printf '%s\n' "${CI_IMAGE_344:-}" ;;
        40) printf '%s\n' "${CI_IMAGE_40:-}" ;;
        42) printf '%s\n' "${CI_IMAGE_42:-}" ;;
        *) printf '\n' ;;
    esac
}

ci_image() {   # <role>: print the image ref for <role>, CI_IMAGE_<ROLE> if set, else ci/legs; return 2 with a message
    _imo=$(ci_override "$1")
    ci_legs_ref '' || return 2
    if [ -z "$_imo" ]; then
        ci_legs_ref "$1"
        return
    fi
    if ! ci_ref_ok "$_imo"; then
        echo "$CI_SELF: CI_IMAGE_$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')='$_imo' is not" \
            "<registry>/<repository>@sha256:<64 hex>" >&2
        return 2
    fi
    printf '%s\n' "$_imo"
}

# ---- the tested tree: a snapshot of the working tree through a temporary index and object folder; it adds no
# object to .git and leaves .git/index alone

ci_snapgit() {   # <git args>: git in CI_REPO with the snapshot's temporary index and object folder (after ci_snapshot)
    GIT_INDEX_FILE=$CI_SNAP_INDEX GIT_OBJECT_DIRECTORY=$CI_SNAP_OBJECTS GIT_ALTERNATE_OBJECT_DIRECTORIES=$CI_SNAP_ALT \
        git -C "$CI_REPO" "$@"
}

ci_git() {   # <git args>: git in CI_REPO that also reads the snapshot's objects (CI_SNAP_OBJECTS, CI_SNAP_ALT)
    # set by ci_snapshot; a host script started by run-all.sh gets both exported
    if [ -n "${CI_SNAP_OBJECTS:-}" ]; then
        GIT_OBJECT_DIRECTORY=$CI_SNAP_OBJECTS GIT_ALTERNATE_OBJECT_DIRECTORIES=${CI_SNAP_ALT:-} git -C "$CI_REPO" "$@"
    else
        git -C "$CI_REPO" "$@"
    fi
}

ci_snapshot() {   # <dir>: snapshot the working tree into the new <dir>; set CI_SNAP_TREE, CI_SNAP_INDEX/_OBJECTS/_ALT
    # a temporary index and object folder inside <dir>: nothing is added to .git (git may refresh the mtime of an
    # object .git already holds, when a changed file has that content); exit 2 on failure
    if [ "${CI_HAVE_GIT:-no}" != yes ]; then
        echo "$CI_SELF: the snapshot of the working tree needs git" >&2
        exit 2
    fi
    CI_SNAP_ALT=$(cd "$CI_REPO" && cd "$(git rev-parse --git-path objects)" && pwd -P) || exit 2   # no --path-format
    if ! mkdir "$1" || ! mkdir "$1/objects"; then exit 2; fi
    _sn=$(cd "$1" && pwd -P) || exit 2
    case $_sn/ in
        "$CI_REPO"/*)   # git add -A would take the run folder itself into the snapshot
            if ! git -C "$CI_REPO" check-ignore -q "$_sn/"; then
                echo "$CI_SELF: $_sn is inside the working tree but not ignored by git; set CI_RESULTS elsewhere" >&2
                exit 2
            fi ;;
    esac
    CI_SNAP_INDEX=$_sn/index CI_SNAP_OBJECTS=$_sn/objects
    # --refresh first, so that add -A writes only the changed files: git freshens (touches) an object that already
    # exists in .git, through the alternate, when it is written again. The sleep puts the refreshed index in a later
    # second than every change made before the run: git takes a file changed in the same second as the index for
    # possibly modified (racily clean), and add -A would write it again
    if ! { ci_snapgit read-tree HEAD && sleep 1 && ci_snapgit update-index -q --refresh && ci_snapgit add -A &&
        CI_SNAP_TREE=$(ci_snapgit write-tree); }; then
        echo "$CI_SELF: the snapshot of the working tree failed" >&2
        exit 2
    fi
}

ci_runner_dirty() {   # [<commit>]: print no when the snapshot (CI_SNAP_TREE) equals <commit>'s tree, else yes
    # pass the commit the caller read before the snapshot, so a commit made meanwhile cannot pair with it (HEAD)
    _rdh=$(git -C "$CI_REPO" rev-parse --verify --quiet "${1:-HEAD}^{tree}") || _rdh=''
    if [ -n "$_rdh" ] && [ "$_rdh" = "${CI_SNAP_TREE:-}" ]; then echo no; else echo yes; fi
}

# ---- the stream into a container, and the container command

# CI_BOOT, the container's command: store the stream in /tmp/in.tar, compare its size with CI_IN_BYTES (exit 98
# when it differs), extract it into /tmp/w and exec ci/stage.sh with the script and its argument.
# shellcheck disable=SC2016  # expanded by the container's sh, not here
CI_BOOT='set -eu; mkdir /tmp/w; cd /tmp/w; cat >/tmp/in.tar; n=$(wc -c </tmp/in.tar); [ "$n" -eq "$CI_IN_BYTES" ] || { echo "input stream: $n of $CI_IN_BYTES bytes" >&2; exit 98; }; tar -x -i -f /tmp/in.tar; exec sh /tmp/w/ci/stage.sh "$@"'

ci_engine_run() {   # <name> <ref> <none|default> <timeout> <bytes> <script> [<arg>]; stdin: stream, stdout: results
    _n=$1 _r=$2 _nw=$3 _t=$4 _b=$5 _sc=$6; shift 6     # also reads: s (stage), commit, dkey (deps key or '')
    case $_nw in
        none|default) ;;
        *) echo "$CI_SELF: ci_engine_run: network is none or default, not '$_nw'" >&2; return 2 ;;
    esac
    _net=''; [ "$_nw" = none ] && _net=none
    _pw=''; [ "$ENGINE" = podman ] && _pw=--passwd=false
    ci_engine run --rm -i --init --log-driver none --ulimit core=0 \
        --user 1000:1000 --pull=never --platform linux/amd64 ${_pw:+"$_pw"} ${_net:+--network "$_net"} \
        -e HOME=/tmp -e CI_STAGE="${s:?ci_engine_run needs s, the stage}" -e CI_TIMEOUT="$_t" \
        -e CI_COMMIT_SHA="${commit-}" -e CI_IMAGE_REF="$_r" -e CI_IN_BYTES="$_b" -e CI_DEPS_KEY="${dkey-}" \
        -w /tmp --name "$_n" --entrypoint sh "$_r" -c "$CI_BOOT" sh "$_sc" "$@"
}

ci_bytes() {   # <part>...: print the total size in bytes; return 1 if a part is missing or unreadable
    _tot=0
    for _p in "$@"; do
        [ -f "$_p" ] || return 1
        _sz=$(wc -c <"$_p") || return 1
        _sz=$(printf '%s' "$_sz" | tr -d ' ')          # BSD wc pads with spaces
        case $_sz in ''|*[!0-9]*) return 1 ;; esac
        _tot=$((_tot + _sz))
    done
    printf '%s\n' "$_tot"
}

ci_feed() {   # <rc-file> <part>...: the parts on stdout, then cat's exit status into <rc-file>
    _f=$1; shift
    cat "$@"
    printf '%s\n' "$?" >"$_f"
}

# ---- the verdict: $run/stages/<stage>/status, key=value, result= written last

ci_status() {   # <stage> <pass|fail|skip> <reason> [<key=value>...]: append stage=, reason=, the keys, result=
    _sts=$1 _str=$2
    _stb="stage=$1
reason=$(printf '%s' "$3" | tr '\r\n' '  ')"
    shift 3
    for _stkv in "$@"; do
        _stb="$_stb
$(printf '%s' "$_stkv" | tr '\r\n' '  ')"
    done
    _std=${run:?ci_status needs run, the run folder}/stages/$_sts
    mkdir -p "$_std" || return 1
    printf '%s\nresult=%s\n' "$_stb" "$_str" >>"$_std/status"
}

ci_result_of() {   # <stage>: print pass, fail or skip if its status holds exactly one such result= line; else invalid
    _rof=${run:?ci_result_of needs run, the run folder}/stages/$1/status
    if [ -f "$_rof" ]; then
        _roc=$(grep -c '^result=' "$_rof" 2>/dev/null) || _roc=0
        if [ "$_roc" = 1 ]; then
            _rov=$(sed -n 's/^result=//p' "$_rof")
            case $_rov in pass|fail|skip) printf '%s\n' "$_rov"; return 0 ;; esac
        fi
    fi
    echo invalid
}

ci_required() {   # <stage>: print the result files <stage> needs besides exit-code, seconds and result.txt
    case $1 in
        pure) echo junit.xml pure-files.tsv ;;
        test-coverage) echo junit.xml coverage.json coverage-core.tsv coverage-core.md ;;
        test-*) echo junit.xml ;;
        package)
            _rqv=$(sed -n '1p' "${run:?ci_required needs run, the run folder}/input/pkg/version" 2>/dev/null |
                tr -d '[:space:]')
            echo "fiberq-$_rqv.sha256 fiberq-$_rqv.contents.tsv" ;;
        deps*) echo deps.tar freeze.txt ;;
        summary) echo summary.md record.txt ;;
    esac
}

ci_verdict() {   # <stage> <engine status> [<key=value>...]: judge stages/<stage>/ and write its status
    # the keys given (image=, started=, deps=, dist=) are written after engine_rc, code and seconds; reads release
    # and strict (either yes: a skip fails), and calls ci_status and ci_required by name (package.sh and run-all.sh
    # redefine them)
    _vs=$1 _ve=$2; shift 2
    _vr=${run:?ci_verdict needs run, the run folder}
    _vd=$_vr/stages/$_vs _vc='' _vsec='' _vok=yes _vbox=no
    mkdir -p "$_vd" || return 1
    if [ "${CI_IN_PLACE:-}" != 1 ] && [ "$_vs" != release-check ]; then   # a container stage: feed, then tar
        _vbox=yes
        _vf=$(cat "$_vr/input/$_vs.feed-rc" 2>/dev/null) || _vf=''
        if [ "$_vf" != 0 ]; then
            # 125 is the engine's own error (docker and podman): it gave up before reading the stream
            if [ "$_ve" = 125 ]; then
                _vw="the engine could not run the container (engine status 125, host feed status ${_vf:-missing}"
                _vw="$_vw; see $_vs.log)"
            else
                _vw="input stream incomplete (host feed status ${_vf:-missing}, engine status $_ve)"
            fi
            ci_status "$_vs" fail "$_vw" "engine_rc=$_ve" code= seconds= "$@"
            return 0
        fi
        _vok=no
        if mkdir "$_vd/out" 2>>"$_vr/$_vs.log" && [ -s "$_vr/raw/$_vs.tar" ] &&
            tar -xf "$_vr/raw/$_vs.tar" -C "$_vd/out" 2>>"$_vr/$_vs.log"; then
            _vok=yes
        fi
        if [ "$_vok" = no ] && [ "$_ve" = 98 ]; then
            ci_status "$_vs" fail "input stream incomplete (the container received fewer bytes than were sent)" \
                "engine_rc=$_ve" code= seconds= "$@"
            return 0
        fi
    fi
    if [ "$_vok" = yes ]; then
        _vc=$(cat "$_vd/out/exit-code" 2>/dev/null) || _vc=''
        _vsec=$(cat "$_vd/out/seconds" 2>/dev/null) || _vsec=''
    fi
    case $_vsec in *[!0-9]*) _vsec='' ;; esac
    case $_vc in
        ''|*[!0-9]*)
            if [ "$_vbox" = yes ] && [ "$_ve" = 99 ]; then
                _vw="stage setup failed in the container (engine status 99; see $_vs.log)"
            elif [ "$_vbox" = yes ] && [ "$_ve" = 125 ]; then
                _vw="the engine could not run the container (engine status 125; see $_vs.log)"
            else
                _vw="no results (engine status $_ve)"
            fi
            ci_status "$_vs" fail "$_vw" "engine_rc=$_ve" code= "seconds=$_vsec" "$@"
            return 0 ;;
    esac
    if [ "$_ve" != "$_vc" ]; then
        ci_status "$_vs" fail "engine status $_ve but stage exit code $_vc" \
            "engine_rc=$_ve" "code=$_vc" "seconds=$_vsec" "$@"
        return 0
    fi
    if [ "$_vc" != 0 ]; then
        _vt=$(ci_timeout_of "$_vs")
        if { [ "$_vc" = 124 ] || [ "$_vc" = 137 ]; } && [ -n "$_vsec" ] && [ "$_vsec" -ge "$_vt" ]; then
            _vw="timed out after $_vt s"
        elif [ "$_vc" -gt 128 ]; then
            _vw="killed by signal $((_vc - 128))"
        else
            _vw="exit code $_vc"
        fi
        ci_status "$_vs" fail "$_vw" "engine_rc=$_ve" "code=$_vc" "seconds=$_vsec" "$@"
        return 0
    fi
    _vneed="exit-code seconds result.txt $(ci_required "$_vs")"
    for _vq in $_vneed; do
        if [ ! -f "$_vd/out/$_vq" ]; then
            ci_status "$_vs" fail "missing result file $_vq" "engine_rc=$_ve" "code=$_vc" "seconds=$_vsec" "$@"
            return 0
        fi
    done
    if grep -q '^skipped=' "$_vd/out/result.txt"; then
        _vw=$(sed -n 's/^skipped=//p' "$_vd/out/result.txt" | head -n 1)
        _vres=skip
        if [ "${release:-no}" = yes ] || [ "${strict:-no}" = yes ]; then _vres=fail; fi
        ci_status "$_vs" "$_vres" "skipped: $_vw" "engine_rc=$_ve" "code=$_vc" "seconds=$_vsec" "$@"
        return 0
    fi
    ci_status "$_vs" pass '' "engine_rc=$_ve" "code=$_vc" "seconds=$_vsec" "$@"
}

# ---- the deps cache: $CI_CACHE/deps/<key>[.N]/ holds deps.tar, freeze.txt and, written last, complete

ci_cksum() {   # <file>: print "<crc> <size>" from cksum, blanks squeezed (the value of deps_cksum= in complete)
    [ -f "$1" ] || return 1
    _ckv=$(cksum <"$1") || return 1
    printf '%s\n' "$_ckv" | tr -s '[:blank:]' ' '
}

ci_filehash() {   # <file> <n>: first <n> hex of git hash-object --no-filters <file> (ck<crc>s<size> without git)
    if [ ! -f "$1" ]; then
        echo "$CI_SELF: $1 not found" >&2
        return 1
    fi
    if command -v git >/dev/null 2>&1; then
        _fhh=$(git hash-object --no-filters "$1") || return 1
        printf '%s\n' "$_fhh" | sed 's/^\(.\{'"$2"'\}\).*/\1/'
    else
        _fhc=$(ci_cksum "$1") || return 1
        printf 'ck%ss%s\n' "${_fhc%% *}" "${_fhc#* }"
    fi
}

ci_deps_key() {   # <test|lint> [<image ref>]: print the deps cache key; without a ref (in place) local-py<X.Y>-...
    # <digest16>-<set>-<req16>-<recipe8>: the image digest, ci/requirements-<set>.txt and ci/deps.sh
    case $1 in test|lint) ;; *) echo "$CI_SELF: no tool set '$1' (test or lint)" >&2; return 2 ;; esac
    _kq=$(ci_filehash "$CI_DIR/requirements-$1.txt" 16) || return 1
    _kr=$(ci_filehash "$CI_DIR/deps.sh" 8) || return 1
    if [ -n "${2:-}" ]; then
        if ! ci_ref_ok "$2"; then
            echo "$CI_SELF: '$2' is not a digest reference" >&2
            return 2
        fi
        _kp=$(printf '%s\n' "${2##*@sha256:}" | sed 's/^\(.\{16\}\).*/\1/')
    else
        _kv=$(python3 -c 'import sys; sys.stdout.write("%d.%d" % sys.version_info[:2])') || {
            echo "$CI_SELF: python3 is needed for the in-place deps key" >&2
            return 1
        }
        _kp=local-py$_kv
    fi
    printf '%s-%s-%s-%s\n' "$_kp" "$1" "$_kq" "$_kr"
}

ci_deps_find() {   # <key>: print the first usable cache folder <key>, <key>.2, ... (stops at a missing name)
    _dfb=${CI_CACHE:?run ci_init first}/deps/$1 _dfk=1
    _dfd=$_dfb
    while [ -e "$_dfd" ]; do
        if [ -f "$_dfd/complete" ]; then
            case $1 in
                local-py*)   # in place: the tools are installed in <folder>/deps, no tar is kept
                    if [ -d "$_dfd/deps" ]; then printf '%s\n' "$_dfd"; return 0; fi ;;
                *)
                    _dfw=$(sed -n 's/^deps_cksum=//p' "$_dfd/complete" | head -n 1)
                    _dfh=$(ci_cksum "$_dfd/deps.tar") || _dfh=''
                    if [ -n "$_dfw" ] && [ "$_dfw" = "$_dfh" ]; then printf '%s\n' "$_dfd"; return 0; fi ;;
            esac
        fi
        _dfk=$((_dfk + 1)); _dfd=$_dfb.$_dfk
    done
    return 1
}
