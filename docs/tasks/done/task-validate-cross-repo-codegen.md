---
id: task-validate-cross-repo-codegen
title: Validate cross-repo codegen (RHAISTRAT-1749-E002)
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-152
commits: ["076ea82", "370a6a6"]
---

# Task: Validate cross-repo codegen (RHAISTRAT-1749-E002)

## Goal

Confirm one strategy can target more than one repository, resolved automatically.

## Context

RHAISTRAT-1749 spans `mlflow-go`, `odh-dashboard`, and `mlflow` — three repos, three languages, one strategy.

## Acceptance Criteria

- [x] Target repo resolved per epic, not per strategy
- [x] Keyword mapping in `config/repo_mapping.json` with an LLM fallback
- [x] Each epic generated against its own clone

## Files Likely Involved

- `scripts/run_pipeline.py`
- `config/repo_mapping.json`

## Status

Done.

## Notes

Resolution is keyword-first with an LLM fallback ([ADR-0007] context). Adding a repo is a mapping entry — but if its toolchain is new, it is also an image change ([ADR-0011]).
