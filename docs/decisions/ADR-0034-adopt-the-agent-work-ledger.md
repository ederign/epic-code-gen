---
id: ADR-0034-adopt-the-agent-work-ledger
title: Adopt the Agent Work Ledger
type: adr
status: accepted
repos: [epic-code-gen]
jira: RHAIFIRST-168
decisions: [ADR-0003, ADR-0027]
---

# ADR-0034: Adopt the Agent Work Ledger

## Status

Accepted (2026-07-31).

## Context

The system works. 24 epics processed across 7 target repos, 5 merged PRs, score progressions like
2.4 → 4.9 → 7.2 → 9.4, ~$80 of logged spend. The engineering record did not keep up:

- **No ADRs.** ~33 real decisions existed only as commit messages, Jira prose, and `if/elif` blocks. The
  nine-state machine was documented nowhere.
- **The best design doc was untracked.** `FOREDER.md` — state machine table, six named decisions with
  rationale, five predicted pitfalls, all five of which came true — was removed from tracking and
  gitignored in `3bd2d3e`, recoverable only via `git show 3bd2d3e^:FOREDER.md`.
- **No CI, no linter** on this repo's 10.5k Python lines, while its entire purpose is enforcing lint on
  other repos.
- **The Jira record was uneven.** ~15 substantial shipped features never got a ticket, and ~20 live
  defects weren't tracked anywhere.
- `epic-code-gen-pipeline/README.md` was unmodified GitLab boilerplate.

The data repo's history is the evidence: 39 of 104 commits are humans hand-editing YAML to unwedge the
pipeline. Every one was a decision made and then forgotten.

## Decision

Adopt [jctanner's Agent Work Ledger](https://gist.github.com/jctanner/7f1d5f132cf3f9b7fc67fbb3e3c8ff4c):
`PLAN.md` as an index, `AGENTS.md` as the handbook, and `docs/` holding architecture, ADRs, phase plans,
milestones, tasks, and bugs — with **state represented by directory placement**, changed via `git mv`.

Adaptations to the upstream format:

1. **One ledger in `epic-code-gen`**, covering all three repos, with a `repos:` frontmatter field. The
   pipeline repo is 16 files of CI glue and the data repo is machine-written; three ledgers would leave
   none of them complete.
2. **Frontmatter on every file**, deliberately *not* registered in `artifact_utils.SCHEMAS` — that module
   governs pipeline runtime artifacts, and coupling docs to it would let a doc typo fail a codegen run.
   `scripts/check_ledger.py` validates it instead.
3. **`## Observed incident` and `## Evidence` added to the bug template.** The best bug reports in this
   project's history (RHAIFIRST-374, 391, 392) carried job URLs, timestamped trace excerpts, and
   reproduction on a pristine checkout. The upstream template would have discarded that.
4. **Jira stays the planning system of record.** Cross-links both ways, no sync automation — a sync script
   is a third thing to break.
5. **The debt was documented, not fixed.** ~20 known defects became `docs/bugs/open/` rather than 20 drive-by
   patches, so the backlog arrives in the format.

The PR companion rule and its check start **advisory**, because a blocking gate while the backlog is still
being seeded would bite every trivial fix. The rule itself is not advisory.

## Consequences

### Positive

- Project state is understandable without chat history, which is the stated goal of the format and the
  actual failure this project had.
- The recurring bug class gets a process countermeasure. The ledger's central rule — *evidence in the file,
  or it isn't done* — is aimed squarely at RHAIFIRST-391, where success was declared with nothing behind it.
- Decisions that look like bugs now have ADRs ([ADR-0027], [ADR-0003]), so a new reader stops "fixing" them.
- First CI on this repo.

### Negative

- Two places to look, Jira and the ledger, with only human discipline keeping them consistent.
- ~115 files of overhead that must be maintained or it rots — and a rotted ledger is worse than none,
  because it is confidently wrong.
- Backfilled entries are reconstructions. They record what landed and what it cost; they cannot recover what
  was considered and rejected. Marked as such in `docs/notes/session-log.md`.
- The companion rule adds friction to every PR, which is the point, and will be resented on the day it
  catches something trivial.
