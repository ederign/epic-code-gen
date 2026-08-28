---
id: ADR-0008-data-repo-as-state-store
title: The data repo, not Jira, is the state store
type: adr
status: accepted
repos: [epic-code-gen, epic-code-gen-pipeline-data]
jira: RHAIFIRST-204
commits: ["f46bf4a", "6fd3e5d"]
decisions: [ADR-0005, ADR-0007]
---

# ADR-0008: The data repo, not Jira, is the state store

## Status

Accepted (2026-06-30).

## Context

The pipeline needs durable per-epic state between runs: which version it is on, what scored what,
which PR exists, which review comments have been answered. The container is thrown away after every
job, so `artifacts/` cannot hold it ([ADR-0001]).

Jira is already the source of truth for eligibility ([ADR-0007]), so it is the tempting place. But
Jira cannot hold a diff, a scores file, or six review documents per version, and writing this volume
of machine state into issue fields or comments would make the issues unreadable to the humans who
depend on them.

## Decision

A dedicated git repository is the state store. Layout is strategy → epic → version:

```
<STRATEGY>/                         e.g. RHAISTRAT-2162/
  strategy-summary.json             regenerated each push
  run-log.jsonl                     append-only, one line per pipeline pass
  otel-<timestamp>.jsonl
  <EPIC>/                           e.g. RHAI-74/
    run-metadata.yaml               ← the state file the pipeline reads
    codegen-spec.md, codegen-plan.md, epic-task.md
    v1/ … v7/                       versions accumulate, never deleted
    final-diff.patch
summary.json                        cross-strategy roll-up
```

Conventions: **diffs only, never full source files.** Append-only run log. Versions accumulate.
`run-metadata.yaml` is what the pipeline reads to decide the next action per epic.

## Consequences

### Positive

- Free history, diffing, and blame on the state of every epic. Every transition is a commit.
- Trivially consumable: the dashboard just clones it. No API, no database to operate.
- Survives the container, and a wiped data repo is a recoverable situation rather than a lost one.

### Negative

- **Every manual recovery is a hand-edited YAML commit.** 39 of the data repo's 104 commits are
  humans unwedging the pipeline — `Unwedge RHAI-74/RHAI-76 from invalid 'completed' state`,
  `Restore RHAI-75 to PRCreated after a clobbered state file`, and ~12 `Clean … for re-run with
  <fix>`. This is the direct, ongoing cost of the decision.
- No locking. Two concurrent pipeline runs race; mitigated only by push-retry-with-rebase, and there
  is no `resource_group` on the job. Tracked in `docs/tasks/pending/`.
- Unbounded growth with no pruning strategy — predicted in `FOREDER.md`, now real at 33 MB.
- Two writers per run share `run-metadata.yaml`, which is the origin of RHAIFIRST-374
  ([ADR-0014]).
