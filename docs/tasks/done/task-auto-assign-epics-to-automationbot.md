---
id: task-auto-assign-epics-to-automationbot
title: Auto-assign epics and STRATs to automationbot on pipeline start
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-209
commits: ["b7db47c"]
---

# Task: Auto-assign epics and STRATs to automationbot on pipeline start

## Goal

Make it visible in Jira that the pipeline has picked up an epic.

## Context

A human watching Jira could not tell whether an epic was queued, in progress, or ignored.

## Acceptance Criteria

- [x] Epic assigned to the automation bot when processing starts
- [x] Parent STRAT transitioned to In Progress when epic work begins
- [x] Idempotent — repeated runs cause no further changes

## Files Likely Involved

- `scripts/run_pipeline.py`
- `scripts/jira_utils.py`

## Status

Done.

## Notes

Combined with PR links posted as Jira comments (`e9d023d`), this made Jira the shared human interface to an autonomous pipeline.
