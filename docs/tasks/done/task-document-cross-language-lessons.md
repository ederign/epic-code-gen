---
id: task-document-cross-language-lessons
title: Document cross-language and validation lessons
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-154
commits: ["71d8ecc", "019023d", "1d23088"]
---

# Task: Document cross-language and validation lessons

## Goal

Write up what the validation runs taught, so the next phase targets the real bottleneck.

## Context

Four validation epics across three languages produced a consistent signal.

## Acceptance Criteria

- [x] Lessons captured in-repo
- [x] Findings drove the next phase's scope

## Files Likely Involved

- `README.md`

## Status

Done.

## Notes

Headline finding: **v1 quality was the bottleneck, not review accuracy.** Most epics spent three or four iterations recovering from a weak initial design, which is what motivated spec-first generation ([ADR-0016]). The write-up itself has since gone stale — see [[bug-readme-is-stale]].
