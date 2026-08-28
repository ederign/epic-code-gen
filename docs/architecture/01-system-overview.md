---
id: 01-system-overview
title: System overview — how a Jira epic becomes a merged PR
type: plan
status: current
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
decisions: [ADR-0005, ADR-0006, ADR-0007, ADR-0008, ADR-0009]
---

# System overview

## Position in the wider chain

```
RFE (rfe-creator)
  → Strategy (strat-creator)
    → Epic decomposition (epic-creator)
      → Code generation (epic-code-gen)   ← this system
        → PR on target repo → CI → human review → merge
```

## The four repos

| Repo | Role | Written by |
|---|---|---|
| `epic-code-gen` | The brains: skill, 13 agents, 20 scripts, 703 tests | humans + agents |
| `epic-code-gen-pipeline` | Thin GitLab CI shell, 16 files | humans |
| `epic-code-gen-pipeline-data` | Git-as-database: state + artifacts | CI bot |
| `epic-code-gen-dashboard` | Reads the data repo → GitLab Pages | humans |

Rationale: [ADR-0005]. The pipeline repo clones the brains repo at run time rather than vendoring it, so
logic ships without touching CI.

## One run, end to end

```
  operator sets STRATEGY_KEYS, presses "play" on codegen-run  (manual trigger)
        │
        ▼
  ┌─────────────────────── GitLab job (6h timeout) ────────────────────────┐
  │  before_script:  setup-env.sh → clone-data-repo.sh                     │
  │                                                                        │
  │  run-codegen.sh:                                                       │
  │    clone epic-code-gen → /tmp/claude-workdir                           │
  │    start otel-collector.py (127.0.0.1:4318)                            │
  │    start progress heartbeat (every 300s)                               │
  │    python3 scripts/run_pipeline.py $KEYS --ci --data-repo /tmp/data-repo│
  │      │                                                                 │
  │      ├─ fetch strategy children from Jira, build dependency DAG        │
  │      ├─ classify eligibility per epic                                  │
  │      └─ for each eligible epic: ONE state transition                   │
  │           └─ if generating: claude -p → /epic-codegen skill            │
  │                                                                        │
  │  after_script:   pipeline-post.sh → push-results.py → data repo commit │
  └────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  trigger-dashboard → epic-code-gen-dashboard pipeline → GitLab Pages
```

`after_script` rather than `script` is deliberate (`aff11df`): results persist even when codegen times
out or crashes. Note it is bounded by `RUNNER_AFTER_SCRIPT_TIMEOUT` (5 min default), independently of the
6-hour job timeout.

## The convergence loop

The system does **not** drive one epic to completion in one job. Each run advances every actionable epic
by exactly one step ([ADR-0009]):

```
run 1:  Pending → Ready              clone, readiness, toolchain preflight
run 2:  Ready → ReviewPending        generate + review (the expensive one)
run 3:  ReviewPending → PRCreated    open the PR
run 4:  PRCreated → PRCreated        no new comments — a valid no-op
run 5:  PRChangesRequested → PRCreated   address review feedback
run 6:  PRCreated → Done             PR merged upstream
```

Full transition graph: [02-pipeline-state-machine.md](02-pipeline-state-machine.md).

This is why the pipeline never blocks on a human: it *observes* that a human acted, on the next run.
It also means latency is measured in runs, and the trigger is manual — so wall-clock latency is really
"how often does someone press the button."

## Inside one epic's generation

The `/epic-codegen` skill, four phases ([04-codegen-skill-phases.md](04-codegen-skill-phases.md)):

```
Phase 1  Spec & Plan
         pattern discovery (explicit refs, concept search, 5–10 siblings, conventions)
           → brainstorming subagent → spec → spec review gate → writing-plans → plan
Phase 2  Implementation
         Superpowers SDD, orchestrator acts as the human partner
Phase 3  Review — 6 agents in parallel
         architecture 30% · tests 30% · lint 20% · intent 20%   (scored)
         wiring · interactions                                   (advisory)
           → score_reviews.py computes the number from finding counts
Phase 4  Iterate or complete
         pass ≥8.0 → final diff · near-miss ≥7.0 on exhaustion → PR anyway
         fail → triage → fix agent → new version (budget 10)
```

## Two authorities, and the seam between them

| Question | Authority |
|---|---|
| Which epics exist, and is this one eligible? | **Jira** ([ADR-0007]) |
| Where is this epic in the pipeline, and what scored what? | **the data repo** ([ADR-0008]) |

That seam is where the worst bug lived: RHAIFIRST-374, an epic whose state file said `completed` — a word
the state machine did not know — was skipped on every run while CI reported success, deadlocking three
dependents. The fix ([ADR-0013], [ADR-0014], [ADR-0015]) is one owner per field, merge-never-write, and
loud failure on the unrecognized.

## Where things are

| Concern | Location |
|---|---|
| Orchestration | `scripts/run_pipeline.py` (1,973 lines) |
| Review loop | `scripts/review_cycle.py` |
| Scoring | `scripts/score_reviews.py` |
| Schemas & state vocabularies | `scripts/artifact_utils.py` |
| Review response | `scripts/review_response.py` |
| Target repo assessment | `validate_target.py`, `repo_readiness.py` |
| Agents | `.claude/agents/` (13 files) |
| The skill | `.claude/skills/epic-codegen/SKILL.md` (829 lines) |
| CI image | `Dockerfile.ci` |

## Scale to date

24 epics across 7 target repos, 39 recorded pipeline passes, 9 PRs (5 merged), ~$80 logged Claude spend,
20.8% reported completion. Score progressions: RHAI-74 2.4 → 4.9 → 7.2 → 9.4; RHAI-64 2.6 → 2.65 → 6.1 →
6.7 → 8.2. Passing scores cluster 7.9–9.4.

Honest counterweight: **39 of the data repo's 104 commits are humans hand-editing state to unwedge the
pipeline.** See [10-known-limitations.md](10-known-limitations.md).
