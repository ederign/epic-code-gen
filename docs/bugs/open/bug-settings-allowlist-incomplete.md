---
id: bug-settings-allowlist-incomplete
title: .claude/settings.json allowlist omits scripts the skill actually runs
type: bug
status: open
repos: [epic-code-gen]
---

# Bug: .claude/settings.json allowlist omits scripts the skill actually runs

## Summary

The permissions allowlist covers 11 scripts but not several the skill invokes, so interactive runs prompt where CI does not.

## Reproduction

1. Run `/epic-codegen` interactively without `--dangerously-skip-permissions`.
2. Observe permission prompts for scripts the skill needs.

## Expected

The allowlist matches what the skill actually invokes.

## Actual

Missing `create_pr.py`, `push_to_fork.py`, `rebase_pr.py`, `review_response.py`, `node scripts/parse_prototype.js`, and the `git`/`cp`/`mkdir`/`printf`/`find` calls SKILL.md issues.

## Impact

Low

## Evidence

Masked in CI because the wrapper passes `--dangerously-skip-permissions`, which is why this has gone unnoticed. The effect is that the interactive and CI paths have different behaviour, and the allowlist no longer documents the skill's real surface.

## Related Tasks

- [[M7-engineering-process]]
