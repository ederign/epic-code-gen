---
id: 07-target-repo-lifecycle
title: Target repo lifecycle — clone to merged PR
type: plan
status: current
repos: [epic-code-gen]
decisions: [ADR-0025, ADR-0030, ADR-0031, ADR-0032]
---

# Target repo lifecycle

How the system touches somebody else's repository, in order.

## 1. Resolve

`run_pipeline.resolve_target_repo()` — keyword match against `config/repo_mapping.json`
(`{"<owner/repo>": {"keywords": [...]}}`, 6 repos), falling back to an LLM resolution
(`resolve_repo_via_llm`) using `config/`'s prompt when no keyword hits.

Seven target repos to date: `ederign/codeflare-sdk`, `ederign/kale`, `opendatahub-io/mlflow`,
`opendatahub-io/mlflow-go`, `opendatahub-io/odh-dashboard`, `opendatahub-io/pipelines-components`,
`project-codeflare/codeflare-sdk`.

## 2. Clone and branch

```bash
python3 scripts/clone_target.py <repo-url> <EPIC_ID> [--dest .target-repo] \
        [--fork-owner user] [--clean]
```

- Expands a bare `owner/repo` slug to a full URL (`eda859c`).
- Detects the upstream default branch rather than assuming `main` — one epic needed `master`.
- Ensures the fork exists, **syncs it and fetches upstream before branching** (`addaaa3`), so the branch is
  based on current upstream rather than a stale fork.
- Creates `epic/<EPIC_ID>`. `checkout_existing_branch()` is the review-response entry point.
- The `fork` remote carries an embedded token; `sanitized_url` keeps it out of error output (`ba23d02`).

## 3. Assess readiness

```bash
python3 scripts/repo_readiness.py <repo-path>
```

Six dimensions, score out of 12, **threshold 8**: integration tests, lint in CI, clear CI signals,
`CLAUDE.md`/`CONTRIBUTING.md`, `CODEOWNERS`, language properties. A repo below threshold is not a good
codegen target — the signals the review loop depends on aren't there.

`e766e5f` softened this from a hard gate; RHAI-68 ran at readiness 9 with `codeowners: 0`.

## 4. Toolchain preflight — **before generating anything**

```bash
python3 scripts/validate_target.py <repo-path> --preflight [--json]
```

Exit 2 = missing tool (distinct from exit 1 = failing check). Required tools come from repo markers
(`uv.lock`, `yarn.lock`) **and** from variable-expanded Makefile recipes for the exact lint/typecheck/test
targets that would run, following prerequisites — so an unrelated `docker-build` recipe doesn't gate
codegen.

A gap flags the epic and **generates nothing**; status stays `Ready` so it retries once the image is fixed.
A missing tool is an environment fault, not the epic's ([ADR-0025]).

## 5. Validate

```bash
python3 scripts/validate_target.py <repo-path> [--json] [--out FILE] [--checks lint,test]
```

Detects language (Go, Python, TypeScript, JavaScript, Rust) from markers and discovers commands from
Makefile targets and `package.json` scripts. Reports a check that couldn't execute as `unrunnable` with
`missing_tool`, never as a plain failure.

**Consumers read `all_passed`, never per-check keys.** Always produce the file with `--out`; never hand-write
it ([ADR-0024]).

## 6. Generate

Phase 2 of the skill, inside `.target-repo/` on `epic/<EPIC_ID>`. Commits accumulate on the branch;
`BASE_SHA` is recorded first so the diff is computable.

## 7. Open the PR

```bash
python3 scripts/push_to_fork.py …   # push to the fork
python3 scripts/create_pr.py …      # PR upstream from the fork branch
```

Uses the **target repo's own PR template** and detected default branch (`4169f06`, `19abb33`) so the PR
reads as a native contribution. Fork-based, under `dora-the-ai-coder` ([ADR-0030]). `da3beaf` handles
duplicate creation gracefully, because the convergence loop can reach this step twice.

## 8. Answer review comments

Per cycle, in this order ([ADR-0032]):

```bash
python3 scripts/rebase_pr.py <repo-path> <branch> [--base main] [--push-remote fork]
```

1. **Rebase onto upstream base first** ([ADR-0031]). Conflicts: `rebase_onto_base()` drives the git
   sequence, a subagent edits only the working tree. Push with `--force-with-lease`.
2. Triage comments — humans always, bots selectively (`config/review_config.json`).
3. One fix agent, all comments, one commit. **Only code inside our own diff**
   (`compute_diff_scope` / `is_comment_in_scope`).
4. Validate + `sanity-check-agent`. No re-scoring.
5. Reply to every comment; record IDs in `pr-replies.json`.

A cycle that rebases nothing and finds nothing actionable **does not consume an iteration**.

## 9. Done

`_ci_handle_pr_created` observes the merge (GitHub API, with a `gh` CLI fallback) and transitions to `Done`.
A PR closed unmerged goes back to `Ready` to regenerate.

## Cleanup

`make clean` removes `tmp/`, `.target-repo/`, `.context/`. The CI container is discarded anyway; the fork
branch persists deliberately, since the PR points at it.
