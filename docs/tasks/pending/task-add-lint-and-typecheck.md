---
id: task-add-lint-and-typecheck
title: Add lint and type checking to this repo's own Python
type: task
status: pending
repos: [epic-code-gen, epic-code-gen-pipeline]
---

# Task: Add lint and type checking to this repo's own Python

## Goal

Hold this repo to the standard it enforces on target repos.

## Context

The product's value proposition is enforcing lint on other repositories. This repo has **no linter and no type checker** for 10.5k lines of Python, no config for ruff/flake8/black/mypy, and no `make lint` target. `Dockerfile.ci` installs `markdownlint-cli` for target repos while nothing lints our own code.

## Acceptance Criteria

- [ ] `ruff` configured and passing (or the failures triaged into tasks)
- [ ] `make lint` target added and wired into CI
- [ ] Decide on type checking — `mypy` is blocked by [ADR-0003]'s flat layout; record the decision
- [ ] `shellcheck` in the pipeline repo stops being `|| true`

## Files Likely Involved

- `pyproject.toml`
- `Makefile`
- `.github/workflows/ledger.yml`

## Status

Pending.

## Notes

Expect a large initial diff. Land the config with generous ignores first, then narrow — a single PR that reformats 10.5k lines is unreviewable. The pipeline repo's `make lint` silently passes when shellcheck is absent, which is worse than having no target.
