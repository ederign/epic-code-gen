---
id: 08-ci-topology
title: CI topology — GitLab pipeline, image, telemetry
type: plan
status: current
repos: [epic-code-gen, epic-code-gen-pipeline]
decisions: [ADR-0010, ADR-0011, ADR-0012]
---

# CI topology

CI lives in `epic-code-gen-pipeline` (GitLab). `epic-code-gen` itself had **no CI at all** until this
ledger added `.github/workflows/ledger.yml`.

## Pipeline

`.gitlab-ci.yml`. Stages: `codegen` → `trigger` → `secret-detection`.

**Workflow rule:** merge-request pipelines are suppressed (`never`) — the jobs are manual and need CI
variables (`8245fad`).

### `.codegen-base` (hidden template)

| Setting | Value |
|---|---|
| `tags` | `aipcc-small-x86_64` |
| `image` | `quay.io/ederignatowicz/epic-code-gen-ci:latest` |
| `timeout` | **6h** (raised from 4h to match `CODEGEN_TIMEOUT`, `b87fc90`) |
| `artifacts` | `when: always`, `expire_in: 30 days` — `claude-otel.jsonl`, `claude-stderr.log`, `pipeline-runs/`, `artifacts/` |

`before_script`:

1. `setup-env.sh`
2. Write `RESULTS_PUSH_TOKEN` to `/home/claude-ci/.tokens/results`, then **`unset` it** so the Claude
   subprocess cannot inherit it.
3. Re-inject it for exactly one command: `clone-data-repo.sh`.

### `codegen-run`

`when: manual`. Sole input `STRATEGY_KEYS` (space-separated); an inline guard exits 1 if it is empty.

- `script`: `run-codegen.sh "$STRATEGY_KEYS"`
- `after_script`: `pipeline-post.sh "$STRATEGY_KEYS"`

**`after_script` is deliberate** (`aff11df`): results persist even when codegen times out or crashes.
Caveat worth knowing — `after_script` is bounded by `RUNNER_AFTER_SCRIPT_TIMEOUT` (5 min default),
*independently* of the 6-hour job timeout, and it is where the data-repo clone-commit-push happens.

### `trigger-dashboard`

`needs: [codegen-run]`, multi-project trigger into `epic-code-gen-dashboard`. Guarded with
`if $CI_PIPELINE_SOURCE == "pipeline"` → `never`, to prevent trigger loops.

### `secret_detection`

GitLab's `Security/Secret-Detection.gitlab-ci.yml` template. Present in all three GitLab repos.

## `run-codegen.sh` — the execution wrapper

1. Preflight: require `JIRA_USER`, `GCP_PROJECT_ID`, `GCP_SERVICE_ACCOUNT_KEY`; `claude --version`.
2. Clone the brains repo `--depth 1` into `/tmp/claude-workdir`, log its HEAD for provenance.
3. Start `otel-collector.py` in the background; export the `OTEL_*` variables.
4. Start a **progress-monitor subshell**: every 300s tail new lines of `tmp/progress.log` prefixed `📋`,
   else print `⏱️ Heartbeat` (`fa8f340`).
5. **Invoke the orchestrator directly** ([ADR-0012]) inside `set +e` / `set -e` to capture `rc`:
   `python3 scripts/run_pipeline.py $KEYS --ci --data-repo /tmp/data-repo --fork-owner dora-the-ai-coder --timeout ${CODEGEN_TIMEOUT:-21600}`
6. Kill the monitor, `sleep 7` for OTEL flush, kill the collector (`d771535` fixed cleanup under `set -e`).
7. Print `otel-summary.py`, copy artifacts into `$CI_PROJECT_DIR`, `cat` stderr, `exit $rc`.

## Telemetry

- `otel-collector.py` — a ~100-line OTLP HTTP/JSON receiver on `127.0.0.1:4318`, appending
  `{ts, path, payload}` per POST to `claude-otel.jsonl`. Also maintains a 60s rolling token rate in
  `/tmp/claude-otel-rate.json` for live tokens/sec display.
- `otel-summary.py` — tokens per model (input / cacheRead / cacheCreation / output), cost per model, active
  time, API request count. Claude Code emits **delta-temporality** metrics, so all deltas are summed —
  which is what makes subagent usage count.
- `push-results.py:extract_otel_cost()` sums `claude_code.cost.usage` into the run log. ~$80 total logged.

Model access is via **Vertex AI** (`CLAUDE_CODE_USE_VERTEX=1`, `CLOUD_ML_REGION=global`), not the Anthropic
API directly.

## The image

`epic-code-gen/Dockerfile.ci`, UBI9, built multi-arch (`linux/amd64,linux/arm64`) via
`make ci-image` / `ci-image-push`. Layer-by-layer rationale — including which layers exist to fix a
specific bug — is in [ADR-0011].

## Result push

`pipeline-post.sh` → `push-results.py`: copy artifacts, **merge** `run-metadata.yaml` ([ADR-0014]),
regenerate `strategy-summary.json` and `summary.json`, append `run-log.jsonl`, copy the OTEL file, then
`git add -A` → commit → `pull --rebase -X theirs` → up to **3** push attempts. **Never force-pushes.**

> **Live defect:** `pipeline-post.sh:41` builds `--strategy-key <k>` per key. Argparse
> abbreviation-matches the `nargs="+"` `--strategy-keys` and **overwrites** rather than appends, so the
> per-key loop only ever runs for the last key. Verified. Codegen artifacts still land (`run_pipeline.py`
> writes them live and `git add -A` sweeps them up), but every strategy except the last loses its state
> merge, its `strategy-summary.json` refresh, its `run-log.jsonl` entry, and its OTEL file. See
> [`../bugs/open/`](../bugs/open/).

## Missing

- **No `resource_group`** on `codegen-run`, so concurrent runs race on the data repo.
- **No schedule.** Still manually triggered; the `resource_group` gap is the blocker.
- The four shell scripts, `otel-collector.py`, `otel-summary.py`, and `stream-claude.py` have **zero
  tests**. `make lint` is `shellcheck … || true`, which passes silently when shellcheck is absent.
