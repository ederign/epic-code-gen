---
id: task-prune-data-repo-growth
title: Define a pruning strategy for the data repo
type: task
status: pending
repos: [epic-code-gen-pipeline-data]
decisions: [ADR-0008]
---

# Task: Define a pruning strategy for the data repo

## Goal

Stop unbounded growth without losing the audit trail.

## Context

33 MB for 24 epics, and **13.7 MB of that is three OTEL files** (one is 9.8 MB). Versions accumulate and are never deleted, by design. `FOREDER.md` predicted this in June.

## Acceptance Criteria

- [ ] Decide what is durable (scores, final diff, run log) vs prunable (raw OTEL, intermediate versions)
- [ ] Compress or downsample OTEL before committing
- [ ] Retention policy for version directories on merged epics
- [ ] Consider what the dashboard actually reads before deleting anything

## Files Likely Involved

- `ci-scripts/push-results.py`

## Status

Pending.

## Notes

The OTEL files are raw OTLP payloads; only the summed cost is consumed. Compressing or summarising at write time would reclaim most of the space with no loss to any current consumer. Note the archive directory `RHAISTRAT-1699-before-ux-ac/` (2.0 MB) is also causing [[bug-summary-json-double-counts-strategy]].
