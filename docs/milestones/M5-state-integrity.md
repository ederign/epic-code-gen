---
id: M5-state-integrity
title: M5 — State integrity
type: milestone
status: done
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
jira: RHAIFIRST-374
---

# M5 — State integrity

**Closed 2026-07-29.** Jira: RHAIFIRST-374, 375, 376.

## Goal

Stop the pipeline silently deadlocking, and stop it silently dropping review feedback.

## Context

RHAISTRAT-2162 deadlocked for two days while every run exited 0. Two epics with merge-quality PRs (9.4 and
8.6) sat at `status: completed` — a value the CI state machine had never heard of — and three dependents
stayed Blocked forever.

## Delivered

- One owner per status field, both vocabularies defined once ([ADR-0013])
- Merge, never write, `run-metadata.yaml`, with the guard duplicated across the repo boundary
  deliberately ([ADR-0014])
- Normalize foreign states on read; an unmappable state fails loudly instead of skipping ([ADR-0015])
- Rebase every review-response cycle, `--force-with-lease` ([ADR-0031])
- Top-level `CHANGES_REQUESTED` bodies handled (RHAIFIRST-375)

## Outcome

Closed. The deadlock class is shut at the write boundary. Residue: `RHAISTRAT-2352/RHAI-264` still carries
the old corrupt `status`, rescued on read rather than migrated, and the two copies of
`PIPELINE_OWNED_KEYS` must be kept in sync by hand.

## Bugs

- [[bug-state-store-clobbered-by-skill]]
- [[bug-review-bodies-silently-dropped]]

## Tasks

- [[task-rebase-epic-branches-every-cycle]]
