---
id: bug-codegen-review-schema-is-dead
title: The codegen-review schema and rebuild-index subsystem are dead
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0002]
---

# Bug: The codegen-review schema and rebuild-index subsystem are dead

## Summary

`SCHEMAS["codegen-review"]`, `find_codegen_review`, `rebuild_index`, `frontmatter.py rebuild-index`, and `artifacts/epics.md` form a subsystem nothing uses.

## Reproduction

1. Search the repo and the data repo for `artifacts/codegen-reviews/` — it appears only inside `artifact_utils.py`.

## Expected

Unused schemas are removed, or the subsystem is wired up.

## Actual

Dead, and misleading: its `scores` keys are `lint, typecheck, tests, intent_coverage, architecture` — a vocabulary that predates the live dimensions (`architecture, tests, lint, intent`). Anyone reading it would infer the wrong dimension set.

## Impact

Low

## Related Tasks

- [[task-frontmatter-schema-module]]
- [[task-delete-dead-code]]
