---
id: ADR-0001-artifacts-as-gitignored-filesystem-tree
title: Artifacts as a gitignored filesystem tree
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["ae79932"]
decisions: [ADR-0008]
---

# ADR-0001: Artifacts as a gitignored filesystem tree

## Status

Accepted (2026-06-22).

## Context

A codegen run produces a lot of intermediate state: the epic body, the strategy doc, a spec, a
plan, a diff per version, four to six review files per version, a scores file, validation output,
revision notes. All of it needs to be readable by the next step, auditable afterwards, and
survivable across a context compaction or a crashed subagent.

The candidates were a database, a single structured blob per run, or plain files in directories.

The dominant constraint is that **the primary consumers are agents with tools, not code**. An agent
can `Read` a file, `Glob` a directory, and `Grep` for a heading. It cannot query SQL without being
handed a client, and it burns context re-serializing a blob to change one field.

## Decision

Artifacts live in a plain directory tree under `artifacts/`, which is gitignored:

```
artifacts/
  epic-tasks/<EPIC_ID>.md            epic body + frontmatter
  strategies/<STRAT>.md              strategy doc from Jira
  codegen-runs/<EPIC_ID>/
    run-metadata.yaml                state
    codegen-spec.md, codegen-plan.md
    v1/ v2/ …                        one directory per iteration
    final-diff.patch
```

One concern per file. Directory names carry meaning (`v3/` is the third iteration). Nothing is
overwritten across iterations — a new version gets a new directory.

`artifacts/` is gitignored because it is per-run scratch on a throwaway CI container. Durability is
a separate concern, solved by pushing to the data repo ([ADR-0008]).

## Consequences

### Positive

- Any agent can inspect any step with `Read`/`Glob` and no extra tooling.
- Iterations are diffable against each other, which is what made score progressions like
  2.4 → 4.9 → 7.2 → 9.4 legible as evidence rather than just a final number.
- A partially complete run is still useful: `de256bb` uses the presence of `v*/diff.patch` to
  detect real work after a non-zero exit.
- No schema migration. Adding a file type costs nothing.

### Negative

- No integrity guarantees. Nothing stops two writers from racing on one file, and that is exactly
  what happened to `run-metadata.yaml` ([ADR-0014], RHAIFIRST-374).
- No validation at the boundary. Free-form YAML means four generations of `run-metadata.yaml`
  schema now coexist in the data repo.
- Growth is unbounded and unpruned. Versions accumulate forever by design; the data repo is 33 MB
  for 24 epics, 13.7 MB of it three OTEL files. Tracked as a pending task.
- "Read the artifacts to find out what happened" scales poorly for a human. That gap is what the
  dashboard and this ledger exist to fill.
