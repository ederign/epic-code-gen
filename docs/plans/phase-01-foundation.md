---
id: phase-01-foundation
title: "Phase 01 — Foundation: contracts, scripts, and the first passing epic"
type: plan
status: done
repos: [epic-code-gen]
commits: ["80c0b65", "ae79932", "0aecf6f", "6ff2c5f", "db8d7da", "b4000f3", "ec19870", "65ee857", "d2ceb4f"]
---

# Phase 01 — Foundation

**2026-06-22 → 2026-06-23. 19 commits.**

## Goal

Prove that an approved epic could be turned into a reviewed diff at all, and put down the
contracts the rest of the system would be built on.

## What shipped

**Contracts first.** `scripts/artifact_utils.py` established YAML frontmatter as the metadata
format with three schemas (`epic-task`, `codegen-run`, `codegen-review`) and a single validation
path; `scripts/frontmatter.py` wrapped it as a CLI so skills never parse YAML themselves.
`scripts/state.py` gave long-running skills a place to persist state that survives context
compression. See [ADR-0002], [ADR-0004].

**Target-repo assessment.** `validate_target.py` (`0aecf6f`) detects language from markers and
discovers lint/typecheck/test commands from Makefile targets and `package.json` scripts rather
than hardcoding them. `repo_readiness.py` scores a repo across six dimensions out of 12 with a
threshold of 8 — the gate that decides whether a repo is even a candidate.
`clone_target.py` (`6ff2c5f`) clones to `.target-repo/` and creates `epic/<EPIC_ID>`.

**Review.** `score_reviews.py` (`db8d7da`) aggregated reviewer output, and `rubrics/` defined five
dimensions with weights. Both the rubrics and the weights in them are now wrong and dead — see
[ADR-0021] and `docs/bugs/open/`.

**Orchestration.** `b4000f3` added the `/epic-codegen` skill; `ec19870` added strategy fetching
from Jira so the skill had business context, not just the epic body.

**Superpowers SDD** (`d2ceb4f`, 06-23) replaced hand-rolled implementation dispatch with the
`subagent-driven-development` skill, with the orchestrator acting as the human partner
([ADR-0017]). Reviewer agents became standalone definitions the same day (`65ee857`), and all
agents moved to opus (`294b19f`).

## Evidence

First end-to-end run: **RHAISTRAT-1749-E001** (expose `ModelConfig` on `Prompt`/`PromptVersion` in
the MLflow Go SDK). Passed on the first iteration — 9.4 weighted, 224 lines across 4 files, 6 new
tests. Lessons captured at the time in `71d8ecc`.

## What it got wrong

- **The rubric weights were invented and never reconciled.** `rubrics/` still claims architecture
  20% / tests 25% / intent 25% and a `patterns` dimension at 10%. The live weights are 30/30/20/20
  with no `patterns` dimension. Superseded but never deleted — 424 lines of confidently wrong
  calibration still in the tree.
- **`codegen-review` was designed and never used.** Its schema (`typecheck`, `intent_coverage`)
  predates the real dimensions, and nothing in the pipeline has ever written one.
- **`max_iterations` churned** 9 → 3 (`726eea5`) → later 5 → 10, leaving five different defaults
  in the tree. Still inconsistent today.
- One passing epic on one Go repo is not validation. That's what [Phase 02](phase-02-pipeline-orchestration.md)
  and RHAIFIRST-136 were for.
