---
name: epic-codegen
description: Generate implementation code for a single epic from an approved strategy, using spec-first subagent-driven development with multi-dimensional review
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
---

# Epic Code Generation

Generate implementation code for a single epic. Reads the epic-task file as
the "product owner," generates a spec and plan, dispatches subagents for
implementation, runs multi-dimensional review, and iterates until pass or
exhaustion.

**Core idea:** The epic strategy IS the product owner. The acceptance criteria
ARE the approval gate. Every human step in the Superpowers methodology is
automated — spec approval becomes AC mapping validation, plan approval becomes
task-to-AC coverage check, review steering becomes weighted score aggregation.

**Narration:** between tool calls, narrate at most one short line.

## Arguments

Parse `$ARGUMENTS` for:
- `EPIC_ID` (required) — e.g., `RHAISTRAT-1749-E001`
- `--max-iterations N` — default 9
- `--dry-run` — produce diff but do not create PR
- `--fork-owner USER` — GitHub username for fork remote
- `--checks lint,test,typecheck` — which validation checks to run (default: all)

## Phase 1: Spec & Plan Generation

### Step 1: Parse Epic Task

```bash
python3 scripts/frontmatter.py read artifacts/epic-tasks/${EPIC_ID}.md
```

Validate:
- File exists and has valid frontmatter
- `status` is `Pending` or `Ready` (not `InProgress` or later)
- `target_repo` is set
- If `dependencies` is non-empty, verify each dependency epic has `status=Validated`

Read the epic-task body — this is your "interview transcript." The body
contains what to build, acceptance criteria, target files, and reference
patterns.

### Step 2: Initialize State

```bash
python3 scripts/state.py init tmp/epic-codegen-${EPIC_ID}.json \
  epic_id=${EPIC_ID} \
  version=0 \
  phase=init \
  status=running \
  max_iterations=9
```

Update epic-task status:
```bash
python3 scripts/frontmatter.py set artifacts/epic-tasks/${EPIC_ID}.md status=InProgress
```

### Step 3: Clone Target Repo

```bash
python3 scripts/clone_target.py <target_repo_url> ${EPIC_ID} --clean [--fork-owner USER]
```

This clones into `.target-repo/`, creates branch `epic/${EPIC_ID}`.

### Step 4: Validate Target Repo

```bash
python3 scripts/repo_readiness.py .target-repo/
```

Gate: score must be >= 8/12. If below, report the gap and stop.

```bash
python3 scripts/validate_target.py .target-repo/ --json
```

Record the discovered language and validation commands for later use.

### Step 5: Read Strategy Context

Read the strategy document for the epic's `strategy_key`:
```
artifacts/strategies/${STRATEGY_KEY}.md
```

This contains the business need, technical approach, affected components,
dependencies, staff engineer input, non-functional requirements, and out
of scope. Together with the epic-task body, this is your "interview
transcript" — all the context a product owner would provide.

### Step 6: Read Repo Context

Read from `.target-repo/`:
- `CLAUDE.md` or `AGENTS.md` (target repo conventions)
- `CONTRIBUTING.md` if present
- Key files named in the epic body (reference implementations, target files)

### Step 7: Pattern Discovery

Search the target repo for patterns referenced in the epic body:
- Function names, type names, file paths mentioned in the epic
- Existing implementations to use as reference
- Test patterns to replicate

Read the reference files. These become the "reference pattern" sections in
the codegen spec.

### Step 8: Write Codegen Spec

Create `artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md`:

```markdown
# Spec: ${EPIC_ID}

## Context
<from epic-task body + strategy document + target repo CLAUDE.md — the "interview answers">

## Design Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|

## Components
### Component 1: <what to change>
- File: <path in target repo>
- Reference pattern: <existing code to adapt from, with file:line>
- Acceptance criteria: <AC from epic>
- Pass criteria: <what "done" looks like — specific assertions>

## Out of Scope
<explicitly excluded to prevent scope creep>
```

Auto-validate: every AC from the epic-task body has a corresponding Component.
If any AC is unmapped, stop and report the gap.

### Step 9: Write Codegen Plan

Create `artifacts/codegen-runs/${EPIC_ID}/codegen-plan.md`:

```markdown
# Plan: ${EPIC_ID}

> For subagent: follow task-by-task. Each task has checkbox steps.
> Emphasis: TDD (write test first), YAGNI, DRY.
> Reference spec: codegen-spec.md

## Global Constraints
[From spec + target repo CLAUDE.md: version floors, naming rules, platform
requirements, additive-only, no new dependencies, etc.]

---

### Task 1: <description>

**Files:**
- Create: `exact/path/to/file.go`
- Modify: `exact/path/to/existing.go:123-145`
- Test: `exact/path/to/test.go`

**Interfaces:**
- Consumes: [from earlier tasks — exact signatures, types]
- Produces: [for later tasks — exact function names, return types]

- [ ] **Step 1: Read reference implementation** at <path>
- [ ] **Step 2: Write failing test** for AC
- [ ] **Step 3: Run test to verify it fails**
- [ ] **Step 4: Write minimal implementation**
- [ ] **Step 5: Run test to verify it passes**
- [ ] **Step 6: Commit**
```

Auto-validate:
- Every spec Component has at least one plan Task
- Every Task has a test step
- Execution order is specified (which tasks depend on which)

Update state:
```bash
python3 scripts/state.py set tmp/epic-codegen-${EPIC_ID}.json phase=planned version=1
```

## Phase 2: Subagent-Driven Development

### Step 10: Record Base Commit

```bash
cd .target-repo && git rev-parse HEAD
```

Save as `BASE_SHA` — used for diff generation later.

### Step 11: Dispatch Implementer Subagent

Dispatch via Agent tool with **model: sonnet** (mechanical execution):

```
Agent:
  description: "Implement ${EPIC_ID}"
  model: sonnet
  prompt: |
    You are implementing code changes for epic ${EPIC_ID}.

    ## Your Requirements

    Read the codegen plan: artifacts/codegen-runs/${EPIC_ID}/codegen-plan.md
    Read the codegen spec: artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md
    Read the target repo conventions: .target-repo/CLAUDE.md

    ## Working Directory

    Work in: .target-repo/

    ## Your Job

    Follow the plan task-by-task. For each task:
    1. Read the reference implementation named in the task
    2. Write a failing test (TDD)
    3. Run the test to confirm it fails
    4. Write the minimal implementation
    5. Run the test to confirm it passes
    6. Commit with a descriptive message

    ## Rules

    - Implement EXACTLY what the spec says. Nothing more (YAGNI).
    - Follow existing patterns from the target repo.
    - Every commit must leave tests passing.
    - Sign off commits: git commit --signoff

    ## Report

    Write your report to: artifacts/codegen-runs/${EPIC_ID}/v1/implementer-report.md

    Include: what you implemented, test results with TDD evidence, files
    changed, self-review findings, any concerns.

    Return ONLY (under 15 lines):
    - Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
    - Commits created (short SHA + subject)
    - One-line test summary
    - Concerns if any
```

### Step 12: Handle Implementer Response

**DONE:** proceed to validation (Step 12).

**DONE_WITH_CONCERNS:** read concerns. If about correctness or scope, address
before proceeding. If observations only, note and proceed.

**NEEDS_CONTEXT:** provide missing context, re-dispatch with same model.

**BLOCKED:** assess the blocker:
1. Context problem → provide more context, re-dispatch
2. Task too complex → re-dispatch with model: opus
3. Task too large → break it down, re-dispatch subtasks
4. Plan wrong → stop, report to user

### Step 13: Validate Target Repo

```bash
python3 scripts/validate_target.py .target-repo/ --json
```

Record validation results.

### Step 14: Generate Diff

```bash
cd .target-repo && git diff ${BASE_SHA}..HEAD > ../artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/diff.patch
```

The diff is a FILE — reviewers Read it, it never enters orchestrator context.

### Step 15: Save Version Artifacts

Save to `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/`:
- `diff.patch` — the code changes
- `validation.json` — validate_target.py output
- `implementer-report.md` — the implementer's report

Update state:
```bash
python3 scripts/state.py set tmp/epic-codegen-${EPIC_ID}.json phase=review version=${VERSION}
```

## Phase 3: Multi-Dimensional Review

### Step 16: Dispatch 5 Reviewer Subagents

Dispatch in parallel via 5 Agent tool calls, all with **model: sonnet**:

For each dimension (tests, intent, lint, architecture, patterns):

```
Agent:
  description: "Review ${EPIC_ID} — ${DIMENSION}"
  model: sonnet
  prompt: |
    You are reviewing the ${DIMENSION} dimension of code changes for ${EPIC_ID}.

    Read your rubric: rubrics/${DIMENSION}-review.md
    Read the diff: artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/diff.patch
    Read the spec: artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md
    ${VALIDATION_LINE}

    Write your review to: artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/review-${DIMENSION}.md

    Your review MUST include a YAML frontmatter block with your score:
    ---
    score: N
    ---

    Follow your rubric's output format exactly.
```

Where `${VALIDATION_LINE}` is set only for the lint reviewer:
`Read validation output: artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/validation.json`

### Step 17: Aggregate Scores

```bash
python3 scripts/score_reviews.py artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/ --json
```

Save score summary to `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/scores.json`.

Update state:
```bash
python3 scripts/state.py set tmp/epic-codegen-${EPIC_ID}.json phase=evaluate
```

## Phase 4: Iterate or Complete

### Step 18: Evaluate Verdict

Read the scoring result:

**pass** (weighted avg >= 8.0, no dimension < 6.0):
- Save final diff: `cp v${VERSION}/diff.patch final-diff.patch`
- Update state: `status=completed`
- Update epic-task: `status=Generated codegen_branch=epic/${EPIC_ID}`
- If not `--dry-run`: report that a PR could be created (but do NOT create
  it — always ask the user first)
- Report success with scores

**near-miss** (weighted avg >= 7.5, at most one dimension 5.0-5.9):
- Treat same as fail — iterate to fix

**fail** and version < max_iterations:
- Proceed to Step 18 (revision)

**fail** and version >= max_iterations:
- Find best version (highest weighted average across all versions)
- Save best diff as `best-diff.patch`
- Update state: `status=exhausted`
- Update epic-task: `status=Failed`
- Report: "Best score was X.X on vN. Recommend manual intervention."

**incomplete** (missing reviewer dimensions):
- Re-dispatch missing reviewers
- Re-aggregate

### Step 19: Prepare Revision

Read ALL reviewer feedback from files (do not paste into your context —
Read the files):
- `v${VERSION}/review-tests.md`
- `v${VERSION}/review-intent.md`
- `v${VERSION}/review-lint.md`
- `v${VERSION}/review-architecture.md`
- `v${VERSION}/review-patterns.md`

Adjudicate findings (judgment — you stay at opus):
- Real findings: confirmed issues that need fixing
- False positives: reviewer misread the code or applied wrong criteria
- Plan-mandated: finding conflicts with what plan requires — note for user

Prioritize real findings:
1. Critical (blockers)
2. Highest score-impact dimension first
3. Quick wins

Write `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/revision-notes.md`:
- Prioritized list of fixes
- For each: what to fix, why, which reviewer flagged it, file:line
- Dismissed findings with reasoning

Increment version:
```bash
python3 scripts/state.py set tmp/epic-codegen-${EPIC_ID}.json version=$((VERSION+1)) phase=implementing
mkdir -p artifacts/codegen-runs/${EPIC_ID}/v$((VERSION+1))
```

### Step 20: Re-dispatch Implementer

Dispatch fix subagent with **model: sonnet**:

```
Agent:
  description: "Fix ${EPIC_ID} v${VERSION+1}"
  model: sonnet
  prompt: |
    You are fixing review findings for epic ${EPIC_ID}.

    Read the revision notes: artifacts/codegen-runs/${EPIC_ID}/v${PREV}/revision-notes.md
    Read the codegen spec: artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md
    Read the target repo conventions: .target-repo/CLAUDE.md

    Work in: .target-repo/

    Fix each item in the revision notes. For each fix:
    1. Read the current code at the cited file:line
    2. Apply the fix
    3. Run covering tests
    4. Commit

    Write your report to: artifacts/codegen-runs/${EPIC_ID}/v${VERSION+1}/implementer-report.md

    Return ONLY (under 15 lines):
    - Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
    - Commits created
    - Test summary
```

After fix subagent completes, go to Step 13 (validate → diff → review → evaluate).

## Run Metadata

At the end of any run (pass, exhausted, or error), write
`artifacts/codegen-runs/${EPIC_ID}/run-metadata.yaml`:

```yaml
epic_id: ${EPIC_ID}
target_repo: <url>
branch: epic/${EPIC_ID}
language: <detected>
status: completed|exhausted|failed|error
versions: <count>
final_score: <weighted avg of best version>
scores_by_dimension:
  tests: N
  intent: N
  lint: N
  architecture: N
  patterns: N
started_at: <timestamp>
```

## Model Selection

| Role | Model | Rationale |
|------|-------|-----------|
| Orchestrator (you) | opus | Judgment: adjudication, false positive detection, finding prioritization |
| Implementer | sonnet | Mechanical: follows plan task-by-task |
| Fix subagent | sonnet | Mechanical: applies specific fixes |
| Reviewers (all 5) | sonnet | Task-scoped: scores against rubric |

**Always specify model explicitly in every Agent dispatch.** Omitting model
inherits session model (opus) and silently wastes cost.

## File Handoffs

Artifacts are files. They never enter your context as inline text.

| Artifact | Written by | Read by |
|----------|-----------|---------|
| strategy doc | fetch_epic.py (from Jira) | Orchestrator (spec generation) |
| codegen-spec.md | Orchestrator | Implementer, all reviewers |
| codegen-plan.md | Orchestrator | Implementer |
| diff.patch | Orchestrator (git diff) | All reviewers |
| validation.json | validate_target.py | Lint reviewer |
| review-*.md | Reviewers | Orchestrator (for adjudication only) |
| revision-notes.md | Orchestrator | Fix subagent |
| implementer-report.md | Implementer/Fix subagent | Orchestrator |

## State Recovery

If context compresses mid-run, recover from state file:

```bash
python3 scripts/state.py read tmp/epic-codegen-${EPIC_ID}.json
```

Resume at the phase and version recorded. Check `artifacts/codegen-runs/${EPIC_ID}/`
for existing version directories. Check `.target-repo/` git log for commits.
Do not re-dispatch work that artifacts show as complete.

## Error Handling

- Clone fails → report error, stop
- Readiness below threshold → report gap, stop
- Implementer BLOCKED after retry → report to user, stop
- All reviewers fail to produce scores → report error, stop
- File write fails → report error, stop

In all error cases: update state to `status=error`, update epic-task to
`status=Failed`, write run-metadata with the error.

## Rules

- Do not create a PR without explicit user approval
- Do not push to non-fork remotes
- Do not commit secrets, tokens, or credentials
- Do not push HTML reports (they may contain sensitive data)
- Do not modify files outside `.target-repo/` and `artifacts/`
- Sign off all commits: `git commit --signoff`
- Never dispatch implementers in parallel (conflicts)
- Never skip review — every version gets all 5 dimensions
- Never dismiss a finding without stating the reasoning
- Always specify model in Agent dispatches
