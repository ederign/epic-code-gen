---
id: wontfix-merge-logic-duplicated-across-repos
title: "merge_state_file logic is duplicated across the repo boundary"
type: bug
status: wontfix
repos: [epic-code-gen, epic-code-gen-pipeline]
---

# Bug: merge_state_file logic is duplicated across the repo boundary

## Status

**Won't fix — deliberate.** Recorded so it is not "DRY-ed up" without understanding the constraint.

## Summary

`epic-code-gen-pipeline/ci-scripts/push-results.py` reimplements `merge_state_file()`,
`PIPELINE_OWNED_KEYS`, and `CODEGEN_OUTCOMES`, duplicating
`epic-code-gen/scripts/artifact_utils.py`'s `merge_run_metadata`, `PIPELINE_OWNED_KEYS`, and
`normalize_ci_status`.

The duplication is flagged in `push-results.py`'s own docstring.

## Why it is deliberate

The two repos are cloned to **separate paths at run time** — `/tmp/claude-workdir` and `/tmp/data-repo` —
and neither is on the other's `sys.path`. `push-results.py` runs in `after_script`, potentially after the
brains repo clone is gone or unusable. It cannot import from a repo it does not have.

The alternatives are worse: publish `artifact_utils` as a package (an install step and a version-skew
failure mode in the one place that must work when everything else has crashed), or vendor the file
(the same duplication, less visibly).

## What this costs

**The two copies must be kept in sync by hand, and nothing enforces it.** A field added to
`PIPELINE_OWNED_KEYS` in one repo and not the other silently reopens RHAIFIRST-374. This is the most
fragile seam in the system, and accepting it is a real trade rather than a free win.

Mitigation: five tests in `TestStateFileIsMergedNotOverwritten` pin the pipeline-repo behaviour, and
[ADR-0014] documents the coupling.

## Related

- [ADR-0014] — merge, never write
- [ADR-0005] — the three-repo split that creates the constraint
- [[bug-state-store-clobbered-by-skill]] — what happens when the guard is absent
- [[bug-push-results-overwrote-state]]
