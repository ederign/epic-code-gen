---
id: task-fix-state-log-run-log-jsonl
title: "Fix State Log: push-results.py never wrote run-log.jsonl"
type: task
status: done
repos: [epic-code-gen, epic-code-gen-pipeline]
jira: RHAIFIRST-210
commits: ["f954967", "6a44d8d", "7bedbb0"]
---

# Task: Fix State Log: push-results.py never wrote run-log.jsonl

## Goal

Make the state log view show real transitions.

## Context

The dashboard's Jira State Log view had nothing to render because `run-log.jsonl` was never written, and transitions were being inferred rather than recorded.

## Acceptance Criteria

- [x] `actions.json` written by `run_pipeline.py` with `from`/`to` per transition
- [x] Passed to `push-results.py` via `--actions-json`
- [x] `run-log.jsonl` appended once per pass
- [x] `from` state recovered from prior entries when `actions.json` is absent

## Files Likely Involved

- `ci-scripts/push-results.py`
- `scripts/run_pipeline.py`

## Status

Done.

## Notes

39 passes are now recorded across seven strategies. The fallback that replays prior entries to recover `from` exists because early runs predate `actions.json`.
