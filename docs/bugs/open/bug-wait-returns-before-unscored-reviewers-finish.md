---
id: bug-wait-returns-before-unscored-reviewers-finish
title: review_cycle.py wait returns before the unscored verifiers finish
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0026, ADR-0028]
---

# Bug: review_cycle.py wait returns before the unscored verifiers finish

## Summary

`wait` returns as soon as the four **scored** review files land. The wiring and interaction verifiers may still be running, so triage can read a truncated or absent file with no way to tell 'clean' from 'never finished'.

## Reproduction

1. Dispatch the review loop.
2. Have the wiring verifier take longer than the four scored reviewers.
3. Observe triage reading `review-wiring.md` while it is still being written.

## Expected

Triage either waits for the verifiers or is told explicitly that a verifier did not complete.

## Actual

Triage reads whatever is on disk. An empty file and a clean verification are indistinguishable, and a verifier's findings can be silently dropped.

## Impact

Medium

## Evidence

This is the inverse of the bug `4f1cc62` fixed — `wait` used to block forever on unscored reviewers ([[bug-wait-blocked-on-unscored-reviewers]]). The fix traded a hang for a race. Data-repo counts are consistent with occasional loss: `review-wiring.md` appears 20 times and `review-interactions.md` 19, against 32 for each scored dimension.

## Related Tasks

- [[task-unscored-verifiers]]
- [[task-review-cycle-extraction]]
- [[M6-review-gate-hardening]]
- Fix: wait for all six with a per-reviewer timeout, and record a distinct 'did not complete' state
