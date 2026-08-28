---
id: ADR-0035-per-repo-github-identity
title: Per-repo GitHub identity, overriding the shared bot
type: adr
status: accepted
repos: [epic-code-gen, epic-code-gen-pipeline]
---

# ADR-0035: Per-repo GitHub identity, overriding the shared bot

## Status

Accepted (2026-08-28).

## Context

[ADR-0030] settled on one bot account, `dora-the-ai-coder`, forking every target and opening every
PR. That works while every target is a public repo the bot can fork.

`rh-forge/rh-forge-ui` is private. The bot has no access to it and cannot be granted any — the org is
not ours to hand out seats in. The account that *can* reach it is a person's: `ederign`, whose
personal PAT already carries the membership.

The obvious move — pass `--fork-owner ederign` and swap `EPIC_CODEGEN_GITHUB_TOKEN` for a personal
PAT — is global. It moves *every* strategy off the bot for that run, so odh-dashboard PRs would
start arriving under a real person's name, which is exactly the misrepresentation [ADR-0030] exists
to prevent. Identity is a property of the target repo, not of the run.

## Decision

Identity resolves per target repo, from the mapping that already routes epics to repos.

`config/repo_mapping.json` entries may carry three optional fields:

```json
"rh-forge/rh-forge-ui": {
  "keywords": ["rh-forge", "forge ui", "..."],
  "fork_owner": "ederign",
  "gh_token_var": "RH_FORGE_GITHUB_TOKEN"
}
```

- `identity_for_repo(target_repo, args, mapping)` in `run_pipeline.py` is the single resolver.
  It returns `{fork_owner, gh_token_var, our_user}`, defaulting to `--fork-owner`,
  `EPIC_CODEGEN_GITHUB_TOKEN`, and `review_config.json`'s `our_user`.
- **`our_user` follows `fork_owner`** unless explicitly set. It is the account whose PR comments the
  review loop must ignore as its own. Left on the bot while the PR is authored by `ederign`, the loop
  reads the author's own comments as reviewer feedback and answers itself forever.
- The token is named, never carried. `gh_token_var` is an environment variable *name*; the value is
  read at the point of use, so nothing in the repo, the mapping, or the CI log holds a credential.
- Every call site resolves through the one function: clone, codegen invocation, PR creation, PR
  liveness check, and both review-response paths. `review_response.py` grew `--our-user` for the same
  reason.
- Slug normalisation accepts `owner/repo`, an https URL, a `git@` URL, and a trailing `.git`, because
  the value arrives in all four forms depending on the call site.

## Consequences

### Positive

- One private target does not move any other target off the bot. The default is unchanged and
  unchanged by omission: an entry with no override behaves exactly as before.
- Provenance stays honest per repo. The bot still authors public-target PRs; the personal account
  authors only the repo that requires it.
- Onboarding a private target is a mapping entry plus a CI variable — no code change.

### Negative

- A personal PAT is now in CI variables. Its blast radius is every repo that account can reach, which
  is far wider than the bot's. It should be scoped and rotated as if it were a shared secret, because
  operationally it is one.
- PRs to `rh-forge-ui` are authored by a person who did not write them. That is a knowing trade
  against [ADR-0030]'s reasoning, accepted because the alternative is not generating the code at all.
- Two identities means two rate-limit buckets and two fork namespaces to reason about when a run
  misbehaves.
- A typo'd `gh_token_var` fails at PR time, not at config load. Nothing validates that the named
  variable exists until it is needed.

## Related

- [ADR-0030] — the shared-bot default this overrides.
- [[task-per-repo-github-identity]]
