---
id: bug-tee-buffering-hid-ci-output
title: tee buffering meant CI showed no output until the job ended
type: bug
status: fixed
repos: [epic-code-gen, epic-code-gen-pipeline]
commits: ["74a1fc9", "268769b"]
---

# Bug: tee buffering meant CI showed no output until the job ended

## Summary

Codegen output was piped through `tee` to produce a log file. `tee` buffers, so a 6-hour job appeared to produce nothing until it finished.

## Reproduction

1. Run codegen in CI with output piped through `tee`.
2. Watch the job log.

## Expected

Output streams live so progress is visible.

## Actual

Nothing until the job ended — a hung run was indistinguishable from a slow one.

## Impact

Medium

## Evidence

Fixed by having `stream-claude.py` write the log file directly rather than relying on a pipe, plus forced foreground execution (`268769b`). This is also why the first attempt at [ADR-0012] was reverted — removing the outer Claude wrapper broke streaming before this was solved properly.

## Related Tasks

- [[task-ci-observability]]
