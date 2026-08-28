---
id: bug-nonzero-claude-exit-read-as-failure
title: A non-zero Claude exit was read as codegen failure even when work completed
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["1b06fbe", "de256bb"]
---

# Bug: A non-zero Claude exit was read as codegen failure even when work completed

## Summary

`invoke_codegen` treated any non-zero exit from the Claude session as a failed codegen, including cases where the session had completed the work and exited oddly.

## Reproduction

1. Run codegen so that the session produces `v*/diff.patch` and then exits non-zero.
2. Observe the epic transition.

## Expected

Completed work is recognised and the epic advances.

## Actual

Marked failed; the completed diff was discarded and the epic regenerated next run.

## Impact

High

## Evidence

Fixed by treating the presence of `v*/diff.patch` as evidence of real work (`de256bb` changed detection from `run-metadata.yaml` to `v*/diff.patch`). This traded one problem for a weaker one — artifact presence is still a weak liveness proxy for a genuinely crashed run: [[bug-artifact-presence-is-weak-liveness-proxy]].

## Related Tasks

- [[task-idempotent-pipeline]]
