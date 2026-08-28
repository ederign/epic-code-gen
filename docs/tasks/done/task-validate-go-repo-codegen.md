---
id: task-validate-go-repo-codegen
title: Validate epic-codegen on a Go repo (RHAISTRAT-1749-E001)
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-151
commits: ["d2ceb4f", "294b19f"]
---

# Task: Validate epic-codegen on a Go repo (RHAISTRAT-1749-E001)

## Goal

Run the full pipeline end to end on a real Go epic and confirm the output is mergeable.

## Context

First real target: expose `ModelConfig` on `Prompt`/`PromptVersion` in the MLflow Go SDK. This was the run that established the pipeline worked at all.

## Acceptance Criteria

- [x] Diff generated against `mlflow-go`
- [x] All four dimensions scored
- [x] Weighted score >= 8.0
- [x] Result recorded in the data repo

## Files Likely Involved

- `scripts/run_pipeline.py`
- `.claude/skills/epic-codegen/SKILL.md`

## Status

Done.

## Notes

Passed on the **first iteration** at 9.4 — 224 lines across 4 files, 6 new tests. Later merged as `mlflow-go` #21. This single result set expectations that the next several epics did not meet, which is what motivated [[task-spec-first-generation]].
