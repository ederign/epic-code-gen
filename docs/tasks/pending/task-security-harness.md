---
id: task-security-harness
title: Security harness
type: task
status: pending
repos: [epic-code-gen]
jira: RHAIFIRST-193
---

# Task: Security harness

## Goal

Establish a security review dimension and fix the known injection surface.

## Context

Generated code goes into other teams' repositories, and the pipeline itself runs shell commands built from repo-derived strings. Neither is currently reviewed for security.

## Acceptance Criteria

- [ ] Command injection in `validate_target.py` fixed (RHAIFIRST-194)
- [ ] Decide whether security is a scored dimension or an advisory verifier
- [ ] Secrets handling reviewed end to end

## Files Likely Involved

- `scripts/validate_target.py`
- `.claude/agents/`

## Status

Pending.

## Notes

RHAIFIRST-194 is the concrete child: `shell=True` subprocess calls in `validate_target.py`. Note the tension with [ADR-0022] — adding a scored dimension means re-deriving the calibrated weights, which is why an advisory verifier ([ADR-0028]) may be the better shape.
