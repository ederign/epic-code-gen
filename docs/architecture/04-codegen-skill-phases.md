---
id: 04-codegen-skill-phases
title: The /epic-codegen skill — four phases, fourteen steps
type: plan
status: current
repos: [epic-code-gen]
decisions: [ADR-0016, ADR-0017, ADR-0018, ADR-0019, ADR-0020]
---

# The `/epic-codegen` skill

`.claude/skills/epic-codegen/SKILL.md`, 829 lines. Handles **one epic per invocation**.

```
/epic-codegen EPIC_ID [--max-iterations N] [--dry-run] [--fork-owner USER]
              [--gh-token-var VARNAME] [--checks lint,test,typecheck]
```

Defaults: `--max-iterations 10`, `--fork-owner dora-the-ai-coder`,
`--gh-token-var EPIC_CODEGEN_GITHUB_TOKEN`.

Two framing rules from the preamble: **the epic strategy IS the product owner**, and **every script runs
from the project root**, never from inside `.target-repo/`.

## Autonomous operation

SDD has 12 human checkpoints; an autonomous pipeline cannot stop at any of them ([ADR-0017]). `SKILL.md`
maps each to a resolution derived from the epic's acceptance criteria — pre-flight conflicts, implementer
questions, `BLOCKED`, `NEEDS_CONTEXT`, plan-mandated findings, finishing — plus a clarifications table
covering continuous execution, `DONE_WITH_CONCERNS`, reviewer ⚠️ marks, fix-report validation, and the
progress ledger. SDD's own final review and finishing steps are skipped, because this pipeline has its
own review phase.

## Phase 1 — Spec & Plan (steps 1–9)

| Step | What |
|---|---|
| 1 | Parse the epic-task file |
| 2 | Init state (`tmp/epic-codegen-<EPIC_ID>.json`) — [ADR-0004] |
| 3 | Clone the target repo, create `epic/<EPIC_ID>` |
| 4 | Validate + readiness, short-circuiting on `pre-setup.json` if the orchestrator pre-staged it |
| 5 | Read the strategy, including the **authoritative** "Staff Engineer Input" section |
| 6 | Read repo context — scan every agent-readiness file: `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `GEMINI.md`, `COPILOT.md`, `CONVENTIONS.md`, `CONSTITUTION.md` |
| **7a–7d** | **Pattern discovery** — explicit refs · concept search · target file + 5–10 siblings + sibling dirs + callers · conventions docs ([ADR-0018]) |
| 7.5 | Parse the UX prototype via `node scripts/parse_prototype.js` ([ADR-0020]) |
| 7.6 | Extract UX ACs → `ux-acceptance-criteria.md` |
| 8 | Write `context-brief.md`, dispatch `design-spec-generator` → **brainstorming** ([ADR-0016]). Retry-then-**fail**, never fallback |
| 8.5 | **Spec review gate** — `spec-reviewer` validates the spec against real repo patterns |
| 9 | Dispatch `plan-generator` → **writing-plans**, then 4-point plan validation |

Step 7 must complete **before** step 8 (`9b65e8c`), or the design gets invented and then justified.

## Phase 2 — Implementation (steps 10–13.5)

| Step | What |
|---|---|
| 10 | Record `BASE_SHA` |
| 11 | Init `.target-repo/.superpowers/sdd/` |
| 12 | `Skill("superpowers:subagent-driven-development")` with the autonomy overrides |
| 13 | Save version artifacts. **`validation.json` via `validate_target.py --out` — NEVER hand-written** ([ADR-0024]) |
| 13.5 | Wiring verification ([ADR-0028]) |

## Phase 3 + 4 — Review, iterate, complete (step 14)

The 9-step **review dispatch loop**, delegated to `review_cycle.py` ([ADR-0026]) and documented in
[06-review-and-scoring.md](06-review-and-scoring.md). Two hard rules live here:

- **Never write review files yourself.** They are the reviewers' output; authoring them is fabricating
  evidence. This is exactly what RHAIFIRST-391 did.
- **No `agentType` for reviewers** — with it they cannot write their review files ([ADR-0027]).

Progress is logged to `tmp/progress.log`, which `run-codegen.sh`'s heartbeat tails every 300s so a 6-hour
run is observable.

Post-loop: `pass` → save final diff · `near-miss` (≥7.0) → PR anyway on exhaustion · `fail` with budget
left → triage → fix → new version.

## Reference sections

`SKILL.md` also carries `## Run Metadata` (the two-writer ownership rule — [ADR-0014]),
`## Model Selection`, `## Review Dimensions`, `## State Recovery`, `## Error Handling`, `## Rules` (11
hard rules), and — the most useful artifact in the file — a **21-row `## File Handoffs` table** mapping
each artifact to its writer and reader. That table is the direct ancestor of
[03-artifact-contracts.md](03-artifact-contracts.md).

## Caveats

- **829 lines of orchestration with no tests.** Every rule in it is a prompt instruction, so every rule is
  advisory in the way prompts are advisory — which is the root of RHAIFIRST-391.
- Step 4's `pre-setup.json` short-circuit reads a `validation` object the orchestrator captured **before**
  installing dependencies. Currently harmless (only `language` is used) but a loaded gun; open bug.
- `--dry-run` produces a diff and no PR.
