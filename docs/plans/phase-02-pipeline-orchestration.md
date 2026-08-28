---
id: phase-02-pipeline-orchestration
title: "Phase 02 — Pipeline orchestration: Jira-direct, fork PRs, CI state machine"
type: plan
status: done
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
jira: RHAIFIRST-200
commits: ["46a08cd", "5bca12a", "a0de047", "c98dbbc", "356a192", "f719edd", "0bfd075"]
---

# Phase 02 — Pipeline orchestration

**2026-06-26 → 2026-06-30. 38 commits here, plus the pipeline and data repos created from scratch
on 06-30.** Jira: RHAIFIRST-200, RHAIFIRST-201 … 205.

## Goal

Go from "a human runs `/epic-codegen` on one epic" to "a GitLab job processes every eligible epic
in a strategy, unattended, and opens real PRs."

## What shipped

**Jira became the input, not HTML reports** (`46a08cd`). `fetch_jira_epics.py` pulls child work
items directly, builds a dependency DAG from "Blocks" links, and classifies each epic's
eligibility from its current Jira status. Real Jira keys became `epic_id`. This is what makes the
system restartable: eligibility is recomputed from Jira every run rather than tracked internally
([ADR-0007]).

**The orchestrator** (`5bca12a`). `run_pipeline.py` processes multiple strategies, resolves each
epic's target repo (keyword match from `config/repo_mapping.json`, LLM fallback), and shells out to
the skill. Strategy — not epic — is the unit of work, because dependencies are per-strategy
([ADR-0006]).

**Autonomous delivery.** Fork creation, push-to-fork, and PR creation for CI environments
(`a0de047`), git identity derived from the GitHub token (`5d7c799`), a default bot fork owner
(`2cfab1e`, `3e83c09`), fork sync before branching (`addaaa3`). Jira transitions (`8b53239`) and PR
links posted back as comments (`e9d023d`). See [ADR-0030].

**Idempotence** (`2e59f0c`). Skip active epics, reconcile merged PRs — so re-running is safe. This
is the beginning of the convergence-loop model ([ADR-0009]).

**The CI state machine** (`c98dbbc`, 15 tests in `80f81ad`). Nine states, one action per epic per
run. `f719edd` added PR lifecycle management (13 tests in `3b903ac`).

**The container** (`356a192`). `Dockerfile.ci` on UBI9 with Go, Node, Python, and Claude Code baked
in — a fat image, deliberately ([ADR-0011]).

**Two new repos, 06-30.** `epic-code-gen-pipeline` (GitLab CI shell: `.gitlab-ci.yml`,
`ci-scripts/`, `push-results.py`) and `epic-code-gen-pipeline-data` (git-as-database). See
[ADR-0005], [ADR-0008].

**Pre-setup** (`0bfd075`). The orchestrator clones and validates the target repo *before* invoking
Claude, saving context and turns, handing the skill a `pre-setup.json`.

## Evidence

First multi-epic strategies processed: RHAISTRAT-1749 (mlflow-go, odh-dashboard, mlflow) and
RHAISTRAT-1699. Merged PRs followed on mlflow-go (#21) and kale.

## What it got wrong

- **`FOREDER.md` was written and then untracked** (`183622a`, then `3bd2d3e` removed it from
  tracking and gitignored it). It contained the state machine table, six named design decisions
  with rationale, and five predicted pitfalls — all five of which came true. The best design
  document in the project was invisible for a month. Recovered in
  [`../architecture/99-historical-foreder.md`](../architecture/99-historical-foreder.md).
- **Two writers, one file.** `run_pipeline.py` writes `run-metadata.yaml` during the run and
  `push-results.py` writes it again in `after_script`. `ddc038e` patched the symptom; the real fix
  waited a month for RHAIFIRST-374 ([ADR-0014]).
- **`pre-setup.json` records validation from an un-installed tree** — `setup_target_repo` runs
  validation at step 2 and installs dependencies at step 3. Still open.
- **Environment debugging dominated.** Seven consecutive commits on 06-30 were data-repo clone
  auth (`78e1cfb`, `c9012ea`, `94dbe61`, `b4ca57a`, `be743f5`, `a38dd3d`). Copying
  `strat-pipeline`'s patterns exactly turned out to be the answer; guessing at them was not.
