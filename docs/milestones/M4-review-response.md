---
id: M4-review-response
title: M4 — V2 code review response pipeline
type: milestone
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-212
---

# M4 — V2 code review response pipeline

**Closed 2026-07-06.** Jira: RHAIFIRST-212.

## Goal

After V1 opens a PR, detect inline review comments from bots and humans, triage them, apply targeted fixes
as new commits on the existing branch, and reply to every comment.

## Key decisions

Recorded at the time and now [ADR-0032]:

- Check out the existing branch from the fork, commit on top — **no regeneration**
- Human reviewers: always address. Bots: selective
- One agent handles all comments, one commit
- Lightweight post-fix check (validation + sanity check), not a full re-review
- Max 5 review iterations
- Only touch code in our own diff

## Delivered in three phases

- **A** — foundation: `pr_lifecycle` enhancements, `github_utils` APIs, `clone_target` checkout
- **B** — orchestrator and agents: `review_response.py`, fix agent, sanity-check agent
- **C** — state machine integration: rewrite of `_ci_handle_pr_changes`

## Outcome

Delivered, then needed two significant repairs: top-level review bodies were silently dropped
(RHAIFIRST-375) and the path hid the fix agent's real error (`d807dca`). Both were the house failure mode.

## Tasks

- [[task-v2-review-response-foundation]]
- [[task-v2-review-response-orchestrator]]
- [[task-v2-review-response-state-machine]]
