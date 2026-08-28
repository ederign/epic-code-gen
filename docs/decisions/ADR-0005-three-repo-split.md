---
id: ADR-0005-three-repo-split
title: "Three-repo split: brains, CI shell, data store"
type: adr
status: accepted
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
jira: RHAIFIRST-200
commits: ["356a192", "c98dbbc"]
decisions: [ADR-0008, ADR-0010]
---

# ADR-0005: Three-repo split — brains, CI shell, data store

## Status

Accepted (2026-06-30). Rationale originally recorded in `FOREDER.md`, which was then untracked;
recovered at [`../architecture/99-historical-foreder.md`](../architecture/99-historical-foreder.md).

## Context

Productionizing the POC meant adding GitLab CI, durable state, and a dashboard. Putting all of it in
one repo would mix three things with genuinely different change rates and different audiences:
orchestration logic (changes daily, reviewed carefully), CI plumbing (changes rarely, needs CI
variables to test), and machine-generated run output (changes every run, never reviewed).

It would also mean every codegen run commits its own artifacts into the repo containing its own
source, so the tool's history and its output history interleave.

## Decision

Four repos, one responsibility each.

| Repo | Host | Role | Written by |
|---|---|---|---|
| `epic-code-gen` | GitHub `ederign/` | The brains: skill, agents, orchestration | Humans + agents |
| `epic-code-gen-pipeline` | GitLab `redhat/rhel-ai/agentic-ci/` | Thin CI shell | Humans |
| `epic-code-gen-pipeline-data` | GitLab, same group | Git-as-database: state + artifacts | CI bot |
| `epic-code-gen-dashboard` | GitLab, same group | Reads data repo → GitLab Pages | Humans |

The pipeline repo clones the brains repo at run time (`CLAUDE_REPO`, `--depth 1`) rather than
vendoring it, so the brains can ship without touching CI.

## Consequences

### Positive

- 336 commits of tool development are not buried under ~60 machine-generated artifact commits.
- The data repo can be wiped, pruned, or rewritten without touching the tool.
- The dashboard is a pure consumer, decoupled behind a multi-project trigger.

### Negative

- **Logic is duplicated across a repo boundary on purpose.** `push-results.py:merge_state_file` and
  its `PIPELINE_OWNED_KEYS` mirror `artifact_utils.merge_run_metadata`, because the two repos are
  cloned to different paths at run time and cannot import each other. They must be kept in sync by
  hand ([ADR-0014]).
- Four repos to keep in step; a contract change can need three PRs.
- **Two single-owner dependencies sit in the critical path**: the brains repo is on personal GitHub
  (`github.com/ederign/`) and the CI image on personal Quay (`quay.io/ederignatowicz/`), while
  everything else is under `gitlab.com/redhat/rhel-ai/`. Tracked in `docs/tasks/pending/`.
- No transactional boundary: a run can succeed in the brains repo and fail to persist in the data
  repo.
