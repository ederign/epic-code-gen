---
id: ADR-0026-python-owns-determinism
title: Python owns the loop; the model owns only triage
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["13d9e63", "f7da07c", "4f1cc62", "5e26193"]
decisions: [ADR-0022, ADR-0012]
---

# ADR-0026: Python owns the loop; the model owns only triage

## Status

Accepted (2026-07-15).

## Context

The review loop lived in `SKILL.md` as prose: dispatch six reviewers, wait for them, verify their
output, score it, triage, dispatch a fix, repeat. Nine steps of bookkeeping, expressed as instructions
to a model that was simultaneously managing a 6-hour context and being compacted periodically.

Bookkeeping is exactly what a model is worst at under pressure. Observed failures: reviewers dispatched
and never waited for; the orchestrator writing review files itself when dispatch appeared to fail;
scores computed by estimation rather than by running the scorer.

## Decision

Move the loop into `scripts/review_cycle.py`. It owns the `REVIEWERS` table (six reviewers, four
scored) and exposes subcommands the skill calls in order:

| Subcommand | Job |
|---|---|
| `prompts` | emit each reviewer's dispatch prompt |
| `wait` | block until review files land |
| `verify` | confirm the files are well-formed and non-empty |
| `score` | run `score_reviews.py`, write `scores.json` |
| `triage-prompt` | build the triage agent's prompt |
| `dispatch-context` | reprint loop state after a compaction ([ADR-0004]) |

The skill's remaining job is to dispatch agents and let Python decide what happens next. **The only
model judgment left in the loop is triage** — deciding which findings to accept and what to fix.

`5e26193` added an anti-fallback guardrail: if dispatch fails, fail. Do not improvise. `SKILL.md` states
it flatly — *never write review files yourself.*

## Consequences

### Positive

- The loop is testable (`tests/test_review_cycle.py`, 38 tests) and behaves identically regardless of
  context pressure.
- Compaction recovery becomes possible, because loop state is a script's concern rather than a memory.
- Same principle as [ADR-0012] and [ADR-0022]: give the model the judgment, give Python the procedure.

### Negative

- The skill still has to *call* these in the right order, so the anti-fallback rule remains a prompt
  instruction, not a mechanism. **RHAIFIRST-391 is that gap being exercised**: the orchestrator skipped
  the loop, authored review files itself, and estimated scores in prose — exactly what `5e26193`
  forbade and nothing enforced.
- `wait` returns as soon as the *scored* dimensions land, leaving wiring and interactions still running
  ([ADR-0028]). `4f1cc62` fixed the inverse bug — blocking forever on unscored reviewers — and the
  result is that triage can read a truncated file with no way to distinguish "clean" from "never
  finished". Open bug.
- State is passed through `tmp/` files parsed by string matching, so a field rename breaks recovery
  silently.
