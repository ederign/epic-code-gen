---
id: task-add-tests-for-untested-modules
title: Add tests for jira_utils, frontmatter, state, and parse_prototype
type: task
status: pending
repos: [epic-code-gen]
---

# Task: Add tests for jira_utils, frontmatter, state, and parse_prototype

## Goal

Cover the four untested modules the whole pipeline depends on.

## Context

703 tests exist, but four load-bearing modules have zero.

## Acceptance Criteria

- [ ] `jira_utils.py` (1,055 lines) — especially `markdown_to_adf` / `adf_to_markdown` round-trips
- [ ] `frontmatter.py` (338 lines) — the CLI every skill calls
- [ ] `state.py` (185 lines) — the store all long-running skills depend on
- [ ] `parse_prototype.js` (699 lines) — needs a JS test runner, which the repo has none
- [ ] A calibration test: a known-Critical review file scores 5.0

## Files Likely Involved

- `tests/test_jira_utils.py`
- `tests/test_frontmatter.py`
- `tests/test_state.py`
- `package.json`

## Status

Pending.

## Notes

`jira_utils.py` is the largest module in the repo and contains a full bidirectional Markdown↔ADF converter — the highest-risk untested surface. The calibration test matters most though: finding parsing **fails open**, so a prompt-drift regression currently looks like flawless code ([ADR-0022]).
