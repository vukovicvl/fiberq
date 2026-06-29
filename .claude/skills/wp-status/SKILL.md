---
name: wp-status
description: Summarise where the FiberQ build is — current work package / phase, what's done, what's next, and the per-task definition of done. Use to orient at the start of a session or before starting a new task.
---

Give a short, accurate status of the FiberQ build plan and the per-task definition of done.

## How
1. Read the build plan (the planning doc under `docs/private/`, if present) and any project memory for the phase/version map (WP1→v1.3, WP2→v1.4, WP3→v1.5, WP4→v1.6; WP5 tests/CI is cross-cutting; WP6 docs ship per release).
2. Check git state: current branch, latest tag, recent commits, and open PRs (if `gh` is available).
3. Read `fiberq/metadata.txt` for the current plugin version.

## Report
- Current plugin version and what's released.
- Which WP/phase is in progress and what is left in it.
- The next task and its definition of done:
  - feature branch merged to main,
  - tagged release with a changelog entry,
  - tests added/updated and green in CI,
  - docs/spec/demo published and linkable,
  - the deliverable is the new increment (not pre-existing code).
- Any blockers or decisions waiting on the maintainer.

Keep it to a tight summary, not a wall of text.
