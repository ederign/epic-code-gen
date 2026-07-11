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
- `--max-iterations N` — default 10
- `--dry-run` — produce diff but do not create PR
- `--fork-owner USER` — GitHub username for fork remote (default: `dora-the-ai-coder`)
- `--gh-token-var VARNAME` — env var holding GitHub token (default: `EPIC_CODEGEN_GITHUB_TOKEN`). Required when `--fork-owner` is set. Enables: authenticated clone, fork creation, push to fork, PR creation.
- `--checks lint,test,typecheck` — which validation checks to run (default: all)

## Autonomous Operation

You ARE the human partner. The epic-task ACs are your requirements.
The strategy document and epic body are your domain knowledge.
Never stop for user input — resolve every checkpoint yourself.

### Overrides — Brainstorming (Step 8)

The design subagent invokes brainstorming and acts as the human partner.
It answers all brainstorming questions from the context brief (which
contains the epic body, strategy, existing implementations, conventions,
and callers gathered in Steps 5-7). See Step 8 for the full subagent
prompt and overrides.

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
  max_iterations=10
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

Focus on two sections:
1. **"Strategy (AI Generated by Agentic SDLC Pipeline)"** — technical
   approach, affected components, high-level requirements, scope
2. **"Staff Engineer Input"** — constraints, corrections, refined
   requirements. This section is authoritative — it overrides the
   AI-generated strategy where they conflict.

Together with the epic-task body, these are your "interview transcript" —
all the context a product owner would provide.

### Step 6: Read Repo Context

Read from `.target-repo/`:
- `CLAUDE.md` or `AGENTS.md` (target repo conventions)
- `CONTRIBUTING.md` if present
- Key files named in the epic body (reference implementations, target files)

### Step 7: Pattern Discovery

**7a — Explicit references:** Search the target repo for patterns referenced
in the epic body: function names, type names, file paths mentioned in the
epic. Read the reference files.

**7b — Concept search:** Extract the key concepts the epic needs to implement
(e.g., "conflict detection", "lazy loading", "middleware filter", "form
validation", "caching layer", "webhook handler"). For each concept, search
the entire codebase for existing implementations:
- Grep for related terms, function names, module names
- When you find an existing implementation of the same concept, read it
  thoroughly — it shows exactly how THIS codebase solves that problem
- Record each existing implementation as a reference pattern with file:line

This is the highest-value step. Most code is built on top of existing code.
The implementer should extend or follow existing patterns, not invent new
ones. If the codebase already has conflict detection, the epic's conflict
detection should use the same approach. If the codebase already has a
middleware chain, the new middleware should follow the same structure.

**7c — Target file analysis:** From the epic body + strategy, identify every
file that will be modified or created. For each existing target file:
- Read it fully — understand its internal structure, not just the symbol
  you're looking for
- Find 5-10 sibling files (same directory, same extension) and read them.
  Siblings reveal local conventions: naming, error handling, data flow,
  test structure, ID generation patterns. More samples = more reliable
  pattern detection.
- Check sibling directories (directories at the same level as the target
  file's parent). These often contain analogous modules that solve similar
  problems — look for how they handle the same concerns (state, validation,
  error handling, testing) that the epic's changes will need to address.
  Read 2-3 representative files from each relevant sibling directory.
- Grep for imports/usages of the target file's exports to find callers.
  Read the key callers to understand how the code being modified is consumed
  (e.g., is it instantiated once or many times? is it called in a loop?
  does the caller pass data via arguments or shared state?)

**7d — Document conventions:** From 7a-7c, write a conventions summary
to include in the codegen spec. Capture only what is relevant for THIS
epic's changes:
- Naming patterns (files, functions, variables, identifiers)
- Data flow patterns (how data/state passes between modules)
- Error handling patterns
- Testing conventions (setup, assertions, fixtures)
- Any pattern the existing sibling files follow consistently

Keep the summary under 30 lines. If conventions are already documented in
`CLAUDE.md` or `CONTRIBUTING.md`, reference those instead of repeating them.

### Step 8: Generate Design Spec via Brainstorming

Before writing the spec, prepare a context brief that summarizes everything
gathered in Steps 5-7. Write it to
`artifacts/codegen-runs/${EPIC_ID}/context-brief.md`:

```markdown
# Context Brief: ${EPIC_ID}

## Epic Requirements
<paste the full epic-task body — ACs, scope, target files, reference patterns>

## Strategy Context
<from the strategy doc, include ONLY these two sections:>
<1. "Strategy (AI Generated by Agentic SDLC Pipeline)" — technical approach,
   affected components, high-level requirements, scope, out-of-scope>
<2. "Staff Engineer Input" — constraints, corrections, refined requirements.
   This section overrides the AI-generated strategy where they conflict.>

## Target Repo
- Repo: <target_repo URL>
- Language: <detected language>
- Conventions file: .target-repo/CLAUDE.md (or AGENTS.md, CONTRIBUTING.md)

## Existing Implementations (from Step 7b)
<each existing implementation found in the codebase that solves concepts
this epic needs — file:line, what it does, why it's relevant>

## Conventions (from Step 7d)
<naming, data flow, error handling, testing patterns from sibling files>

## Callers (from Step 7c)
<for each target file: who imports/uses it, how they consume it>
```

Then dispatch a design subagent that invokes Superpowers brainstorming to
generate the spec. The subagent acts as the human partner — answering
brainstorming's questions from the context brief:

```
Agent:
  description: "Design spec ${EPIC_ID}"
  prompt: |
    You are generating a design spec for epic ${EPIC_ID}.

    ## Your Context

    You have ALL the information needed to make design decisions:
    - Context brief: artifacts/codegen-runs/${EPIC_ID}/context-brief.md
    - Epic task: artifacts/epic-tasks/${EPIC_ID}.md
    - Strategy: artifacts/strategies/${STRATEGY_KEY}.md
    - Target repo: .target-repo/

    Read the context brief first — it contains the epic requirements,
    existing implementations, conventions, and callers.

    ## Process

    Invoke Skill("superpowers:brainstorming") to guide your design.

    ## Autonomous Overrides

    You ARE the human partner for brainstorming. You have all the
    requirements and codebase knowledge. When brainstorming:

    - **Asks clarifying questions**: answer from the context brief.
      The epic-task body has the ACs and scope. The strategy doc has
      the business need and technical approach. The existing
      implementations show how the codebase solves similar problems.
    - **Proposes approaches**: evaluate each approach against the
      existing implementations in the context brief. Prefer approaches
      that extend existing patterns over building new abstractions.
    - **Presents design sections**: approve sections that align with
      the epic ACs and existing codebase patterns. If a section
      contradicts either, request revision with specific reasons.
    - **Offers visual companion**: decline.
    - **Asks for scope decomposition**: the epic is already scoped.
      Proceed with the full epic as one design unit.

    ## Conversation Log

    As you work through brainstorming, record the full conversation in
    artifacts/codegen-runs/${EPIC_ID}/brainstorming-log.md:
    - Every question brainstorming asks (or would ask)
    - Your answer and the context you used to answer it
    - Approach proposals and your evaluation of each
    - Design decisions and rationale

    This log is the primary artifact for understanding WHY the spec
    looks the way it does. Write it as you go, not after the fact.

    ## Output Overrides

    - Write the spec to: artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md
      (NOT docs/superpowers/specs/)
    - Do NOT commit the spec — the pipeline manages commits
    - Do NOT invoke writing-plans — return after the spec is written
      and self-reviewed

    ## Spec Requirements

    The spec MUST include (brainstorming covers most of these naturally):
    - Every AC from the epic-task mapped to a design section
    - File paths for every file to modify or create
    - References to existing implementations that the design extends
    - Out of scope section (from the epic's exclusions)

    After writing: verify every AC has coverage in the spec. If any AC
    is unmapped, add a section for it before finishing.
```

Wait for the design subagent to complete. Read the generated spec at
`artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md`.

### Step 8.5: Spec Review Gate

Dispatch a review agent to validate the spec against the target repo's
actual patterns before proceeding to plan generation:

```
Agent:
  description: "Spec review ${EPIC_ID}"
  prompt: |
    You are reviewing a codegen spec for pattern mismatches against the
    target repo's existing code.

    Read the spec: artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md

    For each design section that names target files:
    1. Read the target file in .target-repo/
    2. Read 1-2 sibling files (same directory, same extension)
    3. If the spec names callers or consumers, read those files

    Check for these mismatches (language-agnostic):

    - **Data flow**: the spec proposes passing data between modules in a
      way that differs from how existing code in the same area does it
    - **Naming**: proposed names don't match the naming conventions in
      sibling files
    - **Reuse**: the spec proposes building something new when an existing
      utility or module in the repo already does the same thing
    - **Integration**: the spec modifies a module without accounting for
      how its callers use it (e.g., callers instantiate it multiple times,
      callers depend on a specific interface, callers pass unique
      identifiers)
    - **Testing**: the spec proposes test patterns that don't match how
      tests in the same directory are structured

    Return a structured list:
    - Section/component name
    - Mismatch category
    - What the spec proposes vs what existing code does
    - Recommended fix

    If no mismatches found, return "CLEAN".
```

If the agent returns mismatches:
- Update the spec to fix them
- Re-verify AC coverage

If clean, proceed to Step 9.

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

### Step 15.5: Write Decision Log

Write `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/decision-log.md` with the
scoring results and the verdict path about to be taken. This log is the primary
artifact for post-run analysis.

```markdown
# Decision Log — ${EPIC_ID} v${VERSION}

## Timestamp
<output of: python3 scripts/state.py timestamp>

## Scores
| Dimension | Score | Findings (C/I/M) | Weight | Weighted |
|-----------|-------|-------------------|--------|----------|
| architecture | X.X | C/I/M | 30% | X.XX |
| tests | X.X | C/I/M | 30% | X.XX |
| lint | X.X | C/I/M | 20% | X.XX |
| intent | X.X | C/I/M | 20% | X.XX |

**Weighted Average:** X.X/10
**Verdict:** pass | near-miss | fail | incomplete

## Decision Path
<which Step 16 branch will be taken>
- Version: N of max_iterations
- Path: pass → PR | near-miss → iterate | fail → iterate | near-miss+exhausted → PR | fail+exhausted → report | incomplete → re-dispatch
```

Append to this log in subsequent steps (Step 17 triage, Step 18 fix result).

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

**near-miss** (weighted avg >= 7.0, at most one dimension 5.0-5.9):
- Treat same as fail — iterate to fix

**fail** and version < max_iterations:
- Proceed to Step 17 (revision)

**near-miss** and version >= max_iterations:
- Find best version (highest weighted average across all versions)
- If best version verdict is **near-miss**: push and create PR with a note
  that human review is needed on code quality findings:
  ```bash
  python3 scripts/push_to_fork.py .target-repo/ epic/${EPIC_ID} --json
  python3 scripts/create_pr.py <upstream_slug> <fork_owner> epic/${EPIC_ID} \
      --title "${EPIC_ID}: <epic title>" \
      --body "<scores summary + note: near-miss after N iterations, human review needed>" \
      --gh-token-var EPIC_CODEGEN_GITHUB_TOKEN --json
  ```
  Before pushing, check out the best version's code:
  `git -C .target-repo/ reset --hard <best-version-sha>`
  Save best diff as `best-diff.patch` and `final-diff.patch`
  Update state: `status=completed`
  Update epic-task: `status=Generated pr_url=<html_url>`

**fail** and version >= max_iterations:
- **DO NOT push code or create a PR. Failed code must not be published.**
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

**Oscillation detection:** If VERSION > 2, also read the revision-notes from
prior versions (`v1/revision-notes.md` through `v${VERSION-1}/revision-notes.md`).
Compare each current finding against prior versions' findings. A finding is
**oscillating** if:
- It was fixed in a prior version (appeared in vN revision-notes, absent in
  vN+1 reviews) but reappeared in a later version, OR
- Fixing it in a prior version caused a contradicting finding in a different
  reviewer dimension (e.g., architecture said "centralize X" → lint said
  "duplicate computation of X" after the centralization was done)

Mark oscillating findings as **skip — oscillating** in the revision notes.
The fix subagent must not touch these areas — fixing them will recreate the
opposite finding. Focus remaining fix effort on non-oscillating findings.

Triage non-oscillating findings for the fix subagent. The script's scores
and verdict are final — you cannot override them. Your job is to prioritize
which findings the fix subagent should address:

1. Critical findings first (these cap the dimension score at 5)
2. Important findings next (each costs 1.5 points)
3. Minor findings last (each costs 0.5 points)

For pre-existing issues outside the diff (e.g., lint failures in unrelated
files), note them as "pre-existing — fix subagent should not attempt" so
the fix agent doesn't waste time on them. These still count toward the
score — the code must pass clean to score well.

Write `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/revision-notes.md`:
- Oscillating findings (skip — do not fix)
- Prioritized list of non-oscillating findings to fix
- For each: what to fix, why, which reviewer flagged it, file:line
- Pre-existing issues noted separately (not fixable by this pipeline)

Append triage decisions to the decision log
(`artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/decision-log.md`):

```markdown
## Triage Decisions

| # | Finding | Dimension | Severity | Disposition | Reason |
|---|---------|-----------|----------|-------------|--------|
| 1 | <finding summary> | architecture | Critical | fix | <why> |
| 2 | <finding summary> | lint | Important | skip — oscillating | <which versions> |
| 3 | <finding summary> | tests | Minor | skip — pre-existing | outside diff |

## Triage Summary
- Findings to fix: N (Criticals: N, Importants: N, Minors: N)
- Oscillating (skip): N
- Pre-existing (skip): N
- Total findings across all reviewers: N
```

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

    Fix ALL items in the revision notes. For each fix:
    1. Read the current code at the cited file:line
    2. Apply the fix

    After ALL fixes are applied:
    3. Run lint/typecheck once
    4. Run tests once
    5. Commit all changes in a single commit

    Write your report to: artifacts/codegen-runs/${EPIC_ID}/v${VERSION+1}/implementer-report.md

    Return ONLY (under 15 lines):
    - Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
    - Commits created
    - Test summary
```

After fix subagent completes, append the result to the decision log
(`artifacts/codegen-runs/${EPIC_ID}/v${PREV_VERSION}/decision-log.md`,
where PREV_VERSION is the version whose triage triggered this fix):

```markdown
## Fix Agent Result
- Status: <DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT>
- Commits: <count>
- Tests: <pass | fail — summary>
- Findings addressed: <N of M from revision notes>
```

Then go to Step 13 (save artifacts → review → evaluate). Do NOT re-enter
SDD for targeted fixes.

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
| strategy doc | fetch_epic.py (from Jira) | Orchestrator (context brief) |
| context-brief.md | Orchestrator (Steps 5-7 summary) | Brainstorming design subagent |
| brainstorming-log.md | Brainstorming design subagent | Post-run analysis (not consumed by pipeline) |
| codegen-spec.md | Brainstorming design subagent (validated by spec review gate) | SDD implementers, all reviewer agents |
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
| decision-log.md | Orchestrator | Post-run analysis (not consumed by pipeline) |

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
- Never push code or create a PR unless the verdict is **pass** or **near-miss** (near-miss only when iterations are exhausted)
- All agents inherit opus from session (no model overrides during validation)
