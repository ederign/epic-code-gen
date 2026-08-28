---
id: bug-non-codegen-epics-processed
title: Epics outside codegen scope were processed
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["996640a"]
decisions: [ADR-0007]
---

# Bug: Epics outside codegen scope were processed

## Summary

The pipeline processed every child of a strategy, including work items from projects that are not codegen targets and epics explicitly labelled to be skipped.

## Reproduction

1. Add a child work item from an out-of-scope project to a strategy.
2. Run the pipeline.

## Expected

Out-of-scope and skip-labelled epics are excluded before any work is done.

## Actual

They were classified, cloned, and in some cases generated against.

## Impact

Medium

## Evidence

Fix added `is_codegen_project()` and `has_skip_label()` (`SKIP_LABEL`, `CODEGEN_PROJECTS`) as guards in `ci_process_epic` **before** state dispatch. Real skip reasons now visible in run logs: `"Skipped (epic-code-gen-skip)"`, `"Project not in codegen scope"`.

## Related Tasks

- [[task-jira-direct-epic-fetching]]
