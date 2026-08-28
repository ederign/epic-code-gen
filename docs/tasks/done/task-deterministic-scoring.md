---
id: task-deterministic-scoring
title: Compute review scores from findings, not reviewer judgment
type: task
status: done
repos: [epic-code-gen]
commits: ["a7326fe", "788f16f", "24d8078"]
decisions: [ADR-0022, ADR-0023]
---

# Task: Compute review scores from findings, not reviewer judgment

## Goal

Make the score reproducible arithmetic over severity classifications.

## Context

Reviewers used to report their own numbers. The same defect scored differently across dimensions and runs, and **a reviewer could write up a Critical and still award 8.5** — while a weighted average of those numbers decided whether a PR opened.

## Acceptance Criteria

- [x] `score = max(1, 10 - 5C - 1.5I - 0.5M)` computed in Python
- [x] Any Critical caps its dimension at 5, making a pass impossible
- [x] Reviewers emit findings only; no score in reviewer output
- [x] Weights architecture 30 / tests 30 / lint 20 / intent 20
- [x] All reviewers recalibrated and cross-dimension dedup added

## Files Likely Involved

- `scripts/score_reviews.py`
- `.claude/agents/`
- `tests/test_score_reviews.py`

## Status

Done.

## Notes

**The pivotal change in the project.** Score progressions became meaningful evidence afterwards (RHAI-74: 2.4 -> 4.9 -> 7.2 -> 9.4). The pressure moved rather than vanishing: classification is now the whole game, and there is still no calibration test asserting a known-Critical is classified Critical.
