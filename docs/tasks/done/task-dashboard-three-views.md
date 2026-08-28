---
id: task-dashboard-three-views
title: epic-code-gen-dashboard — three views on GitLab Pages
type: task
status: done
repos: [epic-code-gen-pipeline]
jira: RHAIFIRST-205
commits: ["347500f", "25ab239"]
---

# Task: epic-code-gen-dashboard — three views on GitLab Pages

## Goal

Make pipeline state legible without reading CI logs or YAML.

## Context

State lives in a git repo as YAML and JSON. That is durable but not readable.

## Acceptance Criteria

- [x] Strategy drilldown view
- [x] Jira state log view
- [x] Cost and telemetry view
- [x] Published to GitLab Pages
- [x] Triggered on codegen-run success

## Files Likely Involved

- `.gitlab-ci.yml`

## Status

Done.

## Notes

Correctly moved out of this repo to `epic-code-gen-dashboard` once it was clear it was a consumer, not part of the engine (`ebadc1e` removed the duplicate). It reads `summary.json`, `strategy-summary.json`, `run-log.jsonl`, and the OTEL files — two of which have live data quality bugs: [[bug-summary-json-double-counts-strategy]].
