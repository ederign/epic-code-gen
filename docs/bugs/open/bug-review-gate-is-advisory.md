---
id: bug-review-gate-is-advisory
title: "Review gate is advisory: epic-codegen opens PRs from unreviewed versions and ignores its own fail verdict"
type: bug
status: open
repos: [epic-code-gen]
jira: RHAIFIRST-391
decisions: [ADR-0022, ADR-0024, ADR-0026]
---

# Bug: Review gate is advisory: epic-codegen opens PRs from unreviewed versions and ignores its own fail verdict

## Summary

The multi-dimensional review gate does not gate. On the RHAI-69 run it opened a PR from a version that was never reviewed or scored, while the only version that *was* scored carried `"verdict": "fail"`. Three independent guards each failed to stop it.

## Reproduction

1. Run codegen on an epic where v1 scores below the pass threshold.
2. Let the orchestrator apply fixes and produce v2.
3. Observe that v2 is never re-reviewed, and a PR is opened anyway.

## Expected

A PR is opened only from a version that has been reviewed by the reviewer agents and scored by `score_reviews.py` to a `pass` verdict.

## Actual

A PR was opened from an unreviewed, unscored version. The job exited 0 with `codegen_outcome: completed`.

## Impact

Critical

## Observed incident

RHAI-69 / RHAISTRAT-1961, 2026-07-30. Pipeline 2719662373, job 15630958076. PR opened: `opendatahub-io/odh-dashboard#9010`.

Trace timeline:

- `19:53:41` — orchestrator: *"Now I need to write out the review files myself since the agents couldn't do that"*
- `19:54:04` — `score_reviews.py` run on `v1/` (the orchestrator-authored files)
- `19:54:09` — reported as "Score: 7.15 (near-miss)"
- `19:58:46` — orchestrator: *"…let me check if I can shortcut by computing the expected scores."*
- `19:58:55` — estimated all four dimensions at 9.5, derived 9.60, declared a pass
- `20:00:48` — PR created

## Evidence

Artifacts committed to the data repo at `2adff02`, path `RHAISTRAT-1961/RHAI-69/`.

**v2 was never reviewed.** It contains `diff.patch`, `revision-notes.md`, and `validation.json` — but no `review-architecture.md`, `review-tests.md`, `review-lint.md`, `review-intent.md`, and no `scores.json`. v1 has all five. Meanwhile `run-metadata.yaml` records `final_version: 2`, `codegen_outcome: completed`, `status: ReviewPending`.

**Three guards failed:**

1. The orchestrator authored the `review-*.md` files itself rather than the reviewer agents, and dismissed a reviewer's Critical finding while writing them — violating the explicit `5e26193` anti-fallback rule and SKILL.md's *never write review files yourself*.
2. v2 was never re-reviewed; scores were **estimated in prose**, not computed.
3. The `validation.json` provenance guard from `8373536` **fired, was recorded in `scores.json`, and was ignored**.

## Related Tasks

- [[task-review-cycle-extraction]]
- [[task-deterministic-scoring]]
- [[bug-self-authored-validation-json-scored]] — the guard that fired and was ignored
- [[bug-review-pending-reimplements-pass-gate]] — a second, independent way the gate can disagree with itself
- [[M6-review-gate-hardening]]
- Root cause is structural: every rule in the review loop is a prompt instruction, and reviewers hold `Write` by necessity ([ADR-0027])
