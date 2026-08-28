---
id: ADR-0007-jira-is-the-source-of-truth
title: Jira is the source of truth for eligibility and dependencies
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["46a08cd", "8b53239", "996640a"]
decisions: [ADR-0006, ADR-0008]
---

# ADR-0007: Jira is the source of truth for eligibility and dependencies

## Status

Accepted (2026-06-26, replacing HTML report parsing).

## Context

The POC read epics out of generated HTML status reports (`fetch_epic.py parse_report`). That works
for a demo and fails for a pipeline: the report is a snapshot, it can be stale, and it has no notion
of whether a human has since closed an epic, retargeted it, or added a blocker.

Meanwhile the humans in this process — staff engineers, product owners — already work in Jira. Any
internal eligibility store would immediately disagree with them.

## Decision

`fetch_jira_epics.py` reads directly from Jira on every run and derives:

- **Identity** — real Jira keys as `epic_id` (`RHOAIENG-72103`, `RHAI-74`).
- **Dependencies** — the DAG from "Blocks" issue links, stored both ways (`dependencies` =
  blocked-by, `blocks`).
- **Eligibility** — computed from current Jira status plus the DAG. `DONE_STATUSES` decides whether a
  blocker is resolved.
- **Scope** — `is_codegen_project()` and `has_skip_label()` exclude out-of-scope work (`996640a`).

The pipeline also writes back: status transitions (`8b53239`), PR links as comments (`e9d023d`),
assignment to the automation bot (`b7db47c`).

## Consequences

### Positive

- A human closing an epic in Jira changes pipeline behavior with no other action. Same for adding a
  blocker or a skip label.
- Eligibility is recomputed from scratch every run, so there is no internal state to drift.
- Jira becomes the shared interface between humans and the pipeline, which is what makes the
  autonomy legible to the team.

### Negative

- Hard dependency on Jira availability and on `JIRA_SERVER`/`JIRA_USER`/`JIRA_TOKEN`. No offline
  mode for the CI path.
- Coupled to Jira's workflow vocabulary. Status name changes have already broken it once, requiring
  fallback aliases (`7d50db2`).
- Jira is the source of truth for *eligibility*, but the data repo is the source of truth for *run
  state* ([ADR-0008]). Two authorities, and the boundary between them is not self-evident — the
  RHAIFIRST-374 deadlock lived exactly there.
- `jira_utils.py` is 1,055 lines including a full Markdown↔ADF converter, and has **no tests**.
