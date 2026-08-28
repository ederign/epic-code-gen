---
id: task-fix-make-test-target
title: Make `make test` pass, and decide the fate of the integration marker
type: task
status: pending
repos: [epic-code-gen]
---

# Task: Make `make test` pass, and decide the fate of the integration marker

## Goal

`make test` should run the full suite and exit 0 when everything passes.

## Context

See [[bug-make-test-fails-on-empty-integration-target]]. `make test` depends on `test-integration`, which
runs `pytest -m "integration"`; nothing carries the marker, pytest exits 5, and make fails. This has been
true on `main` since the marker was introduced, while the handbook told everyone to run `make test`
before pushing.

There are two defensible fixes and the choice is a real one:

- **Delete the target and the marker.** Honest about what exists — there are no integration tests. Also
  removes the misleading `make test-integration` that looks like coverage and provides none.
- **Keep the target, tolerate empty collection.** Right if integration tests are genuinely coming;
  otherwise it preserves a target that reports nothing while looking reassuring.

If keeping it, note pytest has no native "don't fail on empty collection" flag, so the recipe needs
something like `pytest ... ; [ $$? -eq 5 ] && exit 0 || exit $$?` — or `pytest-custom-exit-code`.

## Acceptance Criteria

- [ ] `make test` exits 0 on a clean tree with all tests passing
- [ ] Decision recorded: delete the integration target/marker, or make empty collection non-fatal
- [ ] If the marker is kept, at least one test uses it — otherwise it is removed
- [ ] `AGENTS.md` and `CLAUDE.md` restored to recommending `make test` once it works
- [ ] CI runs whatever the full-suite command becomes

## Files Likely Involved

- `Makefile`
- `pyproject.toml`
- `AGENTS.md`
- `CLAUDE.md`
- `.github/workflows/ledger.yml`

## Status

Pending.

## Notes

Small fix, but it touches the instruction every contributor is given, so it is worth doing deliberately
rather than as a drive-by. Prefer deleting the marker unless someone is actually about to write
integration tests — a target that always reports success on zero tests is the same
looks-like-evidence-but-isn't pattern this project keeps fixing elsewhere ([ADR-0024]).
