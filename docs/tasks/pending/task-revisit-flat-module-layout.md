---
id: task-revisit-flat-module-layout
title: Revisit the flat sys.path module layout
type: task
status: pending
repos: [epic-code-gen]
decisions: [ADR-0003]
---

# Task: Revisit the flat sys.path module layout

## Goal

Decide whether to keep the flat layout or move to a package.

## Context

[ADR-0003] records this as *Accepted, under review*. 20 modules import each other by bare name after a `sys.path.insert`, duplicated ~38 times including in all 18 test files, in two different spellings. There is no `conftest.py`.

## Acceptance Criteria

- [ ] Decide: keep, or migrate to a package with console entry points
- [ ] If keeping — at minimum add a `conftest.py` so tests stop repeating the bootstrap
- [ ] If migrating — update `Dockerfile.ci`, `run-codegen.sh`, and every `python3 scripts/x.py` invocation including those inside SKILL.md prompts
- [ ] Update [ADR-0003] either way

## Files Likely Involved

- `pyproject.toml`
- `tests/conftest.py`
- `scripts/`

## Status

Pending.

## Notes

The reason to keep it is real: CI clones the repo and runs `python3 scripts/run_pipeline.py` with no install step, so there is no stale-install failure mode. The cheap win regardless is `conftest.py`. Blocks [[task-add-lint-and-typecheck]]'s type-checking half.
