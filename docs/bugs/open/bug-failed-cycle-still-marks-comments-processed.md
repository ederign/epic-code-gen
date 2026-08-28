---
id: bug-failed-cycle-still-marks-comments-processed
title: "A failed review-response cycle still replies to every comment and marks it processed, permanently dropping the feedback"
type: bug
status: open
repos: [epic-code-gen]
jira: RHAIFIRST-393
decisions: [ADR-0032]
---

# Bug: A failed review-response cycle still replies to every comment and marks it processed

## Summary

`run_review_response` posts replies and records them **unconditionally**, outside the `if not errors:`
guard that protects the push. Because the processed-comment set is derived from every reply ever recorded,
with no filter on version or outcome, a cycle that failed still consumes its comments. The next cycle finds
zero unprocessed comments and skips the epic — the feedback is gone with no retry path.

## Reproduction

1. Open a PR from the pipeline and have a reviewer leave inline comments.
2. Cause the review-response cycle to fail after triage — e.g. the fix agent errors, or the push fails.
3. Observe replies posted to all comments and appended to `pr-replies.json`.
4. Run the pipeline again. `filter_unprocessed_comments` returns nothing; the epic is skipped.

## Expected

A cycle that did not land its fixes leaves its comments unprocessed, so a later cycle retries them.

## Actual

Comments are marked processed regardless of outcome. The epic is permanently skipped for that feedback.

## Impact

High

## Observed incident

RHAI-69, 2026-07-31. All 8 review comments are now in the processed set after a cycle that did not land.
A future cycle finds zero unprocessed and skips the epic entirely.

## Evidence

**Root cause is placement, verified in source.** `# 9. Push to fork` is guarded
(`review_response.py:492`):

```python
                # 9. Push to fork
                if not errors:
```

but `# 10. Post replies` sits at the outer indentation level (`:508`), outside both that guard and its
`else`, so it runs on every path:

```python
    # 10. Post replies
    reply_sha = commit_sha or "no-change"
    if errors:
        reply_sha = "not-pushed"
```

**The processed set has no notion of success.** `save_pr_replies` (`review_response.py:222`) appends
cumulatively — `existing["replies"].extend(replies)` — and `load_processed_comment_ids`
(`pr_lifecycle.py:349`) returns:

```python
return {r["comment_id"] for r in data.get("replies", [])}
```

No filter on version, and none on outcome.

**One nuance, in the code's favour:** the reply text is *not* dishonest — `reply_sha` is set to
`"not-pushed"` when there are errors, so a human reading the PR can tell the cycle failed. The defect is
that the **pipeline** cannot tell, because the comment id is in the processed set either way. So the
feedback is dropped from the machine's perspective while remaining visible to a person, which is why it
went unnoticed.

**The fix is cheap because the data is already there.** `save_pr_replies` already stamps each reply with
`version`; it just needs an outcome too, and `load_processed_comment_ids` needs to filter on it. Moving the
reply step inside the guard would also work, but replying only on success loses the useful "we saw this and
failed" signal to reviewers — recording the outcome and filtering on it keeps both.

## Related Tasks

- [[task-v2-review-response-orchestrator]] — the cycle this defect lives in
- [[bug-review-gate-is-advisory]] (RHAIFIRST-391) — `Related` in Jira; same family of silent success
- [[bug-baseline-check-failures-scored-as-epic]] (RHAIFIRST-392) — `Related` in Jira; the failure mode that
  triggered this cycle's failure
- [[M6-review-gate-hardening]]
- [ADR-0032] records "reply to every comment" as a deliberate rule — this bug is that rule applied one
  level too broadly, so the ADR's Negative consequences should gain a line once fixed
