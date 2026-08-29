---
id: bug-declined-codegen-marked-terminally-failed
title: Codegen declining to start was recorded as a terminal failure
type: bug
status: fixed
commits: ["a24e3e5"]
repos: [epic-code-gen]
decisions: [ADR-0025]
---

# Bug: Codegen declining to start was recorded as a terminal failure

## Summary

`/epic-codegen` runs a dependency gate before it generates anything. When the
gate says no, the skill stops — correctly. But it recorded that stop as
`codegen_outcome: failed`, and `_ci_handle_ready` had one branch for a codegen
that did not produce artifacts:

```python
state["status"] = "Failed"
state["failure_reason"] = "codegen failed"
```

`Failed` is in `CI_TERMINAL_STATES`. A terminal state is never revisited, so
the epic is skipped on every subsequent run, forever, until someone edits the
data repo by hand.

Refusing to start and trying and breaking are not the same event. The first is
a statement about the *world* — a dependency isn't done yet — and the world
changes between runs. The second is a statement about the epic. Only the second
justifies giving up on it.

## Reproduction

Run an epic whose dependency the gate reports as not done. In the data repo:

```yaml
status: Failed
codegen_outcome: failed
failure_reason: codegen failed
```

All three are false. Nothing failed; nothing was even attempted.

## Expected

`status: Blocked`, `codegen_outcome: blocked`, `blocked_by:` naming the
dependency — a state the next run re-examines.

## Actual

RHAI-761 was marked terminally `Failed` at 19:07:29 by a gate misfire (see
[[bug-dependency-gate-read-stale-snapshot]]) and stayed out of the pipeline
across every later invocation. The stale snapshot cost one cycle; this defect
turned that into all of them.

## Impact

High. It converts any transient, self-correcting condition into permanent
removal from the pipeline, and it does so silently — the dashboard reads
`Failed` and shows a broken epic, so the operator looks for a bug in the epic
rather than in the pipeline's bookkeeping.

## Fix

Two halves, because there are two writers.

The skill (`.claude/skills/epic-codegen/SKILL.md`) now records a gate stop as
`codegen_outcome=blocked`. `blocked` was added to `CODEGEN_OUTCOMES` in
`artifact_utils.py`, which is the single definition the `codegen-run` schema
enum and `merge_run_metadata`'s validation both derive from — so no other list
needed touching.

The pipeline (`run_pipeline.py`) reads that outcome before deciding the CI
state. `blocked` sends the epic back to `Blocked` with its `blocked_by` intact
and no `failure_reason`; anything else still yields `Failed`. This works
because `_merge_run_metadata_into_state` folds the skill's fields into the live
state dict before the branch runs.

The lowercase outcome `blocked` and the capitalised CI state `Blocked` are
deliberately distinct vocabularies over the same word, so
`read_codegen_outcome({"status": "Blocked"})` must keep returning `None` —
pinned by `test_blocked_ci_state_is_not_the_blocked_outcome` in
`tests/test_artifact_utils.py`. Behaviour is covered by
`TestCodegenDeclinedIsNotFailed` in `tests/test_ci_mode.py`.

## Related

- [[bug-dependency-gate-read-stale-snapshot]] — the misfire that exposed this.
- [[bug-clone-fault-marks-epic-failed]] — still open, and the same mistake one
  layer up: a clone or credential fault also writes terminal `Failed`. This fix
  covers the skill declining, not the environment breaking.
- ADR-0025 "unrunnable is not failed" — the principle both violate.
