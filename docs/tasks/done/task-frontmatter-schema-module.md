---
id: task-frontmatter-schema-module
title: Frontmatter schema module and CLI
type: task
status: done
repos: [epic-code-gen]
commits: ["ae79932"]
decisions: [ADR-0002]
---

# Task: Frontmatter schema module and CLI

## Goal

One module owning every artifact schema, with a CLI so skills never parse YAML.

## Context

Artifacts are markdown that agents read as prose, but the pipeline needs structured fields from them. Parsing prose is unreliable; a parallel index drifts.

## Acceptance Criteria

- [x] `SCHEMAS` for epic-task, codegen-run, codegen-review in one module
- [x] Types, required flags, enums, defaults
- [x] Validation on read
- [x] `frontmatter.py` CLI: schema / read / set / merge-run-metadata

## Files Likely Involved

- `scripts/artifact_utils.py`
- `scripts/frontmatter.py`
- `tests/test_artifact_utils.py`

## Status

Done.

## Notes

This single-definition-site property is what made the RHAIFIRST-374 fix small. `frontmatter.py` itself still has **no tests** ([[task-add-tests-for-untested-modules]]), and `run-metadata.yaml` is not actually schema-validated.
