---
id: task-converge-run-metadata-schema
title: Converge the run-metadata.yaml schema and pin it
type: task
status: pending
repos: [epic-code-gen, epic-code-gen-pipeline-data]
decisions: [ADR-0002, ADR-0014]
---

# Task: Converge the run-metadata.yaml schema and pin it

## Goal

One documented schema for the state file, validated on write.

## Context

Four generations coexist in the data repo. Two names for one concept (`dimension_scores` vs `scores_by_dimension`), three counters with no documented relationship (`current_version`, `versions`, `final_version`), and `merge_run_metadata` validates only two rules while every other field is free-form and type-inferred.

## Acceptance Criteria

- [ ] Pick one name per concept and migrate the data repo
- [ ] Document the relationship between the three counters, or collapse them
- [ ] Register the schema so writes are validated, not just `status`/`codegen_outcome`
- [ ] `RHAISTRAT-2352/RHAI-264`'s corrupt `status` migrated rather than normalised on read

## Files Likely Involved

- `scripts/artifact_utils.py`
- `docs/architecture/03-artifact-contracts.md`

## Status

Pending.

## Notes

Current state documented in `docs/architecture/03-artifact-contracts.md`. Fixing this also fixes half of [[bug-summary-json-double-counts-strategy]], since `scores: null` is a symptom of the vocabulary split. Coordinate with the pipeline repo — `PIPELINE_OWNED_KEYS` is duplicated there by design.
