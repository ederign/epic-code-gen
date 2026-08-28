---
id: bug-artifact-presence-is-weak-liveness-proxy
title: A non-zero exit with any v*/diff.patch present is treated as success
type: bug
status: open
repos: [epic-code-gen]
---

# Bug: A non-zero exit with any v*/diff.patch present is treated as success

## Summary

`invoke_codegen` treats the presence of `v*/diff.patch` as evidence that codegen succeeded, even when the session exited non-zero.

## Reproduction

1. Cause a codegen session to write `v1/diff.patch` and then crash.
2. Observe the transition.

## Expected

A crashed run is distinguished from a completed one — e.g. by requiring the artifacts a complete run produces (`scores.json`, a validated `validation.json`).

## Actual

Artifact presence alone is accepted (`run_pipeline.py:614-620`), so a partial run can advance the epic to `ReviewPending` with incomplete artifacts.

## Impact

Medium

## Evidence

This was the deliberate fix for the opposite bug — a completed run being discarded because Claude exited oddly ([[bug-nonzero-claude-exit-read-as-failure]]). The trade was reasonable at the time; the residual risk is that it feeds under-populated versions into the review phase, which is one of the conditions RHAIFIRST-391 exploited.

## Related Tasks

- [[task-idempotent-pipeline]]
- [[bug-review-gate-is-advisory]]
