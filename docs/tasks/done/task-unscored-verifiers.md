---
id: task-unscored-verifiers
title: Add wiring and interaction verifiers
type: task
status: done
repos: [epic-code-gen]
commits: ["5e19a14", "d0f2a2d"]
decisions: [ADR-0028]
---

# Task: Add wiring and interaction verifiers

## Goal

Catch defects the four structural dimensions provably miss, without disturbing the weights.

## Context

Code can pass architecture, tests, lint, and intent and still not work: a handler nothing calls, a callback race, a missing switch branch.

## Acceptance Criteria

- [x] `wiring-verifier` traces trigger -> chain -> outcome per AC
- [x] `interaction-verifier` traces user interactions and enum/branch completeness
- [x] Both dispatched in parallel with the scored reviewers
- [x] Neither affects the score; findings feed triage

## Files Likely Involved

- `.claude/agents/wiring-verifier.md`
- `.claude/agents/interaction-verifier.md`
- `scripts/review_cycle.py`

## Status

Done.

## Notes

Running on 20 and 19 epic-versions respectively. Advisory findings can be ignored, and advisory signals in this system have a track record of being ignored. Neither is documented in README.md or CLAUDE.md.
