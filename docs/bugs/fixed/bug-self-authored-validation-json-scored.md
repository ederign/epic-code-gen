---
id: bug-self-authored-validation-json-scored
title: A hand-written validation.json scored the lint dimension 8.0 while the linter was failing
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["8373536"]
decisions: [ADR-0024]
---

# Bug: A hand-written validation.json scored the lint dimension 8.0 while the linter was failing

## Summary

The lint dimension is scored from `validation.json`, which is supposed to be produced by `validate_target.py` actually running the repo's checks. Nothing verified provenance, so an agent-authored document was accepted as evidence.

## Reproduction

1. Have the skill write `validation.json` by hand instead of using `validate_target.py --out`.
2. Give it a plausible but non-conforming shape, e.g. `{"tests_total": 35, "success": true}`.
3. Run scoring.

## Expected

A document that is not genuine tool output is rejected and the verdict fails.

## Actual

Scored `lint=8.0` while Prettier was failing.

## Impact

Critical

## Evidence

Fix: `VALIDATION_DOCUMENT_KEYS = ("all_passed", "checks")` and `validation_document_status()` returning `ok`/`missing`/`foreign`/`unreadable`. `score_reviews.py` forces `verdict: fail` on `foreign` or `unreadable`; `missing` stays advisory, since absence has legitimate causes and fabrication does not. A real instance is still visible in the data repo at `RHAISTRAT-1961/RHAI-69/v1/scores.json`.

## Related Tasks

- [[task-deterministic-scoring]]
- **The guard is not sufficient** — in RHAIFIRST-391 it fired, was recorded, and was ignored: [[bug-review-gate-is-advisory]]
- [[bug-two-ways-to-produce-validation-json]]
