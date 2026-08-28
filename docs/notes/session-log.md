---
id: session-log
title: Session log
type: plan
status: current
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
---

# Session Log

Dated activity across the three repos. Append a new entry at the **bottom** when you finish a
session ([AGENTS.md §5](../../AGENTS.md#5-workflow) step 10).

> **Entries before 2026-07-31 are reconstructed** from commit history and Jira, not written
> contemporaneously. They record what landed and what it cost, which is recoverable; they do not
> record what was considered and rejected, which mostly isn't. Commit SHAs are cited so any claim
> here can be checked against the diff. From 2026-07-31 forward, entries are written as the work
> happens.

---

## 2026-06-22 — Foundation

Repo created (`80c0b65`). Scaffolding, scripts, and tests in `ae79932`; frontmatter contracts and
schema module; `validate_target.py` (`0aecf6f`), `clone_target.py` (`6ff2c5f`), `repo_readiness.py`,
`score_reviews.py` (`db8d7da`); five reviewer rubrics (`13e55e0`); the `/epic-codegen` skill
(`b4000f3`); strategy fetching from Jira (`ec19870`).

**Discovered:** epic bodies contain escaped backticks that break template literals (`0293ea4`).
`epic-reports/` holds sensitive HTML and must be gitignored (`876a0f3`).

**Next:** run it on a real epic.

## 2026-06-23 — First passing epic

Reviewer agents became standalone definitions (`65ee857`). Superpowers SDD wired in for
implementation dispatch (`d2ceb4f`). Run index for the dashboard, all agents to opus, intent
reviewer reads the epic directly (`294b19f`).

**Completed:** RHAISTRAT-1749-E001 passed first iteration at 9.4 — 224 lines, 4 files, 6 new tests.

**Discovered:** `max_iterations` default of 9 is far too high for a first pass; cut to 3
(`726eea5`). It later went to 5, then 10, and the tree still holds five different defaults.

## 2026-06-26 — Jira becomes the input

Epic fetching moved from HTML reports to Jira directly, with a dependency DAG from "Blocks" links
(`46a08cd`). Pipeline orchestrator (`5bca12a`), target-repo resolution with LLM fallback
(`076ea82`), Jira transitions (`8b53239`), PR linking (`e9d023d`), idempotent runs (`2e59f0c`).
Fork creation / push / PR for CI (`a0de047`), git identity from token (`5d7c799`). All 12 SDD human
checkpoints given autonomous overrides (`450abd0`).

**Discovered:** `tee` buffers, so live CI output never appeared — `stream-claude.py` had to write
the log file itself (`74a1fc9`, after `4828b81`, `3be78c8`).

## 2026-06-27 — Pre-setup and clone hardening

Target repo set up before Claude runs, to save context and turns (`0bfd075`). Fork sync before
branching (`addaaa3`), slug expansion (`eda859c`), fork-mode default fix (`1e65d93`), rich HTML
drill-down (`436c032`), credential sanitizing in git error output (`ba23d02`).

**Discovered:** Claude exiting non-zero did not mean codegen failed (`1b06fbe`) — artifact presence
is the better signal. That fix is still a weak liveness proxy; see `docs/bugs/open/`.

## 2026-06-30 — Three repos, one pipeline

`Dockerfile.ci` (`356a192`) and `make ci-image*` (`48ce5bc`). PR lifecycle management (`f719edd`,
13 tests). **CI mode with the nine-state machine** (`c98dbbc`, 15 tests). Artifacts saved to the
data repo (`f46bf4a`, `6fd3e5d`).

Two repos created from nothing: `epic-code-gen-pipeline` (`.gitlab-ci.yml`, `ci-scripts/`,
`push-results.py`, dashboard generator) and `epic-code-gen-pipeline-data`.

**Discovered:** data-repo clone auth took seven attempts (`78e1cfb` … `a38dd3d`). Matching
`strat-pipeline`'s scripts exactly worked; guessing did not. Claude Code won't load
`.claude/settings.json` from a cloned workdir without a pre-seeded trust file (`fbf9438`).

**Created then hid:** `FOREDER.md` (`183622a`) — the project's best design doc — was removed from
tracking and gitignored the same day (`3bd2d3e`).

## 2026-07-02 — V2 review response

Review-response pipeline in three slices: foundation (`99c9bc6`), orchestrator and agents
(`2f263da`), state-machine integration (`6aecf9b`), merged at `7f4c35f` after its own review found
six issues (`48185b8`). Jira auto-assignment (`b7db47c`). State transitions written as data
(`7bedbb0`).

## 2026-07-03 — Story dashboard, state fall-throughs

Story-mode dashboard built (`9ba09f8` + polish). Three state fall-through fixes: `PRCreated` on
unprocessed comments (`1279fb2`), `Blocked` → codegen when deps resolve (`1045c53`),
`Ready` → `ReviewPending` (`df25f2e`).

**Discovered:** three fall-through bugs in two days is a symptom, not three bugs — the state machine
existed only as `if/elif` with no written transition table.

## 2026-07-04 — PR templates, dashboard moves out

Target repo's own PR template now used, default branch auto-detected (`4169f06`), compliance moved
into `create_pr.py` (`19abb33`). Story dashboard correctly relocated to
`epic-code-gen-dashboard` (`099a249`, `659cbfc`). In the pipeline repo, running the orchestrator
directly was tried (`db58afa`) and reverted the same day (`6e88f27`).

## 2026-07-08 → 07-10 — Ownership and budgets

`CODEOWNERS` added to the pipeline repo (`378db73`, AIPCC-21231). MR pipelines suppressed — the jobs
are manual and need CI variables (`8245fad`). Per-epic timeout to 3h (`b1b5b56`).
PR creation guarded against failed verdicts (`f7983c9`); `max_iterations` to 10 (`a747951`);
reviewers stopped citing patch line numbers (`34b6e8d`); history-aware triage and near-miss PR on
exhaustion (`cf1da6e`).

## 2026-07-09 — Scoring becomes arithmetic

**`a7326fe` — reviewers no longer choose scores.** They classify findings; Python computes
`max(1, 10 − 5C − 1.5I − 0.5M)`. `788f16f` caps any dimension holding a Critical at 5. Wiring
verification added (`5e19a14`). All sonnet references removed — agents inherit the session model
(`527fc9d`).

**Discovered:** a reviewer could previously write up a Critical and still award 8.5.

## 2026-07-11 — Spec-first generation, agents become files

Superpowers `brainstorming` generates the spec (`ffe24ea`); `writing-plans` generates the plan
(`d41a7c0`); each skill isolated in its own subagent (`3ba1751`). Pattern discovery expanded
(`d3a5a24`, `37a1d67`) and forced to run **before** brainstorming (`9b65e8c`). All 13 subagents
extracted to `.claude/agents/` (`f74a79c`, `daee4d7`, `f601ef2`) with per-agent logging (`44da7be`)
and skill-invocation verification (`bbce28f`). Reviewer calibration and cross-dimension dedup
(`24d8078`). Interaction verifier for runtime bugs (`d0f2a2d`).

**Discovered:** without enforced ordering, the design was invented before any evidence was gathered.

## 2026-07-14 → 07-17 — Prototypes and deterministic dispatch

UX prototype parsing via Playwright (`4def105`), UX acceptance criteria extraction (`75e70c9`),
prototype deviations made non-negotiable in triage (`bf0e7cc`). Review dispatch moved into
`review_cycle.py` (`13d9e63`, `f7da07c`) with an anti-fallback guardrail (`5e26193`).
Accepted-findings carry-forward (`050732f`); fix loop moved to a fresh-context subagent (`8a4a5c7`).
In the pipeline repo: run the orchestrator directly, for real this time (`fafa60d`); capture stderr
and logs as artifacts (`6ef9fcd`); timeout to 6h (`ce802ea`, `b87fc90`); progress heartbeat
(`fa8f340`); `pipeline-post.sh` moved to `after_script` so results persist through a crash
(`aff11df`).

**Discovered:** Playwright in a non-root container needed three separate fixes (`210c464`,
`5571f31`, `0346470`). `node_modules` had been committed (`f978330`).

## 2026-07-21 → 07-28 — Repo mappings

Mappings for codeflare-sdk and kale (`ebe0a2a`), repointed at upstream project-codeflare
(`0871f50`). Duplicate PR creation handled gracefully (`da3beaf`).

## 2026-07-29 — State integrity

**RHAIFIRST-374 fixed** (`e03689c`): `run-metadata.yaml` gets one owner per status field, writes
must merge, unmappable states fail loudly. **RHAIFIRST-375 and 376 fixed** (`164d21e`): rebase every
review cycle, handle top-level review bodies. Toolchain preflight gates codegen (`b439623`,
narrowed in `6704253`); `uv` verified without executing it (`e7c9dac`). **Validation authenticity
gate** (`8373536`): a `validation.json` the skill wrote itself forces `fail`.

**Discovered:** RHAISTRAT-2162 had deadlocked for two days with the job exiting 0 every time. Two
epics with merged-quality PRs (9.4 and 8.6) sat at `status: completed`, and three dependents stayed
Blocked forever.

## 2026-07-30 → 07-31 — Scope and honesty

Non-codegen epics skipped by label and project (`996640a`); `markdownlint-cli` added to the CI image
(`72817df`); the review-response path stopped hiding why the fix agent failed (`d807dca`).

**Created:** RHAIFIRST-391 (review gate is advisory — PR opened from an unreviewed version) and
RHAIFIRST-392 (pre-existing target-repo check failures scored as bad code, masking real findings).
Both open.

## 2026-07-31 — Adopt the work ledger

Moved from POC record-keeping to a real engineering record. Added `AGENTS.md` (handbook), `PLAN.md`
(index), and the `docs/` ledger: architecture, ADRs, phase plans, milestones, tasks, bugs.
Backfilled the history above from git and the RHAIFIRST-168 tree. Recovered `FOREDER.md` from
`3bd2d3e^`. Turned the accumulated debt into `docs/bugs/open/` and `docs/tasks/pending/` rather than
fixing it inline. Added the PR companion rule and `scripts/check_ledger.py`.

**Discovered while writing this:** `pipeline-post.sh:41` builds `--strategy-key <k>` per key;
argparse abbreviation-matches the `nargs="+"` `--strategy-keys` and **overwrites** rather than
appends, so `push_results` only ever loops over the last key. Verified empirically. Codegen
artifacts still land — `run_pipeline.py` writes them live and `commit_and_push` does `git add -A` —
but for every strategy except the last, the run never gets its state merged, its
`strategy-summary.json` regenerated, its `run-log.jsonl` entry appended, or its OTEL file copied.
The durable run record and the dashboard feed silently lose all but one strategy per pass.

Also: `epic-code-gen` had no CI and no linter for its own 10.5k Python lines, while its entire
purpose is enforcing lint on other repos.

**Created:** [ADR-0034], the full ADR set, and ~20 open bug files.
