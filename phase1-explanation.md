# Phase 1: Foundation — Explanation

## What Was Built

Phase 1 established the project scaffolding and core scripts for epic-code-gen, mirroring the strat-creator architecture.

### Project Structure

```
epic-code-gen/
  CLAUDE.md              # Project conventions for AI skills
  Makefile               # install, test, test-unit, test-integration, clean
  pyproject.toml         # uv project config (Python 3.11+, pytest, pyyaml)
  .gitignore             # artifacts/, tmp/, .target-repo/, .context/
  .claude/skills/        # Skill definitions (populated in Phase 3)
  scripts/
    artifact_utils.py    # Schema definitions + frontmatter I/O
    frontmatter.py       # CLI for schema/read/set/batch-read/rebuild-index
    state.py             # Key-value state persistence for long-running skills
    repo_readiness.py    # 6-dimension repo assessment (/12, threshold 8)
    fetch_epic.py        # HTML report parser → epic-task files
  tests/
    test_artifact_utils.py  # 34 tests: schemas, validation, I/O, discovery
    test_fetch_epic.py      # 24 tests: parsing, extraction, generation
    test_repo_readiness.py  # 26 tests: all 6 dimensions + full assessment
  artifacts/
    epic-tasks/          # Epic files with YAML frontmatter
    codegen-runs/        # Per-epic audit trail directories
    codegen-reviews/     # Scored review files
```

### Scripts

**artifact_utils.py** — Forked from strat-creator, replaced schemas:
- `epic-task`: epic_id, title, strategy_key, target_repo, target_branch, components, dependencies, effort_size, status (Pending→Validated), readiness_score, codegen_branch
- `codegen-run`: epic_id, status (Running|Completed|Failed|Exhausted), iterations, max_iterations, started_at, completed_at, target_repo, target_branch, codegen_branch, validation (lint/typecheck/tests)
- `codegen-review`: epic_id, recommendation (approve|revise|reject), total_score, scores (lint/typecheck/tests/intent_coverage/architecture)

Kept the validation engine, frontmatter read/write, and file discovery functions. Replaced strat-specific file finders with `find_epic_task`, `find_codegen_run`, `find_codegen_review`, `scan_epic_tasks`. Replaced index rebuild to generate `epics.md` instead of `rfes.md`.

**frontmatter.py** — CLI adapted for epic-code-gen schema types. Auto-detects schema from path (`epic-tasks/` → epic-task, `codegen-runs/` → codegen-run, `codegen-reviews/` → codegen-review).

**state.py** — Copied verbatim from strat-creator. Pure infrastructure, no domain-specific logic.

**repo_readiness.py** — Implements Fullsend's 6-dimension assessment:
1. Integration tests (test dirs + test files)
2. Lint in CI (lint config + CI reference)
3. CI signals (CI config + defined jobs)
4. Context docs (CLAUDE.md/AGENTS.md preferred, CONTRIBUTING.md fallback)
5. CODEOWNERS (with path-specific rules scoring higher)
6. Language properties (type checking + lockfile)

Score /12, threshold 8. Tested against strat-creator (scored 8/12, passes).

**fetch_epic.py** — Parses the 4.3MB epic creator HTML report:
- Extracts strategy sections with DAG dependency graphs (mermaid)
- Parses epic cards: ID, priority, AI score, type, component, team, dependencies
- Extracts AI implementability signals (9 dimensions)
- Parses the `epicBodies` JavaScript object for markdown content
- Generates epic-task files with validated frontmatter + body
- CLI supports: single epic, all epics from strategy, strategy listing, JSON output

### Test Coverage

84 total unit tests, all passing:
- Schema validation: required fields, patterns, enums, type checking, nested dicts, unknown fields
- Frontmatter I/O: write/read roundtrip, body preservation, update, error cases
- File discovery: find_epic_task, find_codegen_run, find_codegen_review, scan, rebuild_index
- HTML parsing: strategy extraction, epic metadata, DAG dependencies, body content, signals
- Repo readiness: all 6 dimensions individually + full assessment

### Commits

1. `feat: add project scaffolding` (RHAIFIRST-137)
2. `feat: fork frontmatter and state scripts from strat-creator` (RHAIFIRST-138)
3. `feat: add repo readiness assessment script` (RHAIFIRST-139)
4. `feat: add epic fetcher with HTML parser` (RHAIFIRST-140)
5. `test: add frontmatter schema validation tests` (RHAIFIRST-141)

## What's Next

Phase 2: Manual POC with RHAISTRAT-1665 — use the fetch_epic to extract the epic, run readiness assessment on odh-dashboard, write a codegen spec, and generate code + tests.
