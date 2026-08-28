---
id: bug-push-results-overwrote-state
title: push-results.py overwrote the state machine's metadata
type: bug
status: fixed
repos: [epic-code-gen-pipeline]
commits: ["ddc038e", "3bbcd2d"]
decisions: [ADR-0014]
---

# Bug: push-results.py overwrote the state machine's metadata

## Summary

`push-results.py` copied the skill's `run-metadata.yaml` over the data repo's copy, destroying the pipeline-owned fields — the pipeline-repo half of RHAIFIRST-374.

## Reproduction

1. Complete a codegen run so the skill writes its own `run-metadata.yaml`.
2. Let `after_script` run `push-results.py`.
3. Diff the data repo's state file against what the pipeline wrote during the run.

## Expected

The skill's fields are merged in; pipeline-owned fields survive.

## Actual

Whole-file overwrite. The pipeline saw no status, treated the epic as Pending, and regenerated work that already had a PR.

## Impact

Critical

## Evidence

Fixed by `merge_state_file()` with `PIPELINE_OWNED_KEYS`, plus rewriting a legacy `status` holding a `CODEGEN_OUTCOMES` value into `codegen_outcome`. `copy_epic_artifacts` now excludes `run-metadata.yaml` from its `copytree` and merges it separately. Pinned by five tests in `TestStateFileIsMergedNotOverwritten`.

## Related Tasks

- [[bug-state-store-clobbered-by-skill]]
- [[M5-state-integrity]]
- The merge logic is **deliberately duplicated** across the repo boundary and must be kept in sync by hand — see [ADR-0014]
