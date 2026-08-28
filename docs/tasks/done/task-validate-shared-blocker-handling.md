---
id: task-validate-shared-blocker-handling
title: Validate shared blocker handling (RHAISTRAT-1748-E001)
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-153
commits: ["46a08cd", "1045c53"]
---

# Task: Validate shared blocker handling (RHAISTRAT-1748-E001)

## Goal

Confirm an epic blocked by another epic waits, and proceeds once the blocker is Done.

## Context

Epics within a strategy form a dependency DAG built from Jira 'Blocks' links. This is what makes strategy the unit of work ([ADR-0006]).

## Acceptance Criteria

- [x] DAG built from Jira 'Blocks' links
- [x] Blocked epics classified as Blocked, not attempted
- [x] An unblocked epic falls through to codegen in the same run

## Files Likely Involved

- `scripts/fetch_jira_epics.py`
- `scripts/run_pipeline.py`

## Status

Done.

## Notes

`1045c53` added the same-run fall-through, so resolving a blocker doesn't cost an extra pass. Note the asymmetry documented in the state machine doc: this check reads the dependency's **data-repo** state, while initial eligibility reads **Jira**.
