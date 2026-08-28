---
id: bug-iteration-reviewer-undefined-base-sha
title: iteration-reviewer.md references ${BASE_SHA}, which nothing emits
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0019]
---

# Bug: iteration-reviewer.md references ${BASE_SHA}, which nothing emits

## Summary

The triage agent's artifact-save snippet uses `${BASE_SHA}`, but `BASE_SHA` is not in its declared inputs and `review_cycle.py triage-prompt` never emits it.

## Reproduction

1. Read `.claude/agents/iteration-reviewer.md`'s `## Inputs (from prompt vars)` list.
2. Search it for `${BASE_SHA}`.
3. Search `review_cycle.py cmd_triage_prompt` for `BASE_SHA`.

## Expected

Every variable a prompt template references is declared and supplied.

## Actual

An undefined variable in a prompt template. The agent either substitutes nothing or invents a value, and the resulting diff command is wrong or empty.

## Impact

Medium

## Evidence

A direct consequence of the [ADR-0019] trade-off: isolating each agent means every input must be marshalled explicitly through prompt variables, and nothing validates that the set a template uses matches the set the dispatcher provides.

## Related Tasks

- [[task-triage-memory-and-oscillation]]
- Fix: emit `BASE_SHA` from `triage-prompt` and declare it — plus a check that template variables are all supplied
