---
id: ADR-0033-iteration-budget-and-near-miss
title: Iteration budget of 10, near-miss PR on exhaustion
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["a747951", "cf1da6e", "050732f", "f7983c9"]
decisions: [ADR-0022, ADR-0032]
---

# ADR-0033: Iteration budget of 10, near-miss PR on exhaustion

## Status

Accepted (2026-07-10).

## Context

The review loop can iterate indefinitely. Two failure modes needed bounding.

**Runaway cost.** Each iteration is a full generate-review-triage-fix cycle on opus ([ADR-0029]). An
epic that never converges burns the job's 6 hours and produces nothing.

**Oscillation.** Reviewers are not perfectly consistent between versions, so a fix for one dimension can
create a finding in another, and triage can revisit a finding it already dismissed. Observed behavior:
scores plateauing while findings rotate.

And a hard cutoff has its own problem. RHAI-64 progressed 2.6 → 2.65 → 6.1 → 6.7 → 8.2 over five
versions — genuinely converging, just slowly. Discarding a 7.9 because the budget ran out throws away
work a human would happily review.

## Decision

**Budget**: `max_iterations` defaults to **10** (`a747951`, up from 5). The review-response loop has its
own separate budget — `max_review_iterations: 5` in `config/review_config.json`.

**Exhaustion is not failure.** On running out of iterations, if the best version is a **near-miss**
(≥ 7.0, `NEAR_MISS_THRESHOLD`), open the PR anyway and say so (`cf1da6e`, handled at
`run_pipeline.py:1378`). Below that, report the best version without a PR. `f7983c9` guards the inverse:
never open a PR on an outright `fail` verdict.

**Anti-oscillation** (`050732f`): findings dismissed with a reason are carried forward in
`tmp/accepted-findings-<EPIC_ID>.json` (`[{finding, dimension, accepted_in, reason}]`) so triage cannot
relitigate them. `cf1da6e` made triage history-aware; `24d8078` added cross-dimension dedup so one defect
reported by three reviewers is one fix.

## Consequences

### Positive

- Bounded worst-case cost per epic, with a defined outcome at the bound.
- Near-miss PRs put a human in the loop at the point where the machine has stopped improving — which is
  the right handoff. `RHAI-64` reached PRCreated at 8.2 this way.
- Accepted-findings carry-forward makes triage decisions durable across versions and auditable in
  `decision-log.md`.

### Negative

- **`max_iterations` has five different defaults in the tree.** `run_pipeline.py:1375` uses `3`;
  `_init_epic_state`, `_ci_handle_pr_changes`, `review_cycle.py`, `SKILL.md`, and `artifact_utils.py` all
  use `10`. An epic whose state file predates the field gets 3 in the scoring path and 10 in the PR path.
  `README.md` still says 3. Real bug, tracked in `docs/bugs/open/`.
- 7.0 is an unvalidated threshold. Nothing measures whether near-miss PRs are actually accepted by
  reviewers more often than they are rejected.
- Ten iterations of opus is a lot of money to spend before concluding an epic won't converge; there is no
  early-abandon on a flat score progression.
