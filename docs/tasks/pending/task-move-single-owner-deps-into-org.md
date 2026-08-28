---
id: task-move-single-owner-deps-into-org
title: Move the brains repo and CI image out of personal namespaces
type: task
status: pending
repos: [epic-code-gen, epic-code-gen-pipeline]
---

# Task: Move the brains repo and CI image out of personal namespaces

## Goal

Remove two bus-factor-one dependencies from the critical path.

## Context

CI clones `https://github.com/ederign/epic-code-gen.git` and runs `quay.io/ederignatowicz/epic-code-gen-ci:latest`. Both are personal namespaces. The other three repos live under `gitlab.com/redhat/rhel-ai/agentic-ci/`.

## Acceptance Criteria

- [ ] Brains repo moved or mirrored to an org namespace
- [ ] CI image published to an org-owned registry path
- [ ] `CLAUDE_REPO` and the image reference updated
- [ ] `CODEOWNERS` added to the brains repo, matching the other three

## Files Likely Involved

- `.gitlab-ci.yml`
- `Makefile`
- `Dockerfile.ci`

## Status

Pending.

## Notes

Blocking for any real production rollout, which is what RHAIFIRST-168 is about. Also worth resolving where this repo's canonical home is: it is on GitHub while its three siblings are on GitLab, which is why the ledger's CI is a GitHub Actions workflow.
