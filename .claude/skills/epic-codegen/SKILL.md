---
name: epic-codegen
description: Generate implementation code for a single epic from an approved strategy, using spec-first subagent-driven development with multi-dimensional review
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent, Skill
---

# Epic Code Generation

Generate implementation code for a single epic. Reads the epic-task file as
the "product owner," generates a spec and plan, invokes Superpowers SDD for
implementation, runs independent reviewer agents, and iterates until pass or
exhaustion.

**Core idea:** The epic strategy IS the product owner. The acceptance criteria
ARE the approval gate. Every human step in the Superpowers methodology is
automated — spec approval becomes AC mapping validation, plan approval becomes
task-to-AC coverage check, review steering becomes weighted score aggregation.

**Narration:** between tool calls, narrate at most one short line.

## Arguments

Parse `$ARGUMENTS` for:
- `EPIC_ID` (required) — e.g., `RHAISTRAT-1749-E001`
- `--max-iterations N` — default 5
- `--dry-run` — produce diff but do not create PR
- `--fork-owner USER` — GitHub username for fork remote (default: `dora-the-ai-coder`)
- `--gh-token-var VARNAME` — env var holding GitHub token (default: `EPIC_CODEGEN_GITHUB_TOKEN`). Required when `--fork-owner` is set. Enables: authenticated clone, fork creation, push to fork, PR creation.
- `--checks lint,test,typecheck` — which validation checks to run (default: all)

## Autonomous Operation

You ARE the human partner. The epic-task ACs are your requirements.
The strategy document and epic body are your domain knowledge.
Never stop for user input — resolve every SDD checkpoint yourself.

### Overrides — SDD would normally stop for human input

| SDD checkpoint | Your resolution |
|---|---|
| Pre-flight plan conflicts | Resolve yourself. ACs are authoritative: AC requires it → plan wins over conflicting task. AC silent → accept finding. Log resolutions in progress ledger. |
| Implementer questions | Answer from: (1) codegen-spec.md, (2) epic body, (3) strategy doc, (4) target repo code/CLAUDE.md. Re-dispatch with your answer. |
| BLOCKED — plan wrong (step 4) | Do NOT escalate. Steps 1-3 unchanged. If plan contradicts ACs, fix the plan. If unfixable, mark task blocked in ledger, skip it, continue remaining tasks. Log blocker for Phase 3. |
| NEEDS_CONTEXT | Answer from epic body + strategy + spec + repo conventions. Re-dispatch with your answer. |
| Plan-mandated findings | ACs are authoritative. AC requires the behavior → dismiss finding. AC silent → accept finding, dispatch fix. |
| Finishing | Do NOT invoke `finishing-a-development-branch`. Proceed directly to Step 13. |

### Clarifications — SDD handles internally, autonomous judgment needed

| SDD checkpoint | Your approach |
|---|---|
| Continuous execution | Execute all tasks without stopping. No progress-check prompts. |
| DONE_WITH_CONCERNS | Verify concerns against ACs. AC satisfied → note concern, proceed to review. AC violated → re-dispatch implementer. |
| Reviewer ⚠️ items | Verify each against ACs. AC covers it → resolved. Real gap → failed spec review, send back to implementer. |
| Fix report validation | If incomplete (missing tests/command/output), re-dispatch fix subagent. Do not re-dispatch reviewer until all three present. |
| Progress ledger | Follow SDD's ledger exactly at `.superpowers/sdd/progress.md`. Check at start, append completions, trust after compaction. |

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
  max_iterations=5
```

Update epic-task status:
```bash
python3 scripts/frontmatter.py set artifacts/epic-tasks/${EPIC_ID}.md status=InProgress
```

### Step 3: Clone Target Repo

If `.target-repo/` already exists and has branch `epic/${EPIC_ID}`, skip
cloning — the pipeline orchestrator already set it up. Otherwise:

```bash
python3 scripts/clone_target.py <target_repo_url> ${EPIC_ID} --clean [--fork-owner USER] [--gh-token-var EPIC_CODEGEN_GITHUB_TOKEN]
```

This clones into `.target-repo/`, creates branch `epic/${EPIC_ID}`.
If `--gh-token-var` is set: clones with token auth (handles private repos),
creates the fork if it doesn't exist, and configures the fork remote with
push credentials embedded in the URL.

### Step 4: Validate Target Repo

If `artifacts/codegen-runs/${EPIC_ID}/pre-setup.json` exists, read it —
the pipeline already ran readiness, validation, and dependency installation.
Extract language and validation commands from that file and skip to Step 5.

Otherwise, run validation manually:

```bash
python3 scripts/repo_readiness.py .target-repo/
```

Record the score and dimension breakdown in `run-metadata.yaml` under a `readiness` key. Proceed regardless of score.

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

Auto-validate:
1. Every AC from the epic-task body has a corresponding Component.
   If any AC is unmapped, stop and report the gap.
2. Every bullet in the epic's Scope section is either (a) reflected in a
   Component's pass criteria, or (b) explicitly noted as a deviation in the
   Design Decisions table with rationale. A design decision that contradicts
   a Scope item without flagging it is an error — stop and report the
   contradiction. The Scope section contains specific implementation
   requirements (e.g., "radio button," "typeahead dropdown") that may be
   more precise than the numbered ACs.

### Step 9: Write Codegen Plan

Create `artifacts/codegen-runs/${EPIC_ID}/codegen-plan.md`:

```markdown
# ${EPIC_ID} Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan task-by-task.
> Steps use checkbox syntax for tracking.

**Goal:** [one sentence from epic ACs]
**Architecture:** [from strategy technical approach]
**Tech Stack:** [from target repo detection]

## Global Constraints
[From spec + target repo CLAUDE.md: version floors, naming rules, platform
requirements, additive-only, no new dependencies, etc.]

## Model Override

All implementer and reviewer subagents MUST use the session's inherited model
(do not specify a model override). The SDD Model Selection section does not
apply to this plan — the calling skill requires all agents to run at the
session's model tier.

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

### Step 11: Initialize SDD Workspace

Run the SDD workspace setup in the target repo:

```bash
cd .target-repo && bash ../superpowers/scripts/sdd-workspace
```

This creates `.superpowers/sdd/` with the progress ledger.

### Step 12: Invoke SDD

Invoke the Superpowers subagent-driven-development skill:

```
Skill("superpowers:subagent-driven-development")
```

SDD reads the plan file (`codegen-plan.md`), recognizes the plan header, and
runs its full pipeline:
1. Creates todos from plan tasks
2. Per task: dispatches implementer → task review → fix loops
3. Updates progress ledger at `.target-repo/.superpowers/sdd/progress.md`
4. Runs final whole-branch code review

**Model override:** when SDD dispatches implementer or reviewer subagents, do
NOT fill in the `[MODEL]` placeholder in the prompt templates. Leave it omitted
so subagents inherit the session model. The SDD Model Selection section ("use
the least powerful model") does not apply — this pipeline requires consistent
model quality across all agents. The plan's `## Model Override` section
reinforces this.

**Override:** when SDD reaches `finishing-a-development-branch`, do NOT invoke
that skill. Proceed directly to Step 13.

### Step 13: Save Version Artifacts

After SDD completes:

```bash
cd .target-repo && git diff ${BASE_SHA}..HEAD > ../artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/diff.patch
```

```bash
python3 scripts/validate_target.py .target-repo/ --json > artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/validation.json
```

Save to `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/`:
- `diff.patch` — the code changes (FILE — reviewers Read it, never inline)
- `validation.json` — validate_target.py output

Update state:
```bash
python3 scripts/state.py set tmp/epic-codegen-${EPIC_ID}.json phase=review version=${VERSION}
```

### Step 13.5: Verify Wiring

Dispatch a wiring verification agent to trace execution paths for each AC.
This catches broken chains (function defined but never called, handler not
registered, state updated but never read) that code-reading reviewers miss.

```
Agent:
  description: "Verify wiring ${EPIC_ID} v${VERSION}"
  prompt: |
    Verify that every AC has a complete, connected execution path from
    trigger to outcome.

    DIFF_FILE = artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/diff.patch
    SPEC_FILE = artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md
    EPIC_FILE = artifacts/epic-tasks/${EPIC_ID}.md
    REVIEW_FILE = artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/review-wiring.md
```

The wiring review is NOT a scored dimension — it does not affect the weighted
average. Its findings are read during Step 17 (triage) and fed to the fix
subagent alongside findings from the 4 scored reviewers.

If the wiring verifier reports Critical findings, proceed to Step 14 normally.

## Phase 3: Multi-Dimensional Review

### Step 14: Dispatch 4 Reviewer Agents

Dispatch in parallel via 4 Agent tool calls.

Each reviewer is a standalone agent definition in `agents/`. The orchestrator
dispatches them — it does not construct reviewer prompts inline.

For each dimension (architecture, tests, lint, intent):

```
Agent:
  description: "Review ${EPIC_ID} — ${DIMENSION}"
  agentType: "${DIMENSION}-reviewer"
  prompt: |
    Review the code changes for ${EPIC_ID}.

    DIFF_FILE = artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/diff.patch
    SPEC_FILE = artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md
    REVIEW_FILE = artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/review-${DIMENSION}.md
    ${EXTRA_FILES}
```

Where `${EXTRA_FILES}` is set per dimension:
- **architecture:** `CLAUDE_MD_FILE = .target-repo/CLAUDE.md`
- **tests:** (none — reads spec ACs)
- **lint:** `VALIDATION_FILE = artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/validation.json`
- **intent:** `EPIC_FILE = artifacts/epic-tasks/${EPIC_ID}.md` (verifies against original ACs, not just the spec's interpretation)

### Step 15: Aggregate Scores

```bash
python3 scripts/score_reviews.py artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/ --json
```

Save score summary to `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/scores.json`.

Update state:
```bash
python3 scripts/state.py set tmp/epic-codegen-${EPIC_ID}.json phase=evaluate
```

## Phase 4: Iterate or Complete

### Step 16: Evaluate Verdict

Read the scoring result:

**pass** (weighted avg >= 8.0, no dimension < 6.0):
- Save final diff: `cp v${VERSION}/diff.patch final-diff.patch`
- Update state: `status=completed`
- Update epic-task: `status=Generated codegen_branch=epic/${EPIC_ID}`
- If `--fork-owner` is set and not `--dry-run`, push and create PR:
  ```bash
  python3 scripts/push_to_fork.py .target-repo/ epic/${EPIC_ID} --json
  python3 scripts/create_pr.py <upstream_slug> <fork_owner> epic/${EPIC_ID} \
      --title "${EPIC_ID}: <epic title>" \
      --body "<scores summary + link to codegen spec>" \
      --gh-token-var EPIC_CODEGEN_GITHUB_TOKEN --json
  ```
  The PR targets the upstream repo's default branch (auto-detected).
  Update epic-task: `pr_url=<html_url from result>`
- Report success with scores and PR URL

**near-miss** (weighted avg >= 7.5, at most one dimension 5.0-5.9):
- Treat same as fail — iterate to fix

**fail** and version < max_iterations:
- Proceed to Step 17 (revision)

**fail** and version >= max_iterations:
- Find best version (highest weighted average across all versions)
- Save best diff as `best-diff.patch`
- Update state: `status=exhausted`
- Update epic-task: `status=Failed`
- Report: "Best score was X.X on vN. Recommend manual intervention."

**incomplete** (missing reviewer dimensions):
- Re-dispatch missing reviewers
- Re-aggregate

### Step 17: Prepare Revision

Read ALL reviewer and verifier feedback from files (do not paste into your
context — Read the files):
- `v${VERSION}/review-architecture.md`
- `v${VERSION}/review-tests.md`
- `v${VERSION}/review-lint.md`
- `v${VERSION}/review-intent.md`
- `v${VERSION}/review-wiring.md` (not scored, but findings go to fix subagent)

Triage findings for the fix subagent. The script's scores and verdict are
final — you cannot override them. Your job is to prioritize which findings
the fix subagent should address:

1. Critical findings first (these cap the dimension score at 5)
2. Important findings next (each costs 1.5 points)
3. Minor findings last (each costs 0.5 points)

For pre-existing issues outside the diff (e.g., lint failures in unrelated
files), note them as "pre-existing — fix subagent should not attempt" so
the fix agent doesn't waste time on them. These still count toward the
score — the code must pass clean to score well.

Write `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/revision-notes.md`:
- Prioritized list of findings to fix
- For each: what to fix, why, which reviewer flagged it, file:line
- Pre-existing issues noted separately (not fixable by this pipeline)

Increment version:
```bash
python3 scripts/state.py set tmp/epic-codegen-${EPIC_ID}.json version=$((VERSION+1)) phase=implementing
mkdir -p artifacts/codegen-runs/${EPIC_ID}/v$((VERSION+1))
```

### Step 18: Re-dispatch Fix Subagent

Dispatch fix subagent:

```
Agent:
  description: "Fix ${EPIC_ID} v${VERSION+1}"
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

After fix subagent completes, go to Step 13 (save artifacts → review →
evaluate). Do NOT re-enter SDD for targeted fixes.

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
  architecture: N
  tests: N
  lint: N
  intent: N
started_at: <timestamp>
```

After writing run-metadata, update the run index:

```bash
python3 scripts/run_index.py artifacts/codegen-runs/
```

This writes `artifacts/codegen-runs/index.json` — a structured aggregate
of all runs for dashboard consumption.

## Model Selection

All agents run on the session model (no model overrides). The codegen plan
contains a `## Model Override` section that instructs the SDD controller to
skip its own model selection and inherit the session model for all subagents.

When we move to cost optimization, downgrade mechanical roles (implementer,
fix subagent) to sonnet first. Keep opus for judgment roles (orchestrator,
reviewers) longest.

## Review Dimensions

4 independent reviewer agents, each a standalone definition in `agents/`:

| Dimension | Agent | Weight | Focus |
|-----------|-------|--------|-------|
| architecture | `agents/architecture-reviewer.md` | 30% | Repo conventions, structural fit, integration quality |
| tests | `agents/tests-reviewer.md` | 30% | AC coverage, TDD evidence, edge cases, assertion quality |
| lint | `agents/lint-reviewer.md` | 20% | Lint/typecheck/build pass, code style, error handling |
| intent | `agents/intent-reviewer.md` | 20% | AC alignment, scope check, semantic correctness |

Pluggable: add/remove/replace a dimension = add/remove an agent file +
update score_reviews.py weights.

## File Handoffs

Artifacts are files. They never enter your context as inline text.

| Artifact | Written by | Read by |
|----------|-----------|---------|
| strategy doc | fetch_epic.py (from Jira) | Orchestrator (spec generation) |
| codegen-spec.md | Orchestrator | SDD implementers, all reviewer agents |
| codegen-plan.md | Orchestrator | SDD (reads plan, dispatches tasks) |
| task-N-brief.md | SDD task-brief script | SDD implementer |
| task-N-report.md | SDD implementer | SDD task reviewer |
| review-package diff | SDD review-package script | SDD task reviewer, final reviewer |
| progress.md | SDD | SDD on resume |
| diff.patch | Orchestrator (git diff) | All reviewer agents |
| validation.json | validate_target.py | Lint reviewer agent |
| review-{arch,tests,lint,intent}.md | Reviewer agents | score_reviews.py (scoring), Orchestrator (triage) |
| review-wiring.md | Wiring verifier | Orchestrator (triage only, not scored) |
| revision-notes.md | Orchestrator | Fix subagent |

## State Recovery

If context compresses mid-run, recover from BOTH:

1. State file:
```bash
python3 scripts/state.py read tmp/epic-codegen-${EPIC_ID}.json
```

2. SDD progress ledger:
```
.target-repo/.superpowers/sdd/progress.md
```

Resume at the phase and version recorded. Check `artifacts/codegen-runs/${EPIC_ID}/`
for existing version directories. Check `.target-repo/` git log for commits.
Do not re-dispatch work that artifacts show as complete.

## Error Handling

- Clone fails → report error, stop
- Readiness below threshold → log warning with gaps, proceed
- SDD reports BLOCKED after retry → report to user, stop
- All reviewers fail to produce scores → report error, stop
- File write fails → report error, stop

In all error cases: update state to `status=error`, update epic-task to
`status=Failed`, write run-metadata with the error.

## Rules

- Do not push to non-fork remotes
- Do not commit secrets, tokens, or credentials
- Do not push HTML reports (they may contain sensitive data)
- Do not modify files outside `.target-repo/` and `artifacts/`
- Sign off all commits: `git commit --signoff`
- Never dispatch implementers in parallel (conflicts)
- Never skip review — every version gets all 4 dimensions
- Never override reviewer scores or the script's verdict
- All agents inherit opus from session (no model overrides during validation)
