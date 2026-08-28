---
id: task-pattern-discovery-expansion
title: Expand pattern discovery and enforce it before design
type: task
status: done
repos: [epic-code-gen]
commits: ["d3a5a24", "37a1d67", "9b65e8c", "69b74cf", "c58f98a"]
decisions: [ADR-0018]
---

# Task: Expand pattern discovery and enforce it before design

## Goal

Gather enough evidence about the target repo that the design is derived rather than invented.

## Context

Architecture is the highest-weighted dimension at 30%, and it measures conformance to conventions that only exist in the repo. One reference file is not a convention.

## Acceptance Criteria

- [x] 7a explicit refs, 7b concept search, 7c target + 5-10 siblings + sibling dirs + callers, 7d conventions docs
- [x] All agent-readiness files scanned (CLAUDE.md, AGENTS.md, .cursorrules, GEMINI.md, COPILOT.md, CONVENTIONS.md, CONSTITUTION.md)
- [x] No cap on convention lines read
- [x] Discovery completes **before** brainstorming is dispatched

## Files Likely Involved

- `.claude/skills/epic-codegen/SKILL.md`

## Status

Done.

## Notes

`9b65e8c` is the important one: without enforced ordering the design was invented first and evidence found afterwards. Enforcement is still a prompt instruction, not a mechanism.
