---
id: task-fix-otel-cost-telemetry
title: "Fix Cost and Telemetry: OTEL data never reached the data repo"
type: task
status: done
repos: [epic-code-gen-pipeline]
jira: RHAIFIRST-211
commits: ["6b47349", "6ef9fcd"]
---

# Task: Fix Cost and Telemetry: OTEL data never reached the data repo

## Goal

Get per-run Claude cost into the data repo so spend is visible per strategy.

## Context

An OTLP collector was running and writing `claude-otel.jsonl`, but the file was never persisted, so the cost view was empty.

## Acceptance Criteria

- [x] `claude-otel.jsonl` copied into the strategy directory per pass
- [x] `otel_cost_usd` extracted and written into `run-log.jsonl`
- [x] Telemetry recorded even on a no-op run
- [x] Deltas summed, so subagent usage is counted

## Files Likely Involved

- `ci-scripts/otel-collector.py`
- `ci-scripts/otel-summary.py`
- `ci-scripts/push-results.py`

## Status

Done.

## Notes

~$80 logged across 39 passes. Claude Code emits delta-temporality metrics, so summing deltas is required rather than optional. The OTEL files are also the bulk of the data repo's size.
