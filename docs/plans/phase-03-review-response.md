---
id: phase-03-review-response
title: "Phase 03 — Review response and telemetry: answering PR comments, seeing cost"
type: plan
status: done
repos: [epic-code-gen, epic-code-gen-pipeline]
jira: RHAIFIRST-212
commits: ["99c9bc6", "2f263da", "6aecf9b", "7f4c35f", "b7db47c", "7bedbb0"]
---

# Phase 03 — Review response and telemetry

**2026-07-02 → 2026-07-04. 40 commits.** Jira: RHAIFIRST-212 (V2 Code Review Response Pipeline),
RHAIFIRST-208/209 (Jira automation), RHAIFIRST-210/211/213 (state log, telemetry, story dashboard).

## Goal

A PR that gets review comments should get fixes, not a regenerated branch. And a run that costs
money should say how much.

## What shipped

**V2 review response**, in three deliberate slices: foundation utilities (`99c9bc6`), orchestrator
plus agents (`2f263da`), state-machine integration (`6aecf9b`), merged at `7f4c35f` after
`48185b8` fixed six issues found in its own review.

The design decisions, all recorded in RHAIFIRST-212 at the time and now in [ADR-0032]:

- Check out the existing branch from the fork and commit on top. **Never regenerate.**
- Human reviewers: always address. Bots: selective.
- One agent handles all comments, one commit — not one agent per comment.
- Lightweight post-fix check (validation + a sanity-check agent), not a full re-review.
- Only touch code inside our own diff.

**Jira automation** (`b7db47c`). Epics and their parent STRAT are auto-assigned to the automation
bot when the pipeline starts, and the STRAT transitions to In Progress. Idempotent by design.

**Telemetry.** An OTLP collector in the pipeline repo captures Claude Code's delta-temporality
metrics to `claude-otel.jsonl`; `otel-summary.py` prints tokens and cost per model.
`push-results.py` extracts total cost into the run log. Cumulative logged spend to date: ~$80.

**State transitions became data** (`7bedbb0`). `actions.json` records every `from` → `to`
transition so the dashboard can render a timeline instead of inferring one.

**Dashboards.** A story-mode visualization was built here (`9ba09f8` and ~15 follow-ups) and then
correctly moved out to `epic-code-gen-dashboard` (`099a249`, `659cbfc`) once it was clear it was a
consumer, not part of the engine.

## Evidence

Review-response cycles are visible in the data repo as version directories with a *different
shape* from codegen versions: `diff.patch`, `validation.json`, `review-feedback.md`,
`review-response-plan.md`, `sanity-check.md` — and no `scores.json`. `RHAISTRAT-2162/RHAI-74/v6/`
and `v7/` are examples. That shape difference is the clearest signal of which loop produced a
version.

## What it got wrong

- **Top-level review bodies were ignored.** The loop only looked at inline comments, so a
  `CHANGES_REQUESTED` review with its objection in the body produced no work at all and the epic
  sat still. Filed as RHAIFIRST-375, fixed a month later in `164d21e`.
- **`current_version` and `versions` diverged silently.** Review-response cycles increment one
  counter, codegen iterations increment the others. Live data shows `current_version: 7`,
  `versions: 4`, `final_version: 4` with no documented relationship. `9ccd429` tried to sync them.
- **Three state fall-through fixes in two days** (`1279fb2`, `1045c53`, `df25f2e`) — each a state
  that should have advanced and didn't. Symptom of a state machine encoded as `if/elif` with no
  written transition table. That table now exists:
  [`../architecture/02-pipeline-state-machine.md`](../architecture/02-pipeline-state-machine.md).
- A rebase was still not part of the cycle, so PRs drifted into CONFLICTING. Fixed in
  [Phase 05](phase-05-hardening.md) (RHAIFIRST-376).
