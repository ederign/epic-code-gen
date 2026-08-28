---
id: task-ci-observability
title: "CI observability: live streaming, heartbeat, stderr capture"
type: task
status: done
repos: [epic-code-gen, epic-code-gen-pipeline]
commits: ["4828b81", "74a1fc9", "f70fad4", "ea47f58", "18d3cb0"]
---

# Task: CI observability: live streaming, heartbeat, stderr capture

## Goal

Make a 6-hour unattended job observable rather than a black box.

## Context

Codegen output appeared only at the end of a job, or not at all. A hung run was indistinguishable from a slow one.

## Acceptance Criteria

- [x] FIFO + `stream-json` rendering with `--include-partial-messages`
- [x] `stream-claude.py` writes the log file directly (tee buffers)
- [x] Progress heartbeat every 300s tailing `tmp/progress.log`
- [x] Claude stderr and pipeline logs captured as CI artifacts
- [x] Background task timeout disabled for CI subagents

## Files Likely Involved

- `ci-scripts/run-claude.sh`
- `ci-scripts/stream-claude.py`
- `ci-scripts/run-codegen.sh`

## Status

Done.

## Notes

`74a1fc9` is the non-obvious one: `tee` buffered output, so the renderer had to own the log file. `stream-claude.py` signals completion by `SIGTERM`-ing its parent and exiting 42 — intentional and surprising, documented in `docs/bugs/wontfix/`. The file is also duplicated across two repos ([[task-deduplicate-stream-claude]]).
