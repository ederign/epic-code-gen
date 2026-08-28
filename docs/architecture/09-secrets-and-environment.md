---
id: 09-secrets-and-environment
title: Secrets and environment variables
type: plan
status: current
repos: [epic-code-gen, epic-code-gen-pipeline]
---

# Secrets and environment

Every environment variable the system reads, collected in one place for the first time. Verified by
sweeping all access patterns — including the `_env_int()` indirection in `review_response.py`, which a
naive `os.environ` grep misses.

## `epic-code-gen` — Python

The whole surface is six variables.

| Variable | Required | Read by | Default |
|---|---|---|---|
| `JIRA_SERVER` | ✔ | `jira_utils.require_env` | — |
| `JIRA_USER` | ✔ | `jira_utils.require_env` | — |
| `JIRA_TOKEN` | ✔ | `jira_utils.require_env` | — |
| `EPIC_CODEGEN_GITHUB_TOKEN` | ✔ | `github_utils` (`DEFAULT_TOKEN_VAR`) | — |
| `RH_FORGE_GITHUB_TOKEN` | | `run_pipeline.identity_for_repo`, via `config/repo_mapping.json` | — |
| `REVIEW_FIX_AGENT_TIMEOUT` | | `review_response._env_int` | `3600` |
| `REVIEW_SANITY_CHECK_TIMEOUT` | | `review_response._env_int` | `600` |

The GitHub token variable name is overridable per invocation via `--gh-token-var` / `--token-var`.

It is also overridable **per target repo**: a `config/repo_mapping.json` entry may name its own
`gh_token_var` alongside a `fork_owner`, and `identity_for_repo()` resolves both at every call site
that touches GitHub. The mapping holds the variable *name*, never a value — the credential is read
from the environment at the point of use, so it appears in neither the repo nor the CI log.
`RH_FORGE_GITHUB_TOKEN` is the first of these, for the private `rh-forge` org. See [ADR-0035].

> **Asymmetry worth knowing:** two agent timeouts are env-tunable, but
> `rebase_pr.CONFLICT_AGENT_TIMEOUT` (900s) and `MAX_CONFLICT_ROUNDS` (10) are plain constants. A
> long-running rebase conflict cannot be given more time without a code change.

## `epic-code-gen` — shell (`ci-scripts/run-claude.sh`)

| Variable | Purpose | Default |
|---|---|---|
| `CLAUDE_MODEL` | model passed to `claude -p` | `claude-opus-4-6` |
| `LOG_DIR` | where `claude-stderr.log` is written | `/tmp` |
| `LOG_FILE` | if set, the stream renderer writes here | unset |
| `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` | **set to 0**, disabling the background-task wait ceiling for CI subagents (`18d3cb0`) | — |

> **Contradiction on the record:** this script *pins* `claude-opus-4-6`, while `README.md`,
> `CLAUDE.md`, and `SKILL.md` all state that agents inherit the session model with no overrides
> ([ADR-0029]). Both cannot be true. Tracked in `docs/bugs/open/`.

## `epic-code-gen-pipeline` — CI variables

Set in GitLab project settings; **not** declared in `.gitlab-ci.yml`.

| Variable | Kind | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | secret | Vertex AI project |
| `GCP_SERVICE_ACCOUNT_KEY` | secret | base64 JSON, decoded to `/tmp/gcp-key.json` |
| `JIRA_API_TOKEN` | secret | mapped to `JIRA_TOKEN` |
| `JIRA_USER` | config | |
| `EPIC_CODEGEN_GITHUB_TOKEN` | secret | fork + PR operations, for every target without an override |
| `RH_FORGE_GITHUB_TOKEN` | secret, optional | the private `rh-forge` org only ([ADR-0035]) |
| `RESULTS_PUSH_TOKEN` | secret | pushes to the data repo |
| `STRATEGY_KEYS` | job input | space-separated strategy keys — the one operator input |
| `CODEGEN_TIMEOUT` | optional | seconds; default `21600` (6h) |
| `CLAUDE_MODEL` | optional | |
| `CLAUDE_REPO_BRANCH` | optional | branch of the brains repo to run |

Declared in `.gitlab-ci.yml`: `CLAUDE_CODE_USE_VERTEX=1`, `ANTHROPIC_VERTEX_PROJECT_ID`,
`CLOUD_ML_REGION=global`, `DISABLE_AUTOUPDATER=1`, `JIRA_SERVER`, `JIRA_TOKEN`, `CLAUDE_REPO`,
`RESULTS_REPO`, `DATA_REPO_DIR=/tmp/data-repo`, `GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-key.json`,
`SECRET_DETECTION_ENABLED`, `FF_TIMESTAMPS`.

Set by `run-codegen.sh` for telemetry: `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `OTEL_METRICS_EXPORTER=otlp`,
`OTEL_LOGS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`,
`OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318`, `OTEL_METRIC_EXPORT_INTERVAL=10000`,
`OTEL_LOG_FILE=/tmp/claude-otel.jsonl`.

## How secrets are handled

Three deliberate practices, worth preserving:

1. **Tokens are moved to disk and unset from the environment** before Claude Code starts, so the
   subprocess does not inherit them. `.codegen-base`'s `before_script` writes `RESULTS_PUSH_TOKEN` to
   `/home/claude-ci/.tokens/results` then `unset`s it, re-injecting it for exactly one command.
   `pipeline-post.sh` deletes `/home/claude-ci/.tokens` when done.
2. **Token length is logged, never the value** (`clone-data-repo.sh`).
3. **Token-embedded remote URLs are sanitized out of error output** —
   `github_utils.sanitized_url`, added in `ba23d02` after credentials appeared in a git error.

GitLab Secret Detection runs as its own stage in all three GitLab repos.

## Local development

`JIRA_SERVER`, `JIRA_USER`, `JIRA_TOKEN` are enough for read-only Jira work (`fetch_jira_epics.py
--json`, `fetch_epic.py`). `EPIC_CODEGEN_GITHUB_TOKEN` is needed for anything touching forks or PRs.

**Do not run `run_pipeline.py` locally** — it is CI-only. `--dry-run` is safe.
