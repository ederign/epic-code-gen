---
id: bug-review-response-hid-fix-agent-failure
title: The review-response path hid why the fix agent failed
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["d807dca"]
---

# Bug: The review-response path hid why the fix agent failed

## Summary

When the fix agent failed, the orchestrator reported a generic failure and discarded the actual error, making the cycle undiagnosable from CI logs.

## Reproduction

1. Cause the review-fix agent to fail (e.g. timeout or a tool error).
2. Inspect the CI log and the epic's artifacts for the cause.

## Expected

The fix agent's real error is surfaced in the log and the failure reason.

## Actual

A generic failure message. The underlying error was swallowed.

## Impact

Medium

## Related Tasks

- [[task-v2-review-response-orchestrator]]
- Same family as [[bug-state-store-clobbered-by-skill]] — a failure reported without the information needed to act on it
