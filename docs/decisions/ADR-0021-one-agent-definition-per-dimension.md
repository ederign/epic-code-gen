---
id: ADR-0021-one-agent-definition-per-dimension
title: One standalone agent definition per review dimension
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["65ee857", "f74a79c", "daee4d7", "f601ef2", "13e55e0"]
decisions: [ADR-0022, ADR-0027]
---

# ADR-0021: One standalone agent definition per review dimension

## Status

Accepted (2026-06-23, completed 2026-07-11).

## Context

Review started as prose inside `SKILL.md` and as five files in `rubrics/`. Two problems: a reviewer's
instructions were tangled with the orchestrator's, so neither could be changed safely; and the rubrics
were documentation that nothing loaded, so they drifted from reality immediately.

## Decision

Every reviewer and verifier is a standalone agent definition in `.claude/agents/`, one file each, with
frontmatter (`name`, `description`, `tools`) and a full output contract: required sections, findings
grouped under `#### Critical` / `#### Important` / `#### Minor`, and findings numbered `N. **Title**`.

Thirteen agents now: four scored reviewers (architecture, tests, lint, intent), two unscored verifiers
(wiring, interactions — [ADR-0028]), and seven generators/actors.

**A reviewer never writes a score.** Its contract explicitly forbids one; `score_reviews.py` derives
the number from the finding counts ([ADR-0022]). The markdown headings *are* the machine interface.

## Consequences

### Positive

- A dimension's calibration can be tuned without touching the orchestrator, and `24d8078` did exactly
  that across all reviewers at once.
- Agents are diffable and reviewable as files, which is what made the calibration pass auditable.
- Adding a dimension is adding a file plus a row in `review_cycle.py`'s `REVIEWERS` table.

### Negative

- **`rubrics/` was never deleted.** 424 lines of superseded calibration still in the tree, and it is
  actively wrong: architecture 20% (real: 30%), tests 25% (real: 30%), intent 25% (real: 20%), a
  `patterns` dimension at 10% that does not exist, and `Model: sonnet` contradicting [ADR-0029]. A
  reader cannot tell which file governs. Tracked in `docs/bugs/open/`.
- The contract is enforced by regex over markdown. `_extract_findings` returns **zeros** on an
  unrecognized heading rather than erroring, so a prompt drift becomes a silently perfect score.
- Thirteen prompt files, no tests. Contract drift is only visible as a wrong number downstream.
