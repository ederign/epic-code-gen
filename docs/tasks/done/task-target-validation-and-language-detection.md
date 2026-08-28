---
id: task-target-validation-and-language-detection
title: Target repo validation and language detection
type: task
status: done
repos: [epic-code-gen]
commits: ["0aecf6f"]
decisions: [ADR-0025]
---

# Task: Target repo validation and language detection

## Goal

Run a target repo's own lint / typecheck / test commands and report the result structurally.

## Context

Checks cannot be hardcoded: every repo defines them differently, in a Makefile or package.json.

## Acceptance Criteria

- [x] Language detected from markers (Go, Python, TS, JS, Rust)
- [x] Commands discovered from Makefile targets and package.json scripts
- [x] Structured `validation.json` with per-check results
- [x] `all_passed` false if any check is unrunnable or none discovered

## Files Likely Involved

- `scripts/validate_target.py`
- `tests/test_validate_target.py`

## Status

Done.

## Notes

The `unrunnable` vs `failed` distinction came later ([[task-toolchain-preflight]]) and is the subtlest logic in the repo. Consumers must read `all_passed`, never per-check keys.
