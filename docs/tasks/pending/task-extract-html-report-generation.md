---
id: task-extract-html-report-generation
title: Extract HTML report generation out of fetch_jira_epics.py
type: task
status: pending
repos: [epic-code-gen]
---

# Task: Extract HTML report generation out of fetch_jira_epics.py

## Goal

Separate fetching from rendering.

## Context

`fetch_jira_epics.py` is 1,020 lines, of which roughly **750 are `_render_*` HTML functions with inline CSS and JS** — in a module named 'fetch'. It has 45 tests, but the split makes it unclear what they cover.

## Acceptance Criteria

- [ ] Rendering moved to its own module
- [ ] `fetch_jira_epics.py` reduced to fetching, DAG building, and eligibility
- [ ] Existing 45 tests still pass, and it is clear which side each covers

## Files Likely Involved

- `scripts/fetch_jira_epics.py`
- `scripts/epic_report.py`

## Status

Pending.

## Notes

Consider whether the HTML report is still needed at all now that the dashboard exists — `epic-reports/` is gitignored and the report was the *pre-Jira* input path. Deleting beats extracting if nothing consumes it. Check before refactoring.
