---
id: bug-baseline-check-failures-scored-as-epic
title: Pre-existing target-repo check failures are scored as bad code, and mask real findings behind them
type: bug
status: open
repos: [epic-code-gen]
jira: RHAIFIRST-392
decisions: [ADR-0023, ADR-0025]
---

# Bug: Pre-existing target-repo check failures are scored as bad code, and mask real findings behind them

## Summary

`validate_target.py` runs a repo's aggregate check targets and the reviewers score whatever comes back, with no notion of whether the same check already failed before the epic touched anything. A repo whose `make lint` is red on `main` therefore fails every epic generated against it, for a fault no amount of code generation can fix.

## Reproduction

1. Pick a target repo whose `make lint` fails on a pristine checkout of `main`.
2. Generate any epic against it.
3. Observe the lint dimension carry a Critical for a failure the diff did not cause.

## Expected

A check that fails identically on the base commit is attributed to the repo, not the epic — and does not prevent the later sub-targets from running.

## Actual

The baseline failure is scored as the epic's defect, caps the lint dimension at 5 ([ADR-0023]), and because GNU make stops at the first failing prerequisite, the genuine findings that would have run afterwards are never surfaced at all.

## Impact

High

## Observed incident

RHAI-68 / RHAISTRAT-1961 against `opendatahub-io/pipelines-components`, 2026-07-30, job 15632649803. PR #194.

`make lint` exits 2 because `ruff format --check` cannot parse three notebook templates:

```
error: Failed to parse .../notebook_templates/classification_notebook.ipynb:23:3:14
error: Failed to parse .../notebook_templates/regression_notebook.ipynb:20:3:14
error: Failed to parse .../notebook_templates/timeseries_notebook.ipynb:15:1:1
```

None of the three is touched by the diff (12 files, all under `components/data_processing/automl/`, `components/training/automl/`, and `pipelines/training/automl/`).

## Evidence

**Reproduced on a pristine checkout** of base `b3c46d6` with the repo's pinned `ruff==0.15.2` — identical three errors, `375 files already formatted`, exit 2. The breakage is upstream's, not the epic's.

**It cost the epic a passing score.** `v4/scores.json`: architecture 9.5, tests 7.5, **lint 4.5**, intent 9.5 → weighted average **7.9**, verdict **fail**. The lint dimension carries exactly one Critical, and that Critical is the baseline failure.

This is the same family as the `unrunnable` vs `failed` distinction ([ADR-0025]) — but that guard only covers checks that could not *execute*. Here the check executes fine and fails for reasons the epic did not cause, so nothing catches it.

## Update 2026-07-31 — cross-repo, and it bites two code paths

A second instance on `opendatahub-io/odh-dashboard` (recorded as a comment on RHAIFIRST-392) changes the
shape of this bug in two ways.

**It is not one repo's problem.** Two of the two target repos tried so far fail their own aggregate check
on `main`, by *different* mechanisms:

| Repo | Mechanism |
|---|---|
| `pipelines-components` | `make lint` → `ruff format --check` cannot parse three notebook templates; GNU make fail-fast then hides later sub-targets |
| `odh-dashboard` | `eslint --max-warnings 0` turns the repo's pre-existing warning debt into a hard failure — no make fail-fast involved |

So a baseline comparison cannot rely on make semantics; the general case is "this check was already red",
whatever the tool.

**It bites in two code paths, not one.** The odh-dashboard instance failed through `run_validation` in
`review_response.py`'s retry loop — not through the reviewer scoring path that RHAI-68 hit. The baseline
comparison is therefore needed in **both** places, or a fix to scoring alone will leave the
review-response cycle still failing on inherited breakage.

**A workaround already happened inside the pipeline, and needs a policy answer.** RHAI-68's fix agent
resolved the `pipelines-components` instance by committing `7f62a5148e`, excluding the notebook templates
from ruff. That unblocked the epic — by **rewriting the target repo's lint configuration**. It is a
defensible change a human might well make, but the pipeline made it autonomously to get past a failure the
epic did not cause, and it is outside the diff scope [ADR-0032] otherwise enforces. Whether an agent may
edit a target repo's lint config to unblock itself should be an explicit decision, not an emergent one.

## Related Tasks

- [[task-toolchain-preflight]]
- [[M6-review-gate-hardening]]
- Likely fix: capture a baseline validation run at `BASE_SHA` and diff findings against it — in both
  the scoring path and `review_response.run_validation`
- [[bug-failed-cycle-still-marks-comments-processed]] (RHAIFIRST-393) — `Related` in Jira; a cycle
  failing on inherited breakage is how that bug gets triggered
- Needs a policy decision: may an agent edit a target repo's lint config to unblock itself?
