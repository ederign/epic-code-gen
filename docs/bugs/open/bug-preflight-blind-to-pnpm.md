---
id: bug-preflight-blind-to-pnpm
title: Toolchain preflight was blind to pnpm
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0025]
---

# Bug: Toolchain preflight was blind to pnpm

## Summary

`detect_required_tools()` recognised exactly one JS package manager: it appended `yarn` when it saw
`yarn.lock`, and nothing otherwise. A pnpm repo therefore preflighted clean on an image with no
pnpm — the gate reported `ok: true` and codegen proceeded.

`discover_commands()` had the matching gap on the other side: `_discover_js_commands` hardcoded
`npm run lint` / `npm run typecheck` / `npm test` regardless of what the repo declared. So even where
pnpm *was* installed, the checks ran through the wrong manager and resolved a different dependency
tree than the repo's own CI.

Together these produce the precise failure [ADR-0025] exists to prevent: an environment fault scored
as bad code.

## Reproduction

1. Point preflight at a repo with `pnpm-lock.yaml` and `"packageManager": "pnpm@10.32.1"`, on a host
   without pnpm — `rh-forge/rh-forge-ui` on the CI image is the live case.
2. `python3 scripts/validate_target.py <repo> --preflight`

## Expected

Exit 2, `missing_tool: pnpm`, no code generated, epic stays `Ready` to retry once the image has it.

## Actual

`ok: true`, exit 0. Codegen runs. Every check then invokes `npm run …` in a pnpm-only workspace and
exits non-zero for reasons the epic did not cause, and the reviewer scores that.

## Impact

High — silently converts a missing-tool fault into a low dimension score on a real PR, which is the
same class of failure as the missing `uv` that produced `lint=5.0` ([[task-toolchain-preflight]]).

## Fix

Written, not yet committed — move to `fixed/` with the SHA once it lands.

`detect_package_manager(repo_path)` is now the single answer to "which manager does this repo want":
the `packageManager` field first (the repo's own statement of record, so a stale lockfile does not
win), then `pnpm-lock.yaml`, then `yarn.lock`, then npm. `detect_required_tools()` gates on its
result for any non-npm manager; `_discover_js_commands()` builds every command through it.

Covered by `TestDetectPackageManager` and `TestDiscoverCommandsPackageManager` in
`tests/test_toolchain_preflight.py`, plus pnpm cases in `TestDetectRequiredTools`.

Fixing detection alone leaves the gate correct and the image wrong, so `Dockerfile.ci` gained pnpm
via corepack in the same change — see [[task-per-repo-github-identity]].

## Related Tasks

- [[task-toolchain-preflight]]
- [[task-per-repo-github-identity]]
