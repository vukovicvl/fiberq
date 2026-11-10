#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/tag.sh - create the annotated tag v<version> for HEAD, only when a full release run has passed on its tree.
# Usage: sh ci/tag.sh
# <version> is version= in fiberq/metadata.txt at HEAD. tag.sh refuses unless the working tree is clean (a snapshot
# in a new ci-results/<time>-<commit12>-tag/ equals HEAD's tree), v<version> does not exist yet, and the newest full
# "sh ci/run-all.sh --release" run for HEAD's tree in ci-results/ (run.txt with root_tree= HEAD's tree, set=release,
# mode=host and an empty only=; runs with --only never count) has a record.txt, equal to the summary stage's own
# copy, with: result=pass, overrides=none, runner_dirty=no, shallow=no, stage.<s>=pass for every release stage, a
# zip_name, fiberq_commit= the commit that a build at HEAD takes fiberq/ from (so the zip can be rebuilt from the
# tag), and dist/<zip_name> equal to its package/ copy. A newer full run without a record.txt (interrupted, still
# running, or its summary failed) refuses.
# It never pushes.
# Exit: 0 tag created; 1 refused; 2 usage or environment (shallow clone, no git, git tag failed).
set -u

usage() {
    echo "usage: sh ci/tag.sh   (no arguments)"
    echo "Tags HEAD as v<version> (fiberq/metadata.txt) when the newest full release run for its tree qualifies:"
    echo "sh ci/run-all.sh --release, from this clean working tree. It never pushes."
}
case ${1:-} in
    '') ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac
if [ $# -gt 1 ]; then usage >&2; exit 2; fi

case $0 in */*) CI_DIR=${0%/*} ;; *) CI_DIR=. ;; esac
# shellcheck source=common.sh
. "$CI_DIR/common.sh"

if [ "${CI_IN_PLACE:-}" = 1 ]; then
    echo "tag.sh: runs on the host, from the records of host-mode release runs; unset CI_IN_PLACE" >&2
    exit 2
fi
ci_init noengine
ci_refuse_shallow "needs full history and the tags: git fetch --unshallow --tags"
head=$(git -C "$CI_REPO" rev-parse --verify --quiet 'HEAD^{commit}') || {
    echo "tag.sh: no commit is checked out" >&2
    exit 2
}
htree=$(git -C "$CI_REPO" rev-parse --verify --quiet "$head^{tree}") || exit 2   # from here on, HEAD is $head

tag_refuse() {   # <reason>: exit 1
    echo "tag.sh: refusing: $1" >&2
    exit 1
}

# 1. a clean working tree: the snapshot (untracked files included, ignored ones not) equals HEAD's tree
run=$(ci_new_run "$(printf '%s\n' "$head" | sed 's/^\(.\{12\}\).*/\1/')-tag") || exit 2
ci_snapshot "$run/snapshot"
if [ "$(ci_runner_dirty "$head")" != no ]; then
    tag_refuse "the working tree is dirty (snapshot $CI_SNAP_TREE, HEAD's tree $htree)"
fi

# 2. the version, and no tag of that name yet
ver=$(git -C "$CI_REPO" show "$head:fiberq/metadata.txt" 2>/dev/null | sed -n 's/^version=//p' | head -n 1 |
    tr -d '[:space:]')
case $ver in
    '') echo "tag.sh: No version found in fiberq/metadata.txt" >&2; exit 1 ;;
    .*|*[!A-Za-z0-9._+-]*) tag_refuse "version=$ver in fiberq/metadata.txt cannot name a tag" ;;
esac
if git -C "$CI_REPO" rev-parse -q --verify "refs/tags/v$ver" >/dev/null; then
    echo "tag.sh: Tag v$ver already exists - bump 'version=' in fiberq/metadata.txt first." >&2
    exit 1
fi

tag_key() {   # <record> <key>: print the value of the one <key>= line; false when there is none or more than one
    _tke=$(printf '%s\n' "$2" | sed 's/[.]/\\./g')
    _tkn=$(grep -c "^$_tke=" "$1" 2>/dev/null) || _tkn=0
    [ "$_tkn" = 1 ] || return 1
    sed -n "s/^$_tke=//p" "$1"
}

# 3. the full --release runs for this tree; runs with --only are named, never used
cands='' partial=''
for rec in "$CI_RESULTS"/*/record.txt; do
    [ -f "$rec" ] || continue
    [ "$(tag_key "$rec" root_tree)" = "$htree" ] || continue
    [ "$(tag_key "$rec" set)" = release ] || continue
    [ "$(tag_key "$rec" mode)" = host ] || continue
    d=${rec%/record.txt}
    d=${d##*/}
    if only=$(tag_key "$rec" only) && [ -z "$only" ]; then
        cands="$cands$d
"
    else
        partial="$partial $d"
    fi
done
if [ -z "$cands" ]; then
    why="no full --release run for this tree in $CI_RESULTS (runs with --only do not count)"
    if [ -n "$partial" ]; then why="$why; runs with --only for this tree:$partial"; fi
    tag_refuse "$why"
fi

# 4. the newest of them (the folder names start with the UTC time) is the evidence, and it must qualify
newest=$(printf '%s' "$cands" | LC_ALL=C sort | tail -n 1)
rdir=$CI_RESULTS/$newest
rec=$rdir/record.txt
# a newer full --release run for this tree that left no record.txt is newer evidence, and it does not qualify
runs=''
for rt in "$CI_RESULTS"/*/run.txt; do
    [ -f "$rt" ] || continue
    [ "$(tag_key "$rt" root_tree)" = "$htree" ] || continue
    [ "$(tag_key "$rt" set)" = release ] || continue
    [ "$(tag_key "$rt" mode)" = host ] || continue
    if ! only=$(tag_key "$rt" only) || [ -n "$only" ]; then continue; fi
    d=${rt%/run.txt}
    runs="$runs${d##*/}
"
done
latest=$(printf '%s%s\n' "$runs" "$newest" | LC_ALL=C sort | tail -n 1)
if [ "$latest" != "$newest" ]; then
    why="a newer full --release run for this tree, $CI_RESULTS/$latest, has no record.txt"
    tag_refuse "$why (interrupted, still running, or its summary failed); run sh ci/run-all.sh --release again"
fi
# run-all.sh copies record.txt from the summary stage; a copy that did not finish is not a record
if ! cmp -s "$rec" "$rdir/stages/summary/out/record.txt"; then
    tag_refuse "$rec differs from $rdir/stages/summary/out/record.txt (the copy did not finish)"
fi
tag_need() {   # <key> <wanted value>: refuse unless the newest full run's record has exactly that
    _tnv=$(tag_key "$rec" "$1") || _tnv='(no single line)'
    if [ "$_tnv" != "$2" ]; then
        tag_refuse "the newest full --release run for this tree, $rdir, has $1=$_tnv, not $2"
    fi
}
tag_need result pass
tag_need overrides none
tag_need runner_dirty no
tag_need shallow no
for st in $CI_RELEASE_STAGES; do tag_need "stage.$st" pass; done
zn=$(tag_key "$rec" zip_name) || zn=''
case $zn in
    ''|.*|*/*) tag_refuse "the newest full --release run for this tree, $rdir, names no usable zip (zip_name=$zn)" ;;
esac
# git archive stamps the zip with its commit (comment, entry times): the run's zip must come from the commit that
# ci/package.sh takes fiberq/ from at HEAD, or a build at the tag gives another zip (an amended commit, --ref)
fc=$(git -C "$CI_REPO" rev-list -1 "$head" -- fiberq) || fc=''
rfc=$(tag_key "$rec" fiberq_commit) || rfc='(no single line)'
if [ -z "$fc" ] || [ "$rfc" != "$fc" ]; then
    why="the newest full --release run for this tree, $rdir, built its zip from fiberq/ at ${rfc:-(none)}"
    tag_refuse "$why, but a build at HEAD takes fiberq/ from ${fc:-no commit}; run sh ci/run-all.sh --release on HEAD"
fi
if [ ! -f "$rdir/package/$zn" ]; then
    tag_refuse "the newest full --release run for this tree, $rdir, has no package/$zn"
fi
if [ ! -f "$CI_REPO/dist/$zn" ]; then
    tag_refuse "dist/$zn is missing (the release run copies it into an empty dist/; see its dist= in record.txt)"
fi
if ! cmp -s "$CI_REPO/dist/$zn" "$rdir/package/$zn"; then
    tag_refuse "dist/$zn differs from $rdir/package/$zn, the zip that the release run tested"
fi

# 5. the tag
if ! git -C "$CI_REPO" tag -a "v$ver" -m "FiberQ $ver" "$head"; then
    echo "tag.sh: git tag -a v$ver failed" >&2
    exit 2
fi
zs=$(tag_key "$rec" zip_sha256) || zs=unknown
echo "Created tag v$ver (not pushed). Release run: $rdir. Artifact: dist/$zn (sha256 $zs)."
exit 0
