---
id: ADR-0015-normalize-on-read-fail-loudly
title: Normalize foreign states on read; fail loudly on the rest
type: adr
status: accepted
repos: [epic-code-gen]
jira: RHAIFIRST-374
commits: ["e03689c"]
decisions: [ADR-0013, ADR-0009]
---

# ADR-0015: Normalize foreign states on read; fail loudly on the rest

## Status

Accepted (2026-07-29, RHAIFIRST-374).

## Context

[ADR-0013] and [ADR-0014] stop *new* corruption. Two problems remain.

First, epics already stuck at `status: completed` need rescuing without a hand-written migration —
and hand-written YAML recovery commits are already 39 of the data repo's 104 commits.

Second, and more important: the original bug was not that a bad value was written. It was that a bad
value was **read and silently ignored**. The dispatcher fell through to `else`, returned
`SKIPPED: Unknown state: completed`, and the job exited 0. A converging state machine
([ADR-0009]) whose unknown-state branch is a no-op will converge on nothing, forever, reporting
success the whole way.

## Decision

Two rules on read.

**1. Normalize what can be mapped.** `normalize_ci_status()` maps legacy and foreign values onto real
CI states:

```
_FOREIGN_CI_STATES = {"exhausted": "Failed", "error": "Failed", "running": "Generating"}
"completed" → "PRCreated" if pr_url is set, else "ReviewPending"
```

`completed` is context-dependent because it means "the skill finished" — whether that implies a PR
exists is only knowable from `pr_url`. The original value is preserved in `status_normalized_from`,
so a normalization is auditable rather than invisible.

**2. Fail loudly on the rest.** An unmappable status is a **hard failure**, never a skip. Stated as a
rule in `CLAUDE.md`: *"an unmappable one is a hard failure, never a skip."*

Precisely: the dispatcher returns the `FAILED` *action* so `main()` exits 1 and the epic lands in the
summary's failed column — but it deliberately **does not write a `Failed` status to the state file**
(`run_pipeline.py:1175-1181`). The comment there explains why: *"we do not understand this document, and
overwriting it would destroy the evidence a human needs, so the run keeps failing until someone fixes
it."* Failing loudly and preserving the evidence are two requirements, and overwriting the state would
satisfy only the first.

## Consequences

### Positive

- Epics stuck by the old bug self-heal on the next run. No migration commit needed.
- The silent-deadlock class is closed structurally: there is no longer a code path where an
  unrecognized state produces a successful no-op.
- `status_normalized_from` means you can tell, later, that an epic's state was rewritten and from
  what.

### Negative

- Normalization is a compatibility shim carrying the memory of a bug. It has no expiry, and nothing
  will prompt anyone to delete it once the last legacy file is gone.
- The `completed → PRCreated | ReviewPending` fork is a heuristic. If `pr_url` is missing for an
  unrelated reason, the epic re-enters review instead of PR handling.
- **Failing loudly means failing.** `_ci_handle_ready` returns `FAILED` while deliberately leaving
  state at `Ready` on a toolchain gap ([ADR-0025]), so `main()` exits 1 on every run until the image
  is fixed — with no backoff and no alerting hook. Correct behavior, unpleasant ergonomics; tracked in
  `docs/bugs/open/`.
