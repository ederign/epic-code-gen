---
id: task-idempotent-pipeline
title: Idempotent pipeline runs and duplicate PR handling
type: task
status: done
repos: [epic-code-gen]
commits: ["2e59f0c", "da3beaf", "fb3b5dc", "1b06fbe", "de256bb"]
decisions: [ADR-0009]
---

# Task: Idempotent pipeline runs and duplicate PR handling

## Goal

Make re-running a pass safe, since re-running is how epics progress.

## Context

The convergence loop means the same epic is processed on every run. Anything not idempotent duplicates work or corrupts state.

## Acceptance Criteria

- [x] Active epics skipped; merged PRs reconciled
- [x] Duplicate PR creation handled gracefully
- [x] Completed codegen artifacts reused instead of re-running Claude
- [x] A non-zero Claude exit with artifacts present is not a failure

## Files Likely Involved

- `scripts/run_pipeline.py`
- `scripts/create_pr.py`

## Status

Done.

## Notes

`de256bb` changed artifact detection to `v*/diff.patch` rather than `run-metadata.yaml`. Artifact presence remains a weak liveness proxy for a crashed run — [[bug-artifact-presence-is-weak-liveness-proxy]].
