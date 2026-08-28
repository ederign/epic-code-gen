---
id: task-run-index-for-dashboard
title: Aggregate run outcomes into index.json
type: task
status: done
repos: [epic-code-gen]
commits: ["294b19f"]
---

# Task: Aggregate run outcomes into index.json

## Goal

One file summarising every run for dashboard consumption.

## Context

Per-epic `run-metadata.yaml` files are the source of truth but require a directory walk to summarise.

## Acceptance Criteria

- [x] Scans `codegen-runs/*/run-metadata.yaml`
- [x] Writes `index.json` with all runs, total, and a summary by `codegen_outcome`
- [x] Called at the end of every `/epic-codegen` run
- [x] 26 tests

## Files Likely Involved

- `scripts/run_index.py`
- `tests/test_run_index.py`

## Status

Done.

## Notes

Carries its own PyYAML-optional fallback parser, which is unreachable — `pyyaml` is a hard dependency and is baked into the image. One of six YAML parsers ([[task-consolidate-yaml-parsers]]). Also references `scores_by_dimension`, which is not the name production writes.
