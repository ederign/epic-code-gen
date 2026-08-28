---
id: task-add-resource-group-to-codegen-run
title: Add a resource_group to codegen-run and enable scheduling
type: task
status: pending
repos: [epic-code-gen-pipeline]
decisions: [ADR-0008]
---

# Task: Add a resource_group to codegen-run and enable scheduling

## Goal

Make concurrent runs safe, then move off a manual trigger.

## Context

`codegen-run` has no `resource_group`, so two concurrent triggers race on the data repo — mitigated only by push-retry-with-rebase (3 attempts, `-X theirs`). `FOREDER.md` identified this in June as **the** prerequisite for scheduling, and it is the real reason the pipeline is still triggered by hand.

## Acceptance Criteria

- [ ] `resource_group` added so runs serialise
- [ ] Verify behaviour with two simultaneous triggers
- [ ] Then add a schedule (`rules: - schedules`)
- [ ] Decide the granularity — global, or per strategy key

## Files Likely Involved

- `.gitlab-ci.yml`

## Status

Pending.

## Notes

Per-strategy granularity would allow useful parallelism, but two strategies still share one data repo and `push-results.py` regenerates the global `summary.json`, so global serialisation is the safe first step. Fix [[bug-multi-strategy-runs-lose-run-record]] before scheduling anything.
