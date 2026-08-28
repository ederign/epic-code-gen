---
id: ADR-0010-thin-ci-shell-fat-python
title: Thin CI shell, fat Python
type: adr
status: accepted
repos: [epic-code-gen, epic-code-gen-pipeline]
jira: RHAIFIRST-202
decisions: [ADR-0005, ADR-0012]
---

# ADR-0010: Thin CI shell, fat Python

## Status

Accepted (2026-06-30). Pattern adopted from the sibling `strat-pipeline`.

## Context

GitLab CI can express a lot in YAML and shell. It is also the worst place to put logic: you cannot
unit-test a `.gitlab-ci.yml`, you cannot run it locally, and every iteration costs a pipeline run and
a push.

## Decision

The pipeline repo holds only what must run in CI: environment setup, secret placement, cloning, the
invocation, and result pushing. Everything else is Python in `epic-code-gen`.

Concretely, the pipeline repo is **16 tracked files, 1,750 lines**, of which one file
(`push-results.py`, 477 lines) contains logic that lives nowhere else. Its four shell scripts do:

| Script | Job |
|---|---|
| `setup-env.sh` | decode GCP key, set `git safe.directory`, write tokens to disk |
| `clone-data-repo.sh` | clone or refresh the data repo with token auth |
| `run-codegen.sh` | clone the brains repo, start OTEL, invoke the orchestrator, copy artifacts |
| `pipeline-post.sh` | run `push-results.py` (in `after_script`) |

No branching on business logic in shell. `run-codegen.sh` calls `run_pipeline.py` and reports its
exit code.

## Consequences

### Positive

- The orchestrator has 703 tests and runs locally in `--dry-run`. The CI wrapper needs almost none.
- A logic change ships by pushing the brains repo; CI is untouched. The pipeline repo has 61 commits
  to the brains repo's 171.
- Secrets are handled in one small, reviewable place.

### Negative

- **The CI shell is nearly untested.** `push-results.py` has 16 tests; the four shell scripts,
  `otel-collector.py`, `otel-summary.py`, and `stream-claude.py` have zero. `make lint` in that repo
  is `shellcheck … || true` — it silently passes when shellcheck is absent.
- The untested seam is where a real bug lives: `pipeline-post.sh`'s `--strategy-key` argument
  construction (see `docs/bugs/open/`). A shell script assembling CLI flags for a Python argparse it
  cannot see is exactly the kind of coupling this split makes invisible.
- Two repos must agree on a contract (`artifacts/` layout, `pipeline-runs/actions.json`) that is
  enforced by neither.
