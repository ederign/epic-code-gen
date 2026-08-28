---
id: task-make-ledger-check-blocking
title: Flip check_ledger.py --diff from advisory to blocking
type: task
status: pending
repos: [epic-code-gen]
decisions: [ADR-0034]
---

# Task: Flip check_ledger.py --diff from advisory to blocking

## Goal

Enforce the PR companion rule in CI once the backlog is seeded.

## Context

`check_ledger.py --diff` warns rather than failing, deliberately: a blocking gate while the ledger was still being populated would have bitten every trivial fix. That justification expires once the backlog exists.

## Acceptance Criteria

- [ ] `continue-on-error` removed from the diff check in the workflow
- [ ] `Ledger: none — <reason>` escape hatch confirmed working
- [ ] A `skip-ledger` label honoured for genuine exceptions
- [ ] Team told before it starts blocking

## Files Likely Involved

- `.github/workflows/ledger.yml`
- `scripts/check_ledger.py`
- `AGENTS.md`

## Status

Pending.

## Notes

`--all` is already blocking — the ledger must stay internally consistent. Only the companion-file check is advisory. Do this once a few PRs have gone through the rule naturally, so the friction is known before it is mandatory.
