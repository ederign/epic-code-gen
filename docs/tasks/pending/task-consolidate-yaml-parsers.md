---
id: task-consolidate-yaml-parsers
title: Consolidate six YAML parsers and three value coercers
type: task
status: pending
repos: [epic-code-gen]
---

# Task: Consolidate six YAML parsers and three value coercers

## Goal

One YAML read path, one coercion function.

## Context

Six independent YAML-ish parsers exist: `artifact_utils` (PyYAML), `run_index._parse_yaml_simple`, `run_pipeline._parse_flat_yaml`, `run_pipeline._read_metadata_simple`, `fetch_jira_epics._parse_simple_yaml`, and `line.startswith("phase:")` scanning in `review_cycle.py`. Three of them exist purely as a PyYAML-optional fallback — but `pyyaml` is a hard dependency in `pyproject.toml` and baked into `Dockerfile.ci`, so those fallbacks are **unreachable in every supported environment**.

## Acceptance Criteria

- [ ] Fallback parsers removed; `artifact_utils.read_frontmatter` is the single read path
- [ ] `frontmatter._coerce_value` / `_infer_value` / `run_index._coerce_value` consolidated
- [ ] Also consolidate: three git wrappers, two HTTP clients, two slug extractors
- [ ] Tests still pass

## Files Likely Involved

- `scripts/run_index.py`
- `scripts/run_pipeline.py`
- `scripts/fetch_jira_epics.py`
- `scripts/artifact_utils.py`

## Status

Pending.

## Notes

The coercers differ subtly — different truthy-string sets (`"yes"`, `"True"`) — so consolidating changes behaviour somewhere. Write the tests first. Note `AGENTS.md` already forbids adding a seventh.
