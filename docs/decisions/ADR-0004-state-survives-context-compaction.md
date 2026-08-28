---
id: ADR-0004-state-survives-context-compaction
title: State persisted to tmp/ so it survives context compaction
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["ae79932", "7848b5e"]
---

# ADR-0004: State persisted to `tmp/` so it survives context compaction

## Status

Accepted (2026-06-22; compaction hook added later).

## Context

A single epic's codegen run is long — up to 6 hours, 10 review iterations, dozens of subagent
dispatches. It will hit context compaction, possibly several times. When it does, the orchestrator
loses the working memory of which epic it is on, which version it is reviewing, and which phase it
is in. Before this was handled, a compaction mid-review restarted the review loop or silently
skipped it.

## Decision

Two mechanisms.

**1. State files.** `scripts/state.py` persists key/value state to `tmp/epic-codegen-<EPIC_ID>.json`
(a line-oriented `key: value` format despite the extension):

```bash
python3 scripts/state.py init <file> key=value ...
python3 scripts/state.py set <file> key=value ...
python3 scripts/state.py read <file>
```

Triage state — findings accepted with a reason in a prior version — goes to
`tmp/accepted-findings-<EPIC_ID>.json`, which is real JSON.

**2. A compaction hook.** `.claude/settings.json` registers a `SessionStart` hook with
`matcher: "compact"` that runs `review_cycle.py dispatch-context`. On compaction it reads the state
file, and if `phase` is one of `review`, `fixing`, or `implementing`, it re-prints `EPIC_ID`,
`VERSION`, and the full review dispatch loop into the fresh context. Recovery is automatic rather
than dependent on the model remembering to look.

## Consequences

### Positive

- A compaction is a non-event for a run in progress. This is the difference between a 6-hour run
  completing and a 6-hour run producing nothing.
- State on disk is inspectable after the fact, so a wedged run can be diagnosed.
- `7848b5e` removed filesystem polling for subagent completion in favour of this, cutting a whole
  class of busy-wait.

### Negative

- `state.py` is explicitly non-atomic ("assumes single-process sequential access") while
  `review_cycle.py` reads the same files during a parallel-agent dispatch loop. No corruption has
  been observed, but nothing prevents it. Tracked in `docs/bugs/open/`.
- The format is bespoke. `review_cycle.py` parses it with `line.startswith("phase:")` string
  matching, so a field rename breaks recovery silently.
- A `.json` extension on a file that is not JSON invites exactly the wrong parser.
- `state.py` has **no tests**, despite every long-running skill depending on it.
