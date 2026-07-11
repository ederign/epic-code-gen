# Epic Code Gen

Given an approved RHAISTRAT strategy and its epic decomposition, generate implementation code against target repos. Handles a single parameterized epic per run.

## Artifact Conventions

All skills read from and write to the `artifacts/` directory.

```
artifacts/                          # gitignored
  epic-tasks/                       # Epic files with YAML frontmatter
    RHAISTRAT-1749-E001.md
  strategies/                       # Strategy docs fetched from Jira
    RHAISTRAT-1749.md
  codegen-runs/                     # Per-epic run audit trail
    RHAISTRAT-1749-E001/
      run-metadata.yaml
      codegen-spec.md
      codegen-plan.md
      v1/                           # Version 1 artifacts
        diff.patch
        validation.json
        review-architecture.md
        review-tests.md
        review-lint.md
        review-intent.md
        scores.json
      v2/                           # Revision after review
        revision-notes.md
        ...
      final-diff.patch              # Best passing version
```

### Frontmatter

All task and review files use YAML frontmatter for structured metadata. Skills must use `scripts/frontmatter.py` to read schemas, set fields, and read validated data.

```bash
# Get schema for a file type
python3 scripts/frontmatter.py schema epic-task
python3 scripts/frontmatter.py schema codegen-run
python3 scripts/frontmatter.py schema codegen-review

# Set/update frontmatter on a file
python3 scripts/frontmatter.py set <path> field=value field=value ...

# Read validated frontmatter as JSON
python3 scripts/frontmatter.py read <path>
```

### State Persistence

Long-running skills use `scripts/state.py` to persist state to `tmp/` files so it survives context compression.

```bash
python3 scripts/state.py init <file> key=value ...
python3 scripts/state.py set <file> key=value ...
python3 scripts/state.py set-default <file> key=value ...
python3 scripts/state.py read <file>
python3 scripts/state.py write-ids <file> ID ...
python3 scripts/state.py read-ids <file>
python3 scripts/state.py timestamp
python3 scripts/state.py clean
```

## Target Repo

Target repos are cloned into `.target-repo/` (gitignored). Use `clone_target.py` for cloning:

```bash
python3 scripts/clone_target.py <repo-url> <EPIC_ID> [--dest .target-repo] [--fork-owner user] [--clean]
```

This creates branch `epic/<EPIC_ID>` and optionally sets up a fork remote.

## Target Validation

Detect language and run lint/typecheck/test against the target repo:

```bash
python3 scripts/validate_target.py <repo-path> [--json] [--checks lint,test]
```

Supports Go, Python, TypeScript, JavaScript, Rust. Discovers commands from Makefile targets and package.json scripts.

## Epic & Strategy Fetching

Generate epic-task files from HTML reports and fetch strategy context from Jira:

```bash
# Fetch epic + strategy (default: also fetches strategy from Jira)
python3 scripts/fetch_epic.py RHAISTRAT-1749-E001 --report <path>

# All epics from a strategy
python3 scripts/fetch_epic.py RHAISTRAT-1749 --report <path> --all-epics

# Skip strategy fetch (offline)
python3 scripts/fetch_epic.py RHAISTRAT-1749-E001 --report <path> --no-strategy
```

Strategy documents are fetched from Jira (RHAISTRAT project) and saved to
`artifacts/strategies/RHAISTRAT-NNNN.md`. Requires `JIRA_SERVER`, `JIRA_USER`,
`JIRA_TOKEN` env vars. The strategy provides business need, technical approach,
affected components, dependencies, and staff engineer input — used as context
during spec generation.

## Jira-Direct Epic Fetching

Fetch child work items directly from Jira and generate epic-task artifacts
with dependency DAG:

```bash
# Fetch all children of a strategy (fresh run: wipes artifacts first)
python3 scripts/fetch_jira_epics.py RHAISTRAT-1699 --clean

# Without HTML report
python3 scripts/fetch_jira_epics.py RHAISTRAT-1699 --clean --no-report

# Output as JSON (no files written)
python3 scripts/fetch_jira_epics.py RHAISTRAT-1699 --json
```

Uses real Jira keys as `epic_id` (e.g., `RHOAIENG-72103`). Requires
`JIRA_SERVER`, `JIRA_USER`, `JIRA_TOKEN` env vars. Builds dependency DAG
from Jira "Blocks" issue links. Stores both `dependencies` (blocked by)
and `blocks` fields. Generates an HTML status report showing task
eligibility for codegen.

## Pipeline Orchestrator

Orchestrate the full codegen pipeline for one or more strategies:

```bash
# Process strategies (fresh run: wipes artifacts, fetches from Jira)
python3 scripts/run_pipeline.py RHAISTRAT-1699 RHAISTRAT-1700

# Dry run (show what would process, don't invoke Claude)
python3 scripts/run_pipeline.py RHAISTRAT-1699 --dry-run

# CI mode (use run-claude.sh wrapper)
python3 scripts/run_pipeline.py RHAISTRAT-1699 --run-script ci-scripts/run-claude.sh

# With codegen options
python3 scripts/run_pipeline.py RHAISTRAT-1699 --max-iterations 5 --fork-owner dora-the-ai-coder
```

For each strategy: fetches children from Jira, classifies epics by
eligibility (based on current Jira status and dependency DAG), invokes
`/epic-codegen` for each eligible epic. Epics blocked by unresolved
dependencies are skipped — they become eligible in a future run after
dependencies are marked Done in Jira. Writes a structured JSON run log
to `pipeline-runs/` for dashboard consumption.

## Repo Readiness

Before code generation, assess target repo readiness using 6 dimensions (score /12, threshold 8):

```bash
python3 scripts/repo_readiness.py <repo-path>
```

Dimensions: integration tests, lint in CI, clear CI signals, CLAUDE.md/CONTRIBUTING.md, CODEOWNERS, language properties.

## Architecture Context

Fetch architecture context from opendatahub-io/architecture-context into `.context/architecture-context/`.

```bash
bash scripts/fetch-architecture-context.sh
bash scripts/fetch-architecture-context.sh /path/to/local/architecture-context
```

## Testing

After every code change, run `make test-unit` for script changes. Run `make test` for the full suite before pushing. A change is not done until tests pass.

## Run Index

Aggregate all run outcomes into a single file for dashboard consumption:

```bash
python3 scripts/run_index.py artifacts/codegen-runs/
python3 scripts/run_index.py artifacts/codegen-runs/ --json
```

Scans `*/run-metadata.yaml`, writes `artifacts/codegen-runs/index.json` with
all runs, total count, and summary by status (completed/exhausted/error).
Called automatically at the end of every `/epic-codegen` run.

## Review Score Aggregation

Compute scores deterministically from reviewer findings and determine pass/fail:

```bash
python3 scripts/score_reviews.py <reviews-dir> [--json]
```

Scores are computed from structured findings, not chosen by reviewers:
`Score = max(1, 10 - 5*Criticals - 1.5*Importants - 0.5*Minors)`.
Any Critical finding caps the dimension score at 5.

Weights: architecture 30%, tests 30%, lint 20%, intent 20%.
Verdict: pass (>=8.0, no dim <6.0), near-miss (>=7.0), fail, incomplete.

Reviewer agents live in `agents/` — one per dimension. Each is a standalone
agent definition with calibration tables and structured output format.
Reviewers classify findings by severity; they do not set scores.

## Superpowers Integration

Phase 1 uses Superpowers `brainstorming` skill (via a design subagent) to
generate the codegen spec. The subagent invokes brainstorming and acts as
the human partner — answering brainstorming's questions from the epic body,
strategy doc, and pattern discovery results. This produces a design spec
with approach exploration and trade-off evaluation, not just a template fill.

Phase 2 uses Superpowers `subagent-driven-development` (SDD) skill for
implementation. SDD handles: per-task implementer dispatch, per-task review,
fix loops, progress ledger, final code review.

The orchestrator IS the human partner — epic ACs resolve all checkpoints
autonomously. See SKILL.md **Autonomous Operation** for the full mapping.
SDD artifacts land in `.target-repo/.superpowers/sdd/`.

SDD scripts (permitted in settings.json):
- `task-brief` — extract task text to file for implementer dispatch
- `review-package` — generate diff file for reviewer
- `sdd-workspace` — create `.superpowers/sdd/` directory

## Code Generation Workflow

Use `/epic-codegen EPIC_ID [--dry-run] [--max-iterations N] [--fork-owner USER]`

```
Phase 1 — Spec & Plan:
  1. Read epic-task, validate dependencies
  2. Clone target repo, validate readiness (>=8/12)
  3. Pattern discovery in target repo (explicit refs, concept search, siblings, callers)
  4. Invoke brainstorming (design subagent answers questions from gathered context → spec)
  5. Spec review gate (validate spec against actual repo patterns)
  6. Invoke writing-plans (plan subagent generates detailed plan from spec)
  7. Validate plan output

Phase 2 — Subagent-Driven Development (Superpowers SDD):
  6. Record base SHA, init SDD workspace
  7. Invoke Skill("superpowers:subagent-driven-development")
  8. Save version artifacts (diff, validation)

Phase 3 — Multi-Dimensional Review:
  9. Dispatch 4 reviewer agents + wiring verifier in parallel
  10. Compute scores from findings (deterministic)
  11. Wiring verifier traces trigger→chain→outcome per AC (not scored, informs triage)

Phase 4 — Iterate or Complete:
  12. Pass (>=8.0): save final diff
  13. Fail: triage findings (including wiring), write revision notes, re-dispatch fix agent
  14. Exhausted: report best version
```

Model selection: all agents run on opus (inherited from session). No model
overrides — all subagents inherit the session model.

All artifacts saved to `artifacts/codegen-runs/<EPIC_ID>/v<N>/`.
State persisted via `tmp/epic-codegen-<EPIC_ID>.json` + SDD progress ledger.
