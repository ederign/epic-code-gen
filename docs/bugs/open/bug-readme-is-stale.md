---
id: bug-readme-is-stale
title: README.md is substantially stale
type: bug
status: open
repos: [epic-code-gen]
---

# Bug: README.md is substantially stale

## Summary

The repo's front door misstates test count, iteration budget, project layout, and phase status, and documented a script that did not exist.

## Reproduction

1. Read `README.md` against the current tree.

## Expected

The README describes the system as it is.

## Actual

Claims **186 unit tests** (actual: 703). Claims **up to 3 iterations max** (actual: 10). Shows reviewer agents at `agents/` in the project root with 4 files (actual: `.claude/agents/`, 13 files). Phase status ends at 'Phase 3b in progress / Phase 4 Next', while PR lifecycle, review response, UX prototypes, and the CI state machine have all shipped. Omits the interaction verifier and the whole UX prototype subsystem.

## Impact

Medium

## Evidence

`CLAUDE.md` additionally documented `bash scripts/fetch-architecture-context.sh` with two usage examples for a script that does not exist, and a `.context/architecture-context/` directory with no consumer. That section was removed on 2026-07-31 as part of [[M7-engineering-process]]; the README itself is still stale.

## Related Tasks

- [[M7-engineering-process]]
- [[bug-max-iterations-default-disagrees]]
- Fix: rewrite the README against `docs/architecture/`, and let it link out rather than restating
