# Epic Code Gen

Given an approved RHAISTRAT strategy and its epic decomposition, generate implementation code against target repos. Handles a single parameterized epic per run.

## Artifact Conventions

All skills read from and write to the `artifacts/` directory.

```
artifacts/                          # gitignored
  epic-tasks/                       # Epic files with YAML frontmatter
    RHAISTRAT-1749-E001.md
  codegen-runs/                     # Per-epic run audit trail
    RHAISTRAT-1749-E001/
      run-metadata.yaml
      codegen-spec.md
      codegen-plan.md
      v1/                           # Version 1 artifacts
        diff.patch
        validation.json
        implementer-report.md
        review-tests.md
        review-intent.md
        review-lint.md
        review-architecture.md
        review-patterns.md
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

## Review Score Aggregation

Aggregate reviewer scores with weights and determine pass/fail:

```bash
python3 scripts/score_reviews.py <reviews-dir> [--json]
```

Weights: tests 25%, intent 25%, lint 20%, architecture 20%, patterns 10%.
Verdict: pass (>=8.0, no dim <6.0), near-miss (>=7.5), fail, incomplete.

Reviewer rubrics live in `rubrics/` — one per dimension. Each defines scoring
criteria (1-10), calibration tables, and output format.

## Code Generation Workflow

Use `/epic-codegen EPIC_ID [--dry-run] [--max-iterations N] [--fork-owner USER]`

The skill automates the Superpowers methodology:

```
Phase 1 — Spec & Plan:
  1. Read epic-task, validate dependencies
  2. Clone target repo, validate readiness (>=8/12)
  3. Pattern discovery in target repo
  4. Generate codegen-spec.md (AC-to-component mapping)
  5. Generate codegen-plan.md (task-by-task with TDD steps)

Phase 2 — Subagent-Driven Development:
  6. Dispatch implementer subagent (model: sonnet)
  7. Validate: lint, typecheck, tests
  8. Generate diff file

Phase 3 — Multi-Dimensional Review:
  9. Dispatch 5 reviewer subagents in parallel (model: sonnet)
  10. Aggregate weighted scores

Phase 4 — Iterate or Complete:
  11. Pass (>=8.0): save final diff
  12. Fail: adjudicate findings, write revision notes, re-dispatch
  13. Exhausted: report best version
```

Model selection: opus for orchestrator (judgment), sonnet for implementers
and reviewers (mechanical). Always specify model explicitly in dispatches.

All artifacts saved to `artifacts/codegen-runs/<EPIC_ID>/v<N>/`.
State persisted via `tmp/epic-codegen-<EPIC_ID>.json`.
