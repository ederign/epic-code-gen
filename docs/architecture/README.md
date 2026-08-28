---
id: architecture-readme
title: Architecture — index
type: plan
status: current
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
---

# Architecture

How the system is built. For *why*, see [`../decisions/`](../decisions/). For process, see
[`AGENTS.md`](../../AGENTS.md).

| Doc | Read it when |
|---|---|
| [01 — System overview](01-system-overview.md) | You are new. Start here. |
| [02 — Pipeline state machine](02-pipeline-state-machine.md) | An epic is stuck, or you're changing `run_pipeline.py` |
| [03 — Artifact contracts](03-artifact-contracts.md) | You're reading or writing any pipeline file |
| [04 — Codegen skill phases](04-codegen-skill-phases.md) | You're changing `SKILL.md` |
| [05 — Agent roster](05-agent-roster.md) | You're changing an agent, or a score looks wrong |
| [06 — Review and scoring](06-review-and-scoring.md) | You're touching the review loop or the rubric |
| [07 — Target repo lifecycle](07-target-repo-lifecycle.md) | You're onboarding a target repo or debugging a PR |
| [08 — CI topology](08-ci-topology.md) | A CI job failed, or you're changing the image |
| [09 — Secrets and environment](09-secrets-and-environment.md) | You need a credential or an env var |
| [10 — Known limitations](10-known-limitations.md) | Before you promise anyone this is production-ready |
| [99 — FOREDER.md (historical)](99-historical-foreder.md) | You want the original design rationale, recovered |

## How a Jira epic becomes a merged PR

One paragraph, then go read [01](01-system-overview.md).

An operator sets `STRATEGY_KEYS` and triggers the GitLab job. The orchestrator asks **Jira** which epics
exist under those strategies and builds a dependency DAG from "Blocks" links. For each epic it reads
current state from the **data repo** and takes **exactly one action** — that's the whole design: progress
happens across runs, not within one, so the pipeline never blocks waiting on a human. When the action is
"generate", it clones the target repo, checks the toolchain is present *before* spending anything, then
hands one epic to the `/epic-codegen` skill. The skill discovers how this repo actually does things, has a
design conversation with itself, writes a plan, implements it via Superpowers SDD, and then submits the
diff to six reviewers. Four of them classify findings by severity and **Python computes the score** — no
model ever picks a number. Score ≥ 8.0 with no dimension below 6.0 opens a PR from a bot's fork, using the
target repo's own PR template. Below that, triage picks what to fix and the loop runs again, up to ten
times. Once the PR is open, later runs rebase it onto current upstream and answer review comments as new
commits on the same branch — never by regenerating. When the PR merges, the epic is `Done`.

## The one thing to understand

This system's characteristic failure is **not** a wrong answer. It is a *confident* answer with nothing
behind it — a PR opened from a version that was never reviewed, a score estimated in prose, an epic marked
`completed` in a vocabulary nothing reads, a fabricated `validation.json` scoring 8.0 while the linter was
failing. Five of the twelve epics under RHAIFIRST-168 are that bug in a new place.

Almost every design decision here is a countermeasure. Scores are arithmetic, not judgment
([ADR-0022]). The loop is Python, not prose ([ADR-0026]). Evidence documents are checked for provenance
([ADR-0024]). An unknown state fails loudly instead of skipping quietly ([ADR-0015]). An environment
fault is not the epic's fault ([ADR-0025]).

If you change something here, the question to ask is: *what would make this lie, and what would catch it?*
