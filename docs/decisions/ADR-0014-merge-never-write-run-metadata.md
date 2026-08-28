---
id: ADR-0014-merge-never-write-run-metadata
title: Merge, never write, run-metadata.yaml
type: adr
status: accepted
repos: [epic-code-gen, epic-code-gen-pipeline]
jira: RHAIFIRST-374
commits: ["e03689c", "ddc038e"]
decisions: [ADR-0013, ADR-0005]
---

# ADR-0014: Merge, never write, `run-metadata.yaml`

## Status

Accepted (2026-07-29, RHAIFIRST-374).

## Context

`run-metadata.yaml` has **two producers in a single run**, in two different repos:

1. `run_pipeline.py` writes state live during the run (`save_epic_state`, artifact copying).
2. `push-results.py` writes it again from `after_script`, merging the skill's output into the data
   repo copy.

Plus the skill itself writes its own summary fields. Every one of these was a whole-file write.

The second write destroyed the first. Fields lost from RHAI-74: `current_version`, `max_iterations`,
`pr_state`, `timestamps`, `scores`. RHAI-76 additionally lost `strategy_key` and `target_branch` —
and used a *third* field layout again (`scores_by_dimension`, `pr_note`, `started_at`/`completed_at`),
so the skill's output was not even self-consistent between two epics in the same run.

`ddc038e` patched one direction of this a month earlier. It was not enough, because the rule was a
convention rather than an enforced invariant.

## Decision

**Never write the file whole. Always merge.**

- In `epic-code-gen`: `artifact_utils.merge_run_metadata()`, or the
  `frontmatter.py merge-run-metadata` CLI, which rejects `status=`.
- In `epic-code-gen-pipeline`: `push-results.py:merge_state_file()`, which refuses to let the
  incoming document overwrite `PIPELINE_OWNED_KEYS` = `status`, `status_normalized_from`,
  `current_version`, `max_iterations`, `pr_state`, `timestamps`, `scores`, `blocked_by`,
  `failure_reason`, `tooling_missing`. A legacy `status` holding a `CODEGEN_OUTCOMES` value is
  rewritten to `codegen_outcome` rather than dropped.

`copy_epic_artifacts` explicitly excludes `run-metadata.yaml` from its `copytree`, then merges it
separately — the one file that must never be copied.

**The duplication is deliberate.** `push-results.py` cannot import `artifact_utils`: the two repos are
cloned to different paths at run time (`/tmp/data-repo` and `/tmp/claude-workdir`) and neither is on
the other's path. The docstring in `push-results.py` says so explicitly. It is a knowing trade of DRY
for a working deploy ([ADR-0005]).

## Consequences

### Positive

- The deadlock class is closed at the write boundary, not by asking producers to behave.
- Five tests in `tests/test_push_results.py::TestStateFileIsMergedNotOverwritten` pin the behavior,
  including `test_pipeline_fields_survive` and `test_legacy_status_becomes_codegen_outcome`.
- Recovery is built in: old corrupt files are repaired on the next merge rather than needing a
  migration.

### Negative

- **Two copies of the ownership list must be kept in sync by hand across two repos.** Nothing
  enforces it; a field added to `PIPELINE_OWNED_KEYS` in one repo and not the other reopens the bug
  quietly. This is the single most fragile seam in the system.
- `merge_run_metadata` validates only two rules; everything else is free-form and type-inferred, so
  schema drift continues unchecked (four generations coexist).
- Merge semantics are last-write-wins per key, with no conflict detection. Two writers setting the
  same non-owned key still silently race.
