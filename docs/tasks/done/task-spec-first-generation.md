---
id: task-spec-first-generation
title: Spec-first generation via Superpowers brainstorming and writing-plans
type: task
status: done
repos: [epic-code-gen]
commits: ["ffe24ea", "d41a7c0", "3ba1751", "bbce28f"]
decisions: [ADR-0016, ADR-0019]
---

# Task: Spec-first generation via Superpowers brainstorming and writing-plans

## Goal

Produce a spec containing approach exploration and trade-offs, not a restated epic.

## Context

Template-filled specs produced weak v1 diffs: most epics burned three or four iterations climbing out of a bad design, and the review loop is better at catching defects than at redirecting an approach.

## Acceptance Criteria

- [x] `brainstorming` invoked via a dedicated subagent acting as the human partner
- [x] `writing-plans` invoked via a second subagent
- [x] Each skill isolated in its own subagent
- [x] Spec review gate validates the spec against real repo patterns before planning
- [x] Skill invocation verified; retry-then-fail, never fallback

## Files Likely Involved

- `.claude/agents/design-spec-generator.md`
- `.claude/agents/plan-generator.md`
- `.claude/agents/spec-reviewer.md`
- `.claude/skills/epic-codegen/SKILL.md`

## Status

Done.

## Notes

`bbce28f` matters more than it looks: a subagent that silently fails to invoke its skill still produces plausible output, so the labeled conversation log is the evidence the skill actually ran.
