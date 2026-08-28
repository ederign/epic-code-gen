---
id: task-delete-dead-code
title: Delete rubrics/, the codegen-review subsystem, and other dead code
type: task
status: pending
repos: [epic-code-gen]
decisions: [ADR-0021]
---

# Task: Delete rubrics/, the codegen-review subsystem, and other dead code

## Goal

Remove code and docs that are unused and actively contradict current behaviour.

## Context

Dead code that looks authoritative is worse than no code: a reader trusts it. `rubrics/` states weights, a dimension, and a model that are all wrong.

## Acceptance Criteria

- [ ] `rubrics/` deleted (5 files, 424 lines)
- [ ] `SCHEMAS["codegen-review"]`, `find_codegen_review`, `rebuild_index`, `frontmatter.py rebuild-index` removed
- [ ] `scripts/__init__.py` removed (0 bytes, vestigial)
- [ ] `make test-integration` and the `integration` marker either used or removed
- [ ] Confirm nothing references them first

## Files Likely Involved

- `rubrics/`
- `scripts/artifact_utils.py`
- `scripts/frontmatter.py`
- `Makefile`

## Status

Pending.

## Notes

See [[bug-rubrics-directory-is-dead-and-wrong]] and [[bug-codegen-review-schema-is-dead]]. Do this **before** the lint work, so the linter isn't run over code that's about to be deleted.
