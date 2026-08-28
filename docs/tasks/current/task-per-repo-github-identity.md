---
id: task-per-repo-github-identity
title: Route RHAISTRAT-2671 to rh-forge-ui under a per-repo identity
type: task
status: current
repos: [epic-code-gen, epic-code-gen-pipeline]
decisions: [ADR-0035, ADR-0030, ADR-0025]
jira: RHAISTRAT-2671
---

# Task: Route RHAISTRAT-2671 to rh-forge-ui under a per-repo identity

## Goal

Make RHAISTRAT-2671's epics generate against `rh-forge/rh-forge-ui` — a private repo the shared bot
cannot reach — without moving any other strategy off the bot.

## Context

Three problems, discovered in order:

1. **The epics resolved to no repo at all.** RHAI-760 and RHAI-761 match none of the keywords in
   `config/repo_mapping.json`, so `resolve_target_repo()` returned `""` and `setup_target_repo()`
   would skip both epics silently — the same failure mode as `91692dc`.
2. **The right target was mapped under a dead name.** `ederign/openc-ui-by-agentic-sdlc` is the same
   product lineage (its `package.json` name is literally `forge-ui`) and its strategy RHAISTRAT-2565
   is Closed. Repointing it alone would not have been enough: the new epics match none of its
   keywords either.
3. **The bot cannot reach the target.** `rh-forge/rh-forge-ui` is private; `ederign` can, and
   `ederign/rh-forge-ui` already exists, so the fork flow works — under a different account.

Then a fourth, found by cloning and actually running the gate: the repo is pnpm + Node `^24.15.0 ||
>=26` with `engine-strict=true`, and the CI image was Node 22 with no pnpm. Preflight said `ok: true`
anyway — see [[bug-preflight-blind-to-pnpm]].

## Acceptance Criteria

- [x] `ederign/openc-ui-by-agentic-sdlc` retired; `rh-forge/rh-forge-ui` carries forward its keywords
      plus the ones RHAI-760/761 actually use
- [x] Both epics resolve without the LLM fallback, and no other repo's keywords collide
- [x] `identity_for_repo()` resolves `fork_owner` / `gh_token_var` / `our_user` per target; all eight
      call sites go through it
- [x] `our_user` follows `fork_owner`, so the review loop does not answer its own comments
- [x] Preflight detects pnpm; JS commands run through the declared manager
- [x] `Dockerfile.ci` on Node 26 with pnpm via corepack, without shadowing the yarn odh-dashboard needs
- [x] `setup-env.sh` documents and stores `RH_FORGE_GITHUB_TOKEN`
- [ ] Image rebuilt and pushed to `quay.io/ederignatowicz/epic-code-gen-ci`
- [ ] `RH_FORGE_GITHUB_TOKEN` set as a masked, protected GitLab CI variable
- [ ] `codegen-run` triggered with `STRATEGY_KEYS=RHAISTRAT-2671`; PRs land on `rh-forge/rh-forge-ui`

## Files Likely Involved

- `config/repo_mapping.json`
- `scripts/run_pipeline.py`
- `scripts/validate_target.py`
- `scripts/review_response.py`
- `Dockerfile.ci`
- `ci-scripts/setup-env.sh`, `ci-scripts/run-codegen.sh` (epic-code-gen-pipeline)
- `tests/test_run_pipeline.py`, `tests/test_toolchain_preflight.py`

## Status

Code complete; blocked on three manual steps that only the repo owner can do — the image push, the
CI variable, and the run itself.

## Notes

Repo readiness on `rh-forge-ui` is 10/12 against a threshold of 8, so the target itself is fine.

The identity override is the interesting part and has its own ADR: [ADR-0035]. The short version is
that identity belongs to the target repo, not to the run, because the alternative — a global
`--fork-owner` swap — would put a person's name on every other strategy's PRs.
