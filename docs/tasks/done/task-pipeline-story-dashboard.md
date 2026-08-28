---
id: task-pipeline-story-dashboard
title: Pipeline Story — interactive HTML dashboard for strategy visualization
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-213
commits: ["9ba09f8", "81367c8", "099a249", "659cbfc"]
---

# Task: Pipeline Story — interactive HTML dashboard for strategy visualization

## Goal

A narrative view of a strategy's journey for demos and review.

## Context

The three operational dashboard views answer 'what is the state'. This answers 'what happened', including the agent loop structure and the epic dependency DAG.

## Acceptance Criteria

- [x] Animated DAG visualization with activity log
- [x] Per-loop timeline with an external review panel
- [x] Progressive-disclosure strategy panel with AI/human badges
- [x] Customer names and partner product references redacted

## Files Likely Involved

- `scripts/pipeline_story.py`

## Status

Done.

## Notes

Built here across ~20 commits on 07-03/04, then moved to `epic-code-gen-dashboard` (`099a249`, `659cbfc`) — it is a consumer, not part of the engine. `e092c34` redacted customer names before it was shared.
