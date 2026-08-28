---
id: ADR-0030-fork-based-prs-under-a-bot
title: Fork-based PRs under a bot identity
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["a0de047", "2cfab1e", "3e83c09", "5d7c799", "addaaa3"]
---

# ADR-0030: Fork-based PRs under a bot identity

## Status

Accepted (2026-06-26).

## Context

Target repos are other teams' — `opendatahub-io/odh-dashboard`, `opendatahub-io/mlflow`,
`project-codeflare/codeflare-sdk`. The pipeline cannot push branches directly to them: it has no write
access, and even with access, an automated agent creating branches in a shared repo is an unpleasant
neighbour.

The work also needs an unambiguous author. A PR that appears to come from a human is a
misrepresentation, and one that comes from a real person's account makes them the apparent author of
code they didn't write.

## Decision

Fork, push to the fork, open the PR upstream, under a dedicated bot identity.

- **Fork owner**: `dora-the-ai-coder`, the default (`2cfab1e`, `3e83c09`), overridable via
  `--fork-owner`.
- `ensure_fork()` creates the fork if absent; `sync_fork()` + upstream fetch run before branching
  (`addaaa3`) so the branch is based on current upstream, not a stale fork.
- Git identity is derived from the GitHub token (`5d7c799`) — no hardcoded author.
- Branch is `epic/<EPIC_ID>`, so the Jira key is legible from the branch name.
- The PR uses the **target repo's own PR template** and its detected default branch (`4169f06`), with
  compliance handled in `create_pr.py` (`19abb33`).
- Token-embedded remote URLs are sanitized out of any error output (`ba23d02`).

## Consequences

### Positive

- No write access needed on any target repo. Onboarding a new target is a fork, not a permissions
  request.
- Provenance is honest: every PR is visibly from the bot. Nine real PRs across seven repos, five
  merged.
- Honoring the target repo's PR template makes the PR read like a native contribution rather than an
  automated dump.
- The fork is a scratch space — a bad branch can be force-pushed or deleted without touching upstream.

### Negative

- The bot account is a shared credential and a single point of failure; its token is in CI variables
  for every run.
- Fork state can drift from upstream, which is why sync-before-branch had to be added and why rebasing
  every review cycle became necessary ([ADR-0031]).
- GitHub API rate limits apply to one account across all strategies — flagged as a pitfall in
  `FOREDER.md` and not yet hit.
- `da3beaf` had to handle duplicate PR creation gracefully: the convergence loop ([ADR-0009]) can
  reach the PR-creation step twice for the same branch.
