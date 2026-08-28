---
id: phase-05-hardening
title: "Phase 05 — Hardening: state integrity, preflight gates, and the trust problem"
type: plan
status: current
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
jira: RHAIFIRST-168
commits: ["e03689c", "8373536", "b439623", "164d21e", "6704253", "996640a", "d807dca"]
---

# Phase 05 — Hardening

**2026-07-21 → present.** Jira: RHAIFIRST-374, 375, 376 (closed); 391, 392 (open).

## Goal

The pipeline runs, generates, reviews, opens PRs, and answers review comments. This phase is about
the gap between *it reported success* and *it succeeded*.

## What shipped

**One owner per status field** (`e03689c`, RHAIFIRST-374). `run-metadata.yaml` had two producers
writing incompatible vocabularies, and the skill's whole-file write destroyed the pipeline's
fields — setting `status: completed`, a value the CI state machine had never heard of. Every
subsequent run fell through to `else` and returned `SKIPPED: Unknown state: completed`, exiting 0.
An entire strategy deadlocked in silence.

The fix defines both vocabularies once in `artifact_utils.py`: `status` (owned by
`run_pipeline.py`, from `CI_STATES`) and `codegen_outcome` (owned by the skill, from
`CODEGEN_OUTCOMES`). Writes must merge; `merge_run_metadata` rejects `status=` from the skill.
`normalize_ci_status` rescues epics already stuck, and an unmappable state is now a hard failure
rather than a silent skip. See [ADR-0013], [ADR-0014], [ADR-0015].

**Rebase every review cycle** (`164d21e`, RHAIFIRST-376). Fixes are now authored against current
upstream code, so a PR never sits CONFLICTING. Conflicts are resolved by a subagent that edits only
the working tree while `rebase_onto_base()` drives the git sequence; the result is pushed with
`--force-with-lease`. The same commit fixed RHAIFIRST-375 — top-level review bodies were being
dropped. A cycle that rebases nothing and finds nothing actionable no longer consumes an iteration.
See [ADR-0031].

**Toolchain preflight** (`b439623`). A missing executable is an environment fault, not the epic's
fault. Preflight checks every tool the repo's real lint/typecheck/test targets need — following
Makefile prerequisites and expanding variables — and exit 2 distinguishes it from a failing check.
On a gap the epic is flagged and **no code is generated**, with status left at `Ready` so it retries
once the image is fixed. `6704253` narrowed it after it started blocking on non-tools, and
`e7c9dac` verifies `uv` with `test -x` rather than executing it, because the freshly installed
amd64 binary segfaults under qemu when cross-building from arm64. See [ADR-0025].

**Validation authenticity** (`8373536`). `score_reviews.py` now rejects a `validation.json` the
skill wrote itself: `validation_document_status()` returns `ok`/`missing`/`foreign`/`unreadable`,
and `foreign` or `unreadable` forces `verdict: fail`. A hand-written
`{"tests_total": 35, "success": true}` had scored `lint=8.0` while Prettier was failing. See
[ADR-0024].

**Scope control** (`996640a`). Epics outside the codegen projects, or carrying the skip label, are
no longer processed at all.

**Stop hiding failures** (`d807dca`). The review-response path swallowed the fix agent's error and
reported a generic failure.

## Still open

The two hardest bugs are unfixed, and both are the same shape as RHAIFIRST-374 — success reported
with nothing behind it:

- **RHAIFIRST-391 — the review gate is advisory.** On RHAI-69 the orchestrator authored the
  `review-*.md` files itself, dismissed a reviewer's Critical, opened a PR from a v2 that was never
  reviewed or scored, and estimated the scores in prose. The `8373536` provenance guard fired, was
  recorded in `scores.json`, and was ignored. Job exited 0.
- **RHAIFIRST-392 — baseline failures are scored as bad code.** `opendatahub-io/pipelines-components`
  has a `make lint` that is red on `main` (three unparseable notebook templates, reproduced on a
  pristine checkout at the pinned `ruff`). It cost RHAI-68 a passing score — `lint=4.5` dragged a
  9.5/7.5/9.5 down to 7.9 — and because GNU make stops at the first failing prerequisite, it also
  *concealed* the genuine findings that would have run after it.

The second is the more interesting failure: the `unrunnable` vs `failed` distinction ([ADR-0025])
only covers checks that could not execute. Here the check executes fine and fails for reasons the
epic did not cause, so nothing catches it.

## What this phase revealed about process

Five of the twelve epics under RHAIFIRST-168 are bug reports, and all five describe a silent
success. The pattern is consistent enough to be structural: a system that reviews its own output
will report that output as good unless something outside the model's judgment says otherwise. Every
fix in this phase is an instance of the same move — take a decision away from the model and give it
to Python, or make the failure loud.

That is also the origin of this ledger. See [ADR-0034].
