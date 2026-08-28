---
id: ADR-0020-prototype-driven-ux-acs
title: Prototype-driven UX acceptance criteria
type: adr
status: accepted
repos: [epic-code-gen]
jira: RHAIFIRST-233
commits: ["4def105", "75e70c9", "bf0e7cc", "58e4bd7"]
---

# ADR-0020: Prototype-driven UX acceptance criteria

## Status

Accepted (2026-07-14 → 07-17). Related open work: RHAIFIRST-233/234/235/236.

## Context

Front-end epics against `odh-dashboard` come with a UXD-produced HTML prototype attached to the Jira
issue. The prototype is the real specification — it shows the exact PatternFly components, labels,
helper text, disabled states, and alert copy. The epic body summarizes it, lossily.

Generated UI code was passing architecture and tests review while not matching the design: right
components, wrong labels; correct form, missing helper text. Nothing in the review loop was looking at
the prototype, so these were invisible.

## Decision

Parse the prototype deterministically, then turn it into numbered acceptance criteria.

**Parse** (`4def105`) — `scripts/parse_prototype.js` (699 lines, Playwright + headless chromium) loads
the prototype and extracts per scenario: component inventory, alerts, disabled states, form labels,
helper text, popover content, checkboxes, radio buttons, badges. It writes one markdown file per
scenario plus a cropped screenshot, and a `prototype-summary.md`.

**Extract** (`75e70c9`) — the `ux-ac-extractor` agent turns that analysis into
`ux-acceptance-criteria.md` with stable numbering: `UX-G1…` for global requirements, `UX-S1-1…`
per scenario.

**Verify** — the `intent-reviewer` gained a `### UX Acceptance Criteria Verification` section, so UX
ACs are scored inside the 20% intent dimension.

**Protect** (`bf0e7cc`) — prototype deviations are **non-negotiable in triage**. The
`iteration-reviewer` may not dismiss a UX finding as out of scope, because it had been doing exactly
that.

## Consequences

### Positive

- The design becomes checkable rather than aspirational. `RHOAIENG-72103` is the first epic through this
  path and reached Done at 8.15.
- Deterministic extraction, not a model reading a screenshot: the same prototype yields the same
  component inventory every time.
- Screenshots are preserved in the data repo, so a human can compare intent to output directly.

### Negative

- Playwright is the single heaviest dependency in the image and took three fixes to run headless as
  non-root (`210c464`, `5571f31`, `0346470`), plus `976a59d` for screenshot cropping.
- Tightly coupled to PatternFly and to UXD's prototype conventions. Prototype detection is a regex over
  Jira table markup and has already broken once on pipe-delimited tables (`58e4bd7`).
- **`parse_prototype.js` has no tests** — 699 lines, and no JS test runner is configured in the repo at
  all.
- Undocumented in `CLAUDE.md`, and the whole subsystem is absent from `README.md`.
