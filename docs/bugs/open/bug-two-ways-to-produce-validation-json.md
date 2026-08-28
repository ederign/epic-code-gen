---
id: bug-two-ways-to-produce-validation-json
title: Two documented ways to produce validation.json, and no way to tell which is normative
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0024]
---

# Bug: Two documented ways to produce validation.json, and no way to tell which is normative

## Summary

`SKILL.md` Step 13 mandates `validate_target.py --out` and says never hand-write the file. `iteration-reviewer.md:161` instead uses `--json > …/validation.json`. Both produce authentic tool output; the guidance conflicts.

## Reproduction

1. Read `SKILL.md` Step 13.
2. Read `.claude/agents/iteration-reviewer.md:161`.

## Expected

One documented way to produce the file.

## Actual

Two, with an emphatic rule attached to only one of them.

## Impact

Low

## Evidence

Both forms pass the [ADR-0024] authenticity gate, because both are genuine `validate_target.py` output — with `--json` and no `--out`, the tool writes the JSON document to stdout (`validate_target.py:747-749`), so the redirect captures a valid file. This is **not** a case of the guard being bypassed.

One real behavioural difference, in the redirect form's favour: if the tool crashes early the redirect leaves a 0-byte file → `unreadable` → forced `fail`, whereas `--out` leaves no file → `missing` → advisory. The `--out` form's advantage is that its `Wrote <path>` confirmation goes to stderr (`:745`), so stdout stays clean for piping.

## Related Tasks

- [[bug-self-authored-validation-json-scored]]
- Fix: pick one form, state it in both places, and delete the other
