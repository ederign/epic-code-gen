---
id: ADR-0025-unrunnable-is-not-failed
title: unrunnable ≠ failed; preflight gates codegen
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["b439623", "6704253", "e7c9dac"]
decisions: [ADR-0011, ADR-0024]
---

# ADR-0025: `unrunnable` ≠ `failed`; preflight gates codegen

## Status

Accepted (2026-07-29).

## Context

`kale`'s Makefile drives `uv run ruff` and `uv run pytest`. Without `uv` in the image the recipe exits
127. GNU make reports `Error 127` and exits 2 rather than propagating it, so from the outside a missing
executable is indistinguishable from a failing lint run. **A missing `uv` once produced `lint=5.0`** —
an environment fault scored as bad code, against an epic that could not have caused it and could not fix
it.

## Decision

Two mechanisms.

**1. A third outcome.** A check that could not execute is reported as `unrunnable` with `missing_tool`,
never as a plain failure. Detection reads output patterns as well as exit codes, because make launders
127. The patterns are deliberately narrow: a bare `No such file or directory` is **not** treated as
unrunnable, since a test failing on a missing fixture is a real failure.

`all_passed` is false if any check is unrunnable *or* if no checks were discovered — so consumers must
read `all_passed` and never per-check keys.

**2. Preflight.** `validate_target.py --preflight` checks that every executable the repo's checks need
is present and **runs nothing**. Exit 2 means a missing tool, distinct from exit 1 (a failing check).
Required tools come from repo markers (`uv.lock`, `yarn.lock`) *and* from variable-expanded Makefile
recipes for the exact lint/typecheck/test targets that would run, following prerequisites — so an
unrelated `docker-build` recipe doesn't gate codegen (`6704253` narrowed this after it started blocking
on non-tools).

`run_pipeline.py` gates on preflight before generating: a missing tool flags the epic and **no code is
generated**. Status stays `Ready` so it retries once the image is fixed — a missing tool is an
environment fault, not the epic's fault.

## Consequences

### Positive

- Environment faults stop costing epics their scores, and stop consuming iterations.
- Failing before generating saves an entire 6-hour codegen cycle that could only have produced a bad
  lint score.
- `Ready` + retry is the right recovery: fix the image, re-run, no manual state repair.

### Negative

- `_ci_handle_ready` returns `FAILED` while setting state to `Ready`, so `main()` exits 1 on every run
  until the image is fixed — no backoff, no alerting hook. Deliberate but unpleasant; open bug.
- Makefile introspection (variable expansion, prerequisite following) is the subtlest logic in the repo
  and only approximates what make will do.
- Narrow patterns mean false negatives: an unrunnable check that fails in an unrecognized way is still
  scored as a failure.
- **It only covers checks that could not execute.** RHAIFIRST-392 is the sibling gap: the check runs
  fine and fails for reasons the epic did not cause. Nothing catches that yet.
