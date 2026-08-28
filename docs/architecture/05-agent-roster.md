---
id: 05-agent-roster
title: Agent roster — all 13 agents and their contracts
type: plan
status: current
repos: [epic-code-gen]
decisions: [ADR-0021, ADR-0027, ADR-0028, ADR-0029]
---

# Agent roster

Thirteen agent definitions in `.claude/agents/`, one file each ([ADR-0021]). All inherit the session
model — no per-agent overrides ([ADR-0029]).

> **Read [ADR-0027] before trusting a `tools:` line.** Reviewers and verifiers are dispatched *without*
> `agentType`, so they inherit the parent's full tool set — including `Write`, which they need to produce
> their output. For those agents `tools:` documents intent, it does not constrain. Generators *are*
> dispatched with `agentType` (SKILL.md:287, 378, 416, 440) and their tool lists are enforced.

## Scored reviewers

Findings → deterministic score ([ADR-0022]). Each writes `REVIEW_FILE`. **None outputs a score.**

| Agent | Weight | Declared tools | Required sections beyond findings |
|---|---|---|---|
| `architecture-reviewer` | 30% | Read, Glob, Grep | `### Convention Compliance`, `### Integration Assessment` |
| `tests-reviewer` | 30% | Read, Glob, Grep | `### AC Coverage` table (`AC \| Test \| file:line \| Covered?`), `### Edge Cases` |
| `lint-reviewer` | 20% | Read, Glob, Grep | `### Validation Results` table; reads `VALIDATION_FILE` |
| `intent-reviewer` | 20% | Read, Glob, Grep | `### AC-to-Diff Mapping`, `### Pass Criteria Verification`, `### Scope Fidelity`, `### UX Acceptance Criteria Verification`, `### Scope Creep Check` |

Shared findings contract: `### Findings` → `#### Critical` / `#### Important` / `#### Minor`, each finding
numbered `N. **Title**`. This markdown *is* the machine interface — `score_reviews.py` parses it by regex
and **fails open** (unrecognized heading → zero findings → 10.0).

`tests-reviewer` explicitly scopes integration/e2e tests out ("NOT a finding"). `intent-reviewer` is the
richest at 174 lines and reads the epic file directly.

## Unscored verifiers

Findings inform triage only ([ADR-0028]).

| Agent | Traces | Notes |
|---|---|---|
| `wiring-verifier` | trigger → chain → outcome per AC | `### Wiring Traces` table. "Minor: none expected — wiring is binary." |
| `interaction-verifier` | user interactions, enum/branch completeness | callback races, missing `switch` cases, broken form flows |

## Generators and actors

| Agent | Job | Output |
|---|---|---|
| `design-spec-generator` | invokes Superpowers `brainstorming`, acts as human partner | `codegen-spec.md`, `brainstorming-log.md` |
| `spec-reviewer` | validates the spec against real repo patterns, pre-plan | `spec-review-log.md` + mismatch table (`Spec Proposes \| Codebase Does \| Fix`) |
| `plan-generator` | invokes Superpowers `writing-plans` | `codegen-plan.md`, `writing-plans-log.md` |
| `ux-ac-extractor` | prototype analysis → numbered UX ACs | `ux-acceptance-criteria.md` (`UX-G1`, `UX-S1-1`) |
| `iteration-reviewer` | **triage** — the only model judgment left in the loop | `revision-notes.md`, `decision-log.md`, updates accepted-findings; dispatches the fix agent |
| `review-fix-agent` | applies PR-review fixes — one agent, all comments, one commit | ≤20-line summary |
| `sanity-check-agent` | verifies fixes address the comments | `sanity-check.md` (`### Addressed`, `### Scope Check`, `### Verdict`) |

`design-spec-generator` opens with an all-caps autonomy directive, strengthened twice (`c61354c`) because
a skill built for human partnership keeps trying to ask the human.

`iteration-reviewer` is the most complex at 190 lines: it applies accepted-findings filtering,
oscillation detection, cross-dimension dedup, and treats prototype UX deviations as non-negotiable
(`bf0e7cc`). It returns a strict JSON block — `{epic_id, version, scores{dim:{score,findings}},
weighted_average, verdict, accepted_findings[], fix_applied, fix_version, summary}` — with "no other
text". It is the only agent holding the `Agent` tool, because it dispatches the fix subagent.

## Two live defects in the definitions

Both tracked in [`../bugs/open/`](../bugs/open/):

- `iteration-reviewer.md` references `${BASE_SHA}`, which is not in its declared inputs and which
  `review_cycle.py triage-prompt` never emits — an undefined variable in a prompt template.
- `iteration-reviewer.md:161` tells the fix path to produce `validation.json` by redirection, while
  `SKILL.md` Step 13 mandates `--out`. Both produce authentic output and pass the [ADR-0024] gate, but a
  reader cannot tell which is normative.

## The dead one

`rubrics/` — 5 files, 424 lines, referenced nowhere. Superseded by these agent definitions and **actively
wrong**: architecture 20% (real 30%), tests 25% (real 30%), intent 25% (real 20%), a `patterns` dimension
at 10% that does not exist, and `Model: sonnet` contradicting [ADR-0029]. Deletion is a pending task.

## Testing

**None of these 13 contracts has a test.** Neither does the 829-line `SKILL.md` that orchestrates them.
Contract drift — a renamed heading, a changed numbering style — surfaces only as a silently wrong score.
