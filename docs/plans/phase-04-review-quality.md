---
id: phase-04-review-quality
title: "Phase 04 — Review quality: deterministic scoring, spec-first generation, UX prototypes"
type: plan
status: done
repos: [epic-code-gen]
commits: ["a7326fe", "788f16f", "ffe24ea", "d41a7c0", "3ba1751", "daee4d7", "13d9e63", "f7da07c", "4def105", "75e70c9"]
---

# Phase 04 — Review quality

**2026-07-09 → 2026-07-17. 76 commits — the largest phase.**

## Goal

The pipeline was running unattended and producing PRs. The problem was that its scores could not
be trusted, and its v1 output was consistently weak enough that most epics burned iterations
climbing out of a bad start.

## What shipped

### Scoring became arithmetic

`a7326fe` is the pivotal commit of the project: **reviewers stopped choosing scores.** They
classify findings by severity; `score_reviews.py` computes
`score = max(1, 10 − 5·Critical − 1.5·Important − 0.5·Minor)`, and `788f16f` capped any dimension
containing a Critical at 5. Before this, a reviewer could write up a Critical and still award 8.5.
See [ADR-0022], [ADR-0023].

`f7983c9` then stopped PR creation on a failed verdict — the gate had been advisory. (It became
advisory again by a different route; see RHAIFIRST-391 in [Phase 05](phase-05-hardening.md).)

`13d9e63` + `f7da07c` moved review dispatch out of prose and into `review_cycle.py`, so the loop is
Python and only triage is a model judgment ([ADR-0026]). `5e26193` added an anti-fallback
guardrail after the orchestrator was caught writing review files itself.

### Generation became spec-first

Instead of prompting for code, the skill now runs Superpowers `brainstorming` through a design
subagent that answers the questions from epic + strategy + pattern discovery (`ffe24ea`), then
`writing-plans` for the implementation plan (`d41a7c0`), each isolated in its own subagent
(`3ba1751`). Pattern discovery was expanded to 5–10 siblings plus sibling directories (`d3a5a24`)
and concept search (`37a1d67`), and `9b65e8c` made it strictly sequential — discovery *before*
brainstorming, because the design was otherwise invented without evidence. See [ADR-0016],
[ADR-0018].

### Agents became files

`f74a79c` → `daee4d7` → `f601ef2` extracted every subagent from inline prose in SKILL.md into
standalone definitions in `.claude/agents/` — 13 of them ([ADR-0021]). `44da7be` added logging to
each, `bbce28f` added skill-invocation verification, so a subagent that silently didn't run became
visible.

### Two new verifiers, neither scored

`5e19a14` added wiring verification (does each AC's trigger → chain → outcome actually connect?)
and `d0f2a2d` added the interaction verifier for runtime bugs that structural review misses —
callback races, missing switch branches, broken form flows. Both inform triage; neither affects the
score ([ADR-0028]).

### Triage got a memory

`cf1da6e` made triage history-aware and added near-miss PR creation on exhaustion; `050732f` added
accepted-findings carry-forward so a finding dismissed with reason in v2 doesn't reappear in v3;
`24d8078` added cross-dimension dedup and reviewer calibration; `8a4a5c7` moved the fix loop into a
fresh-context subagent.

### Prototype-driven generation

`4def105` added Playwright-based parsing of UXD HTML prototypes into per-scenario markdown plus
screenshots; `75e70c9` turned those into numbered UX acceptance criteria (`UX-G1`, `UX-S1-1`) that
the intent reviewer verifies; `bf0e7cc` made prototype deviations non-negotiable in triage. See
[ADR-0020].

## Evidence

Score progressions in the data repo show the loop working as intended rather than converging by
luck: RHAI-74 went 2.4 → 4.9 → 7.2 → 9.4 across v1–v4; RHAI-64 went 2.6 → 2.65 → 6.1 → 6.7 → 8.2.
`RHAISTRAT-1699/RHOAIENG-72103` is the first epic through the full UX-AC path and reached Done at
8.15.

## What it got wrong

- **`rubrics/` was left behind.** The whole point of this phase was calibration, and the old,
  contradictory calibration files were never deleted.
- **`review_cycle.py wait` returns when the *scored* dimensions land**, leaving wiring and
  interactions still running. `4f1cc62` fixed the inverse bug (blocking on unscored reviewers) but
  the result is that triage can read a truncated file with no way to distinguish "clean" from
  "never finished". Still open.
- **Playwright cost three consecutive infrastructure fixes** (`210c464` browser path for non-root,
  `5571f31` `NODE_PATH`, `0346470` missing headless libs) plus `976a59d`. Each one a failed CI run.
- **`node_modules` was committed** (`f978330` removed it) and `package-lock.json` is both tracked
  and gitignored — still true today.
- The reviewers were caught citing patch line numbers instead of source line numbers (`34b6e8d`),
  which made findings unactionable for the fix agent.
