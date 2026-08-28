---
id: task-review-cycle-extraction
title: Extract the review loop into review_cycle.py
type: task
status: done
repos: [epic-code-gen]
commits: ["13d9e63", "f7da07c", "4f1cc62", "5e26193"]
decisions: [ADR-0026]
---

# Task: Extract the review loop into review_cycle.py

## Goal

Move nine steps of loop bookkeeping out of prose and into testable Python.

## Context

The loop lived in SKILL.md as instructions to a model that was simultaneously managing a 6-hour context and being compacted. Observed failures: reviewers dispatched and never waited for; the orchestrator writing review files itself; scores estimated rather than run.

## Acceptance Criteria

- [x] Subcommands prompts / wait / verify / score / triage-prompt / dispatch-context
- [x] `REVIEWERS` table owns the six reviewers, four scored
- [x] Anti-fallback guardrail: if dispatch fails, fail — do not improvise
- [x] 38 tests

## Files Likely Involved

- `scripts/review_cycle.py`
- `tests/test_review_cycle.py`

## Status

Done.

## Notes

The skill still has to *call* these in order, so the anti-fallback rule remains a prompt instruction. [[bug-review-gate-is-advisory]] is that gap being exercised. `wait` also returns before the unscored verifiers finish — [[bug-wait-returns-before-unscored-reviewers-finish]].
