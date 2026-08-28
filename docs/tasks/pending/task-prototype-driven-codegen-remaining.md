---
id: task-prototype-driven-codegen-remaining
title: Prototype-driven code generation — remaining work
type: task
status: pending
repos: [epic-code-gen]
jira: RHAIFIRST-233
decisions: [ADR-0020]
---

# Task: Prototype-driven code generation — remaining work

## Goal

Finish the prototype pipeline: prerequisite parsing, deterministic extraction, and design fidelity review.

## Context

The core path shipped in [[task-ux-prototype-pipeline]] and produced its first Done epic (`RHOAIENG-72103`, 8.15). Three children remain open.

## Acceptance Criteria

- [ ] RHAIFIRST-234 — prerequisite parsing and prototype fetching from Jira
- [ ] RHAIFIRST-235 — deterministic PatternFly HTML prototype extraction
- [ ] RHAIFIRST-236 — spec/plan enrichment and design fidelity review

## Files Likely Involved

- `scripts/parse_prototype.js`
- `.claude/agents/ux-ac-extractor.md`
- `.claude/agents/intent-reviewer.md`

## Status

Pending.

## Notes

Parts of 234/235 already shipped in practice — the Jira issues predate the implementation and have not been reconciled. **Check what actually exists before starting.** Prototype detection is a regex over Jira table markup and has broken once already (`58e4bd7`).
