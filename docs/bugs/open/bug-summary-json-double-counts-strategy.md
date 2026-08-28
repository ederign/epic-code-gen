---
id: bug-summary-json-double-counts-strategy
title: summary.json double-counts a strategy and reports null scores
type: bug
status: open
repos: [epic-code-gen-pipeline, epic-code-gen-pipeline-data]
---

# Bug: summary.json double-counts a strategy and reports null scores

## Summary

Two independent data-quality defects in the dashboard's entry point, both visible in the current `summary.json`.

## Reproduction

1. Read the top-level `summary.json` in the data repo.
2. Compare `stats.strategies` against the number of live strategy directories.
3. Compare an epic's `scores` field against its `run-metadata.yaml`.

## Expected

One row per live strategy, and `scores` populated wherever the epic has scores.

## Actual

Reports `"strategies": 7` and lists `RHAISTRAT-1699` **twice** — really 6 strategies plus 1 archive. And `scores` is `null` for epics that plainly have scores: RHAI-74 shows `scores: null` beside `final_score: 9.4`.

## Impact

Medium

## Evidence

**Cause 1:** `build_global_summary` iterates directories but keys off the `strategy_key` *inside* each `strategy-summary.json`. The manual archive directory `RHAISTRAT-1699-before-ux-ac/` still declares `strategy_key: RHAISTRAT-1699`, so it contributes a duplicate row — and its `failed: 1`.

**Cause 2:** `build_strategy_summary` reads `e.get("scores")`, a field only the nested metadata generation writes. Epics using the `dimension_scores` / `dimensions` / `scores_by_dimension` vocabularies surface as `null` — see the four coexisting schema generations in `docs/architecture/03-artifact-contracts.md`.

## Related Tasks

- [[task-dashboard-three-views]]
- [[task-data-repo-artifact-structure]]
- [[task-converge-run-metadata-schema]]
