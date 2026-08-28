# Architecture Decision Records

Why the system is built the way it is. For *how* it is built, see
[`../architecture/`](../architecture/).

These were written on 2026-07-31 by reverse-engineering the decisions from git history, the
[RHAIFIRST-168](https://redhat.atlassian.net/browse/RHAIFIRST-168) Jira tree, and the recovered
`FOREDER.md`. Each cites the commits or issue that carried it, so any claim here can be checked
against the diff. The decisions themselves were made on the dates shown, not the date they were
written down — that gap is the problem this ledger exists to close.

When to add one: [AGENTS.md §3](../../AGENTS.md#when-to-write-an-adr).

## Foundations

| ADR | Title | Status |
|---|---|---|
| [0001](ADR-0001-artifacts-as-gitignored-filesystem-tree.md) | Artifacts as a gitignored filesystem tree | Accepted |
| [0002](ADR-0002-frontmatter-as-metadata-contract.md) | YAML frontmatter as the metadata contract | Accepted |
| [0003](ADR-0003-flat-modules-not-a-package.md) | Flat `sys.path` modules instead of an installable package | Accepted, under review |
| [0004](ADR-0004-state-survives-context-compaction.md) | State persisted to `tmp/` so it survives context compaction | Accepted |

## Topology

| ADR | Title | Status |
|---|---|---|
| [0005](ADR-0005-three-repo-split.md) | Three-repo split: brains, CI shell, data store | Accepted |
| [0006](ADR-0006-strategy-is-the-unit-of-work.md) | Strategy, not epic, is the unit of work | Accepted |
| [0007](ADR-0007-jira-is-the-source-of-truth.md) | Jira is the source of truth for eligibility and dependencies | Accepted |
| [0008](ADR-0008-data-repo-as-state-store.md) | The data repo, not Jira, is the state store | Accepted |
| [0009](ADR-0009-convergence-loop.md) | Convergence loop: one run advances each epic one step | Accepted |
| [0010](ADR-0010-thin-ci-shell-fat-python.md) | Thin CI shell, fat Python | Accepted |
| [0011](ADR-0011-fat-container-image.md) | Fat container image over runtime installs | Accepted |
| [0012](ADR-0012-run-orchestrator-directly-in-ci.md) | Run the orchestrator directly in CI, not wrapped in Claude Code | Accepted |

## State integrity

| ADR | Title | Status |
|---|---|---|
| [0013](ADR-0013-one-owner-per-status-field.md) | Nine CI states; one owner per status field | Accepted |
| [0014](ADR-0014-merge-never-write-run-metadata.md) | Merge, never write, `run-metadata.yaml` | Accepted |
| [0015](ADR-0015-normalize-on-read-fail-loudly.md) | Normalize foreign states on read; fail loudly on the rest | Accepted |

## Generation

| ADR | Title | Status |
|---|---|---|
| [0016](ADR-0016-spec-first-generation.md) | Spec-first generation via Superpowers brainstorming | Accepted |
| [0017](ADR-0017-sdd-for-implementation.md) | Superpowers SDD for implementation; orchestrator is the human partner | Accepted |
| [0018](ADR-0018-pattern-discovery-before-design.md) | Pattern discovery runs before design, enforced | Accepted |
| [0019](ADR-0019-one-subagent-per-skill.md) | Each Superpowers skill isolated in its own subagent | Accepted |
| [0020](ADR-0020-prototype-driven-ux-acs.md) | Prototype-driven UX acceptance criteria | Accepted |

## Review

| ADR | Title | Status |
|---|---|---|
| [0021](ADR-0021-one-agent-definition-per-dimension.md) | One standalone agent definition per review dimension | Accepted |
| [0022](ADR-0022-deterministic-scoring.md) | **Reviewers classify severity; Python computes the score** | Accepted |
| [0023](ADR-0023-critical-caps-the-dimension.md) | A Critical finding caps its dimension at 5 | Accepted |
| [0024](ADR-0024-validation-authenticity-gate.md) | Reject a `validation.json` the skill wrote itself | Accepted |
| [0025](ADR-0025-unrunnable-is-not-failed.md) | `unrunnable` ≠ `failed`; preflight gates codegen | Accepted |
| [0026](ADR-0026-python-owns-determinism.md) | Python owns the loop; the model owns only triage | Accepted |
| [0027](ADR-0027-reviewers-dispatched-without-agenttype.md) | Reviewers dispatched without `agentType` | Accepted, under review |
| [0028](ADR-0028-unscored-verifiers.md) | Unscored verifiers inform triage but never score | Accepted |
| [0029](ADR-0029-agents-inherit-session-model.md) | All agents inherit the session model | Accepted |

## Delivery

| ADR | Title | Status |
|---|---|---|
| [0030](ADR-0030-fork-based-prs-under-a-bot.md) | Fork-based PRs under a bot identity | Accepted |
| [0031](ADR-0031-rebase-every-review-cycle.md) | Rebase every review cycle; `--force-with-lease` | Accepted |
| [0032](ADR-0032-review-response-never-regenerates.md) | Review response commits on top; never regenerates | Accepted |
| [0033](ADR-0033-iteration-budget-and-near-miss.md) | Iteration budget of 10, near-miss PR on exhaustion | Accepted |
| [0035](ADR-0035-per-repo-github-identity.md) | Per-repo GitHub identity, overriding the shared bot | Accepted |

## Meta

| ADR | Title | Status |
|---|---|---|
| [0034](ADR-0034-adopt-the-agent-work-ledger.md) | Adopt the Agent Work Ledger | Accepted |
