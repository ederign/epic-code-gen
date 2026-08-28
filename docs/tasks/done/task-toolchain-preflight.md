---
id: task-toolchain-preflight
title: Gate codegen on toolchain preflight
type: task
status: done
repos: [epic-code-gen]
commits: ["b439623", "6704253", "e7c9dac"]
decisions: [ADR-0025]
---

# Task: Gate codegen on toolchain preflight

## Goal

Fail before generating when a required executable is missing, and never score an environment fault as bad code.

## Context

`kale`'s Makefile drives `uv run ruff`. Without `uv` the recipe exits 127, GNU make reports `Error 127`, and the reviewer scored `lint=5.0` — an environment fault charged to an epic that could not have caused or fixed it.

## Acceptance Criteria

- [x] `--preflight` checks required tools and runs nothing; exit 2 distinguishes it from exit 1
- [x] Required tools from repo markers **and** variable-expanded Makefile recipes, following prerequisites
- [x] Only the lint/typecheck/test targets inspected, so unrelated recipes don't gate
- [x] A gap flags the epic and generates nothing; status stays `Ready` to retry
- [x] 43 tests

## Files Likely Involved

- `scripts/validate_target.py`
- `scripts/run_pipeline.py`
- `tests/test_toolchain_preflight.py`

## Status

Done.

## Notes

`6704253` narrowed it after it began blocking on non-tools. `e7c9dac` verifies `uv` with `test -x` rather than executing it, because the freshly installed amd64 binary segfaults under qemu when cross-building from arm64. Covers checks that *couldn't run* — not checks that fail for reasons the epic didn't cause ([[bug-baseline-check-failures-scored-as-epic]]).
