---
id: bug-dependency-gate-read-stale-snapshot
title: Dependency gate read a snapshot the same run had already invalidated
type: bug
status: fixed
commits: ["a24e3e5"]
repos: [epic-code-gen]
decisions: [ADR-0025]
---

# Bug: Dependency gate read a snapshot the same run had already invalidated

## Summary

`check_dependencies.py` decides whether an epic may start by reading each
dependency's `jira_status` out of the on-disk epic-task file:

```python
jira_status = read_frontmatter(dep_path)[0].get("jira_status")
done = jira_status in DONE_STATUSES     # Closed, Done, Resolved
```

Those files are written **once**, at the top of a run, by
`fetch_jira_epics.py`. Everything after that point reads a photograph of Jira
taken before the run started — including the parts of the run that change Jira.

A single pipeline invocation therefore both wrote and invalidated its own
source of truth:

```
19:06:49  RHAI-760 → Done, transitioned and closed in Jira by run_pipeline.py
19:07:29  RHAI-761 starts; gate reads artifacts/epic-tasks/RHAI-760.md
          → jira_status: In Progress   (40 seconds stale)
          → exit 1, "dependencies not done"
```

Nothing was wrong with the dependency. It had been satisfied by the same
process, 40 seconds earlier, in memory the gate could not see.

## Reproduction

```python
transition_issue("s", "u", "t", "RHAI-760", "Done", tasks_dir)
check_dependencies("RHAI-761", tasks_dir)["all_done"]   # False, before the fix
```

## Expected

An epic whose only blocker was closed earlier in the same run is eligible.

## Actual

The gate refuses. The skill then records the refusal as
`codegen_outcome: failed`, which the pipeline maps to the terminal CI state
`Failed` — so RHAI-761 was not merely delayed by one cycle, it was removed from
every future cycle until its state was edited by hand in the data repo. That
second half is its own defect; see
[[bug-declined-codegen-marked-terminally-failed]].

## Impact

High, and it fires precisely where the DAG is doing its job: a chain of
dependent epics under one strategy is the case the dependency graph exists to
handle, and it is the only case where a run closes something another epic is
waiting on. Independent epics never hit it.

## Fix

Keep the snapshot in step with the transitions the run performs.
`sync_epic_task_jira_status()` in `run_pipeline.py` writes the new status back
to `artifacts/epic-tasks/<KEY>.md`, and `transition_issue()` calls it on every
successful transition. All nine epic-level call sites pass the directory; the
two strategy-level sites do not, because strategy keys have no epic-task file
(the helper no-ops on a missing file rather than treating it as an error).

The narrower alternative — have `check_dependencies.py` query Jira live —
was rejected: it puts a network call in a gate that runs once per epic, and it
leaves every *other* reader of the snapshot still stale.

Regression coverage in `tests/test_run_pipeline.py`,
`TestSyncEpicTaskJiraStatus`, including the end-to-end case
`test_dependent_gate_passes_after_transition`, which closes a dependency
through `transition_issue` and then asserts the real
`check_dependencies` gate opens.

## Related

- [[bug-declined-codegen-marked-terminally-failed]] — what turned this
  one-cycle delay into a permanent stall.
- [[bug-clone-fault-marks-epic-failed]] — same shape: an environment or timing
  fault recorded as an epic-level failure, against ADR-0025.
