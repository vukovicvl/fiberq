#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/pull.sh - pull the pinned images the pipeline runs; the only step of the pipeline that pulls.
# Usage:
#   sh ci/pull.sh [--hook|--quick|--release|<stage>...]
#   sh ci/pull.sh --bump <role>...
# The first form takes every role the named stages or set need (the default set if none is named), plus python
# for the summary, and reports it present or pulls it by its digest in ci/legs (CI_IMAGE_<ROLE> overrides one).
# --bump is a maintainer step (docker only): it resolves the role's tag to its current digest, pulls that digest,
# which moves no local tag, and prints the replacement line for ci/legs. It never edits ci/legs.
# Exit: 0 all done; 1 some image failed (the others still ran); 2 usage or environment.
set -u
case $0 in */*) CI_DIR=${0%/*} ;; *) CI_DIR=. ;; esac
# shellcheck source=common.sh
. "$CI_DIR/common.sh"

usage() {
    echo "usage: sh ci/pull.sh [--hook|--quick|--release|<stage>...]"
    echo "       sh ci/pull.sh --bump <role>..."
    echo "stages: $CI_ALL_STAGES (a bare leg such as 42 means test-42)"
    echo "roles: the first column of ci/legs"
}

bump=no pset='' stages=''
case ${1:-} in
    -h|--help) usage; exit 0 ;;
    '') pset=default ;;
    --hook|--quick|--release)
        pset=${1#--}; shift
        if [ $# -ne 0 ]; then echo "pull.sh: --$pset takes no stage names" >&2; usage >&2; exit 2; fi ;;
    --bump)
        bump=yes; shift
        if [ $# -eq 0 ]; then echo "pull.sh: --bump needs a role" >&2; usage >&2; exit 2; fi ;;
esac
if [ "$bump" = no ] && [ -z "$pset" ]; then
    for a in "$@"; do
        case $a in -*) echo "pull.sh: unknown option '$a'" >&2; usage >&2; exit 2 ;; esac
        st=$(ci_stage_name "$a") || exit 2
        stages="$stages $st"
    done
fi
if [ -n "$pset" ]; then stages=$(ci_set_stages "$pset") || exit 2; fi
if [ "$bump" = yes ] && [ "${CI_ENGINE:-docker}" != docker ]; then
    echo "pull.sh: --bump needs docker (docker buildx imagetools); with podman, resolve the digest with skopeo" >&2
    exit 2
fi

ci_init nogit

if [ "$bump" = yes ]; then
    if ! ci_engine buildx version >/dev/null 2>&1; then
        echo "pull.sh: --bump needs docker buildx (docker buildx imagetools inspect)" >&2
        exit 2
    fi
    zero=0000000000000000000000000000000000000000000000000000000000000000
    failed=0
    for role in "$@"; do
        found=no repo='' old='' tag=''
        while read -r lr lref lt lx || [ -n "$lr" ]; do
            [ "$lr" = "$role" ] || continue
            found=yes repo=${lref%%@*} tag=$lt
            if ! ci_ref_ok "$repo@sha256:$zero" || [ -n "$lx" ]; then
                echo "pull.sh: the ci/legs line of $role needs <registry>/<repository>@<digest> <tag>" >&2
                exit 2
            fi
            case $tag in ''|*[!A-Za-z0-9_.-]*) echo "pull.sh: bad tag '$tag' for $role in ci/legs" >&2; exit 2 ;; esac
            old=none
            if ci_ref_ok "$lref"; then old=${lref#*@}; fi
            break
        done <"$CI_DIR/legs"
        if [ "$found" = no ]; then echo "pull.sh: role $role not in ci/legs" >&2; exit 2; fi
        if ! new=$(ci_engine buildx imagetools inspect "$repo:$tag" --format '{{.Manifest.Digest}}'); then
            echo "FAILED $role: cannot resolve $repo:$tag"
            failed=1
            continue
        fi
        if ! ci_ref_ok "$repo@$new"; then
            echo "FAILED $role: $repo:$tag resolved to '$new', not sha256:<64 hex>"
            failed=1
            continue
        fi
        if ! ci_engine pull --platform linux/amd64 "$repo@$new" >&2; then
            echo "FAILED $role: cannot pull $repo@$new"
            failed=1
            continue
        fi
        same=''
        [ "$old" != "$new" ] || same=' (unchanged)'
        echo "$role old $old new $new$same"
        echo "replacement line for ci/legs:"
        printf '%-8s %-100s %s\n' "$role" "$repo@$new" "$tag"
    done
    exit "$failed"
fi

roles=''
for st in $stages summary; do
    r=$(ci_role_of "$st") || exit 2
    [ -n "$r" ] || continue
    case " $roles " in *" $r "*) ;; *) roles="$roles $r" ;; esac
done
for r in $roles; do
    ci_image "$r" >/dev/null || exit 2
done
failed=0
for r in $roles; do
    ref=$(ci_image "$r") || exit 2
    note=''
    [ -z "$(ci_override "$r")" ] || note=' (override)'
    if ci_present "$ref"; then
        echo "present $r $ref$note"
    elif ci_engine pull --platform linux/amd64 "$ref" >&2; then
        echo "pulled $r $ref$note"
    else
        if [ "$r" = checker ]; then
            echo "FAILED $r $ref$note (the qt6 stage will report skipped: needs ghcr.io)"
        else
            echo "FAILED $r $ref$note"
        fi
        failed=1
    fi
done
exit "$failed"
