# Project Plan

Navigation index for the [work ledger](AGENTS.md#2-the-ledger). This file links out; it does not
hold content of its own. Process rules live in [`AGENTS.md`](AGENTS.md).

**Initiative:** [RHAIFIRST-168](https://redhat.atlassian.net/browse/RHAIFIRST-168) — Epic Code
Generation — Hardening & Production Rollout.

---

## Where we are

Out of POC. The system has processed 24 epics across 7 target repos and landed 5 merged PRs, with
score progressions like 2.4 → 4.9 → 7.2 → 9.4 over four review iterations. What it lacks is not
capability but **engineering discipline**: until this ledger there were no ADRs, no architecture
docs, no CI on this repo, and no link between a code change and a recorded reason.

Current focus: repo hygiene and process, then the open review-gate defects
([M6](docs/milestones/)) that make a passing score less trustworthy than it looks.

---

## Milestones

| Milestone | Jira | Status |
|---|---|---|
| [M1 — POC validation](docs/milestones/) | RHAIFIRST-136 | Closed |
| [M2 — CI pipeline & dashboard](docs/milestones/) | RHAIFIRST-200 | Closed |
| [M3 — Jira automation](docs/milestones/) | RHAIFIRST-208 | Closed |
| [M4 — Review-response pipeline](docs/milestones/) | RHAIFIRST-212 | Closed |
| [M5 — State integrity](docs/milestones/) | RHAIFIRST-374/375/376 | Closed |
| [M6 — Review-gate hardening](docs/milestones/) | RHAIFIRST-391/392/393 | **Open** |
| [M7 — Engineering process](docs/milestones/) | — | **Open** |

---

## Active tasks

- [`docs/tasks/current/`](docs/tasks/current/) — nothing claimed right now.

Pick up work from [`docs/tasks/pending/`](docs/tasks/pending/). See
[AGENTS.md §5](AGENTS.md#5-workflow) for how to claim it.

---

## Open bugs

Highest impact first. Full list in [`docs/bugs/open/`](docs/bugs/open/).

| Bug | Impact | Jira |
|---|---|---|
| Review gate is advisory — PRs open from unreviewed versions | Critical | RHAIFIRST-391 |
| Baseline target-repo check failures scored as bad code (both repos tried) | High | RHAIFIRST-392 |
| Failed review-response cycle marks comments processed, dropping feedback | High | RHAIFIRST-393 |
| Multi-strategy runs lose the run record for all but the last strategy | High | *needs one* |
| `shell=True` command injection in `validate_target.py` | High | RHAIFIRST-194 |
| `make test` always fails (test-integration collects nothing) | Medium | *needs one* |
| `max_iterations` defaults to 3 in one path and 10 in five others | Medium | *needs one* |

Jira issues are opened [on demand](AGENTS.md#companion-jira--on-demand), so *needs one* means "not yet
visible outside this repo" — not that it is untracked.

---

## Decisions

All ADRs: [`docs/decisions/`](docs/decisions/).

The load-bearing ones, if you read only five:

- **ADR-0013** — nine CI states; `status` vs `codegen_outcome`, one owner per field.
- **ADR-0014** — merge, never write, `run-metadata.yaml`.
- **ADR-0022** — reviewers classify severity; Python computes the score.
- **ADR-0025** — `unrunnable` ≠ `failed`.
- **ADR-0027** — reviewers dispatched without `agentType`, so `tools:` is documentation.

---

## Architecture

[`docs/architecture/`](docs/architecture/) — start with the
[system overview](docs/architecture/01-system-overview.md), then the
[state machine](docs/architecture/02-pipeline-state-machine.md) and
[artifact contracts](docs/architecture/03-artifact-contracts.md).

---

## Log

[`docs/notes/session-log.md`](docs/notes/session-log.md) — dated activity, 2026-06-22 onward.
