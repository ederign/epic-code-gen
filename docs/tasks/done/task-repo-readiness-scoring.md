---
id: task-repo-readiness-scoring
title: Repo readiness scoring
type: task
status: done
repos: [epic-code-gen]
commits: ["ae79932", "e766e5f"]
---

# Task: Repo readiness scoring

## Goal

Decide whether a target repo is a viable codegen target before spending anything on it.

## Context

Generated code is only as reviewable as the signals the repo provides. A repo with no tests and no CI cannot tell us whether generated code works.

## Acceptance Criteria

- [x] Six dimensions scored out of 12, threshold 8
- [x] Integration tests, lint in CI, CI signals, context docs, CODEOWNERS, language properties
- [x] Score recorded in run metadata

## Files Likely Involved

- `scripts/repo_readiness.py`
- `tests/test_repo_readiness.py`

## Status

Done.

## Notes

`e766e5f` softened this from a hard gate — real repos score imperfectly for reasons that don't block codegen. RHAI-68 ran at readiness 9 with `codeowners: 0`.
