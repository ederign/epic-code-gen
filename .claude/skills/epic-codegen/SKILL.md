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

**Working directory:** ALL pipeline script calls (`scripts/*.py`,
`scripts/*.js`) MUST run from the project root — NOT from `.target-repo/`.
After dispatching a subagent that works in `.target-repo/`, verify your
cwd is the project root before running any `python3 scripts/...` command.
If in doubt, use an absolute path or prefix with `cd /path/to/epic-code-gen &&`.

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

### Overrides — Brainstorming (Step 8) and writing-plans (Step 9)

Each Superpowers skill runs in its own subagent for reliable isolation:

- **Brainstorming subagent** (Step 8): invokes brainstorming, acts as
  the human partner answering questions from the context brief. Does NOT
  invoke writing-plans — returns after the spec is written.
- **writing-plans subagent** (Step 9): invokes writing-plans, acts as
  the human partner. Does NOT invoke SDD or executing-plans — returns
  after the plan is written.

See Steps 8 and 9 for the full subagent prompts and overrides.

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
- Key files named in the epic body (reference implementations, target files)
- `CONTRIBUTING.md` if present

**Scan for agent-readiness files** across the entire repo. These are the
highest-signal convention sources — they were written specifically to tell
agents how the codebase works:

```bash
find .target-repo/ -name "CLAUDE.md" -o -name "AGENTS.md" \
  -o -name ".cursorrules" -o -name ".cursor/rules" \
  -o -name "GEMINI.md" -o -name "COPILOT.md" \
  -o -name ".github/copilot-instructions.md" \
  -o -name "CONVENTIONS.md" -o -name "CONSTITUTION.md" \
  -o -name "constitution.md" -o -name ".constitution" \
  2>/dev/null
```

Read ALL found files. Pay special attention to:
- **Root-level files** (`CLAUDE.md`, `AGENTS.md`): repo-wide conventions
- **Nested files** (e.g., `frontend/CLAUDE.md`, `pkg/api/AGENTS.md`):
  subsystem-specific conventions that apply to the target files for this
  epic. These often contain the most relevant patterns.
- **Cursor/Copilot rules**: often contain coding standards, naming
  conventions, and architecture notes that apply to the whole repo

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

Include every convention that is relevant to the epic's changes — do not
truncate. If conventions are already documented in `CLAUDE.md` or
`CONTRIBUTING.md`, reference those instead of repeating them.

### Step 7.5: Parse UX Prototype (if available)

Check the strategy body (read in Step 5) for a UXD marker indicating
UX prototype availability. Look for patterns like:
- "UXD Support: Required" or "UXD Support Required"
- A referenced HTML filename (e.g., "attached in Jira in the file: create-workbench-env-vars.html")

If UXD marker is found:

1. Check `artifacts/strategies/prototypes/${STRATEGY_KEY}/` for HTML files.
   If none exist (manual placement or download failed), log a warning:
   "UXD Support marked Required but no prototype HTML found" and continue.

2. If HTML file found, run the prototype parser:
   ```bash
   node scripts/parse_prototype.js \
     artifacts/strategies/prototypes/${STRATEGY_KEY}/<filename>.html \
     artifacts/codegen-runs/${EPIC_ID}/prototype-analysis/
   ```

3. Read `artifacts/codegen-runs/${EPIC_ID}/prototype-analysis/prototype-summary.md`
   for inclusion in the context brief.

If no UXD marker in the strategy body, skip this step silently.

### Step 8: Generate Design Spec via Brainstorming

**SEQUENCING: Steps 5-7.5 MUST complete before Step 8 begins.** The context
brief below is built from pattern discovery results. If pattern discovery
has not finished, STOP and wait for it. Do NOT dispatch the brainstorming
subagent until the context brief is fully written with real data from
Steps 5-7.

Prepare a context brief that summarizes everything gathered in Steps 5-7.
Write it to
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

## Prototype Scenarios (from Step 7.5)
<If a UX prototype was parsed, include the full prototype-summary.md content here.
 This section provides:
 - Component inventory (PatternFly components and variants UX selected)
 - Per-scenario descriptions with alerts, states, disabled elements
 - Screenshot file paths for visual reference

 ### PatternFly Compliance Rule
 When a UX prototype is provided, the implementation MUST use the same
 PatternFly components identified in the Component Inventory above.
 Do not substitute alternative components or custom implementations
 for components that UX has explicitly specified in the prototype.
 Follow PatternFly conventions for all component usage — variants,
 props, accessibility attributes, and layout patterns.

 ### Scenario Screenshots
 <list screenshot file paths from prototype-analysis/ for brainstorming
  to reference via the Read tool when visual detail is needed>

 If no prototype was parsed, OMIT this entire section.>
```

Then dispatch the design spec generator:

```
Agent:
  description: "Design spec ${EPIC_ID}"
  agentType: "design-spec-generator"
  prompt: |
    Generate a design spec for ${EPIC_ID}.

    CONTEXT_BRIEF = artifacts/codegen-runs/${EPIC_ID}/context-brief.md
    EPIC_FILE = artifacts/epic-tasks/${EPIC_ID}.md
    STRATEGY_FILE = artifacts/strategies/${STRATEGY_KEY}.md
    SPEC_FILE = artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md
    LOG_FILE = artifacts/codegen-runs/${EPIC_ID}/brainstorming-log.md
```

Wait for the design subagent completion notification. Do NOT poll the
filesystem for the spec file — the Agent tool notifies you automatically
when the subagent finishes. Read the generated spec at
`artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md`.

### Step 8.5: Spec Review Gate

Dispatch the spec reviewer agent to validate the spec against the target
repo's actual patterns before proceeding to plan generation:

```
Agent:
  description: "Spec review ${EPIC_ID}"
  agentType: "spec-reviewer"
  prompt: |
    Review the codegen spec for ${EPIC_ID}.

    SPEC_FILE = artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md
    LOG_FILE = artifacts/codegen-runs/${EPIC_ID}/spec-review-log.md
```

Wait for the spec reviewer completion notification. Do NOT poll the
filesystem — the Agent tool notifies you when the subagent finishes.

If the agent returns mismatches:
- Update the spec to fix them
- Re-verify AC coverage

If clean, proceed to Step 9.

### Step 9: Generate Implementation Plan via writing-plans

Dispatch the plan generator:

```
Agent:
  description: "Write plan ${EPIC_ID}"
  agentType: "plan-generator"
  prompt: |
    Generate an implementation plan for ${EPIC_ID}.

    SPEC_FILE = artifacts/codegen-runs/${EPIC_ID}/codegen-spec.md
    EPIC_FILE = artifacts/epic-tasks/${EPIC_ID}.md
    PLAN_FILE = artifacts/codegen-runs/${EPIC_ID}/codegen-plan.md
    LOG_FILE = artifacts/codegen-runs/${EPIC_ID}/writing-plans-log.md
```

Wait for the plan subagent to complete. Validate the output at
`artifacts/codegen-runs/${EPIC_ID}/codegen-plan.md`:

1. File exists and has the writing-plans header (Goal, Architecture,
   Tech Stack, Global Constraints)
2. The `## Model Override` section is present
3. Every design section in the spec has at least one plan Task
4. Every Task has a test step

If validation fails, re-dispatch the plan subagent.

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

Create the SDD workspace in the target repo:

```bash
mkdir -p .target-repo/.superpowers/sdd
printf '*\n' > .target-repo/.superpowers/sdd/.gitignore
```

This creates `.superpowers/sdd/` (gitignored) for SDD artifacts: task
briefs, implementer reports, review packages, and the progress ledger.

### Step 12: Invoke SDD

Read the plan into context so SDD can find it:
```
Read artifacts/codegen-runs/${EPIC_ID}/codegen-plan.md
```

Then invoke the Superpowers subagent-driven-development skill:

```
Skill("superpowers:subagent-driven-development")
```

SDD sees the plan in conversation context, recognizes the plan header, and
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

**Override — skip SDD final review:** when SDD finishes all tasks and is about
to dispatch the final whole-branch code review, SKIP it. The pipeline's Phase 3
runs 4 specialized reviewers with deterministic scoring — SDD's general review
is redundant. Proceed directly to Step 13.

**Override — skip finishing:** do NOT invoke `finishing-a-development-branch`.
Proceed directly to Step 13.

### Step 13: Save Version Artifacts

After SDD completes:

```bash
cd .target-repo && git diff ${BASE_SHA}..HEAD > ../artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/diff.patch
```

```bash
python3 scripts/validate_target.py .target-repo/ --json > artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/validation.json
```

Copy SDD workspace into artifacts for analysis:
```bash
cp -r .target-repo/.superpowers/sdd/ artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/sdd-workspace/
```

Save to `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/`:
- `diff.patch` — the code changes (FILE — reviewers Read it, never inline)
- `validation.json` — validate_target.py output
- `sdd-workspace/` — SDD artifacts (task briefs, reports, progress ledger)

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

## Phase 3+4: Review, Iterate, Complete

### Step 14: Review-Fix Iteration Loop

Each iteration is orchestrated by `scripts/review_cycle.py` — Python
handles all deterministic work (prompt construction, file polling, scoring).
The parent stays as a thin dispatcher that reads script output and launches
agents mechanically. No AI judgment in the dispatch loop.

**REVIEW DISPATCH LOOP** — follow this exactly:

```
1. python3 scripts/review_cycle.py prompts ${EPIC_ID} ${VERSION}
2. Parse YAML output. For each agent in agents list:
   - Build prompt: vars + "\n\nRead " + prompt_file
       + " and follow all instructions exactly."
   - Launch as background Agent. Do NOT use agentType/subagent_type.
3. python3 scripts/review_cycle.py wait ${EPIC_ID} ${VERSION} --max-wait 90
   - If exit code 3: re-run this command (agents still working)
4. python3 scripts/review_cycle.py verify ${EPIC_ID} ${VERSION}
   - If exit code 1: log FAILED dimensions, re-dispatch only those
     (back to step 1 with --only=<failed dims>)
5. python3 scripts/review_cycle.py score ${EPIC_ID} ${VERSION}
   - If exit code 2: incomplete — re-dispatch missing
     (back to step 1 with --only=<missing dims>)
6. Read scores.json from version dir
   - If pass: save final diff, push if configured, done
   - If fail/near-miss: continue to step 7
7. triage_vars=$(python3 scripts/review_cycle.py triage-prompt \
     ${EPIC_ID} ${VERSION})
8. Launch Agent:
   prompt = triage_vars + "\n\nRead .claude/agents/iteration-reviewer.md
     and follow all instructions exactly."
   Do NOT use agentType.
9. Parse triage result JSON
   - If fix_applied: VERSION = fix_version, go to step 1
   - Else: break (nothing fixable)
```

**Why no agentType:** Reviewer agents are defined with `tools: Read, Glob,
Grep` — when dispatched with `agentType`, they cannot write review files.
By dispatching WITHOUT `agentType`, agents get full tools (including Write)
while still reading their agent definition file as instructions.

**Iteration state** is tracked by `review_cycle.py` and state files:
- Version tracking: `tmp/epic-codegen-${EPIC_ID}.json`
- Accepted findings: `tmp/accepted-findings-${EPIC_ID}.json`
- All review files: `artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/`

Before entering the dispatch loop, save version artifacts:

```bash
cd .target-repo && git diff ${BASE_SHA}..HEAD > \
  ../artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/diff.patch
python3 scripts/validate_target.py .target-repo/ --json > \
  artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/validation.json
cp -r .target-repo/.superpowers/sdd/ \
  artifacts/codegen-runs/${EPIC_ID}/v${VERSION}/sdd-workspace/ 2>/dev/null
python3 scripts/state.py set tmp/epic-codegen-${EPIC_ID}.json \
  phase=review version=${VERSION}
```

**After the loop exits:**

```
best_score = 0
best_version = 1

# (tracked across iterations by reading scores.json per version)

if verdict == "pass":
  cp v${VERSION}/diff.patch final-diff.patch
  status = completed
  epic_status = Generated
  if --fork-owner and not --dry-run: push and create PR
  break

if best_score >= 7.0:
  # Near-miss: push best version with human review note
  git -C .target-repo/ reset --hard <best-version-sha>
  cp v${best_version}/diff.patch final-diff.patch
  if --fork-owner and not --dry-run: push and create PR (note: near-miss)
  status = completed
  epic_status = Generated
else:
  # Fail: do NOT push code
  cp v${best_version}/diff.patch best-diff.patch
  status = exhausted
  epic_status = Failed
  report: "Best score was ${best_score} on v${best_version}"
```

**Context recovery:** If context compresses mid-loop, `review_cycle.py
dispatch-context` re-injects the dispatch loop with current EPIC_ID and
VERSION. This is wired into settings.json as a SessionStart hook.

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

4 independent reviewer agents, each a standalone definition in `.claude/agents/`:

| Dimension | Agent | Weight | Focus |
|-----------|-------|--------|-------|
| architecture | `.claude/agents/architecture-reviewer.md` | 30% | Repo conventions, structural fit, integration quality |
| tests | `.claude/agents/tests-reviewer.md` | 30% | AC coverage, TDD evidence, edge cases, assertion quality |
| lint | `.claude/agents/lint-reviewer.md` | 20% | Lint/typecheck/build pass, code style, error handling |
| intent | `.claude/agents/intent-reviewer.md` | 20% | AC alignment, scope check, semantic correctness |

Pluggable: add/remove/replace a dimension = add/remove an agent file +
update score_reviews.py weights.

## File Handoffs

Artifacts are files. They never enter your context as inline text.

| Artifact | Written by | Read by |
|----------|-----------|---------|
| strategy doc | fetch_epic.py (from Jira) | Orchestrator (context brief) |
| prototype-analysis/ | parse_prototype.js (Step 7.5) | Orchestrator (context brief), brainstorming subagent (screenshots) |
| context-brief.md | Orchestrator (Steps 5-7.5 summary) | Brainstorming design subagent |
| brainstorming-log.md | Brainstorming design subagent | Post-run analysis (not consumed by pipeline) |
| spec-review-log.md | Spec review gate agent | Post-run analysis (not consumed by pipeline) |
| codegen-spec.md | Brainstorming design subagent (validated by spec review gate) | SDD implementers, all reviewer agents |
| writing-plans-log.md | writing-plans subagent | Post-run analysis (not consumed by pipeline) |
| codegen-plan.md | writing-plans subagent (Step 9) | SDD (reads plan, dispatches tasks) |
| task-N-brief.md | SDD task-brief script | SDD implementer |
| task-N-report.md | SDD implementer | SDD task reviewer |
| review-package diff | SDD review-package script | SDD task reviewer, final reviewer |
| progress.md | SDD | SDD on resume |
| diff.patch | Orchestrator (git diff) | All reviewer agents |
| validation.json | validate_target.py | Lint reviewer agent |
| review-{arch,tests,lint,intent}.md | Reviewer agents (via review_cycle.py dispatch) | score_reviews.py (scoring), triage agent |
| review-wiring.md | Wiring verifier (via review_cycle.py dispatch) | Triage agent (not scored) |
| review-interactions.md | Interaction verifier (via review_cycle.py dispatch) | Triage agent (not scored) |
| revision-notes.md | Triage agent (iteration-reviewer) | Fix subagent |
| decision-log.md | Triage agent (iteration-reviewer) | Post-run analysis (not consumed by pipeline) |

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
