---
id: M6-review-gate-hardening
title: M6 — Review gate hardening
type: milestone
status: current
repos: [epic-code-gen]
jira: RHAIFIRST-391
---

# M6 — Review gate hardening

**Open.** Jira: RHAIFIRST-391, RHAIFIRST-392, RHAIFIRST-393.

## Goal

Make a passing score mean what it says. Two open defects independently undermine it.

## The problem

Both are the same family as RHAIFIRST-374 — success reported with nothing behind it:

- **The gate does not gate.** On RHAI-69 the orchestrator authored the `review-*.md` files itself, dismissed
  a reviewer's Critical, opened a PR from a v2 that was never reviewed or scored, and estimated the scores
  in prose. Three independent guards each failed to stop it, including the `validation.json` provenance
  guard, which fired and was ignored.
- **Baseline repo failures are charged to the epic.** A target repo whose `make lint` is red on `main` fails
  every epic generated against it — and because GNU make stops at the first failing prerequisite, it also
  conceals the genuine findings that would have run afterwards.

## Why it matters

[ADR-0022] made the score arithmetic rather than judgment, which was necessary but not sufficient: the
skill still has to *call* the loop, and nothing structurally prevents it from not doing so. Until this
milestone closes, a `pass` verdict is weaker evidence than it looks.

## Bugs

- [[bug-review-gate-is-advisory]]
- [[bug-failed-cycle-still-marks-comments-processed]]
- [[bug-baseline-check-failures-scored-as-epic]]
- [[bug-review-pending-reimplements-pass-gate]]
- [[bug-wait-returns-before-unscored-reviewers-finish]]
