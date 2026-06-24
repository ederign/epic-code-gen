# epic-code-gen

Takes an approved RHAISTRAT epic and generates a reviewed, tested code diff against the target repo — fully automated. No human in the loop until the final PR decision.

```
epic-task + strategy ──→ spec ──→ plan ──→ code ──→ review ──→ pass/fail
```

## How It Works

```
/epic-codegen RHAISTRAT-1749-E001 --dry-run
```

**Phase 1 — Spec & Plan:** Read epic + strategy, discover patterns in target repo, generate a codegen-spec (what to build) and codegen-plan (how to build it, TDD steps).

**Phase 2 — Implementation:** Dispatch subagent into the cloned target repo. Follows the plan task-by-task: read reference → write failing test → implement → verify → commit.

**Phase 3 — Review:** 4 independent reviewer agents score the diff in parallel:

| Reviewer | Weight | Focus |
|----------|--------|-------|
| architecture | 30% | Repo conventions, structural fit |
| tests | 30% | AC coverage, TDD evidence, edge cases |
| lint | 20% | Lint/typecheck/build pass, code quality |
| intent | 20% | Does diff match what the epic asked for? |

Pass: weighted avg >= 8.0, no dimension below 6.0.

**Phase 4 — Iterate:** If review fails, the orchestrator adjudicates findings, writes revision notes, dispatches a fix agent, re-reviews. Up to 3 iterations max. All versions preserved (`v1/`, `v2/`, `v3/`).

## Pipeline Position

```
RFE (rfe-creator)
  → Strategy (strat-creator)
    → Epic Decomposition (epic-creator)
      → Code Generation (epic-code-gen)  ← this project
        → PR on target repo → CI → human review → merge
```

## Project Structure

```
.claude/skills/epic-codegen/   # Orchestrator skill (SKILL.md)
agents/                        # Standalone reviewer agent definitions
  architecture-reviewer.md
  tests-reviewer.md
  lint-reviewer.md
  intent-reviewer.md
scripts/
  fetch_epic.py                # Parse epic reports + fetch strategy from Jira
  repo_readiness.py            # 6-dimension target repo assessment (score /12)
  validate_target.py           # Detect language, run lint/typecheck/test
  clone_target.py              # Clone target repo, set up branch + fork remote
  score_reviews.py             # Aggregate reviewer scores, determine pass/fail
  run_index.py                 # Aggregate all runs into index.json for dashboard
  frontmatter.py               # YAML frontmatter CLI for structured metadata
  artifact_utils.py            # Schema definitions (epic-task, codegen-run, codegen-review)
  state.py                     # State persistence for long-running skills
  jira_utils.py                # Jira API access for strategy fetching
tests/                         # 186 unit tests
artifacts/                     # gitignored — runtime data
  epic-tasks/                  #   Epic files with YAML frontmatter
  strategies/                  #   Strategy docs fetched from Jira
  codegen-runs/                #   Per-epic run audit trail (spec, plan, diffs, reviews, scores)
    index.json                 #   Aggregated run outcomes for dashboard
```

## Usage

```bash
# Install dependencies
make install

# Parse an epic from a strategy report (also fetches strategy from Jira)
python3 scripts/fetch_epic.py RHAISTRAT-1749-E001 --report epic-reports/report.html

# Assess target repo readiness (gate: 8/12)
python3 scripts/repo_readiness.py /path/to/target-repo

# Run the full pipeline (dry-run — produces diff, no PR)
/epic-codegen RHAISTRAT-1749-E001 --dry-run

# Run tests
make test
```

## First Run Results

**RHAISTRAT-1749-E001** — Expose ModelConfig on Prompt/PromptVersion in MLflow Go SDK.

| Dimension | Score | Weighted |
|-----------|-------|----------|
| architecture | 10.0 | 3.00 |
| tests | 8.0 | 2.40 |
| lint | 10.0 | 2.00 |
| intent | 10.0 | 2.00 |
| **Total** | | **9.4 — PASS** |

Passed on first iteration. 224 lines across 4 files, 6 new tests.

## Status

- **Phase 1 (Foundation):** Complete — scaffolding, scripts, 186 tests
- **Phase 2 (Manual POC):** Complete — RHAISTRAT-1749-E001 on mlflow-go, 9.4/10 first attempt
- **Phase 3 (Skill Automation):** Complete — orchestrator skill, 4 reviewer agents, score aggregation, run index
- **Phase 3b (Superpowers Integration):** In progress — wiring SDD plugin for implementation dispatch
- **Phase 4 (Validation):** Next — React/TS repos, cross-language, dependency handling
