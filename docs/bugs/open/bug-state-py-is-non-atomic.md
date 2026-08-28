---
id: bug-state-py-is-non-atomic
title: state.py is non-atomic but is read during parallel agent dispatch
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0004]
---

# Bug: state.py is non-atomic but is read during parallel agent dispatch

## Summary

`state.py` documents that it assumes single-process sequential access, while `review_cycle.py` reads the same files during a parallel six-agent dispatch loop.

## Reproduction

1. Inspect `state.py`'s own docstring on atomicity.
2. Trace `review_cycle.py`'s reads of `tmp/epic-codegen-<EPIC>.json` during dispatch.

## Expected

Either atomic writes, or a documented single-writer discipline that is actually enforced.

## Actual

Non-atomic read-modify-write on a file touched during parallel dispatch. No corruption has been observed, but nothing prevents it, and the failure would look like a lost or garbled phase — i.e. a compaction recovery that silently does the wrong thing.

## Impact

Medium

## Evidence

Compounding factors: the file is parsed by `line.startswith("phase:")` string matching in `review_cycle.py:396-403`, so a field rename breaks recovery silently; and `state.py` has **no tests** despite every long-running skill depending on it.

## Related Tasks

- [[task-context-compaction-recovery]]
- [[task-add-tests-for-untested-modules]]
