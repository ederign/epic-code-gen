---
id: ADR-0013-one-owner-per-status-field
title: Nine CI states; one owner per status field
type: adr
status: accepted
repos: [epic-code-gen, epic-code-gen-pipeline]
jira: RHAIFIRST-374
commits: ["c98dbbc", "e03689c"]
decisions: [ADR-0009, ADR-0014, ADR-0015]
---

# ADR-0013: Nine CI states; one owner per status field

## Status

Accepted (state machine 2026-06-30; single-owner rule 2026-07-29, RHAIFIRST-374).

## Context

`run-metadata.yaml` had **three competing status vocabularies** for one field:

| Producer | Vocabulary |
|---|---|
| `run_pipeline.py` CI state machine | `Pending, Ready, Generating, ReviewPending, PRCreated, PRChangesRequested, Done, Blocked, Failed` |
| `.claude/skills/epic-codegen/SKILL.md` | `completed, exhausted, failed, error` (lowercase) |
| `artifact_utils.py` codegen-run enum | `Running, Completed, Failed, Exhausted` (capitalised) |

When `/epic-codegen` finished it wrote `status: completed`. That is not a member of `CI_STATES`, so
the dispatcher fell through every branch to `else` and returned
`SKIPPED … "Unknown state: completed"` — and exited 0.

**Observed incident.** RHAISTRAT-2162, 2026-07-28/29. RHAI-74 (PR ederign/kale#11, score 9.4,
verdict pass) and RHAI-76 (#12, 8.6) were both left at `status: completed`. Later runs reported
`0 processed, 2 skipped, 3 blocked` in ~118s. RHAI-75 was blocked by 74, RHAI-78 by 75, RHAI-77 by all
four — the whole strategy deadlocked with no error surfaced and two merge-quality PRs stranded.

## Decision

Two fields, one owner each, both defined once in `scripts/artifact_utils.py`:

| Field | Owner | Vocabulary |
|---|---|---|
| `status` | `run_pipeline.py` CI state machine | `CI_STATES` (9 values) |
| `codegen_outcome` | the `/epic-codegen` skill | `CODEGEN_OUTCOMES` = `completed, exhausted, failed, error` |

`merge_run_metadata` **raises `ValueError` if `updates` contains `status`** (verified at
`artifact_utils.py:637`) and rejects a `codegen_outcome` outside the vocabulary. The skill cannot
write `status` even by accident. The third vocabulary was retired.

`CI_TERMINAL_STATES = {"Done", "Failed"}`.

## Consequences

### Positive

- The two questions "where is this epic in the pipeline" and "how did its last codegen attempt go"
  are separately answerable, which they always were in reality.
- One definition site. A new state is one edit, not three.
- The guard is a hard error at the write, not a lint or a convention — the skill cannot regress it.

### Negative

- Legacy data still carries the corruption. `RHAISTRAT-2352/RHAI-264` sits at `status: completed`
  today; `normalize_ci_status` rescues it on read ([ADR-0015]) rather than the data being migrated.
- `PIPELINE_OWNED_KEYS` must be duplicated in `push-results.py` across the repo boundary
  ([ADR-0014]).
- The transition graph still exists only as `if/elif` in `run_pipeline.py:1206-1440`. Written down at
  last in [`../architecture/02-pipeline-state-machine.md`](../architecture/02-pipeline-state-machine.md).
- `_ci_handle_review_pending` re-implements the pass gate rather than reading the verdict
  `score_reviews.py` computed, so two copies of the rule can disagree. Open bug.
