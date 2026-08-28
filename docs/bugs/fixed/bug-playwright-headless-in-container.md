---
id: bug-playwright-headless-in-container
title: Playwright could not run headless chromium as a non-root user in CI
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["210c464", "5571f31", "0346470", "976a59d"]
decisions: [ADR-0020]
---

# Bug: Playwright could not run headless chromium as a non-root user in CI

## Summary

UX prototype parsing needs headless chromium. It failed three separate ways in the container before working: browser path unresolvable for the non-root user, the global `playwright` module not resolvable, and missing system libraries.

## Reproduction

1. Run `node scripts/parse_prototype.js` in the CI image as `claude-ci`.
2. Observe browser launch failure.

## Expected

Chromium launches headless and the prototype is parsed.

## Actual

Three distinct failures, each requiring a separate image fix and a failed CI run to discover.

## Impact

Medium

## Evidence

`210c464` set `PLAYWRIGHT_BROWSERS_PATH=/opt/playwright` with `chmod -R 755`; `5571f31` added `NODE_PATH=/usr/lib/node_modules`; `0346470` added `nspr`, `nss`, `libxkbcommon` alongside the earlier `alsa-lib atk at-spi2-atk cups-libs libdrm libXcomposite libXdamage libXrandr mesa-libgbm pango`. `976a59d` then fixed screenshot cropping.

## Related Tasks

- [[task-ux-prototype-pipeline]]
- [[task-ci-image-and-build-infrastructure]]
