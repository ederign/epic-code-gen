---
id: task-jira-direct-epic-fetching
title: Fetch epics directly from Jira with a dependency DAG
type: task
status: done
repos: [epic-code-gen]
commits: ["46a08cd", "996640a", "7d50db2"]
decisions: [ADR-0007]
---

# Task: Fetch epics directly from Jira with a dependency DAG

## Goal

Make Jira the source of truth for which epics exist and which are eligible.

## Context

The POC parsed epics out of generated HTML reports — a stale snapshot with no notion of a human closing an epic, retargeting it, or adding a blocker.

## Acceptance Criteria

- [x] Child work items fetched directly; real Jira keys as `epic_id`
- [x] Dependency DAG from 'Blocks' links, stored as `dependencies` and `blocks`
- [x] Eligibility computed from current Jira status plus the DAG
- [x] Out-of-scope projects and skip-labelled epics excluded
- [x] Status fallback aliases for workflow compatibility
- [x] 45 tests

## Files Likely Involved

- `scripts/fetch_jira_epics.py`
- `scripts/jira_utils.py`
- `tests/test_fetch_jira_epics.py`

## Status

Done.

## Notes

Eligibility is recomputed from scratch every run, so there is no internal state to drift. `7d50db2` was needed when Jira status names changed. Roughly 750 of this module's 1,020 lines are HTML report rendering, which does not belong in a module named 'fetch' — [[task-extract-html-report-generation]].
