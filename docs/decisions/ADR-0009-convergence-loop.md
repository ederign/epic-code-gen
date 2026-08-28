---
id: ADR-0009-convergence-loop
title: "Convergence loop: one run advances each epic one step"
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["2e59f0c", "c98dbbc"]
decisions: [ADR-0006, ADR-0013]
---

# ADR-0009: Convergence loop — one run advances each epic one step

## Status

Accepted (2026-06-26 idempotence, 2026-06-30 formalized as the CI state machine).

## Context

An epic's full journey is long: generate → review → iterate → open PR → wait for human review →
address comments → merge. Parts of it depend on things outside the pipeline's control, chiefly a
human reviewing a PR. A design that tries to drive one epic to completion in a single job must block
on humans, and a job that blocks on humans for days is not a job.

## Decision

Every pipeline run is a **convergence pass**. For each epic it reads current state, takes exactly one
action, records the new state, and exits. Progress across runs, not within one.

```
run 1: Pending  → Ready            (clone, assess readiness, preflight)
run 2: Ready    → ReviewPending    (generate + review)
run 3: ReviewPending → PRCreated   (open the PR)
run 4: PRCreated → PRCreated       (no new comments: no-op)
run 5: PRChangesRequested → PRCreated  (address review comments)
run 6: PRCreated → Done            (PR merged upstream)
```

Corollaries this forces:

- **Runs must be idempotent** (`2e59f0c`). Re-running skips active epics and reconciles merged PRs.
- **A no-op is a valid, successful outcome.** Telemetry is recorded even for a pass that did nothing
  (`6b47349`).
- **Blocked is not terminal.** An epic blocked by a dependency becomes eligible in a later run once
  the blocker is Done in Jira, and falls through to codegen in the same pass (`1045c53`).

## Consequences

### Positive

- The pipeline never waits on a human. It observes that the human has acted, next run.
- Any run can be safely re-triggered, which is what makes recovery-by-re-run viable.
- Crash resilience is inherent: a lost run costs one step, not the epic.

### Negative

- Latency is measured in runs. A five-deep dependency chain needs five passes minimum, and the job
  is manually triggered — so wall-clock latency is really "how often does someone press the button".
- **A state the machine does not recognize silently stalls the epic forever**, because the natural
  failure mode of a converging loop is to keep converging on nothing. That is exactly RHAIFIRST-374:
  `SKIPPED: Unknown state: completed`, exit 0, three dependents blocked indefinitely. Fixed by
  [ADR-0015] — an unmappable state is now a hard failure.
- "It reported success" and "it made progress" are different questions, and only the second one
  matters. The run log records `actions[]` per pass so the difference is visible.
