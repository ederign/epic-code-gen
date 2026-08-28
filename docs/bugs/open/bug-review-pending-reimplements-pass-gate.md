---
id: bug-review-pending-reimplements-pass-gate
title: _ci_handle_review_pending re-implements the pass gate instead of reading the computed verdict
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0022, ADR-0024]
---

# Bug: _ci_handle_review_pending re-implements the pass gate instead of reading the computed verdict

## Summary

`score_reviews.py` computes a `verdict` and writes it to `scores.json`. `_ci_handle_review_pending` ignores it and re-derives the rule itself, so two copies of the pass criteria exist and can disagree.

## Reproduction

1. Produce a version whose `scores.json` has `verdict: fail` because `validation.status` is `foreign`, but whose raw dimension scores would otherwise pass.
2. Let the state machine handle `ReviewPending`.

## Expected

The state machine reads `scores["verdict"]` — the single computed answer.

## Actual

It recomputes `avg >= 8.0 and dims_ok` with a hard-coded 6.0 floor at `run_pipeline.py:1348`. Because only the `score_reviews.py` copy fails on a foreign `validation.json`, the two can reach opposite conclusions on the same artifacts.

## Impact

High

## Evidence

This is one of the mechanisms behind [[bug-review-gate-is-advisory]]: a PR can be opened by a handler that believes the version passed, from artifacts whose recorded verdict is `fail`. The thresholds are also duplicated as literals rather than imported from `score_reviews.PASS_THRESHOLD` / `MIN_DIMENSION_SCORE`.

## Related Tasks

- [[bug-review-gate-is-advisory]]
- [[M6-review-gate-hardening]]
- Fix: read the verdict; delete the second copy of the rule
