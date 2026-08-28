---
id: ADR-0018-pattern-discovery-before-design
title: Pattern discovery runs before design, enforced
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["d3a5a24", "37a1d67", "9b65e8c", "69b74cf", "c58f98a"]
decisions: [ADR-0016]
---

# ADR-0018: Pattern discovery runs before design, enforced

## Status

Accepted (2026-07-11).

## Context

The highest-weighted review dimension is architecture at 30%, and it scores whether generated code
matches the target repo's conventions. Those conventions cannot be inferred from an epic description —
they only exist in the repo.

Two failures were happening. First, discovery was too shallow: one reference file was not enough to
establish a convention. Second, and worse, the ordering was unenforced — the design subagent would
begin designing before discovery had run, inventing an approach and then looking for evidence to
support it. A spec written that way passes a spec review that only checks internal consistency.

## Decision

**Four-part discovery, in Phase 1 Step 7, before any design work:**

| Step | What |
|---|---|
| 7a | Explicit references named in the epic or strategy |
| 7b | Concept search — find how this *kind* of thing is done here (`37a1d67`) |
| 7c | The target file, **5–10 siblings**, sibling directories, and callers (`d3a5a24`) |
| 7d | Conventions docs — every agent-readiness file present |

7d scans `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `GEMINI.md`, `COPILOT.md`, `CONVENTIONS.md`, and
`CONSTITUTION.md` (`69b74cf`, `c58f98a`), with no cap on how many convention lines are read — an earlier
cap was truncating the rules mid-file.

**The ordering is enforced, not requested** (`9b65e8c`): discovery must complete before brainstorming is
dispatched. The results are written to `context-brief.md` and passed in, so the design subagent works
from gathered evidence rather than gathering its own.

## Consequences

### Positive

- The design starts from what the repo does, which is what the architecture reviewer will measure it
  against. Discovery and review are looking at the same thing.
- Reading a target repo's own `AGENTS.md`/`CLAUDE.md` means honoring conventions its maintainers wrote
  down — the single cheapest way to make a generated PR acceptable.
- `context-brief.md` is a durable artifact (present for 9 epics), so a bad spec can be diagnosed as
  bad input vs bad reasoning.

### Negative

- Expensive. 5–10 siblings plus sibling directories plus callers is a lot of reading before any output,
  all of it on the critical path.
- Context pressure. Discovery output competes with the epic, strategy, and plan for the same window;
  this is part of why compaction recovery matters ([ADR-0004]).
- Enforcement is a prompt instruction in `SKILL.md`, not a mechanism. Nothing structurally prevents a
  future agent from designing first — the same class of gap as RHAIFIRST-391.
- Discovery quality is invisible: a shallow pass and a thorough pass produce the same artifact shape.
