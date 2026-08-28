---
id: bug-model-pinning-contradiction
title: run-claude.sh pins a model while three docs say agents inherit the session model
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0029]
---

# Bug: run-claude.sh pins a model while three docs say agents inherit the session model

## Summary

`ci-scripts/run-claude.sh` defaults to `--model ${CLAUDE_MODEL:-claude-opus-4-6}`, pinning a specific model, while `README.md`, `CLAUDE.md`, and `SKILL.md` all state that all agents inherit the session model with no overrides.

## Reproduction

1. Read `ci-scripts/run-claude.sh:20`.
2. Read the model-selection statements in the three docs.

## Expected

One statement of how the model is chosen.

## Actual

Both claims are in the tree and they cannot both be true. In practice CI runs whatever `run-claude.sh` pins, so the docs describe an intent the code does not implement.

## Impact

Medium

## Evidence

`527fc9d` removed all sonnet references specifically to establish the inherit-the-session rule, and `rubrics/` still says `Model: sonnet` ([[bug-rubrics-directory-is-dead-and-wrong]]) — three different answers in one repo.

## Related Tasks

- [[M7-engineering-process]]
- Fix: decide whether CI pins deliberately (and say so in [ADR-0029]) or genuinely inherits
