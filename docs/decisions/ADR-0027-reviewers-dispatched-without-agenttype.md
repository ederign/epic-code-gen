---
id: ADR-0027-reviewers-dispatched-without-agenttype
title: Reviewers dispatched without agentType
type: adr
status: accepted-under-review
repos: [epic-code-gen]
decisions: [ADR-0021, ADR-0026]
---

# ADR-0027: Reviewers dispatched without `agentType`

## Status

**Accepted, under review.** Recorded retroactively 2026-07-31. This is the decision most likely to
look like a bug to a new reader, which is why it needs an ADR.

## Context

Reviewer agents are declared in `.claude/agents/` with `tools: Read, Glob, Grep` — read-only, which is
what a reviewer should be. But a reviewer's *output* is a file: `review-architecture.md` and friends,
which `score_reviews.py` then parses ([ADR-0022]).

Dispatched with `agentType`, the declared tool list is enforced, the agent has no `Write`, and it cannot
produce its output at all. Dispatched without `agentType`, the agent file is used as instructions and
the subagent inherits the parent's full tool set — including `Write`.

## Decision

Dispatch reviewers and verifiers **without** `agentType`, passing the agent definition as instructions.
`SKILL.md:634` states the rationale inline:

> **Why no agentType:** Reviewer agents are defined with `tools: Read, Glob, Grep` — when dispatched
> with `agentType`, they cannot write review files.

Consequently, **for reviewers the `tools:` line is documentation, not enforcement.** It records intent.

Generators are dispatched *with* `agentType`, because they need their declared tools anyway:
`design-spec-generator`, `spec-reviewer`, `plan-generator`, `ux-ac-extractor` (SKILL.md:287, 378, 416,
440).

## Consequences

### Positive

- Reviewers can write their output, which is the whole requirement.
- The agent definition still serves as the calibration and contract document, which is its main value.

### Negative

- **The `tools:` line means two different things depending on dispatch mode**, and nothing in the file
  says which mode it will be dispatched in. This is a genuine trap.
- Reviewers hold `Write`, `Edit`, and `Bash` while being instructed to be read-only. There is no
  mechanism preventing a reviewer from editing the code it is reviewing.
- It is the same permission surface that let RHAIFIRST-391 happen — the orchestrator writing
  `review-*.md` files itself is possible precisely because writing review files is a permitted action
  for whoever is holding the tools.
- A future harness change to how `agentType` handles tool inheritance would break review silently.

### Revisit when

The harness supports declaring a write target for a read-only agent, or reviewers return findings as
structured output instead of files. Either removes the need for this. Tracked in `docs/tasks/pending/`.
