---
id: ADR-0019-one-subagent-per-skill
title: Each Superpowers skill isolated in its own subagent
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["3ba1751", "1b795d3", "bbce28f", "44da7be"]
decisions: [ADR-0016, ADR-0017]
---

# ADR-0019: Each Superpowers skill isolated in its own subagent

## Status

Accepted (2026-07-11).

## Context

Phase 1 invokes `brainstorming`, then `writing-plans`; Phase 2 invokes
`subagent-driven-development`. Invoking them all from the orchestrator's own context created two
problems.

Skills carry substantial instructions and conversational state. Running two in one context means the
second inherits the first's framing — and `brainstorming`'s "act as a partner, ask questions" posture
is actively wrong for `writing-plans`. Worse, the orchestrator's own instructions (autonomy overrides,
artifact rules, the review loop) compete with the skill's for attention, and the orchestrator still has
to run the review phase afterwards on a context already full of design conversation.

## Decision

One subagent per skill invocation, each with a dedicated agent definition in `.claude/agents/`:

| Agent | Invokes | Writes |
|---|---|---|
| `design-spec-generator` | `brainstorming` | `codegen-spec.md`, `brainstorming-log.md` |
| `plan-generator` | `writing-plans` | `codegen-plan.md`, `writing-plans-log.md` |
| `spec-reviewer` | — (validation gate between them) | `spec-review-log.md` |

The orchestrator passes inputs as prompt variables and receives file paths back. Each subagent gets a
fresh context, its own logging (`44da7be`), and its own explicit output contract.

Because a subagent that silently fails to invoke its skill produces plausible-looking output anyway,
`bbce28f` added **skill invocation verification** plus a labeled conversation log — the log is the
evidence that the skill actually ran. Dispatch is retry-then-fail, not retry-then-fallback.

## Consequences

### Positive

- No cross-contamination of skill framing, and the orchestrator's context stays free for the review
  phase, which is the part that must not be compacted away.
- Each phase's reasoning is captured in its own log file, so a bad spec and a bad plan are separately
  diagnosable.
- Verification closes the "skill never ran" failure, which is otherwise invisible.

### Negative

- Every input must be marshalled explicitly through prompt variables. `iteration-reviewer.md` already
  references a `${BASE_SHA}` that nothing emits — an undefined variable in a prompt template, and a live
  bug (`docs/bugs/open/`).
- Three extra subagent dispatches per epic, each with its own failure mode and timeout.
- The orchestrator cannot see *how* the subagent reasoned, only what it wrote — which is why the logs
  are load-bearing rather than nice-to-have.
