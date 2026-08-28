---
id: task-test-plan-integration-epic-creator
title: Test plan integration into epic creator
type: task
status: pending
repos: [epic-code-gen]
jira: RHAIFIRST-169
---

# Task: Test plan integration into epic creator

## Goal

Have epics arrive with a test plan, so the tests dimension has an explicit target.

## Context

Today the tests reviewer infers what should be tested from the acceptance criteria. An epic carrying an explicit test plan would make AC coverage checkable rather than inferred.

## Acceptance Criteria

- [ ] Epic creator emits a test plan section
- [ ] `epic-task` frontmatter or body carries it
- [ ] `tests-reviewer` verifies against the plan, not just the ACs

## Files Likely Involved

- `scripts/fetch_jira_epics.py`
- `.claude/agents/tests-reviewer.md`

## Status

Pending.

## Notes

Upstream of this repo — the change is mostly in `epic-creator`. Listed here because the consuming side is ours.
