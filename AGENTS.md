# AGENTS.md — Operational Handbook

The handbook for anyone working in this repo, human or agent. `CLAUDE.md` holds the
never-violate runtime rules and the script reference; this file holds the process.

Read this before your first change. Read [`PLAN.md`](PLAN.md) to find out what to work on.

---

## 1. What this system is

Given an approved RHAISTRAT strategy and its epic decomposition, generate implementation code
against target repos, review it, and open a PR — autonomously. One parameterized epic per run.

```
RFE (rfe-creator)
  → Strategy (strat-creator)
    → Epic decomposition (epic-creator)
      → Code generation (epic-code-gen)   ← this system
        → PR on target repo → CI → human review → merge
```

Tracked in Jira under [RHAIFIRST-168](https://redhat.atlassian.net/browse/RHAIFIRST-168)
("Epic Code Generation — Hardening & Production Rollout").

### The four repos

| Repo | Host | Role |
|---|---|---|
| **epic-code-gen** | GitHub `ederign/epic-code-gen` | The brains. Skill, agents, all orchestration logic. **The ledger lives here.** |
| **epic-code-gen-pipeline** | GitLab `redhat/rhel-ai/agentic-ci/` | Thin GitLab CI shell. Clones this repo, runs it, pushes results. |
| **epic-code-gen-pipeline-data** | GitLab `redhat/rhel-ai/agentic-ci/` | Git-as-database. Durable state + per-epic artifacts. Machine-written. |
| **epic-code-gen-dashboard** | GitLab `redhat/rhel-ai/agentic-ci/` | Reads the data repo, publishes to GitLab Pages. |

Design rationale for the split is [ADR-0005](docs/decisions/). Full topology is
[`docs/architecture/01-system-overview.md`](docs/architecture/01-system-overview.md).

---

## 2. The ledger

This repo uses a filesystem-native work ledger, adapted from
[jctanner's Agent Work Ledger](https://gist.github.com/jctanner/7f1d5f132cf3f9b7fc67fbb3e3c8ff4c).
It exists so that **project state can be understood without chat history**, and so that an agent
which has lost all context can resume.

```
PLAN.md                  Navigation index. Not the plan.
docs/
  architecture/          How the system is built. Explanatory, not chronological.
  decisions/             ADR-NNNN-*.md — why it is built that way.
  plans/                 Phase plans, the arc of the work.
  milestones/            Groupings that map to Jira epics.
  tasks/{pending,current,blocked,done}/
  bugs/{open,fixed,wontfix}/
  notes/session-log.md   Dated activity log.
```

### Five principles

1. **`PLAN.md` is an index, not the plan.** It links out. It never grows content of its own.
2. **Tasks are files.** One file per meaningful unit of work.
3. **State is location.** A task's status is the directory it sits in. Change status with
   `git mv`, so the transition appears in the diff and in `git log --follow`.
4. **Decisions are recorded.** If you chose between real alternatives, write an ADR. Chat history
   and commit messages are not durable enough — that gap is why this ledger exists.
5. **Bugs are first-class.** Record a defect **when you discover it**, even if you are not fixing
   it, even if you caused it. An unrecorded bug is indistinguishable from a bug nobody knows about.

### Frontmatter

Every ledger file starts with:

```yaml
---
id: task-deterministic-scoring     # kebab-case; must equal the filename minus .md
title: Compute review scores from findings, not reviewer judgment
type: task                         # task | bug | adr | milestone | plan
status: done                       # must agree with the directory it is in
repos: [epic-code-gen]             # which repos this touches
jira: RHAIFIRST-374                # omit if unticketed
commits: [a7326fe, 788f16f]        # REQUIRED for done/fixed. Evidence.
decisions: [ADR-0022]              # optional cross-links
---
```

This is deliberately **not** registered in `scripts/artifact_utils.py` `SCHEMAS`. That module
governs pipeline runtime artifacts; coupling docs to it would let a doc typo fail a codegen run.
`scripts/check_ledger.py` validates ledger frontmatter instead.

Link related ledger files inline with `[[id]]`. A `[[id]]` that doesn't resolve yet is fine — it
marks something worth writing.

### Templates

**Task** — `docs/tasks/<state>/<kebab-title>.md`

```markdown
# Task: <title>

## Goal
## Context
## Acceptance Criteria
- [ ] ...
## Files Likely Involved
## Status
## Notes
```

**Bug** — `docs/bugs/<state>/<kebab-title>.md`

```markdown
# Bug: <title>

## Summary
## Reproduction
## Expected
## Actual
## Impact          <!-- Critical | High | Medium | Low -->
## Related Tasks

<!-- Optional, and strongly preferred when they exist: -->
## Observed incident   <!-- dates, job URLs, trace excerpts -->
## Evidence            <!-- artifact paths, file:line, reproduction on a clean checkout -->
```

`## Observed incident` and `## Evidence` are local additions to the upstream template. The best
bug reports in this project's history (RHAIFIRST-374, 391, 392) had them, and dropping them would
have thrown away the forensics that made those bugs fixable.

**ADR** — `docs/decisions/ADR-NNNN-<kebab-title>.md`

```markdown
# ADR-NNNN: <title>

## Status
<!-- Proposed | Accepted | Accepted, under review | Superseded by ADR-NNNN | Rejected -->
## Context
## Decision
## Consequences
### Positive
### Negative
```

Number ADRs sequentially, never reuse a number, never renumber. Superseding an ADR means writing a
new one and editing the old one's Status — not editing the old one's Decision.

---

## 3. The PR companion rule

> **Every PR must reference at least one ledger file in its `## Ledger` section.**
>
> - New or changed behavior → a file in `docs/tasks/`, moved to `done/` in the same PR that lands
>   the work.
> - A defect → a file in `docs/bugs/`, created **when discovered** (even if not fixed), moved to
>   `fixed/` by the PR that fixes it.
> - An architectural decision → an `ADR-NNNN` in `docs/decisions/`, added in the same PR as the
>   change it justifies.
> - Docs-only, typo, or dependency-bump PRs: write `Ledger: none — <reason>`.
>
> **A task or bug is not done until its Acceptance Criteria are checked and the evidence — commit
> SHAs, test names, job URLs — is recorded in the file. Do not declare success in the PR body and
> leave the ledger file empty.**

That last paragraph is the whole point. The failure it prevents is real and recent: in
RHAIFIRST-391 the orchestrator wrote its own review files, dismissed a reviewer's Critical
finding, estimated scores in prose rather than computing them, and opened a PR — and the job
exited 0 reporting success. Recording evidence is what makes "done" falsifiable.

`scripts/check_ledger.py` enforces a weak form of this in CI. It is **advisory** today
(warns, doesn't block) while the backlog is still being seeded; flipping it to blocking is its own
pending task. The rule is not advisory.

### Companion Jira — on demand

Every feature and bug should have a companion Jira issue under
[RHAIFIRST-168](https://redhat.atlassian.net/browse/RHAIFIRST-168), **opened when it is needed, not
eagerly.** The ledger file comes first and is always required; the Jira issue is the outward-facing
half and gets created when someone outside this repo needs to see it.

Open one when any of these is true:

- The work is being planned, scheduled, or reported on outside this repo.
- Someone else needs to be assigned to it, or it needs to block/relate to other Jira work.
- It is a defect with real consequences that a stakeholder should know about.
- You are about to start work on it.

Don't open one for: internal hygiene the team already agreed on, a bug you are fixing in the same PR
that found it, or anything that would exist only to satisfy a rule.

When you do open one:

1. Add `jira: RHAIFIRST-NNN` to the ledger file's frontmatter.
2. Put the ledger path in the Jira issue, so the link is bidirectional.
3. Keep Jira the **summary** and the ledger file the **detail** — do not maintain the same prose twice.
   The Jira description should be enough to triage; the ledger file is where the evidence lives.

`check_ledger.py` deliberately does **not** require `jira:`. A `done` or `fixed` file needs evidence —
commit SHAs *or* a Jira key — so unticketed work can still close honestly on commits alone. That is why
several backfilled tasks carry commits and no Jira: the work shipped before anyone thought to file it,
and inventing tickets after the fact would be theatre.

Cross-links go stale silently. If a Jira issue's status and its ledger file's directory disagree, the
ledger is what you are looking at — fix whichever is wrong, and prefer moving the file to editing the
status field.

### When to write an ADR

Write one if any of these is true:

- You chose between approaches that a competent engineer might reasonably have decided differently.
- You are accepting a known cost (duplication, a manual step, a fat image) to buy something.
- You are doing something that will look like a mistake to someone who doesn't know why.
- You are reversing or narrowing an earlier decision.

The third case matters most here. Several of this system's sharpest choices look wrong on sight:
reviewers are dispatched *without* `agentType` so they can inherit `Write` ([ADR-0027]); merge
logic is *deliberately* duplicated across a repo boundary ([ADR-0014]); `stream-claude.py` kills
its parent with `SIGTERM` and exits 42 on purpose. Each needed an ADR and didn't have one.

---

## 4. Working agreements

### Testing

- After any change under `scripts/`: `make test-unit`.
- Before pushing: `make test-unit` and `python3 scripts/check_ledger.py --all`.
- **A change is not done until tests pass.** Not "tests pass locally except one" — pass.
- New logic gets tests in the same PR. `scripts/check_ledger.py` is not exempt.

Current suite: **703 tests** across 19 files in `tests/`, ~2.5 min.

> **Do not use `make test`** — it always fails. It depends on `test-integration`, which runs
> `pytest -m integration`; nothing carries that marker, so pytest exits 5 and make reports a failure
> regardless of results. This has been true on `main` since the marker was added. See
> [[bug-make-test-fails-on-empty-integration-target]] and [[task-fix-make-test-target]]; once fixed,
> `make test` becomes the right command again. (`README.md` also claims 186 tests; it is stale by 517.)

### Evidence standard

This system's core failure mode is **confident, plausible, wrong**. It reviews its own generated
code, so an unverified claim becomes a score becomes a merged PR. Hold yourself to the standard the
reviewers are held to:

- Read the source before asserting a mechanism. Cite `file:line`.
- "Works because X" needs the lines that prove X, or it doesn't go in.
- Don't trust a commit subject as a description of a commit's contents. Read the diff.
- Don't trust a subagent's report as fact. It is a lead. Verify before recording.
- Reporting that something failed is always better than reporting a success that isn't real.

### Hard rules

These have all been violated at least once and cost a day each. See `CLAUDE.md` for the full list
with commands.

1. **Never write `run-metadata.yaml` whole — always merge.** Two producers share the file. A
   whole-file write deletes the other's fields and silently deadlocks the epic (RHAIFIRST-374).
2. **A check that couldn't run is `unrunnable`, not `failed`.** Scoring an environment fault as
   bad code once produced `lint=5.0` from a missing `uv`.
3. **Never hand-write `validation.json`.** Use `validate_target.py --out`. The authenticity gate
   exists because a hand-written file once scored `lint=8.0` while Prettier was failing.
4. **Run all scripts from the project root**, never from inside `.target-repo/`.
5. **Never run `run_pipeline.py` locally.** It runs in CI only. `--dry-run` is fine.

### Commits and PRs

- Branch from `main`; don't commit to `main` directly.
- Subject line says what changed and, where it fits, why: `Stop the review-response path hiding
  why the fix agent failed` beats `fix review response`.
- Reference the Jira key when one exists.
- Keep a PR to one phase or one concern. Five reviewable PRs beat one 115-file PR.

---

## 5. Workflow

1. Read `PLAN.md`.
2. Pick a task from `docs/tasks/pending/` (or write one — unplanned work still gets a file).
3. `git mv` it to `docs/tasks/current/`, set `status: current`. Commit that alone, so the claim is
   visible before the work lands.
4. Do the work. Append discoveries to the task's `## Notes` as you go, not at the end.
5. File a bug the moment you find one — separate file, `docs/bugs/open/`. Do not fold an
   unrelated fix into your task.
6. Write an ADR if you made a decision (§3).
7. Check the Acceptance Criteria boxes and record evidence: commit SHAs, test names, job URLs.
8. `git mv` to `docs/tasks/done/`, set `status: done`, fill `commits:`.
9. Update `PLAN.md` if the active set changed.
10. Append an entry to `docs/notes/session-log.md`.

If you end up blocked: `git mv` to `docs/tasks/blocked/`, and record in `## Notes` what
specifically unblocks it. "Blocked" with no exit condition is abandonment with better branding.

---

## 6. Conventions

- **Python**: stdlib only where practical. The only runtime dependency is `pyyaml`. Modules are
  flat in `scripts/` with `sys.path.insert` bootstrapping rather than an installed package — a
  deliberate choice under review ([ADR-0003]).
- **No new YAML parser.** There are already six. Use `artifact_utils.read_frontmatter`.
- **No new HTTP client.** Use `jira_utils` or `github_utils`.
- **Agent definitions** live in `.claude/agents/`, one file per agent. A reviewer's `tools:` line
  is documentation, not enforcement ([ADR-0027]).
- **Reviewers classify severity; Python computes scores.** Never let a model choose a number
  ([ADR-0022]).
- **Artifacts** are written under `artifacts/` (gitignored) and persisted to the data repo by CI.

Full reference: `CLAUDE.md`. Contracts for every artifact file:
[`docs/architecture/03-artifact-contracts.md`](docs/architecture/03-artifact-contracts.md).
