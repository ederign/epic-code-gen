---
id: ADR-0029-agents-inherit-session-model
title: All agents inherit the session model
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["527fc9d", "5e19a14", "294b19f"]
---

# ADR-0029: All agents inherit the session model

## Status

Accepted (2026-07-09).

## Context

Early on, agents carried per-agent model overrides — the `rubrics/` files still say `Model: sonnet`.
The intent was cost control: use a cheaper model for mechanical review, reserve the expensive one for
implementation.

It did not survive contact. Reviewer quality was visibly worse, and because scores were reviewer-chosen
at the time ([ADR-0022] came later), a weaker reviewer produced a *higher* score — less thorough
analysis, fewer findings, more optimism. Cost control was buying worse gates.

There was also a maintenance problem: model identifiers appeared in agent definitions, in `SKILL.md`, in
`rubrics/`, and in shell defaults. Changing model meant finding all of them, and they disagreed.

## Decision

**No per-agent model overrides.** Every subagent inherits the session model. `527fc9d` removed all
sonnet references from the repo; `5e19a14` forced opus for SDD implementers, which under this rule means
"do not let SDD pick something else"; `294b19f` had already moved all reviewers to opus.

`CLAUDE.md` states it: *"all agents run on opus (inherited from session). No model overrides — all
subagents inherit the session model."*

## Consequences

### Positive

- One place to change the model: the session invocation.
- Review quality is uniform, so a score difference between two epics reflects the code, not which model
  happened to review it.
- Removes a confound from every quality comparison across runs.

### Negative

- Most expensive option for every task, including mechanical ones. The ~$80 logged spend across 39
  passes is all opus.
- **The rule is contradicted in the tree.** `ci-scripts/run-claude.sh` defaults to
  `--model ${CLAUDE_MODEL:-claude-opus-4-6}`, which pins a specific model rather than inheriting, while
  `README.md`, `CLAUDE.md`, and `SKILL.md` all say agents inherit the session model. Both statements
  cannot be true. Tracked in `docs/bugs/open/`.
- `rubrics/` still says `Model: sonnet`, so a reader who finds that file first gets the opposite of the
  current rule ([ADR-0021]).
- No mechanism enforces it — a future agent definition adding a `model:` field would just work.
