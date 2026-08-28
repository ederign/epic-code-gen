---
id: ADR-0017-sdd-for-implementation
title: Superpowers SDD for implementation; the orchestrator is the human partner
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["d2ceb4f", "450abd0", "c61354c"]
decisions: [ADR-0016, ADR-0019]
---

# ADR-0017: Superpowers SDD for implementation; the orchestrator is the human partner

## Status

Accepted (2026-06-23; autonomy overrides completed 2026-06-26).

## Context

Phase 2 originally dispatched implementation itself: read the plan, dispatch a subagent per task,
review, fix, repeat. That is a general problem — per-task dispatch, per-task review, fix loops, a
progress ledger, a final code review — and the Superpowers `subagent-driven-development` skill already
solves it, with more care than a bespoke loop was going to get.

The obstacle is that SDD is built for a human in the loop. It has **12 checkpoints** where it stops
and asks: pre-flight conflicts, implementer questions, `BLOCKED`, `NEEDS_CONTEXT`, plan-mandated
findings, whether to finish, and so on. An autonomous pipeline cannot stop.

## Decision

Use SDD for implementation, and make the orchestrator the human partner. **The epic's acceptance
criteria are the product owner** — every checkpoint gets a resolution derived from the epic rather
than from a person.

`SKILL.md` `## Autonomous Operation` maps all 12 checkpoints to autonomous answers (`450abd0`), plus a
clarifications table covering continuous execution, `DONE_WITH_CONCERNS`, reviewer ⚠️ marks,
fix-report validation, and the progress ledger. SDD's own final review and finishing steps are
skipped, because this pipeline has its own review phase ([ADR-0022]).

SDD artifacts land in `.target-repo/.superpowers/sdd/` and are copied into the run's version
directory afterwards (`5340f53`), so the implementation trail is preserved with the diff.

## Consequences

### Positive

- Per-task dispatch, fix loops, and the progress ledger come for free and are better tested than a
  bespoke loop would be.
- The framing — *the epic strategy IS the product owner* — is a genuinely useful discipline. It forces
  every autonomous answer to be traceable to a written AC rather than to the model's preference.
- `implementer-report.md` exists for 14 epics in the data repo.

### Negative

- **A 12-row override table is a fragile contract.** It encodes assumptions about an upstream skill's
  internal checkpoints; an upstream change silently breaks autonomy, and the failure looks like a hung
  job.
- Autonomy had to be re-asserted repeatedly (`450abd0`, `c61354c`, `18d3cb0`) — the natural behavior of
  a human-partnered skill is to wait for the human.
- The orchestrator plays two roles at once (driver and product owner), which is precisely the
  confusion that let RHAIFIRST-391 happen: an orchestrator authorized to answer on the epic's behalf
  also felt authorized to write its own review files and estimate its own scores.
- Adds `.superpowers/sdd/` state inside the target repo clone, which must be kept out of the diff.
