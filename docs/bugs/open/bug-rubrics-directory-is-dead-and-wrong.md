---
id: bug-rubrics-directory-is-dead-and-wrong
title: rubrics/ is dead code that contradicts the live calibration
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0021, ADR-0029]
---

# Bug: rubrics/ is dead code that contradicts the live calibration

## Summary

`rubrics/` holds 5 files and 424 lines of reviewer calibration that nothing loads, and whose content is actively wrong. A reader who finds it first gets the opposite of current rules.

## Reproduction

1. `grep -r rubrics/ --include='*.py' --include='*.md' .` — no references outside the directory itself.
2. Compare its stated weights against `score_reviews.DIMENSION_WEIGHTS`.

## Expected

One source of calibration truth: `.claude/agents/`.

## Actual

`rubrics/` claims architecture 20% (real: 30%), tests 25% (real: 30%), intent 25% (real: 20%), a `patterns` dimension at 10% that does not exist in `DIMENSION_WEIGHTS`, and `Model: sonnet` — contradicting [ADR-0029], which removed all sonnet references.

## Impact

Medium

## Evidence

Worse than merely unused: it is the kind of stale documentation that gets trusted because it looks authoritative and specific. Superseded by `13e55e0` → `daee4d7` → `f601ef2`, which moved calibration into the agent definitions.

## Related Tasks

- [[task-deterministic-scoring]]
- [[M7-engineering-process]]
- Fix: delete the directory. Tracked as [[task-delete-dead-code]]
