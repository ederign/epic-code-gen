---
id: task-gitlab-ci-and-ci-scripts
title: epic-code-gen-pipeline repo — GitLab CI and ci-scripts
type: task
status: done
repos: [epic-code-gen-pipeline]
jira: RHAIFIRST-202
commits: ["62508f3", "059967d", "9b30aba"]
decisions: [ADR-0010]
---

# Task: epic-code-gen-pipeline repo — GitLab CI and ci-scripts

## Goal

A thin CI shell that sets up the environment, runs the orchestrator, and pushes results.

## Context

Logic in YAML and shell cannot be unit-tested or run locally, so every iteration costs a pipeline run.

## Acceptance Criteria

- [x] `.gitlab-ci.yml` with codegen / trigger / secret-detection stages
- [x] Four shell scripts, none containing business logic
- [x] Manual trigger with `STRATEGY_KEYS` as the only operator input
- [x] OTEL collection wired in

## Files Likely Involved

- `.gitlab-ci.yml`
- `ci-scripts/setup-env.sh`
- `ci-scripts/run-codegen.sh`
- `ci-scripts/pipeline-post.sh`
- `ci-scripts/clone-data-repo.sh`

## Status

Done.

## Notes

16 files, 1,750 lines total. Data-repo clone auth took seven attempts before matching `strat-pipeline`'s scripts exactly. The untested shell seam is where [[bug-multi-strategy-runs-lose-run-record]] lives.
