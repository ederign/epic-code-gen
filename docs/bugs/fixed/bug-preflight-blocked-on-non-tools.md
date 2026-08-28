---
id: bug-preflight-blocked-on-non-tools
title: Toolchain preflight blocked on tokens that were not tools
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["6704253"]
decisions: [ADR-0025]
---

# Bug: Toolchain preflight blocked on tokens that were not tools

## Summary

Preflight extracts required executables from variable-expanded Makefile recipes. Its initial extraction was too broad and treated non-tool tokens as missing executables, so codegen was gated on things that did not need to exist.

## Reproduction

1. Point preflight at a repo whose lint/test recipes contain shell builtins, variables, or arguments that look like commands.
2. Run `validate_target.py --preflight`.

## Expected

Only genuine executables required by the lint/typecheck/test targets are checked.

## Actual

Exit 2 for non-tools, so no code was generated for a healthy repo.

## Impact

High

## Evidence

Narrowed to inspect only the lint/typecheck/test targets that would actually run, following prerequisites, so an unrelated `docker-build` recipe does not gate codegen. 43 tests in `tests/test_toolchain_preflight.py`.

## Related Tasks

- [[task-toolchain-preflight]]
