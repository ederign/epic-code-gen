---
id: 000-overview
title: Epic code generation — the arc of the work
type: plan
status: current
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
jira: RHAIFIRST-168
---

# Overview

Five phases, 2026-06-22 → present, 336 commits across three repos. This file is the map;
each phase has its own file with dates, what shipped, and what it cost.

The phases are named after what was actually being built at the time, in the order it happened.
Note that the **CI pipeline came before the review quality work** — the system was running
autonomously in GitLab before its review gate was trustworthy. Several of the sharpest defects
(RHAIFIRST-374, 391, 392) are downstream of that ordering.

| Phase | Dates | Theme | Commits |
|---|---|---|---|
| [01 — Foundation](phase-01-foundation.md) | 06-22 → 06-23 | Scaffolding, contracts, first passing epic | 19 |
| [02 — Pipeline orchestration](phase-02-pipeline-orchestration.md) | 06-26 → 06-30 | Jira-direct, fork PRs, CI state machine, three repos | 38 |
| [03 — Review response & telemetry](phase-03-review-response.md) | 07-02 → 07-04 | V2 PR-comment loop, OTEL, dashboards | 40 |
| [04 — Review quality](phase-04-review-quality.md) | 07-09 → 07-17 | Deterministic scoring, Superpowers, UX prototypes | 76 |
| [05 — Hardening](phase-05-hardening.md) | 07-21 → present | State integrity, preflight, authenticity gates | 12 |

## The through-line

Every phase after the first was driven by the same discovery in a new place: **the system reports
success it hasn't earned.**

- Phase 02 found it in state: an epic marked `completed` — a word the CI state machine had never
  heard of — was skipped on every subsequent run while the job exited 0.
- Phase 03 found it in review response: `CHANGES_REQUESTED` bodies with no inline comments were
  silently dropped, so a reviewer's objection produced no work.
- Phase 04 found it in scoring: reviewers were choosing their own numbers, and a Critical finding
  could sit inside an 8.5.
- Phase 05 is still finding it: RHAIFIRST-391 (a PR opened from a version that was never
  reviewed), RHAIFIRST-392 (a repo's pre-existing lint failure scored as the epic's bad code).

That is why the ledger's central rule is about evidence rather than format
([AGENTS.md §3](../../AGENTS.md#3-the-pr-companion-rule)). The recurring bug class in this
project is not a wrong answer — it is a confident answer with nothing behind it.

## What is not here

The `epic-code-gen-dashboard` repo has its own history and is out of scope for this ledger; it is
a read-only consumer of the data repo. See
[`../architecture/01-system-overview.md`](../architecture/01-system-overview.md) for where it sits.
