---
id: task-fix-command-injection-validate-target
title: Fix command injection in validate_target.py shell=True subprocess calls
type: task
status: pending
repos: [epic-code-gen]
jira: RHAIFIRST-194
---

# Task: Fix command injection in validate_target.py shell=True subprocess calls

## Goal

Stop executing repo-derived strings through a shell.

## Context

`validate_target.py` discovers check commands from a target repo's Makefile and `package.json`, then runs them. Those strings come from a cloned third-party repository.

## Acceptance Criteria

- [ ] Commands executed without `shell=True` where feasible, or explicitly argument-split
- [ ] Makefile/package.json-derived values treated as untrusted input
- [ ] Tests covering a malicious command string

## Files Likely Involved

- `scripts/validate_target.py`
- `tests/test_validate_target.py`

## Status

Pending.

## Notes

Mitigating context: the pipeline already runs arbitrary target-repo build tooling by design, so this is not the only trust boundary — but it is the one that is trivially fixable and currently undefended. Prioritise it above the broader harness.
