---
id: bug-make-test-fails-on-empty-integration-target
title: "`make test` always fails, because test-integration collects zero tests"
type: bug
status: open
repos: [epic-code-gen]
---

# Bug: `make test` always fails, because test-integration collects zero tests

## Summary

`make test` depends on `test-integration`, which runs `pytest -m "integration"`. No test in the suite
carries that marker, so pytest collects nothing and exits **5** (`NO_TESTS_COLLECTED`). Make treats that
as a failed recipe, so `make test` **cannot succeed** — and both `CLAUDE.md` and `AGENTS.md` instruct
contributors to run it before pushing.

## Reproduction

1. `git checkout main`
2. `make test`
3. Observe `test-unit` pass, then:

```
703 deselected in 0.07s
make: *** [test-integration] Error 5
```

## Expected

`make test` runs the full suite and exits 0 when everything passes. A target with no matching tests is a
no-op, not a failure.

## Actual

Exits non-zero every time, on every branch, regardless of test results.

## Impact

Medium

## Observed incident

Found on 2026-07-31 while verifying this ledger — the one command the handbook says to run before
pushing turned out never to have worked.

## Evidence

Confirmed pre-existing, not introduced by the ledger work. Reproduced on a **pristine `main` worktree**:

```
$ git worktree add /tmp/ecg-main main && cd /tmp/ecg-main && make test-integration
632 deselected in 0.48s
make: *** [test-integration] Error 5
```

632 deselected on `main` vs 703 on the ledger branch — consistent with 71 newly added tests and with the
same underlying failure.

Direct cause, verified:

```
$ uv run pytest tests/ -m integration -q ; echo $?
703 deselected in 0.07s
5
```

`grep -rc 'pytest.mark.integration' tests/` returns **0** on both `main` and HEAD. The marker is
registered in `pyproject.toml` and used by nothing, so the target has never had anything to run.

Because the failure is at the *end* of `make test` and the unit output scrolls past, it reads as "the
suite ran" — which is likely why it went unnoticed. `make test-unit` is green: **703 passed**.

## Related Tasks

- [[task-fix-make-test-target]] — the fix
- [[bug-repo-does-not-meet-own-standards]] — the umbrella record; this is one concrete instance
- Interim: `AGENTS.md` and `CLAUDE.md` now tell contributors to run `make test-unit`, with this bug
  cited, rather than carrying an instruction that cannot be satisfied
