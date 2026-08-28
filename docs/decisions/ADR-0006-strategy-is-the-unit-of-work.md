---
id: ADR-0006-strategy-is-the-unit-of-work
title: Strategy, not epic, is the unit of work
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["5bca12a", "46a08cd"]
decisions: [ADR-0007, ADR-0009]
---

# ADR-0006: Strategy, not epic, is the unit of work

## Status

Accepted (2026-06-26).

## Context

`/epic-codegen` handles exactly one epic per run. The obvious CI design is therefore one job per
epic, triggered per epic.

But epics within a strategy are not independent. They form a dependency DAG built from Jira "Blocks"
links, and the DAG is dense in practice: in RHAISTRAT-2162, RHAI-75 is blocked by RHAI-74, RHAI-78 by
RHAI-75, and RHAI-77 by all four. Dispatching per epic means either a scheduler that understands the
DAG or a pile of jobs that mostly exit immediately as blocked.

## Decision

The operator triggers on **strategy keys** (`STRATEGY_KEYS`, space-separated). For each strategy the
orchestrator fetches all children, builds the DAG, classifies every epic's eligibility, and processes
the eligible ones in one job.

The unit of work exposed to the operator is the strategy; the unit of work inside is still one epic
at a time.

## Consequences

### Positive

- Dependency resolution happens where the dependency data is, in one place, once per run.
- An epic unblocked by its predecessor finishing becomes eligible on the *next* run automatically —
  no scheduler state ([ADR-0009]).
- One job means one clone of the target repo, one image pull, one OTEL stream per strategy.

### Negative

- A strategy is only as fast as its longest dependency chain, one link per run. A five-deep chain
  needs at least five pipeline runs.
- Job duration is unbounded by design; the timeout had to go 1h → 3h → 6h (`b1b5b56`, `ce802ea`,
  `b87fc90`) and the GitLab job timeout with it.
- A crash partway through a strategy leaves the rest unprocessed, which is what made `after_script`
  state persistence necessary (`aff11df`).
- **The multi-key path is broken today**: `pipeline-post.sh` passes `--strategy-key` per key, which
  argparse overwrites rather than appends, so only the last strategy gets its run record persisted.
  See `docs/bugs/open/`.
