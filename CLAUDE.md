# Epic Code Gen

Given an approved RHAISTRAT strategy and its epic decomposition, generate implementation code against target repos. Handles a single parameterized epic per run.

## Artifact Conventions

All skills read from and write to the `artifacts/` directory.

```
artifacts/                          # gitignored
  epic-tasks/                       # Epic files with YAML frontmatter
    RHAISTRAT-1665-E001.md
  codegen-runs/                     # Per-epic run audit trail
    RHAISTRAT-1665-E001/
      run-metadata.yaml
      epic-task-snapshot.md
      readiness-assessment.md
      codegen-spec.md
      iterations/
        01-diff.patch
        01-validation.md
      final-diff.patch
      pr-url.txt
  codegen-reviews/                  # Scored review files with YAML frontmatter
    RHAISTRAT-1665-E001-review.md
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

Target repos are cloned into `.target-repo/` (gitignored). The codegen subagent runs inside this directory with the codegen spec as prompt.

```bash
# Clone target repo and create epic branch
git clone <repo-url> .target-repo
cd .target-repo && git checkout -b epic/RHAISTRAT-NNNN-ENNN
```

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

## Code Generation Workflow

```
1. Read epic-task file (target_repo, components, acceptance criteria, dependencies)
2. Check dependencies satisfied (upstream epics status=Validated)
3. Clone target repo, branch epic/RHAISTRAT-NNNN-ENNN
4. Fetch architecture context for target component
5. Pattern discovery in target repo (reference implementations)
6. Generate codegen spec (spec-first approach)
7. Dispatch codegen subagent into .target-repo/ with spec as prompt
8. Validate: lint, typecheck, tests (existing + generated)
9. Iteration loop on failure (max configurable: 10/15/20 by effort size)
10. On pass: create PR (or save diff if dry-run)
```

Every step is logged to `artifacts/codegen-runs/`.
