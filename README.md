# epic-code-gen

Takes approved RHAISTRAT strategies with their epic decomposition and generates implementation code against target repos. Handles a single parameterized epic per run — multi-epic orchestration is an upstream concern.

## What This Does

Given an epic from the strategy pipeline (produced by `strat-creator` → `epic-creator`), this pipeline:

1. **Parses** the epic from a strategy report into a structured epic-task file (`fetch_epic.py`)
2. **Assesses** target repo readiness across 6 dimensions — integration tests, lint, CI signals, context docs, CODEOWNERS, language properties (`repo_readiness.py`)
3. **Generates** a codegen spec mapping acceptance criteria to code changes and tests
4. **Dispatches** a codegen subagent into the target repo with the spec as prompt
5. **Validates** the output — lint, typecheck, tests (existing + generated)
6. **Iterates** on failure up to a configurable budget (default 10 iterations)

Repos scoring below 8/12 on readiness are rejected — the repo needs to improve its development infrastructure before AI code generation is viable.

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
scripts/
  fetch_epic.py          # Parse epic creator HTML reports into epic-task files
  repo_readiness.py      # 6-dimension target repo assessment (score /12)
  frontmatter.py         # YAML frontmatter CLI for structured metadata
  artifact_utils.py      # Schema definitions (epic-task, codegen-run, codegen-review)
  state.py               # State persistence for long-running skills
tests/                   # Unit and integration tests
artifacts/               # gitignored — runtime data (epic-tasks, codegen-runs, reviews)
epic-reports/            # gitignored — epic creator HTML reports (sensitive data)
.target-repo/            # gitignored — cloned target repo for codegen
```

## Usage

```bash
# Install dependencies
make install

# Parse epics from a strategy report
python3 scripts/fetch_epic.py epic-reports/report.html RHAISTRAT-1749-E001

# Assess target repo readiness
python3 scripts/repo_readiness.py /path/to/target-repo

# Run tests
make test
```

## Status

- **Phase 1 (Foundation):** Complete — scaffolding, scripts, tests (84 unit tests)
- **Phase 2 (Manual POC):** Complete — RHAISTRAT-1749-E001 on mlflow-go, zero-iteration success
- **Phase 3 (Skill Automation):** Next — codify POC into reusable Claude skills
- **Phase 4 (Validation):** Planned — test on React/TS repos, cross-language, dependency handling
