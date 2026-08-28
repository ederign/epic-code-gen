---
id: bug-yaml-crash-in-push-results
title: push-results.py crashed on a multi-document run-metadata.yaml
type: bug
status: fixed
repos: [epic-code-gen-pipeline]
commits: ["5c4ea17"]
---

# Bug: push-results.py crashed on a multi-document run-metadata.yaml

## Summary

The skill sometimes appended a second YAML document to `run-metadata.yaml`. `yaml.safe_load` raises on multi-document input, so the push crashed and the run's results were never persisted.

## Reproduction

1. Produce a `run-metadata.yaml` containing two `---` documents.
2. Run `push-results.py`.

## Expected

The file is read without crashing.

## Actual

Exception; artifacts not pushed, so a successful codegen run left no durable record.

## Impact

High

## Evidence

Fixed with `_safe_load_yaml()` using `yaml.safe_load_all()` and taking the first document. The same commit added recursive artifact copying for crash recovery.

## Related Tasks

- [[task-data-repo-artifact-structure]]
- [[bug-push-results-overwrote-state]]
