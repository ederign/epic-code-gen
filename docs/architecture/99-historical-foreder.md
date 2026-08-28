---
id: 99-historical-foreder
title: "FOREDER.md (historical, 2026-06-30) — recovered design brief"
type: plan
status: done
repos: [epic-code-gen-pipeline]
commits: ["183622a", "2b7496b", "3bd2d3e"]
decisions: [ADR-0005, ADR-0008, ADR-0009, ADR-0011]
---

# Historical: FOREDER.md

> **Recovered document. Do not edit the body below.**
>
> This was written on 2026-06-30 (`183622a`, extended by `2b7496b`) as a design brief for the
> pipeline build-out, then **removed from tracking and gitignored** the same day in `3bd2d3e`. It was
> invisible for a month, and it is the most complete design rationale the project produced: the state
> machine table, six named design decisions, what was and wasn't copied from `strat-pipeline`, and
> five predicted pitfalls — **all five of which came true.**
>
> Recovered verbatim from `git show 3bd2d3e^:FOREDER.md`. It is preserved as written, in its original
> voice (it was addressed to a colleague, not to a reader).
>
> **What has changed since it was written** — read the body as a 2026-06-30 snapshot:
>
> | Claim in the document | Status today |
> |---|---|
> | "4 independent reviewers" | Six agents dispatched; four scored, two advisory ([ADR-0028]) |
> | "Scoring rubrics (calibration tables)" | `rubrics/` is dead and its weights are wrong; calibration lives in `.claude/agents/` ([ADR-0021]) |
> | "138 tests across both repos" | 703 in `epic-code-gen`, 16 in the pipeline repo |
> | Manual trigger, "just add a `rules: - schedules` line" later | Still manual. The `resource_group` prerequisite it identifies is still absent |
> | Data-repo growth needs a pruning strategy | Predicted correctly; 33 MB, no pruning exists |
> | Concurrent strategy processing needs a `resource_group` | Predicted correctly; still unmitigated |
> | State machine table | Accurate, and now documented with transitions in [02-pipeline-state-machine.md](02-pipeline-state-machine.md) |
>
> The reason this document was worth recovering, rather than rewriting: it records *why* six decisions
> were made, by the person making them, at the time. That is not reconstructible after the fact —
> which is the entire argument for [ADR-0034].

---

# FOREDER: Epic Code Gen Pipeline

Hey Eder — this is your deep-dive guide to the epic-code-gen pipeline system. Not a reference manual, more like sitting down with a colleague who built it and having them walk you through everything.

## What Are We Actually Building?

Remember how `epic-code-gen` started as a local thing? You'd fire up Claude Code, point it at a strategy's epics, and it would generate code, review it, maybe create a PR. It worked great for our POC — RHAISTRAT-1749-E001 passed on the first try with a 9.4/10 score. But it required you to babysit it.

We're turning that into an autonomous pipeline. Think of it like a factory line that:

1. Picks up strategies tagged as ready
2. Figures out which epics need work (and which are blocked, done, or waiting on PR reviews)
3. Does one round of work on each epic that's actionable
4. Saves everything, pushes results, updates Jira
5. Waits for the next trigger (manual for now, scheduled later)
6. Repeats until every epic in the strategy is done

The key insight is **convergence** — it's not a one-shot pipeline. It's a loop that keeps narrowing the gap between "where we are" and "everything done." Each run moves epics forward by one step, whatever step that is.

## The Three-Repo Architecture

This mirrors what we did with `strat-creator` → `strat-pipeline` → `strat-pipeline-data`, but with important differences.

### epic-code-gen (existing, the brains)

This is where all the intelligence lives:
- Python scripts that orchestrate everything (`run_pipeline.py`, `fetch_jira_epics.py`, `clone_target.py`, etc.)
- Claude Code skills (the `/epic-codegen` skill that actually generates code)
- Reviewer agents (4 independent reviewers: architecture, tests, lint, intent)
- Scoring rubrics (calibration tables so reviewers are consistent)

Think of it as the engine. The pipeline repo is just the car around it.

### epic-code-gen-pipeline (new, the CI shell)

This is deliberately thin. Its job:
- Set up the CI environment (GCP credentials, Git config, clone repos)
- Call `run_pipeline.py` from epic-code-gen
- After the run, push results to the data repo
- Trigger the dashboard rebuild

The `.gitlab-ci.yml` is ~30 lines. The ci-scripts are adapted from strat-pipeline (proven patterns, not invented from scratch). The real logic lives in epic-code-gen's Python code, not here.

**Why thin?** Because you can also run `run_pipeline.py` locally for debugging. If the orchestration lived in shell scripts inside the pipeline repo, you'd need GitLab CI to test anything. By keeping it in Python, `python3 scripts/run_pipeline.py --ci --data-repo ./test-data RHAISTRAT-1749` works on your laptop.

### epic-code-gen-pipeline-data (new, the artifact store)

This is a Git repo used as a database. Every run writes its artifacts here:

```
RHAISTRAT-1749/
├── RHAISTRAT-1749-E001/
│   ├── run-metadata.yaml      ← the epic's current state (the "row" in our "database")
│   ├── codegen-spec.md        ← what to build
│   ├── codegen-plan.md        ← how to build it
│   ├── v1/                    ← first attempt
│   │   ├── diff.patch         ← the actual code changes (JUST the diff, never full files)
│   │   ├── validation.json    ← did lint/tests pass?
│   │   ├── review-*.md        ← 4 reviewer outputs
│   │   └── scores.json        ← dimension scores
│   └── v2/                    ← second attempt (after PR feedback or review failure)
│       └── ...
├── RHAISTRAT-1749-E002/
│   └── ...
└── run-log.jsonl              ← append-only log of every pipeline pass
```

**Why organized by strategy/epic/version instead of by timestamp?** This was a deliberate departure from strat-pipeline-data (which uses `YYYYMMDD-HHMMSS/` folders). When you're debugging why RHAISTRAT-1749-E001 failed, you want to see its entire history in one directory — not hunt through 15 timestamped folders to piece together what happened across 15 runs. The `run-log.jsonl` gives you the timeline view when you need it.

**Why diffs only?** The target repo (e.g., `mlflow/mlflow`) is the source of truth. Storing full files would be wasteful and would diverge from the actual repo state. A diff.patch is small, portable, and tells you exactly what changed.

### epic-code-gen-dashboard (new, the window)

Static HTML/JS served via GitLab Pages. Three views:

1. **Strategy Drilldown** — click a strategy → see all its epics with status badges → click an epic → see its versions with scores and review summaries. Progress bars show how close a strategy is to complete.

2. **Jira State Log** — timeline of every state transition. "E001 went from Ready to ReviewPending at 10:00, then to PRCreated at 10:45." Built from `run-log.jsonl`.

3. **Cost & Telemetry** — how many tokens, how much money, per strategy/epic/version. Built from OTEL data that Claude Code emits.

## The State Machine (This Is the Core Abstraction)

Every epic lives in one of these states:

```
Pending → Ready → Generating → ReviewPending → PRCreated → PRChangesRequested → Done
                                                                ↓
                                                            (also: Blocked, Failed)
```

Each pipeline run reads every epic's state from `run-metadata.yaml` and does exactly one thing:

| State | What happens |
|-------|-------------|
| **No metadata** | New epic discovered. Check dependencies. Set to Ready or Blocked. |
| **Ready** | Clone target repo, run codegen, generate diff. Move to ReviewPending. |
| **ReviewPending** | Score the diff with 4 reviewers. If pass → create PR → PRCreated. If fail → bump version, stay ReviewPending. |
| **PRCreated** | Check GitHub. Merged? → Done. Review comments? → PRChangesRequested. Closed? → Ready (retry). |
| **PRChangesRequested** | Pull review comments, feed into next codegen iteration. Back to ReviewPending. |
| **Blocked** | Check if blocking epic is Done. If so → Ready. |
| **Done** | Skip. |
| **Failed** | Log and skip. Needs human intervention. |

**One iteration per pass.** We deliberately chose not to loop within a single run. If an epic generates code that fails review, it writes the failure, and the *next* pipeline run picks it up for v2. This is simpler to debug (each run does one thing per epic), and more observable (you can see every step in the run-log).

## Key Design Decisions & Why

### Strategy as unit of work, not epic
Epics within a strategy have dependencies. E002 might depend on E001's code being merged first. The pipeline needs to see the whole picture — the dependency DAG — to know what's actionable. If we processed individual epics in isolation, we'd miss these relationships.

### Python orchestration, not shell
The strat-pipeline uses shell scripts for some orchestration, and it works because the logic is simple (process each RFE through create → refine → review). For epic-code-gen, we have dependency DAGs, state machines, PR lifecycle management, GitHub API calls — this would be unmaintainable in bash. Python gives us proper data structures, error handling, and testability.

### Fat Docker image
We bake Python, Go, Node.js, Rust, and Claude Code into one big image. Yes, it'll be 3-5GB. The alternative — installing language runtimes at job start — adds 10+ minutes per run and introduces network failure modes. For a pipeline that runs heavy AI workloads ($$$ per run), spending a few extra GB of disk to save setup time is an obvious trade.

### Manual trigger first
This pipeline creates PRs on real repos. We're not scheduling it until we've validated end-to-end with real strategies and built confidence. When we're ready, it's just adding a `rules: - schedules` line to the CI config.

### Data repo as state store (not Jira)
Jira is for business visibility (humans check ticket status). But the pipeline needs machine-readable state that's fast to read, version-controlled, and doesn't depend on Jira's API being available. `run-metadata.yaml` in Git gives us all of that. Jira transitions happen as a side effect, not as the source of truth.

## Lessons from strat-pipeline

We copied proven patterns rather than inventing new ones:

- **OTEL collector**: Claude Code emits OpenTelemetry metrics. strat-pipeline has a lightweight Python HTTP listener that captures them to JSONL. It works. We copied it.

- **Retry-with-rebase for data repo pushes**: When two CI jobs finish around the same time and both push to the data repo, one will fail. strat-pipeline handles this with a pull-rebase-retry loop (3 attempts). No force-push. We copied it.

- **Jira label locking**: strat-pipeline uses `strat-creator-processing` as a mutex. We use `epic-codegen-active` for the same purpose — prevents two runs from processing the same strategy simultaneously.

- **Thin CI, fat Python**: strat-pipeline's `.gitlab-ci.yml` calls shell scripts that call Claude. Our `.gitlab-ci.yml` calls shell scripts that call Python that calls Claude. The principle is the same: CI config is glue, not logic.

What we *didn't* copy:
- **Timestamped run directories**: strat-pipeline uses `YYYYMMDD-HHMMSS/` folders. We use strategy/epic/version because our data is inherently hierarchical and long-lived (an epic might take 10 runs to complete).
- **`current` symlink**: strat-pipeline has a `current` symlink to the latest run. We don't need it — our structure is navigable by design.

## How Good Engineers Think About This

**Start with the data model.** Before writing any pipeline code, we designed the data repo structure. What does `run-metadata.yaml` contain? What goes in each version folder? Once that's clear, the pipeline code writes itself — it's just "read state, do one thing, write state."

**The state machine is everything.** If you get the states and transitions right, the pipeline is just a switch statement. If you get them wrong, you'll be patching edge cases forever. We spent time getting the state machine right before writing a line of implementation code.

**Copy before you create.** strat-pipeline exists. It works. It's been running for months. We didn't design a new CI pattern — we took their proven pattern and adapted it. The only "new" parts are where epic-code-gen genuinely differs (state machine, PR lifecycle, multi-language support).

**Small iterations.** We're building this in order: Dockerfile → data repo → run_pipeline.py → pipeline repo → dashboard. Each step is testable independently. We're not trying to build the whole thing and hope it works.

## Potential Pitfalls to Watch For

**Image size.** The fat image will be big. If it becomes a problem (slow pulls, storage costs), we can optimize later — multi-stage builds, stripping debug symbols, using slim base images. But don't optimize prematurely.

**Claude context limits.** Long codegen runs (big epics, complex repos) might hit Claude's context window. `state.py` helps survive context compression, but there's a ceiling. If you see degraded quality on large epics, that's probably why.

**GitHub rate limits.** The GitHub API has rate limits. If we're processing 20 epics that all need PR status checks, we might hit them. The `github_utils.py` module should handle retries with backoff.

**Data repo growth.** Every version of every epic stores a diff.patch plus review files. Over months, this adds up. We'll eventually need a pruning strategy (archive old versions, keep only latest N). Not urgent, but worth knowing about.

**Concurrent strategy processing.** Right now, only one strategy runs at a time (manual trigger). When we add scheduling, we'll need resource groups (like strat-pipeline's `resource_group: strat-batch`) to prevent collisions. The Jira label locking handles epic-level dedup, but strategy-level serialization needs CI config.

## Implementation Status

All five stories are implemented and pushed:

| Story | Repo | What's there |
|-------|------|-------------|
| CI Image | epic-code-gen | `Dockerfile.ci` (UBI9 + Python 3.11 + Go 1.24 + Node 22 + Claude Code), Makefile targets |
| Pipeline repo | epic-code-gen-pipeline | `.gitlab-ci.yml`, 8 CI scripts (setup, clone, run, post, OTEL, stream), `push-results.py` |
| run_pipeline.py | epic-code-gen | `--ci`/`--data-repo` flags, state machine, `pr_lifecycle.py` (GitHub API, review feedback) |
| Data repo | epic-code-gen-pipeline-data | README with structure docs, ready for first run |
| Dashboard | epic-code-gen-dashboard | `.gitlab-ci.yml` for Pages, generator in pipeline repo (`scripts/generate-dashboard.py`) |

**Test coverage:** 138 tests across both repos (84 existing + 28 CI-mode + 26 pipeline repo). All passing.

**Next steps to go live:**
1. Build and push Docker image: `make ci-image-push` (from epic-code-gen)
2. Set GitLab CI/CD variables on the pipeline repo (GCP_PROJECT_ID, GCP_SERVICE_ACCOUNT_KEY, JIRA_API_TOKEN, EPIC_CODEGEN_GITHUB_TOKEN, RESULTS_PUSH_TOKEN)
3. Manual trigger with `STRATEGY_KEYS=RHAISTRAT-XXXX`
4. Watch the first run, verify state machine transitions in data repo
5. Check the dashboard at the GitLab Pages URL
