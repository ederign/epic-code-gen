---
id: ADR-0031-rebase-every-review-cycle
title: Rebase every review cycle; push with --force-with-lease
type: adr
status: accepted
repos: [epic-code-gen]
jira: RHAIFIRST-376
commits: ["164d21e"]
decisions: [ADR-0030, ADR-0032]
---

# ADR-0031: Rebase every review cycle; push with `--force-with-lease`

## Status

Accepted (2026-07-29, RHAIFIRST-376).

## Context

Because progress happens one step per run ([ADR-0009]) and PRs wait on human review, an epic branch can
sit for days while upstream moves. Two consequences: the PR drifts into a CONFLICTING state and stops
being mergeable, and — worse — the fix agent authors changes against code that is no longer current, so
a "fix" can conflict with or duplicate work that landed upstream meanwhile.

## Decision

**Rebase onto the latest upstream base at the start of every review-response cycle**, before addressing
any comments. `scripts/rebase_pr.py`:

```bash
python3 scripts/rebase_pr.py <repo-path> <branch> [--base main] \
    [--remote origin] [--push-remote fork] [--no-resolve] [--json]
```

`review_response.py` runs it automatically; `--skip-rebase` opts out.

Conflict resolution splits responsibility deliberately: **`rebase_onto_base()` drives the git sequence
itself** (add / continue / skip / abort), and a Claude subagent is given only the working tree to edit.
The model never runs git. `MAX_CONFLICT_ROUNDS = 10`, `CONFLICT_AGENT_TIMEOUT = 900`.

A rebase rewrites history, so the result is pushed with **`--force-with-lease`**
(`rebase_pr.py:233`), never a plain force and never a plain push — the lease is what prevents clobbering
a concurrent push.

One extra rule: **a cycle that rebases nothing and finds no actionable comments does not consume an
iteration.** Otherwise an unaddressable review loops until the budget is exhausted ([ADR-0033]).

## Consequences

### Positive

- PRs stay mergeable, and fixes are authored against current code.
- Same division of labour as [ADR-0026]: the model does the judgment (how to resolve a conflict), Python
  does the procedure (the git state machine). Git sequences are exactly what a model gets wrong under
  pressure.
- `--force-with-lease` makes the history rewrite safe against a concurrent push instead of merely
  likely-safe.

### Negative

- Rewritten history invalidates existing review comment anchors, so inline comments on old commits can
  become orphaned.
- A rebase can fail in ways the subagent cannot resolve, and then the cycle is stuck needing a human —
  one of the recurring manual-intervention causes in the data repo.
- Rebasing on every cycle is work even when upstream hasn't moved.
- The no-op exemption is a special case in iteration accounting, which makes "how many iterations has
  this epic used" a slightly awkward question — and `current_version` vs `versions` already disagree for
  related reasons.
