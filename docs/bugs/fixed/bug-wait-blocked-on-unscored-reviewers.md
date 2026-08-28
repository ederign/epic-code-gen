---
id: bug-wait-blocked-on-unscored-reviewers
title: review_cycle.py wait blocked forever on unscored reviewers
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["4f1cc62"]
decisions: [ADR-0026]
---

# Bug: review_cycle.py wait blocked forever on unscored reviewers

## Summary

`wait` waited for all six review files. If an unscored verifier never produced one, the loop blocked until the job timed out.

## Reproduction

1. Dispatch the review loop with one verifier failing to write its file.
2. Run `wait`.

## Expected

`wait` returns once the loop can proceed, and signals what is missing.

## Actual

Blocked indefinitely; the 6-hour job timed out with no review completed.

## Impact

High

## Evidence

Fixed by returning once the **scored** dimensions land, plus exit code 2 in the dispatch loop. That fix introduced the inverse problem, which is still open: [[bug-wait-returns-before-unscored-reviewers-finish]].

## Related Tasks

- [[task-review-cycle-extraction]]
- [[task-unscored-verifiers]]
