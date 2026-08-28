---
id: bug-review-bodies-silently-dropped
title: Review response ignores top-level review bodies, silently dropping CHANGES_REQUESTED feedback
type: bug
status: fixed
repos: [epic-code-gen]
jira: RHAIFIRST-375
commits: ["164d21e"]
decisions: [ADR-0032]
---

# Bug: Review response ignores top-level review bodies, silently dropping CHANGES_REQUESTED feedback

## Summary

The review-response loop only examined inline review comments. A reviewer who left `CHANGES_REQUESTED` with their objection in the review **body** produced no work at all.

## Reproduction

1. Open a PR from the pipeline.
2. Submit a review with state `CHANGES_REQUESTED` and text in the body, but no inline comments.
3. Run the pipeline again.

## Expected

The review body is treated as actionable feedback and addressed.

## Actual

No actionable comments found. The epic sits still while the PR shows changes requested.

## Impact

High

## Evidence

`pr_lifecycle.py` gained `format_review_feedback`, `filter_unprocessed_reviews`, and `review_to_comment` to convert a review body into an actionable item, plus `ACTIONABLE_REVIEW_STATES`.

## Related Tasks

- [[task-v2-review-response-orchestrator]]
- [[M5-state-integrity]]
- Fixed in the same commit as [[task-rebase-epic-branches-every-cycle]]
