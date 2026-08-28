---
id: bug-reviewers-cited-patch-line-numbers
title: Reviewers cited patch line numbers instead of source line numbers
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["34b6e8d"]
---

# Bug: Reviewers cited patch line numbers instead of source line numbers

## Summary

Reviewer findings referenced positions in the diff rather than in the source files, so the fix agent could not locate what a finding was talking about.

## Reproduction

1. Generate a diff and run the reviewers.
2. Read a finding's file:line reference and try to open it in the source.

## Expected

Findings cite `file:line` in the source, resolvable by the fix agent.

## Actual

Line numbers were offsets within `diff.patch`, pointing at unrelated or nonexistent source lines.

## Impact

High

## Evidence

Made findings unactionable, so iterations were spent without closing the finding — visible as flat stretches in early score progressions.

## Related Tasks

- [[task-deterministic-scoring]]
- [[task-triage-memory-and-oscillation]]
