---
id: bug-node-modules-committed
title: node_modules was committed to git
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["f978330", "e54900b"]
---

# Bug: node_modules was committed to git

## Summary

`node_modules` was accidentally committed when Playwright was added.

## Reproduction

1. `git log --stat` around the Playwright work.

## Expected

`node_modules` is gitignored and never tracked.

## Actual

Committed, then removed in a follow-up.

## Impact

Low

## Evidence

`e54900b` then updated `package-lock.json` (jsdom replaced by playwright). Note `package-lock.json` is currently **both tracked and gitignored** — see [[bug-gitignored-files-are-tracked]].

## Related Tasks

- [[task-ux-prototype-pipeline]]
