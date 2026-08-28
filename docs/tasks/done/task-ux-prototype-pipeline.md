---
id: task-ux-prototype-pipeline
title: Prototype-driven UX acceptance criteria
type: task
status: done
repos: [epic-code-gen]
commits: ["4def105", "75e70c9", "bf0e7cc", "58e4bd7", "976a59d"]
decisions: [ADR-0020]
---

# Task: Prototype-driven UX acceptance criteria

## Goal

Make a UXD prototype checkable, so generated UI matches the design and not just the epic text.

## Context

Front-end epics come with an HTML prototype attached to the Jira issue. The prototype is the real specification; the epic body summarises it lossily. Generated UI was passing architecture and tests while having wrong labels and missing helper text.

## Acceptance Criteria

- [x] Playwright parser extracts components, alerts, disabled states, labels, helper text, popovers, checkboxes, radios, badges
- [x] Per-scenario markdown plus cropped screenshots
- [x] Numbered UX ACs (`UX-G1`, `UX-S1-1`) verified by the intent reviewer
- [x] Prototype deviations non-negotiable in triage

## Files Likely Involved

- `scripts/parse_prototype.js`
- `.claude/agents/ux-ac-extractor.md`
- `.claude/agents/intent-reviewer.md`

## Status

Done.

## Notes

`RHOAIENG-72103` is the first epic through this path, Done at 8.15. `bf0e7cc` was needed because triage had been dismissing UX findings as out of scope. `parse_prototype.js` is 699 lines with **no tests** and no JS test runner configured. Deliberately carries no `jira:` key: the epic RHAIFIRST-233 is still open because children 234/235/236 remain, so claiming it here would report a live epic as closed. The epic is tracked by [[task-prototype-driven-codegen-remaining]].
