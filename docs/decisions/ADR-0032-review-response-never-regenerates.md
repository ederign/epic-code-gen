---
id: ADR-0032-review-response-never-regenerates
title: Review response commits on top; never regenerates
type: adr
status: accepted
repos: [epic-code-gen]
jira: RHAIFIRST-212
commits: ["99c9bc6", "2f263da", "6aecf9b", "164d21e", "d807dca"]
decisions: [ADR-0031, ADR-0009]
---

# ADR-0032: Review response commits on top; never regenerates

## Status

Accepted (2026-07-02, RHAIFIRST-212).

## Context

Once a PR is open and a reviewer — human or bot — leaves comments, the pipeline has to respond. The
tempting implementation reuses the codegen loop: feed the comments back as requirements and regenerate.

That is wrong for a PR under review. Regenerating throws away the reviewed diff, so a reviewer who
approved three of five files has to start over; it invites unrelated churn; and it makes the PR's history
useless, because the commit under discussion no longer exists.

## Decision

A separate orchestrator, `scripts/review_response.py`, with these rules recorded at decision time:

- **Check out the existing branch from the fork and commit on top.** Never regenerate.
- **Rebase first**, every cycle ([ADR-0031]).
- **Human reviewers: always address. Bots: selective.** `config/review_config.json` lists
  `bot_reviewers` (coderabbitai, Copilot, codecov, sonarcloud, …) and `our_user`.
- **One agent handles all comments, one commit** (`review-fix-agent`) — not one agent per comment, which
  produced conflicting edits and a shredded history.
- **Lightweight post-fix check**: validation plus a `sanity-check-agent` that verifies the changes
  actually address the comments. Not a full four-dimension re-review.
- **Only touch code inside our own diff.** `compute_diff_scope` / `is_comment_in_scope` enforce it, so a
  reviewer's aside about unrelated code doesn't trigger edits.
- **Reply to every comment**, with processed IDs recorded in `pr-replies.json` so nothing is answered
  twice.

## Consequences

### Positive

- Reviewer effort is preserved; the conversation stays attached to real commits.
- Scope containment means an off-hand comment can't become a refactor.
- One commit per cycle keeps the PR history legible — visible in the data repo as `v6/`, `v7/` with a
  distinct artifact shape (`review-feedback.md`, `review-response-plan.md`, `sanity-check.md`, and
  deliberately **no** `scores.json`).

### Negative

- A second loop with its own state, budget, and failure modes. `current_version` counts these while
  `versions` counts codegen iterations, and the two diverge with no documented relationship.
- No re-scoring means a fix can degrade quality without any dimension noticing — the sanity check is much
  weaker than the review gate.
- **It hid its own failures.** Top-level `CHANGES_REQUESTED` bodies with no inline comments were dropped
  entirely (RHAIFIRST-375, fixed in `164d21e`), and the path swallowed the fix agent's error and reported
  a generic failure (`d807dca`, 2026-07-31). Both are the house failure mode: a silent no-op that reports
  success.
