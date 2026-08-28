---
id: bug-gitignored-files-are-tracked
title: Several paths are both gitignored and tracked
type: bug
status: open
repos: [epic-code-gen]
---

# Bug: Several paths are both gitignored and tracked

## Summary

`package-lock.json`, `epic-reports/`, and `pipeline-runs/` are listed in `.gitignore` while also being tracked or present with content, so the ignore rules do not mean what they say.

## Reproduction

1. `git check-ignore -v package-lock.json` and `git ls-files package-lock.json`.

## Expected

A path is either ignored or tracked.

## Actual

Both. `package-lock.json` is gitignored and tracked, with its own commit history (`e54900b`). `epic-reports/` and `pipeline-runs/` are gitignored but present on disk with content.

## Impact

Low

## Evidence

`package-lock.json` arguably *should* be tracked (it pins Playwright for `parse_prototype.js`), which means the `.gitignore` entry is the error rather than the tracking. `epic-reports/` was gitignored deliberately because it holds sensitive HTML (`876a0f3`), so that one is correct and merely confusing.

## Related Tasks

- [[bug-node-modules-committed]]
- [[M7-engineering-process]]
