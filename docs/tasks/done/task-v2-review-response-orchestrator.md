---
id: task-v2-review-response-orchestrator
title: V2 review response — orchestrator and agents
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-212
commits: ["2f263da"]
decisions: [ADR-0032]
---

# Task: V2 review response — orchestrator and agents

## Goal

Drive a full review-response cycle: triage, fix, validate, reply.

## Context

Regenerating a branch under review throws away reviewer effort and makes the PR's history useless. Fixes must land as commits on top of the existing branch.

## Acceptance Criteria

- [x] Existing branch checked out from the fork, never regenerated
- [x] Humans always addressed; bots selectively
- [x] Only code inside our own diff is touched
- [x] Every comment replied to, processed IDs recorded

## Files Likely Involved

- `scripts/review_response.py`
- `.claude/agents/review-fix-agent.md`
- `.claude/agents/sanity-check-agent.md`

## Status

Done.

## Notes

One agent handles all comments and makes one commit — per-comment agents produced conflicting edits and a shredded history. The post-fix check is deliberately lightweight: validation plus a sanity check, not a full four-dimension re-review.
